---
doc_id: skill-guide-spatial-trajectory
title: OmicsClaw Skill Guide — Spatial Trajectory
doc_type: method-reference
domains: [spatial]
related_skills: [spatial-trajectory, trajectory]
search_terms: [spatial trajectory, pseudotime, DPT, CellRank, Palantir, tuning]
priority: 0.8
---

# OmicsClaw Skill Guide — Spatial Trajectory

**Status**: implementation-aligned guide derived from the current OmicsClaw
`spatial-trajectory` skill. This is **not** one of the 28 already validated
end-to-end workflows. It is a living guide for method selection, parameter
reasoning, and wrapper-specific caveats.

## Purpose

Use this guide when you need to decide:
- whether DPT, CellRank, or Palantir is the best first trajectory backend
- which parameters matter first in the current OmicsClaw wrapper
- how to explain pseudotime, fates, and branch entropy without pretending they are the same quantity

## Step 1: Inspect The Data First

If the dataset has not been inspected yet in this conversation, call
`inspect_data` first.

Key properties to check:
- **Preprocessing state**:
  - does `obsm["X_pca"]` exist?
  - does `uns["neighbors"]` exist?
- **Cluster / annotation column**:
  - which `obs` column is biologically meaningful for choosing a root cell type?
  - if `leiden` is missing, what annotation should replace it?
- **Root prior**:
  - does the user already know the likely start population?
  - do they want an exact root barcode or a root annotation group?
- **Velocity support**:
  - for CellRank, are real velocity results available or is the run going to rely on pseudotime / connectivity?
- **Expected output type**:
  - scalar ordering only -> DPT
  - fate probabilities / macrostates -> CellRank
  - pseudotime + branch entropy / waypoint refinement -> Palantir

Important implementation notes in current OmicsClaw:
- The wrapper expects preprocessed data and does not silently rebuild the whole preprocessing story from scratch.
- Root-cell selection is explicit: `root_cell` overrides `root_cell_type`, which overrides the wrapper auto-root heuristic.
- CellRank currently computes a DPT prepass so that root handling and pseudotime-guided kernels are explicit.
- Scanpy's `palantir_results()` returns a Palantir results object; current OmicsClaw writes pseudotime / entropy back into AnnData instead of assuming Scanpy stores them automatically.
- CellRank and Palantir are not silent fallbacks from DPT; they are explicit backends.

## Step 2: Pick The Method Deliberately

Use this quick guide when the user has not explicitly chosen a method:

| Method | Best first use | Strong starting parameters | Main caveat |
|--------|----------------|----------------------------|-------------|
| **DPT** | Simple scalar pseudotime ordering on a preprocessed graph | `dpt_n_dcs=10` plus an explicit root when possible | Does not provide fate probabilities or branch entropy |
| **CellRank** | Fate-oriented trajectory analysis with macrostates and terminal states | `cellrank_n_states=3`, `cellrank_schur_components=20`, `cellrank_frac_to_keep=0.3` | Interpretation depends on which kernel path actually ran |
| **Palantir** | Diffusion-based pseudotime plus branch entropy and waypoint refinement | `palantir_n_components=10`, `palantir_knn=30`, `palantir_num_waypoints=1200` | Requires Palantir install and should not be described as "just DPT with another name" |

Practical default decision order:
1. If the user only wants a first scalar ordering, start with **DPT**.
2. If the user explicitly wants fate probabilities or terminal states, use **CellRank**.
3. If the user wants branch entropy / branching uncertainty or explicitly asks for Palantir, use **Palantir**.

## Step 3: Always Show A Parameter Summary Before Running

Before execution, tell the user what will be run in a short, concrete block:

```text
About to run spatial trajectory analysis
  Method: CellRank
  Cluster key: leiden
  Root: root_cell_type=progenitor
  Parameters: dpt_n_dcs=10, cellrank_use_velocity=false, cellrank_n_states=3, cellrank_schur_components=20, cellrank_frac_to_keep=0.3
  Note: This run will use a DPT prepass for root handling and pseudotime-guided CellRank kernels.
```

## Step 4: Root Selection Rules

Tune in this order:
1. `root_cell`
2. `root_cell_type`
3. `cluster_key`

Guidance:
- Prefer an explicit `root_cell` when the user has a trusted starting barcode.
- Use `root_cell_type` when the user knows the biological origin population but not the exact cell.
- Make `cluster_key` explicit when `leiden` is not the right annotation layer.
- Treat the wrapper auto-root heuristic as a convenience for exploratory runs, not as prior biological truth.

Important warning:
- A trajectory run with the wrong root can still look numerically valid while telling the wrong biological story.

## Step 5: Method-Specific Tuning Rules

### DPT

Tune in this order:
1. `root_cell` / `root_cell_type`
2. `dpt_n_dcs`

Guidance:
- Start with `dpt_n_dcs=10`.
- Increase `dpt_n_dcs` when the user believes the trajectory manifold needs more diffusion structure.
- Decrease it when the graph is noisy and the user wants a simpler scalar ordering.

Important warning:
- `dpt_n_dcs` changes the geometry used for pseudotime and should not be treated as a cosmetic plotting parameter.

### CellRank

Tune in this order:
1. `root_cell` / `root_cell_type`
2. `cellrank_use_velocity`
3. `cellrank_n_states`
4. `cellrank_schur_components`
5. `cellrank_frac_to_keep`

Guidance:
- Start with `cellrank_use_velocity=false` unless real velocity support is known to exist.
- Start with `cellrank_n_states=3`.
- Increase `cellrank_n_states` when the user expects more terminal programs.
- Start with `cellrank_schur_components=20`.
- Increase `cellrank_schur_components` when the coarse decomposition looks too compressed.
- Start with `cellrank_frac_to_keep=0.3`.
- Lower `cellrank_frac_to_keep` when the pseudotime kernel is too permissive.
- Raise it only when a denser forward neighborhood is scientifically justified.

Important warnings:
- `cellrank_use_velocity` is a wrapper-level preference, not a guarantee that a velocity kernel actually ran.
- Always describe the **actual kernel mode** used in the run summary.

### Palantir

Tune in this order:
1. `root_cell` / `root_cell_type`
2. `palantir_knn`
3. `palantir_num_waypoints`
4. `palantir_n_components`
5. `palantir_max_iterations`

Guidance:
- Start with `palantir_knn=30`.
- Lower `palantir_knn` when the graph is too smooth for a rare branching structure.
- Start with `palantir_num_waypoints=1200`.
- Reduce waypoints for small datasets or fast exploratory runs.
- Start with `palantir_n_components=10`.
- Increase it when the user believes the manifold needs more diffusion dimensions.
- Keep `palantir_max_iterations=25` as a default refinement budget.

Important warnings:
- `palantir_num_waypoints` and `palantir_max_iterations` affect the refinement path, not just runtime.
- Do not describe Palantir branch entropy as if it were a CellRank fate probability or a DPT pseudotime confidence score.

## Step 6: What To Say After The Run

- If DPT ordering looks unstable: suggest revisiting the root choice before over-tuning `dpt_n_dcs`.
- If CellRank reports only connectivity mode: explain that the requested kernel path could not be used and say what actually ran.
- If CellRank terminal states are sparse or ambiguous: suggest revisiting `cellrank_n_states` and the biological root assumption.
- If Palantir returns few or no terminal states: explain that the current branch-probability structure may be weak rather than pretending a strong branching story exists.
- If trajectory genes are weak: explain that this may reflect either biology or an unstable root / graph configuration.

## Step 7: Use The Visualization Layers Deliberately

Current OmicsClaw `spatial-trajectory` separates visualization into two layers:

- **Python standard gallery**:
  - canonical analysis output
  - emitted under `figures/` with `figures/manifest.json`
  - should be the default artifact used in interactive analysis and routine
    reporting
- **R customization layer**:
  - optional refinement layer
  - should consume `figure_data/*.csv`
  - should not rerun DPT, CellRank, or Palantir just to restyle figures

Practical rule:

1. Use the Python gallery to confirm the science and the narrative structure.
2. Use the R layer only when the user explicitly wants publication styling,
   panel composition, or deeper aesthetic control.
3. If an R script needs extra inputs, export them from Python first instead of
   embedding scientific recomputation inside the plotting layer.

## Step 8: Explain Results Using Method-Correct Language

When summarizing results:
- For **DPT**, describe the output as diffusion pseudotime on the existing preprocessing graph.
- For **CellRank**, describe the output as macrostate / fate inference on top of a CellRank transition kernel.
- For **Palantir**, describe the output as Palantir pseudotime plus branch entropy / branch probabilities when available.
- Refer to `trajectory_genes.csv` as genes correlated with the scalar pseudotime used by the wrapper.

Do **not** collapse DPT, CellRank, and Palantir into a generic "trajectory
score" story. In the current wrapper, they expose different parameters and
different biological claims.
