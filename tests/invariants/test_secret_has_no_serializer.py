"""INV-007 — a credential value has no serializer (FR-036).

Structural rather than filtered. A redaction filter has to be remembered at
every call site; a missing serializer cannot be forgotten.

The tests below are written as *attempts to leak*, one per implicit path, and
each asserts the plaintext does not appear in the output. Asserting the
redaction marker is present would pass against an implementation that emitted
both.
"""

from __future__ import annotations

import copy
import json
import pickle

import pytest

from src.contracts.secret import REDACTED, Secret, SecretSerializationError

PLAINTEXT = "sk-do-not-log-me-4a91"


@pytest.fixture()
def secret() -> Secret:
    return Secret(PLAINTEXT, name="F2A_TARGET_CREDENTIAL")


def test_str_does_not_contain_the_value(secret: Secret) -> None:
    assert PLAINTEXT not in str(secret)
    assert str(secret) == REDACTED


def test_repr_does_not_contain_the_value(secret: Secret) -> None:
    assert PLAINTEXT not in repr(secret)


def test_fstring_does_not_contain_the_value(secret: Secret) -> None:
    assert PLAINTEXT not in f"{secret}"
    assert PLAINTEXT not in f"{secret!r}"
    assert PLAINTEXT not in f"{secret!s}"
    assert PLAINTEXT not in "%s" % (secret,)
    assert PLAINTEXT not in "{}".format(secret)
    assert PLAINTEXT not in f"{secret:>40}"


def test_json_refuses(secret: Secret) -> None:
    with pytest.raises((TypeError, SecretSerializationError)):
        json.dumps({"credential": secret})


def test_pickle_refuses(secret: Secret) -> None:
    with pytest.raises((SecretSerializationError, TypeError)):
        pickle.dumps(secret)


def test_copy_refuses(secret: Secret) -> None:
    with pytest.raises(SecretSerializationError):
        copy.copy(secret)
    with pytest.raises(SecretSerializationError):
        copy.deepcopy(secret)


def test_len_refuses_because_length_is_an_oracle(secret: Secret) -> None:
    with pytest.raises(SecretSerializationError):
        len(secret)


def test_exception_text_does_not_contain_the_value(secret: Secret) -> None:
    """The commonest accidental disclosure: a traceback."""
    with pytest.raises(SecretSerializationError) as caught:
        pickle.dumps(secret)
    assert PLAINTEXT not in str(caught.value)


def test_reveal_is_the_only_way_out(secret: Secret) -> None:
    assert secret.reveal() == PLAINTEXT


def test_fingerprint_identifies_without_disclosing(secret: Secret) -> None:
    fingerprint = secret.fingerprint()
    assert PLAINTEXT not in fingerprint
    assert len(fingerprint) == 12
    assert Secret(PLAINTEXT, name="other").fingerprint() == fingerprint
    assert Secret("different", name="x").fingerprint() != fingerprint


def test_no_attribute_exposes_the_value(secret: Secret) -> None:
    """The removal proof for an added convenience accessor.

    Someone adding `@property def value(self)` for convenience defeats the
    whole type. `__slots__` keeps the surface enumerable, so this can check it.
    """
    exposed = []
    for name in dir(secret):
        if name in ("reveal", "_value"):
            continue
        try:
            attribute = getattr(secret, name)
        except Exception:
            continue
        if callable(attribute):
            continue
        if PLAINTEXT in str(attribute):
            exposed.append(name)
    assert exposed == [], f"attributes disclose the credential: {exposed}"


def test_a_dict_containing_a_secret_does_not_print_it(secret: Secret) -> None:
    holder = {"credential": secret, "tenant": "t-1"}
    assert PLAINTEXT not in str(holder)
    assert PLAINTEXT not in repr(holder)
