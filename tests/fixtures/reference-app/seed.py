"""T116 — the reference application's seeded state, and the answers it makes true.

**Requirement**: FR-053. Regenerate with

    python tests/fixtures/reference-app/seed.py

which rewrites `state.json`, `questions.json` and `size.json` in place and is
idempotent. `tests/unit/test_reference_app.py` fails if the committed files and
this generator disagree, which is the same tripwire `session_conformance.py`
carries and for the same reason: a committed artifact whose generator has moved
under it is a fixture that pins nothing.

## Why the state is arithmetic rather than authored

Every record here is produced from its own index by arithmetic. Nothing was
chosen by looking at a real depot, a real invoice or a real repository, and
nothing was chosen by looking at the questions below. That is deliberate: a
fixture assembled beside the rule it scores is contaminated and cannot score it,
so synthetic construction is the default in this tree.

## The two halves of a known-correct answer, and only one of them is forgeable

Each question in `questions.json` carries **two** correct things:

- `answer` — the value. It is a fold over the *served business fields*, so
  anything that can read prices and quantities can reproduce it. This half is
  forgeable from the visible state and is labelled so.
- `evidence_digest` — SHA-256 over the `attestation` values of exactly the
  records the answer depends on, in a fixed order. An attestation is
  `HMAC-SHA256(ATTESTATION_KEY, {kind, id, epoch})`. **It is not a function of
  any field any operation serves**: the key is served by nothing, and the
  identity it covers deliberately excludes price, quantity, status and name. A
  pipeline that reaches the right records and preserves what they returned
  reproduces the digest; a pipeline that recomputes the answer from the visible
  fields cannot.

That split is finding 016's lesson applied to a workload rather than to a
provider: *a conformance fixture must assert the digest, not the answer.* A
suite that checks only the answer passes while opaque state is silently
dropped, because the answer survives the loss and the digest does not.

**The exact scope of "unforgeable", stated so it is not overread.**
`ATTESTATION_KEY` is committed in this file, so anyone reading the repository
can compute any attestation. The property is unforgeability **from the served
surface** — no sequence of operations discloses the key, and no served field
determines an attestation — and the failure it defends against is a silently
lossy pipeline, not a hostile one.

## What the expected answers are, and are not, independent of

The `answer` values are folded over the seeded state directly, without going
through `app.py`'s dispatch. So they are independent of the *served surface* and
catch a routing, filtering or serialization defect. They are **not** independent
of the seed: both sides descend from the arithmetic below. FR-022's independent
recomputation is a different and stronger property and this fixture does not
claim it.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
for _entry in (str(REPO), str(HERE)):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

from src.contracts.canonical import dumps  # noqa: E402

STATE_PATH = HERE / "state.json"
QUESTIONS_PATH = HERE / "questions.json"
SERVED_OPERATIONS_PATH = HERE / "served_operations.json"

SCHEMA_VERSION = "1.0.0"
SEED_VERSION = "2026.08.08-1"
DEPLOYMENT_ID = "d-reference-app"

#: The epoch the attestations are taken over. Bumping it changes every
#: attestation and every evidence digest while leaving every served business
#: field byte-identical — which is the property `state.json` exists to hold
#: still and `test_reference_app.py` exercises directly.
SEED_EPOCH = "2026-08-08"

#: Committed, because a fixture must be reproducible. Served by nothing, which
#: is what makes an attestation independent of the visible state. See the module
#: docstring for the exact scope of the claim.
ATTESTATION_KEY = b"function2agent/reference-app/attestation/v1"

#: `PART_COUNT` is prime and `SHIPMENT_COUNT` is a multiple of it, so that a
#: part's shipments land on consecutive residues of the status cycle.
#:
#: The first draft used twelve parts, and twelve shares a factor with the
#: three-element status cycle: the part a shipment belongs to and the status it
#: carries were then both functions of `j` with correlated periods, every
#: shipment of a given part came out with the *same* status, and two of the four
#: questions below silently degenerated to an empty evidence set and an answer
#: of zero. Both would have passed a test that only compared answers. Eleven and
#: three are coprime, which is the property being relied on, and
#: `test_no_question_has_an_empty_evidence_set` is the floor that catches the
#: next person who changes one of these two numbers without the other.
PART_COUNT = 11
SHIPMENT_COUNT = 44

#: Enumerated, never written as "everything except cancelled". A classifier
#: stated as a complement is one unknown member away from inverting itself, and
#: this corpus has already been bitten twice by that shape at a kernel gate.
IN_FLIGHT_STATUSES = ("in_transit", "delivered")
STATUSES = ("in_transit", "delivered", "cancelled")


def attestation(kind: str, identifier: str, key: bytes = ATTESTATION_KEY) -> str:
    """The opaque half of a record.

    The covered identity is `{kind, id, epoch}` and nothing else. Adding a
    business field here would make the attestation derivable from the served
    surface and would quietly retire the only unforgeable thing in the fixture.
    """
    identity = {"epoch": SEED_EPOCH, "id": identifier, "kind": kind}
    return hmac.new(key, dumps(identity), hashlib.sha256).hexdigest()


def build_state(key: bytes = ATTESTATION_KEY) -> dict[str, Any]:
    parts = []
    for i in range(1, PART_COUNT + 1):
        part_id = f"P-{i:04d}"
        parts.append(
            {
                "part_id": part_id,
                "name": f"synthetic part {i:02d}",
                "unit_price_cents": 1000 + i * 137,
                "on_hand": 3 + (i * 7) % 41,
                "attestation": attestation("part", part_id, key),
            }
        )

    shipments = []
    for j in range(1, SHIPMENT_COUNT + 1):
        shipment_id = f"S-{j:04d}"
        shipments.append(
            {
                "shipment_id": shipment_id,
                "part_id": f"P-{((j * 7) % PART_COUNT) + 1:04d}",
                "quantity": 1 + (j * 3) % 17,
                "status": STATUSES[j % 3],
                "attestation": attestation("shipment", shipment_id, key),
            }
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "seed_version": SEED_VERSION,
        "deployment_id": DEPLOYMENT_ID,
        "seed_epoch": SEED_EPOCH,
        "parts": parts,
        "shipments": shipments,
    }


# ---------------------------------------------------------------------------
# The questions.
#
# Each is a fold over the state above and a named evidence set. The folds are
# written here rather than in `app.py` on purpose: an expected answer computed
# by the thing under test is not an expected answer.

ATTESTATION_FIELD = "attestation"


def business_projection(state: dict[str, Any]) -> dict[str, Any]:
    """The state with every attestation removed — what the served surface shows.

    Two seeds taken under different keys have byte-identical projections and
    disjoint attestation sets. That pair is the whole statement of what
    "unforgeable from the visible state" means here, and the test asserts it in
    exactly those terms.
    """
    stripped: dict[str, Any] = {}
    for name, value in state.items():
        if isinstance(value, list):
            stripped[name] = [
                {k: v for k, v in row.items() if k != ATTESTATION_FIELD}
                for row in value
            ]
        else:
            stripped[name] = value
    return stripped


def _evidence_digest(attestations: list[str]) -> str:
    return hashlib.sha256(dumps(attestations)).hexdigest()


def _part(state: dict[str, Any], part_id: str) -> dict[str, Any]:
    for row in state["parts"]:
        if row["part_id"] == part_id:
            return row
    raise KeyError(part_id)


def _shipments_for(state: dict[str, Any], part_id: str) -> list[dict[str, Any]]:
    return [row for row in state["shipments"] if row["part_id"] == part_id]


def build_questions(state: dict[str, Any]) -> dict[str, Any]:
    questions: list[dict[str, Any]] = []

    # Q1 — one record, one field product.
    part = _part(state, "P-0007")
    questions.append(
        {
            "question_id": "Q-001",
            "prompt": (
                "What is the total value in cents of on-hand stock for part "
                "P-0007?"
            ),
            "answer_kind": "integer_cents",
            "answer": part["unit_price_cents"] * part["on_hand"],
            "operations": [{"method": "GET", "path": "/parts/P-0007"}],
            "evidence": [{"kind": "part", "id": "P-0007"}],
            "evidence_digest": _evidence_digest([part[ATTESTATION_FIELD]]),
        }
    )

    # Q2 — a filtered fold over a related collection.
    matching = sorted(
        (
            row
            for row in _shipments_for(state, "P-0003")
            if row["status"] == "in_transit"
        ),
        key=lambda row: row["shipment_id"],
    )
    questions.append(
        {
            "question_id": "Q-002",
            "prompt": (
                "How many units of part P-0003 are on shipments whose status is "
                "in_transit?"
            ),
            "answer_kind": "integer_units",
            "answer": sum(row["quantity"] for row in matching),
            "operations": [
                {"method": "GET", "path": "/shipments?part_id=P-0003"}
            ],
            "evidence": [
                {"kind": "shipment", "id": row["shipment_id"]} for row in matching
            ],
            "evidence_digest": _evidence_digest(
                [row[ATTESTATION_FIELD] for row in matching]
            ),
        }
    )

    # Q3 — an argmax over the whole collection, so the evidence set is every
    # part rather than the winner alone. An answering path that guessed and
    # checked one record would get the answer and miss the digest.
    ranked = sorted(
        state["parts"],
        key=lambda row: (-(row["unit_price_cents"] * row["on_hand"]), row["part_id"]),
    )
    questions.append(
        {
            "question_id": "Q-003",
            "prompt": "Which part has the greatest on-hand value?",
            "answer_kind": "part_id",
            "answer": ranked[0]["part_id"],
            "operations": [{"method": "GET", "path": "/parts"}],
            "evidence": [
                {"kind": "part", "id": row["part_id"]}
                for row in sorted(state["parts"], key=lambda r: r["part_id"])
            ],
            "evidence_digest": _evidence_digest(
                [
                    row[ATTESTATION_FIELD]
                    for row in sorted(state["parts"], key=lambda r: r["part_id"])
                ]
            ),
        }
    )

    # Q4 — the accepting set is enumerated. See IN_FLIGHT_STATUSES.
    in_flight = sorted(
        (
            row
            for row in _shipments_for(state, "P-0011")
            if row["status"] in IN_FLIGHT_STATUSES
        ),
        key=lambda row: row["shipment_id"],
    )
    questions.append(
        {
            "question_id": "Q-004",
            "prompt": (
                "What is the total quantity of part P-0011 across shipments "
                "whose status is in_transit or delivered?"
            ),
            "answer_kind": "integer_units",
            "answer": sum(row["quantity"] for row in in_flight),
            "operations": [
                {"method": "GET", "path": "/shipments?part_id=P-0011"}
            ],
            "evidence": [
                {"kind": "shipment", "id": row["shipment_id"]} for row in in_flight
            ],
            "evidence_digest": _evidence_digest(
                [row[ATTESTATION_FIELD] for row in in_flight]
            ),
        }
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "seed_version": SEED_VERSION,
        "deployment_id": DEPLOYMENT_ID,
        "questions": questions,
    }


def load_state() -> dict[str, Any]:
    return json.loads(STATE_PATH.read_text())


def load_questions() -> dict[str, Any]:
    return json.loads(QUESTIONS_PATH.read_text())


def load_served_operations() -> dict[str, Any]:
    return json.loads(SERVED_OPERATIONS_PATH.read_text())


def _write(path: Path, document: dict[str, Any]) -> None:
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")


def main() -> int:
    state = build_state()
    _write(STATE_PATH, state)
    _write(QUESTIONS_PATH, build_questions(state))

    import size  # noqa: PLC0415 — a sibling script, loaded only when regenerating

    _write(size.SIZE_PATH, size.measure())
    print(f"wrote {STATE_PATH.name}, {QUESTIONS_PATH.name}, {size.SIZE_PATH.name}")
    print(
        "expect tests/unit/test_reference_app.py to fail until README.md's "
        "stated size is brought back into agreement — that is the tripwire, "
        "not a defect"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
