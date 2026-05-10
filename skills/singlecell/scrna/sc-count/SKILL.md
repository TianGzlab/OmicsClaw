---
name: sc-count
description: Load when turning scRNA FASTQ (or existing CellRanger/STARsolo/SimpleAF/kb-python output) into a downstream-ready AnnData. Skip when reads are already counted into AnnData (use sc-standardize-input) or for raw quality assessment only (use sc-fastq-qc).
version: 0.3.0
author: OmicsClaw
license: MIT
tags:
- singlecell
- scrna
- counting
- cellranger
- starsolo
- simpleaf
- kb-python
requires:
- anndata
- pandas
---

# sc-count

## When to use

The user has FASTQ files (or pre-existing tool output directories) and
wants per-cell counts in OmicsClaw's canonical AnnData contract.  Four
backends share one CLI: `cellranger`, `starsolo`, `simpleaf`,
`kb-python`.  When passed an already-counted directory the skill
re-canonicalises rather than re-counts.  Pairs with `sc-fastq-qc`
upstream (read QC) and `sc-multi-count` downstream (merging multiple
samples).

## Inputs & Outputs

| Input | Format | Required |
|---|---|---|
| Reads or counts | FASTQ path / dir, or existing CellRanger / STARsolo / SimpleAF / kb-python output dir | yes (unless `--demo`) |
| Reference | transcriptome / genome dir / index, depending on backend | only when running the backend (not for re-canonicalising existing output) |

| Output | Path | Notes |
|---|---|---|
| AnnData | `processed.h5ad` | canonical contract; sample-label populated when `--sample` is used |
| Run summary | `tables/count_summary.csv` | compact run-level summary |
| Per-barcode metrics | `tables/barcode_metrics.csv` | per-barcode count summary |
| Diagnostic figures | `figures/barcode_rank.png`, `figures/count_distributions.png`, `figures/count_complexity_scatter.png` | always rendered |
| Report | `report.md` + `result.json` | always written |

## Flow

1. Resolve `--input`; if it's an existing CellRanger / STARsolo / SimpleAF / kb-python output dir, re-canonicalise instead of running the backend.
2. Otherwise validate backend prerequisites (chemistry, reference, t2g for kb-python, whitelist for STARsolo).
3. Run the chosen backend against the FASTQ (and `--read2` if explicit).
4. Load the resulting matrix into AnnData; canonicalise (`layers["counts"]`, `adata.raw`, gene-name harmonisation).
5. Render barcode-rank + count-distribution figures.
6. Emit `processed.h5ad` + `report.md` + `result.json`.

## Gotchas

- **Missing input path → hard fail.** `sc_count.py:356` raises `FileNotFoundError(f"Input path not found: {input_path}")`.  Common when the FASTQ dir is on a network mount that has not been resolved at run time.
- **STARsolo requires explicit chemistry.** `sc_count.py:420` raises `ValueError("STARsolo runs require an explicit `--chemistry` value such as `10xv3`.")` when chemistry is left at the `auto` default.  STARsolo currently supports `10xv2`, `10xv3`, and `10xv4`; pass one of those.
- **Backend prerequisites are validated up front.** `sc_count.py:401`, `:423`, `:451` raise `ValueError` for missing `--reference` (CellRanger/STARsolo/simpleaf), missing `--t2g` (kb-python), or unsupported `--chemistry` for STARsolo.  No silent fallback to a different backend — pick a feasible one before invoking.
- **Re-canonicalising-existing-output is detected by directory shape, not a flag.** If `--input` points at a CellRanger output dir (e.g. one with `outs/raw_feature_bc_matrix/`), the skill skips counting and just imports the matrix.  The summary distinguishes the two paths in `result.json["summary"]["mode"]`; verify if you expected a fresh run.

## Key CLI

```bash
# Demo (synthetic FASTQ + CellRanger-shaped output)
python omicsclaw.py run sc-count --demo --output /tmp/sc_count_demo

# CellRanger over FASTQ
python omicsclaw.py run sc-count \
  --input fastq_dir/ --output results/ \
  --reference cellranger_transcriptome --threads 16

# STARsolo (requires explicit chemistry)
python omicsclaw.py run sc-count \
  --input fastq_dir/ --output results/ \
  --reference star_genome_dir --chemistry 10xv3 --whitelist barcodes.tsv

# Re-canonicalise an existing CellRanger output directory
python omicsclaw.py run sc-count \
  --input cellranger_output_dir/ --output results/
```

## See also

- `references/parameters.md` — every CLI flag and per-backend prerequisite
- `references/methodology.md` — backend selection guide, re-canonicalise vs re-run logic
- `references/output_contract.md` — `processed.h5ad` schema + table layouts
- Adjacent skills: `sc-fastq-qc` (upstream — read-quality check before counting), `sc-multi-count` (downstream — merge multiple sample outputs), `sc-standardize-input` (parallel — for AnnData from outside OmicsClaw)
