"""T186 — four loader refusals, one per U-47 term, each failing not warning.

U-47 recorded a hash-pinned trace corpus that rebased onto edited
prompts while every hash check kept passing. FR-053 makes the fix a
requirement. The loader in `src/runtime/batteries/freeze.py` must
satisfy all four terms or **fail**. It does not warn.

The four assertions, one per term:

1. an edited prompt
2. a changed battery version
3. a census mismatch
4. an attempted cross-battery join

A freeze that only hashes a prompt *file* (text not inside the record)
is not the success path — that is U-47's actual failure.
"""

from __future__ import annotations

import hashlib
import warnings
from collections.abc import Callable
from pathlib import Path

import pytest

from src.runtime.batteries.freeze import (
    CENSUS_RECHECK_IS_SKIPPED,
    CHANGED_BATTERY_VERSION_IS_ACCEPTED,
    CROSS_BATTERY_JOIN_IS_PERFORMED,
    IN_RECORD_PROMPT_CHECK_IS_DROPPED,
    BatteryFreeze,
    FreezeError,
    freeze_run,
    join_freezes,
    load_freeze,
)

VERSION = "1.4.0-probe"
TASK_FILES = {"tasks.json": b'{"tasks": []}\n'}
PROMPT = "Count each recipe once however many times it is scheduled."
REQUEST = "GET /api/recipes"


def _trace(
    *,
    task_id: str = "R4.005",
    prompt_text: str = PROMPT,
    request_text: str = REQUEST,
    battery_version: str = VERSION,
) -> dict[str, str]:
    return {
        "task_id": task_id,
        "prompt_text": prompt_text,
        "request_text": request_text,
        "battery_version": battery_version,
    }


def _freeze(
    *,
    battery_version: str = VERSION,
    traces: list[dict[str, str]] | None = None,
    task_files: dict[str, bytes] | None = None,
    census: dict[str, int] | None = None,
) -> BatteryFreeze:
    return freeze_run(
        battery_version=battery_version,
        traces=traces if traces is not None else [_trace(battery_version=battery_version)],
        task_files=task_files if task_files is not None else TASK_FILES,
        census=census,
    )


def _fails_rather_than_warns(match: str, call: Callable[[], object]) -> None:
    """Fail-loud: FreezeError, and no Warning as a substitute."""
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        with pytest.raises(FreezeError, match=match):
            call()
        assert caught == [], (
            "the loader warned instead of failing: "
            f"{[str(w.message) for w in caught]}"
        )


def test_an_edited_prompt_fails_rather_than_warns(tmp_path: Path) -> None:
    """U-47 term 1: the prompt and request text live inside the record.

    Editing the prompt file after freeze is the rebase that a file-hash
    pin missed. The in-record text detects it. A freeze that only hashed
    the file is refused — that is not the success path.
    """
    assert IN_RECORD_PROMPT_CHECK_IS_DROPPED is False

    prompt_file = tmp_path / "R4.005.prompt"
    prompt_file.write_text(PROMPT, encoding="utf-8")
    frozen = _freeze(traces=[_trace(prompt_text=prompt_file.read_text())])

    assert frozen.traces[0].prompt_text == PROMPT
    assert frozen.traces[0].request_text == REQUEST
    assert not hasattr(frozen.traces[0], "prompt_path")
    file_hash = hashlib.sha256(prompt_file.read_bytes()).hexdigest()
    assert frozen.in_record_text_digest != file_hash, (
        "the freeze hashed the prompt file rather than the in-record text; "
        "that is the U-47 success path arriving as a file pin"
    )

    with pytest.raises(FreezeError, match="inside the trace record"):
        freeze_run(
            battery_version=VERSION,
            traces=[{
                "task_id": "R4.005",
                "prompt_path": str(prompt_file),
                "prompt_file_hash": file_hash,
            }],
            task_files=TASK_FILES,
        )

    prompt_file.write_text("Count each recipe twice.", encoding="utf-8")
    _fails_rather_than_warns(
        "prompt file was edited",
        lambda: load_freeze(
            frozen,
            declared_version=VERSION,
            task_files=TASK_FILES,
            presented_prompts={"R4.005": prompt_file.read_text()},
        ),
    )


def test_a_changed_battery_version_fails_rather_than_warns() -> None:
    """U-47 term 2: the battery version and task-file hashes are pinned."""
    assert CHANGED_BATTERY_VERSION_IS_ACCEPTED is False

    frozen = _freeze()
    assert frozen.battery_version == VERSION
    assert frozen.task_file_hashes["tasks.json"] == hashlib.sha256(
        TASK_FILES["tasks.json"]
    ).hexdigest()

    _fails_rather_than_warns(
        "battery version is pinned",
        lambda: load_freeze(
            frozen,
            declared_version="1.5.0-probe",
            task_files=TASK_FILES,
        ),
    )


def test_a_census_mismatch_fails_rather_than_warns() -> None:
    """U-47 term 3: the cross-battery census is pinned and re-checked."""
    assert CENSUS_RECHECK_IS_SKIPPED is False

    census = {"1.0.0": 20, "1.4.0-probe": 1}
    frozen = _freeze(census=census)
    assert dict(frozen.census) == census

    _fails_rather_than_warns(
        "census is pinned",
        lambda: load_freeze(
            frozen,
            declared_version=VERSION,
            task_files=TASK_FILES,
            observed_census={"1.0.0": 20, "1.4.0-probe": 2},
        ),
    )


def test_a_cross_battery_join_fails_rather_than_warns() -> None:
    """U-47 term 4: the analysis path refuses a cross-battery join."""
    assert CROSS_BATTERY_JOIN_IS_PERFORMED is False

    left = _freeze(battery_version="1.4.0-probe")
    right = _freeze(battery_version="1.3.0")

    _fails_rather_than_warns(
        "refuses a cross-battery join",
        lambda: join_freezes(left, right),
    )
