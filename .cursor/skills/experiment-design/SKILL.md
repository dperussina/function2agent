---
name: experiment-design
description: Designs experiments and validation spikes that can actually falsify a claim about an agent system, and rejects designs that cannot. Use when planning a spike, benchmark, eval suite, A/B comparison, or ablation over agents; defining task success criteria or a grading rubric; proposing an LLM-as-judge; comparing single-agent against multi-agent or one tool surface against another; deciding what to measure before building a pipeline; or reviewing a result whose arms differ in more than one variable.
---

# Experiment design

> **Standing: v1, unchanged — and it has a worked example now.** On 2026-08-02 a criterion
> pre-registered in `11-validation-plan.md` §7, **before any experiment ran**, fired against the
> interest of the people who wrote it and was honored as written: the product was re-scoped to about a
> tenth of its planned size (`plan.md` OD-09). **Four things this skill teaches are what made that
> possible, and they are worth pointing at rather than restating.** ① The falsifying arm was the one
> *most likely to embarrass the product* — a shell, a socket and the app's own spec. ② A **ceiling
> arm** of hand-written ideal tools meant the disappointing result could not be blamed on
> implementation quality. ③ The thresholds were written down first and not moved. ④ A **second**
> pre-registered rule — tool arm above 85% means the task set is mis-calibrated, draw no conclusion —
> fired too, and removed two of the three families from the evidence base, leaving the re-scope
> resting on **one family at n = 4** (U-42).
>
> **Read ④ as the load-bearing one.** A pre-registration that only ever fires in your favor is
> decoration. Also note the honest weakness: the run was n = 4 per family against a power analysis
> written for 45 tasks × 5 repeats — thresholds were not moved, but the instrument was smaller than
> the one they were calibrated for.

Source: `research/11-validation-plan.md` §3, §4, §7, §9.

**The ordering principle: the cheapest experiment that can falsify the thesis runs first.** If the
thesis is wrong, learn it in week one. Design backwards from "what result would make us stop."

## Rule 1: no LLM judge in the primary success path

**An LLM judge is anti-correlated with truth on false-success detection — AUROC 0.18–0.30.** A
confident judge verdict is evidence *in the wrong direction*. Every primary outcome must be decided
by something that executes.

Acceptable primary oracles:

- SQL assertions over a database diff against a **privately-seeded fixture** (the agent has never
  seen the seed).
- HTTP status codes and request records from a **recording proxy** — not the agent's own tool-call
  log, which shows a call that returned 500 as having happened.
- Exact match against a value computed by a hand-written reference query.
- For writes: a target-state predicate plus a hand-written reference implementation, with
  `expect_changes` recorded from its actual diff and `allow_changes` widened by hand for legitimate
  alternative paths.

**Run the judge anyway — as an object of study, never as a gate.** Its jobs are to produce judge
AUROC against the oracle on your own corpus, to supply the denominator for "failures the judge
missed that the contract verifier caught," and to give an honest number to put in front of the next
person who proposes an LLM judge in the product. If it lands above 0.7 on your domain, that is a
genuinely useful result that makes future evaluation cheaper — **but the decision to trust it comes
after the measurement, never before.**

### Task authoring: invert it

Do not write a question and then hunt for the answer. **Compute the answer first, then phrase the
question:**

1. Generate candidate answers by running queries against the seeded fixture.
2. Reject degenerate candidates automatically: empty results, zero counts, single-row answers
   trivially first by primary key, anything obtainable from one unfiltered `GET /entity`.
3. **Only now bring in an LLM — to phrase the query in natural language.** A human accepts or
   rejects the phrasing. The model determines surface form and nothing about correctness.
4. **Freeze** the task file, the generator seed, and the fixture hash **before any arm runs.**

### Measure false success separately

False success — the agent reports doing something it did not do — is the failure mode that matters
operationally and the one judges are worst at. Four deterministic detectors, no model in any of
them: **D1** answer/oracle mismatch with voluntary (non-budget-capped) termination; **D2**
trace/claim divergence, where the final message asserts an action the proxy shows no successful
request for; **D3** collateral damage (`D_Δ ⊄ C_expect ∪ C_allow`); **D4** null-task affirmation —
confidently answering about a capability that does not exist, which is the cheapest signal available
since there is no oracle to author.

**Report FSR with failed tasks as the denominator, per detector and pooled.** A system at 40% task
success with 5% false success is far more shippable than one at 60%/50%, and a single success-rate
number hides that completely.

## Rule 2: run the ceiling test before building anything

**Hand-write the ideal tools first.** Roughly 20 tools written by an engineer who knows the app well
— call this arm **A8** — measures the ceiling of the *idea* without building a synthesizer at all.
Against the baseline arm **A0** (shell, read, grep, code search, no network to the app):

- **A8 ≈ A0** → domain tools do not help on these tasks regardless of generation quality. **The
  thesis is dead and it cost a week.**
- **A8 ≫ A0** → there is real headroom, and every later question becomes the far more tractable
  "how close does synthesis get to A8?"

Once a synthesizer exists, the decomposition is clean and this is the whole point:

```
A8 − A0  =  the value of the idea
A8 − A2  =  the quality of the synthesizer   (A2 = generated, selected tools)
```

**Without a ceiling arm those two are confounded, and every disappointing result stays ambiguous
forever** — you can always attribute it to implementation quality and keep going indefinitely.

**Make the baseline mean.** A0 should use a real coding-agent harness, not a hand-rolled loop. Add
**A0b** — the baseline plus a running app, `curl`, and the OpenAPI JSON on disk — which separates
"the value is synthesis" from "the value is merely access." A0b is the arm most likely to embarrass
the product, which is exactly why it must exist.

### Calibrate difficulty before freezing

Run the strongest model on A8 first. Target roughly **20% of tasks solved by every arm, 20% solved
by none, 60% discriminating.** Above 85% on A8 the tasks cannot separate arms; below 25% the corpus
measures noise. Adjust **before** freezing, never after seeing arm results. Useful external anchor:
frontier models score ~43.7% on MCP-Universe, so any design showing 90%+ in every arm is too easy.

## Rule 3: hold the harness fixed — it swings 10–20 points

**Benchmark scores swing 10–20 points on identical model weights depending on harness alone.** An
uncontrolled harness difference will dwarf whatever you are trying to measure.

| Hold fixed | Detail |
|---|---|
| **Model** | One pinned snapshot ID for the whole program, recorded in every result row. Re-run A0 at program end to detect provider-side drift |
| **Harness** | One loop, one context assembler, one truncation policy, one retry policy, one termination rule set. Emit a `harness_fingerprint` hash of the harness source into every result row and **refuse to pool results across differing fingerprints** |
| **System prompt** | One template with `{tool_list}` and `{role}` slots. **Per-arm prompt tuning is forbidden.** If one arm gets tuned, every arm gets the same tuning budget from the same person |
| **Tool result handling** | Identical truncation limit and serialization across arms, **including the baseline's shell output** |
| **Sampling** | Temperature, top-p, and reasoning effort fixed and recorded |
| **Fixture** | Identical snapshot restored before every run; verify by hashing the restored DB |
| **Task order** | Randomized per run with a recorded seed |
| **Repeats** | n = 5 for headline arms, n = 3 for the rest |

## Rule 4: always run the budget-matched control

**Arm A5: a single agent given the multi-agent budget** — set to the *measured* mean spend of the
best multi-agent arm, with everything else identical to the single-agent arm it derives from.

**This is the control almost nobody runs, and without it a multi-agent win is uninterpretable**,
because token spend alone explains most of the variance in agent benchmarks. If A5 matches the
multi-agent arms, the topology contributed nothing and you bought a k× token bill for a
presentation. See `multi-agent-topology-review`.

The same logic generalizes: **whenever an arm gets more of a resource, add a control that gives the
simpler arm the same resource.** More tools, more turns, more context, more wall clock — each one
needs its matched control or the comparison measures the resource, not the design.

## Rule 5: write kill criteria before running, and do not move them

**Pre-register kill criteria as "stop," not as "investigate further."** State them in the plan
document before any data exists, and **nominate the person empowered to call the kill before Phase 0
begins.** Moving a threshold after seeing results is how a dead thesis survives for a year.

Worked examples of well-formed criteria:

| Result | Pre-registered consequence |
|---|---|
| A8 ≈ A0 | Thesis dead. Stop. Domain tools do not help here |
| Contract verifier catches < 10 pp beyond the judge | Contract-derived verification is a CI detail, not a headline differentiator. **Adjust the product narrative honestly** |
| Judge AUROC < 0.5 | Published anti-correlation replicated. **No LLM judge anywhere in the product's success path, ever.** Encode it in the constitution |
| A5 ≈ best multi-agent arm | Multi-agent adds nothing beyond tokens. Ship the single agent |

A criterion phrased as "if X, we will investigate further" is not a kill criterion. It is
permission to continue.

**Rows 2 and 3 are well-formed and *neither branch of either ever evaluated* — note this, because it
is a failure mode pre-registration does not protect against.** Added 2026-08-03. The experiment that
would have read them, E19, was pre-registered, built, self-tested and dry-run at **$0.00**, and then
deliberately **not executed** by owner decision (`plan.md` OD-14). Both rows read a quantity defined
over judge verdicts, **no judge verdict exists anywhere**, and three independent blockers — each
sufficient alone, **all computable before the first call** — made the corpus unable to answer at any
price: the gate's 10 pp boundary sat inside a single trace, three pre-registered riders capped the
verdict independently of any result, and the only sound eligibility rule cost four of seven task
families. **So nothing cleared these rows and nothing failed them**, and the hypothesis is closed
UNMEASURED rather than answered — a null on *power*, not on the hypothesis.

Two things to carry from that, both about the *instrument* rather than the thresholds. **A criterion
can be written correctly and still never fire, and no property of the criterion tells you so** — what
tells you is a power check against the corpus you will actually have, run before the corpus is
frozen. And the corollary to ④ in the standing box above: *a pre-registration that only fires in your
favour is decoration*, but **a pre-registration that never fires at all is the more expensive
failure**, because it consumes the whole build and returns no evidence in either direction.
([`14`](../../../research/14-architecture-synthesis.md) TL;DR 21, U-47;
[finding 015](../../../specs/001-discovery-validation/findings/015-verifier-vs-judge-not-run.md).)

## Rule 6: score the instrument against the state the defect lived in

**An evaluation set drawn from defects that have since been fixed is contaminated by default.** Added
2026-08-03, after the third instance in this project. The question an instrument is being asked is
*would this have caught the defect*, and the only state in which that question has an answer is the
one the defect was live in. Score against the current state and the number measures the repair.

**The half that is easy to miss is the half that actually bit: reconstruct *every* side of the
comparison, not just the artifact carrying the defect.** A score reads at least two things — the
defective artifact and whatever it is scored against — and a half-reconstruction is indistinguishable
from a whole one at the point of use. It produces a real number, from real historical text, with a
git revision quoted beside it.

### The check

Before quoting any number an instrument produces against a set of known defects:

1. **List every artifact the score reads.** The defective one, the thing it is compared against, the
   population it is ranked within, the fixture that pins it, the prose that justifies its threshold.
   Anything that moves the number is on the list, and the list is longer than it first looks.
2. **Fix the revision at which the defect was live**, and diff each listed artifact between there and
   now.
3. **Byte-identical is a clean result and is worth stating out loud**, because it is what licenses the
   score. Unchanged artifact, score stands.
4. **Changed for unrelated reasons → provisional** until re-run with it pinned back. **Changed as part
   of the repair → invalid, not provisional**, and no amount of re-reading it helps.
5. **No revision separates the two states → the instrument is unvalidated on that instance.** Record
   that. Do not substitute the current state, and do not reconstruct a plausible history.

### Three instances, and each teaches something different

| # | Instrument | What the contaminated score said | How it surfaced |
|---|---|---|---|
| 1 | A verifier arm hand-written with the failure cases in view | detection **1.000 by construction** — an identity, not an estimate | pre-registration review, before any spend |
| 2 | A trace corpus frozen by file hash | every downstream figure, computed against questions that had since been edited | three unrelated arrivals inside one hour, none looking for it |
| 3 | A citation advisory ranking requirements against contracts | **2 of 2** known defects found, at ranks 1 and 3 of 57 | someone re-ran it with the requirement text pinned back |

**Instance 1 — the ground truth was also going to be an arm.** In that corpus the hand-written check
*was* the definition of failure, so using it as the arm made marginal detection algebraically equal to
the judge's fail-open rate under a different name. The fix was to require the arms be derived from
contracts by a mechanical procedure applied to *every* case, including the ones it must refuse —
"deriving only where success was expected would have selected the numerator." Cheapest of the three,
because it was caught by reading the design rather than by reading a result.

**Instance 2 — hash-pinning proves the traces did not change and says nothing about the questions.**
The freeze pinned every corpus file and refused to start on any change to any of them. It did not pin
the prompts, which lived in an external mutable file that the traces joined to by a stable task id.
The join was total, so it could never warn, and the dangerous drift was *wording* — which leaves
expected values untouched and is therefore invisible to the obvious value-comparison detector. **A
freeze must cover the inputs the frozen artifacts were derived from, not just the artifacts.**
([finding 015](../../../specs/001-discovery-validation/findings/015-verifier-vs-judge-not-run.md).)

**Instance 3 — the reconstruction was done, and it was done to one side.** Both pre-fix contracts were
correctly checked out of git. The requirements they were scored against were read from the working
tree. One of those requirements had been rewritten *from the contract being scored against it*, growing
from 51 words to 1379 and importing the contract's own subject matter, so a bag-of-words metric was
measuring the import. Pinned back to the revision where the defect was live, its rank falls from **3 of
57 to 10 of 55** — below any cutoff anyone would set. The sibling requirement is byte-identical at both
revisions, so its rank of 1 survives untouched. **The instrument finds 1 of 2, not 2 of 2**, and its
usefulness now rests on a single unleaked positive.

### What it cannot do, and what it costs

**It is inapplicable more often than it is applicable, and the reason is usually commit granularity.**
This repository holds five commits; one of them landed 455 files. Every consistency check, every
fixture pinning one, and every rule fix those fixtures were written around arrived together, so for all
of them the question *was this fixture written before or after the fix* has no answer and never will.
**Commit granularity is an evidence property.** A repository that squashes cannot run this check on its
own history later, and that cost is paid at squash time by someone who is not thinking about
evaluation.

**Two other classes are out of reach.** A defect in a *process* rather than an artifact — the agent
chose the wrong tool — has no state to roll back to. And a defect whose repair destroyed the evidence
cannot be reconstructed at all: instance 2's historical prompts are unrecoverable, so that corpus could
only be *trimmed*, never restored, and trimming spends n. Losing the power to answer is a real outcome
of applying this rule and not a failure of it.

**The costs are real and worth stating before someone discovers them mid-audit.**

- **It forbids a class of legitimate evaluation.** An instrument built today to catch a defect class
  will usually be validated against defects found yesterday, and yesterday's defects are fixed. Applied
  strictly, you cannot validate anything against your own history without reconstruction. The mitigation
  is to budget for the reconstruction rather than to soften the rule — instance 3's cost two flags.
- **Its most common output is "you have less evidence than you thought."** That is expensive to act on
  and easy to argue away, which is exactly why it needs to be a check somebody runs rather than a
  disposition somebody has.
- **It has a false-positive mode.** An artifact can change between revisions for reasons that have
  nothing to do with the repair, and re-pinning it then costs accuracy rather than buying it. Diff
  first; do not assume every change is a leak.
- **Passing it does not make a result clean.** It closes one route. Instance 3's surviving positive is
  still a single example, still chosen by the person who built the metric, still scored under
  parameters selected to reproduce an earlier sweep.

**The tell, if you only remember one thing.** An instrument that scores well on exactly the cases it
was built from, where *built from* silently includes anything the repair touched. **Two of two is the
number to distrust**, and the second tell is an artifact that got longer: text added during a repair is
text written with the answer in view.
([finding 017](../../../specs/001-discovery-validation/findings/017-evaluation-contemporaneity.md).)

## Rule 7: a denominator is the set of cases the instrument could have fired on

**Added 2026-08-03, and it is a different failure from Rule 6 rather than a variant of it.** Rule 6 is
about scoring against the wrong *state*. This is about scoring over the wrong *population*, and it
survives every amount of provenance work you do on the artifacts — the census that exposed it
reproduced its inputs exactly and was still reporting a figure that was not a rate.

**The shape: a detector that can decline, and a denominator that counts the declines as passes.** A
verifier returning `unverifiable`, a judge returning `uncertain`, a classifier with a reject option, a
probe that skips an unroutable target — each produces records on which the instrument returned no
verdict at all. Those records cannot enter a false-alarm numerator by construction, so counting them in
the denominator narrows the confidence interval while supplying no evidence in either direction. **The
figure looks stronger and the evidence has not moved.**

The instance: a postcondition verifier published as raising **zero false alarms across 220 clean
positives**. 45 of the 220 were records it declined, 40 of them a class it declined entirely. `0 of
220` is a true *statement* — no clean positive was flagged — and it is **not a rate**. The rate over
records actually compared is 0 of 175, and the attested subset is 0 of 96 with 93 compared.
([finding 018](../../../specs/001-discovery-validation/findings/018-verifier-false-alarm-attested-denominator.md).)

### The check

1. **Ask what the instrument's third outcome is**, before quoting any rate it produces. Almost every
   real detector has one. If it has none, say so — that is a finding about the instrument.
2. **Print the compared count beside the denominator.** Where they differ, the smaller number is the
   rate and the larger one is a coverage statement. Both are worth having; they are not the same claim.
3. **Report the refusal rate as its own number.** Folding it into a denominator lets a coverage problem
   silently improve an accuracy figure, and coverage is usually the more interesting of the two.
4. **Check that a paired numerator and denominator come from one population.** *"Detects every value
   error with zero false alarms across N clean positives"* is two measurements over two populations
   wearing one sentence. Restate both sides over one population, or label each side explicitly.
5. **Expect the honest paired figure to be smaller on the detection side, and do not read that as a
   loss.** In the instance above, restricting both sides to one population took detection from 10 of 10
   to 2 of 2 — because the failures the instrument exists to catch concentrate in exactly the records
   whose provenance is weakest. That is the general case, not a quirk: the interesting cases and the
   badly-attested cases are usually the same cases.

### Its mirror image, which this project also hit

**A denominator that *excludes* the failure and a denominator that *pads itself* with cases the
instrument could not fire on are opposite defects with an identical symptom.** In the same corpus a
schema-derived arm reported a perfect false-alarm rate on a 60-record sample while raising two false
alarms on the full corpus the sample had simply not drawn. That is the exclusion form; this rule is the
padding form. **Both produce a clean rate, both survive arithmetic checking, and neither is visible in
the figure** — the only thing that exposes either is re-running the instrument over the full population
and counting what it did on every record, including the records it refused.

### Amended 2026-08-04: the trigger is structural, not directional

**A third instance falsifies a directional assumption the two above rest on.** In both of them the
padding *flattered* the figure, so correcting it made the number worse and the author's incentive ran
against checking. In the third the padding **understated** the rate: *"21 of the 70 arm-B commands
that write a file immediately `cat` the whole file back"* computed its numerator over commands that
spilled **command output** while padding its denominator with 25 heredoc script writes — the model
typing a file, with no captured output to read back. The honest form is **21 of 45**. 30% became 47%,
and the correction made the argument the document was advancing *stronger*.

**So arithmetic that reproduces to the digit, and a conclusion that improves under correction, are
both fully compatible with a defective population. Neither is evidence the population is sound.** The
figures above reproduced exactly and were quoted in three places. Run the check whichever way the
error leans — **the trigger is that the numerator and the denominator are named by different
predicates**, and that is a structural property you can read off the two definitions without knowing
which direction the correction will move the number.
([finding 022](../../../specs/002-spec-aware-agent-runtime/findings/022-e7-tool-result-truncation-cap.md).)

**The tell, if you only remember one thing.** A false-alarm figure with a suspiciously round
denominator and no statement of how many comparisons it represents. Ask *how many of these did the
instrument actually look at* — and if the answer is not written down anywhere, the number is a
statement and not a rate. **And do not wait for the number to look too good**: the amendment above is
the instance where it looked too modest.

## Rule 8: an experiment whose positive result is a failure signal needs a negative control

**Added 2026-08-03, and it is a third distinct failure rather than a variant of the two above.** Rule
6 is scoring against the wrong state; Rule 7 is scoring over the wrong population. This one is
scoring from **one reading where the design needs two**, and it survives both of those audits
untouched — the state is current, the population is complete, and the number is still unearned.

**The shape: an ablation reads only the state after the treatment, and a failure there is its
positive result.** Remove the mechanism, observe the test fail, conclude the test was load-bearing.
Remove the feature, observe the score drop, conclude the feature carried the score. The reading is
one bit — *did it break* — and **every way the instrument itself can break produces that same bit.**
A missing dependency, a renamed subject, a subject that was already failing, a treatment that left
the subject unbuildable: each is indistinguishable from success, and each is scored as success.

This inverts the usual protection. When an experiment's expected result is *pass*, a broken
instrument reads as a disappointing result and gets investigated. When the expected result is
*fail*, a broken instrument reads as a triumph and gets published.

**The instance.** This repository's removal-proof harness deletes a mechanism, runs the test that
should depend on it, and reads a non-zero exit as proof. Run on a host where `python3` could not
`import pytest`, every arm exited non-zero for that reason, and it reported **51 proved, 0 unproven**
and exited clean. Nothing in the output was false; every line was computed correctly from what the
instrument observed. The only thing that surfaced it was that the score was implausibly good.

**Two siblings in the same instrument, pointing opposite ways, and both were live.** `pytest` exits
4 for a selector naming a test that no longer exists, which is non-zero and was therefore scored
`proved` — so a *renamed test* silently converted a proof into a result. `go test -run` exits 0 when
its pattern matches nothing, so the same rot on the Go side was scored `UNPROVEN`, which is a false
claim about the tests rather than about the proof. **One rot, two opposite verdicts, neither true.**

### The check

1. **Name the reading a positive result produces.** Here, a non-zero exit status. Write it down; it
   is usually narrower than people assume, and that narrowness is the problem.
2. **List every fault that produces that reading without the treatment having done anything.**
   Dependency absent, subject renamed or deleted, subject already failing, treatment applied nothing,
   treatment left the subject unparseable or unbuildable. The list is short and finite, which is why
   this is a check and not a disposition.
3. **Produce each fault and run the instrument.** Not reason about it — produce it. A missing
   dependency is one `PATH` away; a renamed subject is one rename. An instrument that has never been
   run in its own failure modes has no evidence about them.
4. **Require a reading of the untreated state, and require it to be the expected negative.** This is
   the fix, and everything above is diagnosis. The claim is *A because B*, which needs both states;
   an instrument holding one of them can only ever report *A*.
5. **If the untreated reading is too expensive per case, take it once over the whole population
   rather than dropping it.** Per-case baselines here would have roughly doubled a fifty-one-arm run.
   Taken once across the suite and looked up per arm, the same evidence cost about a tenth of the
   run — and it is *stronger*, because it also answers "was anything already red."

### What it does not buy

**A negative control establishes that the subject passed before, not that it failed *because of* the
treatment.** A treatment that breaks the subject for an unrelated reason still reads as a positive
and still clears every step above. Closing that needs attribution — which specific assertion failed,
and does its name have anything to do with the claim — and attribution is a reading task with no
threshold in it, so it belongs in a listing a human reads rather than in a gate. This project keeps
one at [`tools/proof_attribution.py`](../../../tools/proof_attribution.py), on the same
fails-nothing footing as [the citation advisory](../../../tools/README.md#the-advisory--cite_advisorpy).

**And the control cannot be the thing being controlled for.** The baseline must be taken with the
same interpreter, toolchain and privileges the treated run will use, in the same tree. A baseline
established somewhere healthier than the arms is a statement about the healthier place.

**The tell, if you only remember one thing.** **A perfect score on an ablation suite.** Every
mechanism load-bearing, nothing unproven, no skips — that is either an unusually well-tested system
or an instrument that has stopped discriminating, and from the outside the two are the same output.
Before believing it, break the instrument on purpose and check that the score moves.
([`tests/removal_proofs.sh`](../../../tests/removal_proofs.sh),
[`tools/check_tampers.py`](../../../tools/check_tampers.py).)

## Spike hygiene

**Spike code is disposable; the task corpus and its oracles are not.** The corpus outlives the
spike; every file in `spike/` carries a delete-by date and may not be imported by v1. Track it
explicitly — spike drift, where a spike that works becomes the thing you ship, is a governance
failure rather than a technical one.

Two related distinctions worth keeping straight: **cassette replay tests the plumbing; evaluations
test the prompts.** And when annotating failures, an LLM may pre-sort traces to make human
annotation faster, but **the label of record is human** — with a written codebook, two annotators,
and Cohen's κ reported. Using a model's own annotation pipeline as the primary label reinherits the
judge-reliability problem the whole design exists to route around.
