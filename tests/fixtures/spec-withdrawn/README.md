# T157 — withdrawing an admitted target's published specification, and restoring it

**Task**: T157. **Criterion**: **SC-021**.

| File | What it holds |
| --- | --- |
| `corpus.json` | Five scenarios over a withdrawal-and-restoration timeline |
| `../drift_corpora/spec_withdrawn.py` | The loader, and the age recomputation |
| `../../unit/test_drift_fixtures.py` | The asserted expected output |

## ⚠️ Read this before reading a result off this directory

**SC-021 is not the measurement and must not be read as it.**
[`plan.md` line 831](../../../specs/002-spec-aware-agent-runtime/plan.md),
third column, in its own words:

> **SC-021 is not the measurement and must not be read as it.** It scores an
> implementation's conformance to FR-047 against a fixture derived from FR-047 —
> a conformance test, not evidence the disposition is right. Calling it coverage
> would be the substitution this corpus has caught repeatedly. Manufacturing the
> corpus here is worse than absent: any withdrawal schedule we invent would
> encode the transient-versus-permanent ratio the measurement exists to
> discover.

The same row's first column states the gap this fixture does **not** close:

> **FR-047 ships unmeasured — no experiment has ever run the scenario it
> governs.** Feature 001's only drift experiment is **E13**, whose three named
> mutations are *rename a route, change a parameter type, delete an endpoint*:
> all three move the **source**. It has **no arm in which the source is
> unchanged and the deployment stops serving an operation**, and none in which
> an admitted target's **published specification is withdrawn** — which is the
> case FR-047 actually governs. **E13 never ran at all.** So FR-047's
> disposition (serve the last-known-good set marked stale, deny past the
> ceiling), its fifteen-minute ceiling, and its deployment-clock detection
> latency all ship with **zero** supporting evidence.

[`VERDICT.md` line 162](../../../specs/001-discovery-validation/VERDICT.md) says
the same of the capability: drift detection has *"no detection rate, no
false-alarm rate, no latency to detect, **on either of its two clocks**"*. Both
clocks. Zero measurements.

**So**: this directory is the committed artifact FR-053 requires alongside the
capability, and the thing SC-021 will be scored on when T147 through T152 exist.
It is **not** evidence that serving a last-known-good set marked stale is the
right disposition, nor that 900 seconds is the right ceiling. The deciding
quantity — how often a published specification stops being reachable
*transiently* rather than permanently — is a property of real deployments and
real networks, plan.md says it cannot be manufactured here, and the obligation
is deferred to production against real traffic.

**The withdrawal schedule below is invented, deliberately, and encodes no claim
about that ratio.** Two scenarios restore below the ceiling, one never restores.
That is a shape chosen to exercise SC-021's four clauses, not a distribution.

## SC-021's four clauses, and where each one lives

| Clause | Scenario carrying it |
| --- | --- |
| 100% of results while stale carry a machine-readable marking with the set's age | all four withdrawal scenarios; **9** of the **12** calls in the corpus are made while stale |
| zero calls served after the ceiling elapses | `withdraw-past-ceiling` — **2** calls denied |
| zero sessions end in a generic error at the ceiling | `withdraw-past-ceiling`, and **the terminal state it needs does not exist yet** — see below |
| 100% of operations differing between the last-known-good and restored sets reported as drift | `withdraw-restore-changed-below-ceiling` — **3** operations differ |

## The age is wall clock from the last successful fetch

T149's wording, and `_age_at` implements exactly it: `call − last successful
fetch at or before it`, never `call − the moment staleness was entered`. The
difference is the whole of T149 — measuring from entry means lengthening the
re-fetch interval silently widens the ceiling.

The two rules are only distinguishable on a case where they disagree about a
**disposition** rather than about a number, so the corpus contains one: in
`withdraw-past-ceiling` the call at 02:16:00 is 960 s old under T149 and denied,
and 660 s old measured from entry and would be served.
`test_the_corpus_separates_t149s_age_rule_from_the_wrong_one` asserts such a
call exists.

Every declared age, staleness flag and served flag is recomputed and
contradicted on disagreement; `test_a_declared_age_that_disagrees_with_the_wall_clock_is_refused`
plants a wrong one and asserts the refusal.

## The boundary is deliberately absent

**No call in this corpus has an age of exactly 900 s.** Whether the ceiling
denies at `age == ceiling` or only past it is T149's and T150's decision, and a
fixture that answered it would be writing a requirement. The loader refuses an
exactly-at-ceiling call and
`test_no_call_lands_exactly_on_the_ceiling` asserts none appears.

## The terminal state SC-021's third clause needs does not exist

`src/contracts/terminal.py` is a **closed** taxonomy of twelve members, guarded
by `tests/invariants/test_terminal_taxonomy.py`, and **not one of them names the
staleness ceiling**. T150 requires an in-flight session past the ceiling to end
in a named terminal state rather than by generic error; that name is not in the
taxonomy at the time this fixture was committed.

So `withdraw-past-ceiling` declares `expected_terminal_state: null`, asserts only
the negative — the session must not end generically — and the loader refuses any
non-null name that is not already a member, so a later edit cannot smuggle one
in through a fixture.

`test_the_taxonomy_still_has_no_terminal_state_naming_the_staleness_ceiling`
asserts the **absence itself**. The day T150 adds the member that test fails,
deliberately, and this section plus the corpus's `null` have to move. A gap
recorded only in prose goes stale silently; this one cannot.

## All three of FR-044's non-admissible states

T147 enters the stale state on *"the first re-fetch returning any of FR-044's
three non-admissible states"*. A corpus exercising only `absent` leaves two
thirds of that rule unexercised, so the scenarios use `absent`,
`unreadable_by_credential` and `readable_no_operations` — the last being the
state most easily mistaken for a successful fetch, since the document parses and
is simply empty. `test_all_three_of_fr044s_non_admissible_states_are_exercised`
requires all three, and the state names are imported from
`src/analysis/admission.py` rather than spelled here, so a rename there breaks
this rather than leaving a fixture describing states that no longer exist.

## The population, with its denominator attached

`spec_withdrawn.counts()` reports:

- **5** scenarios: **4** in which the specification is withdrawn, **1** in which
  it never is;
- **3** of the 5 reach a restoration, and **2** of those 3 restore an unchanged
  set;
- **12** calls over all 5 scenarios, of which **9** are made while the set is
  stale and **2** of those 9 are denied past the ceiling;
- **3** of FR-044's 3 non-admissible states exercised.

`test_every_total_is_partitioned_by_a_breakdown_that_sums_to_it` asserts the 4
and the 1 add to the 5.

## The two negative controls, and the ablations they defeat

**Rule 8**: all four of SC-021's clauses are *100%* or *zero*, which is exactly
the shape whose tell is a perfect ablation score.

| Control | Clause it protects | Ablation it defeats |
| --- | --- | --- |
| `never-withdrawn` | first | *mark every result stale.* Its stale denominator is zero, so it must produce zero markings |
| `withdraw-restore-identical-below-ceiling` | fourth | *report drift on every restoration.* Zero operations differ, so zero drift is the only correct answer |

Both ablations are executed against the real population by
`test_an_implementation_marking_every_result_stale_fails_this_corpus` and
`test_an_implementation_reporting_drift_on_every_restoration_fails`.

## This file is not gated

`tools/corpuscheck/config.json` does not walk `tests`, so
`tools/check_corpus.py` never reads this file. The counts above are recomputed
by `spec_withdrawn.counts()`; the ages, staleness flags and dispositions are
recomputed by the loader; the taxonomy gap, the absent boundary, the three
states and both ablations are asserted in `tests/unit/test_drift_fixtures.py`.
