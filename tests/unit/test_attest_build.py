"""The write half of the ratification protocol: `attest.build` and `cli.reattest`.

`preserved-evidence` reads an attestation; `--reattest` writes one. The read half
is held by `tools/fixtures/known-bad`, which carries a unit per failure kind, and
by `tests/unit/test_preserved_evidence_scope.py`, which holds the one kind no
fixture root can. The write half had two callers before this file — `cli.reattest`
and, incidentally, two `attest.build` calls in the scope tests that build a
witness in order to have something to verify — and no arm anywhere asserting what
`build` does.

**What a test may assert here, and where the line is.** The correction protocol is
two acts that cannot collapse into one: a rebuild moves a unit to `unratified`,
and a human moves `attestation_sha256` in `tools/corpuscheck/config.json`. A test
that performed act two would reproduce the trap the design exists to close, since
an attestation a tool can refresh attests nothing. So every arm below builds under
`tmp_path`, over a synthetic unit dict, and **nothing here reads or writes this
repository's `config.json` or any committed attestation**. Setting
`attestation_sha256` on a throwaway dict is constructing a precondition, not
ratifying evidence: the digest it pins covers bytes this test wrote seconds
earlier under a temporary root, and no gate anywhere consults it.

The strongest arm is `test_a_rebuild_does_not_clear_the_gate_on_its_own`. It is the
two-act rule stated mechanically rather than in prose, and it fails if `build` ever
grows the one line that would make the whole check vacuous.

**What 2026-08-11 added, and what it left alone.** The section *The reassurance*
holds `cli.reattest`'s reporting after the repair to its one reassurance arm, which
was reachable only from a record that could not be read. None of the four
properties this file landed with moved: `build` still reports a digest it does not
record, a rebuild still leaves the unit `unratified`, a rebuild under a live plant
still reclassifies rather than clears, and `generation` still counts rebuilds with
an unreadable predecessor restarting the count at 1. The repair changed what is
*reported* about a rebuild and nothing about what a rebuild *does*, so the fourth
arm is unedited and carries a note saying so.
`test_reporting_an_unmoved_tree_does_not_ratify_it` is the two-act rule asserted
again at the new report, in the one state where a tool might be tempted to treat a
provably unmoved tree as needing no pin.

**Why unit tests and not fixture rows.** A fixture cannot reach this code at all.
`check_corpus.py` calls `verify` and never `build`, so no state of a fixture corpus
exercises the writer. Worse, `DEFAULT_CONFIG` resolves beside the module, so both
fixture roots and this repository share one `preserved_evidence` unit list: a unit
added to exercise a rebuild would be in scope for the real gate too, and a rebuild
in a fixture root would leave the real tree's pin describing bytes that had moved.
That is the same constraint under which the `undeclared` kind is held from Python
rather than from `known-bad`.
"""

from __future__ import annotations

import io
import json
import sys
from contextlib import redirect_stderr, redirect_stdout
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "tools"))

from corpuscheck import attest  # noqa: E402
from corpuscheck.cli import reattest  # noqa: E402

STAMP = "2026-08-11"


def _unit(name: str, *, tree: str, witness: str) -> dict:
    return {
        "name": name,
        "tree": tree,
        "attestation": witness,
        "root": {"marker": tree.split("/", 1)[0], "why": "this test's own root"},
        "attestation_sha256": "0" * 64,
    }


def _evidence(root: Path, tree: str, body: str = '{"run_id": "r"}\n') -> Path:
    d = root / tree
    d.mkdir(parents=True, exist_ok=True)
    (d / "manifest.json").write_text(body, encoding="utf-8")
    return d


def _kinds(complaints: list[tuple[str, str, str, str]]) -> list[str]:
    return sorted(kind for kind, _, _, _ in complaints)


# ---------------------------------------------------------------------------
# The two-act rule, which is the whole reason this module is not allowed to be
# convenient.
# ---------------------------------------------------------------------------


def test_a_rebuild_does_not_clear_the_gate_on_its_own(tmp_path) -> None:
    """The record is written and the unit is `unratified`, not clean.

    This is the property that keeps `preserved-evidence` from being vacuous. A
    rebuild is a legitimate act after a legitimate correction and it is not
    sufficient: the pin is a second file edited by a human, or the gate stays red.
    """
    _evidence(tmp_path, "evidence/records")
    unit = _unit("u", tree="evidence/records", witness="witness.json")

    text, digest = attest.build(tmp_path, unit, reason="a correction", attested_at=STAMP)

    assert (tmp_path / "witness.json").is_file()
    assert _kinds(attest.verify(tmp_path, unit)) == ["unratified"]
    # The digest returned is over the bytes written, and it is returned rather
    # than recorded anywhere: recording it beside the record it covers is the
    # self-certification this module refuses.
    assert digest == attest.sha256_bytes(text.encode("utf-8"))
    assert digest not in (tmp_path / "witness.json").read_text(encoding="utf-8")


def test_building_never_moves_the_pin_it_reports(tmp_path) -> None:
    """A tool cannot ratify itself, asserted against the unit it was handed."""
    _evidence(tmp_path, "evidence/records")
    unit = _unit("u", tree="evidence/records", witness="witness.json")
    before = dict(unit)

    attest.build(tmp_path, unit, reason="a correction", attested_at=STAMP)

    assert unit == before, "build mutated the unit it was passed"


def test_a_rebuild_reclassifies_a_live_edit_rather_than_clearing_it(tmp_path) -> None:
    """`edited` becomes `unratified`, which is a different sentence to a human.

    An edit to preserved evidence and a rebuild of the witness over it are two
    events, and the check names them separately so the remedy is not guessed at.
    Before the rebuild the complaint is that somebody rewrote a dated record;
    after it the complaint is that nobody has ratified the rewrite.
    """
    _evidence(tmp_path, "evidence/records")
    unit = _unit("u", tree="evidence/records", witness="witness.json")
    _text, digest = attest.build(tmp_path, unit, reason="the first", attested_at=STAMP)
    unit["attestation_sha256"] = digest
    assert attest.verify(tmp_path, unit) == [], "the precondition was not attested"

    (tmp_path / "evidence" / "records" / "manifest.json").write_text(
        '{"run_id": "rewritten"}\n', encoding="utf-8"
    )
    assert _kinds(attest.verify(tmp_path, unit)) == ["edited"]

    attest.build(tmp_path, unit, reason="the correction", attested_at=STAMP)
    assert _kinds(attest.verify(tmp_path, unit)) == ["unratified"]


# ---------------------------------------------------------------------------
# The generation counter, which is how a reader tells one rebuild from three.
# ---------------------------------------------------------------------------


def test_the_generation_counts_the_rebuilds(tmp_path) -> None:
    _evidence(tmp_path, "evidence/records")
    unit = _unit("u", tree="evidence/records", witness="witness.json")

    seen = []
    for _ in range(3):
        text, _digest = attest.build(tmp_path, unit, reason="r", attested_at=STAMP)
        seen.append(json.loads(text)["generation"])

    assert seen == [1, 2, 3]


def test_an_unreadable_predecessor_restarts_the_count_rather_than_failing(tmp_path) -> None:
    """A witness that does not decode is replaced, and the count says 1.

    The alternative is a writer that cannot run against a corrupted record, which
    would leave the only route out of a corrupted witness a hand edit.

    **This behaviour did not change on 2026-08-11 and this arm is unedited.** What
    changed is that the restart is now reported: it is the whole route by which a
    rebuild can reproduce the pinned bytes, since `generation` is inside the
    digested document, and `cli.reattest` used to say nothing about it. The arms
    under *The reassurance* below are about the reporting and not about the count.
    """
    _evidence(tmp_path, "evidence/records")
    unit = _unit("u", tree="evidence/records", witness="witness.json")
    attest.build(tmp_path, unit, reason="r", attested_at=STAMP)
    (tmp_path / "witness.json").write_text("this is not json\n", encoding="utf-8")

    text, _digest = attest.build(tmp_path, unit, reason="r", attested_at=STAMP)
    assert json.loads(text)["generation"] == 1


def test_a_witness_that_is_not_an_object_restarts_the_count_rather_than_raising(
    tmp_path,
) -> None:
    """Valid JSON that is not a mapping, which used to raise out of `build`.

    `build` read the stored generation with `load(att_path).get(...)` under an
    `except (json.JSONDecodeError, TypeError, ValueError)`, and a witness holding
    `[1, 2, 3]`, `null`, `17` or a quoted string decodes fine and then reaches
    `.get` on a non-mapping. All four were measured raising `AttributeError` out
    of `--reattest` on 2026-08-11 — the state the arm above exists to prevent,
    reached by a corruption that happens to be well-formed JSON. Undecodable
    bytes were never in this class: `UnicodeDecodeError` is a `ValueError`.
    """
    _evidence(tmp_path, "evidence/records")
    unit = _unit("u", tree="evidence/records", witness="witness.json")
    attest.build(tmp_path, unit, reason="r", attested_at=STAMP)

    for body in ("[1, 2, 3]\n", "null\n", "17\n", '"a string"\n'):
        (tmp_path / "witness.json").write_text(body, encoding="utf-8")
        text, _digest = attest.build(tmp_path, unit, reason="r", attested_at=STAMP)
        assert json.loads(text)["generation"] == 1, body


def test_an_absent_tree_is_refused_and_writes_nothing(tmp_path) -> None:
    """The witness is not created over a tree that is not there.

    An attestation over an empty file set is a well-formed record asserting that
    nothing exists, and it would verify clean once pinned. Refusing is what keeps
    a deleted tree a `removed` rather than a rebuild away from green.
    """
    unit = _unit("u", tree="evidence/records", witness="witness.json")

    try:
        attest.build(tmp_path, unit, reason="r", attested_at=STAMP)
    except FileNotFoundError as exc:
        assert "the attested tree is absent" in str(exc)
    else:
        raise AssertionError("a rebuild over an absent tree was allowed")

    assert not (tmp_path / "witness.json").exists()


# ---------------------------------------------------------------------------
# `--reattest`'s scope, which is wider than it looks.
# ---------------------------------------------------------------------------


def _reattest(root: Path, units: list[dict], reason: str, unit_name: str | None):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = reattest(root, {"preserved_evidence": {"units": units}}, reason, unit_name)
    return code, out.getvalue(), err.getvalue()


def test_a_bare_reattest_rebuilds_every_present_unit(tmp_path) -> None:
    """Which is why `--unit` is required for a scoped correction.

    A rebuild never reproduces the bytes it replaces — `generation`,
    `attested_at` and `reason` all move — so a bare form run to correct one tree
    leaves every other present unit red as `unratified` for no edit of its own.
    Each `preserved_evidence` unit declares its own `root.marker`, so the bare
    form is a wider act than the command reads as.
    """
    _evidence(tmp_path, "alpha/records")
    _evidence(tmp_path, "beta/records")
    alpha = _unit("alpha", tree="alpha/records", witness="alpha/witness.json")
    beta = _unit("beta", tree="beta/records", witness="beta/witness.json")

    code, out, _err = _reattest(tmp_path, [alpha, beta], "a correction to alpha only", None)

    assert code == 0
    assert (tmp_path / "alpha" / "witness.json").is_file()
    assert (tmp_path / "beta" / "witness.json").is_file(), (
        "the bare form left beta alone, so `--unit` is no longer load-bearing "
        "and the sentence naming it needs correcting"
    )
    assert "alpha:" in out and "beta:" in out
    assert _kinds(attest.verify(tmp_path, beta)) == ["unratified"]


def test_unit_scopes_the_rebuild_to_one_tree(tmp_path) -> None:
    _evidence(tmp_path, "alpha/records")
    _evidence(tmp_path, "beta/records")
    alpha = _unit("alpha", tree="alpha/records", witness="alpha/witness.json")
    beta = _unit("beta", tree="beta/records", witness="beta/witness.json")

    code, out, _err = _reattest(tmp_path, [alpha, beta], "a correction to alpha", "alpha")

    assert code == 0
    assert (tmp_path / "alpha" / "witness.json").is_file()
    assert not (tmp_path / "beta" / "witness.json").exists()
    assert "beta" not in out


def test_reattest_reports_the_pin_to_move_and_does_not_move_it(tmp_path) -> None:
    """The step it does not take is the one carrying the human decision."""
    _evidence(tmp_path, "evidence/records")
    unit = _unit("u", tree="evidence/records", witness="witness.json")

    code, out, _err = _reattest(tmp_path, [unit], "a correction", None)
    written = (tmp_path / "witness.json").read_bytes()

    assert code == 0
    assert unit["attestation_sha256"] == "0" * 64, "reattest moved the pin"
    assert attest.sha256_bytes(written) in out
    assert "NOT ratified" in out


def test_a_unit_that_is_not_present_is_refused_rather_than_invented(tmp_path) -> None:
    """Both empty-scope exits, because each would otherwise report success."""
    _evidence(tmp_path, "alpha/records")
    alpha = _unit("alpha", tree="alpha/records", witness="alpha/witness.json")

    code, _out, err = _reattest(tmp_path, [alpha], "r", "no-such-unit")
    assert code == 2
    assert "named 'no-such-unit'" in err
    assert not (tmp_path / "alpha" / "witness.json").exists()

    # The same exit for a different reason, and the reason is in the wording: a
    # unit that was asked for by name and a root that carries none of them are
    # different mistakes, and one message for both sends a reader to the wrong
    # file.
    absent = _unit("gamma", tree="gamma/records", witness="gamma/witness.json")
    code, _out, err = _reattest(tmp_path, [absent], "r", None)
    assert code == 2
    assert "is present under this root" in err

    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        assert reattest(tmp_path, {}, "r", None) == 2
    assert "no `preserved_evidence` block" in err.getvalue()


# ---------------------------------------------------------------------------
# The reassurance, which used to be reachable only from a corrupted record.
#
# `cli.reattest` carried one arm reading `the pinned digest already matches;
# nothing to ratify`, guarded on the rebuilt bytes equalling the pin. That guard
# is a statement about the pin and was read as a statement about the tree, and the
# two coincide only when nothing else in the document moves. Three things always
# do — `generation`, `attested_at`, `reason` — and `generation` is inside the
# digested document, so a plain rebuild never reaches the arm. What does reach it
# is `generation` restarting at 1, which happens when the record being replaced is
# absent, undecodable, or decodes without a usable `generation`; and, legitimately,
# a readable predecessor sitting one generation below the pin.
#
# Measured on 2026-08-11 over the committed `verifier-vs-judge-results` unit: a
# plain rebuild carrying the pinned record's own reason and date produced
# generation 2 and a digest unequal to the pin; the same rebuild with the record
# first made unreadable produced generation 1 and the pinned digest exactly.
#
# So the reporting is split in two. `tree_sha256` is the one field a rebuild does
# not move, and it is compared against the record the pin covers — reachable on an
# ordinary rebuild, and true. The pin-matching arm is kept, because reproducing a
# ratified record is a real state worth naming, and it is suppressed wherever the
# predecessor was in `attest.NO_BASELINE`.
# ---------------------------------------------------------------------------

_UNMOVED = "the attested tree has not moved"
_REASSURED = "nothing to ratify"
_REPLACED = "the record this replaced was"

#: `cli.reattest` stamps the record with `date.today()` and takes no override, so a
#: precondition that has to line up with what the command will write cannot use the
#: frozen `STAMP`. Building it against today is what keeps the arms below from
#: going quietly vacuous on any day but the one they were written.
TODAY = date.today().isoformat()


def _ratified(root: Path, *, reason: str, stamp: str = STAMP,
              tree: str = "evidence/records", witness: str = "witness.json"):
    """A unit whose witness is present, self-consistent and pinned to its bytes."""
    _evidence(root, tree)
    unit = _unit("u", tree=tree, witness=witness)
    text, digest = attest.build(root, unit, reason=reason, attested_at=stamp)
    unit["attestation_sha256"] = digest
    assert attest.verify(root, unit) == [], "the precondition was not attested"
    return unit, text


def test_no_corrupt_predecessor_produces_a_reassurance(tmp_path) -> None:
    """THE BINDING PROPERTY. Delete this and the defect comes straight back.

    There must be no state in which the tool reports nothing to ratify while the
    record it just replaced was corrupt. Every state in `attest.NO_BASELINE` is
    exercised, and the three that restart the count are built so the rebuilt bytes
    **do** equal the pin — which is the state the old arm fired in, and the only
    state in which suppressing the reassurance is doing any work at all.

    **That precondition is asserted rather than assumed, because the first draft of
    this test did not reach it and passed anyway.** It built the pinned record with
    one reason and re-ran the command with another, so the rebuilt bytes never
    equalled the pin, the arm was unreachable for a reason having nothing to do
    with the repair, and removing the guard under test changed no outcome. A plant
    caught it. The reason and the stamp now match by construction and
    `reached_the_arm` fails if they ever stop matching.

    `inconsistent` cannot be arranged to match the pin, because its `generation`
    reads fine and therefore moves; that is asserted too rather than left implied.
    Its load-bearing assertion is the other one: the record is pinned and its
    entries do match the tree, so an implementation that read `tree_sha256` off the
    summary rather than recomputing it from the entries beside it would report the
    tree unmoved on the authority of a record the gate calls `malformed`.
    """
    reason = "the reason both acts carry"
    seen = set()
    for index, (label, corrupt) in enumerate((
        ("absent", lambda p: p.unlink()),
        ("unreadable", lambda p: p.write_text("this is not json\n", encoding="utf-8")),
        ("uncounted", lambda p: _rewrite(p, drop="generation")),
        ("inconsistent", lambda p: _rewrite(p, file_count=99)),
        ("inconsistent", lambda p: _rewrite(p, tree_sha256="f" * 64)),
    )):
        root = tmp_path / f"{index}-{label}"
        root.mkdir(parents=True)
        # Same reason, same stamp `cli.reattest` will use, so the rebuild reproduces
        # the pinned document byte for byte once the count restarts at 1.
        unit, _text = _ratified(root, reason=reason, stamp=TODAY)
        witness = root / "witness.json"
        corrupt(witness)
        if label == "inconsistent":
            # Keep the doctored record pinned, so the only thing standing between
            # this and a report of an unmoved tree is the reconciliation.
            unit["attestation_sha256"] = attest.sha256_bytes(witness.read_bytes())

        state, baseline = attest.predecessor(root, unit)
        assert state == label, f"{label}: classified as {state}"
        assert baseline is None, f"{label}: a baseline was read out of a {state} record"

        _code, out, _err = _reattest(root, [unit], reason, None)

        rebuilt = attest.sha256_bytes(witness.read_bytes())
        reached_the_arm = rebuilt == unit["attestation_sha256"]
        if state in attest.RESTARTS_THE_COUNT:
            assert reached_the_arm, (
                f"{label}: the rebuild did not reproduce the pin, so the arm this "
                f"test exists to keep silent was unreachable and every assertion "
                f"below would pass over a tool that had never been repaired"
            )
        else:
            assert not reached_the_arm, (
                f"{label}: the count did not restart, so the pin cannot be "
                f"reproduced — if it was, `RESTARTS_THE_COUNT` is wrong"
            )

        assert _REASSURED not in out, (
            f"{label}: reassurance over a {state} record\n{out}"
        )
        assert _UNMOVED not in out, (
            f"{label}: the tree was called unmoved on a {state} record\n{out}"
        )
        assert _REPLACED in out and state in out, (
            f"{label}: the state was not reported\n{out}"
        )
        seen.add(state)

    assert seen == set(attest.NO_BASELINE), (
        f"a state in attest.NO_BASELINE went unexercised: "
        f"{set(attest.NO_BASELINE) - seen}"
    )


def _rewrite(path: Path, *, drop: str | None = None, **fields) -> None:
    doc = json.loads(path.read_text(encoding="utf-8"))
    if drop is not None:
        doc.pop(drop)
    doc.update(fields)
    path.write_text(json.dumps(doc, indent=1, sort_keys=False) + "\n", encoding="utf-8")


def test_an_unmoved_tree_is_reported_as_unmoved(tmp_path) -> None:
    """The other direction, and the capability the old arm could not deliver.

    A test that only checked the corrupt case would pass over a tool that had
    simply deleted the arm and now says nothing in any state.
    """
    unit, _text = _ratified(tmp_path, reason="the first attestation")

    _code, out, _err = _reattest(
        tmp_path, [unit], "a correction to something else", None
    )

    assert _UNMOVED in out, out
    assert _REPLACED not in out, "a ratified predecessor was reported as unusable"


def test_a_moved_tree_is_not_reported_as_unmoved(tmp_path) -> None:
    """The negative control, without which the arm above passes on a constant."""
    unit, _text = _ratified(tmp_path, reason="the first attestation")
    (tmp_path / "evidence" / "records" / "manifest.json").write_text(
        '{"run_id": "rewritten"}\n', encoding="utf-8"
    )

    _code, out, _err = _reattest(tmp_path, [unit], "the correction", None)

    assert _UNMOVED not in out, out
    assert _REASSURED not in out


def test_reporting_an_unmoved_tree_does_not_ratify_it(tmp_path) -> None:
    """Act one still cannot satisfy act two, asserted at the new report.

    The whole value of the split is that a rebuild leaves the gate red until a
    human moves the pin. This is the arm that fails if the tree-unmoved report ever
    grows into a reason to skip the pin, and it is the same property as
    `test_a_rebuild_does_not_clear_the_gate_on_its_own` asserted in the one state
    where a tool might be tempted to take a shortcut: the tree is provably unmoved.
    """
    unit, _text = _ratified(tmp_path, reason="the first attestation")
    pinned_before = unit["attestation_sha256"]

    _code, out, _err = _reattest(tmp_path, [unit], "a correction", None)

    assert _UNMOVED in out, "the precondition was not the unmoved-tree report"
    assert unit["attestation_sha256"] == pinned_before, "reattest moved the pin"
    assert _kinds(attest.verify(tmp_path, unit)) == ["unratified"], (
        "an unmoved tree cleared the gate without a human, which is act one "
        "satisfying act two"
    )
    assert "NOT ratified" in out


def test_reproducing_a_ratified_record_is_still_reported(tmp_path) -> None:
    """The capability that removing the arm outright would have cost.

    A predecessor one generation below the pin is an unratified intermediate: a
    rebuild over it lands back on the ratified bytes, and there is then genuinely
    nothing to ratify. Nothing is corrupt in this state, so the reassurance is
    kept — which is why the repair gates the arm on the predecessor rather than
    deleting it.
    """
    _evidence(tmp_path, "evidence/records")
    unit = _unit("u", tree="evidence/records", witness="witness.json")
    built = [
        attest.build(tmp_path, unit, reason="r", attested_at=STAMP) for _ in range(3)
    ]
    unit["attestation_sha256"] = built[2][1]
    (tmp_path / "witness.json").write_text(built[1][0], encoding="utf-8")

    state, baseline = attest.predecessor(tmp_path, unit)
    assert (state, baseline) == ("unratified", None)

    _code, out, _err = _reattest(tmp_path, [unit], "r", None)

    assert _REASSURED in out, out
    assert _REPLACED not in out
    assert attest.verify(tmp_path, unit) == [], (
        "reproducing the pinned bytes should leave the unit attested"
    )
    # And the trailer stops claiming the gate is red for a unit that is green.
    assert "Except for: u" in out


def test_a_baseline_is_never_taken_from_a_record_that_is_not_the_pinned_one(
    tmp_path,
) -> None:
    """`unratified` supplies no baseline, even with the tree provably unmoved.

    A baseline from a record nobody ratified would report agreement with whatever
    the last rebuild happened to measure, which is a different claim wearing the
    same words.
    """
    unit, _text = _ratified(tmp_path, reason="the first attestation")
    # A rebuild nobody ratified, over a tree that has not moved.
    attest.build(tmp_path, unit, reason="an unratified rebuild", attested_at=STAMP)

    state, baseline = attest.predecessor(tmp_path, unit)
    assert (state, baseline) == ("unratified", None)

    _code, out, _err = _reattest(tmp_path, [unit], "the next rebuild", None)
    assert _UNMOVED not in out, out


def test_predecessor_reads_the_record_before_the_rebuild_replaces_it(tmp_path) -> None:
    """The ordering, which is the whole reason the state was unreportable.

    After `build` returns there is nothing left to ask, because the record that
    was corrupt has been overwritten. Asserted by classifying the same witness on
    both sides of a rebuild.
    """
    unit, _text = _ratified(tmp_path, reason="the first attestation")
    (tmp_path / "witness.json").write_text("this is not json\n", encoding="utf-8")

    assert attest.predecessor(tmp_path, unit)[0] == "unreadable"
    attest.build(tmp_path, unit, reason="r", attested_at=STAMP)
    assert attest.predecessor(tmp_path, unit)[0] == "unratified", (
        "the corruption is unreadable from after the rebuild, which is why "
        "cli.reattest classifies before it"
    )
