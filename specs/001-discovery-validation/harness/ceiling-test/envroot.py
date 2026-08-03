"""SPIKE - E7 ceiling test. Delete after 2026-11-30. Do not import from product code.

Resolve the provider credential without hardcoding a path to it.

Until 2026-08-02 `runner.py` and `negative_control.py` each carried a module
constant naming a dotenv file inside an unrelated private repository on the
author's laptop. That leaked a private filesystem path into this repository and
made the most expensive experiment in the feature unrunnable by anyone else
without editing source. Both are fixed here, using the same convention as
`../provider-credentials/envroot.py`: the operator names the tree, and the
harness exits rather than guessing.

Resolution order for the search root:

  1. ``--env-root PATH`` on the command line
  2. the ``F2A_ENV_ROOT`` environment variable

There is no default. The root is only consulted when the credential is not
already in the process environment, so

    ANTHROPIC_API_KEY=... python3 runner.py --tasks smoke

needs no root at all.

Nothing here returns, prints, or stores a credential *value* anywhere a caller
does not explicitly put it. It resolves directories, parses ``KEY=VALUE`` lines,
and hands one value back; every error message names the variable and the tree
and never the value (FR-020).

This module is deliberately **absent from `runner.harness_fingerprint`**. That
hash covers every file that can change a *result*; which credential
authenticates the run cannot, and folding it in would invalidate committed
fingerprints for a change that touches no measurement.
"""
from __future__ import annotations

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
