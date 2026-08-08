"""The supervisor's process entry point — the T029 seam recorded at `f167d7e`.

`src/proxy/main.go:359` is the anchor and the shape is deliberately close:
construct the human channel as the first statement, resolve configuration, and
**refuse before anything is opened or bound**. That process existed on the Go
side of the language boundary and had no Python counterpart, so
`config.py::_report` — which assembles *"N required value(s) unset:"* and quotes
each key's `no_default_reason` back — had never run outside a test, for any of
the four authorities that require it (`_NO_DEFAULT_BOUND` FR-049/Q-10,
`_NO_DEFAULT_CEILING` FR-005, and, in `src/runtime/main.py`,
`_NO_DEFAULT_RESULT_BOUND` FR-058 and `_NO_DEFAULT_OPERATOR_PRICES` OD-27).

## Where this deviates from the Go anchor, and why

**Go stops at the first refusal; this gathers every refusal it can take without
side effects.** `LoadConfig` then `BuildProxy` are two `Fatalf`s in sequence, so
an operator whose configuration and whose policy file are both wrong learns
about them one restart apart. That is the exact objection `load()`'s own
docstring raises against reporting one unset key at a time — *"being made to
discover the schema one failure at a time"* — and it does not stop being true
one level up. So the platform check and the configuration resolution both run,
and both reports are emitted before the process exits.

It is not a general principle applied everywhere: a step is gathered only if it
can fail **without having done anything**. Opening the session store is not, so
it happens after, alone, and only if nothing above refused.

On this repository's usual development host the deviation is the difference
between a usable report and none at all: `preflight()` fails on macOS by
design (OD-17, no degraded mode), so a first-refusal-wins order would mean the
configuration report — the twelve-key one this seam exists to make reachable —
could never be seen off a Linux box.

**Go's `main()` ends in `ServeEnforcement`; this one ends in a report and
exits.** There is nothing to serve. Admission, the session workload and the
runner handshake are Phase 4's and are unbuilt, so a supervisor that blocked
here would be a process that looks healthy and is doing nothing, and would be
untestable besides. The last line says so in terms rather than leaving an exit 0
to be read as a running daemon. When the workload lands, it replaces that line;
nothing else in this sequence changes.

## What opening the store settles

**OD-28** deferred the `SessionTable` → `Repository` migration on a ground that
expired *"the moment a supervisor process constructs a `SessionTable` against a
store that may be cold"*. This is that process. The migration landed first, at
`551e6ff`, so the cold-start WAL race is closed rather than made live — measured
either side at four processes meeting a barrier over twelve trials of four cold
first-opens: 8 of 12 trials with a loser before, **0 of 12** after. Opening here
is safe because that work was done, not because this file is careful.
"""

from __future__ import annotations

from pathlib import Path
from typing import Mapping

from src.contracts.config import SUPERVISOR_KEYS, Config, ConfigError, load
from src.contracts.operator_log import OperatorLog
from src.supervisor.preflight import PreflightError, preflight
from src.supervisor.session_table import SessionTable

#: The session table's filename under `F2A_STATE_DIR`. The supervisor writes it
#: and the enforcement point opens the same file read-only through its own
#: `F2A_PROXY_SESSION_DB`; the two are wired by an operator and this constant is
#: what the readiness report names so the wiring is readable rather than
#: guessed.
SESSION_DB = "sessions.db"


def startup(log: OperatorLog, env: Mapping[str, str] | None = None) -> Config:
    """Every refusal that costs nothing to discover, discovered together.

    Returns the resolved configuration, or refuses through `log` and does not
    return. Nothing here has opened a file, bound a socket or created a
    directory, which is what makes gathering the two safe.
    """
    refusals: list[str] = []
    config: Config | None = None

    try:
        preflight()
    except PreflightError as exc:
        refusals.append(str(exc))

    try:
        config = load(SUPERVISOR_KEYS, env=env)
    except ConfigError as exc:
        refusals.append(str(exc))

    if refusals or config is None:
        log.refuse("\n\n".join(refusals))
    return config


def main(env: Mapping[str, str] | None = None,
         log: OperatorLog | None = None) -> int:
    """Start the supervisor, or refuse loudly and start nothing.

    `env` and `log` are parameters rather than reads of process state so the
    whole sequence is exercisable in a test **by content** — an assertion that
    merely observes a `SystemExit` cannot tell a missing ceiling from a syntax
    error, and this repository has ten recorded instances of exactly that.
    """
    log = OperatorLog("f2a-supervisor") if log is None else log
    # Every daemon thread this process starts — the lease renewer above all —
    # reports through the same channel from here on. See
    # `OperatorLog.adopt_thread_exceptions`: the stock hook writes to a
    # buffered stream and takes the process down with SIGABRT in 7 of 120
    # forced-overlap trials, and this one in 0 of 120.
    log.adopt_thread_exceptions()

    config = startup(log, env)

    state_dir = Path(str(config["F2A_STATE_DIR"]))
    session_db = state_dir / SESSION_DB
    # Opened, not merely named. OD-28's ground ① was that no supervisor
    # process constructs a `SessionTable` against a store that may be cold, and
    # a readiness report that printed the path without opening the file would
    # leave that ground exactly where it was while reading as though it had
    # moved.
    with SessionTable(session_db) as sessions:
        log.say(_ready(config, sessions.path))

    log.say(
        "startup complete and this process now exits: no session workload is "
        "built. Admission, the runner handshake and the session lifecycle are "
        "Phase 4's (T105-T112) and this entry point starts none of them. An "
        "exit 0 here means the startup sequence passed, not that a supervisor "
        "is running."
    )
    return 0


def _ready(config: Config, session_db: Path) -> str:
    """What was resolved, named so an operator can check the wiring.

    Modelled on the Go anchor's one `Printf`, which names the listen address,
    the pinned upstream and the policy version — the settings a
    misconfiguration would show up in. The FR-043 markings are listed because
    `Config.is_unvalidated` exists to be answerable *by every surface that
    emits the value*, and a readiness line is one.
    """
    unvalidated = ", ".join(config.unvalidated) or "none"
    return (
        f"supervisor started for tenant {config['F2A_TENANT_ID']} "
        f"deployment {config['F2A_DEPLOYMENT_ID']}\n"
        f"  session table  {session_db}\n"
        f"  location set   {config['F2A_LOCATION_SET']}\n"
        f"  memory.max     {config['SANDBOX_MEMORY_MAX']} bytes\n"
        f"  cpu.max        {config['SANDBOX_CPU_MAX']}\n"
        f"  cpu total      {config['SANDBOX_CPU_TOTAL']} CPU-seconds\n"
        f"  pids.max       {config['SANDBOX_PIDS_MAX']}\n"
        f"  unvalidated    {unvalidated} (FR-043)"
    )


if __name__ == "__main__":  # pragma: no cover - process entry point
    raise SystemExit(main())
