---
name: bulkrna-coexpression
description: Load when discovering gene co-expression modules and hub genes in a bulk RNA-seq cohort via WGCNA-style soft-thresholded networks. Skip for direct DE comparison (use bulkrna-de) or PPI lookup of an existing gene list (use bulkrna-ppi-network); single-cell co-expression uses sc-grn instead.
version: 0.3.0
author: OmicsClaw
license: MIT
tags:
- bulkrna
- coexpression
- WGCNA
- network
- modules
- hub-genes
---

# bulkrna-coexpression

## When to use

Run on a bulk RNA-seq cohort (≥15 samples recommended; works on smaller
sets but module structure is unstable below that) when you want to find
groups of co-regulated genes ("modules") and the hub genes within each.
Soft-thresholded correlation network in the WGCNA style; outputs module
assignments, hub genes, and module-trait correlations.

## Inputs & Outputs

| Input | Format | Required |
|---|---|---|
| Count matrix | `.csv` (gene × sample) | yes (or `--demo`) |
| Sample traits | `--traits` CSV | optional, for module-trait correlation |

| Output | Path | Notes |
|---|---|---|
| Module assignments | `tables/module_assignments.csv` | gene → module colour |
| Hub genes | `tables/hub_genes.csv` | per-module top-connectivity genes |
| Soft-threshold diagnostic | `tables/threshold_fit.csv` + `figures/scale_free_fit.png` | per-power scale-free fit + connectivity |
| Module sizes | `figures/module_sizes.png` | bar chart of gene count per module |
| Module assignments | `figures/module_dendrogram.png` | colour-strip of per-gene module label |
| Report | `report.md` + `result.json` | summary keys: `n_genes_used`, `n_samples`, `soft_power`, `n_modules`, `module_sizes`, `method_used` |

## Flow

1. Load count matrix; validate `--input` (`bulkrna_coexpression.py:721,724` parser-error / `FileNotFoundError`).  Demo path uses `:54`'s built-in fixture.
2. Validate sample count: `:377` raises `ValueError("WGCNA requires >= 8 samples ...")` below 8; `:382` warns "Low sample count" between 8 and 15 but proceeds.
3. Try the R WGCNA bridge (`_run_wgcna_r` via subprocess); `:390` raises `RuntimeError("R WGCNA failed: ...")` if R or the WGCNA package is unavailable.
4. The Python helper `_select_soft_threshold` (`:70`) is a sanity-check / diagnostic that scores candidate powers by scale-free R² — used as a fallback / exploratory aid, not the production estimator.  R WGCNA's own `pickSoftThreshold` drives the real run.
5. Build modules in R; collect assignments + hub genes; emit `module_assignments.csv`, `hub_genes.csv`, `threshold_fit.csv`.

## Gotchas

- **WGCNA hard-fails below 8 samples.**  `bulkrna_coexpression.py:377` raises `ValueError`.  Between 8 and 15 the run proceeds but `:382` warns "Low sample count (N). WGCNA recommends >= 15 samples for reliable module detection." — treat any modules from <15-sample cohorts as exploratory.
- **R WGCNA is required for the production path.**  `:390` raises `RuntimeError` with installation instructions if R or the `WGCNA` package isn't importable.  There is no Python-only fallback that produces module assignments — installing R+WGCNA is mandatory for non-demo runs.
- **Per-power scale-free R² is in `tables/threshold_fit.csv`, not `result.json`.**  The summary dict (`:455-464`) carries `soft_power` (the chosen power) but no R² value; inspect the threshold-fit table to assess scale-free quality.  Below R² ≈ 0.8 the network is not scale-free and modules become noise.
- **No biological-replicate filter.**  Unlike PyDESeq2, this skill makes no distinction between technical and biological replicates.  Modules built on a cohort with hidden batch structure will reflect the batch, not biology — run `bulkrna-batch-correction` upstream if PCA shows batch separation.
- **Gene IDs must match between counts and traits.**  No automatic mapping — feed counts and traits with consistent identifier system, or run `bulkrna-geneid-mapping` first.
- **Hub genes are connectivity-based, not necessarily biology-load-bearing.**  A hub in WGCNA means "highest intramodular correlation" — useful as a starting hypothesis but not proof of regulatory primacy.  Validate with knockdown / knockout data or eQTL evidence.

## Key CLI

```bash
python omicsclaw.py run bulkrna-coexpression --demo
python omicsclaw.py run bulkrna-coexpression \
  --input counts.csv --output results/
python omicsclaw.py run bulkrna-coexpression \
  --input counts.csv --traits clinical.csv --output results/
```

## See also

- `references/parameters.md` — every CLI flag and tuning hint
- `references/methodology.md` — soft-thresholding, module detection, hub-gene definition
- `references/output_contract.md` — exact output directory layout
- Adjacent skills: `bulkrna-batch-correction` (run upstream if batches suspected), `bulkrna-de` (parallel: differential expression), `bulkrna-ppi-network` (parallel: STRING PPI on a gene list), `sc-grn` (single-cell sibling using GRNBoost2 / pySCENIC)
