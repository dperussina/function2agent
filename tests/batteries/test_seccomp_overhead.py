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
#: Samples per arm, of which the median is taken.
#:
#: **Five, and it stays five on the evidence below rather than for want of
#: any.** Q-09's recorded decision — commit the mechanism, or fall back to an
#: audit channel — was to be taken against this battery's figure, and two CI
#: runs of the *same runner class* (31400931286 and 31403771772, both native
#: `6.17.0-1020-azure` x86_64 4 vCPU euid 0, CPython 3.12.13) moved every arm
#: 24–35% and flipped the control's sign. So the repeat count needed a basis.
#:
#: **What was measured, and it is one of the two quantities and not both.**
#: 30 sequential runs of this battery in one `f2a-dev:latest` container on
#: 2026-08-10 — Linux 6.12.76-linuxkit aarch64, euid 0 read from
#: `/proc/self/status`, 10 CPUs, CPython 3.12.13. That is **WITHIN-HOST
#: variance**. It is not between-runner variance and cannot stand for it.
#: `microseconds_per_notification`, median [min–max] over n=30:
#:
#:     path_heavy            61.55  [39.74 –  66.48]
#:     reference_app_api     74.72  [65.56 –  80.14]
#:     shell_heavy           79.26  [63.25 –  85.36]
#:     reference_app_socket  75.25  [34.62 – 506.77]
#:     compute_only         112.27  [ 4.75 – 400.42]   (27 of 30 rated)
#:
#: **A range over 30 draws is not the statistic two CI runs give**, and
#: comparing them would have been the whole defect of the exercise. Compared
#: like with like — the distribution of |relative gap| between two runs on this
#: host, 435 pairs per arm, against the single gap each CI pair shows:
#:
#:     arm                   local median  local max   CI gap   CI percentile
#:     path_heavy                    3.3%      50.3%    27.1%           83rd
#:     reference_app_api             3.8%      20.0%    36.9%          100th
#:     shell_heavy                   4.7%      29.8%    30.2%          100th
#:     reference_app_socket         11.5%     174.4%    43.6%           86th
#:
#: For two arms that gap exceeds all 435 local pairs. ~~So CI carries a
#: component this measurement does not account for, and the data cannot say
#: which: between-runner variance and a larger within-host variance on a 4-vCPU
#: x86_64 Azure guest predict the same observation.~~
#:
#: **Struck 2026-08-10 by a third draw — the inference, never the arithmetic
#: above, which is correct for the pair it describes.** Run 31409214955, same
#: runner class, gave 60.43 / 69.55 / 70.99 / 71.70 in that order. Against run
#: 31400931286 those are gaps of 1.2%, 2.2%, 6.7% and 8.9% — the **20th to 64th
#: percentile** of this host's within-host distribution, which is to say
#: unremarkable. Every pair involving 31403771772 is 23.6–43.6%, at the 83rd to
#: 100th.
#:
#: **So the observed spread is one anomalous run and not a wide runner class**,
#: and "every arm moved 24–35%" was a property of that run rather than of CI.
#: A fourth draw, 31410461698, keeps that reading and widens the concordant
#: band: excluding 31403771772, the three remaining runs sit 1.2–13.8% apart,
#: against local within-host medians of 3.3–11.5% and maxima of 20–174%.
#:
#: ~~The second thing is the useful one: 31403771772 is also the run whose
#: control flipped sign, so `UNRATED["non-positive-overhead"]` is an in-band
#: detector for exactly the run whose figures should not be compared. Two
#: independent signals picking out the same run out of three is what makes it an
#: outlier.~~
#:
#: **Struck by the fourth draw, which is the run that could falsify it and
#: did.** 31410461698's control flipped sign too — overhead -0.028136s, rate
#: withheld — and that run is *not* extreme on any other arm. So the control's
#: sign is **sensitive but not specific**: it fires on the anomalous run and
#: also on an ordinary one, and it must not be read as marking a run whose
#: figures are unusable. What it marks is exactly what it says — an arm whose
#: own difference came out non-positive, for that arm.
#:
#: **What the flip rate does carry is the first evidence separating the two
#: components above, and it is suggestive rather than established at n=4.** The
#: control went non-positive in 2 of 4 CI runs and in 3 of 30 here — 50% against
#: 10%. A sign flip happens when the difference is small next to the run-to-run
#: variation, so its frequency is a crude proxy for that variation, and the
#: proxy says CI's 4-vCPU x86_64 guest is the noisier host. That favours *larger
#: within-host variance on CI* over *between-runner variance* as the explanation
#: for the excess — the two readings the strike above says nothing separates.
#: Four runs cannot settle it, and the measurement named below still can.
#:
#: This host still differs from CI's in architecture, kernel and core count at
#: once, and `host_property_caveat` says in terms that two records on different
#: kernels are not a before and an after. Nothing here measures CI's own
#: within-host variance; that is still owed.
#:
#: **Hence no change, and the reasoning is the refusal rather than the
#: number.** Aggregating five runs into one — grouping the 30, which
#: approximates `REPEATS = 25` — does shrink the within-host range a long way
#: (path_heavy 43.4% → 4.9%, reference_app_api 19.5% → 4.0%, shell_heavy 27.9%
#: → 7.2%, reference_app_socket 627% → 16.5%). So more repeats demonstrably buys
#: within-host stability **on this host**. What it is not shown to buy is the
#: thing it would be raised for: if CI's excess component is between-runner,
#: more samples inside one run reduce it by exactly nothing, and raising the
#: count five-fold at 5× the wall clock on evidence that does not reach the
#: target is tuning a constant until the figures look stable.
#:
#: **What would decide it**, stated because the absence is a gap somebody
#: should close rather than a conclusion: repeat this battery k times *inside a
#: single CI run*, on one runner. That yields within-host variance for CI's own
#: host, and the difference between it and the across-run spread is the
#: between-runner component. It is the only measurement that makes this constant
#: decidable, and until it exists ~~a CI median is not a decidable basis for
#: Q-09~~ **a median over a single CI run is not a decidable basis for Q-09 —
#: refined 2026-08-10 from three runs rather than two** — which is a more useful
#: answer than a tuned number. A median over several runs is a different
#: proposition and is now a reachable one, because the anomalous run is a
#: minority of three and is flagged in-band by its control's sign rather than
#: picked out in hindsight. What no number of runs measures is the repeat count
#: *inside* one run, which is what `REPEATS` sets.
#:
#: **The denominator is not the noisy part, which rules out the other repair.**
#: `notifications_observed` was *identical* in all 30 runs for every arm
#: (2116 / 1189 / 1143 / 539 / 116), so the entire spread above is in the
#: timing numerator. Raising an arm's notification count would buy quantization
#: and not stability, and for `compute_only` it would destroy the control — an
#: arm that takes no paths is what makes it one.
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


# --- the rate, and the reason an arm may not have one ----------------------

#: Why an arm publishes no `microseconds_per_notification`, keyed by the reading
#: that withheld it.
#:
#: **Shape borrowed from `src/runtime/providers/costs.py`'s `UNPRICED`, and for
#: its reason rather than its style.** That table exists because a missing price
#: written as `0.0` is indistinguishable from a turn that cost nothing, and the
#: repair was `spend_usd: float | None` plus a recorded reason for every
#: absence. A rate is the same kind of quantity: `microseconds_per_notification`
#: is the one field here the module's own docstring calls *transferable*, so a
#: number standing where no rate could be computed is a figure that invites
#: subtraction and gets it.
#:
#: **An absence is recorded rather than left as a gap**, because a bare `null`
#: reads as an oversight and the next reader fills it in.
UNRATED: Mapping[str, str] = {
    "no-notifications": (
        "No notifications were observed, so there is no denominator. The "
        "overhead figure beside this stands on its own; a per-notification "
        "rate over zero notifications is not a smaller number, it is not a "
        "number."
    ),
    "non-positive-overhead": (
        "The supervised median came out at or below its own baseline, so the "
        "difference is not an overhead and no rate is derivable from it. "
        "Supervision is strictly additional work — an ioctl and a "
        "/proc/<pid>/mem read per notification — so a non-positive difference "
        "cannot be a measurement of its cost; it is evidence that the cost is "
        "below what this instrument resolves against run-to-run variation on "
        "this host. **The boundary is zero because the quantity's definition "
        "forbids crossing it, and for no other reason.** This is deliberately "
        "not a noise threshold: this battery has no measured noise floor, and "
        "a chosen one would be a fabricated constant silently deciding which "
        "figures get published. The consequence is stated rather than hidden — "
        "a *small positive* difference on this host is equally dominated by "
        "variation and this test does publish a rate for it. Closing that "
        "needs a measured floor, which is a measurement nobody has taken, and "
        "the honest form of not having it is a one-sided detector rather than "
        "an invented bound. **This is a property of the instrument and not of "
        "a runner, which is why it is fixed here rather than reported as CI "
        "flakiness.** CI run 31403771772 published ratio 0.9066, "
        "overhead -0.03922s and -502.82 microseconds per notification for the "
        "compute_only control over 78 notifications; 30 sequential runs on an "
        "unrelated host — 6.12.76-linuxkit aarch64, euid 0, 10 CPUs, "
        "2026-08-10 — put the same arm at or below zero in 3 of 30, low "
        "-0.022496s. A control that flips sign on two hosts of different "
        "architecture and kernel is the measurement doing this, not a noisy "
        "neighbour."
    ),
}


def notification_rate(
    overhead_seconds: float, notifications_observed: float
) -> tuple[float | None, str | None]:
    """The transferable figure, or the key in `UNRATED` naming its absence.

    Takes the **rounded** overhead the record publishes rather than the raw
    difference, so that the sign of `overhead_seconds` and the presence of a
    rate can never disagree in one artifact, and so a reader holding the record
    can re-derive one field from the other two.
    """
    if not notifications_observed:
        return None, "no-notifications"
    if overhead_seconds <= 0:
        return None, "non-positive-overhead"
    return round(overhead_seconds / notifications_observed * 1e6, 2), None


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
        overhead = round(supervised - baseline, 6)
        rate, unrated = notification_rate(overhead, observed)
        arms[name] = {
            "baseline_seconds": round(baseline, 6),
            "supervised_seconds": round(supervised, 6),
            # **Kept as a raw reading even when it is below 1.0, and the rate
            # beside it is not.** The ratio and the overhead are two measured
            # medians and their quotient and difference; they are what this run
            # observed and suppressing them would be discarding a reading. The
            # rate is *derived*, and its derivation is only valid where the
            # difference is an overhead.
            "ratio": round(supervised / baseline, 4) if baseline else None,
            "overhead_seconds": overhead,
            "notifications_observed": observed,
            "microseconds_per_notification": rate,
            # Always present, `null` where a rate was published. A key that
            # appeared only on the suppressing branch would be a key no reader
            # knows to grep for.
            "microseconds_per_notification_absent_because": (
                None if unrated is None else UNRATED[unrated]
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
    never touched. That is the silent-instrument family this repository keeps
    finding: `ci.yml`'s own header counts *"six instruments that produced a
    clean bit over a measurement that was absent, replayed or unnamed"*, and
    `tools/README.md` counts *"four instruments ... hardened in one week for the
    same defect"*. Neither number includes this one. `ci.yml` also already
    reasons correctly one level up about this very file: *"the file is missing
    exactly when the measurement did not happen."*

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


def test_no_arm_publishes_a_rate_its_own_overhead_contradicts(
    measurement,
) -> None:
    """The record's two derived fields agree, on this host's actual readings.

    `tests/unit/test_seccomp_overhead_record.py` proves `notification_rate` has
    this property against injected values; it cannot prove the *fixture* routes
    the arms through it. This is the same gap
    `test_the_records_caveat_is_re_derivable_from_the_environment_it_carries`
    closes for the caveat, and it is closable only where the fixture runs.
    """
    for name, arm in measurement["arms"].items():
        rate = arm["microseconds_per_notification"]
        reason = arm["microseconds_per_notification_absent_because"]
        if rate is None:
            assert reason in UNRATED.values(), (
                f"{name} published no rate and no recorded reason for the "
                "absence, which is the gap a later reader fills in"
            )
            continue
        assert reason is None, f"{name} published a rate and a reason for not"
        assert rate > 0, (
            f"{name} published {rate} microseconds per notification, a rate "
            "supervision cannot produce"
        )
        assert arm["overhead_seconds"] > 0, (
            f"{name} published a rate of {rate} over an overhead of "
            f"{arm['overhead_seconds']}s, so the two disagree in sign"
        )
