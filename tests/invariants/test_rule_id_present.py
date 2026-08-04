"""INV-004 — every deny disposition carries a rule identifier (FR-011).

FR-011 makes the rule part of the record, not an annotation on it. So the check
is that a rule-less deny **cannot be constructed**, not that one is filtered out
downstream: a downstream filter drops the record, and a dropped denial is worse
than an unlabelled one.

The filesystem side and the egress side must agree on this, and the Go
enforcement point enforces the same thing in `src/proxy`. This file covers the
Python side; `go test ./src/proxy/...` covers the other.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from src.supervisor.fs_decisions import (
    ALLOW,
    DENY,
    RULES,
    RULES_BY_ID,
    DecisionSink,
    FilesystemDecision,
    decide,
)
from tests.fixtures.locations import location_set as _location_set


def test_a_deny_without_a_rule_id_cannot_be_constructed() -> None:
    with pytest.raises(ValueError, match="rule identifier"):
        FilesystemDecision(
            session_id="s1", disposition=DENY, syscall="openat",
            path="/etc/shadow", mode="absent", rule_id=None, reason=None,
            pid=1, at=0.0,
        )


def test_an_empty_string_is_not_a_rule_id() -> None:
    with pytest.raises(ValueError, match="rule identifier"):
        FilesystemDecision(
            session_id="s1", disposition=DENY, syscall="openat",
            path="/etc/shadow", mode="absent", rule_id="", reason="x",
            pid=1, at=0.0,
        )


@pytest.mark.parametrize(
    "syscall,path",
    [
        ("openat", "/etc/shadow"),
        ("openat", "/workspace/../etc/shadow"),
        ("unlinkat", "/workspace/file"),
        ("openat", None),
        ("newfstatat", "/proc/self/environ"),
    ],
)
def test_every_denial_path_produces_a_rule_id(syscall: str, path: str | None) -> None:
    decision = decide(
        _location_set(), session_id="s1", syscall=syscall, path=path,
        pid=7, now=0.0,
    )
    assert decision.disposition == DENY
    assert decision.rule_id in RULES_BY_ID
    assert decision.reason == RULES_BY_ID[decision.rule_id].reason


def test_an_allowed_path_is_allowed_so_the_check_is_not_vacuous() -> None:
    """A decide() that denied everything would pass the test above trivially."""
    decision = decide(
        _location_set(), session_id="s1", syscall="openat",
        path="/workspace/src/main.py", pid=7, now=0.0,
    )
    assert decision.disposition == ALLOW
    assert decision.rule_id is None


def test_rule_identifiers_are_unique_and_stable_strings() -> None:
    ids = [rule.rule_id for rule in RULES]
    assert len(ids) == len(set(ids))
    for rule in RULES:
        assert rule.rule_id.startswith("FS-")
        assert rule.reason and " " not in rule.reason


# --- the other side of the same invariant ---------------------------------
#
# The enforcement point is Go (Q-01), and FR-011 does not stop at a language
# boundary. `go test ./src/proxy/...` checks the pipeline's behaviour; this
# checks the *shape* of every deny site in the Go source, from the Python
# invariant suite, so one runner answers the question for the whole system.

REPO = Path(__file__).resolve().parent.parent.parent
PROXY = REPO / "src" / "proxy"

_CONST = re.compile(r'^\s*(Rule\w+)\s*=\s*"([A-Z0-9-]+)"', re.M)
_REGISTERED = re.compile(r'^\s*(Rule\w+):\s*\{Reason:', re.M)
_DENY_CALL = re.compile(r'(?<!func )\bdenyResult(?:WithPolicyRule)?\(\s*([^,\s)]+)')
# The two helpers take the identifier as a parameter and forward it. Those
# forwarding names are not rule identifiers and are not treated as ones; the
# check is on the *call sites*, which is where a bare string would be written.
_HELPER_PARAM = re.compile(
    r'func denyResult(?:WithPolicyRule)?\(([^)]*)\)'
)

requires_proxy = pytest.mark.skipif(
    not (PROXY / "rules.go").is_file(),
    reason="the Go enforcement point is not present in this tree",
)


@requires_proxy
def test_every_go_rule_constant_is_registered() -> None:
    source = (PROXY / "rules.go").read_text()
    declared = dict(_CONST.findall(source))
    registered = set(_REGISTERED.findall(source))
    assert declared, "no rule constants found; the parser is looking at the wrong shape"
    missing = sorted(set(declared) - registered)
    assert missing == [], (
        f"declared but not in ruleRegistry: {missing}. An unregistered "
        "identifier produces a disposition whose named reason is the empty "
        "string, which is FR-011's failure wearing a rule id."
    )


@requires_proxy
def test_every_go_deny_site_names_a_registered_constant() -> None:
    source = (PROXY / "rules.go").read_text()
    declared = {name for name, _ in _CONST.findall(source)}

    forwarded: set[str] = set()
    for path in PROXY.glob("*.go"):
        for signature in _HELPER_PARAM.findall(path.read_text()):
            forwarded.update(
                part.strip().split()[0]
                for part in signature.split(",") if part.strip()
            )

    offenders: list[str] = []
    for path in sorted(PROXY.glob("*.go")):
        if path.name.endswith("_test.go"):
            continue
        for match in _DENY_CALL.finditer(path.read_text()):
            first = match.group(1)
            if first in forwarded:
                continue
            if first.startswith('"'):
                offenders.append(f"{path.name}: bare string {first}")
            elif first not in declared:
                offenders.append(f"{path.name}: unknown identifier {first}")
    assert offenders == [], (
        "deny sites that do not name a registered rule constant:\n  "
        + "\n  ".join(offenders)
    )


@requires_proxy
def test_the_go_scanner_fires_on_a_planted_bare_string(tmp_path: Path) -> None:
    """The removal proof for the Go arm."""
    planted = tmp_path / "stage.go"
    planted.write_text(
        'package main\n\nfunc f() stageResult {\n'
        '\treturn denyResult("made-up-id", "because")\n}\n'
    )
    hits = [m.group(1) for m in _DENY_CALL.finditer(planted.read_text())]
    assert hits == ['"made-up-id"'], hits
    assert hits[0].startswith('"'), "the scanner would not flag a bare string"


@requires_proxy
def test_the_two_rule_namespaces_do_not_collide() -> None:
    """Filesystem rules are `FS-*`, egress rules `EG-*`.

    One shared namespace would make a record's rule identifier ambiguous
    between two registries, and the reader of a trace has no way to
    disambiguate after the fact.
    """
    go_ids = {value for _, value in _CONST.findall((PROXY / "rules.go").read_text())}
    py_ids = set(RULES_BY_ID)
    assert go_ids & py_ids == set()
    assert all(i.startswith("EG-") for i in go_ids)
    assert all(i.startswith("FS-") for i in py_ids)


def test_sink_reports_the_invariant_over_a_batch() -> None:
    sink = DecisionSink()
    location_set = _location_set()
    for path in ("/etc/passwd", "/workspace/ok.py", "/var/run/secret"):
        sink.emit(decide(location_set, session_id="s1", syscall="openat",
                         path=path, pid=7, now=0.0))
    assert sink.all_denials_carry_rule_id()
    assert len(list(sink.denials())) == 2
