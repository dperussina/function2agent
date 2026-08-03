"""dry-run-verdict — a run that called no model may not publish an outcome.

The failure this catches, stated as it actually happened. Experiment E8 was
built, self-tested and dry-run at $0.00 against `judge.StubJudge`, a
deterministic hash of the trace key. Twelve run directories were committed.
Every one of them carried a decision table whose first row read

    MD_best (discounted) = 30.7 pp on arm c2, FOC = 65.8%, FPR = 0.0 pp: ...

followed by a clause promoting the verifier to a shipping product feature —
computed, in full, from the stub. Both figures in that row are defined only
over traces *the judge passed*. Nothing in the row, and nothing in the `judge`
block it derived from, said the judge was a hash.

Everything needed to notice was present and none of it was greppable. The
directory name said `probe-readonly`. A rider two keys away said underpowered.
`report.md` opened with a `DRY RUN — NOT RESULTS` banner. A stranger who greps
this tree for a verdict in six months reads none of that; they read the row.
This was the fifth artifact in this project that was plausible, greppable and
wrong, and it is the pattern that got the constitution amended.

**Scope.** A *run directory* is a directory under one of `dry_run.roots` whose
JSON declares `dry_run: true` — the harness's own marker, so the check inherits
whatever the harness means by it rather than guessing. Every artifact in that
directory with a listed extension is then scanned. Directories with no marker
are not scanned at all: a real run is entitled to publish a verdict, and this
check has no opinion about whether that verdict is right.

**Disclosure must be local, and that is the whole design.** The obvious rule —
exempt a file that discloses somewhere that it is a stub — is precisely the
rule the committed artifacts already satisfied, banner and all. So an exemption
must sit on the same line as the claim, where a grep hit shows it. Two kinds
qualify, and both are shapes the real corpus produces:

  disclosure   the line says what it is — `stub`, `dry run`, `WITHHELD`,
               `no judge verdict`, `NOT A RESULT`. A stub artifact stating that
               it is a stub is the thing this check must never punish.

  prohibition  the line forbids the claim rather than making it. The real
               artifacts carry *"A positive result licenses only 'consistent
               with H2, underpowered'; it does not license 'H2 confirmed'"* —
               which contains a hypothesis-outcome string and is the opposite
               of asserting one.

Struck text is exempt for the same reason it is under `inventory-count`: this
corpus supersedes by striking and dating, never by deleting.

**Amended 2026-08-03 — locality was per-line, and a line is not a location.**
Both exemptions were a substring test over the whole lowercased line, which made
two holes wide enough to walk a real verdict through. `void` is a disclosure
token and it lives inside `avoid`, so a line reading "avoid the gate" exempted
itself; and a single prohibition token exempted *every* claim on its line, so the
corpus's own shape — "licenses only 'consistent with H2, underpowered'; it does
not license 'H2 confirmed'" — would have gone on exempting an unrelated
`VERDICT:` appended to the same line. Tokens are now matched at their left word
boundary and must sit within `MAX_EXEMPTION_DISTANCE` of the claim they license.

**What it does not catch, said plainly.** An arbitrary English sentence
asserting an outcome. The patterns are a curated list in `config.json`, each
named and reasoned, matching the shapes this project's harnesses actually emit
plus the generic ones (`VERDICT:`, `statistically significant`, `H2
confirmed`). A verdict phrased in wording no rule anticipates passes. Widening
the patterns until they cannot is how a checker acquires a false-positive rate
and then gets switched off, which costs more than the misses.

`VERDICT`, `CONCLUSION` and `DECISION` are matched **case-sensitively, in
upper case only**, because `"verdict": "pass"` is a field name in every
`judge_calls.jsonl` and `verdicts.jsonl` row in the corpus and matching it
would produce thousands of hits on data that is not a claim about anything.
"""

from __future__ import annotations

import fnmatch
import json
import re
from pathlib import Path

from ..corpus import Corpus, mask_line
from ..figures import inside_spans, struck_spans
from ..registry import check
from ..report import ERROR, Violation

_MARKER_RE = re.compile(r'"dry_run"\s*:\s*true')

#: How far from a claim an exemption may sit and still be read as covering it.
#:
#: Measured, not guessed: across every artifact in the twelve dry-run directories
#: this corpus has committed, the furthest any real disclosure or prohibition
#: token sits from the claim it licenses is 19 characters. The bound is set six
#: times that so the shapes the harnesses emit keep working, and it still closes
#: the hole — an exemption 400 characters away at the far end of a long line was
#: exempting claims it had nothing to do with, and a single `licenses only` was
#: exempting every claim on its line rather than the one it disclaims.
MAX_EXEMPTION_DISTANCE = 120


def _token_positions(lowered: str, tokens: list[str]) -> list[int]:
    """Where each exemption token starts, matched only at a word boundary.

    A plain substring test found `void` inside `avoid` and `not results` inside
    `cannot results`-shaped prose, so writing "avoid" anywhere on a line bought
    an exemption from a word that disclosed nothing. Only the *left* edge is
    anchored: `neutralis` and `dry run` are deliberately prefixes, and must go
    on matching `neutralised` and `dry runs`.
    """
    out: list[int] = []
    for token in tokens:
        for m in re.finditer(r"(?<![a-z])" + re.escape(token), lowered):
            out.append(m.start())
    return out


def _covers(positions: list[int], start: int, end: int) -> bool:
    return any(
        (start - MAX_EXEMPTION_DISTANCE) <= p <= (end + MAX_EXEMPTION_DISTANCE)
        for p in positions
    )


def _declares_dry_run(path: Path) -> bool:
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return False
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        return bool(_MARKER_RE.search(text))
    return _has_true(obj, "dry_run")


def _has_true(node, key: str) -> bool:
    if isinstance(node, dict):
        if node.get(key) is True:
            return True
        return any(_has_true(v, key) for v in node.values())
    if isinstance(node, list):
        return any(_has_true(v, key) for v in node)
    return False


def _run_dirs(root: Path, roots: list[str]) -> list[Path]:
    seen: set[Path] = set()
    for pattern in roots:
        for path in root.glob(pattern):
            if path.is_dir():
                seen.add(path)
    return sorted(seen)


def _dry_run(run_dir: Path) -> bool:
    return any(_declares_dry_run(p) for p in sorted(run_dir.glob("*.json")))


@check("dry-run-verdict", "A run marked dry_run: true may not publish a verdict.")
def run(corpus: Corpus, ctx: dict) -> list[Violation]:
    config = ctx["config"]
    spec = config.get("dry_run")
    if not spec:
        ctx["skip"]("dry-run-verdict", "no `dry_run` block in config.json")
        return []

    run_dirs = _run_dirs(corpus.root, spec["roots"])
    if not run_dirs:
        ctx["skip"](
            "dry-run-verdict",
            "disabled: no run directories matched " + ", ".join(spec["roots"]),
        )
        return []

    patterns = [
        (rule["name"], re.compile(rule["pattern"], 0 if rule.get("case_sensitive") else re.I))
        for rule in spec["verdict_patterns"]
    ]
    why = {rule["name"]: rule["why"] for rule in spec["verdict_patterns"]}
    disclosure = [t.lower() for t in spec["disclosure_tokens"]]
    prohibition = [t.lower() for t in spec["prohibition_tokens"]]
    extensions = {e.lower() for e in spec["artifact_extensions"]}
    ignore = spec.get("ignore_files", [])

    out: list[Violation] = []
    for run_dir in run_dirs:
        if not _dry_run(run_dir):
            continue
        for path in sorted(run_dir.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in extensions:
                continue
            rel = path.relative_to(corpus.root).as_posix()
            if any(fnmatch.fnmatch(path.name, p) for p in ignore):
                continue
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except (UnicodeDecodeError, OSError):
                continue
            for lineno, raw in enumerate(lines, start=1):
                lowered = raw.lower()
                exempting = _token_positions(lowered, disclosure) + _token_positions(
                    lowered, prohibition
                )
                masked = mask_line(raw) if path.suffix.lower() in {".md", ".markdown"} else raw
                struck = struck_spans(masked)
                for name, rx in patterns:
                    for m in rx.finditer(masked):
                        if inside_spans(struck, m.start(), m.end()):
                            continue
                        if _covers(exempting, m.start(), m.end()):
                            continue
                        out.append(
                            Violation(
                                check="dry-run-verdict",
                                severity=ERROR,
                                path=rel,
                                line=lineno,
                                col=m.start() + 1,
                                found=f"{m.group(0).strip()}  ({name})",
                                expected="no outcome claim in a run that called no model, "
                                "or a disclosure on this line that the run is a stub",
                                hint=f"{why[name]}; the run directory declares "
                                "dry_run: true, so this claim was computed against "
                                "stub output — withhold the classification, keep the "
                                "figures, and say on this line that it is withheld",
                            )
                        )
    return out
