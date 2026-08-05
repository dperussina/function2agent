"""lifecycle-taxonomy — the specified terminal states are the implemented ones.

**Another instance of the class this directory keeps naming**: a claim about
an artifact that lives in a different file from the artifact, so no reviewer of
the change that invalidated it ever sees it. Here the claim is
`data-model.md` §2.1's session lifecycle and the artifact is `TAXONOMY` in
`src/contracts/terminal.py`, which **FR-006** requires to be a closed set.

The catch history is the whole argument for it, and it is worse than the four
before it. On 2026-08-05 the two had diverged **in both directions at once** and
nothing anywhere read one against the other:

* three members the runtime already reaches were absent from the diagram —
  `terminated.capability_lapsed`, `terminated.operator_terminated` and
  `terminated.unrecoverable_fault`, the last of which has been the runner's
  teardown state since T046 and has its own arm in the suite;
* two names the diagram declared were not members — `terminated.no_progress`,
  a real debt recorded under T067, and `terminated.denied_operation`, which was
  recorded nowhere and which no requirement wanted;
* the diagram wrote the bare label `completed` where the member is
  `terminated.completed`, which the invariant test's
  `name.startswith("terminated.")` assertion would have rejected outright.

`check_corpus.py` ran its other sixteen checks at 0 errors throughout, because
none of them reads Python and the diagram was not machine-readable at all.
**OD-26** settles the direction — the module is authoritative for membership and
the diagram is a derived view of it — and authorises this check.

## What made it readable, and what that cost

§2.1 used to enumerate its terminal states as branch labels inside a fenced
`text` diagram. That form could not be reconciled by anything: it is prose art,
`~~` renders literally inside a fence so a superseded name cannot be struck in
the house style, and — the defect finding 027 opened on — it labelled every
branch with a terminal-state *name* rather than a state, so the diagram had no
`TERMINATED` for the code's `STATE_TERMINATED` to correspond to.

So the enumeration moved out of the diagram and into a **table**, and the
diagram kept the shape it was always authoritative about. The table is the
single enumeration; the diagram names no member, so the two cannot drift from
each other. What a human loses is the ten names inline in the picture. What a
human gains is a state model that matches the code, a requirement per member,
and a status column that says which members are owed.

## The three statuses, and why `owed` does not blind the check

| Status | Must be in `TAXONOMY` |
|---|---|
| `member` | **yes** — a declared branch with no member is a specification of something nothing can produce |
| `owed` | **no** — declared, not yet built, and recorded as owed against a task |
| `struck` | **no** — history, kept visible under the house convention |

The status is the cell's **first word**, and anything after it is a note for the
reader — the task an `owed` row is owed against, the date a `struck` row was
struck on. An `owed` row that cannot say what owes it is a row nobody will ever
come back to, so the room for that sentence is deliberate. A first word outside
the three is an error rather than an ignored row: a status the check does not
recognise is a row reconciled against nothing, which is how a table goes quiet
without going away.

**`owed` is checked in the forbidding direction, which is the point.** A marking
that merely exempted a row would go blind the moment the member landed: the
debt would be discharged, the marking would stay, and the table would go on
saying *not yet* about something that ships. So an `owed` row whose name **is**
a member is an error too, and the fix is to advance the row rather than to
delete the check. The same applies to `struck`: a struck name reappearing in the
taxonomy means the strike was reversed without the table being told.

## Vacuity, which a reconciliation check is unusually exposed to

Both sides of this comparison can degrade to the empty set, and an empty set
reconciles perfectly with another empty set. Two floors, neither of which a
passing run can be produced by:

* **A taxonomy that parses to zero members is an error**, unconditionally. That
  is what a moved `TAXONOMY` assignment, a renamed dataclass or a syntax error
  looks like from here, and it is indistinguishable from a real empty taxonomy
  by any comparison.
* **A corpus that has the scoped documents but no branch table in any of them is
  an error.** A renamed header, a reflowed table or a deleted section would
  otherwise take this check to zero findings, which reads exactly like success.

A corpus narrowed so that no scoped document is present at all — `--path
README.md` — is a `skip`, announced, because there is genuinely nothing to read.
Likewise a root with no taxonomy source file: the fixture corpora carry their
own, and a tree without one is not a defect this check can speak on.

## Reading the raw lines rather than the masked ones

Every member name in the table sits in a code span, and masking blanks code
spans to preserve other checks' regexes. This one reads `doc.lines` directly,
which is the case `tools/README.md` names as the exception. It pays for that by
doing its own strike handling rather than inheriting the shared one.

## What it cannot catch

* **A member with the wrong requirement or the wrong meaning.** The table's
  requirement column is not reconciled against `TerminalState.requirement`,
  deliberately: nothing in the taxonomy consumes `requirement` either, and
  pinning a second unread field would add a change-detector rather than a check.
* **A member nothing produces.** `terminated.capability_lapsed` is a member of
  the taxonomy with no producer in `src/`, and that is FR-050's crash path
  waiting to be built rather than a defect. Reachability is a question about
  code, not about these two artifacts.
* **A diagram whose shape is wrong.** Nothing here reads the fenced picture. If
  it grew an edge out of `TERMINATED` this check would not notice; the invariant
  suite and `src/contracts/transition.py`'s rule registry are what govern edges.
"""

from __future__ import annotations

import ast
import fnmatch
import re

from ..corpus import Corpus, split_row
from ..registry import check
from ..report import ERROR, Violation

#: The table this check reads is identified by its first header cell. Anchoring
#: on the header rather than on a heading or an HTML comment keeps the marker
#: visible to the human the table is written for — a reader who renames the
#: column has renamed the thing the check names in its message.
_HEADER_CELL = "terminal state"

_STATUS_MEMBER = "member"
_STATUS_OWED = "owed"
_STATUS_STRUCK = "struck"
_STATUSES = (_STATUS_MEMBER, _STATUS_OWED, _STATUS_STRUCK)

#: `` `terminated.completed` `` or `` ~~`terminated.denied_operation`~~ `` — the
#: strike markers and the code span are presentation and are stripped before the
#: name is compared. The status column is what the check reads; the markup is
#: what the reader sees.
_NAME = re.compile(r"^~*\s*`?([A-Za-z_][A-Za-z0-9_.]*)`?\s*~*$")


def _clean(cell: str) -> str:
    return " ".join(cell.split())


def _parse_taxonomy(source: str) -> set[str] | None:
    """The member names in `TAXONOMY`, by `ast` rather than by import.

    Parsed rather than imported for two reasons that are not interchangeable.
    `--root` may point at a fixture corpus whose `src/contracts/terminal.py` is
    a fixture, and importing it would run it under the real package name; and a
    corpus checker that executes the code it checks has a failure mode no regex
    does. Returns None when the source does not parse at all, which the caller
    reports rather than swallowing.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None

    # `NAME = TerminalState("terminated.x", ...)` — the binding a taxonomy entry
    # is written as. The first positional argument is the wire string.
    by_binding: dict[str, str] = {}
    taxonomy_bindings: list[str] = []

    for node in ast.walk(tree):
        targets: list[ast.expr] = []
        value: ast.expr | None = None
        if isinstance(node, ast.Assign):
            targets = list(node.targets)
            value = node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets = [node.target]
            value = node.value
        else:
            continue

        names = [t.id for t in targets if isinstance(t, ast.Name)]
        if not names or value is None:
            continue

        if (
            isinstance(value, ast.Call)
            and isinstance(value.func, ast.Name)
            and value.func.id == "TerminalState"
            and value.args
            and isinstance(value.args[0], ast.Constant)
            and isinstance(value.args[0].value, str)
        ):
            for name in names:
                by_binding[name] = value.args[0].value
        elif "TAXONOMY" in names and isinstance(value, (ast.Tuple, ast.List)):
            taxonomy_bindings = [
                e.id for e in value.elts if isinstance(e, ast.Name)
            ]

    return {by_binding[b] for b in taxonomy_bindings if b in by_binding}


def _branch_rows(doc) -> list[tuple[int, str, str]]:
    """`(lineno, name, status)` for every row of the branch table.

    Reads `doc.lines`, not `doc.masked_lines`: every name in the table sits in a
    code span, and masking blanks those. Rows inside a fenced block are skipped
    so a worked example in documentation is never read as a declaration.
    """
    rows: list[tuple[int, str, str]] = []
    in_table = False
    name_col = 0
    status_col = -1

    for i, raw in enumerate(doc.lines):
        if i in doc.fenced:
            in_table = False
            continue
        cells = split_row(raw)
        if cells is None:
            in_table = False
            continue

        lowered = [_clean(c).strip("*` ").lower() for c in cells]
        if not in_table:
            if lowered and lowered[0] == _HEADER_CELL and "status" in lowered:
                in_table = True
                name_col = 0
                status_col = lowered.index("status")
            continue

        # The delimiter row and any row too short to carry both columns.
        if status_col >= len(cells) or set(_clean(cells[name_col])) <= {"-", ":"}:
            continue

        m = _NAME.match(_clean(cells[name_col]))
        if m is None:
            continue
        # The first word only. What follows is the note the reader needs — which
        # task owes an `owed` row, when a `struck` one was struck — and reading
        # the whole cell would make every annotated row an unknown status.
        status = _clean(cells[status_col]).split(" ", 1)[0].strip("*`~ ").lower()
        rows.append((i + 1, m.group(1), status))

    return rows


@check(
    "lifecycle-taxonomy",
    "The lifecycle's declared terminal states are exactly the members of src/contracts/terminal.py's TAXONOMY.",
)
def run(corpus: Corpus, ctx: dict) -> list[Violation]:
    config = ctx["config"]
    scope = config.get("lifecycle_taxonomy_files", [])
    source_rel = config.get("lifecycle_taxonomy_source", "")

    if not scope or not source_rel:
        ctx["skip"](
            "lifecycle-taxonomy",
            "no lifecycle_taxonomy_files or lifecycle_taxonomy_source "
            "configured, so nothing was read — this is not a clean result",
        )
        return []

    scoped = [
        d for d in corpus.markdown()
        if any(fnmatch.fnmatch(d.relpath, p) for p in scope)
    ]
    if not scoped:
        ctx["skip"](
            "lifecycle-taxonomy",
            f"no document matching {scope} is in the corpus, so the lifecycle "
            "was not read — narrowing with --path does this",
        )
        return []

    source_path = corpus.root / source_rel
    if not source_path.is_file():
        ctx["skip"](
            "lifecycle-taxonomy",
            f"{source_rel} does not exist under {corpus.root}, so there is no "
            "taxonomy to reconcile the lifecycle against",
        )
        return []

    try:
        members = _parse_taxonomy(source_path.read_text(encoding="utf-8"))
    except OSError:
        members = None

    out: list[Violation] = []
    anchor = scoped[0]

    # Floor one. Zero members is what a moved assignment, a renamed dataclass or
    # a broken parse looks like, and it reconciles perfectly against a table
    # nobody has touched. There is no reading under which reporting success on
    # it is honest.
    if not members:
        out.append(
            Violation(
                check="lifecycle-taxonomy",
                severity=ERROR,
                path=source_rel,
                line=1,
                found="no TAXONOMY member could be read out of this file"
                if members is not None
                else "this file does not parse as Python",
                expected="at least one TerminalState listed in TAXONOMY before "
                "any lifecycle can be reconciled against it",
                hint="0 members here means 'not read', not 'none declared', and "
                "it agrees with every table in the corpus without checking "
                "anything. A member is a module-level "
                'NAME = TerminalState("terminated.x", ...) binding listed in '
                "the TAXONOMY tuple; if either shape moved, this parser has to "
                "move with it",
            )
        )
        return out

    declared: dict[str, tuple[str, str, int]] = {}
    total_rows = 0
    for doc in scoped:
        for lineno, name, status in _branch_rows(doc):
            total_rows += 1
            declared[name] = (status, doc.relpath, lineno)

    # Floor two. The documents are present and the taxonomy is non-empty, so a
    # corpus with no branch table has lost the declaration rather than never
    # having had one — a renamed header column is enough to do it.
    if not total_rows:
        out.append(
            Violation(
                check="lifecycle-taxonomy",
                severity=ERROR,
                path=anchor.relpath,
                line=1,
                found=f"no terminal-state branch table, but {source_rel} "
                f"declares {len(members)} member(s)",
                expected=f"a table whose first header cell is “{_HEADER_CELL}” "
                "and which carries a “Status” column, one row per member",
                hint="this check reconciles a table, not the fenced diagram: a "
                "picture cannot be struck through in the house style and "
                "cannot say which members are owed. If the table was renamed "
                "or reflowed, its absence reads exactly like agreement",
            )
        )
        return out

    for name, (status, relpath, lineno) in sorted(
        declared.items(), key=lambda kv: (kv[1][1], kv[1][2])
    ):
        if status not in _STATUSES:
            out.append(
                Violation(
                    check="lifecycle-taxonomy",
                    severity=ERROR,
                    path=relpath,
                    line=lineno,
                    found=f"{name} carries status {status!r}",
                    expected=f"one of {', '.join(_STATUSES)}",
                    hint="an unrecognised status is not read as any of the "
                    "three, so the row would be reconciled against nothing",
                )
            )
            continue

        is_member = name in members
        if status == _STATUS_MEMBER and not is_member:
            out.append(
                Violation(
                    check="lifecycle-taxonomy",
                    severity=ERROR,
                    path=relpath,
                    line=lineno,
                    found=f"{name} is declared a member of the lifecycle, but "
                    f"is not in {source_rel}'s TAXONOMY",
                    expected=f"{name} in TAXONOMY, or the row marked "
                    f"{_STATUS_OWED!r} against the task that owes it, or "
                    f"struck in the house style",
                    hint="FR-006 makes the taxonomy the closed set, so a "
                    "declared branch with no member specifies an outcome "
                    "nothing can produce (OD-26)",
                )
            )
        elif status in (_STATUS_OWED, _STATUS_STRUCK) and is_member:
            out.append(
                Violation(
                    check="lifecycle-taxonomy",
                    severity=ERROR,
                    path=relpath,
                    line=lineno,
                    found=f"{name} is marked {status!r}, but it IS in "
                    f"{source_rel}'s TAXONOMY",
                    expected=f"status {_STATUS_MEMBER!r}",
                    hint="a marking checked only in the exempting direction "
                    "goes blind the moment the debt is discharged: the member "
                    "ships, the row keeps saying it has not, and nothing ever "
                    "fires again",
                )
            )

    for name in sorted(members):
        if name in declared:
            continue
        out.append(
            Violation(
                check="lifecycle-taxonomy",
                severity=ERROR,
                path=anchor.relpath,
                line=1,
                found=f"{source_rel}'s TAXONOMY declares {name}, and the "
                "lifecycle does not mention it",
                expected=f"a row for {name} with status {_STATUS_MEMBER!r}",
                hint="the runtime can end a session in this state and the "
                "specification does not say so; three members were absent this "
                "way for weeks before anything read the two artifacts against "
                "each other (OD-26)",
            )
        )

    return out
