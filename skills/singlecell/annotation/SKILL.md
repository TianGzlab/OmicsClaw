---
name: sc-annotate
description: >-
  Automated cell type annotation using marker genes, CellTypist, SingleR, or scmap.
  Supports custom references and marker gene lists.
version: 0.1.0
author: OmicsClaw
license: MIT
tags: [singlecell, annotation, cell-type, CellTypist, SingleR, scmap]
metadata:
  omicsclaw:
    domain: singlecell
    requires:
      bins:
        - python3
      env: []
      config: []
    emoji: "🏷️"
    homepage: https://github.com/OmicsClaw/OmicsClaw
    os: [macos, linux]
    install:
      - kind: pip
        package: scanpy
        bins: []
    trigger_keywords:
      - cell type annotation
      - annotate cells
      - CellTypist
      - SingleR
      - marker gene annotation
---

# 🏷️ Single-Cell Annotation

You are **SC Annotate**, a specialised OmicsClaw agent for automated cell type annotation in single-cell data. Your role is to assign biological cell types to clusters or individual cells using reference datasets or marker gene sets.

## Why This Exists

- **Without it**: Manual marker-based annotation is subjective, requires extensive literature review, and is highly time-consuming.
- **With it**: Automated, reproducible cell type labelling using curated reference data and probabilistic models in minutes.
- **Why OmicsClaw**: Provides a unified interface across multiple annotation paradigms (marker-based, model-based, reference-based) enabling consensus annotation.

## Core Capabilities

1. **Marker-based annotation**: Assign cell types from known marker gene sets (e.g., PanglaoDB, CellMarker).
2. **CellTypist integration**: Leverage large-scale pre-trained logistic regression models for immune and pan-tissue data.
3. **Reference-based transfer**: Transfer labels from a reference AnnData to query data (e.g., scANVI, scmap, Ingest).
4. **Consensus scoring**: Compare predictions across multiple methods for high-confidence labels.

## Input Formats

| Format | Extension | Required Fields | Example |
|--------|-----------|-----------------|---------|
| AnnData (preprocessed) | `.h5ad` | `X` (normalized), PCA, clustering | `preprocessed.h5ad` |
| Marker list | `.csv`/`.json` | Gene to Cell Type mapping | `immune_markers.json` |

## Workflow

1. **Validate**: Check for normalized counts, highly variable genes, and existing clusters.
2. **Score**: Run the selected annotation engine (CellTypist, SingleR, or Marker scoring).
3. **Assign**: Resolve labels per cell or aggregate majority votes per cluster.
4. **Generate**: Save annotated h5ad, UMAP plots colored by cell type, and prediction probabilities.
5. **Report**: Write `report.md` detailing the used reference, predicted fractions, and confidence.

## CLI Reference

```bash
# Standard marker-based annotation
python skills/singlecell/annotation/sc_annotate.py \
  --input <processed.h5ad> --markers <markers.json> --output <report_dir>

# CellTypist immune model
python skills/singlecell/annotation/sc_annotate.py \
  --input <processed.h5ad> --method celltypist --model Immune_All_Low.pkl --output <report_dir>

# Demo mode
python omicsclaw.py run sc-annotate --demo
```

## Algorithm / Methodology

### 1. Model-based Annotation (CellTypist - Python)

**Goal:** Annotate cells using a pre-trained logistic regression classifier.

```python
import scanpy as sc
import celltypist
from celltypist import models

# Load data and ensure target is normalized to 10k counts
adata = sc.read_h5ad('processed.h5ad')
sc.pp.normalize_total(adata, target_sum=1e4)
sc.pp.log1p(adata)

# Download and load model (e.g., Immune_All_Low)
models.download_models(force_update=False)
model = models.Model.load(model='Immune_All_Low.pkl')

# Annotate
predictions = celltypist.annotate(adata, model=model, majority_voting=True)

# Transfer labels to AnnData
adata.obs['celltypist_prediction'] = predictions.predicted_labels.predicted_labels
adata.obs['celltypist_majority_voting'] = predictions.predicted_labels.majority_voting
```

### 2. Marker-based Scoring (Scanpy - Python)

**Goal:** Score clusters based on known marker gene expression.

```python
import scanpy as sc
import pandas as pd

# Define markers
marker_genes_dict = {
    'B cells': ['CD79A', 'MS4A1'],
    'T cells': ['CD3D', 'CD3E', 'CD8A', 'CD4'],
    'NK cells': ['GNLY', 'NKG7'],
    'Monocytes': ['CD14', 'LYZ']
}

# Calculate marker gene scores per cell
for cell_type, markers in marker_genes_dict.items():
    sc.tl.score_genes(adata, gene_list=markers, score_name=f'{cell_type}_score')

# Assign cluster labels based on highest mean score per cluster
cluster_scores = adata.obs.groupby('leiden')[[f'{ct}_score' for ct in marker_genes_dict.keys()]].mean()
cluster_annotations = cluster_scores.idxmax(axis=1).str.replace('_score', '')
adata.obs['cell_type'] = adata.obs['leiden'].map(cluster_annotations)
```

### 3. Reference-based Transfer (SingleR - R)

**Goal:** Compare query expression profile to reference transcriptomes.

```r
library(SingleR)
library(celldex)
library(Seurat)

# Load reference dataset
ref <- celldex::HumanPrimaryCellAtlasData()

# Query data from Seurat
query_counts <- GetAssayData(seurat_obj, assay = "RNA", slot = "data")

# Run SingleR
pred <- SingleR(test = query_counts, ref = ref, labels = ref$label.main)

# Add to Seurat object
seurat_obj$SingleR_labels <- pred$labels
```

## Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--method` | `celltypist` | Annotation method: celltypist, markers, singler |
| `--model` | `Immune_All_Low` | Pre-trained model name for CellTypist |
| `--markers` | none | Path to JSON/CSV marker dictionary |
| `--cluster-col` | `leiden` | Cluster column for majority voting |

## Example Queries

- "Annotate this PBMC dataset using the CellTypist immune model"
- "Use this marker gene JSON to label the clusters in my h5ad file"
- "Run SingleR against the Human Primary Cell Atlas for these cells"

## Output Structure

```
output_dir/
├── report.md
├── result.json
├── annotated.h5ad
├── figures/
│   ├── umap_celltype.png
│   ├── celltypist_probabilities.png
│   └── marker_dotplot.png
├── tables/
│   └── annotations.csv
└── reproducibility/
    ├── commands.sh
    ├── environment.yml
    └── checksums.sha256
```

## Dependencies

**Required**: scanpy >= 1.9, pandas, anndata
**Optional**: celltypist (Python), SingleR (R), scvi-tools (Python)

## Safety

- **Local-first**: No data upload. Pre-trained models are downloaded locally.
- **Disclaimer**: Every report includes the OmicsClaw disclaimer regarding automated assertions.
- **Audit trail**: Log all model definitions and threshold selections.

## Integration with Orchestrator

**Trigger conditions**:
- Presence of "annotate", "cell type", "CellTypist" in query.

**Chaining partners**:
- `sc-preprocess`: Pre-requisite for annotation (clusters and UMAP required).
- `sc-de`: Compute differentials between newly annotated cell types.

## Citations

- [CellTypist](https://www.science.org/doi/10.1126/science.abl5197) — Dominguez Conde et al., Science 2022
- [SingleR](https://doi.org/10.1038/s41590-018-0276-y) — Aran et al., Nature Immunology 2019
- [Scanpy](https://scanpy.readthedocs.io/) — Wolf et al., Genome Biology 2018
