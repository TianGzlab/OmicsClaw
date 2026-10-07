---
name: sc-in-silico-perturbation
description: Load when predicting in-silico gene knockout effects on a normalised scRNA AnnData via GRN-based
  propagation (Python) or scTenifoldKnk (R). Skip when you have a real Perturb-seq / CRISPR screen (use
  sc-perturb); predicting drug sensitivity (use sc-drug-response).
tags:
- singlecell
- scrna
- in-silico-perturbation
- knockout
- grn
- sctenifoldknk
---

# sc-in-silico-perturbation

Explore descriptive gene associations or run the optional scTenifoldKnk R
method. The default `grn_ko` name is retained for CLI compatibility; its Pearson
edge-removal score is not a causal knockout simulation or a significance test.

## Method Selection Table

| Method | What it returns | Requirement |
|---|---|---|
| `grn_ko` | Absolute correlation edge-removal scores; no p-values | Python science stack |
| `sctenifoldknk` | R scTenifoldKnk differential-regulation table | Rscript + scTenifoldKnk |

## Key CLI

```bash
python skills/singlecell/scrna/sc-in-silico-perturbation/sc_in_silico_perturbation.py --demo --output /tmp/sc_iko_demo
python skills/singlecell/scrna/sc-in-silico-perturbation/sc_in_silico_perturbation.py --input expression.h5ad --ko-gene TP53 --n-top-genes 2000 --output results/associations
python skills/singlecell/scrna/sc-in-silico-perturbation/sc_in_silico_perturbation.py --input expression.h5ad --method sctenifoldknk --ko-gene TP53 --seed 0 --n-cores 1 --output results/tenifold
```

`--corr-threshold` is an inactive legacy argument; it never thresholded the
correlation matrix. The API intentionally does not expose it.

## Workflow

Preflight checks the target gene. `grn_ko` selects high-variance genes plus the
target, computes Pearson correlations, zeros the target row/column and averages
absolute changes by gene. The target's own score summarizes all its removed
edges; other genes lose one edge. R uses the existing temporary CSV bridge and
sets `set.seed` before fitting. No backend is silently substituted.

## Matrix Contract

Reads raw_counts from `layers['counts']` when present, otherwise X. Inputs are
unchanged by the API; returned table metadata records the chosen source.
CLI `processed.h5ad` carries `omicsclaw_input_contract` and
`omicsclaw_matrix_contract`. Use `sc-perturb` for an actual perturbation screen.

## Inputs & Outputs

Input: expression `.h5ad` with `--ko-gene` in `var_names`.
The CLI writes `processed.h5ad`, `tables/diff_regulation.csv`, `report.md`,
`result.json`, `figures/top_perturbed_genes.png`, and figure/plot-data manifests.
The default table has `gene`, `dr_score`, `wt_ko_corr`; only `perturbation_dr_score`
is added to `var`. R additionally writes `tables/tenifold_diff_regulation.csv`
and may produce a p-value histogram and statistical `var` columns. R-enhanced
volcano plots require R statistical output; they are not made for correlation scores.

## Gotchas

- `tables/diff_regulation.csv` no longer contains fabricated `p_value`, `p.adj`, `z_score` or an `FC` alias for the default method. Scores are sorted descending; they do not measure treatment effects.
- `result.json` → `summary.n_significant` exists only for R results with adjusted p-values. No significant-gene count is inferred from correlation scores.
- `--ko-gene G10` is a synthetic-demo default; the API raises when the chosen gene is absent.
- `tables/tenifold_diff_regulation.csv` is produced only if scTenifoldKnk succeeds. The R package is not installed by this skill.

## API

<!-- api:begin generated from _api.py; regenerate with run.py api <skill dir> --write -->

### `knockout_correlation(adata, *, ko_gene, n_top_genes=2000)`

Return descriptive edge-removal scores, not a causal knockout simulation.

Select the most variable genes plus ko_gene, compute Pearson correlations
from layers['counts'] (or X), and average absolute changes after zeroing the
target row and column. Returns gene, dr_score and wt_ko_corr, with no p-values.
The target's own score includes all its removed edges and is not comparable
to another gene's single removed edge. The input AnnData is unchanged.

### `sctenifoldknk(adata, *, ko_gene, qc=False, qc_min_lib_size=0, qc_min_cells=10, n_net=2, n_cells=100, n_comp=3, q=0.8, td_k=2, ma_dim=2, n_cores=1, random_state=0)`

Return scTenifoldKnk diffRegulation through a temporary CSV bridge.

Uses layers['counts'] or X without changing the input. Requires Rscript and
the scTenifoldKnk R package; missing packages and R failures propagate.
random_state is passed to R set.seed before fitting the network.

### `run_info(table, *, keep: bool=True)`

Return method and interpretation; keep=False removes the table's run record.

### `top_perturbed_genes(table, *, n_top=15)`

Return top correlation scores, or lowest adjusted p-values for scTenifoldKnk.

### `perturbed_genes_figure(table, *, n_top=15)`

Return a Figure of descriptive edge scores or R differential-regulation FC.

<!-- api:end -->

## Dependencies

`anndata`, `matplotlib`, `numpy`, `pandas`, `scanpy`, `scipy`

The R method additionally requires the scTenifoldKnk R package.
