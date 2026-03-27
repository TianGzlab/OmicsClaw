---
name: spatial-cnv
description: >-
  Copy number variation inference from spatial transcriptomics expression data.
version: 0.2.0
author: OmicsClaw Team
license: MIT
tags: [spatial, CNV, copy number, inferCNV, cancer]
metadata:
  omicsclaw:
    domain: spatial
    allowed_extra_flags:
      - "--method"
      - "--reference-key"
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
    trigger_keywords:
      - copy number variation
      - CNV
      - inferCNV
      - chromosomal aberration
      - cancer clone
---

# 🧫 Spatial CNV

You are **Spatial CNV**, a specialised OmicsClaw agent for inferring copy number variations from spatial transcriptomics data. Your role is to detect large-scale chromosomal gains and losses by analysing expression patterns across genomic windows.

## Why This Exists

- **Without it**: Users need to set up inferCNV/Numbat pipelines with gene position annotations manually
- **With it**: Automated CNV scoring with built-in chromosome arm gene annotations
- **Why OmicsClaw**: Combines CNV inference with spatial mapping to identify tumour vs stroma regions

## Workflow

1. **Calculate**: Map genes to chromosomal positions using built-in annotation.
2. **Execute**: Run expression smoothing and compute reference baseline.
3. **Assess**: Flag arms with |z-score| > 1.5 as potential gains/losses.
4. **Generate**: Overlay CNV scores on spatial coordinates.
5. **Report**: Tabulate key chromosomal aberrations and save matrices.

## Core Capabilities

1. **inferCNVpy** (default): Expression-based CNV inference. Uses `adata.X` (log-normalized) to compute log-fold-change vs reference cells
2. **Numbat**: Haplotype-aware CNV analysis via R. Uses `adata.layers["counts"]` (raw integer UMI counts) plus allele counts
3. **Built-in gene positions**: Curated human gene → chromosome arm mapping
4. **Spatial CNV mapping**: Overlay CNV scores on spatial coordinates

## Input Formats

| Format | Extension | Required Fields | Example |
|--------|-----------|-----------------|---------|
| AnnData (preprocessed) | `.h5ad` | `X` (normalised), `layers["counts"]` (raw), `obsm["spatial"]`, gene positions in `var` | `preprocessed.h5ad` |

### Input Matrix Convention

The two CNV methods have fundamentally different statistical approaches:

| Method | Input Matrix | Rationale |
|--------|-------------|-----------|
| `infercnvpy` | `adata.X` (log-normalized) | Subtracts reference expression in log-space (log-fold-change); method explicitly requires normalized, log-transformed input |
| `numbat` | `adata.layers["counts"]` (raw integer UMI) | Count-based haplotype-aware model; explicitly requires gene-by-cell integer UMI count matrix |

**Core principle**: inferCNVpy looks at *log-expression shifts* so needs log-normalized data; Numbat does *count-based CNV modeling* so needs raw counts.

**Numbat additional inputs** (beyond expression counts):
- Allele counts DataFrame (`adata.obsm["allele_counts"]`): phased allele counts from `pileup_and_phase.R` with columns cell/snp_id/CHROM/POS/AD/DP/GT/gene
- Optional normalized reference expression (`lambdas_ref`): gene x cell_type matrix (raw counts / total counts)

**Data layout requirement**:

```python
adata.layers["counts"] = adata.X.copy()   # before normalize_total + log1p
adata.X = lognorm_expr                     # after normalize_total + log1p
```

If `layers["counts"]` is missing, Numbat falls back to `adata.raw` (if available) or `adata.X` with a warning.

## CLI Reference

```bash
# inferCNVpy (default)
python skills/spatial/spatial-cnv/spatial_cnv.py \
  --input <preprocessed.h5ad> --output <report_dir>

# With reference cells
python skills/spatial/spatial-cnv/spatial_cnv.py \
  --input <data.h5ad> --method infercnvpy --reference-key cell_type --reference-cat Normal --output <dir>

# Numbat (R-based, haplotype-aware)
python skills/spatial/spatial-cnv/spatial_cnv.py \
  --input <data.h5ad> --method numbat --output <dir>

# Demo mode
python skills/spatial/spatial-cnv/spatial_cnv.py --demo --output /tmp/cnv_demo

# Via CLI (using 'oc' short alias or 'python omicsclaw.py run')
oc run spatial-cnv --input <file> --output <dir>
oc run spatial-cnv --demo
```

## Example Queries

- "Infer copy number variation on my dataset"
- "Detect tumour regions using inferCNV logic"

## Algorithm / Methodology

### inferCNVpy (default)

1. **Input**: `adata.X` (log-normalized expression)
2. **Gene ordering**: Map genes to chromosomal positions using built-in annotation
3. **Expression smoothing**: Compute running mean expression across ordered genes within each chromosome arm (window=100 genes)
4. **Reference baseline**: Subtract mean expression of reference cells (normal/stroma) in log-space to get relative CNV signal (log-fold-change)
5. **Chromosome arm scoring**: Aggregate per-cell scores for each chromosome arm (1p, 1q, ..., 22q, Xp, Xq)
6. **CNV classification**: Flag arms with |z-score| > 1.5 as potential gains/losses

### Numbat

1. **Input**: `adata.layers["counts"]` (raw integer UMI counts) + allele counts
2. **Haplotype integration**: Combines expression-level and allele-level evidence for CNV calls
3. **Count model**: Uses integer UMI counts directly (not log-normalized) for its generative model
4. **Joint inference**: Simultaneously infers CNV segments, tumor clones, and clone phylogeny

## Output Structure

```
output_directory/
├── report.md
├── result.json
├── processed.h5ad
├── figures/
│   ├── cnv_heatmap.png
│   └── cnv_spatial.png
├── tables/
│   ├── cnv_scores.csv
│   └── chromosome_summary.csv
└── reproducibility/
    ├── commands.sh
    ├── requirements.txt
    └── checksums.sha256
```

## Dependencies

**Required (Python)**:
- `scanpy` >= 1.9

**Optional (Python)**:
- `infercnvpy` — expression-based CNV inference

**Optional (R Environment / Subprocess)**:
- R system installation
- `numbat` (R package) — haplotype-aware CNV inference
- `SingleCellExperiment`, `zellkonverter` (R packages) — data interchange

## Safety

- **Local-first**: Strict offline processing without external upload.
- **Disclaimer**: Requires OmicsClaw reporting structures and disclaimers.
- **Audit trail**: Hyperparameters and operational flow states are logged fully.

## Integration with Orchestrator

**Trigger conditions**:
- Automatically invoked dynamically based on tool metadata and user intent matching.

**Chaining partners**:
- `spatial-preprocess` — QC before operation
- `spatial-annotate` — Use annotations to specify normal reference cells

## Citations

- [inferCNVpy](https://github.com/icbi-lab/infercnvpy) — Python inferCNV for single-cell/spatial data
- [Numbat](https://github.com/kharchenkolab/numbat) — Haplotype-aware CNV analysis from scRNA-seq
- [Tirosh et al. 2016](https://doi.org/10.1126/science.aad0501) — Expression-based CNV inference in tumors
