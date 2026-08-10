"""T113 — the runtime's own default-deny egress plane (`src/runtime/egress.py`).

**An addition, and scored against the authority it actually has.** Constitution
Principle IV bullet 1 (v1.3.0) — "outbound network default-deny with an egress
allowlist meeting **all four** of the following", and "a configuration missing
any one of them does not satisfy this bullet". So there is an arm per term and
`test_no_runtime_egress_rule_cites_a_functional_requirement` refuses the module
the borrowed authority of an `FR-` citation; FR-014–FR-019 scope to the
execution environment and FR-050 is a credential-lifetime requirement, and both
have been reached for here before.

## The vacuity this file is built around

A default-deny plane passes every "was it refused?" arm by refusing everything,
including the traffic it exists to permit. Rule 8's shape exactly. So the
live-socket half runs **two arms differing in one variable**:

| Arm | Variable | Expected |
|---|---|---|
| `test_a_connection_to_an_unpinned_destination_is_refused_on_the_wire` | destination not in the pinned set | `EgressDenied`, naming `RTE-DEST-001` |
| `test_a_connection_to_the_pinned_destination_is_let_through_to_the_network` | the same address, pinned | the plane records `RTE-ALLOW-000` and whatever fails next is **not** the plane |

and the whole hook is controlled by
`test_the_same_connection_is_not_refused_when_no_plane_is_installed`, which is
the arm that fails if `EgressDenied` were coming from somewhere else.

The pinned arm connects to a `TEST-NET-3` address (RFC 5737 §4, reserved for
documentation and routed nowhere) with a short timeout. It is expected to fail —
what is asserted is *which layer* refused it.
"""

from __future__ import annotations

import ipaddress
import re
import socket
from pathlib import Path

import pytest

from src.runtime import egress
from src.runtime.egress import (
    DENIED_PREFIXES,
    INTERNET_FAMILIES,
    RTE_ADDRESS_CLASS_DENIED,
    RTE_ALLOWED,
    RTE_DESTINATION_NOT_PINNED,
    RTE_FAMILY_UNCLASSIFIED,
    RTE_NAME_NOT_AN_ADDRESS,
    RTE_PLANE_NOT_INSTALLED,
    RTE_PORT_NOT_PINNED,
    RTE_RESOLUTION_DENIED,
    RULES,
    Destination,
    EgressDenied,
    EgressError,
    classify,
    guarded,
    parse,
    pin,
    require_installed,
)

REPO = Path(__file__).resolve().parents[2]
RUNTIME = REPO / "src" / "runtime"
ADDRESSES_GO = REPO / "src" / "proxy" / "addresses.go"

#: RFC 5737 §4 — reserved for documentation, routed nowhere. Used so a live
#: connect attempt cannot reach anything real whatever the host's network is.
DOC_ADDRESS = "203.0.113.10"
DOC_PORT = 9


@pytest.fixture()
def plane():
    """A plane pinned to one documentation address, installed for one test."""
    with guarded(pin(f"{DOC_ADDRESS}:{DOC_PORT}")) as installed:
        yield installed


def _connect(host: str, port: int, timeout: float = 0.05) -> BaseException:
    """Attempt one connection and return whatever stopped it."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect((host, port))
    except BaseException as exc:  # noqa: BLE001 - the exception IS the result
        return exc
    finally:
        sock.close()
    raise AssertionError(f"the connection to {host}:{port} succeeded")


# ---------------------------------------------------------------------------
# Default-deny, on a real socket, with its control.
# ---------------------------------------------------------------------------


def test_a_connection_to_an_unpinned_destination_is_refused_on_the_wire(plane) -> None:
    exc = _connect("198.51.100.7", 443)
    assert isinstance(exc, EgressDenied), exc
    assert exc.decision.rule_id == RTE_DESTINATION_NOT_PINNED
    assert "198.51.100.7:443" in str(exc)


def test_a_connection_to_the_pinned_destination_is_let_through_to_the_network(
    plane,
) -> None:
    """The arm that fails if the plane simply refuses everything."""
    exc = _connect(DOC_ADDRESS, DOC_PORT)
    assert not isinstance(exc, EgressDenied), (
        f"the plane refused its own pinned destination: {exc}")
    allowed = [d for d in plane.decisions if d.allowed]
    assert [d.rule_id for d in allowed] == [RTE_ALLOWED]
    assert allowed[0].destination == f"{DOC_ADDRESS}:{DOC_PORT}"


def test_the_same_connection_is_not_refused_when_no_plane_is_installed() -> None:
    """The control on the hook itself.

    Without it, every refusal above is consistent with `EgressDenied` arriving
    from somewhere that is not this module.
    """
    exc = _connect("198.51.100.7", 443)
    assert not isinstance(exc, EgressDenied), (
        "a connection was refused by the egress plane with no plane installed; "
        "the arms above are measuring something else")


def test_connect_ex_is_refused_too_rather_than_returning_an_errno(plane) -> None:
    """`connect_ex` reports failure as a number and there is no number that
    means "policy refused". Returning one would be indistinguishable from the
    kernel's own refusal and would lose the rule identifier.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(0.05)
    try:
        with pytest.raises(EgressDenied) as caught:
            sock.connect_ex(("198.51.100.7", 443))
    finally:
        sock.close()
    assert caught.value.decision.rule_id == RTE_DESTINATION_NOT_PINNED


def test_the_plane_is_removed_when_the_block_raises() -> None:
    """A leaked patch is worse than no patch: it changes a component that
    never opted in, for the rest of the process.
    """
    before = socket.socket.connect
    with pytest.raises(RuntimeError, match="halfway"):
        with guarded(pin(f"{DOC_ADDRESS}:{DOC_PORT}")):
            assert socket.socket.connect is not before
            raise RuntimeError("halfway")
    assert socket.socket.connect is before


def test_a_second_plane_is_refused_rather_than_stacked(plane) -> None:
    with pytest.raises(EgressError, match="another egress plane"):
        pin(f"{DOC_ADDRESS}:{DOC_PORT}").install()


def test_a_caller_with_no_plane_installed_fails_closed() -> None:
    with pytest.raises(EgressDenied) as caught:
        require_installed()
    assert caught.value.decision.rule_id == RTE_PLANE_NOT_INSTALLED


def test_require_installed_returns_the_live_plane(plane) -> None:
    assert require_installed() is plane


# ---------------------------------------------------------------------------
# Term 1 — addresses pinned at configuration time, never names.
# ---------------------------------------------------------------------------


def test_a_name_cannot_be_pinned() -> None:
    with pytest.raises(EgressError, match="is a name, not an address"):
        pin("api.example.test:443")


def test_a_name_at_connect_time_is_denied_and_not_resolved(plane) -> None:
    decision = plane.evaluate(socket.AF_INET, ("api.example.test", 443))
    assert decision.rule_id == RTE_NAME_NOT_AN_ADDRESS
    assert not decision.allowed


def test_a_pinned_destination_holds_a_parsed_address_and_no_prefix() -> None:
    destination = parse("203.0.113.10:443")
    assert destination.address == ipaddress.ip_address("203.0.113.10")
    fields = set(Destination.__dataclass_fields__)
    assert fields == {"address", "port"}, (
        f"Destination has {sorted(fields)}. A prefix or a range field is the "
        "syntax in which term 1 gets widened by configuration, so there must "
        "not be one to write in."
    )


def test_an_ipv6_destination_round_trips_with_its_brackets() -> None:
    destination = parse("[2001:db8::1]:8443")
    assert destination.address == ipaddress.ip_address("2001:db8::1")
    assert destination.port == 8443
    assert str(destination) == "[2001:db8::1]:8443"


# ---------------------------------------------------------------------------
# Term 2 — host AND port, never host alone.
# ---------------------------------------------------------------------------


def test_a_destination_without_a_port_is_refused() -> None:
    with pytest.raises(EgressError, match="host-and-port granularity"):
        pin("203.0.113.10")


def test_the_right_address_on_the_wrong_port_is_denied_by_its_own_rule(plane) -> None:
    """The case a host-granular allowlist would have permitted, and the reason
    the constitution names it: the target and its database share a host.
    """
    decision = plane.evaluate(socket.AF_INET, (DOC_ADDRESS, 5432))
    assert decision.rule_id == RTE_PORT_NOT_PINNED, decision
    assert not decision.allowed


def test_the_wrong_address_is_a_different_rule_from_the_wrong_port(plane) -> None:
    """Distinguishable in the record, or the degradation to host-only is
    invisible in exactly the deployment where it matters.
    """
    wrong_port = plane.evaluate(socket.AF_INET, (DOC_ADDRESS, 5432))
    wrong_address = plane.evaluate(socket.AF_INET, ("198.51.100.7", DOC_PORT))
    assert wrong_port.rule_id != wrong_address.rule_id


# ---------------------------------------------------------------------------
# Term 3 — DNS denied.
# ---------------------------------------------------------------------------


def test_a_name_lookup_is_denied_while_the_plane_is_installed(plane) -> None:
    with pytest.raises(EgressDenied) as caught:
        socket.getaddrinfo("api.example.test", 443)
    assert caught.value.decision.rule_id == RTE_RESOLUTION_DENIED
    with pytest.raises(EgressDenied):
        socket.gethostbyname("api.example.test")


def test_a_numeric_lookup_still_works(plane) -> None:
    """The control on term 3: the resolver hook is refusing *names* and not
    everything. Without this, `create_connection` to a pinned address would be
    refused by the DNS arm and the permit arm above would be unreachable.
    """
    infos = socket.getaddrinfo(DOC_ADDRESS, DOC_PORT, socket.AF_INET,
                               socket.SOCK_STREAM)
    assert infos and infos[0][4][0] == DOC_ADDRESS


def test_the_resolver_hook_is_removed_with_the_plane() -> None:
    before = socket.getaddrinfo
    with guarded(pin(f"{DOC_ADDRESS}:{DOC_PORT}")):
        assert socket.getaddrinfo is not before
    assert socket.getaddrinfo is before


# ---------------------------------------------------------------------------
# Term 4 — denied classes, even on an allowlisted host.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("address,expected", [
    ("127.0.0.1", "loopback"),
    ("::1", "loopback"),
    ("10.1.2.3", "rfc1918_private"),
    ("172.16.0.1", "rfc1918_private"),
    ("192.168.1.1", "rfc1918_private"),
    ("169.254.1.1", "link_local"),
    ("169.254.169.254", "cloud_metadata"),
    ("fe80::1", "link_local"),
    ("fd00::1", "unique_local"),
    ("0.0.0.0", "unspecified"),
    ("::", "unspecified"),
    ("::ffff:127.0.0.1", "loopback"),
])
def test_every_denied_class_is_recognised(address, expected) -> None:
    assert classify(ipaddress.ip_address(address)) == expected


def test_a_public_address_is_in_no_denied_class() -> None:
    """The control: `classify` is not simply returning a class for everything."""
    for address in (DOC_ADDRESS, "198.51.100.7", "8.8.8.8", "2001:db8::1"):
        assert classify(ipaddress.ip_address(address)) is None, address


def test_the_metadata_address_cannot_be_pinned() -> None:
    with pytest.raises(EgressError, match="cloud_metadata"):
        pin("169.254.169.254:80")


def test_loopback_cannot_be_pinned_and_there_is_no_exemption_path() -> None:
    """Deliberately unlike `src/proxy/addresses.go`.

    The enforcement point exempts one declared origin in one of two classes
    because OD-08 co-locates the *target application*. A model provider is not
    co-located, so the circumstance that justified that exemption is absent and
    the mechanism is not copied. Any keyword that reintroduced it would show up
    here as a signature change.
    """
    for denied in ("127.0.0.1:8080", "192.168.1.10:443", "[::1]:443"):
        with pytest.raises(EgressError, match="has no exemption path"):
            pin(denied)


def test_a_denied_class_is_refused_at_connect_time_even_when_pinned() -> None:
    """"even on an allowlisted host" — the second of the two checks.

    `pin()` cannot produce this plane, which is the point: the destination is
    installed past the declaration-time check on purpose, so that what is
    measured is the connect-time check existing independently rather than
    restating the first one.
    """
    plane = egress.EgressPlane()
    smuggled = object.__new__(Destination)
    object.__setattr__(smuggled, "address", ipaddress.ip_address("169.254.169.254"))
    object.__setattr__(smuggled, "port", 80)
    plane.destinations = (smuggled,)

    decision = plane.evaluate(socket.AF_INET, ("169.254.169.254", 80))
    assert not decision.allowed
    assert decision.rule_id == RTE_ADDRESS_CLASS_DENIED
    assert "cloud_metadata" in decision.destination


def test_the_denied_class_table_agrees_with_the_enforcement_points() -> None:
    """Two statements of one policy, tied together rather than merged.

    They are stated twice because a Python module that parsed Go at import
    time would make the runtime's egress plane depend on a source file being on
    disk. The cost of two statements is drift, and this is what pays it.
    """
    if not ADDRESSES_GO.is_file():
        pytest.skip("the Go enforcement point is not present in this tree")
    go_source = ADDRESSES_GO.read_text()
    go_names = dict(re.findall(r'^\s*(class\w+)\s*=\s*"([a-z0-9_]+)"',
                               go_source, re.M))
    go_prefixes = {
        (prefix, go_names[const])
        for prefix, const in re.findall(
            r'\{netip\.MustParsePrefix\("([^"]+)"\), (class\w+)\}', go_source)
    }
    assert len(go_prefixes) >= 10, go_prefixes
    assert set(DENIED_PREFIXES) == go_prefixes, (
        "the runtime's denied-address table and the enforcement point's have "
        f"diverged.\n  only in the runtime: {sorted(set(DENIED_PREFIXES) - go_prefixes)}"
        f"\n  only in Go:          {sorted(go_prefixes - set(DENIED_PREFIXES))}"
    )


# ---------------------------------------------------------------------------
# Families, named rather than complemented.
# ---------------------------------------------------------------------------


def test_only_the_two_internet_families_can_be_permitted() -> None:
    assert INTERNET_FAMILIES == {socket.AF_INET, socket.AF_INET6}


def test_a_family_outside_the_named_set_is_denied_not_passed_through() -> None:
    plane = pin(f"{DOC_ADDRESS}:{DOC_PORT}")
    for family in (getattr(socket, "AF_UNIX", 1), socket.AF_PACKET
                   if hasattr(socket, "AF_PACKET") else 17):
        decision = plane.evaluate(family, ("/tmp/whatever", 0))
        assert not decision.allowed, family
        assert decision.rule_id == RTE_FAMILY_UNCLASSIFIED


# ---------------------------------------------------------------------------
# The authority this module rests on, and the namespace it mints into.
# ---------------------------------------------------------------------------


def test_no_runtime_egress_rule_cites_a_functional_requirement() -> None:
    """The guard against borrowing authority this addition does not have.

    FR-014 through FR-019 scope to the execution environment; FR-050 is a
    credential-lifetime requirement and has been mis-cited for an
    address-pinning property before. Every rule here cites the constitution or
    it is not a rule this module may carry.
    """
    for rule_id, rule in RULES.items():
        assert "Principle IV" in rule.term, (rule_id, rule.term)
        assert not re.search(r"\bFR-\d+", rule.term), (
            f"{rule_id} cites {rule.term!r}. This plane is an addition beyond "
            "what the specification requires; an FR citation here would be "
            "authority it does not have."
        )
    source = (RUNTIME / "egress.py").read_text()
    cited = set(re.findall(r"\bFR-\d{3}\b", source))
    assert cited <= {"FR-014", "FR-019", "FR-050", "FR-038", "FR-043", "FR-048",
                     "FR-049"}, cited
    assert "FR-050 is a credential" in source, (
        "the module no longer says why FR-050 is not its authority, which is "
        "the sentence that stops the next reader reaching for it"
    )


def test_the_runtime_egress_namespace_collides_with_no_other_registry() -> None:
    """`RTE-` is minted here. `EG-` is the enforcement point's, `FS-` the
    filesystem policy's, and `ADM-`, `DEP-`, `EFF-OP-`, `EFF-DENY-` are taken.
    """
    taken = ("EG-", "FS-", "ADM-", "DEP-", "EFF-OP-", "EFF-DENY-", "SBX-",
             "SV-", "REFAPP-")
    for rule_id in RULES:
        assert rule_id.startswith("RTE-"), rule_id
        assert re.match(r"^RTE-[A-Z]+-\d{3}$", rule_id), rule_id
        for prefix in taken:
            assert not rule_id.startswith(prefix), (rule_id, prefix)


def test_every_rule_is_reachable_and_every_reachable_rule_is_registered() -> None:
    """No registered rule is decoration and no emitted rule is unregistered."""
    source = (RUNTIME / "egress.py").read_text()
    emitted = set(re.findall(r"Decision\(\s*(?:True|False),\s*(RTE_\w+)", source))
    constants = {
        name for name in dir(egress)
        if name.startswith("RTE_") and getattr(egress, name) in RULES
    }
    assert emitted, "no Decision construction found; the parser is wrong"
    unregistered = {name for name in emitted if name not in constants}
    assert unregistered == set(), unregistered
    assert len(RULES) == len(constants) == 8


def test_a_decision_names_its_rule_its_reason_and_its_term(plane) -> None:
    decision = plane.evaluate(socket.AF_INET, ("198.51.100.7", 443))
    rendered = str(decision)
    assert decision.rule_id in rendered
    assert decision.reason in rendered
    assert decision.term in rendered


def test_the_decision_record_is_bounded() -> None:
    """An audit trail that grows without limit is the memory exhaustion
    FR-049 exists about, arriving through the audit trail.
    """
    plane = pin(f"{DOC_ADDRESS}:{DOC_PORT}")
    for index in range(plane.MAX_DECISIONS + 50):
        plane.evaluate(socket.AF_INET, ("198.51.100.7", 1 + index % 60000))
    assert len(plane.decisions) == plane.MAX_DECISIONS


# ---------------------------------------------------------------------------
# The seam. This is what makes the plane load-bearing before T058 exists.
# ---------------------------------------------------------------------------

#: Constructions that originate an outbound connection from CPython. Named
#: rather than inferred: a scan for "anything that looks like networking" would
#: match the words in a docstring and pass over a call it had never heard of.
OUTBOUND_CALLS = (
    r"\bsocket\.create_connection\b",
    r"\.connect\(",
    r"\.connect_ex\(",
    r"\bHTTPConnection\(",
    r"\bHTTPSConnection\(",
    r"\burlopen\(",
    r"\brequests\.",
    r"\bhttpx\.",
)

#: `egress.py` is the plane itself and holds the only permitted call sites.
#: `serving.py` binds an inbound listener, which originates nothing.
OUTBOUND_EXEMPT = {"egress.py"}

#: One **named symbol** whose spelling collides with a socket call and which
#: opens a file. Excluded by exact name and not by a rule about what `.connect`
#: usually means: `sqlite3.connect` is the DB-API's opener and the collision is
#: in the word, not in the behaviour. Anything else spelled `.connect(` is a
#: hit, so the exclusion cannot grow by accident — and
#: `test_the_outbound_scan_is_not_blinded_by_the_sqlite_exclusion` holds it.
NOT_OUTBOUND = ((r"\bsqlite3\.connect\(", "sqlite3_open_file("),)


def _outbound_sites(text: str) -> list[str]:
    hits: list[str] = []
    for number, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        scanned = line
        for pattern, replacement in NOT_OUTBOUND:
            scanned = re.sub(pattern, replacement, scanned)
        for pattern in OUTBOUND_CALLS:
            if re.search(pattern, scanned):
                hits.append(f"{number}: {stripped}")
                break
    return hits


def test_no_runtime_module_originates_a_connection_around_the_plane() -> None:
    """The interception point that exists **now** and binds T058 later.

    The plane is not installed by `src/runtime/main.py` — see that module's
    docstring for why — so what keeps it from being a mechanism nobody reaches
    is this: the runtime currently originates no outbound connection, and it
    cannot acquire one without failing here. When the provider transport
    arrives, the way to make this pass is to route it through `guarded()`.
    """
    offenders: list[str] = []
    scanned = 0
    for path in sorted(RUNTIME.rglob("*.py")):
        if path.name in OUTBOUND_EXEMPT:
            continue
        scanned += 1
        for site in _outbound_sites(path.read_text()):
            offenders.append(f"{path.relative_to(REPO)}:{site}")
    # The floor. This assertion succeeds by finding nothing, so the population
    # it looked at is the whole of its weight — and a mistyped `RUNTIME`, a
    # package rename or an `OUTBOUND_EXEMPT` that grew to cover the tree all
    # produce zero offenders out of zero files and read as green.
    # `test_the_outbound_scan_fires_on_a_planted_call` proves the matcher can
    # match; this proves the matcher was pointed at something.
    assert scanned >= 20, (
        f"the outbound scan covered {scanned} runtime modules, which is fewer "
        "than the tree has ever held. It is passing because it read almost "
        f"nothing, not because nothing was found. Check RUNTIME ({RUNTIME}) "
        "and OUTBOUND_EXEMPT."
    )
    assert offenders == [], (
        "outbound connection sites in the runtime that do not go through the "
        "egress plane:\n  " + "\n  ".join(offenders) +
        "\nRoute them through `src/runtime/egress.guarded()` with a pinned "
        "destination. Constitution Principle IV bullet 1: the process that "
        "puts attacker-influenceable text into a model is inside the scope of "
        "default-deny egress whether or not an FR enumerates it."
    )


def test_the_outbound_scan_fires_on_a_planted_call() -> None:
    """The control. The scan above succeeds by finding nothing, so without
    this it is indistinguishable from a scan that cannot find anything.
    """
    for planted in (
        "import socket\ns = socket.create_connection(('h', 1))\n",
        "conn.connect(('h', 1))\n",
        "import httpx\nhttpx.get('https://example.test')\n",
        "from urllib.request import urlopen\nurlopen('https://example.test')\n",
    ):
        assert _outbound_sites(planted), planted
    assert _outbound_sites("# conn.connect((1, 2)) in a comment\n") == []
    assert _outbound_sites("x = 1\ny = connect_to_database\n") == []


def test_the_outbound_scan_is_not_blinded_by_the_sqlite_exclusion() -> None:
    """The exclusion is one symbol, not a rule about the word `connect`."""
    assert _outbound_sites("db = sqlite3.connect(path)\n") == []
    assert _outbound_sites("sock.connect((host, port))\n")
    assert _outbound_sites("mysqlite3 = x\nfoo.connect((h, p))\n")
    # Both on one line: the socket call is still a hit after the scrub.
    assert _outbound_sites("sqlite3.connect(p); sock.connect((h, 1))\n")
