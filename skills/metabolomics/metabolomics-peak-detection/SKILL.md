---
name: metabolomics-peak-detection
description: Load when running per-sample peak picking on a feature × intensity table via `scipy.signal.find_peaks`
  — emits per-(sample, feature) detected peaks with prominence and width. Skip when working with mz /
  RT raw scans (use metabolomics-xcms-preprocessing); only normalising / quantifying (use metabolomics-quantification).
trigger: peak detection, feature detection, XCMS, MZmine, MS-DIAL, peak picking
tags:
- metabolomics
- peak-detection
- find-peaks
- xcms
- mzmine
---

# metabolomics-peak-detection

## When to use

Detect peaks on tabular sample signals ordered by retention time. This is not raw mzML peak extraction; run XCMS externally for that workflow.

## Use from a step

```python
import pandas as pd
from skills._sdk.notebook import load_skill, read_input, write_output
library = load_skill("metabolomics-peak-detection")
data = read_input('features.csv', reader=pd.read_csv)
result = library.detect_peaks(data)
write_output(result, 'tables/result.csv')
```

[examples/example_step.py](examples/example_step.py) runs a seeded synthetic
example through the step runner and writes a table and Figure. Computations
return new DataFrames, leave the input unchanged and expose diagnostics through
`run_info(result)`. Plotting functions write no files.

## API

<!-- api:begin generated from _api.py; regenerate with run.py api <skill dir> --write -->

### `detect_peaks(data, *, sample_cols=None, prominence=10000.0, height=None, distance=5)`

Detect per-sample peaks after sorting rows by retention time.

:param data: DataFrame with mz, rt and numeric sample intensities.
:param sample_cols: Explicit columns; None uses the CLI intensity/sample name detection.
:param prominence: CLI default 10000; adjust to the intensity scale.
:param height: CLI default None; optionally require a minimum peak height.
:param distance: CLI default 5; minimum separation in sorted row positions, not seconds.
:returns: A new peak DataFrame with diagnostics in attrs['run_info'].
:raises ValueError: No sample columns match or peak parameters are invalid.

### `run_info(data, *, keep=True)`

Read diagnostics attached to a returned table.

:param data: DataFrame returned by this library.
:param keep: Default True; use False in the CLI to remove diagnostics.
:returns: An independent dictionary describing the run.
:raises ValueError: The table carries no run_info.

### `peaks_figure(data)`

Plot detected peak intensity against retention time.

:param data: Peak table returned by detect_peaks.
:returns: A matplotlib Figure.
:raises KeyError: Required peak columns are absent.

<!-- api:end -->

## Methods and parameters

scipy.signal.find_peaks uses prominence, optional height and a row-index distance after sorting by rt. Widths are measured at half prominence in row-index units.

## Gotchas

- `detect_peaks` expects mz and rt plus sample/intensity columns. `distance` and `width` are row positions, not seconds. NaNs follow scipy signal semantics and are not imputed. Empty outputs keep their CSV column schema.

## Inputs and outputs

CSV input; `tables/detected_peaks.csv`, `report.md` and `result.json`. Demo mode also writes its synthetic input CSV at the output root.
The function library returns objects; the CLI and step own file writes.

## CLI

```bash
python skills/metabolomics/metabolomics-peak-detection/peak_detect.py --demo --output /tmp/metabolomics_peak_detection
```

## See also

- [Parameters](references/parameters.md)
- [Methodology](references/methodology.md)
- [Output contract](references/output_contract.md)

## Dependencies

`numpy`, `pandas`, `scipy`, `matplotlib`
