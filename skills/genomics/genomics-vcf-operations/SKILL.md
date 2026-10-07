---
name: genomics-vcf-operations
description: Load when summarising / filtering a VCF — variant classification (SNP / MNP / INS / DEL /
  COMPLEX), Ti/Tv ratio, QUAL / DP threshold filtering, INFO-field parsing. Skip when calling variants from BAM (run an external caller first); adding functional annotations (use genomics-variant-annotation).
trigger: VCF, bcftools, variant filter, merge VCF
tags:
- genomics
- vcf
- bcftools
- filter
- ti-tv
- snv
- indel
---

# genomics-vcf-operations

## When to use

Load this skill for the file-based analysis named in the description.
The function library and CLI share the same calculations; no external
aligner, assembler, caller or annotation service is started.

## Use from a step

```python
from skills._sdk.notebook import load_skill, read_input, write_output
library = load_skill("genomics-vcf-operations")
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

### `analyze(data: pd.DataFrame, *, min_qual: float=0.0, min_dp: int=0) -> pd.DataFrame`

Compute vcf-operations summaries and return a new table, leaving data unchanged.

:param data: Records containing chrom, pos, ref, alt, qual, filter, dp, type.
:param min_qual: CLI default 0 keeps all QUAL values; raise to filter.
:param min_dp: CLI default 0 keeps all INFO/DP values; FORMAT/DP is ignored.
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

- `analyze` filters INFO/DP, not per-sample FORMAT/DP. Missing INFO/DP is treated as zero; each ALT becomes one row.
- `read_records` preserves VCF header lines in attrs["vcf_headers"]. The legacy CLI filtered.vcf retains DP only and replaces sample genotypes with missing values; do not use it for genotype-preserving filtering.
- `analyze` raises ValueError when no records pass filters, instead of the old CLI failing later with a missing summary key.

## Inputs and outputs

Input files:

- File types: `.vcf`
- VCF structure: `##fileformat`; columns: `#CHROM`, `POS`, `ID`, `REF`, `ALT`, `QUAL`, `FILTER`, `INFO`

CLI output files:

- `tables/variants.csv`
- `filtered.vcf`
- `report.md`
- `result.json`
- Produces artifact `genomics.filtered_variants` as `filtered.vcf` (`vcf`)

The library writes no files. Steps use `write_output`; the CLI owns the
listed artifacts. Public figure functions return matplotlib Figures and
do not add new CLI outputs.

## CLI

```bash
python skills/genomics/genomics-vcf-operations/genomics_vcf_operations.py --input input_file --output results/
python skills/genomics/genomics-vcf-operations/genomics_vcf_operations.py --demo --output /tmp/genomics_vcf_operations_demo
```

## See also

- `references/parameters.md`
- `references/methodology.md`
- `references/output_contract.md`

## Dependencies

`numpy`, `pandas`, `matplotlib`
