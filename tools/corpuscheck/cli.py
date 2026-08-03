"""Command line for corpuscheck."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .registry import all_checks
from .report import format_json, format_summary, format_text
from .runner import load_config, run_checks, unknown_names


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="check_corpus.py",
        description="Mechanical consistency checks over the function2agent corpus.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "exit codes:\n"
            "  0  no errors (warnings may be present)\n"
            "  1  at least one error-severity violation\n"
            "  2  bad invocation\n"
            "\n"
            "Use --report-only while the corpus is mid-edit: it prints everything\n"
            "and always exits 0.\n"
        ),
    )
    p.add_argument(
        "--root",
        type=Path,
        default=None,
        help="repository root (default: the parent of tools/)",
    )
    p.add_argument(
        "--path",
        action="append",
        default=None,
        metavar="PATH",
        help="restrict the scan to this path; repeatable. Used for fixtures.",
    )
    p.add_argument(
        "--check",
        action="append",
        default=None,
        metavar="NAME",
        help="run only this check; repeatable",
    )
    p.add_argument(
        "--skip",
        action="append",
        default=None,
        metavar="NAME",
        help="skip this check; repeatable",
    )
    p.add_argument("--config", type=Path, default=None, help="alternate config.json")
    p.add_argument(
        "--format",
        choices=("text", "json", "summary"),
        default="text",
        help="output format (default: text)",
    )
    p.add_argument(
        "--report-only",
        action="store_true",
        help="always exit 0; for informational runs while the corpus is being edited",
    )
    p.add_argument(
        "--warnings-as-errors",
        action="store_true",
        help="exit non-zero on warnings too",
    )
    p.add_argument("--no-hints", action="store_true", help="omit the hint line")
    p.add_argument("--list-checks", action="store_true", help="print the check set and exit")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.list_checks:
        width = max(len(c.name) for c in all_checks())
        for c in all_checks():
            flag = "" if c.default_on else "  (off by default)"
            print(f"{c.name:<{width}}  {c.summary}{flag}")
        return 0

    for group in (args.check or [], args.skip or []):
        bad = unknown_names(group)
        if bad:
            print(
                f"unknown check(s): {', '.join(bad)}\n"
                f"known: {', '.join(c.name for c in all_checks())}",
                file=sys.stderr,
            )
            return 2

    root = (args.root or Path(__file__).resolve().parents[2]).resolve()
    if not root.is_dir():
        print(f"root is not a directory: {root}", file=sys.stderr)
        return 2

    config = load_config(args.config)
    result, _selected = run_checks(
        root,
        config=config,
        only_paths=args.path,
        names=args.check,
        skip=args.skip,
    )

    if args.format == "json":
        print(format_json(result))
    elif args.format == "summary":
        print(format_summary(result))
    else:
        print(format_text(result, show_hints=not args.no_hints))

    if args.report_only:
        return 0
    if result.errors:
        return 1
    if args.warnings_as_errors and result.warnings:
        return 1
    return 0
