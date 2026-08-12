"""T136 — a `codegraph` schema-hash mismatch fails the analysis stage. It is never drift.

**Requirement**: **U-04** — *a changed upstream schema must never be read as
changed source.*

## The two conclusions this separates, because they come from one symptom

`codegraph`'s SQLite schema carries no stability guarantee across releases, and
**D-14** has us reading that artifact directly. So an upstream column rename
arrives as *changed rows in a table we query*, with nothing announcing it. The
derived source artifact then hashes differently, and FR-028 reads a changed
content address on a source-derived artifact as **source drift**.

Two readings of the same symptom, and they point at opposite owners:

| reading | what it says | who acts |
| --- | --- | --- |
| upstream schema change | *the tool we consume moved* | us — bump the pin, the digest and the fixture together |
| FR-028 drift signal | *the code under analysis moved away from its documentation* | the target's owner |

Emitting the second when the first is true tells an operator their code drifted
on a day they did not touch it. That is the failure this file exists to prevent.

## Why this is a contract test and not a duplicate of the unit tests

`tests/unit/test_codegraph_pin.py` covers the pin as a **function**: the digest
is a property of the schema and not of the rows, `verify()` fails closed, the
constant re-derives from upstream's committed DDL. `tests/unit/
test_codegraph_invocation.py` covers T119's ordering — the pin is asserted
before an index is handed back.

What is owed here is neither. It is the statement about the **stage**: run the
analysis stage over an artifact whose schema is not the pinned one, and observe
that (a) the stage stops, (b) what it says is *upstream schema change*, and
(c) **no source-derived artifact is published**, so the drift channel — which
FR-028 defines over the content addresses of exactly those artifacts — has
nothing new to read and cannot raise a signal from this event.

## What (c) does and does not establish, stated because it is the load-bearing arm

`src/runtime/drift/` is an empty package at this revision: the drift *detector*
does not exist yet, so no test can watch it stay quiet. What is checkable today
is the thing the detector would read. FR-028's input is a changed content
address on a `source_derived` artifact kind, and `src/contracts/schemas.py`
enumerates which kinds those are. A stage that publishes none of them has
produced no input for the detector, whenever it lands.

So this is a statement about the stage's output, not an observation of a silent
detector. The distinction matters and the arm is named for it.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from src.analysis import codegraph
from src.analysis.artifact_store import ArtifactStore
from src.analysis.codegraph_pin import CodegraphPinError
from src.contracts import schemas
from src.contracts.repository import Repository

REPO = Path(__file__).resolve().parent.parent.parent
SCHEMA_SQL = REPO / "tests" / "fixtures" / "codegraph-schema" / "schema.sql"

SOURCE_DERIVED_KINDS = tuple(
    sorted(s.kind for s in schemas.SCHEMAS if s.source_derived)
)


def _pinned_schema_db(directory: Path) -> Path:
    """A zero-row database at the pinned revision's schema — the matching case."""
    db = directory / ".codegraph" / "codegraph.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db)
    try:
        conn.executescript(SCHEMA_SQL.read_text())
        conn.commit()
    finally:
        conn.close()
    return db


def _upstream_renamed_a_column(directory: Path) -> Path:
    """The mismatching case, built as the real event rather than as noise.

    The whole committed DDL is applied and then **one column is renamed**, which
    is what an upstream release looks like from here. A database with two
    invented tables would also mismatch, and would let this file pass against a
    stage that only rejects nonsense.
    """
    db = _pinned_schema_db(directory)
    conn = sqlite3.connect(db)
    try:
        conn.execute("ALTER TABLE nodes RENAME COLUMN name TO symbol_name")
        conn.commit()
    finally:
        conn.close()
    return db


class _Runner:
    def __init__(self, produce):
        self.produce = produce

    def __call__(self, invocation):
        self.produce(Path(invocation.cwd))
        return codegraph.CompletedInvocation(returncode=0, stdout="", stderr="")


@pytest.fixture()
def store(tmp_path):
    repository = Repository(
        tmp_path / "meta.sqlite3",
        role="analysis",
        tenant_id="t-1",
        deployment_id="d-1",
    )
    yield ArtifactStore(tmp_path / "store", repository)
    repository.close()


# A minimal valid `derived_contract` document. Its content does not matter here
# — what matters is that publishing it moves a source-derived content address,
# which is precisely the event FR-028 reads.
_CONTRACT_DOCUMENT = {
    "schema_version": schemas.DERIVED_CONTRACT.version,
    "deployment_id": "d-1",
    "operation_id": "GET /parts/{part_id}",
    "reads": ["parts"],
    "writes": [],
    "preconditions": [],
    "postconditions": [],
    "failure_taxonomy": [],
    # Required at 1.1.0 under OD-32, and its content still does not matter here.
    "provenance": {
        "derivation_rule": "raises_statement",
        "source_symbol": "get_part",
        "source_file": "parts.py",
        "analyzer_version": "0.1.0",
        "content_hash": "sha256:" + "c" * 64,
        "validation_status": "provisional",
        "validated_against": None,
    },
}


def _run_analysis_stage(repo_root: Path, produce, store: ArtifactStore):
    """Index, then publish — the stage's shape, so the refusal has a place to be.

    The publish is deliberately downstream of the index. If the pin were
    asserted anywhere later than it is, this call would be reached and the arm
    below would see a moved source-derived content address.
    """
    index = codegraph.index_repository(repo_root, runner=_Runner(produce))
    store.publish(
        "derived_contract",
        _CONTRACT_DOCUMENT,
        produced_by="analysis-stage",
        moved_by="analysis-stage",
        now=1.0,
    )
    return index


# ---------------------------------------------------------------------------
# (a) the stage stops


def test_a_schema_mismatch_fails_the_analysis_stage(tmp_path, store) -> None:
    with pytest.raises(CodegraphPinError):
        _run_analysis_stage(tmp_path, _upstream_renamed_a_column, store)


def test_the_matching_schema_lets_the_stage_proceed(tmp_path, store) -> None:
    """The positive control, and without it every arm here passes on a stage
    that refuses everything."""
    index = _run_analysis_stage(tmp_path, _pinned_schema_db, store)
    assert index.digest.digest == codegraph.pin.CODEGRAPH_SCHEMA_SHA256
    assert store.current_ref("derived_contract") is not None, (
        "the control must actually reach the publish, or the arm below is "
        "asserting that an unreachable line was not reached"
    )


# ---------------------------------------------------------------------------
# (b) what it says


def test_the_refusal_is_surfaced_as_an_upstream_schema_change(tmp_path, store) -> None:
    with pytest.raises(CodegraphPinError) as excinfo:
        _run_analysis_stage(tmp_path, _upstream_renamed_a_column, store)

    message = str(excinfo.value)
    assert "upstream schema change" in message.lower(), (
        "an operator reading this must be sent to the pin, not to their own "
        f"repository. Message was:\n{message}"
    )
    assert codegraph.pin.CODEGRAPH_VERSION in message, (
        "the message names the pinned revision, because bumping it is the fix"
    )
    assert codegraph.pin.CODEGRAPH_SCHEMA_SHA256 in message


def test_the_refusal_never_reads_as_source_drift(tmp_path, store) -> None:
    """Every occurrence of the drift vocabulary is a negation.

    A message that said *schema drift detected* would be technically true and
    operationally the wrong instruction: it is the word the drift channel uses.
    """
    with pytest.raises(CodegraphPinError) as excinfo:
        _run_analysis_stage(tmp_path, _upstream_renamed_a_column, store)

    lowered = str(excinfo.value).lower()
    for sentence in lowered.replace("\n", " ").split("."):
        if "drift" not in sentence:
            continue
        assert "not source drift" in sentence or "never" in sentence, (
            "a sentence mentioning drift that does not negate it will be read "
            f"as a drift report: {sentence.strip()!r}"
        )


# ---------------------------------------------------------------------------
# (c) nothing the drift channel reads is produced


def test_a_mismatch_publishes_no_source_derived_artifact(tmp_path, store) -> None:
    before = {k: store.current_ref(k) for k in SOURCE_DERIVED_KINDS}
    assert set(before.values()) == {None}, "the store starts with no refs"

    with pytest.raises(CodegraphPinError):
        _run_analysis_stage(tmp_path, _upstream_renamed_a_column, store)

    after = {k: store.current_ref(k) for k in SOURCE_DERIVED_KINDS}
    assert after == before, (
        "U-04: a mismatch moved a source-derived content address. FR-028 reads "
        f"exactly that as source drift. Moved: "
        f"{ {k: v for k, v in after.items() if before[k] != v} }"
    )


def test_the_kinds_this_arm_watches_are_the_ones_fr_028_reads() -> None:
    """Pinned, so a new source-derived kind cannot slip past the arm above.

    The list is read off the registry rather than typed out; this asserts the
    registry still says what the arm assumes it says.
    """
    assert SOURCE_DERIVED_KINDS == (
        "derived_check",
        "derived_contract",
        "served_operation_set",
    ), (
        "the source-derived kind set moved. The arm above watches whatever the "
        "registry declares, so it is still correct — but a new kind deserves a "
        "deliberate look before this line is updated."
    )


def test_the_pin_error_is_not_catchable_as_a_storage_or_schema_error() -> None:
    """Type-level separation, so no downstream handler can re-label the event."""
    from src.analysis.artifact_store import ArtifactStoreError

    assert not issubclass(CodegraphPinError, ArtifactStoreError)
    assert not issubclass(CodegraphPinError, schemas.SchemaError)
    assert not issubclass(CodegraphPinError, codegraph.CodegraphInvocationError), (
        "an upstream release and a failed subprocess are different events with "
        "different fixes, and a caller must be able to tell them apart"
    )
