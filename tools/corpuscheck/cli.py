"""Command line for corpuscheck."""

from __future__ import annotations

import argparse
import sys
from datetime import date
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
    p.add_argument(
        "--reattest",
        metavar="REASON",
        default=None,
        help="rewrite the preserved-evidence attestation and print the digest to "
        "ratify. Writes no pin: `preserved-evidence` stays red until a human "
        "moves attestation_sha256 in config.json.",
    )
    p.add_argument(
        "--unit",
        default=None,
        metavar="NAME",
        help="restrict --reattest to one preserved_evidence unit",
    )
    return p


def reattest(root: Path, config: dict, reason: str, unit_name: str | None) -> int:
    """Write the attestation for each present unit and report the pin to move.

    Deliberately a *separate act* from editing the records it covers, and
    deliberately incomplete: it stops one step short of green. The step it does
    not take is the one that carries the human decision, so an agent that
    rebuilds without ratifying leaves the gate red rather than leaving no trace.
    """
    from . import attest

    spec = config.get("preserved_evidence")
    if not spec:
        print("no `preserved_evidence` block in config.json", file=sys.stderr)
        return 2

    units = [u for u in spec["units"] if (root / u["tree"]).is_dir()]
    if unit_name:
        units = [u for u in units if u["name"] == unit_name]
    if not units:
        print(
            "no preserved_evidence unit to rebuild"
            + (f" named {unit_name!r}" if unit_name else " is present under this root"),
            file=sys.stderr,
        )
        return 2

    stamp = date.today().isoformat()
    for u in units:
        _text, digest = attest.build(root, u, reason=reason, attested_at=stamp)
        doc = attest.load(root / u["attestation"])
        print(
            f"{u['name']}: wrote {u['attestation']} "
            f"(generation {doc['generation']}, {doc['file_count']} file(s))"
        )
        print(f'  ratify by setting  "attestation_sha256": "{digest}"')
        if digest == u.get("attestation_sha256"):
            print("  the pinned digest already matches; nothing to ratify")
        else:
            print(f"  currently pinned    {u.get('attestation_sha256')}")
    print(
        "\nThe attestation is written and NOT ratified. `preserved-evidence` stays\n"
        "red until the digest above is pinned in tools/corpuscheck/config.json by\n"
        "hand, in the same commit as the edit it covers. Rebuilding and ratifying\n"
        "are two acts on purpose: an attestation a tool can refresh attests nothing."
    )
    return 0


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

    if args.reattest is not None:
        if not args.reattest.strip():
            print("--reattest needs a reason; the record carries it", file=sys.stderr)
            return 2
        return reattest(root, config, args.reattest.strip(), args.unit)

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
