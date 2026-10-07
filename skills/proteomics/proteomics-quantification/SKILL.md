---
name: proteomics-quantification
description: Load when computing per-protein abundance from a peptide / PSM table via LFQ (intensity summation),
  iBAQ (intensity / tryptic peptide count), or spectral counting (PSMs per protein). Skip when the input
  is already protein-level (use proteomics-ms-qc); label-based TMT / iTRAQ workflows (search upstream
  first).
trigger: protein quantification, LFQ, TMT, DIA, DIA-NN, Skyline
tags:
- proteomics
- quantification
- lfq
- ibaq
- spectral-counting
---

# proteomics-quantification

## When to use

lfq sums intensities; spectral_count counts PSM rows; ibaq divides by supplied theoretical counts or a sequence-derived tryptic count.
Use existing search-engine tables; this skill does not search raw spectra.

## Use from a step

```python
from skills._sdk.notebook import load_skill, write_output
library = load_skill('proteomics-quantification')
data = library.demo_data(random_state=42)
result = library.quantify(data)
write_output(result, 'tables/protein_abundance.csv')
```

For real data, use `read_input` and pass any `read_table` helper as `reader=`.
The executable `examples/example_step.py` also checks the result and writes a Figure.

## API

<!-- api:begin generated from _api.py; regenerate with run.py api <skill dir> --write -->

### `quantify(peptides: pd.DataFrame, *, method: str='lfq') -> pd.DataFrame`

Return a new protein abundance table without changing the peptides.

:param peptides: PSM rows with protein and method-specific intensity or sequence columns.
:param method: CLI default lfq sums intensity; spectral_count counts rows; ibaq divides by theoretical peptides.
:returns: Protein abundances with diagnostics in attrs.
:raises ValueError: Required columns or positive theoretical counts are missing.

### `run_info(table: pd.DataFrame, *, keep: bool=True) -> dict`

Read the diagnostics attached to a returned table.

:param table: Table returned by quantify.
:param keep: True preserves attrs; the CLI uses False before serialization.
:returns: A separate diagnostic dictionary.
:raises TypeError: The input is not a DataFrame.

### `abundance_figure(table: pd.DataFrame)`

Plot the distribution of protein abundance.

:param table: Output of quantify, including abundance.
:returns: A matplotlib Figure; no files are written.
:raises KeyError: The abundance column is absent.

### `demo_data(*, random_state: int=42) -> pd.DataFrame`

Generate synthetic peptide data in memory.

:param random_state: CLI seed 42; change to generate another simulation.
:returns: Synthetic peptides with protein sequences for iBAQ.
:raises ValueError: The seed is invalid.

<!-- api:end -->

## Methods and parameters

lfq sums intensities; spectral_count counts PSM rows; ibaq divides by supplied theoretical counts or a sequence-derived tryptic count.
Functions return new DataFrames. `run_info(result)` reads diagnostic attrs;
use `keep=False` before serialization when those attrs are not needed.

## Gotchas

- quantify rejects iBAQ without sequence or n_theoretical_peptides. LFQ is intensity summation, not MaxLFQ normalization.
- `demo_data` uses seed 42, matching the CLI; every demo is synthetic.
- `run_info` lives in DataFrame attrs and is not preserved by CSV serialization.

## Inputs and outputs

The CLI reads CSV tables and writes:

- tables/protein_abundance.csv
- report.md
- result.json
- `reproducibility/commands.sh` records the CLI invocation template.

Functions return data and Figures without writing files. Steps own their outputs.
Demo mode also writes its synthetic input when the original CLI used a file.

## CLI

```bash
python skills/proteomics/proteomics-quantification/proteomics_quantification.py --demo --output /tmp/proteomics_quantification
```

For real input replace `--demo` with `--input <table>`.


## See also

- `references/methodology.md`
- `references/parameters.md`
- `references/output_contract.md`
- `proteomics-data-import` for protein-table normalization; `proteomics-de` for comparisons.

## Dependencies

`numpy`, `pandas`, `matplotlib`
