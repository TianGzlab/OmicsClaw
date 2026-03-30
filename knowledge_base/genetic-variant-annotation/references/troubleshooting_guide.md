# Variant Annotation Troubleshooting Guide

This document provides solutions to common problems encountered during variant annotation workflows.

---

## Installation Issues

### VEP Installation Fails

**Problem:** `conda install ensembl-vep` fails or times out

**Solutions:**

1. Update conda:
```bash
conda update -n base conda
```

2. Try mamba (faster resolver):
```bash
conda install mamba
mamba install -c bioconda ensembl-vep
```

3. Use specific version:
```bash
conda install -c bioconda ensembl-vep=110
```

4. Manual installation:
```bash
git clone https://github.com/Ensembl/ensembl-vep.git
cd ensembl-vep
perl INSTALL.pl
```

### SNPEff Installation Fails

**Problem:** SNPEff command not found after installation

**Solutions:**

1. Verify installation:
```bash
conda list | grep snpeff
```

2. Try alternative installation:
```bash
# Direct download
wget https://snpeff.blob.core.windows.net/versions/snpEff_latest_core.zip
unzip snpEff_latest_core.zip

# Run directly
java -jar snpEff/snpEff.jar -version
```

3. Add to PATH:
```bash
export PATH=$PATH:/path/to/snpEff/
```

---

## Cache/Database Issues

### VEP: "Cannot find cache"

**Problem:** VEP reports cache not found

**Diagnosis:**
```bash
# Check cache location
ls ~/.vep/

# Check what VEP is looking for
vep --help | grep -A 5 "cache"
```

**Solutions:**

1. Install cache if missing:
```bash
vep_install -a c -s homo_sapiens -y GRCh38
```

2. Specify correct cache directory:
```bash
vep --cache --dir_cache /path/to/vep/cache/
```

3. Check cache permissions:
```bash
chmod -R 755 ~/.vep/
```

### SNPEff: "Cannot find database"

**Problem:** SNPEff reports genome database not found

**Diagnosis:**
```bash
# List installed databases
snpEff databases | grep -i grch38

# Check data directory
ls ~/.snpeff/data/
```

**Solutions:**

1. Download database:
```bash
snpEff download GRCh38.105
```

2. List available databases:
```bash
snpEff databases | grep -i human
```

3. Specify correct data directory:
```bash
snpEff ann -dataDir /path/to/snpeff/data/ GRCh38.105 input.vcf
```

---

## Genome Build Mismatches

### Chromosome Naming Issues

**Problem:** "Chromosome chr1 not found" or "Chromosome 1 not found"

**Diagnosis:**
```bash
# Check VCF chromosome names
grep -v "^#" input.vcf | cut -f1 | sort -u | head

# Check reference chromosome names
grep "^>" reference.fa | head
```

**Common mismatches:**
- VCF: `1, 2, 3, ...` vs Reference: `chr1, chr2, chr3, ...`
- VCF: `chr1, chr2, ...` vs Reference: `1, 2, 3, ...`

**Solutions:**

1. Add "chr" prefix:
```bash
sed 's/^/chr/' input.vcf > input_chr.vcf
```

2. Remove "chr" prefix:
```bash
sed 's/^chr//' input.vcf > input_nochr.vcf
```

3. Use bcftools:
```bash
# Add chr
bcftools annotate --rename-chrs chr_name_mapping.txt input.vcf > output.vcf

# chr_name_mapping.txt:
# 1 chr1
# 2 chr2
# ...
```

### GRCh37 vs GRCh38 Mismatch

**Problem:** Annotations missing or incorrect due to genome build mismatch

**Diagnosis:**
```bash
# Check VCF build from header
grep "^##reference" input.vcf

# Check a known variant position
# rs429358 (APOE):
# GRCh37: chr19:45411941
# GRCh38: chr19:44908684
```

**Solution:**
1. Use correct annotation database matching VCF build

2. Liftover VCF to correct build:
```bash
# Using Picard
java -jar picard.jar LiftoverVcf \
    I=input.grch37.vcf \
    O=output.grch38.vcf \
    CHAIN=grch37_to_grch38.chain \
    REJECT=rejected.vcf \
    R=grch38.fa
```

3. Use UCSC liftOver:
```bash
# Convert VCF to BED
# Liftover BED
# Convert back to VCF
```

---

## Annotation Quality Issues

### Low Annotation Rate

**Problem:** Many variants have no consequence annotation

**Diagnosis:**
```bash
# Count annotated vs unannotated variants
# VEP
grep -c "CSQ=" output.vcf

# SNPEff
grep -c "ANN=" output.vcf
```

**Common Causes:**

1. **Genome build mismatch**
   - Solution: Use matching genome build

2. **VCF in non-coding regions**
   - Expected for whole genome sequencing
   - Solution: Focus on coding variants for exome

3. **Poor quality variants**
   - Solution: Filter by QUAL score first

4. **Chromosome naming issues**
   - Solution: Fix chromosome names (see above)

### Missing Pathogenicity Scores

**Problem:** SIFT, PolyPhen, CADD, REVEL fields are empty

**VEP Solutions:**

1. Install plugins:
```bash
# CADD
vep --plugin CADD,/path/to/CADD.tsv.gz

# dbNSFP (includes SIFT, PolyPhen, etc.)
vep --plugin dbNSFP,/path/to/dbNSFP.txt.gz,ALL

# REVEL
vep --plugin REVEL,/path/to/revel.tsv.gz
```

2. Download plugin data:
```bash
# CADD
wget https://krishna.gs.washington.edu/download/CADD/v1.6/GRCh38/whole_genome_SNVs.tsv.gz
wget https://krishna.gs.washington.edu/download/CADD/v1.6/GRCh38/whole_genome_SNVs.tsv.gz.tbi
```

**SNPEff Solutions:**

1. Use SnpSift to add annotations:
```bash
SnpSift dbnsfp \
    -db /path/to/dbNSFP4.4a.txt.gz \
    -f SIFT_pred,Polyphen2_HVAR_pred,CADD_phred,REVEL_score \
    input.vcf > annotated.vcf
```

### Missing ClinVar Annotations

**Problem:** No ClinVar data in output

**VEP Solution:**
```bash
# Add ClinVar as custom annotation
vep --custom ClinVar.vcf.gz,ClinVar,vcf,exact,0,CLNSIG,CLNDN,CLNREVSTAT \
    input.vcf -o output.vcf
```

**SNPEff/SnpSift Solution:**
```bash
# First annotate with SNPEff
snpEff ann GRCh38.105 input.vcf | \

# Then add ClinVar with SnpSift
SnpSift annotate ClinVar.vcf.gz /dev/stdin > output.vcf
```

**Download ClinVar:**
```bash
# GRCh38
wget https://ftp.ncbi.nlm.nih.gov/pub/clinvar/vcf_GRCh38/clinvar.vcf.gz
wget https://ftp.ncbi.nlm.nih.gov/pub/clinvar/vcf_GRCh38/clinvar.vcf.gz.tbi
```

---

## Performance Issues

### VEP Running Very Slowly

**Problem:** VEP takes hours for medium-sized VCF

**Solutions:**

1. Use cache instead of database:
```bash
# Slow
vep --database ...

# Fast
vep --cache --dir_cache ~/.vep/
```

2. Increase parallelization:
```bash
vep --fork 8  # Use 8 CPU cores
```

3. Increase buffer size:
```bash
vep --buffer_size 10000  # More memory but faster
```

4. Process by chromosome:
```bash
for chr in {1..22} X Y; do
    bcftools view -r chr${chr} input.vcf | \
        vep --cache --fork 4 > chr${chr}.vep.vcf &
done
wait

# Merge
bcftools concat chr*.vep.vcf > merged.vcf
```

### Memory Errors

**Problem:** "Out of memory" or killed process

**Solutions:**

1. Reduce buffer size (VEP):
```bash
vep --buffer_size 1000  # Default is 5000
```

2. Reduce parallelization:
```bash
vep --fork 2  # Instead of 8
```

3. Increase Java heap (SNPEff):
```bash
java -Xmx16g -jar snpEff.jar ann ...
```

4. Split VCF by chromosome:
```bash
# Process each chromosome separately
bcftools view -r chr1 input.vcf > chr1.vcf
```

5. Filter VCF first:
```bash
# Keep only PASS variants
bcftools view -f PASS input.vcf > pass_only.vcf

# Or by quality
bcftools view -i 'QUAL>30' input.vcf > high_qual.vcf
```

---

## Output Parsing Issues

### Cannot Parse CSQ/ANN Field

**Problem:** Python/R script fails to parse VEP CSQ or SNPEff ANN field

**Diagnosis:**
```bash
# Check CSQ format in header
grep "^##INFO=<ID=CSQ" output.vcf

# Check example CSQ entry
grep -v "^#" output.vcf | grep "CSQ=" | head -1 | cut -f8
```

**Solutions:**

1. Use provided parser scripts:
```python
from scripts.parse_vep_output import parse_vep_vcf
df = parse_vep_vcf("output.vep.vcf.gz")
```

2. Extract format from header:
```python
import cyvcf2
vcf = cyvcf2.VCF("output.vcf")
csq_info = vcf.get_header_type('CSQ')
format_str = csq_info['Description'].split('Format:')[1].strip()
fields = format_str.split('|')
```

3. Use bcftools to extract fields:
```bash
bcftools query -f '%CHROM\t%POS\t%REF\t%ALT\t%INFO/CSQ\n' output.vcf
```

### Multiallelic Variants

**Problem:** Difficult to parse variants with multiple ALT alleles

**Solution:**
```bash
# Split multiallelic variants
bcftools norm -m- input.vcf > split.vcf

# Each ALT allele becomes separate record
```

---

## Variant Classification Issues

### All Variants Classified as VUS

**Problem:** ACMG classification returns mostly VUS

**Common Causes:**

1. **Missing evidence:**
   - No population frequency data
   - No pathogenicity predictions
   - No ClinVar annotations

**Solution:** Ensure all data sources are included

2. **Incorrect thresholds:**
   - Too stringent criteria
   - Not enough supporting evidence

**Solution:** Review and adjust criteria

3. **Gene-specific issues:**
   - LOF not established for gene
   - Gene has many benign LOF variants

**Solution:** Check gene-disease associations

### High Impact Variants Not Prioritized

**Problem:** Known pathogenic variants ranked low

**Diagnosis:**
```bash
# Check if variant has annotations
grep "VARIANT_ID" annotated.vcf
```

**Solutions:**

1. Check if ClinVar is included
2. Verify population frequency is loaded
3. Ensure pathogenicity scores are present
4. Adjust prioritization weights

---

## File Format Issues

### VCF Format Errors

**Problem:** VCF fails validation

**Diagnosis:**
```bash
# Validate VCF
vcf-validator input.vcf

# Or
bcftools view input.vcf > /dev/null
```

**Common Errors:**

1. **Missing header:**
```bash
# Add minimal header
bcftools view -h reference.vcf > header.txt
cat header.txt variants.txt > fixed.vcf
```

2. **Invalid characters:**
```bash
# Check for tabs vs spaces
cat -A input.vcf | head
```

3. **Unsorted variants:**
```bash
# Sort VCF
bcftools sort input.vcf > sorted.vcf
```

4. **Missing fields:**
```bash
# Fix with bcftools
bcftools +fill-tags input.vcf > fixed.vcf
```

### BGZ Compression Issues

**Problem:** "Not a valid BGZF file"

**Solution:**
```bash
# Decompress and recompress
gunzip input.vcf.gz
bgzip input.vcf
tabix -p vcf input.vcf.gz
```

---

## Python Package Issues

### Import Errors

**Problem:** `ModuleNotFoundError: No module named 'cyvcf2'`

**Solution:**
```bash
# Install missing package
pip install cyvcf2

# Or all required packages
pip install pandas numpy cyvcf2 pysam plotnine plotnine-prism xlsxwriter
```

### Plotnine Errors

**Problem:** Plot generation fails

**Solution:**
```bash
# Update plotnine
pip install --upgrade plotnine plotnine-prism

# Install all dependencies
pip install pandas matplotlib numpy
```

---

## Getting Help

### Collecting Information for Bug Reports

When reporting issues, include:

1. **Tool versions:**
```bash
vep --help | head
snpEff -version
python --version
```

2. **Command used:**
```bash
# Full command with all parameters
```

3. **Input/output examples:**
```bash
# First few lines of VCF
head -20 input.vcf

# Error messages
# Full error output
```

4. **System information:**
```bash
uname -a
free -h  # Memory
df -h    # Disk space
```

### Resources

- **VEP Support:** https://www.ensembl.org/Help/Contact
- **SNPEff GitHub:** https://github.com/pcingola/SnpEff/issues
- **Biostars:** https://www.biostars.org/
- **SEQanswers:** http://seqanswers.com/

---

## Quick Reference: Common Solutions

| Problem | Quick Solution |
|---------|---------------|
| VEP slow | Use `--cache --fork 4` |
| Missing annotations | Check genome build match |
| Chromosome not found | Fix chr naming (add/remove "chr") |
| Out of memory | Reduce `--buffer_size` or `--fork` |
| Missing scores | Install VEP plugins or use SnpSift |
| Cannot parse output | Use provided parser scripts |
| VCF format error | Validate with `bcftools view` |
| Package import error | `pip install` missing packages |
