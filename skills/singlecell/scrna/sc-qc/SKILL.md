---
name: sc-qc
description: >-
  Quality control metric calculation and diagnostic visualization for
  single-cell RNA-seq data. Computes library size, detected genes,
  mitochondrial percentage, and ribosomal percentage without filtering cells.
version: 0.2.0
author: OmicsClaw
license: MIT
tags: [singlecell, scrna, qc, quality-control, metrics, visualization]
metadata:
  omicsclaw:
    domain: singlecell
    allowed_extra_flags:
      - "--species"
    param_hints:
      qc_metrics:
        priority: "species"
        params: ["species"]
        defaults: {species: "human"}
        requires: ["count_like_matrix_in_X", "gene_symbols_with_species_prefix_convention"]
        tips:
          - "--species: Wrapper-level control for mitochondrial / ribosomal gene-prefix detection; use `human` for `MT-` / `RP[SL]`, `mouse` for `mt-` / `Rp[sl]`."
          - "Current OmicsClaw implementation exposes one public QC path, `qc_metrics`; it always computes ribosomal percentage in addition to mitochondrial percentage."
          - "This skill is diagnostic-only and does not remove cells or genes."
    saves_h5ad: true
    requires_preprocessed: false
    requires:
      bins:
        - python3
      env: []
      config: []
    emoji: "📊"
    homepage: https://github.com/OmicsClaw/OmicsClaw
    os: [macos, linux]
    install:
      - kind: pip
        package: scanpy
        bins: []
    trigger_keywords:
      - scRNA QC
      - single-cell QC
      - quality control
      - mitochondrial percentage
      - ribosomal percentage
      - QC violin
      - QC scatter
      - n genes per cell
---

# 📊 Single-Cell QC

You are **SC QC**, the OmicsClaw skill for first-pass single-cell RNA-seq
quality assessment. Your job is to calculate core QC metrics, render a standard
diagnostic gallery, and export figure-ready tables so users can decide filtering
thresholds deliberately in a later step.

## Why This Exists

- **Without it**: users jump straight to filtering with vague or tissue-misaligned thresholds
- **With it**: one run produces a stable QC summary, diagnostic plots, and reusable per-cell metric tables
- **Why OmicsClaw**: the wrapper keeps a standard output contract across CLI / bot / chat usage and records analysis metadata back into AnnData for downstream reuse

## Scope Boundary

Current OmicsClaw `sc-qc` exposes **one implemented analysis path**:
`qc_metrics`.

This skill:

1. calculates QC metrics
2. visualizes QC distributions
3. exports per-cell and summary tables
4. saves an AnnData with QC annotations

This skill does **not**:

1. filter cells
2. filter genes
3. perform doublet detection
4. normalize or cluster the data

Use `sc-preprocessing` or another downstream filtering workflow after reviewing
the QC outputs.

## Core Capabilities

1. **QC metric calculation**: `n_genes_by_counts`, `total_counts`, `pct_counts_mt`, optional log metrics, and ribosomal percentage
2. **Species-aware gene tagging**: mitochondrial and ribosomal features are detected from `--species`
3. **Standard Python gallery**: QC violin, scatter, histogram, and highest-expressed-gene panels
4. **Structured figure-data contract**: `figure_data/` exports figure-ready CSVs plus a manifest for downstream plotting or styling
5. **Stable AnnData write-back**: QC metrics are added to `.obs`, marker flags to `.var`, and OmicsClaw analysis metadata to `.uns`
6. **Notebook-friendly reproducibility**: report, structured result JSON, reproducibility shell command, pinned requirements bundle, README, and analysis notebook

## Input Formats

The current wrapper uses `skills.singlecell._lib.io.smart_load(...)`.

| Format | Extension / form | Current wrapper support | Notes |
|--------|------------------|-------------------------|-------|
| AnnData | `.h5ad` | yes | preferred path |
| 10x HDF5 | `.h5` | yes | delegated to shared single-cell loader |
| Loom | `.loom` | yes | delegated to shared single-cell loader |
| Delimited matrix | `.csv`, `.tsv` | yes | interpreted through the shared count-matrix loader |
| 10x directory | directory | yes | delegated to the shared 10x importer |
| Demo | `--demo` | yes | PBMC3k local/example fallback |

### Input Expectations

- The most reliable input is a **raw-count-like matrix in `adata.X`**.
- Gene names should follow the selected species convention closely enough for
  mitochondrial and ribosomal prefix detection to work.
- If gene symbols use a different naming system, explain that QC percentages may
  be underestimated before running.

## Workflow

1. **Load**: read input data with the shared single-cell loader or demo data.
2. **Tag genes**: mark mitochondrial genes in `adata.var["mt"]` and ribosomal genes in `adata.var["ribo"]`.
3. **Calculate metrics**: run Scanpy QC metric calculation and add log-transformed helper columns.
4. **Render standard gallery**: generate the default OmicsClaw QC gallery under `figures/`.
5. **Export figure data and tables**: write stable CSV exports under `figure_data/` and `tables/`.
6. **Write outputs**: save `qc_checked.h5ad`, `report.md`, `result.json`, README, notebook, and reproducibility bundle.

## CLI Reference

```bash
# Basic usage
python skills/singlecell/scrna/sc-qc/sc_qc.py \
  --input <data.h5ad> --output <dir>

# Mouse gene naming convention
python skills/singlecell/scrna/sc-qc/sc_qc.py \
  --input <data.h5ad> --species mouse --output <dir>

# Demo mode
python skills/singlecell/scrna/sc-qc/sc_qc.py \
  --demo --output /tmp/sc_qc_demo

# Via OmicsClaw
oc run sc-qc --input <data.h5ad> --output <dir>
```

## Public Parameters

| Parameter | Default | Type | Role |
|-----------|---------|------|------|
| `--input` | required unless `--demo` | path | input dataset |
| `--output` | required | path | output directory |
| `--demo` | `false` | flag | run built-in demo data |
| `--species` | `human` | enum | wrapper-level control for MT / ribosomal gene-prefix detection |

### Parameter Design Notes

- `--species` is the only public extra flag because the current wrapper exposes
  a single QC path and does not surface thresholding knobs here.
- `calculate_ribo=True` is fixed in the current implementation and is not a
  public CLI parameter.
- Do **not** present `sc-qc` as if users were choosing among multiple QC
  algorithms today. The main decision in current OmicsClaw is how to interpret
  the output, not how to configure many QC backends.

## Algorithm / Methodology

### Implemented Method: `qc_metrics`

Current OmicsClaw `sc-qc` uses Scanpy QC metric calculation with
species-specific feature tagging.

1. **Species-aware feature tagging**
   - `human`: mitochondrial genes start with `MT-`; ribosomal genes match `^RP[SL]`
   - `mouse`: mitochondrial genes start with `mt-`; ribosomal genes match `^Rp[sl]`
2. **Metric calculation**
   - `scanpy.pp.calculate_qc_metrics(..., qc_vars=["mt", "ribo"], percent_top=None, log1p=False, inplace=True)`
3. **Derived helper metrics**
   - `log10_total_counts`
   - `log10_n_genes_by_counts`
4. **Standard gallery renderers**
   - QC violin plots
   - QC scatter plots
   - QC histograms
   - highest expressed genes summary

### Guaranteed Metric Columns After Success

The saved `qc_checked.h5ad` is expected to contain at least:

```text
adata.obs["n_genes_by_counts"]
adata.obs["total_counts"]
adata.obs["pct_counts_mt"]
adata.obs["log10_total_counts"]
adata.obs["log10_n_genes_by_counts"]
```

When ribosomal pattern matching succeeds, the wrapper also writes:

```text
adata.obs["pct_counts_ribo"]
adata.var["ribo"]
```

The feature-tag columns below are written during QC metric setup:

```text
adata.var["mt"]
adata.var["ribo"]
```

OmicsClaw analysis metadata is also persisted in:

```text
adata.uns["omicsclaw_analyses"]
```

## Interpretation Guidance

### Read These Metrics As Diagnostics, Not Hard Laws

- `n_genes_by_counts`: low values often indicate empty droplets or low-complexity cells; very high values may indicate doublets
- `total_counts`: very low values may indicate poor capture; very high values may reflect doublets or highly loaded droplets
- `pct_counts_mt`: elevated mitochondrial percentage often suggests stressed or dying cells, but acceptable ranges vary by tissue
- `pct_counts_ribo`: useful supporting context, especially when translation-heavy cell states dominate

### Practical First-Pass Reading

- **PBMC-like data** often tolerates stricter mitochondrial cutoffs
- **solid tissues / tumors** often require broader tolerance
- **highly metabolic tissues** may show biologically elevated mitochondrial fractions

Do not convert these plots directly into filtering without considering tissue,
chemistry, ambient RNA burden, and expected cell complexity.

## Output Contract

### Stable Files

```text
output_dir/
├── README.md
├── report.md
├── result.json
├── qc_checked.h5ad
├── figures/
│   ├── qc_violin.png
│   ├── qc_scatter.png
│   ├── qc_histograms.png
│   ├── highest_expr_genes.png
│   └── manifest.json
├── figure_data/
│   ├── manifest.json
│   ├── qc_run_summary.csv
│   ├── qc_metrics_summary.csv
│   ├── qc_metrics_per_cell.csv
│   └── highest_expr_genes.csv
├── tables/
│   ├── qc_metrics_summary.csv
│   ├── qc_metrics_per_cell.csv
│   └── highest_expr_genes.csv
└── reproducibility/
    ├── commands.sh
    ├── requirements.txt
    └── analysis_notebook.ipynb
```

### What Users Should Inspect First

1. `report.md`
2. `figures/qc_violin.png` and `figures/qc_scatter.png`
3. `tables/qc_metrics_summary.csv`
4. `tables/qc_metrics_per_cell.csv`
5. `qc_checked.h5ad` for downstream filtering workflows

### Structured Result Contract

`result.json` includes:

- `summary.method = "qc_metrics"`
- `data.params.species`
- `data.effective_params.calculate_ribo = true`
- `data.visualization.recipe_id = "standard-sc-qc-gallery"`
- `data.visualization.available_figure_data`
- top-level summary values such as `n_cells`, `n_genes`, `median_genes`, and `median_counts`

`data.params` records replayable public CLI parameters.
`data.effective_params` records the actual runtime configuration, including
fixed wrapper behavior.

## Visualization Contract

`sc-qc` treats Python plots as the **standard analysis gallery**. The current
recipe roles are:

- `overview`: QC violin plots
- `diagnostic`: QC scatter plots and histograms
- `supporting`: highest expressed genes panel

`figure_data/` is the stable hand-off layer for downstream custom plotting,
including future R-side visualization or user-authored beautification scripts.

## Example Queries

- "Calculate QC metrics for this scRNA-seq dataset"
- "Show me mitochondrial percentage and genes-per-cell distributions"
- "Generate QC violin and scatter plots before filtering"
- "Run single-cell QC and export the per-cell QC table"

## Dependencies

Required core packages:

- `scanpy`
- `anndata`
- `numpy`
- `pandas`
- `matplotlib`

Notebook export additionally depends on the standard OmicsClaw notebook helper
stack when available.

## Safety And Guardrails

- This skill is **diagnostic only** and does not remove cells or genes.
- Species choice affects mitochondrial / ribosomal pattern matching and should
  be stated explicitly before the run.
- If gene symbols do not follow expected human or mouse prefixes, explain that
  percentage estimates may be incomplete.
- For short execution guardrails, see
  `knowledge_base/knowhows/KH-sc-qc-guardrails.md`.
- For longer method and interpretation guidance, see
  `knowledge_base/skill-guides/singlecell/sc-qc.md`.
