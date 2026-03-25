"""Spatial-analysis-specific utilities for OmicsClaw skills.

This package contains all reusable analysis logic for the spatial domain,
organized by analysis type. Each skill script should import its core
functions from the corresponding _lib module.

Modules
-------
adata_utils      : AnnData helper functions (spatial key detection, metadata)
annotation       : Cell type annotation (marker-based, Tangram, scANVI, CellAssign)
cnv              : Copy number variation inference (inferCNVpy, Numbat)
communication    : Cell-cell communication (LIANA, CellPhoneDB, FastCCC, CellChat)
condition        : Pseudobulk condition comparison (PyDESeq2, Wilcoxon)
de               : Differential expression (rank_genes_groups, PyDESeq2)
deconvolution    : Cell type deconvolution (8 methods incl. R-based)
dependency_manager : Lazy dependency import and R environment validation
domains          : Spatial domain identification (6 algorithms)
enrichment       : Pathway enrichment (Enrichr, GSEA, ssGSEA)
exceptions       : Domain-specific exception classes
genes            : Spatially variable gene detection (Moran's, SpatialDE, SPARK-X)
integration      : Batch integration (Harmony, BBKNN, Scanorama)
loader           : Multi-platform spatial data loader
preprocessing    : QC, normalization, and embedding pipeline
register         : Multi-slice spatial registration (PASTE)
statistics       : Spatial statistics (10 analysis types)
trajectory       : Trajectory inference (DPT, CellRank)
velocity         : RNA velocity (scVelo, veloVI)
viz              : Unified visualization package
viz_utils        : Figure saving utilities
"""
