<!-- AUTO-GENERATED from parameters.yaml — do not edit by hand. -->
<!-- Regenerate: python scripts/generate_parameters_md.py <skill_dir> -->


# Parameters

## Allowed extra CLI flags

- `--engine`
- `--fdr-threshold`
- `--gene-set-db`
- `--gene-set-from-markers`
- `--gene-sets`
- `--groupby`
- `--gsea-max-size`
- `--gsea-min-size`
- `--gsea-permutation-num`
- `--gsea-ranking-metric`
- `--gsea-seed`
- `--gsea-weight`
- `--marker-group`
- `--marker-top-n`
- `--method`
- `--ora-log2fc-cutoff`
- `--ora-max-genes`
- `--ora-padj-cutoff`
- `--r-enhanced`
- `--ranking-method`
- `--species`
- `--top-terms`

## Per-method parameter hints

### `gsea`

**Tuning priority:** gene_sets/gene_set_db/gene_set_from_markers -> engine -> groupby/ranking_method

**Core parameters:**

| name | default |
|---|---|
| `gene_sets` | `—` |
| `gene_set_db` | `—` |
| `gene_set_from_markers` | `—` |
| `marker_group` | `—` |
| `marker_top_n` | `—` |
| `engine` | `auto` |
| `groupby` | `—` |
| `ranking_method` | `wilcoxon` |

**Advanced parameters:**

| name | default |
|---|---|
| `gsea_ranking_metric` | `auto` |
| `gsea_min_size` | `5` |
| `gsea_max_size` | `500` |
| `gsea_permutation_num` | `100` |
| `gsea_weight` | `1.0` |
| `gsea_seed` | `123` |
| `species` | `human` |
| `top_terms` | `18` |

**Requires:**
- `gene_set_source`
- `full_ranked_gene_list`

**Tips:**
- --method gsea: keeps the full ranking and is better when subtle coordinated shifts matter more than hard DEG thresholds.
- If the input is a filtered marker table, OmicsClaw may rebuild a fuller ranking from `processed.h5ad`.
- `gsea_ranking_metric=auto` prefers `stat`, then `scores`, then `logfoldchanges`.

### `ora`

**Tuning priority:** gene_sets/gene_set_db/gene_set_from_markers -> engine -> groupby/ranking_method

**Core parameters:**

| name | default |
|---|---|
| `gene_sets` | `—` |
| `gene_set_db` | `—` |
| `gene_set_from_markers` | `—` |
| `marker_group` | `—` |
| `marker_top_n` | `—` |
| `engine` | `auto` |
| `groupby` | `—` |
| `ranking_method` | `wilcoxon` |

**Advanced parameters:**

| name | default |
|---|---|
| `ora_padj_cutoff` | `0.05` |
| `ora_log2fc_cutoff` | `0.25` |
| `ora_max_genes` | `200` |
| `species` | `human` |
| `top_terms` | `18` |

**Requires:**
- `gene_set_source`
- `normalized_expression_or_upstream_ranking`

**Tips:**
- --method ora: best for thresholded marker/DE gene lists when you want the most enriched terms quickly.
- If you only provide a processed h5ad, the wrapper can auto-rank cluster markers first using `ranking_method`.
- If you already ran `sc-markers` or `sc-de`, passing that output directory lets the wrapper reuse exported rankings.
