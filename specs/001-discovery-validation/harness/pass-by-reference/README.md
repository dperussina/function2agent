# E17 — pass by reference on a command-execution surface

**This experiment has not run. No model has been called. Spend to date: $0.00.**
Everything committed here is a pre-registration, a projection built from local
measurement, and three probes that cost nothing. [`PREREGISTRATION.md`](./PREREGISTRATION.md)
is the document; this file says how to re-run what exists and what it does and does
not establish.

> **SPIKE.** Not product code. Nothing under `src/` may import from this directory,
> and no part of it may be promoted into the product without a from-scratch
> reimplementation under its own specification. Delete after 2026-11-30.

## The question

NVIDIA's OO Agents reports roughly half the tokens of its comparison harnesses and
credits *pass by reference*. Our v1 cannot use that mechanism — **FR-004** returns
bytes across an enforcement boundary — but the economic benefit is reachable another
way: keep the bulk out of the transcript, refer to it by name. No requirement governs
it, so the implicit default is to inline everything a command prints, and that
default sits on the product's cost claim (**OD-09**).

## What is here

| file | what it does | cost to run |
|---|---|---|
| [`PREREGISTRATION.md`](./PREREGISTRATION.md) | the design, the calibration band, the binding decision rule, the budget | — |
| `config.json` | every pinned constant, each with the reason it holds that value | — |
| `corpus.py` | generates the target tree deterministically from seed `20260804` | $0.00 |
| `tasks.py` | 21 tasks: shell plan **and** an independent Python checker for each | $0.00 |
| `measure.py` | generates, runs every plan, measures the bytes, cross-checks every answer | $0.00 |
| `tokens.py` | the token-accounting model, pure functions | — |
| `analysis.py` | calibration gate, exclusion accounting, the two limbs, the decision rule | — |
| `cost.py` | the projection, arithmetic printed | $0.00 |
| `picklability_census.py` | arm B′: which result shapes cross a fork boundary | $0.00 |
| `kernel_probe.py` | Landlock, seccomp user-notification, cgroup v2 — live syscall probes | $0.00 |
| `selftest.py` | 209 self-tests | $0.00 |

There is no `runner.py`. The arm that would spend money is not written, because
writing it before authorization is how a budget gets spent by accident.

## Running it

```bash
cd specs/001-discovery-validation/harness/pass-by-reference

python3 selftest.py                 # 209 tests, ~5s
python3 measure.py                  # generate + measure + cross-check the battery
python3 cost.py --verbose           # the projection, with per-call accumulation
python3 picklability_census.py      # arm B'
```

The kernel probe needs Linux, so on macOS it runs in a container:

```bash
docker run --rm -v "$PWD":/w -w /w python:3.12-slim python3 /w/kernel_probe.py --json
```

`python3 kernel_probe.py --selftest` runs the probe's own structural checks anywhere,
including on macOS, where it correctly refuses to report a kernel verdict.

## What the dry run found — four defects, before any money

This is the point of the exercise, so the defects are recorded rather than quietly
fixed.

1. **The inline arm projected past the context window.** Uncapped, the measured
   battery puts T02's inline transcript at 726,766 input tokens against a 200,000
   window. The comparison would have been a completed handle run against an inline run
   that cannot physically exist, and it produced a 0.030 token ratio — a 97% "saving"
   that is entirely an artefact. Both arms are now capped and the honest contrast is
   *bytes gone* versus *bytes still reachable*.
2. **The config asserted a corpus size the generator never produced.** It declared a
   6 MiB target against an actual 4,228,698 bytes. Now pinned to the produced value and
   asserted by `selftest.py`, which is also how the second change to the generator was
   caught.
3. **The negative control carried a treatment effect.** T14/T16/T17 were labelled
   controls because no step passed the 4,096-byte bulk threshold — but the handle
   preview binds at 1,600 bytes, so they still project a 5% saving. A control that
   carries the effect reads as evidence the instrument is clean. C01–C03 replace them
   and project 1.073–1.075.
4. **A census specimen was silently `None`.** The picklability census called
   `sys.exc_info()[2]` outside any `except` block, so the row reading "traceback
   crosses: yes" was pickling nothing. With a real traceback it does not cross.

A fifth, found by hand rather than by the dry run and recorded because it nearly
inverted a kernel verdict: `prctl` is syscall **167** on aarch64 and **157** on
x86-64, and 157 is `setsid` on aarch64. Passing the x86-64 number made Landlock report
`UNSUPPORTED` on a kernel where it is enforced. `kernel_probe.py` now resolves
`libc.prctl` through the dynamic linker and a self-test forbids any hardcoded syscall
number at that call site.

## Headline projections, and what they are not

| | |
|---|---|
| arm A total | **$13.9697** — irreducible $10.5218, margin $3.4479 |
| arm B total if authorized | **$16.3613** — [not recommended](./PREREGISTRATION.md) |
| projected median token ratio at the 8,000-token inline cap | 0.429 |
| the same at a 2,000-token cap | 0.958 |
| the same at a 32,000-token cap | 0.160 |

**These are projections from local byte measurements and a declared 4.0 bytes/token
divisor. They are not results, and the ratios in particular are inputs to a cost
model, not findings about model behaviour.** Nothing here has been graded, because
nothing has been run.

## What cannot be reproduced from this directory

- **The live arm.** It does not exist yet, by design.
- **Credentials.** None are committed and none are in this repository. Supply your own
  via `F2A_ENV_ROOT` or `--env-root`, per the convention in
  [`../provider-credentials/`](../provider-credentials/). Arm A needs
  `ANTHROPIC_API_KEY`.
- **The kernel readings, off this host.** They are specific to `6.12.76-linuxkit` on
  aarch64 under Docker 29.4.1. `kernel_probe.py` is standalone and will produce your
  host's readings, which may differ — that is the point of committing the probe rather
  than only the table.

## Related

- [`../verifier-vs-judge/PREREGISTRATION.md`](../verifier-vs-judge/PREREGISTRATION.md)
  — the model for this document, and the source of the price basis and the
  bytes-per-token divisor reused here.
- [`../ceiling-test/`](../ceiling-test/) — E7, whose saturated instrument is the reason
  §4 of the preregistration carries a calibration band with pinning caps.
- `research/15-nvidia-oo-agents.md` — the claim under test.
