---
name: spatial-trajectory
description: Load when inferring pseudotime / lineage trajectories on a preprocessed spatial AnnData via
  DPT (default — diffusion pseudotime), CellRank (terminal-state + fate-probability), or Palantir (waypoint
  branch probabilities). Skip when the data has spliced/unspliced layers and you want velocity-driven
  dynamics (use spatial-velocity); non-spatial scRNA pseudotime (use sc-pseudotime).
trigger: trajectory, pseudotime, diffusion pseudotime, DPT, CellRank, Palantir, cell fate, lineage
tags:
- spatial
- trajectory
- pseudotime
- dpt
- cellrank
- palantir
- lineage
---

# spatial-trajectory

## When to use

Infer pseudotime from log-normalized spatial expression with an existing PCA and neighbors graph. DPT is the default; CellRank adds fate probabilities and Palantir adds waypoint branch probabilities.

## Use from a step

```python
from skills._sdk.notebook import load_skill
library = load_skill("spatial-trajectory")
library.trajectory(adata, root_cell=str(adata.obs_names[0]))
```

Run `examples/example_step.py` with the step runner for a synthetic, executable example.

## API

<!-- api:begin generated from _api.py; regenerate with run.py api <skill dir> --write -->

### `trajectory(adata, *, method: str='dpt', cluster_key: str | None=None, root_cell: str | None=None, root_cell_type: str | None=None, method_params: dict | None=None, random_state: int=0, palantir_waypoint_seed: int=20)`

Infer pseudotime in place from log-normalized X and an existing PCA/graph.

DPT and CellRank add dpt_pseudotime; Palantir adds palantir_pseudotime.
CellRank fate calculations can be incomplete; inspect run_info warnings.

:param adata: AnnData with X_pca and a neighbors graph from preprocessing.
:param method: dpt (CLI default), cellrank or palantir.
:param cluster_key: Observation annotation; None detects leiden/cell_type/cluster.
:param root_cell: Starting barcode; None picks the maximum first diffusion component.
:param root_cell_type: Restrict automatic root selection to this annotation value.
:param method_params: Backend options using the CLI names with underscores;
    None retains its defaults, such as dpt_n_dcs=10. See references/parameters.md.
:param random_state: Seed for diffusion maps and supported backend sampling, default 0.
:param palantir_waypoint_seed: Palantir waypoint sampling seed, 20 to preserve
    the original CLI backend default independently from diffusion-map seed 0.
:returns: The same AnnData with pseudotime and JSON run diagnostics.
:raises ValueError: Missing preprocessing, root or annotation, or invalid method.
:raises ImportError: A backend is missing; use install_skill_deps.

### `run_info(adata, *, keep: bool=True) -> dict`

Read the last run's root, effective parameters and method-specific results.

:param adata: AnnData returned by trajectory.
:param keep: True keeps diagnostics; False removes them for CLI serialization.
:returns: A dictionary, including trajectory gene tables when available.

### `pseudotime_table(adata) -> pd.DataFrame`

Return per-spot pseudotime columns in observation order.

:param adata: AnnData after trajectory inference.
:returns: A barcode-indexed table of available DPT/Palantir pseudotime and entropy.

### `trajectory_genes(adata) -> pd.DataFrame`

Return genes correlated with pseudotime from the last inference.

:param adata: AnnData returned by trajectory; expression was read from X.
:returns: Gene, correlation, pvalue, fdr and direction columns, or an empty table.

### `pseudotime_figure(adata, *, basis: str='spatial')`

Plot inferred pseudotime over coordinates without writing a file.

:param adata: AnnData returned by trajectory.
:param basis: Coordinate key, spatial by default; X_umap is also supported.
:returns: A matplotlib Figure owned by the caller.
:raises KeyError: Missing coordinates or pseudotime.

<!-- api:end -->

## Methods and parameters

DPT uses 10 diffusion components. Pass CLI-style option names in `method_params`, such as `{'dpt_n_dcs': 5}`. CellRank and Palantir dependencies load only when selected.
See [parameters](references/parameters.md) and [methodology](references/methodology.md).

## Gotchas

- `trajectory` requires both `obsm['X_pca']` and `uns['neighbors']`.
- `run_info` identifies the root barcode and pseudotime column; `uns['iroot']` is an integer position.
- `trajectory_genes` reads X and returns FDR-filtered Spearman correlations.
- `palantir_branch_probs` is present only when the backend returns branches.

## Inputs and outputs

`trajectory` returns the same AnnData. `pseudotime_table` and `trajectory_genes` return DataFrames; `pseudotime_figure` returns a Figure. CLI output includes `processed.h5ad`, reports and conditional trajectory/fate tables and plots.
The full file inventory and conditions are in [output contract](references/output_contract.md).

## CLI

```bash
python skills/spatial/spatial-trajectory/spatial_trajectory.py --input input.h5ad --output results/
```

The CLI retains reports and the figure gallery. Function calls do not save files.

## See also

- `spatial-preprocess` supplies expression preprocessing.
- [Output contract](references/output_contract.md) lists method-specific files and AnnData fields.

## Dependencies

`anndata`, `cellrank`, `matplotlib`, `numpy`, `palantir`, `pandas`, `scanpy`, `scipy`, `scvelo`, `seaborn`, `statsmodels`
