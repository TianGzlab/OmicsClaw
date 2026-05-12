---
name: sc-cytotrace
description: Load when computing per-cell differentiation potency / stemness scores from gene-expression complexity on a scRNA AnnData via the CytoTRACE-simple method. Skip when ordering cells along a trajectory (use sc-pseudotime) or for marker-based cell-type labelling (use sc-cell-annotation).
version: 0.3.0
author: OmicsClaw
license: MIT
tags:
- singlecell
- scrna
- cytotrace
- potency
- stemness
- differentiation
requires:
- anndata
- scanpy
- numpy
- pandas
- scipy
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

| Input | Format | Required |
|---|---|---|
| Normalised or raw scRNA AnnData | `.h5ad` | yes (unless `--demo`) |

| Output | Path | Notes |
|---|---|---|
| Annotated AnnData | `processed.h5ad` | adds `obs["cytotrace_score"]` (float 0-1), `obs["cytotrace_potency"]` (6-level categorical), `obs["cytotrace_gene_count"]` (int) |
| Per-cell scores | `tables/cytotrace_scores.csv` | always |
| Embedding data | `figure_data/cytotrace_embedding.csv` | always |
| Figures | `figures/potency_umap.png`, `figures/score_distribution.png`, `figures/potency_composition.png` | always |
| Report | `report.md` + `result.json` | always |

## Flow

1. Load AnnData; preflight requires `.X` to be `normalized_expression` OR `raw_counts` (matrix-contract check).
2. Compute per-cell gene-count complexity (number of detected genes).
3. Rank-normalise gene counts; KNN-smooth across `--n-neighbors` neighbours.
4. Min-max rescale to `[0, 1]` → `cytotrace_score`.
5. Bin score into 6 potency categories; record counts per category.
6. Detect degenerate output (≤ 1 unique category) → write `result.json["suggested_actions"]`; do NOT raise.
7. Render figures, save tables, `processed.h5ad`, `report.md`, `result.json`.

## Gotchas

- **Single backend only.** `sc_cytotrace.py:549` argparse `choices=["cytotrace_simple"]` — there is no full CytoTRACE 2 / R-backed path here. `:580` raises `ValueError(f"Unknown method: {args.method}")` if the registry diverges.
- **Score is a *proxy* via gene complexity, not the original CytoTRACE algorithm.** `sc_cytotrace.py:193-199` documents the simplified pipeline (gene_count → rank → smooth → minmax → 6 bins). Don't quote scores as identical to published CytoTRACE — they're correlated but not numerically equivalent.
- **Degenerate output is a soft fail.** When all cells land in 1 potency bin (e.g., uniformly low complexity), `sc_cytotrace.py:253-271` records `result.json["n_potency_categories"] ≤ 1`, sets `degenerate=True`, and writes `suggested_actions: [...]` — but the script returns 0. Always check `result.json["n_potency_categories"]` before interpreting the score.
- **`--input` mandatory unless `--demo`.** `sc_cytotrace.py:562` raises `ValueError("--input required when not using --demo")`.
- **The skill OVERWRITES existing `obs["cytotrace_*"]` columns.** `sc_cytotrace.py:245-247` directly assigns into `obs`. Save the input AnnData first if you need to compare two CytoTRACE runs (e.g., before/after filtering).

## Key CLI

```bash
# Demo
python omicsclaw.py run sc-cytotrace --demo --output /tmp/sc_cytotrace_demo

# Default on a normalised AnnData
python omicsclaw.py run sc-cytotrace \
  --input clustered.h5ad --output results/

# Tighter KNN smoothing for sparse data
python omicsclaw.py run sc-cytotrace \
  --input clustered.h5ad --output results/ --n-neighbors 50

# With R-enhanced ggplot figures
python omicsclaw.py run sc-cytotrace \
  --input clustered.h5ad --output results/ --r-enhanced
```

## See also

- `references/parameters.md` — every CLI flag, smoothing notes
- `references/methodology.md` — gene-count proxy vs original CytoTRACE; bin thresholds
- `references/output_contract.md` — `obs["cytotrace_score"]` / `cytotrace_potency` schema
- Adjacent skills: `sc-pseudotime` (parallel — graph-based trajectory ordering, complementary to potency), `sc-clustering` (upstream — provides UMAP for the potency-on-UMAP plot), `sc-cell-annotation` (parallel — predicts discrete cell-type labels rather than continuous potency)
