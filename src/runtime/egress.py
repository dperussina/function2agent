"""T113 — the runtime's own default-deny egress plane, pinned by address.

## This is an ADDITION, and here is exactly what it rests on

**Not FR-014 through FR-019.** Those scope to the *execution environment* — the
sandbox and the one proxy in front of it — and the runtime process is not in
that scope. Citing them here would be citing a requirement for a property it
does not state.

**Not FR-050.** FR-050 is a credential-*lifetime* requirement with four layers
(opaque handle, lease row, held descriptor in the network namespace,
resume-renews-rather-than-reissues). It has been mis-cited for egress before and
it says nothing about pinning an address.

**Constitution Principle IV, bullet 1 — "outbound network default-deny with an
egress allowlist meeting all four of the following"** (v1.3.0). The principle
binds directly and its scope is the combination of untrusted input and
authority, not one named component; the process that puts attacker-influenceable
text into a model is inside that scope whether or not a functional requirement
enumerates it. [`plan.md`](../../specs/002-spec-aware-agent-runtime/plan.md)
records this as one of **two additions beyond what the specification requires**,
in the Principle IV section, and marking it as an addition rather than
manufacturing a requirement is the house style (`pids.max` under T103 is the
precedent).

## The four terms, and where each is enforced

The constitution says a configuration **missing any one** of these does not
satisfy the bullet, so all four are implemented and none is optional.

| Term | Mechanism here |
|---|---|
| 1. addresses pinned at configuration time, never names re-resolved per request | `Destination` holds a parsed `ip_address`; `pin()` refuses a name outright, and a `connect` whose sockaddr carries a name is `RTE-NAME-001` |
| 2. host **and** port granularity, never host alone | `Destination` has no constructor without a port, and a right-address/wrong-port connect is its own rule, `RTE-PORT-001`, so degradation to host-only is visible in the record rather than silent |
| 3. DNS denied or proxied | `getaddrinfo` and `gethostbyname` are refused for any non-numeric host while the plane is installed (`RTE-DNS-001`) |
| 4. loopback, RFC1918, link-local and the cloud metadata address denied **even on an allowlisted host** | `DENIED_CLASSES`, checked when a destination is declared *and* again at connect time, so an allowlist entry in a denied class is refused twice |

**This plane has no exemption path, and that is a deliberate difference from
`src/proxy/addresses.go`.** The enforcement point exempts one declared origin in
one of two classes because **OD-08** co-locates the *target application* with
the deployment, so the ordinary topology puts the target on RFC1918 or loopback.
A model provider is not co-located with anything. Building the exemption here
would be copying a mechanism without the circumstance that justified it.

## What this does NOT do, stated so a green test is not over-read

**It is not installed by `src/runtime/main.py`.** Two reasons, and the second is
the one that decides it. First, there is nothing to pin: the provider transport
is T058 and does not exist, so a pinned address today would be a value nobody
dials — and, under FR-043, an unvalidated one. Second, `main()` is called
directly by the test suite and returns; a process-wide `socket` patch installed
there and not removed would outlive the call and reach every later test, which
is a live hazard traded for no coverage.

What holds the seam instead is a **static interception point that exists now**:
`tests/contract/test_runtime_egress.py` asserts that no module under
`src/runtime/` opens an outbound client socket except this one. When T058 adds a
provider transport, that scan fails, and the way to make it pass is to route the
transport through `guarded()`. The plane binds a caller that does not exist yet
by refusing to let one arrive unrouted.

**It is a process-local patch, not a kernel control.** A subprocess does not
inherit it and native code that bypasses CPython's `socket` module is not
intercepted. The kernel-level statement about the *sandbox* is the proxy's and
the network namespace's; this is the runtime's own plane and its guarantee stops
at this interpreter.
"""

from __future__ import annotations

import ipaddress
import socket
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Iterator, Mapping, Sequence

# Rule identifiers. `RTE-` — runtime egress. Deliberately **not** `EG-`, which
# is the enforcement point's registry (`src/proxy/rules.go`): one namespace
# across two registries makes a rule identifier in a record ambiguous, and the
# reader of a record has no way to disambiguate after the fact. `ADM-`, `DEP-`,
# `FS-`, `EFF-OP-` and `EFF-DENY-` are taken by admission, deputy inspection,
# the filesystem policy and the effect rules.
RTE_ALLOWED = "RTE-ALLOW-000"
RTE_DESTINATION_NOT_PINNED = "RTE-DEST-001"
RTE_PORT_NOT_PINNED = "RTE-PORT-001"
RTE_NAME_NOT_AN_ADDRESS = "RTE-NAME-001"
RTE_RESOLUTION_DENIED = "RTE-DNS-001"
RTE_ADDRESS_CLASS_DENIED = "RTE-ADDR-001"
RTE_FAMILY_UNCLASSIFIED = "RTE-FAMILY-001"
RTE_PLANE_NOT_INSTALLED = "RTE-PLANE-001"


@dataclass(frozen=True)
class Rule:
    """A named reason and the term it discharges.

    `term` is a **constitution** citation and never an `FR-` identifier. A test
    asserts that, because the one thing this module must not do is borrow
    authority from a requirement that does not state the property — FR-050 in
    particular has been mis-cited for exactly this before.
    """

    reason: str
    term: str


TERM_PINNED = "Principle IV bullet 1 term 1 (addresses pinned at configuration time)"
TERM_HOST_AND_PORT = "Principle IV bullet 1 term 2 (host and port granularity)"
TERM_DNS = "Principle IV bullet 1 term 3 (DNS denied or proxied)"
TERM_CLASSES = "Principle IV bullet 1 term 4 (denied classes, even on an allowlisted host)"
TERM_DEFAULT_DENY = "Principle IV bullet 1 (outbound network default-deny)"

RULES: Mapping[str, Rule] = {
    RTE_ALLOWED: Rule("allowed", TERM_PINNED),
    RTE_DESTINATION_NOT_PINNED: Rule("destination_not_pinned", TERM_DEFAULT_DENY),
    RTE_PORT_NOT_PINNED: Rule("port_not_pinned", TERM_HOST_AND_PORT),
    RTE_NAME_NOT_AN_ADDRESS: Rule("name_not_a_pinned_address", TERM_PINNED),
    RTE_RESOLUTION_DENIED: Rule("resolution_denied", TERM_DNS),
    RTE_ADDRESS_CLASS_DENIED: Rule("address_class_denied", TERM_CLASSES),
    RTE_FAMILY_UNCLASSIFIED: Rule("address_family_unclassified", TERM_DEFAULT_DENY),
    RTE_PLANE_NOT_INSTALLED: Rule("plane_not_installed", TERM_DEFAULT_DENY),
}

# Class names match `src/proxy/addresses.go`'s so that a runtime denial and an
# enforcement-point denial for the same reason read the same in a record.
# `tests/contract/test_runtime_egress.py` asserts the two tables agree; they are
# stated twice because a Python module that parsed Go at import time would make
# the runtime's egress plane depend on a source file being on disk.
CLASS_LOOPBACK = "loopback"
CLASS_PRIVATE = "rfc1918_private"
CLASS_LINK_LOCAL = "link_local"
CLASS_UNIQUE_LOCAL = "unique_local"
CLASS_METADATA = "cloud_metadata"
CLASS_UNSPECIFIED = "unspecified"

CLOUD_METADATA = ipaddress.ip_address("169.254.169.254")

DENIED_PREFIXES: tuple[tuple[str, str], ...] = (
    ("127.0.0.0/8", CLASS_LOOPBACK),
    ("::1/128", CLASS_LOOPBACK),
    ("10.0.0.0/8", CLASS_PRIVATE),
    ("172.16.0.0/12", CLASS_PRIVATE),
    ("192.168.0.0/16", CLASS_PRIVATE),
    ("169.254.0.0/16", CLASS_LINK_LOCAL),
    ("fe80::/10", CLASS_LINK_LOCAL),
    ("fc00::/7", CLASS_UNIQUE_LOCAL),
    ("0.0.0.0/32", CLASS_UNSPECIFIED),
    ("::/128", CLASS_UNSPECIFIED),
)

_NETWORKS = tuple(
    (ipaddress.ip_network(prefix), name) for prefix, name in DENIED_PREFIXES)

#: The address families this plane evaluates and can permit. **Named, never a
#: complement.** Every other family — `AF_UNIX` included — is *denied*, not
#: passed through. The family space belongs to the platform and grows with it,
#: so "anything that is not AF_UNIX leaves the host" is the reading that reports
#: containment holding on a host where it does not. Default-deny over an open
#: set means the closed set is the one that is named.
INTERNET_FAMILIES: frozenset[int] = frozenset({socket.AF_INET, socket.AF_INET6})


class EgressError(RuntimeError):
    """A destination this plane cannot accept as a declaration."""


class EgressDenied(OSError):
    """An outbound connection the plane refused.

    An `OSError` because that is what a caller of `socket.connect` is written
    to handle, and a refusal that arrives as an unrelated exception type gets
    turned into a crash report rather than into a denial an operator reads.
    It carries its rule identifier so the refusal names what produced it.
    """

    def __init__(self, decision: "Decision") -> None:
        super().__init__(str(decision))
        self.decision = decision


def classify(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> str | None:
    """The denied class `address` belongs to, or `None`.

    Knows nothing about allowlists: this is the statement of what is denied,
    kept apart from the statement of what may be reached, so the second cannot
    quietly edit the first.
    """
    if address.version == 6 and address.ipv4_mapped is not None:
        address = address.ipv4_mapped
    if address == CLOUD_METADATA:
        return CLASS_METADATA
    for network, name in _NETWORKS:
        if address.version == network.version and address in network:
            return name
    return None


@dataclass(frozen=True)
class Destination:
    """One pinned destination: an address **and** a port.

    There is no constructor that omits the port and no field that holds a
    prefix, so term 2 cannot be degraded to host-only and term 1 cannot be
    widened into a range by configuration. Both are properties of the type.
    """

    address: ipaddress.IPv4Address | ipaddress.IPv6Address
    port: int

    def __post_init__(self) -> None:
        if not isinstance(self.address, (ipaddress.IPv4Address, ipaddress.IPv6Address)):
            raise EgressError(
                f"{self.address!r} is not a parsed address. A pinned "
                "destination holds an address resolved at configuration time; "
                "a name here would be re-resolved per request, which is the "
                "defeat term 1 names."
            )
        if not (0 < self.port <= 65535):
            raise EgressError(
                f"{self.port!r} is not a port. Term 2 requires host *and* "
                "port granularity: where a target and its database share a "
                "host, a host-granular allowlist permits the database "
                "connection and defeats the requirement by way of its remedy."
            )
        denied = classify(self.address)
        if denied is not None:
            raise EgressError(
                f"{self.address} is in denied class {denied}, and this plane "
                "has no exemption path. The enforcement point exempts one "
                "declared origin because OD-08 co-locates the target "
                "application; a model provider is not co-located, so the "
                "circumstance that justified that exemption is absent here."
            )

    def matches(self, address: object, port: int) -> bool:
        return self.address == address and self.port == port

    def __str__(self) -> str:
        host = (f"[{self.address}]" if self.address.version == 6
                else str(self.address))
        return f"{host}:{self.port}"


@dataclass(frozen=True)
class Decision:
    """One disposition, allow or deny alike.

    Recorded for permits as well as refusals, for FR-038's reason: a permit
    resolved by the wrong rule is the case an attribution has to be able to
    find, and it looks exactly like a permit by the right one unless the rule
    is on the record.
    """

    allowed: bool
    rule_id: str
    destination: str

    @property
    def reason(self) -> str:
        return RULES[self.rule_id].reason

    @property
    def term(self) -> str:
        return RULES[self.rule_id].term

    def __str__(self) -> str:
        verb = "allowed" if self.allowed else "denied"
        return (f"outbound connection to {self.destination} {verb} by "
                f"{self.rule_id} ({self.reason}) — {self.term}")


def parse(spec: str) -> Destination:
    """`"203.0.113.10:443"` or `"[2001:db8::1]:443"` into a `Destination`.

    A name is refused here rather than resolved. That refusal *is* term 1: the
    address an allowlist holds must be the one an operator pinned, and a name
    accepted at this boundary is a name something re-resolves later.
    """
    text = spec.strip()
    if text.startswith("["):
        host, _, port = text.partition("]")
        host = host[1:]
        port = port.lstrip(":")
    else:
        host, _, port = text.rpartition(":")
    if not host or not port:
        raise EgressError(
            f"{spec!r} is not an address and a port. Term 2 pins at "
            "host-and-port granularity, so a destination with no port is not "
            "a destination this plane can hold."
        )
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        raise EgressError(
            f"{host!r} is a name, not an address. Term 1 requires addresses "
            "pinned at configuration time and never names re-resolved per "
            "request: a re-resolved name can be re-pointed at loopback or at "
            "the database. Resolve it once, out of band, and pin the result."
        ) from None
    try:
        number = int(port)
    except ValueError:
        raise EgressError(f"{port!r} is not a port number") from None
    return Destination(address=address, port=number)


class EgressPlane:
    """Default-deny over `socket`, with an explicit pinned allowlist.

    Not a dataclass and not frozen, because a plane records decisions and
    tracks whether it is installed. The **allowlist** is a tuple assigned once
    and never mutated by any method here; the tests that install a denied-class
    destination reach past that on purpose, to show the connect-time class
    check is a second check rather than a restatement of the declaration-time
    one.
    """

    #: Bounded, because a record that grows without limit is the memory
    #: exhaustion FR-049 exists about, arriving through the audit trail.
    MAX_DECISIONS = 1024

    def __init__(self, destinations: Sequence[Destination] = ()) -> None:
        self.destinations: tuple[Destination, ...] = tuple(destinations)
        self.decisions: list[Decision] = []
        self._lock = threading.Lock()
        self._saved: dict[str, Any] = {}

    # -- evaluation ------------------------------------------------------

    def evaluate(self, family: int, sockaddr: Any) -> Decision:
        """The disposition for one connect attempt. No side effect but the record."""
        decision = self._evaluate(family, sockaddr)
        with self._lock:
            self.decisions.append(decision)
            if len(self.decisions) > self.MAX_DECISIONS:
                del self.decisions[:-self.MAX_DECISIONS]
        return decision

    def _evaluate(self, family: int, sockaddr: Any) -> Decision:
        if family not in INTERNET_FAMILIES:
            return Decision(False, RTE_FAMILY_UNCLASSIFIED, f"family={family}")

        try:
            host, port = sockaddr[0], int(sockaddr[1])
        except (TypeError, IndexError, ValueError):
            return Decision(False, RTE_FAMILY_UNCLASSIFIED, repr(sockaddr))

        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            return Decision(False, RTE_NAME_NOT_AN_ADDRESS, f"{host}:{port}")
        if address.version == 6 and address.ipv4_mapped is not None:
            address = address.ipv4_mapped

        target = f"{address}:{port}"

        # Term 4 before the allowlist, so an allowlist entry in a denied class
        # is refused rather than honoured. "Even on an allowlisted host" is the
        # constitution's own wording and this is the ordering that implements it.
        denied = classify(address)
        if denied is not None:
            return Decision(False, RTE_ADDRESS_CLASS_DENIED, f"{target} ({denied})")

        for pinned in self.destinations:
            if pinned.matches(address, port):
                return Decision(True, RTE_ALLOWED, target)
        # Term 2's own record: the address is pinned and the port is not, which
        # is exactly the case a host-granular allowlist would have permitted.
        if any(pinned.address == address for pinned in self.destinations):
            return Decision(False, RTE_PORT_NOT_PINNED, target)
        return Decision(False, RTE_DESTINATION_NOT_PINNED, target)

    def check(self, family: int, sockaddr: Any) -> None:
        decision = self.evaluate(family, sockaddr)
        if not decision.allowed:
            raise EgressDenied(decision)

    def resolution_denied(self, host: object) -> EgressDenied:
        return EgressDenied(Decision(False, RTE_RESOLUTION_DENIED, str(host)))

    # -- installation ----------------------------------------------------

    @property
    def installed(self) -> bool:
        return bool(self._saved)

    def install(self) -> None:
        """Patch `socket` so a connection cannot be made around the plane."""
        if self._saved:
            raise EgressError("this plane is already installed")
        if _current() is not None:
            raise EgressError(
                "another egress plane is installed. Two planes would each "
                "believe they were the interception point and neither would "
                "be; the second is refused rather than stacked."
            )

        plane = self
        self._saved = {
            "connect": socket.socket.connect,
            "connect_ex": socket.socket.connect_ex,
            "getaddrinfo": socket.getaddrinfo,
            "gethostbyname": socket.gethostbyname,
        }
        saved = self._saved

        def connect(sock: socket.socket, address: Any) -> Any:
            plane.check(sock.family, address)
            return saved["connect"](sock, address)

        def connect_ex(sock: socket.socket, address: Any) -> Any:
            # Raises rather than returning an errno. `connect_ex` reports
            # failure as a number, and there is no number that means "policy
            # refused"; returning EPERM would be indistinguishable from the
            # kernel's own refusal and would lose the rule identifier.
            plane.check(sock.family, address)
            return saved["connect_ex"](sock, address)

        def getaddrinfo(host: Any, port: Any, *args: Any, **kwargs: Any) -> Any:
            _require_numeric(plane, host)
            return saved["getaddrinfo"](host, port, *args, **kwargs)

        def gethostbyname(host: Any) -> Any:
            _require_numeric(plane, host)
            return saved["gethostbyname"](host)

        # Both codes, because both errors fire on one line and `method-assign`
        # alone suppressed only the first. The replacement's signature is
        # deliberately wider than `socket`'s, which is the `assignment` half.
        socket.socket.connect = connect          # type: ignore[method-assign,assignment]
        socket.socket.connect_ex = connect_ex    # type: ignore[method-assign,assignment]
        socket.getaddrinfo = getaddrinfo         # type: ignore[assignment]
        socket.gethostbyname = gethostbyname     # type: ignore[assignment]
        _set_current(self)

    def uninstall(self) -> None:
        if not self._saved:
            return
        socket.socket.connect = self._saved["connect"]            # type: ignore[method-assign]
        socket.socket.connect_ex = self._saved["connect_ex"]      # type: ignore[method-assign]
        socket.getaddrinfo = self._saved["getaddrinfo"]           # type: ignore[assignment]
        socket.gethostbyname = self._saved["gethostbyname"]       # type: ignore[assignment]
        self._saved = {}
        _set_current(None)


def _require_numeric(plane: EgressPlane, host: Any) -> None:
    """Term 3. A resolver reachable from here exfiltrates without ever
    completing a connection to a blocked destination, which is why the
    constitution calls it a defeat of the two terms above it.

    `None` and the empty string are the loopback/any-address forms rather than
    names, and they are refused too: the plane holds no destination they could
    match, so allowing the lookup would only produce an address the connect
    hook then denies, with the lookup itself unrecorded.
    """
    if isinstance(host, (bytes, bytearray)):
        host = host.decode("ascii", "replace")
    try:
        ipaddress.ip_address(str(host))
    except ValueError:
        raise plane.resolution_denied(host) from None


_CURRENT: list[EgressPlane | None] = [None]
_CURRENT_LOCK = threading.Lock()


def _current() -> EgressPlane | None:
    with _CURRENT_LOCK:
        return _CURRENT[0]


def _set_current(plane: EgressPlane | None) -> None:
    with _CURRENT_LOCK:
        _CURRENT[0] = plane


def pin(*specs: str) -> EgressPlane:
    """The production constructor: a plane over declared address:port strings.

    Every term is enforced through `parse` and `Destination`, so there is no
    path from here to a plane holding a name, a prefix, a portless entry or a
    denied-class address.
    """
    return EgressPlane([parse(spec) for spec in specs])


@contextmanager
def guarded(plane: EgressPlane) -> Iterator[EgressPlane]:
    """Install for the duration of a block and remove afterwards.

    The removal is in a `finally`, because a plane left installed by a raising
    caller would patch the interpreter for everything after it — and a leaked
    patch is worse than no patch, since it silently changes a component that
    never opted in.
    """
    plane.install()
    try:
        yield plane
    finally:
        plane.uninstall()


def require_installed() -> EgressPlane:
    """The fail-closed entry for a caller about to originate a connection.

    T058's provider transport calls this rather than assuming a plane is up.
    An unpinned outbound call from the runtime is the state this whole module
    exists to make impossible, and "nobody installed it" is the ordinary way
    that state arrives.
    """
    plane = _current()
    if plane is None:
        raise EgressDenied(Decision(
            False, RTE_PLANE_NOT_INSTALLED, "no destination evaluated"))
    return plane
