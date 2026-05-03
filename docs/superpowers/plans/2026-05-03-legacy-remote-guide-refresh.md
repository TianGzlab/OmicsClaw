# Legacy Remote Connection Guide Refresh Plan

**Goal:** Refresh `docs/_legacy/remote-connection-guide.md` so remote execution
setup matches the current `0_setup_env.sh`-managed OmicsClaw environment and
the current `oc app-server` remote control-plane contract.

**Scope and non-goals:**
- Update documentation only.
- Keep the existing OmicsClaw-App remote runtime model and field names.
- Do not change backend code, app code, `0_setup_env.sh`, `environment.yml`, or
  `pyproject.toml`.
- Do not update the Mintlify page unless explicitly requested; this task is for
  the legacy Markdown guide.

**Key assumptions:**
- Full remote analysis servers should use `bash 0_setup_env.sh`, not a
  Python-only venv, because remote jobs may need R packages, bioinformatics
  CLIs, and the heavy scientific stack.
- `oc app-server` is the single backend process for chat streaming, remote
  control-plane routes, notebook routes, and optional KG routes.
- Remote control-plane state lives under
  `<OMICSCLAW_WORKSPACE>/.omicsclaw/remote/`.
- `OMICSCLAW_REMOTE_AUTH_TOKEN` gates remote routers when non-empty; it is a
  no-op only when unset.

**File map:**
- Modify: `docs/_legacy/remote-connection-guide.md`
- Modify: `docs/superpowers/plans/README.md`
- Create: `docs/superpowers/plans/2026-05-03-legacy-remote-guide-refresh.md`

**Tasks:**
1. Compare the legacy guide with `README.md`,
   `docs/_legacy/INSTALLATION.md`, `docs/engineering/remote-execution.mdx`,
   `omicsclaw/app/server.py`, and `omicsclaw/remote/`.
2. Rewrite remote prerequisites and server setup around Linux/WSL/remote Linux
   plus `bash 0_setup_env.sh`.
3. Update manual and auto-start `oc app-server` examples to activate the
   `OmicsClaw` conda environment and export `OMICSCLAW_WORKSPACE` /
   `OMICSCLAW_REMOTE_AUTH_TOKEN`.
4. Preserve runtime profile fields, dataset import guidance, job/artifact
   lifecycle notes, security notes, and troubleshooting while removing stale
   venv/desktop-only setup wording.
5. Update the plans index.

**Verification strategy:**
- Run `bash -n 0_setup_env.sh`.
- Run `git diff --check` on the edited docs.
- Search `docs/_legacy/remote-connection-guide.md` for stale setup language
  such as `source .venv/bin/activate`, `pip install -e ".[desktop]"`, and
  Python 3.10 guidance.
- Inspect edited sections and referenced repo paths.

**Acceptance criteria:**
- Remote server setup leads with `bash 0_setup_env.sh` and `conda activate
  OmicsClaw`.
- The guide explains when a Python-only environment is insufficient for remote
  analysis jobs.
- Auto-start examples activate the conda env before running `oc app-server`.
- Troubleshooting covers incomplete/outdated conda environments and
  `env/doctor` failures consistently with the current install model.
