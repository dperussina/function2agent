---
name: integration-surface-design
description: Designs the HTTP/SSE and embeddable-iframe delivery surfaces for a generated agent stack, and enforces that they are separate product tiers with different capability sets rather than one surface with a configuration flag. Use when adding an embeddable widget, chat iframe, or in-app assistant; designing session tokens, `postMessage` handshakes, CSP `frame-ancestors`, or origin isolation; deciding which tools an end-user-facing agent may hold; propagating end-user identity into tool calls; handling anonymous or unauthenticated agent sessions; or reviewing a proposal to reuse the server-to-server agent behind a browser embed.
---

# Integration surface design

Sources: `research/08-auth-identity-and-secrets.md` §3.2, §5; `research/07-product-vision.md` §3.4, §6.

**The load-bearing claim: HTTP/SSE and the iframe are different product tiers, not one surface with
a flag.** They differ in who the caller is, whether any authority exists to act on, and whether an
approval gate has an approver. A design that ships "the same agent, embeddable" ships an incident.

## Why the iframe is the worst case in the product

It supplies all three legs of the lethal trifecta *by construction*:

1. **Private data** — resource-plane credentials reaching production systems.
2. **Untrusted content** — an anonymous member of the public typing into a text box, plus everything
   that text causes the agent to read.
3. **Egress** — shell and network in the coding-tool configuration; and even with neither, **the
   response rendered back into the iframe is itself an egress channel.**

And this cannot be closed at the model layer. In-band defenses plateau near 95% detection, which is
a failing grade in appsec. Out-of-band defenses are validated on static benchmarks — the same
methodology that made in-band defenses look strong until adaptive attacks broke twelve of them at
>90% success. See `agent-safety-and-sandboxing` for the full posture.

**Therefore: do not plan for the iframe path to be made safe by a defense. Plan for it to be made
safe by not having the capability.**

## The tier table — this is the deliverable

| Capability | HTTP/SSE (server-to-server, operator-authenticated) | Iframe (end-user-facing) |
|---|---|---|
| Shell / arbitrary code execution | Yes, in a microVM sandbox | **No. Not at all.** |
| File read/write | Yes, sandbox filesystem | No |
| Network egress | Destination allowlist | **Deny-all except the API itself** |
| Synthesized domain tools | Full set, policy-gated | **Read-mostly subset, explicitly published per tenant** |
| Write / destructive domain tools | Behind approval nodes | **Not present in the tool set at all** |
| Resource-plane authority | Scoped service identity or delegated user token | **Delegated user token only**; if no user identity, a fixed anonymous-tier scope with no user-data access |
| Durable memory writes | Yes, scanned and scoped | **No cross-session writes.** Session-scoped only. |
| Model-plane credential | Orchestrator-held | Orchestrator-held, **per-session token and cost cap** |

If a proposal cannot fill in this table for the surface it is adding, it is not ready.

## The two rationales that get argued with most

### Removing shell matters more than sandboxing harder

A microVM bounds the blast radius of *code execution*. The thing to fear in this tier is **the agent
using its legitimate resource-plane data path with the wrong authority** — and a hypervisor does
nothing about that. Removing shell removes the universal-tool bypass and makes the declared tool
surface the *complete* surface, which is the precondition for the policy engine being a real
boundary rather than a speed bump.

Reject: "we'll allow shell in the iframe tier but harden the sandbox." That is a stronger answer to
a question nobody asked.

### Removing write tools matters more than gating them

**An approval gate requires an approver.** In an anonymous iframe there is nobody with the authority
to approve — the end user is precisely the party whose authority is in question. **An approval
prompt shown to an attacker is a UI element, not a control.**

When a tenant genuinely needs end-user-initiated writes, route them to the customer's own
application as a normal authenticated request, with the agent producing a **proposal** that the
customer's app authorizes and executes. **The agent recommends; the customer's existing
authorization stack decides.** That inverts the confused deputy — the deputy no longer holds any
authority at all.

## Anonymous sessions: there is nothing to delegate

RFC 8693 token exchange is the correct semantic backbone: exchange the user's **subject token** plus
the agent's **actor token** for an audience-scoped token, recording the acting party in `act`.

- **Authenticated end user** (internal tool, logged-in portal): the customer's backend mints a
  subject token, hands it over HTTP/SSE, the broker exchanges it. **This is the good case; design
  for it.**
- **Anonymous end user** (public support widget): there is **no subject token**, therefore no user
  authority to scope down to, therefore **nothing for RFC 8693 to act on.** This is not fixable with
  better tokens — the authority genuinely does not exist.

The only correct response for anonymous sessions is a **fixed, pre-declared, minimum-authority**
identity with **no user-data access at all**, and the product must say so plainly. Capability
removal is the only real mitigation available in this case.

Corollary on rendering: because the reply itself is egress, **the anonymous tier must not be able to
read other users' data in the first place. Output filtering is not a substitute for not having the
data.**

## Browser-side hardening: table stakes, and nowhere near sufficient

These defend against browser-layer attacks. **They do nothing against prompt injection.** Ship all
of them anyway.

| Control | Requirement |
|---|---|
| Origin isolation | Dedicated origin (`widget.example.io`), never the customer's origin, never `srcdoc` |
| `sandbox` attribute | Start at `sandbox="allow-scripts allow-forms"`. **Never add `allow-same-origin` alongside `allow-scripts`** — the combination lets framed content remove its own sandboxing |
| CSP `frame-ancestors` | **Per-tenant**, derived from registered origins, never a wildcard. Plus `X-Frame-Options: DENY` as a legacy fallback |
| CSP on the widget | `default-src 'none'`; `connect-src` to your API origin only; hashed/nonced `script-src`; no `unsafe-inline`, no `unsafe-eval`. Render agent output as markdown-to-sanitized-DOM, **never** `innerHTML` |
| `postMessage` discipline | Sender specifies an exact `targetOrigin`, never `'*'`. Receiver validates `event.origin` against an allowlist **and** `event.source` **and** the message schema. Message data is untrusted input, never HTML and never a command |
| No tokens in the iframe URL | Query strings and fragments leak via referrer, history, and logs. Use a `postMessage` handshake after load |
| Permissions Policy | Explicitly deny camera, microphone, geolocation, clipboard-read, and anything else unneeded |
| Cookies | Prefer a token in the iframe's own memory. If cookies are unavoidable: `SameSite=None; Secure; HttpOnly; Partitioned` (CHIPS) |

## What the iframe may hold

**Exactly one thing: a short-lived, audience-bound session token, minted by the customer's backend,
scoped to one conversation, carrying the end user's identity claims if any exist.**

- **Never a resource-plane credential.** Not encrypted, not "temporarily," not for a single call.
  Anything in the browser is readable by the page, by extensions, by the user, and by any XSS on the
  host page.
- **Never a model-plane credential.** Same reasoning, plus it turns the customer's LLM key into a
  public inference endpoint anyone with devtools can extract and resell.
- **Minted server-side by the customer**, not by the widget, and not by an endpoint the browser can
  call unauthenticated. The customer's backend knows who the user is; the widget does not.
- **Lifetime in minutes**, refreshed through the customer backend, revocable per conversation.
- **Audience is your API**, validated on **every** request — check the tenant binding per request,
  not just at session start. A token minted for tenant A must be unusable for tenant B.

The session flow deliberately puts the **customer's backend in the trust path for every session**.
It is the only party that knows who the end user is and the only one that can decide whether this
user gets a session at all. **A widget that mints its own sessions is a public, unauthenticated
entry point to an agent holding production credentials.**

## Cost abuse is a first-class control, not a nice-to-have

An anonymous public widget is an open inference endpoint funded by the customer's model-plane
credential. **Per-session token caps, per-IP and per-tenant rate limits, and a tenant-level daily
spend ceiling that hard-stops** (stops, not alerts) are all mandatory. Without them the widget is a
free-inference faucet and someone will find it.

## Sequencing

**Ship HTTP/SSE with authenticated callers first; the iframe is explicitly "not yet."** Its
prerequisites are end-user identity propagation into tool calls, per-session budget enforcement,
egress control, and a completed authorization story — all of which the HTTP/SSE tier needs anyway.

The trap to name out loud: **the iframe is simultaneously the highest-risk surface and the most
demo-able one.** That combination is why it needs an explicit, written "not yet" rather than a
silent absence from the roadmap.

**The written "not yet" now exists as an owner decision, 2026-08-02.** `plan.md` OD-08 ships the
product **self-hosted** and defers the iframe **with** the fully-hosted tier
(`research/14-architecture-synthesis.md` D-20, D-08, O-05). Three things follow for anyone applying
this skill in this repository.

1. **The deferral is not a scheduling accident and must not be re-argued as one.** OD-07 requires the
   emitted stack to carry a **general fallback path** — meaning shell — so an anonymous browser
   surface over the v1 agent is the lethal trifecta complete rather than in part. The capability table
   above is the answer; "harden the sandbox instead" is still rejected.
2. **A self-hosted deployment has nowhere natural to put an anonymous browser session.** The surface
   that would host one is the hosted tier, which is why the two defer together. Do not design a
   single-tenant iframe as a shortcut to shipping one sooner.
3. **The live v1 obligation is negative and cheap: no serving-layer, session-token, or credential
   decision may foreclose a weaker anonymous tier later.** That is D-20's first discipline — never
   assume co-location, and keep the boundary explicit even when everything is on `localhost` — applied
   to this surface. Anonymous-session handling stays in the design; only its implementation waits.
