"""The drift scheduler's package root.

Empty by design at this phase. It exists because **OD-12 routes the drift
scheduler through the same enforcement point as the agent**, which puts it
inside INV-003's scope the moment the first module lands. Declaring the root
now means INV-003's scan asserts a path that exists rather than passing
silently over an absent one — see `tests/invariants/test_sandbox_reachability.py`.
"""
