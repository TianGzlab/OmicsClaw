---
name: sc-qc
description: Load when computing per-cell QC metrics (n_genes, total counts, mt%, ribo%) on a single-cell AnnData before filtering. Skip when reads are still raw FASTQ (use sc-fastq-qc) or you want to filter cells now (use sc-filter).
version: 0.3.0
author: OmicsClaw
license: MIT
tags:
- singlecell
- scrna
- qc
- mitochondrial
- ribosomal
requires:
- anndata
- scanpy
- matplotlib
---

# sc-qc

## When to use

The user has a single-cell AnnData (post-counting / post-standardisation)
and wants to *review* cell quality — counts, detected genes, mitochondrial
percentage, ribosomal percentage — before any filtering.  This skill
**reports**, it does not remove cells.  Use `sc-filter` to actually drop
cells based on these metrics.

## Inputs & Outputs

| Input | Format | Required |
|---|---|---|
| Single-cell AnnData | `.h5ad` | yes (unless `--demo`) |

| Output | Path | Notes |
|---|---|---|
| QC summary | `tables/qc_metrics_summary.csv` | one row per metric, with stats |
| Per-cell metrics | `tables/qc_metrics_per_cell.csv` | one row per cell |
| Top expressed genes | `tables/highest_expr_genes.csv` | by mean expression |
| Diagnostic figures | `figures/qc_violin.png`, `figures/qc_scatter.png` | always rendered |
| Provenance | `result.json` | `summary` includes `n_cells`, `n_genes`, `expression_source` |
| Report | `report.md` | always written |

## Flow

1. Load AnnData via the shared single-cell loader.
2. Detect mitochondrial / ribosomal gene patterns from species hint (or `var_names` heuristic).
3. Compute per-cell QC metrics with `scanpy.pp.calculate_qc_metrics`.
4. Emit summary stats + per-cell metrics tables.
5. Render violin + scatter figures and `tables/highest_expr_genes.csv`.
6. Emit `report.md` + `result.json` (no cell filtering performed).

## Gotchas

- **No filtering happens here.** Despite the name, `sc-qc` does not remove cells or genes — it computes metrics and produces figures.  Run `sc-filter` next with thresholds chosen from the QC violins.  The `result.json` `summary` carries `n_cells` / `n_genes` *as observed*, not as filtered.
- **Input file missing → hard fail.** `sc_qc.py:635` raises `FileNotFoundError` when `--input` does not resolve.  Pre-flight your path before the skill, especially in batch pipelines.
- **`expression_source` records which matrix the run used.** `result.json["summary"]["expression_source"]` reads `layers.counts`, `adata.raw`, or `adata.X` depending on what the loader picked; QC fractions (mt%, ribo%) are only meaningful on a count-like source.  Verify after every run, especially if the input came from outside `sc-standardize-input`.

## Key CLI

```bash
# Demo (built-in PBMC3K)
python omicsclaw.py run sc-qc --demo --output /tmp/sc_qc_demo

# Real run
python omicsclaw.py run sc-qc --input processed.h5ad --output results/

# With R Enhanced figures
python omicsclaw.py run sc-qc --input processed.h5ad --output results/ --r-enhanced
```

## See also

- `references/parameters.md` — every CLI flag and tuning hint
- `references/methodology.md` — mt/ribo gene-pattern detection, scanpy QC parameters
- `references/output_contract.md` — table column schemas + figure roles
- Adjacent skills: `sc-standardize-input` (upstream — required if input is external), `sc-filter` (next step — actually removes cells), `sc-doublet-detection` (parallel — finds doublets)
