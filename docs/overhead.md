# Syscall-supervisor overhead — T199, Q-09

This is the checkable record, not an essay.
`tests/contract/test_overhead.py` walks this file and the mechanism
descriptions that must not quote a different figure.

T101 measured the syscall supervisor's overhead before the mechanism was
committed. The figure lives in
[`tests/batteries/results/seccomp-overhead.json`](../tests/batteries/results/seccomp-overhead.json).
A CI figure and this figure are different measurements and must not be
compared.

## The measured figure

Recorded `2026-08-03T23:24:21+0000` on kernel `6.12.76-linuxkit`, machine
`aarch64`, CPython 3.12.13, 10 cores, Docker Desktop's linuxkit VM. Median
of 5 repeats per arm. `microseconds_per_notification` is the transferable
figure; the record's own `ratio` is not quoted here.

| arm | µs/notification | overhead_seconds | notifications |
| --- | ---: | ---: | ---: |
| compute_only | 80.65 | 0.009355 | 116 |
| path_heavy | 51.49 | 0.108962 | 2116 |
| shell_heavy | 58.67 | 0.031625 | 539 |

T101 did not measure a percentage. This file quotes none.

## Scope, copied from the record that produced the figure

Quoted from `what_this_is_a_property_of` in that JSON, because the caveats
describe the run, and hand-editing them would make a 2026-08-03 linuxkit
record read as though someone had looked at it since:

- Docker Desktop's linuxkit VM on this host, not a bare Linux host.
  Syscall-interception overhead is the measurement most sensitive to that
  difference and it may not transfer.
- A CPython supervisor doing one ioctl and one `/proc/<pid>/mem` read per
  notification. A Go or C supervisor would be faster by an unmeasured
  amount.
- These three workloads, which are proxies for 'shell-heavy'. T101 asks
  for the measurement on the reference application; the reference
  application does not exist yet, so that part of T101 is OUTSTANDING and
  this does not discharge it.
- `SECCOMP_USER_NOTIF_FLAG_CONTINUE` as the response. A supervisor that
  denied or rewrote arguments would pay more.

The committed record carries no `euid` key. Privilege posture is therefore
unusable by this repository's own labelling standard rather than merely
out of date.

## Residual

The committed record has three proxy arms. T101 also asks for the
measurement on the reference application; that clause is outstanding in
this record. Q-09's prohibitive-or-not ruling is not taken here.
