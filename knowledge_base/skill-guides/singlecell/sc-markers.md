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

## When To Use It

Use this skill after clustering when you want to know which genes best distinguish each cluster or label.

Common OmicsClaw path:

1. `sc-qc`
2. `sc-preprocessing`
3. optional `sc-batch-integration`
4. `sc-clustering`
5. `sc-markers`
6. `sc-cell-annotation`

## Method Choice

| Method | Best first use | Main public controls | Main caveat |
|--------|----------------|----------------------|-------------|
| `wilcoxon` | safest first-pass cluster markers | `groupby`, `n_genes`, `n_top`, marker filters | exploratory, not replicate-aware |
| `t-test` | parametric alternative | `groupby`, `n_genes`, `n_top`, marker filters | more sensitive to assumptions |
| `logreg` | discriminative feature ranking | `groupby`, `n_genes`, `n_top`, marker filters | do not over-sell as a minimal marker-panel selector |

## How To Explain Parameters

Start with:
- which grouping column will be ranked (`groupby`)
- which ranking mode will be used (`method`)
- how many genes will be exported (`n_genes`, `n_top`)
- how strict the exported marker filter will be (`min_in_group_fraction`, `min_fold_change`, `max_out_group_fraction`)

## What To Say After The Run

- Review the top marker table and dotplot first.
- If markers look weak, question cluster quality before blaming the test.
- If users want formal treated-vs-control results, redirect to `sc-de`.
- If cluster identity is still unclear, continue to `sc-cell-annotation` with these markers in hand.
