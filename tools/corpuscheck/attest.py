"""Bytes-level attestation over a tree of preserved evidence.

## The hole this closes

`specs/001-discovery-validation/harness/verifier-vs-judge/results/` holds twelve
committed run directories that OD-31 rules are **preserved evidence**: dated
records of runs that happened when the experiment was called `E8`, deliberately
not rewritten when it became `E19`. OD-31 also records, established by planting
the edit rather than by reading the code, that **nothing mechanical held them**.
An `E8`→`E19` rewrite in `20260803T092721-final-verify/manifest.json` left
`freeze.py --verify` reading *intact*, `neutralise_decision.py --check` passing
and `check_corpus.py` at zero errors.

Three separate mechanisms looked like they should have caught it and none could:

* a manifest **records** a `harness_fingerprint`, which is a self-report — no
  hash anywhere covers a manifest's own bytes;
* `corpus_freeze.json` pins eleven `ceiling-test` run directories belonging to a
  **different harness** and contains nothing under this `results/` tree at all;
* `dry-run-verdict` reads what an artifact *claims*, not what its bytes are, so
  a rewrite that changes no claim is invisible to it.

So the ruling was the whole of what protected them, and a ruling is not a gate.

## Why the witness lives outside the tree it attests

The attestation is a single record of per-file SHA-256 digests held **outside**
the tree, and that placement is the entire mechanism rather than a filing
preference. A digest stored beside the bytes it covers is a self-report of
exactly the kind the manifest already was; moving it out is what makes it a
witness. Nothing under `results/` is added, removed or renamed to install it.

The run directory names are not part of the mechanism either. They are committed,
cited by three findings, by `NEUTRALISATION.md` and by the harness index, and
OD-31 declines the cost of a filename chasing its subject. So the digest goes in
a record and not in a name.

A content-digest *filename* is a different thing from this and does not do this
job. `tests/batteries/results/removal-proofs-history/` names records that way, and
`removal_proofs_summary._archive` records the reason as same-second
disambiguation — two runs in one second are two files, two identical runs are one.
The names are written by the run that writes the bodies, nothing reads them back,
and the directory is git-ignored. See *The proof-history archive is not a
precedent for this* in `tools/README.md`.

## One unit per tree

`config.json` carries a unit per attested tree rather than one unit spanning
several. Two trees under this harness are preserved evidence on the same ruling —
`results/`, the twelve run directories, and `adjudication/`, the blind study — and
each has its own attestation and its own pin. Merged, a correction to either would
produce one digest, and ratifying it would silently ratify whatever had moved in
the other tree in the same window; split, `cli.reattest` reports the unmoved unit
as already matching, so the ratifier is told which body of evidence changed. The
merge is also unavailable mechanically: `measure` walks one tree, recursively and
unfiltered, so one unit over both would have to be rooted at the harness directory
and would cover the live code beside them.

## Two failures, and they are different acts

`verify` reports both and never conflates them:

  edited        a file under the tree does not match its attested digest, or the
                file set has changed. Somebody rewrote preserved evidence.

  unratified    the attestation's own bytes do not match the digest pinned in
                `config.json`. Somebody rebuilt the attestation. That is a
                legitimate act after a legitimate correction, and it is **not**
                sufficient on its own: the pin is edited by a human, in a second
                file, or the gate stays red.

That second failure is the one that keeps this from being vacuous. An
attestation a tool can refresh attests nothing, so `build` writes the record and
**prints** the line to paste; it never edits the pin, and no other tool in this
repository calls it. `neutralise_decision.py` — the tool that legitimately
edits these artifacts — does not import this module. Editing the evidence and
ratifying the edit are two acts by construction, not by convention.

## What this cannot do

It cannot stop an author who edits a record, rebuilds the attestation and moves
the pin in the same commit. Nothing in a repository can: the pin is text and the
author has write access. What it converts is a **silent** edit into a **visible**
one — three files in three trees, one of them a guard's own configuration, all
moving together and all in the diff. That is the standard OD-30 accepted for the
measurement record, applied here.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

#: Read in one megabyte blocks so a 4.8 MB tree of JSONL does not arrive in
#: memory whole. Not a tuning constant: any block size computes the same digest.
_BLOCK = 1 << 20


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(_BLOCK), b""):
            h.update(block)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def measure(tree: Path) -> dict[str, str]:
    """Every file under `tree`, by POSIX relative path, with its SHA-256.

    Recursive and unfiltered on purpose. A filter is a place for a file to hide,
    and the tree this covers is closed — nothing is expected to be added to it
    ever again, so an appearance is itself news that the check should report.
    """
    return {
        p.relative_to(tree).as_posix(): sha256_file(p)
        for p in sorted(tree.rglob("*"))
        if p.is_file()
    }


def tree_digest(files: dict[str, str]) -> str:
    """One digest over the whole file set, path and content together.

    Paths are hashed in as well as contents, so swapping two files' bytes moves
    the digest. Without that the set of digests would be attested and the
    assignment of digests to names would not.
    """
    h = hashlib.sha256()
    for rel in sorted(files):
        h.update(rel.encode("utf-8"))
        h.update(b"\0")
        h.update(files[rel].encode("ascii"))
        h.update(b"\n")
    return h.hexdigest()


def document(unit: str, tree_rel: str, files: dict[str, str], *, reason: str,
             generation: int, attested_at: str) -> str:
    """The attestation, serialised exactly as it will be hashed and written.

    Returned as text rather than as an object because the pin covers these
    bytes. Anything that reformats the record moves the pin, which is correct:
    the pin is over bytes and the record is the bytes.
    """
    doc = {
        "_comment": (
            "Bytes-level attestation over a tree of preserved evidence. Written by "
            "tools/corpuscheck/attest.py and read by the `preserved-evidence` check. "
            "This file is NOT a record of a run and carries no measurement; it is a "
            "witness held outside the tree it attests. Rebuilding it does not restore "
            "a green gate on its own — `preserved_evidence.units[].attestation_sha256` "
            "in tools/corpuscheck/config.json pins these bytes and is edited by hand."
        ),
        "unit": unit,
        "tree": tree_rel,
        "generation": generation,
        "attested_at": attested_at,
        "reason": reason,
        "file_count": len(files),
        "tree_sha256": tree_digest(files),
        "files": {rel: files[rel] for rel in sorted(files)},
    }
    return json.dumps(doc, indent=1, sort_keys=False) + "\n"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def verify(root: Path, unit: dict) -> list[tuple[str, str, str, str]]:
    """Complaints as `(kind, path, found, expected)`. Empty means attested.

    `kind` is `edited`, `added`, `removed`, `unratified` or `malformed`, and the
    caller turns each into a violation with its own hint. They are kept apart
    here because they are different events with different remedies, and a single
    "mismatch" would let a reader guess wrong about which one happened.
    """
    tree = root / unit["tree"]
    att_rel = unit["attestation"]
    att_path = root / att_rel
    out: list[tuple[str, str, str, str]] = []

    if not att_path.is_file():
        return [(
            "malformed", att_rel, "the attestation is missing",
            "a committed attestation over " + unit["tree"],
        )]

    raw = att_path.read_bytes()
    got_own = sha256_bytes(raw)
    want_own = unit["attestation_sha256"]
    if got_own != want_own:
        out.append(("unratified", att_rel, got_own, want_own))

    try:
        doc = json.loads(raw.decode("utf-8"))
        attested: dict[str, str] = doc["files"]
        recorded_tree = doc["tree_sha256"]
        recorded_count = doc["file_count"]
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
        out.append((
            "malformed", att_rel, f"unreadable attestation: {exc}",
            "an object carrying `files`, `file_count` and `tree_sha256`",
        ))
        return out

    # The record must agree with itself before it is used to judge anything.
    # A hand-edited `files` entry with the summary left alone would otherwise
    # pass a per-file comparison it had been rewritten to satisfy.
    if len(attested) != recorded_count:
        out.append((
            "malformed", att_rel, f"declares {recorded_count} file(s), lists {len(attested)}",
            "a declared count equal to the number of entries",
        ))
    if tree_digest(attested) != recorded_tree:
        out.append((
            "malformed", att_rel, "tree_sha256 does not cover the entries beside it",
            tree_digest(attested),
        ))

    present = measure(tree) if tree.is_dir() else {}
    if not tree.is_dir():
        return out + [(
            "removed", unit["tree"], "the attested tree is absent",
            f"{recorded_count} attested file(s)",
        )]

    for rel in sorted(set(attested) | set(present)):
        want, got = attested.get(rel), present.get(rel)
        target = f"{unit['tree']}/{rel}"
        if want is None:
            out.append(("added", target, got, "not attested"))
        elif got is None:
            out.append(("removed", target, "absent", want))
        elif want != got:
            out.append(("edited", target, got, want))
    return out


def build(root: Path, unit: dict, *, reason: str, attested_at: str) -> tuple[str, str]:
    """Write the attestation for `unit` and return `(text, its own digest)`.

    The digest is returned rather than recorded anywhere, because recording it
    beside the record it covers is the self-certification this module exists to
    refuse. The caller prints it and a human moves the pin.
    """
    tree = root / unit["tree"]
    if not tree.is_dir():
        raise FileNotFoundError(f"the attested tree is absent: {tree}")
    att_path = root / unit["attestation"]

    generation = 1
    if att_path.is_file():
        try:
            generation = int(load(att_path).get("generation", 0)) + 1
        except (json.JSONDecodeError, TypeError, ValueError):
            generation = 1

    text = document(
        unit["name"], unit["tree"], measure(tree),
        reason=reason, generation=generation, attested_at=attested_at,
    )
    att_path.parent.mkdir(parents=True, exist_ok=True)
    att_path.write_text(text, encoding="utf-8")
    return text, sha256_bytes(text.encode("utf-8"))
