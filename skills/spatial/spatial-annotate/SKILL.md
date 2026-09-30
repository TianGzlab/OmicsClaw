---
name: spatial-annotate
description: Load when assigning per-spot cell-type labels on a spatial AnnData via marker-gene scoring
  or scRNA-reference mapping (Tangram / scANVI / CellAssign). Skip when computing spot-level cell-type
  proportions for multi-cell-per-spot platforms (use spatial-deconv); tissue-domain detection (use spatial-domains).
trigger: cell type annotation, annotate cell types, Tangram, scANVI, CellAssign, marker genes, label transfer, spatial annotation
tags:
- spatial
- annotation
- cell-type
- marker-based
- tangram
- scanvi
- cellassign
---

# spatial-annotate

## When to use

The user has a single-cell-per-spot spatial AnnData (Xenium / MERFISH /
Slide-seq) OR wants a discrete per-spot label even for Visium and has
either marker genes or a labelled scRNA reference. Four methods:

- `marker_based` (default) — built-in marker dictionaries (`--species`,
  `--marker-n-genes`, `--marker-padj-cutoff`); optional custom marker
  model via `--model`. No reference needed.
- `tangram` — gradient mapping from a labelled scRNA reference
  (`--tangram-num-epochs`, `--tangram-train-genes`, `--tangram-device`).
  Requires `tangram` + `torch`.
- `scanvi` — scvi-tools scANVI semi-supervised classifier
  (`--scanvi-n-hidden` / `--scanvi-n-latent` / `--scanvi-n-layers`,
  `--scanvi-max-epochs`). Requires `scvi-tools` + `torch`.
- `cellassign` — Bayesian probabilistic assignment with marker
  matrix (`--cellassign-max-epochs`).

For *proportion* deconvolution on Visium-style multi-cell spots use
`spatial-deconv`. For tissue domains use `spatial-domains`.

## Inputs & Outputs

**Inputs**

- File types: `.h5ad`
- Requires a preprocessed AnnData (`X` normalised, PCA/neighbours present)
- Expects `obsm`: `spatial`

**Outputs**

- `tables/annotation_cell_type_counts.csv`
- `tables/annotation_probabilities.csv`
- `tables/annotation_spatial_points.csv`
- `tables/annotation_summary.csv`
- `tables/annotation_umap_points.csv`
- `tables/cell_type_assignments.csv`
- `tables/cluster_annotations.csv`
- `tables/marker_overlap_scores.csv`
- `figures/annotation_confidence_histogram.png`
- `figures/annotation_confidence_spatial.png`
- `figures/annotation_probability_heatmap.png`
- `figures/cell_type_barplot.png`
- `figures/cell_type_spatial.png`
- `figures/cell_type_umap.png`
- `figures/marker_overlap_heatmap.png`
- `processed.h5ad`
- `report.md`
- `result.json`
- Processed AnnData (`saves_h5ad`) — adds `obs`: `cell_type`; `obsm`: `tangram_ct_pred`, `scanvi_probabilities`, `cellassign_probabilities`

## Flow

1. Load AnnData (`--input`) or chain through `spatial-preprocess --demo`.
2. `parser.error` validates per-method numeric flags; raises if `--reference` is missing for tangram / scanvi; for missing reference path; for missing `--model` path.
3. Dispatch to method:
   - `marker_based`: run `sc.tl.rank_genes_groups` (or use `--model`), score against species marker DB.
   - `tangram`: train Tangram mapping from scRNA → spatial, project labels.
   - `scanvi`: train scANVI on reference + spatial, predict labels.
   - `cellassign`: solve probabilistic assignment given marker matrix.
4. Write `obs["cell_type"]` (Categorical); per-method extras (probabilities, marker overlap).
5. Save `processed.h5ad`, tables, figures, `report.md`, `result.json`.

## Gotchas

- **`--reference` is required for `tangram` / `scanvi`.** `spatial_annotate.py` raises `parser.error(f"--reference is required for {args.method}")`. `marker_based` and `cellassign` can run reference-free (using marker DB or marker matrix).
- **All numeric / file-path validation goes through `parser.error` (exit 2).** `spatial_annotate.py` for numeric ranges; for required-file paths.
- **`--input` missing → `sys.exit(1)` via `print` (NOT `parser.error`).** Same pattern as spatial-domains. Caller wrappers expecting exit-2 get exit-1.
- **`marker_based` species default is `human`.** `spatial_annotate.py` defaults `--species human`. For mouse data pass `--species mouse` so the built-in markers match HGNC vs MGI symbols.
- **Probabilities matrix is method-conditional.** Only `tangram` / `scanvi` / `cellassign` produce a per-spot × celltype probability matrix. `spatial_annotate.py` writes it to `figure_data/annotation_probabilities.csv` (note: figure_data, not tables; filename is `annotation_probabilities.csv`). `marker_based` writes only the discrete `obs["cell_type"]`. Downstream tools reading probabilities must guard for absence.
- **`obsm["spatial"]` ↔ `obsm["X_spatial"]` sync in `_prepare_annotation_plot_state`.** Same dual-key pattern as spatial-domains / spatial-deconv.
- **Demo chains through `spatial-preprocess --demo` via subprocess.** `spatial_annotate.py` raises `RuntimeError(f"spatial-preprocess --demo failed: {result.stderr}")` on chained-run failure.
- **Tangram requires `tangram-sc` (PyPI name) but imports as `tangram`.** `spatial_annotate.py` records this naming wart; pip install `tangram-sc`, not `tangram`.

## Key CLI

```bash
# Demo (chained from spatial-preprocess --demo, marker_based)
python skills/spatial/spatial-annotate/spatial_annotate.py --demo --output /tmp/spatial_annot_demo

# Marker-based on a Visium with built-in human markers
python skills/spatial/spatial-annotate/spatial_annotate.py \
  --input clustered.h5ad --output results/ \
  --method marker_based --species human --marker-n-genes 50

# Tangram reference mapping
python skills/spatial/spatial-annotate/spatial_annotate.py \
  --input clustered.h5ad --output results/ \
  --method tangram --reference scrna_atlas.h5ad \
  --tangram-num-epochs 1000 --tangram-train-genes 1000

# scANVI semi-supervised
python skills/spatial/spatial-annotate/spatial_annotate.py \
  --input clustered.h5ad --output results/ \
  --method scanvi --reference scrna_atlas.h5ad \
  --scanvi-n-latent 30 --scanvi-max-epochs 400 --batch-key sample

# CellAssign with marker matrix
python skills/spatial/spatial-annotate/spatial_annotate.py \
  --input clustered.h5ad --output results/ \
  --method cellassign --cellassign-max-epochs 200
```

## See also

- `references/parameters.md` — every CLI flag, per-method tunables
- `references/methodology.md` — when each backend wins; reference vs marker-based
- `references/output_contract.md` — `obs["cell_type"]` / `obsm["cell_type_probabilities"]` schema
- Adjacent skills: `spatial-preprocess` (upstream — produces clustered spatial input), `sc-cell-annotation` (upstream — labels the scRNA reference for `--reference`), `spatial-deconv` (parallel — proportion-based for multi-cell-per-spot Visium, NOT discrete labels), `spatial-domains` (parallel — label-free tissue regions; complementary to cell-type labels), `spatial-de` (downstream — DE between cell-types from this skill)

## Dependencies

Python packages this skill's script needs. They are not installed for you — check before a long run.

`anndata`, `matplotlib`, `numpy`, `pandas`, `scanpy`, `scipy`, `scvi-tools`, `seaborn`, `tangram-sc`, `torch`
