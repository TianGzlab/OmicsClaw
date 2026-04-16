---
name: sc-cell-communication
description: >-
  Cell-cell communication analysis for annotated scRNA-seq data using a built-in
  ligand-receptor scorer, LIANA, CellPhoneDB, CellChat, or a NicheNet R path.
version: 0.3.0
author: OmicsClaw Team
license: MIT
tags: [singlecell, communication, ligand-receptor, liana, cellphonedb, cellchat, nichenet]
metadata:
  omicsclaw:
    domain: singlecell
    allowed_extra_flags:
      - "--cell-type-key"
      - "--cellchat-min-cells"
      - "--cellchat-prob-type"
      - "--cellphonedb-counts-data"
      - "--cellphonedb-iterations"
      - "--cellphonedb-pvalue"
      - "--cellphonedb-threshold"
      - "--cellphonedb-threads"
      - "--condition-key"
      - "--condition-oi"
      - "--condition-ref"
      - "--method"
      - "--nichenet-lfc-cutoff"
      - "--nichenet-expression-pct"
      - "--nichenet-top-ligands"
      - "--receiver"
      - "--senders"
      - "--species"
      - "--r-enhanced"
    param_hints:
      builtin:
        priority: "cell_type_key -> species"
        params: ["cell_type_key", "species"]
        defaults: {cell_type_key: "cell_type", species: "human"}
        requires: ["normalized_expression", "cell_type_labels_in_obs"]
        tips:
          - "--method builtin: Lightweight heuristic baseline. Good for a quick preview, but not a statistical communication test."
      liana:
        priority: "cell_type_key -> species"
        params: ["cell_type_key", "species"]
        defaults: {cell_type_key: "cell_type", species: "human"}
        requires: ["normalized_expression", "liana", "cell_type_labels_in_obs"]
        tips:
          - "--method liana: Best first rich backend in the current wrapper."
      cellphonedb:
        priority: "cell_type_key -> species"
        params: ["cell_type_key", "species"]
        advanced_params: ["cellphonedb_threshold", "cellphonedb_iterations", "cellphonedb_pvalue", "cellphonedb_threads", "cellphonedb_counts_data"]
        defaults: {cell_type_key: "cell_type", species: "human", cellphonedb_counts_data: "hgnc_symbol", cellphonedb_iterations: 1000, cellphonedb_threshold: 0.1, cellphonedb_threads: 4, cellphonedb_pvalue: 0.05}
        requires: ["normalized_expression", "cellphonedb", "cell_type_labels_in_obs", "human_species"]
        tips:
          - "--method cellphonedb: Uses the official CellPhoneDB statistical backend exposed by the current wrapper."
          - "--cellphonedb-threshold and --cellphonedb-iterations are the main public CellPhoneDB tuning knobs in OmicsClaw."
      cellchat_r:
        priority: "cell_type_key -> species"
        params: ["cell_type_key", "species"]
        advanced_params: ["cellchat_prob_type", "cellchat_min_cells"]
        defaults: {cell_type_key: "cell_type", species: "human", cellchat_prob_type: "triMean", cellchat_min_cells: 10}
        requires: ["normalized_expression", "R_CellChat_stack", "cell_type_labels_in_obs"]
        tips:
          - "--method cellchat_r: R-backed CellChat path with pathway and centrality outputs."
      nichenet_r:
        priority: "cell_type_key -> condition_key -> receiver -> senders"
        params: ["cell_type_key", "condition_key", "condition_oi", "condition_ref", "receiver", "senders"]
        advanced_params: ["nichenet_top_ligands", "nichenet_expression_pct", "nichenet_lfc_cutoff", "species"]
        defaults: {cell_type_key: "cell_type", condition_key: "condition", condition_oi: "stim", condition_ref: "ctrl", receiver: "", senders: "", nichenet_top_ligands: 20, nichenet_expression_pct: 0.10, nichenet_lfc_cutoff: 0.25, species: "human"}
        requires: ["raw_counts_available", "R_nichenetr_stack", "cell_type_labels_in_obs", "condition_labels_in_obs", "human_species"]
        tips:
          - "--method nichenet_r: R-backed NicheNet ligand prioritization path."
          - "--receiver and --senders are required because NicheNet needs explicit receiver and sender cell types."
          - "--nichenet-lfc-cutoff changes the receiver-side DE genes used as the target program."
    saves_h5ad: true
    requires_preprocessed: true
    requires:
      bins: [python3]
      env: []
      config: []
    emoji: "S"
    homepage: https://github.com/OmicsClaw/OmicsClaw
    os: [macos, linux]
    install:
      - kind: pip
        package: omicsclaw[singlecell-communication]
        bins: []
    trigger_keywords:
      - cell communication
      - cell-cell communication
      - ligand receptor
      - cellchat
      - liana
      - cellphonedb
      - nichenet
---

# Single-Cell Cell Communication

## Why This Exists

- Without it: ligand-receptor analysis is hard to standardize across tools.
- With it: the same cell-type labels can be reused across built-in and external communication backends.
- Why OmicsClaw: one output contract captures interactions, top pairs, and summary figures.

## Core Capabilities

1. **Five communication backends**: built-in scorer, LIANA, CellPhoneDB, CellChat, and NicheNet.
2. **Shared grouping contract**: one `cell_type_key`-centric interface across all backends.
3. **Method-correct matrix handling**: LIANA / CellPhoneDB / CellChat use normalized expression, while NicheNet uses raw count-like input for receiver-vs-condition modeling.
4. **Standard gallery**: sender-receiver heatmap, bubble summary, role summary, pathway summary, plus NicheNet ligand ranking.
5. **Downstream-ready export**: annotated `processed.h5ad`, report, structured result JSON, README, `tables/`, `figure_data/`, and reproducibility bundle.

## Scope Boundary

Implemented entry paths:

1. `builtin`
2. `liana`
3. `cellphonedb`
4. `cellchat_r`
5. `nichenet_r`

The wrapper assumes you already have biologically meaningful labels in `obs`.

## Input Formats

| Format | Extension / form | Current wrapper support | Notes |
|--------|------------------|-------------------------|-------|
| AnnData | `.h5ad` | yes | current direct input path |
| Demo | `--demo` | yes | bundled annotated-example fallback |

### Input Expectations

- Required column: a label column such as `cell_type`, `leiden`, or another supplied `--cell-type-key`.
- The grouping column should reflect biologically interpretable labels, not raw QC groups.
- Communication methods expect annotation or clustering to have already been resolved.

## Workflow

1. Validate the grouping column and communication-specific prerequisites.
2. Decide whether the method needs normalized expression or raw count-like input.
3. Run the selected backend.
4. Standardize ligand-receptor rows plus sender/receiver/pathway summaries.
5. Write tables, `figure_data/`, gallery plots, `processed.h5ad`, `report.md`, and `result.json`.

## CLI Reference

```bash
python omicsclaw.py run sc-cell-communication \
  --input data.h5ad --cell-type-key cell_type --output out/

python omicsclaw.py run sc-cell-communication \
  --method liana --input data.h5ad --cell-type-key cell_type --output out/

python omicsclaw.py run sc-cell-communication \
  --method cellphonedb --input data.h5ad --cell-type-key cell_type \
  --cellphonedb-threshold 0.1 --cellphonedb-iterations 1000 --output out/

python omicsclaw.py run sc-cell-communication \
  --method cellchat_r --input data.h5ad --cell-type-key cell_type --output out/

python omicsclaw.py run sc-cell-communication \
  --method nichenet_r --input data.h5ad --cell-type-key cell_type \
  --condition-key condition --condition-oi stim --condition-ref ctrl \
  --receiver Monocyte --senders T_cell,B_cell --nichenet-lfc-cutoff 0.25 --output out/
```

## Public Parameters

| Parameter | Role | Notes |
|-----------|------|-------|
| `--method` | communication backend | `builtin`, `liana`, `cellphonedb`, `cellchat_r`, or `nichenet_r` |
| `--cell-type-key` | grouping column | core public control across all methods |
| `--species` | ligand-receptor resource selector | affects database interpretation and matching |
| `--cellphonedb-*` | CellPhoneDB controls | used only by the `cellphonedb` path |
| `--cellchat-prob-type`, `--cellchat-min-cells` | CellChat controls | used only by the `cellchat_r` path |
| `--condition-*`, `--receiver`, `--senders`, `--nichenet-*` | NicheNet controls | used only by the `nichenet_r` path |

## Algorithm / Methodology

### `builtin`

Current OmicsClaw built-in communication path:

1. uses a compact curated ligand-receptor set
2. aggregates expression by the selected grouping column
3. scores sender-receiver pairs and ranks top interactions

### `liana`

Current OmicsClaw LIANA path:

1. validates the grouping column and species
2. runs LIANA rank aggregation when the Python package is available
3. exports the interaction table under the standard wrapper contract

### `cellphonedb`

Current OmicsClaw CellPhoneDB path:

1. requires `species=human` in the current wrapper
2. uses normalized expression and metadata through the official CellPhoneDB statistical API
3. normalizes CellPhoneDB outputs back into the standard OmicsClaw interaction contract

### `cellchat_r`

Current OmicsClaw CellChat path:

1. exports normalized expression through the shared H5AD bridge
2. runs the R-backed CellChat workflow
3. reimports ranked interactions, pathway summaries, centrality tables, and sender/receiver matrices

### `nichenet_r`

Current OmicsClaw NicheNet path:

1. exports a raw count-like matrix plus metadata through the shared H5AD bridge
2. runs the official `nichenetr` Seurat-wrapper style workflow in R
3. prioritizes ligands for one receiver cell type across two conditions
4. reimports ligand-receptor rows into the shared interaction table and also writes ligand-activity / ligand-target tables

Important implementation note:

- the grouping column is the main scientific control in this wrapper; the current OmicsClaw surface does not expose the full LIANA or CellChat parameter space
- the built-in path leaves `pvalue` empty for compatibility with the shared table schema, so its `n_significant` count is not a formal statistical output
- the CellPhoneDB path currently exposes only a compact public parameter surface and is human-only in this wrapper
- the NicheNet path is also human-only in the current wrapper and its score is ligand activity, not a communication p value

## Output Contract

Successful runs write:

- `processed.h5ad`
- `report.md`
- `result.json`
- `tables/lr_interactions.csv`
- `tables/top_interactions.csv`
- `tables/sender_receiver_summary.csv`
- `tables/group_role_summary.csv`
- `tables/pathway_summary.csv`
- `figures/interaction_heatmap.png`
- `figures/top_interactions.png`
- `figures/source_target_bubble.png`
- `figures/group_role_summary.png`
- `figures/pathway_summary.png`
- `tables/nichenet_ligand_activities.csv` when `--method nichenet_r`
- `tables/nichenet_ligand_target_links.csv` when `--method nichenet_r`
- `figures/nichenet_top_ligands.png` when `--method nichenet_r`
- `tables/cellchat_pathways.csv`, `tables/cellchat_centrality.csv`, `tables/cellchat_count_matrix.csv`, and `tables/cellchat_weight_matrix.csv` when `--method cellchat_r`
- `tables/cellphonedb_means.csv`, `tables/cellphonedb_pvalues.csv`, and `tables/cellphonedb_significant_means.csv` when `--method cellphonedb` returns them

### Visualization Contract

The current wrapper writes direct figure outputs rather than a recipe-driven gallery:

- `figures/interaction_heatmap.png`
- `figures/top_interactions.png`
- `figures/source_target_bubble.png`
- `figures/group_role_summary.png`
- `figures/pathway_summary.png`
- `figures/nichenet_top_ligands.png` for `nichenet_r`

### What Users Should Inspect First

1. `report.md`
2. `figures/interaction_heatmap.png`
3. `figures/source_target_bubble.png`
4. `tables/top_interactions.csv`
5. `tables/lr_interactions.csv`
6. `processed.h5ad`

## Current Limitations

- The built-in method uses a small curated ligand-receptor set and is intentionally lightweight.
- The built-in method leaves `pvalue` empty because it does not run a formal significance test.
- `cellphonedb` is currently human-only in this wrapper.
- `nichenet_r` is currently human-only in this wrapper and requires explicit receiver / sender / condition metadata.
- `cellchat_r` requires a working R environment with CellChat, SingleCellExperiment, and zellkonverter through the shared bridge.
- This skill writes `README.md` and notebook-style reproducibility artifacts when notebook export dependencies are available.

## Safety And Guardrails

- Treat `cell_type_key` as the most important scientific input because all backends aggregate by that grouping.
- Do not describe built-in `pvalue` values as formal significance statistics; for this backend they are intentionally left empty.
- State clearly that `cellphonedb` is human-only in the current wrapper.
- For short execution guardrails, see `knowledge_base/knowhows/KH-sc-cell-communication-guardrails.md`.
- For longer method and interpretation guidance, see `knowledge_base/skill-guides/singlecell/sc-cell-communication.md`.

## CLI Parameters

| Flag | Type | Default | Description | Validation |
|------|------|---------|-------------|------------|
| `--input` | str | — | Input `.h5ad` file | required unless `--demo` |
| `--output` | str | — | Output directory | required |
| `--demo` | flag | off | Run with bundled annotated demo data | — |
| `--method` | str | `builtin` | Communication backend: `builtin`, `liana`, `cellphonedb`, `cellchat_r`, `nichenet_r` | validated against METHOD_REGISTRY |
| `--cell-type-key` | str | `cell_type` | Cell type column in `obs` | — |
| `--species` | str | `human` | Organism for L-R resource selection | choices: human, mouse |
| `--cellphonedb-counts-data` | str | `hgnc_symbol` | Gene ID format for CellPhoneDB | choices: ensembl, gene_name, hgnc_symbol |
| `--cellphonedb-iterations` | int | 1000 | Permutation iterations for CellPhoneDB | cellphonedb only |
| `--cellphonedb-threshold` | float | 0.1 | Minimum expression fraction for CellPhoneDB | cellphonedb only |
| `--cellphonedb-threads` | int | 4 | Parallel threads for CellPhoneDB | cellphonedb only |
| `--cellphonedb-pvalue` | float | 0.05 | P-value cutoff for CellPhoneDB results | cellphonedb only |
| `--cellchat-prob-type` | str | `triMean` | Aggregation method for CellChat | choices: triMean, truncatedMean, thresholdedMean, median |
| `--cellchat-min-cells` | int | 10 | Minimum cells per cell type for CellChat | cellchat_r only |
| `--condition-key` | str | `condition` | Condition column for NicheNet | nichenet_r only |
| `--condition-oi` | str | `stim` | Condition of interest label | nichenet_r only |
| `--condition-ref` | str | `ctrl` | Reference condition label | nichenet_r only |
| `--receiver` | str | `` | Receiver cell type for NicheNet | nichenet_r only |
| `--senders` | str | `` | Comma-separated sender cell types for NicheNet | nichenet_r only |
| `--nichenet-top-ligands` | int | 20 | Number of top ligands to report | nichenet_r only |
| `--nichenet-expression-pct` | float | 0.10 | Minimum expression fraction for ligand filtering | nichenet_r only |
| `--nichenet-lfc-cutoff` | float | 0.25 | log2FC cutoff for receiver DE gene set | nichenet_r only |
| `--r-enhanced` | flag | off | Also render R Enhanced ggplot2 figures | — |

## R Enhanced Plots

Activated by `--r-enhanced`. Files written to `figures/r_enhanced/`.

| Renderer | Output file | figure_data CSV | Plot description | Required R packages |
|----------|-------------|-----------------|------------------|---------------------|
| `plot_ccc_heatmap` | `r_ccc_heatmap.png` | `sender_receiver_summary.csv` | Sender-receiver interaction strength heatmap | ggplot2 |
| `plot_ccc_network` | `r_ccc_network.png` | `sender_receiver_summary.csv` | Network graph of cell-cell interactions | ggplot2, igraph |
| `plot_ccc_bubble` | `r_ccc_bubble.png` | `top_interactions.csv` | Bubble plot of top ligand-receptor pairs | ggplot2 |
| `plot_ccc_stat_bar` | `r_ccc_stat_bar.png` | `group_role_summary.csv` | Bar chart of interaction counts per cell type role | ggplot2 |
| `plot_ccc_stat_violin` | `r_ccc_stat_violin.png` | `top_interactions.csv` | Violin plot of interaction scores per cell type | ggplot2 |
| `plot_ccc_stat_scatter` | `r_ccc_stat_scatter.png` | `top_interactions.csv` | Scatter plot of L-R pair scores | ggplot2 |
| `plot_ccc_bipartite` | `r_ccc_bipartite.png` | `top_interactions.csv` | Bipartite graph of sender-ligand-receptor-receiver | ggplot2, igraph |
| `plot_ccc_diff_network` | `r_ccc_diff_network.png` | `sender_receiver_summary.csv` | Differential interaction network between conditions | ggplot2, igraph |

## Method Fallback Behavior

- `liana`: falls back to `builtin` if the `liana` Python package is not installed. The fallback uses the built-in heuristic scorer (5 curated L-R pairs only). The report records both the requested and executed methods.
- `cellchat_r`: requires R environment with CellChat, SingleCellExperiment, and zellkonverter. Fails with an actionable error if the R stack is missing.
- `nichenet_r`: requires R environment with nichenetr, Seurat, and supporting packages. Human-only in the current wrapper.
- `cellphonedb`: human-only in the current wrapper. Requires `cellphonedb` Python package.

## Workflow Position

**Upstream:** sc-clustering or sc-cell-annotation
**Downstream:** Terminal analysis. Consider: sc-grn (gene regulatory networks)
