# Output Contract — bulkhic-preprocessing

> Status: implemented.

Bulk Hi-C **Step 1**: sample-sheet load + FastQC on raw paired-end reads, with
**optional** fastp adapter/quality trimming (opt-in via `--trim`). By default
Hi-C is mapped **raw** (4DN / distiller / Juicer standard), so without `--trim`
no trimmed FASTQs are produced — the raw FASTQs are symlinked into the
per-sample directory and FastQC runs for QC only. Every sample is a Hi-C
library grouped by biological `condition` + `replicate` (no input/IgG control,
no antibody / peak-mode).

## Output Structure

All outputs land directly under `--output` (OmicsClaw per-skill layout).
`<sample>` is each sample name from the sample sheet.

```
<output>/
├── README.md                              # orientation note
├── report.md                              # markdown summary (samples + trimming table)
├── result.json                            # structured envelope (Step 1)
├── bulkhic-preprocessing.log              # full run log (narrative + tool stdout/stderr)
├── fastq_trimmed/
│   ├── trimmed_summary.csv                # per-sample reads in/out, % kept, q30, tool
│   └── <sample>/                          # one directory per sample
│       ├── fastqc_raw/                    # FastQC HTML + zip reports on raw reads (unless --no-fastqc)
│       ├── <sample>_<mate>.fastq.gz       # default (no --trim): symlink to raw R1/R2 mate
│       ├── ...                            #   (one per mate: R1, and R2 if paired)
│       ├── <sample>_R1_trimmed.fastq.gz   # only with --trim: fastp-trimmed R1
│       ├── <sample>_R2_trimmed.fastq.gz   # only with --trim: fastp-trimmed R2 (paired)
│       ├── <sample>_fastp.json            # only with --trim: fastp QC JSON (parsed for stats)
│       └── <sample>_fastp.html            # only with --trim: fastp QC HTML report
└── reproducibility/
    ├── commands.sh                        # exact rerun command
    └── requirements.txt                   # pinned deps (pandas, numpy)
```

Demo mode (`--demo`) additionally writes, **one level above** `--output`
(i.e. `<output>/../`), the downloaded/streamed FASTQs and a generated sample
sheet:

```
<output>/../
├── fastq/
│   ├── demo_samplesheet.tsv               # generated TSV sample sheet (sample, condition, replicate, R1, R2, genome, source)
│   └── <sample>_R1.sub.fastq.gz           # streamed read-pair prefix per sample (R1/R2)
```

## File Contents

### `report.md`

Markdown summary with:

1. **Samples** — sample count, layout (paired-end), genome, conditions, tool.
2. **Trimming** — a table of `Sample | Condition | Reads before | Reads after | % kept`
   (populated only when `--trim` ran; otherwise dashes, since raw reads are mapped).
3. **Next Steps** — pointer to `bulkhic-mapping` (Step 2: bwa-mem2 `-SP5M` +
   pairtools → `.pairs.gz` + QC).

### `result.json`

Structured envelope chained into the downstream Hi-C steps.

```json
{
  "skill": "bulkhic-preprocessing",
  "version": "0.1.0",
  "log": "<output>/bulkhic-preprocessing.log",
  "steps_completed": ["preprocessing"],
  "steps_pending": ["mapping", "matrix", "compartments", "insulation", "loops", "pileup"],
  "params": {
    "genome": "dm6",
    "trim": false,
    "tool": "none",
    "threads": 16,
    "adapter": "AGATCGGAAGAGC",
    "min_length": 20,
    "quality": 20,
    "run_fastqc": true
  },
  "sample_sheet": {
    "n_samples": 4,
    "layout": "paired-end",
    "genome": "dm6",
    "conditions": ["asynchronous", "G1S_arrest"],
    "replicates_per_condition": { "asynchronous": [1, 2], "G1S_arrest": [1, 2] },
    "is_replicated": true,
    "samples": [
      { "name": "<sample>", "condition": "...", "replicate": 1,
        "r1": "...", "r2": "...", "genome": "dm6" }
    ]
  },
  "preprocessing": [
    { "sample": "<sample>", "tool": "none (raw)",
      "r1_trimmed": "...", "r2_trimmed": "...",
      "stats": { "total_reads_before": 0, "total_reads_after": 0,
                 "q30_rate_before": 0.0, "q30_rate_after": 0.0 } }
  ],
  "prev_result": null
}
```

Notes:
- When `--trim` is **off** (default), `tool` is `"none"` in `params` and
  `"none (raw)"` per sample; `r1_trimmed` / `r2_trimmed` point at the raw-FASTQ
  symlinks under `fastq_trimmed/<sample>/`, and `stats` is empty `{}`.
- When `--trim` is **on**, `tool` is `"fastp"`, the `*_trimmed.fastq.gz` paths
  are real outputs, and `stats` is parsed from `<sample>_fastp.json`
  (`total_reads_before/after`, `q30_rate_before/after`).

### `fastq_trimmed/trimmed_summary.csv`

One row per sample (written for both trim and no-trim runs).

| Column | Type | Meaning |
|---|---|---|
| `sample` | str | sample name |
| `tool` | str | `fastp` (with `--trim`) or `none (raw)` (default) |
| `total_reads_before` | int | raw read/pair count (null when not trimmed) |
| `total_reads_after` | int | post-trim read/pair count (null when not trimmed) |
| `reads_removed` | int | `before − after` (null when not trimmed) |
| `pct_reads_kept` | float | `after / before × 100`, rounded to 2 dp (null when not trimmed) |
| `q30_rate_before` | float | fraction Q≥30 before trimming (fastp; null otherwise) |
| `q30_rate_after` | float | fraction Q≥30 after trimming (fastp; null otherwise) |

### `fastq_trimmed/<sample>/fastqc_raw/`

Standard FastQC output for each input FASTQ — one HTML report plus its zip
bundle per mate (R1, and R2 if paired). Skipped entirely with `--no-fastqc`
or when `fastqc` is not on `PATH`. A `.done` sentinel (keyed on the input FASTQ
paths) caches the result so re-runs skip recompute.

### `fastq_trimmed/<sample>/` FASTQs

- **Default (no `--trim`)**: `<sample>_<mate>.fastq.gz` (one per mate — R1, and
  R2 for paired-end) are **symlinks** to the resolved raw FASTQs, so the
  preprocessing output is self-contained and downstream paths live under this
  skill. These are what `bulkhic-mapping` consumes.
- **With `--trim`**: `<sample>_R1_trimmed.fastq.gz` (+ `_R2` for paired) are the
  fastp-trimmed reads, alongside the fastp QC reports `<sample>_fastp.json`
  (machine-readable, parsed for `stats`) and `<sample>_fastp.html` (human view).
  A `<sample>.fastp.done` sentinel (keyed on inputs + adapter/min-length/quality)
  caches the run.

### `reproducibility/commands.sh`

Single-line `python bulkhic-preprocessing.py ...` rerun command with
`--threads` always expanded; in demo mode it carries `--demo` (+ `--demo-n-reads`
when non-default), otherwise `--input <samplesheet>`. When `--trim` was set it
additionally appends `--trim` and the `--tool` / `--min-length` / `--quality`
flags.

### Demo-only: `../fastq/demo_samplesheet.tsv` and `../fastq/<sample>_R1.sub.fastq.gz`

In `--demo` mode the skill streams the first `--demo-n-reads` read pairs of the
*D. melanogaster* S2R+ in-situ Hi-C libraries (GEO GSE101317, dm6; 2 conditions ×
2 replicates) into `<output>/../fastq/<sample>_{R1,R2}.sub.fastq.gz`, then writes
a generated TSV sample sheet `demo_samplesheet.tsv` (columns: `sample`,
`condition`, `replicate`, `R1`, `R2`, `genome`, `source`) that Step 1 loads.
