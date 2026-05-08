---
name: spatial-cnv
description: >-
  Infer copy number variation programs from spatial transcriptomics data using
  inferCNVpy or Numbat, with method-aware matrix selection, reference controls,
  and spatially mappable CNV summaries.
version: 0.3.0
author: OmicsClaw Team
license: MIT
tags: [spatial, CNV, copy number, infercnvpy, inferCNV, numbat, aneuploidy, cancer]
metadata:
  omicsclaw:
    domain: spatial
    allowed_extra_flags:
    - "--infercnv-chunksize"
    - "--infercnv-dynamic-threshold"
    - "--infercnv-exclude-chromosomes"
    - "--infercnv-include-sex-chromosomes"
    - "--infercnv-lfc-clip"
    - "--infercnv-n-jobs"
    - "--method"
    - "--numbat-genome"
    - "--numbat-max-entropy"
    - "--numbat-min-cells"
    - "--numbat-min-llr"
    - "--numbat-ncores"
    - "--reference-cat"
    - "--reference-key"
    - "--step"
    - "--window-size"
    param_hints:
      infercnvpy:
        priority: "reference_key/reference_cat → window_size/step → infercnv_dynamic_threshold
          → infercnv_lfc_clip"
        params: ["window_size", "step", "infercnv_dynamic_threshold", "infercnv_lfc_clip",
          "infercnv_exclude_chromosomes", "infercnv_chunksize", "infercnv_n_jobs"]
        defaults: {window_size: 100, step: 10, infercnv_dynamic_threshold: 1.5, infercnv_lfc_clip: 3.0,
          infercnv_exclude_chromosomes: "chrX,chrY", infercnv_chunksize: 5000, infercnv_n_jobs: 1}
        requires: ["obsm.spatial", "var.chromosome/start/end", "X_log_normalized"]
        tips:
        - "--reference-key / --reference-cat: Official infercnvpy reference controls;
          omit both only when an all-cells baseline is scientifically acceptable."
        - "--window-size: Number of ordered genes per smoothing window; larger windows
          emphasize broad chromosome-arm events."
        - "--step: Compute every nth window; smaller values increase resolution at
          higher runtime."
        - "--infercnv-dynamic-threshold: infercnvpy denoising cutoff (`None` disables
          thresholding, OmicsClaw default is 1.5)."
        - "--infercnv-lfc-clip: Official log-fold-change clipping bound before smoothing."
        - "--infercnv-exclude-chromosomes / --infercnv-include-sex-chromosomes: infercnvpy
          defaults exclude `chrX` and `chrY`."
        - "--infercnv-chunksize / --infercnv-n-jobs: Runtime controls; OmicsClaw defaults
          to single-job reproducibility."
      numbat:
        priority: "reference_key/reference_cat → numbat_max_entropy → numbat_min_llr/min_cells
          → numbat_ncores"
        params: ["numbat_genome", "numbat_max_entropy", "numbat_min_llr", "numbat_min_cells",
          "numbat_ncores"]
        defaults: {numbat_genome: "hg38", numbat_max_entropy: 0.8, numbat_min_llr: 5.0,
          numbat_min_cells: 50, numbat_ncores: 1}
        requires: ["layers.counts", "allele_counts_table", "reference_key/reference_cat"]
        tips:
        - "--reference-key / --reference-cat: Current OmicsClaw Numbat wrapper requires
          labeled diploid reference cells to construct `lambdas_ref`."
        - "--numbat-max-entropy: Core Numbat filter on allele ambiguity; the spatial
          RNA tutorial recommends relaxing this toward `0.8` for Visium-like data."
        - "--numbat-min-llr: Core confidence cutoff for CNA calls in `run_numbat()`."
        - "--numbat-min-cells: Minimum clone size for retaining a CNA-defined clone."
        - "--numbat-ncores: Passed to `run_numbat()` as `ncores`."
        - "--numbat-genome: Reference genome build for the Numbat model (`hg19` or
          `hg38`)."
    legacy_aliases: [cnv]
    saves_h5ad: true
    requires_preprocessed: true
    requires:
      bins:
      - python3
      env: []
      config: []
    emoji: "🧫"
    homepage: https://github.com/TianGzlab/OmicsClaw
    os: [macos, linux]
    install:
    - kind: pip
      package: scanpy
      bins: []
    - kind: pip
      package: infercnvpy
      bins: []
    trigger_keywords:
    - copy number variation
    - CNV
    - inferCNV
    - infercnvpy
    - Numbat
    - aneuploidy
    - chromosomal aberration
    - tumor clone
    script: spatial_cnv.py
---

# 🧫 Spatial CNV

You are **Spatial CNV**, the copy-number inference skill for OmicsClaw. Your
role is to identify large-scale chromosomal gains and losses from spatial
transcriptomics data while preserving the matrix assumptions and reference
requirements of each CNV method.

## Why This Exists

- **Without it**: users have to wire gene-position metadata, reference groups,
  expression matrices, and downstream spatial visualization manually.
- **With it**: one skill coordinates matrix-aware CNV inference, exports
  reproducibility commands, and writes spatially interpretable summary tables.
- **Why OmicsClaw**: it provides a method-specific wrapper layer around
  inferCNVpy and Numbat, so the user sees the right knobs first and the project
  can extend methods later without changing the interaction pattern.

## Core Capabilities

1. **inferCNVpy** (default): expression-based CNV inference on log-normalized
   expression with official infercnvpy tuning flags.
2. **Numbat**: haplotype-aware CNV inference via R using raw counts, allele
   counts, and diploid reference expression profiles.
3. **Reference-aware runs**: supports `reference_key` / `reference_cat`
   baseline selection for both methods.
4. **Standard Python gallery**: emits a recipe-driven CNV gallery with
   overview, diagnostic, supporting, and uncertainty panels backed by the
   shared `skills/spatial/_lib/viz` layer.
5. **Figure-ready exports**: writes `figure_data/` CSVs plus a gallery manifest
   so downstream tools can restyle the same analysis without recomputing CNV.
6. **Compact result tables**: writes cell-level CNV scores and method-specific
   CNV summaries for downstream inspection.

## Input Formats

| Format | Extension | Required Fields | Example |
|--------|-----------|-----------------|---------|
| AnnData (preprocessed) | `.h5ad` | `X`, `obsm["spatial"]`, `var["chromosome"]`, `var["start"]`, `var["end"]` | `processed.h5ad` |
| Demo | n/a | `--demo` flag | Runs spatial-preprocess demo first and injects synthetic gene positions / references |

### Input Matrix Convention

The two CNV methods do **not** consume the same matrix representation:

| Method | Input Matrix | Rationale |
|--------|--------------|-----------|
| `infercnvpy` | `adata.X` (log-normalized) | `infercnvpy.tl.infercnv()` models smoothed log-fold-change relative to a baseline and documents `layer=None -> X` as the main input path |
| `numbat` | `adata.layers["counts"]` (raw integer UMI counts) | `run_numbat()` expects a gene-by-cell UMI count matrix and combines it with allele evidence |

**Core principle**: inferCNV-style expression smoothing works on normalized
log-expression, while Numbat's joint expression/allelic model works on raw
integer counts plus phased SNP evidence.

### Additional Numbat Inputs

The current OmicsClaw Numbat wrapper requires:

- `adata.obsm["allele_counts"]`: a table-like object with columns
  `cell/snp_id/CHROM/POS/AD/DP/GT/gene`
- `--reference-key` and `--reference-cat`: labeled diploid reference cells used
  by OmicsClaw to build `lambdas_ref`

If `layers["counts"]` is missing, OmicsClaw falls back to `adata.raw` or
`adata.X` with a warning.

## Workflow

1. **Load**: read the preprocessed `.h5ad` and validate genomic annotations.
2. **Validate**: check method-specific matrix requirements and reference
   metadata.
3. **Run CNV inference**:
   - `infercnvpy`: infer CNV matrix, then build CNV-space PCA / neighbors /
     Leiden clusters before computing `cnv_score`
   - `numbat`: export a lightweight h5ad + allele-count table and launch the R
     `run_numbat()` workflow
4. **Summarize**: compute cell-level CNV scores and write method-specific CSV
   outputs.
5. **Visualize**: render the standard Python CNV gallery from a declarative
   recipe built on `plot_cnv()` and `plot_features()`.
6. **Export figure data**: write figure-ready CSVs and manifests for optional
   R-side beautification or custom plotting.
7. **Report and export**: write `report.md`, `result.json`, `processed.h5ad`,
   tables, figures, `figure_data/`, and reproducibility helpers.

## CLI Reference

```bash
# inferCNVpy default run
oc run spatial-cnv \
  --input <processed.h5ad> --output <dir>

# inferCNVpy with explicit reference cells and broader smoothing
oc run spatial-cnv \
  --input <processed.h5ad> --method infercnvpy \
  --reference-key cell_type --reference-cat Normal Stroma \
  --window-size 150 --step 20 \
  --infercnv-dynamic-threshold 1.5 \
  --infercnv-lfc-clip 3.0 \
  --infercnv-exclude-chromosomes chrX chrY \
  --infercnv-chunksize 5000 --infercnv-n-jobs 1 \
  --output <dir>

# inferCNVpy including sex chromosomes
oc run spatial-cnv \
  --input <processed.h5ad> --method infercnvpy \
  --reference-key cell_type --reference-cat Normal \
  --infercnv-include-sex-chromosomes \
  --output <dir>

# Numbat (requires raw counts, allele counts, and diploid references)
oc run spatial-cnv \
  --input <processed.h5ad> --method numbat \
  --reference-key cell_type --reference-cat Normal \
  --numbat-genome hg38 --numbat-max-entropy 0.8 \
  --numbat-min-llr 5 --numbat-min-cells 50 --numbat-ncores 4 \
  --output <dir>

# Demo mode
oc run spatial-cnv --demo --output /tmp/cnv_demo

# Direct script entrypoint
python skills/spatial/spatial-cnv/spatial_cnv.py \
  --input <processed.h5ad> --method infercnvpy --output <dir>
```

Every successful standard OmicsClaw wrapper run, including `oc run` and
conversational skill execution, also writes a top-level `README.md` and
`reproducibility/analysis_notebook.ipynb` to make the output directory easier
to inspect and rerun.

## Example Queries

- "Infer CNV from my spatial transcriptomics data"
- "Run inferCNVpy using stromal spots as the reference baseline"
- "Use Numbat with allele counts to identify tumor clones"

## Algorithm / Methodology

### inferCNVpy (default)

1. **Input**: `adata.X` (log-normalized expression) plus
   `var["chromosome"]`, `var["start"]`, `var["end"]`
2. **Reference baseline**: `reference_key` / `reference_cat` map to the
   official infercnvpy baseline controls; if omitted, infercnvpy uses an
   all-cells average reference
3. **CNV inference**: OmicsClaw runs `infercnvpy.tl.infercnv(...)` with
   official core parameters including `lfc_clip`, `window_size`, `step`,
   `dynamic_threshold`, `exclude_chromosomes`, `chunksize`, and `n_jobs`
4. **CNV-space clustering**: after inference, OmicsClaw computes CNV PCA,
   CNV-neighbor graph, and CNV Leiden clusters before calling
   `infercnvpy.tl.cnv_score(...)`
5. **Cell-level summary**: `cnv_score` is used as the main scalar anomaly score
   and exported for visualization / downstream routing

**Core tuning flags**:

- `--reference-key` / `--reference-cat`: define the diploid baseline; this is
  usually the first scientific decision
- `--window-size`: larger windows emphasize broad arm-level aberrations, while
  smaller windows retain finer local structure
- `--step`: lower values increase resolution and runtime
- `--infercnv-dynamic-threshold`: denoising threshold applied relative to the
  CNV standard deviation; omit or disable only intentionally
- `--infercnv-lfc-clip`: caps extreme log-fold-change values
- `--infercnv-exclude-chromosomes`: official chromosome-exclusion control
- `--infercnv-chunksize` / `--infercnv-n-jobs`: scalability knobs

### Numbat

1. **Input**: raw integer UMI counts from `layers["counts"]` plus allele-count
   table in `adata.obsm["allele_counts"]`
2. **Diploid reference construction**: the current OmicsClaw wrapper builds
   `lambdas_ref` from `--reference-key` and `--reference-cat`
3. **Joint CNV inference**: OmicsClaw calls the R `run_numbat()` workflow with
   `count_mat`, `lambdas_ref`, `df_allele`, `genome`, `max_entropy`,
   `min_LLR`, `min_cells`, and `ncores`
4. **Clone posterior export**: the wrapper exports Numbat joint-posterior and
   clone-posterior tables back into OmicsClaw outputs

**Core tuning flags**:

- `--reference-key` / `--reference-cat`: required in the current wrapper
- `--numbat-max-entropy`: allele-ambiguity filter; the official spatial RNA
  tutorial relaxes this toward `0.8` on Visium-like data
- `--numbat-min-llr`: minimum CNA confidence cutoff
- `--numbat-min-cells`: minimum cells per retained CNA-defined clone
- `--numbat-ncores`: parallel worker count for the R workflow
- `--numbat-genome`: genome build (`hg19` or `hg38`)

## Output Structure

```text
output_directory/
├── README.md
├── report.md
├── result.json
├── processed.h5ad
├── figures/
│   ├── cnv_heatmap.png
│   ├── cnv_spatial.png
│   ├── cnv_umap.png                # when X_umap exists
│   ├── cnv_group_sizes.png         # when CNV groups are available
│   ├── cnv_score_distribution.png
│   └── manifest.json
├── figure_data/
│   ├── cnv_scores.csv
│   ├── cnv_run_summary.csv
│   ├── cnv_spatial_points.csv
│   ├── cnv_umap_points.csv         # when X_umap exists
│   ├── cnv_group_sizes.csv         # when CNV groups are available
│   ├── cnv_bin_summary.csv         # inferCNVpy runs
│   ├── numbat_calls.csv            # Numbat runs
│   ├── numbat_clone_post.csv       # Numbat runs
│   └── manifest.json
├── tables/
│   ├── cnv_scores.csv
│   ├── cnv_run_summary.csv
│   ├── cnv_group_sizes.csv         # when CNV groups are available
│   ├── cnv_bin_summary.csv         # inferCNVpy runs
│   ├── numbat_calls.csv            # Numbat runs
│   └── numbat_clone_post.csv       # Numbat runs
└── reproducibility/
    ├── analysis_notebook.ipynb
    ├── commands.sh
    └── r_visualization.sh
```

`README.md` and `reproducibility/analysis_notebook.ipynb` are generated by the
standard OmicsClaw wrapper. Direct script execution produces the skill-native
outputs plus `reproducibility/commands.sh`.

## Visualization Contract

- **Python gallery is canonical**: `figures/manifest.json` describes the
  standard OmicsClaw CNV story for routine analysis delivery.
- **`figure_data/` is the bridge layer**: downstream plotting code should read
  exported CSVs instead of rerunning inferCNVpy or Numbat.
- **R is an optional customization layer**:
  `skills/spatial/spatial-cnv/r_visualization/` contains starter templates that
  consume `figure_data/` and write polished figures under `figures/custom/`.

## Dependencies

**Required (Python)**:

- `scanpy`

**Optional (Python)**:

- `infercnvpy` for expression-based CNV inference

**Optional (R environment / subprocess)**:

- `numbat`
- `SingleCellExperiment`
- `zellkonverter`

## Safety

- **Local-first**: no data upload; all CNV inference remains on the local
  machine.
- **Method-aware matrix usage**: do not pass log-normalized matrices to Numbat
  or raw-count assumptions to inferCNVpy.
- **Reference transparency**: CNV baselines and reference categories must be
  stated explicitly before running.
- **Interpretation caution**: expression-based CNV scores are screening signals,
  not definitive DNA-level segment calls.

## Integration with Orchestrator

**Trigger conditions**:

- copy number variation
- inferCNV / infercnvpy
- Numbat
- tumor clone / chromosomal aberration

**Chaining partners**:

- `spatial-preprocess` for matrix preparation and counts preservation
- `spatial-annotate` for choosing diploid reference categories
- `spatial-genes` for linking CNV programs to spatially variable genes

## Citations

- [inferCNVpy documentation](https://infercnvpy.readthedocs.io/en/latest/generated/infercnvpy.tl.infercnv.html)
- [Numbat spatial RNA tutorial](https://kharchenkolab.github.io/numbat/articles/spatial-rna.html)
- [Numbat reference: `run_numbat`](https://kharchenkolab.github.io/numbat/reference/run_numbat.html)
- [Tirosh et al. 2016](https://doi.org/10.1126/science.aad0501) — expression-based CNV inference in tumors
