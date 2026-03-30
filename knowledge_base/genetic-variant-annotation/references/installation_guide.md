# Genetic Variant Annotation Installation Guide

This guide provides detailed installation instructions for all tools and dependencies required for the genetic variant annotation workflow.

---

## Overview

The workflow requires:
1. **One annotation tool**: Ensembl VEP OR SNPEff (choose based on use case)
2. **Python environment**: Python 3.9+ with required packages
3. **Optional tools**: bcftools, tabix for VCF manipulation

---

## Core Annotation Tools

### Option 1: Ensembl VEP

**Recommended for:** Human clinical analysis, comprehensive clinical annotations, extensive pathogenicity predictions

#### Conda Installation (Recommended)

```bash
# Create dedicated environment
conda create -n vep python=3.10
conda activate vep

# Install VEP
conda install -c bioconda ensembl-vep

# Verify installation
vep --help
vep --version
```

#### Manual Installation via Git

```bash
# Clone repository
git clone https://github.com/Ensembl/ensembl-vep.git
cd ensembl-vep

# Run installer
perl INSTALL.pl

# Add to PATH
export PATH=$PATH:/path/to/ensembl-vep

# Verify
vep --help
```

#### Install VEP Cache (Required)

VEP requires genome annotation cache files for optimal performance:

```bash
# Human GRCh38 (current, recommended) - ~15-20 GB
vep_install -a c -s homo_sapiens -y GRCh38

# Human GRCh37 (legacy) - ~12-15 GB
vep_install -a c -s homo_sapiens -y GRCh37

# Mouse GRCm39 - ~8-10 GB
vep_install -a c -s mus_musculus -y GRCm39
```

**Cache location:** Default `~/.vep/`

To specify custom cache directory:
```bash
vep_install -a c -s homo_sapiens -y GRCh38 -c /custom/path/vep_cache
```

#### Install VEP Plugins (Optional but Recommended)

**CADD Scores:**
```bash
cd ~/.vep/Plugins
# Download CADD plugin (pre-installed with VEP)
# Download CADD data files from https://cadd.gs.washington.edu/download
wget https://krishna.gs.washington.edu/download/CADD/v1.6/GRCh38/whole_genome_SNVs.tsv.gz
wget https://krishna.gs.washington.edu/download/CADD/v1.6/GRCh38/whole_genome_SNVs.tsv.gz.tbi
```

**dbNSFP (Multiple Prediction Scores):**
```bash
cd ~/.vep/Plugins
# Download dbNSFP database
wget ftp://dbnsfp:dbnsfp@dbnsfp.softgenetics.com/dbNSFP4.4a.zip
unzip dbNSFP4.4a.zip
# Process for VEP (see dbNSFP documentation)
```

**REVEL Scores:**
```bash
cd ~/.vep/Plugins
wget https://sites.google.com/site/revelgenomics/downloads/revel_grch38.tsv.gz
tabix -s 1 -b 2 -e 2 revel_grch38.tsv.gz
```

**SpliceAI:**
```bash
cd ~/.vep/Plugins
wget https://github.com/Illumina/SpliceAI/raw/master/spliceai/annotations/spliceai_scores.raw.snv.hg38.vcf.gz
wget https://github.com/Illumina/SpliceAI/raw/master/spliceai/annotations/spliceai_scores.raw.indel.hg38.vcf.gz
```

---

### Option 2: SNPEff

**Recommended for:** Non-model organisms, quick analysis, limited computational resources, GATK integration

#### Conda Installation (Recommended)

```bash
# Install SNPEff
conda install -c bioconda snpeff

# Verify installation
snpEff -version
```

#### Manual Installation

```bash
# Download latest version
wget https://snpeff.blob.core.windows.net/versions/snpEff_latest_core.zip

# Extract
unzip snpEff_latest_core.zip
cd snpEff

# Test installation
java -jar snpEff.jar -version

# Add to PATH (optional)
export PATH=$PATH:/path/to/snpEff
```

#### Install SNPEff Database (Required)

```bash
# List available databases
snpEff databases | grep -i human
snpEff databases | grep -i GRCh38

# Download human GRCh38 database (~2-3 GB)
snpEff download GRCh38.105

# Download human GRCh37 database
snpEff download GRCh37.75

# Download for custom data directory
snpEff download -dataDir ~/.snpeff GRCh38.105

# Download mouse database
snpEff download GRCm39.105
```

**Database location:** Default `~/.snpeff/data/`

#### Install SnpSift (Companion Tool)

SnpSift is typically included with SNPEff installation. Verify:

```bash
SnpSift -version
```

If not available:
```bash
conda install -c bioconda snpsift
```

#### Download Additional Databases for SnpSift

**dbNSFP (for pathogenicity predictions):**
```bash
cd ~/.snpeff/data
wget ftp://dbnsfp:dbnsfp@dbnsfp.softgenetics.com/dbNSFP4.4a.zip
unzip dbNSFP4.4a.zip
# Use dbNSFP4.4a_variant.chr*.gz files
```

**ClinVar:**
```bash
cd ~/.snpeff/data
wget https://ftp.ncbi.nlm.nih.gov/pub/clinvar/vcf_GRCh38/clinvar.vcf.gz
wget https://ftp.ncbi.nlm.nih.gov/pub/clinvar/vcf_GRCh38/clinvar.vcf.gz.tbi
```

---

## Python Environment Setup

### Create Virtual Environment

```bash
# Using venv
python3 -m venv variant-annotation-env
source variant-annotation-env/bin/activate  # Linux/Mac
# or
variant-annotation-env\Scripts\activate  # Windows

# Using conda
conda create -n variant-annotation python=3.10
conda activate variant-annotation
```

### Install Required Python Packages

```bash
# Install all required packages
pip install pandas numpy plotnine plotnine-prism seaborn pysam cyvcf2 xlsxwriter openpyxl

# Or install individually
pip install pandas>=1.5.0        # Data manipulation
pip install numpy>=1.23.0         # Numerical operations
pip install plotnine>=0.12.0      # Grammar of Graphics plotting
pip install plotnine-prism>=0.1.0 # Prism themes
pip install seaborn>=0.12.0       # Statistical visualizations
pip install pysam>=0.21.0         # VCF/BAM parsing
pip install cyvcf2>=0.30.0        # Fast VCF parsing
pip install xlsxwriter>=3.1.0     # Excel export
pip install openpyxl>=3.1.0       # Excel manipulation
```

### Verify Python Installation

```python
# Test script
import sys
print(f"Python version: {sys.version}")

import pandas as pd
print(f"pandas: {pd.__version__}")

import plotnine
print(f"plotnine: {plotnine.__version__}")

import pysam
print(f"pysam: {pysam.__version__}")

import cyvcf2
print(f"cyvcf2: {cyvcf2.__version__}")

print("All packages installed successfully!")
```

---

## Optional Supporting Tools

### bcftools (VCF Manipulation)

```bash
# Conda installation
conda install -c bioconda bcftools

# Ubuntu/Debian
sudo apt-get install bcftools

# macOS
brew install bcftools

# Verify
bcftools --version
```

### tabix (VCF Indexing)

```bash
# Usually included with samtools/bcftools
conda install -c bioconda tabix

# Verify
tabix --version
```

### vcf-validator (VCF Validation)

```bash
# Conda installation
conda install -c bioconda vcftools

# Verify
vcf-validator --help
```

---

## Version Requirements

### Minimum Versions

- **Python:** 3.9+
- **Ensembl VEP:** Release 110+ (2023+)
- **SNPEff:** Version 5.1+ (2022+)
- **pandas:** 1.5.0+
- **plotnine:** 0.12.0+
- **pysam:** 0.21.0+
- **cyvcf2:** 0.30.0+

### Compatibility Notes

- VEP cache versions must match VEP software version
- SNPEff database versions should correspond to genome build
- Plugin databases should be updated at least annually

---

## Testing Your Installation

### Test VEP Installation

Create a test script: `test_vep_installation.py`

```python
from scripts.run_vep import check_vep_installation

try:
    check_vep_installation()
    print("✓ VEP installation verified")
except Exception as e:
    print(f"✗ VEP installation issue: {e}")
```

Run:
```bash
python test_vep_installation.py
```

### Test SNPEff Installation

Create a test script: `test_snpeff_installation.py`

```python
from scripts.run_snpeff import check_snpeff_installation

try:
    check_snpeff_installation()
    print("✓ SNPEff installation verified")
except Exception as e:
    print(f"✗ SNPEff installation issue: {e}")
```

Run:
```bash
python test_snpeff_installation.py
```

### Test Python Dependencies

Create a test script: `test_dependencies.py`

```python
from scripts.validate_vcf import test_dependencies

try:
    test_dependencies()
    print("✓ All Python dependencies installed")
except ImportError as e:
    print(f"✗ Missing dependency: {e}")
```

Run:
```bash
python test_dependencies.py
```

---

## Disk Space Requirements

### Minimum Space by Configuration

**VEP (Human GRCh38):**
- VEP software: ~500 MB
- GRCh38 cache: 15-20 GB
- Plugins (optional):
  - CADD: ~80 GB (whole genome)
  - dbNSFP: ~35 GB
  - REVEL: ~1 GB
  - SpliceAI: ~15 GB
- **Total minimum:** ~20 GB
- **Total with plugins:** ~150 GB

**SNPEff (Human GRCh38):**
- SNPEff software: ~250 MB
- GRCh38 database: 2-3 GB
- SnpSift databases (optional):
  - dbNSFP: ~35 GB
  - ClinVar: ~500 MB
- **Total minimum:** ~3 GB
- **Total with databases:** ~40 GB

---

## Memory Requirements

### Minimum RAM by Use Case

- **Small VCF (<10K variants):** 4 GB RAM
- **Exome (~100K variants):** 8 GB RAM
- **Whole genome (millions of variants):** 16-32 GB RAM
- **VEP with multiple forks (--fork 4):** Add 2-4 GB per fork

### Optimizing for Limited Memory

**VEP:**
```bash
# Reduce buffer size
vep --buffer_size 1000 --fork 2

# Process by chromosome
for chr in {1..22} X Y; do
    vep -i chr${chr}.vcf -o chr${chr}.vep.vcf
done
```

**SNPEff:**
```bash
# Increase Java heap size if needed
java -Xmx8g -jar snpEff.jar ann GRCh38.105 input.vcf
```

---

## Troubleshooting Installation

### VEP Issues

**"Cannot find cache"**
```bash
# Check cache location
ls ~/.vep/

# Reinstall cache
vep_install -a c -s homo_sapiens -y GRCh38
```

**"Perl module missing"**
```bash
# Install Perl modules via CPAN
cpan Archive::Zip DBI

# Or use conda environment
conda install -c bioconda perl-archive-zip perl-dbi
```

### SNPEff Issues

**"Cannot find database"**
```bash
# List databases
snpEff databases | grep GRCh38

# Download database
snpEff download GRCh38.105
```

**"Java heap space error"**
```bash
# Increase heap size
java -Xmx8g -jar snpEff.jar ann GRCh38.105 input.vcf
```

### Python Package Issues

**"Import Error" for packages**
```bash
# Verify pip installation
pip list | grep pandas

# Reinstall specific package
pip install --upgrade --force-reinstall pandas

# Check for version conflicts
pip check
```

---

## Updating Software

### Update VEP

```bash
# Conda
conda update ensembl-vep

# Git installation
cd ensembl-vep
git pull
perl INSTALL.pl --UPDATE
```

### Update SNPEff

```bash
# Conda
conda update snpeff

# Manual
# Download latest version and replace installation directory
```

### Update Python Packages

```bash
# Update all packages
pip install --upgrade pandas numpy plotnine seaborn pysam cyvcf2 xlsxwriter openpyxl

# Or update individually
pip install --upgrade pandas
```

---

## Additional Resources

- **VEP Installation Guide:** https://www.ensembl.org/info/docs/tools/vep/script/vep_download.html
- **SNPEff Installation Guide:** https://pcingola.github.io/SnpEff/download/
- **Conda Documentation:** https://docs.conda.io/
- **Python Virtual Environments:** https://docs.python.org/3/library/venv.html

---

**Last Updated:** 2026-01-28
