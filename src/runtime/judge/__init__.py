"""The shadow judge package. Import-free on purpose.

T173 and T174 live beside this marker. Re-exporting them here would add a
second name for the same modules and give a success-path importer one more
spelling to reach for. `tests/invariants/test_import_graph.py` already
reserves `src.runtime.judge`; an empty package root keeps that reservation
a directory, not a convenience API.
"""
