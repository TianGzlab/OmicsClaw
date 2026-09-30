---
name: bulkrna-coexpression
description: Load when discovering gene co-expression modules and hub genes in a bulk RNA-seq cohort via
  WGCNA-style soft-thresholded networks. Skip when direct DE comparison (use bulkrna-de); PPI lookup of
  an existing gene list (use bulkrna-ppi-network); single-cell co-expression (use sc-grn).
trigger: coexpression, WGCNA, gene network, co-expression modules, hub genes, gene modules
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
assignments and hub genes.

## Inputs & Outputs

**Inputs**

- File types: `.csv`

**Outputs**

- `tables/counts.csv`
- `tables/gene_modules.csv`
- `tables/hub_genes.csv`
- `tables/module_assignments.csv`
- `tables/soft_power_table.csv`
- `tables/threshold_fit.csv`
- `figures/module_dendrogram.png`
- `figures/module_sizes.png`
- `figures/scale_free_fit.png`
- `wgcna_info.json`
- `report.md`
- `result.json`

## Flow

1. Load count matrix; validate `--input` (`bulkrna_coexpression.py` parser-error / `FileNotFoundError`).  Demo path uses `get_demo_data`'s built-in fixture.
2. Validate sample count: `core_analysis` raises `ValueError("WGCNA requires >= 8 samples ...")` below 8 and warns "Low sample count" between 8 and 15 but proceeds.
3. Try the R WGCNA bridge (`_run_wgcna_r` via subprocess); `core_analysis` raises `RuntimeError("R WGCNA failed: ...")` if R or the WGCNA package is unavailable.
4. The Python helper `_select_soft_threshold` is a sanity-check / diagnostic that scores candidate powers by scale-free R² — used as a fallback / exploratory aid, not the production estimator.  R WGCNA's own `pickSoftThreshold` drives the real run.
5. Build modules in R; collect assignments + hub genes; emit `module_assignments.csv`, `hub_genes.csv`, `threshold_fit.csv`.

## Gotchas

- **WGCNA hard-fails below 8 samples.**  `bulkrna_coexpression.py` raises `ValueError`.  Between 8 and 15 the run proceeds but warns "Low sample count (N). WGCNA recommends >= 15 samples for reliable module detection." — treat any modules from <15-sample cohorts as exploratory.
- **R WGCNA is required for the production path.**  `core_analysis` raises `RuntimeError` with installation instructions if R or the `WGCNA` package isn't importable.  There is no Python-only fallback that produces module assignments — installing R+WGCNA is mandatory for non-demo runs.
- **Per-power scale-free R² is in `tables/threshold_fit.csv`, not `result.json`.**  The summary dict carries `soft_power` (the chosen power) but no R² value; inspect the threshold-fit table to assess scale-free quality.  Below R² ≈ 0.8 the network is not scale-free and modules become noise.
- **No biological-replicate filter.**  Unlike PyDESeq2, this skill makes no distinction between technical and biological replicates.  Modules built on a cohort with hidden batch structure will reflect the batch, not biology — run `bulkrna-batch-correction` upstream if PCA shows batch separation.
- **Hub genes are connectivity-based, not necessarily biology-load-bearing.**  A hub in WGCNA means "highest intramodular correlation" — useful as a starting hypothesis but not proof of regulatory primacy.  Validate with knockdown / knockout data or eQTL evidence.

## Key CLI

```bash
python skills/bulkrna/bulkrna-coexpression/bulkrna_coexpression.py --demo --output /tmp/bulkrna-coexpression_demo
python skills/bulkrna/bulkrna-coexpression/bulkrna_coexpression.py \
  --input counts.csv --output results/
```

## See also

- `references/parameters.md` — every CLI flag and tuning hint
- `references/methodology.md` — soft-thresholding, module detection, hub-gene definition
- `references/output_contract.md` — exact output directory layout
- Adjacent skills: `bulkrna-batch-correction` (run upstream if batches suspected), `bulkrna-de` (parallel: differential expression), `bulkrna-ppi-network` (parallel: STRING PPI on a gene list), `sc-grn` (single-cell sibling using GRNBoost2 / pySCENIC)

## Dependencies

Python packages this skill's script needs. They are not installed for you — check before a long run.

`matplotlib`, `numpy`, `pandas`, `scipy`
