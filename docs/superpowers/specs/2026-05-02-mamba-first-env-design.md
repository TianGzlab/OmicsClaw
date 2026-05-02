# Mamba-first 4-layer env management — design

**Date:** 2026-05-02
**Status:** Implementation in progress (see plan: `docs/superpowers/plans/2026-05-02-mamba-first-env-management.md`)

## Background

pip 24.2+ aborts `pip install -e ".[full,singlecell-upstream]"` with `resolution-too-deep`. The OmicsClaw `[full]` extra is a self-referencing umbrella over 27 sub-extras (~70+ direct deps, ~hundreds transitive). Several packages share heavy transitive deps with mismatched version ranges (torch / numpy / scanpy via scvi-tools / cell2location / scvelo / cellrank / SpaGCN / GraphST / cellcharter), and `cellrank → pygpcca` over-pins jinja2==3.0.3 against `fastapi[standard]`'s jinja2>=3.1.5. pip backtracks past its hardcoded round limit and exits.

## Decision: 4-layer dependency strategy

Top-down decision tree, first match wins:

1. **Layer 0 — foundation (mamba)**: python, R, gxx, cmake, build toolchain. Source: `environment.yml` Tier 0.
2. **Layer 1 — heavy Python science stack (mamba)**: bioconda/conda-forge packages with a Py3.11 build. Source: `environment.yml` Tier 4 (added by Task 1).
3. **Layer 2 — thin pip residue**: omicsclaw editable + PyPI-only packages (no conda recipe). Source: `pyproject.toml` extras (slimmed by Task 2).
4. **Layer 3 — vendored source builds**: tools without conda recipe and unsuitable for pip. Source: `tools/<name>/`, `0_build_vendored_tools.sh`. Currently empty stub.
5. **Layer 4 — isolated sub-envs**: hard-conflict deps. Sources: `environments/<tool>.yml`, `omicsclaw_<tool>` naming, subprocess bridge via `omicsclaw.core.external_env`. First sub-env: banksy (numpy<2.0).

Single entrypoint: `bash 0_setup_env.sh [env_name] [--with-banksy]`.

## Audit results (Step 2 of Task 0)

Source: `docs/superpowers/specs/conda-availability-2026-05-02.csv`

**Total packages audited:** 42
**mamba_ok:** 27 (64%)
**pip_only:** 11 (26%)
**unknown:** 4 (10%) — proxy was down; need network-connected re-run

### mamba_ok packages (27)

| Package | Version | Note |
|---|---|---|
| arboreto | 0.1.6 | noarch |
| bbknn | 1.6.0 | compiled |
| cellrank | 2.2.0 | noarch |
| celltypist | 1.7.1 | noarch |
| coloredlogs | 15.0.1 | noarch |
| doubletdetection | 4.3.0.post1 | noarch |
| esda | 2.9.0 | noarch |
| gseapy | 1.2.1 | compiled |
| harmonypy | 0.2.0 | noarch |
| httpx | 0.23.1 | compiled |
| humanfriendly | 10.0 | compiled |
| kb-python | 0.30.1 | noarch |
| leidenalg | 0.11.0 | compiled |
| liana | 1.7.1 | noarch |
| libpysal | 4.14.1 | noarch |
| louvain | 0.8.2 | compiled |
| multiqc | 1.34 | noarch |
| palantir | 1.4.4 | noarch |
| phate | 2.0.0 | noarch |
| pot | 0.9.6.post1 | compiled |
| pydeseq2 | 0.5.4 | noarch |
| pysal | 26.1 | noarch |
| python-igraph | 1.0.0 | compiled |
| scanorama | 1.7.4 | noarch |
| scrublet | 0.2.3 | noarch |
| scvelo | 0.3.4 | noarch |
| scvi-tools | 1.4.2 | noarch |

### pip_only packages (11)

| Package | Reason |
|---|---|
| ccproxy-api | known-no-conda-recipe (internal package) |
| cellcharter | known-no-conda-recipe |
| fastccc | known-no-conda-recipe |
| flashdeconv | known-no-conda-recipe |
| graphst | known-no-conda-recipe |
| paste-bio | known-no-conda-recipe |
| pyvia | known-no-conda-recipe |
| spagcn | known-no-conda-recipe |
| tangram-sc | known-no-conda-recipe |
| torch | not-in-bioconda-or-conda-forge (pytorch channel only) |
| torch_geometric | not-in-bioconda-or-conda-forge (pyg channel only) |

### unknown packages (4) — requires network-connected verification

| Package | Reason |
|---|---|
| cell2location | not-in-local-cache; verify on network |
| cellphonedb | not-in-local-cache; verify on network |
| infercnvpy | not-in-local-cache; verify on network |
| spatialde | not-in-local-cache; verify on network |

### Surprising classifications

- **torch** — classified `pip_only` because pytorch is not in the standard bioconda/conda-forge channels used here; it lives on the `pytorch` channel. For Task 1, add `pytorch` channel to environment.yml and install torch there.
- **scvi-tools** — `mamba_ok` (noarch on bioconda), which is positive. However the cached version is 1.4.2; the pyproject.toml pins `scvi-tools>=1.4.0,<2.0`. Verify that 1.4.2 satisfies all downstream deps (cell2location) before pinning in environment.yml.
- **harmonypy** — `mamba_ok` via bioconda noarch at version 0.2.0, but pyproject requires `harmonypy>=0.0.9`. The bioconda version is newer; safe to use.
- **cellrank** — `mamba_ok` noarch at 2.2.0 on conda-forge. This is a complex package that was a concern in the plan; the conda version is current.
- **cell2location / cellphonedb / infercnvpy / spatialde** — reclassified to `unknown` (was `pip_only`): the proxy was down at audit time so `mamba search` could not confirm availability. All four have a non-trivial chance of being on bioconda. Task 1 must verify each with `mamba search -c bioconda <pkg>` on a network-connected machine before deciding whether to lift them to environment.yml or leave them in pyproject extras.

## Migration path for existing OmicsClaw envs

Recommended:
```
mamba env update -n OmicsClaw -f environment.yml --prune
mamba run -n OmicsClaw pip install -e ".[full,singlecell-upstream]"
```
If `--prune` removes too aggressively or update fails, fall back to clean rebuild:
```
mamba env remove -n OmicsClaw -y
bash 0_setup_env.sh
```

## Open questions

- liana / liana-py — bioconda has it (1.7.1, noarch). Move to mamba in Task 1.
- tangram-sc — confirmed no conda recipe; stays pip_only.
- torch — needs the `pytorch` conda channel (not bioconda/conda-forge). Add to environment.yml explicitly in Task 1.

**Verify before Task 1 finalizes:** the audit's offline mode could not classify
`cell2location`, `cellphonedb`, `infercnvpy`, `spatialde` (`unknown` rows in
the CSV). All four have a non-trivial chance of being on bioconda; Task 1
should re-run `mamba search -c bioconda <pkg>` on a network-connected machine
for each before deciding whether to lift them or leave them in pyproject.

## Audit run notes

The audit was run on 2026-05-02. The `mamba search` approach used in `scripts/audit_conda_availability.py` failed on this machine because the conda proxy at `10.20.16.126:8081` (configured in `/root/.condarc`) returns HTTP 502 Bad Gateway for bioconda and conda-forge channel paths (it only proxies `free` and `main`). All 42 packages returned non-zero from `mamba search`, producing an all-`pip_only` result.

**Workaround applied:** The OmicsClaw conda env was originally built from direct `conda.anaconda.org` channels, leaving fresh repodata JSON caches in `/opt/conda/pkgs/cache/` for:
- `conda-forge/linux-64` (408 MB, mod Sat 02 May 2026 11:26:58 GMT)
- `conda-forge/noarch` (170 MB, mod Sat 02 May 2026 11:32:10 GMT)
- `bioconda/linux-64` (36 MB, mod Sat 02 May 2026 09:23:05 GMT)
- `bioconda/noarch` (37 MB, mod Sat 02 May 2026 05:23:32 GMT)

These cache files were loaded directly in Python to perform the audit offline. Classification logic: `mamba_ok` if the package has a `py311` compiled build OR a `noarch` pure-Python build (build strings like `pyhd8ed1ab_0`, `pyhdfd78af_0` are compatible with any Python version). 42 packages classified: 27 mamba_ok, 11 pip_only, 4 unknown (64% mamba_ok — meets the expected 60%+ threshold; the 4 unknown packages may push mamba_ok higher once verified on a network-connected machine).

The `scripts/audit_conda_availability.py` script has been updated to correctly handle noarch packages in the `mamba search` JSON output path; the offline cache analysis confirmed the logic is sound.
