"""T116 — what makes the reference application's answers *known*-correct.

**Requirement**: FR-053.

The fixture lives in `tests/fixtures/reference-app/`. Its directory name carries
a hyphen and is therefore not importable as a package path, so the modules are
loaded by putting the directory on `sys.path`.

## The trap this file is written around

Finding 016 records that output-checking tests are **blind to opaque-state
loss**: when the answer is recoverable from the visible inputs, a suite that
verifies the answer passes while opaque state is silently dropped. A reference
application advertising "known-correct answers" is an invitation to build
exactly that suite.

So the load-bearing test here is not `test_the_served_surface_answers_every_question`
— that one is real but weak, and it is labelled weak. It is
`test_the_lossy_oracle_gets_every_answer_right_and_every_digest_wrong`, a
deliberate negative control: a pipeline that reaches the right records, drops
their attestations and recomputes the answer from the business fields. It scores
**4/4 on answers and 0/4 on digests**. If a future change ever lets that oracle
reproduce a digest, the digest has become a function of the served fields and
the unforgeable half of the fixture is gone.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import threading
import urllib.request
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from src.contracts import migrations
from src.contracts.canonical import dumps
from src.contracts.schemas import SERVED_OPERATION_SET

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "reference-app"


def _load(name: str) -> ModuleType:
    """Load a fixture module under a unique name.

    Not a bare `import app`: the fixture directory goes on `sys.path` so that
    `app.py` can find `seed.py`, and three generic top-level names (`app`,
    `seed`, `size`) in the global module table is a collision waiting for the
    next fixture that picks one of them. The prefix keeps them namespaced here
    while leaving the plain names available inside the fixture, where the
    directory is the namespace.
    """
    if str(FIXTURE) not in sys.path:
        sys.path.insert(0, str(FIXTURE))
    spec = importlib.util.spec_from_file_location(
        f"_refapp_{name}", FIXTURE / f"{name}.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


seed = _load("seed")
app_mod = _load("app")
size_mod = _load("size")

_REGENERATE = (
    "the committed reference-app fixture no longer matches its generator. If "
    "the change was intended, regenerate with "
    "`python tests/fixtures/reference-app/seed.py` and bring README.md's "
    "stated size table back into agreement — T203 requires that size to be "
    "reported wherever SC-001 appears, so a stale one is a wrong denominator "
    "in someone else's arithmetic."
)


# ---------------------------------------------------------------------------
# The committed fixture is what its generator produces.


def test_the_committed_state_is_what_the_seed_produces() -> None:
    assert seed.load_state() == seed.build_state(), _REGENERATE


def test_the_committed_questions_are_what_the_seed_produces() -> None:
    assert seed.load_questions() == seed.build_questions(seed.load_state()), _REGENERATE


def test_the_committed_size_is_what_the_measurement_produces() -> None:
    assert size_mod.committed() == size_mod.measure(), _REGENERATE


# ---------------------------------------------------------------------------
# The stated size. T203 reads this; U-21 is why it is stated at all.


def test_the_readme_states_the_size_that_was_measured() -> None:
    """Every figure in `size.json` appears in the README's table, by name.

    The README is where a human reads the denominator. A measurement that is
    correct in a JSON file nobody opens and stale in the prose everybody quotes
    is the failure mode, not a lesser version of it.
    """
    readme = (FIXTURE / "README.md").read_text()
    measured = size_mod.committed()

    # The floor. Without it the loop below is only as strong as the list it
    # walks, and an empty list is a test that reads every figure in the README
    # and checks none of them.
    countable = {k for k, v in measured.items() if isinstance(v, int)}
    stated = set(size_mod.STATED_IN_README)
    assert stated == countable, (
        "the README states a different set of figures from the ones that were "
        f"measured. Measured but unstated: {sorted(countable - stated)}; "
        f"stated but not measured: {sorted(stated - countable)}."
    )

    for field in size_mod.STATED_IN_README:
        row = f"| `{field}` | {measured[field]} |"
        assert row in readme, (
            f"README.md does not state {field} as {measured[field]}. Expected a "
            f"table row {row!r}.\n{_REGENERATE}"
        )


def test_the_size_does_not_claim_a_codegraph_measurement() -> None:
    """U-21's gap is named, not filled by an extrapolation.

    `codegraph` has one datapoint and no established scaling. A node count
    invented here by multiplying lines against that datapoint's ratio would
    look like a measurement and be a guess, and T203 would then propagate the
    guess to every place SC-001 appears.
    """
    measured = size_mod.committed()
    assert measured["codegraph_nodes"] is None
    assert measured["codegraph_edges"] is None
    assert "T119" in measured["codegraph_note"]


def test_the_measured_sources_are_enumerated_not_globbed() -> None:
    """A glob would fold the fixture's own scaffolding into the denominator."""
    on_disk = {p.name for p in FIXTURE.glob("*.py")}
    measured = set(size_mod.APPLICATION_SOURCES)
    assert measured < on_disk, (
        "every Python file in the fixture is being counted as application "
        "source. size.py, which measures, and any future helper are the "
        "fixture around the application, not the application."
    )
    assert "size.py" not in measured


# ---------------------------------------------------------------------------
# The published specification and the route table are one fact stated twice.


def test_the_served_operation_set_validates() -> None:
    """The published document validates — after being migrated forward.

    **The document stays at 1.0.0 on purpose, and the migration is the point.**
    This file is what the *target* publishes, not what this system stores.
    T077 added `set_version` and `captured_at` to the stored artifact's
    required set, and `set_version` is a value **this system derives** — a
    target cannot be required to compute it, and one that published a value
    here would not be believed anyway (`served_operations.py` recomputes and
    `ServedOperationSet.from_document` refuses a document that disagrees with
    itself).

    So the committed fixture is a real pre-1.1.0 document, and reading it is a
    real exercise of the real migration against real committed bytes rather
    than against one written for the test.
    """
    migrated = migrations.migrate(
        "served_operation_set", seed.load_served_operations())
    SERVED_OPERATION_SET.validate(migrated)


def test_the_published_document_declares_the_version_it_is() -> None:
    """And the migration is therefore exercised rather than skipped.

    `migrate` returns a document already at the current version unchanged, so
    the test above would pass over no migration at all if this fixture were
    quietly bumped. This is the assertion that the fixture is still the older
    document the test above claims to be reading.
    """
    assert seed.load_served_operations()["schema_version"] == "1.0.0"


def test_every_published_operation_is_routed() -> None:
    operations = seed.load_served_operations()["operations"]
    published = {op["operation_id"] for op in operations}
    assert published == set(app_mod.ROUTES), (
        "the published specification and the route table disagree. T089 "
        "requires the enforcement point to deny an operation the "
        "specification does not describe; a reference application that "
        "quietly served one could not exercise that denial."
    )


def test_the_published_method_and_path_match_the_route() -> None:
    for op in seed.load_served_operations()["operations"]:
        method, path, tier = app_mod.ROUTES[op["operation_id"]]
        assert (method, path, tier) == (
            op["method"],
            op["path_template"],
            op["effect_tier"],
        ), f"{op['operation_id']} is published differently from how it is routed"


def test_exactly_one_published_operation_is_not_read_only() -> None:
    """T114's subject.

    A battery asserting that nothing which failed to resolve read-only reaches
    the target needs the target to have something that is not read-only. If
    this count ever goes to zero the battery still passes and covers nothing,
    which is the vacuity floor this assertion is.
    """
    tiers = [op["effect_tier"] for op in seed.load_served_operations()["operations"]]
    assert tiers.count(app_mod.WRITE) == 1
    assert set(tiers) == {app_mod.READ_ONLY, app_mod.WRITE}


def test_an_unpublished_operation_is_refused_by_rule() -> None:
    app = app_mod.from_committed_state()
    status, body = app.call("GET", "/parts/P-0007/audit-log")
    assert status == 404
    assert body["rule_id"] == "REFAPP-001"
    assert "no such operation" in body["reason"]


# ---------------------------------------------------------------------------
# Answers. The weak half, labelled.


def test_the_served_surface_answers_every_question() -> None:
    """Weak on purpose, and kept because it catches a routing defect.

    The answers were folded over the seed directly, never through dispatch, so
    a filter that drops a row or a serializer that mangles a number fails here.
    What this cannot see is opaque-state loss — see the lossy oracle below.
    """
    app = app_mod.from_committed_state()
    for question in seed.load_questions()["questions"]:
        assert _answer_from(app, question) == question["answer"], (
            f"{question['question_id']} answered wrongly through the served "
            f"surface: {question['prompt']}"
        )


def test_no_question_has_an_empty_evidence_set() -> None:
    """The vacuity floor, and it has already caught one real defect.

    The first seed used twelve parts against a three-element status cycle.
    Twelve and three share a factor, every shipment of a part came out with the
    same status, and both filtered questions degenerated to an empty evidence
    set with the answer zero. Every assertion above still passed: zero equals
    zero, and the digest of an empty list equals the digest of an empty list.

    Asserted over the **generated** questions, not the committed ones. The
    committed file is already pinned to the generator by
    `test_the_committed_questions_are_what_the_seed_produces`; what needs a
    floor is the arithmetic, because that is where the degeneracy came from and
    a check that reads the committed JSON would go on passing while the
    generator produced nothing.
    """
    generated = seed.build_questions(seed.build_state())["questions"]
    assert generated, "the generator produced no questions at all"
    for question in generated:
        assert question["evidence"], (
            f"{question['question_id']} has no evidence, so its digest is the "
            "digest of an empty list and covers nothing"
        )


# ---------------------------------------------------------------------------
# Digests. The load-bearing half.


def _served_records(app: Any, question: dict[str, Any]) -> list[dict[str, Any]]:
    """Fetch the question's evidence *through the served surface*.

    Deliberately by identifier through the published operations, so what comes
    back is whatever the application chose to serve — attestations included, or
    silently not.
    """
    records = []
    for item in question["evidence"]:
        if item["kind"] == "part":
            _status, body = app.call("GET", f"/parts/{item['id']}")
            records.append(body)
        else:
            part_id = _part_of(app, item["id"])
            _status, body = app.call("GET", f"/shipments?part_id={part_id}")
            match = [r for r in body["shipments"] if r["shipment_id"] == item["id"]]
            records.append(match[0])
    return records


def _part_of(app: Any, shipment_id: str) -> str:
    _status, body = app.call("GET", "/shipments")
    for row in body["shipments"]:
        if row["shipment_id"] == shipment_id:
            return row["part_id"]
    raise AssertionError(shipment_id)


def _answer_from(app: Any, question: dict[str, Any]) -> Any:
    qid = question["question_id"]
    if qid == "Q-001":
        _status, part = app.call("GET", "/parts/P-0007")
        return part["unit_price_cents"] * part["on_hand"]
    if qid == "Q-002":
        _status, body = app.call("GET", "/shipments?part_id=P-0003")
        return sum(
            r["quantity"] for r in body["shipments"] if r["status"] == "in_transit"
        )
    if qid == "Q-003":
        _status, body = app.call("GET", "/parts")
        ranked = sorted(
            body["parts"],
            key=lambda r: (-(r["unit_price_cents"] * r["on_hand"]), r["part_id"]),
        )
        return ranked[0]["part_id"]
    if qid == "Q-004":
        _status, body = app.call("GET", "/shipments?part_id=P-0011")
        return sum(
            r["quantity"]
            for r in body["shipments"]
            if r["status"] in seed.IN_FLIGHT_STATUSES
        )
    raise AssertionError(f"no oracle for {qid}")


def _digest_of(records: list[dict[str, Any]]) -> str:
    return hashlib.sha256(
        dumps([r.get(seed.ATTESTATION_FIELD) for r in records])
    ).hexdigest()


def test_the_served_surface_reproduces_every_evidence_digest() -> None:
    """What a *lossless* pipeline achieves, and the thing the oracle cannot."""
    app = app_mod.from_committed_state()
    for question in seed.load_questions()["questions"]:
        records = _served_records(app, question)
        assert _digest_of(records) == question["evidence_digest"], (
            f"{question['question_id']}: the attestations that came back "
            "through the served surface do not reproduce the committed "
            "evidence digest"
        )


def test_the_lossy_oracle_gets_every_answer_right_and_every_digest_wrong() -> None:
    """**The negative control this whole fixture exists for.**

    The oracle reaches the correct records and recomputes the answer from the
    business fields, exactly as a competent pipeline would — and drops the
    attestations, exactly as a pipeline with a lossy intermediate
    representation silently does.

    It scores 4/4 on answers. It scores 0/4 on digests. That gap is the
    measurement: it is the amount of a conformance signal that
    answer-checking cannot see, quantified rather than asserted.
    """
    app = app_mod.from_committed_state()
    questions = seed.load_questions()["questions"]

    answers_right = 0
    digests_right = 0
    for question in questions:
        lossy = [
            {k: v for k, v in record.items() if k != seed.ATTESTATION_FIELD}
            for record in _served_records(app, question)
        ]
        if _answer_from(app, question) == question["answer"]:
            answers_right += 1
        if _digest_of(lossy) == question["evidence_digest"]:
            digests_right += 1

    assert answers_right == len(questions), (
        "the negative control is not a control: it is supposed to be a "
        "*competent* pipeline that has lost opaque state, so if it cannot even "
        "answer the questions it demonstrates nothing"
    )
    assert digests_right == 0, (
        "a pipeline that dropped every attestation still reproduced an "
        "evidence digest. The digest has become derivable from the served "
        "business fields and no longer detects opaque-state loss — which is "
        "the single property this fixture is here to hold."
    )


# ---------------------------------------------------------------------------
# Unforgeable from the visible state: the precise claim, tested in its terms.


def test_the_attestations_are_independent_of_every_served_business_field() -> None:
    """Change every business field; the attestations do not move.

    A dependence in this direction would mean the digest is a function of the
    served surface, and the lossy oracle above would start reproducing it.
    """
    state = seed.build_state()
    mutated = json.loads(json.dumps(state))
    for row in mutated["parts"]:
        row["unit_price_cents"] += 1
        row["on_hand"] += 1
        row["name"] = "moved"
    for row in mutated["shipments"]:
        row["quantity"] += 1
        row["status"] = "cancelled"

    original = [r["attestation"] for r in state["parts"] + state["shipments"]]
    after = [r["attestation"] for r in mutated["parts"] + mutated["shipments"]]
    assert original == after


def test_a_different_key_moves_every_attestation_and_no_visible_field() -> None:
    """The converse, and the sharper statement of the same property.

    Two seeds taken under different keys have **byte-identical** business
    projections and **disjoint** attestation sets. Nothing an operation serves
    distinguishes them; every digest does.
    """
    committed = seed.build_state()
    other = seed.build_state(key=b"a-different-key-entirely")

    assert seed.business_projection(committed) == seed.business_projection(other)

    def attestations(state: dict[str, Any]) -> set[str]:
        return {r["attestation"] for r in state["parts"] + state["shipments"]}

    assert attestations(committed).isdisjoint(attestations(other))


def test_no_operation_discloses_the_attestation_key() -> None:
    """Sweep every published operation and look for the key in what came back.

    If the key were reachable, the digest would be forgeable from the served
    surface by anyone who read the response and recomputed the HMAC, and the
    unforgeability claim would be false rather than merely weakened.
    """
    app = app_mod.from_committed_state()
    key = seed.ATTESTATION_KEY.decode()
    seen = []
    for method, path, _tier in app_mod.ROUTES.values():
        target = path.replace("{part_id}", "P-0001").replace(
            "{shipment_id}", "S-0001"
        )
        _status, body = app.call(method, target)
        seen.append(json.dumps(body))
    blob = "\n".join(seen)
    assert key not in blob
    assert "attestation_key" not in blob.lower()
    assert len(seen) == len(app_mod.ROUTES), "the sweep did not cover every operation"


def test_the_epoch_moves_the_digests_while_the_projection_stands_still() -> None:
    """The same separation, driven from the other input.

    Stated because `SEED_EPOCH` is the field most likely to be bumped by
    someone regenerating, and it is worth having a test that says out loud what
    bumping it does: every digest changes, no served field does.
    """
    before = seed.build_state()
    original_epoch = seed.SEED_EPOCH
    try:
        seed.SEED_EPOCH = "2027-01-01"
        after = seed.build_state()
    finally:
        seed.SEED_EPOCH = original_epoch

    assert seed.business_projection(before)["parts"] == (
        seed.business_projection(after)["parts"]
    )
    assert before["parts"][0]["attestation"] != after["parts"][0]["attestation"]


# ---------------------------------------------------------------------------
# Effect tiers, in behaviour rather than in a label. T114/T115 groundwork.


def test_every_read_only_operation_leaves_the_state_byte_identical() -> None:
    app = app_mod.from_committed_state()
    before = dumps(app.state)
    for op in seed.load_served_operations()["operations"]:
        if op["effect_tier"] != app_mod.READ_ONLY:
            continue
        target = op["path_template"].replace("{part_id}", "P-0001")
        app.call(op["method"], target)
    assert dumps(app.state) == before


def test_the_one_write_operation_actually_writes() -> None:
    """Otherwise the tier label is decoration and T114 asserts nothing."""
    app = app_mod.from_committed_state()
    before = dumps(app.state)
    status, body = app.call("POST", "/shipments/S-0001/cancel")
    assert status == 200
    assert body["shipment"]["status"] == "cancelled"
    assert dumps(app.state) != before


def test_a_write_does_not_touch_the_committed_fixture() -> None:
    """T180 drives a copy. The copy must be a copy."""
    on_disk = seed.STATE_PATH.read_bytes()
    app = app_mod.from_committed_state()
    app.call("POST", "/shipments/S-0002/cancel")
    assert seed.STATE_PATH.read_bytes() == on_disk


def test_two_applications_built_from_one_state_do_not_share_it() -> None:
    """T180 drives a copy of the workload and diffs it against an untouched one.

    Both sides come from the same seeded document, so if `Application` held a
    reference rather than a copy the write arm would mutate the control arm and
    the diff would come back empty — a battery reporting no unauthorized effect
    because its baseline moved with it.
    """
    shared = seed.load_state()
    control = app_mod.Application(shared)
    treatment = app_mod.Application(shared)
    treatment.call("POST", "/shipments/S-0003/cancel")

    _status, body = control.call("GET", "/shipments")
    row = [r for r in body["shipments"] if r["shipment_id"] == "S-0003"][0]
    assert row["status"] != "cancelled"
    assert dumps(control.state) == dumps(app_mod.Application(shared).state)


def test_the_application_touches_one_directory_and_names_it() -> None:
    """T115's declared set has a single member and no way to move it."""
    assert app_mod.state_root() == FIXTURE
    assert seed.STATE_PATH.parent == app_mod.state_root()


# ---------------------------------------------------------------------------
# The HTTP origin. T101 measures overhead across a real socket.


def test_the_origin_refuses_to_bind_every_interface() -> None:
    app = app_mod.from_committed_state()
    for host in ("", "0.0.0.0", "::", "*"):
        with pytest.raises(ValueError, match="not an address to bind to"):
            app_mod.build_server(app, host=host, port=0)


def test_the_origin_serves_the_same_bytes_the_in_process_call_returns() -> None:
    """The in-process path is a shortcut, not a different application.

    T101 drives the socket; the batteries drive `call`. If those two ever
    diverge, an overhead figure and a safety assertion would be measurements of
    two different programs.
    """
    served = app_mod.from_committed_state()
    server = app_mod.build_server(served, host="127.0.0.1", port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address[0], server.server_address[1]
        with urllib.request.urlopen(f"http://{host}:{port}/parts/P-0007") as resp:
            over_http = json.loads(resp.read())
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    in_process = app_mod.from_committed_state().call("GET", "/parts/P-0007")[1]
    assert over_http == in_process
    assert seed.ATTESTATION_FIELD in over_http, (
        "the HTTP surface dropped the attestation the in-process surface "
        "returns, which is opaque-state loss at the origin"
    )
