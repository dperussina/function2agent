#!/usr/bin/env python3
"""A wall-clock cap for one removal-proof arm, and a distinct exit code for it.

    python3 tools/proof_timeout.py SECONDS COMMAND [ARG...]

Exits with the command's own status, or `124` if the cap was reached first.
Whatever the command printed before it was killed goes to stdout either way, so
the arm that hung is diagnosable from the harness's own output.

WHY THIS EXISTS

`proof()` in `tests/removal_proofs.sh` reads a **non-zero exit** as the tampered
test noticing the mechanism was removed. That reading is correct for a test that
ran and failed and wrong for every other way a process can end non-zero, and two
arms have now found the difference:

  - `FR-048 watch-set guard` installs a USER_NOTIF seccomp filter on the pytest
    process itself once its guard is tampered away, and blocks forever in
    `seccomp_do_user_notification` with nobody holding the descriptor. Recorded
    as a known hazard beside that arm.
  - `T065 wiring` disarms the loop's only backstop while the arm's own ceilings
    are all deliberately out of reach, leaving a runaway loop with no terminator
    of any kind. Measured 2026-08-05 at `1208e06`: no return in 90s, and a
    concurrent pass recorded 56 minutes of continuous CPU.

Two instances is a class. The second one also demonstrated the failure the cap
is really for: a hang does not stay a hang. Somebody eventually kills the
pytest child, bash's command substitution returns 130, `proof()` sees non-zero
and prints **proved** — and the run completes, green, with an arm that never
demonstrated anything. `removal-proofs-20260805T215946-4479acefc95f.json`
records exactly that shape.

WHY A SEPARATE PROCESS GROUP

`start_new_session=True` puts the command in its own process group so the cap
can kill the group rather than the one process. A tampered arm can leave
children behind — `tests/unit/test_supervisor_lease.py` spawns interpreters that
outlive a killed parent, and three such orphans were found still running after
thirteen days on the machine this was written on. Killing only the direct child
leaves those attached to the harness's own terminal and burning CPU behind an
arm that has already been scored.

WHY 124 AND NOT A FILE OR A MARKER LINE

124 is what GNU `timeout(1)` uses, so the number is already familiar, and macOS
ships no `timeout(1)` at all — hence a script rather than a dependency on one.
It is unambiguous for the two commands the harness runs under this cap: `pytest`
exits 0-5 and `go test` exits 0, 1 or 2. A marker line in the output would not
be, because the output belongs to the tampered test and the tampered test can
print anything.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys

TIMED_OUT = 124


def _shell_status(returncode: int) -> int:
    """A child's status the way a shell reports it.

    `Popen.returncode` is **negative** for a signalled child, and `sys.exit(-15)`
    leaves a shell reading 241 — which is above 128 and so still lands in the
    harness's signalled branch, but makes it print `signal 113`. Converting here
    keeps the number in that message the signal that was actually delivered.
    """
    return 128 - returncode if returncode < 0 else returncode


def run(seconds: float, argv: list[str]) -> int:
    proc = subprocess.Popen(
        argv,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        errors="replace",
        start_new_session=True,
    )
    try:
        out, _ = proc.communicate(timeout=seconds)
        sys.stdout.write(out)
        return _shell_status(proc.returncode)
    except subprocess.TimeoutExpired:
        pass

    # The group, not the process. See the module docstring.
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        proc.kill()
    try:
        out, _ = proc.communicate(timeout=30)
    except subprocess.TimeoutExpired:  # pragma: no cover - the kill did not take
        out = ""
    sys.stdout.write(out or "")
    # On stdout rather than stderr: `proof()` captures the two together and this
    # sentence is the only description of what happened that survives.
    sys.stdout.write(
        "\n[proof_timeout] killed after {:g}s: the command did not return. This "
        "is not a demonstrated failure and must not be scored as one.\n".format(
            seconds
        )
    )
    return TIMED_OUT


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print(__doc__.strip().splitlines()[0], file=sys.stderr)
        print(
            "usage: proof_timeout.py SECONDS COMMAND [ARG...]", file=sys.stderr
        )
        return 2
    try:
        seconds = float(argv[1])
    except ValueError:
        print("proof_timeout.py: {!r} is not a number of seconds".format(argv[1]),
              file=sys.stderr)
        return 2
    return run(seconds, argv[2:])


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
