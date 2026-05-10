<!-- AUTO-GENERATED from parameters.yaml — do not edit by hand. -->
<!-- Regenerate: python scripts/generate_parameters_md.py <skill_dir> -->


# Parameters

## Allowed extra CLI flags

- `--cell-type-key`
- `--method`
- `--species`
- `--liana-expr-prop`
- `--liana-min-cells`
- `--liana-n-perms`
- `--liana-resource`
- `--cellphonedb-iterations`
- `--cellphonedb-threshold`
- `--fastccc-single-unit-summary`
- `--fastccc-complex-aggregation`
- `--fastccc-lr-combination`
- `--fastccc-min-percentile`
- `--cellchat-prob-type`
- `--cellchat-min-cells`

## Per-method parameter hints

### `cellchat_r`

**Tuning priority:** cellchat_prob_type → cellchat_min_cells

**Core parameters:**

| name | default |
|---|---|
| `cell_type_key` | `leiden` |
| `species` | `human` |
| `cellchat_prob_type` | `triMean` |
| `cellchat_min_cells` | `10` |

**Requires:**
- `X_log_normalized`
- `obs.cell_type`
- `Rscript`

**Tips:**
- --cellchat-prob-type: forwarded to `computeCommunProb(type=...)`; `triMean` is the current OmicsClaw default.
- --cellchat-min-cells: forwarded to `filterCommunication(min.cells=...)`.

### `cellphonedb`

**Tuning priority:** cellphonedb_threshold → cellphonedb_iterations

**Core parameters:**

| name | default |
|---|---|
| `cell_type_key` | `leiden` |
| `species` | `human` |
| `cellphonedb_threshold` | `0.1` |
| `cellphonedb_iterations` | `1000` |

**Requires:**
- `X_log_normalized`
- `obs.cell_type`
- `human_species`
- `cellphonedb_database`

**Tips:**
- --cellphonedb-threshold: minimum fraction of cells expressing each ligand or receptor.
- --cellphonedb-iterations: label-shuffling iterations in the official statistical method.

### `fastccc`

**Tuning priority:** fastccc_single_unit_summary → fastccc_complex_aggregation → fastccc_lr_combination → fastccc_min_percentile

**Core parameters:**

| name | default |
|---|---|
| `cell_type_key` | `leiden` |
| `species` | `human` |
| `fastccc_single_unit_summary` | `Mean` |
| `fastccc_complex_aggregation` | `Minimum` |
| `fastccc_lr_combination` | `Arithmetic` |
| `fastccc_min_percentile` | `0.1` |

**Requires:**
- `X_log_normalized`
- `obs.cell_type`
- `human_species`
- `cellphonedb_database`

**Tips:**
- --fastccc-single-unit-summary: public FastCCC summary statistic, for example `Mean`, `Median`, `Q3`, or `Quantile_0.9`.
- --fastccc-complex-aggregation: how multi-subunit complexes are summarized (`Minimum` or `Average`).
- --fastccc-lr-combination: how ligand and receptor activity are combined (`Arithmetic` or `Geometric`).
- --fastccc-min-percentile: minimum expressing-cell fraction used in FastCCC filtering.

### `liana`

**Tuning priority:** liana_resource → liana_expr_prop → liana_min_cells → liana_n_perms

**Core parameters:**

| name | default |
|---|---|
| `cell_type_key` | `leiden` |
| `species` | `human` |
| `liana_resource` | `auto` |
| `liana_expr_prop` | `0.1` |
| `liana_min_cells` | `5` |
| `liana_n_perms` | `1000` |

**Requires:**
- `X_log_normalized`
- `obs.cell_type`

**Tips:**
- --liana-resource: `auto` maps to `consensus` for human and `mouseconsensus` for mouse.
- --liana-expr-prop: minimum expressing-cell fraction forwarded to `liana.mt.rank_aggregate`.
- --liana-min-cells: minimum cells per cell type before LIANA tests interactions.
- --liana-n-perms: permutation depth used in LIANA consensus ranking.
