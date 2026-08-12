"""FR-058 — the per-result bound, its disclosure, and its retention location.

FR-058 bounds every result FR-004's two capabilities return *before* it enters
the model's context, and it is satisfied only when all three of its obligations
hold. Each one is a separate failure mode and each is implemented here rather
than left to a caller:

1. **The bound.** Stated in tokens of the model in force, required configuration
   with no default, and never above one twentieth of the context window — a
   configuration above that is **refused rather than clamped**.
2. **The disclosure.** In the result the model reads, not beside it. FR-058:
   *"a disclosure recorded anywhere other than in the result does not discharge
   this"*, because the model arrives at the result and at nothing else.
3. **The trace fields.** Seven, on every `tool_call` span and not only on the
   ones where the bound bit.

**The unit, and the one substitution FR-058 permits.** The bound is in tokens
because the context window is. Where the tokenizer of the model in force is not
available, a byte figure MAY stand in **only if derived so it can never admit
more tokens than the bound** — and an average bytes-per-token divisor is
disqualified by name, because minified JSON, base64, dense identifiers and
tabular numerics are exactly the content an average under-counts. The `4.0`
divisor a reader may be looking for is **not in this repository's own code** — it
is E17's, recorded in `findings/022-e7-tool-result-truncation-cap.md`, whose own
open question is whether 4.0 holds for the payloads it measured.
`conservative_byte_ceiling` exists so that it stays a finding about somebody
else's runtime rather than becoming an import. The safe derivation is one byte
per token: a
token cannot be shorter than a byte, so N bytes can never be more than N tokens.
It is conservative by a factor of three or four on ordinary prose, and that is
the correct direction for a bound.

**Why the disclosure is inside the bound rather than added to it.** The model
reads one string. A bound applied to the preview alone is exceeded by whatever
the notice costs, so the notice is measured and the preview is what fits in the
remainder. The alternative — bound the preview, append the notice — makes the
bound a number the implementation does not honour.

**Why retention is a store and not a path.** FR-058 requires the retention
location to be a declared location under FR-048 carrying **a declared bound of
its own**, unreadable from another session's environment, and not outliving the
session. A function returning a path establishes none of those. Returning a
reference without them would relocate an unbounded quantity from the transcript
onto a disk nothing bounds, which FR-058 calls its own defect relocated rather
than fixed.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

UNIT_TOKENS = "tokens"
UNIT_BYTES = "bytes"

# FR-058 names two dispositions and a contract is not the place to mint a third.
DISPOSITION_RETAINED = "retained"
DISPOSITION_UNRECOVERABLE = "unrecoverable"

# FR-058's ceiling, as a divisor of the context window.
CEILING_DIVISOR = 20


class BoundConfigError(RuntimeError):
    """A bound that cannot be established. Startup stops here."""


class RetentionError(RuntimeError):
    """The withheld bytes cannot be retained as FR-058 requires."""


class Tokenizer(Protocol):
    """The tokenizer of the model in force.

    `name` is carried so the trace can say *which* tokenizer counted, and
    `count` is the whole interface. Deliberately not the provider's SDK object:
    the bound has to be enforceable against a stub in a test, and a protocol is
    what makes the absent case (`None`) a declared state rather than an
    accident.
    """

    name: str

    def count(self, text: str) -> int: ...


def conservative_byte_ceiling(bound_tokens: int) -> int:
    """The largest byte count that cannot admit more than `bound_tokens` tokens.

    One byte per token. Not an approximation of a real ratio and not intended to
    be one: it is the floor of the ratio, which is the only derivation FR-058
    permits. A bytes-per-token *average* — the `4.0` finding 022 records against
    E17 — admits four times the bound on base64 and on minified numerics, which
    is exactly the content the bound exists for.
    """
    return bound_tokens


@dataclass(frozen=True)
class BoundFields:
    """FR-058's third obligation: the seven fields, on every `tool_call` span.

    `bound_applied` is True on every call the bound ran on, whether or not it
    bit. `bound_applied_and_bit` is the separate question, and the two are not
    one field: a bound recorded only where it bit cannot distinguish a result
    that fitted from a bound that was never applied.
    """

    bound_applied: bool
    bound_in_force: int
    unit: str
    byte_proxy: bool
    full_size: int
    admitted: int
    disposition: str
    reference: str | None = None
    tokenizer_name: str | None = None

    def __post_init__(self) -> None:
        if self.unit not in (UNIT_TOKENS, UNIT_BYTES):
            raise BoundConfigError(f"{self.unit!r} is not a declared unit")
        if self.disposition not in (DISPOSITION_RETAINED, DISPOSITION_UNRECOVERABLE):
            raise BoundConfigError(
                f"{self.disposition!r} is not one of FR-058's two dispositions"
            )
        if self.admitted > self.full_size:
            raise BoundConfigError(
                f"admitted ({self.admitted}) exceeds full size "
                f"({self.full_size}), which describes a result that never "
                "existed"
            )
        if self.disposition == DISPOSITION_UNRECOVERABLE and self.reference:
            raise BoundConfigError(
                "an unrecoverable remainder carries no reference; a reference "
                "to bytes nothing kept is worse than none"
            )
        if self.byte_proxy and self.unit != UNIT_BYTES:
            raise BoundConfigError(
                "byte_proxy is set but the unit says tokens. The field answers "
                "whether the bound was enforced in the unit it was written in, "
                "and the two halves have to agree."
            )

    @property
    def bound_applied_and_bit(self) -> bool:
        """Whether anything was actually withheld.

        The equality is the signal, which is why no third disposition value is
        invented: where nothing was withheld, `admitted` equals `full_size`.
        """
        return self.admitted < self.full_size

    def to_record(self) -> dict[str, Any]:
        return {
            "bound_applied": self.bound_applied,
            "bound_in_force": self.bound_in_force,
            "unit": self.unit,
            "byte_proxy": self.byte_proxy,
            "full_size": self.full_size,
            "admitted": self.admitted,
            "disposition": self.disposition,
            "reference": self.reference,
            "tokenizer": self.tokenizer_name,
        }


@dataclass(frozen=True)
class BoundedResult:
    """What the model reads, and what the span records."""

    text: str
    fields: BoundFields


class RetentionStore:
    """Where withheld bytes go: bounded, session-scoped, and temporary.

    Three properties, each of which FR-058 states and none of which a path
    argument would establish:

    - **Its own declared bound.** `max_bytes`, checked against what is already
      held, refusing rather than evicting. Eviction would make an earlier
      reference dangle while the trace still names it.
    - **Not readable from another session's environment.** A directory per
      session at mode 0o700, and `read()` refuses a reference outside this
      session's directory rather than following it. Both halves: the mode stops
      a guessed path and the check stops a handed-over one.
    - **It does not outlive the session.** `discard()` removes the directory,
      and the store refuses to retain anything afterwards.
    """

    def __init__(
        self,
        *,
        root: str | Path,
        session_id: str,
        max_bytes: int,
        declared_target: str | None = None,
        location_set: Any | None = None,
    ) -> None:
        if max_bytes <= 0:
            raise RetentionError(
                "the retention location needs a positive declared bound "
                "(FR-058). Without one the reference moves an unbounded "
                "quantity from the transcript onto a disk."
            )
        if (declared_target is None) != (location_set is None):
            raise RetentionError(
                "declared_target and location_set are supplied together or "
                "not at all; one without the other checks nothing."
            )
        if location_set is not None:
            declaration = location_set.declaring(declared_target)
            if declaration is None:
                raise RetentionError(
                    f"{declared_target!r} is not inside FR-048's declared "
                    "location set. FR-058 requires the withheld bytes to be "
                    "written inside it, so that the agent's next call on the "
                    "same surface can reach them at all."
                )
            if declaration.mode != "rw":
                raise RetentionError(
                    f"{declared_target!r} is declared read-only "
                    f"({declaration.rule_id}), so nothing can be retained "
                    "there. A retention target that cannot be written is the "
                    "unrecoverable branch wearing a reference."
                )
        self.session_id = session_id
        self.max_bytes = int(max_bytes)
        self.directory = Path(root).resolve() / session_id
        self.directory.mkdir(parents=True, exist_ok=True)
        # 0o700 rather than the default umask. The isolation clause is about
        # another session's *execution environment*, and a mode that depends on
        # the umask of whoever started the process is not a property.
        self.directory.chmod(0o700)
        self._discarded = False

    @property
    def bytes_held(self) -> int:
        if self._discarded or not self.directory.exists():
            return 0
        return sum(p.stat().st_size for p in self.directory.iterdir() if p.is_file())

    def retain(self, call_id: str, payload: bytes) -> str:
        """Write the withheld bytes and return the path that names them."""
        if self._discarded:
            raise RetentionError(
                f"session {self.session_id}'s retention location has been "
                "discarded. FR-058 requires it not to outlive the session."
            )
        if self.bytes_held + len(payload) > self.max_bytes:
            raise RetentionError(
                f"retaining {len(payload)} bytes would take session "
                f"{self.session_id} past its declared retention bound of "
                f"{self.max_bytes} ({self.bytes_held} already held). Refused "
                "rather than evicted: an eviction would leave an earlier "
                "reference dangling while the trace still names it. The "
                "caller's remaining option is FR-058's unrecoverable branch."
            )
        path = self.directory / f"{_safe(call_id)}.withheld"
        path.write_bytes(payload)
        path.chmod(0o600)
        return str(path)

    def read(self, reference: str) -> bytes:
        """Read back a reference this session wrote, and only one of those."""
        candidate = Path(reference).resolve()
        if candidate.parent != self.directory:
            raise RetentionError(
                f"{reference!r} is another session's retained result. FR-058 "
                "requires the retention location not to be readable from "
                "another session's execution environment, and following a "
                "handed-over path would be exactly that."
            )
        return candidate.read_bytes()

    def discard(self) -> None:
        """End the retention location with the session."""
        shutil.rmtree(self.directory, ignore_errors=True)
        self._discarded = True


def _safe(call_id: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in call_id) or "call"


@dataclass(frozen=True)
class ResultBound:
    """The configured bound, and the one place a result is held to it."""

    bound_tokens: int
    context_window_tokens: int
    tokenizer: Tokenizer | None = None

    def __post_init__(self) -> None:
        if self.context_window_tokens <= 0:
            raise BoundConfigError(
                "the context window of the model in force is required. It is "
                "not itself a bound — it is what makes FR-058's one-twentieth "
                "ceiling computable, so a bound cannot be checked without it."
            )
        if self.bound_tokens <= 0:
            raise BoundConfigError(
                f"the per-result bound is {self.bound_tokens}. FR-058 requires "
                "a bound; a non-positive one admits nothing and is a typo "
                "rather than a policy."
            )
        ceiling = self.context_window_tokens // CEILING_DIVISOR
        if self.bound_tokens > ceiling:
            raise BoundConfigError(
                f"the per-result bound of {self.bound_tokens} tokens exceeds "
                f"one twentieth of the {self.context_window_tokens}-token "
                f"context window, which is {ceiling}. **Refused, not clamped** "
                "— FR-058 says so directly, because clamping would let a "
                "deployment believe it configured a bound it did not get."
            )

    @property
    def ceiling(self) -> int:
        return self.context_window_tokens // CEILING_DIVISOR

    def _measure(self, text: str) -> int:
        if self.tokenizer is None:
            return len(text.encode("utf-8"))
        return self.tokenizer.count(text)

    def apply(
        self,
        body: str,
        *,
        retention: RetentionStore,
        call_id: str,
    ) -> BoundedResult:
        """Hold one result to the bound, disclosing the fact in the result.

        The order matters. The notice is composed first and measured, then the
        preview is fitted into what is left, then the two are joined and the
        result is measured again — because a preview fitted against an estimated
        notice length is a bound the implementation does not honour.
        """
        proxy = self.tokenizer is None
        # Derived from the same attribute `proxy` is, rather than from `proxy`
        # itself. The two say the same thing, but only this form is a narrowing
        # a checker can follow — `proxy` is a separate bool, so a reader had to
        # hold the correlation and nothing was checking they held it right.
        tokenizer_name = None if self.tokenizer is None else self.tokenizer.name
        unit = UNIT_BYTES if proxy else UNIT_TOKENS
        allowance = conservative_byte_ceiling(self.bound_tokens) if proxy \
            else self.bound_tokens
        full_size = self._measure(body)

        if full_size <= allowance:
            return BoundedResult(
                text=body,
                fields=BoundFields(
                    bound_applied=True,
                    bound_in_force=self.bound_tokens,
                    unit=unit,
                    byte_proxy=proxy,
                    full_size=full_size,
                    admitted=full_size,
                    disposition=DISPOSITION_RETAINED,
                    reference=None,
                    tokenizer_name=tokenizer_name,
                ),
            )

        # Over the bound. Try to retain the whole body — the *whole* body, not
        # the withheld tail, because the reference is what the agent's next call
        # filters or searches and a tail alone is not searchable in context.
        reference: str | None
        try:
            reference = retention.retain(call_id, body.encode("utf-8"))
            disposition = DISPOSITION_RETAINED
        except RetentionError:
            reference = None
            disposition = DISPOSITION_UNRECOVERABLE

        # The notice, then the room it leaves. **Rendered with `admitted` at its
        # largest possible value**, which is `full_size`: the reservation was
        # briefly made against `admitted=0` and the final notice carried a
        # four-digit number, so the returned string came back three bytes over
        # the bound. `admitted <= full_size` always, so a notice rendered with
        # `full_size` is never shorter than the one actually returned.
        notice = _notice(
            full_size=full_size, admitted=full_size, unit=unit,
            reference=reference, bound=self.bound_tokens,
        )
        room = allowance - self._measure(notice)
        if room <= 0:
            # The notice alone reaches the bound. The disclosure wins: a
            # bounded result that reads as a complete one MUST NOT be produced,
            # and a preview with no notice is exactly that.
            preview = ""
        else:
            preview = self._fit(body, room)
        admitted = self._measure(preview)

        text = _notice(
            full_size=full_size, admitted=admitted, unit=unit,
            reference=reference, bound=self.bound_tokens,
        ) + preview
        return BoundedResult(
            text=text,
            fields=BoundFields(
                bound_applied=True,
                bound_in_force=self.bound_tokens,
                unit=unit,
                byte_proxy=proxy,
                full_size=full_size,
                admitted=admitted,
                disposition=disposition,
                reference=reference,
                tokenizer_name=tokenizer_name,
            ),
        )

    def _fit(self, body: str, room: int) -> str:
        """The longest prefix of `body` measuring no more than `room`.

        A binary search over the *measured* length rather than an arithmetic
        estimate. An estimate is where a bytes-per-token average would come back
        in through the side door: `body[:room * 4]` is that average, spelled
        differently.
        """
        if self.tokenizer is None:
            return body.encode("utf-8")[:room].decode("utf-8", errors="ignore")
        low, high = 0, len(body)
        while low < high:
            middle = (low + high + 1) // 2
            if self.tokenizer.count(body[:middle]) <= room:
                low = middle
            else:
                high = middle - 1
        return body[:low]


def _notice(
    *, full_size: int, admitted: int, unit: str, reference: str | None, bound: int
) -> str:
    """FR-058's second obligation, as the first thing the model reads.

    Four things, all of them in the result: that it is bounded, the full size,
    how much was admitted, and either the reference or that the remainder is
    unrecoverable. First rather than last because a model that stops reading has
    read the disclosure.
    """
    where = (
        f"The withheld remainder is retained at {reference} — the next call on "
        "this surface can filter, count or search that path, and the bytes need "
        "not enter this transcript."
        if reference is not None else
        "The withheld remainder is **unrecoverable**: it could not be retained, "
        "so it is gone rather than elsewhere."
    )
    return (
        f"[bounded result — this is NOT the complete output]\n"
        f"full size: {full_size} {unit}; admitted: {admitted} {unit}; "
        f"per-result bound: {bound} tokens.\n"
        f"{where}\n"
        f"--- admitted portion follows ---\n"
    )
