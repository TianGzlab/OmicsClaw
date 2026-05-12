---
name: genomics-cnv-calling
description: Load when calling CNV segments via CBS-style segmentation on a bin-level log2-ratio CSV from exome / WGS coverage — emits per-segment 5-class CN state (`amplification` / `gain` / `neutral` / `loss` / `deep_deletion`), per-chromosome summary, genome-fraction-altered. Skip when working with single-cell / spatial CNV (use `spatial-cnv`).
version: 0.5.0
author: OmicsClaw
license: MIT
tags:
- genomics
- cnv
- copy-number
- cbs
- segmentation
- cnvkit
- gatk-gcnv
requires:
- pandas
- numpy
---

# genomics-cnv-calling

## When to use

The user has a bin-level log2-ratio CSV (typically from CNVkit
`cnr` files, GATK gCNV `denoised copy ratios`, or Control-FREEC
ratio output) and wants to segment into discrete CNV calls. Each
segment is classified into one of five copy-number states based on
mean log2 ratio: `amplification` (> +1.0), `gain` (> +0.3),
`neutral`, `loss` (< -0.3), `deep_deletion` (< -1.0). `--alpha`
controls segmentation significance (default 0.01).

This skill does NOT generate the bin-level log2-ratio CSV — it
consumes the output of CNVkit / GATK gCNV / Control-FREEC. For
spatial / single-cell CNV use `spatial-cnv`.

## Inputs & Outputs

| Input | Format | Required |
|---|---|---|
| Bin-level log2 ratios | `.csv` with columns `chrom`, `start`, `end`, `log2_ratio` | yes (unless `--demo`) |
| Segmentation significance | `--alpha <float>` (default 0.01) | no |

| Output | Path | Notes |
|---|---|---|
| CNV segments | `tables/cnv_segments.csv` | per-segment columns: `chrom`, `start`, `end`, `n_bins`, `log2_ratio`, `cn_state` (5-class), `estimated_cn` |
| Per-chromosome | `tables/cnv_per_chromosome.csv` | n_segments + altered fraction per chromosome |
| Report | `report.md` + `result.json` | summary includes `n_amplifications`, `n_deep_deletions`, `n_gains`, `n_losses`, `genome_fraction_altered` |

## Flow

1. Load bin CSV (`--input <bins.csv>`) or generate a demo bin file at `output_dir/demo_cnv_bins.csv` (`genomics_cnv_calling.py:229`).
2. Read columns via `pd.read_csv` (`genomics_cnv_calling.py:250`); group by `df["chrom"]` (`:254`) and segment per chromosome.
3. Classify each segment via `np.select` (`genomics_cnv_calling.py:161-162`) into one of `amplification` / `gain` / `neutral` / `loss` / `deep_deletion` based on mean log2.
4. Aggregate per-chromosome counts + genome-fraction-altered (`:281-291`).
5. Write `tables/cnv_segments.csv` (`genomics_cnv_calling.py:373`) + `tables/cnv_per_chromosome.csv` (`:382`) + `report.md` + `result.json` (`:385`).

## Gotchas

- **Required CSV column is `chrom`, NOT `chromosome`.** Code reads `df["chrom"]` at `genomics_cnv_calling.py:254`. CNVkit `cnr` files have a `chromosome` column — rename to `chrom` first (`pd.read_csv(...).rename(columns={"chromosome": "chrom"})`). Other required columns are `start`, `end`, `log2_ratio`.
- **`cn_state` has 5 classes, NOT 3.** `genomics_cnv_calling.py:161-162` produces `amplification` (log2 > 1.0), `gain` (> 0.3), `neutral`, `loss` (< -0.3), `deep_deletion` (< -1.0). The summary reports `n_gains` and `n_losses` as **inclusive** of `amplification` / `deep_deletion` (`:281-282`); inspect `n_amplifications` / `n_deep_deletions` for the high-magnitude subset.
- **No bin generator is invoked.** This skill consumes a bin-level log2-ratio CSV — it does NOT run CNVkit / GATK gCNV / Control-FREEC. Run them upstream and feed the bin file here.
- **`--input` REQUIRED unless `--demo`.** `genomics_cnv_calling.py:363` raises `ValueError("--input required when not using --demo")`; non-existent paths raise `FileNotFoundError` at `:366`.
- **`--alpha` controls segmentation aggressiveness.** Lower values (e.g. 0.001) yield fewer / larger segments; higher values (0.1) yield more / smaller. Default 0.01 is suitable for clean exome / WGS data; for noisy panels consider `--alpha 0.001`.
- **Classification thresholds are hard-coded.** ±0.3 (gain/loss) and ±1.0 (amplification/deep_deletion) at `genomics_cnv_calling.py:50-52` — no CLI flag to tune. For tumour-purity-corrected calling, scale the input log2 ratios upstream.

## Key CLI

```bash
# Demo
python omicsclaw.py run genomics-cnv-calling --demo --output /tmp/cnv_demo

# Real CNVkit bins (rename `chromosome` → `chrom` first)
python omicsclaw.py run genomics-cnv-calling \
  --input sample_renamed.cnr.csv --output results/ --alpha 0.01

# Stricter segmentation for noisy panel data
python omicsclaw.py run genomics-cnv-calling \
  --input panel.cnr.csv --output results/ --alpha 0.001
```

## See also

- `references/parameters.md` — every CLI flag
- `references/methodology.md` — segmentation algorithm, 5-class threshold rationale
- `references/output_contract.md` — `tables/cnv_segments.csv` schema
- Adjacent skills: `genomics-alignment` (upstream — BAM that generates depth bins), `genomics-sv-detection` (parallel — large structural variants), `spatial-cnv` (parallel — single-cell / spatial CNV via infercnvpy / Numbat), `genomics-variant-calling` (parallel — small variants on the same BAM)
