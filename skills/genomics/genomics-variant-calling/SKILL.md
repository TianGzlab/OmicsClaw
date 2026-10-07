---
name: genomics-variant-calling
description: Load when summarising small variants (SNVs / indels) from a VCF or computing demo-pattern
  variant statistics (Ti/Tv ratio, per-chromosome distribution, SNP / indel split). Skip when filtering
  / merging VCFs (use genomics-vcf-operations); calling structural variants (use genomics-sv-detection);
  adding functional annotations (use genomics-variant-annotation).
trigger: variant calling, SNV, indel, GATK, DeepVariant, FreeBayes, Mutect2, VQSR
tags:
- genomics
- variant-calling
- snv
- indel
- vcf
- ti-tv
---

# genomics-variant-calling

## When to use

Load this skill for the file-based analysis named in the description.
The function library and CLI share the same calculations; no external
aligner, assembler, caller or annotation service is started.

## Use from a step

```python
from skills._sdk.notebook import load_skill, read_input, write_output
library = load_skill("genomics-variant-calling")
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

:param path: Input file in the format documented under Inputs and outputs.

:returns: Parsed records as a DataFrame.
:raises ValueError: Input values or file structure cannot be parsed.

### `analyze(data: pd.DataFrame) -> pd.DataFrame`

Compute variant-calling summaries and return a new table, leaving data unchanged.

:param data: Records containing chrom, pos, ref, alt, qual, filter, type.

:returns: Result table with diagnostics and summary in attrs['run_info'].
:raises ValueError: Required columns are absent or records are empty or invalid.

### `run_info(data: pd.DataFrame, *, keep: bool=True) -> dict`

Return analysis diagnostics and summary.

:param data: Result returned by analyze.
:param keep: Keep diagnostics by default; the CLI passes False.
:returns: Independent diagnostics dictionary.
:raises ValueError: analyze has not populated diagnostics.

### `distribution_figure(data: pd.DataFrame)`

Plot qual values without writing files.

:param data: Result table containing qual.
:returns: Matplotlib Figure.
:raises ValueError: The value column is absent or table is empty.

<!-- api:end -->

## Methods and parameters

`analyze` returns a new DataFrame and leaves the input unchanged.
`run_info(result)` returns the summary and method diagnostics.
The CLI passes `keep=False` so diagnostics do not enter output tables.
All calculations are deterministic; synthetic CLI demos retain seed 42.

## Gotchas

- `read_records` splits each comma-separated ALT into a separate row. Plain text VCF is supported; decompress compressed files first.
- `analyze` summarizes an existing callset; it does not run a variant caller.
- `run_info()["summary"]["ti_tv_ratio"]` is infinite when no transversions occur.

## Inputs and outputs

Input files:

- File types: `.vcf`

CLI output files:

- `tables/variants.csv`
- `tables/variants_per_chrom.csv`
- `report.md`
- `result.json`
- Produces artifact `genomics.variant_table` as `tables/variants.csv` (`csv`)

The library writes no files. Steps use `write_output`; the CLI owns the
listed artifacts. Public figure functions return matplotlib Figures and
do not add new CLI outputs.

## CLI

```bash
python skills/genomics/genomics-variant-calling/genomics_variant_calling.py --input input_file --output results/
python skills/genomics/genomics-variant-calling/genomics_variant_calling.py --demo --output /tmp/genomics_variant_calling_demo
```

## See also

- `references/parameters.md`
- `references/methodology.md`
- `references/output_contract.md`

## Dependencies

`numpy`, `pandas`, `matplotlib`
