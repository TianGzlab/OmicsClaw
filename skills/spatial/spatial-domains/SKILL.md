---
name: spatial-domains
description: Load when detecting tissue domains / niches on a preprocessed spatial AnnData via Leiden
  / Louvain (spatial-weighted) or graph-neural backends (SpaGCN / STAGATE / GraphST / BANKSY / CellCharter).
  Skip when ranking spatially variable genes (use spatial-genes); spot-level cell-type annotation (use
  spatial-annotate).
trigger: spatial domain, tissue region, niche, spatial niche, niche identification, niche detection, SpaGCN, STAGATE, CellCharter
tags:
- spatial
- domains
- niches
- spagcn
- stagate
- graphst
- banksy
- cellcharter
- leiden
- louvain
---

# spatial-domains

## When to use

Find tissue domains from expression and coordinates. Use spatial-annotate for named cell labels and spatial-genes for variable genes.

## Use from a step

```python
from skills._sdk.notebook import load_skill, read_input, write_output
library = load_skill("spatial-domains")
data = read_input("input.h5ad")
data = library.identify(data, method="leiden", spatial_weight=0.3)
write_output(library.domain_counts(data), "tables/results.csv")
```

Run [examples/example_step.py](examples/example_step.py) through the step runner.

## API

<!-- api:begin generated from _api.py; regenerate with run.py api <skill dir> --write -->

### `identify(adata, *, method: str='leiden', resolution: float=1.0, spatial_weight: float=0.3, refine: bool=False, random_state: int | None=None, **parameters)`

Identify domains in place and return the same AnnData.

Reads log-normalized X, X_pca and spatial coordinates; graph methods reuse
existing expression neighbors. SpaGCN, STAGATE and BANKSY results vary
between runs because their training wrappers do not expose every RNG.

:param adata: Preprocessed spatial AnnData; expression values are retained.
:param method: CLI default leiden, or louvain/spagcn/stagate/graphst/banksy/cellcharter.
:param resolution: Graph-clustering resolution, CLI default 1.0.
:param spatial_weight: Spatial graph weight for Leiden/Louvain, CLI default 0.3.
:param refine: False by default; True smooths labels using spatial KNN.
:param random_state: None preserves CLI defaults: backend seed 42 for STAGATE,
    GraphST and CellCharter, otherwise 0; PCA uses 0. An explicit integer
    overrides both PCA and supported backend seeds. Existing PCA is reused.
:param parameters: Backend options listed in references/parameters.md;
    fixed-K methods use n_domains=7 unless supplied.
:returns: The same AnnData with spatial_domain and JSON run diagnostics.
:raises ValueError: Unsupported method or invalid graph parameters.
:raises ImportError: A backend is missing; use install_skill_deps with the named package.

### `run_info(adata, *, keep: bool=True) -> dict`

Read the method, domain sizes, refinement status and effective seeds.

pca_random_state is None when identify reused existing PCA coordinates.

:param adata: AnnData returned by identify.
:param keep: True retains diagnostics; False removes them before CLI serialization.
:returns: Diagnostic dict, or an empty dict before analysis.

### `domain_counts(adata)`

Count observations and percentages per domain.

:param adata: AnnData with spatial_domain labels; X is not read.
:returns: DataFrame with domain, n_cells and proportion (percent).
:raises KeyError: Domain labels are absent.

### `domain_figure(adata)`

Plot domain labels in spatial coordinates.

:param adata: AnnData with spatial_domain and spatial coordinates; X is not read.
:returns: A matplotlib Figure without writing files.
:raises KeyError: Domain labels are absent.

<!-- api:end -->

## Methods and parameters

Leiden/Louvain combine expression and spatial graphs. SpaGCN, STAGATE, GraphST, BANKSY and CellCharter remain optional. Fixed-K methods default to seven domains.
See [parameters](references/parameters.md) and [methodology](references/methodology.md).

## Gotchas

- `identify` reuses expression neighbors. SpaGCN, STAGATE and BANKSY results vary between runs. `spatial_weight=0` uses expression-only graph clustering.
- `run_info(keep=False)` removes library diagnostics before CLI serialization.

## Inputs and outputs

The library returns AnnData, DataFrames or Figures without file writes. The CLI
keeps reports, result.json, tables and conditional gallery outputs. See the
complete [output contract](references/output_contract.md) for filenames and conditions.

## CLI

```bash
python skills/spatial/spatial-domains/spatial_domains.py --input data.h5ad --output results/spatial-domains
```

## See also

- [Methodology](references/methodology.md)
- [Parameters](references/parameters.md)
- [Output contract](references/output_contract.md)

## Dependencies

`anndata`, `cellcharter`, `GraphST`, `igraph`, `louvain`, `matplotlib`, `numpy`, `pandas`, `pybanksy`, `scanpy`, `scikit-learn`, `scipy`, `seaborn`, `SpaGCN`, `squidpy`, `STAGATE-pyG`, `torch`
