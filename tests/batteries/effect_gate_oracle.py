"""T180 — the FR-041 state-diff oracle.

**Requirement**: FR-041. **Also**: constitution Principle I's admissible
artifacts.

Labels come from observable state on the reference application: snapshot
the application's state, issue the call, diff. A call that leaves state
byte-identical is `read_only_correct`. A call that mutates state is
`write_observed`. The gate's read-only precision is whether its
`read_only` / deny dispositions match that fact. This module produces
the labels; it does not score them, it does not invent a threshold, and
it does not release a write.

## THE THREE THINGS THIS MODULE REFUSES TO DO, AND WHY EACH IS A REFUSAL

**1. It will not ask a model.** Principle I's admissible artifact here is
observable state, not a judgement. `src.runtime.judge` is not imported.
A label that came from a shadow judge agreeing with the published
`effect_tier` would be the substitution FR-052 exists to prevent, applied
to the corpus FR-041 scores against.

**2. It will not label from the verb, the published tier, or the HTTP
status.** `POST /shipments/S-9999/cancel` is a write-shaped call that
404s and leaves state unchanged; it is `read_only_correct` because
nothing mutated. Labelling it `write_observed` because the method is
POST, or because `served_operations.json` says `write`, is a
specification restating itself rather than an observation.

**3. It will not invent a threshold or release a write.** T181's
`PER_CALL_THRESHOLD` stays `UNSET`. Labelling the corpus is the
precondition of the measurement FR-041 requires, not the measurement.
`MEASURED_AGAINST_LABELLED_CORPUS` stays False.

## WHAT IS OWED AND IS NOT BUILT

* **T181 — the per-call threshold.** Unset. This module does not score.
* **T182–T184 — drift.** A sibling's files. Untouched.
* **T214 / T215.** No run produces a `Result`. This oracle drives
  `Application.call` in-process (T116); it does not invent those call
  sites.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any, Iterable

from src.contracts.canonical import dumps
from src.runtime.reports.effect_corpus import (
    CorpusExport,
    ObservationRow,
    attach_labels,
)

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "reference-app"

LABEL_READ_ONLY_CORRECT = "read_only_correct"
LABEL_WRITE_OBSERVED = "write_observed"
LABELS = frozenset({LABEL_READ_ONLY_CORRECT, LABEL_WRITE_OBSERVED})

#: Placeholders the reference application actually serves. A template
#: carrying any other name is not a call this oracle can instantiate,
#: and guessing `{id}` → `P-0001` would label a path the application
#: does not serve.
PLACEHOLDERS = {
    "part_id": "P-0001",
    "shipment_id": "S-0001",
}

_PLACEHOLDER = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")

#: Named residuals. Flipping either is claiming a sibling closed.
T181_THRESHOLD_STAYS_UNSET = True
T214_RESIDUAL_NO_RUN_PRODUCES_A_RESULT = True


class OracleError(ValueError):
    """A call, a template, or a label this oracle refuses."""


class ModuleTextUnavailable(RuntimeError):
    """This module's own text could not be located for the arm that reads it."""


@dataclass(frozen=True)
class StateDiff:
    """One snapshot, one call, one diff.

    `before` and `after` are canonical bytes of `Application.state`.
    The label is a function of those two, never of the response body,
    the HTTP status, the method, or a published effect tier.
    """

    before: bytes
    after: bytes
    label: str

    @property
    def mutated(self) -> bool:
        return self.before != self.after


def _load_fixture(name: str) -> ModuleType:
    """Load a reference-app module under a unique name.

    Same convention as `tests/unit/test_reference_app.py`: the fixture
    directory carries a hyphen, so it is not a package, and a bare
    `import app` collides with the next fixture that picks that name.
    `app.py` itself puts the directory on `sys.path` so `import seed`
    resolves; we do the same before exec so that import sees a loaded
    sibling rather than a second copy.
    """
    if str(FIXTURE) not in sys.path:
        sys.path.insert(0, str(FIXTURE))
    spec = importlib.util.spec_from_file_location(
        f"_t180_{name}", FIXTURE / f"{name}.py"
    )
    if spec is None or spec.loader is None:
        raise OracleError(f"could not load {FIXTURE / name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_SEED = _load_fixture("seed")
_APP = _load_fixture("app")


def fresh_application() -> Any:
    """A private copy of the committed state. T180 drives a copy."""
    return _APP.from_committed_state()


def snapshot(app: Any) -> bytes:
    """Canonical bytes of the application's in-memory state.

    Not the HTTP body, not `Application.calls`, not `state.json` on
    disk. The committed fixture is the control; the copy is the
    treatment. Diffing the file would either miss an in-memory write
    or require this oracle to persist one.
    """
    return dumps(app.state)


def require_label(label: str) -> str:
    """The closed vocabulary. A third value is not an observation."""
    if label not in LABELS:
        raise OracleError(
            f"{label!r} is not an observable-state label. T180's "
            "vocabulary is read_only_correct (state byte-identical) "
            "and write_observed (state mutated). A model judgement, "
            "a published effect_tier, or an invented third value is "
            "not one of those."
        )
    return label


def instantiate(method: str, template: str) -> str:
    """Bind the reference application's placeholders. Refuse any other."""
    if not method:
        raise OracleError("a call with no method is not a labelled observation")

    def _bind(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in PLACEHOLDERS:
            raise OracleError(
                f"placeholder {{{name}}} in {template!r} is not a "
                "reference-application identifier. Instantiating it "
                "would label a path the application does not serve."
            )
        return PLACEHOLDERS[name]

    return _PLACEHOLDER.sub(_bind, template)


def _issue(app: Any, method: str, target: str) -> None:
    """The call. Skipping this makes every write look unchanged."""
    app.call(method, target)


def observe(app: Any, method: str, target: str) -> StateDiff:
    """Snapshot, call, diff. The label is the observable fact."""
    before = snapshot(app)
    _issue(app, method, target)
    after = snapshot(app)
    mutated = before != after
    if not mutated:
        label = require_label(LABEL_READ_ONLY_CORRECT)
    else:
        label = require_label(LABEL_WRITE_OBSERVED)
    return StateDiff(before=before, after=after, label=label)


def label_corpus(rows: Iterable[ObservationRow]) -> CorpusExport:
    """Drive each observation against a fresh copy and attach T180 labels.

    One application per row, always. Reusing a copy would make a second
    cancel of S-0001 look `read_only_correct` because the first already
    wrote, which is a battery reporting no effect because its baseline
    moved with it — the defect `test_two_applications_built_from_one_state_do_not_share_it`
    exists to catch on the fixture, applied here to the oracle.
    """
    records = tuple(rows)
    labels: dict[int, str] = {}
    for row in records:
        if row.decision_seq in labels:
            raise OracleError(
                f"decision_seq {row.decision_seq} appears twice. Two "
                "rows sharing a key cannot both carry a label this "
                "map could distinguish."
            )
        app = fresh_application()
        target = instantiate(row.method, row.matched_template)
        labels[row.decision_seq] = observe(app, row.method, target).label
    return attach_labels(records, labels)


def label_served_operations() -> tuple[StateDiff, ...]:
    """Every published operation, instantiated, labelled by state diff."""
    diffs: list[StateDiff] = []
    for operation in _SEED.load_served_operations()["operations"]:
        method = str(operation["method"])
        template = str(operation["path_template"])
        app = fresh_application()
        diffs.append(observe(app, method, instantiate(method, template)))
    return tuple(diffs)


def module_source() -> str:
    """This module's own text, for the arm that reads it for a judge import."""
    try:
        return Path(__file__).read_text()
    except OSError as exc:
        raise ModuleTextUnavailable(
            "this oracle's own text could not be read, so the arm that "
            "searches it for a shadow-judge import would find none"
        ) from exc
