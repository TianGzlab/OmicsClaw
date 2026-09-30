---
name: genomics-variant-annotation
description: Load when summarising functional impact of an annotated variant CSV — per-IMPACT counts (HIGH
  / MODERATE / LOW / MODIFIER), top consequences, gene-affected count. Skip when input is a raw VCF (convert
  with `bcftools +split-vep` first); calling raw variants (use genomics-variant-calling); filtering VCFs
  (use genomics-vcf-operations).
trigger: variant annotation, VEP, snpEff, ANNOVAR, functional effect
tags:
- genomics
- annotation
- vep
- snpeff
- annovar
- consequence
- impact
---

# genomics-variant-annotation

## When to use

The user has a CSV containing per-variant annotations (lowercase
columns `chrom`, `pos`, `ref`, `alt`, `consequence`, `impact`,
`gene`, optionally `cadd_phred`) — typically the output of running
VEP, snpEff, or ANNOVAR upstream and exporting the resulting VCF
to CSV (e.g. via `bcftools +split-vep`). This skill computes
per-IMPACT counts, top consequences, and the count of distinct
genes affected.

The script does NOT run VEP / snpEff / ANNOVAR, and does NOT
parse a raw VCF — it only reads CSV. For raw calling use
`genomics-variant-calling`; for VCF filtering use
`genomics-vcf-operations`.

## Inputs & Outputs

**Inputs**

- File types: `.csv`
- Accepts artifact `genomics.variant_table` (`csv`)

**Outputs**

- `tables/annotated_variants.csv`
- `tables/impact_distribution.csv`
- `report.md`
- `result.json`
- Produces artifact `genomics.annotated_variants` as `tables/annotated_variants.csv` (`csv`)

## Flow

1. Load CSV (`--input <annotated.csv>`) or generate a demo annotated CSV at `output_dir/demo_annotated_variants.csv` with `--n-variants` records (`variant_annotation.py`).
2. Read columns directly via `pd.read_csv` (`variant_annotation.py`) — no VCF / VEP / snpEff parser exists in this skill.
3. Aggregate per-IMPACT counts (`variant_annotation.py`); pick top-N consequences; count distinct genes touched.
4. Write `tables/annotated_variants.csv` (`variant_annotation.py`) + `tables/impact_distribution.csv` + `report.md` + `result.json`.

## Gotchas

- **CSV-only — no VCF parser exists.** `variant_annotation.py` is `pd.read_csv(input_path)`; passing a `.vcf` raises `ValueError("Could not parse input file: ...")`. Convert VCFs to CSV first with `bcftools +split-vep -d -f '%CHROM,%POS,%REF,%ALT,%CSQ\n'` and post-process to the required column names.
- **Required CSV columns are LOWERCASE.** Code reads `df["impact"]`, `df["consequence"]`, `df["gene"]`, and optionally `df["cadd_phred"]`. A CSV with `IMPACT` / `Consequence` / `Gene` raises `KeyError`.
- **`--input` REQUIRED unless `--demo`.** `variant_annotation.py` raises `ValueError("--input required when not using --demo")`; non-existent paths raise `FileNotFoundError`.
- **No annotator is invoked.** This skill consumes an already-annotated CSV — it does NOT run VEP / snpEff / ANNOVAR. Run an annotator upstream and convert its output to CSV.
- **CADD scoring is optional.** When `cadd_phred` is absent the report omits the CADD section; do NOT add a placeholder NaN column or the value-counts will mis-render.
- **Demo CSV uses fixed IMPACT proportions (~10% HIGH, 30% MODERATE, 50% LOW, 10% MODIFIER).** Useful for smoke tests; not biologically meaningful.

## Key CLI

```bash
# Demo
python skills/genomics/genomics-variant-annotation/variant_annotation.py --demo --output /tmp/anno_demo

# Real annotated CSV (lowercase columns)
python skills/genomics/genomics-variant-annotation/variant_annotation.py \
  --input my_annotations.csv --output results/
```

## See also

- `references/parameters.md` — every CLI flag
- `references/methodology.md` — VEP / snpEff / ANNOVAR field semantics, IMPACT taxonomy
- `references/output_contract.md` — `tables/annotated_variants.csv` + impact distribution
- Adjacent skills: `genomics-variant-calling` (upstream — produces raw VCF), `genomics-vcf-operations` (upstream — filtering / normalisation before annotation), `genomics-sv-detection` (parallel — structural variants), `genomics-phasing` (parallel — phasing analysis)

## Dependencies

Python packages this skill's script needs. They are not installed for you — check before a long run.

`numpy`, `pandas`
