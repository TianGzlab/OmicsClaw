# Experimental Design Best Practices

This document provides comprehensive best practices for designing genomics experiments, including general principles, assay-specific recommendations, and common pitfalls to avoid.

---

## General Design Principles

### 1. Biological Replicates Are Essential

**Key principle:** Biological replicates (different individuals/samples) are more important than technical replicates (same sample sequenced multiple times).

**Why:**
- Biological variation is typically much larger than technical variation in modern sequencing
- Statistical inference requires biological replication to generalize findings
- Technical replicates only measure technical noise, not biological variability

**Recommendations:**
- **Minimum:** 3 biological replicates per condition (absolute minimum)
- **Standard:** 5-6 biological replicates per condition (recommended for most studies)
- **High-confidence:** 10+ biological replicates per condition (for detecting small effects)
- **Technical replicates:** Generally not needed with modern sequencing protocols (optional for quality control)

### 2. Sample Size vs. Sequencing Depth Trade-offs

When budget-constrained, you often must choose between more samples at lower depth or fewer samples at higher depth.

**General rule:** More biological replicates at moderate depth > fewer replicates at very high depth

**Rationale:**
- Statistical power increases more with additional replicates than additional depth
- Exception: Very low depth (<10M reads for RNA-seq) where you miss many transcripts

**Assay-specific recommendations:**

| Assay | Minimum Depth | Standard Depth | When to Increase Depth |
|-------|--------------|----------------|------------------------|
| Bulk RNA-seq | 10M reads | 20-30M reads | Isoform analysis, rare transcripts |
| scRNA-seq | 20K reads/cell | 50-100K reads/cell | Rare cell types, trajectory analysis |
| ATAC-seq | 15M reads | 30-50M reads | Footprinting, TF binding |
| ChIP-seq (narrow) | 10M reads | 20M reads | Weak or diffuse binding |
| ChIP-seq (broad) | 20M reads | 40M reads | Broad histone marks |

**Decision framework:**
1. Calculate power at minimum acceptable depth
2. If power <0.80, first try increasing sample size
3. Only increase depth if already at maximum feasible sample size

### 3. Pilot Studies Are Highly Valuable

**Benefits of pilot data:**
- Accurate dispersion/variability estimates for power calculations
- Identify technical issues before full-scale experiment
- Validate sample collection and processing protocols
- Can detect contamination, batch effects, or quality issues early

**Pilot study design:**
- **Size:** 2-3 samples per condition minimum (more is better)
- **Depth:** Standard sequencing depth for your assay
- **Coverage:** Include all experimental conditions and major covariates
- **Timing:** Run pilot 2-3 months before main experiment if possible

**Using pilot data:**
- Extract dispersion estimates (DESeq2, edgeR) for accurate power calculations
- Estimate effect sizes to refine hypotheses
- Validate that your processing pipeline works
- Adjust main study design based on findings

### 4. Randomization Is Critical

**What to randomize:**
- Sample assignment to conditions (if applicable)
- Sample processing order
- Batch assignment (see Batch Effect Mitigation guide)
- Plate positions and sequencing lanes
- Data collection timing

**Why randomization matters:**
- Prevents systematic bias from confounding variables
- Ensures valid statistical inference
- Controls for unknown confounders
- Enables proper use of statistical adjustment methods

**How to randomize:**
- Use computer-generated random assignments (never manual selection)
- Stratify randomization by important covariates (age, sex, etc.)
- Document randomization scheme for reproducibility
- Consider block randomization to ensure balance

### 5. Balance Covariates Across Conditions

**Important covariates to balance:**
- Sex/gender (often has major effects on gene expression)
- Age or developmental stage
- Genetic background (strain, ancestry)
- Collection site or center (for multi-site studies)
- Time of day (circadian effects)
- Technician or operator

**Balancing strategies:**
- Stratified randomization during sample selection
- Matched pairs or blocking designs
- Statistical adjustment in analysis (include covariates in model)
- Record all potential confounders even if not balanced

**When perfect balance isn't possible:**
- Document imbalances in experimental design
- Include unbalanced covariates in statistical model
- Consider sensitivity analyses
- Be cautious about causal interpretation

---

## Assay-Specific Best Practices

### Bulk RNA-seq

**Sample requirements:**
- 5-6 biological replicates per condition (standard)
- 3 replicates minimum (only for pilot studies or when unavoidable)
- 10+ replicates for small effect detection (<1.5-fold change)

**Depth recommendations:**
- Standard DE analysis: 20-30 million reads
- Isoform-level analysis: 40-50 million reads
- Low-abundance transcripts: 50-100 million reads
- Cost-effective: 15 million reads if increasing sample size instead

**Design considerations:**
- Paired samples (before/after) require fewer replicates (n=4-5 sufficient)
- Time course designs: ensure adequate sampling density
- Multi-factor designs: ensure all factor combinations are represented

### Single-Cell RNA-seq

**Sample requirements:**
- More biological replicates needed than bulk RNA-seq
- Minimum 3 samples per condition (better: 5-6)
- Each sample should contribute 500-5000+ cells depending on goal

**Cell number recommendations:**
- Discovery (cell type identification): 3000-10000 cells per condition
- Differential expression: 500-2000 cells per cell type, across multiple samples
- Trajectory inference: 5000-20000 cells
- Rare cell types: 10000-50000 cells to ensure sufficient representation

**Key principle:** Multiple samples with moderate cells each >> one sample with many cells
- Biological replication matters more than cell number
- Variability between individuals is critical for inference

**Depth recommendations:**
- Standard: 50K reads per cell (after multiplexing)
- Low: 20K reads per cell (budget-constrained)
- High: 100K reads per cell (for rare transcripts or allele-specific expression)

### ATAC-seq

**Sample requirements:**
- 4-5 biological replicates per condition (minimum)
- More replicates needed for differential accessibility (>n=6 preferred)
- Fewer replicates acceptable for peak calling only (n=2-3)

**Depth recommendations:**
- Peak calling: 25 million reads
- Differential accessibility: 40-50 million reads
- Transcription factor footprinting: 100-200 million reads

**Design considerations:**
- ATAC-seq has higher technical variability than RNA-seq
- Consider including spike-in controls for normalization
- Fresh tissue strongly preferred over frozen

### ChIP-seq

**Sample requirements:**
- Narrow peaks (TFs): 2-3 replicates minimum, 4-5 preferred
- Broad peaks (histone marks): 3-4 replicates minimum
- Input/IgG controls: Match number of treatment samples

**Depth recommendations:**
- Narrow peaks: 20 million reads
- Broad peaks: 40 million reads
- Quality matters more than quantity (high enrichment ratio)

**Design considerations:**
- Input or IgG control required for each sample
- Antibody quality is critical (always validate)
- Consider spike-in normalization for comparing conditions

---

## Common Design Pitfalls

### Pitfall 1: Confounding Batch with Condition

**Problem:** All control samples processed in Batch 1, all treatment samples in Batch 2

**Why it's bad:**
- Cannot distinguish treatment effect from batch effect
- Statistical adjustment cannot fully remove confounded effects
- Results may be entirely artifactual

**Solution:**
- Each batch must contain samples from all conditions
- Use balanced batch assignment (see batch_effect_mitigation.md)
- Validate design with `check_confounding()` function

### Pitfall 2: Pooling Instead of Replicating

**Problem:** Pooling multiple individuals into one sample to save sequencing costs

**Why it's bad:**
- Loses all information about biological variability
- No statistical inference possible (n=1)
- Cannot identify outliers or sample-specific effects
- Reduces power to detect differences

**Solution:**
- Keep samples separate and sequence individually
- If budget-constrained, reduce sequencing depth rather than pooling
- Biological replicates > high depth

### Pitfall 3: Pseudoreplication

**Problem:** Treating technical replicates, repeated measurements, or cells from same individual as independent samples

**Examples:**
- Sequencing same library twice and calling it "2 replicates"
- Taking 3 measurements from same individual and treating as n=3
- Using 1000 cells from one person as n=1000 (should be n=1)

**Why it's bad:**
- Inflates sample size and statistical significance
- Underestimates variability
- Violates independence assumption of statistical tests
- Cannot generalize to population

**Solution:**
- Biological replicates = different individuals/samples
- Account for repeated measures in mixed-effects models
- For single-cell: samples are biological replicates, cells are subsamples

### Pitfall 4: Underpowered Studies

**Problem:** Using too few replicates to detect biologically meaningful effects

**Why it's bad:**
- High false negative rate (missing true effects)
- Detected effects may be inflated (winner's curse)
- Wastes resources on inconclusive experiments
- May miss important biology

**Solution:**
- Run power analysis before starting experiment
- Target power ≥0.80 for effects of interest
- Consider pilot study to estimate variability
- Be realistic about detectable effect sizes

### Pitfall 5: Ignoring Sample Size Requirements for Multiple Testing

**Problem:** Planning sample size for detecting one gene, forgetting genome-wide testing correction

**Why it's bad:**
- Multiple testing correction (FDR, Bonferroni) reduces effective significance threshold
- May have good power for individual test but poor power after correction
- Need larger sample sizes for genome-wide studies than candidate gene studies

**Solution:**
- Consider number of tests when calculating sample size
- Use appropriate alpha correction in power calculations
- For RNA-seq: typically 15,000-20,000 tests (genes)
- Consider modern methods like IHW that can improve power

### Pitfall 6: Post-hoc Power Analysis

**Problem:** Calculating power after experiment is completed and results are known

**Why it's bad:**
- Provides no new information beyond the p-value
- Often used to explain away non-significant results
- Power analysis is for planning, not interpretation
- Logically circular reasoning

**Solution:**
- Only perform power analysis during experimental design phase
- If study is underpowered, acknowledge as limitation
- Do not calculate post-hoc power for interpretation

---

## Sample Size Guidelines Summary

### Quick Reference Table

| Assay Type | Minimum n | Standard n | High-confidence n |
|------------|-----------|------------|-------------------|
| Bulk RNA-seq | 3 | 5-6 | 10+ |
| scRNA-seq (samples) | 3 | 5-6 | 8-10 |
| ATAC-seq | 4 | 6-8 | 10+ |
| ChIP-seq (narrow) | 2 | 4-5 | 6+ |
| ChIP-seq (broad) | 3 | 4-5 | 6+ |
| Methylation array | 5 | 8-10 | 15+ |
| Proteomics (TMT) | 3 | 5-6 | 8+ |

**Note:** These are per-condition sample sizes. Increase for small effects or high variability.

### Effect Size Considerations

Multiply standard n by these factors for different effect sizes:

- **Large effects (≥2-fold change):** Use standard n
- **Moderate effects (1.5-2 fold):** Multiply by 1.5-2×
- **Small effects (1.2-1.5 fold):** Multiply by 3-4×
- **Very small effects (<1.2-fold):** May need 20-50+ replicates; consider if biologically meaningful

---

## Budget Optimization Strategies

### Strategy 1: Optimize Depth vs. Replicates

**Approach:** Find optimal balance between sequencing depth and number of samples

**When to use:**
- Fixed total sequencing budget
- Flexible experimental design

**Method:**
1. Calculate power across range of (depth, sample size) combinations
2. Identify combinations that achieve target power (≥0.80)
3. Choose combination with lowest total cost
4. Generally favors more samples at moderate depth

### Strategy 2: Staged Experiments

**Approach:** Run pilot → analyze → adjust → run main experiment

**When to use:**
- High uncertainty about effect sizes or variability
- Large planned experiment with major cost
- Novel experimental system or assay

**Benefits:**
- More accurate sample size for main study
- Validate protocols before full commitment
- Can stop early if effects are not detectable
- Reduces wasted resources

### Strategy 3: Adaptive Sample Size

**Approach:** Plan sequential batches with interim analysis

**When to use:**
- Very expensive experiments
- High uncertainty about effect sizes
- Ethical considerations for minimizing samples (animal studies)

**Method:**
1. Start with minimum n per group (e.g., n=3-4)
2. Analyze data with interim analysis rules
3. Decide to stop (if clear result) or add more samples
4. Requires pre-specified stopping rules to control error rates

**Caution:** Must use proper group sequential methods to control Type I error

### Strategy 4: Focus on Fewer Conditions

**Approach:** Prioritize most important comparisons, reduce number of groups

**When to use:**
- Many planned conditions but limited budget
- Some comparisons more critical than others

**Method:**
- Identify primary hypothesis and key comparisons
- Reduce secondary comparisons or conditions
- Allocate more replicates to primary comparisons
- Can add exploratory conditions at reduced depth

---

## Documentation Requirements

Always document the following in your experimental design:

### Required Information
- Number of biological replicates per condition
- Sequencing depth per sample
- Batch structure and assignment
- Randomization scheme
- Covariate balance strategy
- Expected effect sizes and power calculations
- Multiple testing correction method
- Statistical analysis plan

### Recommended Information
- Pilot study results (if available)
- Sample collection and processing protocols
- Quality control criteria for sample inclusion
- Backup plan if samples fail QC
- Timeline and batch processing schedule
- Software versions for power calculations

### For Publications and Grants
- Power analysis with assumptions clearly stated
- Sample size justification
- Statistical analysis plan
- Randomization and blinding procedures
- How batch effects will be handled
- Multiple testing correction approach

---

## When to Consult a Statistician

Consider consulting a biostatistician for:

- **Complex designs:** Multi-factor, repeated measures, hierarchical structures
- **Unusual data types:** Novel assays, complex count structures
- **Grant applications:** Especially for large-scale or costly experiments
- **Multi-site studies:** Coordinating across institutions
- **Adaptive designs:** Sequential sampling, interim analyses
- **Special populations:** Rare diseases, limited sample availability
- **Regulatory submissions:** Clinical trials, FDA submissions

**Best timing:** Consult during design phase, not after data collection

---

## Additional Resources

- [power_analysis_guidelines.md](power_analysis_guidelines.md) - Detailed power calculation methods
- [batch_effect_mitigation.md](batch_effect_mitigation.md) - Preventing and controlling batch effects
- [multiple_testing_guide.md](multiple_testing_guide.md) - Choosing correction methods
- [qc_guidelines.md](qc_guidelines.md) - Quality control checkpoints
- [cv_tissue_database.csv](cv_tissue_database.csv) - Coefficient of variation by tissue type

---

**Last Updated:** 2026-01-28
**Version:** 1.0
