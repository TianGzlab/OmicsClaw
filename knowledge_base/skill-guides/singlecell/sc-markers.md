---
doc_id: skill-guide-sc-markers
title: OmicsClaw Skill Guide — SC Markers
doc_type: method-reference
domains: [singlecell]
related_skills: [sc-markers]
search_terms: [marker genes, rank_genes_groups, wilcoxon, logreg, cluster markers, tuning]
priority: 0.8
---

# OmicsClaw Skill Guide — SC Markers

**Status**: implementation-aligned guide derived from the current OmicsClaw
`sc-markers` skill. This guide is about cluster-level marker ranking, not
replicate-aware condition DE.

## Purpose

Use this guide when you need to decide:
- whether the user wants cluster markers or condition DE
- which ranking method is the best first pass
- which output parameters matter for interpretation

## Step 1: Inspect The Data First

Key properties to check:
- **Grouping column**:
  - `groupby` should represent meaningful clusters or labels
- **Upstream clustering quality**:
  - poor clusters lead to poor markers
- **Expression state**:
  - the wrapper expects preprocessed single-cell data

Important implementation notes in current OmicsClaw:
- methods are `wilcoxon`, `t-test`, and `logreg`
- `groupby` is the core scientific parameter
- `n_genes` and `n_top` mainly control exported results and visualization scope

## Step 2: Pick The Method Deliberately

| Method | Best first use | Strong starting parameters | Main caveat |
|--------|----------------|----------------------------|-------------|
| **wilcoxon** | Safest first-pass cluster marker ranking | `groupby`, `n_genes`, `n_top` | Still exploratory, not replicate-aware |
| **t-test** | Parametric alternative when users want a simple mean-shift test | `groupby`, `n_genes`, `n_top` | More sensitive to distribution assumptions |
| **logreg** | When users want classification-style marker ranking | `groupby`, `n_genes`, `n_top` | Do not oversell as minimal marker-panel selection |

## Step 3: Always Show A Parameter Summary Before Running

```text
About to run cluster marker discovery
  Method: wilcoxon
  Parameters: groupby=leiden, n_genes=all, n_top=10
  Note: this skill is for cluster markers, not replicate-aware condition DE.
```

## Step 4: Method-Specific Tuning Rules

Tune in this order:
1. `groupby`
2. `method`
3. `n_genes`
4. `n_top`

Guidance:
- treat `groupby` as the most important decision because it defines the biological comparison
- start with `wilcoxon` unless the user has a strong reason to prefer another ranking mode
- use `n_genes` to control export breadth
- use `n_top` to control summary tables and plots

Important warnings:
- do not present this as condition-aware DE
- do not claim low-level Scanpy ranking knobs are publicly exposed here

## Step 5: What To Say After The Run

- If markers look weak: question cluster quality before blaming the ranking test.
- If too many markers are exported: reduce `n_genes` or rely on `n_top` for summaries.
- If users want treated-vs-control DE: redirect them to `sc-de`.

## Step 6: Explain Outputs Using Method-Correct Language

- describe marker tables as cluster-discriminative genes
- describe the heatmap/dotplot as visualization summaries, not validation by themselves
- describe `adata_with_markers.h5ad` as the same AnnData with marker-related metadata preserved for reuse

## Official References

- https://scanpy.readthedocs.io/en/stable/api/scanpy.tl.rank_genes_groups.html
- https://scanpy.readthedocs.io/en/1.9.x/generated/scanpy.tl.rank_genes_groups.html

