# ChIP-Atlas Diff Analysis Output Formats

## Main Result BED (wabi_result.bed) — 8-Column Custom Format

The primary result file is a custom 8-column tab-separated format (NOT standard BED9):

| Column | Name | Type | Description |
|--------|------|------|-------------|
| 1 | chrom | str | Chromosome (e.g., chr1, chrX) |
| 2 | chromStart | int | Start position (0-based) |
| 3 | chromEnd | int | End position (exclusive) |
| 4 | counts_A | str | Comma-separated normalized counts for group A experiments |
| 5 | counts_B | str | Comma-separated normalized counts for group B experiments |
| 6 | logFC | float | Log2 fold change (positive = A enriched, negative = B enriched) |
| 7 | pvalue | float | edgeR p-value |
| 8 | qvalue | float | Benjamini-Hochberg corrected q-value (FDR) |

### Example Row

```
chr1	1048001	1048400	47.80,31.04,36.33	3.43,3.72,4.03	3.16	2.12e-11	7.39e-09
```

This means: Region chr1:1048001-1048400 has normalized counts ~38 in group A vs ~3.7 in group B, logFC=3.16 (A enriched), highly significant (FDR=7.39e-09).

### Derived Columns (computed by parse_bed_results.py)

| Column | Type | Description |
|--------|------|-------------|
| region_size | int | chromEnd - chromStart (bp) |
| direction | str | 'A_enriched' (logFC > 0) or 'B_enriched' (logFC < 0) |
| significant | bool | qvalue < 0.05 |
| mean_count_a | float | Mean of counts_A values |
| mean_count_b | float | Mean of counts_B values |
| score | int | -log10(qvalue) * 100, capped at 1000 (BED-compatible) |

## IGV Visualization BED (wabi_result.igv.bed) — BED9 + GFF3

The IGV file uses standard BED9 format with URL-encoded GFF3 metadata:

| Column | Name | Type | Description |
|--------|------|------|-------------|
| 1 | chrom | str | Chromosome |
| 2 | chromStart | int | Start position |
| 3 | chromEnd | int | End position |
| 4 | name | str | URL-encoded GFF3 attributes (LogFC, P-value, Q-value) |
| 5 | score | int | Significance score (0-1000) |
| 6 | strand | str | Strand (always ".") |
| 7 | thickStart | int | Display start (= chromStart) |
| 8 | thickEnd | int | Display end (= chromEnd) |
| 9 | itemRgb | str | RGB color indicating direction |

### Direction from itemRgb Color

| Color | RGB | Direction |
|-------|-----|-----------|
| Orange | 222,131,68 | Enriched in Group A (positive logFC) |
| Blue | 106,153,208 | Enriched in Group B (negative logFC) |

## Region Size Interpretation

| Size Range | Typical Feature |
|------------|-----------------|
| 100-500 bp | Transcription factor binding sites |
| 500-2,000 bp | Enhancers, narrow histone marks (H3K4me3) |
| 2,000-10,000 bp | Broad histone marks (H3K27me3, H3K36me3) |
| >10,000 bp | Super-enhancers, large chromatin domains |

## IGV Visualization

1. Open IGV and load the matching genome (e.g., hg38)
2. **Option A:** File → Open Session → select `wabi_result.xml` (loads everything)
3. **Option B:** File → Load from File → select `wabi_result.igv.bed` (regions only)
4. Regions appear colored orange (A-enriched) or blue (B-enriched)


---
