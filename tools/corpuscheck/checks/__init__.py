"""Importing this package registers every check.

Adding a check: drop a module in here, decorate the entry point with
`@check(name, summary)`, and add it to the import list below. Nothing else in
the tool needs to change.
"""

from . import (  # noqa: F401
    catalog,
    count_vs_range,
    crossrefs,
    definition_counts,
    dry_run_verdict,
    findings_numbering,
    identifiers,
    inventory,
    lifecycle_taxonomy,
    numeric_provenance,
    preserved_evidence,
    ratio_arithmetic,
    register_ranges,
    sum_arithmetic,
    tables,
    toc,
)
