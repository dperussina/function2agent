# Finding 001 — Alpha

**Result.** Route recall is **0.8961** (69 of 77) at precision **1.0000**.
Contract extraction clears the gate at 60/69 = 0.8696 on the literal reading and
misses at 53/69 = 0.7681 on the validated one.

Coverage from the handler body alone is 15 of 69 endpoints (21.7%).
Symbol recall is **0.9987** (16,655 of 16,677).

**Model spend**: $41.03 across four sessions, of which $18.15 is E4.
Components: $7.59 and $10.56.

The join ratio is **2.94×** on the post-fix basis. The per-family ratio runs to
**3.7×** wherever it succeeds at all, and one outlier task reached **13.7×** —
two separate figures, and a lookup that confuses them is reading the wrong one.

Three multiplicative facts this finding states in prose rather than with a sign,
because that is how the real findings state them too. Token use fell by a factor
of 6.4 once the cache was warm. The arms finished at a ratio of 8.2 on wall
clock. And the tool arm ran at 1/35th of the baseline's cost, which is the only
form in which that particular figure is stated anywhere.
