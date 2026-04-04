---
doc_id: skill-guide-sc-perturb
title: OmicsClaw Skill Guide — SC Perturb
doc_type: method-reference
domains: [singlecell]
related_skills: [sc-perturb]
search_terms: [single-cell perturbation, mixscape, perturb-seq, pertpy]
priority: 0.8
---

# OmicsClaw Skill Guide — SC Perturb

## Purpose

Use this guide to decide:
- when perturbation-aware classification is more informative than raw guide grouping
- how to provide controls and replicates for Mixscape
- how to interpret responder versus non-responder perturbation classes
- when to stop and run upstream perturbation preparation before Mixscape

## Method Selection

| Method | Best first use | Main caveat |
|---|---|---|
| **mixscape** | perturb-seq or CRISPR perturbation screens with a clear control group | requires a credible control label and enough cells per perturbation |

## Tune In This Order

1. `pert_key`
2. `control`
3. `split_by`
4. `n_neighbors`
5. `logfc_threshold`
6. `pval_cutoff`

## Interpretation

- Mixscape first computes perturbation signatures, then separates cells into perturbation responders versus non-responders.
- `mixscape_class_global` is the simplest first summary when explaining overall perturbation effects.
- Posterior probabilities should be interpreted as confidence for perturbed-class assignment, not as causal effect sizes.
- If the AnnData lacks perturbation labels entirely, the analysis is not ready yet; prepare barcode-to-guide assignments first.

## Official References

- https://pertpy.readthedocs.io/en/latest/api/tools/pertpy.tools.Mixscape.html
- https://www.sc-best-practices.org/conditions/perturbation_modeling.html
