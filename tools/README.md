# tools/ — vendored source builds

OmicsClaw vendors source builds here when a tool meets ALL of these:

1. Not on bioconda for Python 3.11 (or for Linux x86_64).
2. Not on PyPI, or PyPI version is broken.
3. Not appropriate for a Layer 4 sub-env (i.e. not a Python lib with
   conflicting deps; rather a CLI binary or self-contained library).

This is the **escape hatch** of last resort. If any of conditions 1–3 is
false, use the corresponding layer instead:

- bioconda recipe → add to `environment.yml`
- PyPI package → add to `pyproject.toml` (or `environment.yml` if
  conda-forge mirrors it)
- Conflicting Python deps → create a Layer 4 sub-env in
  `environments/<tool>.yml` (see `environments/banksy.yml` for an
  example)

## Layout

Each vendored tool gets its own directory:

```
tools/
├── README.md               # this file
├── <tool-name>/
│   ├── upstream/           # git submodule or unpacked tarball
│   ├── build/              # generated; gitignored
│   └── bin/                # final binaries; symlinked into $CONDA_PREFIX/bin
```

## Adding a new vendored tool

1. Add a `build_<tool>()` function to `0_build_vendored_tools.sh` that:
   - Fetches source (git clone or curl + tar)
   - Configures + builds inside the active conda env (so it picks up
     `gxx_linux-64`/`sysroot_linux-64` from `environment.yml` Tier 0)
   - Installs binaries into `tools/<tool-name>/bin/`
   - Skips re-build if binaries already exist (idempotent)

2. Add a `link_if_exists "$TOOLS_DIR/<tool-name>/bin/<binary>"` line to
   `0_setup_env.sh` Tier 4.

3. Document the upstream source URL, build prerequisites, and version
   pinning rationale in this README.

## Why not just `apt install` / `mamba install`?

- `apt`: distro-pinned versions, no Python integration, breaks
  reproducibility.
- `mamba`: covers ~95% of bioinformatics CLIs already (see
  `environment.yml` Tier 1). Vendored builds are the 5% escape hatch.

## When to graduate a vendored tool

If upstream publishes a bioconda recipe that works for Py3.11, retire
the vendored build:

1. Add the package to `environment.yml`.
2. Remove the `build_<tool>()` function and `link_if_exists` line.
3. Delete `tools/<tool-name>/`.
