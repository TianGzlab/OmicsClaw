<!-- AUTO-GENERATED from parameters.yaml — do not edit by hand. -->
<!-- Regenerate: python scripts/generate_parameters_md.py <skill_dir> -->


# Parameters

## Allowed extra CLI flags

- `--method`
- `--gene-sets`
- `--gene-set-db`
- `--species`
- `--groupby`
- `--top-pathways`
- `--aucell-auc-max-rank`
- `--score-genes-ctrl-size`
- `--score-genes-n-bins`
- `--aucell-py-auc-threshold`
- `--r-enhanced`

## Per-method parameter hints

### `aucell_py`

**Tuning priority:** gene_sets/gene_set_db -> groupby -> aucell_py_auc_threshold -> top_pathways

**Core parameters:**

| name | default |
|---|---|
| `gene_sets` | `—` |
| `gene_set_db` | `—` |
| `species` | `human` |
| `groupby` | `auto-detect cluster/cell_type label when omitted` |
| `aucell_py_auc_threshold` | `0.05` |
| `top_pathways` | `20` |

**Requires:**
- `local_gmt_or_gene_set_db`

**Tips:**
- --method aucell_py: pure Python AUCell implementation -- no R required.
- --aucell-py-auc-threshold: fraction of ranked genome for AUC calculation (default 0.05).
- AUCell ranks genes per cell by expression, then measures gene-set recovery curve AUC.

### `aucell_r`

**Tuning priority:** gene_sets/gene_set_db -> groupby -> aucell_auc_max_rank -> top_pathways

**Core parameters:**

| name | default |
|---|---|
| `gene_sets` | `—` |
| `gene_set_db` | `—` |
| `species` | `human` |
| `groupby` | `auto-detect cluster/cell_type label when omitted` |
| `aucell_auc_max_rank` | `5% of detected features when omitted` |
| `top_pathways` | `20` |

**Requires:**
- `AUCell`
- `GSEABase`
- `local_gmt_or_gene_set_db`

**Tips:**
- --method aucell_r: Official AUCell Bioconductor scoring path.
- --aucell-auc-max-rank: AUCell ranking depth override; leave unset to use the wrapper's 5% feature default.

### `score_genes_py`

**Tuning priority:** gene_sets/gene_set_db -> groupby -> score_genes_ctrl_size -> score_genes_n_bins -> top_pathways

**Core parameters:**

| name | default |
|---|---|
| `gene_sets` | `—` |
| `gene_set_db` | `—` |
| `species` | `human` |
| `groupby` | `auto-detect cluster/cell_type label when omitted` |
| `score_genes_ctrl_size` | `50` |
| `score_genes_n_bins` | `25` |
| `top_pathways` | `20` |

**Requires:**
- `normalized_expression`
- `local_gmt_or_gene_set_db`

**Tips:**
- --method score_genes_py: lightweight Python module-score path for normalized adata.X.
- --score-genes-ctrl-size: number of control genes used for background subtraction.
- --score-genes-n-bins: expression binning granularity for control-gene matching.
