# OmicsClaw Methods Guide

This guide lists every supported algorithm for each skill, with ready-to-run
command examples. All commands assume you have already activated the `.venv`
and are running from the project root.

---

## 1. Preprocessing (`preprocess`)

Single fixed pipeline — no `--method` selection needed.

```bash
python omicsclaw.py run preprocess \
  --input examples/card_spatial.h5ad \
  --output output/spatial_preprocess
```

Key parameters:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--data-type` | `generic` | Data platform (`generic`, `visium`, `xenium`, `merfish`, `slideseq`) |
| `--species` | `human` | Species for mitochondrial gene detection (`human` / `mouse`) |
| `--min-genes` | `200` | Minimum genes per cell |
| `--min-cells` | `3` | Minimum cells per gene |
| `--max-mt-pct` | `20.0` | Maximum mitochondrial gene percentage |
| `--n-top-hvg` | `2000` | Number of highly variable genes |
| `--n-pcs` | `50` | Number of PCA components |
| `--n-neighbors` | `15` | Neighbors for graph construction |
| `--leiden-resolution` | `1.0` | Leiden clustering resolution |

---

## 2. Spatial Domains (`domains`)

Identifies tissue regions and niches.

| Method | Description | Extra Parameters |
|--------|-------------|-----------------|
| `leiden` **(default)** | Graph-based clustering with spatial weight | `--resolution`, `--spatial-weight`, `--refine` |
| `louvain` | Louvain community detection | `--resolution`, `--refine` |
| `spagcn` | Graph convolutional network (requires `SpaGCN`) | `--n-domains`, `--refine` |
| `stagate` | Attention-based spatial domain identification (requires `STAGATE_pyG` from GitHub + `torch_geometric`) | `--n-domains`, `--rad-cutoff`, `--refine` |
| `graphst` | Graph self-supervised learning (requires `GraphST`) | `--n-domains`, `--refine` |
| `banksy` | Neighbourhood-augmented clustering (requires `pybanksy`, see note below) | `--resolution`, `--lambda-param`, `--refine` |

```bash
# leiden (default)
python omicsclaw.py run domains \
  --input output/spatial_preprocess/processed.h5ad --output output/spatial_domains \
  --method leiden --resolution 0.8

# louvain
python omicsclaw.py run domains \
  --input output/spatial_preprocess/processed.h5ad --output output/spatial_domains \
  --method louvain --resolution 1.0

# spagcn — specify target domain count
python omicsclaw.py run domains \
  --input output/spatial_preprocess/processed.h5ad --output output/spatial_domains \
  --method spagcn --n-domains 7

# stagate — adjust radius cutoff for spatial network
python omicsclaw.py run domains \
  --input output/spatial_preprocess/processed.h5ad --output output/spatial_domains \
  --method stagate --n-domains 7 --rad-cutoff 50.0

# graphst
python omicsclaw.py run domains \
  --input output/spatial_preprocess/processed.h5ad --output output/spatial_domains \
  --method graphst --n-domains 7

# banksy — tune spatial regularization with --lambda-param
# NOTE: pybanksy requires numpy<2.0, which conflicts with the full tier.
# Use a dedicated environment: pip install -e ".[banksy]"
python omicsclaw.py run domains \
  --input output/spatial_preprocess/processed.h5ad --output output/spatial_domains \
  --method banksy --resolution 0.8 --lambda-param 0.2

# add --refine to any method for spatial KNN post-processing
python omicsclaw.py run domains \
  --input output/spatial_preprocess/processed.h5ad --output output/spatial_domains \
  --method leiden --refine
```

---

## 3. Cell Type Annotation (`annotate`)

| Method | Description | Extra Parameters |
|--------|-------------|-----------------|
| `marker_based` **(default)** | Marker gene scoring against built-in database | `--cluster-key`, `--species` |
| `tangram` | Deep learning mapping to reference (requires `tangram-sc`) | `--reference`, `--cell-type-key` |
| `scanvi` | Semi-supervised VAE (requires `scvi-tools`) | `--reference`, `--cell-type-key` |
| `cellassign` | Probabilistic marker-based assignment (requires `scvi-tools`) | `--model`, `--cell-type-key` |

```bash
# marker_based (no reference needed)
python omicsclaw.py run annotate \
  --input output/preprocess/processed.h5ad --output output/annotate \
  --method marker_based --species human

# tangram — requires a reference scRNA-seq h5ad
python omicsclaw.py run annotate \
  --input output/preprocess/processed.h5ad --output output/annotate \
  --method tangram --reference ref.h5ad --cell-type-key cell_type

# scanvi
python omicsclaw.py run annotate \
  --input output/preprocess/processed.h5ad --output output/annotate \
  --method scanvi --reference ref.h5ad --cell-type-key cell_type

# cellassign
python omicsclaw.py run annotate \
  --input output/preprocess/processed.h5ad --output output/annotate \
  --method cellassign --cell-type-key cell_type
```

---

## 4. Deconvolution (`deconv`)

Estimates cell type proportions per spot. All methods require a single-cell
reference `--reference` annotated with `--cell-type-key`.

| Method | Description | Backend | GPU |
|--------|-------------|---------|-----|
| `flashdeconv` **(default)** | Ultra-fast O(N) sketching deconvolution | Python (`flashdeconv`) | No |
| `cell2location` | Bayesian hierarchical deconvolution | Python (`cell2location`) | Optional |
| `rctd` | Robust Cell Type Decomposition | R (`spacexr`) via `rpy2` | No |
| `destvi` | Multi-resolution VAE deconvolution | Python (`scvi-tools DestVI`) | Optional |
| `stereoscope` | Two-stage probabilistic deconvolution | Python (`scvi-tools Stereoscope`) | Optional |
| `tangram` | Deep learning cell-to-spot mapping | Python (`tangram-sc`) | Optional |
| `spotlight` | NMF-based deconvolution | R (`SPOTlight`) via `rpy2` | No |
| `card` | Conditional autoregressive deconvolution | R (`CARD`) via `rpy2` | No |

```bash
# FlashDeconv (default — fastest, CPU only, no GPU needed)
python omicsclaw.py run deconv \
  --input output/preprocess/processed.h5ad --output output/deconv \
  --method flashdeconv --reference ref.h5ad --cell-type-key cell_type

# cell2location
python omicsclaw.py run deconv \
  --input output/preprocess/processed.h5ad --output output/deconv \
  --method cell2location --reference ref.h5ad --cell-type-key cell_type

# RCTD  (requires R + spacexr; see prerequisites below)
python omicsclaw.py run deconv \
  --input output/preprocess/processed.h5ad --output output/deconv \
  --method rctd --reference ref.h5ad --cell-type-key cell_type \
  --rctd-mode full          # full | doublet | single

# DestVI
python omicsclaw.py run deconv \
  --input output/preprocess/processed.h5ad --output output/deconv \
  --method destvi --reference ref.h5ad --cell-type-key cell_type

# Stereoscope
python omicsclaw.py run deconv \
  --input output/preprocess/processed.h5ad --output output/deconv \
  --method stereoscope --reference ref.h5ad --cell-type-key cell_type

# Tangram
python omicsclaw.py run deconv \
  --input output/preprocess/processed.h5ad --output output/deconv \
  --method tangram --reference ref.h5ad --cell-type-key cell_type

# SPOTlight  (requires R + SPOTlight; see prerequisites below)
python omicsclaw.py run deconv \
  --input output/preprocess/processed.h5ad --output output/deconv \
  --method spotlight --reference ref.h5ad --cell-type-key cell_type

# CARD  (requires R + CARD; see prerequisites below)
python omicsclaw.py run deconv \
  --input output/preprocess/processed.h5ad --output output/deconv \
  --method card --reference ref.h5ad --cell-type-key cellType

# CARD with spatial imputation
python omicsclaw.py run deconv \
  --input output/preprocess/processed.h5ad --output output/deconv \
  --method card --reference ref.h5ad --cell-type-key cellType \
  --card-imputation
```

### RCTD — Prerequisites and Workflow

**What RCTD does**

RCTD (Robust Cell Type Decomposition, Cable *et al.* 2022, *Nature Biotechnology*)
models spatial gene expression as a weighted mixture of cell type profiles learned
from a single-cell reference. It supports three modes:

| Mode | When to use |
|------|-------------|
| `full` | Each spot may contain any mixture of cell types |
| `doublet` (default) | Each spot is composed of at most two cell types |
| `single` | Each spot is assigned exactly one cell type |

**Stack**

```
Python side          R side (called via rpy2)
─────────────        ────────────────────────
OmicsClaw          spacexr::create_RCTD()
  spatial_deconv.py  spacexr::run.RCTD()
  ↕ rpy2 + anndata2ri
```

**Step 1 — Install Python bridge**

```bash
# R must be on PATH first
which R          # e.g. /usr/bin/R or /opt/R/4.4.1/bin/R

pip install "rpy2>=3.5.0,<3.7" anndata2ri
```

**Step 2 — Install R packages**

```bash
# From the OmicsClaw project root:
Rscript install_r_dependencies.R
```

This installs `spacexr` (RCTD), `CARD`, `SPOTlight`, `CellChat`, `numbat`, and
`SPARK` in one step. Individual install commands for `spacexr`:

```r
install.packages("devtools")
devtools::install_github("dmcable/spacexr", build_vignettes = FALSE)
```

**Step 3 — Prepare inputs**

| Argument | Description |
|----------|-------------|
| `--input` | Preprocessed spatial AnnData (`.h5ad`) with `obsm["spatial"]` |
| `--reference` | Single-cell reference AnnData with raw counts in `adata.X` |
| `--cell-type-key` | `adata.obs` column name containing cell type labels |

```bash
# Quick validity check before running
python - <<'EOF'
import anndata as ad
sp  = ad.read_h5ad("output/preprocess/processed.h5ad")
ref = ad.read_h5ad("ref.h5ad")
print("Spatial spots:", sp.n_obs, "| Genes:", sp.n_vars)
print("Ref cells    :", ref.n_obs, "| Cell type col present:",
      "cell_type" in ref.obs.columns)
EOF
```

**Step 4 — Run**

```bash
python omicsclaw.py run deconv \
  --input  output/preprocess/processed.h5ad \
  --output output/deconv_rctd \
  --method rctd \
  --reference ref.h5ad \
  --cell-type-key cell_type
```

**Outputs**

```
output/deconv_rctd/
├── figures/
│   ├── rctd_cell_proportions_spatial.png   # multi-panel spatial proportion maps
│   ├── rctd_dominant_celltype.png          # dominant cell type per spot
│   └── rctd_diversity.png                  # Shannon entropy per spot
├── tables/
│   └── cell_proportions.csv                # per-spot proportion matrix
├── report.md
└── result.json
```

Proportions are stored in `adata.obsm["rctd_proportions"]` and written to
`tables/cell_proportions.csv` (rows = spots, columns = cell types).

**Troubleshooting RCTD**

| Error | Cause | Fix |
|-------|-------|-----|
| `rpy2 not found` | rpy2 not installed | `pip install "rpy2>=3.5.0,<3.7"` |
| `R_HOME not set` | R not on PATH | `export R_HOME=$(R RHOME)` |
| `package 'spacexr' not found` | spacexr not installed in R | `Rscript install_r_dependencies.R` |
| `Error in .check_types` | Reference counts are not integers | ensure `adata.X` stores raw integer counts |
| `minimum_mean_moleculecount` warning | Sparse reference (< 25 cells/type) | filter rare cell types or use `full` mode |

---

## 5. Spatial Statistics (`statistics`)

| Method | Description | Extra Parameters |
|--------|-------------|-----------------|
| `neighborhood_enrichment` **(default)** | Cluster co-localisation enrichment | `--cluster-key` |
| `moran` | Global Moran's I autocorrelation | `--genes`, `--n-top-genes` |
| `geary` | Geary's C autocorrelation | `--genes`, `--n-top-genes` |
| `local_moran` | Local Moran's I (LISA) | `--genes` |
| `getis_ord` | Getis-Ord Gi* hotspot detection | `--genes` |
| `bivariate_moran` | Bivariate spatial correlation between gene pairs | `--genes` |
| `ripley` | Ripley's K/L/F functions | `--cluster-key` |
| `co_occurrence` | Spatial co-occurrence probability | `--cluster-key` |
| `network_properties` | Spatial graph topology metrics | `--cluster-key` |
| `spatial_centrality` | Spot centrality in spatial graph | `--cluster-key` |

```bash
# neighborhood enrichment
python omicsclaw.py run statistics \
  --input output/preprocess/processed.h5ad --output output/statistics \
  --analysis-type neighborhood_enrichment --cluster-key leiden

# global Moran's I on top 20 HVGs
python omicsclaw.py run statistics \
  --input output/preprocess/processed.h5ad --output output/statistics \
  --analysis-type moran --n-top-genes 20

# Getis-Ord Gi* on specific genes
python omicsclaw.py run statistics \
  --input output/preprocess/processed.h5ad --output output/statistics \
  --analysis-type getis_ord --genes EPCAM,CD3D,CD68
```

---

## 6. Spatially Variable Genes (`genes`)

| Method | Description |
|--------|-------------|
| `morans` **(default)** | Moran's I ranking (fast, no extra deps) |
| `spatialde` | Gaussian process model (requires `spatialde`) |
| `sparkx` | Non-parametric covariance test (built-in) |
| `flashs` | Flash-based SVG scoring (built-in) |

```bash
python omicsclaw.py run genes \
  --input output/preprocess/processed.h5ad --output output/genes \
  --method morans --n-top-genes 50

python omicsclaw.py run genes \
  --input output/preprocess/processed.h5ad --output output/genes \
  --method spatialde --fdr-threshold 0.05

python omicsclaw.py run genes \
  --input output/preprocess/processed.h5ad --output output/genes \
  --method sparkx --n-top-genes 50
```

---

## 7. Differential Expression (`de`)

| Method | Description |
|--------|-------------|
| `wilcoxon` **(default)** | Wilcoxon rank-sum test |
| `t-test` | Welch's t-test |
| `pydeseq2` | Pseudobulk DESeq2 (requires `pydeseq2`) |

```bash
# compare all clusters
python omicsclaw.py run de \
  --input output/preprocess/processed.h5ad --output output/de \
  --method wilcoxon --groupby leiden --n-top-genes 20

# compare two specific groups
python omicsclaw.py run de \
  --input output/preprocess/processed.h5ad --output output/de \
  --method t-test --groupby leiden --group1 0 --group2 1

# pseudobulk DESeq2
python omicsclaw.py run de \
  --input output/preprocess/processed.h5ad --output output/de \
  --method pydeseq2 --groupby leiden
```

---

## 8. Condition Comparison (`condition`)

Single method: pseudobulk DESeq2. Requires `.obs` columns for condition and sample.

```bash
python omicsclaw.py run condition \
  --input data.h5ad --output output/condition \
  --condition-key treatment --sample-key sample_id \
  --reference-condition control
```

---

## 9. Cell-Cell Communication (`communication`)

| Method | Description |
|--------|-------------|
| `liana` **(default)** | LIANA+ multi-method consensus (requires `liana`) |
| `cellphonedb` | Permutation-based LR scoring (requires `cellphonedb`) |
| `fastccc` | Fast CCC scoring (requires `fastccc`, Python ≥3.11) |

```bash
python omicsclaw.py run communication \
  --input output/preprocess/processed.h5ad --output output/communication \
  --method liana --cell-type-key leiden --species human

python omicsclaw.py run communication \
  --input output/preprocess/processed.h5ad --output output/communication \
  --method cellphonedb --cell-type-key leiden

python omicsclaw.py run communication \
  --input output/preprocess/processed.h5ad --output output/communication \
  --method fastccc --cell-type-key leiden
```

---

## 10. RNA Velocity (`velocity`)

Requires spliced/unspliced count layers in the input.

| Method | Description |
|--------|-------------|
| `stochastic` **(default)** | Stochastic model (scVelo) |
| `deterministic` | Deterministic model (scVelo) |
| `dynamical` | Full dynamical model (scVelo, slower) |
| `velovi` | Variational inference model (requires `scvi-tools`) |

```bash
python omicsclaw.py run velocity \
  --input data.h5ad --output output/velocity \
  --method stochastic

python omicsclaw.py run velocity \
  --input data.h5ad --output output/velocity \
  --method dynamical
```

---

## 11. Trajectory Inference (`trajectory`)

| Method | Description |
|--------|-------------|
| `dpt` **(default)** | Diffusion pseudotime (built-in via scanpy) |
| `cellrank` | Markov chain trajectory (requires `cellrank`) |
| `palantir` | Diffusion map pseudotime (requires `palantir`) |

```bash
python omicsclaw.py run trajectory \
  --input output/velocity/processed.h5ad --output output/trajectory \
  --method dpt

# specify a root cell and number of terminal states
python omicsclaw.py run trajectory \
  --input output/velocity/processed.h5ad --output output/trajectory \
  --method cellrank --n-states 3

python omicsclaw.py run trajectory \
  --input output/velocity/processed.h5ad --output output/trajectory \
  --method palantir --root-cell CELL_BARCODE_HERE
```

---

## 12. Pathway Enrichment (`enrichment`)

| Method | Description |
|--------|-------------|
| `enrichr` **(default)** | Over-representation analysis via Enrichr API |
| `gsea` | Gene Set Enrichment Analysis (requires `gseapy`) |
| `ssgsea` | Single-sample GSEA scoring (requires `gseapy`) |

```bash
python omicsclaw.py run enrichment \
  --input output/de/processed.h5ad --output output/enrichment \
  --method enrichr --source GO_Biological_Process_2021 --species human

python omicsclaw.py run enrichment \
  --input output/de/processed.h5ad --output output/enrichment \
  --method gsea --source KEGG_2021_Human

python omicsclaw.py run enrichment \
  --input output/de/processed.h5ad --output output/enrichment \
  --method ssgsea
```

---

## 13. Copy Number Variation (`cnv`)

| Method | Description |
|--------|-------------|
| `infercnvpy` **(default)** | Sliding-window CNV inference (requires `infercnvpy`) |
| `numbat` | Haplotype-aware CNV (requires `rpy2` + R + Numbat) |

```bash
# infercnvpy — optionally specify normal reference cells
python omicsclaw.py run cnv \
  --input output/preprocess/processed.h5ad --output output/cnv \
  --method infercnvpy --reference-key cell_type --window-size 250 --step 50

# numbat — requires R environment
python omicsclaw.py run cnv \
  --input output/preprocess/processed.h5ad --output output/cnv \
  --method numbat --reference-key cell_type
```

---

## 14. Multi-Sample Integration (`integrate`)

| Method | Description |
|--------|-------------|
| `harmony` **(default)** | Iterative correction in PCA space (requires `harmonypy`) |
| `bbknn` | Batch-balanced KNN graph (requires `bbknn`) |
| `scanorama` | Panoramic stitching (requires `scanorama`) |

```bash
python omicsclaw.py run integrate \
  --input combined.h5ad --output output/integrate \
  --method harmony --batch-key batch

python omicsclaw.py run integrate \
  --input combined.h5ad --output output/integrate \
  --method bbknn --batch-key batch

python omicsclaw.py run integrate \
  --input combined.h5ad --output output/integrate \
  --method scanorama --batch-key batch
```

---

## 15. Spatial Registration (`register`)

| Method | Description |
|--------|-------------|
| `paste` **(default)** | Optimal transport slice alignment (requires `POT`, `paste-bio`) |

```bash
python omicsclaw.py run register \
  --input combined.h5ad --output output/register \
  --method paste --reference-slice slice1.h5ad
```

---

## 16. Orchestrator (`orchestrator`)

Routes queries to the right skill and chains named pipelines.

```bash
# route by natural language query
python omicsclaw.py run orchestrator \
  --query "find spatially variable genes" \
  --input data.h5ad --output output/orchestrator

# run a named pipeline
python omicsclaw.py run orchestrator \
  --pipeline standard --input data.h5ad --output output/pipeline

# available pipelines: standard, full, integration, spatial_only, cancer
python omicsclaw.py run orchestrator \
  --pipeline cancer --input data.h5ad --output output/pipeline

# list all registered skills
python omicsclaw.py list
```

---

## Genomics Skills

### 17. FASTQ Quality Control (`genomics-qc`)

Comprehensive FASTQ quality assessment: Phred scores, GC/N content, Q20/Q30
rates, per-base quality profiles, adapter contamination detection.

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--input` | required | FASTQ file |
| `--demo` | — | Generate synthetic FASTQ data |

**Key metrics:** mean quality, Q20/Q30 rate, GC content, N content, adapter hits, per-base quality distribution.

```bash
python omicsclaw.py run genomics-qc --demo
python omicsclaw.py run genomics-qc --input reads.fastq.gz --output output/qc
```

---

### 18. Alignment Statistics (`genomics-alignment`)

SAM/BAM-based alignment statistics: flagstat metrics, MAPQ distribution,
insert size analysis. Mirrors `samtools flagstat` output.

**Key metrics:** mapping rate, proper pair rate, duplicate rate, MAPQ distribution, insert size mean/std.

```bash
python omicsclaw.py run genomics-alignment --demo
python omicsclaw.py run genomics-alignment --input aligned.sam --output output/alignment
```

---

### 19. Variant Calling (`genomics-variant-calling`)

Variant classification (SNP/MNP/INS/DEL/COMPLEX per VCF spec), Ti/Tv ratio
calculation, multi-allelic handling.

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--method` | `gatk` | gatk, deepvariant, freebayes |
| `--mode` | `germline` | germline or somatic |

**Quality benchmarks:** WGS Ti/Tv ~2.0-2.1, WES Ti/Tv ~2.8-3.3.

```bash
python omicsclaw.py run genomics-variant-calling --demo
python omicsclaw.py run genomics-variant-calling --input sample.bam --output output/variants
```

---

### 20. VCF Operations (`genomics-vcf-operations`)

VCF parsing, multi-allelic handling, variant type classification, quality/depth
filtering, Ti/Tv and per-chromosome statistics.

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--min-qual` | `0` | Minimum QUAL filter |
| `--min-dp` | `0` | Minimum depth (DP) filter |

```bash
python omicsclaw.py run genomics-vcf-operations --demo
python omicsclaw.py run genomics-vcf-operations --input vars.vcf --output output/vcf-ops \
  --min-qual 30 --min-dp 10
```

---

### 21. Variant Annotation (`genomics-variant-annotation`)

Functional impact prediction using VEP consequence types (HIGH/MODERATE/LOW/MODIFIER),
SIFT (<0.05 = deleterious), PolyPhen-2 (>0.908 = probably damaging), CADD Phred
(>20 = top 1%, >30 = top 0.1%).

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--n-variants` | `300` | Number of demo variants |

```bash
python omicsclaw.py run genomics-variant-annotation --demo
python omicsclaw.py run genomics-variant-annotation --input annotated.csv --output output/annotation
```

---

### 22. Structural Variant Detection (`genomics-sv-detection`)

SV VCF parsing with BND notation for translocations. Classifies DEL/DUP/INV/TRA
with size stratification (small 50bp-1kb, medium 1kb-100kb, large 100kb-10Mb).

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--n-svs` | `100` | Number of demo SVs |

```bash
python omicsclaw.py run genomics-sv-detection --demo
python omicsclaw.py run genomics-sv-detection --input structural.vcf --output output/sv
```

---

### 23. CNV Calling (`genomics-cnv-calling`)

Copy number variation calling using simplified CBS (Circular Binary Segmentation,
Olshen et al. 2004). Uses CNVkit-standard thresholds (gain: log2>0.3, loss: log2<-0.3).

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--method` | `cbs` | cbs, none |
| `--alpha` | `0.01` | CBS significance level |

**CN classification:** amplification (log2>1.0), gain (0.3-1.0), neutral (-0.3 to 0.3),
loss (-1.0 to -0.3), deep deletion (<-1.0). CN estimated as `2 * 2^(log2_ratio)`.

```bash
python omicsclaw.py run genomics-cnv-calling --demo
python omicsclaw.py run genomics-cnv-calling --input bins.csv --output output/cnv --alpha 0.01
```

---

### 24. Genome Assembly (`genomics-assembly`)

Assembly quality metrics (QUAST-compatible): N50/N90/L50/L90, GC content,
contig length distribution, completeness estimation.

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--genome-size` | `0` | Expected genome size in bp (for completeness) |

```bash
python omicsclaw.py run genomics-assembly --demo
python omicsclaw.py run genomics-assembly --input contigs.fasta --output output/assembly \
  --genome-size 5000000
```

---

### 25. Haplotype Phasing (`genomics-phasing`)

Phase block analysis from phased VCF files: N50 (bp and variants), phased
fraction, PS field parsing, pipe-delimited genotype detection.

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--n-variants` | `2000` | Number of demo variants |

```bash
python omicsclaw.py run genomics-phasing --demo
python omicsclaw.py run genomics-phasing --input phased.vcf --output output/phasing
```

---

### 26. Epigenomics (`genomics-epigenomics`)

Peak analysis for ChIP-seq/ATAC-seq/CUT&Tag data. Parses narrowPeak (BED6+4)
format with ENCODE quality standards assessment.

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--method` | `macs2` | macs2, macs3, homer, genrich |
| `--assay` | `chip-seq` | chip-seq, atac-seq, cut-tag |
| `--n-peaks` | `500` | Number of demo peaks |

```bash
python omicsclaw.py run genomics-epigenomics --demo
python omicsclaw.py run genomics-epigenomics --input peaks.narrowPeak --output output/epi \
  --assay atac-seq
```

---

## Metabolomics Skills

### 27. Metabolomics Peak Detection (`metabolomics-peak-detection`)

Detects peaks in metabolomics intensity data using `scipy.signal.find_peaks`.

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--prominence` | `10000` | Minimum peak prominence |
| `--height` | `None` | Minimum absolute peak height |
| `--distance` | `5` | Minimum distance between peaks (data points) |
| `--sample-prefix` | auto | Column prefix to identify samples |

```bash
# Demo
python omicsclaw.py run metabolomics-peak-detection --demo

# With data
python omicsclaw.py run metabolomics-peak-detection \
  --input features.csv --output output/peaks \
  --prominence 50000 --distance 10
```

---

## 18. Metabolomics XCMS Preprocessing (`metabolomics-xcms-preprocessing`)

Simulates XCMS centWave peak detection and alignment (Python fallback).

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--ppm` | `25` | Mass accuracy in ppm |
| `--peakwidth-min` | `10` | Minimum peak width (seconds) |
| `--peakwidth-max` | `60` | Maximum peak width (seconds) |

```bash
python omicsclaw.py run metabolomics-xcms-preprocessing --demo

python omicsclaw.py run metabolomics-xcms-preprocessing \
  --input sample1.mzML sample2.mzML --output output/xcms \
  --ppm 15 --peakwidth-min 5 --peakwidth-max 30
```

---

## 19. Metabolomics Normalization (`metabolomics-normalization`)

| Method | Description | Reference |
|--------|-------------|-----------|
| `median` **(default)** | Scale each sample by its median | MetaboAnalyst |
| `quantile` | Sort → row-mean → rank-assign | Bolstad et al., 2003 |
| `total` | Total-ion-count (TIC) normalization | — |
| `pqn` | Probabilistic Quotient Normalization (median reference spectrum) | Dieterle et al., 2006 |
| `log` | Log2(x + 1) transformation | — |

```bash
python omicsclaw.py run metabolomics-normalization --demo --method quantile

python omicsclaw.py run metabolomics-normalization \
  --input features.csv --output output/norm --method pqn
```

---

## 20. Metabolomics Annotation (`metabolomics-annotation`)

Annotates m/z values against metabolite databases with multi-adduct support.

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--database` | `hmdb` | Database (hmdb, kegg, lipidmaps, metlin) |
| `--ppm` | `10` | Mass tolerance in ppm |
| `--adducts` | `[M+H]+ [M-H]-` | Adduct types to consider |

Supported adducts: `[M+H]+`, `[M-H]-`, `[M+Na]+`, `[M+K]+`, `[M+NH4]+`

```bash
python omicsclaw.py run metabolomics-annotation --demo

python omicsclaw.py run metabolomics-annotation \
  --input peaks.csv --output output/annot \
  --ppm 5 --adducts "[M+H]+" "[M-H]-" "[M+Na]+"
```

---

## 21. Metabolomics Quantification (`metabolomics-quantification`)

Feature quantification with imputation and normalization.

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--impute` | `min` | Imputation method: `min` (half-minimum), `median`, `knn` (sklearn KNNImputer) |
| `--normalize` | `tic` | Normalization: `tic`, `median`, `log` |

```bash
python omicsclaw.py run metabolomics-quantification --demo --impute knn

python omicsclaw.py run metabolomics-quantification \
  --input features.csv --output output/quant \
  --impute knn --normalize median
```

---

## 22. Metabolomics Statistics (`metabolomics-statistics`)

Univariate statistical testing with Benjamini-Hochberg FDR correction.

| Method | Description |
|--------|-------------|
| `ttest` **(default)** | Welch's t-test (`equal_var=False`) |
| `wilcoxon` | Wilcoxon rank-sum (Mann-Whitney U) test |
| `anova` | One-way ANOVA (F-test) |
| `kruskal` | Kruskal-Wallis H test (non-parametric ANOVA) |

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--method` | `ttest` | Statistical test method |
| `--alpha` | `0.05` | Significance threshold (applied to FDR-adjusted p-values) |
| `--group1-prefix` | auto | Column prefix for group 1 |
| `--group2-prefix` | auto | Column prefix for group 2 |

```bash
python omicsclaw.py run metabolomics-statistics --demo --method ttest

python omicsclaw.py run metabolomics-statistics \
  --input features.csv --output output/stats \
  --method kruskal --alpha 0.01
```

---

## 23. Metabolomics Differential Analysis (`metabolomics-de`)

Welch's t-test with BH FDR correction and PCA visualization.

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--group-a-prefix` | `ctrl` | Column prefix for control group |
| `--group-b-prefix` | `treat` | Column prefix for treatment group |

```bash
python omicsclaw.py run metabolomics-de --demo

python omicsclaw.py run metabolomics-de \
  --input quantified.csv --output output/diff \
  --group-a-prefix control --group-b-prefix disease
```

---

## 24. Metabolomics Pathway Enrichment (`metabolomics-pathway-enrichment`)

Over-representation analysis (ORA) using the hypergeometric test against KEGG pathways.

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--method` | `ora` | Analysis method: `ora`, `mummichog`, `fella` |

```bash
python omicsclaw.py run metabolomics-pathway-enrichment --demo

python omicsclaw.py run metabolomics-pathway-enrichment \
  --input significant_metabolites.csv --output output/pathway
```

---

## Quick Reference

| Skill | Default Method | All Supported Methods |
|-------|---------------|----------------------|
| preprocess | — | — |
| domains | `leiden` | leiden, louvain, spagcn, stagate, graphst, banksy |
| annotate | `marker_based` | marker_based, tangram, scanvi, cellassign |
| deconv | `cell2location` | cell2location, rctd, tangram, card |
| statistics | `neighborhood_enrichment` | neighborhood_enrichment, moran, geary, local_moran, getis_ord, bivariate_moran, ripley, co_occurrence, network_properties, spatial_centrality |
| genes | `morans` | morans, spatialde, sparkx, flashs |
| de | `wilcoxon` | wilcoxon, t-test, pydeseq2 |
| condition | — | pseudobulk DESeq2 only |
| communication | `liana` | liana, cellphonedb, fastccc |
| velocity | `stochastic` | stochastic, deterministic, dynamical, velovi |
| trajectory | `dpt` | dpt, cellrank, palantir |
| enrichment | `enrichr` | enrichr, gsea, ssgsea |
| cnv | `infercnvpy` | infercnvpy, numbat |
| integrate | `harmony` | harmony, bbknn, scanorama |
| register | `paste` | paste |
| orchestrator | — | — |
| **genomics-qc** | — | FASTQ parsing, Phred scores |
| **genomics-alignment** | — | SAM flagstat metrics |
| **genomics-variant-calling** | `gatk` | gatk, deepvariant, freebayes |
| **genomics-vcf-operations** | — | VCF stats, multi-allelic, Ti/Tv |
| **genomics-variant-annotation** | — | VEP consequences, SIFT, PolyPhen, CADD |
| **genomics-sv-detection** | — | DEL/DUP/INV/TRA, BND notation |
| **genomics-cnv-calling** | `cbs` | cbs, none |
| **genomics-assembly** | — | N50/N90/L50/L90, GC content |
| **genomics-phasing** | — | Phase block N50, PS field |
| **genomics-epigenomics** | `macs2` | macs2, macs3, homer, genrich |
| **metabolomics-peak-detection** | — | scipy.signal.find_peaks |
| **metabolomics-xcms-preprocessing** | — | centWave simulation |
| **metabolomics-normalization** | `median` | median, quantile, total, pqn, log |
| **metabolomics-annotation** | `hmdb` | hmdb, kegg, lipidmaps, metlin |
| **metabolomics-quantification** | `min` + `tic` | impute: min, median, knn; norm: tic, median, log |
| **metabolomics-statistics** | `ttest` | ttest, wilcoxon, anova, kruskal |
| **metabolomics-de** | — | Welch's t-test + BH FDR |
| **metabolomics-pathway-enrichment** | `ora` | ora, mummichog, fella |

