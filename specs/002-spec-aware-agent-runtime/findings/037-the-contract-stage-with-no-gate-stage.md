# Finding 037 — the egress contract numbers **eight** request-pipeline stages and the enforcement point registers **six gate stages and one final stage**. The stage with no counterpart is stage 4, the address class, and its absence is **sound only because FR-016 pins exactly one address**. That conditional is the finding: nobody had written down that stage 4's soundness is a consequence of FR-016 rather than a property of the pipeline, so a future widening of FR-016 would open a hole that no test named

**Date**: 2026-08-10
**Feature**: 002. Measures
[`contracts/egress-policy.md`](../contracts/egress-policy.md) against
[`src/proxy/main.go`](../../../src/proxy/main.go),
[`src/proxy/pipeline.go`](../../../src/proxy/pipeline.go) and
[`src/proxy/addresses.go`](../../../src/proxy/addresses.go), as built under T095.
**Reports. Repairs nothing in the enforcement point.** The divergence is not a defect and no Go
source was changed to close it. What is added is a test that pins it — see §4.
**User Story**: none directly. Prompted by T095, whose brief made the contract's *enumeration* the
subject and so forced a stage-by-stage correspondence that had not been taken before.
**Owner decision**: **none is minted here and no register was edited.** §5 states the one decision
this finding would need if FR-016 ever widened, and explicitly does not take it.
**Model spend**: **$0.0000.** No model was called and no credential was read. Static reads of Go and
Markdown, plus `pytest` runs of the file being built.
**Method**: **the correspondence is a static reading and is reported as one.** The two behavioural
claims below — that the untampered correspondence holds, and that a planted extra stage is caught —
were each produced by planting the case and watching the test fire, and the plants are named in §4.
No claim here describes runtime behaviour of the proxy on the strength of reading its source; where
this document says the dial-time check runs, that is a claim about *where the call site is*, and it
is written as such.
**Reproduction**: every command is given in full in the section that uses it.
**Numbering note**: `036` was the high-water mark across `specs/*/findings/`, established two ways
and no "next free number" in any other document was consulted. (1) The numeric prefix of every file
matching `specs/*/findings/*.md`, `ls specs/*/findings/*.md | sed 's#.*/##' | sort -V | tail`: max
`036`. (2) A corpus-wide boundary-anchored citation search with **match-only output taken before
sorting**, because ripgrep's default output carries the path and `sort -V` then sorts by path so the
last line is not the maximum: max `036`, plus `037` occurring only as this document's own forward
reference from `tests/contract/test_egress_policy.py`. `037` was free at that moment and re-checked
free immediately before saving.

---

> ## THE RESULT IN ONE PARAGRAPH
>
> The contract's request pipeline is numbered 1–8. Six of those stages are registered gate stages in
> `defaultStages`, one is the re-originator, and **stage 4, the address class, is neither**. Its
> check exists — `addresses.go` classifies at policy load and again on every dial — but it is not a
> per-request gate, so it cannot appear in the pipeline and cannot produce a per-request decision
> record in the way the other seven do. Under FR-016 the destination is **one pinned address**, so a
> class decided at load time and re-checked at dial time is the same decision a per-request gate
> would reach, every request. **The equivalence is a consequence of FR-016's cardinality and of
> nothing else.** That was true before this finding and was written down nowhere.

> ## WHAT THIS FINDING DOES NOT CLAIM
>
> It does **not** claim the address class is unchecked; it is checked twice, and
> `src/proxy/addresses_test.go` covers that behaviour and predates this document. It does **not**
> claim the contract is wrong to number eight stages — the contract is describing the *policy*, and
> the policy does have eight stages. It does **not** propose registering a stage 4. And it takes
> **no** owner decision: §5 states the trigger under which one becomes owed.

---

## 1. The two enumerations, side by side

The contract's numbering is read out of [`contracts/egress-policy.md`](../contracts/egress-policy.md)
by `pipeline_stages()` in the new test file; the registration is read out of
[`src/proxy/main.go`](../../../src/proxy/main.go)'s `defaultStages` and its `NewReoriginator` call by
`registered_stage_names()`. Both parsers are in
[`tests/contract/test_egress_policy.py`](../../../tests/contract/test_egress_policy.py) and both have
a control arm asserting they read the document and the source rather than a constant.

| contract stage | registered counterpart |
|---|---|
| 1 destination | `destination` gate |
| 2 method | `method` gate |
| 3 scheme | `scheme` gate |
| 4 **address class** | **none** |
| 5 header | `header` gate |
| 6 body | `body` gate |
| 7 deny list | `denylist` gate |
| 8 re-originate | `Reoriginator` (final stage, not a gate) |

Reproduce:

```bash
cd /path/to/tree
.venv/bin/python -m pytest tests/contract/test_egress_policy.py -q
```

## 2. Where stage 4 actually runs

Two call sites, both in [`src/proxy/addresses.go`](../../../src/proxy/addresses.go):

- **at policy load**, so an artifact naming a destination in a denied class is refused before the
  proxy listens rather than at the first request that would use it; and
- **at dial**, so the class is re-decided against the address actually being connected to.

Neither is reached through `Pipeline.Run`, which is why neither can be a `stageName` and why a
correspondence test finds a hole at 4 and only at 4.

## 3. Why the absence is sound today, and exactly what it rests on

FR-016 requires the destination to be **one pinned address**, not a name and not a set. A single
address has a single class. A class decided once at load and re-decided at dial is therefore the
same verdict a per-request gate would return on every request in the run, and the per-request gate
would be doing no work the two existing checks do not already do.

**The load-bearing term is FR-016's cardinality, not the address-class rule.** If FR-016 ever
widened — a set of pinned addresses, a per-request destination selection, anything that lets two
requests in one run dial two different addresses — the load-time check stops being equivalent (it
would have to be a check over the whole set), and only the dial-time check would remain
per-connection. That is a live check, so the widening would not be a hole *immediately*; it would be
a hole the moment anything reached the dialler by a path that skipped it.

## 4. What now pins it, and the two plants that show the pin fires

`test_exactly_one_contract_stage_has_no_gate_stage` asserts the divergence is **exactly** stage 4 —
not "at most one", and not "the sets differ". Two failures it therefore reports that a looser
assertion would not:

- a **second** undocumented stage appearing, and
- **stage 4's dial-time check disappearing** while the contract still numbers it.

Plant 1, the correspondence holds untampered and fails on a planted divergence:
`test_the_stage_correspondence_reports_a_planted_divergence` is the negative control the
experiment-design skill's **Rule 8** asks for — this experiment's positive result is *an absence*
(no unmatched stage beyond 4), and an absence is what a broken parser also reports.

Plant 2, a registered stage silently unregistering is caught. Declared as a removal proof in
[`tests/removal_proofs.sh`](../../../tests/removal_proofs.sh), tampering
`src/proxy/main.go` to drop `NewMethodStage` from `defaultStages` while leaving the type in place,
and **observed proved** in the run recorded at
`tests/batteries/results/removal-proofs.latest.json`:

```bash
cd /path/to/tree
bash -c 'PATH="$PWD/.venv/bin:$PATH" bash tests/removal_proofs.sh'
# 311 proved, 0 unproven, 13 skipped
# macOS 26.2 arm64, unprivileged (euid 501), go1.24.3, pytest 8.3.4, CPython 3.12.11
```

The 13 skipped are the pre-existing mount-namespace, filesystem-battery, egress-battery and
bounds-exhaustion arms, all of which need Linux and privilege; the figure is labelled with platform
and privilege because the skip half of it is a property of the host and not of the proof set.

## 5. The decision this does not take

If FR-016 widens, someone owes a decision between (a) registering an address-class gate stage so the
contract's eight and the pipeline's eight coincide, and (b) restating stage 4 in the contract as a
load-and-dial check rather than a request-pipeline stage. **Neither is taken here**, because FR-016
has not widened and a decision taken against a hypothetical would be a decision nobody could
evaluate. What this finding buys is that the trigger is written down next to the reason, so the
choice is available at the moment it is needed instead of being rediscovered.

## 6. Corrections to what was believed going in

- **The brief for T095 said the contract "gained a missing address-class stage at commit 4c788d3".**
  Accurate as to the *contract*. The reading it invites — that the enforcement point gained a stage
  to match — is not: no gate stage was added, and the pipeline registered six gates before that
  commit and six after. The contract gained a *stage number*; the code already had the checks, in
  two places that are not the pipeline.
- **The brief said loopback "is exemptible on the same terms as any other address".** The contract
  says something narrower and the code implements the narrower thing: exactly **two** classes are
  exemptible (`loopback` and `rfc1918_private`), and there is **one** exemption slot in total shared
  between them — `pinnedExemption` holds a single `netip.Addr`. Every other named class is denied
  with no exemption path at all. The brief's own follow-on sentence, "one address in total, not one
  per class", states the containment correctly; the first sentence overstates which classes are in
  scope. Both halves are now asserted by
  `test_two_exemptible_classes_and_exactly_one_exemption`, and both a widened struct and a deleted
  contract clause are declared removal proofs against it.
