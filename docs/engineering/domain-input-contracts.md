# Domain Input Contracts

This document records the current input contract for each registered OmicsClaw
domain. It is intentionally factual: when a domain does not yet have one shared
loader, the contract names the current per-skill entrypoints instead of
pretending a unified loader exists.

Runtime extension detection lives in `omicsclaw/loaders/__init__.py`. Actual
analysis loading usually lives under `skills/<domain>/`.

## spatial

**Supported suffixes**: `.h5ad`, `.h5`, `.hdf5`, `.zarr`, 10x Visium
directories, and spatial raw FASTQ inputs for the raw-processing skill.

**Real loader / entrypoint**: `skills/spatial/_lib/loader.py` exposes
`load_spatial_data()` for Visium, Xenium, Slide-seq, MERFISH, seqFISH, and
generic AnnData. Raw FASTQ handoff is described in
`skills/spatial/_lib/raw_processing_contract.py`.

**Minimum fields**: AnnData must have observations and variables with unique
`var_names`. Most downstream spatial skills expect `.obsm["spatial"]` when
spatial coordinates are needed; raw-processing outputs also record QC columns
such as total counts and detected genes.

**Downstream conventions**: `spatial-preprocess` is the preferred handoff into
analysis skills. Downstream-ready outputs use `processed.h5ad`, keep counts in a
stable matrix/layer contract where available, and place runner-owned
`README.md` plus notebooks at the output root.

## singlecell

**Supported suffixes**: `.h5ad`, `.h5`, `.loom`, `.mtx`, `.csv`, `.tsv`, and
FASTQ/counting outputs for upstream counting skills.

**Real loader / entrypoint**: `skills/singlecell/_lib/io.py` contains 10x H5,
10x MTX, and CSV/TSV count import helpers. Runtime validation and user-facing
preflight checks live in `skills/singlecell/_lib/preflight.py`.

**Minimum fields**: AnnData must have cell observations, gene variables, and a
matrix whose meaning is declared or inferable. Skills that need clustering,
batch integration, cell types, perturbation labels, or sample-aware DE require
the relevant `.obs` columns. Velocity requires spliced/unspliced layers.

**Downstream conventions**: `sc-standardize-input`, `sc-qc`,
`sc-filter`, and `sc-preprocessing` establish matrix and preprocessing state.
Shared helpers in `skills/singlecell/_lib/adata_utils.py` record
`omicsclaw_input_contract` and matrix contracts for downstream checks.

## genomics

**Supported suffixes**: `.fastq`, `.fastq.gz`, `.fq`, `.fq.gz`, `.bam`,
`.cram`, `.sam`, `.vcf`, `.vcf.gz`, `.bed`, `.fasta`, `.fa`, and tabular CSV
inputs for demo or summarized workflows.

**Real loader / entrypoint**: There is no unified genomics loader yet.
Each skill script under `skills/genomics/<skill>/` parses its own input format,
for example `skills/genomics/genomics-qc/genomics_qc.py`,
`skills/genomics/genomics-alignment/genomics_alignment.py`, and
`skills/genomics/genomics-vcf-operations/genomics_vcf_operations.py`.

**Minimum fields**: FASTQ skills require sequence/quality records; alignment
skills require SAM/BAM-like alignment records or summaries; variant skills
require VCF-like fields such as chromosome, position, reference, alternate, and
quality/info when applicable.

**Downstream conventions**: Genomics outputs are tabular summaries, VCF-derived
tables, figures, `report.md`, and `result.json`. No AnnData/h5ad handoff is
assumed for this domain.

## proteomics

**Supported suffixes**: `.mzML`, `.mzXML`, `.csv`, `.tsv`, and common search or
quantification exports from MaxQuant, DIA-NN, Spectronaut, Skyline, or generic
tables.

**Real loader / entrypoint**: There is no unified proteomics loader yet.
Per-skill readers live in scripts such as
`skills/proteomics/proteomics-data-import/proteomics_data_import.py`,
`skills/proteomics/proteomics-identification/proteomics_identification.py`, and
`skills/proteomics/proteomics-quantification/proteomics_quantification.py`.

**Minimum fields**: Tabular inputs must include peptide, protein, intensity, or
sample columns appropriate to the selected skill. Raw MS quality-control paths
need MS file metadata or compatible tabular summaries.

**Downstream conventions**: Proteomics skills emit native tabular artifacts,
figures, `report.md`, and `result.json`. They do not produce h5ad handoff
artifacts.

## metabolomics

**Supported suffixes**: `.mzML`, `.mzXML`, `.cdf`, `.csv`, `.tsv`, and peak or
feature tables.

**Real loader / entrypoint**: There is no unified metabolomics loader yet.
Per-skill loading lives in scripts such as
`skills/metabolomics/metabolomics-peak-detection/peak_detect.py`,
`skills/metabolomics/metabolomics-annotation/metabolomics_annotation.py`, and
`skills/metabolomics/metabolomics-statistics/metabolomics_statistics.py`.

**Minimum fields**: Feature-table workflows need metabolite or feature IDs,
sample intensity columns, and optional group/condition metadata. Annotation and
pathway skills need mass/feature identifiers or pathway-compatible metabolite
names where applicable.

**Downstream conventions**: Metabolomics outputs are native tables, figures,
`report.md`, and `result.json`. No AnnData/h5ad convention is assumed.

## bulkrna

**Supported suffixes**: `.csv`, `.tsv`, `.fastq`, `.fastq.gz`, `.fq`, `.fq.gz`,
`.bam`, and alignment/count summary files depending on the skill.

**Real loader / entrypoint**: There is no unified Bulk RNA loader yet. Skills
under `skills/bulkrna/<skill>/` use their own pandas/CLI parsing paths, for
example `skills/bulkrna/bulkrna-de/bulkrna_de.py`,
`skills/bulkrna/bulkrna-qc/bulkrna_qc.py`, and
`skills/bulkrna/bulkrna-survival/bulkrna_survival.py`.

**Minimum fields**: Count-matrix skills expect genes and sample columns.
Differential expression requires identifiable control/treatment samples or
explicit prefix flags. Survival requires an expression matrix plus clinical
metadata when not using demo mode.

**Downstream conventions**: Bulk RNA skills emit CSV/TSV summaries, figures,
`report.md`, and `result.json`. No h5ad handoff is assumed except for bridge
skills such as bulk-to-single-cell interpolation when a reference is supplied.

## orchestrator

**Supported suffixes**: `*` for routing queries, plus any input file suffix that
can be routed to another domain.

**Real loader / entrypoint**: `skills/orchestrator/omics_orchestrator.py`
accepts `--query`, `--input`, `--routing-mode`, and `--demo`. It relies on
registry metadata and lightweight extension/domain detection rather than
loading full analysis matrices.

**Minimum fields**: A natural-language query, an input path, or demo mode is
required. The orchestrator needs enough intent or file type information to
select a downstream skill.

**Downstream conventions**: The orchestrator returns routing decisions and
pipeline plans. Actual data contracts are delegated to the chosen downstream
domain skill.

## literature

**Supported suffixes**: `.pdf`, `.txt`, DOI strings, PubMed IDs, URLs, and free
text snippets.

**Real loader / entrypoint**: `skills/literature/literature_parse.py` parses
text/PDF/URL/identifier inputs and extracts metadata such as GEO accessions.

**Minimum fields**: A readable paper, identifier, URL, or text snippet is
required. GEO extraction depends on recognizable accession-like text.

**Downstream conventions**: Literature outputs are metadata JSON, a human
report, and extracted accession summaries. It does not create analysis-ready
omics matrices by itself; downstream data download/analysis must be routed
separately.
