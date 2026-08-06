"""SPIKE - E18. The six-turn dependent chain every arm drives. Do not import from product code.

**The shape is T061's, deliberately, and not a second unrelated scenario.**
[Finding 030](../../findings/030-provider-state-chain-derived-not-measured.md) §6
asks for the live arms to run over the chain the offline conformance fixture
already replays, so that a live reading and an offline one describe the same
conversation. The five hops below are copied from
[`tests/conformance/cassettes/build_cassettes.py`](../../../../tests/conformance/cassettes/build_cassettes.py)`::CHAIN`
value for value:

    lookup_customer("Dana Whitfield") -> {"customer_id":   "CUS-4417"}
    list_orders("CUS-4417")           -> {"order_id":      "ORD-7731"}
    get_order_lines("ORD-7731")       -> {"line_id":       "LN-22"}
    get_line_price("LN-22")           -> {"subtotal_usd":  139.99}
    apply_tax(139.99)                 -> {"total_usd":     149.99}

Six turns: five assistant turns that call a tool, and a sixth that answers.

**Every hop's argument is the previous hop's return value and no value is
derivable from the prompt.** Each tool rejects an identifier it did not itself
issue, so a chain that guessed or skipped a hop fails loudly rather than
answering by luck. `ToolLog.chained()` asserts the linkage on the recorded
arguments; it does not infer chaining from the final answer, because
[finding 016](../../../001-discovery-validation/findings/016-provider-sdk-roundtrip.md)
result 7 measured a chain answering correctly with its opaque state stripped
entirely.

**Five hops is not claimed to be the depth at which opaque-state loss bites.**
That depth is unmeasured and `build_cassettes.py` says so about the same chain.
What the length buys here is five separate assistant turns on which a state has
to be carried, which is what makes a *hole* in the middle of a chain
constructible at all — the condition finding 030 §2 says has never been run on
any provider.
"""
from __future__ import annotations

from typing import Any

QUESTION = (
    "What is the final total, tax included, for customer Dana Whitfield's "
    "most recent order? Use the tools; each one needs an identifier the "
    "previous one returns."
)

SYSTEM = (
    "You answer questions about orders using the supplied tools. "
    "Each tool needs an identifier that only the previous tool can give you, "
    "so work through them in order and never guess an identifier. "
    "When you have the final total, state it as a plain number."
)

CUSTOMER = "Dana Whitfield"
CUSTOMER_ID = "CUS-4417"
ORDER_ID = "ORD-7731"
LINE_ID = "LN-22"
SUBTOTAL = 139.99
TOTAL = 149.99

#: Five tools, one per hop. The descriptions say where the argument comes from,
#: because a model that guesses gets an error and burns a turn.
TOOLS: list[dict[str, Any]] = [
    {
        "name": "lookup_customer",
        "description": "Return the internal customer id for a customer's full name.",
        "parameters": {
            "type": "object",
            "properties": {
                "customer_name": {"type": "string",
                                  "description": "The customer's full name."},
            },
            "required": ["customer_name"],
        },
    },
    {
        "name": "list_orders",
        "description": (
            "Return the id of a customer's most recent order. The customer id "
            "must come from lookup_customer; it cannot be guessed."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "customer_id": {"type": "string",
                                "description": "A customer id from lookup_customer."},
            },
            "required": ["customer_id"],
        },
    },
    {
        "name": "get_order_lines",
        "description": (
            "Return the id of the single line on an order. The order id must "
            "come from list_orders; it cannot be guessed."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "order_id": {"type": "string",
                             "description": "An order id from list_orders."},
            },
            "required": ["order_id"],
        },
    },
    {
        "name": "get_line_price",
        "description": (
            "Return the pre-tax subtotal in USD for an order line. The line id "
            "must come from get_order_lines; it cannot be guessed."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "line_id": {"type": "string",
                            "description": "A line id from get_order_lines."},
            },
            "required": ["line_id"],
        },
    },
    {
        "name": "apply_tax",
        "description": (
            "Return the tax-inclusive total in USD for a pre-tax subtotal. The "
            "subtotal must come from get_line_price."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "subtotal_usd": {"type": "number",
                                 "description": "A subtotal from get_line_price."},
            },
            "required": ["subtotal_usd"],
        },
    },
]

#: The linkage `chained()` asserts: (producing tool, its output key,
#: consuming tool, the argument that must equal it).
LINKS: list[tuple[str, str, str, str]] = [
    ("lookup_customer", "customer_id", "list_orders", "customer_id"),
    ("list_orders", "order_id", "get_order_lines", "order_id"),
    ("get_order_lines", "line_id", "get_line_price", "line_id"),
    ("get_line_price", "subtotal_usd", "apply_tax", "subtotal_usd"),
]

HOPS = len(TOOLS)
TURNS = HOPS + 1


class ToolLog:
    """Records what was called with what, so chaining is asserted rather than assumed."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def dispatch(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        result = _dispatch(name, args)
        self.calls.append({"name": name, "args": args, "result": result})
        return result

    @property
    def names(self) -> list[str]:
        return [c["name"] for c in self.calls]

    def _first(self, name: str) -> dict[str, Any] | None:
        return next((c for c in self.calls if c["name"] == name), None)

    def hops_linked(self) -> int:
        """How many of the four links were actually made, in order."""
        made = 0
        for producer, key, consumer, arg in LINKS:
            first, second = self._first(producer), self._first(consumer)
            if not first or not second:
                break
            issued = first["result"].get(key)
            if issued is None or second["args"].get(arg) != issued:
                break
            made += 1
        return made

    def chained(self) -> bool:
        """True only if every hop ran with the value the previous hop returned."""
        return self.hops_linked() == len(LINKS)


def _dispatch(name: str, args: dict[str, Any]) -> dict[str, Any]:
    if name == "lookup_customer":
        if str(args.get("customer_name", "")).strip().lower() != CUSTOMER.lower():
            return {"error": f"no customer named {args.get('customer_name')!r}"}
        return {"customer_id": CUSTOMER_ID}
    if name == "list_orders":
        if args.get("customer_id") != CUSTOMER_ID:
            return {"error": f"unknown customer id {args.get('customer_id')!r}"}
        return {"order_id": ORDER_ID}
    if name == "get_order_lines":
        if args.get("order_id") != ORDER_ID:
            return {"error": f"unknown order id {args.get('order_id')!r}"}
        return {"line_id": LINE_ID}
    if name == "get_line_price":
        if args.get("line_id") != LINE_ID:
            return {"error": f"unknown line id {args.get('line_id')!r}"}
        return {"subtotal_usd": SUBTOTAL}
    if name == "apply_tax":
        # A float compared with `!=` is a trap on a value a model retyped, so
        # the tolerance is explicit and one cent wide.
        try:
            given = float(args.get("subtotal_usd"))
        except (TypeError, ValueError):
            return {"error": f"subtotal_usd must be a number, got {args.get('subtotal_usd')!r}"}
        if abs(given - SUBTOTAL) > 0.005:
            return {"error": f"unknown subtotal {given!r}"}
        return {"total_usd": TOTAL}
    return {"error": f"no such tool {name!r}"}


def answer_correct(text: str) -> bool:
    """The final text states the tax-inclusive total. Tolerant of symbols and prose."""
    if not text:
        return False
    return "149.99" in text.replace(",", "").replace("$", "")
