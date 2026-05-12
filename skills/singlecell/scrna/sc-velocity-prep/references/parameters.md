<!-- AUTO-GENERATED from parameters.yaml — do not edit by hand. -->
<!-- Regenerate: python scripts/generate_parameters_md.py <skill_dir> -->


# Parameters

## Allowed extra CLI flags

- `--base-h5ad`
- `--chemistry`
- `--gtf`
- `--method`
- `--read2`
- `--reference`
- `--sample`
- `--threads`
- `--whitelist`
- `--r-enhanced`

## Per-method parameter hints

### `starsolo`

**Tuning priority:** reference -> chemistry -> whitelist -> base_h5ad -> sample -> threads

**Core parameters:**

| name | default |
|---|---|
| `reference` | `—` |
| `chemistry` | `—` |
| `whitelist` | `—` |
| `base_h5ad` | `—` |
| `sample` | `—` |
| `threads` | `8` |

**Requires:**
- `starsolo_velocyto_output_or_fastq`

**Tips:**
- --chemistry: current STARsolo velocity wrapper supports `10xv2`, `10xv3`, and `10xv4` geometry.
- --whitelist: strongly recommended for real FASTQ-backed STARsolo runs.
- --base-h5ad: merge velocity layers into an existing preprocessed AnnData for direct scVelo use.

### `velocyto`

**Tuning priority:** gtf -> base_h5ad -> threads

**Core parameters:**

| name | default |
|---|---|
| `gtf` | `—` |
| `base_h5ad` | `—` |
| `threads` | `4` |

**Requires:**
- `cellranger_output_or_loom`

**Tips:**
- --gtf: required when the wrapper needs to run velocyto from a Cell Ranger BAM.
- --base-h5ad: merge spliced/unspliced layers back into an existing OmicsClaw object.
