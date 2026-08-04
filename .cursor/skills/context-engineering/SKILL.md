---
name: context-engineering
description: Budgets and manages what enters an agent's context window — working budgets, system prompt content, compaction vs. summarization, retrieval, memory tiers, and subagent isolation. Use when writing or reviewing a system prompt, adding an MCP server or retrieval source, deciding what to summarize or truncate, designing cross-session memory, or diagnosing an agent that loops, repeats itself, pursues a nonexistent file or endpoint, picks the wrong tool, or degrades over a long run.
---

# Context engineering

Sources: `research/01-agent-anatomy.md` §3, §4.

The definition worth using: **deciding exactly which tokens earn a place in the window at each
step.** The window is a scarce contended resource, not a bucket.

## The effective window is much smaller than the rated window

Every frontier model gets measurably worse as context grows, well before the window fills. Across
18 frontier models studied, **every one** showed measurable decline as input length grew — this is
*context rot*. Chroma's data puts accuracy loss beginning around **50,000 tokens of genuinely
relevant information**, inside windows rated 200k–1M. Practitioner rule of thumb: for a model
advertising 1M tokens, the high-quality zone is often **under ~256k**.

*Confidence: high on direction, medium on thresholds.* These are planning numbers, not physical
constants. Measure your own.

**The operative rule: budget working context to a fraction of the rated window, and re-measure the
total whenever you add a tool or a retrieval source.** A worked example for a single support-ticket
task: 5,000 tokens of tool definitions + 3,000 retrieval + 4,000 for eight turns + three tool calls
averaging 1,500 ≈ **16,500 tokens of working context** for one ticket. Each new MCP server usually
costs more than the line item you budgeted for it.

## The four failure modes

The standard vocabulary. Name the mode when diagnosing — the mitigations are different.

| Failure | Mechanism | Signature | Mitigation |
|---|---|---|---|
| **Poisoning** | A hallucination enters context and is then referenced as ground truth | Agent pursues a file, endpoint, or goal that does not exist and cannot be talked out of it | Validate tool output at the boundary; never let the model's *claims* become state, only tool *results*; make corrections destructive |
| **Distraction** | Context grows until the model over-weights history and under-weights its priors | Agent repeats a previous action instead of trying something new; loops | Compact aggressively; cap history; **no-progress detector as a hard stop** |
| **Confusion** | Superfluous-but-not-wrong content degrades output — usually too many similar tool definitions | `send_email` vs. `send_slack` with near-identical descriptions; model picks wrong | Shrink the tool set; defer loading; disambiguate descriptions (see `agent-tool-design`) |
| **Clash** | Two parts of context genuinely contradict | Long-term memory says "prefers mornings," this thread says "avoid mornings" | Timestamp and rank by recency/authority; **remove** superseded turns rather than appending corrections |

Two things to hold onto. **Larger windows amplify these rather than fixing them** — more space is
more surface area for stale and contradictory content. And **clash is usually caused by your own
memory system**: the moment you add cross-session memory you have built a machine for injecting
statements that contradict the current thread.

## Reclaiming space: raw → compaction → summarization

Strict preference ordering. Do not skip a rung.

- **Raw.** Preferred. Keep it if it fits.
- **Compaction is reversible.** Strip information that is redundant *because it exists in the
  environment*. Drop 3,000 lines of file contents from turn 4, leave the path and a note; if the
  agent needs it, it re-reads the file. Nothing is destroyed.
- **Summarization is lossy.** An LLM rewrites history into prose. Anything not in the summary is
  gone forever. Only when compaction no longer yields enough space.

Two implementation details that matter more than they sound:

1. **Keep the most recent tool calls raw, in full detail, through a summarization.** This preserves
   the model's rhythm and formatting. A summarized-only history produces an agent that starts
   writing summaries instead of doing work.
2. **Summaries must preserve *constraints*, not *narrative*.** The failure mode is a summary that
   reads beautifully to a human and is useless to an agent. What must survive: which approaches
   failed, which files were created, which assumptions were invalidated, which handles can be
   re-fetched, which uncertainties are open. Emit typed artifacts — decisions, file changes, open
   questions — not prose.

**Trigger placement:** fire compaction at roughly **70–75% of your intended working budget**, which
is already a fraction of the rated window. Not at the API limit. Provider-native compaction exists
(Anthropic's `compact_20260112` context edit, `input_tokens` trigger, minimum value 50,000); its
`pause_after_compaction` hook is where you re-assert invariants before the model continues.

## System prompt

The only context you fully control on every turn — highest leverage, most abused.

**Belongs:**
- Role and scope in two or three sentences, including what the agent must **refuse**.
- The **loop contract**: how to use tools, when to stop, what "done" means, what to do when blocked.
  Agents fail more often from not knowing when to stop than from not knowing what to do.
- Hard invariants phrased as rules with consequences.
- The output contract, if downstream code parses the final answer.
- **Pointers, not payloads.** "Project conventions are in `CONVENTIONS.md`; read it before editing"
  beats inlining 4,000 tokens irrelevant to 80% of tasks.

**Does not belong:**
- Few-shot examples duplicating what tool schemas already say — put usage examples on the *tool*.
- Long edge-case enumerations — that is what skills and progressive disclosure are for.
- Anything computable at assembly time. If this run cannot touch the database, do not spend tokens
  explaining database policy.

**Named anti-pattern: the kitchen-sink `CLAUDE.md`/`AGENTS.md`.** Genuinely valuable as lightweight
procedural memory, and they rot into 8,000-token dumping grounds injected on every turn of every
task. Treat them as an index with hard size caps; push detail behind file reads.

## Retrieval

1. **Agentic search often beats embedding search** for code and structured corpora. `grep`, `glob`,
   and `read_file` let the model iterate on its own query against ground truth. Reserve embeddings
   for genuinely unstructured, large corpora.
2. **Over-eager retrieval is now the more common failure than under-retrieval.** Retrieval is the
   main vector for context confusion. Fetch fewer, shorter, higher-precision chunks and make it easy
   to fetch more on demand.

## Memory tiers

| Tier | Contents | Lifetime | Substrate |
|---|---|---|---|
| **Working** | Current messages, tool calls, active plan, scratchpad | The run | The context window |
| **Episodic** | Timestamped events: what happened, what was tried, what failed | Cross-session, decaying | Append-only log |
| **Semantic** | Durable facts: preferences, conventions, project state | Indefinite, revisable | Files, KV, vector+graph |
| **Procedural** | How to do things: workflows, playbooks, recipes | Indefinite, versioned | `SKILL.md`, `AGENTS.md`, code |

Episodic is cheap to write and expensive to read; semantic is expensive to write correctly and cheap
to read. **Consolidation** — promoting durable facts out of episodic logs and discarding the rest —
is where memory systems succeed or fail. Without it you get twenty timestamped copies of one
preference and a guaranteed clash.

**Set the promotion bar high: durable memory should contain only things that continue to constrain
future reasoning.** Storing too much is not neutral; it is context pollution you made permanent.

**Expose memory management to the agent as tools**, so memory decisions are made with task context
available. A background pipeline deciding what to remember has strictly less information than the
agent that just finished the task.

**Files beat vectors for agent-authored memory** — inspectable, versionable, diffable, legible to
both the model and the human curating it. The honest counter-evidence: the first systematic study of
filesystem-based agent memory found organization reliably buys **search economy** (roughly halving
retrieval cost on large stores) but that **organization erodes as the store grows** and updates do
not reliably land over time ([arXiv:2607.26637](https://arxiv.org/html/2607.26637)). Read that as:
files are the right substrate, and **the agent cannot yet be trusted to be its own librarian
without supervision.** Budget for a curation mechanism.

**Scratchpad is the primary defense against compaction loss.** If the plan and findings live in
`notes.md`, summarization can be aggressive because the durable artifacts are outside the window.

## Subagent context isolation

The strongest argument for multiple agents is not division of labor — it is that **each subagent
gets a clean window.** The parent hands a self-contained brief, the child burns 80k tokens
exploring, and returns 800 tokens. The parent never sees the 80k.

Real cost: **the summarization seam is lossy and you pay for the discarded tokens.** Every fact the
child saw and omitted is gone. This is exactly why isolation works for read-heavy exploration and
fails for write-heavy interdependent work — see `multi-agent-topology-review`.

**Context folding** is the in-process variant: branch to handle a subtask, then fold it on
completion, collapsing intermediate steps and retaining a concise outcome. Same benefit, no separate
actor, no 15× multiplier ([Anthropic](https://www.anthropic.com/engineering/multi-agent-research-system)).

## Applying this to this project

- **Context isolation is a per-tool execution mode, not a one-time architecture decision.** A
  promoted function whose job is "search the codebase and report" wants isolation. One whose job is
  "apply this migration" must not have it, because its findings and its writes are the same object.
- **A promoted function needs a declared memory contract.** Which tiers does it get? Is semantic
  memory scoped to the caller, the tenant, or global? For most promoted functions the honest answer
  is **episodic only, scoped to the run** — and that is a feature. A function accumulating
  cross-invocation semantic memory has quietly become a stateful service with all the attendant
  governance problems.
