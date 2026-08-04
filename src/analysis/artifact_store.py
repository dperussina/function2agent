"""T019 — the content-addressed `objects/<sha256>` payload store (FR-054).

`Artifact` is immutable; `ArtifactRef` is `(deployment_id, kind) → content_hash`
with history retained. That split is what makes FR-054's rollback a pointer move
rather than a rewrite, and it is the reason the payload store is
content-addressed: two versions of the same artifact coexist, so restoring one
does not have to reconstruct anything.

**Immutability is enforced, not assumed.** `put` on an existing address verifies
the stored bytes match and raises if they do not. A silent overwrite would make
every content address a lie and every rollback a restore-to-whatever-is-there-now.

**Nothing here writes a timestamp into a payload.** The envelope carries them
(FR-055); this store writes exactly the bytes it is handed.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from src.contracts.envelope import Envelope, wrap
from src.contracts.repository import Repository
from src.contracts.schemas import KINDS, require

ARTIFACT_TABLE = "artifact"
REF_TABLE = "artifact_ref"
REF_HISTORY_TABLE = "artifact_ref_history"


class ArtifactStoreError(RuntimeError):
    pass


class ImmutabilityError(ArtifactStoreError):
    """Two different payloads claimed the same content address."""


@dataclass(frozen=True)
class StoredArtifact:
    kind: str
    content_hash: str
    schema_version: str
    produced_by: str


def _hex_of(address: str) -> str:
    if not address.startswith("sha256:"):
        raise ArtifactStoreError(f"{address!r} is not a sha256 content address")
    digest = address.split(":", 1)[1]
    if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        raise ArtifactStoreError(f"{address!r} is not a lowercase sha256 hex digest")
    return digest


class ArtifactStore:
    """Payloads on disk under `objects/`, metadata and refs in the repository."""

    def __init__(self, root: str | Path, repository: Repository) -> None:
        self.root = Path(root)
        self.objects = self.root / "objects"
        self.objects.mkdir(parents=True, exist_ok=True)
        self.repo = repository
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        self.repo.create_table(ARTIFACT_TABLE, {
            "content_hash": "text not null",
            "kind": "text not null",
            "schema_version": "text not null",
            "produced_by": "text not null",
        })
        self.repo.create_table(REF_TABLE, {
            "kind": "text not null",
            "content_hash": "text not null",
        })
        self.repo.create_table(REF_HISTORY_TABLE, {
            "kind": "text not null",
            "content_hash": "text not null",
            "sequence": "int not null",
            "moved_by": "text not null",
            "moved_at": "real not null",
        })

    # -- payloads ----------------------------------------------------------

    def _path_for(self, address: str) -> Path:
        digest = _hex_of(address)
        # Two-character shard, so a directory does not accumulate every object.
        return self.objects / digest[:2] / digest[2:]

    def put(self, envelope: Envelope, *, produced_by: str) -> StoredArtifact:
        """Store the payload bytes and record the artifact. Idempotent."""
        payload = envelope.payload_bytes()
        recomputed = "sha256:" + hashlib.sha256(payload).hexdigest()
        if recomputed != envelope.address:
            raise ImmutabilityError(
                f"the envelope's address {envelope.address} does not match its "
                f"own payload bytes ({recomputed}). Something serialized the "
                "payload twice and got two answers, which is the FR-055 defect."
            )

        target = self._path_for(envelope.address)
        if target.exists():
            existing = target.read_bytes()
            if existing != payload:
                raise ImmutabilityError(
                    f"{envelope.address} already holds different bytes. A "
                    "content address that can hold two payloads makes every "
                    "stored version ambiguous and every rollback a guess."
                )
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            # Write to a temporary file in the same directory and rename, so a
            # crash mid-write leaves no partial object at a valid address.
            handle, temporary = tempfile.mkstemp(dir=str(target.parent))
            try:
                with os.fdopen(handle, "wb") as file:
                    file.write(payload)
                    file.flush()
                    os.fsync(file.fileno())
                os.replace(temporary, target)
            except BaseException:
                Path(temporary).unlink(missing_ok=True)
                raise

        already = self.repo.select(
            ARTIFACT_TABLE, where={"content_hash": envelope.address})
        if not already:
            self.repo.insert(ARTIFACT_TABLE, {
                "content_hash": envelope.address,
                "kind": envelope.kind,
                "schema_version": envelope.schema_version,
                "produced_by": produced_by,
            })
        return StoredArtifact(
            kind=envelope.kind,
            content_hash=envelope.address,
            schema_version=envelope.schema_version,
            produced_by=produced_by,
        )

    def get_bytes(self, address: str) -> bytes:
        target = self._path_for(address)
        if not target.exists():
            raise ArtifactStoreError(f"{address} is not in the object store")
        payload = target.read_bytes()
        recomputed = "sha256:" + hashlib.sha256(payload).hexdigest()
        if recomputed != address:
            raise ImmutabilityError(
                f"{address} holds bytes that hash to {recomputed}. The object "
                "store has been modified underneath the addresses."
            )
        return payload

    def publish(
        self,
        kind: str,
        document: Mapping[str, Any],
        *,
        produced_by: str,
        moved_by: str,
        now: float,
    ) -> StoredArtifact:
        """Wrap, store, and point the ref at it. The ordinary write path."""
        require(kind)
        envelope = wrap(kind, document)
        stored = self.put(envelope, produced_by=produced_by)
        self.set_ref(kind, envelope.address, moved_by=moved_by, now=now)
        return stored

    # -- refs --------------------------------------------------------------

    def current_ref(self, kind: str) -> str | None:
        rows = self.repo.select(REF_TABLE, where={"kind": kind})
        if not rows:
            return None
        if len(rows) > 1:
            raise ArtifactStoreError(
                f"{kind} has {len(rows)} current refs for one deployment; "
                "(deployment_id, kind) is meant to be unique"
            )
        return rows[0]["content_hash"]

    def history(self, kind: str) -> list[dict[str, Any]]:
        """Every ref this kind has held, newest first."""
        return self.repo.select(
            REF_HISTORY_TABLE, where={"kind": kind},
            order_by="sequence", descending=True)

    def set_ref(self, kind: str, address: str, *, moved_by: str, now: float) -> None:
        """Move the ref and append to history in one transaction.

        Not two operations: a move whose history entry failed would make the
        prior version unrecoverable, which is precisely what FR-054's retained
        history exists to prevent.
        """
        if kind not in KINDS:
            raise ArtifactStoreError(f"{kind!r} is not one of FR-054's eight kinds")
        if not self._path_for(address).exists():
            raise ArtifactStoreError(
                f"refusing to point {kind} at {address}, which is not in the "
                "object store. A ref to an absent object is a rollback target "
                "that cannot be restored."
            )

        existing = self.history(kind)
        sequence = (existing[0]["sequence"] + 1) if existing else 0
        current = self.current_ref(kind)

        with self.repo.transaction():
            if current is None:
                self.repo.insert(REF_TABLE, {"kind": kind, "content_hash": address})
            else:
                self.repo.update(
                    REF_TABLE, where={"kind": kind},
                    values={"content_hash": address})
            self.repo.insert(REF_HISTORY_TABLE, {
                "kind": kind,
                "content_hash": address,
                "sequence": sequence,
                "moved_by": moved_by,
                "moved_at": now,
            })

    def previous_ref(self, kind: str) -> str | None:
        """The address immediately before the current one, or None.

        Skips consecutive duplicates: republishing an identical artifact
        appends a history row with the same address, and "the immediately
        prior version" in FR-054 means the prior *version*, not the prior row.
        """
        current = self.current_ref(kind)
        for row in self.history(kind):
            if row["content_hash"] != current:
                return row["content_hash"]
        return None
