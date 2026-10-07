---
name: spatial-integrate
description: Load when removing batch effects from multi-batch spatial AnnData with PCA using Harmony, BBKNN, or Scanorama. Skip physical coordinate alignment (use spatial-register) and single-batch data (use spatial-domains).
trigger: multi-sample integration, batch correction, Harmony, BBKNN, Scanorama
tags:
- spatial
- integration
- batch-correction
---

# spatial-integrate

## Use from a step

```python
from skills._sdk.notebook import load_skill, read_input, write_output
library = load_skill("spatial-integrate")
adata = read_input("data/multi_sample.h5ad")
adata = library.integrate(adata, batch_key="sample")
write_output(adata, "intermediate/integrated.h5ad")
```

## When to use

Correct expression-space batch effects after spatial-preprocess. Harmony and
Scanorama add corrected PCA-based embeddings; BBKNN replaces the neighbor graph.
None aligns tissue coordinates or changes the expression matrix.

## Inputs & Outputs

Input: preprocessed AnnData with `obsm["X_pca"]` and at least two labels in
`obs["batch"]` (or the chosen batch_key). Functions return AnnData, tables and
figures without writing files; see API below.

CLI writes `processed.h5ad`, `report.md`, `result.json`, batch-size and
integration tables, and the comparison gallery. The complete file inventory
and generation conditions are in [references/output_contract.md](references/output_contract.md).
Harmony adds `X_pca_harmony`; Scanorama adds `X_scanorama`;
BBKNN changes `obsp["distances"]` and `obsp["connectivities"]`.

## Key CLI

```bash
python skills/spatial/spatial-integrate/spatial_integrate.py \
  --input multi_sample.h5ad --output results/integration --method harmony --batch-key sample
python skills/spatial/spatial-integrate/spatial_integrate.py --demo --output /tmp/spatial_integrate
```

Use `examples/example_step.py` for load_skill, saved objects and replay.
[references/parameters.md](references/parameters.md) lists the CLI method flags.

## Gotchas

- `X_pca` must exist before integration; no normalization is performed here.
- `X_scanorama` is a corrected PCA-based embedding, not corrected gene expression.
- `batch_entropy_after` measures local mixing, not biological preservation;
  inspect condition and cell-type structure before choosing a correction.
- The function's seed controls Harmony, neighbors, UMAP and Leiden.
  BBKNN's default Annoy matching and Scanorama's wrapper expose no seed here;
  cross-version matching can vary. The installed versions passed repeat CLI checks.
- `run_info(adata, keep=False)` removes only library diagnostics. The CLI keeps
  its existing `uns["spatial_integration"]` summary.
- `X_umap_before_integration` and `X_umap_after_integration` preserve both views.

## API

<!-- api:begin generated from _api.py; regenerate with run.py api <skill dir> --write -->

### `integrate(adata, *, method: str='harmony', batch_key: str='batch', random_state: int=0, **parameters)`

Integrate a multi-batch PCA representation in place, preserving expression.

:param adata: Preprocessed AnnData with X_pca and batch labels.
:param method: harmony (default), bbknn (graph only), or scanorama.
:param batch_key: Batch column in obs, default batch.
:param random_state: Seed for Harmony, neighbors, UMAP and Leiden, default 0.
    BBKNN's default Annoy backend and Scanorama expose no seed here;
    their matching can vary across backend versions.
:param parameters: Method keywords with original CLI defaults: Harmony
    theta=2, lamb=1, max_iter_harmony=10; BBKNN neighbors_within_batch=3,
    n_pcs=50, trim=None; Scanorama knn=20, sigma=15, alpha=0.1, batch_size=5000.
:returns: The same AnnData with corrected embedding or graph, UMAP snapshots,
    per-spot batch entropy, and JSON run diagnostics. X is unchanged.
:raises ValueError: Unknown method, missing batches/PCA, or invalid parameters.
:raises ImportError: Missing backend; use install_skill_deps for that method.

### `run_info(adata, *, keep: bool=True) -> dict`

Read the last integration summary.

:param adata: AnnData returned by integrate.
:param keep: True retains diagnostics; False removes them for CLI serialization.
:returns: Summary including seed and effective method parameters, or an empty dict.

### `mixing_table(adata) -> pd.DataFrame`

Return per-spot entropy before and after correction.

:param adata: Integrated AnnData.
:returns: observation, batch_entropy_before, batch_entropy_after and batch_entropy_delta.
:raises KeyError: Integration entropy columns are absent.

### `embedding_figure(adata, *, batch_key: str='batch')`

Compare the pre- and post-integration UMAP coordinates.

:param adata: Integrated AnnData with both UMAP snapshots.
:param batch_key: Batch labels used for color, default batch.
:returns: A matplotlib Figure; the caller saves and closes it.
:raises KeyError: Batch labels or UMAP snapshots are absent.

<!-- api:end -->

## Dependencies

`anndata`, `bbknn`, `harmonypy`, `matplotlib`, `numpy`, `pandas`, `scanorama`, `scanpy`, `scipy`, `seaborn`

Missing method packages raise ImportError with an install_skill_deps hint.
