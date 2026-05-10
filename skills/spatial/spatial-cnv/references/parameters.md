<!-- AUTO-GENERATED from parameters.yaml — do not edit by hand. -->
<!-- Regenerate: python scripts/generate_parameters_md.py <skill_dir> -->


# Parameters

## Allowed extra CLI flags

- `--infercnv-chunksize`
- `--infercnv-dynamic-threshold`
- `--infercnv-exclude-chromosomes`
- `--infercnv-include-sex-chromosomes`
- `--infercnv-lfc-clip`
- `--infercnv-n-jobs`
- `--method`
- `--numbat-genome`
- `--numbat-max-entropy`
- `--numbat-min-cells`
- `--numbat-min-llr`
- `--numbat-ncores`
- `--reference-cat`
- `--reference-key`
- `--step`
- `--window-size`

## Per-method parameter hints

### `infercnvpy`

**Tuning priority:** reference_key/reference_cat → window_size/step → infercnv_dynamic_threshold → infercnv_lfc_clip

**Core parameters:**

| name | default |
|---|---|
| `window_size` | `100` |
| `step` | `10` |
| `infercnv_dynamic_threshold` | `1.5` |
| `infercnv_lfc_clip` | `3.0` |
| `infercnv_exclude_chromosomes` | `chrX,chrY` |
| `infercnv_chunksize` | `5000` |
| `infercnv_n_jobs` | `1` |

**Requires:**
- `obsm.spatial`
- `var.chromosome/start/end`
- `X_log_normalized`

**Tips:**
- --reference-key / --reference-cat: Official infercnvpy reference controls; omit both only when an all-cells baseline is scientifically acceptable.
- --window-size: Number of ordered genes per smoothing window; larger windows emphasize broad chromosome-arm events.
- --step: Compute every nth window; smaller values increase resolution at higher runtime.
- --infercnv-dynamic-threshold: infercnvpy denoising cutoff (`None` disables thresholding, OmicsClaw default is 1.5).
- --infercnv-lfc-clip: Official log-fold-change clipping bound before smoothing.
- --infercnv-exclude-chromosomes / --infercnv-include-sex-chromosomes: infercnvpy defaults exclude `chrX` and `chrY`.
- --infercnv-chunksize / --infercnv-n-jobs: Runtime controls; OmicsClaw defaults to single-job reproducibility.

### `numbat`

**Tuning priority:** reference_key/reference_cat → numbat_max_entropy → numbat_min_llr/min_cells → numbat_ncores

**Core parameters:**

| name | default |
|---|---|
| `numbat_genome` | `hg38` |
| `numbat_max_entropy` | `0.8` |
| `numbat_min_llr` | `5.0` |
| `numbat_min_cells` | `50` |
| `numbat_ncores` | `1` |

**Requires:**
- `layers.counts`
- `allele_counts_table`
- `reference_key/reference_cat`

**Tips:**
- --reference-key / --reference-cat: Current OmicsClaw Numbat wrapper requires labeled diploid reference cells to construct `lambdas_ref`.
- --numbat-max-entropy: Core Numbat filter on allele ambiguity; the spatial RNA tutorial recommends relaxing this toward `0.8` for Visium-like data.
- --numbat-min-llr: Core confidence cutoff for CNA calls in `run_numbat()`.
- --numbat-min-cells: Minimum clone size for retaining a CNA-defined clone.
- --numbat-ncores: Passed to `run_numbat()` as `ncores`.
- --numbat-genome: Reference genome build for the Numbat model (`hg19` or `hg38`).
