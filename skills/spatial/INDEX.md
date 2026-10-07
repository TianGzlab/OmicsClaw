# Spatial Transcriptomics — Skill Index

> The skill list below is derived from each skill's `SKILL.md` frontmatter
> and is checked by `tests/skills/test_domain_index_is_current.py`.
> Regenerate it with
> `OMICSCLAW_WRITE_SKILL_INDEX=1 pytest tests/skills/test_domain_index_is_current.py`.
> The prose above the list is written by hand.

**Domain key:** `spatial`

**Skill count:** 17

**Primary data types:** h5ad, h5, zarr, loom

Spatial transcriptomics for Visium/Xenium/MERFISH/Slide-seq: QC, domain detection, SVG, deconvolution, cell communication, trajectories, CNV.

## Skills

- `spatial-annotate` — Load when assigning per-spot cell-type labels on a spatial AnnData via marker-gene scoring or scRNA-reference mapping (Tangram / scANVI / CellAssign). Skip when computing spot-level cell-type proportions for multi-cell-per-spot platforms (use spatial-deconv); tissue-domain detection (use spatial-domains).
  triggers: cell type annotation, annotate cell types, Tangram, scANVI, CellAssign, marker genes, label transfer, spatial annotation
- `spatial-cnv` — Load when inferring copy-number variation per spot on a preprocessed spatial AnnData with chromosome-annotated genes via infercnvpy (default — log-ratio sliding-window) or Numbat (R, allele-aware clone deconvolution). Skip when `var["chromosome"]` / `var["start"]` / `var["end"]` gene-coord metadata is missing; no normal-reference subset can be defined.
  triggers: copy number variation, CNV, inferCNV, infercnvpy, Numbat, aneuploidy, chromosomal aberration, tumor clone
- `spatial-communication` — Load when computing ligand-receptor communication on labelled spatial AnnData with LIANA, CellPhoneDB, FastCCC or CellChat. Skip unlabelled data (use spatial-annotate) and non-spatial scRNA analysis (use sc-cell-communication).
  triggers: cell communication, ligand receptor, LIANA, CellPhoneDB, FastCCC, CellChat
- `spatial-condition` — Load when comparing conditions on spatial AnnData using biological-sample pseudobulk PyDESeq2 or Wilcoxon, with sample, condition and cluster labels. Skip one-condition per-cluster DE (use spatial-de) and experiments without independent replicates.
  triggers: condition comparison, pseudobulk, DESeq2, treatment vs control
- `spatial-de` — Load when ranking spatial cluster markers or comparing two spatial groups. Skip when the data is single-cell (use sc-de), bulk (use bulkrna-de), or for spatially variable expression (use spatial-genes).
  triggers: differential expression, marker gene, pseudobulk, Wilcoxon, t-test, PyDESeq2, spatial DE
- `spatial-deconv` — Load when deconvolving spot-level cell-type proportions on a Visium-style spatial AnnData using a labelled scRNA reference (FlashDeconv / Cell2location / RCTD / DestVI / Tangram / others). Skip when each spot is a single cell already (Xenium / MERFISH) (use spatial-annotate); tissue-domain detection (use spatial-domains).
  triggers: cell type deconvolution, spatial deconvolution, cell proportion, cell type proportion, cell2location, RCTD, DestVI, Stereoscope, Tangram, SPOTlight, CARD
- `spatial-domains` — Load when detecting tissue domains / niches on a preprocessed spatial AnnData via Leiden / Louvain (spatial-weighted) or graph-neural backends (SpaGCN / STAGATE / GraphST / BANKSY / CellCharter). Skip when ranking spatially variable genes (use spatial-genes); spot-level cell-type annotation (use spatial-annotate).
  triggers: spatial domain, tissue region, niche, spatial niche, niche identification, niche detection, SpaGCN, STAGATE, CellCharter
- `spatial-enrichment` — Load when running pathway or gene-set enrichment per cluster on spatial AnnData with over-representation, preranked GSEA, or ssGSEA group-mean scores. Skip when ranking spatially variable genes (use spatial-genes) or comparing conditions (use spatial-condition).
  triggers: pathway enrichment, gene set enrichment, enrichr, GSEA, ssGSEA, GO, Reactome, MSigDB
- `spatial-genes` — Load when ranking spatially variable genes with Moran's I, SpatialDE, SPARK-X, or FlashS. Skip when detecting tissue domains (use spatial-domains) or differential expression between groups (use spatial-de).
  triggers: spatially variable gene, spatial gene, SVG, SpatialDE, SPARK-X, spatial pattern, Moran, spatial autocorrelation
- `spatial-integrate` — Load when removing batch effects from multi-batch spatial AnnData with PCA using Harmony, BBKNN, or Scanorama. Skip physical coordinate alignment (use spatial-register) and single-batch data (use spatial-domains).
  triggers: multi-sample integration, batch correction, Harmony, BBKNN, Scanorama
- `spatial-microenvironment-subset` — Load when extracting a niche / microenvironment subset around a center cell-type by spatial radius from a labelled spatial AnnData, producing a smaller AnnData of centers + their within-radius neighbours. Skip when running global tissue-domain detection (use spatial-domains); cross-condition comparison (use spatial-condition).
  triggers: microenvironment, neighborhood subset, spatial radius, neighboring cells, nearby cells, tumor microenvironment, extract cells within 50 microns
- `spatial-preprocess` — Load when running the foundational spatial transcriptomics QC + filtering + normalisation + HVG + PCA + neighbour-graph + Leiden pipeline on a Visium / Xenium / generic spatial AnnData. Skip when raw FASTQs need converting first (use spatial-raw-processing); tissue-domain detection on already-preprocessed data (use spatial-domains).
  triggers: preprocess, spatial preprocessing, spatial QC, normalize, visium, xenium, merfish, slide-seq, load spatial data, leiden, umap
- `spatial-raw-processing` — Load when converting spatial transcriptomics raw FASTQ pairs through ST-Pipeline into a `raw_counts.h5ad` ready for spatial-preprocess. Skip when input is already a count-matrix AnnData (use spatial-preprocess); non-spatial bulk / scRNA FASTQ (use bulkrna-read-qc).
  triggers: spatial raw processing, raw spatial fastq, spatial fastq, st_pipeline, st pipeline, barcode coordinates, ids file, visium raw fastq, slide-seq fastq, slideseq fastq, upstream spatial processing
- `spatial-register` — Load when aligning multiple spatial slices into a common coordinate frame with PASTE or STalign. Skip single-slice data; for expression-space batch correction use spatial-integrate.
  triggers: spatial registration, slice alignment, PASTE, STalign
- `spatial-statistics` — Load when running spatial autocorrelation / hotspot / co-occurrence / neighbourhood-enrichment / Ripley K stats on a clustered spatial AnnData via squidpy. Skip when ranking spatially variable genes (use spatial-genes); tissue domain detection (use spatial-domains).
  triggers: spatial statistics, Moran, Geary, Ripley, co-occurrence, Getis-Ord, local Moran, centrality
- `spatial-trajectory` — Load when inferring pseudotime / lineage trajectories on a preprocessed spatial AnnData via DPT (default — diffusion pseudotime), CellRank (terminal-state + fate-probability), or Palantir (waypoint branch probabilities). Skip when the data has spliced/unspliced layers and you want velocity-driven dynamics (use spatial-velocity); non-spatial scRNA pseudotime (use sc-pseudotime).
  triggers: trajectory, pseudotime, diffusion pseudotime, DPT, CellRank, Palantir, cell fate, lineage
- `spatial-velocity` — Load when estimating RNA velocity on a spatial AnnData with `layers["spliced"]` + `layers["unspliced"]` via scVelo (stochastic / deterministic / dynamical) or veloVI (deep generative). Skip when input lacks the spliced/unspliced layers (must be quantified upstream by velocyto / kb-python / STARsolo); non-spatial scRNA velocity (use sc-velocity).
  triggers: RNA velocity, cellular dynamics, scVelo, VELOVI, latent time, spliced unspliced
