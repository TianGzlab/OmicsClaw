---
name: genomics-epigenomics
description: Load when summarising a peak file (BED / narrowPeak) from ATAC-seq / ChIP-seq / CUT&Tag —
  peak count, width distribution, per-chromosome counts, score statistics. Skip when calling peaks from
  BAM (run MACS / Genrich externally first); working with single-cell ATAC (use scatac-preprocessing).
trigger: epigenomics, ATAC-seq, ChIP-seq, peak calling, MACS, motif, chromatin
tags:
- genomics
- epigenomics
- atac-seq
- chip-seq
- cut-tag
- peaks
- macs
- bed
---

# genomics-epigenomics

## When to use

The user has a peak file (BED, narrowPeak, or broadPeak) from
ATAC-seq, ChIP-seq, or CUT&Tag and wants peak summary statistics:
total peak count, median / mean width, per-chromosome distribution,
optional score column statistics. The script consumes peak files —
it does NOT call peaks from BAM. `--method` (`macs2` / `macs3` /
`homer` / `genrich`) and `--assay` (`chip-seq` / `atac-seq` /
`cut-tag`) are recorded as metadata only.

For single-cell ATAC processing use `scatac-preprocessing`.

## Inputs & Outputs

**Inputs**

- Modalities: atac-seq, chip-seq
- File types: `.bed`, `.narrowpeak`, `.csv`

**Outputs**

- `tables/peaks_per_chromosome.csv`
- `tables/peaks_summary.csv`
- `report.md`
- `result.json`

## Flow

1. Load peak file (`--input <peaks.bed|narrowPeak>`) or generate a demo at `output_dir/demo_peaks.narrowPeak` (`genomics_epigenomics.py`).
2. Parse coordinates; compute per-peak width.
3. Aggregate per-chromosome counts; per-`--assay` expected-width range is added to the report (`genomics_epigenomics.py`).
4. Write `tables/peaks_summary.csv` (`genomics_epigenomics.py`) + `tables/peaks_per_chromosome.csv` + `report.md` + `result.json`.

## Gotchas

- **No peak caller is invoked.** This skill summarises an existing BED/narrowPeak file — it does NOT run MACS / Genrich. Run them upstream and feed the output here.
- **`--method` is metadata-only; `--assay` changes the report.** `--method` is recorded in `result.json` only. `--assay` controls the per-assay expected-peak-width range injected into the summary (`genomics_epigenomics.py`) — `chip-seq` reports 200-2000 bp, `atac-seq` 150-500 bp, `cut-tag` 150-300 bp. Peak parsing itself is identical across assays.
- **`--input` REQUIRED unless `--demo`.** `genomics_epigenomics.py` raises `ValueError("--input required when not using --demo")`; non-existent paths raise `FileNotFoundError`.
- **3-column BED has no score column.** Without a score (col 5 in BED6 / narrowPeak), the summary statistics for "score" are NaN. Pre-convert to narrowPeak or BED6 for score-aware stats. Note: broadPeak's "signalValue" (col 7) and qValue (col 9) are NOT read — the parser only handles up to BED6 plus the narrowPeak 10-col extension.
- **Coordinate convention is 0-based half-open (BED).** Width = `end - start`. If your input uses 1-based closed coordinates, widths are off-by-one.
- **Demo BED has 500 fixed-pattern peaks.** Useful for smoke tests; not biologically meaningful.

## Key CLI

```bash
# Demo
python skills/genomics/genomics-epigenomics/genomics_epigenomics.py --demo --output /tmp/epi_demo

# Real ATAC-seq peaks
python skills/genomics/genomics-epigenomics/genomics_epigenomics.py \
  --input sample_peaks.narrowPeak --output results/ \
  --assay atac-seq --method macs3
```

## See also

- `references/parameters.md` — every CLI flag
- `references/methodology.md` — peak-file format conventions, score interpretation
- `references/output_contract.md` — `tables/peaks_summary.csv` + per-chromosome
- Adjacent skills: `scatac-preprocessing` (parallel — single-cell ATAC), `genomics-alignment` (upstream — BAMs feed peak callers), `genomics-qc` (upstream — FASTQ QC before alignment), `bulkrna-de` (parallel — bulk RNA-seq differential expression)

## Dependencies

Python packages this skill's script needs. They are not installed for you — check before a long run.

`numpy`, `pandas`
