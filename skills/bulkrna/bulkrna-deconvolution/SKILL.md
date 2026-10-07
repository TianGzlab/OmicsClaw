---
name: bulkrna-deconvolution
description: Load when estimating cell-type proportions in bulk RNA-seq samples from a single-cell or
  signature-matrix reference. Skip when the data is already single-cell (no deconvolution needed); spatial
  deconvolution (use spatial-deconv).
trigger: bulk deconvolution, cell type proportion, NNLS, CIBERSORTx, bulk deconv, cell fraction
tags:
- bulkrna
- deconvolution
- NNLS
- cell-type-proportion
---

# bulkrna-deconvolution

## When to use

Estimate bulk cell-type proportions with an explicit signature matrix. See the description for adjacent skills.

## Use from a step

```python
from skills._sdk.notebook import load_skill, read_input, write_output
library = load_skill("bulkrna-deconvolution")
# Supply DataFrames read with read_input(..., reader=...) for your CSV layout.
result = library.deconvolve(counts, signature=signature)
write_output(result, "tables/result.csv")
```

The synthetic worked step is in `examples/example_step.py`.

## API

<!-- api:begin generated from _api.py; regenerate with run.py api <skill dir> --write -->

### `deconvolve(counts, *, signature)`

Estimate sample proportions without changing either input.

:param counts: Nonnegative gene-by-sample expression DataFrame.
:param signature: Required gene-by-cell-type reference, matching the CLI --reference.
:returns: Sample-by-cell-type DataFrame; diagnostics contain residuals and shared genes.
:raises ValueError: Matrices have invalid values, duplicate labels or no shared genes.

### `run_info(result, *, keep=True)`

Read reference overlap and reconstruction diagnostics.

:param result: DataFrame returned by deconvolve.
:param keep: Default True; False removes diagnostics from attrs.
:returns: Diagnostic dictionary, empty after removal.

### `proportions_figure(result)`

Plot estimated cell-type proportions per sample.

:param result: Sample-by-cell-type DataFrame from deconvolve.
:returns: A matplotlib Figure, without writing files.
:raises ValueError: The table cannot be plotted as numeric proportions.

<!-- api:end -->

## Methods and parameters

See [parameters](references/parameters.md) and [methodology](references/methodology.md).

## Gotchas

- `deconvolve` requires shared gene identifiers and nonnegative matrices.
- `run_info()['residuals']` measures fit to the supplied reference, not confidence intervals.
- NNLS is the only backend; `deconvolve` does not call CIBERSORTx or MuSiC.

## Inputs and outputs

The library returns objects without file writes. CLI inventory:

**Inputs**

- File types: `.csv`

**Outputs**

- `tables/dominant_types.csv`
- `tables/proportions.csv`
- `figures/mean_proportions_pie.png`
- `figures/proportions_heatmap.png`
- `figures/proportions_stacked.png`
- `report.md`
- `result.json`

## CLI

```bash
python skills/bulkrna/bulkrna-deconvolution/bulkrna_deconvolution.py --demo --output /tmp/bulkrna-deconvolution
```

## See also

- [Output contract](references/output_contract.md)

## Dependencies

`matplotlib`, `numpy`, `pandas`, `scipy`
