# The reference application

**T116**, **FR-053**. A synthetic workload with seeded state, known-correct
answers, and a stated size.

Phase 3 built a runtime that runs a turn, journals it, prices it, resumes after
a kill and serves over HTTP. What it had never done is run against anything.
This is the something.

## Files

| file | what it is |
|---|---|
| `app.py` | the application: five operations, one of them a write |
| `seed.py` | the generator for the state and the answers, and the attestation scheme |
| `size.py` | the measurement behind the table below |
| `state.json` | 11 parts, 44 shipments, committed |
| `questions.json` | four questions, each with an answer **and** an evidence digest |
| `served_operations.json` | the published specification, a `served_operation_set` |
| `size.json` | the measurement output |

Regenerate the three generated files with

```
python tests/fixtures/reference-app/seed.py
```

It is idempotent, and `tests/unit/test_reference_app.py` fails if the committed
files and the generator have drifted apart.

## The stated size

**T203** requires this size to be reported wherever **SC-001** appears, because
SC-001's fifteen-minute window contains an unbounded analysis step and **U-21**
records `codegraph`'s scale claim as untested on a single small-repository
datapoint. A wall time reported without its denominator is not a rate.

Measured by `size.py`, asserted against this table by
`test_the_readme_states_the_size_that_was_measured`:

| figure | value |
|---|---|
| `application_files` | 3 |
| `application_lines` | 606 |
| `application_code_lines` | 442 |
| `application_definitions` | 32 |
| `seeded_parts` | 11 |
| `seeded_shipments` | 44 |
| `served_operations` | 5 |
| `questions` | 4 |

### How each figure was taken, and what it does not mean

- `application_files` counts the files named in `size.py::APPLICATION_SOURCES`
  — `__init__.py`, `app.py`, `seed.py`. The list is **explicit rather than a
  glob**, so the measuring script and the generated JSON are not counted as
  part of the thing being measured. A glob would inflate the denominator every
  time the fixture grew a helper.
- `application_lines` is every line including blanks, so `wc -l` on those three
  files reproduces it in one command.
- `application_code_lines` excludes blank lines and whole-line `#` comments.
  **It does not exclude docstrings**, and these three files are unusually
  docstring-dense — the gap between 606 and 442 is blank lines, not prose.
  Treat 442 as an upper bound on executable content.
- `application_definitions` counts `def`, `async def` and `class` at any
  nesting depth, via `ast`. It is a cheap proxy for a symbol count, not a
  symbol count.

### What is deliberately not measured

`codegraph_nodes` and `codegraph_edges` are `null`. `codegraph` is invoked by
**T119**, which does not exist, so no node or edge count for this application
has ever been taken. Nothing here converts lines into nodes using U-21's single
datapoint: that ratio has one observation behind it, and a number derived from
it would read as a measurement and be a guess — one that T203 would then
propagate to every place SC-001 appears.

**This application is small.** It is a fixture for correctness and overhead
measurement, not a scale datapoint. It does not test U-21's open question and
should not be reported as if it did.

## Known-correct answers, and which half of one is unforgeable

Each question in `questions.json` carries two correct things.

**`answer`** is a fold over the served business fields. Anything that can read
prices, quantities and statuses reproduces it. This half is **forgeable from
the visible state**, and it is here because it still catches a routing, a
filtering or a serialization defect.

**`evidence_digest`** is SHA-256 over the `attestation` values of exactly the
records the answer depends on, in a fixed order. An attestation is

```
HMAC-SHA256(ATTESTATION_KEY, canonical({kind, id, epoch}))
```

and the covered identity **excludes every business field**. No operation serves
the key; no served field determines an attestation. A pipeline that reaches the
right records and preserves what they returned reproduces the digest. A
pipeline that recomputes the answer from the visible fields cannot.

That split is finding 016's lesson — *a conformance assertion must check a
digest, not an answer* — applied to a workload. The proof that it works is a
negative control,
`test_the_lossy_oracle_gets_every_answer_right_and_every_digest_wrong`: an
oracle that reaches the correct records, drops their attestations and
recomputes each answer scores **4/4 on answers and 0/4 on digests**. That gap
is how much conformance signal answer-checking cannot see.

### The exact scope of "unforgeable"

`ATTESTATION_KEY` is committed in `seed.py`, so anyone reading this repository
can compute any attestation. The property is unforgeability **from the served
surface**, and the failure it defends against is a silently lossy pipeline, not
a hostile one. Stated plainly here because an overread version of this claim
would be a security property this fixture does not have.

## Why the state is synthetic

Every record is produced from its own index by arithmetic. Nothing was chosen
by looking at real data, and nothing was chosen by looking at the questions. A
fixture assembled beside the rule it scores is contaminated and cannot score
it; synthetic construction is the contamination-proof alternative and is the
default in this tree.

The arithmetic has one constraint worth knowing before changing it.
`PART_COUNT` is 11 and the status cycle has 3 elements, and **they are coprime
on purpose**. The first draft used 12 parts: 12 and 3 share a factor, so the
part a shipment belonged to and the status it carried had correlated periods,
every shipment of a given part came out with the same status, and two of the
four questions degenerated to an empty evidence set with the answer zero —
while every answer-checking and digest-checking assertion still passed, because
zero equals zero and the digest of an empty list equals the digest of an empty
list. `test_no_question_has_an_empty_evidence_set` is the floor that now
catches it.

## What this unblocks

- **T101** — workload-level supervisor overhead had no workload. `Application`
  is the in-process arm and `build_server` the socket arm; the two are asserted
  to return identical bytes so an overhead figure and a safety assertion are
  measurements of the same program.
- **T114** — zero calls that did not resolve read-only reach the target. The
  target now has exactly one non-read-only operation,
  `POST /shipments/{shipment_id}/cancel`, and a published specification that
  says which one it is. `test_exactly_one_published_operation_is_not_read_only`
  is the vacuity floor on that.
- **T115** — zero reads and zero writes outside the declared set. The declared
  set has a single member, `state_root()`, with no environment variable that
  moves it, because a location that can be reconfigured is a location a battery
  cannot make claims about.

None of those three is discharged here. This is the subject they were missing.
