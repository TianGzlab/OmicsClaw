# pySCENIC Database Downloads

This guide provides download links and instructions for cisTarget databases required for pySCENIC regulon prediction.

## Overview

pySCENIC requires two types of database files:

1. **Motif ranking databases** (`.feather` files): Precomputed rankings of genes by motif enrichment
2. **Motif annotation files** (`.tbl` files): Mapping of motifs to transcription factors

---

## Human (hg38)

### Recommended Database (10kb upstream + downstream)

**Motif rankings database:**
```bash
wget https://resources.aertslab.org/cistarget/databases/homo_sapiens/hg38/refseq_r80/mc_v10_clust/gene_based/hg38_10kbp_up_10kbp_down_full_tx_v10_clust.genes_vs_motifs.rankings.feather
```

**Motif annotations:**
```bash
wget https://resources.aertslab.org/cistarget/motif2tf/motifs-v10nr_clust-nr.hgnc-m0.001-o0.0.tbl
```

**File sizes:**
- Ranking database: ~1.1 GB
- Motif annotations: ~15 MB

### Alternative Human Databases

**500bp upstream only:**
```bash
wget https://resources.aertslab.org/cistarget/databases/homo_sapiens/hg38/refseq_r80/mc_v10_clust/gene_based/hg38_500bp_up_100bp_down_full_tx_v10_clust.genes_vs_motifs.rankings.feather
```

---

## Mouse (mm10)

### Recommended Database (10kb upstream + downstream)

**Motif rankings database:**
```bash
wget https://resources.aertslab.org/cistarget/databases/mus_musculus/mm10/refseq_r80/mc_v10_clust/gene_based/mm10_10kbp_up_10kbp_down_full_tx_v10_clust.genes_vs_motifs.rankings.feather
```

**Motif annotations:**
```bash
wget https://resources.aertslab.org/cistarget/motif2tf/motifs-v10nr_clust-nr.mgi-m0.001-o0.0.tbl
```

**File sizes:**
- Ranking database: ~900 MB
- Motif annotations: ~15 MB

### Alternative Mouse Databases

**500bp upstream only:**
```bash
wget https://resources.aertslab.org/cistarget/databases/mus_musculus/mm10/refseq_r80/mc_v10_clust/gene_based/mm10_500bp_up_100bp_down_full_tx_v10_clust.genes_vs_motifs.rankings.feather
```

---

## Mouse (mm39/GRCm39)

### Recommended Database

**Motif rankings database:**
```bash
wget https://resources.aertslab.org/cistarget/databases/mus_musculus/mm39/refseq_r108/mc_v10_clust/gene_based/mm39_10kbp_up_10kbp_down_full_tx_v10_clust.genes_vs_motifs.rankings.feather
```

**Motif annotations:**
```bash
wget https://resources.aertslab.org/cistarget/motif2tf/motifs-v10nr_clust-nr.mgi-m0.001-o0.0.tbl
```

---

## Drosophila melanogaster (dm6)

**Motif rankings database:**
```bash
wget https://resources.aertslab.org/cistarget/databases/drosophila_melanogaster/dm6/flybase_r6.02/mc_v10_clust/gene_based/dm6_10kbp_up_10kbp_down_full_tx_v10_clust.genes_vs_motifs.rankings.feather
```

**Motif annotations:**
```bash
wget https://resources.aertslab.org/cistarget/motif2tf/motifs-v10nr_clust-nr.flybase-m0.001-o0.0.tbl
```

---

## Transcription Factor Lists

### Human TFs

**All TFs (HGNC symbols):**
```bash
wget https://resources.aertslab.org/cistarget/tf_lists/allTFs_hg38.txt
```

### Mouse TFs

**All TFs (MGI symbols):**
```bash
wget https://resources.aertslab.org/cistarget/tf_lists/allTFs_mm.txt
```

---

## Database Selection Guide

### Which window size to use?

| Database Type | Use Case | Pros | Cons |
|--------------|----------|------|------|
| **10kb up/down** | Default choice | More comprehensive, better for distal enhancers | Larger file, more noise |
| **500bp up/100bp down** | Focused on promoters | Faster, more specific | Misses distal regulation |

**Recommendation:** Start with 10kb up/down for most analyses.

---

## Download Script

### Complete Human Setup

```bash
#!/bin/bash

# Create databases directory
mkdir -p pyscenic_databases
cd pyscenic_databases

# Download human databases
echo "Downloading human (hg38) databases..."
wget https://resources.aertslab.org/cistarget/databases/homo_sapiens/hg38/refseq_r80/mc_v10_clust/gene_based/hg38_10kbp_up_10kbp_down_full_tx_v10_clust.genes_vs_motifs.rankings.feather

wget https://resources.aertslab.org/cistarget/motif2tf/motifs-v10nr_clust-nr.hgnc-m0.001-o0.0.tbl

wget https://resources.aertslab.org/cistarget/tf_lists/allTFs_hg38.txt

echo "Download complete!"
ls -lh
```

### Complete Mouse Setup

```bash
#!/bin/bash

# Create databases directory
mkdir -p pyscenic_databases
cd pyscenic_databases

# Download mouse databases
echo "Downloading mouse (mm10) databases..."
wget https://resources.aertslab.org/cistarget/databases/mus_musculus/mm10/refseq_r80/mc_v10_clust/gene_based/mm10_10kbp_up_10kbp_down_full_tx_v10_clust.genes_vs_motifs.rankings.feather

wget https://resources.aertslab.org/cistarget/motif2tf/motifs-v10nr_clust-nr.mgi-m0.001-o0.0.tbl

wget https://resources.aertslab.org/cistarget/tf_lists/allTFs_mm.txt

echo "Download complete!"
ls -lh
```

---

## Storage Requirements

### Disk Space

| Species | Total Size | Databases | TF List |
|---------|-----------|-----------|---------|
| Human (hg38) | ~1.2 GB | 1.1 GB | 40 KB |
| Mouse (mm10) | ~950 MB | 900 MB | 35 KB |
| Drosophila (dm6) | ~400 MB | 380 MB | 20 KB |

### Storage Location Tips

1. **Fast storage:** Use SSD for better I/O performance
2. **Shared location:** Store in a central location for multiple projects
3. **Backup:** Keep copies on network storage

---

## Verifying Downloads

After downloading, verify file integrity:

```bash
# Check file exists and has reasonable size
ls -lh *.feather
ls -lh *.tbl

# Quick Python check
python -c "import pandas as pd; df = pd.read_feather('hg38_10kbp_up_10kbp_down_full_tx_v10_clust.genes_vs_motifs.rankings.feather'); print(f'Database shape: {df.shape}')"
```

Expected output for human database: `Database shape: (~20000, ~20000)` (genes x motifs)

---

## Database Updates

The SCENIC team periodically releases updated databases with:
- New motif collections
- Improved genome annotations
- Additional species support

Check for updates at: https://resources.aertslab.org/cistarget/

---

## References

- **cisTarget resources:** https://resources.aertslab.org/cistarget/
- **SCENIC protocol:** Van de Sande et al. (2020). Nature Protocols. doi:10.1038/s41596-020-0336-2
- **motif2TF:** Aibar et al. (2017). Nature Methods. doi:10.1038/nmeth.4463


---
