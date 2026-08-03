"""Score statically derived contracts against the framework's own OpenAPI schema.

Three outcomes are kept distinct for each contract component, because a derived
contract that disagrees with the framework is worse than no contract at all:

  agreement    the derived component matches what the framework publishes
  disagreement the derived component exists and differs
  absence      no component could be derived

Exceptions are reported without an accuracy score, because OpenAPI declares no
exception information. That absence is itself a result.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict

# OpenAPI strips a Starlette path converter suffix (`{name:path}` -> `{name}`).
CONVERTER = re.compile(r"\{([^}:]+):[^}]+\}")


def norm_op(op):
    return CONVERTER.sub(r"{\1}", op)


def name_loc(inputs):
    return {(i["name"], i["location"]) for i in inputs}


def full_tuple(inputs):
    return {(i["name"], i["location"], bool(i["required"]), i["type"]) for i in inputs}


PRIMITIVE_JSON = {
    "bool": "boolean",
    "str": "string",
    "int": "integer",
    "float": "number",
    "bytes": "string",
}

# Starlette response classes. A handler annotated with one of these declares how
# the bytes are framed, not what shape they carry, so no data contract exists to
# derive and none is published either.
RESPONSE_OBJECTS = {
    "Response",
    "StreamingResponse",
    "FileResponse",
    "JSONResponse",
    "PlainTextResponse",
    "HTMLResponse",
    "RedirectResponse",
    "ORJSONResponse",
    "UJSONResponse",
}

# `Any`, `None`, and an unannotated handler all leave FastAPI publishing an
# empty schema, which our key builder tokenises as "unknown".
UNTYPED = {"Any", "None", "NoneType", "object"}


def split_union(text):
    t = text.strip()
    m = re.match(r"^Optional\[(.+)\]$", t)
    if m:
        return [p.strip() for p in m.group(1).split("|")] + ["None"]
    return [p.strip() for p in t.split("|")]


def derived_json_token(text):
    """Reduce a derived return annotation to the same token vocabulary the key
    builder produces from the OpenAPI schema."""
    parts = []
    for p in split_union(text):
        head = p.split("[")[0].split(".")[-1].strip()
        if head in ("None", "NoneType"):
            continue
        if head in ("list", "List", "Sequence"):
            inner = re.match(r"^[\w.]+\[(.+)\]$", p)
            inner_head = (
                inner.group(1).split("[")[0].split(".")[-1].strip()
                if inner
                else "Any"
            )
            parts.append(
                f"array[{PRIMITIVE_JSON.get(inner_head, 'object')}]"
            )
        elif head in ("dict", "Dict", "Mapping"):
            parts.append("object")
        elif head in PRIMITIVE_JSON:
            parts.append(PRIMITIVE_JSON[head])
        elif head in UNTYPED:
            parts.append("unknown")
        else:
            parts.append("object")
    parts = sorted(set(parts))
    if not parts:
        return "unknown"
    if len(parts) == 1:
        return parts[0]
    return "union[" + "|".join(parts) + "]"


# What FastAPI publishes as the response schema when a route declares only a
# response_class. Anything not listed leaves the schema empty.
RESPONSE_CLASS_TOKEN = {
    "PlainTextResponse": "str",
    "HTMLResponse": "str",
    "FileResponse": "str",
}


def derived_return_token(c):
    """The derived return type, preferring the decorator's `response_model`
    because that is what FastAPI itself uses to build the published schema."""
    rm = c.get("response_model")
    ann = c.get("return_annotation")
    chosen = rm or ann
    if not chosen:
        rc = c.get("response_class")
        mapped = RESPONSE_CLASS_TOKEN.get(rc) if rc else None
        if mapped:
            return mapped, mapped
        if rc:
            return rc, rc
        return None, None
    head = chosen.split("[")[0].split(".")[-1].strip()
    head = re.sub(r"^Optional\[", "", head)
    return chosen, head


def key_return_token(k):
    r = k.get("response")
    if not r or not r.get("has_schema"):
        return None, None
    title = r.get("title")
    # FastAPI synthesises `Response <operation name>` when no response_model
    # names a single model; that is not a model name to match against.
    if title and title.startswith("Response "):
        title = None
    return title, r.get("type")


def per_op_ok(d, k, verdict):
    """Both components derived and both agreeing with the framework."""
    return name_loc(d["inputs"]) == name_loc(k["inputs"]) and verdict in (
        "agree_named_model",
        "agree_shape",
        "declared_no_payload",
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--derived", required=True)
    ap.add_argument("--key", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    derived = json.load(open(args.derived))["contracts"]
    key = json.load(open(args.key))["operations"]

    dmap = {norm_op(k): v for k, v in derived.items()}
    kmap = {norm_op(k): v for k, v in key.items()}
    ops = sorted(set(dmap) & set(kmap))

    result = {
        "n_endpoints_scored": len(ops),
        "n_derived": len(dmap),
        "n_key": len(kmap),
        "only_in_derived": sorted(set(dmap) - set(kmap)),
        "only_in_key": sorted(set(kmap) - set(dmap)),
    }

    # ---------------- parameters ----------------
    param = Counter()
    param_detail = []
    for op in ops:
        d, k = dmap[op], kmap[op]
        dn, kn = name_loc(d["inputs"]), name_loc(k["inputs"])
        df, kf = full_tuple(d["inputs"]), full_tuple(k["inputs"])
        if not d["inputs"] and not k["inputs"]:
            param["agree_empty"] += 1
            continue
        if not d["inputs"] and k["inputs"]:
            param["absent"] += 1
            param_detail.append(
                {"op": op, "verdict": "absent", "expected": sorted(kn)}
            )
            continue
        if dn == kn:
            param["agree_names"] += 1
            if df == kf:
                param["agree_full"] += 1
            else:
                param_detail.append(
                    {
                        "op": op,
                        "verdict": "names agree, type/required differ",
                        "derived_only": sorted(df - kf),
                        "expected_only": sorted(kf - df),
                    }
                )
        else:
            param["disagree"] += 1
            param_detail.append(
                {
                    "op": op,
                    "verdict": "disagree",
                    "derived_only": sorted(dn - kn),
                    "expected_only": sorted(kn - dn),
                }
            )
    result["parameters"] = {
        "counts": dict(param),
        "agreement": param["agree_names"] + param["agree_empty"],
        "disagreement": param["disagree"],
        "absence": param["absent"],
        "exact_including_type_and_required": param["agree_full"]
        + param["agree_empty"],
        "detail": param_detail,
    }

    # ---------------- return type ----------------
    ret = Counter()
    ret_detail = []
    ret_verdict = {}
    for op in ops:
        d, k = dmap[op], kmap[op]
        dtxt, dhead = derived_return_token(d)
        ktitle, ktype = key_return_token(k)
        key_silent = ktype in (None, "unknown")

        if dtxt is None:
            if key_silent:
                # Neither the source nor the framework declares anything. No
                # verifier can be built from either side.
                verdict = "neither_declares"
            else:
                verdict = "absent"
                ret_detail.append(
                    {
                        "op": op,
                        "verdict": "absent",
                        "expected": ktitle or ktype,
                        "handler": d["handler"],
                    }
                )
            ret[verdict] += 1
            ret_verdict[op] = verdict
            continue

        if dhead in RESPONSE_OBJECTS:
            verdict = "response_object"
            ret[verdict] += 1
            ret_verdict[op] = verdict
            continue

        dtoken = derived_json_token(dtxt)
        if key_silent:
            if dtoken == "unknown":
                # The source says `-> None` or `-> Any` and the framework
                # publishes an empty schema. Both agree there is no shape, so
                # there is nothing for a verifier to check.
                verdict = (
                    "declared_no_payload"
                    if dtxt.strip() in ("None", "NoneType")
                    else "declared_untyped"
                )
            else:
                verdict = "derived_typed_key_silent"
                ret_detail.append(
                    {
                        "op": op,
                        "verdict": verdict,
                        "derived": dtxt,
                        "handler": d["handler"],
                    }
                )
        elif ktitle and dhead == ktitle:
            verdict = "agree_named_model"
        elif dtoken == ktype:
            verdict = "agree_shape"
        else:
            verdict = "disagree"
            ret_detail.append(
                {
                    "op": op,
                    "verdict": "disagree",
                    "derived": dtxt,
                    "derived_token": dtoken,
                    "expected_title": ktitle,
                    "expected_type": ktype,
                    "handler": d["handler"],
                }
            )
        ret[verdict] += 1
        ret_verdict[op] = verdict

    agree = (
        ret["agree_named_model"]
        + ret["agree_shape"]
        + ret["declared_no_payload"]
    )
    result["return_type"] = {
        "counts": dict(ret),
        "agreement": agree,
        "agreement_note": (
            "declared_no_payload counts as agreement: the handler is annotated "
            "`-> None` and the framework publishes no response schema, which "
            "is a checkable statement that the endpoint returns no body"
        ),
        "disagreement": ret["disagree"] + ret["derived_typed_key_silent"],
        "absence": ret["absent"],
        "no_shape_on_either_side": (
            ret["neither_declares"]
            + ret["declared_untyped"]
            + ret["response_object"]
        ),
        "detail": ret_detail,
    }

    # annotation vs response_model conflicts
    conflicts = []
    both = 0
    for op in ops:
        d = dmap[op]
        rm, ann = d.get("response_model"), d.get("return_annotation")
        if rm and ann:
            both += 1
            if rm.split("[")[0].split(".")[-1] != ann.split("[")[0].split(".")[-1]:
                conflicts.append(
                    {"op": op, "response_model": rm, "annotation": ann}
                )
    result["return_source_conflict"] = {
        "endpoints_declaring_both": both,
        "conflicts": conflicts,
    }

    # ---------------- exceptions ----------------
    exc_classes = Counter()
    one_hop_classes = Counter()
    with_raise_depth1 = 0
    with_raise = 0
    http_with_status = 0
    http_total = 0
    status_seen = Counter()
    undeclared = []
    for op in ops:
        d, k = dmap[op], kmap[op]
        rs = d["raises"]
        hop = d.get("raises_one_hop", [])
        for r in hop:
            one_hop_classes[r["class"]] += 1
        if rs or hop:
            with_raise_depth1 += 1
        if rs:
            with_raise += 1
        for r in rs:
            exc_classes[r["class"]] += 1
            if r["class"] == "HTTPException":
                http_total += 1
                if r["status_code"] is not None:
                    http_with_status += 1
                    status_seen[r["status_code"]] += 1
        derived_codes = {
            str(r["status_code"]) for r in rs if r["status_code"] is not None
        }
        missing = sorted(derived_codes - set(k["declared_status_codes"]))
        if missing:
            undeclared.append({"op": op, "raised_but_undeclared": missing})
    result["exceptions"] = {
        "endpoints_with_at_least_one_raise": with_raise,
        "endpoints_with_no_raise": len(ops) - with_raise,
        "raise_sites": sum(exc_classes.values()),
        "by_class": dict(exc_classes.most_common()),
        "http_exception_sites": http_total,
        "http_exception_sites_with_literal_status": http_with_status,
        "status_codes_seen": {str(k_): v for k_, v in sorted(status_seen.items())},
        "endpoints_raising_a_status_openapi_does_not_declare": len(undeclared),
        "endpoints_with_a_raise_within_one_call_hop": with_raise_depth1,
        "one_hop_raise_classes": dict(one_hop_classes.most_common(12)),
        "undeclared_detail": undeclared,
    }

    # ---------------- the gate ----------------
    produced_both = 0
    validated_both = 0
    all_three = 0
    per_op = {}
    for op in ops:
        d, k = dmap[op], kmap[op]
        dn, kn = name_loc(d["inputs"]), name_loc(k["inputs"])
        p_ok = dn == kn
        dtxt, _ = derived_return_token(d)
        has_params = bool(d["inputs"]) or not k["inputs"]
        has_ret = dtxt is not None
        r_ok = ret_verdict.get(op) in (
            "agree_named_model",
            "agree_shape",
            "declared_no_payload",
        )
        if has_params and has_ret:
            produced_both += 1
        if p_ok and r_ok:
            validated_both += 1
            if d["raises"]:
                all_three += 1
        per_op[op] = {
            "handler": d["handler"],
            "params_ok": p_ok,
            "return_present": has_ret,
            "return_verdict": ret_verdict.get(op),
            "raises": len(d["raises"]),
        }
    # How many endpoints have a response contract on either side at all? The
    # rest cannot be scored for return type by anyone, and saying so is more
    # useful than counting them as failures or quietly dropping them.
    scoreable_return = [
        op
        for op in ops
        if ret_verdict.get(op)
        not in ("neither_declares", "declared_untyped", "response_object")
    ]
    validated_scoreable = sum(
        1
        for op in scoreable_return
        if per_op_ok(dmap[op], kmap[op], ret_verdict.get(op))
    )

    n = len(ops)
    result["return_contract_exists_somewhere"] = {
        "n": len(scoreable_return),
        "validated": validated_scoreable,
        "rate": round(validated_scoreable / len(scoreable_return), 4)
        if scoreable_return
        else 0.0,
    }
    result["gate"] = {
        "threshold": 0.80,
        "n": n,
        "produced_parameters_and_return_type": produced_both,
        "produced_rate": round(produced_both / n, 4) if n else 0.0,
        "validated_parameters_and_return_type": validated_both,
        "validated_rate": round(validated_both / n, 4) if n else 0.0,
        "all_three_components_including_raises": all_three,
        "all_three_rate": round(all_three / n, 4) if n else 0.0,
    }
    result["per_endpoint"] = per_op

    json.dump(result, open(args.out, "w"), indent=2, sort_keys=True)

    g = result["gate"]
    p = result["parameters"]
    r = result["return_type"]
    e = result["exceptions"]
    print(f"endpoints scored: {n}")
    print(
        f"parameters  agree={p['agreement']}  disagree={p['disagreement']}  "
        f"absent={p['absence']}  (exact incl. type+required="
        f"{p['exact_including_type_and_required']})"
    )
    print(
        f"return type agree={r['agreement']}  disagree={r['disagreement']}  "
        f"absent={r['absence']}  no-shape-either-side="
        f"{r['no_shape_on_either_side']}   {r['counts']}"
    )
    print(
        f"exceptions  {e['endpoints_with_at_least_one_raise']}/{n} endpoints "
        f"have a raise site; {e['http_exception_sites_with_literal_status']}"
        f"/{e['http_exception_sites']} HTTPException sites carry a literal "
        f"status code"
    )
    print(
        f"GATE (>=0.80): produced both = {g['produced_parameters_and_return_type']}"
        f"/{n} = {g['produced_rate']:.4f}   "
        f"validated both = {g['validated_parameters_and_return_type']}/{n} = "
        f"{g['validated_rate']:.4f}"
    )
    sc = result["return_contract_exists_somewhere"]
    print(
        f"       restricted to the {sc['n']} endpoints where a return contract "
        f"exists on either side: {sc['validated']}/{sc['n']} = {sc['rate']:.4f}"
    )


if __name__ == "__main__":
    main()
