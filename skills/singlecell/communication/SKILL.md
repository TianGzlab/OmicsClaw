---
name: sc-communication
description: >-
  Cell-cell communication analysis via ligand-receptor interaction scoring
  using CellChat (R), NicheNet (R), LIANA (Python), or built-in L-R database.
version: 0.1.0
author: OmicsClaw
license: MIT
tags: [singlecell, communication, ligand-receptor, CellPhoneDB, LIANA, NicheNet, CellChat]
metadata:
  omicsclaw:
    domain: singlecell
    requires:
      bins:
        - python3
      env: []
      config: []
    emoji: "📡"
    homepage: https://github.com/OmicsClaw/OmicsClaw
    os: [macos, linux]
    install:
      - kind: pip
        package: scanpy
        bins: []
    trigger_keywords:
      - cell communication
      - ligand receptor
      - cell-cell interaction
      - LIANA
      - CellPhoneDB
      - NicheNet
      - CellChat
---

# 📡 Single-Cell Cell-Cell Communication

You are **SC Communication**, a specialised OmicsClaw agent for cell-cell communication analysis via ligand-receptor interaction scoring.

## Why This Exists

- **Without it**: Manually curating L-R databases and computing interaction scores is complex and error-prone
- **With it**: Automated L-R scoring with permutation-based statistics and optional LIANA+ consensus
- **Why OmicsClaw**: Built-in L-R database with graceful fallback when advanced tools are unavailable

## Core Capabilities

1. **CellChat** (R): Curated multi-subunit L-R database with triMean communication probability
2. **NicheNet** (R): Ligand activity analysis predicting target gene programs in receiver cells
3. **LIANA** (Python): Multi-method consensus scoring (CellPhoneDB, CellChat, NATMI, SingleCellSignalR)
4. **Built-in L-R scoring**: Mean-expression product + permutation test for quick analysis

## Workflow

1. **Calculate**: Evaluate transcript profiles over all subsets.
2. **Execute**: Quantify predicted ligand-receptor associations per permutation logic.
3. **Assess**: Generate interaction values using consensus or database structures.
4. **Visualise**: Chart node-circle plots bridging diverse phenotypes.
5. **Report**: Provide actionable predictions and strength matrix.

## CLI Reference

```bash
python skills/singlecell/communication/sc_communication.py \
  --input <processed.h5ad> --output <dir>
python omicsclaw.py run sc-communication --demo
```

## Algorithm / Methodology

### CellChat (R)

**Goal:** Infer and quantify intercellular communication networks from scRNA-seq data using curated ligand-receptor databases.

**Approach:** Create a CellChat object with cell type labels, select a signaling database, identify overexpressed ligands/receptors, compute communication probabilities, and aggregate into pathway-level networks.

```r
library(CellChat)
library(Seurat)

# Create CellChat object from Seurat
cellchat <- createCellChat(object = seurat_obj, group.by = 'cell_type')

# Set ligand-receptor database
CellChatDB <- CellChatDB.human  # or CellChatDB.mouse
cellchat@DB <- CellChatDB

# Subset to secreted signaling (optional)
CellChatDB.use <- subsetDB(CellChatDB, search = 'Secreted Signaling')
cellchat@DB <- CellChatDB.use

# Preprocessing
cellchat <- subsetData(cellchat)
cellchat <- identifyOverExpressedGenes(cellchat)
cellchat <- identifyOverExpressedInteractions(cellchat)

# Compute communication probability
cellchat <- computeCommunProb(cellchat, type = 'triMean')
cellchat <- filterCommunication(cellchat, min.cells = 10)

# Infer signaling pathways
cellchat <- computeCommunProbPathway(cellchat)
cellchat <- aggregateNet(cellchat)
```

#### CellChat Visualization

```r
# Network plots
netVisual_circle(cellchat@net$count, vertex.weight = groupSize, weight.scale = TRUE,
                 label.edge = FALSE, title.name = 'Number of interactions')

# Heatmap of interactions
netVisual_heatmap(cellchat, color.heatmap = 'Reds')

# Specific pathway visualization
netVisual_aggregate(cellchat, signaling = 'WNT', layout = 'circle')
netVisual_aggregate(cellchat, signaling = 'WNT', layout = 'chord')

# Bubble plot
netVisual_bubble(cellchat, sources.use = c(1, 2), targets.use = c(3, 4),
                 remove.isolate = FALSE)
```

#### Compare Conditions

```r
# Create separate CellChat objects per condition
cellchat_ctrl <- createCellChat(subset(seurat_obj, condition == 'control'), group.by = 'cell_type')
cellchat_treat <- createCellChat(subset(seurat_obj, condition == 'treatment'), group.by = 'cell_type')

# Merge for comparison
cellchat_list <- list(Control = cellchat_ctrl, Treatment = cellchat_treat)
cellchat_merged <- mergeCellChat(cellchat_list, add.names = names(cellchat_list))

# Differential interactions
netVisual_diffInteraction(cellchat_merged, weight.scale = TRUE)
rankNet(cellchat_merged, mode = 'comparison', stacked = TRUE)
```

### NicheNet (R)

**Goal:** Predict which ligands from sender cells drive gene expression changes in receiver cells.

```r
library(nichenetr)
library(Seurat)
library(tidyverse)

# Load NicheNet databases
ligand_target_matrix <- readRDS('ligand_target_matrix.rds')
lr_network <- readRDS('lr_network.rds')

# Define sender and receiver cells
sender_celltypes <- c('Macrophage', 'Dendritic')
receiver <- 'T_cell'

# Get expressed genes
expressed_genes_sender <- get_expressed_genes(sender_celltypes, seurat_obj, pct = 0.10)
expressed_genes_receiver <- get_expressed_genes(receiver, seurat_obj, pct = 0.10)

# Define gene set of interest (e.g., DE genes in receiver)
geneset_oi <- FindMarkers(seurat_obj, ident.1 = 'activated_T', ident.2 = 'naive_T') %>%
    filter(p_val_adj < 0.05, avg_log2FC > 0.5) %>% rownames()

# Define potential ligands
ligands <- lr_network %>% pull(from) %>% unique()
expressed_ligands <- intersect(ligands, expressed_genes_sender)
receptors <- lr_network %>% pull(to) %>% unique()
expressed_receptors <- intersect(receptors, expressed_genes_receiver)

potential_ligands <- lr_network %>%
    filter(from %in% expressed_ligands & to %in% expressed_receptors) %>%
    pull(from) %>% unique()

# NicheNet ligand activity analysis
ligand_activities <- predict_ligand_activities(
    geneset = geneset_oi,
    background_expressed_genes = expressed_genes_receiver,
    ligand_target_matrix = ligand_target_matrix,
    potential_ligands = potential_ligands
)

# Top ligands
best_ligands <- ligand_activities %>% top_n(20, pearson) %>% arrange(-pearson) %>% pull(test_ligand)
```

### LIANA (Python)

**Goal:** Run multiple L-R interaction methods and aggregate results for robust consensus scoring.

```python
import liana as li
import scanpy as sc

adata = sc.read_h5ad('adata.h5ad')

# Run LIANA with multiple methods
li.mt.rank_aggregate(adata, groupby='cell_type', resource_name='consensus',
                     expr_prop=0.1, verbose=True)

# Get results
liana_results = adata.uns['liana_res']

# Filter significant interactions
sig_interactions = liana_results[liana_results['liana_rank'] < 0.01]

# Visualize
li.pl.dotplot(adata, colour='magnitude_rank', size='specificity_rank',
              source_groups=['Macrophage'], target_groups=['T_cell'])
```

#### LIANA with Tensor Decomposition

```python
# Multi-sample/condition analysis
li.mt.rank_aggregate(adata, groupby='cell_type', resource_name='consensus',
                     use_raw=False, verbose=True)

# Build tensor for decomposition
li.multi.build_tensor(adata, sample_key='sample', groupby='cell_type',
                      ligand_key='ligand_complex', receptor_key='receptor_complex')

# Run tensor decomposition
li.multi.decompose_tensor(adata, n_components=5)

# Visualize factor loadings
li.pl.factor_loadings(adata, factor_idx=0)
```

## Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--method` | `auto` | auto, liana, cellchat, nichenet, or builtin |
| `--cell-type-key` | `leiden` | Column with cell type labels |
| `--species` | `human` | human or mouse |
| `--n-perms` | `100` | Permutation count |
| `--min-cells` | `10` | Min cells per cell type |

## Example Queries

- "Score ligand-receptor associations across my cells"
- "Employ NicheNet logic to dissect signaling arrays"

## Output Structure

```
output_dir/
├── report.md
├── result.json
├── processed.h5ad
├── figures/
│   └── summary_plot.png
├── tables/
│   └── metrics.csv
└── reproducibility/
    ├── commands.sh
    ├── environment.yml
    └── checksums.sha256
```

## Version Compatibility

Reference examples tested with: scanpy 1.10+, liana 1.0+

## Dependencies

**Required**: scanpy, numpy, pandas
**Optional**: liana (for multi-method consensus), CellChat (R), nichenetr (R)

## Citations

- [CellChat](https://doi.org/10.1038/s41467-021-21246-9) — Jin et al., Nature Communications 2021
- [NicheNet](https://doi.org/10.1038/s41592-019-0667-5) — Browaeys et al., Nature Methods 2020
- [LIANA+](https://github.com/saezlab/liana-py) — Dimitrov et al., Nature Cell Biology 2022
- [CellPhoneDB](https://www.cellphonedb.org/) — Efremova et al., Nature Protocols 2020

## Safety

- **Local-first**: Strict offline processing without external upload.
- **Disclaimer**: Requires OmicsClaw reporting structures and disclaimers.
- **Audit trail**: Hyperparameters and operational flow states are logged fully.

## Integration with Orchestrator

**Trigger conditions**:
- Automatically invoked dynamically based on tool metadata and user intent matching.

**Chaining partners**:
- `sc-preprocess` — QC and clustering before communication analysis
- `sc-trajectory` — Communication along developmental trajectory
- `sc-grn` — Regulatory network context for signaling
