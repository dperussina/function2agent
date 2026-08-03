"""SPIKE - E8 verifier-vs-judge. Delete after 2026-11-30. Do not import from product code.

The oracle-leak barrier: a whitelisting projection, and a hard assertion behind it.

**The hazard is structural, not hypothetical.** ``ceiling-test/runner.py`` writes each trace
record as ``{**row, "tool_calls": ..., "transcript": ...}``, so ``expected``, ``reason``,
``outcome``, ``false_success`` and ``detectors`` are *siblings of the transcript in the same
object*. Any scorer that reaches for the record and serialises it hands the judge the answer.
PREREGISTRATION.md 4.6 and 7.4 make that abort the run and discard every prior call.

Two layers, because either alone is defeatable:

1. :func:`scoring_view` is a **whitelist**. A field that is not named here does not reach a
   scorer, so a future field added to the ceiling-test row format is excluded by default
   rather than included by default. It also tags which leaves are agent-authored.
2. :func:`assert_no_oracle_leak` is a **hard assertion on the assembled payload**, run before
   every model call and before every verifier invocation. It raises :class:`OracleLeak`,
   which callers must treat as fatal.

Scope of the literal checks, and why it is drawn where it is
------------------------------------------------------------
PREREGISTRATION.md 7.4 says the harness asserts the serialised input "contains none of
``expected``, ``reason``, ``outcome``, ``false_success``, nor the literal string of the
expected value." Taken as a bare substring test over the whole payload, that assertion is
unrunnable in both directions and would be worse than nothing:

* ``reason`` and ``outcome`` are ordinary English words. An agent writing "the reason is" in
  its own transcript would abort the run. A check that always fires gets disabled.
* On an oracle-**passing** trace the agent's submitted answer *is* the expected value, and the
  judge is required to see the submitted answer (4.2). A literal expected-value test over the
  whole payload would abort on essentially every positive. A check that must be bypassed to
  run gets bypassed.

So the checks are scoped to the channel the hazard actually travels through:

* **Forbidden keys** are checked as **JSON keys, recursively, over the whole payload,
  absolutely.** This is what catches ``json.dumps(record)``. No exemption exists.
* **Forbidden key-literals and the expected value's literal forms** are checked over the
  **harness-authored region** — every part of the payload the harness itself wrote. Agent
  content is exempt because the application's own data legitimately containing the right
  answer is the task, not a leak.
* **The oracle's ``reason`` string** (e.g. ``"expected 3.201754, got 3.23"``) is checked over
  the **whole payload, absolutely**. That string is pure oracle output; it has no innocent
  route into a transcript, so this test is both safe and strict.

Fail-closed: a leaf is agent-authored only if the builder tagged it :class:`AgentText`.
Anything else — including a field someone adds later — is scanned.
"""

from __future__ import annotations

import json
from typing import Any

#: Field names that carry ground truth in a ceiling-test record. PREREGISTRATION.md 4.6 names
#: the first four; `detectors` is added because it is the false-success detector output and is
#: oracle material by the same argument. Adding to this list can only tighten the barrier.
FORBIDDEN_KEYS = ("expected", "reason", "outcome", "false_success", "detectors")


class OracleLeak(AssertionError):
    """Raised when ground truth reaches a scorer input. Fatal: abort and discard the run."""


class AgentText(str):
    """A string the *agent* wrote (or a tool returned to it), tagged as exempt from the
    literal scans. Tagging is explicit and narrow: only :func:`scoring_view` creates these."""

    __slots__ = ()


# --------------------------------------------------------------------------- projection

#: The only record fields a scorer may see. PREREGISTRATION.md 4.2: the judge sees the task
#: prompt, the full transcript, the tool calls with their results, and the submitted answer.
JUDGE_FIELDS = ("task_id", "arm", "run_id", "attempt", "terminal",
                "submitted", "submitted_status", "tool_calls", "transcript")

#: c1/c2 additionally get nothing beyond this; their derivation inputs are the OpenAPI schema
#: and the tool signatures, which are not part of the record at all.
VERIFIER_FIELDS = JUDGE_FIELDS


#: Join keys. They exist so a verdict can be matched back to a record; no scorer reads them
#: and no prompt builder emits them. They are excluded from the scanned region because they
#: are not a channel into a scorer — and because they produce genuine false positives: run ids
#: are timestamps, and a timestamp such as ``...064550...`` contains the digits of an expected
#: value of 550. Exempting them from the scan would be wrong; excluding them from the *scorer
#: input* is right, and that is what :func:`scorer_content` does.
BOOKKEEPING_FIELDS = ("task_id", "run_id", "arm", "attempt")

#: What a scorer — judge or verifier — is actually shown.
CONTENT_FIELDS = ("task_prompt", "terminal", "submitted_status", "submitted",
                  "tool_calls", "transcript")


def scorer_content(view: dict) -> dict:
    """The content-bearing subset of a scoring view: everything a scorer reads, and nothing else.

    ``terminal`` and ``submitted_status`` are tagged as agent-authored because they describe
    the agent's own behaviour, not the harness's commentary on it.
    """
    out: dict[str, Any] = {}
    for f in CONTENT_FIELDS:
        if f not in view:
            continue
        v = view[f]
        out[f] = AgentText(str(v)) if f in ("terminal", "submitted_status") and v is not None else v
    return out


def _tag(value: Any) -> Any:
    """Recursively mark agent-authored content, preserving structure."""
    if isinstance(value, str):
        return AgentText(value)
    if isinstance(value, list):
        return [_tag(v) for v in value]
    if isinstance(value, dict):
        return {k: _tag(v) for k, v in value.items()}
    return value


def scoring_view(record: dict, task_prompt: str, fields: tuple[str, ...] = JUDGE_FIELDS) -> dict:
    """Project a frozen trace record down to what a scorer is allowed to see.

    ``task_prompt`` comes from the battery's ``prompt`` field. The battery's ``check`` object
    is oracle material and never travels with it.

    Identifiers (``task_id``, ``run_id``, ``arm``, ``attempt``) are retained for bookkeeping and
    stripped again by the prompt builders — they are needed to join verdicts back to records,
    not to score. Nothing in them encodes an outcome.
    """
    out: dict[str, Any] = {}
    for f in fields:
        if f not in record:
            continue
        out[f] = _tag(record[f]) if f in ("transcript", "tool_calls", "submitted") else record[f]
    out["task_prompt"] = AgentText(task_prompt)
    leaked = [k for k in FORBIDDEN_KEYS if k in out]
    if leaked:
        raise OracleLeak(f"scoring_view whitelist admitted an oracle field: {leaked}")
    return out


# --------------------------------------------------------------------------- assertion

def _walk_keys(obj: Any, path: str = "$") -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(k, str) and k.lower() in FORBIDDEN_KEYS:
                found.append((f"{path}.{k}", k))
            found.extend(_walk_keys(v, f"{path}.{k}"))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            found.extend(_walk_keys(v, f"{path}[{i}]"))
    return found


def _harness_authored(obj: Any) -> list[str]:
    """Every string in the payload that the harness itself wrote (untagged strings)."""
    out: list[str] = []
    if isinstance(obj, AgentText):
        return out
    if isinstance(obj, str):
        return [obj]
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(k, str):
                out.append(k)
            out.extend(_harness_authored(v))
    elif isinstance(obj, list):
        for v in obj:
            out.extend(_harness_authored(v))
    return out


def _all_strings(obj: Any) -> list[str]:
    if isinstance(obj, str):
        return [str(obj)]
    if isinstance(obj, dict):
        out: list[str] = []
        for k, v in obj.items():
            if isinstance(k, str):
                out.append(k)
            out.extend(_all_strings(v))
        return out
    if isinstance(obj, list):
        return [s for v in obj for s in _all_strings(v)]
    return []


def expected_literals(expected: Any) -> list[str]:
    """Every literal rendering of an expected value that could betray it in harness text."""
    lits: set[str] = set()

    def add(v: Any) -> None:
        if v is None:
            return
        if isinstance(v, bool):
            lits.add(str(v))
            return
        if isinstance(v, (int, float)):
            lits.add(repr(v))
            lits.add(str(v))
            if isinstance(v, float) and v.is_integer():
                lits.add(str(int(v)))
            return
        if isinstance(v, str):
            if v.strip():
                lits.add(v)
            return
        if isinstance(v, (list, tuple, set)):
            if v:
                lits.add(json.dumps(sorted(v, key=str) if isinstance(v, set) else list(v)))
            for item in v:
                add(item)
            return
        if isinstance(v, dict):
            lits.add(json.dumps(v, sort_keys=True))
            for item in v.values():
                add(item)

    add(expected)
    # A one- or two-character rendering ("0", "[]", "10") collides with ordinary prose and
    # with structural punctuation. Those are dropped from the LITERAL scan; the key scan and
    # the reason-string scan still cover the record-shaped leak, which is the real hazard.
    return sorted(x for x in lits if len(x) >= 3)


#: Key-shaped renderings of a forbidden field. A bare English "reason" in agent prose is not a
#: leak; `"reason":` in harness-authored text is.
def _key_literals() -> list[str]:
    out: list[str] = []
    for k in FORBIDDEN_KEYS:
        out += [f'"{k}"', f"'{k}'", f"{k}=", f"{k}:"]
    return out


def assert_no_oracle_leak(payload: Any, record: dict, where: str = "model call") -> None:
    """Abort the run if ground truth has reached a scorer input.

    Raises :class:`OracleLeak`. PREREGISTRATION.md 4.6 / 7.4 / S2: the caller must treat this
    as fatal — abort immediately, discard every prior call in the run, investigate before any
    re-run. It is not a warning and it is not recoverable within a run.
    """
    # 1. Structural: no oracle field anywhere in the payload, at any depth. Absolute.
    hits = _walk_keys(payload)
    if hits:
        raise OracleLeak(
            f"ORACLE LEAK at {where}: oracle field(s) present in the payload structure: "
            + ", ".join(f"{p} ({k})" for p, k in hits)
            + "\n  This is the ceiling-test record shape reaching a scorer. Abort the run,"
              " discard every call already made, and fix the projection before re-running."
        )

    harness_text = "\n".join(_harness_authored(payload))

    # 2. Key-shaped literals in harness-authored text. Absolute within that region.
    for lit in _key_literals():
        if lit in harness_text:
            raise OracleLeak(
                f"ORACLE LEAK at {where}: harness-authored text contains the oracle field "
                f"literal {lit!r}."
            )

    # 3. The expected value, in harness-authored text. Absolute within that region.
    #    Agent-authored content is exempt by design; see the module docstring.
    for lit in expected_literals(record.get("expected")):
        if lit in harness_text:
            raise OracleLeak(
                f"ORACLE LEAK at {where}: harness-authored text contains the expected value "
                f"literal {lit!r}."
            )

    # 4. The oracle's own reason string, anywhere in the payload. Absolute, unscoped:
    #    "expected 3.201754, got 3.23" has no innocent route into an agent transcript.
    reason = (record.get("reason") or "").strip()
    if len(reason) >= 8:
        blob = "\n".join(_all_strings(payload))
        if reason in blob:
            raise OracleLeak(
                f"ORACLE LEAK at {where}: the oracle's adjudication reason string is present "
                f"in the payload."
            )


def leak_audit(payload: Any, record: dict, where: str = "model call") -> str | None:
    """Non-fatal form, for the pre-flight audit. Returns the complaint, or None."""
    try:
        assert_no_oracle_leak(payload, record, where)
    except OracleLeak as exc:
        return str(exc).splitlines()[0]
    return None
