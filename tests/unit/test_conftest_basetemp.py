"""The basetemp redirect must not delete a concurrent run's directory.

`tests/conftest.py`'s `pytest_configure` shortens `tmp_path` on hosts whose
`$TMPDIR` overflows `sun_path`. It did so into a directory keyed by uid, and it
begins by deleting that directory — so a second pytest process starting while a
first was running deleted the live tree underneath it. The victim saw a
`FileNotFoundError` from whichever test next touched `tmp_path`, naming nothing
about the cause.

These tests assert the two properties that make the redirect concurrency-safe:
the directory a run is given is not shared, and reaping is narrowed to processes
that have exited.
"""

from __future__ import annotations

import os
import subprocess
import sys
import types

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import conftest as suite_conftest  # noqa: E402


def _dead_pid() -> int:
    """A pid that is certainly not running: a child we started and reaped.

    The kernel could in principle recycle it before the assertion runs. That
    would make this test fail rather than pass wrongly, which is the direction
    an unavoidable race should fail in.
    """
    child = subprocess.Popen([sys.executable, "-c", ""])
    child.wait()
    return child.pid


def _config(basetemp: str | None = None) -> types.SimpleNamespace:
    return types.SimpleNamespace(option=types.SimpleNamespace(basetemp=basetemp))


def test_a_live_process_directory_survives_another_runs_configure(tmp_path):
    """The defect, stated as the property it violated.

    A sibling directory named for a live pid must still exist after the reaper
    has run. Under the uid-keyed version the whole root was removed, so this is
    the assertion that separates the two.
    """
    root = tmp_path / "root"
    root.mkdir()
    live = root / str(os.getpid())
    live.mkdir()
    (live / "in-use").write_text("a concurrent run's data")

    suite_conftest._reap_abandoned_basetemps(str(root))

    assert (live / "in-use").read_text() == "a concurrent run's data"


def test_an_exited_process_directory_is_reaped(tmp_path):
    """Per-pid directories leak where a shared one did not, so they are cleaned."""
    root = tmp_path / "root"
    root.mkdir()
    abandoned = root / str(_dead_pid())
    abandoned.mkdir()
    (abandoned / "leftover").write_text("from a run that ended")

    suite_conftest._reap_abandoned_basetemps(str(root))

    assert not abandoned.exists()


def test_a_name_that_is_not_a_pid_is_left_alone(tmp_path):
    """Reaping is keyed on a pid, so anything else in the root is not ours."""
    root = tmp_path / "root"
    root.mkdir()
    stranger = root / "not-a-pid"
    stranger.mkdir()

    suite_conftest._reap_abandoned_basetemps(str(root))

    assert stranger.exists()


def test_a_missing_root_is_not_an_error(tmp_path):
    """The first run on a host has no root to reap."""
    suite_conftest._reap_abandoned_basetemps(str(tmp_path / "never-created"))


def test_a_redirect_that_would_still_overflow_raises(monkeypatch):
    """The guard exists because the failure it prevents does not name this hook.

    A redirect that overflows the budget reintroduces the overflow it was added
    to prevent, and the resulting socket error names the path rather than the
    redirect — so proceeding quietly would restore the original defect with its
    cause one step further away.
    """
    monkeypatch.setattr(suite_conftest, "_SUN_PATH_MAX", 1)
    monkeypatch.setattr(suite_conftest.tempfile, "gettempdir", lambda: "/" * 200)

    with pytest.raises(RuntimeError, match="sun_path budget"):
        suite_conftest.pytest_configure(_config())


def test_an_explicit_basetemp_is_never_overridden():
    """`--basetemp` is how a caller works around this hook; it must win."""
    config = _config(basetemp="/somewhere/chosen/by/the/caller")

    suite_conftest.pytest_configure(config)

    assert config.option.basetemp == "/somewhere/chosen/by/the/caller"
