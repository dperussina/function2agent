# `corpuscheck` — mechanical consistency checks over the corpus

Five consecutive propagation passes each found errors an earlier pass had claimed
to have fixed "wherever it appears." Natural-language self-verification does not
work at this scale. This is the mechanical check that does.

```
python3 tools/check_corpus.py                 # gate a commit; exits 1 on any error
python3 tools/check_corpus.py --report-only   # print everything, always exit 0
python3 tools/check_corpus.py --list-checks
python3 tools/gen_claims.py                   # write the derived claims
python3 tools/gen_claims.py --check           # exit 1 if a derived claim is stale
python3 tools/selftest.py                     # prove the checks and the generator fire
```

Python 3.11+, standard library only, no network. External URL liveness is
deliberately **out of scope** — an earlier checker covered it and this one does
not rebuild it.

| Flag | Effect |
|---|---|
| `--report-only` | Print everything, exit 0. For running while the corpus is mid-edit. |
| `--warnings-as-errors` | Warnings fail the run too. |
| `--check NAME` | Run only these checks. Repeatable. |
| `--skip NAME` | Run everything except these. Repeatable. |
| `--path GLOB` | Restrict the corpus. Repeatable. Checks that lose their inputs report as `skipped` rather than passing silently. |
| `--format text\|json\|summary` | `summary` is one line per check, for comparing runs. `json` is for tooling. |
| `--no-hints` | Drop the hint line. |
| `--config PATH` | Use a different `config.json`. |
| `--root PATH` | Point at a different repository root. |

Narrowing with `--path` is the reason checks announce themselves as skipped:
`--path README.md` removes every findings document, so `numeric-provenance` has
no authority set. Reporting that as "no violations" would be the false-negative
this tool exists to prevent, so it says so instead.

## The one thing to read first

**A validator that passes everything because its regex never matches is the exact
failure mode this project keeps hitting.** A green run of `check_corpus.py`
therefore proves nothing on its own. The evidence lives in `tools/selftest.py`,
which runs the whole check set against two fixture corpora under
`tools/fixtures/`: `known-bad`, where every check must fire on a planted defect
identified by file, line and content, and `known-good`, where no check may fire
on any of the constructs that have historically produced false positives. Both
directions are asserted. If you change a regex, run it.

**And a green self-test proves less than it looks like it proves.** It shows every
check fires; it does not show that the *numbers* the checks compare against are
the numbers the fixtures require. `tools/threshold_probe.py` closes that gap by
moving each threshold one unit and requiring the self-test to break. If you change
a constant, run that too — and read the stale-`.pyc` warning under **Auditing a
threshold** before you write any edit-and-restore loop of your own.

## What each piece does

| File | Purpose |
|---|---|
| `check_corpus.py` | Entry point. Adds `tools/` to `sys.path` and calls the CLI. |
| `corpuscheck/config.json` | Everything tunable: which paths are authoritative, which are consumers, which figure shapes count as measurements, which identifier namespaces to resolve, the inventory rules. Comments live in `_comment_*` keys. |
| `corpuscheck/corpus.py` | File discovery, role assignment, and the masking every check shares — fenced blocks, inline code, link targets and HTML comments blanked to spaces with offsets preserved. Also `split_row`, the table-cell splitter that handles `\|` and pipes inside code spans. |
| `corpuscheck/figures.py` | What counts as a quoted measurement, and what only looks like one. The single highest-leverage file for the noise floor. |
| `corpuscheck/search.py` | Whole-repository text index, including the committed harness results. Answers "does this figure appear anywhere at all", which is what separates a typo from a propagated claim. |
| `corpuscheck/registry.py` | The `@check` decorator and the check table. |
| `corpuscheck/report.py` | `Violation`, and the `text` / `json` / `summary` formats. |
| `corpuscheck/checks/` | One module per failure class. |
| `gen_claims.py` | Writes the two claim classes that are derivable rather than authored. See below. |
| `selftest.py` | Proof that each check fires, that none fires on well-formed input, and that the generator writes digits and nothing else. |
| `threshold_probe.py` | Proof that each numeric threshold is pinned: moves every tolerance, window, bound and distance by one unit and requires the self-test to break. |
| `fixtures/` | The two miniature corpora. See `fixtures/README.md`. |

## The check set

Fifteen checks in nine families. Severity is **error** when the finding is
almost certainly a defect, **warning** when it is a defect *or* a judgement call
the author may have made deliberately.

| Check | Severity | What it catches |
|---|---|---|
| `numeric-provenance` | error / warning | A measurement-shaped figure quoted outside `findings/` that appears in no findings document. **error** when it appears nowhere else in the repository either — the transcription-error case. **warning** when it appears in other documents but no finding — the propagated-without-a-source case. Exact for `ratio4` and `money_cents` since 2026-08-03 — the lookup was a substring test, so `0.8961` was satisfied by a finding containing `0.89612`. |
| `ratio-arithmetic` | error | A count and the rate quoted beside it disagree: `53/69 = 0.7861`. Runs on findings too, because the numerator, the denominator and the rate are three statements of one fact. |
| `sum-arithmetic` | error | A total shown with its components does not equal them: `$18.15 ($7.59 + $10.55)`. |
| `table-integrity` | error | Three ways a table stops being one table: a blank line orphaning a row into body text, a row whose cell count differs from the header, and a run of pipe rows with no `\|---\|` delimiter. The orphan gap was one blank line until 2026-08-03; a new table is excluded by its delimiter, not by the gap, so a second blank was slack rather than a boundary. |
| `link-target` | error | A relative link resolves to nothing. |
| `link-anchor` | error | A `#fragment` names no heading in the target file. Slugs follow GitHub's algorithm including its `-1`/`-2` duplicate suffixes. |
| `link-label` | warning | The link *text* names a different document than the link *target*: `[finding 010](.../011-reachability...)`. The link works, so no existence check catches it, and a reader following the prose lands somewhere else. |
| `identifier-resolution` | error | `D-17`, `U-40`, `OD-06`, `FR-018`, `E15` and friends resolve to a definition. Dangling identifiers are how a superseded decision keeps getting cited. |
| `identifier-gap` | warning | A register with a hole in it. This corpus strikes superseded entries and keeps the row, so a gap usually means a deleted row that something still cites. |
| `findings-numbering` | error / warning | Duplicate numeric prefixes in `findings/` (**error**), a citation of a finding number that does not exist (**error**), and a gap in the sequence (**warning**). |
| `register-range` | warning | A prose summary of a register — `(D-01 … D-19)` — that stops short of the register's real last entry. **`gen_claims.py` now writes the standalone ones**; this rule is what fires when it has not been run, and is the *only* mechanism at the narrated sites the generator refuses. |
| `inventory-count` | warning | A prose count of repository contents that no longer matches the filesystem: "five committed harnesses" when there are eight. Six rules; the `findings` one had no site in any document until 2026-08-03, because alone among the six its pattern required a trailing comma and so read `15 findings,` but not `15 findings and an index`. |
| `catalog-line-count` | warning | A `Lines` column, or an inline `(N lines)`, that has drifted from the file it describes. **`gen_claims.py` writes these**; this rule is what fires when it has not been run. Exact since 2026-08-03 — the previous ±2 tolerance was concealing a live 2-line drift. |
| `toc-coverage` | warning | A `##` section missing from its document's own table of contents, and therefore unreachable from the top of an 800-line file. |
| `dry-run-verdict` | error | An outcome claim inside a run directory whose own manifest says `dry_run: true`: a gate cleared, a hypothesis confirmed, one method materially better than another, a line labelled `VERDICT:`. A run that called no model produced no evidence, so every such claim was computed against stub output. See below for why the disclosure has to be on the same line. |

Three of these name failure classes nobody had named before: `register-range`,
`inventory-count` and `catalog-line-count`. All three share one shape — **a
claim about the corpus that lives in a different file from the thing it
describes**, so no reviewer of the change that invalidated it ever sees it.
Two of the three are now *generated* rather than only checked; see
[Generated claims](#generated-claims--gen_claimspy) for what that changed and
why both rules were nonetheless kept.

`dry-run-verdict` names a fourth, and its shape is different: **a claim that is
arithmetically correct, correctly transcribed, and computed from inputs that do
not exist.** Nothing upstream of it is wrong. `numeric-provenance` traces the
figure to its source and finds one. The defect is entirely in what the figure is
called.

### Why `dry-run-verdict` demands a line-local disclosure

The artifact that motivated the check *did* disclose itself. Its report opened
with a `DRY RUN — NOT RESULTS` banner, its directory was named `probe-readonly`,
and a rider two sections down called the run underpowered. The decision row still
read `verifier is a headline feature`, and a reader who arrives by `grep` reads
that row and no banner.

So the exemption is deliberately narrow: a disclosure token — `stub`, `dry run`,
`withheld`, `void`, `unmeasured`, `no model was called` — must appear **on the
matched line itself**, or the line must be struck through. A banner elsewhere in
the file does not exempt anything, because the grep-shaped reader is exactly the
one the check is protecting. Rewriting a row to carry its own caveat costs a
clause. Getting this wrong cost this project five artifacts.

**A line is not a location, though, and until 2026-08-03 that is all the rule
meant by local.** Both token lists were matched as plain substrings anywhere in
the lowercased line, which opened two holes and both are now closed:

- `void` is a disclosure token and it lives inside `avoid`. A line reading
  "we avoid re-running the probe, so: H2 supported" disclosed nothing and
  exempted itself. Tokens are now matched at their **left word boundary** —
  left only, because `neutralis` and `dry run` are deliberately prefixes and
  must go on matching `neutralised` and `dry runs`.
- One prohibition token exempted **every** claim on its line, however far away.
  A token must now sit within `MAX_EXEMPTION_DISTANCE` (120 characters) of the
  claim it licenses. That bound is measured rather than chosen: across every
  artifact in the twelve committed dry-run directories, the furthest a real
  token sits from its claim is 19 characters. The corpus's own shape —
  "licenses only 'consistent with H2, underpowered'; it does not license 'H2
  confirmed'" — is 27 characters and keeps working; `known-bad` carries the
  same sentence with an unrelated `VERDICT:` bolted onto the end of it.

## Generated claims — `gen_claims.py`

Two of the fifteen checks were guarding **hand-written summaries of facts that
are machine-readable from an artifact sitting right beside them.** Guarding is
the wrong shape of solution for a fact nobody should be transcribing, and the
catch history says so: `catalog-line-count` has been tripped and hand-repaired
by a succession of agents — one fixing two stale counts, one fixing three, one
tripping it twice in a session on its own edits — and `register-range` has
caught drift on **one sentence in `VERDICT.md` four times**, each time because
a new entry landed in `research/14-architecture-synthesis.md`. Every repair was
a human retyping a number a script can read.

```
python3 tools/gen_claims.py            # rewrite in place; idempotent
python3 tools/gen_claims.py --check    # write nothing; exit 1 if a claim is stale
python3 tools/gen_claims.py --diff     # write nothing; print the unified diff
python3 tools/gen_claims.py --list     # every site and its status
python3 tools/gen_claims.py --only line-count   # one generator; repeatable
```

`--root` and `--config` mirror `check_corpus.py`. Two generators, **38 sites in
five files** as of 2026-08-03:

| Generator | Sites | Files it writes |
|---|---|---|
| `line-count` | 32 | `.cursor/skills/README.md` (18 inline `(N lines)`), `research/README.md` (14 `Lines` cells) |
| `register-range` | 6 | `README.md`, `specs/001-discovery-validation/VERDICT.md`, `specs/001-discovery-validation/plan.md` |

### It rewrites the number and nothing else

Each site is located as a **character span inside its line**, and only that
span is replaced. The sentence, the table cell, the emphasis, the citations and
the dated refresh log around it survive byte-for-byte. This is not a nicety:
these claims sit inside prose that carries meaning beyond the number, and a
generator that re-emitted the sentence would be worse than the hand-maintained
version it replaces. `selftest.py` asserts it directly — after a write, every
line the generator touched must be unchanged once digits are stripped from
both sides.

Site detection is **imported from `corpuscheck`, not reimplemented**. The
generator calls the same `_is_whole_register_claim`, the same `_INLINE_COUNT`,
the same `split_row_spans`. A second definition of "what counts as a
whole-register claim" would drift from the first, which is the failure class
this whole directory exists to prevent.

### The sites it refuses, and why the two rules were kept

**A struck claim is history, not a site.** The convention keeps a superseded
value visible inside `~~…~~` with a dated note beside it, so a struck claim is
skipped entirely — rewriting it would delete the correction.

**A live register range sharing its line with a struck one is `MANUAL`:**
reported, never written. The corpus's principal register-range site — `VERDICT.md` §SC-004 — is a dated
refresh log. It names which entry landed on which day, strikes the ranges it
superseded, and says which of them opened and which closed. There the digits
are half the claim and the narrative is the other half. A generator that
silently advanced `C-01…C-19` to `C-01…C-20` would leave a refresh log that
still ends at C-19, **and would have removed the only signal that the log
needed a new line** — converting a detectable staleness into an undetectable
inconsistency. So it reports and refuses.

**Line counts have no `MANUAL` case, and that is the difference in kind between
the two generators.** A document's length has no narrative half — nothing
beside it explains *why* it is 806 lines — so every line-count site is
writable. Struck-ness is therefore tested against the count's own span rather
than its row: a `Lines` row whose *Key findings* cell happens to contain a
strikethrough is not a correction record about the length. Two rows in
`research/README.md` were silently frozen by the looser test before it was
tightened, and both happened to be correct at the time, so nothing surfaced.

That is also the whole disposition of the two rules, and they were kept for
different reasons:

- **`catalog-line-count` — kept as the trigger.** A line count is a bare fact;
  once the generator has written it the claim is complete. The rule survives
  because *the generator is not invoked automatically*, so the window between
  "someone edited a `SKILL.md`" and "someone ran the generator" is real and
  this rule is the only thing that notices it. What changed is what a finding
  *means*: run the generator, do not retype the number. The hint says so.
- **`register-range` — kept because it still guards something no generator
  covers.** At the narrated sites the generator declines, so this rule is not a
  backstop there, it is the mechanism. Retiring it would leave the corpus's
  most-drifted sentence unguarded.

Neither is a check that can no longer fire. Retiring either would have been the
"a safeguard that can no longer trigger reads exactly like one that has been
satisfied" failure this project has already recorded — and `catalog-line-count`
had quietly become a mild instance of it anyway: its ±2 tolerance meant
`research/README.md` could list `08-auth-identity-and-secrets.md` at **804**
lines against an actual **806** and still read clean. It did. The tolerance is
now zero, because a generated number is never approximately right; run
`check_corpus.py --report-only` while a document is mid-edit.

### What is *not* generated, and the one that looks like it should be

`inventory-count` claims — "eighteen project skills", "eight committed
harnesses" — are computed against a glob and are just as derivable, but they
are written as **English number words inside sentences of varying shape**
(`config.json` carries a regex per rule for exactly this reason). Rewriting
`eighteen` to `nineteen` in place is a different and much less safe operation
than rewriting a digit span, and the rule has not produced the repeat-repair
history the other two have. Left checked, not generated.

## Roles: who is authoritative

`config.json` sorts every file into one of four roles, and the roles decide which
checks see which files.

| Role | Glob | Meaning |
|---|---|---|
| `authority` | `specs/*/findings/*.md` | The source of record for measured numbers. Nothing checks these for provenance; they *are* the provenance. |
| `consumer` | `README.md`, `research/*.md`, `specs/*/plan.md`, `spec.md`, `VERDICT.md`, `.cursor/skills/*/SKILL.md`, `docs/*.md` | Documents that quote findings. `numeric-provenance` runs here. |
| `harness` | `specs/*/harness/**` | Experiment code and committed results. Searched by the index, checked only for structure and links. |
| `other` | everything else in scope | Structure and links only. |

`VERDICT.md` is classified as a consumer rather than an authority on purpose.
It adjudicates rather than measures, and treating it as authoritative would make
every figure it derives self-certifying.

## Known false-positive modes

Every one of these was observed on the real corpus and is either handled or
consciously accepted. They are listed because a checker whose failure modes are
undocumented gets switched off the first time it is wrong.

**Handled.**

- *Escaped and code-span pipes.* `` `api-key:endpoint:<chat\|image>` `` in
  `research/08` broke an earlier ad-hoc validator, which counted it as a column
  break. `split_row` tracks backtick runs and `\|` escapes. The exact string is
  in `known-good`.
- *Citation identifiers read as rates.* `doi:10.1609/aaai...` and `Preprints
  202606.0238` both parse as four-decimal figures. Suppressed by a citation
  pattern and by capping a rate's integer part at three digits.
- *Vendor prices read as spend.* `research/05` and `research/13` survey external
  pricing. A money figure followed by a per-unit marker — `/1k`, `/task`,
  `per session-hour` — is a price and is not extracted.
- *Proximity pairing.* The first `ratio-arithmetic` paired any rate within 60
  characters of any count and produced sixteen violations, all false: "route
  recall is 0.8961 (69 of 77) at precision 1.0000" pairs the count with the
  *precision*. Only three syntactic forms are recognised now (`A/B = R`,
  `A of B (R)`, `R (A of B)`).
- *Register subsets.* "U-26 through U-29 are the newly opened ones" is not a
  claim about the register's extent. `register-range` fires only on a range that
  starts at the first entry **and** is either parenthesised or one of several
  register ranges listed together.
- *Inventory words that are not counts.* "Three findings converge on X" is a
  sentence about conclusions. Inventory rules are scoped to index documents by
  the `files` key; unscoped, that one rule produced eleven false positives
  against two real ones.
- *`verdict` the field name.* Every judge-call and oracle row in the harness
  results carries a `"verdict": "pass"` key, and `verdicts.jsonl` is full of
  them. The `labelled-verdict` pattern is the only case-sensitive one in the
  rule and matches `VERDICT:` in upper case only, so a column name is never read
  as a claim. Both forms are in `known-good`.
- *A prohibition read as an assertion.* `PREREGISTRATION.md`-style restrictions
  copied into an analysis — "does not license `H2 confirmed`", "may not be
  described as materially better" — contain the forbidden phrase in order to
  forbid it. A separate `prohibition_tokens` list exempts these; it is kept
  separate from the disclosure list because the reason differs, the line being
  honest about the rule rather than about the artifact.
- *A struck correction.* The house convention keeps the wrong text and strikes
  it. Matches inside `~~…~~` are skipped, so a correction never re-fires as the
  defect it is correcting. `numeric-provenance` was the last figure-reading check
  not to know this, and it mattered the moment the multiplier rule tightened: the
  four `3.7×` claims it surfaced were retracted in the house style — multiplier
  struck, `220 against 60` stated in its place, dated note beside it — and the
  rule went on demanding provenance for the retraction, so the only way to satisfy
  it would have been to delete the correction. The exemption cannot launder a live
  figure, because the strike renders: hiding an unsourced number behind it means
  publishing it struck, which is a retraction and not a claim.
- *A run that actually paid.* The check reads each run directory's own
  `dry_run` marker and only fires where it is `true`. `known-good` contains a
  live run stating the same three claims the dry run beside it is forbidden to
  state.

**Accepted, and live in the current output.**

- *A price in a bare table cell.* `research/05` has a pricing table whose cell
  is just `| $2.50 |`, with no per-unit marker on the line. It is reported. One
  instance corpus-wide.
- *Derived aggregates.* `$24.82` and `$18.15` in `VERDICT.md` are sums computed
  from findings figures, not quoted from one. They are correctly reported as
  unsourced and are not errors of fact. `sum-arithmetic` verifies the arithmetic
  where the working is shown.
- *Percentages and fractions.* `percent_decimal` and `fraction` are implemented
  and **off by default**. Turning them on adds roughly 125 violations, nearly all
  external benchmark and vendor figures from `research/01`, `/04`, `/05` and
  `/13`. Enable them in `numeric_kinds` for a targeted sweep of one document,
  never for the gate.
- *Third-party multipliers with no citation.* **32 warnings, and they are the
  reason this gate is not at zero.** Typing the multiplier lookup surfaced them;
  it did not create them. All 32 are external figures — Anthropic's ~15× token
  multiplier for multi-agent systems (23 sites), a permissive-mode 200× approval
  figure (2), a 5–100× search-loop cost range (5), a 10–25× model-family price
  range (2) — and none is a measurement this corpus took. Under the untyped rule
  they read as sourced because their digits occurred *somewhere* in a finding, and
  the occurrences are worth naming: `15×` was satisfied by "LiteLLM 1.95.0
  publishes **15** wheels", by the decision label **OD-15**, and by the table cell
  `| R2 | 15 |`; `200×` by the HTTP status code **200** in the credential-probe
  table; `25×` by "extraction version **25**" and by `25,633` tokens. That is the
  `$3.7687` defect in a wider form — a status code sourcing a cost multiplier —
  and these warnings are it being caught. Six sibling claims at the same values
  *are* exempt, because they carry the inline link the house style requires; these
  32 carry none, and no citation sits within four lines of any of them. The fix is
  a citation on each line, which belongs to the documents and not to this tool.
  Do not add these values to `numeric_allow`: it is keyed on the digit string, so
  allowing `15×` would also exempt a future genuine 15× measurement.

## Auditing a threshold — `threshold_probe.py`

`selftest.py` proves each check *fires*. That is a different claim from proving
the **number** a check compares against is the number the fixtures require, and
the difference is not academic.

`catalog-line-count` carried `TOLERANCE = 2` for its whole life. Restoring that
value left the entire self-test green — because every planted line-count drift in
`known-bad` was at least 26 lines wide, so the fixture could not tell a tolerance
of 2 from a tolerance of 0. It read as proof and was not proof. A defect planted
comfortably past a threshold demonstrates that the check runs; only a defect
planted *one unit past* the threshold demonstrates where the threshold is.

    python3 tools/threshold_probe.py             # every threshold, both directions
    python3 tools/threshold_probe.py -k orphan   # one threshold
    python3 tools/threshold_probe.py --show-failures

The probe moves each threshold by one unit, runs the self-test, restores the
file, and reports. A threshold is **discriminated** when the move breaks the
self-test. Every threshold declares which direction must break, because the two
shapes differ:

- A **slack** bound — `TOLERANCE`, `MAX_EXEMPTION_DISTANCE`, a rounding
  allowance — suppresses violations as it grows, so the pinning fixture lives in
  `known-bad` just past it and *widening* must break.
- A **window** bound — `MAX_ORPHAN_GAP`, a run length, a word gap — admits
  violations as it grows, so *narrowing* must break, and where `known-good`
  carries a legitimate construct one unit outside the window, widening must
  break too. Both directions are pinned wherever a legitimate construct exists
  to pin the widening side with.

### The stale-`.pyc` trap

**Read this before running any edit-and-restore battery over this tree.** It cost
the prior audit a whole reversion run and the failure mode points at the wrong
file.

`TOLERANCE = 0` and `TOLERANCE = 2` are the same number of bytes. CPython
validates a cached `.pyc` against its source's **mtime and size**, and mtime is
compared at one-second granularity — so an edit-and-restore inside the same
second produces a source file whose mtime and size both match a `.pyc` compiled
from the *other* value, and the interpreter loads the stale cache. What that
looks like from outside is not an obvious error. It is a battery in which
failures leak across unrelated cases: a threshold already restored still reports
broken, and a perturbation that should break reports clean. Every conclusion
drawn from the run is then arbitrary.

Three defences, all applied together on every run the probe makes, because any
one alone is a single point of failure in a harness whose entire job is to be
trustworthy:

- every `__pycache__` under `tools/` is deleted before each interpreter starts
- the child runs with `PYTHONDONTWRITEBYTECODE=1`, so none is written back
- the child runs with `-B`, the same instruction by a second route

Do not remove these because the runs look fast enough without them.

### One bound, two call sites

The per-unit window read as unpinnable until the probe was taught that a single
bound can live at more than one call site. `figures.extract` uses the 24-character
window to drop `$0.08 per session-hour`, and `figures.rate_keys` uses the same
window to remember that `0.08` was named as a rate on the line so a later bare
`$0.08` back-reference stays exempt. Narrow one and the other still exempts the
figure, so a single-site perturbation changes nothing observable. Anchors that
must move together declare `occurrences`; anchors that must not are held to
exactly one match, because an anchor matching twice usually means it also matched
a docstring, and rewriting prose alongside a constant is how a battery starts
lying.

## What this cannot catch

Stated plainly, because knowing the residue is worth more than a coverage claim.

- **Whether a number is *right*.** The tool checks that a quoted figure exists in
  a findings document. If the finding itself is wrong, or if a figure was
  correctly transcribed from the wrong finding, everything passes.
- **Semantic staleness.** "D-17 stays decided-but-unenforceable" in one document
  against "✅ DISCHARGED — D-17 is enforceable" in another is a direct
  contradiction with no numeric or structural signature. Nothing here sees it.
  This is the single largest gap.
- **Which of two mechanisms a claim names.** The recurring `M1`-versus-`M2`
  ablation error is a statement about which named thing causes an effect. Both
  names exist, both are defined, the sentence is well-formed. Undetectable
  without encoding the claim itself.
- **Prose that contradicts an adjacent table.** `finding 010`'s prose named one
  mechanism while its own committed table showed two. Both halves are internally
  valid.
- **Figures with no distinctive shape.** Integer counts — "69 endpoints", "eight
  configurations", "three routers" — carry no marker separating a measurement
  from a quantity, so they are not extracted at all.
- **Cross-document rounding drift.** `0.8961` in one place and `89.61%` in another
  are treated as the same figure by the alias rule, which is usually right and
  hides a real disagreement when it is not. Every alias is now *lossless*: the
  one-decimal form was dropped 2026-08-03, because finding 004 writes `89.6` and
  that made `0.8960` through `0.8965` all read as sourced — six of the ten values
  a slipped last digit can produce in the corpus's most-quoted figure. A figure
  cited only to one decimal in a finding must now be quoted to one decimal.
- **Anything outside markdown.** Committed harness results are searched but not
  checked, except by `dry-run-verdict`, which reads the JSON, JSONL, CSV and
  text artifacts inside run directories. The Python under `harness/` is not read
  by any check — including the analysis script that *emits* the decision rows
  `dry-run-verdict` catches, so the rule stops the artifact reaching the
  repository and does not stop the code producing it.
- **A wrong verdict in a run that paid for it.** `dry-run-verdict` keys entirely
  off the `dry_run` marker. A live run may publish any conclusion it likes,
  however unsupported, and nothing here objects. The check catches *evidence
  that does not exist*, not *reasoning that does not follow*.
- **An unmarked dry run.** A run directory with no `dry_run` marker anywhere is
  treated as live. The marker is written by the runner, so this fails only if
  someone hand-assembles a results directory.
- **A whole-register claim written as ordinary prose.** `register-range` requires
  the range to start at the first entry *and* be parenthesised or listed with
  another range, because the lexical cues do not work — `research/14`'s "U-01
  through U-06 are the ones that cost real money" starts at the first entry, sits
  four words after the phrase "the whole register", and is a subset. The cost is
  that "the decision log OD-01 through OD-14" is not checked: two live sites in
  `specs/002/spec.md` say exactly that and neither is read. Dropping the
  requirement was measured — it reports nothing on the current corpus — but it is
  free only because that U-01 counterexample happens to be struck. The OD
  register is still guarded, at `plan.md`'s parenthesised site.
- **A lone pipe row far from any table.** `table-no-delimiter` needs two
  consecutive pipe rows, and the orphan rule needs the row within two blank lines
  of a real table. A single stray `| a | b |` outside both windows is caught by
  nothing, and cannot safely be: `|P ∩ A_c| / |A_c ∩ (S ∪ N)|` in
  `harness/deployment-reachability/PREREGISTRATION.md` is set-cardinality
  notation and is the corpus's one pipe row belonging to no table. Both windows
  are now pinned from both sides — `known-bad` carries a two-row block and a
  two-blank orphan, `known-good` carries that set-notation row three blanks below
  a closed table — so the residue is exactly as wide as those two bounds say and
  no wider.
- **A multiplier sourced from a *different* multiplier.** The type hole recorded
  here previously is closed. The lookup no longer runs against authority text; it
  runs against the multiplicative figures parsed out of it, so an authority
  writing `$3.72`, `figure 3.7`, `§3.7`, `3.7%` or `3.7 GB` no longer satisfies a
  claim of `3.7x` — all five did before, and the enumerated accept surface fell
  from 130 one-decimal values to 38 (and 151 two-decimal to 49) when kind
  matching replaced digit matching. What is left is the part typing cannot reach:
  two genuinely measured multipliers can sit close enough that one quoted value
  cannot distinguish them. The findings hold **27 such pairs** — a claim of `2.2x`
  is satisfied by both the measured `2.17x` and the measured `2.196x`, and a claim
  of `1.9x` by any of `1.88x`, `1.899x`, `1.9x` and `1.92x`. Both candidates are
  the right *kind* of quantity, so no type rule separates them; only quoting at
  the precision the finding measured to would, and the corpus deliberately does
  not require that. The residue is now same-type imprecision rather than
  cross-type confusion, which is a much narrower thing and is the floor for a
  rule that permits coarse quoting at all.
- **A four-decimal figure whose kind label is wrong.** `ratio4` is safe against
  the confusion above, and by exactness rather than by type: its match must be a
  standalone occurrence of all four decimals, so there is no rounding window for
  a differently-typed number to enter through, and a cross-type match would need
  an exact four-decimal coincidence. None exists — of the 42 `ratio4` claims whose
  only authority occurrence is `$`-prefixed, **42 are themselves dollar amounts on
  the consuming line and 0 are not**, so every one resolves to the identical
  figure and the provenance is correct. What is wrong is the label: `_MONEY_CENTS`
  requires exactly two decimals, so `$35.0817` and `$0.1716` fall through to
  `ratio4` and are checked as rates. Nothing misreports today, because the rules
  that treat the two kinds differently — the per-unit and rate-column exemptions —
  are only reached by figures that need exempting, and no four-decimal *price*
  occurs. Typing `ratio4` against money would break all 42 and fix nothing, so it
  is deliberately not done.
- **A fourth figure kind, if one is ever enabled.** `numeric_kinds` is
  `ratio4`, `money_cents`, `multiplier`, and each has its own lookup — exact,
  `$`-typed and multiplicatively-typed respectively. `figures.py` also extracts
  `percent_decimal` and `fraction`, which the provenance check does not read; the
  bare-substring fallback in `_authoritative` is therefore reached by no enabled
  kind. Enabling either would land on that fallback, which is not even an
  exact-match test: a claim of `53.6%` would be satisfied by `153.66` in any
  finding. The fallback is left as it is rather than hardened, because a branch no
  configuration reaches cannot be pinned by a fixture, and an unfalsifiable
  safeguard is the failure this file exists to record — but enabling a kind means
  giving it a lookup in the same pass.
- **A register that shrinks below `min_definitions`.** A namespace with fewer
  than three definitions disables `identifier-resolution`, `identifier-gap` and
  `register-range` for that namespace. The skip is *announced* — deleting a
  register down to two entries prints `namespace O disabled` — but it does not
  fail the gate, and only `identifier-resolution` announces it; the other two
  drop the namespace silently.
- **A threshold whose own headroom no prose can reach.** The per-unit window is
  24 characters, and across the 63 money figures in this repository that carry a
  per-unit denominator the longest `_PER_UNIT` match is 6 characters. The window
  therefore has 18 characters of headroom that only ~18 spaces between a figure
  and its denominator would occupy, and no fixture can pin it at one unit without
  being written in prose no one would commit. It is pinned at its *effective*
  bound instead: cutting the window to 5 turns `$0.08 per session-hour` back into
  a checked figure and the self-test fails. A threshold set far clear of anything
  real is safe and is also unfalsifiable at the margin, and those are the same
  fact stated twice.
- **A `##` section in a document with no table of contents.** `toc-coverage`
  reads a document's own contents list, so a document without one has nothing to
  be missing from. Eight of the corpus's 104 markdown documents have a contents
  list; the longest without one is 18,484 lines.
- **A struck arithmetic claim is still checked.** `inventory-count`,
  `register-range`, `dry-run-verdict` and `numeric-provenance` exempt matches
  inside `~~…~~`; `ratio-arithmetic` and `sum-arithmetic` do not, and both fire on
  a struck superseded figure. That asymmetry is deliberate — a struck *count* or a
  struck *citation* is correctly retracted, whereas arithmetic does not go stale —
  but it means a correction that supersedes a wrong sum must fix the struck copy
  too.

## Adding a check

1. Drop a module in `corpuscheck/checks/`.
2. Decorate the entry point:

```python
from ..registry import check
from ..report import ERROR, Violation

@check("my-check", "One line for --list-checks.")
def run(corpus, ctx):
    return [
        Violation(
            check="my-check",
            severity=ERROR,
            path=doc.relpath,
            line=lineno,
            found="what is actually there",
            expected="what should be there",
            hint="the thing that turns a puzzle into a fix",
        )
    ]
```

3. Add it to the import list in `corpuscheck/checks/__init__.py`.
4. **Plant a defect in `fixtures/known-bad/` and the correct form in
   `fixtures/known-good/`**, then add a row to `EXPECTED` in `selftest.py`. A
   check with no fixture case is not finished.

Before adding a check, ask whether the claim should be **generated** instead.
If the fact is machine-readable from an artifact in the repository and the
claim is a bare transcription of it, a check will only ever tell a human to
retype something. Add a generator to `gen_claims.py` and a row to
`GEN_EXPECTED` in `selftest.py` — and keep the check, because nothing runs the
generator for you.

Read `doc.masked_lines`, not `doc.lines`, unless you specifically need the raw
text — masking is what keeps code blocks and link targets out of your regex. Call
`ctx["skip"](name, reason)` when a check cannot run rather than reporting
everything as a violation; a check that emits two hundred findings gets disabled
permanently, which costs more than the errors it found.

## Gating a commit

```sh
#!/bin/sh
# .git/hooks/pre-commit
python3 tools/check_corpus.py || {
  echo "corpus check failed; run with --report-only to see warnings too"
  exit 1
}
```

Warnings do not fail the build. Add `--warnings-as-errors` once the current
warning set is cleared, or the hook will be bypassed on the first commit that
touches an unrelated file.
