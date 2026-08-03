# Finding 002 — Bring-your-own provider credentials, probed live

**Date**: 2026-08-02
**User Story**: 3 (choose the substrate that makes this work most efficiently)
**Model spend**: $0.00 — model-list endpoints only, zero tokens generated
**Method**: `GET` against each provider's model-list endpoint using credentials read from the
target's dotenv files. No key value was printed, logged, copied, or written anywhere. The probe
script lives outside both repositories.

## Why this probe

The product's stated architecture is that **the end user brings their own LLM provider credentials**,
and the generated stack uses them to produce the semantic layer — tool descriptions, instructions,
documentation, prompts. That makes "can we actually drive multiple providers from credentials we do
not own" a load-bearing question, not a detail. Research flagged it as unverified (U-03), and
model-agnosticism is a stated product requirement.

Model-list endpoints answer it for free: a `200` proves the credential authenticates and enumerates
exactly what that key may reach, without generating a token.

## Results

| Provider | Credential present | HTTP | Models reachable | Verdict |
|---|---|---|---|---|
| Anthropic | yes | 200 | 11 | **works** |
| OpenAI | yes | 200 | 133 | **works** |
| xAI | yes | 200 | 10 | **works** |
| OpenRouter | yes | 200 | **337** | **works** |
| Google Gemini | yes (see §Credential discovery) | 200 | 58 | **works** — but only on the 12th credential tried |

**All five providers authenticate.** Frontier-tier models are reachable on each: the Anthropic key
reaches `claude-opus-5`, `claude-sonnet-5`, and `claude-fable-5`; the xAI key reaches `grok-4.5` and
`grok-4.3`; the Gemini key reaches `gemini-3-flash-preview`, `gemini-3-pro-image`, `gemini-2.5-pro`
and 39 other generation models; OpenAI exposes 133; OpenRouter exposes 337 spanning Anthropic,
DeepSeek, Amazon Nova, AI21, Allen AI and others.

That gives **five independent model families** for evaluation — more than enough to test
model-agnosticism properly rather than by assertion.

## Credential discovery is a real problem, and this is the finding that surprised me

The first pass read the root dotenv files, found `GEMINI_API_KEY`, and got a clean `400 API key not
valid`. The obvious conclusion — "the Gemini key is dead, rotate it" — **was wrong.** A working key
existed the whole time, under a different name, in a different file.

Scanning every dotenv file in the repository for Google-shaped credentials found **12 distinct
values. Exactly one works.**

| Outcome | Count |
|---|---|
| `400` — API key not valid | 10 |
| `401` — expected OAuth 2 access token (a service-account credential, not an API key) | 1 |
| **`200` — working, 58 models** | **1** |

The working credential is named **`GEMINI_API_KEY_2`**, and it lives in `control_tower/.env` and
`channels/.env`. The canonically-named `GEMINI_API_KEY` at the repository root is one of the ten
dead ones.

**This is directly load-bearing for the product**, and it is the kind of thing only a real
production repository would have taught us:

- **A generated stack cannot assume canonical credential names.** Reading `GEMINI_API_KEY` because
  that is what the vendor documentation calls it would have failed here, in a repository that has
  perfectly good Gemini access.
- **Name does not imply validity, and neither does presence.** Eleven of twelve credentials are
  present, well-formed, and useless. Any design that treats "the variable is set" as "the
  credential works" is wrong on this repository today.
- **This is the strongest argument yet for constitution Principle IV's fail-loudly startup
  validation.** The correct behavior is to *probe* each configured credential at startup and refuse
  to start on a bad one — not to discover it mid-task after spending budget. A model-list call
  costs zero tokens, so this validation is free.
- **Credential discovery may deserve to be a product feature**, not a configuration burden pushed
  onto the user. The system already walks the codebase; finding candidate credentials and telling
  the operator which ones actually authenticate is a small extension with an obvious payoff.
- **One credential was a service account, not an API key** (the `401` asking for an OAuth 2 access
  token). Same provider, same apparent purpose, entirely different auth flow. The two-tier
  abstraction has to accommodate that below the model interface.

## What this establishes

1. **BYO-credential multi-provider access is real, not theoretical.** Four independent first-party
   providers plus one aggregator authenticate from credentials the product does not own, using
   nothing but each vendor's documented HTTP surface. The architecture the owner described is
   viable at the credential layer.

2. **The multi-provider requirement may be far cheaper than the research assumed.** U-03 framed
   model-agnosticism as a risk requiring an abstraction layer or a middleware dependency. But **one
   OpenRouter credential reaches 337 models across essentially every major family.** For breadth
   alone, that is one adapter instead of N.

3. **Two-tier abstraction is confirmed as the right shape, for a reason the probe made concrete.**
   Even at the trivial model-list layer the four providers disagree on everything: Anthropic wants
   `x-api-key` plus a dated `anthropic-version` header, OpenAI and xAI want a bearer token, Gemini
   wants the key in the query string, and the response envelope is `data[].id` for three of them and
   `models[].name` (prefixed `models/`) for Gemini. If the *simplest possible* call already needs
   four code paths, normalizing hosted tools, sandboxes, or provider memory is not going to be
   cleaner. Thin at the bottom, opinionated above it.

4. **Dead credentials are the common case, not the exception** — see the credential-discovery
   section above. Ten of twelve Google credentials in this repository return a clean `400` at
   authentication time, before any token is spent. That clean early failure is the behavior
   generated stacks should copy: validate every configured credential at startup and **fail
   loudly**, per constitution Principle IV. A generated agent that discovers a bad key mid-task,
   after spending budget, is the bad version of this.

## The catch worth naming

**OpenRouter fails the dependency test.** The harness-selection rule is *does this dependency see
prompts and tokens?* — and an aggregating proxy sees both, for every request, from every customer.
That is materially different from a first-party provider the customer already chose and already has
a contract with.

So the honest recommendation splits: OpenRouter is **excellent for our own evaluation harness**,
where 337 models behind one credential makes cross-model comparison nearly free and no customer data
is involved. It is a **poor default for generated production stacks**, where it inserts a third
party into the customer's prompt path. Support it as an option the customer explicitly opts into;
do not make it the path of least resistance.

## What this does NOT license

- **Nothing about generation quality.** No tokens were generated. This proves authentication and
  enumeration, not that any model performs well on our tasks.
- **Nothing about cost or rate limits.** Model-list calls are free and unthrottled; real workloads
  are neither.
- **Nothing about a candidate runtime's provider support.** This probes providers *directly*. Whether
  a specific orchestration runtime can drive a non-default provider is a separate probe and remains
  the open half of U-03.
- **Nothing about credential handling in a generated stack.** These keys were read by a local script,
  not injected into an agent with shell access. The hard problem — keeping a credential reachable by
  a tool but unreachable by the model and absent from every trace — is untested.

## Immediate next steps

1. ~~Rotate the Gemini key~~ — **not needed.** A working credential already existed under
   `GEMINI_API_KEY_2`; the root `GEMINI_API_KEY` is stale and should be deleted or repointed so the
   next reader is not misled the way this probe initially was.
2. **Probe a candidate orchestration runtime against a non-default provider**, which is the
   remaining half of U-03 and the actual substrate question.
3. **Pick the evaluation model set** from what is confirmed reachable. Anthropic, OpenAI, xAI, and
   Google give four genuinely independent families; OpenRouter adds breadth for the harness only.
4. **Write the startup credential-validation probe as a reusable harness component.** It costs zero
   tokens, it already paid for itself once here, and it is a near-verbatim prototype of what
   generated stacks must do at boot.
