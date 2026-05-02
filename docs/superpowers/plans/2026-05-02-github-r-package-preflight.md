# GitHub R Package Preflight Plan

**Goal:** Make `0_setup_env.sh` Tier 3 install the six GitHub-only R packages without compiling avoidable CRAN/Bioconductor dependencies from source.

**Scope:** Audit `Depends`, `Imports`, and `LinkingTo` for `spacexr`, `CARD`, `CellChat`, `numbat`, `SPARK`, and `DoubletFinder`; add only required install-time dependencies to the conda layer when they are available from conda-forge/bioconda.

**Non-goals:** Do not install `Suggests`/vignette/test-only packages, do not replace the GitHub package sources, and do not add a second R dependency installer.

**File map:**
- Modify: `environment.yml`
- Modify: `README.md`
- Modify: `README_zh-CN.md`
- Modify: `tests/test_setup_env_script.py`
- Modify: `docs/superpowers/plans/README.md`

## Tasks

1. Extract current GitHub package metadata from each upstream `DESCRIPTION`.
2. Compare required dependencies against the current `OmicsClaw` conda env.
3. Add a regression test that asserts the conda layer preinstalls the audited GitHub R dependency closure.
4. Add the missing conda-resolvable R packages to `environment.yml`, grouped under the R package tier.
5. Document the decision in English and Chinese README files.
6. Verify with targeted pytest, YAML parsing, `git diff --check`, and R namespace checks where the local environment has been updated.

## Acceptance Criteria

- The regression test fails before the dependency additions and passes after them.
- `environment.yml` remains parseable.
- Tier 3 GitHub package comments still identify only the six GitHub-only package roots as source installs.
- Any dependency that remains outside conda is explicitly called out as residual risk.
