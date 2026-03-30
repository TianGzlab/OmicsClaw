# GSEA/ORA Workflow Validation Framework v3.0

## Overview

This validation framework tests **unique clusterProfiler capabilities** using pre-processed datasets from the vignette. Each test focuses on a distinct feature or visualization type to avoid redundancy.

**Primary References:**
- Yu G. *Biomedical Knowledge Mining using GOSemSim and clusterProfiler* [1]
- Xu S, Hu E, Cai Y, et al. *Using clusterProfiler to characterize multiomics data.* Nature Protocols 19, 3292–3320 (2024) [2]

---

## Validation Test Summary Table

| Test ID | Unique Capability | Dataset | Function | Key Output/Plot |
|---------|------------------|---------|----------|-----------------|
| 1 | **KEGG ORA** | `geneList` (DOSE) | `enrichKEGG()` | `barplot()` |
| 2 | **KEGG GSEA** | `geneList` (DOSE) | `gseKEGG()` | `gseaplot2()` + `ridgeplot()` |
| 3 | **GO ORA with simplify** | `geneList` (DOSE) | `enrichGO()` + `simplify()` | `dotplot()` |
| 4 | **GO DAG visualization** | `geneList` (DOSE) | `enrichGO()` | `goplot()` |
| 5 | **MSigDB/Custom gene sets** | `geneList` (DOSE) | `enricher()` / `GSEA()` | `cnetplot()` |
| 6 | **compareCluster (multi-group)** | `gcSample` (clusterProfiler) | `compareCluster()` | `dotplot()` with facets |
| 7 | **Enrichment map** | `geneList` (DOSE) | `enrichGO()` | `emapplot()` + `treeplot()` |
| 8 | **Gene-concept heatmap** | `geneList` (DOSE) | `enrichKEGG()` | `heatplot()` |
| 9 | **UpSet plot** | `geneList` (DOSE) | `enrichGO()` | `upsetplot()` |
| 10 | **KEGG pathway visualization** | `geneList` (DOSE) | `enrichKEGG()` | `browseKEGG()` / `pathview()` |

---

## Test Details

### Test 1: KEGG ORA with Bar Plot

| Field | Value |
|-------|-------|
| **Unique Capability** | Basic KEGG over-representation analysis |
| **Dataset** | `data(geneList, package="DOSE")` - pre-loaded |
| **Function** | `enrichKEGG()` |
| **Visualization** | `barplot()` |

**Natural Language Prompt:**
> "Using the DOSE geneList dataset, perform KEGG pathway enrichment on genes with |log2FC| > 2 and show results as a bar plot."

**Expected Results:**
- Cell cycle (hsa04110) as top pathway
- At least 5 significant pathways (padj < 0.05)

**Validation Criteria:**
- [ ] `enrichKEGG()` returns results
- [ ] `barplot()` generates visualization
- [ ] Cell cycle pathway is enriched

**Code:**
```r
library(clusterProfiler)
data(geneList, package="DOSE")
gene <- names(geneList)[abs(geneList) > 2]
kk <- enrichKEGG(gene = gene, organism = 'hsa')
barplot(kk, showCategory = 10)
```

---

### Test 2: KEGG GSEA with Running Score Plot and Ridge Plot

| Field | Value |
|-------|-------|
| **Unique Capability** | GSEA with enrichment score visualization |
| **Dataset** | `data(geneList, package="DOSE")` - pre-loaded |
| **Function** | `gseKEGG()` |
| **Visualization** | `gseaplot2()` + `ridgeplot()` |

**Natural Language Prompt:**
> "Using the DOSE geneList dataset, perform KEGG GSEA and show the running enrichment score plot for the top pathway, plus a ridge plot of all significant pathways."

**Expected Results:**
- Mix of positive and negative NES values
- Running score plot shows gene rank distribution

**Validation Criteria:**
- [ ] `gseKEGG()` returns results with NES values
- [ ] `gseaplot2()` shows running enrichment score
- [ ] `ridgeplot()` shows expression distribution across pathways

**Code:**
```r
library(clusterProfiler)
library(enrichplot)
data(geneList, package="DOSE")
kk2 <- gseKEGG(geneList = geneList, organism = 'hsa', minGSSize = 120)
gseaplot2(kk2, geneSetID = 1, title = kk2$Description[1])
ridgeplot(kk2)
```

---

### Test 3: GO ORA with Redundancy Reduction (simplify)

| Field | Value |
|-------|-------|
| **Unique Capability** | GO term simplification to reduce redundancy |
| **Dataset** | `data(geneList, package="DOSE")` - pre-loaded |
| **Function** | `enrichGO()` + `simplify()` |
| **Visualization** | `dotplot()` comparing before/after |

**Natural Language Prompt:**
> "Using the DOSE geneList dataset, perform GO Biological Process enrichment, then use simplify() to reduce redundant terms. Show dotplots before and after simplification."

**Expected Results:**
- Simplified results have fewer, non-redundant terms
- Key biological themes preserved

**Validation Criteria:**
- [ ] `enrichGO()` returns many GO terms
- [ ] `simplify()` reduces term count significantly
- [ ] `dotplot()` shows cleaner, non-redundant results

**Code:**
```r
library(clusterProfiler)
library(org.Hs.eg.db)
data(geneList, package="DOSE")
gene <- names(geneList)[abs(geneList) > 2]
ego <- enrichGO(gene = gene, OrgDb = org.Hs.eg.db, ont = "BP", readable = TRUE)
ego_simplified <- simplify(ego, cutoff = 0.7, by = "p.adjust")
dotplot(ego, showCategory = 15, title = "Before simplify")
dotplot(ego_simplified, showCategory = 15, title = "After simplify")
```

---

### Test 4: GO DAG Visualization

| Field | Value |
|-------|-------|
| **Unique Capability** | Visualize GO terms as directed acyclic graph |
| **Dataset** | `data(geneList, package="DOSE")` - pre-loaded |
| **Function** | `enrichGO()` |
| **Visualization** | `goplot()` |

**Natural Language Prompt:**
> "Using the DOSE geneList dataset, perform GO Cellular Component enrichment and visualize the enriched terms as a GO DAG showing parent-child relationships."

**Expected Results:**
- DAG shows hierarchical GO term relationships
- Enriched terms highlighted with color

**Validation Criteria:**
- [ ] `goplot()` generates DAG visualization
- [ ] Parent-child relationships visible
- [ ] Color indicates enrichment significance

**Code:**
```r
library(clusterProfiler)
library(org.Hs.eg.db)
data(geneList, package="DOSE")
gene <- names(geneList)[abs(geneList) > 2]
ego <- enrichGO(gene = gene, OrgDb = org.Hs.eg.db, ont = "CC")
goplot(ego)
```

---

### Test 5: Custom Gene Sets (MSigDB) with Gene-Concept Network

| Field | Value |
|-------|-------|
| **Unique Capability** | Universal enrichment with custom gene sets + network visualization |
| **Dataset** | `data(geneList, package="DOSE")` - pre-loaded |
| **Function** | `enricher()` or `GSEA()` with MSigDB |
| **Visualization** | `cnetplot()` |

**Natural Language Prompt:**
> "Using the DOSE geneList dataset, perform enrichment analysis with MSigDB Hallmark gene sets and visualize the gene-concept network showing which genes belong to which pathways."

**Expected Results:**
- Custom gene sets successfully used
- Network shows gene-pathway connections

**Validation Criteria:**
- [ ] `enricher()` or `GSEA()` works with custom TERM2GENE
- [ ] `cnetplot()` shows gene-pathway network
- [ ] Genes colored by fold change

**Code:**
```r
library(clusterProfiler)
library(msigdbr)
library(enrichplot)
data(geneList, package="DOSE")
gene <- names(geneList)[abs(geneList) > 2]

# Get Hallmark gene sets
h_gene_sets <- msigdbr(species = "Homo sapiens", category = "H") %>%
  dplyr::select(gs_name, entrez_gene)

em <- enricher(gene, TERM2GENE = h_gene_sets)
cnetplot(em, categorySize = "pvalue", foldChange = geneList)
```

---

### Test 6: compareCluster (Multi-Group Comparison)

| Field | Value |
|-------|-------|
| **Unique Capability** | Compare enrichment across multiple gene clusters |
| **Dataset** | `data(gcSample)` - pre-loaded in clusterProfiler |
| **Function** | `compareCluster()` |
| **Visualization** | `dotplot()` with multiple columns |

**Natural Language Prompt:**
> "Using the gcSample dataset from clusterProfiler, compare GO enrichment across all 8 gene clusters and visualize with a dotplot."

**Expected Results:**
- 8 clusters compared simultaneously
- Shared and unique pathways visible

**Validation Criteria:**
- [ ] `compareCluster()` processes all 8 clusters
- [ ] `dotplot()` shows multi-column comparison
- [ ] Different clusters show different enrichment patterns

**Code:**
```r
library(clusterProfiler)
library(org.Hs.eg.db)
data(gcSample)
ck <- compareCluster(geneCluster = gcSample, fun = enrichGO, 
                     OrgDb = org.Hs.eg.db, ont = "BP")
dotplot(ck)
```

---

### Test 7: Enrichment Map and Tree Plot

| Field | Value |
|-------|-------|
| **Unique Capability** | Visualize term similarity as network/tree |
| **Dataset** | `data(geneList, package="DOSE")` - pre-loaded |
| **Function** | `enrichGO()` + `pairwise_termsim()` |
| **Visualization** | `emapplot()` + `treeplot()` |

**Natural Language Prompt:**
> "Using the DOSE geneList dataset, perform GO enrichment and visualize term relationships using an enrichment map (network of similar terms) and a tree plot (hierarchical clustering)."

**Expected Results:**
- Similar GO terms cluster together
- Tree shows hierarchical grouping of terms

**Validation Criteria:**
- [ ] `pairwise_termsim()` calculates term similarity
- [ ] `emapplot()` shows term similarity network
- [ ] `treeplot()` shows hierarchical clustering

**Code:**
```r
library(clusterProfiler)
library(org.Hs.eg.db)
library(enrichplot)
data(geneList, package="DOSE")
gene <- names(geneList)[abs(geneList) > 2]
ego <- enrichGO(gene = gene, OrgDb = org.Hs.eg.db, ont = "BP")
ego <- pairwise_termsim(ego)
emapplot(ego)
treeplot(ego)
```

---

### Test 8: Gene-Concept Heatmap

| Field | Value |
|-------|-------|
| **Unique Capability** | Heatmap of genes vs pathways |
| **Dataset** | `data(geneList, package="DOSE")` - pre-loaded |
| **Function** | `enrichKEGG()` |
| **Visualization** | `heatplot()` |

**Natural Language Prompt:**
> "Using the DOSE geneList dataset, perform KEGG enrichment and visualize as a heatmap showing which genes are in which pathways, with fold change indicated by color."

**Expected Results:**
- Matrix view of gene-pathway membership
- Fold change shown as color gradient

**Validation Criteria:**
- [ ] `heatplot()` generates gene-pathway matrix
- [ ] Fold change mapped to color
- [ ] Pathways and genes clearly labeled

**Code:**
```r
library(clusterProfiler)
library(enrichplot)
data(geneList, package="DOSE")
gene <- names(geneList)[abs(geneList) > 2]
kk <- enrichKEGG(gene = gene, organism = 'hsa')
heatplot(kk, foldChange = geneList, showCategory = 5)
```

---

### Test 9: UpSet Plot for Pathway Overlap

| Field | Value |
|-------|-------|
| **Unique Capability** | Visualize gene overlap across pathways |
| **Dataset** | `data(geneList, package="DOSE")` - pre-loaded |
| **Function** | `enrichGO()` |
| **Visualization** | `upsetplot()` |

**Natural Language Prompt:**
> "Using the DOSE geneList dataset, perform GO enrichment and create an UpSet plot showing how genes overlap across the top enriched terms."

**Expected Results:**
- UpSet plot shows intersection sizes
- Identifies genes shared across multiple terms

**Validation Criteria:**
- [ ] `upsetplot()` generates visualization
- [ ] Intersection matrix visible
- [ ] Bar heights show intersection sizes

**Code:**
```r
library(clusterProfiler)
library(org.Hs.eg.db)
library(enrichplot)
data(geneList, package="DOSE")
gene <- names(geneList)[abs(geneList) > 2]
ego <- enrichGO(gene = gene, OrgDb = org.Hs.eg.db, ont = "CC")
upsetplot(ego)
```

---

### Test 10: KEGG Pathway Map Visualization

| Field | Value |
|-------|-------|
| **Unique Capability** | Overlay expression on KEGG pathway diagrams |
| **Dataset** | `data(geneList, package="DOSE")` - pre-loaded |
| **Function** | `enrichKEGG()` |
| **Visualization** | `browseKEGG()` or `pathview()` |

**Natural Language Prompt:**
> "Using the DOSE geneList dataset, perform KEGG enrichment and visualize the Cell Cycle pathway with gene expression values overlaid on the pathway diagram."

**Expected Results:**
- KEGG pathway diagram with colored genes
- Expression values mapped to color scale

**Validation Criteria:**
- [ ] `browseKEGG()` opens pathway in browser OR
- [ ] `pathview()` generates pathway image file
- [ ] Genes colored by expression level

**Code:**
```r
library(clusterProfiler)
library(pathview)
data(geneList, package="DOSE")
gene <- names(geneList)[abs(geneList) > 2]
kk <- enrichKEGG(gene = gene, organism = 'hsa')

# Option 1: Browser-based
browseKEGG(kk, 'hsa04110')

# Option 2: Generate image file
pathview(gene.data = geneList, pathway.id = "hsa04110", species = "hsa")
```

---

## Quick Reference: Pre-loaded Datasets

| Dataset | Package | Description | Load Command |
|---------|---------|-------------|--------------|
| `geneList` | DOSE | Ranked gene list (log2FC) from breast cancer | `data(geneList, package="DOSE")` |
| `gcSample` | clusterProfiler | 8 gene clusters for comparison | `data(gcSample)` |

---

## Quick Reference: Visualization Functions

| Function | Input | Output | Use Case |
|----------|-------|--------|----------|
| `barplot()` | enrichResult | Bar chart | Simple pathway counts |
| `dotplot()` | enrichResult | Dot plot | Gene ratio + p-value |
| `cnetplot()` | enrichResult | Network | Gene-pathway connections |
| `heatplot()` | enrichResult | Heatmap | Gene-pathway matrix |
| `emapplot()` | enrichResult + termsim | Network | Term similarity |
| `treeplot()` | enrichResult + termsim | Dendrogram | Term clustering |
| `upsetplot()` | enrichResult | UpSet | Gene overlap |
| `goplot()` | enrichGO result | DAG | GO hierarchy |
| `gseaplot2()` | gseaResult | Line plot | Running enrichment score |
| `ridgeplot()` | gseaResult | Ridge plot | Expression distribution |
| `browseKEGG()` | enrichKEGG result | Browser | Interactive pathway |
| `pathview()` | gene list | Image file | Static pathway diagram |

---

## References

1. Yu G. Biomedical Knowledge Mining using GOSemSim and clusterProfiler. https://yulab-smu.top/biomedical-knowledge-mining-book/
2. Xu S, Hu E, Cai Y, et al. Using clusterProfiler to characterize multiomics data. *Nature Protocols* 19, 3292–3320 (2024).

---

## Changelog

### v3.0 (Current)
- Streamlined to 10 tests focusing on unique capabilities
- Each test covers a distinct clusterProfiler feature or visualization
- All tests use pre-loaded datasets (`geneList`, `gcSample`)
- Removed redundant tests across different datasets
- Added comprehensive visualization function reference
