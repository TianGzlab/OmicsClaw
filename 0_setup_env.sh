#!/usr/bin/env bash
# OmicsClaw environment setup
#
# Strategy (4 tiers):
#   1. mamba/conda env create from environment.yml (R, CLIs, build toolchain)
#   2. pip install -e ".[full,singlecell-upstream]" (OmicsClaw + Python deps)
#      + pip install velocyto (no py3.11 bioconda build)
#   3. inline Rscript -e 'devtools::install_github(...)' (GitHub R packages)
#   4. symlink vendored tools/ binaries into $CONDA_PREFIX/bin (stub for now)
#
# Usage:
#     bash 0_setup_env.sh              # creates env named "OmicsClaw"
#     bash 0_setup_env.sh my_env_name  # custom name

set -euo pipefail

ENV_NAME="${1:-OmicsClaw}"
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$PROJECT_ROOT/environment.yml"
TOOLS_DIR="$PROJECT_ROOT/tools"

# ----- prerequisites: mamba preferred, conda fallback ---------------

if command -v mamba >/dev/null 2>&1; then
    INSTALLER="mamba"
elif command -v conda >/dev/null 2>&1; then
    INSTALLER="conda"
else
    echo "[setup_env] ✖ Neither 'mamba' nor 'conda' is on PATH." >&2
    echo "  Install Miniforge first (mamba is bundled and recommended):" >&2
    echo "    https://github.com/conda-forge/miniforge" >&2
    exit 1
fi
echo "[setup_env] using $INSTALLER"

if [ ! -f "$ENV_FILE" ]; then
    echo "[setup_env] ✖ environment.yml not found at $ENV_FILE" >&2
    exit 1
fi

# ----- Tier 1: declarative env from bioconda + conda-forge ----------

if "$INSTALLER" env list | awk '{print $1}' | grep -qx "$ENV_NAME"; then
    echo "[setup_env] env '$ENV_NAME' already exists — updating from environment.yml"
    "$INSTALLER" env update -n "$ENV_NAME" -f "$ENV_FILE" --prune
else
    echo "[setup_env] creating env '$ENV_NAME' from environment.yml"
    "$INSTALLER" env create -n "$ENV_NAME" -f "$ENV_FILE"
fi

# Resolve the env prefix once — needed by later tiers.
ENV_PREFIX="$("$INSTALLER" run -n "$ENV_NAME" python -c 'import sys; print(sys.prefix)')"
ENV_BIN="$ENV_PREFIX/bin"
echo "[setup_env] env prefix: $ENV_PREFIX"

echo "[setup_env] ✔ Tier 1 complete"
