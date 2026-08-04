# Tasks: Fixture Feature

**Input**: [`spec.md`](./spec.md) (9 functional requirements, 4 success criteria)

Two defects, and they are different in kind.

The success-criteria figure is an ordinary stale count: the specification
defines three and this says four. A bare comparison catches it.

The functional-requirement figure is the one a bare comparison does not catch.
Nine is what a human counted by reading the section; zero is what the extractor
returns, because those bullets lost their bold markers. An implementation that
skips when it computes zero — which is what the sibling inventory rule does —
reports this file clean.

**Coverage**: the phase tables below were indexed by hand, because the generator
that would have built them saw 0 functional requirements in the specification
and emitted nothing. That sentence is the negative control. The claim and the
computed truth agree exactly, both are zero, and the agreement is worthless: an
equality test passes it, and what it has actually verified is that nothing was
read.
