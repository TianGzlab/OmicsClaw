---
name: sc-markers
description: Load when ranking cluster-level marker genes from a clustered single-cell AnnData via Scanpy
  Wilcoxon / t-test / logreg or COSG specificity. Skip when comparing condition-vs-control with replicates
  (use sc-de); assigning cell-type labels (use sc-cell-annotation).
tags:
- singlecell
- scrna
- markers
- cluster-markers
- annotation
- differential-expression
- cosg
---

# sc-markers

## When to use

The user already has clustering / cell-type labels in `obs` (typically
`leiden`, `louvain`, or `cell_type`) and wants ranked marker genes per
group as evidence for downstream annotation or interpretation. Four
methods: `wilcoxon` (default rank-sum), `t-test` (Welch), `logreg`
(multinomial logistic regression — discriminative ranking), `cosg`
(fast cosine-specificity scoring without p-values). This is for
**cluster markers**, not condition contrasts — for treatment-vs-control
DE with replicates use `sc-de`.

## Inputs & Outputs

**Inputs**

- Modalities: scrna
- File types: `.h5ad`
- Requires a preprocessed AnnData (`X` normalised, PCA/neighbours present)

**Outputs**

- `tables/cell_metadata.csv`
- `tables/cluster_summary.csv`
- `tables/markers_all.csv`
- `tables/markers_top.csv`
- `figures/r_feature_violin.png`
- `figures/r_marker_heatmap.png`
- `analysis_summary.txt`
- `processed.h5ad`
- `report.md`
- `result.json`
- Processed AnnData (`saves_h5ad`)

## Flow

1. Load AnnData; resolve `--groupby` (auto-detect from `leiden` / `louvain` / `cell_type` if unset).
2. Validate parameters (`n_top ≥ 1`, fractions in `[0, 1]`, `mu` in `[0, 1]`).
3. Run the selected ranker against `adata.X` (treated as normalised expression).
4. Apply post-filters (`--min-in-group-fraction`, `--min-fold-change`, `--max-out-group-fraction`).
5. Build top-N table, per-cluster summary, and figure-data CSVs.
6. Save `processed.h5ad` (with `rank_genes_groups*` purged from `uns`), `tables/`, `figures/`, `report.md`, `result.json`.

## Gotchas

- **`--groupby` auto-detection requires a recognised column.** `sc_markers.py` raises `ValueError("Grouping column '...' not found in adata.obs")` for an explicit-but-missing key; raises `ValueError('No cluster/cell-type grouping column available for marker discovery.')` when nothing among `leiden` / `louvain` / `cell_type` exists. Run `sc-clustering` first or pass `--groupby <real-obs-column>`.
- **`cosg` returns no p-values.** `sc_markers.py` registers `cosg` as a cosine-similarity specificity scorer — `tables/markers_all.csv` will lack `pvals` / `pvals_adj` columns. Downstream filters that branch on adjusted p-value must handle the method == `cosg` case.
- **`--mu` is `cosg`-only.** `sc_markers.py` sets `result.json["mu"] = args.mu if method == 'cosg' else None`. Passing `--mu` with another method silently records `None`.
- **`adata.X` is treated as normalised expression with no guard.** `sc_markers.py` sets `expression_source = 'adata.X'` without verifying `.X` is log-normalised. If `.X` still holds raw counts (e.g., the user skipped `sc-preprocessing`), the Wilcoxon / t-test runs on counts and the rankings are unreliable.
- **`--input` is mandatory unless `--demo`.** `sc_markers.py` raises `ValueError('--input required when not using --demo')`.

## Key CLI

```bash
# Demo (built-in PBMC3K with leiden labels)
python skills/singlecell/scrna/sc-markers/sc_markers.py --demo --output /tmp/sc_markers_demo

# Default Wilcoxon on leiden clusters
python skills/singlecell/scrna/sc-markers/sc_markers.py \
  --input clustered.h5ad --output results/ --groupby leiden

# COSG fast specificity ranking on a labelled AnnData
python skills/singlecell/scrna/sc-markers/sc_markers.py \
  --input annotated.h5ad --output results/ \
  --groupby cell_type --method cosg --mu 1.0

# Strict marker filtering (high fold-change, low out-group fraction)
python skills/singlecell/scrna/sc-markers/sc_markers.py \
  --input clustered.h5ad --output results/ \
  --min-fold-change 1.0 --max-out-group-fraction 0.2
```

## See also

- `references/parameters.md` — every CLI flag and per-method tuning hint
- `references/methodology.md` — Wilcoxon vs t-test vs logreg vs COSG; when each wins
- `references/output_contract.md` — `markers_all.csv` column schema; figures' figure_data CSVs
- Adjacent skills: `sc-clustering` (upstream — produces the `leiden` / `louvain` column), `sc-cell-annotation` (downstream — uses these markers as evidence for label assignment), `sc-de` (parallel — replicate-aware condition contrasts, NOT cluster markers)

## Dependencies

Python packages this skill's script needs. They are not installed for you — check before a long run.

`anndata`, `matplotlib`, `numpy`, `pandas`, `scanpy`, `scikit-learn`, `scipy`, `seaborn`
