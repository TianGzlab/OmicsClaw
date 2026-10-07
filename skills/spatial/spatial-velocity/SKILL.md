---
name: spatial-velocity
description: Load when estimating RNA velocity on a spatial AnnData with `layers["spliced"]` + `layers["unspliced"]`
  via scVelo (stochastic / deterministic / dynamical) or veloVI (deep generative). Skip when input lacks
  the spliced/unspliced layers (must be quantified upstream by velocyto / kb-python / STARsolo); non-spatial
  scRNA velocity (use sc-velocity).
trigger: RNA velocity, cellular dynamics, scVelo, VELOVI, latent time, spliced unspliced
tags:
- spatial
- velocity
- rna-velocity
- scvelo
- velovi
- dynamics
---

# spatial-velocity

## When to use

Estimate velocity from measured spliced/unspliced count layers. Use spatial-trajectory when these layers are absent, or sc-velocity for non-spatial data.

## Use from a step

```python
from skills._sdk.notebook import load_skill
library = load_skill("spatial-velocity")
library.velocity(adata, method='stochastic')
```

Run `examples/example_step.py` with the step runner for a synthetic, executable example.

## API

<!-- api:begin generated from _api.py; regenerate with run.py api <skill dir> --write -->

### `velocity(adata, *, method: str='stochastic', cluster_key: str='leiden', method_params: dict | None=None, random_state: int=0)`

Estimate velocity in place from spliced/unspliced count layers.

Preprocessing filters genes, normalizes X and count layers, and builds
PCA/neighbors/moments. Optional confidence, pseudotime and latent-time
failures are reported in run_info warnings. VELOVI GPU results can vary
between runs even with a fixed seed. scVelo velocity pseudotime uses an
eigensolver without a seed argument; its results vary between runs.

:param adata: AnnData containing measured spliced and unspliced layers.
:param method: stochastic (CLI default), deterministic, dynamical or velovi.
:param cluster_key: Annotation used in output summaries; default leiden.
:param method_params: CLI options with underscores; None keeps defaults,
    including velocity_min_shared_counts=30 and velocity_n_pcs=30.
    See references/parameters.md for method-specific controls.
:param random_state: PCA/neighbor and VELOVI training seed, default 0.
:returns: The same AnnData with velocity layers, graph and JSON diagnostics.
:raises ValueError: Missing layers or invalid method.
:raises ImportError: A backend is unavailable; use install_skill_deps.

### `run_info(adata, *, keep: bool=True) -> dict`

Read the last velocity method's diagnostics and metric tables.

:param adata: AnnData returned by velocity.
:param keep: True retains diagnostics; False removes them for CLI serialization.
:returns: A dictionary with effective method controls and warnings, or empty dict.

### `cell_metrics(adata) -> pd.DataFrame`

Return velocity speed, confidence and pseudotime for each spot.

:param adata: AnnData returned by velocity.
:returns: The last run's barcode-indexed cell table, or an empty table.

### `gene_metrics(adata) -> pd.DataFrame`

Return fitted velocity gene parameters and fit quality.

:param adata: AnnData returned by velocity.
:returns: The last run's gene-indexed table, or an empty table.

### `velocity_figure(adata, *, color: str='velocity_speed', basis: str='spatial')`

Plot a numeric velocity metric at spot coordinates without saving.

:param adata: AnnData after velocity inference.
:param color: Numeric observation metric; velocity_speed by default.
:param basis: Coordinate key, spatial by default; X_umap is also supported.
:returns: A matplotlib Figure owned by the caller.
:raises KeyError: Missing coordinates or metric.

<!-- api:end -->

## Methods and parameters

scVelo supports stochastic (default), deterministic and dynamical fits. VELOVI uses scvi-tools. Pass CLI option names with underscores in `method_params`; defaults include 30 shared counts, 2000 HVGs, 30 PCs and 30 neighbors.
See [parameters](references/parameters.md) and [methodology](references/methodology.md).

## Gotchas

- `velocity` rejects missing layers; it never constructs spliced/unspliced observations from expression.
- `run_info()['warnings']` records optional confidence/pseudotime/latent-time failures.
- `gene_metrics` reports fitted parameters; VELOVI marks every retained gene as a velocity gene.
- scVelo pseudotime uses an unseeded eigensolver; results vary between runs. GPU VELOVI can also vary despite its seed.

## Inputs and outputs

`velocity` modifies X, count layers and the gene subset in place, then adds velocity and moment layers. `cell_metrics` and `gene_metrics` return DataFrames; `velocity_figure` returns a Figure. CLI reports, tables and plots are conditional on fitted metrics and available coordinates.
The full file inventory and conditions are in [output contract](references/output_contract.md).

## CLI

```bash
python skills/spatial/spatial-velocity/spatial_velocity.py --input input.h5ad --output results/
```

The CLI retains reports and the figure gallery. Function calls do not save files.

## See also

- `spatial-preprocess` supplies expression preprocessing.
- [Output contract](references/output_contract.md) lists method-specific files and AnnData fields.

## Dependencies

`anndata`, `matplotlib`, `numpy`, `pandas`, `scanpy`, `scipy`, `scvelo`, `scvi-tools`, `seaborn`, `torch`, `velovi`
