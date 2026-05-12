<!-- AUTO-GENERATED from parameters.yaml — do not edit by hand. -->
<!-- Regenerate: python scripts/generate_parameters_md.py <skill_dir> -->


# Parameters

## Allowed extra CLI flags

- `--read1`
- `--read2`
- `--ids`
- `--ref-map`
- `--ref-annotation`
- `--exp-name`
- `--platform`
- `--threads`
- `--contaminant-index`
- `--min-length-qual-trimming`
- `--min-quality-trimming`
- `--demultiplexing-mismatches`
- `--demultiplexing-kmer`
- `--umi-allowed-mismatches`
- `--umi-start-position`
- `--umi-end-position`
- `--disable-clipping`
- `--compute-saturation`
- `--htseq-no-ambiguous`
- `--transcriptome`
- `--star-two-pass-mode`
- `--stpipeline-repo`
- `--bin-path`

## Per-method parameter hints

### `st_pipeline`

**Tuning priority:** ids/ref_map/ref_annotation -> threads -> compute_saturation -> demultiplexing -> umi

**Core parameters:**

| name | default |
|---|---|
| `read1` | `—` |
| `read2` | `—` |
| `ids` | `—` |
| `ref_map` | `—` |
| `ref_annotation` | `—` |
| `exp_name` | `—` |
| `platform` | `visium` |
| `threads` | `4` |
| `compute_saturation` | `—` |
| `demultiplexing_mismatches` | `2` |
| `demultiplexing_kmer` | `6` |
| `umi_allowed_mismatches` | `1` |
| `umi_start_position` | `18` |
| `umi_end_position` | `27` |

**Requires:**
- `FASTQ_R1`
- `FASTQ_R2`
- `ids_barcode_coordinate_file`
- `STAR_index_directory`
- `GTF_annotation_or_transcriptome`

**Tips:**
- --ids / --ref-map / --ref-annotation: these are the core run contract; matrix-level inputs should go to spatial-preprocess instead.
- --platform: a reporting label only; it does not switch upstream algorithms, but it keeps the output contract explicit for Visium, Slide-seq, or custom barcode-coordinate assays.
- --compute-saturation: enables the upstream saturation curve so the OmicsClaw report can summarize sequencing depth sufficiency.
- --demultiplexing-mismatches / --demultiplexing-kmer: first tuning knobs when barcode recovery is unexpectedly low.
- --umi-allowed-mismatches / --umi-start-position / --umi-end-position: only adjust if the kit layout differs from the standard assumptions or the upstream protocol documents it.
