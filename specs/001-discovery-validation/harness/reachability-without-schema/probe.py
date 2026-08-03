#!/usr/bin/env python3
"""E15 probe — schema-state classification and two path-level reachability arms.

Runs against any of the six targets: three FastAPI configurations built from the read-only
vendored `adk-python` copy, and three hand-written fixtures.

Three things are measured per target.

**1. Schema state, four-way** (`PRESENT` / `ABSENT` / `FORBIDDEN` / `EMPTY`). The fourth is the
one `plan.md` does not name and the dangerous one: a 200 carrying a syntactically valid schema
with no operations in it. A pipeline that splits on 2xx-versus-not reads `EMPTY` as `PRESENT`
and emits a catalogue of zero operations while reporting success.

**2. Two path-level probe arms**, differing only in how the probe verb is chosen.

  `P-e14`     the verb rule finding 010 shipped: the first verb *this operation* does not
              declare. A literal path whose parameterised sibling declares that verb is
              therefore absorbed by the sibling, **and the sibling's handler runs.**
  `P-global`  a verb *no route in the application declares*. Default `F2APROBE`. A path match
              with an undeclared method is a partial match in every router that separates path
              matching from method matching, so no handler can be reached.

**3. Handler invocations, counted from the server's own stdout** rather than inferred. The
fixtures print a line when a handler body executes. This is the measurement finding 010 could
not make, because the vendored target's handlers are not instrumented and FR-018 forbids
instrumenting them. For the FastAPI targets, handler invocation is instead *estimated* by
response-body discrimination against the router's own 404 body, and every number produced that
way is labelled `body-discriminated` rather than `counted`.

Usage:
  probe.py --targets web,web_no_schema,web_schema_401 --served-key ... --static-set ... --out ...
  probe.py --targets starlette,flask,django --fixture-sets ... --out ...
"""

import argparse
import json
import os
import re
import socket
import subprocess
import sys
import time

import httpx

HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURES = os.path.join(HERE, "fixtures")

GLOBAL_UNUSED_VERB = "F2APROBE"
E14_VERB_ORDER = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
SENTINEL = "f2a-probe"

# Two detectors for "application code executed", in descending order of strength.
#
#   PROVABLE      Under a probe using a method the operation does not declare, a router can
#                 only answer 404 (no path matched) or 405 (path matched, method did not).
#                 **Any other status is proof that a handler ran.** Framework-independent,
#                 no calibration, no heuristic.
#   CALIBRATED    A handler can also answer 404 itself, which the status alone cannot
#                 distinguish from an unrouted 404. So each target is first asked for a path
#                 that certainly does not exist, and that response body is recorded as the
#                 router's own 404 signature. A 404 whose body differs from it is
#                 handler-generated. This is a heuristic, and it is validated against the
#                 three fixtures where handler invocation is counted from the server's log.
ROUTER_ONLY_STATUSES = {404, 405}

# Bodies are compared as equal-length prefixes. Capturing the signature and the probe response
# at different lengths made every long HTML 404 body look handler-generated, which produced four
# false detections on Flask before it was caught by cross-checking against the counted log.
BODY_CAPTURE = 400


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def concretise(path):
    """`/a/{x}/b/{y:path}` -> `/a/f2a-probe/b/f2a-probe`."""
    return re.sub(r"\{[^}]*\}", SENTINEL, path)


def normalise(p):
    p = p.replace("<", "{").replace(">", "}")
    for conv in ("string:", "str:", "int:", "path:", "slug:", "uuid:"):
        p = p.replace("{" + conv, "{")
    return re.sub(r"\{([^}:]+):[^}]*\}", r"{\1}", p)


# --------------------------------------------------------------------------- server launching
FIXTURE_CMD = {
    "starlette": ["uvicorn", "app_starlette:app"],
    "flask": ["uvicorn", "--interface", "wsgi", "app_flask:app"],
    "django": ["uvicorn", "--interface", "wsgi", "app_django:app"],
}


def start_fixture(fw, port, venv_bin):
    cmd = [os.path.join(venv_bin, FIXTURE_CMD[fw][0])] + FIXTURE_CMD[fw][1:] + [
        "--port", str(port), "--log-level", "warning",
    ]
    return subprocess.Popen(cmd, cwd=FIXTURES, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True,
                            env={**os.environ, "PYTHONUNBUFFERED": "1"})


def start_fastapi(cfg, port, venv_bin):
    cmd = [os.path.join(venv_bin, "python"), os.path.join(HERE, "serve_fastapi.py"),
           "--config", cfg, "--port", str(port)]
    return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, env={**os.environ, "PYTHONUNBUFFERED": "1"})


def wait_up(base, timeout=180.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            httpx.get(base + "/f2a-warmup-probe", timeout=2.0)
            return True
        except Exception:
            time.sleep(0.25)
    return False


# ------------------------------------------------------------------ 1. schema state, four-way
def classify_schema(client, base):
    """Four-way classification, plus the two-way reading a naive pipeline would use."""
    out = {"url": base + "/openapi.json"}
    try:
        r = client.get(out["url"])
    except Exception as exc:
        out["state"] = "UNREACHABLE"
        out["error"] = f"{type(exc).__name__}: {exc}"
        out["naive_2xx_reading"] = "not-present"
        return out
    out["status"] = r.status_code
    out["body_prefix"] = r.text[:BODY_CAPTURE]
    if r.status_code in (401, 403):
        out["state"] = "FORBIDDEN"
    elif r.status_code == 404:
        out["state"] = "ABSENT"
    elif 200 <= r.status_code < 300:
        try:
            doc = r.json()
        except Exception:
            out["state"] = "MALFORMED"
            doc = None
        if doc is not None:
            paths = doc.get("paths") or {}
            ops = sum(
                1 for p, item in paths.items() for m in item
                if m.upper() in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}
            )
            out["operation_count"] = ops
            out["state"] = "PRESENT" if ops > 0 else "EMPTY"
            out["operations"] = sorted(
                [m.upper(), normalise(p)]
                for p, item in paths.items() for m in item
                if m.upper() in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}
            )
    else:
        out["state"] = f"OTHER_{r.status_code}"
    # What a pipeline that only checks "did the fetch succeed" would conclude. This is the
    # comparison that makes the EMPTY state's danger a number rather than an argument.
    out["naive_2xx_reading"] = (
        "present" if out.get("status", 0) and 200 <= out["status"] < 300 else "not-present"
    )
    return out


# ------------------------------------------------------------- 2. the two path-level arms
def router_404_signature(client, base):
    """Ask for a path that certainly does not exist and keep the body as the router's own 404."""
    probes = ["/f2a-certainly-absent-" + SENTINEL, "/f2a/certainly/absent"]
    sigs = []
    for p in probes:
        try:
            r = client.request(GLOBAL_UNUSED_VERB, base + p)
            sigs.append({"path": p, "status": r.status_code, "body": r.text[:BODY_CAPTURE]})
        except Exception as exc:
            sigs.append({"path": p, "error": f"{type(exc).__name__}: {exc}"})
    bodies = {s["body"].strip() for s in sigs if s.get("status") == 404}
    return {"probes": sigs, "router_404_bodies": sorted(bodies)}


def path_probe(client, base, paths_to_methods, verb_rule, global_verb, router_404=None):
    """One request per candidate path. Returns per-path routed/status/allow/body."""
    router_bodies = set((router_404 or {}).get("router_404_bodies") or [])
    res = {}
    for path in sorted(paths_to_methods):
        declared = paths_to_methods[path]
        if verb_rule == "global":
            verb = global_verb
        else:
            verb = next((v for v in E14_VERB_ORDER if v not in declared), "OPTIONS")
        rec = {"probe_verb": verb, "url": concretise(path)}
        try:
            r = client.request(verb, base + rec["url"])
            rec["status"] = r.status_code
            rec["allow"] = r.headers.get("allow")
            rec["body"] = r.text[:BODY_CAPTURE]
            rec["routed"] = r.status_code != 404
            # PROVABLE: the router cannot produce anything but 404 or 405 here.
            rec["handler_ran_provable"] = r.status_code not in ROUTER_ONLY_STATUSES
            # CALIBRATED: a 404 whose body is not the router's own 404 body.
            if r.status_code == 404 and router_bodies:
                rec["handler_ran_calibrated"] = (r.text or "").strip() not in router_bodies
            else:
                rec["handler_ran_calibrated"] = False
        except Exception as exc:
            rec["status"] = None
            rec["error"] = f"{type(exc).__name__}: {exc}"
            rec["routed"] = None
        res[path] = rec
    return res


def _one_session(name, kind, venv_bin, body):
    """Start a server, run `body(client, base)`, stop it, and return (result, handler lines).

    **Each arm gets its own server process.** Attribution of a handler invocation to the arm
    that caused it has to be exact, and an in-band marker request cannot provide that: uvicorn
    at `--log-level warning` writes no access lines, so there is nothing in the log to split on.
    A marker *route* would be worse, because it would enter the candidate set. One process per
    arm makes the attribution structural instead of inferred.
    """
    port = free_port()
    base = f"http://127.0.0.1:{port}"
    proc = (start_fixture(name, port, venv_bin) if kind == "fixture"
            else start_fastapi(name, port, venv_bin))
    result, err = None, None
    try:
        if not wait_up(base):
            err = "server never came up"
        else:
            with httpx.Client(timeout=25.0, follow_redirects=False) as c:
                result = body(c, base)
    finally:
        proc.terminate()
        try:
            log = proc.communicate(timeout=20)[0] or ""
        except subprocess.TimeoutExpired:
            proc.kill()
            log = proc.communicate()[0] or ""
    lines = [ln.split("HANDLER-INVOKED", 1)[1].strip()
             for ln in log.splitlines() if "HANDLER-INVOKED" in ln]
    return result, lines, err, log


def run_target(name, kind, candidates_by_path, venv_bin, global_verb, extra_paths=None):
    out = {"target": name, "kind": kind, "global_verb": global_verb, "arms": {},
           "handler_log": {}, "ok": True}

    # Session 1 — schema classification only, so that no handler invocation it causes is
    # attributed to a probe arm.
    def _schema(c, base):
        return {
            "schema": classify_schema(c, base),
            # Two schema-adjacent reads, so "absent" cannot be confused with "app is down".
            "docs_status": _safe_status(c, base + "/docs"),
            "liveness": _safe_status(c, base + "/f2a-liveness-check"),
            "router_404": router_404_signature(c, base),
        }

    res, lines, err, log = _one_session(name, kind, venv_bin, _schema)
    if err:
        out["ok"] = False
        out["error"] = err
        return out, log
    out.update(res)
    out["handler_log"]["schema-classification"] = lines

    # Sessions 2 and 3 — one per probe arm, on a fresh process each time.
    for arm, rule in (("P-e14", "e14"), ("P-global", "global")):
        sig = out.get("router_404")
        res, lines, err, log = _one_session(
            name, kind, venv_bin,
            lambda c, base, _r=rule: path_probe(c, base, candidates_by_path, _r, global_verb,
                                                router_404=sig),
        )
        if err:
            out["ok"] = False
            out["error"] = f"{arm}: {err}"
            return out, log
        out["arms"][arm] = res
        out["handler_log"][arm] = lines

    # Session 4 — the declared adversarial probe, reported outside the gate.
    #
    # A path the *static* reader could not resolve never enters the candidate set and is
    # therefore never probed, which is a real mitigation and is reported as one. But it holds
    # only for a conservative extractor: one that guessed a method list would probe it. So the
    # unsafe case is exercised deliberately here rather than left as an argument.
    if extra_paths:
        def _extra(c, base):
            return path_probe(c, base, {p: set() for p in extra_paths}, "global", global_verb,
                              router_404=out.get("router_404"))

        res, lines, err, log = _one_session(name, kind, venv_bin, _extra)
        out["adversarial_probe"] = {
            "paths": sorted(extra_paths),
            "note": "outside the candidate set; not scored in the gate",
            "result": res,
            "handlers_invoked": lines,
        }
    return out, ""


def _safe_status(c, url):
    try:
        return c.request("GET", url).status_code
    except Exception as exc:
        return f"ERR {type(exc).__name__}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--targets", required=True)
    ap.add_argument("--kind", choices=["fastapi", "fixture"], required=True)
    ap.add_argument("--static-set", help="E14 static-set.json (FastAPI targets)")
    ap.add_argument("--fixture-sets", help="fixture-sets.json (fixture targets)")
    ap.add_argument("--venv-bin", required=True)
    ap.add_argument("--global-verb", default=GLOBAL_UNUSED_VERB)
    ap.add_argument("--extra-paths", default="",
                    help="comma-separated paths probed outside the candidate set, as a "
                         "declared adversarial check; reported, never gated")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    result = {}
    for name in args.targets.split(","):
        if args.kind == "fastapi":
            st = json.load(open(args.static_set))
            pairs = [tuple(p) for p in st["static_set"]]
            pairs += [tuple(p) for p in st["null_set"]["phantoms"]]
            pairs += [tuple(p) for p in st["null_set"]["foreign_apps"]]
        else:
            fs = json.load(open(args.fixture_sets))[name]
            pairs = [tuple(p) for p in fs["static_set"]] + [tuple(p) for p in fs["null_set"]]
        by_path = {}
        for m, p in pairs:
            by_path.setdefault(normalise(p), set()).add(m)

        # The globally-unused verb must actually be unused, or the arm's structural argument
        # does not hold. Verified against the candidate set, and asserted rather than assumed.
        all_declared = {m for ms in by_path.values() for m in ms}
        if args.global_verb in all_declared:
            raise SystemExit(f"--global-verb {args.global_verb} is declared by a candidate "
                             f"operation; the P-global argument would not hold")

        extra = [x for x in args.extra_paths.split(",") if x]
        out, log = run_target(name, args.kind, by_path, args.venv_bin, args.global_verb,
                              extra_paths=extra)
        result[name] = out
        s = out.get("schema", {})
        hl = out.get("handler_log", {})
        adv = out.get("adversarial_probe") or {}
        print(f"{name:18s} schema={s.get('state','9'):9s} (status={s.get('status')}, "
              f"naive={s.get('naive_2xx_reading')})  "
              f"handlers invoked: P-e14={len(hl.get('P-e14', []))} "
              f"P-global={len(hl.get('P-global', []))}"
              + (f"  adversarial={len(adv.get('handlers_invoked', []))}" if adv else ""))
        if not out.get("ok"):
            print(f"   FAILED: {out.get('error')}")
            print(log[-1200:])

    json.dump(result, open(args.out, "w"), indent=2, sort_keys=True, default=str)
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
