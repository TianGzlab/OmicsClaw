<a id="top"></a>

<div align="center">
  <img src="docs/images/OmicsClaw_logo.jpeg" alt="OmicsClaw Logo" width="360"/>

  <h3>OmicsClaw</h3>
  <p><strong>Local-first AI research partner for multi-omics analysis</strong></p>
  <p>Conversational execution · persistent memory · reproducible skills · desktop and server workflows</p>

  <p>
    <a href="README.md"><b>English</b></a> ·
    <a href="README_zh-CN.md"><b>简体中文</b></a> ·
    <a href="docs/introduction/quickstart.mdx"><b>Quick Start</b></a> ·
    <a href="https://TianGzlab.github.io/OmicsClaw/"><b>Docs Site</b></a>
  </p>
</div>

# OmicsClaw

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![CI](https://img.shields.io/badge/CI-passing-brightgreen.svg)](https://github.com/TianGzlab/OmicsClaw/actions)
[![Website](https://img.shields.io/badge/Website-Live-brightgreen.svg)](https://TianGzlab.github.io/OmicsClaw/)

> [!NOTE]
> **v0.1.0 release:** OmicsClaw now provides a stable unified `oc` CLI, interactive CLI/TUI, graph memory, desktop/web app backend, remote execution support, messaging bot frontends, and a generated catalog of 89 analysis skills. Please report issues or feature requests through [GitHub Issues](https://github.com/TianGzlab/OmicsClaw/issues).

OmicsClaw is a multi-omics analysis platform that turns local analysis tools into reusable AI-callable skills. It supports natural-language workflows while keeping raw data and computation on your own machine or remote Linux server.

## Why OmicsClaw?

Most analysis sessions lose context: file paths, parameters, intermediate outputs, and method preferences have to be repeated. OmicsClaw keeps those workflows inspectable and resumable.

| Need | OmicsClaw approach |
|---|---|
| Run established bioinformatics workflows | Skills expose CLI/Python analysis modules with standard input, output, demo, and report contracts |
| Chat without uploading raw data | LLMs receive task context and tool results; local skills process the files |
| Resume interrupted work | Sessions, memory, workspaces, and outputs remain on disk |
| Switch interfaces | Use the same runtime from CLI, TUI, app backend, remote server, or bot channel |
| Extend analysis coverage | Add a skill under `skills/<domain>/<skill-name>/` and regenerate the catalog |

## Quick Start

The recommended setup is the repository bootstrap script. It creates the `OmicsClaw` conda environment and installs Python dependencies, R packages, bioinformatics command-line tools, and GitHub-only R packages managed by the project.

```bash
git clone https://github.com/TianGzlab/OmicsClaw.git
cd OmicsClaw

bash 0_setup_env.sh
conda activate OmicsClaw

oc env
oc list
oc run spatial-preprocess --demo --output /tmp/omicsclaw_demo
```

After installation, both `omicsclaw` and `oc` are available through `[project.scripts]`. If the console script is not on `PATH`, use `python omicsclaw.py <command>`.

Configure LLM credentials and runtime preferences with:

```bash
oc onboard
```

Or create `.env` manually from `.env.example`:

```bash
cp .env.example .env
```

Then set at least one provider block in `.env`:

```dotenv
LLM_PROVIDER=deepseek
LLM_API_KEY=sk-...
```

Start the conversational interface:

```bash
oc interactive
oc tui
oc interactive -p "run spatial-preprocess demo"
```

For the detailed installation guide, see [docs/_legacy/INSTALLATION.md](docs/_legacy/INSTALLATION.md). For the five-minute tutorial, see [docs/introduction/quickstart.mdx](docs/introduction/quickstart.mdx).

## Install Options

| Path | Use when | Command |
|---|---|---|
| Full conda environment | Real analysis work that needs Python, R, and external CLIs | `bash 0_setup_env.sh` |
| Lightweight venv | Chat, routing, development, or Python-only skills | `pip install -e ".[interactive]"` |
| Desktop/app backend | OmicsClaw-App, browser frontends, or remote execution | full conda path, then `oc app-server` |
| Memory API only | Inspect graph memory over HTTP | `pip install -e ".[memory]"`, then `oc memory-server` |

Dependency ownership is intentionally split:

| Dependency type | Source of truth |
|---|---|
| Python package metadata and extras | [pyproject.toml](pyproject.toml) |
| Conda R packages, bioinformatics CLIs, build toolchain | [environment.yml](environment.yml) |
| GitHub-only R packages | Tier 3 in [0_setup_env.sh](0_setup_env.sh) |
| Bot-only runtime details | [bot/README.md](bot/README.md) |

The repository does not use a root `requirements.txt` as the primary install entrypoint.

## Main Commands

| Command | Purpose |
|---|---|
| `oc env` | Inspect installed dependency tiers |
| `oc list` | List available skills |
| `oc run <skill> --demo` | Run a skill with built-in demo data |
| `oc run <skill> --input <file> --output <dir>` | Run a skill on user data |
| `oc interactive` | Start the prompt-toolkit chat interface |
| `oc tui` | Start the full-screen Textual interface |
| `oc app-server --host 127.0.0.1 --port 8765` | Start the backend used by desktop/web frontends |
| `oc memory-server` | Start the graph memory REST API |
| `oc onboard` | Configure LLM, runtime, memory, and channel settings |
| `oc mcp list` / `oc mcp add ...` | Manage Model Context Protocol servers |
| `python -m bot.run --channels telegram,feishu` | Start messaging bot frontends |

Makefile shortcuts such as `make test`, `make demo`, `make bot-telegram`, and `make bot-feishu` remain available for common developer tasks.

## Core Surfaces

| Surface | Entry point | Notes |
|---|---|---|
| CLI runner | `oc list`, `oc run ...` | Direct, reproducible skill execution |
| Interactive CLI/TUI | `oc interactive`, `oc tui` | Natural-language analysis with sessions and memory |
| Desktop/web backend | `oc app-server` | FastAPI backend for OmicsClaw-App and browser frontends |
| Remote execution | `oc app-server` on a remote Linux host | UI stays local; data and jobs stay on the server through SSH tunneling |
| Memory API | `oc memory-server` | Optional HTTP API for memory inspection and management |
| Bot channels | `python -m bot.run --channels ...` | Telegram, Feishu, and other channel adapters share the same tool loop |

Remote execution should bind the backend to `127.0.0.1`, use SSH tunneling, and set `OMICSCLAW_REMOTE_AUTH_TOKEN` when exposing remote control routes. See [docs/engineering/remote-execution.mdx](docs/engineering/remote-execution.mdx) and [docs/_legacy/remote-connection-guide.md](docs/_legacy/remote-connection-guide.md).

## Domain Coverage

`skills/catalog.json` is generated by `scripts/generate_catalog.py` and is the authoritative machine-readable catalog. The current catalog lists 89 skills.

| Domain | Typical workflows | Docs |
|---|---|---|
| Spatial transcriptomics | QC, preprocessing, domains, annotation, deconvolution, communication, CNV, trajectory, registration | [docs/domains/spatial.mdx](docs/domains/spatial.mdx) |
| Single-cell omics | QC, preprocessing, clustering, annotation, doublets, trajectory, velocity, communication, GRN | [docs/domains/singlecell.mdx](docs/domains/singlecell.mdx) |
| Genomics | QC, alignment, variant calling, CNV, assembly, epigenomics, annotation | [docs/domains/genomics.mdx](docs/domains/genomics.mdx) |
| Proteomics | QC, DIA/DDA analysis, PTM, interaction networks, biomarker workflows | [docs/domains/proteomics.mdx](docs/domains/proteomics.mdx) |
| Metabolomics | Peak picking, normalization, annotation, pathway analysis, biomarker workflows | [docs/domains/metabolomics.mdx](docs/domains/metabolomics.mdx) |
| Bulk RNA-seq | QC, alignment, differential expression, enrichment, co-expression, deconvolution, survival | [docs/domains/bulkrna.mdx](docs/domains/bulkrna.mdx) |
| Orchestration and literature | Multi-domain routing, method selection, workflow planning, literature support | [docs/domains/orchestrator.mdx](docs/domains/orchestrator.mdx) |

Run `oc list` for the current CLI view, or inspect [skills/catalog.json](skills/catalog.json) for generated metadata.

## Architecture Snapshot

OmicsClaw keeps domain-specific science in skills and keeps the shared runtime domain-agnostic.

| Path | Responsibility |
|---|---|
| [omicsclaw.py](omicsclaw.py) | Backward-compatible unified CLI runner |
| [omicsclaw/](omicsclaw/) | Core runtime, registry, loaders, memory, routing, app backend, interactive surfaces |
| [skills/](skills/) | Domain-organized analysis skills plus internal `_lib` utility packages |
| [bot/](bot/) | Messaging frontends that reuse the shared LLM tool loop |
| [docs/](docs/) | Mintlify documentation, engineering notes, legacy guides, workflow playbooks |
| [templates/SKILL-TEMPLATE.md](templates/SKILL-TEMPLATE.md) | Starting point for new skills |
| [tests/](tests/) | Pytest coverage for runtime and skills |

For deeper design notes, read [docs/architecture/overview.mdx](docs/architecture/overview.mdx) and [docs/architecture/skill-system.mdx](docs/architecture/skill-system.mdx).

## Memory, MCP, and Extensibility

- **Memory:** interactive sessions and agents can persist context through the graph memory system. See [docs/engineering/memory.mdx](docs/engineering/memory.mdx).
- **MCP:** external tools can be registered with `oc mcp add <name> <command-or-url>` and inspected with `oc mcp list`.
- **New skills:** follow [CONTRIBUTING.md](CONTRIBUTING.md), use [templates/SKILL-TEMPLATE.md](templates/SKILL-TEMPLATE.md), and regenerate the catalog with `python scripts/generate_catalog.py`.
- **Apps and bots:** desktop/web integration is documented in [docs/ecosystem/omicsclaw-app.mdx](docs/ecosystem/omicsclaw-app.mdx); messaging channels are documented in [docs/ecosystem/chat-bot.mdx](docs/ecosystem/chat-bot.mdx) and [bot/README.md](bot/README.md).

## Documentation Map

| Topic | Link |
|---|---|
| Quick start | [docs/introduction/quickstart.mdx](docs/introduction/quickstart.mdx) |
| What OmicsClaw is | [docs/introduction/what-is-omicsclaw.mdx](docs/introduction/what-is-omicsclaw.mdx) |
| Architecture | [docs/architecture/overview.mdx](docs/architecture/overview.mdx) |
| Skill system | [docs/architecture/skill-system.mdx](docs/architecture/skill-system.mdx) |
| Memory | [docs/engineering/memory.mdx](docs/engineering/memory.mdx) |
| Remote execution | [docs/engineering/remote-execution.mdx](docs/engineering/remote-execution.mdx) |
| App backend | [docs/ecosystem/omicsclaw-app.mdx](docs/ecosystem/omicsclaw-app.mdx) |
| Bot channels | [docs/ecosystem/chat-bot.mdx](docs/ecosystem/chat-bot.mdx) |
| Safety rules | [docs/safety/rules-and-disclaimer.mdx](docs/safety/rules-and-disclaimer.mdx) |
| Data privacy | [docs/safety/data-privacy.mdx](docs/safety/data-privacy.mdx) |
| Legacy installation details | [docs/_legacy/INSTALLATION.md](docs/_legacy/INSTALLATION.md) |

Preview the docs site locally with:

```bash
npx mintlify dev
```

## For Developers and AI Agents

Before complex repository maintenance, read [README.md](README.md), [AGENTS.md](AGENTS.md), [SPEC.md](SPEC.md), and the directly relevant code or docs. Repository workflow playbooks live under [docs/superpowers/playbooks/](docs/superpowers/playbooks/) and are indexed from [docs/superpowers/README.md](docs/superpowers/README.md).

Common development commands:

```bash
python -m pytest -v
make test
python scripts/generate_catalog.py
```

If a change creates a durable decision, plan, or workflow update, record it under `docs/superpowers/` and update the matching index.

## Safety and Scope

- OmicsClaw is local-first: raw data processing happens in your configured local or remote runtime.
- OmicsClaw is for research use only. It is not a medical device and does not provide clinical diagnosis.
- Every scientific result should be reviewed by qualified domain experts before downstream decisions.
- When exposing APIs beyond localhost, use explicit host binding, SSH tunnels, and tokens as documented.

See [docs/safety/rules-and-disclaimer.mdx](docs/safety/rules-and-disclaimer.mdx) and [docs/safety/data-privacy.mdx](docs/safety/data-privacy.mdx).

## Team and Community

Maintainers: Luyi Tian, Weige Zhou, Liying Chen, and Pengfei Yin.

Use [GitHub Issues](https://github.com/TianGzlab/OmicsClaw/issues) for bug reports and feature requests. Use [GitHub Discussions](https://github.com/TianGzlab/OmicsClaw/discussions) for questions and workflow discussions.

## Acknowledgments

OmicsClaw is inspired by [ClawBio](https://github.com/ClawBio/ClawBio)'s bioinformatics-native agent skill library and [Nocturne Memory](https://github.com/Dataojitori/nocturne_memory)'s graph-structured memory ideas.

## License

Apache-2.0 License. See [LICENSE](LICENSE).

## Citation

```bibtex
@software{omicsclaw2026,
  title = {OmicsClaw: A Memory-Enabled AI Agent for Multi-Omics Analysis},
  author = {Zhou, Weige and Chen, Liying and Yin, Pengfei and Tian, Luyi},
  year = {2026},
  url = {https://github.com/TianGzlab/OmicsClaw}
}
```

[Back to top](#top)
