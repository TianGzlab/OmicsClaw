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
[![CI](https://img.shields.io/badge/CI-passing-brightgreen.svg)](https://github.com/zhou-1314/OmicsClaw/actions)

## Why OmicsClaw?

**Traditional tools make you repeat yourself.** Every session starts from zero: re-upload data, re-explain context, re-run preprocessing. OmicsClaw remembers.

**Core Value:**
- 🧠 **Memory system** — Remembers your datasets, analysis history, and preferences across sessions
- 💬 **Conversational interface** — Chat with your data via Telegram/Feishu, no command-line needed
- 🔄 **Workflow continuity** — Resume interrupted analyses, track lineage, avoid redundant computation
- 🔒 **Privacy-first** — All processing local, memory stores metadata only (no raw data)
- 🎯 **Smart routing** — Natural language → appropriate analysis automatically
- 🧬 **Multi-omics coverage** — 50+ skills across spatial, single-cell, genomics, proteomics, metabolomics

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

### Option 1: Chat Interface (Recommended)

```bash
# Clone and setup
git clone https://github.com/zhou-1314/OmicsClaw.git
cd OmicsClaw
pip install -e .
pip install -r bot/requirements.txt

# Configure (add your LLM API key)
cp .env.example .env
# Edit .env: set LLM_API_KEY and bot tokens

# Start Telegram bot
python bot/telegram_bot.py

# Or start Feishu bot (no public IP needed)
python bot/feishu_bot.py
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
- `pip install -e ".[<domain>]"` — Where `<domain>` is `spatial`, `singlecell`, `genomics`, `proteomics`, or `metabolomics`
- `pip install -e ".[spatial-domains]"` — Standalone Deep Learning Layer for `SpaGCN` and `STAGATE`
- `pip install -e ".[full]"` — All 50+ optional methods across all domains

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

**Platforms:** Visium, Xenium, MERFISH, Slide-seq, 10x scRNA-seq, Illumina/PacBio, LC-MS/MS

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
| `spatial-preprocess` | QC, normalization, HVG, PCA, UMAP, clustering | Scanpy |
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
| `spatial-integrate` | Multi-sample integration | Harmony, BBKNN, Scanorama |
| `spatial-register` | Spatial registration | PASTE |

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

| Skill | Description | Key Methods |
|-------|-------------|-------------|
| `genomics-qc` | Sequencing quality control | FastQC, MultiQC |
| `genomics-alignment` | Read mapping & alignment | BWA, Bowtie2, STAR |
| `genomics-vcf-operations` | VCF filtering and manipulation | bcftools, GATK |
| `genomics-variant-calling` | SNV and INDEL calling | GATK HaplotypeCaller, FreeBayes |
| `genomics-variant-annotation` | Annotate variants with effects | SnpEff, VEP |
| `genomics-sv-detection` | Structural variant detection | Delly, Manta, Lumpy |
| `genomics-cnv-calling` | Copy number variation calling | CNVkit, Control-FREEC |
| `genomics-assembly` | De novo genome assembly | SPAdes, Megahit |
| `genomics-phasing` | Haplotype phasing | SHAPEIT, Whatshap |
| `genomics-epigenomics` | ATAC-seq/ChIP-seq analysis | MACS2, HOMER |

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
| `metabolomics-peak-detection` | Extract peaks from MS data | XCMS, MZmine |
| `metabolomics-xcms-preprocessing` | Alignment & feature grouping | XCMS |
| `metabolomics-normalization` | Signal drift correction | NOREVA, MetaboAnalyst |
| `metabolomics-annotation` | Metabolite ID & adduct matching | MS-DIAL, SIRIUS |
| `metabolomics-quantification` | Feature quantification | OpenMS, XCMS |
| `metabolomics-statistics` | Multivariate statistics | MetaboAnalyst, ropls |
| `metabolomics-de` | Differential metabolite analysis | t-test, ANOVA |
| `metabolomics-pathway-enrichment` | Pathway and network analysis | MSEA, MetaboAnalyst |

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

**Genomics:**
```bash
python omicsclaw.py run genomics-vcf-operations --input variants.vcf.gz --output output/vcf-ops
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

**File-type detection:**
```bash
# Automatically detects file type and runs appropriate preprocessing
python omicsclaw.py run orchestrator --input data.h5ad --output output
python omicsclaw.py run orchestrator --input variants.vcf.gz --output output
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
├── processed.h5ad         # Updated data (if applicable)
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
│   └── metabolomics/         # Metabolomics utilities
├── skills/                   # Self-contained analysis modules
│   ├── spatial/              # 15 spatial transcriptomics skills
│   ├── singlecell/           # 9 single-cell omics skills
│   ├── genomics/             # 10 genomics skills
│   ├── proteomics/           # 8 proteomics skills
│   ├── metabolomics/         # 8 metabolomics skills
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

Skills communicate via standardized formats (`.h5ad`, `.vcf`, `.mzML`) and can be chained into pipelines.

## Bot Integration — Memory-Enabled Conversational Interface

OmicsClaw includes messaging bot interfaces with **persistent memory** for Telegram and Feishu (Lark).

```bash
# Install bot dependencies
pip install -r bot/requirements.txt

# Configure (create .env file with API keys)
cp .env.example .env
# Edit .env with your LLM_API_KEY, TELEGRAM_BOT_TOKEN, FEISHU_APP_ID, etc.

# Start bots
python bot/telegram_bot.py    # Telegram
python bot/feishu_bot.py      # Feishu (WebSocket, no public IP needed)
```

**Key Features:**
- 🧠 **Persistent memory** — Remembers datasets, analyses, preferences across sessions
- 💬 **Natural language** — "Find spatial domains" → automatic skill routing
- 📁 **Multi-omics upload** — Supports `.h5ad`, `.vcf`, `.mzML` files
- 🖼️ **Image recognition** — Analyzes tissue section photos (H&E, fluorescence)
- 📊 **Auto-delivery** — Reports and figures sent directly to chat
- 🔒 **Privacy-first** — Local processing, metadata-only storage

**Memory in action:**
```
Session 1:
You: [Upload visium_brain.h5ad]
You: "Preprocess this"
Bot: ✅ Done. [Saves DatasetMemory + AnalysisMemory]

Session 2 (next day):
You: "Find spatial domains"
Bot: 🧠 "Using your Visium brain data (5000 spots, normalized yesterday)"
     ✅ Done. [Links to parent analysis]

Session 3:
You: "Use the same clustering as before"
Bot: 🧠 "Applying leiden (resolution=0.8) from your previous analysis"
```

See [bot/README.md](bot/README.md) for detailed setup and [docs/MEMORY_SYSTEM.md](docs/MEMORY_SYSTEM.md) for memory architecture.

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
  title = {OmicsClaw: Multi-omics Analysis Platform},
  author = {Zhou weige},
  year = {2026},
  url = {https://github.com/zhou-1314/OmicsClaw}
}
```

---

**Questions?** Open an issue on [GitHub](https://github.com/zhou-1314/OmicsClaw/issues)
