#!/usr/bin/env bash
# Removal proofs — each mechanism deleted in turn, its test observed failing.
#
# A passing fixture is not evidence a mechanism works. This script makes the
# counterfactual explicit: it edits a mechanism out of the source, runs the
# test that is supposed to depend on it, records whether the test failed, and
# restores the source. A mechanism whose test still passes with the mechanism
# removed is reported as UNPROVEN.
#
# The edits are made to a copy of the tree, never to the working tree, so an
# interrupted run cannot leave a mechanism disabled.
#
# Run:
#   docker run --rm --privileged --cgroupns=host \
#     -v /sys/fs/cgroup:/sys/fs/cgroup:rw -v "$PWD:/work" -w /work \
#     f2a-dev bash tests/removal_proofs.sh
#
# ---------------------------------------------------------------------------
# WHAT A PROOF HAS TO ESTABLISH, AND WHY THE POST-TAMPER RUN IS NOT ENOUGH
#
# A proof claims: *this test fails BECAUSE this mechanism is gone.* Reading only
# the state after the tamper cannot establish that, because everything below
# also produces a failing test and none of it is evidence of anything:
#
#   - the interpreter cannot import pytest, so every arm exits non-zero;
#   - the test named by the proof was renamed, so `pytest` exits 4 for an
#     unrecognised selector — which reads as a failing test;
#   - the test was already failing before anything was tampered;
#   - the tamper produced source that does not parse or does not build.
#
# The first of those was run for real: on a host without pytest the harness
# reported **48 proved, 0 unproven**, and the only reason anyone noticed is that
# the number was implausibly good. A verification instrument that scores full
# marks precisely when it is measuring nothing is worse than no instrument.
#
# So a proof is scored against BOTH states. The suite is run once, untampered,
# before any proof; each proof looks its own test up in that baseline and is
# attempted only if the test RAN and PASSED there. The baseline costs one
# pytest invocation and one `go test` invocation for the whole file — a few
# percent on a run that makes fifty-one of each — because it is taken over the
# whole suite at once rather than per proof.
#
# `tools/check_tampers.py` is the same reasoning applied statically, and costs
# under a second with no pytest, no Go and no privileges. Run that first.
#
# ---------------------------------------------------------------------------
# THE MACHINE-READABLE RECORD, AND WHY THE STDOUT BELOW IS NOT ENOUGH
#
# Every line this script prints is recoverable only for as long as somebody is
# looking at the terminal it printed to. In CI it is not even that: the first
# run of this job on GitHub Actions (30919927355) was green, and `gh run view
# --job ... --log` returned zero bytes, because the job's name carried a `?`
# that GitHub strips from the log archive's paths and `gh` matches those paths
# by job name. The output existed; nothing that anyone reached for could find
# it. The job's exit status was the entire retrievable signal, and an exit
# status cannot distinguish 61 proved from 57 proved with 4 arms skipped.
#
# So the run also writes a JSON record: one entry per proof with its title,
# target file, target test and outcome, the totals, and the environment the
# totals are a property of. `tests/batteries/results/seccomp-overhead.json` is
# the convention it follows, and the reason is the same one the workflow gives
# for that file — a CI figure and a laptop figure are different measurements.
# Here the kernel release is the load-bearing part of that identity: four arms
# are attempted on Linux and skipped on Darwin, so `61 proved` and `57 proved,
# 4 skipped` are one instrument reporting over two different populations.
#
# **The record is not a gate and must never become one.** The exit status is
# still computed from $FAIL by the last line of this file and by nothing else.
# Two ways the record could have become a new way to pass are closed here
# deliberately, and both are the shape this harness already exists to prevent:
#
#   - it is written only AFTER every proof has run, never before, so it cannot
#     describe arms that were not attempted;
#   - on the baseline abort path it is written with `"status": "aborted"` and
#     with NO `totals` key and NO `proofs` key at all. A consumer asking
#     `totals.unproven == 0` raises rather than passing. A summary that reads
#     as success in an environment the harness refused to measure in would be
#     the 48-proved-having-tested-nothing failure with a JSON extension.

set -uo pipefail

SRC=$(pwd)
# This file's own path, resolved before the `cd` below. It is read once, to count
# the Go arms it declares — see the toolchain check under the baseline for why
# that count and not a fixed expectation about the environment.
SELF="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"
# $WORK holds the tree under test and NOTHING else. $SCRATCH holds this harness's
# own working files beside it: the two baseline transcripts, the per-arm records
# and the tamper's stderr. They were one directory until 2026-08-11, and that
# cost a baseline failure in every sweep this instrument ever took.
#
# Two tests resolve a repository root from `__file__`'s ancestors, which under
# this harness resolves to $WORK rather than to the repository. One of them —
# `tests/unit/test_removal_proof_scoring.py::test_the_two_path_lists_between_them_account_for_this_tree`
# — then asserts that REQUIRED_PATHS and NOT_NEEDED_PATHS account for every
# top-level entry it finds, and the four files below were four entries declared
# in neither. The test was right and this harness was wrong: it wrote undeclared
# files into the tree it was about to assert over. Only `.summary-records` and
# `.baseline-pytest.txt` exist by the time the Python baseline runs, which is why
# the cost was 1 outcome and not 4 — finding 039 §9.3 measures it, and §10
# records this repair.
#
# Declaring the four names in NOT_NEEDED_PATHS was the one-line alternative and
# is declined, because that list is consulted for the REPOSITORY root as well —
# the population `unlisted_top_level` exists to police — so it would teach the
# guard to ignore those four names where they would be genuine omissions.
#
# One `mktemp -d` and one trap, so every exit path is covered including the two
# `exit 2` aborts below, and $WORK is a subdirectory rather than a sibling so
# that a single `rm -rf` still removes both. The trap is armed before $WORK is
# created, so a failed `mkdir` cannot leak the directory it was made under.
SCRATCH=$(mktemp -d)
trap 'rm -rf "$SCRATCH"' EXIT
WORK="$SCRATCH/tree"
mkdir -p "$WORK" || exit 1
# ---------------------------------------------------------------------------
# THE COPY LIST, AND THE TWO DIRECTIONS IT USED TO FAIL SILENTLY IN
#
# What each path is here for:
#
#   src, tests, tools, pyproject.toml
#       the tree under test and the suite that reads it.
#   deploy, requirements.lock
#       added under T096. The sandbox image's FR-021 properties are checked
#       statically by tests/invariants/test_sandbox_image.py, which reads
#       deploy/images/sandbox.Dockerfile.
#   .github
#       added under finding 036. tests/unit/test_instrument_census.py reconciles
#       the census against .github/workflows/ci.yml, reached by segment join in
#       `tools/instruments.py` rather than by a slash-joined literal.
#   .gitignore
#       added under finding 039 §10, having been on the not-needed list until
#       then. tests/unit/test_seccomp_overhead_record.py reads it to establish
#       that `tests/batteries/results/*.latest.json` is still an ignored line —
#       the property that keeps its sibling assertion from being vacuous. Reached
#       as `REPO / ".gitignore"`, which is a third form the 2026-08-10 grep
#       behind the not-needed list did not cover.
#   specs
#       added under T095. A CONTRACT test's mechanism lives on the other side of
#       a document in `specs/*/contracts/`. The WHOLE tree, not `002` alone,
#       because tools/corpuscheck walks `specs/*/findings` and a partial copy
#       trades one missing-file baseline failure for another.
#   docs
#       added under T189/T190. tests/contract/test_claims_audit.py and
#       test_support_audit.py read docs/claims-audit.md and docs/support-audit.md
#       as the record, and walk the docs/ tree as a live surface. T172 already
#       walked docs/ but did not require a file inside it.
#
# The Go arms need the fixtures at the relative path the tests use
# (src/proxy/../../tests/fixtures), which `tests` already satisfies.
#
# **Three of those five entries were added retroactively, each after a pass
# discovered its tests could not read a directory, and each presenting as N arms
# scored `test-already-failing` with nothing saying the cause was the copy list.**
# The comments this block replaces called it "third instance of the same failure
# and the same fix". Two things made that repeatable, and both are closed here.
#
# **(a) `2>/dev/null` made a failed copy indistinguishable from a path that was
# never listed.** A renamed or absent source directory produced exactly the same
# silence as an omission, and every dependent test then failed in the baseline
# for a missing file. So the paths are asserted to exist BEFORE anything is
# copied, and the copies no longer discard their own errors: a copy that fails
# for any reason — permissions, a full disk, a path that moved — now aborts with
# the reason on stdout instead of producing a work tree that is quietly short.
#
# **(b) An omission was silent by construction, and the fourth instance was
# scheduled.** `unlisted_top_level` below closes that without changing what is
# copied: it names every top-level entry of the source that is in neither list.
# A new top-level directory therefore announces itself the first time the harness
# runs after it appears, rather than N no-verdicts later.
#
# Why a warning at setup and a refusal only when the symptom shows: a new
# top-level directory is usually irrelevant to this harness (`docs/`, `research/`
# and `examples/` all are), so refusing to sweep would make an unrelated addition
# block the instrument. The note is reprinted at the foot of the run when any arm
# actually reported UNUSABLE, which is the one moment it is load-bearing.
#
# Why not invert to whole-tree-minus-a-deny-list, which is the only option that
# forecloses (b) rather than diagnosing it — MEASURED on this tree, 2026-08-10,
# macOS arm64 unprivileged:
#
#     the allowlist below                              0.71s   35,564 KB
#     whole tree minus {.git,.venv,examples,caches}     0.93s   30,020 KB
#     the same deny list with `examples` forgotten     14.41s  692,788 KB
#
# So the cost is 0.22s, and the deny list is SMALLER because `cp -r` here also
# copies `__pycache__`. That is not the reason it was declined. `examples/` is
# **1.38 GB and git-ignored** — 30x `.git` and `.venv` combined — so a deny list
# is exactly as hand-maintained as this allowlist, and the work tree stops being
# a stated set and becomes whatever untracked files a particular checkout has.
# Two runs on two checkouts of the same commit would then sweep two different
# populations, which is the one property this instrument's record exists to pin
# (`what_this_is_a_property_of`). An omission from a deny list fails toward
# performance rather than correctness, which is the better direction and is why
# the option is worth re-opening — but it needs the copied set derived from what
# git tracks plus what is untracked-and-not-ignored, not from a hand deny list,
# and that is a larger change than this one. Left for an owner with the
# measurement above attached so it need not be re-derived.

#: Every top-level path the work tree must contain. Asserted, not assumed.
REQUIRED_PATHS="src tests tools pyproject.toml deploy requirements.lock .github specs .gitignore README.md docs"

#: Every top-level path deliberately NOT copied, so that `unlisted_top_level`
#: can tell "declared unnecessary" from "nobody has looked at it yet". Keeping
#: this list is the price of (b) being diagnosed rather than silent; the failure
#: mode of letting it rot is a note naming a harmless directory, which is the
#: right direction for a list nobody is obliged to maintain.
#:
#: .git/.venv and the caches are environment. `examples/` is 1.38 GB of vendored
#: read-only reference repos. `research/`, `LICENSE`, `.cursor/` and
#: `.specify/` are read by nothing under `tests/` except as dated records.
#: **`README.md` left this list under T172** — `tests/contract/test_platform_statement.py`
#: reads it as a supported-platform surface, the same third form (``REPO / name``)
#: that moved `.gitignore` onto the copy list. Verified 2026-08-10 by grep for
#: path literals and for segment joins off a repo-root variable — the two forms
#: `.github` and `deploy` are reached by — and that verification is what T172
#: falsified for README.md.
#: **`docs/` left this list under T189/T190** — `tests/contract/test_claims_audit.py`
#: and `tests/contract/test_support_audit.py` read the audit files as the record
#: and walk the `docs/` tree as a live surface (``REPO / AUDIT``). T172 already
#: walked `docs/` as a live tree but left it here because no test then required
#: a file inside it.
#:
#: **That verification was wrong about one entry, and the entry is instructive.**
#: `.gitignore` sat on this list until 2026-08-11, and
#: `tests/unit/test_seccomp_overhead_record.py` reads it as `REPO / ".gitignore"`
#: — a third form neither of the two greps covered. So the work tree never had
#: it, and that test failed in the baseline of every sweep this harness has ever
#: taken, invisibly, because no proof arm names it. It is in REQUIRED_PATHS now.
#: The general lesson is the one this whole block is about: a path is on this
#: list because somebody looked once, and "looked once" is not a guard.
# `.mypy_cache` joins the list with T123. That task's static half is exercised by
# running a type checker over a planted forbidden construction; the test points
# mypy at a temporary cache directory, but a developer reproducing it by hand
# produces this one in the tree. Recorded as looked-at-and-not-needed so its
# appearance is not an unrelated failure in the path-accounting guard. It cannot
# mask a copy-list defect: nothing the suite reads lives in a type-checker cache.
NOT_NEEDED_PATHS=".git .venv examples research LICENSE .cursor .specify .pytest_cache .ruff_cache .mypy_cache"

# unlisted_top_level <dir> -> the entries of <dir> in neither list, one per line.
#
# A function with an enumerated answer rather than an inline loop, for the reason
# `go_toolchain_verdict` is one: it is driven directly by
# `tests/unit/test_removal_proof_scoring.py`, and an inline version could only
# have been checked by reading it.
#
# **git decides what is environment, because a hand-written artifact list is the
# defect this function exists to fix, one directory over.** The first version of
# this classified against `NOT_NEEDED_PATHS` alone and named
# `pytest-collected.txt` on CI, where the workflow writes its JUnit reports into
# the repository root — so the check meant to catch an omitted *directory* failed
# over a *report file*, and it failed only on CI, because a local run writes the
# same reports somewhere else. Adding those five names to `NOT_NEEDED_PATHS`
# would have re-created the fourth-instance problem in the list that was supposed
# to end it: the next tool to drop a file in the root breaks it again.
#
# `.gitignore` already states which paths are environment, is maintained for its
# own reasons, and is the same answer on every host. `check-ignore` consults the
# index, so a *tracked* path matching an ignore pattern is still content and is
# still named.
#
# The suppressed stderr is not the `2>/dev/null` this pass removed from the copy
# list. There, a non-zero exit was discarded; here it is the answer — no repo, no
# git, or any other failure leaves the entry **named**, which is the loud
# direction. A missing git makes this noisy, never quiet.
unlisted_top_level () {
  local entry base
  for entry in "$1"/* "$1"/.[!.]*; do
    [ -e "$entry" ] || continue
    base=$(basename "$entry")
    case " $REQUIRED_PATHS $NOT_NEEDED_PATHS " in
      *" $base "*) continue ;;
    esac
    git -C "$1" check-ignore -q -- "$base" 2>/dev/null && continue
    echo "$base"
  done
}

_absent=""
for _p in $REQUIRED_PATHS; do
  [ -e "$SRC/$_p" ] || _absent="$_absent $_p"
done
if [ -n "$_absent" ]; then
  echo "  CANNOT RUN — the copy list names path(s) this tree does not have:$_absent"
  echo
  echo "  Every test that reads one of those would fail in the baseline for a missing"
  echo "  file, and its arms would be refused as UNUSABLE — which says nothing about"
  echo "  any mechanism. Refusing here instead, because a work tree that is quietly"
  echo "  short is how this harness reported N no-verdicts three times already."
  echo "  If a path was renamed, rename it in REQUIRED_PATHS in the same commit."
  exit 2
fi
for _p in $REQUIRED_PATHS; do
  cp -r "$SRC/$_p" "$WORK/" || {
    echo "  CANNOT RUN — copying $_p into the work tree failed (status $?)."
    echo "  The error is above. This used to be discarded by \`2>/dev/null\`, which"
    echo "  made a failed copy read exactly like a path nobody had listed."
    exit 2
  }
done

# Computed here, where the source tree is still the working directory, and
# printed under the banner below rather than above it.
_unlisted=$(unlisted_top_level "$SRC" | tr '\n' ' ')
cd "$WORK" || exit 1

TAMPER="$SRC/tools/tamper.py"
BASELINE_PY="$SCRATCH/.baseline-pytest.txt"
BASELINE_GO="$SCRATCH/.baseline-go.txt"

# A wall-clock cap on one arm, and the script that applies it. See
# `tools/proof_timeout.py` for why this is a script rather than `timeout(1)`
# (macOS ships none) and why a timed-out arm gets its own outcome below.
#
# 300s is chosen against a measurement, not a feeling: the whole untampered
# suite is ~1300 outcomes in a couple of minutes. Both readings 2026-08-08, and
# both platforms are named because the SKIP half of any such figure is a property
# of the platform and not of the suite: privileged on Linux 6.12.76-linuxkit in
# the dev image, and unprivileged on macOS 26.2. A proof runs
# **one** test. The slowest arms are the kernel-mechanism ones and they are
# seconds. So this is two orders of magnitude above any arm that is working, and
# an arm that reaches it is not slow — it is not coming back. Raise it with
# REMOVAL_PROOF_TIMEOUT if a genuinely long arm ever appears; do not lower it to
# make a hang report faster, because then it stops distinguishing the two.
CAP="$SRC/tools/proof_timeout.py"
PROOF_TIMEOUT="${REMOVAL_PROOF_TIMEOUT:-300}"
TIMED_OUT_STATUS=124

# One line per proof, tab separated, in the order they ran. Lives under $SCRATCH
# so an interrupted run cannot leave a partial file behind that looks like a
# result, and beside $WORK rather than inside it for the reason given at the
# `mktemp -d` above. Its only consumer is `tools/removal_proofs_summary.py`,
# which is handed the path through `F2A_RECORDS` below, so where it lives is not
# a fact any other instrument depends on.
RECORDS="$SCRATCH/.summary-records"
: >"$RECORDS"

# Gitignored by `tests/batteries/results/*.latest.json`, and named to say so:
# this is the record of the run that just happened, never a committed figure.
SUMMARY="${REMOVAL_PROOFS_SUMMARY:-$SRC/tests/batteries/results/removal-proofs.latest.json}"

PASS=0
FAIL=0
SKIP=0
# Counted apart from FAIL on purpose. An arm that did not return is not an arm
# that was demonstrated to still pass; it is an arm nobody measured, and folding
# it into either existing bucket loses the one fact worth keeping. It carries
# the same weight as FAIL in the exit status at the foot of this file.
TIMEOUT=0
# Counted apart from SKIP for the reason `TIMEOUT` is counted apart from FAIL. A
# baseline line the harness cannot read a verdict off is not an arm the
# environment declined to run; it is an arm the harness lost track of, and the
# bucket it used to land in — `skipped` — is the one bucket where losing it is
# invisible. See `baseline_py` and `report_unrunnable`.
UNREADABLE=0
# Counted apart from FAIL for the reason UNREADABLE is counted apart from SKIP,
# one condition over. `unproven` is the one word this harness produces that means
# **your mechanism is dead**, and an arm whose named test was already failing
# before the tamper establishes nothing of the kind: the harness read the
# baseline, found no verdict worth scoring against, and refused to attempt it.
# The two want opposite responses — a vacuous proof is a source defect, a dirty
# baseline is an environment defect — and folding them together has already cost
# real work in both directions. One sweep over a transiently dirty baseline (234
# of 1653 outcomes failing) reported "236 proved, 58 unproven" with ZERO vacuous
# arms, which read at face value says 58 mechanisms have died.
#
# It carries FAIL's weight in the exit status, unchanged, at the foot of this
# file. Only the label was wrong: a dirty baseline means this sweep is not a
# result, so red is the correct verdict and making it green would be finding
# 032's fabrication pointing the other way.
UNUSABLE=0
HAVE_GO=0

# The proof currently running. `_record` reads them so the call sites stay one
# line each; every terminal branch in `proof` and `go_proof` calls it exactly
# once, which is what makes proved+unproven+skipped == entries checkable below.
_P_NAME=""
_P_FILE=""
_P_TEST=""
_P_DRIFTED=no

_record () {
  printf '%s\t%s\t%s\t%s\t%s\t%s\n' \
    "$1" "$2" "$_P_NAME" "$_P_FILE" "$_P_TEST" "$_P_DRIFTED" >>"$RECORDS"
}

# _write_summary <complete|aborted> [reason]
#
# Called from exactly two places: the baseline abort, and after the last proof.
# It never touches $PASS/$FAIL/$SKIP and never influences the exit status — a
# failure to write the record leaves the verdict exactly as it was.
_write_summary () {
  mkdir -p "$(dirname "$SUMMARY")" 2>/dev/null
  F2A_STATUS="$1" \
  F2A_ABORT_REASON="${2:-}" \
  F2A_RECORDS="$RECORDS" \
  F2A_PASS="$PASS" F2A_FAIL="$FAIL" F2A_SKIP="$SKIP" F2A_TIMEOUT="$TIMEOUT" \
  F2A_UNREADABLE="$UNREADABLE" F2A_UNUSABLE="$UNUSABLE" \
  F2A_PY_TOTAL="${_py_total:-}" F2A_PY_FAILED="${_py_failed:-}" \
  F2A_GO_TOTAL="${_go_total:-}" F2A_GO_FAILED="${_go_failed:-}" \
  F2A_HAVE_GO="$HAVE_GO" \
  F2A_EUID="$(id -u)" \
  python3 "$SRC/tools/removal_proofs_summary.py" "$SUMMARY" || {
    echo "  WARNING: the run completed but its JSON record could not be written."
    return 0
  }
  chmod 0644 "$SUMMARY" 2>/dev/null
  echo "record     $SUMMARY"
}

echo "Removal proofs"
echo

if [ -n "$_unlisted" ]; then
  echo "  note       top-level path(s) in neither the copy list nor the not-needed list:"
  echo "             $_unlisted"
  echo "             Nothing is wrong yet. If a test reads one of them, its arms will"
  echo "             be refused as UNUSABLE — add it to REQUIRED_PATHS if the suite"
  echo "             needs it, or to NOT_NEEDED_PATHS to record that it does not."
  echo
fi

# ---------------------------------------------------------------------------
# The baseline. Nothing below is attempted until this says the suite runs.

# `-rs` is load-bearing and not a nicety. Without it the baseline records THAT a
# test was skipped and not WHY, and the harness used to fill the gap with a guess
# — every skipped arm was printed "(privilege or platform)" whether or not
# anybody had established that. Measured on 2026-08-08: run through a login shell
# that drops the Go toolchain off PATH, two T114 arms were skipped because the
# enforcement point could not be built, and the harness reported both of them as
# privilege or platform. pytest had the real reason and the harness discarded it.
#
# The `-rs` block is keyed by the file and line the skip was raised at, not by
# node id, so `baseline_skip_reason` attributes by file. That is weaker than
# per-test and it is a reading rather than an invention, which is the whole
# difference. Its lines begin at column zero with `SKIPPED [n] `, so they are
# matched by nothing that reads this file: `_py_total` requires a space before
# the verdict, and `baseline_py`'s two patterns are anchored on a node id.
python3 -m pytest tests -v -rs --tb=no -p no:cacheprovider >"$BASELINE_PY" 2>&1
if ! grep -qE ' (PASSED|FAILED|SKIPPED|ERROR|XFAIL|XPASS)' "$BASELINE_PY"; then
  echo "  CANNOT RUN — pytest produced no test outcomes at all in this environment."
  echo
  sed 's/^/    /' "$BASELINE_PY" | tail -20
  echo
  echo "  Every proof below would have exited non-zero for this reason and been"
  echo "  scored as proved. Refusing to report a number. Install the pinned"
  echo "  dependencies (pip install --require-hashes -r requirements.lock) or run"
  echo "  inside the dev image."
  # Written with no totals and no proofs. See the header: a record that reads as
  # a clean result here would reinstate the exact defect the abort exists for.
  _write_summary aborted \
    "pytest produced no test outcomes at all in this environment, so every arm would have exited non-zero for that reason and been scored as proved"
  exit 2
fi
_py_total=$(grep -cE ' (PASSED|FAILED|SKIPPED|ERROR|XFAIL|XPASS)' "$BASELINE_PY")
_py_failed=$(grep -cE ' (FAILED|ERROR)' "$BASELINE_PY")

# ---------------------------------------------------------------------------
# The Go toolchain, and why its absence aborts rather than skipping.
#
# `0caf257` — "Stop the removal-proof harness from scoring an environment as a
# result" — settled this for the Python side: an environment that cannot run the
# suite gets a refusal to report a number, not a clean sweep. The Go side did not
# get the same ruling and degraded quietly instead, and the asymmetry was
# measured rather than reasoned.
#
# On 2026-08-08, on one tree at `821ef70`, in one image, differing only in the
# shell the harness was invoked through:
#
#     bash -c  'bash tests/removal_proofs.sh'   ->  222 proved, 0 unproven      exit 0
#     bash -lc 'bash tests/removal_proofs.sh'   ->  210 proved, 0 unproven,
#                                                   12 skipped                  exit 0
#
# `go` lives at `/usr/local/go/bin/go` in the dev image and `bash -l` sources
# `/etc/profile`, which rebuilds PATH without it. So HOW THE HARNESS IS INVOKED
# decided whether twelve proofs ran, and both runs were green. CI already carries
# a hand-written workaround for the same hazard from a different direction —
# `sudo -E env "PATH=$PATH"` in `.github/workflows/ci.yml`, because plain `sudo`
# resets PATH too — which is the second known route into this state and the
# reason a guard belongs here rather than in each invocation.
#
# The condition is "this file declares Go arms and there is no toolchain", not
# "Go is missing". A tree with no Go arms needs no Go, and pinning the
# requirement to the declarations means deleting the arms removes the
# requirement instead of leaving a check that fails for nothing.
#
# Stated as a function with three enumerated answers rather than inline, so the
# decision can be driven directly — `tests/unit/test_removal_proof_scoring.py`
# calls it with `go` on and off PATH and with the arm count at zero. An inline
# `if` could only have been checked by reading it, and this repository's whole
# position is that reading an instrument is not measuring it.
#
# go_toolchain_verdict <declared_go_arms> -> OK | ABORT | NO-GO-ARMS
go_toolchain_verdict () {
  if command -v go >/dev/null 2>&1; then echo OK; return; fi
  if [ "$1" -gt 0 ]; then echo ABORT; return; fi
  echo NO-GO-ARMS
}

_go_arms=$(grep -cE '^go_proof "' "$SELF")
HAVE_GO=0
if [ "$(go_toolchain_verdict "$_go_arms")" = ABORT ]; then
  echo "  CANNOT RUN — no Go toolchain on PATH, and ${_go_arms} proofs need one."
  echo
  echo "    PATH=$PATH"
  echo
  echo "  Those ${_go_arms} arms cover the cross-language capability boundary, which is"
  echo "  the one place in this repository where two implementations agree only"
  echo "  because two people wrote the same thing twice. Running the other arms and"
  echo "  reporting them as a clean sweep is how a degraded run stays green: the"
  echo "  count moves and the exit status does not."
  echo
  echo "  A missing toolchain is an environment, not a result. Install Go, or invoke"
  echo "  the harness through a shell that keeps it on PATH — note that a LOGIN shell"
  echo "  (bash -l) and sudo without -E both rebuild PATH and are how this is usually"
  echo "  reached. In the dev image go is at /usr/local/go/bin/go."
  _write_summary aborted \
    "no Go toolchain on PATH while ${_go_arms} proofs declare Go tests, so those arms would have been recorded skipped and the run would have reported a clean sweep over a population ${_go_arms} arms smaller than the one it declares"
  exit 2
fi
if command -v go >/dev/null 2>&1; then
  HAVE_GO=1
  # `-count=1`, for the same reason the pytest baseline above carries
  # `-p no:cacheprovider`: a baseline is a reading of THIS environment, and Go
  # will happily supply one from another. Confirmed on 2026-08-04 rather than
  # assumed — `go test -v` caches, and a cached result **replays all 223
  # `--- PASS:` lines**, so `_go_total` below would count outcomes from a run
  # that did not happen. In practice the `mktemp` copy usually defeats the
  # cache, because the absolute paths the tests open are part of the key; that
  # is an accident of $WORK and not a guard, and a baseline whose validity
  # rests on an accident is the thing this harness exists to refuse.
  (cd "$WORK/src/proxy" && go test -v -count=1 ./...) >"$BASELINE_GO" 2>&1
  _go_total=$(grep -cE '^ *--- (PASS|FAIL|SKIP): ' "$BASELINE_GO")
  _go_failed=$(grep -cE '^ *--- FAIL: ' "$BASELINE_GO")
  echo "  baseline   ${_py_total} python outcomes (${_py_failed} not passing), ${_go_total} go outcomes (${_go_failed} not passing)"
else
  # Reachable only when this file declares no Go arms at all; the check above
  # aborts otherwise. Named that way rather than "no Go toolchain", because the
  # two are different facts and only one of them is a reason to carry on.
  : >"$BASELINE_GO"
  echo "  baseline   ${_py_total} python outcomes (${_py_failed} not passing), no Go arms declared"
fi
echo

# _escape turns a pytest node id into something grep -E will match literally.
_escape () { printf '%s' "$1" | sed 's/[][\.*^$(){}?+|\/]/\\&/g'; }

# baseline_py: PASSED | SKIPPED | FAILED | ABSENT | UNREADABLE, for a node id or
# a file.
#
# ABSENT is the one that had no detection at all before. A renamed test makes
# `pytest` exit 4, the harness read any non-zero exit as the mechanism being
# load-bearing, and the proof reported `proved` while running nothing.
#
# ---------------------------------------------------------------------------
# UNREADABLE, AND WHY IT IS A SEPARATE OUTCOME RATHER THAN A BETTER SKIP
#
# This function used to end `echo SKIPPED` with no test in front of it — a
# classifier stated as a complement, which is the defect
# `specs/002-spec-aware-agent-runtime/findings/032-removal-proof-signal-fabrication.md`
# established for `proof()`'s exit statuses and which was still standing here,
# twenty lines above it, in the same file. The accepting set for `SKIPPED` was
# "not absent, not failed, not passed", so every way a baseline line can fail to
# carry a verdict landed in it.
#
# There is at least one such way and it is reachable with capture ON. `pytest -v`
# writes the node id, runs the test, then writes the verdict on the SAME line —
# so anything that reaches the real file descriptor 1 while the test runs pushes
# the verdict onto a line of its own. Planted and measured on 2026-08-08:
#
#   def test_positive(capfd):
#       with capfd.disabled():
#           print("output that reaches the terminal mid-line")
#
#   test_r1_plant.py::test_r1_positive_prints_past_capture output that reaches …
#   PASSED            [ 66%]
#
# `baseline_py` returned SKIPPED for that passing test. `capfd.disabled()` is one
# route; `-s` and `PYTEST_ADDOPTS=-s` are others, and none of them is visible to
# a reader of the harness output.
#
# **Why this is worse than the hang in finding 032, and the reason for the fourth
# outcome.** A fabricated `proved` stood out as anomalous. A fabricated `skipped`
# does not: `skipped` is a LEGITIMATE outcome that occurs 2-13 times in every
# unprivileged or non-Linux run, so a lost proof hides inside a population of
# correctly-skipped ones and nothing in the output tells them apart. The two
# states DO differ in the baseline text — a legitimately skipped test has a line
# carrying ` SKIPPED`, a lost one has a line carrying no verdict at all — and the
# fall-through was the only thing throwing that difference away.
#
# So `SKIPPED` now requires pytest to have said so, and the residue gets its own
# name, its own counter and FAIL's weight in the exit status.
baseline_py () {
  local sel esc out
  sel="$1"
  esc=$(_escape "$sel")
  case "$sel" in
    *::*) out=$(grep -E "^${esc}( |\[)" "$BASELINE_PY") ;;
    *)    out=$(grep -E "^${esc}::" "$BASELINE_PY") ;;
  esac
  if [ -z "$out" ]; then echo ABSENT; return; fi
  if echo "$out" | grep -qE ' (FAILED|ERROR)'; then echo FAILED; return; fi
  if echo "$out" | grep -qE ' PASSED'; then echo PASSED; return; fi
  # Enumerated, never a fall-through. XFAIL and XPASS are named here because
  # neither is a usable baseline — a proof needs a test that PASSED untampered —
  # and because leaving them out would make them UNREADABLE, which would be a
  # true statement about the harness and a misleading one about the test.
  #
  # A file-level selector legitimately matches lines with no verdict on them:
  # `-rs` aside, the warnings summary repeats node ids on bare lines. That is why
  # the question is "did ANY matched line carry a verdict", asked in precedence
  # order above, and not "did every matched line carry one".
  if echo "$out" | grep -qE ' (SKIPPED|XFAIL|XPASS)'; then echo SKIPPED; return; fi
  echo UNREADABLE
}

# baseline_skip_reason: the reason PYTEST recorded, or empty.
#
# The `-rs` block is keyed by the file and line the skip was raised at, so this
# attributes by the target's BASENAME — unique across the 69 test files as of
# 2026-08-08, and the reason an empty result is reported as "none recorded"
# rather than filled in. The harness's previous text asserted a cause; this one
# quotes one or says it has none.
baseline_skip_reason () {
  local base
  base=$(basename "${1%%::*}")
  grep -E "^SKIPPED \[[0-9]+\] .*$(_escape "$base"):[0-9]+: " "$BASELINE_PY" \
    | sed -E 's/^SKIPPED \[[0-9]+\] [^ ]*: //' | sort -u | head -2 | tr '\n' ' '
}

# baseline_go: the same question for a `-run` alternation. Every named test must
# have passed. `go test -run` exits 0 when its pattern matches nothing, so a
# renamed Go test reported UNPROVEN — a claim about the tests rather than about
# the proof, and equally false.
baseline_go () {
  local pattern name out verdict=PASSED
  pattern="$1"
  IFS='|' read -r -a _names <<<"$pattern"
  for name in "${_names[@]}"; do
    out=$(grep -E "^ *--- (PASS|FAIL|SKIP): $(_escape "$name") " "$BASELINE_GO")
    if [ -z "$out" ]; then echo ABSENT; return; fi
    if echo "$out" | grep -q -- '--- FAIL: '; then verdict=FAILED; fi
    if [ "$verdict" = PASSED ] && echo "$out" | grep -q -- '--- SKIP: '; then verdict=SKIPPED; fi
  done
  echo "$verdict"
}

# report_unrunnable prints the one line that says why a proof was not attempted,
# and returns 0 if the caller should stop.
report_unrunnable () {
  local verdict="$1" name="$2" test="$3"
  case "$verdict" in
    ABSENT)
      echo "  NO TEST   $name — $test matched nothing in the baseline; the test was renamed or removed"
      _record unproven test-absent
      FAIL=$((FAIL+1)); return 0 ;;
    FAILED)
      # Its own outcome, and note that this branch has printed `UNUSABLE` since
      # it was written — it was the AGGREGATE that called it `unproven`, so the
      # per-arm line and the total disagreed about the same arm. No new word is
      # being coined here; the total is being made to say what the arm says.
      echo "  UNUSABLE  $name — $test already fails before the tamper, so its failure after proves nothing"
      _record unusable test-already-failing
      UNUSABLE=$((UNUSABLE+1)); return 0 ;;
    SKIPPED)
      # The reason pytest gave, never a reason the harness inferred. The text
      # that used to stand here — "(privilege or platform)" — was a diagnosis
      # nothing had established, and on 2026-08-08 it was measured wrong: two
      # T114 arms lost to a missing Go toolchain were both reported as privilege
      # or platform while pytest's own reason said "install a Go toolchain".
      local why
      why=$(baseline_skip_reason "$test")
      echo "  SKIPPED   $name"
      echo "            pytest skipped $test in this run's baseline."
      if [ -n "$why" ]; then
        echo "            Its reason: $why"
      else
        echo "            It recorded no reason this harness could attribute, which is"
        echo "            itself worth reading: a skip with no reason is a skip nobody"
        echo "            can check. The mechanism was NOT exercised here."
      fi
      _record skipped test-skipped-in-baseline
      SKIP=$((SKIP+1)); return 0 ;;
    UNREADABLE)
      # Neither of the two things it superficially resembles, on exactly
      # `report_timeout`'s reasoning. Not `skipped`, because a skip means the
      # environment declined to run the test and the skip count is read as the
      # population this run did not cover — and here the test may well have
      # passed. Not `proved` or `unproven`, because no tamper was applied.
      echo "  NO VERDICT $name"
      echo "            $test appears in the baseline with NO outcome on its line."
      echo "            pytest -v writes the verdict on the same line as the node id, so"
      echo "            anything the test writes to the real stdout splits them. This arm"
      echo "            was NOT attempted, and it is not scored as skipped: a skip is an"
      echo "            arm the environment declined, and nobody declined this one."
      _record unreadable baseline-verdict-unreadable
      UNREADABLE=$((UNREADABLE+1)); return 0 ;;
  esac
  return 1
}

# apply_tamper edits $2 per the snippet in $3, or explains why it could not.
# Returns 0 on success. `tools/tamper.py` owns the matching rules; see its
# docstring for why a match may be whitespace-insensitive and must be unique.
apply_tamper () {
  local name="$1" file="$2" snippet="$3" mode status reason
  cp "$file" "$file.orig"
  mode=$(python3 "$TAMPER" "$file" "$snippet" 2>"$SCRATCH/.tamper-err")
  status=$?
  if [ "$status" -ne 0 ]; then
    case "$status" in
      3) echo "  NO-OP     $name — the tamper matched nothing; the source moved under this proof"
         reason=tamper-matched-nothing ;;
      4) echo "  AMBIGUOUS $name — the tamper matches more than one site; it does not name a mechanism"
         reason=tamper-ambiguous ;;
      5) echo "  NO-OP     $name — the tamper ran and changed nothing"
         reason=tamper-changed-nothing ;;
      7) echo "  BROKEN    $name — the tampered source does not parse; the test would fail for the wrong reason"
         reason=tampered-source-unparseable ;;
      *) echo "  BROKEN    $name — the tamper script failed to run"
         reason=tamper-script-failed ;;
    esac
    sed 's/^/            /' "$SCRATCH/.tamper-err" | head -2
    _record unproven "$reason"
    FAIL=$((FAIL+1))
    mv "$file.orig" "$file"
    drop_bytecode "$file"
    return 1
  fi
  if [ "$mode" = OK_NORMALIZED ]; then
    echo "  drifted   $name — the tamper matched only after whitespace normalization (a formatter moved this site)"
    _P_DRIFTED=yes
  fi
  # **Bytecode, and it is not housekeeping.** CPython decides a cached `.pyc` is
  # current from the source's `(mtime-in-WHOLE-SECONDS, size)` — so two proofs
  # that tamper the same file inside one second with edits of the same byte
  # length make the second one import the FIRST one's compiled module. The
  # second proof then reports on a mechanism it never removed, in whichever
  # direction that happens to fall: `UNPROVEN` when the stale bytecode still
  # holds the guard, and `proved` when it does not.
  #
  # Measured on 2026-08-06, not reasoned. Two `if <cond>:` → `if False:` edits
  # on `repository.py` are both exactly 32 bytes shorter, and the second scored
  # UNPROVEN in the harness while failing correctly when run by hand — the only
  # difference being that the harness ran them 0.4s apart. Forcing the two
  # mtimes equal reproduces it on demand; a `sleep 1` between them hides it.
  #
  # This is a defect of the harness and not of either proof, so it is fixed
  # here rather than by choosing tamper strings that happen not to collide.
  # Scoped to the tampered file's own package: the rest of the copied tree's
  # caches match their sources and recompiling them per proof is a real cost
  # over ~190 arms.
  drop_bytecode "$file"
  return 0
}

# See the note in `apply_tamper`. Called on the way in AND on the way out,
# because a restore is the same edit in reverse and can collide the same way.
drop_bytecode () {
  rm -rf "$(dirname "$1")/__pycache__"
}

# report_timeout is the one place a non-returning arm is scored, and it scores
# it as neither of the two things it superficially resembles.
#
# Not `proved`: `proof()` reads non-zero as the tampered test having failed, and
# a killed process is non-zero for a reason that says nothing about the
# mechanism. That is not hypothetical — it is how a hung arm has already been
# recorded green, because a hang does not stay a hang and whoever kills the
# child hands `proof()` a 130 it cannot tell from a real failure.
#
# Not `skipped` either: a skip means the arm was not attempted and the count of
# skips is read as the population this run did not cover. A timeout was
# attempted and consumed the cap, and burying it there is how an arm leaves a
# green run without anyone noticing it went.
report_timeout () {
  echo "  TIMED OUT $1 — did not return within ${PROOF_TIMEOUT}s"
  echo "            Not scored as proved: a hang is not a demonstrated failure."
  echo "            Not scored as skipped: it ran, and nobody knows the outcome."
  _record timed-out proof-did-not-return
  TIMEOUT=$((TIMEOUT+1))
}

# report_signalled closes the route the cap above only makes rarer.
#
# A shell reports a signalled child as `128 + signum`, and `proof()` reads every
# non-zero status as the tampered test having failed. So a killed process is
# scored **proved** — measured, not reasoned: a planted arm whose tamper sends
# itself SIGTERM prints `proved` and exits the harness 0. That is how a hung arm
# becomes a green record the moment somebody loses patience with it, and it is
# the likeliest explanation for `T065 wiring` reading `proved` in the archive
# from 21:59 on 2026-08-05 while the same arm could not terminate at all.
#
# A tampered test that dies by signal has not reported anything either way: no
# assertion was evaluated, and a segfault or an OOM kill says the tampered
# source did something violent rather than that the test noticed. Scored
# unproven, which is the bucket for "attempted and did not demonstrate".
report_signalled () {
  echo "  SIGNALLED $1 — the test process died on signal $(($2 - 128)), so nothing was asserted"
  echo "            A signalled process is non-zero for a reason that says nothing"
  echo "            about the mechanism. Not scored as proved."
  _record unproven proof-killed-by-signal
  FAIL=$((FAIL+1))
}

# THE TITLE IS A DOUBLE-QUOTED SHELL STRING, SO THE SHELL READS IT BEFORE THIS
# FUNCTION DOES. A backtick in a title is command substitution and `$name` is an
# expansion, and both are silent in the direction that matters: the arm scores
# correctly and the title recorded beside its verdict is the rewritten one.
#
# Observed 2026-08-12, not foreseen. A title reading "so `required` is a presence
# test again" made the harness print `required: command not found` — which reads
# as a broken environment rather than as a typo — and record the title with the
# word deleted. An expansion is worse, because nothing is printed at all and the
# recorded identity of the proof quietly becomes a property of the host.
#
# **This is a gate and not a convention, deliberately.** The note that came out
# of that episode sat as a comment at the one arm that had been bitten, where no
# author of a NEW arm would ever read it, and this repository has already
# recorded "a convention every future author remembers" as a safeguard class
# that failed here. `tools/check_tampers.py` refuses any title whose written form
# differs from the form bash produced — so substitution, expansion and whatever
# bash grows next are one rule that cannot fall behind the shell — and it runs in
# the `invariants` CI job in under a second.
#
# ---------------------------------------------------------------------------
# THE SELECTOR MUST NAME A TEST NODE, NEVER A BARE FILE.
#
# `proof()` reads any non-zero exit from the tampered run as "the test failed
# with the mechanism removed". A selector naming a whole file therefore scores
# `proved` on a failure ANYWHERE in that file, and cannot tell the guard it
# names from its neighbours. The arm goes on reading green after the guard it
# exists to exercise has been deleted, which is the one event it should be
# loudest about.
#
# **Measured across the whole population, 2026-08-12, not reasoned.** 14 of the
# then-413 arms named a bare `.py` file, spanning 11 files of 10-40 collected
# tests each. Each was screened by applying its tamper and counting the failures
# in the named file, then probed by deleting its intended guard outright and
# re-running — the method that settled the FR-025 arm below. **9 of the 14 still
# scored `proved` with their guard gone; 5 correctly went `UNPROVEN`, and those 5
# were exactly the 5 whose tamper failed a single test.** A control was run for
# every arm — guard deleted, no tamper — and all 14 exited 0, so no probe was
# reading the deletion rather than the tamper. All 14 now name a node.
#
# The 9 survivors were NOT the FR-025 failure. There the collateral was
# positional (`Result.__init__() got multiple values for argument 'payload'`) and
# said nothing about the property; here every surviving failure was a genuine
# assertion about the same removed mechanism. So those arms were still evidence
# that the mechanism is covered *somewhere* — what they had stopped being is
# evidence about a NAMED guard, which is the whole of what an archived verdict
# carries. Both are worth repairing and they are not the same finding.
#
# Two further reasons a node selector is not a tidy-up:
#
#   - a deleted guard becomes a `tools/check_tampers.py` ERROR rather than a
#     silent pass, because the selector stops resolving. Verified for all 14.
#   - `baseline_py` scores a file selector FAILED if ANY test in the file failed
#     untampered, so a file-level arm's usability is hostage to up to 39 tests it
#     makes no claim about.
#
# **Name the bare function, never a parametrized id.** `check_tampers.py` reads
# the defined names with a `def test_...(` scan, so `test_x[PARAM]` is reported
# as undefined — which is why two proofs were previously refused for naming ids.
# An id that has merely been renamed is worse: `pytest` exits 4 on a selector it
# cannot resolve, and 4 is non-zero, so the arm reports `proved` having run
# nothing. Naming the function runs every parameter, which is sufficient: the arm
# needs one of them to fail, not all.
proof () {
  local name="$1" file="$2" test="$3" python_edit="$4"
  local verdict
  _P_NAME="$name"; _P_FILE="$file"; _P_TEST="$test"; _P_DRIFTED=no
  verdict=$(baseline_py "$test")
  if report_unrunnable "$verdict" "$name" "$test"; then return; fi

  apply_tamper "$name" "$file" "$python_edit" || return

  local output status
  output=$(python3 "$CAP" "$PROOF_TIMEOUT" \
             python3 -m pytest "$test" -q -p no:cacheprovider 2>&1)
  status=$?
  if [ "$status" -eq "$TIMED_OUT_STATUS" ]; then
    report_timeout "$name"
  elif [ "$status" -gt 128 ]; then
    report_signalled "$name" "$status"
  elif [ "$status" -eq 0 ]; then
    echo "  UNPROVEN  $name — the test still passes with the mechanism removed"
    _record unproven still-passes-without-the-mechanism
    FAIL=$((FAIL+1))
  elif echo "$output" | grep -qE '^(ERROR|INTERNALERROR)' && ! echo "$output" | grep -qE '[0-9]+ failed'; then
    # The test did not run: an import or collection error, not an assertion.
    echo "  BROKEN    $name — the tamper broke collection rather than the mechanism"
    # The lines that produced that verdict, because the verdict alone is not
    # actionable and the output is discarded a line later. **This was added after
    # a BROKEN appeared once and then did not reproduce**: with nothing retained
    # there was no way to tell a genuinely unparseable tamper from a flake in the
    # environment, and those want opposite responses.
    echo "$output" | grep -E '^(ERROR|INTERNALERROR)' | head -3 | sed 's/^/            /'
    _record unproven tamper-broke-collection
    FAIL=$((FAIL+1))
  else
    echo "  proved    $name"
    _record proved ""
    PASS=$((PASS+1))
  fi
  mv "$file.orig" "$file"
  drop_bytecode "$file"
}

proof "FR-048 mount namespace — pivot_root removed" \
  src/supervisor/mounts.py \
  "tests/integration/test_mount_namespace.py::test_an_undeclared_location_is_absent_not_denied" \
  's = s.replace("    _linux.pivot_root(mount_plan.new_root, old)", "    return")'

# The three FR-048 mount-authority proofs below cover three distinct mechanisms in
# `mounts.py`, and the second and third exist because the first passed while two
# writable holes were open (finding 021). The first removes the remount *pass*, the
# second the root seal, the third the *recursion* — and only the third distinguishes
# "the outermost mount is read-only" from "every mount the bind copied is".
proof "FR-048 read-only bind — the MS_REMOUNT pass removed" \
  src/supervisor/mounts.py \
  "tests/integration/test_mount_namespace.py::test_a_read_only_declaration_is_actually_read_only" \
  's = s.replace("    _remount_tree(dest, _flags_for(loc))", "    pass")'

proof "FR-048 session root — the read-only seal removed" \
  src/supervisor/mounts.py \
  "tests/integration/test_mount_authority.py::test_the_root_listing_is_unchanged_by_a_write_attempt" \
  's = s.replace("    _seal_root()", "    pass")'

proof "FR-048 read-only bind — the remount made non-recursive" \
  src/supervisor/mounts.py \
  "tests/integration/test_mount_authority.py::test_a_submount_inside_a_read_only_location_refuses_a_write" \
  's = s.replace("    for point in mount_points_under(dest):", "    for point in [dest]:")'

# --- T115, the adversarial filesystem battery (SC-022) -----------------------
#
# This battery asserts a NEGATIVE — zero reads and zero writes succeed outside
# the declared set — which is Rule 8's shape exactly: the positive result is a
# failure to succeed, and every way the instrument can break produces it. The
# four arms below are therefore two different questions and not four instances
# of one.
#
# The first two remove a MECHANISM and require the battery to notice. They are
# the same two mount repairs finding 021 forced, probed here by a workload
# rather than by a hand-written write: OD-24's ground ① claims those repairs
# close both authority gaps under every privilege model, and until this battery
# existed that claim had no arm behind it.
#
# The second two remove the BATTERY'S OWN INSTRUMENT — the prober's arm loop
# and the detector — and require its controls to notice. A battery whose
# mechanism proofs pass while its prober attempts nothing reports zero
# violations for the wrong reason, and no mechanism proof can tell the two
# apart.
proof "T115 battery — the session root seal removed, so the adversary writes into the root" \
  src/supervisor/mounts.py \
  "tests/batteries/test_adversarial_filesystem.py::test_no_adversarial_write_succeeds_outside_the_declared_set" \
  's = s.replace("    _seal_root()", "    pass")'

proof "T115 battery — the read-only remount removed, so a declared ro location takes a write" \
  src/supervisor/mounts.py \
  "tests/batteries/test_adversarial_filesystem.py::test_no_adversarial_write_succeeds_outside_the_declared_set" \
  's = s.replace("        _remount_tree(dest, _flags_for(loc))", "        pass")'

proof "T115 instrument — the arm table is never attempted, so zero violations is free" \
  tests/batteries/test_adversarial_filesystem.py \
  "tests/batteries/test_adversarial_filesystem.py::test_every_arm_actually_ran" \
  's = s.replace("    for arm in ARMS:", "    for arm in ARMS[:0]:")'

proof "T115 instrument — the detector stops resolving, so a real violation is not caught" \
  tests/batteries/test_adversarial_filesystem.py \
  "tests/batteries/test_adversarial_filesystem.py::test_the_positive_control_is_caught_naming_the_path" \
  's = s.replace("    found = []", "    return []\n    found = []")'

# --- T114, the adversarial egress battery (SC-002, SC-003) -------------------
#
# Same shape as T115's block and for the same reason: the battery asserts a
# NEGATIVE, so every way it can break reads green.
#
# The enforcement point is a Go binary the harness does not rebuild, so a
# mechanism proof cannot tamper `src/proxy/*.go` — the running binary would not
# change and the proof would read UNPROVEN for a reason that says nothing about
# the mechanism. The first arm therefore tampers the POLICY the battery
# derives, which is the enforcement point's only input and the thing an
# operator actually gets wrong: move every path template and the published
# surface stops resolving, so the workload is refused. The second removes the
# network namespace, which is the mechanism behind SC-003's zero rather than a
# property of the host. The third removes the battery's own arm loop, because a
# battery whose policy proof passes while it attempts nothing reports zero for
# the wrong reason.
proof "T114 battery — every path template moved, so the published surface stops resolving" \
  tests/batteries/test_adversarial_egress.py \
  "tests/batteries/test_adversarial_egress.py::test_the_allowed_arms_reached_the_target" \
  's = s.replace("\x22path_template\x22: op[\x22path_template\x22],", "\x22path_template\x22: \x22/moved\x22 + op[\x22path_template\x22],")'

proof "T114 battery — the network namespace removed, so the self-composed dial lands" \
  tests/batteries/test_adversarial_egress.py \
  "tests/batteries/test_adversarial_egress.py::test_a_self_composed_connection_reaches_nothing" \
  's = s.replace("escape_target[1])], isolate=True)", "escape_target[1])], isolate=False)")'

proof "T114 instrument — the arm table is never attempted, so zero violations is free" \
  tests/batteries/test_adversarial_egress.py \
  "tests/batteries/test_adversarial_egress.py::test_every_arm_actually_ran" \
  's = s.replace("        for arm in ARMS", "        for arm in ARMS[:0]")'

# --- T093, the decision log ingested into the trace stream -------------------
#
# The ownership direction is the mechanism: the proxy owns `egress_decision`
# and the runtime reads it. Two of these prove that direction is held by the
# ENGINE and not by the ingest's manners, and three prove the ingest refuses
# rather than completes what it cannot represent — because the failure mode
# this module has is not crashing, it is quietly producing a plausible record.
proof "T093 — the decision database is opened read-write, so the direction is a manner" \
  src/runtime/proxy_ingest.py \
  "tests/contract/test_proxy_ingest.py::test_a_write_through_the_ingest_connection_is_refused" \
  's = s.replace("f\x22file:{self.path}?mode=ro\x22, uri=True", "str(self.path)")'

# The one place in the repository where a requirement label is not merely
# documentation: `src/proxy/rules.go` stamps it into the log AND into the
# client-visible error body, so a label recomputed here disagrees with the one
# the operator was shown. The tamper substitutes a registry-plausible value,
# which is what a re-tagging module would produce.
proof "T093 — the requirement is recomputed on the reading side, so the log and the operator disagree" \
  src/runtime/proxy_ingest.py \
  "tests/contract/test_proxy_ingest.py::test_a_wrong_requirement_on_a_registered_rule_travels_verbatim" \
  's = s.replace("\x22requirement\x22: row.requirement,", "\x22requirement\x22: \x22FR-015\x22,")'

proof "T093 — the disposition map gains a default, so a third disposition records as a denial" \
  src/runtime/proxy_ingest.py \
  "tests/contract/test_proxy_ingest.py::test_an_unclassified_disposition_stops_the_ingest" \
  's = s.replace("return DISPOSITION_OUTCOME[disposition]", "return DISPOSITION_OUTCOME.get(disposition, OUTCOME_DENIED)")'

proof "T093 — the watermark is not read, so every pass re-ingests the whole log" \
  src/runtime/proxy_ingest.py \
  "tests/contract/test_proxy_ingest.py::test_a_second_ingest_over_an_unchanged_log_moves_nothing" \
  's = s.replace("from_seq = watermark(writer, session_id)", "from_seq = 0")'

proof "T093 — a row with no requirement is ingested instead of refused" \
  src/runtime/proxy_ingest.py \
  "tests/contract/test_proxy_ingest.py::test_a_row_with_no_requirement_is_refused" \
  's = s.replace("for field_name in (\x22rule_id\x22, \x22reason\x22, \x22requirement\x22):", "for field_name in ():")'

# `src/runtime/proxy_ingest.py` is on the `permitted` list for the
# engine-specific-SQL invariant, which suspends that check for the whole file.
# This proves the narrowing that pays for it — the file may hold SQL, but not a
# write — is a live check rather than a claim in a comment.
proof "T093 — a write statement enters the file the SQL invariant no longer scans" \
  src/runtime/proxy_ingest.py \
  "tests/contract/test_proxy_ingest.py::test_the_ingest_issues_no_write_statement_at_all" \
  's = s.replace("    def close(self) -> None:", "    def purge(self) -> None:\n        self._conn.execute(\x22DELETE FROM egress_decision\x22)\n\n    def close(self) -> None:")'

# --- T095, the egress-policy contract over every named denial reason ----------
#
# A contract test's mechanism is on the other side of the document, so these
# tamper the Go source and the contract itself rather than the test. Each is a
# drift a reviewer would not see: a reason renamed on one side, a containment
# widened on the other, a stage that stops being registered, and the clause
# that states the containment quietly dropped.
proof "T095 — a published reason is renamed in the registry, so a denial nobody can look up" \
  src/proxy/rules.go \
  "tests/contract/test_egress_policy.py::test_every_named_reason_in_the_contract_is_produced_by_a_registered_rule" \
  's = s.replace("Reason: \x22address_class_denied\x22", "Reason: \x22address_class_denied_v2\x22")'

proof "T095 — the exemption gains a second address slot, so two exemptible classes mean one each" \
  src/proxy/addresses.go \
  "tests/contract/test_egress_policy.py::test_two_exemptible_classes_and_exactly_one_exemption" \
  's = s.replace("type pinnedExemption struct {\n\taddr netip.Addr\n}", "type pinnedExemption struct {\n\taddr netip.Addr\n\tsecond netip.Addr\n}")'

proof "T095 — the clause that holds the containment is dropped from the contract" \
  specs/002-spec-aware-agent-runtime/contracts/egress-policy.md \
  "tests/contract/test_egress_policy.py::test_two_exemptible_classes_and_exactly_one_exemption" \
  's = s.replace("**Two exemptible classes, one\n   exemption**", "Two exemptible classes")'

proof "T095 — a gate stage stops being registered while its type stays behind" \
  src/proxy/main.go \
  "tests/contract/test_egress_policy.py::test_every_stage_type_that_exists_is_wired_into_the_pipeline" \
  's = s.replace("NewMethodStage(origin, policy),", "")'

# --- T113, the runtime's own default-deny egress plane ------------------------
#
# One proof per constitution Principle IV bullet-1 term, plus the hook itself
# and the fail-closed entry. The bullet says a configuration missing ANY ONE of
# the four terms does not satisfy it, so a proof per term is what the authority
# asks for rather than thoroughness for its own sake.
proof "T113 — the connect hook stops consulting the plane, so default-deny is decoration" \
  src/runtime/egress.py \
  "tests/contract/test_runtime_egress.py::test_a_connection_to_an_unpinned_destination_is_refused_on_the_wire" \
  's = s.replace("            plane.check(sock.family, address)\n            return saved[\x22connect\x22](sock, address)", "            return saved[\x22connect\x22](sock, address)")'

proof "T113 term 2 — the port drops out of matching, so host-granular permits the database" \
  src/runtime/egress.py \
  "tests/contract/test_runtime_egress.py::test_the_right_address_on_the_wrong_port_is_denied_by_its_own_rule" \
  's = s.replace("return self.address == address and self.port == port", "return self.address == address")'

proof "T113 term 3 — the resolver stops refusing names, so a lookup exfiltrates without connecting" \
  src/runtime/egress.py \
  "tests/contract/test_runtime_egress.py::test_a_name_lookup_is_denied_while_the_plane_is_installed" \
  's = s.replace("raise plane.resolution_denied(host) from None", "return")'

proof "T113 term 4 — the declaration-time class check removed, so loopback can be pinned" \
  src/runtime/egress.py \
  "tests/contract/test_runtime_egress.py::test_loopback_cannot_be_pinned_and_there_is_no_exemption_path" \
  's = s.replace("denied = classify(self.address)", "denied = None")'

# The second of the two class checks, and the one the constitution's "even on
# an allowlisted host" is about. Isolated from the arm above because the arm
# above is the declaration check: this tamper leaves that one intact.
proof "T113 term 4 — the connect-time class check removed, so an allowlisted metadata address is dialled" \
  src/runtime/egress.py \
  "tests/contract/test_runtime_egress.py::test_a_denied_class_is_refused_at_connect_time_even_when_pinned" \
  's = s.replace("        denied = classify(address)\n", "        denied = None\n")'

proof "T113 — a caller with no plane installed stops failing closed" \
  src/runtime/egress.py \
  "tests/contract/test_runtime_egress.py::test_a_caller_with_no_plane_installed_fails_closed" \
  's = s.replace("    if plane is None:", "    if False:")'

# The instrument, not the mechanism. The static scan is what binds T058's
# provider transport to the plane before that transport exists, so a scan that
# has stopped matching anything is the failure this arm is for.
proof "T113 instrument — the outbound scan matches nothing, so 'no unguarded call site' is free" \
  tests/contract/test_runtime_egress.py \
  "tests/contract/test_runtime_egress.py::test_the_outbound_scan_fires_on_a_planted_call" \
  's = s.replace("        for pattern in OUTBOUND_CALLS:", "        for pattern in OUTBOUND_CALLS[:0]:")'

proof "FR-049 pids.max — the bound not written" \
  src/supervisor/bounds.py \
  "tests/batteries/test_bounds_exhaustion.py::test_process_bound_exhaustion_names_its_terminal_state" \
  's = s.replace(chr(40)+chr(34)+"pids.max"+chr(34)+", str(bounds.pids_max)"+chr(41)+",", chr(40)+chr(34)+"pids.max"+chr(34)+", "+chr(34)+"max"+chr(34)+chr(41)+",")'

proof "FR-049 attach ordering — spawn barrier removed" \
  src/supervisor/cgroup.py \
  "tests/batteries/test_bounds_exhaustion.py::test_the_workload_is_in_the_cgroup_from_its_first_instruction" \
  's = s.replace("        try:\n            self.attach(pid)", "        try:\n            pass")'

proof "FR-050 lease — honoured_at ignores expiry" \
  src/supervisor/session_table.py \
  "tests/integration/test_lease_revocation.py::test_an_unrenewed_lease_lapses" \
  's = s.replace("return self.state == STATE_RUNNING and self.lease_expires_at > now", "return self.state == STATE_RUNNING")'

proof "FR-050 opaque handle — a structured claim instead" \
  src/supervisor/capability.py \
  "tests/integration/test_lease_revocation.py::test_the_handle_carries_no_claim_and_no_expiry" \
  's = s.replace("    handle = secrets.token_hex(HANDLE_BYTES)", "    handle = \x27eyJzZXNzaW9uIjoi\x27 + secrets.token_hex(HANDLE_BYTES)")'

# The tamper restores the swallow rather than deleting the handler: `return` in place of `raise` is
# the edit a contributor would actually make, and it is the state this file shipped until 2026-08-06.
# What makes this a proof of the *report* and not of the renewal count is that the arm's own
# `RENEWALS 1` assertion still passes under the tamper — one planted failure stops renewal at 1
# of 12 either way, and the lease is 0.5s expired either way. Only the stderr assertion moves.
#
# It targets the loop's TERMINAL branch specifically. Since the T016 migration `_loop` has two, and
# the arm this runs plants a raw `sqlite3.OperationalError` — which after the migration is not a
# store error at all and so can only reach the terminal one. The four-space indent difference is
# what keeps the tamper off the tolerated branch's `raise`.
proof "FR-050 lease renewal — the swallow restored, so a failed renewal is silent again" \
  src/supervisor/lease.py \
  "tests/integration/test_lease_revocation.py::test_a_failed_renewal_is_not_silent" \
  's = s.replace("{exc}\"\n                raise", "{exc}\"\n                return")'

# --- T108, the renewer branch the T016 migration made available ---------------
#
# `_loop` tolerates `StoreBusyError` up to the budget `LEASE_TTL_MULTIPLE` already
# grants and stops on everything else. Four mechanisms, four failure directions,
# and they are separated deliberately: a proof set that could not tell them apart
# would report the branch as load-bearing while any three of the four were gone.

# Collapse the split back to re-raise-everything — the pre-2026-08-06 behaviour,
# and the one this task was asked to rule on. Measured either side: one planted
# momentary contention on renewal 2 of 12 gives 1 renewal and a dead thread with
# the tamper applied, 10 and a live thread without it.
proof "T108 renewer — one momentary contention ends a healthy session again" \
  src/supervisor/lease.py \
  "tests/integration/test_lease_revocation.py::test_one_momentary_contention_does_not_end_a_healthy_lease" \
  's = s.replace("                if consecutive_busy > TOLERATED_CONSECUTIVE_BUSY:", "                if True:")'

# The other end of the same line: tolerate without bound. This is the option T108
# refused by name, and it is invisible in the arm above — that one plants a
# single failure, which is under the bound either way. Only a permanently
# planted refusal separates them, and it separates them by attempt count rather
# than by anything a message says.
proof "T108 renewer — contention is tolerated past the budget the lease grants" \
  src/supervisor/lease.py \
  "tests/integration/test_lease_revocation.py::test_contention_beyond_the_lease_budget_stops_renewal" \
  's = s.replace("                if consecutive_busy > TOLERATED_CONSECUTIVE_BUSY:", "                if False:")'

# Widen the split from the busy subclass to `StoreUnavailableError`, its base.
# The tamper is an import alias because that is the smallest honest edit: the
# handler body does not change, only which errors reach it. A wedged store — a
# lock that outlasted the entire busy timeout — then gets waited on, which is
# waiting for something that is not coming.
proof "T108 renewer — a wedged store is retried as though it were momentary" \
  src/supervisor/lease.py \
  "tests/integration/test_lease_revocation.py::test_a_wedged_store_stops_renewal_without_spending_the_budget" \
  's = s.replace("from src.contracts.repository import StoreBusyError", "from src.contracts.repository import StoreUnavailableError as StoreBusyError")'

# The reset, which is what makes the tolerance a budget rather than a lifetime
# quota. Without it a supervisor dies on the second momentary contention it ever
# sees, however many hours and however many healthy renewals apart the two were.
proof "T108 renewer — the tolerance becomes a lifetime quota" \
  src/supervisor/lease.py \
  "tests/integration/test_lease_revocation.py::test_the_tolerance_is_consecutive_and_not_cumulative" \
  's = s.replace("            consecutive_busy = 0", "            pass")'

proof "FR-036 Secret — a __str__ that discloses" \
  src/contracts/secret.py \
  "tests/invariants/test_secret_has_no_serializer.py::test_str_does_not_contain_the_value" \
  's = s.replace("    def __str__(self) -> str:\n        return _marker(self._name)", "    def __str__(self) -> str:\n        return self._value")'

proof "FR-011 rule id — the deny/rule_id check removed" \
  src/supervisor/fs_decisions.py \
  "tests/invariants/test_rule_id_present.py::test_a_deny_without_a_rule_id_cannot_be_constructed" \
  's = s.replace("        if self.disposition == DENY and not self.rule_id:", "        if False:")'

# The tamper moves the field as well as defaulting it, and it has to: a dataclass forbids a defaulted
# field ahead of a non-defaulted one, so a default on `verification` is only expressible below every
# field that has none. That makes {default, relocation} the unique minimal form of ONE mechanism
# removal rather than two — Python offers no other spelling of it — and the distinction is
# load-bearing here, because the T126 arm near the foot of this file defaults `corroboration`.
# Defaulting both in one tamper would remove two mechanisms and prove neither. `corroboration` keeps
# no default under this tamper, and `test_corroboration_has_no_default_in_the_source` goes on passing
# through it, which is the positive evidence that only one moved.
#
# **This arm read `unproven` at `2a5cdbf`, and the reason is worth keeping rather than tidying away.**
# The needle spanned `verification` and `payload` alone, which was right while `payload` was the only
# no-default field after it. T126 made `corroboration` required one field further on, so the tampered
# class raised `TypeError: non-default argument 'corroboration' follows default argument` when the
# decorator built `__init__`. The module never imported, no test ran, and the harness scored
# `unproven` with `tamper-broke-collection` — correctly, and without fabricating a pass. **The
# hardening is what disabled the tamper**: making the corroboration required is precisely what turned
# an edit that used to produce a live wrong program into one that produces a dataclass error.
#
# `tools/check_tampers.py` cannot catch this class and could not have. It checks that the needle still
# matches and that the result still `compile()`s, and here both succeed perfectly — field-ordering is
# enforced when the decorator runs, which is import time and not compile time. That asymmetry is
# recorded in `tools/README.md` under what none of it catches.
#
# **The selector names one test rather than the whole file, and that was measured rather than tidied.**
# Relocating the field also breaks five behavioural arms in this file on `TypeError:
# Result.__init__() got multiple values for argument 'payload'`, which is positional collateral and
# not FR-025's property. Measured 2026-08-12: with the file as the selector and
# `test_verification_has_no_default_in_the_source` deleted outright, the tampered run still read
# `5 failed` and the arm would still have scored `proved` — so the file-level selector could not tell
# the guard it names from the collateral, and would have survived that guard's deletion. Naming the
# test makes the arm's failure identity its own assertion, and turns a deleted guard into a
# `check_tampers.py` error instead of a silent pass.
#
# Residue, stated rather than closed: the arm lands on the first of that test's two assertions —
# verification must be the first field — and no single-edit tamper can reach the second, because the
# configuration it catches, a default on a field that is still first, is one Python refuses to build.
proof "FR-025 result — verification given a default" \
  src/contracts/result.py \
  "tests/invariants/test_result_constructor.py::test_verification_has_no_default_in_the_source" \
  's = s.replace("    verification: VerificationOutcome\n    payload: Any\n    corroboration: Corroboration\n", "    payload: Any\n    corroboration: Corroboration\n    verification: VerificationOutcome = VerificationOutcome.VERIFIED\n")'

proof "FR-006 taxonomy — closed membership becomes a prefix match" \
  src/contracts/terminal.py \
  "tests/invariants/test_terminal_taxonomy.py::test_membership_is_closed_not_a_prefix_match" \
  's = s.replace("    return name in NAMES", "    return name.startswith(chr(116)+chr(101)+chr(114)+chr(109)+chr(105)+chr(110)+chr(97)+chr(116)+chr(101)+chr(100)+chr(46))")'

proof "Q-10 no-default bounds — a default added" \
  src/contracts/config.py \
  "tests/invariants/test_no_default_bounds.py::test_no_default_is_declared" \
  's = s.replace(chr(34)+"memory.max on the session cgroup"+chr(34)+", no_default_reason=_NO_DEFAULT_BOUND"+chr(41), chr(34)+"memory.max on the session cgroup"+chr(34)+", default="+chr(34)+"512MiB"+chr(34)+chr(41))'

# The proof above plants on SANDBOX_MEMORY_MAX, which three separate sites cover — INV-006 by name,
# the fail-loud check by requirement, and the loader test by absence. Until 2026-08-12 it named the
# whole of `test_no_default_bounds.py`, so it proved only that the property was checked *somewhere*
# and could not notice any one of those sites narrowing; measured then, the tamper failed three of
# that file's tests and the arm still scored `proved` with its intended guard deleted outright. It
# now names `test_no_default_is_declared`, so it is attributed to one site. **That repair does not
# make this arm redundant**, and the reason is the key rather than the selector. This one plants on
# MODEL_PRICES_OPERATOR, and the two are not redundant: measured against this exact plant, the old
# requirement-gated check flagged nothing, `test_no_default_bounds.py` and `test_result_bound.py`
# passed, and the widened check was the only thing in the repository that failed. It is the arm that
# would notice the selector being tidied back to a requirement list, which is how the key came to be
# uncovered in the first place.
proof "OD-27 operator prices — a default added beside its own no-default reason" \
  src/contracts/config.py \
  "tests/contract/test_configuration_failloud.py::test_no_key_that_states_a_no_default_reason_acquires_a_default" \
  's = s.replace("no_default_reason=_NO_DEFAULT_OPERATOR_PRICES)", "no_default_reason=_NO_DEFAULT_OPERATOR_PRICES, default=\x22none\x22)")'


# ---------------------------------------------------------------------------
# The cross-language capability boundary.
#
# These are the proofs that matter most, because the boundary they cover has
# nothing structural holding it together — the supervisor and the enforcement
# point agree about the digest and the schema only because two people wrote
# the same thing twice. Both failure modes are total and silent.

go_proof () {
  local name="$1" file="$2" test="$3" python_edit="$4"
  _P_NAME="$name"; _P_FILE="$file"; _P_TEST="$test"; _P_DRIFTED=no
  # Unreachable by design: the toolchain check under the baseline aborts when this
  # file declares Go arms and no `go` is on PATH. It is kept, and turned from a
  # skip into a refusal, because the count that check reads is `^go_proof "` and
  # a declaration this function still receives without matching that anchor — an
  # indented one, which is the exact rot `tools/check_tampers.py` was written
  # against — would arrive here. Scoring that as a skip is how twelve arms went
  # missing from a green run in the first place.
  if [ "$HAVE_GO" -eq 0 ]; then
    echo "  CANNOT RUN $name — no Go toolchain, and the abort above did not fire."
    echo "            This arm's declaration is not matched by the count that guards"
    echo "            it. Refusing to score it either way."
    _record unreadable go-arm-past-the-toolchain-abort
    UNREADABLE=$((UNREADABLE+1))
    return
  fi
  local verdict
  verdict=$(baseline_go "$test")
  if report_unrunnable "$verdict" "$name" "$test"; then return; fi

  apply_tamper "$name" "$file" "$python_edit" || return

  # `-count=1` here too. A tampered file normally forces a cache miss on its
  # own, but that holds only while no two arms share both a tamper and a `-run`
  # pattern — and two of the FR-017 arms already share a tamper and differ only
  # in the pattern. One future arm reusing both would be served the previous
  # arm's verdict, which is a proof reporting a result it did not take.
  local output
  output=$(cd "$WORK/src/proxy" \
             && python3 "$CAP" "$PROOF_TIMEOUT" go test -count=1 -run "$test" ./... 2>&1)
  local status=$?
  if [ "$status" -eq "$TIMED_OUT_STATUS" ]; then
    report_timeout "$name"
  elif [ "$status" -gt 128 ]; then
    report_signalled "$name" "$status"
  elif [ "$status" -eq 0 ]; then
    echo "  UNPROVEN  $name — the test still passes with the mechanism removed"
    _record unproven still-passes-without-the-mechanism
    FAIL=$((FAIL+1))
  elif echo "$output" | grep -q 'build failed'; then
    # A package that will not compile fails every test in it, which is not the
    # same claim as the test noticing the mechanism is gone.
    echo "  BROKEN    $name — the tampered package does not build; no test ran"
    _record unproven tampered-package-does-not-build
    FAIL=$((FAIL+1))
  else
    echo "  proved    $name"
    _record proved ""
    PASS=$((PASS+1))
  fi
  mv "$file.orig" "$file"
  drop_bytecode "$file"
}

proof "conformance — the supervisor's digest convention changed" \
  src/supervisor/session_table.py \
  "tests/unit/test_session_conformance.py::test_the_digest_convention_has_not_moved" \
  's = s.replace("    return hashlib.sha256(handle.encode(\x22utf-8\x22)).hexdigest()", "    return hashlib.sha256(bytes.fromhex(handle)).hexdigest()")'

go_proof "conformance — the proxy digests the decoded bytes instead" \
  src/proxy/capability.go \
  "TestDigestConventionMatchesTheSupervisor" \
  's = s.replace("\tsum := sha256.Sum256([]byte(handle))", "\tdecoded, _ := hex.DecodeString(handle)\n\tsum := sha256.Sum256(decoded)")'

go_proof "conformance — a column name drifts apart" \
  src/proxy/session.go \
  "TestSupervisorWrittenSessionTableIsReadable" \
  's = s.replace("WHERE capability_sha256 = ?", "WHERE capability_digest = ?")'

go_proof "conformance — stage 1 checks only the lease, not the state" \
  src/proxy/capability.go \
  "TestTerminatedSessionWithLiveLeaseIsDenied" \
  's = s.replace("row.State != sessionStateRunning", "false")'

proof "SC-022 path marking — a default provenance added" \
  src/supervisor/fs_decisions.py \
  "tests/unit/test_path_provenance.py::test_a_record_cannot_be_built_without_stating_its_path_provenance" \
  's = s.replace("    path_provenance: str = None  # type: ignore[assignment]", "    path_provenance: str = PATH_SUPERVISOR_READ")'

proof "SC-022 path marking — the supervisor read declared authoritative" \
  src/supervisor/fs_decisions.py \
  "tests/unit/test_path_provenance.py::test_everything_v1_emits_is_marked_unverified" \
  's = s.replace("AUTHORITATIVE_PATH_PROVENANCES = frozenset({PATH_KERNEL_RESOLVED})", "AUTHORITATIVE_PATH_PROVENANCES = frozenset({PATH_KERNEL_RESOLVED, PATH_SUPERVISOR_READ})")'

proof "SC-022 path marking — the caveat dropped from the serialized record" \
  src/supervisor/fs_decisions.py \
  "tests/unit/test_path_provenance.py::test_the_provenance_reaches_the_serialized_record" \
  's = s.replace(chr(34)+"path_provenance"+chr(34)+": self.path_provenance,\n", "")'

# ---------------------------------------------------------------------------
# FR-017's pinned-origin exemption (owner decision 2026-08-03, extended to loopback the same day).
#
# The exemption's risk is not that it fails — it is that it GENERALISES. Most of the proofs below
# therefore remove a containment property rather than the feature, and pass only if a test notices
# the widening.
#
# The exemptible set holds TWO classes since the loopback extension, which adds a second way to
# generalise that did not exist while it held one: not "one address becomes a range" but "one
# address becomes one address PER CLASS". The last three proofs cover the loopback path and that
# new failure mode; a proof set that only tampered the RFC1918 path would leave both unproven.
#
# The tamper strings below carry TWO spaces after `classPrivate:`, which is gofmt's alignment of
# the two-entry map. When the map had one entry they carried one space, and adding the second
# entry made every one of them match nothing. That is now survivable rather than fatal — the
# matcher normalizes intra-line whitespace — but the strings are still written in the source's
# current form, because a proof that matches only after normalization reports `drifted` and is a
# repair waiting to be made. The next edit that changes the longest key in that map will realign
# it again and the proofs will keep applying.

go_proof "FR-017 exemption — the declared RFC1918 origin stops being reachable" \
  src/proxy/addresses.go \
  "TestTheDeclaredRFC1918OriginIsReachable" \
  's = s.replace("\tclassPrivate:  true,\n", "")'

go_proof "FR-017 exemption — the declared loopback origin stops being reachable" \
  src/proxy/addresses.go \
  "TestTheDeclaredLoopbackOriginIsReachable" \
  's = s.replace("\tclassLoopback: true,\n", "")'

go_proof "FR-017 containment — the exemption widened to a prefix" \
  src/proxy/addresses.go \
  "TestADifferentRFC1918AddressIsStillDenied|TestTheExemptionIsAnAddressNotAPrefix" \
  's = s.replace("\treturn e.addr.IsValid() \x26\x26 e.addr == addr", "\treturn e.addr.IsValid() \x26\x26 netip.PrefixFrom(e.addr, 24).Masked().Contains(addr)")'

# The same tamper against the loopback path alone. Sharing a test alternation with the RFC1918
# proof above would let the loopback assertion rot unnoticed, because the RFC1918 half would go on
# failing the run on its own.
go_proof "FR-017 containment — the loopback exemption widened to a prefix" \
  src/proxy/addresses.go \
  "TestADifferentLoopbackAddressIsStillDenied" \
  's = s.replace("\treturn e.addr.IsValid() \x26\x26 e.addr == addr", "\treturn e.addr.IsValid() \x26\x26 netip.PrefixFrom(e.addr, 24).Masked().Contains(addr)")'

# The failure mode two exemptible classes introduce: an exemption that excuses every address in
# any exemptible class rather than the one that was declared.
go_proof "FR-017 containment — the exemption widened to its whole class" \
  src/proxy/addresses.go \
  "TestOneDeclaredOriginExemptsExactlyOneAddress" \
  's = s.replace("\treturn e.addr.IsValid() \x26\x26 e.addr == addr", "\tif c, isDenied := classify(addr); isDenied \x26\x26 exemptibleClasses[c] {\n\t\treturn true\n\t}\n\treturn e.addr.IsValid() \x26\x26 e.addr == addr")'

go_proof "FR-017 containment — link-local becomes exemptible" \
  src/proxy/addresses.go \
  "TestExemptibleClassesIsExactlyPrivateAndLoopback|TestTheMetadataServiceCannotBeExemptedByDeclaringIt" \
  's = s.replace("\tclassPrivate:  true,\n", "\tclassPrivate:  true,\n\tclassLinkLocal: true,\n\tclassMetadata: true,\n")'

go_proof "FR-017 ordering — the exemption consulted before the class is decided" \
  src/proxy/addresses.go \
  "TestTheMetadataServiceCannotBeExemptedByDeclaringIt" \
  's = s.replace("\tif !exemptibleClasses[class] {\n\t\treturn class, true\n\t}\n\tif exempt.exempts(a) {\n\t\treturn \x22\x22, false\n\t}\n\treturn class, true", "\tif exempt.exempts(a) {\n\t\treturn \x22\x22, false\n\t}\n\tif !exemptibleClasses[class] {\n\t\treturn class, true\n\t}\n\treturn class, true")'

# ---------------------------------------------------------------------------
# Phase 2 — schemas, canonical serialization, storage, configuration, tracing.
#
# These mechanisms are structural rather than kernel-facing, and the failure
# mode is the same for all of them: the check degrades to something permissive
# and every test keeps passing. Each proof therefore removes the *discriminating*
# part of a check, not the check itself.
# ---------------------------------------------------------------------------

proof "FR-055 canonical order — key sorting removed" \
  src/contracts/canonical.py \
  "tests/contract/test_canonical_determinism.py::test_key_insertion_order_does_not_change_the_bytes" \
  's = s.replace("for i, key in enumerate(sorted(value, key=_sort_key)):", "for i, key in enumerate(value):")'

proof "FR-055 envelope — volatile values left in the hashed payload" \
  src/contracts/envelope.py \
  "tests/contract/test_canonical_determinism.py::test_changing_a_volatile_value_does_not_move_the_address" \
  's = s.replace("    payload = {k: v for k, v in document.items() if k not in schema.volatile}", "    payload = dict(document)")'

proof "FR-055 volatility scan — the detector stops detecting" \
  src/contracts/envelope.py \
  "tests/contract/test_canonical_determinism.py::test_the_volatility_scanner_catches_an_undeclared_volatile_value" \
  's = s.replace("    findings = scan(payload, schema)", "    findings = []")'

# T015 gates a *version regression*, so the tamper is a version that moved backwards
# without the required bump — the exact edit the gate exists to catch.
proof "T015 schema gate — a version moves backwards unnoticed" \
  src/contracts/schemas.py \
  "tests/contract/test_schema_versions.py::test_the_version_never_moves_backwards" \
  's = s.replace("    kind=\x22served_operation_set\x22,\n    version=\x221.1.0\x22,", "    kind=\x22served_operation_set\x22,\n    version=\x221.0.0\x22,")'

proof "T015 schema gate — a required field removed without a MAJOR bump" \
  src/contracts/schemas.py \
  "tests/contract/test_schema_versions.py::test_a_removed_or_renamed_required_field_is_a_major_bump" \
  's = s.replace("    required=(\x22schema_version\x22, \x22deployment_id\x22, \x22set_version\x22, \x22captured_at\x22,\n              \x22operations\x22),", "    required=(\x22schema_version\x22, \x22deployment_id\x22, \x22set_version\x22),")'

# The tamper names the guard inside `migrate`, not the string `raise MigrationError(`.
# That string occurs five times, and the first is at module scope inside the duplicate-registration
# loop — so the old tamper inserted a `return` outside a function, the module stopped parsing, and
# every test in it failed for a reason this proof does not claim. It read as `proved` for as long
# as it existed. `tools/check_tampers.py` is what surfaced it.
proof "T014 migration — a stale document passes through unmigrated" \
  src/contracts/migrations/__init__.py \
  "tests/contract/test_migrations.py::test_a_document_with_no_path_forward_is_refused_not_passed_through" \
  's = s.replace("        if migration is None:\n", "        if migration is None:\n            return dict(document)\n")'

proof "T017 ownership — a non-owner may write" \
  src/contracts/ownership.py \
  "tests/invariants/test_writer_ownership.py::test_only_the_owner_may_write_each_table" \
  's = s.replace("def require_write(", "def require_write(*_unused_a, **_unused_k):\n    return None\n\n\ndef _disabled_require_write(")'

proof "T016 scope columns — the caller supplies its own tenant" \
  src/contracts/repository.py \
  "tests/invariants/test_writer_ownership.py::test_a_caller_cannot_set_its_own_scope" \
  's = s.replace("        if any(c in row for c in SCOPE_COLUMNS):", "        if False:")'

proof "T019 object store — an address may be overwritten" \
  src/analysis/artifact_store.py \
  "tests/contract/test_rollback.py::test_the_object_store_refuses_to_overwrite_an_address" \
  's = s.replace("        if target.exists():\n            existing = target.read_bytes()", "        if False:\n            existing = target.read_bytes()")'

proof "T020 rollback — the restoration record stops naming an operator" \
  src/analysis/rollback.py \
  "tests/contract/test_rollback.py::test_an_unattributed_restoration_is_refused" \
  's = s.replace("    if not operator:", "    if False:")'

proof "T032 fail-closed config — startup proceeds with values missing" \
  src/contracts/config.py \
  "tests/contract/test_configuration_failloud.py::test_each_required_key_unset_fails_and_names_itself" \
  's = s.replace("    if missing or invalid:\n        raise ConfigError(_report(missing, invalid))", "    if False:\n        raise ConfigError(_report(missing, invalid))")'

proof "T033 unvalidated marking — the marker dropped from the rendering" \
  src/contracts/unvalidated.py \
  "tests/contract/test_unvalidated_marking.py::test_string_interpolation_carries_the_marking" \
  's = s.replace("        return f\x22{self.value} ({MARKER}: {self.provenance})\x22", "        return str(self.value)")'

proof "FR-036 marker — the key name dropped, leaving an undiagnosable trace" \
  src/contracts/secret.py \
  "tests/invariants/test_secret_has_no_serializer.py::test_the_marker_names_the_key_it_stands_for" \
  's = s.replace("    return f\x22<redacted:Secret {name}>\x22 if name else REDACTED", "    return REDACTED")'

proof "T037 rule id — a decision span may omit its rule" \
  src/runtime/trace.py \
  "tests/contract/test_trace_spans.py::test_a_decision_span_cannot_be_built_without_a_rule" \
  's = s.replace("        if self.kind in DECISION_KINDS and self.decision is None:", "        if False:")'

proof "Principle VI — a state_transition span may omit its predicate inputs" \
  src/contracts/transition.py \
  "tests/unit/test_state_transition.py::test_a_selecting_rule_cannot_omit_its_predicate_inputs" \
  's = s.replace("        if rule.selects_among_alternatives and not self.predicate_inputs:", "        if False:")'

proof "Principle VI — bounds.check stops recording the inputs it did not match" \
  src/supervisor/bounds.py \
  "tests/unit/test_state_transition.py::test_from_bound_outcome_carries_every_reading" \
  's = s.replace("        readings=readings,", "        readings=readings[:1],")'

proof "FR-049 preflight — the cgroup.kill probe reads the root cgroup" \
  src/supervisor/preflight.py \
  "tests/unit/test_kernel_floor.py::test_the_kill_probe_reads_a_child_cgroup_and_not_the_root" \
  's = s.replace("    probe = root / CGROUP_KILL_PROBE", "    probe = root")'

# T206's two arms, proved separately, because they fail in different directions.
# The first removes the syscall attempt and restores the pre-T206 behaviour: a
# check that reports green from `/proc/self/ns/` presence and a sysctl, neither
# of which can observe a runtime seccomp refusal. The second keeps the syscall
# and removes only the no-op arm, which is the cell that tells a fixable
# runtime-profile refusal from an LSM or sysctl one — the mechanism still runs,
# and only the layer attribution is wrong, which is the harder failure to notice.
proof "T206 preflight — the namespaces check goes back to presence and a sysctl" \
  src/supervisor/preflight.py \
  "tests/unit/test_namespace_probe.py::test_presence_and_the_sysctl_are_not_evidence_the_mechanism_works" \
  's = s.replace("    ok, layer, message = _classify_unshare_pair(\n        attempt(UNSHARE_NOOP), attempt(CLONE_NEWUSER)\n    )", "    ok, layer, message = True, LAYER_AVAILABLE, \x22presence only\x22")'

proof "T206 preflight — the unshare(0) discriminator is assumed rather than attempted" \
  src/supervisor/preflight.py \
  "tests/unit/test_namespace_probe.py::test_both_arms_refused_is_attributed_to_the_runtime_seccomp_profile" \
  's = s.replace("        attempt(UNSHARE_NOOP), attempt(CLONE_NEWUSER)", "        UnshareAttempt(UNSHARE_NOOP, True, True, None, \x22assumed\x22), attempt(CLONE_NEWUSER)")'

# T207's three arms. The first is the coverage gap itself — the check deleted
# from the set, which is the state 95c871d was in and which reported **every
# FR-048 check green** in the operator-trap arm, FR-048 being the requirement
# that owns the mount and containment sequence. (Not "wholly green": finding
# 026 measured 5 of 7 there, and both reds are FR-049 cgroup artifacts of the
# container rather than anything about the mount sequence.) The other two are
# the ways the check can be present
# and wrong, and both invert a verdict rather than losing one, which is the
# harder failure to notice: pivot_root's permitted reading is a *failure* with
# EBUSY, and its EPERM is only attributable to seccomp in a process holding
# CAP_SYS_ADMIN.
proof "T207 preflight — pivot_root is not in the check set at all" \
  src/supervisor/preflight.py \
  "tests/unit/test_pivot_root_probe.py::test_run_checks_asks_about_pivot_root_after_it_asks_about_unshare" \
  's = s.replace("        checks.append(_check_pivot_root())", "        pass")'

# Repointed at T209. The mechanism that resolves EBUSY moved: it used to be an
# unconditional branch, which arm G falsified by forging a 16, and it is now the
# pair. The defect the proof names is unchanged — EBUSY read as a refusal on a
# host where pivot_root works — so the proof follows the mechanism.
proof "T207 preflight — EBUSY is scored as a refusal instead of as reaching the kernel" \
  src/supervisor/preflight.py \
  "tests/unit/test_pivot_root_probe.py::test_ebusy_is_permitted_because_the_call_reached_the_kernel" \
  's = s.replace("        and attempt.errno in _POST_AUTHORITY_ERRNOS\n", "        and attempt.errno == _EINVAL\n")'

proof "T207 preflight — an EPERM is blamed on seccomp without reading the capability" \
  src/supervisor/preflight.py \
  "tests/unit/test_pivot_root_probe.py::test_eperm_without_the_capability_is_not_attributed_to_seccomp" \
  's = s.replace("    if attempt.errno == _EPERM and sys_admin is True:", "    if attempt.errno == _EPERM:")'

# The three below are the generalisation of the EBUSY proof above, and they exist
# because that proof was not enough. It pinned one errno of a class: EBUSY was
# what all six of finding 026's container arms produced, so `EINVAL` — its
# sibling, produced by the same argument-checking block one branch earlier — went
# uncovered, and CI run 30970910828 reported `refused-unattributed` for a
# permitted syscall on the ubuntu-latest runner. The first restores exactly that
# defect. The second and third are the two ways the fix for it can be wrong in
# opposite directions, and both leave the check present and confidently wrong.
proof "T208 preflight — only EBUSY is resolved, so EINVAL reads as a refusal" \
  src/supervisor/preflight.py \
  "tests/unit/test_pivot_root_probe.py::test_einval_with_no_filter_installed_reached_the_kernel" \
  's = s.replace("attempt.errno in _POST_AUTHORITY_ERRNOS and no_filter", "attempt.errno == _EBUSY and no_filter")'

# Widening in the permissive direction. `defaultErrnoRet` can carry any errno, so
# resolving one without reading the filter posture makes a seccomp refusal read
# as available — the constraint the EINVAL fix was required to preserve.
proof "T208 preflight — the seccomp-mode gate is dropped from the resolved class" \
  src/supervisor/preflight.py \
  "tests/unit/test_pivot_root_probe.py::test_einval_with_a_filter_installed_or_unreadable_stays_unresolved" \
  's = s.replace("    if attempt.errno in _POST_AUTHORITY_ERRNOS and no_filter:", "    if attempt.errno in _POST_AUTHORITY_ERRNOS:")'

# The mistake the obvious fix makes. "Any errno that is not EPERM proves the call
# reached the kernel" is false: path_pivot_root() calls security_sb_pivotroot()
# before every argument check and AppArmor's hook denies with EACCES, so admitting
# EACCES to the resolved class reports containment working on a host where an LSM
# refuses the syscall outright.
# The verdict here was never wrong; the sentence was. An EINVAL under a filter is
# an errno path_pivot_root() does produce, withheld because defaultErrnoRet could
# have forged it — which is not the same as an errno nobody has a reading for, and
# the remedy differs (re-read with the filter off vs. there is no remedy). Measured
# by correction arm C, which put the unrecognised text out for a recognised errno.
proof "T208 preflight — a withheld post-authority errno is reported as unrecognised" \
  src/supervisor/preflight.py \
  "tests/unit/test_pivot_root_probe.py::test_einval_under_a_filter_is_not_described_as_an_unrecognised_errno" \
  's = s.replace("    if attempt.errno in _POST_AUTHORITY_ERRNOS:\n", "    if False:\n")'

# T209 — the pair. A single pivot_root call cannot separate the kernel answering
# from a filter answering as the kernel, because SCMP_ACT_ERRNO returns an errno
# of the profile author's choosing. A second invocation differing only in its
# path pointers can, because a BPF program may not dereference pointers and so
# must answer both calls identically. These four hold that reasoning in place.

# Arm G, restored. The unconditional EBUSY branch read `available` while a filter
# refused the syscall outright — a green containment gate over absent
# containment, which is the worst direction this check can fail in.
proof "T209 preflight — a forged constant errno is resolved without the pair" \
  src/supervisor/preflight.py \
  "tests/unit/test_pivot_root_probe.py::test_a_forged_constant_errno_is_not_resolved_by_the_pair" \
  's = s.replace("    if attempt.ok:\n", "    if attempt.ok or attempt.errno == _EBUSY:\n")'

# The correction to the pair rule. security_sb_pivotroot() runs after
# user_path_at() on every kernel, so an LSM refusal answers EACCES to one call
# and ENOENT to the other — a pair that differs on a host that refused outright.
# Dropping the authority guard turns that into a permit.
proof "T209 preflight — the authority guard is dropped, so a differing pair always resolves" \
  src/supervisor/preflight.py \
  "tests/unit/test_pivot_root_probe.py::test_an_authority_errno_on_the_second_call_also_blocks_resolution" \
  's = s.replace("    if attempt.errno not in _AUTHORITY_ERRNOS and authority:\n", "    if False:\n")'

# Arm F. Without the pair being consulted the check falls back to the seccomp
# mode, and a shared-root host running a filter that PERMITS pivot_root reads as
# refused — a red gate on a working host.
proof "T209 preflight — the second invocation is ignored, so only Seccomp 0 resolves" \
  src/supervisor/preflight.py \
  "tests/unit/test_pivot_root_probe.py::test_the_pair_resolves_without_needing_the_seccomp_mode" \
  's = s.replace("        probe is not None\n", "        False\n")'

# Measured the hard way: ("/proc", "/proc") returned 0 and pivoted the probe
# child. The second invocation must name a path that cannot resolve, so it fails
# at user_path_at() before any mount machinery runs.
proof "T209 preflight — the second invocation names a path that can exist" \
  src/supervisor/preflight.py \
  "tests/unit/test_pivot_root_probe.py::test_the_absent_path_probe_is_a_path_that_cannot_exist" \
  's = s.replace("_ABSENT_PROBE_PATH = b\"/f2a-preflight-no-such-path\"", "_ABSENT_PROBE_PATH = b\"/proc\"")'

proof "T208 preflight — EACCES is admitted to the class that reads as permitted" \
  src/supervisor/preflight.py \
  "tests/unit/test_pivot_root_probe.py::test_eacces_is_never_read_as_reaching_the_kernel" \
  's = s.replace("_POST_AUTHORITY_ERRNOS = frozenset({_EBUSY, _EINVAL})", "_POST_AUTHORITY_ERRNOS = frozenset({_EBUSY, _EINVAL, _EACCES})")'

proof "FR-038 ordering — the span position has no unique index" \
  src/runtime/trace.py \
  "tests/contract/test_trace_spans.py::test_two_writers_over_one_repository_cannot_share_a_position" \
  's = s.replace("}, unique=[(\x22session_id\x22, \x22turn\x22, \x22ordinal\x22)])", "})")'

proof "FR-038 ordering — a resumed writer restarts its ordinals at zero" \
  src/runtime/trace.py \
  "tests/contract/test_trace_spans.py::test_a_resumed_writer_does_not_reissue_an_ordinal" \
  's = s.replace("            ordinal = self._highest_written(session_id, turn) + 1", "            ordinal = 0")'

proof "FR-036 trace — a Secret may reach a span" \
  src/runtime/trace.py \
  "tests/contract/test_trace_redaction.py::test_a_secret_cannot_be_placed_in_a_span_at_all" \
  's = s.replace("        _refuse_secrets_anywhere(self)", "        pass")'

# The two below are the specific narrowings that produced defect X3. The proof
# above only establishes that *a* scan runs; these establish that it covers the
# whole type and descends through the structured fields, which is the part that
# was one-sixth of what its test name claimed.
proof "FR-036 trace — the Secret scan covers only detail again" \
  src/runtime/trace.py \
  "tests/contract/test_trace_spans.py::test_a_secret_nested_in_any_carrier_field_is_refused" \
  's = s.replace("    for f in fields(span):\n        _refuse_secrets(getattr(span, f.name), f.name)", "    _refuse_secrets(span.detail, \x22detail\x22)")'

# The walker itself now lives in src/contracts/secret.py because the event
# stream needs the same refusal and a second copy would drift. The proof
# follows the code; the target test is unchanged.
proof "FR-036 — the shared Secret scan stops at a nested dataclass" \
  src/contracts/secret.py \
  "tests/contract/test_trace_spans.py::test_a_secret_nested_in_any_carrier_field_is_refused" \
  's = s.replace("    elif is_dataclass(value) and not isinstance(value, type):", "    elif False:")'

proof "FR-036 — the shared Secret scan stops at a mapping key" \
  src/contracts/secret.py \
  "tests/contract/test_event_stream_redaction.py::test_a_secret_used_as_a_mapping_key_is_refused" \
  's = s.replace("            refuse_secrets(key, f\x22{path}.<key>\x22, raise_as=raise_as,\n                           destination=destination)", "            pass")'

proof "T038 journal location — a ledger inside the session root is accepted" \
  src/runtime/trace_budget.py \
  "tests/contract/test_budget_journal.py::test_a_journal_inside_the_session_root_is_refused" \
  's = s.replace("    if journal == root or root in journal.parents:", "    if False:")'

# Distinct from the proof above: that one removes the *check*, this one removes
# the constructor's *call* to it, which is the shape defect X2 actually had —
# the check was correct and simply never ran for the construction every caller
# makes.
proof "T038 journal location — the constructor stops running the check" \
  src/runtime/trace_budget.py \
  "tests/contract/test_budget_journal.py::test_the_journal_constructor_enforces_the_location" \
  's = s.replace("        assert_outside_session_root(repository.path, session_root)", "        pass")'

# --- FR-048 / SC-022: the write-mode classification (defect X4) -------------

proof "FS-002 — an open for writing is classified by syscall name alone" \
  src/supervisor/fs_decisions.py \
  "tests/unit/test_fs_write_mode.py::test_an_open_for_writing_at_a_readonly_location_is_denied" \
  's = s.replace("    modifies = syscall in WRITE_SYSCALLS or (", "    modifies = syscall in WRITE_SYSCALLS and (")'

proof "FS-002 — a truncating open counts as a read" \
  src/supervisor/fs_decisions.py \
  "tests/unit/test_fs_write_mode.py::test_the_modifying_flags_are_writes_even_without_o_wronly" \
  's = s.replace("WRITE_OPEN_FLAGS = O_CREAT | O_TRUNC | O_APPEND", "WRITE_OPEN_FLAGS = 0")'

proof "FS-002 — a write to a declared location records the wrong mode" \
  src/supervisor/fs_decisions.py \
  "tests/unit/test_fs_write_mode.py::test_the_audit_record_names_the_declared_mode_it_violated" \
  's = s.replace("            return built(DENY, location.mode, WRITE_TO_READONLY)", "            return built(DENY, \x22absent\x22, WRITE_TO_READONLY)")'

proof "FS-006 — an open with no flag word is assumed to be a read" \
  src/supervisor/fs_decisions.py \
  "tests/unit/test_fs_write_mode.py::test_a_flagless_open_is_not_assumed_to_be_a_read" \
  's = s.replace("    if syscall in OPEN_SYSCALLS and flags is None:", "    if False:")'

proof "FR-048 — the listener stops reading the open flag word" \
  src/supervisor/seccomp.py \
  "tests/unit/test_fs_write_mode.py::test_every_open_syscall_has_a_flags_argument_index" \
  's = s.replace("_FLAGS_ARG = {\x22open\x22: 1, \x22openat\x22: 2}", "_FLAGS_ARG = {\x22open\x22: 1}")'

# The watch-set guard has three call sites and this is the third. It is here rather
# than on the watch-set *completion* — the four names added to WRITE_SYSCALLS — and
# the reason is measured. Tampering the completion instead trips
# `check_watch_set_is_wired` at session start, so 9 tests fail and 4 error across
# `test_seccomp_recording.py` and the overhead battery, and none of them records the
# `allow` such a proof would claim to demonstrate; the failure names the guard doing
# its job, not the classifier. Tampering the `install_filter` call site is worse than
# unhelpful: with the guard gone the test installs a USER_NOTIF filter on the pytest
# process itself and blocks forever in `seccomp_do_user_notification` with nobody
# holding the descriptor — observed on `6.12.76-linuxkit`/`aarch64`, and `proof()`
# has no timeout, so that arm hangs the harness rather than reporting anything.
proof "FR-048 watch-set guard — the listener stops consulting it" \
  src/supervisor/seccomp.py \
  "tests/unit/test_watch_set_wiring.py::test_the_listener_asks_the_guard_before_reading_any_notification" \
  's = s.replace("        check_watch_set_is_wired(watched)\n        self._names", "        self._names")'

proof "T038 accrual — the ledger is written once instead of as it accrues" \
  src/runtime/trace_budget.py \
  "tests/contract/test_budget_journal.py::test_the_ledger_survives_a_kill_with_no_flush" \
  's = s.replace("        with self._lock:\n            self.repo.insert(TABLE, {", "        if consumption.ordinal > 0:\n            return self.totals(consumption.session_id)\n        with self._lock:\n            self.repo.insert(TABLE, {")'

proof "OD-17 kernel floor — an old kernel passes the check" \
  src/supervisor/preflight.py \
  "tests/unit/test_kernel_floor.py::test_a_kernel_below_the_floor_fails_the_check" \
  's = s.replace("    if parsed < MINIMUM_KERNEL:", "    if False:")'

proof "OD-17 kernel floor — an unparseable release is assumed new enough" \
  src/supervisor/preflight.py \
  "tests/unit/test_kernel_floor.py::test_an_unparseable_kernel_fails_the_check" \
  's = s.replace("    if parsed is None:", "    if parsed is None:\n        parsed = MINIMUM_KERNEL\n    if False:")'

proof "OD-17 floor marking — the derived-not-tested caveat dropped" \
  src/supervisor/preflight.py \
  "tests/unit/test_kernel_floor.py::test_the_floor_is_marked_as_derived_and_not_tested" \
  's = s.replace("        \x22DERIVED from documented feature introduction and NOT TESTED on that \x22\n        \x22kernel; every run to date was on 6.12 or 6.17\x22", "        \x22established\x22")'

proof "FR-049 kill_all — the racy per-pid fallback restored" \
  src/supervisor/cgroup.py \
  "tests/unit/test_kernel_floor.py::test_kill_all_refuses_rather_than_degrading" \
  's = s.replace("        if not path.is_file():\n            raise CgroupError(", "        if not path.is_file():\n            for pid in self.live_pids():\n                pass\n            return\n        if False:\n            raise CgroupError(")'

proof "INV-003 vacuity — a package marker counts as coverage again" \
  tests/invariants/test_sandbox_reachability.py \
  "tests/invariants/test_sandbox_reachability.py::test_a_package_marker_does_not_count_as_coverage" \
  's = s.replace("    return [\n        p\n        for p in _sandbox_sources()\n        if p.name != \x22__init__.py\x22 and p.name not in NOT_SANDBOX_RESIDENT\n    ]", "    return _sandbox_sources()")'

proof "INV-003 root check — a moved root stops being noticed" \
  tests/invariants/test_sandbox_reachability.py \
  "tests/invariants/test_sandbox_reachability.py::test_every_declared_root_exists" \
  's = s.replace("    REPO / \x22src\x22 / \x22sandbox\x22,", "    REPO / \x22src\x22 / \x22sandbox_renamed_by_someone\x22,")'

# T-08's two mechanisms. Finding 006 measured both hazards on ADK; OD-15 dropped
# ADK, so the mitigations are ours and the measurement behind them is gone. Four
# proofs, and the pairing is deliberate: the first two separate *recording* order
# from *returned* order, because a dispatcher can get one right and the other
# wrong and the difference is which downstream consumer is corrupted.
proof "T-08 declared order — the journal records in completion order" \
  src/runtime/dispatch.py \
  "tests/invariants/test_fanout_ordering.py::test_recording_follows_declared_index_order_not_completion_order" \
  's = s.replace("            while next_to_record in done:\n                record(done[next_to_record])\n                next_to_record += 1", "            record(done[index])")'

proof "T-08 declared order — the returned results follow completion order" \
  src/runtime/dispatch.py \
  "tests/invariants/test_fanout_ordering.py::test_recording_follows_declared_index_order_not_completion_order" \
  's = s.replace("    results = tuple(done[index] for index in range(len(calls)))", "    results = tuple(done[index] for index in completion)")'

proof "T-08 no default rule — an undeclared shared key falls back to last-write-wins" \
  src/runtime/state_merge.py \
  "tests/invariants/test_fanout_ordering.py::test_an_undeclared_shared_key_is_refused_rather_than_defaulted" \
  's = s.replace("            raise UndeclaredMergeKey(", "            return MergeRule(name=\x22lww\x22, on_conflict=COMBINE, why=\x22\x22, combine=lambda v: v[-1], sample_a=1, sample_b=2)\n            raise UndeclaredMergeKey(")'

# This is the one that reproduces finding 006's measurement exactly: two branches
# write one key, one write is gone, nothing raises. The tamper needs both edits —
# with only the first, `_single_writer` still refuses and the test sees the
# permitted alternative rather than the forbidden one.
proof "T-08 no lost update — single_writer picks a winner instead of refusing" \
  src/runtime/state_merge.py \
  "tests/invariants/test_fanout_ordering.py::test_every_declared_merge_rule_either_combines_or_refuses" \
  's = s.replace("            if rule.on_conflict == REFUSE and len(writers) > 1 and rule is SINGLE_WRITER:", "            if False:"); s = s.replace("def _single_writer(values: Sequence[Any]) -> Any:\n    if len(values) != 1:", "def _single_writer(values: Sequence[Any]) -> Any:\n    return values[-1]\n    if len(values) != 1:")'

# T048/T050. The rollback is one line and its absence is invisible in every
# single-connection test, which is why it survived Phase 2: a refused insert
# raises `UniquenessError` either way, and the damage lands on a *different*
# connection five seconds later.
proof "T050 lock release — a refused insert keeps its transaction open" \
  src/contracts/repository.py \
  "tests/integration/test_store_concurrent_writers.py::test_a_refused_insert_does_not_wedge_another_connection" \
  's = s.replace("                self._rollback_if_outermost()\n                raise UniquenessError(f\x22{table}: {exc}\x22)", "                raise UniquenessError(f\x22{table}: {exc}\x22)")'

# T050/T016. The convergence loop is the whole repair for the first-open race.
# Removing it restores the reported defect exactly — the loser raises instead of
# noticing that the winner already did the work — and it is invisible in every
# multi-process arm, because the race only occurs on about two thirds of runs
# and no party count makes it certain. Only the planted arm catches this
# every time.
proof "T016 WAL convergence — a loser of the first-open race raises again" \
  src/contracts/repository.py \
  "tests/integration/test_store_concurrent_writers.py::test_a_first_open_that_loses_the_wal_race_converges_instead_of_raising" \
  's = s.replace("                if self._read_journal_mode() == \x22wal\x22:\n                    self.wal_entry = WAL_ENTRY_PEER\n                    return", "                if False:\n                    return")'

# T016. The forced read is one line and reads like a redundant query somebody
# could tidy away. Without it `PRAGMA journal_mode` answers from the pager's
# own cache and never looks at the file, so the convergence loop above spins
# until its window expires and then reports a busy store that is in fact
# already in WAL. Measured at 3.7 million consecutive stale reads over five
# seconds, so this is not a narrow window.
proof "T016 journal mode re-read — the pager's stale cache is trusted" \
  src/contracts/repository.py \
  "tests/integration/test_store_concurrent_writers.py::test_a_first_open_that_loses_the_wal_race_converges_instead_of_raising" \
  's = s.replace("        self._conn.execute(\x22SELECT count(*) FROM sqlite_master\x22).fetchone()\n", "")'

# T016. The busy/wedged split is what stops the convergence wait from masking a
# held write lock — the defect this same probe found the first time. Collapsing
# it leaves every arm green except the one that plants a real lock: the store
# still refuses, it just refuses with the wrong word, and "retrying is
# reasonable" is the wrong word about a lock nobody is going to release.
proof "T016 wedged/busy split — a held lock reports as momentary contention" \
  src/contracts/repository.py \
  "tests/integration/test_store_concurrent_writers.py::test_a_wedged_store_is_not_reported_as_transient" \
  's = s.replace("            if refused_in >= BUSY_TIMEOUT_S * _EXHAUSTED_FRACTION:", "            if False:")'

# T016. The translation itself, on the ordinary write surface rather than at
# construction. Every single-connection test passes with this gone, because an
# uncontended write never raises at all — which is exactly how the leak
# survived on five methods until a cross-process probe went looking.
proof "T016 engine translation — sqlite3.OperationalError reaches a caller again" \
  src/contracts/repository.py \
  "tests/integration/test_store_concurrent_writers.py::test_no_sqlite_exception_escapes_the_write_surface" \
  's = s.replace("        with self._lock, self._engine_errors(f\x22inserting into {table}\x22):", "        with self._lock:")'

# --- T016, the per-row scope the `session` migration required -----------------
#
# Six mechanisms, one decision. `session`'s scope columns travel on the row
# because FR-050 layer 1 resolves an opaque digest before the tenant is known.
# Each proof below removes exactly one of the six and is scored against the arm
# that is about it, because they fail in different directions: two of them let a
# caller off the scope entirely, two let the scope leak into the read that must
# not carry one, one loses FR-006's second-termination guard, and one silently
# writes rows nobody can attribute. The whole set is invisible in any test that
# only writes and reads a session row back.

# The direction that turns `unscoped` into a general escape hatch. Without this
# refusal, any caller that wanted no tenant predicate on any table could reach
# for `Repository.unscoped` and get rows with no scope at all — which is the
# opposite of what the constructor is for.
proof "T016 per-row scope — an unscoped handle reaches an ordinary table" \
  src/contracts/repository.py \
  "tests/invariants/test_writer_ownership.py::test_an_unscoped_repository_cannot_reach_an_ordinary_table" \
  's = s.replace("        if not per_row and self.tenant_id is None:", "        if False:")'

# The direction that fails silently, which is why it is a separate proof. A
# connection-scoped handle on `session` writes rows successfully, files them all
# under its own tenant, and makes `resolve` answer only for that tenant — so the
# enforcement point starts denying capabilities with nothing anywhere to
# attribute it to.
proof "T016 per-row scope — a connection-scoped handle reaches the session table" \
  src/contracts/repository.py \
  "tests/invariants/test_writer_ownership.py::test_a_scoped_repository_cannot_reach_the_per_row_table" \
  's = s.replace("        if per_row and self.tenant_id is not None:", "        if False:")'

# FR-035 is inverted here, not waived, and this line is the whole of the
# inversion's obligation half: the caller supplies the columns and the layer
# requires them. Removing it does not fail loudly — the row is refused by
# SQLite's NOT NULL instead, as a uniqueness-shaped error naming neither column.
proof "T016 per-row scope — a session row is admitted without its scope columns" \
  src/contracts/repository.py \
  "tests/invariants/test_writer_ownership.py::test_a_per_row_table_still_requires_both_scope_columns" \
  's = s.replace("            missing = [c for c in SCOPE_COLUMNS if not row.get(c)]\n            if missing:", "            missing = []\n            if False:")'

# The unique index. An ordinary table prefixes its unique groups with the scope
# columns so two tenants may hold one key; on this table that is unsound,
# because the read that has to tell them apart carries no tenant predicate and
# would find two rows for one capability digest.
proof "T016 per-row scope — the capability digest stops being globally unique" \
  src/contracts/repository.py \
  "tests/invariants/test_writer_ownership.py::test_a_per_row_unique_key_is_global_and_a_read_carries_no_tenant" \
  's = s.replace("        keyed = tuple(group) if per_row else (*SCOPE_COLUMNS, *group)", "        keyed = (*SCOPE_COLUMNS, *group)")'

# The read half of the same decision. With the predicate restored, `resolve`
# filters on a tenant the unscoped connection does not have — so every lookup
# returns nothing and FR-050 layer 1 denies every request it is handed.
proof "T016 per-row scope — the tenant predicate returns to the digest lookup" \
  src/contracts/repository.py \
  "tests/invariants/test_writer_ownership.py::test_a_per_row_unique_key_is_global_and_a_read_carries_no_tenant" \
  's = s.replace("        if not per_row:\n            clauses += [", "        if True:\n            clauses += [")'

# FR-006 via the only non-equality predicate this layer offers. Collapsed to
# equality, `terminate` matches on `state = \x22TERMINATED\x22` instead of on its
# complement: the first termination changes zero rows and a second one
# overwrites the recorded outcome. Both halves are wrong and each alone would
# defeat the guard.
proof "T016 NotEqual — the termination guard collapses to an equality" \
  src/contracts/repository.py \
  "tests/invariants/test_writer_ownership.py::test_not_equal_moves_only_the_rows_that_are_not_the_value" \
  's = s.replace("    operator = \x22<>\x22 if isinstance(value, NotEqual) else \x22=\x22", "    operator = \x22=\x22")'

# T050. The rendezvous is what makes the probe's children one-writer-per-process
# rather than hopefully-one-writer-per-process, and removing it is invisible in
# every arm: `Pool` reuses a worker only sometimes, so the measurements stay
# green and quietly run on fewer connections than they name. Deleting the wait
# is a two-character edit with no red test unless one is kept pointed at it.
proof "T050 writer rendezvous — children no longer wait to be one-per-process" \
  tests/integration/test_store_concurrent_writers.py \
  "tests/integration/test_store_concurrent_writers.py::test_the_rendezvous_refuses_a_pool_that_reuses_a_worker" \
  's = s.replace("        _BARRIER.wait(timeout=timeout)", "        pass")'

# T049. The guarded update is the whole mechanism and its return value was
# discarded before this task; the proof is that discarding it again is noticed.
proof "T049 guarded transition — a transition that matched nothing reports success" \
  src/runtime/session_state.py \
  "tests/unit/test_session_store.py::test_a_session_cannot_be_started_twice" \
  's = s.replace("        row = self.lifecycle.get(session_id)\n        if row is None:\n            raise SessionStateError(f\x22{session_id!r} has no session row\x22)", "        row = self.lifecycle.get(session_id)\n        if row is None:\n            raise SessionStateError(f\x22{session_id!r} has no session row\x22)\n        return StateTransition(session_id=session_id, from_state=row.state, to_state=to_state, terminal_state=terminal_state, deciding_rule=rule.rule_id, predicate_inputs=tuple(predicate_inputs), at=at)")'

# FR-006. The taxonomy check moved from `transition.py` alone to the row writer
# too, because the two are written by different paths and only one was guarded.
proof "FR-006 named terminal — the writer accepts any non-empty string again" \
  src/supervisor/session_table.py \
  "tests/integration/test_lease_revocation.py::test_terminate_requires_a_named_state" \
  's = s.replace("        terminal.require(terminal_state)", "        if not terminal_state:\n            raise ValueError(\x22terminate() requires a named terminal state\x22)")'

# FR-005. The ceiling and the total both have to come off disk on every call.
# Caching the ceiling on the store is the shape of finding 006's defect: the
# ceiling of 3 that permitted 6 was a number living on a rebuilt context.
proof "FR-005 ceiling reached — the comparison permits one over the declared number" \
  src/runtime/session_store.py \
  "tests/unit/test_session_store.py::test_a_ceiling_reached_exactly_is_reached" \
  's = s.replace("        breached = observed >= declared", "        breached = observed > declared")'

# FR-058. Five, one per obligation that has an independent failure mode. The
# byte-proxy one is the load-bearing one: FR-058 disqualifies an average
# bytes-per-token divisor by name, this repository has a 4.0 divisor in it, and
# the tamper is exactly the edit somebody makes reaching for it.
proof "FR-058 byte proxy — an average bytes-per-token divisor stands in for the floor" \
  src/runtime/result_bound.py \
  "tests/unit/test_result_bound.py::test_the_byte_proxy_never_uses_an_average_divisor" \
  's = s.replace("    return bound_tokens\n\n\n@dataclass(frozen=True)\nclass BoundFields:", "    return bound_tokens * 4\n\n\n@dataclass(frozen=True)\nclass BoundFields:")'

proof "FR-058 ceiling — a bound above one twentieth is clamped instead of refused" \
  src/runtime/result_bound.py \
  "tests/unit/test_result_bound.py::test_a_bound_above_one_twentieth_of_the_window_is_refused_not_clamped" \
  's = s.replace("        if self.bound_tokens > ceiling:\n            raise BoundConfigError(", "        if False:\n            raise BoundConfigError(")'

proof "FR-058 disclosure — the notice is dropped from the result the model reads" \
  src/runtime/result_bound.py \
  "tests/unit/test_result_bound.py::test_the_bounded_result_discloses_its_own_bounding" \
  's = s.replace("    return (\n        f\x22[bounded result", "    return \x22\x22\n    return (\n        f\x22[bounded result")'

proof "FR-058 trace fields — written only where the bound bit" \
  src/runtime/trace.py \
  "tests/unit/test_result_bound.py::test_a_tool_call_span_without_the_seven_fields_is_refused" \
  's = s.replace("        if self.kind == TOOL_CALL and self.result_bound is None:", "        if False:")'

proof "FR-058 retention — the withheld bytes outlive the session" \
  src/runtime/result_bound.py \
  "tests/unit/test_result_bound.py::test_retention_does_not_outlive_the_session" \
  's = s.replace("        shutil.rmtree(self.directory, ignore_errors=True)\n        self._discarded = True", "        self._discarded = True")'

proof "FR-058 retention bound — the location accepts bytes past its declared bound" \
  src/runtime/result_bound.py \
  "tests/unit/test_result_bound.py::test_the_retention_location_carries_its_own_declared_bound" \
  's = s.replace("        if self.bytes_held + len(payload) > self.max_bytes:", "        if False:")'

# T041. The three load-bearing lines of the loop, one proof each. The turn-index
# one is finding 006's measurement in miniature: the number a ceiling reads has
# to come off the journal, and `len(turns)` is this attempt's count.
#
# **Retargeted twice by T052, and both moves are load-bearing.** The site moved:
# the index now comes from `journal.next_turn_index` rather than from the budget
# totals, because the ledger deliberately over-counts (T053) and is therefore the
# wrong authority for a position. And the *arm* moved, because
# `test_turn_indexes_continue_across_attempts` stopped being able to tell the two
# apart: resume reconstruction seeds `turns` with the completed records, so on a
# clean resume `len(turns)` and the journalled count coincide and the tamper is
# vacuous. The arm below is a journal where they provably differ — turn 0
# complete, turn 1 intended and abandoned — so `len(turns)` is 1 where the
# journal says 2. Under the tamper the loop re-issues turn 1's index and T051's
# unique key refuses it; the failure is the collision the old arm's docstring
# predicted, not an accident.
proof "T041 turn index — the loop numbers turns from this attempt rather than the journal" \
  src/runtime/loop.py \
  "tests/unit/test_loop.py::test_an_abandoned_turns_index_is_never_handed_back_out" \
  's = s.replace("                turn_index = self.journal.next_turn_index(self.session_id)", "                turn_index = len(turns)")'

# T051. The write-ahead half. **A reordering, not a deletion**: the intent still
# gets written, just after the call it was supposed to precede. Deleting it would
# make `commit_outcome` refuse for want of an intent and every turn-taking test in
# the suite fail, which is the vacuous shape — a proof whose tamper breaks the
# module cannot distinguish "write-ahead was load-bearing" from "the file no
# longer works". Reordered, every path that does not crash is unaffected: the
# table ends up holding both rows either way. The arm reads the journal from
# *inside* the model call, which is the only moment the difference exists.
proof "T051 write-ahead — the intent is committed after the effect instead of before" \
  src/runtime/loop.py \
  "tests/unit/test_loop.py::test_every_step_is_journalled_before_it_happens" \
  'intent = "        self.journal.intend(\n            session_id=self.session_id, turn_index=turn_index,\n            step_index=MODEL_STEP_INDEX, step_kind=STEP_MODEL_CALL,\n            effect_id=\x22model\x22, effectful=True,\n            payload={\x22turns_in_context\x22: len(turns),\n                     \x22dropped_turns\x22: context.dropped_turns},\n            at=self.clock())\n"; s = s.replace(intent, ""); s = s.replace("        response = self.model(context)\n", "        response = self.model(context)\n" + intent)'

# T051, the other end of the same key. **Not a second reading of the proof
# above**: that one is about *when* the intent is written, this one is about
# whether recording an outcome twice is refused. Two mechanisms, and the guard
# under proof is the store's unique index rather than any check in Python —
# which is why the tamper removes the index declaration and not a branch.
proof "T051 no repeated outcome — a step's outcome can be recorded twice" \
  src/runtime/journal.py \
  "tests/contract/test_turn_journal.py::test_the_same_outcome_cannot_be_committed_twice" \
  's = s.replace("        }, unique=[[\x22session_id\x22, \x22turn_index\x22, \x22step_index\x22, \x22kind\x22]])", "        })")'

# T052. The granularity. A resume that hands back a step whose outcome is already
# on disk is FR-007'"'"'s repeat, and the tamper is the natural simplification —
# treat the whole turn as pending rather than checking each step. The arm counts
# what `execute` was called with, because the reconstructed record looks
# identical either way: the second run produces a body too.
proof "T052 step granularity — a recorded tool result is re-executed on resume" \
  src/runtime/resume.py \
  "tests/unit/test_loop.py::test_a_recorded_tool_result_is_not_re_executed_on_resume" \
  's = s.replace("            if step is not None and step.is_complete:", "            if False:")'

# T052, the turn level — finding 006'"'"'s 4 of 4. Dropping the completed records
# means the loop starts with an empty transcript and re-calls the provider for
# every turn that already happened. A separate mechanism from the step check
# above: one decides which turns come back, the other which steps inside a turn
# are outstanding, and neither covers the other.
proof "T052 completed turns — a resumed attempt re-executes the turns it already ran" \
  src/runtime/loop.py \
  "tests/unit/test_loop.py::test_a_completed_inner_turn_is_not_re_executed" \
  's = s.replace("        turns: list[TurnRecord] = list(plan.records)", "        turns: list[TurnRecord] = []")'

# T053. **U-30 in one line.** Reserving after the call is the same as not
# reserving, and it is what the loop did before this task. The arm samples the
# totals from inside the provider call, because that is the only moment a
# reservation is distinguishable from an accrual — afterwards both have recorded
# the measurement and the table looks the same.
proof "T053 reserve before the call — the spend is only counted once it returns" \
  src/runtime/loop.py \
  "tests/unit/test_loop.py::test_the_reservation_counts_the_call_in_flight" \
  's = s.replace("        reservation = self.budget.reserve(\n            self.session_id, turn=turn_index, at=self.clock())\n        call_started = self.clock()\n        response = self.model(context)", "        call_started = self.clock()\n        response = self.model(context)\n        reservation = self.budget.reserve(\n            self.session_id, turn=turn_index, at=self.clock())")'


# T053, the durability half. An outstanding reservation has to keep counting, and
# the tamper is the plausible reading of "reconcile replaces the estimate" —
# count only what was committed. Distinct from the proof above: that one is about
# *when* the reservation is made, this one about whether it is counted at all
# once made. The arm is the crash-shaped one, where no reconcile ever happens.
proof "T053 outstanding reservations — the totals ignore the call in flight" \
  src/runtime/ledger.py \
  "tests/contract/test_budget_ledger.py::test_an_unreconciled_reservation_keeps_counting" \
  's = s.replace("        committed = self.journal.totals(session_id)\n        held = self.outstanding(session_id)", "        committed = self.journal.totals(session_id)\n        held = ()")'

# T054. **The one proof in this file that no single-process test can carry.** Every
# other arm below is detected by something in tests/unit or tests/contract as well;
# this tamper is detected by the SIGKILL battery and by nothing else — 564 unit and
# contract tests pass with it applied. The reason is structural: within one attempt a
# tool call is intended exactly once, so `intend` and `intend_once` are
# indistinguishable, and the difference only exists for a process that resumed a turn
# whose intent is already on disk.
#
# It is also the defect a real crash found rather than review. The first run of the
# mid-step arm resumed a turn holding an unrecorded tool intent and the *resume*
# raised, which is a worse failure than the repeat the arm was written to catch.
proof "T054 resumed intent — the retry path re-intends a step that already has one" \
  src/runtime/loop.py \
  "tests/integration/test_resume_sigkill.py::test_a_mid_step_crash_re_executes_no_recorded_step" \
  's = s.replace("        self.journal.intend_once(**self._call_intent(turn_index, call))", "        self.journal.intend(**self._call_intent(turn_index, call))")'

# T055 deliberately carries **no** proof, and this note is here so the next reader
# does not re-derive the search. Its subject is an emergent property — a total that
# never goes backwards across three crashes — and every line that property rests on
# is already detected by something cheaper: the totals living on disk by the two T053
# proofs, the ceilings being recorded by T048's, the turn positions by T041's. The
# two mechanisms it *would* uniquely cover cannot be reached: `reconcile`'s atomicity
# needs a crash between the release and the measurement, and there is no pause point
# inside a single transaction to hang one on. A proof targeting the battery for a
# mechanism another test already refuses would report the battery as load-bearing on
# evidence that belongs to the other test.

# T064, the model call'"'"'s interval. FR-005'"'"'s fourth ceiling had no numerator
# until this pass: finding 029 measured a session run 2.044s against a ceiling of
# 0.001s completing, with `ledger_total_wall_clock_seconds: 0.0`. The tamper is
# that state exactly, and it is not a strawman — the literal `0.0` it restores is
# the text this argument replaced. Nothing about the ceiling machinery changes
# under it, which is the finding'"'"'s point: the comparison still runs, and still
# compares against nothing.
proof "T064 measured call time — the duration of the model call reconciles as zero" \
  src/runtime/loop.py \
  "tests/unit/test_loop.py::test_the_elapsed_time_a_turn_took_is_accrued_to_the_ledger" \
  's = s.replace("            wall_clock_seconds=_interval(call_started, call_finished),", "            wall_clock_seconds=0.0,")'

# T064, the rest of the turn. A second mechanism, not a second reading: the call
# is measured on `reconcile`, everything after it — tool execution, journal
# writes, context assembly — by the accrual at the end. Either alone leaves the
# dimension under-counting, so a single proof over both could not say which was
# load-bearing.
#
# The tamper is a **narrowing**, and the narrowest available: the interval keeps
# being measured and accrued, from a mark taken one line later. That is the
# plausible defect (a mark at the wrong end), it leaves every other property of
# the row intact, and it makes the arm report on the mark rather than on whether
# the file still imports.
proof "T064 the turn tail — the interval after the call is measured from its end" \
  src/runtime/loop.py \
  "tests/unit/test_loop.py::test_the_wall_clock_ceiling_stops_a_session_that_ran_too_long" \
  's = s.replace("        self._accrue_elapsed(turn_index, since=call_finished)", "        self._accrue_elapsed(turn_index, since=self.clock())")'

# T064 on the resume path, and **this one no single-process test can carry**. A
# turn whose model call is already on disk re-enters at `_finish_turn`, and the
# interval that turn'"'"'s tools take is the only wall clock it will ever accrue.
# Within one attempt the mark is redundant with the one above, so nothing in a
# live process can tell: 645 unit and contract tests pass with this tamper
# applied, the sole exception being `test_tamper_matching`, which reports that
# the source moved and is therefore reading the tamper rather than its effect.
# It is detected by the SIGKILL battery, whose third turn is the one that
# resumed. Same narrowing shape as the arm above, and for the same reason.
proof "T064 resumed turns — a turn finished after a crash accrues no wall clock" \
  src/runtime/loop.py \
  "tests/batteries/test_ceilings_under_resume.py::test_the_permitted_turn_count_is_a_real_bound" \
  's = s.replace("        self._accrue_elapsed(turn_index, since=resumed_at)", "        self._accrue_elapsed(turn_index, since=self.clock())")'

# T064. The accrual row is one dimension'"'"'s measurement and nothing else. Setting
# `turns=1` is what a reader who thinks of a ledger row as "a turn happened"
# would write, and it double-counts every turn against a ceiling FR-005 requires
# be exact — the reservation already carried it. The arm asserts the turn total
# rather than a terminal state, so it reports the count and not a consequence of
# the count.
proof "T064 one dimension only — the elapsed-time row counts a turn of its own" \
  src/runtime/loop.py \
  "tests/unit/test_loop.py::test_a_ceiling_is_not_restarted_by_a_second_loop_over_the_same_session" \
  's = s.replace("            turns=0,\n            at=now,", "            turns=1,\n            at=now,")'

# T064 / FR-005'"'"'s refusal of unstated figures. The tamper restores the default
# this pass removed — `wall_clock_seconds: float = 0.0` — which is the state
# finding 029 §4 measured: a deployment that never mentioned the dimension wrote
# nothing to it on any path, and nothing said so. It is a *narrowing* of the
# refusal rather than a deletion of the field, so `ReservationPolicy` still
# constructs and every other test in the suite still passes.
proof "T064 no invented estimate — an unstated wall-clock reservation defaults to zero" \
  src/runtime/ledger.py \
  "tests/contract/test_budget_ledger.py::test_every_estimated_figure_is_refused_when_it_is_omitted" \
  's = s.replace("    wall_clock_seconds: float\n    turns: int = 1", "    wall_clock_seconds: float = 0.0\n    turns: int = 1")'

# T056. FR-037 **across a crash**, which is a different mechanism from FR-037
# within one attempt: the state a resumed process injects came out of the journal
# rather than out of the response object still in memory. The tamper is confined
# to the decode path, so nothing on the non-resume path changes — which is the
# point. A run that never crashes cannot tell whether this line is there.
proof "T056 state across resume — a resumed turn is handed no provider state" \
  src/runtime/resume.py \
  "tests/conformance/test_provider_state_resume.py::test_the_state_a_killed_process_recorded_is_injected_by_the_next_one" \
  's = s.replace("            provider_state=step.provider_state,", "            provider_state=None,")'

# T056, the other end of the same round trip: the *column*. The tamper above
# stops the decode reading it; this one stops the commit writing it. Two
# mechanisms, and either one alone is enough to lose the state — so a single
# proof covering both would be the doubly-covered shape, unable to say which was
# load-bearing. The arm reads the table directly rather than through the loop,
# because a live attempt never consults the column it just wrote.
proof "T056 state on disk — a committed model outcome stores no provider state" \
  src/runtime/loop.py \
  "tests/conformance/test_provider_state_resume.py::test_a_half_finished_turns_state_comes_off_disk_and_not_from_the_provider" \
  's = s.replace("            provider_state=response.provider_state, at=self.clock())", "            provider_state=None, at=self.clock())")'

# T056. The nullable column. Collapsing `None` into `b\"\"` reports a fact the
# provider did not state — an *empty* state where it returned *no* state — and
# every byte-equality assertion in the suite still passes, because the sessions
# that matter never produce both in one run. `or b\"\"` is the natural version of
# this defect, which is why the tamper is written that way rather than as a
# deletion.
proof "T056 absent is not empty — no state and empty state are stored the same" \
  src/runtime/journal.py \
  "tests/conformance/test_provider_state_resume.py::test_no_state_and_empty_state_stay_distinguishable_across_the_boundary" \
  's = s.replace("                \"provider_state\": (None if provider_state is None\n                                   else bytes(provider_state)),", "                \"provider_state\": bytes(provider_state or b\"\"),")'

# T056. FR-037'"'"'s third clause — never logged *readably*. The span carries a
# digest, and the tamper replaces it with the bytes, which is the change somebody
# debugging a state mismatch would make on purpose. Nothing else in the suite
# notices: the detail dict is still populated, still JSON, still the right shape.
proof "T056 digest not bytes — the opaque state is written to the trace readably" \
  src/runtime/loop.py \
  "tests/conformance/test_provider_state_resume.py::test_the_opaque_bytes_are_never_readable_on_the_trace_or_in_the_payload" \
  's = s.replace("                \"provider_state_digest\": state_digest(response.provider_state),", "                \"provider_state_digest\": (response.provider_state or b\"\").hex(),")'

# FR-037 and T-02. The opaque state is round-tripped; a loop that drops it still
# produces plausible answers, which is why the arm asserts the bytes.
proof "T041 opaque state — the provider state is not carried into the next turn" \
  src/runtime/context.py \
  "tests/unit/test_loop.py::test_provider_state_is_reinjected_verbatim" \
  's = s.replace("        kept.append(turn.provider_state)", "        kept.append(None)")'

# FR-037, *never dropped*. The state this plants is the one the code actually
# shipped with until 2026-08-05: the newest turn's, and nothing before it. Every
# turn still gets a state, the round-trip of that state is still byte-exact, and
# the chain still answers correctly — finding 016 measured the last of those. The
# arm that sees it compares what the request carries against what every earlier
# turn produced.
proof "T041 opaque state — only the newest turn's state is carried forward" \
  src/runtime/context.py \
  "tests/conformance/test_provider_state_roundtrip.py::test_the_opaque_field_survives_the_chain_byte_identically" \
  's = s.replace("    kept.reverse()\n    return tuple(kept)", "    kept.reverse()\n    return tuple(kept[-1:])")'

# T042. Trimming the task to fit is the silent failure: the agent answers a
# question nobody asked and every size assertion still passes.
proof "T042 prompt refusal — an over-budget prompt is trimmed instead of refused" \
  src/runtime/context.py \
  "tests/unit/test_context.py::test_a_prompt_that_alone_exceeds_the_budget_is_refused_not_trimmed" \
  's = s.replace("        if head_tokens > self.budget_tokens:\n            raise ContextError(", "        if False:\n            raise ContextError(")'

# T046. Teardown on the unplanned path. Without the `finally` the session is left
# RUNNING with a live lease on the first unhandled exception, and the enforcement
# point keeps honouring a capability whose owner is gone.
proof "T046 teardown — the session is stood down only on the paths that returned" \
  src/runtime/runner.py \
  "tests/unit/test_runner.py::test_a_fault_in_the_loop_still_stands_the_session_down" \
  's = s.replace("        finally:\n            recorded = self._stand_down(loop, session_id, outcome)", "        finally:\n            if outcome is not None:\n                recorded = self._stand_down(loop, session_id, outcome)")'

# T047. Cancellation terminates. The tamper restores the routing this file
# carried until 2026-08-05 — interrupt on cancellation — and the arm is the
# defect that routing had: `STATE_INTERRUPTED` is FR-007's resume state, so
# `attach()` resumed a cancelled session automatically. The arm therefore reads
# the *consequence* rather than the state string: a proof asserting
# `to_state == "TERMINATED"` would be satisfied by any terminal state, and what
# matters is that no edge leads out of the one chosen.
proof "T047 cancellation — a cancelled run is interrupted, so attach resumes it" \
  src/runtime/runner.py \
  "tests/unit/test_cancellation.py::test_a_cancelled_session_cannot_be_attached_to" \
  's = s.replace("                transition = self.machine.terminate(\n                    session_id,\n                    terminal_state=terminal.OPERATOR_TERMINATED.name,\n                    at=self.clock())\n                recorded = EndOfRun(session_id=session_id,\n                                    reason=REASON_CANCELLED, at=transition.at)", "                transition = self.machine.interrupt(session_id, at=self.clock())")'

# T047, the caller-visible half — a second mechanism, not a second reading of the
# one above. Routing cancellation to `terminate()` moves the row; carrying the
# recorded marker back out of teardown is what makes the caller agree with it.
# The tamper leaves the row correct and reports the loop's `None`, which is the
# divergence a reviewer would otherwise have to take on trust.
#
# **The site moved with T066 and the tamper moved with it.** The two fields the
# caller reads — the terminal name and the end-of-run marker — are now resolved
# from one variable rather than separately, so dropping the teardown's
# contribution is one edit instead of two. That is a narrower tamper than the
# one it replaces, not a wider one: it falsifies the same single fact.
proof "T047 cancellation — the terminal state teardown recorded is not reported" \
  src/runtime/runner.py \
  "tests/unit/test_cancellation.py::test_a_cancelled_run_names_operator_terminated_as_its_terminal_state" \
  's = s.replace("        marker = outcome.end_of_run if outcome.end_of_run is not None else recorded", "        marker = outcome.end_of_run")'

# T066. The two raw signals whose *content* is the whole point of them, proved
# separately because one tamper covering both would not say which was missing.
#
# The first is the identity. `terminated.unrecoverable_fault` is FR-006's name
# for a fault the runtime cannot classify further, and before T066 that was
# **all** a reader got — the exception's type and message went out with the
# traceback. The tamper keeps a marker, keeps a fault, and replaces the identity
# with a constant, so only the arm that reads the type moves. A tamper that
# removed the field would instead trip `EndOfRun`'s own pairing check and fail
# every fault path for a reason that is not this one.
proof "T066 error identity — the fault marker names a constant, not the exception" \
  src/runtime/runner.py \
  "tests/unit/test_runner.py::test_a_faulted_run_records_which_exception_ended_it" \
  's = s.replace("                    error=ErrorIdentity.from_exception(\n                        raised if raised is not None\n                        else RuntimeError(\n                            \"the loop returned no outcome and raised nothing\")),", "                    error=ErrorIdentity(\"Exception\", \"a fault\"),")'

# The second is the marker reaching the durable record at all. `LoopOutcome` and
# `RunOutcome` refuse a terminal state without one, so the *return value* is
# guarded structurally; the **span** is not, and a caller-visible marker that
# never lands on the trace leaves an operator reading the record exactly where
# finding 006 found them. Declared against the ceiling arm rather than the fault
# arm so this proof and the one above have different targets.
proof "T066 end-of-run marker — the signal never reaches the trace" \
  src/runtime/loop.py \
  "tests/unit/test_runner.py::test_a_ceiling_termination_records_which_ceiling_and_on_what_reading" \
  's = s.replace("            detail=({} if end_of_run is None\n                    else {\"end_of_run\": end_of_run.to_record()}),", "            detail={},")'

# T067. Three mechanisms, three different failures if removed.
#
# The predicate consulted at all. Without it a repeating agent still stops —
# T065's backstop catches it at twenty calls, or the turn ceiling does — which
# is why the arm reads the *name* rather than the fact of stopping. FR-006's
# complaint about an unset threshold is precisely that the session ends under
# the wrong name, and this tamper is that complaint made concrete.
proof "T067 stall predicate — the loop never consults it" \
  src/runtime/loop.py \
  "tests/unit/test_progress.py::test_a_repeating_agent_ends_in_no_progress_and_not_at_the_turn_ceiling" \
  's = s.replace("            stall = evaluate_stall(turns, self.stall)\n            if stall.stalled:", "            stall = evaluate_stall(turns, self.stall)\n            if False:")'

# The count derived from the journal rather than held per attempt. This is the
# property the predicate was written as a pure function of the records in order
# to have: FR-007 resumes in a new process, and a per-process count resets at
# every crash, so an agent that stalls, crashes and goes on stalling never
# terminates. The tamper narrows the input to the turns this attempt appended,
# which is what a counter on the loop object would see.
proof "T067 stall count — the predicate sees only this process's turns" \
  src/runtime/loop.py \
  "tests/unit/test_progress.py::test_the_count_carries_across_an_attempt_boundary" \
  's = s.replace("            stall = evaluate_stall(turns, self.stall)", "            stall = evaluate_stall(list(turns)[len(plan.records):], self.stall)")'

# The refusal that keeps the reading on the record. `terminated.no_progress`
# without its two figures says only that a threshold nobody can see was crossed,
# and the bare `terminate()` is the route that would drop them.
proof "T067 stall readings — the bare terminate() accepts the member" \
  src/runtime/session_state.py \
  "tests/unit/test_progress.py::test_the_bare_terminate_refuses_this_member" \
  's = s.replace("_NEEDS_READINGS = {ST_CEILING_REACHED, ST_NO_PROGRESS}", "_NEEDS_READINGS = {ST_CEILING_REACHED}")'

# T068. The routing, which is the defect the distinguishability rests on rather
# than a property of it. Cancellation took FR-007's interrupt edge until
# `e2e2311`, and the consequence was not a wrong string — a cancelled session
# stayed resumable and the next attach silently continued a run the consumer had
# ended. The arm reads the row and then tries the attach, so it fails on the
# consequence and not only on the name.
proof "T068 cancellation routing — a cancelled run is left resumable" \
  src/runtime/runner.py \
  "tests/unit/test_terminal_distinguishable.py::test_the_cancelled_session_is_not_left_resumable" \
  's = s.replace("                transition = self.machine.terminate(\n                    session_id,\n                    terminal_state=terminal.OPERATOR_TERMINATED.name,\n                    at=self.clock())\n                recorded = EndOfRun(session_id=session_id,\n                                    reason=REASON_CANCELLED, at=transition.at)", "                transition = self.machine.interrupt(session_id, at=self.clock())")'

# T046. **Not a proof of the terminated refusal.** That guard was tried here and
# the tamper was vacuous: removing it drops the caller through to the "no edge
# out of {state}" branch, which is also a RunnerError also naming TERMINATED, so
# the arm passed on the fallback. Two guards, one property — and a proof that
# cannot tell them apart proves neither. The resume edge is the mechanism with a
# single site, so it is the one under proof.
proof "T046 attach — the resume edge is not taken and the loop runs unauthorised" \
  src/runtime/runner.py \
  "tests/unit/test_runner.py::test_attach_resumes_an_interrupted_session_and_keeps_its_ceilings" \
  's = s.replace("        if row.state == STATE_INTERRUPTED:\n            transition = self.machine.resume(", "        if False:\n            transition = self.machine.resume(")'

# ---------------------------------------------------------------------------
# Capability 5 — the provider layer (T057-T061).
#
# Nine of the eleven below are **narrowings**, not deletions, and that is
# deliberate: a tamper that breaks the module makes every test in it fail, which
# reads as "the mechanism was load-bearing" and cannot distinguish that from
# "the file no longer works". Each of these leaves the module importable and the
# other arms green.

# T059. The framing. A carrier that separated values instead of length-prefixing
# them loses any payload containing the separator, and Google'"'"'s payloads are
# arbitrary bytes. The tamper is the realistic version of that defect rather than
# the reframing itself: a strip of what looks like padding. It leaves the frame
# boundaries correct and only the value wrong, so nothing structural notices —
# and every arm whose payload is base64 still passes.
proof "T059 opaque framing — a trailing NUL is stripped off a payload as padding" \
  src/runtime/providers/state.py \
  "tests/unit/test_provider_state.py::test_a_payload_containing_a_nul_survives_the_round_trip" \
  's = s.replace("        value = bytes(view[at:at + value_len])", "        value = bytes(view[at:at + value_len]).rstrip(b\"\\x00\")")'

# T059. The one bit that says which carrier the provider used. Dropping the text
# branch re-injects Anthropic'"'"'s signature as bytes into a field the SDK
# serializes as a string. The *digest* is unchanged either way, so no
# byte-identity assertion on our side of the wire can see it.
proof "T059 carrier type — a text field is re-injected as bytes" \
  src/runtime/providers/state.py \
  "tests/unit/test_provider_state.py::test_a_text_carrier_comes_back_as_text_and_a_binary_one_as_bytes" \
  's = s.replace("        return self.value.decode(_TEXT_CODEC) if self.text else bytes(self.value)", "        return bytes(self.value)")'

# T059 and T-02. Keyed by provider, never merged. Without the check a blob from
# one provider unpacks cleanly for another — the frames are ours, so nothing in
# the format objects — and the failure downstream is a silently degraded turn
# rather than an error the provider raises.
proof "T059 provider keying — one provider's opaque state unpacks for another" \
  src/runtime/providers/state.py \
  "tests/unit/test_provider_state.py::test_one_providers_state_cannot_be_unpacked_by_another" \
  's = s.replace("    if recorded != provider:\n        raise ProviderMismatchError(", "    if False:\n        raise ProviderMismatchError(")'

# T059 and FR-037'"'"'s third clause — never logged readably. The tamper is the
# change somebody debugging a state mismatch makes on purpose, and it discloses
# the payload on every traceback and every debugger frame thereafter. Nothing
# else in the suite reads a repr.
proof "T059 repr — the opaque payload is disclosed by its own repr" \
  src/runtime/providers/state.py \
  "tests/unit/test_provider_state.py::test_the_payload_is_not_in_the_repr_or_the_str" \
  's = s.replace("            f\"value=<{len(self.value)} opaque bytes>, text={self.text})\"", "            f\"value={self.value!r}, text={self.text})\"")'

# T059 and T061. **The ADK defect itself**, planted. The counter still increments
# so the loud guard never fires; the write simply does not happen. The request is
# still well-formed, the provider still accepts it, the chain still runs and the
# answer is still 149.99 — finding 016 measured all of that. Only the byte
# comparison sees it.
proof "T061 re-injection — the opaque state is counted as written and written nowhere" \
  src/runtime/providers/state.py \
  "tests/conformance/test_provider_state_roundtrip.py::test_the_opaque_field_survives_the_chain_byte_identically" \
  's = s.replace("            1 for slot in slots\n            if write_path(target, slot.path, slot.carrier())", "            1 for slot in slots\n            if True or write_path(target, slot.path, slot.carrier())")'

# T059 and T061. Each state onto the entry it came off, rather than all of them
# onto the newest. This is the shape the code had until 2026-08-05, and on
# Anthropic it put a `signature` key on a `tool_use` block — well-formed JSON the
# provider signed for a different message.
proof "T061 re-injection — every state is written onto the newest assistant entry" \
  src/runtime/providers/state.py \
  "tests/unit/test_provider_state.py::test_a_turn_that_emitted_nothing_keeps_its_slot_and_gets_no_write" \
  's = s.replace("    for target, blob in zip(targets, carried):", "    for target, blob in ((targets[-1], b) for b in carried):")'

# T059 and T061. The alignment check. Zipping short is silent: `zip` stops at the
# shorter of the two and every state it did place is byte-exact, so the digest
# arms all pass while each one sits on the wrong message.
proof "T061 re-injection — a chain that does not line up is zipped short instead of refused" \
  src/runtime/providers/state.py \
  "tests/unit/test_provider_state.py::test_a_chain_that_does_not_line_up_with_the_conversation_is_refused" \
  's = s.replace("    if len(targets) != len(carried):", "    if False:")'

# T061. The vacuity guard, and it is the proof this capability most needs. Every
# byte-identity assertion above it is satisfied by a run in which the field never
# appeared: there is nothing to compare and nothing to fabricate. Without this
# line the silent cassette produces a green fixture that tested nothing, and the
# arm that catches it is the one asserting the refusal.
proof "T061 vacuity guard — a conditional over an empty population reports a pass" \
  tests/conformance/test_provider_state_roundtrip.py \
  "tests/conformance/test_provider_state_roundtrip.py::test_the_vacuity_guard_refuses_a_cassette_that_never_carries_state" \
  's = s.replace("    assert report.present_turns, (", "    assert True, (")'

# T057. The argument asymmetry, on one of the two providers that send a JSON
# string. Skipping the parse hands the tool a mapping whose single key is
# `arguments` and whose value is the whole JSON text, so the tool reports a
# missing argument and the model retries — a translation fault wearing a model
# failure'"'"'s clothes.
proof "T057 argument codec — OpenAI's JSON-string arguments are forwarded unparsed" \
  src/runtime/providers/schema.py \
  "tests/unit/test_provider_schema.py::test_arguments_reach_the_tool_as_a_mapping_whatever_the_wire_said" \
  's = s.replace("        parsed = json.loads(raw)", "        parsed = {\"arguments\": raw}")'

# T057. Google matches a function response by **name**, so two calls to one name
# in a turn are indistinguishable to the provider. Pairing them by position looks
# right locally and attributes one call'"'"'s result to the other'"'"'s; the
# model then answers confidently from the wrong row, which no assertion on the
# answer'"'"'s shape can catch.
proof "T057 Google ambiguity — two calls to one tool name are paired by position" \
  src/runtime/providers/schema.py \
  "tests/unit/test_provider_schema.py::test_two_google_calls_to_one_name_are_refused_rather_than_paired" \
  's = s.replace("            if seen:\n                raise GoogleAmbiguousCallError(", "            if False:\n                raise GoogleAmbiguousCallError(")'

# T058 and finding 016 result 9. The per-model branch inside one vendor. Without
# it `claude-sonnet-5` is sent the request shape that model answers with HTTP
# 400, and the failure arrives at the operator as a provider outage rather than
# as a translation fault of ours.
proof "T058 per-model branch — one request shape is sent to every Anthropic model" \
  src/runtime/providers/wire_anthropic.py \
  "tests/unit/test_provider_schema.py::test_the_anthropic_request_shape_branches_on_the_model_and_not_the_vendor" \
  's = s.replace("        adaptive = model in ADAPTIVE_MODELS", "        adaptive = False")'

# T060. The player'"'"'s only precondition on the request. Without it replay is
# purely ordinal: a driver that dropped an assistant entry is handed exactly the
# response it would have been handed anyway, and the recorded answer becomes an
# answer to a question the driver did not ask.
proof "T060 replay precondition — a request with a turn missing is answered anyway" \
  tests/conformance/cassettes/harness.py \
  "tests/unit/test_cassette_harness.py::test_a_conversation_of_the_wrong_length_is_refused" \
  's = s.replace("        if conversation_length != interaction.request_turns:", "        if False:")'

# T060. The quietest failure a cassette harness has: a fixture that consumed the
# first interaction, passed, and reported a six-turn chain. The tamper leaves the
# method present and returning cleanly, which is what the degraded version of it
# would look like.
proof "T060 exhaustion — a run that played one of six turns reports no news" \
  tests/conformance/cassettes/harness.py \
  "tests/unit/test_cassette_harness.py::test_a_player_that_served_some_turns_reports_the_rest" \
  's = s.replace("        missing = sorted(\n            set(range(len(self.cassette.interactions))) - self._served)", "        missing = []")'

# ---------------------------------------------------------------------------
# T062, T063 and T065 — the cost table, its refusal, and the backstop that does
# not read it.
#
# The independence claim of T065 is the one thing in this group that cannot be
# scored by this harness, and the reason is structural rather than an omission:
# the claim is *"the backstop still fires with the cost table gone"*, which is a
# test that must still PASS under a tamper, and every arm here is scored on a
# test FAILING. It is planted and run instead, in-process, by
# `test_the_backstop_fires_with_the_cost_table_emptied` — which empties `PRICES`
# and makes `price_usd` raise on everything before asserting the backstop is
# unmoved. What IS scored below is the guard that keeps it that way.

# T063, and rule 3 of the house methodology in one line. A prefix match is the
# degradation a contributor reaches for the first time an operator configures a
# dated variant of an id the table holds — and it turns the accepting set into
# its complement: `claude-sonnet` is then priced as whichever member of the
# family sorted first, at a rate nobody chose, for a model nobody priced.
proof "T063 fail-closed lookup — a family prefix is priced as one of its members" \
  src/runtime/providers/costs.py \
  "tests/unit/test_provider_costs.py::test_a_family_prefix_is_not_priced_as_one_of_its_members" \
  's = s.replace("    entries = PRICES.get((provider, model))", "    entries = next((v for (p, m), v in PRICES.items() if p == provider and m.startswith(model)), None)")'

# T062. The address guard on an entry. Without it `source=\"the vendor pricing
# page\"` is accepted, which is the exact shape a price recalled from memory
# takes: it reads as a citation and there is nothing to open. FR-005 forbids a
# ceiling filled from an invented default, and a fabricated conversion rate is
# that failure one level down from the ceiling itself.
proof "T062 sourced entries — a citation nobody can open is accepted" \
  src/runtime/providers/costs.py \
  "tests/unit/test_provider_costs.py::test_an_entry_whose_source_is_prose_rather_than_an_address_is_refused" \
  's = s.replace("            if not value.startswith(\"https://\"):", "            if False:")'

# T063 on the date rather than on the model. Falling back to the nearest
# interval is the plausible edit and it is unsound in a way no assertion on the
# figure can catch: it prices a call at a rate that was not in force, and
# because a scheduled change can go either way the direction of the error is
# unknowable. The named test is the only arm that separates this from the
# in-force lookup, which the tamper leaves working.
proof "T063 date window — a date no entry covers is priced from the nearest one" \
  src/runtime/providers/costs.py \
  "tests/unit/test_provider_costs.py::test_a_date_no_entry_covers_fails_closed_rather_than_picking_the_nearest" \
  's = s.replace("    covering = [entry for entry in entries if entry.covers(as_of)]", "    covering = [entry for entry in entries if entry.covers(as_of)] or [entries[0]]")'

# T062'"'"'s no-uniformity clause, on the one provider whose source states a
# second band. Collapsing to the first band is what a table with one rate per
# model would do, and it under-charges every long-context request by a factor of
# two — the direction that makes a spend ceiling fail to fire.
proof "T062 prompt-length bands — every request is priced at the lowest band" \
  src/runtime/providers/costs.py \
  "tests/unit/test_provider_costs.py::test_the_xai_prompt_length_tier_switches_at_the_stated_threshold" \
  's = s.replace("        if tier.min_input_tokens <= input_tokens:", "        if False:")'

# FR-058'"'"'s disqualification, kept structural. With the unit gate gone a
# float reaches the arithmetic and prices cleanly, so a caller who divided a
# byte count by an average tokens-per-byte figure on the way in gets an answer
# rather than a refusal. That is the one enforcement basis FR-058 rules out by
# name, and nothing downstream of here could tell it from a token count.
proof "T062 unit gate — a non-integer token count is priced instead of refused" \
  src/runtime/providers/costs.py \
  "tests/unit/test_provider_costs.py::test_a_float_token_count_is_refused_rather_than_divided" \
  's = s.replace("    if isinstance(value, bool) or not isinstance(value, int):", "    if False:")'

# T064'"'"'s residue. The reservation exists to over-count — `ledger.py`:
# *"the crash counts the reservation, which is too much rather than too little"*
# — and the split between input and output is not known before the call. Taking
# the cheaper of the two rates inverts that, and on Opus the reservation is then
# a fifth of what the call can cost. It still looks like a derived figure.
proof "T064 reservation figure — the spend reservation is derived at the cheaper rate" \
  src/runtime/providers/costs.py \
  "tests/unit/test_provider_costs.py::test_the_reservation_is_derived_at_the_dearer_of_the_two_rates" \
  's = s.replace("    dearer = max(tier.input_usd_per_mtok, tier.output_usd_per_mtok)", "    dearer = min(tier.input_usd_per_mtok, tier.output_usd_per_mtok)")'

# T065'"'"'s independence, scored from the side this harness can score. The
# tamper is the import a contributor adds the first time the backstop wants to
# know what a call cost; the guard is what refuses it. The other direction —
# the backstop firing with the table emptied — is planted in-process instead,
# for the reason given at the head of this group.
proof "T065 independence — the backstop is made downstream of the cost table" \
  src/runtime/budget_backstop.py \
  "tests/unit/test_budget_backstop.py::test_the_backstop_imports_nothing_from_the_cost_table" \
  's = s.replace("from src.runtime.journal import STEP_MODEL_CALL", "from src.runtime.journal import STEP_MODEL_CALL\nfrom src.runtime.providers.costs import PRICES  # noqa: F401")'

# T065. The property that separates a backstop from a fifth ceiling. research/02
# measured the removed dependency'"'"'s ceiling defaulting to `None`, and a
# maximum a caller can raise is that ceiling with an extra argument: the same
# configuration mistake that put the four FR-005 ceilings out of reach puts this
# one out of reach too, and nothing stops the loop.
proof "T065 unraisable maximum — the backstop can be widened by its caller" \
  src/runtime/budget_backstop.py \
  "tests/unit/test_budget_backstop.py::test_the_maximum_cannot_be_raised" \
  's = s.replace("        if maximum > MAX_MODEL_CALLS:", "        if False:")'

# T065. The metric. Counting every journalled step makes a turn with eight tool
# calls cost nine, so the backstop fires on tool-heavy work that spent almost
# nothing — and an operator whose runs die early removes the backstop, which is
# the one outcome it cannot survive.
proof "T065 metric — tool steps are counted as model calls" \
  src/runtime/budget_backstop.py \
  "tests/unit/test_budget_backstop.py::test_tool_calls_are_not_counted" \
  's = s.replace("        return sum(1 for step in self.journal.steps(session_id)\n                   if getattr(step, \"step_kind\", None) == STEP_MODEL_CALL)", "        return len(self.journal.steps(session_id))")'

# T065. The off-by-one, and it is not cosmetic: `check` runs before the call it
# guards, so `>` permits one call past the maximum every time. The arm below it
# in the same file — that it does not fire under the maximum — passes under this
# tamper, which is what makes the named test the one that separates them.
proof "T065 boundary — the backstop permits one call past its maximum" \
  src/runtime/budget_backstop.py \
  "tests/unit/test_budget_backstop.py::test_it_fires_at_the_maximum_not_one_past_it" \
  's = s.replace("        if made >= self.maximum:", "        if made > self.maximum:")'

# T065 in the loop, which is where it either stops something or does not. The
# tamper leaves the module, the tests and the constructor argument all intact
# and green; only the call site goes. That is exactly how a guard rots, and the
# named arm is the only one in the suite that runs a loop past a ceiling.
proof "T065 wiring — the backstop is built by the loop and never consulted" \
  src/runtime/loop.py \
  "tests/unit/test_budget_backstop.py::test_the_loop_is_stopped_by_the_backstop_with_every_ceiling_out_of_reach" \
  's = s.replace("            if pending_turn is None:\n                self.backstop.check(self.session_id)", "            if False:\n                self.backstop.check(self.session_id)")'

# T065. On by default, because a guard a construction site can omit is absent
# from every construction site written before it existed. The tamper is the
# ordinary-looking version: honour what you were passed, and pass nothing when
# nobody asked for one.
proof "T065 default — a loop constructed without a backstop gets none" \
  src/runtime/loop.py \
  "tests/unit/test_budget_backstop.py::test_the_default_loop_carries_a_backstop_nobody_had_to_pass" \
  's = s.replace("        self.backstop = backstop or CallCountBackstop(journal)", "        self.backstop = backstop")'

# ---------------------------------------------------------------------------
# The seam that makes the cost table reachable.
#
# T062 built the table and T063 the lookup, and neither could price a running
# session: the loop's `ModelResponse` carried no model identifier and no token
# split, so nothing in `src/` could call `price_usd` with the arguments it
# needs. Every turn therefore reached the ledger at the field's `0.0` default
# and FR-005's spend ceiling could not fire. That is finding 029's shape on a
# second dimension — *"the comparison, the wiring and the terminal state all
# worked; the numerator was missing"* — so the arms below are aimed at the
# numerator and not at the comparison.

# The one call to the table from the one module allowed to make it. The tamper
# is the plausible one: keep the seam, keep the split, and put a number on it
# without asking what the vendor charges.
proof "T063 pricing seam — the adapter invents a price instead of reading the table" \
  src/runtime/providers/adapter.py \
  "tests/unit/test_provider_adapter.py::test_a_parsed_turn_arrives_priced_from_the_vendors_own_rates" \
  's = s.replace("        priced = costs.price_usd(\n            provider=parsed.provider, model=model,\n            input_tokens=inputs, output_tokens=outputs, as_of=as_of,\n            operator_prices=operator_prices)\n        spend = priced.usd\n        provenance = priced.provenance", "        spend = 0.0\n        provenance = costs.PROVENANCE_VENDOR")'

# The refusal that makes `spend_usd = None` mean something. Without it `None`
# is just a default nobody set, and the tamper is exactly the coercion the
# docstring says no helper will be offered for.
proof "FR-005 unpriced refusal — an unpriced turn is counted at zero instead" \
  src/runtime/turn.py \
  "tests/unit/test_provider_adapter.py::test_an_unpriced_response_refuses_to_produce_a_spend_figure" \
  's = s.replace("        if self.spend_usd is None:\n            raise UnpricedTurnError(", "        if self.spend_usd is None:\n            return 0.0\n        if False:\n            raise UnpricedTurnError(")'

# The call site, which is the half that actually stops a session. The module
# can refuse all it likes while the loop asks for the raw field; that is the
# same rot shape as the backstop arm above, one layer down.
proof "FR-005 accrual — the loop reads the raw field rather than requiring a price" \
  src/runtime/loop.py \
  "tests/unit/test_loop.py::test_an_unpriced_turn_stops_the_loop_rather_than_accruing_zero" \
  's = s.replace("            reservation, spend_usd=response.require_spend_usd(),", "            reservation, spend_usd=(response.spend_usd or 0.0),")'

# FR-038. A spend figure with no model beside it is not reproducible, because
# the rate is keyed on `(provider, model)` and two models on one provider
# differ by up to 5x. The tamper keeps the span, the cost and the provider.
proof "FR-038 attribution — the model call span drops the model it was priced at" \
  src/runtime/loop.py \
  "tests/unit/test_loop.py::test_the_model_call_span_records_the_model_the_price_was_computed_at" \
  's = s.replace("                \"model\": response.model,", "")'

# The journal side of the same decision. A revision-1 payload records `0.0`
# because that was the field default, and the tamper is the reading any author
# would reach for first: the number is right there, so use it.
proof "T062 journal migration — a pre-pricing turn resumes at its recorded zero" \
  src/runtime/resume.py \
  "tests/unit/test_resume.py::test_a_turn_journaled_before_prices_existed_comes_back_unpriced" \
  's = s.replace("            model, spend, inputs, outputs = \"\", None, None, None", "            model, spend, inputs, outputs = \"\", float(payload.get(\"spend_usd\") or 0.0), None, None")'

# Finding 016's defect arriving through the journal instead of the wire: a
# payload from a revision this build has never seen still has fields this build
# recognises, and reading those is how a rebuild silently drops the rest.
proof "T062 schema gate — a later revision's payload is read for what it recognises" \
  src/runtime/resume.py \
  "tests/unit/test_resume.py::test_a_payload_from_a_later_revision_is_refused_not_partially_read" \
  's = s.replace("    if schema not in READABLE_MODEL_OUTCOME_SCHEMAS:", "    if False:")'

# ---------------------------------------------------------------------------
# OD-27 — the operator-declared price path.
#
# The arms above prove the table is reachable. These prove that opening a
# *second* way in did not reopen what T063 closed. Two families, and they fail
# in opposite directions:
#
#   - the **refusals**, where the tamper admits a declaration that should not
#     be admitted. Every one of them under-charges, which is the direction that
#     makes a ceiling fail to fire, and every one of them looks like a
#     simplification rather than a defect.
#   - the **provenance**, where the tamper still prices correctly and loses the
#     record of *whose* rate it was. Nothing goes red on its own: the totals are
#     right, the session runs, and the only casualty is a later reader's ability
#     to tell a declared figure from a published one. That is precisely the
#     class this harness exists for, because a passing suite is not evidence.

# The limb the decision turns on. The tamper is not sabotage — it is the edit
# an author makes on being told the two-band rule is annoying for a vendor
# whose card they believe is flat. It reintroduces the invented boundary with
# the operator's name on it.
proof "OD-27 context threshold — a single rate is accepted for a two-column card" \
  src/runtime/providers/costs.py \
  "tests/unit/test_provider_costs.py::test_a_single_rate_is_refused_where_the_vendors_card_has_two_columns" \
  's = s.replace("    if len(price.tiers) < 2:\n        raise OperatorPriceError(", "    if False:\n        raise OperatorPriceError(")'

# The way round it. Satisfying "supply both columns" by shape while supplying
# one column by content is what a reader who copied a row does, and the tamper
# is the reading that treats a boundary at which nothing changes as a boundary.
proof "OD-27 identical bands — one column read twice satisfies the two-band rule" \
  src/runtime/providers/costs.py \
  "tests/unit/test_provider_costs.py::test_the_same_rate_twice_is_refused_because_it_is_one_column_read_twice" \
  's = s.replace("        if cheaper or not dearer:", "        if cheaper:")'

# The address half of the two-address property. The tamper is the sympathetic
# one: the operator has a rate for the alias, the alias is a real string the
# vendor documents, so price it.
proof "OD-27 alias address — a declaration is accepted against a moving pointer" \
  src/runtime/providers/costs.py \
  "tests/unit/test_provider_costs.py::test_an_alias_is_not_an_address_a_declaration_may_use" \
  's = s.replace("        refused = REFUSED_ADDRESSES.get((self.provider, self.model))", "        refused = None")'

# The sourced rate's protection. A declaration that construction admits for a
# key the table already holds is a sourced rate displaced by an unsourced one,
# and nothing downstream reports the substitution.
proof "OD-27 vendor precedence — a declaration is allowed to shadow a sourced rate" \
  src/runtime/providers/costs.py \
  "tests/unit/test_provider_costs.py::test_a_declaration_cannot_displace_a_rate_read_off_a_vendors_page" \
  's = s.replace("        if (self.provider, self.model) in PRICES:\n            raise OperatorPriceError(", "        if False:\n            raise OperatorPriceError(")'

# FR-058's treatment, which is the whole of limb ④. Removing the lookup leaves
# a preflight that returns a plausible line for a model nothing prices — worse
# than no preflight, because the operator has now read a startup log saying the
# deployment is priced.
proof "OD-27 startup preflight — an unpriceable model is discovered at its first call" \
  src/runtime/providers/costs.py \
  "tests/unit/test_provider_costs.py::test_an_unpriceable_model_is_refused_at_startup_not_at_its_first_call" \
  's = s.replace("    entry = entry_in_force(provider, model, as_of=as_of,\n                           operator_prices=operator_prices)\n    bands = ", "    entry = next(iter(PRICES.values()))[0]\n    bands = ")'

# The provenance family starts here, and this arm is the one to read. The
# tamper prices the turn **correctly** — the figure, the ceiling and the
# terminal state are all unchanged — and records a declared rate as a published
# one. It is also the plausible edit: `PROVENANCE_VENDOR` is right for the
# branch above it, and reusing it reads as tidying.
proof "OD-27 seam provenance — a declared rate is recorded as a published one" \
  src/runtime/providers/adapter.py \
  "tests/unit/test_provider_adapter.py::test_a_declaration_reaches_the_seam_and_the_response_says_it_was_one" \
  's = s.replace("        spend = priced.usd\n        provenance = priced.provenance", "        spend = priced.usd\n        provenance = costs.PROVENANCE_VENDOR")'

# The record type's own guard. Without it a construction site can supply a
# figure and no provenance, which is the `0.0` defect one field over: a number
# that reads as authoritative because nothing beside it says otherwise.
proof "OD-27 paired fields — a spend figure is admitted with no provenance beside it" \
  src/runtime/turn.py \
  "tests/unit/test_provider_adapter.py::test_a_spend_figure_without_a_provenance_is_refused" \
  's = s.replace("        if (self.spend_usd is None) != (self.spend_provenance is None):", "        if False:")'

# FR-038, and the argument is the `model` arm's above continued. A span
# carrying `(provider, model)` and a figure sends a later reader to
# `costs.PRICES` to check a rate that was never in it.
proof "OD-27 span provenance — the model call span drops where the rate came from" \
  src/runtime/loop.py \
  "tests/unit/test_loop.py::test_the_span_says_whether_the_rate_was_published_or_declared" \
  's = s.replace("                \"spend_provenance\": response.spend_provenance,", "")'

# The journal's disclosure. The tamper leaves the provenance decoded and
# unreported, which is the write-only state this field was nearly left in: read
# by the module that decodes it and visible to nobody resuming the session.
proof "OD-27 resume disclosure — an operator-priced turn resumes indistinguishable from a sourced one" \
  src/runtime/resume.py \
  "tests/unit/test_resume.py::test_a_declared_price_survives_the_journal_as_a_declared_one" \
  's = s.replace("        elif response.spend_provenance == PROVENANCE_OPERATOR:\n            operator_priced.append(turn_index)", "        elif False:\n            operator_priced.append(turn_index)")'

# The migration. A revision-2 payload has a spend and no provenance, and the
# tamper is the cautious-looking reading: do not claim to know, leave it unset.
# It fails on the pairing rule one layer up, which is the point — "unknown" is
# not a state this record admits, because the revision's silence has exactly
# one meaning.
proof "OD-27 revision-2 migration — a pre-OD-27 payload comes back with no provenance" \
  src/runtime/resume.py \
  "tests/unit/test_resume.py::test_a_revision_two_payload_comes_back_as_a_vendor_price" \
  's = s.replace("            if raw_provenance is None and spend is not None:\n                provenance = PROVENANCE_VENDOR", "            if False:\n                provenance = PROVENANCE_VENDOR")'

# ---------------------------------------------------------------------------
# T069/T070 — the caller-visible event stream and the surface that renders it.
#
# TWO OF THE ARMS BELOW TAMPER BY ADDITION RATHER THAN BY REMOVAL, AND THAT IS
# NOT A LAPSE. The guarantee under proof is a *negative*: a field that must not
# be on the wire, and a caller's input that must not be in an error body. There
# is nothing to delete — the mechanism is the absence of a line. The
# counterfactual for an absence is the presence, so those two arms re-introduce
# the exact edit a contributor would make ("carry the state as hex, it is only
# a digest anyway"; "put the path in the 404, the operator will want it"), and
# the proof is that the test notices. An arm that deleted something instead
# would be proving a different mechanism than the test's name claims.

proof "T069 event stream — the FR-036 Secret refusal is gone" \
  src/runtime/events.py \
  "tests/contract/test_event_stream_redaction.py::test_a_secret_cannot_be_placed_on_an_event_at_all" \
  's = s.replace("            refuse_secrets(value, member.name, raise_as=EventError,\n                           destination=\x22a caller-visible event stream\x22)", "            pass")'

proof "T069 event stream — the FR-037 raw-bytes refusal is gone" \
  src/runtime/events.py \
  "tests/contract/test_event_stream_redaction.py::test_raw_bytes_cannot_be_placed_on_an_event" \
  's = s.replace("            _refuse_opaque_bytes(value, member.name)", "            pass")'

# The narrowing, separate from the arm above because it is a different failure:
# the scan still runs and still refuses bytes on a mapping, and only stops
# descending into a list. Three of that test's four planted shapes survive it.
proof "T069 event stream — the FR-037 scan stops at a list" \
  src/runtime/events.py \
  "tests/contract/test_event_stream_redaction.py::test_raw_bytes_cannot_be_placed_on_an_event" \
  's = s.replace("    elif isinstance(value, (list, tuple)):\n        for item in value:\n            _refuse_opaque_bytes(item, f\x22{path}[]\x22)", "    elif False:\n        pass")'

# Additive. See the note above this block.
proof "T069 turn frame — the opaque state is rendered beside its digest" \
  src/runtime/events.py \
  "tests/contract/test_event_stream_redaction.py::test_the_opaque_state_is_on_the_stream_only_as_a_digest" \
  's = s.replace("        return self.emit(KIND_TURN_COMPLETED, turn=record.to_record())", "        return self.emit(KIND_TURN_COMPLETED, turn=dict(record.to_record(), provider_state=record.provider_state.hex()))")'

proof "T069 stream lifecycle — a run reports as ended with no marker" \
  src/runtime/events.py \
  "tests/contract/test_serving_surface.py::test_the_end_of_run_frame_cannot_be_forged_by_omission" \
  's = s.replace("        if kind == TERMINAL_KIND and \x22end_of_run\x22 not in data:", "        if False:")'

proof "T069 stream lifecycle — a stream may begin mid-run" \
  src/runtime/events.py \
  "tests/contract/test_serving_surface.py::test_a_stream_cannot_begin_anywhere_but_at_the_start" \
  's = s.replace("            if not self._events and kind != KIND_SESSION_STARTED:", "            if False:")'

proof "T069 stream lifecycle — events continue after the run has ended" \
  src/runtime/events.py \
  "tests/contract/test_serving_surface.py::test_nothing_is_emitted_after_the_run_has_ended" \
  's = s.replace("            if self._closed:", "            if False:")'

# Additive. See the note above this block.
proof "T070 refusal body — the 404 echoes the path back to the caller" \
  src/runtime/serving.py \
  "tests/contract/test_event_stream_redaction.py::test_a_refusal_does_not_echo_what_the_caller_put_in_the_path" \
  's = s.replace("                       refusal_body(rule_id))", "                       dumps({\x22rule_id\x22: rule_id, \x22reason\x22: REFUSALS[rule_id].reason, \x22requirement\x22: REFUSALS[rule_id].requirement, \x22path\x22: self.path}))")'

proof "T070 request logging — the request line reaches stderr with the path in it" \
  src/runtime/serving.py \
  "tests/contract/test_serving_surface.py::test_the_request_line_does_not_reach_stderr" \
  's = s.replace("        def log_message(self, fmt: str, *args: Any) -> None:", "        def log_message_removed(self, fmt: str, *args: Any) -> None:")'

proof "T070 bind address — an empty host is accepted and binds everywhere" \
  src/runtime/serving.py \
  "tests/contract/test_serving_surface.py::test_the_surface_refuses_to_bind_without_an_explicit_host" \
  's = s.replace("    if not host or host in (\x220.0.0.0\x22, \x22::\x22, \x22*\x22):", "    if False:")'

proof "T070 absent result — a running session serves an empty record with a 200" \
  src/runtime/serving.py \
  "tests/contract/test_serving_surface.py::test_a_result_that_does_not_exist_yet_is_a_refusal_and_not_an_empty_one" \
  's = s.replace("    if view.result is None:\n        raise SurfaceError(RULE_RESULT_ABSENT)", "    if view.result is None:\n        return {\x22session_id\x22: view.session_id, \x22payload\x22: None}")'

# ---------------------------------------------------------------------------
# T029 — the process entry points, and the human channel they construct.
#
# Every arm below is a mechanism that did not exist at `f8c844c` and could not
# have, because the assembly point it belongs to did not: `config.load` was
# referenced only from tests, `Config` was constructed only by its own module's
# factory, and `require_priceable` was called from nowhere. The reporting
# machinery for four authorities was built and unreachable. These arms are the
# reachability, put under the same counterfactual as everything above it.

# The vehicle, and the only arm here whose fault is a *crash* rather than an
# assertion. Measured either side rather than argued: with the loop replaced by
# a buffered write, the plant aborts 12 of 12 with
# `Fatal Python error: _enter_buffered_busy`; with it in place, 0 of 12. The
# tamper is the plausible edit — `sys.stderr.write` is what anyone writing this
# module from scratch reaches for first, and it is correct on the main thread.
proof "T029 operator channel — the write is buffered again" \
  src/contracts/operator_log.py \
  "tests/unit/test_operator_log.py::test_an_unbuffered_write_from_a_daemon_thread_does_not" \
  's = s.replace("        payload = (body + \x22\\n\x22).encode(\x22utf-8\x22, errors=\x22replace\x22)\n        while payload:\n            payload = payload[os.write(self._fd, payload):]", "        import sys as _sys\n        _sys.stderr.write(body + \x22\\n\x22)\n        _sys.stderr.flush()")'

# The per-line framing, which is separable from the vehicle. There is no arm
# for the short-write resumption beside it and that is deliberate: one was
# written, came back UNPROVEN, and the reason is recorded in `say`'s docstring
# — fd 2 is blocking, so the kernel never returns short and the loop cannot be
# made load-bearing by any test in this suite. It is kept and not claimed.
proof "T029 operator channel — only the first line of a report is identified" \
  src/contracts/operator_log.py \
  "tests/unit/test_operator_log.py::test_every_line_of_a_multi_line_report_is_prefixed" \
  's = s.replace("        body = \x22\\n\x22.join(prefix + line for line in message.split(\x22\\n\x22))", "        body = prefix + message")'

# The wiring. `src/supervisor/lease.py` does not import the channel and is not
# handed one — the renewer's `raise` reaches a human only because the entry
# point replaced `threading.excepthook` before any thread started. Removing the
# one call is what puts the renewer back where its note said it was.
proof "T029 thread hook — the supervisor starts without adopting it" \
  src/supervisor/main.py \
  "tests/contract/test_startup_entry_points.py::test_an_entry_point_adopts_the_thread_hook_before_anything_starts" \
  's = s.replace("    log.adopt_thread_exceptions()", "    pass")'

proof "T029 thread hook — the runtime starts without adopting it" \
  src/runtime/main.py \
  "tests/contract/test_startup_entry_points.py::test_an_entry_point_adopts_the_thread_hook_before_anything_starts" \
  's = s.replace("    log.adopt_thread_exceptions()", "    pass")'

# OD-27's gate at its **call site**, which is a different mechanism from the
# gate itself. `costs.py`'s own arm above proves `require_priceable` refuses;
# this proves something asks it. The tamper is the shape the tree was actually
# in — a preflight that exists and is never called.
proof "T029 spend preflight — the runtime starts without asking whether the model is priced" \
  src/runtime/main.py \
  "tests/contract/test_startup_entry_points.py::test_an_unpriced_model_refuses_startup" \
  's = s.replace("        rate_line = require_priceable(", "        rate_line = \x22unchecked\x22 or require_priceable(")'

# The gathering, on both entry points. It is a deliberate deviation from
# `src/proxy/main.go`, which stops at the first `Fatalf`, and the tamper is
# therefore the Go shape restored rather than a mangling — which is exactly why
# it needs an arm: it would read as a correction in review.
proof "T029 gathered refusals — the runtime reports the price failure and drops the bound one" \
  src/runtime/main.py \
  "tests/contract/test_startup_entry_points.py::test_the_runtime_gathers_the_price_and_bound_refusals" \
  's = s.replace("    except (CostTableError, ProviderError, ValueError) as exc:\n        refusals.append(f\x22the model in force is not priceable (OD-27): {exc}\x22)", "    except (CostTableError, ProviderError, ValueError) as exc:\n        log.refuse(f\x22the model in force is not priceable (OD-27): {exc}\x22)")'

# The one that matters most off Linux: `preflight()` fails on macOS by design,
# so a first-refusal-wins order means the twelve-key configuration report — the
# thing this whole seam exists to make reachable — can never be seen on a
# development host.
proof "T029 gathered refusals — the supervisor stops at the platform check" \
  src/supervisor/main.py \
  "tests/contract/test_startup_entry_points.py::test_the_supervisor_gathers_the_platform_and_configuration_refusals" \
  's = s.replace("    except PreflightError as exc:\n        refusals.append(str(exc))", "    except PreflightError as exc:\n        log.refuse(str(exc))")'

# OD-28 ground ①. The tamper reports the same path and does not open it, which
# is the edit somebody makes on the view that opening a store to print its name
# is wasteful — and it leaves the ground exactly where it was while the
# readiness line reads as though it had moved.
proof "T029 session store — the supervisor names the store without opening it" \
  src/supervisor/main.py \
  "tests/contract/test_startup_entry_points.py::test_the_supervisor_opens_the_session_store" \
  's = s.replace("    with SessionTable(session_db) as sessions:\n        log.say(_ready(config, sessions.path))", "    log.say(_ready(config, session_db))")'

# OD-27's *nobody was asked* / *the operator declares nothing* distinction, one
# layer below the key that exists to hold it open. The tamper is the lenient
# reading, and it is the one a contributor reaches for on the first support
# ticket about a missing file.
proof "T029 price declaration — a path that resolves to nothing declares nothing" \
  src/runtime/providers/operator_prices.py \
  "tests/unit/test_operator_prices.py::test_a_missing_file_is_not_the_literal" \
  's = s.replace("    except OSError as exc:\n        raise OperatorPriceError(", "    except OSError as exc:\n        return NO_OPERATOR_PRICES\n    if False:\n        raise OperatorPriceError(")'

# The conversion, which is what is left after the enumeration came out. An
# earlier arm here removed a permitted-field set and reported UNPROVEN, because
# the dataclass constructor already refuses an unexpected keyword and its
# message contains the field name the assertion was matching on — the blind
# arm this harness exists to catch. What is load-bearing is turning that
# `TypeError` into a refusal: without it a typo in a rate card leaves the
# startup gate on an unhandled traceback rather than on an operator report.
proof "T029 price declaration — a malformed declaration escapes as a TypeError" \
  src/runtime/providers/operator_prices.py \
  "tests/unit/test_operator_prices.py::test_an_unrecognised_field_is_refused" \
  's = s.replace("    try:\n        return OperatorPrice(\n            tiers=tuple(_rate(where, i, band) for i, band in enumerate(tiers)),\n            **fields,\n        )\n    except TypeError as exc:\n        raise OperatorPriceError(f\x22{where}: {exc}\x22) from None", "    return OperatorPrice(\n        tiers=tuple(_rate(where, i, band) for i, band in enumerate(tiers)),\n        **fields,\n    )")'

# ---------------------------------------------------------------------------
# The suite's own harness.
#
# `tests/conftest.py` is not a mechanism the specification names, and it is under
# proof for the reason the rest of this file exists: it is infrastructure whose
# failure destroys evidence rather than producing a red test. The basetemp
# redirect deleted a *concurrent* run's live temporary tree, and the victim saw a
# `FileNotFoundError` from whichever test next touched `tmp_path` — a fault in
# one process surfacing as an unexplained failure in another, naming nothing
# about the cause. That is the environmental-fault-wearing-a-result's-clothes
# shape this harness was built for, so the repair gets the same treatment.

# The narrowing under proof is the liveness predicate, not the per-pid keying.
# Those are two mechanisms and only one of them can be removed while leaving the
# module importable and the other five arms in the file green: reaping every
# per-pid directory unconditionally is exactly the uid-keyed behaviour restated,
# and it is also the edit a contributor would make if they read the `os.kill`
# probe as defensive clutter. The named test is the only one of the six that
# separates the two — `test_an_exited_process_directory_is_reaped` passes under
# the tamper, because an unconditional reaper does still reap the dead.
proof "e4ef6e6 basetemp reaping — a live process's directory is reaped too" \
  tests/conftest.py \
  "tests/unit/test_conftest_basetemp.py::test_a_live_process_directory_survives_another_runs_configure" \
  's = s.replace("        try:\n            os.kill(int(name), 0)\n        except ProcessLookupError:\n            shutil.rmtree(os.path.join(root, name), ignore_errors=True)\n        except PermissionError:\n            continue  # Alive and owned by someone else.", "        shutil.rmtree(os.path.join(root, name), ignore_errors=True)")'

# The child processes a run leaves behind — the same shape as the basetemp arm
# above and found the same way. Three supervisors spawned by
# `test_lease_revocation.py`'s crash arm outlived their runs by four days,
# renewing a lease five times a second against a `basetemp` whose pytest
# process had exited. The arm had no `try/finally`, so any failure between the
# spawn and the kill leaked one — and the basetemp defect e4ef6e6 repaired is
# exactly such a failure, which is how the three were made.
#
# Nothing in the suite was looking, which is the part these arms are mostly
# about. A leaked process produces no report, and the run that leaks one is
# usually red for the failure that caused the leak, so the survivor is the one
# thing on the screen that nobody attributes to anything.

# Where the child is killed, and therefore when. Removing this leaves the
# session-scoped sweep below as the only reaper, and a child leaked by the
# third test then spins alongside the remaining twelve hundred.
proof "orphaned crash children — a failed arm leaves its supervisor running" \
  tests/integration/test_lease_revocation.py \
  "tests/integration/test_lease_revocation.py::test_the_crash_arms_child_does_not_outlive_a_failing_test" \
  's = s.replace("    finally:\n        if child.poll() is None:  # pragma: no cover — only on an assert above\n            child.kill()\n\n    # Nothing ran on the way down.", "    finally:\n        pass\n\n    # Nothing ran on the way down.")'

# The two scopes on those scans, which finding 039 established are what stands
# between this file and every other checkout on the host. The marker they match
# on is an ordinary construction, and `ps -e` does not stop at a tree boundary,
# so unscoped the read reports a concurrent pass's supervisor as this run's leak
# — 10 failures in 10 with a decoy alive — and the kill SIGKILLs it, 10 in 10.
#
# These are expressible here only because the arms plant their own decoy. A
# tamper that widens the scan changes nothing on a quiet host, so a proof over
# an arm that merely *ran* the scan would report UNPROVEN and read as the scope
# being unnecessary. The decoy is what makes the widened scan wrong on purpose.
proof "crash-child read — the observer scans the whole machine again" \
  tests/integration/test_lease_revocation.py \
  "tests/integration/test_lease_revocation.py::test_the_leak_read_ignores_another_runs_supervisor" \
  's = s.replace("            if parent != mine or fields[2].startswith(\x22Z\x22):", "            if fields[2].startswith(\x22Z\x22):")'

# The destructive half, and the one worth more than the arm above: this does
# not hand another pass a false red, it ends that pass'"'"'s supervisor child.
proof "crash-child kill — the sweep reaches outside this run again" \
  tests/integration/test_lease_revocation.py \
  "tests/integration/test_lease_revocation.py::test_the_kill_leaves_another_runs_supervisor_alone" \
  's = s.replace("        if marker not in fields[2] or scope not in fields[2]:", "        if marker not in fields[2]:")'

# The sweep's own call site. Every other arm here calls the sweep directly, so
# all of them stay green with this deleted — the mechanism intact, never
# invoked, and invisible. That is the shape the rest of this file exists for.
proof "leaked-child sweep — the summary never runs it" \
  tests/conftest.py \
  "tests/unit/test_conftest_child_reaping.py::test_a_run_that_leaks_a_child_kills_it_and_says_so" \
  's = s.replace("    leaked = _reap_leaked_children()", "    leaked = []")'

# Killing, as distinct from reporting. A report that names a process and leaves
# it running has described the leak rather than ended it.
proof "leaked-child sweep — the report is made and nothing is killed" \
  tests/conftest.py \
  "tests/unit/test_conftest_child_reaping.py::test_the_reaper_kills_what_it_reports" \
  's = s.replace("        try:\n            os.kill(pid, signal.SIGKILL)\n        except OSError:\n            continue  # Exited between the listing and the signal.", "        pass")'

# The zombie narrowing, which is what keeps the report worth reading. An exited
# child nobody waited on is still parented to pytest and the suite makes them
# routinely; counting those as leaks fires the banner on nearly every run.
proof "leaked-child sweep — an unreaped exited child counts as a leak" \
  tests/conftest.py \
  "tests/unit/test_conftest_child_reaping.py::test_a_finished_child_nobody_waited_on_is_not_a_leak" \
  's = s.replace("if parent != mine or pid in exempt or fields[2].startswith(\x22Z\x22):", "if parent != mine or pid in exempt:")'

# The exemption for children the standard library owns. `multiprocessing`'s
# resource tracker is a direct child of any process that has used a spawn
# context and is meant to outlive every test; the concurrent-writer probe
# starts one on every run. Sweeping it is not cleanup.
proof "leaked-child sweep — the multiprocessing resource tracker is killed" \
  tests/conftest.py \
  "tests/unit/test_conftest_child_reaping.py::test_the_multiprocessing_resource_tracker_is_never_reaped" \
  's = s.replace("        if isinstance(pid, int):\n            pids.add(pid)", "        pass")'

# Finding 034's shape, refused rather than met again. An unavailable `ps` and a
# run that leaked nothing produce the same empty list and opposite facts, and
# reporting the second as the first is an instrument scoring a clean sweep over
# a measurement it never took.
proof "leaked-child sweep — a sweep that could not run reads as a clean one" \
  tests/conftest.py \
  "tests/unit/test_conftest_child_reaping.py::test_a_sweep_that_could_not_run_is_reported_and_not_scored_as_clean" \
  's = s.replace("        _children_unchecked = f\x22ps did not run: {type(exc).__name__}: {exc}\x22\n        return []", "        return []")'

# ---------------------------------------------------------------------------
# T096 — the sandbox image's FR-021 properties.
#
# The brief that added these asked whether a Dockerfile can be put under
# removal proof meaningfully. It can, but only because `src/sandbox/image_policy.py`
# exists: a Dockerfile with nothing reading it has no test to fail, and an arm
# over one would be asserting that a file's bytes are its bytes. The arms below
# split accordingly — one over the artifact, five over the checker that gives
# the artifact a failure mode.
#
# None of them is an egress control. FR-021 and the egress policy are one
# control (research.md §T-11); what these prove load-bearing is the *shipping*
# clause — that the image was built with its dependencies resolved and ships no
# way to resolve another.

# The artifact arm. `--require-hashes` is what makes an unpinned addition to the
# lock file a build failure instead of a silent fetch of whatever the index is
# serving today, and it is one word in one line of a file nothing else reads.
proof "T096 sandbox image — the build resolves without pinning the hashes" \
  deploy/images/sandbox.Dockerfile \
  "tests/invariants/test_sandbox_image.py::test_the_committed_sandbox_image_has_no_findings" \
  's = s.replace("pip install --no-cache-dir --require-hashes --prefix=/opt/deps", "pip install --no-cache-dir --prefix=/opt/deps")'

# Ordering, which is the whole of this rule. Without it a Dockerfile satisfies
# SBX-IMG-002 by carrying the teardown anywhere in the stage and reinstalling
# below it — both strings present, the manager shipped.
proof "T096 image policy — a teardown counts wherever it sits" \
  src/sandbox/image_policy.py \
  "tests/invariants/test_sandbox_image.py::test_removing_before_installing_is_still_a_finding" \
  's = s.replace("        torn_down = removed_at.get(name)\n        if torn_down is None or torn_down < line:", "        torn_down = removed_at.get(name)\n        if torn_down is None:")'

# The stage narrowing. Removing it does not weaken the checker — it makes it
# over-broad, and forbids the builder stage from configuring the index it is
# there to resolve from. An over-broad rule gets suppressed, and a suppressed
# rule checks nothing.
proof "T096 image policy — an index URL is a finding in every stage" \
  src/sandbox/image_policy.py \
  "tests/invariants/test_sandbox_image.py::test_an_index_url_in_the_builder_stage_is_not_a_finding" \
  's = s.replace("        if inst.verb in (\x22ENV\x22, \x22ARG\x22) and in_shipped:", "        if inst.verb in (\x22ENV\x22, \x22ARG\x22):")'

# Continuation joining. Every rule is a regex over an instruction body, so a
# violation split across a line continuation is invisible without this — and a
# multi-line `RUN` is the normal shape for the exact block being checked.
proof "T096 image policy — a continued line is two instructions" \
  src/sandbox/image_policy.py \
  "tests/invariants/test_sandbox_image.py::test_a_continuation_is_one_instruction" \
  's = s.replace("            buffer.append(line[:-1])\n            continue", "            pass")'

# Which stage ships. Reading the first FROM instead of the last inverts every
# stage-scoped rule at once: the builder gets audited and the image that ships
# does not.
proof "T096 image policy — the first stage is treated as the one that ships" \
  src/sandbox/image_policy.py \
  "tests/invariants/test_sandbox_image.py::test_the_final_stage_is_the_last_from" \
  's = s.replace("    return stages[-1]", "    return stages[0]")'

# SBX-IMG-006 is the rule that keeps the *other* mechanism alive. CI builds no
# images, so the build-time assertion runs only on a laptop; this is what stops
# it being deleted as redundant with the static checker, and the two are not
# redundant — a package manager arriving from a base image change alters no
# line here and is invisible to a static reading.
proof "T096 image policy — an image that never checks itself is accepted" \
  src/sandbox/image_policy.py \
  "tests/invariants/test_sandbox_image.py::test_a_missing_build_time_assertion_is_found" \
  's = s.replace("    resolved_from_lock = False\n    asserts_at_build_time = False", "    resolved_from_lock = False\n    asserts_at_build_time = True")'

# ---------------------------------------------------------------------------
# T116 — the reference application, and the half of a known-correct answer that
# answer-checking cannot see.
#
# The first arm is the one this fixture exists for. It removes nothing from any
# answer: every question is still answered correctly under it, and every
# assertion about answers still passes. What it removes is the opaque field the
# answers do not depend on — which is finding 016's blindness reproduced on
# purpose, so that the assertion which catches it is on the record as the one
# doing the work.

proof "T116 reference app — a served part omits its attestation" \
  tests/fixtures/reference-app/app.py \
  "tests/unit/test_reference_app.py::test_the_served_surface_reproduces_every_evidence_digest" \
  's = s.replace("        for row in self.state[\x22parts\x22]:\n            if row[\x22part_id\x22] == part_id:\n                return dict(row)", "        for row in self.state[\x22parts\x22]:\n            if row[\x22part_id\x22] == part_id:\n                return {k: v for k, v in row.items() if k != \x22attestation\x22}")'

# The key is what makes an attestation unforgeable from the served surface. A
# plain digest of the same identity is still independent of every business
# field, so the lossy oracle still fails against it and that arm stays green —
# which is why the named test here is the key one and not that one.
proof "T116 reference app — the attestation is a digest rather than a MAC" \
  tests/fixtures/reference-app/seed.py \
  "tests/unit/test_reference_app.py::test_a_different_key_moves_every_attestation_and_no_visible_field" \
  's = s.replace("    return hmac.new(key, dumps(identity), hashlib.sha256).hexdigest()", "    return hashlib.sha256(dumps(identity)).hexdigest()")'

# The coprimality of the part count and the status cycle, which is load-bearing
# arithmetic and reads as an arbitrary constant. Twelve parts is the number the
# first draft used, and it degenerates a filtered question to an empty evidence
# set while every answer and digest assertion goes on passing.
proof "T116 reference app — the part count shares a factor with the status cycle" \
  tests/fixtures/reference-app/seed.py \
  "tests/unit/test_reference_app.py::test_no_question_has_an_empty_evidence_set" \
  's = s.replace("PART_COUNT = 11", "PART_COUNT = 12")'

# Deny by default at the fixture's own door. T114 asserts that nothing which
# failed to resolve read-only reaches the target; a target that answered an
# operation its published specification does not describe could not exercise
# that, because there would be nothing for the enforcement point to be right
# about.
proof "T116 reference app — an unpublished operation resolves to something" \
  tests/fixtures/reference-app/app.py \
  "tests/unit/test_reference_app.py::test_an_unpublished_operation_is_refused_by_rule" \
  's = s.replace("        raise OperationError(\n            404,\n            \x22REFAPP-001\x22,\n            \x22the published specification describes no such operation\x22,\n        )", "        return self._health(query)")'

# The private copy. T180 drives a copy of the workload against an untouched
# control; sharing the document makes the write arm mutate the control and the
# diff come back empty — a battery reporting no unauthorized effect because its
# baseline moved with it.
proof "T116 reference app — the application holds the caller's state by reference" \
  tests/fixtures/reference-app/app.py \
  "tests/unit/test_reference_app.py::test_two_applications_built_from_one_state_do_not_share_it" \
  's = s.replace("        self.state = json.loads(json.dumps(state))  # a private copy, always", "        self.state = state")'

# The fixture origin refuses the wildcards for the same reason
# `src/runtime/serving.py` does. A listening surface created by an omission is
# the shape, and a fixture beside the adversarial batteries is a bad place for
# it.
proof "T116 reference app — the fixture origin binds every interface" \
  tests/fixtures/reference-app/app.py \
  "tests/unit/test_reference_app.py::test_the_origin_refuses_to_bind_every_interface" \
  's = s.replace("    if not host or host in (\x220.0.0.0\x22, \x22::\x22, \x22*\x22):", "    if False:")'

# T203 reports this size wherever SC-001 appears, so the list of figures the
# README is required to state is the only thing standing between a stale
# denominator and a silent one. One name dropped from it is one figure the
# README may state wrongly forever, and the check that walks the list would
# never mention it — which is why the check compares the list against the
# measurement rather than only iterating it.
proof "T116 stated size — a measured figure drops off the list the README must state" \
  tests/fixtures/reference-app/size.py \
  "tests/unit/test_reference_app.py::test_the_readme_states_the_size_that_was_measured" \
  's = s.replace("STATED_IN_README = (\n    \x22application_files\x22,", "STATED_IN_README = (\n    # removed\n")'

# --- The harness's own scorer, and the record it writes ----------------------
#
# These nine arms tamper `tests/removal_proofs.sh` and
# `tools/removal_proofs_summary.py` — this instrument and its record. That is a
# new target for this file and it is safe for the reason the header gives: every
# tamper lands on the COPY under `mktemp -d`, and the copy is read by the tests
# below rather than executed, so the running script is never the tampered one.
#
# They exist because the scorer is where every silent failure this instrument has
# had so far has lived, and until now nothing tested it. `finding 032` repaired
# `proof()`'s exit-status classifier and shipped no test with the repair; the
# defect these arms cover was the same mistake twenty lines above it in the same
# file, and it survived that pass untouched.

proof "harness scorer — the SKIPPED fall-through restored, so a passing test reads as skipped" \
  tests/removal_proofs.sh \
  "tests/unit/test_removal_proof_scoring.py::test_a_passing_test_whose_verdict_moved_to_the_next_line_is_not_scored_skipped" \
  's = s.replace("  if echo \x22$out\x22 | grep -qE " + chr(39) + " (SKIPPED|XFAIL|XPASS)" + chr(39) + "; then echo SKIPPED; return; fi\n  echo UNREADABLE", "  echo SKIPPED")'

proof "harness scorer — an unreadable baseline counted as a skip, where a lost arm is invisible" \
  tests/removal_proofs.sh \
  "tests/unit/test_removal_proof_scoring.py::test_an_unreadable_baseline_is_counted_apart_from_the_skips" \
  's = s.replace("      _record unreadable baseline-verdict-unreadable\n      UNREADABLE=$((UNREADABLE+1)); return 0 ;;", "      _record unreadable baseline-verdict-unreadable\n      SKIP=$((SKIP+1)); return 0 ;;")'

proof "harness scorer — the skip reason is invented again instead of read off the baseline" \
  tests/removal_proofs.sh \
  "tests/unit/test_removal_proof_scoring.py::test_the_skip_reason_reported_is_the_one_pytest_recorded" \
  's = s.replace("      why=$(baseline_skip_reason \x22$test\x22)", "      why=\x22\x22")'

proof "harness scorer — the baseline stops asking pytest why it skipped anything" \
  tests/removal_proofs.sh \
  "tests/unit/test_removal_proof_scoring.py::test_the_baseline_asks_pytest_for_the_reasons_it_will_later_quote" \
  's = s.replace("python3 -m pytest tests -v -" + "rs --tb=no", "python3 -m pytest tests -v --tb=no")'

proof "harness scorer — a missing Go toolchain goes back to being a skip, not an abort" \
  tests/removal_proofs.sh \
  "tests/unit/test_removal_proof_scoring.py::test_a_missing_toolchain_aborts_when_go_arms_are_declared" \
  's = s.replace("  if [ \x22$1\x22 -gt 0 ]; then echo ABORT; return; fi\n", "")'

# --- The copy list's two silent directions, closed on 2026-08-10 ---------------
#
# Both arms cover a check whose absence is invisible by construction, which is
# why neither existed before: a copy list that has silently lost a directory
# reports N arms `test-already-failing` and nothing else, and that is exactly
# what happened for `deploy/`, `.github/` and `specs/` in turn.
proof "harness setup — the unlisted-path classifier stops naming anything, so the copy list's fourth omission is silent again" \
  tests/removal_proofs.sh \
  "tests/unit/test_removal_proof_scoring.py::test_a_planted_top_level_directory_is_named" \
  's = s.replace("\n    echo \x22$base\x22\n", "\n    :\n")'

proof "harness setup — the classifier stops asking git, so a report file in the repository root reads as an omitted directory" \
  tests/removal_proofs.sh \
  "tests/unit/test_removal_proof_scoring.py::test_an_ignored_artifact_is_not_named_but_an_unlisted_directory_still_is" \
  's = s.replace("    git -C \x22$1\x22 check-ignore -q -- \x22$base\x22 2>/dev/null && continue\n", "")'

proof "harness setup — the work-tree copy discards its errors again, so a failed copy reads as a path nobody listed" \
  tests/removal_proofs.sh \
  "tests/unit/test_removal_proof_scoring.py::test_the_work_tree_copy_does_not_discard_its_own_errors" \
  's = s.replace("  cp -r \x22$SRC/$_p\x22 \x22$WORK/\x22 || {", "  cp -r \x22$SRC/$_p\x22 \x22$WORK/\x22 2>/dev/null || {")'

# The replacement writes the variable as `\x24WORK` on purpose. The named test
# greps THIS file for a quoted work-tree dotfile path, and a snippet spelling
# that path out would put it in the UNTAMPERED source — failing the test before
# any tamper, which is a guard defeated by the declaration of its own proof.
# Observed, not foreseen: the first version of this comment quoted the pattern
# and the test fired on the comment.
proof "harness setup — the baseline transcript moves back inside the work tree, so the tree under test carries an undeclared file again" \
  tests/removal_proofs.sh \
  "tests/unit/test_removal_proof_scoring.py::test_the_harness_writes_no_scratch_files_into_the_work_tree" \
  's = s.replace("BASELINE_PY=\x22$SCRATCH/.baseline-pytest.txt\x22", "BASELINE_PY=\x22\x24WORK/.baseline-pytest.txt\x22")'

# --- The already-failing baseline, split out of `unproven` on 2026-08-10 -------
#
# Four arms, mirroring the four the `unreadable` outcome already has, because the
# mechanism has the same four parts and each fails on its own: the counter, the
# exit status, the record's total and the record's reconciliation sum.
#
# The first is the one worth reading twice. `unproven` is the only word this
# instrument produces that means **the mechanism is dead**, and while an
# already-failing baseline was counted in it, that word was also the presenting
# symptom of a dirty suite and of three separate omissions from the copy list at
# the top of this file. The arm below puts the fold back and the test notices.
proof "harness scorer — an already-failing baseline counted back into unproven, where a dead mechanism is indistinguishable from a dirty suite" \
  tests/removal_proofs.sh \
  "tests/unit/test_removal_proof_scoring.py::test_a_baseline_that_already_failed_is_counted_apart_from_the_unproven" \
  's = s.replace("      _record unusable test-already-failing\n      UNUSABLE=$((UNUSABLE+1)); return 0 ;;", "      _record unproven test-already-failing\n      FAIL=$((FAIL+1)); return 0 ;;")'

# The direction the repair could have failed in, and the worse one. These arms
# used to be counted in FAIL, which the exit status consults, so splitting them
# out without extending the last line turns every dirty-baseline run from red to
# GREEN — finding 032's fabrication pointing the other way.
proof "harness scorer — the unusable count dropped from the exit status, so a dirty baseline exits 0" \
  tests/removal_proofs.sh \
  "tests/unit/test_removal_proof_scoring.py::test_an_already_failing_baseline_keeps_the_weight_it_already_had" \
  's = s.replace(" && [ \x22$UNUSABLE\x22 -eq 0 ]\n", "\n")'

proof "harness record — the unusable total dropped, so the unscored arm reads as a dead mechanism" \
  tools/removal_proofs_summary.py \
  "tests/unit/test_removal_proof_scoring.py::test_the_record_counts_an_already_failing_arm_in_a_total_of_its_own" \
  's = s.replace("            \x22unusable\x22: unusable,\n", "")'

proof "harness record — the unusable count left out of the reconciliation sum" \
  tools/removal_proofs_summary.py \
  "tests/unit/test_removal_proof_scoring.py::test_the_record_counts_an_already_failing_arm_in_a_total_of_its_own" \
  's = s.replace("counted = proved + unproven + skipped + timed_out + unreadable + unusable", "counted = proved + unproven + skipped + timed_out + unreadable")'

proof "harness scorer — the unreadable count dropped from the exit status" \
  tests/removal_proofs.sh \
  "tests/unit/test_removal_proof_scoring.py::test_an_unreadable_baseline_carries_weight_in_the_exit_status" \
  's = s.replace("[ \x22$FAIL\x22 -eq 0 ] && [ \x22$TIMEOUT\x22 -eq 0 ] && [ \x22$UNREADABLE\x22 -eq 0 ]", "[ \x22$FAIL\x22 -eq 0 ] && [ \x22$TIMEOUT\x22 -eq 0 ]")'

proof "harness record — the unreadable total dropped, so the lost arm is not in the record" \
  tools/removal_proofs_summary.py \
  "tests/unit/test_removal_proof_scoring.py::test_the_record_counts_an_unreadable_arm_in_a_total_of_its_own" \
  's = s.replace("            \x22unreadable\x22: unreadable,\n", "")'

# The other direction of the same record. Dropping the term from the sum does not
# lose the number, it makes the record call itself `inconsistent` — which spends
# the one signal that means "no figure here can be trusted" on a run that
# reconciles perfectly well.
proof "harness record — the unreadable count left out of the reconciliation sum" \
  tools/removal_proofs_summary.py \
  "tests/unit/test_removal_proof_scoring.py::test_the_record_counts_an_unreadable_arm_in_a_total_of_its_own" \
  's = s.replace("counted = proved + unproven + skipped + timed_out + unreadable + unusable", "counted = proved + unproven + skipped + timed_out + unusable")'

# The bytecode arm's own condition. Not a scorer arm, but the same shape: the
# check went quiet in exactly the environment its subject runs in.
proof "stale bytecode — the arm inherits the image's PYTHONDONTWRITEBYTECODE and plants nothing" \
  tests/unit/test_tamper_matching.py \
  "tests/unit/test_tamper_matching.py::test_the_stale_pyc_arm_plants_its_hazard_where_the_images_disable_bytecode" \
  's = s.replace("    env.pop(\x22PYTHONDONTWRITEBYTECODE\x22, None)", "    pass")'

# The title check in `tools/check_tampers.py`, and it is one arm because the
# mechanism is one comparison. The two constructs that reach it — substitution
# and expansion — are two parametrizations of the named test rather than two
# proofs, since removing the comparison takes both and there is nothing a
# second arm would distinguish.
#
# It is the first proof this file declares against `check_tampers.py`, whose two
# older floor guards still have none. That asymmetry is left alone rather than
# closed quietly here: covering them is its own pass, and it is stated so the
# gap reads as unvisited rather than as decided.
proof "tamper gate — the written title is no longer compared with the one bash produced, so a substituted title records as healthy" \
  tools/check_tampers.py \
  "tests/unit/test_tamper_matching.py::test_a_title_the_shell_rewrites_is_refused" \
  's = s.replace("        if written is not None and written != proof.name:", "        if False:")'

# ---------------------------------------------------------------------------
# Finding 036 — the instrument census, and the six ways it goes quiet.
#
# `tools/instruments.py` is a validator, and the failure this repository keeps
# hitting is a validator that passes everything because its pattern never
# matches. Its whole product is a *report*, so every arm below removes a
# condition and leaves a checker that still exits 0 over the perturbation it
# was built to catch. Two arms are about looking rather than reporting — the
# comment exclusion, and whether the entry-point scan reads the filesystem at
# all — and those are the two that would leave the census green forever.

proof "census — a renamed job reads as an ordinary missing step" \
  tools/instruments.py \
  "tests/unit/test_instrument_census.py::test_a_renamed_job_is_reported" \
  's = s.replace("        block = blocks.get(entry.job)", "        block = blocks.get(entry.job, \x22\x22)")'

proof "census — a deleted CI step is not reported" \
  tools/instruments.py \
  "tests/unit/test_instrument_census.py::test_a_deleted_step_is_reported" \
  's = s.replace("        if entry.anchor not in block:", "        if False:")'

# The arm for finding 036's own defect. Without this direction a gate can be
# wired into CI and stay off the list, which is the whole reason the file
# exists.
proof "census — a gate wired into CI and missing from the list is not reported" \
  tools/instruments.py \
  "tests/unit/test_instrument_census.py::test_a_gate_wired_into_ci_and_missing_from_the_census_is_reported" \
  's = s.replace("                if reference not in invoked:", "                if False:")'

# Direction 4, the second population — the job census by `name:`. Directions 1
# and 2 above read the mapping key; nothing read the `name:` value, and the two
# are different strings with different audiences. Measured at `8d74942`:
# renaming a job's `name:` left seven instruments silent, this one among them,
# and appending a seventh job was invisible to everything. Each arm below
# removes one condition and leaves a reconciliation that still exits 0 over the
# perturbation it was built to catch.

proof "job census — a renamed job name reads as agreement" \
  tools/instruments.py \
  "tests/unit/test_instrument_census.py::test_a_renamed_job_name_is_reported" \
  's = s.replace("        elif found.group(1) != job.name:", "        elif False:")'

proof "job census — a job added to CI and missing from the list is not reported" \
  tools/instruments.py \
  "tests/unit/test_instrument_census.py::test_a_job_added_to_ci_and_missing_from_the_census_is_reported" \
  's = s.replace("        if not any(job.key == key for job in declared):", "        if False:")'

proof "job census — a job whose figures carry no kernel is not reported" \
  tools/instruments.py \
  "tests/unit/test_instrument_census.py::test_a_job_that_drops_the_runner_identity_action_is_reported" \
  's = s.replace("        if IDENTITY_ACTION not in block:", "        if False:")'

# The vacuity floor, and it is the arm that would leave direction 4 green
# forever: a census over nothing reconciles perfectly with any workflow.
proof "job census — an empty declaration reconciles cleanly" \
  tools/instruments.py \
  "tests/unit/test_instrument_census.py::test_the_job_census_is_not_empty" \
  's = s.replace("    if not declared:", "    if False:")'

# The opposite direction, and the one that gets the checker switched off. The
# workflow discusses several tools in prose, including one it deliberately does
# not wire; a scanner that matched comment text would report the reverse of the
# truth about that one on every push.
#
# The trailing `for reference` line is part of the match and is what keeps this
# naming one site. `coverage()` skips comments with a byte-identical two-line
# block, and from 2026-08-12 the shorter string was AMBIGUOUS at 2 occurrences
# — which the tamper matcher reports as an error rather than silently patching
# the first, and this is the anchor it made re-derive.
proof "census — comments are scanned, so prose about a tool reads as wiring" \
  tools/instruments.py \
  "tests/unit/test_instrument_census.py::test_a_reference_inside_a_comment_is_not_reported" \
  's = s.replace("            if line.lstrip().startswith(\x22#\x22):\n                continue\n            for reference in references(line):", "            for reference in references(line):")'

# The 2026-08-12 widening, five arms because it is five mechanisms failing in
# five directions. Direction 2 read a file-shaped pattern only, so `python -m
# mypy`, all three `python -m pytest` invocations and `go vet`/`go test`/`go
# build` were invisible to it while `--check` printed "every instrument the
# workflow runs is declared" — a clean bit over a population nobody had
# measured. The first three arms remove a form the widening added; the last two
# remove the anchor, which is the entire reason the widening was taken rather
# than declined. `tools/instruments.py` is a gate instrument **and** is directly
# exercised by `tests/unit/test_instrument_census.py`, so a pytest-scored proof
# of it is not the vacuous shape a proof of a corpus-checker helper would be:
# pytest is blind to those, and it is not blind to this.

proof "census — a module-form gate wired into CI is not reported" \
  tools/instruments.py \
  "tests/unit/test_instrument_census.py::test_a_module_form_gate_missing_from_the_census_is_reported" \
  's = s.replace("    found.extend(_MODULE.findall(head))", "    pass")'

proof "census — a Go-subcommand gate wired into CI is not reported" \
  tools/instruments.py \
  "tests/unit/test_instrument_census.py::test_a_go_subcommand_gate_missing_from_the_census_is_reported" \
  's = s.replace("    found.extend(f\x22go {sub}\x22 for sub in _GO.findall(head))", "    pass")'

# `specs/` is the alternative that caught a real one: the `slug-differential`
# job has always run a harness there and no census entry named it.
proof "census — a harness under specs/ wired into CI is not reported" \
  tools/instruments.py \
  "tests/unit/test_instrument_census.py::test_a_specs_harness_missing_from_the_census_is_reported" \
  's = s.replace("(?:tests|specs)/", "(?:tests)/")'

# The anchor, both halves. Unanchored, the Go matcher fires 7 times over
# `ci.yml`'s job blocks and 4 are false — a job's own `name:` and three `echo`
# lines whose prose says `go test`. A matcher that reads prose as wiring is the
# failure `tools/README.md` opens with, and it is worse than the gap it closes.
proof "census — the Go matcher reads prose saying go test as an invocation" \
  tools/instruments.py \
  "tests/unit/test_instrument_census.py::test_the_go_matcher_does_not_fire_on_prose_that_says_go_test" \
  's = s.replace("_GO = re.compile(r\x22^go", "_GO = re.compile(r\x22go")'

proof "census — the module matcher reads prose saying python -m as an invocation" \
  tools/instruments.py \
  "tests/unit/test_instrument_census.py::test_the_module_matcher_does_not_fire_on_prose_that_says_python_dash_m" \
  's = s.replace("_MODULE = re.compile(r\x22^python3?", "_MODULE = re.compile(r\x22python3?")'

# The anchor is only reachable because the YAML `run:` key is stripped first.
# Without it `run: go vet ./...` is not at a command position and the Go matcher
# finds 1 of 3 — a silent two-thirds loss, with the census still green.
proof "census — the run: key is not stripped, so a one-line step is invisible" \
  tools/instruments.py \
  "tests/unit/test_instrument_census.py::test_the_run_key_is_stripped_so_a_one_line_step_is_at_a_command_position" \
  's = s.replace("    text = _RUN_KEY.sub(\x22\x22, line.strip(), count=1)", "    text = line.strip()")'

proof "census — a new unclassified tool is not reported" \
  tools/instruments.py \
  "tests/unit/test_instrument_census.py::test_an_unclassified_entry_point_is_reported" \
  's = s.replace("        if candidate not in named:", "        if False:")'

# The silent death. An empty candidate list satisfies direction 3 for every
# input, and every other test in the file passes over it: the planted case
# supplies its own candidates, and the committed tree reconciles either way.
proof "census — the entry-point scan looks nowhere and finds nothing" \
  tools/instruments.py \
  "tests/unit/test_instrument_census.py::test_the_entry_point_scan_reads_the_filesystem" \
  's = s.replace("    found = [\n        f\x22tools/{path.name}\x22\n        for path in sorted((REPO / \x22tools\x22).glob(\x22*.py\x22))\n    ]", "    found = []")'

# ---------------------------------------------------------------------------
# T073–T076 — admission (FR-044, SC-018).
#
# SC-018 asserts a SHARE — "100% of non-admissible targets are rejected" — over
# a population the test itself assembles, which is Rule 8's shape twice over: it
# is trivially true over an empty population, and trivially true if the
# rejection arrived from somewhere other than the classifier. So the arms below
# are three different questions and not one:
#
#   (a) MISCLASSIFICATION arms fold one state into a plausible neighbour and
#       require the fixture set to notice. The tampered classifier still
#       rejects — `absent` is a rejection too — so a test that only checked
#       "was it refused" passes every one of them. They are the arms that
#       distinguish "names a state" from "names the right state", which is what
#       FR-044's remedy text hangs on: telling an operator to publish a
#       specification they already publish is a wrong answer, not a coarse one.
#
#   (b) GATE arms remove the refusal and the ordering separately. A gate that
#       refuses after running the work is not a gate, and no arm that only
#       counts refusals can tell the two apart.
#
#   (c) INSTRUMENT arms remove the population floor and the control loop. These
#       are the two that would leave every other arm above green while the
#       measurement covered nothing — the fixture set shrunk to the admissible
#       cases makes "100% of non-admissible targets rejected" true over zero
#       targets, and an empty mutation table makes the controls stop
#       distinguishing "admitted for the stated reason" from "admitted".

# (a) One state folded into its neighbour, per state. Each names the ONE
# fixture whose expected output moves, so an arm that passed because a
# different case failed would be reported against the wrong mechanism.
proof "FR-044 — an empty specification read as an absent one" \
  src/analysis/admission.py \
  "tests/contract/test_admission.py::test_zero_are_admitted_on_a_specification_that_fetched_and_carried_no_operations" \
  's = s.replace("            state=READABLE_NO_OPERATIONS, operations=(),", "            state=ABSENT, operations=(),")'

proof "FR-044 — a refused credential read as an absent specification" \
  src/analysis/admission.py \
  "tests/contract/test_admission.py::test_a_refused_credential_is_not_reported_as_an_absent_specification" \
  's = s.replace("    if response.status in (401, 403, 407):", "    if False:")'

proof "FR-044 — an origin that never answered read as one that publishes nothing" \
  src/analysis/admission.py \
  "tests/contract/test_admission.py::test_an_origin_that_never_answered_is_not_reported_as_publishing_nothing" \
  's = s.replace("    if response.status >= 500:", "    if False:")'

# The one that reports the wrong thing to the operator rather than merely a
# coarser thing: an unsupported shape returned as an empty operation list says
# "your specification is empty" about a document nobody managed to read.
proof "FR-053 — an unsupported shape returned as an empty operation list" \
  src/analysis/admission.py \
  "tests/contract/test_admission.py::test_an_unsupported_shape_is_not_reported_as_an_empty_specification" \
  's = s.replace("    operations = document.get(\x22operations\x22)", "    operations = document.get(\x22operations\x22) or []")'

# Finding 032's defect, in this classifier: an outcome whose accepting set is
# "none of the others" swallows every shape nobody enumerated.
proof "FR-044 — the classifier given a default state instead of a refusal" \
  src/analysis/admission.py \
  "tests/contract/test_admission.py::test_an_unenumerated_status_is_refused_rather_than_defaulted" \
  's = s.replace("    if response.status != 200:\n        raise UnclassifiableResponse(", "    if response.status != 200:\n        return Classification(state=ABSENT, operations=(), evidence=\x22defaulted\x22)\n    if False:\n        raise UnclassifiableResponse(")'

# The credential is the one input that must not end up in the recorded
# location, and the arm has to move what is RECORDED, not only what is sent —
# a tamper that changed the request and left `location` alone would leave the
# assertion satisfied and prove nothing.
proof "FR-044 — the credential moved from a header into the URL that gets recorded" \
  src/analysis/admission.py \
  "tests/contract/test_admission.py::test_the_credential_never_reaches_the_url" \
  's = s.replace("    if credential:\n        request.add_header(\x22Authorization\x22, f\x22Bearer {credential}\x22)", "    if credential:\n        url = url + \x22?token=\x22 + credential\n        request = urllib.request.Request(url, method=\x22GET\x22)")'

proof "FR-044 — a file the process may not read reported as a file that is not there" \
  src/analysis/admission.py \
  "tests/contract/test_admission.py::test_the_file_transport_reports_the_three_filesystem_outcomes" \
  's = s.replace("    except PermissionError:\n        return FetchResponse(status=403, body=None, location=location)", "    except PermissionError:\n        return FetchResponse(status=404, body=None, location=location)")'

# (b) The gate. Two arms, because "did not start" and "did not start it first"
# are different claims and one test cannot separate them.
proof "FR-044 gate — the refusal removed, so a non-admissible target reaches a session" \
  src/analysis/admission.py \
  "tests/contract/test_admission.py::test_zero_non_admissible_targets_reach_an_agent_session" \
  's = s.replace("    if not decision.admitted:\n        raise NotAdmitted(decision)\n    return start()", "    return start()")'

proof "FR-044 gate — the session started first and refused afterwards" \
  src/analysis/admission.py \
  "tests/contract/test_admission.py::test_the_gate_evaluates_nothing_before_it_refuses" \
  's = s.replace("    if not decision.admitted:\n        raise NotAdmitted(decision)\n    return start()", "    outcome = start()\n    if not decision.admitted:\n        raise NotAdmitted(decision)\n    return outcome")'

# T074's two record guards, separately. One combined guard would be satisfied
# by either half and neither arm below could say which half it removed.
proof "T074 — a rejection recorded with nothing an operator can act on" \
  src/analysis/admission_record.py \
  "tests/contract/test_admission.py::test_a_rejection_record_without_a_remedy_cannot_be_constructed" \
  's = s.replace("        if not self.admitted and not self.operator_action:", "        if False:")'

proof "T074 — an admitted record carrying an outstanding remedy" \
  src/analysis/admission_record.py \
  "tests/contract/test_admission.py::test_an_admitted_record_carrying_a_remedy_cannot_be_constructed" \
  's = s.replace("        if self.admitted and self.operator_action:", "        if False:")'

proof "T074 — a record whose disposition disagrees with its own state" \
  src/analysis/admission_record.py \
  "tests/contract/test_admission.py::test_a_record_cannot_disagree_with_its_own_state" \
  's = s.replace("        if self.admitted != (self.specification_state in ADMISSIBLE_STATES):", "        if False:")'

proof "T074 — a pre-1.1.0 record read back as though it had named a state" \
  src/analysis/admission_record.py \
  "tests/contract/test_admission.py::test_a_pre_1_1_0_record_is_refused_rather_than_read_as_a_classification" \
  's = s.replace("        if state is None:", "        if False:")'

proof "FR-054 migration — a state invented for a decision no classifier ever made" \
  src/contracts/migrations/__init__.py \
  "tests/contract/test_admission.py::test_the_migration_does_not_invent_a_state_a_1_0_0_record_never_named" \
  's = s.replace("        \x22specification_state\x22: document.get(\x22specification_state\x22),", "        \x22specification_state\x22: document.get(\x22specification_state\x22, \x22absent\x22) or \x22absent\x22,")'

proof "FR-044 — a rejected classification handing back an operation list" \
  src/analysis/admission.py \
  "tests/contract/test_admission.py::test_a_rejected_classification_cannot_carry_an_operation_list" \
  's = s.replace("        if self.state != PUBLISHED_NON_EMPTY and self.operations:", "        if False:")'

proof "FR-044 — the admitted state recordable with no operations under it" \
  src/analysis/admission.py \
  "tests/contract/test_admission.py::test_the_admitted_state_cannot_be_recorded_with_no_operations" \
  's = s.replace("        if self.state == PUBLISHED_NON_EMPTY and not self.operations:", "        if False:")'

# (c) The instrument. These two are the reason the arms above mean anything:
# with the population emptied of rejections or the control table emptied of
# mutations, every arm above still passes and SC-018 is measured over nothing.
proof "SC-018 instrument — the population loses its non-admissible cases, so 100% is free" \
  tests/fixtures/admission/__init__.py \
  "tests/contract/test_admission.py::test_the_fixture_set_covers_every_state_the_requirement_names" \
  's = s.replace("    return tuple(cases)", "    return tuple(c for c in cases if c.expected_admitted)")'

proof "SC-018 instrument — the controls attempt no mutation, so 'admissible for the stated reason' is free" \
  tests/contract/test_admission.py \
  "tests/contract/test_admission.py::test_every_admissible_case_is_admissible_for_the_stated_reason" \
  's = s.replace("        for label, override, expected in MUTATIONS:", "        for label, override, expected in MUTATIONS[:0]:")'

# ---------------------------------------------------------------------------
# T077 — the served-operation set (FR-002, OD-06).
#
# The version and the freshness are the two things T077 adds over an operation
# list, and each is removable in a way that leaves a set which still looks like
# a set. The other three arms are the refusals that keep an unusable set from
# being constructed at all.

proof "FR-002 set version — the version stops being a function of the served surface" \
  src/analysis/served_operations.py \
  "tests/contract/test_served_operations.py::test_the_set_version_moves_for_any_change_to_the_served_surface" \
  's = s.replace("    return content_address([dict(operation) for operation in operations])", "    return content_address([])")'

proof "FR-002 set version — a version the target published is believed instead of computed" \
  src/analysis/served_operations.py \
  "tests/contract/test_served_operations.py::test_a_stored_set_version_that_disagrees_with_its_operations_is_refused" \
  's = s.replace("        if stored is not None and stored != built.set_version:", "        if False:")'

proof "T077 freshness — a set with no capture instant is constructible" \
  src/analysis/served_operations.py \
  "tests/contract/test_served_operations.py::test_a_set_with_no_capture_time_is_refused" \
  's = s.replace("        if not self.captured_at:", "        if False:")'

proof "FR-002 — a duplicated operation id makes one entry unaddressable, unnoticed" \
  src/analysis/served_operations.py \
  "tests/contract/test_served_operations.py::test_a_duplicated_operation_id_is_refused" \
  's = s.replace("            if operation.operation_id in seen:", "            if False:")'

proof "OD-06 ordering — a set is built for a target FR-044 refused" \
  src/analysis/served_operations.py \
  "tests/contract/test_served_operations.py::test_a_target_admission_refused_produces_no_set" \
  's = s.replace("        if decision.state not in ADMISSIBLE_STATES:", "        if False:")'

proof "T014 migration — the recovered set version is invented instead of recomputed" \
  src/contracts/migrations/__init__.py \
  "tests/contract/test_served_operations.py::test_the_migration_recovers_the_set_version_rather_than_inventing_one" \
  's = s.replace("        \x22set_version\x22: set_version_of(document.get(\x22operations\x22) or ()),", "        \x22set_version\x22: \x22unknown\x22,")'

# ---------------------------------------------------------------------------
# T078 — the correspondence declaration (FR-057).
#
# The first arm is the requirement itself: FR-057 records a declaration and
# never a verified fact, so the mechanism being proved is a refusal that has no
# success path. The other two are the fail-closed limbs, each paired in the
# test file with a non-coverage arm showing the layer above accepts what it
# refuses — which is what makes them removable rather than doubly covered.

proof "FR-057 — verified correspondence becomes obtainable" \
  src/analysis/correspondence.py \
  "tests/contract/test_correspondence.py::test_asking_for_verified_correspondence_always_refuses" \
  's = s.replace("    raise CorrespondenceNotEstablished(", "    if declaration.reference.commit:\n        return\n    raise CorrespondenceNotEstablished(")'

proof "FR-057 — a moving name is accepted as a clock anchor" \
  src/analysis/correspondence.py \
  "tests/contract/test_correspondence.py::test_a_branch_name_is_refused_rather_than_resolved" \
  's = s.replace("    if not _OBJECT_NAME.match(commit):", "    if False:")'

proof "FR-057 — a source reference is attachable with no declared marking beside it" \
  src/analysis/correspondence.py \
  "tests/contract/test_correspondence.py::test_a_bare_reference_with_no_status_beside_it_is_refused" \
  's = s.replace("    if not status:", "    if False:")'

# ---------------------------------------------------------------------------
# T137 — the two clocks (FR-027, OD-06).
#
# FR-027 asks for the source-derived and deployment-derived artifacts as two
# INDEPENDENTLY versioned things, with drift detected in each SEPARATELY. Both
# halves are removable in ways that leave a module which still returns clock
# readings and still reports movement, so the arms below are grouped by which
# half they carry.
#
# Independence is held by `reading()` refusing a version for a kind that is not
# on the clock being read. That refusal is not hygiene: with it gone, a source
# reading can be built carrying the served surface, and the day the deployment
# moves while the source does not, both clocks report movement — which is the
# fused artifact OD-06 separated the stages to prevent, reassembled one layer up.
#
# The partition guards are three separate branches and not one, because they
# fail in three different directions and only the first is visible to a reader:
# a kind on both clocks, a drift-relevant kind on neither, and a kind on a clock
# that no drift channel reads. The middle one is the silent case — a detector
# iterating the clocks never visits it and nothing anywhere says so.

proof "T137 — a kind sits on both clocks, so *which clock moved* has two answers" \
  src/analysis/clocks.py \
  "tests/contract/test_clocks.py::test_a_kind_on_both_clocks_is_refused" \
  's = s.replace("            if kind in assigned:", "            if False:")'

proof "T137 — a kind drift reads sits on neither clock, so nothing reads it and nothing says so" \
  src/analysis/clocks.py \
  "tests/contract/test_clocks.py::test_a_kind_drift_reads_and_no_clock_reads_is_refused" \
  's = s.replace("    if unassigned:", "    if False:")'

proof "T137 — a clock reads a kind no drift channel publishes, so it moves for an uncovered cause" \
  src/analysis/clocks.py \
  "tests/contract/test_clocks.py::test_a_clock_kind_the_registry_does_not_read_for_drift_is_refused" \
  's = s.replace("    if unknown:", "    if False:")'

# The independence mechanism itself.
proof "T137 — a deployment version enters the source clock's reading, so one change moves both" \
  src/analysis/clocks.py \
  "tests/contract/test_clocks.py::test_a_deployment_version_is_refused_on_the_source_clock" \
  's = s.replace("    if foreign:", "    if False:")'

proof "T137 — a clock is read over a subset of its kinds, so it is silent for what it skipped" \
  src/analysis/clocks.py \
  "tests/contract/test_clocks.py::test_a_clock_read_over_a_subset_of_its_kinds_is_refused" \
  's = s.replace("    if missing:", "    if False:")'

proof "T137 — a blank version is admitted, so two uncomputed readings compare equal" \
  src/analysis/clocks.py \
  "tests/contract/test_clocks.py::test_a_blank_version_is_refused" \
  's = s.replace("    if blank:", "    if False:")'

proof "T137 — the source clock is read with no anchor, so a signal cannot say which source moved" \
  src/analysis/clocks.py \
  "tests/contract/test_clocks.py::test_the_source_clock_is_refused_with_no_anchor" \
  's = s.replace("    if clock == SOURCE and not (source_ref or \x22\x22).strip():", "    if False:")'

proof "T137 — the deployment clock is anchored to a commit, putting the two clocks in one field" \
  src/analysis/clocks.py \
  "tests/contract/test_clocks.py::test_the_deployment_clock_is_refused_with_an_anchor" \
  's = s.replace("    if clock == DEPLOYMENT and source_ref is not None:", "    if False:")'

proof "T137 — a clock name outside the two is accepted, so movement is attributed to nothing" \
  src/analysis/clocks.py \
  "tests/contract/test_clocks.py::test_a_third_clock_is_refused" \
  's = s.replace("    if clock not in KINDS_ON_CLOCK:", "    if False:")'

proof "T137 — a reading is taken for no deployment, so FR-031's identity term has no source" \
  src/analysis/clocks.py \
  "tests/contract/test_clocks.py::test_a_reading_for_no_deployment_is_refused" \
  's = s.replace("    if not deployment_id:", "    if False:")'

# Separate detection. The comparison is where *separately* is either honoured or
# quietly lost, and the last arm here is the detector-never-fires failure rather
# than a false alarm: with the difference test gone every clock reads unmoved
# forever, which is the one outcome a drift detector must never produce silently.
proof "T137 — the two clocks are compared against each other, so a system at rest reports drift" \
  src/analysis/clocks.py \
  "tests/contract/test_clocks.py::test_the_two_clocks_are_not_comparable_against_each_other" \
  's = s.replace("    if before.clock != after.clock:", "    if False:")'

proof "T137 — two deployments are compared on one clock, so a difference between targets reads as movement" \
  src/analysis/clocks.py \
  "tests/contract/test_clocks.py::test_two_deployments_are_not_comparable_on_one_clock" \
  's = s.replace("    if before.deployment_id != after.deployment_id:", "    if False:")'

proof "T137 — a clock absent from one side is reported as unmoved rather than unread" \
  src/analysis/clocks.py \
  "tests/contract/test_clocks.py::test_a_clock_absent_from_one_side_is_not_reported_as_unmoved" \
  's = s.replace("        if absent:", "        if False:")'

proof "T137 — the version comparison stops discriminating, so no clock ever moves" \
  src/analysis/clocks.py \
  "tests/contract/test_clocks.py::test_a_deployment_change_moves_the_deployment_clock_only" \
  's = s.replace("        if before_versions.get(kind) != after_versions.get(kind)", "        if False")'

# The two clocks composed from versions that already exist, rather than from two
# new hash functions. The first arm is the T077 proof above, one level down: with
# the served surface unread, every deployment reading carries one version and the
# clock stops being a function of what the target serves.
proof "T137 — the deployment clock stops reading the served surface, so every capture reads the same" \
  src/analysis/clocks.py \
  "tests/contract/test_clocks.py::test_the_deployment_clock_reads_the_version_t077_defines" \
  's = s.replace("        versions={\x22served_operation_set\x22: set_version_of(operations)},", "        versions={\x22served_operation_set\x22: set_version_of(())},")'

proof "T137 — the declared anchor is hashed into the source clock, so re-declaring configuration reports drift" \
  src/analysis/clocks.py \
  "tests/contract/test_clocks.py::test_the_anchor_is_beside_the_version_and_not_inside_it" \
  's = s.replace("        return content_address({kind: value for kind, value in self.versions})", "        return content_address({\x22source_ref\x22: self.source_ref, **{kind: value for kind, value in self.versions}})")'

# ---------------------------------------------------------------------------
# T139 and T140 — the drift signal, as a sum over two shapes (FR-031, FR-047).
#
# FR-031 requires every drift signal to state which clock moved, the versions
# before and after, and the deployment identity. FR-047 narrows it: a failed
# re-fetch has no *after* version "because no artifact was obtained", and the
# after term becomes FR-044's specification state plus the timestamp of the last
# successful fetch. Two shapes, one requirement.
#
# THE THREE ARMS THAT CARRY THE TYPE CHOICE are the last three in this block,
# and they are the reason the rest exist at all. The cheap encoding is one
# record with `version_after: str | None`, and it passes every field-presence
# test ever written: a `None` there cannot be told apart from a field nobody
# filled in, which is this repository's recorded worst defect class — the
# wall-clock numerator, and `spend_usd: float | None` holding UNPRICED apart
# from COST NOTHING. So those three tampers do not remove a guard. They ADD the
# optional field back, at the type, at the serialized document, and at the
# discriminant that tells a reader which shape it is holding. Each restores the
# ambiguity at a different layer, and each turns exactly one test red.
#
# The refusal arms above them are grouped by which shape they guard. Two are
# worth naming: the successful-fetch refusal is what stops the two arms of the
# sum from overlapping through the VALUE domain after the type system closed
# the structural route, and the naive-timestamp refusal guards the failure that
# produces an answer rather than an error — an age computed from a naive instant
# is compared against FR-047's ceiling and believed.

proof "T139 — a drift signal is raised on a clock outside the two, attributing movement to nothing" \
  src/analysis/drift_signal.py \
  "tests/contract/test_drift_signal.py::test_a_signal_on_a_third_clock_is_refused" \
  's = s.replace("        if self.clock not in CLOCKS:", "        if False:")'

proof "T139 — a drift signal states no deployment identity, so FR-030's responder cannot say whose" \
  src/analysis/drift_signal.py \
  "tests/contract/test_drift_signal.py::test_a_signal_for_no_deployment_is_refused" \
  's = s.replace("        if not self.deployment_id:", "        if False:")'

proof "T139 — a signal carries one version as both before and after, reporting drift and stating none" \
  src/analysis/drift_signal.py \
  "tests/contract/test_drift_signal.py::test_a_signal_whose_two_versions_are_equal_is_refused" \
  's = s.replace("        if self.version_before == self.version_after:", "        if False:")'

proof "T139 — a signal names no artifact kind as moved, so it was not built from a comparison" \
  src/analysis/drift_signal.py \
  "tests/contract/test_drift_signal.py::test_a_signal_naming_no_moved_kind_is_refused" \
  's = s.replace("        if not self.kinds_moved:", "        if False:")'

proof "T139 — a signal is raised for a clock that did not move, which is drift on a system at rest" \
  src/analysis/drift_signal.py \
  "tests/contract/test_drift_signal.py::test_a_signal_from_an_unmoved_clock_is_refused" \
  's = s.replace("        if not movement.moved:", "        if False:")'

# The phase's Independent Test names this negative outright: re-analysing
# unchanged input produces no signal at all. `compare_each` returns one movement
# per clock whether or not it moved, so the filter is the whole mechanism — with
# it gone every run of a system where nothing changed reports drift on both
# clocks, and every downstream count of operations disabled is then measured
# against a detector that always fires.
proof "T139 — every clock emits a signal every run, so unchanged input reports drift on both" \
  src/analysis/drift_signal.py \
  "tests/contract/test_drift_signal.py::test_unchanged_input_produces_no_signal_at_all" \
  's = s.replace("for movement in movements if movement.moved", "for movement in movements if True")'

# T140's value-domain guard, and it is the counterpart of the structural ones
# below. `published_non_empty` is a fetch that WORKED; recording it in the shape
# that means *no artifact was obtained* makes the two arms of the sum overlap,
# so a success and a failure become indistinguishable — the same collapse the
# optional field causes, arriving through the value domain instead of the type.
proof "T140 — a successful fetch is recorded in the shape meaning no artifact was obtained" \
  src/analysis/drift_signal.py \
  "tests/contract/test_drift_signal.py::test_a_successful_fetch_is_refused_in_the_failed_refetch_shape" \
  's = s.replace("        if self.specification_state in ADMISSIBLE_STATES:", "        if False:")'

proof "T140 — a string no classifier produces is recorded as the specification state found" \
  src/analysis/drift_signal.py \
  "tests/contract/test_drift_signal.py::test_a_state_no_classifier_produces_is_refused" \
  's = s.replace("        if self.specification_state not in SPECIFICATION_STATE_FOUND:", "        if False:")'

proof "T140 — a failed re-fetch is attributed to the source clock, where there is nothing to re-fetch" \
  src/analysis/drift_signal.py \
  "tests/contract/test_drift_signal.py::test_a_failed_refetch_from_a_source_reading_is_refused" \
  's = s.replace("    if before.clock != DEPLOYMENT:", "    if False:")'

proof "T140 — an unparseable last-successful-fetch yields an age of zero instead of a refusal" \
  src/analysis/drift_signal.py \
  "tests/contract/test_drift_signal.py::test_an_unparseable_last_successful_fetch_is_refused" \
  's = s.replace("    except ValueError:", "    except ValueError:\n        return 0.0")'

proof "T140 — a naive last-successful-fetch is admitted, so FR-047's ceiling is measured in an unrecorded offset" \
  src/analysis/drift_signal.py \
  "tests/contract/test_drift_signal.py::test_a_naive_last_successful_fetch_is_refused" \
  's = s.replace("    if parsed.tzinfo is None:", "    if False:")'

# The three that carry the type choice. Each ADDS the product type back at a
# different layer rather than removing a guard.
proof "T140 — the narrowed shape regains an optional after version, collapsing no-artifact into nobody-filled-it-in" \
  src/analysis/drift_signal.py \
  "tests/contract/test_drift_signal.py::test_the_narrowed_shape_has_no_after_version_attribute" \
  's = s.replace("    last_successful_fetch: str\n", "    last_successful_fetch: str\n    version_after: str | None = None\n")'

proof "T140 — the narrowed record serializes a null after version, restoring the ambiguity at the boundary" \
  src/analysis/drift_signal.py \
  "tests/contract/test_drift_signal.py::test_the_narrowed_document_carries_no_after_version_key" \
  's = s.replace("            \x22specification_state\x22: self.specification_state,", "            \x22version_after\x22: None,\n            \x22specification_state\x22: self.specification_state,")'

proof "T139/T140 — the discriminant is dropped, so which shape a record is must be inferred from missing keys" \
  src/analysis/drift_signal.py \
  "tests/contract/test_drift_signal.py::test_the_two_documents_are_distinguishable_by_an_explicit_discriminant" \
  's = s.replace("            \x22signal_kind\x22: FAILED_REFETCH,\n", "")'

# ---------------------------------------------------------------------------
# T138 — source-drift detection in the same automated check run (FR-028, SC-008).
#
# FR-028 detects a source change that INVALIDATES a derived contract, in the
# same analysis run as the commit. Two cheap detectors would score SC-008
# perfectly and both are wrong: fire on every source-clock move (C-005/C-006/
# C-007 all move the contract hash), and fire on the whole commit as one blob
# (C-010 carries a breaking change and a non-breaking one). The arms below
# remove the filters that stop those, and the comparison T137 already owns is
# not re-stated — a second version_before != version_after here could disagree
# with compare_each, so the proofs target the SOURCE slice, the invalidation
# filter, and the operation list, not the clock comparison.
#
# The SOURCE slice is Movement.clock == SOURCE, not schemas.source_derived.
# That flag is the union of both clocks; served_operation_set is flagged
# source_derived=True and is the deployment-derived artifact. Filtering on it
# would report a deployment-clock move as source drift.

proof "T138 — a deployment-clock movement is kept as a source-clock movement" \
  src/analysis/source_drift.py \
  "tests/contract/test_source_drift.py::test_a_deployment_clock_move_is_not_source_drift" \
  's = s.replace("        if movement.clock == SOURCE", "        if True")'

proof "T138 — a non-breaking contract change still raises a source-drift finding" \
  src/analysis/source_drift.py \
  "tests/contract/test_source_drift.py::test_a_detector_that_fires_on_a_signature_change_fails_this_corpus" \
  's = s.replace("    if not invalidated:", "    if False:")'

proof "T138 — a breaking diff against an unmoved source clock is reported as a quiet miss" \
  src/analysis/source_drift.py \
  "tests/contract/test_source_drift.py::test_a_breaking_diff_against_an_unmoved_clock_is_refused" \
  's = s.replace("    if not signals:", "    if False:")'

proof "T138 — an operation touched only by a non-breaking kind is named as drifted" \
  src/analysis/source_drift.py \
  "tests/contract/test_source_drift.py::test_drifted_operations_ignores_operations_touched_only_by_a_non_breaking_kind" \
  's = s.replace("        op_id for kind, op_id in diff if kind in BREAKING_KINDS", "        op_id for kind, op_id in diff if True")'

proof "T138 — an unknown change kind is classified rather than refused" \
  src/analysis/source_drift.py \
  "tests/contract/test_source_drift.py::test_an_unknown_change_kind_is_refused" \
  's = s.replace("    if unknown:", "    if False:")'

proof "T138 — a source-drift finding is accepted on the deployment clock" \
  src/analysis/source_drift.py \
  "tests/contract/test_source_drift.py::test_a_finding_on_the_deployment_clock_is_refused" \
  's = s.replace("        if self.signal.clock != SOURCE:", "        if False:")'

# ---------------------------------------------------------------------------
# T141 / T142 — the deployment-clock scheduler, and the one peer it may dial.
#
# T141 produces ArtifactDrift / FailedRefetch from a scheduled re-fetch. T142
# is the peer check: a transport that dials the origin is the second continuous
# path T-10 exists to prevent. INV-003 cannot catch that path on its own —
# admission.fetch_over_http is not under SANDBOX_ROOTS — so the peer comparison
# is the live arm, and its proof is the origin-dialing transport being accepted
# once the comparison is gone.
#
# The DEPLOYMENT filter is Movement.clock == DEPLOYMENT, not
# schemas.source_derived. That flag is the union of both clocks; filtering on
# it would report a source-clock move as deployment drift, the inverse of the
# T138 trap.

proof "T142 — a transport that dials the origin is accepted as the scheduled fetch" \
  src/runtime/drift/scheduler.py \
  "tests/contract/test_drift_scheduler.py::test_a_transport_that_dials_the_origin_is_refused" \
  's = s.replace("        if origin_of(fetched.peer) != self.enforcement_point:", "        if False:")'

proof "T141 — a source-clock movement is kept as a deployment-clock movement" \
  src/runtime/drift/scheduler.py \
  "tests/contract/test_drift_scheduler.py::test_a_source_clock_move_is_not_deployment_drift" \
  's = s.replace("if movement.clock == DEPLOYMENT", "if True")'

proof "T141 — a non-admissible fetch is compared as an ArtifactDrift" \
  src/runtime/drift/scheduler.py \
  "tests/contract/test_drift_scheduler.py::test_a_non_admissible_fetch_is_a_failed_refetch" \
  's = s.replace("        if classification.state not in ADMISSIBLE_STATES:", "        if False:")'

proof "T141 — a source-clock last-successful reading is accepted" \
  src/runtime/drift/scheduler.py \
  "tests/contract/test_drift_scheduler.py::test_a_source_clock_last_successful_is_refused" \
  's = s.replace("        if last_successful.clock != DEPLOYMENT:", "        if False:")'

proof "T142 — an Authorization header is forwarded toward the target" \
  src/runtime/drift/scheduler.py \
  "tests/contract/test_drift_scheduler.py::test_an_authorization_header_is_refused" \
  's = s.replace("        if any(name.lower() == \"authorization\" for name in fetched.request_headers):", "        if False:")'

proof "T142 — a scheduler with no enforcement point is constructed" \
  src/runtime/drift/scheduler.py \
  "tests/contract/test_drift_scheduler.py::test_an_empty_enforcement_point_is_refused" \
  's = s.replace("        if not enforcement_point.strip():", "        if False:")'

# ---------------------------------------------------------------------------
# T143 / T144 — on-demand either clock, and the two additional triggers.
#
# The Plane A refusal stays in scheduler.py (T142's proofs). These arms are
# the new guards: mixing the two inputs, recording trigger=manual rather than
# scheduled, not assuming a pipeline event, and refusing path-level probe as
# a trigger. Session-start is a callable, not a loop.py call site.

proof "T143 — a transport is accepted on the source-clock on-demand path" \
  src/runtime/drift/manual.py \
  "tests/contract/test_drift_manual.py::test_a_transport_on_the_source_clock_path_is_refused" \
  's = s.replace("        if scheduler is not None:", "        if False:")'

proof "T143 — artifacts are accepted on the deployment-clock on-demand path" \
  src/runtime/drift/manual.py \
  "tests/contract/test_drift_manual.py::test_artifacts_on_the_deployment_clock_path_are_refused" \
  's = s.replace("        if before is not None or after is not None:", "        if False:")'

proof "T143 — a manual deployment check records trigger=scheduled" \
  src/runtime/drift/manual.py \
  "tests/contract/test_drift_manual.py::test_a_manual_check_runs_when_a_tick_is_not_due" \
  's = s.replace("return scheduler.tick(now=now, trigger=MANUAL)", "return scheduler.tick(now=now, trigger=\"scheduled\")")'

proof "T143 — a breaking source revision is quiet on demand" \
  src/runtime/drift/manual.py \
  "tests/contract/test_drift_manual.py::test_every_breaking_revision_is_detected_on_demand" \
  's = s.replace("        finding=finding,", "        finding=None,")'

proof "T144 — an unconfigured deployment event is honoured as a trigger" \
  src/runtime/drift/triggers.py \
  "tests/contract/test_drift_triggers.py::test_an_unconfigured_deployment_event_is_refused" \
  's = s.replace("        if not self._selection.deployment_event:", "        if False:")'

proof "T144 — an unconfigured session-start re-check is honoured as a trigger" \
  src/runtime/drift/triggers.py \
  "tests/contract/test_drift_triggers.py::test_an_unconfigured_session_start_is_refused" \
  's = s.replace("        if not self._selection.session_start:", "        if False:")'

proof "T144 — a deployment event records trigger=scheduled" \
  src/runtime/drift/triggers.py \
  "tests/contract/test_drift_triggers.py::test_a_configured_deployment_event_re_fetches_through_plane_a" \
  's = s.replace("return self._scheduler.tick(now=now, trigger=EVENT)", "return self._scheduler.tick(now=now, trigger=\"scheduled\")")'

proof "T144 — a session-start check records trigger=scheduled" \
  src/runtime/drift/triggers.py \
  "tests/contract/test_drift_triggers.py::test_a_configured_session_start_is_a_deployment_clock_re_fetch" \
  's = s.replace("return self._scheduler.tick(now=now, trigger=SESSION_START)", "return self._scheduler.tick(now=now, trigger=\"scheduled\")")'

proof "T144 — path-level probe is accepted as a trigger" \
  src/runtime/drift/scheduler.py \
  "tests/contract/test_drift_triggers.py::test_path_level_probe_is_refused_as_a_trigger" \
  's = s.replace("        if trigger not in ALLOWED_TRIGGERS:", "        if False:")'

# ---------------------------------------------------------------------------
# T147–T152 — the stale last-known-good set. One module, eight arms.
#
# Entering is five states (classifier minus admissible), not FR-047's three:
# subtracting unreachable is the disposition going the other way. The ceiling
# is wall-clock from the last successful fetch, not 3600. T148 stamps STALE
# rather than constructing a Result. T150 names the ceiling, not
# unrecoverable_fault. Restore past the ceiling is admission, not tick;
# recover below it is restore. A restore that changed must evaluate as drift.

proof "T147 — unreachable is excluded from the entering-stale domain" \
  src/runtime/staleness.py \
  "tests/contract/test_staleness.py::test_unreachable_enters_stale_on_the_same_rule_as_absent" \
  's = s.replace("ENTERING_STATES: frozenset[str] = SPECIFICATION_STATE_FOUND", "ENTERING_STATES: frozenset[str] = SPECIFICATION_STATE_FOUND - frozenset((\"unreachable\", \"unparseable\"))")'

proof "T149 — the ceiling comparison is against 3600 seconds" \
  src/runtime/staleness.py \
  "tests/contract/test_staleness.py::test_lengthening_the_interval_does_not_widen_the_ceiling" \
  's = s.replace("    return age_seconds > ceiling_seconds", "    return age_seconds > 3600.0")'

proof "T148 — a stale set is stamped fresh on the caller-visible result" \
  src/runtime/staleness.py \
  "tests/contract/test_staleness.py::test_a_verified_result_can_be_stale" \
  's = s.replace("            StaleMarking.STALE,", "            StaleMarking.FRESH,")'

proof "T150 — a set past the ceiling may still be served" \
  src/runtime/staleness.py \
  "tests/contract/test_staleness.py::test_a_call_at_960s_is_denied_against_a_900s_ceiling" \
  's = s.replace("    return not crossed(state.age_seconds(now), ceiling.seconds)", "    return True")'

proof "T150 — an in-flight session past the ceiling ends as an unrecoverable fault" \
  src/runtime/staleness.py \
  "tests/contract/test_staleness.py::test_in_flight_terminal_names_the_staleness_ceiling_not_a_generic_fault" \
  's = s.replace("    return terminal.STALENESS_CEILING", "    return terminal.UNRECOVERABLE_FAULT")'

proof "T151 — restore past the ceiling is accepted as a tick" \
  src/runtime/staleness.py \
  "tests/contract/test_staleness.py::test_restore_past_the_ceiling_is_refused" \
  's = s.replace("    if crossed(state.age_seconds(now), ceiling.seconds):\n        raise StalenessError(\n            f\"{state.deployment_id}: the ceiling is crossed. Recovery past \"", "    if False:\n        raise StalenessError(\n            f\"{state.deployment_id}: the ceiling is crossed. Recovery past \"")'

proof "T152 — recovery below the ceiling is accepted as admission" \
  src/runtime/staleness.py \
  "tests/contract/test_staleness.py::test_recovery_below_the_ceiling_is_refused" \
  's = s.replace("    if not crossed(state.age_seconds(now), ceiling.seconds):", "    if False:")'

proof "T151 — a restore that changed the set is recorded as zero drift" \
  src/runtime/staleness.py \
  "tests/contract/test_staleness.py::test_changed_restore_below_the_ceiling_is_deployment_clock_drift" \
  's = s.replace("        signals=signals_from_movements((movement,)),", "        signals=(),")'

# ---------------------------------------------------------------------------
# T079 — FR-020's confused-deputy inspection, FR-056's procedure.
#
# Every arm here guards the same failure from a different side: a procedure
# that answers `clean` when it should decline. That is the failure that turns
# the inspection into a rubber stamp, and each of these four removals produces
# a version of it while leaving the whole suite otherwise green.

proof "FR-056 step 2 — an unresolvable call reads as the absence of an outbound request" \
  src/analysis/deputy_inspection.py \
  "tests/contract/test_deputy_inspection.py::test_a_handler_containing_only_an_unresolvable_call_is_not_clean" \
  's = s.replace("        if unresolvable:", "        if False:")'

proof "FR-056 step 3 — an untraceable destination passes as clean" \
  src/analysis/deputy_inspection.py \
  "tests/contract/test_deputy_inspection.py::test_an_untraceable_destination_declines_rather_than_passing" \
  's = s.replace("    if untraceable:", "    if False:")'

proof "FR-056 step 3 — an f-string with a hole counts as a build-time constant" \
  src/analysis/deputy_inspection.py \
  "tests/contract/test_deputy_inspection.py::test_an_f_string_with_an_untraceable_hole_is_not_a_build_time_constant" \
  's = s.replace("        return all(isinstance(part, ast.Constant) for part in node.values)", "        return True")'

proof "FR-056 step 3 — influence tracing stops before its fixed point" \
  src/analysis/deputy_inspection.py \
  "tests/contract/test_deputy_inspection.py::test_influence_is_traced_when_the_chain_is_not_in_walk_order" \
  's = s.replace("    changed = True\n    while changed:", "    changed = True\n    for changed in (True,):")'

proof "FR-056 — uninspectable stops being denied" \
  src/analysis/deputy_inspection.py \
  "tests/contract/test_deputy_inspection.py::test_only_clean_is_allowed" \
  's = s.replace("ALLOWED_OUTCOMES = frozenset({CLEAN})", "ALLOWED_OUTCOMES = frozenset({CLEAN, UNINSPECTABLE})")'

# ---------------------------------------------------------------------------
# T080 — FR-016 address pinning.
#
# The first arm is the positive form of "no per-request re-resolution": the
# pin's address is what a connection is made to, and removing that is exactly
# the edit that hands a name back to whatever dials. It is not a doubling of
# `src/proxy/addresses.go`'s `checkDialAddress` — that one refuses a name at
# the dial and this one stops a name being produced, and either can be deleted
# with the other still in place.

proof "FR-016 — the dial target reverts to the name, so the connection is resolved again" \
  src/analysis/pinning.py \
  "tests/contract/test_pinning.py::test_the_pinned_address_is_what_a_request_is_routed_to" \
  's = s.replace("        return (self.address, self.port)", "        return (self.host, self.port)")'

proof "FR-016 — a pin is allowed to hold a name instead of an address" \
  src/analysis/pinning.py \
  "tests/contract/test_pinning.py::test_a_pin_holding_a_name_is_refused" \
  's = s.replace("        if parsed is None:", "        if False:")'

proof "FR-016 — the port is defaulted rather than pinned, so host-and-port becomes host" \
  src/analysis/pinning.py \
  "tests/contract/test_pinning.py::test_an_authority_without_an_explicit_port_is_refused" \
  's = s.replace("    if not match:", "    if False:")'

proof "FR-016 — a literal destination is round-tripped through the resolver anyway" \
  src/analysis/pinning.py \
  "tests/contract/test_pinning.py::test_a_literal_destination_is_not_sent_to_the_resolver" \
  's = s.replace("    literal = _as_address(host)", "    literal = None if resolve(host) else _as_address(host)")'

proof "FR-016 — the sealed resolver answers instead of refusing, so a late resolve is silent" \
  src/analysis/pinning.py \
  "tests/contract/test_pinning.py::test_the_pin_holds_when_the_resolver_would_now_refuse_outright" \
  's = s.replace("        raise ReresolutionAttempted(", "        return []\n        raise ReresolutionAttempted(")'

proof "FR-016 — two pins for one authority coexist, so the destination is chosen at request time" \
  src/analysis/pinning.py \
  "tests/contract/test_pinning.py::test_two_pins_for_one_authority_are_refused" \
  's = s.replace("        if key in seen and seen[key] != destination.address:", "        if False:")'

# ---------------------------------------------------------------------------
# T081 — FR-010's rule set and deny list as versioned configuration.
#
# The first arm is the one that matters most in this file: a rule declaring an
# unsafe method safe resolves a write to `read_only`, and the enforcement point
# reads the tier this artifact carries, so nothing downstream could catch it.
# That is constitution Principle IV's *zero destructive-classified-as-read*, at
# the only place in the Python tree where it can be violated by data.

proof "FR-010 — an unsafe method admitted as a safe one, so a write resolves read-only" \
  src/analysis/effect_rules.py \
  "tests/contract/test_effect_rules.py::test_a_rule_cannot_declare_an_unsafe_method_safe" \
  's = s.replace("        if self.safe and self.matcher.method not in SAFE_METHODS:", "        if False:")'

# The second half of FR-010's first clause, separately: the guard above stops an
# unsafe method being *declared* safe, and this stops the tier ignoring the
# declaration. Either alone leaves a route from a write to `read_only`.
proof "FR-010 — the tier stops following the target's own safe declaration" \
  src/analysis/effect_rules.py \
  "tests/contract/test_effect_rules.py::test_an_operation_the_target_does_not_declare_safe_is_not_read_only" \
  's = s.replace("        return TIER_READ_ONLY if self.safe else TIER_REVERSIBLE_WRITE", "        return TIER_READ_ONLY")'

proof "FR-010 — a deny-list entry admitted at a permitted tier, so the list denies nothing" \
  src/analysis/effect_rules.py \
  "tests/contract/test_effect_rules.py::test_a_deny_entry_cannot_declare_a_permitted_tier" \
  's = s.replace("        if self.tier in PERMITTED_TIERS:", "        if False:")'

proof "FR-011 — one rule identifier answering to two entries, so a denial names nothing" \
  src/analysis/effect_rules.py \
  "tests/contract/test_effect_rules.py::test_one_identifier_may_not_answer_to_two_entries" \
  's = s.replace("            if previous is not None:", "            if False:")'

# FR-010's last sentence binds interfaces, and a stored artifact a consumer
# reads is one. The arm also holds the U-43 acknowledgement in place.
proof "FR-010 — the artifact stops saying it is a stated rule set and not a proof" \
  src/analysis/effect_rules.py \
  "tests/contract/test_effect_rules.py::test_the_document_says_it_is_a_stated_rule_set_and_not_a_proof" \
  's = s.replace("        \x22a stated rule set, not a proof (FR-010). The deny list is \x22", "        \x22the effect rule set. The deny list is \x22")'

# ---------------------------------------------------------------------------
# T082 — the review gate and its widening predicate.
#
# Five arms, and the reason there are five rather than one is that "an
# unreviewed rule set does not take effect" is an assertion about an absence:
# the gate can be defeated by admitting an approval that was never given, by
# accepting an approval given for different bytes, by accepting one given for
# the opposite direction of travel, or by the widening record it produces being
# a constant. Each is removed on its own below.

proof "FR-012 — the review check satisfied by nothing, so an unapproved version takes effect" \
  src/analysis/review_gate.py \
  "tests/contract/test_review_gate.py::test_an_approved_version_takes_effect_and_an_unapproved_one_does_not" \
  's = s.replace("        store.repo, proposal.kind, proposal.content_hash, CHANGE_PUBLICATION)", "        store.repo, proposal.kind, proposal.content_hash, CHANGE_PUBLICATION) or {\x22reviewer\x22: \x22nobody\x22}")'

proof "FR-012 — the approval unbound from the bytes, so an edit after review still applies" \
  src/analysis/review_gate.py \
  "tests/contract/test_review_gate.py::test_an_approval_does_not_survive_an_edit_to_the_document" \
  's = s.replace("        where={\x22artifact_kind\x22: kind, \x22content_hash\x22: content_hash, \x22change_kind\x22: change_kind},", "        where={\x22artifact_kind\x22: kind, \x22change_kind\x22: change_kind},")'

# The approval that let a version take effect must not authorise the rollback
# back to it. This arm swaps the direction the restoration looks up, which is
# exactly the defect the test found before the column existed.
proof "FR-054 — a restoration admitted on the approval its publication was given" \
  src/analysis/review_gate.py \
  "tests/contract/test_review_gate.py::test_a_restoration_without_a_review_does_not_move_the_reference" \
  's = s.replace("        store.repo, proposal.kind, proposal.content_hash, CHANGE_RESTORATION)", "        store.repo, proposal.kind, proposal.content_hash, CHANGE_PUBLICATION)")'

proof "FR-054 — a restoration recorded by the predicate instead of as a widening" \
  src/analysis/review_gate.py \
  "tests/contract/test_review_gate.py::test_a_restoration_is_recorded_as_a_widening_even_where_it_narrows" \
  's = s.replace("        widening=True,", "        widening=proposal.assessment.widening,")'

# The two halves of the predicate, in opposite directions. The first makes it
# answer `widening` unconditionally, which every widening arm would still pass;
# only the narrowing control catches it. The second makes coverage symmetric,
# so a generalization and a specialization become indistinguishable.
proof "FR-019 — the widening predicate made a constant, so it stops discriminating" \
  src/analysis/review_gate.py \
  "tests/contract/test_review_gate.py::test_a_permission_withdrawn_is_a_narrowing_and_is_not_flagged" \
  's = s.replace("    if added or lifted:", "    if True:")'

proof "FR-019 — coverage made symmetric, so a generalized permission reads as unchanged" \
  src/analysis/effect_rules.py \
  "tests/contract/test_review_gate.py::test_a_permission_generalized_is_a_widening" \
  's = s.replace("        _is_parameter(segment) or segment == counterpart", "        _is_parameter(segment) or _is_parameter(counterpart) or segment == counterpart")'

# ---------------------------------------------------------------------------
# T118 — the SC-001 window as two spans, with the subject's size and FR-045's
# share beside it. Ten arms, because `src/analysis/timing.py` is ten refusals
# and each of them fails in its own direction.
#
# The three structural ones — size required, share required, analysis span
# required — are the whole of T118's mechanism, and each has to be removed
# separately: taking one out leaves the other two reporting, so a single arm
# would score the pair rather than the piece it names.

proof "T118 — a report becomes constructible with no subject size, so a wall time loses its denominator" \
  src/analysis/timing.py \
  "tests/unit/test_sc001_timing.py::test_a_report_cannot_be_built_without_the_subject_size" \
  's = s.replace("        if not isinstance(self.subject_size, SubjectSize):", "        if False:")'

proof "T118 — a report becomes constructible with no FR-045 share, which is the vacuity SC-001 invites" \
  src/analysis/timing.py \
  "tests/unit/test_sc001_timing.py::test_a_report_cannot_be_built_without_the_not_verifiable_share" \
  's = s.replace("        if not isinstance(self.not_verifiable, NotVerifiableShare):", "        if False:")'

# The defect T118 exists for, stated as a tamper: one figure over a bounded
# step and an unbounded one, quietly true on small inputs and quietly false on
# large ones. Nothing else in the module refuses this, because a window with a
# zero analysis span is arithmetically consistent.
proof "T118 — a window with no analysis span becomes a single fused total" \
  src/analysis/timing.py \
  "tests/unit/test_sc001_timing.py::test_a_window_with_no_analysis_span_is_a_fused_total_and_is_refused" \
  's = s.replace("        if self._analysis_spans == 0:", "        if False:")'

# Assessability is derived from FR-045 having reported over a production
# window. Made a constant `True`, every harness run reports an assessable
# SC-001 — which is precisely the reading the specification forbids at the
# passage this arm is named for.
proof "T118 — SC-001 becomes assessable from a harness run, dropping the FR-045 precondition" \
  src/analysis/timing.py \
  "tests/unit/test_sc001_timing.py::test_a_harness_run_is_not_independently_assessable" \
  's = s.replace("        return self.not_verifiable.production", "        return True")'

proof "T118 — an analysis figure taken without codegraph stops saying so, so U-21 reads as answered" \
  src/analysis/timing.py \
  "tests/unit/test_sc001_timing.py::test_an_analysis_figure_taken_without_codegraph_says_so" \
  's = s.replace("    codegraph_invoked: bool = False", "    codegraph_invoked: bool = True")'

proof "T118 — FR-045's breakdown stops having to account for its own total" \
  src/analysis/timing.py \
  "tests/unit/test_sc001_timing.py::test_a_breakdown_that_does_not_sum_to_its_total_describes_neither" \
  's = s.replace("        if counted != self.not_verifiable:", "        if False:")'

# SC-001 names the *first* verified answer. Without the guard the mark moves
# to the last one, and a run whose fourth question took ten minutes reports
# ten minutes for a criterion its first question met in a second.
proof "T118 — a later verified answer moves the mark, so the criterion times the wrong one" \
  src/analysis/timing.py \
  "tests/unit/test_sc001_timing.py::test_a_later_verified_answer_does_not_move_the_first" \
  's = s.replace("        if self._first_verified is None:\n            self._first_verified = self._since_start()", "        self._first_verified = self._since_start()")'

proof "T118 — a share over an empty population becomes a low share instead of no measurement" \
  src/analysis/timing.py \
  "tests/unit/test_sc001_timing.py::test_a_share_over_an_empty_population_is_refused" \
  's = s.replace("        if not isinstance(self.attempted, int) or self.attempted <= 0:", "        if False:")'

proof "T118 — a numerator above its denominator passes, so two populations report as one" \
  src/analysis/timing.py \
  "tests/unit/test_sc001_timing.py::test_a_numerator_above_its_denominator_names_two_populations" \
  's = s.replace("        if self.not_verifiable > self.attempted:", "        if False:")'

proof "T118 — a size document missing a field is filled in, so staleness stops being visible" \
  src/analysis/timing.py \
  "tests/unit/test_sc001_timing.py::test_a_size_document_missing_a_field_is_not_defaulted" \
  's = s.replace("        missing = [key for key in required if key not in document]", "        missing = []")'

# ---------------------------------------------------------------------------
# T117 — the unattended SC-001 harness.
#
# Three arms, and none of them duplicates the ten above: those are the report's
# refusals, these are the run's. A run can satisfy every structural refusal in
# `timing.py` and still hand it numbers taken over the wrong population.

# FR-045's share is a share of the NOT-VERIFIABLE state. Booked as a failure,
# a refusal costs the run its answer and disappears from the share anyway,
# which is the one way to get a clean share out of a run that verified nothing.
proof "T117 — a missing evidence channel is booked as a failure, so it leaves FR-045's share" \
  tests/integration/test_sc001_first_answer.py \
  "tests/integration/test_sc001_first_answer.py::test_absent_evidence_is_not_verifiable_and_not_a_failure" \
  's = s.replace("ABSENT_EVIDENCE_OUTCOME = VerificationOutcome.NOT_VERIFIABLE", "ABSENT_EVIDENCE_OUTCOME = VerificationOutcome.FAILED")'

# The evidence channel being *present* and the evidence channel being *checked*
# are two mechanisms. The arm above removes the first; this removes the second,
# and only an attestation that is present and wrong can tell them apart.
proof "T117 — the recomputed evidence digest stops being compared, so a wrong attestation verifies" \
  tests/integration/test_sc001_first_answer.py \
  "tests/integration/test_sc001_first_answer.py::test_an_altered_attestation_fails_verification_rather_than_refusing_it" \
  's = s.replace("    if digest != question[\x22evidence_digest\x22]:", "    if False:")'

# The cherry-pick. A run that stops at the first verified answer divides
# FR-045's share by however many questions it reached before getting lucky,
# and SC-001 then reports a timing produced by that question alone.
proof "T117 — the run stops at the first verified answer, so the share is taken over what it reached" \
  tests/integration/test_sc001_first_answer.py \
  "tests/integration/test_sc001_first_answer.py::test_every_question_is_attempted_even_after_the_first_verified_answer" \
  's = s.replace("            if result.is_verified:\n                timer.first_verified_answer()", "            if result.is_verified:\n                timer.first_verified_answer()\n                break")'

# ---------------------------------------------------------------------------
# T101 — the reference-application arms, and the shell-heavy clause this pass
# declined to build a second time.
#
# **No arm here targets `tests/batteries/test_seccomp_overhead.py`'s own
# assertions.** That module is `linux_only` and `privileged`, so on any host
# that cannot run it every such proof reports SKIPPED — an outcome that says
# nothing and costs a reader the same attention as one that does.
#
# **`SCORES AGAINST` is the rule and `TAMPERS` is not, and this header used to
# blur them.** It read "The two arms below" when six follow it, and a count that
# drifts under a rule stated once reads as though the rule had narrowed with it —
# which is how the prohibition got restated elsewhere as *"no proof may touch
# that file"*. It may. **Six T101 arms follow, five of which tamper this module**
# and every one of which scores against a test in `tests/unit/` that runs on
# every host. What is forbidden is naming an assertion that cannot run, because
# such an arm reports SKIPPED forever and nobody notices.

# The workload strings are executed only under the supervisor, on privileged
# Linux. A rotted one therefore fails in the one place nobody can reproduce.
proof "T101 — the reference-application workload stops being a program, unnoticed until a privileged run" \
  tests/batteries/test_seccomp_overhead.py \
  "tests/unit/test_reference_app.py::test_t101s_reference_application_workloads_run_on_any_platform" \
  's = s.replace("import app, seed\n", "import app, seed, this_module_does_not_exist\n")'

# T101's shell-heavy clause is recorded as discharged by the generic proxy arm
# *because* the reference application is not a shell workload. Emptying the
# enumeration makes that claim unfalsifiable, which is the state it was in
# before this detector existed.
proof "T101 — the process-spawn enumeration is emptied, so 'not a shell workload' stops being checkable" \
  tests/unit/test_reference_app.py \
  "tests/unit/test_reference_app.py::test_the_spawn_detector_fires_on_a_planted_call" \
  's = s.replace("_PROCESS_SPAWNING_MODULES = frozenset(\n    {\x22subprocess\x22, \x22multiprocessing\x22, \x22pty\x22, \x22asyncio.subprocess\x22}\n)", "_PROCESS_SPAWNING_MODULES = frozenset()")'

# The record's host caveat was a hardcoded string until 2026-08-10, and it
# named Docker Desktop's linuxkit VM on a native Azure runner that had never
# been one. This arm is that defect put back: an early return in front of the
# reading, restoring the exact sentence that shipped. It belongs in this file
# rather than staying a transcript because the guard's whole value is that it
# fails on a constant, and a guard nobody has watched fail is a guard nobody
# has measured.
#
# It names a test in `tests/unit/`, and that is what makes it scoreable at all.
# The reasoning above still holds for `test_seccomp_overhead.py`'s own
# assertions — they are `linux_only` and `privileged` and a proof over them
# reports SKIPPED — but `host_property_caveat` is a pure function of three
# readings, so its test runs on every host and this arm scores everywhere.
proof "T101 — the record's host caveat goes back to being a constant, and describes a host it was not measured on" \
  tests/batteries/test_seccomp_overhead.py \
  "tests/unit/test_seccomp_overhead_caveat.py::test_the_host_caveat_differs_between_three_kernels" \
  's = s.replace("    matched = sorted(", "    return \x22Docker Desktop\x27s linuxkit VM on this host, not a bare Linux host. Syscall-interception overhead is the measurement most sensitive to that difference and it may not transfer.\x22\n    matched = sorted(")'

# --- T101, 2026-08-10: the two derived fields of the record ------------------
#
# **The rule these three arms are written under, because it reads as narrower
# than the paragraph above.** The recorded decision is that no proof *scores
# against* an assertion inside `test_seccomp_overhead.py`, because such a proof
# reports SKIPPED on every host that cannot run the module. It does not forbid
# *tampering* that module — the arm above already tampers it and scores on a
# `tests/unit/` test, and these follow it exactly. Each removes a mechanism from
# the battery and names a test that runs on every host, so all three score
# everywhere.
#
# The reverse case is on the record too, and is why there is no arm for
# `test_no_arm_publishes_a_rate_its_own_overhead_contradicts`: that assertion
# needs the fixture, the fixture needs a kernel and root, and a proof naming it
# would be the SKIPPED-everywhere arm the decision excludes.

# The vacuity itself, put back. Until 2026-08-10 the battery asserted the
# presence of `seccomp-overhead.json`, which is tracked in git — true on a fresh
# checkout, so the test could not fail for the reason its name gave and every CI
# run passed it against a file the run never touched. Collapsing the two names
# restores exactly that: the branch stops reading the environment, and an
# existence check is satisfied by the committed file again.
proof "T101 — the two result-file names collapse, so 'the measurement is recorded' is vacuous again" \
  tests/batteries/test_seccomp_overhead.py \
  "tests/unit/test_seccomp_overhead_record.py::test_the_two_settings_select_different_files" \
  's = s.replace("    return DURABLE_RECORD if environ.get(RECORD_REQUEST) == \x221\x22 else LATEST_RECORD", "    return DURABLE_RECORD")'

# The negative rate, put back. CI run 31403771772 published
# `microseconds_per_notification: -502.82` for the compute_only control over 78
# notifications, because the supervised median came out below its own baseline.
# Removing the sign check republishes it.
proof "T101 — a rate is published for an overhead that came out negative" \
  tests/batteries/test_seccomp_overhead.py \
  "tests/unit/test_seccomp_overhead_record.py::test_the_negative_rate_ci_published_is_withheld_now" \
  's = s.replace("    if overhead_seconds <= 0:\n        return None, \x22non-positive-overhead\x22\n", "")'

# The reason, not the suppression. A rate withheld with no recorded reason is an
# absence that reads as an oversight, which is the shape `costs.UNPRICED` exists
# to prevent — and the arm above still passes with the prose gone, because the
# rate is still withheld. This is the half that keeps the artifact readable.
proof "T101 — a withheld rate stops recording why, so the absence reads as a gap" \
  tests/batteries/test_seccomp_overhead.py \
  "tests/unit/test_seccomp_overhead_record.py::test_every_withholding_reason_is_recorded_in_prose" \
  's = s.replace("UNRATED: Mapping[str, str] = {", "UNRATED: Mapping[str, str] = {\n    \x22unreached-reason\x22: \x22a recorded reason for an absence that no branch can produce, which is a row nobody checks\x22,")'

# --- T101, 2026-08-10: the clearance verdict and its qualification -----------
#
# **Six arms, and until this section the clearance machinery had none.** The
# field shipped at `cc34adb` with thirty unit tests around it and one battery
# assertion that reports SKIPPED on macOS, so deleting a fixture assignment left
# the developer's suite green and was caught only in CI. That is thinner than
# this repository's standard and the gap is closed here rather than recorded.
#
# **All six score on both hosts**, which is the rule the section above states:
# each names a test in `tests/unit/`, and the mechanisms they remove are pure
# functions of readings for exactly that reason. The one arm whose subject
# lives in the fixture — the nesting — was moved into `clearance_field` in the
# same pass, because a mechanism only reachable from a `privileged` assertion
# cannot be proved anywhere the proof would be believed.
#
# **The vacuity shape watched for here is the second guard, not the indifferent
# tamper.** These functions are checked from several angles at once, so a
# careless tamper fails four tests and proves nothing about the one it names.
# Each arm below was chosen so that its named test discriminates the mechanism
# the arm's own sentence describes, and each was run before it was declared.

# The comparator itself, which is the mechanism `58a6277` shipped wrong and
# `cc34adb` corrected. Pointing the verdict at the control's draw excursion
# tests a difference of medians against a range of raw pairwise differences —
# a wider statistic — and that run returned three of the four load-bearing arms
# as not clearing while the same run's k=10 probe put all four clear on 10 of
# 10 draws. The named test moves the band and requires the verdict not to move.
proof "T101 — the clearance verdict compares against the excursion again, so a wider statistic decides it" \
  tests/batteries/test_seccomp_overhead.py \
  "tests/unit/test_seccomp_overhead_record.py::test_the_verdict_compares_like_with_like_and_the_excursion_never_decides" \
  's = s.replace("        if overhead_seconds > control_overhead_seconds:", "        if overhead_seconds > high:")'

# The nesting, which is this field's whole repair. Returning the verdict bare
# restores exactly the record run 31435892323 published: `shell_heavy` reading
# `clears-this-runs-control` with the overlap reachable only through prose. The
# named test asserts the consumer's own filter fails AND that the destructured
# read still works, so a field that had merely become unreadable does not pass.
proof "T101 — the record's verdict goes back to a bare string, so a consumer can lift it without its qualification" \
  tests/batteries/test_seccomp_overhead.py \
  "tests/unit/test_seccomp_overhead_record.py::test_the_recorded_field_is_an_object_a_consumer_cannot_take_half_of" \
  's = s.replace("    return (\n        {\n            \x22verdict\x22: verdict,", "    return (\n        verdict,\n        {\n            \x22verdict\x22: verdict,")'

# The qualification reading the range it names, and the tamper is a half-read
# rather than a deletion — dropping the upper bound leaves the field firing on
# every positive overhead, which is the fires-regardless vacuity that looks
# like a disclosure and reports nothing. The named test moves the band across
# three values and requires both readings to appear.
proof "T101 — the excursion qualification drops its upper bound, so every arm reads as overlapping" \
  tests/batteries/test_seccomp_overhead.py \
  "tests/unit/test_seccomp_overhead_record.py::test_the_excursion_qualifies_and_still_never_decides_the_verdict" \
  's = s.replace("    if low <= overhead_seconds <= high:", "    if low <= overhead_seconds:")'

# The separation held in the signature. A default argument is the edit that
# would not break a caller, so it is the one a later pass could make without
# noticing — and once the comparator is in scope the excursion is one line from
# deciding a verdict again. The named test reads the signature and nothing else.
proof "T101 — the qualification takes the verdict's comparator, so the excursion is one edit from deciding again" \
  tests/batteries/test_seccomp_overhead.py \
  "tests/unit/test_seccomp_overhead_record.py::test_the_qualification_cannot_see_the_comparator_that_decides_the_verdict" \
  's = s.replace("    is_the_control: bool,\n) -> str:", "    is_the_control: bool,\n    control_overhead_seconds: float = 0.0,\n) -> str:")'

# The prose, not the reading. A qualification key the record cannot resolve to a
# sentence is an absence that reads as a gap, which is the shape `costs.UNPRICED`
# and `UNRATED` both exist to prevent. This arm is the `EXCURSION_QUALIFICATION`
# twin of the `UNRATED` arm above and fails for the same reason: a row nothing
# reaches describes a branch that no longer exists.
proof "T101 — the qualification table grows a row nothing reaches, so it describes a branch that is gone" \
  tests/batteries/test_seccomp_overhead.py \
  "tests/unit/test_seccomp_overhead_record.py::test_every_excursion_reading_is_recorded_in_prose" \
  's = s.replace("EXCURSION_QUALIFICATION: Mapping[str, str] = {", "EXCURSION_QUALIFICATION: Mapping[str, str] = {\n    \x22unreached-qualification\x22: \x22a recorded reading of the control excursion that no branch can produce, which is a row nobody checks\x22,")'

# The plant, and this arm tampers a committed *record* rather than a module —
# the only one in this file that does. That is deliberate: the both-directions
# evidence is required to live inside a committed artifact, not a fixture, so
# the thing that must not silently collapse is the artifact. Run 31435892323 is
# one overlapping arm and three standing clear; flattening the one leaves a
# record where the qualification has never been observed firing.
proof "T101 — the committed CI record loses its overlapping arm, so the qualification is never seen firing" \
  tests/batteries/results/seccomp-overhead-ci-31435892323.json \
  "tests/unit/test_seccomp_overhead_record.py::test_a_committed_record_plants_both_qualifications" \
  's = s.replace("\x22qualified_by\x22: \x22overlaps-this-runs-control-excursion\x22", "\x22qualified_by\x22: \x22stands-clear-of-this-runs-control-excursion\x22")'

# ---------------------------------------------------------------------------
# T004 — the `codegraph` schema pin.
#
# ~~One arm~~ **three since 2026-08-10**, when the pin stopped being half-set.
# The first is below and is unchanged. The two after it exist because the
# constants became assertable: while `CODEGRAPH_SCHEMA_SHA256` was `None` there
# was nothing to remove — a guard over an unset value is satisfied by the value
# staying unset, and no tamper distinguishes that from the mechanism working.
#
# The first names the mechanism the module's own first sentence is about:
# only the schema participates in the digest, never a row. That is what makes a
# pin over somebody else's artifact possible at all — the analysed repository
# changes constantly, so a digest that moved with it would report every
# re-index as an upstream release, and FR-028 would then hand the operator an
# upstream release as their own code having moved.
#
# The tamper folds each table's row count into the hash. It is chosen over the
# module's other refusals because **nothing else in the file catches it**: with
# row counts in the digest the canonical ordering, the `sqlite_%` exclusion, the
# whitespace normalisation and both of `verify()`'s arms all still hold and
# their tests all still pass, so exactly one test goes red and the arm cannot be
# scoring a guard it does not name. Verified by planting, not by reading.
proof "T004 — row counts fold into the schema digest, so a re-index reads as an upstream release" \
  src/analysis/codegraph_pin.py \
  "tests/unit/test_codegraph_pin.py::test_the_digest_does_not_move_when_rows_are_inserted" \
  's = s.replace("        ).fetchall()\n    finally:", "        ).fetchall()\n        rows = rows + [(\x22table\x22, \x22rowdata\x22, str([conn.execute(\x22SELECT count(*) FROM \x22 + n).fetchone() for t, n, _ in rows if t == \x22table\x22]))]\n    finally:")'

# The digest itself, and this arm is the reason the fixture under
# `tests/fixtures/codegraph-schema/` was committed rather than the constant
# being left as an opaque 64 characters. **Without a committed schema to
# re-derive from, this tamper fails nothing**: a test that pins the constant's
# shape, or asserts it against a literal copy of itself, passes just as happily
# on one hex digit as on the observed value. One digit is moved rather than the
# whole string, because a mangled constant could be caught by a length or a
# hex-alphabet check and this must be caught by the arithmetic.
proof "T004 — one hex digit of the pinned digest moves, so the constant asserts nothing observed" \
  src/analysis/codegraph_pin.py \
  "tests/unit/test_codegraph_pin.py::test_the_pinned_digest_is_re_derived_from_the_pinned_revisions_own_schema" \
  's = s.replace("044054b3962ba8315b2e7b2243bbfc1e9ec954cfa6b3b30db11f8eb6cb3f01f4", "144054b3962ba8315b2e7b2243bbfc1e9ec954cfa6b3b30db11f8eb6cb3f01f4")'

# The disclosure inside the version string, which is a mechanism and not a
# comment. The vendored tree is seven commits past `v1.5.0`, so a pin that reads
# as a release sends the next reader to `npm install @colbymchenry/codegraph@1.5.0`
# — different code, a digest that will not match, and nothing on the error
# message explaining why. The tamper leaves the revision sha in place and removes
# only the words, so what goes red is the disclosure requirement rather than the
# identity.
proof "T004 — the revision disclosure leaves the version string, so the pin reads as a release" \
  src/analysis/codegraph_pin.py \
  "tests/unit/test_codegraph_pin.py::test_the_pinned_version_names_a_revision_that_cannot_be_installed" \
  's = s.replace("(describe v1.5.0-7-g49c11fc; unreleased revision, not an npm version)", "(1.5.0)")'

# ---------------------------------------------------------------------------
# Phase 5, the analysis cluster: T119, T120, T121, T136.

# The ordering, which is the whole of T119's contract with the pin. Swapping
# `verify` for `schema_digest` leaves the index constructible, leaves the digest
# populated and leaves every other arm of the file passing — it removes only the
# comparison against the pinned constant, which is the one thing that stops an
# upstream release being read as source.
proof "T119 — the index is built from an unverified artifact, so an upstream release passes as source" \
  src/analysis/codegraph.py \
  "tests/unit/test_codegraph_invocation.py::test_the_schema_pin_is_asserted_before_the_index_is_returned" \
  's = s.replace("digest=pin.verify(path)", "digest=pin.schema_digest(path)")'

# rc == 0 with no database. The case a returncode check alone reads as fine, and
# the reason the check is separate from the returncode branch above it.
proof "T119 — a successful run that wrote nothing is admitted, so the stage reads an absent index" \
  src/analysis/codegraph.py \
  "tests/unit/test_codegraph_invocation.py::test_a_successful_run_that_produced_no_artifact_is_a_failure" \
  's = s.replace("    if not db_path.is_file():", "    if False:")'

# T136's distinct mechanism, and it is deliberately not the tamper above.
# `verify()` still fires, the stage still stops, no artifact is still published
# — only the *wording* moves, from "upstream schema change, NOT source drift" to
# the vocabulary the drift channel uses. That is the whole failure U-04 names:
# the analysis correctly refuses and the operator is sent to their own
# repository to look for a change they did not make.
proof "T136 — the refusal adopts the drift vocabulary, so an upstream release reads as source drift" \
  src/analysis/codegraph_pin.py \
  "tests/contract/test_codegraph_schema_pin.py::test_the_refusal_never_reads_as_source_drift" \
  's = s.replace("This is an upstream schema change, NOT source drift. It must ", "Schema drift was detected here. It must ")'

# Independence. A recomputation that reads the quantity it checks agrees with
# itself whatever the value is, which is FR-022 satisfied on paper and nothing
# detected in fact — the ~~8~~ 9 schema-blind numeric false successes feature
# 001 measured, reproduced by a verifier that believes it is recomputing.
# Corrected 2026-08-12 from E8-VIABILITY.md section 6: the split is 9 numeric
# and 2 set-typed, not 8 and 3, and the schema-derived arm misses both classes.
proof "T120 — a recomputation may read the quantity it checks, so it agrees with itself" \
  src/analysis/derive.py \
  "tests/unit/test_derive.py::test_a_self_referential_recomputation_is_refused" \
  's = s.replace("            if self.quantity in self.recomputation.reads:", "            if False:")'

# The empty derivation. Emitting a contract for a function no rule fired on is
# how an analyzer becomes indistinguishable from one that is right, and it is
# the shape of both measured instances of *fluent, plausible and wrong*.
proof "T120 — a function no rule fired on still yields a contract, so absence becomes a claim" \
  src/analysis/derive.py \
  "tests/unit/test_derive.py::test_the_negative_fixture_derives_nothing" \
  's = s.replace("    if not checks and not preconditions and not failures:\n        return None", "    if False:\n        return None")'

# FR-024 property 2. A numeric precision source is a default tolerance with
# extra steps, and the ladder T125 builds would fall to it.
proof "T120 — a numeric precision source is admitted, so the ladder gets a constant to fall to" \
  src/analysis/derive.py \
  "tests/unit/test_derive.py::test_a_numeric_precision_source_is_refused" \
  's = s.replace("        if self.precision_source is not None and _is_numeric(self.precision_source):", "        if False:")'

# The recomputation capability itself, removed one rule at a time rather than
# wholesale: only the `len` branch goes, so `sum` and `max` still recompute and
# the suite does not collapse. What goes red is the arm asserting that no
# numeric quantity is left covered by a shape check alone — which is T132's
# premise, and T132 is unsatisfiable if this ever stops holding.
proof "T120 — the count aggregate stops recomputing, so a numeric quantity is left to a shape check" \
  src/analysis/derive.py \
  "tests/unit/test_derive.py::test_the_shape_only_subset_cannot_express_the_numeric_fault" \
  's = s.replace('"'"'    if name == "len" and isinstance(argument, ast.Name):'"'"', "    if False:")'

# FR-026's "as data", which an absolute path silently defeats: `envelope.scan`
# moves anything path-shaped out of the hashed payload, so the provenance would
# survive construction and vanish at wrap time.
proof "T121 — an absolute source path is admitted, so the provenance is stripped at wrap time" \
  src/analysis/provenance.py \
  "tests/unit/test_provenance.py::test_an_absolute_source_path_is_refused" \
  's = s.replace('"'"'        if self.source_file.startswith("/") or _WINDOWS_PATH.match(self.source_file):'"'"', "        if False:")'

# Constitution Principle I as amended at v1.1.0. A `validated` status with no
# artifact behind it is precisely the presented-as-validated case FR-026
# forbids, and it is the one that happens by accident.
proof "T121 — validated may be claimed with no artifact, so Principle I holds by convention" \
  src/analysis/provenance.py \
  "tests/unit/test_provenance.py::test_validated_cannot_be_claimed_without_naming_the_artifact" \
  's = s.replace("        if validated and not self.validated_against:", "        if False:")'

# ---------------------------------------------------------------------------
# OD-32 — provenance required at contract schema 1.1.0, behind a version gate.
#
# Fourteen arms, in three groups, because the decision is three mechanisms and
# each fails in its own direction:
#
#   - the schema requires FR-026's six as data (four arms), and the interesting
#     one is that a NULL provenance is refused — permitting it is the cheap way
#     to make the backward direction work and it silently un-requires the field
#     for every producer willing to write one;
#   - a 1.0.0 artifact stays readable and its unprovenanced state is named on the
#     object a caller holds (six arms), including the arm for the leniency being
#     scoped to provenance and to nothing else;
#   - absent and provisional never collapse (four arms) — the `spend_usd: 0.0`
#     defect one field over, guarded on the producer side, in the migration and
#     in the record reconstruction.
#
# Every arm below was observed failing under its tamper before it was written
# here.

# The title below is the one the substitution episode happened to; the rule that
# came out of it is enforced by `tools/check_tampers.py` and is described at
# `proof ()`, not here, because a new arm's author reads that and not this.
proof "OD-32 — the inner provenance check is never called, so the outer presence test is all that is left" \
  src/contracts/schemas.py \
  "tests/unit/test_derived_record.py::test_a_current_document_with_an_empty_provenance_object_is_refused" \
  's = s.replace("        if self.required_provenance:", "        if False:")'

# The cheap implementation of the backward direction, and the reason OD-32 limb
# ④ rejects it: a document then declares 1.1.0 without satisfying 1.1.0, and the
# schema loses the one capability the bump was made to add.
proof "OD-32 — a null provenance is admitted at 1.1.0, so a document may claim the version without the fields" \
  src/contracts/schemas.py \
  "tests/unit/test_derived_record.py::test_a_current_document_may_not_declare_its_provenance_absent" \
  's = s.replace("        if not isinstance(value, Mapping):\n            raise SchemaError(\n                f\"{self.kind}: provenance is {value!r}, which is not a \"", "        if value is None:\n            return\n        if not isinstance(value, Mapping):\n            raise SchemaError(\n                f\"{self.kind}: provenance is {value!r}, which is not a \"")'

proof "OD-32 — a partial provenance record satisfies the schema, so five of the six become optional" \
  src/contracts/schemas.py \
  "tests/unit/test_derived_record.py::test_a_current_document_with_a_partial_provenance_record_is_refused" \
  's = s.replace("        absent = [k for k in self.required_provenance if k not in value]", "        absent = []")'

# The two halves declared apart: an inner requirement over a field the outer
# `required` permits omitting is satisfied by a payload with no provenance at
# all — the 1.0.0 defect reconstructed one level down.
proof "OD-32 — the inner requirement may be declared without the outer, so omitting the field satisfies both" \
  src/contracts/schemas.py \
  "tests/unit/test_derived_record.py::test_a_schema_cannot_require_inner_fields_of_a_field_it_permits_omitting" \
  's = s.replace("        if self.required_provenance and \"provenance\" not in self.required:", "        if False:")'

# Finding 016's defect arriving through the artifact store: a document from a
# revision this build never saw has fields this build recognises.
proof "OD-32 — the version gate goes, so a later revision is read for the fields that happen to parse" \
  src/analysis/derived_record.py \
  "tests/unit/test_derived_record.py::test_a_later_revision_is_refused_rather_than_partially_read" \
  's = s.replace("        if declared not in READABLE_SCHEMA_VERSIONS:", "        if False:")'

# The disposition itself. Refusing a 1.0.0 artifact does not make it compliant;
# it makes its non-compliance unreadable, and FR-054's rollback then restores
# something the runtime cannot load.
proof "OD-32 — a 1.0.0 artifact is read under the current schema, so it becomes unloadable rather than unprovenanced" \
  src/analysis/derived_record.py \
  "tests/unit/test_derived_record.py::test_a_legacy_contract_is_readable_and_comes_back_unprovenanced" \
  's = s.replace("        if declared == PROVENANCE_REQUIRED_FROM:", "        if True:")'

# The placeholder this decision forbids, reached by the accessor rather than by a
# helper: returning the absence is what makes an unprovenanced artifact readable
# as a provenanced one at every call site.
proof "OD-32 — require_provenance answers with the absence instead of refusing" \
  src/analysis/derived_record.py \
  "tests/unit/test_derived_record.py::test_asking_an_unprovenanced_artifact_for_its_provenance_raises" \
  's = s.replace("            raise UnprovenancedArtifactError(", "            pass\n        if False:\n            raise UnprovenancedArtifactError(")'

# 1.0.0 `derived_check` could satisfy `required` with the bare string
# "signature". Read as an absence, the claim it makes is discarded silently.
proof "OD-32 — a legacy non-record provenance is read as an absence, so a claim is discarded" \
  src/analysis/derived_record.py \
  "tests/unit/test_derived_record.py::test_a_legacy_provenance_value_that_is_neither_is_refused" \
  's = s.replace("    if not isinstance(value, Mapping):", "    if False:")'

# The leniency is scoped to the one field 1.0.0 did not require. Widened, this
# gate stops being a version gate and becomes a general loosening of the schema.
proof "OD-32 — the 1.0.0 leniency widens past provenance, so any missing required field reads as old" \
  src/analysis/derived_record.py \
  "tests/unit/test_derived_record.py::test_a_legacy_document_missing_a_field_1_0_0_did_require_is_refused" \
  's = s.replace("            if missing:", "            if False:")'

# The disclosure and the records are one fact written twice. Uncross-checked, the
# direction it drifts in is the one where an unprovenanced artifact stops being
# named.
proof "OD-32 — the disclosure stops being cross-checked against the records it summarises" \
  src/analysis/derived_record.py \
  "tests/unit/test_derived_record.py::test_the_disclosure_cannot_disagree_with_the_records" \
  's = s.replace("        if self.unprovenanced_operations != expected:", "        if False:")'

# The same rejected implementation as the null-provenance arm above, reached from
# the other side: the migration is where the three registered neighbours would
# put a marked unrecoverable field, and it is the one place that could mint a
# false-versioned document.
proof "OD-32 — the migration writes a null provenance at 1.1.0, minting a document whose version is a lie" \
  src/contracts/migrations/__init__.py \
  "tests/unit/test_derived_record.py::test_the_migration_refuses_to_produce_an_unprovenanced_current_document" \
  's = s.replace("    value = document.get(\"provenance\")\n    if isinstance(value, Mapping):", "    value = document.get(\"provenance\")\n    if value is None:\n        return {**document, \"schema_version\": \"1.1.0\", \"provenance\": None}\n    if isinstance(value, Mapping):")'

# The subtlest of the fourteen: `Provenance` has defaults for `analyzer_version`
# and `validation_status`, so a partial payload read without this check comes
# back claiming THIS build's analyzer produced it, provisionally. Invented
# provenance, arriving through a constructor default.
proof "OD-32 — a stored partial provenance is rebuilt from constructor defaults, so the record invents its analyzer" \
  src/analysis/provenance.py \
  "tests/unit/test_derived_record.py::test_a_legacy_partial_provenance_record_is_refused" \
  's = s.replace("        if missing:", "        if False:")'

# The producer/reader asymmetry, which is where this decision improves on the
# pricing precedent: one nullable type served both there, two types exist here,
# and these two arms are what keep the nullable one confined to the reader.
proof "OD-32 — the producer contract type accepts an absent provenance, so a fresh derivation can omit it" \
  src/analysis/derive.py \
  "tests/unit/test_derived_record.py::test_a_derived_contract_cannot_be_constructed_without_provenance" \
  's = s.replace("                f\"{self.operation_id}: no provenance. FR-026 requires it on \"", "                \"\")\n        if False:\n            raise DerivationError(")'

proof "OD-32 — the producer check type accepts an absent provenance, so a fresh check can omit it" \
  src/analysis/derive.py \
  "tests/unit/test_derived_record.py::test_a_derived_check_cannot_be_constructed_without_provenance" \
  's = s.replace("                f\"{self.operation_id}/{self.quantity}: no provenance. FR-026 \"", "                \"\")\n        if False:\n            raise DerivationError(")'

# ---------------------------------------------------------------------------
# T122 / T123 — promotion against the published specification, and the gate that
# makes the distinction load-bearing. INV-012.
#
# The first three arms are the type-level gate. Each removes a *different* limb,
# and they are not doubly covered: the subclass arm defeats the type distinction
# while leaving both runtime refusals standing, the issued_by arm defeats the
# runtime backstop while leaving the type distinction standing (which is why its
# test is the construction arm and not the mypy arm), and the recomputes arm
# leaves both of the others whole. A proof that cannot tell two guards apart
# proves neither.

# The type distinction itself. With ProvisionalContract a subclass of
# ValidatedContract, every signature demanding the second accepts the first and
# the whole gate reduces to a naming convention — and `isinstance` in
# Verified.__post_init__ passes too, so this arm has to be scored by the test
# that reads the class relationship rather than by one that constructs.
proof "T123 — ProvisionalContract subclasses ValidatedContract, so the type distinction is a naming convention" \
  src/analysis/validate.py \
  "tests/invariants/test_provisional_never_verified.py::test_provisional_and_validated_are_unrelated_types" \
  's = s.replace("class ProvisionalContract:", "class ProvisionalContract(ValidatedContract):")'

# The runtime backstop for what Python permits and a checker would have caught.
# Removing it leaves the annotations — and therefore the mypy arms — untouched,
# which is exactly why the construction arm exists separately from them.
proof "T123 — Verified accepts any issuer, so a provisional contract reaches VERIFIED at run time" \
  src/analysis/validate.py \
  "tests/invariants/test_provisional_never_verified.py::test_verified_cannot_be_constructed_from_a_provisional_contract" \
  's = s.replace("        if not isinstance(self.issued_by, ValidatedContract):", "        if False:")'

# The condition that keeps T132 satisfiable. Without it a shape-and-type-only
# control verifier can report VERIFIED and stops being distinguishable from the
# real one at the layer meant to separate them.
proof "T123 — a shape-only check can produce VERIFIED, collapsing T132's control into the real verifier" \
  src/analysis/validate.py \
  "tests/invariants/test_provisional_never_verified.py::test_a_shape_only_check_cannot_produce_verified" \
  's = s.replace("        if not self.check.recomputes():", "        if False:")'

# The evidence itself. An agreement that does not compare its two values is a
# boolean with extra steps, which is the failure the type is shaped against.
proof "T123 — an agreement accepts two values that disagree, so agreement stops being evidence" \
  src/analysis/validate.py \
  "tests/invariants/test_provisional_never_verified.py::test_an_agreement_refuses_two_values_that_are_not_equal" \
  's = s.replace("        if self.reported != self.recomputed:", "        if False:")'

# No default tolerance (FR-024). Removing the refusal makes a float pair compare
# under exact equality silently, which is a precision decision taken by accident.
# This refusal raises and carries no named reason: FR-024's machine-readable
# reason is RefusalReason.PRECISION_NOT_STATED, which lives in
# src/runtime/verify.py and refuses ahead of this type. The two are separately
# proved because deleting either leaves the other standing.
proof "T125 — the float refusal goes, so an undefined precision is compared silently" \
  src/analysis/validate.py \
  "tests/invariants/test_provisional_never_verified.py::test_an_agreement_refuses_a_float_and_names_precision_as_undecided" \
  's = s.replace("            if isinstance(value, float):", "            if False:")'

# ---------------------------------------------------------------------------
# T122 — absence is not agreement, at each of the three depths it can arrive.
# Three arms rather than one, because the promotion bug is that a single
# `promote unless contradicted` branch reads all three as agreement, and a proof
# over only one of them would leave the other two able to promote.

# The three absence arms below are titled for what the tamper actually
# produces, which is **not** a promotion. With any one of these branches gone the
# comparison runs against the absence itself and the function cannot answer at
# all — so what each proves is that the branch is the only thing turning that
# absence into a named `provisional`, not that its removal promotes. The
# distinction is worth the words: a title claiming a promotion would describe a
# failure mode the tamper does not reach, and the arm would then be evidence for
# a sentence nobody had tested.
proof "T122 — an absent specification is not turned into a named provisional, so the comparison runs against nothing" \
  src/analysis/validate.py \
  "tests/unit/test_validate.py::test_no_specification_at_all_yields_provisional_naming_the_absence" \
  's = s.replace("    if specification is None or served_operation_id is None:", "    if False:")'

proof "T122 — an unserved operation is not turned into a named provisional, so the comparison reads an absent entry" \
  src/analysis/validate.py \
  "tests/unit/test_validate.py::test_an_operation_the_specification_does_not_serve_is_provisional" \
  's = s.replace("    if operation is None:", "    if False:")'

proof "T122 — a silent entry is not turned into a named provisional, so the comparison reads an absent declaration" \
  src/analysis/validate.py \
  "tests/unit/test_validate.py::test_an_entry_that_declares_no_parameters_is_provisional_not_agreeing" \
  's = s.replace("    if declared is None:\n        return ProvisionalContract(", "    if False:\n        return ProvisionalContract(")'

# The comparison itself. Without it every operation the specification serves
# promotes, whatever it declares — which is the FR-057 signal (a source
# reference pointing at the wrong application) going undetected.
proof "T122 — the parameter comparison goes, so every served operation promotes whatever it declares" \
  src/analysis/validate.py \
  "tests/unit/test_validate.py::test_a_specification_that_disagrees_yields_provisional_with_the_difference_named" \
  's = s.replace("    if derived != published:", "    if False:")'

# Principle I's independence clause at this module's one decision point: what
# `validated_against` is allowed to name. Pointing it at the source file makes
# every derivation self-validating, and the refusal that catches it lives in
# Provenance — so this arm proves that this module is actually subject to it.
proof "T122 — promotion names the derivation's own source file as its validator" \
  src/analysis/validate.py \
  "tests/unit/test_validate.py::test_promotion_cannot_name_the_source_file_as_its_own_validator" \
  's = s.replace("        validated_against=specification.source_url,", "        validated_against=contract.provenance.source_file,")'

# NOTE — `test_promotion_does_not_promote_the_contracts_checks` deliberately has
# **no removal proof**, and the absence is the honest reading rather than an
# oversight. The property is held by the *absence* of code: nothing in
# `validate.py` touches a check's provenance, so there is no mechanism to edit
# out. A removal proof needs a mechanism to remove, and the only way to make
# that test fail is to *add* promotion code — which is not a removal and would
# be a proof shaped to pass. The test stands as a guard against that future
# edit; it is not evidence that a guard is running.

# The bridge that names the contract's status. It was the mitigation for a
# default that no longer exists; what it still carries is the naming, and
# without it a provisional contract yields a Result that says nobody looked.
proof "T123 — the bridge stops marking a provisional result provisional, so the old guard never fires" \
  src/analysis/validate.py \
  "tests/invariants/test_provisional_never_verified.py::test_the_bridge_marks_a_provisional_result_provisional" \
  's = s.replace("            corroboration=Corroboration.PROVISIONAL,", "            corroboration=Corroboration.NOT_STATED,")'

# ---------------------------------------------------------------------------
# T126, T127 and T128 — the result record.
#
# Seven arms over one file. The first two are the defect T123 recorded and this
# record closed: a corroboration a caller could reach by omission. The middle
# three are the exhaustiveness of FR-025's three states, and they are the arms
# worth reading carefully — each removes a DIFFERENT property of the same map,
# because a map that is total, disjoint and complete in its image fails three
# different ways and a single tamper would only ever show one of them.
#
# Every one of these was applied by hand and the named test read failing before
# it was written down here. None fails on an import or a collection error.

# This tamper is applicable only because `corroboration` is currently the LAST field of `Result`
# with no default — add a required field after it and the defaulted `corroboration` precedes a
# non-defaulted one, the dataclass decorator raises `TypeError: non-default argument ... follows
# default argument` at import, and this arm degrades to `unproven`/`tamper-broke-collection`
# exactly as the FR-025 arm above did before `5d067f7`. Measured 2026-08-12 by planting one such
# field. It fails safe rather than green, and `tools/check_tampers.py` cannot see it coming:
# field ordering is enforced when the decorator runs, which is import time and not compile time.
proof "T126 — the corroboration gets a default, so a caller reaches a verified result by saying nothing" \
  src/contracts/result.py \
  "tests/invariants/test_result_constructor.py::test_corroboration_has_no_default_in_the_source" \
  's = s.replace("    corroboration: Corroboration\n", "    corroboration: Corroboration = Corroboration.CORROBORATED\n")'

proof "T127 — the refusal of a verified state with nothing behind it is removed, so nobody said reads as verified" \
  src/contracts/result.py \
  "tests/contract/test_result_record.py::test_a_verified_state_cannot_be_built_without_corroboration" \
  's = s.replace("            if self.corroboration is not Corroboration.CORROBORATED:", "            if False:")'

# Totality. An outcome with no row carries none of FR-025's three states, and
# the record would raise a KeyError at the point a caller asked what state it
# was in — which is the exhaustiveness failure, arriving as a crash.
proof "T127 — an outcome loses its row in the state map, so one outcome carries no reported state" \
  src/contracts/result.py \
  "tests/contract/test_result_record.py::test_the_map_domain_is_exactly_the_outcome_enum" \
  's = s.replace("    VerificationOutcome.MODEL_ASSESSED: ReportedState.NOT_VERIFIABLE,\n", "")'

# Mutual exclusivity, from the other side: the map stays total but starts
# reporting a model assessment as verified. This is Principle I's failure
# exactly, and it is the one a totality check cannot see.
proof "T127 — a model assessment is mapped onto the verified state, so an opinion reports as a verification" \
  src/contracts/result.py \
  "tests/contract/test_result_record.py::test_only_the_verified_state_reads_as_verified" \
  's = s.replace("    VerificationOutcome.MODEL_ASSESSED: ReportedState.NOT_VERIFIABLE,", "    VerificationOutcome.MODEL_ASSESSED: ReportedState.VERIFIED,")'

# The fourth state. This is the arm the structural checks alone cannot carry:
# a fourth member the map's image does not reach is caught by the image check,
# but the count is what catches one that IS reached, and the count is only
# meaningful because it is read off FR-025 rather than written here.
proof "T127 — a fourth reported state is declared, which the requirement does not name" \
  src/contracts/result.py \
  "tests/contract/test_result_record.py::test_the_state_count_agrees_with_the_requirement_that_declares_it" \
  's = s.replace("    NOT_VERIFIABLE = \x22not_verifiable\x22\n\n\n#: The wording", "    NOT_VERIFIABLE = \x22not_verifiable\x22\n    PENDING = \x22pending\x22\n\n\n#: The wording")'

proof "T128 — a stale marking no longer has to carry its age, so nothing can be compared to the ceiling" \
  src/contracts/result.py \
  "tests/contract/test_result_record.py::test_a_stale_marking_without_an_age_is_refused" \
  's = s.replace("            if self.age_seconds is None:", "            if False:")'

# The asymmetry between the two defaults, which is the whole of T128's shape.
# FRESH here would be the boolean defect moved one field over: a caller that
# said nothing about the served-operation set would be recorded as having said
# it was current.
proof "T128 — the staleness default becomes fresh, so silence reads as a current served-operation set" \
  src/contracts/result.py \
  "tests/invariants/test_result_constructor.py::test_the_staleness_default_makes_no_claim" \
  's = s.replace("    staleness: Staleness = field(default=STALENESS_NOT_STATED)", "    staleness: Staleness = field(default=Staleness(StaleMarking.FRESH))")'

# --- OD-35's third subject ----------------------------------------------------
#
# The same asymmetry a THIRD time, and the member that makes it a claim.
# `NOT_REACHED` says a declaration was in hand and the ladder never got to it,
# so a producer that never saw one — `Verified.to_result`, which cannot see a
# precision at all — would be recorded as having resolved a question nobody
# asked. That is `FRESH` again, and the wall-clock numerator defect again: a
# quantity nobody measured, indistinguishable from one somebody did.
proof "OD-35 — the precision default becomes not-reached, so silence reads as a declaration the ladder resolved" \
  src/contracts/result.py \
  "tests/contract/test_result_record.py::test_the_precision_default_makes_no_claim" \
  's = s.replace("    precision: Precision = field(default=PRECISION_NOT_STATED)", "    precision: Precision = field(default=Precision(PrecisionBasis.DECLARATION_NOT_REACHED))")'

# `Staleness`'s stale-needs-an-age refusal, on the field OD-35 ③ modelled on it.
# Without it a record can say the comparison rests on the caller's own word and
# be unable to say WHOSE — the exposure recorded and the thing that closes it
# withheld. FR-024 property 5 names both nouns and this is the one that makes
# the disclosure actionable rather than merely present.
proof "OD-35 — a declared precision no longer has to say where it was declared, so provenance is claimed and not carried" \
  src/contracts/result.py \
  "tests/contract/test_result_record.py::test_a_declared_precision_must_say_where_it_was_declared" \
  's = s.replace("        if declared and not (self.declared_in or \x22\x22).strip():", "        if False:")'

# The mirror, and `PrecisionProvenance`'s own words one layer down: a source
# cited for a displacement that did not happen is fabricated provenance. Here
# it is a declaration cited for a comparison it did not act on, which is a
# record asserting the caller's word carried a rung the artifact ladder carried.
proof "OD-35 — a non-declared basis may carry a source text, so a record cites a declaration that did not act" \
  src/contracts/result.py \
  "tests/contract/test_result_record.py::test_a_basis_that_is_not_declared_carries_no_source_text" \
  's = s.replace("        if not declared and self.declared_in is not None:", "        if False:")'

# OD-35 ④, and the arm that makes a HALF-REVERT to OD-34 ③ fail at construction
# rather than pass quietly. The two fields have different subjects, and the pair
# asserts contradictory things about one contract: a declaration is admissible
# only against a validated contract, and a provisional one refuses at
# CONTRACT_PROVISIONAL before the precision question is reached.
proof "OD-35 — the contradictory pair is admitted, so one record says the contract was both validated and provisional" \
  src/contracts/result.py \
  "tests/contract/test_result_record.py::test_a_declared_precision_cannot_sit_beside_a_provisional_contract" \
  's = s.replace("            and self.corroboration is Corroboration.PROVISIONAL\n        ):", "            and False\n        ):")'

# ---------------------------------------------------------------------------
# INV-013 — the layering pin.
#
# The checker lives in its own test file, as INV-002's does, so these two tamper
# that file. Both were applied by hand and read failing before being written
# here, and both fail on an assertion rather than on a collection error.
#
# The first widens the comparison by one layer, which is the smallest edit that
# makes the rule stop seeing the edge it exists for while still walking the tree
# and still reporting a well-formed empty result — the shape a rule takes when it
# has quietly stopped measuring.
proof "INV-013 — the layer comparison is widened by one, so an upward import is no longer an upward import" \
  tests/invariants/test_layering.py \
  "tests/invariants/test_layering.py::test_the_checker_fires_on_a_planted_upward_import" \
  's = s.replace("if destination is None or destination <= source:", "if destination is None or destination <= source + 1:")'

# The second widens the scope instead of the comparison. Reading every node
# rather than the module body makes the rule fire on the one deferred upward
# import the tree deliberately uses to break a cycle — a rule stated more widely
# than the tree obeys it, firing on something legitimate.
proof "INV-013 — the walk reads every node, so the tree's one deliberate deferred import is reported as a violation" \
  tests/invariants/test_layering.py \
  "tests/invariants/test_layering.py::test_a_deferred_upward_import_is_not_reported" \
  's = s.replace("        for node in tree.body:", "        for node in ast.walk(tree):")'

# ---------------------------------------------------------------------------
# T124, T125 and T129 — the recomputing verifier.
#
# Every arm below was observed failing by planting before it was written down,
# and the failure each produces was read rather than assumed. Ten of the twelve
# fail on an assertion naming the wrong outcome; two fail on a wrong refusal
# reason. None fails on an import, a crash or an unrecognised selector, which
# are the failures any tamper produces and which prove nothing.
#
# One arm in this module has NO proof and the absence is declared rather than
# quiet — see the note at the end of this block.

# The whole of FR-022 in one branch. Without it, two values read out of ONE
# retrieval are compared, which is an identity that agrees whatever the value
# is. The planted run returns Verified.
proof "T124 — the independence refusal goes, so one retrieval supplies both values and the comparison verifies itself" \
  src/runtime/verify.py \
  "tests/contract/test_independent_derivation.py::test_a_path_whose_retrieval_is_the_reported_one_is_refused_by_name" \
  's = s.replace("    if reported.retrieval == recomputed.retrieval:", "    if False:")'

# FR-024's own case, and the reason this is not a doubly-covered guard:
# RecomputationAgreement also refuses a float, by raising, and this module turns
# a raise into a Disagreement. So removing this branch does not restore the
# refusal through a fallback — it converts an honest not-verifiable into a FALSE
# ALARM, and the result carries no list of consulted sources at all. The planted
# run returns Disagreement.
proof "T125 — the float refusal goes, so a quantity with no stated precision is reported as a failure instead of refused" \
  src/runtime/verify.py \
  "tests/unit/test_verify.py::test_a_float_pair_refuses_with_a_named_reason_naming_the_silent_sources" \
  's = s.replace("        if isinstance(sourced.value, float):", "        if False:")'

# The same branch against the arm that matters more: two floats that are exactly
# equal. Without the refusal this PASSES, which is a comparison whose precision
# nobody stated reading as verification — the accident FR-024 exists to prevent.
proof "T125 — the float refusal goes, so two exactly equal floats verify under a precision nobody stated" \
  src/runtime/verify.py \
  "tests/unit/test_verify.py::test_the_float_refusal_is_not_a_disagreement_even_when_the_values_agree" \
  's = s.replace("        if isinstance(sourced.value, float):", "        if False:")'

# True == 1 in Python. The planted run returns Disagreement rather than the
# named refusal, so a boolean reported against a count is triaged as the target
# being wrong instead of as a quantity that is not a magnitude.
proof "T125 — the boolean refusal goes, so a boolean reported quantity is compared against a count" \
  src/runtime/verify.py \
  "tests/unit/test_verify.py::test_a_boolean_reported_quantity_refuses_rather_than_agreeing_with_one" \
  's = s.replace("        if isinstance(sourced.value, bool):", "        if False:")'

# The sharpest false success available to a recomputing verifier: the
# independent path returns nothing, sum of nothing is 0, and a reported 0
# agrees. The planted run returns Verified over a collection with no rows.
proof "T124 — the empty-aggregate guard goes, so an aggregate over no rows is zero and a reported zero verifies" \
  src/runtime/verify.py \
  "tests/unit/test_verify.py::test_an_empty_collection_refuses_rather_than_aggregating_to_zero" \
  's = s.replace("    if not values:", "    if False:")'

# T122's rule one level down: a join between two derived artifacts is declared,
# never inferred. Without it a check is run against a contract it does not
# belong to and the result is attributed to the wrong operation.
proof "T124 — the join guard goes, so a check is run against a contract it does not belong to" \
  src/runtime/verify.py \
  "tests/unit/test_verify.py::test_a_check_from_another_contract_is_refused_rather_than_joined" \
  's = s.replace("    if check.operation_id != contract.contract.operation_id:", "    if False:")'

# FR-024's closing sentence. A refusal that names no consulted source says only
# that it refused, which is the half of the requirement that is easy to miss.
proof "T125 — the consulted-source requirement goes, so a refusal that looked at nothing is constructible" \
  src/runtime/verify.py \
  "tests/unit/test_verify.py::test_every_refusal_names_at_least_one_consulted_source" \
  's = s.replace("        if not self.consulted:", "        if False:")'

# FR-024 property 4 fixes the admissible sources. Without this a refusal can
# cite a source nobody consulted, which is finding 007s fabricated-provenance
# defect arriving in a refusal instead of in a contract.
proof "T125 — the admissible-source check goes, so a refusal can cite a source FR-024 does not admit" \
  src/runtime/verify.py \
  "tests/unit/test_verify.py::test_a_refusal_cannot_name_a_source_outside_fr_024s_admissible_set" \
  's = s.replace("        if self.artifact_class not in ADMISSIBLE_PRECISION_SOURCES:", "        if False:")'

# Reachable by a direct constructor call rather than through verify_quantity,
# and held because T126 and T127 will build records from these types without
# going through this modules entry point.
proof "T129 — the disagreement guard goes, so two values out of one retrieval can be recorded as a disagreement about the target" \
  src/runtime/verify.py \
  "tests/unit/test_verify.py::test_a_disagreement_between_two_values_from_one_retrieval_is_refused" \
  's = s.replace("        if self.reported.retrieval == self.recomputed.retrieval:", "        if False:")'

# An empty source is not equal to any paths source, so a reported result naming
# no producer passes the independence comparison BY OMISSION while having been
# read from anywhere, including from the path itself.
proof "T129 — the reported-source requirement goes, so an unnamed source passes the independence comparison by omission" \
  src/runtime/verify.py \
  "tests/unit/test_verify.py::test_a_reported_result_with_no_named_source_is_refused_at_construction" \
  's = s.replace("        if not self.source.strip():", "        if False:")'

# The two arms below are RELABELS rather than removals, and they are written
# that way on purpose. Deleting either branch produces an AttributeError — the
# provisional contract has no `verified` method, and a shape check has no
# recomputation to read — which is a crash and not a scoreable failure. What is
# scoreable, and what actually matters downstream, is the reason: T130 reports
# the share of not-verifiable results BROKEN DOWN BY these members, so a
# refusal filed under the wrong one is a wrong row in that report.
proof "T125 — a provisional contract refuses under the wrong reason, so T130 files it in the wrong row" \
  src/runtime/verify.py \
  "tests/unit/test_verify.py::test_a_provisional_contract_refuses_and_never_verifies" \
  's = s.replace("            reason=RefusalReason.CONTRACT_PROVISIONAL,", "            reason=RefusalReason.NO_RECOMPUTING_CHECK,")'

proof "T125 — a quantity absent from the reported result refuses under the wrong reason, so nothing-was-claimed reads as nothing-was-derived" \
  src/runtime/verify.py \
  "tests/unit/test_verify.py::test_a_quantity_absent_from_the_reported_result_refuses" \
  's = s.replace("            reason=RefusalReason.QUANTITY_ABSENT_FROM_RESULT,", "            reason=RefusalReason.NO_RECOMPUTING_CHECK,")'

# ---------------------------------------------------------------------------
# T212 — FR-024's caller-declared precision rung (properties 5 and 6, OD-23).
#
# Eight arms. Every one fails on an assertion naming a wrong disposition, a
# wrong report type or a missing refusal; none fails on an import, a crash or
# an unrecognised selector. The two that matter most are the first and the
# fifth, and they fail in OPPOSITE directions: the first opens the weakening
# vector the rung exists to close, the fifth closes the detection the rung
# exists to buy.
#
# The arms live against `tests/unit/test_declared_precision.py` rather than
# `test_verify.py` because that file was under concurrent edit when this rung
# was built. The split is coordination and not a judgement about where the
# arms belong.

# THE WEAKENING VECTOR, and the sharpest arm in this block. Admitting a
# declaration wherever one is present — rather than only where the ladder would
# otherwise refuse — lets a caller declare `-2` against a count the target got
# wrong by one, and 395 and 396 both round to 400 and agree. It fails into a
# FALSE NEGATIVE: a wrong answer read as verified. This is the single condition
# OD-23 replaced the ratchet to remove BY CONSTRUCTION, so its removal restores
# exactly the vector the decision was taken against.
proof "T212 — the admissibility test goes, so a caller-declared precision loosens a comparison an artifact source made exactly" \
  src/runtime/verify.py \
  "tests/unit/test_declared_precision.py::test_a_declaration_may_never_make_a_quantity_be_checked_less_strictly" \
  's = s.replace("    if refusal is not None and refusal.reason is RefusalReason.PRECISION_NOT_STATED:", "    if refusal is None or refusal.reason is RefusalReason.PRECISION_NOT_STATED:")'

# FR-024 property 5s closing sub-bullet: an ignored declaration MUST be
# disclosed on the result, not silently dropped. With the artifact source never
# found, the disclosure degrades to NOT_REACHED and the caller can no longer
# tell an artifact rung from a dropped declaration. A disclosure in a trace does
# not discharge this — the reader arrives at the result and nowhere else, which
# is what FR-058s bounded-result disclosure cost this corpus once already.
proof "T212 — the artifact-source lookup goes, so an ignored declaration is disclosed as never reached and names nothing that displaced it" \
  src/runtime/verify.py \
  "tests/unit/test_declared_precision.py::test_an_ignored_declaration_is_disclosed_on_the_result_and_names_what_displaced_it" \
  's = s.replace("    if check.precision_source is None:", "    if True:")'

# FR-024 property 6. Under this variant the marking is not a formality: *no
# artifact source supplies one* is the rungs own admissibility premise, so the
# precision is by construction a derived field nothing independent can validate,
# and constitution Principle I at v1.1.0 leaves marking as the only disposition.
# Without it an affirmative that can be wrong in either direction reads plain.
proof "T212 — the provisional marking goes, so a verification resting on a caller-declared precision reads as plainly verified" \
  src/runtime/verify.py \
  "tests/unit/test_declared_precision.py::test_an_admitted_declaration_is_marked_provisional_and_is_never_plainly_verified" \
  's = s.replace("        return self.disposition is DeclarationDisposition.ADMITTED", "        return False")'

# A RELABEL rather than a removal, and chosen for the reason T125s two relabels
# were: deleting the disposition produces a constructor error, which is a crash
# and a crash is a failure any tamper produces. What is scoreable is the LIE — a
# declaration that was used, reported as one the ladder never reached.
proof "T212 — an admitted declaration is disclosed under the wrong disposition, so a precision the caller supplied reads as one the ladder never consulted" \
  src/runtime/verify.py \
  "tests/unit/test_declared_precision.py::test_a_declaration_is_admitted_only_where_no_artifact_source_supplies_a_precision" \
  's = s.replace("            disposition=DeclarationDisposition.ADMITTED,", "            disposition=DeclarationDisposition.NOT_REACHED,")'

# WHAT THE RUNG BUYS, scored against OD-23s own measured instance: 3.23 against
# 3.201754, a 0.882% error and the only sub-one-percent catch in the census of
# 61. A comparison that always agrees turns that detection into an affirmative,
# which is a MISSED FAULT against SC-005s 95% — the opposite direction from the
# first arm in this block, and the reason both are held.
proof "T212 — the comparison at the declared precision always agrees, so the census's one sub-one-percent near-miss is reported as verified" \
  src/runtime/verify.py \
  "tests/unit/test_declared_precision.py::test_the_admitted_rung_detects_the_sub_one_percent_near_miss_the_census_measured" \
  's = s.replace("    return reported_at_declared == recomputed_at_declared", "    return True")'

# Property 5 requires the declaration AND ITS SOURCE TEXT recorded as the
# precisions provenance. Without the refusal an unattributable declaration is
# admitted, and property 4s *a precision a model proposes is not a source, at
# any rung, under any provenance* stops being enforceable one level down:
# nothing then distinguishes a precision the caller asked for from one the agent
# supplied on the callers behalf.
proof "T212 — the source-text requirement goes, so a declaration attributable to nobody is admitted as the precision's provenance" \
  src/runtime/verify.py \
  "tests/unit/test_declared_precision.py::test_a_declaration_with_no_source_text_is_refused_at_construction" \
  's = s.replace("        if not self.declared_in.strip():", "        if False:")'

# Finding 007s fabricated provenance, arriving in a disclosure instead of in a
# contract: a declaration reported as admitted while naming a source that
# displaced it. The two arms below are the two directions of one guard, and
# either alone is satisfiable by a broken pair.
proof "T212 — the fabricated-displacement guard goes, so an admitted declaration can name a source that displaced it" \
  src/runtime/verify.py \
  "tests/unit/test_declared_precision.py::test_a_disclosure_cannot_claim_a_displacement_that_did_not_happen" \
  's = s.replace("        if not ignored and self.displaced_by is not None:", "        if False:")'

proof "T212 — the displacement-naming requirement goes, so a declaration reported as ignored need not say what displaced it" \
  src/runtime/verify.py \
  "tests/unit/test_declared_precision.py::test_a_disclosure_cannot_claim_a_displacement_that_did_not_happen" \
  's = s.replace("        if ignored and self.displaced_by is None:", "        if False:")'

# NOTE — `test_the_declared_rung_reaches_no_not_verifiable_state_the_ladder_did_
# not_already_reach` has NO removal proof, and the absence is declared rather
# than filled with an arm shaped to pass. It asserts an ABSENCE — that the rung
# opens no new route into the not-verifiable state — and there is no line whose
# removal creates one. Creating a route means ADDING a RefusalReason member and
# a branch reaching it, which is not a removal and which
# `test_the_refusal_reasons_are_closed_and_each_one_is_reachable` already
# refuses. The arm is kept because it is what fails if a later pass adds that
# member and branch, and `_check_totals` in
# `src/runtime/reports/not_verifiable.py` then stops summing.

# NOTE — the shape-check refusal in `recompute` has NO removal proof, and the
# absence is a finding about this module rather than an oversight. Its condition
# is `not check.recomputes() or check.recomputation is None`, and over any
# CONSTRUCTIBLE DerivedCheck the two disjuncts are equivalent: T120s constructor
# refuses a recomputation check carrying no recomputation, and refuses any other
# kind carrying one. So dropping the first disjunct was planted and the named
# test still passed — a doubly-covered guard whose fallback satisfies the
# assertion, which is the vacuous-proof shape this file exists to refuse. Both
# are kept: the first is FR-022s statement and the second is what narrows the
# type. Named here rather than proved, because a proof shaped to pass is worse
# than a declared gap.

# --- T213, the verification seam (FR-025, OD-34) ------------------------------
#
# Ten arms over two files. The seam is the FIRST route by which a verification
# outcome reaches a caller-visible record — before it, `verify_quantity` was
# referenced nowhere in `src/` outside its own module and `Result` was built
# only by `validate.py`'s two `to_result` methods — so every arm here is about a
# path that did not previously exist and none of them can be carried by an
# older guard.
#
# The block divides in two, and the halves fail in opposite directions:
#
#   - SIX arms remove a MAPPING ROW or a carried field in
#     `src/runtime/result_join.py`, and fail into a record that misreports a
#     verification the verifier got right;
#   - FOUR arms remove the INVARIANT'S OWN SCANNER in
#     `tests/invariants/test_result_constructor.py`, and fail into an invariant
#     that reports nothing. That half exists because the construction-site arms
#     are the ones that had never fired before this task: a scanner returning an
#     empty list satisfies every membership arm above it, which is the same
#     shape as the 48-proved-having-tested-nothing failure this file opens with.
#
# Every tamper below produces a working module and a named assertion. NONE of
# them is scored on a crash, and one candidate arm was DROPPED for being a
# crash rather than retargeted to something weaker:
#
#   - mapping `Refusal` onto MODEL_ASSESSED is caught by `_refuse_unjoinable`
#     and raises. The exclusion is proved through the table and the backstop
#     separately instead, which is two arms and not one.
#
# ⚠️ A SECOND candidate was dropped under OD-34 ③ and is RESTORED, in a
# different shape, by OD-35. The old note read: *mapping `ProvisionallyVerified`
# onto VERIFIED leaves `PROVISIONAL` beside it and `Result.__post_init__`
# refuses that pair, so the defect is unconstructible.* Under OD-35 that row IS
# VERIFIED/CORROBORATED and the defect moved: what is now unconstructible is the
# old row, and what is now REACHABLE AND SILENT is dropping the third cell. The
# arm below is the one that could not be written while ③ stood.

# OD-35's third cell, and the sharpest arm in this block because the tampered
# record is VALID. Without the DECLARED basis a caller-declared precision
# produces VERIFIED/CORROBORATED/NOT_STATED, which is BYTE-IDENTICAL to a plain
# `Verified` record — FR-024 property 5's *"never plain verified"* violated with
# nothing raising, no reason field lost and no breakdown moved. That silence is
# the whole reason OD-35 minted a field instead of trusting `Result.reason`.
proof "T213/OD-35 — the declared-precision row goes, so a caller-declared precision is indistinguishable from a plain verification" \
  src/runtime/result_join.py \
  "tests/unit/test_result_join.py::test_a_provisionally_verified_report_reaches_a_verified_record_marked_declared" \
  's = s.replace("    ProvisionallyVerified: PrecisionBasis.DECLARED,", "    ProvisionallyVerified: PrecisionBasis.NOT_STATED,")'

# ⚠️ DECLARED GAP, on the `test_the_declared_rung_reaches_no_not_verifiable_state`
# treatment: dropping the SOURCE TEXT at the seam — `Precision(basis)` in place
# of `Precision(basis, declared_in=…)` — makes `Precision.__post_init__` raise,
# so the arm would score on the tamper crashing rather than on a named
# assertion. It is not reshaped into something weaker here because the guard it
# would prove is proved directly at `src/contracts/result.py` below, where the
# same defect fails as a `pytest.raises` that did not raise.

# OD-35 ⑤'s map, in place of an import the layering forbids. With ADMITTED
# rerouted the two entry points disagree about one verification: the record
# reached through `result_from_quantity_verification` says an artifact displaced
# a declaration that was in fact admitted, which is finding 007's fabricated
# provenance arriving in a disclosure.
proof "T213/OD-35 — the admitted disposition is mapped onto the displaced basis, so a disclosure names a displacement that did not happen" \
  src/runtime/result_join.py \
  "tests/unit/test_result_join.py::test_the_precision_basis_map_is_total_over_the_disposition" \
  's = s.replace("    DeclarationDisposition.ADMITTED: PrecisionBasis.DECLARED,", "    DeclarationDisposition.ADMITTED: PrecisionBasis.ARTIFACT_DISPLACED_DECLARATION,")'

# A DOWNGRADE rather than an upgrade, and it is the sharper direction: VERIFIED
# is unconstructible here (see the block note), where NOT_VERIFIABLE is legal
# and silent. A recomputation that DISAGREED — the one thing FR-022 exists to
# catch — is then reported as a result nobody could check, which moves a
# detected fault out of SC-005's numerator and into T130's not-verifiable share.
proof "T213 — the disagreement row goes, so a detected fault is reported as a result nobody could check" \
  src/runtime/result_join.py \
  "tests/unit/test_result_join.py::test_a_disagreement_becomes_a_failed_record_that_says_nobody_corroborated" \
  's = s.replace("    Disagreement: VerificationOutcome.FAILED,", "    Disagreement: VerificationOutcome.NOT_VERIFIABLE,")'

# OD-34 ③: *"MODEL_ASSESSED has no source in this union and must not acquire one
# here"*. The subtraction is what makes the exclusion by-name; without it every
# member of the enum is emittable and the seam becomes a second route past the
# boundary `tests/invariants/test_import_graph.py` holds structurally.
proof "T213 — the emittable-outcome subtraction goes, so a model's opinion becomes an outcome the seam may write" \
  src/runtime/result_join.py \
  "tests/unit/test_result_join.py::test_the_seam_can_never_emit_a_model_assessment" \
  's = s.replace(") - {VerificationOutcome.MODEL_ASSESSED}", ")")'

# The backstop, proved SEPARATELY from the table above, because a checker and
# its backstop that are the same check are one check. The arm forces the table
# to hold the forbidden row and requires the seam to refuse anyway.
proof "T213 — the emittable-outcome backstop goes, so a tampered table is transcribed instead of refused" \
  src/runtime/result_join.py \
  "tests/unit/test_result_join.py::test_the_backstop_refuses_an_outcome_the_table_should_never_hold" \
  's = s.replace("    if outcome not in JOINABLE_OUTCOMES:", "    if False:")'

# Totality read OFF THE UNION rather than off a list somebody maintains. With a
# row gone the union and the table disagree, and the arm that compares them is
# the only thing between that and a `VerificationReport` member the seam
# silently cannot join.
proof "T213 — a mapping row goes, so a member of the union has no outcome and the table stops being total" \
  src/runtime/result_join.py \
  "tests/unit/test_result_join.py::test_the_join_is_total_over_the_union_read_off_the_union" \
  's = s.replace("    Refusal: VerificationOutcome.NOT_VERIFIABLE,\n", "")'

# The one refusal reason that reports on the CONTRACT, and the row that makes
# this seam AGREE with `ProvisionalContract.to_result` rather than merely not
# contradict it. Without it one provisional contract yields two caller-visible
# records that disagree about what stood behind it, depending on which producer
# the caller reached.
proof "T213 — the provisional-contract corroboration row goes, so the seam and validate.py's own bridge disagree about one contract" \
  src/runtime/result_join.py \
  "tests/unit/test_result_join.py::test_the_join_agrees_with_the_provisional_bridge_on_a_provisional_contract" \
  's = s.replace("    RefusalReason.CONTRACT_PROVISIONAL: Corroboration.PROVISIONAL,", "    RefusalReason.CONTRACT_PROVISIONAL: Corroboration.NOT_STATED,")'

# OD-34 ③ requires each non-verified arm to carry *"the report's own named
# reason rather than a synthesised one"*. A synthesised reason is not a smaller
# version of the real one: `reports/not_verifiable.py` already records that
# `Result.reason` is free text a breakdown cannot key on, so the detail is the
# only place the operands of a disagreement survive to a reader.
proof "T213 — the disagreement's own reason goes, so a failed record explains itself with a sentence the seam wrote" \
  src/runtime/result_join.py \
  "tests/unit/test_result_join.py::test_a_disagreement_becomes_a_failed_record_that_says_nobody_corroborated" \
  's = s.replace("        return report.detail", "        return \"verification did not succeed\"")'

# FR-024 property 5s closing sub-bullet, one layer further out than T212 proved
# it: *an ignored declaration MUST be disclosed on the result, not silently
# dropped*. T212 put the disclosure on the object `verify.py` returns; this arm
# is about whether it survives onto the CALLER-VISIBLE record, which is where
# FR-058 says the reader arrives. The tampered seam drops it on a plainly
# VERIFIED result, where `Result` requires no reason and nothing else complains.
proof "T213 — the disclosure is dropped at the record, so an ignored declaration is disclosed nowhere a caller reads" \
  src/runtime/result_join.py \
  "tests/unit/test_result_join.py::test_an_ignored_declaration_is_disclosed_on_the_caller_visible_record" \
  's = s.replace("    if disclosure is not None:", "    if False:")'

# --- and the four that remove the invariant's own instrument ------------------
#
# INV-001's construction-site arms are the half of its sentence that was
# UNMEASURED until this task: a `src/` module constructing
# `Result(VerificationOutcome.VERIFIED, …)` with no verifier in it was planted
# on 2026-08-12 and passed all 200 invariants and all three static gates. The
# arms exist now; these are what keep them from passing over nothing.

proof "T213 invariant — the construction-site scan returns nothing, so an unauthorised Result site is free" \
  tests/invariants/test_result_constructor.py \
  "tests/invariants/test_result_constructor.py::test_the_checker_fires_on_an_unverified_construction_site" \
  's = s.replace("    found: list[str] = []", "    return []\n    found: list[str] = []")'

proof "T213 invariant — the scanner reads only the from-import spelling, so an aliased module path constructs freely" \
  tests/invariants/test_result_constructor.py \
  "tests/invariants/test_result_constructor.py::test_the_checker_sees_a_site_reached_through_the_module_path" \
  's = s.replace("                and _dotted(func.value) in module_paths", "                and False")'

proof "T213 invariant — the artifact test admits every module, so an allowlist edit is the whole of the defence" \
  tests/invariants/test_result_constructor.py \
  "tests/invariants/test_result_constructor.py::test_the_artifact_check_fires_on_a_module_that_holds_none" \
  's = s.replace("    return _names_in_scope(tree) & VERIFICATION_ARTIFACTS", "    return _names_in_scope(tree) | VERIFICATION_ARTIFACTS")'

# The negative control's own arm. A scanner that reports every module naming
# the type would make the allowlist a list of IMPORTERS — a different and much
# weaker property, and one `src/runtime/serving.py` already violates by holding
# `Result` for an annotation and constructing none.
proof "T213 invariant — the scanner reports a module that merely names the type, so the allowlist degrades to a list of importers" \
  tests/invariants/test_result_constructor.py \
  "tests/invariants/test_result_constructor.py::test_the_checker_ignores_a_module_that_only_names_the_type" \
  's = s.replace("        if not bare and not module_paths:\n            continue", "        found.append(path.relative_to(root).as_posix() + \":0\")")'

# --- T131/T132, the value-fault corpus and its shape-and-type-only control ----
#
# SC-006 asserts a verifier detects NOTHING, which is Rule 8's shape: the
# positive result is a failure to detect, and a control that cannot run, that is
# handed an empty corpus, or that errors on every input all report the same bit.
# So the arms here divide the same way T115's block does — some remove the
# CONTROL and require its positive arm to notice, others remove the CORPUS's own
# properties and require the non-vacuity arms to notice. A control proof that
# passed while the corpus was empty would prove nothing about either.
#
# All three were run against the working tree before being declared, and the
# first is the one that matters: neutering the control leaves
# `test_the_control_detects_none_of_the_value_faults` GREEN — correctly, that is
# the vacuity — and turns the positive arm red. That asymmetry is the whole
# claim, and it is why the arm below names the positive test and not the zero.
proof "T132 control — the conformance check detects nothing at all, so SC-006's zero is free" \
  tests/batteries/test_conformance_control.py \
  "tests/batteries/test_conformance_control.py::test_the_positive_control_is_caught_naming_the_shape" \
  's = s.replace("    kind = declared_shape[\x22kind\x22]", "    return ()\n    kind = declared_shape[\x22kind\x22]")'

# The recorded resolution of finding 015's open contradiction, as a gate. E8's
# c1 control asserted zero detections over the NUMERIC class, passed correctly,
# and was structurally blind to the set-typed class its subject was actually
# broken in. Narrowing the declaration must turn this red rather than quietly
# shrinking what the zero covers.
proof "T132 control — the bounded-class declaration narrows, so the zero silently covers less" \
  tests/batteries/test_conformance_control.py \
  "tests/batteries/test_conformance_control.py::test_the_null_states_the_classes_it_bounds" \
  's = s.replace("{\x22numeric_value_error\x22, \x22set_cardinality_error\x22, \x22set_membership_error\x22}", "{\x22numeric_value_error\x22}")'

# The stratum is COMPUTED from the two values and never declared, because a
# declared one survives the case being edited underneath it. Pinning it removes
# the computation without removing the field, which is the drift a reviewer
# would not see.
proof "T131 corpus — the relative magnitude is pinned, so the sub-one-percent stratum stops being measured" \
  tests/batteries/test_conformance_control.py \
  "tests/batteries/test_conformance_control.py::test_the_sub_one_percent_stratum_is_populated_and_computed" \
  's = s.replace("        return abs(self.faulted_value - self.correct_value) / abs(self.correct_value)", "        return 0.0")'

# --- T130, the not-verifiable share report (FR-045, SC-019) -------------------
#
# Three properties, and each is a different way the same document reads as a
# measurement while being something else: a threshold in force that nothing
# declares, an idle window reported as a flawless one, and a required key that
# acquired a default.
proof "T130 — a threshold enters the module, so a bound is in force while the field says none is" \
  src/runtime/reports/not_verifiable.py \
  "tests/unit/test_not_verifiable_report.py::test_the_share_is_never_compared_against_anything" \
  's = s.replace("        if self.total_results == 0:", "        if (self.share or 0.0) > 0.5:\n            pass\n        if self.total_results == 0:")'

proof "T130 — an empty window reports a share of zero, so an idle deployment reads as a flawless one" \
  src/runtime/reports/not_verifiable.py \
  "tests/unit/test_not_verifiable_report.py::test_an_empty_window_has_no_share_rather_than_a_share_of_zero" \
  's = s.replace("        if self.total_results == 0:\n            return None", "        if self.total_results == 0:\n            return 0.0")'

proof "T130 — the reporting window acquires a default, so an unset one stops failing startup" \
  src/contracts/config.py \
  "tests/unit/test_not_verifiable_report.py::test_the_window_length_is_declared_configuration_with_no_default" \
  's = s.replace("no_default_reason=_NO_DEFAULT_REPORTING_WINDOW)", "no_default_reason=_NO_DEFAULT_REPORTING_WINDOW, default=\x223600\x22)")'

# --- T133, provenance coverage (SC-007) ---------------------------------------
#
# SC-007 states a 100% and a zero, and both are free over this tree: the
# hundred is a property of two required dataclass fields, and the zero has an
# empty population because nothing in this repository promotes. So the arms
# below remove the two PREDICATES rather than the types, because a predicate
# that returns no faults reports full coverage and no offenders at once.
proof "T133 — the coverage predicate reports no faults, so 100% is a property of the predicate" \
  tests/contract/test_provenance_coverage.py \
  "tests/contract/test_provenance_coverage.py::test_the_coverage_predicate_catches_a_record_that_carries_nothing" \
  's = s.replace("    provenance = getattr(record, \x22provenance\x22, None)", "    return ()\n    provenance = getattr(record, \x22provenance\x22, None)")'

proof "T133 — the presented-as-validated predicate clears everything, so SC-007's zero is unfalsifiable" \
  tests/contract/test_provenance_coverage.py \
  "tests/contract/test_provenance_coverage.py::test_the_predicate_catches_a_status_with_no_artifact_behind_it" \
  's = s.replace("    faults: list[str] = []", "    return ()\n    faults: list[str] = []")'

# Principle I's own refusal, in the source rather than in the test. This is the
# one arm in the block that removes a shipped mechanism: without it a derived
# contract can cite the file its own derivation read as the artifact that
# corroborated it, which is the exact wording SC-007 rules out.
proof "T133 — the independence refusal goes, so a derivation validates against its own input" \
  src/analysis/provenance.py \
  "tests/contract/test_provenance_coverage.py::test_the_constructor_refuses_both_defects_as_well" \
  's = s.replace("        if validated and self.validated_against == self.source_file:", "        if False:")'

# --- T154/T155/T157/T158, Phase 6's four committed drift corpora --------------
#
# These four corpora are committed with NO consumer: every Phase 6 module that
# would score them, T137 through T153, is open. So there is no detector here to
# remove, and the mechanisms these arms remove are the corpora's OWN — the
# recomputations that stop a committed declaration becoming an oracle, and the
# negative-control populations that stop a trivially wrong detector scoring
# 100%.
#
# That makes the block divide the way T131/T132's does. Some arms remove a
# GUARD and require its planted-defect test to notice; others remove part of a
# POPULATION and require an ablation test to notice. The second kind is the one
# that matters here: every criterion these corpora serve — SC-008, SC-009,
# SC-020, SC-021, SC-026 — is phrased as 100% or zero, which is the
# experiment-design skill's Rule 8 shape exactly, and its tell is a perfect
# score on an ablation suite. An arm below that stopped failing would mean the
# corpus had quietly become one only a correct detector could be measured on.
#
# Every selector is node-level. A bare-file selector on
# tests/unit/test_drift_fixtures.py would be scored UNUSABLE the moment any one
# of its 57 tests failed untampered.

proof "T154 corpus — a check run may observe two revisions, so SC-008's 'same run as the commit' stops being falsifiable" \
  tests/fixtures/drift_corpora/source.py \
  "tests/unit/test_drift_fixtures.py::test_a_check_run_observing_two_revisions_is_refused" \
  's = s.replace("    if len(set(runs)) != len(runs):", "    if False:")'

proof "T154 corpus — the declared breaking verdict stops being recomputed, so a committed boolean becomes the oracle" \
  tests/fixtures/drift_corpora/source.py \
  "tests/unit/test_drift_fixtures.py::test_a_declared_breaking_verdict_that_disagrees_with_the_diff_is_refused" \
  's = s.replace("    if bool(entry[\x22breaking\x22]) != breaking:", "    if False:")'

# The classifier this arm named moved to src/analysis/source_drift.py with T138,
# so the loader can import it rather than restate it. The claim did not fall:
# a rename that also changes the signature still has to declare both. Path
# substitution, not a strike.
proof "T154 corpus — a rename may change the signature, so two changes are reported as one" \
  src/analysis/source_drift.py \
  "tests/unit/test_drift_fixtures.py::test_a_rename_whose_signature_moved_is_refused" \
  's = s.replace("        if _signature(before[old]) != _signature(after[new]):", "        if False:")'

# The Rule 8 arm for the source clock: with the non-breaking revisions gone,
# 'always report drift' scores a perfect 100% on SC-008 and nothing notices.
proof "T154 corpus — the population loses its non-breaking revisions, so a detector that always fires scores 100%" \
  tests/fixtures/drift_corpora/source.py \
  "tests/unit/test_drift_fixtures.py::test_a_detector_that_reports_drift_on_every_revision_fails_this_corpus" \
  's = s.replace("    return tuple(revisions)", "    return tuple(r for r in revisions if r.breaking or r.parent is None)")'

# The subset-presented-as-a-total defect, planted directly: the scoreable
# denominator silently becomes the whole corpus, including the base revision
# that can carry no diff at all.
proof "T154 corpus — the scoreable denominator becomes the whole corpus, so the partition stops summing to its total" \
  tests/fixtures/drift_corpora/source.py \
  "tests/unit/test_drift_fixtures.py::test_the_source_corpuss_scoreable_denominator_excludes_the_base_revision" \
  's = s.replace("        \x22revisions_with_a_parent_and_therefore_a_diff\x22: len(scoreable),", "        \x22revisions_with_a_parent_and_therefore_a_diff\x22: len(revisions),")'

# plan.md line 830: inferring the change time from first observation measures
# the detector against itself. This arm lets the corpus do exactly that.
proof "T155 corpus — a change time may coincide with an observation, so it can be read off the detector's own reading" \
  tests/fixtures/drift_corpora/deployment.py \
  "tests/unit/test_drift_fixtures.py::test_a_change_time_read_off_an_observation_is_refused" \
  's = s.replace("            if observation[\x22at\x22] == change_at:", "            if False:")'

proof "T155 corpus — the declared latency stops being recomputed, so a committed number becomes the measurement" \
  tests/fixtures/drift_corpora/deployment.py \
  "tests/unit/test_drift_fixtures.py::test_a_declared_latency_that_disagrees_with_the_clock_is_refused" \
  's = s.replace("            if latency != arm[\x22expected_latency_seconds\x22]:", "            if False:")'

proof "T155 corpus — the population loses the scenario with nothing withdrawn, so 'disable everything' scores 100%" \
  tests/fixtures/drift_corpora/deployment.py \
  "tests/unit/test_drift_fixtures.py::test_a_detector_that_disables_the_target_on_every_poll_fails_this_corpus" \
  's = s.replace("    return tuple(scenarios)", "    return tuple(s for s in scenarios if not s.is_negative_control)")'

proof "T157 corpus — a fixture may name a terminal state outside the taxonomy, so FR-006's closed set opens through test data" \
  tests/fixtures/drift_corpora/spec_withdrawn.py \
  "tests/unit/test_drift_fixtures.py::test_a_terminal_state_outside_the_taxonomy_is_refused" \
  's = s.replace("    if name not in terminal.NAMES:", "    if False:")'

proof "T157 corpus — the age stops being recomputed from the last successful fetch, so T149's anchor is unenforced" \
  tests/fixtures/drift_corpora/spec_withdrawn.py \
  "tests/unit/test_drift_fixtures.py::test_a_declared_age_that_disagrees_with_the_wall_clock_is_refused" \
  's = s.replace("            if age != call[\x22age_seconds\x22]:", "            if False:")'

proof "T157 corpus — the calls lose every non-stale one, so 'mark every result stale' satisfies SC-021's first clause" \
  tests/fixtures/drift_corpora/spec_withdrawn.py \
  "tests/unit/test_drift_fixtures.py::test_an_implementation_marking_every_result_stale_fails_this_corpus" \
  's = s.replace("            calls=tuple(calls),", "            calls=tuple(c for c in calls if c.stale),")'

proof "T157 corpus — the population loses its unchanged restorations, so 'report drift on every restore' scores 100%" \
  tests/fixtures/drift_corpora/spec_withdrawn.py \
  "tests/unit/test_drift_fixtures.py::test_an_implementation_reporting_drift_on_every_restoration_fails" \
  's = s.replace("    return tuple(scenarios)", "    return tuple(s for s in scenarios if s.drift_on_restore)")'

proof "T158 corpus — a withdrawal may enter the corpus, so SC-026 is scored on T157's timeline instead of its own" \
  tests/fixtures/drift_corpora/operation_added.py \
  "tests/unit/test_drift_fixtures.py::test_a_withdrawal_planted_into_this_corpus_is_refused" \
  's = s.replace("        if fetch[\x22state\x22] != PUBLISHED_NON_EMPTY:", "        if False:")'

proof "T158 corpus — an outcome may be declared for an operation that never appears, so an expectation exercises nothing" \
  tests/fixtures/drift_corpora/operation_added.py \
  "tests/unit/test_drift_fixtures.py::test_an_outcome_declared_for_an_operation_that_never_appears_is_refused" \
  's = s.replace("    if declared != reached:", "    if False:")'

proof "T158 corpus — a newly appearing operation may carry no outcome, so FR-051's fail-closed is asserted by omission" \
  tests/fixtures/drift_corpora/operation_added.py \
  "tests/unit/test_drift_fixtures.py::test_an_addition_with_no_declared_outcome_is_refused" \
  's = s.replace("            if op_id not in outcomes:", "            if False:")'

proof "T158 corpus — the population loses the scenario adding nothing, so 'refuse every operation' scores 100%" \
  tests/fixtures/drift_corpora/operation_added.py \
  "tests/unit/test_drift_fixtures.py::test_an_implementation_refusing_every_operation_fails_this_corpus" \
  's = s.replace("    return tuple(scenarios)", "    return tuple(s for s in scenarios if not s.is_negative_control)")'

# --- T153 — FR-051's ordinary successful-fetch increment ----------------------
#
# T158 is now the consumer. These arms remove the increment's own guards:
# refuse a non-admissible fetch, compare against the last inspected (clean)
# set, carry pre-existing clean operations, inspect newly appearing before
# they become available, fail closed per operation rather than per target,
# and admit the clean member of a mixed fetch. Every selector is node-level.

proof "T153 — a non-admissible fetch is inspected anyway" \
  src/analysis/reinspect.py \
  "tests/contract/test_reinspect.py::test_a_non_admissible_fetch_is_refused" \
  's = s.replace("    if decision.state not in ADMISSIBLE_STATES:", "    if False:")'

proof "T153 — every fetch re-inspects the already-clean set" \
  src/analysis/reinspect.py \
  "tests/contract/test_reinspect.py::test_republishing_an_already_inspected_set_inspects_nothing" \
  's = s.replace("    return tuple(sorted(frozenset(fetched) - frozenset(last_inspected)))", "    return tuple(sorted(frozenset(fetched)))")'

proof "T153 — pre-existing operations are dropped, so refuse-everything scores 100%" \
  src/analysis/reinspect.py \
  "tests/contract/test_reinspect.py::test_pre_existing_operations_stay_available_when_nothing_is_added" \
  's = s.replace("        _still_clean(op_id) for op_id in sorted(fetched & inspected)", "        _still_clean(op_id) for op_id in sorted(frozenset())")'

proof "T153 — newly appearing operations become available without inspection" \
  src/analysis/reinspect.py \
  "tests/contract/test_reinspect.py::test_newly_appearing_operations_are_inspected_before_they_become_available" \
  's = s.replace("        inspect_operation(\n            op_id, handler_index=handler_index, codebase=codebase\n        )", "        _still_clean(op_id)")'

proof "T153 — a mixed fetch drops the clean member because the others failed" \
  src/analysis/reinspect.py \
  "tests/contract/test_reinspect.py::test_a_mixed_fetch_admits_the_clean_member_and_refuses_the_others" \
  's = s.replace("        outcomes=(*still_available, *inspected_now),", "        outcomes=(*still_available, *tuple(o for o in inspected_now if o.denied)),")'

proof "T153 — a mixed fetch admits the denied members because one passed" \
  src/analysis/reinspect.py \
  "tests/contract/test_reinspect.py::test_a_mixed_fetch_admits_the_clean_member_and_refuses_the_others" \
  's = s.replace("    inspected_now = new_outcomes", "    inspected_now = tuple(_still_clean(o.operation_id) for o in new_outcomes)")'

proof "T153 — an uninspectable addition takes the target offline" \
  src/analysis/reinspect.py \
  "tests/contract/test_reinspect.py::test_an_uninspectable_addition_is_refused_and_does_not_take_the_target_offline" \
  's = s.replace("    return Reinspection(newly_appearing=newly, report=report)", "    raise DeputyInspectionError(\x22target offline\x22)\n    return Reinspection(newly_appearing=newly, report=report)")'

proof "T153 — no newly appearing operation is recorded, so additions never become available" \
  src/analysis/reinspect.py \
  "tests/contract/test_reinspect.py::test_every_operation_added_scenario_matches_the_loader" \
  's = s.replace("    newly = appearing(fetched, inspected)", "    newly = ()")'

# --- T145 — path-level reachability backstop, not a trigger -------------------
#
# Records a failing precondition on a user-facing call. Does not emit
# path-level probe as a CheckResult.trigger. tick's refusal is left intact
# (T144's proof). The record is not ArtifactDrift or FailedRefetch: FR-031's
# terms cannot be stated without inventing versions that were not obtained.

proof "T145 — an empty operation id is recorded as a path-level backstop" \
  src/runtime/drift/backstop.py \
  "tests/contract/test_drift_backstop.py::test_an_empty_operation_id_is_refused" \
  's = s.replace("    if not operation_id:", "    if False:")'

proof "T145 — an empty deployment id is recorded as a path-level backstop" \
  src/runtime/drift/backstop.py \
  "tests/contract/test_drift_backstop.py::test_an_empty_deployment_id_is_refused" \
  's = s.replace("    if not deployment_id:", "    if False:")'

proof "T145 — an empty observation is recorded as a path-level backstop" \
  src/runtime/drift/backstop.py \
  "tests/contract/test_drift_backstop.py::test_an_empty_observation_is_refused" \
  's = s.replace("    if not observed:", "    if False:")'

proof "T145 — a backstop with no detected_at is recorded" \
  src/runtime/drift/backstop.py \
  "tests/contract/test_drift_backstop.py::test_an_empty_detected_at_is_refused" \
  's = s.replace("    if not detected_at:", "    if False:")'

proof "T145 — the backstop document carries trigger=path-level probe" \
  src/runtime/drift/backstop.py \
  "tests/contract/test_drift_backstop.py::test_the_document_is_not_a_trigger" \
  's = s.replace("            \x22detected_at\x22: self.detected_at,", "            \x22detected_at\x22: self.detected_at,\n            \x22trigger\x22: \x22path-level probe\x22,")'

# --- T146 — disable the observed affected operation (FR-030, SC-009) ----------
#
# Disable what the signal (or the consecutive served-id sets the movement
# was built from) names. FailedRefetch disables nothing. Source-clock
# ArtifactDrift without a finding names no operation. T150 is not a second
# deny-all here.

proof "T146 — a withdrawal disables the whole served set, including health" \
  src/runtime/drift/disable.py \
  "tests/contract/test_drift_disable.py::test_bulk_withdrawal_leaves_health_enabled" \
  's = s.replace("    return tuple(sorted(frozenset(served_before) - frozenset(served_after)))", "    return tuple(sorted(frozenset(served_before)))")'

proof "T146 — list_shipments takes list_parts with it by prefix" \
  src/runtime/drift/disable.py \
  "tests/contract/test_drift_disable.py::test_a_prefix_match_cannot_take_the_neighbour" \
  's = s.replace("    return tuple(sorted(frozenset(served_before) - frozenset(served_after)))", "    return tuple(sorted(op for op in served_before if op.startswith(\x22list_\x22)))")'

proof "T146 — a FailedRefetch disables the served set it was handed" \
  src/runtime/drift/disable.py \
  "tests/contract/test_drift_disable.py::test_a_failed_refetch_disables_no_operation" \
  's = s.replace("                disabled=(),", "                disabled=tuple(sorted(served_before or ())),")'

proof "T146 — a source-clock signal with no named operation disables health" \
  src/runtime/drift/disable.py \
  "tests/contract/test_drift_disable.py::test_a_source_signal_that_cannot_name_an_operation_disables_nothing" \
  's = s.replace("                        disabled=NO_NAMED_OPERATION,", "                        disabled=(\x22health\x22),")'

proof "T146 — C-010 disables the non-breaking half because the finding named any operation" \
  src/runtime/drift/disable.py \
  "tests/contract/test_drift_disable.py::test_c010_does_not_disable_the_non_breaking_half" \
  's = s.replace("                    disabled=source_finding.operations,", "                    disabled=source_finding.operations + (\x22health\x22),")'

proof "T146 — a deployment-clock ArtifactDrift without served sets invents the affected set" \
  src/runtime/drift/disable.py \
  "tests/contract/test_drift_disable.py::test_deployment_artifact_drift_without_served_sets_is_refused" \
  's = s.replace("                if served_before is None or served_after is None:", "                if False:")'

proof "T146 — remaining keeps the disabled operations working" \
  src/runtime/drift/disable.py \
  "tests/contract/test_drift_disable.py::test_bulk_withdrawal_leaves_health_enabled" \
  's = s.replace("        operation_id for operation_id in served if operation_id not in blocked", "        operation_id for operation_id in served")'

proof "T146 — identical served sets are reported as a total withdrawal" \
  src/runtime/drift/disable.py \
  "tests/contract/test_drift_disable.py::test_the_negative_control_disables_nothing" \
  's = s.replace("    return tuple(sorted(frozenset(served_before) - frozenset(served_after)))", "    return tuple(sorted(frozenset(served_before)))")'

proof "T172 instrument — the contradiction scan matches nothing, so 'no unrefused offer' is free" \
  tests/contract/test_platform_statement.py \
  "tests/contract/test_platform_statement.py::test_the_contradiction_scan_fires_on_a_planted_offer" \
  's = s.replace("    for match in OFFER.finditer(collapsed):", "    for match in OFFER.finditer(collapsed[:0]):")'

proof "T172 — preflight stops stating Linux only, so the platform claim is gone" \
  src/supervisor/preflight.py \
  "tests/contract/test_platform_statement.py::test_every_required_surface_states_linux_only" \
  's = s.replace("**OD-17**: Linux only, no degraded mode.", "**OD-17**: any Unix.").replace("Linux-only by construction", "Unix-only by construction")'

proof "T172 — README offers macOS without the OD-17 refusal" \
  README.md \
  "tests/contract/test_platform_statement.py::test_live_trees_do_not_add_an_unrefused_platform_contradiction" \
  's = s.replace("and Linux is the only supported\nplatform (OD-17).", "and Linux or macOS is supported.")'

# --- T168 — FR-033 portability of emitted artifacts --------------------------
#
# Walk of the writers, not a second redaction filter. Secret already redacts;
# FR-055 already moves hostnames out of the hashed payload. Each arm plants
# rather than reasons. drop_bytecode is in apply_tamper.

proof "T168 instrument — the leak scanner matches nothing, so no writer interpolates is free" \
  tests/contract/test_artifact_portability.py \
  "tests/contract/test_artifact_portability.py::test_the_scanner_catches_a_planted_leak" \
  's = s.replace("    found: list[str] = []", "    found: list[str] = []\n    return found")'

proof "T168 — WRITERS drops the journal, so the named population shrinks" \
  tests/contract/test_artifact_portability.py \
  "tests/contract/test_artifact_portability.py::test_named_writers_are_the_population" \
  's = s.replace("    Path(\x22src/runtime/journal.py\x22),\n", "")'

proof "T168 — admission_record fills decided_by_host from the operator hostname" \
  src/analysis/admission_record.py \
  "tests/contract/test_artifact_portability.py::test_no_writer_interpolates_operator_identity" \
  's = s.replace("    if decided_by_host is not None:\n        document[\x22decided_by_host\x22] = decided_by_host", "    document[\x22decided_by_host\x22] = socket.gethostname() if decided_by_host is None else decided_by_host")'

proof "T168 — journal interpolates os.getcwd into a persisted payload" \
  src/runtime/journal.py \
  "tests/contract/test_artifact_portability.py::test_no_writer_interpolates_operator_identity" \
  's = s.replace("        encoded = _encode(payload)", "        encoded = _encode({**dict(payload), \x22cwd\x22: os.getcwd()})")'

proof "T168 — trace interpolates Path.home into a span record" \
  src/runtime/trace.py \
  "tests/contract/test_artifact_portability.py::test_no_writer_interpolates_operator_identity" \
  's = s.replace("            \x22detail\x22: dict(self.detail),", "            \x22detail\x22: dict(self.detail), \x22home\x22: Path.home(),")'

proof "T168 — decision log interpolates os.Hostname into the detail column" \
  src/proxy/decisionlog.go \
  "tests/contract/test_artifact_portability.py::test_the_decision_log_fingerprints_credentials_rather_than_revealing_them" \
  's = s.replace("\t\trec.CredentialFingerprint,\n\t\trec.Detail,\n", "\t\trec.CredentialFingerprint,\n\t\trec.Detail + func() string { h, _ := os.Hostname(); return h }(),\n")'

proof "T168 — operator_log interpolates Secret.reveal into the channel" \
  src/contracts/operator_log.py \
  "tests/contract/test_artifact_portability.py::test_no_writer_interpolates_operator_identity" \
  's = s.replace("        payload = (body + \x22\\n\x22).encode(\x22utf-8\x22, errors=\x22replace\x22)", "        payload = (body + secret.reveal() + \x22\\n\x22).encode(\x22utf-8\x22, errors=\x22replace\x22)")'

proof "T168 — a feature-001 harness file enters the writer walk" \
  tests/contract/test_artifact_portability.py \
  "tests/contract/test_artifact_portability.py::test_dated_records_are_outside_the_walk" \
  's = s.replace("    Path(\x22src/proxy/decisionlog.go\x22),\n)", "    Path(\x22src/proxy/decisionlog.go\x22),\n    Path(\x22specs/001-discovery-validation/harness/ceiling-test/envroot.py\x22),\n)")'

# --- T161 / T162 / T163, Phase 7 credential planes, topology, selection ------
#
# Every arm plants rather than reasons, and names a node. Mix of planes, a
# holder that must never hold, a Kind.SECRET becoming a str, co-location
# inferred from the runtime address, a topology key acquiring a default, and
# three ways selection grows a vendor in the core path.

proof "T161 planes — a target-named Secret is accepted as the runtime provider credential" \
  src/contracts/credentials.py \
  "tests/unit/test_credentials.py::test_a_target_named_secret_is_refused_as_the_runtime_provider_credential" \
  's = s.replace("        if self.secret.name != expected:", "        if False:")'

proof "T161 holders — analysis, the execution environment and tick may hold a credential plane" \
  src/contracts/credentials.py \
  "tests/unit/test_credentials.py::test_analysis_execution_and_tick_may_not_hold_either_plane" \
  's = s.replace("        if self.holder in NEVER_HOLD:", "        if False:")'

proof "T161 holders — the enforcement point may hold the provider credential" \
  src/contracts/credentials.py \
  "tests/unit/test_credentials.py::test_the_enforcement_point_may_not_hold_the_provider_credential" \
  's = s.replace("        if (self.plane, self.holder) not in ALLOWED_HOLDERS:", "        if False:")'

proof "T161 schema — the provider credential is loaded as a str rather than a Secret" \
  src/contracts/config.py \
  "tests/unit/test_credentials.py::test_the_runtime_provider_credential_is_a_secret_not_a_str" \
  's = s.replace("Key(\"F2A_PROVIDER_CREDENTIAL\", Kind.SECRET, \"FR-036\",", "Key(\"F2A_PROVIDER_CREDENTIAL\", Kind.STR, \"FR-036\",")'

proof "T162 co-location — a missing analysis address is filled from the runtime" \
  src/contracts/topology.py \
  "tests/unit/test_topology.py::test_a_missing_analysis_address_is_not_filled_from_the_runtime" \
  's = s.replace("_address(ANALYSIS, ANALYSIS_ADDR_KEY, self.analysis)", "_address(ANALYSIS, ANALYSIS_ADDR_KEY, self.analysis or self.runtime)")'

proof "T162 schema — the analysis address acquires a default, so co-location is assumed" \
  src/contracts/config.py \
  "tests/unit/test_topology.py::test_topology_keys_have_no_default" \
  's = s.replace(chr(34)+"the runtime address"+chr(34)+"),", chr(34)+"the runtime address"+chr(34)+", default="+chr(34)+"127.0.0.1:1"+chr(34)+"),")'

proof "T163 selection — an unknown provider is returned rather than refused" \
  src/runtime/providers/select.py \
  "tests/unit/test_provider_select.py::test_an_unknown_provider_is_refused_at_selection" \
  's = s.replace("    provider = require_provider(str(config[\"MODEL_PROVIDER\"]))\n    model = str(config[\"MODEL_ID\"])\n    return SelectedProvider(\n        driver=driver_for(provider),\n        provider=provider,\n        model=model,\n    )", "    provider = str(config[\"MODEL_PROVIDER\"])\n    model = str(config[\"MODEL_ID\"])\n    return SelectedProvider(\n        driver=object(),\n        provider=provider,\n        model=model,\n    )")'

proof "T163 selection — select.py imports a wire driver, so a vendor enters the core path" \
  src/runtime/providers/select.py \
  "tests/unit/test_provider_select.py::test_select_does_not_import_a_wire_driver" \
  's = s.replace("from src.runtime.providers import driver_for\n", "from src.runtime.providers import driver_for\nfrom src.runtime.providers.wire_anthropic import AnthropicDriver\n")'

proof "T163 selection — driver_for is not called, so the registry is restated" \
  src/runtime/providers/select.py \
  "tests/unit/test_provider_select.py::test_select_calls_driver_for_and_does_not_duplicate_the_registry" \
  's = s.replace("        driver=driver_for(provider),", "        driver=object(),")'

# --- T159 / T160, Phase 7 images and compose ---------------------------------
#
# Every arm plants rather than reasons, and names a node. A named image walk
# that shrinks, the one-image rule, analysis inventing a process, an unpinned
# Go checksum, finding 024's eight names and clone mask, the T172 tripwire
# retargeted onto unconfined, session-store-once, the credential planes, FR-043
# fixture marking, FR-049 host cgroupns, compose leaving REQUIRED_SURFACES,
# and the T119 run-time image population.

proof "T159 walk — PYTHON_PRODUCT_IMAGES drops analysis, so a Python image ships un-scanned" \
  tests/invariants/test_sandbox_image.py \
  "tests/invariants/test_sandbox_image.py::test_image_policy_walks_a_named_python_set_not_every_dockerfile" \
  's = s.replace("    IMAGES / \"analysis.Dockerfile\",\n", "")'

proof "T159 one-image — runtime starts FROM a different base than dev" \
  deploy/images/runtime.Dockerfile \
  "tests/invariants/test_sandbox_image.py::test_runtime_and_dev_share_a_base_and_a_lock" \
  's = s.replace("FROM python:3.12-slim-bookworm AS builder", "FROM python:3.11-slim-bookworm AS builder")'

proof "T159 analysis — the image invents a serve loop instead of failing loud" \
  deploy/images/analysis.Dockerfile \
  "tests/invariants/test_sandbox_image.py::test_src_analysis_has_no_main_and_the_image_fails_loud" \
  's = s.replace("no process to start", "starting analysis")'

proof "T159 enforcement — GO_SHA256 acquires a default, so the checksum is optional" \
  deploy/images/enforcement.Dockerfile \
  "tests/invariants/test_sandbox_image.py::test_enforcement_requires_go_sha256_and_does_not_fetch_in_the_shipped_stage" \
  's = s.replace("ARG GO_SHA256", "ARG GO_SHA256 =deadbeef")'

proof "T160 finding 024 — pivot_root leaves the unconditional eight-name rule" \
  deploy/compose/seccomp/session.json \
  "tests/contract/test_compose_bundle.py::test_finding_024_profile_exposes_the_eight_names_without_the_capability_gate" \
  's = s.replace("        \"pivot_root\",\n", "")'

proof "T160 finding 024 — the non-CAP_SYS_ADMIN clone rule gets its argument mask back" \
  deploy/compose/seccomp/session.json \
  "tests/contract/test_compose_bundle.py::test_finding_024_clone_argument_mask_is_removed" \
  's = s.replace("      \"names\": [\n        \"clone\"\n      ],\n      \"action\": \"SCMP_ACT_ALLOW\",\n      \"excludes\": {\n        \"caps\": [\n          \"CAP_SYS_ADMIN\"\n        ],\n        \"arches\": [\n          \"s390\",\n          \"s390x\"\n        ]\n      }", "      \"names\": [\n        \"clone\"\n      ],\n      \"action\": \"SCMP_ACT_ALLOW\",\n      \"excludes\": {\n        \"caps\": [\n          \"CAP_SYS_ADMIN\"\n        ],\n        \"arches\": [\n          \"s390\",\n          \"s390x\"\n        ]\n      },\n      \"args\": [{\n        \"index\": 0,\n        \"value\": 2114060288,\n        \"op\": \"SCMP_CMP_MASKED_EQ\"\n      }]")'

proof "T160 tripwire — compose offers seccomp=unconfined as an alternative" \
  deploy/compose/compose.yaml \
  "tests/contract/test_platform_statement.py::test_compose_bundle_does_not_offer_unconfined_or_a_degraded_sandbox" \
  's = s.replace("The operator'\''s seccomp action is a file this bundle ships", "The operator may set seccomp=unconfined instead")'

proof "T160 session-store-once — runtime starts without waiting for supervisor" \
  deploy/compose/compose.yaml \
  "tests/contract/test_compose_bundle.py::test_the_session_store_is_created_before_any_second_process_attaches" \
  's = s.replace("    volumes:\n      - f2a-state:/var/lib/f2a\n    depends_on:\n      supervisor:\n        condition: service_completed_successfully\n    # Provider plane only.", "    volumes:\n      - f2a-state:/var/lib/f2a\n    # Provider plane only.")'

proof "T160 planes — analysis holds the provider credential" \
  deploy/compose/compose.yaml \
  "tests/contract/test_compose_bundle.py::test_credentials_sit_on_the_right_services_only" \
  's = s.replace("      F2A_PROXY_UPSTREAM_ADDR: target:9000\n    # Holds neither credential plane (FR-036). Does not open the session store.", "      F2A_PROXY_UPSTREAM_ADDR: target:9000\n      F2A_PROVIDER_CREDENTIAL: ${F2A_PROVIDER_CREDENTIAL:?required}\n    # Holds neither credential plane (FR-036). Does not open the session store.")'

proof "T160 FR-043 — compose names a reference-application hostname" \
  deploy/compose/compose.yaml \
  "tests/contract/test_compose_bundle.py::test_fixture_topology_is_marked_unvalidated_not_a_product_default" \
  's = s.replace("Reference-application hostnames are not what this bundle ships.", "Mealie hostnames are not what this bundle ships.")'

proof "T160 FR-049 — supervisor loses host cgroupns" \
  deploy/compose/compose.yaml \
  "tests/contract/test_compose_bundle.py::test_supervisor_alone_gets_the_cgroup_mount_and_the_seccomp_profile" \
  's = s.replace("    cgroup: host\n", "")'

proof "T172 retarget — compose.yaml leaves REQUIRED_SURFACES" \
  tests/contract/test_platform_statement.py \
  "tests/contract/test_platform_statement.py::test_every_required_surface_states_linux_only" \
  's = s.replace("    Path(\"deploy/compose/compose.yaml\"),\n", "")'

proof "T119 run-time images — RUNTIME_IMAGES drops enforcement" \
  tests/unit/test_codegraph_invocation.py \
  "tests/unit/test_codegraph_invocation.py::test_run_time_images_carry_no_javascript_toolchain" \
  's = s.replace("    REPO / \"deploy\" / \"images\" / \"enforcement.Dockerfile\",\n", "")'

# --- T171, fail-loud through the shipped bundle --------------------------------
#
# Static half only. The live docker-run arms skip when the daemon is absent
# or the image is not loaded, so a proof that named one of those nodes would
# skip in CI and read as coverage. Every arm plants rather than reasons,
# names a node, and uses a needle that is unique in its file.

proof "T171 runtime — CMD no longer invokes the runtime entry point" \
  deploy/images/runtime.Dockerfile \
  "tests/integration/test_bundle_failloud.py::test_the_runtime_image_invokes_runtime_main" \
  's = s.replace("CMD [\"python\", \"-m\", \"src.runtime.main\"]", "CMD [\"python\", \"-c\", \"pass\"]")'

proof "T171 supervisor — CMD no longer invokes the supervisor entry point" \
  deploy/images/supervisor.Dockerfile \
  "tests/integration/test_bundle_failloud.py::test_the_supervisor_image_invokes_supervisor_main" \
  's = s.replace("CMD [\"python\", \"-m\", \"src.supervisor.main\"]", "CMD [\"python\", \"-c\", \"pass\"]")'

proof "T171 runtime — ENTRYPOINT true swallows the fail-loud path" \
  deploy/images/runtime.Dockerfile \
  "tests/integration/test_bundle_failloud.py::test_the_runtime_image_invokes_runtime_main" \
  's = s.replace("# OD-36: report+exit. Linux only, no degraded mode (OD-17).\nCMD [\"python\", \"-m\", \"src.runtime.main\"]", "# OD-36: report+exit. Linux only, no degraded mode (OD-17).\nENTRYPOINT [\"true\"]\nCMD [\"python\", \"-m\", \"src.runtime.main\"]")'

proof "T171 compose — runtime tool-result bound acquires a default" \
  deploy/compose/compose.yaml \
  "tests/integration/test_bundle_failloud.py::test_compose_supplies_no_default_keys_as_required_substitutions" \
  's = s.replace("      TOOL_RESULT_BOUND_TOKENS: ${TOOL_RESULT_BOUND_TOKENS:?required}", "      TOOL_RESULT_BOUND_TOKENS: ${TOOL_RESULT_BOUND_TOKENS:-8000}")'

proof "T171 compose — supervisor memory bound is dropped" \
  deploy/compose/compose.yaml \
  "tests/integration/test_bundle_failloud.py::test_compose_supplies_no_default_keys_as_required_substitutions" \
  's = s.replace("      SANDBOX_MEMORY_MAX: ${SANDBOX_MEMORY_MAX:?required}\n", "")'

proof "T171 analysis — unset entry check inverted so an empty module is execd" \
  deploy/images/analysis.Dockerfile \
  "tests/integration/test_bundle_failloud.py::test_the_analysis_image_is_not_a_third_fail_loud_main" \
  's = s.replace("if [ -z ", "if [ -n ")'

proof "T171 runtime image — target credential baked into a layer" \
  deploy/images/runtime.Dockerfile \
  "tests/integration/test_bundle_failloud.py::test_the_runtime_image_does_not_hold_the_target_credential" \
  's = s.replace("CMD [\"python\", \"-m\", \"src.runtime.main\"]", "ENV F2A_TARGET_CREDENTIAL=x\nCMD [\"python\", \"-m\", \"src.runtime.main\"]")'

proof "T171 supervisor image — provider credential baked into a layer" \
  deploy/images/supervisor.Dockerfile \
  "tests/integration/test_bundle_failloud.py::test_supervisor_analysis_and_sandbox_images_do_not_hold_the_provider_credential" \
  's = s.replace("CMD [\"python\", \"-m\", \"src.supervisor.main\"]", "ENV F2A_PROVIDER_CREDENTIAL=x\nCMD [\"python\", \"-m\", \"src.supervisor.main\"]")'

proof "T171 skip — missing docker no longer names the daemon" \
  tests/integration/test_bundle_failloud.py \
  "tests/integration/test_bundle_failloud.py::test_a_missing_docker_daemon_skip_names_the_daemon" \
  's = s.replace("Docker daemon is absent: `docker` is not on PATH", "docker is not on PATH")'

# --- T164 — SC-010 four-provider US1 battery ---------------------------------
#
# Every arm plants rather than reasons, and names a node. A vendor string
# constant in the battery or the core path, a missing configured model, a
# three-provider set, a skip, a vendor SDK import, select ignoring
# MODEL_PROVIDER, and the transport residual returning a body instead of
# refusing.

proof "T164 battery — a vendor name enters this file as a string constant" \
  tests/batteries/test_four_providers.py \
  "tests/batteries/test_four_providers.py::test_the_battery_and_core_path_name_no_vendor" \
  's = s.replace("CONFIGURATION_ONLY = True", "CONFIGURATION_ONLY = \"anthropic\"")'

proof "T164 core path — loop.py names a vendor as a string constant" \
  src/runtime/loop.py \
  "tests/batteries/test_four_providers.py::test_the_battery_and_core_path_name_no_vendor" \
  's = s.replace("_ANY_PROVIDER = \"\\x00no-prior-provider\"", "_ANY_PROVIDER = \"anthropic\"")'

proof "T164 transport — call returns a body instead of TransportUnavailableError" \
  src/runtime/providers/base.py \
  "tests/batteries/test_four_providers.py::test_the_first_turn_transport_is_unavailable" \
  's = s.replace("        raise TransportUnavailableError(\n            f\"{self.provider}: the transport half of this driver requires \"", "        return {}; raise TransportUnavailableError(\n            f\"{self.provider}: the transport half of this driver requires \"")'

proof "T164 skip — the first-turn arm skips instead of asserting the residual" \
  tests/batteries/test_four_providers.py \
  "tests/batteries/test_four_providers.py::test_the_battery_does_not_skip_a_provider" \
  's = s.replace("    selected = _select(provider)\n    request = selected.driver.build_request(", "    pytest.skip(\"live vendor SDK\")\n    selected = _select(provider)\n    request = selected.driver.build_request(")'

proof "T164 coverage — MODEL_BY_PROVIDER drops a closed provider" \
  tests/batteries/test_four_providers.py \
  "tests/batteries/test_four_providers.py::test_every_closed_provider_has_a_configured_model" \
  's = s.replace("    XAI: \"grok-4.5\",\n", "")'

proof "T164 four — SC-010 accepts three independent providers" \
  tests/batteries/test_four_providers.py \
  "tests/batteries/test_four_providers.py::test_sc010_requires_four_independent_providers" \
  's = s.replace("    assert len(PROVIDERS) == 4, (", "    assert len(PROVIDERS) == 3, (")'

proof "T164 sdk — the battery imports a vendor SDK as a required dependency" \
  tests/batteries/test_four_providers.py \
  "tests/batteries/test_four_providers.py::test_the_battery_does_not_import_a_wire_driver_or_vendor_sdk" \
  's = s.replace("def test_the_residual_is_recorded() -> None:\n    record_evidence(", "def test_the_residual_is_recorded() -> None:\n    import anthropic\n    record_evidence(")'

proof "T164 select — MODEL_PROVIDER is ignored, so every run shares one vendor" \
  tests/batteries/test_four_providers.py \
  "tests/batteries/test_four_providers.py::test_the_us1_path_is_selectable_for_every_provider" \
  's = s.replace("        \"MODEL_PROVIDER\": provider,\n", "        \"MODEL_PROVIDER\": PROVIDERS[0],\n")'

# --- T170 — cassette-backed tests over the core path -------------------------
#
# Every arm plants rather than reasons, and names a node. The loop hook, the
# journal column, the client flag that would collapse this file to T061, a
# missing cassette, a shared vendor, a fake call, a derived cassette cited as
# recorded, and the isolation assertion that T061 does not drive the loop.

proof "T170 core-path hook — the client ignores the loops provider_states" \
  tests/conformance/test_core_path_cassettes.py \
  "tests/conformance/test_core_path_cassettes.py::test_the_loop_round_trips_cassette_state_for_every_provider" \
  's = s.replace("CORE_PATH_STATES = True", "CORE_PATH_STATES = False")'

proof "T170 loop record — _record drops provider_state so the next turn carries nothing" \
  src/runtime/loop.py \
  "tests/conformance/test_core_path_cassettes.py::test_the_loop_round_trips_cassette_state_for_every_provider" \
  's = s.replace("            provider=response.provider,\n            provider_state=response.provider_state,\n            tool_calls=tuple(response.tool_calls),", "            provider=response.provider,\n            provider_state=None,\n            tool_calls=tuple(response.tool_calls),")'

proof "T170 journal — commit_outcome omits the opaque column the loop just received" \
  src/runtime/loop.py \
  "tests/conformance/test_core_path_cassettes.py::test_the_loop_round_trips_cassette_state_for_every_provider" \
  's = s.replace("            payload=encode_model_outcome(response),\n            provider_state=response.provider_state, at=self.clock())", "            payload=encode_model_outcome(response),\n            provider_state=None, at=self.clock())")'

proof "T170 select — MODEL_PROVIDER is ignored, so every cassette shares one vendor" \
  tests/conformance/test_core_path_cassettes.py \
  "tests/conformance/test_core_path_cassettes.py::test_the_loop_round_trips_cassette_state_for_every_provider" \
  's = s.replace("        \"MODEL_PROVIDER\": cassette.provider,\n", "        \"MODEL_PROVIDER\": \"anthropic\",\n")'

proof "T170 coverage — CORE_PATH_CASSETTES drops a closed provider" \
  tests/conformance/test_core_path_cassettes.py \
  "tests/conformance/test_core_path_cassettes.py::test_every_closed_provider_has_a_core_path_cassette" \
  's = s.replace("CORE_PATH_CASSETTES = PROVIDER_CASSETTES", "CORE_PATH_CASSETTES = PROVIDER_CASSETTES[:-1]")'

proof "T170 call — the client invokes ProviderDriver.call instead of the player" \
  tests/conformance/test_core_path_cassettes.py \
  "tests/conformance/test_core_path_cassettes.py::test_the_loop_round_trips_cassette_state_for_every_provider" \
  's = s.replace("        payload = self.player.respond(\n            index, request, conversation_length=len(turns))", "        payload = self.selected.driver.call(request)")'

proof "T170 provenance — a derived cassette is cited as a live measurement" \
  tests/conformance/test_core_path_cassettes.py \
  "tests/conformance/test_core_path_cassettes.py::test_the_loop_round_trips_cassette_state_for_every_provider" \
  's = s.replace("    with pytest.raises(harness.ProvenanceError, match=\"synthetic\"):\n        cassette.require_recorded()", "    cassette.require_recorded()")'

proof "T170 isolation — T061 is allowed to name the loop this file uniquely owns" \
  tests/conformance/test_core_path_cassettes.py \
  "tests/conformance/test_core_path_cassettes.py::test_this_file_drives_the_loop_and_t061_does_not" \
  's = s.replace("    assert \"AgentLoop\" not in there", "    assert \"AgentLoop\" in there")'

# --- T165 — session-wide secret scan over the four SC-004 surfaces ------------
#
# Every arm plants rather than reasons, and names a node. The scanner itself,
# the four-surface population, the zero-session refusal, a leak into model
# context, a leak through the tool result, an emptied persisted dump, the
# every-session flag, and a second redaction filter.

proof "T165 scanner — findings returns no planted values" \
  tests/batteries/test_secret_scan.py \
  "tests/batteries/test_secret_scan.py::test_the_scanner_catches_a_planted_secret_on_each_surface" \
  's = s.replace("    return [secret for secret in secrets if secret in blob]", "    return []")'

proof "T165 surfaces — traces is dropped from the population" \
  tests/batteries/test_secret_scan.py \
  "tests/batteries/test_secret_scan.py::test_the_four_surfaces_are_the_population" \
  's = s.replace("    \"emitted_artifacts\",\n    \"traces\",\n    \"persisted_state\",", "    \"emitted_artifacts\",\n    \"persisted_state\",")'

proof "T165 vacuity — a scan over zero sessions is allowed to pass" \
  tests/batteries/test_secret_scan.py \
  "tests/batteries/test_secret_scan.py::test_a_scan_over_zero_sessions_is_refused" \
  's = s.replace("SCAN_OVER_ZERO_SESSIONS_PASSES = False", "SCAN_OVER_ZERO_SESSIONS_PASSES = True")'

proof "T165 context — the capture site appends the planted provider value" \
  tests/batteries/test_secret_scan.py \
  "tests/batteries/test_secret_scan.py::test_every_session_the_battery_produces_is_clean_on_all_four_surfaces" \
  's = s.replace("    bucket.append(context.render() + leak)", "    bucket.append(context.render() + leak + PROVIDER_PLAINTEXT)")'

proof "T165 tool result — execute returns the planted provider value" \
  tests/batteries/test_secret_scan.py \
  "tests/batteries/test_secret_scan.py::test_every_session_the_battery_produces_is_clean_on_all_four_surfaces" \
  's = s.replace("    return TOOL_RESULT_BODY", "    return PROVIDER_PLAINTEXT")'

proof "T165 persisted — the sqlite dump is emptied" \
  tests/batteries/test_secret_scan.py \
  "tests/batteries/test_secret_scan.py::test_every_session_the_battery_produces_is_clean_on_all_four_surfaces" \
  's = s.replace("        return \"\\n\".join(parts)", "        return \"\"")'

proof "T165 every session — EVERY_SESSION is flipped so the second session is skipped" \
  tests/batteries/test_secret_scan.py \
  "tests/batteries/test_secret_scan.py::test_every_session_the_battery_produces_is_clean_on_all_four_surfaces" \
  's = s.replace("EVERY_SESSION = True", "EVERY_SESSION = False")'

proof "T165 no second filter — CREDENTIAL_PATTERNS is bound as a redaction regex" \
  tests/batteries/test_secret_scan.py \
  "tests/batteries/test_secret_scan.py::test_the_battery_does_not_reimplement_secret_redaction" \
  's = s.replace("def findings(blob: str, secrets: tuple[str, ...] = PLANTED) -> list[str]:", "CREDENTIAL_PATTERNS = {}\n\ndef findings(blob: str, secrets: tuple[str, ...] = PLANTED) -> list[str]:")'

# --- T169 — operator-boundary check (FR-032) ----------------------------------
#
# Every arm plants rather than reasons, and names a node. The leave-required
# flag, a dropped named component, target credential on runtime, provider
# credential on analysis, a vendor SaaS topology identity, required egress at
# runtime startup, a renamed Plane B, and a vendor image registry.

proof "T169 leave — TARGET_DATA_MUST_LEAVE is flipped" \
  tests/integration/test_operator_boundary.py \
  "tests/integration/test_operator_boundary.py::test_no_target_data_or_credential_is_required_to_leave" \
  's = s.replace("TARGET_DATA_MUST_LEAVE = False", "TARGET_DATA_MUST_LEAVE = True")'

proof "T169 components — analysis is dropped from the named set" \
  tests/integration/test_operator_boundary.py \
  "tests/integration/test_operator_boundary.py::test_every_named_component_is_inside_the_operator_bundle" \
  's = s.replace("OPERATOR_COMPONENTS = (\n    \"analysis\",\n    \"enforcement_point\",\n", "OPERATOR_COMPONENTS = (\n    \"enforcement_point\",\n")'

proof "T169 runtime plane — compose puts the target credential on runtime" \
  deploy/compose/compose.yaml \
  "tests/integration/test_operator_boundary.py::test_target_credential_is_not_required_on_runtime" \
  's = s.replace("      F2A_PROVIDER_CREDENTIAL: ${F2A_PROVIDER_CREDENTIAL:?required}\n      REPORTING_WINDOW_SECONDS: ${REPORTING_WINDOW_SECONDS:?required}", "      F2A_PROVIDER_CREDENTIAL: ${F2A_PROVIDER_CREDENTIAL:?required}\n      F2A_TARGET_CREDENTIAL: ${F2A_TARGET_CREDENTIAL:?required}\n      REPORTING_WINDOW_SECONDS: ${REPORTING_WINDOW_SECONDS:?required}")'

proof "T169 analysis plane — compose puts the provider credential on analysis" \
  deploy/compose/compose.yaml \
  "tests/integration/test_operator_boundary.py::test_provider_credential_is_not_required_on_analysis_supervisor_or_sandbox" \
  's = s.replace("      F2A_SOURCE_REF: ${F2A_SOURCE_REF:?required}\n      F2A_DEPLOYMENT_ID: ${F2A_DEPLOYMENT_ID:?required}", "      F2A_SOURCE_REF: ${F2A_SOURCE_REF:?required}\n      F2A_PROVIDER_CREDENTIAL: ${F2A_PROVIDER_CREDENTIAL:?required}\n      F2A_DEPLOYMENT_ID: ${F2A_DEPLOYMENT_ID:?required}")'

proof "T169 topology — the target identity is a vendor SaaS hostname" \
  tests/integration/test_operator_boundary.py \
  "tests/integration/test_operator_boundary.py::test_topology_identities_are_operator_local_not_a_vendor_saas" \
  's = s.replace("    TARGET_ADDR_KEY: \"target:9000\",", "    TARGET_ADDR_KEY: \"api.openai.com:443\",")'

proof "T169 egress — runtime main requires Plane B to start" \
  src/runtime/main.py \
  "tests/integration/test_operator_boundary.py::test_the_product_does_not_require_runtime_egress_to_function" \
  's = s.replace("        config = load(RUNTIME_KEYS, env=env)", "        with guarded(pin(\"203.0.113.10:443\")):\n            config = load(RUNTIME_KEYS, env=env)")'

proof "T169 plane B — guarded is renamed so the watch no longer sees it" \
  src/runtime/egress.py \
  "tests/integration/test_operator_boundary.py::test_runtime_egress_guarded_is_not_weakened" \
  's = s.replace("def guarded(plane: EgressPlane) -> Iterator[EgressPlane]:", "def not_guarded(plane: EgressPlane) -> Iterator[EgressPlane]:")'

proof "T169 image — runtime is pulled from a vendor registry" \
  deploy/compose/compose.yaml \
  "tests/integration/test_operator_boundary.py::test_compose_declares_no_external_control_plane" \
  's = s.replace("    image: f2a-runtime:local", "    image: vendor.example.com/f2a-runtime:local")'

# --- T166 — in-container scan (FR-050 not-present, SC-024) --------------------
#
# Static half only. The live docker-run arms skip when the daemon is absent
# or the sandbox image is not loaded, so a proof that named one of those
# nodes would skip in CI and read as coverage. Every arm plants rather
# than reasons, names a node, and uses a needle that is unique in its file.

proof "T166 scanner — findings returns no planted values" \
  tests/batteries/test_in_container_scan.py \
  "tests/batteries/test_in_container_scan.py::test_the_scanner_catches_a_planted_secret_on_each_surface" \
  's = s.replace("    caught = [secret for secret in secrets if secret in blob]", "    caught = []")'

proof "T166 surfaces — process_table is dropped from the population" \
  tests/batteries/test_in_container_scan.py \
  "tests/batteries/test_in_container_scan.py::test_the_three_surfaces_are_the_population" \
  's = s.replace("SURFACES = (\n    \"environment\",\n    \"process_table\",\n    \"declared_mounts\",\n)", "SURFACES = (\n    \"environment\",\n    \"declared_mounts\",\n)")'

proof "T166 vacuity — a scan over an empty dump is allowed to pass" \
  tests/batteries/test_in_container_scan.py \
  "tests/batteries/test_in_container_scan.py::test_a_scan_over_an_empty_dump_is_refused" \
  's = s.replace("SCAN_OVER_EMPTY_DUMP_PASSES = False", "SCAN_OVER_EMPTY_DUMP_PASSES = True")'

proof "T166 mounts — /scratch is dropped from the claimed set" \
  tests/batteries/test_in_container_scan.py \
  "tests/batteries/test_in_container_scan.py::test_the_scan_claims_only_the_declared_mount_set" \
  's = s.replace("CLAIMED_MOUNTS = (\n    \"/workspace\",\n    \"/opt/toolchain\",\n    \"/scratch\",\n)", "CLAIMED_MOUNTS = (\n    \"/workspace\",\n    \"/opt/toolchain\",\n)")'

proof "T166 image — provider credential baked into the sandbox ENV" \
  deploy/images/sandbox.Dockerfile \
  "tests/batteries/test_in_container_scan.py::test_sandbox_image_holds_neither_credential" \
  's = s.replace("ENV PYTHONDONTWRITEBYTECODE=1 \\\n    PYTHONUNBUFFERED=1", "ENV PYTHONDONTWRITEBYTECODE=1 \\\n    PYTHONUNBUFFERED=1 \\\n    F2A_PROVIDER_CREDENTIAL=x")'

proof "T166 compose — sandbox injects the provider credential" \
  deploy/compose/compose.yaml \
  "tests/batteries/test_in_container_scan.py::test_compose_does_not_inject_credentials_into_sandbox" \
  's = s.replace("      - sandbox-build\n    # T096: no ENTRYPOINT, no CMD, no credential, no package index. Listed so", "      - sandbox-build\n    environment:\n      F2A_PROVIDER_CREDENTIAL: ${F2A_PROVIDER_CREDENTIAL:?required}\n    # T096: no ENTRYPOINT, no CMD, no credential, no package index. Listed so")'

proof "T166 skip — missing docker no longer names the daemon" \
  tests/batteries/test_in_container_scan.py \
  "tests/batteries/test_in_container_scan.py::test_a_missing_docker_daemon_skip_names_the_daemon" \
  's = s.replace("Docker daemon is absent: `docker` is not on PATH", "docker is not on PATH")'

proof "T166 skip — unloaded image no longer names loaded" \
  tests/batteries/test_in_container_scan.py \
  "tests/batteries/test_in_container_scan.py::test_an_unloaded_image_skip_names_the_image" \
  's = s.replace("f\"Docker daemon is present but none of {tags} is loaded; \"", "f\"Docker daemon is present but none of {tags} is missing; \"")'

# --- T167 — not-inherited later session (FR-050, SC-024) ----------------------
#
# Static / in-process half only. The live sequential-run arm skips when the
# daemon is absent or the sandbox image is not loaded. Isolation without
# destroy() is the T110 arm, kept in test_session_env.py and re-asserted
# here; neither file is deleted. Every arm plants rather than reasons,
# names a node, and uses a needle that is unique in its file.

proof "T167 scanner — findings returns no planted scratch value" \
  tests/batteries/test_environment_not_inherited.py \
  "tests/batteries/test_environment_not_inherited.py::test_the_scanner_catches_a_planted_scratch_value" \
  's = s.replace("    return [secret] if secret in blob else []", "    return []")'

proof "T167 t110 — the SIGKILL arm is renamed out of test_session_env.py" \
  tests/unit/test_session_env.py \
  "tests/batteries/test_environment_not_inherited.py::test_t110_session_env_file_still_fires" \
  's = s.replace("def test_destroy_is_housekeeping_and_isolation_does_not_depend_on_it", "def test_destroy_is_now_the_isolation_mechanism")'

proof "T167 flag — ISOLATION_DEPENDS_ON_DESTROY is flipped" \
  tests/batteries/test_environment_not_inherited.py \
  "tests/batteries/test_environment_not_inherited.py::test_nothing_written_in_one_session_is_readable_from_a_later_session" \
  's = s.replace("ISOLATION_DEPENDS_ON_DESTROY = False", "ISOLATION_DEPENDS_ON_DESTROY = True")'

proof "T167 flag — NEXT_IS_NEW_SESSION is flipped so the successor reuses the id" \
  tests/batteries/test_environment_not_inherited.py \
  "tests/batteries/test_environment_not_inherited.py::test_nothing_written_in_one_session_is_readable_from_a_later_session" \
  's = s.replace("NEXT_IS_NEW_SESSION = True", "NEXT_IS_NEW_SESSION = False")'

proof "T167 crash path — destroy() runs before the successor is created" \
  tests/batteries/test_environment_not_inherited.py \
  "tests/batteries/test_environment_not_inherited.py::test_nothing_written_in_one_session_is_readable_from_a_later_session" \
  's = s.replace("    # T167: no destroy(). Isolation must hold on the crash path (T110).\n    later_id = SUCCESSOR_ID if NEXT_IS_NEW_SESSION else CRASHED_ID", "    envs.destroy(CRASHED_ID)\n    later_id = SUCCESSOR_ID if NEXT_IS_NEW_SESSION else CRASHED_ID")'

proof "T167 paths — SessionEnvironments puts every session under one shared base" \
  src/supervisor/session_env.py \
  "tests/batteries/test_environment_not_inherited.py::test_nothing_written_in_one_session_is_readable_from_a_later_session" \
  's = s.replace("    def _paths(self, session_id: str) -> tuple[Path, Path]:\n        base = self.root / session_id\n        return base / \"scratch\", base / \"run\"", "    def _paths(self, session_id: str) -> tuple[Path, Path]:\n        base = self.root / \"shared\"\n        return base / \"scratch\", base / \"run\"")'

proof "T167 create — reuse is no longer refused" \
  src/supervisor/session_env.py \
  "tests/batteries/test_environment_not_inherited.py::test_create_still_refuses_reuse_rather_than_emptying" \
  's = s.replace("        if scratch.exists():", "        if False:")'

proof "T167 skip — missing docker no longer names the daemon" \
  tests/batteries/test_environment_not_inherited.py \
  "tests/batteries/test_environment_not_inherited.py::test_a_missing_docker_daemon_skip_names_the_daemon" \
  's = s.replace("Docker daemon is absent: `docker` is not on PATH", "docker is not on PATH")'

# --- T173 / T174 — shadow judge off the request path, three inject modes ------
#
# FR-039 / SC-025. The writer is a typed verdict function, not a vendor SDK
# (T058 still PARTIAL). T175's differential battery is not these arms; they
# only keep the three modes selectable and the write off the request path.
# Every arm plants rather than reasons, names a node, and uses a needle
# that is unique in its file. T214 is still open: no run produces a Result.

proof "T173 — consider writes the verdict inline, so the request path waits on the judge" \
  src/runtime/judge/shadow.py \
  "tests/unit/test_shadow_judge.py::test_consider_returns_before_the_verdict_is_written" \
  's = s.replace("        self._queue.put(_VerdictJob(result_id, session_id, verifier_label))", "        self._write_verdict(_VerdictJob(result_id, session_id, verifier_label))")'

proof "T173 — the stream sink writes a verdict, so consumption is a success-path insert" \
  src/runtime/judge/shadow.py \
  "tests/unit/test_shadow_judge.py::test_consuming_the_stream_writes_no_row" \
  's = s.replace("        self._queue.put(_EventJob(event))", "        self._seen.append(event)\n        self._write_verdict(_VerdictJob(\"from-event\", event.session_id, \"correct\"))")'

proof "T173 — an empty result id is accepted, so a verdict is keyed to nothing" \
  src/runtime/judge/shadow.py \
  "tests/unit/test_shadow_judge.py::test_an_empty_result_id_is_refused" \
  's = s.replace("        if not result_id:", "        if False:")'

proof "T173 — a success-path role may construct the writer" \
  src/runtime/judge/shadow.py \
  "tests/unit/test_shadow_judge.py::test_a_success_path_role_cannot_write_the_table" \
  's = s.replace("        if repository.role != ROLE_SHADOW_JUDGE:", "        if False and repository.role != ROLE_SHADOW_JUDGE:")'

proof "T173 — off mode still starts the worker thread" \
  src/runtime/judge/shadow.py \
  "tests/unit/test_shadow_judge.py::test_off_mode_starts_no_thread_and_writes_nothing" \
  's = s.replace("        if self._decide is not None:", "        if True:")'

proof "T173 — the judge-to-result plant scan appends nothing, so a planted import is free" \
  tests/unit/test_shadow_judge.py \
  "tests/unit/test_shadow_judge.py::test_the_judge_import_scan_fires_on_a_planted_result_import" \
  's = s.replace("                edges.append(f\"{path.name} imports {imported}\")", "                pass")'

proof "T173 — the success-path-to-judge plant scan appends nothing, so a planted edge is free" \
  tests/unit/test_shadow_judge.py \
  "tests/unit/test_shadow_judge.py::test_the_success_path_import_scan_fires_on_a_planted_judge_edge" \
  's = s.replace("            found.append(imported)", "            pass")'

proof "T173 — T214 residual is marked closed, so a missing Result from a run reads as discharged" \
  tests/unit/test_shadow_judge.py \
  "tests/unit/test_shadow_judge.py::test_no_run_produces_a_result_t214_is_still_open" \
  's = s.replace("T214_RESIDUAL_NO_RUN_PRODUCES_A_RESULT = True", "T214_RESIDUAL_NO_RUN_PRODUCES_A_RESULT = False")'

proof "T174 — off mode returns the agreeing function, so not-running still writes" \
  src/runtime/judge/inject.py \
  "tests/unit/test_judge_inject.py::test_off_writes_no_verdict" \
  's = s.replace("    if mode == MODE_OFF:\n        return None", "    if mode == MODE_OFF:\n        return _agree")'

proof "T174 — agree mode returns the disagreeing function" \
  src/runtime/judge/inject.py \
  "tests/unit/test_judge_inject.py::test_agree_writes_the_verifier_label" \
  's = s.replace("    if mode == MODE_AGREE:\n        return _agree", "    if mode == MODE_AGREE:\n        return _disagree")'

proof "T174 — disagree mode returns the agreeing function" \
  src/runtime/judge/inject.py \
  "tests/unit/test_judge_inject.py::test_disagree_writes_the_other_label" \
  's = s.replace("    if mode == MODE_DISAGREE:\n        return _disagree", "    if mode == MODE_DISAGREE:\n        return _agree")'

proof "T174 — an unknown mode is returned rather than refused" \
  src/runtime/judge/inject.py \
  "tests/unit/test_judge_inject.py::test_an_unknown_mode_is_refused" \
  's = s.replace("    raise JudgeInjectError(", "    return _agree\n    raise JudgeInjectError(")'

proof "T174 — MODES drops off, so the third run cannot be named" \
  src/runtime/judge/inject.py \
  "tests/unit/test_judge_inject.py::test_the_three_modes_are_selectable" \
  's = s.replace("MODES: tuple[str, ...] = (MODE_AGREE, MODE_DISAGREE, MODE_OFF)", "MODES: tuple[str, ...] = (MODE_AGREE, MODE_DISAGREE)")'

# --- T189 / T190, claims audit and support audit -----------------------------
#
# Every arm plants rather than reasons. The two scans succeed by finding
# nothing, so an instrument that matches nothing, a live sentence that
# adds a prohibited shape or an unfixtured support claim, a required-
# surface list that shrinks, a fixture catalog that invents a language,
# and a findings file entering the walk each have an arm. Needles are
# unique in their file — Path("README.md") and the plan.md closer each
# appear twice, so those tampers carry surrounding context.

proof "T189 instrument — _unrefused returns nothing, so a planted claim is free" \
  tests/contract/test_claims_audit.py \
  "tests/contract/test_claims_audit.py::test_the_four_shape_scanners_fire_on_a_planted_claim" \
  's = s.replace("def _unrefused(pattern: re.Pattern[str], collapsed: str) -> list[str]:\n    hits: list[str] = []", "def _unrefused(pattern: re.Pattern[str], collapsed: str) -> list[str]:\n    return []\n    hits: list[str] = []")'

proof "T189 — spec-kit-workflow claims a capability advantage for the curated tool surface" \
  docs/spec-kit-workflow.md \
  "tests/contract/test_claims_audit.py::test_live_trees_have_none_of_the_four_prohibited_shapes" \
  's = s.replace("GitHub Spec Kit is the spec-driven development process of record for this repo.", "GitHub Spec Kit is the spec-driven development process of record for this repo. The curated tool surface has a capability advantage.")'

proof "T189 — spec-kit-workflow asserts that synthesis is safer" \
  docs/spec-kit-workflow.md \
  "tests/contract/test_claims_audit.py::test_live_trees_have_none_of_the_four_prohibited_shapes" \
  's = s.replace("This is the operating manual: what is installed, what to run, and in what order.", "This is the operating manual: synthesis is safer than a hand-written surface.")'

proof "T189 — README quotes a session cost with no basis or scope" \
  README.md \
  "tests/contract/test_claims_audit.py::test_live_trees_have_none_of_the_four_prohibited_shapes" \
  's = s.replace("Fail closed when either one moves.", "Fail closed when either one moves. A session costs $3.50.")'

proof "T189 — README uses provably for effect resolution" \
  README.md \
  "tests/contract/test_claims_audit.py::test_live_trees_have_none_of_the_four_prohibited_shapes" \
  's = s.replace("denies anything that is not a read", "provably resolves every effect as a read")'

proof "T189 — REQUIRED_SURFACES drops README, so the walk no longer covers it" \
  tests/contract/test_claims_audit.py \
  "tests/contract/test_claims_audit.py::test_every_required_surface_exists_and_is_walked" \
  's = s.replace("REQUIRED_SURFACES = (\n    Path(\"README.md\"),\n", "REQUIRED_SURFACES = (\n")'

proof "T189 — a findings file enters the claims walk" \
  tests/contract/test_claims_audit.py \
  "tests/contract/test_claims_audit.py::test_dated_records_are_outside_the_walk" \
  's = s.replace("    Path(\"deploy\"),\n    Path(\"src/supervisor/main.py\"),", "    Path(\"deploy\"),\n    Path(\"specs/002-spec-aware-agent-runtime/findings/README.md\"),\n    Path(\"src/supervisor/main.py\"),")'

proof "T190 instrument — the support-offer scanner matches nothing, so no claim is free" \
  tests/contract/test_support_audit.py \
  "tests/contract/test_support_audit.py::test_the_support_offer_scanner_fires_on_a_planted_claim" \
  's = s.replace("    for match in SUPPORT_OFFER.finditer(collapsed):", "    for match in SUPPORT_OFFER.finditer(collapsed[:0]):")'

proof "T190 — README claims TypeScript is supported" \
  README.md \
  "tests/contract/test_support_audit.py::test_live_trees_do_not_claim_unsupported_names_as_supported" \
  's = s.replace("nothing here reaches another language.", "the product supports TypeScript.")'

proof "T190 — README claims FastAPI is supported" \
  README.md \
  "tests/contract/test_support_audit.py::test_live_trees_do_not_claim_unsupported_names_as_supported" \
  's = s.replace("powers an estimated 70% of MCP servers", "the product supports FastAPI")'

proof "T190 — README claims gRPC is a supported target shape" \
  README.md \
  "tests/contract/test_support_audit.py::test_live_trees_do_not_claim_unsupported_names_as_supported" \
  's = s.replace("(HTTP/RPC), never in-process (D-01)", "(HTTP/RPC); the product supports gRPC (D-01)")'

proof "T190 — FIXTURE_BACKED drops the analyzer, so Python support has no fixture row" \
  tests/contract/test_support_audit.py \
  "tests/contract/test_support_audit.py::test_every_fixture_backed_entry_has_a_committed_fixture_and_expected_output" \
  's = s.replace("    (\n        \"language\",\n        \"hand-written Python\",\n        Path(\"tests/fixtures/analyzer/inventory-service/service.py\"),\n        Path(\"tests/fixtures/analyzer/inventory-service/expected.json\"),\n    ),\n", "")'

proof "T190 — FIXTURE_BACKED invents TypeScript with no files on disk" \
  tests/contract/test_support_audit.py \
  "tests/contract/test_support_audit.py::test_every_fixture_backed_entry_has_a_committed_fixture_and_expected_output" \
  's = s.replace("        Path(\"tests/fixtures/reference-app/questions.json\"),\n    ),\n)", "        Path(\"tests/fixtures/reference-app/questions.json\"),\n    ),\n    (\n        \"language\",\n        \"TypeScript\",\n        Path(\"tests/fixtures/analyzer/typescript/app.ts\"),\n        Path(\"tests/fixtures/analyzer/typescript/expected.json\"),\n    ),\n)")'

proof "T190 — SUPPORTED_SPECIFICATION_SHAPES grows OpenAPI with no fixture" \
  src/analysis/admission.py \
  "tests/contract/test_support_audit.py::test_supported_specification_shapes_are_exactly_the_fixture_backed_target" \
  's = s.replace("SUPPORTED_SPECIFICATION_SHAPES: tuple[str, ...] = (\"served_operation_set\",)", "SUPPORTED_SPECIFICATION_SHAPES: tuple[str, ...] = (\"served_operation_set\", \"openapi\")")'

proof "T190 — a findings file enters the support walk" \
  tests/contract/test_support_audit.py \
  "tests/contract/test_support_audit.py::test_dated_records_are_outside_the_walk" \
  's = s.replace("    Path(\"deploy\"),\n    Path(\"src/supervisor/main.py\"),", "    Path(\"deploy\"),\n    Path(\"specs/002-spec-aware-agent-runtime/findings/README.md\"),\n    Path(\"src/supervisor/main.py\"),")'

# --- T175 — SC-025 differential: three inject modes, caller-visible identity --
#
# FR-052 / SC-025. T025 is the structural half. This battery compares the
# caller-visible surfaces a run actually writes (RunOutcome, EventStream
# frames, proxy-ingest gate dispositions) across agree / disagree / off,
# and reads judge_verdict only to prove the three modes differed. T214
# is still open: no run produces a Result, and a comparison of empty
# Result lists is refused. Every arm plants rather than reasons, names a
# node, and uses a needle that is unique in its file. T176 / T177 / T214
# / T215 were not this slice. T189 plants above are not retargeted.

proof "T175 vacuity — comparing empty Result lists is accepted as the battery" \
  tests/batteries/test_judge_differential.py \
  "tests/batteries/test_judge_differential.py::test_comparing_empty_result_lists_is_refused" \
  's = s.replace("COMPARING_EMPTY_RESULT_LISTS_IS_THE_BATTERY = False", "COMPARING_EMPTY_RESULT_LISTS_IS_THE_BATTERY = True")'

proof "T175 surfaces — gate_decisions is dropped from the population" \
  tests/batteries/test_judge_differential.py \
  "tests/batteries/test_judge_differential.py::test_the_caller_visible_surfaces_are_the_population" \
  's = s.replace("CALLER_VISIBLE = (\n    \"run_outcome\",\n    \"event_stream\",\n    \"gate_decisions\",\n)", "CALLER_VISIBLE = (\n    \"run_outcome\",\n    \"event_stream\",\n)")'

proof "T175 leak — caller-visible comparison includes judge_verdict" \
  tests/batteries/test_judge_differential.py \
  "tests/batteries/test_judge_differential.py::test_caller_visible_comparison_does_not_go_through_judge_verdict" \
  's = s.replace("CALLER_VISIBLE = (\n    \"run_outcome\",\n    \"event_stream\",\n    \"gate_decisions\",\n)", "CALLER_VISIBLE = (\n    \"run_outcome\",\n    \"event_stream\",\n    \"gate_decisions\",\n    \"judge_verdict\",\n)")'

proof "T175 identity — caller-visible surfaces are not compared" \
  tests/batteries/test_judge_differential.py \
  "tests/batteries/test_judge_differential.py::test_caller_visible_surfaces_and_gate_decisions_are_identical_across_modes" \
  's = s.replace("SURFACES_ARE_COMPARED = True", "SURFACES_ARE_COMPARED = False")'

proof "T175 modes — the three verdict populations are not required to differ" \
  tests/batteries/test_judge_differential.py \
  "tests/batteries/test_judge_differential.py::test_caller_visible_surfaces_and_gate_decisions_are_identical_across_modes" \
  's = s.replace("THREE_MODES_WROTE_DIFFERENT_VERDICTS = True", "THREE_MODES_WROTE_DIFFERENT_VERDICTS = False")'

proof "T175 off — off mode writing verdicts is accepted" \
  tests/batteries/test_judge_differential.py \
  "tests/batteries/test_judge_differential.py::test_caller_visible_surfaces_and_gate_decisions_are_identical_across_modes" \
  's = s.replace("OFF_WRITES_NOTHING = True", "OFF_WRITES_NOTHING = False")'

proof "T175 gate — empty gate dispositions are accepted" \
  tests/batteries/test_judge_differential.py \
  "tests/batteries/test_judge_differential.py::test_empty_gate_decisions_are_refused" \
  's = s.replace("GATE_DECISIONS_MAY_BE_EMPTY = False", "GATE_DECISIONS_MAY_BE_EMPTY = True")'

proof "T175 sessions — EVERY_SESSION is flipped so the second session is skipped" \
  tests/batteries/test_judge_differential.py \
  "tests/batteries/test_judge_differential.py::test_caller_visible_surfaces_and_gate_decisions_are_identical_across_modes" \
  's = s.replace("EVERY_SESSION = True", "EVERY_SESSION = False")'

proof "T175 T214 — residual is marked closed, so a missing Result from a run reads as discharged" \
  tests/batteries/test_judge_differential.py \
  "tests/batteries/test_judge_differential.py::test_no_run_produces_a_result_t214_is_still_open" \
  's = s.replace("T214_RESIDUAL_NO_RUN_PRODUCES_A_RESULT = True", "T214_RESIDUAL_NO_RUN_PRODUCES_A_RESULT = False")'

proof "T175 success-path — the planted judge import appends nothing, so a planted edge is free" \
  tests/batteries/test_judge_differential.py \
  "tests/batteries/test_judge_differential.py::test_the_success_path_import_scan_fires_on_a_planted_judge_edge" \
  's = s.replace("            found.append(imported)", "            pass")'

# --- T178 — FR-041 per-request observation at the enforcement point ----------
#
# The record is the corpus. It is not a second decision log: DecisionRecord
# already carries tier, rule, method, disposition; observation adds the
# matched template, the specification metadata, and decision_seq. Every arm
# plants rather than reasons, names a node, and uses a needle unique in its
# file. T179–T181 / T176 / T177 / T214 / T215 are not these arms. T175
# arms above are not retargeted.

go_proof "T178 — observation insert becomes a no-op, so the corpus is empty" \
  src/proxy/observation.go \
  "TestEveryDecisionHasAnObservation" \
  's = s.replace("\t_, err := tx.ExecContext(ctx, `\n\t\tINSERT INTO effect_gate_observation\n\t\t  (decision_seq, resolved_tier, rule_id, matched_template, method, spec_metadata, disposition)\n\t\tVALUES (?,?,?,?,?,?,?)`,\n\t\trec.DecisionSeq,\n\t\trec.ResolvedTier,\n\t\trec.RuleID,\n\t\trec.MatchedTemplate,\n\t\trec.Method,\n\t\trec.SpecMetadata,\n\t\trec.Disposition,\n\t)\n\treturn err", "\treturn nil")'

go_proof "T178 — allows are dropped from the corpus" \
  src/proxy/observation.go \
  "TestObservationFiresForAllowAndDeny" \
  's = s.replace("\treturn disposition == dispositionAllow || disposition == dispositionDeny", "\treturn disposition == dispositionDeny")'

go_proof "T178 — denies are dropped from the corpus" \
  src/proxy/observation.go \
  "TestObservationFiresForAllowAndDeny" \
  's = s.replace("\treturn disposition == dispositionAllow || disposition == dispositionDeny", "\treturn disposition == dispositionAllow")'

go_proof "T178 — the matched operation template is not recorded" \
  src/proxy/observation.go \
  "TestObservationCarriesMatchedTemplate" \
  's = s.replace("\t\tMatchedTemplate: rec.MatchedTemplate,", "\t\tMatchedTemplate: \"\",")'

go_proof "T178 — the specification metadata is emptied" \
  src/proxy/observation.go \
  "TestObservationCarriesSpecificationMetadata" \
  's = s.replace("\t\tSpecMetadata:    meta,", "\t\tSpecMetadata:    emptySpecMetadata,")'

go_proof "T178 — decision_seq is zeroed, so the row is not keyed to a decision" \
  src/proxy/decisionlog.go \
  "TestObservationKeysBackToTheDecision" \
  's = s.replace("\t\tobs := observationFrom(rec, seq)", "\t\tseq = 0\n\t\tobs := observationFrom(rec, seq)")'

go_proof "T178 — a missing observation table no longer fails the request closed" \
  src/proxy/observation.go \
  "TestUnwritableObservationFailsClosed" \
  's = s.replace("\t_, err := tx.ExecContext(ctx, `\n\t\tINSERT INTO effect_gate_observation\n\t\t  (decision_seq, resolved_tier, rule_id, matched_template, method, spec_metadata, disposition)\n\t\tVALUES (?,?,?,?,?,?,?)`,\n\t\trec.DecisionSeq,\n\t\trec.ResolvedTier,\n\t\trec.RuleID,\n\t\trec.MatchedTemplate,\n\t\trec.Method,\n\t\trec.SpecMetadata,\n\t\trec.Disposition,\n\t)\n\treturn err", "\treturn nil")'

go_proof "T178 — the success-path read scan appends nothing, so a planted SELECT is free" \
  src/proxy/observation_test.go \
  "TestTheObservationReadScanFiresOnAPlantedSelect" \
  's = s.replace("\t\t\thits = append(hits, strings.TrimSpace(line))", "\t\t\t_ = line")'

# --- T176 / T177 — adjudication queue and FR-040 margin report ---------------
#
# Sampling is pre-registered before the window. human_label is a human row
# (adjudicator + time); a model stand-in is refused. The margin report keeps
# all three FR-040 branches intact and does not open SC-013's window over an
# empty table. Every arm plants rather than reasons. T179–T181 / T214 / T215
# are not these arms. T173–T175 / T178 arms above are not retargeted.

proof "T176 — a sampling rule registered after the window opens is accepted" \
  src/runtime/adjudication/sampling.py \
  "tests/unit/test_adjudication.py::test_a_rule_cannot_be_registered_after_the_window_opens" \
  's = s.replace("        if self.registered_at >= self.window_starts_at:", "        if False and self.registered_at >= self.window_starts_at:")'

proof "T176 — an empty adjudicator is stored as a human_label row" \
  src/runtime/adjudication/queue.py \
  "tests/unit/test_adjudication.py::test_an_empty_adjudicator_is_refused" \
  's = s.replace("        if not adjudicator:", "        if False:")'

proof "T176 — a model stand-in is stored as a human_label row" \
  src/runtime/adjudication/queue.py \
  "tests/unit/test_adjudication.py::test_a_model_standin_is_refused" \
  's = s.replace("        if adjudicator in MODEL_STANDINS:", "        if False and adjudicator in MODEL_STANDINS:")'

proof "T176 — the operator surface fills suggested_label from the verifier" \
  src/runtime/adjudication/queue.py \
  "tests/unit/test_adjudication.py::test_the_surface_presents_evidence_and_no_suggested_label" \
  's = s.replace("            suggested_label=None,", "            suggested_label=item.evidence.verifier_label,")'

proof "T176 — a success-path role may construct the queue" \
  src/runtime/adjudication/queue.py \
  "tests/unit/test_adjudication.py::test_a_success_path_role_cannot_write_the_table" \
  's = s.replace("        if repository.role != ROLE_SHADOW_JUDGE:", "        if False and repository.role != ROLE_SHADOW_JUDGE:")'

proof "T176 — an empty result id is accepted, so a sample is keyed to nothing" \
  src/runtime/adjudication/queue.py \
  "tests/unit/test_adjudication.py::test_an_empty_result_id_is_refused" \
  's = s.replace("        if not result_id:\n            raise AdjudicationError(\n                \"a sample is keyed to a result; an empty id keys nothing\"", "        if False:\n            raise AdjudicationError(\n                \"a sample is keyed to a result; an empty id keys nothing\"")'

proof "T176 — the adjudication-to-result plant scan appends nothing, so a planted import is free" \
  tests/unit/test_adjudication.py \
  "tests/unit/test_adjudication.py::test_the_adjudication_import_scan_fires_on_a_planted_result_import" \
  's = s.replace("                edges.append(f\"{path.name} imports {imported}\")", "                pass")'

proof "T176 — T214 residual is marked closed, so a missing Result from a run reads as discharged" \
  tests/unit/test_adjudication.py \
  "tests/unit/test_adjudication.py::test_no_run_produces_a_result_t214_is_still_open" \
  's = s.replace("T214_RESIDUAL_NO_RUN_PRODUCES_A_RESULT = True", "T214_RESIDUAL_NO_RUN_PRODUCES_A_RESULT = False")'

proof "T177 — SC-013's window opens over an empty human_label table" \
  src/runtime/reports/margin.py \
  "tests/unit/test_margin_report.py::test_empty_labels_do_not_open_the_sc013_window" \
  's = s.replace("            window_open=False,", "            window_open=True,")'

proof "T177 — the chance branch fires when no human has labelled" \
  src/runtime/reports/margin.py \
  "tests/unit/test_margin_report.py::test_empty_labels_do_not_apply_the_chance_branch" \
  's = s.replace("            applied_branch=None,", "            applied_branch=BRANCH_CHANCE,")'

proof "T177 — chance is checked after headline, so a large margin hides a chance-level judge" \
  src/runtime/reports/margin.py \
  "tests/unit/test_margin_report.py::test_a_judge_at_chance_is_the_chance_branch_even_when_the_margin_is_large" \
  's = s.replace("    if judge_discrimination <= 0:\n        return BRANCH_CHANCE\n    if margin_pp >= MARGIN_THRESHOLD_PP:\n        return BRANCH_HEADLINE", "    if margin_pp >= MARGIN_THRESHOLD_PP:\n        return BRANCH_HEADLINE\n    if judge_discrimination <= 0:\n        return BRANCH_CHANCE")'

proof "T177 — the pre-registered threshold is changed from ten points" \
  src/runtime/reports/margin.py \
  "tests/unit/test_margin_report.py::test_the_threshold_is_the_pre_registered_ten_points" \
  's = s.replace("MARGIN_THRESHOLD_PP = 10.0", "MARGIN_THRESHOLD_PP = 5.0")'

proof "T177 — BRANCHES drops chance, so the third gate is no longer intact" \
  src/runtime/reports/margin.py \
  "tests/unit/test_margin_report.py::test_all_three_branches_are_present_when_labels_do_not_exist" \
  's = s.replace("BRANCHES: tuple[str, ...] = (BRANCH_HEADLINE, BRANCH_INTERNAL, BRANCH_CHANCE)", "BRANCHES: tuple[str, ...] = (BRANCH_HEADLINE, BRANCH_INTERNAL)")'

proof "T177 — the historical pass is recorded as performed" \
  src/runtime/reports/margin.py \
  "tests/unit/test_margin_report.py::test_the_historical_pass_is_recorded_as_never_performed" \
  's = s.replace("    \"The one human adjudication pass this needed was never performed. \"", "    \"The one human adjudication pass this needed was performed. \"")'

proof "T177 — empty labels are filled from the verifier, so the comparison is circular" \
  src/runtime/reports/margin.py \
  "tests/unit/test_margin_report.py::test_empty_labels_do_not_open_the_sc013_window" \
  's = s.replace("    labelled: Sequence[LabelRow] = tuple(human_labels)", "    labelled: Sequence[LabelRow] = tuple(human_labels) or tuple(LabelRow(v.result_id, \"model\", v.label, 0.0) for v in verifier_calls)")'

proof "T177 — the margin-to-result plant scan appends nothing, so a planted import is free" \
  tests/unit/test_margin_report.py \
  "tests/unit/test_margin_report.py::test_the_margin_import_scan_fires_on_a_planted_result_import" \
  's = s.replace("            found.append(imported)", "            pass")'

# --- T179 / T181 — FR-041 corpus export and the unset per-call threshold ----
#
# T179 exports effect_gate_observation, unlabelled. T181 records the
# per-call threshold unset and keeps every write capability blocked.
# T180 is the residual that produces labels; these arms do not snapshot
# the reference application. T176 / T177 / T214 / T215 are not these
# arms. T178 arms above are not retargeted. Every arm plants rather
# than reasons, names a node, and uses a needle unique in its file.

proof "T179 — the exporter ranges over egress_decision, so the corpus is a restated decision log" \
  src/runtime/reports/effect_corpus.py \
  "tests/unit/test_effect_corpus.py::test_the_exporter_ranges_over_the_observation_table_not_the_decision_log" \
  's = s.replace("PHYSICAL_TABLE = \"effect_gate_observation\"", "PHYSICAL_TABLE = \"egress_decision\"")'

proof "T179 — an unlabelled export claims to be labelled, so SC-014 can start over a set T180 has not produced" \
  src/runtime/reports/effect_corpus.py \
  "tests/unit/test_effect_corpus.py::test_an_unlabelled_export_does_not_claim_to_be_labelled" \
  's = s.replace("        return all(row.label is not None for row in self.rows)", "        return True")'

proof "T179 — a third disposition is admitted, so the corpus is no longer every allow and deny" \
  src/runtime/reports/effect_corpus.py \
  "tests/unit/test_effect_corpus.py::test_a_third_disposition_is_refused" \
  's = s.replace("        if self.disposition not in DISPOSITIONS:", "        if False:")'

proof "T179 — the reader opens writable, so a report can write the proxy's store" \
  src/runtime/reports/effect_corpus.py \
  "tests/unit/test_effect_corpus.py::test_the_reader_is_opened_read_only" \
  's = s.replace("self._conn = sqlite3.connect(f\"file:{self.path}?mode=ro\", uri=True)", "self._conn = sqlite3.connect(f\"file:{self.path}?mode=rw\", uri=True)")'

proof "T179 — the success-path import scan appends nothing, so a planted exporter edge is free" \
  tests/unit/test_effect_corpus.py \
  "tests/unit/test_effect_corpus.py::test_the_success_path_import_scan_fires_on_a_planted_exporter_edge" \
  's = s.replace("                found.append(imported)", "                pass")'

proof "T181 — the per-call threshold inherits 0.98, so the superseded per-tool number travels" \
  src/runtime/reports/effect_precision.py \
  "tests/unit/test_effect_precision.py::test_the_threshold_has_no_numeric_default" \
  's = s.replace("PER_CALL_THRESHOLD: object = UNSET", "PER_CALL_THRESHOLD: object = 0.98")'

proof "T181 — the unset branch releases writes, so a write capability ships while the threshold is unset" \
  src/runtime/reports/effect_precision.py \
  "tests/unit/test_effect_precision.py::test_writes_stay_blocked_while_the_threshold_is_unset" \
  's = s.replace("    if PER_CALL_THRESHOLD is UNSET:\n        return False", "    if PER_CALL_THRESHOLD is UNSET:\n        return True")'

proof "T181 — the document states 0.98 while the sentinel is unset, so a number is in force and nothing says so" \
  src/runtime/reports/effect_precision.py \
  "tests/unit/test_effect_precision.py::test_the_document_records_the_threshold_as_unset" \
  's = s.replace("            \"per_call_threshold\": None if unset else self.per_call_threshold,", "            \"per_call_threshold\": 0.98 if unset else self.per_call_threshold,")'

echo
_verdict="$PASS proved, $FAIL unproven"
[ "$SKIP" -gt 0 ] && _verdict="$_verdict, $SKIP skipped"
# Named unconditionally when non-zero and never folded into the others, because
# the whole point of the outcome is that it is visible from the summary line.
[ "$TIMEOUT" -gt 0 ] && _verdict="$_verdict, $TIMEOUT TIMED OUT"
# Named here for the same reason TIMED OUT is, and against the same failure: one
# line about a lost arm, 222 lines down inside a collapsed CI details block, is
# the quiet form of having no outcome at all. The summary line is the only part
# of this output anybody reliably reads.
[ "$UNREADABLE" -gt 0 ] && _verdict="$_verdict, $UNREADABLE BASELINE UNREADABLE"
# Named on the summary line for the reason the two above are, and against a
# failure this one has actually produced three times. `unproven` is the word that
# means a mechanism is dead; while these arms were counted in it, it was also the
# presenting symptom of a dirty baseline, of `deploy/` missing from the copy list,
# of `.github/` missing from it, and of `specs/` missing from it. Four unrelated
# conditions behind one word teaches a reader to discount the word.
[ "$UNUSABLE" -gt 0 ] && _verdict="$_verdict, $UNUSABLE UNUSABLE BASELINE"
echo "$_verdict"
if [ "$UNUSABLE" -gt 0 ]; then
  echo
  echo "  $UNUSABLE arm(s) name a test that was ALREADY FAILING before the tamper, so the"
  echo "  harness refused to score them. This run is NOT green, and it is NOT a claim"
  echo "  that those mechanisms are dead — nothing was established about them either"
  echo "  way. Read them as a dirty baseline, not as a result:"
  echo
  echo "    - if the whole suite is dirty, fix the suite and re-run; the sweep is not"
  echo "      a measurement until the baseline is clean."
  echo "    - if only a few arms are affected and they share a directory, suspect the"
  echo "      COPY LIST at the top of this file before suspecting the mechanisms."
  echo "      deploy/, .github/ and specs/ each reached this bucket that way."
  if [ -n "$_unlisted" ]; then
    echo
    echo "    The setup note is repeated here because this is the moment it matters."
    echo "    These top-level paths are in NEITHER list, so the work tree does not"
    echo "    have them and no test can read them:"
    echo
    echo "      $_unlisted"
    echo
    echo "    If one of the arms above names a test that reads one of those, the"
    echo "    cause is the copy list and not the mechanism."
  fi
fi
if [ "$UNUSABLE" -gt 0 ] && [ "$_py_failed" -gt 0 ]; then
  echo
  echo "  The baseline recorded ${_py_failed} of ${_py_total} python outcomes not passing, which is"
  echo "  where to start: these arms are downstream of that, not independent of it."
fi
if [ "$UNREADABLE" -gt 0 ]; then
  echo
  echo "  $UNREADABLE arm(s) name a test whose baseline line carries no verdict, so they"
  echo "  were never attempted. This run is NOT green, and it is NOT a skip: a skip"
  echo "  says the environment declined the test, and nothing declined these."
  echo "  Find what the test writes to stdout while it runs and stop it writing —"
  echo "  \`pytest -v\` puts the verdict on the node id's own line, and a write that"
  echo "  reaches the real file descriptor 1 pushes it onto the next line. Do not"
  echo "  reach for \`-s\` or PYTEST_ADDOPTS to read this output; they cause it."
fi
if [ "$TIMEOUT" -gt 0 ]; then
  echo
  echo "  $TIMEOUT arm(s) did not return within ${PROOF_TIMEOUT}s and were not measured."
  echo "  This run is NOT green. Re-running will not help: an arm that hangs has no"
  echo "  terminator once its mechanism is removed, and needs one in its own test."
fi
# After the last proof and before the verdict, so the record can only ever
# describe arms that actually ran. It reports; it decides nothing — the line
# below is still the only thing that carries the exit status.
_write_summary complete
[ "$FAIL" -eq 0 ] && [ "$TIMEOUT" -eq 0 ] && [ "$UNREADABLE" -eq 0 ] && [ "$UNUSABLE" -eq 0 ]
