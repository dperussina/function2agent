"""The battery-run freeze package. Import-free on purpose.

T185 lives beside this marker. Re-exporting it here would add a second
name for the same module and give a success-path importer one more
spelling to reach for. The freeze is a measurement artifact — it is
not imported from `result.py`, `loop.py`, `serving.py`, or `main.py`.
"""
