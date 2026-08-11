# function2agent

Point an agent at your running application. Verify what it did against contracts
derived from your code. Fail closed when either one moves.

`function2agent` derives executable contracts from a codebase, drives the running
application through its own external interface, checks every result against those
contracts, and **denies anything that is not a read** at a runtime interception
point. **v1 is read-only**: no write ships until the gate's precision is measured,
which takes the first branch of a rule pre-registered before any experiment ran
([OD-10](specs/001-discovery-validation/plan.md), D-22, U-43).
**Deciding which operations deserve to become tools is v2** — a pre-registered
pivot criterion fired and took it out of v1
([OD-09](specs/001-discovery-validation/plan.md), D-21).

**Accurate emission needs to reach that running application, not just read its
source.** Static analysis recovers what a source tree *declares*; a deployment
serves something else — the target measured here serves 22 or 67 operations from
one tree, depending on how it is started. The best resolution is still to ask the
running instance, and it survives having its schema taken away: probing scored
**precision 1.0000 at path granularity on all seven targets**, schema or no
schema. But it is **exact about paths, not about verbs** — on a route serving
`GET` and withholding `POST`, precision falls to 0.8000, and every measured error
is a method-level one
([finding 011](specs/001-discovery-validation/findings/011-reachability-without-schema.md)).
Recovering the answer from the codebase alone *did* clear its pre-registered gate,
but at **0.9538 in the worst of eight configurations — a margin under one
operation**
([finding 010](specs/001-discovery-validation/findings/010-deployment-reachability.md)).
So reach is a precondition of the pipeline, not a refinement at its end. Three
Python routers, one real application; nothing here reaches another language.

> **Status: discovery is closed, it re-scoped the product to about a tenth of what
> was planned, and ~~the production spec is now blocked on one more experiment~~ all
> three of the capabilities it left behind ship without measurement.** No
> product code exists. Feature `001-discovery-validation` reached nine of the fifteen
> positions on its experiment ladder for ~~**$24.82** ($24.73 + $0.09 + $0.0003)~~
> **≈ $35.17** ($35.0817 + $0.09 + $0.0003) and
> closed on OD-09. That total is a sum across findings — the ceiling test, E5 and E6
> — so no single finding reports it; the two bases for it, and the recomputation you
> can run yourself, are in
> [`VERDICT.md`](specs/001-discovery-validation/VERDICT.md) §6. *(Spend restated
> 2026-08-03 — superseded, not wrong: $24.82 covered four ceiling-test sessions and two
> more ran afterwards. **$35.0817 is the ceiling test's total, not the feature's**;
> conflating the two was the third basis error this corpus has made on a spend figure.)*
> ~~**The next artifact is an experiment, not a specification** — all three surviving
> v1 capabilities are unmeasured, and the one that decides whether v1 has a product
> at all is whether a contract-derived verifier catches anything a general-purpose
> LLM judge does not (OD-11, P-07).~~
> **⚠️ The single most important thing to know about this repository: all three v1
> capabilities — drift detection, the write gate's effect-classification precision,
> and the verifier's margin over an LLM judge — ship without measurement.** They are
> stated together, once, at
> [`VERDICT.md` §2](specs/001-discovery-validation/VERDICT.md#all-three-v1-capabilities-ship-unmeasured).
> The third of them was declared **UNMEASURED** and deferred to production on
> **OD-14**, which retires OD-11's block on the spec and records the whole disposition
> as *a deliberate, knowing departure from this project's prove-before-build
> discipline*. **The next artifact is the production specification again.**
> **The one that could kill the project came back a tie:** across
> three families the curated tool surface never won on success rate — 27/27 against
> 26/27 on lookups, 9/10 against 10/10 on joins, and the shell baseline wins the
> per-record family 4/4 against 2/4 — while costing **~~2.8×~~ ~~2.2× to 9.3×~~ 2.20× to 4.366× less within session wherever it
> succeeded at all**
> ([finding 012](specs/001-discovery-validation/findings/012-ceiling-test-per-family.md)).
> **That fired a pivot rule pre-registered before any experiment ran** — a baseline
> within 5 points meant *"a spec-aware runtime plus a verifier plus drift detection
> — real, but ~10× smaller."* It is honored as written (OD-09, D-21). **The
> capability half of the thesis is not supported and the spec may not assert it.
> ~~"Safer" rests on a single observation whose replication was priced at ~$15 and
> deliberately declined**, so it travels as an assumption to be validated.~~ **"Safer"
> is withdrawn as stated and scoped to *hand-written* surfaces (2026-08-03, C-18): the
> immunity traces to a human declining to use the API's own filter, so a **synthesized
> tool inherits the defect** — the transfer question, not the declined $15 replication,
> is the binding limit, and "synthesis is safer" may not be asserted at all.** **And two
> of the three families were mis-calibrated under a second pre-registered rule, so
> the re-scope rests on one family at n = 4** (U-42).
> Verdict: [`VERDICT.md`](specs/001-discovery-validation/VERDICT.md).
> Architecture: [`research/14-architecture-synthesis.md`](research/14-architecture-synthesis.md).

## The thesis

The obvious version of this product — read a codebase, emit a tool per function —
is already commoditized. At least seven shipping products generate MCP servers
from OpenAPI specs or source, mostly for free, and the author of FastMCP (which
powers an estimated 70% of MCP servers) publicly warns that mechanically
converted servers "technically work but fail in practice."

So the value was supposed to be in refusing to generate most of them — a
300-endpoint application yielding roughly 25 tools, not 300. Four capabilities were
claimed to separate a useful agent stack from a function dump. **Discovery tested
one, and split the four in half.**

**v1 — and now the whole product:**

1. **Contract-derived verification** — verifiers built from signatures, return
   types, postconditions, and exception classes rather than from a model's opinion.
   Measured and buildable, at a thin margin: the ≥ 0.80 gate cleared at **0.8696**
   literal, **0.7681** validated, and both must be quoted (D-09).
2. **Drift detection** — failing closed when the code or the deployment moves.
   Promoted from fourth of four to half the product, and it turned out to have two
   clocks rather than one (O-04).

**v2 — deferred with tool synthesis (OD-09, D-21):**

3. **Promotion selection** — deciding which operations deserve to be tools at all.
   **Never run**; it needs a generator. E7 measured only that a hand-written surface
   returning *records* loses to a shell pipeline while one returning *answers* wins
   on cost by 35×, which constrains how v2 selects rather than whether it should.
4. **Effect classification** — knowing what is read-only, reversible, or
   destructive. **The differentiator defers; the obligation does not.** Constitution
   Principle IV binds every emitted tool, and v1 emits a shell and an HTTP client
   that can issue `DELETE`. So v1 classifies **per call at a runtime interception
   point that can block**, rather than per tool at generation time (D-22, C-16) —
   and because that classifier has never been scored, **the point denies everything
   it cannot resolve as a read** (OD-10). Read-only removes the destructive-action
   risk and **not** the exfiltration risk: a shell plus network access is an egress
   path whatever the target's verbs say (C-16). **And the network half of that
   sentence is a requirement we already owe and have not built** — Principle IV's
   *first* bullet asks for a network allowlist, every argument above is about its
  *second*, and v1 ships open outbound network (C-17). ~~OD-12, **proposed, not
  decided**~~ — **decided 2026-08-03: all sandbox egress traverses one mandatory
  proxy that enforces the destination allowlist and the HTTP method allowlist
  together, so it sees a `curl` in a shell exactly as it sees the runtime's HTTP
  client (OD-12), and Principle IV bullet 1 was amended the same day to say what
  the allowlist has to be — pinned addresses, host *and* port, DNS denied or
  proxied, loopback / RFC 1918 / link-local / metadata denied even on an
  allowlisted host (OD-13, constitution v1.2.0).** Closing it confines the agent
  to the target's API and cuts the direct channel; it does **not** cut the leg,
  because the target's own API can fetch URLs on the agent's behalf (U-44).
  **The defensible claim is bounded blast radius plus detection, not
  prevention — and that is unchanged by the decision, which relocated the
  mechanism rather than proving anything about it.**

**What replaced the missing half is not nothing.** Access turned out to be most of
the capability and synthesis most of the efficiency — and the one case where the
curated surface actually won was **an API that failed open**, silently handing back
60 records where 7 were right. A verifier is exactly what catches that.

What makes the first of those tractable for us in particular: because we start
from *functions*, we inherit a verification signal most agent frameworks have to
invent. That matters
because LLM self-critique without external feedback measurably *degrades*
reasoning ([arXiv:2310.01798](https://arxiv.org/abs/2310.01798)), and LLM judges
are anti-correlated with truth on exactly the failure that matters most — an
agent claiming success it did not achieve.

## Repository map

| Path | What it is |
|---|---|
| [`specs/`](specs/) | `001-discovery-validation` is closed: the spec, the experiment ladder, the findings, one committed harness per experiment position that ran, and the [closing verdict](specs/001-discovery-validation/VERDICT.md). |
| [`research/`](research/) | 15 research documents + an index with reading paths. The evidence base. |
| [`.specify/`](.specify/) | GitHub Spec Kit 0.15.1 scaffolding. Contains the ratified [constitution](.specify/memory/constitution.md). |
| [`.cursor/skills/`](.cursor/skills/) | 18 project skills encoding the research as decision procedures, plus 10 Spec Kit phase prompts. See the [roster](.cursor/skills/README.md). |
| [`docs/spec-kit-workflow.md`](docs/spec-kit-workflow.md) | How to drive the spec process. |
| [`tools/`](tools/) | The instruments. [`instruments.py`](tools/instruments.py) is the census of every check that can fail, and the thing that keeps that census from drifting away from [the workflow that runs them](.github/workflows/ci.yml). |
| `examples/` | Git-ignored. Nine vendored reference repos (codegraph, spec-kit, Google ADK, Anthropic SDK/cookbooks, NVIDIA OO Agents). Read-only. |

## Where to start

- **New here?** [`research/README.md`](research/README.md) has reading paths for
  four different situations. Then [`14-architecture-synthesis.md`](research/14-architecture-synthesis.md).
- **Want the current state?** [`VERDICT.md`](specs/001-discovery-validation/VERDICT.md)
  adjudicates every success criterion, then [`findings/`](specs/001-discovery-validation/findings/).
  Each finding opens with its gate verdict and closes with what it does *not* license.
- **Making an architecture decision?** The synthesis carries a
  [decision register](research/14-architecture-synthesis.md#3-the-decision-register)
  (D-01 … D-22), a contradiction register, and an
  [uncertainty register](research/14-architecture-synthesis.md#5-consolidated-uncertainty-register)
  marking which entries block.
- **Writing the spec?** [`.specify/memory/constitution.md`](.specify/memory/constitution.md)
  first — its four non-negotiable principles are plan gates, not suggestions.
- **Running the checks?** `python3 tools/instruments.py` prints every instrument
  in the repository, what it checks, and where it runs; `--run` runs the fast
  ones and *names the ones it did not run*. Do not work from a remembered list.
  For a week this project's briefs carried five gates and reported all five
  green while a sixth was red, and every one of those reports was true about
  the five. See [`tools/instruments.py`](tools/instruments.py).

## How work proceeds here

**Spec-driven development is the process of record.** Implementation does not
begin before a spec, a plan, and a task list exist. Phases run through Spec Kit
skills in Cursor, invoked with a **hyphen**: `/speckit-specify`, not
`/speckit.specify`. Full sequence in [`docs/spec-kit-workflow.md`](docs/spec-kit-workflow.md).
Every experiment pre-registers its gate before it runs; a tie is reported as a tie.

## Current state

**Decided.** Tools invoke the target over its existing external interface
(HTTP/RPC), never in-process (D-01) — which under OD-09 is not a constraint on a
generator but a description of the whole runtime. MCP is never the internal calling
convention; the export-adapter half defers with synthesis, since the artifact it
exported was the tool catalogue (D-06, amended). Two physically separate credential
planes, with no secret ever entering model context (D-07).
Loop by default; escalate only on a declared constraint (D-10). Extend
`codegraph`: route recall **0.8961** at precision 1.0000 against a framework's own
route table ([finding 004](specs/001-discovery-validation/findings/004-recall-against-authoritative-key.md),
D-14). Contracts are derivable; the ≥ 0.80 gate cleared thinly, at **0.8696**
([finding 007](specs/001-discovery-validation/findings/007-contract-extraction.md),
D-09). Every derived field carries provenance, a validation result, and the
deployment it describes (D-17). Reachability resolves by probing, at path
granularity (D-18). The product is ~~**cheaper and safer, not more capable**~~
**cheaper *within session* (2.20×–4.366×) and safer *only for hand-written surfaces*,
not more capable**, quoted
per family and never pooled (D-19, C-18). **Ship self-hosted, and design so a hosted tier
stays reachable without a rewrite** (OD-08, D-20). **v1 is a spec-aware runtime, a
contract-derived verifier and drift detection; synthesis, promotion selection,
effect classification and decomposition leave v1** (OD-09, D-21). **Every call is
tier-resolved at a runtime interception point that can block** (D-22) — and
**v1 is read-only, so that point allows a resolved read and denies everything
else, including writes, with no runtime approval path** (OD-10). ~~**The
verifier-versus-LLM-judge experiment runs before the production spec, which is
blocked on it** (OD-11).~~ **The verifier's marginal detection over an LLM judge
is UNMEASURED, the production spec is unblocked, and the measurement is deferred
to production traffic with the pre-registered gate unchanged** (OD-14, retiring
OD-11).

**Decided during execution, ~~at about three weeks on the critical path~~ — and
the runtime it decided on has since been dropped.** ~~We live inside Google ADK's
graph execution, lifecycle, HTTP/SSE serving and provider abstraction~~ (OD-01).
**Reversed in part 2026-08-03 by OD-15: ADK is not in v1 at all.** Three of
OD-01's four grounds did not survive contact with a one-agent, one-loop design —
graph execution has no graph, the provider adapter was measured referencing one
provider's opaque reasoning field **zero times** against a spec requiring the
round-trip for four, and the serving limb rested on nothing measured. Lifecycle
survived alone and one limb does not justify the dependency. `litellm` goes with
it, because it declares no license (OD-16), and Linux is the only supported
platform (OD-17).

**Say the cost out loud.** Nine capabilities move from adopt to build — the loop,
the runner, the session store, checkpoint and resume, tool-schema translation,
the per-provider cost table, a spend ceiling, the terminal signals, and the
serving event stream — and **the ~~three weeks~~ figure covers none of them, with
no re-derived estimate anywhere**
([`14`](research/14-architecture-synthesis.md) U-48). We still rely on **none** of
the four loop-safety primitives (OD-01's surviving half), and we no longer inherit
the one that was measured working. What is unchanged is the measurement and the
reasoning: ADK's budget ceiling reset on resume, so a ceiling of 3 permitted 6
cycles and a crashing agent had no effective ceiling at all
([finding 006](specs/001-discovery-validation/findings/006-graph-loop-primitives.md)),
and **partial safety machinery is more dangerous than absent, because it invites
reliance** — which is the argument that made one surviving limb insufficient.
Coding nodes run on our own executor, since the Claude Agent SDK is
Anthropic-only for any different model family and that collides with
bring-your-own-credentials (OD-02, unchanged; it is still an opt-in path).

**Decided by the ceiling test, and it is not the decision we expected.** The
capability claim is gone, and with it most of v1. Cost survives and replicated
everywhere the tool arm succeeded at all; **"safer" survives on one observation,
unreplicated by choice, and is an assumption the spec must validate rather than a
property it may assert** (U-41). One liability nobody designed for arrived with it:
where no tool fits the question, the tool arm burns its whole budget and submits
nothing, against a shell arm that exhausted nothing in 31 scored attempts. So the
emitted stack needs a **general fallback path** — which pushes toward fusing the two
agent classes, the thing [`07`](research/07-product-vision.md) §3.4 calls the lethal
trifecta by construction. **Under OD-09 that pressure gets worse rather than
better**: with no synthesized surface, the general path is not a fallback beside the
curated tools, it is the entire tool surface. The production spec reconciles that
against Principle IV rather than inheriting it (OD-07, C-15). One synthesis
constraint is licensed and worth more than the headline: **tools that return answers
help; tools that return records do not.**

**Decided by building the E19 harness and then declining to run it (OD-14,
2026-08-03).** The verifier's *mechanism* is demonstrated and was not fitted — the
postcondition arm detects all 9 numeric value errors including all 3 sub-1%
near-misses in the eligible population, ~~with **zero false alarms across 220 clean
positives**~~ **and raises zero false alarms on the 96 oracle-positives whose own run
manifest declares the battery under test, 93 of which it compared** — *the offline
full-corpus sweep, restricted to records that need no cross-battery join to attest;
restated 2026-08-03 on that denominator, where the result is stronger rather than
weaker and the struck figure was not wrong
([finding 018](specs/001-discovery-validation/findings/018-verifier-false-alarm-attested-denominator.md)).
`0 of 220` remains true as a statement and is not a rate, because 45 of the 220 were
declined as `unverifiable` and so could never have entered the numerator; the pooled
rate is 0 of 175 compared. The detection count and the false-alarm count above are
over two different populations and are not one measurement — on the attested
population both sides share one denominator and read 2 of 2 false successes flagged,
0 false alarms on 96 positives. The `FPR_c2 = 0/60` quoted elsewhere is the
judge-scored sample and a smaller population again, and the three must never be merged
([`14`](research/14-architecture-synthesis.md) §3.2)* — through a
six-rung precision ladder committed before any derivation was written that
**contains no numeric constant**. What is unmeasured is strictly whether an LLM
judge would have caught the same failures: no judge call was ever billed, and the
corpus cannot answer it — 2 surviving discriminative traces, three pre-registered
riders capping the verdict independently, four of seven task families lost to the
eligibility rule. **The verifier works; nobody knows whether it is needed.** One
design constraint survives at zero cost and outlives the number the gate would
have printed: the failure that matters was schema-conformant end to end, so the
production verifier must **recompute against an independent source** rather than
re-check the same contract.

**Still needs an experiment, and now it is v2 work.** Whether synthesis reaches the
hand-written ceiling. Whether promotion selection beats exposing everything. Which
agent class ships first — only the *through the running application* half was
measured. The decomposition axis. Static effect classification, scheduled into
feature 001 and never measured. **Two things are in v1 and unmeasured, which is a
different and sharper problem:** drift detection was scheduled for a Phase 5 that
never ran, and the verifier's *marginal detection over an LLM judge* — the number
that was supposed to earn it headline status — was scheduled for a Phase 2 that
never ran either. Between them they are the whole of v1. ~~**OD-11 schedules the
second one and blocks the production spec behind it; drift detection is still
unmeasured and still unscheduled, which makes it the sharper of the two.**~~
**OD-14 unschedules the second one — declared UNMEASURED and deferred to production
— so *all three* v1 capabilities now ship without measurement
([`VERDICT.md` §2](specs/001-discovery-validation/VERDICT.md#all-three-v1-capabilities-ship-unmeasured)).
Drift detection remains the sharpest of the three: it has no harness, no
pre-registration and nothing scheduled, while the verifier at least has a
demonstrated mechanism.**

**Open, and needs a human decision.** How much of the codebase-side analysis
survives at all: OD-09 shrinks it from *decompose and synthesize* to *derive
contracts where no schema is published, and detect source drift*, and nobody has
sized that build. ~~Whether v1 performs writes is **settled in principle and unproven
in practice** — D-22 says yes, gated per call, and U-43 records that the gate's
precision has never been measured against anything.~~ **Closed 2026-08-03 by OD-10:
v1 performs no writes.** U-43 stays open and stays blocking — it is now the
*exit condition* from read-only rather than a risk being carried — and it shrank to
one measurable error shape, a side-effecting endpoint reached by a safe method.

## Next actions

1. ~~**Run the verifier-versus-LLM-judge experiment. The production spec is blocked
   on it** (OD-11, P-07, P-09).~~ **RETIRED *as an action* 2026-08-03 by OD-14 — the harness was
   built, self-tested and dry-run at $0.00, and then not executed, because its corpus
   cannot answer the question.** The reasoning stands: if a general-purpose judge catches everything a
   contract-derived verifier catches, the verifier is not a differentiator and — with
   promotion selection and effect classification already in v2 — there is no v1
   product to specify. **The margin is declared UNMEASURED and the measurement moves
   into production instrumentation.** The gate is inherited verbatim from
   [`11-validation-plan.md`](research/11-validation-plan.md) §8 rather than
   re-derived, and travels ~~unchanged~~ **unevaluated** *(corrected 2026-08-03: the
   struck word was not wrong, it was silent — it blurred three states this record
   keeps apart, which is the recurring failure in this corpus)*: ≥ 10 pp → headline
   feature, < 10 pp → CI detail, judge AUROC < 0.5 → a constitutional ban on LLM
   judges in the success path.
   Read those three branches as a rule waiting for its input, not as a rule that
   ran: **neither the success condition nor the failure
   condition ever evaluated**, because both read a quantity defined over judge
   verdicts and **no judge verdict exists anywhere** — every judge row in every
   committed artifact is a stub at `cost_usd: 0.0` with `model: null`. The third
   branch reads the judge's own AUROC, which was likewise never computed. **So
   nothing clears this gate and nothing fails it**, and the verifier's present
   headline status rests on [finding 007](specs/001-discovery-validation/findings/007-contract-extraction.md)'s
   extraction accuracy rather than on the marginal-detection number the gate is
   about. The three states, kept apart: **OD-11's block on the spec is superseded**
   by OD-14; **the measurement is deferred** to production instrumentation; **the
   hypothesis is UNMEASURED and not answered** — a null on *power*, not on the
   hypothesis, so a future measurement is unprejudiced in either direction and H2 is
   not retired. One further trap in the quantity itself: the gate reads *marginal*
   detection, over the subset **the judge passed**. What a judge-free harness can
   compute is a plain **detection rate** over everything the oracle failed, and this
   corpus has quoted the second where the first was meant — `D_c2 = 10 of 15` is a
   detection rate and is not a number this gate can read.
2. **Write the production specification, at the OD-09 scope** — it is item 1 again.
   It inherits **six**
   things it must settle rather than assume: the general-fallback requirement
   against Principle IV (C-15), ~~"safer" as an assumption rather than a property
   (U-41)~~ **"safer" scoped to hand-written surfaces, with "synthesis is safer"
   forbidden outright (C-18, U-41)**, the effect gate's unmeasured precision, which OD-10 turns into the exit
   condition from read-only (U-43), a spend ceiling that survives a crash — no
   layer of the stack has been shown to enforce one (U-30) — **instrumentation for the
   verifier's margin against a shadow judge on real traffic (OD-14), and a verifier
   specified as recomputation against an *independent source* rather than as
   schema-conformance checking, which is the one design constraint E19 produced at
   zero cost**.
3. **Decide what a schema-free catalogue is allowed to promise.** E15 returned:
   taking the schema away costs nothing in path-level accuracy, but no schema-free
   mechanism resolves *which verbs* a path serves, and the one that would — the
   `Allow` header — is wrong in opposite directions on three routers (U-39). **OD-09
   raises the stakes on this rather than lowering them:** the verb is the crude
   effect proxy D-22's gate leans on, so a catalogue that cannot resolve verbs
   cannot resolve tiers either, and under OD-10 every such call is denied — which
   turns an accuracy question into a coverage question.
4. **Size the surviving analysis layer.** It shrank rather than disappeared, and no
   estimate exists for the smaller build.
5. ~~**Apply the constitution amendment OD-03 drafted.** It was deferred pending the
   ceiling test on the reasoning that a retired thesis makes it moot. The thesis was
   not retired, so the condition is discharged and D-17 stays decided-but-unenforceable
   until the sentence lands.~~ ✅ **Done 2026-08-02** — the constitution is at v1.1.0,
   Principle I carries OD-03's sentence, and D-17's four requirements are
   merge-blocking rather than advisory.
6. **Then feature `002-runtime-and-verifier`** — the loop-safety primitives OD-01
   priced at 2.5–3.5 weeks (unchanged by the pivot, and now the largest item on the
   critical path, and **not blocked by item 1**), the verifier, the drift detector,
   and the D-22 gate. `003-synthesis-spike` inherits everything OD-09 deferred.

The point of feature 001 was to try to kill the idea cheaply. It cost ~~**$24.82**~~
**≈ $35.17**
and it killed most of it: the half that was going to be sold, and then — through a
rule written before anyone had a stake in the answer — most of the rest. What
survived is smaller, better-evidenced, and harder to demo. Kill criteria:
[`11-validation-plan.md`](research/11-validation-plan.md) §7 and the gate tables in
[`plan.md`](specs/001-discovery-validation/plan.md); how they were adjudicated:
[`VERDICT.md`](specs/001-discovery-validation/VERDICT.md).

## License

[Apache 2.0](LICENSE).
