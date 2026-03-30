# Batch Effect Mitigation

This document provides comprehensive guidance on preventing, detecting, and controlling batch effects in genomics experiments through proper experimental design.

---

## What Are Batch Effects?

### Definition

**Batch effect:** Systematic non-biological variation introduced when samples are processed in separate groups (batches) at different times or under different conditions.

**Key principle:** Batch effects are technical artifacts, not biological signal. They can severely confound or obscure true biological differences.

### Common Sources of Batch Effects

**Sample processing:**
- Different days/weeks of sample processing
- Different technicians or operators
- Different reagent lots or batches
- Different equipment or instruments
- Different lab locations or facilities

**Library preparation:**
- Different library prep kits or lots
- Different barcoding plates
- Different adapters or indexes
- Time of day effects (temperature, humidity)

**Sequencing:**
- Different sequencing runs
- Different flow cells or lanes
- Different sequencing instruments
- Different base-calling software versions

**Computational:**
- Different alignment software versions
- Different reference genome versions
- Different analysis pipelines

### Impact of Batch Effects

**Magnitude:**
- Can be LARGER than biological effects of interest
- Often affect 20-50% of features in RNA-seq data
- Can create entirely spurious patterns in data

**Consequences:**
- False positives (detecting non-existent differences)
- False negatives (missing true biological signals)
- Inflated or deflated effect size estimates
- Poor reproducibility across studies
- Invalid biological conclusions

---

## The Cardinal Rule: Prevent Confounding

### What Is Confounding?

**Confounded design:** Batch is completely or partially correlated with experimental condition

**CRITICAL:** If batch is confounded with condition, you CANNOT distinguish biological effects from batch effects, even with statistical correction.

### Examples of Confounding (❌ BAD)

**Complete confounding (worst case):**
```
Batch 1: Control_1, Control_2, Control_3
Batch 2: Treatment_1, Treatment_2, Treatment_3
```
❌ All controls in one batch, all treatments in another
❌ Impossible to separate batch effect from treatment effect
❌ Any difference could be 100% batch artifact

**Partial confounding (still bad):**
```
Batch 1: Control_1, Control_2, Treatment_1
Batch 2: Control_3, Treatment_2, Treatment_3
```
❌ Unbalanced conditions across batches
❌ Statistical adjustment has limited power
❌ Results remain questionable

### Non-Confounded Design (✅ GOOD)

**Balanced design:**
```
Batch 1: Control_1, Control_2, Treatment_1, Treatment_2
Batch 2: Control_3, Control_4, Treatment_3, Treatment_4
```
✅ Each batch contains all conditions
✅ Conditions balanced across batches
✅ Can estimate and remove batch effects
✅ Valid biological inference possible

**Key principle:** Every batch must contain samples from ALL experimental conditions in balanced proportions.

---

## Batch Design Strategies

### Strategy 1: Completely Randomized Batch Assignment

**When to use:**
- Single experimental factor (e.g., case vs. control)
- No important covariates to balance

**Method:**
1. List all samples with their condition labels
2. Randomly assign samples to batches
3. Ensure each batch has equal numbers of each condition
4. Verify no confounding with `check_confounding()` function

**R code:**
```r
source("scripts/batch_assignment.R")
batch_design <- assign_samples_to_batches(
  metadata = sample_metadata,
  batch_size = 8,
  balance_vars = "condition"
)
```

### Strategy 2: Stratified Randomization

**When to use:**
- Important covariates that should be balanced (sex, age, site)
- Want to ensure balance across batches

**Method:**
1. Identify variables to balance (condition + covariates)
2. Create strata for each covariate combination
3. Randomly assign samples within strata to batches
4. Maximize balance across all variables

**R code:**
```r
batch_design <- assign_samples_to_batches(
  metadata = sample_metadata,
  batch_size = 8,
  balance_vars = c("condition", "sex", "age_group")
)
```

**Important covariates to consider:**
- Sex/gender (major effect in many tissues)
- Age or developmental stage
- Genetic background or ancestry
- Collection site (multi-site studies)
- Disease severity or subtype
- Time of sample collection

### Strategy 3: Blocked Design

**When to use:**
- Paired samples (before/after treatment)
- Matched samples (case-control pairs)
- Want to minimize within-pair batch differences

**Method:**
1. Identify paired or matched samples
2. Process paired samples in same batch when possible
3. If pairs must span batches, balance pair distribution
4. Account for pairing in statistical model

**Example:**
```
Batch 1: Patient1_Before, Patient1_After, Patient2_Before, Patient2_After
Batch 2: Patient3_Before, Patient3_After, Patient4_Before, Patient4_After
```
✅ Paired samples in same batch (preferred)
✅ Or balanced across batches if necessary

### Strategy 4: Reference Sample Design

**When to use:**
- Multiple batches that cannot be processed simultaneously
- Want to empirically calibrate batch effects
- Large studies spanning many processing days

**Method:**
1. Create pool of reference RNA/DNA from all samples
2. Include 1-2 reference aliquots in EVERY batch
3. Use reference samples to estimate and correct batch effects
4. Helps detect technical drift over time

**Benefits:**
- Enables empirical batch correction
- Detects processing quality issues early
- Allows comparison across batches
- Standard in large-scale studies (GTEX, TCGA)

---

## Batch Size Considerations

### Optimal Batch Size

**Key trade-offs:**
- **Smaller batches:** More batches, higher risk of batch effects, harder to balance
- **Larger batches:** Fewer batches, easier to balance, but logistically challenging

**Recommendations by assay:**

| Assay | Typical Batch Size | Considerations |
|-------|-------------------|----------------|
| Bulk RNA-seq | 8-24 samples | Library prep plate size (8, 12, 24, 96) |
| scRNA-seq | 4-8 samples | 10X lane capacity, complexity |
| ATAC-seq | 8-12 samples | Tagmentation variability, library prep |
| ChIP-seq | 4-8 samples | ChIP success rate, antibody lot |
| Methylation array | 96 samples | Array plate format (96-well) |
| Proteomics (TMT) | 6-16 samples | TMT plex size (6, 10, 16, 18-plex) |

### Determining Batch Size

**Approach 1: Divide by number of conditions**
- For k conditions, use batch size = k × m where m ≥ 2
- Example: 3 conditions, batch size = 6, 9, or 12
- Ensures multiple replicates per condition per batch

**Approach 2: Match experimental constraints**
- Library prep kit size (e.g., 12-plex barcoding)
- Sequencing lane capacity
- Processing time constraints (all samples same day)
- Technician availability

**Approach 3: Minimize number of batches**
- Fewer batches = less batch effect variation
- Process all samples together if possible (small experiments)
- For large studies, batch size 10-20 samples optimal

### Multi-Site Studies

**Special considerations:**
- Site often becomes a major batch effect source
- Each site may process samples independently

**Design strategy:**
1. Ensure all conditions represented at each site
2. Balance conditions within each site
3. Include cross-site reference samples
4. Account for site as batch in analysis
5. Consider centralized processing if feasible

---

## Temporal Batching Strategies

### Time-Based Batching

**When samples arrive over time:**
- Clinical studies with rolling enrollment
- Longitudinal studies with multiple timepoints
- Sequential experiments

**Strategy 1: Fixed batch intervals**
- Process samples every N weeks on fixed schedule
- Accumulate samples, process batch when full
- Ensures balanced batch sizes
- Randomize order within each batch

**Strategy 2: Continuous processing with reference**
- Process samples as they arrive (small batches)
- Include reference sample in each batch
- Use references to normalize across batches
- Appropriate for clinical diagnostics

### Dealing with Sample Delays

**Problem:** Some samples delayed, arrive after main batches processed

**Solution 1: Reserve slots**
- Plan for 10-20% additional samples
- Reserve slots in batches for late arrivals
- Process reserves with pilot samples or controls

**Solution 2: Follow-up batch**
- Process delayed samples in separate batch
- Ensure batch includes both conditions
- Include reference samples from original batches
- Account for batch in analysis

**Solution 3: Drop and re-collect**
- If critical to have in main batch, drop from study
- Re-collect samples for future study
- Document exclusion criteria

---

## Covariate Balancing

### What to Balance

**Priority 1 (must balance):**
- Experimental condition (primary variable)
- Major biological covariates with known large effects:
  - Sex/gender
  - Age group (if wide age range)
  - Disease subtype or severity

**Priority 2 (should balance if possible):**
- Collection site or center
- Genetic background or ancestry
- Sample type or tissue
- Time of collection (AM vs PM, season)

**Priority 3 (nice to balance):**
- Technician
- Storage time
- Other measured covariates

### How to Balance

**Perfect balance (ideal but often not achievable):**
- Equal numbers of each covariate level in each batch
- Example: Each batch has 4 males and 4 females

**Approximate balance (more realistic):**
- Similar proportions of each level across batches
- Example: Batch 1 has 55% female, Batch 2 has 50% female
- Acceptable if differences small

**Statistical balance:**
- No significant association between batch and covariate
- Test with chi-square or Fisher's exact test
- p > 0.05 indicates adequate balance

### Balancing Algorithm

Use provided script for automated balancing:

```r
source("scripts/batch_assignment.R")
batch_design <- assign_samples_to_batches(
  metadata = sample_metadata,
  batch_size = 8,
  balance_vars = c("condition", "sex", "age_group", "site"),
  n_iterations = 10000  # Try many random assignments
)

# Validate balance
source("scripts/batch_validation.R")
validation <- check_balance(batch_design, vars = c("condition", "sex", "age_group"))
print(validation)
```

**Algorithm approach:**
1. Generate many random batch assignments
2. Calculate balance score for each
3. Select assignment with best balance
4. Verify no confounding

---

## Validation of Batch Design

### Pre-Processing Validation (CRITICAL)

**Before starting experiment, validate batch design:**

**Check 1: Confounding test**
```r
source("scripts/batch_validation.R")
confound_result <- check_confounding(
  batch_design,
  condition_var = "condition"
)
# Must return "No confounding detected"
```
❌ If confounding detected, regenerate design - DO NOT PROCEED

**Check 2: Balance test**
```r
balance_result <- check_balance(
  batch_design,
  vars = c("condition", "sex", "age_group")
)
# Should show similar proportions across batches
```

**Check 3: Visual inspection**
```r
visualize_batch_design(
  batch_design,
  output_file = "batch_layout.svg"
)
# Manually inspect: does each batch look similar?
```

### Post-Processing Validation

**After sequencing, check for batch effects:**

**PCA plot colored by batch:**
- Batch clusters indicate batch effect
- Ideally: samples cluster by biology, not batch

**Heatmap of batch vs. sample:**
- Should see no clear batch-related patterns

**Statistical tests:**
- `sva::ComBat` before/after comparison
- Percentage of variance explained by batch (should be <10%)

---

## Common Batch Design Mistakes

### Mistake 1: Sequential Processing by Condition

**Problem:**
```
Week 1: Process all controls
Week 2: Process all treatments
```
❌ Complete confounding of time with condition
❌ Any time-dependent effects look like treatment effects

**Solution:**
```
Week 1: Process Controls 1-4, Treatments 1-4
Week 2: Process Controls 5-8, Treatments 5-8
```
✅ Each week includes both conditions

### Mistake 2: Ignoring Sex Imbalance

**Problem:**
```
Batch 1: 6 females, 2 males
Batch 2: 2 females, 6 males
```
❌ Sex partially confounded with batch
❌ Sex effects can be huge (thousands of genes)

**Solution:**
```
Batch 1: 4 females, 4 males
Batch 2: 4 females, 4 males
```
✅ Balanced sex across batches

### Mistake 3: Filling Batches Sequentially

**Problem:**
- Samples arrive over time
- Fill Batch 1 completely, then move to Batch 2
- Early-arriving samples all in Batch 1, late arrivals in Batch 2
- If sample timing correlates with condition, creates confounding

**Solution:**
- Reserve slots in each batch for each condition
- Randomize arrival order within condition
- Don't start processing until enough samples for balanced batch

### Mistake 4: Unequal Batch Sizes

**Problem:**
```
Batch 1: 12 samples (6 controls, 6 treatments)
Batch 2: 4 samples (2 controls, 2 treatments)
```
⚠️ Very different batch sizes reduce power
⚠️ Harder to detect and correct batch effects

**Solution:**
- Keep batch sizes as equal as possible
- Combine small batches if needed
- Or split large batches to equalize

### Mistake 5: Not Documenting Batch Structure

**Problem:**
- Process samples without recording which batch
- Batch information lost
- Cannot correct for batch effects in analysis

**Solution:**
- Document batch assignment BEFORE processing
- Record batch ID for every sample in metadata
- Include processing date, technician, reagent lots
- Export batch design using `export_design.R`

---

## Statistical Adjustment for Batch Effects

### When Design Prevention Is Not Enough

Even with good design, some batch effects may remain. Statistical correction can help but is not a substitute for good design.

**Methods:**

**1. Linear model with batch covariate**
```r
# DESeq2 with batch
dds <- DESeqDataSetFromMatrix(counts, colData, design = ~ batch + condition)
```
✅ Simple and transparent
✅ Works well for moderate batch effects
❌ May not remove all batch variation

**2. ComBat (sva package)**
```r
library(sva)
normalized_counts <- ComBat(
  dat = log_normalized_counts,
  batch = metadata$batch,
  mod = model.matrix(~ condition, data = metadata)
)
```
✅ Strong batch removal
❌ Can over-correct and remove biology
❌ Use with caution for DE analysis

**3. RUVSeq (Remove Unwanted Variation)**
```r
library(RUVSeq)
set <- RUVs(set, cIdx = negative_control_genes, k = 1)
```
✅ Data-driven approach
✅ Uses negative control genes
❌ Requires specification of controls

**4. SVA (Surrogate Variable Analysis)**
```r
library(sva)
svobj <- sva(dat, mod, mod0)
# Include surrogate variables in DE model
```
✅ Discovers hidden batch variables
✅ Flexible approach
❌ Can be aggressive

### When Statistical Correction Fails

Statistical correction CANNOT fix:
- ❌ Complete confounding (batch = condition)
- ❌ Very strong batch effects (>50% variance)
- ❌ Non-linear batch effects
- ❌ Batch-specific biology (e.g., different protocols)

**In these cases:**
- May need to exclude problematic batches
- Repeat experiment with better design
- Acknowledge as major limitation

---

## Batch Design Checklist

### Before Starting Experiment

- [ ] Identified all batches (processing groups, sequencing runs, etc.)
- [ ] Created batch assignment that includes all conditions in each batch
- [ ] Balanced important covariates (sex, age, site) across batches
- [ ] Ran `check_confounding()` - confirmed no confounding
- [ ] Ran `check_balance()` - confirmed adequate balance
- [ ] Visualized batch design - manual inspection looks good
- [ ] Documented batch assignment in metadata spreadsheet
- [ ] Exported batch layout for lab use (`export_batch_layout()`)
- [ ] Lab has clear batch processing plan with dates

### During Processing

- [ ] Recording batch ID, date, technician, reagent lots
- [ ] Following randomized processing order within batches
- [ ] Including any reference samples in each batch
- [ ] Noting any processing deviations or issues

### After Processing, Before Analysis

- [ ] All samples have batch information in metadata
- [ ] Checked QC metrics - similar across batches
- [ ] Generated PCA plot colored by batch - no obvious clustering
- [ ] Calculated variance explained by batch - documented

### During Analysis

- [ ] Including batch as covariate in statistical model
- [ ] Considering batch correction methods if needed
- [ ] Comparing results with/without batch correction
- [ ] Documenting batch effect handling in methods

---

## Special Cases

### Single Sample Arrives Late

**Problem:** One treatment sample arrives after main batches processed

**Options:**

**Option A: Drop the sample**
- If already well-powered (n ≥ 6 per group)
- One sample won't substantially change results
- Simplest solution

**Option B: Process in follow-up batch**
- Include controls from freezer in the batch
- Must have both conditions in follow-up batch
- Account for batch in analysis
- Works if n is critical

**Option C: Save for future experiment**
- Set aside for replication study
- Avoid confounding issues entirely

### Batch Size Doesn't Divide Sample Size

**Problem:** 22 samples, batch size = 8

**Options:**

**Option A: Variable batch sizes (8, 8, 6)**
- Minimize size variation
- Balance conditions in each batch
- Acceptable solution

**Option B: Include controls/references to fill (8, 8, 8)**
- Include replicates of controls or references
- Makes batches equal size
- More samples can increase power

**Option C: Reduce to equal batches (8, 8)**
- Only if can exclude 6 samples without losing power
- Not recommended if samples are precious

### Batches Span Multiple Sequencing Runs

**Problem:** Library prep batch different from sequencing run batch

**Solution:**
- Record BOTH batch types in metadata
- Library prep batch usually more important
- Can include both in model: `~ seq_run + prep_batch + condition`
- Or use `prep_batch` only if `seq_run` effect small

---

## Additional Resources

**Key Papers:**
- Leek JT et al. (2010) "Tackling the widespread and critical impact of batch effects." *Nat Rev Genet* 11(10):733-739
- Goh WW et al. (2017) "Why Batch Effects Matter in Omics Data." *Trends Biotechnol* 35(6):498-507
- Hicks SC et al. (2015) "Smooth quantile normalization." *Biostatistics* 19(2):185-198

**Workflow Scripts:**
- [batch_assignment.R](../scripts/batch_assignment.R) - Generate balanced batch designs
- [batch_validation.R](../scripts/batch_validation.R) - Validate and visualize designs

**Related Guides:**
- [experimental_design_best_practices.md](experimental_design_best_practices.md) - General design principles
- [qc_guidelines.md](qc_guidelines.md) - Batch-specific QC checks

---

**Last Updated:** 2026-01-28
**Version:** 1.0
