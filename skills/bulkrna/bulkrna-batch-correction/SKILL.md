---
name: bulkrna-batch-correction
description: Load when correcting batch effects in bulk expression using R sva ComBat or the legacy Python parametric approximation. Skip single-batch inputs; use sc-batch-integration for single-cell data or spatial-integrate for spatial slices.
trigger: batch correction, ComBat, batch effect, harmonize, multi-cohort, batch removal
tags:
- bulkrna
- batch-correction
- ComBat
- harmonization
- batch-effect
---

# bulkrna-batch-correction

## When to use

Load when correcting batch effects in bulk expression using R sva ComBat or the legacy Python parametric approximation. Skip single-batch inputs; use sc-batch-integration for single-cell data or spatial-integrate for spatial slices.

## Use from a step

```python
from skills._sdk.notebook import load_skill, write_output
library = load_skill("bulkrna-batch-correction")
result = library.correct(data, batches=batches, backend="python")
write_output(result, "tables/result.csv")
write_output(library.pca_figure(result, batches=batches), "figures/result.png")
```

Read expression and metadata with `read_input` before calling the library.
`examples/example_step.py` constructs a small synthetic dataset and checks
its results through the step runner and fresh-kernel replay.

## API

<!-- api:begin generated from _api.py; regenerate with run.py api <skill dir> --write -->

### `correct(data: pd.DataFrame, *, batches: pd.DataFrame, mode: str='parametric', backend: str='auto') -> pd.DataFrame`

Return corrected expression, leaving the input unchanged.

:param data: Finite nonnegative expression, features by samples; correction uses this scale directly.
:param batches: Metadata with sample and batch columns, and optional biological condition.
:param mode: CLI default parametric, or non-parametric (requires R sva).
:param backend: auto prefers R as the CLI did; r requires R, python uses the legacy parametric approximation.
:returns: Corrected DataFrame with run_info diagnostics; values can be negative.
:raises ValueError: Data, metadata, mode or backend is invalid.
:raises ImportError: An explicitly requested R backend is unavailable.
:raises RuntimeError: R fails and the requested mode/design has no Python fallback.

### `run_info(data: pd.DataFrame, *, keep: bool=True) -> dict`

Return backend diagnostics and before/after batch metrics.

:param data: Result of correct.
:param keep: Keep diagnostics by default; the CLI passes False.
:returns: Diagnostics dictionary.
:raises ValueError: No correction diagnostics are attached.

### `pca_figure(data: pd.DataFrame, *, batches: pd.DataFrame)`

Plot PCA after signed log2(1+abs(x)), accepting negative corrections.

:param data: Original or corrected feature-by-sample expression.
:param batches: Metadata containing sample and batch.
:returns: Matplotlib Figure.
:raises ValueError: Samples lack batch metadata.

<!-- api:end -->

## Methods and parameters

The function library returns DataFrames and Figures. The CLI loads the
same library and owns reports and file writes. R runs in a temporary
directory using Matrix Market, feature/sample identifiers and metadata.
No R intermediate is a permanent CLI output.

## Gotchas

- `correct(backend="auto")` prefers R sva and warns/records any Python fallback. `backend="r"` requires R. The Python method is the legacy parametric approximation, not numerical equivalence to sva.
- `correct` requires at least two batches and two samples per batch. Missing labels and single-batch inputs raise before any backend runs.
- `correct` applies ComBat directly to the supplied scale, not to an automatic log transform. Outputs may be negative and are not integer counts for DESeq2.
- `correct(mode="non-parametric")` and condition covariates require R; Python cannot silently substitute a different design or mode.
- `run_info()["summary"]` contains before/after PCA silhouette metrics using signed log2(1+abs(x)), so negative corrections remain finite. Inspect condition-by-batch balance before removing effects.

## Inputs and outputs

Expression CSV with feature identifiers in the first column; metadata CSV with sample and batch, plus optional condition.

CLI outputs:

- `tables/corrected_expression.csv`
- `tables/batch_metrics.csv`
- `figures/pca_before_correction.png`
- `figures/pca_after_correction.png`
- `figures/batch_assessment.png`
- `report.md`, `result.json`
- `reproducibility/commands.sh`

## CLI

```bash
python skills/bulkrna/bulkrna-batch-correction/bulkrna_batch_correction.py --demo --output /tmp/bulkrna_batch_correction_demo
```

Run the script with `--help` for real-input arguments.

## See also

- `references/parameters.md`
- `references/methodology.md`
- `references/output_contract.md`

## Dependencies

`matplotlib`, `numpy`, `pandas`, `scipy`, `sva`, `Matrix`
