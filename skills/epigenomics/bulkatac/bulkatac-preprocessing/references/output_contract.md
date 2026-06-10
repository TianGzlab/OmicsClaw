# Output Contract — bulkatac-preprocessing

## Output Structure

All skill-generated outputs land directly under the skill's `--output`
directory — the OmicsClaw per-skill layout, with no nested `preprocessing/`
subdir. The caller passes a step-specific dir, e.g.
`--output <project>/preprocessing`, so sibling steps (`bulkatac-mapping`, …)
can locate this result.

Demo mode additionally writes its **input** — `demo_samplesheet.tsv` and
`fastq/` — to `--output`'s **parent** directory, beside `--output` rather
than inside it. That data stands in for a fastq/ dir a real user prepares
separately, so it is kept out of the skill's own artifact namespace.

```
<output>/../                            # parent of --output
├── demo_samplesheet.tsv               # demo only — auto-generated sheet
├── fastq/                             # demo only — raw + subsampled FASTQs
│   ├── SRR1822153_1.fastq.gz          #   raw download (example)
│   └── T0_rep1.ds50000_R1.fastq.gz    #   subsampled (example, --demo-n-reads)
└── <output>/                          # the --output directory
    ├── README.md                      # orientation note
    ├── report.md                      # markdown summary
    ├── result.json                    # structured envelope
    ├── fastq_trimmed/                 # trimmed FASTQs + per-sample QC
    │   ├── <sample>_R1_trimmed.fastq.gz
    │   ├── <sample>_R2_trimmed.fastq.gz   # paired-end only
    │   ├── <sample>_trimmed.fq.gz         # single-end (Trim Galore naming)
    │   ├── <sample>_fastp.json            # fastp only
    │   ├── <sample>_fastp.html            # fastp only
    │   ├── <sample>_trimming_report.txt   # Trim Galore only
    │   └── trimmed_summary.csv            # aggregated per-sample stats
    └── reproducibility/
        ├── commands.sh                # exact re-run command
        └── requirements.txt            # pip-style version pins
```

## File Contents

### `report.md`

Markdown summary with three sections:

1. **Step 1a — Data Loading** — sample count, layout (single-end / paired-end), genome string, condition list, replicate counts per condition, `is_replicated` flag.
2. **Step 1b — Adapter Trimming** — resolved tool name (never `auto`), adapter sequence, `min_length`, quality threshold.
3. **Trimming summary** — inline rendering of `trimmed_summary.csv` (markdown table).

### `result.json`

```json
{
  "skill": "bulkatac-preprocessing",
  "version": "0.1.0",
  "steps_completed": ["data_loading", "preprocessing"],
  "steps_pending": ["mapping", "qc_after_mapping", "peak_calling", ...],
  "params": {
    "genome":     "<resolved>",
    "tool":       "<fastp|trim_galore>",   // never "auto"
    "threads":    16,
    "adapter":    "CTGTCTCTTATACACATCT",
    "min_length": 36,
    "quality":    20,
    "run_fastqc": true
  },
  "sample_sheet": { /* layout, conditions, replicates_per_condition, ... */ },
  "preprocessing": [
    {
      "sample":     "<name>",
      "tool":       "<fastp|trim_galore>",
      "r1_trimmed": "<output>/fastq_trimmed/<sample>_R1_trimmed.fastq.gz",
      "r2_trimmed": "<output>/fastq_trimmed/<sample>_R2_trimmed.fastq.gz",
      "stats":      { /* tool-specific reads-in / reads-out / Q30% / adapter% */ }
    }
  ]
}
```

`steps_pending` carries the explicit roadmap so the OmicsClaw runner /
agent can route downstream work to the right sibling skills.

### `fastq_trimmed/trimmed_summary.csv`

One row per sample. Columns (built by
`_lib.preprocessing.build_preprocessing_summary` at `_lib/preprocessing.py:580-602`):

| Column | Type | Meaning |
|---|---|---|
| `sample` | str | sample name from the sample sheet |
| `tool` | str | resolved tool — `fastp` or `trim_galore` |
| `total_reads_before` | int | total reads before trimming (per mate for paired-end) |
| `total_reads_after` | int | reads passing length + quality filters |
| `reads_removed` | int | `total_reads_before − total_reads_after` (`None` if either source value is missing) |
| `pct_reads_kept` | float | `total_reads_after / total_reads_before × 100`, rounded to 2 dp |
| `q30_rate_before` | float | % bases ≥ Q30 in input (tool-reported; may be empty for Trim Galore) |
| `q30_rate_after` | float | % bases ≥ Q30 after trim |
| `adapter_trimmed_reads` | int | count of reads where an adapter was clipped |
| `pct_adapter_trimmed` | float | `adapter_trimmed_reads / total_reads_before × 100`, rounded to 2 dp |

Trimmed-FASTQ paths are NOT columns of this CSV — they're carried per-sample
in `result.json["preprocessing"][i]["r1_trimmed"]` / `["r2_trimmed"]`.

### `fastq_trimmed/<sample>_R{1,2}_trimmed.fastq.gz`

gzipped FASTQ output from fastp (default) or `<sample>_trimmed.fq.gz` from
Trim Galore (single-end). Reads shorter than `--min-length` or below
average Phred `--quality` are dropped. Adapter sequence stripped using
either fastp's overlap-based detection or Trim Galore's cutadapt-driven
matching against the Nextera adapter.

### `fastq_trimmed/<sample>_fastp.{json,html}` *(fastp only)*

Native fastp report — JSON for programmatic consumption, HTML for human
inspection (per-base quality, adapter content, duplication estimate, k-mer
profiles).

### `fastq_trimmed/<sample>_trimming_report.txt` *(Trim Galore only)*

Trim Galore native log — cutadapt parameters, adapter counts, length
distribution. No JSON equivalent; downstream tooling should prefer the
aggregated `trimmed_summary.csv`.

### `reproducibility/commands.sh`

Single-line shell command reproducing the run. The `--tool` flag is always
the **resolved** tool (never `auto`) so the script ends up identical
across machines:

```bash
#!/bin/bash
python skills/epigenomics/bulkatac/bulkatac-preprocessing/bulkatac-preprocessing.py \
    --input <samplesheet.tsv> --wd <output> --genome <build> \
    --tool fastp --threads 16 --min-length 36 --quality 20
```

### `reproducibility/requirements.txt`

Pip-style pins for the Python packages the script actually imported
(`pandas`, `numpy`). External tools (`fastp`, `fastqc`, `sra-tools`) are
NOT pinned here — record those separately via `conda list` if exact
reproduction matters.

## Demo-mode files

These are demo *input*, so they are written to `--output`'s **parent**
directory (`<output>/../`), beside `--output` rather than inside it.

`<output>/../demo_samplesheet.tsv` — 4-sample sample sheet auto-generated by
`_lib.preprocessing.get_data` after the SRA fetch resolves. Mirrors the
real `--input` schema so a user can copy it as a starting template.

`<output>/../fastq/SRR*_{1,2}.fastq.gz` — raw downloads from SRA. Kept after
the run so a second `--demo` invocation skips the (slow) re-download. Delete
this directory manually to force a refresh.

`<output>/../fastq/<sample>.ds<N>_R{1,2}.fastq.gz` — subsampled FASTQs (e.g.
`T0_rep1.ds50000_R1.fastq.gz`). These are what the sample sheet points at,
not the raw SRR files.
