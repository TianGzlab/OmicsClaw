---
doc_id: skill-guide-sc-batch-integration
title: OmicsClaw Skill Guide — SC Batch Integration
doc_type: method-reference
domains: [singlecell]
related_skills: [sc-batch-integration, sc-integrate]
search_terms: [single-cell batch integration, Harmony, scVI, scANVI, BBKNN, Scanorama, batch key, tuning]
priority: 0.8
---

# OmicsClaw Skill Guide — SC Batch Integration

**Status**: implementation-aligned guide derived from the current OmicsClaw
`sc-batch-integration` skill. This guide explains the real wrapper behavior,
including the public R-backed methods when the matching R stack is available.

## Purpose

Use this guide when you need to decide:
- whether integration is needed or whether the user is really asking for simple joint visualization
- which integration backend is the best first pass
- which parameters matter first in the current wrapper

## Step 1: Inspect The Data First

Key properties to check:
- **Input format**:
  - if the user starts from `.h5`, `.loom`, `.csv`, `.tsv`, or a 10x directory, the safer path is `sc-standardize-input` before integration
- **Input contract**:
  - if the `.h5ad` was not standardized by OmicsClaw, recommend `sc-standardize-input` first for more stable downstream behavior
- **Batch column**:
  - `batch_key` must exist and reflect real technical or sample structure
  - stop when the candidate column looks too close to a per-cell identifier or creates many tiny groups
- **Label availability**:
  - `scanvi` only makes sense if usable labels already exist
- **Upstream state**:
  - PCA should exist or be recomputable
  - when PCA / neighbors / cluster labels are all absent, the standard workflow should usually include `sc-preprocessing` before integration
- **Runtime budget**:
  - scVI / scANVI are heavier than Harmony or BBKNN
- **Matrix contract**:
  - `harmony`, `bbknn`, and `scanorama` operate on normalized / PCA-ready representations
  - `scvi`, `scanvi`, `fastmnn`, `seurat_cca`, and `seurat_rpca` should preserve or read raw counts from `layers["counts"]` when available
- **Input provenance**:
  - if counts may be hidden in `adata.raw` or `layers["counts"]`, recommend `sc-standardize-input` first

Important implementation notes in current OmicsClaw:
- implemented paths are `harmony`, `scvi`, `scanvi`, `bbknn`, `scanorama`, `fastmnn`, `seurat_cca`, and `seurat_rpca`
- the wrapper now loads multiple single-cell file formats through the shared loader, but integration is still safest after standardization and preprocessing
- the R-backed methods run through the shared H5AD bridge and depend on matching R packages
- `n_epochs` only matters for scVI / scANVI

## Step 1.5: Prefer The Workflow, Not Just The Final Skill

Recommended default path for messy external input:
1. `sc-standardize-input`
2. `sc-preprocessing`
3. `sc-batch-integration`
4. `sc-clustering`

Use direct integration only when:
- the user already has a trustworthy scRNA AnnData object
- batch/sample metadata are clear
- the matrix contract is understood
- the user explicitly wants to skip the earlier workflow stages

## Step 2: Pick The Method Deliberately

| Method | Best first use | Strong starting parameters | Main caveat |
|--------|----------------|----------------------------|-------------|
| **harmony** | Fast first-pass correction when a batch column is clear | `batch_key`, `harmony_theta`, `integration_pcs` | Wrapper still does not expose Harmony’s full low-level tuning surface |
| **scvi** | Best general deep generative baseline when count data and GPU/compute are available | `batch_key`, `n_epochs`, `n_latent`, `no_gpu` | Heavier and slower than graph-based methods |
| **scanvi** | Best when existing labels should guide integration and transfer | `batch_key`, `labels_key`, `n_epochs`, `n_latent`, `no_gpu` | Requires labels; otherwise wrapper falls back to scVI |
| **bbknn** | Lightweight graph correction after PCA | `batch_key`, `bbknn_neighbors_within_batch` | Mainly graph correction, not a generative latent model |
| **scanorama** | Useful panorama-style integration baseline | `batch_key`, `scanorama_knn` | Wrapper still does not expose Scanorama’s full parameter set |
| **fastmnn** | R-backed correction when users want batchelor fastMNN | `batch_key`, `integration_features`, `integration_pcs` | Requires the R batchelor stack and counts-aware input handling |
| **seurat_cca** | R-backed Seurat integration with CCA anchors | `batch_key`, `integration_features`, `integration_pcs` | Requires the R Seurat stack and counts-aware input handling |
| **seurat_rpca** | R-backed Seurat integration with RPCA anchors | `batch_key`, `integration_features`, `integration_pcs` | Requires the R Seurat stack and counts-aware input handling |

## Step 3: Always Show A Parameter Summary Before Running

```text
About to run batch integration
  Method: scvi
  Parameters: batch_key=batch, n_epochs=400, n_latent=30, no_gpu=false
  Note: `n_epochs`/`n_latent` are only meaningful for the scVI/scANVI paths.
```

## Step 4: Method-Specific Tuning Rules

### Harmony / BBKNN / Scanorama

Tune in this order:
1. `batch_key`
2. `harmony_theta`
3. `integration_pcs`

Guidance:
- treat `batch_key` as the most important scientific input because it defines what should be corrected
- use Harmony as the safest first-pass correction when the user has not chosen a deep model
- if `batch_key` produces many tiny groups or almost one group per cell, stop and ask for a better column before discussing method tuning

Important warnings:
- do not promise Harmony or Scanorama internals beyond the wrapper parameters already exposed

### scVI / scANVI

Tune in this order:
1. `batch_key`
2. `labels_key` for scANVI
3. `n_epochs`
4. `n_latent`
5. `no_gpu`

Guidance:
- confirm the batch column before tuning epochs
- use `n_epochs` as the main runtime / convergence control in the current wrapper
- use `scanvi` only when meaningful labels exist

Important warnings:
- do not describe scANVI as a drop-in replacement for unlabeled integration
- if no usable labels exist, stop and ask whether the user really wants `scanvi` or should switch to `scvi`

### fastMNN / Seurat CCA / Seurat RPCA

Tune in this order:
1. `batch_key`
2. `integration_features`
3. `integration_pcs`

Guidance:
- keep raw counts available in `layers["counts"]` before handing data to these backends
- describe these as R-backed integration paths, not as Python-native code paths
- if only one unique batch is present, do not run integration just because the wrapper can technically execute
- if the file has not been standardized or does not yet look preprocessed, recommend the upstream workflow before handing data to these methods

## Step 5: What To Say After The Run

- If batches remain separated: question `batch_key` quality before changing methods.
- If clusters collapse biologically: explain possible over-correction.
- If scANVI falls back: say it was because usable labels were missing, and report both the requested and executed methods rather than implying native scANVI output.
- If the integrated embedding looks acceptable: point users to `sc-clustering --use-rep <embedding_key>`.
- If no real batch column exists after review: say integration is unnecessary and return the user to the standard `sc-preprocessing -> sc-clustering` path.

## Step 6: Explain Outputs Using Method-Correct Language

- describe integrated embeddings as corrected latent or graph spaces, depending on the method
- describe batch-mixing tables as diagnostics, not universal quality scores
- describe `processed.h5ad` as the integrated AnnData that should usually feed into `sc-clustering` next

## Official References

- https://scanpy.readthedocs.io/en/latest/generated/scanpy.external.pp.harmony_integrate.html
- https://docs.scvi-tools.org/en/stable/api/reference/scvi.model.SCVI.html
- https://docs.scvi-tools.org/en/stable/api/reference/scvi.model.SCANVI.html
- https://bbknn.readthedocs.io/en/latest/bbknn.bbknn.html
- https://scanpy.readthedocs.io/en/latest/generated/scanpy.external.pp.scanorama_integrate.html
- https://bioconductor.org/packages/release/bioc/html/batchelor.html
- https://satijalab.org/seurat/reference/findintegrationanchors
