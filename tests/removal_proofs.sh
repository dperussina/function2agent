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

set -uo pipefail

SRC=$(pwd)
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
cp -r "$SRC/src" "$SRC/tests" "$SRC/pyproject.toml" "$WORK/" 2>/dev/null
# The Go arms need the fixtures at the relative path the tests use
# (src/proxy/../../tests/fixtures), which the copy above already satisfies.
cd "$WORK" || exit 1

PASS=0
FAIL=0
SKIP=0

# A tamper whose match string has drifted applies nothing, the test passes for the
# ordinary reason, and the result is reported as UNPROVEN — indistinguishable from a
# real gap in the tests. That silently weakens every proof in this file as the source
# moves under it, so a no-op edit is its own failure class.
proof () {
  local name="$1" file="$2" test="$3" python_edit="$4"
  cp "$file" "$file.orig"
  python3 - "$file" <<PY
import sys, pathlib
p = pathlib.Path(sys.argv[1]); s = p.read_text()
before = s
$python_edit
if s == before:
    raise SystemExit(3)
p.write_text(s)
PY
  local edit_status=$?
  if [ "$edit_status" -ne 0 ]; then
    if [ "$edit_status" -eq 3 ]; then
      echo "  NO-OP     $name — the tamper matched nothing; the source moved under this proof"
    else
      echo "  BROKEN    $name — the tamper script failed to run"
    fi
    FAIL=$((FAIL+1))
    mv "$file.orig" "$file"
    return
  fi
  # A test that skipped exits 0, which reads as "passed with the mechanism
  # removed" — so an unprivileged run would report every kernel proof as a gap
  # in the tests rather than as a proof that could not be attempted. Collect the
  # outcome before interpreting the exit status.
  local output
  output=$(python3 -m pytest "$test" -q 2>&1)
  local status=$?
  if [ "$status" -eq 0 ] && echo "$output" | grep -qE '^[0-9]+ skipped|[0-9]+ skipped in ' \
     && ! echo "$output" | grep -qE '[0-9]+ passed'; then
    echo "  SKIPPED   $name — the test did not run here (privilege or platform)"
    SKIP=$((SKIP+1))
  elif [ "$status" -eq 0 ]; then
    echo "  UNPROVEN  $name — the test still passes with the mechanism removed"
    FAIL=$((FAIL+1))
  else
    echo "  proved    $name"
    PASS=$((PASS+1))
  fi
  mv "$file.orig" "$file"
}

echo "Removal proofs"
echo

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

proof "FR-025 result — verification given a default" \
  src/contracts/result.py \
  "tests/invariants/test_result_constructor.py" \
  's = s.replace("    verification: VerificationOutcome\n", "    verification: VerificationOutcome = VerificationOutcome.VERIFIED\n")'

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
  if ! command -v go >/dev/null 2>&1; then
    echo "  SKIPPED   $name — no Go toolchain on PATH"
    SKIP=$((SKIP+1))
    return
  fi
  cp "$file" "$file.orig"
  python3 - "$file" <<PY
import sys, pathlib
p = pathlib.Path(sys.argv[1]); s = p.read_text()
$python_edit
assert s != p.read_text(), "the removal edit matched nothing; the proof would be vacuous"
p.write_text(s)
PY
  if [ $? -ne 0 ]; then
    echo "  UNPROVEN  $name — the removal edit did not apply"
    FAIL=$((FAIL+1))
    mv "$file.orig" "$file"
    return
  fi
  if (cd "$WORK/src/proxy" && go test -run "$test" ./... >/dev/null 2>&1); then
    echo "  UNPROVEN  $name — the test still passes with the mechanism removed"
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
# Note the tamper strings below carry TWO spaces after `classPrivate:`. That is gofmt's alignment
# of the two-entry map, and the single-space form these proofs used while the map had one entry
# now matches nothing. A drifted tamper reports rather than passing silently, which is how this
# was caught.

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

proof "T014 migration — a stale document passes through unmigrated" \
  src/contracts/migrations/__init__.py \
  "tests/contract/test_migrations.py" \
  's = s.replace("        raise MigrationError(", "        return dict(document)\n        raise MigrationError(", 1)'

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

proof "FR-038 ordering — two spans may share a position" \
  src/runtime/trace.py \
  "tests/contract/test_trace_spans.py::test_two_spans_cannot_occupy_one_position" \
  's = s.replace("            if span.position in self._written:", "            if False:")'

proof "FR-036 trace — a Secret may reach a span" \
  src/runtime/trace.py \
  "tests/contract/test_trace_redaction.py::test_a_secret_cannot_be_placed_in_a_span_at_all" \
  's = s.replace("        _refuse_secrets(self.detail, \x22detail\x22)", "        pass")'

proof "T038 journal location — a ledger inside the session root is accepted" \
  src/runtime/trace_budget.py \
  "tests/contract/test_budget_journal.py" \
  's = s.replace("    if journal == root or root in journal.parents:", "    if False:")'

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
  's = s.replace("        \x22DERIVED from documented feature introduction and NOT TESTED on that \x22\n        \x22kernel; every run to date was on 6.12\x22", "        \x22established\x22")'

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
