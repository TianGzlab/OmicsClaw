---
name: metabolomics-de
description: Load when running two-group metabolomics DE (t-test + log2FC + BH-FDR + PCA) on a feature
  × sample CSV using `--group-a-prefix` / `--group-b-prefix` (default `ctrl` / `treat`). Skip when needing
  tunable test backends (use metabolomics-statistics); raw spectra.
trigger: metabolomics differential, PLS-DA, volcano plot, biomarker, OPLS-DA
tags:
- metabolomics
- de
- ttest
- pca
- bh-fdr
- biomarker
---

# metabolomics-de

## When to use

Run Welch tests and treatment/control fold changes using ctrl/treat sample prefixes. Use metabolomics-statistics for another test backend.

## Use from a step

```python
import pandas as pd
from skills._sdk.notebook import load_skill, read_input, write_output
library = load_skill("metabolomics-de")
data = read_input('features.csv', reader=pd.read_csv)
result = library.differential_expression(data)
write_output(result, 'tables/result.csv')
```

[examples/example_step.py](examples/example_step.py) runs a seeded synthetic
example through the step runner and writes a table and Figure. Computations
return new DataFrames, leave the input unchanged and expose diagnostics through
`run_info(result)`. Plotting functions write no files.

## API

<!-- api:begin generated from _api.py; regenerate with run.py api <skill dir> --write -->

### `differential_expression(data, *, group_a_prefix='ctrl', group_b_prefix='treat')`

Return Welch tests, treatment/control log2 fold changes and BH FDR.

:param data: Feature table whose first column identifies features; other columns contain intensities.
:param group_a_prefix: CLI default ctrl; prefix selecting control samples.
:param group_b_prefix: CLI default treat; prefix selecting treatment samples.
:returns: A new differential table with group sizes in attrs['run_info'].
:raises ValueError: A group is absent or groups overlap.

### `run_info(data, *, keep=True)`

Read diagnostics attached to a returned table.

:param data: DataFrame returned by this library.
:param keep: Default True; use False in the CLI to remove diagnostics.
:returns: An independent dictionary describing the run.
:raises ValueError: The table carries no run_info.

### `pca_figure(data, *, group_a_prefix='ctrl', group_b_prefix='treat', random_state=0)`

Plot sample PCA from untransformed intensities; NaNs become zero.

:param data: Feature table with the same sample columns as differential_expression.
:param group_a_prefix: CLI default ctrl; control prefix.
:param group_b_prefix: CLI default treat; treatment prefix.
:param random_state: Default 0; seed forwarded to sklearn PCA.
:returns: A matplotlib Figure with sample labels and explained variance axes.
:raises ImportError: Install scikit-learn with install_skill_deps if unavailable.
:raises ValueError: Groups are absent, overlap or the matrix is invalid.

<!-- api:end -->

## Methods and parameters

Welch tests use raw supplied intensities, with BH FDR and a fixed CLI significance threshold of 0.05. PCA uses untransformed intensities and converts NaNs to zero.

## Gotchas

- `differential_expression` treats the first column as feature IDs. Both groups must be nonempty and disjoint. `tables/significant_features.csv` uses fdr < 0.05. The CLI logs optional PCA failures.

## Inputs and outputs

CSV input; `tables/differential_features.csv`, `report.md` and `result.json`. The CLI also writes `tables/significant_features.csv` and, when PCA succeeds, `figures/pca_scores.png`. Demo mode also writes its synthetic input CSV at the output root.
The function library returns objects; the CLI and step own file writes.

## CLI

```bash
python skills/metabolomics/metabolomics-de/met_diff.py --demo --output /tmp/metabolomics_de
```

## See also

- [Parameters](references/parameters.md)
- [Methodology](references/methodology.md)
- [Output contract](references/output_contract.md)

## Dependencies

`numpy`, `pandas`, `scipy`, `scikit-learn`, `matplotlib`
