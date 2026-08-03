"""SPIKE - E8 verifier-vs-judge. Delete after 2026-11-30. Do not import from product code.

The corpus freeze, and the refusal that enforces it.

PREREGISTRATION.md 2 records that a ceiling-test run was writing to ``results.jsonl``
while the preregistration was being drafted, and pins the scoring set to the **11 complete
run directories** that existed at 2026-08-03 07:10 and to nothing else. The corpus has grown
since: ``20260803T070942-diag-...`` was in progress at freeze time and two further
directories appeared after it. Those records belong to E9.

So the scope is a committed list of directory names plus the SHA-256 of every
``results.jsonl`` and ``traces.jsonl`` in it, and every entry point calls
:func:`verify_or_die` before doing anything else. A run that scores a moved corpus is not
the run that was pre-registered, and the failure has to be loud rather than discovered
afterwards in a diff.

**The freeze pins the battery too, and that is not how it started.** Until 2026-08-03 this
file hashed the *records* and nothing else. It did not hash ``tasks.json``, it did not hash
``tasks/expected.json``, and it did not record which battery version each run had actually
executed. A trace stores no prompt, so nothing anywhere connected a record to the question
its agent was asked. Every arm is fed ``redact.scoring_view(trace, prompt)`` with ``prompt``
read from *today's* ``tasks.json``, and the join that produced that pairing was unchecked:
143 of the 246 in-scope records ran under a battery version that no longer exists, and
7 of them were graded against an answer today's battery no longer computes. The defect was
invisible for the corpus's entire existence because a wrong join produces no error — it
produces a plausible pairing. Amendment B3 records the defect; this module is half of the
fix (:func:`corpus.eligibility` is the other half).

Three things are pinned now that were not:

* the SHA-256 of ``tasks/tasks.json`` and ``tasks/expected.json`` — the battery itself;
* the SHA-256 of every in-scope ``manifest.json``, which is where ``battery_version`` lives;
* the ``battery_version`` each run executed, per run, checked against the battery's own
  declared version so that a **cross-battery join is a named, counted condition** rather
  than a silent one.

    python3 freeze.py --build     # write corpus_freeze.json (done once, committed)
    python3 freeze.py --verify    # what every entry point does
    python3 freeze.py --battery   # the battery attestation, per run
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FREEZE_PATH = os.path.join(HERE, "corpus_freeze.json")

#: The 11 complete run directories named by PREREGISTRATION.md 2. This list is data, not a
#: glob, precisely because a glob would silently absorb whatever the corpus grows next.
SCOPE_RUNS: list[str] = [
    "20260802T151714-smoke",
    "20260802T152825-smoke2",
    "20260802T154826-calibration",
    "20260802T160705-recalibration",
    "20260802T163319-bias-probe",
    "20260802T164929-bias-probe-perrecord",
    "20260802T165903-ambiguity-recheck",
    "20260802T173226-reprobe-perrecord-v2",
    "20260802T173614-baseline-lookup-R1R2",
    "20260803T064400-smoke-paired-precheck",
    "20260803T064550-paired-lookup-R1R2-A3budgets",
]

#: Directories known to exist and known to be out of scope. Listed so that their presence is
#: an expected condition rather than a surprise, and so a reviewer can see the harness knows
#: about them and is declining them on purpose.
KNOWN_OUT_OF_SCOPE_PREFIX = "20260803T070942"

#: ``manifest.json`` is hashed alongside the records because it is the only artifact that
#: records which battery version a run executed. Leaving it unpinned is what let the
#: cross-battery join go unnoticed: the evidence existed on disk and nothing read it.
FILES = ("results.jsonl", "traces.jsonl", "manifest.json")

#: Counted at freeze time, not estimated. verify_or_die re-counts and refuses on drift.
EXPECTED_SHAPE = {
    "records": 246,
    "traces": 246,
    "pass": 226,
    "fail": 20,
    "false_success": 11,
    "distinct_tasks": 61,
    "distinct_false_success_tasks": 6,
}

#: The battery version E8 scores against, taken from ``tasks/expected.json``'s own
#: ``battery_version`` field. Pinned here so that swapping the battery under the harness is
#: a refusal rather than a re-interpretation of every record.
EXPECTED_BATTERY_VERSION = "1.4.0-probe"

#: Counted at freeze time. Runs whose manifest declares a different ``battery_version`` than
#: the battery being scored against. Their records cannot be joined to today's prompt without
#: per-record attestation (:func:`corpus.eligibility`). Listing the count here means a future
#: change to the corpus that alters it is a refusal, not a surprise.
EXPECTED_CROSS_BATTERY_RUNS = 5
EXPECTED_CROSS_BATTERY_RECORDS = 143


def load_config() -> dict:
    with open(os.path.join(HERE, "config.json"), encoding="utf-8") as fh:
        return json.load(fh)


def corpus_root(cfg: dict | None = None) -> str:
    cfg = cfg or load_config()
    return os.path.abspath(os.path.join(HERE, cfg["corpus"]["source_rel"]))


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def battery_paths(cfg: dict | None = None) -> dict[str, str]:
    """The battery artifacts the scoring join depends on, by config key.

    ``tasks_rel`` supplies the **prompt** every arm is shown; ``expected_rel`` supplies the
    **answer** each record's stored ``expected`` is compared against. Both are inputs to the
    join, so both are pinned.
    """
    cfg = cfg or load_config()
    return {
        key: os.path.abspath(os.path.join(HERE, cfg["battery"][key]))
        for key in ("tasks_rel", "expected_rel")
    }


def declared_battery_version(cfg: dict | None = None) -> str:
    """The battery's own version, read from ``expected.json``, not from config.

    Read from the artifact rather than asserted in config on purpose: a config value can be
    edited to agree with whatever is on disk, which is the failure mode this whole module
    exists to prevent.
    """
    with open(battery_paths(cfg)["expected_rel"], encoding="utf-8") as fh:
        return json.load(fh)["battery_version"]


def measure(root: str, cfg: dict | None = None) -> dict:
    """Hash every in-scope file and the battery, and count the corpus shape."""
    cfg = cfg or load_config()
    entries: dict[str, dict[str, str]] = {}
    run_versions: dict[str, str] = {}
    rows: list[dict] = []
    trace_ids: list[tuple] = []
    for run in SCOPE_RUNS:
        d = os.path.join(root, run)
        if not os.path.isdir(d):
            raise SystemExit(f"in-scope run directory is missing: {d}")
        entries[run] = {}
        for fn in FILES:
            p = os.path.join(d, fn)
            if not os.path.isfile(p):
                raise SystemExit(f"in-scope file is missing: {p}")
            entries[run][fn] = sha256_file(p)
        with open(os.path.join(d, "manifest.json"), encoding="utf-8") as fh:
            run_versions[run] = json.load(fh)["battery_version"]
        with open(os.path.join(d, "results.jsonl"), encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    rows.append(json.loads(line))
        with open(os.path.join(d, "traces.jsonl"), encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    r = json.loads(line)
                    trace_ids.append((r["run_id"], r["task_id"], r["arm"], r["attempt"]))

    fs = [r for r in rows if r.get("false_success")]
    shape = {
        "records": len(rows),
        "traces": len(trace_ids),
        "pass": sum(1 for r in rows if r["outcome"] == "pass"),
        "fail": sum(1 for r in rows if r["outcome"] == "fail"),
        "false_success": len(fs),
        "distinct_tasks": len({r["task_id"] for r in rows}),
        "distinct_false_success_tasks": len({r["task_id"] for r in fs}),
    }
    version = declared_battery_version(cfg)
    cross = sorted(r for r, v in run_versions.items() if v != version)
    battery = {
        "version": version,
        "files": {key: sha256_file(p) for key, p in battery_paths(cfg).items()},
        "run_battery_versions": run_versions,
        "cross_battery_runs": cross,
        "cross_battery_records": sum(1 for r in rows if run_versions[r["run_id"]] != version),
    }
    scope = [
        {"run_id": r["run_id"], "task_id": r["task_id"], "arm": r["arm"], "attempt": r["attempt"]}
        for r in rows
    ]
    return {"files": entries, "shape": shape, "scope": scope, "battery": battery}


def build(root: str, cfg: dict | None = None) -> dict:
    m = measure(root, cfg)
    doc = {
        "_comment": (
            "Frozen scope for E8. PREREGISTRATION.md 2 pins the scoring set to these 11 "
            "complete ceiling-test run directories. Any hash change means the corpus moved "
            "and the pre-registered run cannot proceed against it."
        ),
        "_battery_comment": (
            "Amendment B3/B4. A trace stores no prompt, so joining a record to today's "
            "tasks.json is an unchecked cross-artifact join. The battery is pinned here — its "
            "files, its declared version, and the version every in-scope run actually "
            "executed — so that a cross-battery join is a counted condition. corpus.eligibility "
            "decides per record whether the join is attested; freeze.verify refuses if the "
            "battery itself moves."
        ),
        "frozen_at": "2026-08-03",
        "scope_runs": SCOPE_RUNS,
        "out_of_scope_note": (
            f"{KNOWN_OUT_OF_SCOPE_PREFIX}-diag-... was in progress at freeze time; it and every "
            "later directory are out of scope for E8 and may be used only in E9."
        ),
        "files": m["files"],
        "shape": m["shape"],
        "battery": m["battery"],
        "scope_tuples": m["scope"],
    }
    with open(FREEZE_PATH, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=1)
    return doc


def load_freeze() -> dict:
    if not os.path.isfile(FREEZE_PATH):
        raise SystemExit(
            f"corpus freeze is missing: {FREEZE_PATH}\n"
            "  Run: python3 freeze.py --build\n"
            "  The freeze must be committed before any judge call is made."
        )
    with open(FREEZE_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def verify(root: str, frozen: dict | None = None, cfg: dict | None = None) -> list[str]:
    """Returns a list of human-readable drift complaints. Empty means the corpus is intact."""
    frozen = frozen or load_freeze()
    cfg = cfg or load_config()
    problems: list[str] = []

    if frozen["scope_runs"] != SCOPE_RUNS:
        problems.append("the committed scope_runs list does not match freeze.SCOPE_RUNS")

    for run in SCOPE_RUNS:
        for fn in FILES:
            p = os.path.join(root, run, fn)
            if not os.path.isfile(p):
                problems.append(f"missing: {run}/{fn}")
                continue
            want = frozen["files"].get(run, {}).get(fn)
            got = sha256_file(p)
            if want is None:
                problems.append(f"no frozen hash recorded for {run}/{fn}")
            elif want != got:
                problems.append(
                    f"HASH CHANGED {run}/{fn}\n      frozen {want}\n      now    {got}"
                )

    problems += verify_battery(frozen, cfg)

    if not problems:
        shape = measure(root, cfg)["shape"]
        for k, want in EXPECTED_SHAPE.items():
            if shape[k] != want:
                problems.append(f"corpus shape drifted: {k} is {shape[k]}, frozen at {want}")
        if shape != frozen["shape"]:
            problems.append("recounted shape does not match the committed freeze shape")

    return problems


def verify_battery(frozen: dict, cfg: dict | None = None) -> list[str]:
    """Refuse if the battery moved, or if the cross-battery exposure is not what was frozen.

    Separate from the record hashes because it answers a different question. The record
    hashes ask "is this the same corpus"; this asks "is this the same *question* the corpus
    was graded against". The second went unasked until Amendment B3, and a wrong answer to it
    is undetectable downstream: the join succeeds and produces a plausible pairing.
    """
    cfg = cfg or load_config()
    problems: list[str] = []
    pinned = frozen.get("battery")
    if not pinned:
        return ["the committed freeze pins no battery. Rebuild it: python3 freeze.py --build\n"
                "      Amendment B3: a freeze that pins records but not the battery cannot "
                "detect a cross-battery join, which is the defect B3 records."]

    for key, path in battery_paths(cfg).items():
        if not os.path.isfile(path):
            problems.append(f"battery artifact is missing: {path}")
            continue
        want, got = pinned["files"].get(key), sha256_file(path)
        if want is None:
            problems.append(f"no frozen hash recorded for the battery's {key}")
        elif want != got:
            problems.append(
                f"BATTERY CHANGED {key} ({os.path.basename(path)})\n"
                f"      frozen {want}\n      now    {got}\n"
                "      Every record's stored `expected` was compared against the frozen "
                "battery. A new battery re-decides which records are eligible (B3.2), so the "
                "eligibility ledger must be recomputed before anything is scored."
            )

    version = declared_battery_version(cfg)
    if version != pinned["version"]:
        problems.append(f"battery version is {version!r}, frozen at {pinned['version']!r}")
    if version != EXPECTED_BATTERY_VERSION:
        problems.append(
            f"battery version is {version!r}, but freeze.EXPECTED_BATTERY_VERSION is "
            f"{EXPECTED_BATTERY_VERSION!r}"
        )
    if len(pinned.get("cross_battery_runs") or []) != EXPECTED_CROSS_BATTERY_RUNS:
        problems.append(
            f"the freeze records {len(pinned.get('cross_battery_runs') or [])} cross-battery "
            f"run(s); {EXPECTED_CROSS_BATTERY_RUNS} were counted at freeze time"
        )
    if pinned.get("cross_battery_records") != EXPECTED_CROSS_BATTERY_RECORDS:
        problems.append(
            f"the freeze records {pinned.get('cross_battery_records')} cross-battery "
            f"record(s); {EXPECTED_CROSS_BATTERY_RECORDS} were counted at freeze time"
        )
    return problems


def battery_attestation(frozen: dict | None = None, cfg: dict | None = None) -> dict:
    """Per run: the battery version it executed, and whether that is today's.

    ``same_battery`` runs need no cross-artifact join at all — the prompt they are shown is
    the prompt their agents saw. ``cross_battery`` runs do, and every record in one has to
    earn its eligibility individually (:func:`corpus.eligibility`).
    """
    frozen = frozen or load_freeze()
    pinned = frozen.get("battery") or {}
    version = pinned.get("version")
    runs = pinned.get("run_battery_versions") or {}
    return {
        "battery_version": version,
        "run_battery_versions": runs,
        "same_battery_runs": sorted(r for r, v in runs.items() if v == version),
        "cross_battery_runs": sorted(r for r, v in runs.items() if v != version),
        "cross_battery_records": pinned.get("cross_battery_records"),
    }


def run_battery_version(run_id: str, frozen: dict | None = None) -> str | None:
    """The battery version a run executed, or None if the run is not pinned.

    ``None`` is never treated as "probably fine" by a caller: an unpinned run cannot be
    attested, and :func:`corpus.eligibility` makes that ineligible rather than eligible.
    """
    frozen = frozen or load_freeze()
    return ((frozen.get("battery") or {}).get("run_battery_versions") or {}).get(run_id)


def verify_or_die(cfg: dict | None = None) -> dict:
    """Every entry point calls this before anything else. Refuses to start on drift."""
    cfg = cfg or load_config()
    root = corpus_root(cfg)
    frozen = load_freeze()
    problems = verify(root, frozen, cfg)
    if problems:
        sys.exit(
            "REFUSING TO START — the frozen corpus has moved.\n\n"
            + "\n".join(f"  - {p}" for p in problems)
            + "\n\nPREREGISTRATION.md 2 fixes the scoring set to the 11 complete run\n"
            "directories listed in corpus_freeze.json and to nothing else. Scoring a\n"
            "different set is a different experiment. Do not re-freeze to make this pass:\n"
            "records added after the freeze belong to E9.\n"
        )
    return frozen


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--build", action="store_true", help="write corpus_freeze.json")
    ap.add_argument("--verify", action="store_true", help="check the corpus against the freeze")
    ap.add_argument("--battery", action="store_true",
                    help="print the battery attestation, per run")
    args = ap.parse_args()
    cfg = load_config()
    root = corpus_root(cfg)

    if args.build:
        doc = build(root, cfg)
        print(f"wrote {FREEZE_PATH}")
        print(f"  {len(doc['scope_runs'])} run directories, "
              f"{len(doc['scope_runs']) * len(FILES)} files hashed")
        for k, v in doc["shape"].items():
            print(f"  {k:<28} {v}")
        b = doc["battery"]
        print(f"  {'battery_version':<28} {b['version']}")
        print(f"  {'battery files hashed':<28} {len(b['files'])}")
        print(f"  {'cross-battery runs':<28} {len(b['cross_battery_runs'])}")
        print(f"  {'cross-battery records':<28} {b['cross_battery_records']}")
        return 0

    if args.battery:
        att = battery_attestation(cfg=cfg)
        print(f"battery under test: {att['battery_version']}")
        for run, v in sorted(att["run_battery_versions"].items()):
            tag = "same battery" if v == att["battery_version"] else "CROSS-BATTERY"
            print(f"  {run:<45} {v:<14} {tag}")
        print(f"\n{len(att['cross_battery_runs'])} of {len(att['run_battery_versions'])} runs "
              f"ran a different battery, covering {att['cross_battery_records']} records.")
        print("Those records carry no prompt, so joining them to today's tasks.json is only "
              "sound\nwhere corpus.eligibility can attest it per record. Run: "
              "python3 corpus.py --eligibility")
        return 0

    problems = verify(root, cfg=cfg)
    if problems:
        print("corpus freeze: DRIFT")
        for p in problems:
            print(f"  - {p}")
        return 1
    att = battery_attestation(cfg=cfg)
    print(f"corpus freeze: intact — {len(SCOPE_RUNS)} runs, "
          f"{EXPECTED_SHAPE['records']} records, {EXPECTED_SHAPE['fail']} negatives")
    print(f"battery freeze: intact — {att['battery_version']}, "
          f"{len(att['cross_battery_runs'])} cross-battery run(s), "
          f"{att['cross_battery_records']} cross-battery record(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
