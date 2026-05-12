<!-- AUTO-GENERATED from parameters.yaml — do not edit by hand. -->
<!-- Regenerate: python scripts/generate_parameters_md.py <skill_dir> -->


# Parameters

## Allowed extra CLI flags

- `--method`
- `--n-neighbors`
- `--r-enhanced`

## Per-method parameter hints

### `cytotrace_simple`

**Tuning priority:** n_neighbors

**Core parameters:**

| name | default |
|---|---|
| `n_neighbors` | `30` |

**Requires:**
- `normalized_expression_or_counts`

**Tips:**
- `cytotrace_simple` uses gene detection count as a potency proxy. No external models needed.
