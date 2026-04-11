---
name: sc-velocity-prep
description: >-
  Start here for RNA velocity when you have Cell Ranger BAM, loom, or STARsolo
  Velocyto output. Creates the spliced and unspliced layers needed by scVelo.
version: 0.1.0
author: OmicsClaw
license: MIT
tags: [singlecell, scrna, velocity, velocyto, starsolo, scvelo]
metadata:
  omicsclaw:
    domain: singlecell
    requires:
      bins:
        - python3
      env: []
      config: []
    emoji: "🌀"
    homepage: https://github.com/TianGzlab/OmicsClaw
    os: [macos, linux]
    install:
      - kind: pip
        package: scanpy
        bins: []
    trigger_keywords:
      - RNA velocity prep
      - prepare spliced unspliced layers
      - velocyto
      - starsolo velocyto
      - velocity-ready AnnData
    allowed_extra_flags:
      - "--base-h5ad"
      - "--chemistry"
      - "--gtf"
      - "--method"
      - "--read2"
      - "--reference"
      - "--sample"
      - "--threads"
      - "--whitelist"
    legacy_aliases: [scrna-velocity-prep]
    saves_h5ad: true
    requires_preprocessed: false
    param_hints:
      velocyto:
        priority: "gtf -> base_h5ad -> threads"
        params: ["gtf", "base_h5ad", "threads"]
        defaults: {threads: 4}
        requires: ["cellranger_output_or_loom"]
        tips:
          - "--gtf: required when the wrapper needs to run velocyto from a Cell Ranger BAM."
          - "--base-h5ad: merge spliced/unspliced layers back into an existing OmicsClaw object."
      starsolo:
        priority: "reference -> chemistry -> whitelist -> base_h5ad -> sample -> threads"
        params: ["reference", "chemistry", "whitelist", "base_h5ad", "sample", "threads"]
        defaults: {threads: 8}
        requires: ["starsolo_velocyto_output_or_fastq"]
        tips:
          - "--chemistry: current STARsolo velocity wrapper supports `10xv2`, `10xv3`, and `10xv4` geometry."
          - "--whitelist: strongly recommended for real FASTQ-backed STARsolo runs."
          - "--base-h5ad: merge velocity layers into an existing preprocessed AnnData for direct scVelo use."
---

# 🌀 Single-Cell Velocity Prep

You are **SC Velocity Prep**, a specialized OmicsClaw agent for producing
velocity-ready `spliced` and `unspliced` layers before running `sc-velocity`.

## Why This Exists

- **Without it**: users have BAM files or STARsolo outputs but still need to
  manually convert them into `loom` or `h5ad` objects with velocity layers.
- **With it**: one wrapper creates `velocity_input.h5ad` that is ready for the
  existing `sc-velocity` skill.
- **Why OmicsClaw**: it keeps the heavy upstream extraction step separate from
  scVelo modeling while preserving an AnnData-first downstream contract.

## Core Capabilities

1. **Cell Ranger + velocyto path**: generate a loom file from BAM and barcode
   whitelist, then import it.
2. **STARsolo path**: import existing STARsolo Velocyto matrices or run a
   velocity-oriented STARsolo job from FASTQ.
3. **Optional merge path**: add velocity layers into an existing base `h5ad`.
4. **Standard output layer**: writes `processed.h5ad`, a compatibility alias
   `velocity_input.h5ad`, summary figures, and
   figure-ready exports.
5. **Reproducibility layer**: writes `README.md`, `report.md`, `result.json`,
   and rerun commands.

## Input Formats

| Format | Extension | Required Fields / Structure | Example |
|--------|-----------|-----------------------------|---------|
| Cell Ranger output | directory | contains `outs/possorted_genome_bam.bam` and filtered barcodes | `sample_count/` |
| STARsolo output | directory | contains `Solo.out/Velocyto/...` or `spliced.mtx` / `unspliced.mtx` | `starsolo_pbmc/` |
| Loom | `.loom` | velocyto loom file with spliced/unspliced layers | `sample.loom` |
| FASTQ directory | directory | one paired-end 10x sample plus STAR reference and whitelist | `fastqs/` |
| Demo | n/a | `--demo` flag | built-in synthetic velocity layers |

## Data / State Requirements

| Requirement | Where it should exist | Why it matters |
|-------------|------------------------|----------------|
| Spliced/unspliced source | BAM + GTF, STARsolo Velocyto output, or loom | required to construct RNA velocity layers |
| Optional base object | `--base-h5ad` | useful when velocity layers should be merged back into an existing AnnData |

## Beginner Setup Hint

If the user is missing upstream assets, guide them to either:

1. pass explicit local paths such as `--gtf`, `--reference`, or `--whitelist`
2. or place files under:
   - `resources/singlecell/references/gtf/`
   - `resources/singlecell/references/starsolo/`
   - `resources/singlecell/references/whitelists/`

Beginner rule of thumb:

- for `--method velocyto`, the safest `genes.gtf` is usually the one that matches the reference used during counting
- for `--method starsolo`, users need a STAR genome directory plus the matching barcode whitelist

## Workflow

1. **Load**: detect whether the input is a Cell Ranger directory, STARsolo output, FASTQ input, or loom file.
2. **Validate**: enforce backend-specific prerequisites such as `--gtf`, `--reference`, and whitelist compatibility.
3. **Run method**: execute velocyto or STARsolo when needed, or import existing velocity artifacts directly.
4. **Persist results**: build `spliced`, `unspliced`, `ambiguous`, and `counts` layers and optionally merge them into a base `h5ad`.
5. **Visualize / summarize**: export velocity-layer summaries and top-gene balance tables.
6. **Report**: write `README.md`, `report.md`, `result.json`, and the reproducibility bundle.

## CLI Reference

```bash
oc run sc-velocity-prep --input sample_count/ --method velocyto --gtf genes.gtf --output results/
oc run sc-velocity-prep --input starsolo_pbmc/ --method starsolo --base-h5ad processed.h5ad --output results/
oc run sc-velocity-prep --input fastqs/ --method starsolo --reference /path/to/star_index --chemistry 10xv3 --whitelist /path/to/3M-february-2018.txt --output results/
python skills/singlecell/scrna/sc-velocity-prep/sc_velocity_prep.py --demo --output /tmp/sc_velocity_prep_demo
```

## Example Queries

- "把 Cell Ranger 的 BAM 准备成 scVelo 能吃的对象"
- "从 STARsolo Velocyto 输出生成 h5ad"
- "先做 RNA velocity 的 prep，再跑 scVelo"

## Algorithm / Methodology

### velocyto Path

1. **Detect Cell Ranger artifacts**: locate the BAM and filtered barcodes.
2. **Run velocyto**: generate a loom file from BAM + barcode whitelist + GTF when needed.
3. **Import loom**: load spliced/unspliced layers into AnnData.
4. **Optional merge**: align cells and genes with an existing `--base-h5ad`.

### STARsolo Path

1. **Reuse existing Velocyto output**: import `spliced.mtx` / `unspliced.mtx` when already present.
2. **Or run STARsolo**: execute a velocity-oriented FASTQ run with `--soloFeatures Gene Velocyto`.
3. **Optional merge**: align the imported velocity layers with `--base-h5ad`.

**Key parameters**:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--method` | `velocyto` | choose the Cell Ranger+velocyto path or the STARsolo Velocyto path |
| `--gtf` | none | required when running velocyto from Cell Ranger BAM |
| `--base-h5ad` | none | merge velocity layers into an existing AnnData |
| `--reference` | none | STAR genome directory for FASTQ-backed STARsolo runs |
| `--chemistry` | `auto` | STARsolo FASTQ runs require explicit supported chemistry |
| `--whitelist` | none | STARsolo barcode whitelist file |

> **Current OmicsClaw behavior**: the wrapper keeps velocity extraction
> separate from `sc-velocity`. This stage is about generating layers; the
> downstream modeling still belongs to scVelo in `sc-velocity`.

## Visualization Contract

1. **Python standard gallery**: layer-total summary, top-gene balance, and top-gene stacked layer totals.
2. **Figure-ready exports**: `figure_data/` tables for layer totals and top genes.
3. **Gallery manifest**: `figures/manifest.json` records the standard velocity-prep gallery.

## Output Structure

```text
output_directory/
├── README.md
├── report.md
├── result.json
├── processed.h5ad
├── velocity_input.h5ad
├── figures/
│   ├── velocity_layer_summary.png
│   └── velocity_gene_balance.png
│   ├── velocity_top_genes_stacked.png
│   └── manifest.json
├── tables/
│   ├── velocity_layer_summary.csv
│   └── top_velocity_genes.csv
├── figure_data/
│   ├── manifest.json
│   ├── velocity_layer_summary.csv
│   └── top_velocity_genes.csv
├── artifacts/
│   ├── velocyto/
│   └── starsolo/
└── reproducibility/
    ├── analysis_notebook.ipynb
    ├── commands.sh
    └── requirements.txt
```

## Reproducibility Contract

- The wrapper always writes a velocity-ready `h5ad` even when the source was a
  loom file or an existing STARsolo Velocyto directory.
- If `--base-h5ad` is used, the result is an aligned subset that preserves the
  base object's higher-level metadata wherever possible.

## Knowledge Companions

- `knowledge_base/knowhows/KH-sc-velocity-prep-guardrails.md`: short execution guardrails for source selection and layer-prep boundaries.
- `knowledge_base/skill-guides/singlecell/sc-velocity-prep.md`: longer operator guide for velocyto / STARsolo Velocyto preparation and merge behavior.

## Dependencies

**Required**:

- Python 3
- `scanpy`, `anndata`, `pandas`, `numpy`

**Optional but method-specific**:

- `velocyto`
- `STAR`

## Environment Management

- Python extras:
  - `pip install -e ".[singlecell-velocity]"`
- External tools that OmicsClaw does **not** auto-install:
  - `velocyto`
  - `STAR`

Recommended user guidance:

- Do not auto-install `velocyto` or `STAR` during a skill run.
- If users want BAM-backed or STARsolo-backed velocity preparation, tell them to install these tools explicitly into their active environment and verify they are on `PATH`.
- Large annotation and reference assets such as `genes.gtf` and STAR genome directories should be user-managed under `resources/singlecell/references/...` or provided by explicit local paths.

## Workflow Position

**Upstream:** sc-clustering (plus BAM/loom files for spliced/unspliced counts)
**Downstream:** sc-velocity
