#!/usr/bin/env python3
"""Rank requirements by relevance to each contract's subject. **Advisory only.**

For every contract under `specs/*/contracts/`, this scores all of `spec.md`'s
requirements against the contract's subject — its title plus its leading
section — and prints the highest-scoring ones the contract does **not** cite.

    python3 tools/cite_advisor.py                    # the advisory listing
    python3 tools/cite_advisor.py --ground-truth     # score against the five hand-audited contracts
    python3 tools/cite_advisor.py --sensitivity      # how the ranks move with the stoplist and stemmer

**This is not a check and must not become one.** **No finding it makes changes its
exit code** — it exits non-zero only for a path or a revision that does not exist,
which is a broken invocation and not a result. Nothing imports it and
`check_corpus.py` does not know it exists. The gate version of
this idea was attempted on 2026-08-03 and abandoned: its usable threshold window
was four thousandths of a Jaccard score wide, and a clean contract that simply
cited less densely scored worse than a real defect. `tools/README.md` §*What this
cannot catch* carries the measurements. What survived that attempt was the
**ranking**, which needs no threshold, and this is that ranking and nothing more.

**It reports a rank, never a verdict.** The sentence it exists to produce is
*"FR-055 scores higher than anything this contract cites"* — a prompt to go and
look. *"This contract is wrong"* is the sentence that failed the false-positive
probe, and no output here should be readable as it. A contract may legitimately
score highest against a requirement it deliberately does not cite; two of the
three hand-audited clean contracts do exactly that.

**The metric is the one that was measured, not a new one.** Jaccard similarity
between the significant terms of the contract's subject and the significant terms
of each requirement, with citations read at header scope only. `--sensitivity`
exists because the stoplist and the stemmer were the two parameters the prior
sweep did not record, and they move the ranks.
"""

from __future__ import annotations

import argparse
import itertools
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from corpuscheck.corpus import build_masked  # noqa: E402

# --------------------------------------------------------------------------
# Terms
# --------------------------------------------------------------------------

# Three stoplists, kept because the prior sweep swept three and did not record
# which one survived. `medium` is the default: it is the one that reproduces the
# ranks quoted in tools/README.md, and `--sensitivity` shows what the other two
# do to them rather than hiding the choice.
_MINIMAL = set(
    "a an the and or of in on at to for from by with is are was were be been it its this "
    "that these those as".split()
)
_MEDIUM = _MINIMAL | set(
    """
    but if then than do does did doing have has had having will would shall should may might
    must can could not no nor so such they them their there here when where which who whom
    whose what why how all any both each few more most other some only own same too very now
    one two three four five six seven eight nine ten
    """.split()
)
# `large` additionally drops the modal and structural vocabulary every requirement
# in a MUST-shaped specification shares, on the theory that a term present in all
# 57 requirements discriminates between none of them.
_LARGE = _MEDIUM | set(
    """
    required requires require system agent every into upon per within under over between
    across before after during while because since therefore thus however rather first second
    third whole part parts thing things use used using make makes made given give gives
    """.split()
)

STOPLISTS = {"minimal": _MINIMAL, "medium": _MEDIUM, "large": _LARGE}

_SUFFIXES = (
    "ational", "ization", "isation", "ations", "ition", "ments", "ences", "ances",
    "ation", "ement", "ising", "izing", "ities", "ment", "ness", "tion", "sion",
    "ible", "able", "ance", "ence", "ing", "ers", "ies", "ive", "ity", "ise",
    "ize", "ed", "es", "ly", "s",
)

_WORD = re.compile(r"[A-Za-z][A-Za-z_-]*")

MIN_TERM_LENGTH = 3


def stem(word: str) -> str:
    """Longest-suffix strip, leaving at least four characters of stem."""
    for suffix in _SUFFIXES:
        if len(word) - len(suffix) >= 4 and word.endswith(suffix):
            return word[: -len(suffix)]
    return word


def terms(text: str, *, stoplist: set[str], stemming: bool) -> set[str]:
    out: set[str] = set()
    for match in _WORD.finditer(text):
        word = match.group(0).lower().strip("-_")
        if len(word) < MIN_TERM_LENGTH or word in stoplist:
            continue
        out.add(stem(word) if stemming else word)
    return out


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


# --------------------------------------------------------------------------
# Requirements
# --------------------------------------------------------------------------

_REQ_START = re.compile(r"^- \*\*(FR-\d{3})\*\*:")


def parse_requirements(spec_text: str) -> dict[str, str]:
    """`{"FR-038": "<the whole bullet, masked>"}`.

    A requirement is a top-level bullet plus every indented continuation under
    it, which is where the rewrites, the deviation notes and the struck text all
    live. Masking is `corpuscheck`'s, so fenced blocks and link targets are
    already blanked and no term comes out of a code sample.
    """
    lines = spec_text.splitlines()
    masked, fenced = build_masked(lines)
    bodies: dict[str, list[str]] = {}
    current: str | None = None
    for i, raw in enumerate(lines):
        if i in fenced:
            continue
        start = _REQ_START.match(raw)
        if start:
            current = start.group(1)
            bodies.setdefault(current, []).append(masked[i])
            continue
        if current is None:
            continue
        if not raw.strip():
            continue
        if raw.startswith((" ", "\t")):
            bodies[current].append(masked[i])
            continue
        current = None
    return {name: "\n".join(rows) for name, rows in bodies.items()}


# --------------------------------------------------------------------------
# Contracts
# --------------------------------------------------------------------------

_CITE_FIELD = re.compile(r"^\*\*Requirements\*\*:\s*(.*)$")
_FR = re.compile(r"FR-(\d{3})")
# `FR-039–FR-042` and `FR-039-042`, en dash or em dash or hyphen.
_FR_RANGE = re.compile(r"FR-(\d{3})\s*[\u2013\u2014-]\s*(?:FR-)?(\d{3})")


SCOPES = ("header", "body")


@dataclass(frozen=True)
class Contract:
    relpath: str
    title: str
    lead_heading: str
    subject: str
    cites: frozenset[str]  # the `**Requirements**:` header field
    mentions: frozenset[str]  # named anywhere in the prose below the header

    def acknowledged(self, scope: str) -> frozenset[str]:
        """Which requirements count as already considered.

        `header` is the strict shape the prior sweep settled on and is what a
        rule about a *citation field* would have to use. `body` additionally
        counts a requirement the contract names in its prose, which is the right
        question for an advisory: the reader is being asked *"is there a
        requirement you have not thought about"*, and one discussed by name in
        the second paragraph has been thought about. The difference is measured
        rather than assumed — `--ground-truth` reports both.
        """
        if scope == "header":
            return self.cites
        return self.cites | self.mentions


def parse_contract(path: Path, relpath: str) -> Contract | None:
    lines = path.read_text(encoding="utf-8").splitlines()
    masked, fenced = build_masked(lines)

    header_end = len(lines)
    for i, raw in enumerate(lines):
        if raw.strip() == "---" or raw.startswith("## "):
            header_end = i
            break

    title = ""
    cites: set[str] = set()
    for i in range(header_end):
        raw = lines[i]
        if raw.startswith("# ") and not title:
            title = raw[2:].strip()
        field = _CITE_FIELD.match(raw)
        if not field:
            continue
        # The field wraps. Take continuation lines until the next `**Field**:`.
        body = field.group(1)
        j = i + 1
        while j < header_end and lines[j].strip() and not lines[j].startswith("**"):
            body += " " + lines[j]
            j += 1
        for span in _FR_RANGE.finditer(body):
            lo, hi = int(span.group(1)), int(span.group(2))
            if 0 < hi - lo < 100:
                for n in range(lo, hi + 1):
                    cites.add(f"FR-{n:03d}")
        for one in _FR.finditer(body):
            cites.add(f"FR-{one.group(1)}")

    if not title:
        return None

    # Subject: the title plus the leading section. A contract's first section is
    # what its title is about; later sections range over neighbouring concerns
    # and were measured to dilute the signal in the prior sweep.
    lead: list[str] = []
    lead_heading = ""
    started = False
    for i, raw in enumerate(lines):
        if raw.startswith("## "):
            if started:
                break
            started = True
            lead_heading = raw[3:].strip()
            lead.append(masked[i])
            continue
        if started and i not in fenced:
            lead.append(masked[i])

    mentions = {
        f"FR-{m.group(1)}"
        for i, row in enumerate(masked)
        if i >= header_end and i not in fenced
        for m in _FR.finditer(row)
    }

    return Contract(
        relpath=relpath,
        title=title,
        lead_heading=lead_heading,
        subject=title + "\n" + "\n".join(lead),
        cites=frozenset(cites),
        mentions=frozenset(mentions),
    )


CONTRACTS_SUBDIR = "specs/002-spec-aware-agent-runtime/contracts"
SPEC_SUBPATH = "specs/002-spec-aware-agent-runtime/spec.md"


def checkout(root: Path, rev: str, into: Path) -> tuple[Path, Path]:
    """Materialise one revision's contracts and spec.md into `into`.

    The ground-truth run scores contract states that no longer exist in the
    working tree. Reading them straight out of git keeps the validation
    reproducible from the repository rather than from a scratch directory
    someone has to be told about.
    """
    contracts = into / "contracts"
    contracts.mkdir(parents=True, exist_ok=True)

    def git(*args: str) -> str:
        done = subprocess.run(
            ["git", "-C", str(root), *args], capture_output=True, text=True
        )
        if done.returncode != 0:
            # An advisory that dies on a typo is worse than one that says so.
            raise SystemExit(f"git {' '.join(args)}: {done.stderr.strip()}")
        return done.stdout

    def show(relpath: str) -> str:
        return git("show", f"{rev}:{relpath}")

    listing = git("ls-tree", "-r", "--name-only", rev, "--", CONTRACTS_SUBDIR).split()
    if not listing:
        raise SystemExit(f"no contracts under {CONTRACTS_SUBDIR} at {rev}")
    for relpath in listing:
        name = Path(relpath).name
        if name == "README.md":
            continue
        (contracts / name).write_text(show(relpath), encoding="utf-8")

    spec = into / "spec.md"
    spec.write_text(show(SPEC_SUBPATH), encoding="utf-8")
    return contracts, spec


def find_contracts(root: Path, contracts_dir: Path | None) -> list[Path]:
    if contracts_dir is not None:
        return sorted(p for p in contracts_dir.glob("*.md") if p.name != "README.md")
    found: list[Path] = []
    for spec_dir in sorted(root.glob("specs/*/contracts")):
        found += [p for p in sorted(spec_dir.glob("*.md")) if p.name != "README.md"]
    return found


# --------------------------------------------------------------------------
# Scoring
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Ranked:
    contract: Contract
    scores: list[tuple[str, float]]  # descending, ties broken by requirement id
    scope: str = "body"

    def rank_of(self, requirement: str) -> int | None:
        for i, (name, _) in enumerate(self.scores, start=1):
            if name == requirement:
                return i
        return None

    def score_of(self, requirement: str) -> float:
        return dict(self.scores).get(requirement, 0.0)

    def best_cited_rank(self, scope: str | None = None) -> int | None:
        known = self.contract.acknowledged(scope or self.scope)
        for i, (name, _) in enumerate(self.scores, start=1):
            if name in known:
                return i
        return None

    def uncited(self, scope: str | None = None) -> list[tuple[int, str, float]]:
        known = self.contract.acknowledged(scope or self.scope)
        return [
            (i, name, score)
            for i, (name, score) in enumerate(self.scores, start=1)
            if name not in known
        ]

    def outranking(self, scope: str | None = None) -> list[tuple[int, str, float]]:
        """The headline: uncited requirements beating everything the contract knows.

        This is the sentence the advisory exists to produce, so it is also the
        surface its noise should be measured on. A listing whose top five are
        mostly dismissible is survivable; a *headline* that is mostly wrong is
        the thing a reader learns to skip.
        """
        best = self.best_cited_rank(scope)
        if best is None:
            return self.uncited(scope)
        return [row for row in self.uncited(scope) if row[0] < best]


def rank(
    contract: Contract, req_terms: dict[str, set[str]], *, stoplist, stemming, scope: str = "body"
) -> Ranked:
    subject = terms(contract.subject, stoplist=stoplist, stemming=stemming)
    scores = sorted(
        ((name, jaccard(subject, rt)) for name, rt in req_terms.items()),
        key=lambda pair: (-pair[1], pair[0]),
    )
    return Ranked(contract=contract, scores=scores, scope=scope)


def build(root: Path, spec: Path, contracts_dir: Path | None, *, stoplist, stemming, scope="body"):
    requirements = parse_requirements(spec.read_text(encoding="utf-8"))
    req_terms = {
        name: terms(body, stoplist=stoplist, stemming=stemming)
        for name, body in requirements.items()
    }
    ranked: list[Ranked] = []
    for path in find_contracts(root, contracts_dir):
        try:
            rel = path.relative_to(root).as_posix()
        except ValueError:
            rel = path.as_posix()
        contract = parse_contract(path, rel)
        if contract is None:
            continue
        ranked.append(
            rank(contract, req_terms, stoplist=stoplist, stemming=stemming, scope=scope)
        )
    return ranked, requirements


# --------------------------------------------------------------------------
# Ground truth — the five hand-audited contracts
# --------------------------------------------------------------------------

# Established by hand and recorded in tools/README.md. The value is the
# requirement a human determined governs the contract's subject and which the
# contract did not cite at the time. An empty set means the contract was audited
# and found to cite correctly — so *every* suggestion against it is a miss, which
# is the only definition of precision that measures what this tool costs a
# reader.
GROUND_TRUTH: dict[str, frozenset[str]] = {
    "trace-record.md": frozenset({"FR-038"}),
    "artifact-versioning.md": frozenset({"FR-055"}),
    "configuration.md": frozenset(),
    "egress-policy.md": frozenset(),
    "result-record.md": frozenset(),
}


def precision_at(ranked: list[Ranked], k: int, *, scope: str) -> tuple[int, int, float]:
    """Hits over suggestions across every contract with a ground-truth entry.

    A contract audited clean contributes zero hits and however many suggestions
    it emits, so a tool that talks about clean work is penalised for it. That is
    deliberate: an advisory's cost *is* what it says about work that is fine.
    """
    hits = 0
    shown = 0
    for r in ranked:
        name = Path(r.contract.relpath).name
        if name not in GROUND_TRUTH:
            continue
        top = r.uncited(scope)[:k]
        shown += len(top)
        hits += sum(1 for _, req, _ in top if req in GROUND_TRUTH[name])
    return hits, shown, (hits / shown if shown else 0.0)


def headline_precision(ranked: list[Ranked], *, scope: str) -> tuple[int, int, float]:
    """The same, over the `outranks everything you cite` sentence only."""
    hits = 0
    shown = 0
    for r in ranked:
        name = Path(r.contract.relpath).name
        if name not in GROUND_TRUTH:
            continue
        rows = r.outranking(scope)
        shown += len(rows)
        hits += sum(1 for _, req, _ in rows if req in GROUND_TRUTH[name])
    return hits, shown, (hits / shown if shown else 0.0)


# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------

BANNER = (
    "ADVISORY — this tool fails nothing and gates nothing. No finding below\n"
    "changes its exit code.\n"
    "For each contract it ranks every requirement by term overlap with the contract's\n"
    "subject, then lists the highest-scoring ones the contract does not already name.\n"
    "A rank is a reason to go and look. It is not a finding, and nothing here is a\n"
    "claim that a contract is wrong — the threshold rule that would have made it one\n"
    "was measured on 2026-08-03 and does not exist. Expect to dismiss suggestions;\n"
    "the line worth reading is the one marked ->."
)


def emit(ranked: list[Ranked], *, top: int, requirements: dict[str, str], scope: str) -> None:
    print(BANNER)
    print()
    print(
        f"{len(requirements)} requirements scored against {len(ranked)} contract(s); "
        f"citation scope {scope}."
    )
    quiet = 0
    for r in ranked:
        c = r.contract
        print()
        print(f"{c.relpath}")
        lead = f" + § {c.lead_heading}" if c.lead_heading else ""
        print(f'    subject   "{c.title}"{lead}')
        known = c.acknowledged(scope)
        best = r.best_cited_rank(scope)
        extra = f" (+{len(known) - len(c.cites)} named in prose)" if scope == "body" else ""
        if best is None:
            print(f"    knows     {len(c.cites)} cited{extra}; none of them scored")
        else:
            name = r.scores[best - 1][0]
            print(
                f"    knows     {len(c.cites)} cited{extra}; best is {name} "
                f"at rank {best} of {len(r.scores)} ({r.score_of(name):.4f})"
            )
        rows = r.uncited(scope)[:top]
        if not rows:
            print("    nothing unnamed scores at all")
            continue
        head = r.outranking(scope)
        for rank_i, req, score in rows:
            mark = "->" if any(rank_i == h[0] for h in head) else "  "
            note = "  outranks everything this contract names" if mark == "->" else ""
            print(f"   {mark} rank {rank_i:>2} of {len(r.scores)}  {req}  {score:.4f}{note}")
        if not head:
            quiet += 1
            print("      nothing here outranks the contract's own best citation")
    print()
    print(
        f"Advisory only; nothing above failed. {quiet} of {len(ranked)} contract(s) had no "
        "outranking suggestion at all."
    )


def emit_ground_truth(ranked: list[Ranked], *, label: str, requirements: dict[str, str]) -> None:
    print(f"=== ground truth: {label} — {len(requirements)} requirements ===")
    for scope in SCOPES:
        print()
        print(f"--- citation scope: {scope} " + "-" * 46)
        for r in sorted(ranked, key=lambda x: x.contract.relpath):
            name = Path(r.contract.relpath).name
            if name not in GROUND_TRUTH:
                continue
            expected = GROUND_TRUTH[name]
            uncited = r.uncited(scope)
            top5 = ", ".join(f"{req}@{i}" for i, req, _ in uncited[:5]) or "(nothing uncited)"
            head = ", ".join(f"{req}@{i}" for i, req, _ in r.outranking(scope)) or "(silent)"
            print(f"  {name}")
            print(f"    top-5 uncited : {top5}")
            print(f"    headline      : {head}")
            if expected:
                for req in sorted(expected):
                    pos = r.rank_of(req)
                    upos = next((n for n, (_, q, _) in enumerate(uncited, 1) if q == req), None)
                    where = f"position {upos} in the uncited listing" if upos else "already cited"
                    print(
                        f"    ground truth  : {req} at rank {pos} of {len(r.scores)} corpus-wide, "
                        f"{where} ({r.score_of(req):.4f})"
                    )
            else:
                print("    ground truth  : audited clean — every suggestion above is a miss")
        print()
        print(f"    {'k':>3}  {'hits':>4}  {'shown':>5}  precision@k")
        for k in (1, 3, 5):
            hits, shown, p = precision_at(ranked, k, scope=scope)
            print(f"    {k:>3}  {hits:>4}  {shown:>5}  {p:.4f}")
        hits, shown, p = headline_precision(ranked, scope=scope)
        print(f"    headline sentence: {hits} hit(s) in {shown} claim(s)  precision {p:.4f}")
    print()


def emit_ablation(root, spec, contracts_dir, *, stoplist, stemming, scope) -> None:
    """Re-run the probe that killed the gate rule, against the headline surface.

    A clean contract that simply cites less densely is a style difference and not
    a defect, and it is what broke every threshold shape the prior sweep tried.
    Dropping one and two citations from each hand-audited clean contract asks the
    only question that matters for an advisory: **how loud does it get on clean
    work that happens to be sparse?** An advisory fails nothing, so a claim here
    costs a reader thirty seconds rather than a build — but a tool that shouts on
    every sparse contract is one a reader stops reading.
    """
    ranked, requirements = build(
        root, spec, contracts_dir, stoplist=stoplist, stemming=stemming, scope=scope
    )
    print("=== citation ablation over the hand-audited clean contracts ===")
    print(f"    scope {scope}; {len(requirements)} requirements")
    print()
    print(f"  {'contract':<24} {'dropped':>7}  {'cases':>5}  {'silent':>6}  {'worst':>5}  headline claims")
    total_cases = 0
    total_claims = 0
    total_silent = 0
    worst = 0
    for r in sorted(ranked, key=lambda x: x.contract.relpath):
        name = Path(r.contract.relpath).name
        if GROUND_TRUTH.get(name) != frozenset():
            continue
        c = r.contract
        for drop in (1, 2):
            counts: list[int] = []
            for combo in itertools.combinations(sorted(c.cites), drop):
                trimmed = Contract(
                    relpath=c.relpath,
                    title=c.title,
                    lead_heading=c.lead_heading,
                    subject=c.subject,
                    cites=frozenset(c.cites - set(combo)),
                    mentions=frozenset(c.mentions - set(combo)),
                )
                probe = Ranked(contract=trimmed, scores=r.scores, scope=scope)
                counts.append(len(probe.outranking(scope)))
            if not counts:
                continue
            silent = sum(1 for n in counts if n == 0)
            total_cases += len(counts)
            total_claims += sum(counts)
            total_silent += silent
            worst = max(worst, max(counts))
            print(
                f"  {name:<24} {drop:>7}  {len(counts):>5}  {silent:>6}  {max(counts):>5}  "
                f"{sum(counts)} total"
            )
    print()
    print(
        f"  {total_silent} of {total_cases} ablated clean cases were silent; the rest produced "
        f"{total_claims} headline claim(s), every one a false alarm, worst single case {worst}."
    )
    print("  All of them cost a reader a glance. None of them fails anything.")
    print()


def emit_sensitivity(root, spec, contracts_dir, *, top) -> None:
    print("=== sensitivity: the two parameters the prior sweep did not record ===")
    print()
    print(f"  {'stoplist':<9} {'stemming':<9} | " + " | ".join(
        f"{Path(k).stem[:18]:<18}" for k in sorted(GROUND_TRUTH)
    ))
    for stopname in ("minimal", "medium", "large"):
        for stemming in (False, True):
            ranked, reqs = build(
                root, spec, contracts_dir, stoplist=STOPLISTS[stopname], stemming=stemming
            )
            cells = []
            for key in sorted(GROUND_TRUTH):
                r = next((x for x in ranked if Path(x.contract.relpath).name == key), None)
                if r is None:
                    cells.append(f"{'-':<18}")
                    continue
                expected = GROUND_TRUTH[key]
                if expected:
                    req = sorted(expected)[0]
                    cells.append(f"{req}@{r.rank_of(req)}/{len(r.scores):<10}"[:18].ljust(18))
                else:
                    rows = r.uncited("header")
                    top1 = rows[0][1] if rows else "-"
                    cited = "cited" if r.best_cited_rank("header") == 1 else f"top={top1}"
                    cells.append(f"{cited:<18}")
            print(f"  {stopname:<9} {str(stemming):<9} | " + " | ".join(cells))
    print()
    print("  A rank that moves this much with a stoplist is a ranking, not a measurement.")
    print()


# --------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Advisory: requirements a contract's subject scores against but does not cite.",
        epilog="Always exits 0. This is not a gate and must not become one.",
    )
    ap.add_argument("--root", default=".", help="repository root")
    ap.add_argument("--spec", default=None, help="spec.md to read requirements from")
    ap.add_argument("--contracts", default=None, help="directory of contracts to score")
    ap.add_argument("--top", type=int, default=5, help="how many uncited requirements to list")
    ap.add_argument(
        "--stoplist", choices=sorted(STOPLISTS), default="medium", help="which stoplist"
    )
    ap.add_argument("--stemming", action="store_true", help="strip suffixes before comparing")
    ap.add_argument(
        "--scope",
        choices=SCOPES,
        default="body",
        help="what counts as already considered: the header field only, or the prose too",
    )
    ap.add_argument(
        "--ground-truth",
        action="store_true",
        help="score against the five hand-audited contracts and report precision@k",
    )
    ap.add_argument(
        "--sensitivity",
        action="store_true",
        help="show how the ranks move across stoplists and the stemmer",
    )
    ap.add_argument(
        "--ablation",
        action="store_true",
        help="drop citations from the clean contracts and count the false alarms",
    )
    ap.add_argument("--label", default="", help="label for --ground-truth output")
    ap.add_argument(
        "--contracts-at",
        metavar="REV",
        help="score the contracts as they stood at this git revision",
    )
    ap.add_argument(
        "--spec-at",
        metavar="REV",
        help="read requirements as they stood at this git revision",
    )
    args = ap.parse_args(argv)

    root = Path(args.root).resolve()
    with tempfile.TemporaryDirectory(prefix="cite-advisor-") as scratch:
        return _run(args, root, Path(scratch))


def _run(args, root: Path, scratch: Path) -> int:
    contracts_dir = Path(args.contracts).resolve() if args.contracts else None
    spec = (
        Path(args.spec).resolve() if args.spec else root / SPEC_SUBPATH
    )

    if args.contracts_at:
        contracts_dir, at_spec = checkout(root, args.contracts_at, scratch / "contracts-at")
        if not args.spec and not args.spec_at:
            spec = at_spec
    if args.spec_at:
        _, spec = checkout(root, args.spec_at, scratch / "spec-at")

    if not spec.is_file():
        print(f"no spec at {spec}", file=sys.stderr)
        return 0  # still advisory: a missing input is not a failure

    if args.sensitivity:
        emit_sensitivity(root, spec, contracts_dir, top=args.top)
        return 0

    if args.ablation:
        for scope in SCOPES:
            emit_ablation(
                root,
                spec,
                contracts_dir,
                stoplist=STOPLISTS[args.stoplist],
                stemming=args.stemming,
                scope=scope,
            )
        return 0

    ranked, requirements = build(
        root,
        spec,
        contracts_dir,
        stoplist=STOPLISTS[args.stoplist],
        stemming=args.stemming,
        scope=args.scope,
    )

    if args.ground_truth:
        emit_ground_truth(
            ranked,
            label=args.label
            or f"contracts={args.contracts_at or 'working tree'} "
            f"spec={args.spec_at or args.contracts_at or 'working tree'}",
            requirements=requirements,
        )
        return 0

    emit(ranked, top=args.top, requirements=requirements, scope=args.scope)
    return 0


if __name__ == "__main__":
    sys.exit(main())
