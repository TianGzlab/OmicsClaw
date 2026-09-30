<!-- Hand-written. `skill.yaml` and its generators were deleted with the old skill system. -->


# Parameters

## Allowed extra CLI flags

- `--all`
- `--alpha`
- `--beta`
- `--cluster-methods`
- `--confirm-plan`
- `--llm-judge`
- `--max-class-frac`
- `--max-parallel`
- `--members`
- `--n-clusters`
- `--non-interactive`
- `--operator`
- `--resolutions`
- `--run-id`
- `--seed`
- `--timeout`
- `--top-k`

## Per-method parameter hints

### `leiden`

**Tips:**
- Per-member resolution is not a standalone CLI flag; the sweep values come from the --resolutions list (see allowed_extra_flags).

### `louvain`

**Tips:**
- Per-member resolution is not a standalone CLI flag; the sweep values come from the --resolutions list (see allowed_extra_flags).
