# Workflow Integration Patterns

This document describes how the disease-progression-longitudinal workflow integrates with upstream and downstream workflows in the repository.

---

## Upstream Workflows

### From Bulk RNA-seq Analysis

**Workflow:** [bulk-rnaseq-counts-to-de-deseq2](../../bulk-rnaseq-counts-to-de-deseq2/)

Use normalized counts from bulk RNA-seq analysis as input for trajectory analysis.

**Data flow:**
```
bulk-rnaseq-counts-to-de-deseq2/
    ├─> normalized_counts.csv (VST or rlog transformed)
    └─> sample_metadata.csv
        └─> disease-progression-longitudinal/
            └─> Load as input data
```

**Integration code:**
```python
# Load normalized counts from DESeq2 workflow
import pandas as pd

# VST/rlog normalized data from DESeq2
data = pd.read_csv("../bulk-rnaseq-counts-to-de-deseq2/results/normalized_counts.csv", index_col=0)
metadata = pd.read_csv("../bulk-rnaseq-counts-to-de-deseq2/data/sample_metadata.csv")

# Ensure metadata has required columns for trajectory analysis
assert 'patient_id' in metadata.columns
assert 'timepoint' in metadata.columns

# Proceed with trajectory analysis
from scripts.load_longitudinal_data import load_and_validate
data_validated, metadata_validated = load_and_validate(
    data_matrix=data,
    metadata=metadata,
    min_patients=10,
    min_timepoints=3
)
```

**Notes:**
- Use **variance-stabilized transformed (VST)** or **rlog** counts, not raw counts
- DESeq2 batch correction (via `design=~batch+condition`) carries over
- Remove treatment effects if analyzing disease progression independent of treatment

---

### From Single-Cell RNA-seq Analysis (Pseudobulk)

**Workflow:** [scrnaseq-seurat-core-analysis](../../scrnaseq-seurat-core-analysis/) or [scrnaseq-scanpy-core-analysis](../../scrnaseq-scanpy-core-analysis/)

Aggregate single-cell data to pseudobulk profiles per patient/timepoint.

**Data flow:**
```
scrnaseq-seurat-core-analysis/
    └─> Single-cell object with cell type annotations
        └─> Aggregate to pseudobulk per patient × timepoint × cell type
            └─> disease-progression-longitudinal/
```

**Integration code (R to Python):**

```R
# In R: Create pseudobulk from Seurat object
library(Seurat)
library(tidyverse)

# Aggregate counts by patient, timepoint, and cell type
pseudobulk <- AggregateExpression(
  seurat_obj,
  group.by = c("patient_id", "timepoint", "cell_type"),
  assays = "RNA",
  slot = "counts",
  return.seurat = FALSE
)

# Extract matrix
pseudobulk_mat <- pseudobulk$RNA

# Create metadata
metadata <- data.frame(
  sample_id = colnames(pseudobulk_mat),
  patient_id = str_extract(colnames(pseudobulk_mat), "^[^_]+"),
  timepoint = str_extract(colnames(pseudobulk_mat), "(?<=_)[0-9.]+"),
  cell_type = str_extract(colnames(pseudobulk_mat), "[^_]+$")
)

# Export for Python trajectory analysis
write.csv(pseudobulk_mat, "pseudobulk_counts.csv")
write.csv(metadata, "pseudobulk_metadata.csv", row.names = FALSE)
```

```python
# In Python: Load pseudobulk data
import pandas as pd
from scripts.preprocess_features import preprocess_omics

data = pd.read_csv("pseudobulk_counts.csv", index_col=0)
metadata = pd.read_csv("pseudobulk_metadata.csv")

# Normalize pseudobulk counts
data_processed = preprocess_omics(
    data,
    metadata,
    data_type='rnaseq',
    normalization='log_cpm'
)

# Run trajectory analysis per cell type
for cell_type in metadata['cell_type'].unique():
    ct_mask = metadata['cell_type'] == cell_type
    # Trajectory analysis for this cell type...
```

---

### From Proteomics Analysis

**Workflow:** Mass spectrometry proteomics preprocessing

**Data requirements:**
- Protein abundance matrix (log2 transformed intensities)
- Sample metadata with patient IDs and timepoints
- Batch correction if multiple MS runs

**Integration code:**
```python
# Load proteomics data
data = pd.read_csv("protein_abundance.csv", index_col=0)  # Proteins × Samples
metadata = pd.read_csv("sample_metadata.csv")

# Preprocess proteomics data
from scripts.preprocess_features import preprocess_omics

data_processed = preprocess_omics(
    data,
    metadata,
    data_type='proteomics',
    normalization='zscore',         # Z-score normalization common for proteomics
    batch_correction=True,
    batch_column='ms_batch',
    filter_low_variance=True
)

# Proceed with trajectory analysis
```

---

### From Metabolomics Analysis

**Workflow:** Untargeted metabolomics preprocessing

**Data requirements:**
- Metabolite abundance matrix (normalized peak intensities)
- Sample metadata with patient IDs and timepoints
- QC samples for batch correction

**Integration code:**
```python
# Load metabolomics data
data = pd.read_csv("metabolite_abundance.csv", index_col=0)  # Metabolites × Samples
metadata = pd.read_csv("sample_metadata.csv")

# Preprocess metabolomics data
from scripts.preprocess_features import preprocess_omics

data_processed = preprocess_omics(
    data,
    metadata,
    data_type='metabolomics',
    normalization='log2',
    batch_correction=True,
    batch_column='batch',
    filter_low_variance=True
)

# Proceed with trajectory analysis
```

---

## Downstream Workflows

### To Functional Enrichment Analysis

**Workflow:** [functional-enrichment-from-degs](../../functional-enrichment-from-degs/)

Analyze trajectory-associated features using functional enrichment.

**Data flow:**
```
disease-progression-longitudinal/
    └─> trajectory_features.csv (top trajectory-associated genes)
        └─> functional-enrichment-from-degs/
            └─> Pathway enrichment analysis
```

**Integration code:**
```python
# Export trajectory features in DEG format for enrichment analysis
trajectory_features = pd.read_csv("trajectory_features.csv")

# Convert to DEG format (required columns: gene, log2FoldChange, padj)
deg_format = trajectory_features[['feature', 'correlation', 'padj']].copy()
deg_format.columns = ['gene', 'log2FoldChange', 'padj']  # Rename columns
deg_format.to_csv("trajectory_features_for_enrichment.csv", index=False)

# Now use functional-enrichment-from-degs workflow
```

**Expected output:**
- Enriched pathways along disease trajectory
- Biological processes associated with progression
- Upstream regulators (transcription factors, kinases)

---

### To Tissue Expression Analysis

**Workflow:** [tissue-expression-from-degs](../../tissue-expression-from-degs/)

Identify tissue specificity of trajectory-associated genes.

**Data flow:**
```
disease-progression-longitudinal/
    └─> trajectory_features.csv (top trajectory-associated genes)
        └─> tissue-expression-from-degs/
            └─> Query ARCHS4, GTEx, CellxGene databases
```

**Integration code:**
```python
# Extract top trajectory genes
trajectory_features = pd.read_csv("trajectory_features.csv")
top_genes = trajectory_features.nlargest(50, 'correlation')['feature'].tolist()

# Export gene list
with open("trajectory_genes.txt", "w") as f:
    f.write("\n".join(top_genes))

# Use tissue-expression-from-degs workflow to query tissue databases
```

**Use cases:**
- Identify tissue-specific biomarkers for disease progression
- Validate that trajectory genes are relevant to disease tissue
- Discover cell-type-specific progression markers

---

### To Transcription Factor Activity Analysis

**Workflow:** [tf-activity](../../tf-activity/) (if available)

Infer transcription factor activity changes along disease trajectory.

**Data flow:**
```
disease-progression-longitudinal/
    └─> data_processed.csv (all samples with pseudotime)
        └─> tf-activity/
            └─> Infer TF activity per sample
                └─> Plot TF activity along pseudotime
```

**Integration code:**
```python
# Export processed data with pseudotime for TF activity analysis
data_with_pseudotime = data_processed.copy()
data_with_pseudotime.columns = metadata['sample_id']

# Add pseudotime as metadata row
pseudotime_row = pd.Series(pseudotime, index=metadata['sample_id'], name='pseudotime')

# Export
data_with_pseudotime.to_csv("expression_with_pseudotime.csv")
metadata['pseudotime'] = pseudotime
metadata.to_csv("metadata_with_pseudotime.csv", index=False)

# Use tf-activity workflow to analyze TF dynamics
# Expected: identify TFs driving disease progression at each stage
```

---

### To Survival Analysis

Predict clinical outcomes from trajectory position.

**Internal script:** [clinical_validation.py](../scripts/clinical_validation.py)

**Data flow:**
```
disease-progression-longitudinal/
    └─> pseudotime_assignments.csv (pseudotime per sample)
        └─> Survival analysis (Cox PH, Kaplan-Meier)
            └─> Outcome prediction models
```

**Integration code:**
```python
from scripts.clinical_validation import survival_analysis

# Perform survival analysis
survival_results = survival_analysis(
    metadata,
    pseudotime_column='pseudotime',
    time_column='time_to_event',
    event_column='event_occurred'
)

# Results include:
# - Cox PH hazard ratio
# - Kaplan-Meier curves by trajectory group
# - C-index (concordance index)
```

---

### To Machine Learning Outcome Prediction

Build predictive models using trajectory position as feature.

**Data flow:**
```
disease-progression-longitudinal/
    └─> pseudotime + trajectory features
        └─> Machine learning model (logistic regression, random forest, neural network)
            └─> Predict treatment response, disease subtype, clinical outcome
```

**Example code:**
```python
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import cross_val_score

# Combine pseudotime with top trajectory features
X = data_processed.loc[top_features['feature'].head(20), :].T
X['pseudotime'] = pseudotime

y = metadata['outcome']  # Binary outcome (e.g., responder vs. non-responder)

# Train random forest classifier
clf = RandomForestClassifier(n_estimators=100, random_state=42)
cv_scores = cross_val_score(clf, X, y, cv=5, scoring='roc_auc')

print(f"Cross-validated AUC: {cv_scores.mean():.3f} ± {cv_scores.std():.3f}")
```

---

## Multi-Omics Integration

### Parallel Trajectories from Multiple Data Types

Analyze disease progression using multiple omics layers.

**Workflow:**
```
1. Run trajectory analysis separately for each omics type:
   - disease-progression-longitudinal/ with RNA-seq
   - disease-progression-longitudinal/ with proteomics
   - disease-progression-longitudinal/ with metabolomics

2. Compare pseudotime assignments across omics layers

3. Integrate using consensus pseudotime or joint modeling
```

**Integration code:**
```python
# Load pseudotime from each omics layer
pseudotime_rnaseq = pd.read_csv("rnaseq_trajectory/pseudotime_assignments.csv")
pseudotime_proteomics = pd.read_csv("proteomics_trajectory/pseudotime_assignments.csv")
pseudotime_metabolomics = pd.read_csv("metabolomics_trajectory/pseudotime_assignments.csv")

# Merge by sample ID
multi_omics = pseudotime_rnaseq.merge(pseudotime_proteomics, on='sample_id', suffixes=('_rna', '_prot'))
multi_omics = multi_omics.merge(pseudotime_metabolomics, on='sample_id')
multi_omics.columns = ['sample_id', 'pseudotime_rna', 'pseudotime_prot', 'pseudotime_metab']

# Check correlation between omics layers
from scipy.stats import spearmanr
corr_rna_prot, _ = spearmanr(multi_omics['pseudotime_rna'], multi_omics['pseudotime_prot'])
corr_rna_metab, _ = spearmanr(multi_omics['pseudotime_rna'], multi_omics['pseudotime_metab'])
corr_prot_metab, _ = spearmanr(multi_omics['pseudotime_prot'], multi_omics['pseudotime_metab'])

print(f"RNA-Protein: r={corr_rna_prot:.3f}")
print(f"RNA-Metabolite: r={corr_rna_metab:.3f}")
print(f"Protein-Metabolite: r={corr_prot_metab:.3f}")

# Consensus pseudotime (average)
multi_omics['pseudotime_consensus'] = multi_omics[
    ['pseudotime_rna', 'pseudotime_prot', 'pseudotime_metab']
].mean(axis=1)

# Use consensus pseudotime for downstream analysis
```

---

## Cross-Study Integration

### Batch Correction Across Studies

Integrate trajectory analysis from multiple independent cohorts.

**Approach 1: Batch correction before trajectory analysis**
```python
from combat import combat

# Combine data from multiple studies
data_study1 = pd.read_csv("study1_data.csv", index_col=0)
data_study2 = pd.read_csv("study2_data.csv", index_col=0)
data_combined = pd.concat([data_study1, data_study2], axis=1)

metadata_combined = pd.concat([metadata_study1, metadata_study2])

# Batch correction
data_corrected = combat(data_combined, metadata_combined['study'])

# Run trajectory analysis on corrected data
from scripts.timeax_alignment import run_timeax_alignment
model, results = run_timeax_alignment(data_corrected, metadata_combined)
```

**Approach 2: Train on one study, project another**
```python
# Train trajectory on study 1
model_study1, results1 = run_timeax_alignment(data_study1, metadata_study1)

# Project study 2 samples onto study 1 trajectory
from scripts.timeax_inference import project_new_samples
pseudotime_study2 = project_new_samples(model_study1, data_study2)

# Validate: check if trajectory features replicate
```

---

## Clinical Translation

### From Research to Clinical Application

**Workflow for clinical implementation:**

1. **Discovery phase:** disease-progression-longitudinal on research cohort
2. **Validation phase:** Validate trajectory in independent cohort
3. **Clinical deployment:** Project new patients onto validated trajectory

**Implementation:**
```python
# 1. Train on discovery cohort
discovery_model, discovery_results = run_timeax_alignment(
    discovery_data, discovery_metadata
)

# Save model for clinical use
import pickle
with open("clinical_trajectory_model.pkl", "wb") as f:
    pickle.dump(discovery_model, f)

# 2. Validate on independent cohort
validation_pseudotime = project_new_samples(discovery_model, validation_data)

# 3. Clinical deployment: project new patient samples
def clinical_staging_pipeline(patient_data):
    """Assign disease stage to new patient sample."""
    # Load pre-trained model
    with open("clinical_trajectory_model.pkl", "rb") as f:
        model = pickle.load(f)

    # Preprocess patient data
    patient_processed = preprocess_omics(patient_data, ...)

    # Project onto trajectory
    pseudotime = project_new_samples(model, patient_processed)

    # Convert pseudotime to clinical stage
    if pseudotime < 0.33:
        stage = "Early"
    elif pseudotime < 0.67:
        stage = "Intermediate"
    else:
        stage = "Advanced"

    return pseudotime, stage

# Use in clinic
patient_pseudotime, patient_stage = clinical_staging_pipeline(new_patient_data)
print(f"Patient disease stage: {patient_stage} (pseudotime={patient_pseudotime:.3f})")
```

---

## Data Format Requirements

### Input Format from Upstream Workflows

**Expected data structure:**

```
data.csv (Features × Samples)
    ├─ Row names: feature IDs (gene symbols, protein IDs, metabolite IDs)
    ├─ Column names: sample IDs
    └─ Values: normalized expression/abundance

metadata.csv (Samples × Annotations)
    ├─ sample_id: matches column names in data.csv
    ├─ patient_id: patient identifier (for grouping timepoints)
    ├─ timepoint: numeric time value (days, weeks, months)
    ├─ outcome: clinical outcome (optional)
    ├─ batch: batch identifier (optional, for batch correction)
    └─ other covariates: age, sex, treatment, etc.
```

### Output Format for Downstream Workflows

**Generated files:**

```
pseudotime_assignments.csv
    ├─ sample_id
    ├─ patient_id
    ├─ timepoint
    └─ pseudotime (0-1 normalized disease progression)

trajectory_features.csv
    ├─ feature (gene/protein/metabolite ID)
    ├─ correlation (Spearman correlation with pseudotime)
    ├─ pvalue
    └─ padj (FDR-adjusted p-value)

patient_summaries.csv
    ├─ patient_id
    ├─ n_timepoints
    ├─ baseline_pseudotime (first timepoint)
    ├─ final_pseudotime (last timepoint)
    ├─ progression_rate (change per unit time)
    └─ outcome
```

---

## Example Integration Pipelines

### Pipeline 1: RNA-seq → Trajectory → Enrichment

```bash
# Step 1: Bulk RNA-seq analysis
cd bulk-rnaseq-counts-to-de-deseq2/
# Run workflow to generate normalized_counts.csv

# Step 2: Trajectory analysis
cd ../disease-progression-longitudinal/
python3 << EOF
from scripts.load_longitudinal_data import load_and_validate
from scripts.preprocess_features import preprocess_omics
from scripts.timeax_alignment import run_timeax_alignment
from scripts.identify_trajectory_features import find_trajectory_features

# Load data
data, metadata = load_and_validate(
    "../bulk-rnaseq-counts-to-de-deseq2/results/normalized_counts.csv",
    "../bulk-rnaseq-counts-to-de-deseq2/data/sample_metadata.csv"
)

# Preprocess
data_processed = preprocess_omics(data, metadata, data_type='rnaseq')

# Trajectory
model, results = run_timeax_alignment(data_processed, metadata)
pseudotime = results['pseudotime']

# Features
trajectory_features = find_trajectory_features(data_processed, pseudotime)
trajectory_features.to_csv("trajectory_features.csv", index=False)
EOF

# Step 3: Functional enrichment
cd ../functional-enrichment-from-degs/
# Run workflow on trajectory_features.csv
```

### Pipeline 2: Multi-Omics → Trajectory → Outcome Prediction

```python
# Integrate RNA-seq, proteomics, metabolomics trajectories

# Step 1: Load each omics layer
rnaseq_data = pd.read_csv("rnaseq_normalized.csv", index_col=0)
proteomics_data = pd.read_csv("proteomics_normalized.csv", index_col=0)
metabolomics_data = pd.read_csv("metabolomics_normalized.csv", index_col=0)

# Step 2: Run trajectory analysis for each
from scripts.timeax_alignment import run_timeax_alignment

model_rna, results_rna = run_timeax_alignment(rnaseq_data, metadata)
model_prot, results_prot = run_timeax_alignment(proteomics_data, metadata)
model_metab, results_metab = run_timeax_alignment(metabolomics_data, metadata)

# Step 3: Consensus pseudotime
pseudotime_consensus = (results_rna['pseudotime'] +
                        results_prot['pseudotime'] +
                        results_metab['pseudotime']) / 3

# Step 4: Predict outcome using consensus
from scripts.clinical_validation import outcome_prediction

outcome_model = outcome_prediction(
    features=pd.concat([
        rnaseq_data.loc[results_rna['seed_features']],
        proteomics_data.loc[results_prot['seed_features']],
        metabolomics_data.loc[results_metab['seed_features']]
    ]),
    pseudotime=pseudotime_consensus,
    outcome=metadata['outcome']
)
```

---

## Best Practices for Integration

1. **Always validate data format** before passing between workflows
2. **Document normalization methods** used at each step
3. **Preserve sample IDs** consistently across all files
4. **Batch correction** should be done before trajectory analysis, not after
5. **Check correlation** between upstream features and trajectory results
6. **Use version control** to track which workflow versions were used

---

**Last Updated:** 2026-01-28


---
