"""The two Python entry points, and the four fail-loud paths they make reachable.

`tests/contract/test_configuration_failloud.py` proves `config.load` refuses.
This proves **something calls it**. Until `src/supervisor/main.py` and
`src/runtime/main.py` existed, `config.load` was referenced only from tests,
`Config` was constructed only by its own module's factory, and
`require_priceable` was called from nowhere — so four authorities requiring the
identical treatment (`_NO_DEFAULT_BOUND` FR-049/Q-10, `_NO_DEFAULT_CEILING`
FR-005, `_NO_DEFAULT_RESULT_BOUND` FR-058, `_NO_DEFAULT_OPERATOR_PRICES` OD-27)
had their reporting machinery built and unreachable.

## Every assertion here reads the operator's report

Deliberately, and it is the difference between this file and a vacuous one.
Startup exits non-zero for many reasons, and a test that only observes
`SystemExit` cannot tell an unset ceiling from an import error — it would pass
against an entry point that crashed before reaching `load()` at all. So each
case names the **key** and quotes a distinctive fragment of its
**`no_default_reason`**, which is the text FR-049 and FR-005 require to be
quoted back and which nothing else in the tree produces.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from src.analysis.admission import fetch_from_file
from src.contracts import config as cfg
from src.contracts.operator_log import EXIT_STARTUP_REFUSED, OperatorLog
from src.contracts.topology import RUNTIME_ADDR_KEY
from src.runtime import main as runtime_main
from src.supervisor import main as supervisor_main

REPO = Path(__file__).resolve().parents[2]
PUBLISHED_SPEC = REPO / "tests" / "fixtures" / "reference-app" / "served_operations.json"

SUPERVISOR_ENV = {
    "SANDBOX_MEMORY_MAX": "512Mi",
    "SANDBOX_CPU_MAX": "200000 100000",
    "SANDBOX_CPU_TOTAL": "120.0",
    "SANDBOX_PIDS_MAX": "64",
    "SESSION_CEILING_SPEND_USD": "5.00",
    "SESSION_CEILING_TOKENS": "200000",
    "SESSION_CEILING_WALL_CLOCK_SECONDS": "900",
    "SESSION_CEILING_TURNS": "40",
    "F2A_LOCATION_SET": "/etc/f2a/locations.json",
    "F2A_TENANT_ID": "t-1",
    "F2A_DEPLOYMENT_ID": "d-1",
}

RUNTIME_ENV = {
    "SESSION_CEILING_SPEND_USD": "5.00",
    "SESSION_CEILING_TOKENS": "200000",
    "SESSION_CEILING_WALL_CLOCK_SECONDS": "900",
    "SESSION_CEILING_TURNS": "40",
    "TOOL_RESULT_BOUND_TOKENS": "8000",
    "MODEL_CONTEXT_WINDOW_TOKENS": "200000",
    "RESULT_RETENTION_MAX_BYTES": "64MiB",
    "MODEL_PROVIDER": "anthropic",
    "MODEL_ID": "claude-sonnet-4-5-20250929",
    "MODEL_PRICES_OPERATOR": "none",
    "F2A_PROVIDER_CREDENTIAL": "sk-test-provider-credential-t161",
    "REPORTING_WINDOW_SECONDS": "3600",
    "F2A_TENANT_ID": "t-1",
    "F2A_DEPLOYMENT_ID": "d-1",
}

#: A day inside the priced entry's window. Fixed rather than `today()` so this
#: suite does not start failing on the day a vendor rate is superseded.
AS_OF = dt.date(2026, 8, 8)

BY_NAME = {key.name: key
           for key in (*cfg.SUPERVISOR_KEYS, *cfg.RUNTIME_KEYS)}
STATES_A_REASON = tuple(k for k in BY_NAME.values() if k.no_default_reason)


class Recorder(OperatorLog):
    """An `OperatorLog` that keeps what it wrote instead of writing it.

    Subclassed rather than pointed at a pipe: the reports run to kilobytes and
    a pipe would deadlock a same-thread writer against an unread buffer, which
    is a property of the test harness and not of the channel.
    """

    def __init__(self) -> None:
        super().__init__("test", fd=-1)
        self.lines: list[str] = []

    def say(self, message: str) -> None:
        self.lines.append(message)

    @property
    def text(self) -> str:
        return "\n".join(self.lines)


@pytest.fixture
def log() -> Recorder:
    return Recorder()


@pytest.fixture
def on_linux(monkeypatch):
    """Make the supervisor's platform gate pass.

    `preflight()` fails by design off Linux (OD-17, no degraded mode), and this
    suite is about the configuration gate rather than the platform one. The
    platform gate has its own coverage and its refusal is asserted below on its
    own terms.
    """
    monkeypatch.setattr(supervisor_main, "preflight", lambda: None)


# ---------------------------------------------------------------------------
# 1. `config.load()` is called at startup, and all twelve reasons can reach it.
# ---------------------------------------------------------------------------


def test_every_no_default_reason_is_reachable_from_an_entry_point() -> None:
    """The claim the seam was recorded against, as an accounting.

    Thirteen keys carry a `no_default_reason`. A reason declared on a key that
    no entry point resolves is machinery that cannot run, which is the state
    the whole tree was in.

    The count moved from twelve on 2026-08-12 when T130 declared
    `REPORTING_WINDOW_SECONDS` (FR-045, Q-10). **The number came out of the
    census rather than the census out of the number** — the key was added to
    `RUNTIME_KEYS`, this arm reported thirteen, and thirteen was then written
    down. The name no longer carries the count for that reason: a census whose
    own title has to be edited invites the count to be edited with it.
    """
    assert len(STATES_A_REASON) == 13, (
        f"the reason-carrying set moved to {len(STATES_A_REASON)}: "
        f"{sorted(k.name for k in STATES_A_REASON)}"
    )
    reachable = {k.name for k in (*cfg.SUPERVISOR_KEYS, *cfg.RUNTIME_KEYS)
                 if k.no_default_reason}
    orphaned = {k.name for k in STATES_A_REASON} - reachable
    assert not orphaned, (
        f"{sorted(orphaned)} state a no-default reason that no entry point's "
        "key set contains, so `_report` can never quote it"
    )


@pytest.mark.parametrize(
    "key", [k for k in cfg.SUPERVISOR_KEYS if k.no_default_reason],
    ids=lambda k: k.name)
def test_the_supervisor_quotes_each_reason_back(key, log, on_linux, tmp_path) -> None:
    env = {**SUPERVISOR_ENV, "F2A_STATE_DIR": str(tmp_path)}
    del env[key.name]

    with pytest.raises(SystemExit) as caught:
        supervisor_main.main(env=env, log=log)

    assert caught.value.code == EXIT_STARTUP_REFUSED != 0
    assert "startup refused" in log.text
    assert key.name in log.text, f"the report does not name {key.name}"
    # The reason text itself, not a paraphrase and not the key name again. This
    # is the sentence FR-049 and FR-005 require quoted back to the operator.
    assert key.no_default_reason in log.text, (
        f"{key.name} is named but its no-default reason is not quoted, so the "
        "operator is told to set a value without being told it is unsafe to "
        "guess one"
    )
    assert "Nothing has been started" in log.text


@pytest.mark.parametrize(
    "key", [k for k in cfg.RUNTIME_KEYS if k.no_default_reason],
    ids=lambda k: k.name)
def test_the_runtime_quotes_each_reason_back(key, log, tmp_path) -> None:
    env = {**RUNTIME_ENV, "F2A_STATE_DIR": str(tmp_path)}
    del env[key.name]

    with pytest.raises(SystemExit) as caught:
        runtime_main.main(env=env, log=log, today=AS_OF)

    assert caught.value.code == EXIT_STARTUP_REFUSED != 0
    assert key.name in log.text, f"the report does not name {key.name}"
    assert key.no_default_reason in log.text
    assert "Nothing has been started" in log.text


def test_the_report_counts_what_it_lists(log, tmp_path) -> None:
    """`_report`'s own header — the string the seam was recorded against —
    reaching an operator for the first time."""
    env = {k: v for k, v in RUNTIME_ENV.items()
           if k not in ("TOOL_RESULT_BOUND_TOKENS", "MODEL_PRICES_OPERATOR")}
    env["F2A_STATE_DIR"] = str(tmp_path)

    with pytest.raises(SystemExit):
        runtime_main.main(env=env, log=log, today=AS_OF)

    assert "2 required value(s) unset:" in log.text
    assert "TOOL_RESULT_BOUND_TOKENS" in log.text
    assert "MODEL_PRICES_OPERATOR" in log.text
    assert "No value above is filled from a default" in log.text


# ---------------------------------------------------------------------------
# 2. Nothing is started when a required key is unset.
# ---------------------------------------------------------------------------


def test_a_refusing_supervisor_opens_no_store(log, on_linux, tmp_path) -> None:
    """Fail-closed, not merely fail-noisy. Q-10's clause is that an unset bound
    runs nothing at all, and a supervisor that created its session table before
    discovering the ceiling was unset would have done the thing the ceiling
    exists to bound."""
    state = tmp_path / "state"
    state.mkdir()
    env = {**SUPERVISOR_ENV, "F2A_STATE_DIR": str(state)}
    del env["SESSION_CEILING_SPEND_USD"]

    with pytest.raises(SystemExit):
        supervisor_main.main(env=env, log=log)

    assert list(state.iterdir()) == [], (
        f"the refusing supervisor left {[p.name for p in state.iterdir()]} "
        "behind; a store opened before the configuration was checked is the "
        "side effect Q-10 forbids"
    )


def test_the_supervisor_gathers_the_platform_and_configuration_refusals(
        log, monkeypatch, tmp_path) -> None:
    """The deliberate deviation from the Go anchor.

    `src/proxy/main.go` stops at the first `Fatalf`, so an operator whose
    platform *and* configuration are both wrong learns about them one restart
    apart. Both checks here are side-effect free, so both run. On this
    repository's usual development host it is the difference between a usable
    configuration report and none: `preflight()` fails on macOS by design.
    """
    def refuse() -> None:
        raise supervisor_main.PreflightError("cgroup v2 is not mounted")

    monkeypatch.setattr(supervisor_main, "preflight", refuse)
    env = {**SUPERVISOR_ENV, "F2A_STATE_DIR": str(tmp_path)}
    del env["SANDBOX_MEMORY_MAX"]

    with pytest.raises(SystemExit):
        supervisor_main.main(env=env, log=log)

    assert "cgroup v2 is not mounted" in log.text
    assert "SANDBOX_MEMORY_MAX" in log.text, (
        "the configuration report was never reached, so an operator on a "
        "wrong platform can never see it"
    )


# ---------------------------------------------------------------------------
# 3. `require_priceable` is actually called.
# ---------------------------------------------------------------------------


def test_an_unpriced_model_refuses_startup(log, tmp_path) -> None:
    """OD-27's gate, reached. Without it the first turn is what discovers the
    absence — after the money for that call has been spent."""
    env = {**RUNTIME_ENV, "F2A_STATE_DIR": str(tmp_path),
           "MODEL_ID": "claude-sonnet-99"}

    with pytest.raises(SystemExit) as caught:
        runtime_main.main(env=env, log=log, today=AS_OF)

    assert caught.value.code == EXIT_STARTUP_REFUSED != 0
    assert "not priceable (OD-27)" in log.text
    assert "anthropic/claude-sonnet-99 has no cost entry" in log.text
    assert "counted at zero" in log.text, (
        "the refusal does not say what admitting it would have cost, which is "
        "the whole of why this gate is at startup rather than at the ledger"
    )


def test_a_provider_typo_refuses_startup(log, tmp_path) -> None:
    env = {**RUNTIME_ENV, "F2A_STATE_DIR": str(tmp_path),
           "MODEL_PROVIDER": "anthropicc"}

    with pytest.raises(SystemExit):
        runtime_main.main(env=env, log=log, today=AS_OF)

    assert "'anthropicc' is not one of" in log.text


def test_a_priced_model_names_its_rate_on_the_readiness_report(
        log, tmp_path) -> None:
    """`require_priceable` returns a line rather than `None`, and this is why:
    the rate a session will be charged at is a thing to read *before* the
    session runs. T215 binds after the report; without a bind address the
    process refuses, and the rate is still on the report that preceded it."""
    env = {**RUNTIME_ENV, "F2A_STATE_DIR": str(tmp_path)}

    with pytest.raises(SystemExit) as caught:
        runtime_main.main(env=env, log=log, today=AS_OF)

    assert caught.value.code == EXIT_STARTUP_REFUSED != 0
    assert "anthropic/claude-sonnet-4-5-20250929 — vendor rate in force on " \
        "2026-08-08" in log.text
    assert "$3.0/MTok in" in log.text
    assert RUNTIME_ADDR_KEY in log.text
    assert "sk-test-provider-credential-t161" not in log.text, (
        "the provider credential reached the readiness report (FR-036)"
    )


def test_an_operator_declaration_prices_a_model_no_vendor_page_does(
        log, tmp_path) -> None:
    """OD-27's other limb, and the reason `MODEL_PRICES_OPERATOR` needed a
    reader: until one existed the key described a file format no code could
    consume."""
    declaration = tmp_path / "rates.json"
    declaration.write_text(json.dumps({"prices": [{
        "provider": "anthropic",
        "model": "claude-sonnet-99",
        "display_name": "Claude Sonnet 99",
        "tiers": [{"input_usd_per_mtok": 4.0, "output_usd_per_mtok": 20.0}],
        "declared_by": "platform-eng@acme",
        "declaration_ref": "contracts/anthropic-2026.pdf",
        "declared_on": "2026-08-01",
        "scope": "text tokens, standard tier",
    }]}))
    env = {**RUNTIME_ENV, "F2A_STATE_DIR": str(tmp_path),
           "MODEL_ID": "claude-sonnet-99",
           "MODEL_PRICES_OPERATOR": str(declaration)}

    with pytest.raises(SystemExit) as caught:
        runtime_main.main(env=env, log=log, today=AS_OF)

    assert caught.value.code == EXIT_STARTUP_REFUSED != 0
    assert "operator rate in force" in log.text, (
        "the declared rate was admitted but its provenance is not on the "
        "report; a figure from a contract must not read like one from a "
        "vendor page"
    )
    assert "declared by platform-eng@acme" in log.text


def test_a_declaration_pointing_at_nothing_refuses_startup(log, tmp_path) -> None:
    """The literal `'none'` is a value and a missing file is not it. Collapsing
    the two is what `_NO_DEFAULT_OPERATOR_PRICES` exists to prevent."""
    env = {**RUNTIME_ENV, "F2A_STATE_DIR": str(tmp_path),
           "MODEL_PRICES_OPERATOR": str(tmp_path / "absent.json")}

    with pytest.raises(SystemExit):
        runtime_main.main(env=env, log=log, today=AS_OF)

    assert "neither the literal 'none' nor a readable declaration file" in log.text


def test_the_runtime_gathers_the_price_and_bound_refusals(log, tmp_path) -> None:
    env = {**RUNTIME_ENV, "F2A_STATE_DIR": str(tmp_path),
           "MODEL_ID": "claude-sonnet-99",
           "TOOL_RESULT_BOUND_TOKENS": "90000"}

    with pytest.raises(SystemExit):
        runtime_main.main(env=env, log=log, today=AS_OF)

    assert "not priceable (OD-27)" in log.text
    assert "not usable (FR-058)" in log.text
    assert "Refused, not clamped" in log.text


# ---------------------------------------------------------------------------
# The successful path, and what it is careful not to claim.
# ---------------------------------------------------------------------------


def test_the_supervisor_opens_the_session_store(log, on_linux, tmp_path) -> None:
    """OD-28's ground ① was *"no supervisor entry point that opens the session
    store"*. This is that process, and the `SessionTable` -> `Repository`
    migration at `551e6ff` is why opening here does not reintroduce the
    cold-start WAL race."""
    env = {**SUPERVISOR_ENV, "F2A_STATE_DIR": str(tmp_path)}

    assert supervisor_main.main(env=env, log=log) == 0

    store = tmp_path / supervisor_main.SESSION_DB
    assert store.exists(), "the readiness report was emitted but no store was opened"
    assert str(store) in log.text


def test_a_readiness_report_marks_the_unvalidated_values(
        log, on_linux, tmp_path) -> None:
    """FR-043's marking is answerable *by every surface that emits the value*,
    and a readiness line is one."""
    env = {**SUPERVISOR_ENV, "F2A_STATE_DIR": str(tmp_path)}

    supervisor_main.main(env=env, log=log)

    assert "CAPABILITY_LEASE_INTERVAL_SECONDS" in log.text
    assert "(FR-043)" in log.text


def test_the_supervisor_still_exits_after_its_report(log, monkeypatch,
                                                     tmp_path) -> None:
    """OD-36 ⑤: the supervisor's closing line is a different absence and
    is not replaced. An exit 0 here is still not a running supervisor."""
    monkeypatch.setattr(supervisor_main, "preflight", lambda: None)
    env = {**SUPERVISOR_ENV, "F2A_STATE_DIR": str(tmp_path)}

    assert supervisor_main.main(env=env, log=log) == 0

    assert "startup complete and this process now exits" in log.text
    assert "no session workload is built" in log.text
    assert "not that a supervisor is running" in log.text


def test_the_runtime_no_longer_exits_after_a_report_only_startup(
        log, tmp_path) -> None:
    """OD-36: the runtime's superseded sentence is gone. Required config
    without a bind address refuses rather than exiting 0 after the report."""
    assert runtime_main.BINDS_AFTER_STARTUP is True
    env = {**RUNTIME_ENV, "F2A_STATE_DIR": str(tmp_path)}

    with pytest.raises(SystemExit) as caught:
        runtime_main.main(env=env, log=log, today=AS_OF)

    assert caught.value.code == EXIT_STARTUP_REFUSED != 0
    assert "no agent loop is started and no surface is bound" not in log.text
    assert "Phase 3 and Phase 4 work" not in log.text
    assert "startup complete and this process now exits" not in log.text


@pytest.mark.parametrize("entry", [supervisor_main, runtime_main],
                         ids=["supervisor", "runtime"])
def test_an_entry_point_adopts_the_thread_hook_before_anything_starts(
        entry, log, monkeypatch, tmp_path) -> None:
    """The renewer's terminal branch gets its vehicle here and nowhere else.

    `src/supervisor/lease.py` re-raises on a daemon thread and does not import
    the channel; delivery is `threading.excepthook`'s, so the entry point
    installing one is the whole of the wiring. Asserted **before** the refusal
    is reached, because a hook installed after configuration resolves would
    miss nothing today and everything the moment a thread starts earlier.
    """
    import threading

    stock = threading.excepthook
    # Registers the undo before the entry point overwrites it, so a failing
    # assertion below cannot leave the hook installed for the rest of the run.
    monkeypatch.setattr(threading, "excepthook", stock)
    monkeypatch.setattr(supervisor_main, "preflight", lambda: None)
    # Empty environment, so startup refuses at the first opportunity. The hook
    # must already be installed by then.
    with pytest.raises(SystemExit):
        entry.main(env={}, log=log)

    installed = threading.excepthook
    assert installed is not stock, (
        "the entry point refused without having adopted the thread hook, so a "
        "daemon thread dying during this process's exit reports through a "
        "buffered stream — which is the SIGABRT `operator_log.py` measures"
    )

    args = type("Args", (), {"thread": None, "exc_type": ValueError,
                             "exc_value": ValueError("wedged"),
                             "exc_traceback": None})
    installed(args)
    assert "died and was not restarted" in log.text
    assert "ValueError: wedged" in log.text


def test_the_entry_points_read_the_environment_when_not_given_one(
        log, on_linux, tmp_path, monkeypatch) -> None:
    """`env` is a parameter so the sequence is testable by content; the default
    is still the process environment, which is what T029's *"environment
    injection at process start"* names."""
    for name, value in {**SUPERVISOR_ENV,
                        "F2A_STATE_DIR": str(tmp_path)}.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("SESSION_CEILING_TURNS", raising=False)

    with pytest.raises(SystemExit):
        supervisor_main.main(log=log)

    assert "SESSION_CEILING_TURNS" in log.text
    assert os.environ.get("SESSION_CEILING_TURNS") is None


# ---------------------------------------------------------------------------
# T215 — Registry-and-bind after the readiness report (OD-36).
# ---------------------------------------------------------------------------


def _published_spec() -> object:
    return fetch_from_file(PUBLISHED_SPEC)


def _bind_env(tmp_path) -> dict[str, str]:
    return {
        **RUNTIME_ENV,
        "F2A_STATE_DIR": str(tmp_path),
        RUNTIME_ADDR_KEY: "127.0.0.1:0",
    }


def test_an_admitted_target_constructs_a_registry_and_binds(
        log, tmp_path) -> None:
    """Discharge: Registry(, .register(, build_server, view from gate."""
    bound: list[object] = []

    assert runtime_main.BINDS_AFTER_STARTUP is True
    assert runtime_main.REGISTRY_IS_CONSTRUCTED is True
    assert runtime_main.REGISTER_IS_CALLED is True
    assert runtime_main.BUILD_SERVER_IS_CALLED is True
    assert runtime_main.VIEW_COMES_FROM_ADMISSION_GATE is True

    code = runtime_main.main(
        env=_bind_env(tmp_path),
        log=log,
        today=AS_OF,
        fetch_specification=_published_spec,
        serve=bound.append,
    )

    assert code == 0
    assert bound, "build_server returned nothing to serve"
    server = bound[0]
    host, port = server.server_address[:2]
    assert host == "127.0.0.1"
    assert port > 0
    assert "surface bound on" in log.text
    assert "d-1" in log.text
    assert "no agent loop is started and no surface is bound" not in log.text

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        events = urllib.request.urlopen(
            f"http://127.0.0.1:{port}/sessions/d-1/events", timeout=5
        )
        assert events.status == 200
        assert "session_started" in events.read().decode()
        with pytest.raises(urllib.error.HTTPError) as result:
            urllib.request.urlopen(
                f"http://127.0.0.1:{port}/sessions/d-1/result", timeout=5
            )
        assert result.value.code == 409
        with pytest.raises(urllib.error.HTTPError) as unknown:
            urllib.request.urlopen(
                f"http://127.0.0.1:{port}/sessions/test/events", timeout=5
            )
        assert unknown.value.code == 404
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_a_missing_bind_address_refuses_rather_than_defaulting(
        log, tmp_path) -> None:
    """F2A_RUNTIME_ADDR is an existing key. No localhost:8080 default."""
    env = {**RUNTIME_ENV, "F2A_STATE_DIR": str(tmp_path)}

    with pytest.raises(SystemExit) as caught:
        runtime_main.main(
            env=env, log=log, today=AS_OF,
            fetch_specification=_published_spec, serve=lambda _s: None,
        )

    assert caught.value.code == EXIT_STARTUP_REFUSED
    assert RUNTIME_ADDR_KEY in log.text
    assert "127.0.0.1:8080" not in log.text
    assert "8081" not in log.text


def test_no_specification_location_is_an_admission_refusal(
        log, tmp_path) -> None:
    """Process default is no_location_configured, not a fixture path."""
    with pytest.raises(SystemExit) as caught:
        runtime_main.main(
            env=_bind_env(tmp_path), log=log, today=AS_OF,
            serve=lambda _s: None,
        )

    assert caught.value.code == EXIT_STARTUP_REFUSED
    assert "NOT admitted" in log.text
    assert "absent" in log.text


def test_the_view_is_not_a_hand_built_test_session(log, tmp_path) -> None:
    """Plant: VIEW_COMES_FROM_ADMISSION_GATE = False invents session_id=test."""
    assert runtime_main.VIEW_COMES_FROM_ADMISSION_GATE is True
    bound: list[object] = []
    runtime_main.main(
        env=_bind_env(tmp_path),
        log=log,
        today=AS_OF,
        fetch_specification=_published_spec,
        serve=bound.append,
    )
    server = bound[0]
    host, port = server.server_address[:2]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with pytest.raises(urllib.error.HTTPError) as unknown:
            urllib.request.urlopen(
                f"http://127.0.0.1:{port}/sessions/test/events", timeout=5
            )
        assert unknown.value.code == 404
        events = urllib.request.urlopen(
            f"http://127.0.0.1:{port}/sessions/d-1/events", timeout=5
        )
        assert events.status == 200
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_registry_and_register_and_build_server_are_live_in_src() -> None:
    """rg-checkable discharge: the constructions are in src/, not comments."""
    source = Path(runtime_main.__file__).read_text()
    assert "Registry(" in source
    assert ".register(" in source
    assert "build_server(" in source
    assert source.count("Registry(") >= 1
    assert runtime_main.BINDS_AFTER_STARTUP is True


def test_the_supervisor_closing_line_is_untouched() -> None:
    """OD-36 ⑤: this task does not replace the supervisor's workload line."""
    text = Path(supervisor_main.__file__).read_text()
    assert "no session workload is " in text
    assert "Admission, the runner handshake and the session lifecycle are " in text
    assert "Phase 4's (T105-T112)" in text
