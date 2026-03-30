# Enrichment Statistics

Statistical methods used by the ChIP-Atlas Enrichment Analysis API.

## Fisher's Exact Test

The ChIP-Atlas API uses Fisher's exact test on a 2x2 contingency table to assess whether input genes are significantly enriched for binding by each ChIP-seq experiment compared to RefSeq background.

### Contingency Table

|                        | Overlapping peaks | No overlapping peaks |
|------------------------|:-----------------:|:--------------------:|
| **Input genes**        | a                 | b                    |
| **All RefSeq genes**   | c                 | d                    |

Where:
- **a**: Number of input genes with promoter peaks (reported as numerator of overlap_a)
- **b**: Input genes without peaks
- **c**: RefSeq genes with promoter peaks (from overlap_b)
- **d**: RefSeq genes without peaks
- Total RefSeq genes: ~18,622 (hg38)

### P-value

One-sided Fisher's exact test for enrichment (odds ratio > 1). API reports as log10(p-value), e.g., -12.02 means p = 10^-12.02.

## Benjamini-Hochberg Q-values

Multiple testing correction applied across all experiments tested:

1. Rank all experiments by p-value
2. Calculate adjusted p-value: `q_i = p_i * N / rank_i`
3. Enforce monotonicity

API reports as log10(q-value). Use q < 0.05 for genome-wide significance.

## Fold Enrichment

```
fold_enrichment = (a / n_input) / (c / n_refseq)
```

Where n_input = total input genes, n_refseq = total RefSeq genes.

### Interpretation

| Fold Enrichment | Interpretation |
|-----------------|----------------|
| >10x | Very strong enrichment, likely direct regulatory relationship |
| 5-10x | Strong enrichment, good evidence for regulation |
| 2-5x | Moderate enrichment, possible regulation |
| <2x | Weak enrichment, may be background |
| <1x | Depletion (API reports as ~1e-06 for zero overlap) |
| >100,000x | **Sentinel value** — see below |

### Sentinel Values

When the background overlap (c in the contingency table) is zero — meaning no RefSeq genes have peaks for that experiment in the queried regions — the fold enrichment formula produces division by zero. The API reports an extremely large value (typically 1,000,000x) as a sentinel.

**How to identify sentinel values:**
- Fold enrichment ≥ 100,000x
- Typically low overlap count (e.g., 1/19 genes)
- Often non-significant Q-value (q > 0.05)

**How these are handled:**
- Results are sorted by Q-value (not fold enrichment), so sentinels are deprioritized
- Top-20 and visualization panels require minimum 2 gene overlaps
- Scatter and volcano plots cap fold enrichment at 1,000x for display

## P-value Thresholds

| P-value | Significance Level |
|---------|-------------------|
| p < 0.001 | Highly significant (***) |
| p < 0.01 | Significant (**) |
| p < 0.05 | Nominally significant (*) |
| p >= 0.05 | Not significant (ns) |

## Overlap Rate

Fraction of input genes with at least one overlapping peak from an experiment:

```
overlap_rate = regions_with_overlaps / total_input_genes
```

## API Output Columns

The API returns 11 tab-separated columns (no header):

1. Experiment ID (SRX...)
2. Antigen class (e.g., "TFs and others")
3. Antigen name
4. Cell type class (e.g., "Blood")
5. Cell type (e.g., "K-562")
6. Number of peaks
7. Input overlap (e.g., "4/5" = 4 of 5 input genes)
8. Background overlap (e.g., "10/18851")
9. log10(P-value)
10. log10(Q-value)
11. Fold enrichment

## Data Biases

ChIP-Atlas enrichment results are influenced by the composition of public ChIP-seq data:

- **Well-studied factors are over-represented.** TFs like TP53, RELA (NF-κB), and CTCF have hundreds to thousands of public experiments, while less-studied factors may have only a few. A factor appearing enriched may partly reflect data availability rather than biological specificity.
- **Common cell types dominate.** Cell lines like K-562, HeLa, and MCF-7 contribute disproportionately to the database. Enrichment in these cell types is more likely to be detected simply due to more available data.
- **Publication bias.** Experiments in public databases skew toward positive results and well-characterized regulatory relationships.

**Recommendations:**
- Use Q-value ranking (not fold enrichment) to prioritize results
- Consider the number of available experiments when interpreting factor importance
- Validate key findings with orthogonal methods (expression data, perturbation experiments, motif analysis)

## References

- Zou et al. (2024). "ChIP-Atlas 3.0: a data-mining suite to explore chromosome architecture together with large-scale regulome data." *Nucleic Acids Research*.
- Zou et al. (2022). "ChIP-Atlas 2021 update: a data-mining suite for epigenomic exploration." *Nucleic Acids Research*.
- Oki et al. (2018). "ChIP-Atlas: a data-mining suite powered by full integration of public ChIP-seq data." *EMBO Reports*.
