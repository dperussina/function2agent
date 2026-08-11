"""preserved-evidence — a committed record of a run must still be its own bytes.

The failure this catches, stated as it actually happened. OD-31 renumbered an
experiment from `E8` to `E19` and ruled that twelve committed run directories
under `harness/verifier-vs-judge/results/` keep the name they were recorded
under. The same entry records that **nothing mechanical enforced the ruling**,
and it establishes that by planting the edit rather than by reading the code: an
`E8`→`E19` rewrite in `20260803T092721-final-verify/manifest.json` left
`freeze.py --verify` reading *intact*, `neutralise_decision.py --check` passing
and `check_corpus.py` at zero errors. Every gate in the repository was green over
a falsified record.

`dry-run-verdict`, the check built at this boundary for the neighbouring defect,
could not have caught it and still cannot: it reads what an artifact **claims**.
This one reads what an artifact **is**. That is the whole difference between the
two, and it is why this is a second check rather than a widening of that one.

## What it compares

Per unit in `config.json`'s `preserved_evidence.units`: every file under `tree`,
by SHA-256, against the digests in `attestation` — a witness held outside the
tree, because a digest stored beside the bytes it covers is the same self-report
the manifest already was. See `..attest` for why the placement is the mechanism.

Five kinds are reported and never merged, because they are different events:

  edited        a file's bytes moved. This is the plant.
  added         a file appeared in a closed tree.
  removed       an attested file, or the whole tree, is gone.
  unratified    the attestation's own bytes do not match the pin. Somebody
                rebuilt it and no human has ratified the rebuild yet.
  malformed     the attestation disagrees with itself, or cannot be read.

## The ratification split, which is the point rather than an inconvenience

A legitimate correction — the next neutralisation is the named example, and those
records were already edited once under one — proceeds in two acts that cannot
collapse into one:

    python3 tools/check_corpus.py --reattest "why"   # writes the record
    # then a human moves `attestation_sha256` in config.json

`--reattest` prints the new digest and never writes the pin. Nothing else in the
repository calls `attest.build`, and in particular `neutralise_decision.py` does
not: a tool that edited the evidence and refreshed its own attestation would
reproduce, one layer down, exactly the vacuity this check exists to close.

## What it does not claim

That the attested bytes are *correct*. It claims only that they are the bytes a
human ratified, and that a change to them is loud. A wrong figure committed
before the attestation was built is attested wrongness, and this check will
defend it as faithfully as it defends anything else. `numeric-provenance` and
`dry-run-verdict` are the checks with opinions about content.
"""

from __future__ import annotations

from ..attest import verify
from ..registry import check
from ..report import ERROR, Violation

_HINTS = {
    "edited": (
        "this file is preserved evidence — a dated record of a run — and its bytes "
        "moved. If the edit is wrong, restore the file. If it is a deliberate "
        "correction, run `python3 tools/check_corpus.py --reattest \"why\"` and then "
        "move `attestation_sha256` in tools/corpuscheck/config.json by hand; the "
        "rebuild alone does not clear this"
    ),
    "added": (
        "the attested tree is closed and a file appeared in it. Adding to a record "
        "of runs that already happened needs the same ratification an edit does"
    ),
    "removed": (
        "an attested file is gone. A record of a run is not deleted to make a gate "
        "pass; if the removal is deliberate, ratify it the same way an edit is"
    ),
    "unratified": (
        "the attestation was rebuilt and nobody has ratified the rebuild. Paste the "
        "digest under `found` into `preserved_evidence.units[].attestation_sha256` in "
        "tools/corpuscheck/config.json, in the same commit as the edit it covers, so "
        "the two acts appear together in one diff"
    ),
    "malformed": (
        "the attestation cannot be used to judge anything in this state. Rebuild it "
        "with `python3 tools/check_corpus.py --reattest \"why\"` and ratify the result"
    ),
}

_EXPECTED = {
    "edited": "the attested SHA-256 of this preserved record",
    "added": "no file here that the attestation does not cover",
    "removed": "the attested file, present",
    "unratified": "the attestation digest pinned in config.json",
    "malformed": "an attestation that agrees with itself",
}


@check(
    "preserved-evidence",
    "A committed record of a run matches its attested SHA-256, outside the tree.",
)
def run(corpus, ctx: dict) -> list[Violation]:
    spec = (ctx["config"] or {}).get("preserved_evidence")
    if not spec:
        ctx["skip"]("preserved-evidence", "no `preserved_evidence` block in config.json")
        return []

    # Scope is keyed on the attestation, never on the tree. Keying it on the tree
    # is the first thing this was written with and it was wrong: a check that goes
    # out of scope when the thing it protects is absent is disabled by deleting
    # that thing, and on 2026-08-11 deleting all 59 records took this check to
    # `skipped` while it announced itself disabled. The attestation is committed
    # beside the tree it covers, so its presence is what says the unit belongs to
    # this root, and an absent tree is then the `removed` violation rather than
    # silence.
    units = [u for u in spec["units"] if (corpus.root / u["attestation"]).is_file()]
    if not units:
        # Announced once for the whole check rather than per absent unit: the
        # unit list spans this repository and the two fixture corpora, so in
        # every real root most of it is legitimately elsewhere and a skip line
        # per unit would be noise that trains a reader to ignore skip lines.
        ctx["skip"](
            "preserved-evidence",
            "disabled: no attestation present — looked for "
            + ", ".join(u["attestation"] for u in spec["units"]),
        )
        return []

    out: list[Violation] = []
    for unit in units:
        for kind, path, found, expected in verify(corpus.root, unit):
            out.append(
                Violation(
                    check="preserved-evidence",
                    severity=ERROR,
                    path=path,
                    line=1,
                    found=f"{found}  ({kind})",
                    expected=_EXPECTED[kind] if kind != "malformed" else expected,
                    hint=_HINTS[kind],
                )
            )
    return out
