# Claims audit — T189, FR-043, SC-016

This is the checkable record, not an essay. `tests/contract/test_claims_audit.py`
walks the same live surfaces. A later sentence that adds a prohibited shape
fails that test; updating this file without updating the walk does not hide it.

**SC-016**: an audit of all external product material finds **zero** claims of
capability advantage for an application-specific tool surface, **zero** claims
that synthesis is safer, **zero** cost figures quoted without basis and scope,
and **zero** uses of the word "provably" for effect resolution.

## Surfaces walked

The list is the population, not an example. Dated findings, research, harness
results and tests stay off the walk (frozen-sites, same ruling as T172).
T172's Linux-only platform statement is a different audit; this file does not
retarget it.

| Path | Why it is an external product surface |
| --- | --- |
| `README.md` | First document a reader or operator hits |
| `docs/spec-kit-workflow.md` | Operator-facing process doc under `docs/` |
| `deploy/compose/compose.yaml` | Compose comments an operator reads while deploying |
| `src/supervisor/main.py` | Operator readiness and refusal strings |
| `src/runtime/main.py` | Operator readiness and refusal strings |
| `specs/002-spec-aware-agent-runtime/quickstart.md` | Operator path |
| `specs/002-spec-aware-agent-runtime/plan.md` | Plan surfaces that state product shape |

`docs/` is walked as a tree so a prohibited sentence landing in a new doc is
caught. This file and `docs/support-audit.md` sit in that tree; they record the
prohibition and are protected by the same refusal window the scan uses for
FR-043 / SC-016 restatements.

## The four prohibited shapes

For each shape: either an offending sentence quoted with its path, or
**none found**, with the walk that would have caught a later sentence.

| Shape | Finding | Walk that would catch a later sentence |
| --- | --- | --- |
| Capability advantage for an application-specific tool surface | **none found** | `capability_advantage_hits` in `tests/contract/test_claims_audit.py`. Live README states the capability half is not supported and the curated surface never won on success rate; those sit next to a refusal and are not this shape. |
| Synthesis is safer | **none found** | `synthesis_safer_hits` in the same test. Live README restates C-18: the phrase may not be asserted at all. A restatement next to that refusal is not a claim. |
| Cost figure without basis and scope | **none found** | `cost_without_basis_hits` in the same test. Discovery spend on README cites `VERDICT.md`; the within-session multiplier cites finding 012 and D-19; compose states FR-049's cgroup cost with its actual scope (the host's entire cgroup tree); the runtime readiness line echoes the operator-configured FR-005 spend ceiling. A bare money figure or a costing-multiplier with no such nearby citation fails. |
| "provably" for effect resolution | **none found** | `provably_effect_hits` in the same test. No live surface uses the word next to effect resolution. The scan fires on a planted "provably resolves" sentence; a refusal window (zero uses, prohibited, none found, SC-016) keeps this table from matching itself. |

## Frozen sites

Off the walk, because they are dated records or skip reasons, not product
claims: `specs/*/findings/`, `research/`, `specs/*/harness/`, `tests/`.
