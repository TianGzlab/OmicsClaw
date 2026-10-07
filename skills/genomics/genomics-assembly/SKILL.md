---
name: genomics-assembly
description: Load when computing genome-assembly QC metrics — N50/N90, L50/L90, total length, contig count,
  GC content, longest-contig — from a FASTA produced by any assembler (SPAdes / Megahit / Flye / Canu).
  Skip when running the assembly itself; assessing alignment quality (use genomics-alignment).
trigger: genome assembly, de novo, SPAdes, Megahit, Flye, Canu
tags:
- genomics
- assembly
- n50
- l50
- contig
- quast
- spades
- flye
---

# genomics-assembly

## When to use

Load this skill for the file-based analysis named in the description.
The function library and CLI share the same calculations; no external
aligner, assembler, caller or annotation service is started.

## Use from a step

```python
from skills._sdk.notebook import load_skill, read_input, write_output
library = load_skill("genomics-assembly")
data = read_input("input.fasta", reader=library.read_records)
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

### `analyze(data: pd.DataFrame, *, genome_size: int=0) -> pd.DataFrame`

Compute assembly summaries and return a new table, leaving data unchanged.

:param data: Records containing contig, sequence.
:param genome_size: CLI default 0 omits completeness; otherwise expected genome bases.
:returns: Result table with diagnostics and summary in attrs['run_info'].
:raises ValueError: Required columns are absent or records are empty or invalid.

### `run_info(data: pd.DataFrame, *, keep: bool=True) -> dict`

Return the analysis diagnostics and summary.

:param data: Result returned by analyze.
:param keep: Keep diagnostics by default; the CLI passes False.
:returns: Independent diagnostics dictionary.
:raises ValueError: analyze has not populated diagnostics.

### `distribution_figure(data: pd.DataFrame)`

Plot length values without writing files.

:param data: Result table containing length.
:returns: Matplotlib Figure.
:raises ValueError: The value column is absent or the table is empty.

<!-- api:end -->

## Methods and parameters

`analyze` returns a new DataFrame and leaves the input unchanged.
`run_info(result)` returns the summary and method diagnostics.
The CLI passes `keep=False` so diagnostics do not enter output tables.
All calculations are deterministic; synthetic CLI demos retain seed 42.

## Gotchas

- `run_info()["summary"]["completeness_pct"]` is assembly length divided by expected genome size, not a gene-completeness assessment.
- `read_records` uppercases FASTA sequence. GC content excludes N bases; no assembler or QUAST is invoked.

## Inputs and outputs

Input files:

- File types: `.fasta`, `.fa`

CLI output files:

- `tables/assembly_metrics.csv`
- `tables/contig_lengths.csv`
- `report.md`
- `result.json`

The library writes no files. Steps use `write_output`; the CLI owns the
listed artifacts. Public figure functions return matplotlib Figures and
do not add new CLI outputs.

## CLI

```bash
python skills/genomics/genomics-assembly/genome_assembly.py --input input_file --output results/
python skills/genomics/genomics-assembly/genome_assembly.py --demo --output /tmp/genomics_assembly_demo
```

## See also

- `references/parameters.md`
- `references/methodology.md`
- `references/output_contract.md`

## Dependencies

`numpy`, `pandas`, `matplotlib`
