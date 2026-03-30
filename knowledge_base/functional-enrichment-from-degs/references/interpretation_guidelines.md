# Enrichment Results Interpretation Guidelines

This guide provides detailed instructions for interpreting GSEA and ORA results, understanding key output columns, and avoiding common interpretation pitfalls.

---

## GSEA Results Interpretation

### Key Output Columns

| Column | Description | Interpretation |
|--------|-------------|----------------|
| **ID** | Gene set identifier | Unique pathway ID |
| **Description** | Gene set name | Human-readable pathway name |
| **setSize** | Number of genes in set | Pathways with 15-500 genes are most reliable |
| **enrichmentScore** | Raw enrichment score | Magnitude of enrichment (not comparable across sets) |
| **NES** | Normalized Enrichment Score | **Primary metric** - comparable across gene sets |
| **pvalue** | Nominal p-value | Use with caution (not adjusted) |
| **p.adjust** | BH-adjusted p-value (FDR) | **Use this for significance** (threshold: 0.05) |
| **qvalue** | Q-value (alternative FDR) | Alternative to p.adjust |
| **core_enrichment** | Leading edge genes | Genes driving the enrichment signal |

### Understanding NES (Normalized Enrichment Score)

**NES is the most important GSEA metric.**

**Positive NES (e.g., NES = 2.1):**
- Pathway is **ACTIVATED** or **UPREGULATED**
- Genes in this pathway tend to be at the TOP of your ranked list
- Interpretation: "This pathway is more active in condition A vs. condition B"

**Negative NES (e.g., NES = -1.8):**
- Pathway is **SUPPRESSED** or **DOWNREGULATED**
- Genes in this pathway tend to be at the BOTTOM of your ranked list
- Interpretation: "This pathway is less active in condition A vs. condition B"

**Magnitude:**
- |NES| > 2.0: Strong enrichment
- 1.5 < |NES| < 2.0: Moderate enrichment
- |NES| < 1.5: Weak enrichment (but may still be significant if FDR < 0.05)

**Example:**
```
HALLMARK_OXIDATIVE_PHOSPHORYLATION: NES = 2.5, FDR = 0.001
→ Strong upregulation of OXPHOS genes (high metabolic activity)

HALLMARK_INFLAMMATORY_RESPONSE: NES = -1.9, FDR = 0.03
→ Suppression of inflammatory genes (reduced inflammation)
```

### Leading Edge Genes (core_enrichment)

**What are they?**
The subset of genes in a pathway that contribute most to the enrichment signal.

**Why are they important?**
- These are the specific genes driving the pathway enrichment
- Often more informative than the entire pathway
- Good candidates for follow-up validation experiments

**How to use them:**
1. Extract from `core_enrichment` column (semicolon-separated)
2. Check if these genes are known key regulators
3. Look for overlap between related pathways
4. Prioritize for experimental validation

**Example:**
```
Pathway: HALLMARK_APOPTOSIS
Leading edge: BAX, BCL2, CASP3, CASP9, APAF1
→ Focus on these genes for mechanistic follow-up
```

### GSEA Visualization Interpretation

#### Dot Plot (gsea_dotplot.svg)

**What it shows:** Top enriched pathways separated by direction

**How to read:**
- **X-axis:** GeneRatio (proportion of pathway genes in your data)
- **Y-axis:** Pathway names
- **Color:** Adjusted p-value (darker = more significant)
- **Size:** Number of genes in pathway
- **Left panel:** Activated pathways (NES > 0)
- **Right panel:** Suppressed pathways (NES < 0)

**What to look for:**
- Pathways in both panels (biological coherence)
- Clusters of related pathways
- Unexpected pathways (may indicate batch effects or artifacts)

#### Running Score Plot (gsea_running_score.svg)

**What it shows:** How enrichment score is calculated for specific pathways

**Components:**
1. **Top panel:** Running enrichment score (green/red line)
2. **Middle panel:** Gene positions in ranked list (black bars)
3. **Bottom panel:** Ranking metric value

**How to interpret:**
- **Peak at left (green):** Pathway genes are enriched at top of list (activated)
- **Peak at right (red):** Pathway genes are enriched at bottom of list (suppressed)
- **Black bars clustering:** Where pathway genes are concentrated
- **Sharp peak:** Strong, coordinated enrichment
- **Gradual slope:** Weaker or distributed enrichment

---

## ORA Results Interpretation

### Key Output Columns

| Column | Description | Interpretation |
|--------|-------------|----------------|
| **ID** | Gene set identifier | Unique pathway ID |
| **Description** | Gene set name | Human-readable pathway name |
| **GeneRatio** | k/n | k genes in pathway / n total query genes |
| **BgRatio** | M/N | M genes in pathway in background / N total background |
| **pvalue** | Hypergeometric test p-value | Use with caution (not adjusted) |
| **p.adjust** | BH-adjusted p-value (FDR) | **Use this for significance** (threshold: 0.05) |
| **qvalue** | Q-value | Alternative to p.adjust |
| **geneID** | Overlapping genes | Specific genes from your list in this pathway |
| **Count** | Number of overlapping genes | Absolute number of genes |

### Understanding GeneRatio

**What it is:** The proportion of your query genes that belong to this pathway

**Format:** k/n (e.g., "15/100")
- k = genes from your list in this pathway
- n = total genes in your query list

**Interpretation:**
- **Higher ratio = stronger enrichment**
- GeneRatio = 15/100 = 0.15 → 15% of your genes are in this pathway
- Compare across pathways: 20/100 is stronger than 5/100

**Example:**
```
Pathway A: GeneRatio = 25/150 = 0.167 (strong)
Pathway B: GeneRatio = 5/150 = 0.033 (weak)
→ Pathway A has stronger enrichment
```

### Understanding BgRatio

**What it is:** The proportion of all tested genes that belong to this pathway

**Format:** M/N (e.g., "150/20000")
- M = genes in pathway (from background)
- N = total genes in background

**Why it matters:**
- Provides context for GeneRatio
- Larger pathways naturally have higher overlap
- ORA accounts for this in statistical test

### Critical ORA Considerations

#### 1. Must Analyze Up/Down Separately

**❌ WRONG:**
```r
# Combining up and down genes
all_sig <- c(up_genes, down_genes)
ora_all <- run_ora(all_sig, term2gene, background)
# Results are MEANINGLESS - loses directionality
```

**✅ CORRECT:**
```r
# Separate analyses
ora_up <- run_ora(up_genes, term2gene, background, direction = "upregulated")
ora_down <- run_ora(down_genes, term2gene, background, direction = "downregulated")
# Preserves biological directionality
```

#### 2. Must Specify Background

**❌ WRONG:**
```r
ora <- enricher(gene_list, TERM2GENE = term2gene)
# Missing universe parameter - uses all known genes (biased!)
```

**✅ CORRECT:**
```r
ora <- enricher(gene_list, TERM2GENE = term2gene, universe = all_tested_genes)
# Correct denominator for statistics
```

### ORA Visualization Interpretation

#### Bar Plot (ora_upregulated_barplot.svg, ora_downregulated_barplot.svg)

**What it shows:** Top enriched pathways for up or down genes

**How to read:**
- **X-axis:** Gene ratio or count
- **Y-axis:** Pathway names
- **Color:** Adjusted p-value (darker = more significant)

**What to look for:**
- Pathways consistent with expected biology
- Overlap between up and down (may indicate technical artifact)
- Very broad terms (less informative than specific pathways)

---

## Comparing GSEA and ORA Results

When you run both methods, compare results:

### Strong Agreement (Best Case)
```
GSEA: HALLMARK_APOPTOSIS, NES = 2.3, FDR = 0.001
ORA:  HALLMARK_APOPTOSIS, GeneRatio = 15/100, FDR = 0.002
→ High confidence in this pathway
```

### GSEA Significant, ORA Not
```
GSEA: HALLMARK_OXIDATIVE_PHOSPHORYLATION, NES = 1.8, FDR = 0.02
ORA:  HALLMARK_OXIDATIVE_PHOSPHORYLATION, FDR = 0.15
→ Modest but coordinated changes across pathway (still meaningful)
```

### ORA Significant, GSEA Not
```
GSEA: HALLMARK_APOPTOSIS, NES = 1.2, FDR = 0.12
ORA:  HALLMARK_APOPTOSIS, GeneRatio = 8/50, FDR = 0.01
→ Strong signal in subset of genes, but not coordinated across pathway
```

---

## Common Pitfalls to Avoid

### 1. Using Nominal P-values Instead of FDR

**❌ WRONG:**
```r
sig_pathways <- gsea_result@result[gsea_result@result$pvalue < 0.05, ]
# Multiple testing problem - many false positives
```

**✅ CORRECT:**
```r
sig_pathways <- gsea_result@result[gsea_result@result$p.adjust < 0.05, ]
# Properly adjusted for multiple testing
```

### 2. Filtering Results by Keyword

**❌ WRONG:**
```r
immune_pathways <- gsea_result@result[grep("IMMUNE", gsea_result@result$Description), ]
# Misses immune pathways without "immune" in name
# Confirmation bias
```

**✅ CORRECT:**
```r
# Examine all significant pathways
sig_pathways <- gsea_result@result[gsea_result@result$p.adjust < 0.05, ]
# Then interpret biological themes
```

### 3. Ignoring Gene Set Size

Very small gene sets (<10 genes) or very large gene sets (>500 genes) are problematic:
- **Too small:** Unstable statistics
- **Too large:** Lack specificity, hard to interpret

**Solution:** Filter during analysis (already done in workflow scripts)

### 4. Over-Interpreting Weak Signals

Not every FDR < 0.05 pathway is biologically meaningful:
- Check effect size (NES for GSEA, GeneRatio for ORA)
- Look for consistency across related pathways
- Validate with orthogonal approaches

### 5. Combining Up and Down Genes (ORA Only)

**This loses all directionality and produces meaningless results.**

Always analyze upregulated and downregulated genes separately for ORA.

---

## Reporting Enrichment Results

### Minimal Reporting Standards

For each analysis, report:
1. **Method:** GSEA or ORA (or both)
2. **Database:** Gene set collections used (e.g., Hallmark + KEGG)
3. **Thresholds:**
   - GSEA: min/max gene set size, number of permutations
   - ORA: significance cutoffs (padj, log2FC), background genes
4. **Statistics:** FDR-adjusted p-values, NES (GSEA), or GeneRatio (ORA)
5. **Top pathways:** Table of top 10-20 pathways with statistics
6. **Visualizations:** Dot plots, running score plots, or bar plots

### Example Results Text

**GSEA:**
> "We performed GSEA using Hallmark and KEGG gene sets (n=236 gene sets, size 15-500 genes, 10,000 permutations). We identified 28 significantly enriched pathways (FDR < 0.05), including 15 activated and 13 suppressed pathways. The most strongly activated pathway was HALLMARK_OXIDATIVE_PHOSPHORYLATION (NES = 2.5, FDR = 0.001), while HALLMARK_INFLAMMATORY_RESPONSE was the most suppressed (NES = -1.9, FDR = 0.03)."

**ORA:**
> "We performed ORA on significantly upregulated (n=150, padj < 0.05, log2FC > 1) and downregulated (n=112) genes using Hallmark and KEGG gene sets (background: 15,234 tested genes). Upregulated genes were enriched for 12 pathways (FDR < 0.05), with HALLMARK_APOPTOSIS showing strongest enrichment (GeneRatio = 15/150, FDR = 0.002). Downregulated genes were enriched for 8 pathways, including HALLMARK_CELL_CYCLE (GeneRatio = 10/112, FDR = 0.01)."

---

## References

1. **Interpretation best practices:** Reimand J, et al. (2019) Pathway enrichment analysis and visualization of omics data using g:Profiler, GSEA, Cytoscape and EnrichmentMap. Nat Protoc. DOI: 10.1038/s41596-018-0103-9

2. **Common pitfalls:** Khatri P, et al. (2012) Ten Years of Pathway Analysis: Current Approaches and Outstanding Challenges. PLoS Comput Biol. DOI: 10.1371/journal.pcbi.1002375
