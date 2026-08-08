"""The human-facing channel, constructed by an entry point and handed downward.

`src/proxy/main.go:359` is the pattern this follows, and the shape is copied
deliberately: `log.New(os.Stderr, "f2a-proxy: ", log.LstdFlags|log.LUTC)` is the
**first statement of `main()`**, there is no package-level logger anywhere in
Go, and the one place the logger reaches non-`main` code is by being handed to
`http.Server.ErrorLog` — the framework's own error sink. All three properties
are held here. `OperatorLog` is a *type*; this module constructs no instance,
and nothing in `src/` imports it except the two entry points.

## What this deliberately is not

Named rather than left to be discovered, because the next reader's first
instinct will be to grow it and the shape was a decision:

- **Not a logging framework.** No levels, no filters, no handlers, no
  formatters, no configuration file, no rotation, no `logging` integration, no
  hierarchy. Two verbs — `say` and `refuse` — and one delivery hook.
- **Not a package-level singleton.** There is no `log = OperatorLog(...)` here
  and there must not be one. A module-level instance is how a library starts
  addressing a human it was not given, which is the thing Go's arrangement
  prevents structurally rather than by convention.
- **Not the machine-readable channel.** That is `src/runtime/trace.py`'s
  `SpanWriter`, it is built, and FR-038's span kind set is **closed** — verified
  2026-08-06 by attempting it, where `lease_renewal`, `supervisor_error` and
  `operator_message` are each refused by `SpanError`. A span requires a tenant,
  a deployment id and a content-addressed artifact version because it exists
  for reproducible attribution. An operator message has none of those and wants
  none of them. Nothing here widens that set and nothing here should.
- **Not a credential sink.** `Secret.__str__` yields the redaction marker
  (FR-036, T035), so interpolating one into a message is structurally safe
  rather than safe by review. That property belongs to `Secret` and is relied
  on here rather than restated.

## Why every write is one unbuffered `os.write`, which is the measured part

A supervisor's lease renewer runs on a **daemon** thread (FR-050 layer 2), so
the channel has to survive being used while the main thread is finalizing the
interpreter. Buffered text streams do not: finalization tears down
`sys.stderr`'s `BufferedWriter` while another thread holds its lock, and CPython
answers `Fatal Python error: _enter_buffered_busy`, SIGABRT, exit 134.

**Measured rather than reasoned about, and both directions were run** —
CPython 3.12.11 on macOS 26.2 arm64, a daemon thread reporting in a tight loop
while the main thread exits 20 ms later, which forces the overlap instead of
sweeping for it:

| vehicle | trials | SIGABRT | clean |
|---|---:|---:|---:|
| `sys.stderr.write` + `flush` | 40 | 38 | 2 |
| `raise` → stock `threading.excepthook` | 40 | 2 | 38 |
| `os.write(2, ...)` | 40 | 0 | 40 |
| stock `threading.excepthook` | 120 | 7 | 113 |
| `adopt_thread_exceptions()` installed | 120 | **0** | 120 |

The stock-excepthook rate reproduces T108's recorded 4-of-87 sweep from the
other side, which is why that record is cited rather than re-derived.

**One residue, disclosed rather than denied.** Neither vehicle delivers
anything at all when the daemon thread has not been scheduled before
finalization completes: swept across the exit instant in 0.5 ms steps, both the
raise path and the `os.write` path are silent in 20 of 20 trials at 0 ms and
clean from 0.5 ms onward. That is a scheduling gap common to both and is not a
difference between them; what differs is that one of the two can also take the
process down.
"""

from __future__ import annotations

import os
import threading
import time
import traceback
from typing import NoReturn

#: What a process exits with when startup refused. One code, because an
#: operator scripting a restart needs *refused* to be one thing; the reason is
#: on the channel, where a human reads it, and not encoded in the status.
EXIT_STARTUP_REFUSED = 1


class OperatorLog:
    """One unbuffered channel to a human, owned by whoever constructed it.

    A message is written as `<UTC timestamp> <name>: <line>` per line, so a
    multi-line report — the configuration one runs to twelve keys and their
    reasons — is greppable line by line rather than only at its head.

    No example is shown here on purpose: `say` writes to a **file descriptor**,
    so a doctest would appear to demonstrate the output while actually
    capturing none of it. `tests/unit/test_operator_log.py` reads the fd.
    """

    __slots__ = ("name", "_fd", "_clock")

    def __init__(self, name: str, *, fd: int = 2,
                 clock=time.time) -> None:
        self.name = name
        self._fd = fd
        self._clock = clock

    def _stamp(self) -> str:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(self._clock()))

    def say(self, message: str) -> None:
        """Emit one message. Safe from any thread, including during shutdown.

        The whole message is framed and written in as few `os.write` calls as
        the kernel accepts, never through a buffered stream.

        **The resumption loop is defensive and is not under removal proof, and
        that is a finding rather than an omission.** An arm was written for it
        and came back UNPROVEN: on a *blocking* descriptor — which fd 2 is, for
        a terminal, a pipe or a file — the kernel does not return short, so a
        single `os.write` delivers an 800 KB report whole and the loop never
        iterates. The loop earns its place on the descriptors where a short
        return is real (a signal arriving mid-transfer, a non-blocking pipe),
        and the honest statement is that this suite cannot produce one. It is
        kept because dropping the returned count silently truncates in exactly
        that case; it is not claimed as proved.

        **Interleaving is the residue.** A message longer than the pipe's
        atomic-write bound may interleave with another thread's. That is
        cosmetic here, where the writers are one entry point and one renewal
        thread, and the alternative — a lock — is the buffered stream's failure
        mode reintroduced by hand.
        """
        prefix = f"{self._stamp()} {self.name}: "
        body = "\n".join(prefix + line for line in message.split("\n"))
        payload = (body + "\n").encode("utf-8", errors="replace")
        while payload:
            payload = payload[os.write(self._fd, payload):]

    def refuse(self, message: str) -> NoReturn:
        """Report and stop. `main()`'s only failure exit.

        The Go anchor is `logger.Fatalf("startup refused: %v", err)` before
        anything is bound. `SystemExit` rather than `os._exit` because the
        entry point may hold a store open and a context manager should close
        it — and unlike Go's `log.Fatalf`, which skips deferred functions, this
        one does not have to.

        **Only sound on the main thread.** `SystemExit` on any other thread
        terminates that thread silently, which is the opposite of this method's
        purpose. Threads call `say`.
        """
        self.say(f"startup refused: {message}")
        raise SystemExit(EXIT_STARTUP_REFUSED)

    def adopt_thread_exceptions(self) -> None:
        """Route uncaught thread exceptions here instead of to buffered stderr.

        This is the analogue of Go's `http.Server{ErrorLog: logger}` and it is
        the same move: the entry point hands its channel to the runtime's own
        error sink rather than to each component in turn. One call covers every
        thread the process will ever start, including ones whose constructor
        this entry point never sees.

        It is also what gives the lease renewer's terminal branch a vehicle.
        `src/supervisor/lease.py` re-raises where retrying cannot help, and the
        table above is the measurement that makes that raise survivable: the
        stock hook aborts the process in 7 of 120 forced-overlap trials and
        this one in 0 of 120. **`lease.py` is not modified and does not import
        this module** — the fix is at the delivery end, which is why one
        installation covers threads nobody enumerated.

        Process-global state, set once by `main()`. That is a deviation from
        *no package-level logger* and it is the narrow kind: the instance is
        still the one `main()` constructed and still owned by it; what is
        global is the interpreter's delivery hook, which is global whether or
        not anyone sets it.
        """
        def hook(args) -> None:
            self.say(_thread_death(args))

        threading.excepthook = hook


def _thread_death(args) -> str:
    """The message a dead thread leaves. Formatted, never printed, so the one
    write in `say` stays one write."""
    name = args.thread.name if args.thread is not None else "<unknown>"
    if args.exc_type is SystemExit:
        return (f"thread {name!r} exited on SystemExit. A thread cannot stop "
                "this process that way; if it meant to, the exit belongs on "
                "the main thread.")
    text = "".join(traceback.format_exception(
        args.exc_type, args.exc_value, args.exc_traceback))
    return f"thread {name!r} died and was not restarted:\n{text.rstrip()}"
