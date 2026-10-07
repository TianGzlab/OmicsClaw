---
name: sc-fastq-qc
description: Load when checking raw single-cell FASTQ read quality (Phred / GC / adapter / length) before
  counting. Skip when reads are already counted (use sc-qc); bulk FASTQ (use bulkrna-read-qc).
trigger: scRNA FASTQ QC, FastQC single-cell, MultiQC single-cell, raw read quality, read-level QC
tags:
- singlecell
- scrna
- fastq
- qc
- read-quality
---

# sc-fastq-qc

## Use from a step

This is CLI_ONLY: it reads FASTQ files and optionally starts FastQC/MultiQC.

```python
from skills._sdk.notebook import run_cli

run_cli("sc-fastq-qc", "--input", "data/sample_R1.fastq.gz",
        "--read2", "data/sample_R2.fastq.gz",
        inputs=["data/sample_R1.fastq.gz", "data/sample_R2.fastq.gz"])
```

The demo renders synthetic summary tables; it does not read FASTQ or test
the external tools. There is no `_api.py` for this skill.

## When to use

The user has raw scRNA-seq FASTQ files (one or more, or a directory of
samples) and wants per-file / per-sample / per-base quality summaries
before running `sc-count` or `cellranger`. Python summaries always run.
FastQC and MultiQC add reports when installed; a tool that is present but
fails is a hard error, not a fallback to a successful Python-only run.

## Inputs & Outputs

**Inputs**

- Input kinds: `file`, `directory`
- Modalities: scrna
- File types: `.fastq`, `.fq`, and their `.gz` variants
- FASTQ structure: valid first record
- Directory layouts (any): `fastq-collection`

**Outputs**

- `tables/fastq_per_base_quality.csv`
- `tables/fastq_per_file_summary.csv`
- `tables/fastq_per_sample_summary.csv`
- `figures/fastq_file_quality.png`
- `figures/fastq_q30_summary.png`
- `figures/fastq_read_structure.png`
- `figures/per_base_quality.png`
- `figures/manifest.json`, `figure_data/manifest.json`, plot-data CSV files
- `reproducibility/commands.sh`, `reproducibility/requirements.txt`
- Optional external reports under `artifacts/fastqc/` and `artifacts/multiqc/`
- `report.md`
- `result.json`

## Flow

1. Discover FASTQ files and choose one sample (`--sample` disambiguates a directory).
2. Summarize the first `--max-reads` records per file in Python.
3. Run FastQC when present, then MultiQC when both tools are present.
4. Render four figures from the Python summaries; external HTML is separate.
5. Write three tables, `report.md` and `result.json`.

## Gotchas

- **`--max-reads 20000` caps Python summaries only.** `tables/fastq_per_file_summary.csv` records sampled depth. FastQC processes the full files. This is a prefix sample, not random sampling.
- **`--r-enhanced` is accepted but produces no R plots.** This skill emits Python figures only.  Pass freely, expect no R Enhanced output.
- `figures/manifest.json` records per-figure status; `result.json` lists external tool availability and commands under `data.external_tools`.
- `_lib/upstream.py:choose_fastq_sample` rejects ambiguous multi-sample directories. Run once per sample with `--sample`; one invocation does not batch every sample.

## Key CLI

```bash
# Demo (synthetic summary tables, no FASTQ or external tools)
python skills/singlecell/scrna/sc-fastq-qc/sc_fastq_qc.py --demo --output /tmp/sc_fastq_qc_demo

# Single-file with paired-end
python skills/singlecell/scrna/sc-fastq-qc/sc_fastq_qc.py \
  --input sample_R1.fastq.gz --read2 sample_R2.fastq.gz --output results/

# Choose a sample and increase Python sampling depth
python skills/singlecell/scrna/sc-fastq-qc/sc_fastq_qc.py \
  --input fastq_dir/ --sample sample_A --output results/ --max-reads 100000 --threads 8
```

## See also

- `references/parameters.md` — every CLI flag and tuning hint
- `references/methodology.md` — FastQC integration + Python fallback rationale
- `references/output_contract.md` — table column schemas + figure roles
- Adjacent skills: `sc-count` (next step — FASTQ → AnnData), `bulkrna-read-qc` (bulk RNA-seq variant), `sc-qc` (downstream count-matrix QC)

## Dependencies

Python packages this skill's script needs. They are not installed for you — check before a long run.

`anndata`, `matplotlib`, `numpy`, `pandas`, `scanpy`, `scipy`, `seaborn`
