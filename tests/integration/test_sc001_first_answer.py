"""T117 — the unattended first-verified-answer harness for **SC-001**.

**Criterion**: SC-001 — *an operator with a running application reaches a first
verified answer in under 15 minutes from starting configuration, unattended, on
a reference application.*

## The thing this harness must not do, stated before what it does

The specification says, in as many words:

> *"SC-001 asks for a first verified answer within fifteen minutes, which a
> high refusal share can defeat without anything in the runtime being wrong —
> so SC-001 is not independently assessable until FR-045 has reported at least
> once."*

A harness that reports a green SC-001 while a high refusal share is what
produced the timing is the vacuity shape this repository has caught repeatedly.
There are two routes into it and both are closed here:

- **Quoting a timing with no share beside it.** Closed structurally rather than
  by discipline: `src.analysis.timing.Sc001Report` cannot be constructed
  without FR-045's share and without the subject's size, so there is no
  artifact this file could emit that carries a verdict alone.
- **Stopping at the first verified answer.** A run that stopped there would
  report a share over the questions it happened to reach before getting lucky.
  `_run` attempts **every** question and the assertion below says so, because
  the timing is what SC-001 asks for and the denominator is what makes the
  timing readable.

`assessable` is `False` for every run this file produces, and it is *derived*
from FR-045's window being a production one rather than asserted. A harness
cannot make its own traffic production traffic (SC-019: "the first window to
close after first production traffic"), which is the point.

## What a "verified answer" is here, and what it is not

Each question in `questions.json` carries two correct things, and only one of
them survives a lossy pipeline:

- the **answer**, a fold over served business fields — reproducible by anything
  that can read prices and quantities;
- the **evidence digest**, SHA-256 over the `attestation` values of exactly the
  records the answer depends on. An attestation is a MAC over `{kind, id,
  epoch}` and covers no business field, so no served field determines it.

So the outcome is three-valued and each value means something different:

- `VERIFIED` — the answer recomputed from what the origin served matches, *and*
  the digest recomputed from the attestations the origin served matches.
- `FAILED` — an independent check ran and disagreed.
- `NOT_VERIFIABLE` — the origin served records carrying no attestation, so
  there was no independent channel to check against. **This is FR-045's state**
  and it is deliberately not folded into `FAILED`: a refusal counted as a
  failure disappears from the share SC-001 depends on.

**Two things this is not, stated so a green run is not over-read.** First, it
is not FR-022's independent recomputation: both sides descend from `seed.py`'s
arithmetic, so this catches a routing, filtering, serialization or
opaque-state-dropping defect and not a wrong seed. `seed.py`'s own docstring
makes the same disclaimer about its expected answers. Second, the record
selection comes from each question's declared `evidence` list, so the harness
is told which records support an answer rather than deriving that from the
prompt — it scores the *pipeline*, not a question-answering capability.

## What the timed window covers, and the step it does not

The window opens on the starting configuration and closes after the last
question. Inside it, the analysis span covers the real admission path —
fetch the target's published specification, classify it under FR-044, capture
the served-operation set — which is product code, not a stand-in.

It does **not** cover `codegraph`. **T004** leaves `CODEGRAPH_SCHEMA_SHA256`
unset so the pin fails closed, and **T119**, which would invoke `codegraph` at
all, does not exist. Every report this file emits therefore carries
`codegraph_invoked: false` and the caveat that goes with it: the analysis
figure here is **not** a datapoint against **U-21**'s untested scale claim, and
a later reader must not treat a small `analysis_seconds` as evidence that
analysis is cheap at scale.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import sys
import threading
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterator

import pytest

REPO = Path(__file__).resolve().parents[2]
REFAPP_DIR = REPO / "tests" / "fixtures" / "reference-app"
RESULTS = REPO / "tests" / "batteries" / "results"

for _entry in (str(REPO), str(REFAPP_DIR)):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

import app as refapp  # noqa: E402
import seed as refseed  # noqa: E402

from src.analysis.admission import check, fetch_from_file, gate  # noqa: E402
from src.analysis.served_operations import ServedOperationSet  # noqa: E402
from src.analysis.timing import (  # noqa: E402
    NotVerifiableShare,
    Sc001Report,
    Sc001Timer,
    Sc001Verdict,
    SubjectSize,
)
from src.contracts.canonical import dumps  # noqa: E402
from src.contracts.result import (  # noqa: E402
    Corroboration,
    Result,
    VerificationOutcome,
)

#: The starting configuration. Everything the operator supplies and nothing
#: else — no answers, no expected timings, no thresholds.
STARTING_CONFIGURATION = {
    "deployment_id": "d-reference-app",
    "specification_path": str(REFAPP_DIR / "served_operations.json"),
    "bind_host": "127.0.0.1",
    "bind_port": 0,
}

#: The reason string FR-045's breakdown uses for the state this fixture can
#: construct. Named once so the harness and its assertions cannot drift.
NO_EVIDENCE = "evidence_channel_absent"

#: What a missing evidence channel is recorded as. **Not `FAILED`**, and the
#: difference is the whole of FR-045: the share SC-001 depends on is a share of
#: the *not-verifiable* state, so a refusal booked as a failure vanishes from
#: it while still costing the run an answer. Named as a constant so that the
#: choice is one edit rather than two branches that can drift apart.
ABSENT_EVIDENCE_OUTCOME = VerificationOutcome.NOT_VERIFIABLE

#: A wall-clock stop for the whole unattended run. Not a threshold on SC-001 —
#: it is two orders of magnitude under the fifteen-minute window, so it can
#: only ever fire on a hang, and a harness with no terminator is a CI job that
#: reports nothing after six hours.
UNATTENDED_STOP_SECONDS = 120.0


# ---------------------------------------------------------------------------
# The running application.


class LossyApplication(refapp.Application):
    """The reference application with the evidence channel removed for some
    record kinds, and **every business field left intact**.

    This is the negative control. Under it every answer is still correct and
    every answer-only assertion still passes — what disappears is the opaque
    field the answers do not depend on. It is finding 016's blindness
    reproduced on purpose, at the level of the SC-001 path rather than of one
    served record.

    `refapp.Application` is subclassed rather than edited, because `app.py` is
    T116's and carries its own removal proofs.
    """

    def __init__(self, state: dict[str, Any], *, drop_kinds: frozenset[str]):
        super().__init__(state)
        self._drop_kinds = drop_kinds

    def call(self, method: str, target: str) -> tuple[int, dict[str, Any]]:
        status, body = super().call(method, target)
        if "part" in self._drop_kinds:
            body = _strip_attestation(body, "parts")
        if "shipment" in self._drop_kinds:
            body = _strip_attestation(body, "shipments")
        return status, body


def _strip_attestation(body: dict[str, Any], collection: str) -> dict[str, Any]:
    singular = {"parts": "part_id", "shipments": "shipment_id"}[collection]
    stripped: dict[str, Any] = {}
    for key, value in body.items():
        if key == collection and isinstance(value, list):
            stripped[key] = [
                {k: v for k, v in row.items() if k != "attestation"}
                for row in value
            ]
        elif isinstance(value, dict) and singular in value:
            stripped[key] = {k: v for k, v in value.items() if k != "attestation"}
        else:
            stripped[key] = value
    if singular in body:
        stripped = {k: v for k, v in stripped.items() if k != "attestation"}
    return stripped


@dataclass(frozen=True)
class Origin:
    base_url: str
    application: refapp.Application


def _serve(application: refapp.Application) -> Iterator[Origin]:
    server = refapp.build_server(
        application,
        host=STARTING_CONFIGURATION["bind_host"],
        port=STARTING_CONFIGURATION["bind_port"],
    )
    host, port = server.server_address[0], server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield Origin(f"http://{host}:{port}", application)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5.0)


def _get(origin: Origin, path: str) -> dict[str, Any]:
    request = urllib.request.Request(origin.base_url + path, method="GET")
    with urllib.request.urlopen(request, timeout=10.0) as response:
        return json.loads(response.read().decode("utf-8"))


# ---------------------------------------------------------------------------
# Answering and verifying one question.


def _records_served(origin: Origin, question: dict[str, Any]) -> list[dict]:
    """Every record the question's own declared operations returned."""
    served: list[dict[str, Any]] = []
    for operation in question["operations"]:
        body = _get(origin, operation["path"])
        for value in body.values():
            if isinstance(value, list):
                served.extend(row for row in value if isinstance(row, dict))
        if any(key.endswith("_id") for key in body):
            served.append(body)
    return served


def _identity(row: dict[str, Any]) -> tuple[str, str] | None:
    """The `{kind, id}` a served record answers to.

    `shipment_id` is tested **first**, because a shipment row also carries a
    `part_id` — the part it belongs to. Keying on the first identifier-shaped
    field found would file every shipment under its part, collapse a part's
    shipments onto one entry, and make every shipment question look like an
    origin that served nothing.
    """
    if "shipment_id" in row:
        return ("shipment", row["shipment_id"])
    if "part_id" in row:
        return ("part", row["part_id"])
    return None


def _supporting(records: list[dict], question: dict[str, Any]) -> list[dict]:
    """The records the question declares its answer depends on, in the
    declared order. The digest is taken over exactly this sequence."""
    index = {}
    for row in records:
        identity = _identity(row)
        if identity is not None:
            index[identity] = row
    wanted = [(item["kind"], item["id"]) for item in question["evidence"]]
    return [index[key] for key in wanted if key in index]


def _recompute_answer(records: list[dict], question: dict[str, Any]) -> Any:
    """The answer, folded over what the origin served.

    Three folds keyed by `answer_kind`, which is the fixture's own vocabulary.
    A fourth kind arriving with no fold here raises rather than returning
    `None`: a silent `None` would compare unequal, report `FAILED`, and read as
    a runtime defect rather than as an unhandled question shape.
    """
    kind = question["answer_kind"]
    supporting = _supporting(records, question)
    if kind == "integer_cents":
        return sum(r["unit_price_cents"] * r["on_hand"] for r in supporting)
    if kind == "integer_units":
        return sum(r["quantity"] for r in supporting)
    if kind == "part_id":
        ranked = sorted(
            (r for r in records if _identity(r) and _identity(r)[0] == "part"),
            key=lambda r: (-(r["unit_price_cents"] * r["on_hand"]), r["part_id"]),
        )
        return ranked[0]["part_id"]
    raise AssertionError(f"no fold for answer_kind {kind!r}")


def verify(records: list[dict], question: dict[str, Any]) -> Result:
    """The three-valued outcome, from what the origin actually served.

    The evidence channel is checked **first**. A pipeline that dropped the
    attestations still produces every correct answer, so an implementation that
    returned `VERIFIED` on answer equality alone would report a clean run over
    a lossy one — which is exactly what the reference application's negative
    control was built to make visible.
    """
    supporting = _supporting(records, question)
    if len(supporting) != len(question["evidence"]):
        return Result(
            ABSENT_EVIDENCE_OUTCOME,
            payload=None,
            # Nothing corroborated it and nothing could have: the independent
            # channel this answer would be checked against was not served.
            corroboration=Corroboration.NOT_STATED,
            reason=(
                f"{NO_EVIDENCE}: the origin served "
                f"{len(supporting)} of the {len(question['evidence'])} "
                "records this answer depends on"
            ),
        )
    if any("attestation" not in row for row in supporting):
        return Result(
            ABSENT_EVIDENCE_OUTCOME,
            payload=None,
            corroboration=Corroboration.NOT_STATED,
            reason=(
                f"{NO_EVIDENCE}: a supporting record carried no attestation, "
                "so there is no channel independent of the business fields to "
                "check this answer against"
            ),
        )

    answer = _recompute_answer(records, question)
    digest = hashlib.sha256(
        dumps([row["attestation"] for row in supporting])
    ).hexdigest()

    if digest != question["evidence_digest"]:
        return Result(
            VerificationOutcome.FAILED,
            payload={"answer": answer},
            # Corroborated and disagreeing is a different report from nobody
            # having looked, and FAILED carries the distinction the same way
            # VERIFIED does — the attestation channel was there and was read.
            corroboration=Corroboration.CORROBORATED,
            reason="the evidence digest recomputed from the served "
            "attestations disagrees with the one the question declares",
        )
    if answer != question["answer"]:
        return Result(
            VerificationOutcome.FAILED,
            payload={"answer": answer},
            corroboration=Corroboration.CORROBORATED,
            reason=(
                f"recomputed {answer!r}, the question declares "
                f"{question['answer']!r}"
            ),
        )
    return Result(
        VerificationOutcome.VERIFIED,
        payload={"answer": answer},
        corroboration=Corroboration.CORROBORATED,
    )


# ---------------------------------------------------------------------------
# The unattended run.


@dataclass(frozen=True)
class Run:
    report: Sc001Report
    outcomes: dict[str, Result]


def _run(
    build_application: Callable[[dict[str, Any]], refapp.Application],
    *,
    clock: Callable[[], float] = time.perf_counter,
) -> Run:
    """One unattended SC-001 run, from starting configuration.

    Nothing here reads stdin, prompts, or takes an argument that is not in
    `STARTING_CONFIGURATION`.
    """
    timer = Sc001Timer(clock=clock)
    timer.start()

    # -- analysis: the real admission path, which is product code ----------
    with timer.analysis():
        response = fetch_from_file(STARTING_CONFIGURATION["specification_path"])
        decision = check(
            response, deployment_id=STARTING_CONFIGURATION["deployment_id"]
        )
        operation_set = ServedOperationSet.from_admission(
            decision, captured_at="2026-08-08T00:00:00Z"
        )
        size = SubjectSize.from_document(
            json.loads((REFAPP_DIR / "size.json").read_text())
        )

    questions = refseed.load_questions()["questions"]
    outcomes: dict[str, Result] = {}
    deadline = clock() + UNATTENDED_STOP_SECONDS

    application = gate(
        decision, lambda: build_application(refseed.load_state())
    )
    serving = _serve(application)
    origin = next(serving)
    try:
        for question in questions:
            if clock() > deadline:
                raise AssertionError(
                    "the unattended run did not finish within "
                    f"{UNATTENDED_STOP_SECONDS}s; this is a hang, not an "
                    "SC-001 result"
                )
            result = verify(_records_served(origin, question), question)
            outcomes[question["question_id"]] = result
            if result.is_verified:
                timer.first_verified_answer()
            # No `break`. A run that stopped at the first verified answer
            # would report FR-045's share over the questions it happened to
            # reach, and the criterion's timing would then be produced by
            # whichever question got lucky first.
    finally:
        for _ in serving:  # drives the generator's finally
            pass

    window = timer.close()
    refused = {
        qid: r
        for qid, r in outcomes.items()
        if r.verification is VerificationOutcome.NOT_VERIFIABLE
    }
    share = NotVerifiableShare(
        attempted=len(outcomes),
        not_verifiable=len(refused),
        by_reason={NO_EVIDENCE: len(refused)} if refused else {},
        # A harness run is not production traffic, and nothing here can make
        # it so. This is why every report below says `assessable: false`.
        production=False,
    )
    report = Sc001Report(
        window=window,
        subject_size=size,
        not_verifiable=share,
        subject=f"{operation_set.deployment_id} "
        f"({len(operation_set.operations)} served operations)",
        codegraph_invoked=False,
    )
    return Run(report=report, outcomes=outcomes)


def _clean(state: dict[str, Any]) -> refapp.Application:
    return refapp.Application(state)


def _lossy_for_parts(state: dict[str, Any]) -> refapp.Application:
    return LossyApplication(state, drop_kinds=frozenset({"part"}))


def _lossy_for_everything(state: dict[str, Any]) -> refapp.Application:
    return LossyApplication(
        state, drop_kinds=frozenset({"part", "shipment"})
    )


@pytest.fixture(scope="module")
def clean_run() -> Run:
    return _run(_clean)


# ---------------------------------------------------------------------------
# SC-001 itself.


def test_the_run_reaches_a_first_verified_answer_within_the_window(clean_run):
    payload = clean_run.report.to_dict()
    assert payload["verdict"] == Sc001Verdict.FIRST_VERIFIED_ANSWER_WITHIN_WINDOW.value
    assert payload["first_verified_answer_seconds"] is not None


def test_every_question_verified_on_the_unmodified_application(clean_run):
    """The floor under the negative controls. If the clean run refused too,
    a high share below would say nothing about the arm that produced it."""
    assert all(r.is_verified for r in clean_run.outcomes.values()), {
        qid: (r.verification.value, r.reason)
        for qid, r in clean_run.outcomes.items()
    }
    assert len(clean_run.outcomes) == 4


def test_the_reported_window_states_the_reference_applications_size(clean_run):
    size = clean_run.report.to_dict()["subject_size"]
    committed = json.loads((REFAPP_DIR / "size.json").read_text())
    assert size["files"] == committed["application_files"]
    assert size["code_lines"] == committed["application_code_lines"]
    assert size["codegraph_nodes"] is None


def test_analysis_wall_time_is_reported_apart_from_the_rest_of_the_window(
    clean_run,
):
    payload = clean_run.report.to_dict()
    assert payload["analysis_seconds"] > 0.0
    assert payload["remainder_seconds"] > 0.0
    assert payload["codegraph_invoked"] is False
    assert "U-21" in payload["analysis_coverage_caveat"]


def test_sc001_is_reported_as_not_independently_assessable(clean_run):
    """Even on a run where nothing refused. The criterion's assessability is a
    property of FR-045 having reported over production traffic, not of this
    run having gone well."""
    payload = clean_run.report.to_dict()
    assert payload["not_verifiable"]["share"] == 0.0
    assert payload["assessable"] is False
    assert "not independently assessable" in payload["not_assessable_because"]


def test_every_question_is_attempted_even_after_the_first_verified_answer(
    clean_run,
):
    """The cherry-picking guard. A run that stopped at the first verified
    answer would divide FR-045's share by however many questions it reached
    before getting lucky — and the first question here verifies."""
    assert clean_run.outcomes["Q-001"].is_verified
    assert clean_run.report.not_verifiable.attempted == 4


# ---------------------------------------------------------------------------
# The negative control: a green timing produced by a high refusal share.


def test_a_high_refusal_share_does_not_produce_a_green_sc001():
    """Rule 8's negative control for this harness.

    The lossy origin answers every question correctly and refuses half of
    them. A harness scoring the timing alone would report the same
    within-window verdict as the clean run and say nothing about the half it
    lost — which is the vacuity this criterion invites.
    """
    run = _run(_lossy_for_parts)
    payload = run.report.to_dict()

    assert payload["verdict"] == Sc001Verdict.FIRST_VERIFIED_ANSWER_WITHIN_WINDOW.value
    assert payload["not_verifiable"]["share"] == 0.5
    assert payload["not_verifiable"]["by_reason"] == {NO_EVIDENCE: 2}
    assert payload["assessable"] is False

    # And the timing is genuinely indistinguishable from the clean run's, so
    # the share is the only thing carrying the difference.
    assert payload["first_verified_answer_seconds"] is not None


def test_the_refused_questions_still_answered_correctly():
    """What makes the arm above a control rather than a broken origin: the
    business fields are untouched, so an answer-only harness sees nothing.

    The answers are recomputed here from what the **lossy** origin served, and
    they are all correct. That is the whole claim — the refusal is a loss of
    the evidence channel, not of the data.
    """
    run = _run(_lossy_for_parts)
    for qid in ("Q-001", "Q-003"):
        assert (
            run.outcomes[qid].verification is VerificationOutcome.NOT_VERIFIABLE
        )

    application = _lossy_for_parts(refseed.load_state())
    serving = _serve(application)
    origin = next(serving)
    try:
        for question in refseed.load_questions()["questions"]:
            served = _records_served(origin, question)
            assert _recompute_answer(served, question) == question["answer"], (
                f"{question['question_id']} answered wrongly under the lossy "
                "origin, so the arm is a broken origin rather than a control"
            )
    finally:
        for _ in serving:
            pass


def test_absent_evidence_is_not_verifiable_and_not_a_failure():
    """FR-045's share is of the *not-verifiable* state. A refusal recorded as
    a failure disappears from the share SC-001 depends on."""
    run = _run(_lossy_for_everything)
    payload = run.report.to_dict()
    assert payload["not_verifiable"]["share"] == 1.0
    assert payload["verdict"] == Sc001Verdict.NO_VERIFIED_ANSWER.value
    for result in run.outcomes.values():
        assert result.verification is VerificationOutcome.NOT_VERIFIABLE
        assert NO_EVIDENCE in result.reason


def test_an_altered_attestation_fails_verification_rather_than_refusing_it():
    """The other side of the three-valued outcome, and the arm that shows the
    evidence channel is checked rather than merely required to be present.

    An attestation that is present but wrong is a disagreement, not an absence
    — a harness accepting on answer equality alone would return VERIFIED here,
    because every business field is correct.
    """
    state = refseed.load_state()
    state["parts"][6]["attestation"] = "0" * 64
    application = refapp.Application(state)
    serving = _serve(application)
    origin = next(serving)
    try:
        question = next(
            q
            for q in refseed.load_questions()["questions"]
            if q["question_id"] == "Q-001"
        )
        result = verify(_records_served(origin, question), question)
    finally:
        for _ in serving:
            pass
    assert result.verification is VerificationOutcome.FAILED
    assert "evidence digest recomputed" in result.reason
    assert result.payload["answer"] == question["answer"]


# ---------------------------------------------------------------------------
# The record.


def test_the_run_is_recorded_with_the_environment_it_is_a_property_of(clean_run):
    record = {
        "criterion": "SC-001",
        "task": "T117",
        "measured_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "report": clean_run.report.to_dict(),
        "per_question": {
            qid: {"verification": r.verification.value, "reason": r.reason}
            for qid, r in sorted(clean_run.outcomes.items())
        },
        "environment": {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "python": sys.version.split()[0],
            "privileged": os.getuid() == 0,
        },
        "what_this_is_a_property_of": [
            "An in-process HTTP origin on the loopback address. There is no "
            "network, no TLS and no enforcement point in this path — T114 is "
            "the battery that stands the assembled enforcement point up.",
            "An analysis span covering FR-044 admission and served-operation "
            "capture, and NOT covering codegraph: T004 leaves the schema hash "
            "unset and T119 does not exist. This is not a datapoint against "
            "U-21's untested scale claim.",
            "A harness run, which is not production traffic. FR-045 has "
            "reported no production window, so SC-001 is reported as not "
            "independently assessable regardless of the timing.",
            "No model provider is in this path. The answering step recomputes "
            "from the served surface; an agent loop would add unbounded time "
            "this harness does not measure.",
        ],
    }
    RESULTS.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(record, indent=2, sort_keys=True) + "\n"
    if os.environ.get("F2A_RECORD_MEASUREMENTS") == "1":
        (RESULTS / "sc001-first-answer.json").write_text(serialized)
    else:
        (RESULTS / "sc001-first-answer.latest.json").write_text(serialized)
    assert (RESULTS / "sc001-first-answer.json").is_file()
