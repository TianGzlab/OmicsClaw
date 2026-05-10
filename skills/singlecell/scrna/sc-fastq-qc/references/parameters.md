<!-- AUTO-GENERATED from parameters.yaml — do not edit by hand. -->
<!-- Regenerate: python scripts/generate_parameters_md.py <skill_dir> -->


# Parameters

## Allowed extra CLI flags

- `--max-reads`
- `--read2`
- `--sample`
- `--threads`
- `--r-enhanced`

## Per-method parameter hints

### `fastqc`

**Tuning priority:** threads -> sample -> read2 -> max_reads

**Core parameters:**

| name | default |
|---|---|
| `threads` | `4` |
| `sample` | `—` |
| `read2` | `—` |
| `max_reads` | `20000` |

**Requires:**
- `fastq_or_fastq_dir`

**Tips:**
- --threads: forwarded to FastQC when installed, and used for external tool runs.
- --sample: choose one sample when the input directory contains multiple FASTQ groups.
- --max-reads: Python fallback only samples this many reads per FASTQ for lightweight local summaries.
