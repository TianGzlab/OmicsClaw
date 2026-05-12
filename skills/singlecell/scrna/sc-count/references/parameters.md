<!-- AUTO-GENERATED from parameters.yaml — do not edit by hand. -->
<!-- Regenerate: python scripts/generate_parameters_md.py <skill_dir> -->


# Parameters

## Allowed extra CLI flags

- `--chemistry`
- `--method`
- `--r-enhanced`
- `--read2`
- `--reference`
- `--sample`
- `--t2g`
- `--threads`
- `--whitelist`

## Per-method parameter hints

### `cellranger`

**Tuning priority:** reference -> sample -> threads -> chemistry

**Core parameters:**

| name | default |
|---|---|
| `reference` | `—` |
| `sample` | `—` |
| `threads` | `8` |
| `chemistry` | `auto` |

**Requires:**
- `cellranger`
- `fastq_dir_or_existing_cellranger_output`

**Tips:**
- --reference: required Cell Ranger transcriptome reference directory.
- --sample: choose one sample when the FASTQ directory contains multiple groups.
- --chemistry auto: current wrapper leaves chemistry auto-detection to Cell Ranger by default.

### `kb_python`

**Tuning priority:** reference -> t2g -> chemistry -> sample -> threads

**Core parameters:**

| name | default |
|---|---|
| `reference` | `—` |
| `t2g` | `—` |
| `chemistry` | `10xv3` |
| `sample` | `—` |
| `threads` | `8` |

**Requires:**
- `kb_output_or_fastq`

**Tips:**
- --reference: current wrapper expects a kallisto index path.
- --t2g: required transcript-to-gene map for kb-python runs.
- --chemistry: forwarded as kb technology string such as `10xv2`, `10xv3`, or `10xv4`.

### `simpleaf`

**Tuning priority:** reference -> chemistry -> sample -> threads

**Core parameters:**

| name | default |
|---|---|
| `reference` | `—` |
| `chemistry` | `10xv3` |
| `sample` | `—` |
| `threads` | `8` |

**Requires:**
- `simpleaf_output_or_fastq`

**Tips:**
- --reference: current wrapper expects a simpleaf index path.
- --chemistry: current wrapper is optimized for mainstream 10x-style droplet presets.

### `starsolo`

**Tuning priority:** reference -> chemistry -> whitelist -> sample -> threads

**Core parameters:**

| name | default |
|---|---|
| `reference` | `—` |
| `chemistry` | `—` |
| `whitelist` | `—` |
| `sample` | `—` |
| `threads` | `8` |

**Requires:**
- `STAR`
- `10x_paired_fastq_or_existing_starsolo_output`

**Tips:**
- --chemistry: current STARsolo wrapper supports `10xv2`, `10xv3`, and `10xv4` geometry.
- --whitelist: strongly recommended; OmicsClaw only auto-detects common local v2/v3 whitelist files.
- --reference: must be a STAR genome directory, not a raw FASTA/GTF pair.
