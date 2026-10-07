---
name: bulkrna-read-qc
description: Load when checking raw FASTQ quality (Phred / GC / adapter / Q20-Q30) before alignment in
  bulk RNA-seq. Skip when reads are already aligned (use bulkrna-read-alignment); counted (use bulkrna-qc);
  single-cell FASTQ (use sc-fastq-qc).
trigger: FASTQ QC, read quality, Phred, FastQC, adapter, GC content, Q20, Q30
tags:
- bulkrna
- FASTQ
- QC
- Phred
- GC-content
- adapter
- read-quality
---

# bulkrna-read-qc

## When to use

Read raw Phred+33 FASTQ before alignment. This implements selected quality
metrics, not the complete FastQC suite. Use `bulkrna-read-alignment` for logs.

## Use from a step

```python
from skills._sdk.notebook import load_skill, write_output
library = load_skill('bulkrna-read-qc')
data = library.demo_data(random_state=42)
result = library.quality_control(data)
write_output(result, 'tables/qc_summary.csv')
```

For real files, pass `read_fastq`, `read_log` or `read_reference` as appropriate
to `read_input(..., reader=...)`. `examples/example_step.py` is executable.

## API

<!-- api:begin generated from _api.py; regenerate with run.py api <skill dir> --write -->

### `read_fastq(path: str | Path, *, max_reads: int=100000) -> pd.DataFrame`

Read FASTQ records; pass this function as reader= to read_input.

:param path: FASTQ path; a .gz suffix selects gzip decompression.
:param max_reads: CLI limit 100000; increase for a larger leading-read sample.
:returns: Sequence and Phred+33 quality strings as rows.
:raises ValueError: Records are truncated, malformed, or have unequal sequence/quality lengths.

### `quality_control(reads: pd.DataFrame, *, max_reads: int=100000) -> pd.DataFrame`

Compute a new one-row quality summary for Phred+33 reads.

:param reads: sequence and quality string columns; input rows are not changed.
:param max_reads: CLI default 100000 leading records; increase to inspect more reads.
:returns: Scalar QC metrics and adapter counts; run_info retains per-base distributions.
:raises ValueError: Reads, lengths or Phred+33 scores are invalid.

### `run_info(result: pd.DataFrame, *, keep: bool=True) -> dict`

Read full quality distributions and sampling diagnostics.

:param result: Output of quality_control.
:param keep: True preserves attrs; False removes diagnostics before serialization.
:returns: A separate dictionary containing metrics and sampling provenance.
:raises TypeError: The result is not a DataFrame.

### `quality_figure(result: pd.DataFrame)`

Plot mean and interquartile quality by read position.

:param result: QC result retaining its diagnostic attrs.
:returns: A matplotlib Figure without writing files.
:raises KeyError: Per-base diagnostics are absent.

### `gc_figure(result: pd.DataFrame)`

Plot GC fractions across sampled reads.

:param result: QC result retaining its diagnostic attrs.
:returns: A matplotlib Figure without writing files.
:raises KeyError: GC diagnostics are absent.

### `demo_data(*, random_state: int=42) -> pd.DataFrame`

Generate valid synthetic FASTQ records in memory.

:param random_state: CLI seed 42; change for another simulation without altering global RNG state.
:returns: Five thousand 150-base reads with quality strings of the same length.
:raises ValueError: The seed is invalid.

<!-- api:end -->

## Methods and parameters

`read_fastq` reads the leading 100000 records by default and accepts `.gz`.
`quality_control` computes per-base quality, Q20/Q30, GC, lengths and adapter
motif hits from sequence/quality strings. It does not trim reads.

## Gotchas

- `read_fastq` rejects truncated FASTQ and unequal sequence/quality lengths.
- `quality_control` assumes Phred+33, not the older Phred+64 encoding.
- `adapter_rate` sums motif hits and can exceed 100% if a read contains multiple adapters.

## Inputs and outputs

The CLI writes these artifacts; functions return DataFrames and Figures without writing them:

- `tables/qc_summary.csv`
- `figures/per_base_quality.png`
- `figures/gc_content.png`
- `figures/read_length_distribution.png`
- `figures/quality_score_distribution.png`
- `report.md`
- `result.json`
- `reproducibility/commands.sh`
- `demo_reads.fastq` only with `--demo`.

## CLI

```bash
python skills/bulkrna/bulkrna-read-qc/bulkrna_read_qc.py --demo --output /tmp/bulkrna_read_qc
```

For real files use `--input <file>`; trajectory placement also needs `--reference <file>`.

## See also

- `references/methodology.md`
- `references/parameters.md`
- `references/output_contract.md`

## Dependencies

`matplotlib`, `numpy`, `pandas`
