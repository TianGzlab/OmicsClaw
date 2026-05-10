<!-- AUTO-GENERATED from parameters.yaml — do not edit by hand. -->
<!-- Regenerate: python scripts/generate_parameters_md.py <skill_dir> -->


# Parameters

## Allowed extra CLI flags

- `--cell-type-key`
- `--cellchat-min-cells`
- `--cellchat-prob-type`
- `--cellphonedb-counts-data`
- `--cellphonedb-iterations`
- `--cellphonedb-pvalue`
- `--cellphonedb-threshold`
- `--cellphonedb-threads`
- `--condition-key`
- `--condition-oi`
- `--condition-ref`
- `--method`
- `--nichenet-lfc-cutoff`
- `--nichenet-expression-pct`
- `--nichenet-top-ligands`
- `--receiver`
- `--senders`
- `--species`
- `--r-enhanced`

## Per-method parameter hints

### `builtin`

**Tuning priority:** cell_type_key -> species

**Core parameters:**

| name | default |
|---|---|
| `cell_type_key` | `cell_type` |
| `species` | `human` |

**Requires:**
- `normalized_expression`
- `cell_type_labels_in_obs`

**Tips:**
- --method builtin: Lightweight heuristic baseline. Good for a quick preview, but not a statistical communication test.

### `cellchat_r`

**Tuning priority:** cell_type_key -> species

**Core parameters:**

| name | default |
|---|---|
| `cell_type_key` | `cell_type` |
| `species` | `human` |

**Advanced parameters:**

| name | default |
|---|---|
| `cellchat_prob_type` | `triMean` |
| `cellchat_min_cells` | `10` |

**Requires:**
- `normalized_expression`
- `R_CellChat_stack`
- `cell_type_labels_in_obs`

**Tips:**
- --method cellchat_r: R-backed CellChat path with pathway and centrality outputs.

### `cellphonedb`

**Tuning priority:** cell_type_key -> species

**Core parameters:**

| name | default |
|---|---|
| `cell_type_key` | `cell_type` |
| `species` | `human` |

**Advanced parameters:**

| name | default |
|---|---|
| `cellphonedb_threshold` | `0.1` |
| `cellphonedb_iterations` | `1000` |
| `cellphonedb_pvalue` | `0.05` |
| `cellphonedb_threads` | `4` |
| `cellphonedb_counts_data` | `hgnc_symbol` |

**Requires:**
- `normalized_expression`
- `cellphonedb`
- `cell_type_labels_in_obs`
- `human_species`

**Tips:**
- --method cellphonedb: Uses the official CellPhoneDB statistical backend exposed by the current wrapper.
- --cellphonedb-threshold and --cellphonedb-iterations are the main public CellPhoneDB tuning knobs in OmicsClaw.

### `liana`

**Tuning priority:** cell_type_key -> species

**Core parameters:**

| name | default |
|---|---|
| `cell_type_key` | `cell_type` |
| `species` | `human` |

**Requires:**
- `normalized_expression`
- `liana`
- `cell_type_labels_in_obs`

**Tips:**
- --method liana: Best first rich backend in the current wrapper.

### `nichenet_r`

**Tuning priority:** cell_type_key -> condition_key -> receiver -> senders

**Core parameters:**

| name | default |
|---|---|
| `cell_type_key` | `cell_type` |
| `condition_key` | `condition` |
| `condition_oi` | `stim` |
| `condition_ref` | `ctrl` |
| `receiver` | `` |
| `senders` | `` |

**Advanced parameters:**

| name | default |
|---|---|
| `nichenet_top_ligands` | `20` |
| `nichenet_expression_pct` | `0.1` |
| `nichenet_lfc_cutoff` | `0.25` |
| `species` | `human` |

**Requires:**
- `raw_counts_available`
- `R_nichenetr_stack`
- `cell_type_labels_in_obs`
- `condition_labels_in_obs`
- `human_species`

**Tips:**
- --method nichenet_r: R-backed NicheNet ligand prioritization path.
- --receiver and --senders are required because NicheNet needs explicit receiver and sender cell types.
- --nichenet-lfc-cutoff changes the receiver-side DE genes used as the target program.
