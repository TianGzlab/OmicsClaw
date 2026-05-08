---
name: sc-grn
description: >-
  Infer gene regulatory networks from scRNA-seq using the pySCENIC workflow:
  GRNBoost2 for adjacency inference, cisTarget-style motif pruning, and AUCell
  regulon scoring.
version: 0.2.0
author: OmicsClaw
license: MIT
tags: [singlecell, grn, pyscenic, regulon, transcription-factor]
metadata:
  omicsclaw:
    domain: singlecell
    allowed_extra_flags:
    - "--allow-simplified-grn"
    - "--cluster-key"
    - "--db"
    - "--motif"
    - "--n-jobs"
    - "--n-top-targets"
    - "--seed"
    - "--tf-list"
    - "--r-enhanced"
    param_hints:
      pyscenic_workflow:
        priority: "tf_list -> db -> motif -> n_top_targets -> n_jobs"
        params: ["tf_list", "db", "motif", "n_top_targets", "n_jobs", "seed"]
        defaults: {n_top_targets: 50, n_jobs: 4, seed: 42}
        requires: ["preprocessed_anndata", "pyscenic", "arboreto", "TF_list", "cisTarget_database",
          "motif_annotations"]
        tips:
        - "--tf-list, --db, and --motif are the core external resources for a full
          pySCENIC run."
        - "--n-top-targets: Wrapper-level export cap for the top targets retained
          per regulon."
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
      package: pyscenic
      bins: []
    trigger_keywords:
    - grn
    - gene regulatory
    - scenic
    - pyscenic
    - regulon
    - transcription factor
    - grnboost
    script: sc_grn.py
---

# Single-Cell GRN

## Why This Exists

- Without it: regulon analysis requires several external resources and multi-step orchestration.
- With it: pySCENIC-style GRN outputs are standardized into one wrapper contract.
- Why OmicsClaw: tables, figures, and AnnData outputs are bundled together.

## Core Capabilities

1. **Implementation-aligned pySCENIC workflow**: adjacency inference, motif pruning, and regulon scoring.
2. **Explicit external-resource contract**: TF list, cisTarget databases, and motif annotations are surfaced as real prerequisites.
3. **Regulon-centric outputs**: adjacency, regulon, target, and AUCell tables.
4. **Direct figure exports**: regulon activity UMAP, regulon heatmap, and network plot.
5. **Downstream-ready export**: writes `adata_with_grn.h5ad`, report, result JSON, README, and notebook artifacts.

## Scope Boundary

This skill currently exposes one public workflow: `pyscenic_workflow`.

That workflow covers:

1. GRNBoost2 adjacency inference
2. motif-based pruning
3. AUCell regulon scoring

## Input Formats

| Format | Extension / form | Current wrapper support | Notes |
|--------|------------------|-------------------------|-------|
| AnnData | `.h5ad` | preferred | most realistic path for preprocessed scRNA-seq |
| Shared-loader formats | `.h5`, `.loom`, `.csv`, `.tsv`, 10x directory | technically loadable | usually still need preprocessing and external GRN resources |
| Demo | `--demo` | yes | bundled lightweight fallback |

### Input Expectations

- The current skill expects a preprocessed scRNA-seq object.
- Required external resources: TF list, cisTarget database files, and motif annotations.
- The wrapper does not automatically fetch pySCENIC resources for the user.

## Workflow

1. Load preprocessed expression data.
2. Run adjacency inference.
3. Prune candidate targets with motif evidence.
4. Score regulon activity per cell.
5. Export `adata_with_grn.h5ad`, tables, figures, `report.md`, and `result.json`.

## CLI Reference

```bash
python omicsclaw.py run sc-grn \
  --input <processed.h5ad> \
  --tf-list <tfs.txt> \
  --db '<db_glob>' \
  --motif <motif.tbl> \
  --output <dir>
```

## Public Parameters

| Parameter | Role | Notes |
|-----------|------|-------|
| `--tf-list` | transcription-factor list | core prerequisite for adjacency inference |
| `--db` | cisTarget database selector | usually a glob or database path |
| `--motif` | motif annotation table | required for pruning |
| `--n-top-targets` | wrapper-level export cap | limits exported targets per regulon |
| `--n-jobs` | parallelism control | runtime knob for pySCENIC steps |
| `--seed` | reproducibility control | affects stochastic components |

## Algorithm / Methodology

Current OmicsClaw `pyscenic_workflow` runs:

1. GRNBoost2 adjacency inference from expression data
2. motif-based pruning using the supplied cisTarget and motif resources
3. AUCell regulon scoring per cell
4. export of regulon activity and target summaries back into the output AnnData

Important implementation notes:

- `n_top_targets` is a wrapper-level export control, not a full pySCENIC science knob.
- Resource availability matters more than fine parameter tuning for first-pass success.

## Output Contract

Successful runs write:

- `adata_with_grn.h5ad`
- `report.md`
- `result.json`
- `tables/grn_adjacencies.csv`
- `tables/grn_regulons.csv`
- `tables/grn_regulon_targets.csv`
- `tables/grn_auc_matrix.csv`
- `figures/`

### Visualization Contract

The current wrapper writes direct figure outputs rather than a recipe-driven gallery:

- `figures/regulon_activity_umap.png`
- `figures/regulon_heatmap.png`
- `figures/regulon_network.png`

### What Users Should Inspect First

1. `report.md`
2. `tables/grn_regulons.csv`
3. `figures/regulon_activity_umap.png`
4. `tables/grn_auc_matrix.csv`
5. `adata_with_grn.h5ad`

## Current Limitations

- This skill depends on external pySCENIC resources and does not download them automatically.
- The shared runner adds top-level README and notebook-style reproducibility artifacts when notebook export dependencies are available.

## Safety And Guardrails

- Verify the TF list, cisTarget databases, and motif annotations before promising a full run.
- Do not present `n_top_targets` as a full pySCENIC science parameter; it is a wrapper-level export control.
- For short execution guardrails, see `knowledge_base/knowhows/KH-sc-grn-guardrails.md`.
- For longer method and interpretation guidance, see `knowledge_base/skill-guides/singlecell/sc-grn.md`.

## CLI Parameters

| Flag | Type | Default | Description | Validation |
|------|------|---------|-------------|------------|
| `--input` | str | None | Input AnnData file (`.h5ad`) | Required unless `--demo` |
| `--output` | str | — | Output directory | Required |
| `--demo` | flag | off | Run with built-in demo data (GRNBoost2 only) | — |
| `--tf-list` | str | None | TF list file (one TF gene symbol per line) | Optional; required for full pySCENIC run |
| `--db` | str | None | cisTarget database glob pattern | Optional; required for motif pruning |
| `--motif` | str | None | Motif annotations file (`.tbl`) | Optional; required for motif pruning |
| `--n-top-targets` | int | 50 | Maximum targets exported per regulon | Wrapper-level cap, not a pySCENIC science knob |
| `--n-jobs` | int | 4 | Number of parallel jobs for pySCENIC steps | — |
| `--seed` | int | 42 | Random seed for reproducibility | — |
| `--cluster-key` | str | `leiden` | `adata.obs` column for cell grouping in figures | — |
| `--allow-simplified-grn` | flag | off | Accept correlation-based GRN fallback when no TF/database/motif files are provided | Enables `demo_mode` logic without `--demo` |
| `--r-enhanced` | flag | off | Generate R Enhanced plots (requires R + ggplot2) | — |

## R Enhanced Plots

| Renderer | Output file | Description |
|----------|-------------|-------------|
| `plot_embedding_discrete` | `figures/r_enhanced/r_embedding_discrete.png` | UMAP colored by discrete cluster labels |
| `plot_embedding_feature` | `figures/r_enhanced/r_embedding_feature.png` | UMAP colored by a continuous feature (AUC score) |

## Special Requirements

### External pySCENIC Database Files

A full pySCENIC run with motif enrichment requires three external resource files that OmicsClaw does **not** download automatically:

| Resource | Flag | Example download |
|----------|------|-----------------|
| TF list (one TF per line) | `--tf-list` | `wget https://raw.githubusercontent.com/aertslab/pySCENIC/master/resources/hs_hgnc_tfs.txt` |
| cisTarget database (`.feather`) | `--db` | See `https://resources.aertslab.org/cistarget/` |
| Motif annotations (`.tbl`) | `--motif` | `wget https://resources.aertslab.org/cistarget/motif2tf/motifs-v9-nr.hgnc-m0.001-o0.0.tbl` |

Store downloaded files under `examples/databases/motifs/` or provide explicit paths via the flags above.

### Simplified / Fallback Mode

When `--tf-list`, `--db`, and `--motif` are all absent **and** `--allow-simplified-grn` is passed, the wrapper accepts a correlation-based fallback GRN (no motif pruning). This is useful for quick exploratory analysis or when pySCENIC databases are not yet available.

```bash
# Full pySCENIC run
python omicsclaw.py run sc-grn \
  --input processed.h5ad \
  --tf-list hs_hgnc_tfs.txt \
  --db 'databases/*.feather' \
  --motif motifs-v9-nr.hgnc-m0.001-o0.0.tbl \
  --output results/

# Simplified fallback (no external databases needed)
python omicsclaw.py run sc-grn \
  --input processed.h5ad \
  --allow-simplified-grn \
  --output results/
```

## Workflow Position

**Upstream:** sc-clustering or sc-cell-annotation
**Downstream:** Terminal analysis.
