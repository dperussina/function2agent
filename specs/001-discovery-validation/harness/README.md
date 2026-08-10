# Harnesses for feature 001, discovery validation

One directory per experiment. Each holds the code that produced a finding's numbers,
plus whatever raw output survived, plus a README that says what it measures, how to run
it, and — importantly — what it *cannot* reproduce.

These exist because of **SC-005**: *an engineer who did not build the harness can
reproduce any reported number from the committed configuration without consulting the
author.* The bar is reproduction by a stranger, not by the person who ran it.

> **The harness is a durable measurement asset; the arms are disposable.** Neither is
> product code, nothing under `src/` may import from either, and no part of either may
> be promoted into the product without a from-scratch reimplementation under its own
> specification.

## Index

**Eight experiments ran and produced a finding** — E1, E2, E4, E5, E6, E7, E14, E15. E3
was absorbed into E2 and never ran as its own experiment; E8–E13 never ran at all. Those
eight, plus the credential probe from outside the ladder, are the nine positions below.
**Every one now has a directory. Two of them cannot reproduce their numbers for anyone,
ever**, and say so at the top of their own README.

| Directory | Experiment | Finding | Model spend | Provenance | Numbers reproducible |
|---|---|---|---|---|---|
| [`structure-recovery`](./structure-recovery/) | E1 — route extraction precision | [001](../findings/001-structure-recovery.md) | $0.00 | **recovered from the session transcript 2026-08-02** | **no — private target** |
| [`recall-adk-fastapi`](./recall-adk-fastapi/) | E2 — route extraction recall | [004](../findings/004-recall-against-authoritative-key.md) | $0.00 | committed at the time | yes |
| [`contract-extraction`](./contract-extraction/) | E4 — contract extraction | [007](../findings/007-contract-extraction.md) | $0.00 | committed at the time | primary yes; TypeScript column needs your own index |
| [`runtime-provider-agnosticism`](./runtime-provider-agnosticism/) | E5 — runtime provider agnosticism | [003](../findings/003-runtime-provider-agnosticism.md) | ≈$0.09 | **recovered from `/tmp` 2026-08-02** | most; see its Gaps |
| [`graph-loop-primitives`](./graph-loop-primitives/) | E6 — graph-loop primitives | [006](../findings/006-graph-loop-primitives.md) | $0.0003 | **recovered from `/tmp` 2026-08-02** | most; see its Gaps |
| [`ceiling-test`](./ceiling-test/) | E7 — the ceiling test | [005](../findings/005-ceiling-test-harness.md), [008](../findings/008-ceiling-test-calibration.md), [009](../findings/009-ceiling-test.md), [012](../findings/012-ceiling-test-per-family.md), [013](../findings/013-ceiling-test-budget-parity.md), [014](../findings/014-ceiling-test-replication-and-noise-floor.md) | ~~$24.73 (spend-incurred; **$24.67** artifact-exact)~~ **$35.0817** artifact-exact over six sessions; $35.1412 spend-incurred — [derivation](#the-ceiling-test-row-updated-2026-08-03) | committed at the time | yes — [see below](#the-ceiling-test-row-updated-2026-08-03) |
| [`deployment-reachability`](./deployment-reachability/) | E14 — deployment reachability | [010](../findings/010-deployment-reachability.md) | $0.00 | committed at the time | yes |
| [`reachability-without-schema`](./reachability-without-schema/) | E15 — reachability without a published schema | [011](../findings/011-reachability-without-schema.md) | $0.00 | committed at the time | yes |
| [`provider-credentials`](./provider-credentials/) | (outside the ladder) — live credential probe | [002](../findings/002-provider-credentials.md) | $0.00 | **recovered from `/tmp` 2026-08-02** | **no — one person's credentials** |
| [`provider-sdk-roundtrip`](./provider-sdk-roundtrip/) | E16 — opaque-state round-trip through each vendor's own SDK | [016](../findings/016-provider-sdk-roundtrip.md) | 25,214 tokens; **no dollar total** — one arm measured at $0.001860, [see below](#the-e16-row-added-2026-08-03) | committed at the time | yes — with your own credentials |
| [`pass-by-reference`](./pass-by-reference/) | E17 — inlined command output vs a bounded preview plus a filesystem handle | none yet — **pre-registered, not run** | **$0.00** — no model has been called | committed at the time | yes for everything committed; the paid arm does not exist |
| [`slug-differential`](./slug-differential/) | (outside the ladder) — `slugify` against GitHub's own renderer | none; the result is read at `slugify`'s docstring and [`tools/README.md`](../../../tools/README.md)'s `link-anchor` row | **$0.00** — no model is called | **rebuilt from prose 2026-08-10 and then run against the live renderer** | yes — with network egress and a GitHub token |

`runtime-provider-agnosticism` and `graph-loop-primitives` are the harnesses behind
**OD-01** (adopt Google ADK for graph execution, build our own safety layer) and **OD-02**
(do not use the Claude Agent SDK as the coding-node executor) — the pair that decides the
runtime substrate. They were written up as *not committed* by finding 006 §Reproduction
and by [`VERDICT.md`](../VERDICT.md); their scripts survived in `/tmp`, are committed
here, and **both documents were corrected on 2026-08-02** rather than left stale.

## The position count above is stale, and one directory besides the new one is missing from the table

The counts in the index paragraph — eight experiments, nine positions, ten after E16 — are
superseded, and each was correct when written. `ls` now returns **thirteen** directories beside
this file while the table carries **twelve** rows.

The one row that is owed rather than added here is [`verifier-vs-judge`](./verifier-vs-judge/),
E8, which is a committed directory absent from the table. It is named rather than filled in:
its finding, its spend and its provenance are E8's to state, and a row assembled by someone who
had not read the experiment is the plausible-looking substitute this tree refuses elsewhere on
the same page. `slug-differential` sits outside the experiment ladder in the same way
`provider-credentials` does, so it adds a position without adding an experiment.

**Every claim in this file about how many of something the tree holds has now gone stale at
least once**, which is the case the rule at
[`tools/README.md` § When a figure may be a live total](../../../tools/README.md#when-a-figure-may-be-a-live-total-and-when-it-must-be-dated)
calls the first of its two ungateable kinds: nothing counts these directories, so a count of
them belongs in a dated sentence rather than in a standing one.

## The `ceiling-test` row, updated 2026-08-03

Two sessions ran after the row above was last written —
[finding 013](../findings/013-ceiling-test-budget-parity.md) and
[finding 014](../findings/014-ceiling-test-replication-and-noise-floor.md), both on
2026-08-03 — and a probe that finding 014 named as missing is now committed. The row
was **superseded**, not wrong: every figure in it was correct for the four sessions it
covered.

### The spend, derived rather than transcribed

Both accounting bases from [`VERDICT.md`](../VERDICT.md) §6 still apply and both still
differ by the same six cents, so both are carried:

| basis | four sessions | + finding 013 | + finding 014 | six sessions |
|---|---:|---:|---:|---:|
| **artifact-exact** — every `cost_usd` in `results/*/results.jsonl` plus every `spent_usd` in `results/negative-control/*.json` | $24.6705 | $5.5168 | $4.8944 | **$35.0817** |
| **spend-incurred** — the sum of the per-session figures the findings report | $24.73 | $5.5168 | $4.8944 | $35.1412 ($24.73 + $5.5168 + $4.8944) |

Recompute the artifact-exact figure from the committed rows without trusting this table:

```bash
cd specs/001-discovery-validation/harness/ceiling-test
python3 - <<'PY'
import glob, json
rows = sum(json.loads(l)["cost_usd"] for f in glob.glob("results/*/results.jsonl") for l in open(f))
neg  = sum(json.load(open(f))["spent_usd"] for f in glob.glob("results/negative-control/*.json"))
print(f"per-attempt {rows:.6f} + negative-control {neg:.6f} = {rows + neg:.6f}")
PY
```

It prints `per-attempt 34.227372 + negative-control 0.854300 = 35.081672`, which is
finding 013's decomposition to the cent and beyond. The two new sessions are
artifact-exact on both bases — the committed rows sum to $5.516817 and $4.894404, which
is what findings 013 and 014 report — so **the whole ~$0.06 gap between the bases is
still the session-1 negative-control spend that was never committed**, exactly as
[`VERDICT.md`](../VERDICT.md) §6 predicted it would carry through. Nothing new has been
added to it.

> `VERDICT.md` and [`plan.md`](../plan.md) still quote the four-session $24.73 / $24.67
> as E7's total, and [`README.md`](../../../README.md) still carries the program total
> $24.82 built from it. Those are outside this file and are **not** edited here; the
> figures above are what a reader should reconcile them against.

### The fail-open probe is now committed, and it runs

[Finding 014](../findings/014-ceiling-test-replication-and-noise-floor.md) §Threats to
validity recorded that its strongest result — Mealie answering HTTP 200 with the entire
unfiltered collection for any `categories` value it cannot resolve — rested on a probe
**run by hand**, surviving only as a five-row table in
[`results/20260803T072053-repeats5-noisefloor-R1012/NOTES.md`](./ceiling-test/results/20260803T072053-repeats5-noisefloor-R1012/NOTES.md).
Two of those rows were corroborated by committed traces; the nonsense value and the
empty string rested on the note alone, so against SC-005 a stranger could not reproduce
them without rewriting the probe from prose.

[`ceiling-test/fail_open_probe.py`](./ceiling-test/fail_open_probe.py) closes that gap.
It was **executed on 2026-08-03 against the live fixture and reproduced all five
recorded rows exactly**, including the two that had no independent corroboration; output
is at [`ceiling-test/results/fail-open-probe/`](./ceiling-test/results/fail-open-probe/).
It runs no model, costs nothing, issues only `GET` requests, and refuses to report
anything if the instance drifts from the pinned application version or the frozen
fixture fingerprint. It probes a **sixth** case that the hand run did not — the category
slug, which finding 014's published table carries from
[finding 012](../findings/012-ceiling-test-per-family.md) — flagged `in_hand_run: false`
in its output and suppressed by `--recorded-only`, so the two provenances never merge.

This is why the row's **Numbers reproducible** column can still read *yes*. Between
finding 014 being written and this script being committed it could not: that finding
names the gap in its own threats section, and the column was overstated for as long as
the gap was open.

## The E16 row, added 2026-08-03

E16 ran after the index above was written, so the "Eight experiments ran" count at the top of
this file is now **nine**, and the nine positions are ten.

Its **Model spend** cell is the only one in the table that is not a dollar figure, and that is
deliberate rather than an omission. Tokens are measured exactly, from each provider's own usage
field. Converting them to dollars needs a per-provider price table, and the per-provider cost
table is one of the nine capabilities **U-48** records as having **no owner** — it was supplied
by the dependency **OD-15** removed. Hardcoding four price lists into a harness so that a
spend column could look like the others would manufacture exactly the unsourced number this
tree refuses to carry.

One provider reports a server-side cost: xAI's usage proto carries `cost_in_usd_ticks`, and
**the xAI arm's three turns total $0.001860**. That figure is the provider's, not ours, and it
covers one of eight artifacts — the xAI spend inside the negative control is not captured,
because cost extraction was added to the arm and not the control. The other three providers
report tokens only, and a null in that harness's artifacts means *not reported*, never *zero*.

The self-imposed ceiling was **$2.00**. Two of E16's eight artifacts — the model-list probe and
the static field count — run no model at all, in the same spirit as finding 006's twelve
model-free arms.

E16 also uses its **own** virtualenv at `/tmp/f2a-probe-e16` rather than the shared
`/tmp/f2a-probe-runtime`, so that installing four vendor SDKs could not disturb the pinned
`google-adk` / `litellm` environment that findings 003 and 006 depend on. It is therefore
absent from the [Scratch directories](#scratch-directories) table's shared-venv row by design.

## What "recovered" means, and what it does not

**Recovered** means the committed script is the one that ran, not a rewrite from the
finding's prose. ~~Nothing here is a reconstruction except one clearly-marked file,
`runtime-provider-agnosticism/count_reasoning_fields.py`, which says so in its own
docstring and in its harness README.~~

> **Superseded 2026-08-03 — there are now two, and they are not equally trustworthy.**
> The sentence was true when written; a second file has since been added. It is a claim
> about the whole tree, so it needs re-checking whenever anything is added to one.
>
> | file | what it rebuilds | can its numbers be checked against it? |
> |---|---|---|
> | `runtime-provider-agnosticism/count_reasoning_fields.py` | a counting *rule* that was never recorded | **No.** The rule was inferred by fitting it to the four integers it is meant to reproduce. One rule matching four integers with no free parameters is strong evidence and is not the same as holding the original script — its [README](./runtime-provider-agnosticism/README.md#the-one-reconstruction-and-how-far-to-trust-it) prints all three candidate rules so the choice stays visible |
> | `ceiling-test/fail_open_probe.py` | a probe whose *procedure* was recorded in prose but whose script was not | **Yes, and it was.** The recorded values are asserted in the source rather than merely printed, and running it against the live fixture reproduced all five independently. A row that disagreed would have exited non-zero |
>
> The difference is whether the reconstruction can corroborate the numbers or only
> restate them. Both are marked in their own docstrings; only the second is evidence.

Recovery is not the same as a complete run record. Each recovered harness carries a
**Gaps** section listing claims in its finding that it does **not** reproduce — probes
whose scripts did not survive, five-run repeats done by hand, source searches whose
exact form was not recorded. Those are left open and named rather than filled with
plausible-looking substitutes.

> A harness that looks reproducible but silently differs from what actually ran is
> worse than an honest gap. Where a method was not recorded, this tree says so instead
> of guessing.

## The two positions that will never reproduce, and why one of them is still here

[Finding 001](../findings/001-structure-recovery.md) (E1) is read-only SQL against a
pre-existing analysis index of a real, private, production monorepo that is deliberately
*not vendored and not copied*. [Finding 002](../findings/002-provider-credentials.md)
reports which of one person's specific credentials authenticate. Neither is a
lost-artifact problem and neither has a fix: a third party has no target in the first
case and different credentials in the second.

**E1's queries are committed anyway, as of 2026-08-02.** The reasoning, in full, is in
[`structure-recovery/README.md`](./structure-recovery/README.md); in short, finding 001
carried two claims — a general HTTP-verb filter and a 58% handler-ambiguity result — that
were retracted only after E2 independently re-measured them, and **both were legible in
the SQL.** Neither retraction needed a second experiment; both needed someone to read the
query. An inspectable method with unreproducible numbers is strictly better than neither,
and this is the experiment that demonstrates it.

That is a decision about *this* case, not a general licence. What justifies it is that
the method is where the error was, and reading it would have caught the error.

## Credential handling, common to every harness

No harness prints, logs, returns, or writes a credential value, and no committed result
artifact contains one (FR-020). **No harness contains an absolute path into anyone's
filesystem**, and none has a default that points at one — the three that used to are
listed under [§Private paths, removed](#private-paths-removed).

Three harnesses read provider credentials. **All take the dotenv search root as a
required parameter with no default** and exit rather than guess:

```bash
export F2A_ENV_ROOT=/path/to/tree           # required
export F2A_GEMINI_VAR=GEMINI_API_KEY_2      # optional, see finding 002
```

The tree is read and never written to. `F2A_GEMINI_VAR` exists because finding 002
found that the canonically-named `GEMINI_API_KEY` was one of ten dead credentials while
the working one lived under a different name in a different file — **a generated stack
cannot assume canonical credential names, and neither do these harnesses.**

Where a probe must tell two credentials apart, it uses a truncated SHA-256 fingerprint
as the handle, so a table can report "ten of these are dead and this one works" without
any of the eleven appearing anywhere.

## Private paths, removed

Until 2026-08-02 three harnesses named an absolute path inside an unrelated private
repository on the author's laptop. Two consequences, both bad: a private filesystem path
was committed to a public tree, and **the most expensive experiment in the feature
($24.73) could not be run by anyone else without editing its source.** All three are
fixed, and no absolute path into a home directory remains anywhere under `harness/`.

> $24.73 is what that experiment had cost **on the date of the fix**, which is the figure
> the sentence is about. It has since run twice more and stands at **$35.0817**
> artifact-exact; see [above](#the-ceiling-test-row-updated-2026-08-03).

| Was | Now |
|---|---|
| `ceiling-test/runner.py`, `negative_control.py` — a module constant naming a private `.env` | `--env-root` / `F2A_ENV_ROOT`, no default, via [`ceiling-test/envroot.py`](./ceiling-test/envroot.py) |
| `contract-extraction/run.sh` — `TS_DB` defaulting to a private codegraph index | `TS_DB` with no default; unset skips the secondary measurement and prints how to supply one |

Two harnesses take a path to something you must supply, which is a different thing —
`TS_DB` for `contract-extraction`'s TypeScript column, and `CODEGRAPH_DB` for
`structure-recovery`. Both are required, neither has a default, and both fail with a
usage message. `structure-recovery` additionally opens its database through a
`file:…?mode=ro` URI, since it is meant to be pointed at somebody's real index.

Removing the constant changed `ceiling-test`'s harness fingerprint. The old and new
values for both tool surfaces are tabulated in
[`ceiling-test/README.md`](./ceiling-test/README.md#the-credential) so that committed
results remain checkable against the code that produced them.

## Scratch directories

Harnesses write to `/tmp` and never into the repository or into `examples/` (FR-018).

| Variable | Default | Used by |
|---|---|---|
| `F2A_PROBE_DIR` | `/tmp/f2a-probe-runtime` | `runtime-provider-agnosticism`, `graph-loop-primitives` (shared virtualenv, session databases, side-effect logs) |
| `F2A_PYTHON` | `python3` | `provider-sdk-roundtrip` — selects the interpreter. Its committed results used a **separate** virtualenv at `/tmp/f2a-probe-e16`, deliberately not the shared one; see [the E16 row](#the-e16-row-added-2026-08-03) |
| — | `/tmp/f2a-recall` | `recall-adk-fastapi`, `contract-extraction`, `deployment-reachability` (shared index and virtualenv; passed as `run.sh`'s first argument) |

`runtime-provider-agnosticism` and `graph-loop-primitives` share one virtualenv, exactly
as the original probes did — finding 006's method note records the environment as
"reused rather than rebuilt." Its pins live in
[`runtime-provider-agnosticism/requirements.txt`](./runtime-provider-agnosticism/requirements.txt),
which carries a **macOS installation hazard worth reading before you touch the LiteLLM
version.**

## Results directories

`results/` holds committed raw output. It contains only real recorded output; where a
finding quotes a number whose raw output is gone, the harness README says so rather than
regenerating something that would look equivalent.

Three of the four recovered harnesses have **no `results/` directory at all** —
`provider-credentials`, `runtime-provider-agnosticism`, and `structure-recovery` — because
their probes were run interactively and their stdout was never captured. The fourth,
`graph-loop-primitives`, has three genuine surviving artifacts and a
[`PROVENANCE.md`](./graph-loop-primitives/results/PROVENANCE.md) explaining exactly what
they are and what is missing alongside them.

`recall-adk-fastapi` kept its two scored outputs at its top level until 2026-08-02; they
are now at [`recall-adk-fastapi/results/`](./recall-adk-fastapi/results/) like everything
else. The files are unchanged — they were moved, not regenerated.
