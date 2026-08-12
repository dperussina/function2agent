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
| `--path GLOB` | Restrict the corpus. Repeatable. Checks that lose their inputs report as `skipped` rather than passing silently — so a narrowed run checks *less* than the gate and never stands in for it. |
| `--format text\|json\|summary` | `summary` is one line per check, for comparing runs. `json` is for tooling. |
| `--no-hints` | Drop the hint line. |
| `--config PATH` | Use a different `config.json`. |
| `--root PATH` | Point at a different repository root. |

Narrowing with `--path` is the reason checks announce themselves as skipped:
`--path README.md` removes every findings document, so `numeric-provenance` has
no authority set. Reporting that as "no violations" would be the false-negative
this tool exists to prevent, so it says so instead.

**Corrected 2026-08-12 — the sentence above was true of `numeric-provenance` and
was never true of every check, and `identifier-resolution` failed it in the
loud direction rather than the silent one.** At `2979c31`, `--path
specs/002-spec-aware-agent-runtime/tasks.md` reported **304 errors, all
`identifier-resolution`**, against the `FR` register the narrowing had removed —
two checks losing their authority set for the identical reason under the
identical flag, one declaring itself skipped and the other emitting hundreds of
false errors. `identifier-resolution` was the only check that erred loudly;
`identifier-gap` and `register-range` produced the same defect as warnings. All
three are repaired, and the measurement, the two ways the existing guard was
defeated, and the cost of the repair are in
[**Narrowing and the definition index**](#narrowing-and-the-definition-index).

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
| `instruments.py` | **The census.** Every instrument in the repository that can fail, what it checks, where it runs, and whether anything runs it automatically — with `--check` reconciling that list against `.github/workflows/ci.yml` in three directions so it cannot quietly stop being the set, and a fourth reconciling a second population — the workflow's own jobs, by mapping key *and* by `name:`, the string nothing used to read. `--run` runs the fast gates and names the ones it did not. See [The census](#the-census--instrumentspy). |
| `selftest.py` | Proof that each check fires, that none fires on well-formed input, and that the generator writes digits and nothing else. |
| `threshold_probe.py` | Proof that each numeric threshold is pinned: moves every tolerance, window, bound and distance by one unit and requires the self-test to break. |
| `fixtures/` | The two miniature corpora. See `fixtures/README.md`. |

## The check set

Nineteen checks in eleven families. Severity is **error** when the finding is
almost certainly a defect, **warning** when it is a defect *or* a judgement call
the author may have made deliberately.

| Check | Severity | What it catches |
|---|---|---|
| `numeric-provenance` | error / warning | A measurement-shaped figure quoted outside `findings/` that appears in no findings document. **error** when it appears nowhere else in the repository either — the transcription-error case. **warning** when it appears in other documents but no finding — the propagated-without-a-source case. Exact for `ratio4` and `money_cents` since 2026-08-03 — the lookup was a substring test, so `0.8961` was satisfied by a finding containing `0.89612`. |
| `ratio-arithmetic` | error | A count and the rate quoted beside it disagree: `53/69 = 0.7861`. Runs on findings too, because the numerator, the denominator and the rate are three statements of one fact. |
| `sum-arithmetic` | error | A total shown with its components does not equal them: `$18.15 ($7.59 + $10.55)`. |
| `table-integrity` | error | Three ways a table stops being one table: a blank line orphaning a row into body text, a row whose cell count differs from the header, and a run of pipe rows with no `\|---\|` delimiter. The orphan gap was one blank line until 2026-08-03; a new table is excluded by its delimiter, not by the gap, so a second blank was slack rather than a boundary. |
| `link-target` | error | A relative link resolves to nothing. |
| `link-anchor` | error | A `#fragment` names no heading in the target file. ~~Slugs follow GitHub's algorithm including its `-1`/`-2` duplicate suffixes.~~ **The `-1`/`-2` duplicate suffixes are implemented in `_anchors_for` and are correct. The slug itself is now measured against GitHub's renderer rather than described from its documented algorithm: `slugify` reproduces the emitted `id` on all 2,534 headings the corpus walked at `7a60dd3` on 2026-08-10 — the 2,425 anchored at `^#` and the 109 written inside a blockquote, both populations named because an earlier figure of this kind named neither. That is a dated count over a named set rather than a live ratio; the walked set grows whenever the corpus does. `_anchors_for` enumerates blockquoted headings as of the same commit.** *(corrected 2026-08-10, twice. The struck sentence was true about the suffixes and unmeasured about everything else, and the unmeasured half is what licensed two links to be written wrong — see [why a false positive is the worse failure](#a-checker-false-positive-is-more-dangerous-than-a-checker-gap-the-remedy-corrupts-the-correct-artifact-and-then-it-passes).)* |
| `link-label` | warning | The link *text* names a different document than the link *target*: `[finding 010](.../011-reachability...)`. The link works, so no existence check catches it, and a reader following the prose lands somewhere else. |
| `identifier-resolution` | error | `D-17`, `U-40`, `OD-06`, `FR-018`, `E15` and friends resolve to a definition. Dangling identifiers are how a superseded decision keeps getting cited. |
| `identifier-gap` | warning | A register with a hole in it. This corpus strikes superseded entries and keeps the row, so a gap usually means a deleted row that something still cites. **Reads one register per feature since 2026-08-12** for a namespace marked `per_feature` — `FR` and `SC`, whose tokens collide across features — because the corpus-wide union it read before was filled by the other feature's unrelated requirement of the same number, and all 22 rows of `specs/001-discovery-validation/spec.md`'s `FR` register could be deleted, individually or all at once, with every gate green. Zero firings on the clean corpus; the two rows it still cannot see are that register's endpoints, because a density reading sees holes and not truncations. See [the per-feature gap repair](#the-per-feature-gap-repair-and-the-22-rows-it-was-measured-against). |
| `findings-numbering` | error / warning | Duplicate numeric prefixes in `findings/` (**error**), a citation of a finding number that does not exist (**error**), and a gap in the sequence (**warning**). |
| `register-range` | warning | A prose summary of a register — `(D-01 … D-19)` — that stops short of the register's real last entry. **`gen_claims.py` now writes the standalone ones**; this rule is what fires when it has not been run, and is the *only* mechanism at the narrated sites the generator refuses. |
| `inventory-count` | warning | A prose count of repository contents that no longer matches the filesystem: `"eleven committed harnesses" when there are thirteen`. Six rules, each reading only the documents its own `files` glob names. A rule with no live site in that scope reports nothing, which is also what a rule that passes reports, so the check announces a skip per silent rule — see [the sweep](#every-rule-measured-against-its-own-scope). The `findings` rule had no live site in **any** revision of its scope until 2026-08-11, when the corpus-wide total arrived in the repository map. ~~The `findings` rule had no site in any document until 2026-08-03, because alone among the six its pattern required a trailing comma and so read `15 findings,` but not `15 findings and an index`; it has none again.~~ **Corrected 2026-08-11, and it was false in both halves.** No rule's pattern has ever contained a comma, in any revision, and the pattern as written matches `15 findings and an index` — replayed against the rule's own masking over all `14` revisions of `README.md` and `research/README.md`, seven each, it read nothing in every one of them, so there was no 2026-08-03 site to lose. *(The denominator read `266` until 2026-08-11, which is the repository's total commit count at `c9e42ad` rather than a revision count of either document; the replay's conclusion is unaffected.)* Widening its `files` to the findings index was measured and declined: see [the sweep](#every-rule-measured-against-its-own-scope). A rule whose subject is not in the tree at all declares that as a `precondition` and announces being out of scope rather than disabled — see [the `vendored-repos` disposition](#vendored-repos-is-out-of-scope-in-ci-by-construction-and-says-so-rather-than-reporting-an-incident). |
| `definition-count` | error / warning | A prose count of a *register* — "58 functional requirements" — against the definitions in the specification it describes. **error** when the target yields zero definitions, unconditionally; **warning** on an ordinary mismatch, because a deliberately historical figure is a real case and the strike convention is its escape. See [Why zero definitions is an error](#why-zero-definitions-is-an-error-and-not-a-comparison). |
| `count-versus-range` | error / warning | A register's stated size against the range quoted beside it — `thirty-one owner decisions (OD-01 through OD-31)`. Added 2026-08-11, after `specs/001-discovery-validation/plan.md`'s own header carried `thirty` against `OD-31` for a day with every gate green. Alone among the count rules its two operands sit in **one sentence**, which is why neither neighbour sees it: `register-range` reads the range against the register and passes, because the range is the half a generator maintains, and `definition-count` has no rule for owner decisions at all. Measured before it was written and again after: **1 pairing on this corpus, 0 firings**, and 1 pairing with 1 firing against the pre-correction text. The register noun is the scope control — thirty-two OD-range strings sit in this corpus and requiring `owner decisions` beside the count reduces the population to one. *(Measured 2026-08-11 over the loaded corpus, which excludes `tools/fixtures/*`; the same pattern run over the working tree reads thirty-seven, and the five it adds are this rule's own fixtures.)* **warning** on a disagreement; **error** where the count does not parse. |
| `catalog-line-count` | warning | A `Lines` column, or an inline `(N lines)`, that has drifted from the file it describes. **`gen_claims.py` writes these**; this rule is what fires when it has not been run. Exact since 2026-08-03 — the previous ±2 tolerance was concealing a live 2-line drift. |
| `toc-coverage` | warning | A `##` section missing from its document's own table of contents, and therefore unreachable from the top of an 800-line file. |
| `lifecycle-taxonomy` | error | `data-model.md` §2.1's declared terminal states are not exactly the members of `TAXONOMY` in `src/contracts/terminal.py`, in **either** direction. The only check whose other side is source: the taxonomy is parsed with `ast`, never imported, because `--root` may point at a fixture tree. Added 2026-08-05 under **OD-26**, after the two artifacts had diverged in both directions at once — three members absent from the diagram, two diagram labels that were not members, and a bare `completed` where the member is `terminated.completed` — while the other sixteen checks ran at 0 errors, because none of them reads Python. See [Why the lifecycle is a table now](#why-the-lifecycle-is-a-table-now). |
| `dry-run-verdict` | error | An outcome claim inside a run directory whose own manifest says `dry_run: true`: a gate cleared, a hypothesis confirmed, one method materially better than another, a line labelled `VERDICT:`. A run that called no model produced no evidence, so every such claim was computed against stub output. See below for why the disclosure has to be on the same line. |
| `preserved-evidence` | error | A committed record of a run whose **bytes** no longer match a SHA-256 attested outside the tree that holds it. The eleventh family, and the only check here that reads no content at all: every other rule asks whether an artifact *says* something defensible, and this one asks only whether it is the artifact a human ratified. Added 2026-08-11 after **OD-31** established, by planting the edit rather than by reading the code, that nothing mechanical held the twelve `verifier-vs-judge` run directories — an `E8`→`E19` rewrite in a committed manifest left `freeze.py --verify` reading *intact*, `neutralise_decision.py --check` passing and every gate in this repository green. See [Why the attestation is not refreshed by the tool that edits the evidence](#why-the-attestation-is-not-refreshed-by-the-tool-that-edits-the-evidence). |

Four of these name failure classes nobody had named before: `register-range`,
`inventory-count`, `catalog-line-count` and `definition-count`. All four share
one shape — **a claim about the corpus that lives in a different file from the
thing it describes**, so no reviewer of the change that invalidated it ever sees
it. Two of the four are now *generated* rather than only checked; see
[Generated claims](#generated-claims--gen_claimspy) for what that changed and
why both rules were nonetheless kept.

`count-versus-range` is a fifth failure class and is deliberately **not** a
fifth member of that shape — it is its inverse. Its two operands sit in one
sentence, close enough that a reviewer reads both in a single glance and still
does not see the drift, because each half looks maintained: the range is
written by `gen_claims.py` and advanced the day an entry lands, and the count
beside it is prose that nobody owns. Distance is not what hides a stale figure
here. **Maintenance asymmetry is**, and it hides one just as well at four
words' separation as at four files'.

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

### Narrowing and the definition index

**Measured 2026-08-12 on Darwin arm64, Python 3.12.11, unprivileged (uid 501),
against `2979c31`.** `--path` is the obvious way to gate a single edited file
quickly, and until this pass it was the one flag that could make
`identifier-resolution` emit hundreds of errors naming identifiers that resolve
perfectly well in a full run.
`python3 tools/check_corpus.py --path specs/002-spec-aware-agent-runtime/tasks.md`
reported **304 errors, every one `identifier-resolution`, every one in the `FR`
namespace** — against a register the narrowing had itself removed from the walk.
A pass that saw that flood would either distrust the instrument or believe its
own edit had broken the corpus, and both readings are wrong.

The guard that should have caught it was already present and already firing.
`min_definitions` is `3`, and in that same run **eight of the nine namespaces
disabled themselves with a stated reason**. `FR` was the ninth, and why it
survived is the part worth keeping: `min_definitions` counts *definitions in the
corpus that was walked*, and never asks whether the register itself is there.
Two independent things defeat it.

**A prose heading was read as three definitions.** The heading rule accepted any
identifier anywhere in the heading text, so `tasks.md:1134` —

```
### The execution environment — FR-048, FR-049 and FR-050's mechanisms
```

— defined `FR-048`, `FR-049` and `FR-050`. It was the **sole** source of `FR`
definitions in that narrowed run, and three is exactly `min_definitions`. A
heading that *names* identifiers announces a section about them; it does not
define them. The rule is now lead-anchored, like the bullet and table-cell rules
beside it, which is the strictest reading of the shape the module docstring had
always given as its example (`### OD-01 — ADK's role`). **Measured over the whole
corpus the tightening costs nothing:** the nine namespaces define `C` 21, `D` 22,
`E` 19, `FR` 58, `O` 6, `OD` 31, `P` 10, `SC` 30 and `U` 52 entries under the old
rule and under the new one, identically. Every genuine definition already led its
heading; the loose rule was contributing only phantoms.

**A document that legitimately defines part of a register keeps the whole
namespace active.** Fixing the heading rule cleared the reported case and left
the general one, which the same survey then exposed: narrowing to
`specs/002-spec-aware-agent-runtime/spec.md` keeps `OD` enforced on the four
entries that document happens to define, while the 31-entry register in
`specs/001-discovery-validation/plan.md` sits outside the walk — 147 false errors,
with 8 more for `D` and 7 for `U` by the same mechanism. A count threshold cannot
separate "this corpus holds the register" from "this corpus holds three of its
members". Narrowing to `specs/001-discovery-validation/plan.md` showed the
converse: `E19` is defined by `# E19 — verifier vs judge` in the
`verifier-vs-judge` harness README, and the only thing naming it in `plan.md` is
a heading that *leads* with `OD-31` and cites `E19` in passing, so tightening the
heading rule turned a masked false positive into a visible one — 0 errors before,
8 after, all `E19`.

So the activation decision is now asked of the **unnarrowed** tree. Under
`--path`, the check builds a second definition index by walking `corpus.root` on
disk, and enforces a namespace only when the narrowed corpus contains *every*
definition the whole tree contains. A namespace holding part of its register is
announced as `not enforced`; a namespace whose register is gone reads exactly as
it did before, because that test is asked of the tree rather than of the
selection.

**That distinction is the only reason this was a check repair and not a
documentation one.** A guard that goes quiet whenever the register it resolves
against is absent goes quiet on precisely the condition it exists to catch, and
this repository has hit that vacuity failure in four instruments in one week. The
distinction survives here because no combination of `--path` arguments changes
what is on disk under `corpus.root` — the same move `lifecycle-taxonomy` makes to
tell a missing document from a narrowed-away one. `ctx["narrowed_paths"]`, set by
the runner, is what tells the check which of the two questions it is being asked.

**The residual cost, stated plainly: a narrowed run checks fewer identifiers than
the gate does, and is not a substitute for it.** Planting `FR-999` in
`tasks.md` and running the full check exits 1 and names it. Running `--path` on
that same file exits 0, does *not* name it, and prints `namespace FR not
enforced: 58 of 58 definition(s) are outside the --path selection`. That is the
fail-safe direction — it says so rather than passing silently — but it means
`--path` gates links, tables, arithmetic and provenance on the edited file, and
does **not** gate its identifiers unless the register is in the selection too.

The removal control is the other half, and it is the one that matters most.
Deleting all 58 `FR` definition bullets from
`specs/002-spec-aware-agent-runtime/spec.md` and running the full check reports
**1181 errors**, not a quiet pass: the surviving `FR` references across the
corpus go dangling and are reported as such. Restoration in both plants was
verified by reading the original bytes back — SHA-256 over the whole file, plus a
named line confirmed present in it — rather than by an empty `git diff`, which is
what a clean tree prints and also what a destroyed one prints.

**One ordering defect surfaced on the way, and it had never fired.** The runner
executes checks in name order, so `identifier-gap` runs *before*
`identifier-resolution`; the handoff through `ctx["identifiers_defined"]` that the
gap check was written to consume therefore never happened, and its fallback
branch was the only branch ever taken. That is why it kept reporting holes in
registers the resolution check had already disabled. `identifier-gap`,
`identifier-resolution` and `register-range` now share one `_activation` result,
so execution order no longer decides the answer. In a full run that result
selects exactly the namespaces the old per-check threshold selected, so the gate
is unchanged.

Across fourteen single-file narrowings — four READMEs, both `spec.md`, both
`plan.md`, `tasks.md`, `research.md`, `quickstart.md`, `data-model.md`,
`VERDICT.md` and `research/14` — the tool now reports **0 errors and 0 warnings**,
with every namespace it declined to enforce named in a skip line.

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

### Why the attestation is not refreshed by the tool that edits the evidence

**`preserved-evidence` closes a hole that three existing mechanisms each looked
like they should have closed, and the reason none of them did is the same reason
this one is shaped the way it is.** OD-31 rules twelve committed run directories
under `harness/verifier-vs-judge/results/` to be preserved evidence, and records
that the ruling was the whole of what protected them. The demonstration was a
plant, not a reading: an `E8`→`E19` rewrite in
`results/20260803T092721-final-verify/manifest.json` left `freeze.py --verify`
reading *intact*, `neutralise_decision.py --check` passing, `check_corpus.py` at
zero errors, `tools/selftest.py` green and `pytest` at its full complement.

Each near-miss failed differently, and the three failures are worth separating:

- a manifest **records** a `harness_fingerprint`, which is a self-report. No hash
  anywhere covered a manifest's own bytes.
- `corpus_freeze.json` pins eleven `ceiling-test` run directories that live under
  a **different harness** and hold none of this experiment's output. It was never
  pointed at this tree.
- `dry-run-verdict` reads what an artifact **claims**. A rewrite that changes no
  claim is invisible to it, and widening it would not help: the two checks ask
  different questions of the same files.

**The witness lives outside the tree it attests, and that placement is the
mechanism rather than a filing preference.** `tools/preserved_evidence.json`
carries a SHA-256 per file for all **59** files under `results/` — the 58 in the
twelve run directories plus `NEUTRALISATION.md`, which is a dated correction
record and preserved on the same ruling. Nothing under `results/` is added,
renamed or edited to install it, because a digest stored beside the bytes it
covers is the same self-report the manifest already was.

**The blind adjudication study is attested too, and as a second unit rather than
as a widening of the first.** `tools/preserved_evidence_adjudication.json` carries
a SHA-256 per file for all **10** files under
`harness/verifier-vs-judge/adjudication/` — seven at its root, two under `blind/`
and one under `sealed/`. It is preserved evidence on the same OD-31 ruling as the
run directories beside it, and the first version of this guard did not cover it:
the cost was priced over the twelve run directories and the adjudication set was
not in scope when the ruling was made. That omission was an oversight rather than
a decision, so closing it needed no new ruling. The attested total is **69** files
across the two units, being the 59 under `results/` plus the 10 under
`adjudication/`.

**One unit per tree, because that is what keeps a correction's blast radius equal
to its subject.** Merged under one pin, a correction to a run directory would
produce one new digest, and the human moving that pin would also ratify —
silently, in the same digest — anything that had moved under the adjudication tree
in the same window. Split, the pins are independent, ~~and `--reattest` reports
`the pinned digest already matches; nothing to ratify` for the tree that did not
move,~~ so the ratifier is told which body of evidence changed rather than having
to work it out. **Corrected 2026-08-11: the struck clause named a line that could
not fire on a plain rebuild and no longer carries those words. The mechanism is
set out below in this entry and is not restated here, so that there is one
account of it to keep current rather than two.** What a rebuild prints for the
tree that did *not* move is `the attested tree has not moved since the ratified
attestation`, compared on `tree_sha256`; the tree that *did* move prints **no
corresponding line at all**, so the changed body of evidence is identified by
that line's absence rather than by a sentence of its own. Pin independence
predates the repair and is untouched by it, and it discriminates only when the
correction names its `--unit` — a bare `--reattest` moves both digests, as the
paragraph below on `--unit` sets out. The cost is the honest one: two pins and
two ratifications. The merge is in any case unavailable mechanically, since
`attest.measure` walks one tree recursively and unfiltered on purpose — a filter
is a place for a file to hide — so a single unit spanning both would have to be
rooted at `verifier-vs-judge/` and would sweep in the live harness that
legitimately changes.

**Which root a unit belongs to is declared, and the two earlier keyings were each
defeated by the thing they keyed on going missing.** One list of units spans this
repository and the two fixture corpora, so in any given root most of the list is
legitimately elsewhere and the scope filter has to tolerate absence. That is the
whole difficulty, and it was got wrong twice.

Keyed on `tree`, the check went out of scope when the directory it protects was
deleted: removing all **59** attested records took it to `skipped` while it
announced itself disabled. Keyed on `attestation` instead, it acquired a quieter
version of the same defect. A unit whose witness was missing — deleted, never
built, or named with a typo — was dropped from the run and reported **nothing**:
`--check preserved-evidence` printed `0 error(s), 0 warning(s)` and, because the
per-check skip fired only when *no* unit survived the filter, no skip line
either. That is byte-for-byte what a fully attested tree prints. A real unit with
a mis-typed path was **indistinguishable from a fixture unit living under another
root**, so somebody could hold a tree they believed was attested while nothing
read it. **That is the class this guard was built to close, reproduced one layer
up and inside the guard.** It was found by planting the typo, not by reading the
code, which is the same instrument OD-31 used on the evidence itself.

Each unit now declares a `root.marker`: a path that is present wherever the unit
belongs and is **neither its `tree` nor its `attestation`**, so it cannot be
removed by the act being guarded against. A marker that is present and a witness
that is absent is a `malformed` violation naming the path that was looked for; a
marker that is absent is another root's unit, announced as out of scope rather
than as disabled. Two consequences are the point rather than side effects. The
`malformed` branch of `attest.verify` that reports a missing attestation had been
**unreachable from the check since the day it was written**, and is now reached by
a `known-bad` unit that fires it. And a unit declaring no marker at all is an
error against `config.json` rather than a silent pass, since a unit that cannot be
placed in a root cannot be judged in one — that kind is the one failure here no
fixture root can hold, because all three roots share one `config.json` and a unit
with no marker is in scope in every one of them, so it is held by
`tests/unit/test_preserved_evidence_scope.py` instead.

The residue is worth stating rather than leaving to be found. Deleting a unit's
entire marker directory — witness, tree and all — still takes the unit out of
scope silently. For the two real units the marker is the harness directory that
holds the live experiment code, so that act removes the experiment; for the
fixtures it removes a fixture the self-test then requires and does not find.

**`--reattest` takes `--unit` for a reason, and the bare form is a wider act than
it looks.** With no `--unit` it rebuilds every unit whose tree is present, and a
rebuild is never byte-identical to what it replaces because `generation`,
`attested_at` and `reason` all move. So a bare `--reattest` run to correct one
tree leaves the *other* tree's gate red as `unratified` as well, for no
corresponding edit. Correcting one unit names that unit.

**The trap this design exists to avoid.** If the tool that edits the evidence
also refreshes the attestation, the attestation attests nothing — the vacuity
reappears one layer down, and the gate goes green over exactly the edit it was
built to announce. So a correction is **two acts** and they cannot collapse into
one:

    python3 tools/check_corpus.py --reattest "why"   # writes the record
    # then a human moves attestation_sha256 in corpuscheck/config.json

`--reattest` prints the digest to ratify and **never writes the pin**. ~~Nothing
in this repository calls `attest.build`,~~ **Corrected 2026-08-11: it has 17 call
sites, counted at `ebff21a` — one in `cli.reattest` itself, 14 in
`tests/unit/test_attest_build.py` and 2 in
`tests/unit/test_preserved_evidence_scope.py`. The scoped claim is the one that
was meant, and it is the one that carries the two-act argument: no tool *other
than* `--reattest` calls it, so nothing that edits these artifacts can refresh
their attestation. This sentence's ancestor in
`tools/corpuscheck/checks/preserved_evidence.py` reads *"Nothing **else** in the
repository calls `attest.build`"*, and dropping that `else` made the claim false
about `tools/corpuscheck/cli.py` first of all — the tests are a further
counterexample rather than the only one.** And
`specs/001-discovery-validation/harness/verifier-vs-judge/neutralise_decision.py`
— the tool that legitimately rewrites these artifacts, and which touches
`analysis.json` and `report.md` and no manifest at all — does not import it:
re-read at `ebff21a`, its imports are `argparse`, `json`, `re`, `sys` and
`pathlib` and nothing else. A rebuild alone leaves the gate **red**, reported as
`unratified` rather than as an edit, so an agent that refreshes without ratifying
leaves a failing gate rather than no trace.

**`--reattest` could not report that nothing had changed, because the field it
compared moves on every rebuild.** Recorded as the defect's history rather than as
a live bug: the repair landed at `f7ade9f` on 2026-08-11, from a pass holding
`cli.py` and `attest.py` while this entry was being written. Everything below is a
dated reading of the behaviour before that commit, and the mechanism is the half
that transfers either way.

**A rebuild is never byte-identical to what it replaces, so no comparison of
attestation digests can ever report an unmoved tree.** `generation` is inside the
digested document and `build` increments it every time, and `attested_at` and
`reason` move with it. A digest comparison after a rebuild therefore answers *did
the bytes I just wrote differ from the bytes I just replaced*, whose answer is
always yes, rather than *did the evidence move*, which is the question an author
correcting one record actually has.

**The one line that looked like the answer was a statement about the pin wearing
the grammar of a statement about the tree.** That line was
`the pinned digest already matches; nothing to ratify`, true exactly when the
bytes written equal the pinned bytes, and reachable only from a corrupted or
absent record plus a generation-1 pin, or from a readable predecessor sitting one
generation below the pin — never from an ordinary rebuild. So the state a reader
most wanted reported was the one
state the output had no sentence for, and the sentence it did have fired in the
states least like it.

**The field that can answer is `tree_sha256`, because it is the one field a
rebuild of an unmoved tree does not move**: it is a function of the file set
rather than of the record describing it. Comparing it against the same field in
the record the pin covers is a report about the evidence, and it is reachable on
an ordinary rebuild rather than only on a corrupt one. That is the route `f7ade9f`
took, reading the record about to be replaced, naming its state, and taking a
baseline only from a record whose own bytes are the pinned ones.

**The generalisation is about which fields a self-describing record may be
compared on.** A record that stamps itself — a generation counter, a timestamp, a
reason — cannot be diffed against its own predecessor to answer a question about
its subject, because the stamp guarantees a difference the subject did not cause.
The comparison has to name the field that is a function of the subject alone, and
a record mixing the two kinds of field in one digest cannot be asked the question
at all without that field being pulled out by name.

**What it cannot do, stated plainly rather than left to be discovered.** It
cannot stop an author who edits a record, rebuilds the attestation and moves the
pin in one commit. Nothing in a repository can: the pin is text and the author
has write access. What it converts is a **silent** edit into a **visible** one —
three files in three trees, one of them a guard's own configuration, all moving
together and all in the diff. That is the standard OD-30 accepted for the
measurement record, and OD-31's residual asked for nothing stronger.

It also has no opinion about whether the attested bytes are *right*. A wrong
figure committed before the attestation was built is attested wrongness, and this
check will defend it as faithfully as it defends anything else.

**The proof-history archive is not a precedent for this, and it was cited as one.**
`tests/batteries/results/removal-proofs-history/` names each record by content
digest as well as by clock, and that scheme was offered as the model this guard
should follow. It is worth being exact about what it does, because the resemblance
is real and the protection is not. `tools/removal_proofs_summary.py` records the
reason in `_archive`, and the reason is collision handling:

> Named by content digest as well as by clock, so two runs in the same second
> with different outcomes are two files and two identical runs are one.

That is same-second disambiguation and deduplication. **Self-verification is a
property the scheme happens to have rather than a purpose it was built for**, and
finding 032 did exploit it — recomputing the digest of the one record it quotes
and matching the suffix in its filename. That was a decision about one exhibit,
not a protection over a directory.

Three properties keep it from doing what this attestation does, and each is
checkable at the source rather than taken on description. The directory is
**git-ignored**, at `.gitignore:171`, so no checkout contains it and the digests
in its filenames guard nothing any reviewer will ever see: a reading of one
working tree found `83` files there and exactly **one** tracked, the exhibit
finding 032 quotes, present only because it was force-added past the ignore rule.
The name is written by the same run that writes the body, so it is a self-report
in the precise sense this section began with — the manifest's `harness_fingerprint`
failed the same way. And nothing reads the names back: no gate recomputes a digest
in that directory and compares it, so a renamed file, an edited body under an
unchanged name, or a deletion all pass unremarked.

**The hazard is a reader concluding that committed evidence is guarded because its
filenames contain digests.** That is the false-green class this repository has
hardened its instruments against, and it would be arrived at here by analogy
rather than by any claim the archive makes about itself. A content-digest filename
distinguishes records from each other. An attestation held outside the tree, with
its own bytes pinned in a second file that a human edits, is what makes an edit
loud. The two are different mechanisms with different jobs, and only the second one
is a gate.

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

Two of the ~~eighteen~~ **nineteen** checks were guarding **hand-written summaries of facts that
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
  that line a site — including a third, deliberately-partial
  `OD-01 through OD-14` sitting in the same sentence for a different purpose.
- **A single range introduced by punctuation.** A range starting at entry 01
  whose preceding text ends in `(`, `[`, `:`, an em dash or an en dash — after
  `*~_` and spaces are stripped — is a site on its own. A provenance sentence of
  the shape
  `…instead of by the bound: OD-01 through OD-14 came out of measurement…` is
  caught by the colon, with no second register anywhere near it. **That code
  span has to stay on one source line.** `build_masked` masks line by line, so
  a span opening on one line and closing on the next is not recognised as a
  span at all and neither half is masked; re-wrapping the sentence puts a live
  `register-range` warning back into the gate.

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

#### Nothing detects the split itself, and the corpus is safe by coincidence

**The bullet above says the span has to stay on one source line. Nothing in the
gate set can tell you whether it did.** Established 2026-08-11 by planting
rather than by reading `build_masked`, because a masker's source shows what its
author meant to cover and what it covers was the question. Both plants went
into this file in a clean detached worktree at `5305172` — the corpus walks it,
`include` carrying `tools` and `consumer` carrying `tools/*.md` — and each was
restored by reading a needle back out of the file, never by observing an empty
diff, which is [what a destroyed tree also
prints](#the-emptiness-test-inversion--git-diff-cannot-tell-unchanged-from-changed-back).

**A split whose content trips no other rule is completely silent.** The span
`export PATH="$PWD/.venv/bin:$PATH"` broken after `export` — the split this
file took at `a7e91ed`, from a reflow that meant nothing by it — passes **all
seven gates**: corpus 0 errors 0 warnings with the one declared skip, 39 claims
0 stale, 344 proofs, self-test green, 27 instruments, 34 perturbations, 1792
passed and 83 skipped. Nothing tests span balance, so there is no instrument to
name and no severity to argue over.

**The one recorded firing ran the other way, and it cost more than the warning
it was recorded as.** `register-range` at the worked example above was a false
positive *caused by* a split, not a detection *of* one: the split defeated the
masking and exposed a range the masking would otherwise have hidden. Re-planted
at `5305172`, that shape does more than warn. `check_corpus.py` reports it as a
warning and still exits 0, so the gate that actually goes red is
`gen_claims.py --check`, at **exit 1** with 40 claims and 1 stale — the split
did not merely expose a range, it *created a generated-claim site* inside bytes
that should have been masked. Running the documented remedy then advanced the
worked example's bound to `OD-31`, after which all seven gates are green, a
sentence whose whole purpose is a deliberately-partial range no longer carries
one, and it disagrees with this file's two other accounts of the same example.
A whitespace edit reaches [the remedy corrupting the correct
artifact](#a-checker-false-positive-is-more-dangerous-than-a-checker-gap-the-remedy-corrupts-the-correct-artifact-and-then-it-passes)
in two commands.

**The condition is common, and it currently costs nothing; both halves are the
same measurement.** 46 split spans sit in the walked corpus at `5305172` across
140 markdown documents — 28 authority, 12 consumer, 5 harness, 1 other, every
one a single-backtick run, seven of them in this file — and the corpus reads 0
errors 0 warnings, so **not one of the 46 is visible to any gate**. Joining all
of them in a scratch worktree moves nothing except three `line-count` claims
that go stale because their files got a line shorter, which is the newline and
not the span. **The count is a dated reading and it grows with ordinary
authoring**: it read 44 at `0d8b2e4` half an hour earlier, and a single new
finding added two. Three of the 46 carry a token another rule reads, and all
three are silent for three different reasons, none of them masking: the range
in the bullet above, because the split also breaks `_RANGE`, which needs the
second identifier to follow the separator on the same line;
`Preprints 202606.0238` under [the false-positive
register](#known-false-positive-modes), because a rate's integer part is capped
at three digits; and `E8` in `specs/001-discovery-validation/plan.md`, because
it resolves. Three coincidences, not a guard.

**What a check would have to key on**, recorded so a later owner need not
derive it again. Not a fresh definition of an inline span but the masker's own:
`_INLINE_CODE_RE` needs its opening and closing runs in one string, so the
condition is two adjacent non-fenced lines that `mask_line` leaves carrying
unconsumed backtick runs of equal length, where joining them the way a reflow
would un-join them yields a run the masker does consume. **Adjacency is the
scope control and it is not optional.** Without it the indented fence rows in
`adjudication/blind/cases.md` pair with each other dozens of lines apart —
`_FENCE_RE` anchors at `^\s{0,3}` and does not see a fence opened at column
twelve — and the first form of this census read 230 sites, nearly all of them
that.

**It is not offered as ready to wire, and the number is the reason.** An
error-severity rule fires 46 times on a clean corpus, which is the shape that
declined [both halves of an earlier
widening](#both-halves-were-declined-on-a-blast-radius-nobody-had-counted-and-counting-it-reversed-both).
The difference is the part an owner has to rule on, and it cuts both ways:
those declines counted **false positives**, and these 46 are **true
instances** of the condition. They are also not defects in what the documents
say — CommonMark joins the two lines of a paragraph, so a split span renders
exactly as intended. It is a masking defect and not a reading defect, and it
becomes a reading defect only when the exposed half happens to carry something
a rule reads. Wiring it therefore means landing 46 repairs first, and the
question is whether a hazard whose entire measured cost is one corrupted worked
example in this file is worth that. **Recorded rather than closed on the
measuring pass's own authority.**

**Declined by the product owner on 2026-08-11: no rule is to be wired for this
condition, and the ground is not the one the neighbouring declines rest on.**
The 46 are **true instances**. Each really is a span the masker cannot see, so
a rule would be right every time it fired, and CommonMark joins the lines of a
paragraph, so each already renders as its author meant it to. The wiring
therefore buys no change in what any document says, against 46 repairs to reach
green, and it is that ratio rather than any doubt about the condition that
closes it.

**Name that ground whenever this decline is cited.** The declines standing
nearest it were all settled on measured **false positives** — the
duplicate-definition guard on false alarms it could not shed, the
[`unconstructib*` candidate](#what-this-cannot-catch) on firings that were
false at every window width tried, and `_RANGE`'s relaxation on the same
footing. A reader who carries that ground across will conclude this condition
is not real. It is real, it is counted, and it is left alone on cost.

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

#### The first collision to arrive is outside the residue as written, and it widens it

> **The collision was adjudicated 2026-08-11 by `plan.md` **OD-31** and no longer exists: Stage D
> keeps `E8` and the verifier-vs-judge experiment is `E19`.** **This section is left as measured and
> is not renumbered**, because every sentence in it is a dated statement about a state the corpus was
> in, and rewriting `E8` to `E19` here would turn a true measurement into a false one — the whole
> subject is an identifier that named two things, and after OD-31 neither identifier does. **What
> survives the adjudication is the part that was never about this experiment**: a heading can hand
> out a taken number, the declined first-cell guard fires zero times on that case, and the human
> search is still the only instrument that would have caught it. **The residue is unchanged.**

**Measured 2026-08-10 at `6f55897`.** The identifier `E8` names two different
experiments: the Stage-D synthesis experiment defined in
[`plan.md`](../specs/001-discovery-validation/plan.md), which the experiment
ladder and the budget table both mean, and the verifier-vs-judge experiment
closed under OD-14, which owns a harness directory, a preregistration, a
viability document and three findings. A reader tracing the ladder arrives at the
wrong closure. Three things about it are worth more than the repair, and none of
them is the case the residue above predicted.

**It is a definition and a use, not two definitions — inside the document where
it does the damage.** `definitions_in` treats three shapes as defining, and
within `plan.md` exactly one occurrence is any of them: the Stage-D section
heading. The two ladder occurrences sit inside a fenced Mermaid block and are
skipped outright; the cost-table row carries the identifier in its **second**
cell, and only an exact first-cell match defines; every occurrence belonging to
the verifier-vs-judge experiment is prose. **So the per-document set collapse is
not what is happening here** — that set has one member because the document
defines one thing.

**The collapse that is real is the cross-document union, which is the residue's
other clause.** The verifier-vs-judge experiment holds its own heading
definitions in other files, so `_collect_definitions` unions two experiments into
one entry and every reference resolves to it. `identifier-resolution` passes and
is right to pass: it asks whether a token resolves to a definition, not whether
it resolves to the one meant.

**The declined guard would not have caught it either, and that is what moves the
boundary.** The candidate rule reuses the existing first-cell rule, so its
definition sites are **table rows**. This identifier has no first-cell definition
site anywhere in the corpus — both experiments define by heading — so the
candidate fires zero times on this collision at every one of the three scopes it
was measured at. That measurement reproduces exactly at `6f55897`: `12` firings
at corpus scope, `9` at document scope, `2` at table scope, and the twelve are
the twelve named above, unchanged. **The residue therefore understated itself.**
Nothing will notice a register that hands out a taken number, and nothing will
notice a **heading** that hands out a taken number either — including the guard
that was constructed, measured and declined. The human search remains the only
instrument, and it has to read headings as well as register rows, which the
one-command-per-namespace form above does not do.

#### The FR/SC register collision — scoping declined at 153 to 2, and the gap check is where the defect actually bites

**Measured 2026-08-12 at `a2eafa3`.** `FR` and `SC` are one register per feature and their tokens
collide: `specs/001-discovery-validation/spec.md` defines FR-001..FR-022 and SC-001..SC-009,
`specs/002-spec-aware-agent-runtime/spec.md` defines FR-001..FR-058 and SC-001..SC-030, the two FR-001s
are different requirements, and `_collect_definitions` unions them by token. **Feature 001's register
is a proper token subset of feature 002's** — 22 of 22 and 9 of 9, nothing in 001 that 002 lacks —
which is what makes the collision total rather than partial and is the fact the rest of this entry
turns on.

**The false green is real, and confirmed by planting rather than by reading.** `FR-045` planted into
feature 001's own `spec.md`, whose register stops at FR-022, produces **no violation at all**;
`FR-099` planted on the same line, outside the union, is the only firing. So a dangling FR in one
feature does resolve against the other's register, exactly as alleged.

**And repairing it by scoping resolution per feature is disqualified, because the false greens and the
legitimate citations are the same 153 sites.** Both directions were measured before the choice:

| | sites | population |
|---|---:|---|
| Direction A — citations resolving *only* via the union | **153** | 7 documents, all under `specs/001-discovery-validation/` |
| Direction B — citations of a token defined *only* by the other feature | **153** | the identical set; `A − B` and `B − A` are both empty |

The two are not merely equal in count; they are the same sites, asserted as a set comparison rather
than inferred from two totals agreeing. Every citation that resolves only because of the union is a
deliberate cross-feature citation — feature 001 is the discovery feature and its `plan.md` *authorises*
the production specification's requirements, in sentences like *"**Authorises** the production
specification's **FR-025** and **FR-045**"*. **The brief's own example token was one of the legitimate
cases**: FR-045 is cited three times in feature 001 and every one is correct.

131 of the 153 are in `specs/001-discovery-validation/plan.md`; the rest are 7 in
`findings/017-evaluation-contemporaneity.md`, 5 in `findings/016-provider-sdk-roundtrip.md`, 4 in
`findings/031-provider-state-chain-measured.md`, 3 in `VERDICT.md`, 2 in
`harness/provider-sdk-roundtrip/README.md` and 1 in `findings/006-graph-loop-primitives.md`, over 28
distinct tokens. **Only 30 of the 153 name the target feature or "production spec" on the same line**,
so a rule that admitted a cross-feature citation only where the line says so would still reject 123
correct ones.

**Scoped resolution was built and run rather than costed on paper**, in a throwaway copy of the tree:
FR and SC resolved against the claiming document's own `specs/<feature>/spec.md` and every other
namespace left alone. It reports **153 errors on the clean corpus**, matching the independent
measurement exactly. With the `FR-045` / `FR-099` plant added it reports **155** — so the trade is
**2 real firings inside a report of 153 false ones**, which is the `register-range` and
duplicate-register-row disposition at a worse ratio than either. Its violation text is also actively
misleading under scoping: the hint prints `FR currently runs to FR-058`, the union's ceiling, which
tells the reader the token they were just faulted for does exist.

**And 95 citations have no owning feature at all, so the rule's only available answer for them is the
behaviour being repaired.** FR and SC are cited 73 and 22 times outside any `specs/<feature>/`
directory — `research/14-architecture-synthesis.md` (35 FR, 15 SC),
`research/15-nvidia-oo-agents.md` (13, 3), `tools/README.md` (22, 2),
`docs/spec-kit-workflow.md` (2, 0), `research/README.md` (1, 0),
`research/06-examples-inventory.md` (0, 1) and `research/07-product-vision.md` (0, 1). A scoping rule
must either fall back to the union for those — leaving the defect live for the largest single
population — or stop reading them, which is how a check goes quiet over 95 citations. Neither is worth
153 false positives.

**The precedent holds, and it was verified by planting.** `definition-count` does resolve
`definition_count_target` through `_target_of` against the claiming document's own
`specs/<feature>/` directory, so feature-scoped resolution already exists in this repository. A claim
of *"58 functional requirements and 30 success criteria"* planted into
`specs/001-discovery-validation/plan.md` — a document that carries no such claim, so the plant could
not be satisfied by an existing site — is compared against **22** and **9**, feature 001's own
register, and not against the union's 58 and 30. The precedent is real; what it does not carry is a
reason to extend it, because a count claim names one target document while a citation names none.

**Where the defect actually bites is `identifier-gap`, and there the false-positive population is
empty.** The gap check reads the same union. Deleting feature 001's `FR-015` requirement bullet
outright — a deleted row rather than a struck one, which is the precise defect `identifier-gap` exists
to catch — leaves the union contiguous, because feature 002's FR-015 fills the hole.
`identifier-gap` and `identifier-resolution` together reported **0 errors, 0 warnings** on that plant.
Unlike the resolution case this one has no legitimate counterpart: a deleted requirement row is never
correct, and all four per-feature ranges are dense today (FR-001..FR-022, SC-001..SC-009, FR-001..FR-058,
SC-001..SC-030), so a per-feature gap check would fire **zero** times on the clean corpus and catch
this plant. **It is not built here**, and the reason is the shape rather than the cost: a per-feature
gap check acquires a new silence mode — a feature whose `spec.md` is absent or narrowed away simply
has no register to find a hole in — and that is the class this repository has now reintroduced twice
while closing it once, at `preserved-evidence`'s two keyings. It needs the `corpus.root` move that
`_unnarrowed_definitions` makes, and designing that is a pass, not a paragraph.

**`register-range` is the third check the collision reaches, and this entry tripped it while being
written.** The paragraph above originally wrote the two registers as `FR-001…FR-022` and
`SC-001…SC-009` on one line, and `register-range` reported **4 warnings** calling both an under-count
of `FR-001 … FR-058` and `SC-001 … SC-030`. The sentence is true and the check has no way to be right
about it: `maxima` is read from `defined[ns]`, the union, so **no correct statement of one feature's FR
or SC extent can pass this check in the `…`, `–`, `--`, `to` or `through` form** whenever a second
namespace's range shares the line. The ranges here are written `..` instead, which `_RANGE`'s separator
alternation does not match — the same dodge `config.json`'s `_comment_identifiers` already takes for
the identical sentence, and it is recorded here rather than left as a formatting habit, because the
next author writing a true per-feature range will hit it and should know the check is wrong rather
than the prose.

**The residue, stated so it is not mistaken for coverage.** Nothing distinguishes a feature-001
citation of a feature-002 requirement from a feature-001 citation of a requirement that does not
exist; ~~nothing will notice a deleted FR or SC row in either feature while the other still defines
that token;~~ and no true per-feature range claim can be written in the form `register-range` reads.
The declination above is about the first of those and not the other two. **The struck clause was
repaired 2026-08-12 — `identifier-gap` now reads one register per feature; see the entry below. The
third clause was measured and stands, at a firing count, two entries down.**

#### The per-feature gap repair, and the 22 rows it was measured against

**Measured 2026-08-12 at `af36453`, Darwin arm64, Python 3.12.11, in a throwaway worktree.** The
entry above establishes that deleting feature 001's `FR-015` row leaves every gate green. That is one
row; this is the population, and it is **not** the region the defect was expected to occupy.

**The exposure is 22 rows, and it is not the 31-row overlap region.** The brief for this pass
proposed that the exposed set was the region where feature 001's register is a proper token subset of
feature 002's — FR-001..FR-022 and SC-001..SC-009, so 31 rows. Three things are wrong with that
framing and each was measured rather than argued:

- **The collision is symmetric, so the overlap region holds 62 rows and not 31.** Deleting feature
  *002*'s `FR-015` is equally invisible to the gap reading, because feature 001's `FR-015` fills the
  hole. Simulated over every one of the 119 `FR` and `SC` rows in the two specifications and then
  planted in both directions: **64** rows leave `identifier-gap` and `identifier-resolution` silent —
  the 62 in the overlap region, plus feature 002's `FR-048` and `FR-049`, which three findings
  documents under `specs/002-spec-aware-agent-runtime/findings/` restate in bold-lead bullets.
- **`definition-count` is a third guard and it already covered three of the four registers.** A
  deleted row shrinks the register the prose counts, so any register with a live count claim is
  guarded against every one of its rows. Feature 002's `FR` and `SC` are claimed by `plan.md:6` and
  `tasks.md:6`; feature 001's `SC` is claimed by `checklists/requirements.md:91`, *"all nine success
  criteria"*, whose count word sits on the line above the noun and is read through that check's
  two-line window. **Feature 001's `FR` register is the only one of the four with no prose count
  claim anywhere in the corpus**, and it is therefore the whole exposure.
- So the measured figure is **22**: every row of `specs/001-discovery-validation/spec.md`'s `FR`
  register. Each of the 22 was deleted in turn and the full gate run against it — 22 runs, **22 of 22
  reporting 0 errors and 0 warnings**. That is why the brief's own example, `FR-015`, was the one that
  reproduced: it is in the only register nothing was counting.

**Worse than any single row, and found while measuring it: deleting the whole register is also
silent.** Removing all 22 `- **FR-...**` bullets from that file at once — the entire register, not a
hole in it — also reported **0 errors, 0 warnings** before this repair.

**What the repair is.** A namespace marked `per_feature` in `config.json` is read register by
register, each register being the `definition_count_target` in its own `specs/<feature>/` directory —
the same per-feature resolution `definition-count` already performs through `_target_of`, so there is
one convention for "which specification owns this claim" and not two. The union reading is kept for
every other namespace, and for a `per_feature` namespace only when the per-feature pass could not
speak, because it still covers one thing no per-feature reading does: a definition-shaped row for
that namespace **outside** every feature's specification, which puts a hole in the union and in no
register.

**The register is the feature's `spec.md` and not its feature directory, and that choice is
load-bearing rather than arbitrary.** `specs/001-discovery-validation/VERDICT.md` adjudicates all
nine of feature 001's success criteria in a first-cell table, so it *defines* SC-001..SC-009 under
`definitions_in`. A directory-keyed register would have had feature 001's `SC` register filled by its
own verdict document and stayed silent on every row of it — the same masking as the cross-feature
collision, one directory down. Keyed on `spec.md` it does not. The same is true of `FR-048` and
`FR-049` and the three findings documents that restate them.

**What it buys, stated so the excluded case is visible.** Planted row by row against the repaired
tool:

| | rows |
|---|---:|
| Deletions the whole gate was silent on before | **22** |
| Newly caught — `FR-002` .. `FR-021` | **20** |
| ~~Still silent — `FR-001` and `FR-022`~~ **Closed 2026-08-12 by a count claim in that feature's `VERDICT.md`; see the entry below** | ~~**2**~~ **0** |
| Rows the repair newly makes *gap*-visible across all four registers, whatever else covered them | **58** |
| Rows the union reading catches that the per-feature reading does not | **0** |

The last row is what makes the change additive rather than a trade: asserted as a set comparison over
all 119 rows, not inferred from two totals agreeing.

**The limit, named because a coverage claim that quietly excludes a case is how the next reader
over-trusts it: a gap check sees holes, not truncations — and at *both* ends, not just the top.** The
range is computed from the members that are present, so deleting either endpoint shrinks it instead
of perforating it. All eight endpoints of the four registers were planted: `definition-count` catches
six of them and `identifier-resolution` two of those six as well, and ~~the two that fire nothing are
**feature 001's `FR-001` and `FR-022`** — the endpoints of the one register no prose counts~~ **the
two that fired nothing were feature 001's `FR-001` and `FR-022`, the endpoints of the one register no
prose counted; that register now carries a count claim and all eight endpoints fire *(closed
2026-08-12, entry below)*. The blindness described here is unchanged — it is a property of every
density check, and `identifier-gap` still cannot see any of the eight**. The
brief for this pass named only the top of the range; the bottom is exactly as invisible, because
`min(nums)` moves as readily as `max(nums)`.

**And it is defence in depth rather than a duplicate of `definition-count`, which is why all four
registers are read and not just the exposed one.** The compound plant is the demonstration: delete
feature 002's `FR-015` **and** advance both count claims from 58 to 57 — the honest edit, the one a
pass making that deletion would actually make. `definition-count` then agrees and goes quiet. Against
the unrepaired tool that plant reports **0 errors, 0 warnings**; against the repaired one it reports
**1 warning**, and the per-feature gap reading is the only thing left holding the register.

**The new silence mode, and why it is a closure rather than a swap.** A per-feature check must find a
register to look for holes in, and a feature whose `spec.md` is absent — or narrowed away by `--path`
— has none. Answering "no register, therefore no gaps" would install one silence while removing
another, which is the class this repository has reintroduced twice while closing it once. Three
states are distinguished and only the third is ever a pass:

| State | What the tool says |
|---|---|
| Outside the narrowed selection | `specs/001-discovery-validation/spec.md: 22 of 22 FR definition(s) are outside the --path selection … a full run checks it` |
| Absent from the repository | `specs/001-discovery-validation has no spec.md, so its FR register … was not read for holes — this is absent from the repository rather than narrowed away, and it is not a clean result` |
| Present, and every row of the register gone | `specs/001-discovery-validation/spec.md defines no FR members while 1 other feature specification(s) do, so there is no FR register … there to find holes in` |

The first two are separated by asking the question of the **unnarrowed tree** under `corpus.root`,
which is the `_unnarrowed_definitions` move the narrowing repair at `aaa1283` made for the
namespace-level decision; the pattern transfers unchanged, and it is now a cached corpus rather than a
cached union because the per-feature walk needs the documents and not just the tokens. The third state
is a bonus the shape paid for: it turns the whole-register deletion above from a silent `0/0` into an
announced skip. **None of the three fails the gate** — `identifier-gap` is a warning and a skip is not
a violation at all — so what they buy is a line in the report, which is what this repository means by
not passing silently.

**Held by five self-test rows that fail against the unrepaired module, and by two targeted tampers.**
No pytest-scored removal proof was written, and the reason is the precedent: finding 038 measured
pytest blind to the entire corpus checker, so a pytest-scored proof for a corpus-checker helper is
vacuous by construction. Reverting `checks/identifiers.py` and `config.json` to `af36453` and leaving
`selftest.py` in place fails **5** of the 12 new assertions, with the collision fixture reporting `0
violation(s)`. Reading the register off the narrowed corpus instead of the tree fails exactly the
narrowed-away row; keying it on the feature directory instead of the `spec.md` fails **4**, the
primary one among them, because the fixture's restatement is complete and fills the hole.

**The 95 citations with no owning feature are not in scope here, and this is the answer the resolution
attempt could not give.** The entry above records `FR` and `SC` cited 73 and 22 times outside any
`specs/<feature>/` directory, and that population is what disqualified feature-scoped *resolution*: a
citation names no feature, so scoping it either abandons the union or stops reading those documents. A
gap check asks a different question — whether a register is dense — and takes no interest in
citations at all. Measured rather than assumed: of the 7 documents holding those 95 citations,
**0 define any `FR` or `SC` member** under `definitions_in`. Every definition-shaped `FR` or `SC` row
in this corpus sits under `specs/<feature>/`, so there is no ownerless register for this check to be
unable to place. That is the whole asymmetry — the resolution rule's hard population is empty for the
gap rule.

#### The two endpoints closed with prose rather than a mechanism, and the site was not the one the sibling suggested

**Measured 2026-08-12 at `6e70bf5`, Darwin arm64, Python 3.12.11, in a throwaway worktree.** The
entry above leaves feature 001's `FR-001` and `FR-022` uncovered and says why: a density check reads
holes, not truncations. Both were confirmed still silent before anything changed — each deleted in
turn with the whole gate run against it, **0 errors and 0 warnings** each time, which reproduces that
entry's finding at the bottom end as well as the top.

**No new mechanism was added, and that is the ruling.** A truncation is undetectable from the register
alone: the extent is computed from the members present, so closing it needs an *external* declaration
of where the register ends. This corpus has exactly four places such a declaration can live, and
three of them were already refused:

| Where the declaration could live | Disposition |
|---|---|
| A prose count of the register | **Taken.** `definition-count` already reads it, and it covered the other three registers, which is why they were never exposed |
| A prose *range* of the register | Refused. The entry below measures `register-range` firing **0** times over **48** candidate sites, and no correct single-feature extent claim can pass it in the separators it reads |
| The citations of the register | Refused. Feature-scoped `identifier-resolution`, declined two entries above at **153** false positives to **2** |
| A constant in `config.json` | Refused. `definition-count` carries no threshold on purpose, a constant is one more thing `threshold_probe.py` must pin, and a figure no reader ever sees is the register-provenance trap rather than an escape from it |

So the fourth option is not a rival mechanism; it is the first option with the declaration moved
somewhere a person cannot read it. **Teaching `identifier-gap` a declared extent reduces to choosing
one of these four, and three are already closed on measured grounds.** Nothing about the gap check
changed: no code was touched, and therefore no self-test row was added — there is no new behaviour for
one to hold, and the claim below is held by the plants and by `definition-count`'s own existing rows.

**The site is `VERDICT.md`, and the obvious candidate was wrong.** The sibling claim lives at
`specs/001-discovery-validation/checklists/requirements.md:91` — *"all nine success criteria"*, count
word on one line and noun on the next — so the parallel site for `FR` looked like the same file.
**The parallel sentence cannot be written there, because it would be false.** That claim is sayable
about `SC` only because `VERDICT.md` adjudicates every one of the nine; it adjudicates **3** of the
`FR` register's **22** rows and says so in the section heading it sits under. *"It rules on all
twenty-two functional requirements"* would be a fabricated claim that happened to satisfy a checker,
which is the defect this repository refuses under its own name.

**What the claim is doing as prose, which is the test it had to pass.** The section already opened
*"FRs are not adjudicated exhaustively here"* — a disclaimer with no scale on it. A reader could not
tell whether "not exhaustively" meant three of four or three of sixty, and the denominator is the
whole content of that warning. The sentence added supplies it and closes the misreading in the same
breath: the unnamed rows carry no verdict rather than a passing one. It is guarded because it is worth
reading, not written in order to be guarded.

**Both endpoints, planted before and after.**

| Plant | Before | After |
|---|---|---|
| Delete feature 001's `FR-001` | 0 errors, 0 warnings | **1 warning** `definition-count`, expecting 21, hint *the register runs to FR-022* |
| Delete feature 001's `FR-022` | 0 errors, 0 warnings | **1 warning** `definition-count`, expecting 21, hint *the register runs to FR-021* |

The hints differ, which is the check reading the surviving register rather than echoing a constant.
That the claim is *read at all* was established the same way and not by grep: this file's own
`definition-count` extractor reports the site at `VERDICT.md:403` resolving against
`specs/001-discovery-validation/spec.md`, the right register, through `_target_of`. Grep is not
evidence here — the `SC` sibling escaped two independent greps because its count word sits on a
different line from its noun.

**Every row of all four registers, planted, not reasoned about.** Each of the 119 `FR` and `SC` rows
in the two specifications was deleted in turn with the full check set run against it, in the same
`run_checks` path the gate uses:

| Register | rows | caught | silent |
|---|---:|---:|---:|
| `specs/001-discovery-validation/spec.md` `FR` | 22 | **22** | **0** |
| `specs/001-discovery-validation/spec.md` `SC` | 9 | **9** | **0** |
| `specs/002-spec-aware-agent-runtime/spec.md` `FR` | 58 | **58** | **0** |
| `specs/002-spec-aware-agent-runtime/spec.md` `SC` | 30 | **30** | **0** |

**119 of 119 caught, 0 silent**, and the split confirms the mechanism rather than merely the total:
in each register exactly **2** rows are caught by `definition-count` alone and the rest by
`definition-count` together with `identifier-gap`. Those 2 are the endpoints, in all four registers.
No register in this corpus now has a row that can be deleted silently.

**The residue, which is narrower than what it replaces and is measured rather than inferred.** A
count claim is satisfied by advancing the count, so the honest question is what a pass that deletes a
row *and* makes the edit it would actually make can still hide. Planted:

| Compound plant — delete the row **and** advance the count | Result |
|---|---|
| Endpoint `FR-001`, count advanced | **0 errors, 0 warnings** — still silent |
| Endpoint `FR-022`, count advanced | **0 errors, 0 warnings** — still silent |
| Interior `FR-015`, count advanced | **1 warning** `identifier-gap` |

So the endpoints are covered against a *deletion* and not against a deletion plus a matching prose
edit, while every interior row is covered against both. That is the defence-in-depth argument in the
entry above, read from the other side: `identifier-gap` is what survives the count being advanced, and
it is exactly what cannot see an endpoint. **Feature 001 is CLOSED with a `VERDICT.md` and its
register is frozen**, so the compound edit is not a maintenance path anyone is on — which is why this
is recorded as a limit rather than chased with a fifth mechanism. It is also the reason a
hand-maintained figure is safe here and would not be in a live register.

**One thing this does not buy, stated because the number appears in this file.** A count of feature
001's requirements written in *this* document is not checked — `definition-count` resolves its target
through the claiming document's own `specs/<feature>/` directory, and `tools/README.md` has none, so
the figures quoted in this entry are unread prose like every other figure here.

#### No correct statement of one feature's FR or SC extent can pass `register-range`, and the relaxation stays declined

**Measured 2026-08-12 at `af36453`.** The entry two above reports `register-range` firing 4 warnings
on its own true sentence and dodging with `..`. That claim reproduces, is **wider** than it was
stated, and the relaxation is nonetheless declined — on a firing count, and on the same ground every
previous `register-range` relaxation was declined on.

**The claim, re-measured in every separator form.** A line reading *"Feature 001 defines FR-001 …
FR-022 and SC-001 … SC-009 today"* was planted into this file in each form `_RANGE` accepts:

| Form | Warnings |
|---|---:|
| `…`, `...`, `–`, `--`, `to`, `through` | **2** each |
| `..` — the dodge this file and `config.json` both take | **0** |
| one namespace, parenthesised: `(FR-001 … FR-022)` | **1** |
| one namespace, bare prose: `defines FR-001 … FR-022 today` | **0** |

**The stated qualifier is too narrow, and the correction matters to the next author.** The previous
entry attributes the failure to a second namespace's range sharing the line. It is not that:
`_is_whole_register_claim` requires the range to start at `01` and then accepts **either** a
parenthesis **or** two namespaces on the line, so a correct parenthesised statement of a single
feature's extent cannot pass either. What actually escapes is a range that is not read as a
whole-register claim at all — bare, unparenthesised, alone on its line — or a separator `_RANGE` does
not match.

**And the obvious repair helps zero sites, which is what settles it.** Now that `identifier-gap`
resolves a `per_feature` namespace against `_target_of`, the analogous move for `register-range` is to
read `maxima` from the claiming document's own feature register. Censused over the loaded corpus,
`_RANGE` matches **48** `FR`/`SC` range strings, and:

- **all 48 are inside `specs/002-spec-aware-agent-runtime/`**, and **all 48 are subset ranges** —
  not one starts at `001`, so `_is_whole_register_claim` rejects every one and `register-range`'s
  firing count on `FR` and `SC` today is **0 over 48 candidate sites**;
- the sites the complaint is about are the **10** written `..`, and **all 10 are in `tools/README.md`**
  — a document with no owning feature, where `_target_of` returns `None` and a per-feature `maxima`
  falls back to the union it was meant to replace. The repair would leave them exactly where they are.

**The cost side is the recorded one, and it is why this is a decline and not a deferral.** Making
those sentences *matchable* means relaxing `_is_whole_register_claim`, and `specs/002-spec-aware-agent-runtime/checklists/requirements.md`
— one of the two files [the earlier declination](#the-sites-it-refuses-and-why-the-two-rules-were-kept)
names as records that must stay frozen — holds **13** of the 48 subset ranges. A relaxation that read
them would demand a dated validation record advance, which is not noise but a wrong answer. The
markup-tolerant variant carries the separate recorded trap of reading `OD-01 through ~~OD-14` and
stopping at the struck bound.

**One thing the dodge is doing right, and it is not a formatting habit.** The 10 `..` sites all sit
inside dated measurement entries. Were `register-range` to read them it would require them to advance
to `FR-058`, which would destroy the record. For a frozen per-feature claim the unmatched separator is
functioning as the strike convention's analogue, and that is a reason to keep it rather than an
embarrassment to work around.

#### Three answers to "how many namespaces are plural", and which one a given site needs

**Two figures for this were in the corpus by 2026-08-12 with nothing saying how they differ, and a
third was in the code.** A reader meeting them concludes one is stale and picks the wrong one, and
which is correct depends entirely on the purpose. All three are re-derived here with the tool's own
`definitions_in` over the loaded corpus:

| Reading | Answer | Which namespaces |
|---|---:|---|
| Documents containing definition-shaped rows for it | **7 of 9** | E 30, FR 5, D 3, OD 3, SC 3, C 2, U 2; only P and O are single, and it is the same file for both |
| Documents contributing a token no other document contributes | **1 of 9** | `E` alone |
| Logically more than one register — an editorial reading, not a census | **3 of 9** | `FR` and `SC`, one register per feature with colliding tokens; `E`, a ladder plus one index per non-ladder experiment |

**The middle row corrects a figure this pass was handed.** The 3 was relayed as resting on unique
token contribution. It does not: under that test the answer is **1**, because every secondary site for
`D`, `C`, `U`, `OD`, `FR` and `SC` is a strict *subset* of a primary one — including both of the
per-feature namespaces, since feature 001's registers are subsets of feature 002's. The 3 is not
derivable from any token census; it is a statement about the corpus's register *convention*.

**Which site needs which.** A duplicate-register-row guard needs the **7**: it must visit every site
a definition-shaped row can hide at. `identifier-gap`'s plural-register branch is decided by the
**7** as well, because it counts defining documents — its own comment gave the 3, which had it
describing four fewer namespaces than the code reaches, and that is corrected in place. `per_feature`
and `config.json`'s hand-written `what` strings turn on the **3**, which is why they stay
hand-written: a label derived from the union names `specs/002-spec-aware-agent-runtime/spec.md` for
both `FR` and `SC` and erases feature 001's register while looking verified. The **1** is the figure
`_comment_identifiers` is already stating when it says `E` is the only namespace whose plurality that
test can see.

#### The namespace-to-owning-document map cannot have one document per namespace, and the census falsifies its schema

[Why this is documentation and not a check](#why-this-is-documentation-and-not-a-check) envisages *"a
mapping from each namespace to the one document and section that owns it"* as the artifact that would
let the duplicate-register-row guard be restricted to the authoritative register. **That schema is
wrong, and the correction is a measurement rather than a caveat.** Asked of this corpus with the
tool's own `definitions_in` on 2026-08-12, **seven of the nine namespaces are defined by more than one
document**: `E` by **30**, `FR` by **5**, `D` by **3**, `OD` by **3**, `SC` by **3**, `C` by **2**,
`U` by **2**. Only `P` and `O` have a single owning document, and it is the same file for both. The map
must therefore be namespace → **list** of owning sites.

**And for `FR` and `SC` nothing mechanical can tell you the list has two entries.** Their tokens
collide, so asking which single document defines a namespace's whole union names
`specs/002-spec-aware-agent-runtime/spec.md` for both — correctly as far as the token set goes, and
wrongly, because feature 001's FR-001..FR-022 are a subset of 002's FR-001..FR-058 while meaning
different requirements. A derived map would erase feature 001's register and look verified doing it.
`config.json`'s `_comment_identifiers` records the same trap for the hand-written `what` strings and
is why they stay hand-written; the map inherits it. `E` is the only plural namespace whose plurality
that test can see, because no one document covers its union.

This is recorded because it is the obstacle a future pass would otherwise discover after building the
wrong schema. **The map is not built here and neither is the guard.**

#### The duplicate-register-row declination rests on a measurement that could not see this class

The declination above records the candidate guard firing **12 times, all well-formed**, and declines it
on that basis. **That measurement used the first-cell rule only** — `| U-52 |` and nothing else —
which is the narrowest of the three shapes `definitions_in` treats as defining and is not the shape
`FR` and `SC` are written in. Re-derived on 2026-08-12 under the full `definitions_in`, so bold-lead
bullets and identifier-leading headings count too, the same population yields **59** identifiers
defined in more than one document, against **3** under the first-cell rule alone.

Of the 59, **46 span more than one feature** — 22 `FR`, 9 `SC`, 5 `D`, 5 `OD`, 4 `U`, 1 `C` — and the
remaining 13 are 11 `E` and 2 `FR` within one feature. **The `FR` and `SC` entries are the collision
rather than restatements**: they are the same numbers meaning different requirements in two different
specifications, which is the one class in this population that a duplicate guard would be right about.

**Two corrections to the figures this was relayed with, both established here rather than accepted.**
The 59 reproduces exactly and so does the namespace breakdown. The cross-feature total does **not**:
it is **46**, not 41, and the relayed breakdown says so itself — 22 + 9 + 5 + 5 + 4 + 1 sums to 46.
No definition of "cross-feature" available over this population yields 41: treating every non-`specs/`
file as one shared bucket gives 46, requiring two *actual* `specs/<feature>` directories gives **39**,
and requiring two top-level directories gives **10**. The 41 is a transcription, not a reading of the
corpus under some third rule.

This **reopens the declination on a wider measurement; it does not overturn it.** Whether the guard is
worth building now turns on a firing count nobody has taken at the shapes that matter, and 46 of the
59 being cross-feature says nothing yet about how many are defects — the `D`, `U`, `C` and `OD` ones
are the legitimate cross-document restatements the original measurement already found and declined
on. **The guard is not built here.** What has changed is that the number it was declined at was 12 and
the number it would now be judged at is unmeasured.

## Every rule, measured against its own scope

~~Six~~ ~~**Seven**~~ **Eight** of this tool's ~~seventeen~~ ~~**eighteen**~~ **nineteen** checks are
driven by rules in `config.json` rather
than by code, which makes a rule cheap to add and cheap to lose. A rule that
matches nothing contributes no violations, and no violations is what a correct
corpus also contributes. Swept on 2026-08-10 over every rule in every
rule-driven check — the six `inventory_rules`, the two `definition_count_rules`,
the nine `identifier_namespaces`, the three enabled `numeric_kinds`, and the
seven `dry_run.verdict_patterns` — **three were reading nothing at all**, and
each had been silent through every green gate since it stopped.

*(Counts advanced 2026-08-11 with `preserved-evidence`, whose
`preserved_evidence.units` are the seventh rule-driven set, and again the same day
with `count-versus-range`, whose `count_range_rules` are the eighth. **The sweep's
population is left as it stood on 2026-08-10 and is not restated**: it is a dated
measurement of the rules that existed when it ran, and the six units added after
it were not among them. The new set reached the same silence failure this section
is about **twice**, and both corrections are recorded rather than smoothed over.
Scope was first keyed on each unit's tree, so removing an attested tree took the
unit out of scope instead of into violation, and deleting all `59` attested
records took the whole check to `skipped` with a line announcing itself disabled.
~~Scope is now keyed on the attestation, which is committed beside the tree it
covers, and an absent tree is a violation naming the tree.~~ **Superseded
2026-08-11: keying it on the attestation carried the defect rather than removing
it.** A unit whose witness was missing or mis-pathed was filtered out and reported
nothing — `0 error(s), 0 warning(s)` with no skip line, which is what a fully
attested tree prints — so it was indistinguishable from a fixture unit belonging
to another root. Scope is now keyed on a declared `root.marker` that is neither
the tree nor the witness; an absent tree remains a violation naming the tree, and
an absent witness under a present marker became one. `known-bad` holds a unit per
failure kind, so a rule that stops reading takes the self-test with it.)*

The three are not one defect, and the difference decides the response.

* **`committed-harnesses` had a site and lost it.** Its one in-scope match was
  struck on 2026-08-02 and re-stated on 2026-08-03 without a fixed count, on the
  explicit reasoning that `harness/` is the authority for how many harnesses
  there are. The claim was sent somewhere the rule did not look, and nothing
  carried the rule after it. Its number words also stopped at `ten` against a
  directory count of thirteen, so the spelled-out true count could not have
  matched had anyone written it.
* **`findings` had never had one at all, and the reason recorded here was
  invented.** ~~It matched nothing until 2026-08-03 because its pattern required
  a trailing comma, was repaired pointwise, and matches nothing again because the
  scoped documents state no total. Twenty-one phrases of its shape sit elsewhere
  in the corpus.~~ **Corrected 2026-08-11 by replay.** Run against the rule's own
  masking over all ~~`266`~~ **`14`** revisions of `README.md` and
  `research/README.md` — seven each — the
  rule read nothing in **every** revision: there was no comma in any version of
  any of the six patterns, `15 findings and an index` matches the pattern as
  written, and the scoped documents never stated a total to stop stating.
  **The `266` was corrected the same day: it is the repository's total commit
  count at `c9e42ad`, relabelled as a document-revision count, and the replay's
  conclusion survives the correction unchanged.** The
  phrase count outside the rule's scope is `26` at `e551a29`, against `23` when
  it was first measured at `7d723c1` and against the struck claim's twenty-one —
  a dated count over the whole corpus rather than a standing total. **The
  claim that every one of them is prose about conclusions rather than a count of
  documents does not survive reading them either**, and the true shape is a better
  argument than the one it replaces: `five` state a document count explicitly and
  correctly for a population narrower than the glob's — two over the experiment
  ladder (`twelve findings` across nine positions, and `Six of the twelve`),
  `four findings` enumerated by link at E7, `seventeen findings` over one feature's
  directory at a past date, and `Sixteen findings` over `cite_advisor`'s surface.
  Widening the scope would not merely add noise; it would demand that five correct
  scoped counts be rewritten to a corpus-wide total none of them was making. One
  further match is not a count at all: `Feature 002 findings` is the findings
  index's own H1, where `002` names the feature and parses as `2`. The rule has a
  live site as of 2026-08-11 — the repository map states the corpus-wide total,
  `37` across the two `findings/` directories, and the rule reads it there.
* **`gate-state` had never fired anywhere, including the fixture.** Alone among
  the seven dry-run patterns it appeared in neither the corpus nor
  `known-bad`, so nothing had ever shown it capable of matching. The other four
  with no corpus match are exercised by the fixture and were therefore known to
  work. `known-bad` now states a threshold as met, and the self-test requires
  that line, which is what the `EXPECTED` table beside it already says is owed:
  *a rule of seven alternatives is seven rules and a single smoke test would let
  six of them rot.*

**Polarity decides whether zero is a defect, and conflating the two produces the
wrong ruling.** An *assertion* rule — `inventory-count`, `definition-count` —
reads a claim the corpus makes and checks it; zero sites means it verified
nothing. A *prohibition* rule — every `dry_run.verdict_pattern`,
`identifier-resolution` — searches for something that must not be present; zero
sites is the outcome it exists to produce, and demanding a live site would
require the corpus to keep a defect. What a prohibition rule owes instead is a
fixture that fires it, which is why `gate-state` is the only one of the five
quiet patterns that is a finding.

**The `gen_claims.py` floor of one transfers in its visibility and not in its
severity.** That tool errors on a generator matching no sites, on the reasoning
that a silent generator's `0 stale` is what a clean tree also prints — the same
argument, exactly. The severity does not carry: a generator's whole job is to
write claims, so one with no sites is dead by construction, whereas a count rule
with no sites may be reading a corpus that simply makes no such claim, and a
corpus is not obliged to state its own inventory. `definition-count` had already
drawn that line, announcing a skip per rule that matches nothing and declining
to fail the run; `inventory-count` now does the same, and the announcement names
the glob and its count so the reader can see what was not compared.

That answers the question a pointwise repair leaves open. ~~Fixing `findings`'
comma in 2026-08-03 fixed a rule and not the class, and the class recurred in
the same check within a week — twice, in two different ways, neither of which a
pattern edit would have prevented.~~ **Corrected 2026-08-11: no comma was ever
fixed, because no pattern ever had one.** The class argument survives its
example. `committed-harnesses` really did lose a site to a claim being re-stated
somewhere the rule did not look, and `findings` really did run silent through
every green gate — for its whole life rather than for a week — so a rule that
reads nothing goes unnoticed either way. **A rule that cannot fire is a defect in
the instrument rather than in the corpus, so the instrument is where it is now
reported.** The invented comma is itself an instance of the harm: a pointwise
repair was recorded for a rule that had never been repaired, and the record then
supplied a false history to two later passes.

The sweep itself has a residue worth naming. It measures whether a rule *reads*
something, not whether what it reads is worth reading: a rule with one live site
is one edit from zero, and ~~three~~ **four** of the six inventory rules stand
there — `research-documents`, `project-skills`, `speckit-phase-prompts` and, since
2026-08-11, `findings`, each resting on a single cell of `README.md`'s
repository-map table. **`committed-harnesses` rests on a single site too**, at
`specs/001-discovery-validation/harness/README.md`, so the count of one-site rules
is five and only four of them sit in that one table — the qualifier is doing work
and dropping it turns a filtered population into a total. `vendored-repos` is the
one rule with two, and both are prose sentences rather than table cells. Nothing
proposes to duplicate those claims to buy redundancy, because a second copy of a
count is another thing to rot; the floor is what makes their loss audible.

### `vendored-repos` is out of scope in CI by construction, and says so rather than reporting an incident

**The disposition, ruled by the product owner on 2026-08-10: the precondition is
stated in config, the rule is not retired, and no manifest is committed.** The
reasoning is recorded here rather than re-derived, because both alternatives were
considered and both lose something the rule currently holds.

**Retiring it deletes the only guard on a class of claim that demonstrably
rots.** The rule reads `README.md` and `research/README.md`, and both of those
state a repository count that has moved at least once — the `examples/` tree
stood at eight directories when [`research/12`](../research/12-examples-as-corpus.md)
was written and stands at nine now. **Committing a manifest is worse than
retiring**, because it converts a check of *prose against reality* into a check
of *prose against a second copy of the prose*, which is the hazard the residue
above already names about single-cell rules: a second copy of a count is another
thing to rot, and it rots silently against the directories it was copied from.

**It has never fired in CI, and the reason is structural rather than
circumstantial.** `examples/` is git-ignored at `.gitignore:156`, so no checkout
contains it, `_count` returns zero, and the rule short-circuits **before it reads
a claim**. There is therefore no gate figure for this rule at all — not a figure
of zero, but no measurement, because the comparison never runs. The only figure
that exists is a laptop figure, taken in a working tree that has the vendored
repositories beside the corpus.

**What the CI record shows, read per job and per step.** Of the runs of
`ci.yml` available through the API, the `corpus gates (consistency, no model)`
job appears in `108`, and its step `The corpus gate` — the one that runs
`check_corpus.py` — reached a conclusion in `105` of them, `100` successful and
`5` failed. In none of those `105` could this rule have contributed a violation,
because the count it compares against is zero before any claim is read; the `5`
failures belong to other checks. The announcement itself is visible in the run
log verbatim, as `rule vendored-repos disabled: glob examples/*/ matched
nothing`, which is the wording this disposition replaces.

**One measured fact travels with the disposition, and it bounds what the
announcement is worth.** The skip reaches two places: the standard output of a
step that exits `0`, which GitHub renders collapsed, and the
`<details>` disclosure widget the warnings step writes into the run summary,
which GitHub renders collapsed as well. It produces no annotation, no non-zero
exit, and no change to any job's conclusion. It ran that way on every one of the
`105` executed gate steps and drew no response in any of them. **So visibility of
this kind is documentation and not detection**, and nothing here proposes a
louder channel: a rule that cannot read its subject has nothing to escalate, and
an annotation on a condition that is correct by construction is the flapping gate
this repository already refuses elsewhere.

**How a reader now tells the two zero-states apart.** A rule may declare a
`precondition` — a path its subject lives at, and why. Where that path is absent
the skip reads *out of scope in this tree, as declared*, and names the reason.
Where a glob counts zero with no precondition declared, or with the declared path
present, the skip keeps the word **`disabled`**, which is now reserved for the
state that is a fault. The three cases were exercised rather than reasoned: a
working tree with the directories present produces no skip because the rule reads
a live claim, a tree without `examples/` produces the out-of-scope announcement,
and a tree with an empty `examples/` produces `disabled`.

**The scope correction that came out of the same reading, because it changes what
the rule may be credited with.** The rule's `files` scope is
`README.md` and `research/README.md`, and it has never included
`research/12-examples-as-corpus.md`. The stale scope sentence superseded in that
document on 2026-08-10 was therefore **never inside this rule's reach**, and
citing it as evidence that the rule guards live claims would be citing a defect
the rule could not have seen. What the rule guards is the two index claims, both
of which are currently correct at nine; what the `research/12` case demonstrates
is the narrowness of the scope, not the value of the check.

**Widening that scope was measured on 2026-08-10 and declined.** The question the
correction above leaves open is whether the rule should reach `research/12` and
documents like it, and the corpus answers it in one reading. Moving `files` from
the two index documents to `research/*.md` adds **exactly one site**, at
`research/12-examples-as-corpus.md:34`; putting every walked document in reach
adds none beyond it, because the phrase this rule matches occurs in `README.md`
line `157`, in `research/README.md` line `191`, and on that one line. The widened
rule reads `nine` there against a directory count of `9`, so the firing count is
**zero at every scope tried** — two sites read at the shipped scope, three at
`research/*.md`, three again corpus-wide.

**Zero firings is the argument against the widening rather than for it, because
of what the third site is.** The sentence at `:34` is a *quotation of the task
description* this document was written from — it records that the task said one
number and then listed another — and the block beneath it declares the reading a
dated observation of what that pass saw on 2026-08-02 and marks only the scope
claim superseded. The digits agree with the filesystem today because the tree
caught up to the quotation, not because the sentence tracks the tree, and the
sentence is frozen by content: it records what was described, so it may not be
advanced when the directory count next moves. **A rule holding it in scope fires
on a correctly-superseded record the moment a tenth repository is vendored**,
which is the permanent false positive the `unconstructib*` candidate under
[what this cannot catch](#what-this-cannot-catch) was declined over, and it fires
here on a record that is correct rather than merely unhelpful.

**The claim that prompted the question is unreachable at every scope, which is a
second and independent ground.** *"`ls examples/` returns eight directories"*
contains no occurrence of the phrase this rule's pattern requires, so no `files`
setting reaches it and the widening would not have caught it at the time it was
stale. The scope is narrow, and the narrowness turns out not to license widening
it.

## When a figure may be a live total, and when it must be dated

Three rulings in this tree say the same thing from different directions. `gen_claims.py`
refuses to rewrite a register range that shares its line with a struck one, because
substituting the digits alone silences the signal that the note beside them needs a new line.
`ci.yml` keeps the superseded job-duration table beside the current one rather than advancing
the numbers, because the movement from `318` to `540` is itself the finding. The seccomp
variance figures are each declared a closed sample at a stated `n`, on one runner and one boot,
re-derivable from a named artifact. In every case **advancing a digit without the narrative
beside it converts a detectable staleness into an undetectable inconsistency**, and that is the
cost the three rulings are avoiding.

`EXPECTED_PROOFS` runs the other way and does it deliberately. It is a live absolute count, its
own comment says the coupling to the suite is the mechanism rather than an inconvenience, and it
is the only thing that notices a proof being deleted.

**So the distinction is not dated-versus-live.** It is whether anything mechanical recomputes
the figure from a named population. Where something does, the figure may be live, because the
tool holds the truth and a reader does not have to remember it. Where nothing does, the only
honest form is a dated count over a named set — and the set has to be named, because an
unstated scope does not read as a scope, it reads as a total.

### Two corrections the corpus forced on the stricter version of that rule

The rule is tempting to state as *a live total is admissible exactly when something fails if it
goes stale*. The corpus does not support the stronger word, in two separate places.

**A check that notices is enough; a check that fails is not required.** `inventory-count` is
severity `warning`, and CI declines `--warnings-as-errors` on the stated reasoning that the
warning classes flap for a few minutes whenever a document is edited before its generator is
re-run, and *a gate that flaps gets worked around*. `README.md` nevertheless carries live
inventory totals under it — `15` research documents, `18` project skills, `10` Spec Kit phase
prompts — and they are accurate. Nothing fails when one rots; the divergence is still computed
and still printed, to the run-page summary and to anyone running the gate. **Detectability is
the property the three rulings above protect, and severity is a separate decision about
flapping.** A figure whose truth is recomputed and reported has not become an inconsistency
nobody can see, which is the harm.

**A self-describing figure can be gated by counting, and one is.** The stronger rule adds that a
figure whose statement changes the thing it measures can never be gated, because the gate's own
text sits inside the population. `specs/001-discovery-validation/plan.md` is the counterexample:
its line 17 states the OD register's range, the OD register is *defined in that same document*,
and `gen_claims.py` gates it by counting definitions, holding at `30`. It works for two reasons
worth separating, because only the second is about self-reference at all:

- **the update is digit-local.** Rewriting the digits in place neither adds nor removes an OD
  entry, so correcting the figure does not perturb the quantity. Line counts have the same
  shape: replacing `806` with `812` does not change how many lines a document has.
- **the extractor tells the claim from a member.** `_is_whole_register_claim` exists precisely so
  that the `OD-30` inside a range claim is not counted as a thirty-first definition. Without it
  the figure would inflate itself on every write.

So the population a figure counts and the tree a gate touches are different sets, and conflating
them produces the wrong ruling. `EXPECTED_PROOFS` sits in `tests/unit/test_tamper_matching.py`,
and that file **is** a removal-proof target — one proof edits it. It is still not a
self-describing figure, because what the constant counts is proof *declarations* in
`tests/removal_proofs.sh`, and no comment or constant in the target file adds one.

### What is left genuinely ungateable, which is narrower than it looks

Two cases survive, and only these:

- **nothing computes the figure.** No check counts headings, so `slugify`'s agreement with the
  renderer is carried as a dated count at a named commit — `2,534` at `7a60dd3`, and `2,537` when
  [the differential](../specs/001-discovery-validation/harness/slug-differential/) was re-run at
  `58a6277` over `2,428` anchored and `109` blockquoted headings. Both are correct for their sets
  and neither is a ratio a later commit rots.
- **the statement necessarily enlarges the population.** A count of the corpus's headings that
  arrives under a new heading has moved the number it reports. That cost is paid once, at
  creation, rather than on every correction — **this section is an instance, having added
  headings to the corpus it discusses** — which is why the case argues for dating such a figure
  rather than for never gating one.

A count of the harness directories is the first case and not the second: nothing counts them, the
index that states them has gone stale more than once, and the
[harness index](../specs/001-discovery-validation/harness/README.md) now carries its position
count in dated sentences for that reason.

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

### A stale `.pyc` makes two mutation arms one measurement, and restoring the source cannot see it

**Read this before running a mutation sweep whose edits are all the same length.** Established by the
branch-hold sweep at `0d8b2e4`, whose code and long-form record are committed under
`specs/002-spec-aware-agent-runtime/harness/branch-hold-sweep/`. It sits beside the inversion above
for one reason: the integrity check the harness was trusting is *structurally* unable to see the
fault, so the run reads clean exactly where it is wrong.

CPython validates a cached `.pyc` against its source's *(mtime truncated to whole seconds, size)*. A
sweep whose mutation inserts a **constant number of characters** — the `invert` arm wraps a condition
in `not (` and `)`, the same six for every branch in the module — makes every variant of that module
**identical in size**. Two arms on one module inside the same second are then indistinguishable to
that validator, and the stale state it serves is **the previous arm's mutation** rather than the
unmutated module, so the sweep scores one branch on another branch's bytecode. What it produced was
not an error but a confidently wrong verdict set, on a first run.

**Restoration cannot catch it, and that is the property worth carrying forward.** A harness whose
integrity check is "the files are back" verifies the *source*, and under this fault the source is
correct at every single point in the run — only the cache is stale. Restoration has no opinion about
bytecode at all. That is the empty diff above in a second mechanism: a check satisfied by the very
state it exists to detect.

**Purging between arms races the arms; forbidding the write does not.** A purge and the next
interpreter's write are not ordered with respect to each other. So the purge is the *reassuring* half
of a pair whose other half does the work: `threshold_probe.py` deletes every `__pycache__` under
`tools/` **and** runs each child with `PYTHONDONTWRITEBYTECODE=1` and `-B`, and it is the second and
third of those that make its battery sound. Reading the purge as the defence is how the
recommendation travelled.

**The transferable rule, whose precondition is checkable rather than argued.** Forbid the write — in
the child's environment, on its command line, and with the cache prefix left unset so neither can be
routed around. Then **assert that none was written**, before the first arm and after the last, which
is what turns "we forbade it" into "none was written". Then **void the run** if one was. Not purge and
retry: once two arms may have shared a cache, no arm's verdict is known good, so a retry has nothing
to preserve.

The edit-and-restore form of the same fault is under [the stale-`.pyc` trap](#the-stale-pyc-trap),
and finding 038 §6 carries a superseded paragraph recommending the purge — superseded by the sweep's
own record rather than by this entry.

### A process scan must select on this run, and prove it still finds its own

**Asked for by the pass that closed the class, at `5fa07bb`, so the next one is caught at review.**
Two machine-wide process-table scans in `tests/integration/test_lease_revocation.py` were scoped
there. The class is closed in this tree: the only consumers of a machine-wide process listing were
`tests/conftest.py` and those two sites, all three are scoped now, and every other `ps` call in
`tests/` is `-p <pid>`.

**The obvious form of the rule is wrong, and it is wrong twice.** Finding 039 prescribed scoping to
*descendants of the current process, as `conftest.py` already does*, and neither half holds.
`conftest.py` scopes to **direct children** — it compares each row's ppid against `os.getpid()` — not
to descendants. And at the destructive site the child is an **orphan reparented to init**: the nested
run's own sweep reaps it before that process exits, so a descendant walk there finds nothing, kills
nothing and says nothing. That is a **vacuous green**, and it is worse than the noisy red it replaced.
What had to carry the scope instead was a path unique to the run — the calling test's own `tmp_path`,
which the child carries in its argv without being asked to, because its store lives under a
`--basetemp` inside it.

**So the rule is not "scope by ancestry."** A scan that selects processes by a string must select on
something unique to **this run**. Ancestry is one such thing and a good one while it lasts, but it is
unavailable the moment the child is orphaned, and orphaning is the normal case for anything worth
sweeping up after. A path, a nonce or an argv marker minted by this run are the others.

**And any such scope needs a positive control proving the scan still finds its own.** A scope tight
enough to find nothing satisfies the negative arm by itself, so "nothing of ours was left running"
and "the scan is broken" are the same output. Both scopes here carry an arm that fails when the scan
comes back empty, which is the only thing separating those two readings.

**The sharpest measured consequence, because it states the defect better than the mechanism does.**
Since the nested run's sweep reaps the child first, there was nothing of this run's for the unscoped
kill to find — so every one of the ten decoy kills finding 039 recorded was **pure collateral**. The
scan's entire observed effect was on other passes' processes.
### Killing the PID you were handed can leave the measurement running, and a plant-and-restore loop then corrupts the tree it is measuring

**Observed 2026-08-12 while measuring the FR/SC registers, and it invalidated a full 118-row pass
before it was caught.** A census that deletes a register row, runs the gate, and restores the row was
started, then stopped early to change how its output was buffered. The stop used the PID reported for
the command. **That PID was the wrapper, not the Python process.** The wrapper died, the interpreter
did not, and it went on planting and restoring for another ten minutes underneath a *second* census
started in the same tree. Confirmed afterwards by listing processes by name rather than by the
remembered PID: the reported id and the interpreter's id were different, and the interpreter was still
there with a fourteen-minute elapsed time.

**What it cost, and why it did not look like a failure.** The two loops each snapshot a file, mutate
it, and write the snapshot back. Interleaved, one loop's restore writes back a snapshot the other loop
took while a row was deleted, so a row is lost *permanently* and every later iteration is scored
against a register that already has a hole in it. Feature 001's `FR-019` went missing that way. The
run kept printing plausible per-row results for another eighty rows — the warning counts were simply
inflated by the standing hole, which reads as a checker doing more work rather than as a corrupted
input. **A silent-row census is exactly the measurement this failure cannot be seen in**, because its
own success criterion is that nothing goes quiet, and a permanent extra hole makes things *louder*.

**Three guards, and the middle one is the one that would have caught it.**

* The row list must come to the expected total or the run refuses to start. This is what first
  exposed it — the second census announced **118** rows where the register census says 119, and that
  single missing row was the only visible symptom of ten minutes of interleaved corruption.
* **Before each plant, assert the target register is at full strength.** A restore-and-continue loop
  carries damage forward silently; asserting the precondition per iteration converts that into a halt
  at the first bad row instead of a plausible report over all of them.
* Exactly one definition must disappear per plant, so a fat edit is never recorded as a single-row
  deletion. Checking only that *the token* is gone does not establish this.

**And the loop must restore on a signal, because the signal is what breaks it.** A `finally` does not
run on `SIGTERM`, so the default disposition leaves the tree mutated at whatever row was in flight.
A handler that writes the held snapshots back and exits costs four lines.

**The rule.** Do not stop a plant-and-restore loop by killing a remembered id; select it by name,
confirm it is gone by name, and only then read the tree. This is the neighbouring case to the entry
above — that one is about a scan selecting on something unique to *this* run, and this one is about a
kill doing the same. In both, the id you have is not reliably the process that matters.

**The restore discipline held, and is what made this recoverable.** The tree was restored from bytes
and verified by presence — every one of feature 001's 22 `FR` tokens checked individually, not the row
count alone. A count is not enough on its own here for a reason worth stating: had the interleaving
lost one row and duplicated another, the count would have reconciled while the register was wrong.


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

### A negative search result is a claim about a document, and one search form does not establish it

**This one caused a false retraction, and that consequence is why it is filed as a trap rather than
as carelessness.** On 2026-08-10 a pass reported that a measured margin appeared *nowhere* in the
corpus or in any artifact, and that the sample count quoted beside it matched nothing written down.
Both statements were false. The margin was written in three files and the count in the same three,
two of them markdown documents this checker already walks. On the strength of that clean negative a
correct record was withdrawn and its author was described as having invented a measurement.

**The mechanism is that the corpus writes one figure two ways, and neither precise form finds the
other.** The margin carries its unit suffix in the battery comment — `1.16x` — and sits bare inside
emphasis in the two markdown documents. A search for the suffixed spelling returns the battery alone;
a search for the emphasised spelling returns one markdown file alone. Each comes back as a single
confident hit, and a single hit reads like the whole answer rather than like one of two spellings.

**A second mechanism accounts for the other false statement, and it was reproduced while writing this
entry.** The claim that the sample count was invented came from reading the count as *three* where
the document says *three, superseded by four*. Both statements live on the **same** line of
`specs/002-spec-aware-agent-runtime/tasks.md`, and that line is **1873** characters long: it opens
with the three-sample re-derivation and closes, past any reasonable truncation, with the fourth
sample and the revised count. A reader who takes the first few hundred characters sees a
three-sample statement and no four-sample one, and concludes the four-sample figure was invented.
The first read taken for this entry did exactly that and had to be corrected. **Truncation is a
search form too** — a long line is a document a partial read misrepresents, and the fix is to read
the line to its end or to grep for the figure inside it rather than to eyeball the head of it.

**The corpus does not support the further claim that the loose search was impractical, and the
correction strengthens the rule.** Over the working tree the bare form returns **7** files, and all
three sites are among them. Searched bare against the same index the checks use it returns **6**,
because `tests/` is outside the index's roots — **2** of those name the margin, and the other **4**
are a version-number table and three trace artifacts holding the digits incidentally. Even the
corpus-scoped search, reaching only two of the three sites, refutes *appears nowhere* outright. The
reading that put the figure in the dozens counted the git-ignored vendored tree, which supplies
**102** of the **110** files the widest form matches and none of the sites. So the search that would
have found both spellings was never buried — it was a single-digit result that was not run, and
`--hidden --no-ignore` is what turns it back into noise. The remedy is not "search harder", it is
one cheaper search, scoped.

The tell is the mirror of
[Reading an instrument is not measuring it](#reading-an-instrument-is-not-measuring-it--plant-the-case-instead),
and the two now bracket the same error from both sides. There, the claim described *behaviour* and
the evidence was a *document*. Here, the claim describes a *document* and the evidence is *one search
form* — a claim about what a corpus contains, resting on a single guess about how the corpus spells
things. **A negative search result carries the same burden as any other relayed claim**, and the
burden is discharged by searching the bare numeral scoped to the plausible files rather than the
formatted one.

**The two costs are not symmetric, and the discipline should not be either.** A false positive here
buys one unnecessary check: a figure is searched again and found where it was expected. A false
negative retracts a true record, and it does so with the particular authority a clean negative
carries — the reader cannot tell a figure that was never written from a figure that was written in
another spelling, because both print nothing. It also attributes fabrication to whoever wrote the
record. That asymmetry is the whole argument for spending the extra search every time.

**A second limb was proposed for this entry and the measurement did not support it.** The suffixed
site is a Python comment, and no check here reads Python as a document — the corpus walk loads
`.md` and `.markdown` only, and the one check that parses source, `lifecycle-taxonomy`, reads a set
of member names out of `src/contracts/terminal.py` rather than any figure. That much holds. But it
was not the mechanism in this instance: the margin has **two** markdown homes besides the comment,
and the corpus-scoped search reached both, so the record was recoverable without reading a line of
Python. The episode is a search-form failure end to end, and counting it as an instance of the
source-blindness residue would be counting it twice. One of those two homes is worth naming for a
different reason — `specs/*/tasks.md` is walked at role `other` and is **not** in the consumer set,
so `numeric-provenance` does not read figures there either. The figure's only figure-checked home is
`specs/001-discovery-validation/plan.md`.

**What the source-blindness residue does amount to, measured on 2026-08-10 rather than estimated.**
The search index that answers "appears nowhere else" does include `.py`, but its roots are
`research`, `specs`, `docs`, `README.md`, `.cursor/skills` and `.specify/memory` — so `tests/`,
`tools/` and `src/` sit outside it entirely, and the **125** indexed Python files all live under
`specs/*/harness/`. Extracting figures from every Python comment and docstring in the repository
with the corpus's own extractor, under all five implemented figure kinds, gives **356** occurrences
and **194** distinct figures, of which **28** appear nowhere else at all. Hand-triaged, **11** of
those **28** are measurements this project took and has no other record of; the remainder are
illustrative values inside rule docstrings, self-test fixture expectations, and one total derived in
place from a price schedule stated on the same lines. Under the three kinds the gate actually
enables, the exposed set is **12** and its evidential subset is **2**. The population is small and
concentrated: **8** of the **11** are in `tests/batteries/test_seccomp_overhead.py`, one of those
eight is also carried in `tools/seccomp_variance_probe.py`, and the remaining three sit in
`src/supervisor/lease.py` and `tests/integration/test_store_concurrent_writers.py` — **4** holding
files in total. **No check was added for it, because a population that size is a smaller thing than
the rule that would have to read Python to catch it**, and the figure that prompted the count was not
in the population.

### A measured report is not a measured figure — the wrong denominator arrived beside a conclusion that had genuinely been replayed

**On 2026-08-11 a pass replayed the `findings` inventory rule over its own scope, reached the right
conclusion, and published the wrong denominator beside it.** The replay was real and its result
stands: the rule matched nothing in any revision of `README.md` or `research/README.md` before
`451725f`, and the one site at that commit agrees with the filesystem. What the report gave as the
population replayed was `266`. The two documents carry seven revisions each, so the population was
`14`, and `266` is the repository's total commit count at `c9e42ad` — a commit count relabelled as a
document-revision count. `266` against `14` is a factor of nineteen, and the figure reached a brief,
this file at three sites, and the rule's own configuration comment before anyone re-derived it.

**This route is filed separately from the two above it because neither of their remedies fires on
it.** The recorded defences answer a figure carried from memory —
[one cheaper search, scoped](#a-negative-search-result-is-a-claim-about-a-document-and-one-search-form-does-not-establish-it)
— and a history the corpus asserted without anyone replaying it, whose defence is the replay itself,
recorded under [What this cannot catch](#what-this-cannot-catch) beneath *Anything outside markdown*.
A search finds this figure immediately, because it was written down and correctly transcribed
everywhere it travelled. A replay was performed, by the pass that reported it. **The defect is
confined to what the number counted, inside a report whose method was sound in every other respect**,
so a reader holding *replay before relaying* has already discharged the rule that was supposed to
catch it. The owner's tally puts this fifth among the week's wrong figures and first of its route.

**The tell is cheap, needs no tool, and was available throughout: a count is worth checking against
the age of the thing counted before it is checked against anything else.** Two markdown files in a
repository days old cannot have `266` revisions between them, and no path in the tree could. That
reading costs no command and no index, and it separates an impossible figure from a plausible one
without knowing the right answer — which is what makes it usable by a reader who has no way to run
the replay again.

**What kept the substitution invisible is that the wrong figure was a near neighbour of the right
one.** Both are counts of objects in git history, the two commands that produce them differ by a
pathspec, and the wrong one was sitting inside the very comment the pass had been sent to replay. So
the number was not conjured; it was carried one field to the left, out of the artifact under
examination. **A figure that is wrong in kind announces itself, and a figure that is wrong in
population does not** — taken from the same log as the right answer, it reads as the output of the
work that genuinely was done.

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
files. **That is exposure, not defects.** ~~Exactly one real instance has been found~~ ~~**Two, as of
2026-08-10**~~ **Three, as of 2026-08-11**, and most bare references are unambiguous to a reader who
is already in the right directory. No check was built, for the same reason `register-range` was left
hand-maintained: a rule firing on every bare basename would be almost entirely false positives.

**The second instance arrived on 2026-08-10, and the pair did not share a basename at all.** A brief
warned that tamper needles in `src/analysis/codegraph_pin.py` were live, and quoted the plant site as
`).fetchall()` followed by `finally:`. Those two lines sit adjacent at `codegraph_pin.py:121-122` —
and adjacent again at `tests/unit/test_codegraph_pin.py:85-86`, where they close a `sqlite_master`
query in a helper. A reader checking the warning against the tree finds the quoted text twice and
cannot tell from the quotation which file was meant, so a hazard already resolved in one file reads
as live in the other. The wrinkle is that the sibling is not a copy and shares no basename: it is the
**`test_`-prefixed sibling**, which the eye reads as a different filename and a substring search reads
as a superset. Every `src/` module with a unit test has one, so this variant of the exposure is as
wide as the suite — and it is the worse variant, because a bare basename at least *looks* ambiguous,
whereas quoting a file's text and naming one file looks specific. The remedy is the cheap one the
house already uses everywhere else: **quote a path with a line number, not a string.** `git grep -n`
on the quoted text before relaying it costs one command and would have shown both sites.

**The third instance arrived on 2026-08-11, in this file, and it is the variant with a measured
cost.** The attestation section named `` `neutralise_decision.py` `` bare, in a paragraph whose
subject is the attestation machinery under `tools/`. The file is not under `tools/` at all — it is
`specs/001-discovery-validation/harness/verifier-vs-judge/neutralise_decision.py`, three
directories away under a different top-level tree. A pass reading that sentence searched `tools/`
first and found nothing. **What distinguishes this variant from the two above is that the reader is
not in the right directory and has no way to know it:** a shared basename is ambiguous between
trees a reader can enumerate, and a `test_`-prefixed sibling is at least adjacent to its subject,
whereas a bare name in a paragraph about one directory asserts a location by adjacency. The
surrounding prose is the misdirection, so the name is not ambiguous — it is confidently wrong.
Corrected here, and swept: the same sweep gave a path to `` `cli.py` ``, `` `runner.py` `` and two
sites of `` `figures.py` ``, all of which live under `tools/corpuscheck/` while reading as though
they sat in `tools/`. **This is the instance that prices the entry**, because the two above cost a
reader a moment of ambiguity and this one cost a pass a search of the wrong directory.

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

### The entry above is exact about the index and silent about the tree, and on 2026-08-11 it was the tree that fired

**The index hazard above is real and still holds; it is incomplete, and the missing half is where the
damage came from.** On 2026-08-11 two passes shared this working tree. `git status` was read for
staged entries nobody created at every point the entry above prescribes it, and **the index was
unheld every single time it was checked**. Twice that day a concurrent pass's write to this file
silently reverted an edit another pass had already made, and **nothing reported an error** — not a
gate, not a hook, not `git` itself. One push then carried a commit its author had never gated.

**`git add <path>` is a statement about the working tree, so a defence built on it inherits whatever
the tree happens to hold at that instant.** Staging explicit paths keeps another pass's *index* out
of your commit and does nothing whatever about another pass's *writes* to the file you are about to
stage. The two hazards share a name and not a mechanism, and closing the first leaves the second
exactly as wide as it was.

**The tell, and it is the reason no instrument caught this: a reverted edit and an unmade edit are
indistinguishable in a working tree.** Re-reading the file shows text without your change in it, and
that is what the file looks like both when your edit was overwritten and when you never made it.
This is the [emptiness-test
inversion](#the-emptiness-test-inversion--git-diff-cannot-tell-unchanged-from-changed-back) one level
up. There an emptiness test over a diff could not separate *unchanged* from *changed back*; here a
read of the tree cannot separate *never written* from *written and reverted*, and both are satisfied
identically by the state that means the work is gone.

**So the practice that holds is index-only, and every step of it is a presence test.** Intended
content is built from `git show HEAD:<path>` rather than from the shared tree, because a blob at a
commit is a baseline no concurrent writer can reach — the same re-anchoring [finding
038](../specs/002-spec-aware-agent-runtime/findings/038-corpus-check-branch-population-and-the-instrument-declined.md)
§8 had to make after its own sweep took a contaminated baseline from the tree it was mutating. Every
edit is located **by search rather than by line number**, because a concurrent write moves lines and
a span located by number then rewrites something that was never read. The resulting diff is applied
with `git apply --cached`, which writes the index and never the tree. And the result is verified **by
presence at the commit** — `git show <sha>:<path>` for a string only the edit contains — rather than
by an empty `git diff`, which is the inverted test arriving one more time.

**What the arrangement buys is that a pass cannot absorb a hunk it never read.** The commit carries
what that pass built from `HEAD` plus its own edits, and a concurrent pass overwriting the file
underneath it changes what is in the tree without changing what was staged. This entry sits beside
the one above rather than replacing it: the index hazard is real, `git status` is still the read that
finds it, and a tree shared with a live writer is a second hazard that read cannot see.

**The route has a residue, and on 2026-08-11 it fired within the hour of the route being written
down.** An index-only pass never writes the working tree, so a commit built and pushed this way
leaves the shared tree holding exactly the content the commit replaced. `b9760cd` is 89 insertions
and 12 deletions over four paths, and the reading taken after it was pushed had those same four
paths at ` M` with a working-tree diff of 12 insertions and 89 deletions — the commit's exact
mirror, which is the shape this residue always takes.

**The direction is the whole of it: the tree is *behind* the commit rather than ahead of it, and
`git status` renders the two identically.** A path reports ` M` when it holds work nobody has
committed and when it holds content a pushed commit has already superseded. From there a `git add`
or a `git commit -a` over those paths stages a revert of published work — planted rather than
reasoned, with an index-only commit carrying a needle, `git add` on the path, and a staged blob
holding no needle at all. By the tell this entry already states, that revert arrives looking like an
ordinary edit, so the practice adopted to stop passes absorbing each other's hunks leaves behind a
state in which the next routine command silently undoes a pushed commit.

**What separates *behind* from *ahead* is the diff, and never the status.** Both directions were
planted over one file. Where the tree was behind, the working-tree diff was the commit's exact
inverse: a commit of 3 insertions and 1 deletion left a tree diff of 1 insertion and 3 deletions.
Where the tree was ahead by a single uncommitted line, the same comparison read 1 insertion and 0
deletions against that same commit — not an inverse, and not discardable. `git status` printed ` M`
in both cases. A tree that is genuinely ahead is somebody's uncommitted work, and the inverse check
is the only thing standing between reading that work and destroying it.

**So the remedy belongs beside the practice and it runs after the push: `git checkout HEAD --` over
the paths the pass wrote, once the tree diff has been confirmed to be the commit's inverse and to
carry nothing of its own.** That verb is the repair here rather than the hazard, because the index
already holds the committed content — and it is the repair in that one direction only.

**Its verification is by presence, and a ` M` that cannot report its own direction is the third
instrument this file records as blind in the same way.** An empty `git diff` after the checkout is
satisfied by the tree matching whatever `HEAD` holds, including a `HEAD` that never carried the edit
— a push that failed, a ref that moved underneath. What answers is a string only the edit contains,
read back twice: out of the commit with `git show`, and out of the working tree with a grep. The
[emptiness-test inversion](#the-emptiness-test-inversion--git-diff-cannot-tell-unchanged-from-changed-back)
is the first rung, where an emptiness test over a diff cannot separate *unchanged* from *changed
back*; the paragraphs above are the second, where a read of the tree cannot separate *never written*
from *written and reverted*; this is the third. The count is over instruments rather than over
mentions of that entry, of which this file carries two more — one applying its presence remedy to a
planted tamper needle, and one explicitly declining membership as complementary rather than
duplicate.

### One worktree per pass, because every defence above is a read a pass has to remember to take

**Ruled by the owner on 2026-08-11: each non-trivial concurrent pass gets its own git worktree.**
`git worktree add -b <branch> <path> <base>`, work there, commit on that branch, report the resulting
SHAs to the coordinator, who integrates. Nothing here is new machinery. It takes the
[recorded-SHA set](#use-a-detached-worktree-names-no-path-so-two-passes-share-one-and-the-collision-is-silent-in-the-direction-that-matters)
— the one push-safety method of four that discriminates — and makes the isolation it depends on
**structural rather than conventional**: a pass that cannot see another pass's tree cannot absorb its
writes, and a branch carrying one pass's commits cannot publish another's.

**What the shared checkout cost on 2026-08-11, with three passes in it, and the three failures are
the three scopes the git verbs have arriving on one day.**

- **The branch.** The Phase 5 pass found two commits it had not written — `82384f7` and `6756109` —
  interleaved between its own `4ba7bea` and `f09b6f0`. Both touch `src/analysis/codegraph_pin.py`,
  which is the file that pass's own T136 removal proof tampers, and four of the declared proofs name
  it at `7c917d6`. **A rotted tamper needle was the live risk rather than a hypothetical one**: the
  proofs re-gated at the merged `HEAD` and the needles survived, which is luck of exactly the kind
  this file keeps having to record, not a property of the arrangement.
- **The remote.** That pass's push carried the sibling's two commits with it, and both are reachable
  from `origin/main` today. No push can carry a subset, for the reason set out
  [one entry along](#use-a-detached-worktree-names-no-path-so-two-passes-share-one-and-the-collision-is-silent-in-the-direction-that-matters);
  it is not restated here.
- **The tree.** A third pass's in-flight uncommitted edits were misattributed by a second pass to the
  first.

**This class is already recorded here from earlier instances, and the ruling exists because recording
it has not stopped it.** [The index hazard](#staging-explicit-paths-protects-you-from-another-passs-working-tree-not-from-its-index)
dropped two findings out of version control. [The tree hazard](#the-entry-above-is-exact-about-the-index-and-silent-about-the-tree-and-on-2026-08-11-it-was-the-tree-that-fired)
silently reverted two edits to this file in one day and let one push carry a commit its author had
never gated. [A stale held-file list](#a-held-file-list-decays-from-the-moment-it-is-written-and-relaying-one-from-memory-asserts-a-reading-nobody-took)
handed a pass a false all-clear on two files it happened not to need. Each of the three ends in an
instruction to read something — `git status`, the commit range, the tree over the brief — and each
read is available only to a pass that remembers to take it. **An isolated worktree ends in a state
that does not require the read**, which is the whole of what the ruling buys.

**Cost, re-measured on 2026-08-12 rather than transcribed, and the figure this rule was priced with
was measuring something else.** `git worktree add --detach` at `7c917d6` — 906 tracked files — took
`0.532 s` and then `0.466 s` on two consecutive creations. The checkout is not the cost. The gate run
is: `check_corpus.py` from the fresh worktree took `14.4 s` and read `0 error(s), 0 warning(s)` with
the one declared skip that a tree holding no `examples/` always reads, per
[the baseline table](#gating-a-commit). The ~20 s this convention has been quoted with is the
creation and one gate run together, and the second half of that would have been paid in the shared
tree too. **So the isolation is very nearly free**, and that is the measured answer to whether it is
worth keeping.

**The toolchain runs from a worktree provided `PATH` names the shared tree's venv by absolute path**,
which is [the amended companion rule](#use-a-detached-worktree-names-no-path-so-two-passes-share-one-and-the-collision-is-silent-in-the-direction-that-matters)
and its measurement, unchanged by this entry. One worktree per pass makes that rule load-bearing
rather than a special case: there is now always a worktree, so there is never a `.venv` beside the
gate being run.

**Where this meets the index-only workflow, which is the sharp part.** [The index-only
practice](#the-entry-above-is-exact-about-the-index-and-silent-about-the-tree-and-on-2026-08-11-it-was-the-tree-that-fired)
exists to survive a **shared** tree, and it carries a defect that only became reachable once `tools/`
entered `include`: **every gate reads the working tree and none of them reads the index.**
`corpus.build` walks `base.rglob("*")` and reads each path with `read_text`, and no **gate** under
`tools/` invokes `git` for content at all — the one instrument here that does is `cite_advisor.py`,
which reads requirements and contracts out of a revision under `--at` and is advisory, so the
exception belongs to the thing that cannot fail a commit. Established by plant rather than by that
reading, on
[this file's own rule](#reading-an-instrument-is-not-measuring-it--plant-the-case-instead): five
broken `#fragment`s staged into the index alone, with the working tree left correct, leave
`check_corpus.py` at `0 error(s), 0 warning(s)`, and the control is that a single broken `#fragment`
written into the **tree** fires `link-anchor` by name and takes the run to exit 1. So an
index-only edit to a **gated** file is staged, committed and pushed having never been gated once —
the hunk the gate would have objected to is in the commit and was never in the tree the gate walked.
The pass that produced `7c917d6` deviated from index-only for exactly this reason and was right to.

**So the two workflows are not alternatives; they are keyed on whether the tree is shared.**
Index-only in a shared tree, where the hazard is a concurrent writer and the price is a commit you
must then get gated by some other route. Ordinary editing in an isolated worktree, where there is no
other pass to lose work to and the gate reads precisely the bytes you are about to commit. **The
index-only entry above is not superseded and is not to be deleted**: a pass may still be sent into
the shared tree, and everything that entry says about that case remains correct.

### "Use a detached worktree" names no path, so two passes share one, and the collision is silent in the direction that matters

**On 2026-08-10 two concurrent passes were each told to measure in a detached worktree, and both
created it at `/tmp/f2a-wt`.** The second pass's checkout wiped three worktrees the first had placed
there and left one of the first pass's worktrees *inside* the second's tree. Nothing was lost,
because both passes had already captured their measurements — which is luck, not a property of the
arrangement.

**The damage a shared scratch path does is not the lost checkout, it is the polluted `git status`.**
A stray worktree inside your tree shows up as untracked files under a path you did not create, and
`git status` is precisely the instrument a pass reads to decide what to stage. This repository
already requires reading it for [staged entries you did not
create](#staging-explicit-paths-protects-you-from-another-passs-working-tree-not-from-its-index);
a second pass's checkout arriving as untracked noise makes that read harder at the moment it is
being relied on. The failure is silent, and it is silent in the direction that corrupts a commit
rather than the direction that blocks one.

**The convention, in the form a brief can quote:** *"Put the worktree at
`/tmp/f2a-<job>-<unique>`, never at a shared fixed path, and never at `/tmp/f2a-wt`."* A brief that
says "a detached worktree" and names no path has delegated the collision to chance, and the two
passes that collided were each following their brief exactly. `git worktree list` before creating
one costs nothing and shows what is already there; `git worktree remove` when done keeps the next
pass's `git status` clean. The proximate cause is the brief, so the remedy belongs in the brief.

**Amended 2026-08-11: the convention above is the form a brief quotes, and quoted with the other
standing rule about `PATH` it supplies no interpreter at all.** The companion rule reads
*"`export PATH="$PWD/.venv/bin:$PATH"` before any gate"*. `.venv/` is git-ignored at `.gitignore:5`,
so a clean detached worktree has no `.venv`, `$PWD/.venv/bin` is an empty path element, and the rule
resolves to nothing. The two rules cannot both be followed, and they have been quoted together in
every brief for a long time; what has been happening instead is that each pass silently pointed
`PATH` at the **shared tree's** `.venv/bin`, which is obvious enough that nobody filed it. **What a
bare `python3` gets there is not a smaller environment, it is a different interpreter:**
`/opt/homebrew/bin/python3` is **Python 3.14.6** against the venv's **3.12.11**, and it has no
`pytest` at all. A missing minor version is the reading to expect, not a missing site-packages set.

**The instruction that holds, and it is one line: name the shared tree's interpreter by absolute
path.** `/path/to/shared/.venv/bin/python <gate>` from inside the worktree. **Measured sound**, and
the mechanism is why: CPython resolves `sys.prefix` from the *invoked path* — it reads the
`pyvenv.cfg` beside the executable — so the venv answers `sys.prefix` as its own directory from any
cwd and nothing in it resolves relative to a tree. The half that could have gone wrong is what the
venv puts on `sys.path`, and it puts **only** its own `site-packages`: this venv has no editable
install, no `.pth` file and no entry for this project, so **no path element points at the shared
tree's source.** Repository modules come from the worktree — `tools.corpuscheck` imports from the
worktree when invoked there and from the shared tree when invoked there, checked both ways. So the
shared venv contributes third-party dependencies and nothing else, and it is sound **for all seven
gates** rather than for some of them.

**A `PATH` prefix and an absolute `-m` are outcome-identical here, and the absolute form is
preferred for being unambiguous rather than for working better.** Both were run over the whole gate
set from a clean detached worktree and returned the same figures. Nothing in the seven needs the
prefix: `tools/threshold_probe.py` spawns its child as `sys.executable` and the suite's
subprocess-spawning tests do the same, so children inherit the parent; `tools/instruments.py`
carries bare `python3` command tuples, but `--check` compares them to `ci.yml` as **text** and
executes none of them, which is why it passes with no venv on `PATH` at all. An absolute path also
cannot be reordered out from under a gate by a later `PATH` edit.

**Two of the seven care which directory they run from, and only one of them can be got wrong
quietly.** `tools/gen_claims.py` takes `--root` defaulting to `"."`, so it reads the tree you are
standing in; run from a foreign cwd it exits **1** with *"the 'register-range' generator matched no
sites"*, which is the no-sites guard refusing to report a vacuous `0 stale` and is the behaviour to
want. `python -m pytest` needs the repository on `sys.path` and gets it from `pythonpath = ["."]`
resolved against the rootdir, which is discovered from the test path — so it is correct from any
cwd provided that path points into the tree, measured from `/tmp` against an absolute `tests`
path. The other five anchor on `Path(__file__)` and are cwd-independent: `tools/check_corpus.py`
run from the worktree and from `/tmp` produced **byte-identical** output. **Standing in the
worktree root satisfies all three cases**, which is why the instruction is one line and not four.

**The hazard this leaves, and it is the reason the entry says "shared" twice: the interpreter is
shared even when the tree is not.** `site-packages` resolves inside the shared tree's `.venv`, so a
gate run from a pristine detached worktree is reading a dependency set another pass can be
installing into at that moment, and it would read that pass's environment rather than yours.
*"Clean detached worktree"* reads as full isolation and it is **tree** isolation only. Nothing here
claims that has ever happened; the entry exists so that a pass reporting gate numbers knows the
environment was not part of what its worktree isolated.

**On 2026-08-10 a brief told a pass to "commit and push" while a concurrent pass held committed but
unpushed commits on the same branch.** There is no way to push only your own commits. `git push`
advances the remote ref to the commit you hand it, and every commit reachable from that one travels
with it regardless of who wrote it — so the instruction was telling a pass to publish work it had
never read. Nothing went wrong, because the sibling pushed in the interval and the range was already
empty when the pass reached it. That is luck. The brief did not arrange it and could not have.

This is [the entry above](#staging-explicit-paths-protects-you-from-another-passs-working-tree-not-from-its-index)
one level up, and the family relationship is the part worth carrying. Three git verbs, three
different scopes: `git add <path>` is scoped to **a path**, `git commit` is scoped to **the index**,
and `git push` is scoped to **the branch**. Staging explicit paths is a real defence and it is exact
about what it defends — it bounds what enters *your commit*. It bounds nothing about what a later
push publishes, because the push reads none of it. It reads the ref.

**So the rule is one more read, and it is one command: before pushing, run
`git log --oneline origin/main..HEAD` and look at what it prints.** If every commit in the range is
yours, push. **If any commit is not, do not push.** Commit locally, report which commits are in the
range and that you did not author them, and stop there. Do not rebase them out, do not attempt to
push a subset, and do not judge from the outside that they look finished — a commit can be complete
and correct and still be held back on purpose, and the only pass that knows is the one that wrote it.
Improvising is the failure, not the delay.

**Read the range by subject, not by the author field.** Every pass in this repository commits under
the same `user.name` and `user.email`, so `%an` answers "yours" for every commit in the range and a
check written against it reports clean no matter whose work is sitting there. A test that returns the
same verdict on every input is vacuous — true, and carrying no weight, in the sense the suite's own
vacuous-invariant banner means it. What actually distinguishes your commits is that you wrote their
subjects minutes ago. Recognise them, and treat a subject you do not recognise as a stop.

**Amended 2026-08-11: the two-field form of that check is vacuous too, the span is measured, and the
replacement that discriminates is named rather than left to the reader.** The rule as it travels in
briefs reads *"push only if the commit range is entirely your own authorship — verify with
`git log --format='%an %ae'` over the range"*, and the second field buys nothing. Over all `322`
commits reachable from `HEAD` at `f09b6f0`, `%an` takes exactly one distinct value; `%ae` takes two,
and the second belongs to `deea4f3`, the *"Initial commit"* authored
`379170+dperussina@users.noreply.github.com` and committed by `GitHub <noreply@github.com>` from the
web UI on 2026-08-02. **The outlier is the repository's own root commit rather than another pass**, so
it can never sit in a push range, and every commit any pass has ever made carries the identical pair.
A two-field check is the one-field check with a second constant beside it.

**The vacuity is not a no-op, which is why this belongs with the traps and not with the style
notes.** The check does not decline to answer — it answers *"the range is entirely yours"* on the
exact input where the range is not, and so licenses the push it exists to prevent while reporting
that it verified the opposite. The instances this repository has recorded are real, and they are of
two kinds. **Pushing:** the 2026-08-10 brief at the head of this entry, which told a pass to commit
and push while a concurrent pass held unpushed commits on the same branch, and where nothing went
wrong only because the sibling pushed in the interval — that paragraph calls it luck; and 2026-08-11,
where *"one push then carried a commit its author had never gated"*, recorded in
[the entry on the tree the index rule is silent about](#the-entry-above-is-exact-about-the-index-and-silent-about-the-tree-and-on-2026-08-11-it-was-the-tree-that-fired).
**Staging**, which this check does not cover and cannot: the explicit-path practice was adopted
[after two sweep-ups of other passes' work](#staging-explicit-paths-protects-you-from-another-passs-working-tree-not-from-its-index),
and findings 025 and 028 were dropped out of version control entirely by the `git commit -a` that
shape leads to.

**Four candidate replacements were measured rather than reasoned about, in a scratch worktree where
two simulated passes committed to one branch — two commits "mine", one a sibling's, interleaved so
the sibling's sits in the middle of the range.** Only one discriminates:

| method | reading on a range holding another pass's commit | discriminates |
| --- | --- | --- |
| `git log --format='%an <%ae>' <base>..HEAD \| sort -u` | one distinct author; reports clean | **no** |
| author date against committer date, `%aI` against `%cI` | identical on all three commits, and all three inside one second | **no** |
| `git reflog show <branch>` | all three commits, one author, no field naming a pass | **no** |
| recorded-SHA set equality | the sibling's SHA is in the range and absent from the recorded set — **stop** | **yes** |

**Recording your own SHAs is the only sound method of the four, and a single sound method beats a
menu.** Capture `git rev-parse HEAD` immediately after each commit you make, and push only when
`git rev-list <base>..HEAD` equals that recorded set exactly, both sorted. It depends on nothing the
environment can make ambiguous: not on an identity field every pass shares by configuration, not on a
clock two passes can occupy in the same second, and not on a log that records both passes into one
file.

**Why each of the three losers loses, separated because the reasons do not transfer.** The identity
fields are constant by configuration, so they are the vacuity above. Dates fail because concurrency
*is* the hazard rather than an aggravation of it — the three probe commits share a single second, so
any window wide enough to contain your own work contains a sibling's committed alongside it. And the
reflog fails on **scope**, in the way most likely to mislead: the `HEAD` reflog genuinely is
per-worktree, at `.git/worktrees/<name>/logs/HEAD`, which looks like the discriminator until the
branch reflog turns out not to be one. Commits to a branch land in the shared
`.git/logs/refs/heads/<branch>` from every worktree, and the arrangement here has every pass
committing in the one shared tree in any case.

**The method's own failure mode, stated because it will fire rather than left to surprise somebody.**
Amending or rebasing your own commit gives it a new SHA, so the recorded set goes stale and the
comparison reports **stop** over a range that really is entirely yours. Measured: an amend moved
`f1bc838` to `de3a1b6` and the comparison refused. That is a false alarm **in the safe direction**,
and the discipline is to re-record after any history rewrite — never to loosen the comparison, which
would trade a sound method for a comfortable one.

**None of this weakens the paragraph below, and it is worth saying so explicitly.** A *gate* still
cannot answer the question, for exactly the reason given there: another pass's commits are not
defective, so nothing that inspects them can object. A recorded SHA set is not a gate. It is the pass
writing down, at the moment of creation, the one fact that lives outside the tree — and it is
available only to the party that holds it. What this amendment adds is that the fact can be *written
down* rather than only *recognised*, so a reader's memory of what they committed minutes ago stops
being the sole instrument.

**No hook and no gate can take this over**, and the reason is not that nobody has written one. The
question is not one a check can answer: another pass's commits are not defective, so every gate here
passes on them cheerfully. `check_corpus.py`, `check_tampers.py` and the suite all go green on a range
full of somebody else's finished work, and they are right to. What makes the range wrong to push is a
fact about intent that lives outside the tree entirely. The range's contents are the whole signal, and
a reader is the only instrument that can use them. This repository has no `pre-push` hook and
`core.hooksPath` is unset: between a pass and the remote there is nothing at all.

### A held-file list decays from the moment it is written, and relaying one from memory asserts a reading nobody took

**The same 2026-08-10 brief named three files as held by a concurrent pass when five were.** The two
it missed were `tests/removal_proofs.sh`, where every tamper needle in the repository lives, and
`specs/002-spec-aware-agent-runtime/tasks.md`, which carried the sibling's reconciliation of the very
figure that pass had been sent to correct. The cost was zero, because the pass happened to need
neither file. Had it needed either, it would have edited a file the brief had told it was free.

The mechanism is not the branch-scope one above. It is staler and simpler: **a held-file list is a
snapshot of another process's working tree, and it begins decaying the instant it is taken.** Carried
forward from an earlier brief or from memory, it becomes an assertion about the present with no
reading behind it. The error is asymmetric, which is what makes the short list the dangerous
direction — a list naming too many files costs a pass some unnecessary caution and nothing else,
while a list naming too few hands it a false all-clear on exactly the files nobody is watching.

**So the rule is the third read in the family: `git status` is the authority on what is held, and a
brief's list is a hint about where to look.** Reconcile the hint against your own reading before
touching anything, and report any file you found held that the brief did not name — that report is
what stops the same stale list being relayed a fourth time. Where the brief and the tree disagree,
the tree wins: it is not a summary of the state, it is the state.

The three entries end in the same instruction, and it is worth stating once as a family. **`git
status` before staging, `git log origin/main..HEAD` before pushing, and neither of them replaced by a
remembered summary.** All three failures came from acting on a description of the repository instead
of the repository; all three defences are a single read costing under a second; and none of the three
can be delegated, because in every case the tree is not in an erroneous state. It is in a state whose
meaning depends on who else is working in it, and that is not a property a checker can see.

### ~~The reference application is the one place a comment edit is a behavioural change~~ **A comment edit is a behavioural change in two file families, by two different mechanisms** *(uniqueness struck 2026-08-10)*

**On 2026-08-10 a pass corrected a stale `workload.sh` reference in a docstring inside
`tests/fixtures/reference-app/` and broke the gate.** Nothing about the correction was wrong, and the
guard that caught it was working exactly as designed — which is what makes this worth writing down
rather than filing as a false positive.

The reference application's **size is a committed artifact**. `size.json` is generated from the
fixture's own sources and pinned by `test_the_committed_size_is_what_the_measurement_produces`, so any
edit that moves a line count invalidates it. Both published figures are reachable from a comment:
`application_lines` counts every line, blanks and comments included, so a whole-line `#` comment moves
it; and `_code_lines` excludes only blanks and whole-line `#` comments, so a **docstring** line is
counted as code and a docstring edit moves *both* figures. The size is not incidental metadata — T203
requires it to be reported wherever SC-001 appears, which is why it is pinned at all: a stale figure is
a wrong denominator in somebody else's arithmetic.

There is nothing to fix in the gate. The rule is an expectation to drop: **in this fixture, ~~and nowhere
else in the tree,~~ "it's only a comment" is not a reason to expect the suite to stay green.** Either
make the edit net-zero in line count, or regenerate with
`python tests/fixtures/reference-app/seed.py` and bring the fixture README's stated size table back
into agreement — the table is separately pinned by `test_the_readme_states_the_size_that_was_measured`,
so a regeneration that stops at the JSON leaves the prose everybody quotes stale and the JSON nobody
opens correct, which is the failure mode rather than a lesser version of it.

**The "nowhere else" clause is struck as of 2026-08-10 — the hazard is real and the uniqueness was
not.** A second file family has the same property by a mechanism that shares no machinery with this
one: there a comment moves a *measured figure* that a committed artifact pins, here it breaks a
*byte-exact string match* in which no figure appears at all. It is the entry immediately below.

### A tamper needle that spans a line boundary makes a comment a breaking change, and 114 of them do

**On 2026-08-10 a comment inserted between two adjacent lines of `src/analysis/codegraph_pin.py` took
`check_tampers.py` from 0 errors to 1.** Nothing was wrong with the comment. The T004 removal proof's
tamper matches the literal string `'        ).fetchall()\n    finally:'` — the two lines that bracket
the digest's `WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%'` filter — and a needle that spans a
newline is only satisfied while those two lines stay adjacent. Put anything between them and the match
is gone:

```
ERROR    T004 — row counts fold into the schema digest, so a re-index reads as an upstream release
         NO_MATCH: no occurrence of '        ).fetchall()\n    finally:', with or without
         whitespace normalization; the source moved under this proof
```

**Established by planting, not by reasoning**, and reverted in the same pass. `tamper.py`'s second pass
is whitespace-tolerant, which is what makes this worth writing down rather than obvious: the tolerance
covers *reindentation*, so it is easy to assume it also covers an inserted line. It does not, and the
error message says so on its own — "with or without whitespace normalization" is the tolerant pass
reporting that it also failed.

**The scope is not one site.** Parsing the first argument of every `s.replace(` in
`tests/removal_proofs.sh`, **114** needles contain a `\n` — out of 336 recovered, against the 338
proofs `check_tampers.py` declares, the small gap being the parser's rather than a defect. Two
independent extractions agree at 114. So roughly a third of the removal-proof corpus is anchored to
line adjacency in some source file, and three proofs target `codegraph_pin.py` alone.

**Confirm the revert by presence, never by absence.** The needle back and matching once, the planted
string gone, `git diff` empty, and the error count returned to its starting value — which was read off
the tool at 338 proofs / 0 errors before the plant and again after the revert, not assumed. The
[emptiness-test inversion](#the-emptiness-test-inversion--git-diff-cannot-tell-unchanged-from-changed-back)
recorded above is exactly why: `git diff` prints nothing for a tree that was never touched and for one
that was destroyed and restored wrong, so absence distinguishes neither.

~~One residue, stated rather than fixed: **`check_corpus.py` does not walk `tools/`** — its include
list is `README.md`, `research`, `docs`, `specs`, `.cursor/skills`, `.specify/memory` — so this entry
is guarded by nothing.~~ **`check_corpus.py` walks `tools/` as of 2026-08-10, and this entry is
guarded by it.** `check_tampers.py` guards the underlying fact and would have caught the regression
on any gated commit; the *write-up* is what had no instrument, and the residue closed when the
instrument defects that made the widening look expensive were fixed rather than when anything about
this entry changed.

**The widening was measured on 2026-08-10, declined the same day, and installed the same day.** Two lists could carry `tools/` and they are
different knobs. `include`, filtered by `extensions`, is `.md` and `.markdown` only and decides which
documents are **walked and checked**. `search_roots`, filtered by `search_extensions` — which already
contains `.py`, `.sh`, `.yml` and `.json` — decides only where a figure may be **found** when a check
asks whether it occurs anywhere else, and it never parses what it reads: `search.build` loads each
file into a string and the only operations on it are `in` tests. So the corpus reads `.py` under
`specs/` today in the weakest possible sense, and **the sharper statement is that no check extracts a
figure or an identifier from Python anywhere, and neither list walks `tests/` or `tools/` at all.**
Against a baseline of 0 errors and 0 warnings, adding each root to each list:

| widening | errors | warnings | real defects | at 2026-08-10 post-fix | installed |
| --- | --- | --- | --- | --- | --- |
| `include` += `tools` | ~~5~~ **0** | ~~1~~ **0** | 0 | the five errors were the checker's; the one warning was this file's own worked example, and the example is reflowed | **yes** |
| `consumer` += `tools/*.md` | 0 | ~~6~~ **0** | 0 | five were figures mentioned without the code span the same paragraph already uses on the same values; one was a multiplier derived in this file and is restated as its two operands | **yes** |
| `search_roots` += `tools` | 0 | 0 | 0 | unchanged | no — it buys nothing |
| `include` += `tests` | 0 | ~~2~~ **0** | 0 | both warnings were the checker's | no — see below |
| `search_roots` += `tests` | 0 | 0 | 0 | unchanged | no — it buys nothing |

**The two installed rows are one knob and not two, and the order matters.** `load` walks the
`include` roots and assigns a role only to what it walked, so `consumer` += `tools/*.md` on its own
changes nothing at all; the consumer row above is measured with the `include` row already in place.
The reverse is what the residue turned on: `include` alone walks the catalogue for links, tables,
TOCs and register ranges and leaves **every figure in it unread**, because `numeric-provenance`
iterates `ROLE_CONSUMER` and `README.md` does not fnmatch `tools/README.md`.

**`tests` is measured free and is not installed.** `tools/fixtures/*` carries an `exclude` entry
because fixture documents are deliberately-broken artifacts and gating them is incoherent;
`tests/fixtures/*` carries none, so `include` += `tests` would put five fixture READMEs under the
gate on the wrong side of a distinction the corpus already draws. Adding the matching exclude is a
second decision, and nothing has asked for it.

**Seven of those eight firings were defects in the checker, and they are fixed rather than
tolerated** *(measured and corrected 2026-08-10)*. The paragraph below is left standing apart from
the one claim in it that is now measured, because what it got wrong is the evidence: it classified
all eight as false positives — correctly, in that no *corpus* artifact was at fault — and then read
that as a fact about the corpus, when five of them were a fact about `slugify` and two about
`link-label`. **A false positive is a defect somewhere.** Reading it as noise is what leaves it
standing, and reading it as a property of the file being walked is what makes it look like a reason
not to walk the file.

Neither `search_roots` widening moves anything, which is expected: widening the index can only add
places a figure is found, and finding one more occurrence downgrades an error to a warning rather
than creating either. **All eight `include` firings are false positives, by three mechanisms, two of
them self-reference.** The five errors are `link-anchor` and the links are right — `slugify` strips
`_` to remove markdown emphasis, so `` ## Generated claims — `gen_claims.py` `` slugs to
`generated-claims--genclaimspy`, while all five sites write the underscore-preserving spelling.
Planting both spellings in a one-file fixture, the checker rejects the underscore form and proposes
its own; ~~the claim that GitHub keeps the underscore rests on the documented algorithm and on five
independent authorings across two files, and was **not** verified against a renderer from here.~~
**It is verified against a renderer as of 2026-08-10 and the underscore is kept — see below.** The
one warning was `register-range` firing at line 375 on `OD-01 through OD-14`, this file's own worked
example of the sentence shape that rule exists to catch. **Its mechanism was the masking and not the
self-reference.** ~~That is why it turned out to cost nothing.~~ **Corrected 2026-08-11: it does not
cost nothing.** The price, and the further price the documented remedy exacts on top of it, is
[recorded once under nothing detects the split
itself](#nothing-detects-the-split-itself-and-the-corpus-is-safe-by-coincidence) and deliberately not
restated here. *(The refutation sat in that subsection while this sentence went on asserting the
opposite at its own site — the same shape this file corrected over `--reattest`, where the false
clause stood from `5029e1e` to `19aadbf` with its refutation far below it in the same entry.)*
The example already sat inside a backtick code span, which is the documented escape; the span opened
on one source line and closed on the next, and `build_masked` masks line by line, so
`_INLINE_CODE_RE` — which needs its opening and closing runs in one string — matched neither half and
the span was never recognised as a span at all. Reflowing it onto a single line masks it and clears
the warning, at no semantic cost. Nothing
about the containment tests in `figures.inside_spans` is involved; those govern struck spans, and a
partially-contained *code* span is not a containment failure but a span the masker cannot see.
The two `tests` warnings are
`link-label` on `tests/conformance/cassettes/README.md`, where both labels are correct: the check
compares the label against the **unresolved** target string, so a repo-relative label beside a
document-relative target reads as a mismatch.

#### The two `search_roots` rows are not free, and re-measuring them found the cost

**Both rows read `no — it buys nothing`, and that phrasing understates what was measured**
*(re-measured 2026-08-10, and both stay declined)*. A widening that buys nothing is a candidate
for installation the next time someone wants the coverage; a widening that costs something is
not. Three readings separate the two, and the third is the one the table did not carry.

**One check consults the index, and not several.** `search.build` is called once in
`tools/corpuscheck/runner.py` and the result is handed to every check as `ctx["search"]`, which
reads as a shared input. `numeric-provenance` is the only check that touches it. So
`search_roots` is not a noise floor across the check set; its entire blast radius is one rule's
choice of severity.

**That rule uses the index for severity alone**, which is why the zero-error, zero-warning
readings above are what the mechanism predicts rather than evidence the roots are inert. The
violation is appended either way: a non-empty `elsewhere` selects `warning` and the hint
`also in: …`, an empty one selects `error` and the hint `appears nowhere else in the corpus`.
Widening the index can never add a firing, and can only ever remove the `error` severity that
separates a transcription error from a propagated claim.

**The cost is that downgrade, and it lands on the checker's own negative controls.** A probe
document carrying `0.8965`, `0.7734`, `$41.03` and `1.76x` — four figures in no findings
document — reports **four errors** under the shipped roots and **four warnings** once `tests`
and `tools` are added, taking provenance from `tools/selftest.py`, `tools/corpuscheck/figures.py`
and `tests/batteries/test_seccomp_overhead.py`. `0.8965` is the sharpest of the four: it is a
planted digit-neighbour of the measured `0.8961`, written into `figures.py` to prove the lookup
is exact, and under the widening it answers *does this figure appear anywhere at all* with
`also in: tools/README.md, tools/corpuscheck/figures.py`. **The fixture that exists to catch a
transcription error would supply that error its provenance.**

**The surface is `62` figure keys, which is the number to weigh rather than the four in the
probe.** The shipped roots index `488` files carrying `410` distinct extractable figure keys;
`tests` and `tools` add `288` files and `62` keys, each one a value that stops reading as
absent. **`src` was measured alongside them and is declined on a weaker ground**: it adds `80`
files and a single key, so it neither helps nor costs, and a root that changes one key is not
worth the standing invitation to widen the other two beside it.

#### The underscore, settled against a renderer

**Both halves were measured on 2026-08-10 by fetching rendered HTML from GitHub's contents endpoint
and reading the `id` attribute the renderer emitted, for this repository's own files at `main`.**
Not from the documented algorithm, which is what the struck sentence above rested on.

- `` ## The advisory — `cite_advisor.py` `` emits
  `id="user-content-the-advisory--cite_advisorpy"`, and the page's own self-link is
  `href="#the-advisory--cite_advisorpy"`. **The underscore survives.**
- `### OD-26 — … terminated.denied_operation …` emits `…terminateddenied_operation…`. The `.` is
  dropped and the `_` is kept **in one token**, which is the sharpest available demonstration that
  `_` is not in the set of characters the slugger discards.
- `#### _Note_: Multiple entry points`, in a public repository carrying that heading, emits
  `id="user-content-note-multiple-entry-points"`. **Emphasis underscores are gone.**

So the defect is a **conflation of a character's markup role with its literal role**: an
unconditional `replace` standing in for a parse. GitHub renders the heading to HTML first, so
`_emphasis_` is consumed as markup and never reaches the slugger, and then slugs the text content,
where a literal `_` inside an identifier survives because `_` is a word character. **`*` and `~`
need no such distinction and that is why only `_` was wrong**: consumed as markup they vanish, and
left literal they are dropped anyway for not being word characters, so both roles have one outcome.
`_` is the only character where the two roles disagree — and it disagrees in the direction that
invents an anchor no rendered page carries.

`slugify` now parks inline code before the emphasis pass and removes only non-intraword `_` pairs.
Measured against the renderer over ~~the whole corpus as walked on 2026-08-10~~ **the non-blockquoted
headings of the corpus as walked on 2026-08-10, which is a scope this sentence did not state and
which is corrected below**: **29 of 2,371 headings
disagreed before, 4 after, and 26 slugs moved** — every one of them restoring a literal underscore.
Adding `tools/` to `include` later that day put a further 53 headings into the walked set. ~~and they
have not been put through the renderer.~~ **They have been, on 2026-08-10 at `1b52eb9`: all 53 were
fetched from the renderer and all 53 agree.** The count above is left at the set it was taken over
rather than restated over a set it was not, and no current total is given in its place: the walked set
also grows whenever the corpus does, so a "now" figure would be a baseline plus a delta and would rot
on the next commit. The stable statements are the dated measurement, the 53, and their agreement.
Neither family below is reachable in those 53: the only
non-ASCII character in any of their headings is an em dash, which both sides drop, and none of them
ends in punctuation preceded by a space — **an argument from inspection that the differential has now
confirmed rather than replaced, which is the order that matters, since inspection can only bound the
families it already knows about.** The four survivors were two further families, ~~neither
reachable from any live link and both recorded here rather than fixed, because each is a different
defect from the one that was briefed~~ **both repaired 2026-08-10 at `7a60dd3`, and the repair is
below**:

| site | divergence | cause |
| --- | --- | --- |
| `plan.md:3487`, `plan.md:3719`, `findings/028:50`, `findings/028:78` | `①`, `②` and `③` are kept | Python's `\w` matches Unicode category `No`; GitHub's word class does not |
| `research/12-examples-as-corpus.md:103` | a trailing `-` is missing | GitHub drops punctuation and *then* converts the remaining space, keeping a trailing hyphen; this implementation strips first |

**The circled-digit row lists four sites and was written listing three, and the fourth arrived
between the differential and the sentence describing it.** `plan.md:3719` is OD-30's heading, which
gained a `③` at `0236005` the same afternoon. Nothing was mis-transcribed: the run was correct when
it ran, the corpus moved under it within hours, and a count of divergences is a live quantity
however carefully the set it was taken over is named. The dated-set discipline that protects the
denominator does not protect the numerator, and that is the reason the repair below is worth more
than a more careful count would have been.

**Closing the 53 turned up a third population that no differential had ever covered, and it is larger
than both families above put together: headings inside blockquotes.** `crossrefs._anchors_for` matches
`^(#{1,6})\s+`, anchored at the start of the line, so a heading written `> ## Title` never enters the
anchor set the checker builds — and it never entered the set either differential walked, which is why
a run that reproduces the four survivors exactly can still be blind to it. GitHub renders such a
heading as a real heading and emits an `id` for it. Re-run at `7a60dd3` with blockquote prefixes
stripped, the corpus divides in two: the **2,425** headings the checker enumerates, of which **5**
disagree — the two families above, at the four `①`/`②`/`③` sites and the one `★` site — and
the **109** it does not, of which **40** disagree. The first number is the dated set above plus the 53
and one heading the corpus gained in between, so the two runs agree everywhere they overlap, and that
agreement is what licenses reading the 40 as new rather than as a contradiction. **This paragraph
read 107 and 39 when it was written at `1b52eb9`, and both were correct there.** Commit `0236005`
added the two-line banner at `plan.md:3838`–`:3839` a few hours later; one of those lines opens with
`⚠️`, which is what moves 107 to 109 and 39 to 40, and the same commit's `③` in OD-30's heading is
what moved 4 to 5. Three of the five figures in this section were live quantities and none of them
survived the afternoon.

**A claim has been circulating that GitHub emits no anchor for `plan.md:3838`–`:3839`. It emits one
for both**, and the differential aligns 1:1 with the renderer across all 136 documents, which is how
that is known rather than assumed. The pair is a single heading the author wrapped across two source
lines, each line carrying its own `####`, so the renderer sees two headings and anchors them
separately — the second anchor being the tail of a sentence, `#overlap-on-the-same-line-as-the-figure-it-qualifies`.
`plan.md:3810`–`:3811` is a second instance of the same wrap and has the same shape. Neither is a
defect in the checker; both are headings that read as one and anchor as two.

**The 40 are a single family.** Every one is a heading whose
text opens with a pictograph — `⚠️` at 30 sites, `✅` at 8, `⛔` at 2 — and in every one the renderer
emits a leading `-` where this implementation emitted none, preceded at the 30 `⚠️` sites by a literal
U+FE0F that the renderer keeps and this implementation dropped. Seven of the 40 carry a circled digit as
well and so are compounds of this family with the first one above.

### A filtered population presented as a total, for the third time this week — and the neighbours inherit the filter

**"2,371 headings compared" was a count over the non-blockquoted headings only, and nothing at any
of its four sites said so.** The figure was never wrong about its own set. What it omitted was which
set, and the omission is what let two differentials run, a docstring be rewritten, and a catalogue
row be corrected, all without anyone noticing that 109 headings had never been looked at. **An
unstated scope does not read as a scope. It reads as a total**, and a reader who wants to know
whether a population is covered has no way to ask the figure.

This is the third instance of one defect in a week, and the two before it were repaired the same
way — by naming the population at the site rather than by changing the figure:

| instance | the figure | the population it was actually over |
| --- | --- | --- |
| `12 tables` | `research/06` §1, `research/12` §6.5, `research/14` §2.2, `tasks.md` | what `schema_digest()`'s `sql IS NOT NULL AND name NOT LIKE 'sqlite_%'` leaves; `sqlite_master` holds 13 |
| `five gaps` | `research/14` §2.12 | the five this synthesis carries, selected from the eleven `06` §8 names |
| `2,371 headings` | `slugify`'s docstring, this file's `link-anchor` row, the differential write-up, the oracle lesson | the non-blockquoted headings; the population it excluded held 107 then and 109 at `7a60dd3` |

**The neighbouring figures inherited the filter, which is the part worth carrying forward, because
it is what makes this a pattern rather than three coincidences.** The two prior instances had it and
so does this one. Beside the 2,371 stood "29 disagreed before, 4 after, and 26 slugs moved", and all
three were scoped the same way without saying so. Re-running the pre-fix implementation at
`7a60dd3` over both populations, **three blockquoted headings diverge for exactly the underscore
reason the 29 counted** — `plan.md:3810` and two in `findings/023` — so the before-count was low by
at least three and the moved-count by the same three. "4 after" was the worst of them: the honest
figure over both populations was 43.

**One neighbour did not inherit it, and it is worth saying which and why.** The 53 headings `tools/`
added are scope-invariant: all 53 are non-blockquoted, so the figure is the same under either
population and the differential that closed them was complete despite being scoped. That is luck
rather than method — nothing about how the 53 was taken would have revealed a blockquoted heading
if one had been there. **A figure that happens to be scope-invariant and a figure that states its
scope are not the same artifact**, and only the second survives the corpus growing.

### Both halves were declined on a blast radius nobody had counted, and counting it reversed both

**The `★` precedent did not transfer, because it is not a precedent — it is the same fix.** The
leading-hyphen defect at the 40 pictograph sites and the trailing-hyphen defect at the one `★` site
are one defect: `slugify` trimmed *after* dropping characters outside the word class, where the
renderer trims *before*. Any dropped character sitting at either end behind a space loses its hyphen.
So the question was never whether a leading-pictograph rule is more additive than a trailing-`★`
rule; there is one rule, and it was declined once on the reasoning that reordering trim against
convert "reorders it for **every** heading, which is a whole-corpus blast radius for one site".

**That sentence conflated the computation changing with the output changing, and only the second is a
blast radius.** Measured over the 2,425 already-enumerated headings, the three repairs move:

| repair | slugs moved in the enumerated population | of which were wrong before |
| --- | --- | --- |
| trim before the character drop, not after | 1 | 1 |
| drop Unicode category `No` | 4 | 4 |
| keep combining marks, so U+FE0F survives | 0 | 0 |
| **all three together** | **5** | **5** |

Every slug that moved was one of the five that disagreed with the renderer, and no live link pointed
at any of them. After the repair, **0 of 2,425 and 0 of 109 disagree** — 2,534 headings, no
divergence. The compounds needed no separate statement in the end: the circled-digit repair was
measured in the same pass and is as cheap, so the seven are fixed rather than left as a residue.

### Widening the enumeration was measured per check, and only one check could not take it

**The argument that widening is monotone is specific to `link-anchor` and was not assumed for the
others.** `link-anchor` tests a fragment for membership in an anchor *set*, so a larger set can only
resolve more links — but that holds only if the old set is a subset of the new one, and
`_anchors_for` also assigns `-1`/`-2` duplicate suffixes, which a new heading can renumber. It is a
subset: the suffixed set for a base slug is determined by how many headings carry it, so adding one
extends `{s, s-1, … s-(k-1)}` to `{s, … s-k}` and removes nothing. Measured over the corpus,
**0 documents lose an anchor and 109 are added**. That is the invariant, not just today's count.

The other checks were measured rather than argued. Each enumerator was widened alone:

| check | baseline | widen `crossrefs` | widen `toc` | widen `identifiers` | installed |
| --- | --- | --- | --- | --- | --- |
| `link-anchor` | 0 | 0 | 0 | 0 | **yes** |
| `link-target` | 0 | 0 | 0 | 0 | n/a — reads no heading |
| `link-label` | 0 | 0 | 0 | 0 | n/a — reads no heading |
| `toc-coverage` | 0 | 0 | **3** | 0 | **no** |
| `identifier-resolution` | 0 | 0 | 0 | 0 | no — see below |
| `identifier-gap` | 0 | 0 | 0 | 0 | no — see below |
| `definition-count` | 0 | 0 | 0 | 0 | no — see below |
| the remaining ten checks | 0 | 0 | 0 | 0 | n/a — read no heading |

**`link-label` reads no heading enumeration at all**, which is worth stating because it is easy to
assume otherwise from the fact that it resolves its target before comparing: what it resolves is a
*path*, with `posixpath`, and it never consults an anchor set.

**`toc-coverage` is the check that blocked a full widening, and its three firings are all correct
refusals.** They are banner boxes — `> ## ✅ PHASE 0 RAN…` in `research/11`, and two `> ## ⚠️` flags in
`research/14`. A banner is not a section, nobody navigates to it, and requiring it in a table of
contents would make the findings convention itself the violation. The two enumerators answer
different questions: `_anchors_for` asks *what can be linked to*, which the renderer decides, and
`toc` asks *what a reader must be able to reach from the top*, which this corpus's conventions
decide. They are correctly not the same set, and that is now recorded at the `toc` site.

**Widening the identifier enumerator is free and buys nothing, so it is not installed.** It fires
zero either way, and it adds **no** definition the corpus did not already have — 247 identifiers
defined before and 247 after. Installing it would only widen what counts as *defining* an
identifier, so a blockquoted annotation that merely mentions `OD-29` would begin to define it, which
can only ever silence a dangling-reference error. A loosening that fixes nothing is a loosening.

**The reason to widen `link-anchor` was never the count, which is zero, but the class.** No link
points into those 109 today, so nothing is broken. The hazard is the first author who writes one:
they would get a `link-anchor` error against a target that exists on the rendered page, and the
remedy they would reach for is to change the correct artifact — the failure this file records as
[more dangerous than a gap](#a-checker-false-positive-is-more-dangerous-than-a-checker-gap-the-remedy-corrupts-the-correct-artifact-and-then-it-passes).
The population is also not static: `specs/001-discovery-validation/plan.md` carries 28 blockquoted
headings and `findings/026` carries 18, and the banner-box convention adds more with every finding.

**The `link-label` half is fixed too, and the false-negative question was answered before the fix
went in rather than after.** The check now resolves the target with `posixpath` — not
`Path.resolve`, so the verdict does not depend on the filesystem, since the target may not exist,
which is `link-target`'s finding and not this one's, and it may be a symlink, whose real path is not
what the label is claiming. The filename branch **had no firing site in either fixture**: every
planted filename label agreed with its target, so the branch was held only in the direction that
passes and could have been deleted outright with the self-test still green. A firing site was added
to `known-bad` and shown to fire on the *unfixed* code first, so the control is known to have teeth;
the false-positive shape was added to `known-good` and shown to fire there too, which is what made
the fix checkable. After the fix the `known-bad` control still fires and `known-good` is silent.
Swept over the walked corpus, and again with `tests/` and `tools/` added, the change removes
**exactly the two firings** whose labels were verified correct and **adds none** — which is the
false-negative argument, since a resolve-before-compare can only ever remove firings.

**Adding `tools/` to `include` buys no figure coverage on its own, and the two knobs are what the
residue turned on.** `numeric-provenance` iterates `ROLE_CONSUMER` alone, and `tools/README.md`
matches no `consumer` glob — `README.md` does not fnmatch `tools/README.md` — so under the `include`
widening alone this file is classified `ROLE_OTHER`. A false four-decimal ratio and a false
cent-precise spend planted here under that widening produce **zero** firings. Both knobs are now
installed: `include` carries `tools`, `consumer` carries `tools/*.md`, and the same two plants
produce **two errors** under the installed configuration. The plant was re-run rather than inherited,
and the file was restored by rewriting the original bytes and re-reading them, not by observing an
empty diff.

**The widening was declined on measurement and is installed on measurement** *(installed 2026-08-10,
reversing a decline recorded the same morning)*. The decline rested on an arithmetic ground and a
structural one, and both moved.

**The arithmetic ground was seven warnings by two mechanisms, and every one of them was an instrument
reading or a marking this file was already using a few lines away.** `register-range` at the worked
example was the masker failing to see a code span wrapped across two source lines, and reflowing it
onto one line clears it. Five of the six `numeric-provenance` warnings were external multipliers
*mentioned* in the [false-positive register](#known-false-positive-modes) as a census of warning
values, written bare on three lines where the next sentence of the same paragraph writes the same
values in backticks; the code span is this file's own marking for a mentioned token, and applying it
consistently clears them. The sixth was a multiplier this file derived in the open from two bounds,
which is the class `numeric-provenance` records as a real defect rather than a false positive, and it
is restated as its two operands on the precedent that struck four `3.7×` claims and put
`220 against 60` in their place.

**The structural ground was the stronger of the two, and it is the one that turned out to be
answerable.** `tools/README.md` is the document that documents the checker, so it necessarily
contains a worked example of every pattern the checker fires on, and walking it with the checker is
self-referential. That is true, and it is not the same as unfixable. A worked example has to be *read
as an example*, this corpus already has a marking that says so, and every self-referential firing
here was an example that carried no marking or carried one the masker could not see. The distinction
the residue closed on is between *the file is full of examples* and *the examples are unmarked*, and
only the second is a property of the file rather than of its punctuation.

**What the count was doing was making a structural argument look like an arithmetic one.** That
diagnosis was right and it cut the other way in the end: the arithmetic moved when the arithmetic was
shown to be the instrument's, and the structural ground moved with it, because seven false positives
inside the checker had been standing in for a property of the corpus. The two coordination entries
above are covered by the installed gate along with this one.

### A checker false positive is more dangerous than a checker gap: the remedy corrupts the correct artifact, and then it passes

**A gap is silence. Silence leaves the artifact alone.** A false positive names a correct artifact
as broken, and the remedy a reader reaches for is to change the artifact until the instrument stops
complaining. Afterwards the gate is green, so nothing distinguishes the corrupted corpus from a
healthy one, and the instrument that caused the damage is the same one certifying it. **The
corruption is self-confirming, which is what puts it above a gap rather than beside it.**

**This is not a hypothetical here. It has already happened, in the walked corpus, and the gate was
green over it.** `specs/002-spec-aware-agent-runtime/findings/027-lifecycle-edge-set-divergence.md`
carried two links to OD-26 spelling the fragment `…terminateddeniedoperation…` — the underscore
removed, which is `slugify`'s spelling and not GitHub's. **Both links are broken on GitHub** and both
passed `link-anchor` at 0 errors, because the checker computed the target's anchor with the same
defect the links were written with. Fixing `slugify` turned the gate red and named them; they are
corrected at the renderer's actual `id`. Five other links across two files spell the same shape
*correctly* and were the ones the checker rejected. So one defect produced both populations at once:
five correct artifacts reported as errors, and two corrupted artifacts reported as fine.

**The sentence at the top of this file is what licensed it.** ~~"Slugs follow GitHub's algorithm
including its `-1`/`-2` duplicate suffixes"~~ is exactly what a future pass consults when deciding
whether an anchor error is real, and half of it was never measured. A reader who trusts it, sees
`link-anchor` fire on a hand-written fragment, and edits the fragment to match the checker's proposal
has done the wrong thing while every gate agreed. The checker even offers the edit: `link-anchor`'s
hint is `did you mean: #…`, so the wrong spelling arrives pre-written.

Three things follow, and the third is the one that generalises past anchors:

- **A firing you classify as a false positive is a defect report about the instrument.** Recording
  the count and moving on is a decision to keep the defect. Seven of the eight firings that this
  file used as evidence for declining a widening were the checker's own, and were carried as noise
  for a day because "no corpus artifact is at fault" was read as "nothing is at fault".
- **A documentation claim about an instrument's algorithm is load-bearing and needs a measurement,
  not a citation.** The struck sentence was not wrong about the suffixes; it was unmeasured about
  the slug, and an unmeasured half inside a true-sounding whole is worse than an absent claim,
  because it answers the question a reader came with. **A third instance landed the same day, and it
  is a degree worse than unmeasured: it is contradicted by the code it describes.** The multiplier
  entry under [Known false-positive modes](#known-false-positive-modes) told a reader that "one
  citation covers every claim within four lines of it"; `numeric-provenance` reads the figure's own
  line and nothing else. Unmeasured and false are the same defect at two severities and the remedy is
  the same for both — a measurement against the instrument, never a better-sourced sentence — so the
  instance belongs to this bullet rather than to a bullet of its own. **What it adds is where such a
  sentence comes from.** That mechanism was not misremembered; it was invented, to reconcile two
  figures taken over different scopes — lines edited in one directory against warnings counted over
  the corpus — so that the smaller number would explain the larger. **A stated mechanism whose only
  work is to make two numbers agree is the shape to distrust**, and the test is cheap: re-measure both
  figures over one scope. Doing that here dissolved the sentence, because the eight edits reach seven
  of the thirty-two and the commit closed the rest elsewhere.
- **Prefer the instrument's ground truth to the instrument's specification.** The underscore question
  was settled by fetching a rendered page and reading the `id` GitHub emitted, after a previous pass
  had reasoned from the documented algorithm plus five independent authorings and correctly refused
  to act on it. Where an oracle exists — a renderer, a compiler, a kernel — a differential against
  it is cheap and it is not an argument. The differential run here compared 2,371 real headings —
  **the non-blockquoted ones, a scope the run did not state, and the unstated half is where a third
  population of 109 headings sat through two differentials** — and found a second divergence family
  nobody had asked about. Re-run over both populations it compares 2,534.

**Its relation to the [emptiness-test inversion](#the-emptiness-test-inversion--git-diff-cannot-tell-unchanged-from-changed-back) is complementary and not duplicate**, which is why it is
its own entry: that one is a reader misreading an *absence* of signal, and the remedy is to verify by
presence. This one is a reader acting on a *present but wrong* signal, and no amount of verifying by
presence catches it, because the wrong thing is what the instrument asserts.

**The four-line-window instance is recorded inside this entry rather than beside it, and the same test
is what decides that.** A wrong *signal* and a wrong *explanation of the signal* look like two
subjects, and the argument for separating them is real: the second is what lets the first survive
review. But the test this entry applies is not what the defect is about, it is **what error the reader
makes and what remedy corrects it** — and on both counts the two are one. The reader acts on something
the instrument asserts, and the correction is a measurement against the instrument. The distinction is
also already doing work *within* this entry: the struck sentence at the top of the file is what
licensed the two broken links named above, so the explanation and the signal are the two halves of a
single case here rather than two cases. Splitting them would put the licensing claim in one entry and
the instance that demonstrates it in another, which is the duplication the paragraph above declines
for the opposite reason.

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

**The comment committed at `acdf5f7` stated this one step too strongly** — it said the `if: always()`
steps "do not run". Per the reference above they do. The bound it justifies was unaffected, because
what those steps need does not exist by the time they run. **Corrected in
`.github/workflows/ci.yml` at both sites, 2026-08-06**, and that file now states the mechanism the
short way and points here. `acdf5f7`'s own commit message still carries the stronger claim and
cannot be corrected in place; this paragraph is the record that it is wrong.

So the bound is a **sum, not a multiple**, and the arithmetic is the part a future editor would
otherwise re-derive or casually tighten: the observed maximum from the 40-run table in that file's
own header, plus 300s for one arm reaching the cap in the harness, plus 300s for the same arm
reaching it again in `proof_attribution.py`. At `acdf5f7` that read 318 + 300 + 300 = 918s, 15.3
minutes, rounded up to 20, leaving 882s of hang budget — two full cap firings and change. Three
simultaneously hanging arms exceed it, and that is the deliberate stopping point: at three the cap is
not containing the problem, so losing the record is no longer the worse outcome.

**The table was re-derived whole on 2026-08-08 and the sum now reads 540 + 300 + 300 = 1140s, 19
minutes. The bound stays at 20 and nothing moves.** 1140 is inside 1200, so the method returns a
floor below the value already set; nothing has fired, and widening a bound that has not fired spends
the only thing it is for. What did change is the margin: 660s of hang budget rather than 882s, 2.2
cap firings rather than 2.9. The window excluded from that sample, and the rule that excluded it, are
stated in `ci.yml`'s header — 11 runs whose footprint intersects GitHub's 2026-08-06/07 Actions
incident, by a rule that never looks at a duration.

**The `+12s` guess recorded here at `acdf5f7` is now a measurement, and it was low.** Each run's
`removal-proofs.latest.json` carries `totals.entries_recorded`; regressed against job duration over 49
successful runs spanning 64–202 arms, the cost is **1.68s per arm** (R² 0.80). But that slope is not
constant across the range — restricted to runs above 129 arms it is **~3.0s per arm**, and above 147
arms 3.85 — because each arm re-runs a selection out of a suite that is itself growing. Quoting the
average alone would understate the next arm, so the local figure is the one to plan with.

**That converts the instruction this paragraph used to carry into a threshold.** The sum reaches
1200s when a run reaches 600s, which from 540s at 202 arms and ~3.0s per arm is **≈222 arms** — about
20 away, in a repository whose arm count went 64 → 202 in four days. So the trigger is no longer "if a
later sample shows the trend continuing", which had no number in it and depended on someone noticing a
slow run: **when `totals.entries_recorded` reaches 222, this bound stops being derivable and the table
must be re-derived.** The handling of the figures themselves still follows
[`gen_claims.py`](#generated-claims--gen_claimspy)'s rule for a number with a narrative half — the
sentences around them were advanced with the digits, because advancing the digits alone turns
detectable staleness into undetectable inconsistency.

**The rule generalises past CI: when an inner mechanism's whole output is a record it writes at the
end, an outer bound set inside the window the inner one needs converts an informative failure into a
silent one.** They move together — raising `REMOVAL_PROOF_TIMEOUT` without raising the job bound
trades the cap's diagnostic for a cancelled job. And the corollary for the other jobs is worth one
sentence, because it is the honest half of the same pass: their 5 minutes is a **floor**, stated as
one rather than dressed up as a derivation, since the jobs it covers finish in under a minute every
time and a value scaled off that work would be measuring PyPI rather than the job. It still fires on
a hang, and it is far tighter than GitHub's default: 5 minutes against 360.

### The instrument a branch census is scored against is part of its result, and this file uses `library` in two senses

**A branch census reports a rate against an instrument, and the rate without the
instrument beside it is unresolvable.** The case that established it:
[finding 038](../specs/002-spec-aware-agent-runtime/findings/038-corpus-check-branch-population-and-the-instrument-declined.md)
scored every branch in the corpus checker against `tools/selftest.py` alone and
found `tools/corpuscheck/figures.py` its worst module at **10 of 20 (50.0%)**
unheld. Re-scored against the whole gate set, four of those ten are held by
`check_corpus.py`, which is **6 of 20 (30.0%)** — the same twenty branches, the
same module byte-for-byte, and two rates neither of which is wrong. They answer
different questions: *what would `selftest` notice*, and *what would the gate set
notice*. Both readings are dated at `aaa329b`, and both had moved again by
`92143b9`.

**So a census figure carries three things or it is not quotable: the population,
the instrument, and the tree.** The denominator was already understood — finding
038 states its own rate twice because a reader cannot tell whether unscorable
branches sit in the denominator. The instrument is the same defect one level up,
and it is worse in one respect: a wrong denominator makes a rate ambiguous, while
a missing instrument makes a rate *look* like a property of the code when it is a
property of what happened to be watching. **The remedy is the cheap one.** Name
the instrument in the sentence, and name the tree, because both move.

**The correction that belongs beside this, because the inference is inviting and
wrong: `tools/corpuscheck/figures.py` is a library in the ordinary sense and is
not one of the two
files `tools/instruments.py --check` classifies as `library`.** Those two are the
tamper matcher and the per-arm wall-clock cap — `tools/tamper.py` and
`tools/proof_timeout.py` — and `library` there is a classification of *entry
points*, meaning a file that is never invoked as a program and therefore has no
exit code to gate on. `figures.py` is not in that census at all. The census's
candidate set is built from `tools/*.py`, and `tools/corpuscheck/` is excluded
from it as a package rather than a program, so no file under it is a candidate
for any of the three classifications. **Reading the census's `2 library` as
"the two libraries in `tools/`" is the error**, and it is the shape this file
already records under [never stating a classifier as a
complement](#never-state-a-classifier-as-a-complement--enumerate-the-accepting-set):
`library` is the accepting set for one question and says nothing about the
ordinary English word.

### Two neutralisation forms turn "unscorable" into a verdict, because hanging and raising are properties of the form

**A branch census that files hangs and raises as `unscorable` under-reports
coverage, and one of the two needs no new form at all.** The census's own
definitions are what settle it: *held* means the neutralised tree makes the
instrument exit non-zero, and *unscorable* means no form produced a runnable
tree because all of them either raised or hung. **A raise is a non-zero exit.**
An inverted guard that dereferences a `None` takes the instrument to a failing
exit by the census's own definition of held, so filing it as having no verdict
records an absence where there was a verdict, and it records it in the direction
that reports the branch as unmeasured rather than as protected. Hanging is the
form that genuinely produces nothing, and it is worth keeping the two apart for
exactly that reason.

**The second form is for a `while` whose test carries its own termination bound,
and preserving the bound is necessary and not sufficient.** Measured 2026-08-11
against `corpus.py:161`, the inner backtick-run scanner, whose test is a
conjunction of a bound and a character comparison. Six variants were run: the
whole test inverted, forced true and forced false, and the same three applied to
the non-bound conjunct with the bound kept as the left operand. **Exactly one
terminates** — the bound preserved and the non-bound conjunct forced *true*. All
three whole-test forms hang, and so do the two per-conjunct forms that stop the
loop advancing. Under the form that terminates, `tools/selftest.py` and
`check_corpus.py` both exit non-zero, so the branch is held and was never
unscorable in substance.

**The mechanism is the part that transfers, and it is not where it looks like it
is: none of the hanging forms hangs in the loop whose test was neutralised.**
That loop terminates in every form; in the forms that hang it simply never runs.
What spins is the **enclosing** loop, whose index advances only by the inner
loop's result, so a neutralisation that leaves the inner loop making no progress
stalls the outer one. Preserving a termination bound keeps the neutralised loop
bounded and says nothing about whether the loop still advances anything its
caller depends on.

**Which is the general statement: hanging and raising are properties of the
neutralisation form and of the control flow around the branch, not of the
branch.** A verdict filed against a branch on the strength of a form that hung is
a verdict about the form. The remedy is to widen the form set before widening the
verdict set — the third value is for branches no form reaches, and a third value
reached by trying three forms is mostly a statement about the three.

### A superset is not a hold, and one branch is inert rather than unheld

**A membership assertion is satisfied by a superset, so a neutralisation that
widens the result holds nothing while appearing to be checked.** Measured over
`figures.digit_neighbours`, which returns the digit strings one substitution or
transposition away from a value so a hint can name the near neighbour of a
mistyped figure. The check that reads it asserts that an expected neighbour is
**in** the returned set. Two of the function's guards are skips whose forcing
widens what comes back: the substitution guard, forced never to skip, substitutes
digits into non-digit positions, and the transposition guard, forced always to
fire, transposes pairs it was written to exclude. The expected neighbour is still
in the wider set, the assertion passes, and the guard that was supposed to be
under test is gone.

**The direction is what matters and it is asymmetric.** Inverting those same two
guards *narrows* the result — the expected neighbour drops out and the assertion
fails — which is why the census prefers inversion, and it is the whole of the
difference between a form that holds a membership assertion and a form that
cannot. **A widening neutralisation against a membership assertion is a hold that
is not one**, and nothing about the passing run says so.

**One branch is inert rather than unheld, and the two are not the same verdict.**
The substitution loop's `d == ch` guard skips the substitution that would rewrite
a character as itself. Forced never to skip, the only string it adds is the
original value — and `out.discard(value)` on the way out removes exactly that, so
the returned set is **byte-identical** to the pristine one. No instrument can
hold it, because there is no output for an instrument to read differently: the
branch is a small efficiency and the code is correct with it removed. That is the
memoisation pole finding 038 §3 names, arriving in a second module by a second
mechanism, and the test that separates it from an unheld branch is the same one —
whether any input exists for which the two paths disagree about the output.

**The nuance that keeps this from being over-applied, since it decides what a
fixture is worth: whether the two widening guards widen at all depends on the
value.** On a figure with no non-digit character in it, both are inert too — the
substitution guard never skips anything, and the transposition guard excludes
nothing a digit pair would have supplied. Widening needs a value carrying a
decimal point or a thousands separator. So a fixture built entirely on integers
scores those guards inert and a fixture carrying a decimal scores them widened,
and neither fixture holds them. **A verdict over a function of its input is a
verdict over the inputs the fixture supplies**, which is a sharper statement of
the same asymmetry finding 038 §7 makes about held.

## Roles: who is authoritative

`config.json` sorts every file into one of four roles, and the roles decide which
checks see which files.

| Role | Glob | Meaning |
|---|---|---|
| `authority` | `specs/*/findings/*.md` | The source of record for measured numbers. Nothing checks these for provenance; they *are* the provenance. |
| `consumer` | `README.md`, `research/*.md`, `specs/*/plan.md`, `spec.md`, `VERDICT.md`, `checklists/*.md`, `tools/*.md`, `.cursor/skills/*/SKILL.md`, `docs/*.md` | Documents that quote findings. `numeric-provenance` runs here. `tools/*.md` is spelled out because `README.md` does not fnmatch `tools/README.md`. |
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
- *A register the corpus was narrowed away from.* The largest false positive
  this tool has produced: **304 `identifier-resolution` errors** from `--path
  specs/002-spec-aware-agent-runtime/tasks.md` at `2979c31`, every one naming an
  `FR` identifier that resolves in a full run. A heading naming three
  identifiers in prose was read as three definitions, which is exactly
  `min_definitions`, so the namespace stayed enforced against a three-member
  phantom register. Heading definitions are lead-anchored now, and the decision
  to enforce a namespace is taken against the unnarrowed tree rather than
  against whatever `--path` left behind. The reasoning, the second mechanism the
  first fix exposed, and the planted controls are under
  [**Narrowing and the definition index**](#narrowing-and-the-definition-index).

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
  zero** — the fix named at the end of this entry was applied, in commit `1f5450b`.
  ~~as eight inline citations across five `.cursor/skills/*/SKILL.md` files; one
  citation covers every claim within four lines of it, which is why eight edits
  closed thirty-two warnings.~~ **Struck 2026-08-10. There is no four-line window
  in this check and there never was one:** `run` reads
  `externally_attributed(doc.lines[i - 1])` — the line the figure sits on, and
  nothing else — and exempts the figures on that line alone. A reader who trusted
  the struck sentence and put a citation three lines away would get a warning the
  documentation had promised them away. **The sentence existed to reconcile two
  figures taken over different scopes**: `8` counts the lines `1f5450b` changed in
  the five skill files, `32` counts warnings over the whole corpus, and the window
  was invented to make the second follow from the first. **Re-measured this pass by
  running the current check against three worktrees, one implementation over all
  three:** `32` warnings outside `tools/README.md` at `cee7ff8`, the same `32` at
  `d1f7d7a`, and none at `1f5450b`. The intervening commit closed nothing, so the
  clearing is `1f5450b`'s and the attribution survives; what does not survive is the
  account of how. The `32` sat across **fourteen** documents. The five
  `.cursor/skills/*/SKILL.md` files carried **seven** of them, which is what eight
  edited lines in that directory can reach; the other **twenty-five** sat in eight
  `research/*.md` documents and in `specs/001-discovery-validation/plan.md`, all of
  which the same commit also edited. **Thirty** of the thirty-two closed by a
  citation arriving on the figure's own line; the remaining **two** closed by the
  figure being struck rather than sourced — both `100×` claims, retracted in the
  house style, which `figures.struck_spans` skips. The entry is kept because the
  *mechanism* is what matters and it is unchanged: the rule still fires the moment a
  citation is dropped. Typing the multiplier lookup surfaced them;
  it did not create them. All 32 were external figures — Anthropic's `~15×` token
  multiplier for multi-agent systems (23 sites), a permissive-mode `200×` approval
  figure (2), a `5–100×` search-loop cost range (5), a `10–25×` model-family price
  range (2) — and none is a measurement this corpus took. Under the untyped rule
  they read as sourced because their digits occurred *somewhere* in a finding, and
  the occurrences are worth naming: `15×` was satisfied by "LiteLLM 1.95.0
  publishes **15** wheels", by the decision label **OD-15**, and by the table cell
  `| R2 | 15 |`; `200×` by the HTTP status code **200** in the credential-probe
  table; `25×` by "extraction version **25**" and by `25,633` tokens. That is the
  `$3.7687` defect in a wider form — a status code sourcing a cost multiplier —
  and these warnings are it being caught. Six sibling claims at the same values
  *are* exempt, because they carry the inline link the house style requires; these
  32 carried none~~, and no citation sat within four lines of any of them~~.
  **Struck 2026-08-10 with the sentence above, and struck for a second reason.** The
  clause reads as a statement about the observed data rather than about the
  mechanism, and it would have been worth keeping on that ground — but measured over
  the pre-fix tree it is false as data too: **five** of the 32 did have a citation
  within four lines, one in `.cursor/skills/multi-agent-topology-review/SKILL.md`,
  three in `research/01-agent-anatomy.md` and one in `research/README.md`.
  **The surviving clause is the exactly true one**: none of the 32 carried a citation
  on its own line, which is the only distance this check measures. The fix
  was a citation on each line, which belonged to the documents and not to this tool,
  and that is what was done.
  Do not add these values to `numeric_allow`: it is keyed on the digit string, so
  allowing `15×` would also exempt a future genuine `15×` measurement.

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

**The first of the three is the weakest, and a later measurement says so.** A
purge races the write it is trying to pre-empt, so the two below it are what
make this battery sound. The mutation-sweep form of the same fault, where a
purge between arms is actively misleading, is under [a stale `.pyc` makes two
mutation arms one
measurement](#a-stale-pyc-makes-two-mutation-arms-one-measurement-and-restoring-the-source-cannot-see-it).

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

  **A docstring narrating why a rule went quiet is the sharp case, and it has now
  produced three wrong histories in one file.** `checks/inventory.py`'s docstring
  explains the silence of two `inventory-count` rules. Replay against the git log
  found `3` narrated claims wrong: that the `findings` pattern once required a
  trailing comma, when no pattern in the check has ever contained one and that
  pattern is byte-identical from the initial commit; that the rule went silent
  because its scoped documents stopped stating a total, when a replay over the
  `14` revisions of the two documents in scope matched in none of them and they
  never stated one — a denominator this entry carried as `266`, the repository's
  total commit count at `c9e42ad`, until 2026-08-11; and that
  `committed-harnesses`'s site was struck on `2026-08-02`,
  when `deea4f3` — the initial commit of that date — holds three files and
  `VERDICT.md` is not among them. That third one is the instructive one, because
  the date was not conjured. The phrase enters the corpus at `cee7ff8` on
  `2026-08-03` **already struck**, and the strike wraps prose reading *"Corrected
  2026-08-02"* — a date the document records about its own editing. The docstring
  read a document's account of itself as a fact about the log, which is the same
  move that produced the other two.

  **The class, stated so it transfers.** An explanatory claim in source is
  evidence-shaped, is quoted downstream as though it had been established, and is
  read by nothing here — `lifecycle-taxonomy`'s one file for one fact is the only
  source any check reads, and it reads a `TAXONOMY` tuple rather than prose. The
  cost asymmetry is the whole of it: narrating a history is one sentence and
  replaying one is a script, so the unchecked path is also the cheap path. Of the
  three claims above, `2` were relayed into briefs as fact on the corpus's
  authority before anyone replayed them. **No check is proposed**, because the
  population is unmeasured — nobody has counted how many evidential claims sit in
  this repository's docstrings, and a rule over prose in source has no fixture set
  and no measured false-positive rate. What is cheap and was not being done is the
  replay itself: `28` file-revisions across the `4` paths that have ever matched
  `committed-harnesses`'s scope settled the third claim in one pass.
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
  ~~**seven**~~ **eight** OD-range sites, ~~**four are current**~~ ~~**six are current**~~
  **six are current**, ~~one is
  deliberately frozen, and none is
  stale — the residue is a hole, not a live defect.~~ **two are deliberately frozen,
  and the claim that none is stale did not survive 2026-08-11.**

  **Recounted a second time 2026-08-11, and this entry was wrong in both halves.**
  The eighth site is
  `specs/002-spec-aware-agent-runtime/findings/023-user-namespace-privilege-model.md`,
  which writes *the whole sequence OD-01 through OD-23* in the same construction and
  is the **second** frozen site: a dated note beneath it records that the register ran
  to OD-23 when that pass read it and declines to amend the sentence, because it
  records what a dated pass observed. So the frozen population is two and not one —
  `checklists/requirements.md` freezes what a dated *validation run* read, and this
  one freezes what a *pass* saw. And *none is stale* was true when written and false
  when re-read: OD-31 landed on 2026-08-11 and **five** of the six current sites sat
  at OD-30 or OD-28 while the register ran to OD-31, so the residue this entry calls a
  hole had become a live defect at five sites at once. All five were advanced the same
  day. **The lesson is the one this entry already states about undercounting, arriving
  a second time**: a census of an unguarded surface goes stale by the same mechanism
  the surface does, and nothing reads either.
  **Recounted 2026-08-04, and the undercount was this entry's own.** It missed
  `docs/spec-kit-workflow.md:137` and
  `specs/002-spec-aware-agent-runtime/plan.md:11`, both of which carry the same
  struck-and-advanced range as the three it did name. The full ~~seven~~ **eight** are
  `docs/spec-kit-workflow.md`, `specs/002/spec.md` **twice**, `specs/002/plan.md`,
  `specs/002/research.md`, `specs/002/checklists/requirements.md` (a frozen one),
  `specs/002/findings/023-user-namespace-privilege-model.md` (the other, added by the
  2026-08-11 recount), and `specs/001-discovery-validation/plan.md`. **Undercounting matters more here
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
  wrong. *(That run covered seven lines because the eighth site was not yet known.
  Measured 2026-08-11, it is unread too and **by a third mechanism**: its range is
  split by the hard wrap — `OD-01 through` ends one line and `OD-23` begins the
  next — and `register_ranges` scans `doc.masked_lines` one line at a time, so
  `_RANGE` matches neither half. Joined across the break it matches once, which is
  what makes the wrap and not the markup the thing hiding it.)* The one site that
  *is* read is `plan.md`'s parenthesised
  `(OD-01 through OD-31, …)` *(advanced from `OD-21` through `OD-25` as the
  register grew; the generator writes this one)*, which matches and is judged a
  whole-register claim —
  which is why the OD register is guarded at all. A future site written as plain
  prose, unparenthesised and with no markup between the bounds, would be caught by
  neither the regex path nor the guard. Dropping the parenthesised-or-listed
  requirement was measured — it reports nothing on the current corpus — but it is
  free only because that U-01 counterexample happens to be struck.

  **These ~~six~~ seven sites are hand-maintained by decision, not by oversight, and this
  entry is the only place that says so.** The owner has settled that
  `register-range` stays as it is rather than being widened to read them, on
  measured grounds: relaxing `_RANGE` to tolerate markup between the bounds catches
  **zero** stale sites on the current corpus — all ~~six~~ **seven** are already advanced or
  deliberately frozen — while false-positiving on ~~the one site~~ **both sites** that must stay
  frozen, `checklists/requirements.md` and `findings/023`, which record what a dated validation run
  read and what a dated pass observed and whose whole point is that they do not advance. So the regex change buys
  nothing and costs a permanent false alarm at the ~~one place~~ **two places** a false alarm would be
  most misleading. **The consequence is a standing obligation on a human**: when the
  OD register grows, ~~six sites advance~~ **five sites advance** by hand, two stay frozen,
  and nothing anywhere will say if one
  is missed. That is the residue, it is accepted rather than unnoticed, and the
  count above is how wide it is. **The obligation was measured against itself on
  2026-08-11 and it had already been missed**: OD-31 landed and all five advancing
  sites stayed where they were, which is what a residue accepted on a human's
  attention looks like when the attention is spent elsewhere.
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
  `$`-typed and multiplicatively-typed respectively.
  `tools/corpuscheck/figures.py` also extracts
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
5. **One `EXPECTED` row per branch, not per check** — and probe it rather than
   trusting the count. `preserved-evidence` was added 2026-08-11 with a row for
   each of its five reported kinds, and a probe that stubbed each branch in turn
   still found one that survived with the self-test green: its two
   self-consistency rules shared a single fixture, so deleting one left the other
   satisfying the row. The fixture now violates both. **A row count equal to the
   kind count is not coverage**; the arm that proves coverage is deleting the
   branch and requiring the self-test to break, which is what
   `threshold_probe.py` does for constants and what nothing does automatically
   for branches.

   ~~The fixture now violates both and the probe catches all five.~~ **Corrected
   2026-08-11: a later probe of the same check found a branch the self-test
   cannot reach at all.** The scope filter's `undeclared` kind — a unit naming no
   `root.marker` — is in scope in every root by construction, because this
   repository and both fixture corpora read one `config.json`, so a `known-bad`
   unit holding it would turn the real gate red. Six branches were neutralised in
   turn: two broke the self-test, and four were held only by
   `tests/unit/test_preserved_evidence_scope.py`. **A fixture is the idiom and not
   the whole of the floor**, and where a kind cannot be scoped to a fixture root
   the arm that holds it says so rather than being left to the count.

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

**The corpus reading is tree-dependent, so quote the tree with it.** Taken at
`5fa07bb` on one commit, in both trees, minutes apart:

| tree | reading |
| --- | --- |
| the shared checkout | `0 error(s), 0 warning(s)`, **no skip** |
| a clean detached worktree | `0 error(s), 0 warning(s)`, **one skip** |

The skip is emitted by the check **`inventory-count`**, and what it names is the
*rule* **`vendored-repos`**, as out of scope in this tree. There is no check
called `vendored-repos`, and calling it one is how this reading gets misfiled.
The rule reads `examples/`, which is git-ignored, so a fresh worktree does not
carry it and the rule's declared precondition fails; the shared checkout does
carry it beside the corpus, the precondition is met, the rule reads a live claim
and announces nothing. Full disposition under [the `vendored-repos`
disposition](#vendored-repos-is-out-of-scope-in-ci-by-construction-and-says-so-rather-than-reporting-an-incident).

**So the one-skip figure is a detached-worktree baseline and not *the*
baseline.** A pass gating in the shared tree and comparing against it sees a
one-skip discrepancy that is not one, and a pass gating in a fresh worktree
against a shared-tree number sees the same thing mirrored. Say which tree.

## The census — `instruments.py`

**Read this before quoting a list of gates, including the one below.**

`python3 tools/instruments.py` prints every instrument in the repository: what
it checks, whether a non-zero exit fails anything, which CI job runs it, and
what to type to run it by hand. ~~Twenty-six entries at the time of writing —
nineteen gates, five advisories, two libraries.~~ **Twenty-seven entries as of
2026-08-11 — nineteen gates, six advisories, two libraries**, which is
`19 + 6 + 2` and is read off `instruments.py --check` rather than counted by
hand. *(The struck figure was a hedged count and went stale anyway, in a section
whose own first line says to read it before quoting a list of gates. The
advisory population is the limb that moved.)*

It exists because of a defect this directory had no name for. For a week every
pass was briefed with a five-item list of gates — `pytest`, `check_corpus.py`,
`gen_claims.py --check`, `check_tampers.py`, `removal_proofs.sh` — and every
pass reported all five green. There were never five. `tests/invariants/
runner.py` is a sixth, it went red at `7349e31` on 2026-08-08 when T096 added a
test to `tests/invariants/` without adding the invariant that names it, and it
stayed red through three CI runs (`abca043`, `821ef70`, `6cdd4a5`) that failed
on it **and on nothing else**. Every "all five green" was true.

That is a third shape beside the two this directory already documents. Findings
032 and 034 are instruments that produced a clean bit over a measurement they
had not taken — instruments that *lied*. Here nothing lied and nothing was
absent from CI. What was absent was **the instrument from the list of
instruments**, and no mechanism existed whose job was to notice that the list
and the set had come apart.

So `--check` makes ~~exactly one machine-checkable claim — that the census and
`.github/workflows/ci.yml` agree — and proves it in three directions:~~ **two
claims as of 2026-08-11, over two populations: that the instrument census agrees
with `.github/workflows/ci.yml`, in the three directions below, and that a
second census of the workflow's own jobs agrees with it, in a fourth.** *(The
struck phrasing was true until the job census landed, and is superseded in place
rather than edited because "exactly one claim" is what made this section's scope
legible.)*

The three directions over the instruments:

| direction | what it catches |
|---|---|
| declared and absent | a census entry names a CI job and step that the workflow no longer contains. A deleted step, or a renamed job — and a renamed job is not hypothetical here, the removal-proofs job was renamed on 2026-08-04. |
| present and undeclared | a `run:` step names a repository instrument that no entry names. **This is the 2026-08-08 defect mechanised**: a gate wired into CI cannot stay off the list. |
| unclassified | a file that looks like an entry point — every top-level `tools/*.py`, plus `tests/removal_proofs.sh` and `tests/invariants/runner.py` — that no entry names at all. `library` is a real answer and four files use it; not deciding is not an answer. |

All four failure modes were **planted and observed firing** rather than reasoned
about, on 2026-08-09: a deleted `gen_claims.py --check` step, a synthetic
`tools/brand_new_gate.py` wired into the corpus job, an unclassified
`tools/an_unclassified_tool.py` dropped into the directory, and the `corpus` job
renamed to `corpus-gates`. Each produced its own message and exit 1.

**A transcript is a measurement that happened once**, so all four plus two more
are committed as `tests/unit/test_instrument_census.py`, with a removal-proof
arm behind each. The two extra arms are the ones that would leave the census
green *forever* rather than merely unhelpful: the comment exclusion, without
which prose about a tool reads as wiring; and whether the entry-point scan
reads the filesystem at all, since an empty candidate list satisfies direction
3 for every input and no other test in the file would notice. That second one
is `check_tampers.py`'s vacuity floor, one file over.

### Direction 4 — the workflow's own jobs

**This section's thesis reproduced itself one level out, and in this file.**
At `8d74942` `ci.yml` declared six named jobs, and exactly one of those six —
`corpus gates (consistency, no model)` — appeared anywhere in this README, and a
pass was briefed with *"all five jobs are in `tools/README.md`"*, which is wrong
twice over: six, not five, and one named, not all. A hand-maintained list and
the real set had come apart again, in the section that opens by telling you to
read it before quoting a list of gates.

So the repair has the same shape as the one above and for the same reason: the
six names live in a `JOBS` census in `instruments.py` that `--check` reconciles
against the workflow, **and not in a paragraph here**, because a paragraph here
is what failed both times.

**What hid it is that a job has two names with different audiences.** The
mapping key — `go` — is what `needs:` and every `job=` field in the census point
at, and directions 1 and 2 have always read it. The `name:` value — `go test
(the enforcement point)` — is what a run page shows, what `gh run view` reports
per job, and what a required status check is matched on. **Nothing in the
repository read the second one.** Measured 2026-08-11 by renaming one job's
`name:` in a scratch worktree at `8d74942`: `check_corpus.py`, `gen_claims.py
--check`, `check_tampers.py`, `selftest`, `instruments.py --check`,
`invariants/runner.py` and `pytest` **all passed**. Renaming the *key* fires
direction 1 and always did, so the blindness was exactly the string a human
reads.

Direction 4 carries five checks and a vacuity floor: a declared job the workflow
does not define; a job whose `name:` disagrees with the workflow's; a job with
no `name:` at all, where GitHub falls back to the key and the declared name is
one nothing will ever show; a job that drops the shared runner-identity action;
and a job the workflow defines that the census does not declare, which is
direction 2's argument over the second population. The floor fails on an empty
declaration, because zero declared jobs would otherwise satisfy every other
check. Each was planted and observed firing, and each has an arm in
`tests/unit/test_instrument_census.py` with a removal proof behind it.

**The two populations stay separate.** `JOBS` is not folded into `INSTRUMENTS`
and `--check` prints them on separate lines, because merging them would move the
`19 + 6 + 2` figure this section is read for, and the classifications do not
transfer — a CI job is not a gate, an advisory or a library.

**A prose rule over the corpus was measured and declined.** 34 lines in the
corpus match a count-of-jobs phrase: 25 use *job* in an unrelated sense, 4 are
dated readings that must stay frozen, 4 are correct in-context references, and
**1** is the wrong site. One real defect in 34 firings is the disposition this
file already records for the duplicate-definition guard, declined on false
alarms it could not shed, and 4 of the 9 CI-relevant firings are sites a rule
would be asking to have falsified. **The ratio is not the decisive part,
though.** The one wrong site was in `tools/instruments.py`, a `.py` file, and
the walked corpus is markdown only while `search_roots` in
`corpuscheck/config.json` excludes `tools/` outright — so a prose rule could not
have reached its target at any width. That is a different and worse thing than a
poor hit rate, and it is a class the declinations recorded here did not yet
name: **a rule aimed at a population that does not contain the defect.** Finding
040 carries the full table.

`--run` runs the gates that have a standalone command, **does not stop at the
first failure**, and then names every gate it could not run and why. That last
part is the point: a run that quietly covered seven of nineteen and printed one
green line would be this file's own defect one level up.

Two things it deliberately does not have:

- **No timeout.** Not one number in `instruments.py` is a duration, because no
  duration in it has been measured. `proof_timeout.py` already carries a
  measured per-arm cap and `ci.yml` carries measured job bounds; a third bound
  invented here would be the one nobody derived.
- **No gate ordering.** `--run` executes the table top to bottom and reports
  every verdict, so the order changes nothing. The one place order is
  load-bearing is `selftest.py` before `check_corpus.py`, and that ordering is
  inherited from `ci.yml`'s own stated argument rather than invented.

`--check` is wired into the `corpus` job, and the job was chosen for a reason:
it is the only one that installs nothing, so a stdlib-only census keeps that
job's toolchain claim honest. `--run` is deliberately **not** wired anywhere.
CI already runs these in the jobs whose bounds were derived for them, split so
that a contributor does not wait on a container build to learn the model-judge
boundary was crossed; running the set again in one job would collapse that split
and make a four-minute instrument mandatory in a nine-second job.

### Where the authority lives, and why not here

~~**This file is not read by `check_corpus.py`.** The corpus include list is
`README.md`, `research`, `docs`, `specs`, `.cursor/skills` and
`.specify/memory`; `tools/` is never walked. So every link, count and figure in
this README is ungated, including the ones in this section~~, and a census
maintained *here* would have been a second folklore list with better prose.

**Superseded 2026-08-11 — every sentence in the struck passage is false, and the
widening of the include list is what made them so.** `tools` sits in the include
list in `corpuscheck/config.json`, `corpus.load` walks this file as one of the
139 markdown documents it loaded at `4118950`, and it carries the `consumer`
role. It is read, and what it says is gated. **The struck passage had been cited
as standing residue for days and went false underneath the citation**, which is
why it is superseded in place rather than deleted: a reader who arrives holding
the old claim has to be told what replaced it, and a deletion tells them nothing.

**What is gated here was established by planting the case rather than by reading
the config.** Three checks were observed firing against this file at `4118950`. A
relative link to a file that does not exist is `link-target`. A fragment with no
matching heading in this document is `link-anchor`. A four-decimal ratio, a dollar
amount or a multiplier — the three kinds `numeric_kinds` enables in `config.json` —
that occurs in no `specs/*/findings/*.md` is `numeric-provenance`,
which is the one that changes how this file is written: it treats a
measurement-shaped figure as a quotation needing a source, so **a figure derived
in this document states its operands**, and a figure that states none either
matches a findings document or turns the `corpus` job red. An instrumented run
reported fifteen of the eighteen checks then registered as touching this file, and
**that reading is
known to undercount** — `numeric-provenance` is absent from it and was
nevertheless observed firing here, so the plant is the measurement and the
instrumented read is not. **The reading is left as it was taken rather than
advanced**: it is a dated observation over the check set of the day it ran, and the
set has since reached nineteen.

**One further check reads this file and reaches none of it, and that belongs
beside the supersession rather than in a commit message.** `register-range` walks
`doc.masked_lines`, and the range this file quotes in
[the check set](#the-check-set) sits inside a code span, which the masker blanks
to spaces before the rule ever sees it. So the rule is inert at that site while
the register has run past the stated end, and a reader arriving with the news
that this file became gated could reasonably take that range for a checked one.
It is not checked. An unmasked one would be.

**Both directions were planted rather than read off the source, on 2026-08-11**,
in a clean detached worktree at `1cd79f6`. As committed, the range is absent from
`masked_lines` and the run reports `0 error(s), 0 warning(s)`. With the two
backticks removed and nothing else touched, the same run reports one warning at
`tools/README.md:98:65` — `found: D-01 … D-19`, `expected: D-01 … D-22`, hint
`the D register defines 22 entries and runs to D-22; this range under-counts it`
— so the quoted range under-counts the register by three entries. Restoring the
backticks returned the tree to `0 error(s), 0 warning(s)`.

The accepting set is worth enumerating rather than described by its complement,
because "parenthesised" is narrower than the rule and a classifier stated as a
complement is a failure this directory already records. A range is read as a
whole-register claim when it starts at entry `01` **and** either the line carries
ranges from two or more distinct registers, or the text immediately before it —
once trailing spaces, `*`, `~` and `_` are stripped — ends with one of `(`, `[`,
`—`, `–` or `:`. A struck range is skipped, as is a register holding fewer than
three definitions. Nothing outside that set is a site, which is what leaves the
deliberately partial ranges quoted elsewhere in this document unflagged.

Two consequences cut against what this section used to argue. The prose under
`tools/` is now held to the standard `research/` and `specs/` are held to, so a
stale count here fails a gate rather than merely misinforming a reader. And the
top-level `README.md` is no longer distinguished by being the pointer whose link
is checked — ~~the only pointer outside it is in the top-level `README.md`, which
*is* in the corpus include list and therefore has its link checked~~ **this
file's links are checked too, so the pointer's privilege was the first casualty
of the widening**.

That the authoritative census is `instruments.py` itself — a Python table,
reconciled by a gate that runs on every push — is untouched by any of this, and
the reason is worth separating from the gating question. Being walked by
`check_corpus.py` buys this file link resolution, anchor resolution and figure
provenance; it does not buy reconciliation of a prose list against the set the
list describes, which is the only property that would make a census here
trustworthy and the property `instruments.py --check` exists to supply. This
section is commentary on a mechanism that lives elsewhere. When the two disagree,
the mechanism is right.

## Which of these run in CI, and the one that deliberately does not

Until 2026-08-04 **none** of them did. Every corpus claim in this repository
rested on somebody having remembered to run them, which is the same standing as
no gate at all. `.github/workflows/ci.yml` now has a `corpus` job holding four
of them plus the census check, in this order, and the order is the argument:

| step | why it is where it is |
|---|---|
| `selftest.py` | **First.** A validator whose regex stopped matching passes everything, so `check_corpus.py` going green proves nothing until something has shown the checks still fire. This runs the whole set against a corpus where every check must fire and one where none may. |
| `threshold_probe.py` | A green self-test shows each check *fires*, not that the constant it fires at is the right one — `catalog-line-count` carried `TOLERANCE = 2` for its whole life and the self-test could not tell it from `0`. Wired **because it was measured**: 34 perturbations, and the cost is two dated readings — 5.2 s as first recorded at `71a0836` and 5.53 s re-measured there, against 11.29 s at `1cd79f6` — under the conditions stated below this table. ~~A sweep that costs five seconds does not need a schedule.~~ **A sweep measured in seconds does not need a schedule, which held at both readings.** |
| `check_corpus.py` | Errors only. `--warnings-as-errors` is deliberately not set — the warning classes that actually fire are line counts and register ranges, which go stale for the minutes between an edit and `gen_claims.py`. A gate that flaps gets worked around. A second step prints the full report, warnings included, to the run page and cannot fail. |
| `gen_claims.py --check` | The only thing that notices that window. |

The probe's cost is two dated readings rather than one figure, and the older one
was recoverable only by re-running it. 5.2 s entered this table at `71a0836` on
2026-08-04 carrying no conditions: none in the commit message, none in any
`findings/` document, and no second occurrence of the string anywhere in the
repository. It named no platform, no architecture, no privilege and no
interpreter, which is the labelling standard every other figure in this
repository is held to. It nonetheless survived being re-run at its own commit, so
it is kept beside the newer reading rather than replaced by it.

Both readings were taken on macOS `26.2` `arm64`, at euid `501`, on CPython
`3.12.11`, in a clean detached worktree holding no `examples/`.

* At `71a0836`, the commit that introduced the figure: 5.53 s median of three
  draws, 5.32 s lowest and 5.68 s highest. The original digit sits inside that
  spread.
* At `1cd79f6`, the same 34 perturbations: 11.29 s median of five draws, 11.15 s
  lowest and 13.09 s highest.

The host is held constant across the pair, so what moved is the tree rather than
the machine, and the cost is roughly double. What moved in the tree is not
isolated to one cause — the check set went from sixteen to eighteen over that
span and the corpus include list gained `tools` — so the doubling is recorded and
not attributed. Neither median is offered as a tail: five draws is not the forty
a `med`/`p90`/`max` row is built from.

The cache was cold at every draw and could not have been otherwise.
`threshold_probe.py` deletes every `__pycache__` under `tools/` before each child
interpreter starts and runs it with `-B` and `PYTHONDONTWRITEBYTECODE=1`, so a
cold cache is a property of the instrument rather than a condition its caller
supplies. The row's argument is untouched by the larger figure: eleven seconds is
still seconds, and a sweep measured in seconds needs no schedule.

`cite_advisor.py` is **not** wired, and leaving it out is the decision rather
than an oversight. It has no threshold and no finding it makes changes its exit
code — by design, because the gate rule underneath it was built, measured
against 184 ablated clean cases, and rejected. Wiring an advisory into a gate
rebuilds exactly that rejected rule. Running it ungated on every push emits a
permanent listing a reader learns to scroll past, which is how its one true
positive gets lost. It stays a human-run audit aid.

### The renderer is watched, and watching it may not gate

`slugify` is the one function in this tree whose oracle belongs to somebody
else, and after the differential measured it nothing was left watching. A
renderer change would reopen the defect that wrote two committed links against
invented anchors, in the same silence as the first time. `ci.yml` grew a
`slug-differential` job on 2026-08-10 that runs
[the differential](../specs/001-discovery-validation/harness/slug-differential/)
over the whole corpus on every push.

It is a `NON-GATING observation`, the category `ci.yml` already carries for the
unshare pair, and the reasoning is this file's own: the step needs outbound
HTTPS, so an upstream incident or a rate limit would redden a build while saying
nothing about the merge, and a gate that flaps gets worked around. It runs under
`continue-on-error` and reports a divergence as a `::warning::` and a step
summary instead.

Three choices in it were measured rather than assumed, and all three are
recorded at the job:

* **Its own job, not a step in `corpus`.** The whole-corpus run took `105.7`
  seconds on an M-series laptop at `8f15f50`, against a `corpus` job whose
  observed maximum is `44` seconds and whose value is being a fast signal.
* **The whole corpus, not `--path tools`.** The subtree is one document and
  `1.6` seconds, and it reaches `0` blockquoted headings — the population that
  hid a defect for two differentials running. A canary blind to the family that
  was last wrong is not one.
* **`push` only.** On `pull_request` the checked-out SHA is a merge commit
  nothing pushed, so the contents endpoint returns HTTP 404 and the harness
  correctly reports a miss rather than a difference — a useless annotation on
  every PR, for an observation that is a property of the renderer rather than of
  a branch.

It first ran at `3c21260` and took `50` seconds, `45` of them in the
differential, and reported no divergence. **A CI figure and a laptop figure are
different measurements**, which is the rule `ci.yml` opens with, and they
differed by `2.1`× — `105.7` seconds on the laptop against `50` in CI — in the
direction that leaves the 15-minute bound conservative.

What is owed is still the table row. Every row in that table is forty runs, and
`med`, `p90` and `max` are not defined on a single observation; this job's
duration is also mostly the endpoint's rather than this repository's, so one
draw says nothing about the tail a bound is read against. The figure is recorded
at the job and the row waits for the next whole re-derivation.

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
