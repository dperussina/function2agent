"""A whole-repository text index, used to say where else a token appears.

Two questions need answering about any quoted figure, and they are different
questions. *Is it authoritative* — does it occur in a findings document — and
*does it occur anywhere at all*. A figure that appears in five documents and no
finding is a propagated claim that lost its source. A figure that appears in
exactly one place is a typo. Distinguishing those is most of the triage work, so
the index exists to do it mechanically.
"""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass
from pathlib import Path


@dataclass
class SearchIndex:
    files: dict[str, str]  # relpath -> raw text

    def where(self, needle: str) -> list[str]:
        return sorted(rel for rel, text in self.files.items() if needle in text)

    @staticmethod
    def summarise(paths: list[str], limit: int = 3) -> str:
        if len(paths) <= limit:
            return ", ".join(paths)
        return ", ".join(paths[:limit]) + f", (+{len(paths) - limit} more)"

    def occurs(self, needle: str) -> bool:
        return any(needle in text for text in self.files.values())

    def subset(self, patterns: list[str]) -> SearchIndex:
        return SearchIndex(
            files={
                rel: text
                for rel, text in self.files.items()
                if any(fnmatch.fnmatch(rel, p) for p in patterns)
            }
        )


def build(root: Path, config: dict) -> SearchIndex:
    exts = set(config["search_extensions"])
    exclude = config["search_exclude"]
    files: dict[str, str] = {}
    for entry in config["search_roots"]:
        base = root / entry
        paths = [base] if base.is_file() else sorted(base.rglob("*")) if base.is_dir() else []
        for path in paths:
            if not path.is_file() or path.suffix.lower() not in exts:
                continue
            rel = path.relative_to(root).as_posix()
            if any(fnmatch.fnmatch(rel, p) for p in exclude):
                continue
            try:
                files[rel] = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
    return SearchIndex(files=files)
