---
doc_id: skill-guide-sc-differential-abundance
title: OmicsClaw Skill Guide — SC Differential Abundance
doc_type: method-reference
domains: [singlecell]
related_skills: [sc-differential-abundance]
search_terms: [single-cell differential abundance, milo, sccoda, compositional]
priority: 0.8
---

# OmicsClaw Skill Guide — SC Differential Abundance

## Purpose

Use this guide to decide:
- when to run DA/compositional analysis instead of DE
- when Milo or scCODA is the better first choice
- how to explain outputs without over-claiming

## Method Selection

| Method | Best first use | Main requirement | Main caveat |
|---|---|---|---|
| **milo** | local neighborhood shifts on a manifold | meaningful KNN graph + replicate samples | neighborhood-level DA is less intuitive than cluster-level proportions |
| **sccoda** | labeled cluster/cell-type compositional shifts | replicate samples + reference cell type concept | results are relative to the chosen reference |
| **simple** | quick exploratory screen | per-sample labels | not a substitute for formal DA/compositional inference |

## Tune In This Order

### Milo
1. `sample_key`
2. `condition_key`
3. `cell_type_key`
4. `contrast`
5. `prop`
6. `n_neighbors`

Practical rules:
- start with `prop=0.1`; lower it for larger datasets
- use explicit `contrast` when there are more than two condition levels
- if the integrated manifold is poor, fix preprocessing/integration before trusting DA

### scCODA
1. `sample_key`
2. `condition_key`
3. `cell_type_key`
4. `reference_cell_type`
5. `fdr`

Practical rules:
- use `reference_cell_type=automatic` only when you truly lack a stable reference hypothesis
- if no effects are found at strict FDR, report that honestly before loosening thresholds
- always explain that apparent changes in non-significant cell types can arise from compositional coupling

## Interpretation

- **Milo**: significant neighborhoods imply local abundance shifts, not necessarily whole-cluster replacement.
- **scCODA**: non-zero final parameters indicate credible abundance shifts relative to the reference.
- **simple**: use as a ranking and screening view only.

## Official References

- https://www.sc-best-practices.org/conditions/compositional.html
- https://sccoda.readthedocs.io/en/latest/getting_started.html
