# Output Contract — bulkhic-loops

## Output Structure

Mustache (scale-space loop detection) is run per sample on the balanced
`.mcool` from `bulkhic-matrix`, independently at **each** requested
resolution (default 5 kb + 10 kb). Each resolution's loops are written to
their own per-resolution subdir — there is **no cross-resolution merge**.
Two cross-sample analyses are layered on top per resolution: a
conditions-only loop-size distribution and a replicate union-loop PCA, plus
a coolpup.py loop APA pileup.

`<res>` = a resolution bin size in bp (e.g. `5000`, `10000`).
`<sample>` = a sample / condition name from the Step-3 sample sheet.
`<condition>` = the condition label a sample maps to (drives the size violin).

```
<output>/                                          # the --output / --wd directory
├── README.md                                      # orientation note
├── report.md                                      # markdown summary (per-sample × resolution loop counts)
├── result.json                                    # structured envelope (chained from bulkhic-matrix)
├── bulkhic-loops.log                              # full run log (attach_run_log)
├── loops/
│   └── <res>/                                     # one subdir per resolution
│       ├── <sample>.loops.<res>.bedpe             # Mustache loops, 6 cols + name/FDR/detection_scale
│       ├── <sample>.mustache.<res>.tsv            # raw Mustache TSV (pre-BEDPE conversion)
│       └── loop_size_distribution.{png,pdf}       # loop-size violin, conditions only (≥2 conditions)
├── loop_pca/
│   └── <res>/                                     # union-loop strength PCA (replicates, ≥3 samples)
│       ├── loop_pca.{png,pdf}                      # PC1/PC2 scatter coloured by condition
│       └── loop_pca_coords.tsv                     # per-sample PC scores (PC1..PC5)
├── loop_pileup/
│   └── <res>/                                     # coolpup.py loop APA (off-diagonal aggregate)
│       ├── <sample>.pileup.<res>.clpy             # coolpup observed/expected matrix
│       ├── <sample>.pileup.<res>.{png,pdf}        # per-sample APA heatmap + central enrichment
│       ├── <sample>.expected_cis.<res>.tsv        # cooltools expected-cis (when computed)
│       ├── <sample>.loops6.<res>.bedpe            # 6-column BEDPE coolpup.py consumes
│       └── pileup_loops_all.{png,pdf}             # ≥2-sample side-by-side APA comparison
└── reproducibility/
    ├── commands.sh                                # exact rerun invocation
    └── requirements.txt                           # pinned tool list
```

Subtrees are written only when their preconditions are met: the size violin
needs ≥2 conditions, the PCA needs ≥3 replicate samples with ≥3 union loops,
the per-sample pileup needs >0 loops, and `pileup_loops_all.{png,pdf}` needs
≥2 samples with a pileup at that resolution. An empty loop set is a valid
(not failed) result, so an empty `<sample>.loops.<res>.bedpe` may be written.

## File Contents

### `report.md`

Markdown summary headed *Hi-C Loops Report (Mustache)*. Carries the caller,
the resolution list, the Mustache p-threshold (`-pt`) and max distance
(`-d`), then a table of one row per sample with loop counts per resolution
and a `Total` column.

### `result.json`

```json
{
  "skill": "bulkhic-loops",
  "version": "0.2.0",
  "log": "<output>/bulkhic-loops.log",
  "params": {
    "resolutions":    [5000, 10000],
    "fdr":            0.01,
    "max_dist":       2000000,
    "threads":        8,
    "loop_size_figs": { "<res>": "<output>/loops/<res>/loop_size_distribution.{png,pdf}" },
    "loop_pca":       { "<res>": { "png": "...", "coords": "...", "var": [..], "n_union_loops": 0 } },
    "loop_pileup":    { "<res>": "<output>/loop_pileup/<res>/pileup_loops_all.{png,pdf}" }
  },
  "loops": [
    {
      "sample":         "<sample>",
      "resolutions":    [5000, 10000],
      "n_loops":        0,
      "loops_bedpe":    "<output>/loops/<res>/<sample>.loops.<res>.bedpe",
      "per_resolution": [
        { "resolution": 5000, "bedpe": "...", "n_loops": 0 }
      ]
    }
  ],
  "genome_files": "<carried from bulkhic-matrix>",
  "sample_sheet": "<carried from bulkhic-matrix>",
  "prev_result":  "<absolute path to bulkhic-matrix result.json>"
}
```

`loops_bedpe` is the **finest-resolution** BEDPE (smallest bin), the default
input for downstream pileup; `per_resolution[]` enumerates every resolution's
BEDPE + loop count.

### `loops/<res>/<sample>.loops.<res>.bedpe`

Mustache loop calls converted from the raw TSV (`_lib/loops._tsv_to_bedpe`).
Tab-separated, one row per loop, no header:

| Column | Meaning |
|---|---|
| 1 | anchor-1 chromosome (`BIN1_CHR`) |
| 2 | anchor-1 start |
| 3 | anchor-1 end |
| 4 | anchor-2 chromosome (`BIN2_CHROMOSOME`) |
| 5 | anchor-2 start |
| 6 | anchor-2 end |
| 7 | loop name `loop_<N>` |
| 8 | Mustache FDR |
| 9 | Mustache detection scale |

An empty file means Mustache ran successfully and called zero loops at that
resolution.

### `loops/<res>/<sample>.mustache.<res>.tsv`

The raw Mustache output for that sample/resolution, before BEDPE conversion.
Header columns: `BIN1_CHR BIN1_START BIN1_END BIN2_CHROMOSOME BIN2_START
BIN2_END FDR DETECTION_SCALE`. Retained for provenance.

### `loops/<res>/loop_size_distribution.{png,pdf}`

Violin of loop size (anchor separation, `log10` bp) with one violin per
**condition** (combined samples only); x-labels carry each condition's loop
count. Emitted only when ≥2 size observations across conditions are
available. Written by `_lib/loops.plot_loop_size_distribution` via
`_lib/viz.violin_size` (pdf + png).

### `loop_pca/<res>/loop_pca.{png,pdf}` + `loop_pca_coords.tsv`

Sample PCA on loop **contact strength** over the union loop set (replicates
only, needs ≥3 samples and ≥3 union loops). The union of all samples'
intra-chromosomal loops is scored by each sample's balanced contact at the
loop pixel, quantile-normalised + per-loop mean-centred, then SVD'd.

- `loop_pca.{png,pdf}` — PC1/PC2 scatter, points coloured by condition and
  annotated with sample names; axis labels carry the variance explained.
- `loop_pca_coords.tsv` — tab-separated PC scores (up to PC1..PC5), indexed
  by sample name (`_lib/loops.run_loop_pca`).

### `loop_pileup/<res>/`

coolpup.py loop APA (off-diagonal aggregate peak analysis), one set per
resolution. Per sample with >0 loops:

- `<sample>.pileup.<res>.clpy` — coolpup observed/expected aggregate matrix.
- `<sample>.pileup.<res>.{png,pdf}` — APA heatmap (`coolwarm`, diverging norm
  centred on O/E = 1) with the central 3×3 enrichment and feature count
  annotated.
- `<sample>.expected_cis.<res>.tsv` — cooltools `expected-cis` table, computed
  on demand to normalise the pileup (absent if expected-cis failed, in which
  case shifted controls are used).
- `<sample>.loops6.<res>.bedpe` — intermediate 6-column double-BED that
  coolpup.py consumes (our loops BEDPE carries extra name/FDR/scale columns).
- `pileup_loops_all.{png,pdf}` — ≥2-sample side-by-side APA panel on a shared
  colour scale (`_lib/pileup.plot_pileup_all`).

### `reproducibility/commands.sh`

Single-line `python …/bulkhic-loops.py` invocation with `--prev-result`,
`--wd`, `--resolutions`, `--fdr`, and `--max-dist` expanded.

### `reproducibility/requirements.txt`

Pinned tool list for the run: `mustache-hic`, `cooler`, `numpy`, `pandas`
(plus coolpup.py / cooltools from the bulkhic env for the pileup step).
