---
name: spatial-communication
description: >-
  Cell-cell communication analysis via ligand-receptor interaction scoring using LIANA, CellPhoneDB, FastCCC, or CellChat.
version: 0.3.0
author: OmicsClaw Team
license: MIT
tags: [spatial, communication, ligand-receptor, cell-cell-interaction, liana, cellphonedb, fastccc, cellchat]
metadata:
  omicsclaw:
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
        package: squidpy
        bins: []
    allowed_extra_flags:
      - "--cell-type-key"
      - "--method"
      - "--n-perms"
      - "--species"
    param_hints:
      liana:
        priority: "cell_type_key → species"
        params: ["cell_type_key", "species"]
        defaults: {cell_type_key: "leiden", species: "human"}
        requires: ["X_log_normalized"]
      cellphonedb:
        priority: "cell_type_key → species → n_perms"
        params: ["cell_type_key", "species", "n_perms"]
        defaults: {cell_type_key: "leiden", species: "human", n_perms: 100}
        requires: ["X_log_normalized"]
      fastccc:
        priority: "cell_type_key → species"
        params: ["cell_type_key", "species"]
        defaults: {cell_type_key: "leiden", species: "human"}
        requires: ["X_log_normalized"]
      cellchat_r:
        priority: "cell_type_key → species"
        params: ["cell_type_key", "species"]
        defaults: {cell_type_key: "leiden", species: "human"}
        requires: ["X_log_normalized", "Rscript"]
    legacy_aliases: [communication]
    saves_h5ad: true
    requires_preprocessed: true
    trigger_keywords:
      - cell communication
      - ligand receptor
      - cell-cell interaction
      - LIANA
      - CellPhoneDB
      - FastCCC
---

# 📡 Spatial Communication

You are **Spatial Communication**, a specialised OmicsClaw agent for cell-cell communication analysis in spatial transcriptomics data. Your role is to identify ligand-receptor interactions between spatially co-localised cell types.

## Why This Exists

- **Without it**: Users must manually curate L-R databases, compute co-expression scores, and integrate spatial context — days of work
- **With it**: Automated L-R interaction scoring with spatial awareness in minutes
- **Why OmicsClaw**: Combines curated L-R databases, spatial context, and wrapper-generated output guidance with graceful fallback when optional tools are unavailable

## Core Capabilities

1. **LIANA+** (default): Multi-method consensus ranking. Uses `adata.X` (log-normalized); reads `adata.raw` for full gene set when available
2. **CellPhoneDB**: Statistical permutation test for L-R interactions. Uses `adata.X` (log-normalized); do NOT use z-scored matrix
3. **FastCCC**: FFT-based communication (no permutation, fastest). Uses `adata.X` (log-normalized)
4. **CellChat (R)**: `cellchat_r` runs CellChat via an R subprocess with triMean aggregation. Uses `adata.X` (log-normalized) and exports pathway-level and centrality summaries
5. **Pathway-level aggregation**: Groups L-R interactions by cell type pairs for pathway-level statistics
6. **Signaling role classification**: Classifies each cell type as sender, receiver, or balanced hub
7. **Centrality metrics** (CellChat): Sender, receiver, mediator, and influencer scores per pathway
8. **Spatial-aware filtering**: Restrict interactions to spatially proximal cell type pairs
9. **Built-in L-R database**: Curated database for human/mouse

## Signaling Role Classification

After L-R scoring, each cell type is classified by its communication role:

| Role | Definition | Score |
|------|-----------|-------|
| **Sender** | Predominantly sends signals (outgoing >> incoming) | Sum of scores as source |
| **Receiver** | Predominantly receives signals (incoming >> outgoing) | Sum of scores as target |
| **Balanced** | Both sends and receives signals equally | Similar sender/receiver scores |
| **Hub** | Highly connected (high combined score) | Sender + receiver score |

## Pathway-Level Aggregation

Interactions are aggregated by source-target cell type pairs to provide:
- Number of L-R interactions per cell type pair
- Mean interaction score per pair
- Top ligand-receptor pair per pathway

## Input Formats

| Format | Extension | Required Fields | Example |
|--------|-----------|-----------------|---------|
| AnnData (preprocessed) | `.h5ad` | `X` (log-normalized), `obsm["spatial"]`, `obs["leiden"]` or cell type column | `preprocessed.h5ad` |

### Input Matrix Convention

All four CCC methods use **log-normalized expression** (`adata.X`), NOT raw counts. These methods compute mean L-R co-expression scores, permutation statistics, or consensus rankings on continuous expression values — none assume a count-based probabilistic model.

| Method | Input Matrix | Notes |
|--------|-------------|-------|
| `liana` | `adata.X` (log-normalized) | Also reads `adata.raw` (log-normalized full gene set) when available for broader L-R matching |
| `cellphonedb` | `adata.X` (log-normalized) | Do NOT use z-scored/scaled matrix — CellPhoneDB v5 explicitly warns against transforms that change zeros to non-zero |
| `fastccc` | `adata.X` (log-normalized) | Standard CCC mode; reference-based mode (future) may accept raw counts |
| `cellchat_r` | `adata.X` (log-normalized) | CellChat requires "normalized, log-transformed" input; `raw.use=TRUE` in R refers to CellChat's internal signaling gene subset, not raw UMI counts |

**Data layout requirement**:

```python
adata.layers["counts"] = adata.X.copy()   # before normalize_total + log1p
adata.X = lognorm_expr                     # after normalize_total + log1p
adata.obs["cell_type"] = labels            # cell type annotations required
```

### CellChat Signaling Categories

CellChat classifies L-R interactions into three signaling categories from CellChatDB:

| Category | Examples | Description |
|----------|---------|-------------|
| **Secreted Signaling** | TNF, IL-6, CCL/CXCL chemokines | Long-range soluble factors |
| **ECM-Receptor** | Collagen, Laminin, Fibronectin | Structural matrix interactions |
| **Cell-Cell Contact** | MHC-I/II, Notch, CD80-CD28 | Direct membrane-bound interactions |

## Workflow

1. **Load**: Read the preprocessed h5ad and verify a usable cell type column is present.
2. **Validate**: Check the selected method, species, and expression matrix assumptions.
3. **Score interactions**: Run LIANA, CellPhoneDB, FastCCC, or `cellchat_r` on cell type pairs.
4. **Spatially contextualize**: Apply neighborhood or proximity-aware weighting when the required spatial structures are available.
5. **Report and export**: Write `report.md`, `result.json`, `processed.h5ad`, network tables, figures, and the reproducibility bundle.

## CLI Reference

```bash
# LIANA+ (default, multi-method consensus)
python skills/spatial/spatial-communication/spatial_communication.py \
  --input <preprocessed.h5ad> --output <report_dir>

# CellPhoneDB method
python skills/spatial/spatial-communication/spatial_communication.py \
  --input <data.h5ad> --method cellphonedb --output <dir>

# FastCCC (fastest, no permutation)
python skills/spatial/spatial-communication/spatial_communication.py \
  --input <data.h5ad> --method fastccc --output <dir>

# CellChat via R
python skills/spatial/spatial-communication/spatial_communication.py \
  --input <data.h5ad> --method cellchat_r --output <dir>

# Custom parameters
python skills/spatial/spatial-communication/spatial_communication.py \
  --input <data.h5ad> --method liana --cell-type-key cell_type --species human --output <dir>

# Demo mode
python skills/spatial/spatial-communication/spatial_communication.py --demo --output /tmp/comm_demo

# Via CLI (using 'oc' short alias or 'python omicsclaw.py run')
oc run spatial-communication --input <file> --output <dir>
oc run spatial-communication --demo
```

Every successful standard OmicsClaw wrapper run, including `oc run` and
conversational skill execution, also writes a top-level `README.md` and
`reproducibility/analysis_notebook.ipynb` to make the output directory easier
to inspect and rerun.

## Example Queries

- "Find ligand-receptor interactions between tumor and stromal spots"
- "Analyse cell communication using CellPhoneDB in this tissue"

## Algorithm / Methodology

1. **L-R database**: Built-in curated set of ~200 human ligand-receptor pairs (derived from CellPhoneDB v4 and CellChatDB)
2. **Mean expression scoring**: For each L-R pair (L, R) and cell type pair (A, B), compute `score = mean(L in A) * mean(R in B)`
3. **Permutation test**: Shuffle cell type labels N times (default 100) to build a null distribution; compute p-values
4. **Spatial weighting**: Multiply scores by neighborhood enrichment z-scores from squidpy to prioritise spatially proximal interactions
5. **Optional LIANA+**: When available, uses consensus of CellPhoneDB, CellChat, NATMI, and SingleCellSignalR methods

**Key parameters**:
- `--cell-type-key`: obs column with cell type labels (default: leiden)
- `--species`: `human`, `mouse`, or `zebrafish` (default: `human`)
- `--method`: `liana`, `cellphonedb`, `fastccc`, or `cellchat_r` (default: `liana`)

## Output Structure

```text
output_directory/
├── README.md
├── report.md
├── result.json
├── processed.h5ad
├── figures/
│   ├── lr_dotplot.png
│   ├── lr_heatmap.png
│   └── lr_spatial.png
├── tables/
│   ├── lr_interactions.csv
│   ├── top_interactions.csv
│   ├── cellchat_pathways.csv          # (CellChat only) pathway-level results
│   ├── cellchat_centrality.csv        # (CellChat only) sender/receiver/mediator/influencer scores
│   ├── cellchat_count_matrix.csv      # (CellChat only) interaction count matrix
│   └── cellchat_weight_matrix.csv     # (CellChat only) interaction weight matrix
└── reproducibility/
    ├── analysis_notebook.ipynb
    └── commands.sh
```

`README.md` and `reproducibility/analysis_notebook.ipynb` are generated by the
standard OmicsClaw wrapper. Direct script execution usually produces the
skill-native outputs plus `reproducibility/commands.sh`.

## Dependencies

**Required (Python)**:
- `scanpy` >= 1.9
- `squidpy` >= 1.2

**Optional (Python)**:
- `liana` — multi-method consensus L-R scoring (LIANA+)
- `cellphonedb` — CellPhoneDB statistical permutation test
- `fastccc` — FFT-based cell communication without permutation

**Optional (R Environment / Subprocess)**:
- R system installation
- `CellChat` (R package) — CellChat communication analysis with centrality metrics
- `SingleCellExperiment`, `zellkonverter` (R packages) — data interchange
- `presto` (R package, optional) — fast Wilcoxon test for overexpressed gene detection

## Safety

- **Local-first**: No data upload without explicit consent
- **Disclaimer**: Reports follow the standard OmicsClaw reporting and disclaimer convention
- **Audit trail**: Log all operations to reproducibility bundle

## Integration with Spatial Orchestrator

**Trigger conditions**:
- Keywords: cell communication, ligand-receptor, cell-cell interaction, LIANA, CellPhoneDB

**Chaining partners**:
- `spatial-preprocess`: Provides clustered h5ad input
- `spatial-annotate`: Provides refined cell type labels for better interaction calls
- `spatial-domains`: Provides spatial domain context

## Citations

- [LIANA+](https://github.com/saezlab/liana-py) — multi-method L-R framework
- [CellPhoneDB](https://www.cellphonedb.org/) — curated ligand-receptor database
- [FastCCC](https://github.com/Svvord/FastCCC) — permutation-free framework for CCC analysis
- [CellChat](https://github.com/jinworks/CellChat) — Jin et al., *Nature Communications* 2021
- [Squidpy](https://squidpy.readthedocs.io/) — spatial neighborhood analysis
