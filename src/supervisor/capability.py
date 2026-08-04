"""T107 — FR-050 layer 1: the capability handle is **opaque random bytes**.

Not a claim. Not signed. Nothing offline-verifiable, and deliberately so.

The failure this closes is the one the specification's own checklist points
at: a self-describing credential with an expiry is honoured by anyone who can
verify the signature, for as long as its expiry says, *whether or not anything
is still alive to revoke it*. FR-050's bounded clause requires the authority to
stop being honoured the moment the session reaches a terminal state **including
a terminal state reached by crash**, and a signature survives a crash.

So there is nothing in the handle to look at. The proxy resolves it against the
session table on every request (`capability.go` stage 1), which means there is
no state of the world in which something honours the handle because it examined
the handle.

The type below has no serializer, for the same reason `Secret` does not: the
handle is the sandbox's whole authority, and a code path that logs it hands
that authority to whoever reads the log.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass

from src.contracts.secret import Secret
from src.supervisor.session_table import capability_digest

# 32 bytes of `secrets.token_bytes` entropy, hex-encoded. Not a tuned number:
# it is the width at which guessing is not a considered threat, and the handle
# has no other defence because it has no structure.
HANDLE_BYTES = 32


@dataclass(frozen=True)
class Capability:
    """A session's authority to reach the enforcement point.

    `handle` is a `Secret`, so `str()`, `repr()`, f-strings and every
    serializer yield a redaction marker. `digest` is what goes in the session
    table and is safe to record.
    """

    session_id: str
    handle: Secret
    digest: str

    def header_value(self) -> str:
        """The value the sandbox presents as `X-F2A-Capability`.

        The only call site that takes the handle out. Named so it is greppable.
        """
        return self.handle.reveal()


def issue(session_id: str) -> Capability:
    handle = secrets.token_hex(HANDLE_BYTES)
    return Capability(
        session_id=session_id,
        handle=Secret(handle, name=f"capability:{session_id}"),
        digest=capability_digest(handle),
    )
