---
doc_id: skill-guide-spatial-condition
title: OmicsClaw Skill Guide — Spatial Condition Comparison
doc_type: method-reference
domains: [spatial]
related_skills: [spatial-condition, spatial-condition-comparison, condition]
search_terms: [spatial condition comparison, pseudobulk, pydeseq2, deseq2, wilcoxon, replicates, treatment vs control]
priority: 0.8
---

# OmicsClaw Skill Guide — Spatial Condition Comparison

**Status**: implementation-aligned guide derived from the current OmicsClaw
`spatial-condition` skill. This is **not** one of the 28 already validated
end-to-end workflows. It is a living guide for method selection, parameter
reasoning, and wrapper-specific caveats.

## Purpose

Use this guide when you need to decide:

- whether `pydeseq2` or `wilcoxon` is the right first pass
- which pseudobulk design parameters matter first in the current wrapper
- how to explain replicate constraints and DE result semantics correctly
- how to separate the standard Python gallery from later R-side visualization
  refinement

## Step 1: Inspect The Design First

If the dataset has not been inspected yet in this conversation, call
`inspect_data` first.

Key properties to check:

- **Condition labels**: `obs[condition_key]` must contain at least two
  conditions.
- **Sample labels**: `obs[sample_key]` should represent biological replicates,
  not slide positions or arbitrary spot groups.
- **One sample, one condition**: a sample ID should not appear in multiple
  conditions.
- **Replicate count per condition**:
  - `>= 3` per condition: strong setting for `pydeseq2`
  - `2` per condition: workable but weaker
  - `< 2` per condition: not suitable for this wrapper
- **Raw counts availability**: `layers["counts"]` or `adata.raw` is strongly
  preferred for pseudobulk aggregation.
- **Cluster labels**: `cluster_key` should already exist or OmicsClaw will
  auto-compute `leiden` when using the default cluster key.

Important implementation notes in current OmicsClaw:

- Pseudobulk is always computed from raw counts.
- `pydeseq2` runs on raw pseudobulk counts and exposes official PyDESeq2
  controls including `fit_type`, `size_factors_fit_type`, `refit_cooks`,
  `alpha`, `cooks_filter`, `independent_filter`, and `n_cpus`.
- `wilcoxon` uses `scipy.stats.ranksums()` on internally transformed pseudobulk
  log-CPM values and exposes the official `alternative` argument.
- Contrasts with too few samples per condition are skipped and exported as such.
- OmicsClaw emits a canonical Python gallery under `figures/` plus
  `figure_data/` CSV exports for downstream Python or R restyling.

## Step 2: Pick The Method Deliberately

Use this quick guide when the user has not explicitly chosen a method:

| Method | Best first use | Strong starting parameters | Main caveat |
|--------|----------------|----------------------------|-------------|
| **PyDESeq2** | Default for replicate-aware pseudobulk DE | `min_counts_per_gene=10`, `min_samples_per_condition=2`, `pydeseq2_fit_type=parametric`, `pydeseq2_size_factors_fit_type=ratio`, `pydeseq2_alpha=0.05` | Needs adequate replicate structure; unstable or impossible on very sparse designs |
| **Wilcoxon** | Fallback when replicate counts are small or GLM fitting fails | `min_counts_per_gene=10`, `min_samples_per_condition=2`, `wilcoxon_alternative=two-sided` | Less model-aware than NB GLM and should not be oversold as equivalent evidence |

Practical default decision order:

1. If the user says "compare treated vs control" and replicate structure looks
   acceptable, start with **PyDESeq2**.
2. Use **Wilcoxon** when the user explicitly requests it, when replicate counts
   are marginal, or when PyDESeq2 is failing on a narrow subset.
3. If there are not at least two replicates per condition for a contrast, stop
   and explain that the design is not suitable for this wrapper.

## Step 3: Always Show A Parameter Summary Before Running

Before execution, tell the user what will be run in a short, concrete block:

```text
About to run spatial condition comparison
  Method: PyDESeq2
  Reference: control
  Pseudobulk design: sample_key=sample_id, cluster_key=leiden
  Parameters: min_counts_per_gene=10, min_samples_per_condition=2, pydeseq2_fit_type=parametric, pydeseq2_alpha=0.05
  Replicates: control=3, treatment=4
```

## Step 4: Method-Specific Tuning Rules

### PyDESeq2

Tune in this order:

1. `reference_condition`
2. `min_samples_per_condition`
3. `min_counts_per_gene`
4. `pydeseq2_fit_type`
5. `pydeseq2_size_factors_fit_type`
6. `pydeseq2_alpha`

Guidance:

- `reference_condition` is the first interpretive lever because it determines
  the sign of `log2fc`.
- Start with `min_samples_per_condition=2`, but prefer `>=3` in practice.
- Keep `min_counts_per_gene=10` unless the gene space is too sparse or too
  broad for the question.
- Start with `pydeseq2_fit_type=parametric`; switch to `mean` only when the
  parametric dispersion fit is unstable.
- Start with `pydeseq2_size_factors_fit_type=ratio`; consider `poscounts` when
  zeros are pervasive.
- Keep `pydeseq2_alpha=0.05` unless the user explicitly wants a different FDR
  target.

Important warnings:

- Do not use PyDESeq2 on normalized/log-transformed pseudobulk inputs.
- Do not interpret a sample ID that mixes multiple conditions as valid design
  metadata.
- `pydeseq2_refit_cooks`, `pydeseq2_cooks_filter`, and
  `pydeseq2_independent_filter` should usually stay on for a first pass.

### Wilcoxon

Tune in this order:

1. `reference_condition`
2. `min_samples_per_condition`
3. `min_counts_per_gene`
4. `wilcoxon_alternative`

Guidance:

- Use `wilcoxon_alternative=two-sided` as the default.
- Switch to `greater` or `less` only when the biological hypothesis is
  explicitly directional.
- Keep `min_samples_per_condition=2`; if you do not have two samples per group,
  the wrapper should not be trusted for inferential comparison.
- Keep `min_counts_per_gene=10` as the initial gene filter.

Important warnings:

- Wilcoxon here is a fallback on transformed pseudobulk profiles, not a
  drop-in replacement for replicate-rich NB-GLM inference.
- Do not collapse its evidence level into "equivalent to DESeq2" when
  presenting results.

## Step 5: Large-Dataset Rules

For many spots but modest replicate counts:

- Replicate count matters more than spot count.
- A dataset with 100k spots and only one sample per condition is still weak for
  condition inference.

For many clusters:

- Use an existing biologically motivated `cluster_key` when available.
- If dozens of clusters are tested, expect some contrasts to be skipped because
  cluster-specific replicate support is too low.

## Step 6: What To Say After The Run

- If many contrasts were skipped: mention insufficient replicate support per
  condition or aggressive gene filtering.
- If almost no genes are significant: mention low replicate count, small effect
  sizes, or too-strict filtering.
- If PyDESeq2 fell back to Wilcoxon: say so explicitly and point to the
  contrast-specific method labels in the exported tables.
- If one condition dominates nearly all top genes in one cluster: suggest
  checking cluster composition and sample balance before over-interpreting.

## Step 7: Use The Visualization Layers Deliberately

Current OmicsClaw `spatial-condition` separates visualization into two layers:

- **Python standard gallery**:
  - canonical analysis output
  - emitted under `figures/` with `figures/manifest.json`
  - should be the default artifact used in interactive analysis and routine
    reporting
- **R customization layer**:
  - optional refinement layer
  - should consume `figure_data/*.csv`
  - should not rerun PyDESeq2 or Wilcoxon just to restyle figures

Practical rule:

1. Use the Python gallery to confirm the science and the narrative structure.
2. Use the R layer only when the user explicitly wants publication styling,
   panel composition, or deeper aesthetic control.
3. If an R script needs extra inputs, export them from Python first instead of
   embedding DE recomputation inside the plotting layer.

## Step 8: Explain Results Using Method-Correct Language

When summarizing results to the user:

- For **PyDESeq2**, refer to the results as pseudobulk NB-GLM differential
  expression.
- For **Wilcoxon**, refer to the results as pseudobulk rank-sum fallback
  results.

Do **not** describe both outputs as identical evidence just because they share
`log2fc` and adjusted p-values in the exported table.
