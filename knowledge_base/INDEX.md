# Knowledge Base Index

> OmicsClaw Multi-Omics Knowledge Base
> Reorganized: 2026-03-29
> Total workflows: 28 | Shared documents: 41

## Structure

```
knowledge_base/
├── <workflow-id>/
│   ├── SKILL.md          ← YAML metadata + complete execution guide
│   ├── scripts/          ← Executable scripts (R or Python)
│   ├── references/       ← Decision guides, troubleshooting, best practices
│   └── assets/           ← Evaluation test suites (select workflows only)
├── skill-guides/         ← Evolving implementation-aligned guides derived from current OmicsClaw skills
├── knowhows/             ← Cross-workflow best practices and domain knowledge
└── INDEX.md
```

---

## Workflows (28)

| Workflow ID | Name | Scripts | References | Language | Assets |
|---|---|---|---|---|---|
| [bulk-omics-clustering](bulk-omics-clustering/SKILL.md) | Bulk Omics Clustering Analysis | 17 | 8 | R + Python |  |
| [bulk-rnaseq-counts-to-de-deseq2](bulk-rnaseq-counts-to-de-deseq2/SKILL.md) | Bulk RNAseq differential expression (DeSeq2) | 8 | 4 | R |  |
| [cell-cell-communication](cell-cell-communication/SKILL.md) | Cell-Cell Communication Analysis (CellChat) | 5 | 2 | R |  |
| [chip-atlas-diff-analysis](chip-atlas-diff-analysis/SKILL.md) | ChIP-Atlas Diff Analysis | 11 | 3 | Python |  |
| [chip-atlas-peak-enrichment](chip-atlas-peak-enrichment/SKILL.md) | ChIP-Atlas Peak Enrichment | 9 | 4 | Python |  |
| [chip-atlas-target-genes](chip-atlas-target-genes/SKILL.md) | ChIP-Atlas Target Genes | 8 | 3 | Python |  |
| [clinicaltrials-landscape](clinicaltrials-landscape/SKILL.md) | ClinicalTrials.gov Disease Landscape Scanner | 9 | 3 | Python |  |
| [coexpression-network](coexpression-network/SKILL.md) | Weighted Gene Co-expression Network Analysis (WGCNA) | 14 | 4 | R |  |
| [disease-progression-longitudinal](disease-progression-longitudinal/SKILL.md) | Disease Progression Trajectory Analysis | 14 | 7 | R + Python |  |
| [experimental-design-statistics](experimental-design-statistics/SKILL.md) | Experimental Design | 11 | 7 | R |  |
| [functional-enrichment-from-degs](functional-enrichment-from-degs/SKILL.md) | Functional Enrichment Analysis (GSEA + ORA) | 8 | 6 | R |  |
| [genetic-variant-annotation](genetic-variant-annotation/SKILL.md) | Genetic Variant Annotation | 16 | 10 | Python |  |
| [grn-pyscenic](grn-pyscenic/SKILL.md) | Gene Regulatory Network Inference (pySCENIC) | 7 | 2 | Python |  |
| [gwas-to-function-twas](gwas-to-function-twas/SKILL.md) | GWAS to Function via TWAS | 14 | 8 | Python |  |
| [lasso-biomarker-panel](lasso-biomarker-panel/SKILL.md) | LASSO Biomarker Panel Discovery & Validation | 9 | 3 | R + Python |  |
| [literature-preclinical](literature-preclinical/SKILL.md) | Preclinical Literature Extraction | 7 | 1 | R + Python |  |
| [mendelian-randomization-twosamplemr](mendelian-randomization-twosamplemr/SKILL.md) | Two-Sample Mendelian Randomization | 5 | 2 | R |  |
| [multi-omics-integration](multi-omics-integration/SKILL.md) | Multi-Omics Integration (MOFA+) | 4 | 1 | R |  |
| [pcr-primer-design](pcr-primer-design/SKILL.md) | PCR Primer Design | 11 | 5 | Python |  |
| [polygenic-risk-score-prs-catalog](polygenic-risk-score-prs-catalog/SKILL.md) | Polygenic Risk Score (PGS Catalog) | 5 | 2 | R |  |
| [pooled-crispr-screens](pooled-crispr-screens/SKILL.md) | Pooled CRISPR Screen Analysis | 17 | 5 | R + Python |  |
| [proteomics-diff-exp](proteomics-diff-exp/SKILL.md) | Proteomics Differential Expression (limma + DEqMS) | 5 | 2 | R |  |
| [scrna-trajectory-inference](scrna-trajectory-inference/SKILL.md) | Single-Cell Trajectory Inference | 5 | 4 | Python |  |
| [scrnaseq-scanpy-core-analysis](scrnaseq-scanpy-core-analysis/SKILL.md) | Single-Cell RNA-seq Core Analysis (Scanpy) | 18 | 10 | Python |  |
| [scrnaseq-seurat-core-analysis](scrnaseq-seurat-core-analysis/SKILL.md) | Single-Cell RNA-seq Core Analysis (Seurat) | 20 | 11 | R |  |
| [spatial-transcriptomics](spatial-transcriptomics/SKILL.md) | Spatial Transcriptomics Visium Analysis | 4 | 1 | Python |  |
| [survival-analysis-clinical](survival-analysis-clinical/SKILL.md) | Clinical Survival & Outcome Analysis | 4 | 2 | R |  |
| [upstream-regulator-analysis](upstream-regulator-analysis/SKILL.md) | Upstream Regulator Analysis | 8 | 1 | Python |  |

---

## Knowhows (Cross-Workflow Guardrails)

_Universal best practices and domain knowledge rules that apply across all workflows (enforced before any analysis)._

| Document | Description |
|---|---|
| [knowhows/KH-bulk-rnaseq-differential-expression.md](knowhows/KH-bulk-rnaseq-differential-expression.md) | Best practices for RNA-seq DE analysis (use padj, not pvalue) |
| [knowhows/KH-data-analysis-best-practices.md](knowhows/KH-data-analysis-best-practices.md) | General data analysis rules (duplicates, missing values, ID matching) |
| [knowhows/KH-gene-essentiality.md](knowhows/KH-gene-essentiality.md) | Gene essentiality analysis (DepMap negative score = essential) |
| [knowhows/KH-pathway-enrichment.md](knowhows/KH-pathway-enrichment.md) | Pathway enrichment analysis rules and interpretation |
| [knowhows/KH-scatac-preprocessing-guardrails.md](knowhows/KH-scatac-preprocessing-guardrails.md) | Short high-level guardrails for choosing and explaining scATAC preprocessing runs |
| [knowhows/KH-spatial-condition-guardrails.md](knowhows/KH-spatial-condition-guardrails.md) | Short high-level guardrails for pseudobulk spatial condition comparisons |
| [knowhows/KH-spatial-trajectory-guardrails.md](knowhows/KH-spatial-trajectory-guardrails.md) | Short high-level guardrails for selecting and explaining spatial trajectory runs |
| [knowhows/KH-spatial-register-guardrails.md](knowhows/KH-spatial-register-guardrails.md) | Short high-level guardrails for selecting and explaining spatial registration runs |
| [knowhows/KH-spatial-de-guardrails.md](knowhows/KH-spatial-de-guardrails.md) | Short high-level guardrails for choosing between exploratory marker ranking and sample-aware spatial DE |
| [knowhows/KH-spatial-enrichment-guardrails.md](knowhows/KH-spatial-enrichment-guardrails.md) | Short high-level guardrails for selecting and explaining spatial enrichment methods |
| [knowhows/KH-spatial-cnv-guardrails.md](knowhows/KH-spatial-cnv-guardrails.md) | Short high-level guardrails for choosing and explaining spatial CNV analyses |
| [knowhows/KH-spatial-annotate-guardrails.md](knowhows/KH-spatial-annotate-guardrails.md) | Short high-level guardrails for selecting and explaining spatial annotation runs |
| [knowhows/KH-spatial-communication-guardrails.md](knowhows/KH-spatial-communication-guardrails.md) | Short high-level guardrails for selecting and explaining spatial communication analyses |
| [knowhows/KH-spatial-deconv-guardrails.md](knowhows/KH-spatial-deconv-guardrails.md) | Short high-level guardrails for choosing and explaining spatial deconvolution analyses |
| [knowhows/KH-spatial-domain-guardrails.md](knowhows/KH-spatial-domain-guardrails.md) | Short high-level guardrails for choosing and explaining spatial domain analyses |
| [knowhows/KH-spatial-genes-guardrails.md](knowhows/KH-spatial-genes-guardrails.md) | Short high-level guardrails for matrix-aware SVG method selection and explanation |
| [knowhows/KH-spatial-integrate-guardrails.md](knowhows/KH-spatial-integrate-guardrails.md) | Short high-level guardrails for selecting and explaining spatial integration runs |
| [knowhows/KH-spatial-preprocess-guardrails.md](knowhows/KH-spatial-preprocess-guardrails.md) | Short high-level guardrails for choosing and explaining spatial preprocessing runs |
| [knowhows/KH-spatial-raw-processing-guardrails.md](knowhows/KH-spatial-raw-processing-guardrails.md) | Short high-level guardrails for sequencing-level spatial FASTQ processing and downstream handoff |
| [knowhows/KH-spatial-statistics-guardrails.md](knowhows/KH-spatial-statistics-guardrails.md) | Short high-level guardrails for choosing between cluster, gene, and graph-level spatial statistics |
| [knowhows/KH-spatial-velocity-guardrails.md](knowhows/KH-spatial-velocity-guardrails.md) | Short high-level guardrails for choosing and explaining spatial RNA velocity runs |
| [knowhows/KH-sc-differential-abundance-guardrails.md](knowhows/KH-sc-differential-abundance-guardrails.md) | Short high-level guardrails for sample-aware differential abundance and compositional analysis |
| [knowhows/KH-sc-metacell-guardrails.md](knowhows/KH-sc-metacell-guardrails.md) | Short high-level guardrails for metacell construction, compression, and interpretation boundaries |
| [knowhows/KH-sc-gene-programs-guardrails.md](knowhows/KH-sc-gene-programs-guardrails.md) | Short high-level guardrails for de novo gene program discovery and usage interpretation |

---

## Skill Guides (Implementation-Aligned, Evolving)

_These are not part of the 28 validated workflows. They capture longer method-selection and tuning guidance derived from current OmicsClaw skill implementations._

### Recommended Single-Cell Starting Point

If a user is new to scRNA analysis and does not know which skill to run first,
start here:

- [skill-guides/singlecell/sc-rna-quickstart.md](skill-guides/singlecell/sc-rna-quickstart.md) — beginner route from raw FASTQ or existing h5ad into the current OmicsClaw scRNA workflow

| Document | Description |
|---|---|
| [skill-guides/README.md](skill-guides/README.md) | Explains how skill guides differ from validated workflows and from knowhow guardrails |
| [skill-guides/singlecell/sc-rna-quickstart.md](skill-guides/singlecell/sc-rna-quickstart.md) | Beginner-friendly routing guide for the mainstream scRNA path from FASTQ to downstream-ready h5ad |
| [skill-guides/singlecell/sc-fastq-qc.md](skill-guides/singlecell/sc-fastq-qc.md) | Implementation-aware guide for raw single-cell FASTQ QC and FastQC / MultiQC interpretation |
| [skill-guides/singlecell/sc-count.md](skill-guides/singlecell/sc-count.md) | Implementation-aware guide for the main scRNA counting skill, including Cell Ranger, STARsolo, and advanced pseudoalignment backends |
| [skill-guides/singlecell/sc-standardize-input.md](skill-guides/singlecell/sc-standardize-input.md) | Implementation-aware guide for stabilizing external AnnData input before downstream scRNA analysis |
| [skill-guides/singlecell/sc-qc.md](skill-guides/singlecell/sc-qc.md) | Implementation-aware guide for scRNA QC before filtering |
| [skill-guides/singlecell/sc-preprocessing.md](skill-guides/singlecell/sc-preprocessing.md) | Implementation-aware guide for normalization, HVG selection, PCA, UMAP, and clustering |
| [skill-guides/singlecell/sc-velocity-prep.md](skill-guides/singlecell/sc-velocity-prep.md) | Implementation-aware guide for preparing spliced / unspliced layers before scVelo analysis |
| [skill-guides/singlecell/sc-velocity.md](skill-guides/singlecell/sc-velocity.md) | Implementation-aware guide for scVelo mode selection and velocity interpretation |
| [skill-guides/singlecell/scatac-preprocessing.md](skill-guides/singlecell/scatac-preprocessing.md) | Detailed OmicsClaw-specific parameter and scope guide for scATAC preprocessing |
| [skill-guides/singlecell/sc-differential-abundance.md](skill-guides/singlecell/sc-differential-abundance.md) | Detailed OmicsClaw-specific method selection and tuning guide for sample-aware differential abundance and compositional analysis |
| [skill-guides/singlecell/sc-metacell.md](skill-guides/singlecell/sc-metacell.md) | Detailed OmicsClaw-specific guide for metacell construction, summarization, and interpretation |
| [skill-guides/singlecell/sc-gene-programs.md](skill-guides/singlecell/sc-gene-programs.md) | Detailed OmicsClaw-specific guide for gene program discovery, factor selection, and program interpretation |
| [skill-guides/spatial/spatial-annotate.md](skill-guides/spatial/spatial-annotate.md) | Detailed OmicsClaw-specific method selection and tuning guide for spatial annotation |
| [skill-guides/spatial/spatial-condition.md](skill-guides/spatial/spatial-condition.md) | Detailed OmicsClaw-specific method selection and tuning guide for spatial condition comparison |
| [skill-guides/spatial/spatial-de.md](skill-guides/spatial/spatial-de.md) | Detailed OmicsClaw-specific method selection and tuning guide for spatial differential expression |
| [skill-guides/spatial/spatial-enrichment.md](skill-guides/spatial/spatial-enrichment.md) | Detailed OmicsClaw-specific method selection and tuning guide for spatial pathway enrichment |
| [skill-guides/spatial/spatial-cnv.md](skill-guides/spatial/spatial-cnv.md) | Detailed OmicsClaw-specific method selection and tuning guide for spatial CNV inference |
| [skill-guides/spatial/spatial-communication.md](skill-guides/spatial/spatial-communication.md) | Detailed OmicsClaw-specific method selection and tuning guide for spatial cell-cell communication |
| [skill-guides/spatial/spatial-deconv.md](skill-guides/spatial/spatial-deconv.md) | Detailed OmicsClaw-specific method selection and tuning guide for spatial deconvolution |
| [skill-guides/spatial/spatial-domains.md](skill-guides/spatial/spatial-domains.md) | Detailed OmicsClaw-specific method selection and tuning guide for spatial domain identification |
| [skill-guides/spatial/spatial-genes.md](skill-guides/spatial/spatial-genes.md) | Detailed OmicsClaw-specific method selection and tuning guide for spatially variable gene detection |
| [skill-guides/spatial/spatial-integrate.md](skill-guides/spatial/spatial-integrate.md) | Detailed OmicsClaw-specific method selection and tuning guide for spatial multi-sample integration |
| [skill-guides/spatial/spatial-preprocess.md](skill-guides/spatial/spatial-preprocess.md) | Detailed OmicsClaw-specific parameter and loader guide for spatial preprocessing |
| [skill-guides/spatial/spatial-raw-processing.md](skill-guides/spatial/spatial-raw-processing.md) | Detailed OmicsClaw-specific guide for sequencing-level spatial FASTQ processing and handoff to preprocessing |
| [skill-guides/spatial/spatial-statistics.md](skill-guides/spatial/spatial-statistics.md) | Detailed OmicsClaw-specific method selection and tuning guide for spatial statistics |
| [skill-guides/spatial/spatial-velocity.md](skill-guides/spatial/spatial-velocity.md) | Detailed OmicsClaw-specific method selection and tuning guide for spatial RNA velocity |
| [skill-guides/spatial/spatial-register.md](skill-guides/spatial/spatial-register.md) | Detailed OmicsClaw-specific method selection and tuning guide for spatial registration |
| [skill-guides/spatial/spatial-trajectory.md](skill-guides/spatial/spatial-trajectory.md) | Detailed OmicsClaw-specific method selection and tuning guide for spatial trajectory analysis |

---

_Generated by OmicsClaw knowledge base reorganization — 2026-03-28_
