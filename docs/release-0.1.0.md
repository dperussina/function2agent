# v0.1.0 — first tagged cut of the spec-aware runtime

**Date: 2026-08-15.** Version `0.1.0` (`pyproject.toml`). This is the first
tagged cut of feature `002-spec-aware-agent-runtime`. It is not 1.0.0.

**Product floor this wrap documents:** `1e40936`. The tag parent is the
commit that added this file.

`tests/contract/test_release_notes.py` walks this file. Dropping the T205
deferral, dropping the untested-status caveat, claiming a vendor package
sits in the lock, or claiming write access is open, fails that test.

## What an operator can run

Linux only, no degraded mode (OD-17). Every other platform is unsupported
rather than best-effort.

```
python -m src.runtime.main
```

Required configuration includes `F2A_RUNTIME_ADDR` (host:port, no invented
default) and the other no-default keys `src.runtime.main` already refuses
on. See [`quickstart.md`](../specs/002-spec-aware-agent-runtime/quickstart.md)
and [`operator-obligations.md`](./operator-obligations.md).

On that path the process can admit a deployment via `check` / `gate`,
construct a `Registry`, bind via `build_server` (T215), and produce a
cassette-shaped Result through `verify_quantity` and `result_join` (T214).

## What they will not get

- **Live vendor `call`.** No vendor SDK is in `requirements.lock`.
  `ProviderDriver.call` raises `TransportUnavailableError` (T058 PARTIAL).
- **Writes.** Writes are blocked (OD-10). v1 is read-only. T181's
  threshold is unset. U-43 remains the exit condition from read-only.
- **A tested 5.14 kernel floor.** The floor is 5.14, DERIVED from documented feature introduction and NOT TESTED on that kernel; every run to date was on 6.12 or 6.17. Wording is not weaker than preflight.
- **Supervisor session lifecycle.** Supervisor still report+exit after
  opening `SessionTable` (OD-36 ⑤). The session workload was not built.
- **SC-013 labels.** The SC-013 window is closed. E13 never ran.

## T205 is deferred, not done

T205 is deferred for this release; the matrix was not built. 5.14 remains
DERIVED and NOT TESTED. Reinstated by an owner decision to measure, and
by nothing else. Ticking T205 would claim the matrix ran.

## Pointers

- Operator path: [`specs/002-spec-aware-agent-runtime/quickstart.md`](../specs/002-spec-aware-agent-runtime/quickstart.md)
- Obligations: [`operator-obligations.md`](./operator-obligations.md)
- Unvalidated values and the kernel floor: `src/runtime/reports/unvalidated.py`
- Claims audit: [`claims-audit.md`](./claims-audit.md)
- Support audit: [`support-audit.md`](./support-audit.md)
