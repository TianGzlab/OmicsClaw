---
name: sc-qc
description: Load when computing per-cell QC metrics (n_genes, total counts, mt%, ribo%) on a single-cell
  AnnData before filtering. Skip when reads are still raw FASTQ (use sc-fastq-qc); you want to filter
  cells now (use sc-filter).
trigger: scRNA QC, single-cell QC, quality control, mitochondrial percentage, ribosomal percentage, QC violin, QC scatter, n genes per cell
tags:
- singlecell
- scrna
- qc
- mitochondrial
- ribosomal
---

# sc-qc

## When to use

The user has a single-cell AnnData (post-counting / post-standardisation)
and wants to *review* cell quality — counts, detected genes, mitochondrial
percentage, ribosomal percentage — before any filtering.  This skill
**reports**, it does not remove cells.  Use `sc-filter` to actually drop
cells based on these metrics.

## Inputs & Outputs

**Inputs**

- Modalities: scrna
- File types: `.h5ad`

**Outputs**

- `tables/barcode_rank_curve.csv`
- `tables/cell_metadata.csv`
- `tables/gene_expression.csv`
- `tables/highest_expr_genes.csv`
- `tables/qc_metric_correlations.csv`
- `tables/qc_metrics_per_cell.csv`
- `tables/qc_metrics_summary.csv`
- `tables/qc_run_summary.csv`
- `figures/barcode_rank.png`
- `figures/highest_expr_genes.png`
- `figures/qc_correlation_heatmap.png`
- `figures/qc_histograms.png`
- `figures/qc_scatter.png`
- `figures/qc_violin.png`
- `figures/r_qc_violin.png`
- `analysis_summary.txt`
- `processed.h5ad`
- `report.md`
- `result.json`
- Processed AnnData (`saves_h5ad`)

## Flow

1. Load AnnData via the shared single-cell loader.
2. Detect mitochondrial / ribosomal gene patterns from species hint (or `var_names` heuristic).
3. Compute per-cell QC metrics with `scanpy.pp.calculate_qc_metrics`.
4. Emit summary stats + per-cell metrics tables.
5. Render violin + scatter figures and `tables/highest_expr_genes.csv`.
6. Emit `report.md` + `result.json` (no cell filtering performed).

## Gotchas

- **No filtering happens here.** Despite the name, `sc-qc` does not remove cells or genes — it computes metrics and produces figures.  Run `sc-filter` next with thresholds chosen from the QC violins.  The `result.json` `summary` carries `n_cells` / `n_genes` *as observed*, not as filtered.
- **Input file missing → hard fail.** `sc_qc.py` raises `FileNotFoundError` when `--input` does not resolve.  Pre-flight your path before the skill, especially in batch pipelines.
- **`expression_source` records which matrix the run used.** `result.json["summary"]["expression_source"]` reads `layers.counts`, `adata.raw`, or `adata.X` depending on what the loader picked; QC fractions (mt%, ribo%) are only meaningful on a count-like source.  Verify after every run, especially if the input came from outside `sc-standardize-input`.

## Key CLI

```bash
# Demo (built-in PBMC3K)
python skills/singlecell/scrna/sc-qc/sc_qc.py --demo --output /tmp/sc_qc_demo

# Real run
python skills/singlecell/scrna/sc-qc/sc_qc.py --input processed.h5ad --output results/

# With R Enhanced figures
python skills/singlecell/scrna/sc-qc/sc_qc.py --input processed.h5ad --output results/ --r-enhanced
```

## See also

- `references/parameters.md` — every CLI flag and tuning hint
- `references/methodology.md` — mt/ribo gene-pattern detection, scanpy QC parameters
- `references/output_contract.md` — table column schemas + figure roles
- Adjacent skills: `sc-standardize-input` (upstream — required if input is external), `sc-filter` (next step — actually removes cells), `sc-doublet-detection` (parallel — finds doublets)

## Dependencies

Python packages this skill's script needs. They are not installed for you — check before a long run.

`anndata`, `matplotlib`, `numpy`, `pandas`, `scanpy`, `scipy`, `seaborn`
