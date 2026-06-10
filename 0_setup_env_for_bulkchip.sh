#!/usr/bin/env bash
# OmicsClaw — bulk-ChIP tool installer
#
# Populates the conda env for the bulk-ChIP (ChIP-seq) skills:
#   omicsclaw_bulkchip  — every external CLI + Python lib the skills need
#
# The bulk-ChIP skills auto-relocate into omicsclaw_bulkchip at runtime via
# skills/epigenomics/bulkchip/_lib/subenv_bootstrap.py (ensure_bulkchip_env).
#
# Idempotent and re-runnable: each tool is checked first and only installed if
# missing.
#
# Per-tool install strategy (each step tried only if the previous failed):
#   1. mamba install --override-channels -c bioconda -c conda-forge <pkg>
#   2. pip install <pkg>
#   3. from source — clone the GitHub repo into OmicsClaw/tools/<name>.
#
# --override-channels: query ONLY bioconda + conda-forge, ignoring any
# `defaults`/mirror channels in the user's ~/.condarc. Without it conda merges
# those in and also downloads the anaconda main/r repodata indexes — slow over
# flat-repodata mirrors and pointless, since none of these packages live there.
#
# Usage:
#     bash 0_setup_env_for_bulkchip.sh

set -euo pipefail

ENV_NAME="omicsclaw_bulkchip"
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOLS_DIR="$PROJECT_ROOT/tools"

# Route every `pip install` below through a fast PyPI mirror. pip reads
# PIP_INDEX_URL from the environment, so this single export covers all pip
# call sites (agent runtime libs + the analysis-lib pip fallbacks) without
# editing each one. Defaults to the Tsinghua TUNA mirror (reliable from
# mainland China); override by exporting PIP_INDEX_URL before running, e.g.
#   PIP_INDEX_URL=https://pypi.org/simple bash 0_setup_env_for_bulkchip.sh
export PIP_INDEX_URL="${PIP_INDEX_URL:-https://pypi.tuna.tsinghua.edu.cn/simple}"

# ----- prerequisites ------------------------------------------------

if ! command -v conda >/dev/null 2>&1; then
    echo "[bulkchip] ✖ conda not on PATH — install Miniforge first." >&2
    exit 1
fi
if command -v mamba >/dev/null 2>&1; then
    CONDA_INSTALL="mamba"
else
    CONDA_INSTALL="conda"
fi

# ----- enter the omicsclaw_bulkchip conda env -----------------------

CONDA_BASE="$(conda info --base)"
# shellcheck disable=SC1091
source "$CONDA_BASE/etc/profile.d/conda.sh"

if ! conda env list | awk 'NF && $1 !~ /^#/ {print $1}' | grep -qx "$ENV_NAME"; then
    echo "[bulkchip] env '$ENV_NAME' not found — creating it (python=3.11)"
    "$CONDA_INSTALL" create -y --override-channels -n "$ENV_NAME" -c conda-forge python=3.11
fi

conda activate "$ENV_NAME"
echo "[bulkchip] active env: ${CONDA_DEFAULT_ENV:-?}  (prefix: ${CONDA_PREFIX:-?})"
mkdir -p "$TOOLS_DIR"

# ----- helpers ------------------------------------------------------

# install_from_source <binary> <git_url>
install_from_source() {
    local bin="$1" git_url="$2"
    [ -n "$git_url" ] || { echo "[bulkchip]     no source recipe for $bin" >&2; return 1; }
    local name dest
    name="$(basename "$git_url" .git)"
    dest="$TOOLS_DIR/$name"

    if [ -d "$dest" ]; then
        echo "[bulkchip]     tools/$name already downloaded — reusing"
    else
        echo "[bulkchip]     cloning $git_url → tools/$name"
        git clone --depth 1 --recursive "$git_url" "$dest" || return 1
    fi

    if [ -f "$dest/setup.py" ] || [ -f "$dest/pyproject.toml" ]; then
        pip install "$dest" || return 1
    elif [ -f "$dest/Makefile" ] || [ -f "$dest/configure" ]; then
        ( cd "$dest" && { [ -x ./configure ] && ./configure || true; } && make ) || return 1
        if [ -x "$dest/$bin" ]; then
            ln -sf "$dest/$bin" "$CONDA_PREFIX/bin/$bin"
        else
            local found
            found="$(find "$dest" -name "$bin" -type f -perm -u+x 2>/dev/null | head -1)"
            [ -n "$found" ] && ln -sf "$found" "$CONDA_PREFIX/bin/$bin"
        fi
    else
        echo "[bulkchip]     ✖ no build recipe found in tools/$name" >&2
        return 1
    fi
    command -v "$bin" >/dev/null 2>&1
}

# ensure_tool <binary> <conda_pkg> <pip_pkg|-> <git_url|->
ensure_tool() {
    local bin="$1" conda_pkg="$2" pip_pkg="$3" git_url="$4"
    if command -v "$bin" >/dev/null 2>&1; then
        echo "[bulkchip]   ✔ $bin (already present)"
        return 0
    fi
    echo "[bulkchip]   … $bin missing — installing"
    if [ "$conda_pkg" != "-" ] \
       && "$CONDA_INSTALL" install -y --override-channels -c bioconda -c conda-forge "$conda_pkg" \
       && command -v "$bin" >/dev/null 2>&1; then
        echo "[bulkchip]   ✔ $bin via conda ($conda_pkg)"
        return 0
    fi
    if [ "$pip_pkg" != "-" ] \
       && pip install "$pip_pkg" \
       && command -v "$bin" >/dev/null 2>&1; then
        echo "[bulkchip]   ✔ $bin via pip ($pip_pkg)"
        return 0
    fi
    if [ "$git_url" != "-" ] && install_from_source "$bin" "$git_url"; then
        echo "[bulkchip]   ✔ $bin from source"
        return 0
    fi
    echo "[bulkchip]   ✖ FAILED to install $bin — install it manually" >&2
    return 1
}

# ensure_pylib <import_name> <conda_pkg> <pip_pkg>
ensure_pylib() {
    local mod="$1" conda_pkg="$2" pip_pkg="$3"
    if python -c "import $mod" >/dev/null 2>&1; then
        echo "[bulkchip]   ✔ python:$mod (already present)"
        return 0
    fi
    echo "[bulkchip]   … python:$mod missing — installing"
    if "$CONDA_INSTALL" install -y --override-channels -c conda-forge -c bioconda "$conda_pkg" \
       && python -c "import $mod" >/dev/null 2>&1; then
        echo "[bulkchip]   ✔ python:$mod via conda ($conda_pkg)"
        return 0
    fi
    if pip install "$pip_pkg" \
       && python -c "import $mod" >/dev/null 2>&1; then
        echo "[bulkchip]   ✔ python:$mod via pip ($pip_pkg)"
        return 0
    fi
    echo "[bulkchip]   ✖ FAILED to install python:$mod" >&2
    return 1
}

# ensure_pylib_pip <import_name> <pip_pkg>  (pip-only; pure-Python packages)
ensure_pylib_pip() {
    local mod="$1" pip_pkg="$2"
    if python -c "import $mod" >/dev/null 2>&1; then
        echo "[bulkchip]   ✔ python:$mod (already present)"
        return 0
    fi
    echo "[bulkchip]   … python:$mod missing — pip install"
    if pip install "$pip_pkg" \
       && python -c "import $mod" >/dev/null 2>&1; then
        echo "[bulkchip]   ✔ python:$mod via pip ($pip_pkg)"
        return 0
    fi
    echo "[bulkchip]   ✖ FAILED to install python:$mod" >&2
    return 1
}

# ----- OmicsClaw agent env -----------------------------------------
# The skills are run *through the OmicsClaw agent*, which lives in its own env
# ('OmicsClaw', CamelCase — distinct from the lowercase tool/sub-env above).
# This installs ONLY the minimal agent runtime — mirroring the bulk-ATAC
# installer so a bulk-ChIP-only developer still gets a working agent.
AGENT_ENV="OmicsClaw"

echo "[bulkchip] setting up '$AGENT_ENV' (skill-runner agent) ..."
if ! conda env list | awk 'NF && $1 !~ /^#/ {print $1}' | grep -qx "$AGENT_ENV"; then
    echo "[bulkchip] env '$AGENT_ENV' not found — creating it (python=3.11)"
    "$CONDA_INSTALL" create -y --override-channels -n "$AGENT_ENV" -c conda-forge python=3.11
fi
conda activate "$AGENT_ENV"
echo "[bulkchip] active env: ${CONDA_DEFAULT_ENV:-?}"

if python -c "import omicsclaw" >/dev/null 2>&1; then
    echo "[bulkchip]   ✔ python:omicsclaw (already present)"
else
    echo "[bulkchip]   … omicsclaw package missing — pip install -e ."
    pip install -e "$PROJECT_ROOT"
fi

echo "[bulkchip] checking OmicsClaw agent runtime libraries ..."
ensure_pylib_pip yaml           "pyyaml>=6.0"
ensure_pylib_pip rich           "rich>=13.0.0"
ensure_pylib_pip pydantic       "pydantic>=2.0,<3.0"
ensure_pylib_pip nbformat       "nbformat>=5.9"
ensure_pylib_pip jupyter_client "jupyter_client>=8.0"
ensure_pylib_pip ipykernel      "ipykernel>=6.0"
ensure_pylib_pip greenlet       "greenlet>=3.0.0"
ensure_pylib_pip prompt_toolkit "prompt-toolkit>=3.0"
ensure_pylib_pip questionary    "questionary>=2.0"

# Memory-tier libs — enable persistent bot memory across reconnects.
ensure_pylib_pip aiosqlite      "aiosqlite>=0.19"
ensure_pylib_pip sqlalchemy     "sqlalchemy>=2.0"
ensure_pylib_pip cryptography   "cryptography>=41.0"
ensure_pylib_pip fastapi        "fastapi>=0.110"
ensure_pylib_pip uvicorn        "uvicorn>=0.27"
ensure_pylib_pip requests       "requests>=2.31"
ensure_pylib_pip openai         "openai>=1.30"
ensure_pylib_pip dotenv         "python-dotenv>=1.0"

conda activate "$ENV_NAME"

# ----- bulk-ChIP CLI tools ------------------------------------------
# Mirrors the bulk-ATAC stack (shared aligners/MACS2/deepTools/HOMER/idr/
# featureCounts) and adds the ChIP-specific cross-correlation QC tool:
#   phantompeakqualtools (run_spp.R) — NSC / RSC strand cross-correlation.
# TOBIAS is intentionally absent: footprinting is ATAC-only.
#               <binary>            <conda_pkg>            <pip_pkg>  <git_url>
echo "[bulkchip] checking CLI tools ..."
ensure_tool samtools            "samtools>=1.13"       -          https://github.com/samtools/samtools
ensure_tool bwa-mem2            bwa-mem2               -          https://github.com/bwa-mem2/bwa-mem2
ensure_tool bwa                 bwa                    -          https://github.com/lh3/bwa
ensure_tool bowtie2             bowtie2                -          https://github.com/BenLangmead/bowtie2
ensure_tool fastqc              fastqc                 -          https://github.com/s-andrews/FastQC
ensure_tool fastp               fastp                  -          https://github.com/OpenGene/fastp
ensure_tool trim_galore         trim-galore            -          https://github.com/FelixKrueger/TrimGalore
ensure_tool macs2               macs2                  macs2      https://github.com/macs3-project/MACS
ensure_tool bedtools            "bedtools>=2.30"       -          https://github.com/arq5x/bedtools2
ensure_tool bamCoverage         deeptools              deeptools  https://github.com/deeptools/deepTools
ensure_tool plotFingerprint     deeptools              deeptools  -
ensure_tool featureCounts       subread                -          -
ensure_tool annotatePeaks.pl    homer                  -          -
ensure_tool findMotifsGenome.pl homer                  -          -
# idr (Irreproducible Discovery Rate) is intentionally NOT auto-installed here:
#   • bioconda's idr has no python 3.11 build (tops out at 3.10) → it cannot
#     solve against this env's pinned python=3.11, and the doomed solve is slow.
#   • the PyPI name `idr` is an unrelated 2.6 kB squatter (idr 0.0.1), not the
#     real tool — `pip install idr` only pollutes the env (no `idr` binary).
#   • building nboley/idr from source needs numpy at build time, absent here.
# IDR is opt-in (`--idr`) in bulkchip-peak_calling and currently scaffolded
# (peak_calling.py:run_all_idr); when implemented it should mirror bulkatac's
# native scipy IDR fallback. Users who want the canonical external tool can
# install it in a dedicated python<=3.10 sub-env.
ensure_tool fetchChromSizes     ucsc-fetchchromsizes   -          -
ensure_tool run_spp.R           phantompeakqualtools   -          https://github.com/kundajelab/phantompeakqualtools

# ----- analysis Python libraries ------------------------------------
# gseapy powers the GO/KEGG enrichment in bulkchip-annotation-enrichment.
#
# These are installed pip-only (via PIP_INDEX_URL above) rather than conda:
# all five are pure-PyPI packages, and the conda path (-c bioconda -c
# conda-forge) hangs for minutes on the flat-repodata solve over slow mirrors.
# numpy is already supplied by the conda-installed deeptools/macs2, so pip sees
# it satisfied and won't replace it — no numpy ABI conflict with those tools.
echo "[bulkchip] checking Python libraries ..."
ensure_pylib_pip pandas      pandas
ensure_pylib_pip numpy       numpy
ensure_pylib_pip matplotlib  matplotlib
ensure_pylib_pip pydeseq2    pydeseq2
ensure_pylib_pip gseapy      gseapy

# ----- summary ------------------------------------------------------

cat <<EOF

[bulkchip] ✔ done — envs ready:
    $AGENT_ENV       — OmicsClaw agent runtime (runs the skills; minimal deps)
    $ENV_NAME  — bulk-ChIP CLIs + Python libs (skills auto-relocate here)

  Re-run this script any time; already-present tools are skipped.

EOF
