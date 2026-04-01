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
      - "--db"
      - "--motif"
      - "--n-jobs"
      - "--n-top-targets"
      - "--seed"
      - "--tf-list"
    param_hints:
      pyscenic_workflow:
        priority: "tf_list -> db -> motif -> n_top_targets -> n_jobs"
        params: ["tf_list", "db", "motif", "n_top_targets", "n_jobs", "seed"]
        defaults: {n_top_targets: 50, n_jobs: 4, seed: 42}
        requires: ["preprocessed_anndata", "pyscenic", "arboreto", "TF_list", "cisTarget_database", "motif_annotations"]
        tips:
          - "--tf-list, --db, and --motif are the core external resources for a full pySCENIC run."
          - "--n-top-targets: Wrapper-level export cap for the top targets retained per regulon."
    saves_h5ad: true
    requires_preprocessed: true
    trigger_keywords:
      - grn
      - gene regulatory
      - scenic
      - pyscenic
      - regulon
      - transcription factor
      - grnboost
---

# Single-Cell GRN

## Why This Exists

- Without it: regulon analysis requires several external resources and multi-step orchestration.
- With it: pySCENIC-style GRN outputs are standardized into one wrapper contract.
- Why OmicsClaw: tables, figures, and AnnData outputs are bundled together.

## Scope Boundary

This skill currently exposes one public workflow: `pyscenic_workflow`.

That workflow covers:

1. GRNBoost2 adjacency inference
2. motif-based pruning
3. AUCell regulon scoring

## Input Contract

- Accepted input: preprocessed `.h5ad`
- Required external resources: TF list, cisTarget database files, and motif annotations

## Workflow Summary

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

## Current Limitations

- This skill depends on external pySCENIC resources and does not download them automatically.
- This skill writes `README.md` and notebook-style reproducibility artifacts when notebook export dependencies are available.
