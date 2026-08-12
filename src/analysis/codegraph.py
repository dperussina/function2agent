"""T119 — invoke `codegraph` as a subprocess, at analysis time, and nowhere else.

**Requirement**: T-11 and **D-14**.

**D-14** decided the analysis layer reads `codegraph`'s SQLite artifact directly
rather than going through its TypeScript API. That decision is what makes this
module a *subprocess* boundary rather than a client library: `codegraph` runs
once, writes `.codegraph/codegraph.db`, and everything downstream reads a file.
**T-11** is the bundle we author, and it is the reason the second half of this
task is a property of the images rather than of this file — see *The run-time
half* below.

## The pin is asserted before anything is read

`src/analysis/codegraph_pin.py` owns the version and the schema digest and it
fails closed. This module calls `verify()` on the artifact **before** it hands
back anything a caller could read, and there is no constructor for
`CodegraphIndex` that skips it. That ordering is the whole point: **U-04** says
upstream's schema carries no stability guarantee, and a renamed column arrives
as changed rows in a table we query, with nothing announcing it. A mismatch is
an upstream release and must never reach FR-028's drift channel — T136 states
that at contract level, and the pin's own error text distinguishes the two.

## Why the subprocess boundary is injected rather than called directly

`examples/codegraph` is a git-ignored vendored TypeScript tree at
`v1.5.0-7-g49c11fc`, and building it needs `npm install`, which reaches the
network. If this module called `subprocess.run` inline, every test of the
contract *we* wrote — the argv, the failure handling, the missing-artifact case,
the ordering of the pin against the read — would need a built `codegraph`, and
would therefore skip on almost every machine. A skipping test is not a weaker
test, it is no test, and this repository has hardened roughly ten instruments
against exactly that vacuity.

So `run` is a parameter. The default runner is the only site in this file that
touches `subprocess`, and `tests/unit/test_codegraph_invocation.py` scans this
module's AST to keep it that way — a second call site would route around the
boundary and quietly un-test the path that runs in production.

**What that does not establish**, said plainly because a boundary this
convenient invites over-reading: nothing in the test suite runs a real
`codegraph`. The argv below is written against the committed recipe at
`specs/001-discovery-validation/harness/recall-adk-fastapi/run.sh`, which is the
procedure that produced the artifact the pinned digest was read from. That
recipe is the evidence; these tests are evidence about our half of the contract.

## The run-time half — "absent from every run-time image"

`codegraph` is a Node program and this is a Python module, so "absent" is a
property of two things, and neither of them is a comment here:

- **No run-time module imports this one.** `src/runtime`, `src/supervisor`,
  `src/sandbox` and `src/proxy` are scanned for an import edge to
  `src.analysis.codegraph`, and a planted edge is asserted to be reported.
- **The sandbox image carries no JavaScript toolchain.** An image with no node
  and no npm cannot run `codegraph` whatever this code says. That is the same
  construction `deploy/images/sandbox.Dockerfile` already uses for package
  indexes: the image removes the *means*, the egress policy denies the
  *request*, and neither is asked to be the other.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from src.analysis import codegraph_pin as pin
from src.analysis.codegraph_pin import CodegraphPinError, SchemaDigest

__all__ = [
    "CODEGRAPH_DB_RELPATH",
    "CodegraphIndex",
    "CodegraphInvocationError",
    "CompletedInvocation",
    "Invocation",
    "index_repository",
]

# Where upstream writes its artifact, relative to the indexed repository. Read
# off the committed recipe rather than chosen: `run.sh` reads
# `<repo>/.codegraph/codegraph.db` after `codegraph init`.
CODEGRAPH_DB_RELPATH = Path(".codegraph") / "codegraph.db"

# The subcommand the recipe runs. Named as a constant because the artifact's
# shape is a function of it — a different subcommand produces a different
# database, or none, and the pinned digest would then be asserted against
# something it was never observed over.
CODEGRAPH_SUBCOMMAND = "init"

_DEFAULT_BIN = "codegraph"

# The AST scan in the test file looks this function up by name. Keeping the name
# in a constant means renaming the function cannot silently disarm the scan.
_DEFAULT_RUNNER_NAME = "_run_subprocess"


class CodegraphInvocationError(RuntimeError):
    """The indexer did not produce a readable artifact. Never a drift signal."""


@dataclass(frozen=True)
class Invocation:
    """What is about to be executed. Data, so a test can assert on it."""

    argv: tuple[str, ...]
    cwd: str


@dataclass(frozen=True)
class CompletedInvocation:
    returncode: int
    stdout: str
    stderr: str


Runner = Callable[[Invocation], CompletedInvocation]


def _run_subprocess(invocation: Invocation) -> CompletedInvocation:  # pragma: no cover
    """The only site in this module that touches `subprocess`.

    Uncovered on purpose and marked as such: running it requires a built
    `codegraph`, which requires `npm install`, which reaches the network. The
    contract around it is covered; this three-line body is not, and pretending
    otherwise with a mock of `subprocess.run` would test `unittest.mock`.
    """
    completed = subprocess.run(
        list(invocation.argv),
        cwd=invocation.cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    return CompletedInvocation(
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


@dataclass(frozen=True)
class CodegraphIndex:
    """A `codegraph` artifact whose schema has been asserted against the pin.

    `digest` is a field rather than a method, and `verified` is the only
    constructor, so there is no value of this type that holds an unchecked
    artifact. That is the same construction `src/contracts/result.py` uses to
    keep a result from existing without a verification outcome: a check that can
    be skipped is a check that will be.
    """

    db_path: Path
    digest: SchemaDigest

    @classmethod
    def verified(cls, db_path: str | Path) -> "CodegraphIndex":
        """Assert the pin, then admit the artifact. Raises `CodegraphPinError`."""
        path = Path(db_path)
        return cls(db_path=path, digest=pin.verify(path))


def build_invocation(
    repository: str | Path, *, codegraph_bin: str = _DEFAULT_BIN
) -> Invocation:
    """The argv, as data, separated from running it so a test can read it."""
    repo = Path(repository)
    return Invocation(
        argv=(codegraph_bin, CODEGRAPH_SUBCOMMAND, str(repo)),
        cwd=str(repo),
    )


def index_repository(
    repository: str | Path,
    *,
    runner: Runner | None = None,
    codegraph_bin: str = _DEFAULT_BIN,
) -> CodegraphIndex:
    """Index `repository` and return an artifact whose schema matches the pin.

    Three refusals, and the third is the one that would otherwise be silent:

    - a non-zero exit status, carrying the indexer's own stderr, because a
      subprocess failure whose stderr is discarded is unactionable;
    - a **successful** exit with no artifact, which is the case a `returncode`
      check alone reads as fine;
    - a schema that is not the pinned one, which raises `CodegraphPinError`
      from `verify()` and stops the analysis stage. That is an upstream release
      and it must never be emitted as source drift (**U-04**, T136).
    """
    run = runner if runner is not None else _run_subprocess
    invocation = build_invocation(repository, codegraph_bin=codegraph_bin)

    completed = run(invocation)
    if completed.returncode != 0:
        raise CodegraphInvocationError(
            f"codegraph exit status {completed.returncode} — the analysis "
            "stage stops here.\n"
            f"  argv   : {' '.join(invocation.argv)}\n"
            f"  cwd    : {invocation.cwd}\n"
            f"  stderr : {completed.stderr.strip() or '<empty>'}"
        )

    db_path = Path(repository) / CODEGRAPH_DB_RELPATH
    if not db_path.is_file():
        raise CodegraphInvocationError(
            "codegraph reported success and produced no artifact.\n"
            f"  expected: {CODEGRAPH_DB_RELPATH}\n"
            f"  under   : {Path(repository)}\n"
            "  A zero exit status with no database is not a successful "
            "analysis; the stage stops rather than reading an absent index."
        )

    return CodegraphIndex.verified(db_path)


__pin_error__ = CodegraphPinError  # re-exported for callers that catch both
