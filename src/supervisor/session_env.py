"""T110 — FR-050 layer 4: a fresh container and a fresh scratch volume per
session, both keyed by session id, with a resumed session reattaching **its
own** scratch.

The not-inherited clause is the point. Two sessions never share scratch, so a
credential, a cached token or a half-written artefact from one session is not
sitting in the next session's filesystem. `create()` refuses to reuse an
existing directory rather than emptying it — emptying is a cleanup path, and a
cleanup path that fails leaves inheritance in place while reporting success.

**Resume is not a new session.** FR-007 makes a resumed session the *same*
session, so `attach()` reattaches the same directory under the same id and
`create()` is not called. Finding 006 measured what resume actually has to
survive: state written before a `SIGKILL` from a separate process is the only
state a resumed session can rely on, because no cleanup, flush or shutdown hook
runs. So scratch is on the filesystem, created before the container starts, and
nothing about its existence depends on the previous incarnation having exited
tidily.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

SCRATCH_MODE = 0o700


class SessionEnvError(RuntimeError):
    """The environment is not clean. The session does not start."""


@dataclass(frozen=True)
class SessionEnv:
    session_id: str
    scratch: Path
    socket_dir: Path
    resumed: bool

    def assert_owned_and_private(self) -> None:
        """0700 and owned by us, or the session does not start.

        A scratch directory another uid can read is a credential leak between
        tenants, and checking at start costs nothing.
        """
        st = self.scratch.stat()
        if st.st_uid != os.geteuid():
            raise SessionEnvError(
                f"{self.scratch} is owned by uid {st.st_uid}, not "
                f"{os.geteuid()}; refusing to run a session in a directory "
                "another user controls"
            )
        if st.st_mode & 0o077:
            raise SessionEnvError(
                f"{self.scratch} is mode {st.st_mode & 0o777:o}; FR-050's "
                "not-inherited clause needs 0700"
            )


class SessionEnvironments:
    """Allocates and reattaches per-session environments under one root."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def _paths(self, session_id: str) -> tuple[Path, Path]:
        base = self.root / session_id
        return base / "scratch", base / "run"

    def create(self, session_id: str) -> SessionEnv:
        scratch, socket_dir = self._paths(session_id)
        if scratch.exists():
            raise SessionEnvError(
                f"scratch for session {session_id} already exists at "
                f"{scratch}. A new session never inherits one (FR-050), and "
                "this is not emptied and reused: a cleanup path that fails "
                "leaves the inheritance in place while reporting success. "
                "Use attach() if this is a resume (FR-007)."
            )
        scratch.mkdir(parents=True, mode=SCRATCH_MODE)
        socket_dir.mkdir(parents=True, mode=SCRATCH_MODE, exist_ok=True)
        os.chmod(scratch, SCRATCH_MODE)
        os.chmod(socket_dir, SCRATCH_MODE)
        env = SessionEnv(session_id, scratch, socket_dir, resumed=False)
        env.assert_owned_and_private()
        return env

    def attach(self, session_id: str) -> SessionEnv:
        """FR-007 — a resumed session is the same session, so the same scratch."""
        scratch, socket_dir = self._paths(session_id)
        if not scratch.is_dir():
            raise SessionEnvError(
                f"no scratch for session {session_id} at {scratch}. A resume "
                "reattaches its own scratch; it does not create one, because "
                "creating one silently turns a resume into a fresh session "
                "that claims continuity it does not have (FR-007)."
            )
        socket_dir.mkdir(parents=True, mode=SCRATCH_MODE, exist_ok=True)
        env = SessionEnv(session_id, scratch, socket_dir, resumed=True)
        env.assert_owned_and_private()
        return env

    def destroy(self, session_id: str) -> None:
        """Orderly teardown. **Nothing safety-relevant depends on this running.**

        Isolation comes from `create()` refusing to reuse, not from this having
        been reached. A session whose supervisor was `SIGKILL`ed leaves its
        scratch behind, and the next session — which has a different id —
        cannot see it either way.
        """
        base = self.root / session_id
        shutil.rmtree(base, ignore_errors=True)
