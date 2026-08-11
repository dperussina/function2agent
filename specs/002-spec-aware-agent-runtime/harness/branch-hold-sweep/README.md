# `branch-hold-sweep` — the instrument behind finding 038's headline figures

**What it measures.** Every decision branch in the corpus checker, neutralised one at a
time, with [`tools/selftest.py`](../../../../tools/selftest.py) re-run against each
neutralised tree. A branch is **held** when the self-test reports a failing arm, **unheld**
when it stays green, and **unscorable** when no neutralisation form produced a runnable
tree. Over the 279 branches at `aaa329b` that is **222 held, 55 unheld, 2 unscorable**.

**Why it exists.**
[Finding 038](../../findings/038-corpus-check-branch-population-and-the-instrument-declined.md)
reported those figures, and **the sweep that produced them was never committed**. Its
worktrees were removed, so the implementation is gone; `55 of 279 (19.7%)`, the nineteen
per-module counts and everything derived from them rested on an instrument that did not
exist in the tree, and every re-sweep was a fresh reimplementation from prose. Finding 038
§1's second box names the problem in its own words:

> the precedence is a property of how the sweep chose a form and **the sweep is not in this
> repository** — it was never committed, so §1's prose is the only surviving record of it,
> and prose is not a classifier.

This is the classifier.

## Posture

| | |
|---|---|
| Network | **none.** No socket is opened. |
| Privilege | **none.** Any euid; no root, no container, no kernel facility. |
| Writes | a detached worktree under `$TMPDIR`, removed on the way out, and `results/` when `--sweep` is asked for an output path. **Never into the shared tree's `tools/`.** |
| Model spend | **$0.0000.** No model is called and no credential is read. |
| Runtime | ~145 seconds for `--sweep`; milliseconds for `--self-test`, `--population` and `--score`. |

**It is not a gate and must not become one.** Finding 038 §6 already settled the shape
argument — a hundred-second arm does not belong one flag away from a five-second one — and
§5 declines the gate itself on the composition of the unheld set rather than on cost. This
runs on demand. It is absent from
[`tools/instruments.py`](../../../../tools/instruments.py)'s census for the same reason
every other harness under `specs/*/harness/` is: that census's third direction enumerates
`tools/*.py` plus two named entry points, and a spec harness is not one of them.

## Running it

```bash
cd "$(git rev-parse --show-toplevel)"
H=specs/002-spec-aware-agent-runtime/harness/branch-hold-sweep/branch_hold_sweep.py

python3 $H --self-test     # offline, ~2s, no sweep and no worktree
python3 $H --population    # derive the 279 by `ast` and check the nineteen counts
python3 $H --sweep         # the whole thing, ~145s, writes results/
python3 $H --score results/branches-aaa329b.json   # re-score the record, no runs
```

`--sweep` and `--score` **exit non-zero unless they reproduce finding 038**: the triple, all
nineteen per-module branch counts, all nineteen per-module unheld counts, the rejected
rule's control triple, and the twelve branches the two rules disagree on. Every expected
figure is transcribed into the source beside the check that reads it.

**A disagreement is a result.** If this stops reproducing, the thing to do is report the
disagreement, not adjust the harness until it agrees — the acceptance figures were produced
by a *different* implementation, so a divergence is evidence about one of the two and
quietly tuning until the number matches is how a harness becomes a way of re-deriving what
you already believed.

## What committing this next to its own output does and does not establish

Read this before quoting the pair.

At the commit that introduces both, the agreement between `results/` and finding 038 is a
real cross-check: **two independently written classifiers, one of them reconstructed from
prose alone, reaching the same 279 verdicts.** The figures being reproduced came from an
implementation that no longer exists, so nothing here was fitted to them.

**After that commit it is a regression guard and nothing more.** Re-running `--sweep` and
getting the committed record back proves this file still does what it did on 2026-08-11. It
proves nothing whatever about finding 038, and it cannot: both sides of that comparison are
now this harness.

A harness committed together with its own output and later quoted as though the output
corroborated the harness is self-certification, which is the objection the
archive-as-exhibit ruling turned on. The distinction above is the only thing keeping this
pair on the right side of it, and it is written here rather than in a commit message
because the commit message is not where the next reader will be standing.

## The falsifiability control is an output, not a sentence

Reproducing 222/55/2 would mean little if any rule reproduced it. So every arm's outcome is
recorded and then scored **twice**, by two classifiers over one set of runs:

| rule | what it does with a raise | result |
|---|---|---|
| `precedence` — finding 038 §1's stated rule | falls through to the next form | **222 / 55 / 2** |
| `first-non-zero` — the rule §1's `held` repair **rejected** | scores it `held` | **234 / 44 / 1** |

They differ on **12** branches — eleven `unheld`→`held`, plus `ratio_arithmetic.py:105`
`unscorable`→`held` — and **36** branches would be scored on a raising form under the
rejected rule. `--sweep` fails if the two rules *agree*, because two rules agreeing on this
population would mean the sweep had lost the ability to tell them apart.

**The control differs on raises alone.** A timeout is not a non-zero exit under either rule,
so a difference between them cannot be charged to the cap. That is what makes it a
one-variable control rather than two rules that happen to disagree.

The twelve are listed by name in [`results/SUMMARY.txt`](./results/SUMMARY.txt); a count
would be the half a reader cannot check.

## Bytecode is forbidden, not purged

Finding 038's method note says `__pycache__` was purged between edits. **Purging is not
enough, and the reason is timing rather than thoroughness.**

CPython validates a cached `.pyc` against the source's *(mtime truncated to whole seconds,
size)*. Every `invert` mutation inserts `not (` and `)` — **exactly six characters, the same
six for every branch in the module** — so all of a module's inverted variants have identical
size, and two arms on one module inside the same second are indistinguishable to that
validator. The stale state is then **the previous arm's mutation**, not the unmutated
module. Finding 038 measured this directly: `ratio_arithmetic#007` ran `#006`'s bytecode and
reported a verdict at a branch that raises, and the contaminated run returned a confidently
wrong **235 / 43 / 1**.

A purge *races the arms* — the purge and the next interpreter's write are not ordered with
respect to each other. Forbidding the write is not a race. Four mechanisms, all applied:

- `PYTHONDONTWRITEBYTECODE=1` in the child environment
- `-B` on the child's command line
- `PYTHONPYCACHEPREFIX` cleared, so neither can be routed around to another directory
- `assert_no_bytecode()` before the first arm and after the last

The fourth is the one that matters, and it is why the first three are a measured property of
the run rather than a statement of intent. A populated `__pycache__` **voids the run** rather
than triggering a purge and a retry: once two arms may have shared a cache, no arm's verdict
is known good.

**The source-restoration check cannot see this fault**, and a reader who takes restoration
as the integrity guarantee will get the same wrong number. Under the stale-cache fault the
source is correct at every single point in the run — only the cache is wrong. Restoration
has no opinion about bytecode at all. What caught it in finding 038 was the per-module
reproduction check failing, which is a downstream symptom of unknown reach;
`assert_no_bytecode()` is the upstream one.

## A timeout is its own outcome

Every arm is capped at **12 seconds**, the same cap finding 038's sweep used, kept identical
so the arms stay comparable rather than re-derived against whatever hardware this runs on. A
cap that fires is recorded `timeout` and is **never folded into a non-zero exit**. Conflating
the two is the fabrication `f3f1c89` separated out: it turns *the instrument could not
answer* into *the instrument objected*.

`corpus.py:161` is the branch that makes this concrete. It hangs under all three forms — and
it hangs in its **enclosing** loop, not in the one whose test was neutralised, because the
outer loop advances its index only by the inner loop's result. `corpus.py:159` hangs under
two forms and is scored on the third.

## Restoration is verified by presence

After every arm the file is restored from its `git show aaa329b:<path>` text and then **read
back**, and the branch's own recorded test text must be present at its own recorded span.

An empty `git diff` would be the wrong instrument twice over: it compares the tree against
the index rather than against what this harness meant to write, and finding 038 §8 records a
restoration assertion that passed against a file the harness itself had contaminated —
because the harness restored to exactly what it had read, and what it had read was already
mutated. Pristine text here comes from `git show` and nothing else, which is a baseline no
arm can reach.

The span is also verified **before** each substitution: a span that has drifted by a line
rewrites a different expression and scores a branch nobody touched, which produces a number
in the confident direction. A disagreeing span refuses rather than substituting.

## What it cannot reproduce

- **It says nothing about `HEAD`.** The population is well-defined at `aaa329b` and nowhere
  else. Between `aaa329b` and `HEAD` the checker gained a nineteenth check module
  (`count_vs_range.py`) and four others grew, so `HEAD`'s population is a *different*
  population and sweeping it answers a different question. Finding 038 §9 predicted this and
  it has come true. `--ref` accepts another commit and the acceptance figures will then
  disagree, correctly.
- **It cannot tell you whether a held branch is held for the right reason.** Finding 038 §7
  is the standing statement of this asymmetry: `unheld` is a floor and `held` is not
  coverage. Three of the four mis-targeted branches in §4 were arms passing for the wrong
  reason, and every one of them scores `held` here. Finding them needed a human reading what
  the arm asserts against what the branch does, which no sweep automates.
- **It scores against one instrument.** `tools/selftest.py` alone, which is what finding
  038's figures were taken with. It is not the gate set, and §2.2.1 records `figures.py`
  moving from 10 unheld to 6 to 0 as instruments were added.
- **It does not re-derive finding 038's prose**, only its numbers. §3's
  unreachable-versus-defective distinction and §4's three defects are readings, not outputs.

## Provenance

**Built 2026-08-11, reconstructed from finding 038's prose** — §1's three forms and their
precedence, §1's `ast` definition of a decision branch, the repaired `held` test, the 12-second
cap, and §8's `git show` baseline rule. No code from the original sweep survived to copy.

The reconstruction reproduced finding 038 **on its first full run**, with nothing tuned
between deriving the population and reading the verdicts:

| reading | runs | wall | clean baseline | result |
|---|---|---|---|---|
| first sweep, 2026-08-11 | 338 | 144s | 0.38s | 222 / 55 / 2 |
| second sweep, 2026-08-11 | 338 | 146s | 0.27s | 222 / 55 / 2 |

Both returned the same triple, the same nineteen per-module branch counts, the same nineteen
per-module unheld counts, the same `234 / 44 / 1` control and the same twelve differing
branches. Taken on `Darwin 25.2.0 arm64` (macOS 26.2), CPython **3.12.11**, euid **501**,
from a detached worktree at `aaa329b`.

**Three independent corroborations that this is the same population the original sweep
walked**, none of which was aimed at:

1. The `ast` walk returns **279** branches and reproduces all nineteen per-module counts
   exactly.
2. Five branch identifiers finding 038 names resolve to the lines it gives them —
   `crossrefs#010`→`:120`, `crossrefs#023`→`:188`, `crossrefs#024`→`:190`,
   `definition_counts#005`→`:166`, `definition_counts#013`→`:227` — so the enumeration order
   and the naming scheme match, not merely the totals.
3. `ratio_arithmetic#007` is `ratio_arithmetic.py:105`, which is both the branch §1's box
   measures raising under all three forms **and** the identifier §1's `__pycache__` paragraph
   names as having run `#006`'s bytecode.

**The run count matches too.** Finding 038 records **338** `selftest.py` runs; this returns
338. Its **145 seconds** and these 144–146 are the same reading on different hardware.

**Finding 038 §5's *"A full sweep runs about 100 seconds"* stands and is not restated.** It
is a dated estimate written before the sweep was re-run, and §1's second box already records
145s beside it. These readings are recorded here as a third, not merged into either.
