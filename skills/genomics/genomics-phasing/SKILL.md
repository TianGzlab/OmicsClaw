---
name: genomics-phasing
description: Load when summarising a phased VCF (output of WhatsHap / SHAPEIT5 / Eagle2) — phased fraction
  of het variants, phase-block N50, PS-field parsing, pipe-delimited genotype detection. Skip when the
  input is unphased (run a phaser first); calling small variants (use genomics-variant-calling).
trigger: haplotype phasing, WhatsHap, SHAPEIT, Eagle, phasing
tags:
- genomics
- phasing
- haplotype
- whatshap
- shapeit
- eagle
- ps
---

# genomics-phasing

## When to use

Load this skill for the file-based analysis named in the description.
The function library and CLI share the same calculations; no external
aligner, assembler, caller or annotation service is started.

## Use from a step

```python
from skills._sdk.notebook import load_skill, read_input, write_output
library = load_skill("genomics-phasing")
data = read_input("input.vcf", reader=library.read_records)
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

### `analyze(data: pd.DataFrame) -> pd.DataFrame`

Compute phasing summaries and return a new table, leaving data unchanged.

:param data: Records containing chrom, pos, gt, is_phased, is_het, phase_set.

:returns: Result table with diagnostics and summary in attrs['run_info'].
:raises ValueError: Required columns are absent or records are empty or invalid.

### `run_info(data: pd.DataFrame, *, keep: bool=True) -> dict`

Return the analysis diagnostics and summary.

:param data: Result returned by analyze.
:param keep: Keep diagnostics by default; the CLI passes False.
:returns: Independent diagnostics dictionary.
:raises ValueError: analyze has not populated diagnostics.

### `distribution_figure(data: pd.DataFrame)`

Plot pos values without writing files.

:param data: Result table containing pos.
:returns: Matplotlib Figure.
:raises ValueError: The value column is absent or the table is empty.

<!-- api:end -->

## Methods and parameters

`analyze` returns a new DataFrame and leaves the input unchanged.
`run_info(result)` returns the summary and method diagnostics.
The CLI passes `keep=False` so diagnostics do not enter output tables.
All calculations are deterministic; synthetic CLI demos retain seed 42.

## Gotchas

- `read_records` reads only the first sample. The legacy heterozygous classification recognizes 0/1, 1/0, 0|1 and 1|0; other allele combinations are not included.
- `run_info()["summary"]["n_phase_blocks"]` excludes singleton blocks. Missing PS uses the position as a singleton phase set.
- `analyze` summarizes existing phasing; it does not phase variants or estimate switch-error rates.

## Inputs and outputs

Input files:

- File types: `.vcf`
- Accepts artifact `genomics.filtered_variants` (`vcf`)

CLI output files:

- `tables/phase_blocks.csv`
- `tables/phased_variants.csv`
- `report.md`
- `result.json`
- Produces artifact `genomics.phased_variants` as `tables/phased_variants.csv` (`csv`)

The library writes no files. Steps use `write_output`; the CLI owns the
listed artifacts. Public figure functions return matplotlib Figures and
do not add new CLI outputs.

## CLI

```bash
python skills/genomics/genomics-phasing/genomics_phasing.py --input input_file --output results/
python skills/genomics/genomics-phasing/genomics_phasing.py --demo --output /tmp/genomics_phasing_demo
```

## See also

- `references/parameters.md`
- `references/methodology.md`
- `references/output_contract.md`

## Dependencies

`numpy`, `pandas`, `matplotlib`
