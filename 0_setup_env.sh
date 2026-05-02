#!/usr/bin/env bash
# OmicsClaw environment setup
#
# Strategy (4 tiers):
#   1. mamba/conda env create from environment.yml — Tier 0 toolchain +
#      Tier 1-3 R/CLI packages + Tier 4 heavy Python science stack.
#   2. uv pip install -e ".[full,singlecell-upstream]" for the thin pip
#      residue (omicsclaw editable + PyPI-only packages with no conda
#      recipe). Falls back to pip --resolver-max-rounds=200000 if uv
#      is unavailable. Plus pip install velocyto (no py3.11 bioconda
#      build).
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

# Shared conda installations often put the base package cache first
# (`$CONDA_ROOT/pkgs`). libmamba may try to remove/re-extract stale package
# directories there and fail with "Permission denied" for non-admin users.
# Unless the user explicitly configured CONDA_PKGS_DIRS, use a private cache.
if [ -z "${CONDA_PKGS_DIRS:-}" ]; then
    CONDA_PKGS_DIRS="${HOME}/.conda/pkgs"
    export CONDA_PKGS_DIRS
    mkdir -p "$CONDA_PKGS_DIRS"
    echo "[setup_env] using private conda package cache: $CONDA_PKGS_DIRS"
else
    echo "[setup_env] using configured conda package cache: $CONDA_PKGS_DIRS"
fi

# ----- Tier 1: declarative env from bioconda + conda-forge ----------

# Env-existence check matches by name (column 1 of `conda info --envs` /
# `mamba info --envs`). Envs created with --prefix in custom locations are
# listed by absolute path and won't match here — that's intentional; this
# script manages named envs only.
#
# Keep env listing separate from the installer. Some older Python-based mamba
# builds crash on `mamba env list` with:
#   AttributeError: 'Namespace' object has no attribute 'func'
# `conda info --envs` is the stable metadata path when conda is available;
# mamba remains the preferred installer for create/update/run below.
#
# CONDA_CHANNEL_PRIORITY=strict prefixes both create and update because
# `mamba env create`/`mamba env update` (libmamba env subcommand) do NOT
# accept --strict-channel-priority as a CLI flag in mamba 1.5.x; the env
# var is the supported way to enforce strict priority for env subcommands.
list_conda_envs() {
    if command -v conda >/dev/null 2>&1 && conda info --envs; then
        return 0
    fi
    if "$INSTALLER" info --envs; then
        return 0
    fi
    "$INSTALLER" env list
}

list_conda_info_json() {
    if command -v conda >/dev/null 2>&1 && conda info --json; then
        return 0
    fi
    "$INSTALLER" info --json
}

candidate_prefixes_from_env_list() {
    printf '%s\n' "$ENV_LIST_OUTPUT" | awk -v env_name="$ENV_NAME" '
        /^[[:space:]]*($|#)/ { next }
        {
            for (i = 1; i <= NF; i++) {
                if ($i ~ /^\//) {
                    n = split($i, parts, "/")
                    if (parts[n] == env_name) {
                        print $i
                    }
                }
            }
        }
    '
}

candidate_env_dirs() {
    if [ -n "${CONDA_ENVS_PATH:-}" ]; then
        printf '%s\n' "$CONDA_ENVS_PATH" | tr ':' '\n'
    fi
    if command -v python >/dev/null 2>&1; then
        list_conda_info_json 2>/dev/null | python -c 'import json, sys
try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(0)
for path in data.get("envs_dirs", []):
    print(path)
' || true
    fi
    if [ -n "${CONDA_ROOT:-}" ]; then
        printf '%s\n' "$CONDA_ROOT/envs"
    fi
    if command -v conda >/dev/null 2>&1; then
        conda_root="$(cd "$(dirname "$(command -v conda)")/.." && pwd)"
        printf '%s\n' "$conda_root/envs"
    fi
    printf '%s\n' "$HOME/.conda/envs"
}

check_prefix_candidate() {
    prefix="$1"
    [ -n "$prefix" ] || return 1
    if [ -d "$prefix/conda-meta" ]; then
        ENV_PREFIX_CANDIDATE="$prefix"
        return 0
    fi
    if [ -e "$prefix" ]; then
        echo "[setup_env] ✖ found incomplete conda env prefix: $prefix" >&2
        echo "  It exists but is not a registered/complete conda env." >&2
        echo "  Remove or repair it, then re-run:" >&2
        echo "    $INSTALLER env remove -p '$prefix' -y" >&2
        return 2
    fi
    return 1
}

find_named_prefix() {
    while IFS= read -r prefix; do
        check_prefix_candidate "$prefix"
        case $? in
            0) return 0 ;;
            2) return 2 ;;
        esac
    done < <(candidate_prefixes_from_env_list | awk 'NF && !seen[$0]++')

    while IFS= read -r env_dir; do
        [ -n "$env_dir" ] || continue
        check_prefix_candidate "$env_dir/$ENV_NAME"
        case $? in
            0) return 0 ;;
            2) return 2 ;;
        esac
    done < <(candidate_env_dirs | awk 'NF && !seen[$0]++')
    return 1
}

env_run() {
    if [ "$ENV_TARGET_MODE" = "prefix" ]; then
        "$INSTALLER" run -p "$ENV_TARGET_VALUE" --no-capture-output "$@"
    else
        "$INSTALLER" run -n "$ENV_TARGET_VALUE" --no-capture-output "$@"
    fi
}

ENV_LIST_OUTPUT="$(list_conda_envs)" || {
    echo "[setup_env] ✖ failed to list conda environments." >&2
    echo "  Try: conda info --envs" >&2
    echo "  If mamba reports \"Namespace object has no attribute func\", update mamba or keep conda on PATH." >&2
    exit 1
}

ENV_PREFIX_CANDIDATE=""
ENV_TARGET_MODE="name"
ENV_TARGET_VALUE="$ENV_NAME"
if printf '%s\n' "$ENV_LIST_OUTPUT" | awk '{print $1}' | grep -qx "$ENV_NAME"; then
    echo "[setup_env] env '$ENV_NAME' already exists — updating from environment.yml"
    CONDA_CHANNEL_PRIORITY=strict "$INSTALLER" env update -n "$ENV_NAME" -f "$ENV_FILE" --prune
else
    if find_named_prefix; then
        FIND_PREFIX_STATUS=0
    else
        FIND_PREFIX_STATUS=$?
    fi
    if [ "$FIND_PREFIX_STATUS" -eq 2 ]; then
        exit 1
    fi
    if [ "$FIND_PREFIX_STATUS" -eq 0 ]; then
    ENV_TARGET_MODE="prefix"
    ENV_TARGET_VALUE="$ENV_PREFIX_CANDIDATE"
    echo "[setup_env] env prefix '$ENV_TARGET_VALUE' exists but is not listed by name — updating by prefix"
    CONDA_CHANNEL_PRIORITY=strict "$INSTALLER" env update -p "$ENV_TARGET_VALUE" -f "$ENV_FILE" --prune
    else
    echo "[setup_env] creating env '$ENV_NAME' from environment.yml"
    CONDA_CHANNEL_PRIORITY=strict "$INSTALLER" env create -n "$ENV_NAME" -f "$ENV_FILE"
    fi
fi

# Resolve the env prefix once — needed by later tiers.
# --no-capture-output: avoid stdout buffering on some mamba versions.
ENV_PREFIX="$(env_run python -c 'import sys; print(sys.prefix)')"
if [ -z "$ENV_PREFIX" ] || [ ! -d "$ENV_PREFIX" ]; then
    echo "[setup_env] ✖ failed to resolve env prefix for '$ENV_NAME'" >&2
    echo "  ($INSTALLER run returned: '$ENV_PREFIX')" >&2
    exit 1
fi
ENV_BIN="$ENV_PREFIX/bin"
echo "[setup_env] env prefix: $ENV_PREFIX"

echo "[setup_env] ✔ Tier 1 complete"

# ----- Tier 2: thin pip residue -------------------------------------
# After Tier 1 mamba env creation, the bulk of Python deps are already
# installed (see environment.yml Tier 4). Tier 2 here only installs:
#   1. omicsclaw itself in editable mode
#   2. PyPI-only packages with no conda recipe (SpaGCN/GraphST/cellcharter/
#      paste-bio/flashdeconv/fastccc/pyVIA/tangram-sc/...)
#   3. velocyto (no Py3.11 bioconda build)
# Prefer `uv pip install` if available — its PubGrub resolver is dramatically
# faster than pip on the residual graph and never hits resolution-too-deep.
# Fall back to pip with --resolver-max-rounds bump for older toolchains.

echo "[setup_env] Tier 2.0: install editable omicsclaw + thin pip residue"

if [ -z "${SKLEARN_ALLOW_DEPRECATED_SKLEARN_PACKAGE_INSTALL:-}" ]; then
    export SKLEARN_ALLOW_DEPRECATED_SKLEARN_PACKAGE_INSTALL=True
    echo "[setup_env] allowing deprecated sklearn placeholder for upstream SpaGCN metadata"
fi

# uv lives in environment.yml Tier 0 so it should be present in the env's
# bin dir. If not (e.g. older env created before this change), fall back
# to pip with bumped --resolver-max-rounds.
if env_run uv --version >/dev/null 2>&1; then
    echo "[setup_env] using uv (PubGrub resolver) for thin pip residue"
    env_run uv pip install -e "$PROJECT_ROOT[full,singlecell-upstream]"
else
    echo "[setup_env] uv not found in env; falling back to pip with --resolver-max-rounds=200000"
    env_run pip install --resolver-max-rounds=200000 \
        -e "$PROJECT_ROOT[full,singlecell-upstream]"
fi

# Tier 2.1: tools that have no bioconda Python 3.11 build:
#   - velocyto.py: bioconda has only 3.6–3.10 and 3.12 builds, not 3.11.
#                  PyPI name is `velocyto` (the .py suffix is bioconda-only).
#                  velocyto 0.17.17 (latest, 2020) imports numpy at the top
#                  of setup.py without declaring it in [build-system].requires.
#                  Under PEP 517 build isolation, pip's temp build env has no
#                  numpy and the install fails. --no-build-isolation makes the
#                  build reuse the active env, where Tier 4 has already
#                  installed numpy via mamba.
echo "[setup_env] Tier 2.1: pip install velocyto (--no-build-isolation)"
env_run pip install --no-build-isolation "velocyto>=0.17.17"

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
# wrMisc is installed from CRAN here instead of conda because conda-forge's
# current r-wrmisc builds require R 4.4/4.5, while the main env stays on R 4.3.

echo "[setup_env] Tier 3: GitHub R packages (devtools::install_github)"
env_run Rscript - <<'RSCRIPT'
options(repos = c(CRAN = Sys.getenv("CRAN_MIRROR", "https://cloud.r-project.org")))
if (!requireNamespace("wrMisc", quietly = TRUE)) {
  cat("[r-extras] installing wrMisc from CRAN\n")
  install.packages("wrMisc", quiet = TRUE)
  if (!requireNamespace("wrMisc", quietly = TRUE)) {
    stop("[r-extras] FAILED to install wrMisc")
  }
}

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

# ----- Tier 5: optional sub-environments (Layer 4) -----------------
# Tools whose dependency pins conflict with the main env live in dedicated
# sub-envs named `omicsclaw_<tool>`, invoked at runtime via subprocess
# bridge (see omicsclaw/core/external_env.py).
#
# Bootstrap is opt-in: pass `--with-banksy` (or set OMICSCLAW_WITH_BANKSY=1)
# to install. Default skips to keep base-install fast.

bootstrap_subenv() {
    local sub_name="$1"
    local sub_yml="$2"
    if [ ! -f "$sub_yml" ]; then
        echo "[setup_env] ⚠ sub-env file missing: $sub_yml" >&2
        return 1
    fi
    if "$INSTALLER" env list | awk '{print $1}' | grep -qx "$sub_name"; then
        echo "[setup_env] sub-env '$sub_name' exists — updating"
        CONDA_CHANNEL_PRIORITY=strict "$INSTALLER" env update -n "$sub_name" -f "$sub_yml" --prune
    else
        echo "[setup_env] creating sub-env '$sub_name'"
        CONDA_CHANNEL_PRIORITY=strict "$INSTALLER" env create -n "$sub_name" -f "$sub_yml"
    fi
}

# Detect --with-banksy in any positional position (after $ENV_NAME = $1).
WITH_BANKSY=0
for arg in "$@"; do
    case "$arg" in
        --with-banksy) WITH_BANKSY=1 ;;
    esac
done

if [ "${OMICSCLAW_WITH_BANKSY:-0}" = "1" ] || [ "$WITH_BANKSY" = "1" ]; then
    echo "[setup_env] Tier 5: bootstrapping omicsclaw_banksy sub-env"
    bootstrap_subenv "omicsclaw_banksy" "$PROJECT_ROOT/environments/banksy.yml"
    echo "[setup_env] ✔ Tier 5 (banksy) complete"
else
    echo "[setup_env] Tier 5 skipped (set OMICSCLAW_WITH_BANKSY=1 or pass --with-banksy to enable banksy)"
fi

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
