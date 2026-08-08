"""T114 — the adversarial egress battery (**SC-002**, **SC-003**), run against
the assembled enforcement point (`src/proxy`) in front of the reference
application (T116).

SC-002's clauses, and where each is scored below:

1. **zero calls that do not resolve read-only against the published
   specification reach the target** — `test_zero_calls_outside_the_read_only_set_reached_the_target`,
   scored on the *target's own record of what it served* rather than on the
   proxy's record of what it forwarded. The application appends every dispatch
   to `Application.calls`, so the oracle is downstream of the thing under test.
2. **100% of the refusals state the rule that produced them** —
   `test_every_recorded_denial_states_its_rule`, read out of the enforcement
   point's own decision database, whose `rule_id` column carries a
   `CHECK (length(rule_id) > 0)`.

SC-003's clauses:

3. **zero requests are allowed whose method could not be read** —
   `test_no_unreadable_method_was_allowed`, over the raw-socket arms that put
   an unparseable, lowercased or absolute-form request line on the wire.
4. **zero outbound connections leave for a destination outside the pinned
   set** — `test_a_self_composed_connection_reaches_nothing`, which puts a
   prober in an empty network namespace and has it dial a listener that is
   demonstrably reachable from outside it.

## THE VACUITY THIS FILE IS BUILT AROUND

**A battery asserting "zero writes reached the target" passes trivially if
nothing ever attempted a write.** That is this corpus's most-repeated failure
mode and the experiment-design skill's Rule 8 in its exact shape: the positive
result is a *failure to succeed*, and every way the instrument can break
produces the same reading — a proxy that refuses everything, an arm table that
is never walked, a detector that matches nothing.

So each half runs its detector over **two arms differing in one variable**:

| Half | Variable | Battery arm | Positive control arm |
|---|---|---|---|
| SC-002 | whether the request passes through the enforcement point | through the proxy → zero non-read-only calls reach the target | **straight at the origin** → `POST /shipments/S-0001/cancel` reaches it, and is caught **by operation** |
| SC-003 | whether the prober is in the empty network namespace | in the namespace → nothing reachable | **in the parent namespace** → the same destination is reached, and is caught **by address** |

Both controls use the *same* detector function as the battery, not a second
one, and both write what they caught to `tests/batteries/results/`. Two further controls close the ways a
zero could still be free: `test_the_allowed_arms_reached_the_target` (the
proxy is not simply refusing everything) and `test_every_arm_actually_ran`
(the arm table was walked).

## ONE ARM THIS BATTERY CANNOT HAVE, AND WHY THAT IS THE RIGHT ANSWER

The obvious mechanism proof — widen `method_allowlist` to include `POST`, call
every operation `safe`, and require the battery to notice the write landing —
does not exist, because **the enforcement point refuses to start on that
policy**: `ParsePolicy` rejects a `method_allowlist` naming a non-safe method
outright (FR-009). The tamper therefore produces a proxy that never listens,
the fixture skips, and the proof reads `UNPROVEN` while saying nothing about
the mechanism. That is a property worth stating rather than a gap: the
configuration change most likely to produce a write is not a configuration this
component accepts.

## WHAT THIS DOES NOT MEASURE

The SC-003 half models **the sandbox's side of the topology only**: a workload
in a network namespace with no interfaces reaches nothing it composes itself.
It does **not** model the deployed shape's other half — that the enforcement
point must remain reachable over exactly one route — because that needs a
`veth` pair and a container network this repository does not yet build
(`deploy/compose/` is empty). Read the result as "self-composed connections
escape nothing", not as "the one permitted route is the only route".

## RUNNING IT

    docker run --rm --privileged -v "$PWD:/work" -w /work \\
      -e F2A_PROXY_BIN=/path/to/f2a-proxy f2a-dev \\
      .venv/bin/python -m pytest tests/batteries/test_adversarial_egress.py

The enforcement point is a Go binary. It is located from `F2A_PROXY_BIN`, else
built with `go build` when a toolchain is present, else the module **skips** —
a battery that cannot start the thing under test reports nothing, and saying so
is the only honest reading.
"""

from __future__ import annotations

import http.client
import json
import os
import re
import shutil
import socket
import ssl
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from tests.batteries.evidence import record_evidence

pytestmark = [
    pytest.mark.linux_only,
    pytest.mark.privileged,
    pytest.mark.skipif(sys.platform != "linux", reason="OD-17: Linux only"),
]

REPO = Path(__file__).resolve().parents[2]
REFAPP_DIR = REPO / "tests" / "fixtures" / "reference-app"
if str(REFAPP_DIR) not in sys.path:
    sys.path.insert(0, str(REFAPP_DIR))

if sys.platform == "linux":
    import app as refapp

    from src.supervisor._linux import CLONE_NEWNET, unshare
    from src.supervisor.session_table import SessionTable, capability_digest

CAPABILITY_HEADER = "X-F2A-Capability"
HANDLE = "cap-t114-0000000000000000"


# ---------------------------------------------------------------------------
# The detectors. One per success criterion, used by BOTH the battery arm and
# its positive control — a control scored by a second function proves that the
# second function works.
# ---------------------------------------------------------------------------


def calls_outside_the_read_only_set(calls: list[tuple[str, str]]) -> list[str]:
    """SC-002's detector: which of these calls should never have arrived.

    Resolution is against `app.ROUTES`, the reference application's own route
    table, which `served_operations.json` is reconciled against in both
    directions. A call that resolves to no operation is a violation for the
    same reason a `write` one is: the published specification does not describe
    it, so nothing established it as read-only.
    """
    found: list[str] = []
    for method, target in calls:
        path = urlsplit(target).path
        tier = _tier_of(method, path)
        if tier != refapp.READ_ONLY:
            found.append(f"{method} {target} → {tier}")
    return found


def _tier_of(method: str, path: str) -> str:
    for _op, (op_method, template, tier) in refapp.ROUTES.items():
        if method != op_method:
            continue
        parts = [re.escape(segment) for segment in re.split(r"\{[^}]+\}", template)]
        if re.fullmatch("[^/]+".join(parts), path):
            return tier
    return "unresolved"


def destinations_reached(results: list[dict[str, object]]) -> list[str]:
    """SC-003's detector: which destinations a self-composed dial actually hit."""
    return [str(r["address"]) for r in results if r["reached"]]


# ---------------------------------------------------------------------------
# The arm table
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Arm:
    label: str
    #: `None` for a raw-socket arm, which sends bytes rather than a parsed request.
    method: str | None
    target: str
    #: The literal request line for a raw arm.
    raw_line: str | None = None
    send_capability: bool = True
    expect_allowed: bool = False


ARMS: tuple[Arm, ...] = (
    # -- the workload. These MUST be served, or a zero below is the proxy
    #    refusing everything rather than refusing the right things.
    Arm("GET /parts (the workload)", "GET", "/parts", expect_allowed=True),
    Arm("GET /parts/P-0007 (the workload)", "GET", "/parts/P-0007", expect_allowed=True),
    Arm("GET /shipments (the workload)", "GET", "/shipments", expect_allowed=True),
    # -- SC-002: the one operation the reference application has that is not
    #    read-only, reached the only two ways its path can be reached.
    Arm("POST the cancel operation", "POST", "/shipments/S-0001/cancel"),
    Arm("GET the cancel path (undescribed for GET)", "GET", "/shipments/S-0001/cancel"),
    # -- SC-002: methods that are not safe, against paths that are.
    Arm("PUT a part", "PUT", "/parts/P-0007"),
    Arm("DELETE a part", "DELETE", "/parts/P-0007"),
    Arm("PATCH a part", "PATCH", "/parts/P-0007"),
    Arm("POST to the collection", "POST", "/parts"),
    # -- SC-002: an operation the published specification does not describe.
    Arm("GET an undescribed path", "GET", "/admin/dump"),
    # -- FR-050: no capability, so no session.
    Arm("GET /parts with no capability", "GET", "/parts", send_capability=False),
    Arm("GET /parts with a forged capability", "GET", "/parts", send_capability=True),
    # -- SC-003: request lines whose method cannot be read as a safe method.
    Arm("raw: a lowercased method", None, "/parts", raw_line="get /parts HTTP/1.1"),
    Arm("raw: an absolute-form target naming another origin", None,
        "http://evil.example.invalid/parts",
        raw_line="GET http://evil.example.invalid/parts HTTP/1.1"),
    Arm("raw: asterisk-form", None, "*", raw_line="OPTIONS * HTTP/1.1"),
    Arm("raw: a NUL inside the method token", None, "/parts",
        raw_line="G\x00ET /parts HTTP/1.1"),
    Arm("raw: dot-segments toward the cancel operation", None,
        "/parts/../shipments/S-0001/cancel",
        raw_line="GET /parts/../shipments/S-0001/cancel HTTP/1.1"),
    Arm("raw: a second capability header", None, "/parts",
        raw_line="GET /parts HTTP/1.1", send_capability=True),
)

#: The forged-capability arm sends a handle no session table row matches.
FORGED = "GET /parts with a forged capability"
#: The duplicate-header arm needs the header written twice.
DUPLICATED = "raw: a second capability header"


# ---------------------------------------------------------------------------
# Standing the enforcement point up
# ---------------------------------------------------------------------------


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = int(s.getsockname()[1])
    s.close()
    return port


def _issue_cert(into: Path) -> tuple[Path, Path]:
    """A self-signed leaf that is also its own root, for the pinned origin.

    Generated per run rather than committed: a trust anchor in the repository
    is a credential in the repository, and this one exists for ninety seconds.
    """
    cert, key = into / "origin-cert.pem", into / "origin-key.pem"
    proc = subprocess.run(
        ["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
         "-keyout", str(key), "-out", str(cert), "-days", "1",
         "-subj", "/CN=reference-app.invalid",
         "-addext", "subjectAltName=DNS:reference-app.invalid"],
        capture_output=True, text=True, check=False,
    )
    if proc.returncode != 0:
        pytest.skip(f"openssl could not issue a certificate: {proc.stderr[:200]}")
    return cert, key


def _serve_origin(application: object, cert: Path, key: Path) -> tuple[object, int]:
    port = _free_port()
    server = refapp.build_server(application, host="127.0.0.1", port=port)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(str(cert), str(key))
    server.socket = ctx.wrap_socket(server.socket, server_side=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, port


def _write_policy(into: Path) -> Path:
    """The egress policy, derived from the application's published surface.

    `safe` is `effect_tier == "read_only"` and nothing else. Writing the policy
    by hand here would let the battery pass by declaring the cancel operation
    safe, which is the failure it exists to detect.
    """
    served = json.loads((REFAPP_DIR / "served_operations.json").read_text())
    policy = {
        "schema_version": "1.0.0",
        "policy_version": "t114-battery",
        "method_allowlist": ["GET", "HEAD"],
        "served_operations": [
            {
                "operation_id": op["operation_id"],
                "method": op["method"],
                "path_template": op["path_template"],
                "safe": op["effect_tier"] == refapp.READ_ONLY,
                "rule_id": op["rule_id"],
            }
            for op in served["operations"]
        ],
        "deny_list": [],
    }
    path = into / "egress-policy.json"
    path.write_text(json.dumps(policy, indent=2))
    return path


def _admit_session(into: Path) -> Path:
    db = into / "session.sqlite3"
    with SessionTable(db) as table:
        table.create(
            session_id="s-t114",
            tenant_id="t-t114",
            deployment_id="d-reference-app",
            capability_sha256=capability_digest(HANDLE),
            lease_expires_at=time.time() + 3600,
        )
        table.mark_running("s-t114")
    return db


def _proxy_binary(into: Path) -> str:
    if (given := os.environ.get("F2A_PROXY_BIN")):
        if not Path(given).is_file():
            pytest.skip(f"F2A_PROXY_BIN={given} is not a file")
        return given
    if shutil.which("go") is None:
        pytest.skip(
            "the enforcement point is a Go binary: set F2A_PROXY_BIN or "
            "install a Go toolchain. A battery that cannot start the thing "
            "under test reports nothing."
        )
    out = str(into / "f2a-proxy")
    build = subprocess.run(
        ["go", "build", "-o", out, "."],
        cwd=str(REPO / "src" / "proxy"), capture_output=True, text=True, check=False,
    )
    if build.returncode != 0:
        pytest.skip(f"go build failed: {build.stderr[-400:]}")
    return out


@dataclass
class EnforcementPoint:
    port: int
    application: object
    origin_port: int
    decision_db: Path
    proc: subprocess.Popen


@pytest.fixture(scope="module")
def workdir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("t114")


@pytest.fixture(scope="module")
def enforcement_point(workdir: Path):
    """The assembled thing under test: proxy → pinned TLS origin → application."""
    cert, key = _issue_cert(workdir)
    application = refapp.from_committed_state()
    server, origin_port = _serve_origin(application, cert, key)
    decision_db = workdir / "egress-decision.sqlite3"
    env = dict(os.environ)
    listen = _free_port()
    env.update({
        "F2A_PROXY_LISTEN": f"127.0.0.1:{listen}",
        "F2A_PROXY_UPSTREAM_ORIGIN": f"https://reference-app.invalid:{origin_port}",
        "F2A_PROXY_UPSTREAM_ADDR": f"127.0.0.1:{origin_port}",
        "F2A_PROXY_POLICY": str(_write_policy(workdir)),
        "F2A_PROXY_SESSION_DB": str(_admit_session(workdir)),
        "F2A_PROXY_DECISION_DB": str(decision_db),
        "F2A_TARGET_CREDENTIAL_HEADER": "X-Target-Credential",
        "F2A_TARGET_CREDENTIAL": "t114-target-credential",
        "SSL_CERT_FILE": str(cert),
    })
    proc = subprocess.Popen(
        [_proxy_binary(workdir)], env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    for _ in range(100):
        if proc.poll() is not None:
            pytest.skip(f"the enforcement point exited: {proc.stdout.read()[:400]}")
        try:
            socket.create_connection(("127.0.0.1", listen), timeout=0.2).close()
            break
        except OSError:
            time.sleep(0.05)
    else:
        proc.kill()
        pytest.skip("the enforcement point never listened")
    yield EnforcementPoint(listen, application, origin_port, decision_db, proc)
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:  # pragma: no cover - defensive
        proc.kill()
    server.shutdown()


# ---------------------------------------------------------------------------
# Driving the arms
# ---------------------------------------------------------------------------


def _send_parsed(port: int, arm: Arm) -> dict[str, object]:
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    headers = {}
    if arm.send_capability:
        headers[CAPABILITY_HEADER] = "forged-" + HANDLE if arm.label == FORGED else HANDLE
    try:
        conn.request(arm.method or "GET", arm.target, headers=headers)
        resp = conn.getresponse()
        body = resp.read()
        return {
            "label": arm.label,
            "status": resp.status,
            "rule_id": resp.headers.get("X-F2A-Rule-Id", ""),
            "allowed": 200 <= resp.status < 300,
            "body": body[:200].decode("utf-8", "replace"),
        }
    finally:
        conn.close()


def _send_raw(port: int, arm: Arm) -> dict[str, object]:
    extra = f"{CAPABILITY_HEADER}: {HANDLE}\r\n"
    if arm.label == DUPLICATED:
        extra += f"{CAPABILITY_HEADER}: {HANDLE}-second\r\n"
    wire = (
        f"{arm.raw_line}\r\nHost: reference-app.invalid\r\n{extra}"
        "Connection: close\r\n\r\n"
    ).encode()
    sock = socket.create_connection(("127.0.0.1", port), timeout=10)
    sock.sendall(wire)
    buf = b""
    try:
        while chunk := sock.recv(4096):
            buf += chunk
    except OSError:
        pass
    finally:
        sock.close()
    text = buf.decode("utf-8", "replace")
    first = text.splitlines()[0] if text else "<connection closed with no response>"
    status = 0
    if (m := re.match(r"HTTP/1\.[01] (\d{3})", first)):
        status = int(m.group(1))
    rule = ""
    if (m := re.search(r"(?im)^X-F2A-Rule-Id:\s*(\S+)", text)):
        rule = m.group(1)
    return {
        "label": arm.label,
        "status": status,
        "rule_id": rule,
        "allowed": 200 <= status < 300,
        "body": text[:200],
    }


@pytest.fixture(scope="module")
def battery(enforcement_point: EnforcementPoint) -> dict[str, object]:
    outcomes = [
        _send_raw(enforcement_point.port, arm) if arm.raw_line
        else _send_parsed(enforcement_point.port, arm)
        for arm in ARMS
    ]
    time.sleep(0.3)  # the decision log is written on the proxy's own goroutine
    return {
        "outcomes": outcomes,
        "calls": list(enforcement_point.application.calls),
        "decisions": _read_decisions(enforcement_point.decision_db),
    }


def _read_decisions(path: Path) -> list[dict[str, object]]:
    import sqlite3

    if not path.exists():
        return []
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        con.row_factory = sqlite3.Row
        rows = con.execute(
            "SELECT disposition, rule_id, reason, requirement, method, path, "
            "resolved_tier FROM egress_decision ORDER BY seq"
        ).fetchall()
    finally:
        con.close()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# SC-002 — zero calls outside the read-only set reach the target
# ---------------------------------------------------------------------------


def test_every_arm_actually_ran(battery) -> None:
    """The cheapest way a zero is free: nothing was attempted."""
    assert len(battery["outcomes"]) == len(ARMS)
    assert {str(o["label"]) for o in battery["outcomes"]} == {a.label for a in ARMS}


def test_the_allowed_arms_reached_the_target(battery) -> None:
    """The negative control for a proxy that simply refuses everything.

    Without this the SC-002 zero is satisfied by a listener that closes every
    connection, which contains nothing because it serves nothing.
    """
    allowed = [o for o, a in zip(battery["outcomes"], ARMS, strict=True) if a.expect_allowed]
    assert allowed, "the arm table has no workload arm"
    for outcome in allowed:
        assert outcome["allowed"], (
            f"{outcome['label']} did not reach the target "
            f"(status {outcome['status']} rule {outcome['rule_id']!r}); "
            "the zero below would be a refusal of everything"
        )
    served = {t for _m, t in battery["calls"]}
    assert {"/parts", "/parts/P-0007", "/shipments"} <= served, (
        f"the target served {sorted(served)}"
    )


def test_zero_calls_outside_the_read_only_set_reached_the_target(battery) -> None:
    """**SC-002 clause 1**, scored on the target's own record.

    OD-24 ground ①'s companion assertion on the egress side: nothing that fails
    to resolve read-only against the published specification is served.
    """
    violations = calls_outside_the_read_only_set(battery["calls"])
    assert violations == [], (
        "the target served calls that do not resolve read-only:\n  "
        + "\n  ".join(violations)
    )


def test_every_adversarial_arm_was_refused(battery) -> None:
    """Every arm the table marks adversarial got a non-2xx and served nothing."""
    refused = [
        o for o, a in zip(battery["outcomes"], ARMS, strict=True)
        if not a.expect_allowed
    ]
    allowed_anyway = [o["label"] for o in refused if o["allowed"]]
    assert allowed_anyway == [], f"the enforcement point allowed {allowed_anyway}"


def test_every_recorded_denial_states_its_rule(battery) -> None:
    """**SC-002 clause 2**, read out of the enforcement point's decision log.

    The wire response is not the record. A request refused before its head is
    trusted gets a bare status line, and scoring the clause on response headers
    would read that as an unruled denial when the database has the rule. The
    database is where FR-011 says the disposition lives.
    """
    decisions = battery["decisions"]
    assert decisions, (
        "the decision database is empty; the rule clause cannot be scored, and "
        "an unscored clause is not a satisfied one"
    )
    unruled = [d for d in decisions if not str(d["rule_id"]).strip()]
    assert unruled == [], f"denials with no rule: {unruled}"
    denials = [d for d in decisions if d["disposition"] != "allow"]
    assert denials, "no denial was recorded, so the clause has no subject"


def test_no_unreadable_method_was_allowed(battery) -> None:
    """**SC-003 clause 2** — the raw arms, none of which may be served."""
    raw = [
        o for o, a in zip(battery["outcomes"], ARMS, strict=True) if a.raw_line
    ]
    assert len(raw) >= 5, "the raw arm set shrank"
    served = [o["label"] for o in raw if o["allowed"]]
    assert served == [], f"a request whose method could not be read was allowed: {served}"


# ---------------------------------------------------------------------------
# SC-002's POSITIVE CONTROL — the same detector, over a route that bypasses
# the enforcement point, must catch the write and name it.
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def positive_control(workdir: Path) -> dict[str, object]:
    """A command the agent composed itself, sent straight at the pinned origin.

    Its own application instance, so the battery's oracle is not polluted by a
    call the battery did not make.
    """
    control_dir = workdir / "control"
    control_dir.mkdir(exist_ok=True)
    cert, key = _issue_cert(control_dir)
    application = refapp.from_committed_state()
    server, port = _serve_origin(application, cert, key)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    conn = http.client.HTTPSConnection("127.0.0.1", port, timeout=10, context=ctx)
    conn.request("POST", "/shipments/S-0001/cancel")
    resp = conn.getresponse()
    body = json.loads(resp.read())
    conn.close()
    server.shutdown()
    return {
        "status": resp.status,
        "body": body,
        "calls": list(application.calls),
    }


def test_the_positive_control_is_caught_naming_the_operation(positive_control) -> None:
    """**Rule 8's negative control.** Without this reading, "zero calls outside
    the read-only set reached the target" and "the detector matches nothing"
    are the same output."""
    caught = calls_outside_the_read_only_set(positive_control["calls"])
    record_evidence("t114-positive-control-sc002", {
        "detector": "calls_outside_the_read_only_set(target.calls)",
        "route": "straight at the pinned origin, bypassing the enforcement point",
        "caught": caught,
        "target_calls": positive_control["calls"],
    })
    assert caught == ["POST /shipments/S-0001/cancel → write"], (
        f"the detector caught {caught}"
    )


def test_the_positive_controls_write_actually_landed(positive_control) -> None:
    """A control that was caught doing nothing proves nothing.

    The cancel operation must have changed the shipment, or the detector is
    being credited for catching a no-op.
    """
    assert positive_control["status"] == 200, positive_control
    shipment = positive_control["body"]["shipment"]
    assert shipment["status"] == "cancelled", shipment


def test_the_battery_refuses_exactly_where_the_control_succeeds(
    battery, positive_control
) -> None:
    """One variable moved: whether the request passed through the enforcement
    point. The same operation, the same target, opposite outcomes."""
    through_proxy = [
        o for o, a in zip(battery["outcomes"], ARMS, strict=True)
        if a.method == "POST" and a.target == "/shipments/S-0001/cancel"
    ]
    assert len(through_proxy) == 1
    assert not through_proxy[0]["allowed"], through_proxy[0]
    assert positive_control["status"] == 200
    assert ("POST", "/shipments/S-0001/cancel") not in battery["calls"]
    assert ("POST", "/shipments/S-0001/cancel") in positive_control["calls"]


# ---------------------------------------------------------------------------
# SC-003 — a connection the workload composes itself reaches nothing
# ---------------------------------------------------------------------------


def _routable_address() -> str:
    """The address this host would use to leave the loopback interface."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("192.0.2.1", 9))  # TEST-NET-1, no packet is sent
        return str(sock.getsockname()[0])
    except OSError:  # pragma: no cover - a host with no route at all
        pytest.skip("this host has no non-loopback route, so there is nothing to escape to")
    finally:
        sock.close()


def _probe(addresses: list[tuple[str, int]], *, isolate: bool) -> list[dict[str, object]]:
    """Dial each address from a forked child, optionally in an empty netns.

    Forked rather than threaded because `unshare(CLONE_NEWNET)` is
    process-wide: doing it in-process would take the test runner's own network
    away. `isolate` is the single variable between the battery and its control.
    """
    read_fd, write_fd = os.pipe()
    pid = os.fork()
    if pid == 0:  # pragma: no cover - the child never returns
        os.close(read_fd)
        try:
            if isolate:
                unshare(CLONE_NEWNET)
            out = []
            for host, port in addresses:
                entry: dict[str, object] = {"address": f"{host}:{port}"}
                try:
                    socket.create_connection((host, port), timeout=2).close()
                    entry["reached"] = True
                    entry["errno"] = ""
                except OSError as exc:
                    entry["reached"] = False
                    entry["errno"] = str(exc)
                out.append(entry)
            os.write(write_fd, json.dumps(out).encode())
        except BaseException as exc:
            os.write(write_fd, json.dumps({"error": repr(exc)}).encode())
        finally:
            os.close(write_fd)
            os._exit(0)
    os.close(write_fd)
    chunks = []
    while chunk := os.read(read_fd, 65536):
        chunks.append(chunk)
    os.close(read_fd)
    os.waitpid(pid, 0)
    payload = json.loads(b"".join(chunks) or b"[]")
    if isinstance(payload, dict):
        pytest.fail(f"the prober failed before dialling: {payload['error']}")
    return payload


@pytest.fixture(scope="module")
def escape_target():
    """A listener on this host's routable address — a real destination."""
    host = _routable_address()
    server = socket.socket()
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((host, 0))
    server.listen(8)
    port = int(server.getsockname()[1])
    stop = threading.Event()

    def accept_loop() -> None:
        server.settimeout(0.2)
        while not stop.is_set():
            try:
                server.accept()[0].close()
            except (TimeoutError, OSError):
                continue

    thread = threading.Thread(target=accept_loop, daemon=True)
    thread.start()
    yield (host, port)
    stop.set()
    thread.join(timeout=2)
    server.close()


def test_a_self_composed_connection_reaches_nothing(escape_target) -> None:
    """**SC-003 clause 1** — from an empty network namespace, no destination."""
    results = _probe([escape_target, ("127.0.0.1", escape_target[1])], isolate=True)
    reached = destinations_reached(results)
    assert reached == [], f"a self-composed connection reached {reached}"


def test_the_escape_target_is_reachable_without_the_namespace(escape_target) -> None:
    """**Rule 8's negative control for SC-003.** One variable — the namespace.

    Without this reading, "reached nothing" and "the listener was never up" are
    the same output.
    """
    results = _probe([escape_target], isolate=False)
    reached = destinations_reached(results)
    record_evidence("t114-positive-control-sc003", {
        "detector": "destinations_reached(prober_results)",
        "variable": "the prober is NOT in a network namespace of its own",
        "caught": reached,
        "results": results,
    })
    assert reached == [f"{escape_target[0]}:{escape_target[1]}"], (
        f"the same destination was not reachable outside the namespace: {results}"
    )
