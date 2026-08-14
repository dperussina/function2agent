"""The runtime's process entry point — the other half of the T029 seam.

Same anchor as `src/supervisor/main.py` and the same shape:
`src/proxy/main.go:359` constructs its channel, resolves configuration and
refuses before it binds. Read that module's docstring first. The first
deviation from Go recorded there — gathering refusals rather than stopping
at the first — still holds. The second — ending in a report rather than in
a serve loop — is the stance **OD-36** supersedes: after the gates pass,
this process constructs a `Registry`, admits a `SessionView` through
`src.analysis.admission.gate`, and binds via `serving.build_server`.

The supervisor's closing line is a different absence (session workload) and
is not replaced here (OD-36 ⑤).

What this file adds is **the startup gates that only the runtime can run**,
and the answer to the question `tasks.md` left open as the thing a defensible
closure would have to name: *where `require_priceable` runs relative to
`load()`*. T163's `select` runs in the same gathered pass, so the core path
never names a vendor.

## Where `require_priceable` runs, and why there

**Immediately after `load()`, in the same gathered pass as the FR-058 bound, and
before anything that could spend money.** Three properties fix the position:

1. **It cannot run before `load()`.** It is asked about *the model in force*,
   and which model that is comes out of configuration (`MODEL_PROVIDER`,
   `MODEL_ID`, FR-037's *"selected by configuration"*). So it is downstream of
   resolution by construction, not by preference.
2. **It must run before the first call.** That is the whole of `costs.py`'s
   argument for having a preflight at all when the price lookup already
   refuses: *"a deployment configured against an unpriced model starts, accepts
   a session, builds a request, calls a provider — and then refuses, after the
   money for that call has been spent."* Anywhere later and the gate is
   discovered from a bill.
3. **It is gathered with the FR-058 bound rather than sequenced against it.**
   Both depend only on the resolved configuration and neither has a side
   effect, so an operator whose bound is over FR-058's ceiling *and* whose model
   is unpriced learns both at once.

The rate it names is emitted on the readiness report, which is the reason
`require_priceable` returns a line rather than `None`. That matters most for a
declared **zero**: a rate that switches the spend dimension off is a thing to
read before a session runs, not to infer afterwards from a total that never
moved.
"""

from __future__ import annotations

import datetime as dt
import time
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Callable, Mapping

from src.analysis.admission import (
    AdmissionDecision,
    FetchResponse,
    NotAdmitted,
    check,
    gate,
    no_location_configured,
)
from src.contracts.config import (
    RUNTIME_KEYS,
    TOPOLOGY_KEYS,
    Config,
    ConfigError,
    load,
)
from src.contracts.credentials import (
    HOLDER_RUNTIME,
    PLANE_PROVIDER,
    HolderRefusedError,
    PlaneMixError,
    hold,
)
from src.contracts.operator_log import OperatorLog
from src.contracts.secret import Secret
from src.contracts.topology import RUNTIME_ADDR_KEY
from src.runtime.answer import AnswerError, complete_served_run
from src.runtime.events import EventStream
from src.runtime.providers.base import ProviderError
from src.runtime.providers.costs import CostTableError, require_priceable
from src.runtime.providers.select import SelectedProvider, select
from src.runtime.providers.operator_prices import load_operator_prices
from src.runtime.result_bound import BoundConfigError, ResultBound
from src.runtime.serving import Registry, SessionView, SurfaceError, build_server
from src.runtime.session_store import Ceilings, CeilingsError

# ---------------------------------------------------------------------------
# Planted flags. Each one is a removal-proof needle. Flipping it is the
# defect the named T215 test exists to catch. Do not "fix" a proof by
# making the flag unused: the test reads the flag, then the behaviour.
# ---------------------------------------------------------------------------

#: The assembly after the readiness report. False restores the superseded
#: report-and-exit sentence OD-36 replaces.
BINDS_AFTER_STARTUP = True
#: `Registry(` is a live construction, not a comment. False drops it.
REGISTRY_IS_CONSTRUCTED = True
#: `.register(` puts the admitted view in. False drops the call.
REGISTER_IS_CALLED = True
#: `build_server` is called from this process. False skips the bind.
BUILD_SERVER_IS_CALLED = True
#: The view's session identity is the admitted deployment, reached through
#: `gate`. False invents `session_id="test"` — the fixture T215 forbids.
VIEW_COMES_FROM_ADMISSION_GATE = True
#: T214 — the admitted session's answer path runs. False leaves
#: `view.result` as `None` and GET /result as 409.
ANSWER_PATH_RUNS = True

#: The runtime's own store under `F2A_STATE_DIR` — the journal, the ledger and
#: the ceilings. A different file from the supervisor's `sessions.db` because
#: they have different owners: `ownership.py` makes `session` the supervisor's
#: and `session_ceiling` the runtime's, and one file with two writers is the
#: thing that map exists to forbid.
RUNTIME_DB = "runtime.db"


def startup(log: OperatorLog, env: Mapping[str, str] | None = None,
            today: dt.date | None = None) -> tuple[Config, str]:
    """Resolve configuration, then run the gates that depend on it.

    Returns the configuration and the line `require_priceable` produced, or
    refuses through `log` and does not return.

    `today` is a parameter because the rate in force is a function of the date
    and a startup gate that could not be asked about a specific one would be
    testable only on the day its fixture was written.
    """
    try:
        config = load(RUNTIME_KEYS, env=env)
    except ConfigError as exc:
        log.refuse(str(exc))

    day = dt.date.today() if today is None else today
    refusals: list[str] = []
    rate_line = ""
    selected: SelectedProvider | None = None

    # FR-036 — the runtime holds the provider plane and not the target plane.
    # Construction refuses a mix; the value is not interpolated into this
    # report (Secret.__str__ redacts; still do not call .reveal() here).
    try:
        credential = config["F2A_PROVIDER_CREDENTIAL"]
        if not isinstance(credential, Secret):
            raise PlaneMixError(
                "F2A_PROVIDER_CREDENTIAL resolved to a non-Secret; the "
                "provider plane is Kind.SECRET (FR-036)"
            )
        hold(secret=credential, plane=PLANE_PROVIDER, holder=HOLDER_RUNTIME)
    except (PlaneMixError, HolderRefusedError) as exc:
        refusals.append(
            f"the provider credential is not holdable (FR-036): {exc}"
        )

    # FR-037 — selected by configuration, no vendor in the core path. T163
    # is this call. Unknown providers refuse here rather than at the first
    # turn; `require_priceable` then asks about the selected model.
    try:
        selected = select(config)
    except ProviderError as exc:
        refusals.append(
            f"the model provider is not selectable (FR-037): {exc}"
        )

    # OD-27 — the model in force is priced by something an operator can point
    # at, or this process does not start. An unpriced model reaching a session
    # is a spend ceiling compared against nothing.
    try:
        if selected is not None:
            rate_line = require_priceable(
                provider=selected.provider,
                model=selected.model,
                as_of=day,
                operator_prices=load_operator_prices(
                    str(config["MODEL_PRICES_OPERATOR"])
                ),
            )
    # `ValueError` is in the set because a declaration's `declared_on` is
    # parsed by `dt.date.fromisoformat`, which raises it rather than a
    # `CostTableError` — a malformed date in a rate card must refuse startup,
    # not escape as an unhandled traceback.
    except (CostTableError, ProviderError, ValueError) as exc:
        refusals.append(f"the model in force is not priceable (OD-27): {exc}")

    # FR-058 — the per-result bound is required configuration and is refused
    # above one twentieth of the context window. `ResultBound` performs that
    # check in its own constructor, so building one here is the whole gate.
    try:
        ResultBound(
            bound_tokens=int(config["TOOL_RESULT_BOUND_TOKENS"]),
            context_window_tokens=int(config["MODEL_CONTEXT_WINDOW_TOKENS"]),
        )
    except BoundConfigError as exc:
        refusals.append(f"the tool-result bound is not usable (FR-058): {exc}")

    # FR-005 — the four ceilings, refused rather than read as unbounded. They
    # are already resolved by `load()`; this is the second half of the same
    # requirement, which is that the four are a *set* a session can be held to.
    try:
        Ceilings.from_config(config)
    except CeilingsError as exc:
        refusals.append(f"the session ceilings are not usable (FR-005): {exc}")

    if refusals:
        log.refuse("\n\n".join(refusals))
    return config, rate_line


def view_from_admission(
    decision: AdmissionDecision,
    *,
    clock: Callable[[], float],
) -> SessionView:
    """Wrap an admitted decision as a `SessionView`.

    The session identity is the deployment `check` already required
    (FR-035). It is not a string this module invented. A rejected
    decision never reaches here: `gate` is the only caller, and it
    raises `NotAdmitted` rather than calling `start`.
    """
    if not VIEW_COMES_FROM_ADMISSION_GATE:
        stream = EventStream("test", clock=clock)
        stream.start()
        return SessionView(session_id="test", stream=stream)
    session_id = decision.deployment_id
    stream = EventStream(session_id, clock=clock)
    stream.start()
    return SessionView(session_id=session_id, stream=stream)


def _bind_address(env: Mapping[str, str] | None) -> tuple[str, int]:
    """`F2A_RUNTIME_ADDR` as host, port. Existing key; no invented default.

    The key already lives on `TOPOLOGY_KEYS` (FR-034). It is not added to
    `RUNTIME_KEYS`: requiring the analysis and target identities here
    would make this process set values it does not bind. A missing
    runtime address is a loud refusal, not `127.0.0.1:8080`.
    """
    keys = tuple(key for key in TOPOLOGY_KEYS if key.name == RUNTIME_ADDR_KEY)
    config = load(keys, env=env)
    raw = str(config[RUNTIME_ADDR_KEY]).strip()
    host, sep, port_text = raw.rpartition(":")
    if not sep or not host or not port_text:
        raise SurfaceError(
            f"{RUNTIME_ADDR_KEY}={raw!r} is not host:port. FR-034: an "
            "identity, refused rather than defaulted (FR-043)."
        )
    try:
        port = int(port_text)
    except ValueError as exc:
        raise SurfaceError(
            f"{RUNTIME_ADDR_KEY}={raw!r} has a non-integer port"
        ) from exc
    return host, port


def _serve_forever(server: ThreadingHTTPServer) -> None:
    server.serve_forever()


def bind_and_serve(
    config: Config,
    log: OperatorLog,
    *,
    env: Mapping[str, str] | None,
    fetch_specification: Callable[[], FetchResponse] | None,
    clock: Callable[[], float],
    serve: Callable[[ThreadingHTTPServer], None],
) -> int:
    """Admit a session into a `Registry` and bind. OD-36's missing step.

    `fetch_specification` is a seam so a test can supply the published
    specification the analysis admission sequence already knows how to
    classify. The process default is `no_location_configured` — FR-044's
    `ABSENT`, refused rather than a path this module invented. There is
    no specification-location key on `RUNTIME_KEYS`; that absence is a
    residual, not a silent file path.
    """
    try:
        host, port = _bind_address(env)
    except (ConfigError, SurfaceError) as exc:
        log.refuse(f"the bind address is not usable (FR-033, FR-034): {exc}")

    fetch = no_location_configured if fetch_specification is None else fetch_specification
    decision = check(fetch(), deployment_id=str(config["F2A_DEPLOYMENT_ID"]))
    try:
        view = gate(decision, lambda: view_from_admission(decision, clock=clock))
    except NotAdmitted as exc:
        log.refuse(exc.decision.operator_message())

    if not REGISTRY_IS_CONSTRUCTED:
        log.refuse("Registry construction was planted off (T215)")
    registry = Registry()
    if REGISTER_IS_CALLED:
        registry.register(view)
    if ANSWER_PATH_RUNS:
        try:
            complete_served_run(registry, view.session_id)
        except AnswerError as exc:
            log.refuse(
                f"the answered quantity could not become a Result "
                f"(FR-025): {exc}"
            )
    if not BUILD_SERVER_IS_CALLED:
        log.refuse("build_server was planted off (T215)")
    try:
        server = build_server(registry, host=host, port=port)
    except OSError as exc:
        log.refuse(f"the surface could not bind {host}:{port}: {exc}")
    except SurfaceError as exc:
        log.refuse(f"the surface could not bind: {exc}")

    bound_host, bound_port = server.server_address[:2]
    log.say(
        f"surface bound on {bound_host}:{bound_port} for admitted "
        f"session {view.session_id} (FR-033, OD-36)"
    )
    serve(server)
    return 0


def main(env: Mapping[str, str] | None = None,
         log: OperatorLog | None = None,
         today: dt.date | None = None,
         *,
         fetch_specification: Callable[[], FetchResponse] | None = None,
         clock: Callable[[], float] | None = None,
         serve: Callable[[ThreadingHTTPServer], None] | None = None) -> int:
    """Start the runtime, or refuse loudly and start nothing.

    After the gates, this process binds. `serve` defaults to
    `serve_forever`; a test injects a no-op so the bind is observable
    without hanging the suite. An exit 0 after a no-op serve means the
    surface bound, not that a daemon is running. The process entry
    (`python -m src.runtime.main`) does not return after a successful
    bind.
    """
    log = OperatorLog("f2a-runtime") if log is None else log
    log.adopt_thread_exceptions()

    config, rate_line = startup(log, env, today)
    log.say(_ready(config, rate_line))

    if not BINDS_AFTER_STARTUP:
        log.say(
            "startup complete and this process now exits: no agent loop is "
            "started and no surface is bound. `serving.build_server` needs a "
            "registry of live sessions and there is no admission path to fill "
            "one; the loop, the runner and the provider drivers are Phase 3 and "
            "Phase 4 work. An exit 0 here means the startup sequence passed, not "
            "that a runtime is running."
        )
        return 0

    return bind_and_serve(
        config,
        log,
        env=env,
        fetch_specification=fetch_specification,
        clock=time.monotonic if clock is None else clock,
        serve=_serve_forever if serve is None else serve,
    )


def _ready(config: Config, rate_line: str) -> str:
    ceilings = Ceilings.from_config(config)
    state_dir = Path(str(config["F2A_STATE_DIR"]))
    unvalidated = ", ".join(config.unvalidated) or "none"
    return (
        f"runtime started for tenant {config['F2A_TENANT_ID']} "
        f"deployment {config['F2A_DEPLOYMENT_ID']}\n"
        f"  store          {state_dir / RUNTIME_DB}\n"
        f"  model          {rate_line}\n"
        f"  result bound   {config['TOOL_RESULT_BOUND_TOKENS']} tokens of a "
        f"{config['MODEL_CONTEXT_WINDOW_TOKENS']}-token window (FR-058)\n"
        f"  retention      {config['RESULT_RETENTION_MAX_BYTES']} bytes\n"
        f"  ceilings       spend ${ceilings.spend_usd}, "
        f"{ceilings.tokens} tokens, {ceilings.wall_clock_seconds}s, "
        f"{ceilings.turns} turns (FR-005)\n"
        f"  unvalidated    {unvalidated} (FR-043)"
    )


if __name__ == "__main__":  # pragma: no cover - process entry point
    raise SystemExit(main())
