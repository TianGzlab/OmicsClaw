---
doc_id: skill-guide-spatial-integrate
title: OmicsClaw Skill Guide — Spatial Integration
doc_type: method-reference
domains: [spatial]
related_skills: [spatial-integrate, spatial-integration, integrate]
search_terms: [spatial integration, batch correction, harmony, bbknn, scanorama, tuning]
priority: 0.8
---

# OmicsClaw Skill Guide — Spatial Integration

**Status**: implementation-aligned guide derived from the current OmicsClaw
`spatial-integrate` skill. This is **not** one of the 28 already validated
end-to-end workflows. It is a living guide for method selection, parameter
reasoning, and wrapper-specific caveats.

## Purpose

Use this guide when you need to decide:
- which integration method is the best first pass for the current dataset
- which parameters matter first in OmicsClaw's current wrapper
- how to explain the result without pretending that Harmony, BBKNN, and Scanorama have identical behavior

## Step 1: Inspect The Data First

If the dataset has not been inspected yet in this conversation, call
`inspect_data` first.

Key properties to check:
- **Batch count**:
  - `< 2`: integration should not run
  - `2 - 5`: small-to-moderate multi-sample setting
  - `> 5`: pay more attention to mixing strength and runtime
- **Batch-size imbalance**:
  - large imbalance can distort neighbor-graph methods and make over-correction easier to miss
- **Embedding availability**:
  - `obsm["X_pca"]` is required for all currently implemented methods
- **Current neighborhood / UMAP state**:
  - OmicsClaw recomputes UMAP after integration, but the pre-integration graph still affects the baseline diagnostics
- **Cell ordering by batch**:
  - the Scanpy Scanorama wrapper expects same-batch cells to be contiguous; OmicsClaw now sorts a temporary copy internally and restores original order afterward

Important implementation notes in current OmicsClaw:
- Harmony, BBKNN, and Scanorama are all run from `X_pca`.
- BBKNN corrects the **neighbor graph**, not the latent space itself.
- Harmony and Scanorama create new corrected embeddings (`X_pca_harmony`, `X_scanorama`).
- OmicsClaw reports normalized batch-mixing entropy before and after integration.
- If `leiden` labels are missing after integration, OmicsClaw computes them once for visualization and reporting.
- The standard Python result layer is now a recipe-driven gallery under `figures/`, and downstream visualization contracts are exported under `figure_data/`.

## Step 2: Pick The Method Deliberately

Use this quick guide when the user has not explicitly chosen a method:

| Method | Best first use | Strong starting parameters | Main caveat |
|--------|----------------|----------------------------|-------------|
| **Harmony** | Best default general-purpose integration on preprocessed PCA space | `harmony_theta=2.0`, `harmony_lambda=1.0`, `harmony_max_iter=10` | Too aggressive settings can blur real biological differences |
| **BBKNN** | Good graph-based integration when preserving local neighborhood structure matters | `bbknn_neighbors_within_batch=3`, `bbknn_n_pcs=30~50`, `bbknn_trim=null` | It does not generate a new corrected latent embedding |
| **Scanorama** | Strong option when batches only partially overlap or need panoramic stitching | `scanorama_knn=20`, `scanorama_sigma=15`, `scanorama_alpha=0.1`, `scanorama_batch_size=5000` | Matching can become too permissive or too strict depending on overlap structure |

Practical default decision order:
1. If the user just says "integrate these spatial samples" and gives no method, start with **Harmony**.
2. If the user specifically cares about a corrected neighbor graph for downstream UMAP / clustering, consider **BBKNN**.
3. Use **Scanorama** when batches have partial overlap, stronger non-linear shifts, or the user explicitly requests it.

## Step 3: Always Show A Parameter Summary Before Running

Before execution, tell the user what will be run in a short, concrete block:

```text
About to run spatial integration
  Method: Harmony
  Parameters: batch_key=sample_id, harmony_theta=2.0, harmony_lambda=1.0, harmony_max_iter=10
  Dataset: 18,420 spots across 4 batches
  Note: Harmony is a strong first pass because this is a moderate-size merged dataset with an existing PCA embedding.
```

## Step 4: Method-Specific Tuning Rules

### Harmony

Tune in this order:
1. `harmony_theta`
2. `harmony_lambda`
3. `harmony_max_iter`

Guidance:
- Start with `harmony_theta=2.0`.
- Raise `harmony_theta` when batches remain separated after integration.
- Lower `harmony_theta` when cell states appear over-mixed or biologically distinct structures collapse.
- Start with `harmony_lambda=1.0`.
- Lower `harmony_lambda` for stronger correction.
- Increase `harmony_lambda` to regularize the correction more conservatively.
- `harmony_lambda=-1` enables Harmony's automatic lambda estimation.
- Increase `harmony_max_iter` only when Harmony appears not to have converged.

Important warnings:
- Do not frame higher Harmony correction as automatically better. Stronger mixing can mean over-correction.
- If batch separation is mild and biology is strong, changing `theta` or `lambda` too aggressively can remove meaningful structure.

### BBKNN

Tune in this order:
1. `bbknn_neighbors_within_batch`
2. `bbknn_n_pcs`
3. `bbknn_trim`

Guidance:
- Start with `bbknn_neighbors_within_batch=3`.
- Increase `bbknn_neighbors_within_batch` when the integrated graph still shows strong batch islands.
- Keep `bbknn_n_pcs` in the `30~50` range for a first pass on typical spatial data.
- OmicsClaw automatically clamps `bbknn_n_pcs` to the number of PCs actually present in `X_pca`.
- Leave `bbknn_trim` unset at first to keep the package default.
- Add `bbknn_trim` only when the graph looks too dense or too many cross-batch edges are being retained.

Important warnings:
- BBKNN produces a corrected graph, not a new embedding. Describe downstream UMAP as being based on the BBKNN graph.
- If batches are extremely imbalanced, graph-based balancing can still leave subtle batch structure.

### Scanorama

Tune in this order:
1. `scanorama_knn`
2. `scanorama_sigma`
3. `scanorama_alpha`
4. `scanorama_batch_size`

Guidance:
- Start with `scanorama_knn=20`.
- Increase `scanorama_knn` when batches share broad common structure and matching looks too sparse.
- Decrease `scanorama_knn` when unrelated cell states are being matched too easily.
- Start with `scanorama_sigma=15`.
- Increase `scanorama_sigma` for smoother corrections across broader manifolds.
- Decrease `scanorama_sigma` when correction appears too diffuse.
- Start with `scanorama_alpha=0.1`.
- Raise `scanorama_alpha` to demand stronger alignment evidence.
- Lower `scanorama_alpha` when true overlaps are being missed.
- Treat `scanorama_batch_size` mainly as a runtime / scalability knob, not the first scientific tuning target.

Important warnings:
- The current OmicsClaw flow uses the Scanpy wrapper on `X_pca`, not direct raw-expression integration.
- If different batches barely overlap biologically, Scanorama may either under-correct or create questionable matches depending on `knn` and `alpha`.

## Step 5: Large-Dataset Rules

For large merged datasets:
- Start with **Harmony** unless the user has a strong method preference.
- Use **BBKNN** when graph-based downstream clustering is the main goal.
- Increase `scanorama_batch_size` only when Scanorama is specifically needed and runtime becomes a bottleneck.
- Avoid turning too many knobs at once; change one method-specific parameter block between runs.

For highly imbalanced batches:
- Inspect batch-size ratios before trusting improved mixing metrics.
- Prefer conservative first-pass settings before pushing for maximal mixing.
- Watch for small rare batches being over-absorbed into larger cohorts.

## Step 6: What To Say After The Run

- If `batch_mixing_after` barely improves: mention possible causes including weak overlap between batches, an incorrect `batch_key`, or insufficient correction strength for the chosen method.
- If mixing improves but biological clusters collapse: flag likely over-correction and suggest more conservative parameters.
- If Harmony still leaves clear batch islands: suggest higher `harmony_theta`, lower `harmony_lambda`, or trying Scanorama.
- If BBKNN UMAP remains fragmented by batch: suggest increasing `bbknn_neighbors_within_batch`, reviewing `bbknn_n_pcs`, or switching to Harmony.
- If Scanorama appears too permissive: suggest lower `scanorama_knn` or higher `scanorama_alpha`.
- If Scanorama appears too conservative: suggest higher `scanorama_knn` or lower `scanorama_alpha`.
- If one batch remains isolated after any method: explicitly consider that the dataset may contain genuinely non-overlapping biology rather than a purely technical batch effect.

## Step 6.5: Explain The Visualization Contract Correctly

After a successful run, describe outputs in two layers:

- **Python standard gallery**: this is the canonical OmicsClaw result layer. It should be the first thing users inspect.
- **R customization layer**: this is optional and should consume `figure_data/` exports rather than recomputing integration results.

Current `spatial-integrate` gallery roles are:
- `overview`: before/after UMAP by batch
- `diagnostic`: UMAP by cluster and per-batch highlight panels
- `supporting`: batch-size summary
- `uncertainty`: batch-mixing entropy bars plus local entropy visualizations

If the user asks for prettier or journal-style figures, point them to:
- `figure_data/umap_before_points.csv`
- `figure_data/umap_after_points.csv`
- `figure_data/batch_sizes.csv`
- `figure_data/integration_metrics.csv`
- `reproducibility/r_visualization.sh`

## Step 7: Explain Results Using Method-Correct Language

When summarizing results to the user:
- For **Harmony**, refer to the result as a corrected PCA embedding in `X_pca_harmony`.
- For **BBKNN**, refer to the result as a corrected neighbor graph built from `X_pca`.
- For **Scanorama**, refer to the result as a corrected embedding in `X_scanorama`.
- For all methods, explain batch-mixing entropy as a lightweight diagnostic, not a definitive proof that integration quality is perfect.

Do **not** collapse all three methods into a generic "batch correction embedding"
description. The representation and failure modes differ in current OmicsClaw.
