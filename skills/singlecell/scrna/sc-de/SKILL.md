---
name: sc-de
description: Load when finding marker genes per cluster or comparing condition expression in single-cell RNA-seq. Skip if the data is bulk (use bulkrna-de) or spatial (use spatial-de), or for cluster-only markers without conditions (use sc-markers).
version: 0.6.0
author: OmicsClaw
license: MIT
tags:
- singlecell
- differential-expression
- markers
- wilcoxon
- deseq2
---

# sc-de

## When to use

The user has a preprocessed scRNA-seq AnnData and wants to know either
(a) which genes mark each cluster (Wilcoxon / t-test / logreg ranking) or
(b) which genes change between conditions in a replicate-aware way
(`deseq2_r` pseudobulk).  Five backends are exposed; the wrapper enforces
the matrix contract (normalized expression vs raw counts) per backend
because mixing them is the most common silent-wrong-answer failure mode.

## Inputs & Outputs

| Input | Format | Required |
|---|---|---|
| Preprocessed AnnData | `.h5ad` | yes |
| Sample/replicate metadata in `obs` | column name via `--sample-key` | only for `deseq2_r` |
| Cell type label in `obs` | column name via `--celltype-key` | only for `deseq2_r` |

| Output | Path | Notes |
|---|---|---|
| DE table | `tables/de_full.csv` | full per-gene results |
| Top markers | `tables/markers_top.csv` | `--n-top-genes` per group |
| Processed AnnData | `processed.h5ad` | DE results stashed in `uns` |
| Figures | `figures/*.png` | dotplot, rank summary, group summary; pseudobulk volcano/MA per cell type |
| R-enhanced figures | `figures/r_enhanced/*.png` | only with `--r-enhanced` |
| Report | `report.md` + `result.json` | always |

## Flow

1. Load the AnnData and inspect which matrix is in `X` (normalized vs raw).
2. Validate the requested method's matrix contract — fail fast on mismatch.
3. For exploratory paths: run Scanpy `rank_genes_groups` and export marker dotplot + rank summary.
4. For `mast`: hand the log-normalized matrix to the R MAST bridge.
5. For `deseq2_r`: pseudobulk-aggregate by `sample_key` × `celltype_key`, drop bins under `--pseudobulk-min-cells` / `--pseudobulk-min-counts`, run R DESeq2.
6. Render direct figures (and R-enhanced ones if `--r-enhanced`).
7. Write `processed.h5ad`, tables, `figure_data/manifest.json`, `report.md`, `result.json`, and reproducibility script.

## Gotchas

- **Exploratory ranking paths are NOT replicate-aware.** Wilcoxon / t-test / logreg / mast treat each cell as an independent observation, which inflates Type I error for treated-vs-control comparisons across samples.  Use `deseq2_r` whenever biological replicates exist and the question is condition-level inference — not cluster markers.
- **`deseq2_r` requires raw counts.** It looks for `layers["counts"]` first, then `adata.raw`, then `adata.X`.  If `X` is already log-normalized and neither `counts` layer nor `raw` is present, the run silently uses log-normalized values as if they were counts and gives meaningless results.  Verify `result.json["count_source"]` after every pseudobulk run.
- **`--group1` and `--group2` are required for `mast` and `deseq2_r`.** Omitting them on the exploratory paths runs cluster-vs-rest ranking; omitting them on the replicate paths is a hard error.
- **`mast` and `deseq2_r` need a working R stack.** `mast` needs `MAST` + `SingleCellExperiment` + `zellkonverter`; `deseq2_r` needs `DESeq2` + same companions.  The wrapper raises if the R bridge is unavailable — install via the project's R bootstrap, not pip.
- **Pseudobulk bin filtering can drop entire cell types.** If a cell type has fewer than `--pseudobulk-min-cells` (default 10) cells in any sample, the whole bin is dropped from DESeq2.  The dropped-bin list is in `result.json["pseudobulk_dropped"]` — check it before reporting "no DEGs in cell type X."
- **`sample_key` is statistical design, not a label.** DESeq2 fits a per-sample dispersion; using a non-replicate column (e.g. `cell_type` itself) gives nonsense.  The wrapper does not currently catch this — sanity-check the column has >=2 distinct values per condition.

## Key CLI

```bash
# Demo: PBMC3k Wilcoxon cluster markers
python omicsclaw.py run sc-de --demo

# Exploratory: cluster markers via Wilcoxon
python omicsclaw.py run sc-de \
  --input processed.h5ad --output results/ \
  --groupby leiden --method wilcoxon --n-top-genes 20

# Replicate-aware: treated vs control via DESeq2 pseudobulk
python omicsclaw.py run sc-de \
  --input processed.h5ad --output results/ \
  --method deseq2_r --groupby condition \
  --group1 treated --group2 control \
  --sample-key sample_id --celltype-key cell_type \
  --pseudobulk-min-cells 10 --pseudobulk-min-counts 1000
```

## See also

- `references/parameters.md` — every CLI flag and per-method tuning hint
- `references/methodology.md` — Five DE paths, scope boundary, input expectations, workflow
- `references/output_contract.md` — exact output directory layout + visualization contract
- `references/r_visualization.md` — five R-enhanced renderers
- Adjacent skills: `sc-clustering` (upstream cluster discovery), `sc-cell-annotation` (upstream cell type labels for `celltype_key`), `sc-markers` (lighter cluster-marker-only path), `sc-enrichment` (downstream pathway enrichment of DEG lists), `bulkrna-de` / `spatial-de` (sibling DE skills for the other two data modalities)
