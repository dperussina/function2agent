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
python3 tools/cite_advisor.py                 # advisory only; never fails anything
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
| `cite_advisor.py` | **Not a check and not a generator.** Ranks every requirement against each contract's subject and lists the high scorers the contract does not name. No finding changes its exit code, nothing imports it, the gate does not know it exists. |
| `tamper.py` | The matcher `tests/removal_proofs.sh` edits source with. Exact first, whitespace-tolerant second, unique always. See [Removal-proof rot](#removal-proof-rot--tamperpy-and-check_tamperspy). |
| `check_tampers.py` | Static rot check over every removal proof: does each tamper still name one live site, and does each test still exist? No pytest, no Go, no privileges. |
| `proof_timeout.py` | **Not a check.** The per-arm wall-clock cap `tests/removal_proofs.sh` runs every proof under, and the reason it exists rather than `timeout(1)`: macOS ships none. Exits `124`, which the harness scores as `timed-out` — never `proved`, because a killed process is non-zero for a reason that says nothing about the mechanism, and never `skipped`, because that is how an arm leaves a green run unnoticed. |
| `proof_attribution.py` | **Not a check.** For each removal proof, the test that actually fails once its tamper lands — the reading a human does to decide whether a proof proves what it claims. Applies every tamper, so it runs each one under `proof_timeout.py` at the same cap the harness uses; a run that was killed reports `TIMED OUT` or `SIGNALLED` and never `fails NOTHING`, which would be a claim that the test passed made by a run that never reached an assertion. |
| `removal_proofs_summary.py` | **Not a check either.** Writes the harness's JSON record — one entry per proof, plus the kernel, privilege and toolchains the totals are a property of — and renders it for a CI run page. It exists because a green job is one bit, and one bit cannot separate a run where every arm fired from one where the kernel arms all skipped. On the harness's abort path it deliberately emits no totals at all: a record that reads as success out of a run that measured nothing is the defect, not the fix. |
| `selftest.py` | Proof that each check fires, that none fires on well-formed input, and that the generator writes digits and nothing else. |
| `threshold_probe.py` | Proof that each numeric threshold is pinned: moves every tolerance, window, bound and distance by one unit and requires the self-test to break. |
| `fixtures/` | The two miniature corpora. See `fixtures/README.md`. |

## The check set

Seventeen checks in ten families. Severity is **error** when the finding is
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
| `definition-count` | error / warning | A prose count of a *register* — "58 functional requirements" — against the definitions in the specification it describes. **error** when the target yields zero definitions, unconditionally; **warning** on an ordinary mismatch, because a deliberately historical figure is a real case and the strike convention is its escape. See [Why zero definitions is an error](#why-zero-definitions-is-an-error-and-not-a-comparison). |
| `catalog-line-count` | warning | A `Lines` column, or an inline `(N lines)`, that has drifted from the file it describes. **`gen_claims.py` writes these**; this rule is what fires when it has not been run. Exact since 2026-08-03 — the previous ±2 tolerance was concealing a live 2-line drift. |
| `toc-coverage` | warning | A `##` section missing from its document's own table of contents, and therefore unreachable from the top of an 800-line file. |
| `lifecycle-taxonomy` | error | `data-model.md` §2.1's declared terminal states are not exactly the members of `TAXONOMY` in `src/contracts/terminal.py`, in **either** direction. The only check whose other side is source: the taxonomy is parsed with `ast`, never imported, because `--root` may point at a fixture tree. Added 2026-08-05 under **OD-26**, after the two artifacts had diverged in both directions at once — three members absent from the diagram, two diagram labels that were not members, and a bare `completed` where the member is `terminated.completed` — while the other sixteen checks ran at 0 errors, because none of them reads Python. See [Why the lifecycle is a table now](#why-the-lifecycle-is-a-table-now). |
| `dry-run-verdict` | error | An outcome claim inside a run directory whose own manifest says `dry_run: true`: a gate cleared, a hypothesis confirmed, one method materially better than another, a line labelled `VERDICT:`. A run that called no model produced no evidence, so every such claim was computed against stub output. See below for why the disclosure has to be on the same line. |

Four of these name failure classes nobody had named before: `register-range`,
`inventory-count`, `catalog-line-count` and `definition-count`. All four share
one shape — **a claim about the corpus that lives in a different file from the
thing it describes**, so no reviewer of the change that invalidated it ever sees
it. Two of the four are now *generated* rather than only checked; see
[Generated claims](#generated-claims--gen_claimspy) for what that changed and
why both rules were nonetheless kept.

`definition-count` is the fourth, added 2026-08-04, and it was added because
both of its live sites were stale and neither had ever been read: `plan.md`
claimed *54 functional requirements, 28 success criteria* against an actual 57
and 30 — wrong by three and by two **before** FR-058 landed — and `tasks.md`
claimed 55 against 58. `check_corpus.py` ran its other fifteen checks at 0
errors the whole time. It is a check rather than a generator for a reason worth
knowing before reaching for one: both live sites are *correction records* — a
struck figure, a live figure and a dated note on one line — which is exactly the
shape `gen_claims.py` classifies `MANUAL` and refuses to write, and the house
strike-and-advance convention guarantees every future site will be one too.

### Why zero definitions is an error and not a comparison

**This is the sharpest negative control written for this directory, and the
reasoning matters more than the rule's name.** A count check is unusually
exposed to the vacuity failure, because **the number it computes when its
extractor is blind is `0` — and `0` is also a number a document may legitimately
claim.** The two readings are indistinguishable to an equality test.

`tools/fixtures/known-bad/specs/001-fixture/` pins it with a specification whose
requirement bullets lost their bold markers, so the extractor reads none of
them, under a tasks file carrying two claims about that same blind reading:

- **A claim of nine against a computed zero.** A bare equality check *does* fire
  here — and it fires with the wrong finding. It reports an arithmetic mismatch
  and names `0` as the expected value, when what actually happened is that
  nothing was read. A reader who trusts it edits the nine down to zero and makes
  the document worse.
- **A claim of zero against a computed zero.** A bare equality check passes,
  silently. The claim and the computed truth agree exactly, both are zero, and
  the agreement is worthless. An implementation that copied `inventory-count`'s
  `if actual == 0: skip` passes *both* sites.

So the check errors on **the extractor's blindness rather than on the
arithmetic**: a target yielding no definitions of the claimed kind is an error
whatever was claimed, including where the claim is itself zero and the two
therefore agree. **Equality is not verification when one side is the absence of
a reading.** That is the same sentence as the vacuity floor in
[`check_tampers.py`](#the-vacuity-floor-and-the-declaration-cross-check),
reached from a different direction, and four instruments in this repository were
hardened in one week for the same defect.

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

### Why the lifecycle is a table now

**The diagram could not be reconciled by anything, and that is why it drifted.**
`data-model.md` §2.1 enumerated its terminal states as branch labels inside a
fenced `text` picture. Three properties of that form each block a check on their
own, and together they explain a divergence that survived three members and
several weeks:

- **`~~` renders literally inside a fence.** The house convention for a
  superseded claim is to strike it and keep it visible, so a terminal state that
  turned out to be wrong could not be retired in the corpus's own style. Two
  prior passes had already found the same about headings, where a strike
  corrupts the anchor.
- **A picture cannot carry a status.** `terminated.no_progress` is a *declared
  debt* — its predicate is unwritable as specified and T067 owes it — and
  `terminated.denied_operation` was a name no requirement wanted. Nothing in the
  branch syntax could tell those two apart, or tell either from a live member.
- **Its labels were terminal-state names, not states**, so the diagram had no
  `TERMINATED` at all. `Runner.attach`'s refusal message cited §2.1 for having
  *"no edge out of it"*, which was true only because there was no *it*.

So the enumeration moved into a table and the diagram kept the shape it was
always authoritative about — one non-terminal state, one resume edge back, one
`RUNNING → TERMINATED` edge carrying a `terminal_state`. **The table is the only
enumeration**; the picture names no member, so the two cannot drift from each
other. What a human reader loses is the ten names inline in the picture; what a
human reader gains is a state model that matches the code, a requirement per
member, and a column that says which members are owed.

**The status column is checked in the forbidding direction as well as the
permitting one**, and that is the part worth copying. A marking that merely
exempted a row would go blind the moment its debt was discharged — the member
would ship, the row would go on saying *not yet*, and nothing would fire again.
So an `owed` or `struck` row whose name **is** a member is an error too. Both
sides of that rule are pinned in `known-bad`.

**Neither of its two vacuity floors is plantable in a fixture corpus**, which is
why they live in `selftest.py` as `LIFECYCLE_FLOORS` rather than beside the
other rows. Both are properties of a whole corpus — a taxonomy that parses to
nothing, and a corpus where no scoped document declares anything — and planting
either in `known-bad` silences every row-level defect there. They are also the
branches that most need pinning, for the reason
[Why zero definitions is an error](#why-zero-definitions-is-an-error-and-not-a-comparison)
gives one flight up: two things that were never read agree perfectly. Each floor
is exercised by perturbing a copy of `known-good` — the corpus that must
otherwise be silent — and requiring exactly one named violation out of it. The
third perturbation is the cheapest and the most realistic: **renaming one header
column**. The table still renders, still reads correctly to a human, and becomes
invisible to the check that reconciles it.

## Generated claims — `gen_claims.py`

Two of the seventeen checks were guarding **hand-written summaries of facts that
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

`--root` and `--config` mirror `check_corpus.py`. Two generators, **39 sites in
five files** as of 2026-08-04:

| Generator | Sites | Files it writes |
|---|---|---|
| `line-count` | 33 | `.cursor/skills/README.md` (18 inline `(N lines)`), `research/README.md` (15 `Lines` cells) |
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

### The register-provenance trap

**Read this before writing any sentence that explains where the entries in a
register came from.** It is the second trap in this directory that costs a pass
before it is noticed — the other is the stale-`.pyc` trap under **Auditing a
threshold** — and the two share a shape: a tool doing exactly what it was built
to do, in a place nobody expected it to be looking.

A prior pass needed to say that different groups of owner decisions have
different provenance — some came out of feature 001's measurements, others out of
owner sessions, others out of a clarify session recorded retroactively. The
natural way to write that is one sentence carrying several ranges. **Several
ranges together is exactly the shape the generator reads as a whole-register
claim**, so the generator advanced one of the bounds to the register's real last
entry and the sentence then asserted that the *whole* register came out of feature
001's measurements. Every check passed. The sentence was false.

**Two ways in, and only one of them is the one the rules advertise.** Both were
confirmed against `_RANGE` and `_is_whole_register_claim` on 2026-08-03:

- **Two or more different registers on one line.** `in_list` is
  `len({namespace}) >= 2`, so `D-01 … D-22, C-01 … C-15` makes *every* range on
  that line a site — including a third, deliberately-partial `OD-01 through
  OD-14` sitting in the same sentence for a different purpose.
- **A single range introduced by punctuation.** A range starting at entry 01
  whose preceding text ends in `(`, `[`, `:`, an em dash or an en dash — after
  `*~_` and spaces are stripped — is a site on its own. A provenance sentence of
  the shape `…instead of by the bound: OD-01 through OD-14 came out of
  measurement…` is caught by the colon, with no second register anywhere near
  it.

**Emphasis around the whole range does not save you; emphasis around each
identifier does, and only by accident.** Verified on 2026-08-03 by running both
functions over the four shapes. Bolding the range as a unit leaves it a site,
because the leading `*` is stripped before the punctuation test and the closing
one sits after the match. Bolding the two identifiers *separately* makes
`_RANGE` fail outright, because the pattern needs the second identifier to
follow the separator immediately and the intervening `**` breaks it — which is
why `checklists/requirements.md`'s frozen site goes unread. **Do not rely on
that.** It is a side effect of the pattern, not a marking, it looks identical to
an unguarded range, and a later editor tidying the emphasis re-arms the site
silently.

**The workaround, and it is the one the prior pass used: write the bound in
words.** *"The first fourteen came out of feature 001's measurements"* carries
the same claim, is invisible to `_RANGE`, and — the part that matters — **stays
true when the register grows**, because it is a claim about a fixed set of
entries and not about the register's extent. That is the real distinction the
generator is enforcing and the reason it is right to rewrite the digits: a range
written in digits *is* an extent claim to this toolchain, whatever the sentence
around it meant. If you need digits, strike the superseded bound and advance it
in the house style, which makes the site history rather than a claim and is
skipped.

**Do not reach for a `MANUAL` marking here.** `MANUAL` is keyed on a live range
sharing its line with a *struck* one, and a fresh provenance sentence has no
struck range to trigger it.

### Finding the next free register number — and the two searches that get it wrong

**Read this before minting a `U-` or `C-` entry.** Three attempts to read these
registers with a `grep` failed in August 2026, and one failed in the direction
that hands out a **taken** number. The working method is two commands:

```sh
rg -nP '(?<![A-Za-z0-9-])U-\d+' --glob '!.git' .
rg -nP '(?<![A-Za-z0-9-])C-\d+' --glob '!.git' .
```

**Run it corpus-wide, not over the register file**, because a number is often
claimed in a finding before its row exists — that is the house escape for
quoting an unminted entry, and a search scoped to the register cannot see it.

**Both failure directions are real and only one of them is loud.**

- **A backtick anchor undercounts, and this is the dangerous one.** Searching
  for the identifier wrapped in a code span over
  `research/14-architecture-synthesis.md` returns **`U-49`** as its highest hit
  when `U-50`, `U-51` and `U-52` are all landed, and the same search for
  C-numbers returns **nothing at all**. The reason is structural: register rows
  write the identifier **bare in the first table cell**, and only *prose
  citations* wrap it in a code span — so the anchor reads the citations and
  misses the register. In that file the citations happen to stop at `U-48` and
  `U-49`, and no C identifier is written inside a code span at **any** site.
  Acting on either reading mints a number that is already taken.
- **The bare pattern over-counts, via a prefix.** Dropping the lookbehind makes
  `C-\d+` match the tail of every `SC-` identifier — `SC-001` through `SC-030`,
  the success criteria — and also of `NC-1` through `NC-7`. The highest hit then
  reads `C-030`, a zero-padded form that is not even a C identifier's shape.
  **So the lookbehind is not optional.**

**The lookbehind is load-bearing on C and currently inert on U** — no
`[A-Za-z]U-\d+` occurrence exists anywhere in the corpus, so the U command
would work without it today. Write both commands with it anyway: a namespace can
grow a colliding prefix at any time, and two commands that differ only in the
letter are the pair a reader copies correctly. This is the same closed-set
reasoning as
[Never state a classifier as a complement](#never-state-a-classifier-as-a-complement--enumerate-the-accepting-set),
one level down.

**Why bare-in-first-cell is the canonical definition site, from the checker
rather than from the corpus's habits.** `corpuscheck/checks/identifiers.py`
resolves a definition by taking the first cell of a table row, stripping
`[*~`_\s]`, and requiring an **exact** match — a cell of prose that merely
mentions an identifier does not define it. So the checker and the corpus agree
on where an entry lives, and the backtick form was never going to work. Note the
stripping: a first cell is a definition site **even when the identifier is
written in a code span**, so backticking a row heading does not hide it.

**The method is verified by what it found, not by reading its pattern.** It
returns `U-52` and `C-21`, both landed minutes before it was run, and a correct
method must return them. That distinction is
[Reading an instrument is not measuring it](#reading-an-instrument-is-not-measuring-it--plant-the-case-instead)
applied to a search: a regex that looks right and a regex that finds the known
high entry are different claims, and the three failures above all looked right.

**One trap in reading the output.** Piping to `sort -u -V` over `rg`'s default
output sorts by **path** and not by number, so the last line is not the maximum.
Use `-oNI` — match only, no line numbers, no filenames — before sorting, or read
the maximum by eye.

**And this trap is normally survived by accident, which is why it stays
invisible.** Any pipeline that happens to strip the path before sorting — a
second `rg -o`, a `cut`, an `awk '{print $NF}'` — gets the right answer for the
wrong reason, so the person who wrote it never sees the failure and passes the
one-liner on. The failure only appears for the next reader, who copies the
command **from a report rather than from this file** and drops the incidental
stripping step. Copy the two commands above, not a command out of a write-up.
This is the same shape as the emphasis note under
[The register-provenance trap](#the-register-provenance-trap) — a construct that
works by side effect looks identical to one that works by design.

#### Why this is documentation and not a check

**A duplicate register row is caught by nothing, and that was measured rather
than assumed.** A second `| U-52 |` row was planted in the register verbatim.
The only rule that fired was `catalog-line-count`, on the file being one line
longer — an incidental signal, and running `gen_claims.py` cleared it: with two
`U-52` definition rows standing in the register, `check_corpus.py
--warnings-as-errors` reported **0 errors, 0 warnings** and `gen_claims.py
--check` reported **0 stale**. The defect this search method exists to prevent is
entirely unguarded. Duplicates are invisible to the existing machinery *by
construction*, because `definitions_in` returns a **set** per document and
`_collect_definitions` unions those sets.

**A guard is constructible, and it was declined on measurement — the same
disposition as `register-range`'s relaxation and the unconstructible-scoping
check, and for the same reason.** The candidate rule is the narrowest one
available and carries no threshold, no window and no markup tolerance: *two
definition sites for one identifier in one namespace*, reusing the existing
first-cell rule rather than a second definition of it. Run over the clean
corpus it fires **12 times, and every one is well-formed**:

- `D-01`, `D-07` and `D-17` are defined in the register and restated in a table
  in `specs/002-spec-aware-agent-runtime/spec.md` — a legitimate cross-document
  restatement, and the only class a same-file narrowing would spare;
- `E1`, `E2`, `E4`, `E5`, `E6`, `E14` and `E15` each appear in two different
  tables inside `specs/001-discovery-validation/VERDICT.md`;
- `FR-048` heads two adjacent rows and `FR-049` three, inside one table in
  `findings/026-pivot-root-check-measured.md`, which is keyed on something else.

**Zero real defects at any narrowing, and three scopes were measured rather than
two.** The obvious tightening is to ask for the duplicate **inside a single
table**, on the reasoning that every legitimate case above is a *restatement*
somewhere else — a different table or a different file — whereas the defect, a
pass appending a row for a number already taken, necessarily lands in the table
the register is. That reasoning is sound about the twelve and still wrong, and
the measurement is why it was taken:

| scope | firings on the clean corpus | detects the planted `\| U-52 \|` row |
|---|---:|---|
| one corpus | 12 | yes |
| one document | 9 | yes |
| **one table** | **2** | **yes** |

**Both arms were run at table scope**, because a scope firing zero times on the
clean corpus and zero times on the plant is a rule that detects nothing, which is
the failure this repository keeps hitting. With the plant in place it reports
three firings and names `U-52` at the two adjacent lines, so it does catch the
defect. It also carries two permanent false alarms, and **they are a class the
restatement argument does not predict**: `research/14`'s registers are clean at
table scope, and both firings are in one table in
`findings/026-pivot-root-check-measured.md` — a **per-check results table** whose
header column is `requirement` and whose row key is the individual check, so
`FR-049` heads three rows and `FR-048` two because several checks bear on each
one. Any table keyed on something finer than the identifier repeats the
identifier in its leading column, which is an ordinary way to write a results
table rather than a defect.

**Adjacency does not separate them, and that is the next idea worth killing
early.** Both false alarms are consecutive rows (668–670 and 671–672) and so is
the plant (850–851), so requiring the duplicates to be adjacent changes none of
the three counts.

**Restricting to *the authoritative register* would work, and it needs an
artifact that does not exist** — a mapping from each namespace to the one document
and section that owns it — which is the identical objection that declined the
unconstructible-scoping check: **the thing that would have to exist first is the
artifact, not the check.** Excluding `findings/` would clear both false alarms and
is the wrong move for a stated reason: a number is routinely claimed in a finding
*before* its row exists, which is the whole reason the search above runs
corpus-wide, so that exclusion blinds the rule exactly where the claim lands
first — and it fits the rule to where today's two false alarms happen to live.
So the house rule holds here too: a rule firing only on false positives is worse
than a documented residue.

**The residue, stated so it is not mistaken for coverage.** Nothing will notice a
register that hands out a taken number. The search above is the only guard, it is
run by a human, and it is one command per namespace.

## The advisory — `cite_advisor.py`

The gate rule described under [What this cannot catch](#what-this-cannot-catch)
failed and stays unbuilt. **The ranking underneath it was built on 2026-08-03**,
as an advisory that fails nothing.

```
python3 tools/cite_advisor.py                        # the listing
python3 tools/cite_advisor.py --ground-truth         # score against the five hand-audited contracts
python3 tools/cite_advisor.py --contracts-at REV     # score the contracts as they stood at a revision
python3 tools/cite_advisor.py --spec-at REV          # read the requirements as they stood at a revision
python3 tools/cite_advisor.py --sensitivity          # how the ranks move with the stoplist and the stemmer
python3 tools/cite_advisor.py --ablation             # drop citations from clean contracts, count false alarms
```

**`--contracts-at` moves the requirements too, and that is the flag that matters here.** Given
`--contracts-at REV` alone, `spec.md` is read at `REV` as well, which is the state you want and is
why the leak below is visible at all. Holding the contracts at one revision while reading the
requirements at another — the comparison that *exposes* the leak — needs both flags:

```
python3 tools/cite_advisor.py --contracts-at cee7ff8 --ground-truth                  # 1 of 55, 10 of 55
python3 tools/cite_advisor.py --contracts-at cee7ff8 --spec-at HEAD --ground-truth   # 1 of 57,  3 of 57
```

It ranks all of `spec.md`'s requirements by Jaccard similarity against each
contract's subject — its title plus its leading section — and lists the
highest-scoring ones the contract does not name. **It has no threshold, and no
finding it makes changes its exit code** — it exits non-zero only for a path or a
revision that does not exist, which is a broken invocation rather than a result.
`check_corpus.py` does not import it, `selftest.py` does not test it, and adding it
to either would rebuild the rule that failed.

### Why it needs no threshold, which is the whole reason it survives

**Each contract states its own baseline.** The `**Requirements**:` header field
means the tool never has to answer *"is this score high enough?"* — only *"does
this score beat what the contract already names?"* That is why there is no
constant to pin, and it is the property that does not generalise; see
[the generalisation](#the-generalisation-that-was-assessed-and-not-built).

The sentence it exists to produce is **"FR-055 scores higher than anything this
contract names"**. The output marks those lines with `->` and says nothing else
about them. *"This contract is wrong"* is the sentence that failed the
false-positive probe and no output here is readable as it.

### What was measured, and where the earlier claim did not hold

That entry claims the metric put the governing requirement **first of 57**
for `artifact-versioning` and **third of 57** for `trace-record`. The first
half reproduces. **The second half does not survive being checked, and the reason
is a leak.**

Both pre-fix contract states were reconstructed from `cee7ff8`, which predates
all the contract work. Scored against **the requirement text as it stood at that
same revision** — the only state in which the defect was ever live:

| Contract | Governing requirement | Corpus-wide rank | Position in the listing (body scope) |
|---|---|---|---|
| `artifact-versioning.md` | FR-055 | **1 of 55** | **1** |
| `trace-record.md` | FR-038 | **10 of 55** | 6 — below a top-five cutoff |

Scored instead against the **current** requirement set, FR-038 ranks third of 57
exactly as claimed — and that measurement is circular. **FR-038 was rewritten on
2026-08-03 from the contract being scored against it**, growing from **51 words at
`cee7ff8` to 1379 at `HEAD`** — the bullet as `parse_requirements` reads it,
whitespace-split, which is the definition the scoring actually sees.
`spec.md` says so in as many words, that *"the v1 subject is the span, and
it was already the unit in the downstream contract rather than invented here"*.
The third-of-57 figure measures the repair, not the detection. **FR-055 by
contrast is byte-identical at both revisions**, so its first-of-55 is clean.

`--sensitivity` is in the tool because the prior sweep recorded neither the
stoplist nor the stemmer, and they move the ranks. Across six settings FR-055 is
**rank 1 in all six**; FR-038 ranges from **4 to 19 of 55** and reaches the top
three in none of them.

**So the advisory finds one of the two known defects, not two.**

### Precision, and the surface it should be measured on

A contract audited clean contributes zero hits and however many suggestions it
emits, because an advisory's cost *is* what it says about work that is fine.
Over all five hand-audited contracts at their pre-fix state:

| k | hits | suggestions shown | precision@k |
|---|---|---|---|
| 1 | 1 | 5 | `0.2000` |
| 3 | 1 | 15 | `0.0667` |
| 5 | 1 | 25 | `0.0400` |

**The listing is mostly noise and the headline is not**, and the difference is
the whole finding. Restricted to lines marked `->` — requirements outranking
everything the contract names — the same five contracts produce **five claims,
all of them on the one contract that was actually defective, with the correct
answer first**. All three clean contracts are silent.

### The one improvement, and it is a scope change rather than a metric change

The metric is untouched. What changed is **what counts as already considered**:
`--scope body` treats a requirement the contract names anywhere in its prose as
known, not only one listed in the header field. The reader is being asked *"is
there a requirement you have not thought about"*, and one discussed by name in
the second paragraph has been thought about.

This was not asserted. `configuration.md` is audited clean and its two loudest
suggestions were FR-048 and FR-014 — **both named in its own leading section**,
which reads *"Nothing in FR-048's declared mount set carries a configuration
file"*. Neither true positive is named in body prose, so nothing is lost. Running
the same citation-ablation probe that killed the gate rule — dropping one and two
citations from each clean contract, 184 cases:

| Scope | Silent cases | False headline claims | Worst single case |
|---|---|---|---|
| `header` | 133 of 184 | 112 | 6 |
| `body` | **161 of 184** | **33** | 3 |

`configuration.md` is never silent under header scope and silent in all 28 of its
ablations under body scope. **Caveat worth its own sentence: body scope was chosen
after looking at these five documents.** It introduces no constant and its
mechanism is *"does the contract name this identifier"* rather than a tuned bound,
which is the difference that matters — but it is validated on the same corpus that
motivated it, and it deliberately blinds the tool to a contract that mentions the
right requirement in passing without citing it. `--scope header` keeps that
visible and `--ground-truth` reports both.

### What it adds on the repaired contracts: nothing

Run against the working tree, **all five contracts produce no `->` line at all**.
Both repaired contracts now rank their governing requirement first of 57 and cite
it, so it correctly leaves the listing. A tool that goes quiet once the defects are
fixed is the behaviour that separates this from the rule that failed.

### The judgement

**Shipped, narrowly.** On real corpus states the headline surface produced five
claims across ten contract-observations — one true positive, four siblings on the
same defective contract, and **nothing at all on any clean contract in its real
state**. That is not output a reader learns to skip. Against it: the tool detects
one of two known defects, and its usefulness rests on a single unleaked positive
example. **Read the listing below the `->` lines as topic adjacency, not as a
worklist.**

### The generalisation that was assessed and not built

The same defect class appears twice more in this corpus without involving a
contract citation at all: a measured non-compliance sitting unnoticed against a
requirement written independently of it, and an instrumentation defect found only
by cross-reading two findings. **The ranking does not transfer, and the reason is
not the metric.**

What transfers is not Jaccard similarity — it is the **self-supplied baseline**.
A contract carries a `**Requirements**:` field, so the tool compares a score
against a score and needs no constant. **Neither findings nor success criteria
carry such a field.** Success criteria looked like the promising case and are not:
across the whole specification only twelve lines pair a success criterion with a
requirement at all, and every one is a prose aside rather than a mapping. Without
a baseline the tool is back to choosing an absolute cut on a Jaccard score, which
is the four-thousandths-wide window that killed the gate — or to a fixed top-N per
document, which emits a constant volume of suggestions whether or not anything is
wrong. Sixteen findings at three suggestions each is roughly fifty permanent
adjacency claims, which is the shape a reader stops reading.

**A second obstacle is independent of the first.** The defect in the
non-compliance case is that a measurement *violates* a requirement. Bag-of-words
similarity sees topic, not polarity: a finding that satisfies a requirement and a
finding that violates it score identically. That is the failure class already
recorded above as *"which of two mechanisms a claim names"*.

**What ground truth it would need, and what it would cost.** For findings against
requirements, a hand audit pairing every finding with every requirement — sixteen
by fifty-seven, a little over nine hundred judgements — each labelled not merely
*related* but *compliance-bearing*, by someone who understands both sides. The
corpus contains **one** known positive. One positive instance cannot validate a
ranking; the contract case had two and one of those turned out to be leaked. The
cross-reading case is worse: one hundred and twenty finding pairs, ground truth of
exactly one. The analysis code is perhaps a day's work and is not the expensive
part.

**Recommendation: do not build it.** The honest version of the smaller claim is
that ranking findings against requirements would produce a serviceable *reading
aid* — "here are the requirements this finding touches" — which is a different and
much weaker product than defect detection, and nothing in the corpus says anyone
wants it.

## Removal-proof rot — `tamper.py` and `check_tampers.py`

`tests/removal_proofs.sh` is the repository's evidence that its tests are load-bearing: it edits a
mechanism out of the source and requires the test that covers it to start failing. **Its dominant
failure mode is not a mechanism regressing. It is a tamper string quietly ceasing to match**, after
which the edit applies nothing, the test passes for the ordinary reason, and the proof reports a
result it did not earn. Fifteen proofs reached that state on 2026-08-03 — thirteen found at once,
then two more.

```
python3 tools/check_tampers.py                      # every proof; exits 1 on rot
python3 tools/check_tampers.py --warnings-as-errors # a proof surviving on whitespace tolerance fails too
python3 tools/check_tampers.py --root PATH --proofs FILE --exact-only   # score one revision against another
python3 tools/proof_attribution.py --only FR-017    # which test each proof's tamper actually breaks
```

**Three rot classes, and they were not equally visible.**

| Class | What it does | What it used to report |
|---|---|---|
| The tamper string moved | applies no edit | `UNPROVEN` — a claim about the tests, not the proof |
| The tamper grew a second site | `str.replace` edits both | `proved`, for a mechanism it did not isolate |
| The **test** was renamed | `pytest` exits 4, `go test -run` exits 0 | `proved` on the Python side, `UNPROVEN` on the Go side |

The third had no guard anywhere and is the worst of the three, because one rot produced two opposite
verdicts and neither was true.

### Why matching is whitespace-tolerant, and where the tolerance stops

Two of the fifteen rotted for a reason no amount of care prevents. Adding a second entry to a Go map
made `gofmt` realign it, `classPrivate: true,` became `classPrivate:  true,`, and both proofs
matching the single-space form stopped applying. Nobody wrote a wrong string; a formatter moved the
source underneath two correct ones, and the next edit that changes the longest key in that map will
do it again.

So `tamper.py` tries the literal string first and, failing that, normalizes both sides before
matching. **Leading indentation is deliberately not normalized** — it is the one whitespace that
carries meaning in these languages, and collapsing it would let a needle written for one nesting
depth match a same-looking line at another, then splice the replacement in at the wrong depth. What
collapses is runs of spaces and tabs *after* the first non-whitespace character of a line, which is
exactly the alignment class and nothing else.

**Tolerance without uniqueness would be worse than the rot**, so a match must identify exactly one
site. Zero is `NO_MATCH`; two or more is `AMBIGUOUS` unless the tamper declares its multiplicity with
an explicit count. And a normalized match is reported rather than swallowed — the harness prints
`drifted`, the check emits a warning, and the string is a repair waiting to be made.

### The vacuity floor and the declaration cross-check

**Until 2026-08-04 this gate had the defect it exists to prevent.** Handed a
proofs file it could extract nothing from, `check_tampers.py` printed `0 proofs
declared`, `0 errors, 0 warnings`, and exited 0 — green while checking nothing.
Every check it makes is per-proof, so zero proofs is zero checks, and a clean
exit says the opposite.

**A bare zero-floor would not have sufficed, and the negative control that
establishes this is worth stating rather than summarising.** Extraction
degrading from 61 proofs to *one* is the same defect as degrading to zero, and a
zero-check waves it through: a file with **61 declaration-shaped lines and one
extractable proof exited 0** before this landed. The route is not hypothetical —
`_INVOCATION` is anchored at `^` and tolerates no leading whitespace, so
wrapping the declarations in a `for` loop or a function, indenting them by two
spaces, drops every one of them and is an ordinary-looking refactor.

Two guards, because they fail in different directions and neither covers the
other:

- **the vacuity floor** — zero extracted proofs is an error, unconditionally.
  There is no third reading under which reporting success is honest.
- **the declaration cross-check** — every declaration-shaped line in the file
  must have produced a proof. It carries **no constant**, which is what lets it
  travel to the older revisions `--proofs` and `--root` exist to score, and it is
  deliberately *looser* than `_INVOCATION` rather than a second strict
  implementation of it. A stricter second opinion would report rot it had
  invented, which is the failure this whole file is written against.

The absolute count is pinned where the revision is known — `EXPECTED_PROOFS` in
`tests/unit/test_tamper_matching.py`, in the shape `selftest.py` uses for
`GEN_EXPECTED`. It does not belong in the tool, because a hard minimum there
would fail the documented cross-revision workflow, where an older proofs file
legitimately declares fewer. Neither floor notices a proof being *deleted*;
`EXPECTED_PROOFS` is what does.

### The rot check runs in the ordinary suite, and that is the point

Nothing about detection is new; the harness has failed a no-op tamper since Phase 2. What was
missing is a detector cheap enough for the person who *causes* the rot to run. The harness needs
pytest, a Go toolchain, a Linux kernel and root, and takes minutes. Thirteen proofs rotted inside one
session because nothing that ran during that session looked at them.

`check_tampers.py` needs none of that and finishes in well under a second, so it sits in three
places: the fast CI job, `tests/unit/test_tamper_matching.py` in the ordinary `pytest` run, and a
pre-commit hook if you want one. That file also carries the fixtures — the two real 2026-08-03 rots
against the source that caused them, plus the refusals that keep the tolerance honest.

### What none of it catches

- **A tamper that applies cleanly and removes the wrong thing.** The test fails, the harness scores
  it `proved`, and every mechanical check above is satisfied. `proof_attribution.py` prints the
  evidence a human needs — the node ids that went from passing to failing — and decides nothing,
  because no threshold separates "an unexpected test failed" from "this file covers the mechanism
  from two angles."
- **A test that is weak in the same direction the mechanism is.** A proof shows the test notices the
  edit that was made, never that it would notice a subtler one.
- **Rot in a proof for a test that cannot run here.** A skipped arm is scored `SKIPPED` and its
  tamper is never applied — but `check_tampers.py` reads the source statically and so covers those
  four arms on any host, which is the one place the static check is strictly stronger than the
  harness.

### The emptiness-test inversion — `git diff` cannot tell "unchanged" from "changed back"

**Read this before mounting this tree into a container.** On 2026-08-05 a pass bind-mounted the
repository **read-write** into a container whose image carried its own copy of
`src/supervisor/preflight.py` at the commit under test. The container copied that file over the
working tree, silently reverting an entire unfinished implementation.

The check meant to catch that was `git diff --stat`. It printed nothing — and nothing is what a clean
tree prints, but nothing is *also* what a tree prints once your work has been replaced by the
committed version. The check was **exactly inverted with respect to the failure it existed to
catch**: the more completely the work was destroyed, the quieter the signal. An emptiness test over a
diff against `HEAD` is satisfied by "I changed nothing" and by "my changes are gone" identically, and
cannot separate them.

`check_tampers.py` caught it two steps later by reporting `NO_MATCH` on all three new proofs, and the
reason is structural rather than lucky: it reads for strings only the *new* implementation contains,
so it is a **presence** test. A check that names what must be there fails loudly when it is not; a
check that names what must be absent passes on an empty tree.

Two defences, and the first is free:

- **mount `:ro`.** No measurement over this tree needs write access to it. Every arm behind
  [finding 026](../specs/002-spec-aware-agent-runtime/findings/026-pivot-root-check-measured.md) was
  re-run read-only and reproduced identically.
- **verify by presence, not absence** — `git status --short` on a tree you expect to be *dirty*, or a
  grep for a string only your own work contains.

### Reading an instrument is not measuring it — plant the case instead

**A claim about what one of these checks *would* do is worth nothing until something has done it.**
Twice on 2026-08-05 a defect in a harness was asserted from reading its source and relayed onward as
though it had been observed, and both times the defect did not exist. Each cost a downstream pass real
work looking for something that was not there.

The instance that names this section: a proof whose target test no longer exists was believed to score
`proved`, on the reasoning that `pytest` exit 4 is a *usage* error and the existing guards were built
around exit 5 and zero collection. Plausible, and false. Two proofs were planted — a nonexistent test
name inside a real file, and a nonexistent file — and both came back `NO TEST`, unproven. **Three**
independent guards catch it, and each was confirmed separately rather than inferred from the first:
`check_tampers.py` catches it statically and **names exit 4 in its own error text**, so the case was
closed knowingly; `baseline_py` returns `ABSENT`, which is the layer the planted proofs actually
reached; and `proof()`'s collection check would take it regardless, because real exit-4 output begins
`ERROR: not found:` and contains no `N failed`. Written up in
[finding 027](../specs/002-spec-aware-agent-runtime/findings/027-lifecycle-edge-set-divergence.md) §9.

The tell is the same in both instances and is easy to say out loud: **the claim describes behaviour,
and the evidence is a file.** A guard's source tells you what its author intended to cover, which is
exactly the thing in question when you suspect a gap — the gaps live in the distance between intent
and effect, and that distance is invisible from the inside. It is the same reason a removal proof
exists at all: this whole directory rests on the position that a mechanism is proved by deleting it
and watching something fail, not by reading it and agreeing.

So the rule is cheap, because planting a case is nearly always a one-liner here: **before reporting
that a check has a hole, put the hole in front of it and record what it printed.** If that turns out
to be expensive, say the claim is *unverified* in the same breath as making it. An honest "I have not
run this" costs the next reader one sentence; a confident wrong one costs them an afternoon.

### Never state a classifier as a complement — enumerate the accepting set

**A rule of the form "anything but X means success" is one unknown value away from inverting the
verdict it reports**, and on two consecutive passes in August 2026 a rule written that way would have
done exactly that to a kernel containment gate.

The first was **"any errno but `EPERM` means the syscall reached the kernel"**, proposed for the
`pivot_root` check. It fails because AppArmor's `build_pivotroot` hook denies with `EACCES`, before
every argument check — so a host where an LSM refuses outright would have been reported as a working
containment gate. The second, one pass later, was **"the two errnos differ, therefore the call was
permitted"**, proposed to tell a genuine kernel error from one forged by a seccomp filter. It fails
for a different reason on the same cell: `security_sb_pivotroot()` runs *after* `user_path_at()`, so an
LSM-denying host answers `EACCES` to one probe and `ENOENT` to the other — two different errnos, on a
host that refused. Both would have gone green on a refusal.

What made the shipped check sound in both cases was the opposite construction: a **closed list** of
the errnos that mean *permitted* (`EBUSY` and `EINVAL`, each for a stated reason), with everything else
falling to `refused-unattributed`. That fails closed on a value nobody anticipated, including `ENOSYS`.
The measured detail is in
[finding 026](../specs/002-spec-aware-agent-runtime/findings/026-pivot-root-check-measured.md) §7–8.

So the rule, which is about how a *brief* is written as much as a check: **name the values that mean
yes and refuse everything else.** An error space is open — a kernel version, an LSM, or a container
runtime can add a member at any time — so reasoning about it by complement quietly assumes a
completeness nobody holds. One corollary worth carrying: any claim about a `pivot_root` errno pair must
say which kernel line it was derived against. The ordering above is v6.12's; mainline hoists the path
lookup above `may_mount()`, which makes an unprivileged mainline host answer with two distinct errnos
by a third route.

### A derived copy and its authority share a basename — "I corrected `plan.md`" was true and useless

**On 2026-08-04 a pass struck a falsified inference from `OD-24` and recorded in its propagation note
that it had corrected "`plan.md`'s OD-24 note". That was true. It corrected feature 002's plan, which
is a derived view; the entry itself lives in feature 001's plan, which is the register.** The falsified
inference stood live in the authority for a day while a committed note attested that it had been
fixed, and the note's relative link resolved exactly as written — to the author's own sibling, because
that is the directory they were working in. Corrected at `90a54cf`.

**No gate can see this**, and the reason is worth stating precisely: link resolution asks whether a
path *exists*, not whether it is the path the sentence *means*. This is the same blind spot as
`identifier-resolution` passing a mis-citation because the wrong identifier still resolved.

The exposure is wide and was measured rather than assumed: this corpus has **three** `plan.md`, four
`spec.md`, three `tasks.md`, three `data-model.md`, two `requirements.md` and two `NOTES.md`, plus the
`README.md` and `SKILL.md` families — and roughly 49 references to a bare `` `plan.md` `` across ten
files. **That is exposure, not defects.** Exactly one real instance has been found, and most bare
references are unambiguous to a reader who is already in the right directory. No check was built, for
the same reason `register-range` was left hand-maintained: a rule firing on every bare basename would
be almost entirely false positives.

The tell is cheap and does not need a tool: **when a note claims to have corrected a document, ask
whether the thing corrected was the authority or a view of it.** This is the second instance this week
of a correct edit to a derived document leaving the authority standing — the first being the
citation that three sweeps declined to follow, where the label was right and the document it pointed
at carried the false claim. Both share one shape: *the artifact you edited and the artifact that
governs are not the same artifact, and its name does not tell you which one you have.*

### Staging explicit paths protects you from another pass's working tree, not from its index

**On 2026-08-05 the cost-table pass staged explicit paths — the defence this repository adopted after
two sweep-ups of other passes' work — and it still disturbed a concurrent pass's *pre-staged* index
entry, converting a staged rename into an unstaged delete plus an untracked file.** Nothing was lost,
because the shape was noticed. The shape is what matters: from there a `git commit -a` commits the
delete without the add and drops the renamed file out of version control entirely. That has already
happened twice here, to findings 025 and 028, and a 492-line finding came close to going the same way
the same day.

`git add <path>` is a statement about the working tree. It says nothing about what was *already* in
the index when you arrived, and a rename staged by someone else is two index entries that only mean
"rename" while both are present. Touch one and the pair stops being a rename without anything
reporting an error.

**So the rule is a read, not a write: before staging anything, read `git status` for staged entries
you did not create.** If there are any, a concurrent pass is mid-commit and the index is not yours to
edit. This is cheap, it is the only signal available, and no gate can supply it — a hook runs after
the damage is staged, and by then the two halves of the rename are already separated.

### A proof arm with no terminator does not report a hang; it reports whatever the eventual kill looks like

**On 2026-08-05 the `T065 wiring` arm ran for 56 minutes of continuous CPU without returning, and the
archived record from earlier that evening scored the same arm `proved`.** Both are explained by one
mechanism. `proof()` reads a **non-zero exit** as the tampered test having noticed the mechanism was
removed. A killed process is also non-zero. So a hang does not stay a hang: somebody eventually kills
the pytest child, command substitution returns 130, and the arm is printed `proved` and recorded
`proved` in a run that then completes green.

The arm could not have been earned. Its tamper removes the loop's only `backstop.check` call while the
test's own ceilings are all deliberately out of reach — that is what makes it a second guard rather
than the first one counted twice — so with the backstop gone the runaway loop has no terminator of any
kind. **The test cannot fail. It can only not return.** Measured at `1208e06` on a tree carrying no
other changes: no return in 90s.

**The scoring half was measured rather than inferred.** A planted arm whose tamper sends its own
process `SIGTERM` — which is what an externally killed hang looks like from `proof()`'s side — printed
`proved` and the harness exited **0**.

Four fixes, because there are four defects and each leaves the others standing:

- **Scoring, in `proof()` and `go_proof()`.** A status above 128 is a signalled child, and a signalled
  child evaluated no assertion. It is now scored `unproven` with reason `proof-killed-by-signal`
  rather than `proved`. This is the one that closes the fabrication route: without it a cap only makes
  the hang rarer, and any *other* way of killing an arm still buys a green tick.
- **Per arm, in the harness.** `tools/proof_timeout.py` caps every arm and exits `124`, which
  `proof()` scores as `timed-out` — its own outcome, never `proved` and never `skipped`, named in the
  summary and failing the run. A skip would have been the worse of the two mistakes available: it
  reads as "not attempted in this environment", which is how an arm leaves a green run unnoticed.
- **Per test, in the test.** A cap turns a hang into a red run; it does not turn it into a proof. The
  arm still has to be able to *fail*, so its stub provider now refuses past a call count an order of
  magnitude above any maximum `CallCountBackstop` will accept. Untampered the backstop trips first and
  the guard is never reached; tampered it raises in under two seconds.
- **Per arm again, in `proof_attribution.py`.** That tool applies *every* tamper too, ran with no cap
  of any kind, and sits in the same CI job under `if: always()` — the one remaining uncapped path over
  the arms the cap was built for. It did not hang only because the per-test bound above held the line,
  which is the test-level fix doing the cap's work. It now runs each tampered test under the same
  `tools/proof_timeout.py` at the same `REMOVAL_PROOF_TIMEOUT`, and — the load-bearing half — a killed
  run gets its own report rather than the `fails NOTHING` line. `fails NOTHING` says *the test still
  passes*, which is a reading of a run that finished; printing it for a run that was killed is the
  harness's fabricated `proved` one tool over. A cap fired is `TIMED OUT`, a signal is `SIGNALLED`, and
  both are named again at the foot of the listing. Verified by planting, not by reading: two throwaway
  arms — one whose tamper removes a loop's only bound, one whose tamper makes the test signal its own
  process — report `TIMED OUT` and `SIGNALLED` under an 8-second cap, where the same plant against the
  pre-fix tool did not return in 75 seconds.

**The generalisation is the part worth keeping.** Whenever a tamper removes the *only* thing that
stops a loop, the tampered test has no failure mode left. Ask it of every arm whose test runs
something unbounded, and give the test its own bound — one that cannot be mistaken for the mechanism
under proof.

### An outer bound inside an inner bound's window does not make the failure faster, it makes it anonymous

**On 2026-08-06 (`acdf5f7`) every job in `.github/workflows/ci.yml` was given a `timeout-minutes`
for the first time. All but one took its value from the job's own observed duration or from a stated
floor. The `removal proofs` job could take neither, and the reason inverts the intuition that a
tighter fallback is a safer one.**

The cap above is the primary bound: `tools/proof_timeout.py` at `REMOVAL_PROOF_TIMEOUT`, 300s by
default, read at that default by both `tests/removal_proofs.sh` and `tools/proof_attribution.py`. Its
entire product is a *written* verdict — the arm is scored `timed-out`, named in the summary line, and
carried into the JSON record. **That record is written from exactly two places in the harness: the
baseline abort, and the line after the last proof.** The per-arm lines accumulate in a `mktemp -d`
that an `EXIT` trap removes, deliberately — the harness's own comment says they live there "so an
interrupted run cannot leave a partial file behind that looks like a result". So a harness killed
part-way through leaves no record at all, and not just for the arm that hung: for every arm in the
run.

A job that exceeds `timeout-minutes` is **cancelled**, not failed
([GitHub's workflow-syntax reference](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idtimeout-minutes)),
and the runner signals the running step's process tree. The `if: always()` steps that publish the
totals, run the attribution and upload the artifact are **not** skipped — GitHub's
[workflow-cancellation reference](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-cancellation)
says the server re-evaluates the unfinished steps' conditions, `always()` evaluates true, and they
continue into a five-minute forcible-termination window. They run and there is nothing to render.
The renderer exits non-zero on a missing record, which is correct and useless: it reports the
absence, not the arm.

**The comment committed at `acdf5f7` states this one step too strongly** — it says the `if: always()`
steps "do not run". Per the reference above they do. The bound it justifies is unaffected, because
what those steps need does not exist by the time they run, but the mechanism as written in
`.github/workflows/ci.yml` is wrong and is still there.

So the bound is a **sum, not a multiple**, and the arithmetic is the part a future editor would
otherwise re-derive or casually tighten: 318s observed maximum, from the 40-run table in that file's
own header, plus 300s for one arm reaching the cap in the harness, plus 300s for the same arm
reaching it again in `proof_attribution.py`, is 918s — 15.3 minutes, rounded up to 20. That leaves
882s of hang budget over the observed maximum, two full cap firings and change. Three simultaneously
hanging arms exceed it, and that is the deliberate stopping point: at three the cap is not containing
the problem, so losing the record is no longer the worse outcome.

**The rule generalises past CI: when an inner mechanism's whole output is a record it writes at the
end, an outer bound set inside the window the inner one needs converts an informative failure into a
silent one.** They move together — raising `REMOVAL_PROOF_TIMEOUT` without raising the job bound
trades the cap's diagnostic for a cancelled job. And the corollary for the other jobs is worth one
sentence, because it is the honest half of the same pass: their 5 minutes is a **floor**, stated as
one rather than dressed up as a derivation, since the jobs it covers finish in under a minute every
time and a value scaled off that work would be measuring PyPI rather than the job. It still fires on
a hang, and it is 72x tighter than GitHub's 360-minute default.

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

**Accepted.** ~~And live in the current output.~~ **Corrected 2026-08-03 — the gate
is at zero and this section described a state it had left.** Re-run against the
working tree, `check_corpus.py` reports **0 errors and 0 warnings**; re-run against
the tree as `git archive cee7ff8` materialises it, it reports **0 errors and 32
warnings, every one `numeric-provenance` on a multiplier**. So of the four entries
below, one was live at `cee7ff8` and has since been repaired in the documents, and
two were *never* in the output at either revision — the section asserted an
instrument's behaviour without re-running it, which is the same defect the entry on
[the advisory](#what-was-measured-and-where-the-earlier-claim-did-not-hold) records
one flight up. Each entry keeps its reasoning, which is still right about *why* the
construct is accepted; what is struck is the claim that you will see it.

- *A price in a bare table cell.* `research/05` has a pricing table whose cell
  is just `| $2.50 |`, with no per-unit marker on the line. ~~It is reported. One
  instance corpus-wide.~~ **It is not reported, at either revision.** The cell is
  still there — `research/05-frontier-lab-agent-definitions.md` carries it — so the
  accepted construct is real; what is wrong is the claim that the checker surfaces
  it. Anything asserting
  which figures reach the output has to be re-run rather than remembered.
- *Derived aggregates.* `$24.82` and `$18.15` in `VERDICT.md` are sums computed
  from findings figures, not quoted from one. ~~They are correctly reported as
  unsourced and are not errors of fact.~~ **Neither is reported, at either
  revision**, and they are still not errors of fact. `$24.82` has since been struck
  and superseded in `VERDICT.md` in the house style, which exempts it outright.
  `sum-arithmetic` verifies the arithmetic where the working is shown.
- *Percentages and fractions.* `percent_decimal` and `fraction` are implemented
  and **off by default**. Turning them on adds roughly 125 violations, nearly all
  external benchmark and vendor figures from `research/01`, `/04`, `/05` and
  `/13`. Enable them in `numeric_kinds` for a targeted sweep of one document,
  never for the gate.
- *Third-party multipliers with no citation.* ~~**32 warnings, and they are the
  reason this gate is not at zero.**~~ **32 warnings at `cee7ff8`, and they were
  the reason that gate was not at zero. All 32 are now cleared and the gate is at
  zero** — the fix named at the end of this entry was applied, in commit `1f5450b`,
  as eight inline citations across five `.cursor/skills/*/SKILL.md` files; one
  citation covers every claim within four lines of it, which is why eight edits
  closed thirty-two warnings. The entry is kept because the *mechanism* is what
  matters and it is unchanged: the rule still fires the moment a citation is
  dropped. Typing the multiplier lookup surfaced them;
  it did not create them. All 32 were external figures — Anthropic's ~15× token
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
  32 carried none, and no citation sat within four lines of any of them. The fix
  was a citation on each line, which belonged to the documents and not to this tool,
  and that is what was done.
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
- **A contract citing requirements that do not govern its subject — attempted
  2026-08-03 and *not* implemented, because no threshold separates it from clean
  work.** This is the sharpest sub-case of semantic staleness above: two artifacts
  written independently, each internally coherent, wrong only in relation to each
  other. Four instances so far, two of them confirmed by hand against the
  production contracts. `contracts/trace-record.md` cited **FR-030** and **FR-031**
  for its span shape; those are the two drift requirements and neither mentions
  spans, and **FR-038** governs it. `contracts/artifact-versioning.md` had canonical
  serialization as its title subject and its first section, and none of **FR-027**,
  **FR-028**, **FR-034** or **FR-054** says a word about it; **FR-055** governs it.
  Three sibling contracts — `configuration.md`, `egress-policy.md`,
  `result-record.md` — audited clean, giving a five-contract fixture set with
  hand-established ground truth, two bad and three good.

  **What was tried.** Significant-term overlap between a contract's title and
  leading section and the text of each requirement it cites, scored against the
  best-matching cited requirement. 288 configurations were swept — three stoplists,
  stemming on and off, code-fence stripping on and off, three definitions of the
  subject, two citation scopes, and four similarity metrics. 14 separated the two
  bad contracts from the three good ones. Nine of those 14 were then eliminated by
  two controls that a usable rule has to pass and a fitted one does not: the rule
  must go **silent** on the repaired contracts, and it must go silent under a
  citation-only ablation in which the governing requirement is added to the header
  and nothing else in the file changes. Five survived, all sharing one shape —
  Jaccard similarity, header-scope citations, subject taken as title plus leading
  section.

  **The surviving shape has real signal, which is why this entry is long.** Ranked
  against all 57 requirements, the metric puts the hand-identified governing
  requirement **first of 57** for `artifact-versioning` (FR-055) and **third of 57**
  for `trace-record` (FR-038), unaided. For all three clean contracts the
  best-scoring requirement corpus-wide is one they already cite; for both bad ones
  it is not. The signal is not the illusion here.

  **What killed it was the false-positive probe, and the probe is not adversarial.**
  Contracts in this corpus cite between four and fifteen requirements, so a clean
  contract that simply cites less densely is a style difference and not a defect.
  Dropping one and two citations from each clean contract gives 187 clean cases, and
  against those:

  | Rule shape | Defect side | Worst clean case | Usable window |
  |---|---|---|---|
  | best-uncited advantage, fire when ratio ≥ T | `1.536` | `1.700` — `result-record` less two of its eight citations | **none** |
  | rank of best cited requirement, fire when > T | 5 | 5 — `configuration` less two of seven | **none** |
  | absolute similarity, fire when best cited < T | `0.0873` | `0.0913` — `result-record` less two of eight | `0.0040` wide |

  The two relative shapes have **no window at all**: a clean contract that omits two
  citations scores *worse* than the worse of the two real defects. The absolute shape
  has a window `0.0040` wide in a Jaccard score — 0/187 false positives at `0.090`,
  one at `0.092`, nine by `0.120`. A conjunction of the two appears to separate, and
  does not: the ratio term fires at any value from `1.05` up, so the separation is
  carried entirely by the same four-thousandths of absolute similarity. **That is a
  number fitted to the third decimal place of a text-similarity score over five
  documents, not a threshold**, and `threshold_probe.py` exists because this project
  already learned what an unpinnable constant costs. It would fire on the sixth
  contract someone writes, and a gate rule that fires on clean work gets disabled or
  worked around, which costs more than the two defects it would have caught.

  **The narrower version that is worth having is not a check.** The ranking is
  useful precisely where the threshold is not: run as an **advisory listing** — for
  each contract, the highest-scoring requirements it does *not* cite — it named the
  right requirement ~~first and third out of 57~~ **first of 57 for one of the two
  and not at all for the other; see [The advisory](#the-advisory--cite_advisorpy),
  where it was built and measured on 2026-08-03 and where the second half of that
  claim did not survive checking**, with ~~no false-positive cost~~ **a false-positive
  cost that is real but survivable — 33 false claims across 184 ablated clean cases,
  and none on any clean contract in its real state**, because
  an advisory fails nothing. That is a human-run audit aid rather than a gate, so it
  belongs beside `gen_claims.py` rather than in the check set, and ~~it is deliberately
  not built here: the instruction that produced this entry was to implement nothing
  unless the gate bar was met.~~ **it is now built there.**

  **A zero-overlap rule** — fire only where a contract's
  best cited requirement shares no significant term at all with its subject — was
  also considered and rejected: neither real defect reaches zero (`0.0873` and
  `0.0515`), so it would have caught neither, and a branch no fixture can reach is
  the unfalsifiable safeguard this file exists to warn about.
- **Which of two mechanisms a claim names.** The recurring `M1`-versus-`M2`
  ablation error is a statement about which named thing causes an effect. Both
  names exist, both are defined, the sentence is well-formed. Undetectable
  without encoding the claim itself.
- **Prose that contradicts an adjacent table.** `finding 010`'s prose named one
  mechanism while its own committed table showed two. Both halves are internally
  valid.

  **Widened 2026-08-04 to one cell against another inside a single row**, which is
  the same hole one level down and is the harder half to see, because the two
  halves are adjacent rather than separated by a document. `7063b32` corrected the
  middle column of `specs/002-spec-aware-agent-runtime/plan.md`'s Linux-only
  Complexity Tracking row from *all three mechanisms are kernel facilities* to
  *each of the four depends on a kernel facility*, and left the next column of the
  same row reading *two of the three mechanisms are absent*. Nothing here could
  object: the row's cell count is right and its pipes balance, so
  `table-integrity` is satisfied; both cells are well-formed prose; and what they
  disagree about is a bare integer, which the *figures with no distinctive shape*
  entry below records as not extracted at all.

  **The reason it survived is worth more than the instance, because no check will
  ever cover it.** Two commits swept that file for the framing after the clause
  landed, `7063b32` and `c48332f`, and each enumerated what it believed was the
  complete list. Both sweeps were `rg`-shaped and **the pattern matched both
  columns** — so this was not a search that missed a site. The site was found, the
  match was read, one cell was fixed, and the row was recorded as done. **The unit
  of work was the match and the unit of correctness was the row**, and wherever
  those two differ a sweep reports a completeness it does not have.

  So the question to ask on a propagation pass is not *did I visit every match*
  but *did I finish every unit the claim lives in* — the row for a table, the whole
  bullet for a bullet, every site that states **or implies** a figure for a
  corrected count. A grep hit inside a structure whose other parts make the same
  claim is a place to start reading and not a place to stop editing.

  **A second failure mode, found by the pass that fixed the first, and it is the
  more expensive one: a correctly-judged non-instance can be a pointer.**
  `plan.md`'s Phase 0 row reads *the three mechanisms* as a label for
  `research.md` §3's subsection structure. Three passes each judged it a
  non-instance and each was right — but all three stopped there, and §3 itself
  asserted twice that *all three are Linux kernel facilities*, the exact sentence
  `7063b32` had corrected in the two `plan.md` lines derived from it. **Declining
  to edit a citation is not the same as declining to follow it**, and a label
  ruled out as a claim is still a route to the document it names. Where a sweep
  finds a non-instance that *cites* something, the cited unit joins the list.
  This is
  recorded here rather than in a skill because it is a claim about sweep
  completeness rather than about evidence, and because it belongs beside the
  residue it explains: the `register-range` entry below, whose six hand-maintained
  OD-range sites are held by a standing obligation on a human, is the same shape —
  a gap this tool has decided not to close, with the failure mode written down
  where the gap is recorded rather than somewhere else.
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
  **Narrowed 2026-08-05: one check now reads product source.**
  `lifecycle-taxonomy` parses `src/contracts/terminal.py` with `ast` — one file,
  named in `config.json`, for one fact. That is not a general capability and
  should not be read as one: the check knows the shape of a `TerminalState`
  binding and the `TAXONOMY` tuple and nothing else about Python, and it
  **parses rather than imports** because `--root` may point at a fixture tree
  and a corpus checker that executes what it checks has a failure mode no regex
  does.
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
  that "the decision log OD-01 through OD-14" is not checked.
  ~~Two live sites in `specs/002/spec.md` say exactly that and neither is read.~~
  **Corrected 2026-08-03 — the residue is real and this entry named the wrong
  files and the wrong state.** `spec.md`'s two sites do **not** say that: both carry
  ranges whose superseded upper bounds are struck and whose live bound is
  **OD-21** — so they are current, not stale. The genuinely unadvanced sites were in
  `specs/002-spec-aware-agent-runtime/research.md` and
  `specs/002-spec-aware-agent-runtime/checklists/requirements.md`, and the two have
  since diverged. **`research.md` was corrected on 2026-08-03** and now carries the
  same struck-and-advanced form, with a note recording that a prior pass had read
  the sentence as a claim about *provenance* rather than about *extent* and left it
  alone on that reading. **`checklists/requirements.md` is deliberately frozen at
  the fourteenth entry**, because it records what a dated validation run read and
  advancing it would claim coverage that run did not have. So of the corpus's ~~five~~
  **seven** OD-range sites, ~~**four are current**~~ **six are current**, one is
  deliberately frozen, and none is
  stale — the residue is a hole, not a live defect.
  **Recounted 2026-08-04, and the undercount was this entry's own.** It missed
  `docs/spec-kit-workflow.md:137` and
  `specs/002-spec-aware-agent-runtime/plan.md:11`, both of which carry the same
  struck-and-advanced range as the three it did name. The full seven are
  `docs/spec-kit-workflow.md`, `specs/002/spec.md` **twice**, `specs/002/plan.md`,
  `specs/002/research.md`, `specs/002/checklists/requirements.md` (the frozen one),
  and `specs/001-discovery-validation/plan.md`. **Undercounting matters more here
  than anywhere else in this file**, for the reason under the next paragraph: this
  entry is the corpus's only record of how wide the unguarded surface is, so a
  count that is short understates the residue by exactly the sites it forgot.
  ~~**All four unread sites**~~ **All six unread sites fail at the same place, and it is earlier than this entry
  first said.** Verified 2026-08-03 and re-run 2026-08-04 by executing `_RANGE` and
  `_is_whole_register_claim` over all seven raw lines: the five struck-and-advanced
  sites and the frozen one **all return zero regex matches**, because `_RANGE`
  requires the second identifier to follow the separator immediately and **any
  markup sitting between them breaks it** — `~~` at the advanced sites, `**` at the
  frozen one. The whole-register test is never reached at any of the six, so an
  earlier reading of this entry that attributed the frozen site to that test was
  wrong. The one site that *is* read is `plan.md`'s parenthesised
  `(OD-01 through OD-25, …)` *(advanced from `OD-21` as the register grew; the
  generator writes this one)*, which matches and is judged a whole-register claim —
  which is why the OD register is guarded at all. A future site written as plain
  prose, unparenthesised and with no markup between the bounds, would be caught by
  neither the regex path nor the guard. Dropping the parenthesised-or-listed
  requirement was measured — it reports nothing on the current corpus — but it is
  free only because that U-01 counterexample happens to be struck.

  **These six sites are hand-maintained by decision, not by oversight, and this
  entry is the only place that says so.** The owner has settled that
  `register-range` stays as it is rather than being widened to read them, on
  measured grounds: relaxing `_RANGE` to tolerate markup between the bounds catches
  **zero** stale sites on the current corpus — all six are already advanced or
  deliberately frozen — while false-positiving on the one site that must stay
  frozen, `checklists/requirements.md`, which records what a dated validation run
  read and whose whole point is that it does not advance. So the regex change buys
  nothing and costs a permanent false alarm at the one place a false alarm would be
  most misleading. **The consequence is a standing obligation on a human**: when the
  OD register grows, six sites advance by hand and nothing anywhere will say if one
  is missed. That is the residue, it is accepted rather than unnoticed, and the
  count above is how wide it is.
- **An `unconstructible` claim that has outlived its scope.** Two findings once
  asserted opposite things about the same refusal cell — one saying an LSM refusal
  could not be built on any available surface, the other having since built it —
  and nothing caught the contradiction. A check was proposed on the
  `lifecycle-taxonomy` precedent and **declined on this one, measured rather than
  argued.** The candidate rule — an `unconstructib*` or `unconstructed` token with
  no scope qualifier nearby — was built and run over the real corpus through
  `corpuscheck`'s own masking at three window widths: **15 firings at the tightest,
  8 at 30 and 60 characters, and zero real defects at any width.** Worse, **three of
  the seven correctly-scoped sites are among the firings**, escaping the qualifier
  test only because a code span or a `**` sits between the token and its scope —
  the identical markup-between-the-bounds failure that made relaxing `_RANGE`
  unacceptable one bullet above. It also fires on `unconstructible in principle`,
  which is a *different sense* of the word that must never be rescoped, and on a
  finding's own past-tense narration of the cell it corrects. Sparing those would
  mean growing the qualifier vocabulary into a list of the phrasings the corpus
  already happens to use, which is fitting the rule to the corpus rather than to
  the defect. **And the `lifecycle-taxonomy` shape does not transfer**: that check
  works by reconciling two *machine-readable enumerations* against each other, and
  there is no register of which refusal cell is constructible on which surface to
  reconcile against — the thing that would have to exist first is the artifact, not
  the check.
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

## Which of these run in CI, and the one that deliberately does not

Until 2026-08-04 **none** of them did. Every corpus claim in this repository
rested on somebody having remembered to run them, which is the same standing as
no gate at all. `.github/workflows/ci.yml` now has a `corpus` job holding four,
in this order, and the order is the argument:

| step | why it is where it is |
|---|---|
| `selftest.py` | **First.** A validator whose regex stopped matching passes everything, so `check_corpus.py` going green proves nothing until something has shown the checks still fire. This runs the whole set against a corpus where every check must fire and one where none may. |
| `threshold_probe.py` | A green self-test shows each check *fires*, not that the constant it fires at is the right one — `catalog-line-count` carried `TOLERANCE = 2` for its whole life and the self-test could not tell it from `0`. Wired **because it was measured**: 34 perturbations, 5.2 s. A sweep that costs five seconds does not need a schedule. |
| `check_corpus.py` | Errors only. `--warnings-as-errors` is deliberately not set — the warning classes that actually fire are line counts and register ranges, which go stale for the minutes between an edit and `gen_claims.py`. A gate that flaps gets worked around. A second step prints the full report, warnings included, to the run page and cannot fail. |
| `gen_claims.py --check` | The only thing that notices that window. |

`cite_advisor.py` is **not** wired, and leaving it out is the decision rather
than an oversight. It has no threshold and no finding it makes changes its exit
code — by design, because the gate rule underneath it was built, measured
against 184 ablated clean cases, and rejected. Wiring an advisory into a gate
rebuilds exactly that rejected rule. Running it ungated on every push emits a
permanent listing a reader learns to scroll past, which is how its one true
positive gets lost. It stays a human-run audit aid.

### `gen_claims.py --check` reports per generator, and zero is an error

`--check` used to print one total. A generator that matched **nothing** printed
`0 stale`, which is also what a clean tree prints — the two were
indistinguishable, so a marker rename or a reflowed table could take
`register-range` to zero and `--check` would stay green over six claims it was
no longer reading. It now breaks the count out per generator and exits 1 when
any requested generator matched no sites. There is no threshold to tune: the
floor is one, because a generator with no sites is either dead or looking in
the wrong place.

## Reading a pytest run back — `pytest_outcomes.py`

`436 passed, 1 skipped` names no skip, and a privileged test that skipped for
want of a kernel facility is indistinguishable in that sentence from one that
ran. The CI pytest job therefore runs with `-rs` (names skips in the log) and
`--junitxml` (names them durably, in an artifact — the log for run
30919927355 turned out to be unreachable through `gh`, so a reason that exists
only there is a reason nobody can read). This renders those reports.

```sh
python3 tools/pytest_outcomes.py \
  --collected pytest-collected.txt \
  unprivileged=pytest-unprivileged.xml \
  privileged=pytest-privileged.xml
```

It exits non-zero for the three things a pytest exit status cannot express:

- **A missing or unreadable report.** The suite claimed to run and left no
  record of what.
- **A half that collected nothing.** Usually a marker expression that stopped
  selecting.
- **A half that collected work and skipped all of it.** Measured on macOS on
  2026-08-04: `pytest -m privileged` reported `44 skipped, 461 deselected` and
  **exited 0**. Forty-four kernel-mechanism tests were collected, declined, and
  scored as a pass. OD-17 has no degraded mode, so that is a failure.

It also takes a third reading the two halves cannot take about themselves.
The suite is run as two disjoint halves and the pair is taken for the whole,
and nothing verified that it is: a marker expression that stopped selecting a
file leaves those tests in *neither* half, and both halves stay green because
each is internally complete. `--collect-only` over the undivided suite gives
the denominator, and the renderer says so explicitly either way.

`--collected` is optional and the partition line is simply omitted without it.

One deliberate refusal: if the interpreter cannot build an XML parser, every
report reads as unreadable for a reason that has nothing to do with the
reports. It exits **2** with `CANNOT RUN` rather than reporting findings it did
not earn. This is not hypothetical — the system `python3` on the development
host has no `expat`, exactly as it has no `pytest`.
