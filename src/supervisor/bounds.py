"""T103, T105 — FR-049's four controls and the named terminal state each one
produces.

**Processor time is two bounds and the specification asks for one.** SC-023
asks two different things of FR-049: *zero sessions exceed the declared
processor bound*, and *a co-located reference workload on the same host keeps
serving throughout*. A cumulative CPU-seconds ceiling satisfies the first and
does nothing for the second, because a session can saturate every core briefly
and still be under its total. A rate quota satisfies the second and never ends
a session. Both are declared, both are recorded with the deployment identity,
both are enforced from outside — so this is an interpretation of FR-049 rather
than a narrowing of it, and it is the plan's, not this module's.

`pids.max` is **beyond** what FR-049 requires and is marked as an addition. A
fork bomb is the cheapest defeat of SC-023's co-located-workload clause, and
neither of the two processor bounds stops one.

**Nothing here has a default.** `from_config()` reads values that
`src/contracts/config.py` has already failed closed on (Q-10). There is no
code path in this module that invents a number.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from src.supervisor.cgroup import CgroupError, SessionCgroup

# FR-006 — a named member per bound. A generic error is never a terminal state.
TERMINAL_MEMORY = "terminated.memory_bound_exhausted"
TERMINAL_CPU = "terminated.cpu_bound_exhausted"
TERMINAL_PROCESS = "terminated.process_bound_exhausted"

BOUND_TERMINALS = (TERMINAL_MEMORY, TERMINAL_CPU, TERMINAL_PROCESS)


@dataclass(frozen=True)
class Bounds:
    """The declared bounds. Every field is required; none has a default."""

    memory_max_bytes: int
    cpu_max: str            # cgroup v2 `cpu.max` form: "<quota_us> <period_us>"
    cpu_total_seconds: float
    pids_max: int
    deployment_id: str      # FR-049 — both bounds recorded with the deployment

    def as_record(self) -> dict[str, Any]:
        return {
            "deployment_id": self.deployment_id,
            "memory_max_bytes": self.memory_max_bytes,
            "cpu_max": self.cpu_max,
            "cpu_total_seconds": self.cpu_total_seconds,
            "pids_max": self.pids_max,
            "pids_max_is_an_addition_beyond_fr049": True,
        }


def from_config(config: Mapping[str, Any]) -> Bounds:
    return Bounds(
        memory_max_bytes=config["SANDBOX_MEMORY_MAX"],
        cpu_max=config["SANDBOX_CPU_MAX"],
        cpu_total_seconds=config["SANDBOX_CPU_TOTAL"],
        pids_max=config["SANDBOX_PIDS_MAX"],
        deployment_id=config["F2A_DEPLOYMENT_ID"],
    )


def apply(cgroup: SessionCgroup, bounds: Bounds) -> None:
    """Write every control, then verify every one was accepted.

    The read-back is not defensive habit. `memory.max` silently clamps, a
    controller absent from `subtree_control` makes the file absent rather than
    erroring on open in some kernels, and a bound that was not actually applied
    looks exactly like one that was from the writing side. FR-049 is a property
    of the running session, so it is checked on the running session.
    """
    session = cgroup.paths.session
    writes = [
        ("memory.max", str(bounds.memory_max_bytes)),
        # A session that exceeds memory dies as a unit rather than losing a
        # random child, so the terminal state names the session's outcome and
        # not one process's.
        ("memory.oom.group", "1"),
        ("cpu.max", bounds.cpu_max),
        ("pids.max", str(bounds.pids_max)),
    ]
    for name, value in writes:
        path = session / name
        if not path.exists():
            raise CgroupError(
                f"{path} does not exist, so the {name} bound cannot be "
                "enforced from outside. FR-049 has no partial mode: the "
                "session does not start."
            )
        try:
            path.write_text(value)
        except OSError as exc:
            raise CgroupError(f"cannot set {name}={value!r}: {exc}") from None

    applied = {
        "memory.max": (session / "memory.max").read_text().strip(),
        "cpu.max": (session / "cpu.max").read_text().strip(),
        "pids.max": (session / "pids.max").read_text().strip(),
    }
    expected = {
        "memory.max": str(bounds.memory_max_bytes),
        "cpu.max": bounds.cpu_max,
        "pids.max": str(bounds.pids_max),
    }
    mismatched = {k: (expected[k], applied[k]) for k in expected
                  if applied[k] != expected[k]}
    if mismatched:
        raise CgroupError(
            "a bound was written but not applied as written: "
            + ", ".join(f"{k} wanted {w!r} got {g!r}"
                        for k, (w, g) in mismatched.items())
            + ". A clamped or ignored bound is an unenforced bound."
        )


@dataclass(frozen=True)
class BoundOutcome:
    """Why a session ended, named. Never a generic error (FR-006)."""

    terminal_state: str
    bound: str
    observed: str
    declared: str


def check(cgroup: SessionCgroup, bounds: Bounds) -> BoundOutcome | None:
    """One pass of the supervisor's watch loop. None means still within bounds.

    Order matters: memory and process bounds are enforced by the kernel and
    are reported as *already happened*, so they are read first. The cumulative
    processor total is the only one the supervisor itself enforces, because
    cgroup v2 has no cumulative CPU ceiling — `cpu.max` is a rate.
    """
    if cgroup.oom_kills() > 0:
        return BoundOutcome(
            terminal_state=TERMINAL_MEMORY,
            bound="memory.max",
            observed=f"oom_kill={cgroup.oom_kills()}",
            declared=str(bounds.memory_max_bytes),
        )
    if cgroup.pids_events_max() > 0:
        return BoundOutcome(
            terminal_state=TERMINAL_PROCESS,
            bound="pids.max",
            observed=f"pids.events max={cgroup.pids_events_max()}",
            declared=str(bounds.pids_max),
        )
    used = cgroup.cpu_usage_seconds()
    if used >= bounds.cpu_total_seconds:
        return BoundOutcome(
            terminal_state=TERMINAL_CPU,
            bound="cpu.stat usage_usec",
            observed=f"{used:.6f}s",
            declared=f"{bounds.cpu_total_seconds:.6f}s",
        )
    return None
