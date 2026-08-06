"""T035 — a `Secret` with no serializer, so redaction is structural (FR-036).

Pulled forward into the enforcement-point slice because the supervisor and the
proxy both hold credentials in Phase 4, and a redaction *filter* added later
would be exactly the mitigation this type exists to replace: a filter has to be
remembered at every call site and a missing serializer cannot be forgotten.

The rule: there is no way to get the value out except `reveal()`, which is a
verb an author has to type. Every implicit path — `str`, `repr`, `format`,
`json.dumps`, `%`-formatting, f-strings, pickling, copying — yields the
redaction marker or raises.
"""

from __future__ import annotations

import hashlib
from dataclasses import fields, is_dataclass
from typing import Any, Mapping, NoReturn, Type

REDACTED = "<redacted:Secret>"


def _marker(name: str) -> str:
    """The redaction marker, naming the configuration key and not the value.

    A bare `<redacted:Secret>` is safe and useless: an operator reading a
    redacted trace of a session that used three credentials cannot tell which
    one was involved, so the marking makes the record unusable for the
    diagnosis it was kept for. The key *name* is not a credential — it is the
    environment variable an operator set — so carrying it costs nothing and
    recovers the diagnosis. Found by T040's marker test.
    """
    return f"<redacted:Secret {name}>" if name else REDACTED


class SecretSerializationError(TypeError):
    """Something tried to serialize a credential. That is always a defect."""


class Secret:
    """An opaque credential holder.

    >>> s = Secret("hunter2", name="F2A_TARGET_CREDENTIAL")
    >>> str(s)
    '<redacted:Secret F2A_TARGET_CREDENTIAL>'
    >>> f"{s}"
    '<redacted:Secret F2A_TARGET_CREDENTIAL>'
    >>> s.reveal()
    'hunter2'
    """

    __slots__ = ("_value", "_name")

    def __init__(self, value: str, *, name: str) -> None:
        if not isinstance(value, str):
            raise TypeError("Secret wraps a str")
        self._value = value
        self._name = name

    # --- the one way out -------------------------------------------------
    def reveal(self) -> str:
        """The value. Call sites are greppable; that is the point."""
        return self._value

    def fingerprint(self) -> str:
        """A stable handle that is not the credential.

        Twelve hex characters of SHA-256 — enough for a record to say *which*
        credential authenticated, not enough to be one. Same convention as the
        feature 001 harnesses.
        """
        return hashlib.sha256(self._value.encode("utf-8")).hexdigest()[:12]

    @property
    def name(self) -> str:
        """The configuration key it came from. Never the value."""
        return self._name

    def __bool__(self) -> bool:
        return bool(self._value)

    def __len__(self) -> int:
        # Length is a weak oracle on a short secret; refuse rather than leak it.
        raise SecretSerializationError(
            f"len() on Secret({self._name}) would disclose credential length"
        )

    # --- every implicit path is closed -----------------------------------
    def __str__(self) -> str:
        return _marker(self._name)

    def __repr__(self) -> str:
        return _marker(self._name)

    def __format__(self, spec: str) -> str:
        # The spec is discarded deliberately: `f"{secret:.4}"` would otherwise
        # truncate the marker, and a truncated marker is a marker that stops
        # looking like one.
        return _marker(self._name)

    def _refuse(self, *_a: Any, **_k: Any) -> NoReturn:
        raise SecretSerializationError(
            f"Secret({self._name}) has no serializer. If a credential value "
            "genuinely has to leave this process, call .reveal() at the exact "
            "line that needs it so the call site is greppable (FR-036)."
        )

    __reduce__ = _refuse
    __reduce_ex__ = _refuse
    __getstate__ = _refuse
    __copy__ = _refuse
    __deepcopy__ = _refuse
    for_json = _refuse
    to_json = _refuse
    __html__ = _refuse

    # Comparison is constant-time and never yields the value.
    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Secret):
            return NotImplemented
        import hmac

        return hmac.compare_digest(self._value, other._value)

    def __hash__(self) -> int:
        # Hash the fingerprint, not the value, so a Secret in a dict key does
        # not put the value into any hash-collision debug output.
        return hash(("Secret", self.fingerprint()))


def refuse_secrets(
    value: Any, path: str, *, raise_as: Type[Exception], destination: str
) -> None:
    """Refuse a `Secret` anywhere inside `value`. FR-036, once.

    **Why this lives beside the type rather than in each channel that carries
    one.** `src/runtime/trace.py` needs it for a span and `src/runtime/events.py`
    needs it for a caller-visible event, and the two are the same rule about the
    same type. Two copies are two chances for one of them to be relaxed, and the
    relaxation that matters is the same in both: a nesting shape the walk stops
    at. The rule about where a credential may not go belongs with the credential.

    Descends through mappings — **keys as well as values**, because
    `{Secret(...): "x"}` is a credential in the record just as much as a value
    is — through sequences, and through **nested dataclasses**, the last because
    a credential-bearing field is usually one dataclass hop from the object being
    checked rather than a raw mapping on it, and a scan that stopped at the first
    object walked past all of them.

    `raise_as` and `destination` are the caller's, so the refusal names the
    channel the author was writing to. A shared guard that raised one type would
    make every caller catch a stranger's exception, and a shared message would
    tell a reader to look at the wrong artifact.
    """
    if isinstance(value, Secret):
        raise raise_as(
            f"{path} holds a Secret. A credential must not reach "
            f"{destination} (FR-036); pass a reference, not the value."
        )
    if isinstance(value, Mapping):
        for key, item in value.items():
            refuse_secrets(key, f"{path}.<key>", raise_as=raise_as,
                           destination=destination)
            refuse_secrets(item, f"{path}.{key}", raise_as=raise_as,
                           destination=destination)
    elif is_dataclass(value) and not isinstance(value, type):
        for member in fields(value):
            refuse_secrets(getattr(value, member.name),
                           f"{path}.{member.name}", raise_as=raise_as,
                           destination=destination)
    elif isinstance(value, (list, tuple)):
        for item in value:
            refuse_secrets(item, f"{path}[]", raise_as=raise_as,
                           destination=destination)
