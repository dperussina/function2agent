# Fixture repository

One research document, three findings, and an index.

Route recall is **0.8961** at precision **1.0000**, and the validated contract
reading is **0.7681**
([finding 001](specs/001-fixture/findings/001-alpha.md)).

Total spend was **$41.03**. The decision register (~~D-01 … D-02~~ D-01 … D-03)
carries the settled positions; see
[`14-fixture-synthesis.md`](research/14-fixture-synthesis.md)
and its [decision register](research/14-fixture-synthesis.md#1-the-decision-register).

Vendor pricing, for reference: the hosted runtime bills $0.08/hr, so nobody should argue the case on the $0.08 line.
A published benchmark puts a comparable agent at $5.07 <https://example.invalid/benchmark>.

Finding 002 is the reachability probe.

Figures whose authoritative occurrence touches other characters, which an exact
match must still accept: symbol recall **0.9987**, sitting in the finding with a
`*` on its left and a `(` on its right; the **$18.15** subtotal, whose finding
writes it after a `$` and before a space; and precision **0.8000**, which ends
its finding's sentence against a full stop. None of these is a substring of a
longer number, and all three must stay silent.

A multiplier may be quoted coarser than it was measured, and that is why its
lookup is not an exact match. The join ratio reads **2.9×** here against a
finding that writes `2.94×`: the same figure rounded to the place it is quoted
to, and it must stay silent. The per-family ratio reads **3.7×**, and the finding
carries both `3.7×` and a `13.7×` outlier — the anchored lookup must find the
first and must not be satisfied by the second, so a longer number that happens to
end in the quoted one is neither an acceptance nor a reason to reject.

## Constructs that sit just outside a threshold

Each of these is legitimate and must stay silent, and each sits exactly one unit
outside the bound that would otherwise report it. Together with the planted
defects in `known-bad`, they are what makes each bound testable in both
directions: narrow one by a unit and the case below starts being reported.

A bare rate of one decimal place is a floor, a band edge or a scale, not a rate,
so it is not paired with a count beside it, and pairing the two below would
report a disagreement that does not exist:

The pre-registered floor was 0.9 (27 of 41).

A parenthesised number after a count is not always that count's rate, and a
count inside a parenthesis after a rate is not always that rate's count. Both
pairings reach a fixed number of words and stop, and both lines below sit one
word beyond that reach — so widening either pairing by a word turns one of them
into a false report of arithmetic that was never claimed:

In that ladder 22 of 41 arms cleared the pre-registered floor (90.0%), which is
the floor's own value and not the share of arms that cleared it.

The floor itself was 90.0% (cleared by all but 3 of 41), where the fraction
counts the arms that missed it rather than restating the floor.

A repository identifier with a four-digit leading group parses as a four-decimal
rate the moment the integer-part cap is relaxed, and the citation pattern does
not name every repository: Zenodo 2026.0238 is an identifier and not a
measurement.

Two definitions are one short of switching a namespace on, and a namespace that
is off must stay silent about references it cannot resolve:

- **P-01**: the first of only two pending experiments defined here.
- **P-02**: the second, which leaves this register one short of enforcement.

Nothing defines P-05, and while the P namespace is below the definition floor
nothing may say so.

A pipe row that belongs to no table is set-cardinality notation, and it sits
further from the table above it than the orphan-row bound reaches. The table
first, complete:

| Arm | Served |
|---|---|
| R1 | 22 |
| R2 | 24 |



|P ∩ A_c| / |A_c ∩ (S ∪ N)|

That is one row, three blank lines below a closed table: too far to be a row that
fell out of it, and alone, so it is not a table missing its delimiter either.

## Multipliers a finding states in prose rather than with a sign

Typing the multiplier lookup is only safe if it accepts every shape the findings
actually use, and they do not all use the sign. Each line below is legitimate and
must stay silent; each one is also the sole fixture for one accepted form, so
dropping that form from the accept set turns this section into three violations
while the corpus it was meant to protect stays quiet.

Token use fell by **6.4×** once the cache was warm, which the finding states as
"a factor of 6.4".

The arms finished **8.2×** apart on wall clock, which the finding states as "a
ratio of 8.2".

The tool arm was **35×** cheaper, which the finding states only as "1/35th of the
baseline's cost" — the reciprocal, carrying the magnitude in its denominator. In
the real corpus this form is the sole authority behind eight `35×` claims, so a
typed rule that missed it would strip provenance from all eight.

## A multiplication sign that is an operator, not a suffix

Nested per-loop caps multiply: 5 × 5 × 5 = 125 model calls, so a global budget is
the only thing that bounds the tree. Those are operators with a space in front of
them, and no finding measures a `5×` anything — so admitting the space into the
suffix pattern turns this arithmetic into three unsourced multiplier claims, and
on the authority side it would put somebody's *operands* into the accept pool as
though a finding had measured them.
