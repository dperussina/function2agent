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


def test_the_job_census_reconciles_on_the_committed_tree() -> None:
    """Direction 4's negative control, separate from direction 1-3's.

    Without it every planted case below could pass over a reconciliation that
    reports a problem for any input at all.
    """
    assert instruments.reconcile_jobs() == []


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
# Direction 2, the 2026-08-12 widening. Until then this direction matched on a
# file-shaped pattern only, so `python -m mypy`, all three `python -m pytest`
# invocations and `go vet`/`go test`/`go build` were invisible to it while
# `--check` printed "every instrument the workflow runs is declared". Each
# newly-read form gets a firing arm, and — because the widening's whole
# justification is a measured zero false-positive rate — each rejected variant
# gets an arm asserting silence. Those silence arms are the load-bearing half:
# a matcher that fires on prose is worse than the gap it closes, and nothing
# else in this file would notice.


def test_a_module_form_gate_missing_from_the_census_is_reported(
    workflow: str,
) -> None:
    """The shape the old pattern could not see, planted in the shape it uses."""
    perturbed = workflow.replace(
        "      - name: The corpus gate\n",
        "      - name: A gate nobody listed\n"
        "        run: python -m ruff check src/\n\n"
        "      - name: The corpus gate\n",
    )
    assert perturbed != workflow, "the corpus gate step has moved"
    problems = instruments.reconcile(perturbed)
    assert any("ruff" in p and "no census entry names" in p
               for p in problems), problems


def test_a_go_subcommand_gate_missing_from_the_census_is_reported(
    workflow: str,
) -> None:
    perturbed = workflow.replace(
        "      - name: The corpus gate\n",
        "      - name: A gate nobody listed\n"
        "        run: go run ./cmd/planted\n\n"
        "      - name: The corpus gate\n",
    )
    assert perturbed != workflow
    problems = instruments.reconcile(perturbed)
    assert any("go run" in p and "no census entry names" in p
               for p in problems), problems


def test_a_specs_harness_missing_from_the_census_is_reported(
    workflow: str,
) -> None:
    """`specs/` was added because a real one was hiding there.

    The `slug-differential` job has always run a harness under `specs/`, and no
    census entry named it: the job was declared and reconciled by `name:`, so
    direction 4 passed, and direction 3's candidate list does not reach it.
    """
    perturbed = workflow.replace(
        "      - name: The corpus gate\n",
        "      - name: A gate nobody listed\n"
        "        run: python3 specs/001-discovery-validation/harness/nope.py\n\n"
        "      - name: The corpus gate\n",
    )
    assert perturbed != workflow
    problems = instruments.reconcile(perturbed)
    assert any("harness/nope.py" in p and "no census entry names" in p
               for p in problems), problems


def test_the_go_matcher_does_not_fire_on_prose_that_says_go_test() -> None:
    """The measured reason the Go matcher is anchored at a command position.

    Unanchored it fires 7 times over `ci.yml`'s job blocks and 4 are false: a
    job's own `name:`, and three `echo` lines. 3 true to 4 false is a worse
    ratio than either check relaxation `tools/README.md` records as declined.
    """
    silent = [
        'name: go test (the enforcement point)',
        'echo "::error::a package under ./... has no test files; '
        'go test exits 0 over it"',
        'echo "::error::go test reported zero outcomes; nothing was executed"',
        "echo '### go test — the enforcement point'",
        'echo "run go build before shipping"',
    ]
    for line in silent:
        assert instruments.references(line) == [], line


def test_the_module_matcher_does_not_fire_on_prose_that_says_python_dash_m() -> None:
    for line in ['echo "run python -m mypy locally first"',
                 'name: python -m pytest, both halves']:
        assert instruments.references(line) == [], line


def test_a_declared_mypy_error_string_is_not_read_as_an_invocation() -> None:
    """Why the path shape stops at `specs/` and does not reach `src/`.

    Extending it to `src/` adds exactly one firing over `ci.yml` and that one
    is this line — the *declared* error the type-check step asserts by
    identity, not an invocation of anything.
    """
    line = (
        """        KNOWN='src/runtime/runner.py:252: error: "LifecycleGateway" """
        """has no attribute "create"'"""
    )
    assert instruments.references(line) == []


def test_the_run_key_is_stripped_so_a_one_line_step_is_at_a_command_position(
) -> None:
    """Without this, the anchored Go matcher finds 1 of 3 rather than 3 of 3.

    `run: go vet ./...` and `go test ...` inside a `run: |` block are the same
    invocation wearing different YAML.
    """
    assert instruments.references("      - run: go vet ./...") == ["go vet"]
    assert instruments.references("        go test ./... -race") == ["go test"]
    assert instruments.references(
        "      - run: go build -o /tmp/f2a-proxy ./..."
    ) == ["go build"]


def test_a_sudo_env_prefix_does_not_hide_a_module_invocation() -> None:
    """`ci.yml` runs the privileged pytest half behind `sudo -E env "PATH=…"`."""
    assert instruments.references(
        '          sudo -E env "PATH=$PATH" python -m pytest tests -q -rs'
    ) == ["pytest"]


def test_a_line_matched_by_two_patterns_is_reported_once() -> None:
    """`python -m src.supervisor.preflight` is matched by `_REFERENCE` and by
    `_MODULE`. Reporting it twice would make one undeclared instrument look
    like two, and the count is what a reader acts on."""
    assert instruments.references(
        '          sudo -E env "PATH=$PATH" python -m src.supervisor.preflight'
    ) == ["src.supervisor.preflight"]


def test_direction_two_reads_something_on_the_committed_tree() -> None:
    """The vacuity floor, and it is the arm that would have caught the gap.

    A matcher that reads nothing reconciles perfectly with any census — which
    is `check_tampers.py`'s zero-extracted-proofs argument, and the failure
    `tools/README.md` opens with. The old pattern was not vacuous, so this arm
    alone would not have caught it; the two below are what pin the reach.
    """
    read, scanned = instruments.coverage()
    assert scanned > 100, scanned
    assert read > 0, read


def test_direction_two_reads_the_gates_that_used_to_be_invisible() -> None:
    """The regression arm for the widening itself.

    Each of these is an instrument `ci.yml` runs that direction 2 could not see
    before 2026-08-12 — pytest, the largest gate in the repository, among them.
    If a future edit narrows the matcher back, this fails rather than the
    census going quietly green over a smaller population.
    """
    text = instruments.WORKFLOW.read_text()
    seen: set[str] = set()
    for block in instruments._jobs(text).values():
        for line in block.splitlines():
            if line.lstrip().startswith("#"):
                continue
            seen.update(instruments.references(line))
    for token in ("mypy", "pytest", "go vet", "go test", "go build",
                  "specs/001-discovery-validation/harness/slug-differential/"
                  "slug_differential.py"):
        assert token in seen, (token, sorted(seen))


def test_every_invocation_token_a_census_entry_declares_is_actually_invoked(
) -> None:
    """The reverse of direction 2, over the new field.

    An `invocations` token nobody runs is a census claiming to bind something
    it does not — the same defect as a stale `anchor`, in the field added to
    close it. Direction 1 checks that for `anchor`; nothing would check it
    here.
    """
    text = instruments.WORKFLOW.read_text()
    seen: set[str] = set()
    for block in instruments._jobs(text).values():
        for line in block.splitlines():
            if line.lstrip().startswith("#"):
                continue
            seen.update(instruments.references(line))
    for entry in instruments.INSTRUMENTS:
        for token in entry.invocations:
            assert token in seen, (entry.name, token, sorted(seen))


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
# Direction 4 — the job census, by key and by `name:`.
#
# These fixtures live here rather than in `tools/selftest.py` because
# `selftest.py` runs the corpus check set against the two fixture corpora and
# carries no instruments arm at all; every direction of this reconciliation has
# been held from this file since finding 036. The arms below are the two plants
# that measured the gap at `8d74942`, where seven instruments stayed silent.


def test_the_job_census_is_not_empty() -> None:
    """A census over nothing reconciles perfectly with any workflow.

    The same vacuity floor `check_tampers.py` applies to zero extracted proofs,
    and the reason `reconcile_jobs` reports on an empty declaration rather than
    returning clean.
    """
    assert len(instruments.JOBS) >= 5
    assert len({j.key for j in instruments.JOBS}) == len(instruments.JOBS)
    assert len({j.name for j in instruments.JOBS}) == len(instruments.JOBS)
    problems = instruments.reconcile_jobs(declared=())
    assert any("census is empty" in p for p in problems), problems


def test_a_renamed_job_name_is_reported(workflow: str) -> None:
    """The plant nothing saw.

    Renaming a job's `name:` left `check_corpus.py`, `gen_claims.py --check`,
    `check_tampers.py`, `tools/selftest.py`, `instruments.py --check`,
    `tests/invariants/runner.py` and `pytest` all silent — measured at
    `8d74942`. Direction 1 reads the mapping key and cannot see this string.
    """
    perturbed = workflow.replace(
        "    name: go test (the enforcement point)",
        "    name: go test (the egress enforcement point)",
    )
    assert perturbed != workflow, "the go job's name has moved"
    problems = instruments.reconcile_jobs(perturbed)
    assert any("is named" in p and "here" in p for p in problems), problems


def test_a_job_with_no_name_at_all_is_reported(workflow: str) -> None:
    """`name:` is optional in Actions; GitHub falls back to the key. A declared
    name that nothing carries must not read as agreement."""
    perturbed = workflow.replace(
        "    name: go test (the enforcement point)\n", ""
    )
    assert perturbed != workflow
    problems = instruments.reconcile_jobs(perturbed)
    assert any("declares no `name:`" in p for p in problems), problems


def test_a_job_added_to_ci_and_missing_from_the_census_is_reported(
    workflow: str,
) -> None:
    """Direction 2's argument in the second population, and the other plant
    that nothing saw."""
    perturbed = workflow + (
        "\n  lint:\n"
        "    name: shellcheck (a seventh job nobody enumerated)\n"
        "    runs-on: ubuntu-latest\n"
        "    steps:\n"
        "      - uses: actions/checkout@v4\n"
    )
    problems = instruments.reconcile_jobs(perturbed)
    assert any("'lint'" in p and "does not declare" in p
               for p in problems), problems


def test_a_declared_job_the_workflow_does_not_define_is_reported(
    workflow: str,
) -> None:
    perturbed = workflow.replace("\n  go:\n", "\n  gotest:\n")
    assert perturbed != workflow, "the go job key has moved"
    problems = instruments.reconcile_jobs(perturbed)
    assert any("'go'" in p and "does not define it" in p
               for p in problems), problems


def test_a_job_that_drops_the_runner_identity_action_is_reported(
    workflow: str,
) -> None:
    """`ci.yml`'s fifth stated rule: every measurement carries the kernel it was
    taken on, recorded per job. This is what makes the `runner identity` entry's
    note a check rather than a transcribed count — it read "all five jobs" while
    six jobs used it."""
    first = workflow.index(instruments.IDENTITY_ACTION)
    perturbed = (
        workflow[:first]
        + workflow[first + len(instruments.IDENTITY_ACTION) + 1:]
    )
    assert instruments.IDENTITY_ACTION in perturbed, (
        "the perturbation removed every use, so this would not be testing "
        "a per-job reading"
    )
    problems = instruments.reconcile_jobs(perturbed)
    assert any("does not use" in p for p in problems), problems


def test_the_job_name_pattern_cannot_match_a_step_name(workflow: str) -> None:
    """The way direction 4 reads the wrong string.

    A step's name is `      - name:` at six spaces. If the pattern loosened to
    match those, a job would be compared against whichever step happened to sit
    first in its block, and the comparison would fail on the committed tree —
    or worse, pass by coincidence.
    """
    found = instruments._JOB_NAME.findall(workflow)
    assert found, "the pattern matched nothing, so it asserted nothing"
    assert sorted(found) == sorted(j.name for j in instruments.JOBS)


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
