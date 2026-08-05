"""T051 — the write-ahead intent journal (T-07, FR-007, `data-model.md` §2.3).

Keyed `(session_id, turn_index, step_index)`, with an idempotency key per
effectful step. **The intent is committed before the effect and the outcome
after it**, and the ordering is the mechanism rather than a convention the
caller follows.

**What the ordering buys, and what it deliberately does not.** After a
`SIGKILL` — no unwind, no `finally`, no flush — a resume reader has only these
rows. Three states are reachable and each has one reading:

| rows present            | reading                      | consequence on resume |
| ----------------------- | ---------------------------- | --------------------- |
| nothing                 | the step never started       | run it                |
| intent only             | it *may* have run            | see below             |
| intent and outcome      | it finished, and this is how | never run it again    |

The middle row is why the order is this way round and not the other. It is
ambiguous, and the ambiguity is safe: something that may have happened is
treated as expensive rather than as absent. The order that would remove the
ambiguity — outcome first — is not available, because the outcome is not known
until after the effect.

**The middle row is also why there are two ways to record an intent.** A resumed
attempt re-running such a step is not writing a *new* intent; the row it needs is
already there. `intend` refuses a second intent, because within one attempt a
second one is a loop defect. `intend_once` tolerates one whose idempotency key
matches and refuses one whose key differs, which is the retry the middle row
calls for. Collapsing the two into a flag was considered and rejected: the two
callers are entitled to different answers, and a default would give one of them
the wrong one silently. **A real crash found this**, not review —
`tests/integration/test_resume_sigkill.py`'s mid-step arm resumed a turn whose
tool intent was on disk and the resume itself raised.

What is **not** reachable is an outcome with no intent, and `commit_outcome`
refuses to create one. A journal that accepted an orphan outcome would have a
second way to record a step, one that says nothing about whether the effect
preceded it, and no reader could tell the two apart afterwards.

**Why uniqueness lives in the store.** `Repository.create_table`'s docstring
gives the reason and this is the case it is about: *"a resumed one after a crash
shares nothing with the first"*. The second attempt to record a step comes from
a **different process**, so an in-process guard guards nothing. Recording an
outcome twice is precisely the repeat FR-007 forbids, so it is refused by a
unique index.

**Turn indexes are never handed back out.** `next_turn_index` is one past the
highest journalled turn, whether or not that turn completed. Reusing an
abandoned turn's index would re-issue its model call, and a model call that may
already have reached the provider is a duplicate charge against a live account.
The cost of not reusing it is a gap in the reconstructed transcript, which is
recoverable by reading this table; the cost of reusing it is not recoverable at
all. `src/runtime/resume.py` reports the gaps as `abandoned` rather than hiding
them.

**FR-037's opaque state is a column, not a payload field.** The payload is JSON
and JSON is an interpretation, which FR-037 forbids applying to provider state.
A payload containing bytes is refused with a message naming the column, because
the plausible mistake is putting it in the dict the caller already has.
"""

from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import dataclass
from typing import Any, Mapping

from src.contracts.repository import Repository, UniquenessError

TABLE = "turn_journal"

# The two rows a step can have. A closed set, enumerated, and read as an
# enumeration everywhere below — see `_completeness`.
KIND_INTENT = "intent"
KIND_OUTCOME = "outcome"
KINDS: frozenset[str] = frozenset({KIND_INTENT, KIND_OUTCOME})

# The step kinds. Both are effectful: one spends money, the other runs a tool.
STEP_MODEL_CALL = "model_call"
STEP_TOOL_CALL = "tool_call"
STEP_KINDS: frozenset[str] = frozenset({STEP_MODEL_CALL, STEP_TOOL_CALL})

# The model call is step 0 of its turn, and the tool calls it produced follow
# it. They cannot share a position: the model call is what *declared* them, so a
# reader that found them at the same index could not order the two.
MODEL_STEP_INDEX = 0


def tool_step_index(declared_index: int) -> int:
    """The step index for a tool call at the provider's declared position."""
    if declared_index < 0:
        raise JournalError(
            f"declared index {declared_index} is negative; it is a position in "
            "the turn (src/runtime/dispatch.py)"
        )
    return declared_index + 1


class JournalError(RuntimeError):
    """A step that cannot be journalled as described."""


def idempotency_key(
    session_id: str, turn_index: int, step_index: int, effect_id: str
) -> str:
    """The key an effectful step carries, derived from its coordinates alone.

    **Nothing that changes between attempts goes into it.** A key built from a
    clock, a uuid or a process id is a *new* key on the retry, which is the same
    as having no key: the whole purpose is that the retry of a step presents the
    identity the first attempt did.

    `effect_id` is the effect's own name — the provider's `call_id` for a tool
    call — so that two calls at the same coordinates in two different sessions
    do not collide and a caller cannot accidentally reuse one call's key for
    another's.
    """
    material = "\x00".join(
        (session_id, str(turn_index), str(step_index), effect_id))
    return "idem:sha256:" + hashlib.sha256(material.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class JournalStep:
    """One step as the table holds it: at most one intent and one outcome."""

    session_id: str
    turn_index: int
    step_index: int
    step_kind: str
    idempotency_key: str
    effectful: bool
    intent: Mapping[str, Any] | None
    outcome: Mapping[str, Any] | None
    provider_state: bytes | None
    intended_at: float | None
    completed_at: float | None

    @property
    def is_complete(self) -> bool:
        """True only for the one state that means *this finished*.

        Stated as a membership test rather than as `outcome is not None` so
        that it reads the same way as `_completeness`, which is where the
        enumeration is enforced.
        """
        return self.outcome is not None and self.completed_at is not None


def _completeness(kinds: frozenset[str]) -> bool:
    """Is a step with these rows complete? Enumerated, never complemented.

    `tools/README.md`: a rule of the form *"anything but intent means done"*
    fails open on the first value nobody anticipated, and this table will gain
    kinds. So the yes-state is named and everything unrecognised raises.
    """
    unrecognised = kinds - KINDS
    if unrecognised:
        raise JournalError(
            f"unrecognised journal kind {sorted(unrecognised)} in "
            f"{TABLE}. The declared set is {sorted(KINDS)}. This is refused "
            "rather than read as 'not an intent, so done': a classifier stated "
            "as a complement fails open on the first value nobody anticipated, "
            "and here failing open means re-running a step that already ran or "
            "skipping one that did not."
        )
    return KIND_OUTCOME in kinds


class TurnJournal:
    """The runtime's write-ahead journal over `turn_journal`."""

    def __init__(self, repository: Repository) -> None:
        self.repo = repository
        self.table = TABLE
        # Held across the read-then-write in `commit_outcome`. The repository's
        # own lock covers a single statement; this covers the pair, so two
        # threads in one process cannot both find no outcome and both write one.
        # Across processes the unique index is what refuses the second.
        self._lock = threading.Lock()
        self.repo.create_table(TABLE, {
            "session_id": "text not null",
            "turn_index": "int not null",
            "step_index": "int not null",
            "kind": "text not null",
            "step_kind": "text not null",
            "idempotency_key": "text not null",
            "effectful": "int not null",
            "payload": "text not null",
            # FR-037: opaque bytes, in their own column, never in `payload`.
            # Nullable because a provider that returned no state is different
            # from one that returned empty bytes.
            "provider_state": "blob",
            "at": "real not null",
        }, unique=[["session_id", "turn_index", "step_index", "kind"]])

    # -- the two commit points ---------------------------------------------

    def intend(
        self,
        *,
        session_id: str,
        turn_index: int,
        step_index: int,
        step_kind: str,
        effect_id: str,
        effectful: bool,
        payload: Mapping[str, Any],
        at: float,
    ) -> str:
        """Record what is about to happen, and return the step's key.

        Called **before** the effect. Returns the idempotency key so the caller
        passes it on to whatever performs the effect rather than deriving it a
        second time — two derivations are two chances to disagree.
        """
        self._check_position(turn_index, step_index)
        if step_kind not in STEP_KINDS:
            raise JournalError(
                f"{step_kind!r} is not a declared step kind "
                f"({sorted(STEP_KINDS)})."
            )
        if not effectful:
            raise JournalError(
                f"a {step_kind} step declared itself not effectful. A "
                "model call spends money and a tool call acts; both are "
                "effectful, and a flag a caller may set either way on those is "
                "decoration an auditor would read as a fact."
            )
        if not effect_id:
            raise JournalError(
                "an effectful step needs the effect's own identity (the "
                "provider's call_id for a tool call). Without it two calls at "
                "one position share a key."
            )
        key = idempotency_key(session_id, turn_index, step_index, effect_id)
        self._insert(
            session_id=session_id, turn_index=turn_index, step_index=step_index,
            kind=KIND_INTENT, step_kind=step_kind, idempotency_key=key,
            effectful=effectful, payload=payload, provider_state=None, at=at)
        return key

    def intend_once(
        self,
        *,
        session_id: str,
        turn_index: int,
        step_index: int,
        step_kind: str,
        effect_id: str,
        effectful: bool,
        payload: Mapping[str, Any],
        at: float,
    ) -> str:
        """`intend`, for a step that may already have been intended once.

        **This is the retry path, and it is a separate method rather than a flag
        on `intend`.** The two callers want different things and only one of them
        is entitled to tolerance. A first attempt writing a second intent at one
        position is a loop defect, and `intend` refuses it. A *resumed* attempt
        finding an intent with no outcome is looking at the one ambiguous row the
        module docstring's table describes — the step may have run — and it is
        supposed to run the step again. Re-deriving the intent for it would be a
        second write of a row that already says the right thing.

        **What is still refused is a different effect at the same coordinates.**
        The tolerance is keyed on the idempotency key, which is exactly what the
        key is for: it says *this is the same step retried*, and a mismatch says
        the position now holds a different call. Tolerating that would let a
        resumed attempt inherit an intent belonging to somebody else's effect and
        commit its outcome against it, which is worse than either a duplicate or
        a refusal — an outcome recorded under the wrong identity, with nothing
        afterwards able to tell.

        Returns the key either way, so a caller cannot branch on whether a write
        happened. Whether the row is new is not information the caller has any
        legitimate use for; acting on it would mean two code paths where the
        journal is supposed to have collapsed the difference.
        """
        self._check_position(turn_index, step_index)
        key = idempotency_key(session_id, turn_index, step_index, effect_id)
        with self._lock:
            existing = self._row(
                session_id, turn_index, step_index, KIND_INTENT)
            if existing is None:
                return self.intend(
                    session_id=session_id, turn_index=turn_index,
                    step_index=step_index, step_kind=step_kind,
                    effect_id=effect_id, effectful=effectful,
                    payload=payload, at=at)
            if str(existing["idempotency_key"]) != key:
                raise JournalError(
                    f"({session_id!r}, turn {turn_index}, step {step_index}) "
                    f"already holds an intent under a different idempotency "
                    f"key. Two different effects are claiming one position, so "
                    "neither can be retried here: the existing key was derived "
                    "from another effect's identity, and committing this one's "
                    "outcome against it would record the result under the "
                    "wrong name."
                )
            return key

    def commit_outcome(
        self,
        *,
        session_id: str,
        turn_index: int,
        step_index: int,
        payload: Mapping[str, Any],
        at: float,
        provider_state: bytes | None = None,
    ) -> None:
        """Record what happened. Called **after** the effect.

        Refuses a step with no intent. That refusal is the write-ahead half:
        without it the table could hold an outcome that was never preceded by
        an intent, and nothing afterwards could tell that row from one that was.
        """
        self._check_position(turn_index, step_index)
        with self._lock:
            intent = self._row(session_id, turn_index, step_index, KIND_INTENT)
            if intent is None:
                raise JournalError(
                    f"({session_id!r}, turn {turn_index}, step {step_index}) "
                    "has no intent row, so its outcome cannot be committed. "
                    "The intent is written before the effect; an outcome "
                    "arriving without one means either the effect ran "
                    "unjournalled or the coordinates are wrong, and both are "
                    "worth stopping for."
                )
            self._insert(
                session_id=session_id, turn_index=turn_index,
                step_index=step_index, kind=KIND_OUTCOME,
                step_kind=intent["step_kind"],
                idempotency_key=intent["idempotency_key"],
                effectful=bool(intent["effectful"]), payload=payload,
                provider_state=provider_state, at=at)

    # -- reads -------------------------------------------------------------

    def steps(self, session_id: str) -> tuple[JournalStep, ...]:
        """Every step of a session, in `(turn_index, step_index)` order."""
        rows = self.repo.select(TABLE, where={"session_id": session_id})
        grouped: dict[tuple[int, int], list[dict[str, Any]]] = {}
        for row in rows:
            grouped.setdefault(
                (int(row["turn_index"]), int(row["step_index"])), []).append(row)
        return tuple(
            self._step(session_id, turn, step, grouped[(turn, step)])
            for turn, step in sorted(grouped)
        )

    def step(
        self, session_id: str, turn_index: int, step_index: int
    ) -> JournalStep | None:
        for candidate in self.steps(session_id):
            if (candidate.turn_index, candidate.step_index) == (turn_index, step_index):
                return candidate
        return None

    def is_step_complete(
        self, session_id: str, turn_index: int, step_index: int
    ) -> bool:
        """Did this step finish? The question a resumed process actually asks."""
        found = self.step(session_id, turn_index, step_index)
        return found is not None and found.is_complete

    def next_turn_index(self, session_id: str) -> int:
        """One past the highest journalled turn. See the module docstring.

        Read off the table on every call. A cached number here would be finding
        006's defect in a new place: the count a resume depends on living
        somewhere a crash can lose.
        """
        rows = self.repo.select(TABLE, where={"session_id": session_id})
        if not rows:
            return 0
        return max(int(row["turn_index"]) for row in rows) + 1

    def turn_indexes(self, session_id: str) -> tuple[int, ...]:
        rows = self.repo.select(TABLE, where={"session_id": session_id})
        return tuple(sorted({int(row["turn_index"]) for row in rows}))

    # -- internals ---------------------------------------------------------

    @staticmethod
    def _check_position(turn_index: int, step_index: int) -> None:
        if turn_index < 0 or step_index < 0:
            raise JournalError(
                f"(turn {turn_index}, step {step_index}) is not a position. "
                "Both are positions in the session and in the turn "
                "respectively, not counters."
            )

    def _row(
        self, session_id: str, turn_index: int, step_index: int, kind: str
    ) -> dict[str, Any] | None:
        rows = self.repo.select(TABLE, where={
            "session_id": session_id, "turn_index": turn_index,
            "step_index": step_index, "kind": kind,
        })
        return rows[0] if rows else None

    def _insert(
        self,
        *,
        session_id: str,
        turn_index: int,
        step_index: int,
        kind: str,
        step_kind: str,
        idempotency_key: str,
        effectful: bool,
        payload: Mapping[str, Any],
        provider_state: bytes | None,
        at: float,
    ) -> None:
        encoded = _encode(payload)
        if provider_state is not None and not isinstance(
            provider_state, (bytes, bytearray)
        ):
            raise JournalError(
                "provider_state is opaque bytes (FR-037). A str would have to "
                "be encoded, and an encoding is an interpretation."
            )
        try:
            self.repo.insert(TABLE, {
                "session_id": session_id,
                "turn_index": turn_index,
                "step_index": step_index,
                "kind": kind,
                "step_kind": step_kind,
                "idempotency_key": idempotency_key,
                "effectful": 1 if effectful else 0,
                "payload": encoded,
                "provider_state": (None if provider_state is None
                                   else bytes(provider_state)),
                "at": at,
            })
        except UniquenessError:
            raise JournalError(
                f"({session_id!r}, turn {turn_index}, step {step_index}) "
                f"already has a committed {kind}, so this one is refused as "
                "already recorded. FR-007: a recorded effect does not repeat. "
                "The refusal comes from the store's unique index rather than "
                "from this object, because the second attempt in the case that "
                "matters is made by a different process after the first was "
                "killed."
            ) from None

    def _step(
        self,
        session_id: str,
        turn_index: int,
        step_index: int,
        rows: list[dict[str, Any]],
    ) -> JournalStep:
        kinds = frozenset(str(row["kind"]) for row in rows)
        complete = _completeness(kinds)
        by_kind = {str(row["kind"]): row for row in rows}
        intent = by_kind.get(KIND_INTENT)
        outcome = by_kind.get(KIND_OUTCOME)
        source = intent or outcome
        assert source is not None  # a group exists because a row is in it
        state = None if outcome is None else outcome["provider_state"]
        return JournalStep(
            session_id=session_id,
            turn_index=turn_index,
            step_index=step_index,
            step_kind=str(source["step_kind"]),
            idempotency_key=str(source["idempotency_key"]),
            effectful=bool(source["effectful"]),
            intent=None if intent is None else _decode(intent["payload"]),
            outcome=None if outcome is None else _decode(outcome["payload"]),
            provider_state=None if state is None else bytes(state),
            intended_at=None if intent is None else float(intent["at"]),
            completed_at=(float(outcome["at"])
                          if complete and outcome is not None else None),
        )


def _encode(payload: Mapping[str, Any]) -> str:
    """Canonical JSON, or a refusal naming what could not go in.

    `sort_keys` because two encodings of one payload would make a digest over
    this table depend on dict ordering.
    """
    _refuse_bytes(payload, path="payload")
    try:
        return json.dumps(dict(payload), sort_keys=True, separators=(",", ":"))
    except TypeError as exc:
        raise JournalError(
            f"the payload is not serialisable ({exc}). It is refused rather "
            "than coerced: a payload written with `default=str` records the "
            "repr of whatever it was, and a resume reader would rebuild a step "
            "out of that."
        ) from None


def _refuse_bytes(value: Any, *, path: str) -> None:
    """FR-037's one accidental route into the payload."""
    if isinstance(value, (bytes, bytearray)):
        raise JournalError(
            f"{path} carries bytes. Opaque provider_state goes in the "
            "`provider_state` column, which `commit_outcome` takes as its own "
            "argument — putting it in the payload would put it through JSON, "
            "and FR-037 forbids interpreting it."
        )
    if isinstance(value, Mapping):
        for key, item in value.items():
            _refuse_bytes(item, path=f"{path}[{key!r}]")
    elif isinstance(value, (list, tuple)):
        for position, item in enumerate(value):
            _refuse_bytes(item, path=f"{path}[{position}]")


def _decode(encoded: str) -> Mapping[str, Any]:
    try:
        return json.loads(encoded)
    except json.JSONDecodeError as exc:
        raise JournalError(f"a journalled payload does not parse: {exc}") from None
