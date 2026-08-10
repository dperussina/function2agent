"""T095 — the egress-policy contract, tested over every named denial reason.

Against [`contracts/egress-policy.md`](../../specs/002-spec-aware-agent-runtime/contracts/egress-policy.md)
and the enforcement point's own registry, `src/proxy/rules.go`.

## The hazard this file is built around

"Every named denial reason" is an **enumeration** claim, and the way an
enumeration test fails is by passing over an empty or partial set. So nothing
here is transcribed: the reasons come out of the contract's own prose and the
registry comes out of the Go source, and **three controls** stand under the
derivation, each of which fails if its parser stops finding things:

| Control | What it would catch |
|---|---|
| `test_the_contract_parser_reads_the_document_and_not_a_constant` | a parser returning a frozen list, or one that has stopped matching the paragraph |
| `test_the_registry_parser_reads_the_go_source_and_not_a_constant` | the same, on the Go side |
| `test_a_reason_the_registry_does_not_produce_is_caught` | the comparison itself passing vacuously — the negative control the experiment-design skill's Rule 8 asks for, because the correspondence test's positive result is *an absence* |

The comparison is **contract ⊆ registry**, which is the direction the contract
states: "Named reasons include, **at minimum**". The registry is allowed to be
larger and is — it also names `allowed`, which is not a denial reason at all.

## What this file does NOT re-derive

`tests/invariants/test_rule_id_present.py` (INV-004) already covers rule-id
presence at every deny site, registration, uniqueness and the `EG-`/`FS-`
namespace split. `src/proxy/addresses_test.go` already covers the exemption's
behaviour. Neither of those ties the **contract document** to the code, which
is what a contract test is for and is the only thing added here.

## What this file found

The contract's request pipeline numbers **eight** stages; the enforcement point
registers **six gate stages and one final stage**, and the one contract stage
with no counterpart is stage 4, the address class. That is not a bug and it is
not hidden: the check runs at configuration load and on every dial rather than
as a per-request gate, which under FR-016's single pinned address is the same
address every time. `test_exactly_one_contract_stage_has_no_gate_stage` pins
the divergence to that one stage, so a *second* undocumented stage, or the
disappearance of the dial-time check, is a failure. Recorded as finding 037.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
CONTRACT = REPO / "specs" / "002-spec-aware-agent-runtime" / "contracts" / "egress-policy.md"
PROXY = REPO / "src" / "proxy"
RULES_GO = PROXY / "rules.go"
ADDRESSES_GO = PROXY / "addresses.go"
DECISIONLOG_GO = PROXY / "decisionlog.go"

requires_proxy = pytest.mark.skipif(
    not RULES_GO.is_file(),
    reason="the Go enforcement point is not present in this tree")

#: A machine-readable reason: lower snake_case, no spaces. These are written
#: into a JSON error body the client reads and into a `TEXT` column an operator
#: greps, so a reason with a space in it is a reason nobody can filter on.
REASON_TOKEN = re.compile(r"^[a-z][a-z0-9_]*$")

#: The clause the 2026-08-03 amendment turns on. Matched verbatim because it is
#: the containment itself and not a description of one — see the two structural
#: assertions that pair with it. Matched against the document with its line
#: wrapping collapsed, because where markdown breaks a line is not part of the
#: clause and a test that depended on it would fail on a reflow.
ONE_EXEMPTION_CLAUSE = "**Two exemptible classes, one exemption**"


# ---------------------------------------------------------------------------
# Derivation. Nothing below this line is a transcribed list.
# ---------------------------------------------------------------------------


def _contract() -> str:
    return CONTRACT.read_text()


def _unwrapped(text: str) -> str:
    """The document with its line wrapping collapsed to single spaces."""
    return re.sub(r"\s+", " ", text)


def named_reasons(text: str) -> set[str]:
    """The contract's named denial reasons, out of its own paragraph.

    Anchored on the sentence that introduces the list and terminated by the
    blank line that ends the paragraph, so a backticked token elsewhere in the
    document is not swept in and a reason added to the paragraph is.
    """
    match = re.search(
        r"Named reasons include, at minimum:(.*?)\n\n", text, re.DOTALL)
    if match is None:
        return set()
    return {
        token for token in re.findall(r"`([^`]+)`", match.group(1))
        if REASON_TOKEN.match(token)
    }


def registry(text: str) -> dict[str, tuple[str, str]]:
    """`ruleRegistry` as `{rule id: (reason, requirement)}`.

    Read through the constants, because the map is keyed by constant name
    rather than by literal; a rule whose constant is missing is therefore not
    silently dropped, it is absent from `ids` and the caller sees a short map.
    """
    ids = dict(re.findall(r'^\s*(Rule\w+)\s*=\s*"([A-Z0-9-]+)"', text, re.M))
    out: dict[str, tuple[str, str]] = {}
    for name, reason, requirement in re.findall(
        r'^\s*(Rule\w+):\s*\{Reason:\s*"([^"]*)",\s*Requirement:\s*"([^"]*)"\}',
        text, re.M,
    ):
        out[ids.get(name, name)] = (reason, requirement)
    return out


def pipeline_stages(text: str) -> list[str]:
    """Every numbered stage under `## Request pipeline`, normalised.

    Normalisation strips everything but letters, so `Re-originate` and
    `Effect resolution` become `reoriginate` and `effectresolution` — the forms
    a registered stage name is a prefix of. Splitting on the first word instead
    turned `Re-originate` into `re`, which matched no stage and reported a
    divergence that was punctuation.
    """
    section = re.search(
        r"## Request pipeline\n(.*?)\n## ", text, re.DOTALL)
    assert section, "no `## Request pipeline` section in the contract"
    heads = re.findall(r"^\d+\.\s+\*\*([^*]+)\*\*", section.group(1), re.M)
    return [re.sub(r"[^a-z]", "", h.lower()) for h in heads]


def stage_correspondence(
    contract_stages: list[str], registered: set[str]
) -> tuple[set[str], set[str]]:
    """`(contract stages with no gate stage, gate stages the contract omits)`.

    A registered name corresponds to a contract stage when either is a
    **prefix** of the other: the pipeline's `effect` is the contract's
    `Effect resolution`, and the contract's `Re-originate` is the pipeline's
    `reoriginate`. Exact equality would report both pairs as divergences, which
    is a difference in how verbose a heading is rather than in what runs.
    """
    def corresponds(contract: str, name: str) -> bool:
        return contract.startswith(name) or name.startswith(contract)

    unbuilt = {c for c in contract_stages
               if not any(corresponds(c, name) for name in registered)}
    undocumented = {name for name in registered
                    if not any(corresponds(c, name) for c in contract_stages)}
    return unbuilt, undocumented


def defined_stage_names() -> set[str]:
    """Every stage type that *exists* in the enforcement point's source."""
    names: set[str] = set()
    for path in sorted(PROXY.glob("*.go")):
        if path.name.endswith("_test.go"):
            continue
        names.update(re.findall(r'stageName:\s*"([a-z]+)"', path.read_text()))
    return names


def registered_stage_names() -> set[str]:
    """Every stage the pipeline actually **registers**, which is the different
    and load-bearing question.

    A stage type can exist and never be wired in, and a scan over definitions
    would count it. So the gates come out of `defaultStages`'s own body and the
    final stage out of the constructor `NewProxy` passes as `final`, resolved
    to the file that defines it — nothing here is keyed on a filename.
    """
    main = (PROXY / "main.go").read_text()
    body = re.search(r"func defaultStages\(.*?\n\}", main, re.DOTALL)
    assert body, "no `defaultStages` in src/proxy/main.go"
    names = {m.lower() for m in re.findall(r"New(\w+)Stage\(", body.group(0))}

    final_ctor = re.search(r"final := (New\w+)\(", main)
    assert final_ctor, "no final stage constructed in src/proxy/main.go"
    for path in sorted(PROXY.glob("*.go")):
        if path.name.endswith("_test.go"):
            continue
        source = path.read_text()
        if f"func {final_ctor.group(1)}(" in source:
            names.update(re.findall(r'stageName:\s*"([a-z]+)"', source))
    return names


def unproduced(contract_reasons: set[str], produced: set[str]) -> set[str]:
    """Contract reasons no registered rule produces. The comparison itself.

    A named function because the negative control below runs **this** function
    over a planted set rather than a second copy of the comparison — a control
    scored by different code proves only that the different code works.
    """
    return contract_reasons - produced


# ---------------------------------------------------------------------------
# The vacuity floor, and the controls under each parser.
# ---------------------------------------------------------------------------


def test_the_contract_names_a_non_empty_set_of_machine_readable_reasons() -> None:
    reasons = named_reasons(_contract())
    assert len(reasons) >= 10, (
        f"the contract paragraph yielded {len(reasons)} reasons "
        f"({sorted(reasons)}). Every assertion in this file quantifies over "
        "that set, so a short one makes them all cheap."
    )
    for reason in reasons:
        assert REASON_TOKEN.match(reason), (
            f"{reason!r} is not machine-readable. Reasons go into a JSON error "
            "body and a TEXT column; a space in one is a reason nobody filters on."
        )


def test_the_contract_parser_reads_the_document_and_not_a_constant() -> None:
    """Add one, lose one. A frozen list survives neither."""
    text = _contract()
    baseline = named_reasons(text)

    planted = text.replace(
        "`address_class_denied`",
        "`address_class_denied`, `planted_reason_for_t095`")
    assert named_reasons(planted) == baseline | {"planted_reason_for_t095"}

    thinned = text.replace("`session_terminated`, ", "")
    assert named_reasons(thinned) == baseline - {"session_terminated"}

    assert named_reasons("a document with no such paragraph") == set()


@requires_proxy
def test_the_registry_names_a_non_empty_set_of_machine_readable_reasons() -> None:
    rules = registry(RULES_GO.read_text())
    assert len(rules) >= 15, (
        f"the Go registry parser yielded {len(rules)} rules; the pipeline has "
        "more stages than that has entries, so the parser is looking at the "
        "wrong shape"
    )
    for rule_id, (reason, requirement) in rules.items():
        assert rule_id.startswith("EG-"), rule_id
        assert REASON_TOKEN.match(reason), (rule_id, reason)
        assert re.match(r"^FR-\d{3}$", requirement), (rule_id, requirement)


@requires_proxy
def test_the_registry_parser_reads_the_go_source_and_not_a_constant() -> None:
    text = RULES_GO.read_text()
    baseline = registry(text)

    planted = text.replace(
        'RuleAllowed: {Reason: "allowed", Requirement: "FR-011"},',
        'RuleAllowed: {Reason: "allowed", Requirement: "FR-011"},\n'
        '\tRuleMethodNotAllowed2: {Reason: "planted", Requirement: "FR-000"},')
    grown = registry(planted)
    assert len(grown) == len(baseline) + 1
    assert "planted" in {reason for reason, _ in grown.values()}

    thinned = text.replace(
        'RuleAddressClassDenied: {Reason: "address_class_denied", Requirement: "FR-017"},', "")
    assert "EG-ADDR-001" not in registry(thinned)


# ---------------------------------------------------------------------------
# Every named denial reason.
# ---------------------------------------------------------------------------


@requires_proxy
def test_every_named_reason_in_the_contract_is_produced_by_a_registered_rule() -> None:
    reasons = named_reasons(_contract())
    rules = registry(RULES_GO.read_text())
    produced = {reason for reason, _ in rules.values()}

    assert reasons, "no reasons parsed; the check below would be free"
    missing = unproduced(reasons, produced)
    assert missing == set(), (
        f"the contract names {sorted(missing)} but no rule in "
        "src/proxy/rules.go produces them. A reason the contract publishes and "
        "the enforcement point cannot emit is a denial an operator will look "
        "for and never find."
    )


@requires_proxy
def test_a_reason_the_registry_does_not_produce_is_caught() -> None:
    """The negative control. Rule 8: the test above succeeds by finding
    *nothing*, and every way it could break also finds nothing.
    """
    produced = {reason for reason, _ in registry(RULES_GO.read_text()).values()}
    planted = named_reasons(_contract()) | {"exfiltration_denied"}
    assert unproduced(planted, produced) == {"exfiltration_denied"}


@requires_proxy
def test_every_named_reason_names_exactly_the_rules_that_carry_it() -> None:
    """Each reason resolves to at least one `EG-` identifier.

    The record carries the rule id and the reason together (FR-011), so a
    reason with no rule behind it could be published and never attributable.
    """
    rules = registry(RULES_GO.read_text())
    by_reason: dict[str, list[str]] = {}
    for rule_id, (reason, _) in rules.items():
        by_reason.setdefault(reason, []).append(rule_id)

    for reason in sorted(named_reasons(_contract())):
        assert by_reason.get(reason), reason
        for rule_id in by_reason[reason]:
            assert re.match(r"^EG-[A-Z]+-\d{3}$", rule_id), rule_id


@requires_proxy
def test_the_denial_record_carries_everything_the_contract_says_it_does() -> None:
    """"the rule identifier, the method, the path, the resolved tier, the
    session, and the named reason" — read off the Go writer's own schema.
    """
    schema = DECISIONLOG_GO.read_text()
    for column in ("rule_id", "method", "path", "resolved_tier",
                   "session_id", "reason"):
        assert re.search(rf"^\s+{column}\s+TEXT NOT NULL", schema, re.M), column
    assert "CHECK (length(rule_id) > 0)" in schema, (
        "the contract says a denial with no rule identifier fails; the column "
        "no longer refuses one"
    )


@requires_proxy
def test_absolute_https_denial_carries_the_counter_q07_asks_about() -> None:
    rules = registry(RULES_GO.read_text())
    assert rules["EG-DEST-001"][0] == "absolute_https_denied"
    assert re.search(r"^\s+absolute_https_denied\s+INTEGER NOT NULL",
                     DECISIONLOG_GO.read_text(), re.M), (
        "the contract carries this counter deliberately (Q-07): if the reason "
        "dominates real traffic that is evidence for revisiting the posture"
    )


# ---------------------------------------------------------------------------
# The address-class stage, added at 4c788d3 and amended the same day.
# ---------------------------------------------------------------------------


@requires_proxy
def test_two_exemptible_classes_and_exactly_one_exemption() -> None:
    """The document's clause and the code's shape, tied together.

    `src/proxy/addresses_test.go` already asserts both structural properties
    from the Go side. What is new here is that the **contract still says so**:
    the clause and the code are one decision, and either drifting from the
    other is the failure.
    """
    text = _unwrapped(_contract())
    assert ONE_EXEMPTION_CLAUSE in text, (
        "the contract no longer carries the clause that keeps two exemptible "
        "classes from meaning one exemption each"
    )

    source = ADDRESSES_GO.read_text()
    members = re.search(
        r"var exemptibleClasses = map\[string\]bool\{(.*?)\}", source, re.DOTALL)
    assert members, "no exemptibleClasses map"
    classes = re.findall(r"(class\w+):\s*true", members.group(1))
    assert sorted(classes) == ["classLoopback", "classPrivate"], classes

    struct = re.search(r"type pinnedExemption struct \{(.*?)\n\}", source, re.DOTALL)
    assert struct, "no pinnedExemption struct"
    fields = [line for line in struct.group(1).strip().splitlines()
              if line.strip() and not line.strip().startswith("//")]
    assert len(fields) == 1, (
        f"pinnedExemption has {len(fields)} fields ({fields}). One exemption "
        "in total is held by there being nowhere to put a second address."
    )


@requires_proxy
def test_loopback_is_exemptible_and_link_local_is_not_by_any_path() -> None:
    source = ADDRESSES_GO.read_text()
    members = re.search(
        r"var exemptibleClasses = map\[string\]bool\{(.*?)\}", source, re.DOTALL)
    assert members
    body = members.group(1)
    assert "classLoopback" in body, (
        "the 2026-08-03 amendment extended the exemption to a declared "
        "loopback origin on the same terms as RFC1918"
    )
    for inexemptible in ("classLinkLocal", "classMetadata", "classUniqueLocal",
                         "classUnspecified"):
        assert inexemptible not in body, inexemptible


@requires_proxy
def test_the_denied_class_names_are_distinguishable_in_the_record() -> None:
    """"carrying the class that matched so a loopback denial and a link-local
    denial are distinguishable in the record".
    """
    source = ADDRESSES_GO.read_text()
    names = dict(re.findall(r'^\s*(class\w+)\s*=\s*"([a-z0-9_]+)"', source, re.M))
    assert len(names) >= 6, names
    assert len(set(names.values())) == len(names), (
        f"two classes share a name: {names}. A shared name is exactly the "
        "indistinguishability the contract's clause forbids."
    )
    assert "cloud_metadata" in names.values()
    assert "link_local" in names.values()
    assert "loopback" in names.values()


# ---------------------------------------------------------------------------
# The pipeline, and the one stage the contract numbers that is not a gate.
# ---------------------------------------------------------------------------


@requires_proxy
def test_the_contract_numbers_a_non_empty_distinct_stage_list() -> None:
    stages = pipeline_stages(_contract())
    assert len(stages) >= 8, stages
    assert len(set(stages)) == len(stages), f"duplicate stage heads: {stages}"


@requires_proxy
def test_every_registered_stage_is_described_by_the_contract() -> None:
    """The direction that catches an undocumented enforcement stage."""
    registered = registered_stage_names()
    assert len(registered) >= 6, registered
    _, undocumented = stage_correspondence(pipeline_stages(_contract()), registered)
    assert undocumented == set(), (
        f"the enforcement point registers stages the contract does not "
        f"describe: {sorted(undocumented)}"
    )


@requires_proxy
def test_exactly_one_contract_stage_has_no_gate_stage() -> None:
    """Finding 037, pinned so it cannot grow.

    Stage 4 (address class) is enforced at configuration load and on every
    dial, not as a per-request gate — under FR-016's single pinned address a
    gate stage would re-check one constant. Recording it as an expectation
    rather than a silence means a *second* stage slipping out of the pipeline
    fails here.
    """
    unbuilt, _ = stage_correspondence(
        pipeline_stages(_contract()), registered_stage_names())
    assert unbuilt == {"addressclass"}, (
        f"contract stages with no registered gate stage: {sorted(unbuilt)}. "
        "Only the address-class stage is expected to be absent, and only "
        "because it is enforced at dial time instead; anything else here is a "
        "stage the contract promises and the pipeline does not run."
    )


@requires_proxy
def test_every_stage_type_that_exists_is_wired_into_the_pipeline() -> None:
    """A stage that exists and is never registered enforces nothing.

    `defined_stage_names` reads the types; `registered_stage_names` reads
    `defaultStages` and the final constructor. A gate dropped from the
    registration list leaves its type behind, so the two sets diverge and this
    is where that shows — the correspondence arms above would not, because a
    contract stage would still have a matching *definition*.
    """
    defined = defined_stage_names()
    registered = registered_stage_names()
    assert len(defined) >= 7, defined
    assert defined == registered, (
        f"stage types that exist but are not registered: "
        f"{sorted(defined - registered)}; registered but not defined: "
        f"{sorted(registered - defined)}"
    )


@requires_proxy
def test_the_stage_correspondence_reports_a_planted_divergence() -> None:
    """The control on the two arms above, which both succeed by finding
    nothing. A stage removed from the pipeline and a stage added to it must
    each show up, or the pair is unfalsifiable.
    """
    contract = pipeline_stages(_contract())
    registered = registered_stage_names()

    unbuilt, _ = stage_correspondence(contract, registered - {"method"})
    assert unbuilt == {"addressclass", "method"}

    _, undocumented = stage_correspondence(contract, registered | {"shadowstage"})
    assert undocumented == {"shadowstage"}


@requires_proxy
def test_the_address_class_check_is_reachable_from_the_dialer_and_from_startup() -> None:
    """What discharges the contract's stage 4, named rather than assumed.

    Structural: the two call sites. The behavioural arm is
    `TestPinnedDialerRefusesDeniedClassOnTheAddressActuallyDialled` in
    `src/proxy/addresses_test.go`, which dials 169.254.169.254 and observes the
    refusal — this file does not restate it.
    """
    callers = {
        path.name for path in sorted(PROXY.glob("*.go"))
        if not path.name.endswith("_test.go")
        and path.name != "addresses.go"
        and "checkDialAddress(" in path.read_text()
    }
    assert callers == {"reoriginate.go", "main.go"}, (
        f"checkDialAddress is called from {sorted(callers)}. The contract's "
        "address-class stage is discharged by exactly two sites: the pinned "
        "dialer, on the value the kernel receives, and startup validation, so "
        "a proxy pinned into a denied class does not start."
    )
