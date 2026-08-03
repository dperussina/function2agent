#!/usr/bin/env python3
"""Withhold the decision-table classifications from every dry-run artifact.

Twelve run directories exist under `results/`. Every one carries
`spend.dry_run: true`, every judge row in every one of them comes from
`judge.StubJudge` — a deterministic hash of the trace key, `model: null`,
`cost_usd: 0.0` — and every one of them nevertheless committed a decision table
whose first row classified the verifier as a shipping product feature. The
figures that row reads (`MD`, `FOC`) are both defined over traces *the judge
passed*, so both are functions of the stub.

The hazard is not that the file is wrong on its face. It is that a stranger
greps this tree for a verdict in six months and finds one: the directory name
says `probe-readonly`, a rider two keys away says underpowered, and the DRY RUN
banner sits at the top of a different file. None of that is what a grep returns.

So this script does three things to each artifact, and each is one of the three
properties the edit had to satisfy:

  no greppable verdict   `decision` becomes `decision_void`, `rows` becomes
                         `rows_withheld`, and each row keeps its figures while
                         its classification clause is replaced by a withholding
                         notice. The removed clauses are not reproduced here,
                         in any key, in any file under `results/` — quoting one
                         to explain that it was removed would put the string
                         back. Finding 015 quotes the first row in full,
                         adjacent to the demonstration that it was unreachable.

  values preserved       No number is altered, rounded, recomputed or dropped.
                         `MD_best_discounted_pp`, the Wilson intervals, the
                         detected-key lists and the rendered figure prefixes of
                         each row all survive verbatim.

  edit disclosed         `_neutralised` is inserted as the first key of the
                         file, and `_stub` markers are attached to the `judge`
                         arms and to `md_upper_bound` — the blocks the rows
                         derive from, which is where the task's own diagnosis
                         put the omission.

Idempotent: a second run is a no-op. `--check` reports without writing, which
is what `selftest.py` calls.

    python3 neutralise_decision.py            # apply
    python3 neutralise_decision.py --check    # exit 1 if any artifact is unneutralised
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"

DATE = "2026-08-03"
FINDING = "specs/001-discovery-validation/findings/015-verifier-vs-judge-not-run.md"

WITHHELD = (
    "[CLASSIFICATION WITHHELD \u2014 stub judge, no judge verdict exists, "
    "nothing here clears or fails a gate; see _neutralised]"
)

#: (pattern, why the clause was withheld). Anchored on the three row templates
#: `analyze._decide` emits; a row this does not recognise is reported rather
#: than half-edited, because a partly-redacted verdict is worse than an intact
#: one — it looks handled.
ROW_RULES: list[tuple[re.Pattern, str]] = [
    (
        re.compile(
            r"^(MD_best \(discounted\) = [\d.]+ pp on arm \w+, "
            r"FOC = [\d.]+%, FPR = [\d.]+ pp):.*$"
        ),
        "MD is marginal detection over traces the judge passed and FOC is the "
        "fail-open catch rate over traces the judge failed open on; both "
        "denominators are stub output, so the row classified a hash",
    ),
    (
        re.compile(r"^(AUROC_judge 95% CI \[[\d.]+, [\d.]+\] contains 0\.5):.*$"),
        "the AUROC is computed over StubJudge scores, so the interval "
        "describes a hash function and not a judge",
    ),
    (
        re.compile(r"^(UNV_c1 = [\d.]+% > 50%):.*$"),
        "the figure is judge-independent and stands, but the clause is a "
        "decision-table outcome; the restriction it stated is preserved "
        "separately under `restrictions_still_binding`, and arm c1 is "
        "independently quarantined by PREREGISTRATION.md Amendment B5",
    ),
]

RESTRICTIONS = [
    "PREREGISTRATION.md 6.6 forbids describing arm c1 as covering the corpus "
    "while UNV_c1 exceeds 50%. Judge-independent, and it binds. Arm c1 is "
    "separately quarantined by Amendment B5 (c1_schema.verify raises).",
    "PREREGISTRATION.md 3.3(1): md_upper_bound is a statement about the JUDGE "
    "and must not appear in any sentence whose subject is the verifier.",
    "PREREGISTRATION.md 6.9: the false-success base is 10 across 2 families "
    "against a required n >= 30 across >= 3, and Amendment B4.4 establishes "
    "the rider can never lift on this corpus at any spend.",
]

STUB_MARKER = (
    "STUB \u2014 NOT A MEASUREMENT. Every figure in this block is computed from "
    "judge.StubJudge, a deterministic hash of the trace key. No model was "
    "called (spend.dry_run is true, cost_usd 0.0, model null). Anything "
    "derived from it, including the decision table, is stub output. "
    "Added " + DATE + " by neutralise_decision.py; no value was changed."
)


def _notice(n_rows: int) -> dict:
    return {
        "headline": "NOT A RESULT \u2014 no judge verdict exists in this run or "
        "anywhere in this experiment.",
        "date": DATE,
        "applied_by": "neutralise_decision.py (re-runnable, idempotent)",
        "what_changed": (
            "The `decision` key was renamed `decision_void` and the "
            f"classification clause of each of its {n_rows} row(s) was "
            "replaced by a withholding notice. `_stub` markers were added to "
            "the judge arms and to md_upper_bound. Nothing else was touched."
        ),
        "what_did_not_change": (
            "No numeric value anywhere in this file was altered, recomputed, "
            "rounded or removed. Each row keeps the rendered figures it "
            "opened with."
        ),
        "why": (
            "The rows were computed against stubbed judge verdicts and said "
            "so nowhere a reader would grep. A committed artifact that "
            "answers a grep for a verdict with a plausible one is the failure "
            "this project has now hit five times."
        ),
        "correction_class": (
            "WRONG, not narrowed and not superseded. The rows did not "
            "overstate a real measurement; they classified stub output."
        ),
        "load_bearing_correction": (
            "D_c is a DETECTION rate. The gate reads MD \u2014 MARGINAL "
            "detection, restricted to traces the judge passed. With no judge "
            "verdict, MD is undefined on this corpus: nothing here clears the "
            "gate and nothing here fails it. Text implying either is wrong, "
            "not merely unqualified."
        ),
        "what_is_still_real": (
            "The verifier arms, the taxonomy, the eligibility ledger, the "
            "denominators, the controls and the cost projection are computed "
            "from the frozen corpus and do not involve the judge. c2's "
            "detection census is a genuine offline result; its margin over a "
            "judge is unmeasured."
        ),
        "authority": FINDING,
        "amendment": "PREREGISTRATION.md Amendment B5",
        "guard": (
            "tools/check_corpus.py check `dry-run-verdict` fires on a "
            "verdict-shaped claim in any artifact of a run marked "
            "dry_run: true."
        ),
    }


def _void_rows(rows: list[str]) -> tuple[list[dict], list[str]]:
    out: list[dict] = []
    unrecognised: list[str] = []
    for i, row in enumerate(rows, start=1):
        for rx, why in ROW_RULES:
            m = rx.match(row)
            if m:
                out.append(
                    {
                        "row": i,
                        "figures_preserved": m.group(1),
                        "classification": "WITHHELD",
                        "text": f"{m.group(1)} \u2014 {WITHHELD}",
                        "why_withheld": why,
                        "emitted_by": "analyze._decide",
                    }
                )
                break
        else:
            unrecognised.append(row)
    return out, unrecognised


def neutralise(obj: dict) -> tuple[dict, list[str]]:
    """Return the rewritten object and any rows the rules did not recognise."""
    if "_neutralised" in obj:
        return obj, []

    problems: list[str] = []
    decision = obj.get("decision")
    if decision is None:
        return obj, ["no `decision` block"]

    rows = decision.get("rows", [])
    voided, unrecognised = _void_rows(rows)
    problems.extend(f"unrecognised decision row: {r}" for r in unrecognised)

    void = {
        "void": True,
        "not_a_verdict": (
            "This block stated an outcome. The outcome is withheld; the "
            "figures are not. See `_neutralised` at the head of this file."
        ),
        "rows_withheld": voided,
        "restrictions_still_binding": RESTRICTIONS,
    }
    for key, value in decision.items():
        if key == "rows":
            continue
        void[key] = value

    for arm in obj.get("judge", {}).values():
        if isinstance(arm, dict):
            arm["_stub"] = STUB_MARKER
    if isinstance(obj.get("md_upper_bound"), dict):
        obj["md_upper_bound"]["_stub"] = STUB_MARKER

    # `decision_void` keeps the position `decision` held, so a diff of the two
    # files is one renamed key and one rewritten block rather than a reordering.
    out = {"_neutralised": _notice(len(rows))}
    for key, value in obj.items():
        out["decision_void" if key == "decision" else key] = (
            void if key == "decision" else value
        )
    return out, problems


#: The report renders the same three rows as markdown bullets under a heading.
_REPORT_HEADING = "## Decision table"
_REPORT_HEADING_VOID = "## Decision table \u2014 VOID, NOT A VERDICT"
_REPORT_NOTE = (
    "> **NEUTRALISED " + DATE + " \u2014 the classifications below are withheld, "
    "the figures are not.** Every row was computed against stubbed judge "
    "verdicts (`judge.StubJudge`, a deterministic hash of the trace key); no "
    "judge verdict exists in this experiment. `D` is a *detection* rate and "
    "the gate reads `MD`, *marginal* detection over traces the judge passed, "
    "so **nothing here clears the gate or fails it**. Values are unchanged. "
    "See `analysis.json` `_neutralised`, `results/NEUTRALISATION.md`, and "
    "[finding 015](../../../../findings/015-verifier-vs-judge-not-run.md)."
)


def neutralise_report(text: str) -> tuple[str, list[str]]:
    if _REPORT_HEADING_VOID in text:
        return text, []
    if _REPORT_HEADING not in text:
        return text, ["no `## Decision table` heading"]

    lines = text.splitlines()
    out: list[str] = []
    problems: list[str] = []
    in_table = False
    for line in lines:
        if line.strip() == _REPORT_HEADING:
            out.append(_REPORT_HEADING_VOID)
            out.append("")
            out.append(_REPORT_NOTE)
            in_table = True
            continue
        if in_table and line.startswith("## "):
            in_table = False
        if in_table and line.startswith("- "):
            body = line[2:]
            for rx, _why in ROW_RULES:
                m = rx.match(body)
                if m:
                    out.append(f"- {m.group(1)} \u2014 {WITHHELD}")
                    break
            else:
                problems.append(f"unrecognised decision bullet: {body}")
                out.append(line)
            continue
        out.append(line)
    return "\n".join(out) + ("\n" if text.endswith("\n") else ""), problems


def run(check_only: bool) -> int:
    if not RESULTS.is_dir():
        print(f"no results directory at {RESULTS}", file=sys.stderr)
        return 1

    pending: list[str] = []
    problems: list[str] = []
    for run_dir in sorted(p for p in RESULTS.iterdir() if p.is_dir()):
        analysis = run_dir / "analysis.json"
        if analysis.is_file():
            obj = json.loads(analysis.read_text(encoding="utf-8"))
            if "_neutralised" not in obj:
                new, probs = neutralise(obj)
                problems.extend(f"{analysis.name} in {run_dir.name}: {p}" for p in probs)
                pending.append(str(analysis.relative_to(HERE)))
                if not check_only:
                    analysis.write_text(json.dumps(new, indent=1), encoding="utf-8")

        report = run_dir / "report.md"
        if report.is_file():
            text = report.read_text(encoding="utf-8")
            new_text, probs = neutralise_report(text)
            problems.extend(f"{report.name} in {run_dir.name}: {p}" for p in probs)
            if new_text != text:
                pending.append(str(report.relative_to(HERE)))
                if not check_only:
                    report.write_text(new_text, encoding="utf-8")

    for p in problems:
        print(f"PROBLEM  {p}", file=sys.stderr)
    verb = "would neutralise" if check_only else "neutralised"
    for p in pending:
        print(f"{verb}  {p}")
    if not pending:
        print("all dry-run artifacts already neutralised")
    if problems:
        return 1
    return 1 if (check_only and pending) else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="report without writing")
    args = ap.parse_args(argv)
    return run(args.check)


if __name__ == "__main__":
    sys.exit(main())
