---
name: bulkrna-qc
description: Load when checking a bulk RNA-seq count matrix for library-size outliers, gene detection
  rates, and sample-sample correlation before DE. Skip when data is raw FASTQ (use bulkrna-read-qc); aligner
  logs (use bulkrna-read-alignment); single-cell counts (use sc-qc).
trigger: bulk QC, library size, count matrix, sample quality, gene detection, RNA-seq quality, count QC
tags:
- bulkrna
- QC
- count-matrix
- library-size
- gene-detection
- sample-correlation
- CPM
---

# bulkrna-qc

## When to use

Run as the first step on a bulk RNA-seq count matrix (genes × samples)
before differential expression.  Surfaces the four failure modes that
silently bias DE results: a sample with a tiny library, a sample with
suspiciously few detected genes, a low-correlation outlier vs the rest,
and CPM-vs-raw comparison artefacts.

## Inputs & Outputs

**Inputs**

- File types: `.csv`

**Outputs**

- `tables/cpm_normalized.csv`
- `tables/sample_stats.csv`
- `figures/expression_density.png`
- `figures/gene_detection.png`
- `figures/library_sizes.png`
- `figures/sample_correlation.png`
- `report.md`
- `result.json`

## Flow

1. Load the count matrix (raise on missing `--input` or non-existent file per `bulkrna_qc.py`).
2. Compute per-sample library sizes and detected-gene counts.
3. Compute sample × sample correlation matrix; flag samples below the median-of-medians threshold as outliers.
4. Compute CPM normalisation as a side artifact (write `tables/cpm_normalized.csv`).
5. Render four figures and emit `report.md` + `result.json`.

## Gotchas

- **Hard-fails on missing input.**  `bulkrna_qc.py` raises `ValueError("--input is required when not using --demo")`; raises `FileNotFoundError` if the path doesn't exist.  No silent demo fallback when `--input` is given but invalid — fix the path or use `--demo`.
- **CPM is for visualisation only.**  `tables/cpm_normalized.csv` is emitted as a downstream-friendly artefact, but **DE testing must always use raw counts** (PyDESeq2's negative-binomial GLM expects integer counts; feeding CPM produces meaningless dispersion estimates).  Do not pipe `cpm_normalized.csv` into `bulkrna-de`.
- **Outlier flagging is correlation-based, not biology-aware.**  If two biological conditions differ strongly (e.g. tumour vs normal), the cross-condition correlations are *expected* to be lower — the outlier flag may fire on legitimate biology.  Cross-check `result.json["outlier_samples"]` against the experimental design before excluding samples.
- **First column is treated as the gene-id column unconditionally.**  If the CSV has a header row but no leading id column (samples-only), the first sample column will be silently parsed as gene names and omitted from QC.  Inspect `report.md`'s "samples seen" count vs your design before trusting the output.

## Key CLI

```bash
python skills/bulkrna/bulkrna-qc/bulkrna_qc.py --demo --output /tmp/bulkrna-qc_demo
python skills/bulkrna/bulkrna-qc/bulkrna_qc.py --input counts.csv --output results/
```

## See also

- `references/parameters.md` — every CLI flag and tuning hint
- `references/methodology.md` — library-size, gene-detection, correlation-based outlier metrics
- `references/output_contract.md` — exact output directory layout
- Adjacent skills: `bulkrna-read-qc` / `bulkrna-read-alignment` (upstream), `bulkrna-de` (downstream — raw counts only), `bulkrna-batch-correction` (downstream if QC reveals batch effects), `sc-qc` (single-cell sibling)

## Dependencies

Python packages this skill's script needs. They are not installed for you — check before a long run.

`matplotlib`, `numpy`, `pandas`, `scipy`
