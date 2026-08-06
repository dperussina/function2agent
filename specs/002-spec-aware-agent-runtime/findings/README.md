# Feature 002 findings — measurements taken while building

**Opened**: 2026-08-03, after Phase 2 completed.
**Feature**: `002-spec-aware-agent-runtime` ·
**Plan**: [`../plan.md`](../plan.md) ·
**Specification**: [`../spec.md`](../spec.md) ·
**Tasks**: [`../tasks.md`](../tasks.md)

This is the corpus's **second** authority namespace. The first is
[`../../001-discovery-validation/findings/`](../../001-discovery-validation/findings/), and both are
authoritative in the same sense and by the same rule: `tools/corpuscheck/config.json` classifies
`specs/*/findings/*.md` as `authority`, so `numeric-provenance` treats every figure written here as
a source of record rather than as a quotation needing one.

---

## Numbering: this namespace continues feature 001's sequence rather than restarting

Feature 001 issued 001 through 018. **Feature 002 starts at 019.** Finding numbers are unique across
the whole repository, not per feature.

Three reasons, in the order they bind:

1. **The checker already requires it.** `findings-numbering` collects every document matching
   `specs/*/findings/*.md` into one map keyed by numeric prefix, so a feature 002 document numbered
   `001` is a duplicate prefix and an **error**, not a new namespace. The rule's own docstring gives
   the reason it is an error rather than a warning: *"every citation of 'finding 008' downstream
   becomes ambiguous and stays ambiguous — nothing in the prose says which one was meant, so the
   ambiguity cannot be resolved later by reading."*
2. **This corpus cites findings by bare number.** The citation the tooling recognises is
   `finding NNN`, and that is also how the prose reads throughout `research/`, `VERDICT.md` and both
   specifications. There is no field in the citation form where a namespace could go, so a restarted
   sequence would have to be disambiguated by a convention every future author remembers — which is
   the class of safeguard this repository has already recorded as failing.
3. **A globally unique number is self-disambiguating.** Under this scheme the number names exactly
   one document anywhere in the corpus, so a citation of "finding 019" resolves without a namespace
   qualifier. ~~Under this scheme the number *is* the namespace marker: 001–018 are feature 001, 019
   and upward are feature 002. A reader who encounters "finding 019" with no surrounding context can
   tell which feature produced it.~~

   **Retired 2026-08-05 by owner decision — the uniqueness stands and the feature-partition does
   not. A number identifies a document; it never identified a feature, and this claim is what said
   otherwise.** The reason it was retired rather than patched is that it is **unsatisfiable for any
   measurement of the world taken during a later feature**, which is a standing shape rather than a
   one-off. The borderline rule below files a measurement by *what it is of*, not by when it was
   taken; a number is minted from the single corpus-wide sequence at *the moment it is written*. So
   a provider, library or benchmark measured during feature 002 gets a feature-002-era number and a
   feature 001 filing, and the partition breaks by construction. The first case is
   [finding 031](../../001-discovery-validation/findings/031-provider-state-chain-measured.md),
   which measures four commercial LLM providers and now lives in feature 001's directory. **Do not
   reinstate the partition to tidy this up**: the only repair that would restore it is renumbering
   on relocation, and a renumber invalidates every existing citation of the number — the precise
   harm `findings-numbering` exists to prevent.

   **What still holds, and it is measured rather than argued.** Prefix uniqueness is enforced
   **corpus-wide, not per directory**. Established on 2026-08-05 by planting
   `specs/001-discovery-validation/findings/031-PLANT-cross-directory-duplicate.md` against the
   then-extant `specs/002-spec-aware-agent-runtime/findings/031-provider-state-chain-measured.md`
   and running `.venv/bin/python tools/check_corpus.py --check findings-numbering
   --warnings-as-errors`: **2 errors, exit 1**, `findings-duplicate` naming both paths. The plant
   was deleted and the tree returned to 0 errors. So numbers from one sequence living in two
   directories does **not** open a duplicate-number hole, and reasons 1 and 2 above are untouched.
   The consequence for reading the tree: feature 001's directory holds 001–018 **and 031**, and the
   sentence above about what each feature *issued* describes issuance, not directory contents.

**How a citation disambiguates, and the convention that goes with it.** Cite the number and link the
file, exactly as feature 001 does — `[finding 019](./019-phase-2-defect-density.md)` from inside this
directory, and
`[finding 019](../002-spec-aware-agent-runtime/findings/019-phase-2-defect-density.md)` or the
equivalent relative path from outside it. The number resolves on its own; the link states the owning
feature without the reader having to know the ranges.

**The cost of this choice, stated because it is real.** A single sequence means a new finding needs
the repository-wide high-water mark, not this directory's. Two features filing on the same day can
collide. The mitigation is the one feature 001 already uses and this namespace inherits: every
finding opens with a **numbering note** recording that the identifier was checked free across the
whole tree before the file was created. It is a convention, not a mechanism — the duplicate is caught
after the fact by `findings-numbering`, never before.

## What belongs here, and what belongs in feature 001

The two directories are not "old" and "new". They hold different kinds of measurement, and the
distinction is the thing to get right:

| | feature 001 `findings/` | feature 002 `findings/` (here) |
|---|---|---|
| What is measured | the world the product must work in — model providers, code graphs, agent loops, contract extraction, a ceiling on achievable task success | **this project's own output and its own process** — what the build produced, how it behaved, what it cost |
| Typical subject | an external system, a vendored corpus, a hypothesis from the experiment ladder | a phase's source, a shipped mechanism, a harness this repository wrote |
| What a figure licenses | a claim about feasibility, or about what a design may assume | a claim about this codebase, or about how the remaining work should be sized |
| Whether it can be re-run | usually yes, often at a stated model spend | usually yes, usually at `$0.0000`, against the working tree or a named commit |

**The rule that decides a borderline case.** Ask what the measurement is *of*. A measurement of
something outside this repository — a provider, a library, a benchmark, a corpus we did not write —
belongs in feature 001, whatever date it was taken on, because feature 001 is where this corpus's
model of the world lives. A measurement of something this repository produced belongs here.

**Feature 001 is closed to new findings and its documents are not.** Nothing forbids correcting or
extending an existing feature 001 finding; what does not happen is a *new* feature 001 finding
about production work.

## Two properties of this directory that follow from the tooling

**Everything written here is self-certifying, and that is what an authority namespace means.**
`numeric-provenance` does not run on `authority` documents — they *are* the provenance. A figure
invented here will pass every check and can then be quoted anywhere in the corpus. The obligation
that replaces the check is the one feature 001's findings discharge in prose: state the method, state
the population, and give a reproduction command that a reader can run.

**Opening a second namespace widened the accept surface for every consumer document in the corpus,
including feature 001's.** The provenance lookup concatenates *all* authority documents into one text
and asks whether a quoted figure occurs in it, with no test that the finding and the claim belong to
the same feature. So a figure measured here can now silently supply provenance for a sentence about
feature 001's validation work, and the reverse. Nothing in the tooling will notice. The mitigation is
the citation convention above — quote a finding by number **and** link it, so a reader can see which
namespace the number came from even where the checker cannot.

## Index

| Finding | Subject | Spend |
|---|---|---|
| [019](./019-phase-2-defect-density.md) | Phase 2's defect density — this project's first calibration anchor for its own output, and the denominator question it raises about itself | `$0.0000` |
