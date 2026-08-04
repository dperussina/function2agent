"""T021 / SC-028 — one operator action, zero hand-edits, zero restarts.

SC-028's clauses, each asserted separately below, plus the one that makes the
capability real: **the restored deployment produces the artifact hashes it
produced before.** A rollback that restores a pointer to bytes that no longer
hash the same has restored nothing.
"""

from __future__ import annotations

import pytest

from src.analysis.artifact_store import ArtifactStore, ImmutabilityError
from src.analysis.rollback import RESTORATION_TABLE, RollbackError, ensure_schema, restore_previous, restorations
from src.contracts.repository import Repository

KIND = "egress_policy"

V1 = {
    "schema_version": "1.0.0",
    "deployment_id": "d-1",
    "allowed_methods": ["GET"],
    "allowed_paths": ["/orders"],
    "deny_rules": [],
    "published_at": "2026-08-03T10:00:00Z",
}
V2 = {**V1, "allowed_methods": ["GET", "HEAD"], "published_at": "2026-08-03T11:00:00Z"}
V3 = {**V1, "allowed_methods": ["GET", "HEAD", "OPTIONS"]}


@pytest.fixture()
def store(tmp_path):
    repo = Repository(
        tmp_path / "store.sqlite3", role="analysis",
        tenant_id="t-1", deployment_id="d-1")
    ensure_schema(repo)
    yield ArtifactStore(tmp_path / "artifacts", repo)
    repo.close()


def _publish(store: ArtifactStore, document, at: float) -> str:
    stored = store.publish(
        KIND, document, produced_by="test@1.0.0", moved_by="analysis", now=at)
    return stored.content_hash


def test_restoring_is_one_call_with_no_way_to_hand_edit(store) -> None:
    """SC-028's 'zero hand-edits', asserted against the signature.

    `restore_previous` takes a kind, an operator and a clock. There is no
    parameter through which an entry could be supplied, so hand-editing is not
    a discouraged path — it is an absent one.
    """
    import inspect

    parameters = set(inspect.signature(restore_previous).parameters)
    assert parameters == {"store", "kind", "operator", "now"}, (
        f"restore_previous grew parameters {parameters}. If one of them can "
        "carry artifact content, FR-054's 'no hand-editing of individual "
        "entries' is no longer structural."
    )


def test_the_prior_version_is_restored_and_the_hashes_match(store) -> None:
    first = _publish(store, V1, 100.0)
    second = _publish(store, V2, 200.0)
    assert store.current_ref(KIND) == second
    assert first != second

    record = restore_previous(store, KIND, operator="ops@example", now=300.0)

    assert store.current_ref(KIND) == first, "the ref did not move back"
    assert record.restored_from == second
    assert record.restored_to == first

    # SC-028's load-bearing clause: the restored deployment produces the
    # hashes it produced before. Re-deriving V1 must land on the same address.
    from src.contracts.envelope import wrap
    assert wrap(KIND, V1).address == first, (
        "re-deriving the restored artifact produced a different address; the "
        "restoration restored a pointer to something unreproducible"
    )
    assert store.get_bytes(first) == wrap(KIND, V1).payload_bytes()


def test_the_restoration_names_the_operator_and_both_versions(store) -> None:
    """FR-054: recorded exactly as a widening is under FR-019."""
    first = _publish(store, V1, 100.0)
    second = _publish(store, V2, 200.0)
    restore_previous(store, KIND, operator="ops@example", now=300.0)

    rows = restorations(store.repo, KIND)
    assert len(rows) == 1
    row = rows[0]
    assert row["operator"] == "ops@example"
    assert row["restored_from"] == second
    assert row["restored_to"] == first
    assert row["artifact_kind"] == KIND
    assert row["tenant_id"] == "t-1" and row["deployment_id"] == "d-1"


def test_an_unattributed_restoration_is_refused(store) -> None:
    _publish(store, V1, 100.0)
    _publish(store, V2, 200.0)
    with pytest.raises(RollbackError, match="name the operator"):
        restore_previous(store, KIND, operator="", now=300.0)
    # And nothing moved.
    assert restorations(store.repo, KIND) == []


def test_a_reader_opened_before_the_move_sees_the_new_ref(store, tmp_path) -> None:
    """SC-028's 'zero runtime restarts'.

    The reader below is opened before the rollback and never reopened. If the
    ref were cached anywhere, or if restoring required a reload, this reads the
    stale address.
    """
    first = _publish(store, V1, 100.0)
    second = _publish(store, V2, 200.0)

    reader = Repository(
        tmp_path / "store.sqlite3", role="runtime",
        tenant_id="t-1", deployment_id="d-1")
    try:
        before = reader.select("artifact_ref", where={"kind": KIND})
        assert before[0]["content_hash"] == second

        restore_previous(store, KIND, operator="ops@example", now=300.0)

        after = reader.select("artifact_ref", where={"kind": KIND})
        assert after[0]["content_hash"] == first, (
            "a reader that was already running did not observe the moved ref; "
            "restoring would require a restart"
        )
    finally:
        reader.close()


def test_rolling_back_twice_returns_to_where_it_started(store) -> None:
    """FR-054 read literally, and the consequence recorded rather than fixed.

    FR-054 asks for "the immediately prior version". After a rollback from v3
    to v2, the immediately prior version IS v3 — that is where the ref just
    came from — so a second rollback returns to v3 and the pair is a toggle,
    not a walk backwards through publications.

    This is asserted rather than silently accepted because it is a real
    ambiguity in the requirement and an operator could reasonably expect
    either. Implementing the walk would mean distinguishing publications from
    restorations in the history and reading "prior version" as "prior
    *published* version", which FR-054 does not say. The literal reading is
    implemented; the question is in the report.
    """
    first = _publish(store, V1, 100.0)
    second = _publish(store, V2, 200.0)
    third = _publish(store, V3, 300.0)
    assert len({first, second, third}) == 3

    restore_previous(store, KIND, operator="ops", now=400.0)
    assert store.current_ref(KIND) == second

    restore_previous(store, KIND, operator="ops", now=500.0)
    assert store.current_ref(KIND) == third, (
        "the second rollback did not return to the version the first one left. "
        "If the walk-backwards reading was adopted, this test records the "
        "change of behaviour and FR-054's wording needs to say so."
    )
    assert len(restorations(store.repo, KIND)) == 2

    # Both restorations are attributable, whichever reading holds.
    assert [r["restored_to"] for r in restorations(store.repo, KIND)] == [second, third]


def test_a_kind_with_one_version_cannot_be_rolled_back(store) -> None:
    """Refused rather than silently no-op.

    A no-op would tell an operator the restore succeeded while leaving the
    configuration they were trying to leave in force.
    """
    _publish(store, V1, 100.0)
    with pytest.raises(RollbackError, match="only ever held one version"):
        restore_previous(store, KIND, operator="ops", now=200.0)


def test_republishing_identical_content_is_not_a_new_version(store) -> None:
    """'The immediately prior version' means version, not history row."""
    first = _publish(store, V1, 100.0)
    second = _publish(store, V2, 200.0)
    again = _publish(store, V2, 250.0)
    assert again == second

    restore_previous(store, KIND, operator="ops", now=300.0)
    assert store.current_ref(KIND) == first, (
        "rolling back landed on the same content it started from; a duplicate "
        "history row was treated as a version"
    )


def test_the_object_store_refuses_to_overwrite_an_address(store) -> None:
    """Immutability, because rollback restores a pointer and nothing else."""
    from src.contracts.envelope import wrap

    envelope = wrap(KIND, V1)
    store.put(envelope, produced_by="test@1.0.0")
    path = store._path_for(envelope.address)
    path.write_bytes(b'{"tampered":true}\n')

    with pytest.raises(ImmutabilityError):
        store.get_bytes(envelope.address)
    with pytest.raises(ImmutabilityError):
        store.put(envelope, produced_by="test@1.0.0")


def test_a_ref_cannot_point_at_an_absent_object(store) -> None:
    with pytest.raises(Exception, match="not in the object store"):
        store.set_ref(KIND, "sha256:" + "0" * 64, moved_by="ops", now=1.0)


def test_the_restoration_table_is_written_by_analysis_only(store, tmp_path) -> None:
    """T017's ownership map, at the one table this module writes."""
    from src.contracts.ownership import OwnershipError

    runtime = Repository(
        tmp_path / "store.sqlite3", role="runtime",
        tenant_id="t-1", deployment_id="d-1")
    try:
        with pytest.raises(OwnershipError):
            runtime.insert(RESTORATION_TABLE, {
                "artifact_kind": KIND, "operator": "someone",
                "restored_from": "a", "restored_to": "b", "at": 1.0})
    finally:
        runtime.close()
