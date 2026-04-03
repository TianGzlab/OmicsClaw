---
name: sc-count
description: >-
  Default 10x scRNA counting route. Turn FASTQ or existing Cell Ranger /
  STARsolo outputs into a downstream-ready standardized AnnData.
version: 0.1.0
author: OmicsClaw
license: MIT
tags: [singlecell, scrna, count, cellranger, starsolo, fastq]
metadata:
  omicsclaw:
    domain: singlecell
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
        package: scanpy
        bins: []
    trigger_keywords:
      - Cell Ranger count
      - STARsolo count
      - fastq to adata
      - raw single-cell counting
      - generate count matrix
    allowed_extra_flags:
      - "--chemistry"
      - "--method"
      - "--read2"
      - "--reference"
      - "--sample"
      - "--threads"
      - "--whitelist"
    legacy_aliases: [scrna-count]
    saves_h5ad: true
    requires_preprocessed: false
    param_hints:
      cellranger:
        priority: "reference -> sample -> threads -> chemistry"
        params: ["reference", "sample", "threads", "chemistry"]
        defaults: {threads: 8, chemistry: "auto"}
        requires: ["cellranger", "fastq_dir_or_existing_cellranger_output"]
        tips:
          - "--reference: required Cell Ranger transcriptome reference directory."
          - "--sample: choose one sample when the FASTQ directory contains multiple groups."
          - "--chemistry auto: current wrapper leaves chemistry auto-detection to Cell Ranger by default."
      starsolo:
        priority: "reference -> chemistry -> whitelist -> sample -> threads"
        params: ["reference", "chemistry", "whitelist", "sample", "threads"]
        defaults: {threads: 8}
        requires: ["STAR", "10x_paired_fastq_or_existing_starsolo_output"]
        tips:
          - "--chemistry: current STARsolo wrapper supports `10xv2`, `10xv3`, and `10xv4` geometry."
          - "--whitelist: strongly recommended; OmicsClaw only auto-detects common local v2/v3 whitelist files."
          - "--reference: must be a STAR genome directory, not a raw FASTA/GTF pair."
---

# 🧬 Single-Cell Counting

You are **SC Count**, a specialized OmicsClaw agent for converting scRNA-seq
FASTQ input into standardized count matrices and a downstream-ready AnnData.

## Why This Exists

- **Without it**: users must run Cell Ranger or STARsolo manually, then convert
  outputs again before starting OmicsClaw downstream skills.
- **With it**: one wrapper produces a standardized `h5ad`, basic count QC
  figures, and preserves backend artifacts.
- **Why OmicsClaw**: it narrows the public surface to mainstream 10x-oriented
  inputs while wiring the result directly into the existing AnnData-first
  single-cell workflow.

## Core Capabilities

1. **Two mainstream counting backends**: Cell Ranger and STARsolo.
2. **Direct import path**: can also standardize existing Cell Ranger or
   STARsolo output directories without rerunning the backend.
3. **Stable downstream contract**: writes `standardized_input.h5ad` with
   `layers['counts']` and OmicsClaw input-contract metadata.
4. **Standard output layer**: barcode-rank and count-distribution figures plus
   machine-readable tables.
5. **Reproducibility layer**: writes `README.md`, `report.md`, `result.json`,
   and rerun commands.

## Input Formats

| Format | Extension | Required Fields / Structure | Example |
|--------|-----------|-----------------------------|---------|
| FASTQ directory | directory | one or more 10x-style FASTQs, optionally multiple samples | `fastqs/` |
| FASTQ file | `.fastq.gz` | one mate file plus `--read2` for paired input | `PBMC_R1.fastq.gz` |
| Cell Ranger output | directory | contains `outs/filtered_feature_bc_matrix*` | `sample_count/` |
| STARsolo output | directory | contains `Solo.out/Gene/filtered/` | `starsolo_pbmc/` |
| Demo | n/a | `--demo` flag | built-in PBMC example |

## Data / State Requirements

| Requirement | Where it should exist | Why it matters |
|-------------|------------------------|----------------|
| Raw FASTQs or existing count output | input path | counting requires raw reads or a backend output directory to import |
| Backend reference | `--reference` | required for real Cell Ranger / STARsolo runs |
| 10x chemistry contract | `--chemistry`, `--whitelist` | required for STARsolo barcode/UMI parsing |

## Workflow

1. **Load**: detect whether the input is FASTQ or an existing count-output directory.
2. **Validate**: enforce one chosen sample and backend-specific requirements.
3. **Run method**: launch Cell Ranger or STARsolo when needed, or import existing outputs directly.
4. **Persist results**: load the filtered matrix, standardize it into the OmicsClaw AnnData contract, and preserve backend artifact paths.
5. **Visualize / summarize**: generate barcode-rank and count-distribution plots plus summary tables.
6. **Report**: write `README.md`, `report.md`, `result.json`, and the reproducibility bundle.

## CLI Reference

```bash
oc run sc-count --input fastqs/ --method cellranger --reference /path/to/refdata-gex-GRCh38-2020-A --output results/
oc run sc-count --input fastqs/ --method starsolo --reference /path/to/star_index --chemistry 10xv3 --whitelist /path/to/3M-february-2018.txt --output results/
oc run sc-count --input sample_count/ --method cellranger --output results/
python skills/singlecell/scrna/sc-count/sc_count.py --demo --output /tmp/sc_count_demo
```

## Example Queries

- "把这些单细胞 FASTQ 先跑成 count matrix"
- "用 Cell Ranger 跑 10x 数据然后直接转 h5ad"
- "用 STARsolo 产出能接 OmicsClaw 的 adata"

## Algorithm / Methodology

### Cell Ranger Path

1. **FASTQ grouping**: infer one target sample from the input path.
2. **Run Cell Ranger**: execute `cellranger count` with `--nosecondary` and BAM output kept on.
3. **Import filtered matrix**: load the filtered feature-barcode matrix into AnnData.
4. **Standardize output**: create `layers['counts']`, stabilize names, and record OmicsClaw input-contract metadata.

### STARsolo Path

1. **FASTQ grouping**: infer one target sample from the input path.
2. **Run STARsolo**: execute a 10x-oriented `CB_UMI_Simple` wrapper with EmptyDrops-style cell calling.
3. **Import filtered matrix**: load `Solo.out/Gene/filtered`.
4. **Standardize output**: create `layers['counts']` and record the same OmicsClaw contract as the Cell Ranger path.

**Key parameters**:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--method` | `cellranger` | choose Cell Ranger or STARsolo |
| `--reference` | none | backend reference directory |
| `--sample` | none | choose one sample from a multi-sample FASTQ directory |
| `--threads` | `8` | thread count for backend execution |
| `--chemistry` | `auto` | Cell Ranger auto-detects; STARsolo requires explicit supported chemistry |
| `--whitelist` | none | STARsolo barcode whitelist file |

> **Current OmicsClaw behavior**: STARsolo support is intentionally scoped to
> mainstream 10x-style droplet geometry. Complex custom barcode protocols are
> deferred.

## Visualization Contract

1. **Python standard gallery**: barcode-rank and count-distribution plots.
2. **Figure-ready exports**: count summary and per-barcode tables under
   `figure_data/`.

## Output Structure

```text
output_directory/
├── README.md
├── report.md
├── result.json
├── standardized_input.h5ad
├── figures/
│   ├── barcode_rank.png
│   └── count_distributions.png
├── tables/
│   ├── count_summary.csv
│   ├── barcode_metrics.csv
│   └── backend_summary.csv
├── figure_data/
│   ├── manifest.json
│   ├── count_summary.csv
│   └── barcode_metrics.csv
├── artifacts/
│   ├── cellranger/
│   └── starsolo/
└── reproducibility/
    ├── analysis_notebook.ipynb
    ├── commands.sh
    └── requirements.txt
```

## Reproducibility Contract

- The filtered count matrix is always converted into the OmicsClaw AnnData
  input contract.
- Backend-specific raw outputs remain preserved under `artifacts/` for methods
  such as CellBender or RNA-velocity preparation.

## Knowledge Companions

- `knowledge_base/knowhows/KH-sc-count-guardrails.md`: short execution guardrails for import-vs-run decisions and protocol boundaries.
- `knowledge_base/skill-guides/singlecell/sc-count.md`: longer operator guide for Cell Ranger / STARsolo method choice and downstream hand-off.

## Dependencies

**Required**:

- Python 3
- `scanpy`, `anndata`, `pandas`, `numpy`

**Optional but method-specific**:

- `cellranger`
- `STAR`
