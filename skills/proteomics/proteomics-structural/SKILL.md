---
name: proteomics-structural
description: Load when summarising cross-linking MS (XL-MS) results — intra/inter-protein link split,
  optional FDR filtering, distance-constraint validation against a per-crosslinker (DSS / BS3 / EDC /
  DSSO / DSBU) max distance. Skip when raw spectra are the input (run XlinkX / pLink / xiSEARCH first);
  no XL-MS experiment was performed.
trigger: structural proteomics, cross-linking MS, XL-MS, XlinkX, pLink, xiSEARCH
tags:
- proteomics
- structural
- xl-ms
- crosslinking
- dss
- bs3
- dsso
- dsbu
- edc
---

# proteomics-structural

## When to use

The CLI defaults are DSS and fdr_threshold=0.05. DSS/BS3/DSSO/DSBU use 30 angstrom; EDC uses 20 angstrom.
Use existing search-engine tables; this skill does not search raw spectra.

## Use from a step

```python
from skills._sdk.notebook import load_skill, write_output
library = load_skill('proteomics-structural')
data = library.demo_data(random_state=42)
result = library.analyse_crosslinks(data)
write_output(result, 'tables/crosslinks.csv')
```

For real data, use `read_input` and pass any `read_table` helper as `reader=`.
The executable `examples/example_step.py` also checks the result and writes a Figure.

## API

<!-- api:begin generated from _api.py; regenerate with run.py api <skill dir> --write -->

### `analyse_crosslinks(data: pd.DataFrame, *, fdr_threshold: float=0.05, crosslinker: str='DSS') -> pd.DataFrame`

Return filtered crosslinks with protein-pair and optional distance classifications.

:param data: Crosslink rows with protein_a and protein_b, optional fdr and distance_angstrom.
:param fdr_threshold: CLI default 0.05; filters only when an fdr column is present.
:param crosslinker: CLI default DSS; BS3, DSSO and DSBU use 30 A, EDC uses 20 A.
:returns: New crosslink table; absent distance evidence remains unchecked in run_info.
:raises ValueError: Protein identifiers, crosslinker or confidence threshold are invalid.

### `run_info(table: pd.DataFrame, *, keep: bool=True) -> dict`

Read crosslink analysis diagnostics.

:param table: Output of analyse_crosslinks.
:param keep: True preserves attrs; False removes diagnostics.
:returns: A separate dictionary stating which optional checks ran.
:raises TypeError: The input is not a DataFrame.

### `distance_figure(table: pd.DataFrame)`

Plot measured crosslink distances.

:param table: Crosslinks containing distance_angstrom.
:returns: A matplotlib Figure without writing files.
:raises KeyError: distance_angstrom is absent.

### `demo_data(*, random_state: int=42) -> pd.DataFrame`

Generate synthetic crosslink records in memory.

:param random_state: CLI seed 42; change for another simulation.
:returns: Two hundred crosslinks with simulated distances and confidence.
:raises ValueError: The seed is invalid.

<!-- api:end -->

## Methods and parameters

The CLI defaults are DSS and fdr_threshold=0.05. DSS/BS3/DSSO/DSBU use 30 angstrom; EDC uses 20 angstrom.
Functions return new DataFrames. `run_info(result)` reads diagnostic attrs;
use `keep=False` before serialization when those attrs are not needed.

## Gotchas

- analyse_crosslinks requires protein_a and protein_b. run_info records missing distance evidence as unchecked with null satisfaction counts, never 100% passed. FDR filtering requires an fdr column.
- `demo_data` uses seed 42, matching the CLI; every demo is synthetic.
- `run_info` lives in DataFrame attrs and is not preserved by CSV serialization.

## Inputs and outputs

The CLI reads CSV tables and writes:

- tables/crosslinks.csv
- tables/inter_protein_crosslinks.csv (when link_type exists; can be empty)
- report.md
- result.json
- `demo_crosslinks.csv` is written only with `--demo`.

Functions return data and Figures without writing files. Steps own their outputs.
Demo mode also writes its synthetic input when the original CLI used a file.

## CLI

```bash
python skills/proteomics/proteomics-structural/struct_proteomics.py --demo --output /tmp/proteomics_structural
```

For real input replace `--demo` with `--input <table>`.


## See also

- `references/methodology.md`
- `references/parameters.md`
- `references/output_contract.md`
- `proteomics-data-import` for protein-table normalization; `proteomics-de` for comparisons.

## Dependencies

`numpy`, `pandas`, `matplotlib`
