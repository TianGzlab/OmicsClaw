---
name: metabolomics-normalization
description: Load when normalising a feature × sample metabolomics CSV via median, quantile, total (sum),
  PQN (probabilistic quotient), or log methods — emits a normalised wide-form table. Skip when also imputing
  (use metabolomics-quantification); raw spectra (use metabolomics-xcms-preprocessing).
trigger: metabolomics normalization, scaling, NOREVA, TIC normalization
tags:
- metabolomics
- normalization
- pqn
- quantile
- median
- log
---

# metabolomics-normalization

## When to use

Normalize a numeric feature-by-sample table. Use metabolomics-quantification when missing-value imputation is also needed.

## Use from a step

```python
import pandas as pd
from skills._sdk.notebook import load_skill, read_input, write_output
library = load_skill("metabolomics-normalization")
data = read_input('features.csv', reader=lambda path: pd.read_csv(path, index_col=0))
result = library.normalize(data)
write_output(result, 'tables/result.csv')
```

[examples/example_step.py](examples/example_step.py) runs a seeded synthetic
example through the step runner and writes a table and Figure. Computations
return new DataFrames, leave the input unchanged and expose diagnostics through
`run_info(result)`. Plotting functions write no files.

## API

<!-- api:begin generated from _api.py; regenerate with run.py api <skill dir> --write -->

### `normalize(data, *, method='median')`

Return a normalized copy, preserving feature and sample labels.

:param data: Numeric feature-by-sample DataFrame; NaNs retain method semantics.
:param method: CLI default median; quantile, total, pqn or log are alternatives.
:returns: A new DataFrame with method and dimensions in attrs['run_info'].
:raises ValueError: The requested method is unknown.

### `run_info(data, *, keep=True)`

Read diagnostics attached to a returned table.

:param data: DataFrame returned by this library.
:param keep: Default True; use False in the CLI to remove diagnostics.
:returns: An independent dictionary describing the run.
:raises ValueError: The table carries no run_info.

### `distribution_figure(data)`

Plot normalized sample distributions without writing a file.

:param data: Numeric feature-by-sample DataFrame.
:returns: A matplotlib Figure.
:raises ValueError: No numeric columns are available.

<!-- api:end -->

## Methods and parameters

Median and total scale each column to the median column median or sum. Quantile maps ranks to averaged sorted values. PQN uses a TIC-normalized reference to estimate quotients, then divides the original intensities. Log computes log2(x+1).

## Gotchas

- `normalize` preserves NaNs according to the method and performs no imputation. Zero divisors become NaN. The input index is retained in `tables/normalized.csv`.

## Inputs and outputs

CSV input; `tables/normalized.csv`, `report.md` and `result.json`. The CLI writes `reproducibility/commands.sh`.
The function library returns objects; the CLI and step own file writes.

## CLI

```bash
python skills/metabolomics/metabolomics-normalization/metabolomics_normalization.py --demo --output /tmp/metabolomics_normalization
```

## See also

- [Parameters](references/parameters.md)
- [Methodology](references/methodology.md)
- [Output contract](references/output_contract.md)

## Dependencies

`numpy`, `pandas`, `matplotlib`
