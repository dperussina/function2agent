"""Wiring: load config, load the corpus, run the selected checks."""

from __future__ import annotations

import json
from pathlib import Path

from . import checks as _checks  # noqa: F401  (import registers every check)
from . import corpus as corpus_mod
from . import search as search_mod
from .registry import Check, all_checks, get
from .report import Result

DEFAULT_CONFIG = Path(__file__).with_name("config.json")


def load_config(path: Path | None = None) -> dict:
    return json.loads((path or DEFAULT_CONFIG).read_text(encoding="utf-8"))


def select(names: list[str] | None, skip: list[str] | None) -> list[Check]:
    chosen = all_checks() if not names else [c for c in (get(n) for n in names) if c]
    if not names:
        chosen = [c for c in chosen if c.default_on]
    if skip:
        chosen = [c for c in chosen if c.name not in set(skip)]
    return chosen


def run_checks(
    root: Path,
    *,
    config: dict | None = None,
    only_paths: list[str] | None = None,
    names: list[str] | None = None,
    skip: list[str] | None = None,
) -> tuple[Result, list[Check]]:
    cfg = config or load_config()
    the_corpus = corpus_mod.load(root, cfg, only=only_paths)
    index = search_mod.build(root, cfg) if not only_paths else search_mod.SearchIndex(
        files={d.relpath: d.text for d in the_corpus.documents}
    )

    result = Result()
    ctx: dict = {
        "config": cfg,
        "search": index,
        "skip": lambda name, reason: result.skipped.append((name, reason)),
    }

    selected = select(names, skip)
    for chk in selected:
        result.extend(chk.fn(the_corpus, ctx))
    return result, selected


def unknown_names(names: list[str]) -> list[str]:
    return [n for n in names if get(n) is None]
