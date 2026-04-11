---
name: sc-multi-count
description: >-
  Merge multiple single-sample scRNA-seq count matrices (from sc-count) into
  one downstream-ready AnnData with sample labels.
version: 0.1.0
author: OmicsClaw
license: MIT
tags: [singlecell, scrna, count, merge, multi-sample, aggregate]
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
      - merge count matrices
      - multi-sample count
      - aggregate samples
      - combine count outputs
      - cellranger aggr alternative
    allowed_extra_flags:
      - "--sample-id"
    legacy_aliases: [scrna-multi-count]
    saves_h5ad: true
    requires_preprocessed: false
    param_hints:
      merge:
        priority: "input (multiple) -> sample-id -> output"
        params: ["input", "sample-id"]
        defaults: {}
        requires: ["two_or_more_processed_h5ad"]
        tips:
          - "--input: repeat for each sample, e.g. --input s1/processed.h5ad --input s2/processed.h5ad"
          - "--sample-id: optional labels; if omitted, derived from directory or file names."
---

# Multi-Sample Count Merge

You are **SC Multi-Count**, a specialized OmicsClaw agent for merging multiple
single-sample scRNA-seq count matrices into one downstream-ready AnnData.

## Why This Exists

- **Without it**: users manually concatenate AnnData objects, handle barcode
  collisions, and lose provenance metadata.
- **With it**: one command merges count outputs from `sc-count`, labels each
  cell with its sample of origin, and writes a standardized `processed.h5ad`.
- **Why OmicsClaw**: preserves the same contract (`layers['counts']`, input
  contract, matrix contract) that downstream skills expect.

## Core Capabilities

1. **Multi-sample merge**: outer-join concatenation with barcode prefixing.
2. **Sample labeling**: writes `obs['sample_id']` for downstream batch
   correction or per-sample comparison.
3. **Stable downstream contract**: writes `processed.h5ad` with
   `layers['counts']` and OmicsClaw input-contract metadata.
4. **Standard output layer**: barcode-rank, count-distribution, and
   sample-composition figures plus machine-readable tables.
5. **Reproducibility layer**: writes `README.md`, `report.md`, `result.json`,
   and rerun commands.

## Input Formats

| Format | Extension | Required Fields / Structure | Example |
|--------|-----------|-----------------------------|---------|
| Multiple H5AD | `.h5ad` | each from `sc-count` output | `--input s1/processed.h5ad --input s2/processed.h5ad` |
| Demo | n/a | `--demo` flag | built-in split of PBMC demo |

## Data / State Requirements

| Requirement | Where it should exist | Why it matters |
|-------------|------------------------|----------------|
| Per-sample count H5AD | `--input` (repeated) | each must be a count-level AnnData |
| Sample labels | `--sample-id` or inferred | needed for `obs['sample_id']` |

## Workflow

1. **Load**: read each input H5AD and tag with sample ID.
2. **Validate**: check at least two inputs; warn on barcode collisions.
3. **Merge**: outer-join concatenation with barcode prefixing to avoid collisions.
4. **Standardize**: create `layers['counts']`, record OmicsClaw contracts.
5. **Visualize**: barcode-rank, count distributions, complexity scatter, sample composition.
6. **Report**: write `report.md`, `result.json`, and reproducibility bundle.
7. **Export**: write `processed.h5ad`.

## CLI Reference

```bash
# Merge two sc-count outputs
oc run sc-multi-count \
  --input sample1/processed.h5ad \
  --input sample2/processed.h5ad \
  --output merged/

# With explicit sample IDs
oc run sc-multi-count \
  --input s1/processed.h5ad --sample-id Patient_A \
  --input s2/processed.h5ad --sample-id Patient_B \
  --output merged/

# Demo mode
python omicsclaw.py run sc-multi-count --demo --output /tmp/sc_multi_count_demo
```

## Example Queries

- "把这两个样本的 count 矩阵合并到一起"
- "merge these two sc-count outputs"
- "多样本计数矩阵合并"

## Algorithm / Methodology

### Merge Path

1. **Load samples**: read each `processed.h5ad`, prefix barcodes with sample ID.
2. **Outer-join concatenation**: union of gene sets, zero-fill for missing genes.
3. **Standardize**: write `layers['counts']`, `adata.raw`, and OmicsClaw contracts.
4. **Quality checks**: detect empty samples, extreme imbalance, zero cells.

**Key parameters**:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--input` | required | path to a `processed.h5ad` (repeat for each sample) |
| `--sample-id` | inferred | explicit sample label (repeat, matching order of `--input`) |

## Visualization Contract

1. **Python standard gallery**: barcode-rank, count distributions, complexity scatter, sample composition.
2. **Figure-ready exports**: barcode metrics and per-sample summary under `figure_data/`.
3. **Gallery manifest**: `figures/manifest.json`.

## Output Structure

```text
output_directory/
├── README.md
├── report.md
├── result.json
├── processed.h5ad
├── standardized_input.h5ad -> processed.h5ad
├── figures/
│   ├── barcode_rank.png
│   ├── count_distributions.png
│   ├── count_complexity_scatter.png
│   ├── sample_composition.png
│   └── manifest.json
├── tables/
│   ├── barcode_metrics.csv
│   └── per_sample_summary.csv
├── figure_data/
│   ├── manifest.json
│   ├── barcode_metrics.csv
│   └── per_sample_summary.csv
└── reproducibility/
    ├── analysis_notebook.ipynb
    ├── commands.sh
    └── requirements.txt
```

## Workflow Position

- **Upstream step**: `sc-count` (run once per sample to produce individual `processed.h5ad` files)
- **Usual next step**: `sc-qc` for quality assessment on the merged object

## Recommended Next Steps

- `sc-qc` or `sc-preprocessing` on the merged `processed.h5ad`.
- `sc-batch-integration` if samples have batch effects.

## Dependencies

**Required**:

- Python 3
- `scanpy`, `anndata`, `pandas`, `numpy`, `matplotlib`
