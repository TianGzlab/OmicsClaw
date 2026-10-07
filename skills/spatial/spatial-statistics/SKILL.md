---
name: spatial-statistics
description: Load when running spatial autocorrelation / hotspot / co-occurrence / neighbourhood-enrichment
  / Ripley K stats on a clustered spatial AnnData via squidpy. Skip when ranking spatially variable genes
  (use spatial-genes); tissue domain detection (use spatial-domains).
trigger: spatial statistics, Moran, Geary, Ripley, co-occurrence, Getis-Ord, local Moran, centrality
tags:
- spatial
- statistics
- moran
- geary
- ripley
- co-occurrence
- nhood-enrichment
- getis-ord
- squidpy
---

# spatial-statistics

## When to use

Measure spatial enrichment, co-occurrence, autocorrelation or graph structure. Use spatial-genes for SVG ranking and spatial-domains for regions.

## Use from a step

```python
from skills._sdk.notebook import load_skill, read_input, write_output
library = load_skill("spatial-statistics")
data = read_input("input.h5ad")
data = library.analyze(data, analysis_type="neighborhood_enrichment", random_state=123)
write_output(library.results_table(data), "tables/results.csv")
```

Run [examples/example_step.py](examples/example_step.py) through the step runner.

## API

<!-- api:begin generated from _api.py; regenerate with run.py api <skill dir> --write -->

### `analyze(adata, *, analysis_type: str='neighborhood_enrichment', random_state: int=123, **parameters)`

Run one spatial analysis in place and return the same AnnData.

Gene analyses read X (log-normalized expression); cluster and network
analyses read labels, coordinates and spatial_connectivities. Existing
spatial graphs are reused unless force_graph_rebuild=True.

:param adata: Spatial AnnData; cluster-aware methods require categorical labels.
:param analysis_type: CLI default neighborhood_enrichment; also ripley,
    co_occurrence, moran, geary, local_moran, getis_ord, bivariate_moran,
    network_properties or spatial_centrality.
:param random_state: Permutation/simulation seed, matching CLI default 123.
:param parameters: Method keyword options from references/parameters.md;
    omitted values retain backend wrapper defaults. Unknown options raise.
:returns: The same AnnData with JSON-encoded diagnostics and result tables.
:raises ValueError: Unknown analysis or invalid input.
:raises TypeError: An option does not belong to the chosen method.
:raises ImportError: Missing backend; use install_skill_deps with squidpy,
    esda, libpysal or networkx as reported in the error.

### `run_info(adata, *, keep: bool=True) -> dict`

Read the analysis diagnostics, including method-specific DataFrames.

:param adata: AnnData returned by analyze.
:param keep: True retains the record; False removes it before CLI serialization.
:returns: Diagnostic dict; encoded tables are restored as DataFrames.

### `results_table(adata, *, name: str='pair_summary_df')`

Return a method result table independently of the CLI gallery.

:param adata: AnnData returned by analyze.
:param name: Default pair_summary_df for enrichment; results_df for most
    other methods, or zscore_df/count_df/per_cluster_df when present.
:returns: A DataFrame copy.
:raises KeyError: The selected analysis has no table with this name.

### `enrichment_figure(adata)`

Plot the neighborhood enrichment z-score matrix.

:param adata: AnnData after neighborhood_enrichment; expression is not read.
:returns: A matplotlib Figure without saving it.
:raises KeyError: No enrichment matrix is available.

<!-- api:end -->

## Methods and parameters

Ten methods remain available through analysis_type; extra keywords use Python wrapper names documented in references/parameters.md. Existing spatial graphs are reused unless force_graph_rebuild=True.
See [parameters](references/parameters.md) and [methodology](references/methodology.md).

## Gotchas

- `results_table` defaults to pair_summary_df; other methods often return results_df. `spatial_centrality` requires labels and returns cluster-level scores.
- `run_info(keep=False)` removes library diagnostics before CLI serialization.

## Inputs and outputs

The library returns AnnData, DataFrames or Figures without file writes. The CLI
keeps reports, result.json, tables and conditional gallery outputs. See the
complete [output contract](references/output_contract.md) for filenames and conditions.

## CLI

```bash
python skills/spatial/spatial-statistics/spatial_statistics.py --input data.h5ad --output results/spatial-statistics
```

## See also

- [Methodology](references/methodology.md)
- [Parameters](references/parameters.md)
- [Output contract](references/output_contract.md)

## Dependencies

`anndata`, `esda`, `libpysal`, `matplotlib`, `networkx`, `numpy`, `pandas`, `scanpy`, `scipy`, `seaborn`, `squidpy`
