---
name: genomics-alignment
description: Load when computing alignment QC metrics (mapping rate, MAPQ distribution, insert size, duplicate
  rate, proper-pair rate) from a text SAM file produced by any short-/long-read aligner (BWA / Bowtie2
  / Minimap2); convert a BAM with samtools view -h first. Skip when running the alignment step itself;
  only FASTQ-level QC is needed (use genomics-qc).
trigger: alignment, BWA, Bowtie2, Minimap2, map reads
tags:
- genomics
- alignment
- bam
- sam
- bwa
- bowtie2
- minimap2
---

# genomics-alignment

## When to use

Load this skill for the file-based analysis named in the description.
The function library and CLI share the same calculations; no external
aligner, assembler, caller or annotation service is started.

## Use from a step

```python
from skills._sdk.notebook import load_skill, read_input, write_output
library = load_skill("genomics-alignment")
data = read_input("input.sam", reader=library.read_records)
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

:param path: Input file in the format documented under Inputs and outputs.

:returns: Parsed records as a DataFrame.
:raises ValueError: Input values or file structure cannot be parsed.

### `analyze(data: pd.DataFrame) -> pd.DataFrame`

Compute alignment summaries and return a new table, leaving data unchanged.

:param data: Records containing flag, mapq, tlen.

:returns: Result table with diagnostics and summary in attrs['run_info'].
:raises ValueError: Required columns are absent or records are empty or invalid.

### `run_info(data: pd.DataFrame, *, keep: bool=True) -> dict`

Return analysis diagnostics and summary.

:param data: Result returned by analyze.
:param keep: Keep diagnostics by default; the CLI passes False.
:returns: Independent diagnostics dictionary.
:raises ValueError: analyze has not populated diagnostics.

### `distribution_figure(data: pd.DataFrame)`

Plot mapping_rate_pct values without writing files.

:param data: Result table containing mapping_rate_pct.
:returns: Matplotlib Figure.
:raises ValueError: The value column is absent or table is empty.

<!-- api:end -->

## Methods and parameters

`analyze` returns a new DataFrame and leaves the input unchanged.
`run_info(result)` returns the summary and method diagnostics.
The CLI passes `keep=False` so diagnostics do not enter output tables.
All calculations are deterministic; synthetic CLI demos retain seed 42.

## Gotchas

- `read_records` accepts text SAM, not binary BAM/CRAM; convert those upstream. No aligner or samtools is invoked.
- `run_info()["summary"]` excludes secondary and supplementary alignments from primary-read metrics; insert sizes count both mates, matching the legacy CLI.

## Inputs and outputs

Input files:

- File types: `.sam`

CLI output files:

- `tables/alignment_stats.csv`
- `report.md`
- `result.json`

The library writes no files. Steps use `write_output`; the CLI owns the
listed artifacts. Public figure functions return matplotlib Figures and
do not add new CLI outputs.

## CLI

```bash
python skills/genomics/genomics-alignment/genomics_alignment.py --input input_file --output results/
python skills/genomics/genomics-alignment/genomics_alignment.py --demo --output /tmp/genomics_alignment_demo
```

## See also

- `references/parameters.md`
- `references/methodology.md`
- `references/output_contract.md`

## Dependencies

`numpy`, `pandas`, `matplotlib`
