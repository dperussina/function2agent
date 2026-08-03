"""Enumerate reachable models per provider and surface the cheapest candidates.

Model-list endpoints only: zero tokens, zero cost. Prints model IDs only, never a key.

Recovered verbatim from /tmp/f2a-probe-runtime/pick_models.py on 2026-08-02. This is
the model-selection step, not a measured arm: it is how the four model strings the
other probes use were chosen. See the README.
"""
import json
import os
import urllib.error
import urllib.request

import envload

envload.load()


def get(url, headers):
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, {"error": e.read().decode()[:200]}
    except Exception as e:  # noqa: BLE001
        return 0, {"error": f"{type(e).__name__}"}


def show(label, ids, hint):
    ids = sorted(ids)
    match = [i for i in ids if any(h in i.lower() for h in hint)]
    print(f"\n{label}: {len(ids)} models")
    for i in match[:14]:
        print("   ", i)


s, b = get(
    "https://api.anthropic.com/v1/models?limit=100",
    {"x-api-key": os.environ["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01"},
)
show(f"anthropic [{s}]", [m["id"] for m in b.get("data", [])], ("haiku", "fable", "sonnet"))

s, b = get(
    "https://api.openai.com/v1/models",
    {"Authorization": "Bearer " + os.environ["OPENAI_API_KEY"]},
)
show(f"openai [{s}]", [m["id"] for m in b.get("data", [])], ("mini", "nano"))

s, b = get(
    "https://api.x.ai/v1/models",
    {"Authorization": "Bearer " + os.environ["XAI_API_KEY"]},
)
show(f"xai [{s}]", [m["id"] for m in b.get("data", [])], ("grok",))

s, b = get(
    "https://generativelanguage.googleapis.com/v1beta/models?pageSize=200&key="
    + os.environ["GEMINI_API_KEY"],
    {},
)
show(
    f"gemini [{s}]",
    [m["name"].replace("models/", "") for m in b.get("models", [])],
    ("flash-lite", "2.5-flash"),
)
