"""FR-050's not-inherited clause: a fresh scratch per session, and a resumed
session reattaching **its own**.

FR-007 makes a resumed session the same session, so the two operations are
distinct verbs rather than one call that creates-or-opens. A single
`get_or_create` would turn a resume whose scratch went missing into a fresh
session claiming continuity it does not have, silently.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from src.supervisor.session_env import SessionEnvError, SessionEnvironments


@pytest.fixture()
def envs(tmp_path: Path) -> SessionEnvironments:
    return SessionEnvironments(tmp_path / "sessions")


def test_a_new_session_gets_a_fresh_private_scratch(envs) -> None:
    env = envs.create("s-1")
    assert env.scratch.is_dir()
    assert not env.resumed
    assert env.scratch.stat().st_mode & 0o777 == 0o700


def test_two_sessions_never_share_scratch(envs) -> None:
    first = envs.create("s-1")
    second = envs.create("s-2")
    assert first.scratch != second.scratch
    (first.scratch / "token").write_text("leftover")
    assert not (second.scratch / "token").exists()


def test_create_refuses_to_reuse_rather_than_emptying(envs) -> None:
    """Emptying is a cleanup path, and one that fails leaves inheritance in
    place while reporting success."""
    env = envs.create("s-1")
    (env.scratch / "credential-cache").write_text("stale")
    with pytest.raises(SessionEnvError, match="already exists"):
        envs.create("s-1")
    assert (env.scratch / "credential-cache").read_text() == "stale", (
        "create() emptied the directory on the way to refusing"
    )


def test_a_resume_reattaches_the_same_scratch(envs) -> None:
    created = envs.create("s-1")
    (created.scratch / "checkpoint").write_text("iteration 3")
    resumed = envs.attach("s-1")
    assert resumed.scratch == created.scratch
    assert resumed.resumed
    assert (resumed.scratch / "checkpoint").read_text() == "iteration 3"


def test_a_resume_with_no_scratch_refuses_rather_than_creating(envs) -> None:
    """Creating one would turn a resume into a fresh session claiming
    continuity it does not have (FR-007)."""
    with pytest.raises(SessionEnvError, match="does not create one"):
        envs.attach("s-never-existed")


def test_a_world_readable_scratch_stops_the_session(envs) -> None:
    env = envs.create("s-1")
    os.chmod(env.scratch, 0o755)
    with pytest.raises(SessionEnvError, match="0700"):
        envs.attach("s-1")


def test_destroy_is_housekeeping_and_isolation_does_not_depend_on_it(
    envs, tmp_path
) -> None:
    """**The removal proof.** Skip teardown entirely; isolation still holds.

    A session whose supervisor was `SIGKILL`ed leaves its scratch behind. The
    next session has a different id and therefore a different directory, so
    nothing was inherited whether or not `destroy()` ever ran.
    """
    crashed = envs.create("s-crashed")
    (crashed.scratch / "secret-cache").write_text("value")
    # No destroy() call. This is the crash path.
    successor = envs.create("s-successor")
    assert not (successor.scratch / "secret-cache").exists()
    assert crashed.scratch.is_dir(), "something cleaned up; the arm is vacuous"


def test_destroy_removes_the_tree_when_it_does_run(envs) -> None:
    env = envs.create("s-1")
    envs.destroy("s-1")
    assert not env.scratch.exists()
    # Idempotent: a second call on the crash path must not raise.
    envs.destroy("s-1")
