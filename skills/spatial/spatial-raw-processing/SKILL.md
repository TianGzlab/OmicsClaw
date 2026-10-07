---
name: spatial-raw-processing
description: Load when converting spatial transcriptomics raw FASTQ pairs through ST-Pipeline into a `raw_counts.h5ad`
  ready for spatial-preprocess. Skip when input is already a count-matrix AnnData (use spatial-preprocess);
  non-spatial bulk / scRNA FASTQ (use bulkrna-read-qc).
trigger: spatial raw processing, raw spatial fastq, spatial fastq, st_pipeline, st pipeline, barcode coordinates, ids file, visium raw fastq, slide-seq fastq, slideseq fastq, upstream spatial processing
tags:
- spatial
- raw-processing
- fastq
- st-pipeline
- visium
- slideseq
---

# spatial-raw-processing

## Use from a step

This is CLI_ONLY: ST-Pipeline consumes FASTQ files, barcode coordinates and
reference indexes. It is not an in-memory analysis function.

```python
from skills._sdk.notebook import run_cli

output = run_cli("spatial-raw-processing", "--input", "data/run_bundle.json",
                 inputs=["data/run_bundle.json", "data/R1.fastq.gz",
                         "data/R2.fastq.gz", "data/barcodes.tsv"])
```

Record the reference index version in the module README. The executable
example uses synthetic upstream outputs and does not run ST-Pipeline.

## When to use

The user has paired-end spatial-transcriptomics FASTQ files (`read1` =
spatial barcode + UMI, `read2` = cDNA) plus a STAR genome index, and
wants the standard ST-Pipeline run that produces a `raw_counts.h5ad`
with one row per spatial spot. Single backend: `st_pipeline` (calls
`run_stpipeline` from `skills/spatial/_lib/stpipeline_adapter.py`).

After this skill, chain to `spatial-preprocess` for QC + normalisation.
For non-spatial scRNA FASTQ use `sc-fastq-qc`. For bulk RNA-seq read
QC use `bulkrna-read-qc`.

## Inputs & Outputs

**Inputs**

- Input kinds: `file`, `directory`
- Modalities: visium, slideseq
- File types: `.fastq`, `.fq`, `.json`, `.yaml`, `.yml`
- FASTQ structure: valid first record; `paired` layout
- Directory layouts (any): `paired-fastq`

**Outputs**

- `tables/gene_qc.csv`
- `tables/raw_gene_qc.csv`
- `tables/raw_processing_run_summary.csv`
- `tables/raw_processing_spatial_points.csv`
- `tables/raw_spot_qc.csv`
- `tables/raw_top_genes.csv`
- `tables/run_summary.csv`
- `tables/saturation_curve.csv`
- `tables/spatial_coordinates.csv`
- `tables/spot_qc.csv`
- `tables/stage_summary.csv`
- `tables/top_genes.csv`
- `figures/raw_detected_genes_spatial.png`
- `figures/raw_spot_qc_histograms.png`
- `figures/raw_top_genes_barplot.png`
- `figures/raw_total_counts_spatial.png`
- `figures/st_pipeline_saturation_curve.png`
- `figures/st_pipeline_stage_attrition.png`
- `omicsclaw_stpipeline_run.json`
- `raw_counts.h5ad`
- `st_pipeline.stderr.txt`
- `st_pipeline.stdout.txt`
- `report.md`
- `result.json`
- Processed AnnData (`saves_h5ad`) — adds `obs`: `barcode`, `x_array`, `y_array`; `obsm`: `spatial`

## Flow

1. Parse args (or load bundle JSON / YAML from positional `--input`).
2. `_apply_effective_defaults` fills missing parameter values (threads, trimming, UMI ranges, etc.).
3. `_validate_real_run_bundle`: check `read1` / `read2` / `ids` / `ref-map` exist and are well-typed; reject duplicate read1=read2; verify FASTQ extension.
4. Call `run_stpipeline(...)` which shells out to ST-Pipeline (requires the `stpipeline` binary on PATH or `--stpipeline-repo` + `--bin-path`).
5. Wrap the resulting count matrix into AnnData with `X = raw_counts`, `layers["counts"]`, `raw = raw_counts_snapshot`.
6. Save `raw_counts.h5ad` and `result.json`. Print "next: spatial-preprocess on raw_counts.h5ad".

## Gotchas

- **All input failures raise typed exceptions wrapped in `SystemExit(1)`.** `spatial_raw_processing.py` catches `DataError` / `DependencyError` / `ParameterError` / `ProcessingError` and re-raises as `SystemExit(1)`. The originating raises live in `_validate_real_run_bundle` — it raises `ParameterError(f"Missing required parameter: {key}")` for missing `read1`/`read2`/`ids`; raises `DataError(...)` for non-existent files; raises `DataError("Resolved read1/read2 inputs must be FASTQ files.")` for non-FASTQ extensions; raises `ParameterError` for read1==read2; raises `DataError` for missing / wrong-type STAR index dir; raises `DataError` only when `--ref-annotation` was *provided* but the path is missing or not a file (the param itself is optional — omitting it doesn't raise).
- **`--read1` / `--read2` / `--ids` / `--ref-map` are all required for real runs** (not enforced by argparse `required=True`, validated later). Missing any → `ParameterError`. Demo mode skips this validation entirely.
- **The output filename is always `raw_counts.h5ad`** (`spatial_raw_processing.py`). It's not configurable — the contract is consumed by `spatial-preprocess`. Multiple runs to the same `--output` will overwrite.
- **QC tables and figures are written.** `tables/spot_qc.csv` and `figures/raw_total_counts_spatial.png` describe the count matrix; upstream stage and saturation plots depend on available pipeline metrics.
- **Demo mode skips ST-Pipeline entirely.** `spatial_raw_processing.py` calls `create_demo_upstream_outputs(...)` to fabricate a synthetic `raw_counts.h5ad`. Useful for plumbing checks; does NOT exercise the FASTQ → matrix code path.
- **`--platform` is a metadata label only.** `_build_parser` documents it as "Label recorded in outputs"; ST-Pipeline doesn't branch on it. Common values: `visium`, `visium_hd`, `slideseq`, custom strings.

## Key CLI

```bash
# Demo (synthetic raw_counts.h5ad — does NOT run ST-Pipeline)
python skills/spatial/spatial-raw-processing/spatial_raw_processing.py --demo --output /tmp/spatial_raw_demo

# Real run with explicit args
python skills/spatial/spatial-raw-processing/spatial_raw_processing.py \
  --read1 sample_R1.fastq.gz --read2 sample_R2.fastq.gz \
  --ids barcodes.tsv \
  --ref-map /refs/star_index_human \
  --ref-annotation /refs/genes.gtf \
  --exp-name visium_001 --platform visium \
  --threads 16 \
  --output results/

# Real run from bundle JSON
python skills/spatial/spatial-raw-processing/spatial_raw_processing.py \
  --input run_bundle.json --output results/

# Slide-seq with custom UMI range
python skills/spatial/spatial-raw-processing/spatial_raw_processing.py \
  --read1 R1.fq.gz --read2 R2.fq.gz --ids barcodes.tsv \
  --ref-map /refs/star_index --platform slideseq \
  --umi-start-position 1 --umi-end-position 8 \
  --output results/
```

## See also

- `references/parameters.md` — every CLI flag, ST-Pipeline option mapping
- `references/methodology.md` — when ST-Pipeline wins vs Space Ranger; barcode-ID format
- `references/output_contract.md` — `raw_counts.h5ad` schema
- Adjacent skills: `spatial-preprocess` (downstream — required next step; consumes `raw_counts.h5ad`), `bulkrna-read-qc` / `sc-fastq-qc` (parallel — non-spatial FASTQ paths)

## Dependencies

Python packages this skill's script needs. They are not installed for you — check before a long run.

`anndata`, `matplotlib`, `numpy`, `pandas`, `PyYAML`, `scipy`, `seaborn`
