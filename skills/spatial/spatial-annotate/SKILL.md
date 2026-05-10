---
name: spatial-annotate
description: Load when assigning per-spot cell-type labels on a spatial AnnData via marker-gene scoring or scRNA-reference mapping (Tangram / scANVI / CellAssign). Skip when computing spot-level cell-type proportions for multi-cell-per-spot platforms (use spatial-deconv) or for tissue-domain detection (use spatial-domains).
version: 0.5.0
author: OmicsClaw
license: MIT
tags:
- spatial
- annotation
- cell-type
- marker-based
- tangram
- scanvi
- cellassign
requires:
- anndata
- scanpy
- numpy
- pandas
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

| Input | Format | Required |
|---|---|---|
| Spatial AnnData | `.h5ad` with `obsm["spatial"]` | yes (unless `--demo`) |
| scRNA reference | `.h5ad` with cell-type labels (`--reference`) | required for `tangram` / `scanvi` |
| Custom marker model | path (`--model`) | optional for `marker_based` |

| Output | Path | Notes |
|---|---|---|
| Annotated AnnData | `processed.h5ad` | adds `obs["cell_type"]` (Categorical); per-method probability matrices in `obsm` — `obsm["tangram_ct_pred"]` (`_lib/annotation.py:334`), `obsm["scanvi_probabilities"]` (`:482`), `obsm["cellassign_probabilities"]` (`:612`). There is no unified `obsm["cell_type_probabilities"]` key. |
| Annotation summary | `tables/annotation_summary.csv` | per-celltype count + proportion |
| Per-spot assignments | `tables/cell_type_assignments.csv` | always |
| Cluster ↔ celltype | `tables/cluster_annotations.csv` | when an existing cluster column was used |
| Probabilities | `figure_data/annotation_probabilities.csv` | tangram / scanvi / cellassign (per-spot × celltype matrix) |
| Marker overlap | per-method `figure_data/...` CSVs | when `--analysis-type marker_based` finds a marker DB |
| Report | `report.md` + `result.json` | always |

## Flow

1. Load AnnData (`--input`) or chain through `spatial-preprocess --demo`.
2. `parser.error` validates per-method numeric flags (lines `:730-746`); `:748` raises if `--reference` is missing for tangram / scanvi; `:750` for missing reference path; `:752` for missing `--model` path.
3. Dispatch to method:
   - `marker_based`: run `sc.tl.rank_genes_groups` (or use `--model`), score against species marker DB.
   - `tangram`: train Tangram mapping from scRNA → spatial, project labels.
   - `scanvi`: train scANVI on reference + spatial, predict labels.
   - `cellassign`: solve probabilistic assignment given marker matrix.
4. Write `obs["cell_type"]` (Categorical); per-method extras (probabilities, marker overlap).
5. Save `processed.h5ad`, tables, figures, `report.md`, `result.json`.

## Gotchas

- **`--reference` is required for `tangram` / `scanvi`.** `spatial_annotate.py:748` raises `parser.error(f"--reference is required for {args.method}")`. `marker_based` and `cellassign` can run reference-free (using marker DB or marker matrix).
- **All numeric / file-path validation goes through `parser.error` (exit 2).** `spatial_annotate.py:730-746` for numeric ranges; `:748-752` for required-file paths.
- **`--input` missing → `sys.exit(1)` via `print` (NOT `parser.error`).** Same pattern as spatial-domains. Caller wrappers expecting exit-2 get exit-1.
- **`marker_based` species default is `human`.** `spatial_annotate.py:866` defaults `--species human`. For mouse data pass `--species mouse` so the built-in markers match HGNC vs MGI symbols.
- **Probabilities matrix is method-conditional.** Only `tangram` / `scanvi` / `cellassign` produce a per-spot × celltype probability matrix. `spatial_annotate.py:441` writes it to `figure_data/annotation_probabilities.csv` (note: figure_data, not tables; filename is `annotation_probabilities.csv`). `marker_based` writes only the discrete `obs["cell_type"]`. Downstream tools reading probabilities must guard for absence.
- **`obsm["spatial"]` ↔ `obsm["X_spatial"]` sync at `:102-104`.** Same dual-key pattern as spatial-domains / spatial-deconv.
- **Demo chains through `spatial-preprocess --demo` via subprocess.** `spatial_annotate.py:723` raises `RuntimeError(f"spatial-preprocess --demo failed: {result.stderr}")` on chained-run failure.
- **Tangram requires `tangram-sc` (PyPI name) but imports as `tangram`.** `spatial_annotate.py:699` records this naming wart; pip install `tangram-sc`, not `tangram`.

## Key CLI

```bash
# Demo (chained from spatial-preprocess --demo, marker_based)
python omicsclaw.py run spatial-annotate --demo --output /tmp/spatial_annot_demo

# Marker-based on a Visium with built-in human markers
python omicsclaw.py run spatial-annotate \
  --input clustered.h5ad --output results/ \
  --method marker_based --species human --marker-n-genes 50

# Tangram reference mapping
python omicsclaw.py run spatial-annotate \
  --input clustered.h5ad --output results/ \
  --method tangram --reference scrna_atlas.h5ad \
  --tangram-num-epochs 1000 --tangram-train-genes 1000

# scANVI semi-supervised
python omicsclaw.py run spatial-annotate \
  --input clustered.h5ad --output results/ \
  --method scanvi --reference scrna_atlas.h5ad \
  --scanvi-n-latent 30 --scanvi-max-epochs 400 --batch-key sample

# CellAssign with marker matrix
python omicsclaw.py run spatial-annotate \
  --input clustered.h5ad --output results/ \
  --method cellassign --cellassign-max-epochs 200
```

## See also

- `references/parameters.md` — every CLI flag, per-method tunables
- `references/methodology.md` — when each backend wins; reference vs marker-based
- `references/output_contract.md` — `obs["cell_type"]` / `obsm["cell_type_probabilities"]` schema
- Adjacent skills: `spatial-preprocess` (upstream — produces clustered spatial input), `sc-cell-annotation` (upstream — labels the scRNA reference for `--reference`), `spatial-deconv` (parallel — proportion-based for multi-cell-per-spot Visium, NOT discrete labels), `spatial-domains` (parallel — label-free tissue regions; complementary to cell-type labels), `spatial-de` (downstream — DE between cell-types from this skill)
