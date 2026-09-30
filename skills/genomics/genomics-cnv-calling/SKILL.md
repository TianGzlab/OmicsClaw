---
name: genomics-cnv-calling
description: Load when calling CNV segments via CBS-style segmentation on a bin-level log2-ratio CSV from
  exome / WGS coverage — emits per-segment 5-class CN state (`amplification` / `gain` / `neutral` / `loss`
  / `deep_deletion`), per-chromosome summary, genome-fraction-altered. Skip when working with single-cell
  / spatial CNV (use spatial-cnv).
trigger: CNV, copy number, amplification, deletion, CNVkit
tags:
- genomics
- cnv
- copy-number
- cbs
- segmentation
- cnvkit
- gatk-gcnv
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

**Inputs**

- File types: `.csv`

**Outputs**

- `tables/cnv_per_chromosome.csv`
- `tables/cnv_segments.csv`
- `report.md`
- `result.json`

## Flow

1. Load bin CSV (`--input <bins.csv>`) or generate a demo bin file at `output_dir/demo_cnv_bins.csv` (`genomics_cnv_calling.py`).
2. Read columns via `pd.read_csv` (`genomics_cnv_calling.py`); group by `df["chrom"]` and segment per chromosome.
3. Classify each segment via `np.select` (`genomics_cnv_calling.py`) into one of `amplification` / `gain` / `neutral` / `loss` / `deep_deletion` based on mean log2.
4. Aggregate per-chromosome counts + genome-fraction-altered.
5. Write `tables/cnv_segments.csv` (`genomics_cnv_calling.py`) + `tables/cnv_per_chromosome.csv` + `report.md` + `result.json`.

## Gotchas

- **Required CSV column is `chrom`, NOT `chromosome`.** Code reads `df["chrom"]` at `genomics_cnv_calling.py`. CNVkit `cnr` files have a `chromosome` column — rename to `chrom` first (`pd.read_csv(...).rename(columns={"chromosome": "chrom"})`). Other required columns are `start`, `end`, `log2_ratio`.
- **`cn_state` has 5 classes, NOT 3.** `genomics_cnv_calling.py` produces `amplification` (log2 > 1.0), `gain` (> 0.3), `neutral`, `loss` (< -0.3), `deep_deletion` (< -1.0). The summary reports `n_gains` and `n_losses` as **inclusive** of `amplification` / `deep_deletion`; inspect `n_amplifications` / `n_deep_deletions` for the high-magnitude subset.
- **No bin generator is invoked.** This skill consumes a bin-level log2-ratio CSV — it does NOT run CNVkit / GATK gCNV / Control-FREEC. Run them upstream and feed the bin file here.
- **`--input` REQUIRED unless `--demo`.** `genomics_cnv_calling.py` raises `ValueError("--input required when not using --demo")`; non-existent paths raise `FileNotFoundError`.
- **`--alpha` controls segmentation aggressiveness.** Lower values (e.g. 0.001) yield fewer / larger segments; higher values (0.1) yield more / smaller. Default 0.01 is suitable for clean exome / WGS data; for noisy panels consider `--alpha 0.001`.
- **Classification thresholds are hard-coded.** ±0.3 (gain/loss) and ±1.0 (amplification/deep_deletion) at `genomics_cnv_calling.py` — no CLI flag to tune. For tumour-purity-corrected calling, scale the input log2 ratios upstream.

## Key CLI

```bash
# Demo
python skills/genomics/genomics-cnv-calling/genomics_cnv_calling.py --demo --output /tmp/cnv_demo

# Real CNVkit bins (rename `chromosome` → `chrom` first)
python skills/genomics/genomics-cnv-calling/genomics_cnv_calling.py \
  --input sample_renamed.cnr.csv --output results/ --alpha 0.01

# Stricter segmentation for noisy panel data
python skills/genomics/genomics-cnv-calling/genomics_cnv_calling.py \
  --input panel.cnr.csv --output results/ --alpha 0.001
```

## See also

- `references/parameters.md` — every CLI flag
- `references/methodology.md` — segmentation algorithm, 5-class threshold rationale
- `references/output_contract.md` — `tables/cnv_segments.csv` schema
- Adjacent skills: `genomics-alignment` (upstream — BAM that generates depth bins), `genomics-sv-detection` (parallel — large structural variants), `spatial-cnv` (parallel — single-cell / spatial CNV via infercnvpy / Numbat), `genomics-variant-calling` (parallel — small variants on the same BAM)

## Dependencies

Python packages this skill's script needs. They are not installed for you — check before a long run.

`numpy`, `pandas`
