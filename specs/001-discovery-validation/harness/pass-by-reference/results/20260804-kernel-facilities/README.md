# Kernel facility probe — 2026-08-04

Dry run. No model was called; spend $0.00. These are live syscall probes, not a
reading of `/proc/config.gz` — the config is recorded alongside, but every row below
was produced by attempting the operation and observing what the kernel did.

Host: Docker Desktop 29.4.1 on macOS, guest kernel `6.12.76-linuxkit`, aarch64,
image `python:3.12-slim`, euid 0 inside the container.

## The four readings, one flag at a time

Each JSON carries the exact `docker run` line that produced it in its `invocation`
field, so a reader can re-issue it rather than reconstruct it.

| file | added to a plain `docker run` |
|---|---|
| `probe-docker-default.json` | nothing |
| `probe-docker-cgroupmount-only.json` | `--cgroupns=private -v /sys/fs/cgroup:/sys/fs/cgroup:rw` |
| `probe-docker-seccomp-unconfined-only.json` | `--security-opt seccomp=unconfined` |
| `probe-docker-cgroup-rw.json` | both |

| invocation | Landlock | seccomp user-notif | cgroup v2 delegation | `unshare(CLONE_NEWUSER)` |
|---|---|---|---|---|
| defaults | ENFORCED | ENFORCED | read-only (`EROFS`) | `EPERM` |
| cgroup mount only | ENFORCED | ENFORCED | writable | `EPERM` |
| seccomp unconfined only | ENFORCED | ENFORCED | read-only (`EROFS`) | ok |
| both | ENFORCED | ENFORCED | writable | ok |

Reading of the table: Landlock and seccomp user-notification need **no** added
privilege — no `--privileged`, no `--cap-add`, and they work under Docker's own
default seccomp profile. Writable cgroup delegation needs the cgroup namespace and
mount, and nothing else. `unshare(CLONE_NEWUSER)` is gated by Docker's default seccomp
profile rather than by the kernel, which has `CONFIG_USER_NS=y` and
`max_user_namespaces=31337`.

## Why each row is a measurement and not a configuration read

- **Landlock**: opens `/etc/hostname` *before* applying any ruleset and records the
  result; applies the ruleset; opens again. `ok` then `EACCES` is the reading. If the
  untreated open fails, the probe reports the instrument broken rather than reporting
  enforcement — the negative-control discipline, applied to itself.
- **seccomp user-notification**: installs a BPF filter trapping `getppid`, obtains a
  listener fd, has a child issue the syscall, receives the notification, validates it
  with `SECCOMP_IOCTL_NOTIF_ID_VALID`, and sends a response. All five steps are
  recorded separately so a partial failure cannot read as a success.
- **cgroup v2**: checks the unified mount and controller list, then *attempts to create
  a sub-cgroup*, because delegation is the property that matters and it is not
  visible in the controller list.

## The near-miss worth recording

An earlier revision passed `157` as the `prctl` syscall number, which is correct on
x86-64 and is `setsid` on aarch64. Landlock came back `UNSUPPORTED` on a kernel where
it is enforced. The probe now resolves `libc.prctl` through the dynamic linker, and a
self-test forbids any hardcoded syscall number at that call site. `--selftest` runs
those structural checks on any platform, including macOS, where the probe correctly
declines to report a kernel result at all.

## Scope

One kernel version, one architecture, one container runtime. This establishes the
mechanisms live at 6.12.76 under a known minimum privilege set. It is a single point
and not a floor; what it does and does not say about T205 is set out in the
preregistration.
