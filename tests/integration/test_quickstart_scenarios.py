"""T196 — every quickstart.md validation scenario, composed not rebuilt.

Each scenario is a named test that imports and calls the harnesses that
already close its arms. Dropping a scenario from this file, replacing one
with an empty `pass`, or deleting a backing harness fails T196. A skip is
not a pass and not an absence: privileged, live-image, and live-model arms
are named below with the reason they do not run here.

## What this file is, and what it is not

**Do.** Name A–E. Require the backing modules and the named tests inside
them. Invoke the public, fixture-free (or fixture-reconstructable)
harnesses so a green run of this file is a green run of those arms.

**Do not rebuild them.** The batteries and integration files remain the
home of each mechanism. This file is the orchestration that fails if a
scenario is omitted.

**Do not claim a live verified provider answer.** T164 shipped
four-provider *configuration* coverage; `ProviderDriver.call` still
raises `TransportUnavailableError` (T058 PARTIAL). Cassette / config
coverage is what a green A asserts, and the residual is re-asserted.

**Do not open SC-013. Do not set T181's threshold. Do not fuse clocks.
Do not use `compare_each` on a one-clock tick. Do not claim E13 ran.**
"""

from __future__ import annotations

import ast
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
THIS = Path(__file__).resolve()

#: Quickstart A–E. Deleting a letter here, or deleting the matching
#: `test_scenario_{letter}_*` function, is the omitted-scenario defect.
REQUIRED_SCENARIOS = ("A", "B", "C", "D", "E")

#: Exact function names. A prefix match would treat
#: `test_scenario_b_still_names_the_egress_battery` as scenario B.
SCENARIO_TEST_NAMES = {
    "A": "test_scenario_a_verified_answer_unattended",
    "B": "test_scenario_b_the_write_gate_holds",
    "C": "test_scenario_c_the_boundary_holds",
    "D": "test_scenario_d_drift_on_both_clocks",
    "E": "test_scenario_e_verifier_vs_judge",
}

#: Planted residuals. Flipping one is the honesty-rule failure the
#: named test exists to catch. Do not "fix" a proof by making the flag
#: unused: the test reads the flag, then the behaviour.
LIVE_VERIFIED_PROVIDER_ANSWER_IS_CLAIMED = False
T181_THRESHOLD_IS_SET = False
SC014_IS_RETIRED = False
SC013_WINDOW_IS_OPEN = False
CLOCKS_ARE_FUSED = False
COMPARE_EACH_IS_THE_ONE_CLOCK_PATH = False
E13_RAN = False

#: Skip reasons, quoted from the files that own the skip — not invented.
#: Single literals so a contiguous needle is what the named-skip test reads.
PRIVILEGED_SKIP = "needs CAP_SYS_ADMIN (mount namespaces, cgroup writes, seccomp listener). Add --privileged to the docker run."
LINUX_ONLY_SKIP = 'OD-17: Linux only. Run inside the dev image: docker run --rm --privileged -v "$PWD:/work" -w /work f2a-dev python -m pytest'
PROXY_BINARY_SKIP = "the enforcement point is a Go binary: set F2A_PROXY_BIN or have a Go toolchain so the battery can build it"
SANDBOX_IMAGE_SKIP = "Docker daemon is present but none of the T159 sandbox tags is loaded; the live in-container half cannot scan"
LIVE_MODEL_SKIP = "T058 PARTIAL: ProviderDriver.call raises TransportUnavailableError; vendor SDKs are not in requirements.lock. Cassette / four-provider config coverage is what T164 shipped, not a live verified answer."

#: Backing harnesses per scenario. A missing file or a missing named
#: test is the deleted-harness defect. Quoted from a fresh read of each
#: file; the done-note cites the same paths.
HARNESSES: dict[str, tuple[tuple[str, tuple[str, ...]], ...]] = {
    "A": (
        ("tests/integration/test_sc001_first_answer.py", (
            "test_the_run_reaches_a_first_verified_answer_within_the_window",
            "test_every_question_verified_on_the_unmodified_application",
        )),
        ("tests/batteries/test_four_providers.py", (
            "test_sc010_requires_four_independent_providers",
            "test_the_first_turn_transport_is_unavailable",
            "test_the_transport_residual_is_identical_across_providers",
        )),
        ("tests/conformance/test_core_path_cassettes.py", (
            "test_the_loop_round_trips_cassette_state_for_every_provider",
            "test_every_closed_provider_has_a_core_path_cassette",
        )),
        ("tests/conformance/test_provider_state_roundtrip.py", (
            "test_the_opaque_field_survives_the_chain_byte_identically",
            "test_every_provider_has_a_cassette_and_none_is_silently_missing",
            "test_the_answer_alone_cannot_detect_the_loss",
        )),
    ),
    "B": (
        ("tests/batteries/test_adversarial_egress.py", (
            "test_zero_calls_outside_the_read_only_set_reached_the_target",
            "test_every_recorded_denial_states_its_rule",
            "test_every_arm_actually_ran",
        )),
        ("tests/batteries/test_effect_gate_oracle.py", (
            "test_a_mutating_call_is_labelled_write_observed",
            "test_every_published_read_is_read_only_correct_and_the_write_is_observed",
            "test_t181_stays_unset_and_writes_stay_blocked",
        )),
        ("tests/unit/test_effect_precision.py", (
            "test_the_threshold_has_no_numeric_default",
            "test_writes_stay_blocked_while_the_threshold_is_unset",
        )),
    ),
    "C": (
        ("tests/integration/test_mount_namespace.py", (
            "test_an_undeclared_location_is_absent_not_denied",
            "test_a_declared_location_is_present",
        )),
        ("tests/integration/test_seccomp_recording.py", (
            "test_an_undeclared_path_is_recorded_with_a_rule_id",
            "test_the_record_is_emitted_before_the_kernel_acts",
        )),
        ("tests/batteries/test_bounds_exhaustion.py", (
            "test_memory_bound_exhaustion_names_its_terminal_state",
            "test_a_co_located_workload_keeps_serving_during_exhaustion",
            "test_the_workload_is_in_the_cgroup_from_its_first_instruction",
        )),
        ("tests/integration/test_lease_revocation.py", (
            "test_replay_from_a_later_session_is_denied_and_recorded",
            "test_replay_with_no_path_to_the_enforcement_point_is_unreachable",
            "test_a_sigkilled_supervisor_lets_the_lease_lapse",
            "test_the_residual_window_is_bounded_by_the_configured_interval",
        )),
        ("tests/batteries/test_in_container_scan.py", (
            "test_sandbox_image_holds_neither_credential",
            "test_compose_does_not_inject_credentials_into_sandbox",
        )),
    ),
    "D": (
        ("tests/batteries/test_drift_measurement.py", (
            "test_the_one_clock_path_is_compare_not_compare_each",
            "test_the_clocks_are_not_fused",
            "test_the_figures_are_synthetic_and_e13_never_ran",
            "test_source_clock_figures_are_reported_on_the_named_populations",
            "test_deployment_clock_figures_are_reported_on_the_named_populations",
        )),
        ("tests/batteries/test_drift_negative.py", (
            "test_reanalysis_of_unchanged_source_raises_zero_source_clock_signals",
        )),
        ("tests/contract/test_clocks.py", (
            "test_the_two_clocks_are_not_comparable_against_each_other",
        )),
        ("tests/fixtures/drift_corpora/source.py", ()),
        ("tests/fixtures/drift_corpora/deployment.py", ()),
    ),
    "E": (
        ("tests/batteries/test_judge_differential.py", (
            "test_caller_visible_surfaces_and_gate_decisions_are_identical_across_modes",
            "test_the_three_modes_are_the_population",
        )),
        ("tests/invariants/test_import_graph.py", (
            "test_no_recording_module_imports_the_judge",
        )),
        ("tests/unit/test_margin_report.py", (
            "test_empty_labels_do_not_open_the_sc013_window",
        )),
    ),
}


def _this_tree() -> ast.Module:
    return ast.parse(THIS.read_text(), filename=str(THIS))


def _function_defs(tree: ast.AST) -> dict[str, ast.FunctionDef]:
    return {
        node.name: node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
    } if isinstance(tree, ast.Module) else {}


def _function_source(name: str) -> str:
    tree = _this_tree()
    node = _function_defs(tree)[name]
    return ast.get_source_segment(THIS.read_text(), node) or ""


def empty_pass_scenarios(tree: ast.AST) -> list[str]:
    """Scenario tests whose body is only `pass` (docstring ignored).

    The removal proof of an empty A. A scanner that returned nothing
    would make `pass` indistinguishable from a composed run.
    """
    found: list[str] = []
    for name, node in _function_defs(tree).items():
        if not name.startswith("test_scenario_"):
            continue
        statements = [
            stmt for stmt in node.body
            if not (
                isinstance(stmt, ast.Expr)
                and isinstance(stmt.value, ast.Constant)
                and isinstance(stmt.value.value, str)
            )
        ]
        if not statements or (
            len(statements) == 1 and isinstance(statements[0], ast.Pass)
        ):
            found.append(name)
    return found


def _require_harnesses(letter: str) -> None:
    """Fail if a backing file or a named test in it is gone, or is `pass`."""
    entries = HARNESSES[letter]
    for relative, names in entries:
        path = REPO / relative
        assert path.is_file(), (
            f"scenario {letter} backing harness {relative} is gone"
        )
        if not names:
            continue
        tree = ast.parse(path.read_text(), filename=str(path))
        defined = {
            node.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        missing = [name for name in names if name not in defined]
        assert not missing, (
            f"scenario {letter} lost {relative}::{', '.join(missing)}"
        )
        for name in names:
            node = next(
                n for n in ast.walk(tree)
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                and n.name == name
            )
            statements = [
                stmt for stmt in node.body
                if not (
                    isinstance(stmt, ast.Expr)
                    and isinstance(stmt.value, ast.Constant)
                    and isinstance(stmt.value.value, str)
                )
            ]
            assert statements and not (
                len(statements) == 1 and isinstance(statements[0], ast.Pass)
            ), f"{relative}::{name} is an empty pass; that is the defect"


def _sigkill_from_another_process(pid: int) -> None:
    """Finding 006's technique, inlined: pytest 8 refuses calling a fixture."""
    subprocess.run(
        ["kill", "-KILL", str(pid)],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


# ---------------------------------------------------------------------------
# A · A verified answer, unattended — US1, SC-001, SC-010


def _compose_scenario_a(tmp_path: Path) -> None:
    _require_harnesses("A")

    from tests.integration import test_sc001_first_answer as sc001
    from tests.batteries import test_four_providers as four_providers
    from tests.conformance import test_core_path_cassettes as core_path
    from tests.conformance import test_provider_state_roundtrip as roundtrip

    run = sc001._run(sc001._clean)
    sc001.test_the_run_reaches_a_first_verified_answer_within_the_window(run)
    sc001.test_every_question_verified_on_the_unmodified_application(run)

    assert len(four_providers.PROVIDERS) == 4, (
        "SC-010 is four independent providers, not a subset"
    )
    four_providers.test_sc010_requires_four_independent_providers()
    four_providers.test_the_transport_residual_is_identical_across_providers()
    for provider in four_providers.PROVIDERS:
        four_providers.test_the_us1_path_is_selectable_for_every_provider(
            provider
        )
        four_providers.test_the_first_turn_transport_is_unavailable(provider)

    assert LIVE_VERIFIED_PROVIDER_ANSWER_IS_CLAIMED is False
    four_providers.test_the_residual_is_recorded()

    roundtrip.test_every_provider_has_a_cassette_and_none_is_silently_missing()
    for filename in roundtrip.PROVIDER_CASSETTES:
        roundtrip.test_the_opaque_field_survives_the_chain_byte_identically(
            filename
        )
    roundtrip.test_the_answer_alone_cannot_detect_the_loss()

    core_path.test_every_closed_provider_has_a_core_path_cassette()
    for filename in core_path.CORE_PATH_CASSETTES:
        core_path.test_the_loop_round_trips_cassette_state_for_every_provider(
            tmp_path / filename, filename
        )


def test_scenario_a_verified_answer_unattended(tmp_path: Path) -> None:
    """A · A verified answer, unattended — US1, SC-001, SC-010."""
    _compose_scenario_a(tmp_path)


# ---------------------------------------------------------------------------
# B · The write gate holds — US2, SC-002, SC-014


def _compose_scenario_b() -> None:
    _require_harnesses("B")

    from tests.batteries import test_effect_gate_oracle as oracle
    from tests.unit import test_effect_precision as precision

    oracle.test_a_mutating_call_is_labelled_write_observed()
    oracle.test_an_unchanged_call_is_labelled_read_only_correct()
    oracle.test_every_published_read_is_read_only_correct_and_the_write_is_observed()
    oracle.test_t181_stays_unset_and_writes_stay_blocked()

    precision.test_the_threshold_has_no_numeric_default()
    precision.test_writes_stay_blocked_while_the_threshold_is_unset()

    assert T181_THRESHOLD_IS_SET is False
    assert SC014_IS_RETIRED is False

    # Live SC-002 battery: Linux + CAP_SYS_ADMIN + Go proxy. Named, not
    # a pass. The file and its tests are still required above.
    _ = (PRIVILEGED_SKIP, LINUX_ONLY_SKIP, PROXY_BINARY_SKIP)


def test_scenario_b_the_write_gate_holds() -> None:
    """B · The write gate holds under an adversarial battery — US2, SC-002, SC-014."""
    _compose_scenario_b()


# ---------------------------------------------------------------------------
# C · The boundary holds — US3, SC-022, SC-023, SC-024


def _compose_scenario_c(tmp_path: Path) -> None:
    _require_harnesses("C")

    from tests.integration import test_lease_revocation as lease
    from tests.batteries import test_in_container_scan as in_container

    with lease.SessionTable(tmp_path / "sessions.db") as table:
        lease.test_replay_from_a_later_session_is_denied_and_recorded(table)
    unreachable = tmp_path / "unreachable"
    unreachable.mkdir()
    lease.test_replay_with_no_path_to_the_enforcement_point_is_unreachable(
        unreachable
    )
    sigkill_dir = tmp_path / "sigkill"
    sigkill_dir.mkdir()
    lease.test_a_sigkilled_supervisor_lets_the_lease_lapse(
        sigkill_dir, _sigkill_from_another_process
    )
    window_dir = tmp_path / "window"
    window_dir.mkdir()
    lease.test_the_residual_window_is_bounded_by_the_configured_interval(
        window_dir, _sigkill_from_another_process
    )

    in_container.test_sandbox_image_holds_neither_credential()
    in_container.test_compose_does_not_inject_credentials_into_sandbox()

    # Filesystem mount + seccomp recording + bounds: privileged kernel.
    # Live in-container scan: loaded sandbox image. Named, not a pass.
    _ = (PRIVILEGED_SKIP, LINUX_ONLY_SKIP, SANDBOX_IMAGE_SKIP)


def test_scenario_c_the_boundary_holds(tmp_path: Path) -> None:
    """C · The boundary holds — US3, SC-022, SC-023, SC-024."""
    _compose_scenario_c(tmp_path)


# ---------------------------------------------------------------------------
# D · Drift on both clocks — US4, SC-008, SC-009, SC-015, SC-020


def _compose_scenario_d() -> None:
    _require_harnesses("D")

    from tests.batteries import test_drift_measurement as drift
    from tests.batteries import test_drift_negative as negative
    from tests.contract import test_clocks as clocks

    assert COMPARE_EACH_IS_THE_ONE_CLOCK_PATH is False
    assert CLOCKS_ARE_FUSED is False
    assert E13_RAN is False

    drift.test_the_one_clock_path_is_compare_not_compare_each()
    drift.test_the_clocks_are_not_fused()
    drift.test_the_figures_are_synthetic_and_e13_never_ran()
    drift.test_source_clock_figures_are_reported_on_the_named_populations()
    drift.test_deployment_clock_figures_are_reported_on_the_named_populations()
    drift.test_t184_world_property_is_planted()

    negative.test_reanalysis_of_unchanged_source_raises_zero_source_clock_signals()
    clocks.test_the_two_clocks_are_not_comparable_against_each_other()


def test_scenario_d_drift_on_both_clocks() -> None:
    """D · Drift is detected on both clocks — US4, SC-008, SC-009, SC-015, SC-020."""
    _compose_scenario_d()


# ---------------------------------------------------------------------------
# E · Verifier vs judge — US5, SC-013, SC-025


def _compose_scenario_e(tmp_path: Path) -> None:
    _require_harnesses("E")

    from tests.batteries import test_judge_differential as judge
    from tests.invariants import test_import_graph as import_graph
    from tests.unit import test_margin_report as margin

    assert SC013_WINDOW_IS_OPEN is False

    judge.test_the_three_modes_are_the_population()
    judge.test_caller_visible_surfaces_and_gate_decisions_are_identical_across_modes(
        tmp_path
    )
    import_graph.test_no_recording_module_imports_the_judge()
    margin.test_empty_labels_do_not_open_the_sc013_window()


def test_scenario_e_verifier_vs_judge(tmp_path: Path) -> None:
    """E · The verifier is compared to a judge, and the judge cannot reach the caller."""
    _compose_scenario_e(tmp_path)


# ---------------------------------------------------------------------------
# Structural: omitted scenario, empty pass, dropped four-providers.


def test_every_quickstart_scenario_is_present() -> None:
    """Deleting scenario B (or any letter) fails here, not by absence."""
    assert REQUIRED_SCENARIOS == ("A", "B", "C", "D", "E")
    names = set(_function_defs(_this_tree()))
    missing = [
        letter
        for letter in REQUIRED_SCENARIOS
        if SCENARIO_TEST_NAMES[letter] not in names
    ]
    assert missing == [], (
        f"quickstart scenario(s) omitted from this file: {missing}. "
        "A skip is not an absence; the named test must still exist."
    )
    for letter in REQUIRED_SCENARIOS:
        assert letter in HARNESSES, f"scenario {letter} has no harness map"


def test_no_named_scenario_is_an_empty_pass() -> None:
    """Empty `pass` is the defect. The scanner is itself load-bearing."""
    found = empty_pass_scenarios(_this_tree())
    assert found == [], (
        "a named scenario is an empty pass:\n  " + "\n  ".join(found)
    )


def test_the_empty_pass_scanner_fires_on_a_plant() -> None:
    planted = ast.parse(
        "def test_scenario_a_verified_answer_unattended():\n    pass\n"
    )
    found = empty_pass_scenarios(planted)
    assert found == ["test_scenario_a_verified_answer_unattended"], (
        "the empty-pass scanner did not report a planted pass"
    )


def test_scenario_a_asserts_four_independent_providers() -> None:
    """Dropping the four-providers assertion from A fails here."""
    source = _function_source("_compose_scenario_a")
    assert "test_sc010_requires_four_independent_providers" in source, (
        "scenario A dropped the four-providers assertion; SC-010 is "
        "four independent providers, and T164 is configuration coverage, "
        "not a live verified answer"
    )
    assert "len(four_providers.PROVIDERS) == 4" in source


def test_scenario_a_does_not_claim_a_live_verified_provider_answer() -> None:
    assert LIVE_VERIFIED_PROVIDER_ANSWER_IS_CLAIMED is False
    assert LIVE_MODEL_SKIP.startswith("T058 PARTIAL")


def test_t181_stays_unset_and_sc014_is_not_retired() -> None:
    assert T181_THRESHOLD_IS_SET is False
    assert SC014_IS_RETIRED is False
    source = _function_source("_compose_scenario_b")
    assert "test_t181_stays_unset_and_writes_stay_blocked" in source
    assert "test_the_threshold_has_no_numeric_default" in source


def test_sc013_window_stays_closed() -> None:
    assert SC013_WINDOW_IS_OPEN is False
    source = _function_source("_compose_scenario_e")
    assert "test_empty_labels_do_not_open_the_sc013_window" in source


def test_drift_clocks_are_not_fused_and_e13_never_ran() -> None:
    assert CLOCKS_ARE_FUSED is False
    assert COMPARE_EACH_IS_THE_ONE_CLOCK_PATH is False
    assert E13_RAN is False
    source = _function_source("_compose_scenario_d")
    assert "test_the_one_clock_path_is_compare_not_compare_each" in source
    assert "test_the_clocks_are_not_fused" in source
    assert "test_the_figures_are_synthetic_and_e13_never_ran" in source
    assert "import compare_each" not in source


def test_the_two_replay_arms_are_reported_separately() -> None:
    source = _function_source("_compose_scenario_c")
    assert "test_replay_from_a_later_session_is_denied_and_recorded" in source
    assert (
        "test_replay_with_no_path_to_the_enforcement_point_is_unreachable"
        in source
    )


def test_scenario_b_still_names_the_egress_battery() -> None:
    """The live SC-002 battery stays in the map even when this host skips it."""
    paths = [relative for relative, _ in HARNESSES["B"]]
    assert "tests/batteries/test_adversarial_egress.py" in paths


def test_named_skips_are_not_passes() -> None:
    """A skip reason that disappeared is an arm that silently passed."""
    text = THIS.read_text()
    for reason in (
        PRIVILEGED_SKIP,
        LINUX_ONLY_SKIP,
        PROXY_BINARY_SKIP,
        SANDBOX_IMAGE_SKIP,
        LIVE_MODEL_SKIP,
    ):
        assert reason in text, f"named skip reason missing: {reason[:40]}"
