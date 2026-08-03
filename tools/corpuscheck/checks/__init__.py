"""Importing this package registers every check.

Adding a check: drop a module in here, decorate the entry point with
`@check(name, summary)`, and add it to the import list below. Nothing else in
the tool needs to change.
"""

from . import (  # noqa: F401
    catalog,
    crossrefs,
    dry_run_verdict,
    findings_numbering,
    identifiers,
    inventory,
    numeric_provenance,
    ratio_arithmetic,
    register_ranges,
    sum_arithmetic,
    tables,
    toc,
)
