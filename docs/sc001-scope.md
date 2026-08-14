# SC-001 scope — T203, U-21

This is the checkable record, not an essay. `tests/contract/test_sc001_scope.py`
walks this file and the live surfaces that report SC-001. A later sentence that
invents a node count for the reference application, claims U-21 closed, or
reports SC-001 without these figures and without pointing here fails that test.

**SC-001 reports cite this file.** A wall time without its denominator is not
a rate. U-21's scale claim is untested and extrapolates nothing.

## The reference application's stated size

Quoted from the T116 done-note, measured by `size.py` and asserted against
`tests/fixtures/reference-app/README.md`. **These figures are not re-derived
here, and lines are not converted into nodes.**

> The stated size, measured by `size.py` and asserted against `README.md`: 3 application files, 606 lines, 442 non-blank non-comment lines, 32 `def`/`class` definitions, over 11 seeded parts and 44 seeded shipments, 5 served operations and 4 questions. `codegraph_nodes` and `codegraph_edges` are deliberately `null` — `codegraph` is invoked by T119, which does not exist, so **no node count for this application has ever been taken** and nothing here converts lines into nodes using **U-21**'s single datapoint. T203 must report the figures above and that gap, not a derived node count. **This application is small and is not a scale datapoint**; it does not test U-21's open question.

| figure | value |
| --- | ---: |
| `application_files` | 3 |
| `application_lines` | 606 |
| `application_code_lines` | 442 |
| `application_definitions` | 32 |
| `seeded_parts` | 11 |
| `seeded_shipments` | 44 |
| `served_operations` | 5 |
| `questions` | 4 |
| `codegraph_nodes` | `null` — never taken |
| `codegraph_edges` | `null` — never taken |

T119 is now a PARTIAL subprocess wrapper (`src/analysis/codegraph.py`). That
does not close the gap: the wrapper has never been pointed at this
application, so **no node or edge count for the reference application has
ever been taken**. A number derived from that line count and U-21's one ratio
would read as a measurement. It is not written here.

**This application is small and is not a scale datapoint.** It does not
test U-21's open question.

## The one measured `codegraph` datapoint

Not this application. T004 / T119 notes: `codegraph` was built from the
vendored tree and run against a copy of **`adk-python`**, indexed at
**1,867 files, 48,154 nodes, 149,714 edges**. The same build indexed
`labs-OO-Agents` (951 files) and `claude-agent-sdk-python` (109 files) as
controls; one digest for all three.

U-21 records the vendor scale claim (70k files / 2M symbols / 6.4M edges /
<12 min) as **untested**. The `adk-python` index is roughly 2.7% of the
claimed file count and **extrapolates nothing**. U-21 is **open**.

T118 already instruments analysis wall time separately from the rest of
the SC-001 window (`src/analysis/timing.py`). An analysis span taken
today times a step that does not include the unbounded work U-21 is
about (`codegraph_invoked` defaults `False`). That instrument is not a
datapoint against U-21.

## Where SC-001 is reported

A report that names SC-001 without this size and this gap, and without
pointing here, is the failure the contract test exists to catch.

| Surface | How it carries the figures |
| --- | --- |
| This file | The record |
| `src/analysis/timing.py` | `SubjectSize`; `codegraph_nodes` stays `None`; cites U-21 |
| `tests/fixtures/reference-app/README.md` | The T116 table; nodes deliberately `null` |
| `tests/batteries/results/sc001-first-answer.json` | `subject_size` with `codegraph_nodes: null`; `assessable: false` |
| `specs/002-spec-aware-agent-runtime/quickstart.md` | Cites this file |

`specs/002-spec-aware-agent-runtime/spec.md` defines the criterion and is
not amended here.
