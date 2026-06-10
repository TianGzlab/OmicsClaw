#!/usr/bin/env bash
# OmicsClaw — bulk-ATAC tool installer
#
# Populates two conda envs for the bulk-ATAC skills:
#   omicsclaw_bulkatac  — every external CLI + Python lib the skills need
#   omicsclaw_tobias    — TOBIAS only (footprinting; pandas<2, isolated
#                         because it conflicts with pyDESeq2's pandas>=2)
# Idempotent and re-runnable: each tool is checked first and only
# installed if missing.
#
# Per-tool install strategy (each step tried only if the previous failed):
#   1. mamba install --override-channels -c bioconda -c conda-forge <pkg>
#   2. pip install <pkg>
#   3. from source — clone the GitHub repo into OmicsClaw/tools/<name>
#      (skipping the download if tools/<name> already exists), then build.
#
# --override-channels: query ONLY bioconda + conda-forge, ignoring any
# `defaults`/mirror channels in the user's ~/.condarc. Without it conda merges
# those in and also downloads the anaconda main/r repodata indexes — slow over
# flat-repodata mirrors and pointless, since none of these packages live there.
#
# Usage:
#     bash 0_setup_env_for_bulkatac.sh

set -euo pipefail

ENV_NAME="omicsclaw_bulkatac"
TOBIAS_ENV="omicsclaw_tobias"
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOLS_DIR="$PROJECT_ROOT/tools"

# Route every `pip install` below through a fast PyPI mirror. pip reads
# PIP_INDEX_URL from the environment, so this single export covers all pip
# call sites (agent runtime libs, analysis libs, TOBIAS) without editing each
# one. Defaults to the Tsinghua TUNA mirror (reliable from mainland China);
# override by exporting PIP_INDEX_URL before running, e.g.
#   PIP_INDEX_URL=https://pypi.org/simple bash 0_setup_env_for_bulkatac.sh
export PIP_INDEX_URL="${PIP_INDEX_URL:-https://pypi.tuna.tsinghua.edu.cn/simple}"

# ----- prerequisites ------------------------------------------------

if ! command -v conda >/dev/null 2>&1; then
    echo "[bulkatac] ✖ conda not on PATH — install Miniforge first." >&2
    exit 1
fi
if command -v mamba >/dev/null 2>&1; then
    CONDA_INSTALL="mamba"
else
    CONDA_INSTALL="conda"
fi

# ----- enter the omicsclaw_bulkatac conda env -----------------------
# `conda activate` needs the shell hook sourced in a non-interactive script.

CONDA_BASE="$(conda info --base)"
# shellcheck disable=SC1091
source "$CONDA_BASE/etc/profile.d/conda.sh"

if ! conda env list | awk 'NF && $1 !~ /^#/ {print $1}' | grep -qx "$ENV_NAME"; then
    echo "[bulkatac] env '$ENV_NAME' not found — creating it (python=3.11)"
    "$CONDA_INSTALL" create -y --override-channels -n "$ENV_NAME" -c conda-forge python=3.11
fi

conda activate "$ENV_NAME"
echo "[bulkatac] active env: ${CONDA_DEFAULT_ENV:-?}  (prefix: ${CONDA_PREFIX:-?})"
mkdir -p "$TOOLS_DIR"

# ----- helpers ------------------------------------------------------

# install_from_source <binary> <git_url>
#   Clones <git_url> into tools/<name> (reused if already downloaded),
#   then builds with the recipe detected from the source tree.
install_from_source() {
    local bin="$1" git_url="$2"
    [ -n "$git_url" ] || { echo "[bulkatac]     no source recipe for $bin" >&2; return 1; }
    local name dest
    name="$(basename "$git_url" .git)"
    dest="$TOOLS_DIR/$name"

    # Reuse an already-downloaded copy; only clone if absent.
    if [ -d "$dest" ]; then
        echo "[bulkatac]     tools/$name already downloaded — reusing"
    else
        echo "[bulkatac]     cloning $git_url → tools/$name"
        git clone --depth 1 --recursive "$git_url" "$dest" || return 1
    fi

    # Build with whichever recipe the source tree exposes.
    if [ -f "$dest/setup.py" ] || [ -f "$dest/pyproject.toml" ]; then
        pip install "$dest" || return 1
    elif [ -f "$dest/Makefile" ] || [ -f "$dest/configure" ]; then
        ( cd "$dest" && { [ -x ./configure ] && ./configure || true; } && make ) || return 1
        # Link the freshly built binary onto the env PATH.
        if [ -x "$dest/$bin" ]; then
            ln -sf "$dest/$bin" "$CONDA_PREFIX/bin/$bin"
        else
            local found
            found="$(find "$dest" -name "$bin" -type f -perm -u+x 2>/dev/null | head -1)"
            [ -n "$found" ] && ln -sf "$found" "$CONDA_PREFIX/bin/$bin"
        fi
    else
        echo "[bulkatac]     ✖ no build recipe found in tools/$name" >&2
        return 1
    fi
    command -v "$bin" >/dev/null 2>&1
}

# ensure_tool <binary> <conda_pkg> <pip_pkg|-> <git_url|->
#   Skip if <binary> is already on PATH; otherwise install via the
#   conda → pip → source fallback chain.
ensure_tool() {
    local bin="$1" conda_pkg="$2" pip_pkg="$3" git_url="$4"
    if command -v "$bin" >/dev/null 2>&1; then
        echo "[bulkatac]   ✔ $bin (already present)"
        return 0
    fi
    echo "[bulkatac]   … $bin missing — installing"
    # Install output is streamed live (only the `command -v` check is
    # silenced) so slow solves — e.g. TOBIAS — show progress, not silence.
    # 1. conda / mamba
    if [ "$conda_pkg" != "-" ] \
       && "$CONDA_INSTALL" install -y --override-channels -c bioconda -c conda-forge "$conda_pkg" \
       && command -v "$bin" >/dev/null 2>&1; then
        echo "[bulkatac]   ✔ $bin via conda ($conda_pkg)"
        return 0
    fi
    # 2. pip
    if [ "$pip_pkg" != "-" ] \
       && pip install "$pip_pkg" \
       && command -v "$bin" >/dev/null 2>&1; then
        echo "[bulkatac]   ✔ $bin via pip ($pip_pkg)"
        return 0
    fi
    # 3. from source
    if [ "$git_url" != "-" ] && install_from_source "$bin" "$git_url"; then
        echo "[bulkatac]   ✔ $bin from source"
        return 0
    fi
    echo "[bulkatac]   ✖ FAILED to install $bin — install it manually" >&2
    return 1
}

# ensure_pylib <import_name> <conda_pkg> <pip_pkg>
#   Same idea for the Python libs the skills' _lib modules import
#   (no source step — conda/pip always cover these).
ensure_pylib() {
    local mod="$1" conda_pkg="$2" pip_pkg="$3"
    if python -c "import $mod" >/dev/null 2>&1; then
        echo "[bulkatac]   ✔ python:$mod (already present)"
        return 0
    fi
    echo "[bulkatac]   … python:$mod missing — installing"
    # Install output streamed live; only the `import` check is silenced.
    if "$CONDA_INSTALL" install -y --override-channels -c conda-forge -c bioconda "$conda_pkg" \
       && python -c "import $mod" >/dev/null 2>&1; then
        echo "[bulkatac]   ✔ python:$mod via conda ($conda_pkg)"
        return 0
    fi
    if pip install "$pip_pkg" \
       && python -c "import $mod" >/dev/null 2>&1; then
        echo "[bulkatac]   ✔ python:$mod via pip ($pip_pkg)"
        return 0
    fi
    echo "[bulkatac]   ✖ FAILED to install python:$mod" >&2
    return 1
}

# ensure_pylib_pip <import_name> <pip_pkg>
#   pip-only variant of ensure_pylib for pure-Python packages.  Skips the
#   conda step entirely: these have no compiled extensions, so conda's
#   repodata download (a ~200 MB flat index per channel when the mirror
#   serves no shard index) + SAT solve is pure overhead — pip installs
#   them in seconds.
ensure_pylib_pip() {
    local mod="$1" pip_pkg="$2"
    if python -c "import $mod" >/dev/null 2>&1; then
        echo "[bulkatac]   ✔ python:$mod (already present)"
        return 0
    fi
    echo "[bulkatac]   … python:$mod missing — pip install"
    if pip install "$pip_pkg" \
       && python -c "import $mod" >/dev/null 2>&1; then
        echo "[bulkatac]   ✔ python:$mod via pip ($pip_pkg)"
        return 0
    fi
    echo "[bulkatac]   ✖ FAILED to install python:$mod" >&2
    return 1
}

# ----- OmicsClaw agent env -----------------------------------------
# Even when you only develop the bulk-ATAC module, the skills are run
# *through the OmicsClaw agent*, which lives in its own env ('OmicsClaw',
# CamelCase — distinct from the lowercase tool/sub-envs above).  So this
# env is required regardless.
#
# This installs ONLY the minimal agent runtime — NOT the full
# environment.yml multi-omics stack (scanpy, torch, squidpy, ...).  The
# package list mirrors the "Server / notebook runtime" group in
# environment.yml; `pip install -e .` then pulls the omicsclaw package's
# own Tier-1 core deps (setuptools, socksio) from pyproject.toml.
AGENT_ENV="OmicsClaw"

echo "[bulkatac] setting up '$AGENT_ENV' (skill-runner agent) ..."
if ! conda env list | awk 'NF && $1 !~ /^#/ {print $1}' | grep -qx "$AGENT_ENV"; then
    echo "[bulkatac] env '$AGENT_ENV' not found — creating it (python=3.11)"
    "$CONDA_INSTALL" create -y --override-channels -n "$AGENT_ENV" -c conda-forge python=3.11
fi
conda activate "$AGENT_ENV"
echo "[bulkatac] active env: ${CONDA_DEFAULT_ENV:-?}"

# The omicsclaw package itself — editable install if not importable.
if python -c "import omicsclaw" >/dev/null 2>&1; then
    echo "[bulkatac]   ✔ python:omicsclaw (already present)"
else
    echo "[bulkatac]   … omicsclaw package missing — pip install -e ."
    pip install -e "$PROJECT_ROOT"
fi

# Minimal agent runtime libs — installed via pip (ensure_pylib_pip).
# All pure-Python, so pip is fast and conda's repodata/solve is skipped.
# nbformat is what enables the analysis-notebook export step — without it
# the runner only warns "nbformat is not installed; skipping notebook
# export" and the .ipynb is not produced.
echo "[bulkatac] checking OmicsClaw agent runtime libraries ..."
ensure_pylib_pip yaml           "pyyaml>=6.0"
ensure_pylib_pip rich           "rich>=13.0.0"
ensure_pylib_pip pydantic       "pydantic>=2.0,<3.0"
ensure_pylib_pip nbformat       "nbformat>=5.9"
ensure_pylib_pip jupyter_client "jupyter_client>=8.0"
ensure_pylib_pip ipykernel      "ipykernel>=6.0"
ensure_pylib_pip greenlet       "greenlet>=3.0.0"
ensure_pylib_pip prompt_toolkit "prompt-toolkit>=3.0"
ensure_pylib_pip questionary    "questionary>=2.0"

# Memory-tier libs — enable persistent bot memory across Feishu reconnects.
# Without these, bot/session.py:318 logs "Memory dependencies not installed,
# skipping memory init" and the bot loses all cross-session recall (every
# Feishu disconnect/reconnect wipes its context, so it can't tell when a
# skill has already run). These 8 packages are the canonical memory tier
# documented in pyproject.toml `[memory]` (which is itself a no-op because
# the packages were moved to environment.yml Tier 4 — installing them here
# keeps the bot working when users skip the full environment.yml install).
# Default SQLite DB lands at ~/.config/omicsclaw/memory.db; override with
# OMICSCLAW_MEMORY_DB_URL in .env if you want it elsewhere.
ensure_pylib_pip aiosqlite      "aiosqlite>=0.19"
ensure_pylib_pip sqlalchemy     "sqlalchemy>=2.0"
ensure_pylib_pip cryptography   "cryptography>=41.0"
ensure_pylib_pip fastapi        "fastapi>=0.110"
ensure_pylib_pip uvicorn        "uvicorn>=0.27"
ensure_pylib_pip requests       "requests>=2.31"
ensure_pylib_pip openai         "openai>=1.30"
ensure_pylib_pip dotenv         "python-dotenv>=1.0"

conda activate "$ENV_NAME"

# ----- bulk-ATAC CLI tools ------------------------------------------
# Tool list verified against every which()/_check_tool()/_require() call
# and subprocess invocation in skills/epigenomics/_lib/*.py + the scripts.
# bedtools>=2.30 is code-specified (_lib/footprinting.py:21). samtools is
# floored at >=1.13 (the code's own note says 1.10 at _lib/footprinting.py:20,
# but 1.13 is pinned here as a safe modern minimum). All others → latest.
#               <binary>            <conda_pkg>           <pip_pkg>  <git_url>
echo "[bulkatac] checking CLI tools ..."
ensure_tool samtools            "samtools>=1.13"      -          https://github.com/samtools/samtools
ensure_tool bwa                 bwa                   -          https://github.com/lh3/bwa
ensure_tool bowtie2             bowtie2               -          https://github.com/BenLangmead/bowtie2
ensure_tool fastqc              fastqc                -          https://github.com/s-andrews/FastQC
ensure_tool fastp               fastp                 -          https://github.com/OpenGene/fastp
ensure_tool trim_galore         trim-galore           -          https://github.com/FelixKrueger/TrimGalore
ensure_tool macs2               macs2                 macs2      https://github.com/macs3-project/MACS
ensure_tool bedtools            "bedtools>=2.30"      -          https://github.com/arq5x/bedtools2
ensure_tool bamCoverage         deeptools             deeptools  https://github.com/deeptools/deepTools
ensure_tool featureCounts       subread               -          -
ensure_tool annotatePeaks.pl    homer                 -          -
ensure_tool findMotifsGenome.pl homer                 -          -
# idr (Irreproducible Discovery Rate) is intentionally NOT auto-installed here:
#   • bioconda's idr has no python 3.11 build (tops out at 3.10) → it cannot
#     solve against this env's pinned python=3.11, and the doomed solve is slow.
#   • the PyPI name `idr` is an unrelated 2.6 kB squatter (idr 0.0.1), not the
#     real tool — `pip install idr` only pollutes the env (no `idr` binary).
#   • building nboley/idr from source needs numpy at build time, absent here.
# The peak-QC skill handles idr's absence: QC_after_peak_calling.py:_run_idr
# falls back to a native scipy IDR implementation (Li et al. 2011) when `idr`
# is not on PATH. Users who want the canonical external tool can install it in
# a dedicated python<=3.10 sub-env. (scipy arrives via pydeseq2.)
ensure_tool fetchChromSizes     ucsc-fetchchromsizes  -          -

# ----- analysis Python libraries ------------------------------------
# Installed pip-only (via PIP_INDEX_URL above) rather than conda: all four are
# pure-PyPI packages, and the conda path (-c bioconda -c conda-forge) hangs for
# minutes on the flat-repodata solve over slow mirrors. numpy is already
# supplied by the conda-installed deeptools/macs2, so pip sees it satisfied and
# won't replace it — no numpy ABI conflict with those tools.
echo "[bulkatac] checking Python libraries ..."
ensure_pylib_pip pandas      pandas
ensure_pylib_pip numpy       numpy
ensure_pylib_pip matplotlib  matplotlib
ensure_pylib_pip pydeseq2    pydeseq2

# ----- omicsclaw_tobias sub-env (footprinting / TOBIAS) -------------
# Installs TOBIAS per its maintainers' docs
# (https://github.com/loosolab/TOBIAS/wiki/installation): a minimal
# conda base + `pip install tobias`.
#
# Why NOT `conda install tobias -c bioconda`: the bioconda `tobias`
# recipe pulls `xgboost`, whose modern builds require a CUDA virtual
# package — it fails to solve on CPU-only hosts.
#
# Why a MINIMAL conda base (not TOBIAS's full tobias_env.yaml dep list):
# `pip install tobias` resolves the ENTIRE Python tree (pysam, pybigwig,
# MOODS, numpy>=2, scipy, scikit-learn, pandas, adjustText, ...) as one
# mutually-consistent set. conda only needs to provide what pip cannot:
# python>=3.12,<3.14 and the two external CLI programs TOBIAS shells out
# to (samtools, bedtools). Installing TOBIAS's whole dep list via conda
# also tripped channel-name mismatches — e.g. conda lowercases the YAML's
# `adjustText` to `adjusttext`, which is not a package name on the
# configured channels.
#
# IMPORTANT: pin python<3.14. Python 3.14 changed the default
# multiprocessing start method on Linux from `fork` to `forkserver`.
# TOBIAS 0.17.3's logger (utils/logger.py:130 `self.listener.start()`)
# uses a QueueListener whose internals contain RLock / file handle
# objects that are not picklable, which is what `forkserver` requires.
# Result: ATACorrect crashes inside reduction.dump(process_obj, buf)
# before any real work happens. Pinning to 3.13 keeps the fork default.
TOBIAS_ENV_PKGS=( "python>=3.12,<3.14" pip samtools bedtools )

echo "[bulkatac] setting up '$TOBIAS_ENV' (footprinting / TOBIAS) ..."

# Self-healing Python-version check: an existing env built before this
# pin landed may still be on Python 3.14 (the upstream conda default once
# 3.14 shipped). That version is incompatible with TOBIAS 0.17.3 (see
# comment block above). Detect and rebuild rather than silently leaving
# a broken env in place.
_tobias_env_python_bin="$(conda info --base 2>/dev/null)/envs/${TOBIAS_ENV}/bin/python"
if [ -x "$_tobias_env_python_bin" ]; then
    _tobias_env_python_ver="$("$_tobias_env_python_bin" -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null || echo "unknown")"
    case "$_tobias_env_python_ver" in
        3.12|3.13)
            echo "[bulkatac] env '$TOBIAS_ENV' already has python ${_tobias_env_python_ver} (OK)"
            ;;
        *)
            echo "[bulkatac] env '$TOBIAS_ENV' has python ${_tobias_env_python_ver} — incompatible with TOBIAS, rebuilding"
            "$CONDA_INSTALL" env remove -y -n "$TOBIAS_ENV"
            ;;
    esac
fi

if ! conda env list | awk 'NF && $1 !~ /^#/ {print $1}' | grep -qx "$TOBIAS_ENV"; then
    echo "[bulkatac] env '$TOBIAS_ENV' not found — creating minimal base (python>=3.12,<3.14, samtools, bedtools)"
    "$CONDA_INSTALL" create -y --override-channels -n "$TOBIAS_ENV" -c bioconda -c conda-forge "${TOBIAS_ENV_PKGS[@]}"
fi
conda activate "$TOBIAS_ENV"
echo "[bulkatac] active env: ${CONDA_DEFAULT_ENV:-?}"
# conda_pkg is "-": skip the conda step — `conda install tobias` is known
# to fail on CPU-only hosts (xgboost/CUDA). pip is the documented path;
# source clone is the last-resort fallback.
ensure_tool TOBIAS - tobias https://github.com/loosolab/TOBIAS

# TOBIAS 0.17.3 declares `pandas` with no upper bound, so pip resolves to
# pandas 3.x — which breaks BINDetect at bindetect.py:770:
#     info_table.at[names[i], base + "_highlighted"] = False
# `names[i]` is `Series.__getitem__(integer)` on a non-integer-indexed
# Series. Pandas 2 had a positional-access fallback; pandas 3 removed it
# and raises KeyError. Pin pandas<3 in this env only — omicsclaw_bulkatac
# (which uses pyDESeq2 with its own pandas<2 pin) is unaffected.
echo "[bulkatac]   … pinning pandas<3 in $TOBIAS_ENV (TOBIAS BINDetect incompatible with pandas 3)"
pip install --quiet 'pandas<3' \
    && echo "[bulkatac]   ✔ pandas pinned to $(python -c 'import pandas; print(pandas.__version__)')" \
    || echo "[bulkatac]   ✖ failed to pin pandas<3 — BINDetect may fail at runtime" >&2

conda activate "$ENV_NAME"

# ----- summary ------------------------------------------------------

cat <<EOF

[bulkatac] ✔ done — all three envs are ready:
    $AGENT_ENV       — OmicsClaw agent runtime (runs the skills; minimal deps)
    $ENV_NAME  — bulk-ATAC CLIs + Python libs (skills auto-relocate here)
    $TOBIAS_ENV    — TOBIAS for the footprinting skill (isolated dep tree)

  Re-run this script any time; already-present tools are skipped.

EOF
