"""The drift scheduler's package root.

This marker stays import-free. Modules land beside it so INV-003's directory
scan is total over every file that will ever sit here — see
`tests/invariants/test_sandbox_reachability.py`. It exists because **OD-12
routes the drift scheduler through the same enforcement point as the agent**,
which puts `scheduler.py` inside that scan. Importing the scheduler from this
file would add a second name for the same module and is refused by leaving
the marker empty.
"""
