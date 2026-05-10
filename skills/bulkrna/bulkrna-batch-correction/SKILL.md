---
name: bulkrna-batch-correction
description: Load when removing batch effects from a multi-cohort bulk RNA-seq dataset using ComBat (R or Python implementation). Skip if there is only one batch, or for single-cell batch integration (use sc-batch-integration), or for spatial multi-slice integration (use spatial-integrate).
version: 0.3.0
author: OmicsClaw
license: MIT
tags:
- bulkrna
- batch-correction
- ComBat
- harmonization
- batch-effect
---

# bulkrna-batch-correction

## When to use

Run when bulkrna-qc PCA or sample-correlation heatmap reveals samples
clustering by batch (cohort, sequencing run, library prep date) rather
than by biology.  Applies ComBat — preferring the R `sva` implementation
when available, falling back to a Python port.

## Inputs & Outputs

| Input | Format | Required |
|---|---|---|
| Expression matrix | `.csv` (gene × sample) | yes (or `--demo`) |
| Batch metadata | `--batch-info` CSV (sample, batch cols) | yes (or `--demo`) |
| `--mode` | `parametric` or `non-parametric` | default `parametric` |

| Output | Path | Notes |
|---|---|---|
| Corrected matrix | `tables/corrected_expression.csv` | same shape, batch effect removed |
| PCA before correction | `figures/pca_before_correction.png` | per-sample colour-coded by batch |
| PCA after correction | `figures/pca_after_correction.png` | same layout, post-ComBat |
| Batch assessment | `figures/batch_assessment.png` | side-by-side comparison + silhouette delta |
| Batch metrics | `tables/batch_metrics.csv` | silhouette score before/after |
| Report | `report.md` + `result.json` | summary keys: `n_genes`, `n_samples`, `n_batches`, `batch_names`, `mode`, `silhouette_before`, `silhouette_after` |

## Flow

1. Load expression matrix + batch metadata.
2. Try R `sva::ComBat` first; on import failure, fall back to Python ComBat (`bulkrna_batch_correction.py:427` warns "R ComBat not available (...); using Python fallback.").
3. The Python fallback short-circuits with a warning at `:165` ("Only 1 batch detected; returning data unchanged.") when `--batch-info` describes a single batch.  The R path has no equivalent guard.
4. Render before/after PCA; emit corrected table, batch-metrics table, and report.

## Gotchas

- **Single-batch input is a silent no-op (Python fallback only).**  `bulkrna_batch_correction.py:165` returns the input unchanged with a warning when only one batch is detected — but **only when the Python ComBat path runs**.  The R `sva::ComBat` path at `:421` does not have this guard, so a single-batch run on an R-equipped system may proceed with nonsense output.  Verify `result.json["n_batches"]` ≥ 2 before trusting downstream results.
- **R vs Python ComBat give numerically different results.**  `:427`'s silent fallback to the Python port can produce per-gene corrected values that differ at the 3rd decimal from R `sva` — usually inconsequential for downstream DE but visible in direct value comparisons.  The chosen backend is not recorded in the summary dict; only the warning log distinguishes them.
- **ComBat assumes the biological design is balanced across batches.**  If condition X is only in batch 1 and condition Y is only in batch 2, ComBat will remove the biology along with the batch effect.  No automatic check — sanity-cross-tabulate `condition × batch` before running, and consider including condition as a covariate in a more sophisticated tool (limma::removeBatchEffect) if confounded.
- **Negative output values are normal for ComBat-on-counts.**  ComBat operates in log-space and returns gene-by-sample matrices that can contain negative values after back-transform.  Do NOT pipe `corrected_expression.csv` into `bulkrna-de` (which expects non-negative integer counts) — use the corrected matrix only for visualisation, clustering, or co-expression analysis.
- **Silhouette score interpretation is direction-of-improvement, not absolute.**  `silhouette_before` / `silhouette_after` (in `result.json` and `batch_metrics.csv`) measure batch clustering tightness.  A drop indicates batch effect has been reduced; absolute values depend on how separable the batches were originally.

## Key CLI

```bash
python omicsclaw.py run bulkrna-batch-correction --demo
python omicsclaw.py run bulkrna-batch-correction \
  --input counts.csv --batch-info batches.csv --output results/
python omicsclaw.py run bulkrna-batch-correction \
  --input counts.csv --batch-info batches.csv --output results/ \
  --mode non-parametric
```

## See also

- `references/parameters.md` — every CLI flag and tuning hint
- `references/methodology.md` — parametric vs non-parametric ComBat, R↔Python differences, design-confound caveats
- `references/output_contract.md` — exact output directory layout
- Adjacent skills: `bulkrna-qc` (run upstream to spot batch effects), `bulkrna-coexpression` / `bulkrna-survival` (downstream — corrected matrix safe for these), `bulkrna-de` (NOT downstream-safe — DE always wants raw counts), `sc-batch-integration` (single-cell sibling: Harmony/scVI/etc.)
