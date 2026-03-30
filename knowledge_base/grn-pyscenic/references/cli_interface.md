# pySCENIC Command Line Interface

pySCENIC can be run from the command line as an alternative to the Python API. This is useful for batch processing and integration with workflow managers.

## Installation

```bash
pip install pyscenic
```

## Three-Step Pipeline

### Step 1: GRN Inference (GRNBoost2)

Identify co-expression relationships between TFs and potential target genes.

```bash
pyscenic grn \
    expression_matrix.loom \
    allTFs_hg38.txt \
    -o adjacencies.csv \
    --num_workers 4 \
    --seed 777
```

**Parameters:**
- `expression_matrix.loom`: Expression matrix in loom format
- `allTFs_hg38.txt`: List of TF names (one per line)
- `-o`: Output file for adjacencies
- `--num_workers`: Number of parallel workers (default: 1)
- `--seed`: Random seed for reproducibility

**Output:** `adjacencies.csv` with TF-target importance scores

---

### Step 2: cisTarget (Regulon Prediction)

Prune targets using motif enrichment in cis-regulatory regions.

```bash
pyscenic ctx \
    adjacencies.csv \
    hg38_10kbp_up_10kbp_down_full_tx_v10_clust.genes_vs_motifs.rankings.feather \
    --annotations_fname motifs-v10nr_clust-nr.hgnc-m0.001-o0.0.tbl \
    --expression_mtx_fname expression_matrix.loom \
    --output regulons.csv \
    --num_workers 4
```

**Parameters:**
- `adjacencies.csv`: Input from Step 1
- Database file(s): Motif ranking databases (*.feather)
- `--annotations_fname`: Motif annotation file
- `--expression_mtx_fname`: Original expression matrix (optional but recommended)
- `--output`: Output regulons file
- `--num_workers`: Number of parallel workers

**Output:** `regulons.csv` with TF-target regulons after motif pruning

---

### Step 3: AUCell Scoring

Calculate cell-level regulon activity scores.

```bash
pyscenic aucell \
    expression_matrix.loom \
    regulons.csv \
    --output aucell_matrix.csv \
    --num_workers 4
```

**Parameters:**
- `expression_matrix.loom`: Original expression matrix
- `regulons.csv`: Regulons from Step 2
- `--output`: Output AUCell scores matrix
- `--num_workers`: Number of parallel workers

**Output:** `aucell_matrix.csv` with cell x regulon activity matrix

---

## Complete Pipeline Example

```bash
# Set parameters
EXPR="expression_matrix.loom"
TFS="allTFs_hg38.txt"
DB="hg38_10kbp_up_10kbp_down_full_tx_v10_clust.genes_vs_motifs.rankings.feather"
MOTIFS="motifs-v10nr_clust-nr.hgnc-m0.001-o0.0.tbl"
WORKERS=4

# Step 1: GRN inference
pyscenic grn \
    $EXPR \
    $TFS \
    -o adjacencies.csv \
    --num_workers $WORKERS

# Step 2: Regulon prediction
pyscenic ctx \
    adjacencies.csv \
    $DB \
    --annotations_fname $MOTIFS \
    --expression_mtx_fname $EXPR \
    --output regulons.csv \
    --num_workers $WORKERS

# Step 3: AUCell scoring
pyscenic aucell \
    $EXPR \
    regulons.csv \
    --output aucell_matrix.csv \
    --num_workers $WORKERS
```

---

## Converting Data Formats

### CSV to Loom

```python
import loompy as lp
import pandas as pd

# Read CSV (genes x cells)
df = pd.read_csv("expression_matrix.csv", index_col=0)

# Create loom file
lp.create("expression_matrix.loom", df.values,
          row_attrs={"Gene": df.index.tolist()},
          col_attrs={"CellID": df.columns.tolist()})
```

### Loom to CSV

```python
import loompy as lp
import pandas as pd

# Read loom
with lp.connect("expression_matrix.loom") as ds:
    df = pd.DataFrame(ds[:, :],
                     index=ds.ra.Gene,
                     columns=ds.ca.CellID)

# Save as CSV
df.to_csv("expression_matrix.csv")
```

---

## Performance Considerations

### Memory Usage
- GRNBoost2: ~2-4GB per 10k cells
- cisTarget: ~8-16GB (depends on database size)
- AUCell: ~1-2GB per 10k cells

### Runtime Estimates
- GRNBoost2: 10-60 minutes (depends on number of genes and cells)
- cisTarget: 30-120 minutes (depends on number of modules)
- AUCell: 5-20 minutes

### Optimization Tips
1. **Filter genes**: Keep only top 2,000-5,000 variable genes
2. **Subsample cells**: Use 5,000-10,000 cells for very large datasets
3. **Increase workers**: Use 4-8 workers for parallel processing
4. **Use SSD**: Store databases on fast storage

---

## Troubleshooting

### Issue: "Database not found"
**Solution:** Check that the `.feather` database path is correct and files are not corrupted.

### Issue: "Out of memory"
**Solution:**
- Subsample cells or genes
- Reduce number of workers
- Use machine with more RAM

### Issue: "No regulons found"
**Solution:**
- Check TF list matches gene names in your data
- Lower pruning thresholds in cisTarget
- Ensure expression data has sufficient cells (500+ recommended)

### Issue: "Slow GRNBoost2"
**Solution:**
- Reduce number of genes (filter to top variable genes)
- Increase number of workers
- Use smaller TF list

---

## References

- pySCENIC Documentation: https://pyscenic.readthedocs.io/
- pySCENIC GitHub: https://github.com/aertslab/pySCENIC
- SCENIC Protocol: Van de Sande et al. (2020). Nature Protocols. doi:10.1038/s41596-020-0336-2
