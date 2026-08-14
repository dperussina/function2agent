"""T130 — the not-verifiable share report, and the four ways it could lie.

**Requirement**: FR-045. **Criterion**: SC-019. **Also**: the second half of
OD-19.

The report is one number with three qualifiers, and each qualifier exists
because the number alone is misreadable:

| Qualifier | Without it |
|---|---|
| the interval | two reports over different spans compare as if they matched |
| the total | a share of 1/1 and a share of 5000/5000 read identically |
| the breakdown | one dominant reason and seven live ones read identically |
| `partial` | a half-closed window's share is compared against a whole one's |

SC-019 says the first two out loud: *"a bare percentage does not satisfy this"*.

## THE ARM THAT READS THE SOURCE, AND WHY IT IS NOT PARANOIA

`test_the_share_is_never_compared_against_anything` parses the module and
asserts no comparison node anywhere has `share` as an operand. A test that
asserted only `threshold_applied is None` would pass a module that compared the
share internally and reported the field as `None` beside it — which is the
defect FR-041 was written after, a threshold in force while nothing said so.

Run:
    python -m pytest tests/unit/test_not_verifiable_report.py -v
"""

from __future__ import annotations

import ast
import json

import pytest

from src.contracts import config as cfg
from src.contracts.result import REPORTED_STATE, ReportedState, VerificationOutcome
from src.contracts.unvalidated import is_marked
from src.runtime.reports import not_verifiable as nv
from src.runtime.reports.windows import WindowError
from src.runtime.verify import RefusalReason

WINDOW = nv.ReportingWindow(starts_at=1_000.0, length_seconds=3_600.0)
CLOSED = WINDOW.ends_at + 1.0
MID = WINDOW.starts_at + 1.0

SCOPE = {"deployment_id": "d-1", "tenant_id": "t-1"}


def _refused(reason: RefusalReason) -> nv.ReportedOutcome:
    return nv.ReportedOutcome(
        outcome=VerificationOutcome.NOT_VERIFIABLE, refusal_reason=reason
    )


def _verified() -> nv.ReportedOutcome:
    return nv.ReportedOutcome(outcome=VerificationOutcome.VERIFIED)


def _model_assessed() -> nv.ReportedOutcome:
    return nv.ReportedOutcome(
        outcome=VerificationOutcome.MODEL_ASSESSED, unattributed="model_assessed"
    )


# ---------------------------------------------------------------------------
# The named set. Read from the specification's enum, not from the traffic.


def test_the_breakdown_is_total_over_the_named_set_even_at_zero() -> None:
    """A reason nothing produced is reported at zero, not omitted.

    An omitted key and a key nothing in the deployment can reach look the same
    to a reader, and the second is a much more interesting fact.
    """
    produced = report_over([_refused(RefusalReason.PRECISION_NOT_STATED)])
    document = produced.document()["by_refusal_reason"]

    assert set(document) == {reason.value for reason in RefusalReason}, (
        "the breakdown's keys are not the named set. It is describing the "
        "traffic rather than measuring against the specification."
    )
    assert document["precision_not_stated"] == 1
    assert sum(document.values()) == 1
    assert all(
        document[reason.value] == 0
        for reason in RefusalReason
        if reason is not RefusalReason.PRECISION_NOT_STATED
    )


def test_every_named_reason_can_actually_be_counted() -> None:
    """The set is closed *and* reachable, which are two different claims.

    A breakdown total over an enum is free if the enum can be enumerated. This
    arm puts one record under each member and reads each back, so a member that
    the counter drops would show as a zero next to a record that exists.
    """
    produced = report_over([_refused(reason) for reason in RefusalReason])
    document = produced.document()["by_refusal_reason"]
    assert all(document[reason.value] == 1 for reason in RefusalReason)
    assert produced.not_verifiable_total == len(RefusalReason)


def report_over(outcomes, *, now: float = CLOSED) -> nv.NotVerifiableReport:
    return nv.report(outcomes, window=WINDOW, now=now, **SCOPE)


# ---------------------------------------------------------------------------
# The gap in the named set — the half `RefusalReason` cannot cover.


def test_a_model_assessed_result_is_counted_and_is_not_given_a_refusal_reason() -> None:
    """`REPORTED_STATE` puts it in the not-verifiable state; nothing refused it.

    Folding it into `NO_RECOMPUTING_CHECK` would make the breakdown sum and
    would say the verifier looked and declined, which it did not.
    """
    assert (
        REPORTED_STATE[VerificationOutcome.MODEL_ASSESSED]
        is ReportedState.NOT_VERIFIABLE
    ), "the premise moved: model-assessed is no longer reported not-verifiable"

    produced = report_over([_model_assessed(), _verified()])
    document = produced.document()

    assert produced.not_verifiable_total == 1
    assert sum(document["by_refusal_reason"].values()) == 0
    assert document["by_unattributed"]["model_assessed"] == 1
    assert document["unattributed_reasons"]["model_assessed"]


def test_the_two_breakdowns_together_account_for_every_not_verifiable_result() -> None:
    """The property that stops a record falling between the branches."""
    produced = report_over(
        [
            _refused(RefusalReason.CONTRACT_PROVISIONAL),
            _refused(RefusalReason.COLLECTION_UNAVAILABLE),
            _model_assessed(),
            nv.ReportedOutcome(
                outcome=VerificationOutcome.NOT_VERIFIABLE,
                unattributed="reason_not_recorded",
            ),
            _verified(),
            nv.ReportedOutcome(outcome=VerificationOutcome.FAILED),
        ]
    )
    document = produced.document()
    counted = sum(document["by_refusal_reason"].values()) + sum(
        document["by_unattributed"].values()
    )
    assert counted == produced.not_verifiable_total == 4
    assert produced.total_results == 6


def test_a_report_whose_breakdowns_do_not_add_up_cannot_be_constructed() -> None:
    """`_check_totals` is on the dataclass, so a hand-built document fails too."""
    with pytest.raises(nv.ReportInputError, match="account for"):
        nv.NotVerifiableReport(
            deployment_id="d-1",
            tenant_id="t-1",
            window=WINDOW,
            interval_closed=True,
            total_results=10,
            not_verifiable_total=4,
            by_reason={reason: 0 for reason in RefusalReason},
            by_unattributed={key: 0 for key in nv.UNATTRIBUTED},
        )


def test_a_report_that_omits_a_named_reason_cannot_be_constructed() -> None:
    by_reason = {reason: 0 for reason in RefusalReason}
    del by_reason[RefusalReason.SOURCES_NOT_INDEPENDENT]
    with pytest.raises(nv.ReportInputError, match="omits"):
        nv.NotVerifiableReport(
            deployment_id="d-1",
            tenant_id="t-1",
            window=WINDOW,
            interval_closed=True,
            total_results=0,
            not_verifiable_total=0,
            by_reason=by_reason,
            by_unattributed={key: 0 for key in nv.UNATTRIBUTED},
        )


# ---------------------------------------------------------------------------
# The record refuses to be ambiguous about its own attribution.


def test_a_not_verifiable_record_carrying_no_attribution_is_refused() -> None:
    with pytest.raises(nv.ReportInputError, match="neither"):
        nv.ReportedOutcome(outcome=VerificationOutcome.NOT_VERIFIABLE)


def test_a_not_verifiable_record_carrying_both_attributions_is_refused() -> None:
    with pytest.raises(nv.ReportInputError, match="both"):
        nv.ReportedOutcome(
            outcome=VerificationOutcome.NOT_VERIFIABLE,
            refusal_reason=RefusalReason.PRECISION_NOT_STATED,
            unattributed="model_assessed",
        )


def test_an_undeclared_unattributed_reason_is_refused() -> None:
    """Free text here would make the breakdown's second half open."""
    with pytest.raises(nv.ReportInputError, match="not a declared"):
        nv.ReportedOutcome(
            outcome=VerificationOutcome.NOT_VERIFIABLE, unattributed="dunno"
        )


def test_a_verified_result_carrying_a_refusal_reason_is_refused() -> None:
    with pytest.raises(nv.ReportInputError, match="carries an attribution"):
        nv.ReportedOutcome(
            outcome=VerificationOutcome.VERIFIED,
            refusal_reason=RefusalReason.PRECISION_NOT_STATED,
        )


def test_a_model_assessed_result_may_not_claim_the_verifier_refused_it() -> None:
    with pytest.raises(nv.ReportInputError, match="did not run"):
        nv.ReportedOutcome(
            outcome=VerificationOutcome.MODEL_ASSESSED,
            refusal_reason=RefusalReason.NO_RECOMPUTING_CHECK,
        )


# ---------------------------------------------------------------------------
# SC-019 — the share is not a bare percentage.


def test_the_document_states_the_interval_and_the_total_beside_the_share() -> None:
    """SC-019 itself: *'a bare percentage does not satisfy this'*."""
    produced = report_over([_refused(RefusalReason.PRECISION_NOT_STATED)] * 2 + [_verified()])
    document = produced.document()

    assert document["share"] == 2 / 3
    assert document["total_results"] == 3
    assert document["not_verifiable_total"] == 2
    assert document["interval"]["starts_at"] == WINDOW.starts_at
    assert document["interval"]["ends_at"] == WINDOW.ends_at
    assert is_marked(document["interval"]["length_seconds"]), (
        "the window length reached the document unmarked. An operator-typed "
        "length is still a number with no measurement behind it (FR-043)."
    )
    assert document["interval"]["length_seconds"]["value"] == WINDOW.length_seconds
    # Recomputable by the reader from the two counts, which is what makes the
    # share checkable rather than merely stated.
    assert (
        document["not_verifiable_total"] / document["total_results"]
        == document["share"]
    )


def test_an_empty_window_has_no_share_rather_than_a_share_of_zero() -> None:
    """`costs.UNPRICED`'s treatment, applied to a rate.

    Zero would say results arrived and none was unverifiable. Nothing arrived.
    """
    produced = report_over([])
    assert produced.share is None
    assert produced.document()["share"] is None
    assert produced.share_absent_because
    assert "0.0" in produced.share_absent_because


def test_a_share_that_exists_carries_no_absence_note() -> None:
    """The two fields are exclusive, so a reader is never given both."""
    produced = report_over([_verified()])
    assert produced.share == 0.0
    assert produced.share_absent_because is None


def test_a_window_that_has_not_closed_is_marked_partial() -> None:
    """FR-045. A partial window's share is over a smaller population."""
    partial = report_over([_verified()], now=MID)
    assert partial.document()["interval"]["partial"] is True
    assert partial.document()["interval"]["closed"] is False

    whole = report_over([_verified()], now=CLOSED)
    assert whole.document()["interval"]["partial"] is False
    assert whole.document()["interval"]["closed"] is True


def test_the_document_carries_the_deployment_and_the_tenant() -> None:
    """FR-035's two scope columns. A share with no owner is not comparable."""
    document = report_over([_verified()]).document()
    assert document["deployment_id"] == "d-1"
    assert document["tenant_id"] == "t-1"


def test_a_report_without_a_scope_is_refused() -> None:
    with pytest.raises(nv.ReportInputError, match="scope columns"):
        nv.report([], window=WINDOW, now=CLOSED, deployment_id="", tenant_id="t-1")


def test_the_document_is_json() -> None:
    """Machine-readable is a property of the bytes, not of the intent."""
    document = report_over([_model_assessed(), _verified()]).document()
    assert json.loads(json.dumps(document)) == document
    assert document["schema_version"] == nv.SCHEMA_VERSION


# ---------------------------------------------------------------------------
# No threshold, asserted twice — once on the field and once on the source.


def test_no_threshold_is_applied_and_the_absence_is_explained() -> None:
    document = report_over([_refused(RefusalReason.PRECISION_NOT_STATED)]).document()
    assert document["threshold_applied"] is None
    assert document["threshold_absent_because"] == nv.NO_THRESHOLD
    assert "FR-041" in nv.NO_THRESHOLD, (
        "the absence note no longer cites the requirement that makes it "
        "load-bearing rather than pending"
    )


def share_comparisons(source: str) -> list[str]:
    """Every comparison anywhere in `source` that reads `share`.

    **The whole subtree of each comparison, not its top-level operands.** An
    earlier version of this read `node.left` and `node.comparators` directly,
    and the removal proof for this arm found the hole in under a second: the
    planted `if (self.share or 0.0) > 0.5:` has a `BoolOp` on the left, so the
    share was one level down and the detector reported nothing. A threshold
    does not have to be written in the shape a reviewer imagined.
    """
    found: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Compare):
            continue
        for inner in ast.walk(node):
            reads_share = (
                isinstance(inner, ast.Attribute) and inner.attr == "share"
            ) or (isinstance(inner, ast.Name) and inner.id == "share")
            if reads_share:
                found.append(ast.unparse(node))
                break
    return found


def test_the_share_is_never_compared_against_anything() -> None:
    """The field being `None` is not evidence that nothing was compared.

    A module can compare the share internally and report `threshold_applied`
    as `None` beside it, which is FR-041's defect exactly: a threshold in force
    while nothing says so.
    """
    offending = share_comparisons(nv.module_source())
    assert not offending, (
        f"the share is compared against something: {offending}. T130 applies "
        "no threshold because none is pre-registered, and FR-041 is why a "
        "comparison here would not be a harmless one."
    )


def test_the_source_reading_arm_can_see_a_comparison_when_there_is_one() -> None:
    """The positive control for the arm above.

    A source-reading assertion passes when it reads nothing, so the detector is
    shown four shapes a threshold can wear — including the two that defeated
    the first version of it — and must find all four. Without this the arm
    above is satisfied by `module_source()` returning an empty string.
    """
    planted = {
        "bare attribute": "x = self.share > 0.05",
        "bare name": "x = share >= 0.05",
        # The shape the removal proof planted, which the first detector missed.
        "behind a boolean": "x = (self.share or 0.0) > 0.5",
        "behind a call": "x = abs(self.share) > 0.5",
    }
    missed = [label for label, code in planted.items() if not share_comparisons(code)]
    assert not missed, (
        f"the detector cannot see a share comparison it is shown: {missed}"
    )
    assert nv.module_source().strip(), "module_source() returned nothing to read"
    assert "def report(" in nv.module_source()


def test_an_unlocatable_module_is_refused_rather_than_read_as_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The negative control over the two arms above, and over the type fix.

    `inspect.getmodule` is typed `ModuleType | None`, and until 2026-08-12 the
    `None` went straight into `getsource`. The repair is a refusal only if the
    refusal fires, so this drives the branch rather than trusting the
    annotation: an unexercised `raise` is a claim about a line, not a result.

    It matters here more than it would elsewhere because the arm above reports
    an absence — no threshold found in the text. Text that was never read
    reports the same absence, so an empty return would turn a real gate into a
    green one and nothing downstream would notice.
    """
    monkeypatch.setattr(nv.inspect, "getmodule", lambda _obj: None)
    with pytest.raises(nv.ModuleTextUnavailable) as excinfo:
        nv.module_source()
    message = str(excinfo.value)
    # Naming what went missing is the point: `getsource` handed `None` raises
    # `TypeError: ... got NoneType`, which names a type and not the module.
    assert "inspect.getmodule()" in message
    assert "report()" in message


# ---------------------------------------------------------------------------
# The window is configuration, and it has no default.


def test_the_window_length_is_declared_configuration_with_no_default() -> None:
    """FR-045's Q-10 clause, held on the schema rather than on a caller."""
    declared = {key.name: key for key in cfg.RUNTIME_KEYS}
    key = declared.get("REPORTING_WINDOW_SECONDS")
    assert key is not None, (
        "the reporting window is not in RUNTIME_KEYS, so an unset one is a "
        "caller's problem rather than a startup failure"
    )
    assert key.default is None
    assert key.unvalidated is False, (
        "REPORTING_WINDOW_SECONDS acquired unvalidated=True. That plus a "
        "default is inventing a length; the key stays required-with-no-default "
        "and the value is marked when reported."
    )
    assert key.requirement == "FR-045"
    assert key.no_default_reason and "Q-10" in key.no_default_reason


def test_an_unset_window_fails_before_a_report_can_be_built() -> None:
    """The loud failure FR-045 asks for, reached from this module's own door."""
    env = {}
    with pytest.raises(cfg.ConfigError) as caught:
        cfg.load(cfg.RUNTIME_KEYS, env)
    assert "REPORTING_WINDOW_SECONDS" in str(caught.value)
    assert "Q-10" in str(caught.value), (
        "the operator is told to set a value without being told why guessing "
        "one is unsafe"
    )


def test_the_window_is_read_from_configuration_and_not_from_a_number() -> None:
    resolved = cfg.Config(values={"REPORTING_WINDOW_SECONDS": 900.0})
    window = nv.ReportingWindow.from_config(resolved, starts_at=0.0)
    assert window.length_seconds == 900.0
    assert window.ends_at == 900.0
    from src.runtime.reports.windows import ReportingWindow as WindowType
    assert nv.ReportingWindow is WindowType, (
        "T130 and T188 constructed two different window types. There is one "
        "constructor, in windows.py; not_verifiable re-exports it."
    )


def test_a_window_of_no_length_is_refused() -> None:
    """FR-045 rules out unbounded and all-of-time; zero is both at once."""
    for length in (0.0, -1.0):
        with pytest.raises(WindowError, match="FR-045"):
            nv.ReportingWindow(starts_at=0.0, length_seconds=length)
