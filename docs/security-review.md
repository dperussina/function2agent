# Security review — T202

This is the checkable record, not an essay. `tests/contract/test_security_review.py`
walks the same live surfaces. Dropping one of the four named failure classes,
claiming a closed gap, or inventing a green "secure" verdict fails that test.

This is a **review of the enforcement point as built**, not a new mechanism.
The four classes are the population. A fifth is not added to look complete.
U-44 stays open.

## Surfaces walked

The list is the population, not an example. Dated findings, research and
harness results stay off the walk.

| Path | Why it is on the walk |
| --- | --- |
| `src/proxy/form.go` | Stage 2: raw-head parse, ambiguous framing, parser-differential check |
| `src/proxy/framing_test.go` | T094 corpus: arm A (stage 2) and arm B (on the wire, which layer refused) |
| `src/proxy/method.go` | Stage 4: method allowlist evaluated together with destination |
| `src/proxy/reoriginate.go` | Stage 7: the proxy injects the operator's target credential |
| `src/proxy/capability.go` | Stage 1: opaque handle resolved against a lease (FR-050) |
| `src/proxy/pipeline.go` | Seven-stage sequencer; fail-closed is structural |
| `src/analysis/deputy_inspection.py` | FR-056 inspection of the *target* as deputy; U-44's named procedure |
| `tests/contract/test_deputy_inspection.py` | Load-bearing: a `clean` outcome is a stated rule set, not a proof |

## The four named failure classes

For each class: what is built, what is measured, what remains unmeasured.
No class is marked closed. No class is dropped.

| Class | Built | Measured | Unmeasured |
| --- | --- | --- | --- |
| Parser differential | Stage 2 parses the raw request head itself and refuses when that parse and `net/http`'s disagree about method or target (`TestParserDifferentialOnRequestLineIsRefused`). Q-01 bought Go for this component (T003, T083–T092, T094). Finding 006-adjacent: two components disagreeing about what the request *is* is a complete defeat of FR-018. | This component versus `net/http` on `go1.24.3`, on the T094 corpus and the planted method/target mismatch. | This component versus the **target application's** HTTP parser. That is the Q-01 class as named — Go proxy vs target — and no corpus drives the same bytes at a live target parser and compares method and path. |
| Request smuggling | CL.TE (`Content-Length` together with `Transfer-Encoding: chunked`) is `RuleAmbiguousFraming`. Keep-alives are disabled. `TestSmuggledRequestNeverReachesUpstream` asserts the hidden second request is never parsed, never evaluated, and never reaches the pinned upstream. | On the wire against this component's own capture: `/smuggled` is absent; the connection produces one response. | A real target that would have parsed the smuggled request if it had arrived. HTTP/2 framing. Cases outside the T094 corpus. |
| Ambiguous framing | Stage 2 **rejects rather than normalises**. The T094 corpus names CL.TE, two Content-Lengths (conflicting and identical), `chunked, identity`, duplicate `Transfer-Encoding`, obs-fold, `Content-Length` with leading `+` / trailing OWS / list form, CONNECT, Upgrade. Arm B records **which layer** refused — `net/http` or this pipeline — because claiming stage 2 caught a case `net/http` already 400'd would be false. Raw head unavailable is refused, not skipped. | The corpus, on `go1.24.3`. Three cases `net/http` accepts and normalises (CL.TE, identical Content-Lengths, obs-fold on an ordinary header) are the ones stage 2 must catch. | Frames not in the corpus. HTTP/2 prior-knowledge beyond the `PRI * HTTP/2.0` refusal. |
| Confused-deputy composition | The proxy **holds the target credential** and injects it on re-origination (FR-050, T084, T091, T165). The sandbox never sees it. FR-056 / T079 inspects the *target* as deputy — outbound call sites reachable from a served handler — as a **stated rule set**, not a proof. Both `deputy` and `uninspectable` are denied. | Inspection procedure exists and is decidable (decline is a determinate answer). Capability/lease honouring is tested. The credential does not appear in model context, artifacts, traces or persisted state on the T165 scan. | **U-44**. Whether a given target's safe-method operations can induce outbound requests is unmeasured on any target. Naming a procedure does not measure the property. The egress guarantee remains conditional on that unmeasured property. U-44 is **open**. |

## What this review does not claim

- The enforcement point is not declared **secure**. The four classes have
  mechanisms; two of them (parser differential vs the target, U-44) are
  unmeasured on the composition that would actually defeat FR-018 / FR-014.
- U-44 is not discharged, not narrowed to closed, and not reclassified as
  a finding. It stacks with the proxy holding the credential: the effect
  gate is the entire authorization boundary for anything the target will
  do with that credential, including fetches the proxy never sees.
- A fifth class is not invented. A green verdict is not invented.
