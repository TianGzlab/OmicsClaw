---
doc_id: skill-guide-sc-enrichment
title: OmicsClaw Skill Guide — SC Enrichment
doc_type: method-reference
domains: [singlecell]
related_skills: [sc-enrichment]
search_terms: [single-cell enrichment, aucell, pathway activity, gene set scoring, tuning]
priority: 0.8
---

# OmicsClaw Skill Guide — SC Enrichment

**Status**: implementation-aligned guide derived from the current OmicsClaw
`sc-enrichment` skill. This guide documents the current AUCell wrapper surface
and does not imply support for ORA or preranked GSEA in this skill.

## Purpose

Use this guide when you need to decide:
- whether AUCell is the right scoring approach for your question
- how to choose a grouping column for downstream summaries
- which parameters matter most in the current wrapper

## Step 1: Inspect The Data First

Key properties to check:
- **Gene identifiers**:
  - the input object and GMT file should use the same identifier space
- **Grouping column**:
  - `groupby` should reflect interpretable labels if grouped summaries are desired
- **Expression matrix**:
  - AUCell uses within-cell rankings and is comparatively robust to normalization choices, but the input should still be biologically sensible
- **Input provenance**:
  - if the object is external and identifier provenance is unclear, recommend `sc-standardize-input` first

## Step 2: Pick The Method Deliberately

| Method | Best first use | Strong starting parameters | Main caveat |
|--------|----------------|----------------------------|-------------|
| **aucell_r** | Cell-wise pathway or signature activity scoring | `gene_sets`, `groupby`, `aucell_auc_max_rank` | Current wrapper does not expose threshold exploration |

## Step 3: Always Show A Parameter Summary Before Running

```text
About to run single-cell enrichment
  Method: aucell_r
  Parameters: gene_sets=pathways.gmt, groupby=leiden, aucell_auc_max_rank=250
  Note: AUCell scores pathway activity per cell; grouped summaries are downstream aggregations.
```

## Step 4: Method-Specific Tuning Rules

Tune in this order:
1. `gene_sets`
2. `groupby`
3. `aucell_auc_max_rank`
4. `top_pathways`

Guidance:
- fix identifier mismatches before changing numeric parameters
- use `groupby` only when you need interpretable summaries across labels
- raise `aucell_auc_max_rank` when scoring large signatures and lower it for tighter activity definitions
- if `groupby` is missing, say explicitly that the run can still score cells but grouped summaries will be skipped

## Step 5: What To Say After The Run

- If many signatures score near zero: inspect gene-set overlap with the dataset first.
- If grouped summaries are noisy: revisit the biological quality of `groupby` before changing AUCell internals.
- If a user asks for enrichment p-values: explain that this skill currently scores activity rather than running ORA/GSEA significance testing.

## Official References

- https://www.bioconductor.org/packages/devel/bioc/vignettes/AUCell/inst/doc/AUCell.html
- https://github.com/aertslab/AUCell
