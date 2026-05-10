<!-- AUTO-GENERATED from parameters.yaml — do not edit by hand. -->
<!-- Regenerate: python scripts/generate_parameters_md.py <skill_dir> -->


# Parameters

## Allowed extra CLI flags

- `--contamination`
- `--expected-cells`
- `--filtered-matrix-dir`
- `--method`
- `--raw-h5`
- `--raw-matrix-dir`
- `--r-enhanced`

## Per-method parameter hints

### `cellbender`

**Tuning priority:** raw_h5 -> expected_cells

**Core parameters:**

| name | default |
|---|---|
| `raw_h5` | `—` |
| `expected_cells` | `input_n_obs_or_required_without_input` |

**Requires:**
- `cellbender`
- `10x_raw_h5`

**Tips:**
- --raw-h5: Required for the CellBender path.
- --expected-cells: Main CellBender size prior; strongly recommended and required when no separate --input is provided.

### `simple`

**Tuning priority:** contamination

**Core parameters:**

| name | default |
|---|---|
| `contamination` | `0.05` |

**Requires:**
- `count_like_expression_in_layers_counts_or_raw_or_X`
- `scanpy`

**Tips:**
- --method simple: Python fallback that subtracts a global ambient profile from the best available raw-count-like matrix.
- --contamination: Wrapper-level contamination fraction used directly in the subtraction formula after scaling by each barcode's library size.

### `soupx`

**Tuning priority:** raw_matrix_dir -> filtered_matrix_dir

**Core parameters:**

| name | default |
|---|---|
| `raw_matrix_dir` | `—` |
| `filtered_matrix_dir` | `—` |

**Requires:**
- `SoupX_ready_R_environment`
- `10x_raw_and_filtered_matrix_dirs`

**Tips:**
- --method soupx: Requires both raw and filtered 10x matrix directories.
- If the required SoupX inputs are missing, OmicsClaw falls back to `simple`.
