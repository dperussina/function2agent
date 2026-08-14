"""T119 — `codegraph` is invoked as a subprocess, at analysis time, and nowhere else.

**Requirement**: T-11 and **D-14**. D-14 decided the analysis layer reads
`codegraph`'s SQLite artifact directly rather than going through its TypeScript
API, which makes `codegraph` a *build-time producer of a file* and not a library.
T-11 is the run-time bundle we author. Put together they give this task its two
halves, and the second half is the one a test has to hold:

1. `codegraph` is invoked **as a subprocess**, at analysis time.
2. It is **absent from every run-time image**.

## Why every test here injects the subprocess boundary

`examples/codegraph` is a git-ignored vendored TypeScript tree, and building it
needs `npm install`, which reaches the network. A test that shelled out to a
real `codegraph` would therefore skip on every machine that has not built one —
and a test that silently skips is the vacuity pattern this repository has
hardened repeatedly against. So `index_repository` takes its runner as an
argument and every arm below supplies a fake one. What is under test is *this
module's* contract with a subprocess, which is the part we wrote; whether
upstream's indexer works is upstream's business and is pinned, not tested, here.

The consequence is stated rather than hidden: **nothing in this file establishes
that a real `codegraph` invocation succeeds.** The argv is asserted against the
recipe in `specs/001-discovery-validation/harness/recall-adk-fastapi/run.sh`,
which is the committed procedure that did produce one.
"""

from __future__ import annotations

import ast
import re
import sqlite3
from pathlib import Path

import pytest

from src.analysis import codegraph
from src.analysis.codegraph_pin import CodegraphPinError

REPO = Path(__file__).resolve().parent.parent.parent
SCHEMA_SQL = REPO / "tests" / "fixtures" / "codegraph-schema" / "schema.sql"


def _real_schema_db(directory: Path) -> Path:
    """A zero-row database at the pinned revision's schema.

    Digests identically to the 149 MB index the constant was read from — that
    equivalence is `tests/unit/test_codegraph_pin.py`'s, established there and
    relied on here.
    """
    db = directory / ".codegraph" / "codegraph.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db)
    try:
        conn.executescript(SCHEMA_SQL.read_text())
        conn.commit()
    finally:
        conn.close()
    return db


class FakeRunner:
    """Records the invocation and materialises whatever artifact it is told to."""

    def __init__(self, *, returncode: int = 0, stderr: str = "", produce=None):
        self.returncode = returncode
        self.stderr = stderr
        self.produce = produce
        self.calls: list[codegraph.Invocation] = []

    def __call__(self, invocation: codegraph.Invocation) -> codegraph.CompletedInvocation:
        self.calls.append(invocation)
        if self.produce is not None:
            self.produce(Path(invocation.cwd))
        return codegraph.CompletedInvocation(
            returncode=self.returncode, stdout="", stderr=self.stderr
        )


# ---------------------------------------------------------------------------
# The invocation itself.


def test_the_repository_is_indexed_through_the_injected_runner(tmp_path) -> None:
    runner = FakeRunner(produce=_real_schema_db)
    index = codegraph.index_repository(tmp_path, runner=runner)

    assert len(runner.calls) == 1, "the indexer must be invoked exactly once"
    assert index.db_path == tmp_path / codegraph.CODEGRAPH_DB_RELPATH
    assert index.digest.digest == codegraph.pin.CODEGRAPH_SCHEMA_SHA256


def test_the_argv_names_the_indexing_subcommand_and_the_repository(tmp_path) -> None:
    """The recipe's shape, so a reader can compare this to the committed run.sh."""
    runner = FakeRunner(produce=_real_schema_db)
    codegraph.index_repository(tmp_path, runner=runner)

    argv = runner.calls[0].argv
    assert argv[-1] == str(tmp_path), "the repository is the final argument"
    assert "init" in argv, (
        "the harness recipe runs `codegraph init <repo>`; a different "
        "subcommand produces a different artifact or none"
    )
    assert Path(runner.calls[0].cwd) == tmp_path


def test_a_failing_indexer_stops_the_stage_and_carries_its_stderr(tmp_path) -> None:
    runner = FakeRunner(returncode=2, stderr="ENOENT: no such file")
    with pytest.raises(codegraph.CodegraphInvocationError) as excinfo:
        codegraph.index_repository(tmp_path, runner=runner)

    assert "ENOENT: no such file" in str(excinfo.value), (
        "a subprocess failure whose stderr is discarded is unactionable"
    )
    assert "exit status 2" in str(excinfo.value)


def test_a_successful_run_that_produced_no_artifact_is_a_failure(tmp_path) -> None:
    """rc == 0 and no database is the silent case, and it must not be silent."""
    runner = FakeRunner()  # produces nothing
    with pytest.raises(codegraph.CodegraphInvocationError) as excinfo:
        codegraph.index_repository(tmp_path, runner=runner)

    assert "reported success" in str(excinfo.value)
    assert str(codegraph.CODEGRAPH_DB_RELPATH) in str(excinfo.value)


# ---------------------------------------------------------------------------
# The pin is asserted before the artifact is read. T136 states the same
# property at contract level; this is the unit-level arm.


def test_the_schema_pin_is_asserted_before_the_index_is_returned(tmp_path) -> None:
    def wrong_schema(directory: Path) -> Path:
        db = directory / ".codegraph" / "codegraph.db"
        db.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(db)
        conn.execute("CREATE TABLE nodes (id INTEGER PRIMARY KEY)")
        conn.commit()
        conn.close()
        return db

    runner = FakeRunner(produce=wrong_schema)
    with pytest.raises(CodegraphPinError):
        codegraph.index_repository(tmp_path, runner=runner)


def test_an_index_cannot_be_constructed_around_an_unverified_artifact(tmp_path) -> None:
    """The digest is a field, so the type cannot hold an unchecked artifact."""
    db = _real_schema_db(tmp_path)
    index = codegraph.CodegraphIndex.verified(db)
    assert index.digest.version == codegraph.pin.CODEGRAPH_VERSION

    other = tmp_path / "empty.db"
    sqlite3.connect(other).close()
    with pytest.raises(CodegraphPinError):
        codegraph.CodegraphIndex.verified(other)


# ---------------------------------------------------------------------------
# "at analysis time only, absent from every run-time image"


RUNTIME_TREES = ("src/runtime", "src/supervisor", "src/sandbox", "src/proxy")


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module)
            names.update(f"{node.module}.{a.name}" for a in node.names)
    return names


def importers_of_the_analysis_indexer(root: Path, target="src.analysis.codegraph") -> list[str]:
    """Every run-time module with an import edge to the indexer."""
    found: list[str] = []
    for tree in RUNTIME_TREES:
        for path in sorted((root / tree).rglob("*.py")):
            for imported in sorted(_imported_modules(path)):
                if imported == target or imported.startswith(target + "."):
                    found.append(f"{path.relative_to(root).as_posix()} imports {imported}")
    return found


def test_no_run_time_module_imports_the_indexer() -> None:
    edges = importers_of_the_analysis_indexer(REPO)
    assert edges == [], (
        "T119: `codegraph` is invoked at analysis time only. A run-time module "
        "importing the indexer puts a TypeScript build in the serving path:\n  "
        + "\n  ".join(edges)
    )


def test_the_import_scan_fires_on_a_planted_edge(tmp_path) -> None:
    """Without this the scan would report a clean graph over an emptied table."""
    planted = tmp_path / "src" / "runtime"
    planted.mkdir(parents=True)
    (planted / "leak.py").write_text("from src.analysis.codegraph import index_repository\n")
    for tree in ("src/supervisor", "src/sandbox", "src/proxy"):
        (tmp_path / tree).mkdir(parents=True)

    edges = importers_of_the_analysis_indexer(tmp_path)
    assert edges == [
        "src/runtime/leak.py imports src.analysis.codegraph",
        "src/runtime/leak.py imports src.analysis.codegraph.index_repository",
    ], "a `from X import Y` edge is reported as both the module and the symbol"


def test_the_import_scan_does_not_fire_on_the_pin_module(tmp_path) -> None:
    """`codegraph_pin` is Phase 1's and is legitimately reachable.

    Without this arm a prefix match on `src.analysis.codegraph` would forbid the
    pin as well, and the test would be enforcing something T119 does not say.
    """
    for tree in RUNTIME_TREES:
        (tmp_path / tree).mkdir(parents=True)
    (tmp_path / "src" / "runtime" / "ok.py").write_text(
        "from src.analysis.codegraph_pin import verify\n"
    )
    assert importers_of_the_analysis_indexer(tmp_path) == []


JS_TOOLCHAIN = ("nodejs", "node", "npm", "yarn", "pnpm", "codegraph")


def javascript_toolchain_mentions(text: str) -> list[str]:
    """Every place a Dockerfile brings a JavaScript toolchain *in*.

    Removal is excluded deliberately rather than by accident: `sandbox.Dockerfile`
    already does `rm -rf /root/.npmrc`, and a scan that counted that as a
    mention would be a scan nobody could keep green, which is how a check gets
    deleted. Segments are split on the shell's own separators and any segment
    whose command is `rm` is dropped.
    """
    found: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        for segment in re.split(r"&&|\|\||;", line):
            words = segment.replace("\\", " ").split()
            if not words or words[0] == "rm":
                continue
            for word in words:
                token = word.strip("/'\"").lower()
                base = token.rsplit("/", 1)[-1].lstrip(".")
                if base in JS_TOOLCHAIN or token in JS_TOOLCHAIN:
                    found.append(f"{line}  ->  {word}")
    return found


RUNTIME_IMAGES = (
    REPO / "deploy" / "images" / "sandbox.Dockerfile",
    REPO / "deploy" / "images" / "runtime.Dockerfile",
    REPO / "deploy" / "images" / "supervisor.Dockerfile",
    REPO / "deploy" / "images" / "enforcement.Dockerfile",
)


def test_run_time_images_carry_no_javascript_toolchain() -> None:
    """T119: codegraph is an analysis-time producer, absent from run-time images.

    Analysis may grow a JavaScript toolchain when the git-ignored pin is
    bundleable; these four may not. The named set is the population: a
    silent shrink is a new run-time image shipping a toolchain un-scanned.
    """
    assert len(RUNTIME_IMAGES) >= 4
    names = {path.name for path in RUNTIME_IMAGES}
    assert names == {
        "sandbox.Dockerfile",
        "runtime.Dockerfile",
        "supervisor.Dockerfile",
        "enforcement.Dockerfile",
    }
    offenders: list[str] = []
    for path in RUNTIME_IMAGES:
        mentions = javascript_toolchain_mentions(path.read_text())
        if mentions:
            offenders.append(f"{path.name}:\n  " + "\n  ".join(mentions))
    assert offenders == [], (
        "T119: `codegraph` is an analysis-time producer and must be absent "
        "from every run-time image:\n" + "\n".join(offenders)
    )


def test_the_sandbox_image_carries_no_javascript_toolchain() -> None:
    """Kept as the original named node so T119's removal proof still resolves."""
    text = (REPO / "deploy" / "images" / "sandbox.Dockerfile").read_text()
    mentions = javascript_toolchain_mentions(text)
    assert mentions == [], (
        "T119: `codegraph` is an analysis-time producer and must be absent "
        "from every run-time image, but the sandbox image brings a JavaScript "
        "toolchain in:\n  " + "\n  ".join(mentions)
    )


def test_the_image_scan_fires_on_a_planted_install() -> None:
    """A scan that excuses removal could excuse everything; this pins the line."""
    planted = (
        "FROM python:3.12-slim-bookworm AS sandbox\n"
        "RUN apt-get update && apt-get install -y nodejs npm\n"
        "RUN rm -rf /root/.npmrc\n"
    )
    mentions = javascript_toolchain_mentions(planted)
    assert len(mentions) == 2, mentions
    assert all("rm -rf" not in m for m in mentions), (
        "the removal line must stay excused, or the real image cannot pass"
    )


def test_the_module_makes_no_subprocess_call_outside_the_injected_boundary() -> None:
    """The boundary is the mechanism; a second call site would route around it."""
    tree = ast.parse((REPO / "src" / "analysis" / "codegraph.py").read_text())
    default_runner = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == codegraph._DEFAULT_RUNNER_NAME
    ]
    assert len(default_runner) == 1, "the default runner must be exactly one function"

    inside = {id(n) for n in ast.walk(default_runner[0])}
    stray = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Name)
        and node.id == "subprocess"
        and id(node) not in inside
    ]
    assert stray == [], (
        "T119: every subprocess call goes through the injected runner. A second "
        "call site makes the boundary advisory, and the tests that rely on it "
        "stop covering the path that runs in production"
    )
