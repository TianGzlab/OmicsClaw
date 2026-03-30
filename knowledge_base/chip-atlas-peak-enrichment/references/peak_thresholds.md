# ChIP-Atlas Peak Calling Thresholds

ChIP-Atlas provides pre-called peaks at four stringency levels based on MACS2 significance scores.

## Threshold Scale

The API threshold parameter represents MACS2 `-10 * log10(p-value)`:

| Threshold | MACS2 Score | P-value (approx) | Stringency | Recommended For |
|-----------|-------------|-------------------|------------|-----------------|
| **50** | -10*log10(p) >= 50 | 1e-5 | **Default** | Standard analysis, balanced sensitivity/specificity |
| **100** | -10*log10(p) >= 100 | 1e-10 | High | High-confidence peaks only |
| **200** | -10*log10(p) >= 200 | 1e-20 | Very high | Ultra-stringent, strongest binding only |
| **500** | -10*log10(p) >= 500 | 1e-50 | Extreme | Exceptionally strong binding events |

## Choosing a Threshold

### Threshold 50 (1e-5) - **RECOMMENDED DEFAULT**

- Standard enrichment analysis
- Discovering new regulatory relationships
- Works well for most transcription factors
- Typical: ~5,000-10,000 peaks per TF experiment

### Threshold 100 (1e-10) - High Stringency

- High-confidence binding sites only
- Minimizing false positives critical
- Typical: ~1,000-5,000 peaks per experiment

### Threshold 200 (1e-20) - Very High Stringency

- Ultra-high-confidence peaks required
- May miss weaker true positives
- Typical: ~100-1,000 peaks per experiment

### Threshold 500 (1e-50) - Extreme

- Strongest binding events only
- Very few peaks per experiment
- Useful for histone marks with broad domains

## Impact on Enrichment Analysis

Higher thresholds produce fewer peaks but higher fold enrichments. Lower thresholds provide better sensitivity but include more noise. The API default of 50 provides good balance.

## Recommendations by Factor Type

| Factor Type | Recommended Threshold | Rationale |
|-------------|----------------------|-----------|
| **Transcription Factors** | 50 | Balance sensitivity/specificity |
| **Histone Modifications** | 50 or 100 | Broader regions, can use higher stringency |
| **Chromatin Remodelers** | 50 | Often have weaker signals |
| **ATAC-seq** | 50 | Standard open chromatin |

## References

- Zhang et al. (2008). "Model-based Analysis of ChIP-Seq (MACS)." *Genome Biology*.
- ChIP-Atlas documentation: https://chip-atlas.org
