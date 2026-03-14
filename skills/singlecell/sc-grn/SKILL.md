---
name: sc-grn
description: >-
  Gene regulatory network inference using pySCENIC three-step pipeline
  (GRNBoost2 → cisTarget → AUCell), with correlation-based fallback.
  Identifies transcription factor regulons and scores their activity per cell.
version: 0.1.0
author: OmicsClaw
license: MIT
tags: [singlecell, GRN, SCENIC, regulon, transcription-factor]
metadata:
  omicsclaw:
    domain: singlecell
    requires:
      bins:
        - python3
      env: []
      config: []
    emoji: "🕸️"
    homepage: https://github.com/OmicsClaw/OmicsClaw
    os: [macos, linux]
    install:
      - kind: pip
        package: scanpy
        bins: []
    trigger_keywords:
      - gene regulatory network
      - GRN
      - SCENIC
      - regulon
      - transcription factor
      - CellOracle
---

# 🕸️ Single-Cell Gene Regulatory Network Inference

You are **SC GRN**, a specialised OmicsClaw agent for inferring gene regulatory networks from single-cell expression data.

## Why This Exists

- **Without it**: GRN inference requires running multiple tools (GRNBoost2, RcisTarget, AUCell) and stitching outputs together
- **With it**: Unified GRN pipeline with automatic method selection
- **Why OmicsClaw**: Standardised TF→target network for downstream regulon analysis

## Core Capabilities

1. **pySCENIC / GRNBoost2**: Gradient boosting for TF-target co-expression inference
2. **cisTarget pruning**: Filter by cis-regulatory motif enrichment near target gene promoters
3. **AUCell scoring**: Score regulon activity per cell using area under the recovery curve
4. **Correlation fallback**: Pearson correlation-based TF-target scoring when SCENIC is not available
5. **Network output**: CSV adjacency list (TF, target, importance) + regulon activity matrix

## Pipeline Overview

| Step | Tool | Description |
|------|------|-------------|
| 1. GRN inference | GRNBoost2 | Co-expression modules between TFs and targets |
| 2. Regulon pruning | cisTarget | Filter by cis-regulatory motif enrichment |
| 3. Activity scoring | AUCell | Score regulon activity per cell |

## Workflow

1. **Score**: Run boosting matrices for target coexpression logic.
2. **Prune**: Motif filtering from compiled cis-regulatory structures.
3. **Threshold**: Score regulon values per single-cell identity.
4. **Visualise**: Render heatmap and dimensionality profiles.
5. **Report**: Tabulate key defining transcriptional factors.

## CLI Reference

```bash
python skills/singlecell/grn/sc_grn.py \
  --input <processed.h5ad> --output <dir>
python omicsclaw.py run sc-grn --demo
```

## Algorithm / Methodology

### Step 1: GRN Inference with GRNBoost2

#### Using arboreto_with_multiprocessing.py (Recommended)

Native Arboreto is broken with dask >= 2.0. Use the bundled multiprocessing script:

```bash
python arboreto_with_multiprocessing.py \
    filtered.loom \
    allTFs_hg38.txt \
    --method grnboost2 \
    --output adj.tsv \
    --num_workers 8 \
    --seed 42
```

#### Python API (if dask < 2.0)

```python
from arboreto.algo import grnboost2
import pandas as pd

adjacencies = grnboost2(expr_matrix, tf_names=tf_names, verbose=True)
adjacencies.to_csv('adj.tsv', sep='\t', index=False)
```

### Step 2: Regulon Pruning with cisTarget

**Goal:** Filter raw co-expression modules to retain only TF-target links supported by cis-regulatory motif enrichment near target gene promoters.

```python
from pyscenic.prune import prune2df, df2regulons
from ctxcore.rnkdb import FeatherRankingDatabase
import glob
import pickle

# Load ranking databases
db_fnames = glob.glob('*.genes_vs_motifs.rankings.feather')
dbs = [FeatherRankingDatabase(fname) for fname in db_fnames]

# Load motif annotations
motif_annotations_fname = 'motifs-v9-nr.hgnc-m0.001-o0.0.tbl'

adjacencies = pd.read_csv('adj.tsv', sep='\t')

# Prune: only keep TF-target links supported by cis-regulatory motifs
df = prune2df(dbs, adjacencies, motif_annotations_fname)

regulons = df2regulons(df)

with open('regulons.pkl', 'wb') as f:
    pickle.dump(regulons, f)

print(f'Found {len(regulons)} regulons')
for reg in sorted(regulons, key=lambda r: -len(r))[:10]:
    print(f'  {reg.name}: {len(reg)} targets')
```

### Step 3: AUCell Activity Scoring

**Goal:** Score the activity of each regulon in every individual cell.

```python
from pyscenic.aucell import aucell
import loompy

ds = loompy.connect('filtered.loom')
expr_matrix = pd.DataFrame(ds[:, :], index=ds.ra.Gene, columns=ds.ca.CellID).T
ds.close()

with open('regulons.pkl', 'rb') as f:
    regulons = pickle.load(f)

# Score regulon activity per cell
auc_mtx = aucell(expr_matrix, regulons, auc_threshold=0.05, num_workers=8)

auc_mtx.to_csv('auc_matrix.csv')
print(f'Scored {auc_mtx.shape[1]} regulons across {auc_mtx.shape[0]} cells')
```

### CLI Alternative (All 3 Steps)

```bash
# Step 1: GRN inference
pyscenic grn filtered.loom allTFs_hg38.txt -o adj.tsv --num_workers 8

# Step 2: cisTarget pruning
pyscenic ctx adj.tsv \
    hg38__refseq-r80__10kb_up_and_down_tss.mc9nr.genes_vs_motifs.rankings.feather \
    --annotations_fname motifs-v9-nr.hgnc-m0.001-o0.0.tbl \
    --expression_mtx_fname filtered.loom \
    --output reg.csv \
    --num_workers 8

# Step 3: AUCell scoring
pyscenic aucell filtered.loom reg.csv \
    --output scenic_output.loom \
    --num_workers 8
```

### Interpreting Results

#### Regulon Specificity Score (RSS)

```python
from pyscenic.rss import regulon_specificity_scores

# RSS identifies regulons enriched in specific cell types
cell_types = pd.read_csv('cell_types.csv', index_col=0)['cell_type']
rss = regulon_specificity_scores(auc_mtx, cell_types)

# Top regulons per cell type
for ct in rss.columns:
    top_regs = rss[ct].sort_values(ascending=False).head(5)
    print(f'\n{ct}:')
    for reg, score in top_regs.items():
        print(f'  {reg}: {score:.3f}')
```

#### Binary Regulon Activity

```python
from pyscenic.binarization import binarize

# Binarize AUC scores (on/off per cell)
binary_mtx, thresholds = binarize(auc_mtx)

# Fraction of cells with active regulon per cluster
cluster_activity = binary_mtx.groupby(cell_types).mean()
```

### Visualization

```python
import scanpy as sc
import seaborn as sns
import matplotlib.pyplot as plt

adata = sc.read_h5ad('clustered.h5ad')
adata.obsm['X_aucell'] = auc_mtx.loc[adata.obs_names].values

# Regulon activity on UMAP
sc.pl.umap(adata, color=['CEBPB(+)', 'SPI1(+)', 'PAX5(+)'], cmap='viridis')

# Heatmap of top regulons per cell type
top_regulons = rss.apply(lambda x: x.nlargest(3).index.tolist()).explode().unique()
sns.clustermap(auc_mtx[top_regulons].groupby(cell_types).mean().T,
               cmap='viridis', figsize=(10, 8), z_score=0)
plt.savefig('regulon_heatmap.pdf', bbox_inches='tight')
```

## Required Databases

Download cisTarget ranking databases and motif annotations:

```bash
# Human hg38 ranking databases (~1.5 GB each)
wget https://resources.aertslab.org/cistarget/databases/homo_sapiens/hg38/refseq_r80/mc9nr/gene_based/hg38__refseq-r80__10kb_up_and_down_tss.mc9nr.genes_vs_motifs.rankings.feather

# Motif-to-TF annotations
wget https://resources.aertslab.org/cistarget/motif2tf/motifs-v9-nr.hgnc-m0.001-o0.0.tbl
```

## Performance Tips

| Tip | Details |
|-----|---------|
| Subsample for GRN | Use 5000-10000 cells for Step 1; regulons transfer to full dataset |
| Use CLI for Step 1 | `arboreto_with_multiprocessing.py` avoids dask issues |
| Parallelize | All three steps accept `--num_workers` |
| Prefilter genes | Remove genes expressed in < 3 cells or < 1% of cells |
| Loom format | Standard input format; convert from h5ad with `loompy` |

## Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--method` | `auto` | auto, grnboost2, or correlation |
| `--n-top-targets` | `50` | Top targets per TF |
| `--n-workers` | `4` | Parallel workers for SCENIC steps |
| `--auc-threshold` | `0.05` | AUCell threshold (top fraction of ranked genes) |

## Example Queries

- "Construct a gene regulatory network on my data using pySCENIC"
- "Infer the GRN regulons for these identified clusters"

## Output Structure

```
output_dir/
├── report.md
├── result.json
├── processed.h5ad
├── figures/
│   └── summary_plot.png
├── tables/
│   └── metrics.csv
└── reproducibility/
    ├── commands.sh
    ├── environment.yml
    └── checksums.sha256
```

## Version Compatibility

Reference examples tested with: pySCENIC 0.12+, scanpy 1.10+, numpy 1.26+

## Dependencies

**Required**: scanpy, numpy, pandas
**Optional**: pyscenic, arboreto, ctxcore, loompy

## Citations

- [SCENIC](https://doi.org/10.1038/nmeth.4463) — Aibar et al., Nature Methods 2017
- [GRNBoost2](https://doi.org/10.1093/bioinformatics/bty916) — Moerman et al., Bioinformatics 2019
- [cisTarget](https://doi.org/10.1093/nar/gkp983) — Verfaillie et al., Nucleic Acids Research 2015
- [AUCell](https://doi.org/10.1038/nmeth.4463) — scoring from SCENIC pipeline
- [CellOracle](https://doi.org/10.1038/s41586-022-05688-9) — Kamimoto et al., Nature 2023

## Safety

- **Local-first**: Strict offline processing without external upload.
- **Disclaimer**: Requires OmicsClaw reporting structures and disclaimers.
- **Audit trail**: Hyperparameters and operational flow states are logged fully.

## Integration with Orchestrator

**Trigger conditions**:
- Automatically invoked dynamically based on tool metadata and user intent matching.

**Chaining partners**:
- `sc-preprocess` — QC and normalization before regulon analysis
- `sc-communication` — Downstream signaling from GRN regulons
- `sc-de` — Differential expression of regulon targets
