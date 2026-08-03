"""The check registry.

A check is a function `(Corpus, dict) -> list[Violation]` registered under a
short stable name. Adding one is a decorator and an import; nothing else in the
tool needs to know it exists.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from .corpus import Corpus
from .report import Violation

CheckFn = Callable[[Corpus, dict], list[Violation]]


@dataclass(frozen=True)
class Check:
    name: str
    summary: str
    fn: CheckFn
    default_on: bool = True


_REGISTRY: dict[str, Check] = {}


def check(name: str, summary: str, *, default_on: bool = True):
    def wrap(fn: CheckFn) -> CheckFn:
        if name in _REGISTRY:
            raise ValueError(f"duplicate check name: {name}")
        _REGISTRY[name] = Check(name=name, summary=summary, fn=fn, default_on=default_on)
        return fn

    return wrap


def all_checks() -> list[Check]:
    return [_REGISTRY[k] for k in sorted(_REGISTRY)]


def get(name: str) -> Check | None:
    return _REGISTRY.get(name)
