# Tool Selection Guide: VEP vs SNPEff

This guide helps you choose between Ensembl VEP and SNPEff for variant annotation based on your specific use case, organism, and computational resources.

---

## Quick Decision Matrix

| Use Case | Recommended Tool | Why |
|----------|------------------|-----|
| **Human clinical genetics** | VEP | Comprehensive clinical databases (ClinVar, HGMD), ACMG annotations |
| **Human research** | Either | Both provide excellent functional annotation |
| **Mouse (model organism)** | Either | Both well-supported |
| **Non-model organism** | SNPEff | 38,000+ genomes available |
| **Quick exploratory analysis** | SNPEff | Faster, lightweight setup |
| **Limited computational resources** | SNPEff | Lower memory, no large cache needed |
| **Cancer genomics** | Either | Both support COSMIC, somatic annotations |
| **Regulatory variants** | VEP | Better ENCODE, TF binding site annotations |
| **Population genetics** | Either | Both provide allele frequencies |
| **GATK pipeline integration** | SNPEff | Native GATK Funcot alternative |

---

## When to Use Ensembl VEP

### ✅ Best For:

1. **Human Clinical/Medical Genetics**
   - Comprehensive ClinVar annotations
   - HGMD disease associations
   - ACMG/AMP classification support
   - Clinical pharmacogenomics (PharmGKB)
   - Multiple pathogenicity predictions (SIFT, PolyPhen, CADD, REVEL, MutationTaster)

2. **Regulatory Variant Analysis**
   - ENCODE regulatory elements
   - Transcription factor binding sites (TFBS)
   - Enhancer and promoter annotations
   - DNase hypersensitivity sites
   - ChromHMM chromatin states

3. **Comprehensive Annotation Needs**
   - 30+ pathogenicity predictors via plugins
   - Detailed transcript annotations
   - Multiple population frequency databases
   - Conservation scores (PhyloP, PhastCons, GERP++)
   - Protein domain annotations (Pfam, InterPro)

4. **Publication-Quality Reporting**
   - Standardized output formats
   - Well-documented annotation fields
   - JSON/VCF/Tab output options
   - Quarterly releases ensure up-to-date data

### ⚠️ Requirements:

- **Computational:**
  - 16-32 GB RAM for human genomes
  - 15-20 GB disk space per genome cache
  - 4-8 CPU cores recommended for parallelization

- **Setup:**
  - Cache download required (one-time, 30-60 minutes)
  - Plugin installation for advanced features
  - Database downloads for CADD, dbNSFP, etc.

- **Time:**
  - Initial setup: 1-2 hours
  - Runtime: ~10-30 minutes for WES, 1-3 hours for WGS (cached)

### Example Use Cases:

**Clinical Exome Sequencing:**
```
Patient: 3-year-old with developmental delay
Goal: Identify pathogenic variants in known disease genes
VEP advantage: ClinVar, OMIM, HGMD annotations critical for diagnosis
```

**Pharmacogenomics:**
```
Patient: Pre-treatment cancer screening
Goal: Identify variants affecting drug metabolism
VEP advantage: PharmGKB annotations, star allele detection
```

**Regulatory Variant Discovery:**
```
Study: GWAS of complex trait
Goal: Annotate non-coding variants with regulatory impact
VEP advantage: ENCODE annotations, TFBS, eQTL data
```

---

## When to Use SNPEff

### ✅ Best For:

1. **Non-Model Organisms**
   - 38,000+ genomes supported
   - Plants, fungi, bacteria, archaea
   - Custom genome annotations
   - RefSeq and Ensembl support

2. **Quick Analysis**
   - Exploratory data analysis
   - QC and initial filtering
   - Rapid turnaround needed (<1 hour)
   - First-pass annotation before deeper analysis

3. **Limited Computational Resources**
   - Runs on laptops (8 GB RAM sufficient)
   - Smaller disk footprint (~1 GB per genome)
   - No large cache downloads required
   - Fast annotation (2-5x faster than VEP API mode)

4. **GATK Pipeline Integration**
   - Native compatibility with GATK tools
   - Funcotator alternative
   - Integrated with Haplotyp eCaller/Mutect2 workflows
   - SnpSift for post-processing

5. **Cancer Genomics with SnpSift**
   - COSMIC mutation database
   - Cancer gene census annotations
   - Somatic vs germline filtering
   - Tumor-normal comparison tools

### ⚠️ Requirements:

- **Computational:**
  - 8-16 GB RAM (human genomes)
  - ~1 GB disk space per genome
  - 2-4 CPU cores sufficient

- **Setup:**
  - Quick database download (5-10 minutes)
  - No plugin installation needed for basic annotation
  - SnpSift for advanced filtering (optional)

- **Time:**
  - Initial setup: 10-20 minutes
  - Runtime: ~5-15 minutes for WES, 30-90 minutes for WGS

### Example Use Cases:

**Non-Model Organism Research:**
```
Species: Arabidopsis thaliana
Goal: Annotate variants from resequencing study
SNPEff advantage: 38,000+ genomes, easy custom genome support
```

**Quick Exploratory Analysis:**
```
Dataset: Pilot WES data (10 samples)
Goal: Assess variant distribution before full cohort analysis
SNPEff advantage: Fast turnaround for QC and filtering
```

**GATK Workflow:**
```
Pipeline: GATK Best Practices
Goal: Integrate annotation into variant calling workflow
SNPEff advantage: Native GATK compatibility, Funcotator alternative
```

**Resource-Constrained Environment:**
```
System: Laptop with 8 GB RAM
Goal: Annotate small VCF from targeted panel
SNPEff advantage: Lightweight, no large cache files
```

---

## Feature Comparison

| Feature | VEP | SNPEff | Notes |
|---------|-----|--------|-------|
| **Human genome support** | ✅ Excellent | ✅ Excellent | Both fully support GRCh38/GRCh37 |
| **Model organisms** | ✅ Good | ✅ Excellent | SNPEff has broader coverage |
| **Non-model organisms** | ⚠️ Limited | ✅ Excellent | SNPEff: 38,000+ genomes |
| **ClinVar annotations** | ✅ Native | ⚠️ Via SnpSift | VEP better integrated |
| **COSMIC** | ✅ Native | ✅ Native | Both support cancer variants |
| **Pathogenicity scores** | ✅ Extensive | ⚠️ Basic | VEP: 30+ predictors via plugins |
| **Regulatory elements** | ✅ Excellent | ⚠️ Basic | VEP has ENCODE integration |
| **Population frequencies** | ✅ Multiple | ✅ Basic | VEP: gnomAD, 1000G, TopMed, ESP |
| **HGVS notation** | ✅ Yes | ✅ Yes | Both generate standard nomenclature |
| **Custom annotations** | ✅ Via plugins | ✅ Via SnpSift | Both support custom databases |
| **Speed (cached)** | ⚠️ Moderate | ✅ Fast | SNPEff ~2-3x faster |
| **Memory usage** | ⚠️ High (16-32 GB) | ✅ Low (8-16 GB) | VEP requires more RAM |
| **Disk space** | ⚠️ Large (15-20 GB) | ✅ Small (~1 GB) | VEP cache is larger |
| **Setup complexity** | ⚠️ Moderate | ✅ Simple | SNPEff easier to install |
| **Output formats** | ✅ VCF, JSON, Tab | ✅ VCF, HTML | VEP more flexible |
| **Documentation** | ✅ Excellent | ✅ Excellent | Both well-documented |
| **Community support** | ✅ Active | ✅ Active | Both widely used |
| **Update frequency** | ✅ Quarterly | ⚠️ Variable | VEP more regular releases |
| **License** | ✅ Apache 2.0 | ✅ LGPLv3 | Both permissive for commercial use |

---

## Decision Tree

```
START: What is your primary use case?
│
├─ Human clinical/medical genetics?
│  │
│  ├─ YES → Do you need comprehensive pathogenicity predictions?
│  │        │
│  │        ├─ YES → **Use VEP** (ClinVar, SIFT, PolyPhen, CADD, REVEL)
│  │        │
│  │        └─ NO → Do you have > 16 GB RAM and 20 GB disk?
│  │                 │
│  │                 ├─ YES → **Use VEP** (better clinical annotations)
│  │                 │
│  │                 └─ NO → **Use SNPEff** (lighter resource requirements)
│  │
│  └─ NO → Is this a non-model organism?
│           │
│           ├─ YES → **Use SNPEff** (38,000+ genomes)
│           │
│           └─ NO → Do you need regulatory annotations (ENCODE, TFBS)?
│                    │
│                    ├─ YES → **Use VEP** (comprehensive regulatory data)
│                    │
│                    └─ NO → Do you need quick exploratory analysis?
│                             │
│                             ├─ YES → **Use SNPEff** (faster, lightweight)
│                             │
│                             └─ NO → **Either tool works** (choose based on familiarity)
```

---

## Hybrid Approach

For some projects, using **both tools** may be optimal:

### Strategy 1: SNPEff First, VEP for Follow-Up

1. **Initial QC with SNPEff:**
   - Fast annotation for all variants
   - Assess variant distribution and quality
   - Filter to HIGH/MODERATE impact variants

2. **Detailed annotation with VEP:**
   - Re-annotate filtered variants with VEP
   - Add comprehensive pathogenicity predictions
   - Include clinical database annotations

**Advantage:** Fast initial QC, detailed annotation only where needed

### Strategy 2: VEP for Clinical, SNPEff for Research

1. **Clinical samples → VEP:**
   - Patient diagnostic samples
   - Clinical reporting required
   - Comprehensive annotations needed

2. **Research samples → SNPEff:**
   - Population studies
   - Exploratory analyses
   - Quick turnaround needed

**Advantage:** Optimize resource use per sample type

### Strategy 3: Cross-Validation

1. **Annotate with both tools:**
   - Run VEP and SNPEff in parallel
   - Compare consequence assignments
   - Identify discrepancies

2. **Use consensus annotations:**
   - Retain variants annotated similarly by both
   - Manually review discordant annotations
   - Increase confidence in results

**Advantage:** Higher confidence, catches annotation errors

---

## Migration Between Tools

### VEP → SNPEff

**When to migrate:**
- Resource constraints (memory, disk)
- Need non-model organism support
- Require faster turnaround
- GATK pipeline integration

**Considerations:**
- Annotation field names differ (CSQ vs ANN)
- Some VEP plugins have no SNPEff equivalent
- Rewrite parsing scripts for ANN format

### SNPEff → VEP

**When to migrate:**
- Need comprehensive clinical annotations
- Require regulatory element annotations
- Need additional pathogenicity predictors
- Publication-quality reporting

**Considerations:**
- Larger resource requirements
- Cache download required
- Plugin installation for advanced features
- Longer setup time

---

## Tool-Specific Strengths Summary

### VEP Excels At:

1. Clinical variant interpretation
2. Pathogenicity prediction
3. Regulatory variant annotation
4. ClinVar/HGMD integration
5. Pharmacogenomics
6. Publication-ready reports

### SNPEff Excels At:

1. Non-model organism support
2. Fast exploratory analysis
3. Lightweight resource usage
4. GATK pipeline integration
5. Quick setup and deployment
6. Custom genome annotations

---

## Additional Considerations

### Licensing

**VEP:**
- Apache 2.0 license
- Permissive for commercial use
- Some databases (HGMD) require separate licensing

**SNPEff:**
- LGPLv3 license
- Permissive for commercial use
- Source code modifications must be shared

### Support and Community

**VEP:**
- Active Ensembl help forum
- Regular updates (quarterly releases)
- Extensive documentation
- GitHub issue tracker

**SNPEff:**
- Active SourceForge/GitHub community
- Documentation and tutorials
- Email support from developers
- Stack Overflow Q&A

### Integration with Other Tools

**VEP:**
- Integrates with: Ensembl tools, UCSC Genome Browser, Galaxy
- APIs available for programmatic access
- JSON output for custom parsing

**SNPEff:**
- Integrates with: GATK, SnpSift, MultiQC, Galaxy
- Native GATK Funcotator alternative
- bcftools plugin available

---

## Summary: Choosing the Right Tool

### Choose VEP if:
- Human clinical or medical genetics
- Comprehensive annotations critical
- Have adequate computational resources (16+ GB RAM, 20 GB disk)
- Need regulatory variant annotations
- Publication-quality reporting required

### Choose SNPEff if:
- Non-model organism
- Quick exploratory analysis needed
- Limited computational resources
- GATK pipeline integration
- Simple functional annotation sufficient

### Use Both if:
- Resources allow for hybrid approach
- Want cross-validation of annotations
- Different sample types need different annotation depth

---

**For installation instructions, see:** [installation_guide.md](installation_guide.md)

**For usage best practices, see:**
- [vep_best_practices.md](vep_best_practices.md)
- [snpeff_best_practices.md](snpeff_best_practices.md)
