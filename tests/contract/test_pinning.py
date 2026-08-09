"""T080 — FR-016 address pinning, and the absence made positive.

The group that carries the requirement is *"the pin survives a changed
answer"*, and it is three assertions rather than one:

    A.  the pinned address is what a request is routed to;
    B.  changing the resolver's answer after pinning does not move it;
    C.  the changed answer WOULD have moved it — pinning again yields the new
        address.

C is the arm that makes B non-vacuous. Without it, a resolver whose answers
never reach anything passes B, and so does a module that resolves nothing at
all. Every "no re-resolution" test in this file is paired with the control
that shows the resolver was live.
"""

from __future__ import annotations

import ast

import pytest

from src.analysis import admission
from src.analysis.pinning import (
    PinnedDestination,
    PinnedRoute,
    PinningError,
    NotAdmittedForPinning,
    ReresolutionAttempted,
    parse_authority,
    pin,
    pin_for_admission,
    pinned_policy_fragment,
    sealed_resolver,
)


class MovingResolver:
    """A resolver whose answer can be changed, and which counts its calls.

    The count is *evidence about the resolver*, not the assertion: the tests
    assert where a request goes, and use the count only to show the resolver
    was reachable when the control arm needed it to be.
    """

    def __init__(self, answer: str) -> None:
        self.answer = answer
        self.calls: list[str] = []

    def __call__(self, host: str) -> list[str]:
        self.calls.append(host)
        return [self.answer]


def clock(start: float = 1_786_147_200.0):
    ticks = iter(range(10_000))
    return lambda: start + next(ticks)


# ---------------------------------------------------------------------------
# The requirement: the pin is used, and a changed answer does not move it.


def test_the_pinned_address_is_what_a_request_is_routed_to():
    """Arm A. The positive claim, stated before any absence is mentioned."""
    resolver = MovingResolver("203.0.113.7")
    destination = pin("api.example.com:443", resolve=resolver, now=clock())

    assert destination.dial_target() == ("203.0.113.7", 443)
    assert PinnedRoute(destination).route() == ("203.0.113.7", 443)
    assert PinnedRoute(destination).route("api.example.com:443") == (
        "203.0.113.7", 443)


def test_a_changed_answer_does_not_change_where_a_request_goes():
    """Arms B and C together, because B alone proves nothing.

    B: the resolver starts answering `198.51.100.9` after the pin is made,
    and three separate routings still land on `203.0.113.7`.

    C: the control. Pinning the same name again, with the same live resolver,
    yields `198.51.100.9` — so the changed answer was reachable and would
    have moved the destination had anything consulted it. Delete arm C and
    arm B passes against a resolver nobody ever wired up.
    """
    resolver = MovingResolver("203.0.113.7")
    route = PinnedRoute(pin("api.example.com:443", resolve=resolver, now=clock()))

    resolver.answer = "198.51.100.9"

    for _ in range(3):
        assert route.route("api.example.com:443") == ("203.0.113.7", 443)

    moved = pin("api.example.com:443", resolve=resolver, now=clock())
    assert moved.dial_target() == ("198.51.100.9", 443), (
        "the control failed: the resolver's new answer does not reach a "
        "fresh pin either, so the assertion above is vacuous"
    )


def test_the_pin_holds_when_the_resolver_would_now_refuse_outright():
    """A resolver that has become hostile, rather than merely different.

    The runtime is handed `sealed_resolver`, so this is the shape a real
    re-resolution takes: not a wrong answer but a raised exception. Routing
    through the pin must not touch it.
    """
    resolver = MovingResolver("203.0.113.7")
    route = PinnedRoute(pin("api.example.com:443", resolve=resolver, now=clock()))
    before = len(resolver.calls)

    sealed = sealed_resolver()
    assert route.route() == ("203.0.113.7", 443)
    assert len(resolver.calls) == before

    with pytest.raises(ReresolutionAttempted) as raised:
        sealed("api.example.com")
    assert "MUST NOT be re-resolved per request" in str(raised.value)


def test_the_module_cannot_resolve_a_name_by_itself():
    """The structural half of arm B: there is nowhere for a lazy resolve to go.

    A resolver reachable from inside the module is one edit from being called
    lazily, and lazily is per-request. The parameter has no default, and no
    resolution library is imported.
    """
    import src.analysis.pinning as module

    tree = ast.parse(open(module.__file__).read())
    imported = {
        alias.name.split(".")[0]
        for node in ast.walk(tree) if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        node.module.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    assert not (imported & {"socket", "asyncio", "dns", "urllib", "http"}), (
        f"{sorted(imported)} includes something that can resolve a name"
    )

    signature = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "pin"
    )
    resolve = next(a for a in signature.args.kwonlyargs if a.arg == "resolve")
    index = signature.args.kwonlyargs.index(resolve)
    assert signature.args.kw_defaults[index] is None, (
        "`resolve` acquired a default. A default resolver is one nobody "
        "passed and therefore one nobody reviewed."
    )


# ---------------------------------------------------------------------------
# Host AND port.


def test_the_port_is_part_of_the_destination():
    resolver = MovingResolver("203.0.113.7")
    destination = pin("api.example.com:443", resolve=resolver, now=clock())

    assert destination.matches("api.example.com", 443)
    assert not destination.matches("api.example.com", 8443), (
        "the right host on a different port is a different destination "
        "(FR-016, and src/proxy/destination.go reads it the same way)"
    )
    assert not destination.matches("other.example.com", 443)


def test_the_host_comparison_is_case_insensitive_and_the_port_is_not():
    destination = PinnedDestination(
        "API.Example.com", 443, "203.0.113.7", ("203.0.113.7",), 0.0)
    assert destination.matches("api.example.com", 443)
    assert not destination.matches("api.example.com", 444)


def test_an_authority_without_an_explicit_port_is_refused():
    """No default from the scheme. A defaulted port is one nobody reviewed."""
    for authority in ("api.example.com", "https://api.example.com", "::1"):
        with pytest.raises(PinningError) as raised:
            parse_authority(authority)
        assert "explicit port" in str(raised.value), authority


def test_an_ipv6_literal_is_accepted_in_bracket_form_only():
    assert parse_authority("[2001:db8::1]:443") == ("2001:db8::1", 443)
    with pytest.raises(PinningError):
        parse_authority("2001:db8::1:443")


def test_a_route_refuses_a_request_naming_a_different_destination():
    """Refused, not silently redirected onto the pin."""
    route = PinnedRoute(PinnedDestination(
        "api.example.com", 443, "203.0.113.7", ("203.0.113.7",), 0.0))
    with pytest.raises(PinningError) as raised:
        route.route("api.example.com:8443")
    assert "different destination" in str(raised.value)


# ---------------------------------------------------------------------------
# What a pin may hold.


def test_a_pin_holding_a_name_is_refused():
    """The failure the whole mechanism exists to prevent."""
    with pytest.raises(PinningError) as raised:
        PinnedDestination("api.example.com", 443, "api.example.com",
                          ("api.example.com",), 0.0)
    assert "resolve it per request" in str(raised.value)


def test_a_resolver_answering_with_a_name_is_refused():
    """One hop further away is not one hop resolved."""
    with pytest.raises(PinningError) as raised:
        pin("api.example.com:443", resolve=lambda h: ["cdn.example.net"],
            now=clock())
    assert "not an address" in str(raised.value)


def test_a_name_that_resolves_to_nothing_fails_at_admission():
    """Rather than deferring the resolution to the first request."""
    with pytest.raises(PinningError) as raised:
        pin("api.example.com:443", resolve=lambda h: [], now=clock())
    assert "deferring it is precisely the per-request resolution" in str(
        raised.value)


def test_a_non_normal_address_spelling_is_refused():
    """Because the proxy's pinned-origin check is an equality comparison."""
    with pytest.raises(PinningError) as raised:
        PinnedDestination("h", 443, "2001:0db8::0001", ("x",), 0.0)
    assert "non-normal form" in str(raised.value)


def test_a_port_outside_the_range_is_refused():
    with pytest.raises(PinningError):
        PinnedDestination("h", 0, "203.0.113.7", (), 0.0)
    with pytest.raises(PinningError):
        PinnedDestination("h", 70000, "203.0.113.7", (), 0.0)


def test_a_literal_destination_is_not_sent_to_the_resolver():
    """Handing a literal to a resolver is a query that can be answered."""
    resolver = MovingResolver("198.51.100.9")
    destination = pin("203.0.113.7:443", resolve=resolver, now=clock())
    assert destination.dial_target() == ("203.0.113.7", 443)
    assert resolver.calls == []


def test_every_answer_is_recorded_and_the_first_is_chosen():
    """A multi-answer name is where a per-request resolver round-robins."""
    destination = pin("api.example.com:443",
                      resolve=lambda h: ["203.0.113.7", "203.0.113.8"],
                      now=clock())
    assert destination.address == "203.0.113.7"
    assert destination.resolved_from == ("203.0.113.7", "203.0.113.8")
    assert destination.document()["resolved_from"] == [
        "203.0.113.7", "203.0.113.8"]


def test_the_selection_is_stable_across_two_pins_of_the_same_answers():
    """So a restart does not silently move the deployment to the other host."""
    answers = ["203.0.113.7", "203.0.113.8"]
    first = pin("api.example.com:443", resolve=lambda h: answers, now=clock())
    second = pin("api.example.com:443", resolve=lambda h: answers, now=clock())
    assert first.address == second.address


def test_the_authority_carries_the_name_and_the_dial_target_carries_the_address():
    """Both survive, and they are not the same thing.

    TLS validation and virtual hosting are keyed to the name, so a pin that
    threw the name away would break both — the requirement is that the name is
    not what the connection is made *to*, not that it disappears.
    """
    destination = pin("api.example.com:443",
                      resolve=lambda h: ["203.0.113.7"], now=clock())
    assert destination.authority() == "api.example.com:443"
    assert destination.dial_target() == ("203.0.113.7", 443)


def test_an_ipv6_pin_brackets_its_authority_and_reports_its_family():
    destination = pin("[2001:db8::1]:443", resolve=lambda h: [], now=clock())
    assert destination.authority() == "[2001:db8::1]:443"
    assert destination.dial_target() == ("2001:db8::1", 443)
    assert destination.family == 6


# ---------------------------------------------------------------------------
# Pinning happens at admission.


def decision(state: str) -> admission.AdmissionDecision:
    return admission.AdmissionDecision(
        deployment_id="parts-api",
        admitted=state in admission.ADMISSIBLE_STATES,
        state=state,
        criterion=admission.criterion_for(state),
        operations=({"operation_id": "op"},)
        if state in admission.ADMISSIBLE_STATES else (),
        evidence="fixture",
        specification_source="file:///fixture",
    )


def test_an_admitted_target_is_pinned():
    destination = pin_for_admission(
        decision(admission.PUBLISHED_NON_EMPTY), "api.example.com:443",
        resolve=lambda h: ["203.0.113.7"], now=clock())
    assert destination.dial_target() == ("203.0.113.7", 443)


@pytest.mark.parametrize(
    "state", sorted(set(admission.STATES) - admission.ADMISSIBLE_STATES))
def test_a_rejected_target_is_not_pinned(state):
    with pytest.raises(NotAdmittedForPinning):
        pin_for_admission(decision(state), "api.example.com:443",
                          resolve=lambda h: ["203.0.113.7"], now=clock())


def test_the_rejected_target_would_otherwise_have_pinned_cleanly():
    """The control for the parametrized refusal above.

    The same authority and the same resolver pin without complaint on an
    admitted decision, so the refusals are about admission and not about a
    destination that could not have been pinned anyway.
    """
    assert pin_for_admission(
        decision(admission.PUBLISHED_NON_EMPTY), "api.example.com:443",
        resolve=lambda h: ["203.0.113.7"], now=clock()).address == "203.0.113.7"


# ---------------------------------------------------------------------------
# The fragment the proxy reads.


def test_the_fragment_carries_literals_and_says_reresolution_is_forbidden():
    fragment = pinned_policy_fragment([
        pin("api.example.com:443", resolve=lambda h: ["203.0.113.7"],
            now=clock()),
    ])
    entry = fragment["pinned_destinations"][0]
    assert entry["address"] == "203.0.113.7"
    assert entry["host"] == "api.example.com"
    assert fragment["reresolution"] == "forbidden (FR-016)"
    assert "resolved once at admission" in entry["basis"]


def test_two_pins_for_one_authority_are_refused():
    """Otherwise the destination is chosen by whichever pin is consulted."""
    with pytest.raises(PinningError) as raised:
        pinned_policy_fragment([
            PinnedDestination("api.example.com", 443, "203.0.113.7", (), 0.0),
            PinnedDestination("API.example.com", 443, "198.51.100.9", (), 0.0),
        ])
    assert "chosen at request time" in str(raised.value)


def test_the_same_authority_pinned_to_the_same_address_twice_is_fine():
    """The control: the refusal above is about disagreement, not duplication."""
    fragment = pinned_policy_fragment([
        PinnedDestination("api.example.com", 443, "203.0.113.7", (), 0.0),
        PinnedDestination("api.example.com", 443, "203.0.113.7", (), 0.0),
    ])
    assert len(fragment["pinned_destinations"]) == 2


def test_the_same_host_on_two_ports_is_two_destinations_not_a_conflict():
    fragment = pinned_policy_fragment([
        PinnedDestination("api.example.com", 443, "203.0.113.7", (), 0.0),
        PinnedDestination("api.example.com", 8443, "198.51.100.9", (), 0.0),
    ])
    assert len(fragment["pinned_destinations"]) == 2
