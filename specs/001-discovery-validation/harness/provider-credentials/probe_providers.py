"""Probe provider credentials via model-list endpoints. Zero tokens, zero cost.

Reads keys from the operator's dotenv files, never prints a key value, never writes a key
anywhere. Prints provider, HTTP status, model count, and a few sample model ids.

Produces the results table in findings/002-provider-credentials.md.

Recovered from /tmp/f2a_probe_providers.py on 2026-08-02. The only change from the
script that produced the finding is that the dotenv root is now a parameter rather
than a hardcoded path into a private repository — see envroot.py and the README.

Usage:  python3 probe_providers.py --env-root PATH
        F2A_ENV_ROOT=PATH python3 probe_providers.py
"""
import json
import os
import urllib.error
import urllib.request

import envroot

ROOT = envroot.resolve()

# The original probe read only the top-level dotenv files, and the finding's
# "Credential discovery" section is the story of why that was not enough.
ENV_FILES = [".env", ".env.agents", ".env.local"]

WANTED = [
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "GEMINI_API_KEY",
    "XAI_API_KEY",
    "OPENROUTER_API_KEY",
]


def load_keys() -> dict[str, str]:
    """Parse KEY=VALUE lines without executing anything."""
    found: dict[str, str] = {}
    for fname in ENV_FILES:
        path = os.path.join(ROOT, fname)
        if not os.path.exists(path):
            continue
        for name, value in envroot.parse(path).items():
            if name in WANTED and name not in found and value:
                found[name] = value
    return found


def get(url: str, headers: dict[str, str]) -> tuple[int, dict | None, str]:
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            return resp.status, json.loads(resp.read().decode()), ""
    except urllib.error.HTTPError as exc:
        return exc.code, None, exc.read().decode()[:160]
    except Exception as exc:  # noqa: BLE001 - probe reports any failure verbatim
        return 0, None, f"{type(exc).__name__}: {exc}"[:160]


def model_ids(provider: str, body: dict | None) -> list[str]:
    if not body:
        return []
    if provider == "GEMINI_API_KEY":
        return [m.get("name", "").replace("models/", "") for m in body.get("models", [])]
    return [m.get("id", "") for m in body.get("data", [])]


# Four providers, four different auth conventions and two different response
# envelopes. Finding 002 result 3 is that this disagreement exists at the
# simplest possible call, which is why the bottom abstraction tier stays thin.
ENDPOINTS = {
    "ANTHROPIC_API_KEY": lambda k: (
        "https://api.anthropic.com/v1/models?limit=100",
        {"x-api-key": k, "anthropic-version": "2023-06-01"},
    ),
    "OPENAI_API_KEY": lambda k: (
        "https://api.openai.com/v1/models",
        {"Authorization": f"Bearer {k}"},
    ),
    "GEMINI_API_KEY": lambda k: (
        f"https://generativelanguage.googleapis.com/v1beta/models?key={k}&pageSize=200",
        {},
    ),
    "XAI_API_KEY": lambda k: (
        "https://api.x.ai/v1/models",
        {"Authorization": f"Bearer {k}"},
    ),
    "OPENROUTER_API_KEY": lambda k: (
        "https://openrouter.ai/api/v1/models",
        {"Authorization": f"Bearer {k}"},
    ),
}

keys = load_keys()
print(f"dotenv root: {ROOT}")
print(f"files read : {', '.join(ENV_FILES)}\n")
print(f"{'PROVIDER':<22} {'PRESENT':<8} {'STATUS':<7} {'MODELS':<7} SAMPLE / ERROR")
print("-" * 100)

for name in WANTED:
    key = keys.get(name)
    if not key:
        print(f"{name:<22} {'no':<8} {'-':<7} {'-':<7} key not found in dotenv files")
        continue
    url, headers = ENDPOINTS[name](key)
    status, body, err = get(url, headers)
    ids = [m for m in model_ids(name, body) if m]
    verdict = "OK" if status == 200 else "FAIL"
    sample = ", ".join(ids[:3]) if ids else err
    print(f"{name:<22} {'yes':<8} {status:<7} {len(ids):<7} [{verdict}] {sample[:70]}")

print()
print("Sampled model families per working provider:")
for name in WANTED:
    key = keys.get(name)
    if not key:
        continue
    url, headers = ENDPOINTS[name](key)
    status, body, _ = get(url, headers)
    if status != 200:
        continue
    ids = sorted(m for m in model_ids(name, body) if m)
    print(f"\n  {name} -> {len(ids)} models")
    for mid in ids[:14]:
        print(f"      {mid}")
    if len(ids) > 14:
        print(f"      ... and {len(ids) - 14} more")
