---
name: sc-pseudoalign-count
description: >-
  Alternative counting route if you explicitly want SimpleAF / Alevin-fry or
  kb-python instead of Cell Ranger / STARsolo, with the same standardized AnnData handoff.
version: 0.1.0
author: OmicsClaw
license: MIT
tags: [singlecell, scrna, pseudoalignment, simpleaf, alevin-fry, kb-python]
metadata:
  omicsclaw:
    domain: singlecell
    requires:
      bins:
        - python3
      env: []
      config: []
    emoji: "⚡"
    homepage: https://github.com/TianGzlab/OmicsClaw
    os: [macos, linux]
    install:
      - kind: pip
        package: scanpy
        bins: []
    trigger_keywords:
      - simpleaf
      - alevin-fry
      - kb-python
      - kallisto bustools
      - pseudoalign count
    allowed_extra_flags:
      - "--chemistry"
      - "--method"
      - "--read2"
      - "--reference"
      - "--sample"
      - "--t2g"
      - "--threads"
    legacy_aliases: [scrna-pseudoalign-count]
    saves_h5ad: true
    requires_preprocessed: false
    param_hints:
      simpleaf:
        priority: "reference -> chemistry -> sample -> threads"
        params: ["reference", "chemistry", "sample", "threads"]
        defaults: {threads: 8, chemistry: "10xv3"}
        requires: ["simpleaf_output_or_fastq"]
        tips:
          - "--reference: current wrapper expects a simpleaf index path."
          - "--chemistry: current wrapper is optimized for mainstream 10x-style droplet presets."
      kb_python:
        priority: "reference -> t2g -> chemistry -> sample -> threads"
        params: ["reference", "t2g", "chemistry", "sample", "threads"]
        defaults: {threads: 8, chemistry: "10xv3"}
        requires: ["kb_output_or_fastq"]
        tips:
          - "--reference: current wrapper expects a kallisto index path."
          - "--t2g: required transcript-to-gene map for kb-python runs."
          - "--chemistry: forwarded as kb technology string, e.g. `10xv2`, `10xv3`, `10xv4`."
---

# ⚡ Single-Cell Pseudoalign Count

You are **SC Pseudoalign Count**, a specialized OmicsClaw agent for converting
mainstream pseudoalignment outputs from SimpleAF / Alevin-fry or kb-python into
the same downstream-ready AnnData contract used by the rest of the scRNA stack.

## Why This Exists

- **Without it**: users who prefer pseudoalignment backends must manually
  convert outputs into a stable `h5ad` before entering OmicsClaw.
- **With it**: one wrapper can run or import the backend and immediately export
  `standardized_input.h5ad`.
- **Why OmicsClaw**: it gives pseudoalignment users the same handoff contract as
  `sc-count` without pretending every chemistry and protocol is already covered.

## Core Capabilities

1. **Two mainstream pseudoalignment backends**: SimpleAF / Alevin-fry and kb-python.
2. **Import path**: load existing backend result directories when they already
   contain an importable `h5ad` or matrix-market output.
3. **Stable downstream contract**: writes `standardized_input.h5ad` with
   `layers['counts']` and OmicsClaw input-contract metadata.
4. **Standard output layer**: barcode-rank and count-distribution plots plus
   summary tables.
5. **Reproducibility layer**: writes `README.md`, `report.md`, `result.json`,
   and rerun commands.

## Input Formats

| Format | Extension | Required Fields / Structure | Example |
|--------|-----------|-----------------------------|---------|
| FASTQ directory | directory | one paired-end 10x-style sample or `--sample` selection | `fastqs/` |
| FASTQ file | `.fastq.gz` | one mate file plus `--read2` | `PBMC_R1.fastq.gz` |
| Existing simpleaf output | directory or `.h5ad` | importable `h5ad` or matrix-market result | `simpleaf_run/` |
| Existing kb output | directory or `.h5ad` | importable `h5ad` or matrix-market result | `kb_run/` |
| Demo | n/a | `--demo` flag | built-in PBMC example |

## Data / State Requirements

| Requirement | Where it should exist | Why it matters |
|-------------|------------------------|----------------|
| FASTQ or existing backend output | input path | pseudoalignment requires raw reads or an importable result directory |
| Backend index | `--reference` | required for real simpleaf or kb-python runs |
| t2g map for kb-python | `--t2g` | required for real kb-python runs |

## Workflow

1. **Load**: detect whether the input is an existing backend output or raw FASTQ.
2. **Validate**: choose one sample when the FASTQ directory contains multiple groups.
3. **Run method**: execute SimpleAF or kb-python when needed, or import existing outputs directly.
4. **Persist results**: standardize the resulting counts into `standardized_input.h5ad`.
5. **Visualize / summarize**: generate barcode-rank and count-distribution plots plus stable tables.
6. **Report**: write `README.md`, `report.md`, `result.json`, and the reproducibility bundle.

## CLI Reference

```bash
oc run sc-pseudoalign-count --input fastqs/ --method simpleaf --reference /path/to/simpleaf_index --chemistry 10xv3 --output results/
oc run sc-pseudoalign-count --input fastqs/ --method kb_python --reference /path/to/kallisto.idx --t2g /path/to/t2g.txt --chemistry 10xv3 --output results/
oc run sc-pseudoalign-count --input simpleaf_run/ --method simpleaf --output results/
python skills/singlecell/scrna/sc-pseudoalign-count/sc_pseudoalign_count.py --demo --output /tmp/sc_pseudoalign_demo
```

## Example Queries

- "用 simpleaf 跑 10x FASTQ 然后转成 OmicsClaw 的 h5ad"
- "把 kb-python 的输出接到后面的 scRNA 技能"
- "给我一个 pseudoalign 路线的 count handoff"

## Algorithm / Methodology

### SimpleAF Path

1. **Import existing outputs** when an `h5ad` or importable matrix is already available.
2. **Or execute backend** with `simpleaf quant` from FASTQ plus chemistry and index.
3. **Standardize output** into `standardized_input.h5ad`.

### kb-python Path

1. **Import existing outputs** when an `h5ad` or importable matrix is already available.
2. **Or execute backend** with `kb count` from FASTQ plus kallisto index and `t2g`.
3. **Standardize output** into the same AnnData contract.

**Key parameters**:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--method` | `simpleaf` | choose SimpleAF / Alevin-fry or kb-python |
| `--reference` | none | simpleaf index or kallisto index path |
| `--t2g` | none | transcript-to-gene map for kb-python |
| `--chemistry` | `10xv3` | backend chemistry / technology hint |
| `--sample` | none | choose one sample from a multi-sample FASTQ directory |
| `--threads` | `8` | backend thread count |

> **Current OmicsClaw behavior**: this wrapper is intentionally scoped to the
> mainstream 10x-style droplet path first. It does not pretend to cover every
> custom chemistry or protocol combination exposed by upstream tools.

## Visualization Contract

1. **Python standard gallery**: barcode-rank and count-distribution plots.
2. **Figure-ready exports**: `figure_data/` tables for count summary and
   barcode metrics.

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
│   └── barcode_metrics.csv
├── figure_data/
│   ├── manifest.json
│   ├── count_summary.csv
│   └── barcode_metrics.csv
├── artifacts/
│   ├── simpleaf/
│   └── kb_python/
└── reproducibility/
    ├── analysis_notebook.ipynb
    ├── commands.sh
    └── requirements.txt
```

## Reproducibility Contract

- The wrapper always exports a standard AnnData handoff for downstream scRNA skills.
- Backend-specific artifacts remain preserved for auditability and reruns.

## Knowledge Companions

- `knowledge_base/knowhows/KH-sc-pseudoalign-count-guardrails.md`
- `knowledge_base/skill-guides/singlecell/sc-pseudoalign-count.md`

## Dependencies

**Required**:

- Python 3
- `scanpy`, `anndata`, `pandas`, `numpy`

**Optional but method-specific**:

- `simpleaf`
- `kb`
