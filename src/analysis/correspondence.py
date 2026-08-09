"""T078 — the correspondence record, and why it records a declaration (FR-057).

**The task text and `tasks.md`'s Loose-requirements item 3 are both stale, and
the correction changes what this module is.** They were written before
**FR-057** existed. Item 3 says the specification *"states no procedure for
establishing correspondence … yet admission cannot complete without it"*.
FR-057, added 2026-08-03, is that gap adjudicated, and it settles the question
in the opposite direction from the one the task text assumes:

    It MUST be recorded and presented as an operator declaration and MUST NOT
    be recorded or presented as verified correspondence. v1 has no mechanism
    that establishes that a given source produced a given running instance,
    and admission MUST NOT be described — in this specification, in any
    downstream artifact, in the system's interfaces, or in its documentation —
    as establishing that correspondence.

`data-model.md` made the same correction structurally on the same day by
**deleting** `Deployment.correspondence_evidence`, on the ground that *"the
field had no producer anywhere in v1"* and that *"a field that can only ever be
empty, on the entity gating every session, invites a downstream reader to treat
an empty value as a passed check."*

So T078's *"record the correspondence evidence establishing that this source
produced this deployment"* describes an artifact this system is forbidden to
produce. What survives the correction is not nothing, and dropping it would
break the drift model: FR-028 detects source drift, FR-031 requires every drift
signal to say which of the two clocks moved, and **a source clock with no
anchor is not a clock**. The anchor is the declaration. This module records it,
carries it, and refuses in three separate directions.

## The three refusals, and why they are three and not one

They fire on **disjoint inputs**, which is not a stylistic preference. If any
one of them were reachable only through a case an earlier stage already
refuses, its test would pass with its mechanism deleted and a removal proof
could not tell the two guards apart. Each is stated here with the guard
upstream of it and what that guard does *not* cover, and
`tests/contract/test_correspondence.py` asserts the non-coverage rather than
assuming it.

**A — correspondence itself, which can never be produced.**
`verified_correspondence()` exists, is the name a caller reaching for
`correspondence_evidence` would reach for, and **always raises**. It is a
function rather than an absent function, and rather than a field that is always
`None`, because the two failure modes `data-model.md` names are *reading an
empty value as a passed check* and *finding no answer and inventing one*. A
call that refuses and says why does neither.
*Upstream guard*: **none**. Nothing anywhere in this tree establishes a
deployment-to-commit binding — OD-06 is why nothing does, and FR-002 restates
the prohibition. This limb is not doubly covered because there is nothing above
it at all.

**B — a declaration that is present and is not an anchor.**
`require()` refuses a reference whose commit is not a complete object name: a
branch, a tag, an abbreviated hash, `HEAD`. FR-028's source clock needs a fixed
point and `main` is not one — it names a different commit tomorrow, so a drift
comparison against it can report no movement across a deployment that moved.
*Upstream guard*: `src/contracts/config.py` refuses `F2A_SOURCE_REF` **unset**.
It does not refuse this: the key is `Kind.STR`, whose parser is the identity,
so `acme/app@main` loads successfully and starts the process. The contract test
asserts exactly that — `config.load` succeeding on the values this refuses is
what makes this guard's removal proof attributable to this guard.

**C — a source-derived artifact produced without the anchor attached.**
FR-057 requires the reference to be *"carried on every source-derived artifact
as the anchor of the source clock"*, and requires its status as a declaration
to be *"visible in the same place"*. `attach()` writes both or neither, and
refuses a document that already carries one without the other.
*Upstream guard*: `config.load` cannot see this — the process has already
started, with a perfectly good declaration, and something is now publishing an
artifact without it. `envelope.wrap` cannot see it either: `source_ref` is not
in any schema's `required`, so an artifact missing it wraps and stores
cleanly.

## Why this record is NOT attested, and why that is the safe direction

`tests/fixtures/reference-app/seed.py` sets the pattern for evidence that is
hard to forge: its answers are reproducible by anything that can read the
business fields, and its evidence digests are HMAC attestations whose covered
identity **excludes every business field**, so the negative control scores 4/4
on answers and **0/4** on digests. That is what makes the digests evidence: a
process that did not go through the opaque state cannot produce them.

**Nothing of that shape is available here, and the reason is not that it would
be hard.** Ask what the negative control would be. Take a declaration naming
the *wrong* commit — a real repository, a real object name, and not the one
that produced the running instance. Every digest this system could compute over
it is **equally well-formed**: an HMAC over `(deployment_id, repository,
commit)` covers only fields the forger supplied. The negative control scores
**4/4 on the digest**, which in T116's terms is the digest not discriminating
at all. A signature whose negative control passes is not evidence; it is a seal
on a claim, and it certifies the wrong proposition — *this system received this
assertion*, not *this source produced this deployment*.

And it would be worse than useless. FR-057's presentation clause exists because
a reader must not take the reference for a checked fact, and a cryptographic
digest beside a declaration is the most effective way there is to make them.
`data-model.md` deleted a field for inviting that reading when it was *empty*;
a field carrying a valid attestation invites it harder. So this module carries
no digest, and `attach()` puts the word `declared` in the same place as the
reference every time, which is the presentation clause as a mechanism.

**What is left uncovered, stated because it is the residual and not a gap this
module could close.** A declaration naming the wrong *application* surfaces
downstream: derived contracts are validated against the target's published
specification and fail. A declaration naming the **right repository at the
wrong commit** does not surface — the published specification still matches and
the two clocks agree with each other while both disagree with reality. That is
carried in `spec.md`'s Open Risks and is not closed here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping

#: The one status a source reference may carry. A single-member set rather than
#: an enum with an unused `VERIFIED` beside it: an unreachable member is a
#: member somebody reaches for, and FR-057 forbids the value existing at all.
DECLARED = "declared"

#: The field names `attach()` writes. Named so that a consumer can look for the
#: marking without importing the string, and so that adding a third field is an
#: edit here rather than at a call site.
SOURCE_REF_FIELD = "source_ref"
SOURCE_REF_STATUS_FIELD = "source_ref_status"

#: The configuration key FR-057 makes this required under FR-033.
CONFIG_KEY = "F2A_SOURCE_REF"

#: A complete git object name: SHA-1 (40) or SHA-256 (64) hex.
_OBJECT_NAME = re.compile(r"^[0-9a-f]{40}([0-9a-f]{24})?$")

#: The separator in the configured value, `<repository>@<commit>`.
_SEPARATOR = "@"


class CorrespondenceError(RuntimeError):
    """The source clock has no usable anchor. Nothing is started."""


class SourceReferenceMissing(CorrespondenceError):
    """FR-057's loud startup failure, in FR-001's shape."""


class CorrespondenceNotEstablished(CorrespondenceError):
    """Asked for correspondence. v1 has no mechanism that establishes it.

    Raised unconditionally by `verified_correspondence`. It is a distinct type
    rather than a `NotImplementedError` because a caller must be able to
    distinguish *this system cannot answer that question* from *this build is
    incomplete*: the first is FR-057's settled disposition and will not change
    in v1, and the second invites a reader to wait for it.
    """


@dataclass(frozen=True)
class SourceReference:
    """The repository and commit an operator asserts produced the deployment.

    Frozen, and carrying no status field of its own: the status is not a
    property a reference could have some other value for. `status` below is a
    property returning the one constant, so that a consumer reading it gets
    `declared` and a consumer *setting* it has nowhere to set it.
    """

    repository: str
    commit: str

    @property
    def status(self) -> str:
        return DECLARED

    def __str__(self) -> str:
        return f"{self.repository}{_SEPARATOR}{self.commit}"

    def marked(self) -> str:
        """The reference with its status in the same string.

        FR-057: *"Where the source reference appears beside a derived
        artifact, its status as a declaration MUST be visible in the same
        place, so that no consumer can read it as evidence."* A surface that
        renders a reference by interpolating this cannot omit the marking by
        forgetting a second field.
        """
        return f"{self} (operator declaration, not verified)"


@dataclass(frozen=True)
class SourceDeclaration:
    """One deployment's declared source reference.

    This is what T078 records. It is deliberately **not** named
    `CorrespondenceEvidence`: nothing here is evidence, and a type name is
    read by more people than a docstring.
    """

    deployment_id: str
    reference: SourceReference

    @property
    def status(self) -> str:
        return DECLARED

    def document(self) -> dict[str, Any]:
        return {
            "deployment_id": self.deployment_id,
            SOURCE_REF_FIELD: str(self.reference),
            SOURCE_REF_STATUS_FIELD: DECLARED,
            "established_by": (
                "nothing. v1 has no mechanism that establishes that a given "
                "source produced a given running instance (FR-057, OD-06). "
                "This is the operator's assertion, recorded as one. "
                "Divergence between it and the running deployment is detected "
                "afterwards and continuously by the drift machinery "
                "(FR-028-FR-031, FR-046); that is detection of divergence, "
                "not establishment of correspondence."
            ),
        }


# ---------------------------------------------------------------------------
# Refusal A — the thing that cannot be produced.


def verified_correspondence(declaration: SourceDeclaration) -> None:
    """Always raises. There is no v1 mechanism, and this says so in one place.

    Named for what a caller wants rather than for what it does, on purpose.
    Two downstream artifacts once asked admission for exactly this and cited a
    requirement that does not say it; the reader who goes looking now arrives
    somewhere that explains why the answer does not exist, instead of at a
    field that is empty.
    """
    raise CorrespondenceNotEstablished(
        f"{declaration.deployment_id}: nothing establishes that "
        f"{declaration.reference.repository} at "
        f"{declaration.reference.commit} produced this running deployment, "
        "and nothing in v1 can.\n"
        "  what exists           an operator declaration (FR-057), recorded "
        "as one and never as verified correspondence\n"
        "  why there is no more  a verified binding needs something read from "
        "the running instance, which OD-06 removed from analysis so that "
        "analysis stays rebuildable from the codebase alone; FR-002 restates "
        "the prohibition\n"
        "  what covers it        divergence is detected afterwards and "
        "continuously by FR-028-FR-031 and FR-046 — detection of divergence, "
        "not establishment of correspondence, and the two must not be "
        "conflated\n"
        "  the residual          the right repository at the wrong commit is "
        "not detected by either, and is carried as a named risk"
    )


# ---------------------------------------------------------------------------
# Refusal B — a declaration that is not an anchor.


def parse(value: str) -> SourceReference:
    """`<repository>@<commit>` as a reference, or a refusal naming the defect.

    Every refusal says which of the parts failed and why the value cannot
    anchor a clock. FR-057 requires the startup failure to name what is
    missing, and *"invalid source reference"* names nothing.
    """
    text = (value or "").strip()
    if not text:
        raise SourceReferenceMissing(_missing_message())
    if _SEPARATOR not in text:
        raise CorrespondenceError(
            f"{CONFIG_KEY}={value!r} does not contain {_SEPARATOR!r}. FR-057 "
            "requires the repository **and** the commit: the repository alone "
            "names an application and the source clock is anchored to a "
            "point, not to a project. Write it as "
            "`<repository>@<commit>`."
        )
    repository, _, commit = text.rpartition(_SEPARATOR)
    repository, commit = repository.strip(), commit.strip()
    if not repository:
        raise CorrespondenceError(
            f"{CONFIG_KEY}={value!r} names a commit and no repository. A "
            "commit identifier is unique within a repository and this system "
            "supports more than one deployment, so a reference with no "
            "repository does not say which codebase the drift machinery "
            "should compare against."
        )
    if not commit:
        raise CorrespondenceError(
            f"{CONFIG_KEY}={value!r} names a repository and no commit. "
            "FR-028's source clock is anchored to a commit; a repository on "
            "its own moves under every push and would report no drift across "
            "any of them."
        )
    if not _OBJECT_NAME.match(commit):
        raise CorrespondenceError(
            f"{CONFIG_KEY}={value!r}: {commit!r} is not a complete object "
            "name (40 or 64 lowercase hex characters).\n"
            "  A branch, a tag, `HEAD` or an abbreviated hash is refused "
            "rather than resolved, and the reason is not strictness. FR-028's "
            "source clock compares an anchor across time. A moving name "
            "anchors nothing: `main` denotes a different commit tomorrow, so "
            "a comparison against it reports no movement across a deployment "
            "that moved — which is a drift detector that answers 'unchanged' "
            "for the case it exists to catch.\n"
            "  Resolving it here is worse than refusing: this system would be "
            "reading the name against whatever repository state it could see, "
            "and FR-002 forbids source analysis depending on anything but the "
            "codebase. Run `git rev-parse` where the deployment was built and "
            "declare the result."
        )
    return SourceReference(repository=repository, commit=commit)


def require(value: str | None, *, deployment_id: str) -> SourceDeclaration:
    """The declaration, or a loud startup failure naming what is missing.

    FR-057: *"An absent source reference MUST make startup fail loudly, naming
    what is missing, exactly as FR-001 requires of the served-operation set."*
    """
    if not deployment_id:
        raise CorrespondenceError(
            "a source declaration is about a deployment, and none was named. "
            "FR-057 requires the reference to be recorded **on the "
            "deployment**; a declaration with no subject anchors a clock "
            "belonging to nobody."
        )
    if value is None or not str(value).strip():
        raise SourceReferenceMissing(_missing_message())
    return SourceDeclaration(deployment_id=deployment_id, reference=parse(str(value)))


def _missing_message() -> str:
    return (
        f"{CONFIG_KEY} is not set. Nothing has been started.\n"
        "  what is missing   the repository and commit you assert produced "
        "the deployment being admitted, as `<repository>@<commit>` with a "
        "complete object name\n"
        "  why it is needed  FR-028 detects source drift and FR-031 requires "
        "every drift signal to say which of the two clocks moved. A source "
        "clock with no anchor is not a clock, so without this the system can "
        "report that something moved and not which\n"
        "  what it is not    this is an operator declaration and is recorded "
        "as one. Nothing in v1 checks it, and admission does not establish "
        "that this source produced this deployment (FR-057)"
    )


# ---------------------------------------------------------------------------
# Refusal C — a source-derived artifact with no anchor attached.


def attach(
    document: Mapping[str, Any],
    declaration: SourceDeclaration,
) -> dict[str, Any]:
    """Carry the anchor onto a source-derived artifact, with its status beside it.

    FR-057 requires both: the reference *"carried on every source-derived
    artifact as the anchor of the source clock"*, and its status as a
    declaration *"visible in the same place"*. Written together in one call so
    that there is no ordering in which an artifact exists carrying one and not
    the other — the window in which a consumer reads a bare `source_ref` and
    takes it for a checked fact.

    Refuses a document whose `deployment_id` is not the declaration's. An
    anchor carried onto another deployment's artifact would put one
    deployment's source clock on another's drift comparison.
    """
    subject = document.get("deployment_id")
    if subject is not None and subject != declaration.deployment_id:
        raise CorrespondenceError(
            f"the artifact describes {subject!r} and the declaration is about "
            f"{declaration.deployment_id!r}. Attaching it would anchor one "
            "deployment's source clock to another deployment's declared "
            "commit, and FR-031's *which clock moved* would be answered about "
            "the wrong pair."
        )
    out = dict(document)
    out[SOURCE_REF_FIELD] = str(declaration.reference)
    out[SOURCE_REF_STATUS_FIELD] = DECLARED
    return out


def assert_anchored(document: Mapping[str, Any]) -> None:
    """Refuse a source-derived artifact that is not properly anchored.

    Three separate refusals, because they are three different defects:

    - **no reference at all** — FR-028's source clock has nothing to compare;
    - **a reference with no status beside it** — FR-057's presentation clause
      unmet, and this is the one that produces a wrong belief rather than an
      absent one: a consumer reading a bare `source_ref` has no way to know it
      is an assertion;
    - **a status that is not `declared`** — something wrote `verified`, which
      FR-057 forbids in this system's interfaces in the same sentence it
      forbids it in its documentation.
    """
    reference = document.get(SOURCE_REF_FIELD)
    status = document.get(SOURCE_REF_STATUS_FIELD)
    if not reference:
        raise CorrespondenceError(
            f"this artifact carries no {SOURCE_REF_FIELD}. FR-057 requires "
            "the source reference on every source-derived artifact as the "
            "anchor of the source clock, and FR-031 cannot say which of the "
            "two clocks moved for an artifact that is anchored to neither."
        )
    if not status:
        raise CorrespondenceError(
            f"this artifact carries {SOURCE_REF_FIELD}={reference!r} with no "
            f"{SOURCE_REF_STATUS_FIELD} beside it. FR-057 requires the status "
            "to be visible in the same place so that no consumer can read the "
            "reference as evidence — and a bare reference is not a missing "
            "field, it is a reader forming a wrong belief that a check "
            "happened."
        )
    if status != DECLARED:
        raise CorrespondenceError(
            f"this artifact carries {SOURCE_REF_STATUS_FIELD}={status!r}. The "
            f"only value FR-057 permits is {DECLARED!r}: v1 has no mechanism "
            "that establishes that a given source produced a given running "
            "instance, and the requirement forbids recording or presenting "
            "one as verified in this specification, in any downstream "
            "artifact, in the system's interfaces, or in its documentation."
        )
