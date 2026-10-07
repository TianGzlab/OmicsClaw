---
name: genomics-cnv-calling
description: Load when calling CNV segments via CBS-style segmentation on a bin-level log2-ratio CSV from
  exome / WGS coverage — emits per-segment 5-class CN state (`amplification` / `gain` / `neutral` / `loss`
  / `deep_deletion`), per-chromosome summary, genome-fraction-altered. Skip when working with single-cell
  / spatial CNV (use spatial-cnv).
trigger: CNV, copy number, amplification, deletion, CNVkit
tags:
- genomics
- cnv
- copy-number
- cbs
- segmentation
- cnvkit
- gatk-gcnv
---

# genomics-cnv-calling

## When to use

Load this skill for the file-based analysis named in the description.
The function library and CLI share the same calculations; no external
aligner, assembler, caller or annotation service is started.

## Use from a step

```python
from skills._sdk.notebook import load_skill, read_input, write_output
library = load_skill("genomics-cnv-calling")
data = read_input("input.csv", reader=library.read_bins)
result = library.analyze(data)
write_output(result, "tables/result.csv")
write_output(library.copy_ratio_figure(result), "figures/distribution.png")
```

Run `examples/example_step.py` through the step runner for a small,
hand-worked synthetic fixture. It asserts known summary values.
The reader materializes the input in memory; use bounded FASTQ reads or
pre-filter large genomic files before loading them.

## API

<!-- api:begin generated from _api.py; regenerate with run.py api <skill dir> --write -->

### `read_bins(path: str | Path) -> pd.DataFrame`

Read a bin CSV through read_input(path, reader=library.read_bins).

:param path: CSV containing chrom, start, end and log2_ratio.
:returns: Bin table.
:raises ValueError: The CSV cannot be parsed.

### `analyze(data: pd.DataFrame, *, method: str='cbs', alpha: float=0.01) -> pd.DataFrame`

Return new CNV segments from bin-level log2 ratios; leave data unchanged.

:param data: Bins with chrom, start, end and finite log2_ratio.
:param method: CLI default cbs, or none to classify individual bins.
:param alpha: CLI default 0.01; smaller values require stronger splits.
:returns: Segments with cn_state, estimated_cn and attrs['run_info'].
:raises ValueError: Columns, coordinates, method or alpha are invalid.

### `run_info(data: pd.DataFrame, *, keep: bool=True) -> dict`

Return analysis diagnostics and numeric summary.

:param data: Result returned by analyze.
:param keep: Keep diagnostics by default; the CLI passes False.
:returns: Independent copy of run diagnostics.
:raises ValueError: analyze has not populated diagnostics.

### `copy_ratio_figure(data: pd.DataFrame)`

Plot segment log2 ratios in table order without writing a file.

:param data: Segment table returned by analyze.
:returns: Matplotlib Figure.
:raises ValueError: log2_ratio is absent or the table is empty.

<!-- api:end -->

## Methods and parameters

`analyze` returns a new DataFrame and leaves the input unchanged.
`run_info(result)` returns the summary and method diagnostics.
The CLI passes `keep=False` so diagnostics do not enter output tables.
All calculations are deterministic; synthetic CLI demos retain seed 42.

## Gotchas

- `analyze(method="cbs")` uses the existing simplified deterministic split heuristic, not CNVkit or a calibrated CBS permutation test.
- `run_info()["summary"]["genome_fraction_altered"]` retains the legacy fraction of altered segments, not a base-pair-weighted genome fraction.
- `analyze(method="none")` classifies individual bins; gain/loss thresholds are 0.3/-0.3 and amplification/deep-deletion thresholds are 1/-1.

## Inputs and outputs

Input files:

- File types: `.csv`

CLI output files:

- `tables/cnv_per_chromosome.csv`
- `tables/cnv_segments.csv`
- `report.md`
- `result.json`

The library writes no files. Steps use `write_output`; the CLI owns the
listed artifacts. Public figure functions return matplotlib Figures and
do not add new CLI outputs.

## CLI

```bash
python skills/genomics/genomics-cnv-calling/genomics_cnv_calling.py --input input_file --output results/
python skills/genomics/genomics-cnv-calling/genomics_cnv_calling.py --demo --output /tmp/genomics_cnv_calling_demo
```

## See also

- `references/parameters.md`
- `references/methodology.md`
- `references/output_contract.md`

## Dependencies

`numpy`, `pandas`, `matplotlib`
