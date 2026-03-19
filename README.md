<div align="center">
  <img src="docs/images/OmicsClaw_logo.jpeg" alt="OmicsClaw Logo" width="400"/>

  <h3>🧬 OmicsClaw</h3>
  <p><strong>Your Persistent AI Research Partner for Multi-Omics Analysis</strong></p>
  <p>Remembers your data • Learns your preferences • Resumes your workflows</p>
  <p><em>Conversational. Memory-enabled. Local-first. Cross-platform.</em></p>
</div>

# OmicsClaw

> **AI research assistant that remembers.** OmicsClaw transforms multi-omics analysis from repetitive command execution into natural conversations with a persistent partner that tracks your datasets, learns your methods, and resumes interrupted workflows across sessions.

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![CI](https://img.shields.io/badge/CI-passing-brightgreen.svg)](https://github.com/TianGzlab/OmicsClaw/actions)

> [!WARNING]
> **🚧 项目开发中 / Under Active Development**
>
> OmicsClaw 目前正处于积极开发和完善阶段，部分功能可能存在 bug 或尚未完全稳定。我们正在持续改进代码质量、修复已知问题并增加新功能。如果您在使用过程中遇到任何问题，欢迎通过 [GitHub Issues](https://github.com/TianGzlab/OmicsClaw/issues) 反馈，我们会尽力修复和完善。感谢您的理解与支持！
>
> OmicsClaw is currently under active development. Some features may contain bugs or may not be fully stable yet. We are continuously improving code quality, fixing known issues, and adding new features. If you encounter any problems, please report them via [GitHub Issues](https://github.com/TianGzlab/OmicsClaw/issues). Thank you for your understanding and support!

<h3>⚡ Unified Control, Different Surfaces</h3>

<table>
  <tr>
    <th width="75%"><p align="center">🖥️ CLI / TUI</p></th>
    <th width="25%"><p align="center">📱 Mobile (Feishu)</p></th>
  </tr>
  <tr>
    <td align="center">
      <video src="docs/videos/OmicsClaw_CLI.mov" autoplay loop muted playsinline width="100%">
        <a href="docs/videos/OmicsClaw_CLI.mov">View CLI demo</a>
      </video>
    </td>
    <td align="center">
      <video src="docs/videos/Feishu_bot.MP4" width="100%" autoplay loop muted playsinline>
        <a href="docs/videos/Feishu_bot.MP4">View mobile demo</a>
      </video>
    </td>
  </tr>
</table>

## Why OmicsClaw?

**Traditional tools make you repeat yourself.** Every session starts from zero: re-upload data, re-explain context, re-run preprocessing. OmicsClaw remembers.

## ✨ Features
- **🧠 Persistent Memory** — Context, preferences, and analysis history survive across sessions.
- **🌐 Multi-Provider** — Anthropic, OpenAI, DeepSeek, or local LLMs — one config to switch.
- **📱 Multi-Channel** — CLI as the hub; Telegram, Feishu, and more — one agent session.
- **🔌 MCP & Skills** — Plug in MCP servers or install skills from GitHub on the fly.
- **🔄 Workflow Continuity** — Resume interrupted analyses, track lineage, and avoid redundant computation.
- **🔒 Privacy-First** — All processing is local; memory stores metadata only (no raw data uploads).
- **🎯 Smart Routing** — Natural language routed to the appropriate analysis automatically.
- **🧬 Multi-Omics Coverage** — 63+ predefined skills across spatial, single-cell, genomics, proteomics, metabolomics, and bulk RNA-seq.

**What makes it different:**

| Traditional Tools | OmicsClaw |
|-------------------|-----------|
| Re-upload data every session | Remembers file paths & metadata |
| Forget analysis history | Tracks full lineage (preprocess → cluster → DE) |
| Repeat parameters manually | Learns & applies your preferences |
| CLI-only, steep learning curve | Chat interface + CLI |
| Stateless execution | Persistent research partner |

> 📖 **Deep dive:** See [docs/MEMORY_SYSTEM.md](docs/MEMORY_SYSTEM.md) for detailed comparison of memory vs. stateless workflows.

## Quick Start

<details>
<summary> 🪛 Install uv (if you don't have it)</summary>

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

</details>

### Option 1: Chat Interface (Recommended)

```bash
# Clone and setup
git clone https://github.com/TianGzlab/OmicsClaw.git
cd OmicsClaw
pip install -e ".[tui]"
pip install -r bot/requirements.txt  # If you want Telegram/Feishu bots

# Configure (interactive setup wizard)
omicsclaw onboard  # or use short alias: oc onboard
# or manually edit .env

# Start the Interactive Terminal Chat (EvoSci-style TUI)
omicsclaw tui      # or: oc tui

# OR Start Telegram/Feishu bots as background channels
python -m bot.run
```

> 📖 **Bot Configuration Guide:** See [bot/README.md](bot/README.md) for detailed step-by-step instructions on obtaining API keys and configuring `.env` for Telegram/Feishu bots.

**Chat with your data:**
```
You: "Preprocess my Visium data"
Bot: ✅ [Runs QC, normalization, clustering]
     💾 [Remembers: visium_sample.h5ad, 5000 spots, normalized]

[Next day]
You: "Find spatial domains"
Bot: 🧠 "Using your Visium data from yesterday (5000 spots, normalized).
     Running domain detection..."
```

<details>
<summary>In-session commands (Interactive CLI/TUI)</summary>

| Command | Description |
| ------- | ----------- |
| `/skills [domain]` | List all skills (optionally filter by domain) |
| `/run <skill> [--demo] [--input <path>]` | Run a skill directly |
| `/sessions` | List recent sessions |
| `/resume [id]` | Resume a session (interactive picker if no ID) |
| `/delete <id>` | Delete a saved session |
| `/current` | Show current session info |
| `/new` | Start a new session |
| `/clear` | Clear conversation history |
| `/mcp list` | List MCP servers |
| `/mcp add <name> <cmd> [args]` | Add MCP server |
| `/mcp remove <name>` | Remove MCP server |
| `/config list` | View configuration |
| `/config set <key> <val>` | Update configuration |
| `/help` | Show all commands |
| `/exit` | Quit OmicsClaw |

</details>

<details>
<summary>In-bot commands (Telegram / Feishu)</summary>

| Command | Description |
| ------- | ----------- |
| `/start` | Welcome message with instructions |
| `/new` | Start new conversation (memory preserved) |
| `/clear` | Clear conversation history (memory preserved) |
| `/forget` | Clear conversation + memory (complete reset) |
| `/skills` | List all available OmicsClaw analysis skills |
| `/demo <skill>` | Run a skill demo |
| `/examples` | Show usage examples |
| `/files` | List data files |
| `/outputs` | Show recent analysis results |
| `/recent` | Show last 3 analyses |
| `/status` | Bot status and uptime |
| `/version` | Show version info |
| `/health` | System health check |
| `/help` | Show help message |

</details>

### Option 2: Command Line

```bash
# Install
pip install -e .

# Try a demo (no data needed)
python omicsclaw.py run spatial-preprocessing --demo

# Run with your data
python omicsclaw.py run spatial-preprocessing --input data.h5ad --output results/
```

**Installation tiers:**
- `pip install -e .` — Core system operations
- `pip install -e ".[<domain>]"` — Where `<domain>` is `spatial`, `singlecell`, `genomics`, `proteomics`, `metabolomics`, or `bulkrna`
- `pip install -e ".[spatial-domains]"` — Standalone Deep Learning Layer for `SpaGCN` and `STAGATE`
- `pip install -e ".[full]"` — All 63+ optional methods across all domains

*Check your installation status anytime with `python omicsclaw.py env`.*

> 📚 **Documentation:** [INSTALLATION.md](docs/INSTALLATION.md) • [METHODS.md](docs/METHODS.md) • [MEMORY_SYSTEM.md](docs/MEMORY_SYSTEM.md)

## Memory System — The Core Differentiator

OmicsClaw's memory system transforms it from a stateless tool into a persistent research partner.

**What it remembers:**
- 📁 **Datasets** — File paths, platforms (Visium/Xenium), dimensions, preprocessing state
- 📊 **Analyses** — Methods used, parameters, execution time, lineage (parent → child)
- ⚙️ **Preferences** — Your preferred clustering methods, plot styles, species defaults
- 🧬 **Insights** — Biological annotations (cluster = "T cells", domain = "tumor boundary")
- 🔬 **Project context** — Species, tissue type, disease model, research goals

**Real-world impact:**

| Without Memory | With Memory |
|----------------|-------------|
| Re-upload 2GB file every session | Zero re-uploads |
| "Which dataset?" every time | "Using your Visium data from yesterday" |
| Forget which parameters you used | "Applying leiden (resolution=0.8) as before" |
| Cannot resume interrupted work | Pick up exactly where you left off |
| No analysis lineage | Full tracking: preprocess → cluster → DE → enrichment |

> 📖 **Full comparison:** [docs/MEMORY_SYSTEM.md](docs/MEMORY_SYSTEM.md) — Detailed scenarios, privacy model, technical architecture

## Supported Domains

| Domain | Skills | Key Capabilities |
|--------|--------|------------------|
| **Spatial Transcriptomics** | 15 | QC, clustering, cell typing, deconvolution, spatial statistics, communication, velocity, trajectory |
| **Single-Cell Omics** | 9 | Preprocessing, doublet detection, annotation, trajectory, batch integration, DE, GRN |
| **Genomics** | 10 | Variant calling, alignment, annotation, structural variants, assembly, phasing, CNV |
| **Proteomics** | 8 | MS QC, peptide ID, quantification, differential abundance, PTM analysis |
| **Metabolomics** | 8 | Peak detection, XCMS preprocessing, annotation, normalization, statistical analysis |
| **Bulk RNA-seq** | 13 | FASTQ QC, read alignment, count matrix QC, gene ID mapping, batch correction, DE, splicing, enrichment, deconvolution, co-expression, PPI network, survival, trajectory interpolation |

**Platforms:** Visium, Xenium, MERFISH, Slide-seq, 10x scRNA-seq, Illumina/PacBio, LC-MS/MS, bulk RNA-seq (CSV/TSV)

> 📋 **Full skill catalog:** See [Skills Overview](#skills-overview) section below for complete list with methods

## Skills Overview

### Spatial Transcriptomics (15 skills)

- **Basic:** `spatial-preprocessing` — QC, normalization, clustering, UMAP
- **Analysis:** `spatial-domain-identification`, `spatial-cell-annotation`, `spatial-deconvolution`, `spatial-statistics`, `spatial-svg-detection`, `spatial-de`, `spatial-condition-comparison`
- **Advanced:** `spatial-cell-communication`, `spatial-velocity`, `spatial-trajectory`, `spatial-enrichment`, `spatial-cnv`
- **Integration:** `spatial-integration`, `spatial-registration`

<details>
<summary>View all spatial skills</summary>

| Skill | Description | Key Methods |
|-------|-------------|-------------|
| `spatial-preprocessing` | QC, normalization, HVG, PCA, UMAP, clustering | Scanpy |
| `spatial-domain-identification` | Tissue region / niche identification | Leiden, Louvain, SpaGCN, STAGATE, GraphST, BANKSY |
| `spatial-cell-annotation` | Cell type annotation | Marker-based (Scanpy), Tangram, scANVI, CellAssign |
| `spatial-deconvolution` | Cell type proportion estimation | FlashDeconv, Cell2location, RCTD, DestVI, Stereoscope, Tangram, SPOTlight, CARD |
| `spatial-statistics` | Spatial autocorrelation, network topology | Moran's I (Global/Local/Bivariate), Geary's C, Getis-Ord Gi*, Ripley's L, Co-occurrence, Centrality |
| `spatial-svg-detection` | Spatially variable genes | Moran's I, SpatialDE, SPARK-X, FlashS |
| `spatial-de` | Differential expression | Wilcoxon, t-test, PyDESeq2 |
| `spatial-condition-comparison` | Condition comparison | Pseudobulk DESeq2 |
| `spatial-cell-communication` | Ligand-receptor interactions | LIANA+, CellPhoneDB, FastCCC, CellChat |
| `spatial-velocity` | RNA velocity / cellular dynamics | scVelo, VELOVI |
| `spatial-trajectory` | Developmental trajectories | CellRank, Palantir, DPT |
| `spatial-enrichment` | Pathway enrichment | GSEA, ssGSEA, Enrichr |
| `spatial-cnv` | Copy number variation | inferCNVpy, Numbat |
| `spatial-integration` | Multi-sample integration | Harmony, BBKNN, Scanorama |
| `spatial-registration` | Spatial registration | PASTE |

</details>

### Single-Cell Omics (9 skills)

- **Basic:** `sc-preprocessing`, `sc-doublet-detection`
- **Analysis:** `sc-cell-annotation`, `sc-de`
- **Advanced:** `sc-trajectory`, `sc-grn`, `sc-cell-communication`
- **Integration:** `sc-batch-integration`, `sc-multiome`

<details>
<summary>View all single-cell skills</summary>

| Skill | Description | Key Methods |
|-------|-------------|-------------|
| `sc-preprocessing` | QC, normalization, HVG, PCA, UMAP | Scanpy, Seurat |
| `sc-doublet-detection` | Identify and remove doublets | Scrublet, DoubletFinder |
| `sc-cell-annotation` | Cell type annotation | CellTypist, SingleR |
| `sc-de` | Differential expression | Wilcoxon, MAST, DESeq2 |
| `sc-trajectory` | Pseudo-time & trajectory inference | Monocle3, Slingshot |
| `sc-grn` | Gene regulatory networks | SCENIC, CellOracle |
| `sc-cell-communication` | Ligand-receptor interactions | CellPhoneDB, CellChat |
| `sc-batch-integration` | Multi-sample integration | Harmony, scVI, Seurat v4 |
| `sc-multiome` | Multi-omics joint analysis | MOFA+, WNN |

</details>

### Genomics (10 skills)

- **Basic:** `genomics-qc`, `genomics-alignment`, `genomics-vcf-operations`
- **Analysis:** `genomics-variant-calling`, `genomics-variant-annotation`, `genomics-sv-detection`, `genomics-cnv-calling`
- **Advanced:** `genomics-assembly`, `genomics-phasing`, `genomics-epigenomics`

<details>
<summary>View all genomics skills</summary>

| Skill | Description | Key Methods / Metrics |
|-------|-------------|----------------------|
| `genomics-qc` | FASTQ quality control: Phred scores, GC/N content, Q20/Q30 rates, adapter detection | FastQC, fastp, MultiQC |
| `genomics-alignment` | Alignment statistics: MAPQ, mapping rate, insert size, duplicate rate (SAM flagstat) | BWA-MEM2, Bowtie2, Minimap2 |
| `genomics-vcf-operations` | VCF parsing, multi-allelic handling, Ti/Tv, QUAL/DP filtering | bcftools, GATK SelectVariants |
| `genomics-variant-calling` | Variant classification (SNP/MNP/INS/DEL/COMPLEX), Ti/Tv ratio, quality assessment | GATK HaplotypeCaller, DeepVariant, FreeBayes |
| `genomics-variant-annotation` | Functional impact prediction: VEP consequences, SIFT, PolyPhen-2, CADD scores | VEP, SnpEff, ANNOVAR |
| `genomics-sv-detection` | Structural variant calling (DEL/DUP/INV/TRA), BND notation, size classification | Manta, Delly, Lumpy, Sniffles |
| `genomics-cnv-calling` | Copy number variation: CBS segmentation, log2 ratio thresholds, 5-tier CN classification | CNVkit, Control-FREEC, GATK gCNV |
| `genomics-assembly` | Assembly quality: N50/N90/L50/L90 (QUAST-compatible), GC content, completeness | SPAdes, Megahit, Flye, Canu |
| `genomics-phasing` | Haplotype phasing: phase block N50, PS field parsing, phased fraction | WhatsHap, SHAPEIT5, Eagle2 |
| `genomics-epigenomics` | Peak analysis: narrowPeak/BED parsing, ENCODE QC, assay-specific metrics | MACS2/MACS3, Homer, Genrich |

</details>

### Proteomics (8 skills)

- **Basic:** `proteomics-data-import`, `proteomics-ms-qc`
- **Analysis:** `proteomics-identification`, `proteomics-quantification`, `proteomics-de`
- **Advanced:** `proteomics-ptm`, `proteomics-enrichment`, `proteomics-structural`

<details>
<summary>View all proteomics skills</summary>

| Skill | Description | Key Methods |
|-------|-------------|-------------|
| `proteomics-data-import` | RAW to open format conversion | ThermoRawFileParser, msconvert |
| `proteomics-ms-qc` | Mass spectrometry QC | PTXQC, rawtools |
| `proteomics-identification` | Peptide and protein ID | MaxQuant, MSFragger, Comet |
| `proteomics-quantification` | Label-free or isobaric quant | DIA-NN, Skyline, FlashLFQ |
| `proteomics-de` | Differential abundance analysis | MSstats, limma |
| `proteomics-ptm` | Post-translational modifications | PTM-prophet, MaxQuant |
| `proteomics-enrichment` | Protein pathway enrichment | Perseus, clusterProfiler |
| `proteomics-structural` | 3D structure & cross-linking | AlphaFold, xQuest |

</details>

### Metabolomics (8 skills)

- **Basic:** `metabolomics-peak-detection`, `metabolomics-xcms-preprocessing`, `metabolomics-normalization`
- **Analysis:** `metabolomics-annotation`, `metabolomics-quantification`, `metabolomics-statistics`, `metabolomics-de`
- **Advanced:** `metabolomics-pathway-enrichment`

<details>
<summary>View all metabolomics skills</summary>

| Skill | Description | Key Methods |
|-------|-------------|-------------|
| `metabolomics-peak-detection` | Peak detection with prominence/height/distance filtering | `scipy.signal.find_peaks`, peak widths |
| `metabolomics-xcms-preprocessing` | LC-MS/GC-MS peak picking, alignment & feature grouping | XCMS centWave (Python simulation) |
| `metabolomics-normalization` | Normalization & scaling (5 methods) | Median, Quantile (Bolstad 2003), TIC, PQN (Dieterle 2006), Log2 |
| `metabolomics-annotation` | Metabolite annotation with multi-adduct support | HMDB m/z matching, [M+H]⁺/[M-H]⁻/[M+Na]⁺ adducts |
| `metabolomics-quantification` | Feature quantification, imputation & normalization | Min/2, median, KNN imputation (`sklearn`); TIC/median/log norm |
| `metabolomics-statistics` | Univariate statistical testing with FDR correction | Welch's t-test, Wilcoxon, ANOVA, Kruskal-Wallis + BH FDR |
| `metabolomics-de` | Differential metabolite analysis with PCA | Welch's t-test + BH FDR, PCA visualization |
| `metabolomics-pathway-enrichment` | Pathway enrichment via over-representation analysis | Hypergeometric test (ORA), KEGG pathways, BH FDR |

</details>

### Bulk RNA-seq (13 skills)

- **Upstream QC:** `bulkrna-read-qc` — FASTQ quality assessment
- **Alignment:** `bulkrna-read-alignment` — STAR/HISAT2/Salmon mapping statistics
- **Count QC:** `bulkrna-qc` — library size, gene detection, sample correlation
- **Preprocessing:** `bulkrna-geneid-mapping`, `bulkrna-batch-correction`
- **Analysis:** `bulkrna-de`, `bulkrna-splicing`, `bulkrna-enrichment`, `bulkrna-survival`
- **Advanced:** `bulkrna-deconvolution`, `bulkrna-coexpression`, `bulkrna-ppi-network`, `bulkrna-trajblend`

<details>
<summary>View all bulk RNA-seq skills</summary>

| Skill | Description | Key Methods |
|-------|-------------|-------------|
| `bulkrna-read-qc` | FASTQ quality assessment — Phred scores, GC content, adapter detection | FastQC-style Python implementation |
| `bulkrna-read-alignment` | RNA-seq alignment statistics — mapping rate, composition, gene body coverage | STAR/HISAT2/Salmon log parsing |
| `bulkrna-qc` | Count matrix QC — library size, gene detection, sample correlation | pandas, matplotlib; MAD outlier detection |
| `bulkrna-geneid-mapping` | Gene ID conversion — Ensembl, Entrez, HGNC symbol mapping | mygene, built-in tables |
| `bulkrna-batch-correction` | Batch effect correction — ComBat parametric/non-parametric | Empirical Bayes, PCA assessment |
| `bulkrna-de` | Differential expression analysis | PyDESeq2, t-test fallback |
| `bulkrna-splicing` | Alternative splicing analysis — PSI, event detection | rMATS/SUPPA2 parsing, delta-PSI |
| `bulkrna-enrichment` | Pathway enrichment — ORA/GSEA | GSEApy, hypergeometric fallback |
| `bulkrna-deconvolution` | Cell type deconvolution from bulk | NNLS (scipy), CIBERSORTx bridge |
| `bulkrna-coexpression` | WGCNA-style co-expression network | Soft thresholding, hierarchical clustering, TOM |
| `bulkrna-ppi-network` | Protein-protein interaction network analysis | STRING API, graph centrality, hub genes |
| `bulkrna-survival` | Expression-based survival analysis | Kaplan-Meier, log-rank test, Cox PH |
| `bulkrna-trajblend` | Bulk→single-cell trajectory interpolation | NNLS deconvolution, PCA+KNN mapping, pseudotime |

</details>

### Orchestrator (1 skill)

`orchestrator` — Routes queries to appropriate skills, executes multi-step pipelines

## Usage

### Basic Commands

```bash
# List all available skills
python omicsclaw.py list

# List skills by domain
python omicsclaw.py list --domain spatial

# Run with demo data (no input file needed)
python omicsclaw.py run <skill> --demo

# Run with your data
python omicsclaw.py run <skill> --input <file> --output <dir>
```

> 💡 **Domain clarity**: When running skills, the CLI displays which omics domain the skill belongs to (e.g., "Running Spatial Transcriptomics skill: preprocess")

### Example Workflows

**Spatial transcriptomics analysis:**
```bash
# 1. Preprocess: QC, normalize, cluster
python omicsclaw.py run spatial-preprocessing --input data.h5ad --output output/spatial-preprocess

# 2. Identify tissue domains
python omicsclaw.py run spatial-domain-identification --input output/spatial-preprocess/processed.h5ad --output output/spatial-domains

# 3. Find svg genes
python omicsclaw.py run spatial-svg-detection --input output/spatial-domains/processed.h5ad --output output/spatial-svg-detection

# 4. Cell-cell communication
python omicsclaw.py run spatial-cell-communication --input output/spatial-preprocess/processed.h5ad --output output/spatial-cell-cell-communication
```

**Single-cell analysis:**
```bash
# 1. Preprocess: QC, normalize, cluster
python omicsclaw.py run sc-preprocessing --input pbmc.h5ad --output output/sc-preprocess

# 2. Doublet detection
python omicsclaw.py run sc-doublet-detection --input pbmc.h5ad --output output/sc-doublet

# 3. Cell annotation
python omicsclaw.py run sc-cell-annotation --input output/sc-preprocess/processed.h5ad --output output/sc-annotate
```

**Genomics — variant calling pipeline:**
```bash
# 1. Quality control
python omicsclaw.py run genomics-qc --input reads.fastq.gz --output output/genomics-qc

# 2. Alignment statistics
python omicsclaw.py run genomics-alignment --input aligned.sam --output output/genomics-alignment

# 3. Variant calling
python omicsclaw.py run genomics-variant-calling --demo --output output/genomics-variants

# 4. VCF operations (filter by quality)
python omicsclaw.py run genomics-vcf-operations --input variants.vcf --output output/vcf-ops --min-qual 30 --min-dp 10

# 5. Variant annotation
python omicsclaw.py run genomics-variant-annotation --demo --output output/genomics-annotation

# 6. CNV calling (with CBS segmentation)
python omicsclaw.py run genomics-cnv-calling --demo --output output/genomics-cnv

# 7. Assembly quality assessment
python omicsclaw.py run genomics-assembly --input contigs.fasta --output output/genomics-assembly --genome-size 5000000
```

**Metabolomics — LC-MS analysis pipeline:**
```bash
# 1. XCMS preprocessing (peak detection & alignment)
python omicsclaw.py run metabolomics-xcms-preprocessing --demo --output output/met-xcms

# 2. Normalization (PQN with median reference spectrum)
python omicsclaw.py run metabolomics-normalization --input output/met-xcms/tables/peak_table.csv --output output/met-norm --method pqn

# 3. Quantification with KNN imputation
python omicsclaw.py run metabolomics-quantification --input output/met-norm/tables/normalized.csv --output output/met-quant --impute knn

# 4. Statistical analysis (Welch's t-test + BH FDR)
python omicsclaw.py run metabolomics-statistics --input output/met-quant/tables/quantified_features.csv --output output/met-stats --method ttest

# 5. Pathway enrichment (hypergeometric ORA)
python omicsclaw.py run metabolomics-pathway-enrichment --input output/met-stats/tables/significant.csv --output output/met-pathway
```

**(TODO) Bulk RNA-seq — full pipeline (FASTQ → downstream):**
```bash
# 1. FASTQ quality assessment
python omicsclaw.py run bulkrna-read-qc --input reads.fastq.gz --output output/bulk-fastqc

# 2. Alignment QC (parse STAR/HISAT2/Salmon logs)
python omicsclaw.py run bulkrna-read-alignment --input Log.final.out --output output/bulk-align

# 3. Count matrix QC (library size, gene detection, sample correlation)
python omicsclaw.py run bulkrna-qc --input counts.csv --output output/bulk-qc

# 4. Gene ID mapping (Ensembl → HGNC symbol)
python omicsclaw.py run bulkrna-geneid-mapping --input counts.csv --from ensembl --to symbol --output output/bulk-geneid

# 5. Batch correction (ComBat)
python omicsclaw.py run bulkrna-batch-correction --input counts.csv --batch-info batches.csv --output output/bulk-combat

# 6. Differential expression (PyDESeq2 or t-test fallback)
python omicsclaw.py run bulkrna-de --input counts.csv --output output/bulk-de \
  --control-prefix ctrl --treat-prefix treat

# 7. Pathway enrichment (ORA with hypergeometric test)
python omicsclaw.py run bulkrna-enrichment --input output/bulk-de/tables/de_results.csv --output output/bulk-enrich

# 8. Cell type deconvolution (NNLS)
python omicsclaw.py run bulkrna-deconvolution --input counts.csv --output output/bulk-deconv

# 9. Co-expression network analysis (WGCNA-style)
python omicsclaw.py run bulkrna-coexpression --input counts.csv --output output/bulk-wgcna

# 10. PPI network (hub gene identification)
python omicsclaw.py run bulkrna-ppi-network --input output/bulk-de/tables/de_results.csv --output output/bulk-ppi

# 11. Survival analysis (Kaplan-Meier + log-rank)
python omicsclaw.py run bulkrna-survival --input counts.csv --clinical clinical.csv --genes TP53,BRCA1,KRAS --output output/bulk-survival

# 12. Trajectory interpolation (Bulk→single-cell)
python omicsclaw.py run bulkrna-trajblend --input counts.csv --reference scref.h5ad --output output/bulk-traj
```

### Smart Orchestration

The orchestrator automatically routes queries and files to the right analysis:

**Natural language routing:**
```bash
python omicsclaw.py run orchestrator \
  --query "find spatially variable genes" \
  --input data.h5ad --output output
```

**Routing modes** (choose based on query complexity):
```bash
# Keyword mode (default) - fast pattern matching
python omicsclaw.py run orchestrator \
  --query "find spatially variable genes" \
  --routing-mode keyword --output output

# LLM mode - AI-powered semantic understanding
python omicsclaw.py run orchestrator \
  --query "I want to understand which genes show spatial patterns" \
  --routing-mode llm --output output

# Hybrid mode - combines keyword + LLM fallback
python omicsclaw.py run orchestrator \
  --query "analyze cell-cell interactions" \
  --routing-mode hybrid --output output
```

**Named pipelines:**
```bash
# Standard spatial: preprocess → domains → de → genes → statistics
python omicsclaw.py run orchestrator --pipeline standard --input data.h5ad --output output

# Full spatial: adds communication + enrichment
python omicsclaw.py run orchestrator --pipeline full --input data.h5ad --output output

# Single-cell: sc-preprocess → sc-doublet → sc-annotate → sc-trajectory
python omicsclaw.py run orchestrator --pipeline singlecell --input data.h5ad --output output

# Cancer analysis: preprocess → domains → de → cnv → enrichment
python omicsclaw.py run orchestrator --pipeline cancer --input data.h5ad --output output
```

## Output Structure

Every skill generates standardized output:

```
output_dir/
├── report.md              # Human-readable analysis report
├── result.json            # Machine-readable structured results
├── processed.h5ad         # Updated data (spatial/single-cell skills)
├── figures/               # Visualizations (PNG/SVG)
├── tables/                # Result tables (CSV)
└── reproducibility/       # Version info, run command
```

## Architecture

OmicsClaw uses a modular, domain-organized structure:

```
OmicsClaw/
├── omicsclaw.py              # Main CLI entrypoint
├── omicsclaw/                # Core utilities package
│   ├── core/                 # Registry, skill discovery, session management
│   ├── routing/              # Query routing and orchestration logic
│   ├── loaders/              # Unified data loading across domains
│   ├── common/               # Shared utilities (reports, checksums)
│   ├── spatial/              # Spatial transcriptomics utilities
│   ├── singlecell/           # Single-cell omics utilities
│   ├── genomics/             # Genomics utilities
│   ├── proteomics/           # Proteomics utilities
│   ├── metabolomics/         # Metabolomics utilities
│   └── bulkrna/              # Bulk RNA-seq utilities
├── skills/                   # Self-contained analysis modules
│   ├── spatial/              # 15 spatial transcriptomics skills
│   ├── singlecell/           # 9 single-cell omics skills
│   ├── genomics/             # 10 genomics skills
│   ├── proteomics/           # 8 proteomics skills
│   ├── metabolomics/         # 8 metabolomics skills
│   ├── bulkrna/              # 13 bulk RNA-seq skills
│   └── orchestrator/         # Multi-domain routing
├── bot/                      # Telegram + Feishu messaging interfaces
├── docs/                     # Documentation (installation, methods, architecture)
├── examples/                 # Example datasets
├── scripts/                  # Utility scripts (catalog generation, etc.)
├── templates/                # Report and output templates
├── tests/                    # Integration tests
└── sessions/                 # Session storage for workflow state
```

**Each skill is self-contained:**
```
skills/<domain>/<skill>/
├── SKILL.md                  # Methodology specification
├── <skill_script>.py         # CLI implementation
└── tests/                    # Unit and integration tests
```

Skills communicate via standardized formats (`.h5ad`, `.vcf`, `.mzML`, `.csv`) and can be chained into pipelines.

## 📱 Channels Integration — Memory-Enabled Conversational Interface

OmicsClaw includes messaging bot interfaces with **persistent memory**. Connect messaging platforms so they share the same agent session as the CLI. Currently supported channels include Telegram, Feishu (Lark), DingTalk, Discord, Slack, WeChat, QQ, Email, and iMessage.

```bash
# Install core bot dependencies
pip install -r bot/requirements.txt
# Or install dependencies for all channels:
pip install -r bot/requirements-channels.txt

# Configure (create .env file with API keys from .env.example)
cp .env.example .env

# Start your selected channels concurrently (Unified Runner)
python -m bot.run --channels telegram,feishu,slack
# Or start via short alias
make bot-multi CHANNELS=telegram,discord
```

**Key Features:**
- 🧠 **Persistent memory** — Remembers datasets, analyses, preferences across sessions
- 💬 **Natural language** — "Find spatial domains" → automatic skill routing
- 📁 **Multi-omics upload** — Supports `.h5ad`, `.vcf`, `.mzML`, `.csv`/`.tsv` files
- 📊 **Auto-delivery** — Reports and figures sent directly to chat
- 🔒 **Privacy-first** — Local processing, metadata-only storage

> [!TIP]
> For per-channel setup guides, capability matrix, and architecture details, see the **[Channel Integration Guide](bot/README.md)**.
> See **[docs/MEMORY_SYSTEM.md](docs/MEMORY_SYSTEM.md)** for memory architecture.

## Contributing

Contributions are welcome! To add a new skill:

1. Create skill directory: `skills/<domain>/<skill-name>/`
2. Add `SKILL.md` with methodology specification
3. Implement `<skill_name>.py` with CLI interface
4. Add tests in `tests/` directory
5. Run `python scripts/generate_catalog.py` to update registry

See [AGENTS.md](AGENTS.md) for detailed development guidelines.

## Documentation

- [docs/INSTALLATION.md](docs/INSTALLATION.md) — Installation guide with dependency tiers
- [docs/METHODS.md](docs/METHODS.md) — Algorithm reference and parameters
- [docs/architecture.md](docs/architecture.md) — System design and patterns
- [CLAUDE.md](CLAUDE.md) — AI agent instructions for skill routing
- [bot/README.md](bot/README.md) — Bot setup and configuration

## Safety & Disclaimer

- **Local-first processing** — All data stays on your machine
- **Research use only** — Not a medical device, does not provide clinical diagnoses
- **Consult domain experts** — Verify results before making decisions

## License

MIT License - see [LICENSE](LICENSE) for details.

## Citation

If you use OmicsClaw in your research, please cite:

```bibtex
@software{omicsclaw2026,
  title = {OmicsClaw: A Memory-Enabled AI Agent for Multi-Omics Analysis},
  author = {Zhou, Weige and Chen, Liying and Yin, Pengfei and Tian, Luyi},
  year = {2026},
  url = {https://github.com/TianGzlab/OmicsClaw}
}
```

## Acknowledgments

OmicsClaw is built upon the inspiration and contributions of the following outstanding open-source projects:

- **[ClawBio](https://github.com/ClawBio/ClawBio)** — The first bioinformatics-native AI agent skill library. OmicsClaw's skill architecture, local-first philosophy, reproducibility design, and bot integration patterns are deeply inspired by ClawBio. Thank you to the ClawBio team for their pioneering work!
- **[Nocturne Memory](https://github.com/Dataojitori/nocturne_memory)** — A lightweight, rollbackable long-term memory server for MCP agents. OmicsClaw's persistent memory system draws on Nocturne Memory's graph-structured memory architecture and MCP protocol integration, enabling the bot to remember datasets, analysis history, and user preferences across sessions.

## Contact

- **Luyi Tian** (Principal Investigator) — [tian_luyi@gzlab.ac.cn](mailto:tian_luyi@gzlab.ac.cn)
- **Weige Zhou** (Lead Developer) — [GitHub](https://github.com/zhou-1314)
- **Liying Chen** (Developer) — [GitHub](https://github.com/chenly255)
- **Pengfei Yin** (Developer) — [GitHub](https://github.com/astudentfromsustech)

For bug reports and feature requests, please open an issue on [GitHub](https://github.com/TianGzlab/OmicsClaw/issues).
