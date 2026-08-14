"""T167 — SC-024 not-inherited: a later session cannot read this one's writes.

**Criterion**: SC-024 — *zero values written inside one session's
environment are readable from a later session's*. FR-050 layer 4: fresh
container and fresh scratch per session.

## What this file is, and what it is not

**Do.** Static / in-process half CI can fail: `SessionEnvironments`
isolation still holds without `destroy()` (the T110 crash path). Live
half: two sequential `docker run --rm` of the sandbox image, a planted
file in the first scratch, absent from the second. Skip loudly if the
Docker daemon is absent or the sandbox image is not loaded.

**Do not.** Rename `tests/unit/test_session_env.py` — that file is T110
and must keep firing, including the SIGKILL / no-destroy arm. Invent a
serve loop or T215. Build images in CI. Offer `seccomp=unconfined`.
Complete T166's env/proc/mounts scan (different surfaces) or T173+.

A skip-only suite is not a T167 pass. The in-process half is what CI can
fail; it is not the only T167 pass — the live half is the named SC-024
claim when the image is loaded.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from src.supervisor.session_env import SessionEnvError, SessionEnvironments
from tests.batteries.evidence import record_evidence

REPO = Path(__file__).resolve().parents[2]
T110 = REPO / "tests" / "unit" / "test_session_env.py"

SANDBOX_IMAGE_TAGS = ("f2a-sandbox:local", "f2a-sandbox")

#: Unique needle written into the first session's scratch. A later
#: session that can read it has inherited.
PLANTED = "t167-scratch-plant-c3e8a91f4b20d67e"

CRASHED_ID = "sess-t167-crashed"
SUCCESSOR_ID = "sess-t167-successor"

#: Flipping this makes the successor the same session (FR-007 resume),
#: which is not the later-session claim.
NEXT_IS_NEW_SESSION = True

#: Flipping this lets the in-process arm skip the crash-path assertion.
ISOLATION_DEPENDS_ON_DESTROY = False

PLANT_NAME = "t167-planted"


def findings(blob: str, secret: str = PLANTED) -> list[str]:
    return [secret] if secret in blob else []


def _require_docker() -> str:
    """The live half's gate. Skip names the daemon, never silently.

    A missing binary and a present binary that cannot talk to a daemon are
    the same absence: there is no daemon to run a container against.
    """
    exe = shutil.which("docker")
    if exe is None:
        pytest.skip("Docker daemon is absent: `docker` is not on PATH")
    probe = subprocess.run(
        [exe, "info"],
        capture_output=True,
        text=True,
        timeout=20,
    )
    if probe.returncode != 0:
        pytest.skip("Docker daemon is absent: `docker info` refused")
    return exe


def _loaded_image(tags: tuple[str, ...]) -> str:
    docker = _require_docker()
    for tag in tags:
        inspect = subprocess.run(
            [docker, "image", "inspect", tag],
            capture_output=True,
            text=True,
            timeout=20,
        )
        if inspect.returncode == 0:
            return tag
    pytest.skip(
        f"Docker daemon is present but none of {tags} is loaded; "
        "the live later-session half cannot scan"
    )


def _cat_scratch(image: str, scratch: Path) -> subprocess.CompletedProcess[str]:
    """Read the planted file from inside a sandbox run bound to this scratch.

    The host dir is chmod 0755 so uid 10001 (`agent`) can list it. The
    0700 claim stays on `SessionEnvironments` (T110); this arm is the
    later-session mount, not the mode.
    """
    docker = _require_docker()
    argv = [
        docker, "run", "--rm", "--network", "none",
        "-v", f"{scratch.resolve()}:/scratch",
        image, "python3", "-c",
        "import pathlib; p=pathlib.Path('/scratch/" + PLANT_NAME + "'); "
        "print(p.read_text() if p.exists() else 'ABSENT')",
    ]
    return subprocess.run(
        argv,
        capture_output=True,
        text=True,
        timeout=60,
    )


# ---------------------------------------------------------------------------
# Controls.
# ---------------------------------------------------------------------------


def test_the_scanner_catches_a_planted_scratch_value() -> None:
    assert PLANTED in findings(f"ordinary dump {PLANTED} end")
    assert findings("a perfectly ordinary later session") == []


def test_t110_session_env_file_still_fires() -> None:
    """T167 is not a rename of test_session_env.py. The SIGKILL arm stays."""
    assert T110.is_file(), (
        "tests/unit/test_session_env.py is gone; T110's in-process "
        "isolation is no longer a test this suite can fail"
    )
    text = T110.read_text()
    assert "test_destroy_is_housekeeping_and_isolation_does_not_depend_on_it" in text
    assert "No destroy() call. This is the crash path." in text
    assert "test_two_sessions_never_share_scratch" in text
    assert "test_create_refuses_to_reuse_rather_than_emptying" in text


# ---------------------------------------------------------------------------
# Static / in-process: SessionEnvironments, including the no-destroy arm.
# ---------------------------------------------------------------------------


def test_nothing_written_in_one_session_is_readable_from_a_later_session(
    tmp_path: Path,
) -> None:
    """The in-process half. Isolation does not depend on destroy()."""
    assert ISOLATION_DEPENDS_ON_DESTROY is False
    assert NEXT_IS_NEW_SESSION is True
    envs = SessionEnvironments(tmp_path / "sessions")
    crashed = envs.create(CRASHED_ID)
    (crashed.scratch / PLANT_NAME).write_text(PLANTED)
    assert (crashed.scratch / PLANT_NAME).read_text() == PLANTED
    # T167: no destroy(). Isolation must hold on the crash path (T110).
    later_id = SUCCESSOR_ID if NEXT_IS_NEW_SESSION else CRASHED_ID
    successor = envs.create(later_id)
    assert successor.scratch != crashed.scratch
    assert not (successor.scratch / PLANT_NAME).exists()
    later_blob = "\n".join(
        path.read_text(errors="replace")
        for path in successor.scratch.rglob("*")
        if path.is_file()
    )
    assert findings(later_blob) == []
    leaked = [path for path in successor.scratch.rglob("*") if path.is_file()]
    assert leaked == [], f"the later session inherited {leaked}"
    assert crashed.scratch.is_dir(), "something cleaned up; the arm is vacuous"
    assert (crashed.scratch / PLANT_NAME).read_text() == PLANTED


def test_create_still_refuses_reuse_rather_than_emptying(tmp_path: Path) -> None:
    """Emptying is a cleanup path; a failed cleanup would inherit."""
    envs = SessionEnvironments(tmp_path / "sessions")
    env = envs.create(CRASHED_ID)
    (env.scratch / PLANT_NAME).write_text(PLANTED)
    with pytest.raises(SessionEnvError, match="already exists"):
        envs.create(CRASHED_ID)
    assert (env.scratch / PLANT_NAME).read_text() == PLANTED, (
        "create() emptied the directory on the way to refusing"
    )


def test_a_missing_docker_daemon_skip_names_the_daemon(monkeypatch) -> None:
    """The live half's skip is loud, and CI can fail this."""
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    with pytest.raises(pytest.skip.Exception) as caught:
        _require_docker()
    assert "daemon" in str(caught.value).lower(), (
        f"the skip does not name the daemon: {caught.value!r}"
    )


def test_an_unloaded_image_skip_names_the_image(monkeypatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda _name: "/usr/bin/docker")

    def fake_run(argv, **_kwargs):
        if len(argv) >= 2 and argv[1] == "info":
            return subprocess.CompletedProcess(argv, 0, "", "")
        if len(argv) >= 2 and argv[1] == "image":
            return subprocess.CompletedProcess(argv, 1, "", "missing")
        raise AssertionError(argv)

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(pytest.skip.Exception) as caught:
        _loaded_image(SANDBOX_IMAGE_TAGS)
    msg = str(caught.value).lower()
    assert "daemon" in msg, f"the skip does not name the daemon: {caught.value!r}"
    assert "loaded" in msg, (
        f"the skip does not name the unloaded image: {caught.value!r}"
    )


# ---------------------------------------------------------------------------
# Live: two sequential sandbox runs, planted file absent from the second.
# ---------------------------------------------------------------------------


def test_a_plant_in_the_first_scratch_is_absent_from_the_second(
    tmp_path: Path,
) -> None:
    """SC-024 later-session, live. Skip names the daemon or the unloaded image."""
    image = _loaded_image(SANDBOX_IMAGE_TAGS)
    first = tmp_path / "sess-a" / "scratch"
    second = tmp_path / "sess-b" / "scratch"
    first.mkdir(parents=True)
    second.mkdir(parents=True)
    first.chmod(0o755)
    second.chmod(0o755)
    (first / PLANT_NAME).write_text(PLANTED)

    seen = _cat_scratch(image, first)
    combined = (seen.stdout or "") + (seen.stderr or "")
    assert seen.returncode == 0, (
        f"the first sandbox run failed. exit={seen.returncode} text={combined!r}"
    )
    assert PLANTED in (seen.stdout or ""), (
        "the first sandbox run could not read its own planted file; the "
        "second-session absence would be vacuous"
    )

    absent = _cat_scratch(image, second)
    later = (absent.stdout or "") + (absent.stderr or "")
    assert absent.returncode == 0, (
        f"the later sandbox run failed. exit={absent.returncode} text={later!r}"
    )
    assert "ABSENT" in (absent.stdout or ""), (
        f"the later session did not report the plant missing: {later!r}"
    )
    leaks = findings(later)
    assert leaks == [], (
        "a value written in the first session's environment was readable "
        f"from the later session's: {leaks}"
    )
    assert not (second / PLANT_NAME).exists()
    assert (first / PLANT_NAME).is_file(), (
        "the first scratch was cleaned up; the arm is vacuous"
    )


def test_the_residual_is_recorded() -> None:
    record_evidence("sc024-environment-not-inherited", {
        "criterion": "SC-024",
        "task": "T167",
        "what_this_establishes": [
            "In-process: SessionEnvironments isolation holds without "
            "destroy(); create() still refuses reuse. "
            "tests/unit/test_session_env.py still fires, including the "
            "SIGKILL / no-destroy arm.",
            "Live (when the sandbox image is loaded): two sequential "
            "docker run --rm binds, a planted file in the first scratch, "
            "absent from the second. Skip names the Docker daemon or the "
            "unloaded image.",
        ],
        "what_this_does_not": [
            "T166 env / proc / declared-mount readability.",
            "T215 / a serve loop inside the sandbox.",
            "T111 replay / recording arms.",
        ],
    })
