# Fixture repository

Three research documents and an index. (The claim in that sentence is wrong:
there are two research documents plus the index, so `inventory-count` fires.)

## Numbers with no source

The reachability probe scored **0.7734** on the withheld-schema arm — a figure
no findings document records and which appears nowhere else in this corpus.

Total spend across the programme was **$41.03**, quoted here and in the plan and
recorded in neither.

The component figures sum to $18.15 ($7.59 + $10.55).

## References that do not resolve

- The decision register (D-01 … D-02) carries the settled positions.
- Route recall is **0.8961** at precision **1.0000**
  ([finding 010](specs/001-fixture/findings/004-delta.md)).
- Background: [the missing document](research/99-nope.md).
- Jump to [the eventual conclusion](research/14-fixture-synthesis.md#9-the-conclusion).
- Superseded by finding 013, which does not exist.
- Refreshed 2026-01-01: the decision register reads ~~(D-01 … D-02)~~ (D-01 … D-03), D-03 having landed that day. The dated log is the other half of this claim, so `gen_claims.py` reports this range and must not rewrite it.

## A figure that is only a substring of a real one

Nine findings and an index. (Also wrong: there are five findings here. The rule
that catches this demanded a trailing comma until 2026-08-03, so the sentence
had to be punctuated the checker's way before the checker would read it.)

Selection agreement was **0.5312**, which no finding reports. What one finding
does contain is `0.53127`, and a substring test cannot tell the two apart — so
this line read as a figure with provenance until the lookup was made exact.

Route recall was **0.8964**, which no finding reports either. What one finding
does write is `89.6%`, and while the aliases included a one-decimal percentage
that rounded form covered six different four-decimal values, this one among
them.

## A multiplier quoted from a longer one

A multiplier is the one figure this corpus quotes coarser than it measured, so
its lookup cannot demand an exact match the way a four-decimal rate does. Left
unanchored at *both* ends, though, it accepted figures that are not the quoted
one at all. Three shapes, one per hole:

The tool arm was **3.7×** cheaper on the aggregable tasks. No finding says so —
what one finding writes is `13.7×`, an order of magnitude out, and an unanchored
substring test cannot tell the two apart, so this line read as sourced.

The noise floor moved by **4.8×** between replications. The nearest finding
writes `4.8999×`, which rounds to 4.9. A left anchor alone accepts this, because
`4.8` is a prefix of it; but a different figure sharing a prefix is not the same
figure measured more precisely, which is what the rounding bound is for.

The per-family ratio was **3.4×**. One finding writes `3.46×`, which is six
tenths of a unit away in the quoted figure's last place and rounds to 3.5. This
row is what makes the rounding bound itself testable: widen it to a whole unit
and this line goes quiet while the number stays unsourced.

## Defects planted against a threshold rather than past it

Every case below sits one unit outside the bound that catches it, so moving that
bound one unit makes it disappear. A defect planted comfortably past a threshold
proves the check fires and proves nothing about the number it compares against —
which is how `TOLERANCE = 2` survived in a rule whose every fixture drifted by 26
lines or more.

A block of exactly two pipe rows with no delimiter row, which is the shortest run
`table-no-delimiter` will speak on:

| Arm | Served |
| R3 | 41 |

Two register ranges listed on one line make it a register summary without
parentheses, and two is the whole bound: the D range below is stale against a
register that runs to D-04, and the P range is there only to make the line a
list. Nothing defines P, so that namespace stays switched off.

The registers stood at D-01 … D-02, P-01 … P-02 when this line was written.

A count and a rate that disagree by seven tenths of a unit in the rate's last
place — past the half-unit rounding allowance, and inside a whole one: the
literal reading is 60/69 = 0.8695.

A rate quoted to exactly two decimals, which is the coarsest bare rate the rule
reads as a rate at all: the withheld-schema arm is 60/69 = 0.92.

Four words between the count and its parenthesised rate, which is exactly as far
as that pairing reaches — and both halves must sit on one line, because the rule
never joins two:

Coverage from the handler body is 15 of 69 measured Python route handlers (12.7%).

Three words inside the parenthesis before the count, likewise exactly as far as
that pairing reaches:

Symbol recall came back at 0.9987 (matched against ast 16,655 of 16,777).

## A multiplier quoted from a quantity that is not one

The three above are about *where* a multiplier lookup may reach. These three are
about *what kind of thing* it may reach for, which is the hole that let a dollar
amount source a ratio in the real corpus. Each of them goes quiet the moment the
lookup goes back to matching authority text instead of authority figures:

The tool arm was **2.6×** cheaper per solved task. The only thing any finding
writes near that value is `$2.6134`, a total spend — and a spend is not a ratio,
however close the digits sit. This is the E7 defect reproduced in miniature.

The ladder's fourth rung was **5.3×** the first. One finding does contain a
standalone `5.3`, stated with no unit because it is a token count; an untyped
lookup matches it exactly and reads this line as sourced.

## A spend quoted from a quantity that is not money

The symmetric hole, which had no instance in the real corpus and is planted here
because that is the only way to hold it. One session cost **$7.42**. A finding
writes `7.42` — the same digits, standing alone, with no `$` in front of them,
because there it is not a dollar amount. Drop the `$` requirement and this line
reads as sourced.

The filename branch of `link-label` had no firing site in either fixture until
2026-08-10 — every planted filename label agreed with its target, so the branch
was held only in the direction that passes. This label names one document and
the link goes to another: [`research/01-fixture-metrics.md`](research/14-fixture-synthesis.md).
