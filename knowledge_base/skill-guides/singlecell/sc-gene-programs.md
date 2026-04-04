---
doc_id: skill-guide-sc-gene-programs
title: OmicsClaw Skill Guide — SC Gene Programs
doc_type: method-reference
domains: [singlecell]
related_skills: [sc-gene-programs]
search_terms: [single-cell gene programs, cnmf, nmf]
priority: 0.8
---

# OmicsClaw Skill Guide — SC Gene Programs

## Purpose

Use this guide to decide:
- when de novo gene programs are more informative than marker ranking
- how to choose factor count conservatively
- how to describe latent programs without pretending they are pathways

## Method Selection

| Method | Best first use | Main caveat |
|---|---|---|
| **cnmf** | preferred consensus-style program discovery when backend is available | heavier dependency surface |
| **nmf** | lightweight baseline factorization | less stable than consensus workflows |

## Tune In This Order

1. `layer`
2. `n_programs`
3. `n_iter`
4. `top_genes`
5. `seed`

## Interpretation

- a program is a coordinated expression module, not automatically a pathway
- use top genes plus external biology to name programs conservatively
- compare reconstruction error and top-gene coherence before trusting a factorization

## Official References

- https://github.com/codyheiser/cnmf
