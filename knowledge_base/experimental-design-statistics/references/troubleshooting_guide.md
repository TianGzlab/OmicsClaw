# Troubleshooting Guide

Solutions to common issues in experimental design.

---

## Power Analysis Issues

### Issue: Power too low (<0.60)

**Symptoms:**
- Calculated power is 0.40-0.60 for proposed design
- Concerned study will miss true effects

**Solutions:**

1. **Increase sample size** (most effective)
   ```r
   # Calculate required n for 80% power
   required_n <- calc_sample_size_rnaseq(
     depth = 20,
     cv = 0.4,
     fold_change = 2,
     target_power = 0.8
   )
   ```

2. **Increase sequencing depth** (partial solution)
   - Diminishing returns beyond ~30M reads for RNA-seq
   - Better to add samples than excessive depth
   - Rule of thumb: 3 samples at 20M > 2 samples at 30M

3. **Relax effect size threshold**
   - If power too low for 1.5-fold, consider 2-fold
   - Document biological justification for larger threshold

4. **Reduce biological variability (if possible)**
   - Use more homogeneous samples (age-matched, etc.)
   - Improve experimental protocols
   - Standardize sample collection

---

### Issue: Required sample size exceeds budget

**Symptoms:**
- Power analysis says need 15/group
- Budget only supports 8/group

**Solutions:**

1. **Optimize depth vs. replicates trade-off**
   ```r
   # Calculate power for different depth/n combinations
   # Option A: 8 samples at 30M reads
   # Option B: 10 samples at 20M reads
   # Option C: 12 samples at 15M reads

   # Usually more samples wins
   ```

2. **Detect larger effects only**
   - Calculate what fold-change is detectable with your budget
   - Document this limitation clearly

3. **Conduct pilot study first**
   - Use smaller pilot to refine power estimates
   - May reveal lower variability than expected

4. **Consider alternative designs**
   - Paired design (lower variability)
   - Use existing published data as historical controls (careful!)

---

### Issue: No pilot data for CV estimation

**Symptoms:**
- Starting new project without pilot data
- Unsure which CV to use

**Solutions:**

1. **Use literature CV estimates**
   - Check [cv_tissue_database.csv](cv_tissue_database.csv)
   - Find similar tissue/organism/assay
   - Be conservative (use higher CV to be safe)

2. **Check published studies in your field**
   - Look for papers with same tissue/assay
   - Extract dispersion from supplementary data
   - Contact authors if needed

3. **Use general rules of thumb:**
   - Cell lines: 0.1-0.2
   - Inbred mice: 0.2-0.3
   - Human samples: 0.4-0.5
   - When unsure, use 0.4 (conservative)

4. **Conduct small pilot first**
   - Even 2-3 samples per group helps
   - Use `estimate_cv_from_pilot()` to extract CV

---

### Issue: Pilot data shows higher variability than expected

**Symptoms:**
- Extracted CV from pilot is 0.6-0.8
- Much higher than literature estimates

**Solutions:**

1. **Verify pilot data quality**
   - Check for outliers
   - Review QC metrics
   - Check for batch effects in pilot

2. **Investigate sources of variation**
   - Sample collection issues?
   - Technical variation (prep, extraction)?
   - Hidden batch effects?

3. **Reduce variability if possible**
   - Standardize collection protocols
   - Train all operators
   - Use fresh samples (not degraded)

4. **Increase sample size accordingly**
   - Trust your pilot data
   - Plan for higher variability
   - May need 1.5-2× more samples

---

## Batch Design Issues

### Issue: Batch confounded with condition 🚨 CRITICAL

**Symptoms:**
- `check_confounding()` shows p < 0.05
- All control samples in batch 1, all treatment in batch 2

**Solutions:**

1. **STOP - Do not proceed with this design**
   - Cannot separate batch from biological effects
   - Results will be uninterpretable

2. **Regenerate batch assignment**
   ```r
   # Regenerate with correct parameters
   batch_design <- assign_samples_to_batches(
     metadata = metadata,
     batch_size = 8,
     balance_vars = c("condition", "sex")  # Ensure condition included
   )

   # Verify
   check_confounding(batch_design, "condition")
   ```

3. **If confounding persists:**
   - Check batch_size allows balance
   - May need to adjust batch_size
   - Ensure n per condition is divisible by number of batches

4. **Extreme case - forced sequential batches:**
   - If truly cannot balance (e.g., time-course with single timepoint/batch)
   - Use very strong controls across batches
   - Acknowledge severe limitation
   - Consider alternative design

---

### Issue: Cannot balance all conditions in batches

**Symptoms:**
- Have 3 conditions, batch size of 8
- Cannot get equal representation

**Solutions:**

1. **Use incomplete block design**
   ```r
   batch_design <- incomplete_block_design(
     metadata = metadata,
     batch_size = 8,
     primary_var = "condition",  # MUST balance this
     secondary_vars = c("sex")   # Balance as possible
   )
   ```

2. **Adjust batch size**
   - Try different batch sizes
   - Batch size should ideally be multiple of n_conditions
   - Example: 3 conditions → batch_size = 9, 12, 15

3. **Accept slight imbalance**
   - As long as no complete confounding
   - Example: batch 1 has 3/3/2, batch 2 has 3/3/3
   - Document and include batch as covariate

---

### Issue: Sample failure during processing

**Symptoms:**
- One sample failed QC during library prep
- Batch design now unbalanced

**Solutions:**

1. **Document the failure**
   - Note which sample, which batch, why
   - Keep in metadata as "failed"

2. **Do NOT replace from different condition**
   - Bad: Replace failed "control" with another "treatment"
   - This creates confounding

3. **Options for replacement:**
   - Add replacement to NEXT batch (proportional distribution)
   - Or accept slightly unbalanced design
   - Or add replacement to all remaining batches

4. **Statistical approach:**
   - Note imbalance in analysis
   - Use robust methods (DESeq2 handles unbalanced)
   - May slightly reduce power

---

### Issue: Batch processing delayed by weeks

**Symptoms:**
- Planned to process all in 2 weeks
- Now taking 2 months due to delays

**Solutions:**

1. **Document timeline carefully**
   - Exact processing dates for each batch
   - Storage conditions during delays
   - Any protocol changes

2. **Consider "time" as batch variable**
   - Week 1 vs Week 8 may have systematic differences
   - Include date as covariate

3. **Add extra controls**
   - If >1 month between batches, add shared controls
   - Same control samples across time

4. **For future batches:**
   - Consider pausing to regroup
   - Process remaining samples closer together

---

## Sample Size Issues

### Issue: n=2 per group (insufficient)

**Symptoms:**
- Budget or samples limited to n=2
- Know this is problematic

**Solutions:**

1. **Strong recommendation: DO NOT PROCEED**
   - n=2 cannot estimate variance
   - Cannot perform valid statistical tests
   - Results will not be publishable

2. **Absolute minimum is n=3**
   - Even n=3 is marginal
   - n≥6 strongly recommended

3. **If truly stuck with n=2:**
   - Consider it a pilot study only
   - Use for hypothesis generation
   - Plan larger study to validate
   - Do not attempt statistical testing

---

### Issue: Paired design unclear if beneficial

**Symptoms:**
- Have matched samples (before/after)
- Unsure if pairing helps

**Solutions:**

1. **Estimate correlation from pilot**
   ```r
   # If you have pilot paired data
   library(DESeq2)
   # Create DESeq2 object with paired design
   dds <- DESeqDataSetFromMatrix(counts, coldata, design = ~pair + condition)
   # Check if dispersion lower than unpaired
   ```

2. **General rules:**
   - Pairing helpful if within-pair correlation >0.5
   - Before/after in same individual: Usually beneficial
   - Matched pairs (twins, litter-mates): Often beneficial
   - Matched by demographics only: Small benefit

3. **Sample size for paired:**
   - Assume 20-30% variance reduction
   - Calculate power with adjusted CV
   - `CV_paired = CV_unpaired × 0.7` (conservative)

---

## Multiple Testing Issues

### Issue: All p-values non-significant after correction

**Symptoms:**
- Have many raw p < 0.05
- After BH-FDR, all q > 0.05

**Solutions:**

1. **Check power**
   - Study may be underpowered
   - Recalculate power for observed effect sizes

2. **Try more powerful methods**
   ```r
   # IHW can identify 10-20% more discoveries
   ihw_results <- apply_ihw(pvalues, covariates = mean_expression, alpha = 0.05)

   # Compare to BH
   bh_results <- apply_bh_fdr(pvalues, q_threshold = 0.05)
   ```

3. **Check for technical issues**
   - Batch effects masking signal?
   - Poor sample quality?
   - Wrong statistical model?

4. **Consider q < 0.10 for exploratory**
   - If truly exploratory phase
   - Document as exploratory threshold
   - Validate hits in follow-up study

---

### Issue: Too many significant results (>50%)

**Symptoms:**
- After FDR correction, 60% genes significant
- Seems too high

**Solutions:**

1. **Check for technical artifacts**
   - Batch effect not properly corrected?
   - Library size normalization issue?
   - Check QC plots (PCA, sample clustering)

2. **Verify fold-changes are meaningful**
   - May have statistical significance but small effects
   - Filter by fold-change: q < 0.05 AND |FC| > 1.5

3. **Check if expected**
   - Some comparisons have large effects (e.g., tissue types)
   - Drugs/treatments can affect many genes
   - If biologically reasonable, may be real

---

### Issue: Unsure which correction method to use

**Symptoms:**
- Have p-values, need to choose correction
- Confused by options

**Solutions:**

1. **Use decision tree:**
   ```r
   recommendation <- recommend_method(
     n_tests = 20000,
     expected_true_positives = 2000,
     effect_heterogeneity = "moderate",
     sample_size = 6
   )
   print(recommendation)
   ```

2. **Simple rules:**
   - **Most genomics studies:** BH-FDR (q < 0.05)
   - **Candidate genes (<100):** Bonferroni
   - **GWAS:** Bonferroni (p < 5×10⁻⁸)
   - **Want more power + have covariate:** IHW

3. **When in doubt: BH-FDR**
   - Most widely accepted
   - Good balance of power and control
   - Reviewers will accept it

---

## Visualization Issues

### Issue: ggplot2 or ggprism not installed

**Symptoms:**
- Plotting functions fail
- "Package 'ggplot2' not found"

**Solutions:**

```r
# Install visualization packages
install.packages(c("ggplot2", "ggprism"))

# Verify installation
library(ggplot2)
library(ggprism)
```

---

### Issue: Plots not saving correctly

**Symptoms:**
- `ggsave()` doesn't create file
- File corrupted or wrong size

**Solutions:**

1. **Check file path**
   ```r
   # Use absolute path or check working directory
   getwd()  # Where are you?
   ggsave("/full/path/to/output.svg", plot = p, width = 8, height = 6, dpi = 300)
   ```

2. **Check permissions**
   - Can you write to that directory?
   - Try saving to home directory first

3. **Verify plot object exists**
   ```r
   # Make sure plot was created
   print(p)  # Should display plot
   ```

---

## Installation Issues

See [software_requirements.md](software_requirements.md) for detailed installation troubleshooting.

**Quick fixes:**

- **BiocManager fails:** Try specifying CRAN mirror explicitly
- **powsimR slow:** Normal, can take 30 minutes to install
- **Compilation errors (macOS):** Install Xcode Command Line Tools
- **Compilation errors (Linux):** Install libcurl, libssl, libxml2 dev packages

---

## Getting Additional Help

1. **Check other reference documents:**
   - [qc_guidelines.md](qc_guidelines.md) - Quality control checklists
   - [software_requirements.md](software_requirements.md) - Installation help

2. **Package-specific help:**
   - Bioconductor support: https://support.bioconductor.org/
   - Package documentation: `?functionName`

3. **Statistical consultation:**
   - Complex designs may benefit from statistician consultation
   - Especially for: unusual designs, very small n, complex batch structures

---

**Last Updated:** 2026-01-28
**Maintained by:** Knowhows Repository


---
