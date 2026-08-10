# 13 — Claude Managed Agents: Does Anthropic's Hosted Runtime Replace the Harness?

**Last researched: 2026-08-02**

---

## TL;DR — Key takeaways

> 1. **It is real, it is documented, and it is beta.** Claude Managed Agents (CMA) is Anthropic's hosted agent harness — agent config, sandbox, session state, tool execution, and the loop itself run on Anthropic's infrastructure behind `POST /v1/agents`, `/v1/environments`, `/v1/sessions`. Every endpoint requires the `managed-agents-2026-04-01` beta header, and the docs say plainly *"Claude Managed Agents is in beta … Behaviors may be refined between releases"* ([overview](https://platform.claude.com/docs/en/managed-agents/overview)). Launched **2026-04-08** in public beta; enabled by default on all API accounts.
> 2. **BYO-LLM is the disqualifying finding, and it is unambiguous.** Anthropic's own pricing page lists "Cloud platform pricing" as a modifier that does **not** apply to CMA sessions, reason given: *"Not available on partner-operated cloud platforms"* ([pricing](https://platform.claude.com/docs/en/about-claude/pricing)). A customer's **Bedrock or Vertex account cannot run CMA sessions.** Only the direct Claude API and Anthropic-operated Claude Platform on AWS. Customers who bring an Anthropic org key are fine; every other credential story this product promised is not.
> 3. **A managed cloud sandbox cannot reach a customer's internal HTTP endpoint.** Anthropic's own cookbook states the rule: *"if the service is reachable over the public internet with a bearer token, an MCP toolset will work. If it's only reachable from inside your own network, use a custom tool instead"* (`CMA_operate_in_production.ipynb` cell 2). Since synthesized tools invoke the target app over its external interface, this is load-bearing. There are three workarounds and all three cost something — §4.3.
> 4. **Self-hosted sandboxes are the genuinely surprising find and they change the shape of the answer.** `config: {"type": "self_hosted"}` moves tool execution onto your infrastructure while orchestration stays at Anthropic; a worker polls with an *environment key*, not your org API key ([self-hosted sandboxes](https://platform.claude.com/docs/en/managed-agents/self-hosted-sandboxes)). Public beta as of the [2026-05 update](https://claude.com/blog/claude-managed-agents-updates). This is the only configuration in which the network-reachability problem dissolves.
> 5. **The sibling claim that CMA covers "a large share of the infrastructure this product needs" does not survive the matrix.** It covers **4 of 13** needs outright. It does not provide HTTP/SSE serving to *your* end customer, graph orchestration, per-tenant isolation as a primitive, budget enforcement, or dynamic tool registration at the shape this product needs — §3.
> 6. **Session state is stored server-side at Anthropic and is not ZDR- or HIPAA-BAA-eligible.** *"Managed Agents is not currently eligible for Zero Data Retention or HIPAA Business Associate Agreement (BAA) coverage"* ([overview](https://platform.claude.com/docs/en/managed-agents/overview)). Self-hosting the sandbox does not fix this — the event log, conversation history, and outputs still persist on Anthropic's side.
> 7. **Its multi-agent story is the same hub-and-spoke weakness as the Claude Agent SDK, not a graph.** `multiagent: {type: "coordinator", agents: [...]}` gives a coordinator plus a roster of 1–20 specialists; roster agents *"cannot themselves have"* subagents ([API ref](https://platform.claude.com/docs/en/api/beta/agents)). One level, model-discretion routing, no typed edges, no join/fan-in. Everything `06-examples-inventory.md` §7 says about the Claude SDK's weakest dimension applies verbatim.
> 8. **For `function2agent`:** **do not adopt CMA as the primary runtime;** ~~keep the ADK + Claude Agent SDK recommendation~~ — **superseded 2026-08-03 by `specs/001-discovery-validation/plan.md` OD-15: v1 runs on no agent framework at all, with the Claude Agent SDK as an opt-in second executor (OD-02). The *do not adopt CMA* half is unchanged and rests on facts about CMA, not on what replaces it.** But **do use it for the validation spike** — it collapses a week of sandbox plumbing into an afternoon and the spike code is disposable. And **never emit a generated customer stack with a hard CMA dependency**: it fails the `02-agent-harnesses.md` test (it sees prompts *and* tokens *and* owns the loop), it is beta, and it is single-vendor.

---

## Table of contents

1. [What Claude Managed Agents actually is](#1-what-claude-managed-agents-actually-is)
2. [What the vendored cookbooks demonstrate](#2-what-the-vendored-cookbooks-demonstrate)
3. [Infrastructure coverage matrix — testing the "large share" hypothesis](#3-infrastructure-coverage-matrix--testing-the-large-share-hypothesis)
4. [The blocking questions](#4-the-blocking-questions)
5. [Impact on the harness recommendation](#5-impact-on-the-harness-recommendation)
6. [Risk assessment](#6-risk-assessment)
7. [Relevance to `function2agent` — recommendation and trigger conditions](#7-relevance-to-function2agent--recommendation-and-trigger-conditions)
8. [Open questions and things I could not verify](#8-open-questions-and-things-i-could-not-verify)
9. [Sources](#9-sources)

---

## 1. What Claude Managed Agents actually is

**Documented capability.** CMA is a REST API on `api.anthropic.com` built around four primitives ([overview](https://platform.claude.com/docs/en/managed-agents/overview)):

| Primitive | ID prefix | What it holds |
|---|---|---|
| **Agent** | `agent_` | Model, system prompt, tools, MCP servers, skills, `multiagent` roster. Versioned and archivable. |
| **Environment** | `env_` | Where sessions run: `{"type": "cloud"}` (Anthropic sandbox) or `{"type": "self_hosted"}` (your worker). Carries `networking`, `packages`. |
| **Session** | `sesn_` | A running instance: persistent filesystem + persistent conversation history + mounted `resources` + `vault_ids`. |
| **Event** | — | The append-only log. `user.*`, `agent.*`, `session.*`, `span.*`, `system.*`, plus stream-only `event_delta`. |

Secondary primitives: `vault_` (per-end-user credential containers), `depl_` / `drun_` (cron-scheduled deployments), memory stores (separate `agent-memory-2026-07-22` beta header), and Outcomes (a server-side grade-and-revise loop).

### 1.1 What "managed" concretely means

The single most important sentence in the docs, and the one that decides the build-vs-adopt question:

> *"Instead of building your own agent loop, tool execution, and runtime, you get a fully managed environment where Claude can read files, run commands, browse the web, and run code securely. The harness supports built-in prompt caching, compaction, and other performance optimizations."* — [overview](https://platform.claude.com/docs/en/managed-agents/overview)

**Anthropic runs:** the agent loop (model call → tool selection → tool dispatch → continue), context compaction (`agent.thread_context_compacted` is an *event you observe*, not a policy you set), prompt caching, the event log and its durability, session status/lifecycle state machine, retry-on-transient-error (`session.status_rescheduled`), multiagent thread scheduling, and — in `cloud` mode — the container itself.

**You run:** your application. You POST `user.message` events and consume SSE. Plus, optionally: a custom-tool responder (your process executes the tool and POSTs `user.custom_tool_result`), a webhook receiver, and in `self_hosted` mode the sandbox worker.

**You do not control:** the loop's structure. There is no "run this node, then that node." There is no place to insert a deterministic step between two model turns. This is the same architectural constraint `06-examples-inventory.md` §4 identifies for the Claude Agent SDK — *"the SDK's core value is a process boundary to a closed-source agent loop … you cannot restructure the loop"* — except here the boundary is an HTTP call instead of a subprocess.

### 1.2 Relationship to the rest of Anthropic's surface

*Documented, with one inference marked.*

- **vs. Messages API.** Anthropic's own table: Messages is *"Direct model prompting access … best for custom agent loops and fine-grained control"*; CMA is *"Pre-built, configurable agent harness that runs in managed infrastructure … best for long-running tasks and asynchronous work"* ([overview](https://platform.claude.com/docs/en/managed-agents/overview)). CMA is not built *on* the public Messages API from your side — you never send a `messages` array.
- **vs. Claude Agent SDK.** The SDK is a library you run in your process that drives Claude Code's harness locally. CMA is the same *category* of thing hoisted into Anthropic's cloud. **Inference:** they are alternatives, not layers — the cookbooks never import `claude-agent-sdk`; they use `anthropic>=0.109.0` and `client.beta.*`.
- **vs. Claude Code.** Explicitly firewalled by contract. The branding guidelines *forbid* calling a CMA-powered product "Claude Code" or "Claude Code Agent," or using *"Claude Code-branded ASCII art or visual elements that mimic Claude Code"* ([reference](https://platform.claude.com/docs/en/managed-agents/reference)). Note this: a product built on CMA is contractually constrained in how it may market itself.
- **Platform availability.** Direct Claude API and Claude Platform on AWS (Anthropic-operated) only ([API overview](https://platform.claude.com/docs/en/api/overview)). **Not** Bedrock, **not** Vertex, **not** Microsoft Foundry. See §4.1.

### 1.3 Maturity — verified

The sibling doc's "beta or pre-1.0" report is **correct and understated**. Three distinct maturity tiers exist inside one product:

| Tier | Features | Status |
|---|---|---|
| Public beta, on by default | Agents, environments, sessions, events, cloud sandboxes, vaults, deployments | `managed-agents-2026-04-01` header; *"enabled by default for all API accounts"* |
| Public beta, opt-in infra | **Self-hosted sandboxes** | Public beta per the [2026-05 blog](https://claude.com/blog/claude-managed-agents-updates); the cookbook's own guide says *"you were already gated in by us"* (`self_hosted_sandboxes/docs/usage-guide.md:16`) |
| **Research preview** | **MCP tunnels**, **dreaming** | *"Request access"*; tunnels are *"provided 'as-is' without any uptime, support, or continuity commitment"* and *"Anthropic may modify or discontinue MCP tunnels at any time"* ([MCP tunnels](https://platform.claude.com/docs/en/agents-and-tools/mcp-tunnels/overview)) |

The two features this product would most need — self-hosted execution and private-network reachability — sit in the two *less* mature tiers. That is not a coincidence; it is where the hard problems are.

---

## 2. What the vendored cookbooks demonstrate

Read-only from `examples/claude-cookbooks/managed_agents/`. Fifteen notebooks plus six self-hosted-sandbox reference implementations. The three flagged as relevant are the three closest to this product's use cases, and they are worth reading precisely because they *are* the use cases.

### 2.1 `CMA_explore_unfamiliar_codebase.ipynb` — Class A, agent-on-codebase

This is `function2agent`'s Class A scenario as a 14-cell notebook.

**API surface (cell 5):**

```python
agent = client.beta.agents.create(
    name="cookbook-explore", model=MODEL,
    system="You are onboarding to an unfamiliar codebase. Explore before answering...",
    tools=[{"type": "agent_toolset_20260401",
            "default_config": {"enabled": True,
                               "permission_policy": {"type": "always_allow"}}}])
env = client.beta.environments.create(
    name="cookbook-explore-env",
    config={"type": "cloud", "networking": {"type": "limited"}})
session = client.beta.sessions.create(
    environment_id=env.id,
    agent={"type": "agent", "id": agent.id, "version": agent.version},
    resources=[{"type": "file", "file_id": fixture_zip.id, "mount_path": "repo.zip"}])
```

Three objects, three calls. Compare against the ADK path in `06-examples-inventory.md` §3 — this is dramatically less code, and that is the honest case for CMA.

**What it demonstrates.** (a) `agent_toolset_20260401` is a single opaque toolset handle — `bash`, `read`, `write`, `edit`, `glob`, `grep` arrive as one line. (b) `permission_policy` is a first-class field on the toolset, with `always_allow` as one option; the gate notebook shows the confirmation path. (c) `sessions.resources.add` / `.list` / `.delete` (cell 11) mounts files into a **running** session — this is real mid-session context injection, and it is better than what ADK offers out of the box. (d) State persists trivially: cell 9 is `cat /tmp/NOTES.md` sent as a second `user.message`, and the file is still there.

**Limits visible in the code.** Everything is filesystem-and-shell. There is no structured artifact type, no typed hand-off — the "artifact" is a path in a container. The stale-`ARCHITECTURE.md` trap the notebook plants is exactly the drift problem `function2agent` has to solve, and CMA offers no mechanism for it; it is handled by a sentence in the system prompt.

### 2.2 `CMA_orchestrate_issue_to_pr.ipynb` — the durable-session proof

**Environment config (cell 5)** is the interesting cell:

```python
config={"type": "cloud",
        "networking": {"type": "limited", "allow_package_managers": True},
        "packages": {"pip": ["pytest"]}}
```

Package pre-installation is declarative on the environment. Network access is off by default in this notebook's posture and `allow_package_managers` is a *separate boolean* from host allowlisting — a well-designed distinction.

**Orchestration pattern.** There isn't one, and that is the finding. Cell 7 sends **a single `user.message`** and the agent drives the entire issue → fix → PR → CI-failure → recover → review-comment → recover → merge chain autonomously. The notebook's framing: *"State flows through the chain as issue body → file paths → fix diff → PR number → CI output → review comment → final merge."* All of that state lives in the container filesystem and the conversation history. **There is no graph.** The multi-step structure is entirely emergent from the model.

For `function2agent` this cuts both ways. It proves a long autonomous chain works. It also proves CMA offers nothing for *enforcing* that a step runs — which `graph-vs-loop-decision` treats as the whole reason to reach for a graph.

**The `github_repository` resource (cell 10 sidebar)** is directly useful:

```python
resources=[{"type": "github_repository",
            "url": "https://github.com/anthropics/claude-cookbooks",
            "mount_path": "/workspace/cookbook",
            "authorization_token": GH_TOKEN,
            "checkout": {"type": "branch", "name": "main"}}]
```

Server-side clone at session creation. If `function2agent` ingests customer repos, this is one field instead of a clone subsystem. Note the token is passed **in the request body** on this path — contrast with vaults (§2.4), which exist because that pattern doesn't scale to end users.

### 2.3 `CMA_coordinate_specialist_team.ipynb` — the multiagent surface, and its ceiling

**The one field that matters (cell 11):**

```python
coordinator = client.beta.agents.create(
    name="Proposal Writer", model=MODEL, system="...",
    tools=[{"type": "agent_toolset_20260401"}],
    multiagent={"type": "coordinator",
                "agents": [prospect_researcher, case_study_picker, pricing_modeler]})
```

Roster entries are ordinary `agent_` IDs created the same way. Per-role tool scoping is real and is the notebook's stated point — the researcher gets `configs: [{"name": "web_search"}, {"name": "web_fetch"}]` only, the pricer gets no web access at all (cell 5). Subagents report via a `send_to_parent` convention; the coordinator observes `session.thread_created` and `agent.thread_message_received` (cell 13).

**Observed execution (cell 13 output)** — the coordinator parallelized correctly without being told to:

```
[spawn] prospect_researcher
[spawn] pricing_modeler
[report] prospect_researcher returned
[spawn] case_study_picker      ← waited for the researcher's priorities
[report] pricing_modeler returned
[report] case_study_picker returned
```

**The ceiling, and it is a hard one.** From the API reference: roster entries *"reference distinct agents"* and *"cannot themselves have"* subagents ([API ref](https://platform.claude.com/docs/en/api/beta/agents)); the roster is 1–20 entries. So:

- **One level of hierarchy.** No sub-sub-agents. A decomposed codebase with nested service boundaries cannot be mirrored structurally.
- **Model-discretion routing.** The ordering above emerged from the coordinator's system prompt, not from declared edges. Reruns can differ.
- **No join semantics.** Nothing corresponds to ADK's `JoinNode`. Fan-in is the coordinator noticing reports arrived.
- **Context isolation is real** and is the genuine win — the librarian's hundreds of files stay out of the coordinator's window (cell 18). This is the `context-engineering` subagent-isolation pattern, provided as a primitive.

This is functionally the Claude Agent SDK's `Task` tool with a declared roster and better observability. `06-examples-inventory.md` §7 rates that dimension `○` against ADK's `●` and calls it "the SDK's weakest dimension against the vision." **That rating carries over unchanged.**

**Inconsistency worth flagging:** this notebook uses `config={"type": "anthropic_cloud", ...}` while the other two and the docs use `{"type": "cloud", ...}`. Beta churn in the type discriminator, visible inside a single cookbook directory.

### 2.4 Three supporting notebooks that answer questions the flagged three don't

**`CMA_operate_in_production.ipynb`** — the most decision-relevant notebook in the directory.

- **Vaults** (cells 4–8): `client.beta.vaults.create(display_name=..., metadata={"internal_user_id": "u_demo_001"})`, then `vaults.credentials.create(vault_id=..., auth={"type": "static_bearer", "mcp_server_url": ..., "token": ...})`, then `sessions.create(..., vault_ids=[vault.id])`. Anthropic resolves the credential at MCP-call time. *"The agent never sees the token itself."* Supports OAuth-with-refresh as well as static bearer.

  This is a genuinely good design and it is **partially aligned** with `08-auth-identity-and-secrets.md`'s broker model — the credential is resolved at the tool-call boundary and never enters the shell's environment. **But it inverts the custody conclusion.** `08` §-table lists "who custodies resource-plane secrets" and warns that holding many customers' production credentials makes you "a concentrated target." With vaults, *Anthropic* becomes that target. Whether that is better or worse is a customer-by-customer answer, but it is not the architecture `08` recommended, and it is not ZDR-eligible.

- **The public-internet rule** (cell 2), verbatim and load-bearing:

  > *"Rule of thumb: if the service is reachable over the public internet with a bearer token, an MCP toolset will work. If it's only reachable from inside your own network, use a custom tool instead."*

- **Webhooks** (cell 11): register in Console → get a `whsec_` secret → receive `session.status_idled` → inspect events → POST the result back. HMAC-SHA256 verification. This is how you do HITL without holding a connection. It is *your* server doing the serving, which is the point — see §3.

**`CMA_gate_human_in_the_loop.ipynb`** — the custom-tool round-trip: agent emits `agent.custom_tool_use`, session goes `requires_action`-idle, your code executes and POSTs `user.custom_tool_result`. This is the escape hatch for everything CMA can't reach, and it is also the **only** way a cloud-sandbox session touches a private endpoint.

**`self_hosted_sandboxes/`** — six reference implementations (Docker, Cloudflare Containers, Cloudflare Workers, Modal, Daytona, Vercel) against one contract (`self_hosted_sandboxes/README.md`):

1. Receive `session.status_run_started` webhook, verified with `client.beta.webhooks.unwrap()`.
2. Drain the environment work queue (so one delivery recovers earlier misses).
3. Launch a per-session sandbox running the tool runner, heartbeat the lease, POST `tool_result`s back.

And the credential property that matters:

> *"No org API key reaches the runner — the sandbox authenticates with the **environment key**, the single credential for both the control plane and the per-session calls."*

The worker is `ant beta:worker poll --environment-id ... --workdir /workspace`, or embeddable as library code via `client.beta.environments.work.worker(...)`, with a customizable tool list (`usage-guide.md:224-256`). The guide is blunt about the isolation boundary: *"The worker executes shell and file operations directly on the host. Run it inside a container or other isolation boundary you control"* (`usage-guide.md:169`), and `--unrestricted-paths` *"is a guardrail for the file tools only, not a sandbox; it does not constrain bash"* ([reference](https://platform.claude.com/docs/en/managed-agents/reference)).

---

## 3. Infrastructure coverage matrix — testing the "large share" hypothesis

Legend: ● provides · ◐ partially provides · ○ does not provide.

| # | Infrastructure need | Cloud mode | Self-hosted mode | Evidence / what's missing |
|---|---|---|---|---|
| 1 | **Persistent sandboxed execution** | ● | ● | Ubuntu 22.04, x86_64, ≤8 GB RAM, ≤10 GB disk, 8 languages pre-installed ([cloud sandbox ref](https://platform.claude.com/docs/en/managed-agents/cloud-sandboxes-reference)). Self-hosted: whatever your image provides. **The single strongest thing CMA gives you.** |
| 2 | **Durable sessions across turns** | ● | ● | Filesystem + conversation history persist; `sessions.events.list` replays the full log; `session.status_rescheduled` auto-retries transients. Better than what you'd build in a sprint. |
| 3 | **Multi-agent coordination / subagent spawning** | ◐ | ◐ | `multiagent` coordinator, 1–20 roster, **one level**, model-discretion routing, no typed edges, no join. §2.3. Covers isolation; does not cover topology. |
| 4 | **Artifact storage & inter-agent passing** | ◐ | ◐ | Shared container filesystem + `/mnt/session/outputs/`; Files API for in/out. No typed artifact contract, no schema, no versioning. Comparable to the Claude SDK's `○`/ADK's `◐` in `06` §7. |
| 5 | **HTTP/SSE serving to *your* end customer** | ○ | ○ | CMA's SSE is **Anthropic → you**. Nothing serves *your* customer. You build the FastAPI/webhook layer regardless — the production notebook's cell 11 *is* you writing a server. **This is the need the current ADK recommendation exists to satisfy, and CMA does not touch it.** |
| 6 | **Graph / workflow orchestration** | ○ | ○ | No nodes, no edges, no routing, no join, no deterministic step insertion. The issue-to-PR chain is emergent, not declared (§2.2). Cannot enforce "this step always runs." |
| 7 | **Tool registration, incl. dynamically generated tools** | ◐ | ◐ | Three paths: `agent_toolset` (fixed six), `mcp_toolset` (public HTTP MCP), `custom_tool` (your JSON Schema, your executor). Max **128 tools**, 20 MCP servers, 20 skills. Custom tools work for generated tools — but every call round-trips through your process, so you are running the tool-execution path anyway. |
| 8 | **Permission / approval hooks** | ● | ● | `permission_policy` on the toolset (`always_allow` / confirm), `user.tool_confirmation` event, `requires_action` idle bounce, `session.status_idled` webhook. Genuinely good; better than rolling your own. |
| 9 | **Env var & credential injection** | ◐ | ● | Vaults resolve MCP credentials server-side, agent never sees the token (§2.4) — good, and aligned with `08`'s broker principle. But scoped to **MCP servers**; not a general secret-injection mechanism for arbitrary tools. Self-hosted: your worker, your secret plumbing, full control. |
| 10 | **Per-tenant isolation** | ◐ | ◐ | Sessions are isolated containers and vaults are per-end-user — real isolation at the session grain. But tenancy is *your* modeling problem: no tenant primitive, no per-tenant quota, rate limits are **per-organization** ([reference](https://platform.claude.com/docs/en/managed-agents/reference)), so one noisy tenant's session-create burst consumes another's headroom. |
| 11 | **Cost accounting & budget enforcement** | ◐ | ◐ | Accounting: good — `span.model_request_end` carries `model_usage` with token counts, per-thread, and `CMA_plan_big_execute_small.ipynb` meters cost per thread. Enforcement: **absent.** No per-session token cap, no spend ceiling, no kill-at-budget. Only org-level spend limits. You must observe the span stream and call `user.interrupt` yourself. |
| 12 | **Observability & tracing** | ● | ● | The event log *is* a trace: `span.model_request_start/end`, `session.thread_*`, full replay via `events.list`, Console UI, stream-only `event_delta` for live token streaming. Strong. |
| 13 | **Data residency / ZDR** | ○ | ○ | **Not eligible for ZDR or HIPAA BAA** ([overview](https://platform.claude.com/docs/en/managed-agents/overview)). Self-hosting the sandbox does **not** fix this — the event log persists at Anthropic either way. Deletion is available; non-retention is not. |

**Score: 4 full (1, 2, 8, 12), 6 partial, 3 absent in cloud mode.** Self-hosted upgrades #9 to full.

**Verdict on the hypothesis.** The sibling's claim that CMA is "a large share of the infrastructure this product needs" is **wrong as stated, and interestingly wrong.** What CMA covers is *the sandbox and the loop* — the part of the stack that is annoying but well-understood, and the part that is `02-agent-harnesses.md`'s "ordinary infrastructure you should not rebuild." What it does not cover is *serving, orchestration topology, tenancy, and budget* — the parts that are `function2agent`-shaped and that the ADK recommendation exists to solve.

Put differently: **CMA is a very good answer to a question this product has already mostly answered, and no answer at all to the questions it hasn't.** The overlap with the Claude Agent SDK's role in the current recommendation is nearly total; the overlap with ADK's role is nearly zero. That is the structural fact that decides §5.

---

## 4. The blocking questions

### 4.1 Pricing, and whether BYO-LLM survives it — **it does not, for Bedrock/Vertex**

**Documented, primary source.** Two SKUs ([pricing](https://platform.claude.com/docs/en/about-claude/pricing)):

| SKU | Rate | Metering |
|---|---|---|
| Tokens | Standard model rates; prompt-caching multipliers apply identically | All session tokens |
| Session runtime | **$0.08 per session-hour** | `running` status duration, to the millisecond |
| Web search inside a session | $10 / 1,000 searches | Standard rate |

Idle, `rescheduling`, and `terminated` time is free. Session runtime **replaces** Code Execution container-hour billing — no double charge. No batch discount, no fast-mode premium, no `inference_geo` data-residency multiplier.

**The runtime fee is a rounding error and should not drive the decision.** At $0.08/hr, a session burning Sonnet tokens for an hour spends several dollars on inference against 8 cents of runtime. Anyone arguing against CMA on the $0.08 line has the wrong objection.

**The disqualifying line is in the same table.** The list of Messages API modifiers that do not apply includes:

| Modifier | Anthropic's stated reason |
|---|---|
| Cloud platform pricing | **"Not available on partner-operated cloud platforms."** |

Cross-checked against [API overview](https://platform.claude.com/docs/en/api/overview), which lists CMA as available on the direct Claude API and Claude Platform on AWS (Anthropic-operated) — and lists Amazon Bedrock, Google Vertex, and Microsoft Foundry as separate platforms.

**Answer to the blocking question, composed against the product's BYO-credential premise:**

| Customer's model-plane credential | Works with CMA? | Consequence |
|---|---|---|
| Their own Anthropic API key | ✅ Yes | Clean. Tokens and runtime bill to *their* Anthropic org. You never touch their spend. This is the good case and it is the common case. |
| Their AWS Bedrock account | ❌ **No** | Documented as unavailable. A customer with a negotiated Bedrock commit, or an AWS-only procurement posture, cannot use CMA. |
| Their Google Vertex account | ❌ **No** | Same. |
| OpenAI / Google / xAI | ❌ **No** | Claude-only runtime by construction. |
| Anthropic-operated Claude Platform on AWS | ✅ Yes | Bills in Claude Consumption Units. Note this is *Anthropic operating on AWS*, not the customer's AWS account. |

**This is decisive and it is worth being precise about why.** BYO-LLM is not merely degraded — it is bifurcated. Customers whose model plane is an Anthropic key are fully served. Customers whose model plane is Bedrock or Vertex — which, for enterprises with existing AWS/GCP commitments, is the *majority* posture — cannot be served at all by a CMA-based runtime. You would be shipping a product whose runtime silently excludes a large, wealthy, and specifically-targeted segment. *Confidence: high — this is stated on Anthropic's pricing page, not inferred.*

### 4.2 Self-hosting and data residency — **execution yes, data no**

**Documented.** `config: {"type": "self_hosted"}` is a first-class environment type. Anthropic's own framing of the split ([self-hosted sandboxes](https://platform.claude.com/docs/en/managed-agents/self-hosted-sandboxes)):

> *"Self-hosted sandboxes keep the orchestration on Anthropic's side but move tool execution into infrastructure you control, so the agent's code, filesystem, and network egress never leave your environment."*

| Concern | Cloud | Self-hosted |
|---|---|---|
| Where code executes | Anthropic | **Yours** |
| Agent's filesystem | Anthropic | **Yours** |
| Network reach | Anthropic's egress controls | **Your network policy** |
| Model inference | Anthropic | Anthropic |
| Event log / conversation history / outputs | Anthropic | **Anthropic** |
| ZDR / HIPAA BAA eligible | No | **No** |

**The honest answer to "can it run in a customer's environment at all":** the *sandbox* can; the *runtime* cannot. Orchestration, the loop, and the durable event log stay at Anthropic unconditionally. For the prospective customer described in the prompt — one who "will not let a third-party hosted runtime reach their production database" — self-hosted sandboxes are a **complete answer to the reachability objection** and a **partial answer to the data objection**: their production data never transits Anthropic's *sandbox*, but any of it the agent reads into its context does transit Anthropic's *inference and event log*, and is retained.

For a customer with a hard ZDR requirement, CMA is out entirely, in any configuration. *Confidence: high; sourced to the overview page's explicit eligibility statement.*

### 4.3 Network egress and reachability — **the crux, three paths, all with costs**

The requirement is mandatory: synthesized tools invoke the target app over its external HTTP interface, and that interface is frequently internal-only.

**Cloud-mode egress controls** are outbound-only and host-based ([environments](https://platform.claude.com/docs/en/managed-agents/environments)):

| Mode | Behavior |
|---|---|
| `unrestricted` | Full outbound except a safety blocklist. **Default for API-created environments.** |
| `limited` | Only `allowed_hosts`; `allow_package_managers` and `allow_mcp_servers` are separate booleans. |

Note the default asymmetry: API-created environments default to `unrestricted`, Claude Studio-provisioned ones default to `limited`. For a product that generates environments programmatically, **`limited` with an explicit `allowed_hosts` must be the emitted default** — matching `08`'s posture that resource-plane reachability is deny-by-default.

**No VPC peering. No static egress IPs. No private connectivity in cloud mode.** I searched for all three and found nothing; the docs say explicitly you *"don't need to … allowlist Anthropic's IP ranges on your origin"* when using tunnels, which strongly implies stable published egress IPs are not the offered mechanism. *Confidence: medium-high — absence of evidence in the documented surface, not a stated denial.*

**The three paths, ranked:**

| Path | How it works | Cost |
|---|---|---|
| **1. Self-hosted sandbox** | Worker runs in your (or the customer's) VPC. Tool calls originate from inside the perimeter. | Best fit by a wide margin. You operate the worker fleet — which is most of the infra CMA was supposed to save you. §5(c). |
| **2. MCP tunnel** | `cloudflared` dials outbound on port 7844 to Anthropic's edge; MCP requests flow back down. mTLS, no inbound ports ([concepts](https://platform.claude.com/docs/en/agents-and-tools/mcp-tunnels/concepts)). | **Research preview**, access-gated, *"as-is,"* depends on Cloudflare with *"no availability commitment,"* and Anthropic *"may modify or discontinue"* it. Requires the customer to deploy a gateway. **I would not build a product's mandatory data path on this.** |
| **3. Custom tool round-trip** | Agent emits `agent.custom_tool_use`; your server calls the internal endpoint; POSTs `user.custom_tool_result`. | Works today, no gating, and your server already exists. But you are now the tool-execution path — latency on every call, and you've re-taken the job CMA was adopted to do. |

**Answer:** a managed cloud sandbox **cannot** reach a customer's internal endpoint directly. It can reach it via a research-preview tunnel or via a round-trip through your infrastructure. Only the self-hosted sandbox makes it a non-problem.

### 4.4 Availability, quotas, regional coverage

| Dimension | Finding |
|---|---|
| Availability | Public beta since **2026-04-08**, *"enabled by default for all API accounts."* Named production users reported (Notion, Rakuten, Sentry) — [secondary](https://medium.com/@tentenco/anthropic-managed-agents-what-it-is-what-it-kills-and-why-the-timing-matters-0f70c1822f93), not verified against Anthropic. |
| Rate limits | Create endpoints **300 RPM**, read endpoints **1,200 RPM**, per organization ([reference](https://platform.claude.com/docs/en/managed-agents/reference)). Inference inside sessions draws from your standard ITPM/OTPM. Org spend limits apply. |
| Concurrent sessions | **Could not verify.** No documented cap on simultaneous running sessions. The [anthropics/skills reference](https://github.com/anthropics/skills/blob/main/skills/claude-api/shared/managed-agents-api-reference.md) shows an Environments row at 60 RPM / **max concurrent 5**, which contradicts the docs page's numbers and whose "concurrent" scope is ambiguous (concurrent requests vs. concurrent environments). Treat as unresolved — and as a **must-measure before any capacity commitment**, since 5 concurrent environments would be fatal for per-tenant environment isolation. |
| Regional coverage | **Could not verify.** No region selector on `environments.create`. The pricing page notes `inference_geo` (the Messages API data-residency field) does not apply to CMA, which suggests **no regional pinning exists for sessions.** For an EU-data-residency customer this is likely disqualifying. |
| Sandbox ceiling | 8 GB RAM, 10 GB disk, x86_64 only ([cloud sandbox ref](https://platform.claude.com/docs/en/managed-agents/cloud-sandboxes-reference)). **10 GB is a real constraint** for a product that clones large monorepos and runs `codegraph` over them. No documented way to raise it in cloud mode. |
| Object ceilings | 128 tools, 20 MCP servers, 20 skills, 20 multiagent roster entries, outcome `max_iterations` ≤ 20. |

The **128-tool ceiling deserves attention** given the product's core IP. `06`'s finding is that mechanical 1:1 function→tool conversion is an anti-pattern and the differentiator is consolidation. A hard 128 cap is, awkwardly, *aligned* with that thesis — it forces consolidation. But it is a hard cap on a generated artifact's tool surface, set by a vendor, and a large decomposed monolith could exceed it before consolidation.

### 4.5 Model lock-in

**Total.** Every model field takes a Claude identifier. There is no provider abstraction, and there is no reason to expect one.

Weighed against `05-frontier-lab-agent-definitions.md`'s finding of a **>2× cost spread and a >15-point capability spread across providers on the same task class**, with the concrete routing prescription that "a repo-level refactor should go to Fable 5; a long terminal loop to GPT-5.6 Sol; a high-volume cheap agentic pass to Grok 4.5," and the observed spread of $2.49/task (Grok 4.5) vs $11.80/task (Fable 5) at 76 vs 77 on the Coding Agent Index — **adopting CMA as the runtime forecloses the routing economics that `05` recommendation #3 exists to preserve.**

CMA does offer *within-Claude* routing: per-roster-agent model selection (§2.3), and `CMA_watch_subagents_live.ipynb` demonstrates per-agent `effort` as a cost lever. That is a real, useful subset. It is one vendor's slice of a spread that `05` measured across vendors.

Against the two-tier provider abstraction: CMA is **not** a tier-one primitive. It is not a normalized turn/message/tool interface with opaque continuation state — it is an entire loop. Per `provider-abstraction`, opaque continuation state must be a first-class type; here the continuation state is a `sesn_` ID living on Anthropic's servers. It is not portable, not inspectable in a provider-neutral form, and not reconstructible elsewhere. **CMA is a tier-two adapter target at best, and more accurately it is a peer of the whole abstraction rather than something that fits inside it.**

---

## 5. Impact on the harness recommendation

### 5.1 The three architectures

| Dimension | **(a) ADK 2.6.1 + Claude Agent SDK** *(current)* | **(b) CMA as primary runtime** | **(c) Hybrid: CMA self-hosted sandbox for execution; ADK for orchestration + serving** |
|---|---|---|---|
| Sandboxed execution | You build (containers/GKE executors) | ● Managed, zero work | ● CMA worker in your VPC |
| Durable sessions | ● ADK session services + Claude SDK `SessionStore` (Postgres/Redis/S3 + conformance suite) | ● Managed | ◐ Two session stores to reconcile — ADK's and CMA's |
| Graph orchestration | ● `Workflow`/`Graph`/`Edge`/`JoinNode`, graph-as-data (Pydantic) | ○ None | ● ADK retains it |
| Dynamic node spawning | ● `ctx.run_node()` | ◐ Coordinator, model-discretion, one level | ● ADK |
| HTTP/SSE serving to your customer | ● `get_fast_api_app()`, `POST /run_sse` | ○ You build it anyway | ● ADK |
| Tools from an app's HTTP surface | ● `OpenAPIToolset` → `RestApiTool` | ◐ MCP or custom tools, hand-built | ● ADK |
| Coding tool suite | ● Claude SDK (Claude Code parity) | ● `agent_toolset_20260401` | ● CMA toolset, extensible in the worker |
| Reach customer's internal endpoints | ● Your process, your network | ○ Tunnel (research preview) or round-trip | ● Worker is inside the perimeter |
| BYO-LLM | ● Any provider, any of Bedrock/Vertex | ○ Claude only; **no Bedrock/Vertex** | ○ Same — inference is still Anthropic's |
| Provider routing per `05` | ● Preserved | ○ Foreclosed | ○ Foreclosed |
| ZDR-capable | ● Yes (your infra, your retention) | ○ No | ○ No |
| Per-tenant isolation | ● You design it | ◐ Session-grain; org-level rate limits | ◐ Same, plus your worker isolation |
| Budget enforcement | ● You build it, and can | ○ Observe-and-interrupt only | ◐ Interrupt from your orchestrator |
| Ops burden | Highest | Lowest | **High** — you run the worker fleet *and* the ADK layer *and* reconcile two state models |
| Beta exposure | ADK 2.6.1 churn (`06` §3 flags deprecations) | Beta API + research-preview deps | Beta API on the execution path |
| Time to first working spike | Slow (~a week of plumbing) | **Fast (an afternoon)** | Slow |
| Fails `02`'s "sees prompts and tokens" test | Claude SDK: borderline. ADK: no (execution path). | **Yes, decisively** | **Yes** — the loop is still Anthropic's |

### 5.2 Resolving the `02-agent-harnesses.md` test

`02` §7's rule, verbatim:

> *"Avoid third-party abstractions in the model-facing path. Adopt mature third-party infrastructure in the execution path. The test is whether the dependency sees prompts and tokens. If it does, it will churn with the model APIs and you should own it. If it does not, it is ordinary infrastructure and you should not rebuild it."*

The prompt correctly identifies CMA as awkward for this test because it sits in both paths. I don't think it is actually awkward once you decompose it — the test resolves cleanly, and the resolution is instructive:

**Decompose CMA into its two halves and apply the test to each.**

| Half | Sees prompts and tokens? | Verdict under `02` |
|---|---|---|
| **The sandbox** — container, filesystem, `bash`/`read`/`write`/`edit`/`glob`/`grep` execution, lease management, package pre-install | **No.** It executes a tool call and returns bytes. It never sees a system prompt, never counts a token, never decides what to call next. | **Ordinary infrastructure. Adopt.** |
| **The harness** — agent loop, tool *selection*, prompt caching, context compaction, multiagent thread scheduling, the durable event log | **Yes, entirely.** It owns the system prompt, decides tool dispatch, and compacts context on a policy you cannot set. | **Model-facing framework. Do not adopt.** |

CMA sells these as a bundle. `02`'s rule says adopt one and refuse the other.

**And Anthropic themselves ship the unbundling.** `config: {"type": "self_hosted"}` is exactly the seam — it detaches the sandbox from the harness. The problem is that it detaches the wrong half. Self-hosting gives you the *execution-path* half to run yourself (the half `02` says you *should* adopt) while keeping the *model-facing* half at Anthropic (the half `02` says you should own). **The product's unbundling runs precisely opposite to the direction `02`'s rule wants.**

That is the cleanest single statement of why CMA doesn't fit: *the seam is in the right place and pointed the wrong way.*

The one wrinkle worth conceding: `02` §7's own trigger condition says *"if the Claude Agent SDK reaches 1.0 with a clean OSS license, 'build the harness' weakens considerably."* CMA is the *opposite* movement — the harness getting further from you, not closer, and hosted rather than open. If anything CMA **strengthens** `02`'s verdict by demonstrating what the alternative concretely costs.

### 5.3 Recommendation

~~**Keep the current recommendation: ADK 2.6.1 as the outer graph-loop runtime and HTTP/SSE serving layer, with the Claude Agent SDK as the executor inside coding-capable nodes.**~~ **CMA does not overturn it.**

> **Superseded for v1 2026-08-03 — `specs/001-discovery-validation/plan.md` OD-15: v1 runs on no agent framework, and the orchestrator slot this section reasons about does not exist for a single-agent, single-loop v1.** **This section's actual argument is unaffected and its conclusion about CMA is unchanged**: CMA competes for the *executor* slot, it is still spike-only, and the two disqualifying facts in §5 are properties of CMA rather than of whatever sits above it. What lapses is the comparator — the thing CMA is being declined *in favour of* is now our own runtime with the Claude Agent SDK as an opt-in path (OD-02), not ADK.

The reasoning in one paragraph: CMA competes for the *executor* slot, not the *orchestrator* slot. `06` §7 rates the Claude Agent SDK `●` on the coding-tool surface and `○` on graph orchestration, HTTP/SSE serving, and typed shared state — and CMA scores identically on every one of those dimensions while *additionally* forfeiting BYO-Bedrock/Vertex, provider routing, ZDR, and self-contained deployability. It is a strictly worse executor than the Claude Agent SDK for this product's constraints, differing only in that it is easier to start with. Architecture (b) is eliminated.

Architecture (c) is more interesting and I want to be fair to it, because self-hosted sandboxes genuinely solve the reachability problem. But it fails on arithmetic: you take on the worker fleet, the webhook receiver, the lease heartbeating, and the queue-draining logic — *and you still don't get the loop back, and you still can't use Bedrock.* You have paid most of the operational price of building it yourself while keeping all of the lock-in. If you are going to run compute in the customer's VPC anyway, run your own executor there and keep the loop.

**Where CMA does win, unambiguously: time-to-first-run.** Three API calls versus a week of container plumbing. That is not nothing, and it is the entire basis of the spike recommendation in §7.

---

## 6. Risk assessment

**Vendor lock-in — severe, and structurally worse than SDK lock-in.** With the Claude Agent SDK, lock-in is a library dependency in a process you control; a migration is a rewrite of the executor. With CMA, the durable state — sessions, event history, agent versions, vault credentials, memory stores — lives on Anthropic's servers behind opaque IDs. There is no documented export of a session's full state into a portable form, and no import. `provider-abstraction`'s requirement that opaque continuation state be a first-class *type you hold* is violated: you hold a `sesn_` string and Anthropic holds the state. A migration is not a rewrite; it is an abandonment of running work.

**Beta stability — high, and the field's churn makes it higher.** The type discriminator is already inconsistent inside one cookbook directory (`"cloud"` vs `"anthropic_cloud"`, §2.3). The toolset type is date-stamped `agent_toolset_20260401`, which is Anthropic telling you a `..._20261001` is coming. The self-hosted guide pins to exact SDK builds (`Python 0.103.0, TypeScript 0.97.0, ant CLI v1.9.0`) and ships a dedicated `upgrade-guide.md` — a strong tell that upgrades break. The Go SDK worker is literally `// TODO: pending a released Go SDK build`. `06` §3 already flags ADK 2.6.1's deprecation churn as a reason to wrap it behind a façade; CMA's churn is comparable and you cannot wrap an HTTP API's semantics as cheaply as a library's.

**What happens to generated customer stacks if CMA changes or is deprecated.** This is the risk that actually matters, because it is the one this product uniquely creates. A generated stack with a hard CMA dependency has these properties: it stops working if a beta header is retired; it stops working if the customer's org loses access; it cannot be run air-gapped, ever; it cannot be handed to a customer who wants to own it; and its *state* is not the customer's to take. Compare a generated stack that is a FastAPI app plus a tool module plus a graph definition — that one runs anywhere, forever, on any provider.

**Should a generated artifact ever have a hard dependency on CMA? No.** This is the strongest position in this document and I hold it without hedging. The product's value proposition is that it hands a customer a working multi-agent system over *their* codebase. An artifact that only runs against one vendor's beta API, cannot use that customer's existing Bedrock commit, cannot satisfy their ZDR requirement, cannot run in an air-gapped environment, and whose session state is held by a third party is not a deliverable — it is a tenancy in someone else's product wearing the customer's logo. The branding guidelines even constrain what you may call it.

The narrower question — may `function2agent`'s *own* control plane depend on CMA? — is more defensible but still a no, for the BYO-LLM reason in §4.1: your control plane would inherit the Bedrock/Vertex exclusion and pass it to every customer.

**Residual risk if you follow the §7 recommendation:** near zero. Spike code is disposable by definition; the cost of a CMA-based spike that gets thrown away is the days you didn't spend on container plumbing, which is a saving, not a risk. The only real hazard is **spike drift** — a spike that works becoming the thing you ship. Mitigate it explicitly: §7.3.

---

## 7. Relevance to `function2agent` — recommendation and trigger conditions

### 7.1 The verdict

**Do not adopt Claude Managed Agents as the runtime for `function2agent` or for anything it generates. Do use it for the validation spike.**

Three findings carry the decision, in order of weight:

1. **BYO-LLM is bifurcated, not degraded.** Customers on Bedrock or Vertex — the default posture for enterprises with cloud commitments, which is the segment that has internal HTTP endpoints worth wrapping in the first place — cannot use a CMA-based runtime at all ([pricing](https://platform.claude.com/docs/en/about-claude/pricing)). This alone is disqualifying for the generated artifact.
2. **CMA overlaps the executor, not the orchestrator.** It scores `○` on graph orchestration, `○` on HTTP/SSE serving to your customer, and `◐` on multi-agent topology — the exact three dimensions on which `06` §7 chose ADK. Adopting it would replace the half of the stack that is already solved and leave the half that isn't.
3. **The seam points the wrong way.** Under `02`'s test, the sandbox is adoptable execution-path infrastructure and the harness is a model-facing framework you must own. Self-hosted sandboxes unbundle exactly those two — and hand you the one you were supposed to adopt while keeping the one you were supposed to own (§5.2).

### 7.2 What the product should take from CMA anyway

Adoption is not the only way a competitor's design pays. Four things are worth copying, and copying them is free:

1. **Vaults as the resource-plane pattern.** `08-auth-identity-and-secrets.md` argues for a broker resolving `credential_ref` handles at the tool-call boundary so the model cannot introspect them. Vaults are that design, shipped, with a per-end-user container and metadata for mapping back to your user table. **Copy the shape; keep custody yourself** — `08`'s custody analysis stands, and vaults move the concentrated-target risk to Anthropic rather than eliminating it.
2. **`allowed_hosts` deny-by-default as the emitted environment shape.** Note that CMA's API-created default is `unrestricted`. `function2agent` should emit the inverse: `limited` with an explicit host allowlist derived from `codegraph`'s route manifest. The generated agent's egress allowlist is *derivable from static analysis* — that is a differentiator and it falls out of the product's premise for free. **Annotated 2026-08-03, and this is the fourth independent site in the corpus asking for the same control that v1 does not implement** (`14-architecture-synthesis.md` **C-17**, joining constitution Principle IV bullet 1, `08-auth-identity-and-secrets.md` §8.1 item 4, and `07-product-vision.md` §3.2.5 item 5). **Two corrections the pivot forces on this item, in opposite directions.** The *differentiator* claim goes to v2 with synthesis — deriving a per-tool egress allowlist from imports and call sites needs a synthesized tool to attach it to (`plan.md` OD-09, D-22). **The requirement gets cheaper rather than deferring with it:** v1 holds exactly one legitimate destination, the target's API, and it already knows it from the reachability annotation D-18 fetches — **so no static analysis is needed to produce v1's allowlist at all.** *"Falls out of the product's premise for free"* is more true after the pivot, not less, and the item should be read as a **v1 obligation with a v2 upside** rather than as a v2 feature. The one thing it must not be read as saying is that the allowlist closes the exfiltration limb — the target's own URL-fetching endpoints make the allowlisted host a confused deputy (`14` **U-44**). **Decided 2026-08-03 as `plan.md` OD-12, and this item's shape is superseded by something stricter, which is worth recording because CMA's `allowed_hosts` is now the *weaker* design.** v1 does not ship a host allowlist configured in the guest; it routes **all** sandbox egress through **one mandatory proxy** that enforces the destination allowlist and the HTTP method allowlist together, so a `curl` inside a shell is subject to the same rule as the runtime's HTTP client. `allowed_hosts` is host-granular, in-guest, and name-keyed — three properties the constitution's Principle IV bullet 1 now forbids in as many words after the **OD-13** amendment (v1.2.0). **So the item survives as a *shape to copy for the deny-by-default default*, and not as a specification.** The v1-obligation-with-a-v2-upside reading above is unchanged.
3. **The event-log-as-trace design.** `span.model_request_start/end` with `model_usage`, per-thread, replayable via `events.list`. This is a better observability primitive than either ADK or the Claude Agent SDK ships. Emit something isomorphic.
4. **The custom-tool round-trip protocol** (`agent.custom_tool_use` → idle → `user.custom_tool_result`) as the shape for over-the-boundary tool invocation, and the `session.status_idled` webhook as the shape for HITL without long-lived connections. Both are directly reusable designs for the HTTP/SSE serving layer you are building regardless.

### 7.3 Use it for the validation spike — with a stop condition

The calculus genuinely differs for disposable code, and I'd use it. Three CMA calls give you a sandboxed, stateful, coding-capable agent over a mounted repo in an afternoon; the ADK+Claude-SDK equivalent is a week of container and session plumbing before you learn anything. For the experiments in `11-validation-plan.md` — Class A vs Class B, whether inferred agent boundaries produce agents that outperform a flat baseline, whether consolidated tools beat 1:1 tools — **the harness is a confound you want to eliminate, not a variable you want to study.** CMA eliminates it fastest.

Specifically useful for the spike:

- `{"type": "github_repository"}` resource mounting — no clone subsystem needed (§2.2).
- `multiagent` coordinator as a **cheap upper bound** on hub-and-spoke topology. If a CMA coordinator with three scoped specialists cannot beat a single flat agent on the target codebase, the multi-agent premise is in trouble and no amount of graph sophistication will rescue it. That is a genuinely valuable negative result available for a day's work, and it is the kind of test `multi-agent-topology-review` demands before splitting anything.
- Per-thread cost metering from `span.model_request_end` — gives you the cost side of the topology comparison for free.

**Guard rails, non-negotiable:**

- **Cloud mode only, fixture repos only.** No customer code, no customer credentials, no production endpoints. Not ZDR-eligible (§4.2) — treat everything sent to CMA as retained by a third party.
- **A hard stop condition, written down now:** *no CMA call may appear in any code path intended for the generated artifact, and no spike may be promoted to production infrastructure without a from-scratch reimplementation on ~~ADK~~ **v1's own runtime (OD-15, 2026-08-03)**.* Spike drift is the only real risk here and it is a governance problem, not a technical one.
- **Instrument what you actually want to learn**, not the harness. The spike's output should be numbers about boundaries, tools, and topology — findings that transfer to any runtime.

### 7.4 Trigger conditions — what would change this verdict

| # | Trigger | Would change |
|---|---|---|
| 1 | **CMA becomes available on customer-owned Bedrock or Vertex accounts** | The largest objection (§4.1). Would move (c) from "rejected" to "seriously reconsider." Still wouldn't fix graph orchestration or serving. Watch the pricing page's modifier table — this is the exact line that would change. |
| 2 | **CMA reaches GA with ZDR eligibility and a documented session-state export** | Removes the residency objection and downgrades lock-in from "abandonment" to "rewrite." Necessary but not sufficient. |
| 3 | **MCP tunnels exit research preview with an SLA** | Makes cloud-mode reachability viable without a self-hosted worker fleet. Would strengthen (c) considerably. Currently *"as-is,"* Cloudflare-dependent, discontinuable at will. |
| 4 | **A first-class graph/workflow primitive lands** — declared edges, join semantics, guaranteed-step enforcement, nested subagents | This is the one that would genuinely threaten ADK's slot. Nothing in the current surface suggests it is coming; `multiagent` is the opposite bet. |
| 5 | **Empirical result: CMA's managed compaction materially outperforms your own context management** on long codebase-exploration runs | `context-engineering` treats compaction policy as load-bearing and CMA hides it. If measurement shows their closed policy beats yours by a wide margin on real repos, that is a real argument for (c) that no amount of architectural reasoning answers. **Measure this during the spike** — it is the cheapest high-value thing the spike can produce beyond the topology result. |
| 6 | **`function2agent` narrows its ICP to Anthropic-direct, non-regulated customers** | A product decision, not a CMA change — but it would dissolve objections 1 and 2 simultaneously. Worth naming explicitly so it's a *choice* rather than something that happens by drift. |

Triggers 1 and 4 together would justify a full re-evaluation. Any one alone would not.

---

## 8. Open questions and things I could not verify

- **Concurrent session limits.** No documented cap. The [anthropics/skills reference](https://github.com/anthropics/skills/blob/main/skills/claude-api/shared/managed-agents-api-reference.md) and the [docs reference page](https://platform.claude.com/docs/en/managed-agents/reference) **disagree** on read-endpoint RPM (600 vs 1,200), and the skills file lists an Environments row with "max concurrent 5" whose scope is ambiguous. Verify against your own org before any capacity commitment; if it means 5 concurrent environments, per-tenant environment isolation is off the table.
- **Regional coverage / data residency for sessions.** No region field on `environments.create`; the pricing page's note that `inference_geo` doesn't apply to CMA implies no session-level regional pinning exists. I could not find an affirmative statement either way. **For any EU-residency prospect, treat as unresolved and blocking.**
- **Whether a customer's Anthropic API key can be scoped to CMA specifically**, or whether granting CMA access grants full API access. Relevant to `08`'s model-plane blast-radius analysis. Not documented in what I read.
- **Session state export/import.** I found archive and delete, and full event *listing*, but no documented mechanism to export a session into a portable form and rehydrate it elsewhere. My lock-in assessment in §6 rests on this absence. If such a mechanism exists undocumented, §6's severity drops a notch. **Labeled as inference from absence.**
- **Actual sandbox cold-start latency and session-resume latency.** Not documented; materially affects whether CMA is usable for interactive HTTP/SSE serving as opposed to async work. Anthropic positions CMA for *"long-running tasks and asynchronous work"* — which may be a quiet admission that interactive latency is not its strength. **Inference, flagged as such; measure in the spike.**
- **Whether `github_repository` resources support private repos beyond a PAT** (GitHub App installation tokens, SSH deploy keys). The sidebar shows only `authorization_token`.
- **Named production users.** Notion, Rakuten, and Sentry are reported by [secondary Medium coverage](https://medium.com/@tentenco/anthropic-managed-agents-what-it-is-what-it-kills-and-why-the-timing-matters-0f70c1822f93) and not verified against an Anthropic source. The vendored cookbooks include `sentry/` and `linear/` directories, which is corroborating but not confirming.
- **Whether self-hosted sandboxes are still access-gated.** The [2026-05 blog](https://claude.com/blog/claude-managed-agents-updates) says "public beta"; the vendored `usage-guide.md:16` says *"you were already gated in by us to have access."* The vendored copy may predate general availability. Verify before planning on it.
- **The $0.08/session-hour rate and the 2026-04-08 launch date** are current as of 2026-08-02 against Anthropic's pricing page and secondary reporting respectively. Fast-moving; re-verify.
- **Engineering opinions, not cited results.** §5.3's rejection of architecture (c) on operational-arithmetic grounds, §6's position that no generated artifact should carry a hard CMA dependency, and §7.2's four "copy this" recommendations are my judgments from the documented surface. I hold them with strong priors; none is a controlled study. Nobody has run this comparison.

---

## 9. Sources

### §1 — What it is (all primary, Anthropic)

- [Claude Managed Agents overview](https://platform.claude.com/docs/en/managed-agents/overview) — core concepts, beta status, ZDR/BAA ineligibility, supported tools. Accessed 2026-08-02.
- [Managed Agents quickstart](https://platform.claude.com/docs/en/managed-agents/quickstart) — beta headers, three-call setup. Accessed 2026-08-02.
- [Agents API reference (beta)](https://platform.claude.com/docs/en/api/beta/agents) — `multiagent` schema, tool limits, roster constraints. Accessed 2026-08-02.
- [Claude API overview](https://platform.claude.com/docs/en/api/overview) — platform availability matrix. Accessed 2026-08-02.
- [Managed Agents reference](https://platform.claude.com/docs/en/managed-agents/reference) — full event-type tables, worker CLI flags, rate limits, branding guidelines. Accessed 2026-08-02.
- [anthropics/skills — managed-agents-api-reference.md](https://github.com/anthropics/skills/blob/main/skills/claude-api/shared/managed-agents-api-reference.md) — endpoint table, object ceilings, deployments. Anthropic-published; **conflicts with the docs page on rate limits.** Accessed 2026-08-02.

### §2 — Vendored cookbooks (read-only, local)

- `examples/claude-cookbooks/managed_agents/README.md` — notebook index and API-surface summary.
- `examples/claude-cookbooks/managed_agents/CMA_explore_unfamiliar_codebase.ipynb` — cells 5, 9, 11.
- `examples/claude-cookbooks/managed_agents/CMA_orchestrate_issue_to_pr.ipynb` — cells 5, 7, 9, 10.
- `examples/claude-cookbooks/managed_agents/CMA_coordinate_specialist_team.ipynb` — cells 5, 11, 13, 15, 18.
- `examples/claude-cookbooks/managed_agents/CMA_operate_in_production.ipynb` — cells 2, 4–8, 11, 12.
- `examples/claude-cookbooks/managed_agents/self_hosted_sandboxes/README.md` and `docs/usage-guide.md` — worker contract, environment key, six provider implementations, tool customization.
- `examples/claude-cookbooks/managed_agents/pyproject.toml` — `anthropic>=0.109.0`.

### §3–4 — Coverage, pricing, networking, limits

- [Claude pricing — Managed Agents section](https://platform.claude.com/docs/en/about-claude/pricing) — $0.08/session-hour, inapplicable modifiers, **"Not available on partner-operated cloud platforms."** Primary; commercially interested. Accessed 2026-08-02.
- [Environments](https://platform.claude.com/docs/en/managed-agents/environments) — `networking` modes, `allowed_hosts`, `packages`. Accessed 2026-08-02.
- [Cloud sandbox reference](https://platform.claude.com/docs/en/managed-agents/cloud-sandboxes-reference) — 8 GB / 10 GB / Ubuntu 22.04 / x86_64, default networking asymmetry. Accessed 2026-08-02.
- [Self-hosted sandboxes](https://platform.claude.com/docs/en/managed-agents/self-hosted-sandboxes) — split-responsibility table, custom tools reaching internal services. Accessed 2026-08-02.
- [MCP tunnels — overview](https://platform.claude.com/docs/en/agents-and-tools/mcp-tunnels/overview) and [concepts](https://platform.claude.com/docs/en/agents-and-tools/mcp-tunnels/concepts) — research preview, as-is disclaimer, outbound port 7844, mTLS. Accessed 2026-08-02.
- [Anthropic blog — self-hosted sandboxes and MCP tunnels](https://claude.com/blog/claude-managed-agents-updates) — public beta / research preview split. Vendor blog; primary for its own system.
- [InfoQ — Anthropic Introduces MCP Tunnels](https://www.infoq.com/news/2026/05/claude-mcp-tunnels/) — independent corroboration, 2026-05.
- Secondary, used only for the 2026-04-08 launch date and named users, flagged as unverified: [Medium / Ewan Mak](https://medium.com/@tentenco/anthropic-managed-agents-what-it-is-what-it-kills-and-why-the-timing-matters-0f70c1822f93), [Medium / unicodeveloper](https://medium.com/@unicodeveloper/claude-managed-agents-what-it-actually-offers-the-honest-pros-and-cons-and-how-to-run-agents-52369e5cff14), [Verdent guide](https://www.verdent.ai/guides/claude-managed-agents-pricing).

### §5–7 — Cross-references to sibling research

- [`02-agent-harnesses.md`](./02-agent-harnesses.md) §7 — "adopt a thin substrate, build the harness"; the sees-prompts-and-tokens test; the Claude-SDK-reaches-1.0 trigger.
- [`05-frontier-lab-agent-definitions.md`](./05-frontier-lab-agent-definitions.md) — cost/capability spread across providers; recommendation #3 on provider routing.
- [`06-examples-inventory.md`](./06-examples-inventory.md) §3, §4, §7 — ADK 2.6.1 capabilities and deprecation churn; the ADK-vs-Claude-SDK matrix; "process boundary to a closed-source agent loop."
- [`08-auth-identity-and-secrets.md`](./08-auth-identity-and-secrets.md) §1, §3 — two credential planes; broker-resolved `credential_ref`; secret-custody analysis.
- [`03-graph-and-loop-architecture.md`](./03-graph-and-loop-architecture.md) — when a graph is required over a loop.
