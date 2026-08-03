---
name: mcp-export-design
description: "SPLIT STANDING — the 'not the internal calling convention' rule is v1 and binding; the MCP export adapter defers to v2 with tool synthesis (plan.md OD-09), because the artifact it exported was the tool catalogue. Designs the MCP export surface for a generated tool catalog and keeps MCP out of the internal calling convention. Use when emitting or designing an MCP server, choosing a wire revision or transport, deciding whether MCP should be the canonical internal tool representation, planning for MCP protocol churn and legacy-client compatibility, or assuming MCP provides progressive disclosure, tool search, or code-mode execution."
---

# MCP export design

> ## Standing: **split by `plan.md` OD-09 (2026-08-02) — the negative half is v1, the positive half is v2.**
>
> **Negative half — *do not adopt MCP as the internal calling convention* — survives as a v1 rule, but
> its decisive argument does not.** Reason 4 below ("MCP schemas have nowhere to put the metadata the
> safety story depends on… compile-time lethal-trifecta detection requires `read_only` and `egress`
> per tool") is a claim about **a catalogue of labelled synthesized tools**, and v1 emits none. There
> is no compile-time trifecta check for MCP to delete. **Reason 4 is therefore wrong as stated for v1
> and right for v2 — it is the clearest example in the skill set of an argument outliving its
> premise.** The rule survives on reasons 1–3 plus one that OD-09 adds: v1 resolves effect tiers **per
> call at a runtime interception point** (D-22), and MCP has no slot for that either.
>
> **Positive half — *MCP export is the most legible artifact the product can hand a customer* —
> defers with synthesis outright**, because the artifact it exports *is* the tool catalogue. The white
> space `09 §5.2` found is still white space and still a v2 asset, with roughly a six-month lead
> rather than a moat (U-14).
>
> `14-architecture-synthesis.md` records this as **D-06 (amended)** and **C-11**.

Source: `research/09-mcp-as-tool-surface.md`. Cross-refs `research/01-agent-anatomy.md` §5.6, §8.5;
standing per `research/14-architecture-synthesis.md` D-06, D-21, D-22.

## The call

> **MCP is an export adapter and a first-class product artifact. It is not the internal calling
> convention.** (`09 §8.1`) — **v1 keeps the second sentence and defers the first.**

Four layers, and the split is the whole design:

| Layer | Choice |
|---|---|
| **Extraction** | Language-native introspection (LSP/AST/type providers) → typed internal IR carrying `read_only`, `egress`, idempotence, cost, auth scope |
| **Canonical form** | The typed IR. Single source of truth. **All policy and safety analysis happens here** |
| **Internal calling** | Direct, in-process, through the reference monitor. Code mode as a *per-tool policy* projected from the IR |
| **Export** | MCP server (tools only) as a headline artifact; provider-native schemas and OpenAPI as additional adapters from the same IR |

"Export surface" undersells the product side. The generated MCP server is plausibly the **most legible
thing the product produces** — "point it at your repo, get an MCP server your whole company can use
from Claude, ChatGPT, Cursor, and Gemini." **Export in architecture, headline in product** (`09 §8.2`).

## Why not internal — four reasons, in ascending strength

1. **Code mode is blocked over MCP connectors.** Anthropic's live docs state that tools provided by an
   MCP connector *cannot* be called programmatically (verified 2026-08-02; corroborated by LiteLLM's
   provider docs). If you want code mode's token savings you must own the sandbox, which means you must
   own an internal tool representation anyway (`09 §4.1`).
2. **The trust model forces re-validation at the boundary regardless**, and generation *inverts* the
   trust direction: you emit a surface nobody reviewed, at machine scale, across every customer. MCP
   offers no provenance primitive (`09 §7`).
3. **The wire format keeps breaking** — see below.
4. ~~**Decisive:**~~ **v2 only, and no longer decisive — see the standing note.** MCP schemas have
   nowhere to put the metadata the safety story depends on. Compile-time lethal-trifecta detection
   requires `read_only` and `egress` per tool. JSON Schema has no slot; MCP has no convention. You
   could smuggle them through `_meta`, but **no client would enforce them**. If MCP were canonical, the
   differentiating safety property would be **unrepresentable**. That is an architectural
   disqualification, not a preference (`09 §8.2`). **For v1 the argument re-lands one layer down and
   arrives at the same place: the safety property is a per-call tier resolved at a runtime interception
   point (D-22), and MCP has no slot for that either. Weaker as an argument, identical as a
   conclusion.**

See what survives projection — this is reason 4 as a diff (`09 §8.1`):

```jsonc
// Internal IR — canonical
{ "name": "fulfill_order",
  "source":  { "repo": "acme/orders", "commit": "abc123", "symbol": "OrderService.fulfill" },
  "params":  { "orderId": { "newtype": "OrderId", "base": "string" } },
  "effects": { "read_only": false, "egress": ["carrier-api"],
               "idempotent": false, "destructive": true, "auth_scope": "orders:write" } }

// Projected MCP tool — note what is gone
{ "name": "fulfill_order",
  "description": "…Destructive: creates a real shipment. `orderId` is an OrderId, not a customer id.",
  "inputSchema": { "type": "object",
                   "properties": { "orderId": { "type": "string" } },   // newtype ERASED
                   "required": ["orderId"] }
  // read_only, egress, idempotent, destructive, auth_scope: NO SLOT EXISTS.
  // Provenance (repo/commit/generator signature):        NO SLOT EXISTS.
}
```

Everything load-bearing for safety survives only as **English prose in `description`, enforced by
nothing.**

## Protocol churn: four breaking revisions in ~20 months

The version identifier is `YYYY-MM-DD` meaning "the last date backwards incompatible changes were
made," and is explicitly **not** incremented for compatible updates. So by the project's own
definition every revision after the initial release is a break (`09 §1.1`):

| Revision | Notable for |
|---|---|
| `2024-11-05` | Initial release. stdio + HTTP+SSE |
| `2025-03-26` | Streamable HTTP; HTTP+SSE deprecated; OAuth 2.1 |
| `2025-06-18` | Authorization split into resource / authorization server roles |
| `2025-11-25` | Elicitation, tasks (experimental) |
| `2026-07-28` | **Stateless core. Handshake and sessions removed** — by far the largest |

`2026-07-28` removed, in one revision (`09 §1.2`): `initialize`/`notifications/initialized`,
`Mcp-Session-Id`, `ping`, `logging/setLevel`, `notifications/roots/list_changed`, SSE stream
resumability (`Last-Event-ID` gone — a broken stream loses the in-flight request), and all
server-initiated requests, replaced by **Multi Round-Trip Requests (MRTR)**: the server returns
`resultType: "input_required"` with `inputRequests` and the client retries with `inputResponses`.
Two changes cut *in favor*: SEP-2106 loosened `inputSchema`/`outputSchema` to any JSON Schema 2020-12,
and SEP-2549 added `ttlMs`/`cacheScope` plus deterministic `tools/list` ordering.

**Governance is a durability signal, not a stability signal.** Linux Foundation / AAIF stewardship
changed stewardship, not technical control — it remains a BDFL model where two Lead Maintainers hold
final authority and veto. Two people can still land a breaking change, and in July 2026 they did. The
new 12-month deprecation window constrains *removals* going forward; it did not constrain the
`2026-07-28` core changes, which were removals executed in the same revision that introduced the
policy (`09 §1.3`).

## Generated servers must be dual-era

The spec's own compatibility matrix (`09 §1.4`):

| Client | Server | Outcome |
|---|---|---|
| Modern | Modern | Works |
| Modern | Legacy | **Fails** |
| Dual-era | Modern / Legacy | Works |
| **Legacy** | **Modern** | **Fails — "legacy clients have no fall-forward mechanism"** |
| Legacy | Dual-era | Works |

**Every MCP client shipping today is legacy.** A generated server speaking only `2026-07-28` fails
against Claude, ChatGPT, Cursor, and Gemini right now — and fails badly: a bare `400` on HTTP, an
implementation-defined error on stdio, with no downward retry path.

> **Generated servers must be dual-era** — serving legacy `initialize` and modern per-request `_meta`
> concurrently on the same endpoint (which the spec explicitly permits). **Not optional for at least
> a year.** Session handling on the legacy path, statelessness on the modern one.

This is nontrivial generated machinery, and it belongs in **one generator backend**, not smeared across
a runtime. Protocol-churn absorption is exactly what a single adapter layer is for.

## What MCP does not give you — stop expecting these

| Mechanism | In the MCP spec? |
|---|---|
| Cursor pagination on `tools/list` | Yes — paginates *transport*, not context; clients fetch all pages anyway |
| `ttlMs` / `cacheScope` / deterministic ordering | Yes — helps prompt-cache stability; does not reduce the catalog |
| Namespacing | **No** — convention only (`server__tool`), applied by clients |
| Tool search / semantic discovery | **No** — vendor features |
| `defer_loading` | **No** — an **Anthropic Messages API / OpenAI Responses API** construct |
| Server-declared tool subsets or profiles | **No** |
| Programmatic / code-mode invocation | **No** |

**Progressive disclosure is not an MCP feature.** `defer_loading`, the tool search tool, and
`allowed_callers` are proprietary API-level constructs with cross-vendor convergence through parallel
implementation, *not through the protocol* (`09 §4.1`, §4.2).

The consequence inverts the naive reading: **making MCP the output does not solve the tool-count
problem; it removes your tools from the layer where the problem is solvable.** Once tools are behind
`tools/list` you have handed disclosure control to a client you do not own. A generated server's only
real levers are (a) expose fewer tools and (b) name and describe them well — both **generation-time
design decisions made in your own IR**.

Code-mode availability in one table (`09 §4.1`):

| If you… | Code mode? |
|---|---|
| Call tools you define directly in the Messages API | **Yes** — `allowed_callers: ["code_execution_20260120"]` |
| Call tools via Anthropic's MCP connector | **No** — explicitly excluded |
| Call MCP tools through **your own** client + sandbox | **Yes** — you are the client |

That third row is the escape hatch, and it is the one Anthropic's own demo used: "MCP servers as a
directory of TypeScript modules" is implemented *by the client*. The 150k → ~2k token figure came from
a client-side filesystem abstraction, not from anything MCP provides.

## Checklist for an emitted MCP server

```
- [ ] Dual-era: legacy initialize AND modern per-request _meta on one endpoint
- [ ] server/discover implemented (servers MUST; clients MAY call it)
- [ ] Every result carries resultType ("complete" | "input_required")
- [ ] Destructive tools gated via MRTR input_required, not via a model-callable confirm tool
- [ ] Cross-call state via explicit server-minted handles passed as tool arguments —
      sessions are gone, and handle-passing will not fall out of a mechanical translation
- [ ] No reliance on ping, logging/setLevel, or SSE resumability
- [ ] tools/list returns deterministic order; ttlMs / cacheScope set
- [ ] inputSchema uses JSON Schema 2020-12 (SEP-2106) rather than the old narrow subset
- [ ] Effects metadata retained in the IR; description prose states destructiveness explicitly
      since no enforceable slot exists
- [ ] Catalog size decided in the IR before projection, not delegated to client disclosure features
- [ ] Treat every consumed third-party MCP server as untrusted input: pin and hash schemas,
      alert on drift, scope credentials per server
```

## Do / don't

```
DON'T  make MCP the canonical internal representation — reason 4 is disqualifying
DON'T  emit a modern-only server; it fails against every client shipping today
DON'T  count on defer_loading, tool search, or namespacing as protocol features
DON'T  assume Linux Foundation stewardship means the wire format is stable
DON'T  put read_only/egress in _meta and call the safety story handled
DON'T  design server-initiated callbacks — sampling, elicitation, and roots/list are gone

DO     keep a typed IR as the single source of truth and project MCP from it
DO     generate dual-era servers and plan for a fifth break
DO     design handle-passing explicitly for transactions, cursors, and multi-step workflows
DO     decide catalog size at generation time
DO     ship the MCP server as a headline artifact — it is the most legible output
```

## Related skills

`tool-synthesis-from-code` for what goes in the catalog and why effects metadata must live in the IR.
`agent-tool-design` for per-tool quality and the 30–50 tool threshold.
`context-engineering` for the definition-token cost of a large catalog.
