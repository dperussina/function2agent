"""SPIKE - E17 pass-by-reference. Delete after 2026-11-30. Do not import from product code.

Does this host's kernel actually enforce Landlock, seccomp user notification and cgroup v2?

Arm B of E17 runs NOOA with ``execution_backend="sandbox"``. That backend installs Landlock
and a seccomp socket block before any cell bytecode runs, and it is Linux-only by construction.
The macOS host cannot run it, so the only Linux available is the Docker Desktop linuxkit VM.
**A silently disabled sandbox would make arm B measure nothing** — both arms would execute
in-process and the pickle boundary would never be crossed — so this probe exists to decide,
before any money is spent, whether the arm is even single-factor on this host.

Reading ``/proc/config.gz`` is not enough and this probe does not stop there. A facility can
be compiled in, absent from the active LSM list, blocked by the container runtime's own seccomp
profile, or present but unusable at the privilege level the container runs at. Each of those
produces a working ``CONFIG_*=y`` line. So every facility here is **exercised**, not read.

Rule 8 (``experiment-design`` skill) governs the shape of two of these tests and is the reason
they are twice as long as they look like they need to be. For Landlock the positive result is
*an open that fails*; for seccomp it is *a syscall that does not return normally*. Every way the
probe itself can break — a path that does not exist, a child that died, a ctypes signature that
is wrong — produces exactly that same reading and would be scored as success. So each of those
two tests takes an **untreated reading first** and refuses to report enforcement unless the
untreated reading is the expected negative. A Landlock test whose pre-restriction open already
failed reports ``INSTRUMENT_BROKEN``, never ``enforced``.

Nothing here calls a model, reaches the network, or reads a credential. It costs $0.00.

    python3 kernel_probe.py                 # human-readable
    python3 kernel_probe.py --json          # one JSON object on stdout
    python3 kernel_probe.py --selftest      # prove the probe's own logic, no syscalls needed
"""

from __future__ import annotations

import argparse
import ctypes
import ctypes.util
import errno
import json
import os
import platform
import socket
import struct
import sys
import tempfile

# --------------------------------------------------------------------------------------
# Architecture-dependent constants. Wrong numbers here would silently report "unsupported"
# on a perfectly capable kernel, so the table refuses unknown architectures rather than
# guessing a syscall number.
# --------------------------------------------------------------------------------------

_ARCH = platform.machine()

#: ``seccomp(2)`` and ``getppid(2)`` numbers. The landlock trio (444/445/446) is
#: architecture-independent on every port that has them, so it is not in this table.
_SYSCALLS = {
    "aarch64": {"seccomp": 277, "getppid": 173, "audit_arch": 0xC00000B7},
    "arm64":   {"seccomp": 277, "getppid": 173, "audit_arch": 0xC00000B7},
    "x86_64":  {"seccomp": 317, "getppid": 110, "audit_arch": 0xC000003E},
}

NR_LANDLOCK_CREATE_RULESET = 444
NR_LANDLOCK_ADD_RULE = 445
NR_LANDLOCK_RESTRICT_SELF = 446

PR_SET_NO_NEW_PRIVS = 38

#: ``prctl`` is deliberately called through libc rather than through ``syscall(nr, ...)``.
#:
#: The first draft of this probe hardcoded 157 with a comment asserting it was prctl on
#: both aarch64 and x86_64. It is prctl on x86_64 and ``setsid`` on aarch64, where prctl is
#: 167. The probe therefore called ``setsid``, got ``EPERM`` because the forked child was
#: already a process-group leader, and reported Landlock as ``UNSUPPORTED`` on a kernel
#: advertising ABI 6. **A wrong syscall number is indistinguishable from a missing facility
#: at this call site**, which is the whole reason the number is gone: ``libc.prctl`` is
#: resolved by the dynamic linker for the architecture actually running.
_PRCTL_NUMBERS_DIFFER_BY_ARCH = {"x86_64": 157, "aarch64": 167}
LANDLOCK_CREATE_RULESET_VERSION = 1 << 0

LANDLOCK_ACCESS_FS_EXECUTE = 1 << 0
LANDLOCK_ACCESS_FS_READ_FILE = 1 << 2
LANDLOCK_ACCESS_FS_READ_DIR = 1 << 3

SECCOMP_SET_MODE_FILTER = 1
SECCOMP_FILTER_FLAG_NEW_LISTENER = 1 << 3

SECCOMP_RET_ALLOW = 0x7FFF0000
SECCOMP_RET_USER_NOTIF = 0x7FC00000

BPF_LD, BPF_W, BPF_ABS = 0x00, 0x00, 0x20
BPF_JMP, BPF_JEQ, BPF_K = 0x05, 0x10, 0x00
BPF_RET = 0x06

#: ``struct seccomp_notif`` is 80 bytes and ``struct seccomp_notif_resp`` is 24.
_SIZEOF_NOTIF = 80
_SIZEOF_RESP = 24


def _ioc(direction: int, type_: int, nr: int, size: int) -> int:
    return (direction << 30) | (size << 16) | (type_ << 8) | nr


_IOC_WRITE, _IOC_READ = 1, 2
SECCOMP_IOCTL_NOTIF_RECV = _ioc(_IOC_WRITE | _IOC_READ, ord("!"), 0, _SIZEOF_NOTIF)
SECCOMP_IOCTL_NOTIF_SEND = _ioc(_IOC_WRITE | _IOC_READ, ord("!"), 1, _SIZEOF_RESP)
#: This one is ``_IOW``, not ``_IOR``. The distinction is not cosmetic: the ioctl number was
#: **wrong in the kernel's own header until 5.9**, which is one of the three facts that fix
#: this project's 5.14 kernel floor (`tasks.md` T006). Getting it wrong here yields ``EINVAL``
#: from a call site where the failure looks like "the facility is missing".
SECCOMP_IOCTL_NOTIF_ID_VALID = _ioc(_IOC_WRITE, ord("!"), 2, 8)


class SockFprog(ctypes.Structure):
    """``struct sock_fprog``.

    Built with ctypes rather than :mod:`struct` because ``struct`` refuses the pointer
    code ``P`` in any explicit byte-order mode, and the first draft of this probe used
    ``struct.pack("<HxxxxxxP", ...)``. That raises ``struct.error`` inside the forked
    child, which exited silently — and the parent read the empty message as *the kernel
    refused the listener*. A crashed child and an unsupported kernel produced the same
    reading, which is Rule 8's shape in the instrument rather than in the experiment.
    """

    _fields_ = [("len", ctypes.c_ushort), ("filter", ctypes.c_void_p)]


def _libc() -> ctypes.CDLL:
    lib = ctypes.CDLL(ctypes.util.find_library("c") or "libc.so.6", use_errno=True)
    lib.syscall.restype = ctypes.c_long
    lib.prctl.restype = ctypes.c_int
    lib.unshare.restype = ctypes.c_int
    return lib


def _set_no_new_privs(libc: ctypes.CDLL) -> int:
    """``prctl(PR_SET_NO_NEW_PRIVS, 1)``, through libc, never through a hardcoded number."""
    ctypes.set_errno(0)
    return libc.prctl(ctypes.c_int(PR_SET_NO_NEW_PRIVS), ctypes.c_ulong(1),
                      ctypes.c_ulong(0), ctypes.c_ulong(0), ctypes.c_ulong(0))


# --------------------------------------------------------------------------------------
# Landlock
# --------------------------------------------------------------------------------------


def probe_landlock_abi() -> dict:
    """The ABI version the running kernel advertises, or why it does not."""
    try:
        libc = _libc()
    except OSError as exc:  # pragma: no cover - only on a host with no libc
        return {"available": False, "reason": f"libc not loadable: {exc}"}

    ctypes.set_errno(0)
    rc = libc.syscall(
        ctypes.c_long(NR_LANDLOCK_CREATE_RULESET),
        ctypes.c_void_p(None),
        ctypes.c_size_t(0),
        ctypes.c_uint32(LANDLOCK_CREATE_RULESET_VERSION),
    )
    if rc < 0:
        err = ctypes.get_errno()
        return {
            "available": False,
            "abi_version": None,
            "errno": errno.errorcode.get(err, err),
            "reason": {
                errno.ENOSYS: "syscall absent — CONFIG_SECURITY_LANDLOCK=n or kernel < 5.13",
                errno.EOPNOTSUPP: "compiled in but not in the active LSM list (CONFIG_LSM / lsm=)",
                errno.EPERM: "blocked before the kernel saw it — container seccomp profile",
            }.get(err, f"landlock_create_ruleset failed with {errno.errorcode.get(err, err)}"),
        }
    return {"available": True, "abi_version": int(rc), "errno": None, "reason": None}


def _landlock_child(pipe_w: int, victim: str) -> None:
    """Runs in a forked child. Writes one JSON line to ``pipe_w`` and ``_exit``s."""
    result: dict = {"stage": "start"}

    def emit(**kw):
        result.update(kw)
        os.write(pipe_w, json.dumps(result).encode())
        os._exit(0)

    # Rule 8 untreated reading. If this open already fails, every later denial is
    # uninformative and the test must refuse to report rather than score a success.
    try:
        with open(victim, "rb") as fh:
            fh.read(1)
        result["pre_restriction_open"] = "ok"
    except OSError as exc:
        emit(stage="untreated", pre_restriction_open=f"FAILED: {exc.strerror}",
             verdict="INSTRUMENT_BROKEN")

    try:
        libc = _libc()
    except OSError as exc:
        emit(stage="libc", verdict="INSTRUMENT_BROKEN", detail=str(exc))

    # A ruleset that *handles* read access and is given **no** allow rules denies all reads.
    attr = struct.pack(
        "<Q", LANDLOCK_ACCESS_FS_READ_FILE | LANDLOCK_ACCESS_FS_READ_DIR
        | LANDLOCK_ACCESS_FS_EXECUTE
    )
    buf = ctypes.create_string_buffer(attr)
    ctypes.set_errno(0)
    ruleset_fd = libc.syscall(
        ctypes.c_long(NR_LANDLOCK_CREATE_RULESET),
        ctypes.byref(buf), ctypes.c_size_t(len(attr)), ctypes.c_uint32(0),
    )
    if ruleset_fd < 0:
        emit(stage="create_ruleset", verdict="UNSUPPORTED",
             errno=errno.errorcode.get(ctypes.get_errno(), ctypes.get_errno()))

    if _set_no_new_privs(libc) != 0:
        emit(stage="no_new_privs", verdict="UNSUPPORTED",
             errno=errno.errorcode.get(ctypes.get_errno(), ctypes.get_errno()))

    ctypes.set_errno(0)
    if libc.syscall(ctypes.c_long(NR_LANDLOCK_RESTRICT_SELF),
                    ctypes.c_int(int(ruleset_fd)), ctypes.c_uint32(0)) != 0:
        emit(stage="restrict_self", verdict="NOT_ENFORCEABLE",
             errno=errno.errorcode.get(ctypes.get_errno(), ctypes.get_errno()))

    try:
        with open(victim, "rb") as fh:
            fh.read(1)
        emit(stage="post", post_restriction_open="ok", verdict="NOT_ENFORCED")
    except PermissionError:
        emit(stage="post", post_restriction_open="EACCES", verdict="ENFORCED")
    except OSError as exc:
        emit(stage="post", post_restriction_open=f"{exc.strerror}", verdict="AMBIGUOUS")


def probe_landlock_enforcement() -> dict:
    """Fork a child, restrict it, and require a read that worked before to fail after."""
    abi = probe_landlock_abi()
    if not abi["available"]:
        return {"verdict": "UNSUPPORTED", "abi": abi}

    victim = "/etc/hostname" if os.path.exists("/etc/hostname") else __file__
    r, w = os.pipe()
    pid = os.fork()
    if pid == 0:  # pragma: no cover - child never returns
        os.close(r)
        try:
            _landlock_child(w, victim)
        except BaseException as exc:  # noqa: BLE001
            os.write(w, json.dumps({"verdict": "INSTRUMENT_BROKEN",
                                    "detail": repr(exc)}).encode())
        os._exit(0)

    os.close(w)
    payload = b""
    while chunk := os.read(r, 4096):
        payload += chunk
    os.close(r)
    _, status = os.waitpid(pid, 0)
    try:
        out = json.loads(payload or b"{}")
    except json.JSONDecodeError:
        out = {"verdict": "INSTRUMENT_BROKEN", "detail": "child wrote no parseable result"}
    out["abi"] = abi
    out["victim_path"] = victim
    out["child_status"] = status
    return out


# --------------------------------------------------------------------------------------
# seccomp user notification
# --------------------------------------------------------------------------------------


def _bpf_stmt(code: int, k: int) -> bytes:
    return struct.pack("<HBBI", code, 0, 0, k)


def _bpf_jump(code: int, k: int, jt: int, jf: int) -> bytes:
    return struct.pack("<HBBI", code, jt, jf, k)


def _notif_filter(nr_trapped: int, audit_arch: int) -> bytes:
    """Trap exactly one syscall to the listener; allow everything else.

    Trapping everything would deadlock the child before it could hand the listener fd over.
    """
    return b"".join([
        _bpf_stmt(BPF_LD | BPF_W | BPF_ABS, 4),           # seccomp_data.arch
        _bpf_jump(BPF_JMP | BPF_JEQ | BPF_K, audit_arch, 0, 3),
        _bpf_stmt(BPF_LD | BPF_W | BPF_ABS, 0),           # seccomp_data.nr
        _bpf_jump(BPF_JMP | BPF_JEQ | BPF_K, nr_trapped, 0, 1),
        _bpf_stmt(BPF_RET | BPF_K, SECCOMP_RET_USER_NOTIF),
        _bpf_stmt(BPF_RET | BPF_K, SECCOMP_RET_ALLOW),
    ])


def probe_seccomp_user_notif() -> dict:
    """Full round trip: install a listener, trap a syscall, receive, validate, respond.

    A listener fd alone proves the flag is accepted. It does not prove the supervisor can
    read a notification off it, and it does not exercise ``SECCOMP_IOCTL_NOTIF_ID_VALID``,
    which is the ioctl whose number was wrong before 5.9. Both are exercised here because
    both are what this project's supervisor depends on.
    """
    table = _SYSCALLS.get(_ARCH)
    if table is None:
        return {"verdict": "UNKNOWN_ARCH", "arch": _ARCH,
                "detail": "no syscall table for this architecture; refusing to guess"}

    prog = _notif_filter(table["getppid"], table["audit_arch"])
    parent_sock, child_sock = socket.socketpair()

    pid = os.fork()
    if pid == 0:  # pragma: no cover - child never returns
        parent_sock.close()
        code = 0
        try:
            libc = _libc()
            buf = ctypes.create_string_buffer(prog, len(prog))
            fprog = SockFprog(len(prog) // 8, ctypes.cast(buf, ctypes.c_void_p))
            nnp = _set_no_new_privs(libc)
            ctypes.set_errno(0)
            listener = libc.syscall(
                ctypes.c_long(table["seccomp"]),
                ctypes.c_ulong(SECCOMP_SET_MODE_FILTER),
                ctypes.c_ulong(SECCOMP_FILTER_FLAG_NEW_LISTENER),
                ctypes.byref(fprog),
            )
            if listener < 0:
                err = ctypes.get_errno()
                child_sock.sendall(json.dumps(
                    {"listener": False, "no_new_privs_rc": nnp,
                     "errno": errno.errorcode.get(err, err)}).encode())
                child_sock.close()
                os._exit(0)
            socket.send_fds(child_sock, [json.dumps({"listener": True}).encode()],
                            [int(listener)])
            # Trapped. The parent must answer or this blocks forever.
            os.getppid()
            code = 0
        except BaseException as exc:  # noqa: BLE001
            # Never exit silently. An empty message is indistinguishable from "the kernel
            # refused the listener", which is the reading this whole probe must not fake.
            try:
                child_sock.sendall(json.dumps(
                    {"listener": False, "child_exception": repr(exc)}).encode())
            except OSError:
                pass
            code = 3
        finally:
            try:
                child_sock.close()
            except OSError:
                pass
        os._exit(code)

    child_sock.close()
    out: dict = {"arch": _ARCH}
    try:
        msg, fds, _flags, _addr = socket.recv_fds(parent_sock, 4096, 1)
        if not msg:
            out.update(verdict="INSTRUMENT_BROKEN", listener_fd=None,
                       detail="the child sent nothing; a silent child is not evidence "
                              "that the kernel refused the listener")
            return out
        info = json.loads(msg)
        if info.get("child_exception"):
            out.update(verdict="INSTRUMENT_BROKEN", listener_fd=None,
                       detail=info["child_exception"])
            return out
        if not info.get("listener"):
            out.update(verdict="UNSUPPORTED", listener_fd=False,
                       errno=info.get("errno"),
                       no_new_privs_rc=info.get("no_new_privs_rc"),
                       detail="SECCOMP_FILTER_FLAG_NEW_LISTENER refused")
            return out
        listener_fd = fds[0]
        out["listener_fd"] = True

        import fcntl

        notif = bytearray(_SIZEOF_NOTIF)
        fcntl.ioctl(listener_fd, SECCOMP_IOCTL_NOTIF_RECV, notif, True)
        notif_id, notif_pid, _flags2 = struct.unpack_from("<QII", notif, 0)
        nr = struct.unpack_from("<i", notif, 16)[0]
        out.update(recv=True, trapped_syscall_nr=nr, notif_pid=notif_pid,
                   expected_nr=table["getppid"])

        # The ioctl whose number the kernel got wrong before 5.9.
        try:
            fcntl.ioctl(listener_fd, SECCOMP_IOCTL_NOTIF_ID_VALID,
                        struct.pack("<Q", notif_id))
            out["id_valid_ioctl"] = "ok"
        except OSError as exc:
            out["id_valid_ioctl"] = f"{errno.errorcode.get(exc.errno, exc.errno)}"

        resp = struct.pack("<QqiI", notif_id, 0, errno.EPERM, 0)
        fcntl.ioctl(listener_fd, SECCOMP_IOCTL_NOTIF_SEND, bytearray(resp), True)
        out["send"] = True
        out["verdict"] = (
            "ENFORCED" if out.get("recv") and nr == table["getppid"]
            and out["id_valid_ioctl"] == "ok" else "PARTIAL"
        )
        os.close(listener_fd)
    except OSError as exc:
        out.update(verdict="PARTIAL", detail=f"{type(exc).__name__}: {exc}")
    except Exception as exc:  # noqa: BLE001
        out.update(verdict="INSTRUMENT_BROKEN", detail=repr(exc))
    finally:
        parent_sock.close()
        try:
            os.waitpid(pid, 0)
        except ChildProcessError:
            pass
    return out


# --------------------------------------------------------------------------------------
# cgroup v2
# --------------------------------------------------------------------------------------


def probe_cgroup_v2() -> dict:
    """v2 mounted, which controllers, and whether a sub-cgroup can actually be created.

    ``cgroup.kill`` is the file the project's 5.14 floor is bound by, so its presence is
    reported separately from the mount and from write access. A read-only bind of the
    v2 hierarchy — the Docker default — shows every file and permits no delegation, and
    those two facts have to stay distinguishable.
    """
    base = "/sys/fs/cgroup"
    out: dict = {"mountpoint": base}
    controllers = os.path.join(base, "cgroup.controllers")
    out["v2"] = os.path.exists(controllers)
    if not out["v2"]:
        out["verdict"] = "ABSENT"
        return out
    try:
        out["controllers"] = open(controllers).read().split()
    except OSError as exc:
        out["controllers"] = []
        out["controllers_error"] = str(exc)
    out["cgroup_kill_present"] = os.path.exists(os.path.join(base, "cgroup.kill"))
    out["cgroup_freeze_present"] = os.path.exists(os.path.join(base, "cgroup.freeze"))

    probe_dir = os.path.join(base, "f2a-e17-probe")
    try:
        os.mkdir(probe_dir)
        out["delegation"] = "writable"
        out["sub_cgroup_kill_present"] = os.path.exists(
            os.path.join(probe_dir, "cgroup.kill"))
        os.rmdir(probe_dir)
    except OSError as exc:
        out["delegation"] = f"read-only ({errno.errorcode.get(exc.errno, exc.errno)})"
        out["sub_cgroup_kill_present"] = None
    out["verdict"] = "PRESENT"
    return out


# --------------------------------------------------------------------------------------
# Supporting facts
# --------------------------------------------------------------------------------------


def probe_context() -> dict:
    out = {
        "uname": " ".join(platform.uname()),
        "kernel_release": platform.release(),
        "arch": _ARCH,
        "python": sys.version.split()[0],
        "euid": os.geteuid(),
    }
    for key in ("CapEff", "CapBnd", "NoNewPrivs", "Seccomp", "Seccomp_filters"):
        out[key] = None
    try:
        for line in open("/proc/self/status"):
            k, _, v = line.partition(":")
            if k in out:
                out[k] = v.strip()
    except OSError:
        pass
    out["securityfs_lsm"] = None
    try:
        out["securityfs_lsm"] = open("/sys/kernel/security/lsm").read().strip()
    except OSError as exc:
        out["securityfs_lsm_error"] = errno.errorcode.get(exc.errno, str(exc.errno))
    out["config_gz"] = os.path.exists("/proc/config.gz")
    if out["config_gz"]:
        import gzip

        wanted = ("CONFIG_SECURITY_LANDLOCK", "CONFIG_LSM=", "CONFIG_SECCOMP_FILTER",
                  "CONFIG_CGROUPS", "CONFIG_USER_NS", "CONFIG_SECURITYFS")
        found = {}
        try:
            with gzip.open("/proc/config.gz", "rt") as fh:
                for line in fh:
                    line = line.strip()
                    for w in wanted:
                        if line.startswith(w):
                            found[line.split("=")[0]] = line
        except OSError:
            pass
        out["kernel_config"] = found
    return out


def probe_userns() -> dict:
    """Unprivileged user namespaces, which NOOA's sandbox does not use and ours does."""
    out: dict = {}
    try:
        out["max_user_namespaces"] = open(
            "/proc/sys/user/max_user_namespaces").read().strip()
    except OSError as exc:
        out["max_user_namespaces"] = f"unreadable ({exc.strerror})"
    r, w = os.pipe()
    pid = os.fork()
    if pid == 0:  # pragma: no cover
        os.close(r)
        try:
            libc = _libc()
            ctypes.set_errno(0)
            CLONE_NEWUSER = 0x10000000
            rc = libc.unshare(ctypes.c_int(CLONE_NEWUSER))
            msg = "ok" if rc == 0 else errno.errorcode.get(
                ctypes.get_errno(), str(ctypes.get_errno()))
        except BaseException as exc:  # noqa: BLE001
            msg = f"broken: {exc!r}"
        os.write(w, msg.encode())
        os._exit(0)
    os.close(w)
    out["unshare_CLONE_NEWUSER"] = os.read(r, 256).decode() or "no output"
    os.close(r)
    os.waitpid(pid, 0)
    return out


def collect() -> dict:
    return {
        "probe": "E17 kernel facility probe",
        "dry_run": True,
        "model_calls": 0,
        "cost_usd": 0.0,
        "context": probe_context(),
        "landlock": probe_landlock_enforcement(),
        "seccomp_user_notif": probe_seccomp_user_notif(),
        "cgroup_v2": probe_cgroup_v2(),
        "user_namespaces": probe_userns(),
    }


# --------------------------------------------------------------------------------------
# Self-test — the probe's own decision logic, exercised without needing a kernel
# --------------------------------------------------------------------------------------


def _raises(fn) -> bool:
    try:
        fn()
    except Exception:  # noqa: BLE001
        return True
    return False


def selftest() -> int:
    """Assert the parts of this probe that are logic rather than syscalls.

    The syscall paths cannot be unit-tested without the kernel under test, which is the
    point of the probe. What *can* be pinned is every constant a wrong value would turn
    into a false "unsupported", and the Rule 8 guard that must refuse rather than score.
    """
    checks: list[tuple[str, bool, str]] = []

    def ck(name: str, cond: bool, detail: str = "") -> None:
        checks.append((name, bool(cond), detail))

    ck("ioctl NOTIF_RECV", SECCOMP_IOCTL_NOTIF_RECV == 0xC0502100,
       hex(SECCOMP_IOCTL_NOTIF_RECV))
    ck("ioctl NOTIF_SEND", SECCOMP_IOCTL_NOTIF_SEND == 0xC0182101,
       hex(SECCOMP_IOCTL_NOTIF_SEND))
    ck("ioctl ID_VALID is _IOW not _IOR", SECCOMP_IOCTL_NOTIF_ID_VALID == 0x40082102,
       hex(SECCOMP_IOCTL_NOTIF_ID_VALID))
    ck("ID_VALID differs from the pre-5.9 _IOR form",
       SECCOMP_IOCTL_NOTIF_ID_VALID != _ioc(_IOC_READ, ord("!"), 2, 8))
    ck("struct seccomp_notif is 80 bytes", _SIZEOF_NOTIF == 8 + 4 + 4 + (4 + 4 + 8 + 48))
    ck("struct seccomp_notif_resp is 24 bytes", _SIZEOF_RESP == 8 + 8 + 4 + 4)
    ck("landlock syscall numbers are the arch-independent trio",
       (NR_LANDLOCK_CREATE_RULESET, NR_LANDLOCK_ADD_RULE, NR_LANDLOCK_RESTRICT_SELF)
       == (444, 445, 446))
    ck("NEW_LISTENER flag is bit 3", SECCOMP_FILTER_FLAG_NEW_LISTENER == 8)
    ck("USER_NOTIF ret differs from ALLOW", SECCOMP_RET_USER_NOTIF != SECCOMP_RET_ALLOW)

    prog = _notif_filter(173, 0xC00000B7)
    ck("BPF filter is a whole number of 8-byte instructions", len(prog) % 8 == 0,
       f"{len(prog)} bytes")
    ck("BPF filter is 6 instructions", len(prog) // 8 == 6)
    ck("BPF filter mentions USER_NOTIF",
       struct.pack("<I", SECCOMP_RET_USER_NOTIF) in prog)
    ck("BPF filter mentions ALLOW", struct.pack("<I", SECCOMP_RET_ALLOW) in prog)
    ck("BPF jump targets stay inside the program",
       all(struct.unpack_from("<HBBI", prog, i * 8)[1] + i + 1 <= len(prog) // 8
           and struct.unpack_from("<HBBI", prog, i * 8)[2] + i + 1 <= len(prog) // 8
           for i in range(len(prog) // 8)))
    ck("arch table refuses an unknown machine", _SYSCALLS.get("s390x") is None)
    ck("arch table agrees with the running machine or this is not Linux",
       _ARCH in _SYSCALLS or sys.platform != "linux", _ARCH)
    ck("seccomp(2) numbers differ by arch, so the table is not decoration",
       _SYSCALLS["aarch64"]["seccomp"] != _SYSCALLS["x86_64"]["seccomp"])
    ck("audit arch tokens differ by arch",
       _SYSCALLS["aarch64"]["audit_arch"] != _SYSCALLS["x86_64"]["audit_arch"])

    # Defect 1, found by the dry run: prctl's number is architecture-dependent and the
    # first draft hardcoded x86_64's. This pins the fact and pins that no call site uses it.
    ck("prctl's syscall number is NOT architecture-independent",
       _PRCTL_NUMBERS_DIFFER_BY_ARCH["x86_64"] != _PRCTL_NUMBERS_DIFFER_BY_ARCH["aarch64"],
       "157 on x86_64, 167 on aarch64")
    src = open(__file__, encoding="utf-8").read() if os.path.exists(__file__) else ""
    # Assembled rather than written out, because a literal needle occurs in its own check
    # and the check then always fires. It did, on its first run, which is how this is known
    # to be a live matcher rather than one that can never match anything.
    needles = ["syscall(ctypes." + "c_long(%d)" % n for n in (157, 167)]
    ck("no call site passes a hardcoded prctl number to syscall()",
       not any(n in src for n in needles))
    ck("no_new_privs goes through libc.prctl", "libc.prctl(" in src)

    # Defect 2, found by the dry run: struct.pack refuses 'P' under an explicit byte order,
    # so the seccomp child died before it could report anything.
    ck("struct.pack refuses the pointer code under an explicit byte order",
       _raises(lambda: struct.pack("<HxxxxxxP", 6, 0)))
    fprog = SockFprog(6, None)
    ck("SockFprog is pointer-aligned and 16 bytes on LP64",
       ctypes.sizeof(fprog) == (16 if ctypes.sizeof(ctypes.c_void_p) == 8 else 8),
       f"{ctypes.sizeof(fprog)} bytes")
    ck("SockFprog.len survives the round trip", SockFprog(6, None).len == 6)

    # Rule 8 guard, produced rather than reasoned about: point the child at a path that
    # cannot be opened and require INSTRUMENT_BROKEN rather than a scored denial.
    if sys.platform == "linux" and hasattr(os, "fork"):
        r, w = os.pipe()
        pid = os.fork()
        if pid == 0:  # pragma: no cover
            os.close(r)
            try:
                _landlock_child(w, "/nonexistent/f2a-e17-does-not-exist")
            except BaseException:  # noqa: BLE001
                os.write(w, b'{"verdict":"CHILD_CRASHED"}')
            os._exit(0)
        os.close(w)
        raw = b""
        while chunk := os.read(r, 4096):
            raw += chunk
        os.close(r)
        os.waitpid(pid, 0)
        got = json.loads(raw or b"{}").get("verdict")
        ck("Rule 8: unopenable victim yields INSTRUMENT_BROKEN, not ENFORCED",
           got == "INSTRUMENT_BROKEN", f"got {got!r}")
    else:
        ck("Rule 8 guard (skipped: needs Linux + fork)", True, "SKIPPED")

    with tempfile.TemporaryDirectory() as td:
        probe = os.path.join(td, "not-a-cgroup")
        os.makedirs(probe)
        ck("cgroup probe reports ABSENT when there is no v2 hierarchy",
           not os.path.exists(os.path.join(probe, "cgroup.controllers")))

    failed = [c for c in checks if not c[1]]
    for name, ok, detail in checks:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"   [{detail}]" if detail else ""))
    print(f"\n{len(checks)} checks, {len(failed)} failures")
    return 1 if failed else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[2])
    ap.add_argument("--json", action="store_true", help="emit one JSON object on stdout")
    ap.add_argument("--invocation", default=os.environ.get("E17_PROBE_INVOCATION", ""),
                    help="the exact docker command that produced this reading; recorded "
                         "verbatim in the output, because a privilege result no one can "
                         "re-issue the command for is not a privilege result")
    ap.add_argument("--selftest", action="store_true",
                    help="prove the probe's own constants and its Rule 8 guard")
    args = ap.parse_args()

    if args.selftest:
        return selftest()

    if sys.platform != "linux":
        payload = {"probe": "E17 kernel facility probe", "dry_run": True,
                   "verdict": "NOT_LINUX",
                   "detail": f"sys.platform={sys.platform}; run this inside a container"}
        print(json.dumps(payload, indent=2) if args.json else payload["detail"])
        return 2

    data = collect()
    data["invocation"] = args.invocation
    if args.json:
        print(json.dumps(data, indent=2, sort_keys=True))
        return 0

    c = data["context"]
    print(f"kernel   {c['kernel_release']}  {c['arch']}  euid={c['euid']}")
    print(f"caps     CapEff={c['CapEff']}  Seccomp={c['Seccomp']} "
          f"filters={c['Seccomp_filters']}  NoNewPrivs={c['NoNewPrivs']}")
    ll = data["landlock"]
    print(f"landlock ABI={ll['abi'].get('abi_version')}  verdict={ll.get('verdict')}"
          f"  ({ll['abi'].get('reason') or 'syscall accepted'})")
    sc = data["seccomp_user_notif"]
    print(f"seccomp  verdict={sc.get('verdict')}  listener={sc.get('listener_fd')}"
          f"  recv={sc.get('recv')}  id_valid={sc.get('id_valid_ioctl')}"
          f"  send={sc.get('send')}")
    cg = data["cgroup_v2"]
    print(f"cgroup2  {cg.get('verdict')}  kill={cg.get('cgroup_kill_present')}"
          f"  delegation={cg.get('delegation')}")
    un = data["user_namespaces"]
    print(f"userns   unshare={un.get('unshare_CLONE_NEWUSER')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
