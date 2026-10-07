# Output contract

Functions return AnnData, DataFrame or Figure without writing files.
The CLI writes the following files on successful registration.

## Data and tables

- `processed.h5ad`, `report.md`, `result.json`.
- `tables/registration_summary.csv`: method, reference, slice count and legacy
  transport-weight concentration summary.
- `tables/registration_metrics.csv`: spot counts and shift statistics by slice;
  disparity is NaN where unavailable.
- `figure_data/registration_points.csv`, `figure_data/registration_shift_by_slice.csv`
  and `figure_data/registration_run_summary.csv`.
- `figure_data/registration_disparities.csv` only when disparities exist.
- `figures/manifest.json`, `figure_data/manifest.json`.
- `reproducibility/commands.sh`, `reproducibility/environment.txt`,
  `reproducibility/r_visualization.sh`.

## Figures

- `figures/slices_before.png` and `figures/slices_after.png`: coordinates and slice labels.
- `figures/registration_shift_map.png`: per-spot displacement.
- `figures/registration_shift_by_slice.png`: nonempty slice shift summary.
- `figures/registration_shift_distribution.png`: available displacement values.
- `figures/registration_disparities.png`: only with nonempty disparity values.

`obsm["spatial_aligned"]` holds registered coordinates. Original `spatial`
and `X_spatial` coordinates are unchanged. The first sorted slice is the
default reference. PASTE uses the reference-by-source coupling transposed for
source barycenters; unequal slice sizes are supported. Solver failures raise,
rather than saving unchanged coordinates as a successful registration.

The historical disparity field is the sum of squared coupling weights, not
the PASTE objective or a calibrated fit-quality statistic.
