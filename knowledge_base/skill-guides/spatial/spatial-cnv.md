---
doc_id: skill-guide-spatial-cnv
title: OmicsClaw Skill Guide — Spatial CNV
doc_type: method-reference
domains: [spatial]
related_skills: [spatial-cnv, cnv]
search_terms: [spatial cnv, infercnvpy, infercnv, numbat, copy number variation, aneuploidy, tumor clone, tuning, reference cells]
priority: 0.8
---

# OmicsClaw Skill Guide — Spatial CNV

**Status**: implementation-aligned guide derived from the current OmicsClaw
`spatial-cnv` skill. This is **not** one of the 28 already validated end-to-end
workflows. It is a living guide for method selection, parameter reasoning, and
wrapper-specific caveats.

## Purpose

Use this guide when you need to decide:

- whether `infercnvpy` or `numbat` is the correct first pass
- which parameters matter first in the current OmicsClaw wrapper
- how to explain CNV outputs without over-claiming that expression-derived CNV
  scores equal DNA-level truth
- how to separate the standard Python gallery from later R-side visualization
  refinement

## Step 1: Inspect The Data First

If the dataset has not been inspected yet in this conversation, call
`inspect_data` first.

Key properties to check:

- **Spot / cell count**:
  - `<= 5k`: small
  - `5k - 30k`: medium
  - `> 30k`: large
- **Spatial coordinates**: `obsm["spatial"]` should exist if spatial mapping is
  part of the expected output.
- **Gene genomic annotations**: `var["chromosome"]`, `var["start"]`,
  `var["end"]` are required for `infercnvpy`.
- **Expression representation**:
  - `adata.X` should contain log-normalized expression for `infercnvpy`
  - `layers["counts"]` or `adata.raw` is strongly preferred for `numbat`
- **Reference metadata**:
  - `infercnvpy` can run without explicit reference cells, but results are much
    easier to interpret when a diploid baseline is supplied
  - current OmicsClaw `numbat` wrapper requires `reference_key` and
    `reference_cat`
- **Allele counts availability**: `adata.obsm["allele_counts"]` must be
  present for `numbat`

Important implementation notes in current OmicsClaw:

- `infercnvpy` runs on `adata.X`, then OmicsClaw computes CNV PCA, neighbors,
  Leiden clusters, and `cnv_score`.
- `numbat` exports a lightweight h5ad plus an allele-count CSV into the R
  subprocess.
- Current OmicsClaw `numbat` support is best viewed as a structured wrapper
  around the official `run_numbat()` path; it is more dependency-sensitive than
  the default `infercnvpy` workflow.
- OmicsClaw defaults `infercnv_n_jobs=1` for reproducibility, even though
  infercnvpy can use more workers.

## Step 2: Pick The Method Deliberately

Use this quick guide when the user has not explicitly chosen a method:

| Method | Best first use | Strong starting parameters | Main caveat |
|--------|----------------|----------------------------|-------------|
| **infercnvpy** | Best baseline for most preprocessed spatial transcriptomics datasets | `window_size=100`, `step=10`, `infercnv_dynamic_threshold=1.5`, `infercnv_lfc_clip=3.0`, explicit reference if available | Expression-derived CNV screening depends strongly on the quality of the reference baseline |
| **Numbat** | Use when allele counts and a defensible diploid reference are available and clonal CNV structure matters | `numbat_max_entropy=0.8`, `numbat_min_llr=5`, `numbat_min_cells=50`, `numbat_ncores=1~4` | Requires raw counts, allele counts, R dependencies, and stronger input preparation |

Practical default decision order:

1. If the user just says "infer CNV" and provides no extra context, start with
   **infercnvpy**.
2. Use **Numbat** when the user specifically wants haplotype-aware or
   clone-oriented CNV inference and the required allele-count inputs exist.
3. If no clean diploid reference is available, explain that the baseline choice
   is part of the result before running either method.

## Step 3: Always Show A Parameter Summary Before Running

Before execution, tell the user what will be run in a short, concrete block:

```text
About to run spatial CNV inference
  Method: inferCNVpy
  Reference: cell_type in {Normal, Stroma}
  Parameters: window_size=100, step=10, infercnv_dynamic_threshold=1.5, infercnv_lfc_clip=3.0
  Dataset size: 12,842 spots × 4,000 genes
  Note: This is a strong first-pass expression-based CNV screen before heavier haplotype-aware workflows.
```

## Step 4: Method-Specific Tuning Rules

### inferCNVpy

Tune in this order:

1. `reference_key` / `reference_cat`
2. `window_size`
3. `step`
4. `infercnv_dynamic_threshold`
5. `infercnv_lfc_clip`

Guidance:

- The reference definition is the first scientific lever. A poor baseline can
  dominate the result more than any numeric parameter.
- Start with `window_size=100`, which matches infercnvpy's documented default.
- Increase `window_size` when broad arm-level events are the goal.
- Decrease `window_size` when the user wants finer local CNV structure and can
  tolerate higher noise.
- Start with `step=10`; lower it toward `1~5` for denser windows at higher
  runtime.
- Keep `infercnv_dynamic_threshold=1.5` for a first pass unless denoising is
  clearly too aggressive or too permissive.
- Keep `infercnv_lfc_clip=3.0` unless extreme outliers are dominating.

Important warnings:

- OmicsClaw excludes `chrX` / `chrY` by default because infercnvpy documents
  that default; include them only intentionally.
- `cnv_score` is an anomaly-style summary derived after CNV-space clustering.
  Do not describe it as a direct segment call.
- If no defensible reference is available, explain that an all-cells baseline is
  a fallback and may blur tumor-vs-normal separation.

### Numbat

Tune in this order:

1. `reference_key` / `reference_cat`
2. `numbat_max_entropy`
3. `numbat_min_llr`
4. `numbat_min_cells`
5. `numbat_ncores`

Guidance:

- In the current OmicsClaw wrapper, `reference_key` and `reference_cat` are
  required because they are used to construct `lambdas_ref`.
- Start with `numbat_max_entropy=0.8` for spatial RNA / Visium-like data, which
  follows the official spatial tutorial's more permissive recommendation.
- Start with `numbat_min_llr=5` as a conservative confidence threshold.
- Keep `numbat_min_cells=50` unless the dataset is small or the expected clone
  size is known to be smaller.
- Increase `numbat_ncores` when CPU is available and the dataset is large.

Important warnings:

- Do not run Numbat on log-normalized expression in place of raw counts.
- Missing or low-quality allele counts can dominate the failure mode even when
  expression data look fine.
- If reference labels are weak or contaminated by tumor cells, the resulting CNA
  structure can be unstable.

## Step 5: Large-Dataset Rules

For `>30k` spots / cells:

- Prefer **infercnvpy** as the first pass.
- Keep `infercnv_chunksize=5000` unless memory pressure or throughput demands a
  different chunking strategy.
- Only move to **Numbat** if the user explicitly wants clone-aware inference and
  the dependency/input burden is justified.

For highly heterogeneous tumor datasets:

- Spend extra effort validating `reference_key` / `reference_cat`.
- If "normal" labels are uncertain, say so before running. Baseline uncertainty
  is not a minor detail.

## Step 6: What To Say After The Run

- If infercnvpy returns weak separation or uniformly low scores: mention that
  the reference baseline may be too broad, tumor burden may be low, or the
  dataset may not have strong expression-derived CNV signal.
- If infercnvpy scores are globally elevated: mention possible depth effects,
  normalization artifacts, or an invalid reference baseline.
- If Numbat fails early: mention missing allele counts, missing raw counts, or R
  dependency issues before proposing parameter tweaks.
- If Numbat returns very few calls: suggest revisiting `numbat_max_entropy`,
  `numbat_min_llr`, or the reference set.
- If many CNV segments appear but clone support is weak: suggest reviewing
  `numbat_min_cells` and the quality of the allele-count input.

## Step 7: Use The Visualization Layers Deliberately

Current OmicsClaw `spatial-cnv` separates visualization into two layers:

- **Python standard gallery**:
  - canonical analysis output
  - emitted under `figures/` with `figures/manifest.json`
  - should be the default artifact used in interactive analysis and ordinary
    reporting
- **R customization layer**:
  - optional refinement layer
  - should consume `figure_data/*.csv`
  - should not rerun inferCNVpy or Numbat just to restyle figures

Practical rule:

1. Use the Python gallery to confirm the science and narrative structure.
2. Use the R layer only when the user explicitly wants publication styling,
   panel composition, or deeper aesthetic control.
3. If an R script needs extra data, export that data from Python first instead
   of embedding scientific recomputation in the plotting layer.

## Step 8: Explain Results Using Method-Correct Language

When summarizing results to the user:

- For **infercnvpy**, refer to the main scalar output as `cnv_score` and call it
  an expression-derived CNV anomaly score.
- For **Numbat**, refer to the exported outputs as posterior / clone-aware CNV
  summaries and use `numbat_p_cnv` only as a compact cell-level summary when it
  is available.

Do **not** collapse both methods into a generic "CNV score" explanation.
The statistical assumptions and output semantics are different in current
OmicsClaw.
