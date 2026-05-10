---
name: spatial-de
description: Load when ranking spatial cluster markers or comparing two spatial groups in spatial transcriptomics. Skip if the data is single-cell (use sc-de) or bulk (use bulkrna-de), or for spatially variable expression discovery (use spatial-genes).
version: 0.5.0
author: OmicsClaw Team
license: MIT
tags:
- spatial
- differential-expression
- markers
- wilcoxon
- t-test
- pydeseq2
- pseudobulk
---

# spatial-de

## When to use

The user has a preprocessed spatial transcriptomics AnnData (Visium /
Xenium / MERFISH / Slide-seq) and wants either (a) cluster-marker
ranking via Scanpy `wilcoxon` / `t-test`, or (b) replicate-aware
two-group condition DE via `pydeseq2` pseudobulk.  The wrapper exposes
the official Scanpy filter controls and PyDESeq2 GLM controls directly,
and refuses to fabricate replicates — pseudobulk requires a real
`sample_key`.

## Inputs & Outputs

| Input | Format | Required |
|---|---|---|
| Preprocessed AnnData | `.h5ad` | yes (or `--demo`) |
| Sample/replicate column in `obs` | `--sample-key` (default `sample_id`) | only for `pydeseq2` |
| Raw counts in `layers["counts"]` | layer | recommended for `pydeseq2`; fallback chain to `adata.raw` then `adata.X` with warning |

| Output | Path | Notes |
|---|---|---|
| Processed AnnData | `processed.h5ad` | DE results stashed in `uns` |
| Full DE table | `tables/de_full.csv` | per-gene results across all groups |
| Top markers | `tables/markers_top.csv` | `--n-top-genes` per group |
| Standard gallery | `figures/*.png` | recipe-driven (overview / diagnostic / supporting / uncertainty roles) |
| `figure_data/manifest.json` | for the optional R customization layer |
| Report | `report.md` + `result.json` | always |

## Flow

1. Load the preprocessed AnnData; if absent and not `--demo`, run `spatial-preprocess` first (raises `RuntimeError` at `spatial_de.py:1370` if upstream script missing).
2. Validate the matrix contract and method-specific arguments (Scanpy methods need `X = log_normalized`; `pydeseq2` needs counts).
3. For Scanpy paths: run `rank_genes_groups` and (default-on) the official `filter_rank_genes_groups` post-filter.
4. For `pydeseq2`: pseudobulk by `sample_key` × group, drop bins below `--min-cells-per-sample` / `--min-counts-per-gene`, fit PyDESeq2 GLM.  If the same biological sample is in both groups, auto-switch to paired design `~ sample_id + condition`.
5. Render the recipe-driven standard gallery.
6. Write `processed.h5ad`, tables, `figure_data/manifest.json`, `report.md`, `result.json`, and reproducibility script.

## Gotchas

- **`pydeseq2` requires `--sample-key` distinct from `--groupby`.** Hard-fails at `spatial_de.py:1455` with `"--sample-key and --groupby must be different for pydeseq2"`.  Default `sample_key` is `sample_id`; if the user's grouping column happens to be the same name, swap one.
- **`pydeseq2` requires explicit `--group1` and `--group2`.** Hard-fails at `spatial_de.py:1458` (the `--demo` path bypasses this by picking the first two groups it finds).  Other methods treat them as optional (cluster-vs-rest if absent).
- **Counts-layer fallback to `adata.X` is logged but not blocked.** When `pydeseq2` cannot find `layers["counts"]` or `adata.raw`, `spatial_de.py:1684-1686` falls through to `adata.X` with a warning that says verbatim *"If `adata.X` is log-normalized, pseudobulk DE will be statistically invalid."*  Verify `result.json["summary"]["expression_source"]` after every pseudobulk run; do not assume the warning blocked the run.
- **Paired design auto-activates when ≥2 samples each contribute to both groups (with ≥2 cells per side).** Per `skills/spatial/_lib/de.py:485-506` (`_choose_pydeseq2_design`): the wrapper switches the DESeq2 formula to `~ sample_id + condition` only when at least 2 distinct `sample_id` values appear in both groups AND each side of the resulting paired split retains ≥2 cells; otherwise it stays unpaired (`~ condition`).  Check `result.json["summary"]["paired_design"]` (also surfaced at `spatial_de.py:454`); if the run was unintentionally paired (e.g. the user merged samples by accident), the LFC interpretation changes.
- **Skipped sample-group bins ARE surfaced** (unlike sc-de's silent drops).  The full reason list lives in `result.json`'s skipped-sample summary (each row carries `sample_id`, `condition`, `reason`, `n_cells` per `spatial_de.py:1198`).  When pydeseq2 reports few DEGs, inspect this list before assuming biological null.
- **Scanpy `filter_markers` is cluster-style only.** The `--filter-markers` post-filter (default on) enforces the `min_in_group_fraction` / `min_fold_change` / `max_out_group_fraction` triplet from `scanpy.tl.filter_rank_genes_groups` — appropriate for cluster markers, but for a `--group1 vs --group2` contrast it can drop genuine effect genes whose between-condition cell coverage is low.  Pass `--no-filter-markers` for two-group condition comparisons.

## Key CLI

```bash
# Demo: 200-spot synthetic Visium with three domains
python omicsclaw.py run spatial-de --demo

# Default exploratory cluster-marker discovery
python omicsclaw.py run spatial-de \
  --input processed.h5ad --output results/ \
  --groupby leiden --method wilcoxon

# Replicate-aware condition contrast via PyDESeq2 pseudobulk
python omicsclaw.py run spatial-de \
  --input processed.h5ad --output results/ \
  --method pydeseq2 --groupby condition \
  --group1 treated --group2 control \
  --sample-key sample_id \
  --min-cells-per-sample 10 --min-counts-per-gene 10
```

## See also

- `references/parameters.md` — every CLI flag and per-method tuning hint
- `references/methodology.md` — Scanpy `wilcoxon` / `t-test` paths, PyDESeq2 GLM details, design validation, dependencies
- `references/output_contract.md` — Visualization Contract (4 gallery roles) + Output Structure
- `references/r_visualization.md` — R customization layer reading `figure_data/`; templates live in `r_visualization/`
- Adjacent skills: `spatial-preprocess` (upstream prerequisite), `spatial-domains` (upstream cluster discovery), `spatial-genes` (sibling: spatially variable gene discovery, not group-DE), `spatial-condition` (sibling: condition comparison **without** a per-cluster slice — use `spatial-de --method pydeseq2` when you also need a `groupby` cluster context), `sc-de` / `bulkrna-de` (same-question DE for the other two data modalities)
