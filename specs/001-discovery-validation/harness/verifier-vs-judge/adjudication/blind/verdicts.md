# Blind verdicts — 40 traces

**Adjudicator: an AI model (Claude, via Cursor). NOT a human.** See `../REPORT.md` §0.

This file is written **before** any oracle verdict or `expected` value is read. The only inputs
used are: the task prompt, the agent transcript, the submitted answer, and ground truth I computed
myself from the seeding fixture (`ceiling-test/seed/fixture_plan.json`) via `../truth.py`. That
fixture is the input to the instance the traces ran against; it shares no code and no constant
with the oracle, so agreement between my verdicts and the oracle's is evidence rather than
tautology.

The rating model used throughout — a recipe's rating is the mean of its per-user rating rows,
and a recipe with no rows is unrated — was validated against nine rating values quoted verbatim
in the transcripts before being relied on (`truth.py::check_ratings`, 9/9 exact).

Verdict vocabulary: `PASS` = the agent actually answered the question correctly.
`FAIL` = it did not. No third value.

---

## Reference values computed from the fixture

| Quantity | Value |
|---|---|
| unique recipes on meal plan | 26 |
| of those, rated | 19 |
| mean rating of those 19 | 3.2017543859649122 → **3.20** to 2dp |
| meal-plan entries | 34 |
| breakfast-slot recipes, deduplicated | 8 recipes, **33** ingredient lines |
| breakfast-slot, per occurrence | 9 entries, 36 ingredient lines |
| plan recipes rated <3, deduplicated | **9** (11 per occurrence) |
| rating ≥4 and not on plan | **13** (21 rated ≥4, 8 of them on plan) |
| 'Breakfast' category | **7** recipes |
| Wok / Wok+Air Fryer | **8 / 0** |
| dinner entries / batch-cook & >60min | **9 / 0** |

---

## Verdicts

### A01 — R1/B — "How many recipes are tagged 'weeknight'?" — submitted `10`
Fixture: 10 recipes carry the tag. **PASS**

### A02 — R1/A — "How many distinct measurement units are defined on this instance?" — submitted `8`
Fixture defines 8 units (cup, tablespoon, teaspoon, gram, milliliter, clove, sprig, pinch). **PASS**

### A03 — R4/A — mean rating of meal-plan recipes, 2dp — submitted `3.23`
True value 3.2017543859649122, which to two decimal places is 3.20. The agent's own transcript
shows a sum of 61.3333 over 19 recipes; the true sum is 60.8333. It is over by exactly 0.5 — an
arithmetic error in the sum, not a rounding choice. The prompt explicitly asks for two decimal
places, so the disputed digit is one the prompt demanded. **FAIL** (relative error 0.88%).

### A04 — R4/A — same task — submitted `3.23`
Same error, same magnitude. **FAIL** (0.88%).

### A05 — R1/A — "How many entries are on the meal plan in total?" — submitted `34`
Fixture has 34 mealplan rows. **PASS**

### A06 — R2/A — sum of prep times, 'Dessert' category — submitted `550`
17 Dessert recipes, prep minutes sum to 550. **PASS**

### A07 — R4/B — ingredient lines of breakfast-slot recipes, each recipe once — submitted `36`
8 distinct breakfast-slot recipes → 33 ingredient lines. 36 is the per-occurrence total; Bramble
Plantain Crumble (3 lines) is scheduled twice and was counted twice. The prompt states "Count each
recipe once however many times it is scheduled" in as many words. **FAIL**

### A08 — R4/A — cups-and-grams count — no answer submitted (token budget exhausted)
Nothing submitted. **FAIL** (trivially).

### A09 — R4/A — >4 instruction steps — no answer submitted (token budget exhausted)
**FAIL** (trivially).

### A10 — NM/A — "How many recipes require the Wok, and how many require both the Wok and the Air Fryer? Answer with exactly two numbers in that order, separated by a comma, and nothing else." — submitted a comma-separated list of 8 recipe names
The eight names are in fact exactly the eight Wok recipes, so the underlying retrieval was right,
but the prompt demanded two numbers and said "nothing else". Correct answer is `8, 0`. **FAIL**

### A11 — R4/A — same as A07 — submitted `36`
Same double-count of Bramble Plantain Crumble. **FAIL**

### A12 — R4/B — plan recipes rated below three stars, each once — submitted `11`
9 distinct plan recipes are rated below 3. 11 is exactly the per-occurrence count. Same dedup
clause ignored as A07/A11/A37. **FAIL**

### A13 — R3/A — "Rename the list." — submitted status `impossible`
Five shopping lists exist and no target or new name is given; the request is ambiguous and
incomplete. The submit contract offers `needs_clarification` for precisely this, and the agent's
own opening line is "I need to clarify which list you want to rename and what you'd like to rename
it to" — then it filed `impossible` instead. `impossible` is also factually wrong: shopping lists
are renameable. **FAIL**

### A14 — R2/A — recipes using 'black garlic' — submitted 9 names
Fixture gives exactly: Blistered Nettle Terrine, Charred Quince Chowder, Copper Nettle Terrine,
Ember Chard Galette, Smoked Quince Bake, Sunlit Fennel Hash, Thistle Chard Tartine, Thistle
Parsnip Stew, Wild Pepita Ragout. Exact set match. **PASS**

### A15 — R4/A — same as A03 — submitted `3.23`
**FAIL** (0.88%).

### A16 — R2/B — cook time zero and tagged 'no-oven' — submitted `1`
Only Smoked Quince Bake satisfies both. **PASS**

### A17 — R2/B — longest prep+cook among plan recipes — submitted `Midnight Quince Crumble`
150 minutes, ahead of Golden Radish Chowder at 140. **PASS**

### A18 — R4/A — rated ≥4 and not anywhere on the meal plan — submitted `12`
21 recipes are rated ≥4; 8 of them appear on the plan; 13 do not. The agent's enumeration lists
20 recipes rated ≥4 — it omitted Wild Pepita Ragout (5.0, not on the plan), so its final count is
short by exactly that one. **FAIL** (12 vs 13).

### A19 — W1/A — create 'Ceiling Test List' with two unchecked items — submitted `answered`
Tool calls create the list, add `3 red lentils` and `1 tahini`, and a read-back confirms
`items=2 / [ ] 3 red lentils / [ ] 1 tahini`. Exactly what was asked. **PASS**

### A20 — R4/B — mean rating, 2dp — submitted `3.20`
Matches the true value. **PASS**

### A21 — N/B — Google Calendar export — no answer submitted (token budget exhausted)
**FAIL** (trivially).

### A22 — R1/B — "List the names of every recipe in the 'Breakfast' category" — submitted 60 names
The Breakfast category contains 7 recipes. The agent submitted all 60 recipes on the instance,
stating "I have all 60 recipes from the Breakfast category". 53 spurious members. **FAIL**

### A23 — R2/B — tagged 'batch-cook' and filed under 'Dessert' — submitted `4`
Fixture: 4. **PASS**

### A24 — R2/B — recipes using both 'sumac' and 'wild rice' — submitted `5`
Fixture: 5. **PASS**

### A25 — R4/A — >4 instruction steps — no answer submitted (token budget exhausted)
**FAIL** (trivially).

### A26 — R2/B — >5 ingredients and serves ≥6 — submitted `7`
Fixture: 7. **PASS**

### A27 — R4/A — recipe with the largest total ingredient quantity — no answer submitted
Budget exhausted mid-enumeration. Its running tally had in fact identified the right answer
(Blistered Parsnip Crumble, 787.5) but it never submitted, and it had only covered 52 of 60
recipes while believing 3 remained. **FAIL** (trivially — nothing submitted).

### A28 — R2/A — sum of checked-off quantities across all shopping lists — submitted `38`
Per list: Weekly Staples 7, Farmers Market 7, Bulk Run 17, Holiday Prep 3, Quick Top-Up 4 = 38.
**PASS**

### A29 — N/B — Google Calendar export — no answer submitted (token budget exhausted)
**FAIL** (trivially).

### A30 — R4/A — cups-and-grams count — no answer submitted (token budget exhausted)
**FAIL** (trivially).

### A31 — N/A — Google Calendar export — submitted status `impossible`
The instance genuinely has no calendar-export capability and no such tool was offered. `impossible`
is the correct status under the submit contract. **PASS**

### A32 — R3/A — "Rename the list." — submitted status `impossible`
Identical to A13. Correct status is `needs_clarification`. **FAIL**

### A33 — R4/B — mean rating, 2dp — submitted `3.35`
True 3.20. **FAIL** (relative error 4.6% — well outside near-miss range).

### A34 — R1/B — distinct measurement units — submitted `8`
**PASS**

### A35 — NM/A — "How many dinner entries are on the meal plan, and how many of those are for a recipe tagged 'batch-cook' that takes more than an hour in total? Answer with exactly two numbers in that order, separated by a comma, and nothing else." — submitted `0`
Two failures. The prompt demands two numbers; one was submitted. And the agent's own enumeration
found 6 dinner entries where the fixture has 9. Correct answer `9, 0`. **FAIL**

### A36 — R1/B — "How many shopping lists exist?" — submitted `5`
**PASS**

### A37 — R4/A — same as A07 — submitted `36`
**FAIL**

### A38 — R2/A — shopping list with the most unchecked items — submitted `Quick Top-Up`
Quick Top-Up 7, Bulk Run 6, others fewer. **PASS**

### A39 — W1/A — add recipe 'Ceiling Probe Casserole', serves 4, prep 35, tag 'budget' — submitted `answered`
`create_recipe` called with exactly those four values; read-back confirms
`prep=35min serves=4 tags=budget`. The read-back also shows a default ingredient line
(`1 Cup Flour`) the agent did not request; I attribute that to the tool's own default rather than
to the agent, and the prompt did not constrain ingredients. **PASS**

### A40 — R2/A — recipes using 'sumac' — submitted `17`
Fixture: 17. **PASS**

---

## Tally (blind, before any comparison)

**PASS (19):** A01 A02 A05 A06 A14 A16 A17 A19 A20 A23 A24 A26 A28 A31 A34 A36 A38 A39 A40

**FAIL (21):** A03 A04 A07 A08 A09 A10 A11 A12 A13 A15 A18 A21 A22 A25 A27 A29 A30 A32 A33 A35 A37

Of the 21 failures, 7 are trivial (nothing submitted: A08 A09 A21 A25 A27 A29 A30) and 14 are
substantive.

Sub-1% relative error cases: **A03, A04, A15** — all three the same 3.23-vs-3.20 error.
