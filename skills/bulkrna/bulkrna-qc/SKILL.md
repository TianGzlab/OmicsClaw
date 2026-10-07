---
name: bulkrna-qc
description: Load when checking a bulk RNA-seq count matrix for library-size outliers, gene detection
  rates, and sample-sample correlation before DE. Skip when data is raw FASTQ (use bulkrna-read-qc); aligner
  logs (use bulkrna-read-alignment); single-cell counts (use sc-qc).
trigger: bulk QC, library size, count matrix, sample quality, gene detection, RNA-seq quality, count QC
tags:
- bulkrna
- QC
- count-matrix
- library-size
- gene-detection
- sample-correlation
- CPM
---

# bulkrna-qc

## When to use

Assess raw integer count matrices before bulk differential expression. See the description for adjacent skills.

## Use from a step

```python
from skills._sdk.notebook import load_skill, read_input, write_output
library = load_skill("bulkrna-qc")
# Supply DataFrames read with read_input(..., reader=...) for your CSV layout.
result = library.assess(counts)
write_output(result, "tables/result.csv")
```

The synthetic worked step is in `examples/example_step.py`.

## API

<!-- api:begin generated from _api.py; regenerate with run.py api <skill dir> --write -->

### `assess(counts)`

Measure library size and detection on raw counts without changing input.

:param counts: Gene-by-sample nonnegative integer DataFrame with unique labels.
:returns: Sample-indexed DataFrame with QC metrics and diagnostic attrs.
:raises ValueError: The matrix is invalid or a sample has no counts.

### `run_info(result, *, keep=True)`

Read QC diagnostics and auxiliary matrices.

:param result: DataFrame returned by assess.
:param keep: Default True; False removes diagnostics from result.attrs.
:returns: A diagnostic dictionary, empty when no record remains.

### `normalized_counts(result)`

Return CPM for visualization, not differential-expression input.

:param result: DataFrame returned by assess with its diagnostics retained.
:returns: New gene-by-sample CPM DataFrame.
:raises KeyError: QC diagnostics have been removed.

### `library_figure(result)`

Plot total counts per sample without saving files.

:param result: QC table returned by assess.
:returns: A matplotlib Figure; the caller saves and closes it.
:raises KeyError: total_counts is missing.

<!-- api:end -->

## Methods and parameters

See [parameters](references/parameters.md) and [methodology](references/methodology.md).

## Gotchas

- `assess` rejects empty libraries instead of producing undefined CPM.
- `normalized_counts` returns CPM for figures, not DE input.
- `run_info()['outlier_samples']` is correlation-based; check biological groups before removing samples.

## Inputs and outputs

The library returns objects without file writes. CLI inventory:

**Inputs**

- File types: `.csv`

**Outputs**

- `tables/cpm_normalized.csv`
- `tables/sample_stats.csv`
- `figures/expression_density.png`
- `figures/gene_detection.png`
- `figures/library_sizes.png`
- `figures/sample_correlation.png`
- `report.md`
- `result.json`

## CLI

```bash
python skills/bulkrna/bulkrna-qc/bulkrna_qc.py --demo --output /tmp/bulkrna-qc
```

## See also

- [Output contract](references/output_contract.md)

## Dependencies

`matplotlib`, `numpy`, `pandas`, `scipy`
