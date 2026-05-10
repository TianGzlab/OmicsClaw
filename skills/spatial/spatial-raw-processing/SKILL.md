---
name: spatial-raw-processing
description: Load when converting spatial transcriptomics raw FASTQ pairs through ST-Pipeline into a `raw_counts.h5ad` ready for spatial-preprocess. Skip when input is already a count-matrix AnnData (go straight to spatial-preprocess) or for non-spatial bulk / scRNA FASTQ (use bulkrna-read-qc / sc-fastq-qc).
version: 0.3.0
author: OmicsClaw
license: MIT
tags:
- spatial
- raw-processing
- fastq
- st-pipeline
- visium
- slideseq
requires:
- anndata
- numpy
- pandas
---

# spatial-raw-processing

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

| Input | Format | Required |
|---|---|---|
| Read 1 (barcode + UMI) | `.fastq` / `.fastq.gz` (`--read1`) | yes (real run) |
| Read 2 (cDNA) | `.fastq` / `.fastq.gz` (`--read2`) | yes (real run) |
| Spot barcode IDs | TSV / file (`--ids`) | yes (real run) |
| STAR index | directory (`--ref-map`) | yes (real run) |
| Reference annotation | GTF (`--ref-annotation`) | optional |
| Bundle JSON / YAML | path (positional `--input`) | optional — alternative to flag-by-flag args |

| Output | Path | Notes |
|---|---|---|
| Raw counts AnnData | `raw_counts.h5ad` | one row per spatial spot; `obs["barcode"]`, `obsm["spatial"]`, `obs["x_array"]` / `y_array` if available |
| Pipeline metrics | upstream-tool outputs (logs, stats) | written by ST-Pipeline alongside `raw_counts.h5ad` |
| Report | `result.json` | always |

## Flow

1. Parse args (or load bundle JSON / YAML from positional `--input`).
2. `_apply_effective_defaults` fills missing parameter values (threads, trimming, UMI ranges, etc.).
3. `_validate_real_run_bundle`: check `read1` / `read2` / `ids` / `ref-map` exist and are well-typed; reject duplicate read1=read2; verify FASTQ extension.
4. Call `run_stpipeline(...)` which shells out to ST-Pipeline (requires the `stpipeline` binary on PATH or `--stpipeline-repo` + `--bin-path`).
5. Wrap the resulting count matrix into AnnData with `X = raw_counts`, `layers["counts"]`, `raw = raw_counts_snapshot`.
6. Save `raw_counts.h5ad` and `result.json`. Print "next: spatial-preprocess on raw_counts.h5ad".

## Gotchas

- **All input failures raise typed exceptions wrapped in `SystemExit(1)`.** `spatial_raw_processing.py:353` catches `DataError` / `DependencyError` / `ParameterError` / `ProcessingError` and re-raises as `SystemExit(1)`. The originating raises live in `_validate_real_run_bundle` — `:125` raises `ParameterError(f"Missing required parameter: {key}")` for missing `read1`/`read2`/`ids`; `:128` raises `DataError(...)` for non-existent files; `:131` raises `DataError("Resolved read1/read2 inputs must be FASTQ files.")` for non-FASTQ extensions; `:134` raises `ParameterError` for read1==read2; `:138-141` raises `DataError` for missing / wrong-type STAR index dir; `:145-146` raises `DataError` only when `--ref-annotation` was *provided* but the path is missing or not a file (the param itself is optional — omitting it doesn't raise).
- **`--read1` / `--read2` / `--ids` / `--ref-map` are all required for real runs** (not enforced by argparse `required=True`, validated later). Missing any → `ParameterError`. Demo mode skips this validation entirely.
- **The output filename is always `raw_counts.h5ad`** (`spatial_raw_processing.py:286`). It's not configurable — the contract is consumed by `spatial-preprocess`. Multiple runs to the same `--output` will overwrite.
- **No tables / figures are written.** This skill is a wrapper around an external pipeline; it produces only the AnnData + the upstream tool's logs. `result.json` records the run params, not analysis stats.
- **Demo mode skips ST-Pipeline entirely.** `spatial_raw_processing.py:235` calls `create_demo_upstream_outputs(...)` to fabricate a synthetic `raw_counts.h5ad`. Useful for plumbing checks; does NOT exercise the FASTQ → matrix code path.
- **`--platform` is a metadata label only.** `:201` documents it as "Label recorded in outputs"; ST-Pipeline doesn't branch on it. Common values: `visium`, `visium_hd`, `slideseq`, custom strings.

## Key CLI

```bash
# Demo (synthetic raw_counts.h5ad — does NOT run ST-Pipeline)
python omicsclaw.py run spatial-raw-processing --demo --output /tmp/spatial_raw_demo

# Real run with explicit args
python omicsclaw.py run spatial-raw-processing \
  --read1 sample_R1.fastq.gz --read2 sample_R2.fastq.gz \
  --ids barcodes.tsv \
  --ref-map /refs/star_index_human \
  --ref-annotation /refs/genes.gtf \
  --exp-name visium_001 --platform visium \
  --threads 16 \
  --output results/

# Real run from bundle JSON
python omicsclaw.py run spatial-raw-processing \
  --input run_bundle.json --output results/

# Slide-seq with custom UMI range
python omicsclaw.py run spatial-raw-processing \
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
