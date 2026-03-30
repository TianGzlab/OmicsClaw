# Decision Guide for Functional Enrichment Analysis

Comprehensive guidance for making key decisions during functional enrichment analysis.

---

## Decision 1: GSEA vs ORA vs Both

**When:** Before starting analysis

**Question:** Which enrichment method should I use?

### Option 1: GSEA Only (Recommended)

**Use when:**
- You have complete DE results with fold changes and p-values
- Want comprehensive analysis without arbitrary cutoffs
- Need to detect subtle coordinated pathway changes
- Publishing in high-impact journals (GSEA preferred in literature)

**Advantages:**
- Uses ALL genes ranked by expression change
- Detects coordinated changes across pathways
- More statistically powerful than ORA
- No arbitrary significance cutoffs required
- Better handles genes with modest but coordinated changes
- Recommended by methodological benchmarking studies

**Disadvantages:**
- Computationally slower (requires permutations)
- Results can be harder to interpret for non-experts
- Requires ranked gene list (not just gene names)

**When to use:**
- Default choice for most analyses
- Exploratory pathway analysis
- When you have full DE results with statistics
- When you want most sensitive detection

### Option 2: ORA Only

**Use when:**
- You have only a gene list without fold changes
- Need quick preliminary analysis
- Want simple, intuitive results for presentations
- Working with predefined gene sets from literature

**Advantages:**
- Simple, intuitive interpretation
- Faster computation (no permutations)
- Easy to explain to non-computational collaborators
- Works with gene lists from any source

**Disadvantages:**
- Requires arbitrary cutoffs (padj < 0.05, |log2FC| > 1)
- Less sensitive than GSEA
- Can miss pathways with coordinated subtle changes
- Treats all significant genes equally (ignores magnitude)
- Background gene set choice affects results

**When to use:**
- You only have gene names without fold changes
- Quick validation of GSEA results
- Presenting to non-computational audience
- Working with gene lists from literature or databases

### Option 3: Both GSEA and ORA

**Use when:**
- Want thorough analysis with validation
- Preparing results for publication
- Need to compare methods
- Want both sensitive detection (GSEA) and intuitive validation (ORA)

**Advantages:**
- ORA validates GSEA findings
- Provides complementary perspectives
- Increases confidence in shared results
- Useful for methods sections in papers

**Disadvantages:**
- More computation time
- More results to interpret
- May show discrepancies requiring explanation

**When to use:**
- High-stakes projects (grants, publications)
- When you want maximum confidence
- When reviewers may ask for validation
- Exploratory analysis where you're unsure what to expect

### Recommendation Matrix

| Scenario | Method | Rationale |
|----------|--------|-----------|
| Full DE results available | **GSEA** | Most sensitive, uses all information |
| Only gene list (no fold changes) | **ORA** | Only option without rankings |
| High-impact publication | **Both** | Cross-validation increases confidence |
| Quick exploratory analysis | **GSEA** | Best balance of speed and sensitivity |
| Presenting to clinicians | **ORA** | Simpler interpretation |
| Grant proposal/preliminary data | **Both** | Shows thoroughness |

---

## Decision 2: Gene Set Database Selection

**When:** Before retrieving gene sets (Step 3)

**Question:** Which gene set databases should I use?

### Database Options

#### Hallmark + KEGG (Default)

**Use when:** Exploratory analysis, balanced coverage needed

**Coverage:**
- 50 Hallmark pathways (well-defined biological states)
- ~180 KEGG pathways (metabolic and signaling)
- Total: ~230 gene sets

**Advantages:**
- Good balance of coverage and interpretability
- Hallmark pathways are well-curated, coherent
- KEGG provides detailed pathway maps
- Not too many results to overwhelm

**Disadvantages:**
- ⚠️ KEGG requires commercial license for commercial use
- May miss specialized biological processes
- Less granular than GO terms

**Recommendation:** Best default choice for most analyses

#### Hallmark + Reactome

**Use when:** Commercial application, metabolism/signaling focus

**Coverage:**
- 50 Hallmark pathways
- ~2,500 Reactome pathways
- Total: ~2,550 gene sets

**Advantages:**
- Reactome has permissive CC0 license (commercial-friendly)
- Excellent pathway diagrams
- Good for metabolism and signaling pathways
- More curated than GO

**Disadvantages:**
- More gene sets = more multiple testing correction
- Some pathway overlap with Hallmark
- Fewer metabolic pathways than KEGG

**Recommendation:** Use for commercial applications or when KEGG license unavailable

#### GO Biological Process (GO:BP)

**Use when:** Need comprehensive, detailed analysis

**Coverage:**
- ~7,000 GO:BP terms
- Hierarchical organization
- Very comprehensive

**Advantages:**
- Most comprehensive coverage
- Captures detailed biological processes
- Well-standardized across species
- Regular updates

**Disadvantages:**
- Many redundant/overlapping terms
- Results can be overwhelming
- Harder to identify key findings
- More false positives due to multiple testing

**Recommendation:** Use when Hallmark/KEGG miss your biology or when need very detailed view

#### C6 Oncogenic Signatures

**Use when:** Cancer biology research

**Coverage:**
- ~189 oncogenic signatures
- Derived from cancer studies
- Specific to cancer pathways

**Advantages:**
- Highly relevant for cancer research
- Captures known oncogenic mechanisms
- Complements Hallmark for cancer

**Disadvantages:**
- Narrow focus (only cancer)
- Not useful for non-cancer studies

**Recommendation:** Add to Hallmark for cancer-specific research

#### C7 Immunologic Signatures

**Use when:** Immunology research

**Coverage:**
- ~4,872 immunologic signatures
- Cell type markers
- Immune states

**Advantages:**
- Detailed immune cell characterization
- Good for deconvolution of immune components
- Captures immune activation states

**Disadvantages:**
- Very large (heavy multiple testing burden)
- Some signatures are overlapping
- Requires immunology expertise to interpret

**Recommendation:** Use for immunology-focused studies

### Selection Matrix

| Research Focus | Recommended Databases | Rationale |
|----------------|----------------------|-----------|
| **General exploratory** | Hallmark + KEGG | Best coverage, manageable results |
| **Commercial use** | Hallmark + Reactome | License compliance |
| **Metabolic pathways** | KEGG or Reactome | Detailed metabolic coverage |
| **Signaling pathways** | Reactome or KEGG | Pathway diagrams available |
| **Detailed processes** | GO:BP | Comprehensive, granular |
| **Cancer biology** | Hallmark + C6 | Cancer-specific mechanisms |
| **Immunology** | Hallmark + C7 | Immune cell types and states |
| **Publication (broad audience)** | Hallmark only | Most interpretable, least redundant |

### Combining Databases

**Good combinations:**
- Hallmark + KEGG (default)
- Hallmark + Reactome (commercial-friendly)
- Hallmark + C6 (cancer)
- Hallmark + C7 (immunology)
- GO:BP alone (comprehensive)

**Avoid combining:**
- KEGG + Reactome (redundant)
- GO:BP + other databases (too many results)
- Multiple large databases (>3,000 total gene sets)

---

## Decision 3: Ranking Metric for GSEA

**When:** Preparing ranked gene list (Step 2)

**Question:** How should I rank genes for GSEA?

### Option 1: Test Statistic (Best)

**Use when:** Available in your DE results

**Formula:**
- DESeq2: `stat` column (Wald statistic)
- limma: `t` statistic
- edgeR: Custom calculation or use `logFC/sqrt(dispersion)`

**Advantages:**
- Accounts for both effect size AND significance
- Best balance of signal and noise
- Recommended by GSEA developers
- Handles low-expressed genes appropriately

**Disadvantages:**
- Not always available (depends on DE method)
- Different meaning across methods

**Recommendation:** Always use if available (default for DESeq2, limma)

### Option 2: Signed -log10(p-value)

**Use when:** Test statistic unavailable

**Formula:** `sign(log2FC) × -log10(pvalue)`

**Advantages:**
- Emphasizes statistical significance
- Easy to compute from any DE results
- Intuitive interpretation

**Disadvantages:**
- Can overweight genes with very low p-values
- May rank lowly-expressed, noisy genes too highly
- Doesn't account for fold change magnitude well

**Recommendation:** Good fallback when test statistic unavailable

### Option 3: Signed -log10(adjusted p-value)

**Use when:** Want to emphasize FDR-controlled results

**Formula:** `sign(log2FC) × -log10(padj)`

**Advantages:**
- Incorporates multiple testing correction
- Conservative ranking

**Disadvantages:**
- Can compress rankings (many genes at padj boundaries)
- Less dynamic range than pvalue-based ranking
- May miss coordinated subtle changes

**Recommendation:** Use with caution, usually pvalue is better for ranking

### Option 4: log2 Fold Change Only

**Use when:** No p-values available (rare)

**Formula:** `log2FC`

**Advantages:**
- Simple
- Only needs fold changes

**Disadvantages:**
- ❌ NOT RECOMMENDED
- Ignores statistical significance
- Ranks noisy, low-count genes highly
- Poor performance in benchmarks

**Recommendation:** Avoid unless absolutely no alternative

### Ranking Comparison

| Metric | Best For | Sensitivity | Specificity | Ease |
|--------|----------|-------------|-------------|------|
| **Test statistic** | Most cases | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | Easy (if available) |
| **Signed -log10(p)** | Fallback | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | Easy |
| **Signed -log10(padj)** | Conservative | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | Easy |
| **log2FC only** | Desperate | ⭐⭐ | ⭐⭐ | Easy |

### Decision Tree

```
Do you have test statistics (stat, t)?
├─ YES → Use test statistic ✓
└─ NO → Do you have p-values?
    ├─ YES → Use sign(log2FC) × -log10(pvalue) ✓
    └─ NO → Can you get p-values?
        ├─ YES → Re-run DE analysis to get p-values
        └─ NO → Use log2FC only (suboptimal)
```

---

## Decision 4: ORA Significance Thresholds

**When:** Filtering genes for ORA (Step 2 if running ORA)

**Question:** What thresholds should I use to define significant genes?

### Standard Thresholds (Recommended)

**Default:** padj ≤ 0.05, |log2FC| ≥ 1

**Rationale:**
- padj < 0.05: Standard FDR control (5% false discoveries)
- |log2FC| ≥ 1: 2-fold change (biological relevance)
- Widely used in literature
- Good balance of sensitivity and specificity

### Alternative Thresholds

#### More Stringent (Conservative)

**Use:** padj ≤ 0.01, |log2FC| ≥ 1.5

**When:**
- High-noise data
- Want highest confidence results
- Many significant genes (>1,000)

#### More Permissive (Exploratory)

**Use:** padj ≤ 0.1, |log2FC| ≥ 0.5

**When:**
- Few significant genes (<50)
- Exploratory analysis
- Subtle biological effects expected

### Threshold Guidelines

| Scenario | padj | log2FC | Rationale |
|----------|------|--------|-----------|
| **Standard** | ≤0.05 | ≥1 | Default, balanced |
| **Few DE genes (<50)** | ≤0.1 | ≥0.5 | More permissive |
| **Many DE genes (>1000)** | ≤0.01 | ≥1.5 | More stringent |
| **High-noise data** | ≤0.01 | ≥1 | Focus on high confidence |
| **Biological validation** | ≤0.05 | ≥2 | High fold change |

**Recommendation:** Start with defaults, adjust only if results are too sparse or too abundant.

---

## Decision 5: Number of Permutations for GSEA

**When:** Running GSEA (Step 4)

**Question:** How many permutations should I use?

### Options

#### 1,000 permutations

**Use:** Quick testing, preliminary analysis

**Advantages:**
- Fast (~1-2 minutes)
- Good for prototyping

**Disadvantages:**
- Less stable p-values
- Not publication-quality

#### 10,000 permutations (Default)

**Use:** Final analysis, publication

**Advantages:**
- Stable p-values
- Publication-quality
- Good balance of accuracy and speed

**Disadvantages:**
- Takes 10-20 minutes
- More memory usage

#### 100,000 permutations

**Use:** Rarely needed

**Advantages:**
- Highest precision
- Best for borderline significant pathways

**Disadvantages:**
- Very slow (~2 hours)
- Diminishing returns

### Recommendation Matrix

| Use Case | Permutations | Rationale |
|----------|-------------|-----------|
| **Testing code** | 1,000 | Fast iteration |
| **Final analysis** | 10,000 | Default standard |
| **Publication** | 10,000 | Sufficient precision |
| **Borderline results** | 100,000 | Extra precision |

**General recommendation:** Use 10,000 for all final analyses.

---

## Summary Decision Flow

```
Start Enrichment Analysis
│
├─ Do you have fold changes?
│  ├─ YES → Use GSEA (primary)
│  └─ NO → Use ORA only
│
├─ Which databases?
│  ├─ Exploratory → Hallmark + KEGG
│  ├─ Commercial → Hallmark + Reactome
│  ├─ Cancer → Hallmark + C6
│  ├─ Immune → Hallmark + C7
│  └─ Detailed → GO:BP
│
├─ Ranking metric (for GSEA)?
│  ├─ Have test statistic? → Use it
│  └─ Otherwise → sign(log2FC) × -log10(p)
│
├─ ORA thresholds (if running ORA)?
│  └─ Standard: padj ≤ 0.05, |log2FC| ≥ 1
│
└─ GSEA permutations?
   └─ Final analysis: 10,000
```

---

## References

- Subramanian et al. (2005) PNAS - Original GSEA method
- Korotkevich et al. (2016) bioRxiv - Fast GSEA implementation
- Geistlinger et al. (2021) Brief Bioinform - Benchmarking enrichment methods
- Liberzon et al. (2015) Cell Systems - MSigDB Hallmark gene sets
