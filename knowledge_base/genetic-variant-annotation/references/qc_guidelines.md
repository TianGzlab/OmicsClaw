# Quality Control Guidelines for Variant Annotation

This document provides detailed QC checkpoints and expected metrics for each stage of variant annotation.

---

## 1. VCF Validation (Step 1)

### Critical Checkpoints

✅ **Format validation**
- VCF passes format validation with no parsing errors
- Conforms to VCF 4.2 specification
- All required fields present (CHROM, POS, ID, REF, ALT, QUAL, FILTER, INFO)

✅ **Reference genome matching**
- All contigs in VCF header match reference genome
- Contig names consistent (e.g., "chr1" vs "1")
- Variant positions within contig boundaries
- No off-by-one coordinate errors

✅ **Variant integrity**
- No duplicate variant positions
- REF alleles match reference genome
- ALT alleles are valid nucleotide sequences
- Multiallelic sites properly formatted

✅ **Sample data quality**
- FILTER fields consistent across variants
- Genotype calls complete (minimal missing data)
- FORMAT fields properly defined in header
- Phase information valid if present

### Expected Metrics

| Metric | Whole Genome | Whole Exome | Notes |
|--------|--------------|-------------|-------|
| **Ti/Tv ratio** | 2.0 - 2.1 | 2.8 - 3.0 | Transition/transversion ratio |
| **Het/Hom ratio** | 1.5 - 2.0 | 1.5 - 2.0 | Heterozygous/homozygous ratio |
| **Average QUAL** | > 30 | > 30 | Variant quality score |
| **PASS rate** | > 90% | > 95% | % variants passing filters |
| **Indel rate** | 10-15% | 5-10% | % indels vs SNVs |

### Red Flags

❌ **Poor variant quality:**
- Ti/Tv < 1.5 (suggests low-quality variant calls)
- Very high indel rate (> 20% of variants)
- Mean QUAL < 20
- High proportion of multiallelic sites (> 10%)

❌ **Reference mismatch:**
- Many REF alleles don't match reference genome
- Variants outside contig boundaries
- Inconsistent chromosome naming

❌ **Data integrity issues:**
- Large number of missing genotypes (> 10%)
- Inconsistent ploidy
- FILTER fields not defined in header
- Sample names duplicated or missing

### Common VCF Issues and Fixes

| Issue | Cause | Solution |
|-------|-------|----------|
| "Invalid VCF header" | Malformed header lines | Fix ##INFO, ##FORMAT, ##contig definitions |
| "Chromosome not found" | Chr naming mismatch (chr1 vs 1) | Use bcftools annotate to rename contigs |
| "Duplicate positions" | Same variant listed multiple times | Deduplicate with bcftools norm -d |
| "REF doesn't match genome" | Wrong reference genome | Re-call variants with correct reference |
| "Missing genotype data" | Incomplete variant calling | Filter variants with high missingness |

---

## 2. Annotation Completeness (Steps 3-4)

### Critical Checkpoints

✅ **Annotation success**
- 100% of variants successfully annotated
- No skipped variants in output
- VEP/SNPEff completed without errors
- Output VCF/file size reasonable (not empty)

✅ **Consequence assignment**
- Every variant has at least one consequence
- Consequence terms valid (from Sequence Ontology)
- IMPACT assigned (HIGH/MODERATE/LOW/MODIFIER)
- Transcript information present for coding variants

✅ **Gene annotation**
- Gene symbols present for coding/regulatory variants
- Ensembl Gene IDs assigned
- Transcript IDs correspond to correct genome build
- Canonical transcripts marked (if requested)

✅ **Supplementary annotations**
- Population frequencies present (if plugin enabled)
- Pathogenicity scores populated (for missense variants)
- Clinical annotations loaded (ClinVar, COSMIC)
- HGVS notation generated correctly

### Expected Metrics

| Metric | Whole Genome | Whole Exome | Notes |
|--------|--------------|-------------|-------|
| **Annotation rate** | 100% | 100% | All variants annotated |
| **Coding variants** | 1-2% | 40-60% | % coding consequences |
| **Gene assignment** | 30-50% | > 95% | % variants with gene symbol |
| **HIGH impact** | 0.01-0.05% | 0.1-0.5% | Stop-gain, frameshift, etc. |
| **MODERATE impact** | 0.5-1% | 10-20% | Missense, inframe indels |
| **ClinVar matches** | 0.01-0.1% | 0.1-1% | Known clinical variants |

### Red Flags

❌ **Annotation failure:**
- Large number of variants with no consequence assigned
- No gene symbols for exome variants (> 50% intergenic)
- All consequences are "intergenic_variant" in exome
- Empty or truncated output file

❌ **Genome build mismatch:**
- Most exome variants annotated as intergenic (should be coding)
- Very few gene hits in targeted sequencing
- ClinVar matches absent for common clinical panels
- Check: VCF genome build vs annotation database build

❌ **Plugin/database issues:**
- All pathogenicity scores missing (SIFT, PolyPhen)
- No population frequencies (gnomAD, 1000G)
- ClinVar annotations absent
- Check: Plugins installed and databases downloaded

### VEP-Specific Checks

**Cache vs API mode:**
- Cache mode: 100-1000x faster, requires 15-20 GB disk
- API mode: Very slow for large VCFs, no disk space needed
- Recommendation: Always use cache for > 1000 variants

**Plugin verification:**
```bash
# Check installed VEP plugins
vep --list_plugins

# Expected plugins for clinical analysis:
# - CADD
# - dbNSFP
# - REVEL
# - SpliceAI
# - Mastermind
```

**Common VEP errors:**
```bash
# "Cache directory not found"
# Solution: Download cache
vep_install -a cf -s homo_sapiens -y GRCh38

# "Plugin failed: CADD"
# Solution: Download CADD scores
cd $VEP_CACHE_DIR
wget https://krishna.gs.washington.edu/download/CADD/v1.6/GRCh38/whole_genome_SNVs.tsv.gz
```

### SNPEff-Specific Checks

**Database verification:**
```bash
# List available databases
snpEff databases | grep -i GRCh38

# Expected output for human:
# GRCh38.105 (Ensembl release 105)
# GRCh38.p13 (RefSeq annotation)
```

**Annotation field validation:**
- ANN field present in INFO column
- ANN subfields: Allele|Annotation|Impact|Gene_Name|...
- LOF field present (if loss-of-function plugin enabled)
- NMD field present (if nonsense-mediated decay enabled)

**Common SNPEff errors:**
```bash
# "Genome 'GRCh38' not found"
# Solution: Download SNPEff database
snpEff download -v GRCh38.105

# "Cannot read FASTA file"
# Solution: SNPEff doesn't need FASTA (only database)
# Remove -ref option if present
```

---

## 3. Filtering Results (Step 5)

### Critical Checkpoints

✅ **Appropriate stringency**
- Filtering criteria match use case
- Not over-filtering (losing true positives)
- Not under-filtering (too many variants)
- Balance sensitivity vs specificity

✅ **Consequence filtering**
- Impact thresholds appropriate
- Critical consequence types included
- Synonymous variants excluded (or included if needed)

✅ **Frequency filtering**
- Population frequency threshold appropriate for disease model
- Rare disease: AF < 0.01 (dominant) or < 0.05 (recessive)
- Common disease: More permissive thresholds
- Missing frequencies handled correctly

✅ **Quality filtering**
- Variant quality (QUAL) threshold applied
- Depth of coverage (DP) considered
- Allele balance checked for heterozygous variants
- PASS filter applied if appropriate

### Expected Metrics After Filtering

| Filter Level | Whole Exome | Whole Genome | Clinical Sample |
|-------------|-------------|--------------|-----------------|
| **All variants** | 20,000-40,000 | 3-5 million | Variable |
| **Coding variants** | 8,000-15,000 | 50,000-100,000 | 100-5,000 |
| **HIGH/MODERATE impact** | 5,000-10,000 | 30,000-60,000 | 50-2,000 |
| **Rare (AF < 0.01)** | 500-2,000 | 10,000-30,000 | 20-500 |
| **Rare + HIGH impact** | 10-50 | 100-500 | 1-20 |
| **Prioritized pathogenic** | 1-20 | 10-100 | 0-10 |

### Decision Point: Adjust Filtering Thresholds

**Too many variants (> 1000 after filtering):**
- ✅ Decrease allele frequency threshold (0.01 → 0.001)
- ✅ Increase pathogenicity score threshold (CADD > 25, REVEL > 0.7)
- ✅ Require multiple pathogenicity predictions to agree
- ✅ Filter to HIGH impact only (exclude MODERATE)
- ✅ Include only ClinVar Pathogenic/Likely pathogenic

**Too few variants (< 5 after filtering):**
- ✅ Increase allele frequency threshold (0.01 → 0.05)
- ✅ Decrease pathogenicity score threshold (CADD > 15, REVEL > 0.3)
- ✅ Include MODERATE impact variants
- ✅ Include variants of uncertain significance (VUS)
- ✅ Check if variants were lost in earlier QC steps

**No candidate variants:**
- ⚠️ Review original VCF quality (Ti/Tv ratio, variant counts)
- ⚠️ Verify genome build matches (VCF vs annotation database)
- ⚠️ Check if disease gene is in targeted region (for panels)
- ⚠️ Consider expanding to VUS or lower impact variants
- ⚠️ Review inheritance model and filtering assumptions

### Use Case-Specific Filtering Strategies

**1. Clinical Diagnostics (Rare Mendelian Disease)**

```
Stringent filtering:
- Impact: HIGH or MODERATE only
- Frequency: gnomAD AF < 0.01 (dominant) or < 0.05 (recessive)
- Pathogenicity: CADD > 20 OR REVEL > 0.5 OR ClinVar P/LP
- Quality: QUAL > 30, DP > 10, AB 0.3-0.7 (het)
- Consequences: Loss-of-function, missense, splice site

Expected output: 1-20 candidate variants per patient
```

**2. Cancer Genomics (Somatic Variants)**

```
Cancer-specific filtering:
- Impact: HIGH, MODERATE, or known cancer hotspot
- Frequency: Not present in germline (gnomAD AF < 0.001)
- Databases: COSMIC mutations, OncoKB variants
- Quality: Tumor VAF > 0.05, normal VAF < 0.02
- Genes: Cancer gene census, driver genes

Expected output: 1-10 driver mutations per tumor
```

**3. Population Genetics (Research)**

```
Permissive filtering:
- Impact: All impact levels
- Frequency: AF < 0.05 or no frequency filter
- Quality: QUAL > 20, DP > 5
- Consequences: All coding variants

Expected output: 500-5,000 variants per sample
```

**4. Pharmacogenomics**

```
PGx-specific filtering:
- Genes: PGx gene list (CYP2D6, CYP2C19, TPMT, etc.)
- Impact: All impacts (including synonymous if functional)
- Frequency: No frequency filter (common variants important)
- Databases: PharmGKB clinical annotations
- Include: Star alleles, structural variants

Expected output: 10-100 PGx variants per sample
```

---

## 4. Gene-Level Summary (Step 6)

### Critical Checkpoints

✅ **Gene aggregation**
- Variants correctly grouped by gene
- Multiple transcripts handled appropriately
- Gene symbols standardized (HGNC for human)
- Ensembl IDs match genome build

✅ **Variant counting**
- Total variants per gene accurate
- Counts by impact level (HIGH/MODERATE/LOW)
- Counts by consequence type
- No double-counting of variants

✅ **Score aggregation**
- Maximum or mean scores calculated correctly
- Missing scores handled appropriately
- Scores correspond to correct variants

### Expected Metrics

| Metric | Clinical Panel | Whole Exome | Whole Genome |
|--------|----------------|-------------|--------------|
| **Genes with variants** | 50-200 | 8,000-12,000 | 15,000-20,000 |
| **Genes with HIGH impact** | 5-20 | 50-200 | 100-500 |
| **Genes with 2+ variants** | 10-50 | 1,000-3,000 | 3,000-8,000 |
| **Mean variants per gene** | 1-3 | 1-2 | 2-5 |

### Red Flags

❌ One gene has > 100 variants: Possible alignment artifact or repeat region
❌ No genes with > 1 variant: Over-filtering or small sample size
❌ Many genes with only synonymous variants: Consider filtering these out

---

## 5. Variant Prioritization (Step 7)

### Critical Checkpoints

✅ **Prioritization criteria**
- Scoring system appropriate for use case
- Weights reflect clinical/research priorities
- ACMG criteria applied correctly (for clinical)
- ClinVar annotations weighted highly

✅ **Pathogenicity classification**
- ACMG/AMP categories assigned
- Evidence criteria documented
- Conflicting predictions handled
- Uncertain significance not over-interpreted

### Expected Metrics

| Priority Level | Expected Count | Interpretation |
|---------------|----------------|----------------|
| **Pathogenic** | 0-5 per sample | Known pathogenic, report immediately |
| **Likely Pathogenic** | 1-10 per sample | Strong evidence, clinical follow-up |
| **VUS** | 5-50 per sample | Uncertain, monitor or functional studies |
| **Likely Benign** | Many | Can filter out for clinical reports |
| **Benign** | Many | Can filter out for clinical reports |

### Decision Point: Clinical Reporting

**Report immediately:**
- ✅ ClinVar Pathogenic in disease-relevant gene
- ✅ Known disease-causing variant (HGMD, ClinVar)
- ✅ Loss-of-function in haploinsufficient gene
- ✅ ACMG secondary findings (incidental findings)

**Report with caution:**
- ⚠️ VUS in disease-relevant gene with strong predictions
- ⚠️ Novel missense with CADD > 30, REVEL > 0.9
- ⚠️ Splicing variant near canonical splice site
- ⚠️ De novo variant in patient-parent trio

**Do not report:**
- ❌ Common variants (AF > 0.05) unless pharmacogenomic
- ❌ Synonymous variants (unless functional evidence)
- ❌ Benign or Likely benign ClinVar classification
- ❌ Variants in genes unrelated to phenotype

---

## 6. Visualization QC (Step 8)

### Expected Visualizations

**1. Consequence Distribution**
- Most variants should be intronic or intergenic (genome)
- Most variants should be coding (exome)
- Missense variants most common coding consequence
- Stop-gain and frameshift rare (< 1%)

**2. Impact by Chromosome**
- Impact distribution similar across chromosomes
- No chromosome with disproportionate HIGH impact (may indicate QC issue)
- Sex chromosomes (X, Y) may differ in coverage/calling

**3. Pathogenicity Score Distributions**
- CADD scores: Most variants < 20, few > 30
- REVEL scores: Bimodal distribution (benign vs deleterious)
- PolyPhen: Categories clearly separated

**4. Allele Frequency**
- Most variants rare (AF < 0.01)
- Log-scale distribution shows full spectrum
- Very rare variants (AF < 0.0001) most enriched

**5. Gene Burden**
- Some genes naturally have more variants (large genes)
- Outliers may indicate artifacts or true hotspots
- Compare to known mutation-tolerant/intolerant genes

### Red Flags in Visualizations

❌ **Uniform consequences:** If all variants same consequence, annotation may have failed
❌ **Single chromosome outlier:** Possible batch effect or alignment issue
❌ **No rare variants:** Frequency filtering may be too stringent
❌ **All high-scoring:** Pathogenicity filtering may be too permissive

---

## Summary: QC Checklist

Use this checklist at each workflow stage:

### ✅ Step 1: VCF Validation
- [ ] VCF passes format validation
- [ ] Ti/Tv ratio in expected range (2.0-2.1 WGS, 2.8-3.0 WES)
- [ ] Het/Hom ratio 1.5-2.0
- [ ] No duplicate variants
- [ ] Average QUAL > 30

### ✅ Step 3-4: Annotation
- [ ] 100% variants annotated
- [ ] Coding variants percentage appropriate (1-2% WGS, 40-60% WES)
- [ ] Gene symbols present for coding variants
- [ ] Pathogenicity scores populated (if plugins enabled)
- [ ] No genome build mismatch

### ✅ Step 5: Filtering
- [ ] Filtered variant count reasonable (10-100 for clinical, 500-5000 for research)
- [ ] HIGH impact variants: 10-50 (exome), 100-500 (genome)
- [ ] Rare high-impact variants: 1-20 (clinical)
- [ ] Filtering thresholds documented

### ✅ Step 6-7: Gene Summary & Prioritization
- [ ] Gene counts reasonable (50-200 panel, 8000-12000 exome)
- [ ] Prioritized variants: 1-20 for clinical reporting
- [ ] ACMG classifications appropriate
- [ ] Pathogenic/Likely pathogenic variants manually reviewed

### ✅ Step 8: Visualizations
- [ ] Consequence distribution matches sequencing type
- [ ] No chromosomal outliers
- [ ] Allele frequency distribution shows rare variants
- [ ] Pathogenicity scores show expected bimodal distribution

---

**For additional troubleshooting, see:** [troubleshooting_guide.md](troubleshooting_guide.md)
