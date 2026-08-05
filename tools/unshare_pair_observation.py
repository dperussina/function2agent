#!/usr/bin/env python3
"""Run the preflight's namespace checks under a *stated* privilege posture.

    python3 tools/unshare_pair_observation.py --label LABEL --out RECORD.json
    python3 tools/unshare_pair_observation.py --render a.json b.json

WHAT THIS IS FOR, AND WHY IT IS NOT A GATE

`specs/002-spec-aware-agent-runtime/findings/025-preflight-unshare-pair-measured.md`
leaves one cell of `_classify_unshare_pair` **derived rather than measured**:
`kernel-sysctl-or-lsm`, the cell that fires on Ubuntu 24.04 — the likeliest
self-hosted host. It could not be constructed on the measuring host because
Docker Desktop's linuxkit VM carries neither AppArmor nor SELinux, and finding
024 recorded the same gap before it. It is the most consequential refusal the
classifier can report and the one nobody here can produce.

The observation that makes an attempt cheap: **the CI runner is Ubuntu 24.04**,
which ships `kernel.apparmor_restrict_unprivileged_userns` enabled, and the
existing preflight step runs under `sudo` — **root is exempt from that
restriction**, which is why CI has never produced the cell. Running the same
checks *unprivileged* on the same runner may produce it at no hardware cost.

**The result is an observation about the runner, not a property of our code**,
so nothing here fails a build. What it must not do is pass silently when it did
not run: this repository has already lost a measurement to a log line — the
Linux-native seccomp-overhead figure was produced on every run, gitignored, and
swallowed by `pytest -q`. So the record is JSON on disk, rendered to the run
page and uploaded as an artifact, and `--render` **exits non-zero when a record
is missing**, because the file is absent in exactly the case the step exists to
make visible.

THE PREDICTION, AND WHAT THIS WOULD ACCEPT INSTEAD

Predicted: the unprivileged arm reports `kernel-sysctl-or-lsm`. That prediction
is **derived** — from Ubuntu 24.04's documented default and from no observation
of this runner at all. If the arm reports anything else, **that is the result**.
Do not adjust this file until it agrees with the prediction; an experiment whose
only acceptable outcome is the predicted one measures nothing.

THE PAIRED ARM IS THE CONTROL, AND IT IS THE POINT OF RUNNING BOTH

The positive result here is a **refusal**, and Rule 8 of the `experiment-design`
skill is that an experiment whose positive result is a failure signal needs a
negative control — every way this script can itself be broken (a bad import, a
`fork` that fails, a probe that always reports refused) also produces a refusal.
So the *same script* is run twice on the *same VM*, once unprivileged and once
under `sudo`, differing in privilege and nothing else. A privileged arm
reporting `available` is what licenses reading the unprivileged arm's refusal as
being about privilege.

THE POSTURE IS READ, NEVER ASSERTED FROM THE INVOCATION

`--label unprivileged` is a name, not evidence. Every record carries `Uid`,
`CapEff`, `CapBnd` and the seccomp mode read out of `/proc/self/status` in the
process that took the measurement. Finding 024's probe inferred a posture
instead of reading one, wrote a uid map naming a uid it did not own, and every
later `ok` in that sequence was meaningless.

Standard library only, like the rest of `tools/`. It does import
`src.supervisor.preflight`, and that is deliberate: the point is to run **our
committed checks**, not a re-implementation of them that could agree with the
prediction for reasons of its own.
"""

from __future__ import annotations

import json
import os
import platform
import sys
import traceback
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

#: The cell finding 025 could not construct. Written down before the run, in
#: the file the run reads, so that "we expected this" is checkable rather than
#: remembered.
PREDICTED_LAYER = "kernel-sysctl-or-lsm"

#: Read and recorded whatever their values. The first is Ubuntu 24.04's
#: AppArmor switch and the reason this experiment exists; the rest are the
#: other knobs finding 024 named as candidate refusers, kept so that a
#: surprising layer has its context recorded beside it rather than needing a
#: second run.
_SYSCTLS = (
    "/proc/sys/kernel/apparmor_restrict_unprivileged_userns",
    "/proc/sys/user/max_user_namespaces",
    "/proc/sys/kernel/unprivileged_userns_clone",
)

_LSM_PATHS = (
    "/sys/kernel/security/lsm",
    "/sys/module/apparmor/parameters/enabled",
)

_STATUS_FIELDS = (
    "Uid", "Gid", "CapEff", "CapBnd", "CapPrm",
    "Seccomp", "Seccomp_filters", "NoNewPrivs",
)


def _read(path: str) -> str | None:
    try:
        return Path(path).read_text().strip()
    except OSError:
        return None


def _posture() -> dict:
    """The privilege posture, read from `/proc/self/status` in this process."""
    out: dict[str, str | None] = {f: None for f in _STATUS_FIELDS}
    text = _read("/proc/self/status")
    if text is None:
        return out
    for line in text.splitlines():
        key, _, value = line.partition(":")
        if key in out:
            out[key] = value.strip()
    return out


def observe(label: str) -> dict:
    """One arm: posture, host knobs, and our two committed checks."""
    from src.supervisor import preflight

    record: dict = {
        "label": label,
        "produced": True,
        "what_this_is": (
            "an observation about the runner this ran on, not a property of "
            "this repository's code. It gates nothing."
        ),
        "predicted_namespaces_layer": PREDICTED_LAYER,
        "prediction_basis": (
            "DERIVED from Ubuntu 24.04's documented default for "
            "kernel.apparmor_restrict_unprivileged_userns, and from no "
            "observation of this runner. Any other layer is the result, not a "
            "reason to change the step."
        ),
        "host": {
            "kernel": platform.release(),
            "machine": platform.machine(),
            "platform": platform.platform(),
            "python": platform.python_version(),
            "os_release": _read("/etc/os-release"),
        },
        # Read, never inferred from the invocation. `--label unprivileged` is
        # a name; these are the evidence that it was one.
        "posture_read_in_this_process": _posture(),
        "euid": os.geteuid(),
        "uid": os.getuid(),
        "sysctls": {p: _read(p) for p in _SYSCTLS},
        "lsm": {p: _read(p) for p in _LSM_PATHS},
    }

    for name, fn in (("namespaces", preflight._check_namespaces),
                     ("pivot_root", preflight._check_pivot_root)):
        check = fn()
        record[name] = {
            "ok": check.ok,
            "layer": check.layer,
            "requirement": check.requirement,
            "detail": check.detail,
        }
    return record


def _write(path: Path, record: dict) -> None:
    path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")


def take(label: str, out: Path) -> int:
    try:
        record = observe(label)
    except BaseException:  # noqa: BLE001 - the traceback is the record
        # A record is still written. An absent file must mean "the step did not
        # run", so a step that ran and failed has to leave something behind or
        # the two states become indistinguishable at the point of reading.
        _write(out, {
            "label": label,
            "produced": False,
            "error": traceback.format_exc(),
            "what_this_is": (
                "this arm ran and could not complete. The absence of a layer "
                "below is a fault in the instrument, not an observation about "
                "the host."
            ),
        })
        print(f"{label}: FAILED to complete; record written to {out}",
              file=sys.stderr)
        return 1
    _write(out, record)
    print(
        "{}: euid={} CapEff={} seccomp_mode={} namespaces={} pivot_root={}"
        .format(label, record["euid"],
                record["posture_read_in_this_process"]["CapEff"],
                record["posture_read_in_this_process"]["Seccomp"],
                record["namespaces"]["layer"], record["pivot_root"]["layer"])
    )
    return 0


def _load(path: str) -> tuple[str, dict | None, str]:
    try:
        return path, json.loads(Path(path).read_text()), ""
    except (OSError, ValueError) as exc:
        return path, None, str(exc)


def render(paths: list[str]) -> int:
    """The run-page block. Non-zero only when a record is missing."""
    print("## The `unshare` pair and `pivot_root`, by privilege posture\n")
    print(
        "A **non-gating observation about this runner.** Finding 025 leaves "
        "the `{}` cell derived and could not construct it — Docker Desktop's "
        "linuxkit VM carries no LSM. This runner is Ubuntu 24.04, which ships "
        "`kernel.apparmor_restrict_unprivileged_userns` enabled, and the "
        "preflight step above runs under `sudo`, where root is exempt. The "
        "unprivileged arm below is the attempt to produce that cell.\n"
        .format(PREDICTED_LAYER)
    )

    loaded = [_load(p) for p in paths]
    missing = [(p, exc) for p, rec, exc in loaded if rec is None]
    if missing:
        print("### NO RECORD — THE OBSERVATION DID NOT HAPPEN\n")
        for path, exc in missing:
            print(f"- no readable record at `{path}` ({exc})")
        print(
            "\nThe record is written by the step itself, including when the "
            "arm fails, so an absent file means the step did not run at all. "
            "That is the state this block exists to make visible; a silent "
            "pass here is how this repository lost the native "
            "seccomp-overhead figure.\n"
        )

    records = [rec for _, rec, _ in loaded if rec is not None]
    if records:
        print("| arm | euid | `CapEff` | seccomp mode | `namespaces` layer | "
              "`pivot_root` layer |")
        print("|---|---:|---|---:|---|---|")
        for r in records:
            if not r.get("produced", False):
                print("| {} | — | — | — | **ARM FAILED** | **ARM FAILED** |"
                      .format(r.get("label", "?")))
                continue
            p = r["posture_read_in_this_process"]
            print("| {} | {} | `{}` | {} | `{}` | `{}` |".format(
                r["label"], r["euid"], p["CapEff"], p["Seccomp"],
                r["namespaces"]["layer"], r["pivot_root"]["layer"]))
        print()
        print(
            "Posture columns are read from `/proc/self/status` inside each "
            "arm, not asserted from the `sudo` on the command line.\n"
        )

    produced = [r for r in records if r.get("produced")]
    unpriv = [r for r in produced if r["euid"] != 0]
    priv = [r for r in produced if r["euid"] == 0]

    for r in produced:
        knob = r["sysctls"].get(
            "/proc/sys/kernel/apparmor_restrict_unprivileged_userns")
        print("- **{}** — `apparmor_restrict_unprivileged_userns` = `{}`, "
              "`max_user_namespaces` = `{}`, LSM = `{}`".format(
                  r["label"], knob,
                  r["sysctls"].get("/proc/sys/user/max_user_namespaces"),
                  r["lsm"].get("/sys/kernel/security/lsm")))
    print()

    if unpriv:
        seen = unpriv[0]["namespaces"]["layer"]
        hit = seen == PREDICTED_LAYER
        print("### The reading\n")
        print("Predicted for the unprivileged arm: `{}`. Observed: `{}` — "
              "**{}**.\n".format(
                  PREDICTED_LAYER, seen,
                  "the derived cell was constructed" if hit
                  else "the prediction did not hold, and that is the result"))
        if not hit:
            print(
                "> The prediction was derived from Ubuntu 24.04's documented "
                "default and from no observation of this runner. It is "
                "recorded as it came out. **Do not tune this step until it "
                "agrees** — an experiment whose only acceptable outcome is "
                "the predicted one measures nothing.\n"
            )
        if priv:
            print(
                "The privileged arm is the negative control: it reports "
                "`{}`, on the same VM, differing in privilege and nothing "
                "else. Without it, a refusal above would be indistinguishable "
                "from this script being broken.\n"
                .format(priv[0]["namespaces"]["layer"])
            )
        else:
            print(
                "> **No privileged arm in this run.** The unprivileged "
                "reading has no control beside it, so a refusal cannot be "
                "separated from a broken instrument.\n"
            )
    print(
        "> These readings are a property of the runner named in the identity "
        "block above. They are not a claim about any other host, and nothing "
        "here gates a merge.\n"
    )
    return 1 if missing else 0


def main(argv: list[str]) -> int:
    args = list(argv[1:])
    if args and args[0] == "--render":
        if len(args) < 2:
            print("--render needs at least one record path", file=sys.stderr)
            return 2
        return render(args[1:])
    label, out = None, None
    while args:
        arg = args.pop(0)
        if arg == "--label" and args:
            label = args.pop(0)
        elif arg == "--out" and args:
            out = args.pop(0)
        else:
            print(f"unrecognised argument {arg!r}", file=sys.stderr)
            return 2
    if not label or not out:
        print("usage: unshare_pair_observation.py --label L --out RECORD.json",
              file=sys.stderr)
        print("       unshare_pair_observation.py --render RECORD.json ...",
              file=sys.stderr)
        return 2
    return take(label, Path(out))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
