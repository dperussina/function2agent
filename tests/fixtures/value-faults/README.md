# The injected value-fault corpus, and the control corpus beside it

**Tasks**: T131 owns `corpus.json`. T132 owns `shape-faults.json` and
`tests/batteries/test_conformance_control.py`. **Criteria**: SC-005, SC-006.

| File | Owner | What it holds |
| --- | --- | --- |
| `corpus.json` | T131 | Injected value faults, each paired with the correct result for the same case |
| `shape-faults.json` | T132 | The positive control: correct values wearing wrong shapes |

## Why the two corpora are matched by pairing rather than by two lists

SC-005 asks for a detection rate over injected faults and a false-alarm rate
over *"a matched corpus of correct results"*. Two separate files would have to
be kept the same size and the same shape by hand, and a drift between them
moves both rates without moving either corpus visibly. So each case in
`corpus.json` carries **both** its `correct_value` and its `faulted_value`, and
the matched corpus is produced from the same entries. Matched by construction,
not by agreement.

`correct_value` is committed **and** re-derived from `collections` by the
loader, which compares the two and fails on a disagreement. A committed oracle
nobody recomputes is a number, and this corpus exists to catch numbers nobody
recomputed.

## The stratum is computed, never declared

SC-005 names one stratum explicitly — *faults smaller than one percent of the
correct value* — and requires the refusal share to be broken out for it, because
a corpus whose sub-one-percent faults all fall in quantities the precision
ladder refuses reports a healthy aggregate over a stratum it never tested.

No case declares which stratum it is in. The loader computes
`|faulted − correct| / |correct|` and classifies against SC-005's own boundary.
That is the discipline T124's arms already use: an arm there planted a fault of
one unit and its own guard caught that the same plant on a smaller collection
would have been 2.9% and therefore a statement about a class it does not cover.
A declared stratum would have hidden exactly that.

One consequence is visible in the corpus and is left visible.
`count-lot-count-off-by-one` **cannot** be sub-one-percent: the smallest fault a
count of six can carry is one, which is 16.7%. The stratum a case lands in is a
property of the quantity, not of the injection.

## The two fault classes, and why there are two

The measured corpus this one is modelled on carried faults of two kinds, and a
control scoped to one of them certified nothing about the other. That is
recorded as an open contradiction in
[finding 015](../../../specs/001-discovery-validation/findings/015-verifier-vs-judge-not-run.md)
— E8's predicted-null control asserted that the schema arm detected zero
*numeric* value errors, it passed correctly, and the arm's actual defect was in
the *set-typed* class where a cardinality clause certified the wrong answer as
correct. The recorded resolution is that **every negative control must state the
class it bounds**.

So `corpus.json` carries both classes, and
`test_conformance_control.py::test_the_null_states_the_classes_it_bounds`
refuses a control whose bounded set does not cover every class present:

- `numeric_value_error` — a wrong magnitude in a correctly-typed numeric field.
- `set_cardinality_error` and `set_membership_error` — a collection of the right
  element type drawn from the right vocabulary with the wrong members. The
  second has the **correct** cardinality, so the one clause E8's preregistration
  singled out as having any chance at this class passes it too.

The split measured in feature 001 is **9 numeric and 2 set-typed**, corrected
from an earlier 8-and-3 in
[`E8-VIABILITY.md` §6 and §B1.1](../../../specs/001-discovery-validation/E8-VIABILITY.md)
by two agents recomputing from the frozen corpus. Two modules in `src/analysis/`
still quote the superseded 8; see the note at the head of
`test_conformance_control.py`.

## What the shipped verifier cannot express, recorded rather than smoothed over

`Recomputation` in `src/analysis/derive.py` admits four operators — `count`,
`sum`, `min`, `max`. **None of them projects a collection onto a member list**,
which is what the two set-typed cases need. So the shipped verifier has no
check it can derive for the class that broke E8's arm, and the battery's
reference check performs the projection itself.

This is a real gap and it is asserted rather than described:
`test_the_shipped_recomputation_cannot_express_the_set_typed_class` fails the
day `project` is added to `AGGREGATES`, which forces this paragraph to move
rather than letting it go quietly stale.

## No rate is reported here, and SC-005's two percentages are not this task's

SC-005 **does** pre-register two figures — at least 95% detection and a
false-alarm rate no worse than 1%. Neither is reported here, and that is a
statement about the denominator rather than about the thresholds:

> Both rates are computed over **the faults injected into quantities the
> precision ladder does not refuse**, and **the refusal share MUST be reported
> beside them** rather than folded into either.

The eligible population is therefore whatever the precision ladder admits, and
the ladder is not finished. Its admissible **sources** are closed — FR-024
property 4, `ADMISSIBLE_PRECISION_SOURCES` in `src/runtime/verify.py`, shipped
under T125 — but the **caller-declared rung** is open, carried by T212, and it
decides which quantities refuse. A rate computed now would be a rate over a
population T212 can still move. The refusal share the criterion asks for beside
the rates is T130's report, not this corpus.

What T132 does assert is a **count of zero** with its class stated, which SC-006
specifies outright and which needs no threshold to read. That is the whole of
what this directory scores.

## This file is not gated, and that is measured rather than assumed

`tools/corpuscheck/config.json` walks `README.md`, `research`, `docs`, `specs`,
`tools`, `.cursor/skills` and `.specify/memory`. **`tests` is in none of them**,
so nothing in this directory is read by `tools/check_corpus.py` — a figure
planted here fires nothing, verified on 2026-08-12 by planting one and getting
`0 error(s), 0 warning(s)` from the same text that produces two errors in
`tools/README.md`.

The provenance check would not have read the counts above in any case: its
enabled shapes are four-decimal ratios, money with cents and multipliers, and a
bare integer is none of them.

So the load-bearing claims here are held by **tests and not by prose**. Every
number this directory relies on is either recomputed from `collections` by the
loader or asserted in the battery. The two citations above are addresses a
reader can open, and neither is quoted as a figure this corpus depends on.
