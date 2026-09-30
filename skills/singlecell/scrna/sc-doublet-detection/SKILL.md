---
name: sc-doublet-detection
description: Load when annotating putative doublets in single-cell RNA-seq using Scrublet, DoubletDetection,
  DoubletFinder, scDblFinder, or scds. Skip when ambient RNA is the contamination problem (use sc-ambient-removal);
  before counts exist (use sc-fastq-qc).
tags:
- singlecell
- scrna
- doublet
- scrublet
- doubletfinder
- scdblfinder
---

# sc-doublet-detection

## When to use

The user has filtered (or at least QC'd) single-cell counts and wants
to flag putative doublet barcodes before clustering / annotation.
Five backends share one CLI: `scrublet` (default, Python), `doubletdetection`
(Python), `doubletfinder` (R), `scdblfinder` (R), `scds` (R).  Per-cell
scores + binary calls land in `obs`; this skill annotates, it does not
remove cells (filter downstream with `obs["predicted_doublet"]`).

## Inputs & Outputs

**Inputs**

- Modalities: scrna
- File types: `.h5ad`

**Outputs**

- `tables/cell_metadata.csv`
- `tables/doublet_calls.csv`
- `tables/doublet_summary.csv`
- `tables/doubletfinder_results.csv`
- `tables/embedding_points.csv`
- `tables/group_summary.csv`
- `tables/scdblfinder_results.csv`
- `tables/scds_results.csv`
- `tables/summary.csv`
- `figures/embedding_doublet_calls.png`
- `figures/embedding_doublet_scores.png`
- `figures/embedding_doublet_vs_group.png`
- `figures/r_embedding_discrete.png`
- `figures/r_embedding_feature.png`
- `figures/r_feature_violin.png`
- `analysis_summary.txt`
- `input.h5ad`
- `processed.h5ad`
- `report.md`
- `result.json`
- Processed AnnData (`saves_h5ad`) — adds `obs`: `doublet_score`, `predicted_doublet`, `doublet_classification`

## Flow

1. Load AnnData; resolve `--method` against the `METHOD_REGISTRY`.
2. Run the chosen backend (R-backed methods need a working R + rpy2 stack).
3. If the requested R backend fails, fall back deterministically to a Python sibling.
4. Apply the chosen `--threshold` (or method default) to score → call.
5. Write `obs["predicted_doublet"]` + `obs["doublet_score"]`; emit tables and the score-distribution figure.
6. Save `processed.h5ad` + `report.md` + `result.json`.

## Gotchas

- **R backends silently fall back.** `sc_doublet.py` logs `"DoubletFinder runtime failed (...). Falling back to scDblFinder."` and continues; does the same for `scds → cxds`.  After every R-method run, confirm `result.json["summary"]["method_used"]` matches what you asked for — the `--method doubletfinder` flag does not guarantee DoubletFinder ran.
- **Explicit `--scds-mode` (e.g. `bcds` or `hybrid`) silently falls back to the `cxds` default on failure.** `sc_doublet.py` swaps modes when the requested one raises; the requested mode is not surfaced as an error, only logged.  Inspect the warning log when the report claims `scds` ran with the default.
- **No cells are removed.** This skill annotates barcodes; downstream filtering on `obs["predicted_doublet"]` is the user's responsibility.  If `sc-filter` was already run, doublets re-introduce themselves to the cluster graph if not filtered after this step.
- **Group summary is conditional.** `tables/group_summary.csv` is only written when `--batch-key` is set; absence does not mean failure.
- **Embedding pre-flight is non-fatal.** `sc_doublet.py` logs `"Preview embedding computation failed"` and continues; the score-distribution figure still renders without the embedding overlay.  When the figure looks sparse vs documented examples, check the warning log before assuming a bug.
- **Unsupported method → hard fail.** `sc_doublet.py` raises `ValueError("Unsupported method: ...")` for typos like `--method scrubblet`.

## Key CLI

```bash
# Demo (Scrublet)
python skills/singlecell/scrna/sc-doublet-detection/sc_doublet.py --demo --output /tmp/sc_doublet_demo

# Default Scrublet, with batch-aware grouping
python skills/singlecell/scrna/sc-doublet-detection/sc_doublet.py \
  --input filtered.h5ad --output results/ --batch-key sample_id

# scDblFinder with custom expected rate + threshold
python skills/singlecell/scrna/sc-doublet-detection/sc_doublet.py \
  --input filtered.h5ad --output results/ \
  --method scdblfinder --expected-doublet-rate 0.1 --threshold 0.4
```

## See also

- `references/parameters.md` — every CLI flag and per-method tuning hint
- `references/methodology.md` — when each backend wins, R vs Python tradeoffs
- `references/output_contract.md` — `obs` keys added + table schemas
- Adjacent skills: `sc-ambient-removal` (parallel — fixes ambient RNA, complementary to doublet removal), `sc-filter` (upstream — typically run before this), `sc-clustering` (downstream — filter doublets out before clustering)

## Dependencies

Python packages this skill's script needs. They are not installed for you — check before a long run.

`anndata`, `doubletdetection`, `h5py`, `matplotlib`, `numpy`, `pandas`, `scanpy`, `scipy`, `scrublet`, `seaborn`
