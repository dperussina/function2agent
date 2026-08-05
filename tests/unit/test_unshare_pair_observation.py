"""The observation step's *reporting* is what these cover, not its readings.

The readings are a property of whatever runner the step ran on and cannot be
asserted here — asserting them would encode a host property into a test, which
is the mistake T206's first test made. What can be pinned is the reporting
contract the step exists to satisfy, and every one of these is a way this
repository has already lost a measurement or is one step from losing one:

- an absent record is loud and non-zero, because the file is missing in exactly
  the case where the measurement did not happen;
- an arm that ran and failed is distinguishable from an arm that never ran;
- the posture in the record comes from `/proc/self/status`, not from the label;
- the prediction is stated, and a reading that contradicts it is published as
  the result rather than suppressed.

That last one is the one worth a test. A step that only reports cleanly when
the prediction holds is an experiment with one acceptable outcome.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))

import unshare_pair_observation as obs  # noqa: E402


def _record(label: str, euid: int, layer: str, pivot: str = "available") -> dict:
    return {
        "label": label,
        "produced": True,
        "euid": euid,
        "uid": euid,
        "posture_read_in_this_process": {
            "Uid": f"{euid}\t{euid}\t{euid}\t{euid}",
            "CapEff": "0000000000000000" if euid else "000001ffffffffff",
            "Seccomp": "0",
            "Seccomp_filters": "0",
            "NoNewPrivs": "0",
        },
        "host": {"kernel": "6.11.0-1018-azure"},
        "sysctls": {
            "/proc/sys/kernel/apparmor_restrict_unprivileged_userns": "1",
            "/proc/sys/user/max_user_namespaces": "63929",
            "/proc/sys/kernel/unprivileged_userns_clone": None,
        },
        "lsm": {"/sys/kernel/security/lsm": "capability,landlock,yama,apparmor"},
        "namespaces": {"ok": layer == "available", "layer": layer,
                       "requirement": "FR-1", "detail": "d"},
        "pivot_root": {"ok": True, "layer": pivot,
                       "requirement": "FR-2", "detail": "d"},
    }


def _render(capsys, paths: list[str]) -> tuple[int, str]:
    code = obs.render(paths)
    return code, capsys.readouterr().out


def test_a_record_that_is_not_there_is_loud_and_fails_the_render(capsys, tmp_path):
    """Absence is the signal. A missing file means the step did not run."""
    code, out = _render(capsys, [str(tmp_path / "never-written.json")])

    assert code != 0, (
        "render exited 0 with no record on disk. The file is absent in exactly "
        "the case the step exists to make visible, so a zero exit here is the "
        "silent pass that lost the native seccomp-overhead figure."
    )
    assert "THE OBSERVATION DID NOT HAPPEN" in out
    assert "never-written.json" in out, "the missing path is not named"


def test_a_record_that_is_present_and_readable_renders_zero(capsys, tmp_path):
    """The control for the test above: absence must be what fails it."""
    path = tmp_path / "unpriv.json"
    path.write_text(json.dumps(_record("unprivileged", 1001, "kernel-sysctl-or-lsm")))

    code, out = _render(capsys, [str(path)])

    assert code == 0, "a readable record must not be reported as absent"
    assert "THE OBSERVATION DID NOT HAPPEN" not in out


def test_an_arm_that_ran_and_broke_is_not_read_as_an_observation(capsys, tmp_path):
    """A broken instrument and a refusing host must not render alike.

    Both produce "no layer". Only one of them says something about the host.
    """
    path = tmp_path / "broken.json"
    path.write_text(json.dumps({
        "label": "unprivileged", "produced": False, "error": "Traceback ...",
    }))

    code, out = _render(capsys, [str(path)])

    assert code == 0, "the record exists; this is a failed arm, not an absent one"
    assert "ARM FAILED" in out, (
        "an arm that raised rendered as though it had made a reading"
    )


def test_a_reading_that_contradicts_the_prediction_is_published_as_the_result(
    capsys, tmp_path
):
    """The step must not have exactly one acceptable outcome.

    The prediction — `kernel-sysctl-or-lsm` on the unprivileged arm — is
    derived from Ubuntu's documented default and from no observation of the
    runner. A step that reports cleanly only when the prediction holds
    measures nothing.
    """
    path = tmp_path / "unpriv.json"
    path.write_text(json.dumps(_record("unprivileged", 1001, "available")))

    code, out = _render(capsys, [str(path)])

    assert code == 0, (
        "a reading that contradicted the prediction was treated as a failure"
    )
    assert "`available`" in out, "the observed layer is not in the output"
    assert "the prediction did not hold" in out
    assert "Do not tune this step" in out


def test_the_predicted_cell_is_the_one_finding_025_could_not_construct():
    assert obs.PREDICTED_LAYER == "kernel-sysctl-or-lsm"

    from src.supervisor import preflight

    src = Path(preflight.__file__).read_text()
    assert f'"{obs.PREDICTED_LAYER}"' in src, (
        "the observation predicts a layer the classifier cannot emit; the "
        "prediction and the mechanism have drifted apart"
    )


def test_the_privileged_arm_is_named_as_the_control_when_it_is_there(
    capsys, tmp_path
):
    """The positive result here is a refusal, so it needs a control beside it."""
    unpriv = tmp_path / "u.json"
    priv = tmp_path / "p.json"
    unpriv.write_text(json.dumps(_record("unprivileged", 1001, "kernel-sysctl-or-lsm")))
    priv.write_text(json.dumps(_record("privileged (sudo)", 0, "available")))

    code, out = _render(capsys, [str(unpriv), str(priv)])

    assert code == 0
    assert "negative control" in out
    assert "the derived cell was constructed" in out


def test_a_lone_refusal_with_no_control_says_so(capsys, tmp_path):
    """Rule 8: a refusal with nothing beside it cannot be read."""
    path = tmp_path / "u.json"
    path.write_text(json.dumps(_record("unprivileged", 1001, "kernel-sysctl-or-lsm")))

    code, out = _render(capsys, [str(path)])

    assert code == 0
    assert "No privileged arm" in out, (
        "an uncontrolled refusal rendered as though it were controlled"
    )


def test_the_posture_is_read_from_proc_and_not_taken_from_the_label(monkeypatch):
    """`--label unprivileged` is a name. `/proc/self/status` is the evidence.

    Finding 024's probe inferred a posture instead of reading one and wrote a
    uid map naming a uid it did not own.
    """
    monkeypatch.setattr(obs, "_read", lambda path: (
        "Name:\tpython3\nUid:\t1001\t1001\t1001\t1001\n"
        "CapEff:\t0000000000000000\nSeccomp:\t2\nNoNewPrivs:\t1\n"
        if path == "/proc/self/status" else None
    ))

    posture = obs._posture()

    assert posture["Uid"] == "1001\t1001\t1001\t1001"
    assert posture["CapEff"] == "0000000000000000"
    assert posture["Seccomp"] == "2"
    assert posture["NoNewPrivs"] == "1"
    assert posture["CapBnd"] is None, (
        "a field absent from the status file was invented rather than left None"
    )


def test_an_unreadable_status_file_yields_nothing_rather_than_a_default(monkeypatch):
    monkeypatch.setattr(obs, "_read", lambda path: None)

    posture = obs._posture()

    assert set(posture) == set(obs._STATUS_FIELDS)
    assert all(v is None for v in posture.values()), (
        "an unread posture must be absent, not a plausible-looking default"
    )


def test_an_arm_that_raises_still_leaves_a_record_behind(monkeypatch, tmp_path, capsys):
    """A step that ran and failed must not look like a step that never ran."""
    def boom(label):
        raise RuntimeError("no such thing")

    monkeypatch.setattr(obs, "observe", boom)
    out = tmp_path / "rec.json"

    code = obs.take("unprivileged", out)

    assert code == 1
    assert out.exists(), (
        "the arm raised and left no file, which renders as 'the step did not "
        "run' — a different fact"
    )
    written = json.loads(out.read_text())
    assert written["produced"] is False
    assert "no such thing" in written["error"]


@pytest.mark.skipif(sys.platform != "linux", reason="reads /proc/self/status")
def test_on_linux_the_arm_records_the_uid_the_kernel_reports():
    import os

    record = obs.observe("self")

    assert record["produced"] is True
    assert record["posture_read_in_this_process"]["Uid"].split("\t")[0] == str(
        os.getuid()
    )
    assert record["namespaces"]["layer"]
    assert record["pivot_root"]["layer"]
