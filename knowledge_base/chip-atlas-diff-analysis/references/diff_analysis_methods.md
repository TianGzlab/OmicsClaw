# Diff Analysis Statistical Methods

## Differential Peak Regions (DPR) — edgeR

### Pipeline

1. **Data retrieval:** BigWig and BED files retrieved from ChIP-Atlas based on submitted experiment IDs
2. **Format conversion:** BigWig files converted to bedGraph format
3. **Coverage reconstruction:** Raw read coverage reconstructed using total mapped read counts
4. **Genome segmentation:** Genome segmented based on peak regions from query datasets
5. **Count matrix:** Read counts aggregated into m × n matrix (m regions × n experiments)
6. **Differential analysis:** edgeR package performs negative binomial GLM-based testing
7. **Result formatting:** Significant regions reported in BED9 format

### Statistical Framework

- **Model:** Negative binomial generalized linear model (edgeR)
- **Normalization:** TMM (trimmed mean of M-values) across experiments
- **Test:** Quasi-likelihood F-test for differential binding
- **Multiple testing:** Benjamini-Hochberg FDR correction

### Conceptual Relationship to DiffBind

The approach is conceptually related to DiffBind but:
- Does NOT require BAM files (uses pre-computed BigWig/BED from ChIP-Atlas)
- Works directly with processed peak data
- Enables comparison across any public experiments without raw data download

### Reference

Robinson MD, McCarthy DJ, Smyth GK. edgeR: a Bioconductor package for differential expression analysis of digital gene expression data. Bioinformatics. 2010;26(1):139-140.

---

## Differentially Methylated Regions (DMR) — metilene

### Pipeline

1. **Format conversion:** BigWig methylation data converted to bedGraph format
2. **Data aggregation:** Methylation levels aggregated using `metilene_input.pl`
3. **DMR detection:** DMRs detected using `metilene` with default parameters
4. **Result formatting:** Significant DMRs reported in BED9 format

### Statistical Framework

- **Method:** Circular binary segmentation + Mann-Whitney U test
- **Segmentation:** Identifies contiguous regions with differential methylation
- **Significance:** p-values from two-sample tests at each CpG position
- **Correction:** Multiple testing correction across detected regions

### Reference

Jühling F, et al. metilene: fast and sensitive calling of differentially methylated regions from bisulfite sequencing data. Genome Res. 2016;26(2):256-262.

---

## Output Format

### Main BED (wabi_result.bed) — 8-Column Custom Format

The primary result is NOT standard BED9. It has 8 columns:

```
chrom  chromStart  chromEnd  counts_A  counts_B  logFC  pvalue  qvalue
```

- **counts_A/B:** Comma-separated TMM-normalized read counts per experiment
- **logFC:** Log2 fold change from edgeR (positive = A enriched)
- **pvalue:** edgeR p-value from quasi-likelihood F-test
- **qvalue:** Benjamini-Hochberg FDR-corrected p-value

### IGV BED (wabi_result.igv.bed) — BED9 + GFF3

Standard BED9 format for IGV visualization:
- **itemRgb:** Orange (222,131,68) = A-enriched, Blue (106,153,208) = B-enriched
- **name field:** URL-encoded GFF3 attributes with LogFC, P-value, Q-value

See [output_format.md](output_format.md) for complete column definitions.
