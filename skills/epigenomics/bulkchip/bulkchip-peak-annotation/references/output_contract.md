# Output Contract — bulkchip-peak-annotation

## Output Structure

All outputs land directly under the skill's `--wd` / `--output` directory.
The consensus subset is annotated into `annotation/`; when a reachable
bulkchip-DA result lets the default run also annotate the gained/lost peaks,
each DA subset gets its own parallel `annotation_<subset>/` tree
(`annotation_up/`, `annotation_down/`). An explicit `--peak-subset
up|down|condition` annotates only that one subset, still into `annotation/`.

`<subset>` ∈ {`up`, `down`} for the auto-annotated DA peak sets.

```
<output>/                                   # the --wd / --output directory
├── README.md                               # orientation note
├── report.md                               # multi-section markdown summary
├── result.json                             # structured envelope (chained from peak-calling / DA)
├── bulkchip-peak-annotation.log            # full run log (narrative + tool stdout/stderr)
├── annotation/                             # primary (consensus) subset
│   ├── annotated_peaks.tsv                 # per-peak feature category + nearest gene + TSS distance
│   ├── homer_annotated_full.tsv            # full HOMER annotatePeaks.pl output (HOMER path only)
│   ├── peak_annotation_summary.csv         # counts + fraction per feature category
│   ├── peak_annotation_pie.{png,pdf}       # feature-distribution donut
│   ├── peak_tss_distance.{png,pdf}         # distance-to-nearest-TSS histogram
│   └── tss_for_annotation.bed             # 1 bp TSS sites from the GTF (bedtools-fallback path only)
├── annotation_<subset>/                    # same layout, per auto-annotated DA subset (up / down)
│   └── ...
└── reproducibility/
    ├── commands.sh                         # single-line rerun invocation
    └── requirements.txt                    # pandas / numpy / matplotlib
```

## File Contents

### `report.md`

Multi-section markdown summary, one `## Peak→gene annotation — <subset>`
section per annotated subset (built by `_report_section`), each carrying:

- Genome / GTF used and the TSS window (bp) for target-gene calling.
- A **Feature distribution** table (Feature | Peaks | Fraction), sorted by
  count. When no HOMER genome / GTF is available the table degrades to a
  single "no feature annotation" row.
- The **target-gene** count (nearest-gene TSS ≤ window) plus a preview of the
  top 25 gene names.
- The basenames of the feature pie and TSS-distance plots for that subset.

A **Next Steps** section points to `bulkchip-enrichment` (GO/KEGG over the
consensus target genes) and `bulkchip-motif-enrichment`, followed by the
standard OmicsClaw research-tool disclaimer.

### `result.json`

```json
{
  "skill":   "bulkchip-peak-annotation",
  "version": "0.1.0",
  "log":     "<output>/bulkchip-peak-annotation.log",
  "params":  { "peak_subset": "consensus", "tss_window": 3000, "genome": "...",
               "gtf": "... | null", "de_result": "... | null",
               "consensus_only": false, "threads": 8 },
  "annotation": {                              // primary (consensus) — back-compat for enrichment
    "peak_subset":    "consensus",
    "dir":            "<output>/annotation",
    "annotated_tsv":  "<output>/annotation/annotated_peaks.tsv",
    "feature_counts": { "Promoter-TSS": 0, "Intron": 0, "Intergenic": 0 },
    "n_target_genes": 0,
    "target_genes":   [ "..." ],
    "pie_png":        "<output>/annotation/peak_annotation_pie.{png,pdf} | null",
    "tss_dist_png":   "<output>/annotation/peak_tss_distance.{png,pdf} | null",
    "genome":         "...",
    "tss_window":     3000
  },
  "annotations": [ /* one block per annotated subset (consensus, up, down) */ ],
  "prev_result": "<absolute path to peak-calling / DA result.json>"
}
```

`annotation` is the primary (consensus) block, surfaced at top level so
downstream `bulkchip-enrichment` keeps reading `annotation.target_genes`
unchanged. Every annotated subset (including consensus) also appears in the
`annotations` list. Block shape is built by `_annotation_block`.

### `annotation/annotated_peaks.tsv`

Per-peak feature + nearest-gene table; one row per peak, tab-separated, with a
header row. Column set depends on which annotation engine ran.

**HOMER path** (`_annotate_with_homer`, 8 columns):

| Column | Meaning |
|---|---|
| `peak_chr` | chromosome |
| `peak_start` | start coordinate |
| `peak_end` | end coordinate |
| `nearest_gene` | nearest gene name (HOMER `Gene Name`) |
| `distance` | distance to TSS (bp; signed as HOMER reports it) |
| `category` | simplified feature class — Promoter-TSS / TTS / 5'UTR / 3'UTR / Exon / Intron / Intergenic / Non-coding / Other |
| `detailed_annotation` | HOMER's raw annotation string |
| `gene_type` | HOMER gene biotype |

**bedtools-fallback path** (`_annotate_with_bedtools`, 6 columns) — same first
six columns, with `category` ∈ Promoter (<1 kb) / Proximal (1–5 kb) / Distal
(5–50 kb) / Intergenic (>50 kb), distance-based only.

**No-source fallback** (`_annotate_features_unavailable`) — peaks copied
through with `nearest_gene=.`, `distance=.`, `category=NA`; no feature counts
and no target genes are produced.

### `annotation/homer_annotated_full.tsv`

The complete, unparsed stdout of `annotatePeaks.pl` (all HOMER columns).
Written only on the HOMER path (`_annotate_with_homer`); absent for the
bedtools and no-source fallbacks.

### `annotation/peak_annotation_summary.csv`

Per-feature-category counts written by `_write_summary`:

| Column | Meaning |
|---|---|
| `category` | feature category label |
| `count` | number of peaks in that category |
| `fraction` | `count / max(n_peaks, 1)` |

### `annotation/peak_annotation_pie.{png,pdf}`

Donut chart of the feature-category distribution (`plot_annotation_pie`),
centre label = total peak count, legend = category + count + percent, colours
from the ChIPseeker Paired palette. Returns `None` (files absent) when there
are no feature counts.

### `annotation/peak_tss_distance.{png,pdf}`

Histogram of log10 peak distance to nearest TSS
(`plot_tss_distance_histogram`), with dashed reference lines at 1 kb / 5 kb /
50 kb. Returns `None` when there are no positive distances to plot.

### `annotation/tss_for_annotation.bed`

1 bp TSS positions extracted from the GTF (`chr`, `tss`, `tss+1`, gene name,
`.`, strand), written by `_extract_tss_from_gtf` and used as the `-b` input to
`bedtools closest`. Present only when the bedtools-fallback path runs (cached
and reused across runs). The intermediate sorted-peaks file `peaks_sorted.bed`
is created and deleted within the same path.

### `reproducibility/commands.sh`

Single-line `python bulkchip-peak-annotation.py ...` rerun invocation with the
resolved flags expanded (`--prev-result`, `--wd`, `--peak-subset`,
`--tss-window`, `--threads`, and conditionally `--genome`, `--gtf`,
`--de-result`, `--consensus-only`). `requirements.txt` alongside pins the
plotting/analysis deps (pandas, numpy, matplotlib).
