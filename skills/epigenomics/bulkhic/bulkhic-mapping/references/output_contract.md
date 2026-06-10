# Output Contract — bulkhic-mapping

## Output Structure

All run artifacts land under the skill's `--output` / `--wd` directory. The
deduplicated, pairix-indexed `.pairs` files are written one subdirectory per
sample under `pairs/<sample>/`. Reference files (FASTA + aligner index +
chrom.sizes) are written to `--ref-dir` (defaults to a sibling
`reference_<genome>/` of the working directory) and are **reused** across
samples and across runs, so they live outside the working tree.

`<sample>` = the sample name carried over from Step-1 preprocessing.
`<genome>` = the reference build (e.g. `hg38`, `mm10`).

```
<output>/                                       # the --wd / --output directory
├── README.md                                   # orientation note
├── report.md                                   # markdown summary (alignment + library QC)
├── result.json                                 # structured envelope (chained from Step 1)
├── mapping_summary.csv                         # per-sample pairtools library-QC table
├── reproducibility/
│   ├── commands.sh                             # exact rerun invocation
│   └── requirements.txt                        # pinned python deps (pandas, numpy)
└── pairs/<sample>/                             # one subdir per sample
    ├── <sample>.nodups.pairs.gz                # deduplicated, bgzipped, pairix-indexed pairs (deliverable)
    ├── <sample>.nodups.pairs.gz.px2            # pairix index (random access)
    ├── <sample>.dedup.stats                    # pairtools dedup --output-stats (QC source)
    └── <sample>.mapping.done                   # checkpoint sentinel (enables resume)

reference_<genome>/                             # the --ref-dir (built once, reused)
├── <genome>.fa                                 # reference FASTA (downloaded or pre-staged)
├── <genome>.chrom.sizes                        # contig sizes (faidx-derived; for cooler/cooltools)
└── <aligner>_index/<genome>.*                  # bwa-mem2 (or bwa) index files
```

## File Contents

### `report.md`

Markdown summary with:

1. **Alignment + pairs** — sample count, aligner, genome.
2. **Library QC (pairtools)** — one row per sample with valid-pair count,
   valid %, dup %, cis %, cis/trans ratio, and cis-long %, each annotated with
   its 4DN/pairtools quality tier (`preferred` / `acceptable` / `low` / `high`).
3. **QC thresholds (4DN / pairtools)** — the reference-threshold table from
   `_lib/bulkhic_qc_criteria.thresholds_markdown()`.
4. **Next Steps** — pointer to `bulkhic-matrix` (Step 3).

### `result.json`

Structured envelope chained from the Step-1 preprocessing `result.json`.

```json
{
  "skill":           "bulkhic-mapping",
  "version":         "0.1.0",
  "log":             "<output>/bulkhic-mapping.log",
  "steps_completed": ["...", "mapping"],
  "steps_pending":   ["..."],
  "params": {
    "aligner":  "bwa-mem2",
    "threads":  16,
    "min_mapq": 30,
    "ref_dir":  "<absolute path to reference_<genome>>"
  },
  "mapping": [
    {
      "sample":          "<sample>",
      "pairs":           "<output>/pairs/<sample>/<sample>.nodups.pairs.gz",
      "aligner":         "bwa-mem2",
      "n_total":         ...,
      "n_valid_pairs":   ...,
      "valid_frac":      ...,
      "dup_frac":        ...,
      "cis_frac":        ...,
      "cis_trans_ratio": ...,
      "cis_long_frac":   ...,
      "stats_file":      "<output>/pairs/<sample>/<sample>.dedup.stats"
    }
  ],
  "hic_qc_thresholds": { /* HIC_QC_THRESHOLDS verbatim */ },
  "genome_files": {
    "genome":         "<genome>",
    "fasta":          "<ref-dir>/<genome>.fa | null",
    "chrom_sizes":    "<ref-dir>/<genome>.chrom.sizes | null",
    "bwa_mem2_index": "<ref-dir>/bwa-mem2_index/<genome> | null",
    "bwa_index":      "<ref-dir>/bwa_index/<genome> | null"
  },
  "sample_sheet": { /* carried forward from Step 1 */ },
  "prev_result":  "<absolute path to Step-1 result.json>"
}
```

### `mapping_summary.csv`

Per-sample pairtools library-QC table (one row per sample), written by
`_lib/mapping.write_mapping_summary`. Columns:

| Column | Type | Meaning |
|---|---|---|
| `sample` | str | sample name |
| `aligner` | str | `bwa-mem2` or `bwa` |
| `total_pairs` | int | total read pairs seen by pairtools (`total`) |
| `valid_pairs` | int | unique, deduplicated pairs (`total_nodups`) |
| `valid_frac` | float | `valid_pairs / total_pairs` |
| `valid_tier` | str | `preferred` / `acceptable` / `low` |
| `dup_frac` | float | PCR duplicate fraction among mapped pairs |
| `dup_tier` | str | `preferred` / `acceptable` / `high` (lower is better) |
| `cis_frac` | float | cis pairs / (cis + trans) |
| `cis_tier` | str | `preferred` / `acceptable` / `low` |
| `cis_trans_ratio` | float | cis / trans (signal-to-noise proxy) |
| `cis_trans_tier` | str | `preferred` / `acceptable` / `low` |
| `cis_long_frac` | float | cis pairs > 20 kb / all cis pairs (complexity metric) |
| `cis_long_tier` | str | `preferred` / `acceptable` / `low` |

### `pairs/<sample>/<sample>.nodups.pairs.gz`

The deliverable: bgzipped, pairix-indexed, deduplicated 4DN `.pairs` file
produced by `bwa-mem2 mem -SP5M | pairtools parse | pairtools sort` followed by
`pairtools dedup`. Both mates are mapped independently (`-SP5M`: no mate-rescue)
so chimeric Hi-C ligation molecules are not "rescued". Consumed directly by
`cooler cload` in Step 3 (`bulkhic-matrix`).

- `.px2` sidecar — the pairix index for random genomic access.
- The intermediate `<sample>.sorted.pairs.gz` is deleted after dedup; only the
  `nodups` file is kept.

### `pairs/<sample>/<sample>.dedup.stats`

The flat `key<TAB>value` stats file emitted by `pairtools dedup --output-stats`.
It is the single QC source parsed by `_lib/mapping.parse_pairtools_stats` to
derive every metric above (`total`, `total_mapped`, `total_dups`,
`total_nodups`, `cis`, `trans`, and the cumulative `cis_20kb+` long-range bin).

### `pairs/<sample>/<sample>.mapping.done`

Empty sentinel written after a sample completes. On rerun, if the sentinel, the
`nodups` pairs, and the stats file are all present, the alignment is skipped and
the QC is recomputed from the existing stats (checkpoint/resume).

### Reference files (`reference_<genome>/`)

Built once in `--ref-dir` (default: project-sibling `reference_<genome>/`) and
reused. A pre-staged local `<genome>.fa` is reused without re-downloading.

- `<genome>.fa` — reference FASTA (UCSC goldenPath download, or `--fasta-url`,
  or a pre-existing local copy).
- `<genome>.chrom.sizes` — contig name/length table derived **offline** from
  `samtools faidx` (never depends on a UCSC chrom.sizes download); required by
  cooler/cooltools downstream.
- `<aligner>_index/<genome>.*` — the bwa-mem2 (`.bwt.2bit.64`, ...) or bwa
  (`.amb`, ...) index files.

### `reproducibility/commands.sh`

Single-line `python bulkhic-mapping.py ...` rerun command with `--prev-result`,
`--wd`, `--aligner`, `--threads`, and (when set) `--ref-dir` expanded.

### `reproducibility/requirements.txt`

Pinned python dependencies for the run (`pandas`, `numpy`), written by the
common report helper.
