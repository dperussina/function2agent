# Finding 022 — E7's shell baseline never inlined bulk output: every tool result in both arms was capped at 6,000 characters, and no uncapped baseline can be reconstructed from the corpus

**Date**: 2026-08-04
**Feature**: 002. Measures a harness this repository wrote —
[`specs/001-discovery-validation/harness/ceiling-test/`](../../001-discovery-validation/harness/ceiling-test/)
— and the register entries that quote it.
**User Story**: none directly. Bears on **FR-058** (the per-result output bound) and on
[`14`](../../../research/14-architecture-synthesis.md) **U-50**, **U-49** and **D-19**.
**Owner decision**: **none is taken here.** No requirement is written, no harness is changed, no
figure already published by E7 is revised. Two register premises are corrected and three counts are
restated; the conclusions those premises support are unchanged.
**Model spend**: **$0.0000.** No model was called and no credential was read. Every number below is
computed from committed artifacts by reading `tool_calls[]` out of the fourteen `traces.jsonl` files
under [`ceiling-test/results/`](../../001-discovery-validation/harness/ceiling-test/results/).
**Method**: source read first
([`config.json`](../../001-discovery-validation/harness/ceiling-test/config.json),
[`agent.py`](../../001-discovery-validation/harness/ceiling-test/agent.py),
[`runner.py`](../../001-discovery-validation/harness/ceiling-test/runner.py)), then a
re-derivation over every committed arm-B `bash` invocation. Every claim is labelled **observed**,
**derived** or **correlational**, and the three are not blended.

Numbering note: `021` was the high-water mark across both namespaces, checked by listing
`specs/*/findings/` and by ripgrep over the whole tree immediately before this file was created, and
again immediately before it was written. `022` was free both times.

## Arm names in this document

Three documents use overlapping arm letters for different arms, so this document never writes a bare
arm letter. The convention it uses, and which this finding also applies to
[`14`](../../../research/14-architecture-synthesis.md) and
[`15`](../../../research/15-nvidia-oo-agents.md):

| Written here as | Is | Called elsewhere |
|---|---|---|
| **E7 arm A (curated tools)** | the hand-written per-application tool surface | `arm: "A"` in E7's traces |
| **E7 arm B (shell)** | the shell-and-spec baseline whose cost D-19 quotes | `arm: "B"` in E7's traces |
| **E17 arm A (handle-vs-inline)** | inlined command output against a handle plus a bounded preview | `ARM A` in E17's pre-registration; **arm ②** in [`15`](../../../research/15-nvidia-oo-agents.md) §9–§10 |
| **E17 arm B (NOOA)** | NOOA at `execution_backend="inprocess"` against `"sandbox"` | `ARM B` in E17's pre-registration; **arm ①** in [`15`](../../../research/15-nvidia-oo-agents.md) §9–§10 |

**The collision is not cosmetic.** *Arm B* names E7's shell baseline — the arm the product's cost
claim rests on — and E17's NOOA arm, which E17 declined at $0.00 as unable to measure what it was
commissioned to measure. A figure moved between those two documents without translation lands on the
opposite arm from the one it was measured on.

**What was changed and what was not.** The qualified form is applied in this finding and in
[`14`](../../../research/14-architecture-synthesis.md) and
[`15`](../../../research/15-nvidia-oo-agents.md), where every surviving ①/② is now glossed against
it. **Nothing was renamed in either harness, and nothing should be.** Renaming an arm letter in
E7's `config.json` or `runner.py` would change the `arm` field in every committed trace and
invalidate a committed `harness_fingerprint`; renaming E17's `arm_a_*`/`arm_b_*` budget keys would
break a pre-registration that is the document's own tamper evidence. **The proposal for the three
out-of-scope sites is a one-line gloss at each, not a rename**: E17's `PREREGISTRATION.md` §2 and
§11 headings and its `config.json` arm keys; E17's `README.md`; and E7's `config.json`
`budgets.arm_a`/`arm_b` with `runner.py --arms A B`. The circled markers in
[`15`](../../../research/15-nvidia-oo-agents.md) are likewise kept rather than retired, because that
document also uses ① and ② for enumerated grounds, so removing them from the arm role would not
remove the ambiguity and would break every inbound citation.

---

> ## Read this first
>
> **E7's shell baseline did not inline its output. It capped it, at 6,000 characters, in both arms.**
>
> [`config.json`](../../001-discovery-validation/harness/ceiling-test/config.json) sets
> `tool_result_truncation_chars` to **6000**.
> [`runner.py`](../../001-discovery-validation/harness/ceiling-test/runner.py) passes that one value
> into the single `agent.run_attempt` call site both arms share, and
> [`agent.py`](../../001-discovery-validation/harness/ceiling-test/agent.py) truncates the result and
> **then** measures it. So the baseline behind D-19's cost advantage operated under a ceiling of
> about **1,500 tokens** per tool result, at the 4.0 bytes/token divisor E17 itself uses.
>
> Two consequences, and the second is the one with a price attached.
>
> 1. **U-50's premise is false.** That entry says E7's advantage "was taken on a shell surface that
>    already inlines its output." It was taken on a surface that truncates. **The conclusion
>    survives and is strengthened — headroom, not exposure — but the premise is what a reader uses
>    to *size* the headroom, and sized against a 1,500-token cap the headroom is far smaller than
>    sized against unbounded inlining.**
> 2. **E17's headline ratio is selected at a cap 5.3× above the only empirical precedent in this
>    repository.** E17's primary inline cap is 8,000 tokens and returns a projected median ratio of
>    **0.429**. Its own pre-registered sensitivity table's lowest rung is 2,000 tokens — already
>    above E7's 1,500 — and returns **0.958**, which its own §8.4 decision rule maps to
>    *recommend against — the mechanism costs turns and complexity and buys nothing*.
>
> **And the pre-truncation size of any result is recorded nowhere.** `result_chars` is `len(out)`
> *after* truncation. **No uncapped baseline can ever be reconstructed from this corpus.** That is
> permanent, and it is the most consequential secondary claim here.

## The direct answer

**Observed.** Three source facts, each checkable by reading one file.

| Fact | Where | What it says |
|---|---|---|
| `"tool_result_truncation_chars": 6000` | `config.json` line 55 | one cap, declared once |
| `truncation_chars=cfg["tool_result_truncation_chars"]` | `runner.py` line 214 | one call site, reached by both arms; the arm branch above it chooses the budget, the tool set and the sandbox, and does not touch the cap |
| `if len(out) > truncation_chars: out = out[:truncation_chars] + f"\n[truncated at {truncation_chars} characters]"`, then `"result_chars": len(out)` | `agent.py` lines 279–285 | truncate, **then** measure |

**Derived.** The elision marker is 31 characters, so a truncated result records
`result_chars` of exactly **6031**. Across all 2,165 committed tool results in both arms, the only
distinct values at or above 5,900 are **6031** and nothing else; the largest untruncated result
anywhere is **5665**. At the 4.0 bytes/token divisor E17 pins in its own `config.json`, the cap is
**1,508 tokens** including the marker.

**So the corpus has one bit per result — capped or not — and no magnitude behind it.** A reader
cannot ask E7 how large its outputs would have been, now or ever.

## What this corrects

### 1. U-50's premise, in two documents

[`14`](../../../research/14-architecture-synthesis.md) §5.2 `U-50` and
[`15`](../../../research/15-nvidia-oo-agents.md) §9 each state that E7's cost advantage was measured
on an inlining surface. Both are corrected in place, and in both the **conclusion is left standing**:
the open quantity is headroom above a measured baseline, never exposure to it. What changes is the
sizing. The remaining prize on the token limb is the gap between a **1,500-token cap** and E17's
**400-token** handle preview, not the gap between a preview and an unbounded result.

### 2. Three counts that share one defect, and the defect is U-49's

The counts published in [`15`](../../../research/15-nvidia-oo-agents.md) and carried into
`U-50` are *36 of 109 arm-B task-attempts spill output to a named file*, *70 of 998 arm-B commands
write one*, and *21 of the 70 immediately `cat` the whole file back*.

**Every published figure reproduces to the digit.** Re-derived independently from
`tool_calls[].args.command`: 109 arm-B attempts, 998 arm-B `bash` invocations, 70 commands writing a
named file across 36 attempts, 31 attempts later reading one back. Nothing upstream is wrong. **The
defect is what the population contains.**

| Population | Published | Honest | What the difference is |
|---|---|---|---|
| attempts that spill command output to a file | 36 of 109 | **32 of 109** | 4 attempts wrote only a heredoc script |
| commands that spill command output to a file | 70 of 998 | **45 of 998** | 25 commands are `cat > /work/x.py << 'EOF'` — the model typing a file, not capturing output |
| spills immediately read back whole | 21 of the 70 | **21 of 45** | the numerator is computed over output-spills; the published denominator is padded with 25 heredocs that could not have entered it |

**The heredoc exclusion is exact, not a judgement call.** All 25 are a `cat > path << 'EOF'` form
whose sole redirection target is the heredoc's own sink, and **none of the 21 read-backs comes from
one** — the two populations are disjoint by construction, which is precisely why the padded
denominator could never have produced the numerator.

**"21 of the 70" is Rule 7's defect, third instance.** A numerator drawn from one population and a
denominator from a larger one, written as one measurement. Restated over one population the rate is
21 of 45 rather than 21 of 70, and the honest figure is the *less* flattering one on the reading
that matters: nearly half of the spills, not three in ten, hand the whole file straight back.

*Definitions, so the counts are reproducible.* A command **writes a named file** if it redirects
(`>`, `>>`, `1>`, `2>`), pipes to `tee`, or passes `curl -o`/`--output` to a target that is a path
rather than a comparison operand — `/dev/null` and descriptor dups excluded. Applying that rule
without the operand filter yields 72 rather than 70; two `awk '$1 >= 2 {print}'` clauses are the
difference, and excluding them is what reproduces the published figure. A write is
**heredoc-script-only** when every target it writes is the sink of a heredoc on the same line. A
spill is **read back whole** when the same command or the next command in the same attempt runs
`cat <target>` with nothing piped after it; allowing a filter after the `cat` — `| jq`, `| head` —
raises the count from 21 to 32, and the unfiltered reading is the one that matches the published
sentence.

### 3. The pooled 109 crosses seven harness fingerprints, and the pooled rate describes no published figure

**Observed.** `runner.py`'s own `harness_fingerprint` docstring says results with different
fingerprints "must not be pooled." The 109 arm-B attempts carry **seven** distinct fingerprints.
They include **13 smoke attempts** backing no published figure and **25 noise-floor attempts** that
are 5 tasks weighted 5×.

| Run | arm-B attempts | spilling | rate | backs |
|---|---:|---:|---:|---|
| `20260802T151714-smoke` | 5 | 0 | 0% | nothing published |
| `20260802T152825-smoke2` | 5 | 1 | 20% | nothing published |
| `20260802T163319-bias-probe` | 10 | 8 | 80% | the join figure |
| `20260802T164929-bias-probe-perrecord` | 4 | 4 | 100% | the per-record figure |
| `20260802T165903-ambiguity-recheck` | 3 | 2 | 67% | three re-measured join tasks |
| `20260802T173614-baseline-lookup-R1R2` | 27 | 6 | 22% | the historical lookup figure |
| `20260803T064400-smoke-paired-precheck` | 2 | 0 | 0% | nothing published |
| `20260803T064550-paired-lookup-R1R2-A3budgets` | 27 | 5 | 19% | the paired **4.366×** |
| `20260803T071942-smoke-precheck-gapfill` | 1 | 0 | 0% | nothing published |
| `20260803T072053-repeats5-noisefloor-R1012` | 25 | 6 | 24% | the within-session noise floor |

**Across the six runs that back a published figure the spill rate spans 19% to 100% — a five-fold
range.** So **the pooled rate characterises no quoted cost multiplier**, and it must not be written
as though it did. The run behind the corpus's cleanest cost figure, the paired **4.366×**, has the
*lowest* spill rate of the six.

## The secondary claims, each labelled

### Pre-truncation output size is recorded nowhere — permanent

**Observed.** `result_chars` is assigned `len(out)` after the truncating branch. There is no
`raw_chars`, no pre-truncation length, and the transcript stores the same truncated string. The only
value at or above 5,900 anywhere in the corpus is **6031**.

**Consequence, and it is the most consequential thing in this document.** Every question of the form
*what would E7's shell arm have cost with no cap* is unanswerable from the committed artifacts, and
re-asking it needs a new run at a new price. Any future harness in this repository that truncates a
tool result should record the pre-truncation size beside the admitted size — which is the obligation
**FR-058** already places on the product's own `tool_call` span, arrived at independently.

### The cap was nominally symmetric and in practice fell on the shell arm

**Observed**, on the paired run behind **4.366×**
(`20260803T064550-paired-lookup-R1R2-A3budgets`, one run, one fingerprint, 27 tasks per arm):

| | attempts | tool results | results at the cap | attempts hitting the cap | largest result |
|---|---:|---:|---:|---:|---:|
| E7 arm A (curated tools) | 27 | 84 | 0 | 0 | 3,181 chars |
| E7 arm B (shell) | 27 | 229 | 25 | 18 | 6,031 chars |

A curated tool returns a shaped answer and never came within half the cap. A shell command returns
whatever the command printed. **The identical rule therefore bound one arm and not the other**,
which means the cap is not a neutral experimental control: it is a treatment that applies to the
baseline. Corpus-wide the asymmetry is milder but points the same way — 26 of 1,167 arm-A results at
the cap against 128 of 998 arm-B results.

### Bounded headroom — these are ceilings, not estimates

**Derived**, under one stated assumption and one stated limit.

*The assumption that makes them ceilings:* **every output-capture spill is charged as though the
command would otherwise have returned a result filling the cap exactly** — 1,508 tokens. Most would
not have. The true saving is therefore at or below each figure.

*The charging model:* `agent.py` increments `turns` once per API request, and a result produced at
turn *k* sits in the request for turns *k+1* through the last, so it is billed *turns − k* times at
$3.00/Mtok input. **There is no prompt caching anywhere in this corpus** — `cache_read` and
`cache_write` are **0** in every arm-B row and every arm-A row — which is exactly why a result is
charged in full on every turn it is re-sent.

| Run | arm-B spend | spills | headroom already captured, at most | share of arm-B cost |
|---|---:|---:|---:|---:|
| B-only lookup, `20260802T173614` | $4.5495 | 10 | $0.2262 | **≤4.97%** |
| paired lookup, `20260803T064550` (4.366×) | $4.3109 | 6 | $0.1764 | **≤4.09%** |
| join, `20260802T163319` | $3.6943 | 15 | $0.6650 | **≤18.00%** |
| per-record, `20260802T164929` | $1.0584 | 4 | $0.0950 | **≤8.98%** |

**A slightly larger set of ceilings — 5.3%, 4.4%, 19.6%, 10.1% — is in circulation for these same
four runs, and a reader who meets both should know why they differ.** The figures above are this
document's own derivation and are the ones it stands behind. They are lower because a spilled result
is charged for `turns − k` re-sends counted from the turn it was produced on, and because the spill
population is the corrected output-capture one rather than the padded one. The two sets agree on
sign, order and magnitude, and neither changes any conclusion; where they disagree, use these.

*The limit:* **these bound a token quantity and cannot model a trajectory change.** An agent that
never spilled would not have run the same commands in the same order; it would have been truncated
more often, recovered differently, and possibly failed. Nothing here prices that.

### Tool-result content dominates the shell arm's bill, and most of it sits at the cap

**Derived**, same charging model. Counting every tool result at its recorded `result_chars` and
billing it once per re-send:

| Run | tool-result share of arm-B input tokens | of that, share sitting at the cap |
|---|---:|---:|
| B-only lookup | 46.2% | 61.3% |
| paired lookup (4.366×) | 42.9% | 54.8% |
| join | 46.4% | 51.5% |
| per-record | 42.5% | 41.9% |
| all 109 arm-B attempts | 45.1% | 54.4% |

**A wider pair of ranges — 49–53% and 55–61% — is in circulation for these two columns.** The
difference is the same charging convention as above (re-sends counted from the producing turn) plus
the treatment of the system prompt and the task statement, which are counted here as non-tool input.
The reading is unchanged either way and the second column's spread is the wider of the two.

**So bulk output really does dominate the shell arm's bill** — roughly two fifths to a half of every
input token it paid for, and about half of that already pressed flat against the ceiling. **What the
mechanism could still buy is therefore real and it is bounded**: the distance from a ~1,500-token cap
to a ~400-token preview, not the distance from a preview to an unbounded result.

### Correlational only — the model appears to spill *after* being burned, not to economise

**Correlational. This is not a causal claim and no experiment here could make it one.**

**28 of the 32 spilling attempts had already received a capped result earlier in the same attempt**,
before their first spill. The four that had not are
`R4.013`/`bias-probe-perrecord`, `R2.003`/`baseline-lookup-R1R2` and two repeats of
`R2.014`/`noisefloor`.

**The base rate is high and must be stated with it, or the correlation reads as stronger than it
is:** 50 of the 77 non-spilling attempts also hit the cap at some point. So hitting the cap is
common; spilling *without* having hit it is rare.

**Why it matters for transfer.** If spilling is a response to truncation rather than proactive
economising, **the spill rate is a function of the cap and does not transfer to an uncapped
surface** — and it does not transfer to a differently-capped one either. That bears directly on
whether any of E7's spill behaviour predicts what v1's agent will do under **FR-058**, and the
honest answer is that it does not, at any cap other than 6,000 characters.

## What this does not claim

- **It does not revise any E7 cost figure.** 4.366×, 2.20× and 5.06× are unchanged; nothing here
  recomputes a ratio.
- **It does not reopen U-50's direction.** Headroom above a measured baseline, never exposure to it.
  Only the size moves, and it moves down.
- **It does not say E7 was wrong to cap.** Capping is what every real command-execution surface
  does, and E17's own `_cap_note` says an uncapped arm is a bug rather than a default. What was
  wrong was two register entries describing the capped surface as an inlining one.
- **It does not price E17.** 0.429 and 0.958 are projections from a dry run in which no model was
  called. This finding observes only *where E7's empirical cap sits relative to the settings those
  projections were taken at*, which is below all three.
- **It states no requirement.** **FR-058** was written independently and argues its bound from the
  context window and the re-send arithmetic. This finding supplies the empirical precedent that
  argument did not have — E7 produced the corpus's headline cost figures at a ~1,500-token cap,
  inside the "low thousands" operating region FR-058 names and far below the 10,000-token ceiling
  it permits — and it is corroboration, not a derivation.

## Reproduction

`$0.0000`, standard library only, no network, no model call. Read
`tool_calls[]` from the fourteen `traces.jsonl` files under
[`ceiling-test/results/`](../../001-discovery-validation/harness/ceiling-test/results/), key each
attempt by `(run directory, task_id, attempt)` — `attempt` alone is not unique within a run, and
keying on it collapses 109 attempts to 14 — and apply the write, heredoc and read-back definitions
given above. The cap facts need no script: they are three lines of committed source.

## What remains unverified

- **Whether any spilled command would in fact have filled the cap.** Unknowable, by the first
  secondary claim. Every headroom figure above is a ceiling for exactly this reason.
- **Whether the 4.0 bytes/token divisor holds for these payloads.** It is E17's estimation divisor,
  reused so the two sit on one basis; it is not a tokenizer, and JSON-heavy tool output may
  tokenize worse than 4.0 bytes/token, which would make the 1,508-token figure an underestimate.
- **Whether E7 arm A's zero cap-hits on the paired run generalises.** It is 27 attempts on two task
  families with a hand-written tool surface. Corpus-wide arm A hit the cap 26 times.
- **Whether truncation changed any E7 outcome.** No attempt was re-run without the cap and none can
  be, so the question of whether a task failed *because* of truncation is open and closed to this
  corpus at once.
