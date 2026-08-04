"""FR-058 — the per-result bound, its disclosure, and its seven trace fields.

Four things this file is deliberately built to catch, each of them a shape this
corpus has found before:

1. **A bound enforced through an average bytes-per-token divisor.** FR-058
   disqualifies that basis by name, because an average under-counts exactly the
   content that needs the bound — minified JSON, base64, dense identifiers. The
   arms use content whose real token count is far above what a `4.0` divisor
   would predict, and assert the admitted text is within the bound as the
   *tokenizer in force* counts it.
2. **A disclosure that lives only in the trace.** FR-058 forecloses that
   substitution in as many words: the model is a reader that arrives at the
   result and at nothing else. So the assertions read the bytes the model gets.
3. **Fields written only where the bound bit.** A field written only on
   truncation cannot distinguish "not bounded" from "not instrumented", so the
   fitting case asserts all seven are present and `admitted == full_size`.
4. **A reference that relocates the liability.** A path handed back without a
   bound of its own, without session scoping, and without an end is an unbounded
   quantity moved from the transcript onto a disk. The retention arms assert the
   refusal, the isolation and the removal.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from src.runtime.result_bound import (
    DISPOSITION_RETAINED,
    DISPOSITION_UNRECOVERABLE,
    UNIT_BYTES,
    UNIT_TOKENS,
    BoundConfigError,
    ResultBound,
    RetentionError,
    RetentionStore,
    conservative_byte_ceiling,
)
from src.runtime.trace import (
    ArtifactVersions,
    Cost,
    Span,
    SpanError,
    TOOL_CALL,
    MODEL_CALL,
    OUTCOME_OK,
    ATTEMPT_FIRST,
)

WINDOW = 200_000
BOUND = 2_000  # exactly one twentieth of the window is 10_000; this is under it


class WordTokenizer:
    """A stand-in tokenizer. Real enough to fail a byte-average bound.

    One token per whitespace-delimited run, plus one per four characters of any
    run longer than four — which is roughly how a real BPE behaves on dense
    identifiers, and is the behaviour an average divisor gets wrong.
    """

    name = "word-test-v1"

    def count(self, text: str) -> int:
        total = 0
        for run in text.split():
            total += max(1, (len(run) + 3) // 4)
        return total


class OneTokenPerByte:
    """The adversarial extreme: every byte is a token.

    This is not hypothetical — it is what a byte-oriented tokenizer does to
    base64 and to minified numerics, and it is the case a bytes-per-token
    average of 4.0 under-counts by a factor of four.
    """

    name = "byte-test-v1"

    def count(self, text: str) -> int:
        return len(text.encode("utf-8"))


def _retention(tmp_path: Path, *, max_bytes: int = 1_000_000) -> RetentionStore:
    return RetentionStore(
        root=tmp_path / "scratch",
        session_id="sess-1",
        max_bytes=max_bytes,
    )


def _bound(tokenizer=None, **kwargs) -> ResultBound:
    return ResultBound(
        bound_tokens=kwargs.pop("bound_tokens", BOUND),
        context_window_tokens=kwargs.pop("context_window_tokens", WINDOW),
        tokenizer=tokenizer,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Configuration: required, ceilinged, refused rather than clamped.


def test_a_bound_above_one_twentieth_of_the_window_is_refused_not_clamped() -> None:
    with pytest.raises(BoundConfigError) as raised:
        _bound(bound_tokens=WINDOW // 20 + 1)
    message = str(raised.value).lower()
    assert "refused" in message
    assert "clamp" in message
    assert str(WINDOW // 20) in message, (
        "the refusal has to name the ceiling it exceeded, or an operator has "
        "to derive it"
    )


def test_a_bound_at_exactly_one_twentieth_is_permitted() -> None:
    """The ceiling is `MUST NOT exceed`, so the boundary value is legal."""
    bound = _bound(bound_tokens=WINDOW // 20)
    assert bound.bound_tokens == WINDOW // 20


def test_a_bound_of_zero_or_less_is_refused() -> None:
    for value in (0, -1):
        with pytest.raises(BoundConfigError):
            _bound(bound_tokens=value)


def test_a_missing_context_window_is_refused_because_the_ceiling_needs_it() -> None:
    """The window is not a bound, but without it the ceiling is uncomputable."""
    with pytest.raises(BoundConfigError, match="context window"):
        _bound(context_window_tokens=0)


def test_the_config_keys_are_declared_with_no_default() -> None:
    """FR-058 under FR-033: required, and startup fails naming what is missing."""
    from src.contracts.config import RUNTIME_KEYS, ConfigError, load

    names = {key.name for key in RUNTIME_KEYS}
    assert {"TOOL_RESULT_BOUND_TOKENS", "MODEL_CONTEXT_WINDOW_TOKENS",
            "RESULT_RETENTION_MAX_BYTES"} <= names
    for key in RUNTIME_KEYS:
        if key.name.startswith(("TOOL_RESULT_", "MODEL_CONTEXT_", "RESULT_RETENTION_")):
            assert key.default is None, f"{key.name} ships a default"
            assert key.no_default_reason, f"{key.name} has no stated reason"

    with pytest.raises(ConfigError) as raised:
        load(RUNTIME_KEYS, env={})
    report = str(raised.value)
    assert "TOOL_RESULT_BOUND_TOKENS" in report
    assert "Nothing has been started" in report


# ---------------------------------------------------------------------------
# The bound itself, in tokens.


def test_a_result_that_fits_is_returned_whole_and_still_instrumented(tmp_path) -> None:
    """The arm that catches fields written only at the bound."""
    bound = _bound(WordTokenizer())
    body = "a short result"
    outcome = bound.apply(body, retention=_retention(tmp_path), call_id="c-1")

    assert outcome.text == body, "a result within the bound was altered"
    assert not outcome.fields.bound_applied_and_bit
    assert outcome.fields.bound_in_force == BOUND
    assert outcome.fields.unit == UNIT_TOKENS
    assert outcome.fields.byte_proxy is False
    assert outcome.fields.full_size == outcome.fields.admitted, (
        "nothing was withheld, so the two sizes must be equal — that equality "
        "is the signal, and no third disposition is invented"
    )
    assert outcome.fields.disposition == DISPOSITION_RETAINED
    assert outcome.fields.reference is None
    # All seven fields present on a span that never hit the bound.
    record = outcome.fields.to_record()
    assert set(record) >= {
        "bound_applied", "bound_in_force", "unit", "byte_proxy",
        "full_size", "admitted", "disposition",
    }
    assert record["bound_applied"] is True, (
        "the bound WAS applied to this call; it simply did not bite. A false "
        "here makes a result that fitted indistinguishable from a call the "
        "bound never ran on."
    )


def test_a_result_over_the_bound_comes_back_within_it(tmp_path) -> None:
    bound = _bound(WordTokenizer())
    body = " ".join(f"line-{i}-of-a-long-result" for i in range(5_000))
    tokenizer = WordTokenizer()
    assert tokenizer.count(body) > BOUND

    outcome = bound.apply(body, retention=_retention(tmp_path), call_id="c-2")

    assert tokenizer.count(outcome.text) <= BOUND, (
        f"the returned text is {tokenizer.count(outcome.text)} tokens against "
        f"a bound of {BOUND}. The disclosure counts: the model reads the whole "
        "string, so the bound has to cover the preview and the notice together."
    )
    assert outcome.fields.full_size == tokenizer.count(body)
    assert outcome.fields.admitted < outcome.fields.full_size
    assert outcome.fields.bound_applied_and_bit


def test_the_bound_holds_on_content_a_byte_average_under_counts(tmp_path) -> None:
    """FR-058's disqualified basis, as an assertion rather than a comment.

    Base64 under a byte-per-token tokenizer is four times denser than a `4.0`
    divisor predicts. A bound enforced as `bound_tokens * 4` bytes would admit
    four times the bound here, which is why the requirement rules that
    derivation out by name.
    """
    tokenizer = OneTokenPerByte()
    bound = _bound(tokenizer)
    body = "QUJDREVGR0hJSktMTU5PUFFSU1RVVldYWVowMTIzNDU2Nzg5" * 500

    outcome = bound.apply(body, retention=_retention(tmp_path), call_id="c-3")

    admitted_tokens = tokenizer.count(outcome.text)
    assert admitted_tokens <= BOUND, (
        f"{admitted_tokens} tokens admitted against a bound of {BOUND}. An "
        "average divisor would have admitted about four times the bound on "
        "this content, which is the failure FR-058 names."
    )
    # And the control: the average basis really would have overshot here, so
    # the arm above is not passing for a trivial reason.
    would_admit_bytes = BOUND * 4
    assert tokenizer.count(body[:would_admit_bytes]) > BOUND, (
        "a 4.0 divisor would not have overshot on this content, so this arm "
        "does not demonstrate what it claims"
    )


def test_a_byte_proxy_is_permitted_only_when_it_cannot_overshoot(tmp_path) -> None:
    """No tokenizer available: the derivation must be a floor, not an average.

    One byte per token is the only safe floor, because a token cannot be
    shorter than a byte. `conservative_byte_ceiling` is that derivation, and it
    is asserted against the worst case rather than described.
    """
    assert conservative_byte_ceiling(BOUND) == BOUND

    bound = _bound(tokenizer=None)
    body = "x" * 100_000
    outcome = bound.apply(body, retention=_retention(tmp_path), call_id="c-4")

    assert outcome.fields.byte_proxy is True
    assert outcome.fields.unit == UNIT_BYTES, (
        "the unit field has to say what was actually enforced; a trace whose "
        "tokenizer was unavailable is otherwise indistinguishable from one "
        "whose tokenizer was not"
    )
    assert len(outcome.text.encode("utf-8")) <= conservative_byte_ceiling(BOUND)
    # The worst case: every byte is one token. Even then the bound holds.
    assert OneTokenPerByte().count(outcome.text) <= BOUND, (
        "the byte proxy admitted more tokens than the bound under a "
        "byte-oriented tokenizer, which is the case it has to be safe for"
    )


def test_the_byte_proxy_never_uses_an_average_divisor() -> None:
    """The `4.0` in this repository is not reachable from the bound.

    Stated as a test because the divisor exists, is nearby, and is the obvious
    thing to reach for.
    """
    for bound_tokens in (1, 10, 2_000, 10_000):
        assert conservative_byte_ceiling(bound_tokens) == bound_tokens
        assert conservative_byte_ceiling(bound_tokens) < bound_tokens * 4


# ---------------------------------------------------------------------------
# What the agent is told — in the result, not in the trace.


def test_the_bounded_result_discloses_its_own_bounding(tmp_path) -> None:
    bound = _bound(WordTokenizer())
    body = " ".join(f"row-{i}" for i in range(20_000))
    outcome = bound.apply(body, retention=_retention(tmp_path), call_id="c-5")

    text = outcome.text
    assert "bounded" in text.lower(), "the result does not say it is bounded"
    assert str(outcome.fields.full_size) in text, "the full size is not stated"
    assert str(outcome.fields.admitted) in text, "the admitted amount is not stated"
    assert outcome.fields.reference is not None
    assert outcome.fields.reference in text, (
        "the reference is in the trace and not in the result. FR-058: a "
        "disclosure recorded anywhere other than in the result does not "
        "discharge this."
    )


def test_an_unrecoverable_result_says_so_in_itself(tmp_path) -> None:
    """The one permitted lossy case, and the words it has to carry."""
    bound = _bound(WordTokenizer())
    body = " ".join(f"row-{i}" for i in range(20_000))
    full = _retention(tmp_path, max_bytes=16)  # at its bound before we start

    outcome = bound.apply(body, retention=full, call_id="c-6")

    assert outcome.fields.disposition == DISPOSITION_UNRECOVERABLE
    assert outcome.fields.reference is None
    assert "unrecoverable" in outcome.text.lower()
    assert str(outcome.fields.full_size) in outcome.text


def test_a_bounded_result_never_reads_as_a_complete_one(tmp_path) -> None:
    """The property stated as a comparison, not as a keyword search.

    Two calls, one that fits and one that does not. The bounded one has to
    differ from the plain body by more than its length: a caller stripping the
    notice would pass a keyword assertion on the fitting case and fail here.
    """
    bound = _bound(WordTokenizer())
    fitting = bound.apply("small", retention=_retention(tmp_path), call_id="c-7")
    large = " ".join(f"row-{i}" for i in range(20_000))
    bounded = bound.apply(large, retention=_retention(tmp_path), call_id="c-8")

    assert fitting.text == "small"
    assert not bounded.text.startswith(large[:200]) or "bounded" in bounded.text[:400], (
        "the bounded result opens with the payload and no notice, so a model "
        "reading the first lines sees an ordinary result"
    )
    assert bounded.text != large[: len(bounded.text)], (
        "the bounded result is a prefix of the body and nothing else, which is "
        "silent truncation"
    )


# ---------------------------------------------------------------------------
# Retention: its own bound, session-scoped, and it ends.


def test_the_retention_location_carries_its_own_declared_bound(tmp_path) -> None:
    store = _retention(tmp_path, max_bytes=200)
    store.retain("c-1", b"x" * 150)
    with pytest.raises(RetentionError, match="bound"):
        store.retain("c-2", b"x" * 150)
    assert store.bytes_held <= 200


def test_retention_refuses_a_root_outside_the_declared_location_set(tmp_path) -> None:
    """FR-058 requires the withheld bytes inside FR-048's declared set."""
    from src.supervisor.location_set import LocationSet, DeclaredLocation

    declared = LocationSet(
        schema_version="1.0.0", set_version="v1", deployment_id="d-1",
        locations=(DeclaredLocation(
            source=str(tmp_path / "host"), target="/session/scratch", mode="rw",
            nosuid=True, nodev=True, noexec=True,
            rule_id="FS-001", justification="scratch"),),
    )
    RetentionStore(root=tmp_path / "ok", session_id="s", max_bytes=10,
                   declared_target="/session/scratch", location_set=declared)
    with pytest.raises(RetentionError, match="declared"):
        RetentionStore(root=tmp_path / "bad", session_id="s", max_bytes=10,
                       declared_target="/somewhere/else", location_set=declared)


def test_a_read_only_declared_location_is_refused_as_a_retention_target(tmp_path) -> None:
    from src.supervisor.location_set import LocationSet, DeclaredLocation

    declared = LocationSet(
        schema_version="1.0.0", set_version="v1", deployment_id="d-1",
        locations=(DeclaredLocation(
            source=str(tmp_path / "host"), target="/session/ro", mode="ro",
            nosuid=True, nodev=True, noexec=True,
            rule_id="FS-002", justification="read only"),),
    )
    with pytest.raises(RetentionError, match="read-only"):
        RetentionStore(root=tmp_path / "ro", session_id="s", max_bytes=10,
                       declared_target="/session/ro", location_set=declared)


def test_one_sessions_retained_bytes_are_not_reachable_from_another(tmp_path) -> None:
    """FR-050's isolation clause, at the path and at the mode.

    Two arms because either alone is defeatable: separate directories mean a
    guessed path from another session's store is refused, and 0o700 on the
    directory means the path is not readable even if it is guessed.
    """
    first = RetentionStore(root=tmp_path / "scratch", session_id="sess-a",
                           max_bytes=1_000)
    reference = first.retain("c-1", b"secret bytes")

    second = RetentionStore(root=tmp_path / "scratch", session_id="sess-b",
                            max_bytes=1_000)
    assert second.directory != first.directory
    with pytest.raises(RetentionError, match="another session"):
        second.read(reference)

    mode = os.stat(first.directory).st_mode & 0o777
    assert mode == 0o700, f"the retention directory is mode {oct(mode)}"


def test_retention_does_not_outlive_the_session(tmp_path) -> None:
    store = RetentionStore(root=tmp_path / "scratch", session_id="sess-a",
                           max_bytes=1_000)
    reference = store.retain("c-1", b"bytes")
    assert Path(reference).exists()

    store.discard()
    assert not Path(reference).exists()
    assert not store.directory.exists(), (
        "the session's retention directory survived the session, so the "
        "reference relocated an unbounded quantity onto a disk rather than "
        "bounding it"
    )
    with pytest.raises(RetentionError):
        store.retain("c-2", b"more")


def test_the_reference_is_a_path_the_next_call_on_the_surface_can_name(tmp_path) -> None:
    """FR-058 rules out an object handle by name: bytes cross a boundary."""
    store = _retention(tmp_path)
    reference = store.retain("c-1", b"hello withheld world")
    assert Path(reference).is_absolute()
    assert Path(reference).read_bytes() == b"hello withheld world"


# ---------------------------------------------------------------------------
# The trace obligation, on the span.


def _span(fields=None, kind: str = TOOL_CALL) -> Span:
    return Span(
        kind=kind,
        session_id="sess-1",
        turn=0,
        ordinal=0,
        outcome=OUTCOME_OK,
        attempt_kind=ATTEMPT_FIRST,
        versions=ArtifactVersions("t-1", "d-1", {"prompt": "sha256:" + "0" * 64}),
        cost=Cost(0.0, 0, 0.0, 0, 0.0, 0, 0.0, 0),
        at=1.0,
        result_bound=fields,
    )


def test_a_tool_call_span_without_the_seven_fields_is_refused(tmp_path) -> None:
    """The obligation is on every `tool_call`, not only the bounded ones."""
    with pytest.raises(SpanError) as raised:
        _span(None)
    assert "FR-058" in str(raised.value)


def test_the_seven_fields_reach_the_span_record(tmp_path) -> None:
    bound = _bound(WordTokenizer())
    body = " ".join(f"row-{i}" for i in range(20_000))
    outcome = bound.apply(body, retention=_retention(tmp_path), call_id="c-9")

    record = _span(outcome.fields).to_record()
    held = record["result_bound"]
    assert held["bound_applied"] is True
    assert held["bound_in_force"] == BOUND
    assert held["unit"] == UNIT_TOKENS
    assert held["byte_proxy"] is False
    assert held["full_size"] > held["admitted"]
    assert held["disposition"] == DISPOSITION_RETAINED
    assert held["reference"] == outcome.fields.reference
    # And it survives the canonical encoder the writer uses.
    from src.contracts.canonical import dumps
    assert json.loads(dumps(record))["result_bound"]["unit"] == UNIT_TOKENS


def test_only_a_tool_call_span_carries_the_bound_fields(tmp_path) -> None:
    """Putting them elsewhere makes the check miss the span that needed them."""
    bound = _bound(WordTokenizer())
    outcome = bound.apply("x", retention=_retention(tmp_path), call_id="c-10")
    with pytest.raises(SpanError, match="tool_call"):
        _span(outcome.fields, kind=MODEL_CALL)


def test_the_span_kind_set_is_still_seven(tmp_path) -> None:
    """FR-058 adds fields and MUST NOT add a kind. FR-038's set is closed."""
    from src.runtime import trace

    assert len(trace.KINDS) == 7
    assert TOOL_CALL in trace.KINDS
