"""SPIKE - E16 provider-SDK opaque-state round-trip. Do not import from product code.

Resolve provider credentials without hardcoding a path to any of them.

Same convention as `../ceiling-test/envroot.py` and
`../provider-credentials/envroot.py`: the operator names the tree, and the
harness exits rather than guessing. There is no default.

Resolution order for the search root:

  1. ``--env-root PATH`` on the command line
  2. the ``F2A_ENV_ROOT`` environment variable

The root is only consulted for a variable that is not already in the process
environment, so

    ANTHROPIC_API_KEY=... python3 arm_anthropic.py

needs no root at all.

Nothing here prints, logs, returns to a log, or writes a credential *value*.
Where a run must identify which credential it used, it uses
``fingerprint()`` — a truncated SHA-256 over the value — exactly as
`../provider-credentials/` does, so a result artifact can say *which* key
authenticated without containing it (FR-020).

``F2A_GEMINI_VAR`` exists because finding 002 measured the canonically-named
``GEMINI_API_KEY`` as one of ten dead credentials while the working one lived
under a different name in a different file. A generated stack cannot assume
canonical credential names, and neither does this harness.
"""
from __future__ import annotations

import hashlib
import os
import sys

SKIP_DIRS = {
    "node_modules",
    ".git",
    "dist",
    "build",
    "shared-output",
    ".venv",
    "__pycache__",
}

USAGE = (
    "No dotenv search root given, and {var} is not set in the environment.\n"
    "  Either export {var} directly, or name a tree to search:\n"
    "    export F2A_ENV_ROOT=/path/to/tree      # or pass --env-root PATH\n"
    "  The tree is read for files whose name starts with '.env' and is never\n"
    "  written to. No credential value is printed by anything in this harness."
)


def resolve_root(argv: list[str] | None = None) -> str | None:
    """The dotenv search root, or None if the operator named none."""
    argv = list(sys.argv[1:] if argv is None else argv)
    root = None
    if "--env-root" in argv:
        i = argv.index("--env-root")
        if i + 1 < len(argv):
            root = argv[i + 1]
    root = root or os.environ.get("F2A_ENV_ROOT")
    if not root:
        return None
    root = os.path.abspath(os.path.expanduser(root))
    if not os.path.isdir(root):
        sys.exit(f"Dotenv search root is not a directory: {root}")
    return root


def find_env_files(root: str) -> list[str]:
    """Top-level dotenv files first, then the rest of the tree.

    Ordering matters: the first value found for a name wins, so a root-level
    .env takes precedence over one nested in a subproject.
    """
    top: list[str] = []
    nested: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            if fn.startswith(".env"):
                (top if dirpath == root else nested).append(os.path.join(dirpath, fn))
    return sorted(top) + sorted(nested)


def parse(path: str) -> dict[str, str]:
    """Parse KEY=VALUE lines without executing anything.

    Deliberately not a dotenv library: no interpolation, no command
    substitution, no shell. A malformed or hostile dotenv file cannot do
    anything here but produce a dictionary.
    """
    out: dict[str, str] = {}
    try:
        with open(path, encoding="utf-8", errors="ignore") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                name, _, value = line.partition("=")
                out[name.strip()] = value.strip().strip('"').strip("'")
    except OSError:
        pass
    return out


def load_key(var_name: str, argv: list[str] | None = None) -> str:
    """Return one credential: the environment first, then a tree you name."""
    if os.environ.get(var_name):
        return os.environ[var_name]

    root = resolve_root(argv)
    if root is None:
        sys.exit(USAGE.format(var=var_name))

    for path in find_env_files(root):
        value = parse(path).get(var_name)
        if value:
            return value

    sys.exit(
        f"{var_name} was not found in any .env file under {root}.\n"
        f"  Export {var_name} directly, or point F2A_ENV_ROOT at a tree that\n"
        f"  defines it. The value is never printed."
    )


def fingerprint(value: str) -> str:
    """A stable handle for a credential that is not the credential.

    Twelve hex characters of SHA-256. Enough to tell two keys apart in a
    result artifact; not enough to be one.
    """
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


# The variable each provider's key is read from. Google is indirected through
# F2A_GEMINI_VAR for the reason in this module's docstring.
def gemini_var() -> str:
    return os.environ.get("F2A_GEMINI_VAR", "GEMINI_API_KEY")


PROVIDER_VARS = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "google": None,  # resolved via gemini_var() at call time
    "xai": "XAI_API_KEY",
}


def key_for(provider: str, argv: list[str] | None = None) -> tuple[str, str, str]:
    """(value, variable_name, fingerprint) for one provider."""
    var = PROVIDER_VARS[provider] or gemini_var()
    value = load_key(var, argv)
    return value, var, fingerprint(value)
