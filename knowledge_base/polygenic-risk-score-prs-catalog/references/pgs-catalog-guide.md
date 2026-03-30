# PGS Catalog Guide

## What is the PGS Catalog?

The PGS Catalog (https://www.pgscatalog.org/) is an open database of published polygenic scores. It provides:
- **5,000+ scoring files** for hundreds of traits
- **Harmonized weights** mapped to standard genome builds (GRCh37, GRCh38)
- **Metadata** including publication, method, sample sizes, and performance metrics
- **REST API** for programmatic access

## Finding PGS Scores

### Using the Search Function
```r
source("scripts/load_pgs_weights.R")

# Search by trait name
scores <- search_pgs_catalog("coronary artery disease")
scores <- search_pgs_catalog("type 2 diabetes")
scores <- search_pgs_catalog("LDL cholesterol")
```

### Choosing the Best Score
When multiple scores are available for a trait, consider:

1. **Sample size:** Larger GWAS discovery samples generally yield better PRS
2. **Method:** Bayesian methods (LDpred2, PRS-CS, SBayesR) often outperform C+T
3. **Validation:** Check if the score has been validated in independent cohorts
4. **Variant count:** More variants isn't always better — method matters more
5. **Population:** Scores derived from diverse or ancestry-matched GWAS are preferable
6. **Recency:** Newer scores may benefit from larger GWAS and improved methods

### PGS ID Format
- Format: `PGS` followed by 6 digits (e.g., `PGS000018`)
- Lower numbers were deposited earlier; higher numbers are newer
- Publication-linked: each score is tied to a specific publication

## Harmonized Scoring Files

### File Format
PGS Catalog harmonized files contain:
- `hm_chr` — Chromosome (harmonized)
- `hm_pos` — Position (harmonized to GRCh37 or GRCh38)
- `effect_allele` — Allele that the weight applies to
- `other_allele` — Reference/non-effect allele
- `effect_weight` — PRS weight (log-OR for binary traits, beta for continuous)
- `hm_rsID` — rsID (harmonized)

### Genome Build
- **GRCh37 (hg19):** Default for 1000 Genomes Phase 3 and most older GWAS
- **GRCh38 (hg38):** Newer reference; some scores only available in this build
- Always match the genome build between scoring file and target genotypes

## REST API

### Score Metadata
```
GET https://www.pgscatalog.org/rest/score/{pgs_id}
```
Returns: name, trait, method, variants count, publication, FTP URLs

### Trait Search
```
GET https://www.pgscatalog.org/rest/trait/search?term={query}
```
Returns: matching traits with associated PGS IDs

### Rate Limiting
- The API has rate limits; avoid rapid sequential requests
- The `search_pgs_catalog()` function limits to 20 score lookups per search

## Demo Trait Configuration

The default cardiometabolic panel includes:

| Trait | Short Name | PGS ID | Notes |
|-------|-----------|--------|-------|
| Coronary Artery Disease | CAD | PGS000018 | Khera et al. 2018 |
| Type 2 Diabetes | T2D | PGS000014 | Mahajan et al. 2018 |
| LDL Cholesterol | LDL | PGS000062 | GLGC |
| Body Mass Index | BMI | PGS000027 | Khera et al. 2019 |
| Systolic Blood Pressure | SBP | PGS000299 | Evangelou et al. 2018 |

If any PGS ID becomes unavailable, use `search_pgs_catalog()` to find alternatives.

## Troubleshooting Downloads

| Issue | Solution |
|-------|----------|
| 404 error | PGS ID may be wrong or harmonized file unavailable for requested build |
| Timeout | Set `options(timeout = 900)` — genome-wide scores can be 100MB+ |
| Parse error | Ensure correct skip of `#` header lines (handled by `download_pgs_weights()`) |
| Low match rate | Check genome build alignment between weights and genotypes |


---
