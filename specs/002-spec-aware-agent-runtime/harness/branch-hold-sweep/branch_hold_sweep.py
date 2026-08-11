#!/usr/bin/env python3
"""The branch-hold sweep behind [finding 038] — every decision branch in the
corpus checker neutralised, and `tools/selftest.py` re-run against each one.

    python3 branch_hold_sweep.py --population        # derive and count, no runs
    python3 branch_hold_sweep.py --self-test         # offline, seconds, no sweep
    python3 branch_hold_sweep.py --sweep             # the whole thing, ~3 minutes
    python3 branch_hold_sweep.py --score results/branches-aaa329b.json

Finding 038 reported **222 held, 55 unheld, 2 unscorable** over **279** branches
at `aaa329b`, and the sweep that produced those numbers **was never committed**.
This file is the reimplementation. `--sweep` exits non-zero unless it reproduces
that triple *and* all nineteen per-module branch counts.

## What committing this alongside the record does and does not establish

Read this before quoting the pair as evidence of anything.

The numbers in `results/` were produced by **this** file. The numbers in finding
038 were produced by a different implementation that no longer exists. So at the
commit that introduces both, the agreement between them is a genuine
cross-check: two independently written classifiers, one of them reconstructed
from prose alone, reaching the same 279 verdicts. **After that commit it is a
regression guard and nothing more** — re-running `--sweep` and getting the
committed record back proves this file still does what it did, and proves
nothing whatever about finding 038.

A harness committed together with its own output, quoted later as though the
output corroborated the harness, is self-certification. That is the objection
the archive-as-exhibit ruling turned on, and the distinction above is the only
thing keeping this pair on the right side of it.

## The falsifiability control, which is an output rather than a claim

Reproducing 222/55/2 means little on its own: a rule that scored every branch
`held` would also be a rule, and the interesting question is whether *this* rule
is doing work. So every arm's outcome is recorded and then scored **twice**:

  * `precedence` — §1's stated rule. Inversion first; a forcing form only where
    the previous form raised or hung. Expected: **222 / 55 / 2**.
  * `first-non-zero` — the rule the finding's `held` repair rejected, under
    which any non-zero exit is a hold, crash included. Expected: **234 / 44 /
    1**, differing on **12** branches.

Both are computed from one set of runs, so the control costs nothing and cannot
drift away from the measurement it controls. `--sweep` fails if the two rules
agree, because two rules that agree on this population would mean the sweep had
stopped being able to tell them apart.

## Two properties that were learned the expensive way

**1. Bytecode writing is forbidden, not purged.** CPython validates a cached
`.pyc` against the source's *(mtime truncated to whole seconds, size)*. Every
`invert` mutation inserts exactly `not (` and `)` — **six characters, the same
six for every branch in the module** — so all of a module's inverted variants
have identical size, and two arms on one module inside the same second are
indistinguishable to that validator. The stale state is then **the previous
arm's mutation**, not the unmutated module, and the sweep scores a branch on
another branch's bytecode. That produced a confidently wrong **235/43/1** on
finding 038's first re-sweep attempt.

Purging `__pycache__` between arms *races the arms*: the purge and the next
interpreter's write are not ordered with respect to each other. Forbidding the
write is not a race. Three mechanisms, all applied, plus an assertion that they
worked:

  * `PYTHONDONTWRITEBYTECODE=1` in the child environment
  * `-B` on the child's command line
  * `sys.pycache_prefix` left unset, so neither can be routed around
  * `assert_no_bytecode()` before the first arm and after the last, which turns
    "we forbade it" into "none was written"

**The source-restoration check cannot see this fault, and that is the point
worth carrying forward.** Restoration verifies the *source*, and under the
stale-cache fault the source is correct at every single point — only the cache
is wrong. A harness whose integrity check is "the files are back" has no
opinion about bytecode at all. What caught it in finding 038 was the
reproduction check failing to match the per-module counts, which is a
downstream symptom; `assert_no_bytecode()` is the upstream one.

**2. A timeout is its own outcome.** `corpus.py:161` hangs — and it hangs in its
*enclosing* loop, not in the one whose test was neutralised, because the outer
loop advances its index only by the inner loop's result. Every arm is capped,
and a cap that fires is recorded `timeout`, never folded into a non-zero exit.
Conflating the two is the fabrication `f3f1c89` separated out: it turns "the
instrument could not answer" into "the instrument objected".

## The baseline comes from `git show`, never from a working tree

Finding 038 §8 records the harness reproducing, one level up, the defect it was
hunting: its first version took each file's pristine text by reading the working
tree, so a file left mutated by an earlier arm became the pristine text for
every arm after it — and the restore assertion passed, because the harness
restored to exactly what it had read. Pristine text here is `git show
<ref>:<path>` and nothing else, which is a baseline no arm can reach.

[finding 038]: ../../findings/038-corpus-check-branch-population-and-the-instrument-declined.md
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import secrets
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"

#: The commit the 279 verdicts are over. Deliberately not `HEAD`: between this
#: commit and `HEAD` the corpus checker gained a nineteenth check module
#: (`count_vs_range.py`) and four others grew, so `HEAD`'s population is a
#: different population and sweeping it answers a different question. Finding
#: 038 §9 predicted exactly this and it has come true.
REF = "aaa329b"

#: The fifteen files under `checks/` carrying the eighteen checks that existed
#: when the sweep ran, then the four shared modules the checks call into.
#: Ordered as finding 038 §2.1 and §2.2 order them, because the per-module
#: reproduction check reads positionally as well as by name.
CHECK_MODULES = (
    "catalog", "crossrefs", "definition_counts", "dry_run_verdict",
    "findings_numbering", "identifiers", "inventory", "lifecycle_taxonomy",
    "numeric_provenance", "preserved_evidence", "ratio_arithmetic",
    "register_ranges", "sum_arithmetic", "tables", "toc",
)
SHARED_MODULES = ("attest", "figures", "corpus", "search")

MODULE_PATHS: tuple[tuple[str, str], ...] = tuple(
    [(m, f"tools/corpuscheck/checks/{m}.py") for m in CHECK_MODULES]
    + [(m, f"tools/corpuscheck/{m}.py") for m in SHARED_MODULES]
)

#: Finding 038 §2.1's and §2.2's branch counts, transcribed. `--sweep` and
#: `--population` both fail unless the `ast` walk reproduces every one of the
#: nineteen. This is the check that establishes the sweep ran over *the same*
#: population rather than a similar one, and it is the check that caught the
#: stale-bytecode contamination when nothing else could.
EXPECTED_BRANCHES = {
    "catalog": 13, "crossrefs": 28, "definition_counts": 17,
    "dry_run_verdict": 13, "findings_numbering": 7, "identifiers": 16,
    "inventory": 13, "lifecycle_taxonomy": 25, "numeric_provenance": 23,
    "preserved_evidence": 4, "ratio_arithmetic": 9, "register_ranges": 10,
    "sum_arithmetic": 1, "tables": 13, "toc": 11,
    "attest": 12, "figures": 20, "corpus": 37, "search": 7,
}

#: Finding 038 §2.1's unheld column and §2.2's full table, transcribed. Reported
#: per module by `--sweep`; a disagreement is named rather than summed away.
EXPECTED_UNHELD = {
    "catalog": 0, "crossrefs": 6, "definition_counts": 5, "dry_run_verdict": 3,
    "findings_numbering": 0, "identifiers": 3, "inventory": 3,
    "lifecycle_taxonomy": 0, "numeric_provenance": 8, "preserved_evidence": 0,
    "ratio_arithmetic": 0, "register_ranges": 2, "sum_arithmetic": 0,
    "tables": 1, "toc": 1,
    "attest": 2, "figures": 10, "corpus": 9, "search": 2,
}

#: §2.3's combined triple, and §1's second box's figure for the rejected rule.
EXPECTED_PRECEDENCE = (222, 55, 2)
EXPECTED_FIRST_NON_ZERO = (234, 44, 1)
EXPECTED_DIFFERING = 12
#: *"**36** branches would be scored on a raising form"* — §1's second box. The
#: 12 above are the subset of those 36 whose verdict actually moves.
EXPECTED_RAISE_SCORED = 36

#: Every arm is capped here. Finding 038's sweep used the same twelve seconds
#: against a clean `selftest.py` it measured at 0.95s in its own worktree; the
#: cap is kept identical so the arms stay comparable across the two runs rather
#: than being re-derived against whatever hardware this runs on.
CAP_SECONDS = 12

HELD, UNHELD, UNSCORABLE = "held", "unheld", "unscorable"
VERDICT, RAISED, TIMEOUT, GREEN = "verdict", "raised", "timeout", "green"

#: The three neutralisation forms, in §1's order, as (prefix, suffix) inserted
#: at the test's span boundaries.
#:
#: Insertion rather than replacement, deliberately: a test may span several
#: lines and may carry a comment inside it, and rewriting the span as one line
#: would let a `#` swallow the rest of the expression. Inserting at the two
#: offsets leaves every intervening line exactly as it was.
FORMS: tuple[tuple[str, str, str], ...] = (
    ("invert", "not (", ")"),
    ("or-true", "(", ") or True"),
    ("and-false", "(", ") and False"),
)


# ---------------------------------------------------------------------------
# The population, derived rather than declared.


@dataclass(frozen=True)
class Branch:
    """One decision branch, with the exact source span of its test.

    The span carries the test's own source text so that every substitution can
    be verified against what it expects to find *before* it is made. A span
    that has drifted by a line rewrites a different expression and scores a
    branch nobody touched, which produces a number in the confident direction.
    """
    ident: str
    module: str
    relpath: str
    kind: str
    line: int
    col: int
    end_line: int
    end_col: int
    test: str


def _tests(tree: ast.AST) -> list[tuple[str, ast.expr]]:
    """§1's definition of a decision branch, applied by walking rather than declared.

    *"the test expression of an `if` or `elif`, a `while`, a conditional
    expression, a comprehension guard, or an `assert`"*. `elif` needs no case of
    its own: CPython represents it as a nested `If` in the parent's `orelse`, so
    walking every `If` reaches both.
    """
    found: list[tuple[str, ast.expr]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.If):
            found.append(("if", node.test))
        elif isinstance(node, ast.While):
            found.append(("while", node.test))
        elif isinstance(node, ast.IfExp):
            found.append(("ifexp", node.test))
        elif isinstance(node, ast.Assert):
            found.append(("assert", node.test))
        elif isinstance(node, ast.comprehension):
            found.extend(("comprehension", guard) for guard in node.ifs)
    found.sort(key=lambda pair: (pair[1].lineno, pair[1].col_offset))
    return found


def _span(lines: list[str], line: int, col: int, end_line: int, end_col: int) -> str:
    """The source text between two 1-based line / 0-based column offsets.

    Takes offsets rather than a node so that the same function reads a span off
    an `ast` node during derivation and off a `Branch` during substitution and
    restoration. Two implementations of "what text is at this span" is one more
    than the number that can be trusted to agree.
    """
    if line == end_line:
        return lines[line - 1][col:end_col]
    parts = [lines[line - 1][col:]]
    parts.extend(lines[line:end_line - 1])
    parts.append(lines[end_line - 1][:end_col])
    return "\n".join(parts)


def _branch_span(lines: list[str], branch: Branch) -> str:
    return _span(lines, branch.line, branch.col, branch.end_line, branch.end_col)


def population(sources: dict[str, str]) -> list[Branch]:
    """Every branch in the nineteen modules, in module then source order."""
    out: list[Branch] = []
    for module, relpath in MODULE_PATHS:
        source = sources[relpath]
        lines = source.split("\n")
        for index, (kind, node) in enumerate(_tests(ast.parse(source))):
            out.append(Branch(
                ident=f"{module}#{index:03d}",
                module=module,
                relpath=relpath,
                kind=kind,
                line=node.lineno,
                col=node.col_offset,
                end_line=node.end_lineno,
                end_col=node.end_col_offset,
                test=_span(lines, node.lineno, node.col_offset,
                           node.end_lineno, node.end_col_offset),
            ))
    return out


def neutralise(source: str, branch: Branch, form: str) -> str:
    """Insert one form's wrapper at the branch's span, verifying the span first."""
    prefix, suffix = next((p, s) for name, p, s in FORMS if name == form)
    lines = source.split("\n")
    found = _branch_span(lines, branch)
    if found != branch.test:
        raise AssertionError(
            f"{branch.ident}: the span at {branch.relpath}:{branch.line} reads "
            f"{found!r}, and the population recorded {branch.test!r}. The span "
            "has drifted; substituting here would neutralise a different "
            "expression and score a branch that was never touched."
        )
    # Tail first: rewriting the head would move the tail's column offset.
    tail = lines[branch.end_line - 1]
    lines[branch.end_line - 1] = (
        tail[:branch.end_col] + suffix + tail[branch.end_col:]
    )
    head = lines[branch.line - 1]
    lines[branch.line - 1] = head[:branch.col] + prefix + head[branch.col:]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Bytecode, forbidden rather than purged.


def child_env() -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env.pop("PYTHONPYCACHEPREFIX", None)
    return env


def bytecode_under(root: Path) -> list[str]:
    return sorted(
        str(path.relative_to(root))
        for path in root.rglob("__pycache__")
        if path.is_dir() and any(path.iterdir())
    )


def assert_no_bytecode(root: Path, when: str) -> None:
    """Turn "we forbade the write" into "none was written".

    Without this the three defences above are an assertion about intent. With
    it they are a measured property of the run, and the run that violates them
    stops instead of publishing a number that a stale cache chose.
    """
    found = bytecode_under(root / "tools")
    if found:
        raise SystemExit(
            f"bytecode present {when}: {found}\n"
            "Every arm runs with PYTHONDONTWRITEBYTECODE=1 and -B, so a "
            "populated __pycache__ means one of them was routed around. Two "
            "arms on one module inside the same second have identical "
            "(mtime, size) — every invert mutation inserts the same six "
            "characters — so the cache would serve the PREVIOUS ARM'S "
            "MUTATION and the sweep would score branches against each other. "
            "This is not recoverable by purging and re-running: the run is "
            "void."
        )


# ---------------------------------------------------------------------------
# The arms.


@dataclass
class Arm:
    form: str
    outcome: str
    exit_code: int | None
    stdout_bytes: int
    seconds: float
    #: The last line of stderr for a raise, so the record says *what* it raised
    #: rather than merely that it did. This is the field that lets a reader
    #: check the raise/verdict split by hand instead of taking the classifier's
    #: word for it — `ratio_arithmetic#007`'s three arms carry the
    #: `invalid literal for int()` that finding 038 §1 quotes. Empty otherwise.
    detail: str = ""


@dataclass
class Result:
    branch: Branch
    arms: list[Arm] = field(default_factory=list)


def classify(exit_code: int | None, stdout: str) -> str:
    """One arm's outcome, on what `selftest.py` printed rather than what it returned.

    Finding 038's repaired `held` reads *"report a failing arm: a non-zero exit
    that carries a verdict"*, and the discriminator is textual because the exit
    code cannot carry it. `selftest.py` prints `N failure(s):` and then names
    each one before returning 1. An uncaught exception exits 1 having printed
    none of that — for `ratio_arithmetic.py:105` the interpreter dies inside
    `main` at `run_checks(BAD)` with **stdout empty**, and that exit 1 is
    indistinguishable from the exit 1 a missing file produces. A crash is not a
    detection: the instrument did not catch the branch's removal, it became
    unable to answer.
    """
    if exit_code is None:
        return TIMEOUT
    if exit_code == 0:
        return GREEN
    return VERDICT if "failure(s):" in stdout else RAISED


def run_selftest(worktree: Path) -> tuple[int | None, str, str, float]:
    started = time.monotonic()
    try:
        done = subprocess.run(
            [sys.executable, "-B", "tools/selftest.py"],
            cwd=worktree, capture_output=True, text=True,
            timeout=CAP_SECONDS, env=child_env(),
        )
    except subprocess.TimeoutExpired:
        return None, "", "", time.monotonic() - started
    return done.returncode, done.stdout, done.stderr, time.monotonic() - started


def sweep_branch(worktree: Path, pristine: str, branch: Branch) -> Result:
    """Run forms in §1's order until the precedence rule can decide.

    Stopping there is safe for *both* classifiers. `first-non-zero` stops at the
    first form that is not a timeout, and `precedence` stops at the first form
    that is neither a timeout nor a raise — so precedence always sees at least
    as many forms as the control, and the arms gathered here are a superset of
    what the control needs. Neither rule ever wants an arm this loop did not run.
    """
    result = Result(branch=branch)
    target = worktree / branch.relpath
    for form, _prefix, _suffix in FORMS:
        target.write_text(neutralise(pristine, branch, form), encoding="utf-8")
        exit_code, stdout, stderr, seconds = run_selftest(worktree)
        outcome = classify(exit_code, stdout)
        detail = ""
        if outcome == RAISED:
            trace = [line for line in stderr.splitlines() if line.strip()]
            detail = trace[-1].strip()[:200] if trace else "(no stderr either)"
        result.arms.append(Arm(form, outcome, exit_code, len(stdout),
                               round(seconds, 3), detail))
        if outcome in (VERDICT, GREEN):
            break
    restore(target, pristine, branch)
    return result


def restore(target: Path, pristine: str, branch: Branch) -> None:
    """Restore, then verify **by presence** rather than by an absent diff.

    An empty `git diff` is the wrong instrument twice over. It reports the tree
    against the index, so it says nothing about whether the bytes this harness
    meant to put back are the bytes that are there; and finding 038 §8 records
    a restoration assertion that passed against a file the harness itself had
    contaminated. So the needle is read back out of the file: the branch's own
    recorded test text must be present at its own recorded span.

    **This check is structurally unable to see the stale-bytecode fault.** Under
    that fault the source is correct here and at every other point in the run —
    only the cache is wrong. `assert_no_bytecode()` is the check that sees it,
    and a reader who takes this one as the harness's integrity guarantee will
    have the same confidently wrong number finding 038's first attempt had.
    """
    target.write_text(pristine, encoding="utf-8")
    read_back = target.read_text(encoding="utf-8")
    needle = _branch_span(read_back.split("\n"), branch)
    if needle != branch.test:
        raise SystemExit(
            f"{branch.ident}: restoration of {branch.relpath} did not put the "
            f"branch back. The span now reads {needle!r} and the population "
            f"recorded {branch.test!r}."
        )
    if read_back != pristine:
        raise SystemExit(
            f"{branch.ident}: {branch.relpath} differs from its `git show "
            f"{REF}:` text outside the branch's own span."
        )


# ---------------------------------------------------------------------------
# The two classifiers, over one set of arms.


def score_precedence(arms: list[Arm]) -> tuple[str, str | None]:
    """§1's rule: inversion first, a forcing form only where the previous raised or hung."""
    for arm in arms:
        if arm.outcome == VERDICT:
            return HELD, arm.form
        if arm.outcome == GREEN:
            return UNHELD, arm.form
    return UNSCORABLE, None


def score_first_non_zero(arms: list[Arm]) -> tuple[str, str | None]:
    """The rejected rule: any non-zero exit is a hold, crash included.

    A timeout is *still* not a non-zero exit here. Keeping that half identical
    is what makes this a one-variable control: the only thing separating the two
    classifiers is what a raise means, so a difference between them cannot be
    charged to the cap.
    """
    for arm in arms:
        if arm.outcome in (VERDICT, RAISED):
            return HELD, arm.form
        if arm.outcome == GREEN:
            return UNHELD, arm.form
    return UNSCORABLE, None


def tally(results: list[Result], scorer) -> tuple[int, int, int]:
    counts = {HELD: 0, UNHELD: 0, UNSCORABLE: 0}
    for result in results:
        counts[scorer(result.arms)[0]] += 1
    return counts[HELD], counts[UNHELD], counts[UNSCORABLE]


# ---------------------------------------------------------------------------
# Reading the tree.


def git(args: list[str], cwd: Path) -> str:
    done = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if done.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} failed: {done.stderr.strip()}")
    return done.stdout


def repo_root() -> Path:
    return Path(git(["rev-parse", "--show-toplevel"], HERE).strip())


def sources_at(ref: str, root: Path) -> dict[str, str]:
    """Every module's pristine text, from `git show` and never from a working tree."""
    return {relpath: git(["show", f"{ref}:{relpath}"], root)
            for _module, relpath in MODULE_PATHS}


def check_population(branches: list[Branch]) -> list[str]:
    per_module: dict[str, int] = {}
    for branch in branches:
        per_module[branch.module] = per_module.get(branch.module, 0) + 1
    problems = []
    for module, expected in EXPECTED_BRANCHES.items():
        got = per_module.get(module, 0)
        if got != expected:
            problems.append(
                f"{module}: derived {got} branches, finding 038 records {expected}"
            )
    total = sum(per_module.values())
    if total != 279:
        problems.append(f"total: derived {total} branches, finding 038 records 279")
    return problems


# ---------------------------------------------------------------------------
# Commands.


def cmd_population(root: Path, ref: str) -> int:
    branches = population(sources_at(ref, root))
    per_module: dict[str, int] = {}
    for branch in branches:
        per_module[branch.module] = per_module.get(branch.module, 0) + 1
    width = max(len(m) for m in per_module)
    print(f"branch population at {ref}, derived by `ast` from `git show`\n")
    for module, _relpath in MODULE_PATHS:
        expected = EXPECTED_BRANCHES[module]
        got = per_module[module]
        mark = "ok" if got == expected else "MISMATCH"
        print(f"  {module:<{width}}  {got:>3}   finding 038: {expected:>3}   {mark}")
    print(f"\n  {'TOTAL':<{width}}  {len(branches):>3}   finding 038: 279")
    problems = check_population(branches)
    for problem in problems:
        print(f"\nDISAGREEMENT: {problem}")
    return 1 if problems else 0


def cmd_self_test(root: Path) -> int:
    """Offline, seconds, no sweep. Proves the parts that can be proved without one.

    Every arm here is a negative control: each asserts that something the sweep
    depends on *fails* when it should, because a harness whose self-test only
    exercises the passing direction is the shape `tools/README.md` opens with.
    """
    failures: list[str] = []

    def check(label: str, ok: bool, detail: str = "") -> None:
        print(f"  {'PASS' if ok else 'FAIL'}  {label}{'' if ok else '  ' + detail}")
        if not ok:
            failures.append(label)

    print("population — derived, not declared")
    branches = population(sources_at(REF, root))
    problems = check_population(branches)
    check(f"{len(branches)} branches over 19 modules at {REF}", not problems,
          "; ".join(problems))
    check("the five branch ids finding 038 names resolve to its lines",
          all(next(b for b in branches if b.ident == ident).line == line
              for ident, line in (("crossrefs#010", 120), ("crossrefs#023", 188),
                                  ("crossrefs#024", 190),
                                  ("definition_counts#005", 166),
                                  ("definition_counts#013", 227))))

    print("\nspan verification — a drifted span must refuse rather than rewrite")
    sources = sources_at(REF, root)
    victim = next(b for b in branches if b.module == "toc")
    drifted = Branch(**{**asdict(victim), "test": victim.test + " "})
    try:
        neutralise(sources[victim.relpath], drifted, "invert")
        check("a span whose recorded text disagrees raises", False,
              "it substituted anyway")
    except AssertionError:
        check("a span whose recorded text disagrees raises", True)

    print("\nneutralisation — each form parses and changes the module by a fixed width")
    for form, prefix, suffix in FORMS:
        mutated = neutralise(sources[victim.relpath], victim, form)
        ast.parse(mutated)
        check(f"{form} parses and inserts {len(prefix) + len(suffix)} characters",
              len(mutated) - len(sources[victim.relpath]) == len(prefix) + len(suffix))
    invert_widths = {
        len(neutralise(sources[b.relpath], b, "invert")) - len(sources[b.relpath])
        for b in branches if b.module == "toc"
    }
    check("every invert mutation of one module has the same length — the "
          f"stale-.pyc hazard, measured rather than asserted: {invert_widths}",
          invert_widths == {6})

    print("\nclassifier — the four outcomes, on what selftest printed")
    check("exit 0 is green", classify(0, "all self-tests passed") == GREEN)
    check("non-zero carrying a verdict is a verdict",
          classify(1, "  FAIL  x\n1 failure(s):\n  - x") == VERDICT)
    check("non-zero printing nothing is a raise", classify(1, "") == RAISED)
    check("the cap firing is a timeout and not a non-zero exit",
          classify(None, "") == TIMEOUT)

    print("\nthe falsifiability control — two rules, one set of arms")
    raised_then_green = [Arm("invert", RAISED, 1, 0, 0.1),
                         Arm("or-true", GREEN, 0, 900, 0.1)]
    check("a branch whose inversion raises and whose forcing form is green "
          "scores unheld by precedence and held by first-non-zero",
          score_precedence(raised_then_green)[0] == UNHELD
          and score_first_non_zero(raised_then_green)[0] == HELD)
    all_raised = [Arm(f, RAISED, 1, 0, 0.1) for f, _p, _s in FORMS]
    check("a branch raising under all three is unscorable by precedence and "
          "held by first-non-zero",
          score_precedence(all_raised)[0] == UNSCORABLE
          and score_first_non_zero(all_raised)[0] == HELD)
    all_timeout = [Arm(f, TIMEOUT, None, 0, 12.0) for f, _p, _s in FORMS]
    check("a branch hanging under all three is unscorable under BOTH rules — "
          "the control differs on raises alone",
          score_precedence(all_timeout)[0] == UNSCORABLE
          and score_first_non_zero(all_timeout)[0] == UNSCORABLE)

    print("\nbytecode — the guard fires on a populated __pycache__")
    with tempfile.TemporaryDirectory() as tmp:
        planted = Path(tmp) / "tools" / "corpuscheck" / "__pycache__"
        planted.mkdir(parents=True)
        (planted / "corpus.cpython-312.pyc").write_bytes(b"\x00")
        try:
            assert_no_bytecode(Path(tmp), "in the self-test's planted tree")
            check("a planted .pyc stops the run", False, "it was not noticed")
        except SystemExit:
            check("a planted .pyc stops the run", True)
    check("PYTHONDONTWRITEBYTECODE is set in the child environment",
          child_env().get("PYTHONDONTWRITEBYTECODE") == "1")
    check("PYTHONPYCACHEPREFIX is cleared, so the ban cannot be routed around",
          "PYTHONPYCACHEPREFIX" not in child_env())

    print()
    if failures:
        print(f"{len(failures)} failure(s):")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("all self-tests passed")
    return 0


def cmd_sweep(root: Path, ref: str, out: Path | None, keep: bool) -> int:
    sources = sources_at(ref, root)
    branches = population(sources)
    problems = check_population(branches)
    if problems:
        for problem in problems:
            print(f"DISAGREEMENT: {problem}", file=sys.stderr)
        return 1

    nonce = secrets.token_hex(16)
    worktree = Path(os.environ.get("TMPDIR", "/tmp")).resolve() / f"f2a-bhs-{nonce}"
    git(["worktree", "add", "--detach", str(worktree), ref], root)
    started = time.monotonic()
    try:
        assert_no_bytecode(worktree, "before the first arm")
        baseline_exit, _out, _err, baseline_seconds = run_selftest(worktree)
        if baseline_exit != 0:
            print(f"the unmutated tree at {ref} does not pass selftest.py "
                  f"(exit {baseline_exit}); every verdict below would be "
                  "scored against a broken baseline", file=sys.stderr)
            return 1
        print(f"clean selftest.py at {ref}: exit 0 in {baseline_seconds:.2f}s; "
              f"per-arm cap {CAP_SECONDS}s\n")

        results: list[Result] = []
        for index, branch in enumerate(branches, 1):
            results.append(sweep_branch(worktree, sources[branch.relpath], branch))
            if index % 25 == 0 or index == len(branches):
                print(f"  {index:>3}/{len(branches)} branches, "
                      f"{sum(len(r.arms) for r in results)} runs, "
                      f"{time.monotonic() - started:.0f}s", flush=True)
        assert_no_bytecode(worktree, "after the last arm")
    finally:
        if not keep:
            git(["worktree", "remove", "--force", str(worktree)], root)

    elapsed = time.monotonic() - started
    runs = sum(len(r.arms) for r in results)
    return report(results, ref, runs, elapsed, baseline_seconds, out)


def report(results: list[Result], ref: str, runs: int, elapsed: float,
           baseline_seconds: float, out: Path | None) -> int:
    problems: list[str] = []

    precedence = tally(results, score_precedence)
    control = tally(results, score_first_non_zero)
    differing = [
        r for r in results
        if score_precedence(r.arms)[0] != score_first_non_zero(r.arms)[0]
    ]
    scored_on_raise = [
        r for r in results
        if score_first_non_zero(r.arms)[1] is not None
        and next(a for a in r.arms if a.outcome in (VERDICT, RAISED, GREEN)).outcome == RAISED
    ]

    print(f"\n{runs} runs, {elapsed:.0f}s, cap {CAP_SECONDS}s, clean baseline "
          f"{baseline_seconds:.2f}s\n")
    print("per module — branches, and unheld under §1's precedence rule\n")
    width = max(len(m) for m, _p in MODULE_PATHS)
    for module, _relpath in MODULE_PATHS:
        mine = [r for r in results if r.branch.module == module]
        unheld = sum(1 for r in mine if score_precedence(r.arms)[0] == UNHELD)
        want_b, want_u = EXPECTED_BRANCHES[module], EXPECTED_UNHELD[module]
        ok = len(mine) == want_b and unheld == want_u
        print(f"  {'ok  ' if ok else 'DIFF'}  {module:<{width}}  "
              f"{len(mine):>3} branches ({want_b:>3})   "
              f"{unheld:>2} unheld ({want_u:>2})")
        if not ok:
            problems.append(
                f"{module}: {len(mine)} branches / {unheld} unheld; "
                f"finding 038 records {want_b} / {want_u}"
            )

    print(f"\n  precedence      {precedence[0]} held, {precedence[1]} unheld, "
          f"{precedence[2]} unscorable   (finding 038: "
          f"{EXPECTED_PRECEDENCE[0]}/{EXPECTED_PRECEDENCE[1]}/{EXPECTED_PRECEDENCE[2]})")
    print(f"  first-non-zero  {control[0]} held, {control[1]} unheld, "
          f"{control[2]} unscorable   (finding 038: "
          f"{EXPECTED_FIRST_NON_ZERO[0]}/{EXPECTED_FIRST_NON_ZERO[1]}/"
          f"{EXPECTED_FIRST_NON_ZERO[2]})")
    print(f"  the two rules differ on {len(differing)} branches "
          f"(finding 038: {EXPECTED_DIFFERING}); "
          f"{len(scored_on_raise)} would be scored on a raising form")

    if tuple(precedence) != EXPECTED_PRECEDENCE:
        problems.append(f"precedence rule returned {precedence}, "
                        f"finding 038 records {EXPECTED_PRECEDENCE}")
    if tuple(control) != EXPECTED_FIRST_NON_ZERO:
        problems.append(f"first-non-zero rule returned {control}, "
                        f"finding 038 records {EXPECTED_FIRST_NON_ZERO}")
    if len(differing) != EXPECTED_DIFFERING:
        problems.append(f"the two rules differ on {len(differing)} branches, "
                        f"finding 038 records {EXPECTED_DIFFERING}")
    if not differing:
        problems.append(
            "the falsifiability control is vacuous: the rejected rule agreed "
            "with the stated one on every branch, so this sweep cannot show "
            "that its classifier is doing any work"
        )

    # Finding 038's headline zero — *"of the 222 branches recorded `held`, none
    # was scored on a form that raised"* — is not measured here, because under
    # the repaired definition it cannot be anything but zero: `score_precedence`
    # returns `held` only from a `VERDICT` arm, and a `RAISED` arm is never one.
    # Asserting it would be a check that passes because it cannot fail, which is
    # the shape this whole document is about. What *is* measurable is the
    # counterfactual the zero is interesting against, and it is reported instead.
    print(f"  the precedence rule cannot score a hold on a raise by "
          f"construction; under the rejected rule {len(scored_on_raise)} "
          "branches would be (finding 038: 36)")
    if len(scored_on_raise) != EXPECTED_RAISE_SCORED:
        problems.append(
            f"the rejected rule would score {len(scored_on_raise)} branches on "
            f"a raising form, finding 038 records {EXPECTED_RAISE_SCORED}"
        )

    if out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(record(results, ref, runs, elapsed,
                                         baseline_seconds), indent=1) + "\n",
                       encoding="utf-8")
        summary = out.parent / "SUMMARY.txt"
        summary.write_text(render_summary(results, ref, runs, elapsed,
                                          baseline_seconds), encoding="utf-8")
        print(f"\nrecord written to {out}\nsummary written to {summary}")

    print()
    if problems:
        print(f"{len(problems)} disagreement(s) with finding 038:")
        for problem in problems:
            print(f"  - {problem}")
        print("\nA disagreement is a result. Do not adjust this harness until "
              "it agrees — report the disagreement, because tuning until the "
              "number matches is how a harness becomes a way of re-deriving "
              "what you already believed.")
        return 1
    print("reproduced finding 038: 222 held / 55 unheld / 2 unscorable over "
          "279 branches, all nineteen per-module counts, and the rejected "
          "rule's 234/44/1 control")
    return 0


def record(results: list[Result], ref: str, runs: int, elapsed: float,
           baseline_seconds: float) -> dict:
    """The per-branch record, including **the form each verdict was taken on**.

    Finding 038 §1 says the form used is recorded per branch. Until this file
    existed, no such record was in the tree — the sweep that knew it was never
    committed. This is that record, and it is what discharges the clause.

    It is dated to one frozen commit and derives nothing from `HEAD`, so it
    cannot go stale: `aaa329b` will always have these 279 branches.
    """
    return {
        "ref": ref,
        "instrument": "tools/selftest.py",
        "cap_seconds": CAP_SECONDS,
        "clean_baseline_seconds": round(baseline_seconds, 3),
        "runs": runs,
        "elapsed_seconds": round(elapsed, 1),
        "forms": [name for name, _p, _s in FORMS],
        "totals": {
            "precedence": dict(zip(
                (HELD, UNHELD, UNSCORABLE), tally(results, score_precedence))),
            "first_non_zero": dict(zip(
                (HELD, UNHELD, UNSCORABLE), tally(results, score_first_non_zero))),
        },
        "branches": [
            {
                **asdict(r.branch),
                "verdict": score_precedence(r.arms)[0],
                "form_used": score_precedence(r.arms)[1],
                "verdict_first_non_zero": score_first_non_zero(r.arms)[0],
                "arms": [asdict(a) for a in r.arms],
            }
            for r in results
        ],
    }


def render_summary(results: list[Result], ref: str, runs: int, elapsed: float,
                   baseline_seconds: float) -> str:
    """The plain-text face of the record — every branch, its verdict, its form.

    Text rather than Markdown on purpose: `specs/*/harness/**` is role `harness`
    in the corpus checker, but a `.md` file there is still a document, and a
    279-row generated table is not something a human should have to keep
    passing `table-integrity` by hand. The JSON beside this is the machine
    face; this is the one a reader greps.
    """
    lines = [
        f"branch-hold sweep — {ref}",
        f"instrument: tools/selftest.py   cap: {CAP_SECONDS}s   "
        f"clean baseline: {baseline_seconds:.2f}s",
        f"{runs} runs in {elapsed:.0f}s over {len(results)} branches",
        "",
        "The `form` column is what finding 038 §1 says is recorded per branch.",
        "`unscorable` carries no form: no form produced a runnable tree.",
        "",
        f"{'branch':<24} {'site':<46} {'verdict':<11} {'form':<10} arms",
        "-" * 118,
    ]
    for result in sorted(results, key=lambda r: (r.branch.relpath, r.branch.line)):
        verdict, form = score_precedence(result.arms)
        site = f"{result.branch.relpath}:{result.branch.line}"
        arms = " ".join(f"{a.form}={a.outcome}" for a in result.arms)
        lines.append(f"{result.branch.ident:<24} {site:<46} {verdict:<11} "
                     f"{form or '-':<10} {arms}")
    precedence = tally(results, score_precedence)
    control = tally(results, score_first_non_zero)
    differing = [r for r in results
                 if score_precedence(r.arms)[0] != score_first_non_zero(r.arms)[0]]
    lines += [
        "-" * 118,
        f"precedence      {precedence[0]} held / {precedence[1]} unheld / "
        f"{precedence[2]} unscorable",
        f"first-non-zero  {control[0]} held / {control[1]} unheld / "
        f"{control[2]} unscorable   (the rejected rule, as a control)",
        f"the two differ on {len(differing)} branches:",
    ]
    for result in differing:
        lines.append(
            f"  {result.branch.ident:<24} "
            f"{result.branch.relpath}:{result.branch.line}  "
            f"{score_precedence(result.arms)[0]} -> "
            f"{score_first_non_zero(result.arms)[0]}"
        )
    return "\n".join(lines) + "\n"


def cmd_score(path: Path) -> int:
    """Re-score a committed record's arms under both rules, with no runs at all."""
    data = json.loads(path.read_text(encoding="utf-8"))
    results = [
        Result(branch=Branch(**{k: v for k, v in entry.items()
                                if k in Branch.__dataclass_fields__}),
               arms=[Arm(**arm) for arm in entry["arms"]])
        for entry in data["branches"]
    ]
    return report(results, data["ref"], data["runs"], data["elapsed_seconds"],
                  data["clean_baseline_seconds"], None)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--ref", default=REF)
    parser.add_argument("--population", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--sweep", action="store_true")
    parser.add_argument("--score", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--keep-worktree", action="store_true")
    args = parser.parse_args(argv)

    if args.score:
        return cmd_score(args.score)
    root = repo_root()
    if args.population:
        return cmd_population(root, args.ref)
    if args.self_test:
        return cmd_self_test(root)
    if args.sweep:
        out = args.out or (RESULTS / f"branches-{args.ref}.json")
        return cmd_sweep(root, args.ref, out, args.keep_worktree)
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
