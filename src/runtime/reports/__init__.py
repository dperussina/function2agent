"""Standing reports a deployment can be asked for without re-running anything.

FR-045's surfaces live here. They read records that were written as the runtime
ran and produce a versioned document; none of them re-executes a session and
none of them is the trace store's reader.
"""
