"""SPIKE - E18. Credential resolution, **imported from E16 rather than copied**.

[`envroot.py`](../../../001-discovery-validation/harness/provider-sdk-roundtrip/envroot.py)
already implements the whole convention — `--env-root` or `F2A_ENV_ROOT`, no
default, a tree searched for files beginning `.env`, `F2A_GEMINI_VAR` for the
one provider whose canonical variable name
[finding 002](../../../001-discovery-validation/findings/002-provider-credentials.md)
measured dead, and a twelve-hex SHA-256 fingerprint so a result artifact can say
*which* key authenticated without containing it (FR-020).

**This module imports that file. It does not copy it**, which is a departure
from what the three existing `envroot.py` copies do — `ceiling-test`,
`provider-credentials` and `provider-sdk-roundtrip` each hold their own, and the
third one's docstring names the first two as the convention it follows. Three
copies of a credential-resolution routine are three places a fix has to land,
and this harness is in a different feature directory from all of them, so a
fourth copy would be the one that drifts. The path below is computed from
`__file__` and contains no absolute path to anybody's filesystem.

**The one file is loaded by path and its directory is never put on `sys.path`,
and that is not tidiness.** The first version of this module did
`sys.path.insert(0, e16_dir)`, and E16's directory holds modules named
`arm_anthropic`, `arm_openai`, `arm_google`, `arm_xai` and `summarize` — the
same five names this harness uses. Any `import arm_openai` after that line
resolved to *E16's* arm, silently, and the failure surfaced only because E16's
module happens not to define a constant this one does. A shadowed import that
resolved to a module with a compatible surface would have run E16's two-hop
scenario and reported it as this experiment's six-turn one.

Nothing here prints, logs, returns to a log, or writes a credential value.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

_ENVROOT = (
    Path(__file__).resolve().parents[3]
    / "001-discovery-validation"
    / "harness"
    / "provider-sdk-roundtrip"
    / "envroot.py"
)
if not _ENVROOT.is_file():  # pragma: no cover - a moved harness is a build error
    raise SystemExit(
        "E16's envroot.py is not where this harness expects it. Credential "
        "resolution is imported from that file rather than copied into this "
        "directory; see this module's docstring."
    )

_spec = importlib.util.spec_from_file_location("e16_envroot", _ENVROOT)
envroot = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(envroot)

fingerprint = envroot.fingerprint
key_for = envroot.key_for
gemini_var = envroot.gemini_var

__all__ = ["fingerprint", "key_for", "gemini_var"]
