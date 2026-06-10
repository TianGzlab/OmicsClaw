# Output Contract — bulkatac-peak-calling

## Output Structure

All skill outputs land directly under the skill's `--output` directory —
the OmicsClaw per-skill layout (no nested `peak_calling/` subdir). The
`qvalue<q>` tag is baked into every subdirectory derived from the
consensus / annotation / QC stages, so re-running with a different
`--qvalue` writes a parallel tree.

```
<output>/                                       # the --output directory
├── README.md                                   # orientation note
├── report.md                                   # markdown summary
├── result.json                                 # structured envelope (chained from Step 2)
├── peak_calling_summary.csv                    # per-sample + consensus row (n_peaks + tier)
├── peaks/<sample>/qvalue<q>/                   # per-sample MACS2
│   ├── {sample_name}_peaks.narrowPeak
│   └── {sample_name}_summits.bed
├── consensus/qvalue<q>/
│   ├── {cond}_pooled_peaks.narrowPeak          # per-condition pooled MACS2 output
│   ├── {cond}_reproducible.bed                 # per-condition naive-overlap survivors
│   ├── all_reproducible_sorted.bed             # union across conditions, pre-merge
│   ├── consensus_peaks.bed                     # final merged consensus (BED, 0-based)
│   ├── consensus_peaks.saf                     # featureCounts SAF (1-based start)
│   └── peak_counts.txt                         # featureCounts matrix (peaks × samples)
├── annotation/qvalue<q>/
│   ├── annotated_peaks.tsv                     # bedtools-closest annotation
│   ├── homer_annotated_full.tsv                # HOMER annotatePeaks.pl output (when HOMER available)
│   ├── peak_annotation_summary.csv             # category-fraction summary table
│   ├── tss_for_annotation.bed                  # GTF-derived TSS BED used by bedtools fallback
│   └── *.png                                   # per-condition + comparison plots (filenames carry per-prefix tag)
├── heatmap/qvalue<q>/                          # deepTools heatmaps; PNGs from {prefix}.png
└── qc_after_peak_calling/
    ├── qc_after_peak_calling_summary.csv       # FRiP per sample
    ├── frip/qvalue<q>/
    │   ├── frip_bar.tsv                        # FRiP underlying data
    │   └── *.png                               # FRiP bar chart ({prefix}.png)
    ├── pca/qvalue<q>/                          # only when ≥ 2 conditions
    │   ├── pca_peaks.tsv                       # per-peak PC loadings
    │   └── *.png                               # scatter + loadings PNGs
    ├── sample_correlation/qvalue<q>/           # only when ≥ 2 conditions
    │   ├── sample_correlation_{method}.tsv     # Pearson / Spearman correlation matrix
    │   └── *.png
    └── IDR/qvalue<q>/                          # only with --idr
        ├── {condition}_pooled_pseudo_idr.txt   # ENCODE IDR raw output (pooled pseudo-reps)
        ├── {condition}_true_rep_idr.txt        # IDR over true replicate pairs
        ├── {condition}_idr_summary.tsv
        ├── idr_summary.tsv                     # cross-condition aggregate
        └── *.png
```

## File Contents

### `report.md`

Markdown summary with four sections:

1. **Step 3a — Peak Calling** — per-sample table (`Sample | Peaks | ENCODE tier`) + consensus peak count + tier; ENCODE peak-count thresholds (replicated, IDR, FRiP).
2. **Step 3b — Peak Annotation** — category counts table (only when annotation succeeded).
3. **Step 3c — Post-peak QC** — per-sample FRiP table.
4. Disclaimer.

### `result.json`

```json
{
  "skill": "bulkatac-peak-calling",
  "version": "0.1.0",
  "steps_completed": [..."peak_calling", "peak_annotation", "qc_after_peak_calling"],
  "params": { /* qvalue, shift, extsize, overlap_fraction, threads, genome_size, skip_annotation, skip_qc, idr */ },
  "peak_calling": [
    { "sample": "...", "n_peaks": ..., "peak_count_tier": "...", "narrowpeak": "..." }
  ],
  "consensus": {
    "n_peaks":       ...,
    "consensus_bed": "<output>/consensus/qvalue<q>/consensus_peaks.bed",
    "consensus_saf": "<output>/consensus/qvalue<q>/consensus_peaks.saf",
    "count_matrix":  "<output>/consensus/qvalue<q>/peak_counts.txt"
  },
  "genome_files": { /* genome, fasta, gtf, blacklist, chrom_sizes */ },
  "sample_sheet": { /* carried forward */ },
  "mapping":      [ /* Step 2 mapping entries */ ],
  "prev_result":  "<absolute path to Step 2 result.json>"
}
```

### `peak_calling_summary.csv`

One row per sample plus a final `consensus` row (built by
`_lib.peak_calling.build_peak_calling_summary` at
`_lib/peak_calling.py:615-635`):

| Column | Type | Meaning |
|---|---|---|
| `sample` | str | sample name; last row is the literal string `consensus` |
| `n_peaks` | int | MACS2 peak count (sample) or consensus peak count |
| `peak_count_tier` | str | ENCODE tier label — `ideal` / `acceptable` / `concerning` |
| `narrowpeak` | str | absolute path to `<sample>_peaks.narrowPeak` (consensus row points at `consensus_peaks.bed`) |

### `qc_after_peak_calling/qc_after_peak_calling_summary.csv`

One row per sample (built by
`_lib.QC_after_peak_calling.build_qc_after_peak_calling_summary` at
`_lib/QC_after_peak_calling.py:1317-1331`):

| Column | Type | Meaning |
|---|---|---|
| `sample` | str | sample name |
| `frip` | float | Fraction of Reads in Peaks (in consensus set), rounded 4 dp |
| `frip_tier` | str | ENCODE tier label (`> 0.3` preferred, `> 0.2` acceptable) |
| `n_reads_in_peaks` | int | count of usable reads overlapping consensus peaks |
| `n_usable_reads` | int | usable read denominator (from Step 2's `n_usable`) |

### `consensus/qvalue<q>/consensus_peaks.bed`

ENCODE naive-overlap consensus: per condition, pooled BAMs are
re-MACS2-called and intersected with each replicate's peak set at the
`--overlap-fraction` reciprocal-overlap threshold; the per-condition
reproducible sets are then unioned (`bedtools merge`) across conditions.
6-column BED (`chrom`, `start`, `end`, `name`, `score`, `strand`); `name`
is `peak_<N>` (see `_lib/peak_calling.py:607`).

### `consensus/qvalue<q>/consensus_peaks.saf`

Simplified Annotation Format for featureCounts — 5-column TSV with
1-based start coordinates (note: BED is 0-based):

```
GeneID    Chr    Start    End    Strand
peak_1    chr1    9876    10250    .
```

### `consensus/qvalue<q>/peak_counts.txt`

featureCounts native output (built by `_lib.peak_calling.build_count_matrix`
at `_lib/peak_calling.py:480-`). Tab-separated:

- Line 1: comment with the featureCounts invocation.
- Line 2: header — `Geneid  Chr  Start  End  Strand  Length  <sample_1>  <sample_2>  ...`.
- Subsequent lines: one row per consensus peak; sample columns contain raw fragment counts (paired-end uses fragment counting, not read counting).

Feed columns 7+ directly to DESeq2 / edgeR; do NOT normalise here.

### `peaks/<sample>/qvalue<q>/<sample>_peaks.narrowPeak`

Standard MACS2 narrowPeak — 10-column BED-like with summit offset in
column 10. Generated with `--format BAMPE --nomodel` for PE samples
or `--shift -37 --extsize 73` for SE.

### `peaks/<sample>/qvalue<q>/<sample>_summits.bed`

Per-peak summit positions (single-bp BED). Used downstream for
peak-centered heatmaps and motif enrichment.

### `annotation/qvalue<q>/`

Per-condition annotation (when ≥ 2 conditions) or single-set annotation
(fallback). Each path is a `{prefix}.png` rendered next to the underlying
TSV:

- `annotated_peaks.tsv` — bedtools fallback output: per-peak TSV with `chrom`, `start`, `end`, nearest TSS, distance, feature category (`promoter` / `proximal` / `distal` / `intergenic`).
- `homer_annotated_full.tsv` — HOMER `annotatePeaks.pl` output (when HOMER is on `PATH`). Richer category set (promoter-TSS, 5'UTR, exon, intron, intergenic, 3'UTR, non-coding, TTS).
- `peak_annotation_summary.csv` — category-fraction summary table.
- `tss_for_annotation.bed` — GTF-derived TSS BED used by the bedtools fallback.
- Several `*.png` figures rendered by `_lib.peak_annotation.plot_*` — filenames are constructed at call time via a `{prefix}.png` pattern (per-condition pie, per-condition TSS-distance histogram, cross-condition comparison panel, grouped bar).

### `heatmap/qvalue<q>/`

deepTools `computeMatrix` + `plotHeatmap` PNGs (filenames constructed
via `{prefix}.png`):

- TSS-centered heatmap — all samples' BigWig signal centered on annotated TSSs (requires GTF; skipped silently if absent).
- Peak-centered heatmap — all samples' BigWig signal centered on consensus peak midpoints.

### `qc_after_peak_calling/frip/qvalue<q>/`

- `frip_bar.tsv` — underlying per-sample data (sample, FRiP, tier).
- A bar-chart PNG plotted on top of it (filename via `{prefix}.png`) with ENCODE thresholds (0.2 / 0.3) overlaid.

### `qc_after_peak_calling/pca/qvalue<q>/` *(≥ 2 conditions only)*

DESeq2 VST-normalised PCA on the `peak_counts.txt` matrix.

- `pca_peaks.tsv` — per-peak PC loadings + VST values.
- PNG scatter coloured by condition.

### `qc_after_peak_calling/sample_correlation/qvalue<q>/` *(≥ 2 conditions only)*

- `sample_correlation_{method}.tsv` — Pearson or Spearman pairwise correlation matrix (the `{method}` token expands at runtime).
- A clustered-heatmap PNG annotated by condition.

### `qc_after_peak_calling/IDR/qvalue<q>/` *(opt-in via `--idr`)*

ENCODE IDR pipeline — pseudo-replicate splitting + per-replicate MACS2 +
ENCODE IDR algorithm per condition:

- `{condition}_pooled_pseudo_idr.txt` — raw IDR output for the pooled pseudo-replicate pair.
- `{condition}_true_rep_idr.txt` — IDR over true replicate pairs.
- `{condition}_idr_summary.tsv` — per-condition peak count + IDR threshold pass/fail.
- `idr_summary.tsv` — cross-condition aggregate consumed by `plot_idr_summary`.
- A summary PNG (filename via `{prefix}.png`) of IDR rank-vs-significance curves per condition.

### `reproducibility/commands.sh`

Single-line `python bulkatac-peak-calling.py ...` invocation with all
non-default flags expanded. Re-runs of `commands.sh` exactly reproduce
the output tree (modulo `featureCounts` thread non-determinism in row
ordering, which is sorted-stable in newer Subread versions).
