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
    """
    _evidence(tmp_path, "evidence/records")
    unit = _unit("u", tree="evidence/records", witness="witness.json")
    attest.build(tmp_path, unit, reason="r", attested_at=STAMP)
    (tmp_path / "witness.json").write_text("this is not json\n", encoding="utf-8")

    text, _digest = attest.build(tmp_path, unit, reason="r", attested_at=STAMP)
    assert json.loads(text)["generation"] == 1


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
