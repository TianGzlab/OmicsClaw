---
name: sc-batch-integration
description: Load when integrating multi-sample scRNA-seq with Harmony, scVI, scANVI, BBKNN, Scanorama, SIMBA, or supported R-backed methods to remove batch effects. Skip when the data is one sample (no batch effect to integrate) or for upstream merging only (use sc-multi-count).
version: 0.3.0
author: OmicsClaw
license: MIT
tags:
- singlecell
- scrna
- batch-integration
- harmony
- scvi
- scanvi
- bbknn
- scanorama
- simba
requires:
- anndata
- numpy
- scipy
---

# sc-batch-integration

## When to use

The user has a merged multi-sample AnnData (post-`sc-multi-count` or
similar) and needs to remove batch effects so downstream clustering /
annotation isn't dominated by per-sample technical variation.  Seven
backends share one CLI: `harmony` (default), `scvi`, `scanvi` (requires
labels), `bbknn`, `scanorama`, `simba`, plus R-backed methods (e.g.
Seurat integration anchors).  Quality is reported as LISI / ASW
diagnostics when available.

## Inputs & Outputs

| Input | Format | Required |
|---|---|---|
| Merged multi-sample AnnData | `.h5ad` with `obs["batch"]` (or via `--batch-key`) | yes (unless `--demo`) |
| Cell-type labels | `obs["<labels-key>"]` for `scanvi` | only for `--method scanvi` |

| Output | Path | Notes |
|---|---|---|
| Integrated AnnData | `processed.h5ad` | adds `obsm["X_<method>"]` for embedding-based methods (Harmony / scVI / scANVI / Scanorama / SIMBA); BBKNN modifies the neighbour graph and leaves `obsm["X_pca"]` as the embedding |
| Run summary | `tables/integration_summary.csv` | parameters + run mode |
| Batch composition | `tables/batch_sizes.csv`, `tables/batch_mixing_matrix.csv` | per-batch / per-cluster mixing |
| Cluster sizes | `tables/cluster_sizes.csv` | cells per integrated cluster |
| Diagnostics | `tables/integration_metrics.csv` | LISI + ASW when available |
| Report | `report.md` + `result.json` | always written |

## Flow

1. Load merged AnnData; resolve `--batch-key` (default `batch`).
2. Validate backend prerequisites (e.g. `scanvi` needs `--labels-key`).
3. Run the chosen `--method`; write the integrated embedding to `obsm["X_<method>"]` (BBKNN is the exception — it adjusts the neighbour graph in-place and leaves the embedding as `obsm["X_pca"]`).
4. Compute LISI / ASW diagnostics (best-effort; non-fatal if unavailable).
5. Emit summary + batch-composition + diagnostics tables.
6. Save `processed.h5ad` + `report.md` + `result.json`.

## Gotchas

- **`scanvi` silently falls back to `scvi` when labels are missing.** `sc_integrate.py:189-193` logs `"scANVI requires labels; falling back to scVI latent integration"` and writes `result["requested_method"] = "scanvi"`, `result["executed_method"] = "scvi"`, `result["fallback_used"] = True`.  After every `--method scanvi` run, verify `result.json["executed_method"]` matches the request; `--labels-key` must be set and contain valid labels to actually get scANVI.
- **`simba` missing → hard fail.** `sc_integrate.py:242` raises `ImportError` when `--method simba` runs without the `simba` package installed.  Install via `pip install simba` / `conda install -c bioconda simba` / from-source per the message.  scvi-tools failures surface separately with their own ImportError further downstream.
- **Scanorama can return zero overlapping cells.** `sc_integrate.py:349` raises `RuntimeError("Scanorama did not produce 'X_scanorama' embeddings")` when batches share no genes (typical: gene-namespace mismatch).  Pre-run `sc-standardize-input` on each batch.
- **R-backed methods can produce zero-overlap returns too.** `sc_integrate.py:400` raises `RuntimeError(f"R integration method '{method}' returned no overlapping cells")` for the same root cause.
- **LISI / ASW diagnostics are best-effort.** `sc_integrate.py:514` and `:529` log `"LISI diagnostics unavailable"` / `"ASW diagnostics unavailable"` and continue when scIB or its dependencies are missing.  Absence of metric rows in `tables/integration_metrics.csv` does not imply integration quality is bad — it means the diagnostics could not be computed.

## Key CLI

```bash
# Demo (Harmony on built-in two-batch dataset)
python omicsclaw.py run sc-batch-integration --demo --output /tmp/sc_integrate_demo

# Default Harmony on real data
python omicsclaw.py run sc-batch-integration \
  --input merged.h5ad --output results/ \
  --method harmony --batch-key sample_id

# scVI with explicit n_latent
python omicsclaw.py run sc-batch-integration \
  --input merged.h5ad --output results/ \
  --method scvi --batch-key sample_id --n-latent 30 --n-epochs 200

# scANVI (requires labels)
python omicsclaw.py run sc-batch-integration \
  --input merged_with_labels.h5ad --output results/ \
  --method scanvi --batch-key sample_id --labels-key cell_type

# BBKNN (graph-based — modifies neighbours, no obsm["X_bbknn"])
python omicsclaw.py run sc-batch-integration \
  --input merged.h5ad --output results/ \
  --method bbknn --batch-key sample_id
```

## See also

- `references/parameters.md` — every CLI flag and per-method tuning hint
- `references/methodology.md` — when each backend wins, GPU/CPU tradeoffs, label-aware vs label-free integration
- `references/output_contract.md` — `obsm` key conventions, diagnostic semantics
- Adjacent skills: `sc-multi-count` (upstream — produces the merged input), `sc-clustering` (downstream — runs on the integrated embedding via `--use-rep X_<method>`), `sc-cell-annotation` (downstream — label propagation across batches)
