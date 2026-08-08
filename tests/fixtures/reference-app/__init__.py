"""T116 — the reference application (FR-053).

The directory name carries a hyphen, so this package marker is never imported
as `tests.fixtures.reference-app`. It is here so the directory is a package for
tools that walk one, and so a reader who opens the folder first finds a pointer
rather than three JSON files.

Load the modules by putting this directory on `sys.path`:

    import sys; sys.path.insert(0, "tests/fixtures/reference-app")
    import app, seed, size

`tests/unit/test_reference_app.py` does exactly that and is the worked example.
"""
