---
name: sc-cell-annotation
description: Load when assigning cell-type labels to a clustered scRNA AnnData via marker dictionaries,
  CellTypist, PopV, KNNPredict, SingleR, scmap, SCSA, or a manual cluster-to-label map. Skip when ranking
  marker genes per cluster (use sc-markers); condition-vs-control DE (use sc-de).
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

**Inputs**

- Modalities: scrna
- File types: `.h5ad`
- Requires a preprocessed AnnData (`X` normalised, PCA/neighbours present)

**Outputs**

- `tables/annotation_embedding_points.csv`
- `tables/annotation_summary.csv`
- `tables/cell_metadata.csv`
- `tables/cell_type_counts.csv`
- `tables/cellmarker2_markers.csv`
- `tables/cluster_annotation_matrix.csv`
- `tables/popv_predictions.csv`
- `tables/scmap_results.csv`
- `tables/singler_results.csv`
- `figures/cell_type_counts.png`
- `figures/cluster_to_cell_type_heatmap.png`
- `figures/embedding_annotation_score.png`
- `figures/embedding_cell_type.png`
- `figures/embedding_cluster_vs_cell_type.png`
- `figures/r_cell_barplot.png`
- `figures/r_cell_proportion.png`
- `figures/r_cell_sankey.png`
- `figures/r_embedding_discrete.png`
- `figures/r_embedding_feature.png`
- `_demo_ref.h5ad`
- `analysis_summary.txt`
- `input.h5ad`
- `processed.h5ad`
- `report.md`
- `result.json`
- Processed AnnData (`saves_h5ad`) — adds `obs`: `cell_type`, `annotation_requested_method`, `annotation_score`; `obsm`: `cell_type_prob`

## Flow

1. Load AnnData; preflight method-specific requirements (e.g., `manual` needs a map; `popv` / `knnpredict` need a reference).
2. Resolve `--cluster-key` (auto-pick from `leiden` / `louvain` / `cell_type` if unset).
3. Dispatch to the method-specific annotator (`_METHOD_DISPATCH[method]`).
4. Record `requested_method`, `actual_method`, `used_fallback`, optional `fallback_reason` into `obs` + `result.json`.
5. Build counts / cluster-matrix tables and standard figures.
6. Save `processed.h5ad`, `tables/`, `figures/`, `report.md`, `result.json`.

## Gotchas

- **`celltypist` silently falls back to marker-based annotation.** `sc_annotate.py` swaps to `annotate_markers` when input validation fails (e.g., wrong gene-name space, missing genes); does the same on any CellTypist runtime exception. Always check `result.json["actual_method"]` — if it differs from your `--method`, `result.json["fallback_reason"]` records why.
- **`popv` actual backend is decided at runtime, not from `--method`.** `sc_annotate.py` reads `metadata["backend"]` from `apply_popv_annotation` (rapids / scvi / scanvi / classical, depending on what's installed). `result.json["backend"]` records the actually-used backend.
- **R-backed `singler` / `scmap` hard-fail when the R subprocess returns nothing.** `sc_annotate.py` raises `RuntimeError("R annotation method '<m>' returned no predictions")`. Confirm `R`, `SingleR` / `scmap`, and `SingleCellExperiment` are installed before picking these methods.
- **`manual` requires a map file or inline string.** `sc_annotate.py` raises `ValueError("Manual annotation requires --manual-map or --manual-map-file.")`. Inline form: `'0=T cell;1,2=Myeloid'`. File form supports JSON / CSV / TSV / TXT.
- **Custom marker file errors are explicit.** `sc_annotate.py` raises `FileNotFoundError(f"Marker file not found: {p}")`; raises `ValueError(f"No valid marker entries found in {p}")` for empty / malformed JSON / CSV.
- **`--input` is mandatory unless `--demo`.** `sc_annotate.py` raises `ValueError("--input required when not using --demo")`.

## Key CLI

```bash
# Demo (built-in PBMC3K, marker-based)
python skills/singlecell/scrna/sc-cell-annotation/sc_annotate.py --demo --output /tmp/sc_annot_demo

# Marker-based (default) on existing leiden clusters
python skills/singlecell/scrna/sc-cell-annotation/sc_annotate.py \
  --input clustered.h5ad --output results/ --cluster-key leiden

# CellTypist immune model with majority voting
python skills/singlecell/scrna/sc-cell-annotation/sc_annotate.py \
  --input clustered.h5ad --output results/ \
  --method celltypist --model Immune_All_Low --celltypist-majority-voting

# PopV reference mapping (provide labelled reference)
python skills/singlecell/scrna/sc-cell-annotation/sc_annotate.py \
  --input clustered.h5ad --output results/ \
  --method popv --reference labelled_atlas.h5ad --cluster-key leiden

# Manual relabeling
python skills/singlecell/scrna/sc-cell-annotation/sc_annotate.py \
  --input clustered.h5ad --output results/ \
  --method manual --cluster-key leiden \
  --manual-map '0=T cell;1,2=Myeloid;3=B cell'
```

## See also

- `references/parameters.md` — every CLI flag, per-method parameter hints
- `references/methodology.md` — when each backend wins; reference / model notes
- `references/output_contract.md` — `obs["cell_type"]` / `obsm["cell_type_prob"]` / `result.json` keys
- Adjacent skills: `sc-clustering` (upstream — produces the cluster column), `sc-markers` (parallel — ranks the marker genes that *justify* a label; can be run before or after), `sc-de` (downstream — replicate-aware condition DE between labelled groups)

## Dependencies

Python packages this skill's script needs. They are not installed for you — check before a long run.

`anndata`, `celltypist`, `matplotlib`, `numpy`, `pandas`, `popv`, `scanpy`, `scipy`, `seaborn`
