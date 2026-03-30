# R Quick Start Example

This guide shows how to run the clustering workflow using R.

## 5-Minute Example with Simulated Data

Test the workflow with simulated data (3 groups, 300 samples × 1000 genes):

```r
# 1. Load example data
source("scripts/load_example_data.R")
data_list <- load_example_clustering_data()
data <- data_list$data
metadata <- data_list$metadata

# 2. Run clustering
source("scripts/hierarchical_clustering.R")
result <- perform_hierarchical_clustering(data, k = 3)

# 3. Visualize
source("scripts/plot_cluster_heatmap.R")
plot_cluster_heatmap(data, result$clusters, output_file = "quick_test_results/heatmap.pdf")

cat(sprintf("✓ Clusters identified: %d\n", length(unique(result$clusters))))
```

**Expected output:** Dendrogram, PCA plots, silhouette plots, heatmaps in `quick_test_results/`

## R Installation

### Required R packages

| Package | Version | License | Commercial Use | Installation |
|---------|---------|---------|----------------|--------------|
| cluster | ≥2.1 | GPL (≥2) | ✅ Permitted | `install.packages('cluster')` |
| factoextra | ≥1.0 | GPL-2 | ✅ Permitted | `install.packages('factoextra')` |
| NbClust | ≥3.0 | GPL (≥2) | ✅ Permitted | `install.packages('NbClust')` |
| ComplexHeatmap | ≥2.10 | MIT | ✅ Permitted | `BiocManager::install('ComplexHeatmap')` |
| pheatmap | ≥1.0 | GPL (≥2) | ✅ Permitted | `install.packages('pheatmap')` |
| dendextend | ≥1.15 | GPL (≥2) | ✅ Permitted | `install.packages('dendextend')` |
| dbscan | ≥1.1 | GPL (≥2) | ✅ Permitted | `install.packages('dbscan')` |
| mclust | ≥5.4 | GPL (≥2) | ✅ Permitted | `install.packages('mclust')` |
| ggplot2 | ≥3.3 | MIT | ✅ Permitted | `install.packages('ggplot2')` |
| ggprism | ≥1.0 | GPL-3 | ✅ Permitted | `install.packages('ggprism')` |

**Optional:** clValid (GPL-2), fpc (GPL), clustree (GPL-3) - all permitted for commercial use

**Minimum R version:** R ≥4.0

### Quick install

```r
# CRAN packages
install.packages(c('cluster', 'factoextra', 'NbClust', 'pheatmap',
                   'dendextend', 'dbscan', 'mclust', 'ggplot2', 'ggprism'))

# Bioconductor packages
if (!require('BiocManager')) install.packages('BiocManager')
BiocManager::install('ComplexHeatmap')
```

**License Compliance:** All R packages use GPL, MIT, or similar permissive licenses that allow commercial use in AI agent applications. GPL allows commercial use and distribution.

## R-Specific Notes

### ComplexHeatmap for Publication Figures

R's ComplexHeatmap package provides superior heatmap visualization compared to Python alternatives. It's recommended for generating publication-quality figures even if you perform clustering in Python.

Example:
```r
library(ComplexHeatmap)
source("scripts/plot_cluster_heatmap.R")

# Load clustering results from Python
data <- read.csv("clustering_results/clustering_data_matrix.csv", row.names = 1)
clusters <- read.csv("clustering_results/clustering_assignments.csv")

# Generate publication heatmap
plot_cluster_heatmap(
    as.matrix(data),
    clusters$cluster,
    output_file = "publication_heatmap.pdf",
    width = 10,
    height = 12
)
```

### Mixing Python and R

You can leverage both ecosystems:
1. Use Python for clustering algorithms (scikit-learn, HDBSCAN)
2. Export results to CSV
3. Use R for heatmap visualization (ComplexHeatmap)

This gives you the best of both worlds: Python's comprehensive clustering implementations and R's superior biological visualization tools.
