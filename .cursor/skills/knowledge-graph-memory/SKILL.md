---
name: knowledge-graph-memory
description: Designs the knowledge and memory layer for a generated agent stack — which of the four memory tiers a component gets, what substrate holds each, and the hygiene and provenance rules that keep a memory store from becoming an attack surface. Use when adding cross-session memory, a knowledge graph, a vector store, or a repo map to an agent; deciding what an agent should remember or write persistently; promoting a trajectory into a skill or heuristic; or reviewing a design where an agent writes durable state.
---

# Knowledge and memory layer

Sources: `research/01-agent-anatomy.md` §4 (the four tiers, filesystem-as-memory, LLM-managed
paging), `research/04-self-improving-agents.md` §5.4 (memory hygiene and poisoning),
`research/07-product-vision.md` C9 and §6.1.

**Two framing facts to hold simultaneously:** for agent-authored memory the **file beat the vector**,
and **memory is the one improvement mechanism that runs online and writes persistent state**, which
makes it uniquely dangerous. Design for both.

## The four tiers, and which one a component actually gets

The settled CoALA taxonomy (`01 §4.1`):

| Tier | Contents | Lifetime | Substrate | Written by |
|---|---|---|---|---|
| **Working** | Current messages, tool calls, active plan, scratchpad | The turn / the run | The context window itself | The loop |
| **Episodic** | Timestamped events: what happened, what was tried, what failed | Cross-session, decaying | Append-only log, run transcripts | The loop, automatically |
| **Semantic** | Durable facts: preferences, conventions, entity relationships, project state | Indefinite, revisable | Files, KV store | The agent, curated |
| **Procedural** | How to do things: workflows, playbooks, learned recipes | Indefinite, versioned | `SKILL.md`, `AGENTS.md`, code | Humans and agents |

**Default assignment for anything generated: working + episodic scoped to the run. Nothing else,
until a specific need is named** (`01 §4.4`). A promoted function that accumulates cross-invocation
semantic memory **has quietly become a stateful service** with all the attendant governance problems.
That default is a feature, not a limitation.

The distinction with operational weight is **episodic vs. semantic**:

- Episodic is **cheap to write, expensive to read** — it grows without bound and most of it is noise.
- Semantic is **expensive to write correctly, cheap to read**.
- **Consolidation** — promoting durable facts out of episodic logs and discarding the rest — is where
  memory systems succeed or fail. Without it you get twenty timestamped copies of the same preference
  and a guaranteed context clash.

**Promotion bar:** durable memory contains only things that *continue to constrain future reasoning*.
Everything else needs an extremely strong case. Storing too much is not a neutral cost — it is
**context pollution you have made permanent**.

## Substrate: files first, and start without a graph DB

Files won for agent-authored tiers not because vectors are worse at similarity search, but because
files are inspectable, versionable, portable, composable, and **simultaneously legible to the model
and to the human who must curate and trust the store** (`01 §4.3`).

Recurring design features worth copying:

- Structured markdown with YAML frontmatter as the record format.
- **Tiered content within a file** — catalog/summary, overview, full detail — so the agent loads the
  cheap layer first. Progressive disclosure applied to memory.
- **Hybrid multi-signal retrieval** (full-text + recency + importance), not pure embedding similarity.
- Explicit lifecycle governance: consolidation, staleness detection, conflict resolution, GC.

**For this project's knowledge layer specifically** (`07 §6.1`): a generated repo map plus `codegraph`
exposed as a search tool. **No graph DB. No agent-writable memory in v1.** Agentic search — `grep`,
`glob`, `read_file` over ground truth — routinely beats embedding search on code and structured
corpora (`01 §3`), because the model can iterate on its own query. Reserve embeddings for genuinely
unstructured, large corpora.

**Honest counter-evidence, because filesystem memory is over-sold:** the first systematic study found
organization reliably buys search economy — organized stores roughly **halve** retrieval cost on
large material — but also that **organization erodes as the store grows** and updates do not reliably
land correctly over time ([arXiv:2607.26637](https://arxiv.org/html/2607.26637)). Read that as: files
are the right substrate, and **the agent cannot yet be trusted to be its own librarian without
supervision.** Budget for a curation mechanism — periodic human review, a scheduled consolidation pass
with tests, or hard schema constraints — rather than assuming self-organization.

## Expose memory management as tools, not as a background pipeline

Letta's paging model — core (always in context) / archival (unbounded, searched) / recall (pageable
history), all driven by model tool calls — generalizes to one rule (`01 §4.2`):

> **Memory decisions should be made with task context available.** A background pipeline deciding
> what to remember has strictly less information than the agent that just finished the task.

Also externalize working memory deliberately: a scratchpad file is the primary defense against
compaction loss, and a tracked todo list is a **re-anchoring** device against long-run drift, not
primarily a planning device (`01 §4.4`).

## Memory is a documented attack surface

Not a quality concern — a security concern (`04 §5.4`).

A 2026 systematic study identified **four memory write channels** — tool-executed write,
system-prompt-driven write, compaction-driven write, and **experience-to-procedure** — plus nine
structural vulnerabilities, and showed empirically that **agents designed to write and retrieve
memory more aggressively are more exploitable**, and that **existing prompt-injection defenses do not
cover memory poisoning** ([arXiv:2606.04329](https://arxiv.org/abs/2606.04329)).

- "Sleeper" variants plant dormant memories that activate later: write rates up to **~99%** against
  stateful assistants, with attacker-intended actions following in **60–89%** of successful retrievals
  ([arXiv:2605.15338](https://arxiv.org/abs/2605.15338)).
- **Write-time consistency checks suppress direct single-record corruption but fail against
  compositional (multi-record) and trigger-conditioned attacks**
  ([arXiv:2607.14651](https://arxiv.org/abs/2607.14651)). Per-record filtering is necessary and not
  sufficient.

**Note the third channel in that list: experience-to-procedure.** The mechanism that turns successful
trajectories into skills — the highest-value form of memory — is itself a documented attack surface.
Agent-writable memory is an **unreviewed instruction channel**. Treat it as one.

*Calibration:* attack-success figures come largely from controlled conditions with sparse memories;
poison must out-compete real signal at retrieval, so headline percentages likely overstate risk for
mature stores. The structural vulnerability stands regardless (`04` unverified section).

## Hygiene table — every failure mode has a required mitigation

| Failure | What it looks like | Required mitigation |
|---|---|---|
| **Staleness** | Memory encodes a fact that changed | TTLs; re-verify on read for volatile facts; store `as_of` timestamps |
| **Contradiction** | Two memories disagree | Detect on write; keep both with provenance and let retrieval surface the conflict. **Never silently pick one** |
| **Unbounded growth** | Retrieval quality decays, cost rises | Hard cap; evict by recency × utility (track retrieval hit-rate and downstream success per memory) |
| **Overfitting to a user** | One interaction generalized into a rule | Require **k independent observations** before promoting episodic → heuristic |
| **Poisoning** | Adversarial content becomes durable knowledge | Provenance, cross-record checks on write, write-node restriction, human review |

## Non-negotiables for any memory write path

```
- [ ] Provenance on every record: which run, which node, which source,
      trusted/untrusted, verified/unverified — and retrieval can FILTER on it
- [ ] Never write memory derived from untrusted content without validation
      (tool output from the open web is untrusted input)
- [ ] Store the verified OUTCOME, not the attempt. Memory of an unverified
      outcome is memory of a guess
- [ ] Cross-check on write against related existing records, not just per-record
      filtering — compositional attacks are exactly the ones that survive per-record checks
- [ ] Least privilege on write: only designated nodes write memory, enforced by
      topology (see graph-vs-loop-decision), not by prompt
- [ ] Reviewable: a human can list, search, and DELETE what the agent believes
- [ ] Promotion of a memory to a heuristic or skill requires human approval —
      it now affects all runs
```

Procedural memory as **files** is what makes this governable: an agent-authored skill arriving as a
PR is a reviewable, diffable, versionable, revocable artifact. An agent-authored embedding in a vector
store is none of those things (`04 §5.3`).

## Do / don't

```
DON'T  give a generated agent semantic or procedural memory by default
DON'T  stand up a graph DB or vector store before files have demonstrably failed
DON'T  let a background pipeline decide what to remember
DON'T  promote an episodic observation to a heuristic from a single occurrence
DON'T  rely on write-time consistency checks alone — they fail compositionally
DON'T  let compaction write memory unreviewed; it is one of the four attack channels

DO     default to working + episodic, scoped to the run
DO     put memory-management operations behind tools the agent calls with task context
DO     keep a scratchpad file so compaction can be aggressive
DO     store as_of timestamps and TTLs on anything volatile
DO     keep both sides of a contradiction, with provenance
DO     budget an explicit curation mechanism; the agent is not yet a reliable librarian
```

## Related skills

`context-engineering` for the working-tier budget and the raw → compact → summarize ordering.
`contract-derived-verification` for what "verified outcome" means before a write.
`graph-vs-loop-decision` for enforcing write-node restriction in topology.
