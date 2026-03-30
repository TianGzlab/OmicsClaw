# S-PrediXcan and S-MultiXcan Best Practices

Guidelines for running S-PrediXcan (single tissue) and S-MultiXcan (cross-tissue) TWAS analyses.

---

## Installation

```bash
# Conda (recommended)
conda create -n metaxcan python=3.9
conda activate metaxcan
pip install metaxcan

# Or from source
git clone https://github.com/hakyimlab/MetaXcan.git
cd MetaXcan/software
pip install -r requirements.txt
```

---

## S-PrediXcan (Single Tissue)

### Basic Command

```bash
python -m metaxcan.SPrediXcan \
  --model_db_path gtex_v8_mashr_Artery_Coronary.db \
  --covariance gtex_v8_Artery_Coronary_covariance.txt.gz \
  --gwas_file gwas_sumstats.txt \
  --snp_column SNP \
  --effect_allele_column A1 \
  --non_effect_allele_column A2 \
  --beta_column BETA \
  --pvalue_column P \
  --output_file results.csv
```

### Key Parameters

- `--model_db_path`: SQLite database with expression weights
- `--covariance`: Covariance matrix for SNPs in models
- `--gwas_file`: GWAS summary statistics

### Input Format

GWAS file must have:
- SNP ID (rsID or chr:pos)
- Effect allele (A1)
- Non-effect allele (A2)
- Effect size (BETA or OR)
- P-value

---

## S-MultiXcan (Cross-Tissue)

### When to Use

- Trait affects multiple organ systems
- Uncertain which tissue is most relevant
- Want to increase power by aggregating across tissues

### Basic Command

```bash
python -m metaxcan.SMulTiXcan \
  --models_folder gtex_v8_models/ \
  --models_name_pattern "gtex_v8_mashr_(.*).db" \
  --snp_covariance gtex_v8_expression_covariance.txt.gz \
  --gwas_file gwas_sumstats.txt \
  --snp_column SNP \
  --effect_allele_column A1 \
  --non_effect_allele_column A2 \
  --beta_column BETA \
  --pvalue_column P \
  --output_file smultixcan_results.txt
```

### Interpretation

- Identifies genes with consistent effects across tissues
- Higher power than single-tissue analysis
- P-value represents meta-analysis across tissues

---

## GTEx v8 Weights

Download from [PredictDB](https://predictdb.org/):

**MASHR models** (recommended):
- Most accurate prediction models
- Incorporate cross-tissue information
- File format: `gtex_v8_mashr_{tissue}.db`

**Elastic Net models** (alternative):
- Simpler single-tissue models
- File format: `gtex_v8_en_{tissue}.db`

---

## Advantages over FUSION

1. **Speed**: 10-100x faster (summary stats only, no LD loading)
2. **Python-based**: Easy installation via pip/conda
3. **S-MultiXcan**: Built-in cross-tissue meta-analysis
4. **Active development**: Regular updates and support

---

## Disadvantages vs FUSION

1. **Single model**: Uses one prediction model per gene (FUSION tests multiple)
2. **No built-in colocalization**: Must run separately
3. **Fewer tissues**: Primarily GTEx v8 (FUSION has more custom panels)

---

## Multiple Testing

**Bonferroni**: 0.05 / N_genes (typically 2.5×10⁻⁶)
**FDR**: Use scipy `false_discovery_control(pvalues)`

For S-MultiXcan, apply correction to cross-tissue P-values.

---

## Common Issues

| Issue | Solution |
|-------|----------|
| "No genes imputed" | Check SNP ID format matches weights |
| Allele mismatch | Harmonize GWAS alleles to match reference |
| Missing covariance | Download from PredictDB alongside weights |
| Low gene coverage | GWAS may have poor SNP overlap with expression panels |

---

## Performance Tips

- **Pre-filter GWAS**: Keep only HapMap3 SNPs for speed
- **Parallelize tissues**: Run S-PrediXcan per tissue in parallel
- **Use MASHR weights**: Better accuracy than elastic net

---

## References

- Barbeira AN, et al. (2018) Exploring the phenotypic consequences of tissue specific gene expression variation inferred from GWAS summary statistics. *Nat Commun* 9:1825. [doi:10.1038/s41467-018-03621-1](https://doi.org/10.1038/s41467-018-03621-1)

- Barbeira AN, et al. (2019) Integrating predicted transcriptome from multiple tissues improves association detection. *PLoS Genet* 15:e1007889. [doi:10.1371/journal.pgen.1007889](https://doi.org/10.1371/journal.pgen.1007889)

---

**Last Updated:** 2026-01-28
