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
| `markers` | quick label proposal when clusters are already interpretable | `cluster_key`, `marker_file` | built-in markers cover human blood/brain/tissue; use `--marker-file` for other organisms or specialized tissues |
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

## Troubleshooting: All Cells Labeled "Unknown"

If all cells are annotated as "Unknown" with the `markers` method:

1. **Wrong tissue/organism**: Built-in markers cover human PBMC, brain, and general tissue. For mouse data or specialized tissues, provide `--marker-file` with appropriate gene names, or switch to `celltypist` with a tissue-specific model.
2. **Gene naming mismatch**: Human genes are UPPERCASE (CD3D), mouse genes are Title case (Cd3d). The skill auto-detects this and attempts case-insensitive matching, but custom markers are more reliable.
3. **Better alternatives**: For automated annotation, `celltypist` with the right model is usually more reliable than marker scoring. Use `--method celltypist --model <model>` and list models with `celltypist.models.models_description()`.

## What To Say After The Run

- Check the annotated embedding and label distribution first.
- If labels look implausible, question the reference/model before trusting the result.
- If all or most labels are "Unknown", guide the user to provide custom markers or switch methods (see troubleshooting above).
- If labels are still ambiguous, go back to `sc-markers` for supporting evidence.
- If the next question is biological comparison between labeled groups, continue to `sc-de`.
