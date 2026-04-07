---
doc_id: skill-guide-sc-cell-annotation
title: OmicsClaw Skill Guide — SC Cell Annotation
doc_type: method-reference
domains: [singlecell]
related_skills: [sc-cell-annotation, sc-annotate]
search_terms: [single-cell annotation, CellTypist, SingleR, marker-based annotation, tuning]
priority: 0.8
---

# OmicsClaw Skill Guide — SC Cell Annotation

## When To Use It

Use this skill after clustering when the question becomes: “these clusters probably represent what cell types?”

Common OmicsClaw path:

1. `sc-qc`
2. `sc-preprocessing`
3. optional `sc-batch-integration`
4. `sc-clustering`
5. `sc-cell-annotation`
6. optionally return to `sc-markers` for supporting evidence

## Method Choice

| Method | Best first use | Main public controls | Main caveat |
|--------|----------------|----------------------|-------------|
| `manual` | explicit relabeling when you already know what each cluster should be called | `cluster_key`, `manual_map` / `manual_map_file` | quality depends entirely on the supplied mapping |
| `markers` | quick label proposal when clusters are already interpretable | `cluster_key` | depends strongly on upstream cluster quality |
| `celltypist` | best first automated model-based annotation | `model`, `celltypist_majority_voting` | model choice is tissue-dependent |
| `popv` | labeled H5AD reference mapping | `reference`, `cluster_key` | tries official PopV first, then falls back to lightweight mapping |
| `knnpredict` | lightweight AnnData-first reference mapping | `reference`, `cluster_key` | quality depends entirely on the external reference |
| `singler` | Bioconductor atlas-based annotation or local-reference mapping | `reference` | atlas keywords depend on R packages and cache/network; labeled local H5AD references are more stable |
| `scmap` | reference projection through R | `reference` | atlas keywords depend on cache/network; labeled local H5AD references are more stable |

## How To Explain Parameters

Start with:
- which method is being used (`method`)
- whether it depends on a cluster column (`cluster_key`)
- whether the user is explicitly supplying a relabeling map (`manual_map` / `manual_map_file`)
- whether it depends on a model (`model`) or a reference (`reference`)
- whether CellTypist smoothing is enabled (`celltypist_majority_voting`)

## What To Say After The Run

- Check the annotated embedding and label distribution first.
- If labels look implausible, question the reference/model before trusting the result.
- If labels are still ambiguous, go back to `sc-markers` for supporting evidence.
- If the next question is biological comparison between labeled groups, continue to `sc-de`.
