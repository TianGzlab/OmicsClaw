---
name: sc-count
description: >-
  Default scRNA counting route. Turn FASTQ or existing Cell Ranger, STARsolo,
  SimpleAF / Alevin-fry, or kb-python outputs into a downstream-ready
  standardized AnnData.
version: 0.1.0
author: OmicsClaw
license: MIT
tags: [singlecell, scrna, count, cellranger, starsolo, simpleaf, kb-python, fastq]
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
    - "--backend"
    - "--chemistry"
    - "--method"
    - "--read2"
    - "--reference"
    - "--sample"
    - "--t2g"
    - "--threads"
    - "--whitelist"
    - "--r-enhanced"
    legacy_aliases: [scrna-count, sc-pseudoalign-count, scrna-pseudoalign-count]
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
        - "--sample: choose one sample when the FASTQ directory contains multiple
          groups."
        - "--chemistry auto: current wrapper leaves chemistry auto-detection to Cell
          Ranger by default."
      starsolo:
        priority: "reference -> chemistry -> whitelist -> sample -> threads"
        params: ["reference", "chemistry", "whitelist", "sample", "threads"]
        defaults: {threads: 8}
        requires: ["STAR", "10x_paired_fastq_or_existing_starsolo_output"]
        tips:
        - "--chemistry: current STARsolo wrapper supports `10xv2`, `10xv3`, and `10xv4`
          geometry."
        - "--whitelist: strongly recommended; OmicsClaw only auto-detects common local
          v2/v3 whitelist files."
        - "--reference: must be a STAR genome directory, not a raw FASTA/GTF pair."
      simpleaf:
        priority: "reference -> chemistry -> sample -> threads"
        params: ["reference", "chemistry", "sample", "threads"]
        defaults: {threads: 8, chemistry: "10xv3"}
        requires: ["simpleaf_output_or_fastq"]
        tips:
        - "--reference: current wrapper expects a simpleaf index path."
        - "--chemistry: current wrapper is optimized for mainstream 10x-style droplet
          presets."
      kb_python:
        priority: "reference -> t2g -> chemistry -> sample -> threads"
        params: ["reference", "t2g", "chemistry", "sample", "threads"]
        defaults: {threads: 8, chemistry: "10xv3"}
        requires: ["kb_output_or_fastq"]
        tips:
        - "--reference: current wrapper expects a kallisto index path."
        - "--t2g: required transcript-to-gene map for kb-python runs."
        - "--chemistry: forwarded as kb technology string such as `10xv2`, `10xv3`,
          or `10xv4`."
    script: sc_count.py
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

1. **Four counting backends**: Cell Ranger, STARsolo, SimpleAF / Alevin-fry, and kb-python.
2. **Direct import path**: can also standardize existing backend output directories without rerunning them.
3. **Stable downstream contract**: writes `processed.h5ad` with
   `layers['counts']` and OmicsClaw input-contract metadata.
4. **Standard output layer**: barcode-rank and count-distribution figures plus
   machine-readable tables.
5. **Reproducibility layer**: writes native `report.md`, `result.json`,
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
| Backend reference | `--reference` | required for real backend runs |
| 10x chemistry contract | `--chemistry`, `--whitelist` | required for STARsolo barcode/UMI parsing |
| Transcript-to-gene map | `--t2g` | required for kb-python runs |

## Beginner Setup Hint

If the user is missing reference assets, guide them to either:

1. pass explicit local paths such as `--reference`, `--whitelist`, or `--t2g`
2. or place files under:
   - `resources/singlecell/references/cellranger/`
   - `resources/singlecell/references/starsolo/`
   - `resources/singlecell/references/simpleaf/`
   - `resources/singlecell/references/kb/`
   - `resources/singlecell/references/whitelists/`

Download guidance:

- Cell Ranger reference: official 10x reference release pages
- STARsolo: build a STAR genome directory from a matching FASTA / GTF
- STARsolo whitelist: official 10x Cell Ranger barcode files such as `3M-february-2018.txt`
- kb-python: keep both the kallisto index and the matching `t2g`

## Workflow

1. **Load**: detect whether the input is FASTQ or an existing count-output directory.
2. **Validate**: enforce one chosen sample and backend-specific requirements.
3. **Run method**: launch the selected backend when needed, or import existing outputs directly.
4. **Persist results**: load the filtered matrix, standardize it into the OmicsClaw AnnData contract, and preserve backend artifact paths.
5. **Visualize / summarize**: generate barcode-rank and count-distribution plots plus summary tables.
6. **Report**: write native `report.md`, `result.json`, and the reproducibility bundle; the shared runner adds `README.md`.

## CLI Reference

```bash
oc run sc-count --input fastqs/ --method cellranger --reference /path/to/refdata-gex-GRCh38-2020-A --output results/
oc run sc-count --input fastqs/ --method starsolo --reference /path/to/star_index --chemistry 10xv3 --whitelist /path/to/3M-february-2018.txt --output results/
oc run sc-count --input fastqs/ --method simpleaf --reference /path/to/simpleaf_index --chemistry 10xv3 --output results/
oc run sc-count --input fastqs/ --method kb_python --reference /path/to/kallisto.idx --t2g /path/to/t2g.txt --chemistry 10xv3 --output results/
oc run sc-count --input sample_count/ --method cellranger --output results/
python skills/singlecell/scrna/sc-count/sc_count.py --demo --output /tmp/sc_count_demo
```

## Example Queries

- "把这些单细胞 FASTQ 先跑成 count matrix"
- "用 Cell Ranger 跑 10x 数据然后直接转 h5ad"
- "用 STARsolo 产出能接 OmicsClaw 的 adata"
- "用 simpleaf 跑 10x FASTQ 然后直接转 h5ad"
- "把 kb-python 的输出接到后面的 scRNA 技能"

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

### SimpleAF / Alevin-fry Path

1. **FASTQ grouping or import**: infer one sample or import an existing simpleaf output.
2. **Run backend**: execute `simpleaf quant` when needed.
3. **Import result**: read an existing H5AD or matrix output.
4. **Standardize output**: create the same OmicsClaw count handoff contract.

### kb-python Path

1. **FASTQ grouping or import**: infer one sample or import an existing kb output.
2. **Run backend**: execute `kb count` when needed.
3. **Import result**: read an existing H5AD or matrix output.
4. **Standardize output**: create the same OmicsClaw count handoff contract.

**Key parameters**:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--method` | `cellranger` | choose Cell Ranger, STARsolo, SimpleAF / Alevin-fry, or kb-python |
| `--reference` | none | backend reference directory or index path |
| `--t2g` | none | transcript-to-gene map for kb-python |
| `--sample` | none | choose one sample from a multi-sample FASTQ directory |
| `--threads` | `8` | thread count for backend execution |
| `--chemistry` | `auto` | Cell Ranger auto-detects; STARsolo requires explicit supported chemistry |
| `--whitelist` | none | STARsolo barcode whitelist file |

> **Current OmicsClaw behavior**: all non-Cell Ranger methods are intentionally
> scoped to mainstream 10x-style droplet geometry first. Complex custom
> chemistries remain deferred.

## Visualization Contract

1. **Python standard gallery**: barcode-rank and count-distribution plots.
2. **Figure-ready exports**: count summary and per-barcode tables under
   `figure_data/`.
3. **Gallery manifest**: `figures/manifest.json` records the standard counting gallery.

## Output Structure

```text
output_directory/
├── README.md
├── report.md
├── result.json
├── processed.h5ad
├── figures/
│   ├── barcode_rank.png
│   └── count_distributions.png
│   ├── count_complexity_scatter.png
│   └── manifest.json
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
│   ├── starsolo/
│   ├── simpleaf/
│   └── kb_python/
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

- `knowledge_base/knowhows/KH-sc-count-guardrails.md`: short execution guardrails for import-vs-run decisions and backend boundaries.
- `knowledge_base/skill-guides/singlecell/sc-count.md`: longer operator guide for count-method choice and downstream hand-off.

## Dependencies

**Required**:

- Python 3
- `scanpy`, `anndata`, `pandas`, `numpy`

**Optional but method-specific**:

- `cellranger`
- `STAR`
- `simpleaf`
- `kb`

## Environment Management

- Python extras:
  - `pip install -e ".[singlecell-upstream]"`
- External tools that OmicsClaw does **not** auto-install:
  - `cellranger`
  - `STAR`
  - `simpleaf`
  - `kb`

Recommended user guidance:

- Do not auto-install counting backends during a normal run.
- If a backend binary is missing, prompt the user to install it explicitly in the active environment or module system.
- Reference files are also user-managed resources; OmicsClaw should guide users to `resources/singlecell/references/...` or accept explicit local paths, but should not silently download large references during execution.

## CLI Parameters

| Flag | Type | Default | Description | Validation |
|------|------|---------|-------------|------------|
| `--input` | str | None | FASTQ path or existing Cell Ranger / STARsolo output directory | Required unless `--demo` |
| `--output` | str | — | Output directory | Required |
| `--demo` | flag | off | Run with built-in demo data | — |
| `--method` | str | `cellranger` | Counting backend | Choices: `cellranger`, `starsolo`, `simpleaf`, `kb_python` |
| `--reference` | str | None | Backend reference path (Cell Ranger transcriptome, STAR genome dir, simpleaf index, or kallisto index) | Required for real backend runs |
| `--t2g` | str | None | Transcript-to-gene map for kb-python runs | Required for `kb_python` method |
| `--sample` | str | None | Choose one sample from a multi-sample FASTQ directory | — |
| `--read2` | str | None | Explicit mate FASTQ when `--input` points to one file | — |
| `--threads` | int | 8 | Backend thread count | — |
| `--chemistry` | str | `auto` | Chemistry hint; STARsolo supports `10xv2`, `10xv3`, `10xv4`; Cell Ranger auto-detects | — |
| `--whitelist` | str | None | STARsolo barcode whitelist file | Strongly recommended for STARsolo real runs |
| `--r-enhanced` | flag | off | Accepted for CLI consistency; no R Enhanced plots for this skill | No-op |

## R Enhanced Plots

This skill has **no R Enhanced plots**. The `--r-enhanced` flag is accepted for CLI consistency but produces no additional output.

## Special Requirements

### Reference Files

Each backend requires its own reference assets. OmicsClaw does **not** download references automatically.

| Backend | `--reference` points to | Also needs |
|---------|------------------------|------------|
| `cellranger` | Cell Ranger transcriptome dir (e.g., `refdata-gex-GRCh38-2020-A`) | — |
| `starsolo` | STAR genome directory (built from FASTA + GTF) | `--whitelist` (10x barcode list), `--chemistry` |
| `simpleaf` | simpleaf index directory | `--chemistry` |
| `kb_python` | kallisto index file (`.idx`) | `--t2g` (transcript-to-gene map), `--chemistry` |

Place reference assets under `resources/singlecell/references/<backend>/` for auto-detection, or pass explicit paths via `--reference`.

### Direct Import (No Re-run)

If a Cell Ranger or STARsolo run has already completed, pass the existing output directory as `--input` and omit `--reference`. The wrapper imports the filtered matrix directly without re-running the backend.

```bash
# Cell Ranger — run from FASTQ
python omicsclaw.py run sc-count \
  --input fastqs/ --method cellranger \
  --reference /path/to/refdata-gex-GRCh38-2020-A \
  --output results/

# STARsolo — run from FASTQ
python omicsclaw.py run sc-count \
  --input fastqs/ --method starsolo \
  --reference /path/to/star_index \
  --chemistry 10xv3 \
  --whitelist /path/to/3M-february-2018.txt \
  --output results/

# kb-python — run from FASTQ
python omicsclaw.py run sc-count \
  --input fastqs/ --method kb_python \
  --reference /path/to/kallisto.idx \
  --t2g /path/to/t2g.txt \
  --chemistry 10xv3 \
  --output results/

# Import existing Cell Ranger output
python omicsclaw.py run sc-count \
  --input sample_count/ --method cellranger \
  --output results/
```

## Workflow Position

- **Optional upstream step**: `sc-fastq-qc` for read-level quality assessment before counting
- **Usual next step**: `sc-qc` for quality assessment, or `sc-multi-count` if merging multiple samples
