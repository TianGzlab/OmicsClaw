# AGENTS.md — OmicsClaw Guide for AI Coding Agents

This guide is for AI coding agents working on the OmicsClaw codebase.

## Project Overview

OmicsClaw is a multi-omics analysis platform supporting 5 domains: spatial transcriptomics, single-cell omics, genomics, proteomics, and metabolomics. Each skill is a self-contained module that performs a specific analysis task via CLI or Python API. All processing is local-first. Design is inspired by [ClawBio](https://github.com/ClawBio/ClawBio).

**Note**: OmicsClaw evolved from SpatialClaw and now uses a unified `omicsclaw.py` entrypoint.

## Setup

```bash
cd /data1/TianLab/zhouwg/project/OmicsClaw
pip install -e .

# Add optional extras only when needed
# pip install -e ".[interactive]"
# pip install -e ".[tui]"
# pip install -e ".[memory]"
# pip install -e ".[full]"

python omicsclaw.py list   # or: oc list
python omicsclaw.py run spatial-preprocess --demo
```

> **`oc` short alias**: After `pip install -e .`, both `omicsclaw` and `oc` commands
> are available system-wide. `oc` is registered via `[project.scripts]` in
> `pyproject.toml` and points to `omicsclaw.cli:main` — the same entry point as
> `omicsclaw`. No PATH tricks needed.
>
> **Dependency source of truth**: Root dependency management lives in
> `pyproject.toml`. The repository does not use a root `requirements.txt` as a
> primary install entrypoint.

## Commands

> Both `python omicsclaw.py <cmd>` and the short alias `oc <cmd>` work identically
> after `pip install -e .` (or `make install-oc`).

| Command | Purpose |
|---------|---------|
| `oc list` | List all 50+ skills across 5 domains |
| `oc run <skill> --demo` | Run a skill with demo data |
| `oc run <skill> --input <file> --output <dir>` | Run with user data |
| `oc interactive` | **Start interactive terminal chat (CLI mode)** |
| `oc interactive --ui tui` | **Start full-screen Textual TUI** |
| `oc interactive -p "<prompt>"` | **Single-shot mode (non-interactive)** |
| `oc interactive --session <id>` | **Resume a previous session** |
| `oc tui` | Alias for `interactive --ui tui` |
| `oc app-server` | Start the FastAPI backend used by OmicsClaw-App / web frontends |
| `oc mcp list` | List configured MCP servers |
| `oc mcp add <name> <cmd> [args]` | Add an MCP server |
| `oc mcp remove <name>` | Remove an MCP server |
| `oc mcp config` | Show MCP config file path |
| `oc onboard` | Run interactive setup wizard for LLM, runtime, memory, and channels |
| `python -m pytest -v` | Run all tests |
| `make test` | Alias for pytest |
| `make demo` | Run preprocess demo |
| `make install-oc` | (Re)install package + activate `oc` alias |
| `make oc-link` | Quick wrapper script in `~/.local/bin/oc` (no pip) |
| `make bot-telegram` | Start Telegram bot |
| `make bot-feishu` | Start Feishu bot |

## Project Structure

```
OmicsClaw/
├── omicsclaw.py                # Main CLI runner (SKILLS dict, DOMAINS registry)
├── omicsclaw/                  # Core framework (domain-agnostic)
│   ├── common/                 # report.py, session.py, checksums.py
│   ├── core/                   # registry.py, dependency_manager.py
│   ├── loaders/                # File-extension → domain detection helpers
│   ├── memory/                 # Graph memory system
│   ├── routing/                # Multi-agent routing
│   ├── agents/                 # Agent definitions
│   └── interactive/            # Interactive CLI/TUI package
│       ├── __init__.py         # Package entry: run_interactive(), main()
│       ├── _constants.py       # Banner, LOGO, slash commands, slogans
│       ├── _session.py         # SQLite session persistence (aiosqlite)
│       ├── _mcp.py             # MCP server config / YAML management
│       ├── interactive.py      # prompt_toolkit REPL loop (CLI mode)
│       └── tui.py              # Textual full-screen TUI (TUI mode)
├── skills/                     # Domain-organized skills + shared utilities
│   ├── spatial/                # 15 spatial transcriptomics skills
│   │   ├── _lib/               # ★ Shared spatial utilities (adata_utils, viz, loader, etc.)
│   │   │   ├── viz/            # Unified visualization package (13 modules)
│   │   │   ├── adata_utils.py  # AnnData helper functions
│   │   │   ├── loader.py       # Multi-platform data loader
│   │   │   ├── dependency_manager.py  # Lazy import manager
│   │   │   ├── exceptions.py   # Domain-specific exceptions
│   │   │   └── viz_utils.py    # Figure saving utilities
│   │   ├── spatial-preprocess/ # QC + normalization + embedding
│   │   ├── spatial-domains/    # Tissue region identification
│   │   ├── spatial-annotate/   # Cell type annotation
│   │   └── ...
│   ├── singlecell/             # 14 single-cell omics skills
│   │   ├── _lib/               # ★ Shared single-cell utilities (19 modules)
│   │   │   ├── io.py, qc.py, preprocessing.py, markers.py, ...
│   │   │   ├── r_bridge.py     # R/Seurat integration bridge
│   │   │   ├── method_config.py # Method configuration & validation
│   │   │   └── annotation.py, trajectory.py, grn.py, ...
│   │   ├── sc-qc/              # Quality control
│   │   ├── sc-preprocessing/   # Normalization & filtering
│   │   └── ...
│   ├── genomics/               # 10 genomics skills
│   │   └── _lib/               # Shared genomics utilities
│   ├── proteomics/             # 8 proteomics skills
│   │   └── _lib/               # Shared proteomics utilities
│   ├── metabolomics/           # 8 metabolomics skills
│   │   └── _lib/               # Shared metabolomics utilities
│   ├── bulkrna/                # Bulk RNA skills
│   │   └── _lib/               # Shared bulk RNA utilities
│   └── orchestrator/           # Multi-domain routing
├── bot/                        # Messaging bot frontends
│   ├── core.py                 # Shared LLM engine + tool loop (reused by interactive)
│   ├── run.py                  # Unified bot runner
│   ├── channels/               # Platform-specific channel implementations
│   ├── onboard.py              # Interactive setup wizard
│   ├── requirements.txt        # Bot-specific dependencies
│   ├── README.md               # Bot setup guide
│   └── logs/                   # Audit logs (auto-created)
├── SOUL.md                     # Bot/CLI persona (OmicsBot)
├── templates/SKILL-TEMPLATE.md # Template for new skills
├── examples/                   # Shared demo data
├── sessions/                   # SpatialSession JSONs
├── CLAUDE.md                   # Agent routing instructions
└── AGENTS.md                   # This file
```

> **Import convention**: Domain-specific utilities are imported via
> `from skills.<domain>._lib.<module> import <name>`. The `_lib/` directories
> are internal shared packages — they are **not** registered as skills
> (the registry ignores directories starting with `_`).
> `omicsclaw/` contains only domain-agnostic framework code (core, loaders,
> memory, interactive, routing).

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

## Graph Memory System

OmicsClaw uses a centralized graph-based memory system to persist context across sessions, agents, and tool invocations. The core system is located in `omicsclaw/memory/`.

### Architecture

The memory system is backed by SQLite/PostgreSQL and is built as a graph database overlay using SQLAlchemy.

- **Nodes & Edges**: Every entity (session, dataset, user preference) is a node connected via edges to a central root node (`ROOT_NODE_UUID`). Nodes are addressed by URIs (e.g., `session://user123/cli`).
- **MemoryClient**: High-level abstract client (`omicsclaw/memory/memory_client.py`) used by multi-agent pipelines to `remember()`, `recall()`, and `search()`.
- **Compat Layer**: To maintain backward compatibility with old bot memory, `omicsclaw/memory/compat.py` implements the old interface but routes it through the graph engine.
- **REST API**: A FastAPI backend provides management capabilities, accessible via `oc memory-server`.

### Running the Dashboard API

You can spin up the backend API to inspect and manage memories. **Note**: `fastapi` and `uvicorn` are optional dependencies, you must install them first:

```bash
# Install memory API dependencies
pip install fastapi uvicorn
# OR: pip install -e ".[memory]"

# Starts the FastAPI server on port 8766
oc memory-server
```

The memory API binds to `127.0.0.1:8766` by default. If you bind it to a non-local interface, set `OMICSCLAW_MEMORY_API_TOKEN` as well.

## Desktop / Web App Backend

OmicsClaw also exposes a FastAPI backend for desktop and browser frontends such as OmicsClaw-App.

```bash
# Install the frontend/backend bridge dependencies
pip install -e ".[desktop]"

# Start the app backend on the shared frontend contract port
oc app-server --host 127.0.0.1 --port 8765
```

The app backend binds to `127.0.0.1:8765` by default and serves chat streaming, skills, providers, MCP, outputs, bridge control, and memory proxy endpoints for the frontend.

### Configuration (Environment Variables)

- `OMICSCLAW_MEMORY_DB_URL`: SQLAlchemy connection URL (`sqlite+aiosqlite:///bot/data/memory.db`)
- `OMICSCLAW_MEMORY_API_TOKEN`: Bearer token required when exposing the API beyond localhost.

## Bot Integration

OmicsClaw includes multi-channel messaging frontends in `bot/`:

```
bot/
├── __init__.py
├── core.py           # Shared LLM tool loop, skill execution, security
├── run.py            # Unified bot runner
├── channels/         # Platform implementations (telegram, feishu, dingtalk, discord, slack, wechat, qq, email, imessage)
├── requirements.txt  # Bot-specific dependencies
├── README.md         # Setup and configuration guide
└── logs/             # Audit logs (audit.jsonl)
```

### Bot Commands

| Command | Purpose |
|---------|---------|
| `python -m bot.run --channels <names>` | Start one or more configured messaging channels |
| `python -m bot.run --list` | List available channel integrations |
| `make bot-telegram` | Makefile alias for Telegram |
| `make bot-feishu` | Makefile alias for Feishu |

### Bot Architecture

All channels share `bot/core.py` which contains:
- LLM tool-use loop (OpenAI function calling)
- TOOLS definition (omicsclaw, save_file, write_file, generate_audio)
- `execute_omicsclaw()` — runs `omicsclaw.py run <skill>` as subprocess
- Security helpers (path sanitization, file size limits)
- Audit logging (JSONL)

The persona is defined in `SOUL.md` (OmicsBot, the OmicsClaw AI assistant).

### Configuration

Bot environment variables go in `.env` at the project root. See `bot/README.md` for the full list.

## Bot Integration

OmicsClaw includes multi-channel bot frontends in `bot/`. They all import `bot/core.py`, which provides the shared LLM tool-use loop, skill execution, security helpers, and audit logging. Each frontend handles platform-specific message handling, media upload/download, and rate limiting.

```bash
pip install -r bot/requirements.txt
python -m bot.run --channels telegram   # Telegram
python -m bot.run --channels feishu     # Feishu
python -m bot.run --channels telegram,slack,email
```

Configuration is via `.env` at the project root. See `bot/README.md` for required environment variables.

## Safety Boundaries

1. **Local-first**: No data upload
2. **Disclaimer required**: Every report must include the OmicsClaw disclaimer
3. **No hallucinated science**: All parameters trace to SKILL.md or cited tools
4. **Security filtering**: `omicsclaw.py` enforces `allowed_extra_flags` whitelists

## Interactive CLI/TUI

OmicsClaw features a full interactive terminal interface (referencing EvoScientist's architecture).

### Architecture

```
omicsclaw.py interactive
    └── omicsclaw/interactive/interactive.py   # prompt_toolkit REPL
           ├── bot/core.py                     # LLM engine (reused)
           ├── _session.py                     # SQLite session persistence
           ├── _mcp.py                         # MCP server management
           └── _constants.py                   # Banner, slash commands

omicsclaw.py tui  (or --ui tui)
    └── omicsclaw/interactive/tui.py           # Textual full-screen TUI
```

### Interactive Mode Commands

```bash
# Enter interactive CLI (default, uses prompt_toolkit REPL)
oc interactive

# Enter full-screen TUI (requires: pip install textual)
oc tui
oc interactive --ui tui

# Single-shot (non-interactive)
oc interactive -p "run spatial-preprocessing demo"

# Resume a previous session
oc interactive --session <session-id>

# Override model/provider
oc interactive --provider deepseek --model deepseek-chat

# Set working directory
oc interactive --workspace /path/to/workdir

# Daemon mode (persistent workspace, default behavior)
oc interactive --mode daemon

# Run mode (isolated per-session workspace)
oc interactive --mode run

# Run mode with a named workspace
oc interactive --mode run --name my-analysis
```

### Slash Commands (inside interactive session)

| Command | Description |
|---------|-------------|
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

### MCP Server Management

```bash
# Add an MCP server (stdio transport)
oc mcp add sequential-thinking npx -- -y @modelcontextprotocol/server-sequential-thinking

# Add an HTTP-based MCP server
oc mcp add my-server http://localhost:8080

# List all configured MCP servers
oc mcp list

# Remove an MCP server
oc mcp remove sequential-thinking

# Show config file location
oc mcp config
# → ~/.config/omicsclaw/mcp.yaml
```

MCP tools are loaded from `~/.config/omicsclaw/mcp.yaml` at session start.
Requires `langchain-mcp-adapters` for actual tool execution:
```bash
pip install langchain-mcp-adapters
```

### Session Persistence

Sessions are saved to `~/.config/omicsclaw/sessions.db` (SQLite).
Conversation history is preserved across restarts and can be resumed by ID.

### Dependencies

```bash
# Minimal (CLI mode)
pip install prompt-toolkit rich questionary pyyaml aiosqlite

# Or via pyproject.toml extras
pip install -e ".[interactive]"

# Full TUI support
pip install -e ".[tui]"
# then: pip install textual>=0.80
```
