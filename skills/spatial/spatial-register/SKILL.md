---
name: spatial-register
description: Load when aligning multiple spatial slices into a common coordinate frame with PASTE or STalign. Skip single-slice data; for expression-space batch correction use spatial-integrate.
trigger: spatial registration, slice alignment, PASTE, STalign
tags:
- spatial
- registration
- alignment
---

# spatial-register

## Use from a step

```python
from skills._sdk.notebook import load_skill, read_input, write_output
library = load_skill("spatial-register")
adata = library.register(read_input("data/slices.h5ad"), slice_key="slice")
write_output(adata, "intermediate/registered.h5ad")
```

## When to use

Align slice coordinates while preserving the original spatial coordinates.
PASTE uses expression and spatial distances; STalign supports two slices.
For expression-space correction use spatial-integrate instead.

## Inputs & Outputs

Input: AnnData with expression, spatial coordinates and a slice-label column.
The default reference is the first sorted label, not the largest slice.
Functions return the same AnnData, shift tables and figures without writing files.

CLI writes `processed.h5ad`, `report.md`, `result.json`, registration tables
and the before/after gallery. See [references/output_contract.md](references/output_contract.md)
for the complete file inventory. Registered coordinates are `obsm["spatial_aligned"]`;
`spatial` and `X_spatial`, if present, remain unchanged.

## Key CLI

```bash
python skills/spatial/spatial-register/spatial_register.py --input slices.h5ad --output results/registration --slice-key slice --method paste
python skills/spatial/spatial-register/spatial_register.py --demo --output /tmp/spatial_register
```

`examples/example_step.py` aligns unequal-size simulated slices through the
step runner. [references/parameters.md](references/parameters.md) lists backend flags.

## Gotchas

- `spatial_aligned` is a separate coordinate basis; downstream skills do not
  automatically switch from `spatial`.
- PASTE transports source spots with the transpose of its reference-by-source
  coupling. The old `_lib/register.py:run_paste` direction was incorrect;
  unequal slice sizes now work, and solver failures raise instead of reporting success.
- The historical `disparities` summary is sum of squared transport weights,
  not the optimal-transport objective or a calibrated fit statistic.
- The tested PASTE 1.4.0 combination needs POT 0.9.4. POT 0.9.5 and 0.9.6 changed
  the line-search call and fail inside PASTE. Use an isolated compatible environment.
- STalign is optional and was not executed in this migration environment.
  It has no exposed seed control here; do not claim deterministic GPU results.
- `tables/registration_metrics.csv` has NaN disparity where the backend
  does not report it. Inspect shifts without treating smaller displacement as better alignment.

## API

<!-- api:begin generated from _api.py; regenerate with run.py api <skill dir> --write -->

### `register(adata, *, method: str='paste', slice_key: str | None=None, reference_slice: str | None=None, **parameters)`

Add aligned coordinates in place without overwriting the input coordinates.

:param adata: AnnData with expression, spatial coordinates and slice labels.
:param method: paste (default) for transport or stalign for two-slice LDDMM.
:param slice_key: Observation column; None detects slice, sample, section or batch.
:param reference_slice: Target label; None uses the first sorted label.
:param parameters: PASTE alpha=0.1, dissimilarity='kl', use_gpu=False;
    STalign image_size=(400,400), niter=2000, a=500, use_expression=False.
    PASTE is deterministic on CPU; STalign has no seed control and may vary.
:returns: The same AnnData with spatial_aligned and JSON run diagnostics.
:raises ValueError: Invalid labels, coordinates, method or method parameters.
:raises ImportError: Missing backend; use install_skill_deps for paste-bio/POT
    or STalign/torch as appropriate.
:raises RuntimeError: A slice cannot be aligned; partial success is not returned.

### `run_info(adata, *, keep: bool=True) -> dict`

Read the last registration summary.

:param adata: Registered AnnData.
:param keep: True retains diagnostics; False removes them for CLI serialization.
:returns: Summary with reference, slices and effective parameters, or an empty dict.

### `shift_table(adata) -> pd.DataFrame`

Measure Euclidean displacement from original to registered coordinates.

:param adata: AnnData with spatial_aligned and original spatial coordinates.
:returns: observation and shift_distance columns, in observation order.
:raises KeyError: Aligned coordinates are absent.
:raises ValueError: Original coordinates are absent.

### `registration_figure(adata, *, slice_key: str | None=None)`

Plot original and registered slice coordinates side by side.

:param adata: Registered AnnData.
:param slice_key: Slice label column; None detects the column from the data.
:returns: A matplotlib Figure; the caller saves and closes it.
:raises KeyError: Aligned coordinates or labels are absent.

<!-- api:end -->

## Dependencies

`anndata`, `matplotlib`, `numpy`, `pandas`, `paste-bio`, `POT`, `scanpy`, `scikit-learn`, `scipy`, `seaborn`, `STalign`, `torch`

The CLI dependency list covers both methods; install only the chosen backend.
