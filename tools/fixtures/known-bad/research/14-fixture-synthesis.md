# 14 — Fixture Synthesis

## Table of contents

- [1. The decision register](#1-the-decision-register)
- [2. Tables that do not render](#2-tables-that-do-not-render)

## 1. The decision register

| # | Decision | Position |
|---|---|---|
| D-01 | **Invocation boundary** | Over the boundary. |
| D-02 | **Process** | Spec Kit drives. |
| D-04 | **Credentials** | BYO everything. Note there is no D-03 row. |

The credential posture was settled by D-04 and is unaffected by D-99, which no
register defines.

## 2. Tables that do not render

A blank line between the header and the last row ends the table. The `web`
row below is in the file, looks right in a diff, and renders as body text.

| Configuration | Served operations |
|---|---|
| `api_server` | 22 |
| `enterprise` | 24 |

| `web` | 67 |

Column counts must match the header:

| Mechanism | What it does | Needed for |
|---|---|---|
| `M1_class_dispatch` | Resolves a conditional class binding. | `ServerClass = DevServer if web else ApiServer` |
| `M2_kwarg_flow` | Binds actual arguments across a call. |

A block of pipe rows with no delimiter row renders as literal text:

| Arm | Precision |
| R1 | 0.9538 |
| R2 | 1.0000 |

## 3. A section the table of contents never learned about

Added after the contents list was written, and therefore unreachable from the
top of the document.

A row two blank lines below its table renders as body text exactly as a row one
blank line below it does, and nothing follows it that would make it a new table:

| Arm | Served |
|---|---|
| R1 | 22 |


| R2 | 24 |

A self-link sits below the contents list rather than inside it, and it is here to
hold `toc.py`'s TOC-locating branch:
[3. A section the table of contents never learned about](#3-a-section-the-table-of-contents-never-learned-about).
Inverted, that branch starts at the H1, sweeps to the next heading of the same or
higher level, finds no second H1, and so collects this link as a contents entry —
which silences the line 44 violation. Located correctly it stops at the H2 above
and never reads this line, so the violation stands.
