"""The floor under the count vocabulary and the ceiling it announces.

`inventory-count` and `definition-count` both resolve a claimed count through
`inventory._to_int`, and both used to drop an unresolvable one through a bare
`continue`. A count the check could not read and a count that agreed with the
filesystem produced the same report — a silent pass — which is the false-green
shape these two checks exist to catch, sitting inside them.

Three things changed and this file is what holds them. The vocabulary runs to
ninety-nine instead of twenty-two. Every rule draws its number pattern from one
shared alternation through `{{COUNT}}`, rather than carrying its own — the six
private alternations stopped at ten, twelve, twenty and twenty-two, so the
binding ceiling was whichever rule was being read and never the one the module
documented. And a count above the vocabulary is now refused out loud.

**Why these arms are here and not in `tools/fixtures/known-bad/`.** The fixture
tree is the idiom for a corpus check and is where the count-versus-range unit
lives. It cannot hold these: the ceiling branch fires only where a rule's
pattern admits a token the vocabulary does not resolve, and the shipped rules
draw pattern and vocabulary from the same source precisely so that never happens
in a real tree. Reaching the branch takes a crafted rule, which is a config the
fixture roots do not have and should not gain — a fixture carrying one would be
asserting that the shipped configuration is inconsistent when it is not.

The ordering arm is the one worth naming. `inventory-count` resolved the count
*before* testing struck-ness, which was harmless while the parse could only fail
silently. Once it announces, that order reports a violation at every superseded
figure in the corpus — `specs/001-discovery-validation/plan.md`'s owner-decision
header alone carries fourteen struck counts on one line — and punishing the
strike convention is the thing the convention cannot survive.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "tools"))

from corpuscheck.checks.inventory import (  # noqa: E402
    CEILING,
    COUNT,
    _to_int,
    expand_pattern,
)
from corpuscheck.runner import load_config, run_checks  # noqa: E402

#: A rule pattern admitting a count the vocabulary does not resolve. Written as
#: an explicit alternation rather than through `{{COUNT}}` because the point is
#: the divergence: this is what a hand-written pattern looks like when it has
#: drifted from the parser behind it.
_OVER = r"(one hundred|ninety-nine|thirty-one)\s+research\s+documents"


def _tree(root: Path, claim: str, *, documents: int = 3) -> Path:
    """A corpus of `documents` research files and a README making `claim`."""
    (root / "research").mkdir(parents=True, exist_ok=True)
    for i in range(1, documents + 1):
        (root / "research" / f"{i:02d}-note.md").write_text(f"# Note {i}\n")
    (root / "README.md").write_text(f"# Corpus\n\n{claim}\n")
    return root


def _inventory(root: Path, pattern: str):
    cfg = load_config()
    cfg["include"] = ["README.md", "research"]
    cfg["exclude"] = []
    cfg["inventory_default_files"] = ["README.md"]
    cfg["inventory_rules"] = [
        {"name": "research-documents", "pattern": pattern, "glob": "research/[0-9]*.md"}
    ]
    result, _ = run_checks(root, config=cfg, names=["inventory-count"])
    return result


def _definition(root: Path, claim: str, pattern: str):
    """A feature whose `spec.md` defines three FRs and whose `plan.md` claims."""
    feature = root / "specs" / "001-f"
    feature.mkdir(parents=True, exist_ok=True)
    (feature / "spec.md").write_text(
        "# Spec\n\n"
        "- **FR-001**: The system MUST do the first thing.\n"
        "- **FR-002**: The system MUST do the second thing.\n"
        "- **FR-003**: The system MUST do the third thing.\n"
    )
    (feature / "plan.md").write_text(f"# Plan\n\n{claim}\n")
    cfg = load_config()
    cfg["include"] = ["specs"]
    cfg["exclude"] = []
    cfg["definition_count_files"] = ["specs/*/plan.md"]
    cfg["definition_count_target"] = "spec.md"
    cfg["definition_count_rules"] = [
        {"name": "functional-requirements", "namespace": "FR", "pattern": pattern}
    ]
    result, _ = run_checks(root, config=cfg, names=["definition-count"])
    return result


# --------------------------------------------------------------------------
# The vocabulary itself.
# --------------------------------------------------------------------------


def test_the_vocabulary_runs_past_the_ceiling_that_used_to_bind():
    """Twenty-two was the old ceiling and is no longer anywhere near the bound.

    The three checked here are the corpus's own live figures: the owner-decision
    register stands at thirty-one, the production specification defines
    fifty-eight functional requirements, and ninety-nine is the bound itself.
    """
    assert _to_int("twenty-two") == 22
    assert _to_int("twenty-three") == 23
    assert _to_int("thirty-one") == 31
    assert _to_int("fifty-eight") == 58
    assert _to_int("ninety-nine") == 99
    assert CEILING == 99


def test_the_ceiling_is_a_refusal_and_not_a_wrong_answer():
    """Above the bound `_to_int` returns `None` rather than a partial reading.

    A parser that resolved `one hundred and thirty-one` to `131` by ignoring
    what it did not understand would be worse than one that refuses: the check
    would compare a number it invented against the filesystem and report on it.
    """
    assert _to_int("one hundred") is None
    assert _to_int("one hundred and thirty-one") is None


def test_every_word_the_shared_alternation_offers_resolves():
    """Pattern and vocabulary are drawn from one source and cannot drift.

    The announcement exists for the case where they have; this asserts the
    shipped configuration is not that case, which is why no fixture holds it.
    """
    cfg = load_config()
    rules = cfg["inventory_rules"] + cfg["definition_count_rules"]
    assert rules, "no count rules configured, so this asserted nothing"
    for rule in rules:
        assert "{{COUNT}}" in rule["pattern"], (
            f"rule {rule['name']} carries its own number alternation. Every "
            "private alternation this repository had stopped at a different "
            "number, and the ceiling that bound was whichever rule was read."
        )


def test_the_shared_alternation_reaches_the_registers_the_corpus_keeps():
    """`{{COUNT}}` expands to something that matches the live spelled figures."""
    import re

    rx = re.compile(expand_pattern(r"({{COUNT}})\s+owner\s+decisions"), re.IGNORECASE)
    for word, value in (("thirty-one", 31), ("fifty-eight", 58), ("99", 99)):
        m = rx.search(f"{word} owner decisions")
        assert m, f"{word!r} is not matched by the shared alternation"
        assert _to_int(m.group(1)) == value
    assert "hundred" in COUNT, (
        "the alternation no longer matches a spelled count above the bound, so "
        "such a count fails to match at all — no site, no parse, no "
        "announcement, and a report indistinguishable from a verified count"
    )


# --------------------------------------------------------------------------
# The announcement, in both checks that carry it.
# --------------------------------------------------------------------------


def test_inventory_count_refuses_an_unreadable_count_out_loud(tmp_path):
    _tree(tmp_path, "This corpus holds one hundred research documents.")
    result = _inventory(tmp_path, _OVER)
    assert [v.severity for v in result.violations] == ["error"], (
        "an unreadable count reported as clean. A count this check did not read "
        "and a count that agreed produce the same output unless it says so."
    )
    assert "one hundred" in result.violations[0].found


def test_definition_count_refuses_an_unreadable_count_out_loud(tmp_path):
    result = _definition(
        tmp_path,
        "The specification states one hundred functional requirements.",
        r"(one hundred|ninety-nine)\s+functional\s+requirements",
    )
    assert [v.severity for v in result.violations] == ["error"], (
        "an unreadable count reported as clean, which is the failure this check "
        "exists to catch appearing inside it"
    )


def test_a_readable_count_that_agrees_still_passes(tmp_path):
    """The announcement did not turn a correct claim into a violation."""
    _tree(tmp_path, "This corpus holds three research documents.", documents=3)
    result = _inventory(tmp_path, r"({{COUNT}})\s+research\s+documents")
    assert result.violations == []
    assert result.skipped == [], "the rule read nothing, so this asserted nothing"


def test_a_readable_count_that_disagrees_is_still_a_warning(tmp_path):
    """The new error did not swallow the mismatch the check was built for."""
    _tree(tmp_path, "This corpus holds seven research documents.", documents=3)
    result = _inventory(tmp_path, r"({{COUNT}})\s+research\s+documents")
    assert [v.severity for v in result.violations] == ["warning"]


# --------------------------------------------------------------------------
# The ordering. The strike convention is what this protects.
# --------------------------------------------------------------------------


def test_a_struck_unreadable_count_is_not_announced(tmp_path):
    """Struck-ness is read before the count is, and the order is load-bearing.

    The corpus supersedes by striking and dating rather than by deleting. A
    check that resolves the number first announces at every superseded figure,
    and the only way to satisfy it would be to delete the history the
    convention exists to keep.
    """
    _tree(
        tmp_path,
        "This corpus holds ~~one hundred research documents~~ "
        "**three** research documents.",
    )
    result = _inventory(tmp_path, _OVER)
    assert result.violations == [], (
        "a struck count was announced. The strike is the corpus's escape and "
        f"punishing it makes the convention unsatisfiable: {result.violations}"
    )
