<!-- AUTO-GENERATED from parameters.yaml — do not edit by hand. -->
<!-- Regenerate: python scripts/generate_parameters_md.py <skill_dir> -->


# Parameters

## Allowed extra CLI flags

- `--doublet-score-threshold`
- `--max-counts`
- `--max-genes`
- `--max-mt-percent`
- `--min-cells`
- `--min-counts`
- `--min-genes`
- `--no-remove-doublets`
- `--r-enhanced`
- `--tissue`

## Per-method parameter hints

### `threshold_filtering`

**Tuning priority:** tissue -> min_genes/max_mt_percent -> min_cells -> count caps

**Core parameters:**

| name | default |
|---|---|
| `tissue` | `—` |
| `min_genes` | `200` |
| `max_genes` | `—` |
| `min_counts` | `—` |
| `max_counts` | `—` |
| `max_mt_percent` | `20.0` |
| `min_cells` | `3` |

**Requires:**
- `qc_metrics_in_obs_or_count_like_matrix_in_X`
- `scanpy`

**Tips:**
- --tissue: Wrapper-level preset that overrides the default QC thresholds with OmicsClaw tissue heuristics.
- --min-genes / --max-mt-percent: Main cell-retention controls.
- --min-cells: Gene-level retention threshold applied after cell filtering.
