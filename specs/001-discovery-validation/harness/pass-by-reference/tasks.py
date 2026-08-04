"""SPIKE - E17 pass-by-reference. Delete after 2026-11-30. Do not import from product code.

The 18-task battery, its oracle plans, and — separately — its checkers.

**Two independent computations of every answer, on purpose.** Each task carries a
shell `plan` (what a competent operator would type) and a `check` (a Python function
reading the same files directly). They share no code. `selftest.py` asserts they
agree on all 18 tasks, which is the validation constitution Principle I requires of
a derived verifier: the verifier is checked against an artefact its own derivation
did not produce. If they ever disagree, the battery is broken and the run must not
start — not "the checker is probably right".

**The plans are exploratory, not minimal.** A minimal plan for "how many ERROR
lines" is one `grep -c`, which prints eleven bytes and would make the treatment
under test unmeasurable by construction. The committed plans are what an agent
actually does: orient, peek, cast wide, narrow, answer. The wide steps are where
bulk enters the transcript, and their sizes are *measured* from the generated
corpus by `measure.py` rather than assumed by the projection.
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass, field
from typing import Callable

LOG = "logs/app.log"
CSV = "data/metrics.csv"


@dataclass(frozen=True)
class Step:
    label: str
    cmd: str


@dataclass(frozen=True)
class Task:
    id: str
    family: str
    prompt: str
    plan: list[Step]
    check: Callable[[str], str] = field(repr=False)


# --- shell side ------------------------------------------------------------

def run_step(root: str, cmd: str, timeout: float = 60.0) -> tuple[bytes, bytes, int]:
    """Run one plan step under the corpus root. No model, no network, no cost."""
    env = dict(os.environ, LC_ALL="C", LANG="C")
    proc = subprocess.run(["bash", "-c", cmd], cwd=root, capture_output=True,
                          timeout=timeout, env=env)
    return proc.stdout, proc.stderr, proc.returncode


def answer_from_plan(root: str, task: Task) -> str:
    out, _, _ = run_step(root, task.plan[-1].cmd)
    return out.decode("utf-8", "replace").strip()


# --- checker side (independent of every shell command above) ---------------

def _log_lines(root: str) -> list[str]:
    with open(os.path.join(root, LOG)) as fh:
        return [ln for ln in fh.read().split("\n") if ln]


def _log_fields(line: str) -> dict:
    parts = line.split(" ")
    return {
        "ts": parts[0], "level": parts[1], "service": parts[2],
        "req": parts[3].split("=", 1)[1],
        "status": int(parts[4].split("=", 1)[1]),
        "dur": int(parts[5].split("=", 1)[1]),
    }


def _csv_rows(root: str) -> list[dict]:
    with open(os.path.join(root, CSV)) as fh:
        lines = [ln for ln in fh.read().split("\n") if ln]
    out = []
    for ln in lines[1:]:
        ts, region, svc, req, err, p95 = ln.split(",")
        out.append({"ts": ts, "region": region, "service": svc,
                    "requests": int(req), "errors": int(err), "p95": int(p95)})
    return out


def _py_files(root: str) -> list[tuple[str, str]]:
    out = []
    for dirpath, dirnames, filenames in os.walk(os.path.join(root, "src")):
        dirnames.sort()
        for fn in sorted(filenames):
            if fn.endswith(".py"):
                p = os.path.join(dirpath, fn)
                with open(p) as fh:
                    out.append((os.path.relpath(p, root), fh.read()))
    return sorted(out)


def _top(counts: dict[str, int]) -> str:
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]


TASKS: list[Task] = [
    # --- family: log -------------------------------------------------------
    Task("T01", "log", "How many lines in logs/app.log are at ERROR level? Answer with the number only.",
         [Step("orient", "ls -R . | head -40"),
          Step("peek", f"head -20 {LOG}"),
          Step("broad", f"grep ' ERROR ' {LOG}"),
          Step("narrow", f"grep ' ERROR ' {LOG} | cut -d' ' -f1-3"),
          Step("answer", f"grep -c ' ERROR ' {LOG}")],
         lambda r: str(sum(1 for ln in _log_lines(r) if _log_fields(ln)["level"] == "ERROR"))),

    Task("T02", "log", "Which service emits the most 5xx statuses in logs/app.log? Answer with the service name only.",
         [Step("peek", f"head -5 {LOG}"),
          Step("broad", f"grep -E 'status=5[0-9][0-9]' {LOG}"),
          Step("narrow", "grep -E 'status=5[0-9][0-9]' %s | awk '{print $3}'" % LOG),
          Step("tally", "grep -E 'status=5[0-9][0-9]' %s | awk '{print $3}' | sort | uniq -c | sort -k1,1rn -k2,2" % LOG),
          Step("answer", "grep -E 'status=5[0-9][0-9]' %s | awk '{print $3}' | sort | uniq -c | sort -k1,1rn -k2,2 | head -1 | awk '{print $2}'" % LOG)],
         lambda r: _top({s: sum(1 for ln in _log_lines(r)
                                if _log_fields(ln)["service"] == s and 500 <= _log_fields(ln)["status"] < 600)
                         for s in {_log_fields(ln)["service"] for ln in _log_lines(r)}})),

    Task("T03", "log", "How many distinct req ids in logs/app.log carry status=503? Answer with the number only.",
         [Step("peek", f"head -5 {LOG}"),
          Step("broad", f"grep 'status=503' {LOG}"),
          Step("narrow", "grep 'status=503' %s | awk '{print $4}'" % LOG),
          Step("answer", "grep 'status=503' %s | awk '{print $4}' | sort -u | wc -l | tr -d ' '" % LOG)],
         lambda r: str(len({_log_fields(ln)["req"] for ln in _log_lines(r)
                            if _log_fields(ln)["status"] == 503}))),

    Task("T04", "log", "What is the largest dur_ms on any WARN line in logs/app.log? Answer with the number only.",
         [Step("peek", f"head -5 {LOG}"),
          Step("broad", f"grep ' WARN ' {LOG}"),
          Step("narrow", "grep ' WARN ' %s | sed 's/.*dur_ms=//' | cut -d' ' -f1" % LOG),
          Step("answer", "grep ' WARN ' %s | sed 's/.*dur_ms=//' | cut -d' ' -f1 | sort -n | tail -1" % LOG)],
         lambda r: str(max(_log_fields(ln)["dur"] for ln in _log_lines(r)
                           if _log_fields(ln)["level"] == "WARN"))),

    Task("T05", "log", "How many log lines in logs/app.log fall in the 03 hour? Answer with the number only.",
         [Step("orient", "ls -R . | head -40"),
          Step("broad", f"grep 'T03:' {LOG}"),
          Step("narrow", "grep 'T03:' %s | awk '{print $2}'" % LOG),
          Step("answer", f"grep -c 'T03:' {LOG}")],
         lambda r: str(sum(1 for ln in _log_lines(r) if "T03:" in _log_fields(ln)["ts"]))),

    Task("T06", "log", "How many distinct services appear in logs/app.log? Answer with the number only.",
         [Step("peek", f"head -5 {LOG}"),
          Step("broad", "awk '{print $3}' %s" % LOG),
          Step("narrow", "awk '{print $3}' %s | sort | uniq -c" % LOG),
          Step("answer", "awk '{print $3}' %s | sort -u | wc -l | tr -d ' '" % LOG)],
         lambda r: str(len({_log_fields(ln)["service"] for ln in _log_lines(r)}))),

    # --- family: csv -------------------------------------------------------
    Task("T07", "csv", "What is the total of the requests column in data/metrics.csv? Answer with the number only.",
         [Step("peek", f"head -3 {CSV}"),
          Step("broad", f"cut -d, -f4 {CSV}"),
          Step("narrow", f"tail -n +2 {CSV} | cut -d, -f4"),
          Step("answer", "awk -F, 'NR>1{s+=$4} END{print s}' %s" % CSV)],
         lambda r: str(sum(x["requests"] for x in _csv_rows(r)))),

    Task("T08", "csv", "Which region has the highest total errors in data/metrics.csv? Answer with the region name only.",
         [Step("peek", f"head -3 {CSV}"),
          Step("broad", f"tail -n +2 {CSV} | cut -d, -f2,5"),
          Step("tally", "awk -F, 'NR>1{s[$2]+=$5} END{for(k in s) print s[k], k}' %s | sort -k1,1rn -k2,2" % CSV),
          Step("answer", "awk -F, 'NR>1{s[$2]+=$5} END{for(k in s) print s[k], k}' %s | sort -k1,1rn -k2,2 | head -1 | awk '{print $2}'" % CSV)],
         lambda r: _top({reg: sum(x["errors"] for x in _csv_rows(r) if x["region"] == reg)
                         for reg in {x["region"] for x in _csv_rows(r)}})),

    Task("T09", "csv", "How many rows in data/metrics.csv have latency_p95 above 900? Answer with the number only.",
         [Step("peek", f"head -3 {CSV}"),
          Step("broad", f"tail -n +2 {CSV} | cut -d, -f6"),
          Step("narrow", "awk -F, 'NR>1 && $6>900' %s" % CSV),
          Step("answer", "awk -F, 'NR>1 && $6>900' %s | wc -l | tr -d ' '" % CSV)],
         lambda r: str(sum(1 for x in _csv_rows(r) if x["p95"] > 900))),

    Task("T10", "csv", "What is the sum of the errors column for service auth in data/metrics.csv? Answer with the number only.",
         [Step("peek", f"head -3 {CSV}"),
          Step("broad", f"grep ',auth,' {CSV}"),
          Step("narrow", "grep ',auth,' %s | cut -d, -f5" % CSV),
          Step("answer", "awk -F, 'NR>1 && $3==\"auth\"{s+=$5} END{print s}' %s" % CSV)],
         lambda r: str(sum(x["errors"] for x in _csv_rows(r) if x["service"] == "auth"))),

    Task("T11", "csv", "How many distinct regions appear in data/metrics.csv? Answer with the number only.",
         [Step("peek", f"head -3 {CSV}"),
          Step("broad", f"cut -d, -f2 {CSV}"),
          Step("narrow", f"tail -n +2 {CSV} | cut -d, -f2 | sort"),
          Step("answer", "tail -n +2 %s | cut -d, -f2 | sort -u | wc -l | tr -d ' '" % CSV)],
         lambda r: str(len({x["region"] for x in _csv_rows(r)}))),

    Task("T12", "csv", "What is the maximum latency_p95 in data/metrics.csv? Answer with the number only.",
         [Step("peek", f"head -3 {CSV}"),
          Step("broad", f"tail -n +2 {CSV} | cut -d, -f6"),
          Step("narrow", f"tail -n +2 {CSV} | cut -d, -f6 | sort -n"),
          Step("answer", "tail -n +2 %s | cut -d, -f6 | sort -n | tail -1" % CSV)],
         lambda r: str(max(x["p95"] for x in _csv_rows(r)))),

    # --- family: src -------------------------------------------------------
    Task("T13", "src", "How many top-level function definitions are there under src/? Answer with the number only.",
         [Step("orient", "find src -name '*.py' | sort"),
          Step("broad", "grep -rn '^def ' src --include='*.py'"),
          Step("narrow", "grep -rh '^def ' src --include='*.py'"),
          Step("answer", "grep -rh '^def ' src --include='*.py' | wc -l | tr -d ' '")],
         lambda r: str(sum(len(re.findall(r"(?m)^def ", body)) for _, body in _py_files(r)))),

    Task("T14", "src", "How many .py files under src/ contain the string TODO? Answer with the number only.",
         [Step("orient", "find src -name '*.py' | sort"),
          Step("broad", "grep -rn 'TODO' src --include='*.py'"),
          Step("narrow", "grep -rl 'TODO' src --include='*.py' | sort"),
          Step("answer", "grep -rl 'TODO' src --include='*.py' | wc -l | tr -d ' '")],
         lambda r: str(sum(1 for _, body in _py_files(r) if "TODO" in body))),

    Task("T15", "src", "Which .py file under src/ defines the most top-level functions? Answer with the path only, ties broken by the alphabetically first path.",
         [Step("orient", "find src -name '*.py' | sort"),
          Step("broad", "grep -rn '^def ' src --include='*.py'"),
          Step("tally", "grep -rc '^def ' src --include='*.py' | sort -t: -k2,2rn -k1,1"),
          Step("answer", "grep -rc '^def ' src --include='*.py' | sort -t: -k2,2rn -k1,1 | head -1 | cut -d: -f1")],
         lambda r: sorted(((-len(re.findall(r"(?m)^def ", body)), path) for path, body in _py_files(r)))[0][1]),

    Task("T16", "src", "How many top-level class definitions are there under src/? Answer with the number only.",
         [Step("orient", "find src -name '*.py' | sort"),
          Step("broad", "grep -rn '^class ' src --include='*.py'"),
          Step("narrow", "grep -rh '^class ' src --include='*.py'"),
          Step("answer", "grep -rh '^class ' src --include='*.py' | wc -l | tr -d ' '")],
         lambda r: str(sum(len(re.findall(r"(?m)^class ", body)) for _, body in _py_files(r)))),

    Task("T17", "src", "How many lines under src/ start with the word import? Answer with the number only.",
         [Step("orient", "find src -name '*.py' | sort"),
          Step("broad", "grep -rn '^import ' src --include='*.py'"),
          Step("narrow", "grep -rh '^import ' src --include='*.py'"),
          Step("answer", "grep -rh '^import ' src --include='*.py' | wc -l | tr -d ' '")],
         lambda r: str(sum(len(re.findall(r"(?m)^import ", body)) for _, body in _py_files(r)))),

    Task("T18", "src", "How many .py files are there under src/? Answer with the number only.",
         [Step("orient", "ls -R src | head -40"),
          Step("broad", "grep -rn 'def ' src --include='*.py'"),
          Step("narrow", "find src -name '*.py' | sort"),
          Step("answer", "find src -name '*.py' | wc -l | tr -d ' '")],
         lambda r: str(len(_py_files(r)))),
    # --- family: control --------------------------------------------------
    # Genuine null controls: EVERY step prints less than the handle arm's preview
    # envelope, so neither treatment can act and the projected token ratio must come
    # out at or just above 1.00 (just above, because the handle arm carries the
    # larger static prefix and gets nothing back for it).
    #
    # The first draft of this battery labelled T14/T16/T17 the controls because they
    # had no step over the 4,096-byte "bulk" threshold. That was wrong and the dry
    # run showed it: the handle preview binds at 400 tokens ~ 1,600 bytes, so a
    # 2,500-byte step is still elided and those tasks still show a real 5% saving.
    # A control that carries a treatment effect is worse than no control, because it
    # is read as evidence the instrument is clean.
    Task("C01", "control", "What is the header line of data/metrics.csv? Answer with the line only.",
         [Step("peek", f"head -1 {CSV}"),
          Step("answer", f"head -1 {CSV}")],
         lambda r: open(os.path.join(r, CSV)).readline().strip()),

    Task("C02", "control", "How many .py files are in src/core? Answer with the number only.",
         [Step("orient", "ls src"),
          Step("narrow", "ls src/core | head -5"),
          Step("answer", "ls src/core | grep -c '\\.py$'")],
         lambda r: str(sum(1 for p, _ in _py_files(r) if p.startswith("src/core/")))),

    Task("C03", "control", "What is the timestamp on the first line of logs/app.log? Answer with the timestamp only.",
         [Step("peek", f"head -1 {LOG}"),
          Step("answer", "head -1 %s | awk '{print $1}'" % LOG)],
         lambda r: _log_fields(_log_lines(r)[0])["ts"]),
]


def by_id(task_id: str) -> Task:
    for t in TASKS:
        if t.id == task_id:
            return t
    raise KeyError(task_id)


#: The drift sentinel. One fixed, deterministic, cheap task run three times a
#: session under A-inline. It is deliberately NOT one of the 18: a sentinel drawn
#: from the battery would have its own treatment effect mixed into the drift
#: reading it exists to isolate.
SENTINEL = Task(
    "S00", "sentinel", "How many lines are in data/metrics.csv? Answer with the number only.",
    [Step("peek", f"head -3 {CSV}"),
     Step("answer", f"wc -l < {CSV} | tr -d ' '")],
    lambda r: str(len(_csv_rows(r)) + 1),
)
