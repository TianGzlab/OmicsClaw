---
name: sc-multi-count
description: Load when merging multiple single-sample scRNA-seq count matrices (one per sample-from-sc-count)
  into a single downstream-ready AnnData with sample labels. Skip when input is one already-merged AnnData
  (use sc-standardize-input); FASTQ→counts on each sample (use sc-count).
trigger: merge count matrices, multi-sample count, aggregate samples, combine count outputs, cellranger aggr alternative
tags:
- singlecell
- scrna
- multi-sample
- merge
- aggregation
---

# sc-multi-count

## When to use

The user has run `sc-count` (or another counting backend) on multiple
samples separately and now needs them merged into one AnnData with a
canonical sample-label column for downstream batch-aware analysis.
Replaces `cellranger aggr` for the OmicsClaw pipeline — preserves the
canonical AnnData contract instead of re-counting.

## Inputs & Outputs

**Inputs**

- Modalities: scrna

**Outputs**

- `tables/Summary.csv`
- `tables/barcode_metrics.csv`
- `tables/barcodes.tsv`
- `tables/cell_metadata.csv`
- `tables/features.tsv`
- `tables/genes.tsv`
- `tables/metrics_summary.csv`
- `tables/per_sample_summary.csv`
- `figures/barcode_rank.png`
- `figures/count_complexity_scatter.png`
- `figures/count_distributions.png`
- `figures/sample_composition.png`
- `3M-february-2018.txt`
- `737K-august-2016.txt`
- `Aligned.sortedByCoord.out.bam`
- `analysis_summary.txt`
- `multiqc_report.html`
- `possorted_genome_bam.bam`
- `processed.h5ad`
- `standardized_input.h5ad`
- `web_summary.html`
- `report.md`
- `result.json`
- Processed AnnData (`saves_h5ad`) — adds `obs`: `sample_id`

## Flow

1. Collect per-sample AnnData paths from each `--input <path>` flag (`action="append"`); paired `--sample-id <id>` flags assign sample labels.
2. Load each, normalise the single-cell contract (`layers["counts"]`, `adata.raw`, gene name harmonisation).
3. Stack with explicit sample-label per cell.
4. Write merged AnnData; emit per-sample / per-barcode summary tables.
5. Render barcode-rank + composition figures.
6. Emit `report.md` + `result.json`.

## Gotchas

- **`--input` is `action="append"` — repeat the flag, do not comma-split.** `sc_multi_count.py` declares `--input` with `action="append"`.  Pass `--input s1.h5ad --input s2.h5ad --input s3.h5ad`; a single comma-separated value (`--input s1.h5ad,s2.h5ad`) is treated as one literal path that does not exist and triggers `FileNotFoundError`.  No directory expansion.
- **At least two `--input` paths are required.** `sc_multi_count.py` calls `parser.error("At least two --input paths required when not using --demo.")` if you pass zero or one.  For a single-sample run you don't need this skill — just use the upstream `sc-count` output directly.
- **Missing input file → hard fail.** `sc_multi_count.py` raises `FileNotFoundError` when any individual `--input` path does not resolve.  In batch pipelines, a single mistyped sample name aborts the whole merge — pre-flight your file list.
- **`--r-enhanced` is accepted but produces no R plots.** This skill emits Python figures only; the flag exists for CLI consistency.
- **No within-sample re-counting.** This is a stitching skill — it stacks already-canonical AnnData objects.  If a per-sample input has a non-canonical matrix layout, run `sc-standardize-input` on each before this; otherwise the merged contract may surface incoherent per-cell metrics downstream.

## Key CLI

```bash
# Demo (built-in two synthetic samples)
python skills/singlecell/scrna/sc-multi-count/sc_multi_count.py --demo --output /tmp/sc_multi_demo

# Three samples — repeat --input per file
python skills/singlecell/scrna/sc-multi-count/sc_multi_count.py \
  --input s1.h5ad --input s2.h5ad --input s3.h5ad \
  --output results/

# With explicit per-sample labels (paired with --input order)
python skills/singlecell/scrna/sc-multi-count/sc_multi_count.py \
  --input s1.h5ad --sample-id ctrl_a \
  --input s2.h5ad --sample-id ctrl_b \
  --input s3.h5ad --sample-id treat_a \
  --output results/
```

## See also

- `references/parameters.md` — every CLI flag and tuning hint
- `references/methodology.md` — sample-label derivation, contract harmonisation rules
- `references/output_contract.md` — merged `obs` schema, table layout
- Adjacent skills: `sc-count` (upstream — produces single-sample AnnData inputs), `sc-standardize-input` (per-sample contract canonicaliser, run before this when inputs are external), `sc-batch-integration` (downstream — corrects batch effects in the merged AnnData)

## Dependencies

Python packages this skill's script needs. They are not installed for you — check before a long run.

`anndata`, `matplotlib`, `numpy`, `pandas`, `scanpy`, `scipy`, `seaborn`
