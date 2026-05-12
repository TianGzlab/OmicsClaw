---
name: genomics-epigenomics
description: Load when summarising a peak file (BED / narrowPeak) from ATAC-seq / ChIP-seq / CUT&Tag — peak count, width distribution, per-chromosome counts, score statistics. Skip when calling peaks from BAM (run MACS / Genrich externally first) or when working with single-cell ATAC (use `scatac-preprocessing`).
version: 0.5.0
author: OmicsClaw
license: MIT
tags:
- genomics
- epigenomics
- atac-seq
- chip-seq
- cut-tag
- peaks
- macs
- bed
requires:
- pandas
- numpy
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

| Input | Format | Required |
|---|---|---|
| Peaks | `.bed` (3-col or 6-col) or `.narrowPeak` (10-col); broadPeak (9-col) loads as BED6 with cols 7-9 dropped | yes (unless `--demo`) |
| Assay metadata | `--assay {chip-seq,atac-seq,cut-tag}` (default `chip-seq`) | no |
| Caller metadata | `--method {macs2,macs3,homer,genrich}` (default `macs2`) | no |

| Output | Path | Notes |
|---|---|---|
| Peaks summary | `tables/peaks_summary.csv` | per-peak start/end/width/score |
| Per-chromosome | `tables/peaks_per_chromosome.csv` | peaks count per chromosome |
| Report | `report.md` + `result.json` | always; `result.json["data"]["peaks_per_chrom"]` mirrors the table |

## Flow

1. Load peak file (`--input <peaks.bed|narrowPeak>`) or generate a demo at `output_dir/demo_peaks.narrowPeak` (`genomics_epigenomics.py:211`).
2. Parse coordinates; compute per-peak width.
3. Aggregate per-chromosome counts; per-`--assay` expected-width range is added to the report (`genomics_epigenomics.py:172-178`).
4. Write `tables/peaks_summary.csv` (`genomics_epigenomics.py:352`) + `tables/peaks_per_chromosome.csv` (`:360`) + `report.md` + `result.json` (`:366`).

## Gotchas

- **No peak caller is invoked.** This skill summarises an existing BED/narrowPeak file — it does NOT run MACS / Genrich. Run them upstream and feed the output here.
- **`--method` is metadata-only; `--assay` changes the report.** `--method` is recorded in `result.json` only. `--assay` controls the per-assay expected-peak-width range injected into the summary (`genomics_epigenomics.py:172-178`) — `chip-seq` reports 200-2000 bp, `atac-seq` 150-500 bp, `cut-tag` 150-300 bp. Peak parsing itself is identical across assays.
- **`--input` REQUIRED unless `--demo`.** `genomics_epigenomics.py:334` raises `ValueError("--input required when not using --demo")`; non-existent paths raise `FileNotFoundError` at `:337`.
- **3-column BED has no score column.** Without a score (col 5 in BED6 / narrowPeak), the summary statistics for "score" are NaN. Pre-convert to narrowPeak or BED6 for score-aware stats. Note: broadPeak's "signalValue" (col 7) and qValue (col 9) are NOT read — the parser only handles up to BED6 plus the narrowPeak 10-col extension.
- **Coordinate convention is 0-based half-open (BED).** Width = `end - start`. If your input uses 1-based closed coordinates, widths are off-by-one.
- **Demo BED has 500 fixed-pattern peaks.** Useful for orchestrator smoke tests; not biologically meaningful.

## Key CLI

```bash
# Demo
python omicsclaw.py run genomics-epigenomics --demo --output /tmp/epi_demo

# Real ATAC-seq peaks
python omicsclaw.py run genomics-epigenomics \
  --input sample_peaks.narrowPeak --output results/ \
  --assay atac-seq --method macs3
```

## See also

- `references/parameters.md` — every CLI flag
- `references/methodology.md` — peak-file format conventions, score interpretation
- `references/output_contract.md` — `tables/peaks_summary.csv` + per-chromosome
- Adjacent skills: `scatac-preprocessing` (parallel — single-cell ATAC), `genomics-alignment` (upstream — BAMs feed peak callers), `genomics-qc` (upstream — FASTQ QC before alignment), `bulkrna-de` (parallel — bulk RNA-seq differential expression)
