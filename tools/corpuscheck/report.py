"""Violation records and the three output formats.

A violation is only useful if a reader can act on it without opening a second
window, so every one carries file, line, what was found, and what was expected.
`hint` is for the thing that turns a puzzle into a fix — the nearest
authoritative figure, the heading that was probably meant, the row that got
orphaned.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field

ERROR = "error"
WARNING = "warning"

_SEVERITY_ORDER = {ERROR: 0, WARNING: 1}


@dataclass(frozen=True)
class Violation:
    check: str
    severity: str
    path: str
    line: int
    found: str
    expected: str
    hint: str = ""
    col: int | None = None

    def sort_key(self) -> tuple:
        return (
            _SEVERITY_ORDER.get(self.severity, 9),
            self.path,
            self.line,
            self.check,
            self.found,
        )


@dataclass
class Result:
    violations: list[Violation] = field(default_factory=list)
    # Checks that ran but were skipped for a stated reason (missing input, etc).
    skipped: list[tuple[str, str]] = field(default_factory=list)

    def add(self, v: Violation) -> None:
        self.violations.append(v)

    def extend(self, vs: list[Violation]) -> None:
        self.violations.extend(vs)

    @property
    def errors(self) -> list[Violation]:
        return [v for v in self.violations if v.severity == ERROR]

    @property
    def warnings(self) -> list[Violation]:
        return [v for v in self.violations if v.severity == WARNING]


def format_text(result: Result, *, show_hints: bool = True) -> str:
    out: list[str] = []
    for check, reason in result.skipped:
        out.append(f"skipped  {check}: {reason}")
    if result.skipped:
        out.append("")

    by_path: dict[str, list[Violation]] = {}
    for v in sorted(result.violations, key=Violation.sort_key):
        by_path.setdefault(v.path, []).append(v)

    for path, vs in by_path.items():
        out.append(path)
        for v in vs:
            loc = f"{v.line}" if v.col is None else f"{v.line}:{v.col}"
            out.append(f"  {loc:>7}  {v.severity:<7} {v.check}")
            out.append(f"           found:    {v.found}")
            out.append(f"           expected: {v.expected}")
            if show_hints and v.hint:
                out.append(f"           hint:     {v.hint}")
        out.append("")

    n_err = len(result.errors)
    n_warn = len(result.warnings)
    out.append(f"{n_err} error(s), {n_warn} warning(s)")
    return "\n".join(out)


def format_json(result: Result) -> str:
    return json.dumps(
        {
            "violations": [asdict(v) for v in sorted(result.violations, key=Violation.sort_key)],
            "skipped": [{"check": c, "reason": r} for c, r in result.skipped],
            "counts": {"error": len(result.errors), "warning": len(result.warnings)},
        },
        indent=2,
    )


def format_summary(result: Result) -> str:
    """One line per check. For "did anything change" comparisons across runs."""
    counts: dict[tuple[str, str], int] = {}
    for v in result.violations:
        counts[(v.check, v.severity)] = counts.get((v.check, v.severity), 0) + 1
    rows = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    width = max((len(c) for (c, _), _ in rows), default=10)
    out = [f"{check:<{width}}  {sev:<7} {n}" for (check, sev), n in rows]
    out.append("")
    out.append(f"{len(result.errors)} error(s), {len(result.warnings)} warning(s)")
    return "\n".join(out)
