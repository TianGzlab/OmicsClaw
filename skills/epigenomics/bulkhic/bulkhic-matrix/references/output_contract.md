# Output Contract — bulkhic-matrix

## Output Structure

All skill outputs land under the skill's `--output` (a.k.a. `--wd`) directory.
Each sample gets its own matrix subdirectory; per-condition replicate pools are
written as `<condition>_combined`. QC artifacts are written per-resolution under
`matrix_QC/<kind>/<res>/`, and whole-genome contact maps under
`matrix_visualization/<res>/`.

`<sample>` = a replicate name from the Step-2 sample sheet.
`<condition>` = a biological condition; its pooled matrix is named
`<condition>_combined` (only built when a condition has ≥2 replicates; skip with
`--no-combine`).
`<res>` = a resolution in bp (e.g. `5000`, `10000`, `50000`, `100000`).
`<viz_res>` = the whole-genome contact-map resolution (`--viz-resolution`, default `500000`).

```
<output>/                                              # the --output / --wd directory
├── README.md                                          # orientation note
├── report.md                                          # markdown summary + sample table
├── result.json                                        # structured envelope (chained downstream)
├── matrix_summary.csv                                 # one row per matrix (sample, mcool, resolutions, …)
├── matrix/
│   ├── <sample>/
│   │   ├── <sample>.mcool                             # multi-resolution, ICE-balanced contact matrix
│   │   └── <sample>.hic                               # optional Juicebox export (--format both)
│   └── <condition>_combined/
│       ├── <condition>_combined.mcool                 # per-condition pool (replicate contacts summed)
│       └── <condition>_combined.hic                   # optional, pooled (--format both)
├── matrix_QC/
│   ├── p_curve/<res>/                                 # P(s) contact-decay QC, per resolution
│   │   ├── <sample>.expected_cis.<res>.tsv            # cooltools expected-cis table
│   │   ├── <sample>.P_curve.<res>.png                 # per-sample P(s) decay + log-log slope (+ .pdf)
│   │   └── P_curve_of_all.{pdf,png}                   # ≥2-sample P(s) overlay (the MS figure)
│   ├── scc/<res>/                                     # HiCRep SCC reproducibility, per resolution
│   │   ├── scc_values.tsv                             # pairwise SCC matrix
│   │   ├── scc_heatmap.{pdf,png}                      # clustered SCC heatmap
│   │   └── pairs/scc_<sample1>_vs_<sample2>.txt       # raw per-pair hicrep output
│   └── pca/<res>/                                     # sample PCA on contact matrices, per resolution
│       ├── pca_coords.tsv                             # PC1..PC5 coordinates per sample
│       └── sample_pca.{pdf,png}                       # PC1/PC2 scatter, coloured by condition
├── matrix_visualization/<viz_res>/
│   └── <sample>.{pdf,png}                             # whole-genome balanced contact map per sample
└── reproducibility/
    ├── commands.sh                                    # exact rerun command
    └── requirements.txt                               # pinned tool list
```

## File Contents

### `report.md`

Markdown summary with:

1. **Header** — sample count, base binsize, the full resolution pyramid.
2. **Outputs table** — one row per matrix: `Sample | Kind | .mcool | .hic | P(s)`,
   where `Kind` is `replicate` or `pooled (<members>)`.
3. **Per-condition pooling note** — when any combined matrices were built.
4. **Next Steps** — pointers to bulkhic-compartments / -insulation / -loops / -pileup.

### `result.json`

Structured envelope chained from the Step-2 (`bulkhic-mapping`) result and
consumed by every downstream Hi-C skill. Key fields:

```json
{
  "skill":   "bulkhic-matrix",
  "version": "0.1.0",
  "params": {
    "base_binsize":        1000,
    "resolutions":         [1000, 2000, 5000, "..."],
    "p_curve_resolutions": [5000, 10000, 50000, 100000],
    "scc_resolutions":     [5000, 10000, 50000, 100000],
    "viz_resolution":      500000,
    "format":              "mcool",
    "make_hic":            false,
    "combine":             true,
    "scc":                 { "<res>": { "min": "...", "mean": "...", "png": "..." } },
    "pca":                 { "<res>": { "png": "...", "coords": "...", "var": ["...","..."] } },
    "contact_maps":        { "<sample>": "<output>/matrix_visualization/<viz_res>/<sample>.png" }
  },
  "matrix": [
    {
      "sample":       "<sample>",
      "mcool":        "<output>/matrix/<sample>/<sample>.mcool",
      "cool":         null,
      "base_binsize": 1000,
      "resolutions":  [1000, "..."],
      "balanced":     true,
      "hic":          "<output>/matrix/<sample>/<sample>.hic | null",
      "combined":     false,
      "condition":    "<condition>",
      "members":      ["<sample>", "..."]
    }
  ],
  "genome_files": { "...carried from Step 2..." },
  "sample_sheet": { "...carried from Step 2..." },
  "prev_result":  "<absolute path to Step-2 result.json>"
}
```

The base `.cool` is deleted after zoomify (only the `.mcool` is kept), so the
`cool` field in `result.json` is `null`.

### `matrix_summary.csv`

One row per matrix (written by `_lib/matrix.py:write_matrix_summary`). Columns:
`sample`, `combined`, `condition`, `members` (`;`-joined), `mcool`,
`base_binsize`, `resolutions` (comma-joined), `balanced`, `hic`, `expected_tsv`.

### `matrix/<sample>/<sample>.mcool`

The primary deliverable: a multi-resolution, ICE-balanced cooler built via
`cooler cload pairs` → `cooler balance --mad-max 5` → `cooler zoomify --balance`.
Resolutions are the `--resolutions` pyramid (default 1 kb → 1 Mb), each with a
`weight` (balancing) column. This is the format every downstream skill reads.

### `matrix/<condition>_combined/<condition>_combined.mcool`

Per-condition pool: the replicate base `.cool` files for a condition are summed
with `cooler merge`, then balanced + zoomified like any other matrix. Deeper
coverage for loop / TAD / compartment calling. Only conditions with ≥2
replicates are pooled; disabled by `--no-combine`.

### `matrix/<sample>/<sample>.hic`

Optional Juicebox export (only with `--format both` and a working
`tools/juicer_tools.jar` + Java). The `.pairs` are converted to juicer short
format and run through `juicer_tools pre`. Best-effort: any failure logs a
warning and is skipped without affecting the `.mcool` outputs.

### `matrix_QC/p_curve/<res>/`

Contact-distance decay P(s) QC, computed per resolution in
`--p-curve-resolutions` (default `5000,10000,50000,100000`):

- `<sample>.expected_cis.<res>.tsv` — `cooltools expected-cis` table (smoothed,
  ICE-balanced `weight`, main-chromosome view).
- `<sample>.P_curve.<res>.png` (+ `.pdf`) — per-sample log-log P(s) decay with a
  log-log slope sub-panel.
- `P_curve_of_all.{pdf,png}` — multi-sample P(s)+slope overlay (only when ≥2
  samples have a usable P(s) table).

### `matrix_QC/scc/<res>/`

HiCRep stratum-adjusted correlation (SCC) replicate reproducibility, per
resolution in `--scc-resolutions` (only when ≥2 replicates exist):

- `scc_values.tsv` — symmetric pairwise SCC matrix across replicates.
- `scc_heatmap.{pdf,png}` — clustered SCC heatmap.
- `pairs/scc_<sample1>_vs_<sample2>.txt` — raw per-pair `hicrep` output.

### `matrix_QC/pca/<res>/`

Sample PCA on flattened balanced cis contacts (scHiCluster-style embedding),
per `--scc-resolutions`; only built when ≥3 replicates exist:

- `pca_coords.tsv` — PC1..PC5 coordinates per sample.
- `sample_pca.{pdf,png}` — PC1/PC2 scatter coloured by condition.

### `matrix_visualization/<viz_res>/`

Whole-genome ICE-balanced contact map per matrix (HapHiC/GenAsmClaw drawing
style: white→red log-scaled heatmap with chromosome-boundary gridlines),
rendered at `--viz-resolution` (default 500 kb):

- `<sample>.{pdf,png}` — one figure per replicate and per pooled condition.

### `reproducibility/commands.sh`

Single-line `python bulkhic-matrix.py …` rerun command with `--base-binsize`,
`--resolutions`, `--threads`, `--format`, and (when set) `--p-curve-resolutions`,
`--scc-resolutions`, and `--no-combine` expanded.

### `reproducibility/requirements.txt`

Pinned versions of the core tools used: `cooler`, `cooltools`, `numpy`,
`pandas`, `matplotlib`.
