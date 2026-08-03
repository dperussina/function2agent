# Provider-credential harness — do bring-your-own credentials actually authenticate?

Produces the numbers in
[`findings/002-provider-credentials.md`](../../findings/002-provider-credentials.md).

Run `./run.sh /path/to/tree`. **Zero model spend**: every call is a `GET` against a
provider's model-list endpoint, which proves a credential authenticates and enumerates
exactly what it may reach without generating a token.

> **Recovered, not reconstructed.** These scripts are the ones that produced the
> finding, recovered from `/tmp/f2a_probe_providers.py` and `/tmp/f2a_probe_gemini.py`
> on **2026-08-02** and sanitized. The changes are enumerated in
> [§What changed during recovery](#what-changed-during-recovery) and none of them
> touch the measurement.

## The one thing you must supply

**The dotenv search root is a parameter with no default, and the probe exits rather
than guessing.** The original scripts hardcoded a path into a private repository on
the author's laptop; that path is gone from this harness and must not come back.

```bash
./run.sh /path/to/tree                      # or
F2A_ENV_ROOT=/path/to/tree ./run.sh         # or per-script:
python3 probe_providers.py --env-root /path/to/tree
```

The tree is read and never written to. It should contain `.env` files defining some of
`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`, `XAI_API_KEY`,
`OPENROUTER_API_KEY`.

## Credential handling

No script here prints, logs, returns, or writes a credential value, and there is no
result artifact that could contain one. Values live in local variables, go out as a
request header or query parameter, and are discarded.

Where the finding needs to tell two credentials apart — the discovery scan finds twelve
distinct Google-shaped values — it uses a **truncated SHA-256 fingerprint** as the
handle. That is how a table can say "these ten are dead and this one works" without any
of the eleven appearing anywhere.

## What each piece does

| File | Purpose |
|---|---|
| `run.sh` | End-to-end reproduction: the canonical-name probe, then the discovery scan, then the name inventory. |
| `envroot.py` | Resolves the dotenv search root from `--env-root` or `F2A_ENV_ROOT` and **fails loudly if neither is set**. Also the `.env` walker and a deliberately dumb `KEY=VALUE` parser — no interpolation, no shell, no dotenv library, so a hostile dotenv file can only produce a dictionary. |
| `probe_providers.py` | **The results table.** One model-list call per provider under its canonical variable name. Prints provider, HTTP status, model count, and sample model ids. |
| `probe_gemini_discovery.py` | **The credential-discovery table.** Walks every `.env` file in the tree, harvests every Google-shaped value, and tests each one. This is the arm that found the working key under a non-canonical name after the canonical one returned a clean `400`. |
| `inventory_env_names.py` | Lists variable **names only** across the tree. Regenerates the reconnaissance step; see below. |

## What the finding measured, and what you should expect

Against the tree the finding used, on 2026-08-02:

| Probe | Reported |
|---|---|
| `probe_providers.py` | Anthropic 200/11 models, OpenAI 200/133, xAI 200/10, OpenRouter 200/337, Gemini 200/58 |
| `probe_gemini_discovery.py` | 12 distinct Google-shaped values: ten `400`, one `401` (a service-account credential, not an API key), one `200` with 58 models, named `GEMINI_API_KEY_2` |

**These counts are properties of a specific dotenv tree at a specific moment, not of
this harness.** Against your tree the shape of the result reproduces — which providers
authenticate, whether the canonical name is the working one — and the integers will
not. Model counts also drift as vendors publish and retire models, so even against the
same credentials the 11/133/10/337/58 figures are a snapshot rather than a target.

## There is no `results/` directory, and that is not an oversight

The probes were run interactively and **their stdout was never captured to a file**.
The finding's tables were transcribed from the terminal. Nothing survives that could
honestly be committed as a run record, and inventing one would make the harness look
more reproducible than it is.

So: the *method* is fully reproducible from this directory and the *original raw
output is gone*. Re-running against the same tree is the only way to check the
finding's integers, and per the paragraph above some of them will legitimately differ.

## What changed during recovery

| Change | Why | Does it affect the measurement? |
|---|---|---|
| Hardcoded private-repo path → `--env-root` / `F2A_ENV_ROOT`, no default | The original path pointed into an unrelated private repository holding live production keys. It must not be committed, and a wrong-tree default is a silent failure. | No. Same scan, operator-named root. |
| Shared `envroot.py` extracted | Both scripts had their own copy of the walker and parser. | No. Same logic. |
| Dropped a dead entry from the discovery scan's name hints | The original hint list contained `"GgOOGLE"`, compared against an upper-cased name, so it could never match anything. | No — it was unreachable. See the known limitation below. |
| Added `inventory_env_names.py` | Replaces a committed artifact with a regenerable one. | No. It is reconnaissance, not a measured arm. |

`/tmp/f2a_keynames.txt` — the 153 variable names the original reconnaissance produced —
was **confirmed to contain names only**: 153 lines, every one matching `^[A-Z][A-Z0-9_]*$`,
zero `=` characters, no value-shaped tokens. It is nonetheless **not committed**, because
it is an inventory of an unrelated private repository's environment-variable naming, it
is worthless against any other tree, and `inventory_env_names.py` regenerates the same
thing from whatever root the operator names. Nothing in the finding depends on it.

## Known limitation in the discovery scan, preserved deliberately

The scan matches variable names against the hints `GEMINI`, `GOOGLE_AI`, `GENERATIVE`,
`GOOGLE_GENAI`, `GOOGLE_API_KEY`, `VERTEX`. **A bare `GOOGLE` hint is absent**, so a
variable named e.g. `GOOGLE_KEY` or `GOOGLE_TOKEN` would not be harvested.

This is left exactly as it ran. Adding the hint would very likely change the candidate
count away from the 12 the finding reports, which would quietly break correspondence
between this harness and the document it is supposed to reproduce. It is recorded here
as a limitation rather than repaired: the finding's claim is "at least 12 distinct
values, exactly one of which works," and a wider scan could only raise the first number.

## Prerequisites

Python 3 and outbound HTTPS. No third-party packages — the probes use `urllib` from the
standard library, deliberately, so that a dependency tree is not a reason reproduction
fails.
