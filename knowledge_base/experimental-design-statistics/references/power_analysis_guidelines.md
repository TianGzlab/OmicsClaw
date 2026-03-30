# Power Analysis Guidelines

This document provides detailed guidance on performing power analysis for genomics experiments, including methodology, interpretation, and assay-specific considerations.

---

## Power Analysis Fundamentals

### What Is Statistical Power?

**Definition:** Power is the probability of detecting a true effect when it exists (avoiding false negatives).

**Formula:** Power = 1 - β, where β is the Type II error rate

**Key Concept:** Power tells you how likely your experiment is to find a real biological difference if it's actually there.

### Components of Power Analysis

Power depends on four interconnected parameters:

1. **Effect size (δ):** Magnitude of the biological difference (e.g., fold-change)
2. **Sample size (n):** Number of biological replicates per group
3. **Significance level (α):** Threshold for declaring significance (typically 0.05)
4. **Variability (σ):** Biological and technical variation in measurements

**Key relationship:** Larger effect sizes, larger sample sizes, and lower variability all increase power.

### Power Analysis Types

**Prospective (a priori) power analysis:**
- Performed BEFORE data collection
- Determines required sample size for target power
- Used for experimental design and grant applications
- **This is the standard and recommended approach**

**Retrospective (post-hoc) power analysis:**
- Calculated AFTER experiment is complete
- Generally NOT recommended - provides no additional information beyond p-value
- Often misused to explain away negative results
- **Avoid this approach**

---

## Power Analysis Workflow

### Step 1: Define Your Effect Size

**What effect size should you use?**

**Option A: Minimum biologically meaningful effect**
- What's the smallest difference that would be scientifically important?
- For RNA-seq: typically 1.5-2 fold change minimum
- For ATAC-seq: similar, 1.5-2 fold change
- For proteomics: 1.3-1.5 fold change (more compressed dynamic range)

**Option B: Expected effect from literature**
- Search for similar studies in your system
- Extract reported fold-changes for key genes/features
- Use median or typical effect sizes
- Be conservative - published effects often overestimated (winner's curse)

**Option C: From pilot data (most accurate)**
- Run small pilot experiment (n=2-3 per group)
- Analyze differential expression/accessibility
- Use observed effect sizes for power calculations
- Accounts for your specific system and conditions

**Realistic expectations by assay:**
- Bulk RNA-seq: Strong drug treatments show 2-4 fold changes for responsive genes
- scRNA-seq: Cell type markers show 3-10+ fold differences; subtle effects 1.2-1.5 fold
- ATAC-seq: Accessible regions show 1.5-3 fold changes
- ChIP-seq: Enrichment ratios 2-10 fold for true binding sites

### Step 2: Estimate Variability

**Sources of variability:**
- **Biological variation:** Individual-to-individual differences (usually dominates)
- **Technical variation:** Library prep, sequencing, batch effects (usually minor with modern protocols)

**How to estimate variability:**

**Option A: Coefficient of Variation (CV) from literature**
- CV = σ / μ (standard deviation / mean)
- Tissue-specific estimates available in [cv_tissue_database.csv](cv_tissue_database.csv)
- Typical CV values:
  - Low variability (cell lines, model organisms): CV = 0.2-0.3
  - Moderate variability (inbred animals, controlled conditions): CV = 0.3-0.5
  - High variability (human cohorts, outbred populations): CV = 0.5-0.8
  - Very high variability (heterogeneous diseases, complex traits): CV = 0.8-1.5

**Option B: Dispersion from pilot data (recommended)**
- DESeq2 dispersion parameter captures count variability
- More accurate than fixed CV assumptions
- Accounts for mean-variance relationship in count data
- Use `power_pilot_based.R` script with pilot DESeq2 object

**Option C: Conservative assumptions**
- If no pilot data and uncertain about variability, use high end of range
- Better to overestimate variability (get adequate power) than underestimate
- Human studies: assume CV ≥ 0.5
- Animal studies: assume CV ≥ 0.3

### Step 3: Set Target Power and Significance Level

**Standard thresholds:**
- **Power ≥ 0.80 (80%):** Standard for most experiments
- **Power ≥ 0.90 (90%):** Higher confidence, often required for grants or clinical studies
- **Alpha = 0.05:** Standard significance level

**When to use higher power:**
- Expensive experiments (want to avoid false negatives)
- Follow-up validation studies
- Clinical or translational applications
- Grant proposals (reviewers expect 80-90% power)

**When lower power might be acceptable:**
- Exploratory pilot studies (power ~0.60-0.70 acceptable)
- Hypothesis generation (less stringent)
- Sample-limited scenarios where you can't reach 0.80

### Step 4: Perform Power Calculation

**For RNA-seq/ATAC-seq/count-based assays:**

Use power calculation scripts provided:
- [power_rnaseq.R](../scripts/power_rnaseq.R) - RNA-seq power with CV assumptions
- [power_pilot_based.R](../scripts/power_pilot_based.R) - Power from pilot DESeq2 dispersions
- [power_atacseq.R](../scripts/power_atacseq.R) - ATAC-seq specific power

**General approach:**
1. Fix effect size (fold-change)
2. Fix variability (CV or dispersion)
3. Fix significance level (alpha)
4. Solve for sample size that gives target power

**Or inversely:**
1. Fix sample size (if constrained)
2. Calculate achievable power
3. Determine minimum detectable effect size

### Step 5: Interpret Results and Make Decisions

**Power ≥ 0.80:** Experiment adequately powered ✓
- Proceed with planned design
- Document assumptions in analysis plan

**Power = 0.60-0.79:** Moderately powered (⚠️ borderline)
- Consider increasing sample size if feasible
- Or accept lower power if exploratory
- Acknowledge as limitation

**Power < 0.60:** Underpowered ❌
- High risk of false negatives
- Consider redesigning:
  - Increase sample size
  - Increase sequencing depth
  - Focus on larger effects only
  - Run pilot to refine estimates
- May not be worth conducting experiment

---

## Assay-Specific Power Considerations

### Bulk RNA-seq Power Analysis

**Tools:**
- `RNASeqPower` package - Fast, based on Hart et al. (2013) method
- `ssizeRNA` package - More sophisticated, accounts for multiple testing
- `DESeq2` + pilot data - Most accurate for your specific system

**Typical parameters:**
- Mean read count: 20-100 reads for lowly expressed genes (CV highest here)
- Dispersion: 0.1-0.4 (decreases with mean expression)
- Effect size: 1.5-2 fold change minimum for DE
- Tests: ~15,000-20,000 genes (affects multiple testing correction)

**Key considerations:**
- Power varies by expression level (lower power for lowly expressed genes)
- Pilot data highly valuable for accurate dispersion estimates
- Can focus power analysis on "interesting" expression range

**Sample size recommendations:**
- Detect 2-fold changes: n=3-5 per group (adequate power)
- Detect 1.5-fold changes: n=6-10 per group
- Detect <1.5-fold changes: n=10-20+ per group (may not be feasible)

### Single-Cell RNA-seq Power Analysis

**Unique challenges:**
- Two levels of variation: cell-to-cell and sample-to-sample
- Dropout (zero inflation) complicates power
- Large number of cells doesn't substitute for biological replicates

**Tools:**
- `powsimR` package - Comprehensive scRNA-seq power simulation
- `scPower` package - Power for detecting differential expression

**Key principle:** More samples >> more cells per sample

**Typical parameters:**
- Goal-dependent cell numbers:
  - Discovery: 3000-10000 cells total per condition
  - Differential expression: 500-2000 cells per cell type
  - Rare cell types: 10,000-50,000 cells to ensure representation
- Biological replicates: 5-6 samples per condition (more important than cell count)
- Depth: 50K reads/cell standard, 20K minimum

**Sample size recommendations:**
- Cell type discovery: n=3-4 samples, 3000+ cells per sample
- Differential expression: n=5-6 samples, 1000-2000 cells per sample
- Trajectory inference: n=4-6 samples, 3000-5000 cells per sample

**Power analysis approach:**
1. Determine required cells per cell type for adequate power (accounting for dropout)
2. Estimate cell type proportions from pilot or literature
3. Calculate total cells needed per sample
4. Determine number of samples needed for biological replication
5. Biological replicates are more important than cell numbers

### ATAC-seq Power Analysis

**Similar to RNA-seq but with differences:**
- Peaks as features (~50,000-150,000 total peaks depending on cell type)
- Lower mean counts than RNA-seq (affects power)
- Higher variability in some peak regions

**Tools:**
- Adapt RNA-seq power tools (conservative approach)
- `csaw` package for ChIP/ATAC power simulation
- Pilot-based dispersion estimation (recommended)

**Typical parameters:**
- Number of peaks: 50,000-150,000
- Mean counts in peaks: 10-100 reads
- Dispersion: 0.2-0.5 (higher than RNA-seq)
- Effect size: 1.5-2 fold change for differential accessibility

**Sample size recommendations:**
- Detect 2-fold changes: n=4-6 per group
- Detect 1.5-fold changes: n=8-10 per group
- More replicates needed than RNA-seq due to higher variability

### ChIP-seq Power Analysis

**Challenges:**
- Depends heavily on antibody quality and ChIP efficiency
- Narrow peaks (TFs) vs. broad peaks (histone marks) have different characteristics
- Background binding affects signal-to-noise

**Tools:**
- `spp` package for peak calling QC
- Pilot-based approach (highly recommended)
- ENCODE guidelines for replicate concordance

**Typical parameters:**
- Narrow peaks: 10,000-50,000 peaks
- Broad peaks: 50,000-200,000 enriched regions
- Enrichment ratio: 2-10 fold for true binding
- Input/IgG control required for each sample

**Sample size recommendations:**
- Peak calling only: n=2 minimum (ENCODE standard)
- Differential binding: n=3-4 minimum, n=5-6 preferred
- Quality (enrichment) matters more than quantity
- Biological variation can be very high for some marks

---

## Common Power Analysis Scenarios

### Scenario 1: Two-Group Comparison (Most Common)

**Setup:** Control vs. Treatment

**Parameters to specify:**
- n per group
- Expected fold-change
- Variability (CV or dispersion)
- Alpha level (0.05)

**R code example:**
```r
source("scripts/power_rnaseq.R")
power <- calc_power_rnaseq(
  depth = 20,          # Million reads
  n_per_group = 5,     # Biological replicates per group
  cv = 0.4,            # Coefficient of variation
  fold_change = 2,     # 2-fold effect
  alpha = 0.05         # Significance level
)
```

### Scenario 2: Multi-Group Comparison

**Setup:** 3+ conditions (e.g., Control, Treatment A, Treatment B)

**Considerations:**
- More groups require more samples for same power
- Multiple pairwise comparisons reduce power
- May focus power on specific contrasts of interest

**Approach:**
- Calculate power for each pairwise comparison of interest
- Sample size should support primary hypothesis
- Secondary comparisons may have lower power (acceptable if exploratory)

**Sample size adjustment:**
- For k groups with equal n per group, and interest in all pairwise comparisons:
- Rough guideline: increase n by factor of √k compared to two-group design

### Scenario 3: Paired Samples (Before/After)

**Setup:** Same individuals measured at two timepoints or conditions

**Advantages:**
- Controls for individual variation
- Higher power than independent samples
- Can use fewer replicates (n=4-5 often sufficient)

**Power analysis:**
- Use paired t-test framework
- Variability is within-subject change (typically lower than between-subject)
- Effect size is mean difference / SD of differences

**Sample size:**
- Typically need 30-50% fewer samples than unpaired design
- n=4-5 often adequate for paired design
- n=3 minimum (only for very large effects)

### Scenario 4: Multi-Factor Design

**Setup:** Two or more factors (e.g., Treatment × Time)

**Considerations:**
- Need samples for all factor combinations
- Interaction effects typically smaller than main effects
- May need more replicates to detect interactions

**Power analysis approach:**
- Calculate power for main effects and interactions separately
- Prioritize primary hypothesis (main effect or interaction?)
- May need n=6-8 per cell for adequate interaction power

### Scenario 5: Pilot Study for Future Main Study

**Setup:** Small pilot to inform larger study

**Goals:**
- Estimate effect sizes and variability
- Validate protocols
- Calculate accurate power for main study

**Recommended pilot size:**
- Minimum: n=2-3 per group (very rough estimates)
- Better: n=4-5 per group (more reliable estimates)
- Full depth sequencing to match main study

**Using pilot results:**
```r
source("scripts/power_pilot_based.R")
pilot_dds <- readRDS("pilot_deseq2.rds")  # From pilot analysis
main_study_n <- calc_sample_size_from_pilot(
  pilot_dds = pilot_dds,
  fold_change = 1.5,  # Target effect to detect in main study
  power = 0.8,
  fdr = 0.05
)
```

---

## Depth vs. Sample Size Trade-offs

### When Depth Matters More

**Increase depth (not just sample size) when:**
- Very low current depth (< 10M for RNA-seq)
- Interested in rare transcripts or isoforms
- Need allele-specific expression
- Low-input samples (degraded RNA, small cell populations)

### When Sample Size Matters More

**Increase samples (not depth) when:**
- Already at standard depth (20M+ for RNA-seq)
- Interested in differential expression of moderate/high abundance genes
- High biological variability expected
- Want to detect smaller effect sizes
- Want robust, reproducible results

### Mathematical Relationship

**Approximate relationship (from Schurch et al. 2016):**
- Doubling sequencing depth increases power by ~10-20%
- Doubling sample size increases power by ~40-50%

**Cost-effectiveness:**
- If sequencing costs scale linearly, more samples usually better investment
- Exception: Very low depth where you miss many features

### Optimization Approach

1. Set minimum acceptable depth for your assay
2. Calculate power across range of sample sizes at that depth
3. If power insufficient, first try increasing n
4. Only increase depth if already at maximum feasible n

---

## Multiple Testing Considerations

### Why Multiple Testing Matters for Power

**Key insight:** Testing 20,000 genes requires more stringent significance threshold than testing 1 gene

**Effect on power:**
- Benjamini-Hochberg FDR at 0.05 roughly equivalent to individual tests at α ≈ 0.001-0.01
- More stringent threshold requires larger effects or more samples for same power
- Must account for this in power calculations

### Accounting for Multiple Testing

**Approach 1: Adjust alpha in power calculation**
- Use effective alpha after multiple testing correction
- For BH-FDR at 0.05: use α ≈ 0.005-0.01 in power calculation
- Conservative but simple

**Approach 2: Use specialized tools**
- `ssizeRNA` package accounts for multiple testing explicitly
- More accurate but requires more assumptions

**Approach 3: Focus on proportion of discoveries**
- Calculate power to detect X% of truly DE genes
- More realistic for genomics experiments
- Acknowledges won't detect all true effects

### Modern Multiple Testing Methods

**Independent Hypothesis Weighting (IHW):**
- Data-driven weighting increases power
- Can gain 10-30% more discoveries than BH-FDR
- Recommended for RNA-seq when mean expression varies widely

**Adaptive shrinkage (ashr, lfcShrink):**
- Improves effect size estimates
- Can improve power for small effect sizes
- Recommended for DESeq2 workflow

See [multiple_testing_guide.md](multiple_testing_guide.md) for detailed guidance.

---

## Reporting Power Analysis

### For Grant Applications

**Required information:**
- Effect size assumptions and justification
- Variability estimates and source
- Target power and significance level
- Sample size calculation with methods
- Software/tools used
- Reference to statistical methods paper

**Example text:**
> "Sample size was determined using power analysis for RNA-seq experiments (Hart et al. 2013) as implemented in the RNASeqPower package. Assuming a coefficient of variation of 0.4 (typical for mouse liver tissue), sequencing depth of 20 million reads per sample, and targeting 80% power to detect 2-fold changes at FDR < 0.05, we require n=5 biological replicates per group. This sample size provides >90% power to detect 3-fold changes and ~60% power to detect 1.5-fold changes."

### For Publications

**Methods section should include:**
- Sample size and how it was determined
- Effect sizes that could be detected with stated power
- Assumptions about variability
- Multiple testing correction method
- Any deviations from pre-specified plan

**Example text:**
> "Sample size (n=6 per group) was chosen to provide 80% power to detect 2-fold expression changes assuming coefficient of variation of 0.5 and FDR-corrected significance threshold of 0.05, based on pilot data (n=3 per group) and power calculations using the RNASeqPower package."

### Common Mistakes to Avoid

❌ **Don't:** Calculate post-hoc power after seeing results
❌ **Don't:** Use underpowered n and claim "pilot study" (be explicit if exploratory)
❌ **Don't:** Ignore multiple testing correction in power calculation
❌ **Don't:** Assume published effect sizes (often inflated)
❌ **Don't:** Claim adequate power without showing calculations

✅ **Do:** Calculate power during design phase
✅ **Do:** Document all assumptions clearly
✅ **Do:** Use pilot data when available
✅ **Do:** Account for multiple testing
✅ **Do:** Report what effects you had power to detect

---

## Software and Tools

### R Packages for Power Analysis

| Package | Best For | Key Functions |
|---------|----------|---------------|
| `RNASeqPower` | Bulk RNA-seq, fast calculations | `rnapower()`, `rnasize()` |
| `ssizeRNA` | Bulk RNA-seq, pilot-based | `ssizeRNA_single()`, `ssizeRNA_vary()` |
| `powsimR` | scRNA-seq comprehensive | `estimateParam()`, `simulateDE()` |
| `pwr` | General power (t-tests, etc.) | `pwr.t.test()`, `pwr.anova.test()` |
| `ssize.fdr` | FDR-based sample size | `ssize.twoSampVary()` |

### Workflow Scripts

Use the provided scripts for common power calculations:
- [power_rnaseq.R](../scripts/power_rnaseq.R) - RNA-seq power with CV
- [power_pilot_based.R](../scripts/power_pilot_based.R) - Pilot-based power
- [power_atacseq.R](../scripts/power_atacseq.R) - ATAC-seq power
- [sample_size_de.R](../scripts/sample_size_de.R) - Sample size determination
- [sample_size_scrna.R](../scripts/sample_size_scrna.R) - scRNA-seq sample size

---

## Additional Resources

**Key Papers:**
- Hart SN et al. (2013) "Calculating Sample Size Estimates for RNA Sequencing Data." *J Comput Biol* 20(12):970-978
- Schurch NJ et al. (2016) "How many biological replicates are needed in an RNA-seq experiment." *RNA* 22(6):839-851
- Ching T et al. (2014) "Power analysis and sample size estimation for RNA-Seq differential expression." *RNA* 20(11):1684-1696

**Related Guides:**
- [experimental_design_best_practices.md](experimental_design_best_practices.md) - Overall design principles
- [batch_effect_mitigation.md](batch_effect_mitigation.md) - Batch design considerations
- [cv_tissue_database.csv](cv_tissue_database.csv) - Tissue-specific CV estimates

---

**Last Updated:** 2026-01-28
**Version:** 1.0
