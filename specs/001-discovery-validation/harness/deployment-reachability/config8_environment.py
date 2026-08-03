"""Configuration 8 — an eighth configuration, added AFTER results were visible.

This is recorded as post-hoc and is **not** part of the pre-registered gate. It exists
because the mechanism ablation exposed a hole in R1: mechanism M5 was written to handle
the target's optional-dependency guard

    def _register_builder_endpoints(app, web, agents_dir):
      if not web: return
      try:
        import multipart
      except ImportError:
        return                      # <- three routes silently do not register

and the ablation showed M5 makes no difference to the result, because the guard is
expressed as an early return inside an `except` handler that the propagator never
executes. So R1 predicts those three routes served whenever `web` is true, regardless
of whether `python-multipart` is installed.

That is not a configuration flag. It is a property of the deployed environment, and no
declared configuration contains it. This script constructs the same `web` configuration
with `multipart` made unimportable and measures what the application then serves, so
the size of R1's error is a number rather than a worry.

No model is called.
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
import warnings

warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


class _Blocker:
    """A meta-path finder that makes a named top-level package unimportable."""

    def __init__(self, blocked):
        self.blocked = blocked

    def find_module(self, fullname, path=None):  # legacy API, harmless
        return None

    def find_spec(self, fullname, path=None, target=None):
        if fullname == self.blocked or fullname.startswith(self.blocked + "."):
            raise ImportError(f"blocked for measurement: {fullname}")
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--block", default="multipart")
    args = ap.parse_args()

    os.environ.setdefault("ADK_DISABLE_TELEMETRY", "1")

    for name in list(sys.modules):
        if name == args.block or name.startswith(args.block + "."):
            del sys.modules[name]
    sys.meta_path.insert(0, _Blocker(args.block))

    try:
        importlib.import_module(args.block)
        blocked_ok = False
    except ImportError:
        blocked_ok = True

    import build_served_key as bsk

    app = bsk.build_via_get_fast_api_app("web_no_multipart", web=True)
    routes = bsk.enumerate_routes(app)
    openapi, err = bsk.enumerate_openapi(app)

    result = {
        "web_no_multipart": {
            "ok": True,
            "post_hoc": True,
            "blocked_package": args.block,
            "block_effective": blocked_ok,
            "entry_point": "fast_api.get_fast_api_app",
            # The declared configuration is identical to `web`. That is the point:
            # nothing an operator declares distinguishes this deployment from `web`.
            "declared_config": {"web": True},
            "routes": [list(t) for t in routes],
            "openapi": [list(t) for t in (openapi or [])],
            "openapi_error": err,
        }
    }
    with open(args.out, "w") as fh:
        json.dump(result, fh, indent=2, sort_keys=True, default=str)
    print(
        f"block_effective={blocked_ok} served={len(routes)} "
        f"openapi={len(openapi or [])}",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
