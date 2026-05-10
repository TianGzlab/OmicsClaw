---
name: genomics-vcf-operations
description: Load when summarising / filtering a VCF — variant classification (SNP / MNP / INS / DEL / COMPLEX), Ti/Tv ratio, QUAL / DP threshold filtering, INFO-field parsing. Skip when the input is a BAM (use `genomics-variant-calling` upstream first) or when adding functional annotations (use `genomics-variant-annotation`).
version: 0.5.0
author: OmicsClaw
license: MIT
tags:
- genomics
- vcf
- bcftools
- filter
- ti-tv
- snv
- indel
requires:
- pandas
- numpy
---

# genomics-vcf-operations

## When to use

The user has a VCF (cohort, single-sample, or merged) and wants:
classify variants by type (SNP / MNP / INS / DEL / COMPLEX),
compute Ti/Tv on biallelic SNPs, optionally apply hard QUAL / DP
filters, and emit per-chromosome counts. This skill mirrors a
subset of `bcftools stats` + a simple QUAL/DP filter pass — pure
Python, no `bcftools` required.

For variant calling itself (BAM → VCF) see `genomics-variant-calling`;
for functional impact (gene / consequence / impact) use
`genomics-variant-annotation`.

## Inputs & Outputs

| Input | Format | Required |
|---|---|---|
| Variants | `.vcf` (uncompressed; `.vcf.gz` not auto-decompressed) | yes (unless `--demo`) |

| Output | Path | Notes |
|---|---|---|
| Variant table | `tables/variants.csv` | per-variant CHROM/POS/REF/ALT/QUAL/DP/type |
| Filtered VCF | `output_dir/filtered.vcf` | only when `--min-qual > 0` or `--min-dp > 0` |
| Report | `report.md` + `result.json` | always; `result.json["data"]["variants_per_chrom"]` mirrors per-chrom counts |

## Flow

1. Load VCF (`--input <file.vcf>`) or generate a demo VCF at `output_dir/demo.vcf` (`genomics_vcf_operations.py:305`).
2. Parse records; classify each ALT into SNP / MNP / INS / DEL / COMPLEX.
3. Apply `--min-qual` and `--min-dp` filters; write `filtered.vcf` if either threshold is active (`:329`).
4. Compute Ti/Tv on biallelic SNPs; aggregate per-chromosome counts.
5. Write `tables/variants.csv` (`genomics_vcf_operations.py:325`) + `report.md` + `result.json` (`:341`).

## Gotchas

- **`--input` REQUIRED unless `--demo`.** `genomics_vcf_operations.py:310` raises `ValueError("--input required when not using --demo")`; non-existent paths raise `FileNotFoundError` at `:313`.
- **`.vcf.gz` is not auto-decompressed.** The script reads plain text; gzipped VCFs raise an unintelligible parse error rather than a clean `bgzip` hint. Pre-decompress with `bgzip -d` (or `gunzip -k`) first.
- **Filtered VCF only emitted when a filter is active.** `--min-qual 0` and `--min-dp 0` (defaults at `:296-297`) keep every record and SKIP the `filtered.vcf` write. Pass at least one threshold > 0 to get the filtered file.
- **Multi-allelic rows are scored per-ALT but counted as one VCF line.** Per-allele Ti/Tv is computed correctly, but downstream tools that count "rows" will under-count vs `bcftools view`. Pre-normalise (`bcftools norm -m -`) for row-by-allele math.
- **DP is read from `INFO/DP` only.** Per-sample `FORMAT/DP` (genotype-level) is ignored — single-sample VCFs that only put DP in FORMAT will see `DP=NA`, and `--min-dp` will drop them all.
- **Demo VCF is a minimal SNV+indel set with random QUAL/DP.** Useful for orchestrator smoke tests; not biologically meaningful.

## Key CLI

```bash
# Demo
python omicsclaw.py run genomics-vcf-operations --demo --output /tmp/vcf_demo

# Filter at QUAL>=30 and DP>=10
python omicsclaw.py run genomics-vcf-operations \
  --input cohort.vcf --output results/ \
  --min-qual 30 --min-dp 10
```

## See also

- `references/parameters.md` — every CLI flag
- `references/methodology.md` — variant-type rules, Ti/Tv interpretation
- `references/output_contract.md` — `tables/variants.csv` + `filtered.vcf`
- Adjacent skills: `genomics-variant-calling` (upstream — produces the VCF), `genomics-variant-annotation` (downstream — adds gene / consequence / impact), `genomics-sv-detection` (parallel — SVs instead of small variants), `genomics-phasing` (parallel — phased VCF analysis)
