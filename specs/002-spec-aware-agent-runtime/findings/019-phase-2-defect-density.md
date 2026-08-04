# Finding 019 — Phase 2 produced five real defects against 2,337 lines of new source, six times denser than the working assumption on that denominator and 2.4 times denser on the one population containing all five; the two-rate explanation offered for it is reasoned from a single phase and is not a measurement

**Date**: 2026-08-03
**Feature**: 002 — this is the first finding in the second authority namespace. See
[`README.md`](./README.md) for why the numbering continues feature 001's sequence rather than
restarting.
**User Story**: none. This finding measures no product behaviour and answers no hypothesis on the
experiment ladder. It measures **this project's own output**, which is the first calibration anchor
this corpus has ever had for the work it is doing rather than for the world it is doing it in.
**Owner decision**: none is changed. The sizing in [`tasks.md`](../tasks.md) does not move, and the
reason it does not move is recorded there rather than restated here: no row in that document
multiplies a line count by a defect density, so there is no arithmetic for a corrected rate to
invalidate.
**Model spend**: **$0.0000.** No model was called, no credential was read, no network request was
made. Every number below comes from `git` and from `wc -l` over the working tree.
**Method**: the defect list is the implementation pass's own, taken from
[`tasks.md`](../tasks.md) §*Phase 2's measured defect density* and re-located in the working tree —
each of the five is pinned below to the file and line where its fix now sits, so the count is
inspectable rather than asserted. The line counts are recomputed here from the commit that built
Phase 2; the counting rule is stated in full because a line count with no stated method is not a
checkable number.

Numbering note: `018` was the last finding issued anywhere in the repository and `019` was free,
checked by ripgrep with `--hidden` across the whole tree before this file was created. No prior
artifact claims the identifier, in either namespace.

---

> ## Read this before quoting the two-rate table
>
> **The two-rate split — roughly one defect per 500 lines for storage-and-serialization work, roughly
> one per 3,000 for kernel-checked work — is *reasoned from a single phase*. It is not a
> measurement, and no measurement in this corpus supports the second rate at all.**
>
> One phase completed. It produced one density. The second rate in that table is the *prior* the
> phase was measured against, carried forward on an argument about failure modes rather than on any
> observation of kernel-mechanism code in this repository. Whether kernel-checked code is genuinely
> cleaner, or whether Phase 2 simply happened to be the harder phase, **is not established by one
> data point**, and the next phase to complete is the test of it.
>
> The table lives in [`tasks.md`](../tasks.md) and is not duplicated here, deliberately. Quote it
> from there, with this sentence attached. **A reasoned split requoted as a measured one is the
> failure this corpus has recorded repeatedly** — most recently in
> [finding 017](../../001-discovery-validation/findings/017-evaluation-contemporaneity.md) §S6, where
> a description of an instrument's behaviour went stale because nobody re-ran the instrument.

## The headline

**Phase 2 produced five real defects against 2,337 lines of new source — about one per 467.** The
working assumption going in was one per 3,000, so on that denominator the phase came in roughly
**6.4×** denser than predicted. On the one denominator that contains all five defects it is **2.4×**
denser; see [the denominator problem](#the-denominator-problem-this-measurement-has-about-itself)
below, which is not a caveat on the headline so much as a second reading of it.

The prediction was not merely low; it was low in the direction the implementer expected it to be
high. Phase 2 is types, schemas, canonical serialization, a repository and a rollback path — work
expected to be *cleaner* than the kernel-mechanism code of Phase 1, on the intuition that there is
less to get wrong. The measurement says the opposite.

## What was counted, and how

**The denominator is `wc -l` over the twelve Python source files that commit `34e33d3`
("Build Phase 2: contracts, storage, transitions, and the two decisions") added under `src/`.** Whole
files, every line including blanks, comments and docstrings; no exclusions; measured against the
working tree and confirmed byte-identical to the same files at that commit.

| file | `wc -l` |
|---|---:|
| `src/analysis/artifact_store.py` | 241 |
| `src/analysis/rollback.py` | 129 |
| `src/contracts/envelope.py` | 179 |
| `src/contracts/migrations/__init__.py` | 160 |
| `src/contracts/ownership.py` | 142 |
| `src/contracts/repository.py` | 310 |
| `src/contracts/schemas.py` | 225 |
| `src/contracts/transition.py` | 268 |
| `src/contracts/unvalidated.py` | 144 |
| `src/runtime/drift/__init__.py` | 8 |
| `src/runtime/trace.py` | 385 |
| `src/runtime/trace_budget.py` | 146 |
| **total** | **2,337** |

`wc -l` counts newline-terminated lines and Python's `splitlines()` counts logical lines; the two
agree exactly on all twelve files, so the total does not depend on which convention a reader assumes.
The counts are written as fixed digits and are deliberately **not** wired to the corpus's line-count
generator: a dated measurement is history, and a generated cell that silently advanced when someone
edited `repository.py` would leave this document's headline ratio disagreeing with its own table.

**Where the previously circulated 2,329 came from.** An earlier pass recorded "about 2,329" for the
same set. The difference is exactly **8** lines and it is exactly `src/runtime/drift/__init__.py`, an
empty package marker that the earlier count evidently excluded. Both numbers describe the same twelve
files; this one includes the stub because excluding a file on the grounds that it is short is a
judgement, and a judgement in a denominator has to be declared.

**Whichever way, "roughly 2,300" in [`tasks.md`](../tasks.md) is this measurement rounded and not a
different one.** That document's *one per 460* is `2,300 ÷ 5`; the unrounded figure is one per 467.
Nothing material moves.

## The five defects, each pinned to where its fix now sits

| # | Defect | Where the fix is | Class |
|---|---|---|---|
| 1 | A **non-reentrant lock**. `transaction()` holds the lock across the writes inside it, so a plain `Lock` deadlocked the repository the moment a caller wrote two rows in one transaction — the shape every ref move has, and the shape rollback always has | `src/contracts/repository.py` line 100, with the reason in the comment above it | concurrency, silent until a particular nesting occurs |
| 2 | A **rollback split across two transactions**. The restoration record and the ref move were separate commits, so a crash between them left a ref moved with no history entry: an unattributed move, which is the one case retained history exists to prevent | `src/analysis/rollback.py` lines 104–108, now one transaction | durability, silent until a crash lands in the window |
| 3 | A **volatility scanner with no positive control**. Nothing in the suite asserted that the scanner ever returns a non-empty list, so an implementation returning the empty list unconditionally would have passed every test in the file | `tests/contract/test_canonical_determinism.py`, `test_the_volatility_scanner_catches_an_undeclared_volatile_value` | **instrument reporting success while measuring nothing** |
| 4 | A **redaction marker that named no credential**. A bare marker is safe and useless: an operator reading a redacted trace of a session that used three credentials cannot tell which one appeared where, which is the diagnosis the trace was retained for | `src/contracts/secret.py` lines 23–32, the marker now carrying the configuration key | observability, safe and worthless |
| 5 | A **benchmark overwriting its own committed measurement** on every privileged run, so a deliberate re-measurement and an incidental CI run were indistinguishable and a real regression would arrive as ordinary run-to-run noise | `tests/batteries/test_seccomp_overhead.py` line 199, re-recording now behind an explicit environment variable | **instrument destroying its own baseline** |

**Three of the five are instruments or records that would have reported success while establishing
nothing** — the scanner that could match nothing, the marker that redacts without identifying, the
benchmark that overwrites the figure it exists to defend. That is the failure class this repository
has a name for and a whole checker directory about.

## The explanation offered, and why it is the load-bearing part

**Kernel mechanism code fails loudly. The kernel returns `EPERM`, the call fails at the syscall with
a named errno, and the test stops.** A wrong `clone` flag, a missing capability, a malformed seccomp
program: the failure arrives on first execution, before review, and it arrives labelled.

**Serialization and storage code fails quietly.** It returns a plausible value. The assertion passes.
The defect is in what the value *means* — a lock that is correct until a caller nests, a record that
is durable until a crash lands in a two-transaction window, a marker that is present and
uninformative, a scanner that matches nothing and reports clean.

So the intuition that types-and-serialization work has less to get wrong inverts. It has **more
surface to be quietly wrong on**, and quiet wrongness is what survives a test suite. That is the
argument, and it is what the classification in [`tasks.md`](../tasks.md) is built on.

**Two of the five were visible only because someone asked whether removing the mechanism would be
noticed**, which is this repository's removal-proof discipline applied at the point of writing rather
than as a script. Defects 3 and 4 are the two. Neither has a symptom; neither would have been found
by reading the code or by running the rest of the suite, because the rest of the suite passes either
way.

**Where the tree's own attribution differs from that summary, and it differs on one of the two.** I
could not establish "found by a removal proof" for both, and the difference is worth stating rather
than smoothing. Defect 4 carries an explicit attribution in the source — *"Found by T040's marker
test"* in `src/contracts/secret.py` and again in
`tests/invariants/test_secret_has_no_serializer.py` — so it was surfaced by a contract test, not by
`tests/removal_proofs.sh`. Defect 3 carries no attribution at all; what its fix carries is the
reasoning, in a docstring that opens *"The positive control for the scanner itself"* and says the
scanner *"could be returning the empty list unconditionally and nothing above would notice."* So the
common factor is the **discipline** — assert that the mechanism's absence would be detected — and not
the specific harness. That is the accurate version of the claim, and it is weaker than "a removal
proof found two of five" in exactly the way that matters: the discipline is what generalises, and
`tests/removal_proofs.sh` is one instrument implementing it.

**Discovery order cannot be established from history for any of the five.** The whole phase landed in
one commit, so nothing orders a defect's discovery against the code that fixed it — the same
undecidability
[finding 017](../../001-discovery-validation/findings/017-evaluation-contemporaneity.md) §S2 records
for the checker's fixtures, arriving again in the same repository for the same reason. Every
attribution in this section is read off a comment written by the pass that made the fix.

## The denominator problem this measurement has about itself

**Two of the five defects are not in the 2,337 lines.** Defect 4 is in `src/contracts/secret.py`, a
file the Phase 2 commit *modified* rather than added. Defect 5 is in
`tests/batteries/test_seccomp_overhead.py`, also modified, and under `tests/` rather than `src/`. The
numerator is drawn from everything Phase 2 touched; the denominator counts only the source files it
created.

That is precisely the pairing **U-49** was opened for — a numerator and a denominator drawn from
different populations, written as one measurement — arriving in this project's own first
self-measurement, one day after the register entry.
[Finding 018](../../001-discovery-validation/findings/018-verifier-false-alarm-attested-denominator.md)
states the rule: restate both sides over one population, or label each explicitly. Both, here:

| denominator | what it counts | are all five defects inside it? | rate | against one per 3,000 |
|---|---:|---|---|---|
| **2,337** | the twelve new `src/*.py` files — the headline | **No.** Three of five | one per 467 | **6.4×** denser |
| 2,695 | every line the commit added to any `src/*.py`, new files and edits alike | No. Four of five | one per 539 | 5.6× denser |
| 3,073 | every line the commit added anywhere under `src/`, including Go | No. Four of five | one per 615 | 4.9× denser |
| **6,235** | every line the commit added under `src/` **or** `tests/` — the one shared population | **Yes.** Five of five | one per 1,247 | **2.4×** denser |

**Both bold rows are true and they are not the same claim.** *One per 467* is the density of new
source, and it is the right figure for anyone asking how much review new source needs. *One per
1,247* is the only figure on this table whose numerator and denominator describe the same body of
work, and it is the right figure for anyone sizing a phase.

**The direction survives every denominator and the magnitude does not.** Phase 2 was denser than
predicted on all four; how much denser moves by a factor of about two and a half depending on which
population is named. **A statement of the form "six times worse" is only true of the narrowest
denominator, and must carry it.**

## What this does not establish

- **It does not establish the two-rate split.** Restated here because the callout at the top of this
  document is the thing most likely to be dropped in requotation. One phase produced one density. The
  ~1-per-3,000 rate for kernel-checked code is the prior, not an observation — no kernel-mechanism
  code in this repository has ever been counted this way. The loud-versus-quiet argument is a
  plausible mechanism for a difference nobody has measured.
- **It does not establish that Phase 2 is representative of storage-and-serialization work.** It is
  one phase, written by one pass, in one week, reviewed by the same people who wrote it. A second
  phase in the same class is the cheapest thing that would move this from an anchor to a rate.
- **"Five real defects" is a judgement, not a count of a well-defined population.** There is no
  declared severity bar, no independent adjudicator, and no record of anything that was considered
  and rejected as not-a-defect. The five are the five the implementation pass called real. A
  different reviewer might have said four or seven, and nothing here bounds that.
- **It says nothing about defects still present.** This is a count of defects *found*, and a phase
  that found five may contain more. Three of the five had no symptom, which is direct evidence that
  finding a defect in this class requires someone to go looking; the two found by removal proof are
  evidence about the method, not about the residue.
- **It cannot be converted into days, and no conversion is attempted.** A defect rate predicts
  defects. Turning one into schedule needs a cost per defect, which this corpus has never measured;
  [`tasks.md`](../tasks.md) refuses the conversion for the same reason and this finding does not
  supply one.
- **Nothing here is a claim about the correctness of the shipped Phase 2 code.** Five defects were
  found and fixed. That the fixes are correct is asserted by their tests, which are the same suite
  that missed three of the five.

## Register entries needing propagation

Identifiers only, and new entries are described rather than numbered so that nothing cites an
identifier before it exists. `research/14-architecture-synthesis.md` is outside this pass's write
scope and was not edited.

| Entry | Should become |
|---|---|
| **U-49**, existing | **A second instance, and the first in this project's own output.** The register entry was opened from a verifier false-alarm figure. The same shape — a numerator over one population paired with a denominator over another — is present in this feature's first self-measurement, and was found only by asking the question U-49 tells a reader to ask. Worth recording on the entry as evidence that the rule generalises past evaluation harnesses to any internal metric. |
| **New entry, next free `U` number** | **A defect-density anchor taken from a single phase is a point, and a two-rate classification derived from it is an argument wearing a measurement's clothes.** Phase 2 measured one rate; the second rate in the working split has no observation behind it at all. The mitigation is not a code change: it is that the split may not be quoted without the sentence saying which half was measured. The next completed phase either supports the split or collapses it. |

## Reproduction

Everything here is reproducible offline at `$0.0000`, with no credential, no network and no
container. From the repository root:

```bash
# the denominator: the twelve new Phase 2 source files, and the total
git diff-tree --no-commit-id --name-status -r 34e33d3 \
  | awk '$1=="A" && $2 ~ /^src\/.*\.py$/ {print $2}' | sort | xargs wc -l

# the same files as the commit left them, to show the working tree has not moved
for f in $(git diff-tree --no-commit-id --name-status -r 34e33d3 \
             | awk '$1=="A" && $2 ~ /^src\/.*\.py$/ {print $2}'); do
  git show "34e33d3:$f" | wc -l
done | paste -sd+ - | bc

# the four denominators in the table above
git show --numstat --format= 34e33d3 | awk '
  $3 ~ /^src\/.*\.py$/            {srcpy += $1}
  $3 ~ /^src\//                   {src   += $1}
  $3 ~ /^(src|tests)\//           {both  += $1}
  END {print "src py added:", srcpy; print "src added:", src; print "src+tests added:", both}'

# the five defects, each at the site named in the table
sed -n '96,101p'   src/contracts/repository.py
sed -n '103,109p'  src/analysis/rollback.py
grep -n 'test_the_volatility_scanner_catches_an_undeclared_volatile_value' \
     tests/contract/test_canonical_determinism.py
sed -n '22,33p'    src/contracts/secret.py
sed -n '199,208p'  tests/batteries/test_seccomp_overhead.py

# the only discovery attribution the tree carries, and the absence of the others
rg -n 'Found by|removal proof' src/ tests/
```

The two modified files carrying defects 4 and 5 are identified as modified rather than added by the
same `git diff-tree` invocation, with status `M`; that is the whole evidence for the denominator
section above.
