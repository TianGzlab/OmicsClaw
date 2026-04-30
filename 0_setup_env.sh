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

# Env-existence check matches by name (column 1 of `env list`). Envs
# created with --prefix in custom locations are listed by absolute path
# and won't match here — that's intentional; this script manages named
# envs only.
#
# CONDA_CHANNEL_PRIORITY=strict prefixes both create and update because
# `mamba env create`/`mamba env update` (libmamba env subcommand) do NOT
# accept --strict-channel-priority as a CLI flag in mamba 1.5.x; the env
# var is the supported way to enforce strict priority for env subcommands.
if "$INSTALLER" env list | awk '{print $1}' | grep -qx "$ENV_NAME"; then
    echo "[setup_env] env '$ENV_NAME' already exists — updating from environment.yml"
    CONDA_CHANNEL_PRIORITY=strict "$INSTALLER" env update -n "$ENV_NAME" -f "$ENV_FILE" --prune
else
    echo "[setup_env] creating env '$ENV_NAME' from environment.yml"
    CONDA_CHANNEL_PRIORITY=strict "$INSTALLER" env create -n "$ENV_NAME" -f "$ENV_FILE"
fi

# Resolve the env prefix once — needed by later tiers.
# --no-capture-output: avoid stdout buffering on some mamba versions.
ENV_PREFIX="$("$INSTALLER" run -n "$ENV_NAME" --no-capture-output \
    python -c 'import sys; print(sys.prefix)')"
if [ -z "$ENV_PREFIX" ] || [ ! -d "$ENV_PREFIX" ]; then
    echo "[setup_env] ✖ failed to resolve env prefix for '$ENV_NAME'" >&2
    echo "  ($INSTALLER run returned: '$ENV_PREFIX')" >&2
    exit 1
fi
ENV_BIN="$ENV_PREFIX/bin"
echo "[setup_env] env prefix: $ENV_PREFIX"

echo "[setup_env] ✔ Tier 1 complete"

# ----- Tier 2: OmicsClaw editable + Python optional extras ----------
# pyproject.toml owns all Python deps. Running pip inside the env
# attaches them to the Tier 1 Python interpreter.

echo "[setup_env] Tier 2.0: pip install -e \".[full,singlecell-upstream]\""
"$INSTALLER" run -n "$ENV_NAME" --no-capture-output \
    pip install -e "$PROJECT_ROOT[full,singlecell-upstream]"

# Tier 2.1: tools that have no bioconda Python 3.11 build (surfaced by T2
# validation):
#   - velocyto.py: bioconda has only 3.6–3.10 and 3.12 builds, not 3.11.
#                  PyPI name is `velocyto` (the .py suffix is bioconda-only).
echo "[setup_env] Tier 2.1: pip install velocyto"
"$INSTALLER" run -n "$ENV_NAME" --no-capture-output \
    pip install "velocyto>=0.17.17"

echo "[setup_env] ✔ Tier 2 complete"

# NOTE on cnvkit (genomics-cnv-calling skill): bioconda ships only 0.9.8
# which crashes on pandas>=2.0 (uses removed pandas.Int64Index). Newer
# versions (0.9.10+) have the fix but their joblib<1.0 transitive dep
# conflicts with macs3's scikit-learn requirement of joblib>=1.0. cnvkit
# is therefore NOT bundled; users who need it should install it in a
# separate dedicated env to avoid corrupting macs3. Same pattern as
# cellranger (proprietary), documented at the skill level.

# ----- Tier 3: GitHub-only R packages (no bioconda equivalent) ----------
# Idempotent: requireNamespace() skips already-installed packages.
# Compiles run inside the activated env so they pick up Tier 1's gxx +
# sysroot + R headers automatically. r-devtools is in environment.yml.

echo "[setup_env] Tier 3: GitHub R packages (devtools::install_github)"
"$INSTALLER" run -n "$ENV_NAME" --no-capture-output Rscript - <<'RSCRIPT'
gh_pkgs <- list(
  c("spacexr",       "dmcable/spacexr"),
  c("CARD",          "YMa-lab/CARD"),
  c("CellChat",      "jinworks/CellChat"),
  c("numbat",        "kharchenkolab/numbat"),
  c("SPARK",         "xzhoulab/SPARK"),
  c("DoubletFinder", "chris-mcginnis-ucsf/DoubletFinder")
)
for (p in gh_pkgs) {
  if (requireNamespace(p[1], quietly = TRUE)) {
    cat(sprintf("[r-extras] %s already installed — skipping\n", p[1]))
  } else {
    cat(sprintf("[r-extras] installing %s from GitHub:%s\n", p[1], p[2]))
    devtools::install_github(p[2], upgrade = "never", quiet = TRUE)
    if (!requireNamespace(p[1], quietly = TRUE)) {
      stop(sprintf("[r-extras] FAILED to install %s", p[1]))
    }
  }
}
cat("[r-extras] all 6 GitHub R packages OK\n")
RSCRIPT
echo "[setup_env] ✔ Tier 3 complete"

# ----- Tier 4: vendored binaries → $CONDA_PREFIX/bin (stub) ----------
# No tools are vendored today. To add one:
#   1. add a build block to 0_build_vendored_tools.sh
#   2. add `link_if_exists "$TOOLS_DIR/<tool>/<binary>"` below

link_if_exists() {
    local src="$1"
    local name
    name="$(basename "$src")"
    if [ -e "$src" ]; then
        chmod +x "$src" 2>/dev/null || true
        ln -sf "$src" "$ENV_BIN/$name"
        echo "  ✔ linked $name"
    else
        echo "  ⚠ skipped $name (not found at $src)"
    fi
}

echo "[setup_env] Tier 4: linking vendored tools (currently empty stub)"
# Add link_if_exists calls here when vendoring real tools.
echo "[setup_env] ✔ Tier 4 complete (no tools vendored)"

# ----- summary ------------------------------------------------------

cat <<EOF

[setup_env] ✔ env '$ENV_NAME' is ready.

  conda activate $ENV_NAME

To rebuild from scratch:
  $INSTALLER env remove -n $ENV_NAME -y
  bash 0_setup_env.sh

To vendor a new tool (currently no vendored tools):
  see tools/README.md and 0_build_vendored_tools.sh

EOF
