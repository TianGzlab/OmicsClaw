---
name: genomics-variant-calling
description: >-
  Germline and somatic variant calling (SNVs, Indels) using GATK HaplotypeCaller,
  Mutect2, DeepVariant, or FreeBayes. Includes GVCF workflow, VQSR, and hard filtering.
version: 0.1.0
author: OmicsClaw
license: MIT
tags: [genomics, variant-calling, GATK, DeepVariant, FreeBayes, VQSR]
metadata:
  omicsclaw:
    domain: genomics
    emoji: "🔎"
    trigger_keywords: [variant calling, SNV, indel, GATK, DeepVariant, FreeBayes, Mutect2, VQSR]
---

# 🔎 Variant Calling

Germline and somatic small variant calling (SNVs, Indels). Supports GATK HaplotypeCaller, Mutect2, DeepVariant, and FreeBayes.

## Core Capabilities

1. **GATK HaplotypeCaller**: Gold standard for germline variant calling with GVCF cohort workflow
2. **GATK Mutect2**: Somatic variant calling for tumor-normal pairs
3. **DeepVariant**: Deep learning-based variant caller (CNN)
4. **FreeBayes**: Bayesian haplotype-based caller
5. **VQSR / Hard Filtering**: Machine learning and rule-based variant quality filtering

## CLI Reference

```bash
python omicsclaw.py run genomics-variant-calling --demo
python omicsclaw.py run genomics-variant-calling --input <data.bam> --output <dir>
```

## Algorithm / Methodology

### GATK Single-Sample Calling

```bash
# Basic HaplotypeCaller
gatk HaplotypeCaller \
    -R reference.fa \
    -I sample.bam \
    -O sample.vcf.gz

# With standard annotations
gatk HaplotypeCaller \
    -R reference.fa \
    -I sample.bam \
    -O sample.vcf.gz \
    -A Coverage -A QualByDepth -A FisherStrand -A StrandOddsRatio \
    -A MappingQualityRankSumTest -A ReadPosRankSumTest

# Target intervals (exome/panel)
gatk HaplotypeCaller \
    -R reference.fa \
    -I sample.bam \
    -L targets.interval_list \
    -O sample.vcf.gz
```

### GVCF Workflow (Recommended for Cohorts)

```bash
# Step 1: Generate GVCFs per sample
gatk HaplotypeCaller \
    -R reference.fa \
    -I sample.bam \
    -O sample.g.vcf.gz \
    -ERC GVCF

# Step 2: Combine GVCFs (GenomicsDBImport)
gatk GenomicsDBImport \
    --genomicsdb-workspace-path genomicsdb \
    --sample-name-map sample_map.txt \
    -L intervals.interval_list

# Step 3: Joint Genotyping
gatk GenotypeGVCFs \
    -R reference.fa \
    -V gendb://genomicsdb \
    -O cohort.vcf.gz
```

### VQSR (Variant Quality Score Recalibration)

Machine learning-based filtering using known variant sites. Requires many variants (WGS preferred).

```bash
# Build SNP model
gatk VariantRecalibrator \
    -R reference.fa -V cohort.vcf.gz \
    --resource:hapmap,known=false,training=true,truth=true,prior=15.0 hapmap.vcf.gz \
    --resource:omni,known=false,training=true,truth=false,prior=12.0 omni.vcf.gz \
    --resource:1000G,known=false,training=true,truth=false,prior=10.0 1000G.vcf.gz \
    --resource:dbsnp,known=true,training=false,truth=false,prior=2.0 dbsnp.vcf.gz \
    -an QD -an MQ -an MQRankSum -an ReadPosRankSum -an FS -an SOR \
    -mode SNP -O snp.recal --tranches-file snp.tranches

# Apply SNP filter
gatk ApplyVQSR \
    -R reference.fa -V cohort.vcf.gz -O cohort.snp_recal.vcf.gz \
    --recal-file snp.recal --tranches-file snp.tranches \
    --truth-sensitivity-filter-level 99.5 -mode SNP
```

### Hard Filtering (When VQSR Not Suitable)

For small datasets, exomes, or single samples where VQSR fails.

```bash
# Filter SNPs
gatk VariantFiltration -R reference.fa -V snps.vcf.gz -O snps.filtered.vcf.gz \
    --filter-expression "QD < 2.0" --filter-name "QD2" \
    --filter-expression "FS > 60.0" --filter-name "FS60" \
    --filter-expression "MQ < 40.0" --filter-name "MQ40" \
    --filter-expression "MQRankSum < -12.5" --filter-name "MQRankSum-12.5" \
    --filter-expression "ReadPosRankSum < -8.0" --filter-name "ReadPosRankSum-8" \
    --filter-expression "SOR > 3.0" --filter-name "SOR3"

# Filter Indels
gatk VariantFiltration -R reference.fa -V indels.vcf.gz -O indels.filtered.vcf.gz \
    --filter-expression "QD < 2.0" --filter-name "QD2" \
    --filter-expression "FS > 200.0" --filter-name "FS200" \
    --filter-expression "ReadPosRankSum < -20.0" --filter-name "ReadPosRankSum-20" \
    --filter-expression "SOR > 10.0" --filter-name "SOR10"
```

### BQSR (Base Quality Score Recalibration)

```bash
# Step 1: BaseRecalibrator
gatk BaseRecalibrator -R reference.fa -I sample.bam \
    --known-sites dbsnp.vcf.gz --known-sites known_indels.vcf.gz \
    -O recal_data.table

# Step 2: ApplyBQSR
gatk ApplyBQSR -R reference.fa -I sample.bam \
    --bqsr-recal-file recal_data.table -O sample.recal.bam
```

### Complete Single-Sample Pipeline

```bash
#!/bin/bash
SAMPLE=$1; REF=reference.fa
DBSNP=dbsnp.vcf.gz; KNOWN_INDELS=known_indels.vcf.gz

# BQSR
gatk BaseRecalibrator -R $REF -I ${SAMPLE}.bam \
    --known-sites $DBSNP --known-sites $KNOWN_INDELS -O ${SAMPLE}.recal.table
gatk ApplyBQSR -R $REF -I ${SAMPLE}.bam \
    --bqsr-recal-file ${SAMPLE}.recal.table -O ${SAMPLE}.recal.bam

# Call variants
gatk HaplotypeCaller -R $REF -I ${SAMPLE}.recal.bam -O ${SAMPLE}.g.vcf.gz -ERC GVCF

# Genotype
gatk GenotypeGVCFs -R $REF -V ${SAMPLE}.g.vcf.gz -O ${SAMPLE}.vcf.gz

# Hard filter
gatk VariantFiltration -R $REF -V ${SAMPLE}.vcf.gz -O ${SAMPLE}.filtered.vcf.gz \
    --filter-expression "QD < 2.0" --filter-name "LowQD" \
    --filter-expression "FS > 60.0" --filter-name "HighFS" \
    --filter-expression "MQ < 40.0" --filter-name "LowMQ"
```

## Key Annotations Reference

| Annotation | Description | Good Values |
|------------|-------------|-------------|
| QD | Quality by Depth | > 2.0 |
| FS | Fisher Strand | < 60 (SNP), < 200 (Indel) |
| SOR | Strand Odds Ratio | < 3 (SNP), < 10 (Indel) |
| MQ | Mapping Quality | > 40 |
| MQRankSum | MQ Rank Sum Test | > -12.5 |
| ReadPosRankSum | Read Position Rank Sum | > -8.0 (SNP), > -20.0 (Indel) |

## Resource Files

| Resource | Use |
|----------|-----|
| dbSNP | Known variants (prior=2.0) |
| HapMap | Training/truth SNPs (prior=15.0) |
| Omni | Training SNPs (prior=12.0) |
| 1000G SNPs | Training SNPs (prior=10.0) |
| Mills Indels | Training/truth indels (prior=12.0) |

## Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--method` | `gatk` | gatk, deepvariant, freebayes |
| `--mode` | `germline` | germline or somatic |
| `--reference` | required | Reference genome FASTA |
| `--intervals` | none | Target intervals (BED/interval_list) |

## Why This Exists

- **Without it**: Raw alignments contain spurious mismatch artifacts from sequencing chemistry or mapping errors
- **With it**: Machine learning and Bayesian models distinguish true biology from technical noise
- **Why OmicsClaw**: Standardizes the notoriously complex GATK/DeepVariant execution graphs

## Workflow

1. **Calculate**: Accumulate pileups and local haplotype graphs.
2. **Execute**: Calculate likelihood of variant states per locus.
3. **Assess**: Perform VQSR machine learning or hard filtering.
4. **Generate**: Output structural VCF catalogs.
5. **Report**: Tabulate key transition/transversion metrics.

## Example Queries

- "Call germline traits from this bam using GATK"
- "Use Mutect2 for somatic variants on tumor-normal pairs"

## Output Structure

```
output_directory/
├── report.md
├── result.json
├── variants.vcf.gz
├── figures/
│   └── vqsr_tranches.png
├── tables/
│   └── variant_quality_summary.csv
└── reproducibility/
    ├── commands.sh
    ├── environment.yml
    └── checksums.sha256
```

## Safety

- **Local-first**: Strict offline processing without external upload.
- **Disclaimer**: Requires OmicsClaw reporting structures and disclaimers.
- **Audit trail**: Hyperparameters and operational flow states are logged fully.

## Integration with Orchestrator

**Trigger conditions**:
- Automatically invoked dynamically based on tool metadata and user intent matching.

**Chaining partners**:
- `align` — Upstream BAM mapping
- `annotation` — Downstream consequence indexing

## Version Compatibility

Reference examples tested with: GATK 4.5+, bcftools 1.19+

## Dependencies

**Required**: GATK 4.x, samtools, bcftools
**Optional**: DeepVariant, FreeBayes

## Citations

- [GATK](https://gatk.broadinstitute.org/) — McKenna et al., Genome Research 2010
- [DeepVariant](https://doi.org/10.1038/nbt.4235) — Poplin et al., Nature Biotechnology 2018
- [FreeBayes](https://github.com/freebayes/freebayes) — Garrison & Marth, arXiv 2012

## Related Skills

- `genomics-qc` — QC before variant calling
- `align` — Read alignment upstream
- `vcf-ops` — Post-calling VCF manipulation
- `variant-annotate` — Variant annotation downstream
