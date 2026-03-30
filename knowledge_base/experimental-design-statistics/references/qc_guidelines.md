# Quality Control Guidelines

Comprehensive QC checklists and guidelines for experimental design.

---

## Power Analysis QC

### Before Calculating Power

- [ ] **Verify CV estimates match your biological system**
  - Cell lines: CV = 0.1-0.2
  - Inbred mice: CV = 0.2-0.3
  - Outbred mice/primary cells: CV = 0.3-0.4
  - Human samples: CV = 0.3-0.5
  - Check [cv_tissue_database.csv](cv_tissue_database.csv) for your specific tissue

- [ ] **Use pilot data if available**
  - Pilot-based power is more accurate than literature CV estimates
  - Requires at least 2-3 samples per condition in pilot
  - Use `extract_dispersion_deseq2()` to get accurate parameters

- [ ] **Sequencing depth is realistic**
  - Bulk RNA-seq: 15-30 million reads typical
  - scRNA-seq: 50,000-100,000 reads per cell typical
  - ATAC-seq: 25-50 million reads typical
  - Don't assume excessive depth to compensate for low sample size

- [ ] **Effect size is biologically meaningful**
  - Can you measure this fold-change with your assay?
  - Is this effect size relevant to your biological question?
  - Smaller effects require more samples

### After Calculating Power

- [ ] **Power ≥0.80 (80%)**
  - Lower power wastes resources (high false negative rate)
  - For critical experiments, aim for power ≥0.90

- [ ] **Test multiple scenarios**
  - Calculate power for range of effect sizes
  - Test different sample sizes
  - Evaluate trade-offs (depth vs. replicates)

- [ ] **Document assumptions**
  - Record CV source (pilot data or literature)
  - Document sequencing depth assumptions
  - Note effect size justification

---

## Sample Size QC

### Minimum Requirements (CRITICAL)

- [ ] **At least 3 biological replicates per condition**
  - n=2 is insufficient for statistics
  - n=3 is absolute minimum
  - n≥6 recommended for robust results

- [ ] **Add 10-20% buffer for failures**
  - Sample failures happen (extraction, QC, etc.)
  - Plan for: `n_planned = n_required × 1.15`
  - Budget accordingly

- [ ] **Biological > technical replicates**
  - Prioritize more biological samples over technical replicates
  - Technical replicates don't capture biological variation
  - Exception: Method validation studies

### Budget and Feasibility

- [ ] **Total cost calculated**
  - Cost = (samples × depth) + prep costs
  - Verify budget supports proposed design

- [ ] **Sample availability confirmed**
  - Are enough samples obtainable?
  - Consider recruitment timeline (human studies)
  - Animal breeding timelines (mouse studies)

- [ ] **Sequencing capacity available**
  - Check facility capacity and timeline
  - Plan for potential delays

### Paired Design Considerations

- [ ] **Verify pairing reduces variance**
  - Paired designs assume within-pair correlation
  - Use pilot data to verify benefit
  - Calculate power assuming reduced CV (×0.7-0.8)

- [ ] **Account for attrition in paired studies**
  - Missing one timepoint loses entire pair
  - Buffer needs to be higher (~20-30%)

---

## Batch Design QC (MOST CRITICAL)

### Pre-Assignment Checks

- [ ] **Understand batch structure**
  - What defines a "batch"? (day, plate, run, operator?)
  - How many samples can be processed per batch?
  - Are there multiple batch levels? (plate + day + sequencing run)

- [ ] **Identify all variables to balance**
  - Primary: Experimental condition (MUST balance)
  - Secondary: Sex, age, genetic background, collection site
  - Consider hidden variables (time of day, operator)

### Critical Confounding Check (REQUIRED)

- [ ] **Batch NOT confounded with condition** ⚠️ CRITICAL
  - Each batch MUST contain all experimental conditions
  - Never process all samples from one condition in single batch
  - Chi-square test p-value > 0.05
  - **If confounded:** Regenerate assignment immediately

- [ ] **Visual inspection passed**
  - Create contingency table: `table(batch, condition)`
  - Each cell should have samples
  - Roughly balanced counts

### Balance Checks

- [ ] **Primary covariates balanced**
  - Sex balanced across batches (chi-square p > 0.05)
  - Age groups balanced if relevant
  - Genetic background balanced (mouse studies)

- [ ] **Sample sizes approximately equal**
  - All batches have similar n
  - Deviations <20% acceptable
  - Last batch can be smaller if needed

- [ ] **Controls included in each batch**
  - Same control sample(s) processed in every batch
  - Enables batch effect correction
  - Use "split pool" controls if possible

### Practical Considerations

- [ ] **Randomization applied**
  - Randomize sample order within batches
  - Use `add_processing_order(randomize_within=TRUE)`
  - Avoid systematic patterns

- [ ] **Plate positions randomized**
  - Avoid edge wells when possible (edge effects)
  - Randomize within plates
  - Document well positions

- [ ] **Metadata recording plan ready**
  - Template for recording batch variables
  - Fields: date, operator, reagent lots, instrument, plate/well
  - Lab team trained on importance

---

## Metadata Documentation Requirements

### Essential Batch Metadata (ALWAYS RECORD)

- [ ] **Processing date**
  - Format: YYYY-MM-DD
  - Include time if relevant (morning vs. afternoon effects)

- [ ] **Operator/Technician**
  - Record who performed each step
  - Operator effects are real

- [ ] **Reagent lot numbers**
  - Record ALL reagent lots used
  - Lot-to-lot variation can create batch effects
  - Keep labels/receipts

- [ ] **Instrument/Equipment ID**
  - Which machine used for each step?
  - Calibration status
  - Maintenance logs

- [ ] **Plate/Chip information**
  - Plate barcode or ID
  - Well positions for each sample
  - Plate position effects (edge, center)

### Additional Metadata (Recommended)

- [ ] **Library prep batch**
  - If separate from extraction batch
  - Kit lot numbers

- [ ] **Sequencing run information**
  - Flowcell ID
  - Lane assignments
  - Run date

- [ ] **Protocol deviations**
  - ANY deviation from standard protocol
  - Which samples affected
  - Reason for deviation

- [ ] **Environmental conditions**
  - Room temperature (if relevant)
  - Humidity (RNA stability)
  - Storage conditions during delays

---

## Multiple Testing QC

### Method Selection Verification

- [ ] **Method appropriate for data type**
  - Genome-wide (>5000 tests): BH-FDR or IHW
  - Candidate genes (<100 tests): Bonferroni
  - GWAS (millions): Bonferroni with standard threshold (5×10⁻⁸)

- [ ] **Consider effect heterogeneity**
  - Heterogeneous effects: Use IHW if covariate available
  - Homogeneous effects: BH-FDR sufficient

- [ ] **Sample size adequate for method**
  - Small n (<6): Consider permutation-based FDR
  - Parametric assumptions may be violated

### Post-Correction Checks

- [ ] **Number of significant results reasonable**
  - Too many (>50%): Check for technical issues
  - Too few (0-1): Power may be insufficient

- [ ] **QQ plot checked (if applicable)**
  - Verify calibration of p-values
  - Check for inflation/deflation

- [ ] **Top hits make biological sense**
  - Known genes in pathway?
  - Consistent with literature?
  - Effect sizes reasonable?

---

## Grant Proposal QC Checklist

When preparing experimental design for grant proposals:

- [ ] **Power analysis documented**
  - CV source clearly stated
  - Power calculations shown
  - Sample size justified

- [ ] **Budget justified**
  - Cost per sample calculated
  - Sequencing depth justified
  - Why this n and not less?

- [ ] **Batch design planned**
  - Statement that batches will be balanced
  - Description of batch effect mitigation
  - Reference to statistical analysis plan

- [ ] **Statistical analysis plan included**
  - Which software/methods
  - Multiple testing correction method
  - Batch effect correction approach

- [ ] **Citations included**
  - Power analysis method papers
  - Statistical method papers
  - Best practices references

- [ ] **Preliminary data supports assumptions**
  - Pilot data shows expected variability
  - Effect size estimates reasonable
  - Technical feasibility demonstrated

---

## Red Flags to Watch For

### Power Analysis Red Flags

- ⚠️ **Power <0.60**: Study severely underpowered
- ⚠️ **Very large n (>20/group) for large effects**: Check assumptions
- ⚠️ **CV unusually low (<0.1) for complex samples**: Likely unrealistic
- ⚠️ **Depth >100M reads for RNA-seq**: Diminishing returns, better to add samples

### Batch Design Red Flags

- 🚨 **CRITICAL: Batch confounded with condition**: DO NOT PROCEED
- ⚠️ **All samples of one condition in first batch**: Bad randomization
- ⚠️ **No controls across batches**: Can't correct batch effects
- ⚠️ **Processing timeline >6 months**: Long timeline increases batch risk
- ⚠️ **Different operators for each condition**: Operator confounded

### Sample Size Red Flags

- ⚠️ **n=2 per group**: Insufficient for statistics
- ⚠️ **No buffer for failures**: Will likely be underpowered
- ⚠️ **Technical replicates counted as biological**: Wrong variance estimate
- ⚠️ **Paired design treated as independent**: Wrong power calculation

---

**Last Updated:** 2026-01-28
**Maintained by:** Knowhows Repository
