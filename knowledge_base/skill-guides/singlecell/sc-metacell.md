---
doc_id: skill-guide-sc-metacell
title: OmicsClaw Skill Guide — SC Metacell
doc_type: method-reference
domains: [singlecell]
related_skills: [sc-metacell]
search_terms: [single-cell metacell, SEACells, compression]
priority: 0.8
---

# OmicsClaw Skill Guide — SC Metacell

## Purpose

Use this guide to decide:
- when metacell construction helps downstream stability
- when a structure-aware method is worth the extra dependency cost
- how aggressively to compress without losing biology

## Method Selection

| Method | Best first use | Main caveat |
|---|---|---|
| **seacells** | structure-aware metacell construction | optional dependency and longer runtime |
| **kmeans** | fast lightweight compression baseline | not equivalent to SEACells-style archetypal aggregation |

## Tune In This Order

1. `use_rep`
2. `n_metacells`
3. `celltype_key`
4. `min_iter` / `max_iter`

## Interpretation

- too few metacells can blur rare or transitional populations
- too many metacells can undercut the purpose of denoising/compression
- always compare dominant labels and cells-per-metacell before reusing the output downstream

## Official References

- https://github.com/dpeerlab/SEACells
