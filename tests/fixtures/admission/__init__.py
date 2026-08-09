"""T075 — the admission fixture set: every FR-044 specification state, committed.

**Requirement**: FR-053 — *a target shape is supported only where a committed
fixture and an asserted expected output for it exist*, and *every measurable
outcome that names a fixture set MUST have that fixture committed alongside the
capability it exercises rather than assembled when the measurement falls due*.
SC-018 is the measurable outcome; `src/analysis/admission.py` is the capability;
this directory is committed in the same change as both.

## What a case is, and why it is a *response* rather than a document

Each subdirectory is one **recorded origin response**, not one specification
document. `response.json` says what an origin did — a status, a body, or a
transport failure — and `expected.json` says which state
`src/analysis/admission.py` must classify it into and which criterion must fire.

The split matters and it is the reason this set can score the classifier at all.
Three of FR-044's four states are **not properties of a document**: `absent` has
no document, `unreadable_by_credential` has a document nobody read, and
`unreachable` has no answer. A fixture set of specification documents could
exercise exactly two of the six states, and the other four would have to be
produced by mocking the fetch — at which point the test asserts that a mock
returns what it was told to return.

So the transport boundary is where the fixtures sit. `load_response` builds a
`FetchResponse` and hands it to the real `classify`. Nothing in this package
imports a state name in order to produce one: `response.json` contains statuses
and bytes, and the state is the classifier's answer.

## The asserted expected output

`expected.json` carries, per case:

| field | what it asserts |
|---|---|
| `state` | the FR-044 state `classify` must return |
| `admitted` | whether `check` admits it. `true` for exactly the two published cases |
| `rule_id` | the `ADM-` criterion that must fire |
| `operation_ids` | for an admissible case, the operations the specification describes, in order. `[]` otherwise |
| `exercises` | prose: *why this response is in that state*, written before the classifier was run against it |

`operation_ids` is the half that makes an admissible case an assertion rather
than a tautology. A classifier that returned `published_non_empty` for
everything would satisfy `state`; it would not reproduce five specific operation
identifiers in order.

## The admissible case is the reference application's own published file

`published-reference-app/response.json` points its body at
`../../reference-app/served_operations.json` rather than carrying a copy. A copy
would be a second file to keep in step with T116's, and the reconciliation
`tests/unit/test_reference_app.py` performs between `ROUTES` and that document
would not cover it — so the copy could drift into describing a surface the
reference application does not serve, and this set would go on admitting it.

**One thing the reference application does not do**, recorded because it looks
like it does: it does not *serve* its specification over HTTP. `app.py` publishes
five operations and none of them is the specification, so a live admission check
against `build_server` would classify `absent` and reject it. The document is
fetched from the file it is committed as. `fetch_over_http` is exercised against
a purpose-built loopback origin in `tests/contract/test_admission.py` instead,
because an HTTP transport whose only evidence was a recorded response would be
an untested transport with a fixture in front of it.

## What is deliberately not here

- **No OpenAPI case that is expected to be admitted.** `unparseable-openapi` is
  a real OpenAPI 3 document and it is expected to be *rejected*, because FR-053
  makes a shape supported only where a committed fixture and an asserted
  expected output exist and there is no OpenAPI parser to assert one against.
  The case is here so that the rejection is the one an operator can act on —
  `ADM-005` names the shape and says so — rather than a misreport as "your
  specification is empty".
- **No case whose expected state was read off a run.** Every `exercises` line
  states the property of the response that puts it in its state, and the states
  were written from FR-044's text.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from src.analysis.admission import FetchResponse

HERE = Path(__file__).resolve().parent
#: Everything a `body_file` may resolve inside. A case may reach a sibling
#: fixture — the admissible case reaches the reference application's published
#: document on purpose — and may not reach outside the fixture tree.
FIXTURE_ROOT = HERE.parent

#: The two fields every case must state and the extra one an admissible case
#: must state. Enumerated so a case that forgets one fails at load time rather
#: than producing a `None` some assertion compares equal to.
_REQUIRED_EXPECTATIONS = ("state", "admitted", "rule_id", "operation_ids",
                          "exercises")


class FixtureError(RuntimeError):
    """A case that is not usable as an expected output."""


@dataclass(frozen=True)
class AdmissionCase:
    """One recorded response and the outcome it asserts."""

    name: str
    directory: Path
    #: The raw `response.json`, so a test can assert on the *evidence* rather
    #: than only on the verdict — for instance that `readable-no-operations`
    #: really did carry status 200 and a parseable body, which is the specific
    #: thing FR-044 forbids reading as a deployment that serves nothing.
    response_document: Mapping[str, Any]
    expected: Mapping[str, Any]

    @property
    def expected_state(self) -> str:
        return str(self.expected["state"])

    @property
    def expected_admitted(self) -> bool:
        return bool(self.expected["admitted"])

    @property
    def expected_rule_id(self) -> str:
        return str(self.expected["rule_id"])

    @property
    def expected_operation_ids(self) -> tuple[str, ...]:
        return tuple(str(o) for o in self.expected["operation_ids"])

    def response(self) -> FetchResponse:
        """The recorded response as the classifier's input."""
        return _build_response(self.name, self.directory, self.response_document)

    def response_with(self, **overrides: Any) -> FetchResponse:
        """The same response with one recorded field changed.

        This is what the mutation controls in `tests/contract/test_admission.py`
        use. Changing exactly one property of a case that is admitted, and
        requiring the state to move to a specific other state, is how "this
        fixture is admissible" becomes "this fixture is admissible *because of
        this property*" — a control that carried the treatment is the failure
        this repository has already recorded once.
        """
        document = {**self.response_document, **overrides}
        return _build_response(self.name, self.directory, document)


def _resolve_body(name: str, directory: Path, body_file: str) -> bytes:
    candidate = (directory / body_file).resolve()
    if not candidate.is_relative_to(FIXTURE_ROOT):
        raise FixtureError(
            f"{name}: body_file {body_file!r} resolves to {candidate}, outside "
            f"{FIXTURE_ROOT}. A case that reads outside the fixture tree is a "
            "case the removal-proof harness cannot run — its working copy "
            "takes `tests` and not the whole checkout — and it would be "
            "reported as UNUSABLE rather than as a broken proof."
        )
    if not candidate.is_file():
        raise FixtureError(f"{name}: body_file {body_file!r} is not a file")
    return candidate.read_bytes()


def _build_response(
    name: str, directory: Path, document: Mapping[str, Any]
) -> FetchResponse:
    body: bytes | None = None
    if document.get("body_file") is not None:
        body = _resolve_body(name, directory, str(document["body_file"]))
    elif document.get("body_text") is not None:
        body = str(document["body_text"]).encode("utf-8")
    elif document.get("body_bytes_hex") is not None:
        body = bytes.fromhex(str(document["body_bytes_hex"]))
    return FetchResponse(
        status=document.get("status"),
        body=body,
        location=str(document.get("location", "")),
        transport_error=document.get("transport_error"),
    )


def load_cases() -> tuple[AdmissionCase, ...]:
    """Every case in this directory, in name order.

    Discovered from the filesystem rather than listed in a constant. A constant
    would be a second place the set is stated, and the failure it invites is a
    case committed and never scored — which is a fixture that exists and
    measures nothing.
    """
    cases: list[AdmissionCase] = []
    for directory in sorted(p for p in HERE.iterdir() if p.is_dir()):
        if directory.name.startswith("__"):
            continue
        response_path = directory / "response.json"
        expected_path = directory / "expected.json"
        for path in (response_path, expected_path):
            if not path.is_file():
                raise FixtureError(
                    f"{directory.name}: {path.name} is missing. FR-053 wants a "
                    "committed fixture **and** an asserted expected output; a "
                    "directory with only one of the two is half a fixture."
                )
        expected = json.loads(expected_path.read_text())
        missing = [k for k in _REQUIRED_EXPECTATIONS if k not in expected]
        if missing:
            raise FixtureError(
                f"{directory.name}: expected.json is missing {missing}"
            )
        cases.append(AdmissionCase(
            name=directory.name,
            directory=directory,
            response_document=json.loads(response_path.read_text()),
            expected=expected,
        ))
    if not cases:
        raise FixtureError(
            "no cases found. An empty fixture set makes every assertion over "
            "it true, which is the vacuous pass this set exists to prevent."
        )
    return tuple(cases)


def cases_by_state() -> dict[str, tuple[AdmissionCase, ...]]:
    """The cases grouped by the state they assert, for the coverage floor."""
    grouped: dict[str, list[AdmissionCase]] = {}
    for case in load_cases():
        grouped.setdefault(case.expected_state, []).append(case)
    return {state: tuple(members) for state, members in grouped.items()}
