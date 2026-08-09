"""T079 — FR-020's confused-deputy inspection, and FR-056's procedure.

Organised by what each group can be wrong about rather than by function:

1.  The stage boundary — that this runs after FR-044, over that stage's list.
2.  Step 1, handler resolution: exactly one, and both other counts decline.
3.  Step 2, enumeration: the catalogue's entries found, and — the group that
    matters — every unresolvable construct declining rather than passing.
4.  Step 3, destination influence: the three answers, and the near-misses that
    a laxer reading gets wrong.
5.  The outcome space and the fail-closed rule.
6.  The catalogue as reviewable configuration.

The negative controls are group 3's and group 4's. A confused-deputy inspection
that returns `clean` for everything passes every positive test in this file,
and the tests that can tell it apart are the ones asserting that a handler
which *should* decline does.
"""

from __future__ import annotations

import ast

import pytest

from src.analysis import admission
from src.analysis.deputy_inspection import (
    ALLOWED_OUTCOMES,
    CATALOGUE_BY_NAME,
    CATALOGUE_VERSION,
    CLEAN,
    DEPUTY,
    OUTBOUND_CATALOGUE,
    OUTCOMES,
    UNINSPECTABLE,
    UNRESOLVABLE_CONSTRUCTS,
    Codebase,
    DeputyInspectionError,
    InspectionReport,
    NotAdmittedForInspection,
    OperationOutcome,
    OutboundConstruct,
    gate,
    handler_index_from,
    inspect_admission,
    inspect_operation,
    outcomes_by_operation,
)


def outcome_of(source: str, symbol: str = "handler") -> OperationOutcome:
    """One handler's outcome, with the index and codebase wired up."""
    return inspect_operation(
        "op",
        handler_index={"op": symbol},
        codebase=Codebase.from_sources({"app.py": source}),
    )


# ---------------------------------------------------------------------------
# 1. The stage boundary.


def admitted(operations=(("op", ),)) -> admission.AdmissionDecision:
    return admission.AdmissionDecision(
        deployment_id="parts-api",
        admitted=True,
        state=admission.PUBLISHED_NON_EMPTY,
        criterion=admission.criterion_for(admission.PUBLISHED_NON_EMPTY),
        operations=tuple({"operation_id": op[0]} for op in operations),
        evidence="fixture",
        specification_source="file:///fixture",
    )


def rejected(state: str) -> admission.AdmissionDecision:
    return admission.AdmissionDecision(
        deployment_id="parts-api",
        admitted=False,
        state=state,
        criterion=admission.criterion_for(state),
        operations=(),
        evidence="fixture",
        specification_source="file:///fixture",
    )


@pytest.mark.parametrize(
    "state", sorted(set(admission.STATES) - admission.ADMISSIBLE_STATES)
)
def test_a_rejected_target_has_no_operation_list_to_inspect(state):
    """FR-020's ordering clause, over every non-admissible state.

    Parametrized over `STATES` rather than `FR_044_STATES` on purpose: the two
    states T073 added are non-admissible too, and an inspection that ran on an
    `unreachable` target would be inspecting an operation list nobody fetched.
    """
    with pytest.raises(NotAdmittedForInspection) as raised:
        inspect_admission(
            rejected(state),
            handler_index={},
            codebase=Codebase.from_sources({"app.py": ""}),
        )
    assert "second stage of one admission sequence" in str(raised.value)


def test_the_inspection_runs_over_the_list_the_first_stage_supplied():
    """The list is FR-044's, not one this stage built for itself."""
    decision = admitted((("a",), ("b",), ("c",)))
    report = inspect_admission(
        decision,
        handler_index={"a": "handler", "b": "handler", "c": "handler"},
        codebase=Codebase.from_sources({"app.py": "def handler(): pass"}),
    )
    assert [o.operation_id for o in report.outcomes] == ["a", "b", "c"]
    assert report.deployment_id == decision.deployment_id


def test_an_operation_absent_from_the_first_stages_list_is_not_inspected():
    """And asking for it raises rather than returning a permissive default.

    The permissive default is the bug: `outcome_for` returning `clean` for an
    unknown operation would make FR-051's comparison silently admit anything
    the first stage never listed.
    """
    report = inspect_admission(
        admitted((("a",),)),
        handler_index={"a": "handler"},
        codebase=Codebase.from_sources({"app.py": "def handler(): pass"}),
    )
    with pytest.raises(DeputyInspectionError) as raised:
        report.outcome_for("b")
    assert "recorded" in str(raised.value)


# ---------------------------------------------------------------------------
# 2. Step 1 — handler resolution.


def test_step_one_resolves_exactly_one_handler():
    result = outcome_of("def handler(): pass")
    assert result.outcome == CLEAN
    assert result.step == 2


def test_step_one_declines_when_the_operation_resolves_to_no_handler():
    """Zero handlers: served by something outside the analysed codebase."""
    result = inspect_operation(
        "op", handler_index={},
        codebase=Codebase.from_sources({"app.py": "def handler(): pass"}))
    assert result.outcome == UNINSPECTABLE
    assert result.step == 1
    assert "no handler symbol" in result.reason


def test_step_one_declines_when_the_index_names_a_symbol_that_is_not_there():
    result = outcome_of("def other(): pass", symbol="handler")
    assert (result.outcome, result.step) == (UNINSPECTABLE, 1)
    assert "defines no such symbol" in result.reason


def test_step_one_declines_when_the_symbol_is_defined_more_than_once():
    """Not 'pick the first'. Two definitions is not knowing which one serves it."""
    result = inspect_operation(
        "op", handler_index={"op": "handler"},
        codebase=Codebase.from_sources({
            "a.py": "def handler(): pass",
            "b.py": "def handler(url): __import__(url)",
        }))
    assert (result.outcome, result.step) == (UNINSPECTABLE, 1)
    assert "2 times" in result.reason


def test_the_first_definition_would_have_been_clean():
    """The negative control for the test above, and the reason it is not vacuous.

    `a.py`'s handler is `clean` and `b.py`'s is `uninspectable`. A procedure
    that picked the first definition would report `clean` — so the assertion
    above is discriminating between two behaviours that differ, rather than
    observing that a broken fixture fails.
    """
    assert outcome_of("def handler(): pass").outcome == CLEAN
    assert outcome_of("def handler(url): __import__(url)").outcome == UNINSPECTABLE


def test_methods_are_indexed_by_class_and_by_bare_name():
    result = inspect_operation(
        "op", handler_index={"op": "Parts.list"},
        codebase=Codebase.from_sources({
            "a.py": "class Parts:\n    def list(self): pass\n"}))
    assert result.outcome == CLEAN


def test_a_file_that_does_not_parse_contributes_no_symbols(tmp_path):
    """Fail-closed: its operations resolve to zero, not to something nearby.

    The other file in the directory parses, so this is not asserting that a
    broken tree yields nothing — it is asserting the broken file is skipped
    and its symbol is therefore missing, which is `uninspectable` at step 1.
    """
    (tmp_path / "broken.py").write_text("def handler(:\n")
    (tmp_path / "fine.py").write_text("def other(): pass\n")
    codebase = Codebase.from_directory(tmp_path)

    assert "other" in codebase.symbols
    result = inspect_operation(
        "op", handler_index={"op": "handler"}, codebase=codebase)
    assert (result.outcome, result.step) == (UNINSPECTABLE, 1)


def test_the_handler_index_refuses_two_symbols_for_one_operation():
    with pytest.raises(DeputyInspectionError) as raised:
        handler_index_from([("op", "a"), ("op", "b")])
    assert "exactly one" in str(raised.value)
    assert handler_index_from([("op", "a"), ("op", "a")]) == {"op": "a"}


# ---------------------------------------------------------------------------
# 3. Step 2 — enumeration, and the unresolvable constructs.
#
# This is the group that separates a real inspection from a rubber stamp.


def test_a_handler_with_no_outbound_call_is_clean():
    result = outcome_of(
        "def handler(part_id):\n"
        "    rows = database.lookup(part_id)\n"
        "    return rows\n"
    )
    assert result.outcome == CLEAN
    assert "catalogue" in result.reason


@pytest.mark.parametrize("construct", sorted(UNRESOLVABLE_CONSTRUCTS))
def test_every_unresolvable_construct_declines(construct):
    """FR-056 step 2's central rule, over each construct it names.

    *"A call the analyser can classify as neither outbound nor not-outbound
    makes the operation uninspectable"* — and the failure this guards is the
    one that turns the whole mechanism into a rubber stamp, since a handler
    containing only unresolvable calls contains no *catalogued* call and would
    otherwise read as `clean`.
    """
    call = f"{construct}(payload)" if "." not in construct else (
        f"import importlib\n    importlib.import_module(payload)")
    result = outcome_of(f"def handler(payload):\n    {call}\n")
    assert result.outcome == UNINSPECTABLE, construct
    assert result.step == 2


def test_a_handler_containing_only_an_unresolvable_call_is_not_clean():
    """The rubber-stamp control, stated as its own assertion.

    A procedure that enumerated catalogue hits and returned `clean` when it
    found none passes every other test in group 3. This is the one it fails.

    **The fixture is `getattr` bound to a name and called separately, and the
    shape is deliberate.** Written as `getattr(client, name)()` the outer call
    is dispatch through a value, so the *dispatch* guard catches it and this
    test passes with the unresolvable-construct table removed — a doubly
    covered guard, and its removal proof could not tell the two apart. Split
    across two statements, `getattr(...)` is a plain dotted callee and only the
    table declines it; `method()` resolves to a name that is not in the
    catalogue and is skipped. The table is then the sole mechanism.
    """
    result = outcome_of(
        "def handler(name):\n"
        "    method = getattr(client, name)\n"
        "    method()\n"
    )
    assert result.outcome != CLEAN
    assert result.step == 2


def test_dispatch_through_a_value_declines():
    """Not a name at all: a call on a subscript, and a call on a call."""
    for body in ("handlers[name]()", "factory()()"):
        result = outcome_of(f"def handler(name):\n    {body}\n")
        assert result.outcome == UNINSPECTABLE, body
        assert result.step == 2


def test_a_dotted_call_on_a_plain_receiver_is_resolvable():
    """The other side of the line above, so it is a line and not a blanket.

    `requests.get(...)` is a dotted name and resolves; if every attribute call
    declined, the catalogue would never match anything and the procedure would
    be `uninspectable`-for-everything, which is fail-closed and useless.
    """
    result = outcome_of('def handler():\n    requests.get("https://x/y")\n')
    assert result.outcome == CLEAN
    assert [s.rule_id for s in result.call_sites] == ["DEP-003"]


@pytest.mark.parametrize("entry", OUTBOUND_CATALOGUE, ids=lambda e: e.rule_id)
def test_every_catalogue_entry_is_found_at_a_call_site(entry):
    """FR-053's discipline: a construct is covered where a fixture exists.

    Every entry gets one here, so the catalogue cannot grow an entry that the
    matcher never actually fires on.
    """
    index = entry.destination_argument
    arguments = (
        ", ".join(["\"x\""] * index + ['"https://fixed.example/x"'])
        if isinstance(index, int)
        else f'{index}="https://fixed.example/x"'
    )
    result = outcome_of(
        f"def handler():\n    {entry.qualified_name}({arguments})\n")
    assert entry.rule_id in [s.rule_id for s in result.call_sites]


# ---------------------------------------------------------------------------
# 4. Step 3 — destination influence.


def test_a_build_time_destination_is_not_a_deputy():
    result = outcome_of(
        'def handler(part_id):\n'
        '    requests.get("https://inventory.internal/parts")\n'
    )
    assert result.outcome == CLEAN
    assert result.call_sites[0].destination == "build_time"


def test_a_destination_read_from_the_targets_own_configuration_is_not_a_deputy():
    for body in ('requests.get(self.upstream_url)',
                 'requests.get(UPSTREAM_URL)',
                 'requests.get(SETTINGS["upstream"])'):
        result = outcome_of(f"def handler(part_id):\n    {body}\n")
        assert result.outcome == CLEAN, body
        assert result.call_sites[0].destination == "target_configuration"


def test_a_destination_influenced_by_an_input_is_a_deputy():
    result = outcome_of(
        "def handler(callback_url):\n"
        "    requests.post(callback_url, json={})\n"
    )
    assert result.outcome == DEPUTY
    assert result.step == 3
    assert result.call_sites[0].destination == "operation_input"
    assert "never traverses the enforcement point" in result.reason


def test_influence_is_traced_through_a_chain_of_assignments():
    """Straight-line derivation, which a single pass happens to get right.

    `ast.walk` is breadth-first, so sibling statements are visited in source
    order and a chain written top-down needs only one pass. Kept as the
    ordinary case; the test below is the one that requires the fixed point.
    """
    result = outcome_of(
        "def handler(hook):\n"
        "    a = hook\n"
        "    b = a\n"
        "    target = b\n"
        "    requests.get(target)\n"
    )
    assert result.outcome == DEPUTY
    assert "target" in result.call_sites[0].detail


def test_influence_is_traced_when_the_chain_is_not_in_walk_order():
    """The fixed point, and the shape that needs it.

    `target = source` is a direct child of the handler; `source = hook` is
    nested one level down, and breadth-first order therefore visits the *use*
    before the *definition*. A single pass leaves `target` unmarked, reports
    the destination as untraceable-or-fixed, and misses a deputy — which is a
    false negative on precisely the case FR-020 exists for.
    """
    result = outcome_of(
        "def handler(hook, flag):\n"
        "    target = source\n"
        "    if flag:\n"
        "        source = hook\n"
        "    requests.get(target)\n"
    )
    assert result.outcome == DEPUTY, (
        "the derivation stopped before its fixed point: `target` is an input "
        "only after `source` is, and `source` is defined below it in "
        "breadth-first order"
    )


def test_an_f_string_naming_an_input_is_a_deputy():
    """The obvious case. Note it does **not** exercise the literal test.

    The influence check runs first and matches on the name inside the hole, so
    this outcome is the same whether an f-string counts as a literal or not.
    The test below is the one that separates them.
    """
    result = outcome_of(
        'def handler(host):\n'
        '    requests.get(f"https://{host}/parts")\n'
    )
    assert result.outcome == DEPUTY


def test_an_f_string_with_an_untraceable_hole_is_not_a_build_time_constant():
    """The near-miss a laxer literal test absorbs, and only this one sees it.

    The hole is a call rather than an input, so the influence check does not
    fire and the answer turns entirely on whether a joined string with a hole
    counts as fixed at build time. It does not: this is a template, and where
    it points is decided somewhere this analyser cannot see.
    """
    result = outcome_of(
        'def handler(part_id):\n'
        '    requests.get(f"https://{resolve_upstream()}/parts")\n'
    )
    assert result.outcome == UNINSPECTABLE
    assert result.call_sites[0].destination == "untraceable"


def test_an_f_string_with_no_hole_is_a_build_time_constant():
    """The control for the test above."""
    result = outcome_of('def handler(x):\n    requests.get(f"https://fixed/x")\n')
    assert result.outcome == CLEAN
    assert result.call_sites[0].destination == "build_time"


def test_an_untraceable_destination_declines_rather_than_passing():
    """'I could not find where this URL came from' is not 'it is a constant'."""
    result = outcome_of(
        "def handler(part_id):\n"
        "    requests.get(resolve_upstream())\n"
    )
    assert result.outcome == UNINSPECTABLE
    assert result.step == 3
    assert result.call_sites[0].destination == "untraceable"
    assert "is not 'it is a constant'" in result.reason


def test_a_call_inside_a_configuration_looking_chain_disqualifies_it():
    """`self.resolve(x)` reads like configuration and is a function of `x`."""
    result = outcome_of(
        "def handler(part_id):\n"
        "    requests.get(self.resolve(part_id))\n"
    )
    assert result.outcome == DEPUTY


def test_a_missing_destination_argument_is_untraceable_not_absent():
    result = outcome_of("def handler(x):\n    requests.get()\n")
    assert result.outcome == UNINSPECTABLE
    assert "not an absent destination" in result.call_sites[0].detail


def test_self_is_not_an_operation_input():
    """Otherwise every attribute read on the receiver is an influenced one.

    Which would make every method handler that reads its own configuration a
    deputy — the fail-closed direction, but wrong, and wrong in a way that
    denies the operations FR-056 step 3 explicitly permits.
    """
    result = inspect_operation(
        "op", handler_index={"op": "Parts.fetch"},
        codebase=Codebase.from_sources({"a.py":
            "class Parts:\n"
            "    def fetch(self):\n"
            "        requests.get(self.upstream)\n"}))
    assert result.outcome == CLEAN


def test_a_deputy_outweighs_an_untraceable_site_in_the_same_handler():
    """Both are denied, and the reported reason names the actionable one."""
    result = outcome_of(
        "def handler(hook):\n"
        "    requests.get(resolve())\n"
        "    requests.post(hook)\n"
    )
    assert result.outcome == DEPUTY


# ---------------------------------------------------------------------------
# 5. The outcome space and the fail-closed rule.


def test_the_outcome_space_is_closed():
    assert OUTCOMES == (CLEAN, DEPUTY, UNINSPECTABLE)
    with pytest.raises(DeputyInspectionError) as raised:
        OperationOutcome("op", "probably-fine", 1, "why")
    assert "fourth disposition" in str(raised.value)


def test_only_clean_is_allowed():
    assert ALLOWED_OUTCOMES == frozenset({CLEAN})
    assert not OperationOutcome("op", CLEAN, 1, "why").denied
    assert OperationOutcome("op", DEPUTY, 3, "why").denied
    assert OperationOutcome("op", UNINSPECTABLE, 2, "why").denied


def test_an_outcome_states_its_step_and_its_reason():
    with pytest.raises(DeputyInspectionError):
        OperationOutcome("op", CLEAN, 4, "why")
    with pytest.raises(DeputyInspectionError):
        OperationOutcome("op", CLEAN, 1, "")


def test_the_available_surface_is_the_clean_set_only():
    report = InspectionReport("d", (
        OperationOutcome("a", CLEAN, 3, "fixed destination"),
        OperationOutcome("b", DEPUTY, 3, "input-influenced"),
        OperationOutcome("c", UNINSPECTABLE, 2, "reflection"),
    ))
    assert report.available == ("a",)
    assert report.denied == ("b", "c")


def test_the_gate_refuses_and_names_the_step():
    report = InspectionReport("d", (
        OperationOutcome("a", CLEAN, 3, "fixed"),
        OperationOutcome("b", UNINSPECTABLE, 2, "reflection at line 4"),
    ))
    gate(report, "a")
    with pytest.raises(DeputyInspectionError) as raised:
        gate(report, "b")
    assert "FR-056 step 2" in str(raised.value)
    assert "reflection at line 4" in str(raised.value)


def test_the_target_level_case_is_the_degenerate_operation_level_one():
    """FR-020 says a target fails closed; FR-056 says an operation does.

    Where the analysis precondition fails, every operation declines at step 1
    and the target has no callable operation left — so no separate target-level
    threshold is needed, and none is invented.
    """
    report = inspect_admission(
        admitted((("a",), ("b",))),
        handler_index={},
        codebase=Codebase.from_sources({"app.py": ""}),
    )
    assert report.available == ()
    assert set(report.denied) == {"a", "b"}
    assert {o.step for o in report.outcomes} == {1}


def test_the_recorded_outcome_is_what_fr_051_compares():
    report = inspect_admission(
        admitted((("a",), ("b",))),
        handler_index={"a": "clean_handler", "b": "deputy_handler"},
        codebase=Codebase.from_sources({"app.py":
            'def clean_handler():\n    requests.get("https://fixed/x")\n'
            "def deputy_handler(u):\n    requests.get(u)\n"}))
    assert outcomes_by_operation(report) == {"a": CLEAN, "b": DEPUTY}


# ---------------------------------------------------------------------------
# 6. The catalogue as reviewable configuration.


def test_the_catalogue_is_versioned_and_every_entry_is_justified():
    assert CATALOGUE_VERSION == "1.0.0"
    for entry in OUTBOUND_CATALOGUE:
        assert entry.rule_id.startswith("DEP-")
        assert len(entry.justification) > 40, entry.rule_id
    assert len(CATALOGUE_BY_NAME) == len(OUTBOUND_CATALOGUE)


def test_an_entry_outside_the_deputy_rule_namespace_is_refused():
    with pytest.raises(DeputyInspectionError) as raised:
        OutboundConstruct("EG-001", "x.y", 0, "a" * 50)
    assert "namespace" in str(raised.value)


def test_an_unjustified_entry_is_refused():
    with pytest.raises(DeputyInspectionError):
        OutboundConstruct("DEP-999", "x.y", 0, "")


def test_the_report_document_says_it_is_a_stated_rule_set_and_not_a_proof():
    """FR-056 requires this in its own words, and U-44 requires the rest.

    A consumer reading a `clean` outcome as a measured property is the failure
    this sentence exists to prevent.
    """
    report = InspectionReport("d", (OperationOutcome("a", CLEAN, 3, "fixed"),))
    document = report.document()
    assert "not a proof" in document["basis"]
    assert "U-44" in document["basis"]
    assert document["catalogue_version"] == CATALOGUE_VERSION
    assert document["outcomes"][0]["denied"] is False


def test_the_catalogue_version_travels_with_every_outcome():
    """So a recorded finding says which rule set produced it."""
    outcome = OperationOutcome("a", CLEAN, 3, "fixed")
    assert outcome.document()["catalogue_version"] == CATALOGUE_VERSION


# ---------------------------------------------------------------------------
# The layering arm, matching T077's.


def test_this_stage_reads_source_and_never_a_running_deployment():
    """OD-06's line, from the other side.

    T077's set is established *above* analysis, from what a deployment
    publishes. This stage is *analysis*: it reads the codebase and must not
    reach a deployment, or its answer would stop being reproducible from the
    source alone.
    """
    import src.analysis.deputy_inspection as module

    source = ast.parse(open(module.__file__).read())
    imported = {
        alias.name
        for node in ast.walk(source)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        node.module
        for node in ast.walk(source)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    forbidden = {"urllib.request", "http.client", "socket", "requests", "httpx"}
    assert not (imported & forbidden), (
        f"{sorted(imported & forbidden)}: a static analyser that opens a "
        "socket is not analysing the codebase any more"
    )
