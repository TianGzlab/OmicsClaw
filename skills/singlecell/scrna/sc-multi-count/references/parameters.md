<!-- AUTO-GENERATED from parameters.yaml — do not edit by hand. -->
<!-- Regenerate: python scripts/generate_parameters_md.py <skill_dir> -->


# Parameters

## Allowed extra CLI flags

- `--r-enhanced`
- `--sample-id`

## Per-method parameter hints

### `merge`

**Tuning priority:** input (multiple) -> sample-id -> output

**Core parameters:**

| name | default |
|---|---|
| `input` | `—` |
| `sample-id` | `—` |

**Requires:**
- `two_or_more_processed_h5ad`

**Tips:**
- --input: repeat for each sample, e.g. --input s1/processed.h5ad --input s2/processed.h5ad
- --sample-id: optional labels; if omitted, derived from directory or file names.
