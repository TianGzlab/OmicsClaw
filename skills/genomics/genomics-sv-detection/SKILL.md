---
name: genomics-sv-detection
description: Load when summarising structural variants from an SV VCF (DEL / DUP / INV / TRA) — INFO/SVTYPE-based
  classification, size classification, per-type counts. Skip when working with small SNVs / indels (use genomics-variant-calling);
  calling SVs from BAM (run Manta / Delly / Sniffles first).
trigger: structural variant, SV, Manta, Delly, Lumpy, Sniffles
tags:
- genomics
- structural-variants
- sv
- manta
- delly
- sniffles
- bnd
---

# genomics-sv-detection

## When to use

Load this skill for the file-based analysis named in the description.
The function library and CLI share the same calculations; no external
aligner, assembler, caller or annotation service is started.

## Use from a step

```python
from skills._sdk.notebook import load_skill, read_input, write_output
library = load_skill("genomics-sv-detection")
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

Compute sv-detection summaries and return a new table, leaving data unchanged.

:param data: Records containing chrom, sv_type, sv_len, filter, size_class, genotype.

:returns: Result table with diagnostics and summary in attrs['run_info'].
:raises ValueError: Required columns are absent or records are empty or invalid.

### `run_info(data: pd.DataFrame, *, keep: bool=True) -> dict`

Return the analysis diagnostics and summary.

:param data: Result returned by analyze.
:param keep: Keep diagnostics by default; the CLI passes False.
:returns: Independent diagnostics dictionary.
:raises ValueError: analyze has not populated diagnostics.

### `distribution_figure(data: pd.DataFrame)`

Plot sv_len values without writing files.

:param data: Result table containing sv_len.
:returns: Matplotlib Figure.
:raises ValueError: The value column is absent or the table is empty.

<!-- api:end -->

## Methods and parameters

`analyze` returns a new DataFrame and leaves the input unchanged.
`run_info(result)` returns the summary and method diagnostics.
The CLI passes `keep=False` so diagnostics do not enter output tables.
All calculations are deterministic; synthetic CLI demos retain seed 42.

## Gotchas

- `read_records` reads INFO/SVTYPE; breakend ALT notation without that field stays UNKNOWN. There is no mate-pair resolution or SV calling.
- `run_info()["summary"]` uses absolute SVLEN and the legacy small (<1000), medium (<100000), and large size classes. Only the first sample genotype is read.

## Inputs and outputs

Input files:

- File types: `.vcf`

CLI output files:

- `tables/structural_variants.csv`
- `report.md`
- `result.json`

The library writes no files. Steps use `write_output`; the CLI owns the
listed artifacts. Public figure functions return matplotlib Figures and
do not add new CLI outputs.

## CLI

```bash
python skills/genomics/genomics-sv-detection/sv_detection.py --input input_file --output results/
python skills/genomics/genomics-sv-detection/sv_detection.py --demo --output /tmp/genomics_sv_detection_demo
```

## See also

- `references/parameters.md`
- `references/methodology.md`
- `references/output_contract.md`

## Dependencies

`numpy`, `pandas`, `matplotlib`
