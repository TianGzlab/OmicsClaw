<!-- AUTO-GENERATED from parameters.yaml — do not edit by hand. -->
<!-- Regenerate: python scripts/generate_parameters_md.py <skill_dir> -->


# Parameters

## Allowed extra CLI flags

- `--embedding-method`
- `--cluster-method`
- `--use-rep`
- `--n-neighbors`
- `--n-pcs`
- `--resolution`
- `--umap-min-dist`
- `--umap-spread`
- `--tsne-perplexity`
- `--tsne-metric`
- `--diffmap-n-comps`
- `--phate-knn`
- `--phate-decay`
- `--r-enhanced`

## Per-method parameter hints

### `diffmap`

**Tuning priority:** use_rep -> cluster_method -> n_neighbors/resolution

**Core parameters:**

| name | default |
|---|---|
| `use_rep` | `—` |
| `cluster_method` | `leiden` |
| `n_neighbors` | `15` |
| `resolution` | `1.0` |

**Advanced parameters:**

| name | default |
|---|---|
| `n_pcs` | `50` |
| `diffmap_n_comps` | `15` |

**Requires:**
- `normalized_expression`
- `embedding_or_pca`

**Tips:**
- `diffmap` often emphasizes continuous trajectories more than compact clusters.

### `phate`

**Tuning priority:** use_rep -> cluster_method -> n_neighbors/resolution

**Core parameters:**

| name | default |
|---|---|
| `use_rep` | `—` |
| `cluster_method` | `leiden` |
| `n_neighbors` | `15` |
| `resolution` | `1.0` |

**Advanced parameters:**

| name | default |
|---|---|
| `n_pcs` | `50` |
| `phate_knn` | `15` |
| `phate_decay` | `40` |

**Requires:**
- `normalized_expression`
- `embedding_or_pca`
- `phate`

**Tips:**
- `phate` is optional and may need extra installation before use.

### `tsne`

**Tuning priority:** use_rep -> cluster_method -> n_neighbors/resolution

**Core parameters:**

| name | default |
|---|---|
| `use_rep` | `—` |
| `cluster_method` | `leiden` |
| `n_neighbors` | `15` |
| `resolution` | `1.0` |

**Advanced parameters:**

| name | default |
|---|---|
| `n_pcs` | `50` |
| `tsne_perplexity` | `30.0` |
| `tsne_metric` | `euclidean` |

**Requires:**
- `normalized_expression`
- `embedding_or_pca`

**Tips:**
- `tsne` is mainly for visualization; the clustering still comes from the neighbor graph.

### `umap`

**Tuning priority:** use_rep -> cluster_method -> n_neighbors/resolution

**Core parameters:**

| name | default |
|---|---|
| `use_rep` | `—` |
| `cluster_method` | `leiden` |
| `n_neighbors` | `15` |
| `resolution` | `1.0` |

**Advanced parameters:**

| name | default |
|---|---|
| `n_pcs` | `50` |
| `umap_min_dist` | `0.5` |
| `umap_spread` | `1.0` |

**Requires:**
- `normalized_expression`
- `embedding_or_pca`

**Tips:**
- `use_rep` is the most important selector if multiple embeddings are available.
