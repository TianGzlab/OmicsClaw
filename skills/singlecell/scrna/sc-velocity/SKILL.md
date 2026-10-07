---
name: sc-velocity
description: Load when computing RNA velocity vectors on a scRNA AnnData with spliced / unspliced layers
  via scVelo (stochastic / dynamical / steady-state); dynamical mode additionally exports latent time.
  Skip when input lacks spliced+unspliced layers (use sc-velocity-prep); trajectory pseudotime ordering
  (use sc-pseudotime).
trigger: rna velocity, velocity, scvelo, spliced unspliced, cellular dynamics, velovi, velocity pseudotime
tags:
- singlecell
- scrna
- velocity
- rna-velocity
- scvelo
- latent-time
- kinetics
---

# sc-velocity

## Use from a step

```python
velocity = load_skill("sc-velocity")
adata = velocity.velocity(read_input("velocity_ready.h5ad"), mode="stochastic",
                          n_jobs=4, random_state=0)
write_output(velocity.velocity_summary(adata), "tables/velocity_summary.csv")
write_output(velocity.top_velocity_genes(adata), "tables/top_velocity_genes.csv")
write_output(adata, "intermediate/adata_velocity.h5ad")
```

The function modifies the input, including scVelo gene filtering.
`examples/example_step.py` uses `velocity_simulation`, a seeded kinetic
simulation with spliced/unspliced layers. The old CLI demo is retained only
for compatibility and does not establish biological velocity.

## API

<!-- api:begin generated from _api.py; regenerate with run.py api <skill dir> --write -->

### `velocity(adata, *, mode: str='stochastic', n_jobs: int=4, random_state: int=0)`

Compute scVelo velocity in place, including its gene filtering.

Both spliced and unspliced count layers are required. The shared method
filters/normalizes expression, explicitly constructs seeded neighbors,
computes moments, velocity and its graph, plus latent time in
dynamical mode. Fewer than five cells or genes, graph failures and
latent-time failures raise errors; no placeholder outputs are created.
Gene filtering modifies every aligned matrix. A failed call can leave
partial preprocessing, so retry from a fresh input copy.

:param mode: stochastic (default), steady_state or dynamical.
:param n_jobs: Dynamics worker budget, default 4; the shared small-data
    branch uses one worker. Graph workers follow scVelo's own settings.
:param random_state: Neighbor seed, default 0.
:returns: The same AnnData. Inspect velocity_diagnostics before interpretation.
:raises ValueError: Layers, mode, worker budget or input dimensions are invalid.
:raises RuntimeError: Velocity graph or dynamical latent-time computation fails.
:raises ImportError: scvelo is unavailable.

### `run_info(adata, *, keep: bool=True) -> dict`

Read the completed run's mode, seed and placeholder policy; empty after failure.

Completion does not establish biological fit validity. keep=False removes
the record from uns.

### `velocity_diagnostics(adata) -> dict`

Return zero/NaN and expressed-velocity-gene checks, not fit validation.

The API rejects placeholder fallbacks. For objects without a completed
API run record, placeholder_fallback_used is unknown (None). These
numerical checks do not establish biological fit validity.

### `velocity_summary(adata) -> pd.DataFrame`

Return method, dimensions and latent-time availability as metric/value rows.

### `velocity_cells_table(adata) -> pd.DataFrame`

Return cell_id, optional UMAP coordinates, velocity magnitude and latent time.

### `top_velocity_genes(adata, *, n_top: int=40) -> pd.DataFrame`

Rank genes by mean absolute velocity and retain their signed mean.

### `stream_figure(adata, *, basis: str='umap')`

Return a scVelo stream Figure; X_<basis> must already be present.

<!-- api:end -->

## Methods and parameters

Modes are `stochastic` (default), `steady_state` and `dynamical`.
The shared backend filters and normalizes expression, computes moments,
velocity and its graph, and attempts latent time for dynamical mode.
`random_state=0` explicitly seeds the neighbor graph before moments.
`n_jobs=4` controls dynamics; the legacy small-data branch uses one worker
and graph workers follow scVelo's settings.

The API never terminates its caller. The compatibility CLI drains its own
loky workers and remaining descendants before exiting; it no longer kills
the process group that may contain a notebook kernel.

## Gotchas

- `_api.py:14` (`velocity`): scvelo 0.3.4's stochastic fit fails with NumPy 2.4
  when its least-squares code assigns a one-element array to a scalar.
  The tested CI combination is scvelo 0.3.4 with NumPy 2.0.2.
- `velocity` can remove genes from X and all aligned layers (`_api.py:14`).
- Inspect `velocity_diagnostics(adata)`, not just the presence of a velocity layer.
  It detects zero/NaN output, not biological validity (`_api.py:61`).
- Graph and dynamical latent-time failures raise errors with the backend
  exception attached. The API and CLI do not replace them with identity
  graphs or uniform sequences (`_api.py:14`).
- Fewer than five cells or genes raise `ValueError` before fitting.
  A failed call can leave partial preprocessing; retry from a fresh copy
  of the input (`_api.py:14`).
- Only dynamical mode attempts latent time. `stream_figure` requires an
  existing display embedding such as X_umap (`_api.py:130`).
- Generate real splicing layers with `sc-velocity-prep`; copied or scaled
  expression layers do not supply the required kinetic signal (`_api.py:14`).

## Inputs & Outputs

Input AnnData must contain `layers["spliced"]` and `layers["unspliced"]`.
The API returns the annotated object and table/Figure helpers.

CLI files include `processed.h5ad`, its `adata_with_velocity.h5ad` alias,
`tables/velocity_summary.csv`, `tables/velocity_cells.csv`,
`tables/top_velocity_genes.csv`, `report.md`, `result.json`, plots and
figure-data manifests. Latent-time plots depend on that obs column;
R-enhanced plots are optional.

## Key CLI

```bash
python skills/singlecell/scrna/sc-velocity/sc_velocity.py --demo --output /tmp/sc_velocity_demo
python skills/singlecell/scrna/sc-velocity/sc_velocity.py --input velocity_ready.h5ad --mode stochastic --output results/
```

## Dependencies

`anndata`, `joblib`, `matplotlib`, `numpy`, `pandas`, `psutil`, `scanpy`, `scikit-learn`, `scipy`, `scvelo`, `seaborn`
