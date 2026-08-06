"""SPIKE - E18. Prove the instrument before spending on it. **No model is called.**

Rule 8 of the [`experiment-design`](../../../../.cursor/skills/experiment-design/SKILL.md)
skill does not stop at *have a negative control*. Step 3 is **"produce each
fault and run the instrument"** — *"not reason about it — produce it. An
instrument that has never been run in its own failure modes has no evidence
about them."* Rows B and C of this probe read one bit, *did the provider error*,
and the faults that produce that bit without the treatment having done anything
are the reason row A exists. But there is a second family this file covers and
row A cannot: faults in which **the treatment was never applied at all** and the
arm reports a clean tolerated result over having withheld nothing.

Six checks, each against a scripted provider that emits exactly what the check
needs. Run it before the paid run and after any edit to `conditions.py` or
`loop.py`:

    python3 selfcheck.py

Exit status is 0 when every check passes and 1 otherwise; a failing check names
the arm, the expectation and what it saw.
"""
from __future__ import annotations

import json
import sys

import chain
import conditions as C
import loop


class ScriptedProvider:
    """A provider that follows `chain` exactly, with configurable state emission.

    `state_on` is the set of assistant-turn indices that emit an opaque value.
    `error_on_shape` is a request shape the provider refuses, so a check can
    assert that an error at a particular shape is scored the way it should be.
    """

    provider = "scripted"
    sdk = "none"
    sdk_version = "0"
    opaque_field = "fake.opaque"
    model = "scripted-1"

    def __init__(self, state_on: set[int] | None = None,
                 error_on_shape: str | None = None) -> None:
        self.state_on = set(range(chain.TURNS)) if state_on is None else state_on
        self.error_on_shape = error_on_shape
        self.turn = 0
        self.seen_shapes: list[str] = []
        self.states_in_last_request: list[str] = []

    # -- the adapter surface ------------------------------------------------
    def first_user(self):
        return {"role": "user", "content": chain.QUESTION}

    def flatten(self, kind, body):
        return [body]

    def send(self, entries):
        carried = [entry["opaque"] for entry in entries
                   if entry.get("role") == "assistant" and "opaque" in entry]
        self.states_in_last_request = carried
        emitted = [entry["_ordinal"] for entry in entries
                   if entry.get("role") == "assistant" and entry.get("_stateful")]
        present = [entry.get("opaque") is not None for entry in entries
                   if entry.get("role") == "assistant" and entry.get("_stateful")]
        shape = C.shape_of(present)
        self.seen_shapes.append(shape)
        if self.error_on_shape is not None and shape == self.error_on_shape:
            raise ScriptedRefusal(f"refusing a {shape} conversation")
        turn, self.turn = self.turn, self.turn + 1
        body = {"role": "assistant", "_turn": turn, "_ordinal": len(emitted),
                "_stateful": turn in self.state_on}
        if turn in self.state_on:
            body["opaque"] = f"opaque-{turn}"
        if turn < chain.HOPS:
            name, args = _hop(turn)
            body["call"] = {"id": f"c{turn}", "name": name, "args": args}
        else:
            body["text"] = f"The final total is {chain.TOTAL}"
        return body

    def assistant(self, response):
        paths = [["opaque"]] if "opaque" in response else []
        return response, paths

    def usage(self, response):
        return 100, 10, None

    def tool_calls(self, body):
        call = body.get("call")
        return [(call["id"], call["name"], call["args"])] if call else []

    def tool_entry(self, results):
        return {"role": "tool",
                "content": json.dumps([out for _i, _n, out in results])}

    def text(self, body):
        return body.get("text", "")

    def classify(self, exc):
        return (400, "capability") if isinstance(exc, ScriptedRefusal) else None


class ScriptedRefusal(Exception):
    """The scripted provider's own 400."""


def _hop(turn: int) -> tuple[str, dict]:
    """The call the scripted model makes on turn `turn`, always correctly chained."""
    return {
        0: ("lookup_customer", {"customer_name": chain.CUSTOMER}),
        1: ("list_orders", {"customer_id": chain.CUSTOMER_ID}),
        2: ("get_order_lines", {"order_id": chain.ORDER_ID}),
        3: ("get_line_price", {"line_id": chain.LINE_ID}),
        4: ("apply_tax", {"subtotal_usd": chain.SUBTOTAL}),
    }[turn]


# ---------------------------------------------------------------------------

FAILURES: list[str] = []


def check(name: str, ok: bool, saw: object = None) -> None:
    if ok:
        print(f"  ok    {name}")
        return
    FAILURES.append(name)
    print(f"  FAIL  {name}" + (f" — saw {saw!r}" if saw is not None else ""))


def main() -> int:
    print("E18 selfcheck — no model is called, nothing is spent")

    print("\n1. the persistence boundary actually removes the value")
    body = {"role": "assistant",
            "content": [{"type": "thinking", "signature": "SIG"},
                        {"type": "tool_use", "id": "t0"}]}
    persisted = C.persist(body, [["content", 0, "signature"]])
    check("the persisted body carries no signature",
          "signature" not in persisted.body["content"][0],
          persisted.body["content"][0])
    check("the original body is untouched", body["content"][0]["signature"] == "SIG")
    withheld, written = C.rebuild(persisted, carry=False)
    check("rebuild(carry=False) writes nothing",
          "signature" not in withheld["content"][0] and written == [])
    restored, written = C.rebuild(persisted, carry=True)
    check("rebuild(carry=True) restores it verbatim",
          restored["content"][0]["signature"] == "SIG" and len(written) == 1)

    print("\n2. condition A carries every state and never produces a gap")
    full = loop.run(ScriptedProvider(), C.FULL, ScriptedProvider().first_user())
    check("six turns", full.turns == chain.TURNS, full.turns)
    check("chained", full.chained and full.answer_correct)
    check("a state on every turn", full.state_turns == chain.TURNS,
          full.state_turns)
    check("no shape other than full or no-state-yet",
          set(full.request_shapes) <= {C.SHAPE_FULL, C.SHAPE_NO_STATE_YET},
          full.request_shapes)
    check("treatment not applied, verdict OK",
          not full.treatment_applied and full.verdict == "OK", full.verdict)

    print("\n3. condition B produces a trailing gap and then an interior hole")
    result = loop.run(ScriptedProvider(), C.DROP_ONE, ScriptedProvider().first_user())
    check("a trailing gap was sent",
          C.SHAPE_TRAILING_GAP in result.request_shapes, result.request_shapes)
    check("an interior hole was sent",
          C.SHAPE_INTERIOR_HOLE in result.request_shapes, result.request_shapes)
    # Ordinal 1's state is in every A request that holds two or more assistant
    # turns — four of the six — and in none of B's. Nothing else may differ.
    check("B re-injected exactly four values fewer than A",
          len(full.digests_reinjected) - len(result.digests_reinjected) == 4,
          (len(full.digests_reinjected), len(result.digests_reinjected)))
    check("treatment applied, verdict TOLERATED on a provider that does not care",
          result.treatment_applied and result.verdict == "TOLERATED",
          result.verdict)
    check("the withheld ordinal is recorded",
          result.withheld_ordinal == C.DROP_ORDINAL, result.withheld_ordinal)

    print("\n4. condition C carries nothing at all")
    result = loop.run(ScriptedProvider(), C.DROP_ALL, ScriptedProvider().first_user())
    check("nothing was ever re-injected", result.digests_reinjected == [],
          result.digests_reinjected)
    check("every request after the first is all-absent",
          set(result.request_shapes) <= {C.SHAPE_ALL_ABSENT, C.SHAPE_NO_STATE_YET},
          result.request_shapes)
    check("treatment applied", result.treatment_applied)

    print("\n5. a provider that emits no state makes B and C UNTESTABLE, not passes")
    for condition in (C.DROP_ONE, C.DROP_ALL):
        result = loop.run(ScriptedProvider(state_on=set()), condition,
                          ScriptedProvider().first_user())
        check(f"condition {condition} over a silent provider is UNTESTABLE",
              result.verdict == "UNTESTABLE-NO-STATE", result.verdict)
        check(f"condition {condition} says so in a note",
              any("emitted no opaque state" in n for n in result.notes),
              result.notes)

    print("\n6. an error is scored as ERRORED under B/C and CONTROL-FAILED under A")
    result = loop.run(ScriptedProvider(error_on_shape=C.SHAPE_INTERIOR_HOLE),
                      C.DROP_ONE, ScriptedProvider().first_user())
    check("B errored at the interior hole",
          result.verdict == "ERRORED"
          and result.last_request_shape == C.SHAPE_INTERIOR_HOLE,
          (result.verdict, result.last_request_shape))
    check("the status is recorded", result.error_status == 400, result.error_status)
    result = loop.run(ScriptedProvider(error_on_shape=C.SHAPE_FULL), C.FULL,
                      ScriptedProvider().first_user())
    check("A erroring is CONTROL-FAILED and not OK",
          result.verdict == "CONTROL-FAILED", result.verdict)

    print("\n7. a provider that errors before the gap is reached is not scored ERRORED")
    result = loop.run(ScriptedProvider(state_on={0, 2}, error_on_shape=C.SHAPE_FULL),
                      C.DROP_ONE, ScriptedProvider().first_user())
    check("no gap was ever sent, so the arm is UNTESTABLE-NOT-APPLIED",
          result.verdict == "UNTESTABLE-NOT-APPLIED", result.verdict)

    print("\n8. a provider that emits state on one turn cannot be given a hole")
    result = loop.run(ScriptedProvider(state_on={0}), C.DROP_ONE,
                      ScriptedProvider().first_user())
    check("condition B over a one-state provider is UNTESTABLE-ONE-STATE-ONLY",
          result.verdict == "UNTESTABLE-ONE-STATE-ONLY", result.verdict)
    check("and it says which turns carried state",
          result.state_turn_indices == [0], result.state_turn_indices)
    check("and it says why in a note",
          any("cannot be built" in n for n in result.notes), result.notes)
    result = loop.run(ScriptedProvider(state_on={0}), C.DROP_ALL,
                      ScriptedProvider().first_user())
    check("condition C over the same provider is still testable",
          result.verdict in ("TOLERATED", "ERRORED"), result.verdict)

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILED: " + ", ".join(FAILURES))
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
