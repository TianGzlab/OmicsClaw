---
name: metabolomics-statistics
description: Load when running univariate two-group testing (t-test / Wilcoxon / ANOVA / Kruskal-Wallis)
  on a feature × sample metabolomics CSV with `--group1-prefix` / `--group2-prefix` column matching, BH-FDR
  adjusted. Skip when working with raw spectra (use metabolomics-xcms-preprocessing); two-group DE with
  default `ctrl` / `treat` prefixes (use metabolomics-de).
trigger: metabolomics statistics, multivariate, PCA, clustering
tags:
- metabolomics
- statistics
- ttest
- wilcoxon
- anova
- kruskal
- bh-fdr
---

# metabolomics-statistics

## When to use

Test two explicit sample groups using Welch, ranksums, ANOVA or Kruskal. Use metabolomics-de for the ctrl/treat contrast and PCA CLI.

## Use from a step

```python
import pandas as pd
from skills._sdk.notebook import load_skill, read_input, write_output
library = load_skill("metabolomics-statistics")
data = read_input('features.csv', reader=lambda path: pd.read_csv(path, index_col=0))
result = library.test_groups(data, group1_prefix='ctrl', group2_prefix='treat')
write_output(result, 'tables/result.csv')
```

[examples/example_step.py](examples/example_step.py) runs a seeded synthetic
example through the step runner and writes a table and Figure. Computations
return new DataFrames, leave the input unchanged and expose diagnostics through
`run_info(result)`. Plotting functions write no files.

## API

<!-- api:begin generated from _api.py; regenerate with run.py api <skill dir> --write -->

### `test_groups(data, *, method='ttest', alpha=0.05, group1_prefix=None, group2_prefix=None, group1_cols=None, group2_cols=None)`

Return two-group test statistics and BH-adjusted p values.

:param data: Numeric feature-by-sample DataFrame with feature IDs as its index.
:param method: CLI default ttest; wilcoxon (ranksums), anova or kruskal also work.
:param alpha: CLI default .05; diagnostic significance threshold.
:param group1_prefix: CLI default None; prefix selecting the reference samples.
:param group2_prefix: CLI default None; prefix selecting the comparison samples.
:param group1_cols: Explicit reference columns; supply together with group2_cols.
:param group2_cols: Explicit comparison columns; overrides prefix selection.
:returns: A new DataFrame with grouping and significance diagnostics.
:raises ValueError: A group is empty, overlaps another or is only partly specified.

### `run_info(data, *, keep=True)`

Read diagnostics attached to a returned table.

:param data: DataFrame returned by this library.
:param keep: Default True; use False in the CLI to remove diagnostics.
:returns: An independent dictionary describing the run.
:raises ValueError: The table carries no run_info.

### `volcano_figure(data)`

Plot group2/group1 log2 fold change against BH-adjusted significance.

:param data: Results from test_groups.
:returns: A matplotlib Figure.
:raises KeyError: log2fc or fdr is absent.

<!-- api:end -->

## Methods and parameters

The wilcoxon label calls scipy.stats.ranksums, not paired Wilcoxon or Mann-Whitney U. ANOVA and Kruskal accept exactly two groups here. BH FDR covers every returned feature.

## Gotchas

- `test_groups` falls back to midpoint grouping with a warning when both prefixes are not supplied; run_info records the columns. `tables/significant.csv` uses fdr < alpha. log2fc is group2/group1.

## Inputs and outputs

CSV input; `tables/statistics.csv`, `report.md` and `result.json`. The CLI also writes `tables/significant.csv`. The CLI writes `reproducibility/commands.sh`.
The function library returns objects; the CLI and step own file writes.

## CLI

```bash
python skills/metabolomics/metabolomics-statistics/metabolomics_statistics.py --demo --output /tmp/metabolomics_statistics
```

## See also

- [Parameters](references/parameters.md)
- [Methodology](references/methodology.md)
- [Output contract](references/output_contract.md)

## Dependencies

`numpy`, `pandas`, `scipy`, `matplotlib`
