---
name: sc-multi-count
description: Load when merging multiple single-sample scRNA-seq count matrices (one per sample-from-sc-count) into a single downstream-ready AnnData with sample labels. Skip when input is one already-merged AnnData (use sc-standardize-input) or for raw FASTQ multiplexing (use sc-count).
version: 0.3.0
author: OmicsClaw
license: MIT
tags:
- singlecell
- scrna
- multi-sample
- merge
- aggregation
requires:
- anndata
- pandas
---

# sc-multi-count

## When to use

The user has run `sc-count` (or another counting backend) on multiple
samples separately and now needs them merged into one AnnData with a
canonical sample-label column for downstream batch-aware analysis.
Replaces `cellranger aggr` for the OmicsClaw pipeline — preserves the
canonical AnnData contract instead of re-counting.

## Inputs & Outputs

| Input | Format | Required |
|---|---|---|
| Per-sample inputs | directory of `.h5ad` (one per sample) or list passed via `--input` | yes (unless `--demo`) |

| Output | Path | Notes |
|---|---|---|
| Merged AnnData | `processed.h5ad` | adds `obs["sample"]` from filename or label arg |
| Per-barcode summary | `tables/barcode_metrics.csv` | per-barcode count summary with sample labels |
| Per-sample summary | `tables/per_sample_summary.csv` | per-sample summary statistics |
| Diagnostic figures | `figures/barcode_rank.png`, `figures/count_distributions.png`, `figures/count_complexity_scatter.png`, `figures/sample_composition.png` | always rendered |
| Report | `report.md` + `result.json` | always written |

## Flow

1. Discover per-sample AnnData files from `--input` (file list or directory).
2. Load each, normalise the single-cell contract (`layers["counts"]`, `adata.raw`, gene name harmonisation).
3. Stack with explicit sample-label per cell.
4. Write merged AnnData; emit per-sample / per-barcode summary tables.
5. Render barcode-rank + composition figures.
6. Emit `report.md` + `result.json`.

## Gotchas

- **Missing input → hard fail.** `sc_multi_count.py:346` raises `FileNotFoundError` when any element of `--input` does not resolve.  In batch pipelines, a single mistyped sample name aborts the whole merge — pre-flight your file list.
- **`--r-enhanced` is accepted but produces no R plots.** This skill emits Python figures only; the flag exists for CLI consistency.
- **No within-sample re-counting.** This is a stitching skill — it stacks already-canonical AnnData objects.  If a per-sample input has a non-canonical matrix layout, run `sc-standardize-input` on each before this; otherwise the merged contract may surface incoherent per-cell metrics downstream.

## Key CLI

```bash
# Demo (built-in two synthetic samples)
python omicsclaw.py run sc-multi-count --demo --output /tmp/sc_multi_demo

# Merge by directory
python omicsclaw.py run sc-multi-count \
  --input cellranger_aggregated_dir/ --output results/

# Explicit list (each --input may be repeated; or a comma-separated list)
python omicsclaw.py run sc-multi-count \
  --input s1.h5ad,s2.h5ad,s3.h5ad --output results/
```

## See also

- `references/parameters.md` — every CLI flag and tuning hint
- `references/methodology.md` — sample-label derivation, contract harmonisation rules
- `references/output_contract.md` — merged `obs` schema, table layout
- Adjacent skills: `sc-count` (upstream — produces single-sample AnnData inputs), `sc-standardize-input` (per-sample contract canonicaliser, run before this when inputs are external), `sc-batch-integration` (downstream — corrects batch effects in the merged AnnData)
