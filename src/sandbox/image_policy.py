"""T096 — the sandbox image's FR-021 properties, checked rather than asserted.

**Requirement**: FR-021 — *the runtime MUST ship with its dependencies already
resolved and MUST NOT resolve dependencies at run time.*

## What this module is, and the mechanism it is deliberately not

`research.md` §T-11 and `contracts/egress-policy.md` both record that FR-021
and the egress policy are **one control**: resolving a dependency at run time is
an outbound request to a destination that is not the target, so the enforcement
point already denies it. Nothing here is a network control and nothing here
denies anything at run time.

This is a **static reading of a build artifact**. It answers a question the
egress policy cannot: *does the shipped image contain the means and the
configuration to resolve a dependency, and does it contain a secret?* The
egress policy governs the request; this governs what was shipped. Two different
propositions about one requirement, which is not the same as two mechanisms
enforcing one.

The alternative was a comment in the Dockerfile saying the property holds. A
comment is not checkable and rots at the first edit. The `RUN` block at the end
of `sandbox.Dockerfile` fails the build if the property stops holding; this
module reproduces the same rules statically, so CI catches a regression without
a Docker daemon — and CI builds no images today, so without it the build-time
assertion would only ever run on someone's laptop.

## Reading Dockerfiles

The parser is deliberately small: continuations joined, comments dropped,
stages tracked. It is not a Dockerfile implementation and does not need to be —
every rule below is a question about which instructions appear in which stage,
and none needs the semantics of a build.

**The `FROM` handling is the part that matters.** A rule applied to the whole
file rather than to the final stage would be wrong in both directions: it would
flag the builder stage for using `pip`, which is exactly where FR-021 requires
resolution to happen, and it would miss a package manager reinstated in the
final stage of a file whose builder looked clean.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

#: Rule identifiers, so a finding names the rule that produced it the way a
#: `filesystem_decision` or an egress denial does. A refusal that cannot say
#: which rule refused is a refusal nobody can argue with.
SBX_IMG_001 = "SBX-IMG-001"  # dependencies resolved from a hash-pinned lock file
SBX_IMG_002 = "SBX-IMG-002"  # no package manager in the shipped stage
SBX_IMG_003 = "SBX-IMG-003"  # no index configuration
SBX_IMG_004 = "SBX-IMG-004"  # no secret
SBX_IMG_005 = "SBX-IMG-005"  # no fetch in the shipped stage
SBX_IMG_006 = "SBX-IMG-006"  # the build asserts it, not only this checker


@dataclass(frozen=True)
class Instruction:
    """One logical Dockerfile instruction, continuations already joined."""

    stage: str
    verb: str
    body: str
    line: int


@dataclass(frozen=True)
class Finding:
    rule_id: str
    line: int
    reason: str

    def __str__(self) -> str:
        return f"{self.rule_id} (line {self.line}): {self.reason}"


def parse(text: str) -> list[Instruction]:
    """Join continuations, drop comments, track the stage each instruction is in.

    A stage is named by its `AS` clause when it has one and by its index when it
    does not, because an unnamed final stage is common and the rules below still
    have to be able to say which stage they are talking about.
    """
    instructions: list[Instruction] = []
    stage = "0"
    stage_index = 0
    buffer: list[str] = []
    start = 0

    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.rstrip()
        stripped = line.strip()
        if not buffer and (not stripped or stripped.startswith("#")):
            continue
        if not buffer:
            start = number
        # A comment line inside a continuation is a comment, not a fragment.
        if buffer and stripped.startswith("#"):
            continue
        if line.endswith("\\"):
            buffer.append(line[:-1])
            continue

        buffer.append(line)
        joined = " ".join(part.strip() for part in buffer).strip()
        buffer = []
        if not joined:
            continue

        verb, _, body = joined.partition(" ")
        verb = verb.upper()
        if verb == "FROM":
            match = re.search(r"\bAS\s+(\S+)", body, re.IGNORECASE)
            stage = match.group(1) if match else str(stage_index)
            stage_index += 1
        instructions.append(Instruction(stage, verb, body.strip(), start))

    return instructions


def final_stage(instructions: list[Instruction]) -> str:
    """The stage that ships.

    The last `FROM` wins. A `COPY --from=` back into it is a copy of files, not
    a resumption of that stage, so it does not move the answer.
    """
    stages = [i.stage for i in instructions if i.verb == "FROM"]
    if not stages:
        raise ValueError("the Dockerfile has no FROM instruction")
    return stages[-1]


# ---------------------------------------------------------------------------
# The rules.

@dataclass(frozen=True)
class PackageManager:
    """A resolver, how to spot it being used, and how to spot it being removed.

    The pairing is the whole point of this rule. **Invoking a package manager
    during the build is not a violation of FR-021 — it is what FR-021 requires**
    ("MUST ship with its dependencies already resolved"). The violation is
    *retaining* it, because a manager present in the shipped filesystem is a way
    to resolve at run time.

    The first draft of this rule flagged any invocation in the shipped stage,
    which was wrong in a way worth recording: it would have failed a correct
    image for installing the shell that T096 requires it to have, and the
    obvious way to satisfy it — move the install into a builder stage and
    inherit from it — changes where a line sits without changing a single fact
    about what ships.
    """

    name: str
    invoked: str
    removed: tuple[str, ...]


_PACKAGE_MANAGERS = (
    PackageManager(
        "apt",
        r"\bapt(-get)?\s+install\b",
        (r"rm\b[^\n]*?/usr/bin/apt-get", r"rm\b[^\n]*?\bapt-get\b"),
    ),
    PackageManager(
        "dpkg",
        r"\bdpkg\s+(-i|--install)\b",
        (r"rm\b[^\n]*?/usr/bin/dpkg",),
    ),
    PackageManager(
        "pip",
        r"\bpip3?\s+install\b",
        (r"rm\b[^\n]*?/usr/local/bin/pip\b", r"rm\b[^\n]*?site-packages/pip\b"),
    ),
    PackageManager(
        "npm",
        r"\bnpm\s+(install|i|ci)\b",
        (r"rm\b[^\n]*?\bnpm\b",),
    ),
    PackageManager("apk", r"\bapk\s+add\b", (r"rm\b[^\n]*?\bapk\b",)),
    PackageManager(
        "yum", r"\b(yum|dnf)\s+install\b", (r"rm\b[^\n]*?\b(yum|dnf)\b",)
    ),
    PackageManager("gem", r"\bgem\s+install\b", (r"rm\b[^\n]*?\bgem\b",)),
    PackageManager(
        "cargo", r"\bcargo\s+install\b", (r"rm\b[^\n]*?\bcargo\b",)
    ),
    PackageManager("go", r"\bgo\s+install\b", (r"rm\b[^\n]*?/usr/local/go\b",)),
)

_FETCHERS = (r"\bcurl\b", r"\bwget\b")

#: Names whose *presence* is the finding, regardless of value. Matched against
#: an `ARG` or `ENV` name so that `ENV PIP_INDEX_URL=` with an empty value is
#: still a finding: an empty index URL is configuration that a later edit fills
#: in, not the absence of configuration.
_INDEX_NAMES = (
    "PIP_INDEX_URL",
    "PIP_EXTRA_INDEX_URL",
    "PIP_TRUSTED_HOST",
    "NPM_CONFIG_REGISTRY",
    "GOPROXY",
)

#: Matched against the *name*, so a finding does not require reading a value.
#: `_KEY` is broad enough to reach a name that is not a secret — a checksum
#: argument, say. There is no exemption list because nothing in `deploy/`
#: currently trips it, and a speculative exemption is a hole opened before
#: anyone has shown it is needed. Enumerate one when a real name collides.
_SECRET_NAMES = re.compile(
    r"(TOKEN|SECRET|PASSWORD|PASSWD|API_?KEY|CREDENTIAL|_KEY|AUTH)",
    re.IGNORECASE,
)


def _names(body: str) -> list[tuple[str, str]]:
    """`ENV`/`ARG` name/value pairs, in both the `k=v` and the `k v` forms."""
    pairs: list[tuple[str, str]] = []
    if "=" in body:
        for token in re.findall(r"([A-Za-z_][A-Za-z0-9_]*)=(\S*)", body):
            pairs.append(token)
    else:
        parts = body.split(None, 1)
        if parts:
            pairs.append((parts[0], parts[1] if len(parts) > 1 else ""))
    return pairs


def check(text: str) -> list[Finding]:
    """Every FR-021 finding in one Dockerfile, in line order."""
    instructions = parse(text)
    shipped = final_stage(instructions)
    findings: list[Finding] = []

    resolved_from_lock = False
    asserts_at_build_time = False

    #: Where each manager was last invoked in the shipped stage, and whether a
    #: later instruction in that stage tore it down. Resolved after the walk,
    #: because the teardown is by construction below the invocation.
    invoked_at: dict[str, int] = {}
    removed_at: dict[str, int] = {}

    for inst in instructions:
        in_shipped = inst.stage == shipped
        body = inst.body

        if inst.verb == "RUN":
            if re.search(r"--require-hashes", body) and re.search(
                r"-r\s+\S*requirements\.lock", body
            ):
                resolved_from_lock = True
            if "SBX-IMG" in body and re.search(r"\bexit\s+1\b", body):
                asserts_at_build_time = True

            if in_shipped:
                for manager in _PACKAGE_MANAGERS:
                    if re.search(manager.invoked, body):
                        invoked_at.setdefault(manager.name, inst.line)
                    if any(re.search(p, body) for p in manager.removed):
                        removed_at[manager.name] = inst.line
                for pattern in _FETCHERS:
                    if re.search(pattern, body):
                        findings.append(
                            Finding(
                                SBX_IMG_005,
                                inst.line,
                                f"the shipped stage fetches ({pattern}). A "
                                f"fetch is dependency resolution wearing a "
                                f"different name and FR-021 does not "
                                f"distinguish.",
                            )
                        )

        if inst.verb == "ADD" and re.search(r"https?://", body):
            findings.append(
                Finding(
                    SBX_IMG_005,
                    inst.line,
                    "ADD from a URL resolves a dependency at build time "
                    "without a hash. Use a pinned, hashed lock entry.",
                )
            )

        if inst.verb in ("ENV", "ARG") and in_shipped:
            for name, value in _names(body):
                upper = name.upper()
                if upper in _INDEX_NAMES:
                    findings.append(
                        Finding(
                            SBX_IMG_003,
                            inst.line,
                            f"{name} configures a package index in the shipped "
                            f"stage. An index the image knows how to reach is "
                            f"configuration FR-021 asks not to ship, and an "
                            f"environment variable is something the contained "
                            f"process can change.",
                        )
                    )
                if _SECRET_NAMES.search(upper):
                    findings.append(
                        Finding(
                            SBX_IMG_004,
                            inst.line,
                            f"{name} reads as a secret. A build argument is "
                            f"recorded in the image history and an ENV is "
                            f"readable by the contained process; T096 "
                            f"requires the image to hold no secret.",
                        )
                    )
                del value

        if "--mount=type=secret" in body:
            findings.append(
                Finding(
                    SBX_IMG_004,
                    inst.line,
                    "a build secret mount means the build needs a secret to "
                    "succeed. T096's image is built from a committed lock "
                    "file and needs none.",
                )
            )

    for name, line in sorted(invoked_at.items(), key=lambda kv: kv[1]):
        torn_down = removed_at.get(name)
        if torn_down is None or torn_down < line:
            findings.append(
                Finding(
                    SBX_IMG_002,
                    line,
                    f"the shipped stage uses {name} and never removes it, so "
                    f"{name} is present in the image and can resolve a "
                    f"dependency at run time. FR-021 requires the image to "
                    f"ship resolved. Installing at build time is correct; "
                    f"keeping the resolver afterwards is not.",
                )
            )

    if not resolved_from_lock:
        findings.append(
            Finding(
                SBX_IMG_001,
                0,
                "no stage installs from a hash-pinned lock file. FR-021 "
                "requires dependencies resolved at build time, and "
                "--require-hashes against requirements.lock is what makes an "
                "unpinned addition a build failure rather than a silent fetch.",
            )
        )

    if not asserts_at_build_time:
        findings.append(
            Finding(
                SBX_IMG_006,
                0,
                "the build does not assert its own FR-021 properties. This "
                "checker reads the Dockerfile; nothing would catch a package "
                "manager reinstated by a base-image change, because that "
                "changes no line here. The image needs a RUN that exits 1 on "
                "finding one.",
            )
        )

    return sorted(findings, key=lambda f: (f.line, f.rule_id))


def check_path(path: Path) -> list[Finding]:
    return check(path.read_text())
