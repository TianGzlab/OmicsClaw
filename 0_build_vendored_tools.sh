#!/usr/bin/env bash
# OmicsClaw vendored tool builder
#
# Add a build_<tool>() function below for each tool that meets the criteria
# in tools/README.md. Then add a `build_<tool>` call to the dispatch block
# at the bottom and a `link_if_exists` line to 0_setup_env.sh Tier 4.
#
# Each build function should be idempotent: re-running this script must be
# a no-op when binaries already exist.

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOLS_DIR="$PROJECT_ROOT/tools"
mkdir -p "$TOOLS_DIR"

# ----- sanity: required build tools must be on PATH -----------------

need_tool() {
    if ! command -v "$1" >/dev/null 2>&1; then
        echo "[build] ✖ missing build tool: $1" >&2
        echo "  Activate the conda env first:  conda activate OmicsClaw" >&2
        exit 1
    fi
}

need_tool git
need_tool make
need_tool cmake
need_tool autoreconf
need_tool libtool
# Add need_tool calls for tool-specific helpers (e.g. yaggo for Jellyfish)
# alongside the corresponding build block below.

# ----- conda-wrapped compiler propagation ---------------------------
# Some Makefiles hardcode `g++` and bypass conda's wrapper. We export
# CC/CXX explicitly so all builds use the wrapped compiler with the
# pinned sysroot.

if [ -z "${CC:-}" ] || [ -z "${CXX:-}" ]; then
    if [ -n "${CONDA_PREFIX:-}" ] && [ -x "$CONDA_PREFIX/bin/x86_64-conda-linux-gnu-gcc" ]; then
        export CC="$CONDA_PREFIX/bin/x86_64-conda-linux-gnu-gcc"
        export CXX="$CONDA_PREFIX/bin/x86_64-conda-linux-gnu-g++"
    else
        echo "[build] ✖ CC/CXX not set and conda compiler not found." >&2
        echo "  Activate the env:  conda activate OmicsClaw" >&2
        exit 1
    fi
fi
if [ -z "${AR:-}" ] && [ -x "${CONDA_PREFIX:-}/bin/x86_64-conda-linux-gnu-ar" ]; then
    export AR="$CONDA_PREFIX/bin/x86_64-conda-linux-gnu-ar"
fi
echo "[build] using CC=$CC CXX=$CXX AR=${AR:-<unset>}"

# Make env's headers and libs visible to bare Makefile compiler calls.
export CPATH="${CONDA_PREFIX}/include${CPATH:+:$CPATH}"
export LIBRARY_PATH="${CONDA_PREFIX}/lib${LIBRARY_PATH:+:$LIBRARY_PATH}"
export LD_LIBRARY_PATH="${CONDA_PREFIX}/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"

# ----- helpers ------------------------------------------------------

# clone_at_tag <repo_url> <dest> [<tag>]
# - fresh clone if $dest doesn't exist
# - checkout $tag if provided (safe to call on existing clone)
clone_at_tag() {
    local repo_url="$1"
    local dest="$2"
    local tag="${3:-}"

    if [ -d "$dest/.git" ]; then
        echo "  (reusing existing clone at $dest)"
    else
        rm -rf "$dest"
        git clone "$repo_url" "$dest"
    fi

    if [ -n "$tag" ]; then
        (cd "$dest" && (git fetch --tags --quiet 2>/dev/null || true) \
            && git checkout --quiet "$tag")
    fi
}

JOBS="$(nproc 2>/dev/null || echo 4)"

# Example template (commented out — uncomment + adapt when needed):
#
# build_examplebio() {
#     local name="examplebio"
#     local repo="https://github.com/example/examplebio.git"
#     local rev="v1.2.3"
#     local dest="$TOOLS_DIR/$name"
#
#     if [ -e "$dest/bin/examplebio" ]; then
#         echo "[vendored] $name already built — skipping"
#         return 0
#     fi
#
#     mkdir -p "$dest"
#     if [ ! -d "$dest/upstream" ]; then
#         git clone --depth 1 --branch "$rev" "$repo" "$dest/upstream"
#     fi
#
#     pushd "$dest/upstream" >/dev/null
#     mkdir -p "$dest/build"
#     cmake -B "$dest/build" -S . -DCMAKE_INSTALL_PREFIX="$dest"
#     cmake --build "$dest/build" -j"$(nproc)"
#     cmake --install "$dest/build"
#     popd >/dev/null
#
#     echo "[vendored] $name built — binaries in $dest/bin"
# }

# Dispatch — call build_<tool> for each vendored tool.
# Currently empty.

echo "[vendored] no tools to build (stub)"
