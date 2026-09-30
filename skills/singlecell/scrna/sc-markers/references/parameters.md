<!-- Hand-written. `skill.yaml` and its generators were deleted with the old skill system. -->


# Parameters

## Allowed extra CLI flags

- `--groupby`
- `--max-out-group-fraction`
- `--method`
- `--min-fold-change`
- `--min-in-group-fraction`
- `--mu`
- `--n-genes`
- `--n-top`
- `--r-enhanced`

## Per-method parameter hints

### `cosg`

**Tuning priority:** groupby -> n_genes -> mu

**Core parameters:**

| name | default |
|---|---|
| `groupby` | `—` |
| `n_genes` | `50` |
| `n_top` | `10` |
| `mu` | `1.0` |

**Requires:**
- `normalized_expression`
- `group_labels_in_obs`

**Tips:**
- --method cosg: fast cosine-similarity specificity scoring without p-values.
- --mu: specificity penalty (0-1). Higher values penalize non-target expression more.
- COSG is especially useful for large datasets where Wilcoxon is slow.

### `logreg`

**Tuning priority:** groupby -> n_genes -> n_top

**Core parameters:**

| name | default |
|---|---|
| `groupby` | `—` |
| `n_genes` | `all` |
| `n_top` | `10` |

**Advanced parameters:**

| name | default |
|---|---|
| `min_fold_change` | `0.25` |
| `min_in_group_fraction` | `0.25` |
| `max_out_group_fraction` | `0.5` |

**Requires:**
- `normalized_expression`
- `group_labels_in_obs`

**Tips:**
- --method logreg: classification-style ranking for discriminative genes.

### `t-test`

**Tuning priority:** groupby -> n_genes -> n_top

**Core parameters:**

| name | default |
|---|---|
| `groupby` | `—` |
| `n_genes` | `all` |
| `n_top` | `10` |

**Advanced parameters:**

| name | default |
|---|---|
| `min_fold_change` | `0.25` |
| `min_in_group_fraction` | `0.25` |
| `max_out_group_fraction` | `0.5` |

**Requires:**
- `normalized_expression`
- `group_labels_in_obs`

**Tips:**
- --method t-test: parametric alternative when users want a simple mean-shift test.

### `wilcoxon`

**Tuning priority:** groupby -> n_genes -> n_top

**Core parameters:**

| name | default |
|---|---|
| `groupby` | `—` |
| `n_genes` | `all` |
| `n_top` | `10` |

**Advanced parameters:**

| name | default |
|---|---|
| `min_fold_change` | `0.25` |
| `min_in_group_fraction` | `0.25` |
| `max_out_group_fraction` | `0.5` |

**Requires:**
- `normalized_expression`
- `group_labels_in_obs`

**Tips:**
- --method wilcoxon: safest first-pass default for cluster marker ranking.
