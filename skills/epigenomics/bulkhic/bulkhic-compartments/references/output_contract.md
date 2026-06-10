# Output Contract — bulkhic-compartments

## Output Structure

All skill outputs land under the skill's `--output` (`--wd`) directory. The
compartment analysis is run **per resolution** (default `10000,25000,50000,100000`
bp) and **per sample**, so the compartment / saddle products are nested under
a `<res>` resolution subdir, and most filenames carry the resolution in the
stem. `<sample>` is the sample name carried forward from the Step-3 matrix
result; `<res>` is the bin size in bp (e.g. `100000`).

Compartment-track files (view / expected-cis / GC / eigenvectors / A/B BED)
are written under `compartments/<res>/`; saddle products (dump, heatmap,
strength) under `saddle_plots/<res>/`; the cross-sample compartment PCA under
`compartment_pca/<res>/`.

```
<output>/                                              # the --output / --wd directory
├── README.md                                          # orientation note
├── report.md                                          # markdown summary + per-sample table
├── result.json                                        # structured envelope (chained from Step-3 matrix)
├── bulkhic-compartments.log                           # full run log
├── compartments/<res>/                                # compartment tracks, per resolution
│   ├── view.<res>.bed                                 # main-chromosome viewframe (shared across samples)
│   ├── gc.<res>.tsv                                   # per-bin GC phasing track (shared across samples)
│   ├── <sample>.expected_cis.<res>.tsv               # cooltools expected-cis (per sample)
│   ├── <sample>.eigs.<res>.cis.vecs.tsv              # E1 eigenvector(s), GC-phased (+ = A, − = B)
│   ├── <sample>.eigs.<res>.cis.lam.txt              # eigenvalues
│   └── <sample>.AB.<res>.bed                          # A/B compartment calls (BED4, E1 sign)
├── saddle_plots/<res>/                                # compartment-strength products, per resolution
│   ├── <sample>.saddle.<res>.saddledump.npz         # cooltools saddle dump (saddledata matrix)
│   ├── <sample>.saddle.<res>.png                      # saddle obs/exp heatmap
│   ├── <sample>.strength.<res>.tsv                    # AA / BB / AB / strength table
│   └── saddle_strength_all.{png,pdf}                  # ≥2-sample overlay (conditions only)
├── compartment_pca/<res>/                             # dcHiC-style sample PCA, per resolution
│   ├── compartment_pca.{png,pdf}                      # PC1/PC2 scatter on quantile-normalized E1
│   └── compartment_pca_coords.tsv                     # per-sample PC coordinates
└── reproducibility/
    ├── commands.sh                                    # exact rerun invocation
    └── requirements.txt                               # pinned tool list
```

## File Contents

### `report.md`

Markdown summary headed by skill name, version, and the resolution list. The
body is a per-(sample × resolution) table with columns: `Sample`,
`Resolution`, `E1 track` (✓/—), `A/B BED` (✓/—), `Saddle` (✓/—), and
`Strength` (the `(AA·BB)/AB²` scalar, or `—`). Closes with the OmicsClaw
research-tool disclaimer.

### `result.json`

Structured envelope chained from the Step-3 matrix `result.json`. Key fields:

```json
{
  "skill": "bulkhic-compartments",
  "version": "0.1.0",
  "log": "<output>/bulkhic-compartments.log",
  "params": {
    "resolutions":      [10000, 25000, 50000, 100000],
    "n_eigs":           1,
    "threads":          8,
    "comparison_figs":  { "<res>": "<output>/saddle_plots/<res>/saddle_strength_all.{png,pdf}" },
    "compartment_pca":  { "<res>": { "png": "...", "coords": "...", "var": [..], "n_bins": .. } }
  },
  "compartments": [
    {
      "sample":       "<sample>",
      "resolution":   100000,
      "is_combined":  false,
      "eigs_vecs":    "<output>/compartments/<res>/<sample>.eigs.<res>.cis.vecs.tsv",
      "eigs_lam":     "...cis.lam.txt | null",
      "ab_bed":       "<output>/compartments/<res>/<sample>.AB.<res>.bed | null",
      "saddle_npz":   "<output>/saddle_plots/<res>/<sample>.saddle.<res>.saddledump.npz | null",
      "saddle_png":   "...saddle.<res>.png | null",
      "gc_track":     "<output>/compartments/<res>/gc.<res>.tsv | null",
      "view_bed":     "<output>/compartments/<res>/view.<res>.bed | null",
      "expected_tsv": "<output>/compartments/<res>/<sample>.expected_cis.<res>.tsv | null",
      "strength_tsv": "...strength.<res>.tsv | null",
      "strength":     1.234,
      "AA":           1.5, "BB": 1.4, "AB": 1.0
    }
  ],
  "genome_files": { /* carried from Step-3 matrix (incl. fasta) */ },
  "sample_sheet": { /* carried forward */ },
  "prev_result":  "<absolute path to Step-3 matrix result.json>"
}
```

One element of `compartments[]` is written per (sample × resolution); any
product that failed/was skipped is `null`.

### `compartments/<res>/view.<res>.bed`

Main-chromosome viewframe (BED, no header: `chrom`, `start`, `end`, `name`) of
all chromosomes ≥ `max(10·res, 1 Mb)`. Drops the small unplaced scaffolds that
otherwise corrupt expected-cis / eigs-cis / saddle. **Shared across samples** at
a given resolution (genome-level, sample-independent).

### `compartments/<res>/gc.<res>.tsv`

Per-bin GC-content phasing track (`chrom`, `start`, `end`, `GC`) computed with
`bioframe.frac_gc` over the cooler bins, restricted to the view. Used to phase
the E1 sign so that **+ = A (GC-rich / active)** and **− = B**. **Shared across
samples** at a given resolution.

### `compartments/<res>/<sample>.expected_cis.<res>.tsv`

`cooltools expected-cis` output (per-diagonal expected contact frequency over
the main-chromosome view); required input to the saddle step.

### `compartments/<res>/<sample>.eigs.<res>.cis.vecs.tsv`

`cooltools eigs-cis` eigenvectors, one row per bin (`chrom`, `start`, `end`, …,
`E1`[, `E2`…]). `E1` is the GC-phased compartment score. The companion
`<sample>.eigs.<res>.cis.lam.txt` holds the eigenvalues. Re-running reuses an
existing non-empty `.cis.vecs.tsv` as a checkpoint (delete the `.eigs.*` files
to force recomputation).

### `compartments/<res>/<sample>.AB.<res>.bed`

A/B compartment calls as BED4 (`chrom`, `start`, `end`, `compartment`) derived
by binarising `E1`: `A` where `E1 > 0`, `B` where `E1 < 0` (NaN bins dropped).

### `saddle_plots/<res>/<sample>.saddle.<res>.saddledump.npz`

`cooltools saddle` dump (`--qrange 0.025 0.975 --n-bins 38`). The `saddledata`
array is the mean observed/expected per E1-quantile pair; consumed downstream to
compute strength and render the heatmap.

### `saddle_plots/<res>/<sample>.saddle.<res>.png`

Saddle observed/expected heatmap (square, log-diverging colormap about 1, E1
quantile B→A on both axes), titled with the sample, resolution, and strength.

### `saddle_plots/<res>/<sample>.strength.<res>.tsv`

One-row table `AA`, `BB`, `AB`, `strength`, where the corners of the flanking-
trimmed saddle matrix give AA (active-active), BB (inactive-inactive), AB
(active-inactive) and `strength = (AA·BB)/AB²`.

### `saddle_plots/<res>/saddle_strength_all.{png,pdf}`

Cross-sample overlay produced only when ≥2 samples are present (conditions /
combined samples preferred, falling back to all samples). Left panel:
`(AA+BB)/(AB+BA)` vs extent (quantile bins from the corner), one step curve per
sample; right panel: a strength bar per sample. Colours come from the shared
sample palette.

### `compartment_pca/<res>/compartment_pca.{png,pdf}` + `compartment_pca_coords.tsv`

dcHiC-style cross-sample PCA on the GC-phased E1 compartment scores
(individual replicates only; requires ≥3 samples). The (bins × samples) E1
matrix is quantile-normalized across samples, then PCA'd via numpy SVD. The
figure is a PC1/PC2 scatter coloured by condition (PC variance % in the axis
labels); `compartment_pca_coords.tsv` holds up to 5 per-sample PC coordinates.

### `reproducibility/commands.sh`

Single-line `python bulkhic-compartments.py …` rerun with `--prev-result`,
`--wd`, `--resolutions`, and `--threads` expanded. `requirements.txt` pins the
tool stack (`cooler`, `cooltools`, `bioframe`, `numpy`, `pandas`, `matplotlib`).
