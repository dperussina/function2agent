# Contract — Egress Policy at the Single Enforcement Point

**Requirements**: FR-008–FR-019, FR-021, FR-046, FR-050
**Inherited decision**: **OD-12** — one mandatory proxy, destination and method allowlists together,
**re-originating from a cleartext endpoint rather than intercepting TLS**, `CONNECT` denied.

---

## Posture

The execution environment has exactly one reachable address: the enforcement point, over a cleartext
endpoint presented to the agent as the target's base URL. The enforcement point reads the method and
path in the clear (FR-018), resolves the call, and then makes **its own** outbound TLS connection to
the pinned address with ordinary certificate validation.

No CA is installed in the sandbox. No certificate pin is asked of the operator. The sandbox needs no
resolver, because the only address it can reach is reachable by a static hosts entry.

**This works because v1 has exactly one legitimate destination whose base-URL string we control**, and
**OD-12** records that it does not generalize past that. The boundary is carried forward, not
inherited.

## Request pipeline

Each stage is fail-closed; reaching the next stage requires an explicit allow.

1. **Capability** — resolve the opaque session handle against the session table. Honoured only when
   the session is `RUNNING` **and** the lease is unexpired. There is nothing in the handle to verify.
2. **Form** — `CONNECT` denied. `Upgrade` denied. Non-HTTP bytes have nothing to speak to. Ambiguous
   framing (conflicting length and chunking headers) rejected outright rather than normalized, so the
   enforcement point and the target cannot disagree about what the request is.
3. **Destination** — origin-form paths, or absolute-form `http` targets naming the pinned origin,
   which is how a URL echoed out of a response body still works ([`../research.md`](../research.md)
   §1.3(a)). Absolute `https` is denied with a **named reason and a counter**. Anything else denied.
4. **Address class** *(stated 2026-08-03; FR-017 governs it and this pipeline did not name it.
   Amended later the same day, when the owner extended the exemption to a declared loopback origin)*
   — the resolved address is checked against the denied classes. ~~**Loopback and link-local,
   including the cloud metadata address at 169.254.169.254, are denied unconditionally with no
   exemption path.** RFC1918 is denied except for the single explicitly declared target origin~~
   **Link-local, including the cloud metadata address at 169.254.169.254, is denied unconditionally
   with no exemption path** — as are unique-local and the unspecified address. **RFC1918 and
   loopback** are denied except for the single explicitly
   declared target origin, and that exemption is keyed to the one address FR-016 already pins — it is
   **not** a range, a prefix or a configuration toggle, because each of those turns one declared
   exemption into a class exemption with no edit to the requirement. **Two exemptible classes, one
   exemption**: which class the declared origin falls in decides whether an exemption may be built at
   all, never how many may exist, so a deployment cannot hold one of each. Stage 3 checks the *name
   and form* of the destination; this stage checks what it *resolves to*, and the two are separate
   because an allowlisted host is exactly how a denied address gets reached.
5. **Method** — against the allowlist. Destination and method are evaluated **together**, never
   separately: this is the property **OD-12** tested for and the reason a `CONNECT`-oriented proxy
   was rejected, since it sees a host and a port and silently degrades a method allowlist into a
   destination one.
6. **Effect resolution** — match the path against the served-operation set; consult the deny list of
   known side-effecting reads; resolve the tier **per call** (FR-008, FR-009, FR-010). Resolution
   **blocks** the call — the disposition is decided before anything is sent (FR-008).
7. **Unresolvable** — an operation the served set does not describe is **denied**, not guessed
   (FR-010).
8. **Re-originate** — inject the target credential, connect out to the pinned address, validate the
   certificate.

## Denials

Every denial records the **rule identifier**, the method, the path, the resolved tier, the session,
and the named reason (FR-011). A denial with no rule identifier fails the invariant suite.

Named reasons include, at minimum: `capability_not_honoured`, `session_terminated`, `lease_expired`,
`method_not_allowed`, `destination_not_allowed`, `absolute_https_denied`, `connect_denied`,
`upgrade_denied`, `ambiguous_framing`, `operation_unresolvable`, `known_side_effecting_read`, and
— added 2026-08-03 with stage 4 — `address_class_denied`, carrying the class that matched so a
loopback denial and a link-local denial are distinguishable in the record.

`absolute_https_denied` carries a counter deliberately. If it dominates real traffic that is evidence
for revisiting the posture in v2 — which is why the failure is counted rather than worked around
(**Q-07**).

## What is not here

**No TLS interception.** **OD-12** worked it through and rejected it for stated reasons.

**No response-body rewriting.** Rewriting absolute URLs out of responses would apply a content
transformation to untrusted bytes on the enforcement path, creating a new injection surface at the
one component every other safety property depends on. Rejected, not deferred.

**No command classification.** FR-013 forbids satisfying these requirements by inspecting what a
command looks like. Enforcement is on the request, at the network boundary.

**No generated tool surface.** The served-operation set is data this component resolves against
(**OD-09**).

## What else this contract enforces without a second mechanism

**FR-021 — no dependency resolution at run time.** A package fetch is an outbound request to a
destination that is not the target, so stage 3 denies it. Two requirements, one control; nobody
should build a second mechanism for it.

**FR-046 — the drift scheduler's specification re-fetch traverses this same enforcement point.**
Otherwise there is a second, continuous, unenforced path to the target and FR-014's guarantee is true
of the sandbox and false of the system ([`../research.md`](../research.md) §1.3(b)).

## Reachability of the enforcement point itself

Its configuration is in a different mount namespace and is not in FR-048's declared set. Its control
plane is in a different network plane. The sandbox has no `NET_ADMIN`, no raw sockets, and one route.
So "cannot reach, modify, reconfigure or bypass" (FR-014) is a property of the topology rather than
an assertion about intent.

## Tests owed

- A framing-ambiguity corpus: every request the enforcement point forwards is parsed identically by
  the upstream. This is the named failure **Q-01** buys a second language to prevent.
- `CONNECT`, `Upgrade`, absolute `https`, non-HTTP bytes: each denied, each with its named reason.
- Method-and-destination evaluated together: a permitted method to a non-pinned destination denied,
  and a non-permitted method to the pinned destination denied.
- An unresolvable operation denied rather than passed.
- **The address-class stage, both directions** (FR-017): link-local, the metadata address,
  unique-local and the unspecified address denied through an allowlisted host and with no
  configuration that admits them, including a declaration naming one of them as the target; an
  RFC1918 **or loopback** address that is *not* the declared origin denied; the declared origin
  itself permitted in either class. The exemption set is asserted to be **exactly one address** — a
  test that admits a prefix or a range is testing a different rule from the one FR-017 states, and
  so is one that lets a single declaration produce an exemption in each exemptible class.
- The replay fixture, both arms: a handle captured during a session and replayed from inside a later
  session's environment is **denied and recorded**; replayed from a position with no path to the
  enforcement point it is refused by unreachability and recorded only as a drop counter (SC-024,
  [`../plan.md`](../plan.md) Complexity Tracking).
- Every disposition carries a rule identifier.
