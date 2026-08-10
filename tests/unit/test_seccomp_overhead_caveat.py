"""T101 — the measurement record's host caveat is a **reading**, not a constant.

`tests/batteries/test_seccomp_overhead.py` emits a record whose
`what_this_is_a_property_of` list is the part a reader is meant to consult
*before* comparing two figures. Its first entry named **Docker Desktop's
`linuxkit` VM** as a hardcoded string, and hardcoded is the whole defect: the
same module records `environment.kernel` correctly as a reading, so when CI ran
it on GitHub's native runner the emitted record carried prose naming a host the
measurement was not taken on, one line away from a machine-readable field that
was right. That is this repository's most frequently recurring defect class —
a claim that was true when written, in prose, beside a correct reading nobody
cross-checks.

**Why this file is in `tests/unit/` and not beside the battery.**
`test_seccomp_overhead.py` is `linux_only` and `privileged`. A test of the
caveat placed inside it would run on privileged Linux and nowhere else — which
is precisely the condition under which the defect shipped, because nothing on
the developer's macOS host could see it. So the caveat builder is a pure
function of three readings, with no kernel in it and no privilege, and it is
exercised here with **injected** environment values on whatever host is
running. There is no `skipif` in this file and there must not be one.

Loading the battery by path is the mechanism
`tests/unit/test_reference_app.py::test_t101s_reference_application_workloads_run_on_any_platform`
already uses to reach that module's contents from a platform-independent test,
for the same reason: the thing being checked decays silently between privileged
runs.

**The accepting set is closed, and that is deliberate.** `tools/README.md`
records two consecutive near-misses from classifiers written as complements —
"any errno but `EPERM`", then "the two errnos differ" — each of which would
have reported a refusing host as a working one. The same trap is available
here and is more tempting, because "no virtualization marker" reads so easily
as "bare metal". It is not. Nothing this process can observe establishes that a
kernel is running on hardware, so the unmarked branch says it cannot tell,
and `test_an_unrecognised_kernel_is_not_reported_as_bare_metal` is what holds
it to that.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

BATTERY = (
    Path(__file__).resolve().parents[1] / "batteries" / "test_seccomp_overhead.py"
)

# Two kernels this repository has actually measured on, and one it has not.
# The first two are the pair `ci.yml` warns about in terms: the recorded Q-09
# figure was taken on `6.12.76-linuxkit`, CI's native figure on
# `6.17.0-1020-azure`, and they "are not a before and an after and must not be
# subtracted". The third is the case that matters most for the classifier —
# a release string carrying no marker at all.
LINUXKIT = ("6.12.76-linuxkit", "aarch64", 0)
AZURE = ("6.17.0-1020-azure", "x86_64", 0)
UNMARKED = ("6.11.4-200.fc40.x86_64", "x86_64", 0)


@pytest.fixture(scope="module")
def battery():
    spec = importlib.util.spec_from_file_location("_t101_battery_caveat", BATTERY)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_host_caveat_differs_between_three_kernels(battery) -> None:
    """The load-bearing test, and the one a hardcoded string cannot pass.

    A constant returns one value for every input. Three distinct hosts must
    produce three distinct caveats, so any implementation that stops reading
    its arguments fails here regardless of *what* it hardcodes.
    """
    caveats = [
        battery.host_property_caveat(*LINUXKIT),
        battery.host_property_caveat(*AZURE),
        battery.host_property_caveat(*UNMARKED),
    ]
    assert len(set(caveats)) == 3, (
        "the host caveat did not vary across three different hosts, so it is "
        f"not a reading: {caveats}"
    )


def test_each_caveat_states_the_kernel_and_architecture_it_was_built_from(
    battery,
) -> None:
    """A caveat that varies but names nothing is a different kind of useless."""
    for kernel, machine, euid in (LINUXKIT, AZURE, UNMARKED):
        caveat = battery.host_property_caveat(kernel, machine, euid)
        assert kernel in caveat, f"{kernel!r} absent from its own caveat"
        assert machine in caveat, f"{machine!r} absent from its own caveat"


def test_the_linuxkit_case_stays_reachable_and_names_it(battery) -> None:
    """Q-09's recorded figure was taken on `6.12.76-linuxkit`, and a reader
    holding that record still needs to be told so.

    Making the caveat a reading must not make the linuxkit warning
    unreachable — it is the one case this repository has a committed
    measurement for.
    """
    caveat = battery.host_property_caveat(*LINUXKIT)
    assert "linuxkit" in caveat
    assert "bare" in caveat.lower(), (
        "the linuxkit caveat no longer says this is not a bare-metal figure"
    )


def test_an_unrecognised_kernel_is_not_reported_as_bare_metal(battery) -> None:
    """The complement trap, refused.

    Absence of a known virtualization marker is not evidence of hardware. A
    caveat that read "this is a bare Linux host" on any kernel it did not
    recognise would be the original defect with the sign flipped — it would
    assert a category nothing in the process can establish, and it would do it
    on exactly the hosts nobody anticipated.
    """
    caveat = battery.host_property_caveat(*UNMARKED)
    lowered = caveat.lower()
    assert "cannot" in lowered or "nothing" in lowered, (
        "the unmarked branch does not admit that it cannot tell a VM from "
        f"metal: {caveat!r}"
    )
    for asserted in ("is a bare", "on bare metal", "bare-metal host"):
        assert asserted not in lowered, (
            f"the unmarked branch asserts {asserted!r}, a category this "
            "process cannot observe"
        )


def test_every_caveat_warns_against_subtracting_two_records(battery) -> None:
    """The warning that must survive every branch.

    `ci.yml` says of the linuxkit and native figures that they "are not a
    before and an after and must not be subtracted". A reader comparing two
    records is the person this caveat exists for, so the warning cannot be
    something only the recognised hosts get.
    """
    for host in (LINUXKIT, AZURE, UNMARKED):
        caveat = battery.host_property_caveat(*host)
        assert "subtracted" in caveat, (
            f"no do-not-subtract warning for {host[0]}: {caveat!r}"
        )


def test_the_caveat_reports_the_privilege_it_ran_under(battery) -> None:
    """Privilege is the fourth reading, and it changes what the figure is.

    The measurement needs `CAP_SYS_ADMIN`-ish authority to install the filter
    at all; a record that does not say which euid produced it cannot be
    compared with one taken under `sudo`.
    """
    kernel, machine, _ = AZURE
    assert battery.host_property_caveat(kernel, machine, 0) != (
        battery.host_property_caveat(kernel, machine, 501)
    )


def test_the_full_caveat_list_leads_with_the_host_reading(battery) -> None:
    """The wiring, checked rather than assumed.

    A correct `host_property_caveat` that the record never calls would leave
    the defect exactly where it was. `property_caveats` is what the fixture
    puts in the record, so this asserts the reading reaches it — and that the
    entries after it, which really are constants about the supervisor and the
    workloads, are unaffected by the host.
    """
    linuxkit = battery.property_caveats(*LINUXKIT)
    azure = battery.property_caveats(*AZURE)

    assert linuxkit[0] == battery.host_property_caveat(*LINUXKIT)
    assert linuxkit[0] != azure[0]
    assert linuxkit[1:] == azure[1:], (
        "an entry after the first varied with the host; those are claims "
        "about the supervisor and the workloads, not about the machine"
    )


def test_the_reference_application_is_not_described_as_nonexistent(battery) -> None:
    """T116 landed on 2026-08-08 and the record's third caveat predates it.

    The module's list was corrected; `tests/batteries/results/
    seccomp-overhead.json` still carries the pre-T116 text because it is a
    *measurement artifact* and the honest repair for a stale one is a new
    measurement, not an edit. This holds the module half of that.
    """
    joined = " ".join(battery.property_caveats(*AZURE))
    assert "does not exist yet" not in joined
    assert "three workloads" not in joined
