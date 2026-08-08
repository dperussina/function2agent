"""OD-27's reader: what a declaration file may say, and what it may not.

The module under test validates almost nothing itself — every rule about a
declared rate lives on `costs.OperatorPrice` and `costs.Rate`, which have their
own suite. What is tested here is the layer between a file and those
constructors, and the two rules that are the reader's own:

* `'none'` is a **value**, and a path to a file that is not there is not it;
* an unrecognised field is refused rather than dropped.

Both are the same failure in different clothes: a declaration that reads as
having been applied while pricing something other than what the rate card says.
"""

from __future__ import annotations

import json

import pytest

from src.runtime.providers.costs import NO_OPERATOR_PRICES, OperatorPriceError
from src.runtime.providers.operator_prices import (
    DECLARES_NOTHING,
    load_operator_prices,
)

DECLARATION = {
    "provider": "anthropic",
    "model": "claude-sonnet-99",
    "display_name": "Claude Sonnet 99",
    "tiers": [{"input_usd_per_mtok": 4.0, "output_usd_per_mtok": 20.0}],
    "declared_by": "platform-eng@acme",
    "declaration_ref": "contracts/anthropic-2026.pdf",
    "declared_on": "2026-08-01",
    "scope": "text tokens, standard tier",
}


def write(tmp_path, *entries):
    path = tmp_path / "rates.json"
    path.write_text(json.dumps({"prices": list(entries)}))
    return str(path)


def test_the_literal_declares_nothing() -> None:
    assert load_operator_prices(DECLARES_NOTHING) is NO_OPERATOR_PRICES


def test_a_declaration_reaches_the_book(tmp_path) -> None:
    book = load_operator_prices(write(tmp_path, DECLARATION))
    assert book.get("anthropic", "claude-sonnet-99")


def test_a_bare_list_is_accepted(tmp_path) -> None:
    path = tmp_path / "rates.json"
    path.write_text(json.dumps([DECLARATION]))
    assert load_operator_prices(str(path)).get("anthropic", "claude-sonnet-99")


def test_a_missing_file_is_not_the_literal(tmp_path) -> None:
    """The distinction `_NO_DEFAULT_OPERATOR_PRICES` exists to hold open. A
    reader that answered *the operator declares nothing* for a path that does
    not resolve would put the collapse back one layer down from the key."""
    with pytest.raises(OperatorPriceError, match="neither the literal"):
        load_operator_prices(str(tmp_path / "absent.json"))


def test_an_empty_declaration_is_refused(tmp_path) -> None:
    with pytest.raises(OperatorPriceError, match="declares no rates"):
        load_operator_prices(write(tmp_path))


def test_a_file_that_is_not_json_is_refused(tmp_path) -> None:
    path = tmp_path / "rates.json"
    path.write_text("provider: anthropic\n")
    with pytest.raises(OperatorPriceError, match="not JSON"):
        load_operator_prices(str(path))


def test_an_unrecognised_field_is_refused(tmp_path) -> None:
    """`effective_untill` is the case the enumeration is written for: a reader
    that ignores what it does not know prices a model past the date its
    contract ended, and reports nothing."""
    typo = {**DECLARATION, "effective_untill": "2026-09-01"}
    with pytest.raises(OperatorPriceError, match="effective_untill"):
        load_operator_prices(write(tmp_path, typo))


def test_an_unrecognised_band_field_is_refused(tmp_path) -> None:
    entry = {**DECLARATION,
             "tiers": [{"input_usd_per_mtok": 4.0, "output_usd_per_mtok": 20.0,
                        "min_output_tokens": 1000}]}
    with pytest.raises(OperatorPriceError, match="min_output_tokens"):
        load_operator_prices(write(tmp_path, entry))


def test_a_missing_required_field_is_refused_by_the_type(tmp_path) -> None:
    """Deferred, not duplicated. The reader does not know that a declaration
    needs an accountable party; `OperatorPrice` does, and a second opinion here
    would be a second definition of the same rule."""
    entry = {k: v for k, v in DECLARATION.items() if k != "declared_by"}
    with pytest.raises(OperatorPriceError, match="declared_by"):
        load_operator_prices(write(tmp_path, entry))


def test_a_declaration_addressing_a_priced_model_is_refused(tmp_path) -> None:
    entry = {**DECLARATION, "model": "claude-sonnet-5"}
    with pytest.raises(OperatorPriceError, match="already priced"):
        load_operator_prices(write(tmp_path, entry))


def test_a_tiers_key_that_is_not_a_list_is_refused(tmp_path) -> None:
    entry = {**DECLARATION, "tiers": {"input_usd_per_mtok": 4.0}}
    with pytest.raises(OperatorPriceError, match="non-empty list"):
        load_operator_prices(write(tmp_path, entry))
