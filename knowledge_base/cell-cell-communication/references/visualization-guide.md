# CellChat Visualization Guide

## Overview of Plot Types

| Plot | Best for | CellChat function |
|------|----------|-------------------|
| **Circle plot** | Overall network topology, interaction counts/strength | `netVisual_circle()` |
| **Chord diagram** | Detailed cell-to-cell flow, pathway-specific | `netVisual_chord_cell()` |
| **Bubble plot** | Comparing L-R pairs across cell type pairs | `netVisual_bubble()` |
| **Heatmap** | Signaling pattern overview, pathway contributions | `netAnalysis_signalingRole_heatmap()` |
| **Scatter** | Identifying dominant senders vs receivers | `netAnalysis_signalingRole_scatter()` |
| **Hierarchy** | Communication flow for a specific pathway | `netVisual_aggregate(..., layout = "hierarchy")` |

## Customizing Colors

```r
# Define custom colors for cell types
library(CellChat)

# Get cell type names
cell_types <- levels(cellchat@idents)

# Option 1: CellChat's built-in palette
colors <- scPalette(length(cell_types))
names(colors) <- cell_types

# Option 2: Manual colors
colors <- c(
    "CD4 T"       = "#E41A1C",
    "CD14+ Mono"  = "#377EB8",
    "B"           = "#4DAF4A",
    "CD8 T"       = "#984EA3",
    "NK"          = "#FF7F00",
    "FCGR3A+ Mono" = "#A65628",
    "DC"          = "#F781BF",
    "Platelet"    = "#999999"
)

# Use in plots
netVisual_circle(cellchat@net$count, color.use = colors, ...)
netVisual_chord_cell(cellchat, color.use = colors, ...)
```

## Circle Plot Customization

```r
# Basic circle plot
netVisual_circle(cellchat@net$count, weight.scale = TRUE)

# With vertex sizing by cell count
group_sizes <- as.numeric(table(cellchat@idents))
netVisual_circle(
    cellchat@net$count,
    vertex.weight = group_sizes,
    weight.scale = TRUE,
    label.edge = FALSE,
    title.name = "Number of Interactions"
)

# Filter to show only top N interactions
mat <- cellchat@net$weight
threshold <- sort(mat, decreasing = TRUE)[20]  # top 20
mat[mat < threshold] <- 0
netVisual_circle(mat, weight.scale = TRUE)

# Show interactions FROM specific cell types
netVisual_circle(
    cellchat@net$weight,
    sources.use = c("CD14+ Mono", "FCGR3A+ Mono"),
    weight.scale = TRUE,
    title.name = "Monocyte Outgoing Communication"
)
```

## Chord Diagram Customization

```r
# Full network chord diagram
netVisual_chord_cell(cellchat, net = cellchat@net$weight)

# Pathway-specific chord diagram
netVisual_chord_gene(
    cellchat,
    signaling = "MHC-II",
    slot.name = "net",
    title.name = "MHC-II Signaling"
)

# Filter by source/target
netVisual_chord_cell(
    cellchat,
    net = cellchat@net$weight,
    sources.use = c("CD14+ Mono"),
    targets.use = c("CD4 T", "CD8 T"),
    title.name = "Monocyte → T cell Communication"
)
```

## Bubble Plot Customization

```r
# All interactions
netVisual_bubble(cellchat, remove.isolate = TRUE)

# Filter by source and target
netVisual_bubble(
    cellchat,
    sources.use = c("CD14+ Mono"),
    targets.use = c("CD4 T", "CD8 T", "NK"),
    remove.isolate = TRUE
)

# Show specific pathways only
netVisual_bubble(
    cellchat,
    signaling = c("MHC-II", "TNF", "CCL"),
    remove.isolate = TRUE
)

# Sort by pathway
netVisual_bubble(
    cellchat,
    remove.isolate = TRUE,
    sort.by.source = TRUE
)
```

## Heatmap Variations

```r
# Outgoing signaling patterns (which cell types send which signals)
netAnalysis_signalingRole_heatmap(cellchat, pattern = "outgoing")

# Incoming signaling patterns
netAnalysis_signalingRole_heatmap(cellchat, pattern = "incoming")

# Signaling contribution for specific pathways
netAnalysis_signalingRole_heatmap(
    cellchat,
    signaling = c("MHC-II", "TNF", "CCL", "CXCL"),
    pattern = "outgoing"
)

# Network centrality heatmap (sender, receiver, mediator, influencer)
netAnalysis_signalingRole_network(cellchat, signaling = cellchat@netP$pathways)
```

## Pathway-Specific Deep Dive

```r
pathways.show <- "MHC-II"

# Three layout options for the same pathway
par(mfrow = c(1, 3))
netVisual_aggregate(cellchat, signaling = pathways.show, layout = "circle")
netVisual_aggregate(cellchat, signaling = pathways.show, layout = "chord")
netVisual_aggregate(cellchat, signaling = pathways.show, layout = "hierarchy")

# Which L-R pairs contribute most to this pathway?
netAnalysis_contribution(cellchat, signaling = pathways.show)

# Gene expression of the pathway's ligands and receptors
plotGeneExpression(cellchat, signaling = pathways.show)
```

## Multi-Condition Comparison Plots

After merging CellChat objects from two conditions:

```r
# Compare total interaction counts
compareInteractions(cellchat_merged, show.legend = TRUE, group = c(1, 2))

# Differential interaction network
netVisual_diffInteraction(cellchat_merged, weight.scale = TRUE)

# Information flow comparison (pathway ranking)
rankNet(cellchat_merged, mode = "comparison", stacked = TRUE)

# Scatter: compare signaling strength
netAnalysis_signalingChanges_scatter(cellchat_merged, idents.use = "CD14+ Mono")
```

## Publication Figure Assembly

For combining multiple CellChat plots into a single figure:

```r
# Use patchwork or cowplot for ggplot-based CellChat outputs
library(patchwork)

p1 <- netVisual_bubble(cellchat, remove.isolate = TRUE)
p2 <- netAnalysis_signalingRole_scatter(cellchat)

combined <- p1 + p2 + plot_layout(widths = c(2, 1))
ggsave("combined_figure.png", combined, width = 16, height = 8, dpi = 300)
```

For base R plots (circle, chord), save individually and combine externally or use `par(mfrow)`:

```r
png("combined_networks.png", width = 16, height = 8, units = "in", res = 300)
par(mfrow = c(1, 2), mar = c(1, 1, 2, 1))
netVisual_circle(cellchat@net$count, weight.scale = TRUE,
                 title.name = "Interaction Count")
netVisual_circle(cellchat@net$weight, weight.scale = TRUE,
                 title.name = "Interaction Strength")
dev.off()
```


---
