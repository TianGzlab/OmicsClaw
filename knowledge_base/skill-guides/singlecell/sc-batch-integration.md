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
`sc-batch-integration` skill. This guide explains the real wrapper behavior and
does not imply that every metadata-declared backend is fully bundled today.

## Purpose

Use this guide when you need to decide:
- whether integration is needed or whether the user is really asking for simple joint visualization
- which integration backend is the best first pass
- which parameters matter first in the current wrapper

## Step 1: Inspect The Data First

Key properties to check:
- **Batch column**:
  - `batch_key` must exist and reflect real technical or sample structure
- **Label availability**:
  - `scanvi` only makes sense if usable labels already exist
- **Upstream state**:
  - PCA should exist or be recomputable
- **Runtime budget**:
  - scVI / scANVI are heavier than Harmony or BBKNN

Important implementation notes in current OmicsClaw:
- implemented paths are `harmony`, `scvi`, `scanvi`, `bbknn`, and `scanorama`
- `fastmnn`, `seurat_cca`, and `seurat_rpca` are declared but not bundled in the current wrapper
- `n_epochs` only matters for scVI / scANVI

## Step 2: Pick The Method Deliberately

| Method | Best first use | Strong starting parameters | Main caveat |
|--------|----------------|----------------------------|-------------|
| **harmony** | Fast first-pass correction when a batch column is clear | `batch_key` | Wrapper does not expose Harmony’s full low-level tuning surface |
| **scvi** | Best general deep generative baseline when count data and GPU/compute are available | `batch_key`, `n_epochs`, `no_gpu` | Heavier and slower than graph-based methods |
| **scanvi** | Best when existing labels should guide integration and transfer | `batch_key`, `n_epochs`, `no_gpu` | Requires labels; otherwise wrapper falls back to scVI |
| **bbknn** | Lightweight graph correction after PCA | `batch_key` | Mainly graph correction, not a generative latent model |
| **scanorama** | Useful panorama-style integration baseline | `batch_key` | Wrapper does not expose Scanorama’s full parameter set |

## Step 3: Always Show A Parameter Summary Before Running

```text
About to run batch integration
  Method: scvi
  Parameters: batch_key=batch, n_epochs=400, no_gpu=false
  Note: n_epochs is only meaningful for the scVI/scANVI paths.
```

## Step 4: Method-Specific Tuning Rules

### Harmony / BBKNN / Scanorama

Tune in this order:
1. `batch_key`

Guidance:
- treat `batch_key` as the most important scientific input because it defines what should be corrected
- use Harmony as the safest first-pass correction when the user has not chosen a deep model

Important warnings:
- do not promise Harmony `theta`, BBKNN `neighbors_within_batch`, or Scanorama `knn/sigma` as current public OmicsClaw parameters

### scVI / scANVI

Tune in this order:
1. `batch_key`
2. `n_epochs`
3. `no_gpu`

Guidance:
- confirm the batch column before tuning epochs
- use `n_epochs` as the main runtime / convergence control in the current wrapper
- use `scanvi` only when meaningful labels exist

Important warnings:
- do not describe scANVI as a drop-in replacement for unlabeled integration
- do not expose `labels_key`, `unlabeled_category`, or architectural internals as current public wrapper knobs

## Step 5: What To Say After The Run

- If batches remain separated: question `batch_key` quality before changing methods.
- If clusters collapse biologically: explain possible over-correction.
- If scANVI falls back: say it was because usable labels were missing, not because the model “failed”.

## Step 6: Explain Outputs Using Method-Correct Language

- describe integrated embeddings as corrected latent or graph spaces, depending on the method
- describe batch-mixing tables as diagnostics, not universal quality scores
- describe `processed.h5ad` as the integrated AnnData used for downstream clustering and plotting

## Official References

- https://scanpy.readthedocs.io/en/latest/generated/scanpy.external.pp.harmony_integrate.html
- https://docs.scvi-tools.org/en/stable/api/reference/scvi.model.SCVI.html
- https://docs.scvi-tools.org/en/stable/api/reference/scvi.model.SCANVI.html
- https://bbknn.readthedocs.io/en/latest/bbknn.bbknn.html
- https://scanpy.readthedocs.io/en/latest/generated/scanpy.external.pp.scanorama_integrate.html

