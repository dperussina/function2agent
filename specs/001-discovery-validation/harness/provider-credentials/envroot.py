"""Resolve the dotenv search root, without ever hardcoding one.

The original probe read a path into a private repository that happens to sit on
the author's laptop. That path is deliberately absent here: the operator names
their own search root, and the probe refuses to guess (FR-020, and constitution
Principle IV's fail-loudly posture).

Resolution order:

  1. ``--env-root PATH`` on the command line
  2. the ``F2A_ENV_ROOT`` environment variable

There is no default. A probe that silently scans the wrong tree is worse than
one that will not start.

Nothing in this module returns, prints, or stores a credential *value*. It
resolves directories and parses ``KEY=VALUE`` lines; callers are responsible for
keeping values in local variables and out of every output stream.
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


def resolve(argv: list[str] | None = None) -> str:
    """Returns the dotenv search root, or exits with an explanation."""
    argv = list(sys.argv[1:] if argv is None else argv)
    root = None
    if "--env-root" in argv:
        i = argv.index("--env-root")
        if i + 1 < len(argv):
            root = argv[i + 1]
    root = root or os.environ.get("F2A_ENV_ROOT")

    if not root:
        sys.exit(
            "No dotenv search root given.\n"
            "  Pass --env-root PATH, or set F2A_ENV_ROOT=PATH.\n"
            "  PATH is a directory tree containing the .env files whose provider\n"
            "  credentials you want probed. The probe reads it and never writes to it."
        )
    root = os.path.abspath(os.path.expanduser(root))
    if not os.path.isdir(root):
        sys.exit(f"Dotenv search root is not a directory: {root}")
    return root


def find_env_files(root: str, recursive: bool = True) -> list[str]:
    """Every file whose name starts with '.env', skipping vendor directories."""
    if not recursive:
        return sorted(
            os.path.join(root, fn)
            for fn in os.listdir(root)
            if fn.startswith(".env") and os.path.isfile(os.path.join(root, fn))
        )
    out: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            if fn.startswith(".env"):
                out.append(os.path.join(dirpath, fn))
    return sorted(out)


def parse(path: str) -> dict[str, str]:
    """Parse KEY=VALUE lines without executing anything.

    Deliberately not a dotenv library: no interpolation, no command substitution,
    no shell. A malformed or hostile dotenv file cannot do anything here but
    produce a dictionary.
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
