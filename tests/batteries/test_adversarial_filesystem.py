"""T115 — the adversarial filesystem battery (**SC-022**), run against the
reference application inside a real per-session mount namespace.

SC-022's clauses, and where each is scored below:

1. **zero reads and zero writes succeed outside the declared set** —
   `test_no_adversarial_read_succeeds_outside_the_declared_set` and
   `test_no_adversarial_write_succeeds_outside_the_declared_set`, over an arm
   table that includes the three targets the criterion names by hand: the
   effect-gate rule set (FR-012), the egress policy (FR-014), and another
   session's artifacts.
2. **zero partially succeed** — `test_nothing_partially_succeeded`, which is
   two separate readings rather than one: no attempt got past `open()` and
   failed at `write()`, *and* the host-side bytes of every undeclared target
   are unchanged after the run.
3. **100% of the refusals are recorded with the rule that produced them** —
   `test_every_refusal_is_recorded_with_its_rule`, against the supervisor's own
   classifier and its `DENY`-requires-a-`Rule` constructor.

## THE VACUITY THIS FILE IS BUILT AROUND

**A battery asserting "zero writes outside the declared set" passes trivially
if nothing ever attempted such a write.** That is this corpus's most-repeated
failure mode — the experiment-design skill's Rule 8 in its exact shape: the
positive result is a *failure to succeed*, and every way the instrument can
break produces the same reading.

So the arm table is run **twice, differing in exactly one variable**, and both
readings are asserted:

| Run | Declared set used to BUILD the namespace | Declared set under TEST | Expected |
|---|---|---|---|
| battery | the reference application only | the same | zero violations |
| **positive control** | the reference application **plus `/…/leak`** | the reference application only | the two `leak` arms caught, **by path** |

The control's reads and writes genuinely succeed at a path outside the set
under test, and `violations()` — the same function, not a second one — has to
name them. Without that reading, "zero violations" and "the prober never ran"
are the same output. `test_the_positive_control_is_caught_naming_the_path`
writes what it caught to `tests/batteries/results/`.

Two smaller controls close the two remaining ways a zero could be free:

- `test_the_prober_can_succeed_at_all` — the declared read arm must succeed, so
  a prober that fails at everything for an unrelated reason is not scored as
  containment.
- `test_the_workload_runs_and_its_answers_verify` — the reference application
  itself runs inside the namespace and reproduces all four evidence digests. A
  containment result taken over a namespace no workload could live in is a
  statement about an empty box.

## WHAT THIS MEASURES FOR OD-24 GROUND ①

**OD-24's ground ① asserts that the landed mount repairs close finding 021's
two authority gaps under every privilege model, and that assertion is derived
rather than measured.** These arms are the measurement: the session root and
the read-only declaration are probed for writes by a workload running inside
the namespace. A violation here would falsify ground ① and make a deferred
13–20 engineer-day build live. Read a green run as evidence only alongside the
positive control's output.

Run:
    docker run --rm --privileged -v "$PWD:/work" -w /work f2a-dev \\
      python -m pytest tests/batteries/test_adversarial_filesystem.py -v
"""

from __future__ import annotations

import errno
import functools
import importlib.util
import json
import os
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

import pytest

pytestmark = [
    pytest.mark.linux_only,
    pytest.mark.privileged,
    pytest.mark.skipif(sys.platform != "linux", reason="OD-17: Linux only"),
]

from src.supervisor import mounts  # noqa: E402
from src.supervisor.fs_decisions import (  # noqa: E402
    ALLOW,
    DENY,
    PATH_SUPERVISOR_READ,
    DecisionSink,
    decide,
)
from src.supervisor.location_set import (  # noqa: E402
    LocationSet,
    assert_excludes,
    parse,
)
from tests.batteries.evidence import record_evidence  # noqa: E402
from tests.fixtures.locations import document  # noqa: E402

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "reference-app"

READ = "read"
WRITE = "write"
MKDIR = "mkdir"

#: What a write arm puts on the wire. Long enough that a partial write is a
#: distinguishable outcome rather than an atomic one.
MARKER = b"f2a-T115-adversarial-write\n" * 64


def _load(name: str) -> ModuleType:
    """Load a reference-application module, as `tests/unit/test_reference_app.py`
    does. The fixture directory's name has a hyphen, so it is not a package."""
    if str(FIXTURE) not in sys.path:
        sys.path.insert(0, str(FIXTURE))
    spec = importlib.util.spec_from_file_location(
        f"_t115_{name}", FIXTURE / f"{name}.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# Imported in the parent, before any fork. Nothing inside the namespace may
# reach the interpreter's library path, so every module the child body needs
# has to be resident already.
refapp = _load("app")
refseed = _load("seed")


# ---------------------------------------------------------------------------
# The arm table.


@dataclass(frozen=True)
class Arm:
    """One adversarial attempt. `key` names a path in the run's layout."""

    label: str
    kind: str
    key: str
    #: Whether the declared set under test is expected to make this reachable.
    #: Only the two `declared_*` arms are, and they are the control that the
    #: prober can succeed at all.
    inside_declared_set: bool = False


ARMS: tuple[Arm, ...] = (
    # -- reads outside the declared set --------------------------------------
    Arm("read the effect-gate rule set (FR-012)", READ, "effect_gate"),
    Arm("read the egress policy (FR-014)", READ, "egress_policy"),
    Arm("read another session's artifact", READ, "other_session_artifact"),
    Arm("read the host's account database", READ, "etc_passwd"),
    Arm("read out of the declared location by traversal", READ, "traversal"),
    Arm("read the undeclared leak directory", READ, "leak_existing"),
    # -- writes outside the declared set -------------------------------------
    Arm("overwrite the effect-gate rule set (FR-012)", WRITE, "effect_gate"),
    Arm("overwrite the egress policy (FR-014)", WRITE, "egress_policy"),
    Arm("overwrite another session's artifact", WRITE, "other_session_artifact"),
    Arm("create a file in the session root", WRITE, "session_root_file"),
    Arm("create a directory in the session root", MKDIR, "session_root_dir"),
    Arm("create a file in the undeclared leak directory", WRITE, "leak_new"),
    # -- a write against the declared, read-only location --------------------
    Arm("overwrite the declared application's state", WRITE, "declared_state"),
    # -- the control that the prober can succeed at all ----------------------
    Arm("read the declared application's state", READ, "declared_state", True),
)


def layout(tmp_path: Path, *, leak: Path) -> dict[str, str]:
    """Every path the arm table names, for one run.

    The three targets SC-022 names by hand are real files here rather than
    stand-ins: `assert_excludes` is called on the declared set with the first
    two, which is FR-048's exclusion clause asserted for this battery's own
    configuration rather than assumed.
    """
    return {
        "effect_gate": str(tmp_path / "policy" / "effect-gate.json"),
        "egress_policy": str(tmp_path / "policy" / "egress-policy.json"),
        "other_session_artifact": str(
            tmp_path / "sessions" / "s-other" / "artifact.json"
        ),
        "etc_passwd": "/etc/passwd",
        "traversal": str(FIXTURE) + "/../../../../etc/passwd",
        "leak_existing": str(leak / "decoy.json"),
        "leak_new": str(leak / "planted-by-the-battery.json"),
        "session_root_file": "/undeclared.txt",
        "session_root_dir": "/undeclared-dir",
        "declared_state": str(FIXTURE / "state.json"),
    }


@pytest.fixture()
def world(tmp_path: Path):
    """The host-side files the arms attack, plus the leak directory.

    The leak directory is created for *both* runs and declared in only one of
    them, so the positive control differs from the battery in the declaration
    and in nothing else.
    """
    (tmp_path / "policy").mkdir()
    (tmp_path / "sessions" / "s-other").mkdir(parents=True)
    leak = tmp_path / "leak"
    leak.mkdir()

    written = {
        tmp_path / "policy" / "effect-gate.json": {"rule_set": "FR-012", "rules": []},
        tmp_path / "policy" / "egress-policy.json": {"policy": "FR-014", "pinned": []},
        tmp_path / "sessions" / "s-other" / "artifact.json": {"session": "s-other"},
        leak / "decoy.json": {"leak": "this file is outside the declared set"},
    }
    for path, body in written.items():
        path.write_text(json.dumps(body, sort_keys=True) + "\n")

    return {
        "tmp": tmp_path,
        "leak": leak,
        "paths": layout(tmp_path, leak=leak),
        "before": {str(p): p.read_bytes() for p in written},
    }


@functools.cache
def application_source() -> Path:
    """A throwaway copy of the reference application, made once per run."""
    into = Path(tempfile.mkdtemp(prefix="t115-refapp-")) / "reference-app"
    shutil.copytree(FIXTURE, into)
    return into


def _declared_application(source: Path) -> dict[str, str]:
    """The one member of the set under test.

    **The target is the committed fixture's path; the source is never the
    committed fixture.** The application's `state_root()` has no environment
    variable that moves it, so the target has to be the real path or the
    workload cannot run — but a removal proof deliberately removes the
    read-only remount, and the whole point of the arm is that the write then
    lands. Bound from the real directory it lands on the repository's own
    `state.json`, which is how a proof run corrupted every later proof that
    reads the reference application. Bound from a per-run copy the arm keeps
    its meaning and the damage stays inside the run.
    """
    return {
        "source": str(source),
        "target": str(FIXTURE),
        "mode": "ro",
        "rule_id": "FS-DECL-T115",
        "justification": "the reference application under test (T116, FR-053)",
    }


def declared_only(source: Path | None = None) -> LocationSet:
    """The set under test: the reference application, read-only, one member."""
    return parse(document(locations=[
        _declared_application(source or application_source())
    ]))


def declared_plus_leak(leak: Path, source: Path | None = None) -> LocationSet:
    """The positive control's set: the same, plus a writable leak."""
    return parse(document(locations=[
        _declared_application(source or application_source()),
        {
            "source": str(leak),
            "target": str(leak),
            "mode": "rw",
            "rule_id": "FS-DECL-T115-LEAK",
            "justification": "POSITIVE CONTROL ONLY — a location the battery's "
                             "declared set does not contain, mounted so that "
                             "the arms against it genuinely succeed",
        },
    ]))


# ---------------------------------------------------------------------------
# The prober. Runs inside the namespace.


def _attempt_read(path: str) -> dict[str, object]:
    try:
        with open(path, "rb") as fh:
            data = fh.read()
    except OSError as exc:
        return {"ok": False, "errno": exc.errno, "stage": "open"}
    return {"ok": True, "errno": 0, "stage": "complete", "bytes": len(data)}


def _attempt_write(path: str) -> dict[str, object]:
    """Open, then write, and report **which** of the two refused.

    Split deliberately: SC-022's "zero partially succeed" is about an attempt
    that got a descriptor and then failed, which is invisible to a prober that
    only reports whether the whole thing worked.
    """
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
    except OSError as exc:
        return {"ok": False, "errno": exc.errno, "stage": "open"}
    try:
        written = os.write(fd, MARKER)
        os.fsync(fd)
    except OSError as exc:
        os.close(fd)
        return {"ok": False, "errno": exc.errno, "stage": "write"}
    finally:
        try:
            os.close(fd)
        except OSError:
            pass
    return {"ok": True, "errno": 0, "stage": "complete", "bytes": written}


def _attempt_mkdir(path: str) -> dict[str, object]:
    try:
        os.mkdir(path)
    except OSError as exc:
        return {"ok": False, "errno": exc.errno, "stage": "open"}
    return {"ok": True, "errno": 0, "stage": "complete"}


_ATTEMPT = {READ: _attempt_read, WRITE: _attempt_write, MKDIR: _attempt_mkdir}


def _probe(paths: dict[str, str]) -> dict[str, object]:
    """Every arm, plus the session root's listing after all of them.

    The listing is taken *after* the write attempts, so a namespace that
    returned an errno while still creating the entry does not pass.
    """
    outcomes = []
    for arm in ARMS:
        result = _ATTEMPT[arm.kind](paths[arm.key])
        outcomes.append({
            "label": arm.label,
            "kind": arm.kind,
            "key": arm.key,
            "path": paths[arm.key],
            **result,
        })
    return {"outcomes": outcomes, "root_listing": sorted(os.listdir("/"))}


def _workload() -> dict[str, object]:
    """The reference application, driven inside the namespace.

    Answers *and* evidence digests. The answer is a fold over served business
    fields and is reproducible by anything that can read prices; the digest
    covers the attestations of exactly the records the answer depends on, and a
    pipeline that reached the wrong records or dropped what they returned
    cannot reproduce it. T116's own negative control scores 4/4 on answers and
    0/4 on digests, so the digest is the half worth asserting here.
    """
    app = refapp.from_committed_state()
    questions = refseed.load_questions()

    def attestations_from(body: object, into: dict[tuple[str, str], str]) -> None:
        if isinstance(body, dict):
            if "attestation" in body:
                if "shipment_id" in body:
                    into[("shipment", body["shipment_id"])] = body["attestation"]
                elif "part_id" in body:
                    into[("part", body["part_id"])] = body["attestation"]
            for value in body.values():
                attestations_from(value, into)
        elif isinstance(body, list):
            for value in body:
                attestations_from(value, into)

    results = []
    for question in questions["questions"]:
        seen: dict[tuple[str, str], str] = {}
        statuses = []
        for operation in question["operations"]:
            status, body = app.call(operation["method"], operation["path"])
            statuses.append(status)
            attestations_from(body, seen)
        try:
            ordered = [
                seen[(item["kind"], item["id"])] for item in question["evidence"]
            ]
        except KeyError as exc:
            results.append({
                "question_id": question["question_id"],
                "digest_ok": False,
                "missing_evidence": str(exc),
                "statuses": statuses,
            })
            continue
        results.append({
            "question_id": question["question_id"],
            "digest_ok": refseed._evidence_digest(ordered)
                         == question["evidence_digest"],
            "statuses": statuses,
        })
    return {"questions": results, "operations": list(app.calls)}


def _probe_and_work(paths: dict[str, str]) -> dict[str, object]:
    """One namespace, both readings. The workload runs first, so a prober that
    left the namespace in a strange state cannot be what made it fail."""
    work = _workload()
    probe = _probe(paths)
    return {"workload": work, **probe}


# ---------------------------------------------------------------------------
# The detector. One function, used by the battery and by its positive control.


def violations(
    outcomes: list[dict[str, object]], under_test: LocationSet
) -> list[dict[str, object]]:
    """Every attempt that SUCCEEDED at a path `under_test` does not permit.

    Resolution goes through `LocationSet.declaring`, the supervisor's own
    resolver, rather than a second matcher written here. Two matchers that
    disagree is how a path becomes permitted by the auditor and absent to the
    kernel, or the reverse.
    """
    found = []
    for outcome in outcomes:
        if not outcome["ok"]:
            continue
        declaring = under_test.declaring(str(outcome["path"]))
        if declaring is None:
            found.append({**outcome, "why": "no declaration makes this reachable"})
        elif outcome["kind"] in (WRITE, MKDIR) and declaring.mode != "rw":
            found.append({
                **outcome,
                "why": f"declared {declaring.mode!r} by {declaring.rule_id}, "
                       "and this attempt modifies",
            })
    return found


def _run(location_set: LocationSet, tmp_path: Path, paths: dict[str, str]):
    staging = tmp_path / "staging"
    staging.mkdir(exist_ok=True)
    plan = mounts.plan(location_set, "s-t115", str(staging))
    out = mounts.run_in_namespace(plan, lambda: _probe_and_work(paths))
    assert out["ok"], out
    return out["result"]


@pytest.fixture()
def battery(world):
    """The battery run: the namespace and the set under test are the same set."""
    return _run(declared_only(), world["tmp"], world["paths"])


# ---------------------------------------------------------------------------
# SC-022 clause 1 — zero reads and zero writes succeed outside the set.


def test_no_adversarial_read_succeeds_outside_the_declared_set(battery) -> None:
    reads = [o for o in battery["outcomes"] if o["kind"] == READ]
    escaped = violations(reads, declared_only())
    assert not escaped, (
        "a read succeeded outside the declared set:\n"
        + "\n".join(f"  {o['label']}: {o['path']} — {o['why']}" for o in escaped)
    )


def test_no_adversarial_write_succeeds_outside_the_declared_set(battery) -> None:
    """The clause OD-24 ground ① rests on, probed rather than derived."""
    writes = [o for o in battery["outcomes"] if o["kind"] in (WRITE, MKDIR)]
    escaped = violations(writes, declared_only())
    assert not escaped, (
        "a write succeeded outside the declared set, which falsifies OD-24 "
        "ground ①'s claim that the landed mount repairs close finding 021's "
        "authority gaps:\n"
        + "\n".join(f"  {o['label']}: {o['path']} — {o['why']}" for o in escaped)
    )


def test_the_session_root_holds_only_the_declared_target(battery) -> None:
    """Finding 021's observable form: the listing, taken after the attempts."""
    top = str(FIXTURE).lstrip("/").split("/")[0]
    assert battery["root_listing"] == [top], (
        f"the session root lists {battery['root_listing']} after every write "
        f"arm; only {top!r} — the first component of the one declared "
        "target — should be there"
    )


def test_every_arm_actually_ran(battery) -> None:
    """The cheapest way a zero is free: nothing was attempted."""
    assert len(battery["outcomes"]) == len(ARMS)
    assert {o["label"] for o in battery["outcomes"]} == {a.label for a in ARMS}


def test_the_prober_can_succeed_at_all(battery) -> None:
    """A prober failing at everything is not containment.

    The one arm inside the declared set has to succeed, and it has to read
    real bytes. Without this the suite above is satisfied by a namespace whose
    build failed in a way that left nothing openable.
    """
    inside = [a for a in ARMS if a.inside_declared_set]
    assert inside, "no arm is inside the declared set; this control is vacuous"
    for arm in inside:
        outcome = next(o for o in battery["outcomes"] if o["label"] == arm.label)
        assert outcome["ok"], (
            f"{arm.label} failed with errno {outcome['errno']}. Every arm in "
            "this battery is then failing for a reason that has nothing to do "
            "with the declared set."
        )
        assert int(outcome["bytes"]) > 0


# ---------------------------------------------------------------------------
# SC-022 clause 2 — zero partially succeed.


def test_nothing_partially_succeeded(battery) -> None:
    """Refused at `open`, never between `open` and `write`."""
    partial = [
        o for o in battery["outcomes"]
        if o["kind"] in (WRITE, MKDIR) and o["stage"] == "write"
    ]
    assert not partial, (
        "an attempt obtained a descriptor outside the declared set and then "
        "failed writing through it, which is a partial success:\n"
        + "\n".join(f"  {o['label']}: {o['path']} errno {o['errno']}"
                    for o in partial)
    )


def test_the_undeclared_targets_are_byte_identical_afterwards(
    battery, world
) -> None:
    """The other half of "partially": the host-side bytes.

    A refusal that returned an errno after truncating the file would satisfy
    every assertion above. This is the reading that does not depend on what
    the prober reported.
    """
    changed = []
    for path, before in world["before"].items():
        after = Path(path).read_bytes()
        if after != before:
            changed.append(f"  {path}: {len(before)} bytes → {len(after)} bytes")
    assert not changed, (
        "an undeclared target's bytes moved during the battery:\n"
        + "\n".join(changed)
    )


def test_the_leak_directory_gained_nothing(battery, world) -> None:
    """The write arm's path must not exist on the host after the battery run.

    Separate from the byte check because this arm creates rather than
    overwrites, so there is no `before` to compare.
    """
    planted = Path(world["paths"]["leak_new"])
    assert not planted.exists(), (
        f"{planted} exists after the battery run, so the write arm against an "
        "undeclared location reached the host filesystem"
    )


# ---------------------------------------------------------------------------
# The workload. A containment result over a namespace nothing can live in is a
# statement about an empty box.


def test_the_workload_runs_and_its_answers_verify(battery) -> None:
    results = battery["workload"]["questions"]
    assert len(results) == 4, f"the reference application answered {len(results)}"
    failed = [r for r in results if not r["digest_ok"]]
    assert not failed, (
        "the reference application ran inside the namespace and could not "
        "reproduce every evidence digest, so the containment arms above were "
        "taken over a workload that was not working:\n" + json.dumps(failed)
    )


def test_the_workload_served_every_operation_it_was_asked_for(battery) -> None:
    served = battery["workload"]["operations"]
    assert served, "the workload made no calls"
    assert all(status == 200
               for r in battery["workload"]["questions"]
               for status in r["statuses"]), battery["workload"]["questions"]


# ---------------------------------------------------------------------------
# THE POSITIVE CONTROL.


@pytest.fixture()
def positive_control(world):
    """The same arm table, against a namespace that declares the leak.

    One variable differs from `battery`: the location set handed to
    `mounts.plan`. The arms, the prober, the detector and the set under test
    are identical.
    """
    return _run(declared_plus_leak(world["leak"]), world["tmp"], world["paths"])


def test_the_positive_control_is_caught_naming_the_path(
    positive_control, world
) -> None:
    """Rule 8's required second reading, recorded rather than only asserted.

    Without this, "zero violations" above and "the instrument is not wired"
    are the same output.

    **The catch is written to `results/`, not printed.** Capture is off in this
    repository, and `removal_proofs.sh` reads a test's baseline verdict off the
    same line as its node id — a test that writes to stdout while running puts
    `PASSED` on a later line, `baseline_py` finds no verdict, and every proof
    aimed at that test is scored `SKIPPED` and never attempted. Measured on
    2026-08-08: this test printed, and its own removal proof was skipped for
    the whole run.
    """
    caught = violations(positive_control["outcomes"], declared_only())
    record_evidence("t115-positive-control", {
        "detector": "violations(outcomes, declared_only())",
        "caught": [
            {
                "kind": o["kind"],
                "succeeded": o["ok"],
                "path": o["path"],
                "arm": o["label"],
                "why": o["why"],
            }
            for o in caught
        ],
    })

    paths = {str(o["path"]) for o in caught}
    assert world["paths"]["leak_existing"] in paths, (
        "the control read a file outside the set under test and the detector "
        f"did not name it. Caught: {sorted(paths)}"
    )
    assert world["paths"]["leak_new"] in paths, (
        "the control created a file outside the set under test and the "
        f"detector did not name it. Caught: {sorted(paths)}"
    )


def test_the_positive_controls_arms_really_did_reach_the_filesystem(
    positive_control, world
) -> None:
    """The control has to be a *success*, not merely a flagged failure.

    A detector that flagged a refused attempt would satisfy the test above
    while proving nothing, so the control's write is read back off the host.
    """
    outcomes = {o["key"]: o for o in positive_control["outcomes"]}
    assert outcomes["leak_existing"]["ok"], outcomes["leak_existing"]
    assert outcomes["leak_new"]["ok"], outcomes["leak_new"]
    planted = Path(world["paths"]["leak_new"])
    assert planted.exists() and planted.read_bytes() == MARKER, (
        "the positive control reported a successful write and the bytes are "
        "not on the host, so the control is not the success it claims"
    )


def test_the_control_and_the_battery_differ_in_one_variable(
    battery, positive_control
) -> None:
    """Both runs attempt the same arms; only the declaration moved.

    Stated as a test because a control that quietly ran a different arm table
    is a control of something else.
    """
    assert ([o["label"] for o in battery["outcomes"]]
            == [o["label"] for o in positive_control["outcomes"]])
    assert ([o["path"] for o in battery["outcomes"]]
            == [o["path"] for o in positive_control["outcomes"]])


def test_the_battery_refuses_exactly_where_the_control_succeeds(
    battery, positive_control
) -> None:
    """The delta, arm by arm. The two leak arms flip and nothing else does.

    Paired **positionally**, not by path: `declared_state` is the subject of
    two arms — a read that succeeds and a write that must not — and a
    path-keyed pairing silently compared the read of one run against the write
    of the other. That is a control reporting a delta it invented, which is
    the failure this file exists to catch, one level up.
    """
    flipped = {
        control["label"]
        for control, base in zip(
            positive_control["outcomes"], battery["outcomes"], strict=True
        )
        if control["ok"] and not base["ok"]
    }
    assert flipped == {
        "read the undeclared leak directory",
        "create a file in the undeclared leak directory",
    }, (
        f"declaring the leak changed the outcome of {sorted(flipped)}; only "
        "the two arms against it should move"
    )


# ---------------------------------------------------------------------------
# SC-022 clause 3 — 100% of refusals recorded with their rule.


def test_every_refusal_is_recorded_with_its_rule(battery, world) -> None:
    """Every refused arm classified by the supervisor's own decision path.

    Scored on the record's existence and its rule identifier, per SC-022's
    2026-08-03 narrowing: **no arm asserts that the recorded `path` equals the
    path the adversary asked for.** The supervisor reads that path out of the
    workload's own memory, and an arm asserting equality would fail against a
    correctly-behaving supervisor.
    """
    under_test = declared_only()
    sink = DecisionSink()
    refused = [o for o in battery["outcomes"] if not o["ok"]]
    assert refused, "no arm was refused; there is nothing to record"

    for outcome in refused:
        syscall = {READ: "openat", WRITE: "openat", MKDIR: "mkdirat"}[
            str(outcome["kind"])
        ]
        flags = None
        if syscall == "openat":
            flags = (os.O_WRONLY | os.O_CREAT | os.O_TRUNC
                     if outcome["kind"] == WRITE else os.O_RDONLY)
        sink.emit(decide(
            under_test,
            session_id="s-t115",
            syscall=syscall,
            path=str(outcome["path"]),
            pid=os.getpid(),
            flags=flags,
            path_provenance=PATH_SUPERVISOR_READ,
        ))

    assert len(sink.decisions) == len(refused), (
        "SC-022's recording clause is total: every refused attempt produces a "
        f"record. {len(refused)} refused, {len(sink.decisions)} recorded"
    )
    denials = [d for d in sink.decisions if d.disposition == DENY]
    assert len(denials) == len(refused), (
        "a refused attempt was classified as an allow:\n"
        + "\n".join(str(d.to_record()) for d in sink.decisions
                    if d.disposition == ALLOW)
    )
    assert sink.all_denials_carry_rule_id()
    assert all(not d.path_is_authoritative for d in sink.decisions), (
        "a record presented its path as a fact. The supervisor read it out of "
        "the workload's memory and cannot vouch for it (SC-022's narrowing)"
    )


def test_the_recorder_is_not_stamping_deny_on_everything(world) -> None:
    """The recording arm's own control.

    A classifier that denied unconditionally would satisfy the test above
    while carrying no information. The declared read has to come back `allow`
    with no rule, from the same call.
    """
    permitted = decide(
        declared_only(),
        session_id="s-t115",
        syscall="openat",
        path=world["paths"]["declared_state"],
        pid=os.getpid(),
        flags=os.O_RDONLY,
        path_provenance=PATH_SUPERVISOR_READ,
    )
    assert permitted.disposition == ALLOW
    assert permitted.rule_id is None


def test_the_declared_set_excludes_what_fr048_requires_it_to(world) -> None:
    """FR-048's exclusion clause, asserted for this battery's own set.

    The effect-gate rule set and the egress policy are two of the three
    targets SC-022 names, and a battery that attacked them from inside a
    namespace that had declared them would be measuring nothing.
    """
    assert_excludes(declared_only(), (
        world["paths"]["effect_gate"],
        world["paths"]["egress_policy"],
        world["paths"]["other_session_artifact"],
    ))


def test_the_exclusion_check_would_notice_a_declared_policy(world) -> None:
    """…and the exclusion check itself is not vacuous."""
    from src.supervisor.location_set import LocationSetError

    with pytest.raises(LocationSetError):
        assert_excludes(
            declared_plus_leak(world["leak"]),
            (world["paths"]["leak_existing"],),
        )


def test_the_refusals_name_the_absence_rather_than_a_permission(battery) -> None:
    """FR-048's structural property: undeclared is *absent*, not denied.

    `ENOENT` and `EROFS` are the two honest answers — nothing is there, or the
    mount refuses modification. `EACCES` would mean the path existed and
    something said no, which is the posture FR-048 exists to replace.
    """
    unexpected = [
        o for o in battery["outcomes"]
        if not o["ok"] and o["errno"] not in (errno.ENOENT, errno.EROFS)
    ]
    assert not unexpected, (
        "a refusal came back with an errno that is neither ENOENT nor EROFS:\n"
        + "\n".join(
            f"  {o['label']}: {errno.errorcode.get(int(o['errno']), o['errno'])}"
            for o in unexpected
        )
    )
