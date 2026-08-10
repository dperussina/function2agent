#!/usr/bin/env python3
"""T101 / **Q-09** — the noise floor `notification_rate`'s sign test was
refused a magnitude bound for want of.

    python3 tools/seccomp_variance_probe.py --take --out RECORD.json [--k N]
    python3 tools/seccomp_variance_probe.py --render RECORD.json

WHAT THIS MEASURES, AND WHY NOTHING ELSE SUBSTITUTES FOR IT

`tests/batteries/test_seccomp_overhead.py` takes `REPEATS = 5` samples per arm
and publishes their median. So repeating that whole battery **k times inside one
CI job** yields *k medians-of-5* with the runner, the kernel, the architecture,
the core count and the boot all held fixed. That is the only construction that
separates the two components the battery's own `REPEATS` note says nothing
distinguishes:

  - **k medians TIGHT** — within-run variance is already handled at 5, and the
    residual variation lives at the whole-run or between-run level, where
    raising `REPEATS` cannot reach it.
  - **k medians WIDE** — raising `REPEATS` buys something real, and the case for
    5 is weaker than the aggregation evidence in that note makes it look.

**Either answer is publishable and neither is the target.** Do not tune `k`, the
arms or the caps until the figures look stable; a contradicting reading is the
result. The battery's own note reached its conclusion by refusing to raise a
constant on evidence that did not address the question, and this probe exists to
address it rather than to confirm it.

WHY IT IS NOT A GATE, AND WHY IT IS STILL VISIBLE

What this measures is the *variance of a timing measurement on a shared cloud
runner*. A noisy neighbour on the hypervisor moves it and says nothing about the
merge, so a gate built on it would fail for reasons no contributor can act on
and would be disabled within a week. It therefore follows the pattern
`ci.yml`'s `The unshare pair, unprivileged and privileged — NON-GATING
observation` step already establishes: `continue-on-error: true`, and a
`--render` that **exits non-zero when there is no record**, so an absent
observation surfaces as an annotated step and a `::warning::` rather than as
nothing at all. Non-gating, still visible.

WHY THE PROBE IS BOUNDED RATHER THAN GUARDED BY A CONDITIONAL

A job timeout **cancels the job**, and GitHub re-evaluates unfinished steps'
conditions on a cancel — so `if: always()` stays true and those steps run and
find nothing to render. `tools/README.md` § "An outer bound inside an inner
bound's window" is the full treatment. The protection a probe needs is therefore
a bound on *itself*, not a conditional after it: a hang in here must not consume
the budget of the steps that produce Q-09's actual figure.

Two bounds, and the second is the binding one:

  - `PER_BATTERY_CAP` — one battery invocation, via `tools/proof_timeout.py`,
    which is already this repository's wall-clock cap and exits `124`. Reused
    rather than reimplemented; macOS ships no `timeout(1)`, which is why that
    file exists at all.
  - `TOTAL_BUDGET` — the whole probe. A battery is launched **only if the cap
    could fire without exceeding the budget**, so the probe's wall clock is
    bounded by `TOTAL_BUDGET` and not by `k * PER_BATTERY_CAP`. Reaching it
    stops the probe and it reports `batteries_completed` below `k`, which is a
    reading and not a failure.

THE NUMBERS, MEASURED ON THE HOST THEY BOUND RATHER THAN CHOSEN

The battery's own cost is **14.83 s on CI's own runner**, read off run
31412656505's `pytest-privileged.xml`: the `measurement` fixture is module
scoped, so its whole cost lands on the first test that requests it
(`test_this_runs_measurement_reached_the_file_it_was_asked_for`, 14.826 s) and
the module's other seven cases report 0.000 s against a cached fixture. That is
17.9% of an 82.80 s privileged half. The same battery is 12.0 s on a
`6.12.76-linuxkit` aarch64 10-core container at euid 0 — close enough to be
reassuring and not the figure these bounds are set from, since CI's host is a
4-vCPU x86_64 Azure guest.

That run's pytest job took **195 s against `timeout-minutes: 10`** — 99 s
unprivileged, 84 s privileged, every other step at or under 3 s — so there is
**405 s of headroom**, per job and per step off the Actions API rather than off
the run page's total.

**`k = 10` is chosen on the statistic and not on the budget.** It yields
`C(10,2) = 45` pairwise gaps per arm, which is the same statistic the battery's
note computes over 435 local pairs at n=30, at a pair count that still supports
a median and a maximum without one draw dominating either. At 14.83 s a battery
that is ~148 s, which is 37% of the headroom — so **the budget would have
permitted k≈25 and did not decide k**. Stating it the other way, because it is
the direction that matters: a `k` chosen to fit a budget measures the budget.

The caps are then set so that the *probe* cannot spend the headroom it is not
using: `PER_BATTERY_CAP = 90` is 6.1x the measured 14.83 s, and
`TOTAL_BUDGET = 300` bounds the step at half the job's bound with the job's
existing 195 s of work already accounted for — 195 + 300 = 495 s inside 600 s.

WHAT THIS LICENSES AND WHAT IT MUST NOT

`notification_rate` withholds a rate on a non-positive difference, and that
boundary is zero **because the quantity's definition forbids crossing it** —
supervision does strictly more work than its own baseline. A *magnitude* bound
was deliberately refused because this battery had no measured noise floor and a
chosen one would be a constant silently deciding which figures get published.

This probe measures that floor. **It does not install a bound, and nothing here
should be read as proposing one is now safe to install.** That decision belongs
to the owner and goes in against a floor whose `n` the owner has read.
`tests/unit/test_seccomp_overhead_record.py::
test_a_small_positive_overhead_is_still_published_because_no_floor_is_known`
pins the current reasoning, so anyone adding a magnitude bound has to come and
delete it first — which is the intended cost.

WHAT IT DOES NOT MEASURE

The across-run component. This is one runner and one boot by construction, which
is the whole point; the between-run spread is a different quantity read off
several runs' artifacts. Two records taken on different kernels are not a before
and an after and must not be subtracted, and the same holds for a within-run
range and an across-run range.
"""

from __future__ import annotations

import argparse
import itertools
import json
import os
import platform
import shutil
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import proof_timeout  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
BATTERY = "tests/batteries/test_seccomp_overhead.py"
RESULTS = REPO / "tests" / "batteries" / "results"
LATEST = RESULTS / "seccomp-overhead.latest.json"

#: Battery invocations. See the module docstring for why 10 and not a value the
#: budget chose.
DEFAULT_K = 10

#: One battery invocation's wall-clock cap, 6.1x the 14.83 s measured on CI.
PER_BATTERY_CAP = 90.0

#: The whole probe's wall-clock cap, and the binding bound.
TOTAL_BUDGET = 300.0

#: The arms whose rate is load-bearing, in the order the battery's own note
#: lists them. `compute_only` is deliberately last and deliberately included:
#: it is the control, its rate is the one that goes non-positive, and a floor
#: that excluded the arm that motivated it would be measuring the easy case.
ARMS = (
    "path_heavy",
    "reference_app_api",
    "shell_heavy",
    "reference_app_socket",
    "compute_only",
)

#: The figure the floor is expressed in. The battery's own docstring calls this
#: the one transferable field; `ratio` folds in an interpreter start that
#: cancels out of the difference, so a spread in `ratio` is not a spread in the
#: quantity anybody quotes.
FIGURE = "microseconds_per_notification"


def _relative_gap(a: float, b: float) -> float:
    """`|a - b|` over their mean, as a percentage.

    **The formula is the battery note's own, recovered from its published
    figures rather than assumed.** Its four quoted CI gaps against run
    31400931286 — 1.2%, 2.2%, 6.7%, 8.9% — reproduce exactly under this
    definition and under neither `|a-b|/min` nor `|a-b|/max`. A floor computed
    with a different denominator would not be comparable to the spread it is
    supposed to be read against, which is the whole reason it is pinned here.
    """
    return 100.0 * abs(a - b) / ((a + b) / 2.0)


def _spread(values: list[float]) -> dict:
    """Median, range and pairwise gaps for one arm's draws.

    `range_percent` is `(max - min) / median`, which is also recovered rather
    than chosen: it reproduces all four of the battery note's within-host range
    figures — path_heavy 43.4%, reference_app_api 19.5%, shell_heavy 27.9%,
    reference_app_socket 627% — off the medians and extrema printed beside
    them.
    """
    median = statistics.median(values)
    gaps = [_relative_gap(a, b) for a, b in itertools.combinations(values, 2)]
    return {
        "draws": values,
        "n": len(values),
        "median": round(median, 2),
        "min": round(min(values), 2),
        "max": round(max(values), 2),
        "range_percent": round(100.0 * (max(values) - min(values)) / median, 1)
        if median
        else None,
        "pairs": len(gaps),
        "pairwise_gap_median_percent": round(statistics.median(gaps), 1)
        if gaps
        else None,
        "pairwise_gap_max_percent": round(max(gaps), 1) if gaps else None,
    }


def _environment() -> dict:
    """What the floor is a property of.

    Core count is here rather than inferred because a median-of-5 on a 4-vCPU
    guest and one on a 10-core host are different measurements, and the
    battery's own record carries the same field for the same reason.
    """
    return {
        "platform": platform.platform(),
        "machine": platform.machine(),
        "kernel": platform.release(),
        "euid": os.geteuid(),
        "cpu_count": os.cpu_count(),
        "python": sys.version.split()[0],
    }


def _run_one_battery() -> tuple[int, dict | None]:
    """One battery invocation under the per-invocation cap.

    Returns its shell status and the record it left, or `None` when it left
    none. The record is read from `seccomp-overhead.latest.json` because that is
    what an ordinary privileged run writes; `F2A_RECORD_MEASUREMENTS` is
    deliberately not set, so this probe cannot touch the committed figure.
    """
    if LATEST.exists():
        LATEST.unlink()
    status = proof_timeout.run(
        PER_BATTERY_CAP,
        [sys.executable, "-m", "pytest", BATTERY, "-q", "--no-header", "-p",
         "no:cacheprovider"],
    )
    if not LATEST.exists():
        return status, None
    try:
        return status, json.loads(LATEST.read_text())
    except (OSError, json.JSONDecodeError):
        return status, None


def take(k: int, out: Path) -> int:
    """Run the battery `k` times and record the spread of its medians.

    **The gating suite's own figure is preserved.** `ci.yml`'s
    `The kernel-native seccomp-overhead figure` step reads and publishes
    `seccomp-overhead.latest.json`, and the artifact upload keeps it. This probe
    overwrites that file `k` times by construction, so the incoming copy is
    saved first and restored last — otherwise the figure CI publishes as "the
    privileged suite's" would silently become this probe's last battery, which
    is the stale-figure-quoted-as-a-fresh-one defect one file over.
    """
    started = time.monotonic()
    preserved = LATEST.read_bytes() if LATEST.exists() else None

    batteries: list[dict] = []
    stopped_because = None
    try:
        for attempt in range(1, k + 1):
            elapsed = time.monotonic() - started
            # Launch only if the cap could fire inside the budget. This is what
            # makes TOTAL_BUDGET the bound rather than k * PER_BATTERY_CAP.
            if elapsed + PER_BATTERY_CAP > TOTAL_BUDGET:
                stopped_because = (
                    f"the total budget of {TOTAL_BUDGET:g}s would not contain "
                    f"another capped invocation after {elapsed:.1f}s, so "
                    f"{attempt - 1} of {k} batteries ran. This is a reading of "
                    "the budget and not a failure of the measurement."
                )
                break
            at = time.monotonic()
            status, record = _run_one_battery()
            took = time.monotonic() - at
            entry = {
                "attempt": attempt,
                "seconds": round(took, 2),
                "status": status,
                "timed_out": status == proof_timeout.TIMED_OUT,
                "arms": None,
            }
            if record is not None:
                entry["arms"] = {
                    arm: {
                        FIGURE: record["arms"][arm][FIGURE],
                        "overhead_seconds": record["arms"][arm][
                            "overhead_seconds"
                        ],
                        "notifications_observed": record["arms"][arm][
                            "notifications_observed"
                        ],
                    }
                    for arm in ARMS
                    if arm in record["arms"]
                }
                entry["environment"] = record["environment"]
            batteries.append(entry)
    finally:
        # Restore before anything else can read it, including on the exception
        # path — a probe that leaves the gating step's input replaced has
        # damaged a measurement it was only supposed to observe.
        if preserved is None:
            if LATEST.exists():
                LATEST.unlink()
        else:
            LATEST.write_bytes(preserved)

    rated = [b for b in batteries if b["arms"]]
    per_arm = {}
    for arm in ARMS:
        values = [
            b["arms"][arm][FIGURE]
            for b in rated
            if arm in b["arms"] and b["arms"][arm][FIGURE] is not None
        ]
        withheld = sum(
            1
            for b in rated
            if arm in b["arms"] and b["arms"][arm][FIGURE] is None
        )
        per_arm[arm] = {
            "rated": len(values),
            "withheld": withheld,
            # Two draws is the floor for a spread. One draw has no range and
            # reporting 0.0 for it would be a number standing where there is
            # no measurement — the `UNPRICED`/`UNRATED` defect this repository
            # has now recorded three times.
            "spread": _spread(values) if len(values) >= 2 else None,
            "spread_absent_because": None
            if len(values) >= 2
            else (
                f"{len(values)} rated draw(s) and {withheld} withheld. A "
                "spread needs at least two draws of the same quantity; one is "
                "a reading and zero is not a measurement."
            ),
        }

    record = {
        "question": "Q-09",
        "task": "T101",
        "what_this_is": (
            "k repeats of tests/batteries/test_seccomp_overhead.py inside ONE "
            "job on ONE runner, so every draw is a median-of-REPEATS with the "
            "runner, kernel, architecture, core count and boot held fixed. "
            "This is WITHIN-RUN variance. It is not the across-run spread and "
            "must not be compared with one or subtracted from one."
        ),
        "measured_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "k_requested": k,
        "batteries_completed": len(batteries),
        "batteries_with_a_record": len(rated),
        "stopped_because": stopped_because,
        "per_battery_cap_seconds": PER_BATTERY_CAP,
        "total_budget_seconds": TOTAL_BUDGET,
        "wall_clock_seconds": round(time.monotonic() - started, 2),
        "figure": FIGURE,
        "environment": _environment(),
        "per_arm": per_arm,
        "batteries": batteries,
        "what_this_does_not_license": (
            "A magnitude bound on notification_rate. The sign test's boundary "
            "is zero because the quantity's definition forbids crossing it; a "
            "magnitude bound is a constant deciding which figures get "
            "published and installing one is the owner's decision against a "
            "floor whose n they have read. Nothing here installs one."
        ),
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    print(json.dumps(record["per_arm"], indent=2, sort_keys=True))
    print("\nenvironment: " + json.dumps(record["environment"], sort_keys=True))
    print(
        f"\n{len(rated)} of {k} batteries left a record in "
        f"{record['wall_clock_seconds']:g}s"
    )
    if stopped_because:
        print(f"stopped early: {stopped_because}")
    return 0


def render(path: str) -> int:
    """Render the record for a run page, non-zero when there is nothing to
    render.

    Absence is the failure this exits on, for `ci.yml`'s own reason one step
    over: the file is missing in exactly the case where the observation did not
    happen, and a step that goes green over that is the silent instrument this
    repository keeps finding.
    """
    target = Path(path)
    if not target.is_file() or not target.stat().st_size:
        print("### seccomp within-run variance — NOT PRODUCED\n")
        print(
            f"No record at `{path}`. That file is written by the probe itself, "
            "so its absence means the observation did not happen — the probe "
            "was cancelled, or it left nothing. This does not gate the build, "
            "and it is not a measurement either."
        )
        print()
        return 1
    try:
        record = json.loads(target.read_text())
    except json.JSONDecodeError as exc:
        print("### seccomp within-run variance — UNREADABLE\n")
        print(f"`{path}` is not JSON: {exc}")
        print()
        return 1

    env = record["environment"]
    print("### seccomp overhead — WITHIN-RUN variance, one runner, one boot\n")
    print(record["what_this_is"])
    print()
    print(
        f"`{record['batteries_with_a_record']}` of `{record['k_requested']}` "
        f"batteries left a record in {record['wall_clock_seconds']:g}s, cap "
        f"{record['per_battery_cap_seconds']:g}s per battery, budget "
        f"{record['total_budget_seconds']:g}s.\n"
    )
    print(
        f"Kernel `{env['kernel']}` on `{env['machine']}`, euid `{env['euid']}`, "
        f"`{env['cpu_count']}` cores, CPython `{env['python']}`. "
        f"Platform `{env['platform']}`.\n"
    )
    if record.get("stopped_because"):
        print(f"**Stopped early.** {record['stopped_because']}\n")

    print(f"| arm | rated | withheld | median | min | max | range | "
          f"pairs | gap median | gap max |")
    print("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    # `ARMS` order rather than the record's, which a `sort_keys` dump leaves
    # alphabetical. The order carries meaning: `compute_only` is the control and
    # belongs last, beside the proxies whose rate it is supposed to be unlike.
    ordered = [(arm, record["per_arm"][arm]) for arm in ARMS
               if arm in record["per_arm"]]
    for arm, entry in ordered:
        spread = entry["spread"]
        if spread is None:
            print(
                f"| `{arm}` | {entry['rated']} | {entry['withheld']} | "
                "— | — | — | — | — | — | — |"
            )
            continue
        print(
            f"| `{arm}` | {entry['rated']} | {entry['withheld']} | "
            f"{spread['median']} | {spread['min']} | {spread['max']} | "
            f"{spread['range_percent']}% | {spread['pairs']} | "
            f"{spread['pairwise_gap_median_percent']}% | "
            f"{spread['pairwise_gap_max_percent']}% |"
        )
    print()
    print(
        f"`{record['figure']}`. `range` is `(max - min) / median` and `gap` is "
        "`|a - b| / mean(a, b)` over every pair — both are the statistics the "
        "battery's own `REPEATS` note uses, so these figures are comparable "
        "to the within-host and across-run spreads quoted there.\n"
    )
    for arm, entry in ordered:
        if entry["spread_absent_because"]:
            print(f"- `{arm}`: {entry['spread_absent_because']}")
    print()
    print(f"**What this does not license.** {record['what_this_does_not_license']}")
    print()
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Within-run variance of the T101 seccomp-overhead battery."
    )
    parser.add_argument("--take", action="store_true",
                        help="run the battery k times and write the record")
    parser.add_argument("--render", metavar="RECORD.json",
                        help="render a record for a run page")
    parser.add_argument("--k", type=int, default=DEFAULT_K,
                        help=f"battery invocations (default {DEFAULT_K})")
    parser.add_argument("--out", type=Path,
                        default=RESULTS / "seccomp-variance.latest.json")
    args = parser.parse_args(argv)

    if args.render:
        return render(args.render)
    if not args.take:
        parser.print_help()
        return 2
    if args.k < 2:
        print("--k must be at least 2; a spread needs two draws",
              file=sys.stderr)
        return 2
    return take(args.k, args.out)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
