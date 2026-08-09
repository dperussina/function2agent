"""T077 — the served-operation set (FR-002, **OD-06**).

Three properties T077 names, and one the layering decision underneath it names:

1. the set carries **deployment identity**;
2. it carries **its own version**, distinct from the schema version and from
   the artifact's content address;
3. it carries **its freshness**, and freshness means one thing;
4. it is produced by a stage **above source analysis**, which is OD-06's whole
   content and is asserted structurally rather than described.

## Why the version arms are about what does *not* move it

A version field is trivially satisfiable: any constant satisfies "carries its
own version", and any hash of the whole document satisfies "changes when the
document changes". Neither is what FR-028 needs. So the arms here are mostly
**negative controls on the version**: fetching from a different URL, at a
different time, under a different schema version, or on a different host must
all leave `set_version` unmoved, and changing any field of any operation must
move it. That converts "there is a version" into "this version reads the
deployment clock and nothing else".

## Why the freshness arms are about what it does not mean

`captured_at` cannot be tested for *correctness* — nothing here knows when the
deployment changed, which is O-04's whole point. What can be tested is that the
field is not quietly load-bearing for something it cannot support, and that the
one question it does answer (FR-047's *have we looked recently enough*) is
answered from it and from nothing else.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from src.analysis import served_operations as so
from src.analysis.admission import (
    ABSENT,
    PUBLISHED_NON_EMPTY,
    AdmissionDecision,
    criterion_for,
)
from src.analysis.served_operations import (
    ServedOperation,
    ServedOperationSet,
    ServedOperationSetError,
    NotAdmittedForCapture,
    set_version_of,
)
from src.contracts import envelope, migrations
from src.contracts.schemas import SERVED_OPERATION_SET

REPO = Path(__file__).resolve().parents[2]

#: A capture instant used throughout. Fixed rather than `time.time()`: an age
#: assertion against a moving clock is an assertion that arithmetic works.
CAPTURED_AT = "2026-08-08T00:00:00Z"
CAPTURED_EPOCH = 1786147200.0

OPERATIONS = (
    {"operation_id": "list_parts", "method": "GET", "path_template": "/parts",
     "effect_tier": "read_only"},
    {"operation_id": "get_part", "method": "GET",
     "path_template": "/parts/{part_id}", "effect_tier": "read_only"},
)


def _decision(
    *,
    deployment_id: str = "d-reference-app",
    state: str = PUBLISHED_NON_EMPTY,
    operations: tuple = OPERATIONS,
    source: str = "https://target.example.test/served-operations",
) -> AdmissionDecision:
    return AdmissionDecision(
        deployment_id=deployment_id,
        admitted=state == PUBLISHED_NON_EMPTY,
        state=state,
        criterion=criterion_for(state),
        operations=operations if state == PUBLISHED_NON_EMPTY else (),
        evidence="status 200",
        specification_source=source,
    )


def _set(**kwargs) -> ServedOperationSet:
    return ServedOperationSet.from_admission(
        _decision(**kwargs), captured_at=CAPTURED_AT)


# ---------------------------------------------------------------------------
# 1. Deployment identity.


def test_the_set_carries_the_deployment_identity_of_the_decision_it_came_from():
    """FR-002's *"MUST record the deployment identity it describes"*."""
    built = _set(deployment_id="d-seven")
    assert built.deployment_id == "d-seven"
    assert built.document()["deployment_id"] == "d-seven"


def test_the_identity_cannot_be_supplied_separately_from_the_decision():
    """One fact, one source.

    `from_admission` takes no `deployment_id`. If it did, a caller could build
    a set that claims to describe one deployment out of another's
    specification, and nothing downstream could tell.
    """
    import inspect

    parameters = inspect.signature(ServedOperationSet.from_admission).parameters
    assert "deployment_id" not in parameters, (
        "from_admission has acquired a deployment_id parameter. The identity "
        "is on the decision; a second way to state it is a second fact, and "
        "the day the two disagree the artifact says it describes one "
        "deployment while having been built from another's specification."
    )


def test_a_set_with_no_deployment_identity_is_refused():
    with pytest.raises(ServedOperationSetError, match="deployment identity"):
        ServedOperationSet(
            deployment_id="",
            operations=(ServedOperation.from_entry(OPERATIONS[0], index=0),),
            captured_at=CAPTURED_AT,
            source_url="",
        )


# ---------------------------------------------------------------------------
# 2. Its own version.


def test_the_set_carries_a_version_of_its_own():
    built = _set()
    assert built.set_version.startswith("sha256:")
    assert built.document()["set_version"] == built.set_version


def test_the_set_version_is_not_the_schema_version():
    """Two words everywhere (`src/contracts/schemas.py`)."""
    built = _set()
    assert built.set_version != so.SCHEMA_VERSION
    assert built.document()["schema_version"] == so.SCHEMA_VERSION


@pytest.mark.parametrize(
    "label,build",
    [
        ("a different source url",
         lambda: _set(source="https://elsewhere.example.test/spec")),
        ("a different capture time",
         lambda: ServedOperationSet.from_admission(
             _decision(), captured_at="2019-01-01T00:00:00Z")),
    ],
    ids=["source-url", "capture-time"],
)
def test_the_set_version_does_not_move_for_anything_but_the_operations(
    label: str, build
) -> None:
    """The negative controls that make the version a clock reading.

    A version that moved with the URL we happened to fetch from, or with when
    we happened to look, would report the deployment as having changed every
    time this system was reconfigured or rerun. That is FR-055's false-alarm
    failure one level up, and it is the specific defect this field is shaped
    to avoid.
    """
    assert build().set_version == _set().set_version, (
        f"{label} moved the set version. The deployment clock's reading is "
        "over the served surface and nothing else."
    )


def test_the_set_version_does_not_move_when_our_own_schema_version_moves():
    """The one the content address cannot give, and the reason this field exists.

    The artifact's content address is over a payload that includes
    `schema_version`, so it moves when **we** release. `set_version` must not:
    a schema release of ours is not the deployment clock ticking.
    """
    from src.contracts.canonical import content_address

    document = _set().document()
    # The hashed payload, split exactly as `envelope.wrap` splits it. The
    # address is computed here rather than through `wrap` because `wrap`
    # validates against the registry, and the whole arm is about a schema
    # version the registry does not hold yet.
    hashed_now = {k: v for k, v in document.items()
                  if k not in SERVED_OPERATION_SET.volatile}
    hashed_future = {**hashed_now, "schema_version": "9.9.9"}

    assert content_address(hashed_now) == \
        envelope.wrap("served_operation_set", document).address, (
        "this arm is not splitting the document the way the envelope does, so "
        "the comparison below is against something that is not the artifact's "
        "address"
    )
    assert content_address(hashed_future) != content_address(hashed_now), (
        "the content address is insensitive to the schema version, so the "
        "argument for a separate set_version does not hold and this arm is "
        "asserting nothing"
    )
    assert set_version_of(hashed_future["operations"]) == \
        set_version_of(hashed_now["operations"]), (
        "set_version moved with our own schema version, so a schema release "
        "of ours reads as the deployment clock ticking"
    )


@pytest.mark.parametrize(
    "label,mutate",
    [
        ("an operation added",
         lambda ops: ops + ({"operation_id": "new", "method": "GET",
                             "path_template": "/new"},)),
        ("an operation removed", lambda ops: ops[:1]),
        ("a path template changed",
         lambda ops: ({**ops[0], "path_template": "/parts/v2"}, ops[1])),
        ("a method changed", lambda ops: ({**ops[0], "method": "HEAD"}, ops[1])),
        ("a declared field changed",
         lambda ops: ({**ops[0], "effect_tier": "write"}, ops[1])),
        ("the order changed", lambda ops: (ops[1], ops[0])),
    ],
    ids=["added", "removed", "path", "method", "declared-field", "order"],
)
def test_the_set_version_moves_for_any_change_to_the_served_surface(
    label: str, mutate
) -> None:
    """The positive half. Six mutations, each a real deployment-clock movement."""
    assert _set(operations=mutate(OPERATIONS)).set_version != _set().set_version, (
        f"{label} left the set version unchanged, so the deployment clock "
        "does not read it"
    )


def test_a_set_version_the_target_published_is_not_believed():
    """A version asserted by the subject of the measurement is not a measurement.

    A target that published its own `set_version` and never moved it would
    hold this system's deployment clock still. The value is recomputed, and
    the published one never reaches the artifact.
    """
    published = {**OPERATIONS[0], "set_version": "sha256:" + "0" * 64}
    built = _set(operations=(published, OPERATIONS[1]))
    assert built.set_version != "sha256:" + "0" * 64


def test_a_stored_set_version_that_disagrees_with_its_operations_is_refused():
    document = _set().document()
    document["set_version"] = "sha256:" + "f" * 64
    with pytest.raises(ServedOperationSetError, match="disagrees with itself"):
        ServedOperationSet.from_document(document)


# ---------------------------------------------------------------------------
# 3. Freshness.


def test_the_set_carries_when_it_was_captured():
    built = _set()
    assert built.captured_at == CAPTURED_AT
    assert built.document()["captured_at"] == CAPTURED_AT


def test_the_age_is_measured_from_the_capture_instant():
    assert _set().age_seconds(CAPTURED_EPOCH + 300.0) == pytest.approx(300.0)


def test_a_capture_stamped_in_the_future_reports_a_negative_age():
    """Not clamped. See `age_seconds`.

    Clamping would present the set as fresh on precisely the evidence that its
    timestamp cannot be trusted.
    """
    assert _set().age_seconds(CAPTURED_EPOCH - 60.0) == pytest.approx(-60.0)


@pytest.mark.parametrize(
    "age,ceiling,stale",
    [(0.0, 3600.0, False), (3599.0, 3600.0, False),
     (3600.0, 3600.0, False), (3601.0, 3600.0, True)],
    ids=["fresh", "just-inside", "exactly-at", "past"],
)
def test_staleness_is_decided_at_the_ceiling(age, ceiling, stale) -> None:
    assert _set().is_stale(CAPTURED_EPOCH + age, ceiling) is stale


def test_a_negative_ceiling_is_refused_rather_than_making_everything_stale():
    """A ceiling that refuses everything looks exactly like a working ceiling."""
    with pytest.raises(ServedOperationSetError, match="not a duration"):
        _set().is_stale(CAPTURED_EPOCH, -1.0)


def test_a_set_with_no_capture_time_is_refused():
    with pytest.raises(ServedOperationSetError, match="when it was captured"):
        ServedOperationSet(
            deployment_id="d-1",
            operations=(ServedOperation.from_entry(OPERATIONS[0], index=0),),
            captured_at="",
            source_url="",
        )


@pytest.mark.parametrize(
    "value",
    ["yesterday", "2026-08-08", "2026-08-08T00:00:00"],
    ids=["prose", "date-only", "no-timezone"],
)
def test_an_uncomputable_capture_time_refuses_rather_than_returning_a_sentinel(
    value: str,
) -> None:
    """A sentinel age would flow into `is_stale` and answer with a number nobody
    computed. The date-only case is admitted by `fromisoformat` and rejected
    for carrying no timezone, which is the case a naive parser lets through."""
    built = ServedOperationSet(
        deployment_id="d-1",
        operations=(ServedOperation.from_entry(OPERATIONS[0], index=0),),
        captured_at=value,
        source_url="",
    )
    with pytest.raises(ServedOperationSetError):
        built.age_seconds(CAPTURED_EPOCH)


def test_freshness_does_not_pretend_to_be_a_deployment_clock_anchor():
    """O-04 stays open: there is no second-clock field with no producer.

    `data-model.md` deleted `correspondence_evidence` on 2026-08-03 for being
    a field that could only ever be empty on the entity gating every session.
    A `deployment_revision` or `changed_at` here would be the same field by a
    different name, and the reader who found it empty would read that as a
    check that passed.
    """
    document = _set().document()
    for invented in ("deployment_revision", "changed_at", "deployed_at",
                     "build_id", "revision"):
        assert invented not in document, (
            f"{invented} is on the artifact with nothing producing it. When a "
            "deployment-clock anchor arrives it is a new field at a new "
            "schema version with a real producer, and until then an empty one "
            "reads as a passed check."
        )


def test_the_capture_time_is_beside_the_hash_and_not_under_it():
    """FR-055. Re-observing an unchanged deployment must not move the address."""
    wrapped = envelope.wrap("served_operation_set", _set().document())
    assert "captured_at" not in wrapped.payload
    assert wrapped.context["captured_at"] == CAPTURED_AT

    later = ServedOperationSet.from_admission(
        _decision(), captured_at="2026-09-09T09:09:09Z")
    assert envelope.wrap("served_operation_set", later.document()).address == \
        wrapped.address, (
        "looking again moved the artifact's content address, which FR-028 "
        "reads as the source having changed"
    )


# ---------------------------------------------------------------------------
# 4. The stage boundary (OD-06).

#: Modules on the source-analysis side of OD-06's line. An import edge from
#: T077's module to any of these is the layering collapse the decision exists
#: to prevent.
SOURCE_ANALYSIS_MODULES = (
    "src.analysis.codegraph_pin",
    "src.analysis.deputy_inspection",
    "codegraph",
    "ast",
    "libcst",
)


def _imports_of(path: Path) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(), filename=str(path))):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module)
    return names


def test_the_producing_stage_imports_nothing_from_source_analysis():
    """OD-06 as a property of the import graph, not of a paragraph.

    OD-06 put reachability *above* analysis so that analysis stays rebuildable
    from the codebase alone — deterministic, cacheable, and testable against
    committed fixtures, which a network probe would break because a fixture
    repository has nothing to probe. The decision survives only while the two
    stages cannot see each other, and a comment saying so is a convention.
    """
    imported = _imports_of(REPO / "src" / "analysis" / "served_operations.py")
    offending = sorted(imported & set(SOURCE_ANALYSIS_MODULES))
    assert not offending, (
        f"src/analysis/served_operations.py imports {offending}. FR-002 "
        "requires this set to be produced by a stage separate from and above "
        "source analysis; an edge in this direction is the two stages having "
        "merged."
    )


def test_the_checker_would_fire_on_a_planted_edge(tmp_path: Path):
    """The removal proof for the arm above, in the file.

    Without this, emptying `SOURCE_ANALYSIS_MODULES` would report a clean
    graph over the real module and pass forever — the exact shape INV-002's
    planted-edge test exists for.
    """
    planted = tmp_path / "planted.py"
    planted.write_text("from src.analysis.codegraph_pin import verify\n")
    assert _imports_of(planted) & set(SOURCE_ANALYSIS_MODULES)


def test_there_is_no_constructor_that_takes_a_codebase():
    """The stage boundary as a property of the interface.

    An import check catches the edge; this catches the parameter. A
    `from_codebase`, or a `from_admission` that also took a source tree, would
    make the set derivable without a running deployment — which is the
    opposite error from the one above and is not caught by it.
    """
    forbidden = ("from_codebase", "from_source", "from_routes", "from_index")
    for name in forbidden:
        assert not hasattr(ServedOperationSet, name), (
            f"ServedOperationSet.{name} produces a served-operation set "
            "without a running deployment. FR-002 requires the set to be "
            "obtained from a specification the target itself publishes."
        )
    import inspect

    for parameter in inspect.signature(
            ServedOperationSet.from_admission).parameters:
        assert "path" not in parameter and "codebase" not in parameter, (
            f"from_admission takes {parameter!r}, which reaches the source "
            "side of OD-06's line"
        )


def test_a_target_admission_refused_produces_no_set():
    """FR-044's disposition, carried into this stage.

    An empty set would be a value the caller goes on to use.
    """
    with pytest.raises(NotAdmittedForCapture, match="was not admitted"):
        ServedOperationSet.from_admission(
            _decision(state=ABSENT), captured_at=CAPTURED_AT)


# ---------------------------------------------------------------------------
# Operation granularity, and the artifact.


@pytest.mark.parametrize(
    "field", ["operation_id", "method", "path_template"],
    ids=["operation_id", "method", "path_template"],
)
def test_an_operation_missing_an_addressing_field_is_refused(field: str):
    entry = {k: v for k, v in OPERATIONS[0].items() if k != field}
    with pytest.raises(ServedOperationSetError, match="operations\\[0\\]"):
        ServedOperation.from_entry(entry, index=0)


def test_a_duplicated_operation_id_is_refused():
    """FR-056 records an inspection outcome per operation.

    The second entry would silently inherit the first's outcome.
    """
    with pytest.raises(ServedOperationSetError, match="appears twice"):
        _set(operations=(OPERATIONS[0], {**OPERATIONS[1],
                                         "operation_id": "list_parts"}))


def test_an_empty_set_is_refused():
    with pytest.raises(ServedOperationSetError, match="no operations"):
        ServedOperationSet(
            deployment_id="d-1", operations=(), captured_at=CAPTURED_AT,
            source_url="")


def test_the_document_satisfies_the_registry_schema():
    SERVED_OPERATION_SET.validate(_set().document())


def test_the_document_round_trips():
    built = _set()
    read = ServedOperationSet.from_document(built.document())
    assert read == built


def test_a_stale_schema_version_is_refused_rather_than_migrated_silently():
    document = {**_set().document(), "schema_version": "1.0.0"}
    with pytest.raises(ServedOperationSetError, match="Migrate it explicitly"):
        ServedOperationSet.from_document(document)


# ---------------------------------------------------------------------------
# The migration, against the committed pre-1.1.0 document.


def _published() -> dict:
    path = REPO / "tests" / "fixtures" / "reference-app" / "served_operations.json"
    return json.loads(path.read_text())


def test_the_migration_recovers_the_set_version_rather_than_inventing_one():
    """The contrast with the admission_decision migration, and it is the point.

    `set_version` is a function of the operation list and the operation list is
    in the document, so a migrated 1.0.0 set gets exactly the version it would
    have been given had it been written today. A placeholder here would read as
    the deployment having moved on the day we released a schema.
    """
    migrated = migrations.migrate("served_operation_set", _published())
    assert migrated["set_version"] == set_version_of(_published()["operations"])


def test_the_migration_does_not_invent_a_capture_time_the_document_never_had():
    without = {k: v for k, v in _published().items() if k != "captured_at"}
    migrated = migrations.migrate("served_operation_set", without)
    assert migrated["captured_at"] is None
    with pytest.raises(ServedOperationSetError, match="no capture time"):
        ServedOperationSet.from_document(migrated)


def test_the_committed_published_document_migrates_and_reads_back():
    migrated = migrations.migrate("served_operation_set", _published())
    built = ServedOperationSet.from_document(migrated)
    assert built.deployment_id == "d-reference-app"
    assert built.operation_ids() == (
        "health", "list_parts", "get_part", "list_shipments", "cancel_shipment")
