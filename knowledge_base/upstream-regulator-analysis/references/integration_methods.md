# Upstream Regulator Analysis: Statistical Methods

## Overview

This skill identifies transcription factors (TFs) driving differential expression by integrating two data layers:

1. **Epigenomics** — ChIP-Atlas peak enrichment (433,000+ public ChIP-seq experiments)
2. **Transcriptomics** — RNA-seq differential expression results

The integration produces a **regulatory score** that ranks TFs by combined evidence from binding enrichment, target-gene overlap, and directional concordance.

## Step-by-Step Methodology

### Step 1: ChIP-Atlas Peak Enrichment

DE genes (upregulated and downregulated separately) are submitted to the ChIP-Atlas Enrichment Analysis API. For each gene, the Ensembl REST API maps gene symbols to promoter regions (TSS ± distance). The ChIP-Atlas API performs Fisher's exact test per experiment, comparing overlap of ChIP-seq peaks with submitted gene regions vs. RefSeq background.

**Output per experiment:** fold enrichment, p-value, BH-corrected q-value.

### Step 2: TF Selection

Enrichment results from both up and down gene lists are aggregated. For each unique TF (antigen), the best q-value across all experiments and both directions is retained. TFs are ranked by q-value, and the top N (default: 10) passing the enrichment threshold (default: q < 0.05) are selected for target gene analysis.

### Step 3: Target Gene Retrieval

For each selected TF, pre-computed target gene data is downloaded from ChIP-Atlas. These files contain MACS2-derived binding scores for every gene in the genome across all available ChIP-seq experiments for that TF.

### Step 4: Regulon Scoring (Novel Integration)

For each TF, the following metrics are computed:

#### Fisher's Exact Test

A 2×2 contingency table tests whether TF targets are enriched among DE genes:

```
                    DE         Not-DE
TF-bound          a            b          a+b = TF targets in background
Not-TF-bound      c            d          c+d = non-targets in background
                 a+c          b+d          N = total background genes
```

Where:
- **a** = TF targets that are differentially expressed
- **b** = TF targets that are NOT differentially expressed
- **c** = non-TF-targets that are differentially expressed
- **d** = non-TF-targets that are NOT differentially expressed
- Background = all genes present in the DE results file

The one-sided Fisher's exact test (`alternative="greater"`) tests whether TF targets are over-represented among DE genes.

#### Directional Concordance

Among TF targets that are DE, what fraction move in the dominant direction?

```
concordance = max(n_up, n_down) / (n_up + n_down)
```

- **Activator:** concordance > 0.6, majority targets upregulated
- **Repressor:** concordance > 0.6, majority targets downregulated
- **Mixed:** concordance ≤ 0.6

The 0.6 threshold requires at least 60% of TF-bound DE genes to move in one direction.

#### Combined Regulatory Score

```
regulatory_score = -log10(fisher_p) × concordance × -log10(chip_q)
```

This multiplicative formula requires evidence from all three axes:
- **Binding enrichment** (ChIP-Atlas q-value) — TF binds near these genes more than expected
- **Target-DE overlap** (Fisher's p-value) — TF targets are enriched among DE genes
- **Directional concordance** — TF targets change expression in a consistent direction

A high score requires strong evidence across all three. If any axis is weak (non-significant), the entire score is pulled down.

## Statistical Considerations

### Background Gene Set

The background for Fisher's test is all genes present in the DE results file (typically ~15,000-20,000 genes). This represents the measured universe — genes that could have been detected as DE but were not.

### Multiple Testing

- ChIP-Atlas enrichment: BH-corrected q-values per experiment
- Fisher's exact test: computed per TF (no cross-TF correction)
- The regulatory score ranks TFs but does not provide a formal multi-test-corrected p-value across all TFs

### Independence Assumption

Fisher's exact test assumes gene selection is independent. This may be violated if TF targets cluster in biological pathways (pathway co-regulation). The test is still useful as a ranking metric but p-values should be interpreted as approximate.

### Limitations

1. **ChIP-Atlas data bias** — Well-studied TFs (TP53, MYC, CTCF) have more experiments, potentially inflating enrichment signals
2. **Cell-type specificity** — ChIP-Atlas aggregates across cell types; a TF may bind different targets in different contexts
3. **Indirect effects** — A DE gene bound by a TF may be regulated by a different mechanism
4. **Simple regulation model** — The activator/repressor classification ignores context-dependent, combinatorial, and post-transcriptional regulation

## Comparison to IPA Upstream Regulator Analysis

Ingenuity Pathway Analysis (IPA) performs a conceptually similar upstream regulator analysis using curated literature-derived regulatory relationships. This skill differs by:

- Using **experimental ChIP-seq binding data** (ChIP-Atlas) rather than literature curation
- Incorporating **binding enrichment significance** (not just overlap)
- Computing **directional concordance** from actual expression changes
- Being **open-source** and transparent in methodology

## References

- Zou Z, et al. (2024) ChIP-Atlas 3.0. *Nucleic Acids Res.* 52(W1):W159-W166
- Oki S, et al. (2018) ChIP-Atlas. *EMBO Rep.* 19(12):e46255
- Fisher RA (1922) On the interpretation of chi-squared. *J R Stat Soc.* 85(1):87-94
