---
name: sc-count
description: Load when turning scRNA FASTQ (or existing CellRanger/STARsolo/SimpleAF/kb-python output)
  into a downstream-ready AnnData. Skip when reads are already counted into AnnData (use sc-standardize-input);
  raw quality assessment only (use sc-fastq-qc).
trigger: Cell Ranger count, STARsolo count, fastq to adata, raw single-cell counting, generate count matrix
tags:
- singlecell
- scrna
- counting
- cellranger
- starsolo
- simpleaf
- kb-python
---

# sc-count

## Use from a step

This is CLI_ONLY: counting needs external tools and reference indexes.

```python
from skills._sdk.notebook import run_cli

run_cli("sc-count", "--input", "data/sample_R1.fastq.gz",
        "--read2", "data/sample_R2.fastq.gz", "--method", "starsolo",
        "--reference", "/refs/star", "--chemistry", "10xv3",
        "--whitelist", "/refs/barcodes.tsv",
        inputs=["data/sample_R1.fastq.gz", "data/sample_R2.fastq.gz",
                "/refs/barcodes.tsv"])
```

Record the reference index version in the module README as well. The demo
standardizes PBMC3k raw counts; it does not align or count reads. There is
no `_api.py` for this skill.

## When to use

The user has FASTQ files (or pre-existing tool output directories) and
wants per-cell counts in OmicsClaw's canonical AnnData contract.  Four
backends share one CLI: `cellranger`, `starsolo`, `simpleaf`,
`kb_python`. When passed a matching already-counted directory the skill
re-canonicalises rather than re-counts.  Pairs with `sc-fastq-qc`
upstream (read QC) and `sc-multi-count` downstream (merging multiple
samples).

## Inputs & Outputs

**Inputs**

- Input kinds: `file`, `directory`
- Modalities: scrna
- File types: `.fastq`, `.fq`, compressed FASTQ, and backend-specific `.h5ad`
- FASTQ structure: valid first record; `paired` layout
- Directory layouts (any): `paired-fastq`, `tenx-matrix`, `cellranger-output`, `starsolo-output`, `pseudoalign-output`

**Outputs**

- `tables/backend_summary.csv`
- `tables/barcode_metrics.csv`
- `tables/count_summary.csv`
- `figures/barcode_rank.png`
- `figures/count_complexity_scatter.png`
- `figures/count_distributions.png`
- `processed.h5ad`
- `standardized_input.h5ad`
- `figures/manifest.json`, `figure_data/manifest.json`, plot-data CSV files
- `reproducibility/commands.sh`, `reproducibility/requirements.txt`
- Backend-specific files under `artifacts/` only when counting runs; BAM and HTML are not guaranteed.
- `report.md`
- `result.json`
- Processed AnnData (`saves_h5ad`)

## Flow

1. Resolve `--input`; if it's an existing CellRanger / STARsolo / SimpleAF / kb-python output dir, re-canonicalise instead of running the backend.
2. Otherwise validate backend prerequisites (chemistry, reference, t2g for kb-python, whitelist for STARsolo).
3. Run the chosen backend against the FASTQ (and `--read2` if explicit).
4. Load the resulting matrix into AnnData; canonicalise (`layers["counts"]`, `adata.raw`, gene-name harmonisation).
5. Render barcode-rank + count-distribution figures.
6. Emit `processed.h5ad` + `report.md` + `result.json`.

## Gotchas

- **Missing input path → hard fail.** `sc_count.py` raises `FileNotFoundError(f"Input path not found: {input_path}")`.  Common when the FASTQ dir is on a network mount that has not been resolved at run time.
- **STARsolo requires explicit chemistry.** `sc_count.py` raises `ValueError("STARsolo runs require an explicit `--chemistry` value such as `10xv3`.")` when chemistry is left at the `auto` default.  STARsolo currently supports `10xv2`, `10xv3`, and `10xv4`; pass one of those.
- **Backend prerequisites are validated up front.** `sc_count.py` raises `ValueError` for missing `--reference` (CellRanger/STARsolo/simpleaf), missing `--t2g` (kb-python), or unsupported `--chemistry` for STARsolo.  No silent fallback to a different backend — pick a feasible one before invoking.
- **Choose the backend matching the existing output.** `sc_count.py:main` detects directory shape within the selected `--method`. `result.json["data"]["execution"]` is empty when no backend ran. `tables/backend_summary.csv` is always written and can be empty; imported output may already contain backend metrics.
- `sc_count.py:_recommended_reference_dir` names suggested reference locations, not bundled indexes. Supply references yourself. The simpleaf backend needs a configured `ALEVIN_FRY_HOME`; the installed simpleaf 0.24.0 failed without it during migration preflight. The demo does not validate external-tool setup.
- `sc_count.py:main` defaults to eight threads. A directory containing several FASTQ samples needs `--sample`.

## Key CLI

```bash
# Demo (standardizes PBMC3k counts; no counting backend)
python skills/singlecell/scrna/sc-count/sc_count.py --demo --output /tmp/sc_count_demo

# CellRanger over FASTQ
python skills/singlecell/scrna/sc-count/sc_count.py \
  --input fastq_dir/ --output results/ \
  --reference cellranger_transcriptome --threads 16

# STARsolo (requires explicit chemistry)
python skills/singlecell/scrna/sc-count/sc_count.py \
  --input fastq_dir/ --output results/ \
  --method starsolo --reference star_genome_dir --chemistry 10xv3 --whitelist barcodes.tsv

# Re-canonicalise an existing CellRanger output directory
python skills/singlecell/scrna/sc-count/sc_count.py \
  --input cellranger_output_dir/ --output results/
```

## See also

- `references/parameters.md` — every CLI flag and per-backend prerequisite
- `references/methodology.md` — backend selection guide, re-canonicalise vs re-run logic
- `references/output_contract.md` — `processed.h5ad` schema + table layouts
- Adjacent skills: `sc-fastq-qc` (upstream — read-quality check before counting), `sc-multi-count` (downstream — merge multiple sample outputs), `sc-standardize-input` (parallel — for AnnData from outside OmicsClaw)

## Dependencies

Python packages this skill's script needs. They are not installed for you — check before a long run.

`anndata`, `matplotlib`, `numpy`, `pandas`, `scanpy`, `scipy`, `seaborn`
