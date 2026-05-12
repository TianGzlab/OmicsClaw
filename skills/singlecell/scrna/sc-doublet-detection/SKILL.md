---
name: sc-doublet-detection
description: Load when annotating putative doublets in single-cell RNA-seq using Scrublet, DoubletDetection, DoubletFinder, scDblFinder, or scds. Skip when ambient RNA is the contamination problem (use sc-ambient-removal) or before counts exist (use sc-fastq-qc / sc-count).
version: 0.3.0
author: OmicsClaw
license: MIT
tags:
- singlecell
- scrna
- doublet
- scrublet
- doubletfinder
- scdblfinder
requires:
- anndata
- numpy
- scanpy
---

# sc-doublet-detection

## When to use

The user has filtered (or at least QC'd) single-cell counts and wants
to flag putative doublet barcodes before clustering / annotation.
Five backends share one CLI: `scrublet` (default, Python), `doubletdetection`
(Python), `doubletfinder` (R), `scdblfinder` (R), `scds` (R).  Per-cell
scores + binary calls land in `obs`; this skill annotates, it does not
remove cells (filter downstream with `obs["is_doublet"]`).

## Inputs & Outputs

| Input | Format | Required |
|---|---|---|
| Single-cell AnnData | `.h5ad` (post-`sc-filter`) | yes (unless `--demo`) |

| Output | Path | Notes |
|---|---|---|
| Annotated AnnData | `processed.h5ad` | adds `obs["doublet_score"]`, `obs["is_doublet"]` |
| Per-cell calls | `tables/doublet_calls.csv` | per-barcode scores + flags |
| Run summary | `tables/summary.csv` | counts of doublets by group / threshold |
| Per-group breakdown | `tables/group_summary.csv` | only when `--batch-key` is set |
| Score distribution | `figures/doublet_score_distribution.png` | always rendered |
| Report | `report.md` + `result.json` | always written |

## Flow

1. Load AnnData; resolve `--method` against the `METHOD_REGISTRY`.
2. Run the chosen backend (R-backed methods need a working R + rpy2 stack).
3. If the requested R backend fails, fall back deterministically to a Python sibling.
4. Apply the chosen `--threshold` (or method default) to score → call.
5. Write `obs["is_doublet"]` + `obs["doublet_score"]`; emit tables and the score-distribution figure.
6. Save `processed.h5ad` + `report.md` + `result.json`.

## Gotchas

- **R backends silently fall back.** `sc_doublet.py:304` logs `"DoubletFinder runtime failed (...). Falling back to scDblFinder."` and continues; `sc_doublet.py:359` does the same for `scds → cxds`.  After every R-method run, confirm `result.json["summary"]["method_used"]` matches what you asked for — the `--method doubletfinder` flag does not guarantee DoubletFinder ran.
- **Explicit `--scds-mode` (e.g. `bcds` or `hybrid`) silently falls back to the `cxds` default on failure.** `sc_doublet.py:359` swaps modes when the requested one raises; the requested mode is not surfaced as an error, only logged.  Inspect the warning log when the report claims `scds` ran with the default.
- **No cells are removed.** This skill annotates barcodes; downstream filtering on `obs["is_doublet"]` is the user's responsibility.  If `sc-filter` was already run, doublets re-introduce themselves to the cluster graph if not filtered after this step.
- **Group summary is conditional.** `tables/group_summary.csv` is only written when `--batch-key` is set; absence does not mean failure.
- **Embedding pre-flight is non-fatal.** `sc_doublet.py:429` logs `"Preview embedding computation failed"` and continues; the score-distribution figure still renders without the embedding overlay.  When the figure looks sparse vs documented examples, check the warning log before assuming a bug.
- **Unsupported method → hard fail.** `sc_doublet.py:801` raises `ValueError("Unsupported method: ...")` for typos like `--method scrubblet`.

## Key CLI

```bash
# Demo (Scrublet)
python omicsclaw.py run sc-doublet-detection --demo --output /tmp/sc_doublet_demo

# Default Scrublet, with batch-aware grouping
python omicsclaw.py run sc-doublet-detection \
  --input filtered.h5ad --output results/ --batch-key sample_id

# scDblFinder with custom expected rate + threshold
python omicsclaw.py run sc-doublet-detection \
  --input filtered.h5ad --output results/ \
  --method scdblfinder --expected-doublet-rate 0.1 --threshold 0.4
```

## See also

- `references/parameters.md` — every CLI flag and per-method tuning hint
- `references/methodology.md` — when each backend wins, R vs Python tradeoffs
- `references/output_contract.md` — `obs` keys added + table schemas
- Adjacent skills: `sc-ambient-removal` (parallel — fixes ambient RNA, complementary to doublet removal), `sc-filter` (upstream — typically run before this), `sc-clustering` (downstream — filter doublets out before clustering)
