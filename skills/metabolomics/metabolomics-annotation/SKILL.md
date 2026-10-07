---
name: metabolomics-annotation
description: Load when annotating LC-MS features against a built-in 15-metabolite HMDB demo dictionary
  by m/z within a `--ppm` tolerance — emits a per-feature annotation table. Skip when needing spectral matching or online database searches (use external SIRIUS / GNPS).
trigger: metabolite annotation, SIRIUS, GNPS, MetFrag, spectral matching, metabolite ID, ppm tolerance
tags:
- metabolomics
- annotation
- hmdb
- demo
- mz-match
---

# metabolomics-annotation

## When to use

Match m/z to adduct masses in an explicit reference or the bundled 15-metabolite demo. Use external SIRIUS/GNPS for spectral or database-scale identification.

## Use from a step

```python
import pandas as pd
from skills._sdk.notebook import load_skill, read_input, write_output
library = load_skill("metabolomics-annotation")
data = read_input('features.csv', reader=pd.read_csv)
result = library.annotate(data)
write_output(result, 'tables/result.csv')
```

[examples/example_step.py](examples/example_step.py) runs a seeded synthetic
example through the step runner and writes a table and Figure. Computations
return new DataFrames, leave the input unchanged and expose diagnostics through
`run_info(result)`. Plotting functions write no files.

## API

<!-- api:begin generated from _api.py; regenerate with run.py api <skill dir> --write -->

### `annotate(data, *, database='hmdb', ppm=10.0, adducts=None, reference=None)`

Match every observed m/z to all reference adducts within tolerance.

:param data: Feature DataFrame with a numeric mz column.
:param database: CLI default hmdb; other labels require an explicit reference.
:param ppm: CLI default 10; nonnegative mass error tolerance in parts per million.
:param adducts: CLI default None resolves to [M+H]+ and [M-H]-.
:param reference: Optional DataFrame with name, neutral_mass, database_id and formula; None uses 15 demo metabolites.
:returns: A new annotations DataFrame; attrs['run_info'] names the reference scope.
:raises ValueError: Reference, observed masses, tolerance or adducts are invalid.

### `run_info(data, *, keep=True)`

Read diagnostics attached to a returned table.

:param data: DataFrame returned by this library.
:param keep: Default True; use False in the CLI to remove diagnostics.
:returns: An independent dictionary describing the run.
:raises ValueError: The table carries no run_info.

### `mass_error_figure(data)`

Plot the ppm error of matched metabolite candidates.

:param data: Annotation table returned by annotate.
:returns: A matplotlib Figure.
:raises KeyError: ppm_error is absent.

<!-- api:end -->

## Methods and parameters

The default hmdb lookup is a 15-entry demo. Pass reference= with name, neutral_mass, database_id and formula for local real-reference mass matching. No network lookup runs. The CLI has no reference-file flag.

## Gotchas

- `annotate` rejects other database labels without reference data. Each query can have multiple candidate rows in `tables/annotations.csv`; Unknown rows retain unmatched queries. Confidence labels describe ppm bins, not identification probability.

## Inputs and outputs

CSV input; `tables/annotations.csv`, `report.md` and `result.json`. The CLI writes `reproducibility/commands.sh`.
The function library returns objects; the CLI and step own file writes.

## CLI

```bash
python skills/metabolomics/metabolomics-annotation/metabolomics_annotation.py --demo --output /tmp/metabolomics_annotation
```

## See also

- [Parameters](references/parameters.md)
- [Methodology](references/methodology.md)
- [Output contract](references/output_contract.md)

## Dependencies

`numpy`, `pandas`, `matplotlib`
