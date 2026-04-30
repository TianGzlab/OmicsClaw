# OmicsClaw Conda-Primary Environment Management — Design

**Date:** 2026-04-30
**Status:** Approved for implementation (pending user review of this spec)
**Origin:** User request to integrate the GenAsmClaw `0_setup_env.sh` /
`0_build_vendored_tools.sh` pattern into OmicsClaw, replacing the current
pip+venv + standalone `install_r_dependencies.R` setup.

## Goal

Adopt a **single-command, four-tier, mamba-first environment install** for
OmicsClaw, so a fresh clone reaches a fully-functional analysis environment by
running only `bash 0_setup_env.sh`. The new flow installs Python, ~15
bioinformatics CLIs (samtools/STAR/fastqc/bwa/...), R 4.3 + ~30 R packages,
OmicsClaw itself (editable), and 6 GitHub-only R packages — without leaving any
"manual install" instructions in user-facing docs.

The legacy pip+venv path is retained as a **lightweight fallback** for users
who only need the LLM/routing/chat surfaces and do not run analyses.

## Non-Goals

- **Removing the venv path entirely.** It is deliberately preserved (under a
  "Legacy lightweight venv path" Makefile section) for users who don't run
  bioinformatics analyses. Forcing every chat-only user to install conda would
  be a regression.
- **Building any tools from source in this iteration.** The vendored-tool
  framework (`0_build_vendored_tools.sh`, `tools/`) is added as a **stub** so
  future work has a ready scaffolding, but no tool is actually built today.
- **Touching skill or runtime code.** OmicsClaw already detects
  `$CONDA_PREFIX/bin/Rscript` (`omicsclaw/core/r_script_runner.py:27`,
  `omicsclaw/core/dependency_manager.py:148`). The runtime is conda-friendly;
  only the install surface needs to change.
- **Replacing pyproject.toml.** It remains the single source of truth for
  Python dependencies. environment.yml never re-declares a Python package that
  pyproject.toml already lists.
- **Per-tier R install (`--tier bulkrna|spatial|singlecell`).** This option in
  the old R script existed because CRAN/Bioconductor source compiles are slow.
  With bioconda binaries, installing all R packages is fast enough that
  per-tier filtering is no longer worth the complexity. Users with specialized
  needs may fork `environment.yml`.

## Key Design Decisions

### D1 — Conda is the system package manager

Everything that pip cannot install (R packages, bioinformatics CLIs, build
toolchains, system libraries) is declared in `environment.yml`. Pip remains
responsible for OmicsClaw itself and its pure-Python deps via
`pip install -e ".[full]"`.

This avoids the double-source-of-truth problem that would arise if both conda
and pip tried to manage e.g. `numpy`. The boundary is sharp: **pyproject.toml
owns Python; environment.yml owns everything else.**

### D2 — mamba preferred, conda fallback

The shell driver detects `mamba` first, then falls back to `conda`:

```bash
if command -v mamba >/dev/null 2>&1; then
    INSTALLER="mamba"
elif command -v conda >/dev/null 2>&1; then
    INSTALLER="conda"
else
    echo "Install Miniforge first: https://github.com/conda-forge/miniforge"
    exit 1
fi
```

User-facing docs (README, AGENTS.md) explicitly **recommend Miniforge** (which
ships mamba) over Anaconda/Miniconda. mamba's solver is dramatically faster on
environments of this size (~30 R packages + ~15 CLIs + Python core).

### D3 — `install_r_dependencies.R` is fully removed

| Group | Count | New home |
|---|---|---|
| CRAN packages (dplyr, ggplot2, Seurat, sctransform, harmony, SoupX, openxlsx, HGNChelper, NMF, mclust, survival, msigdbr, ashr, Matrix) | 14 | `environment.yml` (`r-*`) |
| Bioconductor packages (DESeq2, apeglm, edgeR, limma, WGCNA, sva, clusterProfiler, SingleR, scran, scuttle, scDblFinder, batchelor, muscat, SpatialExperiment, zellkonverter, SPOTlight, SingleCellExperiment, celldex) | 18 | `environment.yml` (`bioconductor-*`) |
| GitHub-only packages (spacexr/RCTD, CARD, CellChat, numbat, SPARK, DoubletFinder) | 6 | Inline `Rscript` block in Tier 3 of `0_setup_env.sh` (~18 lines, idempotent) |

**Net effect:** the 330-line `install_r_dependencies.R` is deleted. R deps live
in exactly two places afterward — `environment.yml` for everything bioconda
ships, and an inline 18-line block for the GitHub long-tail.

Rationale: keeping the R script after migrating CRAN+Bioc to environment.yml
would create three install paths (yml + script + GitHub) instead of two. Pure
duplication. The bioconda binaries are pre-built and orders of magnitude
faster than `BiocManager::install` source compiles, so the migration is also
a performance win.

### D4 — Vendored-tool tier is a stub framework

GenAsmClaw vendors `hifiasm v0.25.0`, `seqtk v1.5`, `Jellyfish v2.3.1` from
source because bioconda cannot pin the exact `-rNNN` build suffix. **OmicsClaw
currently has no such constraint** — every external CLI it shells out to
(samtools, STAR, fastqc, bwa, ...) is well-served by bioconda's stable
versions.

We therefore adopt the *framework* but ship it empty:

- `tools/` directory (empty, with `.gitkeep` and a short `README.md`)
- `0_build_vendored_tools.sh` — keeps the GenAsmClaw skeleton:
  - `set -euo pipefail`, project-root detection
  - Build-tool sanity checks (`need_tool` for git/make/cmake/autoreconf/libtool/yaggo)
  - `clone_at_tag()` helper
  - `CC/CXX/CPATH/LIBRARY_PATH` exports for conda-wrapped compiler usage
  - **No actual tool build blocks** — only a commented template showing how
    a future `hifiasm`-style block would slot in.
- `0_setup_env.sh` Tier 4: still invokes `link_if_exists` over a (currently
  empty) tools/ tree — no-op today, ready when a tool gets added.

When a real source-built tool becomes necessary later, the developer:
1. Adds a build block to `0_build_vendored_tools.sh`.
2. Adds a single `link_if_exists "$TOOLS_DIR/<tool>/<bin>"` line in
   `0_setup_env.sh` Tier 4.

That is the entire incremental cost — the scaffolding around it is already
correct.

### D5 — venv path preserved, de-emphasized

Makefile structure becomes:

```makefile
## ── Conda environment (recommended, full functionality) ─────────────
setup-env:                          # bash 0_setup_env.sh
setup-env-name:                     # bash 0_setup_env.sh "$(NAME)"

## ── Legacy lightweight venv path (Python-only skills) ────────────────
## NOTE: this path does NOT install R, samtools, STAR, fastqc, etc.
## For full functionality use: make setup-env  (or: bash 0_setup_env.sh)
venv:
setup:
setup-full:
```

README.md install section is reordered:

1. **Conda (recommended, full functionality)** — `bash 0_setup_env.sh && conda activate OmicsClaw`. Calls out Miniforge install link.
2. **venv (lightweight, Python-only)** — current docs preserved, with a clear
   one-line note that R-based and CLI-based skills will fail under this path.

### D6 — Environment name `OmicsClaw`

Mirrors GenAsmClaw's project-named pattern. Override-able via positional arg:
`bash 0_setup_env.sh my_env_name`. Makefile exposes both:
`make setup-env` (default name) and `make setup-env-name NAME=foo`.

## Architecture: Four-Tier Install (driven by `0_setup_env.sh`)

```
┌─────────────────────────────────────────────────────────────────────────┐
│  bash 0_setup_env.sh    ←  one command, fully idempotent                │
└─────────────────────────────────────────────────────────────────────────┘
        │
        ▼
   detect mamba|conda  (mamba preferred — fail with Miniforge link if neither)
        │
        ▼
┌─ Tier 1 ─────────────────────────────────────────────────────────────────┐
│  $INSTALLER env create -n OmicsClaw -f environment.yml                   │
│  (or: env update --prune  if env already exists)                         │
│  ├─ python=3.11                                                          │
│  ├─ build toolchain  (gxx_linux-64=12, sysroot_linux-64=2.17,           │
│  │                    cmake, make, autoconf, automake, libtool,          │
│  │                    pkg-config, git)                                   │
│  │                   tool-specific helpers (e.g. yaggo for Jellyfish)    │
│  │                   are added on demand when their tool gets vendored   │
│  ├─ ~15 bioconda CLIs  (samtools, bcftools, bwa, bwa-mem2, bowtie2,      │
│  │                       minimap2, hisat2, star, fastqc, multiqc, fastp, │
│  │                       trim-galore, gatk4, picard, simpleaf,           │
│  │                       kb-python, velocyto.py)                         │
│  └─ R 4.3 + ~30 r-*/bioconductor-* packages                              │
└──────────────────────────────────────────────────────────────────────────┘
        │
        ▼
┌─ Tier 2 ─────────────────────────────────────────────────────────────────┐
│  $INSTALLER run -n OmicsClaw pip install -e ".[full]"                    │
│  └─ OmicsClaw editable + Python optional extras (scvi-tools, cellrank,   │
│     palantir, harmonypy, bbknn, scvelo, infercnvpy, gseapy, ...)         │
└──────────────────────────────────────────────────────────────────────────┘
        │
        ▼
┌─ Tier 3 ─────────────────────────────────────────────────────────────────┐
│  $INSTALLER run -n OmicsClaw Rscript - <<'RSCRIPT'                       │
│  └─ devtools::install_github for 6 GitHub-only R packages                │
│     (spacexr, CARD, CellChat, numbat, SPARK, DoubletFinder)              │
│  ~18 lines of inline R, idempotent (skip if already installed)           │
└──────────────────────────────────────────────────────────────────────────┘
        │
        ▼
┌─ Tier 4 ─────────────────────────────────────────────────────────────────┐
│  symlink vendored binaries → $CONDA_PREFIX/bin/                          │
│  └─ Iterates over tools/<tool>/<bin> with link_if_exists                 │
│     Currently empty (stub); ready when a vendored tool is added          │
└──────────────────────────────────────────────────────────────────────────┘
```

**Idempotency:** Tier 1 uses `env update --prune` if env already exists. Tier
2's editable pip install is naturally idempotent. Tier 3 checks
`requireNamespace()` per package before installing. Tier 4 uses `ln -sf`
(overwrite OK). Re-running `bash 0_setup_env.sh` on a finished env is a no-op.

## File Map (exact repo-relative paths)

### Added

| Path | Approx. lines | Purpose |
|---|---|---|
| `environment.yml` | 70 | Conda env declaration: Python + build toolchain + bioconda CLIs + R + r-*/bioconductor-* |
| `0_setup_env.sh` | 140 | Main driver — Tiers 1–4 |
| `0_build_vendored_tools.sh` | 50 | Stub with `clone_at_tag()` helper, build-tool sanity checks, commented build template |
| `tools/.gitkeep` | 0 | Preserve empty directory in git |
| `tools/README.md` | 30 | Brief: how to add a vendored tool (where to clone, where the binary should land, which `link_if_exists` line to add to setup_env.sh) |

### Modified

| Path | Change |
|---|---|
| `Makefile` | Add `setup-env` and `setup-env-name` targets at top; relabel existing `venv`/`setup`/`setup-full` under "Legacy lightweight venv path" comment header |
| `README.md` | Reorganize install section: Conda (recommended) | venv (lightweight). Add Miniforge install pointer. Note which skills fall back if user picks venv. |
| `AGENTS.md` | Update the `## Setup` block to mirror README ordering |
| `pyproject.toml` | Add a 3-line header comment pointing to `environment.yml` for non-Python deps. No functional changes. |
| `docs/superpowers/specs/README.md` | Add this spec to the index |

### Removed

| Path | Reason |
|---|---|
| `install_r_dependencies.R` | CRAN + Bioconductor sections move to `environment.yml`; GitHub section moves inline to `0_setup_env.sh` Tier 3. No third home for R deps remains. |

### Untouched

- `omicsclaw/` (runtime is already conda-aware)
- `skills/` (no changes — skills shell out to CLIs by name; conda installs them on PATH)
- `bot/` (separate concern, has its own `requirements.txt`)
- `tests/`
- `.github/` (CI is out of scope for this spec)

## Migration & Compatibility

- **Existing pip+venv users**: zero breakage. Their `.venv/` keeps working.
  They don't get bioinformatics CLIs (they didn't have them before either).
- **Existing users with `install_r_dependencies.R`-installed R packages**:
  zero breakage. The OmicsClaw runtime detects R via `$CONDA_PREFIX` first
  but falls through to `Rscript` on PATH, which is what the old script
  populated. Their installed packages remain importable.
- **Users wanting to upgrade**: `bash 0_setup_env.sh` creates a new
  `OmicsClaw` conda env in parallel with their existing `.venv/`. They can
  decommission `.venv/` whenever they like.
- **CI**: any workflow currently running `pip install -e ".[full]"` keeps
  working unchanged. A future CI job that exercises the full conda path is
  out of scope here.
- **`omicsclaw env` doctor** (`omicsclaw/diagnostics.py`): existing R/Rscript
  detection is already conda-aware — will report richer info under conda.

## Acceptance Criteria

A reviewer should be able to verify each of these after merge:

1. **Fresh-checkout install works in one command.** On a machine with
   Miniforge installed:
   ```bash
   git clone <repo> && cd OmicsClaw && bash 0_setup_env.sh
   conda activate OmicsClaw
   python -c "import omicsclaw"
   Rscript -e 'library(DESeq2); library(spacexr); library(CellChat)'
   samtools --version && STAR --version && fastqc --version
   omicsclaw env    # doctor output reports OK for both Python and R
   ```
2. **Idempotent re-run.** Running `bash 0_setup_env.sh` a second time on a
   completed env touches nothing (Tier 1 prune-update is no-op, Tier 2 is
   no-op, Tier 3 reports "already installed" for all 6 GitHub packages,
   Tier 4 re-symlinks harmlessly).
3. **mamba-first behaviour observable.** With both mamba and conda present,
   the script's first `[setup_env] using ...` line shows `mamba`.
4. **venv fallback still works.**
   ```bash
   python3 -m venv .venv && source .venv/bin/activate
   pip install -e .
   omicsclaw list   # subset of skills functional, others report missing CLI/R
   ```
5. **No broken references.** No production code, Makefile target, or
   user-facing docs (README.md, AGENTS.md, CLAUDE.md, CONTRIBUTING.md,
   `docs/` outside `docs/superpowers/specs/`) reference
   `install_r_dependencies.R`. Historical mentions in dated specs / plans
   under `docs/superpowers/` are allowed for traceability.
6. **Docs are consistent.** README.md and AGENTS.md "Setup" sections both
   present conda first, venv second; both reference `bash 0_setup_env.sh`
   identically.

## Risks & Mitigations

- **bioconda package name typos in `environment.yml`.** ~30 R packages must
  be referenced by their exact bioconda canonical name (`r-seurat` not
  `r-Seurat`, `bioconductor-deseq2` not `bioconductor-DESeq2`, lower-cased).
  *Mitigation:* the implementation plan includes a verification step that
  runs `mamba search` for every package name before commit.
- **GitHub-package compile failures against conda-provided R.**
  `devtools::install_github` builds C/C++ code requiring R headers. If the
  build toolchain isn't aligned with conda's R, compiles fail.
  *Mitigation:* Tier 1 already pins `gxx_linux-64=12.*` and
  `sysroot_linux-64=2.17` so conda's compiler wrapper sees the env's R
  headers and libs. Tier 3 runs **inside the activated env** via
  `$INSTALLER run -n OmicsClaw`.
- **mamba absent + conda solver too slow.** Some users may only have
  Anaconda's `conda`. *Mitigation:* fallback path works (just slower); the
  setup-time message and README explicitly nudge users toward Miniforge.
- **Disk usage.** A full `OmicsClaw` env will be ~5–8 GB (R ecosystem +
  CLIs + Python). *Mitigation:* venv path is preserved for users who don't
  need analysis tooling.

## Open Issues / Future Work (deliberately deferred)

- **First vendored tool.** Add when a real need arises (e.g., a tool not on
  bioconda or requiring an exact upstream commit).
- **CI conda workflow.** Add a GitHub Actions job that runs
  `bash 0_setup_env.sh` and a smoke test. Out of scope for this iteration.
- **conda-lock for fully reproducible builds.** Consider once env stabilizes.
- **macOS / Windows support.** GenAsmClaw's setup is Linux-only (`sysroot_linux-64`,
  `gxx_linux-64` are Linux pins). Cross-platform conda envs require either
  removing the Linux-only pins (loses sysroot reproducibility) or maintaining
  per-platform yml files. Defer until macOS/Windows users actually request.
