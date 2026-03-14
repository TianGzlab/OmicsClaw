<div align="center">
  <img src="docs/images/OmicsClaw_logo.jpeg" alt="OmicsClaw Logo" width="400"/>

  <h3>🧬 OmicsClaw</h3>
  <p><strong>Multi-omics analysis platform with 50+ specialized skills.</strong></p>
  <p>Spatial transcriptomics • Single-cell • Genomics • Proteomics • Metabolomics</p>
  <p><em>Local-first. Skill-based. Natural language routing. Modular. Reproducible.</em></p>
</div>

# OmicsClaw

> Multi-omics analysis platform with **50+ specialized skills** across spatial transcriptomics, single-cell, genomics, proteomics, and metabolomics. Command-line interface with natural language routing for complete analysis workflows.

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

**Key Features:**
- 🧬 **50+ analysis skills** across 5 omics domains with unified CLI
- 🔒 **Local-first processing** — your data never leaves your machine
- 🎯 **Smart orchestration** — natural language query routing with 3 modes (keyword/LLM/hybrid)
- 📦 **Modular dependencies** — install only what you need
- 🤖 **Bot integration** — Telegram and Feishu messaging interfaces
- 🧪 **Demo mode** — try any skill instantly with synthetic data

## Quick Start

```bash
# Clone and setup
git clone https://github.com/zhou-1314/OmicsClaw.git
cd OmicsClaw

# Create virtual environment (Python 3.11+ required)
python3.11 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install core dependencies
pip install -e .

# Try a demo
python omicsclaw.py run spatial-preprocessing --demo
```

**Installation tiers:**
- `pip install -e .` — Core install, all skills work with built-in methods
- `pip install -e ".[spatial]"` — Add advanced spatial methods (SpaGCN, STAGATE)
- `pip install -e ".[full]"` — All 50+ optional analysis methods

> 💡 Missing dependencies? You'll get clear `ImportError` messages with install instructions.

**See also:**
- [docs/INSTALLATION.md](docs/INSTALLATION.md) — Complete installation guide
- [docs/METHODS.md](docs/METHODS.md) — Algorithm reference and parameters

## Supported Domains

| Domain | Skills | Key Capabilities |
|--------|--------|------------------|
| **Spatial Transcriptomics** | 15 | QC, clustering, cell typing, deconvolution, spatial statistics, ligand-receptor, velocity, trajectory |
| **Single-Cell Omics** | 9 | Preprocessing, doublet detection, annotation, trajectory, batch integration, communication, DE, GRN, multiome |
| **Genomics** | 10 | VCF operations, variant calling, alignment, annotation, structural variants, assembly, phasing, CNV, epigenomics |
| **Proteomics** | 8 | MS QC, data import, peptide ID, quantification, differential abundance, PTM analysis, enrichment, structure |
| **Metabolomics** | 8 | Peak detection, XCMS preprocessing, annotation, normalization, statistical analysis, differential, pathway, quantification |
| **Orchestrator** | 1 | Natural language routing, multi-domain pipelines, file-type detection |

**Platforms supported:** Visium, Xenium, MERFISH, Slide-seq, 10x scRNA-seq, Illumina/PacBio sequencing, LC-MS/MS

> **Roadmap:** Expanding to transcriptomics, epigenomics, metagenomics, immunomics, and multi-omics integration domains.

## Skills Overview

### Spatial Transcriptomics (15 skills)

- **Foundation:** `spatial-preprocessing` — QC, normalization, clustering, UMAP
- **Analysis:** `spatial-domain-identification`, `spatial-cell-annotation`, `spatial-deconvolution`, `spatial-statistics`, `spatial-svg-detection`, `spatial-de`, `spatial-condition-comparison`
- **Advanced:** `spatial-cell-communication`, `spatial-velocity`, `spatial-trajectory`, `spatial-enrichment`, `spatial-cnv`
- **Integration:** `spatial-integration`, `spatial-registration`

<details>
<summary>View all spatial skills</summary>

| Skill | Description | Key Methods |
|-------|-------------|-------------|
| `spatial-preprocessing` | QC, normalization, HVG, PCA, UMAP, clustering | Scanpy, Squidpy |
| `spatial-domain-identification` | Tissue region / niche identification | SpaGCN, STAGATE, GraphST, Leiden |
| `spatial-cell-annotation` | Cell type annotation | Tangram, scANVI, CellAssign |
| `spatial-deconvolution` | Cell type proportion estimation | CARD, Cell2Location, RCTD |
| `spatial-statistics` | Spatial autocorrelation patterns | Moran's I, Geary's C, Ripley's K |
| `spatial-svg-detection` | Spatially variable genes | SpatialDE, SPARK-X |
| `spatial-de` | Differential expression | Wilcoxon, t-test, PyDESeq2 |
| `spatial-condition-comparison` | Condition comparison | Pseudobulk DESeq2 |
| `spatial-cell-communication` | Ligand-receptor interactions | LIANA+, CellPhoneDB |
| `spatial-velocity` | RNA velocity / cellular dynamics | scVelo, VeloVI |
| `spatial-trajectory` | Developmental trajectories | CellRank, Palantir, DPT |
| `spatial-enrichment` | Pathway enrichment | GSEA, ORA, Enrichr |
| `spatial-cnv` | Copy number variation | inferCNVpy, Numbat |
| `spatial-integration` | Multi-sample integration | Harmony, BBKNN, Scanorama |
| `spatial-registration` | Spatial registration | PASTE, STalign |

</details>

### Single-Cell Omics (9 skills)

`sc-preprocessing` • `sc-doublet-detection` • `sc-trajectory` • `sc-cell-annotation` • `sc-batch-integration` • `sc-de` • `sc-grn` • `sc-cell-communication` • `sc-multiome`

### Genomics (10 skills)

`genomics-vcf-operations` • `genomics-variant-calling` • `genomics-qc` • `genomics-alignment` • `genomics-variant-annotation` • `genomics-sv-detection` • `genomics-assembly` • `genomics-phasing` • `genomics-cnv-calling` • `genomics-epigenomics`

### Proteomics (8 skills)

`proteomics-ms-qc` • `proteomics-data-import` • `proteomics-identification` • `proteomics-quantification` • `proteomics-de` • `proteomics-ptm` • `proteomics-enrichment` • `proteomics-structural`

### Metabolomics (8 skills)

`metabolomics-peak-detection` • `metabolomics-xcms-preprocessing` • `metabolomics-annotation` • `metabolomics-normalization` • `metabolomics-de` • `metabolomics-pathway-enrichment` • `metabolomics-statistics` • `metabolomics-quantification`

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

## Testing

```bash
# Run all tests (uses demo mode, no external data needed)
make test

# Test specific domain
python -m pytest skills/spatial/ -v
python -m pytest skills/singlecell/ -v

# Test single skill
python -m pytest skills/spatial/spatial-preprocessing/tests/ -v

# Run tests requiring full dependencies
python -m pytest -m slow -v
```

All default tests complete in under 5 minutes using synthetic demo data.

## Bot Integration

OmicsClaw includes messaging bot interfaces for Telegram and Feishu (Lark):

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

**Features:**
- Natural language query routing to skills
- Multi-omics file upload support (`.h5ad`, `.vcf`, `.mzML`)
- Image recognition for tissue sections
- Automated report and figure delivery
- Rate limiting and audit logging

See [bot/README.md](bot/README.md) for detailed setup instructions.

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

**Questions?** Open an issue on [GitHub](https://github.com/OmicsClaw/OmicsClaw/issues)
