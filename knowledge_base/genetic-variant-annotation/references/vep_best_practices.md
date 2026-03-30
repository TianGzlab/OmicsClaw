# Ensembl VEP Best Practices

This document provides detailed guidelines for using Ensembl Variant Effect Predictor (VEP) in variant annotation workflows.

---

## Installation

### Conda Installation (Recommended)

```bash
# Create dedicated environment
conda create -n vep python=3.10
conda activate vep

# Install VEP
conda install -c bioconda ensembl-vep

# Verify installation
vep --help
```

### Manual Installation

```bash
# Clone repository
git clone https://github.com/Ensembl/ensembl-vep.git
cd ensembl-vep

# Run installer
perl INSTALL.pl
```

---

## Cache Setup

VEP requires genome annotation caches for optimal performance. Using caches is **strongly recommended** over database queries.

### Installing Human Caches

```bash
# GRCh38 (current, recommended)
vep_install -a c -s homo_sapiens -y GRCh38

# GRCh37 (legacy)
vep_install -a c -s homo_sapiens -y GRCh37
```

### Cache Location

Default: `~/.vep/`

Specify custom location:
```bash
vep -i input.vcf --cache --dir_cache /path/to/cache
```

### Cache Disk Space Requirements

- Human GRCh38: ~15-20 GB
- Human GRCh37: ~12-15 GB
- Mouse GRCm39: ~8-10 GB

---

## Common Usage Patterns

### Basic Annotation

```bash
vep -i input.vcf \
    -o output.vcf \
    --cache \
    --assembly GRCh38 \
    --vcf \
    --force_overwrite
```

### Comprehensive Annotation (--everything)

```bash
vep -i input.vcf \
    -o output.vcf \
    --cache \
    --assembly GRCh38 \
    --everything \
    --vcf \
    --force_overwrite \
    --fork 4
```

**--everything includes:**
- Transcript consequences with HGVS notation
- Protein domains (Pfam, InterPro)
- Regulatory features
- Existing variant IDs (dbSNP, COSMIC)
- Population allele frequencies
- SIFT and PolyPhen predictions

### Clinical Annotation

```bash
vep -i input.vcf \
    -o output.vcf \
    --cache \
    --assembly GRCh38 \
    --everything \
    --vcf \
    --fork 4 \
    --plugin CADD,/path/to/CADD.tsv.gz \
    --plugin REVEL,/path/to/revel_scores.tsv.gz \
    --custom ClinVar.vcf.gz,ClinVar,vcf,exact,0,CLNSIG,CLNREVSTAT,CLNDN \
    --max_af gnomAD
```

---

## Key Parameters

### Performance

- `--fork N`: Use N CPU cores for parallel processing (recommended: 4-8). Speeds up annotation significantly but increases memory usage. Each fork processes variants independently.
- `--buffer_size N`: Number of variants to read at a time (default: 5000). Higher values = faster processing but more memory. Reduce if memory is limited.
- `--cache`: Use local cache files (fast, 10-100x faster than database queries). **Strongly recommended** for production use.
- `--database`: Query Ensembl database directly (slow, requires internet, but always current). Only use if cache unavailable.

### Assembly and Genome

- `--assembly GRCh38`: Specify genome assembly (GRCh37 or GRCh38 for human, GRCm38 or GRCm39 for mouse). **Must match VCF chromosome naming.**
- `--species homo_sapiens`: Specify species (default: human). Required for non-human organisms.

### Output Formats

- `--vcf`: VCF output format (recommended for downstream tools)
- `--json`: JSON output format (for programmatic parsing)
- `--tab`: Tab-delimited output (human-readable tables)
- `--force_overwrite`: Overwrite existing output files without prompting

### Annotation Completeness

- `--everything`: Include all available annotations - transcript consequences, HGVS notation, protein domains, regulatory features, existing variant IDs, population frequencies, SIFT/PolyPhen predictions. **Recommended starting point for most analyses.**
- `--pick`: Report only one consequence per variant (most severe). Reduces output size for clinical reporting.
- `--per_gene`: Report one consequence per gene
- `--flag_pick`: Flag picked consequences without filtering others out

### Transcript Selection

- `--coding_only`: Report coding variants only (excludes intronic, intergenic)
- `--canonical`: Flag canonical transcripts (one representative per gene)
- `--mane`: Flag MANE Select transcripts (human only, gold-standard clinical transcripts)
- `--pick_allele`: Pick one consequence per allele

### Population Frequencies

- `--check_frequency`: Check allele frequencies in reference populations
- `--max_af gnomAD`: Add maximum gnomAD allele frequency across all populations. Essential for variant filtering.
- `--af`: Add individual population frequencies (AFR, AMR, EAS, NFE, etc.)
- `--af_1kg`: Include 1000 Genomes frequencies
- `--af_esp`: Include ESP6500 frequencies

### Clinical Annotations

- `--check_existing`: Check for known variants in databases (dbSNP, COSMIC, ESP, ExAC)
- `--pubmed`: Report PubMed IDs associated with variants

### Regulatory Elements

- `--regulatory`: Include regulatory region annotations (promoters, enhancers, transcription factor binding sites)
- `--cell_type`: Limit regulatory annotations to specific cell types (e.g., "HUVEC" for endothelial)

---

## Plugins

VEP functionality can be extended with plugins. Useful clinical plugins:

### CADD Scores

```bash
--plugin CADD,/path/to/CADD_GRCh38_v1.6.tsv.gz
```

Download: https://cadd.gs.washington.edu/download

### dbNSFP (Multiple Prediction Scores)

```bash
--plugin dbNSFP,/path/to/dbNSFP4.4a_grch38.gz,ALL
```

Includes: SIFT, PolyPhen, MutationTaster, FATHMM, GERP++, phyl oP, PhastCons

Download: https://sites.google.com/site/jpopgen/dbNSFP

### REVEL Scores

```bash
--plugin REVEL,/path/to/revel_grch38.tsv.gz
```

Download: https://sites.google.com/site/revelgenomics/downloads

### SpliceAI

```bash
--plugin SpliceAI,snv=/path/to/spliceai_scores.raw.snv.hg38.vcf.gz,indel=/path/to/spliceai_scores.raw.indel.hg38.vcf.gz
```

### LOFTEE (Loss-of-Function)

```bash
--plugin LoF,loftee_path:/path/to/loftee
```

---

## Custom Annotations

### Adding ClinVar

```bash
--custom ClinVar.vcf.gz,ClinVar,vcf,exact,0,CLNSIG,CLNDN,CLNREVSTAT
```

Format: `file,short_name,file_type,match_type,force_coord_shift,fields`

### Adding COSMIC

```bash
--custom CosmicCodingMuts.vcf.gz,COSMIC,vcf,exact,0,CNT
```

---

## VCF Output Format

VEP adds annotations to the INFO field with the CSQ key:

```
##INFO=<ID=CSQ,Number=.,Type=String,Description="Consequence annotations from Ensembl VEP. Format: Allele|Consequence|IMPACT|SYMBOL|Gene|Feature_type|Feature|BIOTYPE|...">
```

### Parsing CSQ Field

The CSQ format is defined in the VCF header. Use the header to parse fields programmatically.

Example CSQ entry:
```
T|missense_variant|MODERATE|BRCA1|ENSG00000012048|Transcript|ENST00000357654|protein_coding|10/23|...
```

---

## Best Practices

### 1. Always Use Caches

- 10-100x faster than database queries
- Consistent results
- Doesn't require internet connection

### 2. Use --fork for Large Files

```bash
--fork 4  # For standard workstation
--fork 8  # For HPC systems
```

### 3. Filter to Canonical Transcripts

For clinical reporting, focus on canonical transcripts:

```bash
--canonical --pick
```

Or use MANE Select transcripts (human only):
```bash
--mane --pick
```

### 4. Include Population Frequencies

Essential for filtering rare variants:

```bash
--max_af gnomAD --af gnomAD
```

### 5. Add Pathogenicity Predictions

For clinical analysis, include:
- CADD (integrated score)
- REVEL (missense variants)
- dbNSFP (multiple predictors)
- SpliceAI (splicing variants)

### 6. Validate Input VCF

Always validate VCF format before running VEP:

```bash
vcf-validator input.vcf
# or
bcftools view -h input.vcf >/dev/null
```

### 7. Check Genome Build

Ensure VCF and cache genome builds match:
- VCF chr1 (GRCh38) vs VEP --assembly GRCh38 ✓
- VCF chr1 (hg19) vs VEP --assembly GRCh38 ✗

### 8. Monitor Memory Usage

For very large VCFs:
- Reduce `--buffer_size`
- Process by chromosome
- Use `--fork` cautiously (more forks = more memory)

---

## Troubleshooting

### VEP Runs Very Slowly

**Cause:** Using database queries instead of cache

**Solution:**
```bash
# Install cache
vep_install -a c -s homo_sapiens -y GRCh38

# Use cache in command
vep --cache --dir_cache ~/.vep/
```

### "Cannot find cache"

**Cause:** Cache not installed or wrong path

**Solution:**
```bash
# Check cache location
ls ~/.vep/

# Specify correct path
vep --cache --dir_cache /path/to/vep/cache
```

### "Chromosome not found in cache"

**Cause:** Genome build mismatch (hg19 vs GRCh38)

**Solution:**
- Check VCF header contigs
- Ensure `--assembly` matches VCF build
- Consider using `--liftover` for conversion

### Memory Errors

**Solution:**
```bash
# Reduce buffer size
--buffer_size 1000

# Reduce fork count
--fork 2

# Process by chromosome
for chr in {1..22} X Y; do
    vep -i chr${chr}.vcf -o chr${chr}.vep.vcf --cache --fork 4
done
```

### Missing Pathogenicity Scores

**Cause:** Plugins not installed or wrong path

**Solution:**
```bash
# Verify plugin files exist
ls /path/to/CADD.tsv.gz
ls /path/to/CADD.tsv.gz.tbi  # Index required

# Use correct path in command
--plugin CADD,/path/to/CADD.tsv.gz
```

---

## Version Compatibility

- VEP 110+: Compatible with Ensembl 110+ (2023+)
- Cache versions must match VEP version
- Plugin database versions should be recent (within 1 year)

### Updating VEP

```bash
# Conda
conda update ensembl-vep

# Git
cd ensembl-vep
git pull
perl INSTALL.pl --UPDATE
```

---

## References

- VEP Documentation: https://www.ensembl.org/info/docs/tools/vep/index.html
- VEP Tutorial: https://www.ensembl.org/info/docs/tools/vep/script/vep_tutorial.html
- VEP Paper: McLaren W, et al. (2016) Genome Biology 17:122


---
