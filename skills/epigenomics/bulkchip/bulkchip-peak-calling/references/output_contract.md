# Output Contract — bulkchip-peak-calling

> Scaffold: intended outputs once the tool-backed body is implemented.

## Output Structure

```
<output>/
├── README.md
├── report.md
├── result.json                        # chained from Step 2
├── peak_calling_summary.csv           # per-sample n_peaks + FRiP + consensus row
├── peaks/<sample>/
│   ├── <sample>_peaks.narrowPeak      # narrow mode (TF/sharp)
│   ├── <sample>_summits.bed           # narrow mode
│   └── <sample>_peaks.broadPeak       # broad mode (broad histone)
├── consensus/
│   ├── consensus_peaks.bed            # ENCODE naive-overlap (0-based BED)
│   ├── consensus_peaks.saf            # featureCounts SAF (1-based)
│   └── peak_counts.txt                # featureCounts matrix (peaks × samples)
├── qc/
│   ├── frip/                          # FRiP bar plot
│   └── IDR/                           # only with --idr (point-source)
└── reproducibility/
```

## File Contents

### `result.json`

```json
{
  "skill": "bulkchip-peak-calling",
  "version": "0.1.0",
  "steps_completed": ["...", "peak_calling"],
  "params": { "peak_mode": "auto", "qvalue": 0.05, "broad_cutoff": 0.1, "overlap_fraction": 0.5, "idr": false },
  "peak_calling": [
    { "sample": "...", "control": "...", "peak_mode": "narrow",
      "peaks_file": "...", "n_peaks": 0, "frip": 0.0, "frip_tier": "..." }
  ],
  "consensus": {
    "n_peaks": 0,
    "consensus_bed": "<output>/consensus/consensus_peaks.bed",
    "consensus_saf": "<output>/consensus/consensus_peaks.saf",
    "count_matrix":  "<output>/consensus/peak_counts.txt"
  },
  "control_map": { "<chip_sample>": "<control_sample>" },
  "genome_files": { /* carried forward */ },
  "sample_sheet": { /* carried forward */ },
  "prev_result": "<absolute path to Step 2 result.json>"
}
```

### `peak_calling_summary.csv`

| Column | Type | Meaning |
|---|---|---|
| `sample` | str | sample name; final row is the literal `consensus` |
| `control` | str | matched input/IgG sample (empty for consensus row) |
| `peak_mode` | str | `narrow` / `broad` |
| `n_peaks` | int | MACS2 peak count (sample) or consensus count |
| `frip` | float | Fraction of Reads in Peaks (empty for consensus row) |
| `frip_tier` | str | report-only tier (ENCODE sets no hard ChIP FRiP cutoff) |

### `consensus/peak_counts.txt`

featureCounts native output: header
`Geneid  Chr  Start  End  Strand  Length  <sample_1> ...`; one row per consensus
peak; sample columns are raw fragment counts. Feed columns 7+ to DESeq2/edgeR.

### `consensus/consensus_peaks.saf`

5-column TSV (1-based): `GeneID  Chr  Start  End  Strand`.
