# Decision Guide for scRNA-seq Analysis with Seurat

Comprehensive guidance for making key decisions throughout your single-cell RNA-seq analysis workflow.

---

## Decision 1: Ambient RNA Correction

**When:** Before QC, if using raw CellRanger output

### Options

**Option A: Skip Ambient RNA Correction**
- **Use when:**
  - Working with filtered CellRanger matrices (`filtered_feature_bc_matrix/`)
  - Analyzing low-soup tissues (PBMC, sorted cells)
  - Data already processed by someone else
- **Pros:** Faster, simpler workflow
- **Cons:** May retain background contamination if data is raw

**Option B: Apply SoupX Correction**
- **Use when:**
  - Working with raw CellRanger matrices (`raw_feature_bc_matrix/`)
  - Analyzing high-soup tissues (brain, lung, tumor, lymph nodes, spleen)
  - Contamination fraction >5% (check with `autoEstCont()`)
- **Pros:** Removes ambient RNA contamination, improves downstream analysis
- **Cons:** Requires both raw and filtered matrices, adds processing time

### Recommendation

- **Default:** Skip for PBMC and filtered data
- **Use SoupX:** For brain, lung, tumor, or any raw matrices

### Implementation

See [ambient_rna_correction.md](ambient_rna_correction.md) for detailed guidance.

---

## Decision 2: QC Strategy

**When:** Step 2, before filtering cells

### Options

**Option A: Batch-Aware MAD Outlier Detection**
- **Use when:**
  - Multiple batches with potential batch-specific QC distributions
  - Don't have established tissue-specific thresholds
  - Want adaptive, data-driven filtering
- **How it works:** Calculates median + MAD per batch, flags outliers >5 MADs away
- **Pros:** Adapts to batch differences, reduces over-filtering
- **Cons:** May be too lenient if contamination is widespread

**Option B: Fixed Tissue-Specific Thresholds**
- **Use when:**
  - Single batch or well-characterized tissue type
  - Have established QC guidelines for your tissue
  - Want reproducible, standardized filtering
- **Thresholds by tissue:**
  - PBMC: 200-2500 genes, <5% MT
  - Brain: 200-6000 genes, <10% MT
  - Tumor: 200-5000 genes, <20% MT
  - Lung: 200-4000 genes, <15% MT
- **Pros:** Reproducible, well-tested thresholds
- **Cons:** May need adjustment for your specific data

### Recommendation

- **Multi-batch data:** Use MAD (batch-aware)
- **Single batch:** Use fixed thresholds based on tissue type
- **Unknown tissue:** Start with MAD, then inspect distributions

### Implementation

```r
# MAD approach
seurat_obj <- batch_mad_outlier_detection(
  seurat_obj,
  batch_col = "batch",
  metrics = c("nFeature_RNA", "nCount_RNA", "percent.mt"),
  nmads = 5
)

# Fixed thresholds
seurat_obj <- mark_outliers_fixed(seurat_obj, tissue = "pbmc")
```

See [qc_guidelines.md](qc_guidelines.md) for tissue-specific threshold tables.

---

## Decision 3: Normalization Method

**When:** Step 4, after QC filtering

### Options

**Option A: SCTransform (Recommended)**
- **Use when:**
  - UMI-based data (10X Chromium, Drop-seq, inDrop)
  - Multiple batches with technical variation
  - Need to regress out covariates (MT%, cell cycle)
- **How it works:** Regularized negative binomial regression, stabilizes variance
- **Pros:** Better handling of technical noise, built-in regression
- **Cons:** Slower, memory-intensive for large datasets

**Option B: LogNormalize + Scale**
- **Use when:**
  - Non-UMI data (Smart-seq2)
  - Speed is critical
  - Following classic Seurat workflow for comparison
- **How it works:** Log-transform after library size normalization
- **Pros:** Fast, memory-efficient, well-tested
- **Cons:** Assumes equal capture efficiency, separate scaling step needed

### Recommendation

- **Default:** SCTransform for 10X/UMI data
- **Large datasets (>100k cells):** Consider LogNormalize for speed
- **Non-UMI data:** Use LogNormalize

### Implementation

```r
# SCTransform
seurat_obj <- run_sctransform(
  seurat_obj,
  vars_to_regress = c("percent.mt"),
  vst.flavor = "v2"  # Use v2 for Seurat v5
)

# LogNormalize
seurat_obj <- run_lognormalize(seurat_obj)
seurat_obj <- find_hvgs(seurat_obj, n_features = 2000)
seurat_obj <- scale_data(seurat_obj, vars_to_regress = c("percent.mt"))
```

See [seurat_best_practices.md](seurat_best_practices.md) for detailed comparison.

---

## Decision 4: Batch Integration Method

**When:** Step 6, if you have multiple batches

### Options

**Option A: Harmony (Recommended)**
- **Use when:**
  - Standard batch correction needs
  - Want fast integration
  - Using SCTransform normalization
- **How it works:** Iteratively adjusts PCA embeddings to mix batches
- **Pros:** Fast, simple, works well with SCTransform, preserves biological variation
- **Cons:** May not handle very complex batch effects

**Option B: Seurat CCA Integration**
- **Use when:**
  - Complex batch effects (different labs, technologies)
  - Need canonical correlation analysis
  - Have subtle biological differences to preserve
- **How it works:** Identifies shared correlation structure across batches
- **Pros:** Handles complex batch effects, preserves cell type differences
- **Cons:** Slower, more memory-intensive

**Option C: Seurat RPCA Integration**
- **Use when:**
  - Very large datasets (>100k cells)
  - Need faster integration than CCA
  - Batches are relatively similar
- **How it works:** Uses reciprocal PCA for anchor identification
- **Pros:** Faster than CCA, scalable
- **Cons:** May overcorrect if batches are very different

**Option D: Skip Integration**
- **Use when:**
  - Single batch
  - Minimal batch effects (check PCA/UMAP first)
- **Decision point:** Always visualize PCA/UMAP colored by batch before deciding

### Recommendation

- **Default:** Harmony (fast, robust)
- **Complex batches:** CCA
- **Very large data:** RPCA
- **Always validate:** Use LISI/ASW metrics

### Implementation

```r
# Harmony
seurat_obj <- run_harmony_integration(
  seurat_obj,
  batch_var = "batch",
  dims_use = 1:30
)

# CCA
seurat_obj <- run_seurat_cca_integration(
  seurat_obj,
  batch_var = "batch",
  dims = 1:30,
  k.anchor = 5
)

# RPCA
seurat_obj <- run_seurat_rpca_integration(
  seurat_obj,
  batch_var = "batch",
  dims = 1:30
)
```

### Validation

Always validate integration quality:
- **Batch LISI:** Close to 1 (good mixing)
- **Cell type LISI:** Preserved (not collapsed)
- **Visual inspection:** UMAP colored by batch should show mixing

See [integration_methods.md](integration_methods.md) for detailed comparison.

---

## Decision 5: Clustering Resolution

**When:** Step 7, during clustering

### Options

**Option A: Test Multiple Resolutions (Recommended)**
- **Use when:** Exploratory analysis (most cases)
- **Resolutions to test:** 0.4, 0.6, 0.8, 1.0
- **Pros:** See data at different granularities, choose best after inspection
- **Cons:** More clusters to evaluate

**Option B: Single Resolution**
- **Use when:** Know expected granularity from prior knowledge
- **Guidelines:**
  - Coarse (major cell types): 0.3-0.5
  - Standard: 0.6-0.8
  - Fine (subtypes): 1.0-1.5

### How to Choose

1. **Biological interpretability:** Can clusters be assigned meaningful cell type labels?
2. **Stability:** Do clusters remain stable across resolutions?
3. **Marker quality:** Do clusters have clear, specific marker genes?
4. **Cluster size:** Are clusters large enough (>10 cells minimum)?
5. **Prior knowledge:** Does resolution match expected cell type diversity?

### Recommendation

- **Test multiple first:** 0.4, 0.6, 0.8, 1.0
- **Compare visually:** UMAP plots at each resolution
- **Check markers:** Quality of marker genes at each resolution
- **Choose final:** Balance granularity with biological meaning

### Implementation

```r
# Test multiple resolutions
seurat_obj <- cluster_multiple_resolutions(
  seurat_obj,
  dims = 1:30,
  reduction = reduction,
  resolutions = c(0.4, 0.6, 0.8, 1.0)
)

# Compare visually
plot_clustering_comparison(
  seurat_obj,
  resolutions = c(0.4, 0.6, 0.8, 1.0),
  output_dir = "results/resolution_comparison"
)

# Set active resolution after inspection
Idents(seurat_obj) <- "RNA_snn_res.0.8"
```

---

## Decision 6: Cell Type Annotation Strategy

**When:** Step 9, after clustering

### Options

**Option A: Manual Annotation (Recommended)**
- **Use when:**
  - Need high accuracy
  - Have domain expertise
  - Time for careful marker gene review
- **Pros:** Most accurate, captures nuances, publishable
- **Cons:** Time-consuming, requires expertise

**Option B: Automated with SingleR**
- **Use when:**
  - Need fast preliminary annotations
  - Exploring new dataset
  - Standard tissue types (PBMC, brain, etc.)
- **Pros:** Fast, reproducible, no marker gene knowledge needed
- **Cons:** May misclassify rare/novel types, less accurate

**Option C: Both (Validate Automated with Manual)**
- **Use when:**
  - Want best of both worlds
  - Time to do both
  - Need confidence in annotations
- **Workflow:** Run SingleR first, then manually validate/refine with marker genes
- **Pros:** Fast initial labels, validated accuracy
- **Cons:** Most time-intensive

### Recommendation

- **Publication:** Manual annotation (Option A or C)
- **Exploration:** Automated (Option B)
- **Best practice:** Both (Option C) - automated first, then validate

### Manual Annotation Workflow

1. **Find cluster markers** (Step 8)
2. **Check top marker genes** against known databases
3. **Use marker gene database** ([marker_gene_database.md](marker_gene_database.md))
4. **Visualize markers** with feature plots, dot plots
5. **Assign labels** based on marker expression patterns
6. **Validate:** Check for doublet clusters (mixed markers)

### Automated Annotation Workflow

```r
# SingleR with human reference
seurat_obj <- annotate_with_singler(
  seurat_obj,
  reference = "HPCA",  # Human Primary Cell Atlas
  label.main = TRUE
)

# Alternative references:
# - "MonacoImmune" (immune cells)
# - "DatabaseImmuneCellExpression" (DICE)
# - "BlueprintEncode" (general)
```

### Common Pitfalls

- **Over-splitting:** Too high resolution creates biologically meaningless clusters
- **Under-splitting:** Missing rare cell types or subtypes
- **Doublets:** Clusters with markers from multiple cell types
- **Batch-driven clusters:** Clusters that separate by batch, not biology

See [marker_gene_database.md](marker_gene_database.md) for cell type markers.

---

## Summary Decision Tree

```
Start
  │
  ├─ Raw data? → YES → Apply SoupX → Continue
  │           → NO  → Skip SoupX → Continue
  │
  ├─ Multiple batches? → YES → Use MAD QC → Continue
  │                   → NO  → Fixed thresholds → Continue
  │
  ├─ UMI data? → YES → SCTransform → Continue
  │           → NO  → LogNormalize → Continue
  │
  ├─ Multiple batches? → YES → Integrate (Harmony recommended) → Validate with LISI
  │                   → NO  → Skip integration
  │
  ├─ Clustering → Test resolutions 0.4, 0.6, 0.8, 1.0 → Choose best
  │
  └─ Annotation → Automated (fast) OR Manual (accurate) OR Both (best)
```

---

## Common Decision Scenarios

### Scenario 1: Standard 10X PBMC, Single Sample
- **Ambient RNA:** Skip
- **QC:** Fixed PBMC thresholds
- **Normalization:** SCTransform
- **Integration:** Skip
- **Resolution:** Test 0.4-1.0, choose 0.6-0.8
- **Annotation:** Manual with standard PBMC markers

### Scenario 2: Brain Tissue, Multiple Batches
- **Ambient RNA:** Apply SoupX (high-soup tissue)
- **QC:** Batch-aware MAD
- **Normalization:** SCTransform
- **Integration:** Harmony
- **Resolution:** Test 0.4-1.0, choose higher (0.8-1.0) for neuronal subtypes
- **Annotation:** Manual (complex cell types)

### Scenario 3: Tumor Sample, Unknown Composition
- **Ambient RNA:** Apply SoupX (high-soup)
- **QC:** MAD with lenient MT threshold (<20%)
- **Normalization:** SCTransform
- **Integration:** Depends on batches
- **Resolution:** Test broad range 0.4-1.5
- **Annotation:** Both (automated first, then validate)

### Scenario 4: Large Dataset (>100k cells)
- **Ambient RNA:** As needed
- **QC:** As needed
- **Normalization:** Consider LogNormalize for speed
- **Integration:** RPCA if multiple batches
- **Resolution:** Standard 0.6-0.8
- **Annotation:** Automated first, validate selected clusters

---

**Related Documentation:**
- [qc_guidelines.md](qc_guidelines.md) - Tissue-specific QC thresholds
- [seurat_best_practices.md](seurat_best_practices.md) - Comprehensive best practices
- [integration_methods.md](integration_methods.md) - Batch integration comparison
- [marker_gene_database.md](marker_gene_database.md) - Cell type markers
- [troubleshooting_guide.md](troubleshooting_guide.md) - Common issues and solutions
