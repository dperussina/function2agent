"""T171 — fail-loud startup through the shipped bundle (FR-033).

T211 (`tests/contract/test_startup_entry_points.py`) exercises the path
**in-process**. This is the other half: the images T159 built, with the
environment T160's compose file supplies, refuse in a container the same
way they refuse on a developer's host.

CI has no Docker daemon for `compose up`. A build smoke that passed over a
missing daemon is the vacuity this corpus refuses. So this file is two
halves, and a skip-only suite is not a T171 pass:

1. **Static, planted.** The images' CMD actually invoke
   `python -m src.runtime.main` and `python -m src.supervisor.main`; compose
   supplies the no-default keys those modules read as `${KEY:?required}`;
   unsetting a named key is still the path those images run. CI can fail
   this half.
2. **Live container.** `docker run` of one image with a named key missing,
   quoting the key and a distinctive fragment of its `no_default_reason`.
   **Skip loudly** if the Docker daemon is absent (the reason names the
   daemon) or the image is not loaded. Exit status alone cannot tell an
   unset ceiling from a missing interpreter; a container makes the second
   more likely rather than less.

Analysis has **no** `def main`. It is not a third fail-loud entry point.
If this file covers analysis, the claim is the unset-`F2A_ANALYSIS_ENTRY`
refusal already in the image, not a serve loop (OD-36).

Linux only, no degraded mode (OD-17). T215 / a serve loop is not this
task. T172's compose tripwire stays retargeted:
`test_compose_bundle_does_not_offer_unconfined_or_a_degraded_sandbox`.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from src.contracts import config as cfg
from src.contracts.credentials import PROVIDER_KEY, TARGET_KEY
from src.sandbox import image_policy

REPO = Path(__file__).resolve().parents[2]
IMAGES = REPO / "deploy" / "images"
COMPOSE_FILE = REPO / "deploy" / "compose" / "compose.yaml"

RUNTIME_IMAGE_TAGS = ("f2a-runtime:local", "f2a-runtime")
SUPERVISOR_IMAGE_TAGS = ("f2a-supervisor:local", "f2a-supervisor")
ANALYSIS_IMAGE_TAGS = ("f2a-analysis:local", "f2a-analysis")

RUNTIME_CMD = '["python", "-m", "src.runtime.main"]'
SUPERVISOR_CMD = '["python", "-m", "src.supervisor.main"]'

#: Same values as `tests/contract/test_startup_entry_points.py`, so a
#: through-the-bundle refusal is asked the same question the in-process
#: suite already quotes. Do not invent a second schema.
SUPERVISOR_ENV = {
    "SANDBOX_MEMORY_MAX": "512Mi",
    "SANDBOX_CPU_MAX": "200000 100000",
    "SANDBOX_CPU_TOTAL": "120.0",
    "SANDBOX_PIDS_MAX": "64",
    "SESSION_CEILING_SPEND_USD": "5.00",
    "SESSION_CEILING_TOKENS": "200000",
    "SESSION_CEILING_WALL_CLOCK_SECONDS": "900",
    "SESSION_CEILING_TURNS": "40",
    "F2A_LOCATION_SET": "/etc/f2a/locations.json",
    "F2A_TENANT_ID": "t-1",
    "F2A_DEPLOYMENT_ID": "d-1",
    "F2A_STATE_DIR": "/tmp/f2a-t171",
}

RUNTIME_ENV = {
    "SESSION_CEILING_SPEND_USD": "5.00",
    "SESSION_CEILING_TOKENS": "200000",
    "SESSION_CEILING_WALL_CLOCK_SECONDS": "900",
    "SESSION_CEILING_TURNS": "40",
    "TOOL_RESULT_BOUND_TOKENS": "8000",
    "MODEL_CONTEXT_WINDOW_TOKENS": "200000",
    "RESULT_RETENTION_MAX_BYTES": "64MiB",
    "MODEL_PROVIDER": "anthropic",
    "MODEL_ID": "claude-sonnet-4-5-20250929",
    "MODEL_PRICES_OPERATOR": "none",
    "F2A_PROVIDER_CREDENTIAL": "sk-test-provider-credential-t171",
    "REPORTING_WINDOW_SECONDS": "3600",
    "F2A_TENANT_ID": "t-1",
    "F2A_DEPLOYMENT_ID": "d-1",
    "F2A_STATE_DIR": "/tmp/f2a-t171",
}

SUPERVISOR_REASON_KEYS = tuple(
    k for k in cfg.SUPERVISOR_KEYS if k.no_default_reason
)
RUNTIME_REASON_KEYS = tuple(
    k for k in cfg.RUNTIME_KEYS if k.no_default_reason
)


def _load_compose() -> dict:
    loaded = yaml.safe_load(COMPOSE_FILE.read_text())
    assert isinstance(loaded, dict)
    return loaded


def _env(service: dict) -> dict[str, str]:
    raw = service.get("environment") or {}
    if isinstance(raw, list):
        out: dict[str, str] = {}
        for item in raw:
            key, _, value = str(item).partition("=")
            out[key] = value
        return out
    return {str(k): str(v) for k, v in raw.items()}


def _shipped_cmd(dockerfile: Path) -> tuple[str | None, str | None]:
    """ENTRYPOINT body and CMD body of the shipped stage, or None."""
    instructions = image_policy.parse(dockerfile.read_text())
    shipped = image_policy.final_stage(instructions)
    entry: str | None = None
    cmd: str | None = None
    for inst in instructions:
        if inst.stage != shipped:
            continue
        if inst.verb == "ENTRYPOINT":
            entry = inst.body
        elif inst.verb == "CMD":
            cmd = inst.body
    return entry, cmd


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
        "the live container half cannot quote the reason text"
    )


def _run_image(image: str, env: dict[str, str],
               missing: str | None) -> subprocess.CompletedProcess[str]:
    docker = _require_docker()
    argv = [docker, "run", "--rm", "--network", "none"]
    for name, value in env.items():
        if name == missing:
            continue
        argv.extend(["-e", f"{name}={value}"])
    argv.append(image)
    return subprocess.run(
        argv,
        capture_output=True,
        text=True,
        timeout=90,
    )


# ---------------------------------------------------------------------------
# 1. Static: the images invoke the modules, compose supplies the keys.
# ---------------------------------------------------------------------------


def test_the_runtime_image_invokes_runtime_main() -> None:
    """The command T171 writes the live half against.

    An ENTRYPOINT of `true` (or a CMD that is not this module) would make
    unsetting a named key a no-op: the process that quotes the reason
    never starts.
    """
    path = IMAGES / "runtime.Dockerfile"
    entry, cmd = _shipped_cmd(path)
    assert entry is None, (
        f"runtime.Dockerfile ships ENTRYPOINT {entry!r}; CMD then becomes "
        "arguments and python -m src.runtime.main may never run"
    )
    assert cmd == RUNTIME_CMD, (
        f"runtime.Dockerfile CMD is {cmd!r}, not {RUNTIME_CMD}. T171's "
        "live half quotes a reason that only this module emits."
    )


def test_the_supervisor_image_invokes_supervisor_main() -> None:
    path = IMAGES / "supervisor.Dockerfile"
    entry, cmd = _shipped_cmd(path)
    assert entry is None, (
        f"supervisor.Dockerfile ships ENTRYPOINT {entry!r}; CMD then "
        "becomes arguments and python -m src.supervisor.main may never run"
    )
    assert cmd == SUPERVISOR_CMD, (
        f"supervisor.Dockerfile CMD is {cmd!r}, not {SUPERVISOR_CMD}"
    )


def test_the_analysis_image_is_not_a_third_fail_loud_main() -> None:
    """Analysis has no def main. The image refuses on unset F2A_ANALYSIS_ENTRY.

    Not a serve loop (OD-36). T159 walks `src/analysis/` for `def main`;
    this asserts the image's own unset-entry path, which is the only
    analysis claim T171 is allowed to make.
    """
    path = IMAGES / "analysis.Dockerfile"
    entry, cmd = _shipped_cmd(path)
    assert entry is None
    assert cmd is not None
    assert "src.analysis.main" not in cmd
    assert "F2A_ANALYSIS_ENTRY" in cmd
    assert "-z" in cmd, (
        "the analysis CMD no longer tests that F2A_ANALYSIS_ENTRY is "
        "unset; an empty exec is not a fail-loud refusal"
    )
    assert "no process to start" in cmd
    text = path.read_text()
    assert "F2A_ANALYSIS_ENTRY=" in text


def test_compose_supplies_no_default_keys_as_required_substitutions() -> None:
    """Unsetting a named key is still the path those images run.

    Compose interpolates `${KEY:?required}` for every no-default key the
    two modules read. A `:-` default, or a dropped key, would start the
    container with an invented value (or without the variable) and the
    image CMD would no longer be asked the question T211 already quotes.
    """
    compose = _load_compose()
    supervisor_env = _env(compose["services"]["supervisor"])
    runtime_env = _env(compose["services"]["runtime"])
    for key in SUPERVISOR_REASON_KEYS:
        assert key.name in supervisor_env, (
            f"compose supervisor does not supply {key.name}, so unsetting "
            "it is not a path this bundle runs"
        )
        expected = "${" + key.name + ":?required}"
        assert supervisor_env[key.name] == expected, (
            f"compose supervisor sets {key.name}={supervisor_env[key.name]!r}; "
            "required substitution is the unset path, a default is not"
        )
    for key in RUNTIME_REASON_KEYS:
        assert key.name in runtime_env, (
            f"compose runtime does not supply {key.name}, so unsetting "
            "it is not a path this bundle runs"
        )
        expected = "${" + key.name + ":?required}"
        assert runtime_env[key.name] == expected, (
            f"compose runtime sets {key.name}={runtime_env[key.name]!r}; "
            "required substitution is the unset path, a default is not"
        )


def test_the_runtime_image_does_not_hold_the_target_credential() -> None:
    text = (IMAGES / "runtime.Dockerfile").read_text()
    assert TARGET_KEY not in text, (
        f"the runtime image names {TARGET_KEY}; the target plane is the "
        "enforcement point only (FR-036)"
    )
    runtime_env = _env(_load_compose()["services"]["runtime"])
    assert TARGET_KEY not in runtime_env


def test_supervisor_analysis_and_sandbox_images_do_not_hold_the_provider_credential() -> None:
    for name in ("supervisor", "analysis", "sandbox"):
        text = (IMAGES / f"{name}.Dockerfile").read_text()
        assert PROVIDER_KEY not in text, (
            f"the {name} image names {PROVIDER_KEY}; the provider plane "
            "is runtime only (FR-036)"
        )
        assert TARGET_KEY not in text, (
            f"the {name} image names {TARGET_KEY}; the target plane is "
            "the enforcement point only (FR-036)"
        )


def test_a_missing_docker_daemon_skip_names_the_daemon(monkeypatch) -> None:
    """The live half's skip is loud, and CI can fail this.

    A skip that says only "cannot run" does not name the daemon. A
    helper that returns a path instead of skipping would make `docker
    run` raise and look like a product failure.
    """
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    with pytest.raises(pytest.skip.Exception) as caught:
        _require_docker()
    assert "daemon" in str(caught.value).lower(), (
        f"the skip does not name the daemon: {caught.value!r}"
    )


# ---------------------------------------------------------------------------
# 2. Live: docker run of one image, content assertion on the reason text.
# ---------------------------------------------------------------------------


def _quote(proc: subprocess.CompletedProcess[str], key: cfg.Key) -> None:
    """Content, not exit status alone. Same discipline as T211."""
    combined = (proc.stdout or "") + (proc.stderr or "")
    assert key.name in combined, (
        f"the container report does not name {key.name}. "
        f"exit={proc.returncode} stdout={proc.stdout!r} "
        f"stderr={proc.stderr!r}"
    )
    assert key.no_default_reason is not None
    assert key.no_default_reason in combined, (
        f"{key.name} is named but its no-default reason is not quoted, "
        "so the operator is told to set a value without being told it "
        "is unsafe to guess one. "
        f"exit={proc.returncode} text={combined!r}"
    )
    assert "Nothing has been started" in combined
    assert proc.returncode != 0


@pytest.mark.parametrize(
    "key", SUPERVISOR_REASON_KEYS, ids=lambda k: k.name)
def test_the_supervisor_container_quotes_each_reason_back(key: cfg.Key) -> None:
    image = _loaded_image(SUPERVISOR_IMAGE_TAGS)
    proc = _run_image(image, SUPERVISOR_ENV, missing=key.name)
    _quote(proc, key)


@pytest.mark.parametrize(
    "key", RUNTIME_REASON_KEYS, ids=lambda k: k.name)
def test_the_runtime_container_quotes_each_reason_back(key: cfg.Key) -> None:
    image = _loaded_image(RUNTIME_IMAGE_TAGS)
    proc = _run_image(image, RUNTIME_ENV, missing=key.name)
    _quote(proc, key)
    assert "sk-test-provider-credential-t171" not in (
        (proc.stdout or "") + (proc.stderr or "")
    ), "the provider credential reached the refusal report (FR-036)"


def test_the_analysis_container_refuses_an_unset_entry() -> None:
    """Not a third main: the image's own unset-F2A_ANALYSIS_ENTRY refusal."""
    image = _loaded_image(ANALYSIS_IMAGE_TAGS)
    proc = _run_image(image, {}, missing=None)
    combined = (proc.stdout or "") + (proc.stderr or "")
    assert "F2A_ANALYSIS_ENTRY" in combined, (
        f"the analysis container did not name F2A_ANALYSIS_ENTRY. "
        f"exit={proc.returncode} text={combined!r}"
    )
    assert "no process to start" in combined
    assert "src/analysis/ has no def main" in combined
    assert proc.returncode != 0
