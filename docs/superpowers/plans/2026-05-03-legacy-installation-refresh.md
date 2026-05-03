# Legacy Installation Guide Refresh Plan

**Goal:** Refresh `docs/_legacy/INSTALLATION.md` so it reflects the current
`0_setup_env.sh`-managed dependency stack.

**Scope and non-goals:**
- Update documentation only.
- Keep `bash 0_setup_env.sh` as the recommended full-install path.
- Preserve venv/pip as a lightweight Python-only fallback.
- Do not change `0_setup_env.sh`, `environment.yml`, or `pyproject.toml`.

**Key assumptions:**
- `README.md` is the current contributor-facing source for installation
  behavior.
- `environment.yml` owns R packages, bioinformatics CLIs, build tooling, and
  most heavy Python science dependencies.
- `pyproject.toml` owns the editable package, console scripts, and thin
  pip-only residue.

**File map:**
- Modify: `docs/_legacy/INSTALLATION.md`
- Modify: `docs/superpowers/plans/README.md`
- Create: `docs/superpowers/plans/2026-05-03-legacy-installation-refresh.md`

**Tasks:**
1. Capture current installation facts from `README.md`, `0_setup_env.sh`,
   `environment.yml`, and `pyproject.toml`.
2. Rewrite `docs/_legacy/INSTALLATION.md` around these install profiles:
   full conda-managed setup, lightweight venv setup, optional extras, runtime
   services, verification, and troubleshooting.
3. Remove stale guidance that presents pip extras as the primary analysis
   install path or tells users to manually install R system dependencies for
   the recommended path.
4. Keep concise command examples for Miniforge, custom env names, banksy,
   CUDA/CPU torch selection, `oc onboard`, app server, memory server, MCP, and
   pytest verification.
5. Update this plans index.

**Verification strategy:**
- Run `bash -n 0_setup_env.sh`.
- Run `python -m pytest -q tests/test_context_assembler.py`.
- Search `docs/_legacy/INSTALLATION.md` for stale primary-install language
  such as "start with `pip install -e .`" and manual R install instructions.

**Acceptance criteria:**
- The guide leads with `bash 0_setup_env.sh`.
- The guide accurately describes dependency ownership across
  `environment.yml`, `pyproject.toml`, and Tier 3 GitHub R installs.
- Lightweight pip/venv guidance is explicitly labeled Python-only.
- Verification and troubleshooting sections match the current CLI surface.
