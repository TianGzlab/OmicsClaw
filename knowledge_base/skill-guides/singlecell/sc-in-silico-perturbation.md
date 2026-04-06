---
doc_id: skill-guide-sc-in-silico-perturbation
title: OmicsClaw Skill Guide — In-Silico Perturbation
doc_type: method-reference
domains: [singlecell]
related_skills: [sc-in-silico-perturbation]
search_terms: [scTenifoldKnk, virtual knockout, in silico knockout, single-cell GRN]
priority: 0.8
---

# OmicsClaw Skill Guide — In-Silico Perturbation

## Purpose

Use this guide to decide:
- when a virtual knockout on a WT network is appropriate
- how to choose the knockout gene and network-construction parameters
- how to interpret differential regulation output conservatively

## Method Selection

| Method | Best first use | Main caveat |
|---|---|---|
| **sctenifoldknk** | in-silico knockout from a wild-type scRNA expression matrix | result quality depends on the inferred WT network, not direct perturbation evidence |

## Tune In This Order

1. `ko_gene`
2. `qc`
3. `n_net`
4. `n_cells`
5. `n_comp`
6. `q`
7. `td_k`
8. `ma_dim`

## Interpretation

- `diffRegulation` is the primary output table: genes farther apart in the WT/KO aligned manifolds are the predicted perturbed genes.
- The output reflects changes on an inferred regulatory network after zeroing the knockout gene’s outgoing edges.
- Use top perturbed genes as hypotheses for downstream validation, not as final proof of function.

## Official References

- https://github.com/cailab-tamu/scTenifoldKnk
- https://sctenifold.readthedocs.io/en/latest/sctenifoldknk.html
