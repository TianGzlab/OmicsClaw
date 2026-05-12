<!-- AUTO-GENERATED from parameters.yaml — do not edit by hand. -->
<!-- Regenerate: python scripts/generate_parameters_md.py <skill_dir> -->


# Parameters

## Allowed extra CLI flags

- `--celltypist-majority-voting`
- `--cluster-key`
- `--manual-map`
- `--manual-map-file`
- `--marker-file`
- `--method`
- `--model`
- `--r-enhanced`
- `--reference`
- `--scsa-foldchange`
- `--scsa-pvalue`
- `--species`
- `--tissue`

## Per-method parameter hints

### `celltypist`

**Tuning priority:** model -> celltypist_majority_voting

**Core parameters:**

| name | default |
|---|---|
| `model` | `Immune_All_Low` |
| `celltypist_majority_voting` | `False` |

**Requires:**
- `celltypist`
- `normalized_expression_matrix`

**Tips:**
- --model: CellTypist model name or model file stem.
- --celltypist-majority-voting: optional neighborhood/cluster smoothing for CellTypist labels.

### `knnpredict`

**Tuning priority:** reference -> cluster_key

**Core parameters:**

| name | default |
|---|---|
| `reference` | `—` |
| `cluster_key` | `auto` |

**Requires:**
- `labeled_reference_h5ad`
- `normalized_expression_matrix`

**Tips:**
- --method knnpredict: lightweight AnnData-first projection inspired by SCOP KNNPredict.

### `manual`

**Tuning priority:** cluster_key -> manual_map/manual_map_file

**Core parameters:**

| name | default |
|---|---|
| `cluster_key` | `auto` |
| `manual_map` | `—` |
| `manual_map_file` | `—` |

**Requires:**
- `cluster_labels_in_obs`

**Tips:**
- --method manual: explicit relabeling from user-provided cluster mappings.
- --manual-map example: `0=T cell;1,2=Myeloid`.

### `markers`

**Tuning priority:** cluster_key -> marker_file

**Core parameters:**

| name | default |
|---|---|
| `cluster_key` | `auto` |
| `marker_file` | `None` |

**Requires:**
- `normalized_expression`
- `cluster_labels_in_obs`

**Tips:**
- --method markers: use when clusters already exist and you want a quick label proposal from known markers.
- Built-in markers cover blood (PBMC), brain, and general tissue cell types (human gene symbols).
- For non-human organisms or specialized tissues, provide --marker-file markers.json.
- If ALL cells are 'Unknown', it means marker genes were not found — see Reference Data Guide below.

### `popv`

**Tuning priority:** reference -> cluster_key

**Core parameters:**

| name | default |
|---|---|
| `reference` | `—` |
| `cluster_key` | `auto` |

**Requires:**
- `labeled_reference_h5ad`
- `normalized_expression_matrix`

**Tips:**
- --method popv: official PopV path when possible, else lightweight reference mapping fallback.

### `scmap`

**Tuning priority:** reference

**Core parameters:**

| name | default |
|---|---|
| `reference` | `HPCA` |

**Requires:**
- `R_scmap_stack`

**Tips:**
- --method scmap: R scmap path using celldex / ExperimentHub atlases or a labeled local H5AD reference.

### `singler`

**Tuning priority:** reference

**Core parameters:**

| name | default |
|---|---|
| `reference` | `HPCA` |

**Requires:**
- `R_SingleR_stack`

**Tips:**
- --method singler: R SingleR path using celldex / ExperimentHub atlases or a labeled local H5AD reference.
