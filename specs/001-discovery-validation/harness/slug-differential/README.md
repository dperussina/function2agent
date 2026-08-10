# `slug-differential` — `slugify` measured against GitHub's own renderer

**What it measures.** `corpuscheck.corpus.slugify` computes the heading anchor that the
`link-anchor` check resolves every `#fragment` against. This harness walks every markdown
document in the corpus, enumerates its headings, fetches the same document's rendered HTML
from GitHub, reads the `id` GitHub actually emitted for each heading, and compares the two
position by position. The renderer is the oracle; nothing here is an argument about what
GitHub's algorithm is documented to do.

**Why it exists.** For as long as `slugify` was described rather than measured, it invented
anchors no rendered page carried, `link-anchor` computed every target with the same defect,
and two committed links were written to match the invention and passed a green gate. This
instrument found four families nothing else had: the underscore family, the circled-digit
family, the leading/trailing trim family, and the `109` blockquoted headings no enumerator
had ever reached.

## Posture

| | |
|---|---|
| Network | **yes** — outbound HTTPS to `api.github.com`, `GET` only. The renderer is not vendorable, which is the whole reason this exists. |
| Privilege | **none.** Any euid; no root, no container, no kernel facility. |
| Writes | **nothing.** Not into the repository, not into `/tmp`, not into `examples/`. |
| Model spend | **$0.00.** No model is called. |
| Credentials | a GitHub token is read and **never printed, logged or returned** — only its source is named. |

**This is why it is not in `tools/`.** `tools/README.md` declares that tree Python 3.11+,
standard library only, **no network**, and that constraint is real rather than aspirational:
the only `urllib` import anywhere under `tools/` is `urllib.parse`. An instrument whose
oracle is a live renderer cannot live there without breaking the claim that makes the rest
of `tools/` auditable.

## Running it

```bash
export PATH="$PWD/.venv/bin:$PATH"
cd "$(git rev-parse --show-toplevel)"

# offline; plants the known misbuild and shows the zero-anchor floor firing
python specs/001-discovery-validation/harness/slug-differential/slug_differential.py --self-test

# the whole corpus at HEAD
python specs/001-discovery-validation/harness/slug-differential/slug_differential.py

# one subtree
python specs/001-discovery-validation/harness/slug-differential/slug_differential.py --path tools
```

A token is optional for a subtree and **required for a whole-corpus run**: unauthenticated
`api.github.com` allows 60 requests an hour and the corpus is well past a hundred documents.
`GITHUB_TOKEN` and `GH_TOKEN` are read, and `gh auth token` is the fallback. **The ref must be
pushed** — the contents endpoint renders a commit the remote has, so a local-only commit
returns HTTP 404 and is reported as such rather than as a corpus difference.

## The detail a rebuild has already got wrong twice

The endpoint is the **contents** endpoint with a rendering `Accept`:

```
GET https://api.github.com/repos/<owner>/<repo>/contents/<path>?ref=<ref>
Accept: application/vnd.github.html+json
```

**The `id` is not on the heading element.** It sits on an `<a class="anchor">` *beside* the
heading text:

```html
<h2 dir="auto">Title<a id="user-content-title" class="anchor" href="#title"></a></h2>
```

A rebuild that read `id` off the `<hN>` returned zero ids for every document — and because
zero ids is also a wrong *count*, it reported a heading-count mismatch on every document
rather than an error. That reading's plain meaning is "the corpus moved under the harness",
which points a reader at the corpus instead of at the instrument. It is the quiet direction,
and it is the reason `_anchor_count_or_die` runs **before** any count is compared.

Two neighbouring endpoints fail differently and are worth naming so a rebuild does not reach
for them: plain `Accept: application/vnd.github+json` returns base64 source with no anchors,
and `POST /markdown` renders GFM but emits bare `<h2 dir="auto">` with **no `id` and no
anchor element at all**.

## What fails loudly, and what a wrong number would have looked like

Every one of these is a non-zero exit. The list is the point of the file: the misbuild's
failure mode was a plausible number, and a harness whose failure mode is a number rather
than an error measures nothing while looking like it measured.

| condition | why it is an error rather than a count |
|---|---|
| a document renders **zero anchors** while its source has headings | every extraction failure produces exactly this, and as a count it reads as corpus drift |
| the anchors' `id` and `href` disagree | the same slug read two ways is not one value, and averaging them hides which is wrong |
| walked and rendered heading counts differ | both sides are pinned to one commit, so this is an enumeration difference and cannot be drift |
| **zero headings compared overall** | a total of zero is what a broken walker returns and it is also what a pass would print |
| the ref is absent from the remote | HTTP 404 named as such, rather than counted as a missing document |
| a document absent at the ref | named, rather than silently skipped |

**Both sides are read at one revision.** Document text comes from `git show <ref>:<path>`,
never from the working tree. Comparing newer local text against an older rendered page
produces a count mismatch that looks precisely like a parser defect — it happened, and it
cost a reader that conclusion. Pinning both sides makes the class impossible rather than
merely unlikely, and it means a dirty tree cannot perturb a run.

The `--self-test` arm drives the real misbuild class rather than a mock: `HeadingElementIds`
is the wrong extractor, kept in the source, and the test asserts both that it finds nothing
and that finding nothing raises. **Removing the floor makes `--self-test` exit 1 and name the
vacuity**, which is the check that the plant is a negative control rather than decoration.

## What it cannot reproduce

- **It cannot certify `slugify` over a corpus it did not walk.** Every figure it produces is a
  dated count over the documents present at one commit, and the walked set grows whenever the
  corpus does. The two reading sites — `slugify`'s docstring and `tools/README.md`'s
  `link-anchor` row — carry the figure dated to a commit for that reason.
- **It cannot be replaced by a committed table of ids, and there is deliberately no
  `results/` directory here.** A recorded ground truth stops being ground truth the moment
  the renderer changes, and the renderer is not ours. The only committed HTML is the two-line
  `_FIXTURE` in the source, which certifies *which element position each extractor reads* and
  certifies nothing whatever about `slugify`.
- **It cannot tell a renderer change from a `slugify` regression.** A future divergence means
  the two disagree; which one moved is a question for the commit history of each.
- **It does not measure `toc-coverage` or the duplicate-suffix numbering as such.** It compares
  final slugs, so a suffix defect would surface as a divergence without being named as one.

## Provenance

Reconstructed from prose, and the reconstruction **corroborates rather than restates** — which
is the distinction [the harness index](../README.md#what-recovered-means-and-what-it-does-not)
draws between the two files in this tree that were rebuilt rather than recovered. The earlier
runs that found the four families were never committed; this file was rebuilt from the method
recorded in `slugify`'s docstring and `tools/README.md`, and then **run against the live
renderer, which is what makes it evidence**. Executed 2026-08-10 at `58a6277`: `2537` headings
compared — `2428` anchored at `^#` plus `109` blockquoted — `0` diverged, `0` errors, over
`136` documents. That is an independent re-derivation of the agreement `tools/README.md`
records at `7a60dd3` over the `2534` headings the corpus held then, taken with a separately
written walker at a later commit.

**The committed form of the file was then run from a clean detached worktree at its own
commit**, which is the reproduction SC-005 actually asks for — the earlier run measured a
working tree, and a harness verified only before it was committed has not been verified in the
shape a stranger receives. At `ac99926`, over `137` documents: `2439` anchored at `^#` plus
`109` blockquoted, `2548` compared, `0` diverged, `0` errors, exit `0`.

The three dated figures move — `2534` at `7a60dd3`, `2537` at `58a6277`, `2548` at `ac99926` —
and the last two commits in that sequence are the ones that added this directory and a section
to `tools/README.md`. **The instrument's own commits enlarge the population it counts**, which
is the second of the two ungateable kinds in
[`tools/README.md` § When a figure may be a live total](../../../../tools/README.md#when-a-figure-may-be-a-live-total-and-when-it-must-be-dated)
and the reason none of the three is written as a current total.
