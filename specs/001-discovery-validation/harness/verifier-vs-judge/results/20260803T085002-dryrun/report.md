# E8 verifier-vs-judge — results

> ## DRY RUN — NOT RESULTS
>
> No model was called. Every judge verdict below comes from `judge.StubJudge`, a deterministic hash of the trace key. The judge metrics, the AUROC, the fail-open rate and every decision-table row derived from them are **meaningless as findings** and exist only to prove the pipeline runs end to end.
>
> The verifier arms, the taxonomy, the denominators, the controls and the cost projection are computed from the frozen corpus and are real.

## Eligibility — Amendment B3.2

- Rule: PREREGISTRATION.md Amendment B3.2, as corrected by B4
- Battery under test: `1.4.0-probe`
- Population: **eligible records only (195 of 246; 51 excluded by Amendment B3.2)**
- Policy on unattested records: `exclude`

| Status | n | negatives | positives | false successes |
|---|---|---|---|---|
| `eligible_same_battery` | 103 | 7 | 96 | 2 |
| `eligible_value_attested` | 92 | 8 | 84 | 8 |
| `ineligible_stale` | 7 | 1 | 6 | 1 |
| `ineligible_unattested` | 44 | 4 | 40 | 0 |

**Cost in task families.** The exclusion is not spread evenly. 4 of 7 families go to zero — N (16), NM (7), R3 (14), W1 (14) — leaving R1, R2, R4.

Every record of every lost family lives in a run that executed a superseded battery, so **no setting of `eligibility.on_unattested` recovers any of them**; only re-running the battery does. Read every arm's coverage below as coverage of R1/R2/R4 traces, not of the corpus.

51 record(s) were excluded before selection, so no arm scored them.

**Stale — B3.2's own exclusion (7).** Each of these agents was graded against an expectation the battery no longer holds, so it answered a different question from the one every arm is shown. Itemised in full because this is the defect, not a side effect:

  - `20260802T154826-calibration/NM.001/A/1` [fail, false_success] — stored expected [] disagrees with the battery's [8, 0] (run executed battery 1.1.0)
  - `20260802T154826-calibration/NM.002/A/1` [pass] — stored expected 0 disagrees with the battery's [21, 0] (run executed battery 1.1.0)
  - `20260802T154826-calibration/NM.003/A/1` [pass] — stored expected [] disagrees with the battery's [8, 0] (run executed battery 1.1.0)
  - `20260802T160705-recalibration/NM.001/A/1` [pass] — stored expected [] disagrees with the battery's [8, 0] (run executed battery 1.2.0)
  - `20260802T160705-recalibration/NM.002/A/1` [pass] — stored expected 0 disagrees with the battery's [21, 0] (run executed battery 1.2.0)
  - `20260802T160705-recalibration/NM.003/A/1` [pass] — stored expected [] disagrees with the battery's [8, 0] (run executed battery 1.2.0)
  - `20260802T160705-recalibration/NM.004/A/1` [pass] — stored expected 0 disagrees with the battery's [9, 0] (run executed battery 1.2.0)

**Unattested (44).** Cross-battery records with nothing to compare, so the join can be shown neither sound nor unsound. Grouped by run and cause; the full list is in `analysis.json`:

| Run | Cause | n | negatives |
|---|---|---|---|
| `20260802T151714-smoke` | check kind 'impossible' | 2 | 1 |
| `20260802T151714-smoke` | check kind 'needs_clarification' | 2 | 0 |
| `20260802T151714-smoke` | check kind 'state' | 2 | 0 |
| `20260802T152825-smoke2` | check kind 'impossible' | 2 | 1 |
| `20260802T152825-smoke2` | check kind 'needs_clarification' | 2 | 0 |
| `20260802T152825-smoke2` | check kind 'state' | 2 | 0 |
| `20260802T154826-calibration` | check kind 'impossible' | 6 | 0 |
| `20260802T154826-calibration` | check kind 'needs_clarification' | 5 | 1 |
| `20260802T154826-calibration` | check kind 'state' | 5 | 0 |
| `20260802T160705-recalibration` | check kind 'impossible' | 6 | 0 |
| `20260802T160705-recalibration` | check kind 'needs_clarification' | 5 | 1 |
| `20260802T160705-recalibration` | check kind 'state' | 5 | 0 |

Denominators, against the sizes 6.3 preregistered before this rule existed:

| Denominator | n | 6.3 preregistered | difference | over |
|---|---|---|---|---|
| `N` | 15 | 20 | −5 | eligible records only (195 of 246; 51 excluded by Amendment B3.2) |
| `N_disc` | 10 | 13 | −3 | eligible records only (195 of 246; 51 excluded by Amendment B3.2) |
| `N_fs` | 10 | 11 | −1 | eligible records only (195 of 246; 51 excluded by Amendment B3.2) |

## Amendment required — the measured taxonomy disagrees with PREREGISTRATION.md 2.1

- n_negatives: preregistration says 20, mechanical classification counts 15
- no_output: preregistration says 7, mechanical classification counts 5
- protocol: preregistration says 2, mechanical classification counts 0
- false_success: preregistration says 11, mechanical classification counts 10
- numeric_value_error: preregistration says 8, mechanical classification counts 9
- set_cardinality_error: preregistration says 3, mechanical classification counts 1
- near_miss_n: preregistration says 2, mechanical classification counts 3

The counts above are mechanical, read off the oracle's own recorded reason strings. They are reported rather than reconciled: editing either side to agree would defeat the point of pre-registering the split.

## Controls

- PASS  **leak-assert fires (record)** — a payload embedding the oracle record aborts
- PASS  **leak-assert fires (value)** — the expected value in harness text aborts
- PASS  **leak-assert fires (reason)** — the oracle reason string aborts wherever it appears
- PASS  **leak-assert stays quiet** — a clean payload containing the English words 'reason' and 'outcome' in agent text does not abort
- PASS  **label-shuffle (b)** — mean AUROC over 1000 permutations = 0.4966 (range 0.267–0.753); must centre on 0.500 ± 0.05
- PASS  **label-shuffle (b_prime)** — mean AUROC over 1000 permutations = 0.4990 (range 0.248–0.777); must centre on 0.500 ± 0.05
- PASS  **constant-fail FPR** — FPR = 1.000; a verifier that flags everything must score 1.000, which is why the <= 5 pp admissibility constraint is not optional
- PASS  **constant-pass MD** — MD = 0.000, FPR = 0.000; both must be 0.000
- PASS  **constant-pass FPR** — FPR = 0.000; must be 0.000
- PASS  **constant-fail MD** — MD = 0.467; with 7 fail-open trace(s) the anchor must be strictly positive, and equal to the judge's fail-open rate
- PASS  **predicted-null (c1)** — c1 detected 0 of 9 numeric value errors; predicted 0.  [preregistration says 8 numeric value errors; the mechanical classification counts 9 — amendment required, the control ran over the measured set]

## Retired arm (d)

- **MD upper bound == judge fail-open rate** = 46.7 pp (7/15)
  - `MD(oracle-as-verifier) = |{oracle=fail and judge=pass and oracle=fail}| / |{oracle=fail}| = |{oracle=fail and judge=pass}| / |{oracle=fail}| = FO_judge, exactly`
  - PREREGISTRATION.md 3.3(1): this is a statement about the JUDGE. It MUST NOT appear in any sentence whose subject is the verifier, and it does not feed the decision table.

## Judge arm (b)

- D_judge: 53.3 pp (8/15; Wilson 95% 30.1–75.2 pp; numerator families: R4 8; over eligible records only (195 of 246; 51 excluded by Amendment B3.2))
- FO_judge: 46.7 pp (7/15; Wilson 95% 24.8–69.9 pp; numerator families: R1 1, R4 6; over eligible records only (195 of 246; 51 excluded by Amendment B3.2))
- CFO_judge: 13.3 pp (2/15; Wilson 95% 3.7–37.9 pp; numerator families: R4 2; over eligible records only (195 of 246; 51 excluded by Amendment B3.2))
- FPR_judge: 51.7 pp (31/60; Wilson 95% 39.3–63.8 pp; numerator families: R1 12, R2 14, R4 5; over eligible records only (195 of 246; 51 excluded by Amendment B3.2))
- flip_rate: 0.0 pp (0/75; Wilson 95% 0.0–4.9 pp; numerator families: none; over eligible records only (195 of 246; 51 excluded by Amendment B3.2))
- AUROC = 0.537, 95% CI [0.360, 0.711]
- judge noise floor = 0.0 pp (per-replicate detection [0.5333333333333333, 0.5333333333333333, 0.5333333333333333])
- unparsed verdicts = 0

## Judge arm (b_prime)

- D_judge: 40.0 pp (6/15; Wilson 95% 19.8–64.3 pp; numerator families: R1 1, R4 5; over eligible records only (195 of 246; 51 excluded by Amendment B3.2))
- FO_judge: 60.0 pp (9/15; Wilson 95% 35.7–80.2 pp; numerator families: R4 9; over eligible records only (195 of 246; 51 excluded by Amendment B3.2))
- CFO_judge: 33.3 pp (5/15; Wilson 95% 15.2–58.3 pp; numerator families: R4 5; over eligible records only (195 of 246; 51 excluded by Amendment B3.2))
- FPR_judge: 41.7 pp (25/60; Wilson 95% 30.1–54.3 pp; numerator families: R1 9, R2 10, R4 6; over eligible records only (195 of 246; 51 excluded by Amendment B3.2))
- flip_rate: 0.0 pp (0/75; Wilson 95% 0.0–4.9 pp; numerator families: none; over eligible records only (195 of 246; 51 excluded by Amendment B3.2))
- AUROC = 0.483, 95% CI [0.296, 0.674]
- judge noise floor = 0.0 pp (per-replicate detection [0.4, 0.4, 0.4])
- unparsed verdicts = 0

## Verifier arms

### c1
- **N** — MD gate figure 13.3 pp, admissible=True
  - D_c1: 40.0 pp (6/15; Wilson 95% 19.8–64.3 pp; numerator families: R1 1, R4 5; over eligible records only (195 of 246; 51 excluded by Amendment B3.2))
  - MD_c1: 13.3 pp (2/15; Wilson 95% 3.7–37.9 pp; numerator families: R1 1, R4 1; over eligible records only (195 of 246; 51 excluded by Amendment B3.2))
  - FPR_c1: 0.0 pp (0/60; Wilson 95% 0.0–6.0 pp; numerator families: none; over eligible records only (195 of 246; 51 excluded by Amendment B3.2))
  - UNV_c1: 92.0 pp (69/75; Wilson 95% 83.6–96.3 pp; numerator families: R1 22, R2 26, R4 21; over eligible records only (195 of 246; 51 excluded by Amendment B3.2))
  - FOC_c1: 28.6 pp (2/7; Wilson 95% 8.2–64.1 pp; numerator families: R1 1, R4 1; over eligible records only (195 of 246; 51 excluded by Amendment B3.2))
- **N_disc** — MD gate figure 10.0 pp, admissible=True
  - D_c1: 10.0 pp (1/10; Wilson 95% 1.8–40.4 pp; numerator families: R1 1; over eligible records only (195 of 246; 51 excluded by Amendment B3.2))
  - MD_c1: 10.0 pp (1/10; Wilson 95% 1.8–40.4 pp; numerator families: R1 1; over eligible records only (195 of 246; 51 excluded by Amendment B3.2))
  - FPR_c1: 0.0 pp (0/60; Wilson 95% 0.0–6.0 pp; numerator families: none; over eligible records only (195 of 246; 51 excluded by Amendment B3.2))
  - UNV_c1: 92.0 pp (69/75; Wilson 95% 83.6–96.3 pp; numerator families: R1 22, R2 26, R4 21; over eligible records only (195 of 246; 51 excluded by Amendment B3.2))
  - FOC_c1: 16.7 pp (1/6; Wilson 95% 3.0–56.4 pp; numerator families: R1 1; over eligible records only (195 of 246; 51 excluded by Amendment B3.2))
- **N_fs** — MD gate figure 10.0 pp, admissible=True
  - D_c1: 10.0 pp (1/10; Wilson 95% 1.8–40.4 pp; numerator families: R1 1; over eligible records only (195 of 246; 51 excluded by Amendment B3.2))
  - MD_c1: 10.0 pp (1/10; Wilson 95% 1.8–40.4 pp; numerator families: R1 1; over eligible records only (195 of 246; 51 excluded by Amendment B3.2))
  - FPR_c1: 0.0 pp (0/60; Wilson 95% 0.0–6.0 pp; numerator families: none; over eligible records only (195 of 246; 51 excluded by Amendment B3.2))
  - UNV_c1: 92.0 pp (69/75; Wilson 95% 83.6–96.3 pp; numerator families: R1 22, R2 26, R4 21; over eligible records only (195 of 246; 51 excluded by Amendment B3.2))
  - FOC_c1: 16.7 pp (1/6; Wilson 95% 3.0–56.4 pp; numerator families: R1 1; over eligible records only (195 of 246; 51 excluded by Amendment B3.2))
- **N_excl_near_miss** — MD gate figure 16.7 pp, admissible=True
  - D_c1: 50.0 pp (6/12; Wilson 95% 25.4–74.6 pp; numerator families: R1 1, R4 5; over eligible records only (195 of 246; 51 excluded by Amendment B3.2))
  - MD_c1: 16.7 pp (2/12; Wilson 95% 4.7–44.8 pp; numerator families: R1 1, R4 1; over eligible records only (195 of 246; 51 excluded by Amendment B3.2))
  - FPR_c1: 0.0 pp (0/60; Wilson 95% 0.0–6.0 pp; numerator families: none; over eligible records only (195 of 246; 51 excluded by Amendment B3.2))
  - UNV_c1: 92.0 pp (69/75; Wilson 95% 83.6–96.3 pp; numerator families: R1 22, R2 26, R4 21; over eligible records only (195 of 246; 51 excluded by Amendment B3.2))
  - FOC_c1: 33.3 pp (2/6; Wilson 95% 9.7–70.0 pp; numerator families: R1 1, R4 1; over eligible records only (195 of 246; 51 excluded by Amendment B3.2))

### c2
- **N** — MD gate figure 30.7 pp (raw 40.0 pp × 0.7681), admissible=True
  - D_c2: 66.7 pp (10/15; Wilson 95% 41.7–84.8 pp; numerator families: R1 1, R4 9; over eligible records only (195 of 246; 51 excluded by Amendment B3.2))
  - MD_c2: 40.0 pp (6/15; Wilson 95% 19.8–64.3 pp; numerator families: R1 1, R4 5; over eligible records only (195 of 246; 51 excluded by Amendment B3.2))
  - FPR_c2: 0.0 pp (0/60; Wilson 95% 0.0–6.0 pp; numerator families: none; over eligible records only (195 of 246; 51 excluded by Amendment B3.2))
  - UNV_c2: 10.7 pp (8/75; Wilson 95% 5.5–19.7 pp; numerator families: R2 3, R4 5; over eligible records only (195 of 246; 51 excluded by Amendment B3.2))
  - FOC_c2: 85.7 pp (6/7; Wilson 95% 48.7–97.4 pp; numerator families: R1 1, R4 5; over eligible records only (195 of 246; 51 excluded by Amendment B3.2))
- **N_disc** — MD gate figure 46.1 pp (raw 60.0 pp × 0.7681), admissible=True
  - D_c2: 100.0 pp (10/10; Wilson 95% 72.2–100.0 pp; numerator families: R1 1, R4 9; over eligible records only (195 of 246; 51 excluded by Amendment B3.2))
  - MD_c2: 60.0 pp (6/10; Wilson 95% 31.3–83.2 pp; numerator families: R1 1, R4 5; over eligible records only (195 of 246; 51 excluded by Amendment B3.2))
  - FPR_c2: 0.0 pp (0/60; Wilson 95% 0.0–6.0 pp; numerator families: none; over eligible records only (195 of 246; 51 excluded by Amendment B3.2))
  - UNV_c2: 10.7 pp (8/75; Wilson 95% 5.5–19.7 pp; numerator families: R2 3, R4 5; over eligible records only (195 of 246; 51 excluded by Amendment B3.2))
  - FOC_c2: 100.0 pp (6/6; Wilson 95% 61.0–100.0 pp; numerator families: R1 1, R4 5; over eligible records only (195 of 246; 51 excluded by Amendment B3.2))
- **N_fs** — MD gate figure 46.1 pp (raw 60.0 pp × 0.7681), admissible=True
  - D_c2: 100.0 pp (10/10; Wilson 95% 72.2–100.0 pp; numerator families: R1 1, R4 9; over eligible records only (195 of 246; 51 excluded by Amendment B3.2))
  - MD_c2: 60.0 pp (6/10; Wilson 95% 31.3–83.2 pp; numerator families: R1 1, R4 5; over eligible records only (195 of 246; 51 excluded by Amendment B3.2))
  - FPR_c2: 0.0 pp (0/60; Wilson 95% 0.0–6.0 pp; numerator families: none; over eligible records only (195 of 246; 51 excluded by Amendment B3.2))
  - UNV_c2: 10.7 pp (8/75; Wilson 95% 5.5–19.7 pp; numerator families: R2 3, R4 5; over eligible records only (195 of 246; 51 excluded by Amendment B3.2))
  - FOC_c2: 100.0 pp (6/6; Wilson 95% 61.0–100.0 pp; numerator families: R1 1, R4 5; over eligible records only (195 of 246; 51 excluded by Amendment B3.2))
- **N_excl_near_miss** — MD gate figure 32.0 pp (raw 41.7 pp × 0.7681), admissible=True
  - D_c2: 58.3 pp (7/12; Wilson 95% 32.0–80.7 pp; numerator families: R1 1, R4 6; over eligible records only (195 of 246; 51 excluded by Amendment B3.2))
  - MD_c2: 41.7 pp (5/12; Wilson 95% 19.3–68.0 pp; numerator families: R1 1, R4 4; over eligible records only (195 of 246; 51 excluded by Amendment B3.2))
  - FPR_c2: 0.0 pp (0/60; Wilson 95% 0.0–6.0 pp; numerator families: none; over eligible records only (195 of 246; 51 excluded by Amendment B3.2))
  - UNV_c2: 10.7 pp (8/75; Wilson 95% 5.5–19.7 pp; numerator families: R2 3, R4 5; over eligible records only (195 of 246; 51 excluded by Amendment B3.2))
  - FOC_c2: 83.3 pp (5/6; Wilson 95% 43.6–97.0 pp; numerator families: R1 1, R4 4; over eligible records only (195 of 246; 51 excluded by Amendment B3.2))

### constant-fail
- **N** — MD gate figure 46.7 pp, admissible=False
  - D_constant-fail: 100.0 pp (15/15; Wilson 95% 79.6–100.0 pp; numerator families: R1 1, R4 14; over eligible records only (195 of 246; 51 excluded by Amendment B3.2))
  - MD_constant-fail: 46.7 pp (7/15; Wilson 95% 24.8–69.9 pp; numerator families: R1 1, R4 6; over eligible records only (195 of 246; 51 excluded by Amendment B3.2))
  - FPR_constant-fail: 100.0 pp (60/60; Wilson 95% 94.0–100.0 pp; numerator families: R1 22, R2 26, R4 12; over eligible records only (195 of 246; 51 excluded by Amendment B3.2))
  - UNV_constant-fail: 0.0 pp (0/75; Wilson 95% 0.0–4.9 pp; numerator families: none; over eligible records only (195 of 246; 51 excluded by Amendment B3.2))
  - FOC_constant-fail: 100.0 pp (7/7; Wilson 95% 64.6–100.0 pp; numerator families: R1 1, R4 6; over eligible records only (195 of 246; 51 excluded by Amendment B3.2))
- **N_disc** — MD gate figure 60.0 pp, admissible=False
  - D_constant-fail: 100.0 pp (10/10; Wilson 95% 72.2–100.0 pp; numerator families: R1 1, R4 9; over eligible records only (195 of 246; 51 excluded by Amendment B3.2))
  - MD_constant-fail: 60.0 pp (6/10; Wilson 95% 31.3–83.2 pp; numerator families: R1 1, R4 5; over eligible records only (195 of 246; 51 excluded by Amendment B3.2))
  - FPR_constant-fail: 100.0 pp (60/60; Wilson 95% 94.0–100.0 pp; numerator families: R1 22, R2 26, R4 12; over eligible records only (195 of 246; 51 excluded by Amendment B3.2))
  - UNV_constant-fail: 0.0 pp (0/75; Wilson 95% 0.0–4.9 pp; numerator families: none; over eligible records only (195 of 246; 51 excluded by Amendment B3.2))
  - FOC_constant-fail: 100.0 pp (6/6; Wilson 95% 61.0–100.0 pp; numerator families: R1 1, R4 5; over eligible records only (195 of 246; 51 excluded by Amendment B3.2))
- **N_fs** — MD gate figure 60.0 pp, admissible=False
  - D_constant-fail: 100.0 pp (10/10; Wilson 95% 72.2–100.0 pp; numerator families: R1 1, R4 9; over eligible records only (195 of 246; 51 excluded by Amendment B3.2))
  - MD_constant-fail: 60.0 pp (6/10; Wilson 95% 31.3–83.2 pp; numerator families: R1 1, R4 5; over eligible records only (195 of 246; 51 excluded by Amendment B3.2))
  - FPR_constant-fail: 100.0 pp (60/60; Wilson 95% 94.0–100.0 pp; numerator families: R1 22, R2 26, R4 12; over eligible records only (195 of 246; 51 excluded by Amendment B3.2))
  - UNV_constant-fail: 0.0 pp (0/75; Wilson 95% 0.0–4.9 pp; numerator families: none; over eligible records only (195 of 246; 51 excluded by Amendment B3.2))
  - FOC_constant-fail: 100.0 pp (6/6; Wilson 95% 61.0–100.0 pp; numerator families: R1 1, R4 5; over eligible records only (195 of 246; 51 excluded by Amendment B3.2))
- **N_excl_near_miss** — MD gate figure 50.0 pp, admissible=False
  - D_constant-fail: 100.0 pp (12/12; Wilson 95% 75.7–100.0 pp; numerator families: R1 1, R4 11; over eligible records only (195 of 246; 51 excluded by Amendment B3.2))
  - MD_constant-fail: 50.0 pp (6/12; Wilson 95% 25.4–74.6 pp; numerator families: R1 1, R4 5; over eligible records only (195 of 246; 51 excluded by Amendment B3.2))
  - FPR_constant-fail: 100.0 pp (60/60; Wilson 95% 94.0–100.0 pp; numerator families: R1 22, R2 26, R4 12; over eligible records only (195 of 246; 51 excluded by Amendment B3.2))
  - UNV_constant-fail: 0.0 pp (0/75; Wilson 95% 0.0–4.9 pp; numerator families: none; over eligible records only (195 of 246; 51 excluded by Amendment B3.2))
  - FOC_constant-fail: 100.0 pp (6/6; Wilson 95% 61.0–100.0 pp; numerator families: R1 1, R4 5; over eligible records only (195 of 246; 51 excluded by Amendment B3.2))

### constant-pass
- **N** — MD gate figure 0.0 pp, admissible=True
  - D_constant-pass: 0.0 pp (0/15; Wilson 95% 0.0–20.4 pp; numerator families: none; over eligible records only (195 of 246; 51 excluded by Amendment B3.2))
  - MD_constant-pass: 0.0 pp (0/15; Wilson 95% 0.0–20.4 pp; numerator families: none; over eligible records only (195 of 246; 51 excluded by Amendment B3.2))
  - FPR_constant-pass: 0.0 pp (0/60; Wilson 95% 0.0–6.0 pp; numerator families: none; over eligible records only (195 of 246; 51 excluded by Amendment B3.2))
  - UNV_constant-pass: 0.0 pp (0/75; Wilson 95% 0.0–4.9 pp; numerator families: none; over eligible records only (195 of 246; 51 excluded by Amendment B3.2))
  - FOC_constant-pass: 0.0 pp (0/7; Wilson 95% 0.0–35.4 pp; numerator families: none; over eligible records only (195 of 246; 51 excluded by Amendment B3.2))
- **N_disc** — MD gate figure 0.0 pp, admissible=True
  - D_constant-pass: 0.0 pp (0/10; Wilson 95% 0.0–27.8 pp; numerator families: none; over eligible records only (195 of 246; 51 excluded by Amendment B3.2))
  - MD_constant-pass: 0.0 pp (0/10; Wilson 95% 0.0–27.8 pp; numerator families: none; over eligible records only (195 of 246; 51 excluded by Amendment B3.2))
  - FPR_constant-pass: 0.0 pp (0/60; Wilson 95% 0.0–6.0 pp; numerator families: none; over eligible records only (195 of 246; 51 excluded by Amendment B3.2))
  - UNV_constant-pass: 0.0 pp (0/75; Wilson 95% 0.0–4.9 pp; numerator families: none; over eligible records only (195 of 246; 51 excluded by Amendment B3.2))
  - FOC_constant-pass: 0.0 pp (0/6; Wilson 95% 0.0–39.0 pp; numerator families: none; over eligible records only (195 of 246; 51 excluded by Amendment B3.2))
- **N_fs** — MD gate figure 0.0 pp, admissible=True
  - D_constant-pass: 0.0 pp (0/10; Wilson 95% 0.0–27.8 pp; numerator families: none; over eligible records only (195 of 246; 51 excluded by Amendment B3.2))
  - MD_constant-pass: 0.0 pp (0/10; Wilson 95% 0.0–27.8 pp; numerator families: none; over eligible records only (195 of 246; 51 excluded by Amendment B3.2))
  - FPR_constant-pass: 0.0 pp (0/60; Wilson 95% 0.0–6.0 pp; numerator families: none; over eligible records only (195 of 246; 51 excluded by Amendment B3.2))
  - UNV_constant-pass: 0.0 pp (0/75; Wilson 95% 0.0–4.9 pp; numerator families: none; over eligible records only (195 of 246; 51 excluded by Amendment B3.2))
  - FOC_constant-pass: 0.0 pp (0/6; Wilson 95% 0.0–39.0 pp; numerator families: none; over eligible records only (195 of 246; 51 excluded by Amendment B3.2))
- **N_excl_near_miss** — MD gate figure 0.0 pp, admissible=True
  - D_constant-pass: 0.0 pp (0/12; Wilson 95% 0.0–24.3 pp; numerator families: none; over eligible records only (195 of 246; 51 excluded by Amendment B3.2))
  - MD_constant-pass: 0.0 pp (0/12; Wilson 95% 0.0–24.3 pp; numerator families: none; over eligible records only (195 of 246; 51 excluded by Amendment B3.2))
  - FPR_constant-pass: 0.0 pp (0/60; Wilson 95% 0.0–6.0 pp; numerator families: none; over eligible records only (195 of 246; 51 excluded by Amendment B3.2))
  - UNV_constant-pass: 0.0 pp (0/75; Wilson 95% 0.0–4.9 pp; numerator families: none; over eligible records only (195 of 246; 51 excluded by Amendment B3.2))
  - FOC_constant-pass: 0.0 pp (0/6; Wilson 95% 0.0–39.0 pp; numerator families: none; over eligible records only (195 of 246; 51 excluded by Amendment B3.2))

## Decision table — VOID, NOT A VERDICT

> **NEUTRALISED 2026-08-03 — the classifications below are withheld, the figures are not.** Every row was computed against stubbed judge verdicts (`judge.StubJudge`, a deterministic hash of the trace key); no judge verdict exists in this experiment. `D` is a *detection* rate and the gate reads `MD`, *marginal* detection over traces the judge passed, so **nothing here clears the gate or fails it**. Values are unchanged. See `analysis.json` `_neutralised`, `results/NEUTRALISATION.md`, and [finding 015](../../../../findings/015-verifier-vs-judge-not-run.md).

- MD_best (discounted) = 30.7 pp on arm c2, FOC = 65.8%, FPR = 0.0 pp — [CLASSIFICATION WITHHELD — stub judge, no judge verdict exists, nothing here clears or fails a gate; see _neutralised]
- AUROC_judge 95% CI [0.360, 0.711] contains 0.5 — [CLASSIFICATION WITHHELD — stub judge, no judge verdict exists, nothing here clears or fails a gate; see _neutralised]
- UNV_c1 = 92.0% > 50% — [CLASSIFICATION WITHHELD — stub judge, no judge verdict exists, nothing here clears or fails a gate; see _neutralised]

> UNDERPOWERED — ADVISORY. The gate's verdict is advisory-only until the false-success base reaches n >= 30 across >= 3 families (6.9, 9.3). Measured on the population actually scored — eligible records only (195 of 246; 51 excluded by Amendment B3.2) — that base is 10 false success(es) across 5 task(s), 9 of them in family R4; one case is 10.0 pp on N_fs and the gate fires at 2 trace(s) out of 15 on N. A positive result licenses only 'consistent with H2, underpowered'; it does not license 'H2 confirmed'.

> Positives are stratified-sampled, so the scoring set's base rate is not the population base rate. AUROC is prevalence-invariant and unbiased here. Accuracy, PPV, NPV and F1 are not computed at all (6.7).
