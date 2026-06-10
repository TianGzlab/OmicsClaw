# Output Contract — bulkhic-tads

## Output Structure

All skill outputs land directly under the skill's `--output` (`--wd`)
directory — the OmicsClaw per-skill layout. TAD calling is run across
every requested resolution (`--resolutions`, default `5000,10000,25000,50000`),
and the per-resolution artifacts are written into resolution-keyed
subdirectories so the parallel resolutions never collide.

`<res>` = a bin size in bp (e.g. `25000`).
`<sample>` = a matrix sample name carried from Step 3 (`bulkhic-matrix`);
this includes both per-replicate samples and the combined per-`<condition>`
matrices (`is_combined`).
`<condition>` = a biological condition from the sample sheet (combined matrices).

```
<output>/                                          # the --output / --wd directory
├── README.md                                      # orientation note
├── report.md                                      # markdown summary table
├── result.json                                    # structured envelope (chained from Step 3)
├── bulkhic-tads.log                               # full run log (attach_run_log)
├── tads/<res>/                                    # per-resolution insulation + TAD calls
│   ├── <sample>.insulation.<res>.tsv             # cooltools per-bin insulation table
│   ├── <sample>.boundaries.<res>.bed             # boundary bins (BED3/BED4 + strength)
│   ├── <sample>.TADs.<res>.bed                   # TAD domains (small TADs merged)
│   ├── view.<res>.bed                            # cooltools viewframe (assembled chroms)
│   └── tad_size_distribution.{png,pdf}          # TAD size violins, conditions only
├── tad_pca/<res>/                                 # HiC-bench-style TAD-profile PCA
│   ├── tad_pca.{png,pdf}                         # PC1/PC2 sample scatter (replicates)
│   └── tad_pca_coords.tsv                        # PCA coordinates (PC1..PC5)
├── tad_pileup/<res>/                              # coolpup.py on-diagonal TAD pileup
│   ├── <sample>.expected_cis.<res>.tsv          # cis expected (cooltools), per sample
│   ├── <sample>.pileup.<res>.clpy               # aggregate O/E matrix (coolpuppy)
│   ├── <sample>.pileup.<res>.{png,pdf}          # per-sample rescaled TAD pileup
│   └── pileup_tads_all.{png,pdf}                 # ≥2-sample side-by-side comparison
└── reproducibility/
    ├── commands.sh                                # exact rerun invocation
    └── requirements.txt                           # pinned tool list
```

## File Contents

### `report.md`

Markdown summary headed *Hi-C Insulation / TAD Report* with the skill /
version banner, the resolution list, the diamond-window multiple, and one
table row per `(sample, resolution)` carrying `Boundaries`, `TADs`, and a
tick for whether the insulation track was produced. Ends with the standard
research-tool disclaimer.

### `result.json`

Structured envelope written by `write_report`:

```json
{
  "skill": "bulkhic-tads",
  "version": "0.1.0",
  "log": "<output>/bulkhic-tads.log",
  "params": {
    "resolutions":      [5000, 10000, 25000, 50000],
    "window_multiple":  8,
    "windows_override": null,
    "threshold":        "Li",
    "threads":          8,
    "tad_size_figs":    { "<res>": "<output>/tads/<res>/tad_size_distribution.{png,pdf}" },
    "tad_pca":          { "<res>": { "png": "...", "coords": "...", "var": [..], "n_bins": ... } },
    "tad_pileup":       { "<res>": "<output>/tad_pileup/<res>/pileup_tads_all.{png,pdf}" }
  },
  "insulation": [
    {
      "sample":         "<sample>",
      "resolution":     25000,
      "is_combined":    false,
      "windows":        [200000],
      "insulation_tsv": "<output>/tads/<res>/<sample>.insulation.<res>.tsv",
      "primary_window": 200000,
      "boundaries_bed": "<output>/tads/<res>/<sample>.boundaries.<res>.bed",
      "n_boundaries":   ...,
      "tads_bed":       "<output>/tads/<res>/<sample>.TADs.<res>.bed",
      "n_tads":         ...
    }
  ],
  "genome_files": { /* carried from Step 3 */ },
  "sample_sheet": { /* carried from Step 3 */ },
  "prev_result":  "<absolute path to bulkhic-matrix result.json>"
}
```

One `insulation[]` entry is emitted per `(sample, resolution)` pair.

### `tads/<res>/<sample>.insulation.<res>.tsv`

Raw `cooltools insulation` output for one sample at one resolution
(`run_insulation` / `_lib/insulation.py`). One row per genomic bin with
`chrom`, `start`, `end`, and, for the diamond window `<w>` (= `--window-multiple`
× `<res>`, default 8×), `log2_insulation_score_<w>`, `is_boundary_<w>`, and
`boundary_strength_<w>`. This TSV is the checkpoint: if it exists and is
non-empty, the cooltools call is skipped and the BEDs are re-derived from it.

### `tads/<res>/<sample>.boundaries.<res>.bed`

Boundary bins extracted from the insulation TSV (`_boundaries_bed`): the rows
flagged `is_boundary_<w> == True` at the primary window, written as
`chrom start end [boundary_strength]` (BED3, plus the strength column when
present). No header.

### `tads/<res>/<sample>.TADs.<res>.bed`

TAD domains (`_extract_tads`, BED3, no header). Boundaries are turned into
domains spanning consecutive boundary midpoints (and chromosome ends); TADs
longer than 3 Mb are dropped, and TADs shorter than `primary_window // 2` are
merged into the neighbour across whichever flanking boundary is *weaker*
(ports the production `extract_TADs`, `merge_strategy="weaker_boundary"`).

### `tads/<res>/view.<res>.bed`

cooltools viewframe (`_make_view`): `chrom start end name` for the assembled
chromosomes large enough to hold the diamond window (floored at ≥1 Mb). Shared
by all samples at that resolution; restricting the view keeps small unplaced
scaffolds from crashing `insul_diamond`.

### `tads/<res>/tad_size_distribution.{png,pdf}`

Violin of `log10(TAD size in bp)` per condition
(`plot_tad_size_distribution` → `_lib/viz.violin_size`). Built from the
**combined / condition** matrices only (falls back to all samples if no
combined matrix exists); each x-label carries that condition's TAD count.
Emitted only when ≥2 TADs are available.

### `tad_pca/<res>/tad_pca.{png,pdf}` and `tad_pca_coords.tsv`

HiC-bench-style sample PCA on the TAD profile (`run_tad_pca`). Per-bin
`log2_insulation_score_<w>` is assembled into a bins × samples matrix over the
individual **replicates** (`is_combined == False`), quantile-normalized across
samples, then PCA-projected via numpy SVD.

- `tad_pca.{png,pdf}` — PC1/PC2 scatter, points coloured by condition and
  labelled by sample; axis labels carry the variance explained. Requires ≥3
  replicates (else skipped).
- `tad_pca_coords.tsv` — the projected coordinates, rows = samples, columns =
  `PC1`…`PC5` (up to 5 components).

### `tad_pileup/<res>/`

coolpup.py on-diagonal, size-normalized TAD pileup per sample
(`run_pileup` / `_lib/pileup.py`), run for samples with ≥1 called TAD.

- `<sample>.expected_cis.<res>.tsv` — cis expected signal from
  `cooltools expected-cis` (computed if not already present).
- `<sample>.pileup.<res>.clpy` — the aggregate observed/expected matrix
  emitted by coolpup.py (`--local --rescale --rescale_flank 1.0
  --rescale_size 99`). Also the per-sample checkpoint.
- `<sample>.pileup.<res>.{png,pdf}` — rescaled TAD heatmap (TAD start→end,
  O/E colour, central-enrichment annotation), via `_plot_pileup` →
  `_lib/viz.save_figure`.
- `pileup_tads_all.{png,pdf}` — side-by-side comparison panel across samples
  on a shared colour scale (`plot_pileup_all`); written only when ≥2 samples
  produced a pileup.

### `reproducibility/commands.sh`

Single-line `python skills/epigenomics/bulkhic/bulkhic-tads/bulkhic-tads.py …`
invocation with `--prev-result`, `--wd`, `--resolutions`, `--window-multiple`,
and `--threshold` expanded to the values actually used.

### `reproducibility/requirements.txt`

Pinned tool list for the run (`cooler`, `cooltools`, `numpy`, `pandas`),
written by the common `write_repro_requirements` helper.
