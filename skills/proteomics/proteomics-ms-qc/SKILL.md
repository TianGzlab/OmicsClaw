---
name: proteomics-ms-qc
description: Load when computing protein-table QC — proteins × samples count, missing-value rate, intensity
  CV (median + mean) — from a MaxQuant / FragPipe / DIA-NN protein-quantification CSV. Skip when raw mzML
  / RAW spectra are the input (run a search engine first); peptide-level QC is needed (use proteomics-identification).
trigger: MS QC, mass spec QC, PTXQC, rawTools
tags:
- proteomics
- qc
- ms
- maxquant
- intensity
- missing-values
- cv
---

# proteomics-ms-qc

## When to use

Numeric columns excluding metadata-like names are samples; if none remain, all numeric columns are used. Zero and NaN count as missing.
Use existing search-engine tables; this skill does not search raw spectra.

## Use from a step

```python
from skills._sdk.notebook import load_skill, write_output
library = load_skill('proteomics-ms-qc')
data = library.demo_data(random_state=42)
result = library.quality_control(data)
write_output(result, 'tables/qc_metrics.csv')
```

For real data, use `read_input` and pass any `read_table` helper as `reader=`.
The executable `examples/example_step.py` also checks the result and writes a Figure.

## API

<!-- api:begin generated from _api.py; regenerate with run.py api <skill dir> --write -->

### `quality_control(data: pd.DataFrame) -> pd.DataFrame`

Return a one-row QC table without changing input intensities.

:param data: Protein rows and numeric intensity columns; metadata-like names are excluded when possible.
:returns: Scalar QC metrics; per-sample completeness and selected columns are in run_info.
:raises ValueError: There are no proteins or numeric intensity columns.

### `run_info(table: pd.DataFrame, *, keep: bool=True) -> dict`

Read QC diagnostics.

:param table: Output of quality_control.
:param keep: True preserves attrs; False removes diagnostics.
:returns: A separate dictionary with selected sample columns and completeness.
:raises TypeError: The input is not a DataFrame.

### `completeness_figure(table: pd.DataFrame)`

Plot detected protein percentages per sample.

:param table: QC table retaining run_info attributes.
:returns: A matplotlib Figure without writing files.
:raises KeyError: QC diagnostics are absent.

### `demo_data(*, random_state: int=42) -> pd.DataFrame`

Generate a synthetic protein intensity table.

:param random_state: CLI seed 42; change for another simulation.
:returns: One hundred proteins and five sample columns.
:raises ValueError: The seed is invalid.

<!-- api:end -->

## Methods and parameters

Numeric columns excluding metadata-like names are samples; if none remain, all numeric columns are used. Zero and NaN count as missing.
Functions return new DataFrames. `run_info(result)` reads diagnostic attrs;
use `keep=False` before serialization when those attrs are not needed.

## Gotchas

- quality_control reports per-protein CV across positive intensities. run_info retains the actual sample columns and per-sample completeness.
- `demo_data` uses seed 42, matching the CLI; every demo is synthetic.
- `run_info` lives in DataFrame attrs and is not preserved by CSV serialization.

## Inputs and outputs

The CLI reads CSV tables and writes:

- tables/qc_metrics.csv
- report.md
- result.json
- `demo_proteomics.csv` is written only with `--demo`.

- `reproducibility/commands.sh` records the CLI invocation template.

Functions return data and Figures without writing files. Steps own their outputs.
Demo mode also writes its synthetic input when the original CLI used a file.

## CLI

```bash
python skills/proteomics/proteomics-ms-qc/proteomics_ms_qc.py --demo --output /tmp/proteomics_ms_qc
```

For real input replace `--demo` with `--input <table>`.


## See also

- `references/methodology.md`
- `references/parameters.md`
- `references/output_contract.md`
- `proteomics-data-import` for protein-table normalization; `proteomics-de` for comparisons.

## Dependencies

`numpy`, `pandas`, `matplotlib`
