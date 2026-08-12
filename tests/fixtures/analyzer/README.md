# Analyzer fixtures — T135

**Requirement**: FR-053, and constitution Principle VII's analyzer clause —
*"every supported language and framework MUST have a committed fixture
repository plus asserted expected decomposition. Language support without a
fixture is not supported."*

**Exercised by**: [`tests/unit/test_derive.py`](../../unit/test_derive.py).

## The inventory

| Fixture | What it is for | Correct derivation |
| --- | --- | --- |
| [`inventory-service/`](./inventory-service/) | All five derivation rules, over three functions | 3 contracts, 6 checks, 3 of them recomputations |
| [`no-derivable-checks/`](./no-derivable-checks/) | Source no rule fires on | **empty** |

The second one is not filler. An analyzer scored only where it succeeds cannot
be distinguished from one that emits a contract for every function it sees, and
*fluent, plausible and wrong* is the failure class this corpus has measured
twice by two different mechanisms — finding 004's confidently-wrong `docstring`
values, and finding 007's alias-generator result, where disabling one derivation
rule left **15 of 69 endpoints with a contract wrong about every field name on
the wire and nothing in the output indicating it**. A negative fixture is the
cheapest instrument against that, and it is the one a positive-only suite lacks.

## What "known-correct" means here

`expected.json` in each directory was **written from the source by hand, before
the analyzer existed**, and the analyzer was then made to match it. It was not
recorded from a run and then frozen.

That direction is the whole point and it is worth being precise about, because
the two constructions produce files that look identical and mean opposite
things. An expectation recorded from a run asserts that the analyzer still does
what it did — a change-detector. An expectation written from the source asserts
that the analyzer does what a careful reader of the source says it should. Only
the second can find the analyzer wrong on the day it is written.

**The one exception, labelled rather than buried.** `provenance.content_hash` is
a *computed* value recorded in the file, not a hand-derived one; nobody can
hand-compute a SHA-256. Its role is coupling, not expectation: editing
`service.py` turns `test_the_committed_source_hashes_still_match_the_fixture`
red, which forces the hand-written expectation beside it to be re-read rather
than silently outgrown. That is FR-028's requirement — *a source change that
invalidates a derived contract MUST be detected in the same automated check run
as the change* — at fixture scale.

## Why the fixtures are synthetic

This repository's recorded position is that synthetic fixtures are the
contamination-proof construction and are the default. The alternative — deriving
fixtures from the same source the checker was written against — makes the
checker's coverage undecidable: you cannot tell a rule that generalizes from a
rule that memorized the one repository it was developed on.

`service.py` and `opaque.py` therefore import nothing, depend on nothing, and
are written to be read. Every function in `service.py` exists to exercise a
named rule or a named combination, and its docstring says which.

## What these fixtures do and do not make supported

They make **these five rules over hand-written Python** a supported shape under
FR-053, and nothing wider. Specifically:

- **Not a framework.** No FastAPI, no decorators, no route table. Finding 007's
  0.8696 literal / 0.7681 validated figures are about a real framework's
  published schema and are **not** a claim about this analyzer.
- **Not a second language.** There is no TypeScript fixture, so TypeScript is
  unsupported rather than best-effort, which is what FR-053 requires it to be
  described as.
- **Not a scale datapoint.** Two files. Nothing here says anything about how the
  derivation behaves over 48,154 nodes.

Adding a language or a rule requires its fixture and its hand-written expected
output **in the same change**, per Principle VII's last line.

## Adding a fixture

1. Write the source. Import nothing.
2. Write `expected.json` from the source, by hand, before running anything.
3. Run the test. If it disagrees, decide which of the two is wrong **on the
   source**, and say so in the commit. Updating the expectation to match the
   output is how a fixture stops being evidence.
4. Fill `content_hash` from the run, once the structure is agreed.
