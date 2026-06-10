# Output Contract — bulkatac-footprinting

## Output Structure

All skill outputs land directly under the skill's `--output` directory —
the OmicsClaw per-skill layout (no nested `footprinting/` subdir). JASPAR
motifs (when auto-downloaded) cache under `motifs/`; per-condition staging
artifacts live under `merged_bams/` and the various TOBIAS sub-tool dirs.

```
<output>/                                       # the --output directory
├── README.md                                   # orientation note
├── report.md                                   # markdown summary
├── result.json                                 # structured envelope (chained from Step 3)
├── merged_peaks.bed                            # consensus peaks staged for TOBIAS
├── concat_peaks.bed                            # intermediate (per-condition concatenation)
├── sorted_peaks.bed                            # intermediate (sorted concat)
├── top_tf_ranking.tsv                          # top TFs ranked by binding score / differential change
├── motifs/                                     # only when --motifs was auto-downloaded
│   └── JASPAR2024_CORE_<group>.jaspar
├── merged_bams/
│   └── <cond>_merged.bam                       # per-condition merged BAM (replicates pooled)
├── atacorrect/<cond>/
│   ├── {prefix}_corrected.bw                   # Tn5-bias-corrected signal
│   ├── {prefix}_uncorrected.bw                 # raw (pre-correction) reference
│   ├── {prefix}_bias.bw                        # learned Tn5 sequence-bias track
│   ├── {prefix}_expected.bw                    # expected signal under the bias model
│   └── {prefix}_atacorrect.pdf                 # bias-correction QC PDF
├── footprints/<cond>/
│   └── <cond>_footprints.bw                    # per-base footprint score BigWig (ScoreBigwig)
├── bindetect/                                  # TOBIAS BINDetect output
│   ├── bindetect_results.txt                   # one row per TF — scores, bound count, log2FC, pvalue
│   ├── bindetect_figures.pdf                   # built-in score distributions + per-TF volcanos
│   └── <TF>/beds/                              # per-TF, per-condition TFBS BEDs
│       └── <TF>_<cond>_all.bed                 # all scanned TFBSs (TOBIAS also writes _bound / _unbound siblings)
├── plots/
│   ├── aggregate/
│   │   └── aggregate_{tf_name}.png             # aggregate footprint profile per top TF (top 20 by default)
│   └── tf_differential_volcano.pdf             # custom volcano (only when ≥ 2 conditions)
└── reproducibility/commands.sh
```

## File Contents

### `report.md`

Markdown summary with five sections:

1. **Parameters** — genome FASTA / motif DB / condition list / thread count.
2. **Step 2: Tn5 bias correction (ATACorrect)** — per-condition `corrected.bw` paths.
3. **Step 3: Footprint scoring (ScoreBigwig)** — per-condition `footprints.bw` paths.
4. **Step 4: Motif scanning + binding (BINDetect)** — n_motifs_tested, `is_differential`, n TFs above the differential threshold (only with ≥ 2 conditions), and pointers to `bindetect_results.txt` + `bindetect_figures.pdf`.
5. **Normalisation + statistical test** — table of normalisation methods (ATACorrect `10M / reads_in_peaks`; BINDetect quantile) + the spatial-test description.

### `result.json`

```json
{
  "skill": "bulkatac-footprinting",
  "version": "0.1.0",
  "params": {
    "genome":       "<genome>",
    "genome_fasta": "<absolute path>",
    "motifs_file":  "<absolute path>",
    "treat":        "<cond_b | null>",
    "control":      "<cond_a | null>",
    "threads":      16,
    "blacklist":    "<absolute path | null>"
  },
  "footprinting": {
    "conditions":    ["<cond_a>", "<cond_b>"],
    "n_conditions":  2,
    "merged_peaks":  "<output>/merged_peaks.bed",
    "atacorrect": [
      { "condition": "<cond>", "corrected_bw": "<output>/atacorrect/<cond>/<prefix>_corrected.bw" }
    ],
    "footprints": [
      { "condition": "<cond>", "footprint_bw": "<output>/footprints/<cond>/<cond>_footprints.bw" }
    ],
    "bindetect": {
      "results_txt":     "<output>/bindetect/bindetect_results.txt",
      "figures_pdf":     "<output>/bindetect/bindetect_figures.pdf",
      "n_motifs_tested": ...,
      "n_differential":  ...,            // |change| > 0.1
      "is_differential": true            // false in single-condition mode
    },
    "top_tf_ranking":  "<output>/top_tf_ranking.tsv",
    "aggregate_plots": [
      "<output>/plots/aggregate/aggregate_<tf>.png", ...
    ]
  },
  "prev_result":  "<absolute path to Step 3 result.json>"
}
```

### `bindetect/bindetect_results.txt`

TOBIAS-native BINDetect output — one row per TF. Tab-separated; the
exact column set comes from TOBIAS and is documented at
`https://github.com/loosolab/TOBIAS`. Typical columns:

| Column | Meaning |
|---|---|
| `output_prefix` | TF identifier (matrix ID + name) |
| `name` | TF gene symbol |
| `motif_id` | JASPAR matrix ID |
| `cluster` | motif-similarity cluster |
| `total_tfbs` | scanned binding sites across the consensus |
| `<cond>_mean_score` | per-condition mean BINDetect score |
| `<cond>_bound` | per-condition bound-TFBS count |
| `<cond_b>_<cond_a>_change` | log2 binding-change (differential mode only) |
| `<cond_b>_<cond_a>_pvalue` | one-sample t-test against ~100 background log2FCs |

In single-condition mode the differential change / pvalue columns are
absent and `is_differential = false` in `result.json`.

### `bindetect/<TF>/beds/<TF>_<cond>_all.bed` (+ TOBIAS-native bound / unbound siblings)

Per-TF BEDs of scanned TFBSs (one `_all.bed` per condition; TOBIAS also
emits matching `_bound` / `_unbound` siblings with the same naming
convention — classified by footprint score against a per-TF threshold).

`_lib.footprinting.plot_aggregate_top_tfs` (`_lib/footprinting.py:431-437`)
loads the `_all.bed` files for the aggregate plots.

### `top_tf_ranking.tsv`

Top TFs ranked by score / differential change. Used as the canonical
short-list for downstream interpretation. Columns mirror a subset of
`bindetect_results.txt` (TF identity + ranking score + bound counts).

### `atacorrect/<cond>/<prefix>_*.bw`

TOBIAS ATACorrect quartet:

- `<prefix>_corrected.bw` — Tn5-bias-corrected signal (use this downstream).
- `<prefix>_uncorrected.bw` — raw signal for visual comparison.
- `<prefix>_bias.bw` — learned per-position bias track.
- `<prefix>_expected.bw` — expected signal under the bias model.

`<prefix>` is `<cond>_<consensus-stem>` per TOBIAS convention.

### `atacorrect/<cond>/<prefix>_atacorrect.pdf`

Multi-page QC PDF: per-position bias profile, score distributions,
read-pileup vs corrected-signal comparison at random peaks.

### `footprints/<cond>/<cond>_footprints.bw`

Per-base footprint score BigWig from `ScoreBigwig`. Larger values =
deeper protein-protection footprint (likely TF occupancy).

### `plots/aggregate/aggregate_<tf>.png`

Aggregate footprint profile per top TF — averaged corrected-signal
intensity across all bound TFBSs, with the motif location overlaid.
Top 20 TFs by default (per `_lib/footprinting.py:752-754`).

### `plots/tf_differential_volcano.pdf`

Custom volcano plot — per-TF differential binding change vs
significance. Only emitted when `≥ 2 conditions` (i.e.
`is_differential = true`).

### `merged_bams/<cond>_merged.bam`

Per-condition merged BAM (`samtools merge` of all replicates of that
condition). Required because ATACorrect / ScoreBigwig take a single BAM
per condition. Indexed in place.

### `merged_peaks.bed` + `concat_peaks.bed` + `sorted_peaks.bed`

`merged_peaks.bed` is the final consensus passed to TOBIAS (carried over
from `bulkatac-peak-calling`); `concat_peaks.bed` and `sorted_peaks.bed`
are pre-merge intermediates left in place for debugging.

### `motifs/JASPAR2024_CORE_<group>.jaspar`

Only written when `--motifs` was auto-downloaded. Cached so re-runs skip
the download. Group is one of `vertebrates` / `plants` / `insects` /
`fungi` / `nematodes` (`bulkatac-footprinting.py:98-119`).

### `reproducibility/commands.sh`

Single-line `python bulkatac-footprinting.py ...` invocation with
resolved `--genome-fasta` and `--motifs` paths, so re-runs of
`commands.sh` skip both auto-detection and the JASPAR download.
