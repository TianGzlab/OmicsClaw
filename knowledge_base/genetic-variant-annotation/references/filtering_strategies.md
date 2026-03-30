# Variant Filtering Strategies

This guide provides detailed filtering strategies for different use cases, including recommended thresholds, filtering logic, and decision criteria.

---

## Overview

Variant filtering is a critical step to reduce the list of annotated variants to a manageable set of candidates for further investigation. The optimal filtering strategy depends on:

1. **Use case** (clinical diagnostics, research, population genetics)
2. **Disease model** (dominant, recessive, de novo, somatic)
3. **Sequencing type** (whole genome, whole exome, targeted panel)
4. **Available annotations** (pathogenicity scores, clinical databases)
5. **Downstream analysis** (clinical reporting, burden testing, association studies)

---

## General Filtering Principles

### Hierarchical Filtering Approach

**Stage 1: Quality Filtering**
- Remove low-quality variants (QUAL, DP, AB thresholds)
- Apply PASS filter if available
- Remove variants failing technical QC

**Stage 2: Consequence Filtering**
- Filter by variant impact (HIGH/MODERATE/LOW)
- Select specific consequence types
- Remove synonymous variants (unless functional evidence)

**Stage 3: Frequency Filtering**
- Apply population frequency thresholds
- Consider disease model (dominant vs recessive)
- Handle missing frequencies appropriately

**Stage 4: Pathogenicity Filtering**
- Use pathogenicity predictions (SIFT, PolyPhen, CADD, REVEL)
- Include ClinVar classifications
- Consider loss-of-function predictions

**Stage 5: Gene-Based Filtering**
- Filter to disease-relevant gene lists
- Apply gene constraint metrics (pLI, LOEUF)
- Consider mode of inheritance per gene

---

## Filtering by Use Case

### 1. Clinical Diagnostics (Rare Mendelian Disease)

**Goal:** Identify pathogenic variants responsible for patient phenotype

#### Dominant Disease Filtering

```python
filter_by_consequence(
    df,
    impact=['HIGH', 'MODERATE'],
    consequence_types=[
        'stop_gained', 'frameshift_variant',
        'splice_acceptor_variant', 'splice_donor_variant',
        'start_lost', 'stop_lost',
        'missense_variant', 'inframe_deletion', 'inframe_insertion'
    ]
)

filter_by_frequency(
    df,
    max_af=0.01,  # Rare variants only
    population='gnomAD_AF',
    missing_as_rare=True
)

filter_by_pathogenicity(
    df,
    cadd_threshold=20,
    revel_threshold=0.5,
    sift='deleterious',
    polyphen='probably_damaging',
    clinvar=['Pathogenic', 'Likely_pathogenic'],
    require_all=False  # Any pathogenic prediction
)
```

**Expected output:** 1-10 candidate variants per patient

**Adjust if:**
- Too many candidates (>20): Increase stringency (AF < 0.001, CADD > 25)
- No candidates: Decrease stringency (AF < 0.05, CADD > 15, include MODERATE)

#### Recessive Disease Filtering

```python
# More permissive frequency threshold for recessive
filter_by_frequency(
    df,
    max_af=0.05,  # Carriers more common for recessive
    population='gnomAD_AF',
    missing_as_rare=True
)

# Then identify compound heterozygous or homozygous
filter_by_zygosity(
    df,
    mode='recessive',
    require_compound_het=True,
    same_gene=True
)
```

**Expected output:** 1-5 genes with biallelic variants per patient

#### X-Linked Disease Filtering

```python
# Filter to X chromosome
filter_by_chromosome(df, chromosomes=['X', 'chrX'])

# For males: hemizygous variants
# For females: heterozygous variants with skewed X-inactivation (if available)

filter_by_frequency(
    df,
    max_af=0.001,  # Stricter for X-linked
    population='gnomAD_AF_male'  # Use male frequency for X chr
)
```

---

### 2. Cancer Genomics (Somatic Variants)

**Goal:** Identify somatic driver mutations and actionable variants

#### Tumor-Only Filtering

```python
# Somatic-like filtering (without matched normal)
filter_by_frequency(
    df,
    max_af=0.001,  # Remove common germline
    population='gnomAD_AF',
    missing_as_rare=False  # Missing likely novel or rare
)

filter_by_consequence(
    df,
    impact=['HIGH', 'MODERATE'],
    consequence_types=[
        'stop_gained', 'frameshift_variant',
        'missense_variant', 'splice_site_variant',
        'inframe_deletion', 'inframe_insertion'
    ]
)

# Filter to cancer genes
filter_by_gene_list(
    df,
    gene_list=['TP53', 'KRAS', 'EGFR', ...],  # Cancer Gene Census
    database='COSMIC'
)

# Prioritize by COSMIC mutations
filter_by_database(
    df,
    cosmic_count_threshold=5,  # Seen in 5+ COSMIC samples
    hotspot=True
)
```

**Expected output:** 1-10 driver mutations per tumor

#### Tumor-Normal Paired Filtering

```python
# Remove variants present in matched normal
filter_germline(
    df,
    normal_bam='patient_normal.bam',
    max_normal_vaf=0.02  # Allow up to 2% VAF in normal (sequencing error)
)

# Require minimum tumor VAF
filter_by_vaf(
    df,
    min_tumor_vaf=0.05,  # At least 5% allele fraction in tumor
    min_depth=20         # Minimum coverage in tumor
)

# Filter to somatic mutation signatures
filter_by_signature(
    df,
    signatures=['SBS1', 'SBS5', 'SBS40'],  # Age, clock-like, tobacco
    cosmic_signatures=True
)
```

**Expected output:** 5-20 high-confidence somatic variants per tumor

---

### 3. Population Genetics (Research)

**Goal:** Analyze variant distributions, allele frequencies, selection signals

#### Permissive Filtering for Research

```python
# Quality filtering only
filter_by_quality(
    df,
    min_qual=20,
    min_depth=5,
    max_missing=0.1  # Allow 10% missing genotypes
)

# Keep all coding variants (including synonymous)
filter_by_consequence(
    df,
    impact=['HIGH', 'MODERATE', 'LOW'],
    include_synonymous=True,
    include_utr=False
)

# No frequency filter (or permissive)
filter_by_frequency(
    df,
    max_af=0.5,  # Keep common and rare variants
    population='gnomAD_AF'
)
```

**Expected output:** 500-5,000 coding variants per sample

#### Selection Analysis

```python
# Filter for loss-of-function variants
filter_by_consequence(
    df,
    consequence_types=[
        'stop_gained', 'frameshift_variant',
        'splice_acceptor_variant', 'splice_donor_variant'
    ]
)

# Stratify by frequency for selection analysis
stratify_by_frequency(
    df,
    bins=[0, 0.001, 0.01, 0.05, 0.5],
    labels=['ultra_rare', 'rare', 'low_freq', 'common']
)

# Analyze by gene constraint
filter_by_constraint(
    df,
    pli_threshold=0.9,  # Loss-of-function intolerant genes
    loeuf_threshold=0.35
)
```

---

### 4. Pharmacogenomics

**Goal:** Identify variants affecting drug metabolism and response

#### PGx Gene Filtering

```python
# Filter to pharmacogenes
filter_by_gene_list(
    df,
    gene_list=['CYP2D6', 'CYP2C19', 'CYP2C9', 'TPMT', 'DPYD', 'SLCO1B1', ...],
    database='PharmGKB'
)

# Include all impact levels (functional synonymous variants exist)
filter_by_consequence(
    df,
    impact=['HIGH', 'MODERATE', 'LOW', 'MODIFIER'],
    include_synonymous=True  # Some synonymous variants are functional
)

# No frequency filter (common variants important for PGx)
# Include PharmGKB clinical annotations
filter_by_database(
    df,
    pharmgkb_level=['1A', '1B', '2A', '2B'],  # Evidence levels
    clinical_annotation=True
)

# Annotate with star alleles
annotate_star_alleles(
    df,
    genes=['CYP2D6', 'CYP2C19', 'CYP2C9']
)
```

**Expected output:** 10-100 PGx variants per sample

---

### 5. Familial Analysis (Trio/Pedigree)

**Goal:** Identify de novo, inherited, or segregating variants

#### De Novo Variant Discovery

```python
# Identify variants in proband absent in parents
filter_de_novo(
    df,
    proband='child.vcf',
    parents=['mother.vcf', 'father.vcf'],
    max_parent_vaf=0.01,  # Allow 1% parental mosaic
    min_proband_vaf=0.3   # Require 30% in proband
)

# High-impact variants (de novo typically deleterious)
filter_by_consequence(
    df,
    impact=['HIGH', 'MODERATE'],
    consequence_types=[
        'stop_gained', 'frameshift_variant',
        'splice_site_variant', 'missense_variant'
    ]
)

# Pathogenic predictions
filter_by_pathogenicity(
    df,
    cadd_threshold=25,
    revel_threshold=0.7,
    require_all=False
)
```

**Expected output:** 0-5 de novo mutations per child (high-confidence)

#### Segregation Analysis

```python
# Variants present in all affected family members
filter_by_segregation(
    df,
    affected_samples=['proband', 'sibling1', 'aunt'],
    unaffected_samples=['father', 'mother'],
    require_in_all_affected=True,
    absent_in_unaffected=True
)

# Filter by inheritance mode
filter_by_inheritance(
    df,
    mode='dominant',  # or 'recessive', 'x_linked'
    penetrance=0.95   # 95% penetrance
)
```

---

## Filtering Thresholds

### Population Frequency Thresholds

| Disease Model | gnomAD AF Threshold | Rationale |
|--------------|---------------------|-----------|
| **Dominant (severe)** | < 0.001 (0.1%) | Must be very rare |
| **Dominant (mild)** | < 0.01 (1%) | Can be more common |
| **Recessive** | < 0.05 (5%) | Carriers common |
| **X-linked** | < 0.001 (males) | Hemizygous in males |
| **Somatic (cancer)** | < 0.001 | Exclude germline |
| **Pharmacogenomics** | No filter | Common variants important |
| **Population genetics** | < 0.5 (50%) | Keep most variants |

### Pathogenicity Score Thresholds

| Score | Threshold | Category | Interpretation |
|-------|-----------|----------|----------------|
| **CADD Phred** | > 30 | High confidence deleterious | Top 0.1% deleterious |
| | 20-30 | Moderate confidence | Top 1% deleterious |
| | 15-20 | Low confidence | Top 3% deleterious |
| | < 15 | Likely benign | Bottom 97% |
| **REVEL** | > 0.75 | Likely pathogenic | High confidence |
| | 0.5-0.75 | Uncertain | Moderate confidence |
| | < 0.5 | Likely benign | Low pathogenicity |
| **SIFT** | < 0.05 | Deleterious | Damaging prediction |
| | >= 0.05 | Tolerated | Benign prediction |
| **PolyPhen-2** | > 0.85 | Probably damaging | High confidence |
| | 0.45-0.85 | Possibly damaging | Moderate confidence |
| | < 0.45 | Benign | Low impact |

### Variant Quality Thresholds

| Metric | Threshold | Sequencing Type | Notes |
|--------|-----------|-----------------|-------|
| **QUAL** | > 30 | All | Phred-scaled quality score |
| **DP (Depth)** | > 10 | WES/WGS | Minimum coverage |
| | > 20 | Clinical | Higher confidence |
| **GQ (Genotype Quality)** | > 20 | All | Phred-scaled genotype quality |
| **AB (Allele Balance)** | 0.3 - 0.7 | Germline het | Expected ~0.5 for het |
| | 0.05 - 0.95 | Somatic | Wider range for tumors |
| **VAF (Variant Allele Freq)** | > 0.05 | Somatic | Minimum tumor VAF |

---

## Consequence Type Priorities

### HIGH Impact Consequences

Always include these for clinical analysis:

```python
high_impact_consequences = [
    'transcript_ablation',         # Complete gene loss
    'splice_acceptor_variant',     # Disrupts splicing (AG)
    'splice_donor_variant',        # Disrupts splicing (GT)
    'stop_gained',                 # Nonsense mutation
    'frameshift_variant',          # Frameshift indel
    'stop_lost',                   # Loss of stop codon
    'start_lost',                  # Loss of start codon
    'transcript_amplification'     # Gene amplification
]
```

### MODERATE Impact Consequences

Include for clinical and research:

```python
moderate_impact_consequences = [
    'inframe_insertion',           # In-frame indel (not frameshift)
    'inframe_deletion',
    'missense_variant',            # Amino acid substitution
    'protein_altering_variant',    # Complex changes
    'splice_region_variant',       # Near splice site (±3-8 bp)
]
```

### LOW Impact Consequences

Include for research, usually exclude from clinical:

```python
low_impact_consequences = [
    'synonymous_variant',          # Silent mutation
    'stop_retained_variant',       # Synonymous stop
    'incomplete_terminal_codon_variant',
    'coding_sequence_variant',     # Within coding sequence (unspecified)
]
```

### MODIFIER Consequences

Typically exclude (intronic, intergenic, UTR):

```python
modifier_consequences = [
    'intron_variant',
    'intergenic_variant',
    '5_prime_UTR_variant',
    '3_prime_UTR_variant',
    'upstream_gene_variant',
    'downstream_gene_variant',
    # Many others...
]
```

---

## Combining Multiple Filters

### Logical Operators

**AND (intersection):** All criteria must be met
```python
# Rare AND high-impact AND pathogenic
variants = filter_by_frequency(df, max_af=0.01)
variants = filter_by_consequence(variants, impact=['HIGH'])
variants = filter_by_pathogenicity(variants, cadd_threshold=20)
```

**OR (union):** Any criterion met
```python
# ClinVar pathogenic OR (rare + high CADD)
clinvar_pathogenic = filter_by_clinvar(df, classes=['Pathogenic'])
rare_deleterious = filter_by_frequency(df, max_af=0.01)
rare_deleterious = filter_by_pathogenicity(rare_deleterious, cadd_threshold=25)

variants = pandas.concat([clinvar_pathogenic, rare_deleterious]).drop_duplicates()
```

### Prioritization Scoring

**Weighted scoring approach:**
```python
def calculate_priority_score(row):
    score = 0

    # Clinical significance (30%)
    if row['CLIN_SIG'] == 'Pathogenic':
        score += 30
    elif row['CLIN_SIG'] == 'Likely_pathogenic':
        score += 20

    # Consequence severity (25%)
    if row['IMPACT'] == 'HIGH':
        score += 25
    elif row['IMPACT'] == 'MODERATE':
        score += 15

    # Pathogenicity scores (20%)
    if row['CADD_PHRED'] > 30:
        score += 20
    elif row['CADD_PHRED'] > 20:
        score += 10

    # Allele frequency (15%)
    if row['gnomAD_AF'] < 0.001:
        score += 15
    elif row['gnomAD_AF'] < 0.01:
        score += 10

    # Loss of function (10%)
    if row['LOF'] == 'HC':  # High-confidence LOF
        score += 10

    return score

df['Priority_Score'] = df.apply(calculate_priority_score, axis=1)
df = df.sort_values('Priority_Score', ascending=False)
```

---

## Handling Missing Data

### Missing Frequency Data

**Options:**
1. **Treat as rare** (conservative, recommended for clinical):
   ```python
   filter_by_frequency(df, max_af=0.01, missing_as_rare=True)
   ```

2. **Exclude missing** (permissive, research):
   ```python
   filter_by_frequency(df, max_af=0.01, missing_as_rare=False)
   ```

3. **Separate category** (manual review):
   ```python
   rare_variants = df[df['gnomAD_AF'] < 0.01]
   missing_freq = df[df['gnomAD_AF'].isna()]
   ```

### Missing Pathogenicity Scores

**Options:**
1. **Require any score** (strict):
   ```python
   df = df[df[['SIFT', 'PolyPhen', 'CADD', 'REVEL']].notna().any(axis=1)]
   ```

2. **Use available scores** (permissive):
   ```python
   # Calculate consensus from non-missing scores
   df['Pathogenic_Predictions'] = df[['SIFT', 'PolyPhen', 'CADD']].count(axis=1)
   ```

3. **Impute from consequence** (approximation):
   ```python
   # HIGH impact variants likely pathogenic even without scores
   df.loc[df['IMPACT'] == 'HIGH', 'Pathogenic'] = True
   ```

---

## Special Filtering Scenarios

### Splice Site Variants

**Canonical splice sites** (high confidence):
```python
filter_by_consequence(
    df,
    consequence_types=[
        'splice_acceptor_variant',  # ±1-2 bp from exon boundary
        'splice_donor_variant'
    ]
)
```

**Extended splice regions** (moderate confidence):
```python
filter_by_consequence(
    df,
    consequence_types=[
        'splice_region_variant',  # ±3-8 bp from exon boundary
        'splice_polypyrimidine_tract_variant'
    ]
)
# Validate with SpliceAI or MaxEntScan predictions
```

### Structural Variants

**Large deletions/duplications:**
```python
filter_by_svtype(
    df,
    svtypes=['DEL', 'DUP'],
    min_size=50,  # Minimum 50 bp
    max_size=5000000  # Maximum 5 Mb
)

# Filter by gene overlap
filter_by_gene_overlap(
    df,
    disease_genes=True,
    exon_overlap=True  # Must overlap coding exons
)
```

### Mitochondrial Variants

**mtDNA-specific filtering:**
```python
# Filter to mitochondrial chromosome
filter_by_chromosome(df, chromosomes=['MT', 'chrM'])

# Heteroplasmy threshold (not diploid)
filter_by_heteroplasmy(
    df,
    min_heteroplasmy=0.10,  # At least 10% of reads
    max_heteroplasmy=0.95   # Not fixed (leave room for error)
)

# mtDNA pathogenicity databases (MITOMAP)
filter_by_database(df, database='MITOMAP', pathogenic=True)
```

---

## Filtering Workflows by Disease Class

### Neurodevelopmental Disorders

```python
# De novo or very rare variants
filter_by_frequency(df, max_af=0.0001)

# High/moderate impact
filter_by_consequence(df, impact=['HIGH', 'MODERATE'])

# Filter to neurodevelopmental genes
filter_by_gene_list(df, gene_list='DDG2P_neurodevelopmental.txt')

# Strong pathogenicity predictions
filter_by_pathogenicity(df, cadd_threshold=25, revel_threshold=0.7)
```

### Cardiac Disorders

```python
# Rare variants (carriers more common for some cardiomyopathies)
filter_by_frequency(df, max_af=0.01)

# Include missense (many pathogenic missense in cardiac genes)
filter_by_consequence(df, impact=['HIGH', 'MODERATE'])

# Filter to cardiac gene panel
filter_by_gene_list(df, gene_list='ClinGen_cardiac_genes.txt')

# ClinVar classifications critical
prioritize_by_clinvar(df, evidence_level=['reviewed_by_expert_panel'])
```

### Cancer Predisposition

```python
# Rare variants (germline)
filter_by_frequency(df, max_af=0.001)

# Loss-of-function in tumor suppressors
filter_by_consequence(df, consequence_types=['stop_gained', 'frameshift_variant'])
filter_by_gene_list(df, gene_list='TSG_tumor_suppressors.txt')

# Or activating mutations in oncogenes
filter_by_hotspot(df, oncogenes=True, hotspot_database='COSMIC')
```

---

## Quality Control During Filtering

### Monitor Filtering Steps

Track how many variants are removed at each step:

```python
print(f"Starting variants: {len(df)}")

df = filter_by_quality(df, min_qual=30)
print(f"After quality filter: {len(df)}")

df = filter_by_consequence(df, impact=['HIGH', 'MODERATE'])
print(f"After consequence filter: {len(df)}")

df = filter_by_frequency(df, max_af=0.01)
print(f"After frequency filter: {len(df)}")

df = filter_by_pathogenicity(df, cadd_threshold=20)
print(f"After pathogenicity filter: {len(df)}")
```

### Sanity Checks

```python
# Check if filtering is too strict (no variants remaining)
if len(df) == 0:
    print("WARNING: No variants remaining after filtering!")
    print("Consider relaxing thresholds")

# Check if filtering is too permissive (too many variants)
if len(df) > 1000:
    print("WARNING: Many variants remaining ({len(df)})")
    print("Consider stricter filtering for clinical analysis")

# Check for expected variants (positive controls)
expected_variants = ['rs121913527', 'rs80338939']  # Known pathogenic
if not df['ID'].isin(expected_variants).any():
    print("WARNING: Expected pathogenic variants not found!")
    print("Check filtering logic or VCF quality")
```

---

## Summary: Recommended Filtering Pipelines

### Clinical Diagnostics (Conservative)

```
Quality (QUAL>30, DP>10)
→ HIGH/MODERATE impact
→ gnomAD AF < 0.01
→ CADD > 20 OR ClinVar P/LP
→ Disease gene list
→ Manual review top 10-20 variants
```

### Research (Permissive)

```
Quality (QUAL>20, DP>5)
→ All coding consequences
→ gnomAD AF < 0.05
→ Gene constraint (optional)
→ Statistical analysis on 500-5000 variants
```

### Cancer (Somatic)

```
Quality + VAF filters
→ Germline removal (AF < 0.001)
→ HIGH/MODERATE impact
→ Cancer gene census
→ COSMIC hotspots
→ Actionable variants prioritization
```

---

**For additional guidance, see:**
- [consequence_terms.md](consequence_terms.md) - Detailed consequence type descriptions
- [pathogenicity_interpretation.md](pathogenicity_interpretation.md) - ACMG classification guidelines
- [qc_guidelines.md](qc_guidelines.md) - Expected metrics and QC checkpoints
