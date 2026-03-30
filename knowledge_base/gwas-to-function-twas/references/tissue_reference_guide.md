# Tissue Reference Guide for TWAS

Comprehensive guide for selecting appropriate tissues based on trait biology.

---

## GTEx v8 Available Tissues (54 Total)

### Cardiovascular System
- **Artery_Coronary** - Coronary artery disease, atherosclerosis
- **Artery_Aorta** - Aortic aneurysm, arterial stiffness
- **Artery_Tibial** - Peripheral artery disease
- **Heart_Atrial_Appendage** - Atrial fibrillation
- **Heart_Left_Ventricle** - Heart failure, cardiomyopathy

### Metabolic Tissues
- **Liver** - Lipid metabolism, T2D, NAFLD
- **Pancreas** - Diabetes, insulin secretion
- **Adipose_Subcutaneous** - Obesity, metabolic syndrome
- **Adipose_Visceral_Omentum** - Central obesity, insulin resistance
- **Muscle_Skeletal** - Insulin sensitivity, exercise response

### Brain and Nervous System
- **Brain_Cortex** - Cognitive function, neurodegeneration
- **Brain_Cerebellum** - Motor control, ataxia
- **Brain_Hippocampus** - Memory, Alzheimer's disease
- **Brain_Substantia_nigra** - Parkinson's disease
- **Brain_Anterior_cingulate_cortex_BA24** - Psychiatric disorders
- **Brain_Putamen_basal_ganglia** - Movement disorders
- **Brain_Nucleus_accumbens_basal_ganglia** - Reward, addiction
- **Nerve_Tibial** - Peripheral neuropathy

### Immune System
- **Whole_Blood** - Autoimmune, infection, hematologic traits
- **Spleen** - Immune response
- **Cells_EBV-transformed_lymphocytes** - Immune cell function

### Respiratory
- **Lung** - Asthma, COPD, pulmonary fibrosis

### Gastrointestinal
- **Colon_Sigmoid** - Colorectal cancer, IBD
- **Colon_Transverse** - IBD, colon cancer
- **Small_Intestine_Terminal_Ileum** - Crohn's disease
- **Esophagus_Mucosa** - Barrett's esophagus, GERD
- **Esophagus_Muscularis** - Esophageal motility
- **Stomach** - Gastric cancer, ulcers

### Renal
- **Kidney_Cortex** - Chronic kidney disease, glomerular function
- **Kidney_Medulla** - Renal tubular function

### Reproductive
- **Testis** - Male infertility, testosterone
- **Ovary** - PCOS, ovarian cancer
- **Prostate** - Prostate cancer, BPH
- **Uterus** - Endometriosis, fibroids
- **Vagina** - Reproductive tract disorders
- **Breast_Mammary_Tissue** - Breast cancer

### Endocrine
- **Thyroid** - Thyroid function, autoimmune thyroid disease
- **Pituitary** - Hormone regulation
- **Adrenal_Gland** - Cortisol, stress response

### Skin
- **Skin_Sun_Exposed_Lower_leg** - Melanoma, skin aging
- **Skin_Not_Sun_Exposed_Suprapubic** - Dermatologic disorders

---

## Trait-to-Tissue Mapping

### Cardiovascular Diseases
| Trait | Primary Tissues | Secondary Tissues |
|-------|----------------|-------------------|
| Coronary artery disease | Artery_Coronary, Artery_Aorta | Heart_Left_Ventricle, Liver, Whole_Blood |
| Atrial fibrillation | Heart_Atrial_Appendage | Heart_Left_Ventricle, Whole_Blood |
| Hypertension | Artery_Aorta, Artery_Tibial | Kidney_Cortex, Adrenal_Gland |
| Heart failure | Heart_Left_Ventricle | Heart_Atrial_Appendage, Liver |

### Metabolic Disorders
| Trait | Primary Tissues | Secondary Tissues |
|-------|----------------|-------------------|
| Type 2 diabetes | Pancreas, Liver | Adipose_Visceral, Muscle_Skeletal |
| Obesity | Adipose_Subcutaneous, Adipose_Visceral | Hypothalamus, Liver |
| Hyperlipidemia | Liver | Adipose, Small_Intestine |
| NAFLD | Liver | Adipose_Visceral, Pancreas |

### Neurological Disorders
| Trait | Primary Tissues | Secondary Tissues |
|-------|----------------|-------------------|
| Alzheimer's disease | Brain_Hippocampus, Brain_Cortex | Brain_Frontal_Cortex |
| Parkinson's disease | Brain_Substantia_nigra | Brain_Putamen |
| Schizophrenia | Brain_Cortex, Brain_Hippocampus | Brain_Anterior_cingulate |
| Depression | Brain_Anterior_cingulate | Brain_Hippocampus |

### Autoimmune Diseases
| Trait | Primary Tissues | Secondary Tissues |
|-------|----------------|-------------------|
| Rheumatoid arthritis | Whole_Blood, EBV_lymphocytes | Spleen |
| Crohn's disease | Small_Intestine, Colon_Transverse | Whole_Blood |
| Ulcerative colitis | Colon_Sigmoid, Colon_Transverse | Whole_Blood |
| Multiple sclerosis | Brain_Cortex, Brain_Cerebellum | Whole_Blood |

---

## Data-Driven Tissue Selection with LDSC

For rigorous studies, use LDSC partitioned heritability to identify tissues statistically enriched for trait heritability.

**See [gwas-heritability-ldsc](../../gwas-heritability-ldsc/) workflow** for:
- Running LDSC tissue enrichment analysis
- Statistical evidence for tissue relevance
- Unbiased tissue recommendations

**When to use LDSC-based selection:**
- Novel traits with uncertain tissue relevance
- Comprehensive analyses requiring statistical rigor
- Publishing results (reviewers expect statistical justification)

**When biology-based selection is acceptable:**
- Well-studied traits with clear tissue relevance (e.g., CAD → Artery)
- Exploratory hypothesis generation
- Time/resource constraints

---

## TCGA Cancer Tissues

For cancer GWAS, use TCGA expression references:
- **BRCA**: Breast invasive carcinoma
- **LUAD**: Lung adenocarcinoma
- **COAD**: Colon adenocarcinoma
- **PRAD**: Prostate adenocarcinoma
- **THCA**: Thyroid carcinoma
- (+ 28 more cancer types)

---

## How Many Tissues to Analyze?

**Conservative (3-5 tissues)**:
- Disease-specific tissues only
- Reduces multiple testing burden
- Faster runtime

**Moderate (5-10 tissues)**:
- Primary + secondary tissues
- Balance between discovery and specificity
- Recommended for most studies

**Comprehensive (S-MultiXcan, all 54 tissues)**:
- Maximum discovery power
- Cross-tissue meta-analysis
- Good for polygenic traits affecting multiple systems

---

**Last Updated:** 2026-01-28
