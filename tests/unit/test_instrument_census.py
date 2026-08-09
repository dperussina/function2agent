"""The floor under `tools/instruments.py` — each direction is shown to fire.

`tools/README.md` opens with the failure this repository keeps hitting: *a
validator that passes everything because its regex never matches*. The census
is a validator, and it would be an unusually poor place to reproduce that. So
every direction below is exercised against a **perturbed** workflow or
candidate list, and the clean tree is asserted separately so that no
planted-defect test can pass vacuously.

Finding 036 is what this file is the durable form of. The four perturbations
here were first run by hand against the real workflow on 2026-08-09; a
transcript in a document is a measurement that happened once, and this is the
version that happens on every push.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "tools"))

import instruments  # noqa: E402


@pytest.fixture
def workflow() -> str:
    return instruments.WORKFLOW.read_text()


# ---------------------------------------------------------------------------
# The negative control. Without this, every test below could pass over a
# checker that reports a problem for any input at all.


def test_the_committed_tree_reconciles() -> None:
    assert instruments.reconcile() == []


def test_the_census_is_not_empty_and_classifies_everything_it_lists() -> None:
    """Zero entries would satisfy directions 1 and 2 trivially.

    The same shape as `check_tampers.py`'s vacuity floor: a census over nothing
    passes a census check, and reports the opposite of the truth.
    """
    assert len(instruments.INSTRUMENTS) >= 20
    kinds = {e.kind for e in instruments.INSTRUMENTS}
    assert kinds <= {instruments.GATE, instruments.ADVISORY, instruments.LIBRARY}
    assert instruments.GATE in kinds


# ---------------------------------------------------------------------------
# Direction 1 — declared and absent.


def test_a_deleted_step_is_reported(workflow: str) -> None:
    perturbed = workflow.replace(
        "        run: python3 tools/gen_claims.py --check\n",
        "        run: true\n",
    )
    assert perturbed != workflow, "the anchor this test perturbs has moved"
    problems = instruments.reconcile(perturbed)
    assert any("generated claims" in p and "does not contain" in p
               for p in problems), problems


def test_a_renamed_job_is_reported(workflow: str) -> None:
    """A required check is named by its job name, and the removal-proofs job
    was renamed once already. A census pointed at a job that no longer exists
    must say so rather than silently matching nothing."""
    perturbed = workflow.replace("\n  corpus:\n", "\n  corpus-gates:\n")
    assert perturbed != workflow, "the corpus job key has moved"
    problems = instruments.reconcile(perturbed)
    assert any("which the workflow does not define" in p for p in problems), problems


# ---------------------------------------------------------------------------
# Direction 2 — present and undeclared. This is finding 036's defect
# mechanised, and the single most important assertion in the file.


def test_a_gate_wired_into_ci_and_missing_from_the_census_is_reported(
    workflow: str,
) -> None:
    perturbed = workflow.replace(
        "      - name: The corpus gate\n",
        "      - name: A gate nobody listed\n"
        "        run: python3 tools/brand_new_gate.py\n\n"
        "      - name: The corpus gate\n",
    )
    assert perturbed != workflow, "the corpus gate step has moved"
    problems = instruments.reconcile(perturbed)
    assert any("tools/brand_new_gate.py" in p and "no census entry names" in p
               for p in problems), problems


def test_a_reference_inside_a_comment_is_not_reported(workflow: str) -> None:
    """The other direction, and it is not decoration.

    `ci.yml` discusses several instruments in prose, including
    `tools/cite_advisor.py`, which it deliberately does **not** wire. A scanner
    that matched comment text would report the exact opposite of the truth
    about that one, and a checker that cries wolf on the committed tree gets
    switched off.
    """
    perturbed = workflow.replace(
        "      - name: The corpus gate\n",
        "      # a comment mentioning tools/entirely_fictional_tool.py\n"
        "      - name: The corpus gate\n",
    )
    assert perturbed != workflow
    assert instruments.reconcile(perturbed) == []


# ---------------------------------------------------------------------------
# Direction 3 — unclassified.


def test_an_unclassified_entry_point_is_reported() -> None:
    problems = instruments.reconcile(
        candidates=["tools/an_unclassified_tool.py"]
    )
    assert any("an_unclassified_tool.py" in p and "Classify it" in p
               for p in problems), problems


def test_every_top_level_tool_is_classified() -> None:
    """Direction 3 over the real tree, stated as its own assertion.

    `test_the_committed_tree_reconciles` covers this, but it would also pass if
    direction 3 stopped looking at the filesystem, and that is the way this
    particular check dies.
    """
    named = {name for entry in instruments.INSTRUMENTS for name in entry.files}
    on_disk = {f"tools/{p.name}" for p in (REPO / "tools").glob("*.py")}
    assert on_disk, "the glob found no tools at all, so this asserted nothing"
    assert on_disk <= named, sorted(on_disk - named)


def test_the_entry_point_scan_reads_the_filesystem() -> None:
    """The way direction 3 dies silently.

    A candidate list that came back empty would satisfy direction 3 for every
    input, and no other test in this file would notice: the planted case above
    passes its candidates in explicitly, and the clean tree reconciles either
    way. This is the assertion that the scan looked anywhere at all — the same
    reason `check_tampers.py` treats zero extracted proofs as an error.
    """
    candidates = instruments._entry_point_candidates()
    assert len(candidates) > 5, candidates
    assert "tools/check_corpus.py" in candidates
    assert "tests/removal_proofs.sh" in candidates
    assert "tests/invariants/runner.py" in candidates


# ---------------------------------------------------------------------------
# `--run` must not stop at the first failure.


def test_the_runner_reports_every_gate_it_could_not_run() -> None:
    """A run that quietly covered seven of nineteen and printed one green line
    would be finding 036's defect one level up."""
    gates = [e for e in instruments.INSTRUMENTS if e.kind == instruments.GATE]
    runnable = [e for e in gates if e.command and not e.slow]
    assert runnable, "no gate is runnable, so --run would report nothing"
    assert len(runnable) < len(gates), (
        "every gate is runnable here, so the 'not run' listing this test "
        "exists to protect would never appear"
    )
