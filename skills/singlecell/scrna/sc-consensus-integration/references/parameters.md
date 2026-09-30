<!-- Hand-written. `skill.yaml` and its generators were deleted with the old skill system. -->


# Parameters

## Allowed extra CLI flags

- `--all`
- `--alpha`
- `--batch-key`
- `--beta`
- `--confirm-plan`
- `--include-scvi`
- `--integration-methods`
- `--max-class-frac`
- `--max-parallel`
- `--members`
- `--non-interactive`
- `--operator`
- `--resolution`
- `--run-id`
- `--seed`
- `--timeout`
- `--top-k`
- `--vote-baseline`

## Per-method parameter hints

### `default`

**Core parameters:**

| name | default |
|---|---|
| `integration_methods` | `none,harmony,scanorama` |
| `resolution` | `1.0` |
| `batch_key` | `batch` |

**Tips:**
- Members are integration backends; `none` is the unintegrated X_pca baseline that exposes batch-artifact clusters.
- Add `--include-scvi` for the GPU/stochastic scVI member; serialise GPU members with `--max-parallel 1`.
