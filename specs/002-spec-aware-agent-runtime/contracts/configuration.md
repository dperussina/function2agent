# Contract — Configuration and Credentials

**Requirements**: FR-032, FR-033, FR-036, FR-043, FR-049, FR-050, FR-053

---

## Where configuration enters

Configuration reaches the **runtime** and the **supervisor** through environment injection at process
start, and the **enforcement point** through its own mounted configuration in a separate namespace
that the sandbox cannot reach or modify (FR-012, FR-014).

Configuration never reaches the **execution environment**. Nothing in FR-048's declared mount set
carries a configuration file, and no secret is present in the container's environment or process
state (FR-050). This is the distinction the design turns on: FR-033's injection targets the runtime,
not the environment a shell runs in.

## Required, with no default

Startup **fails with a named reason** when any of these is unset. There is no permissive mode.

| Key | Why it has no default |
|---|---|
| `TARGET_BASE_URL` | there is no sensible default target |
| `TARGET_PINNED_ADDRESSES` | FR-016 requires pinned host-and-port; resolving at run time is the thing being prevented |
| `SANDBOX_MEMORY_MAX` | **FR-049 states no default, because nothing in the evidence base bears on an agent's working set** |
| `SANDBOX_CPU_MAX`, `SANDBOX_CPU_TOTAL` | as above. Two bounds, for the two things SC-023 asks of one requirement ([`../research.md`](../research.md) §3.2) |
| at least one provider credential | FR-032 — bring-your-own-credentials |

**On the two bounds specifically.** This plan recommends failing closed rather than shipping a marked
default (**Q-10**). Shipping a number here would be a configured value with nothing behind it, and
this corpus has repeatedly caught inherited numbers presented as measured ones. If the owner takes
**Q-10** the other way, the shipped value carries FR-043's marking on every external surface and is
never described as validated.

The compose bundle we author for the **reference application** sets these so the fixture batteries
can run. Those are fixture values, marked under FR-043, and they are not product defaults.

## Configured, with a value and no measurement behind it

Each of these has a value in the shipped bundle and **none of them is validated**. Every one carries
FR-043's marking wherever it surfaces externally.

| Key | What it governs |
|---|---|
| `STALENESS_CEILING` | when a result is marked stale (FR-047) |
| `DRIFT_CHECK_INTERVAL` | the scheduled re-fetch (FR-046) |
| `CAPABILITY_LEASE_INTERVAL` | the residual window in FR-050's crash case ([`../research.md`](../research.md) §3.3) |

`CAPABILITY_LEASE_INTERVAL` is the only one this plan introduces. It exists because the alternative —
a self-describing credential with an expiry — is honoured by anyone who can verify it whether or not
anything is alive to revoke it.

## Credentials

| Credential | Held by | Never reaches |
|---|---|---|
| model provider | the runtime | the execution environment, the enforcement point, any trace, any artifact |
| target | the enforcement point, injected on re-origination | the execution environment, the runtime's traces, the model's context |
| the session capability | the execution environment | anywhere it could be verified offline — it is an opaque handle, not a claim |

**Redaction is structural, not a filter.** The credential is not in the container, so there is nothing
in the container to redact. Trace writers accept a `Secret` type that has no serializer, so a
credential cannot be logged by a code path that forgets to redact it.

## Tests owed

- Each required key unset in turn: startup fails, names the key, and starts nothing.
- Malformed values for each key: same.
- A grep-and-shape assertion over a completed session's traces and artifacts: **no credential-shaped
  value present**.
- An assertion inside the running container: **no secret readable** from the environment, the
  process table, or any mount in the declared set (SC-024).
- Every FR-043-marked value appears marked on every external surface that emits it.
