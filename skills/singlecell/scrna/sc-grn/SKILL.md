---
name: sc-grn
description: >-
  Gene regulatory network inference using pySCENIC (GRNBoost2, cisTarget, AUCell)
version: 0.1.0
metadata:
  omicsclaw:
    domain: singlecell
    allowed_extra_flags:
      - "--db"
      - "--motif"
      - "--n-jobs"
      - "--n-top-targets"
      - "--seed"
      - "--tf-list"
    saves_h5ad: true
    requires_preprocessed: true
    trigger_keywords:
      - grn
      - gene regulatory
      - scenic
      - pyscenic
      - regulon
      - transcription factor
      - grnboost
---

# sc-grn — Gene Regulatory Network Inference

## Purpose

Infer gene regulatory networks from single-cell RNA-seq data using **pySCENIC**:

- **GRNBoost2** — co-expression network inference between TFs and target genes
- **cisTarget** — motif enrichment and pruning to identify direct targets
- **AUCell** — regulon activity scoring per cell

Identify master regulators and their target genes driving cell states.

## When to Use

- Identifying master regulators of cell types/states
- Understanding transcriptional programs
- Finding candidate TFs for perturbation experiments
- Linking TFs to phenotype

## Requirements

### Input Data
- AnnData with preprocessed gene expression
- Standard preprocessing (normalize, log1p, HVG)

### Python Dependencies
- `arboreto` — GRNBoost2 implementation
- `pyscenic` — cisTarget + AUCell

### External Databases (Required for Full Analysis)

| Database | Description | Source |
|----------|-------------|--------|
| TF list | List of TF gene symbols | [pySCENIC resources](https://github.com/aertslab/pySCENIC/tree/master/resources) |
| cisTarget DB | Motif-to-gene mappings | [cisTarget DBs](https://resources.aertslab.org/cistarget/) |
| Motif annotations | TF-to-motif mappings | [motif2TF](https://resources.aertslab.org/cistarget/motif2tf/) |

#### Example Database Files

```bash
# Download for human (hg38)
wget https://raw.githubusercontent.com/aertslab/pySCENIC/master/resources/hs_hgnc_tfs.txt
wget https://resources.aertslab.org/cistarget/databases/homo_sapiens/hg38/refseq_r80/mc9nr/gene_based/hg38__refseq_r80__mc9nr_gg6_500bp_upstream.feather
wget https://resources.aertslab.org/cistarget/motif2tf/motifs-v9-nr.hgnc-m0.001-o0.0.tbl
```

## Usage

### CLI

```bash
# Full workflow with all databases
python omicsclaw.py run sc-grn \
    --input preprocessed.h5ad \
    --output results/ \
    --tf-list hs_hgnc_tfs.txt \
    --db "hg38*.feather" \
    --motif motifs-v9-nr.hgnc-m0.001-o0.0.tbl

# Demo mode (GRNBoost2 only, no external DBs)
python omicsclaw.py run sc-grn --demo --output /tmp/grn_demo/
```

### Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--input` | required | Input AnnData file (.h5ad) |
| `--output` | required | Output directory |
| `--demo` | false | Run demo mode (GRNBoost2 only) |
| `--tf-list` | required | TF list file (one per line) |
| `--db` | required | Glob pattern for cisTarget databases |
| `--motif` | required | Motif annotations file |
| `--n-top-targets` | 50 | Max targets per regulon |
| `--n-jobs` | 4 | Parallel jobs |
| `--seed` | 42 | Random seed |

## Output Structure

```
output_dir/
├── adata_with_grn.h5ad           # AnnData with regulon activity scores
├── report.md                      # Analysis report
├── result.json                    # Machine-readable results
├── figures/
│   ├── regulon_activity_umap.png  # Top regulons on UMAP
│   ├── regulon_heatmap.png        # Regulon activity heatmap
│   └── regulon_network.png        # TF-target network diagram
├── tables/
│   ├── grn_adjacencies.csv        # All TF-target adjacencies
│   ├── grn_regulons.csv           # Regulon summary
│   ├── grn_regulon_targets.csv    # TF-target pairs
│   └── grn_auc_matrix.csv         # AUCell activity scores
└── reproducibility/
    ├── commands.sh
    └── requirements.txt
```

## Methods

### GRNBoost2 (Co-expression)

Gradient boosting-based method that learns feature importance between TF expression
and target gene expression across cells.

- **Input**: Expression matrix + TF list
- **Output**: TF-target adjacencies with importance scores
- **Limitation**: Co-expression ≠ direct regulation

### cisTarget (Motif Pruning)

Prunes co-expression network to direct targets using motif enrichment:
1. For each TF, get top co-expressed targets
2. Check if targets share enriched motifs
3. Keep only targets with the TF's motif in regulatory regions

- **Input**: Adjacencies + cisTarget DB + motif annotations
- **Output**: Pruned regulons with NES scores

### AUCell (Activity Scoring)

Calculates regulon activity per cell by computing area under the recovery curve
of gene expression rankings.

- **Input**: Expression matrix + regulons
- **Output**: AUC score matrix (cells × regulons)

## Interpretation

1. **Regulon activity UMAP**: Shows which TFs are active in which cell types
2. **Heatmap**: Cluster-level regulon activity patterns
3. **Network diagram**: TF-target relationships
4. **High NES**: Strong motif enrichment → likely direct targets

## Tips

- Use appropriate species-specific databases
- Filter low-quality cells first with `sc-qc` and `sc-filter`
- Combine with `sc-cell-annotation` to link regulons to cell types
- Run demo mode first to test installation

## Troubleshooting

| Issue | Solution |
|-------|----------|
| arboreto not installed | `pip install arboreto` |
| GRNBoost2 fails (dask error) | Auto-fallback to correlation-based GRN |
| Database files missing | Download from resources.aertslab.org |
| Slow GRNBoost2 | Reduce n_jobs if memory-limited |
| Too few regulons | Check TF list matches your species |

### Known Issue: dask/arboreto Compatibility

arboreto 0.1.6 (2020) may be incompatible with dask 2024.x due to API changes.
When GRNBoost2 fails, the skill automatically falls back to **correlation-based GRN inference** (Spearman correlation).

For full pySCENIC support with GRNBoost2, you may need:
```bash
pip install "dask==2021.11.2" "distributed==2021.11.2"
```
However, this may conflict with other packages like squidpy or spatialdata.

## References

- Aibar et al. (2017) SCENIC: Single-cell regulatory network inference and clustering
- Van de Sande et al. (2020) pySCENIC
- Moerman et al. (2019) GRNBoost2
