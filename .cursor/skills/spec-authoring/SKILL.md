---
name: spec-authoring
description: Drives the Spec Kit workflow in this repository and holds a feature spec to the project constitution before it reaches the plan phase. Use when writing or reviewing a feature spec, running the speckit phases, scoping a vertical slice for `/speckit-specify`, deciding where an artifact belongs under `specs/<NNN>-<name>/`, or checking a spec or plan against the four non-negotiable constitutional principles.
disable-model-invocation: true
---

# Spec authoring

Sources: `docs/spec-kit-workflow.md`; `.specify/memory/constitution.md` (ratified v1.0.0).

Spec Kit `specify-cli` **0.15.1**, initialized with `--integration cursor-agent --script sh`.

## Command spelling: hyphen, not dot

**In Cursor the phases are skills invoked with a hyphen: `/speckit-specify`. Never
`/speckit.specify`.** The dotted form in upstream Spec Kit docs is the Claude/Copilot slash-command
spelling; `invoke_separator` is `-` for this project (`.specify/integration.json`). A dotted command
will not resolve.

The phases are **agent-driven prompt templates, not CLI subcommands**. The one real CLI is
`specify` itself (`specify version`, `specify self check`, `specify self upgrade`).

## Phase sequence

| Order | Command | Required? | Produces |
|---|---|---|---|
| 1 | `/speckit-constitution` | once per project — **already done, v1.0.0** | `.specify/memory/constitution.md` |
| 2 | `/speckit-specify` | yes | `specs/<NNN>-<name>/spec.md`, `checklists/requirements.md`, `.specify/feature.json` |
| 3 | `/speckit-clarify` | recommended | targeted Q&A folded back into `spec.md` |
| 4 | `/speckit-plan` | yes | `plan.md` (+ `research.md`, `data-model.md`, `contracts/` as needed) |
| 5 | `/speckit-tasks` | yes | `tasks.md`, dependency-ordered, grouped by user story |
| 6 | `/speckit-analyze` | recommended | non-destructive cross-artifact consistency report |
| 7 | `/speckit-implement` | yes | executes `tasks.md` |

Also available: **`/speckit-checklist`** (custom quality checklists, after plan),
**`/speckit-converge`** (re-assess the codebase against the spec and append remaining work as
tasks), **`/speckit-taskstoissues`** (convert `tasks.md` into GitHub issues).

Re-run `/speckit-constitution` **only to amend**, following its MAJOR/MINOR/PATCH rules and updating
the Sync Impact Report comment at the top of the file.

**Let each phase finish and review its artifact before starting the next. The gates are the point of
the process.** The skills shell out to `.specify/scripts/bash/*.sh` for path resolution, so always
run from the repo root. Feature directories are numbered sequentially (`001-`, `002-`, …).

## Scope one vertical slice per invocation

**Spec Kit creates exactly one feature per `/speckit-specify` invocation, and this product is far
too large for one.** Slicing is therefore a required step, not a nicety — an unsliced invocation
produces a spec too broad to plan against.

A plausible first cut, from `docs/spec-kit-workflow.md`: *analyze one language's codebase → emit one
layer's agent with contract-derived verification and a loop.* Defer the knowledge layer, the iframe
embed, and multi-agent artifact trading to later features.

Test a proposed slice against all four:

- Does it exercise the differentiator (contract-derived verification) end to end?
- Does it depend on anything the research corpus lists as unsolved?
- Can it be verified programmatically against a committed fixture repo?
- Is it one feature, or is "and" doing load-bearing work in the description?

**Keep the spec free of tech-stack detail. Stack choices belong in `/speckit-plan`.**

## Where artifacts live

```
.specify/memory/constitution.md      # the constitution (amend only via /speckit-constitution)
.specify/feature.json                # runtime pointer at the active feature directory
.specify/scripts/bash/*.sh           # path resolution the phase skills shell out to
.specify/templates/                  # spec, plan, tasks, checklist, constitution templates
specs/<NNN>-<short-name>/
  spec.md                            # /speckit-specify
  checklists/requirements.md         # /speckit-specify, plus /speckit-checklist output
  plan.md, research.md, data-model.md, contracts/   # /speckit-plan
  tasks.md                           # /speckit-tasks
```

Do not hand-create feature directories or hand-edit `.specify/feature.json`; the scripts own both.

## The four non-negotiables every spec must satisfy

`/speckit-plan` has a **mandatory Constitution Check section** that will hold the spec to these.
Satisfy them while writing the spec, not while defending the plan.

### I. Contract-Derived Verification (NON-NEGOTIABLE)

Every verification signal in an emitted agent derives from an artifact the codebase already
contains — type signatures, return types, declared exceptions, existing tests, observable state.
**The project must not ship LLM self-critique as the verification mechanism for any emitted node,
and must not let a model decide "did this succeed."** A promoted function emits a node contract
(reads, writes, pre, post); a node with no derivable verifier is flagged, not backed by a model
critic. Where a model must judge, it is pairwise. See `contract-derived-verification`.

**Spec smell:** any acceptance criterion phrased as "the agent confirms," "the model validates," or
"quality is assessed by."

### II. Topology Encodes Protocol

**Anything an agent must not skip lives in graph structure, not in a system prompt.** Every emitted
topology is serializable **data** (not code), diffable, content-addressed, and versioned, and
carries a machine-checkable invariants block — e.g. "every irreversible node is preceded by an
approval node" — that runs as topology tests on every change, human or optimizer. See
`graph-vs-loop-decision`.

Note the companion principle III: **the default emission is a plain tool plus a loop.** A graph is
emitted only on a declared constraint, and the escalation must cite that specific constraint in the
emitted artifact. A spec that assumes a graph without naming the constraint fails the Constitution
Check.

### IV. Structural Safety Boundaries (NON-NEGOTIABLE)

Safety is structural, never prompt-level, for the combination this product creates by construction:
shell access, production data access, and untrusted end-user input.

- **Permission tiers.** Every emitted tool is classified read-only, reversible-write, or
  irreversible/destructive, and the tier is enforced structurally.
- **Reachability.** An untrusted surface must not reach an irreversible tool without traversing a
  gate.
- **Secrets.** Configuration arrives via environment-variable injection with a declared, validated
  schema; **secret values are never written into generated artifacts**, and startup fails loudly on
  a missing or invalid required variable. See `credential-and-env-injection`.
- **Attribution.** Every action is attributable to an author, an input, and a content hash.
  Guardrails, evals, and the invariant list live where an agent cannot modify them.

### VII. Test-First and Fixture-Backed (NON-NEGOTIABLE)

Tests are written and **must fail** before implementation, with a shape specific to an
analyzer-plus-generator rather than a web app:

- **Analyzer:** every supported language and framework has a **committed fixture repository** plus
  asserted expected decomposition. **A language without a fixture is not supported** — not
  best-effort, unsupported.
- **Generator:** emitted artifacts are asserted structurally — topology tests for reachability and
  ordering, contract tests per node, schema tests on the serialized topology.
- **Determinism:** analysis of a fixed input is reproducible and emitted artifacts are byte-stable
  for the same input and version. Model calls in tests are served from recorded cassettes keyed by
  `(node_id, step, prompt_hash)`. **Cassette replay tests the plumbing; evaluations test the
  prompts** — do not conflate them. See `experiment-design`.
- **Integration surface:** HTTP/SSE, the iframe embed contract, and env-var injection each have
  contract tests that **fail closed** on missing or malformed configuration.

Adding a supported language, a new emitted node kind, or a new tool tier requires its fixtures and
contract tests **in the same change**.

## Review bar before advancing a phase

- [ ] Every command in the artifact uses the hyphen form
- [ ] The feature is one slice; "and" is not load-bearing in its description
- [ ] No tech-stack detail in `spec.md` (it belongs in `plan.md`)
- [ ] No acceptance criterion depends on a model's self-assessment (I)
- [ ] Anything that must not be skipped is expressed as topology, and any graph cites its declared constraint (II, III)
- [ ] Every tool named in the spec has a permission tier, and no untrusted path reaches an irreversible tool ungated (IV)
- [ ] Every new language, node kind, or tool tier brings fixtures and failing tests in the same change (VII)
- [ ] Any new layer, dependency, or agent boundary is justified against a **named failure it prevents** (VIII — unjustified structure is a review defect, not a style preference)
