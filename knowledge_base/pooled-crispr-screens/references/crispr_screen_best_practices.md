# CRISPR Screen Best Practices

Comprehensive guidelines for designing, executing, and analyzing pooled CRISPR screens with single-cell RNA-seq readout.

---

## Experimental Design

### Library Design

**sgRNA Coverage:**
- **3-5 sgRNAs per gene**: Optimal for distinguishing on-target from off-target effects
- **≥100 non-targeting controls**: Essential for robust outlier detection baseline
- **Positive controls**: Include 5-10 well-characterized perturbations
  - Essential genes (expect cell death/depletion)
  - Known phenotypic perturbations (e.g., transcription factors)
  - Pathway-specific controls (e.g., key signaling molecules)

**Negative Controls:**
- Use non-targeting sgRNAs that match GC content of targeting sgRNAs
- Distribute non-targeting controls throughout library (avoid clustering)
- Consider safe-harbor targeting controls (e.g., AAVS1 locus)

**Library Complexity:**
- Small screens (10-100 genes): 1,000-5,000 sgRNAs
- Medium screens (100-1,000 genes): 5,000-10,000 sgRNAs
- Genome-wide screens (15,000-20,000 genes): 50,000-100,000 sgRNAs

### MOI (Multiplicity of Infection) Optimization

**Target MOI: 0.3-0.5**
- Ensures majority of cells receive 0 or 1 sgRNA
- Minimizes sgRNA doublets (<10%)
- Balances capture efficiency with singlet purity

**MOI vs Doublet Rate:**
| MOI | Expected Doublet Rate | Expected Singlet Rate |
|-----|----------------------|----------------------|
| 0.3 | ~4% | ~26% |
| 0.5 | ~7% | ~40% |
| 0.8 | ~13% | ~55% |
| 1.0 | ~18% | ~63% |

**Titration experiment:**
- Test MOI range: 0.1, 0.3, 0.5, 0.8
- Measure: sgRNA capture rate, doublet rate, cell viability
- Select optimal MOI balancing efficiency and singlet purity

### Cell Numbers

**Minimum cells per perturbation: 50-100**
- Accounts for dropout during QC filtering (~30-50%)
- Provides statistical power for DE and outlier detection
- Plan for 2-3x target cell number at sequencing

**Total cell calculation:**
```
Total cells = (# perturbations) × (cells/perturbation) × (safety factor)
Example: 1000 genes × 50 cells × 2 = 100,000 cells target
```

### Biological Replicates

**Minimum: 2 independent transductions**
- Captures biological variability
- Reduces batch effects
- Enables validation of hits

**Replicate types:**
- **Technical replicates**: Same transduction, split for sequencing (not ideal)
- **Biological replicates**: Independent transductions from same cell source (good)
- **True biological replicates**: Different batches of cells, independent transductions (best)

---

## Experimental Execution

### Viral Transduction

**Timing:**
- Allow 3-5 days post-transduction before selection
- Begin antibiotic selection for 5-7 days (depends on cell line)
- Allow 2-3 days recovery post-selection before phenotypic assay

**Selection:**
- Optimize antibiotic concentration for complete killing of untransduced cells
- Confirm transduction efficiency (>80% recommended before MOI optimization)
- Maintain cell density to avoid growth-based selection bias

### Cell Culture Considerations

**Avoid bottlenecks:**
- Maintain ≥500 cells per sgRNA throughout culture
- Passage at consistent density and intervals
- Document population doublings

**Population drift concerns:**
- Strong survival phenotypes will dominate over time
- Limit culture duration post-transduction (7-14 days recommended)
- Consider early harvesting for lethal perturbations

### 10X Capture Optimization

**Cell concentration:**
- Target: 700-1,200 cells/µL (follow 10X guidelines)
- Dead cell removal: Use DAPI/7-AAD sorting if viability <90%
- Singlet gating: Remove doublets by FSC-A vs FSC-H

**Library preparation:**
- Follow 10X Feature Barcoding protocol for sgRNA capture
- Optimize sgRNA amplification cycles (typically 12-15 cycles)
- Check sgRNA library complexity by qPCR or Bioanalyzer

---

## Computational Analysis Best Practices

### sgRNA Assignment

**Thresholds:**
- **Minimum UMI per sgRNA**: 2-3 UMIs (reduces noise from ambient RNA)
- **Singlet assignment**: Cell has >70% UMI from single sgRNA
- **Doublet filtering**: Remove cells with 30-70% UMI from multiple sgRNAs

**Expected mapping rates:**
- ✅ >50%: Excellent
- ⚠️ 30-50%: Acceptable
- ❌ <30%: Poor capture, troubleshoot library prep

### Quality Control

**Standard scRNA-seq QC:**
- Apply same QC as regular single-cell experiments
- Adjust thresholds for cell type (see qc_guidelines.md)

**CRISPR-specific QC:**
- Check cells per perturbation distribution
- Flag perturbations with <20 cells (insufficient power)
- Check control cell distribution across batches

### Batch Effect Assessment

**When to correct:**
- Strong batch separation in PCA (PC1-2 driven by batch)
- Different QC metric distributions across batches
- Inconsistent perturbation representation across batches

**Correction methods:**
- **Harmony**: Fast, preserves biological variation
- **Seurat integration**: Good for small numbers of batches
- **BBKNN**: k-NN based, preserves local structure
- **Combat**: Linear model-based, good for balanced designs

**When NOT to correct:**
- Batches overlap in PCA space
- Perturbation effects are larger than batch effects
- Small batch differences (<10% variance explained)

### Statistical Power Considerations

**Sample size for DE:**
- Minimum 20 cells per group for t-test
- 50+ cells preferred for robust p-values
- >100 cells for detecting small effect sizes (log2FC < 0.5)

**Multiple testing correction:**
- Use Benjamini-Hochberg (FDR) for genome-wide screens
- Consider permutation-based FDR for small screens
- Report both raw p-values and adjusted q-values

---

## Hit Validation

### Computational Validation

**Within-screen validation:**
1. **Multiple sgRNAs per gene**: Require ≥2 sgRNAs with consistent phenotype
2. **Target gene downregulation**: Verify target gene expression reduced (CRISPRi) or increased (CRISPRa)
3. **Phenotype specificity**: Check outlier phenotype is distinct from other perturbations

**Cross-replicate validation:**
- Hits should replicate across biological replicates
- Calculate correlation of effect sizes across replicates
- Use rank-based metrics (less sensitive to outliers)

### Experimental Validation

**Tier 1 validation (in original screen context):**
- Re-introduce individual sgRNAs in bulk
- Measure phenotype by flow cytometry or bulk RNA-seq
- Confirm target gene knockdown by qPCR or Western blot

**Tier 2 validation (orthogonal methods):**
- Alternative CRISPR modality (CRISPRi → CRISPRko)
- Small molecule perturbation (if available)
- Genetic rescue experiments

**Tier 3 validation (functional assays):**
- Mechanistic experiments based on transcriptional signature
- Pathway perturbation experiments
- In vivo validation (if applicable)

---

## Common Pitfalls

### Experimental

1. **Over-passaging cells**
   - Problem: Selection for fast-growing clones
   - Solution: Limit culture time, harvest early

2. **Low viral titer**
   - Problem: Uneven representation, low MOI
   - Solution: Titrate virus, optimize production

3. **Poor cell viability at capture**
   - Problem: High ambient RNA, sgRNA misassignment
   - Solution: Dead cell removal, optimize culture conditions

4. **Insufficient sgRNA capture**
   - Problem: Low mapping rates
   - Solution: Optimize library prep, increase sgRNA amplification cycles

### Computational

1. **Too strict QC filtering**
   - Problem: Removes true perturbation effects (e.g., sick cells)
   - Solution: Apply QC to controls first, use relaxed thresholds for perturbed cells

2. **Over-correction of batch effects**
   - Problem: Removes biological signal
   - Solution: Check if perturbation effects are preserved after correction

3. **Ignoring target gene expression**
   - Problem: Include non-functional sgRNAs in analysis
   - Solution: Check target gene expression, filter sgRNAs with no effect

4. **Multiple testing burden**
   - Problem: Loss of power in genome-wide screens
   - Solution: Use permutation-based FDR, prioritize hits with multiple sgRNAs

---

## Screen-Type Specific Considerations

### CRISPRi (Interference)

**Expected phenotypes:**
- Target gene downregulation (70-90% knockdown typical)
- Phenotypes emerge quickly (24-72 hours)
- Well-suited for essential gene screens (no cell death)

**Best practices:**
- Use dCas9-KRAB or dCas9-KRAB-MeCP2 for stronger repression
- Target promoter-proximal regions (TSS ± 200 bp)
- Verify dCas9-KRAB expression and nuclear localization

### CRISPRa (Activation)

**Expected phenotypes:**
- Target gene upregulation (2-100x increase possible)
- Requires more optimization than CRISPRi
- Cell-type and locus-dependent efficacy

**Best practices:**
- Use dCas9-VPR or dCas9-SAM for strong activation
- Target proximal promoter regions (TSS -200 to +100 bp)
- Include endogenous positive controls (verify activation)

### CRISPRko (Knockout)

**Expected phenotypes:**
- Complete gene disruption (indels, frameshifts)
- Slower phenotype emergence (protein turnover dependent)
- Strong phenotypes (loss-of-function)

**Best practices:**
- Allow 7-10 days for protein depletion
- Target early exons (maximize frameshift probability)
- Be cautious with essential genes (may cause cell death/dropout)

---

## Recommended Reading

**Method Development:**
- Dixit et al. (2016) "Perturb-Seq" *Cell* - Original Perturb-seq method
- Adamson et al. (2016) "A Multiplexed Single-Cell CRISPR Screening Platform" *Cell* - High-throughput screening
- Replogle et al. (2020) "Direct guide RNA capture" *Nature Biotechnology* - Improved capture methods

**Analysis Approaches:**
- Schraivogel et al. (2020) "Targeted Perturb-seq" *Nature Methods* - Statistical methods
- Norman et al. (2019) "Genetic interaction manifolds" *Science* - Combinatorial screens
- McFaline-Figueroa et al. (2019) "Pooled CRISPR screening" *Science* - Large-scale analysis

**Best Practices:**
- Doench (2018) "Am I ready for CRISPR?" *Nature Reviews Genetics* - Experimental design
- Sanson et al. (2018) "Optimized libraries for CRISPR-Cas9 screens" *Nature Communications* - Library design
