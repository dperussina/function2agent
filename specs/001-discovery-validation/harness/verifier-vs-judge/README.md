# E8 — verifier vs judge

**Does a contract-derived verifier catch real failures that an LLM judge misses?** That is
hypothesis **H2** from `research/11-validation-plan.md`, and it is the row that document calls
"the most consequential gap in the table." If a general LLM judge catches everything a derived
verifier catches, the verifier is not a differentiator and v1 has no product.

Read [`PREREGISTRATION.md`](PREREGISTRATION.md) before reading any result. The thresholds, the
denominators, the stop conditions and the decision table were fixed before any judge call was
made and before any scoring code existed. **This directory is the harness that document
specifies.** Anything the harness does that the preregistration does not authorise is an
amendment; the ones this build found are listed under *Disagreements* below, and none of them
has been silently applied.

> This is spike code. It is not a product prototype, nothing in `src/` may import from it, and
> it is scheduled for deletion after 2026-11-30.

> ## ⛔ E8 is CLOSED. It was built and then deliberately **not run**. Arm (c1) is QUARANTINED.
>
> **Status: built, dry-run at $0.00, and retired by owner decision on 2026-08-03 without a
> single model call.** Not "not run yet" — *not run*, because the corpus cannot answer the
> question it was preregistered to ask. Three independent reasons, none of which needed a call:
> power, three preregistered riders, and the coverage the eligibility rule costs.
>
> **Arm (c1) may not be scored.** `c1_schema.verify()` raises; `runner.py` refuses `--arms … c1`.
> Its one non-trivial detection is fabricated by a defect that is deliberately **not fixed**
> (amendment rule 2). Running it prints a schema-derived catch that did not happen.
>
> **Read [`../../findings/015-verifier-vs-judge-not-run.md`](../../findings/015-verifier-vs-judge-not-run.md)
> before running anything in this directory**, and PREREGISTRATION.md **Amendment B5**. The
> sections below are left as built, with dated corrections in place; where one contradicts the
> finding, the finding is right.

**No model has been called and nothing has been spent** — all 5,490 recorded judge-call rows are
stub rows at `cost_usd: 0.0`, across 12 run directories all marked `dry_run: true`.

> **⚠️ Every committed `analysis.json` and `report.md` under `results/` had its decision block
> neutralised on 2026-08-03, and none of them may be read as a verdict.** They were emitted with
> a decision table computed against those stub judge rows, and the rows said so nowhere a reader
> would grep. **No figure was altered**; the classification clause of each row was withheld and
> the block renamed. The rationale, the exact transformation, what was deliberately *not* done,
> and how to reproduce or reverse it are in
> [`results/NEUTRALISATION.md`](./results/NEUTRALISATION.md). The recurrence guard is the
> `dry-run-verdict` check in `tools/check_corpus.py`, which fails the corpus check on a
> verdict-shaped claim in any artifact belonging to a run marked `dry_run: true`.

---

## Reproducing the zero-cost validation

```bash
cd specs/001-discovery-validation/harness/verifier-vs-judge

python3 freeze.py --verify              # the frozen corpus is intact, or refuse
python3 selftest.py                     # 169 checks: every control fires and stays quiet
python3 runner.py --dry-run --leak-audit   # pre-flight the leak assertion over all 80 traces
python3 runner.py --dry-run             # the whole pipeline, stub judge, $0.00
```

None of that needs a credential, a network, or a running container.

The priced run, ~~once authorised~~ **which will not happen — retained so the command is on the
record, not as an instruction**:

```bash
export F2A_ENV_ROOT=/path/to/your/dotenv/tree   # or --env-root PATH, or export the key
python3 runner.py --arms b b_prime ~~c1~~ c2 --app-base-url http://localhost:9925
```

*(Corrected 2026-08-03 — `c1` is **quarantined**. `runner.py` refuses it before the freeze, the
credential and the projection, and prints why. It remains an accepted `--arms` value so that
asking for it yields the explanation rather than an argparse error. Amendment B5.)*

### The credential

`runner.py` takes one Anthropic key from `ANTHROPIC_API_KEY` in the environment, and only if
that is unset does it search a dotenv tree **you name**, via `--env-root PATH` or
`F2A_ENV_ROOT`. **There is no default path** and no guessing: with neither supplied it exits
with a usage message before spending anything. Resolution goes through
[`../provider-credentials/envroot.py`](../provider-credentials/envroot.py) — imported, not
copied — which parses `KEY=VALUE` lines itself with no interpolation and no shell.

No credential value is read into a log, a trace, a manifest, an error message, or a model
prompt. Only key *names* are ever printed. `selftest.py` scans every file in this directory for
key material and for absolute home paths, and fails if it finds either.

---

## Layout

| File | Role |
|---|---|
| `PREREGISTRATION.md` | the specification. Not written by this build and not edited by it. |
| `config.json` | everything pinned: models, prices, seed, repeats, denominators, gate thresholds, stop conditions. Hashed into the fingerprint. |
| `corpus_freeze.json` | the 11 in-scope ceiling-test run directories, the SHA-256 of all 22 files, the counted corpus shape, and — since B4.5 — the **battery**: the hashes of `tasks.json` and `expected.json`, each run's `battery_version`, and the cross-battery census. |
| `freeze.py` | builds and verifies the freeze; `verify_or_die` is the refuse-to-start every entry point calls first. `--battery` reports which runs executed a superseded battery. |
| `redact.py` | the whitelisting projection and the hard oracle-leak assertion. |
| `corpus.py` | loads the frozen scope; the B3.2 eligibility rule (`--eligibility`), the mechanical negative taxonomy and the three denominators. |
| `select.py` | the scoring set: every **eligible** negative (15 of 20, per B4.2) plus 60 seeded, stratified positives. Refuses without the eligibility partition. |
| `prompts/judge_v1.md` | the judge prompt, written once, hashed into the manifest, never tuned. |
| `judge.py` | arms (b) and (b′), credential resolution, payload assembly, verdict parsing, and the stub judge. |
| `derivation-rules.md` | the c1 and c2 derivation rules, committed before any per-task derivation. |
| `c1_schema.py` | arm (c1), the seven schema clauses. |
| `c2_postcond.py` | arm (c2): the bounded projection language, the precision ladder, the literal-provenance validator, and the refusals. |
| `recompute_source.py` | c2's recomputation source — one interface over the live Mealie client and an offline fixture; `--audit` replays it against the recorded traces. |
| `c2_derivations.json` | the human-applied c2 derivations: 61 entries, 44 derivations across 10 rule families plus 17 recorded refusals. |
| `cost.py` | token estimation, truncation, the projection, and the live ceiling. |
| `metrics.py` | every metric of §6, each with counts and a Wilson interval. |
| `controls.py` | the five negative controls. |
| `analyze.py` | the report, and the assertions that void the run. |
| `runner.py` | the driver. |
| `selftest.py` | proves every check fires on planted-bad input and stays quiet on known-good. |
| `fixtures/` | the planted-bad and known-good inputs the self-test runs against. |
| `results/<run_id>/` | `manifest.json`, `judge_calls.jsonl`, `verdicts.jsonl`, `analysis.json`, `report.md`. |

---

## The six mechanisms that stop this experiment fooling itself

### 1. The oracle-leak assertion

The ceiling-test trace format writes `{**row, "tool_calls": ..., "transcript": ...}`, so
`expected`, `reason`, `outcome`, `false_success` and `detectors` sit **in the same object as
the transcript**. A scorer that serialises the record hands the judge the answer.

Two layers. `redact.scoring_view` is a whitelist, so a field added to the record format later
is excluded by default rather than included by default. `redact.assert_no_oracle_leak` runs on
the fully assembled payload before **every** judge call and **every** verifier invocation, and
raises `OracleLeak`, which `runner.py` treats as fatal: it writes `ABORTED.json`, discards the
run, and exits 3.

The literal checks are scoped deliberately, and the scoping is the part worth reviewing:

- **Forbidden keys** are checked as JSON keys, recursively, over the whole payload,
  **absolutely**. This is what catches `json.dumps(record)`.
- **The oracle's own `reason` string** is checked over the whole payload, **absolutely**.
  `"expected 3.201754, got 3.23"` has no innocent route into a transcript.
- **Key literals and the expected value** are checked over the **harness-authored region**.
  Agent content is exempt, because on an oracle-passing trace the agent's submitted answer
  *is* the expected value and §4.2 requires the judge to see the submitted answer.

A bare substring test over the whole payload would abort on nearly every positive and on any
transcript containing the English word "reason". A check that must be bypassed to run gets
bypassed, which is the same outcome as a check that never fires.

`--leak-audit` pre-flights the assertion over all 80 selected traces and reports rather than
aborts, so the audit costs nothing and is read before anyone spends.

### 2. The five negative controls

All five run on every invocation, and `controls.leak_assertion_selfcheck()` runs at the top of
`runner.py` **before the first call**, so an assertion disabled by a refactor is caught before
480 calls have been paid for rather than after.

| Control | How it is checked |
|---|---|
| Label-shuffle | 1000 permutations of the oracle label vector; mean AUROC must be 0.500 ± 0.05. Measured 0.5024 and 0.4973 on the two judge arms. Voids the run if it drifts. |
| Constant-fail | FPR must be exactly 1.000 and MD must equal the judge's fail-open rate. Both asserted, not printed. |
| Constant-pass | MD and FPR must both be exactly 0.000. |
| Oracle-leak | four directions, three firing and one silent, checked at run start and again in the self-test. |
| Predicted-null | c1 must detect zero numeric value errors. Detection voids c1 (S3). **Reports NOT RUN since the quarantine, and S3 is undischarged rather than satisfied.** |

Each is exercised against planted-bad input in `selftest.py`: the label-shuffle control against
an AUROC that ignores its labels, the anchors against a metric that ignores its verdicts, the
leak assertion against a payload embedding the record, and the predicted-null against a c1 stub
that cheats. A control that cannot fail is not a control.

### 3. The schema-arm blindness prediction

`controls.predicted_null` is called from `analyze.analyse` on every run. If c1 detects any
numeric value error, the run is marked `fatal`, the report opens with **RUN IS VOID**, c1 is
voided, and `runner.py` exits non-zero. It is an assertion, not a note.

**It fired twice during construction, and both times it was right.** The first time, clause
C1.3's type extraction only read the top-level properties of directly `$ref`-ed schemas, so a
paginated envelope's numeric fields were invisible and a perfectly well-typed number looked
categorically impossible — c1 "caught" 5 of 9 numeric errors by a spurious type mismatch. The
second time, a corrected walk still failed to descend into operation objects and c1 caught 9 of
9. Both were implementation defects in c1, found before any judge call and before any result
existed. With the walk resolving `$ref`s transitively, c1 detects **0 of 9**, as pre-registered.

> *(Narrowed 2026-08-03 — the third time it did not fire, and it should have. The 0-of-9 is real
> and is genuine evidence for §7(5). But the control is **scoped to the numeric class**, and c1's
> defect is in the set-typed one: clause C1.5 fires 3 times corpus-wide and is wrong all 3 times,
> which no numeric-class control can see. **A control aimed at one failure class certifies
> nothing about the others** — and this one certified an arm whose only non-trivial output was
> fabricated. Recorded because that lesson outlives E8. B5.1, B5.2, and finding 015.)*

### 4. Frozen corpus scope

The corpus was live while the preregistration was being written and it has grown again since:
`20260803T070942-diag-…` was in progress at freeze time, and two further directories have
appeared. `freeze.SCOPE_RUNS` is a **committed list of 11 directory names**, not a glob,
precisely because a glob would absorb whatever comes next. `corpus_freeze.json` carries the
SHA-256 of all 22 files plus the counted shape, and `verify_or_die` refuses to start on any
hash change, any missing file, or any shape drift — with a message that says explicitly not to
re-freeze to make it pass.

The frozen shape reproduces the preregistration's counted table exactly: 246 records, 226 pass,
20 fail, 11 false successes across 6 distinct tasks, 61 distinct tasks.

**The freeze pinned the records but not the question they were graded against**, and did so for
the corpus's entire existence. Traces carry no prompt, so a trace run under a superseded task
battery joined silently against today's `tasks.json` and produced a plausible pairing. Since
B4.5 the freeze also pins the battery: the hashes of `tasks.json` and `expected.json`, each
run's `battery_version` read from its own `manifest.json`, the version under test, and the
cross-battery census (**5 runs, 143 records**) so the exposure cannot change under a passing
hash check. A freeze carrying no battery block is rejected outright rather than read as nothing
to check — that reading is what kept the defect invisible. `python3 freeze.py --battery` reports
which runs are affected.

### 5. The three denominators and the discount

`corpus.denominators` derives N, N_disc and N_fs mechanically from the oracle's own recorded
reason strings, and every verifier arm is reported against all three plus a fourth,
near-miss-excluded variant. The gate reads N.

They are derived over the **eligible** population, so they are ~~N (20), N_disc (13) and
N_fs (11)~~ **N (15), N_disc (10) and N_fs (10)**. *(Corrected 2026-08-03 — **narrowed** by
Amendment B4, not wrong when written: the preregistered sizes are the corpus's, and B3.2 had
not been applied.)* The report prints each denominator beside the size §6.3 preregistered and
the difference, and every `Proportion` carries the population it is over, so a shrunken
denominator can never appear without its reason.

The ×0.7681 pipeline discount is applied in `analyze._serialise_verifier` to arm c2 only, and
the decision table reads `MD_gate_pp`, which **is** the discounted figure. The raw number is
printed beside it and is never an input to a gate. `selftest.py` asserts the arithmetic on the
preregistration's own worked example: a raw 12 pp discounts to 9.2172 pp and does not clear.

### 6. Cost governance

`cost.project` measures the actual serialised payload of the 80 selected traces and prints the
arithmetic before the first call. The live `cost.Ledger` is checked **before** each call, and
bills measured usage from the API response, never the estimate. Truncation caps any transcript
at 24,000 tokens, elides the middle rather than either end, and flags the record.
`--dry-run` runs the entire pipeline against recorded fixtures with a stub judge for $0.00.

**Measured projection** (80 traces, mean 4,905 input tokens/call, max raw payload 85,280 B,
0 records truncated):

| Line | Tokens | Rate | Cost |
|---|---|---|---|
| (b) `claude-sonnet-4-5-20250929` input | 240 × 4,905 = 1.1772 M | $3.00/M | $3.532 |
| (b) output | 240 × 250 = 0.0600 M | $15.00/M | $0.900 |
| (b′) `claude-3-5-haiku-20241022` input | 240 × 4,905 = 1.1772 M | $0.80/M | $0.942 |
| (b′) output | 240 × 250 = 0.0600 M | $4.00/M | $0.240 |
| **Judge subtotal** | | | **$5.613** |
| Repair reserve | | | $2.000 |
| **Planned total** | | | **$7.613** |

Against the preregistration's $6.85 expected and $8.62 pessimistic, and under the $9.00 abort.
The contingency does not fire: $5.613 is below the $6.50 trigger, so positives keep all three
repeats. No transcript reaches the 24,000-token cap — the largest is 85,280 bytes ≈ 21,320
tokens — so the truncation count is expected to be 0 and any non-zero count is news.

The measured mean of 4,905 tokens sits close to the preregistration's *pessimistic* 5,200
rather than its expected 4,065, because the 20 negatives are much larger than the corpus mean:
38,112 bytes against 13,490. The preregistration anticipated this and priced it.

---

## Disagreements with the preregistration, and what was done about each

Every one of these is reported rather than silently absorbed. None changes a threshold.

**1. The false-success split is 9 numeric / 2 set, not 8 / 3.** §2.1 decomposes the 11 false
successes as 8 numeric value errors and 3 set/cardinality errors. Classifying them
mechanically from the oracle's own reason strings gives **9 numeric and 2 set**. The totals
agree (11), and every other figure in §2 reproduces exactly; one record is on the other side of
the line. Consequence: §4.6, §7.5 and S3 are all keyed to "the 8". The harness runs the
predicted-null control over the **measured** subclass of 9, prints
`amendment required` next to the result, and never substitutes the preregistered count.
Substituting it would be an unrecorded amendment; shrinking the measured set to match would be
worse. **This needs an amendment before the run.**

**2. There are 3 sub-1% near-misses, not 2.** §6.5 says two of the numeric false successes are
under 1% relative error (`3.23` vs `3.201754`, 0.88%). Three records carry that exact
mismatch. The near-miss-excluded metric variant uses the measured 3. Same amendment.

**3. The $6.50 contingency trigger reads on the combined judge arms, not arm (b) alone.** §10
says "projects arm (b)'s cost. If the projection exceeds $6.50 …". Arm (b) alone is planned at
$3.83 expected and $5.23 pessimistic, so read literally the contingency could never fire. The
$6.50 trigger sits between the document's own **combined** subtotals ($4.85 expected, $6.62
pessimistic), which is the only reading under which it is live. `config.json` records the
reading as `contingency_scope: judge_arms_combined` and the projection prints both figures.

**4. §7.4's leak assertion is unrunnable as a literal substring test.** See mechanism 1 above
for the scoping adopted and why. This is the single most consequential interpretation in the
build and the one a reviewer should challenge first.

**5. The RNG seed is required but not named.** §9.1 requires a seed recorded in the manifest
before selection and does not give one. `config.json` pins `20260803`, committed before any
selection ran.

**6. Arm (b′) is priced but not named.** §10 prices the cheap judge at $0.80/$4.00 per M and
calls it "Haiku-class". `claude-3-5-haiku-20241022` is the dated snapshot at exactly those list
prices; pinned in `config.json` before any call.

**7. The per-file SHA-256 hashes did not exist to be pinned.** §2 requires the harness to
record them and refuse on change, but the preregistration contains no hash values. They were
computed at build time and committed in `corpus_freeze.json`.

**8. c1 as specified is nearly vacuous on this corpus, and that is a finding, not a bug.**
Clauses C1.2, C1.3, C1.4 and C1.6 fire on nothing; C1.1 catches the 7 no-output traces and
~~C1.5 catches 1 of the 2 set-cardinality errors~~ **C1.5 catches none of them**. ~~`UNV_c1 = 90%`~~
**92.0%**, which trips §6.6's rule that an arm above 50% unverifiable may not be described as
covering the corpus. This is exactly the structural blindness §2.1 predicts, arriving as a
measurement rather than as an argument.

> *(Corrected 2026-08-03 — the conclusion is **right and understated**; the supporting sentence
> is **wrong**. C1.5 does return `fail` on the one set-typed record, and that is not a catch: it
> compares the 60-name submission against `total=8` read from `/api/organizers/categories` while
> naming `/api/recipes`, which returned **60** — equal to the submission, so a correct comparison
> **passes** the trace. Corpus-wide the clause fires 3 times and is wrong 3 times; the other two
> are oracle-**positives**, where the answer is a filtered subset of the collection the envelope
> counts. **C1.5 precision is 0 of 3.** So c1 is not "nearly vacuous with one catch" — it is
> vacuous, plus a fabrication. Arm quarantined; clause deliberately not repaired. B5.1, B5.3,
> finding 015.)*

**9. Two clauses were silently vacuous until the self-test caught them.** C1.5 matched
`"total"` while tool results are embedded as escaped JSON strings (`\"total\"`), and C1.4/C1.5
tested `isinstance(sub, list)` while the submit contract serialises **every** answer as text —
all 239 submissions in the corpus are strings. Either defect alone would have produced a clause
that could not fire on any trace, indistinguishable from a clause that correctly found nothing.
Both were found by planted fixtures, not by the corpus.

---

## Arm (c2) — built 2026-08-03

The postcondition arm is now complete, and with it the answer to the question the experiment
exists to ask.

**c2 detects all 9 numeric value errors, including all 3 sub-1% near-misses, with zero false
alarms on 220 clean positives.** These are the failures `c1` is structurally blind to by
construction.

> *(Labelled 2026-08-03 — **not a correction; both figures are zero and both were right.** The
> corpus quotes "zero false alarms on **220** clean positives" and `FPR_c2 = **0/60**`
> interchangeably, and they are **different populations** whose denominators differ by roughly
> 3.7×. **220** is the offline **full-corpus sweep**: `c2_postcond.verify` run directly over all
> 246 frozen records against the committed offline fixture, covering every one of the 226
> oracle-positives less the 6 stale ones. **60** is the **seeded stratified sample** that
> `select.select` draws for a run, and it is the population every `FPR_c` figure in every
> `report.md` under `results/` is computed on — sized for the judge, whose calls are what cost
> money. Quote the 220 for a claim about the mechanism and the 60 for anything set beside a
> judge-scored metric. **The distinction is load-bearing, not pedantic:** `FPR_c1` reads a
> perfect `0/60` in every dry run while `c1` was raising two false alarms elsewhere in the
> corpus that the sample had not drawn. Finding 015.)* ~~On the frozen corpus, excluding the stale traces of Amendment B3, `D_c2` is
10/14 = 71.4 pp raw, **54.9 pp after the ×0.7681 contract-extraction discount** — the figure
the decision table reads, comfortably clear of the ≥10 pp gate.~~

**On the eligible population `D_c2` is 10/15 = 66.7% raw, 51.2 pp discounted** — c2 flags every
one of the 10 eligible false successes and none of the 5 no-output negatives, which it correctly
declines rather than catching for free.

> *(Corrected 2026-08-03 — the numerator and the false-alarm claim stand and were re-derived
> independently; the denominator and the **conclusion** do not. **Wrong**: 14 was B3.3's
> uncorrected negative count, superseded by B4.2 at 15. **Wrong and load-bearing**: `D_c2` is a
> *detection* rate and the gate reads `MD` — **marginal** detection, traces the judge passed and
> the verifier failed. No judge verdict exists, and none ever will, so **nothing here clears the
> gate or fails it**. c2's *mechanism* is demonstrated; its *marginal value over a judge* is
> unmeasured, and the distinction is the whole of what the owner's decision turns on. Finding
> 015.)*

**The near-misses are caught by exactness, not by a tolerance.** This matters more than the
headline. `groundtruth/openapi.json` declares **no numeric precision anywhere** — no
`multipleOf`, no numeric `format`, in any of 243 component schemas — so §4.5's instruction to
compare "at the schema's declared precision" has no referent on this target (Amendment B2).
What replaced it is a six-rung precision ladder committed in `derivation-rules.md` before any
derivation was written. The ladder contains **no numeric constant**: each rung names a *source*
of precision, never a value, and its last rung is a refusal rather than a default tolerance.
28 projections land on integer-closed exactness, 9 on text/set identity, 6 on the application's
own serialisation, 1 on a precision the request itself declares, and 17 refuse. A count is an
integer, so 12 ≠ 13 however close they are proportionally — no tolerance had to be chosen, and
so none could be fitted.

> *(Narrowed 2026-08-03 — **the heading over-claims for the near-misses specifically.** The
> ladder verifiably contains no numeric constant, every rung names a source rather than a value,
> and the last rung refuses; all of that is re-derived and stands. But "12 ≠ 13" is integer
> exactness and **the three near-misses are not counts** — they are one mean, `3.23` against
> `3.201754`, and they are the sole projection on rung **P4**, whose 2 decimal places are read
> out of the request text's "to two decimal places". So they are caught by *exactness at a
> precision the prompt declared*, not by exactness on integers, and c2 labels that derivation
> `provisional` on its own provenance. Threshold-free: yes. Contract-derived: no — that one is
> request-derived, on an experiment about contract derivation. B2.2 invited exactly this
> discount. Finding 015.)*

**How the no-fitting constraint is enforced rather than promised.** Every literal a pipeline
compares against must be declared with a source, and a `prompt`-sourced literal must actually
occur in the request text; `validate_derivation` re-tokenises and checks. An expected value
does not occur in the text of the request that produced it, so it cannot be declared, and an
undeclared literal is rejected. Entries are keyed by request signature, never by task id, and
the self-test asserts no task identifier appears in `c2_derivations.json` or in
`derivation-rules.md`. The derivation procedure was applied to **all 61 requests in one pass**,
including the 17 it must refuse, because deriving only where success was expected would select
`MD_c2`'s own numerator.

**Recomputation runs offline, at zero cost.** `recompute_source.py` presents one interface over
a live Mealie client (reused from `harness/ceiling-test/`) and an offline fixture rendered from
the seed plan into the response shapes the OpenAPI document declares. No live instance is
contacted. The rendering is not trusted on assertion: `--audit` replays it against every API
response recorded in the frozen traces, and the committed fixture passes.

### A fixture-fidelity defect, and how it was found

The first validation pass reproduced 43 of 44 oracle expectations. The single disagreement was
a user count — 4 recomputed against 5 expected. The cause was the fixture, not the derivation:
Mealie bootstraps one administrator at first start, `ceiling-test/seed/apply.py` authenticates
as it, and the fixture rendered only the seed plan's four users. The fix is sourced from
`ceiling-test/config.json`'s `target.admin_email` — the address the seeder logs in as — and not
from any expected value. It is recorded here rather than quietly patched because it was
surfaced by the Principle I validation pass and **not** by the trace audit, which could not
catch it: no recorded trace contains a users listing. With it corrected, all 44 agree.

## Before this can run

1. ~~**Amend the preregistration** for disagreements 1 and 2.~~ **Done** — Amendments B1 and B2,
   dated 2026-08-03, recorded with reason and validity cost under the document's own amendment
   convention. `corpus.taxonomy_discrepancies` now asserts the counts on every load.
2. ~~**Write `c2_derivations.json`.**~~ **Done** — 61 entries, one per request: 44 derivations
   across 10 rule families and 17 recorded refusals.
3. ~~**Stand up a recomputation source for c2.**~~ **Done** — `recompute_source.py`, offline by
   default, audited against the recorded traces.
4. ~~**Apply the Amendment B3 eligibility rule — this is now the most urgent item.** 12 of 246
   records carry an `expected` value that disagrees with today's `tasks/expected.json`: the four
   `NM` tasks were revised from a one-part question into the two-number corroborated form, and
   three `R4` tasks moved from a null expectation to a real one.~~ **Done** — Amendment B4,
   2026-08-03. ~~**6 of the 20 negatives (30%) and 6 positives are stale**~~ **1 negative and 6
   positives.** *(Corrected 2026-08-03 — **wrong**: the three `R4` tasks are not stale. Those
   runs executed today's battery; nothing was submitted, so `ceiling-test/checks.py` never
   computed an `expected`, and sibling records for the same tasks in the same runs carry today's
   values. Derivation in B4.1.)*

   Applied in `corpus.py` (`eligibility`, `partition`) and enforced in `runner.py`, `select.py`
   and `analyze.py`. **195 of 246 records are eligible**: 7 stale and 44 *unattested* — a third
   status B3.2 did not anticipate, for cross-battery records with nothing to compare (B4.3).
   The ledger prints before selection and heads every report; every metric states its
   population. Read it with `python3 corpus.py --eligibility`.

   Two costs, both larger than B3.3 estimated. **Four of seven task families go to zero**
   (N, NM, R3, W1), taking the whole `protocol` negative class with them, and no policy
   setting recovers them — every record of every lost family lives in a cross-battery run
   (B4.4). And `UNV_c1` is 92.0%, with every marginal c1 detection coming from its one
   non-schema clause: **E8 has one verifier arm that can make a claim, not two** (B4.6).
   The 9 numeric false successes are all clean, so the central claim is unaffected.
5. **Run the §4.1 oracle adjudication**: a human pass over all 20 negatives and a random 20 of
   the 226 positives. Not implemented here; it costs no model tokens, and >2/40 overturns is
   stop condition S1. Nothing downstream is interpretable until it is done.

   *(2026-08-03 — **still open, and it will stay open.** A blind pass over 40 traces exists at
   [`adjudication/REPORT.md`](adjudication/REPORT.md) and it states in its own §0 that it was
   performed by a **model**, not a human. §4.1 requires a human and S1's >2/40 threshold is
   defined over that human pass. **The requirement was never satisfied at any n**, which caps
   what E8 could have claimed independently of sample size. B5.4.)*
5. **Review interpretation 4** (the leak-assertion scoping) and disagreement 3 (the contingency
   reading). Both are judgement calls this build made and recorded; both are cheaper to
   overturn now than after the spend.
6. **Confirm `pip install anthropic` is available** in the run environment. `--dry-run` needs
   neither the package nor a credential; the priced run needs both.

Stop conditions S1, S5 and S6 are pre-registered cheap outs and two of them are more likely
than the design's success case. That is deliberate: a defensible null here is a product
decision worth more than a marginal positive.
