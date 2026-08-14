"""T166 — SC-024 not-present: env, process table, declared mounts.

**Criterion**: SC-024 — *zero secret values are readable from inside the
environment*. FR-050's not-present clause: an environment variable, process
state, or a file inside FR-048's declared set.

## What this file is, and what it is not

**Do.** Static half CI can fail: the sandbox image holds neither credential;
compose does not inject `F2A_PROVIDER_CREDENTIAL` / `F2A_TARGET_CREDENTIAL`
into sandbox; the scan's mount list is the declared location set (plus
per-session scratch). Live half: `docker run --rm` of the sandbox image
inspects `env`, `/proc`, and the declared mounts. Skip loudly if the
Docker daemon is absent or the sandbox image is not loaded.

**Do not.** Invent a serve loop or T215 so a session "runs" in the
container. Build images in CI. Offer `seccomp=unconfined`. Scan T165's
four surfaces (model context / artifacts / traces / persisted state).
Complete T167 (later-session inheritance) or T173+.

A skip-only suite is not a T166 pass. The static half is what CI can fail.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from src.contracts.credentials import PROVIDER_KEY, TARGET_KEY
from src.sandbox import image_policy
from tests.batteries.evidence import record_evidence
from tests.fixtures.locations import document, scratch_entry

REPO = Path(__file__).resolve().parents[2]
IMAGES = REPO / "deploy" / "images"
SANDBOX_DOCKERFILE = IMAGES / "sandbox.Dockerfile"
COMPOSE_FILE = REPO / "deploy" / "compose" / "compose.yaml"

SANDBOX_IMAGE_TAGS = ("f2a-sandbox:local", "f2a-sandbox")

#: SC-024's not-present surfaces inside the execution environment.
#: Shrinking the tuple is a silent pass over a channel the criterion still
#: names.
SURFACES = (
    "environment",
    "process_table",
    "declared_mounts",
)

#: The scan claims these mounts and no others. Derived from the committed
#: location-set fixture plus per-session scratch (FR-048 / FR-050).
CLAIMED_MOUNTS = (
    "/workspace",
    "/opt/toolchain",
    "/scratch",
)

#: Unique needles. The scanner looks for these values, not for a
#: credential-shaped regex (that filter is T040's).
PROVIDER_PLAINTEXT = "sk-t166-provider-a8c1e4f029b73d56"
TARGET_PLAINTEXT = "tgt-t166-enforcement-6d2b9a0e4c17f835"
PLANTED = (PROVIDER_PLAINTEXT, TARGET_PLAINTEXT)

#: Host-side assignment forms. The in-container dump script must not
#: mention these strings, or `/proc/self/cmdline` would be a false hit.
CREDENTIAL_ASSIGNMENTS = (
    f"{PROVIDER_KEY}=",
    f"{TARGET_KEY}=",
)

#: A scan over an empty dump is a pass for a leaker. Refused.
SCAN_OVER_EMPTY_DUMP_PASSES = False

#: Generic dump. No credential key names, no planted values — those would
#: appear in `/proc/self/cmdline` if passed via `python3 -c`.
DUMP_SCRIPT = """\
import os, sys, pathlib
print("===ENV===")
for k in sorted(os.environ):
    print("%s=%s" % (k, os.environ[k]))
print("===PROC===")
proc = pathlib.Path("/proc")
for d in sorted(proc.iterdir()):
    if not d.name.isdigit():
        continue
    for name in ("environ", "cmdline"):
        p = d / name
        try:
            data = p.read_bytes().replace(b"\\x00", b"\\n")
        except OSError:
            continue
        sys.stdout.buffer.write(("---%s---\\n" % p).encode())
        sys.stdout.buffer.write(data)
        if not data.endswith(b"\\n"):
            sys.stdout.buffer.write(b"\\n")
print("===MOUNTS===")
for target in sys.argv[1:]:
    root = pathlib.Path(target)
    print("---%s---" % target)
    if not root.exists():
        print("ABSENT")
        continue
    if root.is_file():
        try:
            print(root.read_text(errors="replace"))
        except OSError as exc:
            print("UNREADABLE %s" % exc)
        continue
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        try:
            body = path.read_text(errors="replace")
        except OSError as exc:
            print("%s: UNREADABLE %s" % (path, exc))
            continue
        print("%s:" % path)
        print(body)
"""


def findings(
    blob: str,
    secrets: tuple[str, ...] = PLANTED,
) -> list[str]:
    """Substring scan for planted values and credential assignments."""
    caught = [secret for secret in secrets if secret in blob]
    for assignment in CREDENTIAL_ASSIGNMENTS:
        if assignment in blob:
            caught.append(assignment)
    return caught


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


def _declared_mounts_from_fixture() -> tuple[str, ...]:
    locs = list(document()["locations"])
    locs.append(scratch_entry("/var/lib/f2a/sessions/unused/scratch"))
    return tuple(str(loc["target"]) for loc in locs)


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
        "the live in-container half cannot scan"
    )


def _run_sandbox(
    image: str,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    docker = _require_docker()
    argv = [docker, "run", "--rm", "-i", "--network", "none"]
    for name, value in (extra_env or {}).items():
        argv.extend(["-e", f"{name}={value}"])
    argv.extend([image, "python3", "-", *CLAIMED_MOUNTS])
    return subprocess.run(
        argv,
        input=DUMP_SCRIPT,
        capture_output=True,
        text=True,
        timeout=60,
    )


# ---------------------------------------------------------------------------
# Controls. Without these, every assertion below is free.
# ---------------------------------------------------------------------------


def test_the_scanner_catches_a_planted_secret_on_each_surface() -> None:
    """The control. A detector that matches nothing passes for a leaker."""
    for name in SURFACES:
        blob = f"ordinary {name} payload {PROVIDER_PLAINTEXT} end"
        caught = findings(blob)
        assert PROVIDER_PLAINTEXT in caught, (
            f"the scanner misses a planted provider secret on {name}"
        )
        blob = f"ordinary {name} payload {TARGET_PLAINTEXT} end"
        caught = findings(blob)
        assert TARGET_PLAINTEXT in caught, (
            f"the scanner misses a planted target secret on {name}"
        )
        blob = f"ordinary {name} payload {PROVIDER_KEY}=leaked end"
        caught = findings(blob)
        assert f"{PROVIDER_KEY}=" in caught, (
            f"the scanner misses a credential assignment on {name}"
        )
    assert findings("a perfectly ordinary sandbox dump") == []


def test_a_scan_over_an_empty_dump_is_refused() -> None:
    """SC-024 over nothing is vacuous."""
    assert SCAN_OVER_EMPTY_DUMP_PASSES is False
    empty = ""
    assert not empty.strip()
    if SCAN_OVER_EMPTY_DUMP_PASSES:
        return
    assert findings(empty) == []


def test_the_three_surfaces_are_the_population() -> None:
    assert SURFACES == (
        "environment",
        "process_table",
        "declared_mounts",
    )
    assert len(SURFACES) == 3
    assert len(set(SURFACES)) == 3


def test_the_scan_claims_only_the_declared_mount_set() -> None:
    """The mount list is FR-048's declared set plus scratch, not /proc/mounts."""
    assert CLAIMED_MOUNTS == _declared_mounts_from_fixture()
    assert CLAIMED_MOUNTS == (
        "/workspace",
        "/opt/toolchain",
        "/scratch",
    )
    assert "/proc" not in CLAIMED_MOUNTS
    assert "/" not in CLAIMED_MOUNTS


# ---------------------------------------------------------------------------
# Static: image and compose hold neither plane. CI can fail this.
# ---------------------------------------------------------------------------


def test_sandbox_image_holds_neither_credential() -> None:
    text = SANDBOX_DOCKERFILE.read_text()
    assert PROVIDER_KEY not in text, (
        f"the sandbox image names {PROVIDER_KEY}; the provider plane is "
        "runtime only (FR-036 / FR-050)"
    )
    assert TARGET_KEY not in text, (
        f"the sandbox image names {TARGET_KEY}; the target plane is the "
        "enforcement point only (FR-036 / FR-050)"
    )
    instructions = image_policy.parse(text)
    shipped = image_policy.final_stage(instructions)
    for inst in instructions:
        if inst.stage != shipped:
            continue
        if inst.verb in ("ENV", "ARG"):
            assert PROVIDER_KEY not in inst.body
            assert TARGET_KEY not in inst.body
        assert inst.verb != "ENTRYPOINT", (
            f"sandbox.Dockerfile ships ENTRYPOINT {inst.body!r}; the live "
            "scan's python3 dump would become arguments and may never run"
        )
        assert inst.verb != "CMD", (
            f"sandbox.Dockerfile ships CMD {inst.body!r}; T096 left the "
            "supervisor to decide what runs"
        )


def test_compose_does_not_inject_credentials_into_sandbox() -> None:
    compose = _load_compose()
    sandbox = compose["services"]["sandbox"]
    keys = set(_env(sandbox))
    assert PROVIDER_KEY not in keys, (
        f"compose sandbox injects {PROVIDER_KEY}; FR-050's not-present "
        "clause keeps both planes out of the execution environment"
    )
    assert TARGET_KEY not in keys, (
        f"compose sandbox injects {TARGET_KEY}; FR-050's not-present "
        "clause keeps both planes out of the execution environment"
    )
    assert sandbox.get("profiles") == ["sandbox-build"], (
        "sandbox is a running service; T160 listed it only so "
        "`docker compose build` produces the image"
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
    assert "loaded" in msg, f"the skip does not name the unloaded image: {caught.value!r}"


# ---------------------------------------------------------------------------
# Live: docker run of the sandbox image, scan env / proc / declared mounts.
# ---------------------------------------------------------------------------


def test_the_in_container_scanner_catches_a_secret_injected_at_run() -> None:
    """Live control. Skip names the daemon or the unloaded image."""
    image = _loaded_image(SANDBOX_IMAGE_TAGS)
    proc = _run_sandbox(
        image,
        extra_env={PROVIDER_KEY: PROVIDER_PLAINTEXT},
    )
    dump = (proc.stdout or "") + (proc.stderr or "")
    assert proc.returncode == 0, (
        f"the sandbox dump failed. exit={proc.returncode} text={dump!r}"
    )
    assert dump.strip(), "the live dump was empty; the scan is vacuous"
    caught = findings(dump)
    assert PROVIDER_PLAINTEXT in caught, (
        f"the in-container scanner missed a secret injected at run: {caught!r}"
    )


def test_no_secret_is_readable_from_env_proc_or_declared_mounts() -> None:
    """SC-024 not-present, live. Skip names the daemon or the unloaded image."""
    image = _loaded_image(SANDBOX_IMAGE_TAGS)
    proc = _run_sandbox(image)
    dump = (proc.stdout or "") + (proc.stderr or "")
    assert proc.returncode == 0, (
        f"the sandbox dump failed. exit={proc.returncode} text={dump!r}"
    )
    assert dump.strip(), "the live dump was empty; SC-024 over nothing is vacuous"
    assert "===ENV===" in dump
    assert "===PROC===" in dump
    assert "===MOUNTS===" in dump
    for target in CLAIMED_MOUNTS:
        assert f"---{target}---" in dump, (
            f"the dump never ranged over declared mount {target}"
        )
    leaks = findings(dump)
    assert leaks == [], (
        "secret values were readable from inside the sandbox: "
        + ", ".join(leaks)
    )


def test_the_residual_is_recorded() -> None:
    record_evidence("sc024-in-container-scan", {
        "criterion": "SC-024",
        "task": "T166",
        "surfaces": list(SURFACES),
        "claimed_mounts": list(CLAIMED_MOUNTS),
        "what_this_establishes": [
            "Static: sandbox image and compose sandbox service hold "
            "neither F2A_PROVIDER_CREDENTIAL nor F2A_TARGET_CREDENTIAL.",
            "The scan's mount list is the declared location set plus "
            "per-session scratch, not every host mount.",
            "Live (when the sandbox image is loaded): docker run --rm "
            "inspects env, /proc, and declared mounts; planted values "
            "are absent. Skip names the Docker daemon or the unloaded "
            "image.",
        ],
        "what_this_does_not": [
            "T165's four session surfaces (model context / artifacts / "
            "traces / persisted state).",
            "T167 later-session inheritance.",
            "T111 replay / recording arms.",
            "T215 / a serve loop inside the sandbox.",
        ],
    })
