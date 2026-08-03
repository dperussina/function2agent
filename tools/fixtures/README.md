# Fixtures

Two miniature corpora, laid out like the real one so the same `config.json`
applies to both without special-casing.

| Tree | What it is for |
|---|---|
| `known-bad/` | One deliberate instance of every failure class the checker claims to catch. `selftest.py` asserts each check fires here. |
| `known-good/` | The same content with every defect repaired, plus the constructs that have historically produced *false* positives — an escaped pipe in a table cell, a DOI, a vendor price, a subset range in prose, a `"verdict"` field name, a struck correction, a copied prohibition. Every check must be silent here. |

`specs/001-fixture/harness/probe/results/` is a pair rather than a single case,
and the pairing is the point: the two run directories state the same three
conclusions, and the only difference between them is that one declares
`dry_run: true`. `known-bad` holds the dry run stating them plainly under a
banner two screens away; `known-good` holds the same dry run with each
conclusion withheld on its own line, beside a live run stating them freely.

Neither tree is scanned by a normal run: `config.json` excludes `tools/fixtures/*`
and does not list `tools/` among its roots.

`known-bad/README.md`'s last bullet is a pair too, and it exists for
`gen_claims.py` rather than for a check: a stale register range sitting on a
line that also carries a struck one. The struck range makes the line a
correction record, so the generator classifies the live range as `MANUAL` —
reported, never written, because the dated note beside it is the other half of
the claim. `register-range` fires on it regardless, which is the point: it is
the only mechanism at a site the generator declines.

Run all four directions — every check fires, no check fires on good input, the
generator finds every stale claim, and it writes digits and nothing else — with:

```
python3 tools/selftest.py
```

A check with no `known-bad` case is not finished. A check that fires on
`known-good` is worse than no check at all, because it teaches the next person
to ignore output.
