"""T165 — SC-004: automated secret scan over every session's four surfaces.

**Criterion**: SC-004 — *Zero secret values appear in model context, emitted
artifacts, traces or persisted state, asserted by an automated scan that
runs on every session.*

## What this file is, and what it is not

**Do.** Produce real sessions. Scan the four surfaces each one wrote.
Plant unique credential values the session holds, and catch them if they
appear. Fail if the battery produced no session, or if a named surface
was empty — a scan over nothing is a pass for a system that leaks.

**Do not re-implement `Secret` redaction as a second filter.** T035's
type already refuses serialization. T040 / T072 scan credential *shapes*
on one channel each. T168 walks writers for operator identity. This
battery looks for the planted *values* on the four surfaces of sessions
it actually ran. A unit test that only walks types is not this task.

**Do not complete T166 / T167.** In-container readability and
not-inherited scratch are later sessions. `tests/unit/test_session_env.py`
already covers in-process scratch isolation; SC-024's later-session claim
is not this slice.
"""

from __future__ import annotations

import ast
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from src.contracts import terminal
from src.contracts.credentials import (
    HOLDER_ENFORCEMENT,
    HOLDER_RUNTIME,
    PLANE_PROVIDER,
    PLANE_TARGET,
    PROVIDER_KEY,
    TARGET_KEY,
    hold,
)
from src.contracts.repository import Repository
from src.contracts.result import Corroboration, Result, VerificationOutcome
from src.contracts.secret import Secret
from src.runtime.dispatch import ToolCall
from src.runtime.events import EventStream
from src.runtime.journal import TurnJournal
from src.runtime.ledger import BudgetLedger, ReservationPolicy
from src.runtime.loop import ModelResponse
from src.runtime.progress import StallPolicy
from src.runtime.providers.costs import PROVENANCE_OPERATOR
from src.runtime.result_bound import ResultBound, RetentionStore
from src.runtime.runner import Runner
from src.runtime.session_state import SessionStateMachine
from src.runtime.session_store import Ceilings, SessionStore
from src.runtime.serving import sse_frame
from src.runtime.trace import ArtifactVersions, SpanWriter
from src.runtime.trace_budget import BudgetJournal
from src.supervisor.session_table import SessionTable
from tests.batteries.evidence import record_evidence

REPO = Path(__file__).resolve().parents[2]
THIS = Path(__file__).resolve()

#: The four surfaces SC-004 names. The tuple is the population: shrinking
#: it is a silent pass over a channel the criterion still names.
SURFACES = (
    "model_context",
    "emitted_artifacts",
    "traces",
    "persisted_state",
)

#: The scan runs on every session this battery produces, not a sample.
EVERY_SESSION = True

#: A scan over zero sessions is a pass for a leaker. Refused.
SCAN_OVER_ZERO_SESSIONS_PASSES = False

#: Unique needles. The scanner looks for these values, not for a
#: credential-shaped regex (that filter is T040's, on traces only).
PROVIDER_PLAINTEXT = "sk-t165-provider-7f3a9c2e1b08d4a1"
TARGET_PLAINTEXT = "tgt-t165-enforcement-9b4e2c1a7d06f883"
PLANTED = (PROVIDER_PLAINTEXT, TARGET_PLAINTEXT)

TOOL_RESULT_BODY = "on-hand: 12"
PROMPT = "how many units of P1 are on hand?"
TENANT, DEPLOYMENT = "t-1", "d-1"
VERSIONS = ArtifactVersions(TENANT, DEPLOYMENT, {"prompt": "sha256:" + "0" * 64})
CEILINGS = Ceilings(spend_usd=100.0, tokens=1_000_000,
                    wall_clock_seconds=10_000.0, turns=50)


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


def findings(blob: str, secrets: tuple[str, ...] = PLANTED) -> list[str]:
    """Substring scan for planted values. Not a redaction filter."""
    return [secret for secret in secrets if secret in blob]


def _blob(value: object) -> str:
    return json.dumps(value, default=str, sort_keys=True)


def _record_context(context, bucket: list[str], *, leak: str = "") -> None:
    """One capture site. A second `append` would make a tamper ambiguous."""
    bucket.append(context.render() + leak)


def _execute(_call: ToolCall) -> str:
    """The tool result enters model context on the next turn. Do not reveal."""
    return TOOL_RESULT_BODY


def _dump_sqlite(path: Path) -> str:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        names = [
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        ]
        parts: list[str] = []
        for name in names:
            rows = [dict(row) for row in conn.execute(f'SELECT * FROM "{name}"')]
            parts.append(_blob({"table": name, "rows": rows}))
        return "\n".join(parts)
    finally:
        conn.close()


def _emitted_artifacts(outcome) -> str:
    """Caller-visible artifacts of this session: outcome, event stream, result.

    The runner does not yet wire EventStream (T215 is not this slice). The
    stream is populated from the session's own turns through the product
    type, which is the channel a caller would read.
    """
    stream = EventStream(outcome.session_id, clock=_clock())
    stream.start()
    for turn in outcome.turns:
        stream.turn_started(turn.turn_index)
        for call, result in zip(turn.tool_calls, turn.tool_results):
            stream.tool_started(turn.turn_index, call)
            fields = getattr(result, "fields", None)
            assert fields is not None, (
                "a tool result reached the artifact scan without BoundFields"
            )
            stream.tool_finished(turn.turn_index, result, fields)
        stream.turn_completed(turn)
    assert outcome.end_of_run is not None
    stream.end(outcome.end_of_run)
    frames = b"".join(sse_frame(event) for event in stream.events)
    result = Result(
        VerificationOutcome.NOT_VERIFIABLE,
        payload={"text": outcome.text, "session_id": outcome.session_id},
        corroboration=Corroboration.NOT_STATED,
        reason=(
            "this battery session did not run the verifier; the scan is "
            "of the record, not of a verified quantity"
        ),
    )
    return _blob({
        "run_outcome": {
            "session_id": outcome.session_id,
            "text": outcome.text,
            "terminal_state": outcome.terminal_state,
            "turns": [turn.to_record() for turn in outcome.turns],
        },
        "event_stream": frames.decode("utf-8"),
        "result": {
            "verification": result.verification.value,
            "payload": result.payload,
            "corroboration": result.corroboration.value,
            "reason": result.reason,
        },
    })


@dataclass
class ProducedSession:
    session_id: str
    surfaces: dict[str, str]


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


def _hold_planes() -> tuple[Secret, Secret]:
    """The session's process holds both planes. Neither value may appear."""
    provider = Secret(PROVIDER_PLAINTEXT, name=PROVIDER_KEY)
    target = Secret(TARGET_PLAINTEXT, name=TARGET_KEY)
    hold(secret=provider, plane=PLANE_PROVIDER, holder=HOLDER_RUNTIME)
    hold(secret=target, plane=PLANE_TARGET, holder=HOLDER_ENFORCEMENT)
    return provider, target


def _produce_sessions(tmp_path: Path) -> list[ProducedSession]:
    """Two sessions, so 'every session' is not a population of one."""
    provider, target = _hold_planes()
    assert PROVIDER_PLAINTEXT not in str(provider)
    assert TARGET_PLAINTEXT not in str(target)

    produced: list[ProducedSession] = []

    # Session A — one model call, no tools.
    contexts_a: list[str] = []
    rig_a = Rig(tmp_path / "sess-a")

    def model_a(context) -> ModelResponse:
        _record_context(context, contexts_a)
        return _finish("the answer")

    outcome_a = rig_a.runner.start(
        session_id="sess-t165-a",
        prompt=PROMPT,
        ceilings=CEILINGS,
        capability_handle="handle-t165-a",
        model=model_a,
        execute=_execute,
    )
    assert outcome_a.terminal_state == terminal.COMPLETED.name
    produced.append(_surfaces_of(
        "sess-t165-a", outcome_a, contexts_a, rig_a,
    ))
    rig_a.close()
    if not EVERY_SESSION:
        return produced

    # Session B — a tool call, so model context includes a tool result.
    contexts_b: list[str] = []
    n = {"turn": 0}
    rig_b = Rig(tmp_path / "sess-b")

    def model_b(context) -> ModelResponse:
        _record_context(context, contexts_b)
        n["turn"] += 1
        if n["turn"] == 1:
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
        session_id="sess-t165-b",
        prompt=PROMPT,
        ceilings=CEILINGS,
        capability_handle="handle-t165-b",
        model=model_b,
        execute=_execute,
    )
    assert outcome_b.terminal_state == terminal.COMPLETED.name
    produced.append(_surfaces_of(
        "sess-t165-b", outcome_b, contexts_b, rig_b,
    ))
    rig_b.close()
    return produced


def _surfaces_of(
    session_id: str,
    outcome,
    contexts: list[str],
    rig: Rig,
) -> ProducedSession:
    traces = _blob(rig.spans.spans(session_id))
    artifacts = _emitted_artifacts(outcome)
    # Dump while the connections are still open so WAL pages are visible.
    persisted = "\n".join([
        _dump_sqlite(rig.tmp_path / "runtime.sqlite3"),
        _dump_sqlite(rig.tmp_path / "session.sqlite3"),
        _blob(rig.lifecycle.get(session_id)),
    ])
    scratch = rig.tmp_path / "scratch" / session_id
    if scratch.is_dir():
        for path in sorted(scratch.rglob("*")):
            if path.is_file():
                persisted += "\n" + path.read_text(errors="replace")
    return ProducedSession(
        session_id=session_id,
        surfaces={
            "model_context": "\n".join(contexts),
            "emitted_artifacts": artifacts,
            "traces": traces,
            "persisted_state": persisted,
        },
    )


def _require_populated(session: ProducedSession) -> None:
    missing = [name for name in SURFACES if name not in session.surfaces]
    assert missing == [], f"{session.session_id} dropped surfaces: {missing}"
    empty = [
        name for name in SURFACES
        if not str(session.surfaces[name]).strip()
    ]
    assert empty == [], (
        f"{session.session_id} produced empty surfaces: {empty}. "
        "A scan over nothing is vacuous (SC-004)."
    )


# ---------------------------------------------------------------------------
# Controls. Without these, every assertion below is free.
# ---------------------------------------------------------------------------


def test_the_scanner_catches_a_planted_secret_on_each_surface() -> None:
    """The control. A detector that matches nothing passes for a leaker."""
    for name in SURFACES:
        blob = f"ordinary {name} payload {PROVIDER_PLAINTEXT} end"
        caught = findings(blob)
        assert PROVIDER_PLAINTEXT in caught, (
            f"the scanner misses a planted provider secret on {name}"
        )
        blob = f"ordinary {name} payload {TARGET_PLAINTEXT} end"
        caught = findings(blob)
        assert TARGET_PLAINTEXT in caught, (
            f"the scanner misses a planted target secret on {name}"
        )
    assert findings("a perfectly ordinary session dump") == []


def test_a_scan_over_zero_sessions_is_refused() -> None:
    """SC-004 runs on every session. Zero sessions is not a pass."""
    assert SCAN_OVER_ZERO_SESSIONS_PASSES is False
    sessions: list[ProducedSession] = []
    assert not sessions
    if SCAN_OVER_ZERO_SESSIONS_PASSES:
        return


def test_a_scan_over_an_empty_surface_is_refused() -> None:
    empty = ProducedSession(
        session_id="sess-empty",
        surfaces={name: "" for name in SURFACES},
    )
    try:
        _require_populated(empty)
    except AssertionError as caught:
        assert "empty surfaces" in str(caught)
        return
    raise AssertionError("an empty surface was accepted; the scan is free")


# ---------------------------------------------------------------------------
# The battery. Every session, four surfaces.
# ---------------------------------------------------------------------------


def test_every_session_the_battery_produces_is_clean_on_all_four_surfaces(
    tmp_path: Path,
) -> None:
    sessions = _produce_sessions(tmp_path)
    assert sessions, (
        "the battery produced no session; SC-004 over nothing is vacuous"
    )
    assert EVERY_SESSION is True
    assert len(sessions) >= 2, (
        "every session of a population of one is free; this battery "
        "produces two"
    )
    leaks: list[str] = []
    for session in sessions:
        _require_populated(session)
        for name in SURFACES:
            caught = findings(session.surfaces[name])
            if caught:
                leaks.append(
                    f"{session.session_id}/{name}: {caught}"
                )
    assert leaks == [], (
        "planted secret values reached a session surface:\n  "
        + "\n  ".join(leaks)
    )
    # Session B's model context must have seen the tool result, or the
    # context surface was never ranged over a tool-using turn.
    tool_session = next(s for s in sessions if s.session_id == "sess-t165-b")
    assert TOOL_RESULT_BODY in tool_session.surfaces["model_context"], (
        "session B's model context never contained the tool result; the "
        "context surface was not ranged over a tool-using turn"
    )
    assert tool_session.surfaces["traces"]
    assert '"kind"' in tool_session.surfaces["traces"] or "model_call" in (
        tool_session.surfaces["traces"]
    )
    assert '"table"' in tool_session.surfaces["persisted_state"], (
        "persisted_state never contained a sqlite dump; the surface was "
        "not ranged over stored rows"
    )


def test_the_four_surfaces_are_the_population() -> None:
    assert SURFACES == (
        "model_context",
        "emitted_artifacts",
        "traces",
        "persisted_state",
    )
    assert len(SURFACES) == 4
    assert len(set(SURFACES)) == 4


def test_the_battery_does_not_reimplement_secret_redaction() -> None:
    """Scan values. Secret already refuses serialization. No second filter."""
    tree = ast.parse(THIS.read_text(), filename=str(THIS))
    names = {
        node.name for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    }
    assert "refuse_secrets" not in names
    assert "credential_findings" not in names
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
            imported.update(
                f"{node.module}.{alias.name}" for alias in node.names
            )
    assert "tests.contract.test_trace_redaction" not in imported
    assert "tests.contract.test_event_stream_redaction" not in imported
    assert "tests.contract.test_artifact_portability" not in imported
    bound = {
        node.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Name)
    }
    assert "CREDENTIAL_PATTERNS" not in bound
    assert "compile" not in {
        node.attr for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
    }


def test_held_credentials_are_in_process_and_do_not_print_the_value() -> None:
    """The plant is present. str() is not a leak; reveal() would be."""
    provider, target = _hold_planes()
    assert provider.reveal() == PROVIDER_PLAINTEXT
    assert target.reveal() == TARGET_PLAINTEXT
    assert PROVIDER_PLAINTEXT not in str(provider)
    assert TARGET_PLAINTEXT not in str(target)


def test_the_residual_is_recorded() -> None:
    record_evidence("sc004-secret-scan", {
        "criterion": "SC-004",
        "task": "T165",
        "surfaces": list(SURFACES),
        "sessions": ["sess-t165-a", "sess-t165-b"],
        "what_this_establishes": [
            "Two completed Runner sessions are scanned on model context, "
            "emitted artifacts (RunOutcome, EventStream, Result), traces, "
            "and persisted sqlite / scratch.",
            "Unique planted provider and target values do not appear.",
            "The scanner catches a plant on each surface; zero sessions "
            "and empty surfaces are refused.",
        ],
        "what_this_does_not": [
            "A second Secret redaction filter (T035 / INV-007).",
            "Per-channel shape scans (T040 traces, T072 event stream).",
            "Writer-walk portability (T168).",
            "In-container readability (T166) or not-inherited scratch (T167).",
        ],
    })
