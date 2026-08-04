"""SPIKE - E16. The chained-tool scenario every arm drives. Do not import from product code.

One scenario, four SDKs. The scenario is deliberately *dependent*: the second
tool call cannot be constructed without the first call's return value, so an
arm that reaches the right answer has demonstrably chained rather than made two
independent calls that happened to both fire.

    Q: "What is the order total for customer Dana Whitfield?"

    lookup_customer_order("Dana Whitfield") -> {"order_id": "ORD-7731"}
    get_order_total("ORD-7731")             -> {"total_usd": 149.99}

`ORD-7731` appears nowhere in the prompt and is not derivable from it. A model
that answers 149.99 obtained the id from tool 1 and fed it to tool 2.

`get_order_total` rejects any order id it was not given, so a guessed id is a
visible failure rather than a silent pass.

Two hops is what finding 003 drove and it explicitly declined to read its pass
as clearance ("that is a weak result and should not be read as clearance").
This scenario is the same depth. It is *not* the long chain
`tasks.md` T061 specifies, and this harness does not claim to be that test —
see the README's Scope section.
"""
from __future__ import annotations

from typing import Any

QUESTION = "What is the order total for customer Dana Whitfield? Use the tools."

SYSTEM = (
    "You answer questions about orders using the supplied tools. "
    "You must look up the order id before you can fetch a total. "
    "When you have the total, state it as a plain number."
)

CUSTOMER = "Dana Whitfield"
ORDER_ID = "ORD-7731"
TOTAL = 149.99

# The two-hop dependency, as data, so every arm shares one definition.
TOOLS: list[dict[str, Any]] = [
    {
        "name": "lookup_customer_order",
        "description": "Return the order id for a customer's most recent order.",
        "parameters": {
            "type": "object",
            "properties": {
                "customer_name": {
                    "type": "string",
                    "description": "The customer's full name.",
                }
            },
            "required": ["customer_name"],
        },
    },
    {
        "name": "get_order_total",
        "description": (
            "Return the total in USD for an order id. The order id must come "
            "from lookup_customer_order; it cannot be guessed."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "order_id": {
                    "type": "string",
                    "description": "An order id previously returned by lookup_customer_order.",
                }
            },
            "required": ["order_id"],
        },
    },
]


class ToolLog:
    """Records what was called with what, so chaining can be asserted rather than assumed."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def dispatch(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        result = _dispatch(name, args)
        self.calls.append({"name": name, "args": args, "result": result})
        return result

    @property
    def names(self) -> list[str]:
        return [c["name"] for c in self.calls]

    def chained(self) -> bool:
        """True only if hop 2 ran with the id hop 1 returned."""
        first = next((c for c in self.calls if c["name"] == "lookup_customer_order"), None)
        second = next((c for c in self.calls if c["name"] == "get_order_total"), None)
        if not first or not second:
            return False
        returned = first["result"].get("order_id")
        return bool(returned) and second["args"].get("order_id") == returned


def _dispatch(name: str, args: dict[str, Any]) -> dict[str, Any]:
    if name == "lookup_customer_order":
        if str(args.get("customer_name", "")).strip().lower() != CUSTOMER.lower():
            return {"error": f"no customer named {args.get('customer_name')!r}"}
        return {"order_id": ORDER_ID}
    if name == "get_order_total":
        # A guessed id fails loudly. This is what makes `chained()` meaningful.
        if args.get("order_id") != ORDER_ID:
            return {"error": f"unknown order id {args.get('order_id')!r}"}
        return {"total_usd": TOTAL}
    return {"error": f"no such tool {name!r}"}


def answer_correct(text: str) -> bool:
    """The final text states the total. Tolerant of currency symbols and prose."""
    if not text:
        return False
    normalized = text.replace(",", "").replace("$", "")
    return "149.99" in normalized
