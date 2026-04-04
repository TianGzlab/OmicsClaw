---
doc_id: skill-guide-sc-pseudotime
title: OmicsClaw Skill Guide — SC Pseudotime
doc_type: method-reference
domains: [singlecell]
related_skills: [sc-pseudotime]
search_terms: [pseudotime, DPT, PAGA, diffusion map, Palantir, VIA, CellRank, root cluster, trajectory genes, tuning]
priority: 0.8
---

# OmicsClaw Skill Guide — SC Pseudotime

**Status**: implementation-aligned guide derived from the current OmicsClaw
`sc-pseudotime` skill. This guide separates the trajectory method itself from
the trajectory-gene ranking method used afterward.

## Purpose

Use this guide when you need to decide:
- whether DPT is the right trajectory path for the current dataset
- how to explain root choice correctly
- which parameters matter most in the current wrapper

## Step 1: Inspect The Data First

Key properties to check:
- **Cluster labels**:
  - `cluster_key` must exist and be biologically interpretable
- **Graph readiness**:
  - neighbors should exist or be recomputable
- **Root knowledge**:
  - a biologically plausible root cluster or root cell is often the most important human choice
- **Input provenance**:
  - if the object is external, recommend `sc-standardize-input` first, but make clear that standardization does not choose the root for pseudotime

Important implementation notes in current OmicsClaw:
- trajectory `method` is currently `dpt`, `palantir`, `via`, or `cellrank`
- `corr_method` is not a trajectory algorithm; it only ranks trajectory genes after pseudotime is inferred
- the wrapper bundles PAGA, diffusion map, and DPT into one execution path
- the wrapper now uses shared preflight checks, so missing cluster columns or missing root choice should be clarified before the run rather than left to opaque failures

## Step 2: Pick The Method Deliberately

| Method | Best first use | Strong starting parameters | Main caveat |
|--------|----------------|----------------------------|-------------|
| **dpt** | Classic Scanpy pseudotime after clustering and graph construction | `cluster_key`, `root_cluster`, `n_dcs`, `corr_method` | Root choice still governs directionality |
| **palantir** | waypoint-based pseudotime with entropy and fate probabilities | `root_cluster`/`root_cell`, `palantir_knn`, `palantir_num_waypoints` | heavier dependency and explicit root required |
| **via** | graph-based pseudotime with automatic terminal-state discovery | `root_cluster`/`root_cell`, `via_knn` | optional pyVIA dependency and embedding-quality sensitivity |
| **cellrank** | fate-oriented trajectory analysis with macrostates and terminal states | `root_cluster`/`root_cell`, `cellrank_n_states`, `cellrank_schur_components`, `cellrank_frac_to_keep` | heavier kernel decomposition and fate outputs depend on kernel choice |

## Step 3: Always Show A Parameter Summary Before Running

```text
About to run pseudotime analysis
  Method: cellrank
  Parameters: cluster_key=leiden, root_cluster=0, n_dcs=10, n_genes=50, corr_method=pearson
  Note: corr_method only affects trajectory-gene ranking after DPT is computed.
```

## Step 4: Method-Specific Tuning Rules

Tune in this order:
1. `cluster_key`
2. `root_cluster` or `root_cell`
3. `n_dcs`
4. `n_genes`
5. `corr_method`
6. `cellrank_n_states` / `cellrank_schur_components` / `cellrank_frac_to_keep` when using CellRank

Guidance:
- choose `root_cluster` or `root_cell` before touching numeric tuning
- use `n_dcs` to control how much diffusion structure is retained for DPT
- use `n_genes` to control how many trajectory-associated genes are exported
- use `corr_method` only to change the downstream ranking rule

Important warnings:
- do not describe `pearson` or `spearman` as pseudotime methods
- do not describe VIA as diffusion pseudotime; it is a separate graph-based trajectory framework
- do not expose Scanpy / CellRank parameters that the wrapper does not currently forward

## Step 5: What To Say After The Run

- If pseudotime looks biologically reversed: revisit root choice first.
- If trajectory genes are unstable: revisit `corr_method` only after confirming the trajectory itself makes sense.
- If branch structure looks implausible: question upstream clustering or neighbor graph quality.

## Step 6: Explain Outputs Using Method-Correct Language

- describe PAGA as coarse cluster connectivity
- describe DPT as pseudotemporal ordering from the chosen root
- describe CellRank as macrostate / terminal-state / fate inference built on a transition kernel
- describe trajectory genes as genes correlated with inferred pseudotime in the current wrapper

## Official References

- https://scanpy.readthedocs.io/en/stable/generated/scanpy.tl.paga.html
- https://scanpy.readthedocs.io/en/stable/generated/scanpy.tl.diffmap.html
- https://scanpy.readthedocs.io/en/stable/generated/scanpy.tl.dpt.html
- https://github.com/ShobiStassen/VIA
- https://pypi.org/project/pyVIA/
- https://cellrank.readthedocs.io/
- https://scanpy.readthedocs.io/en/latest/tutorials/trajectories/paga-paul15.html
