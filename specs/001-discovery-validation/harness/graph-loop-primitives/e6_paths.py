"""Scratch paths for the E6 arms.

The recovered probes wrote their SQLite sessions, ledgers, and side-effect logs
to a hardcoded `/tmp/f2a-probe-runtime/`. That directory is still the default, so
a re-run behaves exactly as the original did, but it is now overridable:

    F2A_PROBE_DIR=/somewhere/else ./run.sh

Nothing written here is a credential. These are session databases, invocation
ledgers, and append-only side-effect logs — the programmatic evidence the arms
are adjudicated from.

The side-effect logs in particular must survive `SIGKILL`, which is why the
probes `fsync` them rather than relying on interpreter shutdown.
"""
import os

DEFAULT = "/tmp/f2a-probe-runtime"


def workdir() -> str:
    d = os.environ.get("F2A_PROBE_DIR", DEFAULT)
    os.makedirs(d, exist_ok=True)
    return d


def path(name: str) -> str:
    return os.path.join(workdir(), name)
