"""Ground truth for E4: the contract FastAPI itself publishes for every route.

Instantiates the ADK application in each configuration and reads `app.openapi()`
— the schema the framework generates from its own route table and the Pydantic
models bound to it. For each `(method, path)` this records the operation's
inputs (name, location, required, JSON type) and its declared success response
schema.

This is the authority the statically derived contracts are scored against. It is
machine-generated; nothing here is transcribed by hand.

OpenAPI declares no exception information beyond response status codes, so the
exception half of the contract has no authoritative key and is reported
separately in the finding.
"""

from __future__ import annotations

import json
import os
import sys
import warnings

warnings.filterwarnings("ignore")

CONFIGS = {
    "api_server": dict(web=False),
    "web": dict(web=True),
    "web_a2a": dict(web=True, a2a=True),
    "web_triggers": dict(web=True, trigger_sources=["pubsub", "eventarc"]),
    "enterprise": dict(web=False, gemini_enterprise_app_name="probe_app"),
}


def deref(schema, components, depth=0):
    """Resolve a $ref one level, guarding against cycles."""
    if not isinstance(schema, dict) or depth > 8:
        return schema if isinstance(schema, dict) else {}
    ref = schema.get("$ref")
    if not ref:
        return schema
    name = ref.rsplit("/", 1)[-1]
    return deref(components.get(name, {}), components, depth + 1)


def json_type(schema, components, depth=0):
    """A single comparable type token for a property schema."""
    s = deref(schema, components, depth)
    if not isinstance(s, dict):
        return "unknown"
    if "type" in s:
        t = s["type"]
        if t == "array":
            inner = json_type(s.get("items", {}), components, depth + 1)
            return f"array[{inner}]"
        return t
    for key in ("anyOf", "oneOf", "allOf"):
        if key in s:
            parts = [json_type(x, components, depth + 1) for x in s[key]]
            parts = sorted({p for p in parts if p != "null"})
            if len(parts) == 1:
                return parts[0]
            return "union[" + "|".join(parts) + "]"
        if s.get("properties") is not None:
            return "object"
    if s.get("properties") is not None:
        return "object"
    return "unknown"


def body_fields(schema, components):
    """Expand a request-body schema one level into (name, required, type)."""
    s = deref(schema, components)
    # An `Optional[Model]` body is published as `anyOf: [$ref, null]`; unwrap it
    # so the model's fields are visible rather than an opaque body blob.
    if "properties" not in s:
        for key in ("anyOf", "oneOf"):
            branches = [
                deref(b, components)
                for b in s.get(key, [])
                if deref(b, components).get("type") != "null"
            ]
            named = [b for b in branches if b.get("properties") is not None]
            if len(named) == 1:
                s = named[0]
                break
    props = s.get("properties")
    if props is None:
        return None, json_type(schema, components)
    required = set(s.get("required", []))
    out = []
    for name, prop in props.items():
        out.append(
            {
                "name": name,
                "location": "body",
                "required": name in required,
                "type": json_type(prop, components),
            }
        )
    return out, s.get("title", "object")


def extract(spec):
    components = spec.get("components", {}).get("schemas", {})
    ops = {}
    for path, item in spec.get("paths", {}).items():
        for method, op in item.items():
            if method.upper() not in {
                "GET",
                "POST",
                "PUT",
                "PATCH",
                "DELETE",
                "OPTIONS",
                "HEAD",
            }:
                continue
            inputs = []
            for p in op.get("parameters", []) or []:
                inputs.append(
                    {
                        "name": p.get("name"),
                        "location": p.get("in"),
                        "required": bool(p.get("required")),
                        "type": json_type(p.get("schema", {}), components),
                    }
                )
            body_title = None
            rb = op.get("requestBody")
            if rb:
                content = rb.get("content", {})
                media = next(iter(content.values()), {})
                fields, body_title = body_fields(
                    media.get("schema", {}), components
                )
                if fields is None:
                    inputs.append(
                        {
                            "name": "__body__",
                            "location": "body",
                            "required": bool(rb.get("required")),
                            "type": body_title,
                        }
                    )
                else:
                    inputs.extend(fields)

            resp = None
            for code in ("200", "201", "204"):
                r = op.get("responses", {}).get(code)
                if not r:
                    continue
                content = r.get("content", {})
                media = next(iter(content.values()), {})
                sch = media.get("schema")
                if sch is None:
                    resp = {"code": code, "has_schema": False, "type": None,
                            "title": None}
                else:
                    d = deref(sch, components)
                    resp = {
                        "code": code,
                        "has_schema": True,
                        "type": json_type(sch, components),
                        "title": d.get("title"),
                    }
                break

            ops[f"{method.upper()} {path}"] = {
                "inputs": inputs,
                "response": resp,
                "declared_status_codes": sorted(op.get("responses", {}).keys()),
                "operation_id": op.get("operationId"),
            }
    return ops


def main():
    agents_dir = os.environ.get("F2A_AGENTS_DIR", "")
    from google.adk.cli.fast_api import get_fast_api_app

    merged = {}
    per_config = {}
    for name, kwargs in CONFIGS.items():
        try:
            app = get_fast_api_app(agents_dir=agents_dir, **kwargs)
            ops = extract(app.openapi())
            per_config[name] = sorted(ops)
            for k, v in ops.items():
                merged.setdefault(k, v)
            print(f"{name}: {len(ops)} operations", file=sys.stderr)
        except Exception as exc:  # noqa: BLE001
            per_config[name] = None
            print(f"{name}: FAILED {type(exc).__name__}: {exc}", file=sys.stderr)

    json.dump(
        {"operations": merged, "per_config": per_config},
        sys.stdout,
        indent=2,
        sort_keys=True,
    )
    print(f"union: {len(merged)} operations", file=sys.stderr)


if __name__ == "__main__":
    main()
