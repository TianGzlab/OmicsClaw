# Output Contract — bulkatac-DA

## Output Structure

All skill outputs land directly under the skill's `--output` directory —
the OmicsClaw per-skill layout (no nested `DA/` step subdir). Contrast +
threshold tokens are baked into every subdirectory derived from the DA
stage, so re-running with different `--padj` / `--lfc` writes a parallel
tree rather than overwriting.

`<contrast>` = `<treat>_vs_<control>` (e.g. `T15_vs_T0`).
`<param_tag>` = `q<peak_qvalue>_padj<padj>_lfc<lfc>` (e.g. `q0.05_padj0.05_lfc1.0`).

```
<output>/                                       # the --output directory
├── README.md                                   # orientation note
├── report.md                                   # markdown summary
├── result.json                                 # structured envelope (chained from Step 3)
├── DA/<contrast>/<param_tag>/                  # contrast-results subdir
│   ├── da_results_<contrast>.tsv               # per-peak pyDESeq2 results + direction + annotation
│   ├── da_summary_<contrast>.csv               # one-row contrast summary
│   ├── da_peaks_up_<contrast>.bed              # IGV-ready, RGB red (255,0,0)
│   ├── da_peaks_down_<contrast>.bed            # IGV-ready, RGB blue (0,0,255)
│   └── da_peaks_all_<contrast>.bed             # all DA peaks, colour-coded by direction
├── plots/<contrast>/<param_tag>/
│   ├── volcano_<contrast>.pdf                  # publication-ready
│   ├── volcano_<contrast>.png                  # raster
│   └── volcano_<contrast>.tsv                  # underlying point data
└── reproducibility/commands.sh
```

## File Contents

### `report.md`

Markdown summary with three sections:

1. **Contrast** — table of `Peaks tested`, `Up`, `Down`, `padj threshold`, `log2FC threshold`.
2. **Output files** — relative paths to the four artifact files for this contrast.
3. **Genome browser tracks** — instructions for loading the BED tracks into IGV / WashU / UCSC and the RGB colour scheme.

### `result.json`

```json
{
  "skill": "bulkatac-DA",
  "version": "0.1.0",
  "params": {
    "treat":       "<treat>",
    "control":     "<control>",
    "padj":        0.05,
    "lfc":         1.0,
    "peak_qvalue": 0.05
  },
  "param_tag": "q0.05_padj0.05_lfc1.0",
  "da": {
    "contrast":          "<treat>_vs_<control>",
    "n_tested":          ...,
    "n_up":              ...,
    "n_down":            ...,
    "padj_threshold":    0.05,
    "lfc_threshold":     1.0,
    "results_tsv":       "<output>/DA/<contrast>/<param_tag>/da_results_<contrast>.tsv",
    "up_bed":            "<output>/DA/<contrast>/<param_tag>/da_peaks_up_<contrast>.bed",
    "down_bed":          "...da_peaks_down_<contrast>.bed",
    "all_bed":           "...da_peaks_all_<contrast>.bed",
    "volcano_pdf":       "<output>/plots/<contrast>/<param_tag>/volcano_<contrast>.pdf",
    "annotation_source": "<step3>/annotation/qvalue<q>/annotated_peaks.tsv | null"
  },
  "prev_result":  "<absolute path to Step 3 result.json>",
  "sample_sheet": { /* carried forward */ }
}
```

### `DA/<contrast>/<param_tag>/da_results_<contrast>.tsv`

Per-peak pyDESeq2 results (one row per consensus peak that survives
pre-filtering; tab-separated; index column = peak ID `peak_<N>`).
Written at `_lib/DA.py:196`.

| Column | Type | Meaning |
|---|---|---|
| (index) | str | consensus peak ID (e.g. `peak_42`) — assigned at `_lib/DA.py:125` |
| `chr` | str | chromosome of the consensus peak (only present when `peak_info` is supplied — inserted at `_lib/DA.py:168-171`) |
| `start` | int | 0-based start coordinate (BED-style); same conditional as `chr` |
| `end` | int | exclusive end coordinate; same conditional as `chr` |
| `baseMean` | float | mean of normalised counts across all samples (pyDESeq2) |
| `log2FoldChange` | float | unshrunk log2 fold change (`treat` over `control`) |
| `lfcSE` | float | standard error of the LFC |
| `stat` | float | Wald statistic |
| `pvalue` | float | raw Wald p-value |
| `padj` | float | Benjamini–Hochberg adjusted p-value |
| `direction` | str | `up`, `down`, or `ns` per the `--padj` / `--lfc` cuts at `_lib/DA.py:184-186` |
| `gene_name` | str | nearest gene name (only when `annotation_tsv` was joined) |
| `feature_category` | str | `promoter` / `proximal` / `distal` / `intergenic` (only when annotation joined) |
| ...others | str | additional annotation columns (HOMER fields when HOMER is the annotation source) |

Floats are written with `float_format="%.6f"` (`_lib/DA.py:196`).

### `DA/<contrast>/<param_tag>/da_summary_<contrast>.csv`

One-row CSV (built at `_lib/DA.py:199-208`):

| Column | Type | Meaning |
|---|---|---|
| `contrast` | str | `<treat>_vs_<control>` |
| `n_tested` | int | peaks that passed pyDESeq2 pre-filter |
| `n_up` | int | peaks with `direction == "up"` |
| `n_down` | int | peaks with `direction == "down"` |
| `n_ns` | int | `n_tested − n_up − n_down` |
| `padj_threshold` | float | `--padj` value used |
| `lfc_threshold` | float | `--lfc` value used |

### `DA/<contrast>/<param_tag>/da_peaks_{up,down,all}_<contrast>.bed`

9-column BED (BED9) with track header + per-peak RGB colour for direct
loading into IGV / WashU / UCSC. Written by `_lib/DA._write_browser_bed`
(up / down) and `_write_browser_bed_all` (all).

- Up: red `(255,0,0)`
- Down: blue `(0,0,255)`
- "All" combines both, retaining direction colour

Track header line (line 1) carries `name=`, `description=`, and
`itemRgb="On"` so colours render correctly on first load.

### `plots/<contrast>/<param_tag>/volcano_<contrast>.{pdf,png,tsv}`

Volcano plot in two raster sizes plus the underlying point data:

- `.pdf` — vector, publication-ready (used by `result.json["da"]["volcano_pdf"]`).
- `.png` — raster.
- `.tsv` — underlying point data with columns `baseMean`, `log2FoldChange`, `pvalue`, `direction` (`_lib/DA.py:335-336`). Useful for re-plotting with custom styling.

Significance thresholds in the plot match the `--padj` / `--lfc` flags;
`-log10(pvalue)` is clipped above a script-internal cap so single
ultra-significant points don't compress the y-axis.

### `reproducibility/commands.sh`

Single-line `python bulkatac-DA.py ...` invocation with the four
parameter flags expanded (`--treat`, `--control`, `--padj`, `--lfc`).
`peak_qvalue` is inherited from Step 3 and not flagged in the rerun
command (re-running this script picks it up from `prev_result`).
