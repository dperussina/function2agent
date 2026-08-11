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

    Three things are reported per unit besides the digest, and which of them fires
    is decided by `attest.predecessor`, read **before** `build` overwrites the
    record it describes:

    * the state of the record being replaced, whenever that state is one in which
      no baseline can be read from it. Until 2026-08-11 this was silent, and the
      silence was the defect: the only line this function printed in that state
      was `the pinned digest already matches; nothing to ratify`, which is a true
      statement about the pin and reads as a statement about the tree. It was
      reachable *only* from a corrupted or absent record plus a generation-1 pin,
      or from a readable predecessor sitting one generation below the pin — never
      from a plain rebuild, because `generation` is inside the digested document
      and moves every time.
    * whether the attested tree has moved, by comparing `tree_sha256` against the
      same field in the record the pin covers. That is the one field a rebuild
      does not move, so this is the report the arm above was misread as making,
      and it is reachable on an ordinary rebuild.
    * that the pin needs no edit, when the bytes written are the pinned bytes —
      which is a real state after a rebuild that lands back on a ratified record,
      and is suppressed when the predecessor was in `attest.NO_BASELINE`, because
      there the sentence would be reassurance emitted over a record that had just
      been found corrupt.

    None of the three writes a pin, and the tree-unmoved line in particular does
    not make act one satisfy act two: the record it describes is new bytes, so
    `preserved-evidence` reports `unratified` until a human moves the digest.

    **The asymmetry in the tree-moved bullet is deliberate. Ruled 2026-08-11: the
    unmoved tree gets a line, the moved tree gets no counterpart, and that stays.**
    What the line adds is not identification — the new digest and `currently
    pinned` print in both states, so the two are already told apart — it is
    *reassurance*, and the asymmetry runs in the fail-safe direction. Wrongly
    **present**, the reassurance lets a human skip ratification of a tree that did
    move, which is the false-reassurance defect `f7ade9f` closed and
    `test_reporting_an_unmoved_tree_does_not_ratify_it` pins against. Wrongly
    **absent**, it costs a ratification of a tree that had not moved: mildly
    wasteful, and nothing is lost. **The general form is that a claim licensing a
    reader to skip work must be earned and stated positively, and its absence must
    mean do the work. Shaped the other way round — earned in order to *do* the
    work — the same report fails open.**

    `tools/README.md`'s emptiness-test inversion says to verify by presence and
    never by absence, and a reader arriving here will reach for it as the reason to
    add the line. **It is not this case.** There a check's silence could not
    separate success from total destruction, so an absence carried no information
    whatever. Here the digest separates the two states, and the only thing gated on
    this line's presence is the shortcut.

    No test prices adding it: `test_a_moved_tree_is_not_reported_as_unmoved`
    asserts only the absence of `the attested tree has not moved` and of `nothing
    to ratify`, and a distinct moved-tree line contains neither needle. **That cuts
    the other way too — a bare `else` on the comparison below would be equally
    unpriced, and it would be wrong.** `baseline` is `None` for every
    `attest.NO_BASELINE` state and for `unratified`, so an `else` would report a
    moved tree in exactly the states where the WARNING above says whether the tree
    moved is not known from here.

    **That arm was offered on 2026-08-11 and is declined — recorded here so the
    offer is not re-derived.** The reason is not cost. The line it would assert
    against does not exist, so it has no needle and would have to recognise a
    movement claim by its wording, pinning a *vocabulary* rather than a
    *behaviour* — stale the moment someone words the line differently from
    whatever the test guessed, which is the change-detector shape this repository
    has already declined twice. Two constructions escape the needle and neither
    rescues the arm: an exact-output assertion over these states is sound but pins
    *every* line's wording instead of one, so it fails the same objection harder;
    and asserting that the comparison below carries no `else` pins a code shape
    that today implies the property without asserting it, and stays green against
    a movement claim printed anywhere else in this function.

    **What would make it buildable, so this is a judgement and not a dead end —
    and it is two things rather than one.** A moved-tree line existing, which
    gives the assertion a needle. Or this function's output acquiring a
    machine-readable structure, which gives it a *field* and retires the wording
    problem entirely: today `main` returns at the `--reattest` branch before
    `--format` is read, so nothing here is anything but untagged prose.
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
    matched: list[str] = []
    for u in units:
        # Read the outgoing record before it is overwritten. Afterwards there is
        # nothing left to ask what state it was in, which is how the state came to
        # be unreported in the first place.
        state, baseline = attest.predecessor(root, u)
        _text, digest = attest.build(root, u, reason=reason, attested_at=stamp)
        doc = attest.load(root / u["attestation"])
        print(
            f"{u['name']}: wrote {u['attestation']} "
            f"(generation {doc['generation']}, {doc['file_count']} file(s))"
        )
        if state in attest.NO_BASELINE:
            print(f"  WARNING: the record this replaced was {state}, so no baseline")
            print("  could be read out of it and whether the attested tree moved is")
            print("  not known from here")
            if state in attest.RESTARTS_THE_COUNT:
                print("  WARNING: and the generation above restarted at 1 rather than")
                print("  counting on from the record that is now gone")
        print(f'  ratify by setting  "attestation_sha256": "{digest}"')
        print(f"  currently pinned    {u.get('attestation_sha256')}")
        if baseline is not None and baseline == doc["tree_sha256"]:
            print("  the attested tree has not moved since the ratified attestation;")
            print("  this record differs from it in generation, date and reason only")
        if digest == u.get("attestation_sha256"):
            matched.append(u["name"])
            if state not in attest.NO_BASELINE:
                print("  these bytes are the pinned bytes; nothing to ratify")
    print(
        "\nThe attestation is written and NOT ratified. `preserved-evidence` stays\n"
        "red until the digest above is pinned in tools/corpuscheck/config.json by\n"
        "hand, in the same commit as the edit it covers. Rebuilding and ratifying\n"
        "are two acts on purpose: an attestation a tool can refresh attests nothing."
    )
    if matched:
        # The paragraph above is false for these units and was printed anyway. A
        # rebuild reaches this state only by reproducing a ratified record byte for
        # byte, which asserts nothing a human has not already signed off — so the
        # gate going green with nobody acting is not the two-act rule failing. It
        # is still the one case where the sentence above does not apply, and saying
        # so is the difference between reporting it and being quiet about it.
        print(
            "\nExcept for: " + ", ".join(matched) + "\n"
            "The bytes written for that unit ARE the pinned bytes, so it is green\n"
            "with nobody having ratified anything — which is only reachable by\n"
            "reproducing a record a human already ratified. Where a line above\n"
            "names the record that was replaced, that is what happened: a corrupt\n"
            "witness over an unmoved tree, restored rather than re-attested."
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
