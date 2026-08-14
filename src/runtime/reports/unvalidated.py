"""T192 — standing report of every value still marked unvalidated.

**Requirement**: FR-043. **Also**: FR-046, FR-047, FR-049, FR-050, OD-17.

The report names every configured value FR-043 still covers, and it names
the Linux kernel floor as a **different kind**. The configured entries are
numbers an operator typed or that shipped as a stated default. The floor
is a preflight constant read out of documented feature introduction
rather than out of a boot, and it is the only entry a measurement would
close (T205, deferred, so this entry stays on the report indefinitely).

## WHAT THIS MODULE WILL NOT DO

**1. It will not fold the kernel floor into the configured list.** The
four-and-the-window are values an operator configures. 5.14 is DERIVED
and NOT TESTED. Those are different facts. A single list that mixed them
would let a reader treat the floor as one more config key.

**2. It will not drop FR-049's two bounds because they lack
`unvalidated=True`.** `SANDBOX_MEMORY_MAX` and `SANDBOX_CPU_MAX` are
required with no default (Q-10). They do not appear in `Config.unvalidated`
— that tuple is keys that shipped a default. They are still unmeasured
numbers. `SANDBOX_CPU_TOTAL` and `SANDBOX_PIDS_MAX` are adjacent FR-049
keys; the task names two bounds, so those two stay off this list and
are named as a residual.

**3. It will not retag `DRIFT_CHECK_INTERVAL_SECONDS`.** The key's
description and FR-046's five-minute default are the deployment-clock
scheduler. The schema citation is FR-028 (T141 residual). Using the key
is correct. Retagging it is not this slice.

**4. It will not claim T205 ran, and it will not weaken DERIVED, NOT
TESTED.** Wording may not be weaker than the preflight's own, which
states the derivation and the untested status together. This module
imports `MINIMUM_KERNEL`, `MINIMUM_KERNEL_BASIS`, and
`MINIMUM_KERNEL_IS_TESTED` from `src/supervisor/preflight.py` and
repeats that pairing.

**5. It will not import the loop, serving, result, or judge package.**
It reads a Config it is handed and preflight constants. It invents no
measurement.

E13 is not this report. No `tick` lives here.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any, Mapping

from src.contracts.config import Config, ConfigError
from src.contracts.unvalidated import (
    MARKED_WHEN_REPORTED,
    PROVENANCES,
    SHIPPED_DEFAULTS,
    Unvalidated,
    mark,
)
from src.supervisor.preflight import (
    MINIMUM_KERNEL,
    MINIMUM_KERNEL_BASIS,
    MINIMUM_KERNEL_IS_TESTED,
)

SCHEMA_VERSION = "1.0.0"

KIND_SHIPPED_DEFAULT = "shipped_default"
KIND_REQUIRED_NO_DEFAULT = "required_no_default"
KIND_DERIVED_NOT_TESTED = "derived_not_tested"

#: Preflight's own pairing, quoted rather than paraphrased. Weakening
#: "NOT TESTED" here is the plant `test_the_kernel_floor_wording_is_not_weaker_than_preflight` applies.
KERNEL_WORDING = (
    "DERIVED from documented feature introduction and NOT TESTED on that "
    "kernel; every run to date was on 6.12 or 6.17"
)

FR028_CITATION_RESIDUAL = (
    "DRIFT_CHECK_INTERVAL_SECONDS is the deployment-clock scheduler "
    "FR-046's five-minute default describes. Its schema citation is "
    "FR-028 (T141 residual). Using the key is correct; retagging it "
    "is not this slice."
)

FR049_BOUNDS_RESIDUAL = (
    "SANDBOX_CPU_TOTAL and SANDBOX_PIDS_MAX are adjacent FR-049 keys. "
    "This report names the two bounds the task names — memory.max and "
    "cpu.max — and not the cumulative CPU-seconds ceiling or pids.max."
)

T205_DEFERRED = (
    "T205 is deferred by owner decision 2026-08-03, not planned work "
    "for v1. This entry stays on the report indefinitely. This module "
    "does not claim the matrix ran."
)


class ModuleTextUnavailable(RuntimeError):
    """This module's own text could not be located for the arm that reads it."""


def _value_of(config: Any, name: str) -> Any:
    """The bare configured number, or None if this config does not carry it."""
    if config is None:
        return None
    if isinstance(config, Config):
        try:
            return config.raw(name)
        except ConfigError:
            return None
    if isinstance(config, Mapping) and name in config:
        value = config[name]
        return value.value if isinstance(value, Unvalidated) else value
    return None


def _kind_of(name: str) -> str:
    if name in SHIPPED_DEFAULTS:
        return KIND_SHIPPED_DEFAULT
    if name in MARKED_WHEN_REPORTED:
        return KIND_REQUIRED_NO_DEFAULT
    raise ValueError(
        f"{name!r} is not a shipped default and not a required-no-default "
        "FR-043 value. The standing report does not invent a third class."
    )


@dataclass(frozen=True)
class ConfiguredEntry:
    """One operator-configured FR-043 value."""

    name: str
    kind: str
    requirement: str
    provenance: str
    value: dict[str, Any] | None

    def document(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "requirement": self.requirement,
            "provenance": self.provenance,
            "value": self.value,
        }


@dataclass(frozen=True)
class KernelFloorEntry:
    """The Linux kernel floor, as a distinct kind. DERIVED, NOT TESTED."""

    kind: str
    major: int
    minor: int
    basis: str
    derived: bool
    tested: bool
    wording: str
    closes_by: str
    t205_ran: bool
    t205_status: str

    def document(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "name": "MINIMUM_KERNEL",
            "version": f"{self.major}.{self.minor}",
            "major": self.major,
            "minor": self.minor,
            "basis": self.basis,
            "derived": self.derived,
            "tested": self.tested,
            "wording": self.wording,
            "closes_by": self.closes_by,
            "t205_ran": self.t205_ran,
            "t205_status": self.t205_status,
        }


@dataclass(frozen=True)
class UnvalidatedStandingReport:
    """FR-043's catalog. Configured values and the kernel floor, kept apart."""

    configured: tuple[ConfiguredEntry, ...]
    kernel_floor: KernelFloorEntry
    residuals: Mapping[str, str]

    def document(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "configured": [entry.document() for entry in self.configured],
            "kernel_floor": self.kernel_floor.document(),
            "residuals": dict(self.residuals),
        }


def _configured_entries(config: Any) -> tuple[ConfiguredEntry, ...]:
    """Every FR-043 configured value, including required-with-no-default.

    The loop is over `PROVENANCES`, not `Config.unvalidated`. Filtering on
    `unvalidated=True` would drop FR-049's two bounds and the reporting
    window — the plant
    `test_fr049_bounds_appear_though_they_lack_unvalidated_true` applies.
    """
    entries: list[ConfiguredEntry] = []
    for name in sorted(PROVENANCES):
        raw = _value_of(config, name)
        marked = mark(name, raw).marked_record() if raw is not None else None
        requirement = "FR-043"
        if name == "DRIFT_CHECK_INTERVAL_SECONDS":
            requirement = "FR-028"
        elif name == "STALENESS_CEILING_SECONDS":
            requirement = "FR-047"
        elif name == "CAPABILITY_LEASE_INTERVAL_SECONDS":
            requirement = "FR-050"
        elif name in {"SANDBOX_MEMORY_MAX", "SANDBOX_CPU_MAX"}:
            requirement = "FR-049"
        elif name == "REPORTING_WINDOW_SECONDS":
            requirement = "FR-045"
        entries.append(ConfiguredEntry(
            name=name,
            kind=_kind_of(name),
            requirement=requirement,
            provenance=PROVENANCES[name],
            value=marked,
        ))
    return tuple(entries)


def _kernel_floor() -> KernelFloorEntry:
    return KernelFloorEntry(
        kind=KIND_DERIVED_NOT_TESTED,
        major=MINIMUM_KERNEL[0],
        minor=MINIMUM_KERNEL[1],
        basis=MINIMUM_KERNEL_BASIS,
        derived=True,
        tested=MINIMUM_KERNEL_IS_TESTED,
        wording=KERNEL_WORDING,
        closes_by="T205",
        t205_ran=False,
        t205_status="deferred",
    )


def report(config: Any = None) -> UnvalidatedStandingReport:
    """The catalog: configured guesses, and the untested kernel floor apart."""
    return UnvalidatedStandingReport(
        configured=_configured_entries(config),
        kernel_floor=_kernel_floor(),
        residuals={
            "fr028_citation": FR028_CITATION_RESIDUAL,
            "fr049_adjacent_keys": FR049_BOUNDS_RESIDUAL,
            "t205": T205_DEFERRED,
        },
    )


def module_source() -> str:
    """This module's own text, for the arm that reads it for a fold."""
    module = inspect.getmodule(report)
    if module is None:
        raise ModuleTextUnavailable(
            "inspect.getmodule() could not locate the module defining "
            "report(), so this module's own text cannot be read. Refused "
            "rather than returned empty: the arm that calls this searches "
            "the text for a folded kernel floor and reports finding none, "
            "and text that was never read finds none either."
        )
    return inspect.getsource(module)
