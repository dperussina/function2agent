"""Analyzer fixture — a synthetic target whose correct derivation is decidable by reading it.

**Not** a copy of anything, and deliberately not derived from the source the
analyzer was written against. See `../README.md` for why that construction is
the default here.

Every function below exists to exercise exactly one derivation rule or one
combination of them, and the expected output in `../inventory-service/expected.json`
was written from this file by hand before the analyzer existed.

Nothing here imports anything. A fixture with a dependency is a fixture that can
stop being analyzable for a reason that has nothing to do with the analyzer.
"""


class UnknownPart(Exception):
    """The part identifier is absent from the catalogue."""


class OutOfStock(Exception):
    """A lot exists and holds no units."""


def stock_report(lots: dict) -> dict:
    """Units on hand across the lots supplied.

    Exercises four rules at once: a leading guard, a raised exception class, a
    declared return type, and two aggregate bindings — one a count and one a
    sum over an element field.
    """
    if not lots:
        raise UnknownPart("no lots supplied")
    return {
        "lot_count": len(lots),
        "total_units": sum(lot["quantity"] for lot in lots),
    }


def oldest_lot_age(lots: dict) -> int:
    """Age in days of the oldest lot.

    A `max` aggregate returned directly rather than inside a mapping, with the
    postcondition stated as an assert over a *different* collection than the one
    the return value was computed from. The assert is the independent path: it
    reads `lots`, and the quantity under check is `oldest`.
    """
    ages = [lot["age_days"] for lot in lots]
    oldest = max(ages)
    assert oldest == max(lot["age_days"] for lot in lots)
    return oldest


def reserve(lots: dict, wanted: int) -> int:
    """Units reserved. Never more than requested.

    Exercises two guards and two exception classes, and has **no** aggregate
    binding — the return value is accumulated in a loop, which no rule here can
    turn into a recomputation. The expected output says so rather than
    inventing one, which is the case that keeps the analyzer honest.
    """
    if wanted <= 0:
        raise OutOfStock("nothing was requested")
    if not lots:
        raise UnknownPart("no lots supplied")
    taken = 0
    for lot in lots:
        if taken >= wanted:
            break
        taken = taken + lot["quantity"]
    return taken
