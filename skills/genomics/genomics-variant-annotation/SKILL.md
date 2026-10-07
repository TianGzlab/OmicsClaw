---
name: genomics-variant-annotation
description: Load when summarising functional impact of an annotated variant CSV — per-IMPACT counts (HIGH
  / MODERATE / LOW / MODIFIER), top consequences, gene-affected count. Skip when input is a raw VCF (convert
  with `bcftools +split-vep` first); calling raw variants (use genomics-variant-calling); filtering VCFs
  (use genomics-vcf-operations).
trigger: variant annotation, VEP, snpEff, ANNOVAR, functional effect
tags:
- genomics
- annotation
- vep
- snpeff
- annovar
- consequence
- impact
---

# genomics-variant-annotation

## When to use

Load this skill for the file-based analysis named in the description.
The function library and CLI share the same calculations; no external
aligner, assembler, caller or annotation service is started.

## Use from a step

```python
from skills._sdk.notebook import load_skill, read_input, write_output
library = load_skill("genomics-variant-annotation")
data = read_input("input.csv", reader=library.read_records)
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

Compute variant-annotation summaries and return a new table, leaving data unchanged.

:param data: Records containing impact, consequence, gene, cadd_phred.

:returns: Result table with diagnostics and summary in attrs['run_info'].
:raises ValueError: Required columns are absent or records are empty or invalid.

### `run_info(data: pd.DataFrame, *, keep: bool=True) -> dict`

Return the analysis diagnostics and summary.

:param data: Result returned by analyze.
:param keep: Keep diagnostics by default; the CLI passes False.
:returns: Independent diagnostics dictionary.
:raises ValueError: analyze has not populated diagnostics.

### `distribution_figure(data: pd.DataFrame)`

Plot cadd_phred values without writing files.

:param data: Result table containing cadd_phred.
:returns: Matplotlib Figure.
:raises ValueError: The value column is absent or the table is empty.

<!-- api:end -->

## Methods and parameters

`analyze` returns a new DataFrame and leaves the input unchanged.
`run_info(result)` returns the summary and method diagnostics.
The CLI passes `keep=False` so diagnostics do not enter output tables.
All calculations are deterministic; synthetic CLI demos retain seed 42.

## Gotchas

- `analyze` summarizes annotations already supplied by the caller; it does not run VEP, SIFT, PolyPhen or CADD.
- `analyze` requires lowercase impact, consequence, gene and cadd_phred columns. Missense rows also require sift_prediction and polyphen_prediction.
- `tables/annotated_variants.csv` from --demo contains simulated scores, not predictions for real variants.

## Inputs and outputs

Input files:

- File types: `.csv`
- Accepts artifact `genomics.variant_table` (`csv`)

CLI output files:

- `tables/annotated_variants.csv`
- `tables/impact_distribution.csv`
- `report.md`
- `result.json`
- Produces artifact `genomics.annotated_variants` as `tables/annotated_variants.csv` (`csv`)

The library writes no files. Steps use `write_output`; the CLI owns the
listed artifacts. Public figure functions return matplotlib Figures and
do not add new CLI outputs.

## CLI

```bash
python skills/genomics/genomics-variant-annotation/variant_annotation.py --input input_file --output results/
python skills/genomics/genomics-variant-annotation/variant_annotation.py --demo --output /tmp/genomics_variant_annotation_demo
```

## See also

- `references/parameters.md`
- `references/methodology.md`
- `references/output_contract.md`

## Dependencies

`numpy`, `pandas`, `matplotlib`
