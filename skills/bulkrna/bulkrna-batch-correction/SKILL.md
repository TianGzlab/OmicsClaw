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
| Corrected matrix | `tables/counts_corrected.csv` | same shape, batch effect removed |
| PCA before/after | `figures/pca_before_after.png` | side-by-side comparison |
| Per-batch summary | `tables/batch_summary.csv` | sample counts per batch |
| Report | `report.md` + `result.json` | always |

## Flow

1. Load expression matrix + batch metadata.
2. If `--batch-info` describes only one batch, warn at `bulkrna_batch_correction.py:165` ("Only 1 batch detected; returning data unchanged.") and short-circuit — no transformation applied.
3. Try R `sva::ComBat`.  On import failure, fall back to Python implementation (`:427` warns "R ComBat not available (...); using Python fallback.").
4. Render before/after PCA; emit corrected table + report.

## Gotchas

- **Single-batch input is a silent no-op.**  `bulkrna_batch_correction.py:165` returns the input unchanged (with a warning).  If your `--batch-info` accidentally has all samples in one batch (typo, header parsing error), the run "succeeds" but does nothing.  Verify `result.json["batches_seen"]` ≥ 2 before trusting downstream results.
- **R vs Python ComBat give numerically different results.**  `:427`'s silent fallback to the Python port can produce per-gene corrected values that differ at the 3rd decimal from R `sva` — usually inconsequential for downstream DE but visible in direct value comparisons.  Cross-check `result.json["backend"]`.
- **ComBat assumes the biological design is balanced across batches.**  If condition X is only in batch 1 and condition Y is only in batch 2, ComBat will remove the biology along with the batch effect.  No automatic check — sanity-cross-tabulate `condition × batch` before running, and consider including condition as a covariate in a more sophisticated tool (limma::removeBatchEffect) if confounded.
- **Negative output values are normal for ComBat-on-counts.**  ComBat operates in log-space and returns gene-by-sample matrices that can contain negative values after back-transform.  Do NOT pipe `counts_corrected.csv` into `bulkrna-de` (which expects non-negative integer counts) — use the corrected matrix only for visualisation, clustering, or co-expression analysis.

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
