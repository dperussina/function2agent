"""T160 — the compose bundle: topology, credentials, seccomp, session-store order.

Static. CI has no Docker daemon for `compose up`; these tests read files.
A build smoke that passed over a missing daemon would be the vacuity this
corpus refuses. T171 exercises fail-loud *through* the bundle; this file
does not.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from src.contracts.credentials import PROVIDER_KEY, TARGET_KEY
from src.contracts.topology import (
    ANALYSIS_ADDR_KEY,
    RUNTIME_ADDR_KEY,
    TARGET_ADDR_KEY,
)

REPO = Path(__file__).resolve().parents[2]
COMPOSE_DIR = REPO / "deploy" / "compose"
COMPOSE_FILE = COMPOSE_DIR / "compose.yaml"
PROFILE = COMPOSE_DIR / "seccomp" / "session.json"

#: Finding 024's eight names — the appended unconditional allow rule.
#: `unshare` was already among the 426, inside the CAP_SYS_ADMIN-gated
#: rule; a profile built to the count 427 that still gates it refuses.
#: pivot_root is the added name (in no default-profile rule).
FINDING_024_EIGHT = (
    "unshare",
    "mount",
    "umount2",
    "pivot_root",
    "setns",
    "mount_setattr",
    "move_mount",
    "open_tree",
)

PRODUCT_SERVICES = ("analysis", "runtime", "supervisor", "enforcement")
SANDBOX_SERVICE = "sandbox"

PROVIDER_HOLDERS = frozenset({"runtime"})
TARGET_HOLDERS = frozenset({"enforcement"})
LISTEN_HOLDERS = frozenset({"enforcement"})
NEVER_CREDENTIAL = frozenset({"analysis", "supervisor", "sandbox"})


def _load_compose() -> dict:
    assert COMPOSE_FILE.is_file(), "T160 owes deploy/compose/compose.yaml"
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


def _bundle_text() -> str:
    parts: list[str] = []
    for path in sorted(COMPOSE_DIR.rglob("*")):
        if path.is_file():
            parts.append(path.read_text())
    return "\n".join(parts)


def test_the_compose_bundle_names_four_product_images_and_the_sandbox() -> None:
    compose = _load_compose()
    services = compose["services"]
    for name in (*PRODUCT_SERVICES, SANDBOX_SERVICE):
        assert name in services, f"compose is missing service {name}"
        build = services[name].get("build") or {}
        dockerfile = build.get("dockerfile", "")
        assert dockerfile.endswith(f"{name}.Dockerfile") or (
            name == "enforcement" and dockerfile.endswith("enforcement.Dockerfile")
        ), f"{name} does not build from deploy/images/{name}.Dockerfile: {dockerfile}"


def test_fixture_topology_is_marked_unvalidated_not_a_product_default() -> None:
    text = COMPOSE_FILE.read_text()
    assert "FR-043" in text
    assert "fixture configuration" in text
    assert "not a product default" in text.lower() or "not product defaults" in text.lower()
    assert "mealie" not in text.lower()
    compose = _load_compose()
    runtime_env = _env(compose["services"]["runtime"])
    assert runtime_env[ANALYSIS_ADDR_KEY] == "analysis:8080"
    assert runtime_env[RUNTIME_ADDR_KEY] == "runtime:8081"
    assert runtime_env[TARGET_ADDR_KEY] == "target:9000"


def test_credentials_sit_on_the_right_services_only() -> None:
    compose = _load_compose()
    services = compose["services"]
    for name, spec in services.items():
        keys = set(_env(spec))
        if name in PROVIDER_HOLDERS:
            assert PROVIDER_KEY in keys, f"{name} must hold {PROVIDER_KEY}"
        else:
            assert PROVIDER_KEY not in keys, (
                f"{name} holds {PROVIDER_KEY}; the provider plane is runtime only"
            )
        if name in TARGET_HOLDERS:
            assert TARGET_KEY in keys
            assert "F2A_TARGET_CREDENTIAL_HEADER" in keys
        else:
            assert TARGET_KEY not in keys, (
                f"{name} holds {TARGET_KEY}; the target plane is the "
                "enforcement point only"
            )
            assert "F2A_TARGET_CREDENTIAL_HEADER" not in keys
        if name in LISTEN_HOLDERS:
            assert "F2A_PROXY_LISTEN" in keys
        else:
            assert "F2A_PROXY_LISTEN" not in keys, (
                f"{name} sets F2A_PROXY_LISTEN; that is a Go env on the "
                "enforcement point only"
            )
        if name in NEVER_CREDENTIAL:
            assert PROVIDER_KEY not in keys
            assert TARGET_KEY not in keys
    assert "ANTHROPIC_API_KEY" not in _bundle_text()
    assert "OPENAI_API_KEY" not in _bundle_text()


def test_supervisor_alone_gets_the_cgroup_mount_and_the_seccomp_profile() -> None:
    compose = _load_compose()
    supervisor = compose["services"]["supervisor"]
    assert supervisor.get("cgroup") == "host"
    mounts = supervisor.get("volumes") or []
    cgroup = [
        m for m in mounts
        if isinstance(m, dict) and m.get("target") == "/sys/fs/cgroup"
    ]
    assert cgroup, "supervisor must bind /sys/fs/cgroup"
    assert cgroup[0].get("read_only") is False
    opts = supervisor.get("security_opt") or []
    assert any(
        str(opt).startswith("seccomp=") and str(opt).endswith("session.json")
        for opt in opts
    ), f"supervisor security_opt does not reference the shipped profile: {opts}"
    text = COMPOSE_FILE.read_text()
    assert "entire cgroup tree" in text
    assert "delegated subtree" in text
    for name, spec in compose["services"].items():
        if name == "supervisor":
            continue
        assert spec.get("cgroup") != "host", (
            f"{name} takes host cgroupns; FR-049 is the supervisor's mount"
        )
        other_opts = spec.get("security_opt") or []
        assert other_opts == [], f"{name} carries security_opt {other_opts}"


def test_the_session_store_is_created_before_any_second_process_attaches() -> None:
    """Finding 033 first limb, checkable.

    T016's migration is closed (`session_table.py` sits on Repository). This
    is the other limb: compose must not start supervisor and a second
    process against a missing store concurrently.
    """
    compose = _load_compose()
    for name in ("runtime", "enforcement"):
        depends = compose["services"][name].get("depends_on")
        assert isinstance(depends, dict), (
            f"{name} depends_on is {depends!r}; the dict form with "
            "service_completed_successfully is what serialises first-open"
        )
        assert depends.get("supervisor", {}).get("condition") == (
            "service_completed_successfully"
        ), (
            f"{name} does not wait for supervisor to finish opening the "
            f"store: {depends}"
        )
    supervisor_depends = compose["services"]["supervisor"].get("depends_on")
    assert not supervisor_depends, (
        "supervisor is the first opener; it must not wait on a peer that "
        f"also opens the store: {supervisor_depends}"
    )


def test_finding_024_profile_exposes_the_eight_names_without_the_capability_gate() -> None:
    import json

    assert PROFILE.is_file(), "T160 owes deploy/compose/seccomp/session.json"
    profile = json.loads(PROFILE.read_text())
    assert profile["defaultAction"] == "SCMP_ACT_ERRNO"
    eight = set(FINDING_024_EIGHT)
    matching = [
        rule for rule in profile["syscalls"]
        if rule.get("action") == "SCMP_ACT_ALLOW"
        and not rule.get("includes")
        and eight <= set(rule.get("names") or [])
    ]
    assert matching, (
        "session.json has no unconditional SCMP_ACT_ALLOW covering finding "
        "024's eight names. A 427-count profile that still gates unshare on "
        "CAP_SYS_ADMIN refuses."
    )
    assert "pivot_root" in matching[0]["names"]
    denied_in_default = ("keyctl", "add_key", "userfaultfd", "kexec_load", "swapon")
    allowed_names: set[str] = set()
    for rule in profile["syscalls"]:
        if rule.get("action") == "SCMP_ACT_ALLOW":
            allowed_names.update(rule.get("names") or [])
    for name in denied_in_default:
        assert name not in allowed_names, (
            f"{name} is allow-listed; finding 024 keeps it denied"
        )


def test_finding_024_clone_argument_mask_is_removed() -> None:
    import json

    profile = json.loads(PROFILE.read_text())
    clone_rules = [
        rule for rule in profile["syscalls"]
        if rule.get("names") == ["clone"]
        and "CAP_SYS_ADMIN" in (rule.get("excludes") or {}).get("caps", [])
    ]
    assert clone_rules, "the non-CAP_SYS_ADMIN clone rule is gone"
    for rule in clone_rules:
        assert "args" not in rule, (
            "the non-CAP_SYS_ADMIN clone rule still carries an argument "
            "mask, so namespace flags do not pass (finding 024)"
        )


def test_the_bundle_does_not_contain_unconfined_or_a_degraded_sandbox() -> None:
    """T172 tripwire, retargeted. Absence of compose files is no longer the fail.

    A later edit that offers the whole filter, or a degraded sandbox, must
    still fail. The string is matched in comments too: an offered alternative
    in a comment is an offer.
    """
    text = _bundle_text()
    assert "unconfined" not in text.lower(), (
        "the compose bundle names unconfined. Finding 024: that is not the "
        "operator's choice. The shipped profile is."
    )
    collapsed = " ".join(text.split())
    assert "degraded sandbox" not in collapsed.lower()
    assert "best-effort sandbox" not in collapsed.lower()
    assert "Linux only" in COMPOSE_FILE.read_text()
    assert "no degraded mode" in COMPOSE_FILE.read_text()
