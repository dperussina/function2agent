# Fixture data model

The document side of the `lifecycle-taxonomy` fixture. Its table disagrees with
`src/contracts/terminal.py` in every direction the check speaks on, one defect
per direction, so that removing any one branch of the check takes exactly one
expected violation away.

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
| `terminated.turn_ceiling_reached` | `FR-005` | member |
| `terminated.no_progress` | `FR-006` | owed — nothing produces it yet |
| ~~`terminated.denied_operation`~~ | — | struck — no requirement wants it |
| `terminated.cpu_bound_exhausted` | `FR-049` | pending |

Six rows and five planted defects, one per branch:

- `terminated.turn_ceiling_reached` is declared a member and is not one.
- `terminated.operator_terminated` is a member and has no row at all.
- `terminated.no_progress` is marked `owed` and **is** a member. This is the
  negative control for the anti-blindness rule: a marking read only in the
  exempting direction passes this row, and goes on passing it forever once the
  debt is discharged.
- `terminated.denied_operation` is marked `struck` and **is** a member, which
  is the same rule from the other side.
- `terminated.cpu_bound_exhausted` carries a status outside the three. An
  implementation that ignored unknown statuses would reconcile this row against
  nothing and report it clean.

A decoy, which must not be read as a declaration:

```text
| Terminal state | Requirement | Status |
|---|---|---|
| `terminated.invented_in_a_fence` | `FR-000` | member |
```
