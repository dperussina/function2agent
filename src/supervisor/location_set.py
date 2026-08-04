"""T098 — FR-048's declared location set, as versioned configuration stated
**positively**, with the effect-gate rule set and the egress policy
deliberately outside it.

FR-048's exact words: *"a location is reachable because it was declared, never
because nothing excluded it."* That is a statement about the shape of the
configuration, not only about the mechanism underneath it, and it is checkable
here: this module has no deny list, no exclusion pattern and no wildcard. The
only thing it can express is *this path, this mode, because of this rule*.

The second clause is the one that turns two separate assertions into one
boundary. FR-048 requires the effect-gate rule set of FR-012 and the egress
policy of FR-014 to lie outside the declared set. `load()` therefore takes
those two paths and **fails closed** if any declared location would contain
either — which is what makes FR-012's "no write path" and FR-014's "cannot
reach, modify, reconfigure or bypass" one thing a test can check rather than
two things a reviewer has to believe.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any

from src.contracts.canonical import content_address

SCHEMA_VERSION = "1.0.0"

VALID_MODES = ("ro", "rw")


class LocationSetError(RuntimeError):
    """The declared set is not usable. The session does not start."""


@dataclass(frozen=True)
class DeclaredLocation:
    """One mount. Every field is stated; none is inferred."""

    source: str          # path on the host
    target: str          # absolute path inside the session's namespace
    mode: str            # "ro" | "rw"
    nosuid: bool
    nodev: bool
    noexec: bool
    rule_id: str         # FR-011 — the rule a refusal names
    justification: str   # reviewable before it takes effect (FR-012, FR-019)

    def as_canonical(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "target": self.target,
            "mode": self.mode,
            "nosuid": self.nosuid,
            "nodev": self.nodev,
            "noexec": self.noexec,
            "rule_id": self.rule_id,
            "justification": self.justification,
        }


@dataclass(frozen=True)
class LocationSet:
    schema_version: str
    set_version: str
    deployment_id: str
    locations: tuple[DeclaredLocation, ...]

    def as_canonical(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "set_version": self.set_version,
            "deployment_id": self.deployment_id,
            "locations": [loc.as_canonical() for loc in self.locations],
        }

    def content_address(self) -> str:
        """FR-054 — the set is a versioned, content-addressed artifact."""
        return content_address(self.as_canonical())

    def declaring(self, path: str) -> DeclaredLocation | None:
        """The declaration that makes `path` reachable, or None.

        None is the answer for *every* path that was not declared. There is no
        second question about whether something excluded it.
        """
        candidate = PurePosixPath(os.path.normpath(path))
        best: DeclaredLocation | None = None
        for loc in self.locations:
            target = PurePosixPath(loc.target)
            if candidate == target or target in candidate.parents:
                if best is None or len(loc.target) > len(best.target):
                    best = loc
        return best

    def rule_for_refusal(self) -> str:
        """The rule identifier a refusal outside the set carries (FR-011)."""
        return f"FS-UNDECLARED-001@{self.set_version}"


def _require(obj: dict[str, Any], key: str, where: str) -> Any:
    if key not in obj:
        raise LocationSetError(f"{where}: missing required field {key!r}")
    return obj[key]


def parse(document: dict[str, Any]) -> LocationSet:
    version = _require(document, "schema_version", "location set")
    if version != SCHEMA_VERSION:
        raise LocationSetError(
            f"location set schema_version {version!r} is not {SCHEMA_VERSION!r}. "
            "A schema change is a MAJOR bump under FR-034 and must ship a "
            "migration, never be read leniently."
        )
    raw_locations = _require(document, "locations", "location set")
    if not isinstance(raw_locations, list) or not raw_locations:
        raise LocationSetError(
            "location set declares no locations. An empty set is not a "
            "configuration error to be defaulted around — declare the "
            "toolchain and the scratch volume explicitly (FR-048)."
        )

    seen_targets: set[str] = set()
    locations: list[DeclaredLocation] = []
    for i, raw in enumerate(raw_locations):
        where = f"location[{i}]"
        target = str(_require(raw, "target", where))
        if not target.startswith("/"):
            raise LocationSetError(f"{where}: target must be absolute, got {target!r}")
        target = os.path.normpath(target)
        if target in seen_targets:
            raise LocationSetError(
                f"{where}: target {target!r} is declared twice. Two "
                "declarations for one path means the effective mode depends "
                "on ordering, which is not a positive statement."
            )
        seen_targets.add(target)
        mode = str(_require(raw, "mode", where))
        if mode not in VALID_MODES:
            raise LocationSetError(f"{where}: mode must be one of {VALID_MODES}")
        rule_id = str(_require(raw, "rule_id", where))
        if not rule_id:
            raise LocationSetError(
                f"{where}: rule_id is empty. FR-011 makes the rule part of the "
                "record, so a location whose refusal could not name a rule is "
                "not declarable."
            )
        justification = str(_require(raw, "justification", where))
        if not justification.strip():
            raise LocationSetError(
                f"{where}: justification is empty. FR-012 and FR-019 require "
                "the set to be reviewable before it takes effect, and an "
                "unjustified entry is not reviewable."
            )
        locations.append(
            DeclaredLocation(
                source=os.path.normpath(str(_require(raw, "source", where))),
                target=target,
                mode=mode,
                nosuid=bool(raw.get("nosuid", True)),
                nodev=bool(raw.get("nodev", True)),
                noexec=bool(raw.get("noexec", mode == "rw")),
                rule_id=rule_id,
                justification=justification,
            )
        )

    return LocationSet(
        schema_version=version,
        set_version=str(_require(document, "set_version", "location set")),
        deployment_id=str(_require(document, "deployment_id", "location set")),
        locations=tuple(locations),
    )


def load(
    path: str,
    *,
    must_exclude: tuple[str, ...],
) -> LocationSet:
    """Load and assert FR-048's exclusion clause.

    `must_exclude` is FR-048's named pair — the effect-gate rule set of FR-012
    and the egress policy of FR-014 — plus anything else the caller requires to
    be unreachable. A declared location that would place any of them inside the
    namespace fails closed here, before a session starts.
    """
    try:
        with open(path, "rb") as fh:
            document = json.loads(fh.read().decode("utf-8"))
    except OSError as exc:
        raise LocationSetError(f"cannot read location set {path}: {exc}") from None
    except json.JSONDecodeError as exc:
        raise LocationSetError(f"location set {path} is not valid JSON: {exc}") from None

    location_set = parse(document)
    assert_excludes(location_set, must_exclude)
    return location_set


def assert_excludes(location_set: LocationSet, must_exclude: tuple[str, ...]) -> None:
    """FR-048's second clause, as a check rather than a convention."""
    violations: list[str] = []
    for excluded in must_exclude:
        norm = os.path.normpath(excluded)
        for loc in location_set.locations:
            src = PurePosixPath(loc.source)
            cand = PurePosixPath(norm)
            if cand == src or src in cand.parents:
                violations.append(
                    f"    {norm}\n"
                    f"      would be inside declared location "
                    f"{loc.target!r} (source {loc.source!r}, rule {loc.rule_id})"
                )
    if violations:
        raise LocationSetError(
            "The declared location set would expose something FR-048 requires "
            "to lie outside it:\n"
            + "\n".join(violations)
            + "\n\n  FR-048 puts the effect-gate rule set (FR-012) and the "
            "egress policy (FR-014) outside the declared set precisely so "
            "that FR-012's 'no write path' and FR-014's 'cannot reach, "
            "modify, reconfigure or bypass' are one checkable boundary. "
            "This session does not start."
        )
