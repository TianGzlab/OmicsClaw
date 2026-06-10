# Output Contract — bulkchip-enrichment

## Output Structure

All outputs land directly under the skill's `--output` / `--wd` directory
(the OmicsClaw per-skill layout — no nested step subdir). The skill consumes
the target-gene set from an upstream `bulkchip-peak-annotation` result.json and
runs GO / KEGG over-representation (gseapy / Enrichr), emitting one results CSV
plus one dotplot per requested gene-set library.

`<library>` = the filesystem-safe slug of a requested gene-set library name
(e.g. `GO_Biological_Process`, `KEGG`) — one CSV + one dotplot per library.

```
<output>/                              # the --output / --wd directory
├── README.md                         # orientation note
├── report.md                         # markdown summary (per-library term table)
├── result.json                       # structured envelope (chained from bulkchip-peak-annotation)
├── bulkchip-enrichment.log           # full run log (narrative + every tool's stdout/stderr)
├── enrichment/                       # per-library GO/KEGG outputs
│   ├── <library>.csv                 # term, overlap, adjusted_p_value, p_value, combined_score, genes
│   ├── <library>_dotplot.png         # top-terms dotplot (only when ≥1 significant term)
│   └── _enrichr_<library>/           # raw gseapy.enrichr working dir per library
├── enrichment_summary.csv            # one row per gene-set library
└── reproducibility/
    ├── commands.sh                   # single-line rerun invocation
    └── requirements.txt              # pinned Python deps for the run
```

Graceful degradation: a missing `gseapy`, an Enrichr network failure, or an
empty target-gene set yields **header-only** `<library>.csv` files
(`n_significant_terms = 0`) and no dotplot — the skill never crashes.

## File Contents

### `result.json`

Structured envelope written by `write_report` (`bulkchip-enrichment.py`):

```json
{
  "skill": "bulkchip-enrichment",
  "version": "0.1.0",
  "log": "<output>/bulkchip-enrichment.log",
  "params": {
    "gene_sets": ["GO_Biological_Process", "KEGG"],
    "genome":    "<genome build, e.g. sacCer3>",
    "organism":  "<human|mouse|yeast|fly|worm|fish>",
    "gmt":       "<offline .gmt path or null>",
    "padj":      0.05,
    "threads":   4
  },
  "enrichment": {
    "n_target_genes": "...",
    "gene_source":    "target_genes | annotated_tsv",
    "peak_subset":    "...",
    "organism":       "<organism>",
    "summary_csv":    "<output>/enrichment_summary.csv",
    "libraries": [
      {
        "gene_set":    "GO_Biological_Process",
        "results_csv": "<output>/enrichment/<library>.csv",
        "dotplot_png": "<output>/enrichment/<library>_dotplot.png | null",
        "n_terms":     "..."
      }
    ]
  },
  "prev_result": "<absolute path to bulkchip-peak-annotation result.json>"
}
```

- `organism` is auto-derived from the upstream genome build (e.g. `sacCer3 →
  yeast`) unless `--organism` overrides it; unmapped builds default to `human`.
- `gene_source` records whether genes came from `annotation.target_genes` or
  the fallback nearest-gene column of `annotation.annotated_tsv`.

### `enrichment/<library>.csv`

One row per Enrichr term for the library, sorted by ascending adjusted
p-value (written by `run_functional_enrichment` in `_lib/enrichment.py`).
When the library returns nothing (or gseapy/Enrichr is unavailable) this is a
**header-only** file.

| Column | Type | Meaning |
|---|---|---|
| `term` | str | gene-set / pathway term label (Enrichr `Term`) |
| `overlap` | str | `k/K` — query genes in term over term size |
| `adjusted_p_value` | float | Benjamini–Hochberg adjusted p-value (sort key; cutoff = `--padj`) |
| `p_value` | float | raw Fisher-exact p-value |
| `combined_score` | float | Enrichr combined score |
| `genes` | str | semicolon-separated overlapping query genes |

### `enrichment/<library>_dotplot.png`

Top-terms dotplot (up to 15 most-significant terms) rendered by `_make_dotplot`
in `_lib/enrichment.py`: y-axis = term labels, x-axis and colour =
`-log10(adjusted p-value)`, marker size scales with the overlap gene count.
Written **only** when the library has ≥1 term at `adjusted_p_value ≤ --padj`;
absent (and `dotplot_png = null` in `result.json`) otherwise.

### `enrichment/_enrichr_<library>/`

Per-library scratch directory passed to `gseapy.enrichr` as its `outdir`.
Holds gseapy's own raw Enrichr response artifacts; the curated, contract-shaped
output is the sibling `<library>.csv`.

### `enrichment_summary.csv`

One row per requested gene-set library (written by `write_enrichment_summary`
in `_lib/enrichment.py`):

| Column | Type | Meaning |
|---|---|---|
| `gene_set` | str | gene-set library name as requested |
| `n_significant_terms` | int | terms at `adjusted_p_value ≤ --padj` |
| `results_csv` | str | path to the library's `<library>.csv` |
| `dotplot_png` | str | path to the dotplot PNG (empty when none was drawn) |

### `report.md`

Markdown summary: a header block (target-gene count + source + peak subset,
organism, gene-set libraries, adjusted-p cutoff, optional offline GMT) and a
"Significant terms per library" table (library, significant-term count, results
CSV, dotplot). When the total is zero it explains the likely causes (small /
intergenic gene set, organism–library mismatch, or offline gseapy/Enrichr) and
points to a "Next Steps" reference to `bulkchip-motif-enrichment`.

### `reproducibility/commands.sh`

Single-line `python bulkchip-enrichment.py ...` rerun invocation with
`--prev-result`, `--wd`, `--gene-sets`, `--organism`, `--padj`, `--threads`
(and `--gmt` when an offline library was used) expanded.

### `reproducibility/requirements.txt`

Pinned Python dependencies for the run (`pandas`, `numpy`, `gseapy`,
`matplotlib`), written by the common `write_repro_requirements` helper.
