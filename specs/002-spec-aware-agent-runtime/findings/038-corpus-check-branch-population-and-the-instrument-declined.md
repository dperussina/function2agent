# Finding 038 — `pytest` is blind to the entire corpus checker: with all eighteen checks stubbed to return nothing, `pytest tests -q` still reports **1745 passed, 83 skipped**, and `tools/selftest.py` is the sole instrument holding any of it. Against that one instrument **55 of 279 (19.7%)** decision branches in the checker are unheld — a branch can be neutralised and the self-test stays green. Three of those unheld branches are live defects with names. The instrument that would gate the rate is **declined**, on the composition of the unheld set rather than on cost

**Date**: 2026-08-11
**Feature**: 002. Measures
[`tools/corpuscheck/checks/`](../../../tools/corpuscheck/checks/) and the four shared modules those
checks call into — [`tools/corpuscheck/attest.py`](../../../tools/corpuscheck/attest.py),
[`tools/corpuscheck/figures.py`](../../../tools/corpuscheck/figures.py),
[`tools/corpuscheck/corpus.py`](../../../tools/corpuscheck/corpus.py) and
[`tools/corpuscheck/search.py`](../../../tools/corpuscheck/search.py) — against
[`tools/selftest.py`](../../../tools/selftest.py).
**Reports, and repairs the three defects in §4.** **No check was changed and no branch was deleted**
— every repair is a self-test or fixture change, because in all three cases the check is right and
the arm claiming to hold it was not. The three landed after the pass holding `tools/selftest.py`
committed at `4118950` and released the file; until then they were recorded unfixed, and §4 keeps
both states. The measurement itself repairs nothing: the rate in §2 stands as taken.
**User Story**: none directly. Prompted by a census of the checker's decision branches, which was
commissioned to find out whether the ad hoc practice of fixturing a branch when somebody remembers
to had produced coverage or the appearance of it.
**Owner decision**: **none is minted here and no register was edited.** §5 declines building the
instrument; that declination is a measurement result rather than an owner ruling, and §5 says which
part of it an owner would have to take if the verdict were reopened.
**Model spend**: **$0.0000.** No model was called and no credential was read. Static `ast` reads of
Python, plus repeated runs of `tools/selftest.py` and one run of `pytest tests -q`.
**Method**: **each branch was neutralised and the self-test re-run**, which is the same arm
[`tools/threshold_probe.py`](../../../tools/threshold_probe.py) applies to constants. The branch
population was derived by `ast` rather than declared, the neutralisation was located by source span
and verified against the recorded text before the edit, and the pristine baseline was taken from
`git show HEAD:<path>` rather than from the working tree — §6 records why that last detail is the
finding's own near-miss and not a detail.
**Reproduction**: every command is given in full in the section that uses it. The measured tree is
`aaa329b`; the sweep runs against a clean checkout of it and takes about 100 seconds.
**Numbering note**: `037` was the high-water mark across `specs/*/findings/`, established two ways
and **no "next free number" written in any other document was consulted or trusted** — two such
reservations in this corpus have rotted. (1) The numeric prefix of every file matching
`specs/*/findings/*.md`: max `037`, over 37 numbered documents in two directories. (2) A corpus-wide
boundary-anchored citation search of the `finding NNN` form with **match-only output taken before
sorting**, because ripgrep's default output carries the path and a version sort then orders by path
so the last line is not the maximum: max `037`. `038` was free at that moment and re-checked free
immediately before saving.

---

> ## THE RESULT IN ONE PARAGRAPH
>
> The corpus checker has **no test coverage in `pytest` at all**. Every one of its eighteen checks
> was replaced with a body that returns nothing, and `pytest tests -q` reported **1745 passed, 83
> skipped** — exit 0, not one assertion moved. `tools/selftest.py` under the same mutation exits 1.
> So the whole of what holds the checker honest is one instrument, and the question worth asking is
> how much that instrument actually holds. Of the **203** decision branches in
> `tools/corpuscheck/checks/`, **170 held, 32 were unheld and 1 was unscorable** — unheld meaning the
> branch was neutralised and `tools/selftest.py` stayed green, so nothing in the repository would
> notice its removal. Extending the population to the four shared modules the checks call into adds
> **76** branches and takes the total to **279 (203 + 76)**, of which **55 of 279 (19.7%)** are
> unheld. `figures.py` is the worst single module at **10 of 20 (50.0%)**. Three unheld branches are
> live defects rather than merely unfixtured, and each is a self-test that passes for the wrong
> reason; **all three are repaired here**, and each repair is probed by neutralising the branch it
> now claims to hold rather than asserted. **The instrument that would gate this rate is declined** —
> not because the sweep is slow,
> though it is, but because 25 of the 32 unheld branches in `checks/` are one fixture each, which is
> the existing practice working unevenly rather than an instrument's output, and a gate would need a
> baseline of 55 accepted exceptions on its first day.

> ## WHAT THIS FINDING DOES NOT CLAIM
>
> It does **not** claim the checker is broken. `check_corpus.py` reads 0 errors and 0 warnings over
> 138 documents at `aaa329b`, and every check that fires, fires correctly as far as this measurement
> reaches. It does **not** claim `pytest` should have covered the checker — the split of labour that
> puts the corpus checks behind `selftest.py` is deliberate and recorded; what is new here is the
> *measurement* of how much that leaves resting on one instrument. It does **not** claim an unheld
> branch is a defect: §3 is entirely about the cases where it is not, and that distinction is the
> most transferable thing here. It does **not** claim "held" means correct — §7 states the asymmetry
> that makes only one half of this number usable. And it takes **no** owner decision.

> ## THE INSTRUMENT SITS BESIDE EVERY FIGURE HERE, AND ONE MODULE'S FIGURES HAVE MOVED
>
> **Every branch figure in this document was scored against `tools/selftest.py` alone.** The title's
> clause that it is *"the sole instrument holding any of it"* is a reading over `checks/` and it does
> not survive for one shared module: §2.2.1 records `figures.py` re-scored on 2026-08-11 against the
> whole gate set, where `check_corpus.py` holds four of the ten branches `selftest` left unheld, and
> at `92143b9` a unit test holds all twenty. The title stands as written because a heading cannot
> carry a strikethrough without corrupting its anchor; this box is the correction.
>
> **No corpus-wide figure moves for it, and none is restated here.** 55, 32, 279 and every rate
> derived from them are `selftest` readings taken over `aaa329b` and they stay exactly as taken.
> **Only `figures.py` was re-scored.** Advancing the corpus-wide rates to an instrument nobody ran
> them against would publish a measurement that was never taken, which is the defect §8 records this
> document's own harness committing one level up and the defect §2.1's box declines for the
> nineteenth check. §2.2.1 names the modules that were not re-derived, so a reader can tell which
> one moved from which ones nobody looked at again.

---

## 1. What was measured, and how a branch was neutralised

A **decision branch** is the test expression of an `if` or `elif`, a `while`, a conditional
expression, a comprehension guard, or an `assert`. The population was derived by walking the module
with `ast` and recording, for each test, its exact source span — module, kind, line, column, end
line, end column, and the source text of the test itself. Nothing was declared by hand.

**Deriving the population rather than declaring it is the load-bearing choice**, and it is the one
place this measurement's method differs from `threshold_probe.py`'s. A declared table of branches
goes stale the moment somebody adds an `if`, and it goes stale silently, in exactly the direction
that reports coverage the tree does not have. The `ast` walk cannot.

Neutralisation was attempted in three forms, in this order, and the form used is recorded per branch:

| form | what replaces the test | what it establishes |
|---|---|---|
| `invert` | the test wrapped so its truth value is reversed | the strongest arm: both directions of the branch matter |
| `or True` | the test forced true | the branch's false arm is never taken |
| `and False` | the test forced false | the branch's true arm is never taken |

Inversion was preferred because it is the only one of the three that fails when *either* direction
of a branch is unheld. The forcing forms were used only where inversion crashed the check outright
or hung it, which is a property of the branch rather than of the method — a loop guard inverted
becomes an infinite loop, and a `None` guard inverted dereferences the `None`.

The verdict for each branch is one of three, and the third is not a rounding of the other two:

- ~~**held** — the neutralised tree makes `tools/selftest.py` exit non-zero. Removing the branch
  would be caught.~~ **Superseded 2026-08-11 — the box below repairs this definition, and repairs
  nothing else.**
- **held** — the neutralised tree makes `tools/selftest.py` **report a failing arm**: a non-zero exit
  that carries a verdict. Removing the branch would be caught. An uncaught exception is a non-zero
  exit and is not a hold, because it reports nothing.
- **unheld** — the neutralised tree leaves `tools/selftest.py` exit 0. Nothing in the repository
  would notice.
- **unscorable** — no neutralisation form produced a runnable tree. All three either raised or hung,
  so the branch has no verdict rather than a green one. **A form that raises lands here and not in
  `held`**, which is the precedence the box below supplies.

> ### The `held` definition overlapped `unscorable` on the raised case, and the repair is to the definition
>
> **Corrected 2026-08-11.** `held`'s test as written above was an exit code, and `unscorable`'s was
> whether any form produced a runnable tree. **A raise satisfies both**, because an uncaught
> exception exits non-zero, and nothing above said which verdict wins. A reader applying the two
> definitions mechanically therefore scores a *crashing* branch **held** — a false positive in the
> coverage direction, which is the opposite of the direction §7 establishes this document's numbers
> are safe in. The silence was not quite symmetric, and that is worth naming rather than
> overstating: `unscorable`'s *"produced a runnable tree"* leans the right way, since a tree that
> raises is not a runnable one. But `held`'s clause never mentioned runnability, so the lean was
> available only to a reader who went looking for it.
>
> **The measurement, taken here rather than reasoned from the definitions.** The branch is
> `ratio_arithmetic.py:105`, the `order == "count-first"` test that decides which regex group is the
> count and which is the rate. Under all three of §1's forms it raises
> `ValueError: invalid literal for int() with base 10` out of `_num`, because the swapped groups
> hand a rate to the integer parser — and `tools/selftest.py` exits **1** under every one of them.
> **No form hangs**, so §1's *"either raised or hung"* resolves to *raised* here, three times.
> Measured 2026-08-11 at `19aadbf`, over a `ratio_arithmetic.py` byte-identical to `aaa329b`'s, so
> it is the same branch this document scored. The nine branches were re-derived by `ast` from
> `git show HEAD:<path>` and every span was verified against its recorded text before substitution,
> which is §1's method unchanged.
>
> **A raise does not score `held`, and what settles it is what `selftest.py` printed rather than what
> it returned.** Under the inverted form its standard output is **empty** — not one `PASS` line, no
> arm named, no site — and the interpreter dies inside `main` at `run_checks(BAD)` before any arm is
> evaluated. That exit 1 is the interpreter's, and it is indistinguishable from the exit 1 a missing
> file or a malformed mutation produces, so it carries no information about the branch at all. Set
> that beside the genuine hold §2.3 records for `corpus.py:161`, where `tools/selftest.py` and
> `check_corpus.py` both exit 1 **with a verdict at a named site**. The old definition's second
> sentence — *"Removing the branch would be caught"* — is the clause a raise fails, so its two
> halves disagreed with each other and the repair makes the operational half say what the gloss
> already meant. **A crash is not a detection**: the instrument did not catch the branch's removal,
> it became unable to answer.
>
> ~~**This repairs the definition and no verdict, and no branch's verdict was re-derived under it.**
> The repaired test differs from the old one only where a neutralisation raises, and a raise is what
> put a branch in the unscorable class rather than in `held` — so every branch this document records
> as held was scored on a run that reported a verdict, and every figure in §2 stands exactly as
> taken.~~ **Superseded 2026-08-11 — the argument was right and is no longer the grounds.** All 279
> verdicts have since been re-derived under the repaired definition and not one moved: **of the 222
> branches recorded `held`, none was scored on a form that raised**. The reasoning struck above was
> sound, but it argued from the form precedence §1 states rather than from a run, and the box after
> §1's method notes replaces it with the run. Re-stating 279 verdicts against a repaired definition
> without re-running them would publish a measurement never taken, which is the defect §8 records
> this document's own harness committing one level up — **which is why the sweep was re-run rather
> than the digits restated**. What the repair changes for a *later* sweep, and the count in §5, are
> unaffected either way.

**The edit was verified against the recorded text before it was made.** Each span carries the source
of its own test, and the neutralisation asserted the bytes at the span matched that text before
substituting. A span that has drifted by a line rewrites the wrong expression and scores a branch
that was never touched, which would produce a number in the confident direction.

Between edits `__pycache__` was purged, because a stale `.pyc` makes a mutated module run as its
unmutated self and every branch then scores held.

> ### The re-sweep the repaired definition implied: all 279 re-derived, and none of the 222 held on a raise
>
> **Run 2026-08-11.** The box above repaired the `held` test from an exit code to a reported verdict
> and then argued, from §1's form precedence, that no recorded verdict could move under it. This is
> that argument run instead of made. It was worth running rather than accepting, because the
> precedence is a property of how the sweep chose a form and **the sweep is not in this repository** —
> it was never committed, so §1's prose is the only surviving record of it, and prose is not a
> classifier.
>
> **The number, which is the point of the exercise.** Of the **222** branches recorded `held`, **none
> was scored on a form that raised**. It is zero, and it is recorded as a reading rather than left as
> a corollary of the paragraph above.
>
> **The tree and the instrument.** A clean detached worktree at **`aaa329b`**, the commit the 279
> verdicts are over — deliberately *not* `HEAD`, because §9's caveat has since come true: `HEAD`
> carries a nineteenth check module and four grown ones, so its population is a different one and
> sweeping it would answer a different question. The population was re-derived by `ast` from
> `git show aaa329b:<path>`, never from a working tree, and it reproduces §2.1's and §2.2's branch
> counts **exactly, in all nineteen modules** — which is what establishes that this is the same
> population and not merely a similar one. The instrument is `tools/selftest.py` alone, the same one
> §2.1 and §2.2 were taken with, so nothing here adds an instrument and §2.2.1's separation of the
> one re-scored module from the rest is untouched.
>
> **It reproduces the record, and that is what makes the zero informative rather than circular.**
> Scoring every branch by §1's stated precedence — inversion first, a forcing form only where the
> previous one raised or hung — returns **222 held, 55 unheld, 2 unscorable**, with no per-module
> disagreement anywhere in the nineteen. **The test could have failed.** Scoring the same arms by the
> rule the repair rejected, under which the first non-zero exit wins, returns **234 held, 44 unheld,
> 1 unscorable**: **36** branches would be scored on a raising form, and **12** of them would change
> verdict — eleven from `unheld` to `held`, and `ratio_arithmetic.py:105` from `unscorable` to
> `held`. The two rules are nowhere near observationally equivalent on this population, so a sweep
> that had taken the first non-zero exit could not have produced §2.3's figures. The reproduction is
> therefore evidence about the classifier that produced them.
>
> **A hang is scored as itself.** Two branches have a hanging arm — `corpus.py:161` under all three
> forms and `corpus.py:159` under two — and each is recorded `timeout`, never folded into a non-zero
> exit. Every arm was capped at **12 seconds** against a clean `selftest.py` measured at **0.95
> seconds** in the same worktree.
>
> **Cost, because §5's estimate is the one a later pass will reach for.** **338** `selftest.py` runs
> and **145 seconds**, and a second full sweep returned identical verdicts for all 279 branches.
> §5's *"about 100 seconds"* is the right order and slightly low: most branches cost one run, the
> fallback forms add 59, and the three hanging arms spend 36 seconds on the cap. This is minutes. The
> figure sometimes quoted against a 279-branch re-score — several hours — is the **gate-set** cost of
> §2.2.1's every-instrument sweep and does not describe a `selftest.py`-only re-sweep.
>
> **`__pycache__` is a sharper hazard than the note above states, and this run measured it.** The
> note is right that a stale `.pyc` scores branches held, but the mechanism deserves recording,
> because the first attempt at this re-sweep hit it and returned **235 held, 43 unheld, 1
> unscorable** — a wrong answer in the confident direction that would have moved every figure in §2.
> Python validates a cached `.pyc` against the source's *(mtime truncated to whole seconds, size)*,
> and **every `invert` mutation of a module has the same length as every other**, so two arms on one
> module inside the same second are indistinguishable to that validator. The stale state is then the
> **previous arm's mutation** rather than the unmutated module: measured directly, `ratio_arithmetic`
> `#007` ran `#006`'s bytecode and reported a verdict at a branch that raises. Purging between edits
> is necessary and not sufficient, since the purge races the arms; the arms must also be forbidden to
> write bytecode at all. **What caught it was the reproduction check** — the contaminated run failed
> to match §2.1's and §2.2's per-module counts. Nothing in the tree would have caught it, and the
> restoration check could not: the source file is correct at every point, and only the cache is
> stale.

### 1.1 The prior question, and how the blindness was established

**The branch census only means something once you know which instrument is doing the holding**, so
that was measured first, by a coarser mutation than any single branch. Every one of the eighteen
`check(ctx)` entry points under `tools/corpuscheck/checks/` had its body replaced with a bare
`return` — no violations, no skips, no reads — and the two instruments were run against the result.
`pytest tests -q` reported **1745 passed, 83 skipped** and exited 0. `tools/selftest.py` exited 1.

**That asymmetry is the reason this document exists**, and it is stronger evidence than a coverage
percentage would have been: coverage measures which lines execute under the suite, and eighteen
functions that execute and then return nothing would still have read as covered. Stubbing the return
value asks the question coverage cannot — whether anything downstream *depends* on what the check
found — and the answer across 1745 tests is no.

**The `1745` is a dated reading of a moving number and the argument does not rest on it.** The same
command at `39a67a2` reports **1752 passed, 83 skipped**, seven higher, because a concurrent pass
added `tests/unit/test_preserved_evidence_scope.py` and it was committed at `4118950` between the
measurement and this document. What the figure is doing here is establishing that a large suite moves
by *zero* under the mutation, so the total's exact value is incidental and its stability under
stubbing is the finding. A reader re-running against a later tree should expect a different total and
the same delta of nothing.

## 2. The rate, both populations, and the split

**Every figure in this section is scored against `tools/selftest.py`, and the instrument is part of
the result rather than context for it.** A branch is unheld *with respect to an instrument*: the same
branch scores held the moment anything else notices its removal, and nothing about the phrase "the
unheld rate" says which instrument was watching. That is the same defect §2.3 records for the
denominator, one level up — a figure quoted without its instrument is unresolvable, and §2.2.1 is the
case that establishes it, where one module re-scored against more instruments halved its own rate
with no line of the module changed.

### 2.1 The eighteen checks

The eighteen checks live in fifteen files under `tools/corpuscheck/checks/`, and the branch counts
are per file:

> **A nineteenth check landed after this census and is not in its population.** `count-versus-range`
> was registered on 2026-08-11, after the sweep ran at `aaa329b`. It was never neutralised and never
> scored, so every branch figure in this section, in §2.3 and in §7 is a **dated reading over the
> eighteen checks that existed when the sweep ran**, and it stays exactly true of those eighteen.
> **No figure here is advanced to cover it.** Advancing a count or a rate to include a branch nobody
> probed would publish a measurement that was never taken, which is a worse defect than a stale
> denominator and is the one this repository keeps catching; the stale denominator is visible to a
> reader who checks, and the fabricated figure is not.
>
> **It would be probeable by the same method**, which is the part a reader deciding whether the rate
> transfers needs. The method wants two things and the nineteenth has both: its module carries
> decision branches of the kinds §1 defines, so an `ast` walk derives a population from it exactly as
> it did for the other fifteen files, and `tools/selftest.py` already exercises the check — it pins
> rows against `specs/001-fixture/plan.md` in the known-bad corpus — so a neutralised branch has an
> instrument that can notice. The nineteenth is **like** the eighteen rather than unlike them, and a
> later sweep extends the population without changing the method. What that sweep would report about
> it is unmeasured here.

| module | branches | unheld |
|---|---|---|
| `catalog.py` | 13 | 0 |
| `crossrefs.py` | 28 | 6 |
| `definition_counts.py` | 17 | 5 |
| `dry_run_verdict.py` | 13 | 3 |
| `findings_numbering.py` | 7 | 0 |
| `identifiers.py` | 16 | 3 |
| `inventory.py` | 13 | 3 |
| `lifecycle_taxonomy.py` | 25 | 0 |
| `numeric_provenance.py` | 23 | 8 |
| `preserved_evidence.py` | 4 | 0 |
| `ratio_arithmetic.py` | 9 | 0 (1 unscorable) |
| `register_ranges.py` | 10 | 2 |
| `sum_arithmetic.py` | 1 | 0 |
| `tables.py` | 13 | 1 |
| `toc.py` | 11 | 1 |
| **TOTAL** | **203** | **32** |

**170 held, 32 unheld, 1 unscorable**, so the unheld rate over `checks/` **against
`tools/selftest.py`** is **32 of 203 (15.8%)**. No other instrument was run against this population.
**Every verdict in this table was taken under the superseded `held` definition and re-derived
unchanged under the repaired one** on 2026-08-11 — §1's second box records that re-sweep, and states
which definition each figure here rests on.

**Five checks hold every branch they have**: `catalog-line-count`, `lifecycle-taxonomy`,
`findings-numbering`, `preserved-evidence` and `sum-arithmetic`. That is worth stating beside the
rate because it is evidence about the *practice* rather than about the checker: where somebody sat
down and fixtured a check per failure kind, the branches are held, and the unevenness in the rest is
what the aggregate is measuring.

`numeric_provenance.py` carries the largest absolute share at 8 of the 32, and it is also the check
with the most kinds and exemptions, so the two are unsurprising together.

### 2.2 The four shared modules

The checks are not the whole of the checker. Extending the population to the four modules the checks
call into adds **76 (12 + 20 + 37 + 7)** branches:

Every verdict in the table is `tools/selftest.py`'s, and `figures.py`'s row is the one row a later
pass re-scored against more instruments — see §2.2.1, which leaves this row standing and adds the
other readings beside it rather than replacing it. As in §2.1, every verdict here was **taken under
the superseded `held` definition and re-derived unchanged under the repaired one**, per §1's second
box.

| module | branches | held | unheld | unscorable | instrument |
|---|---|---|---|---|---|
| `attest.py` | 12 | 10 | 2 | 0 | `selftest` |
| `figures.py` | 20 | 10 | 10 | 0 | `selftest`; re-scored in §2.2.1 |
| `corpus.py` | 37 | 27 | 9 | 1 | `selftest` |
| `search.py` | 7 | 5 | 2 | 0 | `selftest` |
| **TOTAL** | **76** | **52** | **23** | **1** | `selftest` |

~~**`figures.py` is the worst module in either population at 10 of 20 (50.0%)**, and its position
explains why that matters more than its size: it is the arithmetic and figure-shape library that
`numeric-provenance`, `ratio-arithmetic` and `sum-arithmetic` all read through, so a silently
removable branch there is a silently removable branch in three checks at once.~~

**Superseded 2026-08-11 in one clause, and the clause was wrong rather than stale.**
`tools/corpuscheck/checks/ratio_arithmetic.py` contains **no reference to `figures` of any kind** —
not an import, not a mention — so it never read through this module, and a silently removable branch
here was never a silently removable branch in it. The rate above is untouched by the correction.

**`figures.py` is the worst module in either population against `tools/selftest.py` at 10 of 20
(50.0%)**, and its position explains why that matters more than its size: it is the arithmetic and
figure-shape library the checks import for struck and inline spans, multiplier parsing and sum
arithmetic, so a silently removable branch there is a silently removable branch in every check that
imports it at once.

**The importers are named by the search that finds them rather than counted here**, because a count
is the half a later import falsifies while the search keeps answering — and a stated count that a
future import moves is the class of claim this corpus keeps repairing:

    git grep -nE '^from \.\.figures import' -- tools/corpuscheck/checks/

**Widening that search past `checks/` is where the reach turns out to be larger than the struck
sentence claimed, and it is what §2.2.1 needs:**

    git grep -nE 'from \.*(corpuscheck\.)?figures import' -- tools/

The second form finds everything the first one does and adds `tools/gen_claims.py`, which imports
`inside_spans` and `struck_spans` for its own use. So this module sits under a second gate as well as
under `check_corpus.py`, and it is read by a `pytest` unit test besides — which is the mechanism
§2.2.1 measures rather than a detail about imports.

### 2.2.1 The same twenty branches, re-scored against the gate set

**Re-scored 2026-08-11, and both readings are right because they answer different questions.** The
module did not change: `tools/corpuscheck/figures.py` is byte-identical at `aaa329b` and at
`92143b9`, and an `ast` walk derives the same twenty branches from either. Every difference below is
a property of the instrument.

| instrument | tree | unheld of 20 |
|---|---|---|
| `tools/selftest.py` alone | `aaa329b` | 10 — §2.2's row, reproduced branch for branch |
| the gate set as it stood when the re-scoring ran | `aaa329b` | 6 |
| `tools/selftest.py` alone | `92143b9` | 7 |
| the gate set | `92143b9` | 0 |

**Four of the ten are held by `check_corpus.py`, and they are named rather than counted** because a
count is the thing a reader cannot check:

| branch | site | what it decides |
|---|---|---|
| the `percent_decimal` dispatch | `figures.py:258` | whether percentage figures are extracted at all |
| `table_cells`'s pipe early-out | `figures.py:298` | whether a line is treated as a table row |
| `rate_columns`'s header test | `figures.py:322` | which header cells declare a per-unit denominator |
| `column_of`'s containment test | `figures.py:329` | which column a figure's offset falls in |

**The last three are the rate-column mechanism, and their hold rests on prose.** `check_corpus.py`
notices their removal because documents in the corpus carry rate-bearing table columns for it to
read; edit those sentences away and the hold goes with them. A hold that depends on what a document
happens to say is a hold, and it is a different kind of hold from a fixture's.

**The two rows at `92143b9` are why this subsection states a tree beside every instrument.** Three
more branches — the whole of `digit_neighbours`, at `figures.py:438`, `:441` and `:445` — became
`selftest`-held when two `numeric-provenance` rows reading the near-neighbour clause landed, which is
the difference between the first row and the third. And `tests/unit/test_figures_library.py` landed in
the same commit and holds all twenty, which is the difference between the second row and the fourth.
**So the gate-set reading of 6 of 20 (30.0%) is a dated reading of a gate set that no longer exists**,
and quoting it as current would assert a rate the tree has already closed.

**The other modules are un-re-derived, and that is the honest state rather than an oversight.**
`attest.py`, `corpus.py`, `search.py` and all fifteen files under `checks/` carry `selftest`-scored
figures and nothing else. **No gate-set reading exists for any of them**, none is inferred here from
`figures.py`'s, and a reader must be able to tell the one module that was re-scored from the ones
nobody looked at again — which is what this paragraph exists to make possible. What a gate-set
re-scoring would report about them is unmeasured, and §7 says which direction it would have to move.

### 2.3 The combined figure, and the denominator that has to be stated

Combining the two populations gives **279 (203 + 76)** branches: **222 held, 55 unheld, 2
unscorable**. **All three were taken against `tools/selftest.py` under the superseded `held`
definition, and all three were re-derived unchanged under the repaired one** on 2026-08-11; §1's
second box records the re-sweep and reports that none of the 222 was scored on a raising form.

> **The two unscorable branches are a property of the three forms tried, not of the branches, and
> one of them has since been scored.** `corpus.py:161` is the inner backtick-run scanner's
> `while` test. All three of §1's forms hang on it, and none of the three hangs *in that loop*: the
> enclosing loop advances its index only by the inner loop's result, so a form that stops the inner
> loop making progress stalls the outer one. A fourth form — the termination bound kept as the left
> conjunct and the right conjunct forced true — terminates, and under it `tools/selftest.py` and
> `check_corpus.py` both exit 1, so the branch is **held**. Measured 2026-08-11 at `92143b9`, over a
> `corpus.py` byte-identical to `aaa329b`'s, so it is the same branch this document scored.
> ~~The other unscorable branch was not re-examined and no claim is made about it.~~
> **Superseded 2026-08-11: the other unscorable branch is `ratio_arithmetic.py:105` and §1's box
> examines it.** It raises under all three forms and stays unscorable under the repaired `held`,
> so it is the one branch in this population that still carries no verdict.
> **Neither figure below is advanced for this**, because the sweep that produced them tried three
> forms and these are its numbers; what changes is what "unscorable" may be read as meaning, and
> `tools/README.md` carries the generalisation.

**The rate is 55 of 279 (19.7%).** Stated with the other denominator a reader might reasonably use,
excluding the two unscorable branches because they carry no verdict either way, it is
**55 of 277 (19.9%)**. Both are written out here because the two figures differ by a rounding step
and a sentence quoting one of them without its operands is unresolvable — the difference is whether
the two unscorable branches sit in the denominator, and nothing about the phrase "the unheld rate"
says which. **Both rates carry the same definition as their operands**: taken under the superseded
`held` definition and re-derived unchanged under the repaired one, against `tools/selftest.py`. A
rate is only as dated as the verdicts under it, and §1's box repaired a definition after these were
first written down, so which definition they rest on is stated here rather than inferred.

### 2.4 The three-way split of the 32

The 32 unheld branches in `checks/` divide **32 (3 + 25 + 4)**:

| class | count | what it means |
|---|---|---|
| unreachable | 3 | the branch cannot be reached as the code stands, so no fixture could hold it. §3 |
| unfixtured | 25 | the branch is reachable and no fixture reaches it. One fixture each would hold it |
| mis-targeted | 4 | a self-test arm names the branch and does not exercise it. §4 |

**The composition is the whole of the argument in §5**, so it is stated before the verdict rather
than after it. 25 of 32 being one fixture each is not an instrument's output; it is the existing
practice having been applied unevenly, and the repair for each is a line in a fixture.

## 3. Unreachable-as-written is not defective-as-written, and collapsing them is a real error

The brief that commissioned this census carried the rule that an unreachable branch is a defect, on
the strength of a case where it was one: a scope key routed `preserved-evidence` to `skipped` when
the evidence it protects was deleted, so the branch that should have reported the loss was
unreachable *and* the check announced itself disabled while a real failure went unreported. **That
rule does not survive this population, and the two poles are worth naming because the distinction
generalises past this checker.**

All three unreachable branches here are **inert memoisation**:

| branch | site | the guard |
|---|---|---|
| `crossrefs#010` | `crossrefs.py:120` | `d.relpath not in anchor_cache` |
| `definition_counts#005` | `definition_counts.py:166` | `window_struck is None` |
| `definition_counts#013` | `definition_counts.py:227` | `target.relpath not in cache` |

Each is a compute-once cache whose cold and warm paths **call one definition and return one value**.
They are unreachable in a full run only because check ordering is fixed and something earlier has
already warmed the cache. Running the owning check in isolation against a cold cache produces
byte-identical violations either way. There is no state of the corpus in which taking the cold path
and taking the warm path disagree, so there is nothing a fixture could assert and nothing a reader
of the output could ever have been misled by.

**The two poles, stated so the next census does not have to rediscover them:**

- **Defective-as-written** — the scope-key case. The branch is unreachable *and* its unreachability
  changes what the tool reports. A real failure produced a green or a skip. Reachability was the
  mechanism of the defect.
- **Unreachable-as-written** — the memoisation case. The branch is unreachable and both paths agree
  by construction. Nothing the tool reports depends on which is taken.

The test that separates them is not "can this line execute" but **"does any input exist for which
the two paths disagree about the output"**. The commissioning rule collapsed them by testing the
first question and reporting the second, and 3 of the 32 unheld branches in this population would
have been filed as defects on that reading. They are not defects, and the sweep's own numbers were
what showed it.

## 4. Three live defects, each a self-test change

These are the 3 of the 4 mis-targeted branches that resolve to a named defect. Each is a change to
`tools/selftest.py` or its fixtures rather than to a check — in all three cases the check is right
and the arm that claims to hold it does not.

~~**All three are recorded unfixed.** `tools/selftest.py` carried another pass's uncommitted edits
throughout this pass, at every reading from 09:06 onward, and editing around a live pass in a file
whose whole content is a table of assertions is how a row gets absorbed and lost.~~ **Repaired
2026-08-11, after the holding pass committed at `4118950` and released the file.** All three are
fixed and each fix is probed rather than asserted, which is the discipline whose absence produced
two of the three. Each subsection below carries the reproduction and the probe.

**The probe is a differential over one variable.** The same four neutralisations were run against a
clean checkout of `4118950` without the fixes and against the same checkout with only the fixes
applied. Before: all four leave `tools/selftest.py` at exit 0. After: all four take it to exit 1.
The neutralisation was located by `ast`, verified against the recorded text of the branch before the
edit, run with `__pycache__` purged, and the file restored from a byte copy and confirmed present.

| branch | neutralisation | before the fix | after the fix |
|---|---|---|---|
| `inventory.py:199` | invert `sites == 0` | exit 0 — unheld | exit 1 — held |
| `crossrefs.py:188` | branch never entered | exit 0 — unheld | exit 1 — held |
| `crossrefs.py:190` | never violates | exit 0 — unheld | exit 1 — held |
| `toc.py:53` | invert the TOC test | exit 0 — unheld | exit 1 — held |

### 4.1 `inventory.py:199` — a vacuity arm that passes as long as *any* rule announces

The branch is `if sites == 0:`, the arm that fires `inventory-count`'s per-rule skip with the
message that zero findings mean *"nothing read", not "nothing wrong"*. The self-test's floor arm for
it deletes the only live `findings` claim and then looks for a `findings` needle in whatever the
check emits.

**Every rule's vacuity message ends in the same boilerplate about zero findings**, so the needle is
satisfied by any rule's skip line. Under neutralisation the `research-documents` rule announces,
`research-documents`'s message contains the needle, and the arm goes green having never touched the
rule it names. The arm asserts that *something* announced, which was not the claim.

Reproduction: neutralise `inventory.py:199` and run `tools/selftest.py`. The two `inventory floor`
lines that appear when the check is stubbed entirely — one about the deleted `findings` claim
producing no skip, one about the surviving `research-documents` claim — are the arm's two halves,
and only the second is doing work under this branch's neutralisation.

**Repaired**: the needle became `rule findings matched no live claim`, which is the prefix
`inventory.py` writes for this rule and no other, in place of the bare word `findings`. The probe is
the defect displayed: under the inverted branch the arm now fails, and the skip list it prints as
evidence contains `rule research-documents matched no live claim in README.md, research/README.md
(glob research/[0-9]*.md counts 2): its zero findings mean 'nothing read', not 'nothing wrong'` —
a message that satisfies both of the old needles and neither of the new one. The wrong rule
answering is now visible in the failure text rather than invisible in a pass.

### 4.2 `crossrefs.py:188` and `:190` — a branch dead under its own fixture, and a comment that says otherwise

The numeric link-label branch is `if nm and path_part.endswith(".md"):` at line 188 and
`if not base.startswith(nm.group(1) + "-"):` at line 190. Both are unheld — `crossrefs#023` and
`crossrefs#024` — and **`crossrefs#024` is never evaluated at all** under the self-test's corpus.

The reason is a regex boundary. The branch is entered only when the link's label matches
`_NUMERIC_TEXT`, whose pattern anchors both ends around an optionally-backticked two-digit run and
therefore requires the label be **exactly two digits**.
The fixture row the self-test points at is `README.md:127` in the known-bad corpus, whose label is
the backticked filename `` `research/01-fixture-metrics.md` ``. That label is matched by
`_FILENAME_IN_TEXT` and can never be matched by `_NUMERIC_TEXT`, so control reaches the filename
branch below and the numeric branch above it is skipped.

**The comment above that row claims the row holds something it does not.** At
`tools/selftest.py:110-114` it reads that the row *"is what makes resolving the target before
comparing a change that can be checked"*, and the 2026-08-10 repair it records is real — the
filename branch genuinely was held only in the direction that passes, and this row genuinely fixed
that. What the row does not do is hold the numeric branch, and the two branches sit eleven lines
apart in the same function under one comment. **A repair asserted rather than probed is what left
this here**, which is the same shape as the other two defects in this section.

The branch is reachable and the fixture was one line from correct: a link written
`[01](research/14-fixture-synthesis.md)` has a two-digit label and a target whose basename does not
begin `01-`, so it enters at 188 and violates at 190.

Reproduction of the defect: delete both branches outright and run `tools/selftest.py`. Every row
stayed green, including `README.md:127`.

**Repaired**: that link was added to the known-bad `README.md` and a row
`("link-label", "README.md", 133, "a filename beginning 01-")` was added beside the existing one.
**The misleading comment was corrected rather than left to be re-read**: it now says which branch the
`README.md:127` row holds and states that it does not hold the numeric branch eleven lines above it
in the same function, which is the sentence that had to become true. Under either branch neutralised
the new row fails with `expected link-label at README.md:133 matching 'a filename beginning 01-',
not found`, and the `README.md:127` row is unaffected — the two rows now hold two branches instead of
one row appearing to hold both.

### 4.3 `toc.py:53` — a TOC-locating branch that inverts with no effect

The branch is `if m and m.group(2).strip().lower().rstrip(":") in _TOC_TITLES:`, the scan that finds
where a document's table of contents starts. Inverting it — taking the first *non*-TOC heading
instead — produces **the same violation at the same line with the same needle**, so the arm cannot
tell the two apart.

The mechanism is that the fixture's TOC sits under the document's first H1. Inverted, `toc_start`
becomes that H1 at line 1; the sweep for the TOC's extent then runs to the next heading of the same
or higher level and no other H1 stops it; so the sweep collects the same two entries it collected
before, and the coverage comparison below reaches the same verdict.

Reproduction of the defect: invert `toc.py:53` and run `tools/selftest.py`. It stayed green.

**Repaired, and not by the route that first suggested itself.** ~~The repair is a fixture whose
document has a heading before its TOC that the inverted scan would seize on, so the two starting
points select different entry sets.~~ A heading before the TOC changes nothing, because the inverted
scan takes the *first* non-TOC heading and that is the H1 at line 1 whatever sits after it. What
separates the two starting points is the **extent sweep**: located correctly it stops at the H2 below
the contents list, and inverted it runs to the next heading of level 1 or higher, finds no second H1,
and therefore collects every self-link in the document. So a self-link placed *below* the contents
list is invisible to the correct scan and swallowed by the inverted one. One was appended to
`14-fixture-synthesis.md` pointing at the section the `toc-coverage` row flags, and under inversion
the check now produces nothing at all: the self-test fails with both `check toc-coverage produced
nothing on known-bad` and the missing line 44 row.

**It was appended at end of file on purpose.** An insertion beside line 44 moved every line below it
and broke two `table-integrity` rows pinned at line 55 and two generated line-count claims; appending
moved only the document's own length, which is one number in three places. Those places were two
`GEN_EXPECTED` rows and the `catalog-line-count` drift row, and the fixture's own catalog claim moved
from 56 to 64 so that the planted drift stays `+1` — the width that shipped past `TOLERANCE = 2`, and
the whole reason that row exists. **Fixing a self-test by editing a fixture costs a line-number
audit**, and that cost is the argument for appending rather than inserting.

## 5. The verdict: the instrument is declined, on composition

**The rate is reported and the sweep is not built.** The reasoning is the composition of the unheld
set rather than the cost of running it, and the costs are recorded second because they are real but
they are not what decides it.

**The composition.** 25 of the 32 unheld branches in `checks/` are one fixture each. That is not a
gap an instrument closes; it is the practice this repository already has, applied unevenly, and the
repair for each is a line in a fixture that somebody writes once. An instrument whose output is
"write 25 fixtures" tells the tree something a single dated measurement — this document — tells it
equally well, and only once.

**The baseline problem, which is the sharper half.** A gate over this population needs a baseline of
accepted exceptions from its first day, and that baseline is **55** entries. A list of 55 accepted
exceptions, maintained by hand, whose entries nothing reconciles against the reasons they were
accepted, is precisely the folklore list that
[`tools/instruments.py`](../../../tools/instruments.py) exists to prevent — and this repository has
already recorded, in [finding 036](./036-the-instrument-absent-from-the-list-of-instruments.md),
what happens when a list and the set it describes come apart with nothing whose job is to notice.
Building this gate would open a second one.

**The other costs, stated for completeness:**

- **Three-valued results.** The verdict is held / unheld / unscorable, and a gate needs a bit.
  ~~The two unscorable branches have no verdict rather than a passing one, so the gate would have to
  either accept them as exceptions — growing the list — or report a green over a branch it could not
  score, which is the failure mode findings 032 and 034 already record.~~
  **Corrected 2026-08-11 — one unscorable branch, not two, and the argument survives at one.** §2.3
  records `corpus.py:161` scored **held** under a fourth form, so the only branch left carrying no
  verdict is `ratio_arithmetic.py:105`. A gate still faces the identical choice over it — accept it
  as an exception, growing the list, or report a green over a branch it could not score, which is
  the failure mode findings 032 and 034 already record — and that choice does not divide by the
  count: one unscorable branch needs the same machinery two did, and a population derived by `ast`
  can grow the class back at any commit. **The correction sharpens this cost rather than softening
  it.** §1's box measures a third option the struck bullet did not name: a gate reading exit codes
  mechanically scores this branch **held** and publishes a green *by crash*, which is worse than a
  green over a branch it could not score, and this is the one branch in the population that
  demonstrates it. **§2.3's figures are not advanced for any of this** — 222, 55 and 2 are the
  three-form sweep's numbers over `aaa329b` and they stay as taken.
- **Runtime.** A full sweep runs about 100 seconds against `threshold_probe.py`'s measured 5.2
  seconds, because each of 279 branches costs a `selftest.py` run. `threshold_probe.py` was wired
  into CI *because* it was measured at five seconds; a twenty-fold instrument does not inherit that
  argument.

**What an owner would have to decide if this were reopened**, stated because §5 declines rather than
settles: whether 55 accepted exceptions at day one is tolerable in exchange for the population never
going stale again. This document's answer is no on the strength of the 25, and that answer weakens
as the 25 get fixtured.

## 6. If it is ever built, it is a sibling of `threshold_probe.py` and not a mode of it

Recorded because the natural move is the wrong one. The harness is worth reusing and the shape is
not.

**Reuse the harness.** `threshold_probe.py` already carries the pieces this sweep needed and
rebuilt: the `__pycache__` purge between edits, the edit-restore loop with restoration verified
rather than assumed, and the `MUST_BREAK` / `MAY_HOLD` vocabulary for saying what an arm is entitled
to conclude. All three transfer unchanged.

**Do not reuse the declared table.** `threshold_probe.py` names its constants in a table, which is
correct for constants because a constant is added deliberately and rarely. A branch population
declared the same way goes stale the moment somebody adds an `if`, and it goes stale in the
direction that reports coverage the tree does not have. **A branch population must be derived by
`ast` or it is not a population.** That is the one thing this census would hand forward.

**A sibling, not a `--branches` flag**, because the two differ in exactly the way that matters for a
gate: the constant population is declared and small and the sweep is five seconds, and the branch
population is derived and large and the sweep is a hundred. Wiring the second behind a flag on the
first puts a hundred-second arm one argument away from a five-second gate.

## 7. The asymmetry that makes the number usable, and the half that is not

**"Unheld" is a floor and can be read as one.** A branch scored unheld was neutralised and the
self-test stayed green. If `tools/selftest.py` were weaker than it is, more branches would score
unheld and none would score fewer. So **55 of 279 (19.7%)** is a lower bound on what is removable
without detection, and it is a lower bound in the safe direction: the true figure is this or worse,
never better.

**§2.2.1 is that floor behaving as a floor, and it is the strongest confirmation this document has
of its own asymmetry.** The argument above says an instrument weaker than the one scored against
moves the unheld count up and never down. Its contrapositive is that *adding* instruments moves the
count down and never up, and that is the direction `figures.py` moved in every one of the readings
§2.2.1 records: 10 against `selftest`, 6 once `check_corpus.py` was counted, 0 once a unit test
existed. **Nothing in §2.2 needed correcting for that to happen**, which is the point — the
re-scoring did not find the census wrong, it found the census's own qualifier doing its job. So a
reader who re-scores any figure in §2 against more instruments should expect it to fall, and a fall
is this claim holding rather than failing. The direction is the claim; the magnitude is not, and only
`figures.py` has been measured.

**"Held" is not robust and must not be read as coverage.** A branch scored held is held by whatever
`tools/selftest.py` happens to assert, and the self-test asserting *something* that changed is not
the self-test asserting the right thing changed. §4 is the evidence: **three of the four
mis-targeted branches are arms that pass for the wrong reason**, and every one of them would have
scored held on a naive reading of exit codes. They were found by reading what the arm asserts
against what the branch does, which no sweep automates.

The consequence for quoting this finding: the unheld rate is usable as a floor, and the held count
is not usable as a coverage claim. `170 of 203` branches in `checks/` survive neutralisation
detection; that sentence is true and it is not the sentence "83.7% of the checker is covered".

### 7.1 A comparison no fixture can hold, whatever the corpus says

**Measured 2026-08-11 at `19aadbf`, and recorded here because it existed nowhere in this corpus.** An
earlier pass settled this question by planting and left the result in a transcript. The plant is cheap,
so it was re-run for this subsection rather than transcribed from that record.

§2.2.1 names `rate_columns`'s header test and `column_of`'s containment test among the four branches
`check_corpus.py` holds, and says their hold rests on prose. **This is the sharper version of that
observation**: for one comparison, no prose can hold them at all.

`numeric-provenance`'s rate-column exemption is a single membership test, in
`numeric_provenance.py`'s `run`:

    column_of(masked, fig.col) in rates.get(i, ())

**Both operands are ordinals out of `enumerate(table_cells(...))`, and that is the structural half.**
`rate_columns` enumerates `table_cells(header)`; `column_of` enumerates `table_cells(line)`. The two
calls are on different lines — a header and a body row — so they are the same enumerator applied
twice rather than one shared call, and what matters is that the ordinals on both sides of `in` are
produced by that one function. **In `tools/` it has exactly two readers, and they are those two
functions**, which this search says and a count would not:

    git grep -n 'table_cells' -- tools/ tests/

Nothing else under `tools/` carries an independent opinion about which column is which. The only
reader outside it is `tests/unit/test_figures_library.py`.

**The plant, with its uniformity verified on both sides rather than assumed.** A sentinel cell was
prepended to `table_cells`'s return value, after both of its pipe-stripping steps so that neither
removes it again. For a header declaring `cost / call`, `rate_columns` moved from `[1]` to `[2]`; for
the body row beneath it, `column_of` moved from `1` to `2`; and the membership test answered true
before the shift and after it. Every ordinal on both sides moved by one, so the comparison cancels
the shift and reaches the same verdict.

**Of the twenty-five instruments, twenty-four are blind and one fires.** The population is the
nineteen checks `check_corpus.py --list-checks` registers, all of which run inside `check_corpus.py`,
plus the six other gate commands — and it is not `instruments.py --check`'s own `19 gate, 6 advisory`
split, which counts a different thing and agrees by coincidence. Under the plant `check_corpus.py`
read 0 errors and 0 warnings, `gen_claims.py --check` read 0 stale, `check_tampers.py` read 344
proofs and 0 errors, `tools/selftest.py` passed, `instruments.py --check` reported the census OK, and
`threshold_probe.py` reported all 34 perturbations behaving as declared. **`pytest` fired: four
failures, every one of them in `tests/unit/test_figures_library.py`**, and every one an exact-offset
assertion.

**This is a check-design gap and not a coverage gap, and that distinction is the transferable part.**
Every other member of this document's unheld family is a branch nobody fixtured, and one fixture each
would hold it — that is the whole of §5's composition argument. This one differs in kind: because
both operands come from the one enumeration, **no corpus content can ever produce a firing**, so it
is outside the reach of the repair §5 declines to build an instrument for. `table-integrity` is the
check a reader would expect to catch a spurious cell, and it cannot see this one at all — it counts
cells through `corpus.split_row` and never calls `table_cells`, so the sentinel never reaches it.
That is a stronger blindness than a shift it saw and cancelled.

**Catching it needs an absolute reference, and the corpus supplies none.** Three exist: a hard-coded
expected ordinal, which is exactly what those four unit tests are and why they were the only
instrument that fired; an independent second implementation to diff the ordinals against; or an
anchor on the header cell's **text** rather than on its position. **No check was built here and no
rule was widened.** This subsection records the measured negative and stops there.

## 8. The harness had the defect it was hunting, one level up

This is recorded rather than smoothed over, because it is the emptiness-test inversion the checker's
own documentation is about, reproduced inside the instrument measuring the checker.

**The first version of the sweep took its pristine baseline by reading the working tree.** For each
branch it read the file, edited the span, ran the self-test, and wrote the file back from the text it
had read at the start. That baseline **cannot distinguish a clean file from one that was already
contaminated before the baseline was taken**. A file mutated by an earlier arm and not restored
becomes the pristine text for every arm after it, and the restore assertion passes — because the
harness restores to exactly what it read, which is the contaminated state.

It happened. The sweep left `tools/corpuscheck/corpus.py` mutated while its own restoration
assertion passed, and every subsequent shared-module verdict was scored against a checker with a
live mutation in it.

**Re-anchored to `git show HEAD:<path>`**, which is a baseline no earlier arm can reach:

- The **shared-module numbers moved materially.** Seven of the 76 shared branches are named in the
  sweep's own casualty record — `attest#000` and six in `corpus.py` — and the shared population's
  verdicts are reported here from the re-anchored run only.
- The **203-branch sweep over `checks/` reproduced exactly, branch for branch.** The pre-anchor and
  post-anchor result sets have the same 203 keys and **zero verdict differences**; one entry differs
  only in which neutralisation form was recorded, not in its verdict. That is why §2.1's numbers are
  stated with the same confidence as §2.2's despite the harness defect sitting between them.

The reproduction is the whole point: the two runs agreeing on 203 branches and disagreeing on 7 of
76 is what establishes that the contamination was confined to the second population, and neither run
alone could have established it. **A restoration verified against what the harness itself read is
not verified.** The general form is that a baseline must come from outside the process that can
corrupt it, which is the same rule the attestation machinery in `attest.py` applies to evidence and
the same rule `check_tampers.py` applies to its own vacuity floor.

## 9. Two caveats on the population, both of which will date this document

**The population is `aaa329b`'s and `preserved_evidence.py` has already grown.** At the measured
commit that module carries **4** branches and all 4 are held. During this pass another pass was
actively reworking it — adding a sixth reported kind and a declared scope marker — so the module's
branch count at the next commit is larger than 4 and this document's 203 is a figure over
`aaa329b` rather than a standing property. **That is the argument for `ast` derivation restated as a
fact about this very document**: the number in §2.1 was already going stale while §2.1 was being
written, and only a derived population tracks that.

**The 25 unfixtured branches are the part most likely to move.** Each is one fixture from held, and
this document names the class rather than the 25 lines, so a later reader who finds the rate lower
should not read the difference as this measurement having been wrong.
