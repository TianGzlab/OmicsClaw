---
doc_id: skill-guide-sc-doublet-detection
title: OmicsClaw Skill Guide — SC Doublet Detection
doc_type: method-reference
domains: [singlecell]
related_skills: [sc-doublet-detection, sc-doublet]
search_terms: [doublet detection, Scrublet, DoubletDetection, DoubletFinder, scDblFinder, scds, expected doublet rate]
priority: 0.8
---

# OmicsClaw Skill Guide — SC Doublet Detection

## When To Use It

Use this skill when you have already reviewed basic QC and want to label likely multiplets before trusting final clusters, annotation, or DE results.

Common OmicsClaw path:

1. `sc-qc`
2. `sc-doublet-detection`
3. keep singlets if the calls look credible
4. `sc-preprocessing`
5. `sc-clustering`

If the object is already preprocessed, the skill still works as long as raw counts are available in `layers["counts"]`, aligned `adata.raw`, or count-like `adata.X`.

## Method Selection

| Method | Best first use | Main public controls | Main caveat |
|--------|----------------|----------------------|-------------|
| `scrublet` | Default Python first pass | `expected_doublet_rate`, optional `batch_key`, optional `threshold` | `threshold` is Scrublet-only |
| `doubletdetection` | Python consensus classifier from the SCOP method family | `doubletdetection_n_iters`, optional `doubletdetection_standard_scaling` | wrapper records `expected_doublet_rate` for context only |
| `doubletfinder` | Seurat-style R path | `expected_doublet_rate` | may fall back to `scdblfinder` |
| `scdblfinder` | clean Bioconductor default | `expected_doublet_rate` | advanced scDblFinder knobs stay hidden |
| `scds` | score-family alternative from Bioconductor | `expected_doublet_rate`, `scds_mode` | wrapper converts the chosen score family into top-rate calls; `cxds` is the safest first pass in the current environment |

## How To Explain Parameters To Users

- Start with the **method**
- Then explain the **one or two knobs that actually matter for that method**
- Do not dump every backend parameter at once

Examples:

- `scrublet`
  - `expected_doublet_rate`
  - `batch_key` if captures/samples are mixed
  - `threshold` only when automatic calls look clearly wrong
- `doubletdetection`
  - `doubletdetection_n_iters`
  - optional `doubletdetection_standard_scaling`
- `scds`
  - `scds_mode`
  - `expected_doublet_rate`

## Output Interpretation

Standard output columns:

- `doublet_score`
- `predicted_doublet`
- `doublet_classification`

Interpret them this way:

- `doublet_score`: backend-specific evidence score, not a universal probability
- `predicted_doublet`: wrapper boolean call
- `doublet_classification`: human-readable label

## What To Say After The Run

- Review the histogram and embedding plots first
- If many doublets localize to specific clusters or bridges, treat them as a real branch to inspect
- If you accept the calls, keep singlets and rerun preprocessing / clustering for the final downstream object
- If users ask whether OmicsClaw already removed the cells, answer clearly: **no, it only annotated them**
