# Installation Guide

## Quick Start

```bash
# Clone the repository
git clone https://github.com/TianGzlab/OmicsClaw.git
cd OmicsClaw

# Create and activate a Python 3.11+ virtual environment
python3.11 -m venv .venv
source .venv/bin/activate

# Install the base package
pip install -e .

# Verify the CLI
oc list
oc run spatial-preprocess --demo
```

After editable install, both of these entrypoints are available:

- `omicsclaw`
- `oc`

Both resolve to the same package CLI.

## Supported Python Versions

OmicsClaw currently targets:

- Python 3.11
- Python 3.12

The package metadata currently requires:

```text
>=3.11,<3.14
```

## System Requirements

| Component | Minimum | Recommended |
| --- | --- | --- |
| Python | 3.11 | 3.11 or 3.12 |
| RAM | 8 GB | 32 GB+ for larger analyses |
| Disk | 2 GB for core install | 10 GB+ for full method stack |
| GPU | optional | recommended for deep-learning-heavy methods |
| R | optional | recommended for R-backed workflows |

## Installation Profiles

OmicsClaw uses optional dependency groups instead of requiring one monolithic environment.

`pyproject.toml` is the only root dependency source of truth. The repository no longer maintains a root `requirements.txt` as a primary installation entrypoint.

### 1. Core install

```bash
pip install -e .
```

This installs the base platform and the core dependencies needed for:

- the main CLI
- skill discovery
- prompt/runtime infrastructure
- core AnnData and scientific Python tooling

### 2. Domain-focused installs

Install only the domains you need:

```bash
pip install -e ".[spatial]"
pip install -e ".[singlecell]"
pip install -e ".[genomics]"
pip install -e ".[proteomics]"
pip install -e ".[metabolomics]"
pip install -e ".[bulkrna]"
```

### 3. Optional spatial sub-layers

Some heavier spatial capabilities are intentionally split out:

```bash
pip install -e ".[spatial-domains]"
pip install -e ".[spatial-annotate]"
pip install -e ".[spatial-deconv]"
pip install -e ".[spatial-trajectory]"
pip install -e ".[spatial-velocity]"
pip install -e ".[spatial-cnv]"
pip install -e ".[spatial-enrichment]"
pip install -e ".[spatial-communication]"
pip install -e ".[spatial-integration]"
pip install -e ".[spatial-registration]"
pip install -e ".[spatial-condition]"
```

This lets you avoid pulling in every GPU- or R-heavy dependency up front.

### 4. Full install

```bash
pip install -e ".[full]"
```

Use this when you want the broadest method coverage in one environment.

### 5. Interactive CLI / TUI

Interactive mode has its own lightweight extras. `.[interactive]` now includes:

- prompt-toolkit / Rich / Questionary for the terminal UI
- aiosqlite for session persistence
- OpenAI-compatible client + HTTP dependencies used by the interactive LLM bridge

```bash
pip install -e ".[interactive]"
```

OmicsClaw automatically reads the project-root `.env` file for interactive startup. If `python-dotenv` is not installed, a built-in fallback parser is used, so standard `.env` key/value files still work.

For the full-screen Textual TUI:

```bash
pip install -e ".[tui]"
```

### 6. Memory server

To use the graph-memory REST API and dashboard backend:

```bash
pip install -e ".[memory]"
```

### 7. Desktop / web frontend backend

To drive OmicsClaw-App or any compatible local web frontend:

```bash
pip install -e ".[desktop]"
oc app-server --host 127.0.0.1 --port 8765
```

The `desktop` extra includes the notebook runtime dependencies, so this same
server process also serves the native `/notebook/*` routes used by the
embedded notebook UI. No separate notebook bridge is required.

### 8. Research and autonomous extras

For research-pipeline or notebook-style auxiliary workflows:

```bash
pip install -e ".[research]"
pip install -e ".[autonomous]"
```

### 9. Development tools

```bash
pip install -e ".[dev]"
```

This adds test and lint tooling such as `pytest`, `ruff`, `black`, and `mypy`.

## Common Installation Patterns

### Minimal interactive workstation

```bash
pip install -e ".[interactive]"
```

After installation, the fastest way to configure the runtime is:

```bash
oc onboard
```

This writes the project `.env` and can configure LLM credentials, shared runtime settings, memory options, and messaging channels.

Example custom endpoint configuration:

```env
LLM_PROVIDER=custom
LLM_BASE_URL=https://your-endpoint.example.com/v1
OMICSCLAW_MODEL=your-model-name
LLM_API_KEY=sk-xxxxxxxxxxxxxxxx
```

Provider-specific keys also work without setting `LLM_API_KEY`, for example:

```env
DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

### Interactive + TUI + memory

```bash
pip install -e ".[tui,memory]"
```

### Spatial workstation

```bash
pip install -e ".[spatial,interactive]"
```

### Broad analysis workstation

```bash
pip install -e ".[full,interactive,memory]"
```

### Development environment

```bash
pip install -e ".[full,interactive,memory,dev]"
```

## Verifying the Installation

Useful smoke tests:

```bash
oc list
python omicsclaw.py env
oc run spatial-preprocess --demo
oc interactive -p "介绍一下你能做什么"
```

If you installed TUI support:

```bash
oc tui
```

If you installed memory support:

```bash
oc memory-server
```

By default this binds to `127.0.0.1:8766`. If you bind the memory API to a non-local interface, you must also set `OMICSCLAW_MEMORY_API_TOKEN`.

If you installed desktop frontend support:

```bash
oc app-server
```

By default this binds to `127.0.0.1:8765` and includes the notebook routes
consumed by OmicsClaw-App.

If `omicsclaw_kg` is importable, or you set
`OMICSCLAW_KG_SOURCE_DIR=/path/to/OmicsClaw-KG`, the same `oc app-server`
process also exposes the embedded `/kg/*` routes used by the KG Explorer.

## Interactive and Workspace Features

After installing `.[interactive]`, you can use:

```bash
oc interactive
oc interactive --ui tui
oc interactive -p "run spatial-preprocess demo"
oc interactive --session <session-id>
oc interactive --workspace /path/to/workdir
oc interactive --mode daemon
oc interactive --mode run --name my-analysis
```

Workspace behavior:

- `--mode daemon` keeps using a persistent workspace
- `--mode run` creates an isolated per-session workspace
- `--workspace` explicitly selects the workspace directory

## MCP Support

MCP server configuration commands are available from the main CLI:

```bash
oc mcp list
oc mcp add sequential-thinking npx -- -y @modelcontextprotocol/server-sequential-thinking
oc mcp remove sequential-thinking
oc mcp config
```

To actually load and execute MCP tools inside interactive sessions, install the adapter package separately:

```bash
pip install langchain-mcp-adapters
```

Notes:

- OmicsClaw stores MCP configuration in the user config directory
- prompt injection only includes active prompt-worthy MCP servers
- configured but unavailable servers do not consume prompt budget

## R Dependencies

For R Enhanced plotting dependencies (ggplot2, ComplexHeatmap, monocle3, GSVA, etc.), see [docs/R-DEPENDENCIES.md](R-DEPENDENCIES.md).

Some skills rely on R packages invoked through subprocess-based R workflows.

Install R first:

```bash
# Ubuntu / Debian
sudo apt install r-base r-base-dev

# macOS
brew install r
```

Then install any required system libraries for compiled R packages as needed.

Typical Ubuntu packages:

```bash
sudo apt install libcurl4-openssl-dev libssl-dev libxml2-dev \
                 libharfbuzz-dev libfribidi-dev libfreetype6-dev \
                 libpng-dev libtiff5-dev libjpeg-dev
```

If your selected methods require Python-side R bridges or helpers, install those explicitly in your environment.

## Fast Installation with uv

If you use `uv`, environment creation and dependency resolution are usually much faster:

```bash
pip install uv
uv venv .venv --python 3.11
source .venv/bin/activate
uv pip install -e ".[interactive]"
```

## Testing the Runtime

For a broader runtime verification:

```bash
python -m pytest -q tests/test_context_assembler.py
python -m pytest -q tests/test_query_engine.py
python -m pytest -q tests/test_interactive_loop.py
```

For a full test run:

```bash
python -m pytest -v
```

## Troubleshooting

### `oc` cannot find `omicsclaw.py`

The package entrypoint searches for the repository-root launcher. Run `oc` from inside the OmicsClaw repository, or set:

```bash
export OMICSCLAW_CLI_PATH=/absolute/path/to/omicsclaw.py
```

### TUI falls back or fails to start

Install the TUI extra:

```bash
pip install -e ".[tui]"
```

### MCP servers are configured but no MCP tools appear

Check all three conditions:

1. `langchain-mcp-adapters` is installed
2. the configured server command or URL is reachable
3. you restarted the interactive session after changing MCP config

### Memory server command fails

Install the memory extra:

```bash
pip install -e ".[memory]"
```

### Heavy optional packages fail to build

Use smaller installation profiles first, then add only the domain extras you need. This is especially helpful for:

- GPU and PyTorch-heavy spatial methods
- R-backed workflows
- packages with compiled scientific dependencies

## Summary

The recommended installation strategy is:

- start with `pip install -e .`
- add only the domain extras you need
- add `.[interactive]` or `.[tui]` for interactive use
- add `.[memory]` if you want the memory API and dashboard
- add `.[dev]` for testing and development work

This matches OmicsClaw's current modular runtime design much better than trying to install every optional method on day one.
