# FUSION Best Practices

Guidelines for running FUSION transcriptome-wide association studies effectively.

---

## Installation and Setup

```bash
git clone https://github.com/gusevlab/fusion_twas.git
cd fusion_twas

# R dependencies
R -e "install.packages(c('optparse', 'RColorBrewer', 'data.table'))"
R -e "install.packages('devtools'); devtools::install_github('gabraham/plink2R/plink2R')"

# Download LD reference panel
wget https://data.broadinstitute.org/alkesgroup/FUSION/LDREF.tar.bz2
tar xjvf LDREF.tar.bz2
```

---

## Prediction Models

FUSION supports multiple prediction models. Choose based on your analysis goals:

| Model | Description | Use When |
|-------|-------------|----------|
| **BSLMM** | Bayesian sparse linear mixed model | Best overall performance (recommended) |
| **LASSO** | L1-penalized regression | Fast, works well for sparse signals |
| **Elastic Net** | Mix of L1 + L2 penalties | Correlated predictors |
| **top1** | Single best eQTL | Fast, conservative |

**Recommended**: Use all models and select best-performing per gene (default FUSION behavior).

---

## Key Parameters

### LD Reference Panel

Must match GWAS ancestry:
- `--ref_ld_chr 1000G.EUR.` for European
- `--ref_ld_chr 1000G.EAS.` for East Asian
- `--ref_ld_chr 1000G.AFR.` for African

### Expression Weights

Download from [FUSION website](http://gusevlab.org/projects/fusion/):
- GTEx v8: 54 tissues
- TCGA: 33 cancer types
- Custom: Compute from your own eQTL data

---

## Multiple Testing Correction

**Bonferroni threshold**: 0.05 / N_genes_tested
- Typically: 0.05 / 20,000 = 2.5×10⁻⁶

**FDR**: Controls proportion of false discoveries
- Use `p.adjust(p, method="fdr")` in R
- Recommended for exploratory analyses

---

## Colocalization with FUSION

FUSION includes built-in colocalization via `FUSION.post_process.R`:

```R
Rscript FUSION.post_process.R \
  --sumstats gwas_sumstats.txt \
  --input fusion_results.dat \
  --out fusion_coloc \
  --ref_ld_chr 1000G.EUR. \
  --chr CHR \
  --coloc_P 1e-4
```

**PP.H4 > 0.8**: Strong colocalization (keep gene)
**PP.H4 < 0.5**: Likely LD artifact (exclude)

---

## Common Issues

| Issue | Solution |
|-------|----------|
| "No genes tested" | Check weight file path, verify chromosome range |
| LD reference mismatch | Ensure GWAS and LD panel have same ancestry |
| Memory error | Run chromosomes separately, increase RAM |
| Negative R² | Normal for some genes - predictive power is low |

---

## Performance Optimization

- **Parallelize by chromosome**: Run chr1-22 in parallel
- **Use BSLMM only** for faster runtime (~2-4 hours per tissue)
- **Pre-filter GWAS**: Remove SNPs with MAF < 1% or INFO < 0.6

---

## References

- Gusev A, et al. (2016) Integrative approaches for large-scale transcriptome-wide association studies. *Nat Genet* 48:245-252. [doi:10.1038/ng.3506](https://doi.org/10.1038/ng.3506)

---

**Last Updated:** 2026-01-28
