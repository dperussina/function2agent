# Open definitions — T195, FR-038, SC-012

This is the checkable record, not an essay.
`tests/contract/test_open_definitions.py` walks this file. A later sentence
that invents a definition for a term this file marks undefined fails that
test; updating this file without updating the walk does not hide it.

Loose-requirements item 1: **FR-038** and **SC-012** ask for per-node trace
records including an explicit distinction between a *retry* and a *repair*.
The requirement names the distinction. Nothing in the corpus defines either
term. v1 emits no graph, no nodes, and no routing — Principle II's deviation
record is accepted on exactly that ground. The rewrite of FR-038 treated the
distinction as already having a v1 subject and carried it through unchanged;
having a subject is not a definition.

**The distinction between a retry and a repair is undefined in this specification.**

Recording that gap is the close. Inventing a retry definition, or a repair
definition, to make the requirement look complete is not. T194 maps the
per-node record onto v1's nearest subject and is not this file.
