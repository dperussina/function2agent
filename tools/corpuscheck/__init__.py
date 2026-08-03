"""corpuscheck — mechanical consistency checks over the function2agent corpus.

Entry point is `tools/check_corpus.py`. See `tools/README.md`.
"""

__all__ = ["run_checks"]

from .runner import run_checks
