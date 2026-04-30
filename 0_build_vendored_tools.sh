#!/usr/bin/env bash
# Build vendored tools from upstream source.
#
# Run AFTER the conda env is created and activated, so the build toolchain
# (gxx / cmake / autoconf+automake+libtool / make) is on PATH:
#
#     conda activate OmicsClaw
#     bash 0_build_vendored_tools.sh
#     bash 0_setup_env.sh         # re-run to symlink any new binaries
#
# Currently builds NOTHING — this is a stub. To add a tool:
#   1. add a build block following the commented template at the bottom
#   2. add a `link_if_exists` line in 0_setup_env.sh Tier 4
#
# Idempotent by convention: each tool block must skip itself if its binary
# already exists. Force a rebuild by deleting tools/<dir>/.

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

# ────────────────────────────────────────────────────────────────────
#  Build blocks go below. None are active today.
# ────────────────────────────────────────────────────────────────────

# # ----- TEMPLATE: hifiasm vX.Y.Z (delete this block when adding real tool)
# if [ -x "$TOOLS_DIR/hifiasm/hifiasm" ]; then
#     echo "[hifiasm] already built — skipping"
# else
#     echo "[hifiasm] cloning & building vX.Y.Z"
#     clone_at_tag https://github.com/chhylp123/hifiasm "$TOOLS_DIR/hifiasm" X.Y.Z
#     (cd "$TOOLS_DIR/hifiasm" && make -j "$JOBS" CC="$CC" CXX="$CXX")
# fi

# ----- done ---------------------------------------------------------

cat <<EOF

[build] ✔ no vendored tools currently configured.

To add a tool:
  1. uncomment the template above (and rename for the real tool)
  2. add a matching link_if_exists call in 0_setup_env.sh Tier 4
  3. re-run:    bash 0_setup_env.sh

EOF
