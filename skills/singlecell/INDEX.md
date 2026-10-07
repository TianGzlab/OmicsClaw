# Single-Cell Omics — Skill Index

> The skill list below is derived from each skill's `SKILL.md` frontmatter
> and is checked by `tests/skills/test_domain_index_is_current.py`.
> Regenerate it with
> `OMICSCLAW_WRITE_SKILL_INDEX=1 pytest tests/skills/test_domain_index_is_current.py`.
> The prose above the list is written by hand.

**Domain key:** `singlecell`

**Skill count:** 30

**Primary data types:** h5ad, h5, loom, mtx

scRNA-seq + scATAC-seq: FASTQ→counts, QC, filter, doublet removal, normalize→HVG→PCA→UMAP→cluster, annotation, DE, trajectory, velocity, GRN, CCC.

## Skills

- `sc-ambient-removal` — Load when removing ambient RNA contamination from droplet-based scRNA-seq using a simple subtraction path, CellBender, or SoupX. Skip when the contamination is multiplet barcodes (use sc-doublet-detection); before counts exist (use sc-count).
  triggers: ambient RNA, ambient removal, cellbender, contamination, background RNA
- `sc-batch-integration` — Load when integrating multi-sample scRNA-seq with Harmony, scVI, scANVI, BBKNN, Scanorama, SIMBA, or supported R-backed methods to remove batch effects. Skip when the data is one sample (no batch effect to integrate); upstream merging only (use sc-multi-count).
  triggers: batch integration, batch effect, harmony, scvi, bbknn, merge samples
- `sc-cell-annotation` — Load when assigning cell-type labels to a clustered scRNA AnnData via marker dictionaries, CellTypist, PopV, KNNPredict, SingleR, scmap, SCSA, or a manual cluster-to-label map. Skip when ranking marker genes per cluster (use sc-markers); condition-vs-control DE (use sc-de).
- `sc-cell-communication` — Load when computing cell-cell ligand-receptor communication on an annotated scRNA AnnData via builtin scorer, LIANA, CellPhoneDB, CellChat (R), or NicheNet (R). Skip when assigning cell-type labels (use sc-cell-annotation); transcription factor → target regulatory networks (use sc-grn).
  triggers: cell communication, cell-cell communication, ligand receptor, cellchat, liana, cellphonedb, nichenet
- `sc-clustering` — Load when building the neighbour graph, embedding (UMAP/t-SNE/diffmap/PHATE), and clustering (Leiden/Louvain) on a normalised single-cell AnnData. Skip when QC/normalisation/HVG/PCA have not run yet (use sc-preprocessing); marker ranking after clustering (use sc-markers).
- `sc-count` — Load when turning scRNA FASTQ (or existing CellRanger/STARsolo/SimpleAF/kb-python output) into a downstream-ready AnnData. Skip when reads are already counted into AnnData (use sc-standardize-input); raw quality assessment only (use sc-fastq-qc).
  triggers: Cell Ranger count, STARsolo count, fastq to adata, raw single-cell counting, generate count matrix
- `sc-cytotrace` — Load when computing per-cell differentiation potency / stemness scores from gene-expression complexity on a scRNA AnnData via the CytoTRACE-simple method. Skip when ordering cells along a trajectory (use sc-pseudotime); marker-based cell-type labelling (use sc-cell-annotation).
- `sc-de` — Load when finding marker genes per cluster or comparing condition expression in single-cell RNA-seq. Skip when the data is bulk (use bulkrna-de); spatial (use spatial-de); cluster-only markers without conditions (use sc-markers).
  triggers: differential expression, marker genes, de analysis, wilcoxon, pseudo-bulk
- `sc-differential-abundance` — Load when testing whether cell-type / cluster proportions or neighbourhood densities differ between conditions in a multi-sample scRNA AnnData via Milo, scCODA, simple proportion screen, or R Monte-Carlo permutation. Skip when ranking marker genes (use sc-markers); per-cell DE (use sc-de).
- `sc-doublet-detection` — Load when annotating putative doublets in single-cell RNA-seq using Scrublet, DoubletDetection, DoubletFinder, scDblFinder, or scds. Skip when ambient RNA is the contamination problem (use sc-ambient-removal); before counts exist (use sc-fastq-qc).
- `sc-drug-response` — Load when scoring drug sensitivity per cluster on an annotated scRNA AnnData via simple-correlation against drug-target signatures or via CaDRReS-Sc pretrained models (GDSC / PRISM). Skip when the AnnData has no cluster labels yet (use sc-clustering); predicting genetic-perturbation effects (use sc-in-silico-perturbation).
- `sc-enrichment` — Load when running bulk-style pathway enrichment (ORA / GSEA / GSEA-R / GSVA-R) on a per-group ranked DE / marker list against a gene-set library. Skip when computing per-cell pathway scores in-place (use sc-pathway-scoring); de-novo gene-program discovery (use sc-gene-programs).
  triggers: sc enrichment, single-cell enrichment, GO enrichment, KEGG enrichment, GSEA, ORA, pathway enrichment
- `sc-fastq-qc` — Load when checking raw single-cell FASTQ read quality (Phred / GC / adapter / length) before counting. Skip when reads are already counted (use sc-qc); bulk FASTQ (use bulkrna-read-qc).
  triggers: scRNA FASTQ QC, FastQC single-cell, MultiQC single-cell, raw read quality, read-level QC
- `sc-filter` — Load when removing low-quality cells and lowly-detected genes from a single-cell AnnData using QC-derived thresholds or tissue presets. Skip when the full normalize→HVG→PCA→cluster pipeline (use sc-preprocessing); reads are still raw FASTQ (use sc-fastq-qc).
  triggers: filter cells, cell filtering, gene filtering, remove low quality, qc filtering, tissue-specific thresholds
- `sc-gene-programs` — Load when extracting gene programs (NMF / cNMF factorisation) and per-cell program usage scores from a non-negative scRNA AnnData. Skip when ranking marker genes per cluster (use sc-markers); inferring TF → target regulons (use sc-grn).
- `sc-grn` — Load when inferring TF → target gene regulatory networks on a normalised scRNA AnnData via pySCENIC (GRNBoost2 + cisTarget + AUCell) or correlation-based GRN fallback (when arboreto is unavailable, in --demo, or with --allow-simplified-grn). Skip when computing ligand-receptor cell-cell signalling (use sc-cell-communication); predicting genetic-KO effects (use sc-in-silico-perturbation).
  triggers: grn, gene regulatory, scenic, pyscenic, regulon, transcription factor, grnboost
- `sc-in-silico-perturbation` — Load when predicting in-silico gene knockout effects on a normalised scRNA AnnData via GRN-based propagation (Python) or scTenifoldKnk (R). Skip when you have a real Perturb-seq / CRISPR screen (use sc-perturb); predicting drug sensitivity (use sc-drug-response).
- `sc-markers` — Load when ranking cluster-level marker genes from a clustered single-cell AnnData via Scanpy Wilcoxon / t-test / logreg or COSG specificity. Skip when comparing condition-vs-control with replicates (use sc-de); assigning cell-type labels (use sc-cell-annotation).
- `sc-metacell` — Load when aggregating single cells into metacells (sample-aware coarse-grained pseudo-cells) on a normalised scRNA AnnData via SEACells or KMeans on a low-D embedding. Skip when ranking marker genes per cluster (use sc-markers); trajectory pseudotime ordering (use sc-pseudotime).
- `sc-multi-count` — Load when merging multiple single-sample scRNA-seq count matrices (one per sample-from-sc-count) into a single downstream-ready AnnData with sample labels. Skip when input is one already-merged AnnData (use sc-standardize-input); FASTQ→counts on each sample (use sc-count).
  triggers: merge count matrices, multi-sample count, aggregate samples, combine count outputs, cellranger aggr alternative
- `sc-pathway-scoring` — Load when computing per-cell pathway / gene-set scores on a normalised scRNA AnnData via AUCell (R or Python) or Scanpy score_genes. Skip when running condition-vs-control bulk-style enrichment on top of a DE table (use sc-enrichment); de-novo gene-program discovery (use sc-gene-programs).
  triggers: pathway score, pathway scoring, gene set score, module score, pathway activity, signature score
- `sc-perturb` — Load when classifying perturbed vs non-perturbed cells in a Perturb-seq / CRISPR-screen scRNA AnnData via the pertpy Mixscape workflow. Skip when guide labels are not yet attached to the expression object (use sc-perturb-prep); in-silico KO predictions on unperturbed data (use sc-in-silico-perturbation).
- `sc-perturb-prep` — Load when attaching cell-barcode → sgRNA assignments from a mapping TSV/CSV onto a Perturb-seq expression AnnData, producing standardised perturbation / sgRNA / target-gene obs columns. Skip when the AnnData already has perturbation labels (use sc-perturb); raw guide-calling from FASTQ (use upstream demuxlet / cellranger guide pipelines).
- `sc-preprocessing` — Load when normalising QC'd scRNA into a PCA-ready AnnData via scanpy / Seurat / SCTransform / Pearson residuals. Skip when QC thresholds are still undecided (use sc-qc); batch correction across samples (use sc-batch-integration).
  triggers: single cell preprocess, scRNA preprocessing, normalize hvg pca, base preprocessing, Seurat preprocessing, SCTransform preprocessing
- `sc-pseudotime` — Load when ordering cells along a developmental trajectory in a normalised scRNA AnnData via DPT, Palantir, VIA, CellRank, Slingshot (R), or Monocle3 (R). Skip when ranking marker genes per cluster (use sc-markers); RNA velocity vector fields (use sc-velocity).
  triggers: pseudotime, trajectory, lineage, diffusion pseudotime, palantir, via, cellrank, monocle3, slingshot
- `sc-qc` — Load when computing per-cell QC metrics (n_genes, total counts, mt%, ribo%) on a single-cell AnnData before filtering. Skip when reads are still raw FASTQ (use sc-fastq-qc); you want to filter cells now (use sc-filter).
  triggers: scRNA QC, single-cell QC, quality control, mitochondrial percentage, ribosomal percentage, QC violin, QC scatter, n genes per cell
- `sc-standardize-input` — Load when an external single-cell h5ad/h5/loom/mtx needs to be canonicalised onto the OmicsClaw AnnData contract before downstream scRNA skills run. Skip when data already came from sc-count (already canonical); bulk RNA-seq (use bulkrna-qc); spatial (use spatial-preprocess).
  triggers: standardize AnnData, fix scRNA input, canonicalize single-cell input, prepare AnnData, input contract
- `sc-velocity` — Load when computing RNA velocity vectors on a scRNA AnnData with spliced / unspliced layers via scVelo (stochastic / dynamical / steady-state); dynamical mode additionally exports latent time. Skip when input lacks spliced+unspliced layers (use sc-velocity-prep); trajectory pseudotime ordering (use sc-pseudotime).
  triggers: rna velocity, velocity, scvelo, spliced unspliced, cellular dynamics, velovi, velocity pseudotime
- `sc-velocity-prep` — Load when generating spliced / unspliced layers from Cell Ranger BAM, FASTQ, STARsolo output, or velocyto loom — the prerequisite for sc-velocity. Skip when AnnData already has spliced+unspliced layers (use sc-velocity); any non-velocity preprocessing (use sc-preprocessing).
  triggers: RNA velocity prep, prepare spliced unspliced layers, velocyto, starsolo velocyto, velocity-ready AnnData
- `scatac-preprocessing` — Load when preprocessing a single-cell ATAC peak × cell AnnData via Signac-style TF-IDF + LSI + Leiden, producing a clustered UMAP-ready object. Skip when input is fragments; BAM (peak calling not implemented here); scRNA preprocessing (use sc-preprocessing).
  triggers: scATAC preprocessing, single-cell ATAC preprocessing, ATAC TF-IDF LSI, chromatin accessibility clustering, scATAC UMAP Leiden
