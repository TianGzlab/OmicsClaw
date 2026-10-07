---
name: spatial-genes
description: Load when ranking spatially variable genes with Moran's I, SpatialDE, SPARK-X, or FlashS. Skip when detecting tissue domains (use spatial-domains) or differential expression between groups (use spatial-de).
trigger: spatially variable gene, spatial gene, SVG, SpatialDE, SPARK-X, spatial pattern, Moran, spatial autocorrelation
tags:
- spatial
- svg
- spatially-variable-genes
- morans-i
- spatialde
- sparkx
- flashs
---

# spatial-genes

## When to use

Rank genes whose expression varies across spatial coordinates. Moran's I
uses continuous log-normalized expression; SpatialDE, SPARK-X and the legacy
FlashS approximation use counts. Scores have method-specific meanings.

## Use from a step

```python
from skills._sdk.notebook import load_skill, read_input, write_output
library = load_skill("spatial-genes")
adata = read_input("processed.h5ad")
library.spatial_genes(adata, random_state=0)
write_output(library.results(adata), "tables/svg_results.csv")
```

The executable example checks spatial autocorrelation in simulated stripes.

## API

<!-- api:begin generated from _api.py; regenerate with run.py api <skill dir> --write -->

### `spatial_genes(adata, *, method='morans', n_top_genes=20, fdr_threshold=0.05, random_state=None, **parameters)`

Compute spatial gene scores and return the same AnnData.

Moran's I reads X; count-based methods prefer counts, then raw, then X.
SpatialDE AEH does not expose a seed: results vary between runs.

:param adata: Expression and spatial coordinates; modified in place.
:param method: CLI default morans; spatialde, sparkx or flashs also supported.
:param n_top_genes: CLI default 20 reported significant genes.
:param fdr_threshold: CLI default 0.05 significance threshold.
:param random_state: None uses CLI seeds, 0 for Moran's I and 42 for FlashS.
:param parameters: Method-specific CLI parameters in references/parameters.md.
:returns: The same AnnData with spatial_genes_results in uns.
:raises ValueError: Method, thresholds or spatial coordinates are invalid.
:raises ImportError: A backend is missing; use install_skill_deps.

### `results(adata, *, significant_only=False)`

Return native spatial-gene scores and significance columns.

:param adata: AnnData returned by spatial_genes.
:param significant_only: Default False; True selects the run's FDR threshold.
:returns: A new DataFrame; score meaning depends on the method.
:raises ValueError: No run is recorded.

### `run_info(adata, *, keep=True)`

Read the most recent spatial-gene diagnostics.

:param adata: AnnData returned by spatial_genes.
:param keep: Default True; False removes transient diagnostics for CLI output.
:returns: Method, thresholds and significant-gene counts.
:raises ValueError: No run is recorded.

### `ranking_figure(adata, *, n_top=20)`

Plot the highest-scoring genes without writing files.

:param adata: AnnData returned by spatial_genes.
:param n_top: Default 20 genes, matching the CLI report size.
:returns: A matplotlib Figure.
:raises ValueError: No run is recorded or n_top is not positive.

<!-- api:end -->

## Methods and parameters

Moran's I defaults to six neighbors and 100 permutations. The default seed is
0 for Moran's I and 42 for FlashS, matching their CLIs. SpatialDE's optional
AEH clustering has no seed interface and may vary between runs. SPARK-X
requires R and SPARK. See [parameters](references/parameters.md) for backend
keywords and [methodology](references/methodology.md) for algorithms.

## Gotchas

- `spatial_genes` stores every method's table in `uns['spatial_genes_results']`;
  Moran's I also writes `uns['moranI']`.
- `results` returns native scores, not a common calibrated statistic.
- Count methods prefer `layers['counts']`, then raw, then X with a warning;
  preserve original counts before normalization.
- `run_info()['significance_column']` names the method's p-value/q-value column.
- `spatial_genes(method='spatialde')` needs both SpatialDE and NaiveDE.

## Inputs and outputs

Functions modify AnnData in place and return tables/Figures without file
output. The CLI writes `processed.h5ad`, `tables/svg_results.csv`, diagnostics,
report and result JSON. The [output contract](references/output_contract.md)
distinguishes temporary R exchange files from delivered artifacts.

## CLI

```bash
python skills/spatial/spatial-genes/spatial_genes.py --input processed.h5ad --output results/genes
python skills/spatial/spatial-genes/spatial_genes.py --demo --output /tmp/spatial-genes_demo
```

## See also

Use spatial-preprocess to prepare expression, spatial-de to compare groups,
and spatial-statistics for spatial relationships between labels.

## Dependencies

`anndata`, `matplotlib`, `numpy`, `pandas`, `scanpy`, `scipy`, `seaborn`, `SpatialDE`, `squidpy`, `statsmodels`

SpatialDE also imports NaiveDE. SPARK-X requires the R package SPARK.
