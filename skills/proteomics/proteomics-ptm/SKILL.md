---
name: proteomics-ptm
description: Load when summarising PTM sites (phosphorylation, acetylation, ubiquitination, etc.) from
  a per-site CSV — site-class assignment (Olsen et al. Class I/II/III by `localization_probability`),
  per-PTM-type counts, amino-acid distribution, sites-per-protein. Skip when raw spectra are the input;
  you only need protein-level abundance (use proteomics-quantification).
trigger: PTM, phosphorylation, acetylation, ubiquitination, modification, motif
tags:
- proteomics
- ptm
- phosphorylation
- acetylation
- ubiquitination
- site-localization
---

# proteomics-ptm

## When to use

Class I starts at loc_threshold (default 0.75); Class II starts at 0.50. The PTM type is case-sensitive.
Use existing search-engine tables; this skill does not search raw spectra.

## Use from a step

```python
from skills._sdk.notebook import load_skill, write_output
library = load_skill('proteomics-ptm')
data = library.demo_data(random_state=42)
result = library.classify_sites(data)
write_output(result, 'tables/ptm_sites.csv')
```

For real data, use `read_input` and pass any `read_table` helper as `reader=`.
The executable `examples/example_step.py` also checks the result and writes a Figure.

## API

<!-- api:begin generated from _api.py; regenerate with run.py api <skill dir> --write -->

### `classify_sites(data: pd.DataFrame, *, loc_threshold: float=0.75) -> pd.DataFrame`

Return a new PTM table with localization confidence classes.

:param data: Site rows with protein and ptm_type; localization_probability is optional.
:param loc_threshold: CLI default 0.75 for Class I; Class II starts at 0.50.
:returns: Classified sites with summary diagnostics in attrs.
:raises ValueError: Required columns are absent or the threshold is outside [0.5, 1].

### `run_info(table: pd.DataFrame, *, keep: bool=True) -> dict`

Read PTM classification diagnostics.

:param table: Classified PTM sites.
:param keep: True preserves attrs; False removes diagnostics.
:returns: A separate dictionary with localization threshold and summary.
:raises TypeError: The input is not a DataFrame.

### `class_figure(table: pd.DataFrame)`

Plot site counts by localization class.

:param table: Classified PTM sites containing site_class.
:returns: A matplotlib Figure without writing files.
:raises KeyError: site_class is absent.

### `demo_data(*, random_state: int=42) -> pd.DataFrame`

Generate synthetic PTM sites in memory.

:param random_state: CLI seed 42; change for another simulation.
:returns: Two hundred synthetic site records.
:raises ValueError: The seed is invalid.

<!-- api:end -->

## Methods and parameters

Class I starts at loc_threshold (default 0.75); Class II starts at 0.50. The PTM type is case-sensitive.
Functions return new DataFrames. `run_info(result)` reads diagnostic attrs;
use `keep=False` before serialization when those attrs are not needed.

## Gotchas

- classify_sites returns Unknown when localization_probability is absent. tables/ptm_class_I_sites.csv can be empty.
- `demo_data` uses seed 42, matching the CLI; every demo is synthetic.
- `run_info` lives in DataFrame attrs and is not preserved by CSV serialization.

## Inputs and outputs

The CLI reads CSV tables and writes:

- tables/ptm_sites.csv
- tables/ptm_class_I_sites.csv
- report.md
- result.json
- `demo_ptm_sites.csv` is written only with `--demo`.

Functions return data and Figures without writing files. Steps own their outputs.
Demo mode also writes its synthetic input when the original CLI used a file.

## CLI

```bash
python skills/proteomics/proteomics-ptm/proteomics_ptm.py --demo --output /tmp/proteomics_ptm
```

For real input replace `--demo` with `--input <table>`.


## See also

- `references/methodology.md`
- `references/parameters.md`
- `references/output_contract.md`
- `proteomics-data-import` for protein-table normalization; `proteomics-de` for comparisons.

## Dependencies

`numpy`, `pandas`, `matplotlib`
