# Architecture

## Overview

OmicsClaw is a **skill-based, local-first** multi-omics analysis framework. Each analysis capability is packaged as an independent skill — a self-contained module with methodology documentation, implementation, and tests. Skills communicate through standardized data formats (`.h5ad`, `.vcf`, `.mzML`).

**Data Flow:**
```
User Input (CLI / Bot)
       ↓
omicsclaw.py (Router + Security)
       ↓
Skills (40+ across 5 domains)
       ↓
Standardized Output (reports, data, figures)
```

## Directory Structure

```
OmicsClaw/
├── omicsclaw.py              # Main CLI entrypoint
├── omicsclaw/                # Core utilities
│   ├── core/                 # Registry, skill discovery
│   ├── routing/              # Query routing, orchestration
│   ├── loaders/              # Multi-omics data loading
│   ├── common/               # Shared utilities (reports, viz)
│   ├── spatial/              # Spatial transcriptomics utils
│   ├── singlecell/           # Single-cell utils
│   ├── genomics/             # Genomics utils
│   ├── proteomics/           # Proteomics utils
│   └── metabolomics/         # Metabolomics utils
├── skills/                   # Analysis modules
│   ├── spatial/              # 16 spatial skills
│   ├── singlecell/           # 5 single-cell skills
│   ├── genomics/             # 8 genomics skills
│   ├── proteomics/           # 6 proteomics skills
│   ├── metabolomics/         # 5 metabolomics skills
│   ├── orchestrator/         # Multi-domain routing
│   └── catalog.json          # Auto-generated skill index
├── bot/                      # Messaging interfaces
│   ├── core.py               # LLM engine + tool loop
│   ├── telegram_bot.py       # Telegram frontend
│   └── feishu_bot.py         # Feishu frontend
├── docs/                     # Documentation
├── examples/                 # Demo datasets
├── scripts/                  # Utility scripts
├── templates/                # Output templates
├── tests/                    # Integration tests
└── sessions/                 # Workflow state
```

## Skill Structure

Each skill is self-contained with three components:

### 1. SKILL.md - Methodology Specification

```yaml
---
name: skill-name
description: One-line description
version: 0.1.0
tags: [domain, method, ...]
metadata:
  omicsclaw:
    domain: spatial
    emoji: "🔬"
---
```

Required sections: Core Capabilities, Workflow, Input/Output, Dependencies, Safety

### 2. Python Script - Implementation

- CLI interface: `--input`, `--output`, `--demo`
- Uses shared utilities from `omicsclaw/`
- Outputs: `report.md`, `result.json`, `processed.h5ad`
- Graceful dependency handling via `dependency_manager`

### 3. Tests - Validation

- `test_demo_mode` - Script runs successfully
- `test_demo_report_content` - Report contains required sections
- `test_demo_result_json` - JSON output is valid

## Data Flow

Skills pass state through standardized file formats:

**Spatial/Single-cell:** AnnData (`.h5ad`) with progressive enrichment
```
preprocess → domains → de → genes → statistics
```

**Genomics:** VCF files (`.vcf.gz`)
**Proteomics/Metabolomics:** mzML files

Each skill adds results to the data object without modifying previous results.

## Orchestrator

The orchestrator skill routes queries to appropriate analysis skills:

| Routing Method | Example |
|----------------|---------|
| Natural language | "find spatially variable genes" → `genes` |
| File type | `.h5ad` → `preprocess`, `.vcf` → `vcf-ops` |
| Named pipeline | `--pipeline standard` → sequential execution |

Named pipelines execute skills sequentially, passing output as input to the next skill.

## Security

`omicsclaw.py` enforces per-skill `allowed_extra_flags` whitelist to prevent injection attacks.

## Output Format

Every skill produces standardized output:

```
output_dir/
├── report.md              # Human-readable analysis
├── result.json            # Machine-readable results
├── processed.h5ad         # Updated data (if applicable)
├── figures/               # Visualizations
├── tables/                # Result tables
└── reproducibility/       # Version info, run command
```

## Adding a New Skill

1. Create skill directory: `skills/<domain>/<skill-name>/`
2. Add `SKILL.md` with methodology
3. Implement `<skill_name>.py` with CLI interface
4. Add tests in `tests/`
5. Register in `omicsclaw/core/registry.py`
6. Update `pytest.ini`
7. Run `python scripts/generate_catalog.py`
8. Verify: `python omicsclaw.py list`

## Dependency Management

- **Core** (scanpy, anndata, numpy) - Always required
- **Optional** (torch, scvi-tools, rpy2) - Loaded lazily, clear errors if missing
- **R packages** - Called via rpy2, fallback to Python alternatives

## Testing

```bash
python -m pytest -v                    # All skills
python -m pytest skills/spatial/ -v    # Single domain
python -m pytest -k "test_demo" -v     # Demo tests only
```

All tests use `--demo` mode with synthetic data (< 3 min total).

## Bot Integration

OmicsClaw includes messaging bot interfaces for Telegram and Feishu:

```
User Message
     ↓
Bot Frontend (telegram_bot.py / feishu_bot.py)
     ↓
bot/core.py (LLM tool loop)
     ↓
omicsclaw.py (skill execution)
     ↓
Results delivered via messaging
```

**Components:**

- **core.py** - Platform-agnostic LLM engine, tool execution, security, audit logging
- **telegram_bot.py** - Telegram handlers, rate limiting, media processing
- **feishu_bot.py** - Feishu WebSocket, rich-text parsing, group chat filtering
- **SOUL.md** - Bot persona definition

Both frontends delegate to `core.llm_tool_loop()` which executes skills as subprocesses and returns results for delivery.

---

**For detailed bot setup, see [bot/README.md](../bot/README.md)**
