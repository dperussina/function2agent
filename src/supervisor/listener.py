"""T109 — FR-050 layer 3: the path is bound to a live process, so the common
crash closes **instantly**.

The sandbox reaches the enforcement point over a per-session listener whose
socket the supervisor holds open **by its own file descriptor**. When the
supervisor process dies the descriptor closes with it and the listener is gone.
The kernel performs the revocation and no cleanup code is involved — which is
the property, and which is why the test kills the holder with `SIGKILL` from a
separate process rather than asking it to shut down.

This is what narrows layer 2's residual window from *every crash* to the
narrower case where the supervisor is alive but the session row was not
updated.

**A Unix domain socket in the session's own directory, not a TCP port.** A
listening TCP port outlives nothing the way a descriptor does — but more
importantly, a port is reachable from anywhere on the host, and FR-050's
bounded clause is about *this session's* authority. A socket file inside the
session's scratch, mounted into only that session's namespace, means a later
session has no path to it at all. That is the second arm of SC-024's replay
fixture: refused by unreachability rather than denied, and recorded only as a
drop counter, because nothing receives the connection.
"""

from __future__ import annotations

import os
import socket
from dataclasses import dataclass
from pathlib import Path

BACKLOG = 64


@dataclass(frozen=True)
class ListenerHandle:
    session_id: str
    socket_path: str
    fileno: int


class SessionListener:
    """One session's path to the enforcement point.

    The object owns the descriptor and nothing else does. There is no
    `atexit`, no `finally` in a caller that the mechanism relies on, and no
    unlink-on-shutdown that has to run for revocation to happen: a stale socket
    *file* with no process behind it refuses connections with `ECONNREFUSED`,
    which is the same refusal.
    """

    def __init__(self, session_id: str, directory: str | Path) -> None:
        self.session_id = session_id
        self.directory = Path(directory)
        self.socket_path = str(self.directory / f"session-{session_id}.sock")
        self._sock: socket.socket | None = None

    def open(self) -> ListenerHandle:
        self.directory.mkdir(parents=True, exist_ok=True)
        # A leftover file from a session that crashed is not a live listener;
        # removing it is housekeeping and never a safety step.
        try:
            os.unlink(self.socket_path)
        except FileNotFoundError:
            pass
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.bind(self.socket_path)
        sock.listen(BACKLOG)
        # 0600: the socket is reachable only by the uid the session runs as,
        # and only from inside the namespace the file is mounted into.
        os.chmod(self.socket_path, 0o600)
        self._sock = sock
        return ListenerHandle(self.session_id, self.socket_path, sock.fileno())

    def accept(self) -> tuple[socket.socket, object]:
        if self._sock is None:
            raise RuntimeError("listener is not open")
        return self._sock.accept()

    def close(self) -> None:
        """Orderly close. Identical in effect to the process dying."""
        if self._sock is not None:
            self._sock.close()
            self._sock = None
        try:
            os.unlink(self.socket_path)
        except FileNotFoundError:
            pass


def is_reachable(socket_path: str, timeout: float = 1.0) -> bool:
    """Can anything still connect? Used by the replay fixture's second arm."""
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect(socket_path)
    except (ConnectionRefusedError, FileNotFoundError, OSError):
        return False
    finally:
        sock.close()
    return True
