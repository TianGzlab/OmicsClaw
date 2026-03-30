# Gene Set Database Selection Guide

This guide helps you choose the appropriate gene set databases for your enrichment analysis based on your research question and biological context.

---

## Quick Recommendations

| Research Focus | Recommended Databases | Reason |
|----------------|----------------------|---------|
| **Exploratory analysis (default)** | Hallmark + KEGG | Good coverage, non-redundant, manageable size |
| **Metabolic pathways** | KEGG | Comprehensive metabolic pathway coverage |
| **Signaling pathways** | Reactome or KEGG | Detailed signaling cascade information |
| **Broad biological processes** | GO:BP | Comprehensive but large (may need filtering) |
| **Molecular functions** | GO:MF | Enzymatic activities, binding functions |
| **Cellular localization** | GO:CC | Subcellular compartments |
| **Cancer biology** | Hallmark + C6 (Oncogenic Signatures) | Cancer-specific pathways and signatures |
| **Immunology** | Hallmark + C7 (Immunologic Signatures) | Immune cell types and responses |
| **Hypothesis testing** | Custom gene sets | Test specific hypotheses |

---

## MSigDB Collections (via msigdbr package)

### Hallmark Gene Sets (H) - **DEFAULT**

**Size:** 50 gene sets
**Description:** Well-defined biological states and processes curated from multiple sources
**Redundancy:** LOW (coherent, non-redundant)

**When to use:**
- ✅ Exploratory analysis (default choice)
- ✅ When you want clear, interpretable results
- ✅ For presentations to non-bioinformaticians
- ✅ When pathway redundancy is a concern

**Strengths:**
- Highly curated and non-redundant
- Biologically coherent gene sets
- Easy to interpret
- Good balance of coverage and specificity

**Examples:**
- HALLMARK_APOPTOSIS
- HALLMARK_INFLAMMATORY_RESPONSE
- HALLMARK_MYC_TARGETS_V1
- HALLMARK_OXIDATIVE_PHOSPHORYLATION

**Usage:**
```r
term2gene <- get_msigdb_genesets(species = "human", categories = c("H"))
```

---

### KEGG Pathways (C2:CP:KEGG)

**Size:** ~186 gene sets (human)
**Description:** Canonical pathways from KEGG database
**Redundancy:** MODERATE

**When to use:**
- ✅ Metabolic pathway analysis
- ✅ When you need pathway diagrams (available from KEGG website)
- ✅ Signaling cascade analysis
- ✅ Cross-species comparison (KEGG has good conservation)

**Strengths:**
- Well-annotated metabolic pathways
- Diagrams available online
- Widely recognized and cited

**Limitations:**
- Not updated as frequently as Reactome
- Some gene sets are very small

**Examples:**
- KEGG_GLYCOLYSIS_GLUCONEOGENESIS
- KEGG_OXIDATIVE_PHOSPHORYLATION
- KEGG_MAPK_SIGNALING_PATHWAY

**Usage:**
```r
term2gene <- get_msigdb_genesets(species = "human", categories = c("KEGG"))
```

---

### Reactome Pathways (C2:CP:REACTOME)

**Size:** ~1,615 gene sets (human)
**Description:** Curated pathways from Reactome database
**Redundancy:** MODERATE-HIGH (hierarchical structure)

**When to use:**
- ✅ Detailed signaling pathway analysis
- ✅ When you want the most up-to-date pathway annotations
- ✅ For hierarchical pathway exploration

**Strengths:**
- Frequently updated
- Very detailed pathway hierarchy
- Excellent online visualization tools

**Limitations:**
- Large number of gene sets (may be overwhelming)
- Hierarchical redundancy (parent-child relationships)

**Examples:**
- REACTOME_CELL_CYCLE
- REACTOME_APOPTOSIS
- REACTOME_IMMUNE_SYSTEM

**Usage:**
```r
term2gene <- get_msigdb_genesets(species = "human", categories = c("REACTOME"))
```

---

### Gene Ontology (GO) Gene Sets (C5)

#### GO Biological Process (GO:BP)

**Size:** ~7,658 gene sets (human)
**Description:** Biological processes from Gene Ontology
**Redundancy:** HIGH (hierarchical structure)

**When to use:**
- ✅ Comprehensive process-level analysis
- ✅ When Hallmark/KEGG are too narrow
- ✅ For specific process hypotheses

**Strengths:**
- Most comprehensive coverage
- Standardized ontology across all organisms

**Limitations:**
- VERY LARGE (results can be overwhelming)
- High redundancy due to hierarchy
- May need filtering by size or specificity

**Examples:**
- GOBP_APOPTOTIC_PROCESS
- GOBP_CELL_CYCLE
- GOBP_IMMUNE_RESPONSE

**Usage:**
```r
term2gene <- get_msigdb_genesets(species = "human", categories = c("GO:BP"))
```

#### GO Molecular Function (GO:MF)

**Size:** ~1,738 gene sets (human)
**Description:** Molecular-level activities from Gene Ontology

**When to use:**
- ✅ Enzymatic activity analysis
- ✅ Binding function analysis
- ✅ Catalytic activity studies

**Examples:**
- GOMF_PROTEIN_KINASE_ACTIVITY
- GOMF_DNA_BINDING
- GOMF_CATALYTIC_ACTIVITY

#### GO Cellular Component (GO:CC)

**Size:** ~1,006 gene sets (human)
**Description:** Subcellular localization from Gene Ontology

**When to use:**
- ✅ Organelle-specific analysis
- ✅ Subcellular localization studies

**Examples:**
- GOCC_MITOCHONDRION
- GOCC_NUCLEUS
- GOCC_EXTRACELLULAR_MATRIX

---

### Oncogenic Signatures (C6)

**Size:** ~189 gene sets
**Description:** Gene sets from cancer-related studies

**When to use:**
- ✅ Cancer biology research
- ✅ Oncogene/tumor suppressor pathway analysis

**Examples:**
- EGFR_UP.V1_UP
- RAS_UP.V1_UP
- TP53_DN.V1_DN

**Usage:**
```r
# Hallmark + Oncogenic signatures for cancer studies
term2gene <- get_msigdb_genesets(species = "human", categories = c("H", "C6"))
```

---

### Immunologic Signatures (C7)

**Size:** ~4,872 gene sets
**Description:** Gene sets from immunology studies

**When to use:**
- ✅ Immunology research
- ✅ Immune cell type analysis
- ✅ Immune response studies

**Examples:**
- GSE22886_NAIVE_CD4_TCELL_VS_TREG_UP
- GSE2405_0H_VS_6H_ACT_CD4_TCELL_UP

---

## Combining Multiple Databases

### Recommended Combinations

**Default (Exploratory):**
```r
term2gene <- get_msigdb_genesets(species = "human", categories = c("H", "KEGG"))
```
Good balance of coverage and interpretability (~236 gene sets)

**Comprehensive (Signaling + Metabolism):**
```r
term2gene <- get_msigdb_genesets(species = "human", categories = c("H", "KEGG", "REACTOME"))
```
Very thorough but may have redundancy (~1,850 gene sets)

**Hypothesis-Driven (Specific Biology):**
```r
# Cancer example
term2gene <- get_msigdb_genesets(species = "human", categories = c("H", "C6"))

# Immunology example
term2gene <- get_msigdb_genesets(species = "human", categories = c("H", "C7"))
```

---

## Gene Set Size Filtering

Enrichment tests are sensitive to gene set size:

- **Too small (<10-15 genes):** Unstable statistics, high false positive rate
- **Too large (>500 genes):** Lack specificity, hard to interpret
- **Optimal range:** 15-500 genes (default in workflow)

**Adjust filters in scripts:**
```r
# GSEA
gsea_result <- run_gsea(ranked_genes, term2gene, min_size = 15, max_size = 500)

# ORA
ora_result <- run_ora(gene_list, term2gene, background, min_size = 10, max_size = 500)
```

---

## Species Support

MSigDB gene sets are available for:
- **Human** (Homo sapiens) - most comprehensive
- **Mouse** (Mus musculus) - human gene sets mapped to mouse orthologs

**Usage:**
```r
# Human (default)
term2gene <- get_msigdb_genesets(species = "human", categories = c("H"))

# Mouse
term2gene <- get_msigdb_genesets(species = "mouse", categories = c("H"))
```

---

## Decision Tree for Database Selection

```
Start here
    │
    ▼
Is this exploratory analysis?
    │
┌───┴───┐
│       │
YES     NO (hypothesis-driven)
│       │
▼       ▼
H + KEGG  What's your focus?
            │
        ┌───┴───┬────────┬─────────┐
        │       │        │         │
        Cancer  Immune   Metabolism Signaling
        │       │        │         │
        ▼       ▼        ▼         ▼
     H + C6   H + C7    KEGG    H + REACTOME
```

---

## References

1. **MSigDB:** Liberzon A, et al. (2015) The Molecular Signatures Database Hallmark Gene Set Collection. Cell Syst. DOI: 10.1016/j.cels.2015.12.004

2. **KEGG:** Kanehisa M, et al. (2021) KEGG: integrating viruses and cellular organisms. Nucleic Acids Res. DOI: 10.1093/nar/gkaa970

3. **Reactome:** Jassal B, et al. (2020) The reactome pathway knowledgebase. Nucleic Acids Res. DOI: 10.1093/nar/gkz1031

4. **Gene Ontology:** Ashburner M, et al. (2000) Gene Ontology: tool for the unification of biology. Nat Genet. DOI: 10.1038/75556
