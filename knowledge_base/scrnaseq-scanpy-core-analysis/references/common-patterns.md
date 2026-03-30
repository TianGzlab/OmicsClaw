# Common Analysis Patterns

This document provides complete code patterns for common single-cell RNA-seq analysis scenarios. Each pattern is a working end-to-end example that you can adapt to your data.

---

## Pattern 1: Standard 10X PBMC Analysis (Single Batch)

**Use case:** Basic analysis of filtered 10X Chromium PBMC data, single batch, no integration needed.

```python
import scanpy as sc
from scripts.setup_and_import import import_10x_data
from scripts.qc_metrics import calculate_qc_metrics, batch_mad_outlier_detection
from scripts.filter_cells import run_scrublet_detection, filter_by_mad_outliers
from scripts.normalize_data import run_standard_normalization
from scripts.find_variable_genes import find_highly_variable_genes
from scripts.scale_and_pca import scale_data, run_pca_analysis
from scripts.cluster_cells import build_neighbor_graph, cluster_leiden_multiple_resolutions
from scripts.run_umap import run_umap_reduction
from scripts.find_markers import find_all_cluster_markers
from scripts.annotate_celltypes import annotate_clusters_manual
from scripts.plot_dimreduction import plot_umap_clusters
from scripts.export_results import export_anndata_results

# 1. Load data
adata = import_10x_data("filtered_feature_bc_matrix/")

# 2. QC and filtering
adata = calculate_qc_metrics(adata, species="human")
adata = run_scrublet_detection(adata)
adata = filter_by_mad_outliers(adata, remove_doublets=True)

# 3. Normalize and find variable genes
adata = run_standard_normalization(adata, target_sum=1e4)
adata = find_highly_variable_genes(adata, n_top_genes=2000)

# 4. Scale and PCA
adata = scale_data(adata, vars_to_regress=["total_counts", "pct_counts_mt"])
adata = run_pca_analysis(adata, n_pcs=50)

# 5. Cluster and visualize
adata = build_neighbor_graph(adata, use_rep="X_pca", n_neighbors=10)
adata = cluster_leiden_multiple_resolutions(adata, resolutions=[0.4, 0.6, 0.8, 1.0])
adata = run_umap_reduction(adata, n_neighbors=10)

# 6. Find markers
all_markers = find_all_cluster_markers(adata, cluster_key="leiden_0.8")

# 7. Annotate (manual)
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
adata = annotate_clusters_manual(adata, annotations, cluster_key="leiden_0.8")

# 8. Visualize and export
plot_umap_clusters(adata, cluster_key="cell_type", output_dir="results/umap")
export_anndata_results(adata, output_dir="results", cluster_key="cell_type")
```

---

## Pattern 2: Multi-Batch Integration with scVI

**Use case:** Multiple batches (different donors, sequencing runs, etc.) requiring integration to remove batch effects.

```python
import scanpy as sc
from scripts.setup_and_import import import_10x_data
from scripts.qc_metrics import calculate_qc_metrics, batch_mad_outlier_detection
from scripts.filter_cells import run_scrublet_detection, filter_by_mad_outliers
from scripts.normalize_data import run_standard_normalization
from scripts.find_variable_genes import find_highly_variable_genes
from scripts.scale_and_pca import scale_data, run_pca_analysis
from scripts.integrate_scvi import run_scvi_integration
from scripts.integration_diagnostics import compute_lisi_scores, plot_integration_metrics
from scripts.cluster_cells import build_neighbor_graph, cluster_leiden_multiple_resolutions
from scripts.run_umap import run_umap_reduction
from scripts.find_markers import find_all_cluster_markers
from scripts.annotate_celltypes import annotate_clusters_manual
from scripts.export_results import export_anndata_results

# 1. Load data from multiple batches
adata_list = []
for batch_name in ["batch1", "batch2", "batch3"]:
    adata_batch = import_10x_data(f"data/{batch_name}/filtered_feature_bc_matrix/")
    adata_batch.obs["batch"] = batch_name
    adata_list.append(adata_batch)

adata = sc.concat(adata_list, join="outer")

# 2. QC and filtering (batch-aware)
adata = calculate_qc_metrics(adata, species="human")
adata = batch_mad_outlier_detection(adata, batch_key="batch", nmads=5)
adata = run_scrublet_detection(adata, batch_key="batch")
adata = filter_by_mad_outliers(adata, remove_doublets=True)

# 3. Normalize and find variable genes (batch-corrected)
adata = run_standard_normalization(adata, target_sum=1e4)
adata = find_highly_variable_genes(adata, n_top_genes=2000, batch_key="batch")

# 4. Scale and PCA
adata = scale_data(adata, vars_to_regress=["total_counts", "pct_counts_mt"])
adata = run_pca_analysis(adata, n_pcs=50)

# 5. Integrate batches with scVI
adata = run_scvi_integration(adata, batch_key="batch", n_latent=30, max_epochs=400)

# 6. Validate integration
lisi_scores = compute_lisi_scores(adata, batch_key="batch", use_rep="X_scVI")
print(f"Batch LISI: {lisi_scores['batch_LISI']:.2f} (target ≈1)")

plot_integration_metrics(adata, lisi_scores, output_dir="results/integration")

# 7. Cluster on integrated space
adata = build_neighbor_graph(adata, use_rep="X_scVI", n_neighbors=10)
adata = cluster_leiden_multiple_resolutions(adata, resolutions=[0.4, 0.6, 0.8, 1.0])
adata = run_umap_reduction(adata, n_neighbors=10)

# 8. Find markers and annotate
all_markers = find_all_cluster_markers(adata, cluster_key="leiden_0.8")
adata = annotate_clusters_manual(adata, annotations, cluster_key="leiden_0.8")

# 9. Export
export_anndata_results(adata, output_dir="results", cluster_key="cell_type")
```

---

## Pattern 3: Multi-Batch Integration with Harmony (CPU-friendly)

**Use case:** Same as Pattern 2, but using Harmony for faster CPU-based integration.

```python
import scanpy as sc
from scripts.setup_and_import import import_10x_data
from scripts.qc_metrics import calculate_qc_metrics, batch_mad_outlier_detection
from scripts.filter_cells import run_scrublet_detection, filter_by_mad_outliers
from scripts.normalize_data import run_standard_normalization
from scripts.find_variable_genes import find_highly_variable_genes
from scripts.scale_and_pca import scale_data, run_pca_analysis
from scripts.integrate_scvi import run_harmony_integration
from scripts.cluster_cells import build_neighbor_graph, cluster_leiden_multiple_resolutions
from scripts.run_umap import run_umap_reduction

# Steps 1-4: Same as Pattern 2 (load, QC, normalize, PCA)
# ...

# 5. Integrate batches with Harmony
adata = run_harmony_integration(
    adata,
    batch_key="batch",
    basis="X_pca",
    n_pcs=30,
    theta=2.0
)
# Creates adata.obsm["X_pca_harmony"]

# 6. Cluster on integrated space
adata = build_neighbor_graph(adata, use_rep="X_pca_harmony", n_neighbors=10)
adata = cluster_leiden_multiple_resolutions(adata, resolutions=[0.4, 0.6, 0.8])
adata = run_umap_reduction(adata, n_neighbors=10)

# Steps 7-8: Find markers, annotate, export
# ...
```

---

## Pattern 4: Raw Data with Ambient RNA Correction

**Use case:** Starting from raw CellRanger output with ambient RNA contamination (brain, lung, tumor tissues).

```python
from scripts.remove_ambient_rna import run_cellbender, estimate_contamination
from scripts.setup_and_import import import_10x_data
from scripts.qc_metrics import calculate_qc_metrics
from scripts.filter_cells import run_scrublet_detection, filter_by_mad_outliers

# 1. Remove ambient RNA with CellBender
adata = run_cellbender(
    raw_h5="raw_feature_bc_matrix.h5",
    expected_cells=10000,
    total_droplets=30000,
    output_dir="results/ambient"
)

# Check contamination level
contamination = estimate_contamination(adata)
print(f"Estimated contamination: {contamination:.1%}")

# 2. Continue with standard QC workflow
adata = calculate_qc_metrics(adata, species="human")
adata = run_scrublet_detection(adata)
adata = filter_by_mad_outliers(adata, remove_doublets=True)

# 3. Continue with normalization, clustering, etc.
# ...
```

---

## Pattern 5: Condition Comparison with Pseudobulk DE

**Use case:** Multi-sample experiment comparing conditions (treated vs control, disease vs healthy). Requires biological replicates.

```python
import scanpy as sc
from scripts.setup_and_import import import_10x_data
from scripts.qc_metrics import calculate_qc_metrics, batch_mad_outlier_detection
from scripts.filter_cells import run_scrublet_detection, filter_by_mad_outliers
from scripts.normalize_data import run_standard_normalization
from scripts.find_variable_genes import find_highly_variable_genes
from scripts.scale_and_pca import scale_data, run_pca_analysis
from scripts.cluster_cells import build_neighbor_graph, cluster_leiden_multiple_resolutions
from scripts.run_umap import run_umap_reduction
from scripts.find_markers import find_all_cluster_markers
from scripts.annotate_celltypes import annotate_clusters_manual
from scripts.pseudobulk_de import aggregate_to_pseudobulk, run_deseq2_analysis
from scripts.pseudobulk_de import plot_volcano, plot_ma

# 1. Load data with sample metadata
adata = import_10x_data("filtered_feature_bc_matrix/")

# Add sample metadata
sample_metadata = {
    "sample1": {"condition": "control", "donor": "donor1", "batch": "batch1"},
    "sample2": {"condition": "control", "donor": "donor2", "batch": "batch1"},
    "sample3": {"condition": "treated", "donor": "donor3", "batch": "batch2"},
    "sample4": {"condition": "treated", "donor": "donor4", "batch": "batch2"}
}

# Map metadata to cells
for col in ["condition", "donor", "batch"]:
    adata.obs[col] = adata.obs["sample_id"].map(lambda x: sample_metadata[x][col])

# 2-7. Standard workflow: QC, normalize, cluster, annotate
# ... (same as Pattern 1 or 2)

# 8. Pseudobulk aggregation
pseudobulk = aggregate_to_pseudobulk(
    adata,
    sample_key="sample_id",
    celltype_key="cell_type",
    min_cells=10,
    min_counts=1
)

# 9. Differential expression per cell type
de_results = run_deseq2_analysis(
    pseudobulk,
    formula="~ batch + condition",  # Include batch as covariate
    contrast=["condition", "treated", "control"],
    celltype_key="cell_type",
    alpha=0.05,
    output_dir="results/pseudobulk_de"
)

# 10. Visualize results for each cell type
for celltype in de_results.keys():
    plot_volcano(
        de_results[celltype],
        celltype=celltype,
        padj_threshold=0.05,
        log2fc_threshold=0.5,
        output_dir="results/pseudobulk_de"
    )
    plot_ma(de_results[celltype], celltype=celltype, output_dir="results/pseudobulk_de")

# 11. Export significant genes
for celltype, results in de_results.items():
    sig_genes = results[results["padj"] < 0.05]
    sig_genes.to_csv(f"results/pseudobulk_de/{celltype}_sig_genes.csv")
```

**Important:** Pseudobulk DE is the gold standard for condition comparisons. Do NOT use cell-level Wilcoxon tests for inferential statistics. See [pseudobulk_de_guide.md](pseudobulk_de_guide.md).

---

## Pattern 6: Automated Cell Type Annotation with CellTypist

**Use case:** Quick automated annotation using reference atlases, especially for immune cells.

```python
from scripts.setup_and_import import import_10x_data
from scripts.qc_metrics import calculate_qc_metrics
from scripts.filter_cells import run_scrublet_detection, filter_by_mad_outliers
from scripts.normalize_data import run_standard_normalization
from scripts.find_variable_genes import find_highly_variable_genes
from scripts.scale_and_pca import scale_data, run_pca_analysis
from scripts.cluster_cells import build_neighbor_graph, cluster_leiden_multiple_resolutions
from scripts.run_umap import run_umap_reduction
from scripts.annotate_celltypes import annotate_with_celltypist
from scripts.plot_dimreduction import plot_umap_clusters

# 1-5. Standard workflow through clustering
# ...

# 6. Automated annotation
adata = annotate_with_celltypist(
    adata,
    model="Immune_All_Low.pkl",  # or "Immune_All_High.pkl" for fine-grained
    majority_voting=True
)
# Adds: predicted_labels, over_clustering, conf_score columns

# 7. Visualize automated annotations
plot_umap_clusters(adata, cluster_key="predicted_labels", output_dir="results/annotation")

# 8. Optional: Refine manually based on cluster markers
from scripts.annotate_celltypes import annotate_clusters_manual

# Review automated labels and merge/split as needed
refined_annotations = {
    "CD4 T cells": "CD4 T cells",
    "CD8 T cells": "CD8 T cells",
    "NK cells": "NK cells",
    # ... adjust as needed
}
adata = annotate_clusters_manual(
    adata,
    refined_annotations,
    cluster_key="predicted_labels",
    celltype_col="cell_type_refined"
)
```

---

## Pattern 7: Hybrid Annotation (Automated + Manual)

**Use case:** Use automated annotation as starting point, then refine manually with domain knowledge.

```python
from scripts.find_markers import find_all_cluster_markers
from scripts.annotate_celltypes import annotate_with_celltypist, annotate_clusters_manual
from scripts.plot_dimreduction import plot_feature_umap

# 1. Initial automated annotation
adata = annotate_with_celltypist(adata, model="Immune_All_Low.pkl")

# 2. Find cluster markers
all_markers = find_all_cluster_markers(adata, cluster_key="leiden_0.8")

# 3. Review marker genes for each cluster
for cluster in adata.obs["leiden_0.8"].unique():
    cluster_markers = all_markers[all_markers["cluster"] == cluster].head(10)
    print(f"\nCluster {cluster}:")
    print(cluster_markers[["gene", "logfoldchange", "pval_adj"]])

# 4. Plot key markers to validate
marker_genes = ["CD3D", "CD4", "CD8A", "CD14", "MS4A1", "NKG7", "FCGR3A"]
plot_feature_umap(adata, features=marker_genes, output_dir="results/markers")

# 5. Manual refinement based on markers + automated labels
annotations_refined = {
    "0": "CD4 T cells",  # High CD3D, CD4
    "1": "CD14+ Monocytes",  # High CD14, low FCGR3A
    "2": "CD8 T cells",  # High CD3D, CD8A
    "3": "B cells",  # High MS4A1
    "4": "NK cells",  # High NKG7, low CD3D
    "5": "CD16+ Monocytes",  # High CD14, FCGR3A
    # ... continue for all clusters
}

adata = annotate_clusters_manual(
    adata,
    annotations_refined,
    cluster_key="leiden_0.8",
    celltype_col="cell_type"
)
```

---

## Pattern 8: Using Pearson Residuals Normalization

**Use case:** Alternative normalization method that handles heteroscedastic data differently.

```python
from scripts.setup_and_import import import_10x_data
from scripts.qc_metrics import calculate_qc_metrics
from scripts.filter_cells import run_scrublet_detection, filter_by_mad_outliers
from scripts.normalize_data import run_pearson_residuals
from scripts.find_variable_genes import find_highly_variable_genes
from scripts.scale_and_pca import run_pca_analysis
from scripts.cluster_cells import build_neighbor_graph, cluster_leiden_multiple_resolutions
from scripts.run_umap import run_umap_reduction

# 1-2. Load and QC
adata = import_10x_data("filtered_feature_bc_matrix/")
adata = calculate_qc_metrics(adata, species="human")
adata = run_scrublet_detection(adata)
adata = filter_by_mad_outliers(adata, remove_doublets=True)

# 3. Normalize with Pearson residuals (instead of standard)
adata = run_pearson_residuals(adata, theta=100, clip=None)
# Creates adata.layers["pearson_residuals"]

# 4. Find variable genes (on Pearson residuals)
adata = find_highly_variable_genes(adata, n_top_genes=2000)

# 5. PCA (no scaling needed, Pearson residuals already scaled)
adata = run_pca_analysis(adata, n_pcs=50)

# 6-8. Continue with clustering, annotation, etc.
# ...
```

**When to use:** Alternative to standard normalization. See [scanpy_best_practices.md](scanpy_best_practices.md) for comparison.

---

## Pattern 9: Custom Tissue-Specific QC Thresholds

**Use case:** Analyzing tissue with known QC characteristics different from PBMC (e.g., brain with higher MT%, tumor with higher gene counts).

```python
from scripts.setup_and_import import import_10x_data
from scripts.qc_metrics import calculate_qc_metrics, mark_outliers_fixed
from scripts.filter_cells import run_scrublet_detection, filter_cells_by_tissue
from scripts.plot_qc import plot_qc_violin, plot_qc_scatter

# 1. Load data
adata = import_10x_data("filtered_feature_bc_matrix/")

# 2. Calculate QC metrics
adata = calculate_qc_metrics(adata, species="human")

# 3. Visualize QC distributions
plot_qc_violin(adata, output_dir="results/qc")
plot_qc_scatter(adata, output_dir="results/qc")

# 4. Apply tissue-specific thresholds
# For brain tissue (example):
adata = mark_outliers_fixed(
    adata,
    tissue="custom",
    min_genes=500,     # Higher than PBMC (200)
    max_genes=6000,    # Higher than PBMC (2500)
    max_pct_mt=10.0    # Higher than PBMC (5%)
)

# 5. Doublet detection and filtering
adata = run_scrublet_detection(adata)
adata = filter_cells_by_tissue(adata, tissue="custom", remove_doublets=True)

# Check retention
print(f"Cells retained: {adata.n_obs}")
```

**See [qc_guidelines.md](qc_guidelines.md) for tissue-specific recommendations.**

---

## Pattern 10: scANVI Semi-Supervised Integration

**Use case:** Multi-batch data with partial cell type labels available (e.g., from one batch).

```python
from scripts.setup_and_import import import_10x_data
from scripts.qc_metrics import calculate_qc_metrics, batch_mad_outlier_detection
from scripts.filter_cells import run_scrublet_detection, filter_by_mad_outliers
from scripts.normalize_data import run_standard_normalization
from scripts.find_variable_genes import find_highly_variable_genes
from scripts.scale_and_pca import scale_data, run_pca_analysis
from scripts.integrate_scvi import run_scanvi_integration
from scripts.cluster_cells import build_neighbor_graph, cluster_leiden_multiple_resolutions
from scripts.run_umap import run_umap_reduction

# 1-4. Standard workflow through PCA
# ...

# 5. Add coarse cell type labels (if available for some cells)
# Example: One batch has prior annotations
adata.obs["cell_type_coarse"] = "Unknown"
adata.obs.loc[adata.obs["batch"] == "batch1", "cell_type_coarse"] = (
    adata.obs.loc[adata.obs["batch"] == "batch1", "prior_labels"]
)

# 6. Integrate with scANVI (semi-supervised)
adata = run_scanvi_integration(
    adata,
    batch_key="batch",
    labels_key="cell_type_coarse",
    unlabeled_category="Unknown",
    n_latent=30,
    max_epochs=400
)
# Propagates labels to unlabeled cells

# 7. Cluster and refine
adata = build_neighbor_graph(adata, use_rep="X_scANVI", n_neighbors=10)
adata = cluster_leiden_multiple_resolutions(adata, resolutions=[0.4, 0.6, 0.8])
adata = run_umap_reduction(adata)

# 8. Review propagated labels and refine
# ...
```

---

## Additional Resources

- **Complete working example:** [eval/complete_example_analysis.py](../eval/complete_example_analysis.py)
- **Decision guidance:** [decision-guide.md](decision-guide.md)
- **Detailed workflow:** [workflow-details.md](workflow-details.md)
- **Best practices:** [scanpy_best_practices.md](scanpy_best_practices.md)
- **Troubleshooting:** [troubleshooting_guide.md](troubleshooting_guide.md)
