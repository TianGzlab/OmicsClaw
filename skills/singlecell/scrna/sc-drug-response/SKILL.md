---
name: sc-drug-response
description: Drug response prediction from scRNA-seq (CaDRReS-Sc, simple correlation)
version: 0.1.0
metadata:
  omicsclaw:
    domain: singlecell
    script: sc_drug_response.py
    allowed_extra_flags:
    - --cluster-key
    - --drug-db
    - --method
    - --model-dir
    - --n-drugs
    - --r-enhanced
    param_hints: {}
    saves_h5ad: false
    requires_preprocessed: true
---

# sc-drug-response

**Single-cell drug response prediction** — predict drug sensitivity from single-cell transcriptomes using pharmacogenomic models or gene expression correlation with known drug targets.

## Data / State Requirements

| Requirement | Details |
|---|---|
| **Input** | Preprocessed AnnData (`.h5ad`) with normalized expression in `X` |
| **Matrix** | Normalized expression (log1p-transformed) |
| **Layers** | `layers["counts"]` recommended for CaDRReS |
| **Metadata** | Cluster labels in `.obs` (leiden, louvain, or custom) |
| **Gene names** | HGNC symbols required (e.g., BRCA1, EGFR). Ensembl IDs will fail — run `sc-standardize-input` or `bulkrna-geneid-mapping` first |
| **Upstream** | `sc-preprocessing` must be completed first |
| **Reference** | `cadrres` method requires pretrained model files (see Reference Data Guide) |

## Method Selection Table

| Scenario | Recommended Method | Example |
|---|---|---|
| Quick exploration, no external data | `simple_correlation` | `--method simple_correlation` |
| Publication-quality predictions with GDSC | `cadrres` | `--method cadrres --drug-db gdsc --model-dir ~/.cache/omicsclaw/drug_response/` |
| PRISM drug library | `cadrres` | `--method cadrres --drug-db prism --model-dir ~/.cache/omicsclaw/drug_response/` |
| Mouse data | `simple_correlation` | `--method simple_correlation` (auto-detects species) |

### Method Details

#### `simple_correlation` (default, no external data needed)

Scores drug sensitivity per cluster by computing mean expression of known drug target genes. Built-in target gene sets cover 15 common drugs (Cisplatin, Paclitaxel, Doxorubicin, etc.). Higher score = higher predicted sensitivity.

**Pros**: No model download required, fast, interpretable.
**Cons**: Simplified scoring, limited to built-in drug-target mappings.

#### `cadrres` (CaDRReS-Sc)

Uses CaDRReS-Sc pretrained pharmacogenomic models to predict IC50 (GDSC) or AUC (PRISM) from single-cell cluster expression profiles. Provides cell death proportion estimates for GDSC.

**Pros**: Model-based, covers hundreds of drugs, validated on GDSC/PRISM.
**Cons**: Requires model download (~500MB), currently human-only.

## Parameters

| Parameter | Default | Description |
|---|---|---|
| `--method` | `simple_correlation` | `cadrres` or `simple_correlation` |
| `--model-dir` | `~/.cache/omicsclaw/drug_response/` | CaDRReS model directory (cadrres only) |
| `--drug-db` | `gdsc` | Drug database: `gdsc` or `prism` |
| `--n-drugs` | `10` | Number of top drugs to report/visualize |
| `--cluster-key` | auto-detect | `.obs` column with cluster labels |
| `--demo` | off | Run with synthetic data |

## Workflow

1. **Load** — Read preprocessed `.h5ad` or generate demo data
2. **Preflight** — Validate cluster key exists, check model files (cadrres), detect species
3. **Run method** — Compute drug sensitivity scores per cluster
4. **Detect degenerate output** — Check for empty results, report actionable guidance
5. **Store results** — Drug scores in `adata.obs` columns (`drug_score_<DrugName>`)
6. **Render gallery** — UMAP overlay, bar chart, heatmap
7. **Export** — `processed.h5ad`, `tables/drug_rankings.csv`, `report.md`, `result.json`

## Output Contract

| Output | Location | Description |
|---|---|---|
| `processed.h5ad` | `<output>/` | AnnData with drug scores in `.obs` |
| `drug_rankings.csv` | `<output>/tables/` | Full drug ranking (Drug, Cluster, Score, Rank) |
| `drug_sensitivity_umap.png` | `<output>/figures/` | Top drug sensitivity overlaid on UMAP |
| `top_drugs_bar.png` | `<output>/figures/` | Bar chart of top N drugs |
| `drug_cluster_heatmap.png` | `<output>/figures/` | Drug sensitivity heatmap across clusters |
| `report.md` | `<output>/` | Analysis report |
| `result.json` | `<output>/` | Machine-readable results with diagnostics |

### AnnData output schema

```
adata.obs["drug_score_Cisplatin"]   # float, sensitivity score for Cisplatin
adata.obs["drug_score_Paclitaxel"]  # float, sensitivity score for Paclitaxel
# ... one column per scored drug
adata.uns["omicsclaw_input_contract"]
adata.uns["omicsclaw_matrix_contract"]
```

## Reference Data Guide

### CaDRReS-Sc Model Files (cadrres method only)

The `simple_correlation` method requires NO external data.

For `cadrres`, you need:

| File | Source | Size |
|---|---|---|
| `cadrres-wo-sample-bias_param_dict_all_genes.pickle` | CaDRReS-Sc release | ~200MB |
| `cadrres-wo-sample-bias_param_dict_prism.pickle` | CaDRReS-Sc release | ~200MB |
| `masked_drugs.csv` | CaDRReS-Sc release | <1MB |
| `GDSC_exp.tsv.gz` | CaDRReS-Sc release | ~100MB |

#### Download instructions

```bash
# 1. Create cache directory
mkdir -p ~/.cache/omicsclaw/drug_response/

# 2. Clone CaDRReS-Sc (for scripts + preprocessed data)
git clone https://github.com/CSB5/CaDRReS-Sc.git

# 3. Download pretrained models
wget https://github.com/CSB5/CaDRReS-Sc/releases/download/v1.0/CaDRReS-Sc-model.tar.gz
tar -xzf CaDRReS-Sc-model.tar.gz -C ~/.cache/omicsclaw/drug_response/

# 4. Download GDSC expression (for kernel features)
wget https://github.com/CSB5/CaDRReS-Sc/releases/download/v1.0/GDSC_exp.tsv.gz
mv GDSC_exp.tsv.gz ~/.cache/omicsclaw/drug_response/
```

#### Choosing GDSC vs PRISM

- **GDSC**: 265 drugs, IC50-based, broader coverage of cancer drugs
- **PRISM**: 1,448 compounds, AUC-based, includes non-oncology compounds

## Next Steps

After drug response prediction:

| Goal | Skill | Command |
|---|---|---|
| Identify markers for sensitive clusters | `sc-markers` | `python omicsclaw.py run sc-markers --input processed.h5ad --output markers/` |
| Pathway analysis of sensitive clusters | `sc-enrichment` | `python omicsclaw.py run sc-enrichment --input processed.h5ad --output enrichment/` |
| DE between sensitive vs resistant clusters | `sc-de` | `python omicsclaw.py run sc-de --input processed.h5ad --output de/` |
| Cell-cell communication in tumor | `sc-cell-communication` | `python omicsclaw.py run sc-cell-communication --input processed.h5ad --output comm/` |

## Example Commands

```bash
# Demo mode (no data needed)
python omicsclaw.py run sc-drug-response --demo --output /tmp/drug_demo

# Simple correlation (no model needed)
python omicsclaw.py run sc-drug-response \
  --input preprocessed.h5ad --output results/ \
  --method simple_correlation --n-drugs 15

# CaDRReS with GDSC
python omicsclaw.py run sc-drug-response \
  --input preprocessed.h5ad --output results/ \
  --method cadrres --drug-db gdsc \
  --model-dir ~/.cache/omicsclaw/drug_response/

# Custom cluster key
python omicsclaw.py run sc-drug-response \
  --input preprocessed.h5ad --output results/ \
  --method simple_correlation --cluster-key cell_type
```

## CLI Parameters

| Flag | Type | Default | Description | Validation |
|------|------|---------|-------------|------------|
| `--input` | str | — | Input `.h5ad` file | required unless `--demo` |
| `--output` | str | — | Output directory | required |
| `--demo` | flag | off | Run with synthetic demo data | — |
| `--method` | str | `simple_correlation` | Prediction method: `simple_correlation`, `cadrres` | validated against METHOD_REGISTRY |
| `--model-dir` | path | `~/.cache/omicsclaw/drug_response/` | Directory containing CaDRReS model files | cadrres only |
| `--drug-db` | str | `gdsc` | Drug database: `gdsc` or `prism` | choices: gdsc, prism |
| `--n-drugs` | int | 10 | Number of top drugs to report/visualize | — |
| `--cluster-key` | str | None | `.obs` column with cluster labels; auto-detected when omitted | — |
| `--r-enhanced` | flag | off | Accepted for CLI consistency; no R Enhanced plots available | no-op |

## Methods

| Method | Description | Required packages | Fallback |
|--------|-------------|-------------------|---------|
| `simple_correlation` | Mean expression of known drug-target genes per cluster. Covers 15 built-in drugs (Cisplatin, Paclitaxel, Doxorubicin, etc.). No model download needed. Fast and interpretable. | scanpy, numpy, pandas | None (always available) |
| `cadrres` | CaDRReS-Sc pretrained pharmacogenomic model predicting IC50 (GDSC) or AUC (PRISM) from cluster expression profiles. Requires ~500 MB model download. Human-only. | scanpy, numpy, pandas + pretrained model files | Falls back to `simple_correlation` with a warning if model files are missing |

## Workflow Position

**Upstream:** sc-clustering or sc-cell-annotation
**Downstream:** Terminal analysis.
