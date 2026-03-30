# SNPEff Best Practices

This document provides detailed guidelines for using SNPEff variant annotation tool.

---

## Installation

### Conda Installation (Recommended)

```bash
# Install SNPEff
conda install -c bioconda snpeff

# Verify installation
snpEff -version
```

### Manual Installation

```bash
# Download latest version
wget https://snpeff.blob.core.windows.net/versions/snpEff_latest_core.zip

# Extract
unzip snpEff_latest_core.zip

# Test
java -jar snpEff/snpEff.jar -version
```

---

## Database Setup

SNPEff requires genome databases for annotation.

### List Available Databases

```bash
snpEff databases | grep -i human
snpEff databases | grep -i GRCh38
```

Common human databases:
- `GRCh38.105`: Ensembl release 105, GRCh38
- `GRCh37.75`: Ensembl release 75, GRCh37
- `hg38`: UCSC hg38
- `hg19`: UCSC hg19

### Download Database

```bash
# Download GRCh38
snpEff download GRCh38.105

# Download GRCh37
snpEff download GRCh37.75

# Specify custom data directory
snpEff download -dataDir /path/to/data GRCh38.105
```

### Database Disk Space

- Human genome: ~2-3 GB
- Mouse genome: ~1-2 GB

---

## Common Usage Patterns

### Basic Annotation

```bash
snpEff ann GRCh38.105 input.vcf > output.vcf
```

### With Statistics

```bash
snpEff ann \
    -stats output_stats.html \
    GRCh38.105 \
    input.vcf > output.vcf
```

### Recommended Clinical Configuration

```bash
snpEff ann \
    -dataDir ~/.snpeff \
    -stats snpeff_stats.html \
    -csvStats snpeff_stats.csv \
    -canon \
    -hgvs \
    -lof \
    -no-downstream \
    -no-upstream \
    -no-intergenic \
    GRCh38.105 \
    input.vcf > output.vcf
```

---

## Key Parameters

### Output and Statistics

- `-stats file.html`: Generate comprehensive HTML statistics report with plots showing variant distribution, effects by impact, functional class, and genomic region. **Recommended for QC.**
- `-csvStats file.csv`: Generate CSV format statistics for programmatic analysis
- `-v`: Verbose mode - prints detailed progress and warnings
- `-q`: Quiet mode - suppress all output except errors

### Annotation Options

- `-canon`: Use only canonical transcripts (one representative transcript per gene). **Recommended for clinical reporting** to reduce redundancy and focus on primary isoforms.
- `-hgvs`: Add HGVS nomenclature (e.g., "c.123A>G", "p.Lys41Arg"). **Essential for clinical reporting** as it provides standardized variant descriptions.
- `-lof`: Predict high-confidence loss-of-function variants using stringent criteria (stop-gained, frameshift affecting >50% of protein, splice-disrupting, initiator codon variants). Adds LOF and NMD (nonsense-mediated decay) tags.
- `-oicr`: Use OICR tag format instead of default ANN format
- `-sequenceOntology`: Use Sequence Ontology terms for consequence types (default, recommended)
- `-formatEff`: Use old EFF format (deprecated, avoid unless required for legacy tools)

### Filtering Options

These parameters reduce output to relevant variants by excluding low-information regions:

- `-no-downstream`: Don't annotate downstream gene variants (typically 5kb after gene end). Reduces noise for coding-focused analysis.
- `-no-upstream`: Don't annotate upstream gene variants (typically 5kb before gene start). Useful for exome/targeted sequencing.
- `-no-intergenic`: Don't annotate intergenic variants (variants between genes). **Recommended for exome analysis** where intergenic variants are not of interest.
- `-no-intron`: Don't annotate intronic variants. Use cautiously - some intronic variants affect splicing.
- `-no-utr`: Don't annotate UTR (untranslated region) variants. May miss regulatory variants.

**Typical exome configuration:** `-no-downstream -no-upstream -no-intergenic` (keeps coding and regulatory variants)

### Performance

- `-t N`: Use N threads for parallel processing. Note: Multi-threading support varies by operation; most benefit is during database loading.

### Data Directory

- `-dataDir /path/to/data`: Specify custom location for SNPEff databases (default: `~/.snpeff/data/`)

### Input/Output Formats

- **Input formats:** VCF (default), BED
- **Output formats:** VCF (default), GATK, BED, TXT

### Cancer-Specific

- `-cancer`: Enable cancer-specific annotations
- `-cancerSamples file.txt`: Specify cancer sample mapping file

---

## ANN Field Format

SNPEff adds annotations to the INFO field with the ANN key:

```
##INFO=<ID=ANN,Number=.,Type=String,Description="Functional annotations: 'Allele | Annotation | Annotation_Impact | Gene_Name | Gene_ID | Feature_Type | Feature_ID | Transcript_BioType | Rank | HGVS.c | HGVS.p | cDNA.pos / cDNA.length | CDS.pos / CDS.length | AA.pos / AA.length | Distance | ERRORS / WARNINGS / INFO' ">
```

### Example ANN Entry

```
T|missense_variant|MODERATE|BRCA1|ENSG00000012048|transcript|ENST00000357654|protein_coding|10/23|c.1234A>T|p.Lys412Tyr|1234/5592|1234/5643|412/1863||
```

### Field Positions

1. Allele
2. Annotation (consequence)
3. Annotation_Impact (HIGH, MODERATE, LOW, MODIFIER)
4. Gene_Name
5. Gene_ID
6. Feature_Type
7. Feature_ID (transcript ID)
8. Transcript_BioType
9. Rank (exon/intron rank)
10. HGVS.c (coding sequence)
11. HGVS.p (protein sequence)
12. cDNA_position/length
13. CDS_position/length
14. Protein_position/length
15. Distance to feature
16. Errors/Warnings/Info

---

## SnpSift for Additional Annotations

SnpSift is a companion tool for filtering and annotating VCF files.

### Add dbNSFP Annotations

```bash
SnpSift dbnsfp \
    -db /path/to/dbNSFP4.4a.txt.gz \
    -f SIFT_pred,Polyphen2_HVAR_pred,CADD_phred,REVEL_score \
    input.vcf > annotated.vcf
```

### Add ClinVar Annotations

```bash
SnpSift annotate \
    ClinVar.vcf.gz \
    input.vcf > annotated.vcf
```

### Filter Variants

```bash
# High impact variants only
SnpSift filter "(ANN[*].IMPACT = 'HIGH')" input.vcf > high_impact.vcf

# Rare variants (gnomAD AF < 0.01)
SnpSift filter "(dbNSFP_gnomAD_genomes_AF < 0.01)" input.vcf > rare.vcf
```

---

## Best Practices

### 1. Use Canonical Transcripts

For clinical reporting:

```bash
snpEff ann -canon GRCh38.105 input.vcf > output.vcf
```

### 2. Add HGVS Nomenclature

Essential for clinical reporting:

```bash
snpEff ann -hgvs GRCh38.105 input.vcf > output.vcf
```

### 3. Enable LOF Prediction

Identifies high-confidence loss-of-function variants:

```bash
snpEff ann -lof GRCh38.105 input.vcf > output.vcf
```

LOF criteria:
- Stop-gained variants
- Frameshift variants affecting >50% of protein
- Splice-site disrupting variants
- Initiator codon variants

### 4. Filter Non-Coding Variants for Exome

```bash
snpEff ann \
    -no-downstream \
    -no-upstream \
    -no-intergenic \
    GRCh38.105 \
    input.vcf > output.vcf
```

### 5. Generate Statistics Report

Always generate HTML report for QC:

```bash
snpEff ann -stats report.html GRCh38.105 input.vcf > output.vcf
```

Report includes:
- Variant type distribution
- Effects by impact
- Effects by functional class
- Effects by genomic region
- Base changes
- Quality metrics

### 6. Combine with SnpSift

```bash
# Annotate with SNPEff
snpEff ann -hgvs -lof GRCh38.105 input.vcf | \

# Add dbNSFP scores
SnpSift dbnsfp -db dbNSFP.txt.gz \
    -f SIFT_pred,Polyphen2_HVAR_pred,CADD_phred | \

# Filter high impact
SnpSift filter "(ANN[*].IMPACT = 'HIGH') | (ANN[*].IMPACT = 'MODERATE')" \
    > filtered.vcf
```

### 7. Match Database Version to VCF

Ensure genome build compatibility:
- VCF with GRCh38 → Use GRCh38.* database
- VCF with hg19/GRCh37 → Use GRCh37.* database

---

## Cancer Analysis with SNPEff

### Annotate Somatic Variants

```bash
snpEff ann \
    -cancer \
    -cancerSamples cancer_samples.txt \
    GRCh38.105 \
    tumor.vcf > tumor.annotated.vcf
```

### Add COSMIC Annotations

```bash
SnpSift annotate \
    CosmicCodingMuts.vcf.gz \
    input.vcf > cosmic_annotated.vcf
```

---

## Troubleshooting

### "Cannot find database"

**Cause:** Database not downloaded

**Solution:**
```bash
# List available databases
snpEff databases | grep GRCh38

# Download database
snpEff download GRCh38.105
```

### "Chromosome not found"

**Cause:** Chromosome naming mismatch (chr1 vs 1)

**Solution:**
- Check VCF chromosome names: `grep -v "^#" input.vcf | cut -f1 | sort -u`
- SNPEff handles both "chr1" and "1" formats automatically
- If issues persist, use alternative database (e.g., hg38 instead of GRCh38)

### Empty ANN Field

**Cause:** No overlapping annotations or genome build mismatch

**Solution:**
- Verify genome build matches VCF
- Check that variants are in coding regions
- Use `-v` for verbose output to debug

### Very Large Output Files

**Cause:** Annotating all transcripts and intergenic regions

**Solution:**
```bash
# Filter to coding variants only
snpEff ann \
    -no-intergenic \
    -no-downstream \
    -no-upstream \
    GRCh38.105 input.vcf > output.vcf
```

### Statistics Show Low Annotation Rate

**Causes:**
- Genome build mismatch
- Poor quality variants
- Non-coding variants (expected for WGS)

**Investigation:**
```bash
# Check variant distribution in stats HTML
firefox snpeff_stats.html

# Check example variants
head -n 1000 output.vcf | grep "ANN="
```

---

## Performance Optimization

### For Large VCFs

```bash
# Process by chromosome
for chr in {1..22} X Y; do
    grep "^${chr}\t" input.vcf | snpEff ann GRCh38.105 /dev/stdin > chr${chr}.vcf
done

# Merge results
bcftools concat chr*.vcf -o merged.vcf
```

### Memory Settings

```bash
# Increase Java heap size (default: 1GB)
java -Xmx8g -jar snpEff.jar ann GRCh38.105 input.vcf > output.vcf
```

---

## Comparison with VEP

| Feature | SNPEff | VEP |
|---------|--------|-----|
| Speed | Faster | Slower (Perl) |
| Organisms | 38,000+ | ~100 well-annotated |
| Installation | Simpler | More complex |
| Output Format | ANN field (standard) | CSQ field |
| Database Size | Smaller (2-3 GB) | Larger (15-20 GB) |
| Clinical Databases | Via SnpSift | Native integration |
| Plugins | Limited | Extensive |
| Updates | Less frequent | Quarterly |
| GATK Integration | Excellent | Good |

**Use SNPEff when:**
- Working with non-model organisms
- Speed is priority
- Simple setup needed
- GATK pipeline integration

**Use VEP when:**
- Comprehensive human clinical annotation
- Need latest databases
- Extensive plugin ecosystem required

---

## References

- SNPEff Documentation: https://pcingola.github.io/SnpEff/
- SNPEff Paper: Cingolani P, et al. (2012) Fly 6(2):80-92
- SnpSift Documentation: https://pcingola.github.io/SnpEff/ss_introduction/
