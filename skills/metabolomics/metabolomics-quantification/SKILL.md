---
name: metabolomics-quantification
description: Load when imputing missing values (min / median / KNN) and normalising (TIC / median / log)
  a feature × sample metabolomics CSV. Skip when only normalisation is needed (use metabolomics-normalization);
  the input is raw spectra (use metabolomics-xcms-preprocessing).
trigger: metabolomics quantification, imputation, feature quantification, missing values
tags:
- metabolomics
- quantification
- imputation
- normalization
- knn
- tic
---

# metabolomics-quantification

## When to use

Impute zeros/NaNs and normalize sample intensities while keeping feature metadata. Use metabolomics-normalization for normalization alone.

## Use from a step

```python
import pandas as pd
from skills._sdk.notebook import load_skill, read_input, write_output
library = load_skill("metabolomics-quantification")
data = read_input('features.csv', reader=pd.read_csv)
result = library.quantify(data)
write_output(result, 'tables/result.csv')
```

[examples/example_step.py](examples/example_step.py) runs a seeded synthetic
example through the step runner and writes a table and Figure. Computations
return new DataFrames, leave the input unchanged and expose diagnostics through
`run_info(result)`. Plotting functions write no files.

## API

<!-- api:begin generated from _api.py; regenerate with run.py api <skill dir> --write -->

### `quantify(data, *, impute='min', normalize='tic')`

Return imputed and normalized intensities with metadata preserved.

:param data: Feature table with sample/intensity columns; zeros and NaNs are missing.
:param impute: CLI default min (half global positive minimum); median or knn also work.
:param normalize: CLI default tic; median or log are alternatives.
:returns: A new DataFrame with missing-value counts in attrs['run_info'].
:raises ValueError: Samples are absent, have no positive observations or a method is unknown.
:raises ImportError: KNN requires scikit-learn; use install_skill_deps.

### `run_info(data, *, keep=True)`

Read diagnostics attached to a returned table.

:param data: DataFrame returned by this library.
:param keep: Default True; use False in the CLI to remove diagnostics.
:returns: An independent dictionary describing the run.
:raises ValueError: The table carries no run_info.

### `distribution_figure(data)`

Plot sample intensities, excluding numeric feature metadata.

:param data: The input or quantified feature table.
:returns: A matplotlib Figure.
:raises ValueError: No numeric sample columns are available.

<!-- api:end -->

## Methods and parameters

Min imputation uses half the global positive minimum, median uses each column positive median, and KNN uses neighbouring feature rows with up to five neighbours. TIC scales column sums to their median; median scales column medians; log computes log2(x+1).

## Gotchas

- `quantify` detects sample/intensity prefixes, then numeric columns excluding feature_id, mz, rt, name and id. Every sample needs a positive observed intensity; completely missing samples raise ValueError for all methods.

## Inputs and outputs

CSV input; `tables/quantified_features.csv`, `report.md` and `result.json`. Demo mode also writes its synthetic input CSV at the output root.
The function library returns objects; the CLI and step own file writes.

## CLI

```bash
python skills/metabolomics/metabolomics-quantification/met_quantify.py --demo --output /tmp/metabolomics_quantification
```

## See also

- [Parameters](references/parameters.md)
- [Methodology](references/methodology.md)
- [Output contract](references/output_contract.md)

## Dependencies

`numpy`, `pandas`, `scikit-learn`, `matplotlib`
