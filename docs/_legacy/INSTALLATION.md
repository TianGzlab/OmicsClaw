# Installation Guide

> This is the archived Markdown installation guide. The current docs site uses
> `docs/introduction/quickstart.mdx`, but this file remains useful for
> repository-local setup and troubleshooting notes.

## Recommended Path

Use `0_setup_env.sh` for a full OmicsClaw analysis environment. It provisions
the conda environment, R stack, bioinformatics command-line tools, editable
OmicsClaw package, Python optional method residue, and GitHub-only R packages.

```bash
git clone https://github.com/TianGzlab/OmicsClaw.git
cd OmicsClaw

bash 0_setup_env.sh
conda activate OmicsClaw

oc env
oc list
oc run spatial-preprocess --demo
```

After setup, both console entrypoints are available:

- `omicsclaw`
- `oc`

They resolve to the same package CLI. You can also use the repository launcher
directly:

```bash
python omicsclaw.py list
```

## Prerequisites

The setup script requires either `mamba` or `conda` on `PATH`. Miniforge is the
recommended installer because it uses `conda-forge` by default and includes
`mamba`.

The full `environment.yml` path is currently designed for Linux, WSL2, and
remote Linux analysis servers. It includes Linux toolchain packages such as
`gxx_linux-64` and `sysroot_linux-64`. On macOS, use the lightweight Python-only
path locally, or run the full setup on a Linux/WSL/remote execution host.

### Install Miniforge

Linux and WSL:

```bash
curl -L -O "https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-$(uname)-$(uname -m).sh"
bash "Miniforge3-$(uname)-$(uname -m).sh"
exec "$SHELL"
conda --version
mamba --version
```

Windows users should run the full setup inside WSL2. Native Windows Miniforge
can be used for the lightweight Python-only path, but the full conda analysis
environment contains Linux-specific toolchain packages.

## What `0_setup_env.sh` Manages

The current dependency model has one full-install entrypoint:

```bash
bash 0_setup_env.sh [env_name]
```

Default environment name: `OmicsClaw`.

Custom environment name:

```bash
bash 0_setup_env.sh OmicsClaw_dev
conda activate OmicsClaw_dev
```

The script is idempotent. Re-running it updates the existing environment in
place using `environment.yml`, then re-applies the pip and R source-install
layers.

| Layer | Owner | Source | Contents |
| --- | --- | --- | --- |
| Conda base | `mamba` or `conda` | `environment.yml` | Python 3.11, R 4.3, build toolchain, bioinformatics CLIs, heavy Python science stack |
| Thin pip residue | `uv pip` or `pip` | `pyproject.toml` extras | editable `omicsclaw`, PyPI-only method packages, console scripts |
| R source packages | `Rscript` + `devtools` | inline Tier 3 in `0_setup_env.sh` | GitHub-only R packages such as spacexr, CARD, CellChat, numbat, SPARK, DoubletFinder |
| Vendored tools | symlink stub | `tools/`, `0_build_vendored_tools.sh` | currently no bundled vendored binaries |
| Isolated sub-envs | `mamba` or `conda` | `environments/*.yml` | hard-conflict tools such as optional banksy |

Dependency source of truth:

- Python package metadata and console scripts: `pyproject.toml`
- R packages, bioinformatics CLIs, build tooling, and heavy scientific Python
  packages: `environment.yml`
- GitHub-only R roots: Tier 3 inside `0_setup_env.sh`
- The repository does not use a root `requirements.txt` as a primary install
  entrypoint.

## Full Install Options

### Standard CPU-safe setup

```bash
bash 0_setup_env.sh
conda activate OmicsClaw
```

The conda layer installs a CPU-safe PyTorch baseline. This is the safest default
for laptops, shared servers, CI, and machines without NVIDIA GPUs.

### GPU-aware PyTorch setup

The script can replace the CPU baseline with the official CUDA PyTorch wheel
after the main conda solve completes.

```bash
# Default behavior: try CUDA only if nvidia-smi reports a GPU; continue if not verified.
OMICSCLAW_TORCH_BACKEND=auto bash 0_setup_env.sh

# Require CUDA PyTorch and fail setup if install or verification fails.
OMICSCLAW_TORCH_BACKEND=cuda OMICSCLAW_PYTORCH_CUDA_VERSION=12.1 bash 0_setup_env.sh

# Force CPU PyTorch even on GPU-capable machines.
OMICSCLAW_TORCH_BACKEND=cpu bash 0_setup_env.sh
```

Verify CUDA after setup:

```bash
mamba run -n OmicsClaw python -c "import torch; print(torch.cuda.is_available(), torch.version.cuda)"
```

Expected on a correctly wired CUDA environment:

```text
True 12.1
```

Advanced mirrors can override:

- `OMICSCLAW_TORCH_WHEEL_INDEX`
- `OMICSCLAW_TORCH_VERSION`
- `OMICSCLAW_PYTORCH_CUDA_TAG`
- `OMICSCLAW_TORCH_WHEEL_SPEC`

Remote installs must run setup on the actual analysis server. A desktop
client's GPU state is not relevant for a remote execution host.

### Optional banksy sub-environment

`pybanksy` requires dependency pins that conflict with the main full analysis
environment, so it is installed only into a dedicated `omicsclaw_banksy`
sub-environment when explicitly requested.

Recommended safe form:

```bash
OMICSCLAW_WITH_BANKSY=1 bash 0_setup_env.sh
```

With a custom main env name:

```bash
bash 0_setup_env.sh OmicsClaw_dev --with-banksy
```

## Lightweight Python-only Path

Use a venv only when you need chat/routing/development surfaces and do not need
R-backed methods or external bioinformatics CLIs such as `samtools`, `STAR`,
`fastqc`, `bwa`, `bcftools`, or `gatk4`.

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e .
oc list
```

Common lightweight extras:

```bash
pip install -e ".[interactive]"
pip install -e ".[tui]"
pip install -e ".[memory]"
pip install -e ".[desktop]"
pip install -e ".[dev]"
```

The `[full]` extra is preserved for compatibility, but it is no longer the
recommended way to build a complete analysis workstation. Use
`bash 0_setup_env.sh` for full local analysis coverage because the heavy
scientific stack has moved into the conda layer.

## Configuration

The fastest way to configure LLM providers, shared runtime settings, memory,
and messaging channels is:

```bash
oc onboard
```

The wizard writes the project-root `.env` file. Manual configuration is also
supported:

```env
LLM_PROVIDER=custom
LLM_BASE_URL=https://your-endpoint.example.com/v1
OMICSCLAW_MODEL=your-model-name
LLM_API_KEY=sk-xxxxxxxxxxxxxxxx
```

Provider-specific keys can also be used:

```env
DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
OPENAI_API_KEY=sk-proj-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

OAuth support is not part of the analysis-focused full extra. Install it only
when you need ccproxy-backed OAuth:

```bash
pip install -e ".[oauth]"
# or
pip install -e ".[full,oauth]"
```

## Runtime Services

### Interactive CLI and TUI

```bash
oc interactive
oc interactive --ui tui
oc tui
oc interactive -p "run spatial-preprocess demo"
oc interactive --session <session-id>
```

The full-screen TUI needs `textual>=0.80`. If `oc tui` reports that `textual`
is missing, install the TUI extra inside the active environment:

```bash
pip install -e ".[tui]"
```

Workspace options:

```bash
oc interactive --workspace /path/to/workdir
oc interactive --mode daemon
oc interactive --mode run --name my-analysis
```

### Memory API

```bash
oc memory-server
```

Default bind address: `127.0.0.1:8766`.

If you expose the memory API beyond localhost, set
`OMICSCLAW_MEMORY_API_TOKEN`.

### Desktop / web app backend

```bash
oc app-server --host 127.0.0.1 --port 8765
```

The app backend serves chat streaming, skills, providers, MCP, outputs, bridge
control, memory proxy routes, and native notebook routes. If `omicsclaw_kg` is
installed or `OMICSCLAW_KG_SOURCE_DIR=/path/to/OmicsClaw-KG` is set, the same
process also mounts the embedded `/kg/*` routes.

### MCP management

```bash
oc mcp list
oc mcp add sequential-thinking npx -- -y @modelcontextprotocol/server-sequential-thinking
oc mcp remove sequential-thinking
oc mcp config
```

To execute MCP tools inside interactive sessions, install the adapter package:

```bash
pip install langchain-mcp-adapters
```

## Verification

Fast smoke checks after full setup:

```bash
oc env
oc list
oc run spatial-preprocess --demo
```

After configuring an LLM provider with `oc onboard`, verify the interactive
surface:

```bash
oc interactive -p "介绍一下你能做什么"
```

Script and dependency-management checks:

```bash
bash -n 0_setup_env.sh
```

Install the development extra before running pytest if your active environment
does not already include it:

```bash
pip install -e ".[dev]"
python -m pytest -q tests/test_context_assembler.py
```

Full test suite:

```bash
python -m pytest -v
```

End-to-end fresh-machine smoke test:

```bash
bash scripts/smoke_test_setup.sh
```

Run the full smoke test only when you can afford a complete environment create
and update cycle.

## Troubleshooting

### Neither `mamba` nor `conda` is found

Install Miniforge, restart the shell, and verify:

```bash
conda --version
mamba --version
```

### Shared conda cache permission errors

On shared conda installations, `0_setup_env.sh` defaults `CONDA_PKGS_DIRS` to a
private writable cache:

```bash
~/.conda/pkgs
```

To use another cache:

```bash
export CONDA_PKGS_DIRS=/path/to/writable/pkgs
bash 0_setup_env.sh
```

### Existing prefix is incomplete

If a previous interrupted setup left a directory without `conda-meta`, remove
or repair that prefix before rerunning:

```bash
mamba env remove -p /path/to/incomplete/env -y
bash 0_setup_env.sh
```

### pip reports `resolution-too-deep`

Use `bash 0_setup_env.sh` instead of a direct all-pip `[full]` install. The
current setup intentionally moves heavy resolver hubs such as scanpy, anndata,
squidpy, torch, scvi-tools, scvelo, cellrank, multiqc, and kb-python into the
conda layer, leaving pip with only the thin PyPI-only residue.

### CUDA setup is not verified

For optional acceleration, let setup continue:

```bash
OMICSCLAW_TORCH_BACKEND=auto bash 0_setup_env.sh
```

For mandatory acceleration, make CUDA verification fatal:

```bash
OMICSCLAW_TORCH_BACKEND=cuda bash 0_setup_env.sh
```

Then check:

```bash
mamba run -n OmicsClaw python -c "import torch; print(torch.cuda.is_available(), torch.version.cuda)"
```

### SpaGCN pulls the deprecated `sklearn` placeholder

Tier 2 sets:

```bash
SKLEARN_ALLOW_DEPRECATED_SKLEARN_PACKAGE_INSTALL=True
```

This only allows SpaGCN's legacy metadata to resolve. OmicsClaw itself depends
on `scikit-learn`.

### R package guidance

For the recommended full setup, do not manually install the project R stack
first. `0_setup_env.sh` installs R 4.3 packages through `environment.yml` and
GitHub-only R packages through its Tier 3 Rscript block.

For historical R notes, see [R-DEPENDENCIES.md](R-DEPENDENCIES.md).

### `cnvkit` is missing

`cnvkit` is intentionally not bundled because current compatible versions
conflict with the main environment's `macs3` dependency chain. Install it in a
separate dedicated environment if you need `genomics-cnv-calling`.

### `oc` cannot find `omicsclaw.py`

Run from inside the OmicsClaw repository or set:

```bash
export OMICSCLAW_CLI_PATH=/absolute/path/to/omicsclaw.py
```

### TUI fails to start in a lightweight venv

Install the TUI extra:

```bash
pip install -e ".[tui]"
```

In the full `0_setup_env.sh` environment, the core interactive stack is
installed by the conda layer, but `textual` remains an optional TUI extra.

### MCP servers are configured but no tools appear

Check:

1. `langchain-mcp-adapters` is installed.
2. The configured MCP command or URL is reachable.
3. You restarted the interactive session after changing MCP config.

## Summary

Recommended install strategy:

1. Use `bash 0_setup_env.sh` for the complete local analysis environment.
2. Use `oc onboard` to configure LLM and runtime settings.
3. Use the venv path only for lightweight Python-only chat, routing, or
   development work.
4. Keep hard-conflict tools in isolated sub-environments instead of forcing
   them into the main analysis env.
