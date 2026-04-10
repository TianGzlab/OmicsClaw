---
doc_id: skill-guide-sc-pseudotime
title: OmicsClaw Skill Guide — SC Pseudotime
doc_type: method-reference
domains: [singlecell]
related_skills: [sc-pseudotime]
search_terms: [pseudotime, trajectory, DPT, Palantir, VIA, CellRank, Slingshot, root cluster, use_rep]
priority: 0.8
---

# OmicsClaw Skill Guide — SC Pseudotime

## What This Step Means

`sc-pseudotime` is the trajectory step after clustering. It orders cells along a continuous process and then ranks genes associated with that ordering.

This is not the same as:
- clustering
- annotation
- differential expression

It is specifically about *directional progression*.

## What Users Must Decide

1. which label column defines the state space (`cluster_key`)
2. which embedding / representation should drive the trajectory (`use_rep`)
3. which state is the beginning (`root_cluster` or `root_cell`)
4. which method matches the biological question (`dpt`, `palantir`, `via`, `cellrank`, `slingshot_r`)

## Method Cheat Sheet

| Method | Use when | Key user-facing defaults |
|--------|----------|--------------------------|
| `dpt` | you want a classic first-pass pseudotime | `use_rep=X_umap`, `n_neighbors=15`, `n_pcs=50`, `n_dcs=10` |
| `palantir` | you want entropy / terminal-state probabilities | `palantir_knn=30`, `palantir_n_components=10`, `palantir_num_waypoints=1200` |
| `via` | you want graph-based branch discovery | `via_knn=30`, `via_seed=20` |
| `cellrank` | you want macrostates or fate probabilities | `cellrank_n_states=3`, `cellrank_schur_components=20`, `cellrank_frac_to_keep=0.3` |
| `slingshot_r` | you want explicit lineage curves | optional `end_clusters`, branch-aware curve output |

## How To Explain `use_rep`

- `X_umap`: current default first-pass trajectory view in the wrapper
- `X_pca`: alternative baseline trajectory on the preprocessing PCA
- `X_harmony`, `X_scvi`, `X_scanvi`, `X_scanorama`: use these when the user already decided to trust an integrated representation

Do not say “embedding only affects plotting”.  
For pseudotime, `use_rep` changes the graph and therefore the trajectory itself.

## How To Explain Outputs

- `pseudotime_embedding.png`: pseudotime laid onto a display embedding
- `pseudotime_distribution_by_group.png`: whether different clusters occupy different trajectory ranges
- `trajectory_gene_heatmap.png`: top genes ordered by pseudotime
- `trajectory_gene_trends.png`: smooth expression trends for the top trajectory genes
- `fate_probability_heatmap.png`: only when the backend returns lineage/fate probabilities
- `lineage_curves.png`: only for Slingshot

## Usual Next Steps

- use `sc-pathway-scoring` to see whether known programs rise or fall along the trajectory
- use `sc-enrichment` to interpret trajectory-associated genes statistically
- revisit `sc-cell-annotation` if the inferred start state looks biologically backwards
