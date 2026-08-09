# The admission fixture set

**T075**, **FR-053**. Fourteen recorded origin responses covering every state
`src/analysis/admission.py` can classify, each with an asserted expected output.
Scored by `tests/contract/test_admission.py` (**T076**, **SC-018**).

Read `__init__.py`'s docstring for the case format and for why a case is a
*response* rather than a specification document. This file is the map.

## The cases, by state

| state | admitted | criterion | cases |
|---|---|---|---|
| `published_non_empty` | **yes** | `ADM-001` | `published-reference-app`, `published-single-operation` |
| `absent` | no | `ADM-002` | `absent-not-found`, `absent-gone`, `absent-no-location-configured` |
| `unreadable_by_credential` | no | `ADM-003` | `unreadable-unauthorized`, `unreadable-forbidden`, `unreadable-proxy-authentication-required` |
| `readable_no_operations` | no | `ADM-004` | `readable-no-operations` |
| `unparseable` | no | `ADM-005` | `unparseable-openapi`, `unparseable-not-json`, `unparseable-operation-without-id` |
| `unreachable` | no | `ADM-006` | `unreachable-connection-refused`, `unreachable-server-error` |

The first four rows are FR-044's own four states, in the requirement's order.
The last two are additive and every case in them is rejected, so the admitted
set is exactly the first row. `src/analysis/admission.py`'s docstring says why
each addition exists rather than being folded into one of the four.

## Why each state has more than one case, where it does

A state with one case is scored by one response, and a classifier that
recognised only that response would pass. So `absent` carries three statuses,
`unreadable_by_credential` three, `unparseable` three shapes, and `unreachable`
both a status-bearing and a status-free form.

`readable_no_operations` is the exception and has one case, because the state
has one shape: a fetch that succeeded completely and a document describing zero
operations. Multiplying it would multiply the same response. What that state has
instead is a **mutation control** — `published-reference-app` with its operation
list emptied and nothing else changed must land here — which is a stronger
assertion than a second identical case would be.

## What makes the admissible cases non-vacuous

Two things, both in `tests/contract/test_admission.py`:

1. **`operation_ids`.** The reference-application case asserts five specific
   identifiers in order. A classifier that returned `published_non_empty` for
   every input would satisfy `state` and would not reproduce those.
2. **The mutation controls.** Each admissible case is mutated in exactly one
   recorded property — status to 404, status to 401, status to 502, the
   operation list emptied, the body replaced with an unsupported shape — and
   each mutation must move the state to one specific other state. That is what
   turns "this case is admissible" into "this case is admissible *because* the
   status is 200 and the document parses and it describes at least one
   operation", which is the claim the set actually needs to support.

A control that carried the treatment is a failure this repository has already
recorded, and an admissible fixture that was admissible for an incidental
reason would be that failure here.

## Regenerating

Nothing here is generated. `published-reference-app` reads T116's committed
`served_operations.json` through a relative `body_file` rather than copying it,
so the one document that could drift out of step with a real application does
not exist twice. Every other body is written by hand and small enough to read.
