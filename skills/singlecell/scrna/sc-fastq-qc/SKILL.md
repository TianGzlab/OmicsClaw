---
name: sc-fastq-qc
description: >-
  Start here if you have raw single-cell FASTQ files. Checks read quality
  before counting with FastQC and MultiQC when available, plus a stable local
  fallback summary.
version: 0.1.0
author: OmicsClaw
license: MIT
tags: [singlecell, scrna, fastq, qc, fastqc, multiqc]
metadata:
  omicsclaw:
    domain: singlecell
    requires:
      bins:
        - python3
      env: []
      config: []
    emoji: "🧪"
    homepage: https://github.com/TianGzlab/OmicsClaw
    os: [macos, linux]
    install:
      - kind: pip
        package: pandas
        bins: []
    trigger_keywords:
      - scRNA FASTQ QC
      - FastQC single-cell
      - MultiQC single-cell
      - raw read quality
      - read-level QC
    allowed_extra_flags:
      - "--max-reads"
      - "--read2"
      - "--sample"
      - "--threads"
    legacy_aliases: [scrna-fastq-qc]
    saves_h5ad: false
    requires_preprocessed: false
    param_hints:
      fastqc:
        priority: "threads -> sample -> read2 -> max_reads"
        params: ["threads", "sample", "read2", "max_reads"]
        defaults: {threads: 4, max_reads: 20000}
        requires: ["fastq_or_fastq_dir"]
        tips:
          - "--threads: forwarded to FastQC when installed, and used for external tool runs."
          - "--sample: choose one sample when the input directory contains multiple FASTQ groups."
          - "--max-reads: Python fallback only samples this many reads per FASTQ for lightweight local summaries."
---

# 🧪 Single-Cell FASTQ QC

You are **SC FASTQ QC**, a specialized OmicsClaw agent for single-cell
RNA-seq raw-read quality assessment before alignment and counting.

## Why This Exists

- **Without it**: users must run FastQC and MultiQC manually, then separately
  inspect read quality before choosing Cell Ranger or STARsolo.
- **With it**: one wrapper produces a stable QC summary, figures, and
  reproducibility bundle from raw FASTQ input.
- **Why OmicsClaw**: it preserves the mainstream FastQC/MultiQC workflow when
  installed, but still writes a local-first Python summary so downstream
  reporting stays stable.

## Core Capabilities

1. **FASTQ discovery**: recognizes single-file or directory-based scRNA FASTQ
   inputs and groups lane-split files by sample.
2. **Mainstream QC backend**: runs FastQC and MultiQC when those tools are
   available.
3. **Stable local fallback**: computes sampled read-level quality summaries even
   when external tools are unavailable.
4. **Standard output layer**: writes canonical figures, summary tables, and
   figure-ready exports under `figure_data/`.
5. **Reproducibility layer**: writes `README.md`, `report.md`, `result.json`,
   and rerun commands.

## Input Formats

| Format | Extension | Required Fields / Structure | Example |
|--------|-----------|-----------------------------|---------|
| FASTQ file | `.fastq`, `.fq`, `.fastq.gz`, `.fq.gz` | one raw read file; pair `--read2` when needed | `sample_R1.fastq.gz` |
| FASTQ directory | directory | one or more lane-split FASTQs with common sample stems | `fastqs/` |
| Demo | n/a | `--demo` flag | built-in synthetic summary |

## Data / State Requirements

| Requirement | Where it should exist | Why it matters |
|-------------|------------------------|----------------|
| Raw reads | input FASTQ file(s) | FastQC and fallback summaries operate on raw reads |
| Stable sample grouping | FASTQ filenames or `--sample` | needed to avoid mixing multiple samples in one report |

## Workflow

1. **Load**: discover FASTQ files and group them into logical samples.
2. **Validate**: ensure the chosen sample exists and paired-end inputs are aligned when requested.
3. **Run method**: execute FastQC and MultiQC when available, and always build a lightweight sampled summary.
4. **Persist results**: write summary tables and figure-ready CSVs.
5. **Visualize / summarize**: generate per-base quality and sample-level overview plots.
6. **Report**: write `README.md`, `report.md`, `result.json`, and the reproducibility bundle.

## CLI Reference

```bash
oc run sc-fastq-qc --input fastqs/ --output results/
oc run sc-fastq-qc --input sample_R1.fastq.gz --read2 sample_R2.fastq.gz --output results/
oc run sc-fastq-qc --input fastqs/ --sample PBMC_1 --threads 8 --output results/
python skills/singlecell/scrna/sc-fastq-qc/sc_fastq_qc.py --demo --output /tmp/sc_fastq_qc_demo
```

## Example Queries

- "先看看这些单细胞 FASTQ 质量怎么样"
- "给我跑 FastQC 和 MultiQC"
- "上游 raw reads 先做个 scRNA FASTQ QC"

## Algorithm / Methodology

### FastQC Wrapper Path

1. **Discover FASTQs**: infer sample groupings from common Illumina naming patterns.
2. **Run FastQC**: call FastQC on all matching FASTQs when the binary is available.
3. **Aggregate with MultiQC**: restrict aggregation to the FastQC module for faster local reports.
4. **Fallback summary**: sample reads directly in Python to keep stable numeric outputs even without external tools.

**Key parameters**:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--threads` | `4` | thread count for external FastQC runs |
| `--sample` | none | choose one sample from a multi-sample FASTQ directory |
| `--read2` | none | explicit mate file when `--input` points to one FASTQ file |
| `--max-reads` | `20000` | per-FASTQ sampling depth for the Python fallback summary |

> **Current OmicsClaw behavior**: FastQC and MultiQC artifacts are optional.
> The wrapper always writes its own summary tables and figures so downstream
> reporting does not depend on external binaries being present.

## Visualization Contract

1. **Python standard gallery**: per-base quality and sample-level quality overview.
2. **Figure-ready exports**: `figure_data/` tables for custom plotting or audit.
3. **Gallery manifest**: `figures/manifest.json` records the standard quick-look QC gallery.

## Output Structure

```text
output_directory/
├── README.md
├── report.md
├── result.json
├── figures/
│   ├── fastq_q30_summary.png
│   └── per_base_quality.png
│   ├── fastq_read_structure.png
│   └── manifest.json
├── tables/
│   ├── fastq_per_file_summary.csv
│   ├── fastq_per_sample_summary.csv
│   └── fastq_per_base_quality.csv
├── figure_data/
│   ├── manifest.json
│   ├── fastq_per_file_summary.csv
│   ├── fastq_per_sample_summary.csv
│   └── fastq_per_base_quality.csv
├── artifacts/
│   ├── fastqc/
│   └── multiqc/
└── reproducibility/
    ├── analysis_notebook.ipynb
    ├── commands.sh
    └── requirements.txt
```

## Reproducibility Contract

- The wrapper records whether FastQC and MultiQC were actually available.
- The Python summary is always emitted so comparative reruns stay possible.

## Knowledge Companions

- `knowledge_base/knowhows/KH-sc-fastq-qc-guardrails.md`: short execution guardrails for scope, input grouping, and interpretation.
- `knowledge_base/skill-guides/singlecell/sc-fastq-qc.md`: longer operator guide for FastQC / MultiQC usage and result interpretation.

## Dependencies

**Required**:

- Python 3
- `pandas`, `numpy`, `matplotlib`

**Optional but recommended**:

- `fastqc`
- `multiqc`

## Environment Management

- Python extras:
  - `pip install -e ".[singlecell-upstream]"`
- External tools that OmicsClaw does **not** auto-install:
  - `fastqc`
  - `multiqc`

Recommended user guidance:

- Do not auto-download these tools during a normal skill run.
- If `fastqc` or `multiqc` is missing, tell the user how to install them in the active environment or on `PATH`.
- For shared lab machines, recommend a dedicated scRNA upstream environment rather than mixing these tools into every OmicsClaw workflow environment.

## Workflow Position

- **Upstream step**: None (this is the first step in the scRNA workflow)
- **Usual next step**: `sc-count` to generate a count matrix from FASTQs
