# Fixture data model

The clean counterpart. Its table agrees with `src/contracts/terminal.py` and
carries, alongside the agreement, every construct that a narrower check would
report as a defect.

## 2.1 Session

**Lifecycle — the shape.**

```text
CREATED ─▶ RUNNING ─┬─▶ TERMINATED  ⟨terminal_state⟩
                    └─▶ INTERRUPTED ─▶ RUNNING
```

**Lifecycle — the terminal states.**

| Terminal state | Requirement | Status |
|---|---|---|
| `terminated.completed` | `FR-006` | member |
| `terminated.spend_ceiling_reached` | `FR-005` | member |
| `terminated.operator_terminated` | `FR-006` | member |
| `terminated.no_progress` | `FR-006` | owed — the predicate is unwritable as specified |
| ~~`terminated.denied_operation`~~ | — | struck — no requirement wants it |

Four constructs here have produced, or would produce, a false positive:

- An `owed` row naming a state the taxonomy does not carry. That is a recorded
  debt, not a divergence, and a membership-only comparison reports it.
- A `struck` row, kept visible under the house convention with the name inside
  `~~…~~`. Deleting it would be the only way to satisfy a check that read it.
- A status cell carrying a note after the keyword. The status is the first word;
  a check reading the whole cell finds no recognised status on either row.
- A binding in the taxonomy source that the `TAXONOMY` tuple does not list —
  `terminated.never_adopted`. A parser reading bindings rather than the tuple
  would report it as a member this document had forgotten.

And the fenced decoy, which is not a declaration:

```text
| Terminal state | Requirement | Status |
|---|---|---|
| `terminated.invented_in_a_fence` | `FR-000` | member |
```
