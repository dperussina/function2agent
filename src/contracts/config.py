"""T029, T030, T031 — declared configuration, injected at process start,
failing loudly on anything missing or invalid (FR-033).

Three rules, and the third is the one this module exists for.

1. **Declared.** Every key a process reads is in a schema here. A process reads
   `os.environ` nowhere else.
2. **Injected at start.** Resolution happens once, before anything is started.
   A process that gets past `load()` has every value it will ever need.
3. **No default for a bound and no default for a ceiling.** **Q-10** accepted
   the recommendation that FR-049's `SANDBOX_MEMORY_MAX`, `SANDBOX_CPU_MAX` and
   `SANDBOX_CPU_TOTAL` be required with no default, and FR-005 was extended the
   same day to take Q-10's treatment for the four session ceilings rather than
   FR-047's. So neither ships a number.

   The distinction the plan draws is worth keeping in front of the reader,
   because it is the reason two superficially similar cases are treated
   differently: an unvalidated staleness ceiling is *a number nobody has
   checked*; an invented spend ceiling is *an unbounded liability wearing one*.
   `STALENESS_CEILING_SECONDS`, `DRIFT_CHECK_INTERVAL_SECONDS` and
   `CAPABILITY_LEASE_INTERVAL_SECONDS` therefore ship stated defaults marked
   unvalidated under FR-043; the bounds and the ceilings ship nothing.

There is no `--force`, no `DEFAULTS=1`, and no way to start with a bound unset.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Mapping

from src.contracts.secret import Secret
from src.contracts.unvalidated import Unvalidated, mark


class Kind(Enum):
    STR = "str"
    INT = "int"
    FLOAT = "float"
    PATH = "path"
    SECRET = "secret"
    BYTES_SIZE = "bytes_size"  # e.g. "512MiB"
    CPU_QUOTA = "cpu_quota"  # e.g. "50000/100000" — cgroup v2 cpu.max form


class ConfigError(RuntimeError):
    """Startup stops here. Nothing is started, nothing is partially started."""


@dataclass(frozen=True)
class Key:
    name: str
    kind: Kind
    requirement: str
    purpose: str
    # `required` with no default is the Q-10 treatment. A key that ships a
    # default MUST carry `unvalidated=True` and appear in FR-043's standing
    # report, because a default nobody measured is a claim.
    default: str | None = None
    unvalidated: bool = False
    # Why this key has no default, quoted back to the operator at startup.
    no_default_reason: str | None = None


def _bytes_size(raw: str) -> int:
    units = {"": 1, "K": 10**3, "KI": 2**10, "M": 10**6, "MI": 2**20,
             "G": 10**9, "GI": 2**30}
    text = raw.strip().upper().removesuffix("B")
    for suffix in sorted(units, key=len, reverse=True):
        if suffix and text.endswith(suffix):
            number, unit = text[: -len(suffix)], suffix
            break
    else:
        number, unit = text, ""
    try:
        value = int(float(number) * units[unit])
    except (ValueError, KeyError) as exc:
        raise ValueError(f"not a byte size: {raw!r} ({exc})") from None
    if value <= 0:
        raise ValueError(f"byte size must be positive: {raw!r}")
    return value


def _cpu_quota(raw: str) -> str:
    """cgroup v2 `cpu.max` form: `<quota_us> <period_us>` or `max <period_us>`."""
    parts = raw.strip().replace("/", " ").split()
    if len(parts) != 2:
        raise ValueError(
            f"cpu.max needs '<quota_us> <period_us>', got {raw!r}. 'max' is "
            "rejected: an unbounded rate is not a declared bound (FR-049)."
        )
    quota, period = parts
    if quota == "max":
        raise ValueError(
            "cpu.max='max' is an unset bound wearing a value. FR-049 requires "
            "a declared bound; Q-10 requires startup to fail rather than "
            "default."
        )
    if int(quota) <= 0 or int(period) <= 0:
        raise ValueError(f"cpu.max quota and period must be positive: {raw!r}")
    return f"{int(quota)} {int(period)}"


_PARSERS: Mapping[Kind, Callable[[str], Any]] = {
    Kind.STR: lambda s: s,
    Kind.INT: lambda s: int(s),
    Kind.FLOAT: lambda s: float(s),
    Kind.PATH: lambda s: s,
    Kind.BYTES_SIZE: _bytes_size,
    Kind.CPU_QUOTA: _cpu_quota,
}


_NO_DEFAULT_BOUND = (
    "FR-049 states no default for either bound and Q-10 was accepted as "
    "recommended: required configuration, startup fails loudly. Nothing in "
    "feature 001's evidence base bears on an agent's working set, so any "
    "number shipped here would be invented."
)

_NO_DEFAULT_CEILING = (
    "FR-005 states no default for any of the four ceilings. A ceiling filled "
    "from an invented default is not an unvalidated number — it is an "
    "unbounded liability wearing one."
)


# ---------------------------------------------------------------------------
# The declared schema.
# ---------------------------------------------------------------------------

SUPERVISOR_KEYS: tuple[Key, ...] = (
    # FR-049 — no default, Q-10.
    Key("SANDBOX_MEMORY_MAX", Kind.BYTES_SIZE, "FR-049",
        "memory.max on the session cgroup", no_default_reason=_NO_DEFAULT_BOUND),
    Key("SANDBOX_CPU_MAX", Kind.CPU_QUOTA, "FR-049",
        "cpu.max as a rate — quota over period, protects the co-located host",
        no_default_reason=_NO_DEFAULT_BOUND),
    Key("SANDBOX_CPU_TOTAL", Kind.FLOAT, "FR-049",
        "cumulative CPU-seconds ceiling watched against cpu.stat",
        no_default_reason=_NO_DEFAULT_BOUND),
    Key("SANDBOX_PIDS_MAX", Kind.INT, "FR-049",
        "pids.max — an addition beyond FR-049, marked as one; a fork bomb is "
        "the cheapest defeat of SC-023's co-located-workload clause",
        no_default_reason=_NO_DEFAULT_BOUND),
    # FR-005 — no default, extended to take Q-10's treatment.
    Key("SESSION_CEILING_SPEND_USD", Kind.FLOAT, "FR-005",
        "spend ceiling", no_default_reason=_NO_DEFAULT_CEILING),
    Key("SESSION_CEILING_TOKENS", Kind.INT, "FR-005",
        "token-consumption ceiling", no_default_reason=_NO_DEFAULT_CEILING),
    Key("SESSION_CEILING_WALL_CLOCK_SECONDS", Kind.FLOAT, "FR-005",
        "wall-clock ceiling", no_default_reason=_NO_DEFAULT_CEILING),
    Key("SESSION_CEILING_TURNS", Kind.INT, "FR-005",
        "turn ceiling", no_default_reason=_NO_DEFAULT_CEILING),
    # Paths and identity.
    Key("F2A_STATE_DIR", Kind.PATH, "FR-033",
        "directory holding the session table and the supervisor's state"),
    Key("F2A_LOCATION_SET", Kind.PATH, "FR-048",
        "the declared filesystem location set, stated positively"),
    Key("F2A_TENANT_ID", Kind.STR, "FR-035", "tenant namespace, from OD-08"),
    Key("F2A_DEPLOYMENT_ID", Kind.STR, "FR-035", "admitted deployment identity"),
    # FR-043 — a stated default, marked unvalidated. Introduced by research §3.3.
    Key("CAPABILITY_LEASE_INTERVAL_SECONDS", Kind.FLOAT, "FR-050",
        "how often the supervisor renews the session lease; the residual "
        "window after a crash is one of these",
        default="5.0", unvalidated=True),
    Key("STALENESS_CEILING_SECONDS", Kind.FLOAT, "FR-047",
        "how old a served-operation set may be before it is refused. FR-047 "
        "states the default, says it is one, and binds it to FR-043",
        default="900.0", unvalidated=True),
    Key("DRIFT_CHECK_INTERVAL_SECONDS", Kind.FLOAT, "FR-028",
        "how often the drift check runs against the deployment clock",
        default="300.0", unvalidated=True),
)


_CEILING_KEYS: tuple[Key, ...] = tuple(
    key for key in SUPERVISOR_KEYS if key.name.startswith("SESSION_CEILING_")
)

_NO_DEFAULT_OPERATOR_PRICES = (
    "OD-27 states no default, on FR-058's treatment rather than FR-047's. The "
    "distinction this key exists to hold open is between *nobody was asked* "
    "and *the operator declares nothing*, and an optional key collapses them: "
    "an unset key would be the state of a deployment that never heard of the "
    "mechanism and of one that considered it and declined, which are the same "
    "two readings `spend_usd: float | None` separates one layer down. Set it "
    "to a declaration file, or to the literal 'none' to declare nothing."
)

_NO_DEFAULT_REPORTING_WINDOW = (
    "FR-045 states no default for the reporting window and cites Q-10 by name. "
    "An unset window is not a number nobody measured — it is a single window "
    "covering all of time, which FR-045 rules out along with 'unbounded' and "
    "'a figure this specification invented'. SC-019 is not evaluable until an "
    "operator sets it, and that is a precondition rather than a defect: a "
    "share is a share OF an interval, and an interval nobody declared makes "
    "two consecutive reports incomparable while looking identical."
)

_NO_DEFAULT_RESULT_BOUND = (
    "FR-058 states the bound is required configuration and states no default. "
    "An unset per-result bound is not a number nobody measured; it is the "
    "operative behaviour of inlining whatever the call printed, which no "
    "requirement chose."
)

RUNTIME_KEYS: tuple[Key, ...] = (
    # FR-005 — the same four keys the supervisor reads. Shared Key objects
    # rather than a second declaration: two declarations of one ceiling would
    # eventually disagree, and the disagreement would be between the process
    # that enforces the ceiling and the process that reports it.
    *_CEILING_KEYS,
    # FR-058 — no default, and the ceiling is derived rather than configured.
    Key("TOOL_RESULT_BOUND_TOKENS", Kind.INT, "FR-058",
        "the largest a single tool result may be, in tokens of the model in "
        "force. Refused above one twentieth of the context window",
        no_default_reason=_NO_DEFAULT_RESULT_BOUND),
    Key("MODEL_CONTEXT_WINDOW_TOKENS", Kind.INT, "FR-058",
        "the context window of the model in force. Not a bound in itself — it "
        "is what makes FR-058's one-twentieth ceiling computable, so a bound "
        "cannot be checked without it",
        no_default_reason=_NO_DEFAULT_RESULT_BOUND),
    Key("RESULT_RETENTION_MAX_BYTES", Kind.BYTES_SIZE, "FR-058",
        "the declared bound on the retention location a bounded result points "
        "at. Without it the reference relocates an unbounded liability from "
        "the transcript onto a disk nothing bounds",
        no_default_reason=_NO_DEFAULT_RESULT_BOUND),
    # OD-27 — no default, and 'none' is a value rather than an absence. The
    # requirement field names the authority that *states* the disposition, not
    # the treatment it borrows: the FR-049 bounds cite FR-049 though they take
    # Q-10's treatment, and the FR-005 ceilings cite FR-005 though they take
    # Q-10's rather than FR-047's. OD-27 limb ④ is what states this key is
    # required with no default; FR-058 is what OD-27 calls "the precedent in
    # shape", and it governs bounding a tool result, not pricing a model.
    # FR-037 — *"selected by configuration"*. Required with no default and
    # **no `no_default_reason`**, which is the distinction the field exists to
    # carry rather than an omission: the twelve keys that have one are keys an
    # authority ruled out a default *for*, having considered one. These two are
    # in `F2A_TENANT_ID`'s class — there is no universal value to have ruled
    # out. Without them `require_priceable` cannot be asked its question, and
    # `MODEL_CONTEXT_WINDOW_TOKENS` is a window belonging to a model nothing
    # names; OD-27's whole gate is *is the model in force priced*, and "in
    # force" has to be a thing an operator wrote down. Provider selection
    # proper is T163's; this is the address the startup gate is asked about.
    Key("MODEL_PROVIDER", Kind.STR, "FR-037",
        "which of the four SC-010 providers the runtime calls. Checked "
        "against `providers.base.PROVIDERS` at startup, so a typo is a "
        "startup failure rather than a first-turn one"),
    Key("MODEL_ID", Kind.STR, "FR-037",
        "the API identifier requests are made against — the string that "
        "reaches the vendor, and the address `require_priceable` and "
        "`costs.PRICES` are both keyed on"),
    Key("MODEL_PRICES_OPERATOR", Kind.STR, "OD-27",
        "the operator's own declared rates, for models no vendor page in "
        "`costs.PRICES` prices. A path to a declaration file, or the literal "
        "'none'. Nothing is filled in from it that the operator did not "
        "write, and a model neither this key nor the table prices fails at "
        "startup rather than at its first call",
        no_default_reason=_NO_DEFAULT_OPERATOR_PRICES),
    # FR-036 / FR-050 — one declared key for the provider plane, Kind.SECRET
    # so `load()` wraps it as T035's `Secret`. Not `ANTHROPIC_API_KEY` /
    # `OPENAI_API_KEY`: those names in the core path are provider-specific
    # behaviour in the core (FR-037). No default, and no `no_default_reason`:
    # this is `MODEL_PROVIDER`'s class — there is no universal value to have
    # ruled out. The target plane is `F2A_TARGET_CREDENTIAL` on the Go
    # enforcement point and is deliberately not in this tuple: requiring it
    # here would make the runtime hold the target credential.
    Key("F2A_PROVIDER_CREDENTIAL", Kind.SECRET, "FR-036",
        "the runtime-held model-provider credential. Not the target "
        "credential and not a session capability. Never present in the "
        "execution environment (FR-050)"),
    # FR-045 — no default, Q-10 again, and **in the runtime's container rather
    # than a fourth one**. `ANALYSIS_KEYS` exists because the runtime never
    # reads a source reference, and the test that distinction has to pass is
    # whether the process would be made to set a value it never uses. The
    # runtime is the process that *produces* the results this window counts, so
    # it fails the test in the other direction: a reporting window resolved
    # anywhere else would be a window over somebody else's traffic.
    Key("REPORTING_WINDOW_SECONDS", Kind.FLOAT, "FR-045",
        "the fixed length of the interval a not-verifiable share is a share "
        "of. Fixed rather than per-report so consecutive reports are "
        "comparable — a share over an interval the reader cannot see is a "
        "number without a denominator",
        no_default_reason=_NO_DEFAULT_REPORTING_WINDOW),
    Key("F2A_STATE_DIR", Kind.PATH, "FR-033",
        "directory holding the runtime's own store — the journal, the ledger "
        "and the ceilings. Outside the session's mount namespace"),
    Key("F2A_TENANT_ID", Kind.STR, "FR-035", "tenant namespace, from OD-08"),
    Key("F2A_DEPLOYMENT_ID", Kind.STR, "FR-035", "admitted deployment identity"),
)


#: T078, FR-057. The analysis stage's own declared keys.
#:
#: **A third tuple rather than an addition to the other two**, because the
#: containers are per-process and this key belongs to neither of those
#: processes: the supervisor never reads a source reference and the runtime
#: does not either. Adding it to `RUNTIME_KEYS` would have made every runtime
#: start require a value the runtime never uses, which is the shape of a
#: required key nobody can explain and therefore of a key that acquires a
#: default.
#:
#: `F2A_SOURCE_REF` is required with **no default** and carries no
#: `no_default_reason`, which is `F2A_TENANT_ID`'s class rather than the
#: FR-049 bounds' class: there is no universal value that was considered and
#: ruled out. There is no value at all — the repository and commit are facts
#: about the operator's deployment, and nothing could stand in for them.
ANALYSIS_KEYS: tuple[Key, ...] = (
    Key("F2A_SOURCE_REF", Kind.STR, "FR-057",
        "the repository and commit the operator asserts produced the admitted "
        "deployment, as `<repository>@<commit>`. FR-028's source clock is "
        "anchored to it. **Recorded and presented as an operator declaration "
        "and never as verified correspondence** — this key's value is not "
        "checked against anything, and nothing in v1 can check it "
        "(src/analysis/correspondence.py)"),
    Key("F2A_DEPLOYMENT_ID", Kind.STR, "FR-035", "admitted deployment identity"),
)


#: T162, FR-034. The analysis / runtime / target boundary, as three required
#: identities, even when all three run on one host.
#:
#: **A fourth tuple rather than an addition to the other three**, because
#: the containers are per-process and these keys name the boundary between
#: processes. T159/T160 consume them; `src/contracts/topology.py` is the
#: fail-loud constructor. Adding them to `RUNTIME_KEYS` would make every
#: runtime start require a listen topology the runtime does not bind
#: (OD-36: report+exit).
#:
#: `F2A_PROXY_LISTEN` is a Go env on the enforcement point — the path to
#: the target, not a fourth colocated role — and is not declared here.
#: The target identity is `F2A_PROXY_UPSTREAM_ADDR`, the name Go already
#: reads; declaring a second Python-only target key would be the duplicate
#: FR-034's check for existing keys exists to prevent.
#:
#: No default, and no `no_default_reason`: `MODEL_PROVIDER`'s class. There
#: is no universal host to have ruled out, and filling a missing analysis
#: address from the runtime's would be the co-location assumption FR-034
#: forbids.
TOPOLOGY_KEYS: tuple[Key, ...] = (
    Key("F2A_ANALYSIS_ADDR", Kind.STR, "FR-034",
        "analysis-stage identity as host:port. Required even when analysis "
        "shares a host with the runtime; a missing value is not filled from "
        "the runtime address"),
    Key("F2A_RUNTIME_ADDR", Kind.STR, "FR-034",
        "runtime identity as host:port. Required even when the runtime shares "
        "a host with analysis or the target"),
    Key("F2A_PROXY_UPSTREAM_ADDR", Kind.STR, "FR-034",
        "target identity as host:port — the same name the enforcement point "
        "already reads in Go. Not F2A_PROXY_LISTEN, which is the path to the "
        "target rather than a fourth colocated role"),
)


@dataclass(frozen=True)
class Config:
    values: Mapping[str, Any]
    unvalidated: tuple[str, ...] = field(default_factory=tuple)

    def __getitem__(self, name: str) -> Any:
        try:
            return self.values[name]
        except KeyError:
            raise ConfigError(
                f"{name} is not in the declared schema. Add it to a *_KEYS "
                "tuple rather than reading os.environ (FR-033)."
            ) from None

    def is_unvalidated(self, name: str) -> bool:
        """FR-043 — must be answerable by every surface that emits the value."""
        return name in self.unvalidated

    def raw(self, name: str) -> Any:
        """The bare value, marking stripped. An explicit, greppable act.

        Every FR-043 value comes out of `__getitem__` wrapped, so a surface
        that emits `config[name]` emits it marked. Reaching the underlying
        number is possible — these are configuration and have to be compared —
        but it is written down, which is the whole difference between an
        omission and a decision.
        """
        value = self[name]
        return value.value if isinstance(value, Unvalidated) else value

    def marked_values(self) -> dict[str, Any]:
        """Every FR-043 value, in the shape an external surface emits."""
        return {
            name: self.values[name].marked_record()
            for name in self.unvalidated
            if isinstance(self.values[name], Unvalidated)
        }


def load(keys: tuple[Key, ...], env: Mapping[str, str] | None = None) -> Config:
    """Resolve every declared key, or raise naming every problem at once.

    All problems are reported together. An operator who fixes one key and
    restarts to find a second is being made to discover the schema one failure
    at a time, which is a worse experience than the one FR-033 asks for.
    """
    source = os.environ if env is None else env
    resolved: dict[str, Any] = {}
    unvalidated: list[str] = []
    missing: list[Key] = []
    invalid: list[tuple[Key, str]] = []

    for key in keys:
        raw = source.get(key.name)
        if raw is None or raw == "":
            if key.default is None:
                missing.append(key)
                continue
            raw = key.default
        if key.kind is Kind.SECRET:
            resolved[key.name] = Secret(raw, name=key.name)
        else:
            try:
                resolved[key.name] = _PARSERS[key.kind](raw)
            except (ValueError, TypeError) as exc:
                # `raw` is not echoed for a SECRET key; for the rest the value
                # is configuration and printing it helps.
                invalid.append((key, str(exc)))
                continue
        if key.unvalidated:
            unvalidated.append(key.name)
            # FR-043: the marking travels WITH the value, not beside it in a
            # list a surface has to remember to consult. `Config.raw()` is the
            # explicit way to get the bare number.
            resolved[key.name] = mark(key.name, resolved[key.name])

    if missing or invalid:
        raise ConfigError(_report(missing, invalid))
    return Config(values=resolved, unvalidated=tuple(unvalidated))


def _report(missing: list[Key], invalid: list[tuple[Key, str]]) -> str:
    lines = ["Configuration is incomplete. Nothing has been started.", ""]
    if missing:
        lines.append(f"  {len(missing)} required value(s) unset:")
        for key in missing:
            lines.append(f"    - {key.name}  ({key.requirement}) — {key.purpose}")
            if key.no_default_reason:
                lines.append(f"        no default, and deliberately so: "
                             f"{key.no_default_reason}")
        lines.append("")
    if invalid:
        lines.append(f"  {len(invalid)} value(s) malformed:")
        for key, why in invalid:
            lines.append(f"    - {key.name}  ({key.requirement}): {why}")
        lines.append("")
    lines.append(
        "  No value above is filled from a default. FR-005 and FR-049 state "
        "none, and Q-10 was accepted as recommended."
    )
    return "\n".join(lines)
