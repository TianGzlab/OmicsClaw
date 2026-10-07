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

## Use from a step

```python
from skills._sdk.notebook import load_skill, read_input, write_output

merge = load_skill("sc-multi-count")
samples = [read_input("data/sample_a.h5ad"), read_input("data/sample_b.h5ad")]
adata = merge.merge_samples(samples, sample_ids=["sample_a", "sample_b"])
write_output(adata, "intermediate/merged.h5ad")
write_output(merge.per_sample_summary(adata), "tables/samples.csv")
```

The API returns objects and does not write files. Existing sample labels are
kept even when `sample_ids` supplies different barcode prefixes. See
`examples/example_step.py` for a count-conservation check using two halves
of PBMC3k; those halves are demonstration samples, not biological replicates.

## When to use

The user has run `sc-count` (or another counting backend) on multiple
samples separately and now needs them merged into one AnnData with a
canonical sample-label column for downstream batch-aware analysis.
This only joins matrices; it does not perform Cell Ranger's depth
normalization or recount reads.

## Inputs & Outputs

**Inputs**

- Two or more AnnData objects with raw count-like values in `.X`; the CLI
  takes repeated `--input` H5AD paths. Features are aligned by name.

**Outputs**

- `tables/barcode_metrics.csv`
- `tables/per_sample_summary.csv`
- `figures/barcode_rank.png`
- `figures/count_complexity_scatter.png`
- `figures/count_distributions.png`
- `figures/sample_composition.png`
- `processed.h5ad`
- `standardized_input.h5ad`
- `report.md`
- `result.json`
- `figures/manifest.json`, `figure_data/manifest.json` and copies of the two tables
- `reproducibility/commands.sh`, `reproducibility/requirements.txt`
- The returned AnnData has sample labels, `layers["counts"]` and a count snapshot in `.raw`.

## Flow

1. Collect per-sample AnnData paths from each `--input <path>` flag (`action="append"`); paired `--sample-id <id>` flags assign sample labels.
2. Load and tag samples, preserving an existing `obs["sample_id"]`.
3. Join features and cells, zero-fill absent features, then record the count contract.
4. Write merged AnnData; emit per-sample / per-barcode summary tables.
5. Render barcode-rank + composition figures.
6. Emit `report.md` + `result.json`.

## Gotchas

- **`--input` is `action="append"` — repeat the flag, do not comma-split.** `sc_multi_count.py` declares `--input` with `action="append"`.  Pass `--input s1.h5ad --input s2.h5ad --input s3.h5ad`; a single comma-separated value (`--input s1.h5ad,s2.h5ad`) is treated as one literal path that does not exist and triggers `FileNotFoundError`.  No directory expansion.
- **At least two `--input` paths are required.** `sc_multi_count.py` calls `parser.error("At least two --input paths required when not using --demo.")` if you pass zero or one.  For a single-sample run you don't need this skill — just use the upstream `sc-count` output directly.
- **Missing input file → hard fail.** `sc_multi_count.py` raises `FileNotFoundError` when any individual `--input` path does not resolve.  In batch pipelines, a single mistyped sample name aborts the whole merge — pre-flight your file list.
- **`--r-enhanced` is accepted but produces no R plots.** This skill emits Python figures only; the flag exists for CLI consistency.
- **No within-sample re-counting.** This is a stitching skill — it stacks already-canonical AnnData objects.  If a per-sample input has a non-canonical matrix layout, run `sc-standardize-input` on each before this; otherwise the merged contract may surface incoherent per-cell metrics downstream.
- `_api.py:merge_samples` does not validate integer counts. It labels `.X` and its copies as raw counts; passing normalized data gives a misleading matrix contract.
- `_api.py:merge_samples` keeps existing sample labels. `--sample-id` changes barcode prefixes but does not replace an existing `sample_id` column; check `tables/per_sample_summary.csv`.
- `sc_multi_count.py:_demo_adata` ignores `--sample-id` in demo mode. Its labels stay `sample_A` and `sample_B`.

## Key CLI

```bash
# Demo (two halves of PBMC3k raw counts)
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

## API

<!-- api:begin generated from _api.py; regenerate with run.py api <skill dir> --write -->

### `merge_samples(adatas, *, sample_ids=None, sample_key='sample_id', join='outer')`

Merge .X counts, align features and return a standardized copy.

Inputs are not modified. Missing features in an outer join become zeros.
Existing sample labels are kept; sample_ids supplies missing labels and,
when given, prefixes each input's barcodes. With no IDs, existing barcodes
are kept and duplicate names get numeric suffixes; missing sample labels
become sample_1, sample_2, etc. Like the CLI, this does not test whether .X
holds integer counts. Standardize external inputs before merging them.

### `barcode_metrics(adata, *, sample_key='sample_id')`

Return per-barcode .X counts and detected features, sorted by total counts.

### `per_sample_summary(adata, *, sample_key='sample_id')`

Return cell counts, median counts/features and summed UMIs for each sample.

### `sample_composition_figure(adata, *, sample_key='sample_id')`

Return a Figure showing each sample's cell count; do not write it.

### `run_info(adata, *, keep: bool=True)`

Return merge diagnostics; keep=False removes the run record.

<!-- api:end -->

## See also

- `references/parameters.md` — every CLI flag and tuning hint
- `references/methodology.md` — sample-label derivation, contract harmonisation rules
- `references/output_contract.md` — merged `obs` schema, table layout
- Adjacent skills: `sc-count` (upstream — produces single-sample AnnData inputs), `sc-standardize-input` (per-sample contract canonicaliser, run before this when inputs are external), `sc-batch-integration` (downstream — corrects batch effects in the merged AnnData)

## Dependencies

Python packages this skill's script needs. They are not installed for you — check before a long run.

`anndata`, `matplotlib`, `numpy`, `pandas`, `scanpy`, `scipy`, `seaborn`
