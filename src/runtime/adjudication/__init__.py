"""The adjudication package. Import-free on purpose.

T176 lives beside this marker. Re-exporting it here would add a second
name for the same modules and give a success-path importer one more
spelling to reach for. `tests/invariants/test_import_graph.py` already
reserves the recording side; an empty package root keeps this package a
directory, not a convenience API. Adjudication is measurement — it is
not imported from `result.py`, `loop.py`, or `serving.py`.
"""
