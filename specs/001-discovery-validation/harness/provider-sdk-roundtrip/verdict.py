"""SPIKE - E16. The result record and the round-trip measurement. Do not import from product code.

**What this measures, stated precisely, because the naive version of it is vacuous.**

"We echoed the bytes back and they were the same bytes" proves nothing — we
control both ends of that comparison. FR-037's actual failure mode is an
*adapter* dropping or mutating provider-opaque state on the way back out, which
is what finding 003 result 7 caught: ADK's LiteLLM adapter referenced xAI's
`encrypted_content` zero times under every counting rule.

So each arm measures four separate things and reports them separately:

1. ``opaque_state_present`` — did the provider emit an opaque reasoning field at
   all on this model and configuration? If not, the round-trip is untestable
   here and the arm says so rather than passing by default.
2. ``sdk_preserved`` — the field is hashed **on receipt** from the response
   object, and hashed again **after** it has been put through whatever
   structure the SDK requires for the next request. Equal hashes mean the
   SDK's own round-trip did not mutate it. This is the half an adapter breaks.
3. ``provider_accepted`` — the next request, carrying the re-injected state,
   returned successfully. A provider that validates its own opaque field
   (several do, via signature checks) rejects a corrupted one, so this is an
   independent check on 2 rather than a restatement of it.
4. ``chained`` — hop 2 ran with the id hop 1 returned, and the final answer is
   right. Capability, not transport.

An arm can pass 4 and fail 2 or 3. Finding 003 is the reason that distinction
is drawn: chained tool use worked on xAI *while* the opaque field was being
dropped, "so the gap did not bite at two hops on a trivial task."

**Environmental failures are separated from capability failures** and carry
``failure_kind``. Finding 003 had a dead credential that looked like a
capability result; this harness will not repeat that.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import time
from typing import Any


def digest(value: Any) -> str | None:
    """A stable hash of an opaque field, whatever shape it arrives in.

    bytes hash directly; str hashes as UTF-8; anything else is canonicalized
    through sorted-key JSON first so that dict ordering cannot masquerade as
    mutation.
    """
    if value is None:
        return None
    if isinstance(value, bytes):
        payload = value
    elif isinstance(value, str):
        payload = value.encode("utf-8")
    else:
        payload = json.dumps(value, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def digest_all(values: list[Any]) -> list[str]:
    """Per-field digests, order preserved. Several providers emit more than one."""
    return [d for d in (digest(v) for v in values) if d is not None]


@dataclasses.dataclass
class ArmResult:
    provider: str
    sdk: str
    sdk_version: str
    model: str
    credential_var: str
    credential_fp: str

    # The opaque field this provider is expected to carry, named explicitly so
    # a reader can check we looked for the right thing.
    opaque_field: str = ""

    ok: bool = False
    failure_kind: str | None = None  # "environmental" | "capability" | None
    error: str | None = None

    opaque_state_present: bool = False
    sdk_preserved: bool | None = None
    provider_accepted: bool | None = None
    chained: bool = False
    answer_correct: bool = False

    digests_in: list[str] = dataclasses.field(default_factory=list)
    digests_out: list[str] = dataclasses.field(default_factory=list)

    tool_calls: list[str] = dataclasses.field(default_factory=list)
    turns: int = 0
    final_text: str = ""

    input_tokens: int = 0
    output_tokens: int = 0

    # Populated only where the *provider* reports a cost. xAI's usage proto
    # carries `cost_in_usd_ticks`; the other three report tokens and leave the
    # conversion to a price table this harness does not have and will not
    # invent. None here means "not reported", never "zero".
    cost_usd_reported_by_provider: float | None = None

    elapsed_s: float = 0.0
    notes: list[str] = dataclasses.field(default_factory=list)

    def note(self, msg: str) -> None:
        self.notes.append(msg)

    def as_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


class Timer:
    def __enter__(self):
        self.t0 = time.time()
        return self

    def __exit__(self, *exc):
        self.elapsed = time.time() - self.t0
        return False


def emit(result: ArmResult) -> int:
    """Print one JSON object. Exit status is 0 for a completed arm.

    A capability failure is a *result*, not a harness error, so it still exits
    0 and still prints. Only an environmental failure — a dead credential, no
    network — is worth a non-zero status, because that one means nothing was
    measured.
    """
    print(json.dumps(result.as_dict(), indent=2, default=str))
    return 2 if result.failure_kind == "environmental" else 0
