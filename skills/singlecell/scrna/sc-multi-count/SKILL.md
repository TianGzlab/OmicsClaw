---
name: sc-multi-count
description: >-
  Use this only for Cell Ranger multi, CITE-seq, ADT, or HTO-style multimodal
  10x data. Preserves the multimodal object and also exports an RNA-only handoff.
version: 0.1.0
author: OmicsClaw
license: MIT
tags: [singlecell, scrna, multimodal, cite-seq, hto, cellranger-multi]
metadata:
  omicsclaw:
    domain: singlecell
    requires:
      bins:
        - python3
      env: []
      config: []
    emoji: "🧩"
    homepage: https://github.com/TianGzlab/OmicsClaw
    os: [macos, linux]
    install:
      - kind: pip
        package: scanpy
        bins: []
    trigger_keywords:
      - cellranger multi
      - CITE-seq
      - HTO
      - hashing
      - antibody capture
      - multimodal count
    allowed_extra_flags:
      - "--sample"
      - "--threads"
    legacy_aliases: [scrna-multi-count]
    saves_h5ad: true
    requires_preprocessed: false
    param_hints:
      cellranger_multi:
        priority: "sample -> threads"
        params: ["sample", "threads"]
        defaults: {threads: 8}
        requires: ["cellranger_multi_output_or_config_csv"]
        tips:
          - "--sample: choose one sample from `per_sample_outs/` when the multi run produced per-sample outputs."
          - "--threads: forwarded to `cellranger multi` when the backend is executed for real."
---

# 🧩 Single-Cell Multi Count

You are **SC Multi Count**, a specialized OmicsClaw agent for turning
mainstream 10x multimodal Cell Ranger multi outputs into both a preserved
multimodal AnnData and an RNA-only handoff for the current scRNA stack.

## Why This Exists

- **Without it**: users running CITE-seq or HTO workflows must manually inspect
  `cellranger multi` outputs, decide which matrix to load, and then separately
  derive an RNA-only handoff for downstream scRNA analysis.
- **With it**: one wrapper preserves the multimodal matrix and also exports an
  RNA-only `h5ad` that drops cleanly into existing OmicsClaw scRNA skills.
- **Why OmicsClaw**: it keeps the current downstream RNA-first contract honest
  while preserving multimodal provenance and feature-type information.

## Core Capabilities

1. **Two main entry paths**: import an existing `cellranger multi` output
   directory or execute `cellranger multi` from a config CSV.
2. **Multimodal preservation**: writes `multimodal_standardized_input.h5ad`
   without dropping ADT / HTO features.
3. **RNA handoff**: writes `rna_standardized_input.h5ad` for current scRNA
   downstream skills.
4. **Standard output layer**: modality summary and RNA barcode-rank figures plus
   machine-readable tables.
5. **Reproducibility layer**: writes `README.md`, `report.md`, `result.json`,
   and the rerun bundle.

## Input Formats

| Format | Extension | Required Fields / Structure | Example |
|--------|-----------|-----------------------------|---------|
| Cell Ranger multi config | `.csv` | valid `cellranger multi` config CSV | `config.csv` |
| Cell Ranger multi output | directory | contains `outs/` with filtered matrix and optional `per_sample_outs/` | `run_multi/` |
| Demo | n/a | `--demo` flag | built-in synthetic CITE-seq-like example |

## Data / State Requirements

| Requirement | Where it should exist | Why it matters |
|-------------|------------------------|----------------|
| Cell Ranger multi config or outputs | input path | required to run or import the multimodal matrix |
| Feature-type annotations | `.var['feature_types']` in imported matrix | needed to preserve multimodal content and derive the RNA subset |

## Workflow

1. **Load**: detect whether the input is a config CSV or an existing `cellranger multi` output directory.
2. **Validate**: choose a target sample when importing from `per_sample_outs/`.
3. **Run method**: execute `cellranger multi` when needed, or import outputs directly.
4. **Persist results**: save both multimodal and RNA-only standardized AnnData objects.
5. **Visualize / summarize**: generate modality totals and RNA barcode-rank summaries.
6. **Report**: write `README.md`, `report.md`, `result.json`, and reproducibility artifacts.

## CLI Reference

```bash
oc run sc-multi-count --input config.csv --output results/
oc run sc-multi-count --input run_multi/ --sample PBMC_1 --output results/
python skills/singlecell/scrna/sc-multi-count/sc_multi_count.py --demo --output /tmp/sc_multi_demo
```

## Example Queries

- "把 cellranger multi 的 CITE-seq 输出整理成 h5ad"
- "做一个 HTO / 抗体 capture 的 multimodal handoff"
- "把 multimodal 输出拆成保留全模态和 RNA-only 两个对象"

## Algorithm / Methodology

### Cell Ranger multi Path

1. **Import existing outputs**: detect top-level `outs/` or `per_sample_outs/` and load the filtered feature-barcode matrix.
2. **Or execute backend**: run `cellranger multi` from a config CSV when the binary is available.
3. **Preserve modalities**: keep the full matrix in `multimodal_standardized_input.h5ad`.
4. **Build RNA handoff**: subset `Gene Expression` features into `rna_standardized_input.h5ad`.

**Key parameters**:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--sample` | none | choose one sample from `per_sample_outs/` |
| `--threads` | `8` | thread count for real `cellranger multi` execution |

> **Current OmicsClaw behavior**: this wrapper preserves multimodal outputs but
> current downstream single-cell analysis skills still primarily operate on the
> RNA-only handoff.

## Visualization Contract

1. **Python standard gallery**: feature-type totals and RNA barcode-rank plots.
2. **Figure-ready exports**: `figure_data/` tables for modality totals and RNA
   barcode metrics.

## Output Structure

```text
output_directory/
├── README.md
├── report.md
├── result.json
├── multimodal_standardized_input.h5ad
├── rna_standardized_input.h5ad
├── figures/
│   ├── feature_type_totals.png
│   ├── rna_barcode_rank.png
│   └── rna_count_distributions.png
├── tables/
│   ├── feature_type_summary.csv
│   └── rna_barcode_metrics.csv
├── figure_data/
│   ├── manifest.json
│   ├── feature_type_summary.csv
│   └── rna_barcode_metrics.csv
├── artifacts/
│   └── cellranger_multi/
└── reproducibility/
    ├── analysis_notebook.ipynb
    ├── commands.sh
    └── requirements.txt
```

## Reproducibility Contract

- The multimodal object is preserved without pretending that current downstream
  scRNA skills consume all modalities.
- The RNA-only handoff is the stable bridge to the existing scRNA pipeline.

## Knowledge Companions

- `knowledge_base/knowhows/KH-sc-multi-count-guardrails.md`
- `knowledge_base/skill-guides/singlecell/sc-multi-count.md`

## Dependencies

**Required**:

- Python 3
- `scanpy`, `anndata`, `pandas`, `numpy`

**Optional but method-specific**:

- `cellranger`
