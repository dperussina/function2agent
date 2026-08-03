# E8 verifier-vs-judge — results

> ## DRY RUN — NOT RESULTS
>
> No model was called. Every judge verdict below comes from `judge.StubJudge`, a deterministic hash of the trace key. The judge metrics, the AUROC, the fail-open rate and every decision-table row derived from them are **meaningless as findings** and exist only to prove the pipeline runs end to end.
>
> The verifier arms, the taxonomy, the denominators, the controls and the cost projection are computed from the frozen corpus and are real.

## Amendment required — the measured taxonomy disagrees with PREREGISTRATION.md 2.1

- numeric_value_error: preregistration says 8, mechanical classification counts 9
- set_cardinality_error: preregistration says 3, mechanical classification counts 2
- near_miss_n: preregistration says 2, mechanical classification counts 3

The counts above are mechanical, read off the oracle's own recorded reason strings. They are reported rather than reconciled: editing either side to agree would defeat the point of pre-registering the split.

## Controls

- PASS  **leak-assert fires (record)** — a payload embedding the oracle record aborts
- PASS  **leak-assert fires (value)** — the expected value in harness text aborts
- PASS  **leak-assert fires (reason)** — the oracle reason string aborts wherever it appears
- PASS  **leak-assert stays quiet** — a clean payload containing the English words 'reason' and 'outcome' in agent text does not abort
- PASS  **label-shuffle (b)** — mean AUROC over 1000 permutations = 0.5024 (range 0.300–0.719); must centre on 0.500 ± 0.05
- PASS  **label-shuffle (b_prime)** — mean AUROC over 1000 permutations = 0.4973 (range 0.245–0.717); must centre on 0.500 ± 0.05
- PASS  **constant-fail FPR** — FPR = 1.000; a verifier that flags everything must score 1.000, which is why the <= 5 pp admissibility constraint is not optional
- PASS  **constant-pass MD** — MD = 0.000, FPR = 0.000; both must be 0.000
- PASS  **constant-pass FPR** — FPR = 0.000; must be 0.000
- PASS  **constant-fail MD** — MD = 0.500; with 10 fail-open trace(s) the anchor must be strictly positive, and equal to the judge's fail-open rate
- PASS  **predicted-null (c1)** — c1 detected 0 of 9 numeric value errors; predicted 0.  [preregistration says 8 numeric value errors; the mechanical classification counts 9 — amendment required, the control ran over the measured set]

## Retired arm (d)

- **MD upper bound == judge fail-open rate** = 50.0 pp (10/20)
  - `MD(oracle-as-verifier) = |{oracle=fail and judge=pass and oracle=fail}| / |{oracle=fail}| = |{oracle=fail and judge=pass}| / |{oracle=fail}| = FO_judge, exactly`
  - PREREGISTRATION.md 3.3(1): this is a statement about the JUDGE. It MUST NOT appear in any sentence whose subject is the verifier, and it does not feed the decision table.

## Judge arm (b)

- D_judge: 50.0 pp (10/20; Wilson 95% 29.9–70.1 pp; numerator families: R3 2, R4 8)
- FO_judge: 50.0 pp (10/20; Wilson 95% 29.9–70.1 pp; numerator families: N 2, NM 1, R1 1, R4 6)
- CFO_judge: 10.0 pp (2/20; Wilson 95% 2.8–30.1 pp; numerator families: R4 2)
- FPR_judge: 48.3 pp (29/60; Wilson 95% 36.2–60.7 pp; numerator families: N 1, NM 1, R1 9, R2 10, R3 2, R4 3, W1 3)
- flip_rate: 0.0 pp (0/80; Wilson 95% 0.0–4.6 pp; numerator families: none)
- AUROC = 0.512, 95% CI [0.359, 0.664]
- judge noise floor = 0.0 pp (per-replicate detection [0.5, 0.5, 0.5])
- unparsed verdicts = 0

## Judge arm (b_prime)

- D_judge: 50.0 pp (10/20; Wilson 95% 29.9–70.1 pp; numerator families: N 2, NM 1, R1 1, R3 1, R4 5)
- FO_judge: 50.0 pp (10/20; Wilson 95% 29.9–70.1 pp; numerator families: R3 1, R4 9)
- CFO_judge: 25.0 pp (5/20; Wilson 95% 11.2–46.9 pp; numerator families: R4 5)
- FPR_judge: 51.7 pp (31/60; Wilson 95% 39.3–63.8 pp; numerator families: N 4, NM 1, R1 8, R2 8, R3 3, R4 5, W1 2)
- flip_rate: 0.0 pp (0/80; Wilson 95% 0.0–4.6 pp; numerator families: none)
- AUROC = 0.541, 95% CI [0.375, 0.701]
- judge noise floor = 0.0 pp (per-replicate detection [0.5, 0.5, 0.5])
- unparsed verdicts = 0

## Verifier arms

### c1
- **N** — MD gate figure 20.0 pp, admissible=True
  - D_c1: 40.0 pp (8/20; Wilson 95% 21.9–61.3 pp; numerator families: N 2, R1 1, R4 5)
  - MD_c1: 20.0 pp (4/20; Wilson 95% 8.1–41.6 pp; numerator families: N 2, R1 1, R4 1)
  - FPR_c1: 0.0 pp (0/60; Wilson 95% 0.0–6.0 pp; numerator families: none)
  - UNV_c1: 90.0 pp (72/80; Wilson 95% 81.5–94.8 pp; numerator families: N 4, NM 3, R1 18, R2 20, R3 6, R4 18, W1 3)
  - FOC_c1: 40.0 pp (4/10; Wilson 95% 16.8–68.7 pp; numerator families: N 2, R1 1, R4 1)
- **N_disc** — MD gate figure 7.7 pp, admissible=True
  - D_c1: 7.7 pp (1/13; Wilson 95% 1.4–33.3 pp; numerator families: R1 1)
  - MD_c1: 7.7 pp (1/13; Wilson 95% 1.4–33.3 pp; numerator families: R1 1)
  - FPR_c1: 0.0 pp (0/60; Wilson 95% 0.0–6.0 pp; numerator families: none)
  - UNV_c1: 90.0 pp (72/80; Wilson 95% 81.5–94.8 pp; numerator families: N 4, NM 3, R1 18, R2 20, R3 6, R4 18, W1 3)
  - FOC_c1: 14.3 pp (1/7; Wilson 95% 2.6–51.3 pp; numerator families: R1 1)
- **N_fs** — MD gate figure 9.1 pp, admissible=True
  - D_c1: 9.1 pp (1/11; Wilson 95% 1.6–37.7 pp; numerator families: R1 1)
  - MD_c1: 9.1 pp (1/11; Wilson 95% 1.6–37.7 pp; numerator families: R1 1)
  - FPR_c1: 0.0 pp (0/60; Wilson 95% 0.0–6.0 pp; numerator families: none)
  - UNV_c1: 90.0 pp (72/80; Wilson 95% 81.5–94.8 pp; numerator families: N 4, NM 3, R1 18, R2 20, R3 6, R4 18, W1 3)
  - FOC_c1: 14.3 pp (1/7; Wilson 95% 2.6–51.3 pp; numerator families: R1 1)
- **N_excl_near_miss** — MD gate figure 23.5 pp, admissible=True
  - D_c1: 47.1 pp (8/17; Wilson 95% 26.2–69.0 pp; numerator families: N 2, R1 1, R4 5)
  - MD_c1: 23.5 pp (4/17; Wilson 95% 9.6–47.3 pp; numerator families: N 2, R1 1, R4 1)
  - FPR_c1: 0.0 pp (0/60; Wilson 95% 0.0–6.0 pp; numerator families: none)
  - UNV_c1: 90.0 pp (72/80; Wilson 95% 81.5–94.8 pp; numerator families: N 4, NM 3, R1 18, R2 20, R3 6, R4 18, W1 3)
  - FOC_c1: 44.4 pp (4/9; Wilson 95% 18.9–73.3 pp; numerator families: N 2, R1 1, R4 1)

### c2
- **N** — MD gate figure 26.9 pp (raw 35.0 pp × 0.7681), admissible=True
  - D_c2: 55.0 pp (11/20; Wilson 95% 34.2–74.2 pp; numerator families: NM 1, R1 1, R4 9)
  - MD_c2: 35.0 pp (7/20; Wilson 95% 18.1–56.7 pp; numerator families: NM 1, R1 1, R4 5)
  - FPR_c2: 3.3 pp (2/60; Wilson 95% 0.9–11.4 pp; numerator families: NM 2)
  - UNV_c2: 27.5 pp (22/80; Wilson 95% 18.9–38.1 pp; numerator families: N 6, R2 2, R3 6, R4 5, W1 3)
  - FOC_c2: 70.0 pp (7/10; Wilson 95% 39.7–89.2 pp; numerator families: NM 1, R1 1, R4 5)
- **N_disc** — MD gate figure 41.4 pp (raw 53.8 pp × 0.7681), admissible=True
  - D_c2: 84.6 pp (11/13; Wilson 95% 57.8–95.7 pp; numerator families: NM 1, R1 1, R4 9)
  - MD_c2: 53.8 pp (7/13; Wilson 95% 29.1–76.8 pp; numerator families: NM 1, R1 1, R4 5)
  - FPR_c2: 3.3 pp (2/60; Wilson 95% 0.9–11.4 pp; numerator families: NM 2)
  - UNV_c2: 27.5 pp (22/80; Wilson 95% 18.9–38.1 pp; numerator families: N 6, R2 2, R3 6, R4 5, W1 3)
  - FOC_c2: 100.0 pp (7/7; Wilson 95% 64.6–100.0 pp; numerator families: NM 1, R1 1, R4 5)
- **N_fs** — MD gate figure 48.9 pp (raw 63.6 pp × 0.7681), admissible=True
  - D_c2: 100.0 pp (11/11; Wilson 95% 74.1–100.0 pp; numerator families: NM 1, R1 1, R4 9)
  - MD_c2: 63.6 pp (7/11; Wilson 95% 35.4–84.8 pp; numerator families: NM 1, R1 1, R4 5)
  - FPR_c2: 3.3 pp (2/60; Wilson 95% 0.9–11.4 pp; numerator families: NM 2)
  - UNV_c2: 27.5 pp (22/80; Wilson 95% 18.9–38.1 pp; numerator families: N 6, R2 2, R3 6, R4 5, W1 3)
  - FOC_c2: 100.0 pp (7/7; Wilson 95% 64.6–100.0 pp; numerator families: NM 1, R1 1, R4 5)
- **N_excl_near_miss** — MD gate figure 27.1 pp (raw 35.3 pp × 0.7681), admissible=True
  - D_c2: 47.1 pp (8/17; Wilson 95% 26.2–69.0 pp; numerator families: NM 1, R1 1, R4 6)
  - MD_c2: 35.3 pp (6/17; Wilson 95% 17.3–58.7 pp; numerator families: NM 1, R1 1, R4 4)
  - FPR_c2: 3.3 pp (2/60; Wilson 95% 0.9–11.4 pp; numerator families: NM 2)
  - UNV_c2: 27.5 pp (22/80; Wilson 95% 18.9–38.1 pp; numerator families: N 6, R2 2, R3 6, R4 5, W1 3)
  - FOC_c2: 66.7 pp (6/9; Wilson 95% 35.4–87.9 pp; numerator families: NM 1, R1 1, R4 4)

### constant-fail
- **N** — MD gate figure 50.0 pp, admissible=False
  - D_constant-fail: 100.0 pp (20/20; Wilson 95% 83.9–100.0 pp; numerator families: N 2, NM 1, R1 1, R3 2, R4 14)
  - MD_constant-fail: 50.0 pp (10/20; Wilson 95% 29.9–70.1 pp; numerator families: N 2, NM 1, R1 1, R4 6)
  - FPR_constant-fail: 100.0 pp (60/60; Wilson 95% 94.0–100.0 pp; numerator families: N 4, NM 2, R1 18, R2 20, R3 4, R4 9, W1 3)
  - UNV_constant-fail: 0.0 pp (0/80; Wilson 95% 0.0–4.6 pp; numerator families: none)
  - FOC_constant-fail: 100.0 pp (10/10; Wilson 95% 72.2–100.0 pp; numerator families: N 2, NM 1, R1 1, R4 6)
- **N_disc** — MD gate figure 53.8 pp, admissible=False
  - D_constant-fail: 100.0 pp (13/13; Wilson 95% 77.2–100.0 pp; numerator families: NM 1, R1 1, R3 2, R4 9)
  - MD_constant-fail: 53.8 pp (7/13; Wilson 95% 29.1–76.8 pp; numerator families: NM 1, R1 1, R4 5)
  - FPR_constant-fail: 100.0 pp (60/60; Wilson 95% 94.0–100.0 pp; numerator families: N 4, NM 2, R1 18, R2 20, R3 4, R4 9, W1 3)
  - UNV_constant-fail: 0.0 pp (0/80; Wilson 95% 0.0–4.6 pp; numerator families: none)
  - FOC_constant-fail: 100.0 pp (7/7; Wilson 95% 64.6–100.0 pp; numerator families: NM 1, R1 1, R4 5)
- **N_fs** — MD gate figure 63.6 pp, admissible=False
  - D_constant-fail: 100.0 pp (11/11; Wilson 95% 74.1–100.0 pp; numerator families: NM 1, R1 1, R4 9)
  - MD_constant-fail: 63.6 pp (7/11; Wilson 95% 35.4–84.8 pp; numerator families: NM 1, R1 1, R4 5)
  - FPR_constant-fail: 100.0 pp (60/60; Wilson 95% 94.0–100.0 pp; numerator families: N 4, NM 2, R1 18, R2 20, R3 4, R4 9, W1 3)
  - UNV_constant-fail: 0.0 pp (0/80; Wilson 95% 0.0–4.6 pp; numerator families: none)
  - FOC_constant-fail: 100.0 pp (7/7; Wilson 95% 64.6–100.0 pp; numerator families: NM 1, R1 1, R4 5)
- **N_excl_near_miss** — MD gate figure 52.9 pp, admissible=False
  - D_constant-fail: 100.0 pp (17/17; Wilson 95% 81.6–100.0 pp; numerator families: N 2, NM 1, R1 1, R3 2, R4 11)
  - MD_constant-fail: 52.9 pp (9/17; Wilson 95% 31.0–73.8 pp; numerator families: N 2, NM 1, R1 1, R4 5)
  - FPR_constant-fail: 100.0 pp (60/60; Wilson 95% 94.0–100.0 pp; numerator families: N 4, NM 2, R1 18, R2 20, R3 4, R4 9, W1 3)
  - UNV_constant-fail: 0.0 pp (0/80; Wilson 95% 0.0–4.6 pp; numerator families: none)
  - FOC_constant-fail: 100.0 pp (9/9; Wilson 95% 70.1–100.0 pp; numerator families: N 2, NM 1, R1 1, R4 5)

### constant-pass
- **N** — MD gate figure 0.0 pp, admissible=True
  - D_constant-pass: 0.0 pp (0/20; Wilson 95% 0.0–16.1 pp; numerator families: none)
  - MD_constant-pass: 0.0 pp (0/20; Wilson 95% 0.0–16.1 pp; numerator families: none)
  - FPR_constant-pass: 0.0 pp (0/60; Wilson 95% 0.0–6.0 pp; numerator families: none)
  - UNV_constant-pass: 0.0 pp (0/80; Wilson 95% 0.0–4.6 pp; numerator families: none)
  - FOC_constant-pass: 0.0 pp (0/10; Wilson 95% 0.0–27.8 pp; numerator families: none)
- **N_disc** — MD gate figure 0.0 pp, admissible=True
  - D_constant-pass: 0.0 pp (0/13; Wilson 95% 0.0–22.8 pp; numerator families: none)
  - MD_constant-pass: 0.0 pp (0/13; Wilson 95% 0.0–22.8 pp; numerator families: none)
  - FPR_constant-pass: 0.0 pp (0/60; Wilson 95% 0.0–6.0 pp; numerator families: none)
  - UNV_constant-pass: 0.0 pp (0/80; Wilson 95% 0.0–4.6 pp; numerator families: none)
  - FOC_constant-pass: 0.0 pp (0/7; Wilson 95% 0.0–35.4 pp; numerator families: none)
- **N_fs** — MD gate figure 0.0 pp, admissible=True
  - D_constant-pass: 0.0 pp (0/11; Wilson 95% 0.0–25.9 pp; numerator families: none)
  - MD_constant-pass: 0.0 pp (0/11; Wilson 95% 0.0–25.9 pp; numerator families: none)
  - FPR_constant-pass: 0.0 pp (0/60; Wilson 95% 0.0–6.0 pp; numerator families: none)
  - UNV_constant-pass: 0.0 pp (0/80; Wilson 95% 0.0–4.6 pp; numerator families: none)
  - FOC_constant-pass: 0.0 pp (0/7; Wilson 95% 0.0–35.4 pp; numerator families: none)
- **N_excl_near_miss** — MD gate figure 0.0 pp, admissible=True
  - D_constant-pass: 0.0 pp (0/17; Wilson 95% 0.0–18.4 pp; numerator families: none)
  - MD_constant-pass: 0.0 pp (0/17; Wilson 95% 0.0–18.4 pp; numerator families: none)
  - FPR_constant-pass: 0.0 pp (0/60; Wilson 95% 0.0–6.0 pp; numerator families: none)
  - UNV_constant-pass: 0.0 pp (0/80; Wilson 95% 0.0–4.6 pp; numerator families: none)
  - FOC_constant-pass: 0.0 pp (0/9; Wilson 95% 0.0–29.9 pp; numerator families: none)

## Decision table — VOID, NOT A VERDICT

> **NEUTRALISED 2026-08-03 — the classifications below are withheld, the figures are not.** Every row was computed against stubbed judge verdicts (`judge.StubJudge`, a deterministic hash of the trace key); no judge verdict exists in this experiment. `D` is a *detection* rate and the gate reads `MD`, *marginal* detection over traces the judge passed, so **nothing here clears the gate or fails it**. Values are unchanged. See `analysis.json` `_neutralised`, `results/NEUTRALISATION.md`, and [finding 015](../../../../findings/015-verifier-vs-judge-not-run.md).

- MD_best (discounted) = 26.9 pp on arm c2, FOC = 53.8%, FPR = 3.3 pp — [CLASSIFICATION WITHHELD — stub judge, no judge verdict exists, nothing here clears or fails a gate; see _neutralised]
- AUROC_judge 95% CI [0.359, 0.664] contains 0.5 — [CLASSIFICATION WITHHELD — stub judge, no judge verdict exists, nothing here clears or fails a gate; see _neutralised]
- UNV_c1 = 90.0% > 50% — [CLASSIFICATION WITHHELD — stub judge, no judge verdict exists, nothing here clears or fails a gate; see _neutralised]

> UNDERPOWERED — ADVISORY. The gate's verdict is advisory-only until the false-success base reaches n >= 30 across >= 3 families (6.9, 9.3). The corpus carries 11 false successes across 6 tasks with 8 of them in family R4; one case is 9.1 pp on N_fs and the gate fires at 2 traces out of 20 on N. A positive result licenses only 'consistent with H2, underpowered'; it does not license 'H2 confirmed'.

> Positives are stratified-sampled, so the scoring set's base rate is not the corpus base rate (20/246 = 8.13%). AUROC is prevalence-invariant and unbiased here. Accuracy, PPV, NPV and F1 are not computed at all (6.7).
