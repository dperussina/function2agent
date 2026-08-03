# Neutralisation notice — 2026-08-03

**Every run directory under this path is a dry run. No judge verdict exists in any of them, or
anywhere in this experiment.** Twelve runs are committed here; all twelve carry
`spend.dry_run: true`, and all 5,490 recorded judge-call rows across them are stub rows at
`cost_usd: 0.0` with `model: null`. E8 was built, self-tested, dry-run at $0.00 and then
deliberately **not run** — [finding 015](../../../findings/015-verifier-vs-judge-not-run.md).

## What was wrong

Each `analysis.json` committed a `decision` block whose first row read, in substance,
*"MD_best (discounted) = 30.7 pp on arm c2, FOC = 65.8%, FPR = 0.0 pp"* followed by a clause
promoting the verifier from a measurement to a shipping product claim. Ten of the run
directories rendered the same three rows into `report.md` as bullets under `## Decision table`.

Both figures the first row reads are functions of the stub. `MD` is **marginal** detection —
traces the judge passed and the verifier failed — and `FOC` is the catch rate over traces the
judge failed open on. Neither is defined without a judge verdict. Neither the row nor the `judge`
block it derives from said so.

**This is not an over-claim on a real measurement. It is a classification of stub output**, and
the correction class is **wrong**, not *narrowed* and not *superseded*.

The load-bearing part, and the one most likely to be reintroduced by someone reading quickly:
`D_c2` is a **detection** rate; the gate reads `MD`, **marginal** detection. With no judge
verdict, `MD` is undefined on this corpus, so **nothing here clears the gate and nothing here
fails it**. Surviving text implying either is wrong rather than merely unqualified.

The hazard was never that a careful reader would be fooled. The directory name says
`probe-readonly`, a rider two keys away says underpowered, and `report.md` opens with a
`DRY RUN — NOT RESULTS` banner. None of that is what a grep returns. A stranger who finds this
tree in six months and greps it for a verdict got one.

## What was done

`neutralise_decision.py` in the harness root applies the edit and re-checks it. It is
re-runnable and idempotent; `--check` exits non-zero if any artifact under `results/` is
unneutralised.

| Property required | How it is satisfied |
|---|---|
| No greppable string reads as a verdict | `decision` → `decision_void`, `rows` → `rows_withheld`; each row keeps its rendered figures and its classification clause is replaced by a withholding notice. The removed clauses are **not reproduced anywhere under `results/`** — quoting one to explain its removal would put the string back. |
| Original values preserved | No number was altered, recomputed, rounded or dropped. `MD_best_discounted_pp`, `MD_best_arm`, the advisory rider, the prevalence warning, every Wilson interval and every detected-key list survive verbatim. |
| The edit is disclosed | `_neutralised` is the **first key** of every `analysis.json`, carrying the date, the mechanism, the correction class and the authority. `_stub` markers were added to each `judge` arm and to `md_upper_bound` — the blocks the rows derive from, which is where the omission actually sat. Each `report.md` carries a dated `NEUTRALISED` note directly under a heading now reading `## Decision table — VOID, NOT A VERDICT`. |

Two restrictions the old rows carried were **prohibitions rather than outcomes**, so they are
preserved rather than withheld, under `decision_void.restrictions_still_binding`: §6.6's bar on
describing arm c1 as covering the corpus, and §3.3(1)'s bar on `md_upper_bound` appearing in any
sentence whose subject is the verifier. §6.9's rider is preserved there too.

## Sibling directories carried the same defect

They were checked rather than assumed. **All twelve did**, in two figure variants — the three
`20260803T0821xx` runs predate Amendment B3.2 and read 26.9 pp / 53.8% / 3.3 pp; the other nine
read 30.7 pp / 65.8% / 0.0 pp. `20260803T091345-quarantine-check` and
`20260803T092721-final-verify` carry two rows rather than three, because arm c1 was quarantined
by then and the `UNV_c1` row is not emitted. `20260803T084936-dryrun` and
`20260803T084946-dryrun` have no `report.md`. Nothing else varies.

## What was deliberately *not* done

**`analyze.py` still emits the clause.** It is one of the sixteen files hashed into
`harness_fingerprint`, so editing it would make every recorded fingerprint incomparable with any
future run, to fix an emitter for an experiment that will not run (Amendment B5, OD-14). The
recurrence guard is external and mechanical instead:

- `python3 tools/check_corpus.py` — check **`dry-run-verdict`** flags verdict-shaped and
  decision-shaped claims in any artifact belonging to a run marked `dry_run: true`, and passes a
  stub artifact that states locally that it is a stub.
- `python3 neutralise_decision.py --check` — exits non-zero on any unneutralised artifact here.

**The consequence, stated plainly because it is a residual and not a closed loop: any future
`runner.py --dry-run` writes a fresh directory containing the un-neutralised clause.** That is
accepted rather than solved. Run `python3 neutralise_decision.py` after any dry run, or delete the
directory; `tools/check_corpus.py` fails the corpus check if neither is done, which is the point at
which it becomes impossible to commit one silently. **The guard is at the repository boundary, not
at the emitter**, and moving it to the emitter costs the fingerprint.

**The `adjudication/` tree was not touched.** It is a completed blind study, it sits outside
`results/`, and it carries no `dry_run` marker.

## What is still real in these files

The verifier arms, the taxonomy, the eligibility ledger, the denominators, the controls and the
cost projection are computed from the frozen corpus and never touch the judge. Arm c2's detection
census is a genuine offline result. Its **margin over a judge is unmeasured**, and that
distinction is the whole of what the owner's decision turns on: *the verifier works; nobody knows
whether it is needed.*
