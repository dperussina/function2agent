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
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
cp -r "$SRC/src" "$SRC/tests" "$SRC/tools" "$SRC/pyproject.toml" "$WORK/" 2>/dev/null
# The Go arms need the fixtures at the relative path the tests use
# (src/proxy/../../tests/fixtures), which the copy above already satisfies.
cd "$WORK" || exit 1

TAMPER="$SRC/tools/tamper.py"
BASELINE_PY="$WORK/.baseline-pytest.txt"
BASELINE_GO="$WORK/.baseline-go.txt"

# A wall-clock cap on one arm, and the script that applies it. See
# `tools/proof_timeout.py` for why this is a script rather than `timeout(1)`
# (macOS ships none) and why a timed-out arm gets its own outcome below.
#
# 300s is chosen against a measurement, not a feeling: the whole untampered
# suite is 980 outcomes in ~10s on the machine this was set on, and a proof runs
# **one** test. The slowest arms are the kernel-mechanism ones and they are
# seconds. So this is two orders of magnitude above any arm that is working, and
# an arm that reaches it is not slow — it is not coming back. Raise it with
# REMOVAL_PROOF_TIMEOUT if a genuinely long arm ever appears; do not lower it to
# make a hang report faster, because then it stops distinguishing the two.
CAP="$SRC/tools/proof_timeout.py"
PROOF_TIMEOUT="${REMOVAL_PROOF_TIMEOUT:-300}"
TIMED_OUT_STATUS=124

# One line per proof, tab separated, in the order they ran. Lives in $WORK so an
# interrupted run cannot leave a partial file behind that looks like a result.
RECORDS="$WORK/.summary-records"
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

# ---------------------------------------------------------------------------
# The baseline. Nothing below is attempted until this says the suite runs.

python3 -m pytest tests -v --tb=no -p no:cacheprovider >"$BASELINE_PY" 2>&1
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

HAVE_GO=0
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
  : >"$BASELINE_GO"
  echo "  baseline   ${_py_total} python outcomes (${_py_failed} not passing), no Go toolchain"
fi
echo

# _escape turns a pytest node id into something grep -E will match literally.
_escape () { printf '%s' "$1" | sed 's/[][\.*^$(){}?+|\/]/\\&/g'; }

# baseline_py: PASSED | SKIPPED | FAILED | ABSENT, for a node id or a file.
#
# ABSENT is the one that had no detection at all before. A renamed test makes
# `pytest` exit 4, the harness read any non-zero exit as the mechanism being
# load-bearing, and the proof reported `proved` while running nothing.
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
  echo SKIPPED
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
      echo "  UNUSABLE  $name — $test already fails before the tamper, so its failure after proves nothing"
      _record unproven test-already-failing
      FAIL=$((FAIL+1)); return 0 ;;
    SKIPPED)
      echo "  SKIPPED   $name — the test did not run here (privilege or platform)"
      _record skipped test-skipped-in-baseline
      SKIP=$((SKIP+1)); return 0 ;;
  esac
  return 1
}

# apply_tamper edits $2 per the snippet in $3, or explains why it could not.
# Returns 0 on success. `tools/tamper.py` owns the matching rules; see its
# docstring for why a match may be whitespace-insensitive and must be unique.
apply_tamper () {
  local name="$1" file="$2" snippet="$3" mode status reason
  cp "$file" "$file.orig"
  mode=$(python3 "$TAMPER" "$file" "$snippet" 2>"$WORK/.tamper-err")
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
    sed 's/^/            /' "$WORK/.tamper-err" | head -2
    _record unproven "$reason"
    FAIL=$((FAIL+1))
    mv "$file.orig" "$file"
    return 1
  fi
  if [ "$mode" = OK_NORMALIZED ]; then
    echo "  drifted   $name — the tamper matched only after whitespace normalization (a formatter moved this site)"
    _P_DRIFTED=yes
  fi
  return 0
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

proof "FR-036 Secret — a __str__ that discloses" \
  src/contracts/secret.py \
  "tests/invariants/test_secret_has_no_serializer.py" \
  's = s.replace("    def __str__(self) -> str:\n        return _marker(self._name)", "    def __str__(self) -> str:\n        return self._value")'

proof "FR-011 rule id — the deny/rule_id check removed" \
  src/supervisor/fs_decisions.py \
  "tests/invariants/test_rule_id_present.py::test_a_deny_without_a_rule_id_cannot_be_constructed" \
  's = s.replace("        if self.disposition == DENY and not self.rule_id:", "        if False:")'

# The tamper moves the field as well as defaulting it, and it has to. `verification` is the first
# field of a dataclass whose second field has no default, so adding a default to it alone is not a
# weaker contract — it is `TypeError: non-default argument 'payload' follows default argument` at
# class-definition time. The module then does not import, every test in the file errors during
# collection, and the harness scored that as `proved` for as long as the proof existed. Moving the
# field below `payload` is the edit a contributor would actually make, and it is the one both
# assertions in `test_verification_has_no_default_in_the_source` exist to catch.
proof "FR-025 result — verification given a default" \
  src/contracts/result.py \
  "tests/invariants/test_result_constructor.py" \
  's = s.replace("    verification: VerificationOutcome\n    payload: Any\n", "    payload: Any\n    verification: VerificationOutcome = VerificationOutcome.VERIFIED\n")'

proof "FR-006 taxonomy — closed membership becomes a prefix match" \
  src/contracts/terminal.py \
  "tests/invariants/test_terminal_taxonomy.py::test_membership_is_closed_not_a_prefix_match" \
  's = s.replace("    return name in NAMES", "    return name.startswith(chr(116)+chr(101)+chr(114)+chr(109)+chr(105)+chr(110)+chr(97)+chr(116)+chr(101)+chr(100)+chr(46))")'

proof "Q-10 no-default bounds — a default added" \
  src/contracts/config.py \
  "tests/invariants/test_no_default_bounds.py" \
  's = s.replace(chr(34)+"memory.max on the session cgroup"+chr(34)+", no_default_reason=_NO_DEFAULT_BOUND"+chr(41), chr(34)+"memory.max on the session cgroup"+chr(34)+", default="+chr(34)+"512MiB"+chr(34)+chr(41))'


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
  if [ "$HAVE_GO" -eq 0 ]; then
    echo "  SKIPPED   $name — no Go toolchain on PATH"
    _record skipped no-go-toolchain
    SKIP=$((SKIP+1))
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
  "tests/contract/test_canonical_determinism.py" \
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
  "tests/contract/test_schema_versions.py" \
  's = s.replace("    kind=\x22served_operation_set\x22,\n    version=\x221.0.0\x22,", "    kind=\x22served_operation_set\x22,\n    version=\x220.9.0\x22,")'

proof "T015 schema gate — a required field removed without a MAJOR bump" \
  src/contracts/schemas.py \
  "tests/contract/test_schema_versions.py" \
  's = s.replace("    required=(\x22schema_version\x22, \x22deployment_id\x22, \x22operations\x22),", "    required=(\x22schema_version\x22, \x22deployment_id\x22),")'

# The tamper names the guard inside `migrate`, not the string `raise MigrationError(`.
# That string occurs five times, and the first is at module scope inside the duplicate-registration
# loop — so the old tamper inserted a `return` outside a function, the module stopped parsing, and
# every test in it failed for a reason this proof does not claim. It read as `proved` for as long
# as it existed. `tools/check_tampers.py` is what surfaced it.
proof "T014 migration — a stale document passes through unmigrated" \
  src/contracts/migrations/__init__.py \
  "tests/contract/test_migrations.py" \
  's = s.replace("        if migration is None:\n", "        if migration is None:\n            return dict(document)\n")'

proof "T017 ownership — a non-owner may write" \
  src/contracts/ownership.py \
  "tests/invariants/test_writer_ownership.py" \
  's = s.replace("def require_write(", "def require_write(*_unused_a, **_unused_k):\n    return None\n\n\ndef _disabled_require_write(")'

proof "T016 scope columns — the caller supplies its own tenant" \
  src/contracts/repository.py \
  "tests/invariants/test_writer_ownership.py" \
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
  "tests/contract/test_configuration_failloud.py" \
  's = s.replace("    if missing or invalid:\n        raise ConfigError(_report(missing, invalid))", "    if False:\n        raise ConfigError(_report(missing, invalid))")'

proof "T033 unvalidated marking — the marker dropped from the rendering" \
  src/contracts/unvalidated.py \
  "tests/contract/test_unvalidated_marking.py" \
  's = s.replace("        return f\x22{self.value} ({MARKER}: {self.provenance})\x22", "        return str(self.value)")'

proof "FR-036 marker — the key name dropped, leaving an undiagnosable trace" \
  src/contracts/secret.py \
  "tests/invariants/test_secret_has_no_serializer.py::test_the_marker_names_the_key_it_stands_for" \
  's = s.replace("    return f\x22<redacted:Secret {name}>\x22 if name else REDACTED", "    return REDACTED")'

proof "T037 rule id — a decision span may omit its rule" \
  src/runtime/trace.py \
  "tests/contract/test_trace_spans.py" \
  's = s.replace("        if self.kind in DECISION_KINDS and self.decision is None:", "        if False:")'

proof "Principle VI — a state_transition span may omit its predicate inputs" \
  src/contracts/transition.py \
  "tests/unit/test_state_transition.py" \
  's = s.replace("        if rule.selects_among_alternatives and not self.predicate_inputs:", "        if False:")'

proof "Principle VI — bounds.check stops recording the inputs it did not match" \
  src/supervisor/bounds.py \
  "tests/unit/test_state_transition.py" \
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

proof "FR-036 trace — the Secret scan stops at a nested dataclass" \
  src/runtime/trace.py \
  "tests/contract/test_trace_spans.py::test_a_secret_nested_in_any_carrier_field_is_refused" \
  's = s.replace("    elif is_dataclass(value) and not isinstance(value, type):", "    elif False:")'

proof "T038 journal location — a ledger inside the session root is accepted" \
  src/runtime/trace_budget.py \
  "tests/contract/test_budget_journal.py" \
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
  's = s.replace("    return [p for p in _sandbox_sources() if p.name != \x22__init__.py\x22]", "    return _sandbox_sources()")'

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
  's = s.replace("                transition = self.machine.terminate(\n                    session_id,\n                    terminal_state=terminal.OPERATOR_TERMINATED.name,\n                    at=self.clock())\n                recorded = transition.terminal_state", "                transition = self.machine.interrupt(session_id, at=self.clock())")'

# T047, the caller-visible half — a second mechanism, not a second reading of the
# one above. Routing cancellation to `terminate()` moves the row; carrying the
# recorded name back out of teardown is what makes the caller agree with it. The
# tamper leaves the row correct and reports the loop's `None`, which is the
# divergence a reviewer would otherwise have to take on trust.
proof "T047 cancellation — the terminal state teardown recorded is not reported" \
  src/runtime/runner.py \
  "tests/unit/test_cancellation.py::test_a_cancelled_run_names_operator_terminated_as_its_terminal_state" \
  's = s.replace("            terminal_state=(outcome.terminal_state if outcome.terminal_state\n                            is not None else recorded),", "            terminal_state=outcome.terminal_state,")'

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
  's = s.replace("        spend = costs.price_usd(\n            provider=parsed.provider, model=model,\n            input_tokens=inputs, output_tokens=outputs, as_of=as_of)", "        spend = 0.0")'

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
  's = s.replace("    if schema not in (LEGACY_MODEL_OUTCOME_SCHEMA, MODEL_OUTCOME_SCHEMA):", "    if False:")'

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

echo
_verdict="$PASS proved, $FAIL unproven"
[ "$SKIP" -gt 0 ] && _verdict="$_verdict, $SKIP skipped"
# Named unconditionally when non-zero and never folded into the others, because
# the whole point of the outcome is that it is visible from the summary line.
[ "$TIMEOUT" -gt 0 ] && _verdict="$_verdict, $TIMEOUT TIMED OUT"
echo "$_verdict"
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
[ "$FAIL" -eq 0 ] && [ "$TIMEOUT" -eq 0 ]
