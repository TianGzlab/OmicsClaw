# Bulk RNA-seq — Skill Index

> The skill list below is derived from each skill's `SKILL.md` frontmatter
> and is checked by `tests/skills/test_domain_index_is_current.py`.
> Regenerate it with
> `OMICSCLAW_WRITE_SKILL_INDEX=1 pytest tests/skills/test_domain_index_is_current.py`.
> The prose above the list is written by hand.

**Domain key:** `bulkrna`

**Skill count:** 14

**Primary data types:** csv, tsv, fastq, bam

Bulk RNA-seq: FASTQ QC, alignment, count QC, DE (DESeq2), enrichment, splicing, WGCNA, deconvolution, PPI, survival, TrajBlend bulk-to-sc.

## Skills

- `bulkrna-batch-correction` — Load when correcting batch effects in bulk expression using R sva ComBat or the legacy Python parametric approximation. Skip single-batch inputs; use sc-batch-integration for single-cell data or spatial-integrate for spatial slices.
  triggers: batch correction, ComBat, batch effect, harmonize, multi-cohort, batch removal
- `bulkrna-coexpression` — Load when discovering bulk gene co-expression modules and hub genes with R WGCNA. Skip direct expression contrasts (use bulkrna-de), existing-gene-list PPI lookup (use bulkrna-ppi-network), or single-cell networks (use sc-grn).
  triggers: coexpression, WGCNA, gene network, co-expression modules, hub genes, gene modules
- `bulkrna-cosinor-rhythm` — Load when the user needs Deterministic fixed-period 24-hour single-component cosinor OLS rhythm analysis for a bulk RNA time-course CSV. Skip when an existing bulkrna skill already covers the request.
  triggers: cosinor, circadian rhythmicity, 24-hour rhythm, bulk RNA time course
- `bulkrna-de` — Load when comparing gene expression between two conditions in bulk RNA-seq count data. Skip when the data is single-cell (use sc-de); spatial (use spatial-de); you need exon-level alternative splicing (use bulkrna-splicing).
  triggers: differential expression, DE analysis, DESeq2, volcano plot, fold change, DEGs, bulk DE
- `bulkrna-deconvolution` — Load when estimating cell-type proportions in bulk RNA-seq samples from a single-cell or signature-matrix reference. Skip when the data is already single-cell (no deconvolution needed); spatial deconvolution (use spatial-deconv).
  triggers: bulk deconvolution, cell type proportion, NNLS, CIBERSORTx, bulk deconv, cell fraction
- `bulkrna-enrichment` — Load when running pathway / GO term enrichment on a bulk RNA-seq DE result list. Skip when the input is single-cell (use sc-enrichment); the input is spatial (use spatial-enrichment); metabolite pathways (use metabolomics-pathway-enrichment).
  triggers: bulk enrichment, pathway analysis, GSEA, ORA, GO enrichment, KEGG, bulk pathway
- `bulkrna-geneid-mapping` — Load when converting Ensembl, Entrez or symbol IDs in a bulk RNA count matrix using an explicit mapping or a small human demo reference. Skip when IDs already match downstream needs; use fetch_mapping explicitly for MyGene lookup.
  triggers: gene ID, Ensembl, Entrez, gene symbol, ID mapping, gene annotation, convert IDs
- `bulkrna-ppi-network` — Load when querying STRING for the protein-protein interaction neighborhood of a bulk RNA-seq DEG list and finding hub genes. Skip when pathway enrichment of the same list (use bulkrna-enrichment); de novo co-expression network discovery (use bulkrna-coexpression).
  triggers: PPI, protein interaction, STRING, network, hub gene, interactome
- `bulkrna-qc` — Load when checking a bulk RNA-seq count matrix for library-size outliers, gene detection rates, and sample-sample correlation before DE. Skip when data is raw FASTQ (use bulkrna-read-qc); aligner logs (use bulkrna-read-alignment); single-cell counts (use sc-qc).
  triggers: bulk QC, library size, count matrix, sample quality, gene detection, RNA-seq quality, count QC
- `bulkrna-read-alignment` — Load when summarising STAR / HISAT2 / Salmon alignment-rate logs in bulk RNA-seq. Skip when data is raw FASTQ (use bulkrna-read-qc); already counted (use bulkrna-qc); genome-DNA alignment (use genomics-alignment).
  triggers: RNA-seq alignment, STAR, HISAT2, Salmon, mapping rate, read alignment, alignment QC
- `bulkrna-read-qc` — Load when checking raw FASTQ quality (Phred / GC / adapter / Q20-Q30) before alignment in bulk RNA-seq. Skip when reads are already aligned (use bulkrna-read-alignment); counted (use bulkrna-qc); single-cell FASTQ (use sc-fastq-qc).
  triggers: FASTQ QC, read quality, Phred, FastQC, adapter, GC content, Q20, Q30
- `bulkrna-splicing` — Load when summarising rMATS / SUPPA2 alternative-splicing output and identifying significant differential splicing events. Skip when you only have count-level DE (use bulkrna-de); splicing in single-cell; spatial data (currently unsupported).
  triggers: alternative splicing, splicing analysis, PSI, rMATS, SUPPA2, exon skipping, differential splicing
- `bulkrna-survival` — Load when comparing bulk expression strata against clinical time-to-event data with Kaplan-Meier and log-rank tests. R survival also fits Cox HR; Python reports a descriptive events/person-time ratio. Skip missing clinical outcomes.
  triggers: survival, Kaplan-Meier, Cox, prognosis, hazard ratio, overall survival, clinical outcome
- `bulkrna-trajblend` — Load when placing bulk RNA-seq samples on a single-cell reference's pseudotime axis (NNLS deconvolution + nearest-neighbour mapping). Skip when plain cell-type proportions (use bulkrna-deconvolution); native single-cell trajectory inference (use sc-pseudotime).
  triggers: trajblend, trajectory, bulk to single cell, interpolation, bulk2single, VAE, deconvolution trajectory
