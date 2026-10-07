---
name: spatial-de
description: Load when ranking spatial cluster markers or comparing two spatial groups. Skip when the data is single-cell (use sc-de), bulk (use bulkrna-de), or for spatially variable expression (use spatial-genes).
trigger: differential expression, marker gene, pseudobulk, Wilcoxon, t-test, PyDESeq2, spatial DE
tags:
- spatial
- differential-expression
- markers
- wilcoxon
- t-test
- pydeseq2
- pseudobulk
---

# spatial-de

## When to use

Rank spatial group markers with Wilcoxon or t-test, or compare conditions
with sample-aware PyDESeq2 pseudobulk. Biological sample labels are required;
spatial spots do not supply independent replicates.

## Use from a step

```python
from skills._sdk.notebook import load_skill, read_input, write_output
library = load_skill("spatial-de")
adata = read_input("processed.h5ad")
library.differential_expression(adata, groupby="leiden")
write_output(library.results(adata), "tables/de_full.csv")
```

The executable example checks known markers in simulated spatial domains.

## API

<!-- api:begin generated from _api.py; regenerate with run.py api <skill dir> --write -->

### `differential_expression(adata, *, method='wilcoxon', groupby='leiden', group1=None, group2=None, n_top_genes=10, fdr_threshold=0.05, log2fc_threshold=1.0, **parameters)`

Test groups and return the same AnnData, with results in its diagnostics.

Scanpy uses raw when present, otherwise log-normalized X. PyDESeq2 uses
counts, then raw, then X; provide integer counts and biological samples.

:param adata: Expression and group labels; modified in place.
:param method: CLI default wilcoxon; t-test or pydeseq2 for other tests.
:param groupby: CLI default leiden; obs column defining comparisons.
:param group1: Tested group, or None for each group versus rest.
:param group2: Reference group; supply together with group1.
:param n_top_genes: CLI default 10 marker genes per group.
:param fdr_threshold: CLI default 0.05 adjusted-p-value threshold.
:param log2fc_threshold: CLI default 1.0 effect-size threshold.
:param parameters: Method-specific CLI parameters from references/parameters.md.
:returns: The same AnnData; results returns the full result table.
:raises ValueError: Groups, method or sample replication are invalid.
:raises ImportError: PyDESeq2 is unavailable; use install_skill_deps.

### `results(adata, *, markers_only=False)`

Return the full or selected marker table without changing expression.

:param adata: AnnData returned by differential_expression.
:param markers_only: Default False; True selects the reported top markers.
:returns: A new DataFrame with method-native effect and significance columns.
:raises ValueError: No differential expression run is recorded.

### `run_info(adata, *, keep=True)`

Read diagnostics and the result tables from the most recent run.

:param adata: AnnData returned by differential_expression.
:param keep: Default True; False removes diagnostics before CLI serialization.
:returns: Diagnostic dictionary including full_df and markers_df.
:raises ValueError: No differential expression run is recorded.

### `volcano_figure(adata, *, group=None)`

Plot effect size against adjusted significance for one comparison.

:param adata: AnnData returned by differential_expression.
:param group: Tested group; None chooses the first reported group.
:returns: A matplotlib Figure; no files are written.
:raises ValueError: No results exist for the selected group.

<!-- api:end -->

## Methods and parameters

Scanpy ranks every gene, then optionally filters markers. PyDESeq2 requires
both group labels and two retained pseudobulk profiles per condition. It uses
a paired design when two biological samples contribute to both groups.
See [parameters](references/parameters.md) for keyword arguments and
[methodology](references/methodology.md) for matrix and design details.

## Gotchas

- `differential_expression` uses Scanpy's raw preference when raw exists;
  otherwise provide log-normalized X. Count methods prefer `layers['counts']`.
- `run_info()['design_formula']` records the PyDESeq2 paired/unpaired design.
- `tables/skipped_sample_groups.csv` records bins below the cell threshold.
- `results(markers_only=True)` may contain nonsignificant top genes when no
  genes pass all filters; inspect the significance columns.

## Inputs and outputs

Functions modify AnnData in place and return DataFrames/Figures without
writing files. The CLI writes `processed.h5ad`, `tables/de_full.csv`,
marker/diagnostic tables, report and result JSON.
The [output contract](references/output_contract.md) lists conditional figures.

## CLI

```bash
python skills/spatial/spatial-de/spatial_de.py --input processed.h5ad --output results/de
python skills/spatial/spatial-de/spatial_de.py --demo --output /tmp/spatial-de_demo
```

## See also

Use spatial-preprocess before analysis, spatial-genes for autocorrelation,
and sc-de or bulkrna-de for their respective modalities.

## Dependencies

`anndata`, `matplotlib`, `numpy`, `pandas`, `pydeseq2`, `scanpy`, `scipy`, `seaborn`
