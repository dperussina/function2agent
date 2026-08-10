#!/usr/bin/env python3
"""The removal-proof harness's machine-readable record — writer and renderer.

    python3 tools/removal_proofs_summary.py OUT.json      # write (called by the harness)
    python3 tools/removal_proofs_summary.py --render F    # F -> markdown on stdout

`tests/removal_proofs.sh` prints a human report and then calls this to write the
same run down in a form that survives the terminal. It exists because the first
CI run of that harness was green and its output was unrecoverable, which makes
`61 proved` and `57 proved, 4 skipped` indistinguishable from outside — and those
are two different claims about the kernel mechanisms, not two phrasings of one.

WHAT THE RECORD IS A PROPERTY OF

`tests/batteries/results/seccomp-overhead.json` is the convention here, down to
the `what_this_is_a_property_of` key, and the reason carries over unchanged: a
figure without the environment that produced it cannot be compared with another
figure. For this instrument the **kernel release** is the load-bearing part.
Four arms — pivot_root, MS_REMOUNT, pids.max, cgroup attach ordering — are
attempted where their tests run and skipped where they do not, so the total
alone does not say which population it was taken over. Privilege and the
presence of a Go toolchain move the population the same way and are recorded
for the same reason.

WHY THIS CANNOT BECOME A WAY TO PASS

The writer refuses to produce a summary that reads as success out of a run that
measured nothing, and it refuses in the two places that matter:

  - On the harness's baseline abort it is invoked with status `aborted`, and it
    then emits **no** `totals` key and **no** `proofs` key. There is nothing for
    a consumer to read as a clean result; `totals.unproven == 0` raises.
  - When the per-proof entries and the harness's own counters disagree, the
    status becomes `inconsistent` and the totals carry `entries_recorded` beside
    them. Silently reconciling the two would make the record agree with itself
    by construction, which is the property least worth having.

Neither mode decides anything. The harness's exit status is computed from its
own failure counter and this file is never consulted for it. The renderer is the
one place that can fail a job, and only for the case that would otherwise be
indistinguishable from a good run: a green harness step that produced no record.

EVERY RUN, NOT JUST THE LAST ONE

The path the harness passes is `removal-proofs.latest.json` and the next run
overwrites it. `_archive` keeps a per-run copy beside it so a run that disagreed
with its neighbours can still be read. See that function for the run that made
this necessary.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
import sys
import time

# Stable codes, written by the harness, paired with the sentence the harness
# printed. Both go into the record: the code so a reader can count them, the
# sentence so a reader who has never opened the harness knows what happened.
REASONS = {
    "test-absent": (
        "the test named by this proof matched nothing in the baseline; it was "
        "renamed or removed, and the proof was pointed at nothing"
    ),
    "test-already-failing": (
        "the test already fails before the tamper, so its failure afterwards "
        "would prove nothing and the harness did NOT attempt the arm. Scored "
        "`unusable` since 2026-08-10 and never `unproven`: an unproven arm is one "
        "whose test PASSED without its mechanism, which says the mechanism is "
        "dead, and this arm says nothing about its mechanism in either direction. "
        "The commonest causes are a dirty baseline and a top-level directory "
        "missing from the harness's copy list — `deploy/`, `.github/` and "
        "`specs/` have each presented here"
    ),
    "test-skipped-in-baseline": (
        "pytest skipped this proof's test in this run's baseline, so the "
        "mechanism was NOT exercised here. The harness prints pytest's own "
        "recorded reason beside the arm; it does not name a cause of its own, "
        "because the text that used to stand here — 'privilege or platform' — "
        "was a diagnosis nothing had established and was measured wrong"
    ),
    "no-go-toolchain": (
        "no Go toolchain on PATH, so this cross-language arm was NOT exercised "
        "here. RETIRED as an outcome on 2026-08-08: a missing toolchain aborts "
        "the run instead of skipping its arms. Kept so that records written "
        "before that date still read"
    ),
    "baseline-verdict-unreadable": (
        "this proof's test appears in the baseline with no outcome on its line, "
        "so the harness could not establish that it passed untampered and did "
        "NOT attempt the arm. `pytest -v` writes the verdict on the node id's "
        "own line and any write reaching the real stdout splits the two. Never "
        "scored as skipped: a skip says the environment declined the test, and "
        "nothing declined this one"
    ),
    "go-arm-past-the-toolchain-abort": (
        "a Go arm reached the scorer with no toolchain present, which the "
        "baseline's abort exists to prevent; its declaration is not matched by "
        "the count that guards it. Refused rather than scored either way"
    ),
    "tamper-matched-nothing": (
        "the tamper matched nothing; the source moved under this proof"
    ),
    "tamper-ambiguous": (
        "the tamper matches more than one site, so it does not name a mechanism"
    ),
    "tamper-changed-nothing": "the tamper ran and changed nothing",
    "tampered-source-unparseable": (
        "the tampered source does not parse; the test would have failed for a "
        "reason this proof does not claim"
    ),
    "tamper-script-failed": "the tamper script failed to run",
    "tamper-broke-collection": (
        "the tamper broke collection rather than the mechanism; no test ran"
    ),
    "tampered-package-does-not-build": (
        "the tampered package does not build, so every test in it fails for a "
        "reason this proof does not claim"
    ),
    "still-passes-without-the-mechanism": (
        "the test still passes with the mechanism removed"
    ),
    "proof-killed-by-signal": (
        "the tampered test's process died on a signal, so no assertion was "
        "evaluated; a signalled process is non-zero for a reason that says "
        "nothing about the mechanism and is never scored as proved"
    ),
    "proof-did-not-return": (
        "the tampered test did not return within the harness's per-arm cap, so "
        "the mechanism was NOT measured; a hang is not a demonstrated failure "
        "and is never scored as proved"
    ),
}


def _cmd(*argv: str) -> str | None:
    """The tool's version string, or None when it is not usable here."""
    try:
        done = subprocess.run(argv, capture_output=True, text=True, timeout=30)
    except Exception:
        return None
    return done.stdout.strip() if done.returncode == 0 else None


def _int_or_none(name: str) -> int | None:
    raw = os.environ.get(name, "")
    return int(raw) if raw.isdigit() else None


def _environment(have_go: bool) -> dict:
    euid = _int_or_none("F2A_EUID")
    env = {
        "kernel": platform.release(),
        "system": platform.system(),
        "machine": platform.machine(),
        "platform": platform.platform(),
        "privileged": euid == 0,
        "euid": euid,
        "python": platform.python_version(),
        "pytest": _cmd(sys.executable, "-m", "pytest", "--version"),
        "go": _cmd("go", "version") if have_go else None,
    }
    if os.environ.get("GITHUB_ACTIONS") == "true":
        env["github"] = {
            k.lower().removeprefix("github_"): os.environ.get(k)
            for k in (
                "GITHUB_RUN_ID",
                "GITHUB_RUN_ATTEMPT",
                "GITHUB_WORKFLOW",
                "GITHUB_JOB",
                "GITHUB_SHA",
                "GITHUB_REF",
            )
        }
        env["github"]["runner_image"] = os.environ.get("ImageOS")
    return env


def _caveats(
    env: dict,
    have_go: bool,
    skipped: int,
    probed_go: bool = True,
    unreadable: int = 0,
    unusable: int = 0,
) -> list[str]:
    out = [
        "Kernel {kernel} on {system}/{machine}. Four arms — pivot_root, "
        "MS_REMOUNT, pids.max and cgroup attach ordering — are attempted only "
        "where their tests run, so a total taken on Darwin and a total taken "
        "on Linux are the same instrument over two different populations and "
        "must not be compared.".format(**env),
    ]
    if env["privileged"]:
        out.append(
            "A privileged run (euid 0). The kernel-mechanism arms were "
            "attempted rather than skipped for want of privilege."
        )
    else:
        out.append(
            "An UNPRIVILEGED run (euid {euid}). The kernel-mechanism arms need "
            "root; any skip below may be privilege rather than "
            "platform.".format(**env)
        )
    # The Go probe runs after the baseline, so on the abort path there is no
    # answer here and saying "no Go toolchain" would be a claim about something
    # never looked at — the failure this whole record exists to stop.
    if probed_go:
        out.append(
            "A Go toolchain was present, so the cross-language conformance and "
            "FR-017 arms were attempted."
            if have_go
            else "NO Go toolchain was present. Since 2026-08-08 that aborts the "
            "run rather than skipping its arms, so a COMPLETE record should "
            "never carry this sentence; if one does, the Go arms went missing "
            "from a total that was reported anyway."
        )
    out.append(
        "The baseline is the whole suite run untampered in this same tree, "
        "with this same interpreter and these same privileges. Each proof is "
        "attempted only if its own test RAN and PASSED there, so a proof whose "
        "test was skipped is recorded as skipped and never as proved."
    )
    if skipped:
        out.append(
            "{} arm(s) were NOT exercised in this environment. The proved count "
            "is a statement about the arms that ran, not about the mechanism "
            "set as a whole.".format(skipped)
        )
    if unreadable:
        out.append(
            "{} arm(s) name a test whose baseline line carries NO verdict, so "
            "the harness could not establish that it passed untampered and did "
            "not attempt the arm. These are counted apart from the skips on "
            "purpose: a skip is an arm the environment declined, and nothing "
            "declined these. This run is not green.".format(unreadable)
        )
    if unusable:
        out.append(
            "{} arm(s) name a test that was ALREADY FAILING in this run's "
            "baseline, so the harness refused to score them. These are counted "
            "apart from the unproven on purpose, and the distinction is the "
            "whole point: `unproven` means the mechanism is dead, and these arms "
            "established nothing about their mechanisms in either direction. "
            "Read them as a dirty baseline. If they share a directory, suspect "
            "the harness's copy list before suspecting the mechanisms. This run "
            "is not green.".format(unusable)
        )
    return out


def _read_records(path: str) -> list[dict]:
    proofs = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.rstrip("\n")
            if not line:
                continue
            outcome, reason, title, target_file, target_test, drifted = line.split("\t")
            entry = {
                "title": title,
                "target_file": target_file,
                "target_test": target_test,
                "outcome": outcome,
            }
            if reason:
                entry["reason"] = reason
                entry["reason_text"] = REASONS.get(reason, reason)
            if drifted == "yes":
                entry["tamper_drifted"] = True
            proofs.append(entry)
    return proofs


def write(out_path: str) -> int:
    status = os.environ.get("F2A_STATUS", "unknown")
    have_go = os.environ.get("F2A_HAVE_GO") == "1"
    env = _environment(have_go)

    doc = {
        "instrument": "tests/removal_proofs.sh",
        "measured_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "status": status,
        "environment": env,
    }

    if status == "aborted":
        # No totals and no proofs, deliberately. The harness refused to report a
        # number here; the record must not supply one on its behalf.
        doc["aborted_reason"] = os.environ.get("F2A_ABORT_REASON") or (
            "the harness refused to report a number in this environment"
        )
        doc["what_this_is_a_property_of"] = [
            "NOTHING WAS MEASURED. The harness aborted before any proof ran, so "
            "this record carries no totals and no per-proof outcomes by design.",
            *_caveats(env, have_go, 0, probed_go=False),
        ]
    else:
        proofs = _read_records(os.environ["F2A_RECORDS"])
        proved = _int_or_none("F2A_PASS") or 0
        unproven = _int_or_none("F2A_FAIL") or 0
        skipped = _int_or_none("F2A_SKIP") or 0
        timed_out = _int_or_none("F2A_TIMEOUT") or 0
        # Its own total, not folded into `unproven` or `skipped`. An arm whose
        # baseline verdict could not be read was never attempted, so `unproven`
        # would overstate it; and it is not an arm the environment declined, so
        # `skipped` would hide it in the one bucket where a lost arm is invisible.
        # Same reasoning as `timed_out`, which finding 032 settled.
        unreadable = _int_or_none("F2A_UNREADABLE") or 0
        # And the same reasoning again, applied to the case the comment above
        # missed rather than to a new one. By its own words: an arm whose baseline
        # verdict was *read and was failing* was equally never attempted, so
        # `unproven` overstates it in exactly the way described one line up. The
        # chain is `timed_out` (finding 032) -> `unreadable` (same reasoning,
        # stated above) -> here, and this is the third link, not a fourth
        # judgement.
        #
        # The distinction is not cosmetic, because `unproven` is the only word
        # this instrument produces that means **the mechanism is dead**. While
        # this outcome was folded into it, that word was also the presenting
        # symptom of a transiently dirty baseline ("236 proved, 58 unproven" over
        # 234 failing outcomes, with zero vacuous arms) and of three separate
        # omissions from the harness's copy list. Four conditions behind one word
        # teaches every reader to discount it.
        unusable = _int_or_none("F2A_UNUSABLE") or 0
        # Named rather than inlined into the `if`, because every outcome added
        # here has to join this sum and the line is now long enough that the next
        # one would wrap it. A wrapped condition is a worse tamper target: the two
        # removal proofs over this sum name it by its text.
        counted = proved + unproven + skipped + timed_out + unreadable + unusable
        if counted != len(proofs):
            doc["status"] = "inconsistent"
        doc["baseline"] = {
            "python_outcomes": _int_or_none("F2A_PY_TOTAL"),
            "python_not_passing": _int_or_none("F2A_PY_FAILED"),
            "go_outcomes": _int_or_none("F2A_GO_TOTAL"),
            "go_not_passing": _int_or_none("F2A_GO_FAILED"),
        }
        doc["totals"] = {
            "proved": proved,
            "unproven": unproven,
            "skipped": skipped,
            "timed_out": timed_out,
            "unreadable": unreadable,
            "unusable": unusable,
            "entries_recorded": len(proofs),
        }
        doc["skipped_titles"] = [p["title"] for p in proofs if p["outcome"] == "skipped"]
        doc["unproven_titles"] = [
            p["title"] for p in proofs if p["outcome"] == "unproven"
        ]
        doc["timed_out_titles"] = [
            p["title"] for p in proofs if p["outcome"] == "timed-out"
        ]
        doc["unreadable_titles"] = [
            p["title"] for p in proofs if p["outcome"] == "unreadable"
        ]
        doc["unusable_titles"] = [
            p["title"] for p in proofs if p["outcome"] == "unusable"
        ]
        doc["proofs"] = proofs
        doc["what_this_is_a_property_of"] = _caveats(
            env, have_go, skipped, unreadable=unreadable, unusable=unusable
        )

    body = json.dumps(doc, indent=2, sort_keys=True) + "\n"
    with open(out_path, "w", encoding="utf-8") as handle:
        handle.write(body)
    _archive(out_path, body)
    return 0


def _archive(out_path: str, body: str) -> None:
    """Keep this run's record beside the one the next run will overwrite.

    `tests/removal_proofs.sh` writes to `removal-proofs.latest.json` and the
    name is honest: the next run replaces it. On 2026-08-05 the harness reported
    `113 proved, 1 unproven` on one run and `114 proved, 0 unproven` on the
    three after it, and the run that disagreed **could no longer be read** — so
    nobody could say which proof it was, whether it was flaky or fixed, or
    whether the three green runs were the same instrument. An instrument that
    disagrees with itself once in four is worth more than one that never does;
    it is only worth anything if the disagreeing run survives.

    Named by content digest as well as by clock, so two runs in the same second
    with different outcomes are two files and two identical runs are one. This
    never raises: the canonical record at `out_path` is the contract and a
    failure to keep an extra copy must not turn a green run red. It says so on
    stderr instead, because an archive that silently stopped working is the
    thing this exists to prevent, one level up.
    """
    directory = os.path.join(os.path.dirname(os.path.abspath(out_path)),
                             "removal-proofs-history")
    stem = os.path.basename(out_path).removesuffix(".json").removesuffix(".latest")
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()[:12]
    name = "{}-{}-{}.json".format(stem, time.strftime("%Y%m%dT%H%M%S"), digest)
    try:
        os.makedirs(directory, exist_ok=True)
        with open(os.path.join(directory, name), "w", encoding="utf-8") as handle:
            handle.write(body)
    except OSError as exc:
        print(
            "WARNING: this run's record was written to {} but could not be "
            "archived to {} ({}). The next run will overwrite it and this run "
            "will not be readable afterwards.".format(out_path, directory, exc),
            file=sys.stderr,
        )


def render(in_path: str) -> int:
    """JSON -> markdown on stdout. Exit 1 when there is no record to render."""
    try:
        with open(in_path, encoding="utf-8") as handle:
            doc = json.load(handle)
    except (OSError, ValueError) as exc:
        print("## Removal proofs — NO RECORD\n")
        print(
            "The harness produced no readable record at `{}` ({}). A run whose "
            "outcomes cannot be read afterwards is exactly the state this "
            "record exists to remove, so this step fails rather than letting a "
            "green tick stand in for evidence nobody can see.".format(in_path, exc)
        )
        return 1

    env = doc.get("environment", {})
    ident = "kernel `{}` on {}, {}, python {}".format(
        env.get("kernel"),
        env.get("system"),
        "privileged" if env.get("privileged") else "**unprivileged**",
        env.get("python"),
    )

    if doc.get("status") == "aborted":
        print("## Removal proofs — ABORTED, nothing measured\n")
        print("> {}\n".format(doc.get("aborted_reason")))
        print(
            "No totals are recorded, by design: the harness refuses to report a "
            "number in an environment it cannot measure in.\n"
        )
        print("Measured on {}.".format(ident))
        return 0

    totals = doc.get("totals", {})
    proved = totals.get("proved", 0)
    unproven = totals.get("unproven", 0)
    skipped = totals.get("skipped", 0)
    # `.get` with a default rather than `[...]`, because every record written
    # before the per-arm cap existed has no such key and those runs still have
    # to render. A missing key means the run predates the cap, not that it had
    # none — see the timed-out section below, which says so.
    timed_out = totals.get("timed_out", 0)
    # Same reasoning as `timed_out` above: absent from every record written before
    # 2026-08-08, and a missing key means the run predates the outcome rather than
    # that it had none.
    unreadable = totals.get("unreadable", 0)
    # Same reasoning again. Absent from every record written before this outcome
    # was split out of `unproven`, and `render` is run over the archive, so a
    # missing key must mean the run predates the outcome rather than crash.
    unusable = totals.get("unusable", 0)

    print("## Removal proofs\n")
    print(
        "| proved | unproven | **skipped** | **timed out** | "
        "**baseline unreadable** | **baseline already failing** | entries |"
    )
    print("|---:|---:|---:|---:|---:|---:|---:|")
    print(
        "| {} | {} | **{}** | **{}** | **{}** | **{}** | {} |\n".format(
            proved,
            unproven,
            skipped,
            timed_out,
            unreadable,
            unusable,
            totals.get("entries_recorded"),
        )
    )
    print("Measured on {}.\n".format(ident))

    if doc.get("status") == "inconsistent":
        print(
            "> **INCONSISTENT** — the harness's counters and the recorded "
            "entries disagree. Treat every number above as unreliable.\n"
        )

    if skipped:
        print(
            "### {} arm(s) were NOT exercised here\n\n"
            "A skipped arm is not a proved arm. The mechanisms below were not "
            "tested by this run.\n".format(skipped)
        )
        for proof in doc.get("proofs", []):
            if proof["outcome"] == "skipped":
                print("- **{}** — {}".format(proof["title"], proof.get("reason_text")))
        print()
    else:
        print("Every declared arm was exercised in this environment.\n")

    if unreadable:
        print(
            "### {} arm(s) name a test with NO baseline verdict\n\n"
            "These were never attempted, and they are **not** skips. `pytest -v` "
            "writes a test's verdict on the same line as its node id, so anything "
            "the test writes to the real stdout while it runs pushes the verdict "
            "onto the next line and the harness can no longer read it. A skip "
            "says the environment declined the test; nothing declined "
            "these.\n".format(unreadable)
        )
        for proof in doc.get("proofs", []):
            if proof["outcome"] == "unreadable":
                print("- **{}** — {}".format(proof["title"], proof.get("reason_text")))
        print()

    if timed_out:
        print(
            "### {} arm(s) DID NOT RETURN\n\n"
            "Each of these was attempted and consumed the harness's per-arm cap "
            "without reporting, so its mechanism was not measured. A timed-out "
            "arm is neither proved nor skipped: scoring it proved would read a "
            "killed process as a demonstrated failure, and scoring it skipped "
            "would let it leave a green run unnoticed.\n".format(timed_out)
        )
        for proof in doc.get("proofs", []):
            if proof["outcome"] == "timed-out":
                print("- **{}** — {}".format(proof["title"], proof.get("reason_text")))
        print()

    if unusable:
        print(
            "### {} arm(s) name a test that was ALREADY FAILING\n\n"
            "The harness refused to score these, and they are **not** unproven. "
            "`unproven` means the test still passed with its mechanism removed — "
            "the mechanism is dead. These arms establish nothing about their "
            "mechanisms in either direction, because their named test was already "
            "failing before anything was tampered.\n\n"
            "Read this as a dirty baseline rather than as a result. If these arms "
            "share a directory, suspect the harness's copy list before suspecting "
            "the mechanisms: `deploy/`, `.github/` and `specs/` each reached this "
            "bucket by being absent from it, and in none of those cases did "
            "anything in this summary say so.\n".format(unusable)
        )
        for proof in doc.get("proofs", []):
            if proof["outcome"] == "unusable":
                print("- **{}** — {}".format(proof["title"], proof.get("reason_text")))
        print()

    if unproven:
        print("### {} unproven\n".format(unproven))
        for proof in doc.get("proofs", []):
            if proof["outcome"] == "unproven":
                print("- **{}** — {}".format(proof["title"], proof.get("reason_text")))
        print()

    drifted = [p["title"] for p in doc.get("proofs", []) if p.get("tamper_drifted")]
    if drifted:
        print(
            "### {} tamper(s) matched only after whitespace normalization\n".format(
                len(drifted)
            )
        )
        for title in drifted:
            print("- {}".format(title))
        print()

    for caveat in doc.get("what_this_is_a_property_of", []):
        print("> {}\n".format(caveat))
    return 0


def main(argv: list[str]) -> int:
    if len(argv) == 3 and argv[1] == "--render":
        return render(argv[2])
    if len(argv) == 2 and not argv[1].startswith("-"):
        return write(argv[1])
    print(__doc__.strip().splitlines()[0], file=sys.stderr)
    print(
        "usage: removal_proofs_summary.py OUT.json | --render IN.json",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
