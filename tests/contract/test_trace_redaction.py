"""T040 — no credential-shaped value and no readable `provider_state` in any trace.

FR-036 (secrets never in a trace) and FR-037 (opaque provider continuation state
is not readable data). Both are scanned over what actually reaches storage,
because that is the artifact an operator, a support engineer, or an exfiltrating
reader gets — not over what the writer intended to put there.

**The scanner is checked against a planted positive.** A redaction test whose
detector matches nothing passes for a system that writes every key in plaintext,
which is the failure mode of most redaction tests.
"""

from __future__ import annotations

import json
import re

import pytest

from src.contracts.repository import Repository
from src.contracts.secret import Secret
from src.runtime import trace
from src.runtime.trace import ArtifactVersions, Cost, DecisionFields, Span, SpanError, SpanWriter

VERSIONS = ArtifactVersions(
    tenant_id="t-1", deployment_id="d-1",
    by_kind={"egress_policy": "sha256:" + "2" * 64})

COST = Cost(0.01, 100, 0.5, 0, 0.01, 100, 0.5, 1)

# Credential shapes. Each is a real-world prefix or structure, so a value that
# looks like one of these in a trace is a finding rather than a coincidence.
CREDENTIAL_PATTERNS = {
    "openai_key": re.compile(r"sk-[A-Za-z0-9_-]{16,}"),
    "anthropic_key": re.compile(r"sk-ant-[A-Za-z0-9_-]{16,}"),
    "google_key": re.compile(r"AIza[0-9A-Za-z_-]{30,}"),
    "aws_access_key": re.compile(r"AKIA[0-9A-Z]{12,}"),
    "bearer_header": re.compile(r"[Bb]earer\s+[A-Za-z0-9._-]{20,}"),
    "jwt": re.compile(r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"),
    "private_key_block": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
}

TEST_CREDENTIAL = "sk-live-0123456789abcdefghij"


def credential_findings(text: str) -> list[tuple[str, str]]:
    return [(name, match.group(0))
            for name, pattern in CREDENTIAL_PATTERNS.items()
            for match in pattern.finditer(text)]


@pytest.fixture()
def writer(tmp_path):
    repo = Repository(tmp_path / "trace.sqlite3", role="runtime",
                      tenant_id="t-1", deployment_id="d-1")
    yield SpanWriter(repo)
    repo.close()


def _write(writer: SpanWriter, **kwargs) -> None:
    writer.write(Span(
        session_id="sess-1", turn=0, ordinal=writer.next_ordinal("sess-1", 0),
        versions=VERSIONS, cost=COST, at=1.0,
        attempt_kind=trace.ATTEMPT_FIRST, **kwargs))


def _all_stored_text(writer: SpanWriter) -> str:
    return json.dumps(writer.spans("sess-1"))


def test_the_scanner_catches_a_planted_credential() -> None:
    """The control. Without it, every assertion below is vacuous."""
    for sample in (
        TEST_CREDENTIAL,
        "sk-ant-api03-abcdefghijklmnopqrst",
        "AIzaSyA0123456789abcdefghijklmnopqrstu",
        "AKIAIOSFODNN7EXAMPLE",
        "Authorization: Bearer abcdefghijklmnopqrstuvwxyz012345",
        "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.abcdefghijk",
        "-----BEGIN RSA PRIVATE KEY-----",
    ):
        assert credential_findings(sample), f"the scanner misses {sample[:20]!r}"
    assert not credential_findings("a perfectly ordinary trace payload")


def test_no_credential_shaped_value_reaches_storage(writer) -> None:
    _write(writer, kind=trace.MODEL_CALL, outcome=trace.OUTCOME_OK,
           detail={"model": "test", "request_id": "req-1"})
    _write(writer, kind=trace.EGRESS_DECISION, outcome=trace.OUTCOME_OK,
           decision=DecisionFields(
               rule_id="EG-ALLOW-001", resolved_tier="read_only",
               matched={"method": "GET", "path": "/orders"}))
    findings = credential_findings(_all_stored_text(writer))
    assert not findings, f"credential-shaped values in the trace: {findings}"


def test_a_secret_cannot_be_placed_in_a_span_at_all(writer) -> None:
    """The structural half. FR-036's `Secret` has no serializer, and the span
    writer refuses one outright so it never gets as far as rendering."""
    with pytest.raises(SpanError, match="Secret"):
        _write(writer, kind=trace.MODEL_CALL, outcome=trace.OUTCOME_OK,
               detail={"auth": Secret(TEST_CREDENTIAL, name="F2A_MODEL_KEY")})

    # Nested, because the first thing anyone does is put it one level down.
    with pytest.raises(SpanError, match="Secret"):
        _write(writer, kind=trace.MODEL_CALL, outcome=trace.OUTCOME_OK,
               detail={"request": {"headers": {"authorization":
                                               Secret(TEST_CREDENTIAL, name="k")}}})
    with pytest.raises(SpanError, match="Secret"):
        _write(writer, kind=trace.MODEL_CALL, outcome=trace.OUTCOME_OK,
               detail={"chain": [{"auth": Secret(TEST_CREDENTIAL, name="k")}]})

    assert writer.spans("sess-1") == [], "a refused span was written anyway"


def test_a_raw_credential_string_would_be_caught_by_the_scan(writer) -> None:
    """The residual case: someone passes the credential as a bare string.

    Nothing structurally prevents that — a `str` is a `str` — so this asserts
    the scan is what catches it, and that the scan is pointed at storage rather
    than at the object.
    """
    _write(writer, kind=trace.MODEL_CALL, outcome=trace.OUTCOME_OK,
           detail={"authorization": TEST_CREDENTIAL})
    findings = credential_findings(_all_stored_text(writer))
    assert findings, (
        "a bare credential string reached storage and the scan did not see "
        "it; T040's scan is looking at the wrong artifact"
    )


def test_provider_state_is_not_readable_in_a_trace(writer) -> None:
    """FR-037. Opaque continuation state is a handle, not data.

    A trace that carries the state itself makes an opaque value readable, and a
    reader who can read it will parse it — after which the provider's next
    format change is a runtime break in this system.
    """
    _write(writer, kind=trace.MODEL_CALL, outcome=trace.OUTCOME_OK,
           detail={"provider_state_ref": "ps-7f3a", "model": "test"})

    stored = json.loads(_all_stored_text(writer))
    payloads = [json.loads(row["payload"]) for row in stored]
    for payload in payloads:
        detail = payload["detail"]
        assert "provider_state" not in detail, (
            "the trace carries provider_state itself. FR-037 makes it opaque; "
            "carry a reference."
        )
        for key, value in detail.items():
            if "provider_state" in key:
                assert key.endswith("_ref"), (
                    f"{key} looks like provider state carried inline"
                )
                assert len(str(value)) < 64, (
                    f"{key} holds {len(str(value))} characters — that is a "
                    "payload, not a handle"
                )


def test_a_trace_scan_over_a_full_session_is_clean(writer) -> None:
    """End to end over the session T039 builds, so the two tests cover the
    same trace rather than two different ones."""
    from tests.contract.test_trace_spans import _full_session

    repo = writer.repo
    other = SpanWriter(repo)
    _full_session(other, session_id="sess-full")

    text = json.dumps(other.spans("sess-full"))
    assert not credential_findings(text)
    assert "provider_state" not in text or '"provider_state_ref"' in text
    assert text, "the scan ran over nothing"


def test_the_redaction_marker_is_not_itself_a_leak() -> None:
    """A marker that embeds part of the value is worse than none."""
    secret = Secret(TEST_CREDENTIAL, name="F2A_MODEL_KEY")
    rendered = f"{secret!r} {secret}"
    assert TEST_CREDENTIAL not in rendered
    assert not credential_findings(rendered)
    assert "F2A_MODEL_KEY" in rendered, (
        "the marker does not name which credential it stands for, which makes "
        "a redacted trace unusable for diagnosis"
    )
