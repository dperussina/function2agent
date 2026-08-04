"""The two **authority** gaps from finding 021: places where a write *succeeds*
inside a session, as distinct from the audit gaps in the seccomp watch set.

`test_mount_namespace.py` next door asserts that declared behaviour works and
that undeclared locations are *absent*. Every assertion in it is of the form
"the thing we said would happen happened". None of them asks the opposite
question — **can the workload write somewhere it was never given?** — and that
is exactly why two writable holes survived 436 tests and 61 removal proofs.

The two questions this file adds:

1. **Is the session root itself read-only?** It is not a declared location and
   no `FS-*` rule governs it, so a file created there is created at a path the
   classifier will call `FS-001 undeclared_location` *while the kernel completes
   the write*. `test_the_root_contains_only_declared_targets` next door lists
   the root and finds two entries — but it lists it without having tried to add
   a third, so it passes against a root that anything can write to.

2. **Is a read-only declaration read-only all the way down?** The bind carries
   `MS_REC` and copies the source's whole subtree; `MS_REMOUNT | MS_BIND`
   applies to one mount rather than to a tree, so before the fix every submount
   inside a declared `mode="ro"` source stayed writable.
   `test_a_read_only_declaration_is_actually_read_only` next door writes to a
   file at the *top* of the location, which is the one place the non-recursive
   remount does cover.

**Finding 021 says both gaps close under an unprivileged uid. That claim is
false as stated and nothing here rests on it.** The finding re-ran its probe
after `setuid(65534)` and got `EACCES` everywhere, and read that as the gaps
closing. It is an artifact of its probe tmpfs's *file permissions*, not a
property of the declaration: re-measured with the recursive remount disabled
and the workload at uid 65534, a submount file at mode `0666` was still
writable. A uid drop changes who may write a given inode; `mode="ro"` is a
promise about the declaration, and the two are different facts. So these
assertions are not "defense in depth behind a privilege drop" — a privilege
drop would not make any of them redundant, and the mount flags are the only
thing establishing what they assert.

Run:
    docker run --rm --privileged -v "$PWD:/work" -w /work python:3.12-slim \\
        sh -c 'pip install -q pytest PyYAML && python -m pytest \\
        tests/integration/test_mount_authority.py -v'
"""

from __future__ import annotations

import errno
import json
import os
import sys
from pathlib import Path

import pytest

pytestmark = [
    pytest.mark.linux_only,
    pytest.mark.privileged,
    pytest.mark.skipif(sys.platform != "linux", reason="OD-17: Linux only"),
]

from src.supervisor import _linux, mounts  # noqa: E402
from src.supervisor.location_set import parse  # noqa: E402
from tests.fixtures.locations import document  # noqa: E402

SUBMOUNT = "inner"
SUBMOUNT_FILE = "inner/from-submount.txt"


def _write_errno(path: str) -> int:
    """Open `path` for writing and return the errno, or 0 on success."""
    try:
        with open(path, "wb") as fh:
            fh.write(b"x")
        return 0
    except OSError as exc:
        return exc.errno


def _mkdir_errno(path: str) -> int:
    try:
        os.mkdir(path)
        return 0
    except OSError as exc:
        return exc.errno


@pytest.fixture()
def declared(tmp_path: Path):
    """One read-only declaration, with a directory the test can submount into."""
    app = tmp_path / "app"
    (app / SUBMOUNT).mkdir(parents=True)
    (app / "main.py").write_text("print('hello')\n")

    location_set = parse(document(locations=[
        {"source": str(app), "target": "/workspace", "mode": "ro",
         "rule_id": "FS-DECL-001", "justification": "the analyzed application"},
    ]))
    staging = tmp_path / "staging"
    staging.mkdir()
    return app, mounts.plan(location_set, "s-authority", str(staging))


def _run_with_submount(plan, source: Path, body):
    """Run `body` inside the namespace, with a tmpfs submounted in the source.

    Two forks deep on purpose. The submount has to exist in the mount table
    that `enter()` inherits, so it is created in an intermediate child that has
    already unshared — which keeps it out of the test process's own namespace
    and out of the host's. `run_in_namespace()` then forks again and unshares
    again, and the second namespace inherits the tmpfs as a submount of the
    declared source.

    Mounting it in the host namespace and unmounting in a `finally` would be
    shorter and would leave a writable tmpfs behind whenever the test crashed.
    """
    read_fd, write_fd = os.pipe()
    pid = os.fork()
    if pid == 0:  # intermediate child: owns the submount
        os.close(read_fd)
        code = 0
        try:
            _linux.unshare(_linux.CLONE_NEWNS)
            _linux.mount(None, "/", None, _linux.MS_REC | _linux.MS_PRIVATE)
            _linux.mount("tmpfs", str(source / SUBMOUNT), "tmpfs", 0, "mode=0755")
            (source / SUBMOUNT_FILE).write_text("seeded in the submount\n")
            payload = mounts.run_in_namespace(plan, body)
        except BaseException as exc:  # noqa: BLE001 - reported, then exit
            payload = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
            code = 1
        try:
            os.write(write_fd, json.dumps(payload).encode("utf-8"))
        finally:
            os.close(write_fd)
        os._exit(code)

    os.close(write_fd)
    chunks = []
    while True:
        chunk = os.read(read_fd, 65536)
        if not chunk:
            break
        chunks.append(chunk)
    os.close(read_fd)
    os.waitpid(pid, 0)
    raw = b"".join(chunks)
    assert raw, "the intermediate child produced no result"
    return json.loads(raw.decode("utf-8"))


# --- Defect 2: the session root ------------------------------------------


def test_the_session_root_refuses_a_new_file(declared) -> None:
    """A path in the session root is undeclared. Nothing may be created at it.

    Finding 021 observed `openat(O_CREAT)` return `OK` here as uid 0. The
    classifier calls such a path `FS-001 undeclared_location` — a record that
    says *there is nothing at this path* about a write that is at that moment
    putting something there.
    """
    _app, plan = declared
    out = mounts.run_in_namespace(plan, lambda: _write_errno("/undeclared.txt"))
    assert out["ok"], out
    assert out["result"] == errno.EROFS, (
        f"creating /undeclared.txt in the session root gave errno "
        f"{out['result']} ({errno.errorcode.get(out['result'], '?')}); the "
        "root is not a declared location, so a workload must not be able to "
        "put a file at a path FS-001 will describe as absent"
    )


def test_the_session_root_refuses_a_new_directory(declared) -> None:
    """`mkdir` is a separate kernel path from `openat(O_CREAT)`.

    Asserted separately because a root that refused `openat` and allowed
    `mkdir` would pass the test above and still let a workload build a tree at
    an undeclared path.
    """
    _app, plan = declared
    out = mounts.run_in_namespace(plan, lambda: _mkdir_errno("/undeclared-dir"))
    assert out["ok"], out
    assert out["result"] == errno.EROFS, (
        f"mkdir /undeclared-dir gave errno {out['result']} "
        f"({errno.errorcode.get(out['result'], '?')}), not EROFS"
    )


def test_the_root_listing_is_unchanged_by_a_write_attempt(declared) -> None:
    """The observable form of the gap, stated as the finding stated it.

    Finding 021 recorded the root listing going from one entry to four. This
    asserts the listing *after* the attempts, so a fix that returned an errno
    while still creating the entry would not pass.
    """
    _app, plan = declared

    def attempt_then_list() -> list[str]:
        for path in ("/undeclared.txt", "/undeclared2.txt"):
            _write_errno(path)
        _mkdir_errno("/undeclared-dir")
        return sorted(os.listdir("/"))

    out = mounts.run_in_namespace(plan, attempt_then_list)
    assert out["ok"], out
    assert out["result"] == ["workspace"], (
        f"the session root lists {out['result']} after three write attempts; "
        "only the declared target should be there"
    )


def test_a_declared_read_only_location_is_still_readable(declared) -> None:
    """The root going read-only must not take the declared set with it.

    A fix that remounted `/` read-only and broke reads inside `/workspace`
    would satisfy every assertion above and destroy the mechanism.
    """
    _app, plan = declared
    out = mounts.run_in_namespace(
        plan, lambda: open("/workspace/main.py", "rb").read().decode()
    )
    assert out["ok"], out
    assert out["result"] == "print('hello')\n"


# --- Defect 3: submounts inside a read-only declaration ------------------


def test_the_submount_fixture_actually_produces_a_submount(declared) -> None:
    """**Control arm.** Without this, defect 3's test could pass vacuously.

    If the tmpfs failed to mount, or `MS_REC` did not carry it into the
    session, the write below would fail for the ordinary reason — the enclosing
    mount is read-only — and the test would report success while measuring
    nothing. This asserts the submount is a distinct mount inside the session
    before anything is claimed about its flags.

    `st_dev` rather than `/proc/self/mountinfo`, which is how finding 021 read
    it: the session root is empty by construction, so there is no `/proc`
    inside it to read. A distinct device number is the same fact — two mounts,
    not one — and is available without mounting anything extra.
    """
    app, plan = declared

    def devices() -> list[int]:
        return [os.stat("/workspace").st_dev,
                os.stat(f"/workspace/{SUBMOUNT}").st_dev]

    out = _run_with_submount(plan, app, devices)
    assert out["ok"], out
    outer, inner = out["result"]
    assert outer != inner, (
        f"/workspace and /workspace/{SUBMOUNT} share st_dev {outer}; the "
        "fixture did not produce a submount, so the read-only-submount test "
        "below would measure nothing"
    )


def test_a_submount_inside_a_read_only_location_refuses_a_write(declared) -> None:
    """Defect 3. The bind is recursive; the read-only remount must be too.

    Finding 021 observed `OK` from both `openat` and `openat2` against a file
    inside a submount under a `mode="ro"` declaration, while the identical
    write one directory up returned `EROFS`. `mountinfo` showed the outer mount
    `ro` and the inner `rw`.
    """
    app, plan = declared
    out = _run_with_submount(
        plan, app, lambda: _write_errno(f"/workspace/{SUBMOUNT_FILE}")
    )
    assert out["ok"], out
    assert out["result"] == errno.EROFS, (
        f"writing to /workspace/{SUBMOUNT_FILE} gave errno {out['result']} "
        f"({errno.errorcode.get(out['result'], '?')}). The declaration is "
        "mode='ro' and the bind carries MS_REC, so the read-only remount has "
        "to reach every mount the bind copied, not only the outermost one"
    )


def test_a_new_file_in_that_submount_is_refused_too(declared) -> None:
    """`O_CREAT` against a path that does not yet exist in the submount.

    Separate from the overwrite above because the two take different paths
    through the VFS, and finding 021 measured both.
    """
    app, plan = declared
    out = _run_with_submount(
        plan, app, lambda: _write_errno(f"/workspace/{SUBMOUNT}/created.txt")
    )
    assert out["ok"], out
    assert out["result"] == errno.EROFS


def test_the_submount_carries_the_read_only_flag_itself(declared) -> None:
    """The mechanism, not just the errno.

    `EROFS` could in principle come from the underlying filesystem rather than
    from this mount's own flags — and the submount here is a `tmpfs`, which is
    writable by nature, so the flag has to be on the mount. `statvfs` reports
    the per-mount flags directly, which is the same fact finding 021 read out
    of `mountinfo`'s `ro` / `rw` field, obtainable without a `/proc`.
    """
    app, plan = declared

    def inner_is_read_only() -> list[bool]:
        return [bool(os.statvfs("/workspace").f_flag & os.ST_RDONLY),
                bool(os.statvfs(f"/workspace/{SUBMOUNT}").f_flag & os.ST_RDONLY)]

    out = _run_with_submount(plan, app, inner_is_read_only)
    assert out["ok"], out
    outer, inner = out["result"]
    assert outer, "the outer mount is not read-only; the fixture is wrong"
    assert inner, (
        "the outer mount carries ST_RDONLY and the submount does not. That is "
        "finding 021's mountinfo observation exactly: outer ro, inner rw"
    )


def test_a_writable_declaration_is_not_made_read_only_by_the_recursion(
    tmp_path: Path,
) -> None:
    """**The counterfactual.** The recursion must not read-only everything.

    A fix that applied `MS_RDONLY` to every mount regardless of the
    declaration's mode would pass every assertion above and would silently
    convert `mode="rw"` into `mode="ro"`. Under OD-10 nothing writes today, so
    no other test in the suite would notice.
    """
    scratch = tmp_path / "scratch"
    (scratch / SUBMOUNT).mkdir(parents=True)
    location_set = parse(document(locations=[
        {"source": str(scratch), "target": "/scratch", "mode": "rw",
         "rule_id": "FS-DECL-003", "justification": "per-session scratch"},
    ]))
    staging = tmp_path / "staging"
    staging.mkdir()
    plan = mounts.plan(location_set, "s-rw", str(staging))

    out = _run_with_submount(
        plan, scratch, lambda: _write_errno(f"/scratch/{SUBMOUNT}/ok.txt")
    )
    assert out["ok"], out
    assert out["result"] == 0, (
        f"a declared mode='rw' submount returned errno {out['result']} "
        f"({errno.errorcode.get(out['result'], '?')}); the recursion must "
        "carry the declaration's own flags, not MS_RDONLY unconditionally"
    )
