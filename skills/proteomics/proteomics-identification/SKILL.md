---
name: proteomics-identification
description: Load when summarising peptide identifications (PSM count, unique peptide count, distinct
  protein count, score / charge distributions) from a peptide-level CSV produced by MaxQuant / FragPipe
  / DIA-NN. Skip when raw spectra are the input (run a search engine first); working with protein-quantification
  tables (use proteomics-ms-qc).
trigger: peptide identification, database search, MaxQuant, MS-GF+, Comet, Mascot
tags:
- proteomics
- identification
- peptides
- psm
- maxquant
- msgf
---

# proteomics-identification

## When to use

Confidence filtering uses qvalue, q-value, q_value, PEP, pep or fdr in that order. The default threshold is 0.01.
Use existing search-engine tables; this skill does not search raw spectra.

## Use from a step

```python
from skills._sdk.notebook import load_skill, write_output
library = load_skill('proteomics-identification')
data = library.demo_data(random_state=42)
result = library.filter_identifications(data, n_spectra=1000)
write_output(result, 'tables/peptides.csv')
```

For real data, use `read_input` and pass any `read_table` helper as `reader=`.
The executable `examples/example_step.py` also checks the result and writes a Figure.

## API

<!-- api:begin generated from _api.py; regenerate with run.py api <skill dir> --write -->

### `read_table(path: str | Path) -> pd.DataFrame`

Read peptide CSV/TSV; pass this function as reader= to read_input.

:param path: Peptide table; txt and tsv suffixes select tab separation.
:returns: Table with common MaxQuant column names normalized.
:raises OSError: The file cannot be read.

### `filter_identifications(data: pd.DataFrame, *, fdr_threshold: float=0.01, n_spectra: int | None=None) -> pd.DataFrame`

Filter peptide confidence values and return a new table.

:param data: Existing peptide/protein rows with optional qvalue, q-value, q_value, PEP, pep or fdr.
:param fdr_threshold: CLI default 0.01; PEP thresholding is not a global FDR estimate.
:param n_spectra: Total spectra; CLI default None uses retained PSM count, not an observed identification rate.
:returns: Filtered rows with the actual confidence column and summary in attrs.
:raises ValueError: Threshold or spectrum count is invalid.

### `run_info(table: pd.DataFrame, *, keep: bool=True) -> dict`

Read identification diagnostics.

:param table: Filtered peptide table.
:param keep: True preserves attrs; False removes diagnostics.
:returns: A separate dictionary with filter provenance and summary.
:raises TypeError: The input is not a DataFrame.

### `score_figure(table: pd.DataFrame)`

Plot peptide identification scores.

:param table: Peptide table including score.
:returns: A matplotlib Figure without writing files.
:raises KeyError: score is absent.

### `demo_data(*, random_state: int=42) -> pd.DataFrame`

Simulate identifications for one thousand spectra.

:param random_state: CLI seed 42; change for another simulation.
:returns: Synthetic peptide identifications, not a search-engine result.
:raises ValueError: The seed is invalid.

<!-- api:end -->

## Methods and parameters

Confidence filtering uses qvalue, q-value, q_value, PEP, pep or fdr in that order. The default threshold is 0.01.
Functions return new DataFrames. `run_info(result)` reads diagnostic attrs;
use `keep=False` before serialization when those attrs are not needed.

## Gotchas

- filter_identifications warns and records an unfiltered result without confidence columns. PEP thresholding is not global FDR control. run_info marks inferred spectrum totals.
- `demo_data` uses seed 42, matching the CLI; every demo is synthetic.
- `run_info` lives in DataFrame attrs and is not preserved by CSV serialization.

## Inputs and outputs

The CLI reads CSV tables and writes:

- tables/peptides.csv
- report.md
- result.json
- `reproducibility/commands.sh` records the CLI invocation template.

Functions return data and Figures without writing files. Steps own their outputs.
Demo mode also writes its synthetic input when the original CLI used a file.

## CLI

```bash
python skills/proteomics/proteomics-identification/proteomics_identification.py --demo --output /tmp/proteomics_identification
```

For real input replace `--demo` with `--input <table>`.


## See also

- `references/methodology.md`
- `references/parameters.md`
- `references/output_contract.md`
- `proteomics-data-import` for protein-table normalization; `proteomics-de` for comparisons.

## Dependencies

`numpy`, `pandas`, `matplotlib`
