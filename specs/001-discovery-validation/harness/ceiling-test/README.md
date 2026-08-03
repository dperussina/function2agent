# E7 — the ceiling test

**Question.** Does a small, curated set of application-specific tools make an agent
measurably better at real tasks than a capable general agent that has only a shell,
network access to the same application, and the application's own OpenAPI schema?

The tools in this harness are hand-written and deliberately good. They define the
**ceiling** of the `function2agent` thesis: if ideal tools do not beat a plain shell agent
that can already reach the application, no amount of synthesis quality rescues the idea. A
negative result here is a success of the method and is reported with equal prominence
(FR-017).

Read [`PREREGISTRATION.md`](PREREGISTRATION.md) before reading any result. The thresholds
were fixed before anything ran and may not be revised (FR-006).

> This is spike code. It is not a product prototype, nothing in `src/` may import from it,
> and it is scheduled for deletion after 2026-11-30.

---

## The target application

[Mealie](https://github.com/mealie-recipes/mealie) v3.22.0, a self-hosted recipe manager
with a FastAPI backend. It was chosen because it satisfies every criterion in FR-008
without compromise: it is real software written by other people, it is data-driven, it
runs locally from a single Docker image with no paid account, its state is seedable to a
deterministic fixture, and it publishes a complete OpenAPI schema — 259 operations — so
ground truth is machine-generated rather than hand-transcribed.

The image is pinned by digest in `config.json`. The container is disposable, sits on its
own Docker network, and holds nothing shared (FR-019).

### It fails open, and that is the single most consequential thing about it

`GET /api/recipes?categories=<value>` answers **HTTP 200 with the entire unfiltered
collection** for any value it cannot resolve to a category UUID. No error, no empty
result, and nothing in the response body separating *"your filter matched everything"*
from *"your filter was discarded"*. [`fail_open_probe.py`](fail_open_probe.py) measures it
with no model in the loop and at no cost:

| `categories=` value | HTTP | `total` | |
|---|---:|---:|---|
| `906d5da2-…` (the UUID) | 200 | 7 | filtered |
| `breakfast` (the slug) | 200 | 7 | filtered |
| `Breakfast` (the display name) | 200 | **60** | **fail-open** |
| `zzzz-not-real` (nonsense) | 200 | **60** | **fail-open** |
| *(the empty string)* | 200 | **60** | **fail-open** |
| *(the parameter omitted)* | 200 | 60 | the collection size |

The parameter *works* for two of the three plausible identifier forms, which is what makes
this dangerous rather than merely wrong: an agent that gets it right once has no reason to
doubt it the next time. It is the mechanism behind the one false success in the record —
Arm B asked for `Breakfast` by name on `R1.012`, read `60` out of `jq '.total'`, and
submitted all 60 as the 7 that matched.

Arm A cannot reach the path at all. `search_recipes` never passes `category` to the query
parameter; it fetches recipe details and filters in Python through `_select` in
[`tools/mealie_tools.py`](tools/mealie_tools.py). **That immunity is a property of human
authorship at tool-writing time, not of the tool abstraction** — a tool synthesized from
`GET /api/recipes` would wrap the vulnerable parameter and inherit the defect exactly as
the shell agent did. See
[finding 014](../../findings/014-ceiling-test-replication-and-noise-floor.md).

> **Committed 2026-08-03.** This probe was originally run **by hand**, and its rows lived
> only in [`results/20260803T072053-repeats5-noisefloor-R1012/NOTES.md`](./results/20260803T072053-repeats5-noisefloor-R1012/NOTES.md).
> Finding 014 recorded the missing script as a threat to validity against SC-005: the
> display-name and UUID rows were corroborated by committed traces, but `zzzz-not-real`
> and the empty string rested on the note alone. The script asserts the recorded values
> rather than printing whatever it finds, and running it reproduced all five exactly. The
> slug row is a **sixth** case the hand run did not cover — finding 014 sources it from
> [finding 012](../../findings/012-ceiling-test-per-family.md) — and it is marked
> `in_hand_run: false` in the output and omitted by `--recorded-only`.

## Reproducing a run

```bash
cd specs/001-discovery-validation/harness/ceiling-test

export ANTHROPIC_API_KEY=...         # or: export F2A_ENV_ROOT=/path/to/dotenv/tree

./target/up.sh                       # pull the pinned image, start Mealie, build the Arm B sandbox
python3 seed/generate_plan.py        # deterministic fixture plan from the committed seed
python3 seed/apply.py                # apply it over HTTP
python3 groundtruth/extract_openapi.py   # operation inventory from the live schema
python3 tasks/validate_battery.py    # freeze expected values; self-test the adjudicator

python3 negative_control.py          # prove the checks reject unearned claims
python3 verify_write_checks.py       # prove the write checks accept genuine completions
python3 fail_open_probe.py           # the target's fail-open filter; no model, no spend
python3 runner.py --tasks smoke --arms A B --attempts 1 --max-usd 10

./target/down.sh
```

### The credential

`runner.py` and `negative_control.py` need one Anthropic key. They take it from
`ANTHROPIC_API_KEY` in the environment, and only if that is unset do they search a dotenv
tree **you name**, via `--env-root PATH` or `F2A_ENV_ROOT`. **There is no default path**
and no guessing: with neither supplied, both exit with a usage message before spending
anything. The tree is read and never written to, and `envroot.py` parses `KEY=VALUE` lines
itself — no interpolation, no shell — so a hostile dotenv file can only produce a
dictionary. This is the same convention as
[`../provider-credentials/`](../provider-credentials/).

> **Corrected 2026-08-02.** Until then both scripts carried a module constant naming a
> dotenv file inside an unrelated private repository on the author's laptop, consumed
> directly in `main()`. It leaked a private filesystem path into this repository and made
> the feature's only expensive experiment unrunnable by anyone else without editing
> source. `agent.load_api_key`, which took a file path and is why the constant existed,
> was removed in the same pass.
>
> **This changed the harness fingerprint**, because `runner.py` and `agent.py` are both
> hashed into it. Nothing about a measurement changed — the diff is credential resolution
> and a docstring — but the rule that results with different fingerprints must not be
> pooled is mechanical, so the transition is recorded here rather than left to be
> discovered.
>
> | tool surface | fingerprint after the fix | attested before |
> |---|---|---|
> | `v1` | `bc4d54f0e6e79918` | nothing to compare — no `v1` run was ever committed |
> | `v2` | `365f7debbf2c2ea5` | `f9abf1d35e94e32e`, in the last two manifests under `results/` |
>
> Both post-fix values are reproducible right now:
> `python3 -c "import runner; print(runner.harness_fingerprint('v2'))"`. The pre-fix `v2`
> value is not asserted from memory — it is the literal `harness_fingerprint` field in
> `results/20260802T173226-reprobe-perrecord-v2/manifest.json` and
> `results/20260802T173614-baseline-lookup-R1R2/manifest.json`, the two most recent
> committed runs (one Arm A, one Arm B, both `v2`). The seven earlier runs carry seven
> other fingerprints, because `tasks.json` and `config.json` are hashed in too and both
> moved during calibration.
>
> So: a fresh run of the per-family battery will report `365f7debbf2c2ea5` and will not
> match the two committed manifests. **That mismatch is this edit, not fixture drift.**

No credential is written to any config file, container, trace, log, or result artifact
(FR-020), and tool results are redacted before they reach a transcript.

`runner.py` refuses to start if the running instance no longer reproduces the frozen
fixture fingerprint. Running against a drifted fixture would void the result, so the
failure is loud rather than silent.

### Useful invocations

```bash
python3 runner.py --tasks all --arms A --attempts 1 --max-usd 8       # calibration pass
python3 runner.py --tasks all --arms A B --attempts 3 --max-usd 120   # the full battery
python3 runner.py --tasks R2.004,N.003 --arms B                       # a single-task probe
python3 runner.py --tasks R4.011 --arms A --tool-surface v1            # arm A's original 20 tools
```

`--tool-surface` selects arm A's tool set: **v1** is the twenty tools frozen on 2026-08-02 at
15:10, before the per-record task family existed; **v2** (the default) adds `aggregate_recipes`
under [preregistration](PREREGISTRATION.md) A5. Both remain runnable so the two surfaces can be
reported side by side. The surface is folded into the harness fingerprint, so results from
different surfaces cannot be pooled by accident.

## What is being compared

| | Arm A — tool-equipped | Arm B — baseline |
|---|---|---|
| Capability | 21 hand-written domain tools over the HTTP API (20 on `--tool-surface v1`) | `bash` in a container on the application's network, with `curl`, `jq`, `python3`, and the full OpenAPI schema on disk |
| Credentials | a valid API token, held by the tools | the same valid API token, in the environment |
| Turns | 40 | 120 |
| Tokens | 300,000 | 900,000 |
| Spend | $1.20 | $3.60 |
| Wall clock | 600s | 1800s |

**`config.json` is the authority for every figure in that table, not this README.** It is what
`runner.py` reads, it is hashed into the harness fingerprint, and it is stamped into every run
manifest — so a result can be checked against the budgets that produced it without trusting any
prose. Verify with `python3 -c "import json;print(json.load(open('config.json'))['budgets'])"`.

> **Corrected 2026-08-03. The table above showed the pre-A3 figures — 20 / 150,000 / $0.60 / 300s
> against 60 / 450,000 / $1.80 / 900s — and had been stale since amendment A3.1 doubled both arms.**
> The ratio statement below was never wrong, which is exactly why the staleness survived: 3× is
> true of both pairs.
>
> It did real damage anyway. Reading this table alongside a committed result led directly to the
> conclusion that **A1.1** was the operative amendment and that the *baseline* was the
> over-allowanced arm in the 6×-mismatched lookup comparison. The opposite is the case: Arm B's
> historical lookup run sat exactly at its committed budget and the tool arm's data predated the
> A3.1 raise, so the repair was to raise the tool arm. See
> [finding 013](../../findings/013-ceiling-test-budget-parity.md).
>
> | | Arm A | Arm B | authority |
> |---|---|---|---|
> | original pre-registration | 20 / 150,000 / $0.60 / 300s | 30 / 225,000 / $0.90 / 450s | [`PREREGISTRATION.md`](PREREGISTRATION.md) §What is being compared |
> | after **A1.1** | 20 / 150,000 / $0.60 / 300s | 60 / 450,000 / $1.80 / 900s | amendment A1.1 |
> | after **A3.1** (OD-04) — current | **40 / 300,000 / $1.20 / 600s** | **120 / 900,000 / $3.60 / 1800s** | `config.json` |
>
> Committed results predating A3.1 carry the earlier budgets in their own manifests, which is
> where a reader should look rather than here.

Arm B receives **3× Arm A's budget on every axis** (raised from 1.5× by amendment A1.1 after
the smoke run showed Arm B losing a task to token exhaustion rather than to error, and preserved
through A3.1's doubling of both arms). FR-005 requires the control receive at least the same
budget; the asymmetry is deliberate and favours the control, because a rigged baseline would make
the whole result worthless.

Budget exhaustion is reported as a first-class metric per arm, and an exhausted attempt is
always described as *"could not finish within budget"* rather than as getting the answer
wrong. The two mean different things for the product.

Everything else is held constant (FR-004): the same pinned model snapshot at temperature
0, the same system-prompt scaffold and `submit_answer` contract, the same 6,000-character
tool-result truncation, the same task text, and a fixture restored to a byte-identical
state before every attempt.

Arm B's sandbox has **no route to the internet**. It can reach Mealie and nothing else,
and it holds no LLM provider credentials. Both were verified directly.

## The task battery

57 tasks in `tasks/tasks.json`, committed as data rather than code, spanning the families
in `research/11-validation-plan.md` §3.2.

| Family | n | What it exercises |
|---|---:|---|
| R1 | 12 | single-hop reads |
| R2 | 15 | multi-hop reads, joins and aggregations across collections |
| R4 | 10 | composition: joins across collections plus arithmetic over the join |
| R3 | 5 | underspecified requests where the correct behaviour is to ask, not to guess |
| N | 6 | **null tasks that cannot be completed at all** |
| NM | 4 | **near-miss tasks: well-formed queries that legitimately match nothing** |
| W1 | 5 | writes, checked against the resulting application state |

The `NM` family exists to remove a shortcut. Every `N` task is impossible because a
capability or field is absent from the application, which an arm holding a closed list of
twenty tools can notice at a glance while a shell agent must prove a negative across 259
operations. In an `NM` task the tool exists, the field exists and the tag exists; the only
way to answer is to query and find nothing. Together the two families distinguish *"I
checked and there is nothing"* from *"this capability does not exist."*

Each `NM` task asks for a **corroborated pair** of counts: one that is legitimately zero and
one that is not. Asking only for the zero would let an arm pass by abstaining, which the
negative control demonstrated by answering "none" and being credited.

**Every outcome is decided by a programmatic comparison against the application's own
observable state.** No model judges any result (FR-001). Read tasks are scored against a
declarative reference query re-executed at scoring time, so an expected value can never
drift from the fixture it came from. Write tasks are scored against post-state predicates,
plus a guard that the state actually changed during the attempt, plus collateral
invariants that catch damage the task did not license.

The seeded fixture is generated from a committed PRNG seed and is not visible to either
arm in advance (FR-009).

### False success

False-success rate is a co-primary metric, not a footnote. Three detectors are
implemented: **D1**, an answer that disagrees with the oracle on a confident voluntary
termination; **D3**, state that moved in a way the task did not license; and **D4**, a
confident answer to an impossible task. D2, trace-versus-claim divergence via a recording
proxy, is not implemented in this version.

### Two adversarial checks on the battery itself

A check that only ever passes is not a check, and a check that only ever fails is no better.
Both directions are tested, neither is decorative, and each has caught a real defect.

`negative_control.py` runs an agent holding no tools at all, instructed to answer
immediately from guesswork, through the same adjudicator and the same live application
state as a real arm. Every task must come back as a failure. On its first run it caught a
write task whose post-state predicate credited an agent that had done nothing; the guard
that now prevents that exists because of that run. On its first full sweep it caught a task
whose expected value collided with a number a bluffing model reaches for, which was
re-pointed.

`verify_write_checks.py` covers the opposite direction. For every write task it performs
the genuine completion over HTTP using the Arm A tools and requires the check to **pass**,
then performs a near miss that violates exactly one stated requirement and requires the
check to **fail**. It runs no model and costs nothing.

## Layout

```
config.json            everything pinned: image digest, model snapshot, prices, budgets, seed
PREREGISTRATION.md     thresholds and kill criteria, fixed before any arm ran
envroot.py             credential resolution; no default path, exits rather than guessing
target/                up.sh, down.sh, the Arm B sandbox image
seed/                  deterministic fixture generation and application
groundtruth/           the operation inventory extracted from the live OpenAPI schema
tasks/                 tasks.json, frozen expected.json, validate_battery.py
tools/mealie_tools.py  the hand-written tools (Arm A); surfaces v1 (20) and v2 (21)
arms.py                capability blocks and the Arm B sandbox lifecycle
agent.py               the loop shared by both arms; budget enforcement; redaction
state.py               the oracle: state snapshot and declarative reference queries
checks.py              adjudication and the false-success detectors
snapshot.py            fixture snapshot and restore between write attempts
runner.py              the experiment driver
negative_control.py    proves the checks reject unearned claims
verify_write_checks.py proves the write checks accept genuine completions
fail_open_probe.py     the target's fail-open filter, probed with no model in the loop
results/<run_id>/      manifest.json, results.jsonl, traces.jsonl
results/fail-open-probe/   one file per probe run
```

Each result row records the outcome, the **terminal condition by name**, wall-clock time,
turns, the input/output/cache token split, and cost (FR-002), along with the harness
fingerprint that produced it. Results carrying different fingerprints must not be pooled.

> **Note added 2026-08-03 — one reported comparison violates the rule directly above, and it is
> recorded here rather than only in the finding.** The lookup-family cost ratio quoted as 5.0×
> pairs the tool arm from [`results/20260802T160705-recalibration/`](./results/20260802T160705-recalibration/)
> (fingerprint `35c8ef293cf0611c`, battery 1.2.0, arm-A budget 20 turns / 150,000 tokens / $0.60)
> with the shell arm from [`results/20260802T173614-baseline-lookup-R1R2/`](./results/20260802T173614-baseline-lookup-R1R2/)
> (fingerprint `f9abf1d35e94e32e`, battery 1.4.0-probe, arm-B budget 120 turns / 900,000 tokens /
> $3.60). The budget asymmetry across that pairing is therefore **6× on every axis**, not the 3×
> amendment **A1.1** committed to, because the tool-arm figures predate the OD-04 raise that doubled
> arm A. **Neither arm came near binding** — the tool arm's worst lookup attempt used 19,926 of
> 150,000 tokens and the shell arm's 127,736 of 900,000, with no exhaustion in any of the 27 — so
> the 27/27-versus-26/27 tie is not an artifact of it. The disclosure is owed regardless. See
> [finding 012](../../findings/012-ceiling-test-per-family.md) §The headline.
>
> **Resolved the same day, and the asymmetry turned out to contribute nothing.** A paired run of the
> same 27 tasks at one fingerprint and the committed budgets, plus a three-task diagnostic that
> re-ran the tool arm's v1 surface at the raised budget and reproduced its historical token counts
> to within three tokens, put budget's contribution to the cost ratio at a factor of 1.0000. The
> stale side was the tool arm, not the baseline. See
> [finding 013](../../findings/013-ceiling-test-budget-parity.md).

## Costs and ceilings

The runner enforces a per-attempt budget and a whole-run spend ceiling and **halts rather
than exceeding either** (FR-021). Every price is pinned in `config.json` at the rate in
force on the run date and is never recomputed later.
