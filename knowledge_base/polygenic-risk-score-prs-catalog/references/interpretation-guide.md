# PRS Interpretation Guide

## What Does a Polygenic Risk Score Measure?

A PRS quantifies an individual's genetic predisposition to a trait by summing the effects of many genetic variants across the genome. Each variant contributes a small effect, and the aggregate captures the polygenic component of risk.

**PRS z-score interpretation:**
- **z = 0:** Average genetic risk (population mean)
- **z > 0:** Above-average genetic risk
- **z < 0:** Below-average genetic risk
- **z > 1.96:** Top ~2.5% of genetic risk (95th percentile)
- **z < -1.96:** Bottom ~2.5% (5th percentile)

## Multi-Trait PRS Interpretation

### Correlation Between Traits
Correlations between PRS for different traits reflect **shared genetic architecture** (pleiotropy):
- **High positive correlation (r > 0.3):** Traits share many risk variants in the same direction
- **Near zero correlation:** Largely independent genetic architectures
- **Negative correlation:** Some genetic variants increase risk for one trait but decrease risk for another

Example: LDL cholesterol and CAD PRS may be positively correlated because LDL-raising variants also increase CAD risk.

### Composite Risk Score
The composite risk score (mean z-score across traits) provides a summary of overall cardiometabolic genetic burden. Interpret with caution:
- Treats all traits equally (no clinical weighting)
- Correlations between traits mean the composite is NOT simply additive
- Useful for ranking individuals but NOT for clinical risk prediction

## Population Differences

### Why PRS Differs Across Populations
PRS values systematically differ across ancestry groups due to:
1. **Allele frequency differences:** Risk alleles vary in frequency across populations
2. **LD pattern differences:** The tag SNPs may capture different amounts of causal variation
3. **GWAS discovery bias:** Most GWAS are conducted in European populations
4. **Ascertainment bias:** Genotyping arrays optimized for European variation

### Important Caveats
- **Do NOT interpret population mean differences as evidence of differential disease risk** — PRS are calibrated within populations, not across them
- Population PRS differences primarily reflect methodological factors, not biological risk differences
- PRS developed in one ancestry have **reduced predictive accuracy** in other ancestries (typically 2-5x lower R²)
- Within-population percentile ranks are more meaningful than across-population comparisons

## Clinical Context

PRS are **NOT diagnostic tests**:
- PRS explains only a fraction of trait variance (typically 5-15% for complex traits)
- Environmental factors, rare variants, and gene-gene interactions are not captured
- Clinical utility requires validation in independent cohorts
- Always combine PRS with clinical risk factors for risk assessment

## Further Reading

See references/ in the polygenic-risk-score skill for detailed methods comparison and troubleshooting.
