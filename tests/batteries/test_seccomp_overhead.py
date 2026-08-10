"""T101 / **Q-09** — measure the syscall supervisor's overhead **before the
mechanism is committed**.

Q-09 was accepted *with* the measurement, not with a prediction of its result.
The recorded fallback, if the overhead is prohibitive, is an audit channel that
keeps SC-022 and loses the before-execution property. This file produces the
number that decides.

**What the number is a property of, stated first because it is the part that
transfers least.** Every figure here is a property of:

  - ~~Docker Desktop's `linuxkit` VM on this host — **not a bare Linux host**.~~
    **Struck 2026-08-10: that sentence was a constant, and the record carried
    it onto hosts it had never been true of.** It was written on a laptop. When
    CI ran this module on GitHub's native runner the emitted record named
    `linuxkit` in prose while `environment.kernel`, one field away, correctly
    read `6.17.0-1020-azure`. The caveat is now a **reading**:
    `host_property_caveat` below builds it from the kernel release, the
    architecture and the euid the run actually observed. Syscall cost inside a
    virtualized kernel is not the syscall cost on metal, and syscall
    *interception* cost is the thing most sensitive to that — which is why the
    caveat about it was the part that most needed to stop being hardcoded.
  - The host's architecture, kernel version and core count, all recorded in
    the result file rather than described here.
  - A **CPython** supervisor answering notifications with `fcntl.ioctl` and a
    `/proc/<pid>/mem` read per attempt. A Go or C supervisor would be faster;
    how much faster is not measured and is not guessed at.
  - The five workloads below. Three are proxies — `shell_heavy`, `path_heavy`
    and the `compute_only` control — and two drive the reference application
    T116 built, over the two surfaces `app.py` names: `Application.call` is
    the in-process API sequence and `build_server` the socket arm.

**The shell-heavy arm on the reference application does not exist, and its
absence is deliberate and checked.** T101 asks for "the shell-heavy arm that
stresses it". `shell_heavy` below is that arm and has been measured since
2026-08-03; what T116 did not bring is a shell-heavy arm *of the reference
application*, and building one would have been a mistake rather than a gap.
The reference application composes no shell command — it spawns no process at
all, which `tests/unit/test_reference_app.py::
test_the_reference_application_spawns_no_process` asserts mechanically so the
claim is checked rather than argued. An arm that wrapped it in `sh -c` would
be measuring `sh`'s process spawn and the client's, attribute both to the
reference application, and hand back the proxy figure wearing the fixture's
name. The absence is recorded in the result file with this reasoning, and the
assertion is the tripwire: if anyone gives the reference application a
subprocess call, it fires and this clause reopens.

This corpus has been burned by exactly this class of error: a measured 1.0000
precision that turned out to be a property of the target rather than of the
mechanism. So the compute-only arm exists specifically to show that the
overhead is attributable to syscall interception — if it moved too, the number
would be measuring the VM's scheduler and nothing else.

Run:
    docker run --rm --privileged -v "$PWD:/work" -w /work f2a-dev \\
        python -m pytest tests/batteries/test_seccomp_overhead.py -s -v
"""

from __future__ import annotations

import json
import os
import platform
import statistics
import sys
import textwrap
import time
from collections.abc import Mapping
from pathlib import Path

import pytest

pytestmark = [
    pytest.mark.linux_only,
    pytest.mark.privileged,
    pytest.mark.skipif(sys.platform != "linux", reason="OD-17: Linux only"),
]

from src.supervisor import _linux, seccomp  # noqa: E402

RESULTS = Path(__file__).resolve().parent / "results"
REPO = Path(__file__).resolve().parents[2]
REFAPP_DIR = REPO / "tests" / "fixtures" / "reference-app"
REPEATS = 5

# --- the workloads --------------------------------------------------------

# Shell-heavy: process spawn plus the path resolution every exec performs. This
# is the arm Q-09 names, because an agent that composes shell commands pays
# this cost on every one of them.
SHELL_HEAVY = textwrap.dedent(
    """
    import subprocess
    for _ in range(30):
        subprocess.run(['/bin/sh', '-c', 'true'], check=True)
    """
)

# Path-heavy without exec: isolates the per-notification cost from the cost of
# spawning a process, which the shell arm conflates.
PATH_HEAVY = textwrap.dedent(
    """
    import os
    for i in range(2000):
        try:
            os.stat('/etc/hostname')
        except OSError:
            pass
    """
)

# Compute-only: the control. Takes no paths, so the filter never fires. If this
# arm slows down, the numbers above are measuring something other than
# interception.
COMPUTE_ONLY = textwrap.dedent(
    """
    total = 0
    for i in range(4_000_000):
        total += i
    """
)

# --- the reference application (T116) -------------------------------------
#
# The two arms `app.py` names, and the reason there are two: an overhead figure
# and a safety assertion must be measurements of one program, and T116's
# `test_the_origin_serves_the_same_bytes_the_in_process_call_returns` is what
# holds these two surfaces to that. Measuring only the socket arm would fold
# the HTTP stack's cost into the application's; measuring only the in-process
# arm would leave the surface an operator actually reaches unmeasured.
#
# The paths are interpolated at run time and are never written down: an
# absolute path into somebody's checkout does not belong in a committed file,
# and a relative one would depend on the subprocess's working directory.
_REFAPP_PREAMBLE = """
import sys
sys.path.insert(0, {repo!r})
sys.path.insert(0, {refapp!r})
import app, seed
"""

# The in-process API sequence. State is re-read each round on purpose — that
# read is the reference application's real filesystem contact, and hoisting it
# out of the loop would leave an arm that touches no path after import and
# measures the interpreter's startup instead.
REFERENCE_APP_API = _REFAPP_PREAMBLE + """
for _ in range(40):
    a = app.Application(seed.load_state())
    a.call('GET', '/health')
    a.call('GET', '/parts')
    a.call('GET', '/parts/P-0007')
    a.call('GET', '/shipments?part_id=P-0003')
    a.call('GET', '/shipments?part_id=P-0011')
"""

# The socket arm: the same operations over `build_server`, which is the surface
# an operator's session actually reaches.
REFERENCE_APP_SOCKET = _REFAPP_PREAMBLE + """
import json, threading, urllib.request
a = app.Application(seed.load_state())
server = app.build_server(a, host='127.0.0.1', port=0)
host, port = server.server_address[0], server.server_address[1]
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()
base = 'http://%s:%d' % (host, port)
try:
    for _ in range(40):
        for path in ('/health', '/parts', '/parts/P-0007',
                     '/shipments?part_id=P-0003', '/shipments?part_id=P-0011'):
            with urllib.request.urlopen(base + path, timeout=10) as r:
                json.loads(r.read().decode('utf-8'))
finally:
    server.shutdown()
    server.server_close()
"""


def _reference_app_source(template: str) -> str:
    return template.format(repo=str(REPO), refapp=str(REFAPP_DIR))


# --- which file a run writes, and why the branch is a function -------------

#: Q-09's *recorded* figure. **Tracked in git**, which is the whole reason the
#: two names below have to be told apart: `DURABLE_RECORD.is_file()` is true on
#: a fresh checkout, so an assertion built on it cannot fail for the reason a
#: test named "the measurement is recorded" claims to check. It was one, until
#: 2026-08-10.
DURABLE_RECORD = "seccomp-overhead.json"

#: What an ordinary privileged run produces. Gitignored, so its presence is a
#: statement about *this* run and not about the checkout.
LATEST_RECORD = "seccomp-overhead.latest.json"

#: The environment variable that promotes a run's figure to the recorded one.
RECORD_REQUEST = "F2A_RECORD_MEASUREMENTS"


def record_filename(environ: Mapping[str, str]) -> str:
    """Which of the two files *this* run writes, read from the environment.

    A function rather than an `if` inside the fixture, and it is the same
    argument `host_property_caveat` is: the branch has to be reachable from a
    test that runs on hosts this module cannot run on. It is also the only
    copy — a test that re-implemented the branch in order to check it would
    agree with itself while both halves drifted, which is the shape
    `tools/README.md` records as a stricter second opinion reporting rot it
    invented.

    Recording is **conditional by design** (see the fixture), so the honest
    question is never "does a file exist" but "does the file this run was asked
    for exist". Both branches produce something, so neither is a skip.
    """
    return DURABLE_RECORD if environ.get(RECORD_REQUEST) == "1" else LATEST_RECORD


#: Recorded in the result file rather than only in the docstring, because the
#: artifact outlives the module a reader would otherwise have to go and find.
SHELL_HEAVY_ABSENCE = (
    "There is NO shell-heavy arm of the reference application, and the "
    "absence is deliberate. T101's shell-heavy clause is discharged by the "
    "`shell_heavy` arm above. The reference application composes no shell "
    "command and spawns no process — asserted by "
    "tests/unit/test_reference_app.py::"
    "test_the_reference_application_spawns_no_process — so an arm wrapping it "
    "in `sh -c` would measure sh's process spawn and the client's, attribute "
    "both to the reference application, and reproduce the proxy figure under "
    "the fixture's name. If that assertion ever fires, this clause reopens."
)


# --- what the figure is a property of, read rather than asserted -----------
#
# Kernel-release substrings that positively identify a virtualized or cloud
# guest kernel, each with the reason it is here. **This is a closed accepting
# set and never a complement**, which `tools/README.md` records as the shape
# two containment checks nearly shipped with: "any errno but EPERM", then "the
# two errnos differ", each of which would have reported a refusing host as a
# working one. The tempting complement here is "no marker, therefore bare
# metal", and it is wrong for the same reason — the space of kernel flavours is
# open, and a host nobody anticipated would be classified by the branch nobody
# checked. So a match means *known guest*; everything else means *undetermined*
# and says so.
#
# The residual error is one-sided by construction: a bare-metal host running a
# kernel whose release string happens to contain one of these is over-warned.
# Over-warning a reader who is about to compare two figures costs a sentence.
# Under-warning them is the defect this table exists to end.
VIRTUALIZATION_MARKERS: dict[str, str] = {
    "linuxkit": "Docker Desktop's linuxkit VM",
    "azure": "an Azure hypervisor guest, which is what GitHub's hosted runners are",
    "aws": "an AWS EC2 guest",
    "gcp": "a Google Compute Engine guest",
    "cloud": "a distribution 'cloud' kernel flavour, which is built for guests",
    "microsoft": "WSL2's Microsoft kernel, a guest under a Windows host",
}


def host_property_caveat(kernel: str, machine: str, euid: int) -> str:
    """The first entry of `what_this_is_a_property_of`, built from readings.

    Three arguments, because three things are all this process can honestly
    observe about the machine underneath it: the kernel release, the
    architecture, and the privilege the measurement ran with. It deliberately
    does **not** take a host category, and it does not derive one — see the
    table above for why the unmarked branch declines to guess.
    """
    matched = sorted(
        marker for marker in VIRTUALIZATION_MARKERS if marker in kernel.lower()
    )
    where = (
        f"Kernel {kernel} on {machine}, measured at euid {euid}. "
    )
    if matched:
        named = "; ".join(VIRTUALIZATION_MARKERS[marker] for marker in matched)
        what = (
            f"That release string names {named}, so this is a figure from a "
            "virtualized kernel and not from a bare Linux host. "
        )
    else:
        known = ", ".join(sorted(VIRTUALIZATION_MARKERS))
        what = (
            "That release string carries none of the virtualization markers "
            f"this record knows how to recognise ({known}) — which is not "
            "evidence of hardware. Nothing this process can observe "
            "establishes whether the kernel is running on metal or in a "
            "guest, so the figure is a property of this kernel and not of a "
            "hardware class. "
        )
    return where + what + (
        "Syscall-interception overhead is the measurement most sensitive to "
        "that difference and it may not transfer. Two records taken on "
        "different kernels are not a before and an after and must not be "
        "subtracted."
    )


def property_caveats(kernel: str, machine: str, euid: int) -> list[str]:
    """Everything the figure is a property of: one reading, then four
    constants.

    The split is the point. The first entry varies with the host because it is
    a statement *about* the host; the rest are claims about the supervisor,
    the response flag and the workloads, which are properties of this file and
    would be just as true on any machine.
    """
    return [
        host_property_caveat(kernel, machine, euid),
        "A CPython supervisor doing one ioctl and one /proc/<pid>/mem read "
        "per notification. A Go or C supervisor would be faster by an "
        "unmeasured amount.",
        "Five workloads. `shell_heavy`, `path_heavy` and `compute_only` "
        "are proxies; `reference_app_api` and `reference_app_socket` "
        "drive T116's reference application over the two surfaces app.py "
        "names. The reference application existed from 2026-08-08; the "
        "earlier record here said it did not, which was true when it was "
        "written and is superseded.",
        "SECCOMP_USER_NOTIF_FLAG_CONTINUE as the response. A supervisor "
        "that denied or rewrote arguments would pay more.",
        "An interpreter start per round. Every arm pays it in both the "
        "baseline and the supervised run, so it cancels out of "
        "overhead_seconds and inflates notifications_observed — which is "
        "why microseconds_per_notification is the transferable figure and "
        "`ratio` is not.",
    ]


def _run_plain(source: str) -> float:
    started = time.perf_counter()
    pid = os.fork()
    if pid == 0:
        try:
            exec(compile(source, "<workload>", "exec"), {"__name__": "__main__"})
        finally:
            os._exit(0)
    os.waitpid(pid, 0)
    return time.perf_counter() - started


def _run_supervised(source: str) -> tuple[float, int]:
    observed = 0

    def count(_attempt: seccomp.Attempt) -> None:
        nonlocal observed
        observed += 1

    argv = [sys.executable, "-c", source]
    started = time.perf_counter()
    pid, listener = seccomp.spawn_with_listener(argv, count)
    os.waitpid(pid, 0)
    elapsed = time.perf_counter() - started
    time.sleep(0.05)
    listener.stop()
    return elapsed, listener.observed


def _run_unsupervised_subprocess(source: str) -> float:
    """The honest baseline for the supervised arm: same `execve`, no filter."""
    argv = [sys.executable, "-c", source]
    started = time.perf_counter()
    pid = os.fork()
    if pid == 0:
        os.execv(argv[0], argv)
    os.waitpid(pid, 0)
    return time.perf_counter() - started


def _median(fn, *args) -> float:
    return statistics.median(fn(*args) for _ in range(REPEATS))


@pytest.fixture(scope="module")
def measurement() -> dict:
    arms = {}
    for name, source in (
        ("shell_heavy", SHELL_HEAVY),
        ("path_heavy", PATH_HEAVY),
        ("compute_only", COMPUTE_ONLY),
        ("reference_app_api", _reference_app_source(REFERENCE_APP_API)),
        ("reference_app_socket", _reference_app_source(REFERENCE_APP_SOCKET)),
    ):
        baseline = _median(_run_unsupervised_subprocess, source)
        supervised_samples = [_run_supervised(source) for _ in range(REPEATS)]
        supervised = statistics.median(t for t, _ in supervised_samples)
        observed = statistics.median(n for _, n in supervised_samples)
        arms[name] = {
            "baseline_seconds": round(baseline, 6),
            "supervised_seconds": round(supervised, 6),
            "ratio": round(supervised / baseline, 4) if baseline else None,
            "overhead_seconds": round(supervised - baseline, 6),
            "notifications_observed": observed,
            "microseconds_per_notification": (
                round((supervised - baseline) / observed * 1e6, 2)
                if observed else None
            ),
        }

    record = {
        "question": "Q-09",
        "task": "T101",
        "measured_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "repeats_per_arm": REPEATS,
        "arms": arms,
        "environment": {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "kernel": platform.release(),
            # Recorded because the caveat below is built from it, and a
            # caveat quoting a reading the record does not carry cannot be
            # re-derived by anyone holding the artifact.
            "euid": os.geteuid(),
            "python": sys.version.split()[0],
            "cpu_count": os.cpu_count(),
            "audit_arch": hex(_linux.audit_arch()),
            "watched_syscalls": sorted(_linux.path_taking_syscalls()),
        },
        "shell_heavy_on_the_reference_application": SHELL_HEAVY_ABSENCE,
        "what_this_is_a_property_of": property_caveats(
            platform.release(), platform.machine(), os.geteuid()
        ),
    }
    RESULTS.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(record, indent=2, sort_keys=True) + "\n"

    # The committed record is Q-09's *recorded* measurement. Overwriting it on
    # every privileged run replaced a deliberate figure with whichever run
    # happened last — so a reviewer could not tell an intentional
    # re-measurement from a suite that ran in CI, and a real regression would
    # arrive as ordinary run-to-run noise in a file nobody reads twice.
    # Re-recording is now something you ask for.
    (RESULTS / record_filename(os.environ)).write_text(serialized)
    return record


def test_this_runs_measurement_reached_the_file_it_was_asked_for(
    measurement,
) -> None:
    """~~`assert (RESULTS / "seccomp-overhead.json").is_file()`~~

    **Struck 2026-08-10: that assertion could not fail for the reason its own
    name gave.** `seccomp-overhead.json` is *tracked in git*, so it is present
    on a fresh checkout and the test passed whether or not the run recorded
    anything. What an ordinary run produces is `seccomp-overhead.latest.json`,
    and the durable file is written only when `F2A_RECORD_MEASUREMENTS=1` — so
    on every CI run to date this was an existence check against a file the run
    never touched. That is the silent-instrument family `tools/README.md`
    counts at least eight of, and `ci.yml` already reasons correctly one level
    up: *"the file is missing exactly when the measurement did not happen."*

    Two things are asserted rather than one, because existence alone would
    close only half of it:

    - **The file this run was asked for**, chosen by `record_filename` from the
      environment. That is what separates *recording was not requested* from
      *recording was requested and did not happen* — the second fails here, the
      first cannot arise, because both branches write something. **No skip**: a
      test that skipped when the variable was unset would go silent on exactly
      the configuration CI runs under, which is the same defect wearing
      different clothes.
    - **That it holds this run's record**, not any record. Existence is still
      vacuous on the `F2A_RECORD_MEASUREMENTS=1` branch, for the original
      reason — the target is tracked. Content equality is not: the committed
      file is a 2026-08-03 linuxkit measurement and no fresh run reproduces it.
    """
    requested = os.environ.get(RECORD_REQUEST)
    path = RESULTS / record_filename(os.environ)
    assert path.is_file(), (
        f"the fixture completed a measurement and left nothing at {path.name}. "
        f"With {RECORD_REQUEST}={requested!r} that is the file this run was "
        "asked to write, so the measurement happened and the recording did "
        "not."
    )
    assert json.loads(path.read_text()) == measurement, (
        f"{path.name} exists but does not hold the record this run produced. "
        "The file is therefore left over from an earlier run — or the fixture "
        "wrote the other one of the two names — and reading it as this "
        "measurement is how a stale figure gets quoted as a fresh one."
    )
    print("\n" + json.dumps(measurement["arms"], indent=2))
    print("\nenvironment: " + json.dumps(measurement["environment"], indent=2))


def test_the_records_caveat_is_re_derivable_from_the_environment_it_carries(
    measurement,
) -> None:
    """The one step `tests/unit/test_seccomp_overhead_caveat.py` cannot reach.

    That file injects environment values, so it proves the caveat is a
    function of its arguments; it cannot prove the *fixture* passes this
    host's readings rather than somebody's favourite constants. Here the
    record is regenerated from the environment block the record itself
    carries, and the two must agree — which is only checkable where the
    fixture actually runs.

    Deliberately not named by a removal proof: this module is `linux_only` and
    `privileged`, so such a proof would report SKIPPED on every host that
    cannot run it.
    """
    environment = measurement["environment"]
    assert measurement["what_this_is_a_property_of"] == property_caveats(
        environment["kernel"], environment["machine"], environment["euid"]
    )


def test_the_filter_actually_fired_so_the_numbers_mean_something(
    measurement,
) -> None:
    """A measured overhead of zero because nothing was intercepted is not a
    measurement of the mechanism."""
    assert measurement["arms"]["path_heavy"]["notifications_observed"] > 1000
    assert measurement["arms"]["shell_heavy"]["notifications_observed"] > 100


def test_the_compute_control_shows_the_overhead_is_attributable(
    measurement,
) -> None:
    """The control arm. Takes no paths, so the filter never fires.

    If this moved with the others, every number here would be a property of
    the VM's scheduler rather than of interception, and the corpus has made
    that mistake before.
    """
    control = measurement["arms"]["compute_only"]
    assert control["notifications_observed"] < 200, (
        f"the compute-only arm triggered {control['notifications_observed']} "
        "notifications; it is not a control"
    )
    path_ratio = measurement["arms"]["path_heavy"]["ratio"]
    assert path_ratio > control["ratio"], (
        f"the path-heavy arm ({path_ratio}x) is not slower than the "
        f"compute-only control ({control['ratio']}x), so the overhead is not "
        "attributable to syscall interception"
    )


def test_the_reference_application_arms_ran_and_fired_the_filter(
    measurement,
) -> None:
    """T101's outstanding clause: the figure on the **reference application**,
    not on a proxy for one.

    Both surfaces `app.py` names are measured. A zero-notification arm here
    would mean the workload never reached the state on disk, which is the
    reference application's only filesystem contact and therefore the only
    thing the supervisor has to intercept.
    """
    for name in ("reference_app_api", "reference_app_socket"):
        arm = measurement["arms"][name]
        assert arm["notifications_observed"] > 100, (
            f"the {name} arm triggered {arm['notifications_observed']} "
            "notifications; it did not reach the application's state"
        )
        assert arm["microseconds_per_notification"] is not None


def test_the_absence_of_a_shell_heavy_reference_arm_is_recorded(
    measurement,
) -> None:
    """The clause T101 asks for and this file declines to build, recorded with
    its reasoning rather than dropped quietly."""
    recorded = measurement["shell_heavy_on_the_reference_application"]
    assert "spawns no process" in recorded
    assert "shell_heavy" in measurement["arms"]


def test_overhead_is_reported_not_asserted_against_a_threshold(
    measurement,
) -> None:
    """Q-09 owes a figure, not a pass mark.

    There is no threshold here on purpose. Inventing one would be exactly the
    unvalidated number FR-043 exists to prevent, and the decision Q-09 records
    — commit the mechanism, or fall back to an audit channel — is the owner's
    to make against the recorded figure.
    """
    for name, arm in measurement["arms"].items():
        assert arm["ratio"] is not None, f"{name} produced no ratio"
