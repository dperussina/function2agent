"""T168 — no operator-specific path, hostname, address or credential in
emitted artifacts (FR-033).

FR-033's second sentence: *No operator-specific path, hostname, address or
credential MAY be written into any emitted artifact.* Configuration reaches
the system by environment injection; that is T032 / T211. This file is the
portability half.

**This is a walk of the writers, not a second redaction filter.** `Secret`
already redacts, and FR-055 already moves hostname-shaped values out of a
hashed payload (then the artifact store discards the envelope's context). A
scan of stored bytes therefore cannot see a writer that interpolates
`socket.gethostname()` into a document and then hands it to `wrap`. The
check is: do the modules that actually emit — traces, journals, results,
decision logs, operator reports — call `os.getcwd()`, `socket.gethostname()`,
a home directory, or `Secret.reveal()` / `Secret.Reveal()` while building a
record.

Dated measurement records that correctly name a CI kernel or a Darwin host
as the machine that produced a figure are frozen dated records, not this
defect, and stay off the walk.
"""

from __future__ import annotations

import ast
import json
import re
import socket
from pathlib import Path

from src.analysis.admission import check
from src.analysis.admission_record import record
from src.analysis.artifact_store import ArtifactStore
from src.contracts.ownership import ROLE_ANALYSIS
from src.contracts.repository import Repository
from tests.fixtures.admission import load_cases

REPO = Path(__file__).resolve().parents[2]

#: Product writers that persist or emit a record. The list is the population,
#: not an example: a silent shrink is the walk passing over nothing. Entry
#: points that *echo declared configuration* back to the operator who just
#: set it (readiness lines) are not writers of portable artifacts.
WRITERS: tuple[Path, ...] = (
    Path("src/contracts/operator_log.py"),
    Path("src/runtime/journal.py"),
    Path("src/runtime/trace.py"),
    Path("src/runtime/events.py"),
    Path("src/runtime/reports/not_verifiable.py"),
    Path("src/runtime/turn.py"),
    Path("src/runtime/proxy_ingest.py"),
    Path("src/contracts/result.py"),
    Path("src/analysis/admission_record.py"),
    Path("src/supervisor/fs_decisions.py"),
    Path("src/proxy/decisionlog.go"),
)

NAMED_WRITERS = frozenset({
    "src/contracts/operator_log.py",
    "src/runtime/journal.py",
    "src/runtime/trace.py",
    "src/proxy/decisionlog.go",
})

#: Last component of a Call that fetches operator identity. `home` is only a
#: leak as `Path.home()` — a field named `home` is not.
_FORBIDDEN_CALL_ATTRS = frozenset({
    "getcwd",
    "gethostname",
    "expanduser",
    "reveal",
    "Reveal",
    "Hostname",
    "Getwd",
    "UserHomeDir",
})

_GO_CALLS = (
    "os.Hostname(",
    "os.Getwd(",
    "os.UserHomeDir(",
    'os.Getenv("HOME")',
    "os.Getenv(`HOME`)",
    ".Reveal(",
)

_GO_LINE_COMMENT = re.compile(r"//.*?$", re.M)
_GO_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.S)

_OPERATOR_HOME = re.compile(r"/Users/[A-Za-z]|/home/[a-z]")


def _call_attr(node: ast.AST) -> str | None:
    if not isinstance(node, ast.Call):
        return None
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _first_str_arg(node: ast.Call) -> str | None:
    if not node.args:
        return None
    arg = node.args[0]
    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
        return arg.value
    return None


def _is_environ(node: ast.AST) -> bool:
    if isinstance(node, ast.Name) and node.id == "environ":
        return True
    return isinstance(node, ast.Attribute) and node.attr == "environ"


def python_leaks(source: str) -> list[str]:
    """Operator-identity interpolations in Python *code*, not in prose.

    A substring scan would trip on a docstring explaining why the writer
    does not call `socket.gethostname()`, which is the opposite of a check.
    """
    tree = ast.parse(source)
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            attr = _call_attr(node)
            if attr in _FORBIDDEN_CALL_ATTRS or attr == "home":
                found.append(attr)
            elif attr in {"getenv", "get"} and _first_str_arg(node) == "HOME":
                if attr == "get" and not (
                    isinstance(node.func, ast.Attribute)
                    and _is_environ(node.func.value)
                ):
                    continue
                found.append("HOME")
        elif isinstance(node, ast.Subscript) and _is_environ(node.value):
            sl = node.slice
            if isinstance(sl, ast.Constant) and sl.value == "HOME":
                found.append("HOME")
    return found


def _go_code(source: str) -> str:
    stripped = _GO_BLOCK_COMMENT.sub("", source)
    return _GO_LINE_COMMENT.sub("", stripped)


def go_leaks(source: str) -> list[str]:
    """Call-shaped leaks in Go, after comments are stripped.

    `.Fingerprint(` is the permitted form of identifying a credential on a
    decision record; `.Reveal(` is the value leaving the type.
    """
    code = _go_code(source)
    return [needle for needle in _GO_CALLS if needle in code]


def leaks_in(path: Path) -> list[str]:
    text = path.read_text()
    if path.suffix == ".go":
        return go_leaks(text)
    return python_leaks(text)


def test_the_scanner_catches_a_planted_leak() -> None:
    """The control. Without it, every 'no leaks' below is free."""
    planted_py = (
        "import os, socket\n"
        "from pathlib import Path\n"
        "def write(record, secret):\n"
        "    record['host'] = socket.gethostname()\n"
        "    record['cwd'] = os.getcwd()\n"
        "    record['home'] = Path.home()\n"
        "    record['envhome'] = os.environ['HOME']\n"
        "    record['getenv'] = os.getenv('HOME')\n"
        "    record['secret'] = secret.reveal()\n"
    )
    found = python_leaks(planted_py)
    for expected in ("gethostname", "getcwd", "home", "HOME", "reveal"):
        assert expected in found, f"the scanner misses {expected} in {found}"

    planted_go = (
        "package main\nfunc write() {\n"
        "\th, _ := os.Hostname()\n"
        "\twd, _ := os.Getwd()\n"
        "\thome, _ := os.UserHomeDir()\n"
        '\t_ = os.Getenv("HOME")\n'
        "\t_ = cred.Reveal()\n"
        "}\n"
    )
    go_found = go_leaks(planted_go)
    assert go_found, "the Go scanner misses a planted leak"
    for needle in ("os.Hostname(", "os.Getwd(", "os.UserHomeDir(",
                   'os.Getenv("HOME")', ".Reveal("):
        assert needle in go_found, f"the Go scanner misses {needle}"

    clean_py = (
        "def write(record, secret):\n"
        "    record['host'] = decided_by_host\n"
        "    record['cred'] = secret.fingerprint()\n"
    )
    assert python_leaks(clean_py) == []
    clean_go = (
        "package main\n"
        "func write(rec DecisionRecord) {\n"
        "\t_ = rec.CredentialFingerprint\n"
        "}\n"
    )
    assert go_leaks(clean_go) == []
    # Prose that names the prohibition is not a leak.
    assert python_leaks(
        '"""Do not call socket.gethostname() or Secret.reveal()."""\n'
        "def write(record):\n    record['kind'] = 'span'\n"
    ) == []
    assert go_leaks(
        "package main\n// Do not call os.Hostname() or cred.Reveal().\n"
        "func write() {}\n"
    ) == []


def test_named_writers_are_the_population() -> None:
    """A shorter list is the walk passing over nothing."""
    relative = [path.as_posix() for path in WRITERS]
    assert len(WRITERS) >= 11, (
        f"WRITERS shrank to {len(WRITERS)}. The named population at T168 "
        "was eleven emit paths; a shorter list is the walk covering nothing."
    )
    missing = NAMED_WRITERS - set(relative)
    assert not missing, (
        "a writer FR-033 named is no longer on the walk: "
        + ", ".join(sorted(missing))
    )
    for path in WRITERS:
        assert (REPO / path).is_file(), f"{path} is gone; it was an emit path"


def test_no_writer_interpolates_operator_identity() -> None:
    """The claim. Failures name the writer and the interpolation."""
    offenders: list[str] = []
    for relative in WRITERS:
        path = REPO / relative
        found = leaks_in(path)
        if found:
            offenders.append(f"{relative}: {found}")
    assert offenders == [], (
        "writer(s) interpolate operator-specific identity into an emitted "
        "record (FR-033):\n  "
        + "\n  ".join(offenders)
        + "\nFill identity from declared configuration or a caller-supplied "
        "envelope field. Do not call os.getcwd(), socket.gethostname(), "
        "Path.home(), or Secret.reveal() while building a persisted record. "
        "Credentials already have Secret (redaction) and fingerprint "
        "(decision log); do not grow a second filter."
    )


def test_dated_records_are_outside_the_walk() -> None:
    """Frozen-sites: a correctly-scoped dated host record stays.

    Findings, research, harness results and battery figures name the
    measuring host on purpose. If one of them enters WRITERS, a true
    dated record starts failing as a portability leak.
    """
    walked = [path.as_posix() for path in WRITERS]
    leaked = [
        path
        for path in walked
        if "/findings/" in path
        or path.startswith("research/")
        or "/harness/" in path
        or path.startswith("tests/batteries/results/")
        or path.startswith("specs/001-")
    ]
    assert leaked == [], (
        "the portability walk reached a dated record:\n  "
        + "\n  ".join(leaked)
    )
    assert walked, "the walk is empty; dated-record exclusion is free"


def test_the_decision_log_fingerprints_credentials_rather_than_revealing_them() -> None:
    """Consume the existing refusal; do not duplicate Secret.

    `src/proxy/decisionlog.go` identifies a credential by truncated SHA-256
    and never by value. A walk that re-implemented redaction would pass for
    the same reason T040's first scanner did: two artifacts agreeing on a
    gap. This asserts the mechanism the log already has.
    """
    source = (REPO / "src/proxy/decisionlog.go").read_text()
    assert "CredentialFingerprint" in source
    assert "truncated SHA-256" in source
    assert ".Reveal(" not in _go_code(source)
    assert "os.Hostname(" not in _go_code(source)


def test_portable_fixtures_carry_no_operator_home() -> None:
    """Committed fixtures that claim to be portable must not pin a home.

    `tests/fixtures/README.md` is FR-053's inventory. An absolute operator
    home in one of those files makes the fixture a machine, not a fixture.
    """
    root = REPO / "tests" / "fixtures"
    offenders: list[str] = []
    scanned = 0
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix in {".sqlite3", ".pyc"}:
            continue
        scanned += 1
        text = path.read_text(errors="replace")
        if _OPERATOR_HOME.search(text):
            offenders.append(path.relative_to(REPO).as_posix())
    assert scanned >= 10, (
        f"the fixture walk covered {scanned} files; it is passing because "
        "it read almost nothing"
    )
    assert offenders == [], (
        "committed fixture(s) pin an operator home path:\n  "
        + "\n  ".join(offenders)
    )


def _store(tmp_path: Path) -> ArtifactStore:
    repository = Repository(
        tmp_path / "analysis.db", role=ROLE_ANALYSIS,
        tenant_id="t-portability", deployment_id="d-portability")
    return ArtifactStore(tmp_path, repository)


def test_an_omitted_host_is_not_filled_from_the_operator_machine(
    tmp_path, monkeypatch
) -> None:
    """The live leak this walk found, asserted over the document wrap sees.

    FR-055 moves `decided_by_host` into envelope context and the store
    discards that context, so a scan of stored bytes cannot see a default
    of `socket.gethostname()`. The canary is planted on `wrap`'s input.
    """
    seen: list[dict] = []
    import src.analysis.artifact_store as store_mod

    inner = store_mod.wrap

    def capturing_wrap(kind, document):
        seen.append(dict(document))
        return inner(kind, document)

    monkeypatch.setattr(store_mod, "wrap", capturing_wrap)
    monkeypatch.setattr(
        socket, "gethostname", lambda: "CANARY-OPERATOR-HOST.example"
    )

    case = next(c for c in load_cases() if c.expected_admitted)
    decision = check(case.response(), deployment_id="d-portability")
    record(_store(tmp_path), decision, now=1_700_000_000.0)

    assert seen, "record() did not reach wrap; this assertion would be free"
    dumped = json.dumps(seen)
    assert "CANARY-OPERATOR-HOST.example" not in dumped
    assert "decided_by_host" not in seen[0], (
        "the writer filled decided_by_host when the caller omitted it. "
        "FR-033: the portable default is to omit the field, not to stamp "
        "the operator hostname."
    )


def test_a_caller_supplied_host_still_travels_in_the_envelope(
    tmp_path, monkeypatch
) -> None:
    """FR-055 is not revoked. A fixture identity the caller named is allowed."""
    import src.analysis.artifact_store as store_mod

    seen: list[dict] = []
    inner = store_mod.wrap

    def capturing_wrap(kind, document):
        seen.append(dict(document))
        return inner(kind, document)

    monkeypatch.setattr(store_mod, "wrap", capturing_wrap)
    case = next(c for c in load_cases() if c.expected_admitted)
    decision = check(case.response(), deployment_id="d-portability")
    record(
        _store(tmp_path), decision, now=1_700_000_000.0,
        decided_by_host="runner-7",
    )
    assert seen, "record() did not reach wrap"
    assert seen[0]["decided_by_host"] == "runner-7"
