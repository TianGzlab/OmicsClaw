# Output Contract — bulkhic-pileup

## Output Structure

All outputs land under the skill's `--output` (a.k.a. `--wd`) directory.
Each feature **kind** gets its own subdirectory, and each sample gets its
own subdirectory beneath that, so loop-APA and boundary/TAD pileups never
clash on the per-sample `<sample>.pileup.<res>.*` filenames.

`<kind>` = pileup geometry: `loops` (off-diagonal APA), `tads`
(on-diagonal, size-rescaled 99×99), or `boundaries`/custom (on-diagonal).
`<sample>` = sample name carried from the Step-3 matrix result.
`<res>` = pileup bin size in bp (e.g. `10000`).

```
<output>/                                        # the --output / --wd directory
├── README.md                                    # orientation note
├── report.md                                    # markdown summary table
├── result.json                                  # structured envelope (chained from Step 3 matrix)
├── bulkhic-pileup.log                           # full run log
├── <kind>/                                       # one dir per feature kind piled up
│   ├── <sample>/
│   │   ├── <sample>.pileup.<res>.clpy           # coolpup.py aggregate O/E matrix (checkpoint)
│   │   ├── <sample>.pileup.<res>.png            # aggregate heatmap (raster)
│   │   ├── <sample>.pileup.<res>.pdf            # aggregate heatmap (vector, publication)
│   │   ├── <sample>.expected_cis.<res>.tsv      # cooltools expected-cis (intermediate)
│   │   └── <sample>.loops6.<res>.bedpe          # 6-col BEDPE for coolpup (loops kind only)
│   └── pileup_<kind>_all.{png,pdf}             # ≥2-sample side-by-side panel (raster + vector)
└── reproducibility/
    ├── commands.sh                              # exact rerun invocation
    └── requirements.txt                         # pinned tool list
```

When no features are available to aggregate (no `--features` and no sibling
loop/boundary calls), the run degrades gracefully: only `README.md`,
`report.md`, `result.json`, `bulkhic-pileup.log`, and `reproducibility/`
are written, with an empty `pileup[]` array in `result.json`.

## File Contents

### `report.md`

Markdown summary. Header lists the skill/version, the flank (bp), and the
feature kinds piled up, followed by one table row per (sample × feature kind):

| Column | Meaning |
|---|---|
| `Sample` | sample name |
| `Feature` | `<kind>` (loops / tads / boundaries / custom) |
| `Format` | features format (`bedpe` or `bed`) |
| `Res (bp)` | pileup bin size |
| `Pileup` | `✓` if the aggregate matrix was produced, else `—` |
| `Center enrichment` | mean O/E over the central 3×3 of the heatmap (`—` if not computed) |

Ends with the standard OmicsClaw research-tool disclaimer.

### `result.json`

```json
{
  "skill": "bulkhic-pileup",
  "version": "0.1.0",
  "log": "<output>/bulkhic-pileup.log",
  "params": {
    "resolution":     null,
    "flank":          100000,
    "threads":        8,
    "feature_kinds":  ["<kind>"],
    "comparison_figs": { "<kind>": "<output>/<kind>/pileup_<kind>_all.<png|pdf>" }
  },
  "pileup": [
    {
      "sample":            "<sample>",
      "kind":              "<kind>",
      "resolution":        10000,
      "features":          "<path to BEDPE/BED features>",
      "features_format":   "bedpe",
      "pileup_npz":        "<output>/<kind>/<sample>/<sample>.pileup.<res>.clpy",
      "pileup_png":        "<output>/<kind>/<sample>/<sample>.pileup.<res>.png",
      "center_enrichment": 1.87
    }
  ],
  "genome_files": { /* carried forward from Step 3 */ },
  "sample_sheet": { /* carried forward from Step 3 */ },
  "prev_result":  "<absolute path to Step 3 matrix result.json>"
}
```

- `comparison_figs` is only present when ≥2 samples were piled up for a kind.
- `pileup_npz` holds the `.clpy` aggregate-matrix path (the JSON key is named
  `npz` for cross-skill consistency; the on-disk file is a coolpup `.clpy`).
- `pileup_png` / `center_enrichment` are `null` when plotting was skipped or
  the matrix was empty.

### `<kind>/<sample>/<sample>.pileup.<res>.clpy`

The coolpup.py aggregate observed/expected matrix — the stacked, averaged
snippet around every feature. This is the **checkpoint**: if it already
exists, the run skips re-calling coolpup.py and just re-plots from it.

- `loops` (BEDPE): off-diagonal APA, square matrix spanning `±flank`.
- `tads` (BED): on-diagonal, size-rescaled to 99×99 (`--rescale_size 99`).
- `boundaries`/custom (BED): on-diagonal, local, spanning `±flank`.

Loaded back via `coolpuppy.lib.io.load_pileup_df` for plotting and
central-enrichment scoring.

### `<kind>/<sample>/<sample>.pileup.<res>.{png,pdf}`

Aggregate heatmap of the `.clpy` matrix, rendered with a diverging colormap
(`coolwarm`) on a `TwoSlopeNorm` centred at observed/expected = 1. Annotated
with the central-enrichment score and feature count (`n=...`). Both a raster
`.png` and a vector `.pdf` are written by `_lib/viz.save_figure`.

### `<kind>/<sample>/<sample>.expected_cis.<res>.tsv`

Per-sample cis expected signal from `cooltools expected-cis`, computed at the
pileup resolution and passed to coolpup.py via `--expected`. If this step
fails, coolpup falls back to shifted-control normalisation and no `.tsv` is
kept.

### `<kind>/<sample>/<sample>.loops6.<res>.bedpe`

A cleaned 6-column (double-BED) BEDPE derived from the input loops, written
only for the `loops`/BEDPE geometry — coolpup.py wants exactly 6 columns,
while the upstream loops BEDPE carries extra name/FDR/scale columns.

### `<kind>/pileup_<kind>_all.{png,pdf}`

Side-by-side comparison panel of every sample's aggregate heatmap for one
feature kind, drawn only when ≥2 samples were piled up. All panels share a
single colour scale (`TwoSlopeNorm` over the pooled 1st–99th percentiles) so
enrichment is comparable across samples. Written by `plot_pileup_all`.

### `reproducibility/commands.sh`

Single-line `python <script> --prev-result ... --wd ... --flank ...`
invocation (with `--resolution` appended only when the user pinned one).
Re-running it reproduces the pileup from the same matrix result.

### `reproducibility/requirements.txt`

Pinned tool list for the run: `cooler`, `cooltools`, `numpy`, `pandas`,
`matplotlib`.
