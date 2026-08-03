"""R1 — read deployment configuration as an analysis input.

For a given declared configuration, predict which route declarations in the
target's source actually register. This is a small depth-limited concrete-value
propagator over Python `ast`: it starts at a named entry point with the
configuration bound to that entry point's parameters, walks statements in order,
evaluates branch tests where it can, follows calls into other functions and
methods, and records every `@<app>.<verb>("<path>")` decorator it reaches.

Nothing is executed. No model is called.

Each capability the propagator needs is a *named mechanism* that can be switched
off individually, so its contribution is measurable (PREREGISTRATION.md
secondary measurement 2):

  M1_class_dispatch  resolve `C = A if cond else B` then `C(...)`, walk the MRO
                     to find methods, and resolve `super().m()`.
  M2_kwarg_flow      bind actual arguments to parameters across a call, including
                     `**d` expansion and `d.update(k=v)`.
  M3_attribute_flow  carry constructor keyword arguments into `self.attr` reads.
  M4_membership      evaluate `"x" in <concrete collection>` element-wise rather
                     than as a truthiness test on the collection.
  M5_optional_import a guard on whether an optional package imports is treated as
                     satisfied when that package is importable.

With every mechanism off, what remains is R1-naive: a lexical `if <name>:` in the
function that immediately encloses the decorator, where `<name>` is a parameter
of that function bound directly from the declared configuration.
"""

from __future__ import annotations

import argparse
import ast
import importlib.util
import json
import os
from dataclasses import dataclass, field

VERBS = ("get", "post", "put", "patch", "delete", "options", "head", "websocket")

ALL_MECHANISMS = (
    "M1_class_dispatch",
    "M2_kwarg_flow",
    "M3_attribute_flow",
    "M4_membership",
    "M5_optional_import",
    "M6_explicit_presence",
    "M7_class_attrs",
    "M8_comprehension",
)


class Unknown:
    """A value the propagator could not resolve. Distinct from None and False."""

    _inst = None

    def __new__(cls):
        if cls._inst is None:
            cls._inst = super().__new__(cls)
        return cls._inst

    def __repr__(self):
        return "UNKNOWN"

    def __bool__(self):
        raise TypeError("Unknown has no truth value")


UNKNOWN = Unknown()


class Present:
    """A keyword the caller explicitly supplied, whose value did not evaluate.

    Mechanism M6. The target sets `web_assets_dir` to a computed `Path` only inside
    `if web:`, and every route behind `if web_assets_dir:` therefore depends on
    presence rather than on the value. Treating an explicitly supplied optional
    parameter as truthy recovers those routes.

    This is **not sound**: a caller can explicitly supply an empty string or an
    empty list, and this mechanism would call it enabled. It is reported in the
    ablation for exactly that reason.
    """

    _inst = None

    def __new__(cls):
        if cls._inst is None:
            cls._inst = super().__new__(cls)
        return cls._inst

    def __repr__(self):
        return "PRESENT"

    def __bool__(self):
        return True


PRESENT = Present()


@dataclass
class Obj:
    """An instance of a class defined in the analysed source."""

    cls: str
    attrs: dict = field(default_factory=dict)


@dataclass
class FastAPIApp:
    """The application object route decorators attach to."""

    tag: str = "app"


@dataclass
class ClassRef:
    name: str


@dataclass
class Found:
    method: str
    path: str
    module: str
    lineno: int
    certain: bool  # False when some guard on the way here was unresolvable
    guards: list


class Analyzer:
    def __init__(self, source_root, mechanisms):
        self.root = source_root
        self.m = set(mechanisms)
        self.modules = {}  # dotted module name -> ast.Module
        self.classes = {}  # "module.Class" -> ast.ClassDef
        self.class_module = {}
        self.functions = {}  # "module.func" -> ast.FunctionDef
        self._load()

    # ---------- loading ----------

    def _load(self):
        for dirpath, _dirs, files in os.walk(self.root):
            for fn in files:
                if not fn.endswith(".py"):
                    continue
                full = os.path.join(dirpath, fn)
                rel = os.path.relpath(full, self.root)
                mod = rel[:-3].replace(os.sep, ".")
                if mod.endswith(".__init__"):
                    mod = mod[: -len(".__init__")]
                try:
                    tree = ast.parse(open(full, encoding="utf-8").read(), filename=full)
                except SyntaxError:
                    continue
                self.modules[mod] = tree
                for node in tree.body:
                    if isinstance(node, ast.ClassDef):
                        self.classes[f"{mod}.{node.name}"] = node
                        self.class_module[node.name] = mod
                    elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        self.functions[f"{mod}.{node.name}"] = node

    def find_class(self, name):
        if name in self.class_module:
            return self.classes[f"{self.class_module[name]}.{name}"]
        return None

    def mro(self, class_name):
        """Linear base chain by name. Only classes defined in the analysed source."""
        out, cur, seen = [], class_name, set()
        while cur and cur not in seen:
            seen.add(cur)
            node = self.find_class(cur)
            if node is None:
                break
            out.append(cur)
            nxt = None
            for b in node.bases:
                if isinstance(b, ast.Name) and self.find_class(b.id):
                    nxt = b.id
                    break
            cur = nxt
        return out

    def lookup_method(self, class_name, method_name):
        chain = self.mro(class_name) if "M1_class_dispatch" in self.m else [class_name]
        for cn in chain:
            node = self.find_class(cn)
            if node is None:
                continue
            for st in node.body:
                if (
                    isinstance(st, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and st.name == method_name
                ):
                    return cn, st
        return None, None

    # ---------- evaluation ----------

    def eval_expr(self, node, env):
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Name):
            if node.id in env:
                return env[node.id]
            # Plain name resolution: a class defined in the analysed source and
            # imported into this module. Not a mechanism — without it no name
            # referring to a class resolves at all.
            if self.find_class(node.id) is not None:
                return ClassRef(node.id)
            return UNKNOWN
        if isinstance(node, ast.List):
            vals = [self.eval_expr(e, env) for e in node.elts]
            return UNKNOWN if any(v is UNKNOWN for v in vals) else vals
        if isinstance(node, ast.Tuple):
            vals = [self.eval_expr(e, env) for e in node.elts]
            return UNKNOWN if any(v is UNKNOWN for v in vals) else tuple(vals)
        if isinstance(node, ast.Dict):
            out = {}
            for k, v in zip(node.keys, node.values):
                kv = self.eval_expr(k, env) if k is not None else UNKNOWN
                if kv is UNKNOWN or not isinstance(kv, str):
                    return UNKNOWN
                out[kv] = self.eval_expr(v, env)
            return out
        if isinstance(node, ast.Attribute):
            base = self.eval_expr(node.value, env)
            if isinstance(base, Obj):
                if "M3_attribute_flow" in self.m and node.attr in base.attrs:
                    return base.attrs[node.attr]
                if "M7_class_attrs" in self.m:
                    return self.class_attr(base.cls, node.attr, env)
            return UNKNOWN
        if isinstance(node, (ast.ListComp, ast.SetComp)):
            return self.eval_comprehension(node, env)
        if isinstance(node, ast.IfExp):
            test = self.truth(node.test, env)
            if test is True:
                return self.eval_expr(node.body, env)
            if test is False:
                return self.eval_expr(node.orelse, env)
            return UNKNOWN
        if isinstance(node, ast.JoinedStr):
            return UNKNOWN
        if isinstance(node, ast.NamedExpr):
            val = self.eval_expr(node.value, env)
            if isinstance(node.target, ast.Name):
                env[node.target.id] = val
            return val
        return UNKNOWN

    def class_attr(self, class_name, attr, env):
        """A class-level assignment, looked up through the base chain (M7).

        `VALID_TRIGGER_SOURCES = ["pubsub", "eventarc"]` is a class attribute, and
        the predicate that decides whether a trigger route registers reads it.
        """
        for cn in self.mro(class_name):
            node = self.find_class(cn)
            if node is None:
                continue
            for st in node.body:
                targets = (
                    st.targets
                    if isinstance(st, ast.Assign)
                    else ([st.target] if isinstance(st, ast.AnnAssign) else [])
                )
                for t in targets:
                    if isinstance(t, ast.Name) and t.id == attr and st.value is not None:
                        return self.eval_expr(st.value, {})
        return UNKNOWN

    def eval_comprehension(self, node, env):
        """A list/set comprehension over a single concrete iterable (M8)."""
        if "M8_comprehension" not in self.m or len(node.generators) != 1:
            return UNKNOWN
        gen = node.generators[0]
        if not isinstance(gen.target, ast.Name):
            return UNKNOWN
        iterable = self.eval_expr(gen.iter, env)
        if not isinstance(iterable, (list, tuple, set)):
            return UNKNOWN
        out = []
        for item in iterable:
            sub = dict(env)
            sub[gen.target.id] = item
            keep = True
            for cond in gen.ifs:
                t = self.truth(cond, sub)
                if t is not True:
                    keep = False
                    break
            if keep:
                val = self.eval_expr(node.elt, sub)
                if val is UNKNOWN:
                    return UNKNOWN
                out.append(val)
        return out

    def truth(self, node, env):
        """Evaluate a branch test to True, False, or UNKNOWN."""
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            inner = self.truth(node.operand, env)
            return UNKNOWN if inner is UNKNOWN else (not inner)
        if isinstance(node, ast.BoolOp):
            vals = [self.truth(v, env) for v in node.values]
            if isinstance(node.op, ast.And):
                if any(v is False for v in vals):
                    return False
                return UNKNOWN if any(v is UNKNOWN for v in vals) else True
            if any(v is True for v in vals):
                return True
            return UNKNOWN if any(v is UNKNOWN for v in vals) else False
        if isinstance(node, ast.Compare) and len(node.ops) == 1:
            op = node.ops[0]
            if isinstance(op, (ast.In, ast.NotIn)):
                if "M4_membership" not in self.m:
                    return UNKNOWN
                needle = self.eval_expr(node.left, env)
                hay = self.eval_expr(node.comparators[0], env)
                if needle is UNKNOWN or hay is UNKNOWN or hay is None:
                    return UNKNOWN
                try:
                    res = needle in hay
                except TypeError:
                    return UNKNOWN
                return res if isinstance(op, ast.In) else (not res)
            left = self.eval_expr(node.left, env)
            right = self.eval_expr(node.comparators[0], env)
            if left is UNKNOWN or right is UNKNOWN:
                return UNKNOWN
            try:
                if isinstance(op, ast.Eq):
                    return left == right
                if isinstance(op, ast.NotEq):
                    return left != right
                if isinstance(op, ast.Is):
                    return left is right
                if isinstance(op, ast.IsNot):
                    return left is not right
            except Exception:  # noqa: BLE001
                return UNKNOWN
            return UNKNOWN
        val = self.eval_expr(node, env)
        if val is UNKNOWN:
            return UNKNOWN
        try:
            return bool(val)
        except Exception:  # noqa: BLE001
            return UNKNOWN

    # ---------- optional-import guard (M5) ----------

    def _is_optional_import_guard(self, stmts):
        """True when a Try block's body is only imports, i.e. an availability probe."""
        for st in stmts:
            if not isinstance(st, (ast.Import, ast.ImportFrom)):
                return None
        names = []
        for st in stmts:
            if isinstance(st, ast.Import):
                names += [a.name.split(".")[0] for a in st.names]
            else:
                names.append((st.module or "").split(".")[0])
        return names

    # ---------- walking ----------

    def run(self, entry_module, entry_func, config, max_depth=8):
        self.found = []
        self.notes = []
        fn = self.functions.get(f"{entry_module}.{entry_func}")
        if fn is None:
            raise SystemExit(f"entry point not found: {entry_module}.{entry_func}")
        env = self.bind_params(fn, [], dict(config), env_outer={})
        env["__app__"] = None
        try:
            self.exec_body(fn.body, env, entry_module, depth=0, guards=[], certain=True,
                           max_depth=max_depth)
        except _Returned:
            pass
        return self.found, self.notes

    def run_method_entry(self, class_name, method, ctor_kwargs, call_kwargs,
                         max_depth=8):
        """Entry point for the embedding path: construct a class, call a method.

        Configuration 7 deploys by instantiating the server class directly rather
        than through the module-level factory, which is what decorrelates
        `web_assets_dir` from the `web` flag.
        """
        self.found = []
        self.notes = []
        obj = Obj(cls=class_name)
        owner, init = self.lookup_method(class_name, "__init__")
        if init is not None and "M3_attribute_flow" in self.m:
            ienv = self.bind_params(init, [obj], dict(ctor_kwargs), {})
            for k, v in ienv.items():
                if k != "self":
                    obj.attrs.setdefault(k, v)
            ienv["self"] = obj
            ienv["__class__"] = owner
            try:
                self.exec_body(init.body, ienv, self.class_module.get(owner, "?"), 1, [],
                               True, max_depth)
            except _Returned:
                pass
        owner, fn = self.lookup_method(class_name, method)
        if fn is None:
            raise SystemExit(f"{class_name}.{method} not found")
        fenv = self.bind_params(fn, [obj], dict(call_kwargs), {})
        fenv["self"] = obj
        fenv["__class__"] = owner
        try:
            self.exec_body(fn.body, fenv, self.class_module.get(owner, "?"), 1, [], True,
                           max_depth)
        except _Returned:
            pass
        return self.found, self.notes

    def bind_params(self, fn, args, kwargs, env_outer):
        """Bind actual arguments to parameter names, falling back to defaults."""
        env = {}
        a = fn.args
        names = [p.arg for p in a.posonlyargs] + [p.arg for p in a.args]
        defaults = list(a.defaults)
        pad = len(names) - len(defaults)
        for i, nm in enumerate(names):
            if i < len(args):
                env[nm] = args[i]
            elif nm in kwargs:
                env[nm] = kwargs[nm]
            elif i >= pad:
                env[nm] = self.eval_expr(defaults[i - pad], env_outer)
            else:
                env[nm] = UNKNOWN
        for i, p in enumerate(a.kwonlyargs):
            if p.arg in kwargs:
                env[p.arg] = kwargs[p.arg]
            else:
                d = a.kw_defaults[i]
                env[p.arg] = self.eval_expr(d, env_outer) if d is not None else UNKNOWN
        # `**kwargs` catch-all: everything the callee did not name explicitly.
        if a.kwarg is not None:
            named = set(names) | {p.arg for p in a.kwonlyargs}
            env[a.kwarg.arg] = {k: v for k, v in kwargs.items() if k not in named}
        return env

    def _route_decorators(self, decs, env):
        """Every `@<appvalue>.<verb>("<path>")` among these decorators.

        All of them, not the first: this target stacks two route decorators on four
        handlers, and taking only the first silently loses four operations.
        """
        out = []
        for dec in decs:
            if not isinstance(dec, ast.Call) or not isinstance(dec.func, ast.Attribute):
                continue
            verb = dec.func.attr
            if verb not in VERBS or not dec.args:
                continue
            target = self.eval_expr(dec.func.value, env)
            if not isinstance(target, FastAPIApp):
                continue
            path = self.eval_expr(dec.args[0], env)
            if not isinstance(path, str):
                continue
            out.append((("WS" if verb == "websocket" else verb.upper()), path))
        return out

    def exec_body(self, body, env, module, depth, guards, certain, max_depth):
        for st in body:
            self.exec_stmt(st, env, module, depth, guards, certain, max_depth)

    def exec_stmt(self, st, env, module, depth, guards, certain, max_depth):
        if isinstance(st, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for hit in self._route_decorators(st.decorator_list, env):
                self.found.append(
                    Found(hit[0], hit[1], module, st.lineno, certain, list(guards))
                )
            # A nested def is not executed at definition time.
            return

        if isinstance(st, ast.ClassDef):
            return

        if isinstance(st, ast.If):
            t = self.truth(st.test, env)
            label = ast.unparse(st.test)
            if t is True:
                self.exec_body(st.body, env, module, depth, guards + [label],
                               certain, max_depth)
            elif t is False:
                self.exec_body(st.orelse, env, module, depth,
                               guards + [f"not ({label})"], certain, max_depth)
            else:
                # Unresolvable guard: both branches are possible. Everything found
                # underneath is marked uncertain. A `return` in one branch must not
                # stop the other from being walked.
                rets = []
                for body, lbl in (
                    (st.body, f"?{label}"),
                    (st.orelse, f"?not({label})"),
                ):
                    try:
                        self.exec_body(body, env, module, depth, guards + [lbl], False,
                                       max_depth)
                        rets.append(None)
                    except _Returned as r:
                        rets.append(r)
                if all(r is not None for r in rets) and rets:
                    raise rets[0]
            return

        if isinstance(st, ast.Try):
            imports = self._is_optional_import_guard(st.body)
            if imports is not None and "M5_optional_import" in self.m:
                available = all(
                    importlib.util.find_spec(n) is not None for n in imports if n
                )
                if available:
                    self.exec_body(st.body, env, module, depth,
                                   guards + [f"import {','.join(imports)} ok"],
                                   certain, max_depth)
                else:
                    for h in st.handlers:
                        self.exec_body(h.body, env, module, depth,
                                       guards + [f"import {','.join(imports)} missing"],
                                       certain, max_depth)
                self.exec_body(st.orelse, env, module, depth, guards, certain, max_depth)
                self.exec_body(st.finalbody, env, module, depth, guards, certain,
                               max_depth)
                return
            unc = certain if imports is None else False
            self.exec_body(st.body, env, module, depth, guards, unc, max_depth)
            self.exec_body(st.orelse, env, module, depth, guards, unc, max_depth)
            self.exec_body(st.finalbody, env, module, depth, guards, certain, max_depth)
            return

        if isinstance(st, ast.Return):
            # `if not web: return` — a guard expressed as early exit. Reaching a
            # Return on a live path means nothing after it executes. The value is
            # carried so a caller can bind it; without that, `app = super().
            # get_fast_api_app(...)` loses the application object and every route
            # registered downstream of it disappears.
            val = (
                self.eval_call_or_expr(st.value, env, module, depth, guards, certain,
                                        max_depth)
                if st.value is not None
                else None
            )
            raise _Returned(val)

        if isinstance(st, ast.Raise):
            raise _Returned(UNKNOWN)

        if isinstance(st, (ast.For, ast.AsyncFor)):
            # Loop trip count is a runtime property. Anything registered inside is
            # not statically predictable.
            self.exec_body(st.body, env, module, depth, guards + ["?loop"], False,
                           max_depth)
            self.exec_body(st.orelse, env, module, depth, guards, certain, max_depth)
            return

        if isinstance(st, (ast.With, ast.AsyncWith)):
            self.exec_body(st.body, env, module, depth, guards, certain, max_depth)
            return

        if isinstance(st, ast.Assign):
            val = self.eval_call_or_expr(st.value, env, module, depth, guards, certain,
                                         max_depth)
            for tgt in st.targets:
                self.assign(tgt, val, env)
            return

        if isinstance(st, ast.AnnAssign):
            if st.value is not None:
                val = self.eval_call_or_expr(st.value, env, module, depth, guards,
                                              certain, max_depth)
                self.assign(st.target, val, env)
            return

        if isinstance(st, ast.Expr):
            self.eval_call_or_expr(st.value, env, module, depth, guards, certain,
                                    max_depth)
            return

    def assign(self, tgt, val, env):
        if isinstance(tgt, ast.Name):
            env[tgt.id] = val
        elif isinstance(tgt, ast.Attribute) and "M3_attribute_flow" in self.m:
            base = self.eval_expr(tgt.value, env)
            if isinstance(base, Obj):
                base.attrs[tgt.attr] = val

    def eval_call_or_expr(self, node, env, module, depth, guards, certain, max_depth):
        if isinstance(node, ast.Call):
            return self.do_call(node, env, module, depth, guards, certain, max_depth)
        return self.eval_expr(node, env)

    def _collect_args(self, node, env, module, depth, guards, certain, max_depth):
        args = [
            self.eval_call_or_expr(a, env, module, depth, guards, certain, max_depth)
            for a in node.args
            if not isinstance(a, ast.Starred)
        ]
        kwargs = {}
        for kw in node.keywords:
            val = self.eval_call_or_expr(kw.value, env, module, depth, guards, certain,
                                          max_depth)
            if kw.arg is None:
                # **d expansion
                if "M2_kwarg_flow" in self.m and isinstance(val, dict):
                    kwargs.update(val)
                continue
            if val is UNKNOWN and "M6_explicit_presence" in self.m:
                val = PRESENT
            kwargs[kw.arg] = val
        return args, kwargs

    def do_call(self, node, env, module, depth, guards, certain, max_depth):
        if depth >= max_depth:
            return UNKNOWN
        f = node.func

        # FastAPI(...) — the application object itself.
        if isinstance(f, ast.Name) and f.id in ("FastAPI",):
            return FastAPIApp()

        # d.update(k=v) — how the target threads optional kwargs through.
        if isinstance(f, ast.Attribute) and f.attr == "update":
            base = self.eval_expr(f.value, env)
            if isinstance(base, dict) and "M2_kwarg_flow" in self.m:
                _a, kw = self._collect_args(node, env, module, depth, guards, certain,
                                            max_depth)
                base.update(kw)
            return None

        # d.get(k[, default]) — how a **kwargs dict is read back out.
        if isinstance(f, ast.Attribute) and f.attr == "get":
            base = self.eval_expr(f.value, env)
            if isinstance(base, dict) and "M2_kwarg_flow" in self.m and node.args:
                k = self.eval_expr(node.args[0], env)
                default = (
                    self.eval_expr(node.args[1], env) if len(node.args) > 1 else None
                )
                if isinstance(k, str):
                    return base.get(k, default)
            return UNKNOWN

        args, kwargs = self._collect_args(node, env, module, depth, guards, certain,
                                          max_depth)

        # super().method(...)
        if (
            isinstance(f, ast.Attribute)
            and isinstance(f.value, ast.Call)
            and isinstance(f.value.func, ast.Name)
            and f.value.func.id == "super"
        ):
            if "M1_class_dispatch" not in self.m:
                return UNKNOWN
            selfobj = env.get("self")
            cur = env.get("__class__")
            if not isinstance(selfobj, Obj) or not cur:
                return UNKNOWN
            chain = self.mro(selfobj.cls)
            try:
                start = chain.index(cur) + 1
            except ValueError:
                start = 1
            for cn in chain[start:]:
                owner, fn = self.lookup_method(cn, f.attr)
                if fn is not None:
                    return self.enter(fn, owner, selfobj, args, kwargs, env, depth,
                                       guards, certain, max_depth)
            return UNKNOWN

        # obj.method(...)
        if isinstance(f, ast.Attribute):
            base = self.eval_expr(f.value, env)
            if isinstance(base, Obj):
                owner, fn = self.lookup_method(base.cls, f.attr)
                if fn is not None:
                    return self.enter(fn, owner, base, args, kwargs, env, depth, guards,
                                       certain, max_depth)
            return UNKNOWN

        if isinstance(f, ast.Name):
            val = env.get(f.id, None)
            # A name bound to a class (possibly via `C = A if cond else B`).
            cls_name = None
            if isinstance(val, ClassRef):
                cls_name = val.name
            elif self.find_class(f.id) is not None:
                cls_name = f.id
            if cls_name is not None:
                if isinstance(val, ClassRef) and "M1_class_dispatch" not in self.m:
                    return UNKNOWN
                obj = Obj(cls=cls_name)
                if "M3_attribute_flow" in self.m:
                    owner, init = self.lookup_method(cls_name, "__init__")
                    if init is not None:
                        ienv = self.bind_params(init, [obj] + list(args), kwargs, env)
                        for k, v in ienv.items():
                            if k != "self":
                                obj.attrs.setdefault(k, v)
                        # also honour explicit self.x = ... in __init__
                        ienv["self"] = obj
                        ienv["__class__"] = owner
                        try:
                            self.exec_body(init.body, ienv, self.class_module.get(
                                cls_name, module), depth + 1, guards, certain, max_depth)
                        except _Returned:
                            pass
                return obj
            # A plain local function.
            for key in (f"{module}.{f.id}",):
                fn = self.functions.get(key)
                if fn is not None:
                    return self.enter(fn, None, None, args, kwargs, env, depth, guards,
                                       certain, max_depth)
            # Cross-module function, resolved by unique name.
            cands = [k for k in self.functions if k.rsplit(".", 1)[-1] == f.id]
            if len(cands) == 1:
                fn = self.functions[cands[0]]
                return self.enter(fn, None, None, args, kwargs, env, depth, guards,
                                   certain, max_depth,
                                   module_override=cands[0].rsplit(".", 1)[0])
            return UNKNOWN

        return UNKNOWN

    def enter(self, fn, owner_class, selfobj, args, kwargs, env, depth, guards, certain,
              max_depth, module_override=None):
        if "M2_kwarg_flow" not in self.m and depth > 0:
            return UNKNOWN
        mod = module_override or (
            self.class_module.get(owner_class) if owner_class else None
        )
        if mod is None:
            mod = self._module_of_function(fn)
        # `self` is the first declared parameter of a method, and the caller's
        # argument list does not contain it.
        callee_args = ([selfobj] + list(args)) if selfobj is not None else list(args)
        fenv = self.bind_params(fn, callee_args, kwargs, env)
        if selfobj is not None:
            fenv["self"] = selfobj
            fenv["__class__"] = owner_class
        try:
            self.exec_body(fn.body, fenv, mod, depth + 1, guards, certain, max_depth)
        except _Returned as r:
            return r.value
        return UNKNOWN

    def _module_of_function(self, fn):
        for key, node in self.functions.items():
            if node is fn:
                return key.rsplit(".", 1)[0]
        for key, cls in self.classes.items():
            for st in cls.body:
                if st is fn:
                    return key.rsplit(".", 1)[0]
        return "?"


class _Returned(Exception):
    def __init__(self, value=None):
        super().__init__()
        self.value = value


# ---------------------------------------------------------------------------
# R1-naive: the lexical predictor
# ---------------------------------------------------------------------------


def lexical_predict(source_root, config):
    """What a first-pass configuration parser recovers.

    Scans every `@<x>.<verb>("<path>")` decorator in the source. For each, walks
    outward through the enclosing statements *within the same function* and
    collects every `if` test it sits inside. A test is evaluated only when it is a
    bare name (or `not name`) matching a declared configuration key. Anything else
    is unresolvable.

    No call graph, no class dispatch, no attribute tracking, no membership
    evaluation. This is deliberately the cheap implementation, because findings 004
    and 007 both established that rules discovered by inspecting one codebase's
    failures should not be assumed to transfer, and the untuned number is the one
    worth carrying forward.
    """
    certain_true, certain_false, unresolved = [], [], []

    for dirpath, _dirs, files in os.walk(source_root):
        for fn in sorted(files):
            if not fn.endswith(".py"):
                continue
            full = os.path.join(dirpath, fn)
            try:
                tree = ast.parse(open(full, encoding="utf-8").read(), filename=full)
            except SyntaxError:
                continue
            rel = os.path.relpath(full, source_root)
            _lex_walk(tree, [], rel, config, certain_true, certain_false, unresolved)

    return certain_true, certain_false, unresolved


def _lex_eval(test, config):
    """True / False / None(unresolvable) for a lexical guard test."""
    negate = False
    node = test
    while isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        negate = not negate
        node = node.operand
    if isinstance(node, ast.Name) and node.id in config:
        val = config[node.id]
        try:
            res = bool(val)
        except Exception:  # noqa: BLE001
            return None
        return (not res) if negate else res
    return None


def _lex_walk(node, guard_stack, relfile, config, ct, cf, unres):
    body = getattr(node, "body", None)
    if body is None or isinstance(node, (ast.Lambda,)):
        return

    for st in body if isinstance(body, list) else [body]:
        if isinstance(st, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for hit in _lex_routes(st):
                verdicts = list(guard_stack)
                if any(v is False for v in verdicts):
                    cf.append((hit[0], hit[1], relfile, st.lineno))
                elif any(v is None for v in verdicts):
                    unres.append((hit[0], hit[1], relfile, st.lineno))
                else:
                    ct.append((hit[0], hit[1], relfile, st.lineno))
            # A new function frame: lexical guards from the enclosing frame do not
            # apply to code inside a *separate* function definition, but nested
            # defs inside a guarded block do inherit it. Keep the stack; the
            # distinction is interprocedural and this arm has none.
            _lex_walk(st, guard_stack, relfile, config, ct, cf, unres)
            continue
        if isinstance(st, ast.If):
            v = _lex_eval(st.test, config)
            _lex_walk(st, guard_stack + [v], relfile, config, ct, cf, unres)
            if st.orelse:
                inv = None if v is None else (not v)
                _lex_walk(
                    ast.Module(body=st.orelse, type_ignores=[]),
                    guard_stack + [inv],
                    relfile,
                    config,
                    ct,
                    cf,
                    unres,
                )
            continue
        if isinstance(st, (ast.For, ast.AsyncFor, ast.While, ast.With, ast.AsyncWith,
                           ast.Try, ast.ClassDef)):
            _lex_walk(st, guard_stack, relfile, config, ct, cf, unres)
            for extra in ("orelse", "finalbody", "handlers"):
                items = getattr(st, extra, None) or []
                if extra == "handlers":
                    for h in items:
                        _lex_walk(h, guard_stack, relfile, config, ct, cf, unres)
                elif items:
                    _lex_walk(
                        ast.Module(body=items, type_ignores=[]),
                        guard_stack,
                        relfile,
                        config,
                        ct,
                        cf,
                        unres,
                    )
            continue


def _lex_routes(fndef):
    """Every route decorator on this handler.

    A handler can carry more than one. This target stacks a kebab-case path and a
    snake_case legacy alias on four eval handlers, and an earlier version of this
    scanner returned only the first decorator and lost four real operations. The
    loss was silent: the totals still looked plausible.
    """
    out = []
    for dec in fndef.decorator_list:
        if not isinstance(dec, ast.Call) or not isinstance(dec.func, ast.Attribute):
            continue
        verb = dec.func.attr
        if verb not in VERBS or not dec.args:
            continue
        path = dec.args[0]
        if not isinstance(path, ast.Constant) or not isinstance(path.value, str):
            continue
        out.append((("WS" if verb == "websocket" else verb.upper()), path.value))
    return out


# The declared configuration each arm may read, mapped onto the entry point's
# parameter names. This is what an operator would supply, or what a Dockerfile
# CMD / Helm values file would be parsed into.
def config_to_entry_kwargs(name, declared):
    kw = dict(declared)
    kw.setdefault("agents_dir", "agents")
    return kw


ENTRY = {
    "default": ("fast_api", "get_fast_api_app"),
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True, help="path to src/google/adk/cli")
    ap.add_argument("--served-key", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument(
        "--mechanisms",
        default=",".join(ALL_MECHANISMS),
        help="comma-separated subset, or 'none'",
    )
    ap.add_argument(
        "--mode",
        default="interprocedural",
        choices=("interprocedural", "lexical"),
        help="lexical = R1-naive, the first-pass predictor",
    )
    ap.add_argument(
        "--entry",
        default="fast_api:get_fast_api_app",
        help="module:function, relative to --src. Lets the interprocedural arm be "
        "run with the whole repository in scope, so that its exclusion of other "
        "applications' routes is a measurement rather than an artefact of scoping.",
    )
    ap.add_argument("--entry-class", default="DevServer")
    args = ap.parse_args()
    ENTRY["default"] = tuple(args.entry.split(":", 1))

    mechs = [] if args.mechanisms == "none" else [
        m for m in args.mechanisms.split(",") if m
    ]
    key = json.load(open(args.served_key))

    out = {"mode": args.mode, "mechanisms": mechs, "configs": {}}

    if args.mode == "lexical":
        for name, cfg in key.items():
            if not cfg.get("ok"):
                out["configs"][name] = {"ok": False, "reason": "did not build"}
                continue
            ct, cf, unres = lexical_predict(args.src, cfg["declared_config"])
            out["configs"][name] = {
                "ok": True,
                "entry": "lexical scan of all route decorators",
                "declared_config": cfg["declared_config"],
                "certain": [list(p[:2]) for p in sorted(set(x[:2] for x in ct))],
                "uncertain": [
                    list(p) for p in sorted(set(x[:2] for x in unres))
                    if list(p) not in [list(q[:2]) for q in ct]
                ],
                "excluded_by_guard": [
                    list(p) for p in sorted(set(x[:2] for x in cf))
                ],
                "detail": [
                    {"method": m, "path": p, "module": f, "lineno": ln,
                     "verdict": v}
                    for v, group in (("served", ct), ("not_served", cf),
                                     ("unresolvable", unres))
                    for (m, p, f, ln) in group
                ],
            }
            print(
                f"{name}: lexical predicted {len(set(x[:2] for x in ct))} served, "
                f"{len(set(x[:2] for x in cf))} excluded, "
                f"{len(set(x[:2] for x in unres))} unresolvable",
                flush=True,
            )
        with open(args.out, "w") as fh:
            json.dump(out, fh, indent=2, sort_keys=True, default=str)
        return

    for name, cfg in key.items():
        if not cfg.get("ok"):
            out["configs"][name] = {"ok": False, "reason": "configuration did not build"}
            continue
        an = Analyzer(args.src, mechs)
        entry_mod, entry_fn = ENTRY["default"]
        if name == "devserver_no_assets":
            # Configuration 7 uses the embedding entry point. Recorded, not hidden.
            entry_mod, entry_fn = "dev_server", "get_fast_api_app"
        try:
            if name == "devserver_no_assets":
                found, notes = an.run_method_entry(
                    "DevServer",
                    "get_fast_api_app",
                    ctor_kwargs={"agents_dir": "agents"},
                    call_kwargs={
                        "web_assets_dir": cfg["declared_config"].get("web_assets_dir")
                    },
                )
            else:
                found, notes = an.run(
                    entry_mod,
                    entry_fn,
                    config_to_entry_kwargs(name, cfg["declared_config"]),
                )
        except RecursionError:
            out["configs"][name] = {"ok": False, "reason": "recursion limit"}
            continue

        certain = sorted({(f.method, f.path) for f in found if f.certain})
        uncertain = sorted({(f.method, f.path) for f in found if not f.certain})
        uncertain = [p for p in uncertain if p not in set(certain)]
        out["configs"][name] = {
            "ok": True,
            "entry": f"{entry_mod}.{entry_fn}",
            "declared_config": cfg["declared_config"],
            "certain": [list(p) for p in certain],
            "uncertain": [list(p) for p in uncertain],
            "detail": [
                {
                    "method": f.method,
                    "path": f.path,
                    "module": f.module,
                    "lineno": f.lineno,
                    "certain": f.certain,
                    "guards": f.guards,
                }
                for f in sorted(found, key=lambda x: (x.module, x.lineno))
            ],
            "notes": notes,
        }
        print(
            f"{name}: predicted {len(certain)} certain, {len(uncertain)} uncertain",
            flush=True,
        )

    with open(args.out, "w") as fh:
        json.dump(out, fh, indent=2, sort_keys=True, default=str)


if __name__ == "__main__":
    main()
