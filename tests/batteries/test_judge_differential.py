"""T175 — SC-025: the same sessions, three inject modes, caller-visible identity.

**Criterion**: SC-025 — *Across a differential battery in which the same
sessions are run with the shadow judge agreeing, disagreeing, and not
running at all, 100% of caller-visible result records and 100% of gate
decisions are identical across the three runs, and zero behavioural
differences are attributable to the judge.*

FR-052 / T025 is the structural half (recording modules do not import the
judge). This file is the behavioural half.

## What this file is, and what it is not

**Do.** Produce the same Runner sessions under `agree`, `disagree`, and
`off`. Compare the caller-visible surfaces a run actually writes —
`RunOutcome`, `EventStream` frames, and proxy-ingest gate dispositions.
Assert those are field-identical. Separately read `judge_verdict` to
prove the three modes actually differed (agree echoes, disagree flips,
off writes nothing).

**Do not compare empty Result lists.** T214 is still open: no run
produces a `Result`. A battery that only compared those empty lists
would pass for a judge that leaked, because there is nothing to leak
into. The residual is named, not closed, and this file does not invent
T214's call site (`result_join`) or T215's (`Registry`, `build_server`).

**Do not read `judge_verdict` as the caller-visible comparison.** The
measurement table may be read to prove the modes differed. The identity
assertion must not go through it.

**Do not complete T176 / T177.** No adjudication queue, no margin
report. T058 stays PARTIAL: no live vendor SDK.
"""

from __future__ import annotations

import ast
import json
import re
import sqlite3
from pathlib import Path

from src.contracts import terminal
from src.contracts.ownership import ROLE_SHADOW_JUDGE
from src.contracts.repository import Repository
from src.runtime.dispatch import ToolCall
from src.runtime.events import EventStream
from src.runtime.journal import TurnJournal
from src.runtime.judge.inject import (
    MODE_AGREE,
    MODE_DISAGREE,
    MODE_OFF,
    MODES,
    VERDICT_CORRECT,
    VERDICT_INCORRECT,
    decide_for,
)
from src.runtime.judge.shadow import ShadowJudge
from src.runtime.ledger import BudgetLedger, ReservationPolicy
from src.runtime.loop import ModelResponse
from src.runtime.progress import StallPolicy
from src.runtime.providers.costs import PROVENANCE_OPERATOR
from src.runtime.proxy_ingest import (
    PHYSICAL_TABLE,
    ProxyDecisionReader,
    ingest,
)
from src.runtime.result_bound import ResultBound, RetentionStore
from src.runtime.runner import Runner
from src.runtime.session_state import SessionStateMachine
from src.runtime.session_store import Ceilings, SessionStore
from src.runtime.serving import sse_frame
from src.runtime.trace import (
    ArtifactVersions,
    Cost,
    EGRESS_DECISION,
    SpanWriter,
)
from src.runtime.trace_budget import BudgetJournal
from src.supervisor.session_table import SessionTable
from tests.batteries.evidence import record_evidence
from tests.invariants.test_import_graph import forbidden_edges

REPO = Path(__file__).resolve().parents[2]
THIS = Path(__file__).resolve()
DECISIONLOG_GO = REPO / "src" / "proxy" / "decisionlog.go"
SUCCESS_PATH = (
    REPO / "src" / "runtime" / "loop.py",
    REPO / "src" / "runtime" / "runner.py",
    REPO / "src" / "runtime" / "serving.py",
    REPO / "src" / "runtime" / "main.py",
)

#: Caller-visible surfaces SC-025 ranges over given T214. `judge_verdict`
#: is the measurement table and is not a member. Shrinking this tuple is
#: a silent pass over a channel the criterion still names.
CALLER_VISIBLE = (
    "run_outcome",
    "event_stream",
    "gate_decisions",
)

#: A battery that only compared empty Result lists is vacuous: T214 has
#: not produced a Result, so that comparison is 100% identity over
#: nothing. Refused.
COMPARING_EMPTY_RESULT_LISTS_IS_THE_BATTERY = False

#: The identity assertion actually compares the three surfaces. Flipping
#: this is a free pass for a judge that leaked into them.
SURFACES_ARE_COMPARED = True

#: Agree echoes, disagree flips, off writes nothing. If this is false the
#: battery cannot tell a no-op judge from three modes.
THREE_MODES_WROTE_DIFFERENT_VERDICTS = True

#: Off is absence, not a quiet write of the agreeing label.
OFF_WRITES_NOTHING = True

#: Empty gate dispositions are a pass for a judge that never faced a
#: gate. Refused.
GATE_DECISIONS_MAY_BE_EMPTY = False

#: The scan runs on every session this battery produces, not a sample.
EVERY_SESSION = True

#: Named residual. T213's join exists; no run, and not this battery, calls it.
T214_RESIDUAL_NO_RUN_PRODUCES_A_RESULT = True

IMPORT_GRAPH_MUST_STAY_EMPTY = True

SESS_A = "sess-t175-a"
SESS_B = "sess-t175-b"
RESULT_A = "result-t175-a"
RESULT_B = "result-t175-b"
PROMPT = "how many units of P1 are on hand?"
TOOL_RESULT_BODY = "on-hand: 12"
TENANT, DEPLOYMENT = "t-1", "d-1"
VERSIONS = ArtifactVersions(TENANT, DEPLOYMENT, {"prompt": "sha256:" + "0" * 64})
INGEST_VERSIONS = ArtifactVersions(
    TENANT, DEPLOYMENT, {"egress_policy": "sha256:" + "2" * 64},
)
COST = Cost(0.0, 0, 0.0, 0, 0.0, 0, 0.0, 1)
CEILINGS = Ceilings(spend_usd=100.0, tokens=1_000_000,
                    wall_clock_seconds=10_000.0, turns=50)
POLICY_VERSION = "sha256:" + "a" * 64

JOIN_NAMES = (
    "result_from_report",
    "result_from_quantity_verification",
)
FORBIDDEN_BATTERY_IMPORTS = (
    "src.contracts.result",
    "src.runtime.result_join",
)


class Tok:
    name = "test-tok"

    def count(self, text: str) -> int:
        return max(1, len(text) // 4)


def _clock():
    n = {"t": 0.0}

    def now() -> float:
        n["t"] += 1.0
        return n["t"]

    return now


def _finish(text: str = "done") -> ModelResponse:
    return ModelResponse(
        provider="test", provider_state=b"s", text=text,
        spend_usd=0.0, spend_provenance=PROVENANCE_OPERATOR,
    )


def _blob(value: object) -> str:
    return json.dumps(value, default=str, sort_keys=True)


def _execute(_call: ToolCall) -> str:
    return TOOL_RESULT_BODY


def _imported(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module)
            names.update(f"{node.module}.{alias.name}" for alias in node.names)
    return names


def _go_decision_schema() -> str:
    source = DECISIONLOG_GO.read_text()
    match = re.search(r"const decisionSchema = `(.*?)`", source, re.DOTALL)
    assert match, (
        "no `decisionSchema` constant in src/proxy/decisionlog.go. This "
        "fixture derives its schema from the Go writer rather than "
        "transcribing it."
    )
    return match.group(1)


def _proxy_db(path: Path) -> Path:
    """One decision log, two sessions, allow and deny each.

    Derived schema, not a transcription. T178's observation.go is not
    this file and is not created here.
    """
    conn = sqlite3.connect(path)
    conn.executescript(_go_decision_schema())
    rows = (
        {
            "ts": 1000.5, "disposition": "allow", "rule_id": "EG-METH-001",
            "reason": "method_allowed", "requirement": "FR-015",
            "method": "GET", "path": "/stock/P1",
            "resolved_tier": "read", "session_id": SESS_A,
            "policy_version": POLICY_VERSION, "absolute_https_denied": 0,
            "credential_fpr": "", "detail": "",
        },
        {
            "ts": 1001.5, "disposition": "deny", "rule_id": "EG-METH-001",
            "reason": "method_not_allowed", "requirement": "FR-015",
            "method": "POST", "path": "/orders/O-1/cancel",
            "resolved_tier": "unresolved", "session_id": SESS_A,
            "policy_version": POLICY_VERSION, "absolute_https_denied": 0,
            "credential_fpr": "", "detail": "",
        },
        {
            "ts": 1002.5, "disposition": "allow", "rule_id": "EG-METH-001",
            "reason": "method_allowed", "requirement": "FR-015",
            "method": "GET", "path": "/stock/P1",
            "resolved_tier": "read", "session_id": SESS_B,
            "policy_version": POLICY_VERSION, "absolute_https_denied": 0,
            "credential_fpr": "", "detail": "",
        },
        {
            "ts": 1003.5, "disposition": "deny", "rule_id": "EG-METH-001",
            "reason": "method_not_allowed", "requirement": "FR-015",
            "method": "POST", "path": "/orders/O-1/cancel",
            "resolved_tier": "unresolved", "session_id": SESS_B,
            "policy_version": POLICY_VERSION, "absolute_https_denied": 0,
            "credential_fpr": "", "detail": "",
        },
    )
    for row in rows:
        names = ", ".join(row)
        marks = ", ".join("?" for _ in row)
        conn.execute(
            f"INSERT INTO {PHYSICAL_TABLE} ({names}) VALUES ({marks})",
            tuple(row.values()),
        )
    conn.commit()
    conn.close()
    return path


class Rig:
    def __init__(self, tmp_path: Path):
        self.tmp_path = tmp_path
        self.lifecycle = SessionTable(tmp_path / "session.sqlite3")
        self.repo = Repository(
            tmp_path / "runtime.sqlite3", role="runtime",
            tenant_id=TENANT, deployment_id=DEPLOYMENT,
        )
        self.store = SessionStore(self.repo, lifecycle=self.lifecycle)
        self.budget = BudgetLedger(
            BudgetJournal(self.repo, session_root=tmp_path / "root"),
            policy=ReservationPolicy(
                spend_usd=0.001, tokens=1, wall_clock_seconds=0.001,
            ),
        )
        self.journal = TurnJournal(self.repo)
        self.spans = SpanWriter(self.repo)
        self.machine = SessionStateMachine(self.lifecycle)
        self.runner = Runner(
            store=self.store,
            lifecycle=self.lifecycle,
            machine=self.machine,
            budget=self.budget,
            journal=self.journal,
            spans=self.spans,
            bound=ResultBound(
                bound_tokens=500, context_window_tokens=10_000, tokenizer=Tok(),
            ),
            retention=lambda session_id: RetentionStore(
                root=tmp_path / "scratch", session_id=session_id,
                max_bytes=1_000_000,
            ),
            versions=VERSIONS,
            tenant_id=TENANT,
            deployment_id=DEPLOYMENT,
            clock=_clock(),
            lease_interval_seconds=2_000_000_000.0,
            stall=StallPolicy(consecutive_turns=1_000),
        )

    def close(self) -> None:
        self.repo.close()
        self.lifecycle.close()


def _run_outcome_blob(outcome) -> str:
    assert not hasattr(outcome, "result"), (
        "a run produced a Result field; that call site is T214's and is "
        "still open"
    )
    assert outcome.end_of_run is not None
    return _blob({
        "session_id": outcome.session_id,
        "text": outcome.text,
        "terminal_state": outcome.terminal_state,
        "cancelled": outcome.cancelled,
        "turns": [turn.to_record() for turn in outcome.turns],
        "end_of_run": outcome.end_of_run.to_record(),
    })


def _event_stream_frames(outcome, judge: ShadowJudge) -> str:
    """Caller-visible SSE frames. The runner does not wire EventStream
    (T215 is not this slice). The stream is populated from the session's
    own turns through the product type, with the judge attached first so
    a leak into the frames would be visible.
    """
    stream = EventStream(outcome.session_id, clock=_clock())
    judge.attach(stream)
    stream.start()
    for turn in outcome.turns:
        stream.turn_started(turn.turn_index)
        for call, result in zip(turn.tool_calls, turn.tool_results):
            stream.tool_started(turn.turn_index, call)
            fields = getattr(result, "fields", None)
            assert fields is not None, (
                "a tool result reached the stream without BoundFields"
            )
            stream.tool_finished(turn.turn_index, result, fields)
        stream.turn_completed(turn)
    assert outcome.end_of_run is not None
    stream.end(outcome.end_of_run)
    return b"".join(sse_frame(event) for event in stream.events).decode("utf-8")


def _gate_decisions_blob(rig: Rig, session_id: str, proxy_db: Path) -> str:
    with ProxyDecisionReader(proxy_db) as reader:
        moved = ingest(
            reader, rig.spans, session_id=session_id, turn=0,
            versions=INGEST_VERSIONS, cost=COST,
        )
    assert moved.ingested > 0, (
        f"{session_id} ingested no gate decisions; comparing empty "
        "dispositions is the empty-Result failure on the gate channel"
    )
    rows: list[dict[str, object]] = []
    for stored in rig.spans.spans(session_id):
        payload = json.loads(stored["payload"])
        if payload.get("kind") != EGRESS_DECISION:
            continue
        detail = payload.get("detail") or {}
        if detail.get("source") != "proxy_decision_log":
            continue
        decision = payload.get("decision") or {}
        rows.append({
            "session_id": session_id,
            "decision_seq": detail["decision_seq"],
            "disposition": detail["disposition"],
            "rule_id": decision.get("rule_id"),
            "reason": detail["reason"],
            "requirement": detail["requirement"],
            "outcome": payload.get("outcome"),
        })
    rows.sort(key=lambda row: int(row["decision_seq"]))
    return _blob(rows)


def _require_populated(session_id: str, surfaces: dict[str, str]) -> None:
    missing = [name for name in CALLER_VISIBLE if name not in surfaces]
    assert missing == [], f"{session_id} dropped surfaces: {missing}"
    empty = [
        name for name in CALLER_VISIBLE
        if not str(surfaces[name]).strip()
    ]
    if GATE_DECISIONS_MAY_BE_EMPTY:
        empty = [name for name in empty if name != "gate_decisions"]
    assert empty == [], (
        f"{session_id} produced empty surfaces: {empty}. "
        "A differential over nothing is vacuous (SC-025)."
    )


def _surfaces_of(
    outcome,
    rig: Rig,
    judge: ShadowJudge,
    proxy_db: Path,
    result_id: str,
    verifier_label: str,
) -> dict[str, str]:
    frames = _event_stream_frames(outcome, judge)
    judge.consider(result_id, outcome.session_id, verifier_label)
    gates = _gate_decisions_blob(rig, outcome.session_id, proxy_db)
    surfaces = {
        "run_outcome": _run_outcome_blob(outcome),
        "event_stream": frames,
        "gate_decisions": gates,
    }
    _require_populated(outcome.session_id, surfaces)
    return surfaces


def _produce_mode(tmp_path: Path, mode: str) -> tuple[dict[str, dict[str, str]], list[dict[str, object]]]:
    """One inject mode over the same two sessions."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    proxy_db = _proxy_db(tmp_path / "decisions.sqlite3")
    judge_repo = Repository(
        tmp_path / "judge.sqlite3", role=ROLE_SHADOW_JUDGE,
        tenant_id=TENANT, deployment_id=DEPLOYMENT,
    )
    produced: dict[str, dict[str, str]] = {}

    rig_a = Rig(tmp_path / "sess-a")

    def model_a(context) -> ModelResponse:
        return _finish("the answer")

    outcome_a = rig_a.runner.start(
        session_id=SESS_A,
        prompt=PROMPT,
        ceilings=CEILINGS,
        capability_handle="handle-t175-a",
        model=model_a,
        execute=_execute,
    )
    assert outcome_a.terminal_state == terminal.COMPLETED.name

    contexts_b = {"turn": 0}
    rig_b = Rig(tmp_path / "sess-b")

    def model_b(context) -> ModelResponse:
        contexts_b["turn"] += 1
        if contexts_b["turn"] == 1:
            return ModelResponse(
                provider="test", provider_state=b"s", text="",
                spend_usd=0.0, spend_provenance=PROVENANCE_OPERATOR,
                tool_calls=(
                    ToolCall(
                        index=0, call_id="c0", name="get_stock",
                        arguments={"part_id": "P1"},
                    ),
                ),
            )
        return _finish("twelve")

    outcome_b = rig_b.runner.start(
        session_id=SESS_B,
        prompt=PROMPT,
        ceilings=CEILINGS,
        capability_handle="handle-t175-b",
        model=model_b,
        execute=_execute,
    )
    assert outcome_b.terminal_state == terminal.COMPLETED.name

    with ShadowJudge(judge_repo, decide_for(mode), clock=_clock()) as judge:
        produced[SESS_A] = _surfaces_of(
            outcome_a, rig_a, judge, proxy_db, RESULT_A, VERDICT_CORRECT,
        )
        if EVERY_SESSION:
            produced[SESS_B] = _surfaces_of(
                outcome_b, rig_b, judge, proxy_db, RESULT_B, VERDICT_INCORRECT,
            )
        judge.wait_idle()
        verdicts = [
            {
                "result_id": row["result_id"],
                "session_id": row["session_id"],
                "verdict": row["verdict"],
            }
            for row in judge.verdicts()
        ]
    rig_a.close()
    rig_b.close()
    judge_repo.close()
    return produced, verdicts


def _verdict_key(rows: list[dict[str, object]]) -> tuple[tuple[object, ...], ...]:
    return tuple(
        (row["result_id"], row["session_id"], row["verdict"])
        for row in sorted(rows, key=lambda r: str(r["result_id"]))
    )


# ---------------------------------------------------------------------------
# Controls. Without these, every assertion below is free.
# ---------------------------------------------------------------------------


def test_comparing_empty_result_lists_is_refused() -> None:
    """T214 has produced no Result. Identity over that empty set is free."""
    assert COMPARING_EMPTY_RESULT_LISTS_IS_THE_BATTERY is False
    results: dict[str, list[object]] = {mode: [] for mode in MODES}
    assert all(not rows for rows in results.values())
    if COMPARING_EMPTY_RESULT_LISTS_IS_THE_BATTERY:
        return


def test_the_caller_visible_surfaces_are_the_population() -> None:
    assert CALLER_VISIBLE == (
        "run_outcome",
        "event_stream",
        "gate_decisions",
    )
    assert len(CALLER_VISIBLE) == 3
    assert len(set(CALLER_VISIBLE)) == 3


def test_caller_visible_comparison_does_not_go_through_judge_verdict() -> None:
    """The measurement table proves the modes differed. It is not a surface."""
    assert "judge_verdict" not in CALLER_VISIBLE


def test_empty_gate_decisions_are_refused() -> None:
    assert GATE_DECISIONS_MAY_BE_EMPTY is False
    empty = {name: "" for name in CALLER_VISIBLE}
    try:
        _require_populated("sess-empty", empty)
    except AssertionError as caught:
        assert "empty surfaces" in str(caught)
        return
    raise AssertionError("empty gate decisions were accepted; the gate half is free")


def test_the_three_modes_are_the_population() -> None:
    assert MODES == (MODE_AGREE, MODE_DISAGREE, MODE_OFF)


# ---------------------------------------------------------------------------
# The battery. Same sessions, three modes, caller-visible identity.
# ---------------------------------------------------------------------------


def test_caller_visible_surfaces_and_gate_decisions_are_identical_across_modes(
    tmp_path: Path,
) -> None:
    by_mode: dict[str, dict[str, dict[str, str]]] = {}
    verdicts: dict[str, list[dict[str, object]]] = {}
    for mode in MODES:
        surfaces, rows = _produce_mode(tmp_path / mode, mode)
        assert SESS_A in surfaces
        assert EVERY_SESSION is True
        assert SESS_B in surfaces, (
            "every session of a population of one is free; this battery "
            "produces two"
        )
        by_mode[mode] = surfaces
        verdicts[mode] = rows

    assert SURFACES_ARE_COMPARED is True
    if SURFACES_ARE_COMPARED:
        agree = by_mode[MODE_AGREE]
        disagree = by_mode[MODE_DISAGREE]
        off = by_mode[MODE_OFF]
        assert agree == disagree, (
            "agree and disagree differed on a caller-visible surface; "
            "the judge leaked into what the caller sees"
        )
        assert agree == off, (
            "agree and off differed on a caller-visible surface; "
            "the judge leaked into what the caller sees"
        )

    for mode, sessions in by_mode.items():
        for session_id, surfaces in sessions.items():
            _require_populated(session_id, surfaces)
            joined = "\n".join(surfaces[name] for name in CALLER_VISIBLE)
            assert "judge_verdict" not in joined, (
                f"{mode}/{session_id} leaked the measurement table into "
                "a caller-visible surface"
            )
            assert RESULT_A not in joined and RESULT_B not in joined, (
                f"{mode}/{session_id} leaked a judge result id into a "
                "caller-visible surface"
            )

    assert THREE_MODES_WROTE_DIFFERENT_VERDICTS is True
    if THREE_MODES_WROTE_DIFFERENT_VERDICTS:
        agree_v = _verdict_key(verdicts[MODE_AGREE])
        disagree_v = _verdict_key(verdicts[MODE_DISAGREE])
        off_v = _verdict_key(verdicts[MODE_OFF])
        assert agree_v == (
            (RESULT_A, SESS_A, VERDICT_CORRECT),
            (RESULT_B, SESS_B, VERDICT_INCORRECT),
        ), f"agree did not echo the verifier labels: {agree_v}"
        assert disagree_v == (
            (RESULT_A, SESS_A, VERDICT_INCORRECT),
            (RESULT_B, SESS_B, VERDICT_CORRECT),
        ), f"disagree did not flip the verifier labels: {disagree_v}"
        assert agree_v != disagree_v
        assert OFF_WRITES_NOTHING is True
        if OFF_WRITES_NOTHING:
            assert off_v == (), f"off wrote verdicts: {off_v}"

    tool = by_mode[MODE_AGREE][SESS_B]["run_outcome"]
    assert "twelve" in tool, (
        "session B never completed a tool-using turn; the differential "
        "did not range over a tool-using session"
    )
    gates = by_mode[MODE_AGREE][SESS_A]["gate_decisions"]
    assert '"disposition": "allow"' in gates
    assert '"disposition": "deny"' in gates


def test_no_run_produces_a_result_t214_is_still_open() -> None:
    """Named residual. T213's join exists; no run, and not this battery, calls it."""
    assert T214_RESIDUAL_NO_RUN_PRODUCES_A_RESULT
    imported = _imported(THIS)
    for name in FORBIDDEN_BATTERY_IMPORTS:
        assert name not in imported, (
            f"this battery imported {name}; that is T214's call site "
            "and is still open"
        )
    hits: list[str] = []
    scanned = (
        *SUCCESS_PATH,
        *(REPO / "src" / "runtime" / "judge").glob("*.py"),
    )
    for path in scanned:
        relative = path.relative_to(REPO).as_posix()
        for node in ast.walk(ast.parse(path.read_text(), filename=str(path))):
            if isinstance(node, ast.Name) and node.id in JOIN_NAMES:
                hits.append(f"{relative} names {node.id}")
            if isinstance(node, ast.Attribute) and node.attr in JOIN_NAMES:
                hits.append(f"{relative} names {node.attr}")
    assert hits == [], (
        "a success-path or judge module called the T213 join; that call "
        "site is T214's and is still open:\n  " + "\n  ".join(hits)
    )


def test_forbidden_edges_stay_empty() -> None:
    """T025's structural half, re-asserted where the behavioural half now lives."""
    assert IMPORT_GRAPH_MUST_STAY_EMPTY is True
    assert forbidden_edges(REPO) == []


def test_the_success_path_does_not_import_the_judge() -> None:
    found: list[str] = []
    for path in SUCCESS_PATH:
        relative = path.relative_to(REPO).as_posix()
        for imported in sorted(_imported(path)):
            if imported == "src.runtime.judge" or imported.startswith(
                    "src.runtime.judge."):
                found.append(f"{relative} imports {imported}")
    assert found == [], (
        "a success-path module imported the judge:\n  " + "\n  ".join(found)
    )


def test_the_success_path_import_scan_fires_on_a_planted_judge_edge(
        tmp_path: Path) -> None:
    """The removal proof of loop/runner/serving/main → judge."""
    planted = tmp_path / "loop.py"
    planted.write_text("from src.runtime.judge.shadow import ShadowJudge\n")
    found: list[str] = []
    for imported in _imported(planted):
        if imported == "src.runtime.judge" or imported.startswith(
                "src.runtime.judge."):
            found.append(imported)
    assert found, "the success-path→judge scan did not report a planted import"


def test_the_battery_does_not_invent_t214_or_t215() -> None:
    imported = _imported(THIS)
    assert "src.runtime.serving" in imported or any(
        name.startswith("src.runtime.serving") for name in imported
    )
    bound = {
        node.id for node in ast.walk(ast.parse(THIS.read_text(), filename=str(THIS)))
        if isinstance(node, ast.Name)
    }
    assert "Registry" not in bound
    assert "build_server" not in bound
    assert "SessionView" not in bound


def test_the_residual_is_recorded() -> None:
    record_evidence("sc025-judge-differential", {
        "criterion": "SC-025",
        "task": "T175",
        "modes": list(MODES),
        "sessions": [SESS_A, SESS_B],
        "caller_visible": list(CALLER_VISIBLE),
        "what_this_establishes": [
            "The same two Runner sessions (one model-only, one tool-using) "
            "run under agree, disagree, and off.",
            "RunOutcome, EventStream SSE frames, and proxy-ingest gate "
            "dispositions are field-identical across the three modes.",
            "judge_verdict populations differ: agree echoes, disagree "
            "flips, off writes nothing.",
        ],
        "what_this_does_not": [
            "A run-produced Result (T214 is still open).",
            "Registry / build_server (T215).",
            "An adjudication queue (T176) or margin report (T177).",
            "A live vendor SDK (T058 PARTIAL).",
        ],
        "t214_residual": (
            "no run produces a Result; this battery does not invent "
            "result_join's call site so the judge has a live one"
        ),
    })
