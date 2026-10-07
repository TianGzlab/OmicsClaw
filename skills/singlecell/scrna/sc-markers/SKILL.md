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

## Use from a step

```python
markers = load_skill("sc-markers")
adata = read_input("results/02_cluster/intermediate/adata_clustered.h5ad")
table = markers.find_markers(adata, groupby="leiden")
write_output(table, "tables/markers_all.csv")
write_output(markers.top_markers(table), "tables/markers_top.csv")
write_output(markers.run_info(table), "tables/marker_run.json")
```

A complete step on log-normalized PBMC expression is in `examples/example_step.py`.

## API

<!-- api:begin generated from _api.py; regenerate with run.py api <skill dir> --write -->

### `find_markers(adata, *, groupby: str, method: str='wilcoxon', n_genes: int | None=None, min_in_group_fraction: float=0.25, min_fold_change: float=0.25, max_out_group_fraction: float=0.5, mu: float=1.0) -> pd.DataFrame`

Rank marker genes for each group against the rest using adata.X.

X should contain normalized expression. Computation uses a copy, so the
input's matrices, obs and uns are unchanged. Scanpy methods apply the
expression-fraction and fold-change filters; when filtering fails or
removes every row, the unfiltered ranking is returned and run_info records
filter_fallback and its reason. COSG scores specificity without p-values.

:param groupby: The obs column defining clusters or cell types.
:param method: wilcoxon (default), t-test, logreg or cosg.
:param n_genes: Genes ranked per group. None means all genes for Scanpy
    methods and 50 for COSG, matching the CLI defaults.
:param min_in_group_fraction: Minimum expressing fraction within a group.
    Default 0.25; unused by COSG.
:param min_fold_change: Fold-change filter passed to Scanpy. Default 0.25;
    unused by COSG.
:param max_out_group_fraction: Maximum expressing fraction outside a group.
    Default 0.5; unused by COSG.
:param mu: COSG specificity penalty. Default 1.0; unused by Scanpy methods.
:returns: A DataFrame with group, names, scores and method-dependent effect,
    p-value and fraction columns. COSG pvals and pvals_adj are NaN. The
    table's attrs hold the run record; use run_info before CSV export.
:raises ValueError: Unknown method or missing grouping column.

### `run_info(table: pd.DataFrame, *, keep: bool=True) -> dict`

Return the method, grouping and filter-fallback record attached to a marker table.

:param keep: False removes the record from table.attrs; default True keeps it.
:returns: A copy of the run record, or an empty dict for an unrecorded table.
    CSV files do not preserve attrs; write this record separately if needed.

### `top_markers(table: pd.DataFrame, *, n_top: int=10) -> pd.DataFrame`

Return the top n_top rows per group, using adjusted p-value then effect.

Tables without finite adjusted p-values, including COSG, use scores.
Otherwise logfoldchanges is the effect when available, falling back to scores.

### `cluster_summary(table: pd.DataFrame) -> pd.DataFrame`

Return n_markers, top_gene, top_effect, median_effect and effect_metric per group.

The top gene uses the same ordering as top_markers. Effect statistics use
all returned markers in the group.

### `marker_dotplot_figure(adata, table: pd.DataFrame, *, groupby: str, n_top: int=5)`

Return a matplotlib Figure of marker expression in adata.X by group.

Dot size shows the expressing fraction; color shows mean expression.
The top n_top markers per group are selected with top_markers.

<!-- api:end -->

## Methods and parameters

The four methods and their interpretation are described in
`references/methodology.md`. `find_markers` uses `X` with `use_raw=False`.
For `pbmc3k_processed` or `pbmc68k_reduced`, take `adata.raw.to_adata()` to
use their log-normalized matrix; their X is scaled.

- `groupby` explicitly names the labels to compare.
- `method="wilcoxon"` preserves the CLI default; `t-test` uses Welch's test,
  `logreg` gives a discriminative ranking, and `cosg` gives specificity scores.
- `n_genes=None` ranks all genes for Scanpy methods and 50 per group for COSG.
- The CLI's post-filter defaults are `min_in_group_fraction=0.25`,
  `min_fold_change=0.25` and `max_out_group_fraction=0.5`.
- `mu=1.0` preserves the COSG specificity penalty; the other methods ignore it.
- `top_markers(..., n_top=10)` preserves the CLI's compact-summary size.

## Gotchas

- `run_info(table)["filter_fallback"]` is true when post-filtering failed or
  removed every row. The function then returns the unfiltered ranking, as the
  CLI did previously; read `fallback_reason` before interpreting the table.
- COSG's `pvals` and `pvals_adj` columns in `tables/markers_all.csv` contain NaN.
  `top_markers` ranks those rows by `scores`; p-value filters must handle missing values.
- `_api.py:21` (`find_markers`) uses X without checking that it is log-normalized.
  Supply the intended expression matrix explicitly.
- `sc_markers.py:134` (`_resolve_groupby`) can choose a recognized label column for
  the CLI. The function API requires `groupby` explicitly.
- Binary `logreg` can return a Scanpy table without `group`, causing
  `_api.py:91` to raise `KeyError`. Use `wilcoxon`, `t-test` or COSG
  for two groups; this existing Scanpy-wrapper limitation is unchanged.
- CSV export drops DataFrame attrs. Save `run_info(table)` separately when
  keeping the fallback record matters; the CLI stores it at
  `result.json["data"]["run_info"]`.

## Inputs and outputs

`find_markers` reads X and the selected obs column, computes on a copy and
returns a DataFrame. The input AnnData is unchanged, including its uns entries.
`top_markers` and `cluster_summary` return tables; `marker_dotplot_figure`
returns a matplotlib Figure from X. These functions do not write files.

The CLI writes `processed.h5ad`, `report.md`, `result.json`,
`tables/markers_all.csv`, `tables/markers_top.csv`, `tables/cluster_summary.csv`,
and figure-data copies of those tables. Conditional figures and R outputs are
listed in `references/output_contract.md`.

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
