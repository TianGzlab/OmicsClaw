---
doc_id: pathway-enrichment
title: Pathway Enrichment Analysis
doc_type: knowhow
critical_rule: MUST separate up and down genes for ORA and MUST NOT choose pathways by keyword filtering instead of significance
domains: [bulkrna, singlecell, general]
related_skills: [functional-enrichment-from-degs]
phases: [before_run]
search_terms: [ORA, GSEA, enrichment, pathway, KEGG, Reactome, enrichr, clusterProfiler, 富集分析, 通路富集, 通路分析, 功能富集]
priority: 0.9
---

# Pathway Enrichment Analysis

## ORA vs GSEA: Choose the Right Method

| Method | Input | Use When |
|--------|-------|----------|
| **ORA** (Over-Representation Analysis) | Discrete gene list (e.g., DEGs) | You have a defined set of significant genes |
| **GSEA** (Gene Set Enrichment Analysis) | Ranked list of ALL genes | You want to detect subtle coordinated changes |

**Common Mistake:** Using GSEA when ORA is requested, or vice versa.

### Handling Up/Down-Regulated Genes

| Method | How to Handle Direction |
|--------|------------------------|
| **ORA** | Separate up-regulated and down-regulated genes into two lists, run enrichment on each |
| **GSEA** | Use full ranked list (e.g., by log2FC or signed -log10(p)); the method handles direction automatically |

**CRITICAL for condition comparisons:** When comparing enriched pathways between conditions (e.g., "which pathways are enriched in condition A but not B"), you MUST:
1. Run separate analyses for up and down-regulated genes
2. Combine significant pathways: Condition_enriched = up_enriched ∪ down_enriched
3. Pooling up and down genes together gives DIFFERENT results

**When NOT to separate:**
- If user explicitly provides a specific gene set to analyze
- If user specifies to analyze all DEGs together

```r
# ORA: Separate up and down, then combine results
up_genes <- degs[degs$log2FC > 0, "gene"]
down_genes <- degs[degs$log2FC < 0, "gene"]

up_enrichment <- enrichKEGG(gene = up_genes, organism = 'hsa')
down_enrichment <- enrichKEGG(gene = down_genes, organism = 'hsa')

# Combine: pathways significant in EITHER direction
up_pathways <- up_enrichment$ID[up_enrichment$p.adjust < 0.05]
down_pathways <- down_enrichment$ID[down_enrichment$p.adjust < 0.05]
all_enriched_pathways <- union(up_pathways, down_pathways)

# GSEA: Use full ranked list (handles direction automatically)
ranked_genes <- setNames(degs$log2FC, degs$gene)
gsea_result <- gseKEGG(geneList = sort(ranked_genes, decreasing = TRUE), organism = 'hsa')
```

---

## ORA Tools

### R: clusterProfiler

```r
library(clusterProfiler)
library(org.Hs.eg.db)

# KEGG enrichment (ORA)
kegg_result <- enrichKEGG(
  gene = gene_list,        # Entrez IDs
  organism = 'hsa',
  pvalueCutoff = 0.05
)

# GO enrichment (ORA)
go_result <- enrichGO(
  gene = gene_list,
  OrgDb = org.Hs.eg.db,
  ont = "BP",              # BP, MF, or CC
  pvalueCutoff = 0.05
)
```

### Python: GSEApy

```python
import gseapy as gp

# ORA using Enrichr (online) - Fisher's exact test
enr = gp.enrichr(
    gene_list=my_genes,
    gene_sets='KEGG_2021_Human',  # or 'Reactome_2022', 'GO_Biological_Process_2021'
    outdir='enrichr_results'
)

# ORA using local implementation (offline)
enr = gp.enrich(
    gene_list=my_genes,
    gene_sets='KEGG_2021_Human',
    background=background_genes,  # Important: specify background
    outdir='enrich_results'
)
```

**Note:** `gp.enrichr()` and `gp.enrich()` are ORA methods. `gp.gsea()` and `gp.prerank()` are GSEA methods.

---

## Interpreting "Domain-Relevant" Pathways

**When a question asks about "immune-relevant", "cancer-related", or other domain-specific pathways:**

1. **First, run enrichment on ALL pathways** - don't pre-filter
2. **Examine ALL significantly enriched pathways** (p.adj < 0.05)
3. **Determine relevance based on biological context, NOT keywords**

### WARNING: Do NOT Use Keyword Matching

**Do NOT use keyword matching to INCLUDE or EXCLUDE pathways** - it will miss biologically relevant pathways.

Many pathways are functionally relevant without containing domain-specific keywords:
- Signaling pathways (e.g., cGMP, calcium, MAPK) regulate key cellular responses
- Metabolic pathways affect cell function across many biological contexts
- Cell death and stress response pathways are relevant to many experimental systems

**Key Insight:** Assess each enriched pathway by its biological function, not by keyword matching. A pathway without "immune" in its name may still be immune-relevant.

```python
# CORRECT: Check all enriched pathways, assess relevance by biological function
enriched = results[results['Adjusted P-value'] < 0.05]
# Review each pathway - consider its biological role in the experimental context

# WRONG: Using keywords to INCLUDE - misses relevant pathways!
# immune_pathways = results[results['Term'].str.contains('immune|T cell|cytokine')]

# ALSO WRONG: Using keywords to EXCLUDE - removes relevant pathways!
# non_immune = results[~results['Term'].str.contains('immune')]  # DON'T DO THIS
```

---

## Checklist

Before reporting pathway enrichment results:
- [ ] Used correct method (ORA for gene list, GSEA for ranked list)
- [ ] For ORA comparing conditions: separated up/down-regulated genes
- [ ] Specified appropriate background genes for ORA
- [ ] Applied multiple testing correction (adjusted p-value)
- [ ] Examined ALL enriched pathways for biological relevance
- [ ] Did not pre-filter pathways based on keyword matching
