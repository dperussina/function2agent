"""T080 — FR-016's address pinning, at admission, at host-and-port granularity.

FR-016 has three clauses and **this module is one of them, not all three**:

1.  *"Destinations MUST be pinned to specific addresses at configuration time,
    at host-and-port granularity."* — **here**.
2.  *"Names MUST NOT be re-resolved per request."* — **here**, as the property
    the pin makes structurally true, and in `src/proxy/addresses.go`
    (`checkDialAddress`) as the enforcement that refuses a dial to anything
    that is not a literal address.
3.  *"Name resolution MUST be unavailable from the execution environment or
    mediated entirely by the enforcement point."* — **not here**. That is a
    topology fact about the sandbox, asserted by INV-003's arm and by the
    compose file, and no Python object can make it true.

## The point of the pin, stated as the attack it forecloses

Resolving a name per request means the destination is chosen by whoever
answers the query at the moment of the request. An allowlist over *names* is
therefore an allowlist over a third party's future answers: the name passes
review, and a later answer sends the connection somewhere the reviewer never
saw. This is DNS rebinding when it is deliberate and a stale cache when it is
not, and both have the same shape — the reviewed thing and the connected thing
are different things.

Pinning collapses the two. The name is resolved **once**, at admission, in
front of the operator; from then on the address is data, and no later answer
from anywhere can move it.

## Host-and-port, and why the port is not an afterthought

FR-016 says host-**and**-port with the emphasis in the requirement's own text.
`src/proxy/destination.go` reads it strictly on the same ground: *"an
absolute-form target naming the right host on a different port is a different
destination."* A pin that fixed the host and let the port float would permit
reaching a different service on the same machine, which is most of the value
of the pin gone. `PinnedDestination` therefore has no default port and no
scheme-derived port — `parse` refuses an authority without an explicit one
rather than supplying 443, because a supplied default is a port nobody
reviewed.

## What "no per-request re-resolution" is, as a testable claim

It is an absence, and an absence is the easy thing to test wrongly: a test
asserting *"the resolver was called once"* passes if nothing ever resolved,
and a test asserting *"the resolver was not called during the request"* passes
against a module that never had a resolver. Both are satisfied by a broken
implementation.

The positive form is in three parts and the third is the one that matters:

- The pinned address **is used** — `dial_target()` returns it, and a request
  routed through the pin lands on it.
- A resolver answer that changes after pinning **does not** change where a
  request goes.
- **The changed answer would have changed it**, had it been consulted:
  pinning the same name again after the change yields the new address. Without
  this arm the second is vacuous, because a resolver whose answer never
  reaches anything satisfies it trivially.

`tests/contract/test_pinning.py` carries all three.

## The resolver is injected, and that is a design constraint rather than test dressing

`resolve` is a parameter with no default that reaches the network. The module
imports no socket library at all — a static arm asserts it — so there is
exactly one place a name can become an address, and it is a value the caller
passed in. A module that could resolve on its own would be one edit away from
resolving lazily, and lazily is per-request.
"""

from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Mapping, Sequence

from src.analysis.admission import ADMISSIBLE_STATES, AdmissionDecision, AdmissionError

#: A resolver: a name, and the addresses it currently answers with.
Resolver = Callable[[str], Sequence[str]]


class PinningError(AdmissionError):
    """A destination that could not be pinned as FR-016 requires."""


class NotAdmittedForPinning(PinningError):
    """Asked to pin the destination of a target FR-044 refused."""


class ReresolutionAttempted(PinningError):
    """Something asked for a name to be resolved after admission.

    Raised by `sealed_resolver`, which exists so that a re-resolution is a
    crash rather than a silent second answer. A code path that acquires one
    later fails loudly at the first request instead of quietly becoming
    correct-looking and unpinned.
    """


# `host:port` with an explicit port. A bracketed IPv6 literal is accepted in
# the bracket form only, since `::1:8080` is ambiguous and guessing is how a
# port ends up defaulted.
_AUTHORITY = re.compile(
    r"^(?:\[(?P<v6>[0-9A-Fa-f:.]+)\]|(?P<host>[^\[\]:/?#]+)):(?P<port>\d{1,5})$"
)


def _as_address(text: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    """The literal, or None. A separate function so the guard has one branch."""
    try:
        return ipaddress.ip_address(text)
    except ValueError:
        return None


@dataclass(frozen=True)
class PinnedDestination:
    """One destination, fixed at admission: a name, a port, and an address.

    Frozen, because a pin that can be mutated after review is not a pin. The
    address is a literal — `str(ipaddress.ip_address(...))` normalised — so
    that nothing downstream has a name it might be tempted to look up.
    """

    #: The name as configured. Kept for the operator's benefit and for the
    #: `Host` header; **never resolved again**.
    host: str
    port: int
    #: The literal address the name answered with at admission.
    address: str
    #: Which of the answers were available at pinning time, in the resolver's
    #: order. Recorded because *which one was chosen* is a fact the operator
    #: may need, and because a name with several answers is the case where a
    #: per-request resolver would silently round-robin.
    resolved_from: tuple[str, ...]
    pinned_at: float

    def __post_init__(self) -> None:
        if not self.host:
            raise PinningError("a pinned destination names a host")
        if not (1 <= self.port <= 65535):
            raise PinningError(
                f"port {self.port} is outside 1-65535. FR-016 pins at "
                "host-and-port granularity, and a port outside the range is "
                "not a port a connection could be made to."
            )
        parsed = _as_address(self.address)
        if parsed is None:
            raise PinningError(
                f"{self.address!r} is not a literal address. The whole point "
                "of pinning is that no name survives admission: a pin holding "
                "a name is a name something downstream will resolve, and it "
                "will resolve it per request. (FR-016)"
            )
        if str(parsed) != self.address:
            raise PinningError(
                f"{self.address!r} is a literal address written in a "
                f"non-normal form ({parsed} is the normal one). Two spellings "
                "of one address compare unequal, and the proxy's pinned-origin "
                "check is an equality comparison."
            )

    @property
    def family(self) -> int:
        return ipaddress.ip_address(self.address).version

    def dial_target(self) -> tuple[str, int]:
        """Where a connection actually goes. The address, never the name.

        This is the positive form of *"names MUST NOT be re-resolved per
        request"*: there is no code path from a request to a resolver because
        the thing a request is handed is already an address.
        """
        return (self.address, self.port)

    def authority(self) -> str:
        """The `host:port` the request should carry, which is the *name*.

        Deliberately different from `dial_target`. TLS certificate validation
        and virtual hosting are both keyed to the name, so the name has to
        survive — it just must not be what the connection is made to.
        """
        host = f"[{self.host}]" if ":" in self.host else self.host
        return f"{host}:{self.port}"

    def matches(self, host: str, port: int) -> bool:
        """FR-016's strict reading, mirroring `destination.go`'s.

        Host **and** port. The host comparison is case-insensitive because DNS
        names are; the port comparison is exact because ports are not.
        """
        return host.lower() == self.host.lower() and port == self.port

    def document(self) -> dict[str, Any]:
        return {
            "host": self.host,
            "port": self.port,
            "address": self.address,
            "resolved_from": list(self.resolved_from),
            "pinned_at": self.pinned_at,
            "basis": (
                "resolved once at admission (FR-016). The name is recorded "
                "for the request authority and is never resolved again; the "
                "address is what a connection is made to."
            ),
        }


def parse_authority(authority: str) -> tuple[str, int]:
    """`host:port` into its two parts, refusing an implicit port.

    **No default is supplied and that is the requirement rather than
    strictness for its own sake.** FR-016 pins host *and* port; a default
    port is a port the operator did not write and the reviewer did not read,
    and it is exactly the value that would silently differ between a config
    written for `https://` and a deployment listening on 8443.
    """
    match = _AUTHORITY.match(authority.strip())
    if not match:
        raise PinningError(
            f"{authority!r} is not `host:port` with an explicit port. FR-016 "
            "pins at host-and-port granularity, so the port is part of the "
            "destination and is not defaulted from a scheme: a defaulted port "
            "is one nobody reviewed. Write `api.example.com:443`, or "
            "`[2001:db8::1]:443` for an IPv6 literal."
        )
    host = match.group("v6") or match.group("host")
    port = int(match.group("port"))
    if not (1 <= port <= 65535):
        raise PinningError(f"port {port} in {authority!r} is outside 1-65535")
    return host, port


def pin(
    authority: str,
    *,
    resolve: Resolver,
    now: Callable[[], float],
    select: Callable[[Sequence[str]], str] | None = None,
) -> PinnedDestination:
    """Resolve a destination **once** and fix it.

    `resolve` has no default: see the module docstring. `select` chooses among
    several answers and defaults to the first, which is deterministic given
    the resolver's order — `min` would have been deterministic too and would
    have quietly changed which host a deployment talks to, so the first answer
    is kept and the choice is recorded on the pin rather than hidden in it.
    """
    host, port = parse_authority(authority)

    literal = _as_address(host)
    if literal is not None:
        # Already an address. Not resolved, and specifically not round-tripped
        # through the resolver: handing a literal to a resolver is a query
        # that can be answered, and a PTR-then-A round trip is a resolution
        # nobody asked for.
        return PinnedDestination(
            host=str(literal), port=port, address=str(literal),
            resolved_from=(str(literal),), pinned_at=now())

    answers = tuple(str(answer) for answer in resolve(host))
    if not answers:
        raise PinningError(
            f"{host!r} resolved to no addresses at admission, so there is "
            "nothing to pin. This fails now rather than deferring the "
            "resolution to the first request: a destination that cannot be "
            "pinned cannot be reviewed, and deferring it is precisely the "
            "per-request resolution FR-016 forbids."
        )

    chosen = (select or (lambda candidates: candidates[0]))(answers)
    try:
        normalised = str(ipaddress.ip_address(chosen))
    except ValueError as error:
        raise PinningError(
            f"the resolver answered {chosen!r} for {host!r}, which is not an "
            "address. A resolver that answers with a name has moved the "
            "resolution one hop further away rather than performing it."
        ) from error

    return PinnedDestination(
        host=host, port=port, address=normalised,
        resolved_from=answers, pinned_at=now())


def pin_for_admission(
    decision: AdmissionDecision,
    authority: str,
    *,
    resolve: Resolver,
    now: Callable[[], float],
) -> PinnedDestination:
    """Pin at admission, refusing a target FR-044 rejected.

    The ordering is the reason this lives beside the admission stages rather
    than in the runtime: *"at configuration time"* means before anything can
    make a request, and admission is the last moment at which that is
    structurally true.
    """
    if decision.state not in ADMISSIBLE_STATES:
        raise NotAdmittedForPinning(
            f"{decision.deployment_id} was not admitted (state "
            f"{decision.state}, criterion {decision.rule_id}); pinning a "
            "destination for a target that will never be called records a "
            "reviewed address for a deployment nobody reviewed."
        )
    return pin(authority, resolve=resolve, now=now)


def sealed_resolver(reason: str = "admission has completed") -> Resolver:
    """A resolver that refuses, for handing to anything past admission.

    The runtime is given this one. If some later code path acquires a resolver
    and calls it, the process raises instead of quietly answering — which
    turns "we do not re-resolve" from a property of the code as currently
    written into a property the code cannot violate without crashing.
    """

    def refuse(host: str) -> Sequence[str]:
        raise ReresolutionAttempted(
            f"something asked to resolve {host!r} after {reason}. FR-016: "
            "names MUST NOT be re-resolved per request. Whatever needs an "
            "address here should be reading the pin made at admission; if it "
            "genuinely needs a destination that was not pinned, that "
            "destination was never reviewed."
        )

    return refuse


@dataclass(frozen=True)
class PinnedRoute:
    """A pin plus the request-time routing decision, as one object.

    Exists so the *positive* claim has something to be made about: a route
    takes a request's intended authority and returns where the connection
    goes, and that answer comes from the pin. A test can then assert the
    address is used rather than asserting a resolver was not called.
    """

    destination: PinnedDestination

    def route(self, requested_authority: str | None = None) -> tuple[str, int]:
        """Where a request goes, optionally checking what it asked for.

        With no argument, the pin. With one, the pin after confirming the
        request asked for the pinned authority — a request naming anything
        else is refused rather than silently redirected onto the pin, because
        silently redirecting would make the pin a rewriter and hide a
        misconfiguration that the operator should see.
        """
        if requested_authority is not None:
            host, port = parse_authority(requested_authority)
            if not self.destination.matches(host, port):
                raise PinningError(
                    f"the request names {requested_authority!r} and the "
                    f"pinned destination is {self.destination.authority()!r}. "
                    "Host and port must both match (FR-016): the right host "
                    "on a different port is a different destination."
                )
        return self.destination.dial_target()


def pinned_policy_fragment(
    destinations: Iterable[PinnedDestination],
) -> Mapping[str, Any]:
    """The pins as the proxy reads them.

    `src/proxy/addresses.go`'s `checkDialAddress` refuses a dial address that
    is not a literal IP with a port, so this fragment's job is to be the thing
    that satisfies it — the Python side produces the literal, the Go side
    refuses anything else. **The two are not the same guard**: this one can be
    deleted and the proxy still refuses names; the proxy's can be deleted and
    this one still emits literals. Each covers a different failure, which is
    why both exist.
    """
    pins = tuple(destinations)
    seen: dict[tuple[str, int], str] = {}
    for destination in pins:
        key = (destination.host.lower(), destination.port)
        if key in seen and seen[key] != destination.address:
            raise PinningError(
                f"{destination.authority()} is pinned to two addresses "
                f"({seen[key]} and {destination.address}). Two pins for one "
                "authority means the destination is chosen at request time by "
                "whichever pin is consulted, which is the per-request "
                "variability the pin exists to remove."
            )
        seen[key] = destination.address
    return {
        "pinned_destinations": [destination.document() for destination in pins],
        "reresolution": "forbidden (FR-016)",
    }
