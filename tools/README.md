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

       link_if_exists "$TOOLS_DIR/<tool>/<binary>"

3. **Add any tool-specific build deps** to `environment.yml` (e.g.,
   `yaggo` for Jellyfish; `automake` is already present for autotools
   projects).

4. **Document** the version chosen in this README under a "Vendored tools"
   section, and add a one-liner to the project README's Installation section
   noting the tool comes via `0_build_vendored_tools.sh`.

## Reproducibility notes

- `0_build_vendored_tools.sh` pins build flags via `CC` / `CXX` / `CPATH` /
  `LIBRARY_PATH` exported from `$CONDA_PREFIX`, so the conda env's
  `sysroot_linux-64=2.17` ABI applies to all builds.
- For shared-library tools (e.g., Jellyfish's `libjellyfish-2.0.so.2`), pass
  `LDFLAGS='-Wl,-rpath,$ORIGIN/../lib'` so the binary self-locates its libs
  even after symlinking into `$CONDA_PREFIX/bin`.

## Vendored tools

_(none currently)_
