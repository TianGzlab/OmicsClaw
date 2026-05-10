---
name: bulkrna-survival
description: Load when stratifying patients by gene expression and testing for survival differences (Kaplan-Meier + Cox) in bulk RNA-seq. Skip if no time-to-event clinical data exists, or for non-bulk cohorts (single-cell / spatial survival is not supported).
version: 0.3.0
author: OmicsClaw
license: MIT
tags:
- bulkrna
- survival
- Kaplan-Meier
- Cox
- hazard-ratio
- clinical
---

# bulkrna-survival

## When to use

Run on a bulk RNA-seq cohort with paired clinical survival data
(time-to-event + censoring) when you want to ask "does high vs low
expression of gene X predict survival?".  Default workflow: per-gene
median-cutoff stratification, log-rank p-value, Kaplan-Meier curve, and
Cox proportional-hazards hazard ratio.

## Inputs & Outputs

| Input | Format | Required |
|---|---|---|
| Expression matrix | `.csv` (gene × sample) | yes (or `--demo`) |
| Clinical data | `.csv` (sample, time, event cols) via `--clinical` | yes (or `--demo`) |
| Genes to test | `--genes TP53,BRCA1` (comma-separated) | optional, defaults to all in expression matrix |

| Output | Path | Notes |
|---|---|---|
| Per-gene survival stats | `tables/survival_summary.csv` | log-rank p, HR, HR 95% CI |
| KM curves | `figures/<gene>_km.png` | one per gene tested |
| Forest plot | `figures/forest_plot.png` | HR + CI across genes |
| Report | `report.md` + `result.json` | always |

## Flow

1. Load expression matrix + clinical data; align by sample ID.
2. For each gene in `--genes` (or all):
   - Skip with warning at `bulkrna_survival.py:630` if gene not in expression matrix.
   - Stratify samples by `--cutoff-method` (default `median`; alt `optimal` finds the maxstat cut).
   - Run log-rank test on the stratified groups.
   - Fit Cox model; warn at `:326` if the high or low group has too few events to be meaningful.
3. Try R `survival` package first; fall back to Python `lifelines` (`:626` warns "R survival not available (...); using Python fallback").
4. Render KM curves + forest plot; emit summary table.

## Gotchas

- **Genes not in the expression matrix are silently skipped.**  `bulkrna_survival.py:630` logs a warning per missing gene and continues.  Check `result.json["tested_genes"]` vs `--genes` after the run — a typo'd or wrong-namespace gene list produces empty output without an obvious error.
- **`--cutoff-method optimal` p-values are NOT corrected for multiple testing.**  The `optimal` cutoff scans all possible cuts and picks the maximally separating one, which inflates Type I error.  Reported log-rank p-values are raw — apply Bonferroni / BH correction externally if you scan many genes.
- **R-vs-Python survival backends give slightly different HRs.**  `:626`'s silent fallback to `lifelines` can produce HRs that differ at the 2nd decimal place from R `survival`'s output (different tie-handling defaults: Efron in R, Breslow in lifelines).  Cross-check `result.json["backend"]` — `"r_survival"` vs `"python_lifelines"` — before reporting exact HR values.
- **Low-event arms produce unstable Cox estimates.**  `:326` warns when an arm has too few events; the run continues with whatever HR / CI the model returns, which can be wildly inflated.  Sanity-check `tables/survival_summary.csv["events_high"]` and `["events_low"]` — any arm with <5 events is statistically uninterpretable.

## Key CLI

```bash
python omicsclaw.py run bulkrna-survival --demo
python omicsclaw.py run bulkrna-survival \
  --input expression.csv --clinical clinical.csv \
  --genes TP53,BRCA1,EGFR --output results/
python omicsclaw.py run bulkrna-survival \
  --input expression.csv --clinical clinical.csv \
  --genes TP53 --cutoff-method optimal --output results/
```

## See also

- `references/parameters.md` — every CLI flag and tuning hint
- `references/methodology.md` — KM + log-rank + Cox theory, R vs Python backend differences, optimal-cutoff caveats
- `references/output_contract.md` — exact output directory layout
- Adjacent skills: `bulkrna-de` (parallel: differential expression — survival adds the time-to-event dimension), `bulkrna-coexpression` (parallel: module-level survival via eigengene if traits include time-to-event)
