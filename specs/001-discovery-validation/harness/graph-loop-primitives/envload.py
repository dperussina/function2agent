"""Credential loading for the two E6 arms that call a model.

Twelve of E6's fourteen arms use pure Python function nodes and need no
credential at all. Only `e6_p3b_budget.py` and `e6_p3c_budget_resume.py` call a
model, because whether `max_llm_calls` actually halts a run is the one question
that cannot be answered without one.

Rather than keep a second copy, this delegates to the E5 harness's loader, which
is the same module the original probes imported — both experiments shared one
virtualenv and one `envload.py`.

See ../runtime-provider-agnosticism/envload.py for the credential-handling rules.
No value is printed, logged, or written anywhere.
"""
import importlib.util
import os
import sys

_SIBLING = os.path.normpath(
    os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "..",
        "runtime-provider-agnosticism",
        "envload.py",
    )
)

if not os.path.exists(_SIBLING):
    sys.exit(
        f"Expected the E5 credential loader at {_SIBLING} and it is not there.\n"
        "  The two harnesses shared one loader; graph-loop-primitives does not\n"
        "  keep its own copy."
    )

_spec = importlib.util.spec_from_file_location("_f2a_envload", _SIBLING)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

load = _mod.load
workdir = _mod.workdir
