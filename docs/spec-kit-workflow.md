# Spec Kit Workflow for `function2agent`

GitHub Spec Kit is the spec-driven development process of record for this repo.
This is the operating manual: what is installed, what to run, and in what order.

## Installed version and install path

| | |
|---|---|
| CLI | `specify-cli` **0.15.1** (upstream latest release, tag `v0.15.1`) |
| Install command | `uv tool install specify-cli --from git+https://github.com/github/spec-kit.git@v0.15.1` |
| Binary | `~/.local/bin/specify` (ensure `~/.local/bin` is on `PATH`) |
| Init command used | `specify init --here --force --integration cursor-agent --script sh` |
| Agent target | Cursor (`cursor-agent`), skills mode, bash scripts |

Verify with `specify version`; check for newer releases with `specify self check`
(read-only) and upgrade with `specify self upgrade`.

Notes on flags, verified against the 0.15.x source:

- `--ai` is gone; the flag is **`--integration`**.
- **`--no-git` no longer exists** (removed in v0.10.0). `specify init` does not
  touch git at all now — git behavior is an opt-in extension
  (`specify extension add git`). Nothing needed to suppress it here.
- `--here` initializes in place; `--force` skips the non-empty-directory
  confirmation. Init only writes `.specify/` and `.cursor/`, so `README.md`,
  `LICENSE`, `.gitignore`, and `research/` were untouched.

## What is installed

```
.specify/
  init-options.json                  # recorded init flags (integration, script, numbering)
  integration.json                   # active integration + invoke separator ("-")
  integrations/*.manifest.json       # file manifests for upgrade/uninstall
  memory/constitution.md             # THE CONSTITUTION (ratified 1.0.0, now v1.3.0)
  scripts/bash/                      # check-prerequisites, common, create-new-feature,
                                     #   setup-plan, setup-tasks
  templates/                         # spec, plan, tasks, checklist, constitution templates
  workflows/speckit/workflow.yml     # optional non-interactive full-cycle runner
.cursor/skills/speckit-*/SKILL.md    # the 10 agent-driven phase prompts
docs/spec-kit-workflow.md            # this file
```

Runtime state created later: `.specify/feature.json` (points at the active
feature directory) and `specs/<NNN>-<short-name>/` per feature.

## Phase sequence

Spec Kit phases are **agent-driven prompt templates**, not CLI subcommands. In
Cursor they are skills invoked with a **hyphen**, not a dot — `/speckit-specify`,
not `/speckit.specify`. (The dotted form in upstream docs is the Claude/Copilot
slash-command spelling; `invoke_separator` is `-` for this project.)

| Order | Command | Required? | Produces |
|---|---|---|---|
| 1 | `/speckit-constitution` | once per project | `.specify/memory/constitution.md` |
| 2 | `/speckit-specify` | yes | `specs/<NNN>-<name>/spec.md` + `checklists/requirements.md` + `.specify/feature.json` |
| 3 | `/speckit-clarify` | recommended | targeted Q&A folded back into `spec.md` |
| 4 | `/speckit-plan` | yes | `plan.md` (+ `research.md`, `data-model.md`, `contracts/` as needed) |
| 5 | `/speckit-tasks` | yes | `tasks.md`, dependency-ordered, grouped by user story |
| 6 | `/speckit-analyze` | recommended | cross-artifact consistency report (non-destructive) |
| 7 | `/speckit-implement` | yes | executes `tasks.md` |

Also available: `/speckit-checklist` (custom quality checklists, after plan),
`/speckit-converge` (re-assess codebase vs. spec and append remaining work as
tasks), `/speckit-taskstoissues` (convert `tasks.md` into GitHub issues).

Step 1 is **already done** — the constitution is ~~ratified at v1.0.0~~ ~~at v1.2.0: ratified at
1.0.0, amended twice since.~~ **at v1.3.0: ratified at 1.0.0, amended three times since.** Re-run
`/speckit-constitution` only to amend it, and follow its versioning rules
(MAJOR / MINOR / PATCH) plus the Sync Impact Report comment at the top of the file.

> **Corrected 2026-08-03 — superseded, not wrong. The version was accurate when
> this file was written and ~~two amendments have~~ **three amendments have** landed since.**
>
> - **v1.1.0**, 2026-08-02 (`plan.md` **OD-03**). Principle I gains one
>   requirement: a derived verifier MUST be validated against an artifact its own
>   derivation did not produce, or be marked provisional and carry provenance and
>   confidence. Four separate measurements had produced derived artifacts that were
>   fluent, complete and wrong.
> - **v1.2.0**, 2026-08-03 (`plan.md` **OD-13**). Principle IV bullet 1's network
>   clause becomes a four-term specification: addresses pinned at configuration
>   time, host *and* port granularity, DNS denied or proxied, and loopback /
>   RFC 1918 / link-local / cloud-metadata denied even on an allowlisted host.
> - **v1.3.0**, 2026-08-03 (`plan.md` **OD-22**). Principle VI is restated over a
>   **traced unit** whose kind is tier-relative — the node for an emitted agent
>   system, the span for a runtime executing a loop — and its ship gate binds
>   attributability to the shipping tier's own declared unit rather than to "a
>   versioned node". Three obligations are added with it: a closed declared unit
>   set, tracing at the finest unit that has an outcome and a cost, and unit
>   identity separated from artifact version.
>
> All three are MINOR bumps, all three carry owner approval and an empty migration
> plan, and all three are already reflected in the Sync Impact Report at the top of
> `.specify/memory/constitution.md`. The first two *strengthen* a NON-NEGOTIABLE
> principle. **The third is the one to read differently**: Principle VI is not
> NON-NEGOTIABLE, and the amendment also gives a previously unsatisfiable ship gate
> a subject, so it relaxes in one direction while adding obligations in three —
> the Sync Impact Report argues the bump rather than asserting it. **Anything
> planned against v1.0.0's wording will not pass the plan phase's Constitution
> Check.**

## How to drive it from Cursor

1. Open this repo in Cursor. The skills in `.cursor/skills/` are picked up
   automatically.
2. Type the skill invocation followed by your input as plain prose, e.g.
   `/speckit-specify <feature description>`. Everything after the command name
   is the input the skill reads.
3. Let each phase finish and **review its artifact before starting the next.**
   The gates are the point of the process.
4. The skills shell out to `.specify/scripts/bash/*.sh` for path resolution.
   Always run from the repo root.

Feature directories are numbered **sequentially** (`001-`, `002-`, …) per
`feature_numbering` in `.specify/init-options.json`.

Optional non-interactive runner (specify → gate → plan → gate → tasks →
implement) — useful for CI, not recommended for the first feature:

```bash
specify workflow run speckit --input spec="<description>" --input integration=cursor-agent
```

## Where the project actually stands

> **⚠️ THIS SECTION WAS REWRITTEN 2026-08-03 — superseded, not wrong.** It was
> headed *"Next step: the first feature spec"* and it listed three blockers.
> **All three are discharged**, and one of them was discharged in a way that
> narrows what this file used to say rather than simply answering it. The old
> text is struck below with what replaced it, because a reader who trusted it
> today would think the project had not started.

| Feature | State |
|---|---|
| **001 — discovery and validation** | **Closed.** Fifteen numbered experiments, nine ladder positions reached, eight run. The adjudication is [`../specs/001-discovery-validation/VERDICT.md`](../specs/001-discovery-validation/VERDICT.md); the binding scope decisions are **OD-01** through ~~**OD-14**~~ ~~**OD-20**~~ ~~**OD-21**~~ **OD-25** in [`../specs/001-discovery-validation/plan.md`](../specs/001-discovery-validation/plan.md) |
| **002 — spec-aware agent runtime** | ~~**Specify phase complete.**~~ **Clarify and plan phases complete.** [`../specs/002-spec-aware-agent-runtime/spec.md`](../specs/002-spec-aware-agent-runtime/spec.md), its quality checklist, and [`plan.md`](../specs/002-spec-aware-agent-runtime/plan.md) with its research, data model, contracts and quickstart. ~~Three `[NEEDS CLARIFICATION]` markers await the owner~~ |

> **Both rows corrected 2026-08-03 — stale, not wrong when written.** The OD range
> stopped at OD-14 before **OD-15**, **OD-16** and **OD-17** landed and before
> **OD-18**, **OD-19** and **OD-20** recorded the clarify session's own decisions.
> And the three markers do not await anybody: they were resolved by the owner on
> 2026-08-03 — they are exactly what OD-18, OD-19 and OD-20 record — and a fourth
> marker they opened between them was resolved the same day as FR-047. The "next
> command" sentence below was correspondingly wrong and is struck.
>
> **Corrected once more the same day: the range now ends at OD-21.** The fourth
> marker's resolution — serve the last-known-good set marked stale, deny past a
> configured staleness ceiling — was the one decision of that session still
> carried as prose rather than as a record. It is now **OD-21**, so all four of
> the clarify session's answers are citable and this row's range covers them.
>
> **Advanced again 2026-08-04: the range now ends at OD-25.** Four entries landed
> after OD-21 — **OD-22** and **OD-23** on 2026-08-03, the owner's answers to the
> two questions the production specification left open at its Clarifications
> section; and **OD-24** and **OD-25** on 2026-08-04, the workload's privilege
> model and the default disposition for tool output. This row states the
> register's extent and nothing narrower, so all four are inside it.

~~**The next command is `/speckit-plan`**, once the three markers are resolved —
or `/speckit-clarify` first if the owner prefers to resolve them through the
tool rather than in review.~~ **`/speckit-clarify` and `/speckit-plan` have both
run.** The next command is `/speckit-tasks`, and the constitution's
compliance-review section makes `/speckit-analyze` mandatory before
`/speckit-implement` for this feature, because it adds a permission tier.

### What the three former blockers turned into

1. ~~**The deployment model — needs a human decision, and no experiment resolves
   it.**~~ ✅ **Decided 2026-08-02, `plan.md` OD-08 (D-20): ship self-hosted;
   design so a fully hosted tier stays reachable without a rewrite.** The three
   things this bullet said would fall out of it did, and they fell out in three
   directions rather than one — multi-tenancy is *deferred rather than absent*
   and survives as namespaceability and tenant-identity disciplines enforced
   from the first commit; the credential architecture has its **custody** half
   discharged by construction and its **confused-deputy** half untouched; and
   the iframe tier is deferred with the hosted model.
2. ~~**Phase 0 results.**~~ ✅ **Complete.** The ceiling test ran and returned a
   result against the interest of the people who designed it: a curated,
   hand-written tool surface **never won a task family on success rate** against
   an agent holding a shell and the application's own specification. A
   pre-registered pivot rule fired, and `plan.md` **OD-09** honors it — v1 is a
   spec-aware runtime, a contract-derived verifier, and drift detection.
   Everything the whole-product vision described beyond those three left v1.
   **The theory this bullet gave for running Phase 0 first — that a spec written
   against an unfalsified thesis is expensive fiction — is the one thing here
   that was fully vindicated.**
3. ~~**Scope of feature 001** … the gating question is which agent class ships
   first … **so v1 picks one.**~~ **Superseded, and *narrowed* rather than
   answered — read this one rather than skimming it.** Feature 001 was scoped as
   discovery and is closed; feature 002 is the production spec. On the agent
   class: v1 operates **through the running application**, so the framing was
   right about the primary class. It was **wrong that v1 picks exactly one**.
   OD-07 established that a tool surface is a bet that the question falls inside
   it, and that losing the bet costs an entire budget for no answer, so v1 also
   holds a **general fallback path** — a shell. That is the fusion this bullet
   called the lethal trifecta by construction, and it is reconciled rather than
   avoided: `plan.md` **OD-10** makes v1 read-only and **OD-12** routes all
   egress through one mandatory enforcement point. The knowledge layer, the
   iframe embed and multi-agent artifact trading are deferred exactly as this
   bullet said.

### Non-negotiables from the constitution that shape a plan

Unchanged in substance and **sharper in ~~two~~ three places** since this file was
written: verification derives from contracts, never model self-critique — and a
**derived verifier must be validated against an artifact its own derivation did
not produce, or marked provisional** (v1.1.0); protocol lives in topology; the
loop is the default emission; safety boundaries are structural, with the network
clause now a **four-term** specification rather than "allowlisted to named
hosts" (v1.2.0); and observability ships with the capability rather than after
it — now stated over a **traced unit** the shipping tier declares, so it binds a
loop's spans and a graph's nodes alike, and **nothing ships that cannot be
attributed to one** (v1.3.0). The plan phase has a mandatory Constitution Check
that will hold you to all of them, **against ~~v1.2.0~~ v1.3.0 and not against the
wording quoted in older documents.**

Keep the spec free of tech-stack detail — stack choices belong in
`/speckit-plan`.

### The house convention for correcting any of this

Every document in this corpus corrects itself in place rather than being
rewritten. **Strike the wrong text, keep it visible, and attach a dated note**
that says what was believed and what is now known — and classify the change,
because the three are not the same act:

| Class | Meaning |
|---|---|
| **Wrong** | It was untrue when written |
| **Narrowed** | It was true and claimed more than the evidence supports; what may be inferred from it shrinks |
| **Superseded** | It was true of the state it described and that state has moved |

The section you are reading is *superseded*, and its third bullet is *narrowed*.
`python3 tools/check_corpus.py` gates the mechanical half of this — dangling
identifiers, unsourced figures, broken links — and it must stay clean.
