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

Two units in this repository are real evidence rather than fixtures, and they are
two rather than one so that a correction's blast radius equals its subject:
`verifier-vs-judge-results` over the twelve run directories, and
`verifier-vs-judge-adjudication` over the blind study beside them, which the first
version of this guard did not cover because its cost was priced over the run
directories alone. Each carries its own pin. `..attest` argues the split.

Five kinds are reported and never merged, because they are different events:

  edited        a file's bytes moved. This is the plant.
  added         a file appeared in a closed tree.
  removed       an attested file, or the whole tree, is gone.
  unratified    the attestation's own bytes do not match the pin. Somebody
                rebuilt it and no human has ratified the rebuild yet.
  malformed     the attestation disagrees with itself, cannot be read, or is
                not there at all.

A sixth, `undeclared`, is reported against `config.json` rather than against any
tree, because it is a defect in the unit list and not in a body of evidence.

## Which root a unit belongs to is declared, not inferred

Every unit names a `root.marker`, a path that is neither its `tree` nor its
`attestation`, and a unit is judged in exactly the roots where that path exists.
The declaration is what this check was missing, and its absence had reproduced
the failure the check exists to close, one layer up and inside the guard.

Scope was first keyed on `tree`, and deleting the protected directory took the
check to `skipped` while it announced itself disabled. Scope was keyed on
`attestation` next, and that filter merged two states that are not the same
event: a unit whose witness is *missing or mis-pathed*, and a fixture unit that
legitimately *lives under another root*. One list of units spans this repository
and the two fixture corpora, so most of it is out of scope in any given root and
the filter had to tolerate absence — which meant a real unit with a typo'd
`attestation` was dropped from the run and reported nothing. The check printed
`0 error(s), 0 warning(s)` and, because the per-check skip fired only when *no*
unit survived the filter, no skip line either. That is what a fully attested tree
prints. Somebody could hold a tree they believed was attested while nothing read
it, which is the exact class this guard was built to close.

Two consequences of the declaration, both of them the point:

* the `malformed` branch of `..attest.verify` that reports a missing attestation
  became reachable from the check, having been dead code under the old filter;
* a unit that declares no marker is a violation rather than a silent pass, since
  a unit that cannot be placed in a root cannot be judged in one.

## The ratification split, which is the point rather than an inconvenience

A legitimate correction — the next neutralisation is the named example, and those
records were already edited once under one — proceeds in two acts that cannot
collapse into one:

    python3 tools/check_corpus.py --reattest "why" --unit NAME   # writes the record
    # then a human moves that unit's `attestation_sha256` in config.json

`--unit` is named because the bare form rebuilds every unit whose tree is present,
and a rebuild never reproduces the bytes it replaces — `generation`, `attested_at`
and `reason` all move — so correcting one tree without it leaves the other tree
red as `unratified` for no edit of its own.

`--reattest` prints the new digest and never writes the pin. Nothing else in the
repository calls `attest.build`, and in particular `neutralise_decision.py` does
not: a tool that edited the evidence and refreshed its own attestation would
reproduce, one layer down, exactly the vacuity this check exists to close.

There is one state in which a rebuild alone leaves this check green, and it is not
a hole in the split: a rebuild that reproduces a ratified record **byte for byte**
pins nothing new, because the bytes a human signed off are the bytes on disk
again. It is reachable when the witness was corrupt or absent over an unmoved
tree — `attest.build` restarts `generation` at 1 there — and `--reattest` names
the state of the record it replaced rather than reporting the match alone, which
until 2026-08-11 was the only thing it said. `attest.NO_BASELINE` and
`tests/unit/test_attest_build.py` hold that.

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
        "correction, run `python3 tools/check_corpus.py --reattest \"why\" --unit "
        "NAME` and then move that unit's `attestation_sha256` in "
        "tools/corpuscheck/config.json by hand; the rebuild alone does not clear "
        "this, and omitting --unit rebuilds every other unit too"
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
    "undeclared": (
        "a unit that names no `root.marker` cannot be placed in a root, so it cannot "
        "be judged in one. Give it a marker path that is present wherever the unit "
        "belongs and is neither its `tree` nor its `attestation` — without one the "
        "unit is carried in the list and read by nothing, which is the silence this "
        "check exists to refuse"
    ),
}

_EXPECTED = {
    "edited": "the attested SHA-256 of this preserved record",
    "added": "no file here that the attestation does not cover",
    "removed": "the attested file, present",
    "unratified": "the attestation digest pinned in config.json",
    "malformed": "an attestation that agrees with itself",
    "undeclared": "a `root.marker` naming the root this unit expects",
}

#: Where an `undeclared` unit is reported. The unit list is the subject, so the
#: violation points at the file that carries it rather than at a tree.
_CONFIG_REL = "tools/corpuscheck/config.json"


@check(
    "preserved-evidence",
    "A committed record of a run matches its attested SHA-256, outside the tree.",
)
def run(corpus, ctx: dict) -> list[Violation]:
    spec = (ctx["config"] or {}).get("preserved_evidence")
    if not spec:
        ctx["skip"]("preserved-evidence", "no `preserved_evidence` block in config.json")
        return []

    out: list[Violation] = []

    # Scope is keyed on a declared marker, never on the tree and no longer on the
    # attestation. Both of those key the check on something whose absence is the
    # very thing being guarded against, and each was defeated in turn: keyed on
    # the tree, deleting all 59 records took the check to `skipped`; keyed on the
    # attestation, a unit with a missing or mis-typed `attestation` was filtered
    # out and reported nothing at all, which is indistinguishable from a fixture
    # unit that legitimately lives under another root. The marker separates those
    # two states, which is the whole of this fix: marker present and witness
    # absent is a `malformed` violation, and marker absent is another root's unit.
    units: list[dict] = []
    elsewhere: list[dict] = []
    for unit in spec["units"]:
        marker = (unit.get("root") or {}).get("marker")
        if not marker:
            out.append(
                Violation(
                    check="preserved-evidence",
                    severity=ERROR,
                    path=_CONFIG_REL,
                    line=1,
                    found=f"unit {unit['name']} declares no `root.marker`  (undeclared)",
                    expected=_EXPECTED["undeclared"],
                    hint=_HINTS["undeclared"],
                )
            )
        elif (corpus.root / marker).exists():
            units.append(unit)
        else:
            elsewhere.append(unit)

    if not units:
        # Announced once for the whole check rather than per out-of-scope unit:
        # the unit list spans this repository and the two fixture corpora, so in
        # every real root most of it is legitimately elsewhere and a skip line
        # per unit would be noise that trains a reader to ignore skip lines. The
        # word is `out of scope` and not `disabled`, which the older message
        # used: every unit here declared a root and none of those roots is this
        # one, so nothing is broken.
        #
        # Guarded on `elsewhere` because a list whose every unit is `undeclared`
        # leaves nothing to have looked for, and announcing a skip that names no
        # unit would report an absence nobody declared. That case is the error
        # above, and `out` is returned rather than `[]` so this silence cannot
        # swallow it.
        if elsewhere:
            ctx["skip"](
                "preserved-evidence",
                "every unit is out of scope in this tree, as declared and not as a "
                "fault — looked for "
                + ", ".join(f"{u['name']} at {u['root']['marker']}" for u in elsewhere),
            )
        return out

    for unit in units:
        for kind, path, found, expected in verify(corpus.root, unit):
            # `malformed` and a whole-tree loss both carry an expectation only the
            # attestation knows — the digest its entries add up to, or how many
            # records the absent directory held. The per-kind sentence is right for
            # the rest and better than showing a reader a bare digest. Naming the
            # unit's own tree is what distinguishes the tree-level event: without
            # this, a deleted directory read "expected: the attested file, present"
            # while pointing at a directory.
            speaks_for_itself = kind == "malformed" or path == unit["tree"]
            out.append(
                Violation(
                    check="preserved-evidence",
                    severity=ERROR,
                    path=path,
                    line=1,
                    found=f"{found}  ({kind})",
                    expected=expected if speaks_for_itself else _EXPECTED[kind],
                    hint=_HINTS[kind],
                )
            )
    return out
