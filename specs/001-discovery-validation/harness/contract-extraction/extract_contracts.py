"""Derive a contract (parameters, return type, thrown exceptions) for each
recovered endpoint, statically.

The route-to-handler link comes from the codegraph index. Everything after that
is derived from the repository's own source with Python's `ast` module — no
execution of the target, and no model.

Three components are derived per endpoint:

  parameters  names, declared types, location (path/query/body/header), and
              whether required. Parameters annotated with a Pydantic model are
              expanded to the model's own fields, following base classes, and
              renamed if an inherited `model_config` declares an alias
              generator.
  return      the `-> T` annotation on the handler and the decorator's
              `response_model=` argument, recorded separately so that a
              disagreement between them stays visible.
  raises      every `raise` site in the handler body, with the status code of
              an `HTTPException` where it is a literal.

Output is one JSON record per endpoint, scored by score_contracts.py.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import sqlite3
from collections import defaultdict

VERBS = {"get", "post", "put", "patch", "delete", "options", "head"}

# Types FastAPI injects rather than reading off the request as a named input.
FRAMEWORK_TYPES = {
    "Request",
    "FastAPIRequest",
    "StarletteRequest",
    "WebSocket",
    "Response",
    "BackgroundTasks",
    "HTTPConnection",
    "SecurityScopes",
}

# Callables used as a parameter default that declare where the value comes from.
LOCATION_MARKERS = {
    "Query": "query",
    "Path": "path",
    "Body": "body",
    "Header": "header",
    "Cookie": "cookie",
    "Form": "body",
    "File": "body",
}

PRIMITIVES = {
    "str": "string",
    "int": "integer",
    "float": "number",
    "bool": "boolean",
    "bytes": "string",
    "dict": "object",
    "list": "array",
    "Any": "unknown",
    "UploadFile": "string",
}


def unparse(node):
    try:
        return ast.unparse(node)
    except Exception:  # noqa: BLE001
        return "<unparseable>"


def strip_optional(ann):
    """Return (inner_annotation_text, is_optional)."""
    t = ann.strip()
    m = re.match(r"^Optional\[(.+)\]$", t)
    if m:
        return m.group(1).strip(), True
    if "|" in t:
        parts = [p.strip() for p in t.split("|")]
        non_null = [p for p in parts if p not in ("None", "NoneType")]
        if len(non_null) != len(parts):
            return (non_null[0] if non_null else t), True
    return t, False


def base_name(ann):
    """The bare symbol at the head of an annotation, e.g. `Session` in
    `Optional[Session]` and `UploadFile` in `list[UploadFile]`."""
    t, _ = strip_optional(ann)
    m = re.match(r"^([\w.]+)\s*\[(.+)\]$", t)
    if m:
        head = m.group(1).split(".")[-1]
        if head in ("list", "List", "Sequence", "Iterable", "set", "Set"):
            return base_name(m.group(2))
        if head in ("dict", "Dict", "Mapping"):
            return "dict"
        return head
    return t.split(".")[-1]


def json_type_of(ann):
    """Best-effort JSON type token for a Python annotation, comparable with the
    tokens `build_contract_key.py` derives from the OpenAPI schema."""
    t, _ = strip_optional(ann)
    m = re.match(r"^([\w.]+)\s*\[(.+)\]$", t)
    if m:
        head = m.group(1).split(".")[-1]
        if head in ("list", "List", "Sequence", "Iterable"):
            return f"array[{json_type_of(m.group(2))}]"
        if head in ("dict", "Dict", "Mapping"):
            return "object"
        if head in ("Literal",):
            return "string"
    head = t.split(".")[-1]
    return PRIMITIVES.get(head, "object")


FIELD_FACTORIES = {"Field", "PrivateAttr"}


def has_default_value(value):
    """Whether an assigned value actually supplies a default.

    `x: str = Field(description="...")` assigns something but leaves the field
    required; only `default=`, `default_factory=`, or a non-Ellipsis positional
    argument makes it optional. Reading the presence of an assignment as a
    default is the obvious first-pass mistake and it silently inverts the
    required flag.
    """
    if value is None:
        return False
    if isinstance(value, ast.Constant) and value.value is Ellipsis:
        return False
    if isinstance(value, ast.Call):
        head = unparse(value.func).split(".")[-1]
        if head in FIELD_FACTORIES:
            for kw in value.keywords:
                if kw.arg in ("default", "default_factory"):
                    if kw.arg == "default" and isinstance(
                        kw.value, ast.Constant
                    ):
                        return kw.value.value is not Ellipsis
                    return True
            if value.args:
                first = value.args[0]
                if isinstance(first, ast.Constant) and first.value is Ellipsis:
                    return False
                return True
            return False
    return True


def to_camel(name):
    """pydantic.alias_generators.to_camel, reimplemented for static use."""
    parts = name.split("_")
    if not parts:
        return name
    return parts[0] + "".join(p.title() for p in parts[1:])


ALIAS_GENERATORS = {"to_camel": to_camel}


# --------------------------------------------------------------------------
# Repository class index
# --------------------------------------------------------------------------


class ClassIndex:
    """Every class in the repository, with its declared fields and bases.

    Module-level type aliases are collected alongside classes, because a field
    annotated `Optional[StaticConversation]` carries no shape at all until
    `StaticConversation: TypeAlias = list[Invocation]` is resolved.
    """

    def __init__(self):
        self.by_name = defaultdict(list)
        self.aliases = {}

    def build(self, root, subdirs=("src",)):
        for sub in subdirs:
            for dirpath, dirs, files in os.walk(os.path.join(root, sub)):
                dirs[:] = [
                    d for d in dirs if d not in ("__pycache__", ".codegraph")
                ]
                for f in files:
                    if not f.endswith(".py"):
                        continue
                    p = os.path.join(dirpath, f)
                    rel = os.path.relpath(p, root)
                    try:
                        tree = ast.parse(
                            open(p, encoding="utf-8", errors="replace").read()
                        )
                    except SyntaxError:
                        continue
                    for node in ast.walk(tree):
                        if isinstance(node, ast.ClassDef):
                            self.by_name[node.name].append(
                                self._record(node, rel)
                            )
                    for node in tree.body:
                        alias = self._alias(node)
                        if alias:
                            self.aliases.setdefault(alias[0], alias[1])
        return self

    @staticmethod
    def _alias(node):
        """`Name: TypeAlias = <expr>` or a bare `Name = <type expr>`."""
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            ann = unparse(node.annotation).split(".")[-1]
            if ann == "TypeAlias" and node.value is not None:
                return node.target.id, unparse(node.value)
            return None
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and isinstance(node.value, ast.Subscript)
        ):
            txt = unparse(node.value)
            if re.match(r"^(list|List|dict|Dict|Union|Optional)\[", txt):
                return node.targets[0].id, txt
        return None

    def resolve_alias(self, ann, depth=0):
        """Substitute a module-level alias into an annotation, once."""
        if depth > 4:
            return ann
        head = base_name(ann)
        target = self.aliases.get(head)
        if target and target != ann:
            return self.resolve_alias(ann.replace(head, target, 1), depth + 1)
        return ann

    @staticmethod
    def _record(node, rel):
        fields = []
        alias_gen = None
        for stmt in node.body:
            if isinstance(stmt, ast.AnnAssign) and isinstance(
                stmt.target, ast.Name
            ):
                name = stmt.target.id
                if name.startswith("_") or name == "model_config":
                    continue
                fields.append(
                    {
                        "name": name,
                        "annotation": unparse(stmt.annotation),
                        "has_default": has_default_value(stmt.value),
                        "has_default_naive": stmt.value is not None,
                    }
                )
            if isinstance(stmt, ast.Assign):
                for t in stmt.targets:
                    if isinstance(t, ast.Name) and t.id == "model_config":
                        txt = unparse(stmt.value)
                        m = re.search(r"alias_generator\s*=\s*([\w.]+)", txt)
                        if m:
                            alias_gen = m.group(1).split(".")[-1]
        return {
            "name": node.name,
            "file": rel,
            "bases": [unparse(b).split(".")[-1] for b in node.bases],
            "fields": fields,
            "alias_generator": alias_gen,
        }

    def lookup(self, name, prefer_file=None):
        cands = self.by_name.get(name, [])
        if not cands:
            return None
        if prefer_file:
            same = [c for c in cands if c["file"] == prefer_file]
            if same:
                return same[0]
        return cands[0]

    def resolve_model(self, name, prefer_file=None, depth=0, seen=None):
        """Flatten a model's fields through its base classes, and find the
        alias generator that the nearest configured ancestor declares.

        Returns None when the name is not a class in the repository, which is
        how a non-model annotation is distinguished from an unresolvable one.
        """
        seen = seen or set()
        if depth > 6 or name in seen:
            return None
        seen.add(name)
        rec = self.lookup(name, prefer_file)
        if rec is None:
            return None
        fields = []
        alias_gen = rec["alias_generator"]
        is_model = any(
            b in ("BaseModel", "pydantic.BaseModel") for b in rec["bases"]
        )
        for b in rec["bases"]:
            parent = self.resolve_model(b, rec["file"], depth + 1, seen)
            if parent:
                fields.extend(parent["fields"])
                alias_gen = alias_gen or parent["alias_generator"]
                is_model = is_model or parent["is_model"]
        own = {f["name"] for f in rec["fields"]}
        fields = [f for f in fields if f["name"] not in own] + rec["fields"]
        return {
            "name": name,
            "file": rec["file"],
            "fields": fields,
            "alias_generator": alias_gen,
            "is_model": is_model,
        }


# --------------------------------------------------------------------------
# Handler analysis
# --------------------------------------------------------------------------


def find_function(tree, lineno, name):
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.lineno == lineno and node.name == name:
                return node
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == name and abs(node.lineno - lineno) <= 3:
                return node
    return None


def route_decorator(fn):
    """The `@x.verb("path", ...)` decorator on a handler, if present."""
    for dec in fn.decorator_list:
        if not isinstance(dec, ast.Call):
            continue
        func = dec.func
        if isinstance(func, ast.Attribute) and func.attr in VERBS:
            return dec
    return None


def path_params(path):
    return [m.split(":")[0] for m in re.findall(r"\{([^}]+)\}", path)]


SCALAR_HEADS = {
    "str",
    "int",
    "float",
    "bool",
    "bytes",
    "UUID",
    "date",
    "datetime",
    "time",
    "Decimal",
    "Literal",
}


def is_complex(ann, class_index, handler_file):
    """FastAPI binds a scalar-annotated parameter to the query string and a
    complex one (model, dict, list) to the request body. An extractor that
    defaults everything unmatched to `query` gets the complex ones wrong."""
    inner, _ = strip_optional(ann)
    head = base_name(inner)
    root = inner.split("[")[0].split(".")[-1].strip()
    if root in ("dict", "Dict", "Mapping", "list", "List", "Sequence", "set"):
        return True
    if head in SCALAR_HEADS or root in SCALAR_HEADS:
        return False
    rec = class_index.lookup(head, handler_file)
    if rec is not None:
        return True
    return False


def classify_param(arg, default, in_path, class_index, handler_file, rules):
    """One handler parameter becomes zero, one, or many contract inputs."""
    name = arg.arg
    ann = unparse(arg.annotation) if arg.annotation else None
    if ann and rules.get("aliases"):
        ann = class_index.resolve_alias(ann)
    default_txt = unparse(default) if default is not None else None

    if name in ("self", "cls"):
        return [], "receiver"

    if ann is None:
        return (
            [
                {
                    "name": name,
                    "location": "query",
                    "required": default is None,
                    "type": "unknown",
                    "source": "unannotated",
                }
            ],
            "unannotated",
        )

    head = base_name(ann)

    if head in FRAMEWORK_TYPES:
        return [], "framework-injected"

    if default_txt and default_txt.startswith("Depends("):
        return [], "dependency"

    marker = None
    if default_txt:
        m = re.match(r"^(\w+)\(", default_txt)
        if m and m.group(1) in LOCATION_MARKERS:
            marker = LOCATION_MARKERS[m.group(1)]

    inner, optional = strip_optional(ann)
    has_default = default is not None and default_txt not in ("...", "Ellipsis")
    if default_txt and re.match(r"^\w+\(", default_txt):
        # Query(None)/File(...) style: required iff the first argument is `...`
        inner_args = default_txt[default_txt.index("(") + 1 :].rstrip(")")
        has_default = not inner_args.strip().startswith("...")

    model = class_index.resolve_model(head, handler_file)
    if model and model["is_model"] and marker != "query":
        gen = (
            ALIAS_GENERATORS.get(model["alias_generator"] or "")
            if rules.get("alias_generator")
            else None
        )
        out = []
        for f in model["fields"]:
            wire = gen(f["name"]) if gen else f["name"]
            f_ann = f["annotation"]
            if rules.get("aliases"):
                f_ann = class_index.resolve_alias(f_ann)
            _, f_opt = strip_optional(f_ann)
            required = not (f["has_default"] or f_opt)
            if not rules.get("field_defaults"):
                required = not (f["has_default_naive"] or f_opt)
            out.append(
                {
                    "name": wire,
                    "declared_name": f["name"],
                    "location": "body",
                    "required": required,
                    "type": json_type_of(f_ann),
                    "source": f"model:{model['name']}",
                }
            )
        return out, "model-expanded"

    if name in in_path:
        location = "path"
        required = True
    elif marker:
        location = marker
        required = not has_default
    elif head == "UploadFile":
        location = "body"
        required = not has_default
    elif rules.get("complex_is_body") and is_complex(
        ann, class_index, handler_file
    ):
        # A lone complex body parameter is the body, not a named field inside
        # it, unless Body(embed=True) says otherwise.
        return (
            [
                {
                    "name": name,
                    "location": "body",
                    "required": not has_default,
                    "type": json_type_of(ann),
                    "source": "signature",
                    "body_whole": True,
                }
            ],
            "complex-body",
        )
    else:
        location = "query"
        required = not has_default

    return (
        [
            {
                "name": name,
                "location": location,
                "required": required,
                "type": json_type_of(ann),
                "source": "signature",
            }
        ],
        "scalar",
    )


def raise_sites(fn):
    """Every `raise` in a function body, with a literal status code where the
    exception is constructed with one."""
    out = []
    for node in ast.walk(fn):
        if not isinstance(node, ast.Raise) or node.exc is None:
            continue
        exc = node.exc
        if isinstance(exc, ast.Call):
            cls = base_name(unparse(exc.func))
            status = None
            for kw in exc.keywords:
                if kw.arg == "status_code" and isinstance(
                    kw.value, ast.Constant
                ):
                    status = kw.value.value
            if status is None and exc.args:
                first = exc.args[0]
                if isinstance(first, ast.Constant) and isinstance(
                    first.value, int
                ):
                    status = first.value
            out.append(
                {"class": cls, "status_code": status, "line": node.lineno}
            )
        elif isinstance(exc, ast.Name):
            out.append(
                {
                    "class": exc.id,
                    "status_code": None,
                    "line": node.lineno,
                    "reraise": True,
                }
            )
        else:
            out.append(
                {
                    "class": base_name(unparse(exc)),
                    "status_code": None,
                    "line": node.lineno,
                }
            )
    return out


def derive(fn, route_path, class_index, handler_file, rules):
    in_path = set(path_params(route_path))
    args = fn.args
    positional = list(args.posonlyargs) + list(args.args)
    defaults = [None] * (len(positional) - len(args.defaults)) + list(
        args.defaults
    )

    inputs = []
    notes = defaultdict(int)
    for a, d in zip(positional, defaults):
        got, why = classify_param(
            a, d, in_path, class_index, handler_file, rules
        )
        inputs.extend(got)
        notes[why] += 1
    for a, d in zip(args.kwonlyargs, args.kw_defaults):
        got, why = classify_param(
            a, d, in_path, class_index, handler_file, rules
        )
        inputs.extend(got)
        notes[why] += 1

    whole = [i for i in inputs if i.get("body_whole")]
    other_body = [
        i for i in inputs if i["location"] == "body" and not i.get("body_whole")
    ]
    if len(whole) == 1 and not other_body:
        whole[0]["declared_name"] = whole[0]["name"]
        whole[0]["name"] = "__body__"

    dec = route_decorator(fn)
    response_model = None
    response_class = None
    declared_status = None
    declared_responses = []
    if dec:
        for kw in dec.keywords:
            if kw.arg == "response_model":
                response_model = unparse(kw.value)
            elif kw.arg == "response_class" and rules.get("response_class"):
                # A third declaration site for the return type. `response_class=
                # PlainTextResponse` is what makes FastAPI publish `type: string`
                # for a handler that carries no annotation at all.
                response_class = unparse(kw.value).split(".")[-1]
            elif kw.arg == "status_code":
                declared_status = unparse(kw.value)
            elif kw.arg == "responses":
                declared_responses = re.findall(r"\b(\d{3})\b", unparse(kw.value))

    annotation = unparse(fn.returns) if fn.returns else None
    if annotation and rules.get("aliases"):
        annotation = class_index.resolve_alias(annotation)

    raises = raise_sites(fn)

    return {
        "inputs": inputs,
        "param_notes": dict(notes),
        "return_annotation": annotation,
        "response_model": response_model,
        "response_class": response_class,
        "declared_status_code": declared_status,
        "declared_responses": declared_responses,
        "raises": raises,
    }


def one_hop_raises(con, repo, trees, h_name, h_file, h_line):
    """Raise sites in the functions the handler calls directly.

    A handler that never raises may still fail, because the service it delegates
    to raises. Following `calls` edges one hop shows how much of the exception
    surface sits below the handler itself.
    """
    rows = con.execute(
        """
        SELECT DISTINCT t.name, t.file_path, t.start_line
        FROM nodes h
        JOIN edges e ON e.source = h.id AND e.kind = 'calls'
        JOIN nodes t ON t.id = e.target
        WHERE h.name = ? AND h.file_path = ? AND h.start_line = ?
          AND t.kind IN ('function', 'method')
        """,
        (h_name, h_file, h_line),
    ).fetchall()
    out = []
    for name, path, line in rows:
        if not path or not path.endswith(".py"):
            continue
        if path not in trees:
            full = os.path.join(repo, path)
            if not os.path.exists(full):
                continue
            try:
                trees[path] = ast.parse(
                    open(full, encoding="utf-8", errors="replace").read()
                )
            except SyntaxError:
                continue
        callee = find_function(trees[path], line, name)
        if callee is None:
            continue
        for r in raise_sites(callee):
            r["in"] = f"{path}:{name}"
            out.append(r)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--db", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument(
        "--disable",
        default="",
        help=(
            "comma-separated rules to switch off, so each one's contribution "
            "can be measured: field_defaults (a bare Field() is not a "
            "default), complex_is_body (a complex annotation binds to the "
            "request body, not the query string), aliases (resolve module-"
            "level type aliases), alias_generator (apply an inherited "
            "model_config alias generator to field names), response_class "
            "(read the decorator's response_class= as a return-type "
            "declaration). `all` disables every one."
        ),
    )
    args = ap.parse_args()

    ALL_RULES = (
        "field_defaults",
        "complex_is_body",
        "aliases",
        "alias_generator",
        "response_class",
    )
    off = {r.strip() for r in args.disable.split(",") if r.strip()}
    if "all" in off:
        off = set(ALL_RULES)
    rules = {r: r not in off for r in ALL_RULES}

    class_index = ClassIndex().build(args.repo)

    con = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    rows = con.execute(
        """
        SELECT n.name, n.file_path, t.name, t.file_path, t.start_line,
               t.signature
        FROM nodes n
        JOIN edges e ON e.source = n.id
        JOIN nodes t ON t.id = e.target
        WHERE n.kind = 'route' AND n.file_path LIKE 'src/%'
        ORDER BY n.file_path, n.start_line
        """
    ).fetchall()
    con2 = con

    trees = {}
    out = {}
    failures = []
    for route_name, route_file, h_name, h_file, h_line, h_sig in rows:
        m = re.match(r"^([A-Z]+)\s+(\S.*)$", route_name)
        if not m:
            continue
        op = f"{m.group(1)} {m.group(2)}"
        if h_file not in trees:
            path = os.path.join(args.repo, h_file)
            trees[h_file] = ast.parse(
                open(path, encoding="utf-8", errors="replace").read()
            )
        fn = find_function(trees[h_file], h_line, h_name)
        if fn is None:
            failures.append(
                {"op": op, "handler": h_name, "reason": "handler not located"}
            )
            continue
        contract = derive(fn, m.group(2), class_index, h_file, rules)
        contract["raises_one_hop"] = one_hop_raises(
            con2, args.repo, trees, h_name, h_file, h_line
        )
        contract["handler"] = h_name
        contract["handler_file"] = h_file
        contract["handler_line"] = h_line
        contract["index_signature"] = h_sig
        out[op] = contract

    con2.close()
    json.dump(
        {"contracts": out, "failures": failures, "rules": rules},
        open(args.out, "w"),
        indent=2,
        sort_keys=True,
    )
    print(
        f"derived contracts for {len(out)} endpoints "
        f"({len(failures)} handler lookups failed)"
    )


if __name__ == "__main__":
    main()
