#!/usr/bin/env python3
"""What the pytest jobs actually ran — reader for the JUnit reports CI writes.

    python3 tools/pytest_outcomes.py [--collected COLLECT.txt] LABEL=report.xml ...

`pytest -q` prints `436 passed, 1 skipped`. That sentence names no skip, and a
privileged test that quietly skipped for want of a kernel facility is
indistinguishable in it from one that ran and passed. The two are different
claims about FR-048, FR-049 and FR-050, and OD-17 says there is no degraded
mode — so a skip that nobody can see is the state this file exists to remove.

`-rs` puts the reasons in the job log. That is worth having and it is not
enough on its own: the log is exactly the artifact that turned out to be
unreachable for run 30919927355, where a `?` in a job name cost the whole
removal-proof output. So the durable record is `--junitxml`, kept as an
artifact, and this is the renderer that turns it into something a person reads
on the run page.

WHY THIS CAN FAIL A JOB, AND THE TWO CASES IT FAILS FOR

`tools/removal_proofs_summary.py` sets the rule this follows: a renderer must
not become a second, weaker verdict. pytest's own exit status already decides
pass and fail, and **nothing here re-decides it** — a report full of failures
renders and exits 0, because the step that produced it has already gone red.

It fails for the two cases pytest's exit status cannot express, and both are
the same defect wearing different clothes:

  - **a report that is missing or unreadable.** A step that went green without
    leaving one measured something nobody can check afterwards.
  - **a report in which nothing ran.** `tests == 0` is the empty selector;
    `tests == skipped` is the suite that collected work and then declined all
    of it. Both exit 0 from pytest and both are green over an absent
    measurement.

Neither failure is about the code under test. Both are about the instrument.

THE PARTITION, WHICH NOTHING ELSE CHECKS

CI runs the suite as two halves, `-m "not privileged"` and `-m privileged`, and
takes the pair for the whole. Nothing verifies that it is. A marker expression
that stopped selecting a file, a marker renamed on one side only, or a test
carrying a spelling neither expression matches, all leave that test in no half
at all — and **both halves stay green**, because each is internally complete.
Given `--collected`, holding the output of a plain `pytest --collect-only -q`,
this compares the collected total against the sum of the halves and fails when
they disagree. The two sides of that comparison are both observations; neither
is a number anybody typed.

**Exit 2 is a third thing and is kept separate on purpose.** An interpreter
whose `xml.etree` cannot build a parser — Homebrew's CPython 3.14 on macOS
ships a `pyexpat` linked against the wrong `libexpat` and raises `ImportError`
from `ET.parse` — makes every report unreadable for a reason that has nothing
to do with the reports. Folding that into exit 1 would report "no record" for
a run whose records are all present and fine, which is the same
cannot-measure-scored-as-a-result confusion `tests/removal_proofs.sh` exits 2
for.
"""

from __future__ import annotations

import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

# `459/503 tests collected (44 deselected)` and `503 tests collected`. The
# denominator is the corpus; the numerator is whatever the invocation selected.
_COLLECTED = re.compile(r"^(?:(\d+)/)?(\d+) tests? collected", re.MULTILINE)


@dataclass
class Report:
    label: str
    path: str
    tests: int = 0
    failures: int = 0
    errors: int = 0
    skipped: int = 0
    seconds: float = 0.0
    skips: list[tuple[str, str]] = field(default_factory=list)

    @property
    def executed(self) -> int:
        """Outcomes that are evidence about the code. Skips are not."""
        return self.tests - self.skipped

    @property
    def passed(self) -> int:
        return self.tests - self.skipped - self.failures - self.errors


def _read(label: str, path: str) -> Report:
    report = Report(label=label, path=path)
    root = ET.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
    for suite in suites:
        report.tests += int(suite.get("tests", 0))
        report.failures += int(suite.get("failures", 0))
        report.errors += int(suite.get("errors", 0))
        report.skipped += int(suite.get("skipped", 0))
        report.seconds += float(suite.get("time", 0.0))
    for case in root.iter("testcase"):
        for skipped in case.findall("skipped"):
            name = "{}::{}".format(
                case.get("classname", "").replace(".", "/"), case.get("name", "")
            )
            reason = (skipped.get("message") or skipped.text or "").strip()
            report.skips.append((name, reason.splitlines()[0] if reason else ""))
    return report


class CannotRun(RuntimeError):
    """The interpreter cannot parse XML at all. Not a finding about a report."""


def _collected_total(path: str) -> int:
    """The corpus size, read out of a plain `pytest --collect-only -q` run."""
    try:
        text = open(path, encoding="utf-8", errors="replace").read()
    except OSError as exc:
        raise CannotRun(
            "no collection listing at {} ({}), so the partition cannot be "
            "checked against anything".format(path, exc)
        ) from exc
    matches = _COLLECTED.findall(text)
    if not matches:
        raise CannotRun(
            "the collection listing at {} carries no `N tests collected` "
            "line. pytest prints one on every run; its absence means the "
            "collection step did not do what this check reads.".format(path)
        )
    return int(matches[-1][1])


def render(pairs: list[tuple[str, str]], collected: str | None = None) -> int:
    print("## pytest outcomes\n")

    reports: list[Report] = []
    unreadable: list[tuple[str, str, str]] = []
    for label, path in pairs:
        try:
            reports.append(_read(label, path))
        except ImportError as exc:  # no usable XML parser in this interpreter
            raise CannotRun(
                "this interpreter cannot build an XML parser ({}), so every "
                "report reads as unreadable for a reason that is not about "
                "the reports. Refusing to report a finding.".format(exc)
            ) from exc
        except (OSError, ET.ParseError) as exc:
            unreadable.append((label, path, str(exc)))

    if unreadable:
        print("### NO REPORT\n")
        for label, path, exc in unreadable:
            print("- **{}** — no readable JUnit report at `{}` ({})".format(
                label, path, exc))
        print(
            "\nA pytest step that finished without leaving a report measured "
            "something nobody can check afterwards, which is the state this "
            "record exists to remove. Failing rather than letting a green "
            "tick stand in for evidence nobody can see.\n"
        )

    if reports:
        print("| suite | tests | passed | failed | errors | **skipped** | seconds |")
        print("|---|---:|---:|---:|---:|---:|---:|")
        for r in reports:
            print("| {} | {} | {} | {} | {} | **{}** | {:.1f} |".format(
                r.label, r.tests, r.passed, r.failures, r.errors,
                r.skipped, r.seconds))
        print()

    unpartitioned = 0
    if collected is not None and reports:
        total = _collected_total(collected)
        reported = sum(r.tests for r in reports)
        if total != reported:
            unpartitioned = total - reported
            print(
                "> **THE HALVES DO NOT COVER THE SUITE.** `--collect-only` "
                "finds **{}** test(s); the reports above account for **{}**. "
                "{} test(s) are in no half and therefore ran nowhere, while "
                "every half stayed green because each is internally "
                "complete.\n".format(total, reported, abs(unpartitioned))
            )
        else:
            print(
                "The two halves account for all **{}** collected test(s), so "
                "nothing fell between the marker expressions.\n".format(total)
            )

    empty = [r for r in reports if r.tests == 0]
    vacuous = [r for r in reports if r.tests and r.executed == 0]

    for r in empty:
        print(
            "> **{}: NOTHING WAS COLLECTED.** The selector matched no test at "
            "all, so this suite's green exit is a statement about an empty "
            "set.\n".format(r.label)
        )
    for r in vacuous:
        print(
            "> **{}: NOTHING WAS EXECUTED.** All {} collected test(s) skipped. "
            "OD-17 has no degraded mode, so a suite that collected work and "
            "then declined all of it has not exercised the mechanisms it "
            "names.\n".format(r.label, r.tests)
        )

    for r in reports:
        if not r.skips:
            if r.tests:
                print("**{}** — every collected test ran.\n".format(r.label))
            continue
        print("### {} — {} skipped, named\n".format(r.label, len(r.skips)))
        print(
            "A skipped test is not a passing test. Each line below is a "
            "mechanism this run did **not** exercise.\n"
        )
        for name, reason in r.skips:
            print("- `{}` — {}".format(name, reason or "no reason recorded"))
        print()

    print(
        "> These counts are a property of the runner they were taken on; the "
        "identity block above says which. A skip for want of a kernel "
        "facility and a skip for want of privilege are the same word here and "
        "different findings, so read the reason rather than the count.\n"
    )
    return 1 if (unreadable or empty or vacuous or unpartitioned) else 0


def main(argv: list[str]) -> int:
    pairs: list[tuple[str, str]] = []
    collected: str | None = None
    rest = list(argv[1:])
    while rest:
        arg = rest.pop(0)
        if arg == "--collected":
            if not rest:
                print("--collected needs a path", file=sys.stderr)
                return 2
            collected = rest.pop(0)
            continue
        label, sep, path = arg.partition("=")
        if not sep:
            label, path = path or label, label
        pairs.append((label, path))
    if not pairs:
        print(__doc__.strip().splitlines()[0], file=sys.stderr)
        print(
            "usage: pytest_outcomes.py [--collected COLLECT.txt] "
            "LABEL=report.xml [LABEL=report.xml ...]",
            file=sys.stderr,
        )
        return 2
    try:
        return render(pairs, collected)
    except CannotRun as exc:
        print("\n> **CANNOT RUN** — {}\n".format(exc))
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
