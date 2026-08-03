"""Load provider credentials from a dotenv tree, in-process only.

Never prints, logs, or writes a credential value. Values are assigned directly to
os.environ and are only ever referred to by variable name. Read-only against the
tree being scanned.

The original probe hardcoded a path into a private repository and a hardcoded
mapping of variable name to dotenv file. Both are parameters here:

  F2A_ENV_ROOT   the directory tree to scan for .env files. Required; no default.
  F2A_GEMINI_VAR the variable name holding the Google credential. Optional.

Why `F2A_GEMINI_VAR` exists at all is finding 002's central result: on the tree
this probe originally ran against, the canonically-named `GEMINI_API_KEY` was one
of ten dead credentials and the working one was called `GEMINI_API_KEY_2`. A
generated stack cannot assume canonical credential names, and neither can this.
"""
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

# Canonical names, in the order each is preferred. The Gemini entry carries a
# fallback because of finding 002 §Credential discovery.
WANTED = ["ANTHROPIC_API_KEY", "OPENAI_API_KEY", "XAI_API_KEY"]
GEMINI_CANDIDATES = ["GEMINI_API_KEY", "GEMINI_API_KEY_2", "GOOGLE_API_KEY"]


def _root():
    root = os.environ.get("F2A_ENV_ROOT")
    if not root:
        sys.exit(
            "F2A_ENV_ROOT is not set.\n"
            "  Set it to a directory tree containing the .env files with your\n"
            "  provider credentials. It is read and never written to, and no key\n"
            "  value is printed by anything in this harness."
        )
    root = os.path.abspath(os.path.expanduser(root))
    if not os.path.isdir(root):
        sys.exit(f"F2A_ENV_ROOT is not a directory: {root}")
    return root


def _env_files(root):
    """Top-level dotenv files first, then the rest of the tree.

    Ordering matters: the first value found for a name wins, so a root-level
    .env takes precedence over one nested in a subproject.
    """
    top, nested = [], []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            if fn.startswith(".env"):
                (top if dirpath == root else nested).append(
                    os.path.join(dirpath, fn)
                )
    return sorted(top) + sorted(nested)


def _parse(path):
    out = {}
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


def load():
    """Populate os.environ with provider keys. Returns the list of names loaded."""
    root = _root()
    seen = {}
    for path in _env_files(root):
        for name, value in _parse(path).items():
            if value and name not in seen:
                seen[name] = value

    gemini_order = GEMINI_CANDIDATES
    override = os.environ.get("F2A_GEMINI_VAR")
    if override:
        gemini_order = [override] + [c for c in GEMINI_CANDIDATES if c != override]

    loaded = []
    for var in WANTED:
        if var in seen:
            os.environ[var] = seen[var]
            loaded.append(var)

    for var in gemini_order:
        if var in seen:
            # ADK and LiteLLM read GEMINI_API_KEY / GOOGLE_API_KEY regardless of
            # what the credential is called in the operator's dotenv file.
            os.environ["GEMINI_API_KEY"] = seen[var]
            os.environ["GOOGLE_API_KEY"] = seen[var]
            loaded.append(f"{var} -> GEMINI_API_KEY, GOOGLE_API_KEY")
            break

    os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "0"

    if not loaded:
        sys.exit(
            f"No provider credentials found under {root}.\n"
            f"  Looked for: {', '.join(WANTED + GEMINI_CANDIDATES)}\n"
            f"  Set F2A_GEMINI_VAR if your Google credential uses another name."
        )
    return loaded


def workdir():
    """Scratch directory for anything a probe needs to write. Never credentials."""
    d = os.environ.get("F2A_PROBE_DIR", "/tmp/f2a-probe-runtime")
    os.makedirs(d, exist_ok=True)
    return d


if __name__ == "__main__":
    # Names only. Printing the list is safe; printing a value never is.
    print("loaded (names only):")
    for n in load():
        print(f"  {n}")
