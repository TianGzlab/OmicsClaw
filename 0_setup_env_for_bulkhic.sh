#!/usr/bin/env bash
# OmicsClaw — bulk-Hi-C tool installer
#
# Populates the conda env for the bulk-Hi-C (chromosome-conformation) skills:
#   omicsclaw_bulkhic  — every external CLI + Python lib the skills need
#
# The bulk-Hi-C skills auto-relocate into omicsclaw_bulkhic at runtime via
# skills/epigenomics/bulkhic/_lib/subenv_bootstrap.py (ensure_bulkhic_env).
#
# Idempotent and re-runnable: each tool is checked first and only installed if
# missing.
#
# Per-tool install strategy (each step tried only if the previous failed):
#   1. mamba install --override-channels -c bioconda -c conda-forge <pkg>
#   2. pip install <pkg>
#   3. from source — clone the GitHub repo into OmicsClaw/tools/<name>.
#
# Usage:
#     bash 0_setup_env_for_bulkhic.sh

set -euo pipefail

ENV_NAME="omicsclaw_bulkhic"
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOLS_DIR="$PROJECT_ROOT/tools"

export PIP_INDEX_URL="${PIP_INDEX_URL:-https://pypi.tuna.tsinghua.edu.cn/simple}"

# ----- prerequisites ------------------------------------------------

if ! command -v conda >/dev/null 2>&1; then
    echo "[bulkhic] ✖ conda not on PATH — install Miniforge first." >&2
    exit 1
fi
if command -v mamba >/dev/null 2>&1; then
    CONDA_INSTALL="mamba"
else
    CONDA_INSTALL="conda"
fi

# ----- enter the omicsclaw_bulkhic conda env ------------------------

CONDA_BASE="$(conda info --base)"
# shellcheck disable=SC1091
source "$CONDA_BASE/etc/profile.d/conda.sh"

if ! conda env list | awk 'NF && $1 !~ /^#/ {print $1}' | grep -qx "$ENV_NAME"; then
    echo "[bulkhic] env '$ENV_NAME' not found — creating it (python=3.11)"
    "$CONDA_INSTALL" create -y --override-channels -n "$ENV_NAME" -c conda-forge python=3.11
fi

conda activate "$ENV_NAME"
echo "[bulkhic] active env: ${CONDA_DEFAULT_ENV:-?}  (prefix: ${CONDA_PREFIX:-?})"
mkdir -p "$TOOLS_DIR"

# ----- helpers ------------------------------------------------------

# install_from_source <binary> <git_url>
install_from_source() {
    local bin="$1" git_url="$2"
    [ -n "$git_url" ] || { echo "[bulkhic]     no source recipe for $bin" >&2; return 1; }
    local name dest
    name="$(basename "$git_url" .git)"
    dest="$TOOLS_DIR/$name"

    if [ -d "$dest" ]; then
        echo "[bulkhic]     tools/$name already downloaded — reusing"
    else
        echo "[bulkhic]     cloning $git_url → tools/$name"
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
        echo "[bulkhic]     ✖ no build recipe found in tools/$name" >&2
        return 1
    fi
    command -v "$bin" >/dev/null 2>&1
}

# ensure_tool <binary> <conda_pkg> <pip_pkg|-> <git_url|->
ensure_tool() {
    local bin="$1" conda_pkg="$2" pip_pkg="$3" git_url="$4"
    if command -v "$bin" >/dev/null 2>&1; then
        echo "[bulkhic]   ✔ $bin (already present)"
        return 0
    fi
    echo "[bulkhic]   … $bin missing — installing"
    if [ "$conda_pkg" != "-" ] \
       && "$CONDA_INSTALL" install -y --override-channels -c bioconda -c conda-forge "$conda_pkg" \
       && command -v "$bin" >/dev/null 2>&1; then
        echo "[bulkhic]   ✔ $bin via conda ($conda_pkg)"
        return 0
    fi
    if [ "$pip_pkg" != "-" ] \
       && pip install "$pip_pkg" \
       && command -v "$bin" >/dev/null 2>&1; then
        echo "[bulkhic]   ✔ $bin via pip ($pip_pkg)"
        return 0
    fi
    if [ "$git_url" != "-" ] && install_from_source "$bin" "$git_url"; then
        echo "[bulkhic]   ✔ $bin from source"
        return 0
    fi
    echo "[bulkhic]   ✖ FAILED to install $bin — install it manually" >&2
    return 1
}

# ensure_pylib_pip <import_name> <pip_pkg>  (pip-only; pure-Python packages)
ensure_pylib_pip() {
    local mod="$1" pip_pkg="$2"
    if python -c "import $mod" >/dev/null 2>&1; then
        echo "[bulkhic]   ✔ python:$mod (already present)"
        return 0
    fi
    echo "[bulkhic]   … python:$mod missing — pip install"
    if pip install "$pip_pkg" \
       && python -c "import $mod" >/dev/null 2>&1; then
        echo "[bulkhic]   ✔ python:$mod via pip ($pip_pkg)"
        return 0
    fi
    echo "[bulkhic]   ✖ FAILED to install python:$mod" >&2
    return 1
}

# ----- OmicsClaw agent env -----------------------------------------
# The skills are run *through the OmicsClaw agent*, which lives in its own env
# ('OmicsClaw', CamelCase — distinct from the lowercase tool/sub-env above).
AGENT_ENV="OmicsClaw"

echo "[bulkhic] setting up '$AGENT_ENV' (skill-runner agent) ..."
if ! conda env list | awk 'NF && $1 !~ /^#/ {print $1}' | grep -qx "$AGENT_ENV"; then
    echo "[bulkhic] env '$AGENT_ENV' not found — creating it (python=3.11)"
    "$CONDA_INSTALL" create -y --override-channels -n "$AGENT_ENV" -c conda-forge python=3.11
fi
conda activate "$AGENT_ENV"
echo "[bulkhic] active env: ${CONDA_DEFAULT_ENV:-?}"

if python -c "import omicsclaw" >/dev/null 2>&1; then
    echo "[bulkhic]   ✔ python:omicsclaw (already present)"
else
    echo "[bulkhic]   … omicsclaw package missing — pip install -e ."
    pip install -e "$PROJECT_ROOT"
fi

echo "[bulkhic] checking OmicsClaw agent runtime libraries ..."
ensure_pylib_pip yaml           "pyyaml>=6.0"
ensure_pylib_pip rich           "rich>=13.0.0"
ensure_pylib_pip pydantic       "pydantic>=2.0,<3.0"
ensure_pylib_pip nbformat       "nbformat>=5.9"
ensure_pylib_pip jupyter_client "jupyter_client>=8.0"
ensure_pylib_pip ipykernel      "ipykernel>=6.0"
ensure_pylib_pip greenlet       "greenlet>=3.0.0"
ensure_pylib_pip prompt_toolkit "prompt-toolkit>=3.0"
ensure_pylib_pip questionary    "questionary>=2.0"
ensure_pylib_pip aiosqlite      "aiosqlite>=0.19"
ensure_pylib_pip sqlalchemy     "sqlalchemy>=2.0"
ensure_pylib_pip cryptography   "cryptography>=41.0"
ensure_pylib_pip fastapi        "fastapi>=0.110"
ensure_pylib_pip uvicorn        "uvicorn>=0.27"
ensure_pylib_pip requests       "requests>=2.31"
ensure_pylib_pip openai         "openai>=1.30"
ensure_pylib_pip dotenv         "python-dotenv>=1.0"

conda activate "$ENV_NAME"

# ----- bulk-Hi-C CLI tools ------------------------------------------
# Upstream: bwa-mem2/bwa (-SP5M), samtools, pairtools, pairix.
# Matrix + downstream: cooler, cooltools, coolpup.py (open2c).
# seqtk is only for demo subsampling. Java + juicer_tools.jar (below) are
# OPTIONAL — only needed for the .hic (Juicebox) export.
#
# IMPORTANT: pairtools / pairix / cooler / cooltools / coolpup.py are
# pure-PyPI packages — install them via PIP (conda_pkg = "-"), NOT conda. On
# hosts where mamba's shard index is unavailable, each `conda install` falls
# back to parsing the full flat bioconda/conda-forge repodata (~25+ min PER
# solve); pip from PIP_INDEX_URL takes seconds. Only the genuinely-compiled
# tools (samtools, bwa-mem2, bwa, fastqc, fastp) go through conda.
#               <binary>      <conda_pkg>        <pip_pkg>    <git_url>
echo "[bulkhic] checking CLI tools ..."
ensure_tool samtools     "samtools>=1.13"   -            https://github.com/samtools/samtools
ensure_tool bwa-mem2     bwa-mem2           -            https://github.com/bwa-mem2/bwa-mem2
ensure_tool bwa          bwa                -            https://github.com/lh3/bwa
ensure_tool fastqc       fastqc             -            https://github.com/s-andrews/FastQC
ensure_tool fastp        fastp              -            https://github.com/OpenGene/fastp
ensure_tool pairtools    -                  pairtools    https://github.com/open2c/pairtools
# pairix is NOT on PyPI and conda is slow here; it is OPTIONAL (bulkhic-mapping
# guards it, and `cooler cload pairs` reads the .pairs.gz without a pairix index).
# Check only — never block the install over it.
if command -v pairix >/dev/null 2>&1; then
    echo "[bulkhic]   ✔ pairix (present)"
else
    echo "[bulkhic]   (pairix not found — optional; cooler cload reads .pairs.gz without it. Enable: conda install -c bioconda pairix)"
fi
ensure_tool cooler       -                  cooler       https://github.com/open2c/cooler
ensure_tool cooltools    -                  cooltools    https://github.com/open2c/cooltools
ensure_tool coolpup.py   -                  coolpuppy    https://github.com/open2c/coolpuppy
# Mustache (bulkhic-loops caller) needs numpy<2 → installed in its OWN env below.
# seqtk is optional (demo subsampling only; bulkhic falls back to `head`).
# pip has no seqtk → source build; non-fatal.
ensure_tool seqtk        -                  -            https://github.com/lh3/seqtk \
    || echo "[bulkhic]   (seqtk optional — only for --demo-n-reads subsampling; skipped)"
# Java for the optional .hic export (juicer_tools pre). Install openjdk if absent.
if command -v java >/dev/null 2>&1; then
    echo "[bulkhic]   OK java (present)"
else
    echo "[bulkhic]   ... java not found - installing openjdk (for .hic export)"
    "$CONDA_INSTALL" install -y --override-channels -c conda-forge openjdk >/dev/null 2>&1 \
        && echo "[bulkhic]   OK openjdk installed" \
        || echo "[bulkhic]   (openjdk install failed - .hic export skipped; --format mcool still works)"
fi

# bedGraphToBigWig (UCSC) — lets `cooltools insulation --bigwig` emit genome-
# browser tracks (bioframe.to_bigwig shells out to it). OPTIONAL: insulation
# still writes its score/boundary TSV without it. Prefer the prebuilt UCSC
# static binary (fast, no conda solve); fall back to bioconda; non-fatal.
if command -v bedGraphToBigWig >/dev/null 2>&1; then
    echo "[bulkhic]   ✔ bedGraphToBigWig (already present)"
else
    echo "[bulkhic]   … bedGraphToBigWig missing — fetching UCSC static binary"
    _BG2BW_DEST="$CONDA_PREFIX/bin/bedGraphToBigWig"
    _BG2BW_URL="https://hgdownload.soe.ucsc.edu/admin/exe/linux.x86_64/bedGraphToBigWig"
    if command -v wget >/dev/null 2>&1 \
       && wget -q --tries=2 --timeout=30 -O "$_BG2BW_DEST" "$_BG2BW_URL" \
       && chmod +x "$_BG2BW_DEST" \
       && "$_BG2BW_DEST" 2>&1 | grep -qi "bedGraphToBigWig"; then
        echo "[bulkhic]   ✔ bedGraphToBigWig (UCSC static binary)"
    else
        rm -f "$_BG2BW_DEST"
        ensure_tool bedGraphToBigWig ucsc-bedgraphtobigwig - - \
            || echo "[bulkhic]   (bedGraphToBigWig optional — insulation works without bigWig tracks)"
    fi
fi

# ----- analysis Python libraries ------------------------------------
echo "[bulkhic] checking Python libraries ..."
# pandas pinned <3: cooltools (eigs-cis / insulation) calls read_table(verbose=),
# a kwarg pandas 3.0 REMOVED → TypeError at runtime. The explicit downgrade block
# below also covers the case where pandas 3.x was already pulled in as a
# transitive dep of pairtools/cooler before this line runs.
ensure_pylib_pip pandas     "pandas<3"
ensure_pylib_pip numpy      numpy
ensure_pylib_pip scipy      scipy
ensure_pylib_pip matplotlib matplotlib
ensure_pylib_pip cooler     cooler
ensure_pylib_pip cooltools  cooltools
ensure_pylib_pip bioframe   bioframe
# coolpup.py → h5sparse imports pkg_resources (dropped in setuptools>=81) → pin <81.
ensure_pylib_pip pkg_resources "setuptools<81"
# coolpup.py writes its .clpy via pandas HDFStore -> needs pytables.
ensure_pylib_pip tables tables
# hicrep -> replicate reproducibility SCC (bulkhic-matrix QC); seaborn -> SCC heatmap.
ensure_pylib_pip hicrep hicrep
ensure_pylib_pip seaborn seaborn

# ----- cooltools-compatible pandas pin ------------------------------
# pip pulls bleeding-edge pandas as a transitive dep (e.g. pandas 3.x), but the
# released cooltools predates pandas 3.0 — which REMOVED the read_table(verbose=)
# kwarg cooltools' eigs-cis / insulation still pass → TypeError at runtime.
# Force pandas < 3 (2.2.x still carries the deprecated kwarg). ensure_pylib_pip
# above won't downgrade an already-imported pandas, so enforce it explicitly.
echo "[bulkhic] enforcing cooltools-compatible pandas (<3) ..."
if python -c "import pandas,sys; sys.exit(0 if int(pandas.__version__.split('.')[0])<3 else 1)"; then
    echo "[bulkhic]   ✔ pandas $(python -c 'import pandas;print(pandas.__version__)') (<3, OK for cooltools)"
else
    echo "[bulkhic]   downgrading pandas to <3 (cooltools incompatible with pandas 3.x)"
    pip install "pandas>=1.5,<3"
fi

# ----- juicer_tools jar (for bulkhic-matrix --format both .hic export) -----
# Aiden Lab Juicebox release jar; the `pre` subcommand is API-stable across
# 1.x/2.x. Download strategy: smartdl (tries direct, then the iKuuu userspace
# proxy on the CN boxes — fast Japan node) if present; otherwise curl direct +
# gh-proxy/ghproxy mirrors. .hic export is optional; .mcool always works.
JUICER_TOOLS_VER="${JUICER_TOOLS_VER:-2.20.00}"
JUICER_JAR="$TOOLS_DIR/juicer_tools.jar"
_JURL="https://github.com/aidenlab/Juicebox/releases/download/v${JUICER_TOOLS_VER}/juicer_tools.${JUICER_TOOLS_VER}.jar"
if [ -f "$JUICER_JAR" ]; then
    echo "[bulkhic]   OK juicer_tools.jar (already present)"
else
    echo "[bulkhic] fetching juicer_tools v${JUICER_TOOLS_VER} (~37 MB) for .hic export ..."
    # 1) smartdl: direct first, then the iKuuu proxy (fast on CN boxes)
    if [ -x "$HOME/proxy/smartdl.sh" ]; then
        "$HOME/proxy/smartdl.sh" "$_JURL" "$TOOLS_DIR" >/dev/null 2>&1 || true
        _vjar=$(ls -S "$TOOLS_DIR"/juicer_tools.*.jar 2>/dev/null | head -1)
        [ -n "$_vjar" ] && [ "$_vjar" != "$JUICER_JAR" ] && ln -sf "$(basename "$_vjar")" "$JUICER_JAR"
    fi
    # 2) fall back to curl direct + gh-proxy / ghproxy mirrors
    if [ ! -s "$JUICER_JAR" ] && command -v curl >/dev/null 2>&1; then
        for _u in "$_JURL" "https://gh-proxy.com/${_JURL}" "https://ghproxy.com/${_JURL}" "https://mirror.ghproxy.com/${_JURL}"; do
            echo "[bulkhic]   trying $_u"
            if curl -fSL --retry 4 --retry-delay 8 --retry-max-time 900 --connect-timeout 30 -C - "$_u" -o "$JUICER_JAR"; then break; fi
            rm -f "$JUICER_JAR"
        done
    fi
    if [ -s "$JUICER_JAR" ]; then
        echo "[bulkhic]   OK juicer_tools.jar (bulkhic-matrix --format both enabled)"
    else
        echo "[bulkhic]   (juicer_tools download failed - .hic export optional; --format mcool still works)"
    fi
fi

# ----- Mustache loop caller (dedicated numpy<2 env) -----------------
# mustache-hic calls np.nan_to_num(<scipy.sparse>, copy=False), which numpy>=2
# forbids; the bulkhic env is numpy>=2 (cooltools requires it). So Mustache gets
# its OWN env and bulkhic-loops/_lib/loops.py calls this env's `mustache` binary.
MUSTACHE_ENV="omicsclaw_mustache"
echo "[bulkhic] setting up '$MUSTACHE_ENV' (Mustache loop caller, numpy<2) ..."
if ! conda env list | awk 'NF && $1 !~ /^#/ {print $1}' | grep -qx "$MUSTACHE_ENV"; then
    "$CONDA_INSTALL" create -y --override-channels -n "$MUSTACHE_ENV" -c conda-forge \
        python=3.10 "numpy<2" scipy "pandas<3"
fi
if [ -x "$CONDA_BASE/envs/$MUSTACHE_ENV/bin/mustache" ]; then
    echo "[bulkhic]   OK mustache (env $MUSTACHE_ENV, already present)"
else
    echo "[bulkhic]   ... installing mustache-hic into $MUSTACHE_ENV"
    conda run -n "$MUSTACHE_ENV" pip install mustache-hic cooler \
        && echo "[bulkhic]   OK mustache (env $MUSTACHE_ENV)" \
        || echo "[bulkhic]   XX mustache install FAILED in $MUSTACHE_ENV" >&2
fi
conda activate "$ENV_NAME"

# ----- summary ------------------------------------------------------

cat <<EOF

[bulkhic] ✔ done — envs ready:
    $AGENT_ENV       — OmicsClaw agent runtime (runs the skills; minimal deps)
    $ENV_NAME  — bulk-Hi-C CLIs + Python libs (skills auto-relocate here)

  Re-run this script any time; already-present tools are skipped.
  .hic export (juicer_tools.jar + java) is OPTIONAL — cooler/cooltools is the
  primary analysis path.

EOF
