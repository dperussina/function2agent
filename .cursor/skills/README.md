# Project skills roster — `function2agent`

Project-scoped Agent Skills live in `.cursor/skills/<skill-name>/SKILL.md` and are shared with
anyone using this repository. This file is the roster: what exists, what is planned, and what
each planned skill is waiting on.

These skills exist to make the `research/` findings **operative** — to change agent behavior at
decision time rather than sitting inert in markdown. Each one encodes a decision procedure,
thresholds, or constraints that an agent would otherwise get wrong.

## Conventions used here

- **Auto-invocation is on by default.** Every guardrail skill omits `disable-model-invocation`.
  They are ambient: they must fire when an agent is about to make the relevant mistake, not only
  when a human names them. A skill that is a *procedure a human explicitly invokes* rather than a
  guardrail sets `disable-model-invocation: true` — currently only [`spec-authoring`](spec-authoring/SKILL.md),
  which drives a phase workflow that must not start on its own.
- Every skill cites its source as `research/<doc>.md §<section>` so a reader can go deeper.
- Load-bearing numbers are stated inline. A skill that says "multi-agent is expensive" does not
  change behavior; one that says "~15× tokens" does.
- Negative findings are stated as negative findings. These skills should make an agent more
  skeptical, not more confident.
- **The 10 `speckit-*` skills in this directory are not ours.** Spec Kit 0.15.1 installed them as
  its phase prompts (`speckit-specify`, `speckit-plan`, …). Leave them alone; they are managed by
  `specify` and are replaced on upgrade. The roster below covers only the 18 hand-written project
  skills. See [`docs/spec-kit-workflow.md`](../../docs/spec-kit-workflow.md).

## Standing after OD-09 — read this before using the roster

**`plan.md` OD-09 (2026-08-02) cut v1 to a spec-aware runtime, a contract-derived verifier and drift
detection.** Tool synthesis, promotion selection, generation-time effect classification and
decomposition-into-agents left v1. **No skill was deleted.** A skill describing v2 work is still
correct about v2, and the ones below carry a standing banner at the top of their `SKILL.md`.

| Skill | Standing | What changed |
|---|---|---|
| [`tool-synthesis-from-code`](tool-synthesis-from-code/SKILL.md) | **v2 — deferred** | Describes nothing v1 builds. Correct about v2, which now carries a measured number (~~2.8×–9.3×~~ ~~2.2×–9.3×~~ **2.20×–4.366× within session** cheaper, lower bound corrected 2026-08-03 — the join ratio is 2.20×, not 2.8× — and **upper bound narrowed the same day**, the 9.3× being a cross-run n = 2 pairing rather than a range endpoint) and a measured liability (returns nothing outside its surface). Its *effects metadata* section is the exception — the Principle IV mandate is v1, the static per-tool mechanism is v2 |
| [`codebase-decomposition`](codebase-decomposition/SKILL.md) | **v2 — deferred, undecided** | v1 is one agent by scope, not by evidence: the arm that would have settled it never ran. Nothing in the skill was refuted |
| [`mcp-export-design`](mcp-export-design/SKILL.md) | **Split** | *Not the internal calling convention* is v1 and binding. The **export adapter defers with synthesis** — the artifact it exported was the tool catalogue. Its "decisive" reason 4 is **wrong for v1** and right for v2 |
| [`agent-tool-design`](agent-tool-design/SKILL.md) | **v1 — narrowed** | Applies to the four tools v1 hand-writes, and to v2 synthesis. Its framing sentence — *this project's core job is synthesizing tools* — is no longer true of v1 |
| [`multi-agent-topology-review`](multi-agent-topology-review/SKILL.md) | **v1 — its default became the architecture** | "One agent" is now the shipped design. It won by forfeit, not by measurement; do not cite v1's shape as evidence for the default |
| [`agent-safety-and-sandboxing`](agent-safety-and-sandboxing/SKILL.md) | **v1 — extended, and ~~the Principle IV gap is now filled~~ *one* of Principle IV's gaps is now filled** *(corrected 2026-08-03: the skill encodes bullet 2, permission tiers; **bullet 1's network allowlist is unmet by v1 and was uncited** — C-17)* | New section *Effect tiers and the interception point* encodes Principle IV as a five-step procedure: classify the **call** not the tool when the tool is general, resolve from the fully-substituted action, intercept in deterministic code that can block, bind tier to disposition, state unmeasured precision. Its static trifecta audit is **wrong for v1** — there is no promotion time to compute it at — and its closing *do not promote it* rule defers with the promotion step |
| [`contract-derived-verification`](contract-derived-verification/SKILL.md) | **v1 — promoted to half the product, and now gating it** | Ranked third of four differentiators; now one of two. D-09's thin margin is now under half the product, and the head-to-head that was supposed to earn its headline status (`11` Phase 2) never ran — ~~**and as of `plan.md` OD-11 (2026-08-03) it runs before the production spec, which is blocked on it**~~ **and as of `plan.md` OD-14, the same day, it never will run here: the harness was built and dry-run at $0.00, its corpus cannot answer the question, and the margin is declared UNMEASURED and deferred to production. The skill's *mechanism* claims are demonstrated — 9 of 9 numeric errors, 3 of 3 sub-1% near-misses, zero false alarms on 220 clean positives *(the offline full-corpus sweep, not the `0/60` judge-scored sample — [`14`](../../research/14-architecture-synthesis.md) §3.2)*, no numeric constant in the ladder — its *comparative* claims are not** |
| [`experiment-design`](experiment-design/SKILL.md) | **v1 — unchanged, with a worked example** | Its own pre-registration discipline produced OD-09, including a second rule that fired *against* the pivot and cut the evidence base to one family at n = 4. **OD-10 and OD-11 are two more instances of the same discipline**: one takes the first branch of a Phase 5 rule that never ran, the other refuses to spec on three unmeasured capabilities. **OD-14 is the counter-instance and belongs in this row for that reason** — it specs on three unmeasured capabilities anyway, having found the measurement unobtainable, and says so in those words. A skill about experiment design should carry the one time the discipline was knowingly set aside, not just the times it held |

**Two further owner decisions, 2026-08-03, and both land inside this table rather than beside it.**
**OD-10 — v1 is read-only.** No write ships until the effect gate's precision is measured, so
`agent-safety-and-sandboxing`'s disposition table collapses to allow-a-resolved-read / deny-everything-else
and nothing escalates to a human at runtime. **Do not read that as the trifecta being cut** — egress is
a shell plus network access, and read-only leaves it intact. ~~**OD-11 — the production spec is blocked**
on the verifier-versus-judge head-to-head above. The next artifact is an experiment, not a
specification.~~ **OD-11's blocking condition was retired the same day by OD-14.** The head-to-head
was built, self-tested and dry-run at $0.00 and then not executed — 2 discriminative traces, three
pre-registered riders capping the verdict independently, four of seven task families lost to the
eligibility rule — so **the verifier's margin over an LLM judge is UNMEASURED and deferred to
production, the spec is unblocked, and the next artifact is a specification again.** OD-14 records
that as **a deliberate departure from this project's prove-before-build discipline**, and
[`VERDICT.md` §2](../../specs/001-discovery-validation/VERDICT.md#all-three-v1-capabilities-ship-unmeasured)
states the consequence once: **all three v1 capabilities ship without measurement.**

**A third change, 2026-08-03, later the same day, and it is a *correction* to two skills rather than
a consequence of a decision.** Working out whether network-layer egress control closes the limb OD-10
left open turned up that **constitution Principle IV's first bullet — *network allowlisted to named
hosts* — is unmet by v1 and had never been cited**; every Principle IV argument in this corpus,
including `agent-safety-and-sandboxing`'s five-step procedure, is about the *second* bullet
(`14` **C-17**, **U-44**; `plan.md` **OD-12**, proposed — a drafted requirement, not a decision).
**`agent-safety-and-sandboxing`** has its read-only trifecta paragraph struck and rewritten (an
egress allowlist is an obligation, not an option, and it narrows the leg to four named channels
rather than cutting it), gains a five-term specification of the egress control, and gains a fifth
non-compliance pattern in Step 3 — **an interception point is not an egress control**, because its
visibility ends at the argv of any command it allows. **`credential-and-env-injection`** moves out of
*Unaffected* below: its Rule 3 gains the same five terms and the note that under self-hosting we
specify the policy and the customer instantiates it.

**A fourth change, 2026-08-03 later the same day, and it upgrades the third from a correction to a
requirement.** ~~`plan.md` **OD-12**, proposed — a drafted requirement, not a decision~~ — **ratified**,
and **OD-13** amends `.specify/memory/constitution.md` to **v1.2.0**, replacing bullet 1's *"named
hosts"* with four normative terms (pinned addresses, host *and* port, DNS denied or proxied,
loopback / RFC 1918 / link-local / metadata denied even on an allowlisted host). **The change that
matters for the skills is where the control lives:** all sandbox egress traverses **one mandatory
proxy** holding the destination allowlist and the method allowlist together, which resolves the
Step 3 non-compliance pattern above rather than only naming it — an in-process check can be walked
past by a subprocess and a proxy cannot. **`agent-safety-and-sandboxing`** takes the ratification,
the constitutional wording, the enforcement-point change, the resolution of the shell dilemma in
Step 3, and the TLS-interception verdict (**rejected for v1** in favour of re-origination, because a
proxy CA inside the sandbox concentrates impersonation into one key and forces a certificate pin on
self-hosted targets). **`credential-and-env-injection`** takes the same wording changes in Rule 3 and
the operator-burden reasoning that produced the TLS verdict. **Neither skill's claim about what the
control buys changes:** the egress leg is narrowed to enumerated channels, not cut (U-44), and
*provably read-only* is no more available at a proxy than in a dispatcher (U-43).

**Unaffected:** `context-engineering`, `provider-abstraction`, `research-doc-conventions`,
`knowledge-graph-memory`, `vendored-example-navigation`,
`integration-surface-design`, `harness-selection`, `spec-authoring`. **`harness-selection` deserves a
note despite being unaffected:** OD-01's 2.5–3.5 weeks of loop-safety build is **unchanged** by the
pivot and is now the largest item on the critical path, so it is more relevant than before, not less.

## Written and available

| Skill | Purpose | Encodes | Source |
|---|---|---|---|
| [`agent-tool-design`](agent-tool-design/SKILL.md) (185 lines) | Design or review a tool exposed to an LLM | Naming, description disambiguation, parameter schemas, error-message-as-prompt, token-efficient returns, the 30–50 tool confusion threshold, deferred loading vs. code execution | `01 §5` |
| [`graph-vs-loop-decision`](graph-vs-loop-decision/SKILL.md) (175 lines) | Decide whether emitted control flow is a loop, an FSM, or a graph | Loop-is-default rule; graph only on a declared constraint (ordering / mandatory step / human gate / compensator); topology-as-data with content hash, version, and machine-checkable invariants | `03 §2, §8, §11` |
| [`contract-derived-verification`](contract-derived-verification/SKILL.md) (451 lines) | Build verification signals from code contracts, not from model opinion — **and validate the derived verifier itself, or mark it provisional** | Signature → verifier mapping **with its rows now measurably ranked — shape checks reach 0 of 9 value errors, recomputation reaches 9 of 9**; the arXiv:2310.01798 self-correction negative result; judge AUROC 0.18–0.30 on false success; **the validate-or-mark-provisional decision procedure, merge-blocking under constitution v1.1.0 Principle I**; **score-on-the-full-population (C-19) and freeze-the-questions (U-47)**; typed terminals; loop guards | `03 §3, §7.1, §11`; `04 §2, §11`; **constitution Principle I (v1.1.0)**; `14` D-17, **D-21 amendment (4), C-19, U-47**; findings `007 §4–5`, `011 §6`, **`015`** |
| [`context-engineering`](context-engineering/SKILL.md) (160 lines) | Budget and manage what enters the context window | Effective-vs-rated window gap; raw → compact → summarize ordering; the four failure modes; subagent isolation as a per-tool execution mode | `01 §3, §4` |
| [`multi-agent-topology-review`](multi-agent-topology-review/SKILL.md) (179 lines) | Argue against unnecessary multi-agent designs | ~15× token multiplier; token spend alone explained ~80% of BrowseComp variance; MAST 41–86.7% failure rates, two-thirds architectural; single-threaded-writes / fan-out-reads-only | `01 §7` |
| [`provider-abstraction`](provider-abstraction/SKILL.md) (139 lines) | Draw the line between what a model-provider layer normalizes and what it must not | Two-tier abstraction; `provider_state: opaque` as a first-class type; the four things that must never be abstracted (hosted tools, sandboxes, multi-agent, memory) | `05 §4.2–4.4` |
| [`research-doc-conventions`](research-doc-conventions/SKILL.md) (138 lines) | Keep new research docs consistent with the established house style | Dated "Last researched" line, TL;DR box, mandatory source links, explicit unverified section, density over length, negative findings stated plainly | `research/` house style |
| [`codebase-decomposition`](codebase-decomposition/SKILL.md) (174 lines) | Decide where one generated agent ends and the next begins | Layer decomposition is the wrong axis (~15× tokens for a call stack of LLMs); bounded contexts are right but not statically recoverable; codegraph has **zero** layer/domain concept so boundary inference is net-new; import-DAG clustering → framework classification → LLM adjudication; four forcing functions, only the trust-boundary one non-negotiable | `07 §3.1`; `06 §1` |
| [`tool-synthesis-from-code`](tool-synthesis-from-code/SKILL.md) (223 lines) | Turn analyzed code into a curated tool set rather than a function dump | Mechanical 1:1 conversion is the documented anti-pattern (FastMCP author, ~70% of MCP servers: "technically work but fail in practice"); 300 endpoints → ~20–25 tools (~15:1); synthesize at the **trust boundary**, not the function boundary; consolidation into outcome-named tools; `read_only`/`egress` effects metadata MCP cannot represent | `07 §3.2`; `09 §5.3, §4.3`; `01 §5` |
| [`knowledge-graph-memory`](knowledge-graph-memory/SKILL.md) (164 lines) | Design the knowledge and memory layer | The four tiers and the working+episodic default; files beat vectors but the agent is not yet a reliable librarian; memory as a documented attack surface (four write channels incl. experience-to-procedure, ~99% sleeper write rates, write-time checks failing compositionally); staleness / contradiction / growth / provenance | `01 §4`; `04 §5.4`; `07 C9, §6.1` |
| [`mcp-export-design`](mcp-export-design/SKILL.md) (217 lines) | Design the MCP export surface without making MCP internal | MCP as export adapter and headline artifact, not calling convention; the four reasons, decisively that schemas have no slot for `read_only`/`egress`; **four breaking wire revisions in ~20 months**; modern-server + legacy-client fails, so generated servers must be dual-era for ~a year; code mode blocked over connectors; progressive disclosure is a vendor API construct, not MCP | `09` |
| [`vendored-example-navigation`](vendored-example-navigation/SKILL.md) (171 lines) | Find prior art fast in the read-only `examples/` tree | What each of the eight repos is good for and is *not* evidence for; high-value paths (`get_fast_api_app()`, the 26 CRUD routes, `types.py`, the CMA notebooks); `adk-python` as the one genuine Class B target with `/openapi.json` as the answer key; 78% Python / 16% TypeScript and zero real PHP/Ruby/C#/Swift | `06`; `12` |
| [`agent-safety-and-sandboxing`](agent-safety-and-sandboxing/SKILL.md) (460 lines) | Place isolation, permission layers, and human gates in a generated stack | **Principle IV as a five-step procedure: every call tier-resolved at a deterministic interception point that can block, unresolvable ⇒ deny (D-22);** lethal-trifecta audit as a static promotion-time check (**v2 — v1 has no promotion time, so the audit runs per session**); in-band defenses plateau at 95% (a failing appsec grade) and out-of-band ones are static-benchmark-only after adaptive attacks broke twelve in-band defenses at >90%; deny rules resolve before any permissive mode; Codex Auto-review 9,280/720/7 and ~200× fewer human stops, and why it is sandbox-only; approvals display the **resolved** action, not the model's summary; **network egress specified in five terms (host *and* port, addresses pinned not re-resolved, DNS denied or proxied, loopback/RFC 1918/metadata denied even on an allowlisted host, ~~enforced at the host~~ *enforced at one mandatory egress proxy every outbound byte traverses*) — and an interception point is *not* an egress control, because its visibility ends at the argv of any command it allows (C-17, closed by OD-12)**; **the proxy resolves that rather than only naming it, so v1's shell executes and nothing classifies a shell command for effect; TLS interception rejected for v1 in favour of re-origination from a cleartext proxy endpoint, which works only because there is one destination** | `01 §8`; `08 §3.5`, **`08 §8.1` item 4**; **`.specify/memory/constitution.md` Principle IV bullets 1–2 (v1.2.0)**; **`plan.md` OD-12, OD-13** |
| [`credential-and-env-injection`](credential-and-env-injection/SKILL.md) (261 lines) | Get secrets to generated tools without any reaching the model | Two physically separate credential planes (model plane reversible, resource plane often not); `credential_ref` enums resolved by a broker outside the sandbox; redaction seam **before** compaction and persistence; env vars disqualified *here specifically* because the agent has shell by design; resource-plane creds unreachable from an agent shell; `authorization: UNRESOLVED` default because static analysis structurally strips authz; **what self-hosted-first (OD-08) discharges — custody and cross-tenant blast radius — against the two rules it makes harder, since co-location is now the default topology**; **Rule 3 is *unmet by v1* and its allowlist needs five terms rather than one, and under self-hosting we specify the policy while the customer instantiates it (C-17)**; **four of those terms are constitutional text at v1.2.0 and the fifth is now *enforced at a mandatory proxy outside the sandbox*, whose consequence is that the sandbox needs no resolver at all (OD-12, OD-13)** | `08 §1, §3.4, §4, §8.1`; **`plan.md` OD-08, OD-12, OD-13; `14` D-20, C-17, U-44** |
| [`integration-surface-design`](integration-surface-design/SKILL.md) (161 lines) | Design the HTTP/SSE and embeddable-iframe delivery surfaces | HTTP/SSE and iframe are different product **tiers**, not one surface with a flag; the per-capability tier table; removing shell beats sandboxing harder (a microVM does not bound wrong-authority use of a legitimate data path); anonymous sessions have no subject token so RFC 8693 has nothing to scope down to; response rendering is itself egress; cost caps as a mandatory control; **the iframe's "not yet" is now an owner decision (OD-08 defers it with the hosted tier) and the surviving v1 obligation is not to foreclose it** | `08 §3.2, §5`; `07 §3.4, §6`; **`plan.md` OD-08; `14` D-20, D-08, O-05** |
| [`harness-selection`](harness-selection/SKILL.md) (190 lines) | Choose or evaluate an agent harness for the product and for emitted stacks | Adopt a thin substrate, build the harness — this product *is* a harness generator; the dependency test is *does it see prompts and tokens*; ~~ADK + Claude Agent SDK split~~ **no framework at all for v1 (OD-15, 2026-08-03 — three of OD-01's four grounds lost their subject against a one-agent design, and the provider limb was measured non-compliant), with the Claude Agent SDK still an opt-in second path** and its honest costs (two session systems, two permission models, ~~two deprecation calendars~~ one) **plus the cost OD-15 buys them with: nine capabilities moved to build with no estimate anywhere (U-48)**; AutoGen and Semantic Kernel in maintenance mode; CMA spike-only (no Bedrock/Vertex, no internal-endpoint reach); the Claude Agent SDK license resolved as *MIT wrapper + proprietary bundled CLI*, so emitted packs declare it as a peer dependency and never vendor it | `02 §2, §6`; `06 §3, §7`; `13 §4, §7` |
| [`experiment-design`](experiment-design/SKILL.md) (192 lines) | Design spikes and evals that can actually falsify a claim | No LLM judge in the primary success path (AUROC 0.18–0.30, anti-correlated on false success); programmatically verifiable outcomes against a privately-seeded fixture; the ceiling test (ideal−baseline = value of the idea, ideal−generated = quality of the synthesizer); harness held fixed because it swings 10–20 points; the budget-matched single-agent control; kill criteria pre-registered as "stop" — **and E8's rows as the case where a well-formed criterion never evaluated at all** | `11 §3, §4, §7, §9`; **`plan.md` OD-14; finding `015`** |
| [`spec-authoring`](spec-authoring/SKILL.md) (155 lines) | Drive Spec Kit and hold a spec to the constitution | Hyphen not dot (`/speckit-specify`); the full phase sequence plus `checklist` / `converge` / `taskstoissues`; one feature per invocation so the product must be sliced; artifact locations; the four non-negotiable principles (contract-derived verification, topology-encodes-protocol, structural safety boundaries, test-first with fixture repos). **Human-invoked: sets `disable-model-invocation: true`** | `docs/spec-kit-workflow.md`; `.specify/memory/constitution.md` |

## Planned — blocked on research still in flight

None. The research corpus is complete and every skill that was blocked on it has been written.

## Deliberately deferred (not blocked — a judgment call)

| Candidate | Why deferred |
|---|---|
| `agent-evaluation-and-flywheel` | Fully grounded in `04 §2–§3`, but the load-bearing rules an agent needs at decision time (verify the world not the last message; never let a judge decide "did it succeed"; typed terminals; held-out set) are already in `contract-derived-verification`. A separate skill would mostly restate it. Split it out only if the eval tooling and flywheel automation become real work in this repo. |
| `memory-architecture` | **Superseded** by `knowledge-graph-memory`, which now carries tier assignment, the promotion bar, filesystem-vs-vector, and memory hygiene/poisoning. `context-engineering` keeps the working-tier budget. |
| `model-selection` | `01 §9` is real, but model tables go stale fast and the create-skill guide warns against time-sensitive content. Revisit if per-role routing becomes a code-level concern. |
| `planning-patterns` | `01 §6` plus `03 §7` reduce to two rules already carried by the two control-flow skills: plan–execute–replan is not worth it under ~5–8 steps, and a critic without an external signal degrades output. |
