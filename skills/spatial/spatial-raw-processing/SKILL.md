---
name: spatial-raw-processing
description: >-
  Process barcoded spatial transcriptomics FASTQ pairs with st_pipeline,
  preserve upstream artifacts, convert the counts matrix into a standardized
  raw_counts.h5ad, and hand off cleanly to spatial-preprocess.
version: 0.1.0
author: OmicsClaw Team
license: MIT
tags: [spatial, raw-processing, fastq, st_pipeline, visium, slideseq, upstream]
metadata:
  omicsclaw:
    domain: spatial
    allowed_extra_flags:
    - "--read1"
    - "--read2"
    - "--ids"
    - "--ref-map"
    - "--ref-annotation"
    - "--exp-name"
    - "--platform"
    - "--threads"
    - "--contaminant-index"
    - "--min-length-qual-trimming"
    - "--min-quality-trimming"
    - "--demultiplexing-mismatches"
    - "--demultiplexing-kmer"
    - "--umi-allowed-mismatches"
    - "--umi-start-position"
    - "--umi-end-position"
    - "--disable-clipping"
    - "--compute-saturation"
    - "--htseq-no-ambiguous"
    - "--transcriptome"
    - "--star-two-pass-mode"
    - "--stpipeline-repo"
    - "--bin-path"
    param_hints:
      st_pipeline:
        priority: "ids/ref_map/ref_annotation -> threads -> compute_saturation ->
          demultiplexing -> umi"
        params: ["read1", "read2", "ids", "ref_map", "ref_annotation", "exp_name",
          "platform", "threads", "compute_saturation", "demultiplexing_mismatches",
          "demultiplexing_kmer", "umi_allowed_mismatches", "umi_start_position", "umi_end_position"]
        defaults: {platform: "visium", threads: 4, min_length_qual_trimming: 20, min_quality_trimming: 20,
          demultiplexing_mismatches: 2, demultiplexing_kmer: 6, umi_allowed_mismatches: 1,
          umi_start_position: 18, umi_end_position: 27}
        requires: ["FASTQ_R1", "FASTQ_R2", "ids_barcode_coordinate_file", "STAR_index_directory",
          "GTF_annotation_or_transcriptome"]
        tips:
        - "--ids / --ref-map / --ref-annotation: these are the core run contract;
          matrix-level inputs should go to spatial-preprocess instead."
        - "--platform: a reporting label only; it does not switch upstream algorithms,
          but it keeps the output contract explicit for Visium, Slide-seq, or custom
          barcode-coordinate assays."
        - "--compute-saturation: enables the upstream saturation curve so the OmicsClaw
          report can summarize sequencing depth sufficiency."
        - "--demultiplexing-mismatches / --demultiplexing-kmer: first tuning knobs
          when barcode recovery is unexpectedly low."
        - "--umi-allowed-mismatches / --umi-start-position / --umi-end-position: only
          adjust if the kit layout differs from the standard assumptions or the upstream
          protocol documents it."
    legacy_aliases: [spatial-raw-fastq-processing, spatial-st-pipeline]
    saves_h5ad: true
    requires_preprocessed: false
    requires:
      bins:
      - python3
      env: []
      config: []
    emoji: "🧬"
    homepage: https://github.com/TianGzlab/OmicsClaw
    os: [macos, linux]
    install:
    - kind: pip
      package: anndata
      bins: []
    trigger_keywords:
    - spatial raw processing
    - raw spatial fastq
    - spatial fastq
    - st_pipeline
    - st pipeline
    - barcode coordinates
    - ids file
    - visium raw fastq
    - slide-seq fastq
    - slideseq fastq
    - upstream spatial processing
    script: spatial_raw_processing.py
---

# 🧬 Spatial Raw Processing

You are **Spatial Raw Processing**, the OmicsClaw skill for turning barcoded
spatial transcriptomics FASTQ pairs into a standardized raw-count AnnData via
`st_pipeline`. This skill sits **upstream** of `spatial-preprocess`: it does
not normalize or cluster the data, it only runs the raw sequencing pipeline,
preserves the upstream artifacts, and packages the resulting count matrix into
`raw_counts.h5ad`.

## Why This Exists

- **Without it**: users must manually run `st_pipeline`, keep track of IDs / STAR index / GTF paths, convert the output TSV into AnnData, and then remember which object should be passed into downstream OmicsClaw skills.
- **With it**: one command preserves the upstream logs, writes `raw_counts.h5ad`, exports a standard gallery and tables, and tells the user exactly how to hand off to `spatial-preprocess`.
- **Why OmicsClaw**: the wrapper standardizes the post-`st_pipeline` object model, report structure, figure-data exports, and downstream routing instead of leaving raw TSV/BED/log files as disconnected artifacts.

## Core Capabilities

1. **FASTQ-to-count-matrix execution**: runs `st_pipeline` on a resolved R1/R2 FASTQ pair with barcode-coordinate metadata.
2. **Input validation**: checks FASTQ pairing, IDs file structure, reference paths, and rejects matrix-level inputs that belong in `spatial-preprocess`.
3. **Standardized AnnData conversion**: converts `<expName>_stdata.tsv` plus the IDs table into `raw_counts.h5ad` with `layers["counts"]`, `raw`, and `obsm["spatial"]`.
4. **Upstream artifact preservation**: keeps logs, stdout/stderr, counts TSV, and BED outputs under `upstream/st_pipeline/`.
5. **Standard visualization layer**: emits a raw-processing gallery with coordinate-level count structure, read attrition, QC distributions, top genes, and optional saturation curves.
6. **Figure-ready exports**: writes `figure_data/` CSVs plus a manifest for downstream customization.
7. **Downstream handoff**: records `spatial-preprocess` as the canonical next step and surfaces the exact handoff path in the report and `result.json`.

## Input Formats

| Format | Extension | Required Fields / Structure | Example |
|--------|-----------|-----------------------------|---------|
| FASTQ pair | `.fastq`, `.fq`, `.fastq.gz`, `.fq.gz` | R1 and R2 from a barcoded spatial assay | `sample_R1.fastq.gz`, `sample_R2.fastq.gz` |
| FASTQ directory | directory | exactly one resolvable FASTQ pair, or use `--read1/--read2` explicitly | `fastq_run/` |
| Run config | `.json`, `.yaml`, `.yml` | keys such as `input`, `ids`, `ref_map`, `ref_annotation`, `exp_name` | `st_run.yaml` |
| Demo | n/a | `--demo` flag | built-in synthetic upstream outputs |

## Data / State Requirements

| Requirement | Where it should exist | Why it matters |
|-------------|------------------------|----------------|
| R1 FASTQ with barcodes / UMI | `--read1` or resolved from `--input` | Required by `st_pipeline` for barcode and UMI parsing |
| R2 FASTQ with transcript sequence | `--read2` or resolved from `--input` | Required by `st_pipeline` for mapping and annotation |
| Barcode-to-coordinate map | `--ids` | Supplies `(BARCODE, X, Y)` so the output matrix can be placed onto spatial coordinates |
| STAR genome index | `--ref-map` | Required by upstream mapping |
| Gene annotation or transcriptome mode | `--ref-annotation` unless `--transcriptome` | Required to assign mapped reads to genes |

Important boundary:

- **Do not** send `.h5ad`, Space Ranger matrix directories, or Xenium exports here. Those are matrix-level inputs and belong in `spatial-preprocess`.
- `spatial-raw-processing` is for **sequencing-level** spatial assays where you still have FASTQ files plus barcode-coordinate metadata.

## Workflow

1. **Load / resolve inputs**: accept explicit `--read1/--read2`, a pair-containing directory, or a JSON/YAML config.
2. **Validate**: reject matrix-level inputs, validate the IDs file structure, and check the reference paths.
3. **Run upstream method**: execute `st_pipeline` or use the OmicsClaw demo path.
4. **Persist upstream artifacts**: keep the counts TSV, BED, logs, stdout/stderr, and run metadata under `upstream/st_pipeline/`.
5. **Convert to AnnData**: write `raw_counts.h5ad` with raw counts in `X`, `layers["counts"]`, `raw`, and `obsm["spatial"]`.
6. **Visualize / summarize**: generate the canonical gallery, export tables, and write `figure_data/`.
7. **Report / handoff**: write native `report.md`, `result.json`, and the reproducibility bundle, then point the user to `spatial-preprocess`; the shared runner adds `README.md`.

## CLI Reference

```bash
# Standard usage with explicit FASTQ paths
oc run spatial-raw-processing \
  --read1 sample_R1.fastq.gz --read2 sample_R2.fastq.gz \
  --ids ids/barcodes.txt --ref-map refs/star_index --ref-annotation refs/genes.gtf \
  --output /tmp/spatial_raw_out

# Resolve the FASTQ pair from an input directory
oc run spatial-raw-processing \
  --input fastq_run/ \
  --ids ids/barcodes.txt --ref-map refs/star_index --ref-annotation refs/genes.gtf \
  --platform visium --output /tmp/spatial_raw_out

# Use a local st_pipeline repository clone instead of a global install
oc run spatial-raw-processing \
  --read1 sample_R1.fastq.gz --read2 sample_R2.fastq.gz \
  --ids ids/barcodes.txt --ref-map refs/star_index --ref-annotation refs/genes.gtf \
  --stpipeline-repo /path/to/st_pipeline \
  --output /tmp/spatial_raw_out

# Enable saturation reporting
oc run spatial-raw-processing \
  --read1 sample_R1.fastq.gz --read2 sample_R2.fastq.gz \
  --ids ids/barcodes.txt --ref-map refs/star_index --ref-annotation refs/genes.gtf \
  --compute-saturation --output /tmp/spatial_raw_out

# Config-driven execution
oc run spatial-raw-processing --input st_run.yaml --output /tmp/spatial_raw_out

# Demo mode
oc run spatial-raw-processing --demo --output /tmp/spatial_raw_demo

# Direct script entrypoint
python skills/spatial/spatial-raw-processing/spatial_raw_processing.py \
  --read1 sample_R1.fastq.gz --read2 sample_R2.fastq.gz \
  --ids ids/barcodes.txt --ref-map refs/star_index --ref-annotation refs/genes.gtf \
  --output /tmp/spatial_raw_out
```

## Example Queries

- "Process these Visium FASTQs with st_pipeline and give me a raw h5ad for downstream analysis."
- "I have spatial transcriptomics FASTQ files plus an IDs barcode-coordinate file. Run the upstream processing first."
- "Use my local st_pipeline checkout to build a raw spatial count object and tell me the next OmicsClaw step."

## Algorithm / Methodology

### `st_pipeline`

1. **FASTQ resolution**: infer or validate the R1/R2 FASTQ pair.
2. **Reference validation**: check the STAR index, annotation, and barcode-coordinate inputs.
3. **Upstream execution**: call `st_pipeline_run` from either an installed package, a PATH binary, or `--stpipeline-repo`.
4. **Artifact preservation**: capture logs, stdout/stderr, the counts matrix TSV, and the transcript BED.
5. **Matrix conversion**: align the counts matrix with the IDs coordinate table and convert it to AnnData.
6. **Raw matrix contract**: store raw counts in `X`, `layers["counts"]`, and `raw` so downstream OmicsClaw preprocessing remains consistent.

**Key parameters**:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `platform` | `visium` | Output/report label only; does not switch algorithms |
| `threads` | `4` | Worker count forwarded to upstream `st_pipeline` |
| `min_length_qual_trimming` | `20` | Upstream read-length filter after quality trimming |
| `min_quality_trimming` | `20` | Upstream base-quality threshold |
| `demultiplexing_mismatches` | `2` | Allowed barcode mismatches during demultiplexing |
| `demultiplexing_kmer` | `6` | Barcode k-mer size used during demultiplexing |
| `umi_allowed_mismatches` | `1` | UMI clustering tolerance |
| `umi_start_position` | `18` | UMI start position in R1 |
| `umi_end_position` | `27` | UMI end position in R1 |
| `compute_saturation` | `False` | Request upstream sequencing saturation summaries |

> **Current OmicsClaw behavior**: the wrapper intentionally exposes only the first-pass tuning knobs most users need. If a run requires deeper upstream control, the preserved upstream metadata makes it clear what was executed and where to rerun custom `st_pipeline` variants.

## Visualization Contract

OmicsClaw treats `spatial-raw-processing` visualization as a layered contract:

1. **Python standard gallery**: canonical raw-processing overview and QC outputs.
2. **Figure-ready exports**: `figure_data/` tables for downstream customization.
3. **Optional R customization layer**: a styling/publication layer that consumes `figure_data/` without rerunning the upstream pipeline.

Current gallery roles include:

- `overview`: coordinate-level raw count structure
- `diagnostic`: upstream read attrition and coordinate-level feature complexity
- `supporting`: raw QC distributions and top detected genes
- `uncertainty`: optional saturation summaries when enabled upstream

## Output Structure

```text
output_directory/
├── README.md
├── report.md
├── result.json
├── raw_counts.h5ad
├── upstream/
│   └── st_pipeline/
│       ├── <expName>_stdata.tsv
│       ├── <expName>_reads.bed
│       ├── <expName>_pipeline.log
│       ├── st_pipeline.stdout.txt
│       ├── st_pipeline.stderr.txt
│       └── omicsclaw_stpipeline_run.json
├── figures/
│   ├── *.png
│   └── manifest.json
├── tables/
│   ├── run_summary.csv
│   ├── stage_summary.csv
│   ├── spot_qc.csv
│   ├── gene_qc.csv
│   └── top_genes.csv
├── figure_data/
│   ├── raw_processing_run_summary.csv
│   ├── stage_summary.csv
│   ├── raw_spot_qc.csv
│   ├── raw_gene_qc.csv
│   ├── raw_top_genes.csv
│   └── manifest.json
├── r_visualization/
│   ├── README.md
│   └── raw_processing_publication_template.R
└── reproducibility/
    ├── analysis_notebook.ipynb
    ├── commands.sh
    ├── requirements.txt
    └── r_visualization.sh
```

### Output Files Explained

- `raw_counts.h5ad`: raw-count handoff object for `spatial-preprocess`.
- `upstream/st_pipeline/`: preserved upstream outputs for auditing or manual reruns.
- `tables/`: complete tabular exports for downstream analysis.
- `figure_data/`: plot-ready CSV exports that mirror the standard gallery.
- `report.md`: explains what was run and how to continue downstream.

## Knowledge Companions

- `knowledge_base/knowhows/KH-spatial-raw-processing-guardrails.md`
- `knowledge_base/skill-guides/spatial/spatial-raw-processing.md`
- `knowledge_base/skill-guides/spatial/spatial-preprocess.md`

Boundary reminder:

- `spatial-raw-processing`: sequencing-level upstream processing
- `spatial-preprocess`: matrix-level QC, normalization, HVG selection, embedding, and clustering

## Dependencies

**Required**:

- Python 3
- `anndata`, `numpy`, `pandas`, `scipy`, `matplotlib`
- `st_pipeline` available on `PATH`, installed as a package, or provided through `--stpipeline-repo`

**Optional but recommended**:

- `Rscript` plus `ggplot2` if you want to use the provided R visualization template
