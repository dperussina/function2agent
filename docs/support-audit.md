# Support audit — T190, FR-053, SC-027

This is the checkable record, not an essay. `tests/contract/test_support_audit.py`
walks the same live surfaces. A later sentence that claims support for a
language, framework or target shape with no committed fixture and asserted
expected output fails that test.

**SC-027**: an audit of every statement of what the product supports finds
**zero** supported languages, frameworks or target shapes for which no
committed fixture and asserted expected output exist.

**Not this audit.** T172 already walked the Linux-only platform statement.
This file does not retarget it. Implementation languages (Python 3.12 for
analysis / runtime / supervisor; Go for the enforcement point) are how the
product is built, not a claim about which customer languages are supported.

## Surfaces walked

The list is the population, not an example. Dated findings, research, harness
results and tests stay off the walk (frozen-sites). Fixture paths below are
the evidence a support claim must point at; they are not themselves walked
as product claims.

| Path | Why it is an external support-statement surface |
| --- | --- |
| `README.md` | Product thesis and current-state claims |
| `docs/spec-kit-workflow.md` | Operator-facing process doc under `docs/` |
| `deploy/compose/compose.yaml` | Compose comments |
| `src/supervisor/main.py` | Operator strings |
| `src/runtime/main.py` | Operator strings |
| `src/analysis/admission.py` | Operator-facing ADM-005 support statement and `SUPPORTED_SPECIFICATION_SHAPES` |
| `specs/002-spec-aware-agent-runtime/quickstart.md` | Operator path |
| `specs/002-spec-aware-agent-runtime/plan.md` | Language / framework / target-shape plan statements |
| `pyproject.toml` | Packaging description an installer reads |

## Fixture-backed — the only support claims we may make

Each row has a committed fixture **and** an asserted expected output. Adding a
language, framework or target shape without both, in the same change, is not
support. Recording "no fixture, therefore not a support claim we may make" is
the honest close; inventing a fixture to close a gap is not.

| Claim | Kind | Fixture | Asserted expected output | Asserted by |
| --- | --- | --- | --- | --- |
| Five derivation rules over hand-written Python | language | `tests/fixtures/analyzer/inventory-service/service.py` | `tests/fixtures/analyzer/inventory-service/expected.json` | `tests/unit/test_derive.py` |
| Hand-written Python, no rule fires | language | `tests/fixtures/analyzer/no-derivable-checks/opaque.py` | `tests/fixtures/analyzer/no-derivable-checks/expected.json` | `tests/unit/test_derive.py` |
| `served_operation_set` published specification | target shape | `tests/fixtures/reference-app/served_operations.json` | `tests/fixtures/admission/published-reference-app/expected.json` | `tests/contract/test_admission.py` |
| HTTP reference application | target shape | `tests/fixtures/reference-app/app.py` | `tests/fixtures/reference-app/questions.json` | `tests/unit/test_reference_app.py` |

`SUPPORTED_SPECIFICATION_SHAPES` in `src/analysis/admission.py` is exactly
`served_operation_set`. Widening it without a fixture is a product-behaviour
change this audit refuses.

No framework is in this table. The analyzer fixtures import nothing and have
no route table. Finding 007's figures are about a real framework's published
schema and are not a claim about this analyzer.

## Recorded unsupported — no fixture, therefore not a support claim we may make

Live surfaces that name these do so as a refusal (FR-053: unsupported rather
than best-effort), or do not name them as supported. A later "supports X"
without a row in the table above fails the contract test.

| Name | Kind | Why unsupported | Live-surface status |
| --- | --- | --- | --- |
| TypeScript | language | No committed fixture, no asserted expected output | README: nothing here reaches another language. Not claimed as supported. |
| FastAPI, Flask, Django | framework | Analyzer fixtures are not a framework | Not claimed as supported on a live surface. |
| OpenAPI, JSON Schema, gRPC reflection, WSDL | target shape | Admission classifies them `unparseable`; ADM-005 says so to the operator | `src/analysis/admission.py` names them unsupported rather than best-effort (FR-053). |
| Agent frameworks (ADK and others) | framework | OD-15: no agent framework in v1 | `plan.md` states no agent framework. |

README's "HTTP/RPC" is D-01's invocation convention (tools call the target over
its existing external interface, never in-process). HTTP as a
`served_operation_set` target has the fixture row above. RPC / gRPC as a
target shape does not, so it is not a support claim we may make.
