---
name: genomics-epigenomics
description: Load when summarising a peak file (BED / narrowPeak) from ATAC-seq / ChIP-seq / CUT&Tag —
  peak count, width distribution, per-chromosome counts, score statistics. Skip when calling peaks from
  BAM (run MACS / Genrich externally first); working with single-cell ATAC (use scatac-preprocessing).
trigger: epigenomics, ATAC-seq, ChIP-seq, peak calling, MACS, motif, chromatin
tags:
- genomics
- epigenomics
- atac-seq
- chip-seq
- cut-tag
- peaks
- macs
- bed
---

# genomics-epigenomics

## When to use

Load this skill for the file-based analysis named in the description.
The function library and CLI share the same calculations; no external
aligner, assembler, caller or annotation service is started.

## Use from a step

```python
from skills._sdk.notebook import load_skill, read_input, write_output
library = load_skill("genomics-epigenomics")
data = read_input("input.bed", reader=library.read_records)
result = library.analyze(data)
write_output(result, "tables/result.csv")
write_output(library.distribution_figure(result), "figures/distribution.png")
```

Run `examples/example_step.py` through the step runner for a small,
hand-worked synthetic fixture. It asserts known summary values.
The reader materializes the input in memory; use bounded FASTQ reads or
pre-filter large genomic files before loading them.

## API

<!-- api:begin generated from _api.py; regenerate with run.py api <skill dir> --write -->

### `read_records(path: str | Path) -> pd.DataFrame`

Read records through read_input(path, reader=library.read_records).

:param path: Existing input file in the format documented under Inputs and outputs.
:returns: Parsed records as a DataFrame.
:raises ValueError: Input values or file structure cannot be parsed.

### `analyze(data: pd.DataFrame, *, assay: str='chip-seq') -> pd.DataFrame`

Compute epigenomics summaries and return a new table, leaving data unchanged.

:param data: Records containing chrom, start, end.
:param assay: CLI default chip-seq; atac-seq and cut-tag change descriptive expectations.
:returns: Result table with diagnostics and summary in attrs['run_info'].
:raises ValueError: Required columns are absent or records are empty or invalid.

### `run_info(data: pd.DataFrame, *, keep: bool=True) -> dict`

Return the analysis diagnostics and summary.

:param data: Result returned by analyze.
:param keep: Keep diagnostics by default; the CLI passes False.
:returns: Independent diagnostics dictionary.
:raises ValueError: analyze has not populated diagnostics.

### `distribution_figure(data: pd.DataFrame)`

Plot width values without writing files.

:param data: Result table containing width.
:returns: Matplotlib Figure.
:raises ValueError: The value column is absent or the table is empty.

<!-- api:end -->

## Methods and parameters

`analyze` returns a new DataFrame and leaves the input unchanged.
`run_info(result)` returns the summary and method diagnostics.
The CLI passes `keep=False` so diagnostics do not enter output tables.
All calculations are deterministic; synthetic CLI demos retain seed 42.

## Gotchas

- `analyze` uses BED zero-based, half-open coordinates and recomputes width as end minus start. It does not call peaks.
- `run_info()["summary"]` retains the legacy p/q-value heuristic: medians above 1 are treated as negative-log10 values. Convert or inspect inputs before interpreting significance.
- `read_records` treats a .csv suffix as CSV and other suffixes as BED/narrowPeak. `assay` only changes descriptive expectations.

## Inputs and outputs

Input files:

- Modalities: atac-seq, chip-seq
- File types: `.bed`, `.narrowpeak`, `.csv`

CLI output files:

- `tables/peaks_per_chromosome.csv`
- `tables/peaks_summary.csv`
- `report.md`
- `result.json`

The library writes no files. Steps use `write_output`; the CLI owns the
listed artifacts. Public figure functions return matplotlib Figures and
do not add new CLI outputs.

## CLI

```bash
python skills/genomics/genomics-epigenomics/genomics_epigenomics.py --input input_file --output results/
python skills/genomics/genomics-epigenomics/genomics_epigenomics.py --demo --output /tmp/genomics_epigenomics_demo
```

## See also

- `references/parameters.md`
- `references/methodology.md`
- `references/output_contract.md`

## Dependencies

`numpy`, `pandas`, `matplotlib`
