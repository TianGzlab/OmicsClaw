---
doc_id: skill-guide-spatial-annotate
title: OmicsClaw Skill Guide — Spatial Annotation
doc_type: method-reference
domains: [spatial]
related_skills: [spatial-annotate, spatial-cell-annotation, annotate]
search_terms: [spatial annotation, cell type annotation, Tangram, scANVI, CellAssign, marker overlap, tuning, counts layer]
priority: 0.8
---

# OmicsClaw Skill Guide — Spatial Annotation

**Status**: implementation-aligned guide derived from the current OmicsClaw
`spatial-annotate` skill. This is **not** one of the already validated
end-to-end benchmark workflows. It is a living guide for method selection,
parameter reasoning, and wrapper-specific caveats.

## Purpose

Use this guide when you need to decide:
- which annotation method is the best first pass for a given dataset
- which parameters matter first in the current OmicsClaw wrapper
- how to explain matrix assumptions and confidence outputs correctly

## Step 1: Inspect The Data First

If the dataset has not been inspected yet in this conversation, call
`inspect_data` first.

Key properties to check:
- **Cluster labels**:
  - `marker_based` needs a usable cluster column such as `leiden`
  - if clusters are clearly poor, marker-based annotation will usually be poor too
- **Expression representation**:
  - `adata.X` should contain log-normalized expression for `marker_based` and `tangram`
  - `layers["counts"]` or `adata.raw` is strongly preferred for `scanvi` and `cellassign`
- **Reference readiness**:
  - Tangram and scANVI need a reference `.h5ad`
  - the requested `cell_type_key` must exist in `reference.obs`
  - there must be sufficient shared genes between reference and spatial data
- **Batch structure**:
  - if reference or spatial data spans multiple batches / samples, confirm whether a shared `batch_key` exists before using scANVI
- **Marker-panel readiness**:
  - CellAssign can use built-in human/mouse signatures
  - if a custom marker JSON is available, verify its gene symbols match the dataset naming convention

Important implementation notes in current OmicsClaw:
- `marker_based` uses `scanpy.tl.rank_genes_groups` plus `scanpy.tl.marker_gene_overlap`.
- `marker_based` defaults to `marker_overlap_normalize=reference`, which preserves the older overlap / signature-size behavior.
- `marker_padj_cutoff` only matters when `marker_n_genes=0`; this follows Scanpy's documented precedence.
- Tangram currently runs `mode="cells"` only.
- `tangram_train_genes` is an OmicsClaw wrapper control for the gene list passed into `tg.pp_adatas(..., genes=...)`; it is not a separate Tangram API flag.
- `scanvi_max_epochs` currently drives SCVI pretraining, SCANVI finetuning, and query adaptation in the current wrapper.
- `model` is an OmicsClaw wrapper path to a JSON marker-panel file for CellAssign, not a native CellAssign constructor argument.

## Step 2: Pick The Method Deliberately

Use this quick guide when the user has not explicitly chosen a method:

| Method | Best first use | Strong starting parameters | Main caveat |
|--------|----------------|----------------------------|-------------|
| **marker_based** | Best fast baseline when clusters are already reasonable and no reference is available | `cluster_key=leiden`, `marker_rank_method=wilcoxon`, `marker_n_genes=50`, `marker_overlap_method=overlap_count`, `marker_overlap_normalize=reference` | Quality is limited by cluster quality and marker-panel coverage |
| **Tangram** | Best when a good scRNA reference exists and the goal is projection onto space | `cell_type_key=cell_type`, `tangram_num_epochs=500`, `tangram_train_genes=2000`, `tangram_device=auto` | Requires strong shared-gene agreement and normalized expression on both sides |
| **scANVI** | Best for supervised label transfer with count data and possible batch structure | `layer=counts`, `batch_key=<if available>`, `scanvi_n_hidden=128`, `scanvi_n_latent=10`, `scanvi_n_layers=1`, `scanvi_max_epochs=100` | Requires raw counts and is slower / heavier than marker-based mode |
| **CellAssign** | Best when the user has a trustworthy marker panel and wants probabilistic count-based labels | `layer=counts`, `cellassign_max_epochs=400`, `batch_key=<if available>`, `model=<custom JSON or built-in species panel>` | Strongly dependent on marker-panel quality; not a good default when markers are weak |

Practical default decision order:
1. If the user only says "annotate my spatial data" and there is no reference, start with **marker_based**.
2. If a high-quality scRNA reference is available and the user wants projected labels on space, consider **Tangram** first.
3. If batch effects or more formal count-based transfer matter, prefer **scANVI** over Tangram.
4. If the user already has a curated marker panel and wants count-based probabilistic assignments, use **CellAssign**.

## Step 3: Always Show A Parameter Summary Before Running

Before execution, tell the user what will be run in a short, concrete block:

```text
About to run spatial annotation
  Method: scANVI
  Parameters: layer=counts, batch_key=sample_id, scanvi_n_latent=10, scanvi_max_epochs=100
  Reference: atlas_reference.h5ad
  Note: This is a count-based transfer model, so the raw counts layer matters more than normalized adata.X.
```

## Step 4: Method-Specific Tuning Rules

### Marker-Based

Tune in this order:
1. `cluster_key`
2. `marker_rank_method`
3. `marker_n_genes`
4. `marker_overlap_method`
5. `marker_overlap_normalize`
6. `marker_padj_cutoff`

Guidance:
- Start with `cluster_key=leiden` only if that clustering already looks biologically plausible.
- Keep `marker_rank_method=wilcoxon` as the safest first pass.
- Start with `marker_n_genes=50`.
- If you want all significant markers instead of a fixed top-N list, set `marker_n_genes=0` and then use `marker_padj_cutoff`.
- Keep `marker_overlap_method=overlap_count` and `marker_overlap_normalize=reference` for a simple, interpretable baseline.
- Use `overlap_coef` or `jaccard` only when the user specifically wants scale-free overlap metrics.

Important warnings:
- Do not describe this mode as probabilistic label transfer; it is a cluster-marker overlap baseline.
- If clusters are unstable or over-split, annotation quality will reflect that upstream problem rather than a downstream "annotation failure."

### Tangram

Tune in this order:
1. `cell_type_key`
2. `tangram_train_genes`
3. `tangram_num_epochs`
4. `tangram_device`

Guidance:
- Confirm the reference label column first; that is more important than tuning epochs.
- Start with `tangram_train_genes=2000` when reference HVGs are available.
- Use `tangram_train_genes=0` only when the user explicitly wants all shared genes and accepts the extra runtime.
- Keep `tangram_num_epochs=500` for a balanced first pass.
- Leave `tangram_device=auto` unless the user needs to force CPU or a specific accelerator.

Important warnings:
- Tangram assumes normalized expression on both sides; do not feed raw counts as the primary matrix.
- The current OmicsClaw wrapper uses `mode="cells"` only. Do not promise cluster-mode Tangram behavior unless the implementation changes.

### scANVI

Tune in this order:
1. `layer`
2. `batch_key`
3. `scanvi_n_latent`
4. `scanvi_n_hidden`
5. `scanvi_n_layers`
6. `scanvi_max_epochs`

Guidance:
- Treat `layer` as the first scientific decision: use raw counts, not log-normalized expression.
- If the data spans batches / samples and that metadata is trustworthy, provide `batch_key`.
- Keep `scanvi_n_latent=10`, `scanvi_n_hidden=128`, and `scanvi_n_layers=1` for the first pass.
- Increase `scanvi_n_latent` only when the tissue / reference complexity is clearly higher and runtime is acceptable.
- Raise `scanvi_max_epochs` only after confirming the first pass underfits or confidence remains poor.

Important warnings:
- Do not describe scANVI as just a classifier; the current wrapper uses SCVI pretraining plus SCANVI transfer on count data.
- If raw counts are missing and the wrapper falls back to `adata.X`, explain that the result is much less trustworthy.

### CellAssign

Tune in this order:
1. `model` or `species`
2. `layer`
3. `batch_key`
4. `cellassign_max_epochs`

Guidance:
- The strongest determinant is marker quality. Prefer a curated JSON marker panel when the user has one.
- If no custom panel exists, use the built-in species signatures as a baseline only.
- Keep `layer=counts` unless raw counts were stored under a different layer name.
- Add `batch_key` only when it captures real technical structure.
- Keep `cellassign_max_epochs=400` as the default first pass.

Important warnings:
- Do not oversell built-in signatures as a validated atlas; they are generic baseline signatures.
- If most marker genes are absent from the dataset, the issue is panel compatibility, not just training time.

## Step 5: Reference And Marker Rules

For Tangram or scANVI:
- Do not start until the reference file, label column, and shared genes are confirmed.
- If gene overlap is small, explain that transfer quality is limited by reference compatibility.

For CellAssign:
- Do not treat `species` as a biology-setting parameter if a custom marker JSON is supplied; in that case the JSON panel is the real annotation source.
- If marker symbols use a different naming convention from the dataset, fix that mismatch before rerunning.

## Step 6: What To Say After The Run

- If one label dominates almost all spots: mention possible reference mismatch, marker-panel collapse, or poor upstream clustering.
- If many labels are `Unknown` in `marker_based`: suggest checking `cluster_key`, marker quality, or trying a reference-based method.
- If Tangram gives diffuse predictions: mention possible weak gene overlap or inadequate training-gene selection.
- If scANVI confidence is low: mention possible missing / wrong counts layer, poor reference compatibility, or insufficient training epochs.
- If CellAssign confidence is low: mention missing marker genes, weak marker specificity, or incompatible panel design.
- If two methods disagree strongly: explain that marker overlap, spatial projection, and count-based latent models encode different assumptions; compare overlap and biological plausibility instead of declaring one method "wrong" by default.

## Step 7: Explain Results Using Method-Correct Language

When summarizing results to the user:
- For **marker_based**, refer to the key signal as **marker-overlap score**.
- For **Tangram**, refer to the result as **projected cell-type probabilities** or **projected labels**.
- For **scANVI**, refer to the result as **model-based predicted labels** with **confidence**.
- For **CellAssign**, refer to the result as **probabilistic marker-based assignments** with **confidence**.

Do **not** collapse all four methods into a generic "annotation score" explanation.
The score semantics are method-specific in the current OmicsClaw outputs.
