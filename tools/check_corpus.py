#!/usr/bin/env python3
"""Run the corpus consistency checks. See tools/README.md.

    python3 tools/check_corpus.py                 # gate a commit
    python3 tools/check_corpus.py --report-only   # informational
    python3 tools/check_corpus.py --list-checks
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from corpuscheck.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
