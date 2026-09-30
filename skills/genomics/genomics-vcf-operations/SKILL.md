---
name: genomics-vcf-operations
description: Load when summarising / filtering a VCF — variant classification (SNP / MNP / INS / DEL /
  COMPLEX), Ti/Tv ratio, QUAL / DP threshold filtering, INFO-field parsing. Skip when the input is a BAM
  (use genomics-variant-calling); adding functional annotations (use genomics-variant-annotation).
trigger: VCF, bcftools, variant filter, merge VCF
tags:
- genomics
- vcf
- bcftools
- filter
- ti-tv
- snv
- indel
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

**Inputs**

- File types: `.vcf`
- VCF structure: `##fileformat`; columns: `#CHROM`, `POS`, `ID`, `REF`, `ALT`, `QUAL`, `FILTER`, `INFO`

**Outputs**

- `tables/variants.csv`
- `filtered.vcf`
- `report.md`
- `result.json`
- Produces artifact `genomics.filtered_variants` as `filtered.vcf` (`vcf`)

## Flow

1. Load plain/gzip VCF (`--input <file.vcf[.gz]>`) or generate a demo VCF at `output_dir/demo.vcf`.
2. Parse records; classify each ALT into SNP / MNP / INS / DEL / COMPLEX.
3. Apply `--min-qual` and `--min-dp` filters; always materialise the declared normalized `filtered.vcf` artifact (zero thresholds are pass-through).
4. Compute Ti/Tv on biallelic SNPs; aggregate per-chromosome counts.
5. Write `tables/variants.csv` (`genomics_vcf_operations.py`) + `report.md` + `result.json`.

## Gotchas

- **`--input` REQUIRED unless `--demo`.** `genomics_vcf_operations.py` raises `ValueError("--input required when not using --demo")`; non-existent paths raise `FileNotFoundError`.
- **Plain `.vcf` plus gzip/bzip2/xz-compressed VCF are supported.** Unknown compression codecs are rejected by the content probe rather than passed to the parser.
- **`filtered.vcf` is always emitted.** With the default zero thresholds it is a normalized pass-through; positive `--min-qual` / `--min-dp` values reduce the retained records.
- **Multi-allelic rows are scored per-ALT but counted as one VCF line.** Per-allele Ti/Tv is computed correctly, but downstream tools that count "rows" will under-count vs `bcftools view`. Pre-normalise (`bcftools norm -m -`) for row-by-allele math.
- **DP is read from `INFO/DP` only.** Per-sample `FORMAT/DP` (genotype-level) is ignored — single-sample VCFs that only put DP in FORMAT will see `DP=NA`, and `--min-dp` will drop them all.
- **Demo VCF is a minimal SNV+indel set with random QUAL/DP.** Useful for smoke tests; not biologically meaningful.

## Key CLI

```bash
# Demo
python skills/genomics/genomics-vcf-operations/genomics_vcf_operations.py --demo --output /tmp/vcf_demo

# Filter at QUAL>=30 and DP>=10
python skills/genomics/genomics-vcf-operations/genomics_vcf_operations.py \
  --input cohort.vcf --output results/ \
  --min-qual 30 --min-dp 10
```

## See also

- `references/parameters.md` — every CLI flag
- `references/methodology.md` — variant-type rules, Ti/Tv interpretation
- `references/output_contract.md` — `tables/variants.csv` + `filtered.vcf`
- Adjacent skills: `genomics-variant-calling` (upstream — produces the VCF), `genomics-variant-annotation` (downstream — adds gene / consequence / impact), `genomics-sv-detection` (parallel — SVs instead of small variants), `genomics-phasing` (parallel — phased VCF analysis)

## Dependencies

Python packages this skill's script needs. They are not installed for you — check before a long run.

`numpy`, `pandas`
