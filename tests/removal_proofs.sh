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

PASS=0
FAIL=0
SKIP=0

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
  exit 2
fi
_py_total=$(grep -cE ' (PASSED|FAILED|SKIPPED|ERROR|XFAIL|XPASS)' "$BASELINE_PY")
_py_failed=$(grep -cE ' (FAILED|ERROR)' "$BASELINE_PY")

HAVE_GO=0
if command -v go >/dev/null 2>&1; then
  HAVE_GO=1
  (cd "$WORK/src/proxy" && go test -v ./...) >"$BASELINE_GO" 2>&1
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
      FAIL=$((FAIL+1)); return 0 ;;
    FAILED)
      echo "  UNUSABLE  $name — $test already fails before the tamper, so its failure after proves nothing"
      FAIL=$((FAIL+1)); return 0 ;;
    SKIPPED)
      echo "  SKIPPED   $name — the test did not run here (privilege or platform)"
      SKIP=$((SKIP+1)); return 0 ;;
  esac
  return 1
}

# apply_tamper edits $2 per the snippet in $3, or explains why it could not.
# Returns 0 on success. `tools/tamper.py` owns the matching rules; see its
# docstring for why a match may be whitespace-insensitive and must be unique.
apply_tamper () {
  local name="$1" file="$2" snippet="$3" mode status
  cp "$file" "$file.orig"
  mode=$(python3 "$TAMPER" "$file" "$snippet" 2>"$WORK/.tamper-err")
  status=$?
  if [ "$status" -ne 0 ]; then
    case "$status" in
      3) echo "  NO-OP     $name — the tamper matched nothing; the source moved under this proof" ;;
      4) echo "  AMBIGUOUS $name — the tamper matches more than one site; it does not name a mechanism" ;;
      5) echo "  NO-OP     $name — the tamper ran and changed nothing" ;;
      7) echo "  BROKEN    $name — the tampered source does not parse; the test would fail for the wrong reason" ;;
      *) echo "  BROKEN    $name — the tamper script failed to run" ;;
    esac
    sed 's/^/            /' "$WORK/.tamper-err" | head -2
    FAIL=$((FAIL+1))
    mv "$file.orig" "$file"
    return 1
  fi
  if [ "$mode" = OK_NORMALIZED ]; then
    echo "  drifted   $name — the tamper matched only after whitespace normalization (a formatter moved this site)"
  fi
  return 0
}

proof () {
  local name="$1" file="$2" test="$3" python_edit="$4"
  local verdict
  verdict=$(baseline_py "$test")
  if report_unrunnable "$verdict" "$name" "$test"; then return; fi

  apply_tamper "$name" "$file" "$python_edit" || return

  local output status
  output=$(python3 -m pytest "$test" -q -p no:cacheprovider 2>&1)
  status=$?
  if [ "$status" -eq 0 ]; then
    echo "  UNPROVEN  $name — the test still passes with the mechanism removed"
    FAIL=$((FAIL+1))
  elif echo "$output" | grep -qE '^(ERROR|INTERNALERROR)' && ! echo "$output" | grep -qE '[0-9]+ failed'; then
    # The test did not run: an import or collection error, not an assertion.
    echo "  BROKEN    $name — the tamper broke collection rather than the mechanism"
    FAIL=$((FAIL+1))
  else
    echo "  proved    $name"
    PASS=$((PASS+1))
  fi
  mv "$file.orig" "$file"
}

proof "FR-048 mount namespace — pivot_root removed" \
  src/supervisor/mounts.py \
  "tests/integration/test_mount_namespace.py::test_an_undeclared_location_is_absent_not_denied" \
  's = s.replace("    _linux.pivot_root(mount_plan.new_root, old)", "    return")'

proof "FR-048 read-only bind — the MS_REMOUNT pass removed" \
  src/supervisor/mounts.py \
  "tests/integration/test_mount_namespace.py::test_a_read_only_declaration_is_actually_read_only" \
  's = s.replace("        _linux.mount(None, dest, None,\n                     _linux.MS_REMOUNT | _linux.MS_BIND | _flags_for(loc))", "        pass")'

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
  if [ "$HAVE_GO" -eq 0 ]; then
    echo "  SKIPPED   $name — no Go toolchain on PATH"
    SKIP=$((SKIP+1))
    return
  fi
  local verdict
  verdict=$(baseline_go "$test")
  if report_unrunnable "$verdict" "$name" "$test"; then return; fi

  apply_tamper "$name" "$file" "$python_edit" || return

  local output
  output=$(cd "$WORK/src/proxy" && go test -run "$test" ./... 2>&1)
  local status=$?
  if [ "$status" -eq 0 ]; then
    echo "  UNPROVEN  $name — the test still passes with the mechanism removed"
    FAIL=$((FAIL+1))
  elif echo "$output" | grep -q 'build failed'; then
    # A package that will not compile fails every test in it, which is not the
    # same claim as the test noticing the mechanism is gone.
    echo "  BROKEN    $name — the tampered package does not build; no test ran"
    FAIL=$((FAIL+1))
  else
    echo "  proved    $name"
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

echo
if [ "$SKIP" -gt 0 ]; then
  echo "$PASS proved, $FAIL unproven, $SKIP skipped"
else
  echo "$PASS proved, $FAIL unproven"
fi
[ "$FAIL" -eq 0 ]
