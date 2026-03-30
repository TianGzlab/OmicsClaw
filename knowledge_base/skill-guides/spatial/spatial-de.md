---
doc_id: skill-guide-spatial-de
title: OmicsClaw Skill Guide — Spatial Differential Expression
doc_type: method-reference
domains: [spatial]
related_skills: [spatial-de, de]
search_terms: [spatial differential expression, marker genes, wilcoxon, t-test, pydeseq2, pseudobulk, sample-aware DE]
priority: 0.8
---

# OmicsClaw Skill Guide — Spatial Differential Expression

**Status**: implementation-aligned guide derived from the current OmicsClaw
`spatial-de` skill. This is **not** one of the 28 already validated end-to-end
workflows. It is a living guide for method selection, parameter reasoning, and
wrapper-specific caveats.

## Purpose

Use this guide when you need to decide:

- whether the user needs exploratory Scanpy marker ranking or sample-aware
  pseudobulk inference
- which parameters matter first for the chosen method
- how to explain result semantics without blurring marker discovery and
  replicate-aware differential expression
- how to separate the standard Python gallery from later R-side visualization
  refinement

## Step 1: Inspect The Data First

If the dataset has not been inspected yet in this conversation, call
`inspect_data` first.

Key properties to check:

- **Group labels**: `obs[groupby]` must contain at least two groups.
- **Expression representation**:
  - `adata.X` should be log-normalized for `wilcoxon` / `t-test`.
  - `layers["counts"]` or `adata.raw` is strongly preferred for `pydeseq2`.
- **Sample labels**:
  - `obs[sample_key]` is required for `pydeseq2`.
  - it should represent biological replicates, not arbitrary spot chunks.
- **Comparison goal**:
  - cluster markers / fast ranking: Scanpy first
  - explicit two-group inference with biological replicate structure: `pydeseq2`
- **Group overlap across samples**:
  - if the same samples contribute to both groups, OmicsClaw can use a paired
    design in the PyDESeq2 path
  - if samples belong to only one group each, OmicsClaw uses `~ condition`
- **Counts coverage per sample x group**:
  - low spot counts strongly affect `min_cells_per_sample`
  - very sparse genes interact with `min_counts_per_gene`

Important implementation notes in current OmicsClaw:

- `wilcoxon` and `t-test` both wrap `scanpy.tl.rank_genes_groups`.
- `filter_markers` exposes the official
  `scanpy.tl.filter_rank_genes_groups(...)` post-filter layer.
- `pydeseq2` is intentionally restricted to explicit two-group comparisons.
- OmicsClaw does **not** random-split cells into fake DESeq2 replicates.
- If `groupby=leiden` is missing, the wrapper can auto-compute Leiden labels.
- OmicsClaw emits a canonical Python gallery under `figures/` plus
  `figure_data/` CSV exports for downstream Python or R restyling.

## Step 2: Pick The Method Deliberately

Use this quick guide when the user has not explicitly chosen a method:

| Method | Best first use | Strong starting parameters | Main caveat |
|--------|----------------|----------------------------|-------------|
| **Wilcoxon** | Best default exploratory marker ranking for most clustered datasets | `scanpy_corr_method=benjamini-hochberg`, `filter_markers=true`, `min_in_group_fraction=0.25`, `min_fold_change=1.0` | Still spot/cell-level marker ranking, not replicate-aware sample inference |
| **t-test** | Fast first-pass marker screening | same Scanpy filter controls as Wilcoxon | Stronger parametric assumptions than Wilcoxon |
| **PyDESeq2** | Explicit two-group comparison with real biological sample structure | `sample_key=sample_id`, `min_cells_per_sample=10`, `min_counts_per_gene=10`, `pydeseq2_fit_type=parametric`, `pydeseq2_size_factors_fit_type=ratio`, `pydeseq2_alpha=0.05` | Requires real replicate structure and raw counts; not a substitute for arbitrary cluster-only comparisons without samples |

Practical default decision order:

1. If the user says "find marker genes" or "rank cluster markers", start with
   **Wilcoxon**.
2. Use **t-test** when the user wants a faster exploratory pass and accepts the
   stronger assumptions.
3. Use **PyDESeq2** only when the comparison is explicitly two-group and the
   dataset has a meaningful `sample_key`.
4. If the actual question is "treated vs control across replicates", check
   whether `spatial-condition` is the better skill.

## Step 3: Always Show A Parameter Summary Before Running

Before execution, tell the user what will be run in a short, concrete block:

```text
About to run spatial differential expression
  Method: PyDESeq2
  Comparison: leiden 0 vs 1
  Sample-aware design: sample_key=sample_id
  Parameters: min_cells_per_sample=10, min_counts_per_gene=10, pydeseq2_fit_type=parametric, pydeseq2_alpha=0.05
```

For Scanpy methods:

```text
About to run spatial differential expression
  Method: Wilcoxon
  Grouping: leiden
  Parameters: scanpy_corr_method=benjamini-hochberg, filter_markers=true, min_in_group_fraction=0.25, min_fold_change=1.0
```

## Step 4: Method-Specific Tuning Rules

### Wilcoxon

Tune in this order:

1. `groupby`
2. `scanpy_corr_method`
3. `filter_markers`
4. `min_in_group_fraction`
5. `min_fold_change`
6. `max_out_group_fraction`
7. `scanpy_tie_correct`

Guidance:

- Start with `scanpy_corr_method=benjamini-hochberg`.
- Keep `filter_markers=true` for the first pass unless the user explicitly wants
  raw ranking output.
- Use the default marker filter thresholds first; they are a reasonable balance
  between specificity and usability.
- Turn on `scanpy_pts` when detection fractions would help interpret markers.
- Only turn on `scanpy_rankby_abs` when the user explicitly wants ranking by
  absolute score rather than direction-aware marker emphasis.

Important warnings:

- Do not describe Wilcoxon marker ranking as replicate-aware inference.
- `scanpy_tie_correct` is method-specific; do not mention it for `t-test`.

### t-test

Tune in this order:

1. `groupby`
2. `scanpy_corr_method`
3. `filter_markers`
4. `min_in_group_fraction`
5. `min_fold_change`
6. `max_out_group_fraction`

Guidance:

- Use the same Scanpy post-filter defaults as Wilcoxon.
- Prefer `t-test` for fast first-pass ranking rather than final inference.
- If the user is concerned about non-normality or robustness, switch to
  Wilcoxon.

Important warnings:

- Do not oversell speed as inferential strength.
- If the dataset looks count-like in `adata.X`, stop and confirm preprocessing
  before running a Scanpy test.

### PyDESeq2

Tune in this order:

1. `group1` / `group2`
2. `sample_key`
3. `min_cells_per_sample`
4. `min_counts_per_gene`
5. `pydeseq2_fit_type`
6. `pydeseq2_size_factors_fit_type`
7. `pydeseq2_alpha`

Guidance:

- `group1` and `group2` must be explicit. This wrapper does not run PyDESeq2 as
  an all-groups marker screen.
- `sample_key` must represent biological replicates.
- Start with `min_cells_per_sample=10`; lower it only when the compared groups
  are sparse within samples and the user understands the tradeoff.
- Start with `min_counts_per_gene=10`.
- Start with `pydeseq2_fit_type=parametric`; switch to `mean` only when the
  dispersion trend is unstable.
- Start with `pydeseq2_size_factors_fit_type=ratio`; use `poscounts` when zeros
  dominate.
- Keep `pydeseq2_refit_cooks`, `pydeseq2_cooks_filter`, and
  `pydeseq2_independent_filter` on for a first pass.

Important warnings:

- Do not use PyDESeq2 when the only available "replicates" would be fabricated
  from the same sample.
- Do not present a cluster-only comparison with no sample structure as
  DESeq2-style evidence.
- If very few sample x group combinations survive `min_cells_per_sample`, the
  result may be impossible or weak even if the dataset has many total spots.

## Step 5: Large-Dataset Rules

For many spots but weak sample structure:

- A very large number of spots does not compensate for missing biological
  replicates in the PyDESeq2 path.
- In that situation, a Scanpy marker run may still be useful, but it should be
  presented as exploratory.

For many clusters:

- Use Scanpy first for broad marker screening.
- Reserve PyDESeq2 for the narrower two-group comparisons that actually matter.

## Step 6: What To Say After The Run

- If Scanpy returns many markers but PyDESeq2 returns few: explain that marker
  ranking and sample-aware inference operate at different evidence levels.
- If PyDESeq2 skips many sample-group combinations: mention insufficient cells
  per sample x group and point to `skipped_sample_groups.csv`.
- If almost no genes are significant: mention low replicate support, sparse
  pseudobulk profiles, or overly strict thresholds.
- If many top hits are mitochondrial or ribosomal: flag a preprocessing issue
  before over-interpreting biology.

## Step 7: Use The Visualization Layers Deliberately

Current OmicsClaw `spatial-de` separates visualization into two layers:

- **Python standard gallery**:
  - canonical analysis output
  - emitted under `figures/` with `figures/manifest.json`
  - should be the default artifact used in interactive analysis and routine
    reporting
- **R customization layer**:
  - optional refinement layer
  - should consume `figure_data/*.csv`
  - should not rerun Scanpy ranking or PyDESeq2 just to restyle figures

Practical rule:

1. Use the Python gallery to confirm the science and the narrative structure.
2. Use the R layer only when the user explicitly wants publication styling,
   panel composition, or deeper aesthetic control.
3. If an R script needs extra inputs, export them from Python first instead of
   embedding scientific recomputation inside the plotting layer.

## Step 8: Explain Results Using Method-Correct Language

When summarizing results to the user:

- For **Wilcoxon** and **t-test**, refer to the output as exploratory Scanpy
  marker ranking on log-normalized expression.
- For **PyDESeq2**, refer to the output as sample-aware pseudobulk NB-GLM
  differential expression.

Do **not** collapse all three methods into a generic "DE p-value list"
explanation. In current OmicsClaw they answer different scientific questions.
