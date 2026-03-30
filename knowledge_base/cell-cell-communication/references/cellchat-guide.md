# CellChat v2 Detailed Guide

## CellChatDB Database Categories

CellChat v2 includes three categories of cell-cell interactions:

| Category | Description | Examples |
|----------|-------------|----------|
| **Secreted Signaling** | Soluble ligands binding receptors on distant cells | TNF, IL-6, CCL, CXCL chemokines |
| **ECM-Receptor** | Extracellular matrix molecules signaling through receptors | Collagen, Laminin, Fibronectin |
| **Cell-Cell Contact** | Membrane-bound ligand-receptor interactions | MHC-I/II, Notch, CD80-CD28 |

### Filtering by category

```r
CellChatDB <- CellChatDB.human
# Use specific category
CellChatDB_secreted <- subsetDB(CellChatDB, search = "Secreted Signaling")
cellchat@DB <- CellChatDB_secreted
```

## Parameter Tuning

### Communication probability method

| Method | Parameter | Behavior | When to use |
|--------|-----------|----------|-------------|
| `triMean` | `type = "triMean"` | Conservative, favors strong interactions | Default, recommended for most analyses |
| `truncatedMean` | `type = "truncatedMean", trim = 0.1` | More sensitive, detects weaker signals | Large datasets, exploratory analysis |
| `median` | `type = "median"` | Most conservative | When specificity is critical |

```r
# Default (recommended)
cellchat <- computeCommunProb(cellchat, type = "triMean")

# More sensitive
cellchat <- computeCommunProb(cellchat, type = "truncatedMean", trim = 0.1)
```

### Minimum cells threshold

```r
# Default: filter cell groups with <10 cells
cellchat <- filterCommunication(cellchat, min.cells = 10)

# More permissive for rare cell types
cellchat <- filterCommunication(cellchat, min.cells = 5)
```

## Multi-Condition Comparison

Compare communication between conditions (e.g., disease vs healthy, treated vs untreated).

### Workflow

```r
# 1. Run CellChat separately for each condition
cellchat_ctrl <- run_cellchat_analysis(seurat_ctrl, species = "human")
cellchat_treat <- run_cellchat_analysis(seurat_treat, species = "human")

# 2. Lift cell groups to shared label space (if cell types differ)
group_new <- union(levels(cellchat_ctrl@idents), levels(cellchat_treat@idents))
cellchat_ctrl <- liftCellChat(cellchat_ctrl, group_new)
cellchat_treat <- liftCellChat(cellchat_treat, group_new)

# 3. Merge
cellchat_list <- list(Control = cellchat_ctrl, Treated = cellchat_treat)
cellchat_merged <- mergeCellChat(cellchat_list, add.names = names(cellchat_list))

# 4. Compare
compareInteractions(cellchat_merged, show.legend = TRUE)
netVisual_diffInteraction(cellchat_merged, weight.scale = TRUE)
rankNet(cellchat_merged, mode = "comparison")
```

### Splitting a multi-condition Seurat object

```r
# If conditions are in metadata column "condition"
seurat_list <- SplitObject(seurat_obj, split.by = "condition")
cellchat_ctrl <- run_cellchat_analysis(seurat_list[["control"]])
cellchat_treat <- run_cellchat_analysis(seurat_list[["treated"]])
```

## Handling Rare Cell Types

Cell types with very few cells (<10) may:
- Produce unreliable communication probabilities
- Cause errors in centrality computation

**Solutions:**

1. **Merge rare types** into broader categories:
```r
seurat_obj$celltype_broad <- seurat_obj$celltype
seurat_obj$celltype_broad[seurat_obj$celltype %in% c("pDC", "cDC")] <- "Dendritic cells"
```

2. **Increase min.cells filter:**
```r
cellchat <- filterCommunication(cellchat, min.cells = 20)
```

3. **Remove from analysis:**
```r
# Subset Seurat before CellChat
cells_keep <- colnames(seurat_obj)[!seurat_obj$celltype %in% c("Platelets")]
seurat_obj <- subset(seurat_obj, cells = cells_keep)
```

## Memory Optimization for Large Datasets

For datasets >50,000 cells:

1. **Subsample** before CellChat (communication is computed on group averages):
```r
seurat_sub <- subset(seurat_obj, downsample = 5000)  # max 5000 per type
```

2. **Use population size** parameter:
```r
cellchat <- computeCommunProb(cellchat, type = "triMean", population.size = TRUE)
```

3. **Run garbage collection** between steps:
```r
gc()
```

## Examining Specific Pathways

After the main analysis, dive into individual pathways:

```r
# List all active pathways
cellchat@netP$pathways

# Visualize a specific pathway
pathways.show <- "MHC-II"

# Hierarchy plot (shows communication flow)
netVisual_aggregate(cellchat, signaling = pathways.show, layout = "hierarchy")

# Circle plot for one pathway
netVisual_aggregate(cellchat, signaling = pathways.show, layout = "circle")

# Chord diagram for one pathway
netVisual_aggregate(cellchat, signaling = pathways.show, layout = "chord")

# Contribution of each L-R pair to the pathway
netAnalysis_contribution(cellchat, signaling = pathways.show)
```

## Extracting Results Programmatically

```r
# All significant interactions as data frame
df <- subsetCommunication(cellchat)

# Filter by source cell type
df_mono <- subsetCommunication(cellchat, sources.use = "CD14+ Mono")

# Filter by target
df_tcell <- subsetCommunication(cellchat, targets.use = "CD8 T")

# Filter by pathway
df_tnf <- subsetCommunication(cellchat, signaling = "TNF")

# Pathway-level (aggregated) interactions
df_pw <- subsetCommunication(cellchat, slot.name = "netP")

# Interaction strength matrix
cellchat@net$weight   # cell type x cell type
cellchat@net$count    # number of interactions
```

## CellChat Object Structure

```
cellchat@data.signaling    # Expression data (signaling genes only)
cellchat@idents            # Cell type labels (factor)
cellchat@DB                # Ligand-receptor database used
cellchat@LR$LRsig         # Overexpressed L-R pairs
cellchat@net$prob          # 3D array: source x target x L-R pair
cellchat@net$pval          # P-values for each interaction
cellchat@net$count         # Aggregated interaction counts
cellchat@net$weight        # Aggregated interaction weights
cellchat@netP$pathways     # Active signaling pathways
cellchat@netP$prob         # 3D array: source x target x pathway
cellchat@netP$centr        # Centrality scores per pathway
```
