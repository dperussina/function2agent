---
name: graph-vs-loop-decision
description: Decides whether an agent's control flow should be a bare loop, an explicit state machine, or a graph, and specifies how emitted topologies must be represented. Use when designing or emitting agent control flow, choosing between a ReAct loop and a graph framework, adding a supervisor or orchestrator, enforcing that a required step always runs, placing a human approval gate, adding compensating actions or rollback, or reviewing a design that reaches for LangGraph, a state machine, or a dynamic planner.
---

# Graph vs. loop decision

Source: `research/03-graph-and-loop-architecture.md` §2, §5, §8, §11.

**Default position: the loop wins, and the industry under-says this.** A graph is justified only by
a *declared constraint*. If you cannot name the constraint, emit a tool and a loop.

## The decision procedure

```
1. Is there a step that MUST happen and sometimes does not?
     No  → Bare loop. Ship it. Stop here.
     Yes → continue.

2. How many distinct phases?
     ≤5 and roughly linear → explicit state machine (a dict of transitions is enough)
     Branching / fan-out / human-in-the-loop / resumable → graph

3. Do side effects need exactly-once across process crashes?
     Yes → graph on top of a durable execution engine
     No  → graph + checkpointer
```

The tell that you have outgrown the loop is **not** "it's getting complicated." It is "there is a
step that must happen and sometimes doesn't."

### The four constraints that justify a graph

Emit a graph only when the user or the analysis **declares** one of these. Nothing else counts.

| Constraint | What it looks like | Why a prompt can't do it |
|---|---|---|
| **Ordering** | B must not run before A | The model gets a vote; sometimes it votes wrong |
| **Mandatory step** | `commit` unreachable except through `validate` | A skipped validation is silent |
| **Human gate** | Refunds over $500 need supervisor approval | An insistent user talks the model past policy text |
| **Compensating action** | Money moved and the next step failed | There is no distributed transaction to roll back for you |

## Anti-patterns, named

- **"Graph for a `for` loop."** Topology sprawl with zero reliability gain and a second mental model
  to maintain.
- **A conditional edge whose predicate is an LLM answering "should we validate?"** You moved the
  prompt into the graph and kept all of its unreliability. Prefer code predicates over model
  predicates wherever the decision is expressible in code.
- **The supervisor pattern applied to one coherent task.** The most over-applied topology in the
  ecosystem. Correct when sub-domains have genuinely disjoint tools and policies; wrong when
  sub-agents must re-explain context to each other. If they share most of their context, they are
  one agent with more tools.
- **The dynamic planner.** The plan is generated with zero observations, so it encodes assumptions
  the first tool call invalidates. It earns its keep only with an explicit *replan* edge and a cheap
  trigger — i.e. only once you have turned it back into a graph with a cycle. Not worth it under
  ~5 steps; consider it above ~8, bounded to 2–3 replans, each consuming the failure reason.

## What a graph must guarantee structurally

The point of the topology is guarantees no prompt achieves:

```
START → plan → draft_write → validate ⇄ repair
                                 ↓ valid
                          needs approval? ─yes→ interrupt(human) ─approved→ commit → audit_log → END
                                 └─no──────────────────────────────────────────↑
```

`commit` is unreachable except through `validate`. `audit_log` is unreachable-past except through
`commit`. Those are structural.

**Test the topology, not the behavior.** These run in milliseconds, need no model, and catch exactly
the regression class an automated topology editor could introduce:

```python
def test_commit_requires_validation():
    paths = all_simple_paths(graph, source=START, target="commit")
    assert all("validate" in p for p in paths), "commit reachable without validate"

def test_no_side_effect_before_approval():
    for p in all_simple_paths(graph, START, "charge_card"):
        assert p.index("human_approval") < p.index("charge_card")
```

## Node contracts

Every node declares its contract. This is the bridge from a function signature to a graph node.

```python
@node(
    reads   = ["order_id", "customer"],
    writes  = ["inventory_check"],
    pre     = [lambda s: s.order_id is not None],
    post    = [lambda s: s.inventory_check in {"ok", "short"}],
    retries = RetryPolicy(max=3, on=(TransientError,)),
    idempotency_key = lambda s: f"invcheck:{s.order_id}",
)
def check_inventory(state: State) -> Update: ...
```

- A failing **precondition is a routing signal** (go gather the missing input), not an exception.
- A failing **postcondition is a repair signal**.
- **Every channel has an explicit reducer.** `messages` appends, `budget_spent` sums,
  `current_plan` overwrites. Last-write-wins is a *choice*, never a default you fall into. Two
  parallel branches writing the same non-reducer channel in one super-step should fail at compile
  time.
- **Keep the repair edge distinguishable from the retry edge in traces.** Retry means "the world was
  flaky"; repair means "we were wrong." Conflating them destroys failure attribution.

## Side effects: sagas

There is no distributed transaction across a payment API, an email service, and your database.
Three non-negotiables:

1. **Every side-effecting node declares a compensator**, or declares itself irreversible — in which
   case it must sit behind a human gate.
2. **Idempotency keys derive from stable state**, never from a UUID generated inside the node. On
   replay the node re-runs and would mint a new UUID.
3. **Compensation is itself a graph path** and must be as testable as the forward path. Failed
   compensation is the worst state the system can reach; give it its own terminal type and an alert.

## Topology must be data

Non-negotiable from day one. It costs little now and is impossible to retrofit; A/B-ing two
topologies you cannot serialize is not possible.

```yaml
graph: order_fulfillment
version: 7
content_hash: sha256:9f2c…
nodes:
  reserve_inventory:
    fn: inventory.reserve
    reads: [order_id, items]
    writes: [reservation_id]
    idempotency_key: "reserve:{order_id}"
    compensator: inventory.release
  charge_card:
    fn: payments.charge
    irreversible: true
    requires_approval_above_usd: 500
edges:
  - [START, validate_order]
  - [validate_order, reserve_inventory, {when: "valid"}]
  - [validate_order, reject, {when: "invalid"}]
invariants:
  - "charge_card is unreachable without validate_order"
  - "every irreversible node is preceded by an approval node"
```

Requirements, all four:

- **Serializable** — the topology is the source of truth, compiled into the framework's code API.
- **Content-addressed** — `content_hash` so a run is attributable to an exact topology.
- **Versioned** — rollback is a row change, not a deploy.
- **Carries an `invariants` block** — a machine-checkable safety-property list that runs as a unit
  test on every topology change, human PR or optimizer alike. Without it, automated topology
  modification is not something you can responsibly ship.

## Promotion ladder for this project

Not every function needs to become a full agent. Make the default cheap.

| Tier | What it is | Who decides |
|---|---|---|
| **T0** | Tool. Function exposed, no control flow | Default |
| **T1** | Guarded tool: precondition guard + postcondition verifier + typed failures | **Free and automatic** — derivable from type hints and exception classes, no LLM at runtime |
| **T2** | Self-healing node: bounded repair loop fed by the verifier's output | Automatic where a verifier exists |
| **T3** | Agentic node: planning over sub-tools, budget, memory | Opt-in |
| **T4** | Protocolled subgraph: mandatory steps, HITL gate, saga compensators, audit | **Explicit declaration required.** Ordering, gates, and compensators are policy and cannot be inferred from a signature. Make the user write them, as data. |

**The default promotion is a verifier-repair loop, not a ReAct loop** — guard → body → verify →
(repair | out), where the verifier is programmatic and derived from the function's own contract. See
`contract-derived-verification` for why the verifier must not be an LLM critiquing itself.
