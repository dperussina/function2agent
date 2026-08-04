"""FR-048's mechanism test: an undeclared location is **absent**, not
permission-denied.

The distinction is the requirement. A `chmod`-based or capability-based scheme
produces `EACCES` — the path exists, something refused. FR-048 says *"a
location is reachable because it was declared, never because nothing excluded
it"*, and the observable form of that is `ENOENT`: there is nothing to exclude,
because there is no `/etc`.

So these tests assert **the errno**, not merely that the open failed. A test
that asserted only failure would pass against a permissions scheme, which is
the design FR-048 rejects.

The removal proof is `test_without_pivot_root_the_host_is_visible`: it runs the
same body with the namespace step omitted and asserts the host root *is*
reachable. Without it, every assertion here would also pass on a machine where
`/etc/shadow` happened to be unreadable for some other reason.

Run:
    docker run --rm --privileged -v "$PWD:/work" -w /work f2a-dev \\
        python -m pytest tests/integration/test_mount_namespace.py -v
"""

from __future__ import annotations

import errno
import os
import sys
from pathlib import Path

import pytest

pytestmark = [
    pytest.mark.linux_only,
    pytest.mark.privileged,
    pytest.mark.skipif(sys.platform != "linux", reason="OD-17: Linux only"),
]

from src.supervisor import mounts  # noqa: E402
from src.supervisor.location_set import parse  # noqa: E402
from tests.fixtures.locations import document  # noqa: E402


def _probe_errno(path: str) -> int:
    """Open `path` and return the errno, or 0 on success. JSON-able."""
    try:
        with open(path, "rb"):
            return 0
    except OSError as exc:
        return exc.errno


@pytest.fixture()
def declared(tmp_path: Path):
    app = tmp_path / "app"
    app.mkdir()
    (app / "main.py").write_text("print('hello')\n")
    tools = tmp_path / "toolchain"
    tools.mkdir()
    (tools / "python").write_text("#!/bin/sh\n")

    location_set = parse(document(locations=[
        {"source": str(app), "target": "/workspace", "mode": "ro",
         "rule_id": "FS-DECL-001", "justification": "the analyzed application"},
        {"source": str(tools), "target": "/opt/toolchain", "mode": "ro",
         "rule_id": "FS-DECL-002", "justification": "resolved toolchain"},
    ]))
    staging = tmp_path / "staging"
    staging.mkdir()
    return mounts.plan(location_set, "s-fr048", str(staging))


def test_a_declared_location_is_present(declared) -> None:
    out = mounts.run_in_namespace(
        declared, lambda: _probe_errno("/workspace/main.py")
    )
    assert out["ok"], out
    assert out["result"] == 0


@pytest.mark.parametrize(
    "undeclared",
    ["/etc/shadow", "/etc/passwd", "/root/.ssh/id_rsa", "/proc/self/environ",
     "/var/lib/f2a/egress-policy.json"],
)
def test_an_undeclared_location_is_absent_not_denied(declared, undeclared) -> None:
    out = mounts.run_in_namespace(declared, lambda: _probe_errno(undeclared))
    assert out["ok"], out
    assert out["result"] == errno.ENOENT, (
        f"{undeclared} produced errno {out['result']} "
        f"({errno.errorcode.get(out['result'], '?')}). FR-048 requires "
        "ENOENT — absent. EACCES would mean the path exists and something "
        "refused, which is the excluded-by-policy design FR-048 rejects."
    )


def test_the_root_contains_only_declared_targets(declared) -> None:
    out = mounts.run_in_namespace(declared, lambda: sorted(os.listdir("/")))
    assert out["ok"], out
    assert out["result"] == ["opt", "workspace"], (
        f"root contains {out['result']}; an empty root plus the declared set "
        "should contain nothing else"
    )


def test_a_read_only_declaration_is_actually_read_only(declared) -> None:
    """The remount step, asserted.

    A bind mount ignores its flags on the first `mount()` call; only the
    `MS_REMOUNT` pass applies them. Omitting the second call yields a mount
    that looks read-only in the plan and is writable in fact, and this is the
    test that tells them apart.
    """
    def write() -> int:
        try:
            with open("/workspace/injected", "wb") as fh:
                fh.write(b"x")
            return 0
        except OSError as exc:
            return exc.errno

    out = mounts.run_in_namespace(declared, write)
    assert out["ok"], out
    assert out["result"] == errno.EROFS


def test_a_declared_source_that_does_not_exist_fails_the_session(tmp_path) -> None:
    """Fail closed, not skip. A skipped mount makes the positive set false."""
    location_set = parse(document(locations=[
        {"source": str(tmp_path / "absent"), "target": "/workspace",
         "mode": "ro", "rule_id": "FS-DECL-001", "justification": "missing"},
    ]))
    staging = tmp_path / "staging"
    staging.mkdir()
    out = mounts.run_in_namespace(
        mounts.plan(location_set, "s-missing", str(staging)),
        lambda: 0,
    )
    assert not out["ok"]
    assert "MountError" in out["error"]


def test_without_pivot_root_the_host_is_visible(declared) -> None:
    """**The removal proof.** Same probe, mechanism removed.

    If `/etc/shadow` were unreachable for some unrelated reason, every
    assertion above would pass with the namespace deleted. This runs the probe
    in a plain fork and asserts the host root *is* reachable, so the ENOENT
    results above are attributable to the namespace and to nothing else.
    """
    read_fd, write_fd = os.pipe()
    pid = os.fork()
    if pid == 0:
        os.close(read_fd)
        os.write(write_fd, str(_probe_errno("/etc/passwd")).encode())
        os.close(write_fd)
        os._exit(0)
    os.close(write_fd)
    observed = int(os.read(read_fd, 32) or b"-1")
    os.close(read_fd)
    os.waitpid(pid, 0)
    assert observed != errno.ENOENT, (
        "/etc/passwd is already absent on this host, so the ENOENT results "
        "above are not evidence the mount namespace did anything"
    )


def test_the_plan_is_recordable_before_anything_is_mounted(declared) -> None:
    """SC-022 needs the record; the plan is what the supervisor emits."""
    record = declared.as_record()
    assert record["location_set_address"].startswith("sha256:")
    assert [m["target"] for m in record["mounts"]] == ["/workspace", "/opt/toolchain"]
    assert all(m["rule_id"] for m in record["mounts"])
