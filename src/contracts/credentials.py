"""T161 — two credential planes, typed so a mix is refused at construction.

FR-036: model-provider credentials and target credentials are held in two
separate planes. FR-050: neither is present in, or retrievable from, the
agent's execution environment.

This module names the planes and the holders. It does not inject. The Go
enforcement point already holds the target plane (`F2A_TARGET_CREDENTIAL`)
and injects it on re-origination; a second copy here would be a second
lifecycle for the same secret. The runtime may hold the provider plane.
Analysis, the sandbox, the execution environment, and the Phase 6
scheduler/manual/tick path hold neither. A session capability
(`X-F2A-Capability`) is not a credential plane.

The value is a `Secret` (T035). There is no second wrapper. This type adds
the plane and the holder, and construction refuses a combination the type
system would otherwise represent.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.contracts.secret import Secret

#: The one declared runtime key for the provider plane. Not a per-vendor
#: env name: `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` as implicit names in
#: the core path is provider-specific behaviour in the core (FR-037).
PROVIDER_KEY = "F2A_PROVIDER_CREDENTIAL"

#: Already held by the Go enforcement point. Named here so a Secret that
#: carries this name cannot be constructed as the runtime's provider
#: credential, and so the Python runtime cannot grow a second copy of
#: the injection.
TARGET_KEY = "F2A_TARGET_CREDENTIAL"

PLANE_PROVIDER = "provider"
PLANE_TARGET = "target"
PLANES = frozenset({PLANE_PROVIDER, PLANE_TARGET})

HOLDER_RUNTIME = "runtime"
HOLDER_ENFORCEMENT = "enforcement_point"
HOLDER_ANALYSIS = "analysis"
HOLDER_EXECUTION = "execution_environment"
HOLDER_SANDBOX = "sandbox"
HOLDER_SUPERVISOR = "supervisor"
#: Named residual, not a wiring. T141–T144's scheduler/manual/tick must
#: not hold the target credential or issue a capability. This slice
#: refuses the holder; it does not call `tick`.
HOLDER_SCHEDULER = "scheduler"
HOLDER_MANUAL = "manual"
HOLDER_TICK = "tick"

_KEY_FOR_PLANE = {
    PLANE_PROVIDER: PROVIDER_KEY,
    PLANE_TARGET: TARGET_KEY,
}

#: The only legal (plane, holder) pairs. A mix is a construction error,
#: not a comment.
ALLOWED_HOLDERS: frozenset[tuple[str, str]] = frozenset({
    (PLANE_PROVIDER, HOLDER_RUNTIME),
    (PLANE_TARGET, HOLDER_ENFORCEMENT),
})

#: Holders that may not hold either plane. Distinct from ALLOWED_HOLDERS
#: so emptying this set is a different plant from widening the pairs.
NEVER_HOLD: frozenset[str] = frozenset({
    HOLDER_ANALYSIS,
    HOLDER_EXECUTION,
    HOLDER_SANDBOX,
    HOLDER_SUPERVISOR,
    HOLDER_SCHEDULER,
    HOLDER_MANUAL,
    HOLDER_TICK,
})


class PlaneMixError(ValueError):
    """A Secret from one plane was offered as the other, or is not a plane."""


class HolderRefusedError(ValueError):
    """A holder that may not hold this plane (or either plane) was named."""


@dataclass(frozen=True)
class HeldCredential:
    """A `Secret` in one plane, held by one role.

    Construction is the check. There is no `reveal` here: the value leaves
    this type only through `Secret.reveal` at a greppable call site, and
    this module is not one.
    """

    secret: Secret
    plane: str
    holder: str

    def __post_init__(self) -> None:
        if not isinstance(self.secret, Secret):
            raise PlaneMixError(
                "a credential plane holds a Secret, not a bare value "
                "(FR-036)"
            )
        expected = _KEY_FOR_PLANE.get(self.plane)
        if expected is None:
            raise PlaneMixError(
                f"{self.plane!r} is not a credential plane. The planes are "
                f"{PLANE_PROVIDER} and {PLANE_TARGET} (FR-036). A session "
                "capability is not either."
            )
        if self.secret.name != expected:
            raise PlaneMixError(
                f"a Secret named {self.secret.name!r} is not the "
                f"{self.plane} plane. The {self.plane} plane is {expected}. "
                "Mixing the planes is refused at construction (FR-036)."
            )
        if self.holder in NEVER_HOLD:
            raise HolderRefusedError(
                f"{self.holder} may not hold a credential plane. The "
                "provider credential is held by the runtime; the target "
                "credential is held by the enforcement point. Neither "
                "reaches the execution environment (FR-050). A session "
                "capability is not a credential plane."
            )
        if (self.plane, self.holder) not in ALLOWED_HOLDERS:
            raise HolderRefusedError(
                f"{self.holder} may not hold the {self.plane} plane "
                "(FR-036)."
            )

    def fingerprint(self) -> str:
        """Which credential, not the value."""
        return self.secret.fingerprint()

    @property
    def name(self) -> str:
        """The configuration key. Never the value."""
        return self.secret.name


def hold(*, secret: Secret, plane: str, holder: str) -> HeldCredential:
    """Construct a held credential, or refuse a mix."""
    return HeldCredential(secret=secret, plane=plane, holder=holder)
