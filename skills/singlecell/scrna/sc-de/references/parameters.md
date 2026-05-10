<!-- AUTO-GENERATED from parameters.yaml — do not edit by hand. -->
<!-- Regenerate: python scripts/generate_parameters_md.py <skill_dir> -->


# Parameters

## Allowed extra CLI flags

- `--celltype-key`
- `--group1`
- `--group2`
- `--groupby`
- `--log2fc-threshold`
- `--logreg-solver`
- `--method`
- `--n-top-genes`
- `--padj-threshold`
- `--pseudobulk-min-cells`
- `--pseudobulk-min-counts`
- `--sample-key`
- `--r-enhanced`

## Per-method parameter hints

### `deseq2_r`

**Tuning priority:** groupby -> group1/group2 -> sample_key -> celltype_key

**Core parameters:**

| name | default |
|---|---|
| `groupby` | `—` |
| `group1` | `—` |
| `group2` | `—` |
| `sample_key` | `sample_id` |
| `celltype_key` | `cell_type` |

**Advanced parameters:**

| name | default |
|---|---|
| `pseudobulk_min_cells` | `10` |
| `pseudobulk_min_counts` | `1000` |
| `padj_threshold` | `0.05` |
| `log2fc_threshold` | `1.0` |

**Requires:**
- `raw_counts_or_raw_layer`
- `biological_replicates`
- `R_DESeq2_stack`

**Tips:**
- --method deseq2_r: Sample-aware pseudobulk path.
- --group1 and --group2 are required for the DESeq2 path.

### `logreg`

**Tuning priority:** groupby -> logreg_solver -> n_top_genes

**Core parameters:**

| name | default |
|---|---|
| `groupby` | `leiden` |
| `logreg_solver` | `lbfgs` |
| `n_top_genes` | `10` |

**Advanced parameters:**

| name | default |
|---|---|
| `padj_threshold` | `0.05` |
| `log2fc_threshold` | `1.0` |

**Requires:**
- `preprocessed_anndata`
- `scanpy`

**Tips:**
- --method logreg: Logistic-regression ranking, useful when you want genes that best separate one group from the others.

### `mast`

**Tuning priority:** groupby -> group1/group2 -> n_top_genes

**Core parameters:**

| name | default |
|---|---|
| `groupby` | `leiden` |
| `group1` | `—` |
| `group2` | `—` |
| `n_top_genes` | `10` |

**Advanced parameters:**

| name | default |
|---|---|
| `padj_threshold` | `0.05` |
| `log2fc_threshold` | `1.0` |

**Requires:**
- `R_MAST_stack`
- `log_normalized_expression_matrix`

**Tips:**
- --method mast: R-backed MAST hurdle-model path on log-normalized expression.

### `t-test`

**Tuning priority:** groupby -> n_top_genes -> group1/group2

**Core parameters:**

| name | default |
|---|---|
| `groupby` | `leiden` |
| `n_top_genes` | `10` |
| `group1` | `—` |
| `group2` | `—` |

**Advanced parameters:**

| name | default |
|---|---|
| `padj_threshold` | `0.05` |
| `log2fc_threshold` | `1.0` |

**Requires:**
- `preprocessed_anndata`
- `scanpy`

**Tips:**
- --method t-test: Parametric alternative to Wilcoxon.

### `wilcoxon`

**Tuning priority:** groupby -> n_top_genes -> group1/group2

**Core parameters:**

| name | default |
|---|---|
| `groupby` | `leiden` |
| `n_top_genes` | `10` |
| `group1` | `—` |
| `group2` | `—` |

**Advanced parameters:**

| name | default |
|---|---|
| `padj_threshold` | `0.05` |
| `log2fc_threshold` | `1.0` |

**Requires:**
- `preprocessed_anndata`
- `scanpy`

**Tips:**
- --method wilcoxon: Default exploratory marker-ranking path.
