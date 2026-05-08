---
name: spatial-communication
description: >-
  Cell-cell communication analysis for spatial transcriptomics using LIANA,
  CellPhoneDB, FastCCC, or CellChat, with method-specific parameter hints and
  standardized ligand-receptor outputs.
version: 0.5.0
author: OmicsClaw Team
license: MIT
tags: [spatial, communication, ligand-receptor, liana, cellphonedb, fastccc, cellchat]
metadata:
  omicsclaw:
    domain: spatial
    allowed_extra_flags:
    - "--cell-type-key"
    - "--method"
    - "--species"
    - "--liana-expr-prop"
    - "--liana-min-cells"
    - "--liana-n-perms"
    - "--liana-resource"
    - "--cellphonedb-iterations"
    - "--cellphonedb-threshold"
    - "--fastccc-single-unit-summary"
    - "--fastccc-complex-aggregation"
    - "--fastccc-lr-combination"
    - "--fastccc-min-percentile"
    - "--cellchat-prob-type"
    - "--cellchat-min-cells"
    param_hints:
      liana:
        priority: "liana_resource → liana_expr_prop → liana_min_cells → liana_n_perms"
        params: ["cell_type_key", "species", "liana_resource", "liana_expr_prop",
          "liana_min_cells", "liana_n_perms"]
        defaults: {cell_type_key: "leiden", species: "human", liana_resource: "auto",
          liana_expr_prop: 0.1, liana_min_cells: 5, liana_n_perms: 1000}
        requires: ["X_log_normalized", "obs.cell_type"]
        tips:
        - "--liana-resource: `auto` maps to `consensus` for human and `mouseconsensus`
          for mouse."
        - "--liana-expr-prop: minimum expressing-cell fraction forwarded to `liana.mt.rank_aggregate`."
        - "--liana-min-cells: minimum cells per cell type before LIANA tests interactions."
        - "--liana-n-perms: permutation depth used in LIANA consensus ranking."
      cellphonedb:
        priority: "cellphonedb_threshold → cellphonedb_iterations"
        params: ["cell_type_key", "species", "cellphonedb_threshold", "cellphonedb_iterations"]
        defaults: {cell_type_key: "leiden", species: "human", cellphonedb_threshold: 0.1,
          cellphonedb_iterations: 1000}
        requires: ["X_log_normalized", "obs.cell_type", "human_species", "cellphonedb_database"]
        tips:
        - "--cellphonedb-threshold: minimum fraction of cells expressing each ligand
          or receptor."
        - "--cellphonedb-iterations: label-shuffling iterations in the official statistical
          method."
      fastccc:
        priority: "fastccc_single_unit_summary → fastccc_complex_aggregation → fastccc_lr_combination
          → fastccc_min_percentile"
        params: ["cell_type_key", "species", "fastccc_single_unit_summary", "fastccc_complex_aggregation",
          "fastccc_lr_combination", "fastccc_min_percentile"]
        defaults: {cell_type_key: "leiden", species: "human", fastccc_single_unit_summary: "Mean",
          fastccc_complex_aggregation: "Minimum", fastccc_lr_combination: "Arithmetic",
          fastccc_min_percentile: 0.1}
        requires: ["X_log_normalized", "obs.cell_type", "human_species", "cellphonedb_database"]
        tips:
        - "--fastccc-single-unit-summary: public FastCCC summary statistic, for example
          `Mean`, `Median`, `Q3`, or `Quantile_0.9`."
        - "--fastccc-complex-aggregation: how multi-subunit complexes are summarized
          (`Minimum` or `Average`)."
        - "--fastccc-lr-combination: how ligand and receptor activity are combined
          (`Arithmetic` or `Geometric`)."
        - "--fastccc-min-percentile: minimum expressing-cell fraction used in FastCCC
          filtering."
      cellchat_r:
        priority: "cellchat_prob_type → cellchat_min_cells"
        params: ["cell_type_key", "species", "cellchat_prob_type", "cellchat_min_cells"]
        defaults: {cell_type_key: "leiden", species: "human", cellchat_prob_type: "triMean",
          cellchat_min_cells: 10}
        requires: ["X_log_normalized", "obs.cell_type", "Rscript"]
        tips:
        - "--cellchat-prob-type: forwarded to `computeCommunProb(type=...)`; `triMean`
          is the current OmicsClaw default."
        - "--cellchat-min-cells: forwarded to `filterCommunication(min.cells=...)`."
    legacy_aliases: [communication]
    saves_h5ad: true
    requires_preprocessed: true
    requires:
      bins:
      - python3
      env: []
      config: []
    emoji: "📡"
    homepage: https://github.com/TianGzlab/OmicsClaw
    os: [macos, linux]
    install:
    - kind: pip
      package: scanpy
      bins: []
    trigger_keywords:
    - cell communication
    - cell-cell communication
    - ligand receptor
    - ligand-receptor
    - LIANA
    - CellPhoneDB
    - FastCCC
    - CellChat
    script: spatial_communication.py
---

# 📡 Spatial Communication

You are **Spatial Communication**, the OmicsClaw skill for ligand-receptor
interaction analysis in spatial transcriptomics data. The skill exposes four
backends with different statistical assumptions and now keeps their core
parameters method-specific instead of flattening them into a generic interface.

## Why This Exists

- **Without it**: users often mix up matrix assumptions, species support, and communication scores across LIANA, CellPhoneDB, FastCCC, and CellChat.
- **With it**: one command runs a method-correct communication workflow, exports a standardized LR table, and keeps a reproducible parameter record.
- **Why OmicsClaw**: the wrapper normalizes output structure while still preserving method-specific tuning hints, guardrails, and downstream UX.

## Core Capabilities

1. **LIANA**: multi-method consensus communication ranking through `liana.mt.rank_aggregate`.
2. **CellPhoneDB**: official statistical permutation method with `iterations` and `threshold` controls.
3. **FastCCC**: permutation-free communication analysis through the public `statistical_analysis_method` API.
4. **CellChat (R)**: R-based communication inference with pathway and centrality exports.
5. **Standard Python gallery**: emits a recipe-driven communication gallery with LR overviews, role diagnostics, supporting summaries, and uncertainty panels built on shared `skills/spatial/_lib/viz` primitives.
6. **Standardized LR outputs**: all methods are normalized to the same columns: `ligand`, `receptor`, `source`, `target`, `score`, `pvalue`.
7. **Communication summaries**: exports aggregated source-target communication summaries plus signaling-role classification.
8. **Method-aware reproducibility**: only the parameters relevant to the selected method are written to `reproducibility/commands.sh`.

## Input Formats

| Format | Extension | Required Fields | Example |
|--------|-----------|-----------------|---------|
| AnnData (preprocessed) | `.h5ad` | `X` (log-normalized), `obsm["spatial"]`, `obs["leiden"]` or another cell type column | `processed.h5ad` |

## Input Matrix Convention

Current OmicsClaw `spatial-communication` uses **log-normalized expression in
`adata.X`** for all four backends. Do not pass z-scored or centered matrices.

| Method | Input Matrix | Notes |
|--------|-------------|-------|
| `liana` | `adata.X`; uses `adata.raw` if available | `adata.raw` is treated as the log-normalized full gene space, not raw UMI counts |
| `cellphonedb` | `adata.X` | CellPhoneDB docs explicitly warn against transforms that convert zeros into non-zero values |
| `fastccc` | `adata.X` | Current OmicsClaw wrapper writes the AnnData view to h5ad and runs FastCCC on that matrix |
| `cellchat_r` | `adata.X` | CellChat tutorial expects normalized, log-transformed expression |

## Species Support

Current wrapper support is intentionally method-specific:

| Method | Supported species in current OmicsClaw wrapper |
|--------|-----------------------------------------------|
| `liana` | `human`, `mouse` |
| `cellphonedb` | `human` only |
| `fastccc` | `human` only |
| `cellchat_r` | `human`, `mouse` |

The CLI only exposes `human` and `mouse`. Unsupported combinations fail fast.

## Workflow

1. **Load**: read the preprocessed h5ad and verify the requested cell type column exists.
2. **Validate**: check species support and method-specific parameter ranges.
3. **Run the selected communication backend**.
4. **Standardize outputs**: store a normalized LR results table in `adata.uns["ccc_results"]` and a method-specific result key.
5. **Aggregate**: export source-target communication summaries and signaling roles.
6. **Render**: generate the standard Python communication gallery from shared `plot_communication()` and `plot_features()` building blocks.
7. **Export figure data**: write `figure_data/` CSVs and manifests for optional downstream R-side customization.
8. **Report and export**: write `report.md`, `result.json`, `processed.h5ad`, tables, `figure_data/`, and reproducibility metadata.

## CLI Reference

```bash
# Default OmicsClaw CLI alias
oc run spatial-cell-communication \
  --input <processed.h5ad> --output <report_dir>

# LIANA with method-specific controls
oc run spatial-cell-communication \
  --input <processed.h5ad> --method liana \
  --cell-type-key cell_type --species mouse \
  --liana-resource auto --liana-expr-prop 0.1 --liana-min-cells 10 --liana-n-perms 1000 \
  --output <dir>

# CellPhoneDB statistical method
oc run spatial-cell-communication \
  --input <processed.h5ad> --method cellphonedb \
  --cellphonedb-threshold 0.1 --cellphonedb-iterations 1000 \
  --output <dir>

# FastCCC
oc run spatial-cell-communication \
  --input <processed.h5ad> --method fastccc \
  --fastccc-single-unit-summary Mean \
  --fastccc-complex-aggregation Minimum \
  --fastccc-lr-combination Arithmetic \
  --fastccc-min-percentile 0.1 \
  --output <dir>

# CellChat via R
oc run spatial-cell-communication \
  --input <processed.h5ad> --method cellchat_r \
  --species mouse --cellchat-prob-type triMean --cellchat-min-cells 10 \
  --output <dir>

# Demo mode
oc run spatial-cell-communication --demo --output /tmp/comm_demo

# Direct script entrypoint
python skills/spatial/spatial-communication/spatial_communication.py \
  --input <processed.h5ad> --method liana --output <dir>
```

Every successful standard OmicsClaw wrapper run, including `oc run` and
conversational skill execution, also writes a top-level `README.md` and
`reproducibility/analysis_notebook.ipynb` to make the output directory easier
to inspect and rerun. Direct script execution primarily produces the
skill-native outputs plus `reproducibility/commands.sh`.

## Example Queries

- "Run LIANA on my spatial data and explain the main parameters before running."
- "Use CellPhoneDB for cell-cell communication and tell me why the threshold matters."
- "Try FastCCC first because I want a faster communication screen."
- "Run CellChat on mouse data and export pathway-level communication tables."

## Methodology

### LIANA

- Backend: `liana.mt.rank_aggregate`
- Core wrapper-exposed knobs: `resource_name`, `expr_prop`, `min_cells`, `n_perms`
- Default resource behavior: `auto -> consensus` for human, `auto -> mouseconsensus` for mouse
- Recommended first-pass use: general communication screening when the user wants a robust default

### CellPhoneDB

- Backend: CellPhoneDB official `cpdb_statistical_analysis_method.call`
- Core wrapper-exposed knobs: `iterations`, `threshold`
- Recommended first-pass use: users who explicitly want permutation-backed CellPhoneDB statistics
- Important caveat: current wrapper is human-only for CellPhoneDB

### FastCCC

- Backend: public `fastccc.statistical_analysis_method`
- Core wrapper-exposed knobs: `single_unit_summary`, `complex_aggregation`, `LR_combination`, `min_percentile`
- Recommended first-pass use: faster human communication screening when permutation testing is not required
- Important caveat: current wrapper uses a CellPhoneDB-formatted database resource and is human-only

### CellChat (R)

- Backend: `computeCommunProb` + `filterCommunication` through `sc_cellchat.R`
- Core wrapper-exposed knobs: `type`, `min.cells`
- Recommended first-pass use: pathway-level communication and centrality analysis
- Important caveat: requires an R environment with `CellChat`, `SingleCellExperiment`, and `zellkonverter`

## Output Structure

```text
output_directory/
├── README.md                               # wrapper mode
├── report.md
├── result.json
├── processed.h5ad
├── figures/
│   ├── lr_dotplot.png
│   ├── lr_heatmap.png
│   ├── lr_spatial.png                      # if spatial score layer exists
│   ├── communication_roles_spatial.png
│   ├── communication_hub_umap.png          # or communication_hub_spatial.png
│   ├── signaling_roles.png
│   ├── source_target_summary.png
│   ├── communication_pvalue_distribution.png
│   ├── communication_score_vs_significance.png
│   └── manifest.json
├── figure_data/
│   ├── lr_interactions.csv
│   ├── top_interactions.csv
│   ├── communication_summary.csv
│   ├── signaling_roles.csv
│   ├── source_target_summary.csv
│   ├── communication_run_summary.csv
│   ├── communication_spatial_points.csv
│   ├── communication_umap_points.csv
│   └── manifest.json
├── tables/
│   ├── lr_interactions.csv
│   ├── top_interactions.csv
│   ├── communication_summary.csv
│   ├── signaling_roles.csv
│   ├── source_target_summary.csv
│   ├── cellchat_pathways.csv              # CellChat only
│   ├── cellchat_centrality.csv            # CellChat only
│   ├── cellchat_count_matrix.csv          # CellChat only
│   └── cellchat_weight_matrix.csv         # CellChat only
└── reproducibility/
    ├── analysis_notebook.ipynb            # wrapper mode
    ├── commands.sh
    ├── requirements.txt
    └── r_visualization.sh
```

## Visualization Contract

- **Python gallery is canonical**: `figures/manifest.json` describes the
  standard OmicsClaw communication story for routine analysis delivery.
- **`figure_data/` is the bridge layer**: downstream plotting code should read
  exported CSVs instead of rerunning LIANA, CellPhoneDB, FastCCC, or CellChat.
- **R is an optional customization layer**:
  `skills/spatial/spatial-communication/r_visualization/` contains starter
  templates that consume `figure_data/` and write polished figures under
  `figures/custom/`.

## Dependencies

**Required (Python)**:
- `scanpy`

**Optional (Python)**:
- `liana`
- `cellphonedb`
- `fastccc`

**Optional (R)**:
- `CellChat`
- `SingleCellExperiment`
- `zellkonverter`

## Safety

- **Local-first**: no data upload.
- **Matrix-aware**: do not describe scaled or z-scored matrices as acceptable CellPhoneDB input.
- **Species-aware**: do not silently run unsupported method-species combinations.
- **Audit trail**: preserve the actual method-specific flags that were used.

## Integration with Spatial Orchestrator

**Trigger conditions**:
- Keywords: cell communication, ligand receptor, LIANA, CellPhoneDB, FastCCC, CellChat

**Chaining partners**:
- `spatial-preprocess`: prepares log-normalized AnnData input
- `spatial-annotate`: improves cell type labels before communication analysis
- `spatial-domains`: helps interpret communication within spatial regions

## Citations

- [LIANA+](https://github.com/saezlab/liana-py)
- [CellPhoneDB](https://www.cellphonedb.org/)
- [FastCCC](https://github.com/Svvord/FastCCC)
- [CellChat](https://github.com/jinworks/CellChat)
