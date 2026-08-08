"""T096 — the sandbox image ships resolved, holds no secret, and can reach no index.

**Requirement**: FR-021.

## What this file is not

It is **not** a second enforcement of the egress policy. `research.md` §T-11 and
`contracts/egress-policy.md` both record that FR-021 and the egress policy are
one control: resolving a dependency at run time is an outbound request to a
destination that is not the target, so the enforcement point already denies it.
Nothing here denies anything. Nothing here opens a socket, and one test below
exists specifically to fail if a future edit makes it try.

What this file checks is the *other* proposition in FR-021 — that the image
**ships** with its dependencies already resolved. The egress policy governs the
request; this governs what was shipped. An image with `pip`, an index URL and a
`.netrc` in it satisfies the deny rule and still fails FR-021's first clause,
and no amount of egress enforcement would notice.

## Why a static reading, and why it is not the only mechanism

CI builds no images. So the `RUN` block at the end of `sandbox.Dockerfile`,
which fails the build when a package manager survives, runs only where someone
builds — which today is a laptop. The static checker is what makes the property
hold in CI. The two are not redundant: the build assertion catches a package
manager arriving from a **base image change**, which alters no line of the
Dockerfile and is therefore invisible to a static reading;
`test_the_image_asserts_its_own_properties_at_build_time` is what keeps that
half from being deleted.

## The floor

A scanner that finds nothing is indistinguishable from a scanner that looks in
the wrong place. Every rule below is therefore paired with a **synthetic**
Dockerfile that violates it, and the test asserts the rule fires on it. The
fixtures are constructed here rather than lifted from a real image on purpose:
a fixture assembled beside the rule it scores is contaminated and cannot score
it.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from src.sandbox import image_policy
from src.sandbox.image_policy import (
    SBX_IMG_001,
    SBX_IMG_002,
    SBX_IMG_003,
    SBX_IMG_004,
    SBX_IMG_005,
    SBX_IMG_006,
    check,
    check_path,
)

REPO = Path(__file__).resolve().parents[2]
SANDBOX = REPO / "deploy" / "images" / "sandbox.Dockerfile"

#: A minimal image that satisfies every rule. Each planted defect below is this
#: text plus one violation, so a fired rule is attributable to the change and
#: not to whatever else a realistic Dockerfile happens to contain.
CLEAN = """
FROM python:3.12-slim-bookworm AS builder
COPY requirements.lock /tmp/requirements.lock
RUN pip install --require-hashes --prefix=/opt/deps -r /tmp/requirements.lock

FROM python:3.12-slim-bookworm AS sandbox
COPY --from=builder /opt/deps /usr/local
RUN rm -rf /usr/local/bin/pip /usr/bin/apt-get
RUN set -eu; \\
    [ ! -e /usr/bin/apt-get ] || { echo "SBX-IMG: apt survived"; exit 1; }
USER 10001
"""


def _rules(text: str) -> set[str]:
    return {f.rule_id for f in check(text)}


# ---------------------------------------------------------------------------
# The committed image.


def test_the_sandbox_image_exists() -> None:
    assert SANDBOX.exists(), (
        "T096's artifact is missing, so every assertion below would be a "
        "scanner reporting no findings over no input"
    )


def test_the_committed_sandbox_image_has_no_findings() -> None:
    findings = check_path(SANDBOX)
    assert not findings, "\n".join(str(f) for f in findings)


def test_the_image_ships_a_shell_and_a_toolchain() -> None:
    """T096's first clause, which the rules above do not cover.

    Every rule in `image_policy` is a prohibition. An empty Dockerfile passes
    all of them, and an empty Dockerfile is not a sandbox image.
    """
    text = SANDBOX.read_text()
    assert "util-linux" in text and "procps" in text
    assert "/bin/bash" in text


def test_the_image_asserts_its_own_properties_at_build_time() -> None:
    """The half that survives a base image changing under the file.

    A static reading of a Dockerfile cannot see a package manager that arrived
    because `python:3.12-slim-bookworm` started shipping one. The build-time
    `RUN` can, and this is what stops it being deleted as redundant.
    """
    text = SANDBOX.read_text()
    assert "SBX-IMG" in text and "exit 1" in text
    for probe in ("/usr/local/bin/pip", "/usr/bin/apt-get", "/root/.netrc"):
        assert probe in text, f"the build-time assertion does not probe {probe}"


def test_the_build_assertion_does_not_reach_a_network() -> None:
    """The line this task is most likely to be crossed at.

    A build step that curls an index to prove it is unreachable would be the
    second mechanism §T-11 warns against, and it would make the build's verdict
    a property of the machine that ran it rather than of the image.

    Scanned over **parsed instruction bodies**, not the file's text. The first
    version scanned the text and failed on the word "ship*ping* property" in a
    comment — a scanner matching prose is the same blindness in the opposite
    direction, and it would have been just as happy matching `curl` in a
    sentence explaining why there is no `curl`.
    """
    commands = " ".join(
        i.body for i in image_policy.parse(SANDBOX.read_text()) if i.verb == "RUN"
    )
    for reaching in ("curl", "wget", "getent", "ping", "iptables", "nslookup"):
        assert not re.search(rf"\b{reaching}\b", commands), (
            f"the sandbox image runs {reaching!r}. FR-021 and the egress "
            "policy are one control; this image's contribution is that it "
            "ships nothing to resolve with, not that it re-denies the request."
        )


def test_the_image_carries_no_entrypoint_of_its_own() -> None:
    """The supervisor decides what runs; two answers would be one too many."""
    verbs = {i.verb for i in image_policy.parse(SANDBOX.read_text())}
    assert "ENTRYPOINT" not in verbs
    assert "CMD" not in verbs


def test_the_image_drops_root() -> None:
    instructions = image_policy.parse(SANDBOX.read_text())
    users = [i for i in instructions if i.verb == "USER"]
    assert users, "the sandbox image runs as root"
    assert users[-1].body.split(":")[0] not in ("root", "0")


# ---------------------------------------------------------------------------
# The floor: every rule fires on a synthetic violation.


def test_the_clean_fixture_is_clean() -> None:
    """Without this, every planted-defect test below could pass vacuously."""
    assert not _rules(CLEAN)


def test_a_retained_package_manager_is_found() -> None:
    planted = CLEAN.replace(
        "RUN rm -rf /usr/local/bin/pip /usr/bin/apt-get",
        "RUN apt-get install -y curl-less-thing",
    )
    assert SBX_IMG_002 in _rules(planted)


def test_installing_at_build_time_and_removing_after_is_not_a_finding() -> None:
    """The distinction the first version of this rule got wrong.

    FR-021 requires resolution *at build time*. An image that installs a shell
    and then removes the manager has done exactly what the requirement asks,
    and a rule that flagged it would push the install into a builder stage —
    moving a line without changing one fact about what ships.
    """
    permitted = CLEAN.replace(
        "COPY --from=builder /opt/deps /usr/local",
        "COPY --from=builder /opt/deps /usr/local\n"
        "RUN apt-get install -y --no-install-recommends util-linux",
    )
    assert SBX_IMG_002 not in _rules(permitted)


def test_removing_before_installing_is_still_a_finding() -> None:
    """Order matters, and a rule that ignored it would be trivially satisfied.

    Otherwise a Dockerfile could carry the teardown near the top, reinstall
    below it, and pass by having both strings present somewhere.
    """
    planted = CLEAN.replace(
        "RUN rm -rf /usr/local/bin/pip /usr/bin/apt-get",
        "RUN rm -rf /usr/local/bin/pip /usr/bin/apt-get\n"
        "RUN apt-get install -y reinstated",
    )
    assert SBX_IMG_002 in _rules(planted)


def test_an_index_url_is_found() -> None:
    planted = CLEAN.replace(
        "USER 10001", "ENV PIP_INDEX_URL=https://pypi.org/simple\nUSER 10001"
    )
    assert SBX_IMG_003 in _rules(planted)


def test_an_empty_index_url_is_still_found() -> None:
    """Configuration a later edit fills in is configuration."""
    planted = CLEAN.replace("USER 10001", "ENV PIP_INDEX_URL=\nUSER 10001")
    assert SBX_IMG_003 in _rules(planted)


def test_an_index_url_in_the_builder_stage_is_not_a_finding() -> None:
    """The builder is discarded, so what it configures does not ship.

    Stated as a test because the natural over-broad implementation checks the
    whole file, and would then forbid the one stage FR-021 requires to resolve.
    """
    permitted = CLEAN.replace(
        "COPY requirements.lock /tmp/requirements.lock",
        "ENV PIP_INDEX_URL=https://internal.example/simple\n"
        "COPY requirements.lock /tmp/requirements.lock",
    )
    assert SBX_IMG_003 not in _rules(permitted)


@pytest.mark.parametrize(
    "name",
    ["NPM_TOKEN", "REGISTRY_PASSWORD", "ARTIFACTORY_API_KEY", "PROXY_AUTH"],
)
def test_a_secret_shaped_name_is_found(name: str) -> None:
    planted = CLEAN.replace("USER 10001", f"ENV {name}=whatever\nUSER 10001")
    assert SBX_IMG_004 in _rules(planted)


def test_a_build_secret_mount_is_found() -> None:
    planted = CLEAN.replace(
        "RUN rm -rf /usr/local/bin/pip /usr/bin/apt-get",
        "RUN --mount=type=secret,id=idx rm -rf /usr/local/bin/pip /usr/bin/apt-get",
    )
    assert SBX_IMG_004 in _rules(planted)


def test_a_fetch_in_the_shipped_stage_is_found() -> None:
    planted = CLEAN.replace(
        "USER 10001", "RUN curl -o /tmp/x https://example/x\nUSER 10001"
    )
    assert SBX_IMG_005 in _rules(planted)


def test_an_add_from_a_url_is_found() -> None:
    planted = CLEAN.replace("USER 10001", "ADD https://example/x.tgz /tmp/\nUSER 10001")
    assert SBX_IMG_005 in _rules(planted)


def test_an_unpinned_install_is_found() -> None:
    planted = CLEAN.replace("--require-hashes ", "")
    assert SBX_IMG_001 in _rules(planted)


def test_an_install_from_something_other_than_the_lock_file_is_found() -> None:
    planted = CLEAN.replace("-r /tmp/requirements.lock", "requests")
    assert SBX_IMG_001 in _rules(planted)


def test_a_missing_build_time_assertion_is_found() -> None:
    planted = CLEAN.replace('{ echo "SBX-IMG: apt survived"; exit 1; }', "true")
    assert SBX_IMG_006 in _rules(planted)


# ---------------------------------------------------------------------------
# The parser, at the two places a wrong answer would silently weaken a rule.


def test_a_continuation_is_one_instruction() -> None:
    """Otherwise a violation split across a backslash is invisible."""
    text = "FROM base AS s\nRUN apt-get \\\n    install -y thing\n"
    instructions = image_policy.parse(text)
    assert [i.verb for i in instructions] == ["FROM", "RUN"]
    assert "apt-get install" in " ".join(instructions[1].body.split())


def test_the_final_stage_is_the_last_from() -> None:
    text = "FROM a AS builder\nRUN pip install x\nFROM b AS ship\nUSER 1\n"
    assert image_policy.final_stage(image_policy.parse(text)) == "ship"


def test_an_unnamed_final_stage_still_resolves() -> None:
    """`FROM x AS builder` followed by a bare `FROM y` is a common shape."""
    text = "FROM a AS builder\nRUN pip install x\nFROM b\nRUN apt-get install y\n"
    findings = {f.rule_id for f in check(text)}
    assert SBX_IMG_002 in findings


def test_a_dockerfile_with_no_from_is_refused_rather_than_passed() -> None:
    with pytest.raises(ValueError, match="no FROM"):
        image_policy.final_stage(image_policy.parse("RUN echo hi\n"))
