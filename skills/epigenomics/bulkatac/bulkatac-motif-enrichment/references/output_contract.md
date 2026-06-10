# Output Contract — bulkatac-motif-enrichment

## Output Structure

All skill outputs land directly under the skill's `--output` directory —
the OmicsClaw per-skill layout (no nested `motif_enrichment/` subdir).
HOMER native outputs live under per-peak-set subdirectories (`all_peaks/`,
`da_up/`, `da_down/`); custom summary + plots live at the root.

```
<output>/                                       # the --output directory
├── README.md                                   # orientation note
├── report.md                                   # markdown summary
├── result.json                                 # structured envelope (chained from Step 4)
├── top_motif_summary.tsv                       # cross-peak-set ranked motif table
├── all_peaks/                                  # full consensus vs GC-matched genomic background
│   ├── knownResults.txt                        # tab-separated known-motif enrichment table
│   ├── knownResults.html                       # interactive HOMER report (logos + p-values)
│   ├── homerResults.html                       # de novo motif HTML report
│   ├── homerMotifs.all.motifs                  # all de novo motifs in HOMER PWM format
│   ├── knownResults/                           # known-motif logo PNGs + per-motif info HTMLs
│   └── homerResults/                           # de novo motif logos + match-to-known reports
├── da_up/                                      # DA-up vs consensus background (-bg -chopify)
│   └── (same structure as all_peaks/)
├── da_down/                                    # DA-down vs consensus background (-bg -chopify)
│   └── (same structure as all_peaks/)
├── plots/
│   └── *.pdf / *.png                           # top motif bar charts per peak set (filename via {plot_name}.pdf)
└── reproducibility/
    ├── commands.sh
    └── requirements.txt
```

## File Contents

### `report.md`

Markdown summary with two repeating blocks (one per peak set) plus a
background-strategy footer:

1. **Per peak-set block** — peak count, HOMER success flag, top 10 known motifs table (`rank, motif, consensus, log10(p), %target, %background, enrichment`), top 5 de novo motifs table (`rank, consensus, log10(p), best-known-match`).
2. **Background strategy table** — explains why each peak set uses the background it does (genomic for `all_peaks`; consensus for `da_up`/`da_down`).

### `result.json`

```json
{
  "skill":   "bulkatac-motif-enrichment",
  "version": "0.1.0",
  "params": {
    "genome":        "<genome>",
    "genome_fasta":  "<absolute path | null>",
    "size":          200,
    "mask":          true,
    "denovo_length": "8,10,12",
    "n_motifs":      25,
    "threads":       16
  },
  "motif_enrichment": [
    {
      "peak_set":            "all_peaks",     // or "da_up", "da_down"
      "n_peaks":             ...,
      "homer_succeeded":     true,
      "n_known_motifs":      ...,
      "n_denovo_motifs":     ...,
      "top_known":           ["<motif_name>", ...],   // top 5
      "top_denovo":          ["<consensus>", ...],    // top 5
      "known_results_txt":   "<output>/<peak_set>/knownResults.txt",
      "known_results_html":  "<output>/<peak_set>/knownResults.html",
      "denovo_results_html": "<output>/<peak_set>/homerResults.html",
      "output_dir":          "<output>/<peak_set>/"
    }
  ],
  "summary_tsv":  "<output>/top_motif_summary.tsv",
  "prev_result":  "<absolute path to peak-calling result.json>",  // from chain walk
  "da_result":    "<absolute path to DA result.json>"
}
```

### `<peak_set>/knownResults.txt`

HOMER-native tab-separated table — one row per known motif tested.
Columns (HOMER docs at `homer.ucsd.edu/homer/ngs/peakMotifs.html`):

| Column | Meaning |
|---|---|
| `Motif Name` | TF / cofactor name + database source (e.g. `Fra1(bZIP)/BT549-Fra1-ChIP-Seq/Homer`) |
| `Consensus` | IUPAC consensus sequence of the PWM |
| `P-value` | hypergeometric p-value |
| `Log P-value` | natural log of P-value (more negative = more significant) |
| `q-value (Benjamini)` | BH-corrected significance |
| `# of Target Sequences with Motif` | foreground peak count carrying ≥ 1 motif occurrence |
| `% of Target Sequences with Motif` | as a fraction of foreground peaks |
| `# of Background Sequences with Motif` | background count |
| `% of Background Sequences with Motif` | fraction of background |

`% Target / % Background` is the enrichment ratio reported in
`report.md`.

### `<peak_set>/knownResults.html`

HOMER's interactive HTML report — sortable known-motif table with motif
logo PNG inline and `% target` / `% background` bar visualisations.
Open in a browser; no external server required.

### `<peak_set>/homerResults.html`

HOMER's interactive HTML report for *de novo* motifs — discovered PWMs
with logos, best-match-to-known TFs, and per-motif p-values. Each row
links to a per-motif HTML detail page in `homerResults/`.

### `<peak_set>/homerMotifs.all.motifs`

All de novo motifs concatenated in HOMER's `.motifs` PWM format.
Re-usable as `findMotifsGenome.pl ... -mknown <this_file>` to scan
other peak sets with this same de novo collection.

### `<peak_set>/knownResults/`

Per-known-motif assets emitted by HOMER itself: logo PNGs (HOMER-native
`motifN.logo.*` naming) and per-motif info HTML pages.

### `<peak_set>/homerResults/`

Per-de-novo-motif assets: logo PNGs, match-to-known reports, and the
per-motif `.motif` files (HOMER PWM format) for downstream scanning.

### `top_motif_summary.tsv`

Cross-peak-set ranked motif table (written by
`_lib.motif_enrichment.write_motif_summary`). Useful as the single
file to read for "what TFs matter in this experiment?". Columns
include the peak set the motif came from, motif name / consensus,
p-value, and enrichment direction.

### `plots/*.pdf` and `plots/*.png`

Top-motif bar charts per peak set, rendered by
`_lib.motif_enrichment.plot_top_known_motifs` (`_lib/motif_enrichment.py:767`)
and `plot_top_denovo_motifs` (`_lib/motif_enrichment.py:833`). Filenames
are built at call time via a `{plot_name}.pdf` pattern with
`plot_name = f"top_known_motifs_{peak_set}"` (or `top_denovo_motifs_...`)
— see `_lib/motif_enrichment.py:827, 880`. Both PDF and PNG are
emitted per `_save_figure` (`_lib/motif_enrichment.py:763`).

### `reproducibility/commands.sh`

Single-line `python bulkatac-motif-enrichment.py ...` invocation with
resolved `--genome` / `--genome-fasta` and the HOMER parameter flags
expanded. Re-runs of `commands.sh` skip auto-detection and exactly
reproduce the per-peak-set output dirs.

### `reproducibility/requirements.txt`

Pip-style pins for the Python packages the script imported
(`matplotlib`, `numpy`, `pandas`). HOMER itself (a Perl tool) is NOT
pinned here — record its version separately with `findMotifsGenome.pl 2>&1 | head -1`.

### `NOTE_no_peaks.txt`

Sentinel file written when a peak set is empty (e.g. `da_up` has zero
peaks at the user's `--padj` / `--lfc` thresholds) so the HOMER output
dir isn't silently empty. Inspect `result.json["motif_enrichment"][i]["n_peaks"]`
to confirm before assuming a HOMER failure.
