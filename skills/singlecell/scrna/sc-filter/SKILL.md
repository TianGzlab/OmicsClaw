---
name: sc-filter
description: Load when removing low-quality cells and lowly-detected genes from a single-cell AnnData
  using QC-derived thresholds or tissue presets. Skip when the full normalize→HVG→PCA→cluster pipeline
  (use sc-preprocessing); reads are still raw FASTQ (use sc-fastq-qc).
trigger: filter cells, cell filtering, gene filtering, remove low quality, qc filtering, tissue-specific thresholds
tags:
- singlecell
- scrna
- filter
- qc
- mitochondrial
---

# sc-filter

## When to use

The user has reviewed `sc-qc` output and now wants to actually drop
low-quality cells and lowly-detected genes — by per-cell thresholds
(`--min-genes`, `--max-genes`, `--max-mt-percent`, `--min-counts`,
`--max-counts`, `--min-cells`) or tissue-specific presets (`--tissue
brain` / `pbmc` / etc.).  This skill removes cells; it does not
normalise, cluster, or annotate.

## Inputs & Outputs

**Inputs**

- Modalities: scrna
- File types: `.h5ad`

**Outputs**

- `tables/cell_metadata.csv`
- `tables/filter_reasons.csv`
- `tables/filter_state.csv`
- `tables/filter_stats.csv`
- `tables/filter_summary.csv`
- `tables/gene_expression.csv`
- `tables/retention_summary.csv`
- `figures/filter_comparison.png`
- `figures/filter_reason_summary.png`
- `figures/filter_state_scatter.png`
- `figures/filter_summary.png`
- `figures/filter_thresholds.png`
- `figures/r_feature_violin.png`
- `analysis_summary.txt`
- `processed.h5ad`
- `report.md`
- `result.json`
- Processed AnnData (`saves_h5ad`)

## Flow

1. Load AnnData via shared loader; persist `expression_source` in `result.json`.
2. If `--tissue` is set, apply preset thresholds (overrides any matching CLI flag silently).
3. Compute per-cell metrics; mark cells / genes failing each rule.
4. Drop cells failing any active rule; drop genes detected in fewer than `--min-cells` cells.
5. Emit before/after retention tables and figures.
6. Save `processed.h5ad` + `report.md` + `result.json`.

## Gotchas

- **`--tissue` presets silently override matching CLI flags.** Passing `--tissue pbmc` plus `--max-mt-percent 30` resolves to whatever the PBMC preset declares for `max_mt_percent`, not 30.  When mixing, omit the explicit flag or override the preset by editing it in `references/methodology.md`.  Result tables record the *effective* thresholds, not the user-passed ones.
- **QC metrics are computed on demand if missing.** `sc_filter.py` calls `ensure_qc_metrics(...)` when the AnnData lacks `n_genes_by_counts` / `pct_counts_mt`, so this skill works *without* a prior `sc-qc` run.  Running `sc-qc` first is still recommended for diagnostic figures, but it's not a hard prerequisite.
- **Input file missing → hard fail.** `sc_filter.py` raises `FileNotFoundError` on a non-existent `--input`.  Common in batch pipelines when an upstream output dir was renamed.
- **`expression_source` is recorded but does not gate the filter.** `result.json["summary"]["expression_source"]` carries which matrix the metrics came from (`layers.counts` / `adata.raw` / `adata.X`).  Filtering still runs even if the source is log-normalised — but `total_counts` / mt% interpretations become meaningless.  Check the source before relying on the thresholds.
- **`processed.h5ad` is contract-preserving, not contract-canonical.** The skill keeps whatever layers / `raw` / `uns` the input had; if upstream skipped `sc-standardize-input`, downstream skills may still mis-classify the count source.  Run `sc-standardize-input` before `sc-filter` when input came from outside OmicsClaw.

## Key CLI

```bash
# Demo
python skills/singlecell/scrna/sc-filter/sc_filter.py --demo --output /tmp/sc_filter_demo

# Threshold-based (typical PBMC defaults)
python skills/singlecell/scrna/sc-filter/sc_filter.py \
  --input qc_output.h5ad --output results/ \
  --min-genes 200 --max-mt-percent 20 --min-cells 3

# Tissue preset (overrides matching CLI flags)
python skills/singlecell/scrna/sc-filter/sc_filter.py \
  --input qc_output.h5ad --output results/ --tissue pbmc
```

## See also

- `references/parameters.md` — every CLI flag and tuning hint
- `references/methodology.md` — tissue preset definitions, threshold semantics
- `references/output_contract.md` — `processed.h5ad` + table schemas
- Adjacent skills: `sc-qc` (upstream — produces metrics; recommended before this), `sc-doublet-detection` (parallel — drops doublets), `sc-preprocessing` (downstream — normalise/HVG/PCA on the filtered AnnData)

## Dependencies

Python packages this skill's script needs. They are not installed for you — check before a long run.

`anndata`, `matplotlib`, `numpy`, `pandas`, `scanpy`, `scipy`, `seaborn`
