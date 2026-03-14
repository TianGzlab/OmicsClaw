# AGENTS.md — OmicsClaw Guide for AI Coding Agents

This guide is for AI coding agents working on the OmicsClaw codebase.

## Project Overview

OmicsClaw is a multi-omics analysis platform supporting 5 domains: spatial transcriptomics, single-cell omics, genomics, proteomics, and metabolomics. Each skill is a self-contained module that performs a specific analysis task via CLI or Python API. All processing is local-first. Design is inspired by [ClawBio](https://github.com/ClawBio/ClawBio).

**Note**: OmicsClaw evolved from SpatialClaw and now uses a unified `omicsclaw.py` entrypoint.

## Setup

```bash
cd /data1/TianLab/zhouwg/project/OmicsClaw
pip install -r requirements.txt
python omicsclaw.py list
python omicsclaw.py run spatial-preprocessing --demo
```

## Commands

| Command | Purpose |
|---------|---------|
| `python omicsclaw.py list` | List all 50+ skills across 5 domains |
| `python omicsclaw.py run <skill> --demo` | Run a skill with demo data |
| `python omicsclaw.py run <skill> --input <file> --output <dir>` | Run with user data |
| `python -m pytest -v` | Run all tests |
| `make test` | Alias for pytest |
| `make demo` | Run preprocess demo |
| `make bot-telegram` | Start Telegram bot |
| `make bot-feishu` | Start Feishu bot |

## Project Structure

```
OmicsClaw/
├── omicsclaw.py                # Main CLI runner (SKILLS dict, DOMAINS registry)
├── omicsclaw/                  # Shared utilities package
│   ├── common/                 # report.py, session.py, checksums.py
│   ├── spatial/                # loader.py, adata_utils.py, viz_utils.py
│   └── loaders/                # Unified data loading (load_omics_data)
├── skills/                     # Domain-organized skill directories
│   ├── spatial/                # 15 spatial transcriptomics skills
│   │   ├── spatial-preprocess/ # QC + normalization + embedding
│   │   ├── spatial-domains/    # Tissue region identification
│   │   ├── spatial-annotate/   # Cell type annotation
│   │   └── ...
│   ├── singlecell/             # 9 single-cell omics skills
│   │   ├── sc-preprocessing/   # scRNA-seq QC + normalization
│   │   ├── sc-doublet-detection/ # Doublet removal
│   │   └── ...
│   ├── genomics/               # 10 genomics skills
│   │   ├── genomics-vcf-ops/   # VCF operations
│   │   ├── genomics-variant-calling/ # Variant calling
│   │   └── ...
│   ├── proteomics/             # 8 proteomics skills
│   │   ├── proteomics-ms-qc/   # MS quality control
│   │   ├── proteomics-peptide-id/ # Peptide identification
│   │   └── ...
│   ├── metabolomics/           # 8 metabolomics skills
│   │   ├── peak-detection/     # Peak detection
│   │   ├── xcms-preprocess/    # XCMS preprocessing
│   │   └── ...
│   └── orchestrator/           # Multi-domain routing
│   ├── spatial-trajectory/     # Trajectory inference
│   ├── spatial-enrichment/     # Pathway enrichment
│   ├── spatial-cnv/            # Copy number variation
│   ├── spatial-integrate/      # Multi-sample integration
│   ├── spatial-register/       # Spatial registration
│   ├── spatial-orchestrator/   # Query routing
│   └── catalog.json            # Auto-generated skill index
├── bot/                        # Messaging bot frontends
│   ├── core.py                 # Shared LLM engine + tool loop + security
│   ├── telegram_bot.py         # Telegram frontend
│   ├── feishu_bot.py           # Feishu (Lark) frontend
│   ├── requirements.txt        # Bot-specific dependencies
│   ├── README.md               # Bot setup guide
│   └── logs/                   # Audit logs (auto-created)
├── SOUL.md                     # Bot persona (RoboTerri)
├── templates/SKILL-TEMPLATE.md # Template for new skills
├── examples/                   # Shared demo data
├── sessions/                   # SpatialSession JSONs
├── CLAUDE.md                   # Agent routing instructions
└── AGENTS.md                   # This file
```

## Skill Architecture

Every skill has a `SKILL.md` with YAML frontmatter + methodology, a Python script accepting `--input`, `--output`, `--demo`, and optionally `tests/` and `data/`.

Skills are registered in `omicsclaw/core/registry.py` and dynamically discovered from `skills/`.

## How to Add a New Skill

1. `mkdir skills/<your-skill-name>`
2. `cp templates/SKILL-TEMPLATE.md skills/<your-skill-name>/SKILL.md`
3. Fill in SKILL.md
4. Add Python script accepting `--input`, `--output`, `--demo`
5. Add tests in `tests/`
6. Register stable aliases in `omicsclaw/core/registry.py` (or rely on dynamic discovery)
7. Add test path to `pytest.ini`
8. Regenerate catalog: `python scripts/generate_catalog.py`

## Bot Integration

OmicsClaw includes dual-channel messaging bots in `bot/`:

```
bot/
├── __init__.py
├── core.py           # Shared LLM tool loop, skill execution, security
├── telegram_bot.py   # Telegram frontend (python-telegram-bot)
├── feishu_bot.py     # Feishu frontend (lark-oapi WebSocket)
├── requirements.txt  # Bot-specific dependencies
├── README.md         # Setup and configuration guide
└── logs/             # Audit logs (audit.jsonl)
```

### Bot Commands

| Command | Purpose |
|---------|---------|
| `python bot/telegram_bot.py` | Start Telegram bot |
| `python bot/feishu_bot.py` | Start Feishu bot |
| `make bot-telegram` | Makefile alias for Telegram |
| `make bot-feishu` | Makefile alias for Feishu |

### Bot Architecture

Both bots share `bot/core.py` which contains:
- LLM tool-use loop (OpenAI function calling)
- TOOLS definition (omicsclaw, save_file, write_file, generate_audio)
- `execute_omicsclaw()` — runs `omicsclaw.py run <skill>` as subprocess
- Security helpers (path sanitization, file size limits)
- Audit logging (JSONL)

The persona is defined in `SOUL.md` (RoboTerri, based on Professor Teresa K. Attwood).

### Configuration

Bot environment variables go in `.env` at the project root. See `bot/README.md` for the full list.

## Bot Integration

OmicsClaw includes Telegram and Feishu bot frontends in `bot/`. Both import `bot/core.py` which provides the shared LLM tool-use loop, skill execution, security helpers, and audit logging. Each frontend handles platform-specific message handling, media upload/download, and rate limiting.

```bash
pip install -r bot/requirements.txt
python bot/telegram_bot.py   # Telegram
python bot/feishu_bot.py     # Feishu (WebSocket long-connection, no public IP)
```

Configuration is via `.env` at the project root. See `bot/README.md` for required environment variables.

## Safety Boundaries

1. **Local-first**: No data upload
2. **Disclaimer required**: Every report must include the OmicsClaw disclaimer
3. **No hallucinated science**: All parameters trace to SKILL.md or cited tools
4. **Security filtering**: `omicsclaw.py` enforces `allowed_extra_flags` whitelists
