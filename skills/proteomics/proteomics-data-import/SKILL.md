---
name: proteomics-data-import
description: Load when ingesting a MaxQuant `proteinGroups.txt`, FragPipe `combined_protein.tsv`, DIA-NN
  report, or generic CSV / TSV protein-quantification table — normalises columns to a standard schema,
  emits `tables/proteins.csv`. Skip when raw spectra are the input (run the search engine first); the
  file is already OmicsClaw schema.
trigger: data import, convert proteomics, format conversion
tags:
- proteomics
- import
- maxquant
- fragpipe
- diann
- spectronaut
---

# proteomics-data-import

## When to use

maxquant is the default; fragpipe, diann and generic normalize their own column names. read_table detects CSV/TSV separation.
Use existing search-engine tables; this skill does not search raw spectra.

## Use from a step

```python
from skills._sdk.notebook import load_skill, write_output
library = load_skill('proteomics-data-import')
data = library.demo_data(random_state=42)
result = library.standardize(data)
write_output(result, 'tables/proteins.csv')
```

For real data, use `read_input` and pass any `read_table` helper as `reader=`.
The executable `examples/example_step.py` also checks the result and writes a Figure.

## API

<!-- api:begin generated from _api.py; regenerate with run.py api <skill dir> --write -->

### `read_table(path: str | Path) -> pd.DataFrame`

Read a CSV or TSV; pass this function as reader= to read_input.

:param path: Search-engine output file; the first line selects comma or tab separation.
:returns: Unmodified input columns as a DataFrame.
:raises OSError: The file cannot be read.

### `standardize(data: pd.DataFrame, *, format: str='maxquant') -> pd.DataFrame`

Return a standardized copy of a search-engine protein table.

:param data: Original protein table with engine-specific column names.
:param format: CLI default maxquant; fragpipe, diann and generic use their own mappings.
:returns: Protein table; MaxQuant reverse, contaminant and site-only flags are filtered.
:raises ValueError: The format is unsupported.

### `run_info(table: pd.DataFrame, *, keep: bool=True) -> dict`

Read import diagnostics.

:param table: Standardized protein table.
:param keep: True preserves attrs; False removes diagnostics.
:returns: A separate diagnostic dictionary.
:raises TypeError: The input is not a DataFrame.

### `intensity_figure(table: pd.DataFrame)`

Plot numeric column medians for checking an imported table.

:param table: Standardized protein table; numeric metadata is included.
:returns: A matplotlib Figure without writing files.
:raises TypeError: The input is not a DataFrame.

### `demo_data(*, random_state: int=42) -> pd.DataFrame`

Generate a synthetic MaxQuant table in memory.

:param random_state: CLI seed 42; change for another simulation.
:returns: Two hundred protein rows, including five flagged rows.
:raises ValueError: The seed is invalid.

<!-- api:end -->

## Methods and parameters

maxquant is the default; fragpipe, diann and generic normalize their own column names. read_table detects CSV/TSV separation.
Functions return new DataFrames. `run_info(result)` reads diagnostic attrs;
use `keep=False` before serialization when those attrs are not needed.

## Gotchas

- standardize filters MaxQuant Reverse, Potential contaminant and Only identified by site flags. Generic import does not infer those flags.
- `demo_data` uses seed 42, matching the CLI; every demo is synthetic.
- `run_info` lives in DataFrame attrs and is not preserved by CSV serialization.

## Inputs and outputs

The CLI reads CSV tables and writes:

- tables/proteins.csv
- report.md
- result.json
- `demo_proteinGroups.txt` is written only with `--demo`.

Functions return data and Figures without writing files. Steps own their outputs.
Demo mode also writes its synthetic input when the original CLI used a file.

## CLI

```bash
python skills/proteomics/proteomics-data-import/proteomics_data_import.py --demo --output /tmp/proteomics_data_import
```

For real input replace `--demo` with `--input <table>`.


## See also

- `references/methodology.md`
- `references/parameters.md`
- `references/output_contract.md`
- `proteomics-data-import` for protein-table normalization; `proteomics-de` for comparisons.

## Dependencies

`numpy`, `pandas`, `matplotlib`
