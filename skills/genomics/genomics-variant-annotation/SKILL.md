---
name: genomics-variant-annotation
description: Load when summarising functional impact of an annotated variant CSV — per-IMPACT counts (HIGH / MODERATE / LOW / MODIFIER), top consequences, gene-affected count. Skip when input is a raw VCF (convert with `bcftools +split-vep` first), when calling raw variants (use `genomics-variant-calling`), or filtering VCFs (use `genomics-vcf-operations`).
version: 0.5.0
author: OmicsClaw
license: MIT
tags:
- genomics
- annotation
- vep
- snpeff
- annovar
- consequence
- impact
requires:
- pandas
- numpy
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

| Input | Format | Required |
|---|---|---|
| Annotated CSV | `.csv` with lowercase columns `chrom`, `pos`, `ref`, `alt`, `consequence`, `impact`, `gene` (and optionally `cadd_phred`) | yes (unless `--demo`) |

| Output | Path | Notes |
|---|---|---|
| Annotated table | `tables/annotated_variants.csv` | per-variant copy of the input CSV |
| Impact distribution | `tables/impact_distribution.csv` | counts per IMPACT class |
| Report | `report.md` + `result.json` | `result.json["data"]["top_consequences"]` mirrors top-N consequence counts |

## Flow

1. Load CSV (`--input <annotated.csv>`) or generate a demo annotated CSV at `output_dir/demo_annotated_variants.csv` with `--n-variants` records (`variant_annotation.py:227`).
2. Read columns directly via `pd.read_csv` (`variant_annotation.py:356`) — no VCF / VEP / snpEff parser exists in this skill.
3. Aggregate per-IMPACT counts (`variant_annotation.py:240`); pick top-N consequences (`:241`); count distinct genes touched (`:252`).
4. Write `tables/annotated_variants.csv` (`variant_annotation.py:366`) + `tables/impact_distribution.csv` (`:377`) + `report.md` + `result.json` (`:383`).

## Gotchas

- **CSV-only — no VCF parser exists.** `variant_annotation.py:356` is `pd.read_csv(input_path)`; passing a `.vcf` raises `ValueError("Could not parse input file: ...")` at `variant_annotation.py:358`. Convert VCFs to CSV first with `bcftools +split-vep -d -f '%CHROM,%POS,%REF,%ALT,%CSQ\n'` and post-process to the required column names.
- **Required CSV columns are LOWERCASE.** Code reads `df["impact"]` (`:240`), `df["consequence"]` (`:241`), `df["gene"]` (`:252`), and optionally `df["cadd_phred"]` (`:271`). A CSV with `IMPACT` / `Consequence` / `Gene` raises `KeyError`.
- **`--input` REQUIRED unless `--demo`.** `variant_annotation.py:348` raises `ValueError("--input required when not using --demo")`; non-existent paths raise `FileNotFoundError` at `:351`.
- **No annotator is invoked.** This skill consumes an already-annotated CSV — it does NOT run VEP / snpEff / ANNOVAR. Run an annotator upstream and convert its output to CSV.
- **CADD scoring is optional.** When `cadd_phred` is absent the report omits the CADD section; do NOT add a placeholder NaN column or the value-counts will mis-render.
- **Demo CSV uses fixed IMPACT proportions (~10% HIGH, 30% MODERATE, 50% LOW, 10% MODIFIER).** Useful for orchestrator smoke tests; not biologically meaningful.

## Key CLI

```bash
# Demo
python omicsclaw.py run genomics-variant-annotation --demo --output /tmp/anno_demo

# Real annotated CSV (lowercase columns)
python omicsclaw.py run genomics-variant-annotation \
  --input my_annotations.csv --output results/
```

## See also

- `references/parameters.md` — every CLI flag
- `references/methodology.md` — VEP / snpEff / ANNOVAR field semantics, IMPACT taxonomy
- `references/output_contract.md` — `tables/annotated_variants.csv` + impact distribution
- Adjacent skills: `genomics-variant-calling` (upstream — produces raw VCF), `genomics-vcf-operations` (upstream — filtering / normalisation before annotation), `genomics-sv-detection` (parallel — structural variants), `genomics-phasing` (parallel — phasing analysis)
