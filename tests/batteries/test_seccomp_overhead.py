"""T101 / **Q-09** — measure the syscall supervisor's overhead **before the
mechanism is committed**.

Q-09 was accepted *with* the measurement, not with a prediction of its result.
The recorded fallback, if the overhead is prohibitive, is an audit channel that
keeps SC-022 and loses the before-execution property. This file produces the
number that decides.

**What the number is a property of, stated first because it is the part that
transfers least.** Every figure here is a property of:

  - ~~Docker Desktop's `linuxkit` VM on this host — **not a bare Linux host**.~~
    **Struck 2026-08-10: that sentence was a constant, and the record carried
    it onto hosts it had never been true of.** It was written on a laptop. When
    CI ran this module on GitHub's native runner the emitted record named
    `linuxkit` in prose while `environment.kernel`, one field away, correctly
    read `6.17.0-1020-azure`. The caveat is now a **reading**:
    `host_property_caveat` below builds it from the kernel release, the
    architecture and the euid the run actually observed. Syscall cost inside a
    virtualized kernel is not the syscall cost on metal, and syscall
    *interception* cost is the thing most sensitive to that — which is why the
    caveat about it was the part that most needed to stop being hardcoded.
  - The host's architecture, kernel version and core count, all recorded in
    the result file rather than described here.
  - A **CPython** supervisor answering notifications with `fcntl.ioctl` and a
    `/proc/<pid>/mem` read per attempt. A Go or C supervisor would be faster;
    how much faster is not measured and is not guessed at.
  - The five workloads below. Three are proxies — `shell_heavy`, `path_heavy`
    and the `compute_only` control — and two drive the reference application
    T116 built, over the two surfaces `app.py` names: `Application.call` is
    the in-process API sequence and `build_server` the socket arm.

**The shell-heavy arm on the reference application does not exist, and its
absence is deliberate and checked.** T101 asks for "the shell-heavy arm that
stresses it". `shell_heavy` below is that arm and has been measured since
2026-08-03; what T116 did not bring is a shell-heavy arm *of the reference
application*, and building one would have been a mistake rather than a gap.
The reference application composes no shell command — it spawns no process at
all, which `tests/unit/test_reference_app.py::
test_the_reference_application_spawns_no_process` asserts mechanically so the
claim is checked rather than argued. An arm that wrapped it in `sh -c` would
be measuring `sh`'s process spawn and the client's, attribute both to the
reference application, and hand back the proxy figure wearing the fixture's
name. The absence is recorded in the result file with this reasoning, and the
assertion is the tripwire: if anyone gives the reference application a
subprocess call, it fires and this clause reopens.

This corpus has been burned by exactly this class of error: a measured 1.0000
precision that turned out to be a property of the target rather than of the
mechanism. So the compute-only arm exists specifically to show that the
overhead is attributable to syscall interception — if it moved too, the number
would be measuring the VM's scheduler and nothing else.

Run:
    docker run --rm --privileged -v "$PWD:/work" -w /work f2a-dev \\
        python -m pytest tests/batteries/test_seccomp_overhead.py -s -v
"""

from __future__ import annotations

import json
import os
import platform
import statistics
import sys
import textwrap
import time
from collections.abc import Mapping
from pathlib import Path

import pytest

pytestmark = [
    pytest.mark.linux_only,
    pytest.mark.privileged,
    pytest.mark.skipif(sys.platform != "linux", reason="OD-17: Linux only"),
]

from src.supervisor import _linux, seccomp  # noqa: E402

RESULTS = Path(__file__).resolve().parent / "results"
REPO = Path(__file__).resolve().parents[2]
REFAPP_DIR = REPO / "tests" / "fixtures" / "reference-app"
#: Samples per arm, of which the median is taken.
#:
#: **Five, and it stays five on the evidence below rather than for want of
#: any.** Q-09's recorded decision — commit the mechanism, or fall back to an
#: audit channel — was to be taken against this battery's figure, and two CI
#: runs of the *same runner class* (31400931286 and 31403771772, both native
#: `6.17.0-1020-azure` x86_64 4 vCPU euid 0, CPython 3.12.13) moved every arm
#: 24–35% and flipped the control's sign. So the repeat count needed a basis.
#:
#: **What was measured, and it is one of the two quantities and not both.**
#: 30 sequential runs of this battery in one `f2a-dev:latest` container on
#: 2026-08-10 — Linux 6.12.76-linuxkit aarch64, euid 0 read from
#: `/proc/self/status`, 10 CPUs, CPython 3.12.13. That is **WITHIN-HOST
#: variance**. It is not between-runner variance and cannot stand for it.
#: `microseconds_per_notification`, median [min–max] over n=30:
#:
#:     path_heavy            61.55  [39.74 –  66.48]
#:     reference_app_api     74.72  [65.56 –  80.14]
#:     shell_heavy           79.26  [63.25 –  85.36]
#:     reference_app_socket  75.25  [34.62 – 506.77]
#:     compute_only         112.27  [ 4.75 – 400.42]   (27 of 30 rated)
#:
#: **A range over 30 draws is not the statistic two CI runs give**, and
#: comparing them would have been the whole defect of the exercise. Compared
#: like with like — the distribution of |relative gap| between two runs on this
#: host, 435 pairs per arm, against the single gap each CI pair shows:
#:
#:     arm                   local median  local max   CI gap   CI percentile
#:     path_heavy                    3.3%      50.3%    27.1%           83rd
#:     reference_app_api             3.8%      20.0%    36.9%          100th
#:     shell_heavy                   4.7%      29.8%    30.2%          100th
#:     reference_app_socket         11.5%     174.4%    43.6%           86th
#:
#: For two arms that gap exceeds all 435 local pairs. ~~So CI carries a
#: component this measurement does not account for, and the data cannot say
#: which: between-runner variance and a larger within-host variance on a 4-vCPU
#: x86_64 Azure guest predict the same observation.~~
#:
#: **Struck 2026-08-10 by a third draw — the inference, never the arithmetic
#: above, which is correct for the pair it describes.** Run 31409214955, same
#: runner class, gave 60.43 / 69.55 / 70.99 / 71.70 in that order. Against run
#: 31400931286 those are gaps of 1.2%, 2.2%, 6.7% and 8.9% — the **20th to 64th
#: percentile** of this host's within-host distribution, which is to say
#: unremarkable. Every pair involving 31403771772 is 23.6–43.6%, at the 83rd to
#: 100th.
#:
#: ~~**So the observed spread is one anomalous run and not a wide runner
#: class**, and "every arm moved 24–35%" was a property of that run rather than
#: of CI. A fourth draw, 31410461698, keeps that reading and widens the
#: concordant band: excluding 31403771772, the three remaining runs sit
#: 1.2–13.8% apart, against local within-host medians of 3.3–11.5% and maxima
#: of 20–174%.~~
#:
#: **Struck 2026-08-10 at n=11 — the inference again, never the arithmetic,
#: which is correct for the runs it describes.** Every CI run since 31400931286
#: publishes this figure as an artifact, so the sample is **11 runs** on one
#: runner class and not the three to five the readings above were taken over.
#: Recomputed from the artifacts with the same statistic, 45 pairs per arm over
#: the four load-bearing arms, **180 pairs**:
#:
#:     excluding 31403771772 (n=10)   median 18.5%   max 69.6%
#:     pairs involving 31403771772                  0.1% – 43.6%
#:
#: So 18.5% was the **median** of the concordant band and not its extent; the
#: extreme pair is `path_heavy` 34.33 against 64.41 — runs 31404642569 and
#: 31411573174, **neither of them the run called anomalous** — and
#: 31403771772's own maximum sits *below* the concordant maximum while its
#: minimum is the smallest gap in the sample (45.46 against 31407296884's
#: 45.49). **The run is not separable from the class it was excluded from, so
#: the spread is wide across runs with no outlier.** That is a third reading and
#: not a return to the struck between-runner one: nothing here says *where* the
#: width lives, which is the question the probe below now takes.
#:
#: A closed sample at n=11, re-derivable rather than transcribed:
#: `gh run download <id> -n pytest-outcomes-and-native-overhead` over those runs
#: and `|a-b| / mean(a,b)`. The control went non-positive in **8 of 11**, and
#: its three published positive rates are 188.02, 62.74 and 74.04 — a 3.0x
#: swing, every value positive, every one passing the sign test.
#:
#: ~~The second thing is the useful one: 31403771772 is also the run whose
#: control flipped sign, so `UNRATED["non-positive-overhead"]` is an in-band
#: detector for exactly the run whose figures should not be compared. Two
#: independent signals picking out the same run out of three is what makes it an
#: outlier.~~
#:
#: **Struck by the fourth draw, which is the run that could falsify it and
#: did.** 31410461698's control flipped sign too — overhead -0.028136s, rate
#: withheld — and that run is *not* extreme on any other arm. So the control's
#: sign is **sensitive but not specific**: it fires on the anomalous run and
#: also on an ordinary one, and it must not be read as marking a run whose
#: figures are unusable. What it marks is exactly what it says — an arm whose
#: own difference came out non-positive, for that arm.
#:
#: **What the flip rate does carry is the first evidence separating the two
#: components above, and it is suggestive rather than established at n=4.** The
#: control went non-positive in 2 of 4 CI runs and in 3 of 30 here — 50% against
#: 10%. A sign flip happens when the difference is small next to the run-to-run
#: variation, so its frequency is a crude proxy for that variation, and the
#: proxy says CI's 4-vCPU x86_64 guest is the noisier host. That favours *larger
#: within-host variance on CI* over *between-runner variance* as the explanation
#: for the excess — the two readings the strike above says nothing separates.
#: Four runs cannot settle it, and the measurement named below still can.
#:
#: **Settled 2026-08-10 by that measurement, and it splits: the proxy is right
#: about the control and wrong about every other arm.** The floor below puts
#: CI's within-run range at **12.7–28.0%** on the four load-bearing arms against
#: this host's within-host **19.5–627%**, so CI's 4-vCPU guest is the *quieter*
#: host there, not the noisier one. The control goes the other way — non-positive
#: in **3 of 10** within one CI run and 3 of 30 here — which is the arm the flip
#: rate was actually computed on. So a flip rate is a proxy for the variance *of
#: the arm it was measured on* and does not transfer to the others, which is a
#: narrower reading than "the noisier host" and the one the data supports.
#:
#: This host still differs from CI's in architecture, kernel and core count at
#: once, and `host_property_caveat` says in terms that two records on different
#: kernels are not a before and an after. Nothing here measures CI's own
#: within-host variance; that is still owed.
#:
#: **Hence no change, and the reasoning is the refusal rather than the
#: number.** Aggregating five runs into one — grouping the 30, which
#: approximates `REPEATS = 25` — does shrink the within-host range a long way
#: (path_heavy 43.4% → 4.9%, reference_app_api 19.5% → 4.0%, shell_heavy 27.9%
#: → 7.2%, reference_app_socket 627% → 16.5%). So more repeats demonstrably buys
#: within-host stability **on this host**. What it is not shown to buy is the
#: thing it would be raised for: if CI's excess component is between-runner,
#: more samples inside one run reduce it by exactly nothing, and raising the
#: count five-fold at 5× the wall clock on evidence that does not reach the
#: target is tuning a constant until the figures look stable.
#:
#: **What decides it is now built rather than named.** Repeat this battery k
#: times *inside a single CI run*, on one runner: that yields k medians-of-5
#: with the runner, kernel, architecture, core count and boot held fixed, which
#: is within-run variance for CI's own host. `tools/seccomp_variance_probe.py`
#: takes it at **k = 10** and `ci.yml` runs it as a **non-gating** step in the
#: same job as the privileged suite, bounded by a 90s per-battery cap and a 300s
#: total budget. Sized against readings rather than guesses: this battery costs
#: **14.83s on that runner class**, read off run 31412656505's
#: `pytest-privileged.xml`, in a job that took 195s against a 600s bound.
#:
#: ~~a CI median is not a decidable basis for Q-09~~ **a median over a single CI
#: run is not a decidable basis for Q-09 — refined 2026-08-10 from three runs
#: rather than two** — which is a more useful answer than a tuned number. What
#: no number of runs measures is the repeat count *inside* one run, which is
#: what `REPEATS` sets, and that is exactly what the probe measures.
#:
#: **THE FLOOR WAS TAKEN, AND THE ANSWER IS TIGHT FOR THE FOUR LOAD-BEARING
#: ARMS AND WIDE FOR THE CONTROL.** Run 31415736559, 10 of 10 batteries in
#: 151.0s on `6.17.0-1020-azure` x86_64, euid 0, **4 cores**, CPython 3.12.13.
#: A closed sample at n=10, one runner, one boot; re-derivable from that run's
#: `seccomp-variance.latest.json` artifact. `microseconds_per_notification`,
#: median [min–max], with the pairwise-gap median and max over 45 pairs:
#:
#:     path_heavy            62.70  [59.42 –  68.32]  range 14.2%  gap 6.0% / 13.9%
#:     reference_app_api     65.62  [64.44 –  74.47]  range 15.3%  gap 2.3% / 14.4%
#:     shell_heavy           71.06  [67.06 –  76.09]  range 12.7%  gap 4.6% / 12.6%
#:     reference_app_socket  72.44  [65.87 –  86.17]  range 28.0%  gap 7.4% / 26.7%
#:     compute_only          24.79  [ 4.04 – 131.73]  range 515%   gap 127% / 188%   (7 of 10 rated)
#:
#: **So `REPEATS` stays 5, and now because the right quantity was measured.**
#: Within-run pairwise gaps on the load-bearing arms are 2.3–7.4% at the median
#: against the across-run **18.5% median and 69.6% maximum** above. Raising
#: `REPEATS` shrinks the smaller component and leaves the larger one untouched,
#: so five-fold wall clock buys a few percent of the wrong number. The residual
#: lives at the whole-run level, which is where `REPEATS` cannot reach.
#:
#: **The denominator claim holds on CI too, and more strictly.**
#: `notifications_observed` was a *single* value across all ten draws for every
#: arm — 2078 / 827 / 372 / 833 / 78 — so the whole within-run spread is in the
#: timing numerator. Those are not this host's counts, which is the point of
#: recording both.
#:
#: **The control is the finding.** Its `overhead_seconds` straddles zero across
#: one boot — **−0.004659 to +0.010275 s**, non-positive in 3 of 10 — and its
#: rated draws swing **32.6x**, from 4.04 to 131.73 µs/notification. That is
#: wider than anything the across-run sample shows, so the 3.0x swing in the
#: published control rate is not an across-run effect at all: it is this arm's
#: own within-run noise, measured. All four load-bearing arms sit clear of that
#: band **on this sample** — `shell_heavy` closest at 24.9–28.3 ms of overhead
#: against the control's +10.3 ms ceiling, a factor of 2.4 **and this arm
#: overlaps the control's band on two of the four samples now recorded, so the
#: clearance here is a property of this draw** *(qualifier added 2026-08-10 under
#: limb ③'s revised rule, which requires the overlap on the figure's own line)*.
#:
#: **THE FLOOR WAS THEN TAKEN TWICE MORE, AND THE SPLIT REPRODUCES WHILE THE
#: NUMBERS DO NOT.** Runs `31416789165` and `31416959913`, same runner class,
#: same `6.17.0-1020-azure` x86_64, euid 0, 4 cores, CPython 3.12.13, 10 of 10
#: batteries in 127.7 s and 139.3 s. Three closed samples at n=10 each, three
#: boots; no sample is folded into another. Within-run pairwise-gap medians:
#::
#:     path_heavy            6.0%   3.3%   3.1%
#:     reference_app_api     2.3%   4.5%   3.8%
#:     shell_heavy           4.6%   7.0%   6.8%
#:     reference_app_socket  7.4%   7.8%  10.1%
#:     compute_only          127%   98%    70%     (7, 8 and 6 of 10 rated)
#::
#: **Two cells of that table were transcription errors and are corrected
#: 2026-08-10 by re-derivation from the artifacts.** `path_heavy`'s first
#: column read **2.3%**, which is `reference_app_api`'s value one row down —
#: the detailed block above for the same run says `path_heavy` gap
#: **6.0% / 13.9%**, so the table contradicted its own source four paragraphs
#: up. `compute_only`'s rated count for that run read **10**, where the same
#: block says **7 of 10** and 3 of 10 draws are non-positive. Neither error
#: reaches a conclusion: the load-bearing range `2.3–7.4%` is over all four
#: arms and 2.3% is `reference_app_api`'s, so it stands as written. Recorded
#: rather than silently fixed because the same two cells had propagated to
#: `specs/002-spec-aware-agent-runtime/tasks.md`, which is the
#: claim-in-a-different-file-from-its-subject shape `tools/README.md` names.
#: **So TIGHT-on-the-four and WIDE-on-the-control is reproducible, three for
#: three, and that is the part `REPEATS` is decided on.** The medians themselves
#: are not: the same arm's median-of-ten-medians reads 62.70, 40.82 and 43.97
#: µs/notification across the three, and the across-run gaps between them are
#: **42.3% / 46.3% / 47.7% / 59.1%** on the four load-bearing arms and 140.5% on
#: the control. **That is the conclusion in its strongest form.** Each of those
#: points already aggregates fifty samples, and fifty samples still leaves a
#: 42–59% across-run gap, so the residual is not a sample-count problem at any
#: `REPEATS` this battery could afford. `REPEATS` stays 5.
#:
#: **The bound this floor looked like it licensed does not survive the repeat,
#: and that is the load-bearing correction.** From the first sample alone the
#: control's positive extreme was **+0.010275 s** and reporting it invited
#: reading a floor off it. The next two give **+0.017368** and **+0.029317 s** —
#: the defining quantity of the bound moves **2.9x** across three samples of
#: identical construction on one runner class. Worse, in `31416959913` that
#: extreme sits **above** `shell_heavy`'s own overhead for the same run
#: (0.0188–0.0228 s), so a bound read off that sample's control would withhold a
#: load-bearing arm outright. **There is no single number here to be a floor**,
#: and the original refusal to install a magnitude bound is what this measurement
#: vindicates rather than what it repairs.
#:
#: ~~A median over several runs is a different proposition and is now a
#: reachable one, because the anomalous run is a minority of three and is
#: flagged in-band by its control's sign rather than picked out in hindsight.~~
#: **Struck 2026-08-10 by the n=11 sample above, and both halves of it fail.**
#: There is no anomalous run to be a minority of, and the control's sign is not
#: a flag for one: it goes non-positive in **8 of 11** runs, including runs that
#: are unremarkable on every other arm. A median over several runs is still a
#: different proposition from a median over one, but it is not made decidable by
#: an in-band outlier detector, because there is neither an outlier nor a
#: detector. **`REPEATS` stays 5 on this evidence**, and the probe is what can
#: move it.
#:
#: **The denominator is not the noisy part, which rules out the other repair.**
#: `notifications_observed` was *identical* in all 30 runs for every arm
#: (2116 / 1189 / 1143 / 539 / 116), so the entire spread above is in the
#: timing numerator. Raising an arm's notification count would buy quantization
#: and not stability, and for `compute_only` it would destroy the control — an
#: arm that takes no paths is what makes it one.
#:
#: **`reference_app_socket` IS REPRODUCIBLY THE WIDEST OF THE FOUR
#: LOAD-BEARING ARMS, AND THAT IS A PROPERTY OF THE WORKLOAD RATHER THAN A
#: DEFECT IN THE ARM. Established 2026-08-10.** The width is in the table
#: above — widest of the four in all three samples, gap median 7.4 / 7.8 /
#: 10.1% against its widest sibling's 6.0 / 7.0 / 6.8%, gap maximum 26.7 /
#: 34.1 / 31.0% against a sibling ceiling of 14.4 / 18.4 / 19.3%, and range
#: 28.0 / 39.7 / 32.2% against 15.3 / 18.3 / 19.5%. Three for three on every
#: one of the three statistics, so the pattern is not noise about noise. This
#: entry records **which of the two things it is**, because the answers want
#: opposite responses and the arm is one of the four any T101 figure rests on.
#:
#: **The denominator is fixed for this arm as it is for the others, which is
#: the single most decisive check and it comes out clean.**
#: `notifications_observed` takes **exactly one distinct value across all ten
#: draws, in every arm, in all three samples** — 15 of 15 arm-sample cells at
#: one distinct value. For `reference_app_socket` that value is **833 / 835 /
#: 835**. So a moving denominator is ruled out here specifically and not by
#: inheritance from the others, and the whole of this arm's excess width is in
#: the timing numerator. **The recorded field is itself a median of `REPEATS`
#: counts** and the record does not retain the five, so what is established is
#: that the median-of-5 never moved — which is the quantity the rate is
#: computed from and therefore the one that matters.
#:
#: **A fourth sample was taken after the paragraphs below were written and
#: confirms them prospectively, which is the only kind of confirmation this
#: file counts.** Run `31421757875`, the CI run of the commit that first
#: recorded this finding, same runner class, 10 of 10 batteries in 154.7 s.
#: `reference_app_socket` is again the widest of the four at **7.8%** against
#: a widest sibling of 6.2%, **1.26x**; `notifications_observed` is again one
#: distinct value in every arm, **833** for this arm, taking the denominator
#: check to **20 of 20 arm-sample cells**; and the resolution table below
#: reads **459% / 56% / 41% / 6.4%** in the same order on that run. Four for
#: four on a claim that was committed at three, against a draw that did not
#: exist when it was written.
#:
#: **The cause is that this arm extracts the smallest signal from the largest
#: timed region of the four, measured on CI's own artifacts.**
#: `overhead_seconds` as a percentage of the arm's own `baseline_seconds`, from
#: the three runs' `seccomp-overhead.latest.json`:
#::
#:     path_heavy            729%   704%   635%
#:     reference_app_api      83%    64%    62%
#:     shell_heavy            60%    52%    56%
#:     reference_app_socket  7.7%   4.9%   6.6%
#:     compute_only         -6.0%  -4.0%   1.8%   (the control)
#::
#: `reference_app_socket` differences two ~0.7 s medians to recover ~0.05 s.
#: The other three recover between half and seven times their own baseline, an
#: order of magnitude better resolved, and the arm nearest the socket arm's
#: regime is **the control**. `overhead_seconds` is a difference, so a
#: workload's constant cost cancels exactly and only its run-to-run *noise*
#: survives — which means an arm whose absolute noise is large next to the
#: overhead it carries is the widest arm with nothing wrong anywhere. Measured
#: directly on `6.12.76-linuxkit` aarch64 euid 0 at n=25 through this module's
#: own `_run_unsupervised_subprocess`, the workloads' `stdev / overhead` ranks
#: **0.01 / 0.15 / 0.24 / 2.29** for path, api, shell and socket, and that
#: ordering is the observed width ordering of the four on the same host. A
#: ranking that could have come out in any order came out in that one.
#:
#: **The obvious repair was planted and it does not work, which is why it is
#: recorded here rather than installed.** Most of this arm's timed region is
#: not the workload: `socketserver.BaseServer.serve_forever` polls its
#: shutdown flag at a default `poll_interval` of **0.5 s**, so
#: `server.shutdown()` waits out the current `select` and the arm's teardown
#: is **bimodal — ~0.0001 s or ~0.505 s**, 3 and 17 of 20 draws. Phase-timed
#: unsupervised at n=20 on the linuxkit host, that teardown is **78% of the
#: workload's median wall clock and 88% of its peak-to-peak spread**, which
#: makes it look like the whole answer. It is not. Passing
#: `poll_interval=0.01` and repeating the probe at k=10 on one host took the
#: battery's own cost from 12.0 s to 8.47 s and the probe from **134 s to
#: 90 s** — so the dead time is real and was removed — while the arm's gap
#: median moved only **38.0% → 34.0%**, still the widest of the four at
#: **1.76x** its widest sibling against 1.84x before. **The teardown is dead
#: time that cancels out of a difference of medians and is absorbed by the
#: median-of-5; it is not the source of the width.** Both directions are on
#: the record so that the next reader does not remove it, observe no
#: improvement, and conclude the width was an instrument defect after all.
#: `notifications_observed` was unmoved in both directions
#: (2116 / 1189 / 479 / 1143 / 116), so the plant did not buy its result by
#: changing the denominator.
#:
#: **What follows for quoting a figure that rests on this arm.** The four
#: load-bearing arms are **not equally resolved**, and the table above is the
#: statement of by how much. A figure quoted from `reference_app_socket` alone
#: carries roughly an order of magnitude less resolution than the same figure
#: from `path_heavy`, and any headline that pools or minimises across the four
#: is dominated by the worst-resolved of them. The arm stays exactly as it is:
#: it measures the surface an operator's session actually reaches, its width
#: is that surface's own timing noise, and narrowing it by editing the
#: workload would buy a tighter number by measuring something else.
#:
#: **The paragraph above became a rule on 2026-08-10 — `OD-30` publishes T101's
#: figure PER ARM against the same run's measured control, and forbids pooling
#: or minimising across the four outright.** No threshold is installed and
#: `test_a_small_positive_overhead_is_still_published_because_no_floor_is_known`
#: still asserts the refusal.
#: ~~The control arm *is* the floor, so an arm clearing that run's control
#: excursion by orders of magnitude publishes a number and an arm inside it
#: publishes as **not resolved by this instrument**.~~ **Struck 2026-08-10 with
#: limb ③'s revision at `OD-30`: no arm is withheld. Every arm publishes its
#: overhead with the same run's control excursion and the pooled control range
#: beside it, and any overlap with either is stated AS an overlap on the same
#: line as the figure it qualifies.** The comparator that was struck was a
#: per-run maximum, so the set of published arms was a property of the draw —
#: and the quantity it made a bound out of is the one the paragraphs above
#: establish there is *"no single number here to be a floor"* for.
#:
#: **THE MARK NOW TRAVELS INTO THE ARTIFACT AND NOT ONLY THROUGH THIS PROSE —
#: 2026-08-10.** Line-locality in a docstring protects a reader of this module
#: and reaches nobody holding the record. `overhead_against_this_runs_control`
#: and its `_because` sit beside every arm's `overhead_seconds`, carrying the
#: verdict and both ranges on the figure's own line. **The verdict compares
#: like with like** — the arm's difference of medians against the control's
#: difference of medians — and the control's own draw excursion qualifies it
#: rather than deciding it. That split was paid for: for one commit the
#: excursion *was* the comparator, and run `31434583620` returned three of the
#: four load-bearing arms as not clearing while the same run's k=10 probe put
#: all four clear on 10 of 10 draws. A range of raw pairwise differences is a
#: wider statistic than a difference of medians, so the mismatch under-claimed,
#: and an artifact contradicting the better-powered reading of its own
#: instrument is worse than one that says less. **No pooled range is written
#: into the record**: a pooled range is a constant, and a constant here would
#: travel onto hosts it was never measured on, which is what
#: `host_property_caveat` stopped being a hardcoded sentence to end. The pooled
#: half of limb ③ is carried in prose, where a human states its provenance.
#:
#: **`shell_heavy`'s OVERHEAD SITS AT THE SAME ABSOLUTE SCALE AS THE CONTROL'S
#: NOISE, AND IT CLEARS THAT CONTROL ON TWO OF THE FOUR RECORDED SAMPLES.
#: THIS IS A FACT ABOUT Q-09's OWN NAMED ARM AND IT IS STATED HERE RATHER THAN
#: LEFT TO BE INFERRED.** *(The count read `one of the three` until 2026-08-10,
#: when the fourth sample below landed; it is restated in the header rather than
#: only in the block that changed it, because a reader who arrives at this
#: heading by `grep` reads the count here and not four paragraphs down.)*
#: `overhead_seconds` per run against that run's control
#: positive extreme, re-derived from the three `seccomp-variance.latest.json`
#: artifacts at 10 draws per arm:
#::
#:     run           control extreme   shell_heavy overhead   draws above
#:     31415736559       +0.010275 s    0.024945-0.028304 s     10 of 10
#:     31416789165       +0.017368 s    0.014794-0.017791 s      1 of 10
#:     31416959913       +0.029317 s    0.018794-0.022802 s      0 of 10
#::
#: Pooled over all 30 draws the control runs **-0.007711 to +0.029317 s**,
#: non-positive in 9 of them, and `shell_heavy` is **the only one of the four
#: load-bearing arms that overlaps it at all** — 0.014794 to 0.028304 s, inside
#: the control's ceiling — while `path_heavy`, `reference_app_api` and
#: `reference_app_socket` clear it on every draw, at minima of 0.081526,
#: 0.032178 and 0.031767 s. **So a `shell_heavy` figure quoted from this battery
#: is a measurement whose precision is insufficient to separate it from the
#: instrument's own zero reading on two samples of three, and it must not be
#: quoted without that sentence.** It is a measurement rather than an absence,
#: which is why it is published; FR-043's *"marked unvalidated wherever it
#: appears"* discipline is the family it belongs to, and `costs.UNPRICED` — where
#: the quantity's definition rules the value out — is not.
#:
#: **A FOURTH SAMPLE CONFIRMS THIS PROSPECTIVELY AND TIGHTENS IT, WHICH IS THE
#: ONLY KIND OF CONFIRMATION THIS FILE COUNTS.** Run `31427947131`, the CI run of
#: the commit that first recorded the finding above, same runner class, 10 of 10
#: batteries in 150.7 s. Control **-0.012760 to +0.021070 s**; `shell_heavy`
#: **0.024417-0.028696 s**, above that run's control extreme in **10 of 10**
#: draws — so the arm *clears* here, and it clears by **1.16x**, the narrowest
#: margin of the four samples and narrower than the 2.43x of `31415736559`. The
#: three-sample statements above are left standing because they were correct for
#: their sample; what the fourth changes is the count, to **two of four
#: published and two of four withheld** under the struck rule. Pooled over all
#: **40** draws the control runs **-0.012760 to +0.029317 s**, non-positive in
#: **14**, and `shell_heavy` is **still the only one of the four load-bearing
#: arms that overlaps it** at 0.014794-0.028696 s. **A claim that could have
#: come back either way came back confirming the arm sits at the control's own
#: scale**, and the margin moving to 1.16x is the direction that makes the
#: disclosure matter more rather than less.
#:
#: **This arm is not the one at risk, and that is the one place reading the two
#: quantities as one inverts the answer.** Resolution — overhead as a share of
#: an arm's own baseline — is where `reference_app_socket` is worst, and it is
#: what the table above measures. The withheld-arm question tested *absolute*
#: overhead against the control's *absolute* excursion, and on that quantity
#: this arm clears its own run's control in all three samples.
#: ~~It recovers **~0.05 s** against a control whose widest observed positive
#: extreme over the three samples is **+0.029317 s**.~~ **Struck 2026-08-10: that
#: sentence spliced two runs.** The ~0.05 s is `31415736559`'s figure and
#: +0.029317 s is `31416959913`'s control, and this file's own rule is that the
#: comparison is made within one run. Taken within each run this arm clears by
#: factors of 5.34, 1.83 and 1.23 — so it does clear, three for three, but the
#: margin on the widest-control sample is **1.23** and not the order of
#: magnitude the spliced pair implied.
#:
#: ~~`notifications_observed` was *identical* in all 30 runs for every arm
#: (2116 / 1189 / 1143 / 539 / 116)~~ **The 30-run list above is read in this
#: file's own arm order and its middle two entries do not survive a re-reading
#: on the same host — flagged 2026-08-10, and deliberately not rewritten.** In
#: the k=10 readings taken here on `6.12.76-linuxkit` aarch64 euid 0, the same
#: container and the same CPython, `path_heavy`, `reference_app_api` and
#: `compute_only` reproduce that list exactly at **2116 / 1189 / 116**, while
#: `shell_heavy` reads **479** and `reference_app_socket` reads **1143** — so
#: the value the list assigns to `shell_heavy` is the one this host gives
#: `reference_app_socket`. Three of five matching exactly makes a transposition
#: of the middle pair likelier than three independent drifts, but **539 is not
#: reproduced by anything measured here** *(superseded 2026-08-10 — it is
#: reproduced, by a committed artifact rather than by a run taken here; the
#: identification is below)* and the 30-run sample cannot be
#: re-read, so the list is left standing with this note rather than corrected
#: to figures its own pass never took. **The paragraph's conclusion is
#: unaffected either way**: every value was identical across all 30 runs, which
#: is what ruled the denominator out, and that holds under any assignment of
#: the two.
#:
#: ~~**539 is not reproduced by anything measured here**~~ **539 IS reproduced,
#: and by a committed artifact rather than by a new run: it is `shell_heavy`'s
#: own `notifications_observed` in `tests/batteries/results/seccomp-overhead.json`
#: — identified 2026-08-10, and the transposition reading above is completed
#: rather than replaced.** That record was written 2026-08-03 by `d1f7d7a` on the
#: same kernel, the same architecture and the same CPython as the re-reading, and
#: it holds `compute_only` 116, `path_heavy` 2116 and `shell_heavy` **539**. So
#: every one of the 30-run list's five values is a real reading of a distinct
#: arm — `path_heavy` 2116, `reference_app_api` 1189, `reference_app_socket`
#: 1143, `shell_heavy` 539, `compute_only` 116 — and the list is a correct
#: *multiset* written into this file's own table order with its middle pair
#: **transposed**. Nothing is unaccounted for and no value was invented.
#:
#: **What the identification does not settle is why `shell_heavy` re-reads at
#: 479, and that stays open rather than being assigned to the obvious cause.**
#: The two records differ in their watched set — twelve syscalls in the 2026-08-03
#: record against sixteen in the re-reading, the four added being `renameat`,
#: `symlinkat`, `linkat` and `utimensat`, which joined on 2026-08-04 by
#: `46fd6b5`. **That change predicts the count moving *up*, and it moved down**,
#: so the watch set is not established as the cause and is not recorded as one.
#: What *is* established is a dating consequence: 539 belongs to the twelve-syscall
#: era, so it cannot be a reading from the 2026-08-10 sample the list is attached
#: to, and the list is a splice across that boundary rather than one sample's
#: output. **The list is still not corrected to figures its own pass never
#: took** — the transposed order is left standing with this note, on the same
#: ground as before, and the paragraph's conclusion is unaffected for the third
#: time.
REPEATS = 5

# --- the workloads --------------------------------------------------------

# Shell-heavy: process spawn plus the path resolution every exec performs. This
# is the arm Q-09 names, because an agent that composes shell commands pays
# this cost on every one of them.
SHELL_HEAVY = textwrap.dedent(
    """
    import subprocess
    for _ in range(30):
        subprocess.run(['/bin/sh', '-c', 'true'], check=True)
    """
)

# Path-heavy without exec: isolates the per-notification cost from the cost of
# spawning a process, which the shell arm conflates.
PATH_HEAVY = textwrap.dedent(
    """
    import os
    for i in range(2000):
        try:
            os.stat('/etc/hostname')
        except OSError:
            pass
    """
)

# Compute-only: the control. Takes no paths, so the filter never fires. If this
# arm slows down, the numbers above are measuring something other than
# interception.
COMPUTE_ONLY = textwrap.dedent(
    """
    total = 0
    for i in range(4_000_000):
        total += i
    """
)

# --- the reference application (T116) -------------------------------------
#
# The two arms `app.py` names, and the reason there are two: an overhead figure
# and a safety assertion must be measurements of one program, and T116's
# `test_the_origin_serves_the_same_bytes_the_in_process_call_returns` is what
# holds these two surfaces to that. Measuring only the socket arm would fold
# the HTTP stack's cost into the application's; measuring only the in-process
# arm would leave the surface an operator actually reaches unmeasured.
#
# The paths are interpolated at run time and are never written down: an
# absolute path into somebody's checkout does not belong in a committed file,
# and a relative one would depend on the subprocess's working directory.
_REFAPP_PREAMBLE = """
import sys
sys.path.insert(0, {repo!r})
sys.path.insert(0, {refapp!r})
import app, seed
"""

# The in-process API sequence. State is re-read each round on purpose — that
# read is the reference application's real filesystem contact, and hoisting it
# out of the loop would leave an arm that touches no path after import and
# measures the interpreter's startup instead.
REFERENCE_APP_API = _REFAPP_PREAMBLE + """
for _ in range(40):
    a = app.Application(seed.load_state())
    a.call('GET', '/health')
    a.call('GET', '/parts')
    a.call('GET', '/parts/P-0007')
    a.call('GET', '/shipments?part_id=P-0003')
    a.call('GET', '/shipments?part_id=P-0011')
"""

# The socket arm: the same operations over `build_server`, which is the surface
# an operator's session actually reaches.
REFERENCE_APP_SOCKET = _REFAPP_PREAMBLE + """
import json, threading, urllib.request
a = app.Application(seed.load_state())
server = app.build_server(a, host='127.0.0.1', port=0)
host, port = server.server_address[0], server.server_address[1]
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()
base = 'http://%s:%d' % (host, port)
try:
    for _ in range(40):
        for path in ('/health', '/parts', '/parts/P-0007',
                     '/shipments?part_id=P-0003', '/shipments?part_id=P-0011'):
            with urllib.request.urlopen(base + path, timeout=10) as r:
                json.loads(r.read().decode('utf-8'))
finally:
    server.shutdown()
    server.server_close()
"""


def _reference_app_source(template: str) -> str:
    return template.format(repo=str(REPO), refapp=str(REFAPP_DIR))


# --- which file a run writes, and why the branch is a function -------------

#: Q-09's *recorded* figure. **Tracked in git**, which is the whole reason the
#: two names below have to be told apart: `DURABLE_RECORD.is_file()` is true on
#: a fresh checkout, so an assertion built on it cannot fail for the reason a
#: test named "the measurement is recorded" claims to check. It was one, until
#: 2026-08-10.
DURABLE_RECORD = "seccomp-overhead.json"

#: What an ordinary privileged run produces. Gitignored, so its presence is a
#: statement about *this* run and not about the checkout.
LATEST_RECORD = "seccomp-overhead.latest.json"

#: The environment variable that promotes a run's figure to the recorded one.
RECORD_REQUEST = "F2A_RECORD_MEASUREMENTS"


def record_filename(environ: Mapping[str, str]) -> str:
    """Which of the two files *this* run writes, read from the environment.

    A function rather than an `if` inside the fixture, and it is the same
    argument `host_property_caveat` is: the branch has to be reachable from a
    test that runs on hosts this module cannot run on. It is also the only
    copy — a test that re-implemented the branch in order to check it would
    agree with itself while both halves drifted, which is the shape
    `tools/README.md` records as a stricter second opinion reporting rot it
    invented.

    Recording is **conditional by design** (see the fixture), so the honest
    question is never "does a file exist" but "does the file this run was asked
    for exist". Both branches produce something, so neither is a skip.
    """
    return DURABLE_RECORD if environ.get(RECORD_REQUEST) == "1" else LATEST_RECORD


# --- the rate, and the reason an arm may not have one ----------------------

#: Why an arm publishes no `microseconds_per_notification`, keyed by the reading
#: that withheld it.
#:
#: **Shape borrowed from `src/runtime/providers/costs.py`'s `UNPRICED`, and for
#: its reason rather than its style.** That table exists because a missing price
#: written as `0.0` is indistinguishable from a turn that cost nothing, and the
#: repair was `spend_usd: float | None` plus a recorded reason for every
#: absence. A rate is the same kind of quantity: `microseconds_per_notification`
#: is the one field here the module's own docstring calls *transferable*, so a
#: number standing where no rate could be computed is a figure that invites
#: subtraction and gets it.
#:
#: **An absence is recorded rather than left as a gap**, because a bare `null`
#: reads as an oversight and the next reader fills it in.
UNRATED: Mapping[str, str] = {
    "no-notifications": (
        "No notifications were observed, so there is no denominator. The "
        "overhead figure beside this stands on its own; a per-notification "
        "rate over zero notifications is not a smaller number, it is not a "
        "number."
    ),
    "non-positive-overhead": (
        "The supervised median came out at or below its own baseline, so the "
        "difference is not an overhead and no rate is derivable from it. "
        "Supervision is strictly additional work — an ioctl and a "
        "/proc/<pid>/mem read per notification — so a non-positive difference "
        "cannot be a measurement of its cost; it is evidence that the cost is "
        "below what this instrument resolves against run-to-run variation on "
        "this host. **The boundary is zero because the quantity's definition "
        "forbids crossing it, and for no other reason.** This is deliberately "
        "not a noise threshold: this battery has no measured noise floor, and "
        "a chosen one would be a fabricated constant silently deciding which "
        "figures get published. The consequence is stated rather than hidden — "
        "a *small positive* difference on this host is equally dominated by "
        "variation and this test does publish a rate for it. Closing that "
        "needs a measured floor, which is a measurement nobody has taken, and "
        "the honest form of not having it is a one-sided detector rather than "
        "an invented bound. **This is a property of the instrument and not of "
        "a runner, which is why it is fixed here rather than reported as CI "
        "flakiness.** CI run 31403771772 published ratio 0.9066, "
        "overhead -0.03922s and -502.82 microseconds per notification for the "
        "compute_only control over 78 notifications; 30 sequential runs on an "
        "unrelated host — 6.12.76-linuxkit aarch64, euid 0, 10 CPUs, "
        "2026-08-10 — put the same arm at or below zero in 3 of 30, low "
        "-0.022496s. A control that flips sign on two hosts of different "
        "architecture and kernel is the measurement doing this, not a noisy "
        "neighbour."
    ),
}


def notification_rate(
    overhead_seconds: float, notifications_observed: float
) -> tuple[float | None, str | None]:
    """The transferable figure, or the key in `UNRATED` naming its absence.

    Takes the **rounded** overhead the record publishes rather than the raw
    difference, so that the sign of `overhead_seconds` and the presence of a
    rate can never disagree in one artifact, and so a reader holding the record
    can re-derive one field from the other two.
    """
    if not notifications_observed:
        return None, "no-notifications"
    if overhead_seconds <= 0:
        return None, "non-positive-overhead"
    return round(overhead_seconds / notifications_observed * 1e6, 2), None


# --- did this arm clear its own run's control ------------------------------

#: The arm every other arm is read against. Named rather than positional
#: because the loop below is ordered for readability and an index into it
#: would silently re-point if anyone reordered the workloads.
CONTROL_ARM = "compute_only"


def observed_excursion(
    baseline_samples: list[float], supervised_samples: list[float]
) -> tuple[float, float]:
    """The tightest interval containing every difference this run's draws form.

    **A reading, and the scope of the reading is the whole of what makes it
    honest.** `overhead_seconds` is one median minus one median, so a record
    that carried only it would describe the control as a point and invite a
    reader to treat that point as a floor. It is not a point: these are
    `REPEATS` draws either side, and the widest difference they can form is
    `max(supervised) - min(baseline)` while the narrowest is
    `min(supervised) - max(baseline)`.

    **This is NOT the across-battery excursion the module's docstring quotes
    from `seccomp_variance_probe.py`**, and conflating the two is the splice
    this file has already struck a sentence for. The probe repeats the whole
    battery k times and reports the spread of k medians; this is the spread
    *within* one battery's own draws. They are different quantities on
    different scopes and neither stands for the other. What this one is good
    for is the only comparison a single battery run can make without reaching
    for a number it did not measure.

    The interval is deliberately the widest the draws admit rather than a
    standard error or a percentile. A narrower one would be a chosen bound,
    and a chosen bound is the fabricated constant
    `UNRATED["non-positive-overhead"]` refuses at length.

    **This is a qualifier and NOT the verdict's comparator, and the distinction
    was paid for.** It was the comparator for one commit. A range of raw
    pairwise differences is a wider statistic than the difference of two
    medians every arm publishes, so testing one against the other is a
    mismatch that runs one way: it under-claims. Run 31434583620 made that
    concrete — three of the four load-bearing arms came back as not clearing,
    against the same run class's probe analysis where all four clear on 10 of
    10 draws. An artifact that contradicts the better-powered reading of the
    same instrument is worse than one that stays quiet, so the verdict moved
    to the like-for-like comparison and this interval stayed on as what it
    honestly is: a statement of how far this run's control draws roamed, which
    is the second range limb ③ asks to be stated as an overlap where one
    exists.
    """
    return (
        round(min(supervised_samples) - max(baseline_samples), 6),
        round(max(supervised_samples) - min(baseline_samples), 6),
    )


#: Why an arm's overhead stands where it does relative to its own run's
#: control, keyed by the reading that put it there.
#:
#: **Four keys and not a boolean, and the reason is the T206 shape.** A
#: `cleared: true/false` field would map three distinguishable readings onto
#: one value: the control compared with itself, an arm with no overhead to
#: clear anything with, and an arm whose overhead the control's own excursion
#: swallows. Those want different responses from a reader — the first is a
#: definitional non-answer, the second is an instrument that resolved nothing,
#: the third is a real figure that is not separated from zero — and a boolean
#: hands all three back as `false`, which reads as *the mechanism was measured
#: and found not to clear*. Only one of the three says that.
#:
#: **Shape borrowed from `UNRATED` directly above**, which exists because a
#: withheld quantity written as a bare `null` reads as an oversight. The same
#: argument applies one level out: a record that carried `overhead_seconds`
#: and nothing about the control leaves an artifact consumer lifting the bare
#: figure, which is the FR-058 defect — the reader takes the result and never
#: reaches the trace. Prose in this file cannot reach that reader.
CLEARANCE: Mapping[str, str] = {
    "clears-this-runs-control": (
        "The arm's overhead stands above the same run's control overhead. The "
        "two are the SAME statistic — a median of REPEATS supervised draws "
        "minus a median of REPEATS baseline draws — so the comparison is like "
        "for like, which is the property that makes it a comparison at all. "
        "Whether the margin survives the control's own draw-to-draw roaming is "
        "stated on the line beside it, because a median-of-REPEATS difference "
        "is one draw of a noisy quantity and a single battery observes no "
        "excursion of it. The across-battery excursion is what "
        "`tools/seccomp_variance_probe.py` measures over k repeats and this "
        "record does not carry it. A margin measured here is a property of "
        "this run and does not transfer to another."
    ),
    "does-not-clear-this-runs-control": (
        "The arm's overhead does not stand above the same run's control "
        "overhead, compared like for like as two differences of medians, so "
        "this run does not separate the figure from the instrument's own zero "
        "reading. The figure is published rather than withheld — it is a "
        "measurement and not an absence — and this field is the sentence that "
        "must travel with it. No threshold decided this: the comparator is the "
        "control's own measured figure on this run and there is no floor "
        "constant anywhere in this record."
    ),
    "is-this-runs-control": (
        "This arm IS the control, so the comparison is the control against "
        "itself and its outcome is a property of arithmetic rather than of "
        "syscall interception. The field records that rather than reporting a "
        "clearance, because a control that 'cleared itself' and a control that "
        "'failed to clear itself' would both be read as findings about the "
        "supervisor, and neither is one. The control's own excursion is the "
        "comparator every other arm on this record was read against."
    ),
    "no-overhead-to-clear-with": (
        "The arm's own overhead came out non-positive, so there is no overhead "
        "to clear anything with and no clearance is stated. This is a distinct "
        "reading from an overhead the control swallows: there the instrument "
        "resolved a cost and could not separate it, here it resolved no cost "
        "at all. The two share a remedy in neither direction, which is why "
        "they are not one value. `microseconds_per_notification_absent_because` "
        "beside this carries the same run's reasoning for the missing rate."
    ),
}


def control_clearance(
    overhead_seconds: float,
    control_overhead_seconds: float,
    control_excursion: tuple[float, float],
    is_the_control: bool,
) -> tuple[str, str]:
    """The key in `CLEARANCE`, and the sentence that carries this run's numbers.

    Two returns rather than one, and the second is the load-bearing half. The
    key is greppable and the prose behind it is fixed; **the sentence is where
    the figures sit**, and they sit there because limb ③'s rule is that an
    overlap is stated ON THE LINE of the figure it qualifies. A reader who
    arrives at an arm by `grep` reads that arm's fields and no banner — which
    is the defect the `dry-run-verdict` artifact shipped, disclosing itself in
    a banner and a directory name while its decision row still read as a
    headline.

    **TWO ranges stand beside the figure and they answer different questions**,
    which is limb ③'s shape rather than a decoration on it. The verdict tests
    the arm's overhead against the control's overhead, like for like. The
    control's own draw excursion is the second range, and where the arm's
    figure falls inside it that is stated AS an overlap in the same sentence —
    so a margin that the control's own draws could have produced by roaming
    never reads as a clean clearance.

    A pure function of readings, so it is checkable on hosts this module
    cannot run on — the same argument `record_filename`, `notification_rate`
    and `host_property_caveat` are each written under, and the reason all four
    of their tests live in `tests/unit/`.
    """
    low, high = control_excursion
    against = f"this run's control overhead of {control_overhead_seconds:+f} s"
    roam = f"the control's own draw excursion of {low:+f} to {high:+f} s"
    if is_the_control:
        key = "is-this-runs-control"
        reading = f"{overhead_seconds:+f} s of overhead, which IS {against}"
    elif overhead_seconds <= 0:
        key = "no-overhead-to-clear-with"
        reading = (
            f"{overhead_seconds:+f} s of overhead, non-positive, against {against}"
        )
    else:
        if overhead_seconds > control_overhead_seconds:
            key = "clears-this-runs-control"
            margin = (
                f" — clearing it by {overhead_seconds / control_overhead_seconds:.2f}x"
                if control_overhead_seconds > 0
                else " — and the control's own figure is non-positive on this run"
            )
        else:
            key = "does-not-clear-this-runs-control"
            margin = " — NOT clearing it"
        # The second range, and the overlap stated as an overlap on this same
        # line. A reader who lifts the margin without this clause is the
        # reader line-locality exists for.
        qualifier = (
            f", and OVERLAPPING {roam}, so this run's own control draws roamed "
            "far enough to have produced a difference this size"
            if low <= overhead_seconds <= high
            else f", and standing clear of {roam}"
        )
        reading = (
            f"{overhead_seconds:+f} s of overhead against "
            f"{against}{margin}{qualifier}"
        )
    return key, f"{reading}. {CLEARANCE[key]}"


#: Recorded in the result file rather than only in the docstring, because the
#: artifact outlives the module a reader would otherwise have to go and find.
SHELL_HEAVY_ABSENCE = (
    "There is NO shell-heavy arm of the reference application, and the "
    "absence is deliberate. T101's shell-heavy clause is discharged by the "
    "`shell_heavy` arm above. The reference application composes no shell "
    "command and spawns no process — asserted by "
    "tests/unit/test_reference_app.py::"
    "test_the_reference_application_spawns_no_process — so an arm wrapping it "
    "in `sh -c` would measure sh's process spawn and the client's, attribute "
    "both to the reference application, and reproduce the proxy figure under "
    "the fixture's name. If that assertion ever fires, this clause reopens."
)


# --- what the figure is a property of, read rather than asserted -----------
#
# Kernel-release substrings that positively identify a virtualized or cloud
# guest kernel, each with the reason it is here. **This is a closed accepting
# set and never a complement**, which `tools/README.md` records as the shape
# two containment checks nearly shipped with: "any errno but EPERM", then "the
# two errnos differ", each of which would have reported a refusing host as a
# working one. The tempting complement here is "no marker, therefore bare
# metal", and it is wrong for the same reason — the space of kernel flavours is
# open, and a host nobody anticipated would be classified by the branch nobody
# checked. So a match means *known guest*; everything else means *undetermined*
# and says so.
#
# The residual error is one-sided by construction: a bare-metal host running a
# kernel whose release string happens to contain one of these is over-warned.
# Over-warning a reader who is about to compare two figures costs a sentence.
# Under-warning them is the defect this table exists to end.
VIRTUALIZATION_MARKERS: dict[str, str] = {
    "linuxkit": "Docker Desktop's linuxkit VM",
    "azure": "an Azure hypervisor guest, which is what GitHub's hosted runners are",
    "aws": "an AWS EC2 guest",
    "gcp": "a Google Compute Engine guest",
    "cloud": "a distribution 'cloud' kernel flavour, which is built for guests",
    "microsoft": "WSL2's Microsoft kernel, a guest under a Windows host",
}


def host_property_caveat(kernel: str, machine: str, euid: int) -> str:
    """The first entry of `what_this_is_a_property_of`, built from readings.

    Three arguments, because three things are all this process can honestly
    observe about the machine underneath it: the kernel release, the
    architecture, and the privilege the measurement ran with. It deliberately
    does **not** take a host category, and it does not derive one — see the
    table above for why the unmarked branch declines to guess.
    """
    matched = sorted(
        marker for marker in VIRTUALIZATION_MARKERS if marker in kernel.lower()
    )
    where = (
        f"Kernel {kernel} on {machine}, measured at euid {euid}. "
    )
    if matched:
        named = "; ".join(VIRTUALIZATION_MARKERS[marker] for marker in matched)
        what = (
            f"That release string names {named}, so this is a figure from a "
            "virtualized kernel and not from a bare Linux host. "
        )
    else:
        known = ", ".join(sorted(VIRTUALIZATION_MARKERS))
        what = (
            "That release string carries none of the virtualization markers "
            f"this record knows how to recognise ({known}) — which is not "
            "evidence of hardware. Nothing this process can observe "
            "establishes whether the kernel is running on metal or in a "
            "guest, so the figure is a property of this kernel and not of a "
            "hardware class. "
        )
    return where + what + (
        "Syscall-interception overhead is the measurement most sensitive to "
        "that difference and it may not transfer. Two records taken on "
        "different kernels are not a before and an after and must not be "
        "subtracted."
    )


def property_caveats(kernel: str, machine: str, euid: int) -> list[str]:
    """Everything the figure is a property of: one reading, then four
    constants.

    The split is the point. The first entry varies with the host because it is
    a statement *about* the host; the rest are claims about the supervisor,
    the response flag and the workloads, which are properties of this file and
    would be just as true on any machine.
    """
    return [
        host_property_caveat(kernel, machine, euid),
        "A CPython supervisor doing one ioctl and one /proc/<pid>/mem read "
        "per notification. A Go or C supervisor would be faster by an "
        "unmeasured amount.",
        "Five workloads. `shell_heavy`, `path_heavy` and `compute_only` "
        "are proxies; `reference_app_api` and `reference_app_socket` "
        "drive T116's reference application over the two surfaces app.py "
        "names. The reference application existed from 2026-08-08; the "
        "earlier record here said it did not, which was true when it was "
        "written and is superseded.",
        "SECCOMP_USER_NOTIF_FLAG_CONTINUE as the response. A supervisor "
        "that denied or rewrote arguments would pay more.",
        "An interpreter start per round. Every arm pays it in both the "
        "baseline and the supervised run, so it cancels out of "
        "overhead_seconds and inflates notifications_observed — which is "
        "why microseconds_per_notification is the transferable figure and "
        "`ratio` is not.",
    ]


def _run_plain(source: str) -> float:
    started = time.perf_counter()
    pid = os.fork()
    if pid == 0:
        try:
            exec(compile(source, "<workload>", "exec"), {"__name__": "__main__"})
        finally:
            os._exit(0)
    os.waitpid(pid, 0)
    return time.perf_counter() - started


def _run_supervised(source: str) -> tuple[float, int]:
    observed = 0

    def count(_attempt: seccomp.Attempt) -> None:
        nonlocal observed
        observed += 1

    argv = [sys.executable, "-c", source]
    started = time.perf_counter()
    pid, listener = seccomp.spawn_with_listener(argv, count)
    os.waitpid(pid, 0)
    elapsed = time.perf_counter() - started
    time.sleep(0.05)
    listener.stop()
    return elapsed, listener.observed


def _run_unsupervised_subprocess(source: str) -> float:
    """The honest baseline for the supervised arm: same `execve`, no filter."""
    argv = [sys.executable, "-c", source]
    started = time.perf_counter()
    pid = os.fork()
    if pid == 0:
        os.execv(argv[0], argv)
    os.waitpid(pid, 0)
    return time.perf_counter() - started


@pytest.fixture(scope="module")
def measurement() -> dict:
    arms = {}
    excursions = {}
    for name, source in (
        ("shell_heavy", SHELL_HEAVY),
        ("path_heavy", PATH_HEAVY),
        (CONTROL_ARM, COMPUTE_ONLY),
        ("reference_app_api", _reference_app_source(REFERENCE_APP_API)),
        ("reference_app_socket", _reference_app_source(REFERENCE_APP_SOCKET)),
    ):
        # The draws are kept rather than collapsed on sight, because the
        # control's excursion is a property of the draws and `_median` threw
        # them away. The published `baseline_seconds` is the same median of
        # the same draws it always was.
        baseline_samples = [
            _run_unsupervised_subprocess(source) for _ in range(REPEATS)
        ]
        baseline = statistics.median(baseline_samples)
        supervised_samples = [_run_supervised(source) for _ in range(REPEATS)]
        supervised = statistics.median(t for t, _ in supervised_samples)
        observed = statistics.median(n for _, n in supervised_samples)
        overhead = round(supervised - baseline, 6)
        rate, unrated = notification_rate(overhead, observed)
        excursions[name] = observed_excursion(
            baseline_samples, [t for t, _ in supervised_samples]
        )
        arms[name] = {
            "baseline_seconds": round(baseline, 6),
            "supervised_seconds": round(supervised, 6),
            # **Kept as a raw reading even when it is below 1.0, and the rate
            # beside it is not.** The ratio and the overhead are two measured
            # medians and their quotient and difference; they are what this run
            # observed and suppressing them would be discarding a reading. The
            # rate is *derived*, and its derivation is only valid where the
            # difference is an overhead.
            "ratio": round(supervised / baseline, 4) if baseline else None,
            "overhead_seconds": overhead,
            "notifications_observed": observed,
            "microseconds_per_notification": rate,
            # Always present, `null` where a rate was published. A key that
            # appeared only on the suppressing branch would be a key no reader
            # knows to grep for.
            "microseconds_per_notification_absent_because": (
                None if unrated is None else UNRATED[unrated]
            ),
        }

    # A second pass, because the comparator is another arm and the loop above
    # reaches the control third. Every arm is annotated against the SAME run's
    # control, which is the scope limb ③ names — a figure read against some
    # other run's control would be the splice this file has already struck.
    control_excursion = excursions[CONTROL_ARM]
    control_overhead = arms[CONTROL_ARM]["overhead_seconds"]
    for name, arm in arms.items():
        key, sentence = control_clearance(
            arm["overhead_seconds"],
            control_overhead,
            control_excursion,
            name == CONTROL_ARM,
        )
        # Beside the figure it qualifies rather than in a header, and always
        # present rather than only on the overlapping branch — a key that
        # appeared only when there was bad news is a key no reader knows to
        # grep for, which is the argument
        # `microseconds_per_notification_absent_because` is already written
        # under one field up.
        arm["overhead_against_this_runs_control"] = key
        arm["overhead_against_this_runs_control_because"] = sentence

    record = {
        "question": "Q-09",
        "task": "T101",
        "measured_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "repeats_per_arm": REPEATS,
        # The comparator every arm above was read against, published once so a
        # consumer can re-derive any arm's verdict from the two fields beside
        # it rather than taking the verdict on trust. The per-arm sentence
        # carries it too, and the duplication is deliberate: this key serves a
        # machine reading the record whole, the sentence serves a reader who
        # arrived at one arm.
        "control_excursion_seconds": list(excursions[CONTROL_ARM]),
        "control_excursion_is_a_property_of": (
            "The within-battery spread of the "
            f"{CONTROL_ARM} arm's own {REPEATS} draws on this run — the widest "
            "difference they can form, low and high. It is NOT the "
            "across-battery excursion `tools/seccomp_variance_probe.py` "
            "reports, which repeats this whole battery k times and spreads k "
            "medians; the two are different quantities on different scopes and "
            "neither stands for the other. No pooled range from any other run "
            "appears in this record, because a pooled range is a constant and "
            "a constant written here would travel onto hosts it was never "
            "measured on — which is the defect `what_this_is_a_property_of[0]` "
            "stopped being a hardcoded sentence in order to end."
        ),
        "arms": arms,
        "environment": {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "kernel": platform.release(),
            # Recorded because the caveat below is built from it, and a
            # caveat quoting a reading the record does not carry cannot be
            # re-derived by anyone holding the artifact.
            "euid": os.geteuid(),
            "python": sys.version.split()[0],
            "cpu_count": os.cpu_count(),
            "audit_arch": hex(_linux.audit_arch()),
            "watched_syscalls": sorted(_linux.path_taking_syscalls()),
        },
        "shell_heavy_on_the_reference_application": SHELL_HEAVY_ABSENCE,
        "what_this_is_a_property_of": property_caveats(
            platform.release(), platform.machine(), os.geteuid()
        ),
    }
    RESULTS.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(record, indent=2, sort_keys=True) + "\n"

    # The committed record is Q-09's *recorded* measurement. Overwriting it on
    # every privileged run replaced a deliberate figure with whichever run
    # happened last — so a reviewer could not tell an intentional
    # re-measurement from a suite that ran in CI, and a real regression would
    # arrive as ordinary run-to-run noise in a file nobody reads twice.
    # Re-recording is now something you ask for.
    (RESULTS / record_filename(os.environ)).write_text(serialized)
    return record


def test_this_runs_measurement_reached_the_file_it_was_asked_for(
    measurement,
) -> None:
    """~~`assert (RESULTS / "seccomp-overhead.json").is_file()`~~

    **Struck 2026-08-10: that assertion could not fail for the reason its own
    name gave.** `seccomp-overhead.json` is *tracked in git*, so it is present
    on a fresh checkout and the test passed whether or not the run recorded
    anything. What an ordinary run produces is `seccomp-overhead.latest.json`,
    and the durable file is written only when `F2A_RECORD_MEASUREMENTS=1` — so
    on every CI run to date this was an existence check against a file the run
    never touched. That is the silent-instrument family this repository keeps
    finding: `ci.yml`'s own header counts *"six instruments that produced a
    clean bit over a measurement that was absent, replayed or unnamed"*, and
    `tools/README.md` counts *"four instruments ... hardened in one week for the
    same defect"*. Neither number includes this one. `ci.yml` also already
    reasons correctly one level up about this very file: *"the file is missing
    exactly when the measurement did not happen."*

    Two things are asserted rather than one, because existence alone would
    close only half of it:

    - **The file this run was asked for**, chosen by `record_filename` from the
      environment. That is what separates *recording was not requested* from
      *recording was requested and did not happen* — the second fails here, the
      first cannot arise, because both branches write something. **No skip**: a
      test that skipped when the variable was unset would go silent on exactly
      the configuration CI runs under, which is the same defect wearing
      different clothes.
    - **That it holds this run's record**, not any record. Existence is still
      vacuous on the `F2A_RECORD_MEASUREMENTS=1` branch, for the original
      reason — the target is tracked. Content equality is not: the committed
      file is a 2026-08-03 linuxkit measurement and no fresh run reproduces it.
    """
    requested = os.environ.get(RECORD_REQUEST)
    path = RESULTS / record_filename(os.environ)
    assert path.is_file(), (
        f"the fixture completed a measurement and left nothing at {path.name}. "
        f"With {RECORD_REQUEST}={requested!r} that is the file this run was "
        "asked to write, so the measurement happened and the recording did "
        "not."
    )
    assert json.loads(path.read_text()) == measurement, (
        f"{path.name} exists but does not hold the record this run produced. "
        "The file is therefore left over from an earlier run — or the fixture "
        "wrote the other one of the two names — and reading it as this "
        "measurement is how a stale figure gets quoted as a fresh one."
    )
    print("\n" + json.dumps(measurement["arms"], indent=2))
    print("\nenvironment: " + json.dumps(measurement["environment"], indent=2))


def test_the_records_caveat_is_re_derivable_from_the_environment_it_carries(
    measurement,
) -> None:
    """The one step `tests/unit/test_seccomp_overhead_caveat.py` cannot reach.

    That file injects environment values, so it proves the caveat is a
    function of its arguments; it cannot prove the *fixture* passes this
    host's readings rather than somebody's favourite constants. Here the
    record is regenerated from the environment block the record itself
    carries, and the two must agree — which is only checkable where the
    fixture actually runs.

    Deliberately not named by a removal proof: this module is `linux_only` and
    `privileged`, so such a proof would report SKIPPED on every host that
    cannot run it.
    """
    environment = measurement["environment"]
    assert measurement["what_this_is_a_property_of"] == property_caveats(
        environment["kernel"], environment["machine"], environment["euid"]
    )


def test_the_filter_actually_fired_so_the_numbers_mean_something(
    measurement,
) -> None:
    """A measured overhead of zero because nothing was intercepted is not a
    measurement of the mechanism."""
    assert measurement["arms"]["path_heavy"]["notifications_observed"] > 1000
    assert measurement["arms"]["shell_heavy"]["notifications_observed"] > 100


def test_the_compute_control_shows_the_overhead_is_attributable(
    measurement,
) -> None:
    """The control arm. Takes no paths, so the filter never fires.

    If this moved with the others, every number here would be a property of
    the VM's scheduler rather than of interception, and the corpus has made
    that mistake before.
    """
    control = measurement["arms"]["compute_only"]
    assert control["notifications_observed"] < 200, (
        f"the compute-only arm triggered {control['notifications_observed']} "
        "notifications; it is not a control"
    )
    path_ratio = measurement["arms"]["path_heavy"]["ratio"]
    assert path_ratio > control["ratio"], (
        f"the path-heavy arm ({path_ratio}x) is not slower than the "
        f"compute-only control ({control['ratio']}x), so the overhead is not "
        "attributable to syscall interception"
    )


def test_the_reference_application_arms_ran_and_fired_the_filter(
    measurement,
) -> None:
    """T101's outstanding clause: the figure on the **reference application**,
    not on a proxy for one.

    Both surfaces `app.py` names are measured. A zero-notification arm here
    would mean the workload never reached the state on disk, which is the
    reference application's only filesystem contact and therefore the only
    thing the supervisor has to intercept.
    """
    for name in ("reference_app_api", "reference_app_socket"):
        arm = measurement["arms"][name]
        assert arm["notifications_observed"] > 100, (
            f"the {name} arm triggered {arm['notifications_observed']} "
            "notifications; it did not reach the application's state"
        )
        assert arm["microseconds_per_notification"] is not None


def test_the_absence_of_a_shell_heavy_reference_arm_is_recorded(
    measurement,
) -> None:
    """The clause T101 asks for and this file declines to build, recorded with
    its reasoning rather than dropped quietly."""
    recorded = measurement["shell_heavy_on_the_reference_application"]
    assert "spawns no process" in recorded
    assert "shell_heavy" in measurement["arms"]


def test_overhead_is_reported_not_asserted_against_a_threshold(
    measurement,
) -> None:
    """Q-09 owes a figure, not a pass mark.

    There is no threshold here on purpose. Inventing one would be exactly the
    unvalidated number FR-043 exists to prevent, and the decision Q-09 records
    — commit the mechanism, or fall back to an audit channel — is the owner's
    to make against the recorded figure.
    """
    for name, arm in measurement["arms"].items():
        assert arm["ratio"] is not None, f"{name} produced no ratio"


def test_no_arm_publishes_a_rate_its_own_overhead_contradicts(
    measurement,
) -> None:
    """The record's two derived fields agree, on this host's actual readings.

    `tests/unit/test_seccomp_overhead_record.py` proves `notification_rate` has
    this property against injected values; it cannot prove the *fixture* routes
    the arms through it. This is the same gap
    `test_the_records_caveat_is_re_derivable_from_the_environment_it_carries`
    closes for the caveat, and it is closable only where the fixture runs.
    """
    for name, arm in measurement["arms"].items():
        rate = arm["microseconds_per_notification"]
        reason = arm["microseconds_per_notification_absent_because"]
        if rate is None:
            assert reason in UNRATED.values(), (
                f"{name} published no rate and no recorded reason for the "
                "absence, which is the gap a later reader fills in"
            )
            continue
        assert reason is None, f"{name} published a rate and a reason for not"
        assert rate > 0, (
            f"{name} published {rate} microseconds per notification, a rate "
            "supervision cannot produce"
        )
        assert arm["overhead_seconds"] > 0, (
            f"{name} published a rate of {rate} over an overhead of "
            f"{arm['overhead_seconds']}s, so the two disagree in sign"
        )


def test_every_arm_says_where_it_stands_against_this_runs_control(
    measurement,
) -> None:
    """The mark travels into the artifact, on this host's actual readings.

    `tests/unit/test_seccomp_overhead_record.py` proves `control_clearance`
    distinguishes the four readings against injected values and plants a
    clearing arm and an overlapping arm side by side; it cannot prove the
    *fixture* routes the arms through it against the same run's control. That
    is the gap `test_no_arm_publishes_a_rate_its_own_overhead_contradicts`
    closes for the rate and it is closable only where the fixture runs.

    The field exists because line-locality in this module's prose protects a
    reader of this module and nobody else. An artifact consumer lifts
    `overhead_seconds` and gets a bare number, which is the identical defect
    one layer down.
    """
    control_excursion = tuple(measurement["control_excursion_seconds"])
    control_overhead = measurement["arms"][CONTROL_ARM]["overhead_seconds"]
    for name, arm in measurement["arms"].items():
        key = arm["overhead_against_this_runs_control"]
        assert key in CLEARANCE, (
            f"{name} recorded {key!r}, which names no reading in CLEARANCE"
        )
        expected, sentence = control_clearance(
            arm["overhead_seconds"],
            control_overhead,
            control_excursion,
            name == CONTROL_ARM,
        )
        assert key == expected, (
            f"{name} recorded {key!r} where its own overhead of "
            f"{arm['overhead_seconds']}s against a control of "
            f"{control_overhead}s gives {expected!r}, so the record's verdict "
            "is not a reading of the figures beside it"
        )
        assert arm["overhead_against_this_runs_control_because"] == sentence
        assert str(arm["overhead_seconds"]).lstrip("-")[:6] in sentence or (
            f"{arm['overhead_seconds']:+f}" in sentence
        ), (
            f"{name}'s sentence does not carry its own figure, so the overlap "
            "does not travel on the line of the figure it qualifies"
        )
    assert (
        measurement["arms"][CONTROL_ARM]["overhead_against_this_runs_control"]
        == "is-this-runs-control"
    ), "the control did not identify itself, so every other arm's comparator is unnamed"
