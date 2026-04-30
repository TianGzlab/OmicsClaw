# OmicsClaw Conda-Primary Environment Management — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate OmicsClaw from pip+venv + standalone `install_r_dependencies.R` to a single-command, **mamba-first**, four-tier conda install. Keep the legacy venv path as a documented lightweight fallback.

**Architecture:** A new `0_setup_env.sh` drives four tiers in order — (1) `mamba|conda env create -f environment.yml` for non-Python deps (R, bioconda CLIs, build toolchain), (2) `pip install -e ".[full]"` for Python, (3) inline `Rscript -e 'devtools::install_github(...)'` for the 6 GitHub-only R packages, (4) symlink `tools/<bin>` into `$CONDA_PREFIX/bin` (currently a no-op stub). The full `install_r_dependencies.R` is removed; CRAN+Bioc go to environment.yml, GitHub goes inline in setup_env.sh.

**Tech stack:** `mamba`/`conda` (Miniforge), `bioconda` channel, `conda-forge` channel, `pip`, `bash` (`set -euo pipefail`), R 4.3 + `devtools`.

**Spec reference:** [`docs/superpowers/specs/2026-04-30-conda-env-management-design.md`](../specs/2026-04-30-conda-env-management-design.md)

**Pre-implementation environment check:** the engineer running this plan must have either `mamba` or `conda` on PATH. If only `conda` is available, implementation works but mamba-specific steps are skipped (noted per task).

---

## Phase 1 — `environment.yml`

### Task 1: Draft `environment.yml`

**Files:**
- Create: `environment.yml`

**Why:** Single declarative spec for everything that pip cannot install: R, bioconda CLIs, build toolchain. This is Tier 1 of the four-tier install. Drafting first (rather than incrementally) lets us validate all package names in a single solver run (Task 2).

- [ ] **Step 1: Write `environment.yml` with the full content below.**

```yaml
# OmicsClaw analysis environment
#
# Owns everything that pip cannot install reliably:
#   - bioinformatics CLIs (samtools, STAR, fastqc, bwa, ...)
#   - R 4.3 + CRAN + Bioconductor packages
#   - C/C++ build toolchain (for pip's compiled deps + future tools/ vendoring)
#
# Owns NOTHING from pyproject.toml — Python deps are pip's responsibility,
# installed by 0_setup_env.sh Tier 2 via `pip install -e ".[full]"`.
#
# Channel order matters: conda-forge first (broad scientific), bioconda
# second (genomics specific). Channel priority strict to avoid R-package
# conflicts between conda-forge's R rebuilds and bioconda's r-* mirror.
name: OmicsClaw
channels:
  - conda-forge
  - bioconda
  - nodefaults
dependencies:
  # ────────── Tier 0: Python interpreter + build toolchain ──────────
  - python=3.11
  - pip
  - gxx_linux-64=12.*
  - sysroot_linux-64=2.17
  - cmake
  - make
  - autoconf
  - automake
  - libtool
  - pkg-config
  - git

  # ────────── Tier 1: bioinformatics CLIs (pip can't ship these) ──────────
  # Alignment
  - samtools
  - bcftools
  - bwa
  - bwa-mem2
  - bowtie2
  - minimap2
  - hisat2
  - star
  # QC
  - fastqc
  - multiqc
  - fastp
  - trim-galore
  # Variant calling / postprocessing
  - gatk4
  - picard
  # Single-cell / RNA upstream
  - simpleaf
  - kb-python
  - velocyto.py

  # ────────── Tier 2: R 4.3 + CRAN packages (replaces install_r_dependencies.R, CRAN section) ──────────
  - r-base=4.3
  - r-devtools
  - r-biocmanager
  - r-dplyr
  - r-ggplot2
  - r-matrix
  - r-seurat
  - r-sctransform
  - r-harmony
  - r-soupx
  - r-openxlsx
  - r-hgnchelper
  - r-nmf
  - r-mclust
  - r-survival
  - r-msigdbr
  - r-ashr

  # ────────── Tier 3: Bioconductor packages (replaces install_r_dependencies.R, Bioc section) ──────────
  - bioconductor-singlecellexperiment
  - bioconductor-scran
  - bioconductor-scuttle
  - bioconductor-singler
  - bioconductor-celldex
  - bioconductor-scdblfinder
  - bioconductor-batchelor
  - bioconductor-muscat
  - bioconductor-spatialexperiment
  - bioconductor-zellkonverter
  - bioconductor-spotlight
  - bioconductor-deseq2
  - bioconductor-apeglm
  - bioconductor-edger
  - bioconductor-limma
  - bioconductor-wgcna
  - bioconductor-sva
  - bioconductor-clusterprofiler

  # NOTE: 6 GitHub-only R packages (spacexr/RCTD, CARD, CellChat, numbat,
  # SPARK, DoubletFinder) are NOT in this file — they have no bioconda
  # equivalent. They are installed via `devtools::install_github` in
  # 0_setup_env.sh Tier 3.
```

- [ ] **Step 2: Verify the file is syntactically valid YAML.**

Run: `python -c "import yaml; yaml.safe_load(open('environment.yml'))"`
Expected: no output (success).

- [ ] **Step 3: Commit the draft.**

```bash
git add environment.yml
git commit -m "chore(env): draft environment.yml for conda-primary install

Declares R 4.3 + CRAN/Bioc packages, bioconda CLIs, and build toolchain.
Will be wired to a 0_setup_env.sh driver in subsequent commits.
Pre-validation against bioconda happens in the next task."
```

**If something fails:** YAML syntax errors will surface at Step 2 — read the parser message, the file is small.

---

### Task 2: Validate `environment.yml` against bioconda

**Files:**
- Read: `environment.yml`

**Why:** Spec risk #1 — bioconda package name typos (e.g., `r-Seurat` vs `r-seurat`). This task forces the solver to verify every name *before* we wire it into the setup script. Failure here is cheap; failure later, after writing 5 more files, is expensive.

- [ ] **Step 1: Have `mamba` available, or fall back to `conda`.**

Run: `command -v mamba || command -v conda`
Expected: prints a path. If neither, install Miniforge first (https://github.com/conda-forge/miniforge) and re-run.

- [ ] **Step 2: Solve and create the env (full download).** This is the real test — solving alone catches typos but not full availability. Use a throwaway env name to avoid colliding with any existing `OmicsClaw` env.

Run:
```bash
INSTALLER=$(command -v mamba >/dev/null && echo mamba || echo conda)
$INSTALLER env create -f environment.yml -n OmicsClawValidate
```
Expected: solver succeeds, packages download, env is created. Watch for any "PackagesNotFoundError" — that names the offending package.

- [ ] **Step 3: Smoke-check the created env.**

Run:
```bash
$INSTALLER run -n OmicsClawValidate python --version
$INSTALLER run -n OmicsClawValidate Rscript --version
$INSTALLER run -n OmicsClawValidate samtools --version | head -1
$INSTALLER run -n OmicsClawValidate Rscript -e 'library(DESeq2); library(Seurat); cat("OK\n")'
```
Expected:
- Python 3.11.x
- Rscript 4.3.x
- samtools 1.x
- "OK" (no library load error)

- [ ] **Step 4: Remove the throwaway env.**

Run: `$INSTALLER env remove -n OmicsClawValidate -y`
Expected: env removed.

- [ ] **Step 5: If any package failed, fix the name in `environment.yml` and repeat Steps 2–4.** Common patterns:
  - `r-PackageName` must be lower-case → `r-packagename`
  - `bioconductor-PackageName` must be lower-case → `bioconductor-packagename`
  - Dashes, not underscores: `kb-python` not `kb_python`
  - `velocyto.py` keeps the dot — that is the canonical bioconda name
  - If a package truly doesn't exist on bioconda, move it to Tier 3 (GitHub) and note in spec — but for the listed packages this should not happen.

- [ ] **Step 6: Commit any name fixes.**

```bash
git add environment.yml
git commit -m "fix(env): correct bioconda package names after solver validation"
```
(Skip the commit if no fixes were needed.)

**If something fails:** if solving hangs >10 minutes on conda fallback, set `CONDA_SUBDIR=linux-64` and retry. If a package is missing, paste the exact name into `mamba search -c bioconda <name>` to see suggestions.

---

## Phase 2 — `0_setup_env.sh` (driver, tier-by-tier)

### Task 3: Write Tier 1 of `0_setup_env.sh` (env detect + create/update)

**Files:**
- Create: `0_setup_env.sh`

**Why:** The shell driver's first responsibility is detecting `mamba`/`conda` and applying `environment.yml`. Building tier-by-tier with verification between tiers means each tier is independently debugged.

- [ ] **Step 1: Create `0_setup_env.sh` with the Tier 1 skeleton.**

```bash
#!/usr/bin/env bash
# OmicsClaw environment setup
#
# Strategy (4 tiers):
#   1. mamba/conda env create from environment.yml (R, CLIs, build toolchain)
#   2. pip install -e ".[full]" (OmicsClaw + Python deps)
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

# Resolve the env prefix once — needed by Tier 4 below.
ENV_PREFIX="$("$INSTALLER" run -n "$ENV_NAME" python -c 'import sys; print(sys.prefix)')"
ENV_BIN="$ENV_PREFIX/bin"
echo "[setup_env] env prefix: $ENV_PREFIX"

echo "[setup_env] ✔ Tier 1 complete"
```

- [ ] **Step 2: Make executable.**

Run: `chmod +x 0_setup_env.sh`

- [ ] **Step 3: Run a fresh setup end-to-end (Tier 1 only).**

Run: `bash 0_setup_env.sh`
Expected: prints `using mamba` (or conda), creates `OmicsClaw` env, prints `Tier 1 complete`. Env appears in `mamba env list`.

- [ ] **Step 4: Run again to verify idempotent update path.**

Run: `bash 0_setup_env.sh`
Expected: prints `env 'OmicsClaw' already exists — updating ... --prune`, `Tier 1 complete`. No errors.

- [ ] **Step 5: Commit.**

```bash
git add 0_setup_env.sh
git commit -m "feat(env): add 0_setup_env.sh Tier 1 (env create/update)"
```

**If something fails:** if `env update --prune` errors on a re-run, the prior env may be in a half-broken state. `mamba env remove -n OmicsClaw && bash 0_setup_env.sh` recovers cleanly.

---

### Task 4: Add Tier 2 — `pip install -e ".[full]"`

**Files:**
- Modify: `0_setup_env.sh` (append after Tier 1)

**Why:** Python deps live in `pyproject.toml`; conda only owns Tier 1 components. Running `pip install -e ".[full]"` *inside* the freshly-built env wires OmicsClaw and all its Python optional extras (scvi-tools, cellrank, palantir, ...) into Tier 1's Python interpreter.

- [ ] **Step 1: Append the Tier 2 block to the end of `0_setup_env.sh`** (after the existing `echo "[setup_env] ✔ Tier 1 complete"` line — do NOT duplicate that line):

```bash

# ----- Tier 2: OmicsClaw editable + Python optional extras ----------
# pyproject.toml owns all Python deps. Running pip inside the env
# attaches them to the Tier 1 Python interpreter.

echo "[setup_env] Tier 2: pip install -e \".[full]\""
"$INSTALLER" run -n "$ENV_NAME" pip install -e "$PROJECT_ROOT[full]"
echo "[setup_env] ✔ Tier 2 complete"
```

- [ ] **Step 2: Run the full script.**

Run: `bash 0_setup_env.sh`
Expected: Tier 1 prints idempotent update, Tier 2 prints pip output, ends with `Tier 2 complete`.

- [ ] **Step 3: Verify OmicsClaw is importable in the env.**

Run:
```bash
INSTALLER=$(command -v mamba >/dev/null && echo mamba || echo conda)
$INSTALLER run -n OmicsClaw python -c "import omicsclaw; print(omicsclaw.__file__)"
$INSTALLER run -n OmicsClaw oc list 2>&1 | head -10
```
Expected: prints OmicsClaw's file path inside the project, and `oc list` shows the skill catalog.

- [ ] **Step 4: Commit.**

```bash
git add 0_setup_env.sh
git commit -m "feat(env): add Tier 2 (pip install -e .[full]) to 0_setup_env.sh"
```

**If something fails:** if pip resolves a numpy or torch version that conflicts with conda's, that means the spec's "pyproject.toml owns Python" boundary leaked. Diagnose: `pip list | grep -E '^(numpy|scipy|torch)'` and compare to `mamba list -n OmicsClaw numpy`. The fix is to remove any Python sci-deps that snuck into environment.yml.

---

### Task 5: Add Tier 3 — inline `Rscript` for GitHub-only R packages

**Files:**
- Modify: `0_setup_env.sh` (append after Tier 2)

**Why:** The 6 GitHub-only R packages (spacexr, CARD, CellChat, numbat, SPARK, DoubletFinder) have no bioconda equivalent. Per spec D3, they go inline as a heredoc in setup_env.sh — no separate R script. The block is idempotent: `requireNamespace()` skips already-installed packages.

- [ ] **Step 1: Append the Tier 3 block.**

```bash
# ----- Tier 3: GitHub-only R packages (no bioconda equivalent) ----------
# Idempotent: requireNamespace() skips already-installed packages.
# Compiles run inside the activated env so they pick up Tier 1's gxx +
# sysroot + R headers automatically.

echo "[setup_env] Tier 3: GitHub R packages (devtools::install_github)"
"$INSTALLER" run -n "$ENV_NAME" Rscript - <<'RSCRIPT'
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
```

- [ ] **Step 2: Run the full script.** First time may take 5–15 minutes (compiling RcppArmadillo etc.).

Run: `bash 0_setup_env.sh`
Expected: ends with `Tier 3 complete` and `all 6 GitHub R packages OK`.

- [ ] **Step 3: Verify each GitHub package loads.**

Run:
```bash
INSTALLER=$(command -v mamba >/dev/null && echo mamba || echo conda)
$INSTALLER run -n OmicsClaw Rscript -e '
  for (p in c("spacexr", "CARD", "CellChat", "numbat", "SPARK", "DoubletFinder")) {
    if (!requireNamespace(p, quietly=TRUE)) stop(paste("MISSING:", p))
    cat(p, "OK\n")
  }
'
```
Expected: 6 lines of `<pkg> OK`, no errors.

- [ ] **Step 4: Run the script a third time to confirm idempotence.**

Run: `bash 0_setup_env.sh`
Expected: Tier 3 prints 6 lines of `already installed — skipping`, then `Tier 3 complete`.

- [ ] **Step 5: Commit.**

```bash
git add 0_setup_env.sh
git commit -m "feat(env): add Tier 3 (GitHub R packages) to 0_setup_env.sh"
```

**If something fails:** the most common failure is a compile error inside `RcppArmadillo` or similar. Check the error: usually it's `error: unable to find R headers`. The fix is to ensure Tier 1's `gxx_linux-64` is on the env's PATH at `Rscript` time — `$INSTALLER run -n "$ENV_NAME"` already activates the env, so this should not happen. If it does, run `$INSTALLER list -n OmicsClaw | grep -E "(gxx|sysroot)"` and confirm both are installed.

---

### Task 6: Add Tier 4 — vendored binary symlinks (stub no-op)

**Files:**
- Modify: `0_setup_env.sh` (append after Tier 3)

**Why:** Future-ready scaffolding. Today `tools/` is empty so the loop is a no-op. The structure is identical to GenAsmClaw's tier so adding a real vendored tool later is a one-liner.

- [ ] **Step 1: Append the Tier 4 block.**

```bash
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
```

- [ ] **Step 2: Run the full script.**

Run: `bash 0_setup_env.sh`
Expected: ends with the summary block, prints `Tier 4 complete (no tools vendored)`.

- [ ] **Step 3: Commit.**

```bash
git add 0_setup_env.sh
git commit -m "feat(env): add Tier 4 (vendored symlink stub) to 0_setup_env.sh"
```

**If something fails:** unlikely — the stub touches no files. If `link_if_exists` is reported missing in a future task, check this task's append placement.

---

## Phase 3 — Vendoring framework stub

### Task 7: Write `0_build_vendored_tools.sh` stub

**Files:**
- Create: `0_build_vendored_tools.sh`

**Why:** The build helper for Tier 4 vendored tools. Today it builds nothing — only the helpers (`clone_at_tag`, build-tool sanity checks) are present, plus a commented template showing how a real build block looks. This way, adding a tool later is "fill in the template", not "design from scratch".

- [ ] **Step 1: Create the stub script.**

```bash
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
```

- [ ] **Step 2: Make executable.**

Run: `chmod +x 0_build_vendored_tools.sh`

- [ ] **Step 3: Run the stub end-to-end inside the activated env.**

Run:
```bash
INSTALLER=$(command -v mamba >/dev/null && echo mamba || echo conda)
$INSTALLER run -n OmicsClaw bash 0_build_vendored_tools.sh
```
Expected: prints `using CC=...`, then `no vendored tools currently configured.`. Exit 0.

- [ ] **Step 4: Commit.**

```bash
git add 0_build_vendored_tools.sh
git commit -m "feat(env): add 0_build_vendored_tools.sh stub for source-built tools"
```

**If something fails:** if the script errors with `missing build tool: <name>`, that means the engineer ran it outside the env. Fix: `conda activate OmicsClaw` then re-run. The error message already says this.

---

### Task 8: Create `tools/` directory + README

**Files:**
- Create: `tools/.gitkeep`
- Create: `tools/README.md`

**Why:** Keep the tools/ directory in git and document the contract for future tool additions. `.gitkeep` follows convention even though `README.md` alone would also work — it makes the "this directory is intentionally tracked even when empty" intent explicit.

- [ ] **Step 1: Create `tools/README.md`.**

```markdown
# tools/

This directory holds **vendored bioinformatics tools** built from upstream
source. It is currently empty — no tool needs source-build today; everything
OmicsClaw skills shell out to is satisfied by `bioconda` (see `environment.yml`).

The framework exists for the case where bioconda cannot deliver the exact
upstream version we need (e.g., a `git` SHA pinned for reproducibility, or
a `-rNNN` build suffix that bioconda strips).

## How to add a vendored tool

1. **Add a build block** to `0_build_vendored_tools.sh`. Use the commented
   template at the bottom of that file as a starting point. The block must:
   - skip itself if the expected output already exists (idempotency)
   - clone via `clone_at_tag <repo> <dest> <tag>` (the helper handles offline
     reuse)
   - build using `$CC` / `$CXX` so the conda-wrapped compiler is honored

2. **Add a symlink line** to `0_setup_env.sh` Tier 4:
   ```bash
   link_if_exists "$TOOLS_DIR/<tool>/<bin>"
   ```

3. **Add any tool-specific build deps** to `environment.yml` (e.g.,
   `yaggo` for Jellyfish, `automake` is already present for autotools
   projects).

4. **Document** the version chosen in this README under a "Vendored tools"
   section, and add a one-liner to the project README's Installation section
   noting the tool comes via `0_build_vendored_tools.sh`.

## Reproducibility notes

- `0_build_vendored_tools.sh` pins build flags via `CC/CXX/CPATH/LIBRARY_PATH`
  exported from `$CONDA_PREFIX`, so the conda env's `sysroot_linux-64=2.17`
  ABI applies to all builds.
- For shared-library tools (e.g., Jellyfish's `libjellyfish-2.0.so.2`), pass
  `LDFLAGS='-Wl,-rpath,$ORIGIN/../lib'` so the binary self-locates its libs
  even after symlinking into `$CONDA_PREFIX/bin`. See GenAsmClaw's
  `0_build_vendored_tools.sh` for the worked Jellyfish example.

## Vendored tools

_(none currently)_
```

- [ ] **Step 2: Create the `.gitkeep` marker.**

Run: `touch tools/.gitkeep`

- [ ] **Step 3: Verify directory structure.**

Run: `ls -A tools/`
Expected: `.gitkeep  README.md`.

- [ ] **Step 4: Commit.**

```bash
git add tools/.gitkeep tools/README.md
git commit -m "docs(tools): add tools/ directory + onboarding README

Empty directory ready for future source-built tools. Documents how to add
one (build block + symlink line + env.yml dep + README entry)."
```

**If something fails:** unlikely — pure docs.

---

## Phase 4 — Cleanup & migration

### Task 9: Remove `install_r_dependencies.R`

**Files:**
- Delete: `install_r_dependencies.R`

**Why:** Per spec D3, the file's responsibilities are now fully covered: CRAN+Bioc by `environment.yml`, GitHub by `0_setup_env.sh` Tier 3. Keeping it would create a third install path and invite drift.

- [ ] **Step 1: Confirm the new env satisfies what the old script provided.** Run a final sanity check:

```bash
INSTALLER=$(command -v mamba >/dev/null && echo mamba || echo conda)
$INSTALLER run -n OmicsClaw Rscript -e '
  cran_pkgs <- c("dplyr","ggplot2","Matrix","Seurat","sctransform","harmony",
                 "SoupX","openxlsx","HGNChelper","NMF","mclust","survival",
                 "msigdbr","ashr")
  bioc_pkgs <- c("SingleCellExperiment","scran","scuttle","SingleR","celldex",
                 "scDblFinder","batchelor","muscat","SpatialExperiment",
                 "zellkonverter","SPOTlight","DESeq2","apeglm","edgeR","limma",
                 "WGCNA","sva","clusterProfiler")
  gh_pkgs   <- c("spacexr","CARD","CellChat","numbat","SPARK","DoubletFinder")
  miss <- character(0)
  for (p in c(cran_pkgs, bioc_pkgs, gh_pkgs)) {
    if (!requireNamespace(p, quietly=TRUE)) miss <- c(miss, p)
  }
  if (length(miss)) stop("MISSING: ", paste(miss, collapse=", "))
  cat("All ", length(c(cran_pkgs, bioc_pkgs, gh_pkgs)), " R packages present\n", sep="")
'
```
Expected: prints `All 38 R packages present`. If anything is missing, **do not delete the old script** — go back and fix `environment.yml` or `0_setup_env.sh` Tier 3 first.

- [ ] **Step 2: Find every reference in the repo to the file.**

Run: `grep -rn "install_r_dependencies" --include="*.md" --include="*.py" --include="*.sh" --include="Makefile" --include="*.yml" --include="*.toml" .`
Expected: a list of references. Ignore matches inside `docs/superpowers/specs/` and `docs/superpowers/plans/` (historical traceability allowed). Real production references are likely in: README.md, AGENTS.md, CLAUDE.md, CONTRIBUTING.md, and possibly omicsclaw/diagnostics.py / dependency_manager.py error messages.

- [ ] **Step 3: Delete the file.**

Run: `git rm install_r_dependencies.R`

- [ ] **Step 4: Update each non-historical reference found in Step 2.** Change wording from `Rscript install_r_dependencies.R` to `bash 0_setup_env.sh` (recommended) or to a generic phrase about activating the OmicsClaw conda env, as appropriate. README, AGENTS.md, and pyproject.toml are handled by Tasks 11–13; for the rest:
  - `omicsclaw/core/dependency_manager.py` — there are user-facing `ImportError` messages (around lines 195–215) that currently say `Rscript install_r_dependencies.R`. Find them with `grep -n install_r_dependencies omicsclaw/core/dependency_manager.py` and replace with:

```python
"Install R (>= 4.3) and ensure 'Rscript' is on your PATH.\n"
"The recommended path is `bash 0_setup_env.sh` which provisions R 4.3 and all "
"required packages via mamba/conda."
```

  - any other production matches found in Step 2: rewrite or delete contextually. If the surrounding sentence loses meaning, replace with a short note like "see `bash 0_setup_env.sh`".

- [ ] **Step 5: Re-run the grep to confirm no production references remain.**

Run: `grep -rn "install_r_dependencies" --include="*.md" --include="*.py" --include="*.sh" --include="Makefile" --include="*.yml" --include="*.toml" . | grep -v "docs/superpowers/"`
Expected: empty output.

- [ ] **Step 6: Commit.**

```bash
git add -A
git commit -m "refactor(env): remove install_r_dependencies.R

CRAN+Bioconductor packages now live in environment.yml; GitHub-only packages
install via 0_setup_env.sh Tier 3. Single source of truth for R deps.

Updates dependency_manager.py error messages to point at the new install flow."
```

**If something fails:** if Step 1 reports missing packages, the cause is in environment.yml or Tier 3 — go back and fix before deleting the old script. Restore via `git checkout install_r_dependencies.R` if you've already deleted prematurely.

---

### Task 10: Update `Makefile`

**Files:**
- Modify: `Makefile`

**Why:** Spec D5 — Makefile gets new `setup-env` / `setup-env-name` targets at the top; existing `venv` / `setup` / `setup-full` targets are preserved but relabeled as the Legacy lightweight venv path.

- [ ] **Step 1: Read the current Makefile** so you know which targets exist:

Run: `cat Makefile | head -60`

- [ ] **Step 2: Replace the top section** (the existing `## ── Virtual-environment + installation targets ──` block, currently lines ~7–49) with the structure below. Keep `install`, `install-spatial-domains`, `install-full`, `install-dev`, `install-oc`, `oc-link`, `setup`, `setup-full` exactly as they are — only change the section header comment and add the new targets above them.

```makefile
## ── Conda environment (recommended, full functionality) ──────────────
## Single-command install of R 4.3, ~30 R packages, ~15 bioconda CLIs,
## OmicsClaw (editable), and all Python optional extras.
## Requires mamba (recommended) or conda — install Miniforge:
##   https://github.com/conda-forge/miniforge

setup-env:
	bash 0_setup_env.sh

# Use a custom env name: `make setup-env-name NAME=foo`
NAME ?= OmicsClaw
setup-env-name:
	bash 0_setup_env.sh "$(NAME)"

## ── Legacy lightweight venv path (Python-only skills) ────────────────
## NOTE: this path does NOT install R, samtools, STAR, fastqc, etc.
## For full functionality use:  make setup-env  (or: bash 0_setup_env.sh)

venv:
	python3 -m venv .venv
	@echo "Activate with: source .venv/bin/activate"

install:
	pip install -e .

# (existing install-spatial-domains / install-full / install-dev / install-oc / oc-link / setup / setup-full follow unchanged)
```

- [ ] **Step 3: Verify the Makefile parses.**

Run: `make -n setup-env`
Expected: prints `bash 0_setup_env.sh` (does not execute it; `-n` is dry-run). No syntax errors.

- [ ] **Step 4: Verify the legacy targets still work.**

Run: `make -n setup-full`
Expected: prints `pip install -e ".[full]"`.

- [ ] **Step 5: Commit.**

```bash
git add Makefile
git commit -m "feat(makefile): add setup-env target; relabel venv path as legacy

setup-env runs bash 0_setup_env.sh for the full conda-primary install.
setup-env-name allows a custom env name. Legacy venv targets are preserved
under a clearly-labeled 'Legacy lightweight venv path' header for users who
only need the LLM/routing surfaces."
```

**If something fails:** Makefile syntax issues usually surface as `*** missing separator. Stop.` — re-check that recipe lines are tab-indented (not spaces).

---

### Task 11: Update `README.md` install section

**Files:**
- Modify: `README.md` (Installation section, around line 80-128)

**Why:** Spec D5 + D2 — install section reorders to Conda (recommended) | venv (lightweight). Calls out Miniforge explicitly.

- [ ] **Step 1: Locate the current "📦 Installation" section** (around line 80 onward). It currently leads with "venv recommended" and `pip install -e .`.

- [ ] **Step 2: Replace the section's body with the new content.**

```markdown
## 📦 Installation

OmicsClaw ships with two install paths:

### 🥇 Conda (recommended — full functionality)

Provisions R 4.3 + ~30 R packages, ~15 bioinformatics CLIs (samtools / STAR /
fastqc / bwa / ...), OmicsClaw itself (editable), and all Python optional
extras in **one command**.

```bash
# 1. Install Miniforge if you don't have it (mamba is bundled, recommended)
#    https://github.com/conda-forge/miniforge

# 2. Clone and bootstrap
git clone https://github.com/TianGzlab/OmicsClaw.git
cd OmicsClaw
bash 0_setup_env.sh           # creates conda env "OmicsClaw"
conda activate OmicsClaw

# 3. Verify
python omicsclaw.py env       # or: oc env
```

The setup script is **idempotent** — re-running it updates the env in place.
For a custom env name: `bash 0_setup_env.sh my_env_name`.

### 🪶 venv (lightweight — Python-only skills)

For users who only need the **LLM/routing/chat surfaces** and do not run
analyses. This path **does not install R, samtools, STAR, fastqc, etc.** —
skills that depend on those will report "tool not on PATH" at runtime.

<details>
<summary>Setup with venv</summary>

```bash
# 1. Create a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 2. Install OmicsClaw
pip install -e .
# Optional: pip install -e ".[interactive]" / ".[tui]" / ".[memory]" / ".[full]"
# Optional: pip install -r bot/requirements.txt   # for messaging channels
```

Or via Makefile:

```bash
make venv && make setup
```

</details>

*Check your installation status anytime with `omicsclaw env` or `python omicsclaw.py env`.*
```

- [ ] **Step 3: Verify the diff.**

Run: `git diff README.md | head -100`
Expected: large change in the install section, no accidental edits elsewhere.

- [ ] **Step 4: Render-check by reading the file in a Markdown viewer or `glow README.md`** if available; otherwise visually inspect that headers and code fences nest correctly.

- [ ] **Step 5: Commit.**

```bash
git add README.md
git commit -m "docs(readme): reorder install — Conda primary, venv legacy

Conda path is now the recommended single-command install (R + CLIs + Python).
venv is preserved under a 'lightweight Python-only' note for chat-only users.
Adds Miniforge install link."
```

**If something fails:** if Markdown rendering breaks, the most likely cause is a missing closing ``` fence — count them carefully.

---

### Task 12: Update `AGENTS.md`

**Files:**
- Modify: `AGENTS.md` (Setup section, lines 29-52)

**Why:** Keep the AI-agent contract aligned with README. Same conda-first ordering.

- [ ] **Step 1: Locate the `## Setup` block in AGENTS.md.**

- [ ] **Step 2: Replace it with:**

```markdown
## Setup

```bash
cd /path/to/OmicsClaw

# Recommended: full conda-primary install (R + CLIs + Python in one shot)
bash 0_setup_env.sh
conda activate OmicsClaw

# Lightweight alternative (Python-only skills, no R or CLIs):
# pip install -e .
# pip install -e ".[interactive]" / ".[tui]" / ".[memory]" / ".[full]"

python omicsclaw.py list   # or: oc list
python omicsclaw.py run spatial-preprocess --demo
```

> **`oc` short alias**: After installing OmicsClaw (either path), both
> `omicsclaw` and `oc` commands are available system-wide via the
> `[project.scripts]` entry in `pyproject.toml`.
>
> **Dependency source of truth**:
> - **Python deps** live in `pyproject.toml` (used by both install paths).
> - **R + bioconda CLIs + build toolchain** live in `environment.yml` (conda
>   path only).
> - **GitHub-only R packages** are installed inline by `0_setup_env.sh`
>   Tier 3.
>
> The repository does not use a root `requirements.txt` as a primary install
> entrypoint.
```

- [ ] **Step 3: Commit.**

```bash
git add AGENTS.md
git commit -m "docs(agents): sync Setup section with conda-primary install"
```

**If something fails:** unlikely — pure docs.

---

### Task 13: Add `pyproject.toml` header comment

**Files:**
- Modify: `pyproject.toml` (top, before `[build-system]`)

**Why:** Make the install-path boundary discoverable: anyone opening pyproject.toml learns immediately that R/CLIs are NOT here, and where they are.

- [ ] **Step 1: Prepend the comment.**

```toml
# OmicsClaw Python deps live here.
# R packages, bioinformatics CLIs (samtools/STAR/fastqc/...), and the build
# toolchain are declared in environment.yml and installed by 0_setup_env.sh.
# See docs/superpowers/specs/2026-04-30-conda-env-management-design.md.

[build-system]
```

- [ ] **Step 2: Verify pyproject still parses.**

Run: `python -c "import tomllib; tomllib.loads(open('pyproject.toml').read())"`
Expected: no output. If you're on Python <3.11, use `pip install tomli && python -c "import tomli; tomli.loads(open('pyproject.toml').read())"`.

- [ ] **Step 3: Commit.**

```bash
git add pyproject.toml
git commit -m "docs(pyproject): pointer to environment.yml for non-Python deps"
```

**If something fails:** TOML syntax errors will fail Step 2 — comments must use `#`, not `;` or `//`.

---

## Phase 5 — Final verification

### Task 14: Walk through Acceptance Criteria

**Files:** none (verification only)

**Why:** Spec defines 6 explicit Acceptance Criteria. Walking each one demonstrates the work is complete and provides reviewers a clear go/no-go signal.

- [ ] **Step 1: AC#1 — Fresh-checkout install works in one command.**

```bash
INSTALLER=$(command -v mamba >/dev/null && echo mamba || echo conda)
# Pretend fresh: remove env if exists
$INSTALLER env remove -n OmicsClaw -y 2>/dev/null || true
bash 0_setup_env.sh
conda activate OmicsClaw 2>/dev/null || $INSTALLER activate OmicsClaw
python -c "import omicsclaw; print('omicsclaw OK')"
Rscript -e 'library(DESeq2); library(spacexr); library(CellChat); cat("R OK\n")'
samtools --version | head -1
STAR --version
fastqc --version
omicsclaw env
```
Expected: every command succeeds; `omicsclaw env` doctor reports OK for Python and R.

- [ ] **Step 2: AC#2 — Idempotent re-run.**

```bash
bash 0_setup_env.sh 2>&1 | tee /tmp/setup_rerun.log
grep -c "already installed" /tmp/setup_rerun.log
```
Expected: every Tier reports update/skip messages, exit 0. Tier 3 prints "already installed — skipping" 6 times.

- [ ] **Step 3: AC#3 — mamba-first behaviour.** (Skip if only conda is installed.)

```bash
bash 0_setup_env.sh 2>&1 | head -2 | grep -q "using mamba" && echo OK || echo "not using mamba"
```
Expected: `OK`.

- [ ] **Step 4: AC#4 — venv fallback still works.**

```bash
deactivate 2>/dev/null || true
$INSTALLER deactivate 2>/dev/null || true
python3 -m venv /tmp/oc-venv-check
source /tmp/oc-venv-check/bin/activate
pip install -e .
python -c "import omicsclaw; print('venv path OK')"
omicsclaw list | head -5
deactivate
rm -rf /tmp/oc-venv-check
```
Expected: install completes, `omicsclaw list` works (subset of skills functional).

- [ ] **Step 5: AC#5 — No broken references.**

```bash
grep -rn "install_r_dependencies" \
  --include="*.md" --include="*.py" --include="*.sh" \
  --include="Makefile" --include="*.yml" --include="*.toml" . \
  | grep -v "docs/superpowers/"
```
Expected: empty output.

- [ ] **Step 6: AC#6 — Docs consistent.** Open README.md and AGENTS.md side by side; confirm both:
  - Lead with the conda path
  - Mention `bash 0_setup_env.sh` as the single command
  - Note Miniforge as the recommended conda distribution
  - Mention venv path is "Python-only / lightweight"

- [ ] **Step 7: Record results.** If all 6 ACs pass, the implementation is complete. Otherwise note which AC failed and either fix inline or open a follow-up issue (per spec's "Open Issues" section).

**If something fails:** AC#1 failures are diagnostic-rich (the failing command's output is the clue). AC#5 false positives are usually historical mentions in `docs/superpowers/` — the grep filter excludes those.

---

### Task 15: Update plans index + close out

**Files:**
- Modify: `docs/superpowers/plans/README.md`

**Why:** Per repo `SPEC.md` convention, every dated plan must be linked from the plans index.

- [ ] **Step 1: Update the plans index.**

```markdown
## Tracked Entries

- [2026-04-30-conda-env-management-plan.md](2026-04-30-conda-env-management-plan.md)
  — implement the four-tier mamba-first conda install (environment.yml,
  0_setup_env.sh, vendoring stub, install_r_dependencies.R removal).
- [2026-04-16-remote-connection-guide-refresh.md](2026-04-16-remote-connection-guide-refresh.md)
  ...
```

(Insert the new bullet at the top of the existing list; do not reorder others.)

- [ ] **Step 2: Update root `README.md`'s milestone section** if it has a "What changed recently" or similar list — add a one-line note "2026-04-30: switched to conda-primary install (`bash 0_setup_env.sh`)". If no such section exists in README, skip this step.

- [ ] **Step 3: Final commit.**

```bash
git add docs/superpowers/plans/README.md README.md 2>/dev/null
git commit -m "docs(plans): link conda env management plan in index"
```

- [ ] **Step 4: Optional — branch sign-off.** If working on a feature branch, the
  branch is now ready for code review. Per repository playbook, run:

```bash
# Review your full change set
git log --oneline main..HEAD
git diff main..HEAD --stat
```
Expected: a clean stack of ~12 commits implementing the plan, no surprise files.

**If something fails:** unlikely — purely admin.

---

## Self-Review Checklist (run before handing off)

- [ ] **Spec coverage.** Each spec section maps to a task:
  - Goal → entire plan
  - Non-Goals → preserved by file map (venv kept, no actual vendored tool, no skill code touched)
  - D1 (conda owns non-Python) → Task 1 environment.yml content
  - D2 (mamba preferred) → Task 3 detect block
  - D3 (R script removed) → Task 9
  - D4 (vendoring stub) → Tasks 6, 7, 8
  - D5 (venv preserved) → Task 10 Makefile + Task 11 README
  - D6 (env name `OmicsClaw`) → Task 3 `ENV_NAME="${1:-OmicsClaw}"`
  - File Map → each "Added/Modified/Removed" entry has a task
  - Acceptance Criteria → Task 14
  - Risks & Mitigations → Task 2 (bioconda name validation), Task 5 (compile env), Task 3 (mamba/conda fallback)

- [ ] **No placeholders.** Every step has actual code or commands. No "TBD", "implement later", "similar to above".

- [ ] **Type/name consistency.** Function/var names match across tasks: `INSTALLER`, `ENV_NAME`, `ENV_PREFIX`, `ENV_BIN`, `link_if_exists`, `clone_at_tag`, `need_tool` — used consistently per definition.

- [ ] **Each task is committable.** Every task ends with a `git commit` step.
