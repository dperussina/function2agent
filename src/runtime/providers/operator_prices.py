"""OD-27 — the reader for `MODEL_PRICES_OPERATOR`, and nothing else.

The key's own declaration in `src/contracts/config.py` says what it holds: *"A
path to a declaration file, or the literal 'none'."* Until an entry point
existed, nothing read either form, so the key described a file format no code
could consume. This is that reader.

**It validates nothing itself, and that is the design.** Every rule about what
a declaration may say lives on `costs.OperatorPrice` and `costs.Rate` —
addresses already priced from a vendor page are refused, `REFUSED_ADDRESSES` is
refused, a single band is refused where the vendor's card has two columns and
no stated boundary, an accountable party and a declaration reference are both
required, and `OperatorPriceBook` refuses two declarations in force on one day.
A second opinion here would be a second definition of the same rules, which is
the drift this repository's tooling exists to prevent. This module turns JSON
into those constructors and lets them refuse.

**That rule cost a round trip and is recorded because it will be tempting
again.** This module first carried an enumerated set of permitted field names,
on the argument that an unrecognised key is a typo in a rate card and a reader
which ignores what it does not know would drop `effective_untill` and price a
model past the day its contract ended. The argument is right and the code was
redundant: a dataclass constructor already refuses an unexpected keyword, and
its refusal names the field. The removal proof is what said so — the arm came
back UNPROVEN because the test passed with the enumeration deleted, and it
passed because `OperatorPrice.__init__() got an unexpected keyword argument
'effective_untill'` contains the same substring the assertion was looking for.
So the mechanism under proof here is the **conversion**: a `TypeError` from
either constructor is turned into an `OperatorPriceError` naming the file and
the declaration's index, because a startup gate must refuse rather than exit on
an unhandled traceback.

**`'none'` is a value and not an absence**, which is the whole reason the key
carries `_NO_DEFAULT_OPERATOR_PRICES`: *nobody was asked* and *the operator
declares nothing* must stay distinguishable, and an optional key collapses
them. So the literal is spelled here and anything else is a path.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.runtime.providers.costs import (
    NO_OPERATOR_PRICES,
    OperatorPrice,
    OperatorPriceBook,
    OperatorPriceError,
    Rate,
)

#: The literal that declares nothing. Written down rather than left as an empty
#: string, because `load()` treats an empty environment variable as unset.
DECLARES_NOTHING = "none"


def load_operator_prices(setting: str) -> OperatorPriceBook:
    """Resolve `MODEL_PRICES_OPERATOR` to the book a price lookup is handed.

    Raises `OperatorPriceError` for every failure, so that a caller at startup
    has one thing to catch and one thing to quote back.
    """
    if setting == DECLARES_NOTHING:
        return NO_OPERATOR_PRICES
    path = Path(setting)
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise OperatorPriceError(
            f"MODEL_PRICES_OPERATOR={setting!r} is neither the literal "
            f"{DECLARES_NOTHING!r} nor a readable declaration file: {exc}. A "
            "deployment that declares nothing says so; it does not point at a "
            "file that is not there."
        ) from None
    try:
        document = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise OperatorPriceError(
            f"{path}: not JSON ({exc}). The declaration is a list of rate "
            "objects, or an object with a 'prices' key holding one."
        ) from None
    return OperatorPriceBook(
        tuple(_price(path, index, entry)
              for index, entry in enumerate(_entries(path, document)))
    )


def _entries(path: Path, document: Any) -> list[Any]:
    if isinstance(document, dict):
        document = document.get("prices")
    if not isinstance(document, list):
        raise OperatorPriceError(
            f"{path}: the declaration is a JSON list of rate objects, or an "
            "object with a 'prices' key holding one."
        )
    if not document:
        raise OperatorPriceError(
            f"{path}: declares no rates. An empty file and the literal "
            f"{DECLARES_NOTHING!r} would price identically and read "
            "differently — one says the operator declined and the other says "
            "somebody started a rate card and stopped. Set the key to "
            f"{DECLARES_NOTHING!r} to declare nothing."
        )
    return document


def _price(path: Path, index: int, entry: Any) -> OperatorPrice:
    where = f"{path}: declaration {index}"
    if not isinstance(entry, dict):
        raise OperatorPriceError(f"{where} is {type(entry).__name__}, not an object")
    tiers = entry.get("tiers")
    if not isinstance(tiers, list) or not tiers:
        raise OperatorPriceError(
            f"{where}: 'tiers' is a non-empty list of rate bands. A "
            "declaration with no band prices nothing."
        )
    fields = {name: value for name, value in entry.items() if name != "tiers"}
    try:
        return OperatorPrice(
            tiers=tuple(_rate(where, i, band) for i, band in enumerate(tiers)),
            **fields,
        )
    except TypeError as exc:
        raise OperatorPriceError(f"{where}: {exc}") from None


def _rate(where: str, index: int, band: Any) -> Rate:
    if not isinstance(band, dict):
        raise OperatorPriceError(
            f"{where}, band {index} is {type(band).__name__}, not an object")
    try:
        return Rate(**band)
    except TypeError as exc:
        raise OperatorPriceError(f"{where}, band {index}: {exc}") from None
