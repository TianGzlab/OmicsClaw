---
name: sc-cell-annotation
description: Load when assigning cell-type labels to a clustered scRNA AnnData via marker dictionaries, CellTypist, PopV, KNNPredict, SingleR, scmap, SCSA, or a manual cluster-to-label map. Skip when ranking marker genes per cluster (use sc-markers) or for condition-vs-control DE (use sc-de).
version: 0.6.0
author: OmicsClaw
license: MIT
tags:
- singlecell
- scrna
- cell-annotation
- celltypist
- popv
- singler
- scmap
- scsa
- knnpredict
- markers
requires:
- anndata
- scanpy
- numpy
- pandas
---

# sc-cell-annotation

## When to use

The user has a clustered AnnData (e.g. `obs["leiden"]`) and wants
labelled cell types in `obs["cell_type"]`. Pick a method by
data / reference availability:

- `markers` (default) — built-in or custom marker-gene scoring.
- `manual` — user-supplied cluster-to-label map (`--manual-map` or `--manual-map-file`).
- `celltypist` — pretrained `Immune_All_Low.pkl` style classifier.
- `popv` / `knnpredict` — reference AnnData mapping (PopV consensus or lightweight KNN).
- `singler` / `scmap` — R-backed reference annotation.
- `scsa` — Fisher-test DB scoring (`--species`, `--tissue`).

This skill labels — for **ranking** the genes that justify a label use
`sc-markers`; for replicate-aware condition DE use `sc-de`.

## Inputs & Outputs

| Input | Format | Required |
|---|---|---|
| Clustered AnnData | `.h5ad` with normalised `.X` and a cluster column in `obs` | yes (unless `--demo`) |
| Reference (popv / knnpredict / singler / scmap) | `.h5ad` (popv / knnpredict) or atlas selector ("HPCA", etc.) | conditional |
| Manual map (`manual`) | inline string `'0=T cell;1,2=Myeloid'` or `--manual-map-file` | conditional |
| Custom marker file (`markers`) | JSON / CSV via `--marker-file` | optional |

| Output | Path | Notes |
|---|---|---|
| Annotated AnnData | `processed.h5ad` | adds `obs["cell_type"]`, `obs["annotation_requested_method"]`, optional `obs["annotation_score"]`, optional `obsm["cell_type_prob"]` |
| Annotation overview | `tables/annotation_summary.csv` | always |
| Counts / proportions | `tables/cell_type_counts.csv` | always |
| Cluster ↔ cell-type | `tables/cluster_annotation_matrix.csv` | when a `cluster_key` is resolved |
| Figures | `figures/embedding_cell_type.png`, `figures/embedding_cluster_vs_cell_type.png`, `figures/cluster_to_cell_type_heatmap.png`, `figures/cell_type_counts.png`, `figures/embedding_annotation_score.png` | last is conditional on a numeric score |
| Report | `report.md` + `result.json` | always |

## Flow

1. Load AnnData; preflight method-specific requirements (e.g., `manual` needs a map; `popv` / `knnpredict` need a reference).
2. Resolve `--cluster-key` (auto-pick from `leiden` / `louvain` / `cell_type` if unset).
3. Dispatch to the method-specific annotator (`_METHOD_DISPATCH[method]`).
4. Record `requested_method`, `actual_method`, `used_fallback`, optional `fallback_reason` into `obs` + `result.json`.
5. Build counts / cluster-matrix tables and standard figures.
6. Save `processed.h5ad`, `tables/`, `figures/`, `report.md`, `result.json`.

## Gotchas

- **`celltypist` silently falls back to marker-based annotation.** `sc_annotate.py:508-518` swaps to `annotate_markers` when input validation fails (e.g., wrong gene-name space, missing genes); `sc_annotate.py:552-562` does the same on any CellTypist runtime exception. Always check `result.json["actual_method"]` — if it differs from your `--method`, `result.json["fallback_reason"]` records why.
- **`popv` actual backend is decided at runtime, not from `--method`.** `sc_annotate.py:577` reads `metadata["backend"]` from `apply_popv_annotation` (rapids / scvi / scanvi / classical, depending on what's installed). `result.json["backend"]` records the actually-used backend.
- **R-backed `singler` / `scmap` hard-fail when the R subprocess returns nothing.** `sc_annotate.py:637` raises `RuntimeError("R annotation method '<m>' returned no predictions")`. Confirm `R`, `SingleR` / `scmap`, and `SingleCellExperiment` are installed before picking these methods.
- **`manual` requires a map file or inline string.** `sc_annotate.py:477` raises `ValueError("Manual annotation requires --manual-map or --manual-map-file.")`. Inline form: `'0=T cell;1,2=Myeloid'`. File form supports JSON / CSV / TSV / TXT.
- **Custom marker file errors are explicit.** `sc_annotate.py:220` raises `FileNotFoundError(f"Marker file not found: {p}")`; `sc_annotate.py:238` raises `ValueError(f"No valid marker entries found in {p}")` for empty / malformed JSON / CSV.
- **`--input` is mandatory unless `--demo`.** `sc_annotate.py:1541` raises `ValueError("--input required when not using --demo")`.

## Key CLI

```bash
# Demo (built-in PBMC3K, marker-based)
python omicsclaw.py run sc-cell-annotation --demo --output /tmp/sc_annot_demo

# Marker-based (default) on existing leiden clusters
python omicsclaw.py run sc-cell-annotation \
  --input clustered.h5ad --output results/ --cluster-key leiden

# CellTypist immune model with majority voting
python omicsclaw.py run sc-cell-annotation \
  --input clustered.h5ad --output results/ \
  --method celltypist --model Immune_All_Low --celltypist-majority-voting

# PopV reference mapping (provide labelled reference)
python omicsclaw.py run sc-cell-annotation \
  --input clustered.h5ad --output results/ \
  --method popv --reference labelled_atlas.h5ad --cluster-key leiden

# Manual relabeling
python omicsclaw.py run sc-cell-annotation \
  --input clustered.h5ad --output results/ \
  --method manual --cluster-key leiden \
  --manual-map '0=T cell;1,2=Myeloid;3=B cell'
```

## See also

- `references/parameters.md` — every CLI flag, per-method parameter hints
- `references/methodology.md` — when each backend wins; reference / model notes
- `references/output_contract.md` — `obs["cell_type"]` / `obsm["cell_type_prob"]` / `result.json` keys
- Adjacent skills: `sc-clustering` (upstream — produces the cluster column), `sc-markers` (parallel — ranks the marker genes that *justify* a label; can be run before or after), `sc-de` (downstream — replicate-aware condition DE between labelled groups)
