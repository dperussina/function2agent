"""SPIKE - E16. Free model-list probe. Costs nothing; generates no tokens.

Exists so the model each arm drives is *chosen against what the credential can
actually reach* rather than assumed from documentation. Finding 002 established
that a credential's reachable set is not guessable — one of its Google keys was
the canonically-named one and dead.

Prints model identifiers only. No credential value is printed; each provider
line carries the twelve-hex fingerprint of the key that authenticated.
"""
from __future__ import annotations

import json
import sys

import envroot


def anthropic_models() -> list[str]:
    import anthropic

    key, var, fp = envroot.key_for("anthropic")
    client = anthropic.Anthropic(api_key=key)
    print(f"# anthropic via {var} fp={fp}")
    return [m.id for m in client.models.list(limit=100).data]


def openai_models() -> list[str]:
    import openai

    key, var, fp = envroot.key_for("openai")
    client = openai.OpenAI(api_key=key)
    print(f"# openai via {var} fp={fp}")
    return [m.id for m in client.models.list().data]


def google_models() -> list[str]:
    from google import genai

    key, var, fp = envroot.key_for("google")
    client = genai.Client(api_key=key)
    print(f"# google via {var} fp={fp}")
    out = []
    for m in client.models.list():
        actions = getattr(m, "supported_actions", None) or []
        if not actions or "generateContent" in actions:
            out.append(m.name)
    return out


def xai_models() -> list[str]:
    from xai_sdk import Client

    key, var, fp = envroot.key_for("xai")
    client = Client(api_key=key)
    print(f"# xai via {var} fp={fp}")
    return [m.name for m in client.models.list_language_models()]


PROBES = {
    "anthropic": anthropic_models,
    "openai": openai_models,
    "google": google_models,
    "xai": xai_models,
}


def main() -> int:
    want = [a for a in sys.argv[1:] if not a.startswith("-")]
    targets = want or list(PROBES)
    out = {}
    for name in targets:
        try:
            out[name] = sorted(PROBES[name]())
        except SystemExit:
            raise
        except Exception as exc:  # noqa: BLE001 - a failed probe is a result
            out[name] = {"error": f"{type(exc).__name__}: {exc}"}
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
