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
| Per-gene survival stats | `tables/survival_results.csv` | columns: `gene, cutoff, n_high, n_low, hazard_ratio, log_rank_chi2, log_rank_pval, median_survival_high, median_survival_low` |
| KM curves | `figures/<gene>_km.png` | one per gene tested |
| Forest plot | `figures/forest_plot.png` | HR + CI across genes |
| Report | `report.md` + `result.json` | summary contains `n_genes` and per-gene `results` array (`bulkrna_survival.py:153-160`) |

## Flow

1. Load expression matrix + clinical data; align by sample ID.
2. For each gene in `--genes` (or all):
   - Skip with warning at `bulkrna_survival.py:630` if gene not in expression matrix.
   - Stratify samples by `--cutoff-method` (default `median`; alt `optimal` finds the maxstat cut).
   - Run log-rank test on the stratified groups.
   - Compute a simple events/time hazard ratio.  Warn at `:326` ("Heavy censoring (X%). KM tail estimates may be unreliable.") when the censoring rate exceeds 80%.
3. Try R `survival` package first; fall back to Python `lifelines` (`:626` warns "R survival not available (...); using Python fallback.").
4. Render KM curves + forest plot; emit `tables/survival_results.csv`.

## Gotchas

- **Genes not in the expression matrix are silently skipped.**  `bulkrna_survival.py:630` logs a warning per missing gene and continues.  After the run, count the rows in `tables/survival_results.csv` (or inspect `result.json["results"]`) and compare against the `--genes` list — a typo'd or wrong-namespace gene produces no obvious error.
- **`--cutoff-method optimal` p-values are NOT corrected for multiple testing.**  The `optimal` cutoff scans all possible cuts and picks the maximally separating one, which inflates Type I error.  Reported log-rank p-values are raw — apply Bonferroni / BH correction externally if you scan many genes.
- **The hazard ratio is a simple events/person-time ratio, not a Cox MLE.**  The script computes `(events_high / time_high) / (events_low / time_low)` (`bulkrna_survival.py:328-333`), not a Cox proportional-hazards regression coefficient.  This estimator is biased when proportional-hazards holds with unequal exposure — for publication-grade HRs, re-fit a proper Cox model in R or `lifelines` against the same stratification.
- **R-vs-Python backend silently switches.**  `:626` warns and falls back to a NumPy log-rank implementation when R `survival` isn't importable; the per-gene HR estimator is the same simple events/time ratio in both cases, but the chosen backend isn't recorded in the summary dict — only in the warning log.  Verify R availability before relying on the result for downstream papers.
- **Heavy censoring distorts KM tail estimates.**  `:326` fires when ≥80% of patients are censored; the printed median survival numbers are dominated by extrapolation past the last event time.  Treat `median_survival_*` as "≥ X" rather than a point estimate when the corresponding gene's censoring rate is high.

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
