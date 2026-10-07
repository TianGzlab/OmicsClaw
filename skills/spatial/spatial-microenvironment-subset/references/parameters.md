<!-- Hand-written. `skill.yaml` and its generators were deleted with the old skill system. -->


# Parameters

## Python library

Call subset(adata, center_values=[...], radius_native=...); center_key defaults to a recognized label column. Pass labels as lists rather than comma-separated CLI strings. radius_native and radius_microns are exclusive. include_centers=False corresponds to --exclude-centers. The input remains unchanged; the result contains role and nearest-center distance columns.

## Allowed extra CLI flags

- `--center-key`
- `--center-values`
- `--data-type`
- `--exclude-centers`
- `--microns-per-coordinate-unit`
- `--radius-microns`
- `--radius-native`
- `--target-key`
- `--target-values`

## Per-method parameter hints

_No method-specific tuning hints._
