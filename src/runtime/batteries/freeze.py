"""T185 — BatteryRun freeze carrying U-47's four terms (FR-053).

U-47 recorded a hash-pinned trace corpus that rebased onto edited
prompts while every hash check kept passing. FR-053 makes the fix a
requirement. All four terms, adopted verbatim from
`contracts/trace-record.md`:

1. The prompt and request text live inside the trace record, so the
   artifact is self-contained and cannot be rebased by editing a file
   it points at.
2. The battery version and task-file hashes are pinned in the freeze.
3. The cross-battery census is pinned as an invariant and re-checked
   on load, so a corpus that has silently changed shape fails rather
   than reports.
4. The analysis path refuses a cross-battery join rather than
   performing one.

A loader that cannot satisfy all four **fails**. It does not warn.

This is a measurement artifact, not a success-path table. `TABLE` is
`battery_run`. The writer is `ROLE_ANALYSIS`; the reader set is empty.
Do not import this module from `loop.py`, `serving.py`, `main.py`,
`src/contracts/result.py`, or the gates. T187 will assert the table is
structurally apart; this slice does not invent that scan.

A freeze that stores a path to a prompt file and hashes the file is
the U-47 failure mode and is refused. Editing the prompt file after
freeze is undetectable by a file-hash that moved with the file, and
is detected by the in-record text.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Mapping, Sequence

from src.contracts.ownership import ROLE_ANALYSIS

TABLE = "battery_run"

WRITER = ROLE_ANALYSIS

# ---------------------------------------------------------------------------
# Planted flags. Each one is a removal-proof needle. Flipping it is the
# defect the named T186 test exists to catch. Do not "fix" a proof by
# making the flag unused: the test reads the flag, then the behaviour.
# ---------------------------------------------------------------------------

IN_RECORD_PROMPT_CHECK_IS_DROPPED = False
CHANGED_BATTERY_VERSION_IS_ACCEPTED = False
CENSUS_RECHECK_IS_SKIPPED = False
CROSS_BATTERY_JOIN_IS_PERFORMED = False


class FreezeError(ValueError):
    """A freeze or load this module refuses. Not a warning."""


@dataclass(frozen=True)
class TraceRecord:
    """One trace, self-contained. The prompt text is the record.

    There is no `prompt_path`. A path the record pointed at is how
    U-47's corpus rebased onto edited prompts while every hash check
    kept passing.
    """

    task_id: str
    prompt_text: str
    request_text: str
    battery_version: str


@dataclass(frozen=True)
class BatteryFreeze:
    """The frozen measurement artifact. All four U-47 terms travel on it."""

    battery_version: str
    task_file_hashes: Mapping[str, str]
    census: Mapping[str, int]
    traces: tuple[TraceRecord, ...]
    in_record_text_digest: str


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _hash_task_files(task_files: Mapping[str, bytes]) -> dict[str, str]:
    return {name: _sha256(payload) for name, payload in sorted(task_files.items())}


def _in_record_text_digest(traces: Sequence[TraceRecord]) -> str:
    """Hash of the texts *inside* the records, never of a file they name."""
    joined = "\n".join(
        f"{t.task_id}\0{t.prompt_text}\0{t.request_text}" for t in traces
    )
    return _sha256(joined.encode("utf-8"))


def _census_of(traces: Sequence[TraceRecord]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for trace in traces:
        counts[trace.battery_version] = counts.get(trace.battery_version, 0) + 1
    return counts


def _require_in_record_text(raw: Mapping[str, str], *, index: int) -> tuple[str, str]:
    """Term 1: the texts live inside the record. A path or file hash is refused."""
    prompt_text = raw.get("prompt_text", "")
    request_text = raw.get("request_text", "")
    if not prompt_text or not request_text:
        raise FreezeError(
            "the prompt and request text live inside the trace record "
            f"(trace {index}). A path or file-hash pin without the text "
            "is the U-47 failure and is refused."
        )
    return prompt_text, request_text


def freeze_run(
    *,
    battery_version: str,
    traces: Sequence[Mapping[str, str]],
    task_files: Mapping[str, bytes],
    census: Mapping[str, int] | None = None,
) -> BatteryFreeze:
    """Pin a BatteryRun. Every term is required at freeze time, not later."""
    if not battery_version:
        raise FreezeError("the battery version is pinned in the freeze; an empty version pins nothing")
    if not task_files:
        raise FreezeError("task-file hashes are pinned in the freeze; an empty set pins nothing")
    if not traces:
        raise FreezeError("a freeze with no traces is not a measurement artifact")

    records: list[TraceRecord] = []
    for index, raw in enumerate(traces):
        prompt_text, request_text = _require_in_record_text(raw, index=index)
        task_id = raw.get("task_id", "")
        if not task_id:
            raise FreezeError(f"trace {index} has no task_id")
        version = raw.get("battery_version", battery_version)
        if version != battery_version:
            raise FreezeError(
                "the analysis path refuses a cross-battery join rather "
                f"than performing one: freeze is {battery_version!r}, "
                f"trace {task_id!r} is {version!r}."
            )
        records.append(
            TraceRecord(
                task_id=task_id,
                prompt_text=prompt_text,
                request_text=request_text,
                battery_version=battery_version,
            )
        )

    pinned_hashes = _hash_task_files(task_files)
    computed_census = _census_of(records)
    pinned_census = dict(census) if census is not None else computed_census
    if census is not None and dict(census) != computed_census:
        # A caller-supplied census that disagrees with the traces is a
        # silently wrong shape at freeze time. Pin what the traces are,
        # or refuse — do not store a number the traces do not support.
        # A *wider* corpus census (more versions than this freeze) is
        # the invariant FR-053 pins; it must include this freeze's own
        # counts as a subset.
        for version, count in computed_census.items():
            pinned = pinned_census.get(version)
            if pinned != count:
                raise FreezeError(
                    "the cross-battery census is pinned as an invariant; "
                    f"version {version!r} has {count} traces in this "
                    f"freeze and the supplied census says {pinned!r}."
                )

    return BatteryFreeze(
        battery_version=battery_version,
        task_file_hashes=pinned_hashes,
        census=pinned_census,
        traces=tuple(records),
        in_record_text_digest=_in_record_text_digest(records),
    )


def load_freeze(
    frozen: BatteryFreeze,
    *,
    declared_version: str,
    task_files: Mapping[str, bytes],
    presented_prompts: Mapping[str, str] | None = None,
    observed_census: Mapping[str, int] | None = None,
) -> BatteryFreeze:
    """Re-check every U-47 term. Fail. Do not warn."""
    if not IN_RECORD_PROMPT_CHECK_IS_DROPPED:
        for index, trace in enumerate(frozen.traces):
            if not trace.prompt_text or not trace.request_text:
                raise FreezeError(
                    "the prompt and request text live inside the trace "
                    f"record (trace {index}, task {trace.task_id!r}). "
                    "A record that lost them cannot be loaded."
                )
        digest = _in_record_text_digest(frozen.traces)
        if digest != frozen.in_record_text_digest:
            raise FreezeError(
                "the in-record prompt and request text were edited after "
                "the freeze. The pinned digest does not match. This is "
                "the U-47 rebase, and it fails rather than warns."
            )
        if presented_prompts is not None:
            for trace in frozen.traces:
                presented = presented_prompts.get(trace.task_id)
                if presented is None:
                    raise FreezeError(
                        f"no presented prompt for task {trace.task_id!r}; "
                        "the in-record text cannot be compared to a missing file."
                    )
                if presented != trace.prompt_text:
                    raise FreezeError(
                        "the prompt file was edited after the freeze "
                        f"(task {trace.task_id!r}). The in-record text "
                        "does not match. A file-hash pin that moved with "
                        "the file would have passed; the in-record text "
                        "fails rather than warns."
                    )

    if not CHANGED_BATTERY_VERSION_IS_ACCEPTED:
        if declared_version != frozen.battery_version:
            raise FreezeError(
                "the battery version is pinned in the freeze "
                f"({frozen.battery_version!r}); the declared version "
                f"on load is {declared_version!r}. A changed version "
                "fails rather than warns."
            )
        observed_hashes = _hash_task_files(task_files)
        if observed_hashes != dict(frozen.task_file_hashes):
            raise FreezeError(
                "the task-file hashes are pinned in the freeze and do "
                "not match the files presented on load."
            )

    if not CENSUS_RECHECK_IS_SKIPPED:
        current = (
            dict(observed_census)
            if observed_census is not None
            else _census_of(frozen.traces)
        )
        if current != dict(frozen.census):
            raise FreezeError(
                "the cross-battery census is pinned as an invariant and "
                "re-checked on load. The corpus has silently changed "
                f"shape: pinned {dict(frozen.census)!r}, observed "
                f"{current!r}. A mismatch fails rather than reports."
            )

    return frozen


def join_freezes(left: BatteryFreeze, right: BatteryFreeze) -> BatteryFreeze:
    """The analysis path. A cross-battery join is refused, not warned."""
    versions = {left.battery_version, right.battery_version}
    if len(versions) > 1:
        if CROSS_BATTERY_JOIN_IS_PERFORMED:
            # The U-47 defect: concatenate across batteries and return.
            traces = left.traces + right.traces
            hashes = dict(left.task_file_hashes)
            hashes.update(right.task_file_hashes)
            census: dict[str, int] = dict(left.census)
            for version, count in right.census.items():
                census[version] = census.get(version, 0) + count
            return BatteryFreeze(
                battery_version=",".join(sorted(versions)),
                task_file_hashes=hashes,
                census=census,
                traces=traces,
                in_record_text_digest=_in_record_text_digest(traces),
            )
        raise FreezeError(
            "the analysis path refuses a cross-battery join rather than "
            f"performing one ({left.battery_version!r} with "
            f"{right.battery_version!r}). It does not warn."
        )
    raise FreezeError(
        "the analysis path refuses a cross-battery join rather than "
        "performing one. Same-version concatenation is not a join this "
        "module offers."
    )
