---
name: bulkrna-read-alignment
description: Load when summarising STAR / HISAT2 / Salmon alignment-rate logs in bulk RNA-seq. Skip when
  data is raw FASTQ (use bulkrna-read-qc); already counted (use bulkrna-qc); genome-DNA alignment (use
  genomics-alignment).
trigger: RNA-seq alignment, STAR, HISAT2, Salmon, mapping rate, read alignment, alignment QC
tags:
- bulkrna
- alignment
- STAR
- HISAT2
- Salmon
- mapping-rate
- strandedness
---

# bulkrna-read-alignment

## When to use

Summarize existing STAR, paired-end HISAT2 or Salmon logs. This does not run
an aligner. Use `bulkrna-read-qc` for FASTQ and `bulkrna-qc` for counts.

## Use from a step

```python
from skills._sdk.notebook import load_skill, write_output
library = load_skill('bulkrna-read-alignment')
data = library.demo_data(random_state=42)
result = library.summarize(data)
write_output(result, 'tables/alignment_stats.csv')
```

For real files, pass `read_fastq`, `read_log` or `read_reference` as appropriate
to `read_input(..., reader=...)`. `examples/example_step.py` is executable.

## API

<!-- api:begin generated from _api.py; regenerate with run.py api <skill dir> --write -->

### `read_log(path: str | Path) -> str`

Read log text; pass this function as reader= to read_input.

:param path: STAR, HISAT2 or Salmon text/JSON log.
:returns: File contents without interpreting its filename.
:raises OSError: The file cannot be read.

### `summarize(data: str | pd.DataFrame, *, method: str='star') -> pd.DataFrame`

Parse alignment counts and return a new mapping summary.

:param data: Log text or a one-row parsed table, including demo_data output.
:param method: CLI default star; select hisat2 for paired-end summaries or salmon for meta_info JSON.
:returns: Mapping counts/rates with quality heuristics in run_info; Salmon reports total mapped, not unique mapped.
:raises ValueError: Required counts are missing, inconsistent or the method is unsupported.

### `run_info(result: pd.DataFrame, *, keep: bool=True) -> dict`

Read mapping assessment and unavailable-evidence diagnostics.

:param result: Output of summarize.
:param keep: True preserves attrs; False removes diagnostics before serialization.
:returns: A separate quality/provenance dictionary.
:raises TypeError: The result is not a DataFrame.

### `mapping_figure(result: pd.DataFrame)`

Plot observed mapping counts as percentages.

:param result: Output of summarize.
:returns: A matplotlib Figure without writing files.
:raises KeyError: Mapping counts are absent.

### `composition_figure(result: pd.DataFrame)`

Plot observed mapping composition.

:param result: Output of summarize.
:returns: A matplotlib Figure without writing files.
:raises KeyError: Mapping counts are absent.

### `coverage_figure(coverage: pd.DataFrame)`

Plot an explicitly supplied gene-body coverage profile.

:param coverage: position and coverage columns; alignment logs cannot supply these observations.
:returns: A matplotlib Figure without synthesizing missing measurements.
:raises KeyError: Coverage columns are absent.

### `demo_data(*, random_state: int=42) -> pd.DataFrame`

Generate the synthetic STAR summary used by the CLI demo.

:param random_state: CLI seed 42; change for another simulation.
:returns: One simulated alignment summary row.
:raises ValueError: The seed is invalid.

### `demo_coverage(*, random_state: int=42) -> pd.DataFrame`

Generate an illustrative coverage profile, not inferred from an alignment log.

:param random_state: CLI demo seed 42; change for another simulation.
:returns: One hundred simulated percentile/coverage rows.
:raises ValueError: The seed is invalid.

<!-- api:end -->

## Methods and parameters

`summarize` defaults to STAR, matching the CLI. Choose `hisat2` or `salmon`
explicitly; filenames do not override that choice. STAR/HISAT2 include unique
and multimapped counts. Salmon meta_info reports total mapped counts only.

## Gotchas

- `summarize` rejects absent or inconsistent read counts.
- `run_info` states that logs provide neither gene-body coverage nor inferred strandedness.
- `coverage_figure` needs an explicit measured profile. `demo_coverage` is synthetic and is only used by `--demo`.
- `mapped_rate` for Salmon does not mean uniquely mapped rate.
- HISAT2 `unmapped` is the residual after concordant pairs and includes discordant/unpaired mappings; `run_info` records this limitation.

## Inputs and outputs

The CLI writes these artifacts; functions return DataFrames and Figures without writing them:

- `tables/alignment_stats.csv`
- `figures/mapping_summary.png`
- `figures/alignment_composition.png`
- `figures/gene_body_coverage.png (demo only)`
- `report.md`
- `result.json`
- `reproducibility/commands.sh`

## CLI

```bash
python skills/bulkrna/bulkrna-read-alignment/bulkrna_read_alignment.py --demo --output /tmp/bulkrna_read_alignment
```

For real files use `--input <file>`; trajectory placement also needs `--reference <file>`.

## See also

- `references/methodology.md`
- `references/parameters.md`
- `references/output_contract.md`

## Dependencies

`matplotlib`, `numpy`, `pandas`
