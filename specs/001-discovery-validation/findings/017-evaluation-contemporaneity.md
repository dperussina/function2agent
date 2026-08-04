# Finding 017 — Three evaluations were scored against artifacts that postdate the defect they were detecting; a survey of where else it may have happened

**Date**: 2026-08-03
**User Story**: methodological — this finding measures no system behaviour. It measures how this
corpus's own instruments were validated, and it is filed here because it changes how several
figures already in `findings/` should be read.
**Model spend**: **$0.0000.** No model was called at any point. Every number below is produced by
`git`, by re-running committed tools, or by a read-only script over committed artifacts.
**Method**: re-execution of `tools/cite_advisor.py` at pinned revisions; re-execution of
`tools/check_corpus.py` against both the working tree and the tree as `git archive cee7ff8`
materialises it; re-execution of `tools/threshold_probe.py`; and a read-only recount of the
disclosure-token distances the `dry-run-verdict` bound is justified by. Where a claim was inherited
from `tools/README.md` it was re-derived rather than quoted, and the two disagreements are reported
below rather than reconciled.

Numbering note: `016` was the last finding issued and `017` was free, checked against
`findings/` before this file was created. No prior artifact claims the identifier.

---

## The headline

**Three times, an evaluation in this corpus was scored against an artifact state that postdates the
defect the evaluation was meant to detect.** Each was caught by accident, in the course of doing
something else. The third was caught only because someone re-ran the tool with one extra flag.

| # | Instrument | The contaminated score | Caught by | Cost |
|---|---|---|---|---|
| 1 | A verifier arm hand-written with the failure cases in view | detection **1.000 by construction** | pre-registration review | none — caught before spend |
| 2 | A trace corpus frozen by file hash | every downstream figure, joined to questions that had since been edited | three unrelated arrivals inside one hour | the whole of E8 |
| 3 | The citation advisory | **2 of 2** known defects found, at ranks 1 and 3 of 57 | re-running it with the requirement text pinned back | one of the two positives |

**The transferable rule, and the half of it that is easy to miss.** An evaluation set drawn from
defects that have since been fixed is contaminated by default, and must be reconstructed from
version control before use. The half that actually bit here is that **reconstruction has to cover
every side of the comparison, not only the artifact carrying the defect** — instance 3 *did* check
the defective contracts out of git, and read the requirements they were scored against from the
working tree. A half-reconstruction is indistinguishable from a whole one at the point of use: it
produces a real number, from real historical text, with a revision quoted beside it.

The rule and its decision procedure are recorded as Rule 6 of
[`experiment-design`](../../../.cursor/skills/experiment-design/SKILL.md), which is where someone
about to build or score an instrument will encounter it. This document is the evidence and the
survey.

## Instance 3, re-verified

`tools/cite_advisor.py` ranks every requirement in `spec.md` against each contract's subject and
lists the high scorers the contract does not cite. Two historical instances of the defect it exists
to catch were used as its evaluation set.

Both pre-fix contract states were correctly reconstructed from `cee7ff8`. Scored against the
requirement text **as it also stood at `cee7ff8`** — the only state in which either defect was ever
live:

| Contract | Governing requirement | Rank against the requirement set at `cee7ff8` | Rank against the current requirement set |
|---|---|---|---|
| `artifact-versioning.md` | FR-055 | **1 of 55** | 1 of 57 |
| `trace-record.md` | FR-038 | **10 of 55** | 3 of 57 |

**FR-055's bullet is byte-identical at both revisions** — SHA-1 over the parsed body agrees — so its
rank of 1 is clean and the tool genuinely found that defect. **FR-038's is not.** As the tool's own
parser reads it, the bullet grows from 51 words at `cee7ff8` to 1379 at `HEAD`, and the production
specification states in as many words that its v1 subject *"was already the unit in the downstream
contract rather than invented here"* — that is, the requirement was rewritten using the subject
matter of the contract now being scored against it. A term-overlap metric then measures the import.
The third-of-57 figure is the repair, not the detection.

**The tool finds one of the two known defects, not two**, and its usefulness rests on a single
unleaked positive. That was already the conclusion in `tools/README.md`; this finding confirms it
independently and records two things that did not check out.

### Two things that did not check out

- **The reproduction was not documented.** `tools/README.md` listed `--contracts-at REV` and not
  `--spec-at REV`. Given `--contracts-at` alone the tool moves the requirements to that revision
  too, which is the correct default and is why the clean figures reproduce — but the comparison
  that *exposes* the leak needs both flags, and the file did not say so. **A file reporting a leak
  should say how to see it.** Corrected.
- **The word counts do not reproduce.** The file gave the rewrite as growing from 53 words to 1374.
  Five tokenisations were tried — whitespace split over the masked bullet, the same over the raw
  bullet, the same with the identifier prefix removed, and two regular-expression word patterns —
  and none yields either figure. Whitespace split over the bullet as the tool's own parser reads it
  gives 51 and 1379. Corrected to those, with the definition stated, because a word count with no
  stated tokenisation is not a checkable number. **The material claim is unaffected**: the
  requirement grew by more than an order of magnitude under every definition tried.

## Instances 1 and 2, and the link between them

**Instance 1 was the cheapest, and it was caught by reading a design rather than a result.** The
pre-registration for the verifier-versus-judge experiment initially had a verifier arm that would
have been the hand-written ground truth itself. Marginal detection would then have been
algebraically identical to the judge's fail-open rate under a different name — an identity, not an
estimate, and one that would have cleared the gate. The fix was to require the arms be derived from
contracts by a mechanical procedure applied to **every** case, including the ones the procedure must
refuse, on the stated grounds that *deriving only where success was expected would have selected the
numerator*. That is this finding's rule, applied correctly and in advance, by the same project that
then missed it twice.

**Instance 2 is recorded in [finding 015](./015-verifier-vs-judge-not-run.md) and is not restated
here**, except for the part that matters to the survey: the freeze pinned every corpus file and
refused to start on any change to any of them, and it did not pin the *questions*. Hash-pinning a
derived artifact proves the artifact did not change and says nothing about its inputs.

**The two instances are causally linked, and the link is the uncomfortable part.** The near-miss
task reformulation that [finding 008](./008-ceiling-test-calibration.md) records as a *repair* —
turning four one-part questions into two-number corroborated pairs, because a bluffing agent could
pass the originals by abstaining — is precisely the prompt edit that finding 015 identifies as
provable drift under the frozen corpus. **A correct repair to an instrument silently invalidated a
corpus collected with the earlier version of it.** Neither pass was careless. The repair had no
reason to know a frozen corpus depended on the wording, and the freeze had no mechanism to notice.

## The survey: where else this may have happened

Three instances found by accident is not a base rate. What follows is a deliberate sweep of the
measurements this corpus relies on, ranked by how much rests on the figure. **Clean results are
included and are worth as much as the dirty ones.**

### S1 — the verifier's zero-false-alarm figure. Suspect; medium confidence; a cheap check settles it

**What rests on it.** [`VERDICT.md`](../VERDICT.md) describes the verifier as the one v1 capability
that is *"softer than unmeasured suggests"*, and the evidence it gives is that the postcondition arm
detects every numeric value error **with zero false alarms across 220 clean positives**. That
sentence is doing more product work than any other figure in the corpus.

**The suspicion.** The 220 is 226 oracle-positives less the 6 that the arm itself flagged. Excluding
those 6 is defensible — finding 015 establishes their staleness by three routes that do not involve
the arm, so the exclusion is not fitted to it. But **the remaining 220 sit in a corpus that is still
rebased.** Finding 015 records that 143 of 246 records ran under a battery version that no longer
exists, that a rebased corpus can only be trimmed and never repaired, and that the value-comparison
test which identified the 6 is **blind to wording drift** — 7 of the 9 numeric false successes are
prompt-drifted and every one of them passes that test. The eligibility machinery says the same
thing from the other side: only `eligible_same_battery` records need no join to attest, and 92 of
the 195 eligible records rest on the value test instead.

**Confidence.** Medium that the figure needs a caveat it does not currently carry; low that it is
wrong. A false alarm means the arm flagged a trace the oracle passed, and the arm recomputes from
the application's declared fields, so prompt drift only produces one where the drift moved the
answer. That it fired exactly 6 times is mild evidence the other records did not move.

**The check that settles it, and it is cheap.** Re-run the arm's false-alarm census restricted to
the records whose run manifest reports the current battery version, and report that rate beside the
pooled one. Read-only, no model, no credential. If it is still zero the claim is *stronger* than it
currently reads and should be restated on the narrower denominator. If it is not, the exclusion of 6
was insufficient and the headline needs rewriting.

### S2 — the consistency checker's rules and the fixtures pinning them. Structurally undecidable, but largely clean by construction

**The question asked was whether the fixtures pinning `numeric-provenance`, `dry-run-verdict` and the
multiplier rule were written before or after the false acceptances those rules were fixed in response
to. It has no answer and never will.** This repository holds five commits. One of them landed 455
files and rather more than a quarter of a million inserted lines, and every module under
`tools/corpuscheck/`, every fixture under `tools/fixtures/`, and every rule fix the documentation
dates to 2026-08-03 arrived inside it together. Nothing after it has touched any of them.
**Commit granularity is an evidence property**, and it is spent before anyone thinks about
evaluation.

**Three mitigations exist and two of them were verified here.**

- **`threshold_probe.py` discriminates 30 of its 34 declared perturbations**, meaning that for those
  the fixture would break if the constant moved one unit — a property that holds regardless of when
  the fixture was written, and therefore immune to this whole failure class. Six perturbations are
  declared as expected-to-hold and are justified in prose sitting in the same commit as the
  constants. Those six are the residue: their justifications are unfalsifiable from history and they
  are the only part of the numeric surface where the question is open.
- **The two named fixtures are synthetic, and that is the contamination-proof construction.** The
  word-boundary hole in `dry-run-verdict` is pinned by a planted line reading *"we avoid re-running
  the probe, so: H2 supported"* — and the string `avoid` occurs nowhere in any committed run
  directory. The exactness hole in `numeric-provenance` is pinned by a fixture quoting a figure
  against a finding carrying a longer one that contains it — and the illustrative pair named in the
  documentation occurs nowhere in the corpus either. **A fixture that reproduces the trap's shape
  rather than its historical instance cannot have been copied from a repaired artifact.** It is the
  right construction and it should be the default.
- The third mitigation, not verified here, is that the multiplier rule's real instances were live in
  the corpus until very recently. See S6.

**Verdict: clean by construction where it can be checked, undecidable at six numeric perturbations,
and no route exists to close those from history.** The available substitute is to attempt writing a
fixture one unit past each and see whether it can be expressed in prose anyone would commit; where
it cannot, the bound is unfalsifiable at the margin and should say so.

### S3 — the citation advisory's own parameter choices. In-sample; high confidence; low impact

Two parameters were selected on the data they are reported over. `--scope body` is self-disclosed in
`tools/README.md` as *"chosen after looking at these five documents"*. `--stoplist medium` is the
default because, in the tool's own words, it is the one that reproduces the ranks quoted in the
documentation — selection on a prior claim rather than on an outcome, but selection nonetheless. The
sensitivity sweep shows what it costs: the clean positive holds rank 1 under all six stoplist and
stemmer settings, while the leaked one ranges from 4 to 19 of 55 and reaches the top three under
none of them. **Notably the default is not the setting that flatters the tool** — the largest
stoplist with stemming ranks the leaked requirement best.

**Impact is low** because the tool gates nothing, exits zero on every finding, and both choices are
disclosed beside the numbers. **No check is needed.** What is needed is that the surviving headline
be quoted with the stoplist named, since the number is a ranking and not a measurement.

### S4 — the `dry-run-verdict` exemption bound's "measured, not guessed" justification. Confirmed post-repair; high confidence; low impact

The bound is justified by a measurement across the twelve committed dry-run directories: the
furthest a real disclosure token sits from the claim it licenses. **Those artifacts had already been
rewritten to carry line-local disclosures in response to this very rule** — the documentation says
the earlier form cost the project five artifacts — so the measurement describes repaired prose, not
prose the harnesses emit unprompted. That is exactly the pattern this finding is about.

**Impact is low, and the reason is worth stating because it is the general mitigation.** The bound is
set several times the measured maximum, so it is not sitting at the repaired edge; a different
measurement would not move it. A threshold fitted *to* a post-repair measurement would be a real
defect. A threshold set clear of one is only weakly justified by it.

**One disagreement I could not resolve.** An independent recount over the same artifacts gives a
maximum distance of 18 characters where the documentation says 19. The difference is almost
certainly an inclusive-versus-exclusive convention at the span end. I did not chase it and did not
edit the documented figure, because I could not determine which convention the original count used
and substituting mine would replace a number I cannot verify with a number nobody else can
reproduce either.

### S5 — what a green self-test means. Structural; high confidence; not a figure

`known-good` is described as holding *"the constructs that have historically produced false
positives"*. Every one of them was harvested from the real corpus **after** someone noticed the
false positive and fixed the check. It therefore encodes the modes already found and can encode no
others. **A green `known-good` run measures regression, not coverage** — it proves no previously
fixed false positive has come back, and says nothing about the next one. This is not contamination
of any number; it is a bound on what the self-test licenses, and it is worth naming because a green
self-test reads like a coverage claim.

### S6 — the documentation's own account of the checker's live output. Confirmed contaminated; fixed in this pass

`tools/README.md` carried a section headed *"Accepted, and live in the current output"* listing four
constructs the checker was said to report, one of them described as the reason the gate was not at
zero. **The gate is at zero.** Re-running the checker against the working tree gives no errors and no
warnings; re-running it against the tree at `cee7ff8` gives no errors and 32 warnings, every one a
multiplier. The 32 were cleared by adding eight inline citations across five skill documents — one
citation covers every claim within four lines of it — and two of the other three entries were never
in the output at either revision.

**This is the same defect in its smallest form**: a description of an instrument's behaviour that
went stale when the artifacts were repaired, and that nobody re-ran because re-running it is exactly
the step the description makes feel unnecessary. It is recorded here rather than passed over because
it was found by the same check as instance 3 and because it is the cheapest possible demonstration
that the pattern is live. The section has been corrected in the house style, with the superseded
claims struck rather than deleted.

### Clean results

Five things were checked and came back clean. They are listed because a survey that reports only
what it found is not a survey.

| # | What was checked | Result |
|---|---|---|
| C1 | E7's calibration band and its false-success threshold | **Clean.** Both are in the pre-registration, the file records the threshold as *"recorded now rather than chosen after the numbers arrive"*, and the band then fired against its authors twice and was not moved |
| C2 | Finding 010's eighth deployment configuration | **Clean.** Added after results were visible, labelled post-hoc at every appearance including the verdict row, and excluded from the pre-registered adjudication |
| C3 | The two named checker fixtures | **Clean by construction.** Both are synthetic and neither construct occurs in the live corpus, so neither can have been copied from a repaired artifact. See S2 |
| C4 | The surviving half of instance 3 | **Clean.** FR-055's bullet is byte-identical at both revisions and ranks first at both, so the tool found that defect unaided |
| C5 | The verifier ladder's freedom from tuned constants | **Clean, and it is this finding's rule applied in advance.** The derivation ran over all 61 requests in one pass, including the 17 it must refuse, explicitly so that deriving only where success was expected could not select the numerator |

## What this does not establish

- **The survey is not exhaustive and its own base rate is unknown.** Six candidates and five clean
  results are what one pass over the tooling and the findings index produced. Nothing here bounds
  what a second pass would find, and the honest reading of three accidental discoveries is that the
  denominator is unmeasured.
- **S1 is not a defect finding.** It is a suspicion with a named check attached. Nothing here says
  the verifier's false-alarm figure is wrong, and the arm's behaviour on the six stale records is
  evidence in its favour rather than against it.
- **S2 cannot be closed.** The undecidability is a property of the repository's history and no
  amount of further work changes it. Any future statement that those fixtures were written
  independently of the fixes would be an assertion, not a finding.
- **The rule was not validated against anything.** It is derived from three instances in one corpus,
  all found in one week, all in artifacts written by the same small number of authors. Whether it
  generalises is untested, and the limits recorded alongside it in the skill are reasoned rather
  than measured.
- **No re-scoring of any prior finding was performed.** This document changes how several figures
  should be read; it does not change any of them, and none of the numbers in `findings/` was edited.

## Reproduction

```bash
# instance 3 — the two sides of the comparison
python3 tools/cite_advisor.py --contracts-at cee7ff8 --ground-truth
python3 tools/cite_advisor.py --contracts-at cee7ff8 --spec-at HEAD --ground-truth
python3 tools/cite_advisor.py --contracts-at cee7ff8 --sensitivity

# S6 — the checker's output then and now
python3 tools/check_corpus.py --report-only --format summary
mkdir -p /tmp/at-cee && git archive cee7ff8 | tar -x -C /tmp/at-cee
python3 /tmp/at-cee/tools/check_corpus.py --root /tmp/at-cee --report-only --format summary

# S2 — which perturbations are discriminated
python3 tools/threshold_probe.py
```

The FR-038 and FR-055 word counts and body hashes are reproduced by parsing each revision's
`spec.md` with the advisory's own `parse_requirements`, which is what the scoring reads.
