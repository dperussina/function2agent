"""Find a working Google/Gemini credential across every dotenv file in a tree.

Never prints a key value. Keys are identified by a short SHA-256 fingerprint so distinct
credentials can be told apart safely. Uses model-list endpoints only: zero tokens, zero cost.

Produces the credential-discovery table in findings/002-provider-credentials.md — the
12-candidate scan whose result was 10x `400`, 1x `401`, and exactly one working key
under a non-canonical name.

Recovered from /tmp/f2a_probe_gemini.py on 2026-08-02. The only change from the
script that produced the finding is that the scan root is now a parameter rather
than a hardcoded path into a private repository — see envroot.py and the README.

Usage:  python3 probe_gemini_discovery.py --env-root PATH
        F2A_ENV_ROOT=PATH python3 probe_gemini_discovery.py
"""
import hashlib
import json
import urllib.error
import urllib.parse
import urllib.request

import envroot

ROOT = envroot.resolve()

# Substring hints, matched case-insensitively against the variable name. The
# finding's whole point is that the canonical name is not reliable, so the scan
# is by shape-and-hint rather than by exact name.
NAME_HINT = (
    "GEMINI",
    "GOOGLE_AI",
    "GENERATIVE",
    "GOOGLE_GENAI",
    "GOOGLE_API_KEY",
    "VERTEX",
)


def fingerprint(value: str) -> str:
    """A stable, non-reversible handle for a credential. Never the credential."""
    return hashlib.sha256(value.encode()).hexdigest()[:10]


def harvest() -> dict[str, list[tuple[str, str]]]:
    """value -> [(relative file, var name), ...]

    Keyed by value so that the same credential appearing under two names in two
    files is counted once, which is how the finding arrives at 12 *distinct*
    values rather than 12 occurrences.
    """
    import os

    candidates: dict[str, list[tuple[str, str]]] = {}
    for path in envroot.find_env_files(ROOT):
        for name, value in envroot.parse(path).items():
            if not value or len(value) < 20:
                continue
            if any(h in name.upper() for h in NAME_HINT):
                candidates.setdefault(value, []).append(
                    (os.path.relpath(path, ROOT), name)
                )
    return candidates


def test_gemini(key: str) -> tuple[int, int, str]:
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models?pageSize=200&key="
        + urllib.parse.quote(key)
    )
    try:
        with urllib.request.urlopen(url, timeout=25) as resp:
            body = json.loads(resp.read().decode())
            return resp.status, len(body.get("models", [])), ""
    except urllib.error.HTTPError as exc:
        try:
            msg = json.loads(exc.read().decode())["error"]["message"][:70]
        except Exception:  # noqa: BLE001
            msg = f"HTTP {exc.code}"
        return exc.code, 0, msg
    except Exception as exc:  # noqa: BLE001
        return 0, 0, f"{type(exc).__name__}"[:70]


cands = harvest()
print(f"scan root: {ROOT}")
print(f"scanned dotenv files, found {len(cands)} distinct Google/Gemini-shaped credential values\n")
print(f"{'FINGERPRINT':<12} {'HTTP':<6} {'MODELS':<7} SOURCE(S) / ERROR")
print("-" * 104)

working: list[tuple[str, list[tuple[str, str]], int]] = []
for value, sources in cands.items():
    fp = fingerprint(value)
    status, count, err = test_gemini(value)
    src = "; ".join(f"{f}:{n}" for f, n in sources[:2])
    if len(sources) > 2:
        src += f" (+{len(sources) - 2} more)"
    tag = "OK" if status == 200 else "fail"
    detail = src if status == 200 else f"{err}  <- {src}"
    print(f"{fp:<12} {status:<6} {count:<7} [{tag}] {detail[:78]}")
    if status == 200:
        working.append((fp, sources, count))

if working:
    fp, sources, count = max(working, key=lambda w: w[2])
    print(f"\nWORKING Gemini credential: fingerprint {fp}, {count} models")
    print("  found in:")
    for f, n in sources:
        print(f"    {f}  ->  {n}")
    key = next(v for v in cands if fingerprint(v) == fp)
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models?pageSize=200&key="
        + urllib.parse.quote(key)
    )
    with urllib.request.urlopen(url, timeout=25) as resp:
        models = json.loads(resp.read().decode()).get("models", [])
    names = sorted(m["name"].replace("models/", "") for m in models)
    gen = [n for n in names if "gemini" in n]
    print(f"\n  {len(gen)} Gemini generation models reachable; newest-looking:")
    for n in [x for x in gen if "2.5" in x or "3" in x or "flash-latest" in x][:12]:
        print(f"    {n}")
else:
    print("\nNo working Google/Gemini credential found in any dotenv file.")
