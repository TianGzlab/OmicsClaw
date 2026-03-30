# Workflow Details: Complete Code Examples

This document provides detailed code examples and explanations for each step of the single-cell RNA-seq analysis workflow. Use this as a reference for implementing the Standard Workflow described in SKILL.md.

---

## Phase 1: QC and Filtering

### Step 1: Ambient RNA Correction (Optional - Raw Data Only)

**When to use:** Raw CellRanger matrices, high-soup tissues (brain, lung, tumor, lymph nodes)

**CellBender approach (recommended, GPU required):**
```python
from scripts.remove_ambient_rna import run_cellbender, estimate_contamination

# Run CellBender
adata_denoised = run_cellbender(
    raw_h5="raw_feature_bc_matrix.h5",
    expected_cells=10000,
    total_droplets=30000,  # 2-3x expected cells
    epochs=150,
    output_dir="results/ambient"
)

# Check contamination level
contamination = estimate_contamination(adata_denoised)
print(f"Estimated contamination: {contamination:.1%}")
```

**SoupX Python wrapper (CPU-friendly alternative):**
```python
from scripts.remove_ambient_rna import run_soupx_python

adata_denoised = run_soupx_python(
    raw_matrix_dir="raw_feature_bc_matrix/",
    filtered_matrix_dir="filtered_feature_bc_matrix/"
)
```

**Skip if:** Using pre-filtered data or low-soup tissue (PBMC, sorted cells)

---

### Step 2: Load Data and Calculate QC Metrics

**Import data:**
```python
from scripts.setup_and_import import (
    setup_scanpy_environment,
    import_10x_data,
    import_h5_data,
    import_csv_data
)

# Setup environment with recommended settings
setup_scanpy_environment()

# Option A: 10X directory
adata = import_10x_data("filtered_feature_bc_matrix/")

# Option B: H5 file
adata = import_h5_data("filtered_feature_bc_matrix.h5")

# Option C: CSV/TSV matrix
adata = import_csv_data("counts_matrix.csv", transpose=True)

# Option D: Existing AnnData
import scanpy as sc
adata = sc.read_h5ad("data.h5ad")
```

**Calculate QC metrics:**
```python
from scripts.qc_metrics import calculate_qc_metrics, batch_mad_outlier_detection

# Calculate basic QC metrics
adata = calculate_qc_metrics(adata, species="human")
# Adds: n_genes_by_counts, total_counts, pct_counts_mt, pct_counts_ribo

# Batch-aware MAD outlier detection (recommended for multi-batch)
if "batch" in adata.obs.columns:
    adata = batch_mad_outlier_detection(
        adata,
        batch_key="batch",
        metrics=["log1p_total_counts", "log1p_n_genes_by_counts", "pct_counts_mt"],
        nmads=5  # 5 MADs is conservative
    )
    # Adds: outlier (boolean column)
else:
    # Fixed thresholds for single batch
    from scripts.qc_metrics import mark_outliers_fixed
    adata = mark_outliers_fixed(
        adata,
        tissue="pbmc",  # or "brain", "tumor", etc.
        min_genes=200,
        max_genes=2500,
        max_pct_mt=5.0
    )
```

**Visualize QC:**
```python
from scripts.plot_qc import plot_qc_violin, plot_qc_scatter, plot_qc_by_batch

# Violin plots of QC metrics
plot_qc_violin(adata, batch_key="batch", output_dir="results/qc")

# Scatter plots (genes vs counts, colored by MT%)
plot_qc_scatter(adata, output_dir="results/qc")

# Per-batch QC distributions
plot_qc_by_batch(adata, batch_key="batch", output_dir="results/qc")
```

---

### Step 3: Doublet Detection and Filtering

**Run doublet detection:**
```python
from scripts.filter_cells import (
    run_scrublet_detection,
    filter_by_mad_outliers,
    filter_cells_by_tissue
)

# Scrublet doublet detection (per batch)
adata = run_scrublet_detection(
    adata,
    batch_key="batch",  # Run separately per batch
    expected_doublet_rate=0.06,  # Adjust based on cell loading
    min_counts=2,
    min_cells=3,
    n_prin_comps=30
)
# Adds: doublet_score, predicted_doublet columns

# Visualize doublet scores
from scripts.plot_qc import plot_doublet_scores
plot_doublet_scores(adata, output_dir="results/qc")
```

**Filter cells:**
```python
# Filter using MAD outliers + doublets
adata_filtered = filter_by_mad_outliers(
    adata,
    remove_doublets=True,
    doublet_score_threshold=0.25  # Adjust if needed
)

# Alternative: Filter by fixed tissue thresholds
adata_filtered = filter_cells_by_tissue(
    adata,
    tissue="pbmc",
    remove_doublets=True
)

# Check retention
n_before = adata.n_obs
n_after = adata_filtered.n_obs
retention = 100 * n_after / n_before
print(f"Cells retained: {n_after}/{n_before} ({retention:.1f}%)")
```

**QC checkpoint:** Aim for >70% retention. If lower, review thresholds.

---

## Phase 2: Normalization and Feature Selection

### Step 4: Normalize Data

**Standard normalization (recommended):**
```python
from scripts.normalize_data import run_standard_normalization

adata = run_standard_normalization(
    adata,
    target_sum=1e4,  # Scale to 10,000 counts per cell
    exclude_highly_expressed=False,
    log_transform=True
)
# Creates adata.layers["log1p_norm"]
```

**Alternative: Pearson residuals:**
```python
from scripts.normalize_data import run_pearson_residuals

adata = run_pearson_residuals(
    adata,
    theta=100,  # Overdispersion parameter
    clip=None   # Don't clip residuals
)
# Creates adata.layers["pearson_residuals"]
```

**When to use Pearson residuals:** Alternative to standard normalization, handles heteroscedastic data differently. See [scanpy_best_practices.md](scanpy_best_practices.md) for comparison.

---

### Step 5: Find Variable Genes and Run PCA

**Identify highly variable genes:**
```python
from scripts.find_variable_genes import find_highly_variable_genes

adata = find_highly_variable_genes(
    adata,
    n_top_genes=2000,
    flavor="seurat_v3",  # or "seurat", "cell_ranger"
    batch_key="batch"    # Optional: correct for batch
)
# Adds: highly_variable, means, dispersions columns to adata.var
```

**Scale data:**
```python
from scripts.scale_and_pca import scale_data

adata = scale_data(
    adata,
    max_value=10,  # Clip to ±10 std dev
    vars_to_regress=["total_counts", "pct_counts_mt"]  # Optional
)
# Creates adata.X (scaled) and stores raw in adata.layers["log1p_norm"]
```

**Run PCA:**
```python
from scripts.scale_and_pca import run_pca_analysis, plot_pca_variance

adata = run_pca_analysis(adata, n_pcs=50)
# Creates adata.obsm["X_pca"]

# Visualize variance explained
plot_pca_variance(adata, output_dir="results/pca")

# Determine number of PCs to use
from scripts.scale_and_pca import estimate_n_pcs
n_pcs = estimate_n_pcs(adata, variance_threshold=0.02)
print(f"Recommended PCs: {n_pcs}")
```

---

## Phase 3: Batch Integration (Multi-Batch Only)

### Step 6a: scVI Integration

**Setup and train scVI model:**
```python
from scripts.integrate_scvi import run_scvi_integration

adata = run_scvi_integration(
    adata,
    batch_key="batch",
    n_latent=30,       # Latent dimensions (20-50 typical)
    n_layers=2,        # Hidden layers
    max_epochs=400,    # Training epochs
    early_stopping=True,
    use_gpu=True       # Requires GPU
)
# Creates adata.obsm["X_scVI"] and stores model
```

**scANVI (semi-supervised with labels):**
```python
from scripts.integrate_scvi import run_scanvi_integration

adata = run_scanvi_integration(
    adata,
    batch_key="batch",
    labels_key="cell_type_coarse",  # Partial labels
    unlabeled_category="Unknown",
    n_latent=30,
    max_epochs=400
)
# Creates adata.obsm["X_scANVI"]
```

---

### Step 6b: Harmony Integration (Alternative)

**Run Harmony:**
```python
from scripts.integrate_scvi import run_harmony_integration

adata = run_harmony_integration(
    adata,
    batch_key="batch",
    basis="X_pca",     # Run on PCA
    n_pcs=30,          # Use first 30 PCs
    theta=2.0,         # Diversity clustering penalty
    max_iter=10
)
# Creates adata.obsm["X_pca_harmony"]
```

---

### Step 6c: Integration Diagnostics

**Compute integration quality metrics:**
```python
from scripts.integration_diagnostics import (
    compute_lisi_scores,
    compute_asw_scores,
    plot_integration_metrics,
    compare_integration_methods
)

# LISI scores (Local Inverse Simpson's Index)
lisi_scores = compute_lisi_scores(
    adata,
    batch_key="batch",
    label_key="cell_type",
    use_rep="X_scVI",  # or "X_scANVI", "X_pca_harmony"
    perplexity=30
)
# Returns dict with "batch_LISI" and "celltype_LISI"

# ASW scores (Average Silhouette Width)
asw_scores = compute_asw_scores(
    adata,
    batch_key="batch",
    label_key="cell_type",
    use_rep="X_scVI"
)
# Returns dict with "batch_ASW" and "celltype_ASW"

# Visualize metrics
plot_integration_metrics(
    adata,
    lisi_scores,
    asw_scores,
    output_dir="results/integration"
)

# Compare before/after
compare_integration_methods(
    adata,
    batch_key="batch",
    representations=["X_pca", "X_scVI"],
    output_dir="results/integration"
)
```

**Success criteria:**
- **Batch LISI ≈ 1:** Good batch mixing
- **Cell type LISI ≈ n_celltypes:** Biology preserved
- **Batch ASW ≈ 0:** No batch clustering
- **Cell type ASW ≈ 1:** Strong cell type clustering

---

## Phase 4: Clustering and Visualization

### Step 7: Build Neighbor Graph and Cluster

**Build neighbor graph:**
```python
from scripts.cluster_cells import build_neighbor_graph

# Use integrated representation if available
use_rep = "X_scVI" if "X_scVI" in adata.obsm else "X_pca"

adata = build_neighbor_graph(
    adata,
    n_neighbors=10,    # Typical: 10-30
    n_pcs=30,          # Only used if use_rep="X_pca"
    use_rep=use_rep,
    metric="euclidean"
)
# Creates adata.obsp["distances"] and adata.obsp["connectivities"]
```

**Leiden clustering at multiple resolutions:**
```python
from scripts.cluster_cells import cluster_leiden_multiple_resolutions

adata = cluster_leiden_multiple_resolutions(
    adata,
    resolutions=[0.4, 0.6, 0.8, 1.0],
    random_state=42
)
# Adds: leiden_0.4, leiden_0.6, leiden_0.8, leiden_1.0 to adata.obs

# Set active clustering
adata.obs["clusters"] = adata.obs["leiden_0.8"]
```

**Evaluate clustering stability:**
```python
from scripts.cluster_cells import evaluate_clustering_stability

stability_scores = evaluate_clustering_stability(
    adata,
    cluster_key="leiden_0.8",
    n_iterations=100
)
```

---

### Step 8: Run UMAP

**Compute UMAP:**
```python
from scripts.run_umap import run_umap_reduction

adata = run_umap_reduction(
    adata,
    n_neighbors=10,    # Match neighbor graph
    min_dist=0.5,      # Minimum distance between points
    spread=1.0,        # Scale of embedded points
    random_state=42
)
# Creates adata.obsm["X_umap"]
```

---

### Step 9: Visualize Results

**UMAP plots:**
```python
from scripts.plot_dimreduction import (
    plot_umap_clusters,
    plot_clustering_comparison,
    plot_feature_umap,
    plot_umap_batches
)

# Cluster UMAP
plot_umap_clusters(
    adata,
    cluster_key="leiden_0.8",
    output_dir="results/umap"
)

# Compare multiple resolutions
plot_clustering_comparison(
    adata,
    resolutions=[0.4, 0.6, 0.8, 1.0],
    output_dir="results/umap"
)

# Feature plots for QC metrics
plot_feature_umap(
    adata,
    features=["n_genes_by_counts", "total_counts", "pct_counts_mt"],
    output_dir="results/umap"
)

# Feature plots for marker genes
plot_feature_umap(
    adata,
    features=["CD3D", "CD8A", "CD4", "CD14", "MS4A1", "NKG7"],
    output_dir="results/umap"
)

# Batch distribution
plot_umap_batches(adata, batch_key="batch", output_dir="results/umap")
```

---

## Phase 5: Biological Interpretation

### Step 10: Find Marker Genes (Exploratory)

**Find markers for all clusters:**
```python
from scripts.find_markers import (
    find_all_cluster_markers,
    export_marker_tables,
    plot_top_markers_heatmap,
    plot_markers_dotplot
)

# Wilcoxon rank-sum test (default, fast)
all_markers = find_all_cluster_markers(
    adata,
    cluster_key="leiden_0.8",
    method="wilcoxon",
    min_logfoldchange=0.25,
    min_pct=0.1
)

# Alternative: t-test (faster but assumes normality)
# all_markers = find_all_cluster_markers(adata, method="t-test")

# Export results
export_marker_tables(all_markers, output_dir="results/markers")

# Heatmap of top markers
plot_top_markers_heatmap(
    adata,
    all_markers,
    n_top=10,
    cluster_key="leiden_0.8",
    output_dir="results/markers"
)

# Dot plot
plot_markers_dotplot(
    adata,
    all_markers,
    n_top=5,
    output_dir="results/markers"
)
```

**Important:** This is **exploratory DE** for characterizing clusters. For condition comparisons, use pseudobulk (Step 11).

---

### Step 11: Annotate Cell Types

**Manual annotation (recommended):**
```python
from scripts.annotate_celltypes import (
    annotate_clusters_manual,
    plot_annotated_umap,
    plot_annotation_markers
)

# Create annotation dictionary based on marker genes
annotations = {
    "0": "CD4 T cells",
    "1": "CD14+ Monocytes",
    "2": "CD8 T cells",
    "3": "B cells",
    "4": "NK cells",
    "5": "CD16+ Monocytes",
    "6": "Dendritic cells",
    "7": "Megakaryocytes"
}

adata = annotate_clusters_manual(
    adata,
    annotations,
    cluster_key="leiden_0.8",
    celltype_col="cell_type"
)

# Visualize
plot_annotated_umap(adata, output_dir="results/annotation")
plot_annotation_markers(adata, output_dir="results/annotation")
```

**Automated annotation with CellTypist:**
```python
from scripts.annotate_celltypes import annotate_with_celltypist

adata = annotate_with_celltypist(
    adata,
    model="Immune_All_Low.pkl",  # or "Immune_All_High.pkl"
    majority_voting=True
)
# Adds: predicted_labels, over_clustering columns
```

**Hybrid approach (recommended):**
```python
# Use automated for initial annotation
adata = annotate_with_celltypist(adata, model="Immune_All_Low.pkl")

# Review and refine manually
annotations_refined = {
    "CD4 T cells": "CD4 T cells",
    "CD8 T cells": "CD8 T cells",
    # ... merge or split as needed
}
adata = annotate_clusters_manual(adata, annotations_refined, cluster_key="predicted_labels")
```

---

## Phase 6: Inferential Analysis (Multi-Sample Only)

### Step 12: Pseudobulk Differential Expression

**Aggregate to pseudobulk:**
```python
from scripts.pseudobulk_de import (
    aggregate_to_pseudobulk,
    run_deseq2_analysis,
    export_de_results,
    plot_volcano,
    plot_ma
)

# Sum counts per sample × cell type
pseudobulk = aggregate_to_pseudobulk(
    adata,
    sample_key="sample_id",
    celltype_key="cell_type",
    min_cells=10,      # Minimum cells per sample-celltype
    min_counts=1       # Minimum total counts
)
# Returns dict of AnnData objects (one per cell type)
```

**Run DESeq2:**
```python
# Test condition effect per cell type
de_results = run_deseq2_analysis(
    pseudobulk,
    formula="~ batch + condition",  # Include batch as covariate
    contrast=["condition", "treated", "control"],
    celltype_key="cell_type",
    alpha=0.05,        # FDR threshold
    output_dir="results/pseudobulk_de"
)
# Returns dict of DataFrames with DE results
```

**Export and visualize:**
```python
# Export all results
export_de_results(de_results, output_dir="results/pseudobulk_de")

# Create plots for each cell type
for celltype in de_results.keys():
    # Volcano plot
    plot_volcano(
        de_results[celltype],
        celltype=celltype,
        padj_threshold=0.05,
        log2fc_threshold=0.5,
        output_dir="results/pseudobulk_de"
    )

    # MA plot
    plot_ma(
        de_results[celltype],
        celltype=celltype,
        output_dir="results/pseudobulk_de"
    )
```

**Important distinction:**
- **Exploratory (Step 10):** Wilcoxon on individual cells → Find cluster-defining genes
- **Inferential (Step 12):** DESeq2 on pseudobulk samples → Test condition effects with proper statistics

See [pseudobulk_de_guide.md](pseudobulk_de_guide.md) for detailed methodology.

---

## Phase 7: Export Results

### Step 13: Export Processed Data

**Save all results:**
```python
from scripts.export_results import export_anndata_results

export_anndata_results(
    adata,
    output_dir="results",
    cluster_key="cell_type",
    export_raw=True,           # Include raw counts
    export_metadata=True,      # Cell metadata CSV
    export_embeddings=True,    # PCA, UMAP coordinates
    export_markers=True        # Marker gene tables
)
```

**Outputs:**
- `adata_processed.h5ad` - Complete AnnData object
- `normalized_counts.csv` - Normalized expression
- `cell_metadata.csv` - Cell annotations
- `umap_coordinates.csv` - UMAP coordinates
- `cluster_markers_all.csv` - Marker genes
- Summary statistics and plots

---

## Complete End-to-End Example

See [eval/complete_example_analysis.py](../eval/complete_example_analysis.py) for a full working example on PBMC 3k data.


---
