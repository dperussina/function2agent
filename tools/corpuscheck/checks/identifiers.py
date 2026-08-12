"""identifier-resolution — every D-17, U-40, OD-06, FR-018, E15 has a definition.

Dangling identifiers are how a superseded decision keeps getting cited: the row
is struck or renumbered somewhere, the citations are not, and the reference
still reads like an authority. The check resolves each reference against a
definition index built from the places this corpus actually defines things:

  * the first column of a register table — `| D-17 | ... |`, including struck
    and bolded forms like `| ~~**P-02**~~ |`
  * a heading that *leads* with the identifier — `### OD-01 — ADK's role`
  * a bold-lead bullet — `- **FR-018**: Analysis MUST operate on copies`

All three shapes are lead-anchored, and the heading shape is deliberately the
strictest reading of the example above: only the identifier the heading opens
with defines. A heading that merely *names* identifiers in prose — `### The
execution environment — FR-048, FR-049 and FR-050's mechanisms` — announces a
section about them, it does not define them. Counting those as definitions is
not a harmless over-read: it manufactures exactly the phantom register that
defeats the `min_definitions` guard below. See the note in `tools/README.md`
under **Narrowing and the definition index** for the measurement.

A namespace is only enforced once at least `min_definitions` of its members are
found. If a register is deleted or renamed, the check turns itself off with a
stated reason rather than reporting every reference in the corpus as dangling —
a checker that produces two hundred violations gets switched off permanently,
which costs more than the errors it found.

That guard is load-bearing under `--path`: narrowing removes the register from
the corpus, the namespace falls under the threshold, and the check declares
itself skipped instead of reporting every surviving reference as unresolved.
The cost of the guard is stated in the same README section — a skip cannot tell
"narrowed away" from "deleted", so a green narrowed run is not evidence that
the registers still exist.

`identifier-gap` is the companion: a namespace with a hole in it (D-01…D-14,
D-16…) usually means an entry was deleted rather than struck, and struck-with-a
-tombstone is this corpus's own convention.

**`identifier-gap` reads one register per feature for a namespace marked
`per_feature`, and the union for every other namespace.** `_collect_definitions`
unions definitions by token, and for `FR` and `SC` that union is a hole in the
check rather than a register: they are one register per feature and their tokens
COLLIDE — feature 001 defines FR-001…FR-022, feature 002 defines FR-001…FR-058,
and 001's register is a proper token subset of 002's. Deleting feature 001's
`FR-015` requirement outright, which is exactly the defect this check is for,
left the union contiguous because 002's FR-015 filled the hole, and the whole
gate reported **0 errors, 0 warnings** — measured 2026-08-12 by planting the
deletion, and again for all 22 of that register's rows, every one silent.

So a `per_feature` namespace is read register by register, each one being the
`definition_count_target` in its own `specs/<feature>/` directory — the same
per-feature resolution `definition-count` already does through `_target_of`. The
register is that one file and not the feature directory, which is what makes the
check see past a restatement: `specs/001-discovery-validation/VERDICT.md`
adjudicates all nine of feature 001's `SC` criteria in a first-cell table, so a
directory-keyed reading would have had 001's `SC` register filled by its own
verdict document and stayed silent on every row of it.

**The new silence mode this acquires, and how it is closed.** A feature whose
`spec.md` is absent, or narrowed away by `--path`, has no register to find a
hole in, and answering "no register, therefore no gaps" would install one
silence while removing another. Three states are distinguished, and only the
third is ever a pass: *outside the narrowed selection* and *absent from the
repository* are both announced through `ctx["skip"]`, and the test that
separates them is asked of the unnarrowed tree under `corpus.root` — the move
`_unnarrowed_definitions` makes for the namespace-level decision, which no
combination of `--path` arguments can answer.

`tools/README.md` under **The FR/SC register collision** carries the exposure
measurement, the coverage this adds and the two rows it cannot see, and why
scoping `identifier-resolution` per feature was declined on numbers while this
gap-side case has no false-positive population at all.
"""

from __future__ import annotations

import re

from ..corpus import Corpus, load as load_corpus, split_row
from ..registry import check
from ..report import ERROR, WARNING, Violation

_DECOR = re.compile(r"[*~`_\s]+")
_HEADING = re.compile(r"^#{1,6}\s+(.*)$")
# Leading decoration only — `### **OD-01** — role` and `### ~~D-05~~ superseded`
# still lead with their identifier once the markup is stripped.
_LEAD_DECOR = re.compile(r"^[*~`_\s]+")
_BULLET_DEF = re.compile(r"^\s*[-*+]\s+\*\*([A-Za-z]{1,3}-?\d{1,3})\*\*\s*[:.\u2014-]")


def _namespaces(config: dict) -> dict[str, re.Pattern]:
    return {
        name: re.compile(r"(?<![A-Za-z0-9-])" + spec["pattern"] + r"(?![A-Za-z0-9-])")
        for name, spec in config["identifier_namespaces"].items()
    }


def definitions_in(doc, patterns: dict[str, re.Pattern]) -> dict[str, set[str]]:
    """Map namespace -> identifiers *this one document* defines.

    The single definition of "defines" in this tool. `_collect_definitions`
    unions it over the corpus and `definition-count` asks it about one file;
    both have to agree about the three shapes below, and a second copy of the
    rule would drift from the first, which is the failure class this directory
    exists to prevent.
    """
    defined: dict[str, set[str]] = {ns: set() for ns in patterns}

    def note(text: str) -> None:
        for ns, rx in patterns.items():
            for m in rx.finditer(text):
                defined[ns].add(m.group(0))

    def note_lead(text: str) -> None:
        """Only an identifier the text *opens* with defines it.

        The namespace patterns already carry a trailing boundary lookahead, so
        an anchored `match` is the whole rule.
        """
        head = _LEAD_DECOR.sub("", text)
        for ns, rx in patterns.items():
            m = rx.match(head)
            if m:
                defined[ns].add(m.group(0))

    for i, line in enumerate(doc.lines):
        if i in doc.fenced:
            continue

        hm = _HEADING.match(line)
        if hm:
            note_lead(hm.group(1))
            continue

        bm = _BULLET_DEF.match(line)
        if bm:
            note(bm.group(1))
            continue

        if line.lstrip().startswith("|"):
            cells = split_row(line)
            if cells:
                head = _DECOR.sub("", cells[0])
                # Only an exact first-cell match defines; a cell of prose
                # that happens to mention D-17 does not.
                for ns, rx in patterns.items():
                    m = rx.fullmatch(head)
                    if m:
                        defined[ns].add(m.group(0))
    return defined


def _collect_definitions(corpus: Corpus, patterns: dict[str, re.Pattern]) -> dict[str, set[str]]:
    """Map namespace -> set of identifiers the corpus defines."""
    defined: dict[str, set[str]] = {ns: set() for ns in patterns}
    for doc in corpus.markdown():
        for ns, ids in definitions_in(doc, patterns).items():
            defined[ns] |= ids
    return defined


def _definition_sites(
    corpus: Corpus, patterns: dict[str, re.Pattern]
) -> dict[str, list[tuple[str, int]]]:
    """Map namespace -> `(relpath, members defined there)`, densest document first.

    `identifier-gap` needs this and `_collect_definitions` cannot supply it,
    because a union of sets has forgotten which file each member came from.
    That is the whole reason the gap violation used to print a configured prose
    label where every other violation prints an openable relpath: there was no
    computed answer to put there.

    Read off this run's corpus rather than off `config`, which is what makes it
    correct in all three trees the checks run against. The configured `what`
    string names the real corpus's addresses, so in either fixture tree it named
    a document that does not exist — the known-bad register is
    `research/14-fixture-synthesis.md` and the label said `research/14 §3.1`.

    Ties break on relpath so the chosen document does not depend on walk order.
    """
    counts: dict[str, dict[str, int]] = {ns: {} for ns in patterns}
    for doc in corpus.markdown():
        for ns, ids in definitions_in(doc, patterns).items():
            if ids:
                counts[ns][doc.relpath] = len(ids)
    return {
        ns: sorted(per_doc.items(), key=lambda kv: (-kv[1], kv[0]))
        for ns, per_doc in counts.items()
    }


def _unnarrowed_corpus(corpus: Corpus, ctx: dict) -> Corpus:
    """The corpus the *whole tree* yields, ignoring any `--path`.

    Read off the filesystem under `corpus.root` rather than off the corpus that
    was handed in, which is the same move `lifecycle-taxonomy` makes to tell a
    missing document from a narrowed-away one. This is what keeps every skip
    below from being vacuous: each deletion test is asked of the unnarrowed
    tree, so no combination of `--path` arguments can answer it.

    Cached on `ctx`, because both the namespace-level activation and the
    per-feature register walk need it and the tree is expensive to walk twice.
    """
    cached = ctx.get("_unnarrowed_corpus")
    if cached is None:
        cached = load_corpus(corpus.root, ctx["config"])
        ctx["_unnarrowed_corpus"] = cached
    return cached


def _unnarrowed_definitions(
    corpus: Corpus, ctx: dict, patterns: dict[str, re.Pattern]
) -> dict[str, set[str]]:
    """The definition index the whole tree yields, ignoring any `--path`."""
    return _collect_definitions(_unnarrowed_corpus(corpus, ctx), patterns)


def _feature_specs(
    corpus: Corpus, patterns: dict[str, re.Pattern], target: str
) -> tuple[dict[str, dict[str, set[str]]], set[str]]:
    """`(feature -> namespace -> identifiers it defines, features seen at all)`.

    A feature's register is the `target` in its own `specs/<feature>/` directory.
    `definition-count` resolves its claims through the same two-component prefix
    and the same configured filename, and reusing both is the point: a
    per-feature register lives where that check already looks for one, rather
    than at a second address that could drift from it.

    The second element is every `specs/<feature>/` directory the corpus holds a
    document under, whether or not that directory has a `<target>`. Without it a
    feature whose specification had been deleted outright would simply not
    appear, and not appearing is indistinguishable from a clean register.

    A feature present in the first element defines *some* namespace's members in
    its `<target>`; a feature present only in the second has no readable
    register there.
    """
    rx = re.compile(r"^(specs/[^/]+)/")
    registers: dict[str, dict[str, set[str]]] = {}
    features: set[str] = set()
    for doc in corpus.markdown():
        m = rx.match(doc.relpath)
        if not m:
            continue
        feature = m.group(1)
        features.add(feature)
        if doc.relpath == f"{feature}/{target}":
            registers[feature] = definitions_in(doc, patterns)
    return registers, features


def _activation(corpus: Corpus, ctx: dict) -> tuple[dict[str, set[str]], dict[str, re.Pattern], list[str]]:
    """Which namespaces this run may enforce, decided once and shared.

    Both checks in this module need the same answer, and the runner executes
    them in name order, so `identifier-gap` runs *first*. The older arrangement
    had `identifier-gap` read an index that `identifier-resolution` was
    expected to have left in `ctx`; that handoff ran in the wrong direction and
    the fallback branch was therefore the only branch ever taken, which is how
    the gap check kept reporting on namespaces the resolution check had
    disabled. Computing it here makes the order irrelevant.

    Returns the narrowed definition index, the enforceable namespaces, and the
    reasons for every namespace left out, for the caller to announce.
    """
    cached = ctx.get("_identifier_activation")
    if cached is not None:
        return cached

    config = ctx["config"]
    patterns = _namespaces(config)
    minimum = config["min_definitions"]
    defined = _collect_definitions(corpus, patterns)

    # Under `--path`, `defined` is only what survived the narrowing. Every
    # deletion test below is asked of `whole` instead, which is read off the
    # unnarrowed tree, so narrowing can suppress a namespace but can never make
    # a deleted register look present.
    whole = (
        _unnarrowed_definitions(corpus, ctx, patterns)
        if ctx.get("narrowed_paths")
        else defined
    )

    active: dict[str, re.Pattern] = {}
    reasons: list[str] = []
    for ns, rx in patterns.items():
        if len(whole[ns]) < minimum:
            # Asked of the whole tree: the register is absent, deleted or
            # renamed, and this reads the same with or without `--path`.
            reasons.append(
                f"namespace {ns} disabled: found {len(whole[ns])} definition(s), "
                f"need {minimum} ({config['identifier_namespaces'][ns]['what']})"
            )
            continue

        missing = whole[ns] - defined[ns]
        if missing:
            # The register exists; this run just cannot see all of it. Resolving
            # against a partial index would report every reference to the part
            # that was narrowed away as dangling — hundreds of errors naming
            # identifiers that resolve perfectly well in a full run.
            reasons.append(
                f"namespace {ns} not enforced: {len(missing)} of {len(whole[ns])} "
                f"definition(s) are outside the --path selection, so the register "
                f"({config['identifier_namespaces'][ns]['what']}) was only partly "
                "read — a full run enforces it"
            )
            continue

        active[ns] = rx

    out = (defined, active, reasons)
    ctx["_identifier_activation"] = out
    ctx["identifiers_defined"] = defined
    ctx["identifiers_active"] = set(active)
    return out


@check("identifier-resolution", "Register identifiers (D-17, U-40, OD-06, FR-018, E15) resolve.")
def resolution(corpus: Corpus, ctx: dict) -> list[Violation]:
    config = ctx["config"]
    defined, active, reasons = _activation(corpus, ctx)
    for reason in reasons:
        ctx["skip"]("identifier-resolution", reason)

    out: list[Violation] = []
    for doc in corpus.markdown():
        for lineno, masked in enumerate(doc.masked_lines, start=1):
            if not masked.strip():
                continue
            for ns, rx in active.items():
                for m in rx.finditer(masked):
                    token = m.group(0)
                    if token in defined[ns]:
                        continue
                    out.append(
                        Violation(
                            check="identifier-resolution",
                            severity=ERROR,
                            path=doc.relpath,
                            line=lineno,
                            col=m.start() + 1,
                            found=token,
                            expected=f"a definition of {token} in the {ns} register "
                            f"({config['identifier_namespaces'][ns]['what']})",
                            hint=f"{ns} currently runs to "
                            f"{max(sorted(defined[ns]), default='—')}; "
                            "struck entries keep their row, deleted ones do not",
                        )
                    )
    return out


def _missing(ids: set[str], minimum: int) -> tuple[list[int], list[int]] | None:
    """`(numbers present, numbers missing between the endpoints)`, or `None`.

    `None` means the set is too small to speak on. A density reading sees
    **holes and not truncations**: the range is computed from the members that
    are there, so deleting either endpoint shrinks the range rather than
    perforating it and this returns no missing numbers. That is a property of
    every density check and not of this one — measured 2026-08-12 over all 119
    `FR` and `SC` rows in the two feature specifications, the per-feature
    reading is blind to exactly the two endpoints of each of the four registers
    and to nothing else.
    """
    if len(ids) < minimum:
        return None
    nums = sorted(int(re.sub(r"\D", "", i)) for i in ids)
    return nums, [n for n in range(min(nums), max(nums) + 1) if n not in nums]


def _pretty(ns: str, ids: set[str], missing: list[int]) -> str:
    exemplar = sorted(ids)[0]
    width = len(re.sub(r"\D", "", exemplar))
    joiner = "-" if "-" in exemplar else ""
    return ", ".join(f"{ns}{joiner}{n:0{width}d}" for n in missing)


def _per_feature_gaps(
    corpus: Corpus, ctx: dict, active: dict[str, re.Pattern]
) -> tuple[list[Violation], set[str]]:
    """Holes in each feature's own register, for namespaces marked `per_feature`.

    Returns the violations and the namespaces this pass spoke on, so the caller
    can leave those out of the union reading rather than report one hole twice.

    Every namespace here is one register per feature with COLLIDING tokens, so
    the union is not a register and a hole in one feature's register is filled
    by another feature's unrelated requirement of the same number. The three
    states below are genuinely different and only the last is a pass.
    """
    config = ctx["config"]
    minimum = config["min_definitions"]
    target = config.get("definition_count_target", "spec.md")
    per_feature = [
        ns for ns in sorted(active)
        if config["identifier_namespaces"][ns].get("per_feature")
    ]
    if not per_feature:
        return [], set()

    patterns = {ns: active[ns] for ns in per_feature}
    seen_regs, seen_features = _feature_specs(corpus, patterns, target)
    # Asked of the tree, never of the selection: `--path` decides what this run
    # read, and must not be able to decide whether a register exists. Without
    # `--path` the two readings are the same walk, so it is not repeated.
    whole_regs, whole_features = (
        _feature_specs(_unnarrowed_corpus(corpus, ctx), patterns, target)
        if ctx.get("narrowed_paths")
        else (seen_regs, seen_features)
    )

    out: list[Violation] = []
    spoke: set[str] = set()
    for ns in per_feature:
        label = config["identifier_namespaces"][ns]["what"]
        registers = {f: r[ns] for f, r in whole_regs.items() if r[ns]}
        if not registers:
            # No feature defines this namespace anywhere in the tree. The
            # namespace-level activation already announced that; adding a
            # second line per feature would say it again.
            continue

        for feature in sorted(whole_features):
            rel = f"{feature}/{target}"
            whole_ids = whole_regs.get(feature, {}).get(ns, set())

            if feature not in whole_regs:
                ctx["skip"](
                    "identifier-gap",
                    f"{feature} has no {target}, so its {ns} register ({label}) "
                    "was not read for holes — this is absent from the repository "
                    "rather than narrowed away, and it is not a clean result",
                )
                continue

            if not whole_ids:
                if len(registers) == len(whole_features):
                    continue
                ctx["skip"](
                    "identifier-gap",
                    f"{rel} defines no {ns} members while "
                    f"{len(registers)} other feature specification(s) do, so there "
                    f"is no {ns} register ({label}) there to find holes in",
                )
                continue

            if len(whole_ids) < minimum:
                ctx["skip"](
                    "identifier-gap",
                    f"{rel}: {ns} register ({label}) has {len(whole_ids)} "
                    f"definition(s), need {minimum} before a hole in it can be "
                    "told from a short register",
                )
                continue

            seen_ids = seen_regs.get(feature, {}).get(ns, set())
            if seen_ids != whole_ids:
                ctx["skip"](
                    "identifier-gap",
                    f"{rel}: {len(whole_ids) - len(seen_ids)} of "
                    f"{len(whole_ids)} {ns} definition(s) are outside the --path "
                    f"selection, so that register ({label}) was only partly read "
                    "and was not checked for holes — a full run checks it",
                )
                continue

            spoke.add(ns)
            found = _missing(seen_ids, minimum)
            if found is None:
                continue
            nums, missing = found
            if not missing:
                continue
            out.append(
                Violation(
                    check="identifier-gap",
                    severity=WARNING,
                    path=rel,
                    line=0,
                    found=f"{feature}'s {ns} register ({label}) has no definition "
                    f"for {_pretty(ns, seen_ids, missing)}",
                    expected=f"a contiguous {ns} register from {min(nums)} to "
                    f"{max(nums)} in {rel}",
                    hint=f"{ns} is one register per feature and the tokens collide "
                    "across features, so a row deleted here leaves the corpus-wide "
                    "union contiguous and only this per-feature reading sees it; a "
                    "superseded entry should keep its row with a strike-through",
                )
            )
    return out, spoke


@check("identifier-gap", "A register with a missing member usually means a deleted row.")
def gaps(corpus: Corpus, ctx: dict) -> list[Violation]:
    config = ctx["config"]
    # Same activation decision `identifier-resolution` uses, so a namespace
    # whose register was narrowed away is not reported here as a register full
    # of holes. Announcing those reasons is left to that check, which is where
    # they have always been printed; the per-feature skips below are this
    # check's own and have nowhere else to go.
    defined, active, _reasons = _activation(corpus, ctx)

    out, spoke = _per_feature_gaps(corpus, ctx, active)
    sites = _definition_sites(corpus, active)

    for ns in sorted(active):
        # A namespace the per-feature pass read is not read again as a union:
        # one deleted row would otherwise be reported twice. The union reading
        # is kept for it when the per-feature pass could not speak, because it
        # still covers one thing no per-feature reading does — a
        # definition-shaped row for that namespace outside every feature's
        # specification, which puts a hole in the union and in no register.
        if ns in spoke:
            continue
        found = _missing(defined[ns], config["min_definitions"])
        if found is None:
            continue
        nums, missing = found
        if not missing:
            continue
        pretty = _pretty(ns, defined[ns], missing)

        label = config["identifier_namespaces"][ns]["what"]
        where = sites[ns]
        # `path` is the column a reader expects to be able to open, so it gets a
        # relpath even where the register has no single file.
        #
        # **How many namespaces reach the branch below depends on the question,
        # and two different answers are recorded in this repository.** Measured
        # 2026-08-12 with `definitions_in` over the loaded corpus:
        #
        #   * **7 of 9** contain definition-shaped rows in more than one
        #     document — E 30, FR 5, D 3, OD 3, SC 3, C 2, U 2 — and this is the
        #     reading that decides the branch, because `sites` counts defining
        #     documents and nothing else. So D, C, U and OD take it too.
        #   * **1 of 9** — `E` alone — has more than one document contributing a
        #     token no other document contributes. Every secondary site for D,
        #     C, U, OD, FR and SC is a strict subset of a primary one: a
        #     restatement, not a register.
        #
        # A third figure is an editorial reading rather than a census: `FR`,
        # `SC` and `E` are the **3** namespaces that are logically more than one
        # register — FR and SC one per feature with COLLIDING tokens, E a ladder
        # plus one index per non-ladder experiment. That is the reading
        # `per_feature` and `config.json`'s hand-written `what` strings turn on,
        # and it is *not* what this branch tests. An earlier revision of this
        # comment gave the 3 as though it were, which had it describing four
        # fewer namespaces than the code reaches. See `tools/README.md` under
        # **Three answers to "how many namespaces are plural"**.
        #
        # For a namespace that reaches here there is no one document to name,
        # and saying so is the honest answer rather than a silent pick.
        if len(where) == 1:
            spans = f"defined in {where[0][0]}"
        else:
            # Bounded, because `E` spans 30 documents — a ladder in one plan.md
            # plus one index per non-ladder experiment plus every committed run
            # report that heads a section with an identifier. An unbounded list
            # would put thirty paths on one line and stop being read.
            named = ", ".join(f"{rel} defines {n}" for rel, n in where[:3])
            rest = len(where) - 3
            spans = (
                f"the {ns} register has no single file: {len(where)} documents "
                f"define members of it ({named}"
                + (f", and {rest} more" if rest > 0 else "")
                + "), and this is filed against the one defining most of them"
            )

        out.append(
            Violation(
                check="identifier-gap",
                severity=WARNING,
                path=where[0][0],
                line=0,
                found=f"{ns} register ({label}) has no definition for {pretty}",
                expected=f"a contiguous {ns} register from {min(nums)} to {max(nums)}; {spans}",
                hint="a superseded entry should keep its row with a strike-through, "
                "so a gap usually means a deleted row that is still cited elsewhere",
            )
        )
    return out
