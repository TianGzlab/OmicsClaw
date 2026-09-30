---
name: sc-cytotrace
description: Load when computing per-cell differentiation potency / stemness scores from gene-expression
  complexity on a scRNA AnnData via the CytoTRACE-simple method. Skip when ordering cells along a trajectory
  (use sc-pseudotime); marker-based cell-type labelling (use sc-cell-annotation).
tags:
- singlecell
- scrna
- cytotrace
- potency
- stemness
- differentiation
---

# sc-cytotrace

## When to use

The user has a normalised (or raw-count) scRNA AnnData and wants a
single per-cell **differentiation potency** score (0 = differentiated,
1 = stem/totipotent), plus a 6-bin categorical label
(`Differentiated`, `Mostly Differentiated`, ..., `Totipotent`). The
implementation uses the CytoTRACE-simple proxy: gene-expression
complexity (number of genes detected per cell), KNN-smoothed and rank-
normalised. Single backend: `cytotrace_simple`.

Output goes into `obs["cytotrace_score"]`, `obs["cytotrace_potency"]`,
`obs["cytotrace_gene_count"]`. For trajectory ordering use
`sc-pseudotime`; for cell-type labels use `sc-cell-annotation`.

## Inputs & Outputs

**Inputs**

- Modalities: scrna
- File types: `.h5ad`
- Requires a preprocessed AnnData (`X` normalised, PCA/neighbours present)

**Outputs**

- `tables/cell_metadata.csv`
- `tables/cytotrace_embedding.csv`
- `tables/cytotrace_scores.csv`
- `figures/potency_composition.png`
- `figures/potency_umap.png`
- `figures/r_cell_density.png`
- `figures/r_cytotrace_boxplot.png`
- `figures/r_embedding_discrete.png`
- `figures/r_embedding_feature.png`
- `figures/score_distribution.png`
- `analysis_summary.txt`
- `processed.h5ad`
- `report.md`
- `result.json`
- Processed AnnData (`saves_h5ad`) — adds `obs`: `cytotrace_score`, `cytotrace_potency`, `cytotrace_gene_count`

## Flow

1. Load AnnData; preflight requires `.X` to be `normalized_expression` OR `raw_counts` (matrix-contract check).
2. Compute per-cell gene-count complexity (number of detected genes).
3. Rank-normalise gene counts; KNN-smooth across `--n-neighbors` neighbours.
4. Min-max rescale to `[0, 1]` → `cytotrace_score`.
5. Bin score into 6 potency categories; record counts per category.
6. Detect degenerate output (≤ 1 unique category) → write `result.json["suggested_actions"]`; do NOT raise.
7. Render figures, save tables, `processed.h5ad`, `report.md`, `result.json`.

## Gotchas

- **Single backend only.** `sc_cytotrace.py` argparse `choices=["cytotrace_simple"]` — there is no full CytoTRACE 2 / R-backed path here. `main` raises `ValueError(f"Unknown method: {args.method}")` if the registry diverges.
- **Score is a *proxy* via gene complexity, not the original CytoTRACE algorithm.** `sc_cytotrace.py` documents the simplified pipeline (gene_count → rank → smooth → minmax → 6 bins). Don't quote scores as identical to published CytoTRACE — they're correlated but not numerically equivalent.
- **Degenerate output is a soft fail.** When all cells land in 1 potency bin (e.g., uniformly low complexity), `sc_cytotrace.py` records `result.json["n_potency_categories"] ≤ 1`, sets `degenerate=True`, and writes `suggested_actions: [...]` — but the script returns 0. Always check `result.json["n_potency_categories"]` before interpreting the score.
- **`--input` mandatory unless `--demo`.** `sc_cytotrace.py` raises `ValueError("--input required when not using --demo")`.
- **The skill OVERWRITES existing `obs["cytotrace_*"]` columns.** `sc_cytotrace.py` directly assigns into `obs`. Save the input AnnData first if you need to compare two CytoTRACE runs (e.g., before/after filtering).

## Key CLI

```bash
# Demo
python skills/singlecell/scrna/sc-cytotrace/sc_cytotrace.py --demo --output /tmp/sc_cytotrace_demo

# Default on a normalised AnnData
python skills/singlecell/scrna/sc-cytotrace/sc_cytotrace.py \
  --input clustered.h5ad --output results/

# Tighter KNN smoothing for sparse data
python skills/singlecell/scrna/sc-cytotrace/sc_cytotrace.py \
  --input clustered.h5ad --output results/ --n-neighbors 50

# With R-enhanced ggplot figures
python skills/singlecell/scrna/sc-cytotrace/sc_cytotrace.py \
  --input clustered.h5ad --output results/ --r-enhanced
```

## See also

- `references/parameters.md` — every CLI flag, smoothing notes
- `references/methodology.md` — gene-count proxy vs original CytoTRACE; bin thresholds
- `references/output_contract.md` — `obs["cytotrace_score"]` / `cytotrace_potency` schema
- Adjacent skills: `sc-pseudotime` (parallel — graph-based trajectory ordering, complementary to potency), `sc-clustering` (upstream — provides UMAP for the potency-on-UMAP plot), `sc-cell-annotation` (parallel — predicts discrete cell-type labels rather than continuous potency)

## Dependencies

Python packages this skill's script needs. They are not installed for you — check before a long run.

`anndata`, `matplotlib`, `numpy`, `pandas`, `scanpy`, `scipy`
