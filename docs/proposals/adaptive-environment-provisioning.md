# Adaptive Per-Skill Environment Provisioning for OmicsClaw

> **Current status (2026-09-24):** the implementation described below was removed together with the skill runner; runtime environment provisioning is now planned in [plan 0061](../plans/0061-adaptive-env-provisioning.md). This document is kept as history.

> **Status:** ACCEPTED + IMPLEMENTED (Phases 0–3), each phase Codex-verified.
> **Author:** OmicsClaw agent (Claude). **Date:** 2026-06-29.
>
> **Implementation summary (2026-06-29):**
> - **Phase 0** — `requires:` wired into runtime metadata; `dep_spec.py` (import↔pip
>   bridge via `DEPENDENCY_REGISTRY`, classification, pip-spec resolution).
> - **Phase 1** — `env_resolver.py` probe-only resolver at the single runner seam
>   (`runner._prepare_skill_run`); async-offloaded; modes off/probe/on + kill-switch.
> - **Phase 2** — `venv_provision.py` content-addressed `--system-site-packages`
>   overlay venvs (uv-create + **venv-pip `--no-deps` install** for ABI-safety —
>   `uv pip` was found to shadow base numpy/pandas), fingerprint cache, flock lock;
>   the `on` provisioning branch. **Default-on** (user-confirmed). Non-fatal throughout.
> - **Phase 3** — provenance (`SkillRunResult.runtime_source`); AutoAgent env
>   whitelist; `oc env overlays|clean` cache management.
> - **Deferred (documented):** per-method dep slicing (`--no-deps` makes over-install
>   cheap); routing the literature/replot special call-paths through the resolver
>   (edge, non-fatal). Skill-to-skill `sys.executable` calls self-resolve (a child
>   inherits the parent's venv interpreter).
> - Disable anytime: `OMICSCLAW_SKIP_ADAPTIVE_ENV=1` or `OMICSCLAW_ADAPTIVE_ENV=off`.
> - ~97 new tests (dep_spec / env_resolver / venv_provision / phase3), all green.
>
> Original proposal (reviewed by an independent Codex pass) follows.
> **Reviewers:** Codex (gpt-5.5, xhigh, read-only) cross-checked every load-bearing
> claim against the codebase; its corrections are folded in and marked
> _[Codex]_ where they changed the design.

## Goal

Let OmicsClaw decide **at analysis time** whether a skill's required
dependencies are already importable. If yes → run the skill in the active
environment with **zero overhead** (today's behavior). If no → transparently
create/reuse a managed overlay virtualenv, install **only the missing pip
leaves**, and run there. This removes the hard requirement that users
pre-build the entire conda environment (`bash 0_setup_env.sh`) before any
skill works — while **never** attempting a doomed install or leaving the user
worse off than today.

> **Scope honesty (critical, _[Codex]_-reinforced):** the adaptive venv handles
> **pip-installable leaves** and **base-deps-only domains**. It deliberately does
> **not** try to replace conda for the heavy, pip-hostile stack (scvi-tools,
> torch, cellrank, scvelo, scanpy-family) that was *intentionally* moved to
> `environment.yml` Tier 4 because pip resolution blows up (`pyproject.toml:43-50`,
> `environment.yml:219-239`). Nor R packages, nor CLI tools (samtools/STAR/GATK),
> nor conda-only/version-conflicting packages (`pybanksy` numpy<2.0). For those,
> the resolver **degrades gracefully** with a clear "build the conda env" hint
> rather than launching a multi-minute failing pip solve.

---

## 1. Reference design — how cellclaw does it

cellclaw's adaptivity is **emergent, not a single decision tree**. Its declarative
"declare packages → build venv → install → fingerprint-skip" module
(`core/skill_runtime.py:90-145`) is **dormant** (zero `runtime.toml` on disk, zero
callers). What actually runs is three cooperating layers:

1. **Per-project overlay venv** — `core/project_uv.py:25` runs
   `uv venv --system-site-packages <project>/.venv` once per project
   (`--system-site-packages` hardcoded at `:51`). The venv inherits the base
   interpreter's site-packages, so installed packages import without reinstall;
   the venv is a *writable overlay* that only absorbs `pip install` of missing
   leaves. Idempotent (`_venv_looks_valid` short-circuit); best-effort (returns
   `False` if `uv` absent or `CELLCLAW_SKIP_PROJECT_UV_VENV` set).
2. **Execution wiring** — `agent/tools/shell.py:777-833`: before any command it
   prepends the venv `bin` to `PATH`, sets `VIRTUAL_ENV` / `PYTHONNOUSERSITE=1`,
   and rewrites leading `python`/`pip` to the venv's absolute python. Every skill
   script transparently runs *inside* the overlay venv.
3. **Detection = in-script import probe** — 140 skill scripts use
   `try: import X / except ImportError: raise ImportError("… pip install X")`. On
   miss, the **LLM agent** decides to `pip install` (landing in the overlay).

**Port these patterns** (not the dormant orchestration): the
`--system-site-packages` overlay, the uv→stdlib-venv fallback
(`skill_runtime.py:108-121`), the sha256 fingerprint-skip
(`skill_runtime.py:34,128,137`), cross-platform venv helpers
(`skill_runtime.py:20-49`), exec-time PATH/VIRTUAL_ENV injection
(`shell.py:802-831`), skip env vars + non-fatal best-effort, lazy idempotent
creation. **Do not port** the `runtime.toml` schema or the cwd-walk venv
discovery — OmicsClaw resolves venvs by an explicit managed path.

**OmicsClaw will do this _deterministically_** (a resolver), which is strictly
better than cellclaw's agent-driven emergence: reproducible, no LLM in the loop,
and testable.

---

## 2. OmicsClaw current state

**Execution path (out-of-process subprocess; never in-process import):**
`oc run <skill>` → `run_skill` → `_prepare_skill_run` (`omicsclaw/skill/runner.py:112`)
→ argv at `runner.py:204-212` via
`build_skill_argv(python_executable=get_skill_runner_python(), …)` → env at
`runner.py:241-247` (`PYTHONPATH` prepend + `PYTHONNOUSERSITE=1`, **no
`VIRTUAL_ENV`**) → `drive_subprocess` / async `adrive_subprocess`.

**The manual-env assumption lives in** `get_skill_runner_python()`
(`skill/execution/python_runtime.py:25-57`): one global interpreter
(`sys.executable` or `OMICSCLAW_RUN_PYTHON`), no per-skill selection, **no
dependency probe**. A missing dep just ImportErrors in the subprocess.

**Existing dependency infrastructure (fragmented — reuse, don't reinvent):**

| Source | Keyed by | Reality |
|---|---|---|
| `pyproject.toml [optional-dependencies]` | extra name | Holds **only pip-only "conda-residue" leaves** (SpaGCN, GraphST, torch_geometric, cellcharter, tangram-sc, cell2location, flashdeconv, cellphonedb, fastccc, SpatialDE, infercnvpy, paste-bio, pyVIA, phate). Heavy stack moved to conda. `genomics/proteomics/metabolomics` and several `singlecell-*` extras are **empty** by design (`pyproject.toml:124-127,150-153,229-237`). |
| `skills/<domain>/_lib/dependency_manager.py` `DEPENDENCY_REGISTRY` | **method**→`DependencyInfo` | **Live runtime gate** (`require()`/`is_available()`). Field is `module_name` for spatial/singlecell but **`import_name`** for proteomics/metabolomics _[Codex]_ (`skills/proteomics/_lib/dependency_manager.py:8`, `metabolomics/…:8`). Some `install_cmd` point at now-**empty** extras (`scvi-tools`→`.[singlecell-batch]`) so `install_cmd` is **not** a reliable machine pip spec _[Codex]_ (`skills/singlecell/_lib/dependency_manager.py:24-31`). Carries `availability_check` for the BANKSY sub-env. |
| `omicsclaw/core/dependency_manager.py` `DOMAIN_TIERS` | import-name→tier | `check_dependencies()` has zero callers (dormant); `get_installed_tiers()` is a reusable probe library. |
| `omicsclaw/core/r_dependency_manager.py` `R_TIER_PACKAGES` | R skill-tier→R pkgs | Live `Rscript` validation. R-only. |
| `skills/*/parameters.yaml` `install:` / top-level `requires:` | skill | 33-38/95 coverage, import-time hard deps; **migrated through but the registry never loads it** — orphaned. |
| `SKILL.md requires:` frontmatter | skill | 82/95, core-deps only; display/preflight. |
| `environments/banksy.yml` + `core/external_env.py` | conda sub-env | The one materialized isolated env (`mamba run -n omicsclaw_banksy …`) for numpy<2.0. |

---

## 3. Design principles

1. **Additive overlay, never replacement.** Create the venv with
   `--system-site-packages` **from the target `base_python`** _[Codex]_ so it
   inherits that interpreter (conda env if provisioned, bare python otherwise).
   It only absorbs additive pip leaves; never a version-conflicting pin of an
   already-present base package.
2. **Probe first, provision only on miss.** A fully-provisioned machine returns
   in-place with zero venv work.
3. **Non-fatal, best-effort.** Any failure (no uv, no network, no pip mapping,
   install error) → warn + run in base env → the user gets the *same* ImportError
   as today, never worse. `OMICSCLAW_SKIP_ADAPTIVE_ENV=1` restores exact legacy
   behavior.
4. **Reuse existing maps**; introduce no new manifest format if the curated
   registries + `parameters.yaml` already encode the truth.
5. **Respect the conda/R/CLI boundary at the _method_ level** _[Codex]_ — a single
   skill can mix Python and R/CLI methods (`spatial-deconv`, `sc-count`).
6. **One main seam owns both halves** (interpreter + env overlay), with the known
   bypasses fixed explicitly.

---

## 4. Architecture

### 4.1 The seam — main, not only _[Codex]_

Primary edit at `omicsclaw/skill/runner.py:204-247`, replacing the bare
`get_skill_runner_python()` with an adaptive resolver and merging its overlay
into `env`. Because both `run_skill` (`:419-429`) and `arun_skill` (`:498-509`)
share `_prepare_skill_run`, this covers CLI (`omicsclaw.py:1509-1519`), desktop
executor (`omicsclaw/execution/executors/default.py:117-126`), bot/agent
(`runtime/tools/builders/agent_executors.py:442-454`, `skill/chain.py:136-147`),
and generic pipelines (`pipeline_runner.py:81-116`, which re-resolve per step).

**Known bypasses to address separately (Phase 3):**
- Literature parse shells out to `literature_parse.py` directly
  (`agent_executors.py:1093-1102`).
- Replot wrapper invokes `omicsclaw.py replot` (`agent_executors.py:681-683`).
- Some skill scripts shell out to *other* skill scripts with raw `sys.executable`
  (`skills/spatial/spatial-de/spatial_de.py:1364`,
  `skills/spatial/spatial-annotate/spatial_annotate.py:719`).
These won't get per-target adaptive resolution until they route through the
resolver (or read `CELLCLAW_PREFERRED_PYTHON`-style env we export).

### 4.2 New modules

- `omicsclaw/skill/execution/env_resolver.py` — `resolve_skill_runtime(skill_info,
  *, method, base_python) -> SkillRuntime(python, env_overlay, source, notes)`.
- `…/execution/venv_utils.py` — `venv_looks_valid` / `get_venv_python` /
  `venv_bin_dir` (POSIX `bin` vs Windows `Scripts`), ported from
  `skill_runtime.py:20-49`.
- `…/execution/venv_provision.py` — `ensure_overlay_venv(venv_dir, base_python)`
  (`uv venv --python <base_python> --system-site-packages` → `<base_python> -m
  venv --system-site-packages`), `install_into_venv(venv_py, pip_specs)`, and the
  fingerprint cache (see §5) + a per-venv lock with stale-lock recovery.
- `…/execution/dep_spec.py` — `required_imports_for(skill_info, method)`,
  `runtime_kind(skill_info, method)` (method-level), and `pip_specs_for(imports)`
  (the import→pip-spec resolver, §6).

### 4.3 Wiring

```python
runtime = resolve_skill_runtime(skill_info, method=requested_method,
                                base_python=get_skill_runner_python())
cmd = build_skill_argv(python_executable=runtime.python, ...)   # no signature change
env = os.environ.copy()
env["PYTHONPATH"] = str(OMICSCLAW_DIR) + os.pathsep + env.get("PYTHONPATH", "")
env.setdefault("PYTHONNOUSERSITE", "1")
env.update(runtime.env_overlay)        # VIRTUAL_ENV + PATH prepend, only on venv branch
```

For `arun_skill`, provisioning must run **off the event loop** _[Codex]_
(`asyncio.to_thread` / a provisioning executor) so it doesn't block before the
first await (`runner.py:498-520`).

---

## 5. The adaptive decision algorithm

```
resolve_skill_runtime(skill_info, method, base_python):

1. SKIP GUARD
   if OMICSCLAW_SKIP_ADAPTIVE_ENV in {1,true,yes,on}:
        return SkillRuntime(base_python, {}, source="skip")   # exact legacy

2. METHOD-LEVEL KIND GATE  _[Codex]_
   kind = runtime_kind(skill_info, method)   # python | r | cli | conda-isolated | hybrid
   if kind in {r, cli, conda-isolated}:
        return SkillRuntime(base_python, {}, source="base")   # existing validators/sub-env bridge
        # hybrid: only the Python sub-deps are eligible; R/CLI parts deferred.

3. COMPUTE REQUIRED IMPORT NAMES  (§6)
   imports = BASE_IMPORTS ∪ deps_for(skill, method)
   imports -= DENY_PROBE            # banksy/cnvkit/velocyto/cellranger + conda-only

4. PROBE — ALWAYS via subprocess against the TARGET interpreter w/ the FINAL env  _[Codex]_
   missing = subprocess_find_spec(base_python, imports, env=final_env_with_PYTHONNOUSERSITE)
   if not missing:
        return SkillRuntime(base_python, {}, source="base")   # ← IN-PLACE, no venv

5. RESOLVE pip SPECS — bail soft if not pip-installable
   pip_specs = pip_specs_for(missing)        # import→pip name+version; None for conda/R/CLI-only
   unmet = [m for m in missing if not pip_specs.has(m)]
   if unmet:                                  # e.g. scvi-tools on a bare base env
        warn(f"{skill}:{method} needs {unmet}; not pip-installable here. "
             f"Run `bash 0_setup_env.sh` (conda) — see install hint.")
        return SkillRuntime(base_python, {}, source="base")   # never launch a doomed solve

6. RESOLVE MANAGED VENV  (content-addressed key, managed cache root)
   key = runtime_key(base_python, platform, resolver, sorted(pip_specs))   # §Decisions D2/D3
   venv_dir = ENV_ROOT / key / ".venv"
   fp = sha256(base_python_path+version, sys.prefix, platform/ABI, resolver_version,
               sorted(pip_specs), pyproject/env hashes)        # richer fingerprint _[Codex]_
   with venv_lock(venv_dir):                                   # TOCTOU-safe, stale-lock recovery
        if not venv_looks_valid(venv_dir):
             if not ensure_overlay_venv(venv_dir, base_python):  # uv→stdlib, from base_python
                  warn(...); return SkillRuntime(base_python, {}, source="base")
        venv_py = get_venv_python(venv_dir)
        still = subprocess_find_spec(venv_py, imports, env=final_env)
        if still and not fingerprint_matches(venv_dir, fp):
             if not install_into_venv(venv_py, pip_specs_for(still), timeout=1800):
                  warn("auto-install failed; base-env fallback"); 
                  return SkillRuntime(base_python, {}, source="base")
             write_fingerprint(venv_dir, fp)

7. RETURN SkillRuntime(venv_py, overlay(venv_dir), source=f"venv:{key}",
                       notes=[f"auto-installed {still} into {key}"])
```

**`--system-site-packages` is load-bearing** (steps 4-6): the venv inherits the
base conda env, so the heavy Tier-4 stack imports without reinstall and only the
missing pip leaf lands in the overlay — otherwise every venv would re-solve the
whole stack and blow the timeout. **Probe base first** (step 4) preserves today's
zero-overhead path. **Fingerprint** (step 6) makes the 2nd run instant; it keys on
the full interpreter/platform/resolver/spec identity, not just pip specs _[Codex]_,
so an env change correctly busts the cache.

---

## 6. Dependency source of truth _[Codex]_-revised

The authoritative per-method **dependency SET** comes from curated, method-aware
sources; `pyproject` is demoted to a **pip-name/version-spec lookup map only**
(it is sparse-by-design and its extra names don't match aliases).

- **PRIMARY — `skills/<domain>/_lib/dependency_manager.py` `DEPENDENCY_REGISTRY`**
  (method-level, live). It already encodes method→import-name→install hint and the
  `availability_check` sub-env override. The bridge must read **both** field names
  (`module_name` *and* `import_name`) _[Codex]_.
- **SECONDARY — `parameters.yaml` per-method `requires`/`install` block**, once
  **loaded into metadata** (a Phase-0 wiring task — today it's orphaned). This
  makes the declaration method-aware and data-driven.
- **PIP-SPEC MAP — `pyproject.toml` extras** used *only* to turn an import/pip name
  into a versioned pip spec (e.g. `infercnvpy>=0.4.0`). Requires an **explicit
  skill→extra table** because names diverge: `spatial-integrate`↔`spatial-integration`,
  `spatial-register`↔`spatial-registration`, `sc-batch-integration`↔`singlecell-batch`
  _[Codex]_ (`pyproject.toml:268,272,150`).
- **LAST RESORT — import-scan** of the skill script, only for the base-deps-only
  domains with empty extras (`genomics/proteomics/metabolomics/bulkrna`).
- **R / CLI** stay on `r_dependency_manager.py` + `validate_r_environment()`; never
  routed to the pip venv.

`omicsclaw/core/dependency_manager.py` `DOMAIN_TIERS` + `get_installed_tiers()`
provide a ready import↔tier↔representative-probe library to reuse.

---

## 7. Implementation phases

**Phase 0 — Audit & wiring (no behavior change).**
- Build the `skill×method → {pip_leaves, conda_only, r, cli}` truth table by
  reconciling `_lib` registries, `parameters.yaml`, pyproject extras, and
  `environment.yml` Tier 4.
- Load/normalize `parameters.yaml` `requires`/`install` into the registry
  metadata _[Codex]_ (extend `lazy_metadata._RUNTIME_FIELDS:14`).
- Build the explicit **skill→extra** map and the method-level `runtime_kind`
  classifier. Seed `DENY_PROBE` from documented exceptions (`pybanksy`, `cnvkit`,
  `velocyto`, `cellranger`).

**Phase 1 — Probe-only (observability, zero risk).** Steps 1-4 behind
`OMICSCLAW_ADAPTIVE_ENV=probe` (default off): always return base interpreter, just
log "skill:method missing {…}" using **subprocess** probing. Validate import-set
resolution against real runs. Ship & observe.

**Phase 2 — Managed venv provisioning (core).** `venv_utils` / `venv_provision`
(uv→stdlib, `--system-site-packages` from `base_python`), per-venv lock, steps 5-7,
overlay merge, async-offloaded provisioning for `arun_skill`. Default on;
kill-switch `OMICSCLAW_SKIP_ADAPTIVE_ENV`. New `OMICSCLAW_ENV_DIR`.

**Phase 3 — Bypasses, UX, provenance.** Route literature/replot/skill-to-skill
shell-outs through the resolver (or export `OMICSCLAW_PREFERRED_PYTHON`). Add the
adaptive env vars to AutoAgent's `SUBPROCESS_ENV_WHITELIST`
(`omicsclaw/autoagent/constants.py:36-41`) _[Codex]_. Friendly pre-flight message;
record `SkillRuntime.source/notes` in `SkillRunResult` + the repro notebook.
`oc env status|clean|rebuild`.

**Phase 4 — (Stretch) conda-aware sub-envs.** Generalize the `external_env.py`
BANKSY pattern to auto-create conda sub-envs for conflicting/conda-only deps when
`mamba` is present. Opt-in; out of scope for the pip-venv core.

---

## 8. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Heavy pip-hostile stack on a bare base env (scvi-tools/torch/cellrank) | step 5 bails soft with a conda hint — **never** launch a doomed pip solve |
| R / CLI / conda-only methods | method-level kind gate (step 2) → base env + existing validators/sub-env bridge |
| `--system-site-packages` inherits the *creating* interpreter _[Codex]_ | create from **`base_python`** (`uv venv --python` / `<base_python> -m venv`) |
| In-process `find_spec` lies (PYTHONNOUSERSITE is child-only) _[Codex]_ | always probe via **subprocess** with the final env |
| Provisioning blocks the desktop event loop _[Codex]_ | offload (`to_thread`/executor) in `arun_skill` |
| Fingerprint too coarse _[Codex]_ | key on base-python path+version, `sys.prefix`, platform/ABI, resolver version, pip specs, pyproject/env hashes |
| Extra names ≠ aliases; extras sparse/empty _[Codex]_ | explicit skill→extra map; pyproject is spec-map only, not the dep set |
| `module_name` vs `import_name` field variance _[Codex]_ | bridge reads both |
| BANKSY double-provision _[Codex]_ | `availability_check` detects the sub-env; `DENY_PROBE` excludes it from pip overlay |
| AutoAgent strips env _[Codex]_ | extend `SUBPROCESS_ENV_WHITELIST` |
| Concurrency / TOCTOU | per-venv lock + stale-lock recovery |
| Offline / no-uv / Windows | non-fatal fallback; uv→stdlib venv; `Scripts/python.exe` handled |

---

## 9. Decisions for your review (recommended defaults)

- **D1 — uv hard vs soft.** **SOFT** (uv→stdlib fallback). _Codex: agree._
- **D2 — venv granularity.** **PER-RUNTIME-KEY** (content-addressed by the resolved
  pip-spec set + base-python + platform), giving per-skill-or-finer isolation while
  *deduplicating identical envs*. _Codex changed this from my original per-domain:_
  domains mix heterogeneous Python/R/CLI/conflict-prone methods, so per-domain is
  too coarse. (Per-domain remains available as a coarser opt-in.)
- **D3 — venv location.** Managed cache via `OMICSCLAW_ENV_DIR`, default
  `~/.cache/omicsclaw/envs/<key>/.venv`; **include python+platform in the key**.
  _Codex: agree._
- **D4 — conda interop.** **ADDITIVE OVERLAY**, created from the target `base_python`,
  constrained to never shadow a conda-provided package. _Codex: agree with caveat._
- **D5 — source of truth.** **Curated `_lib` registry + `parameters.yaml` (method-aware)
  as the dependency SET; pyproject extras as a pip-spec MAP only; import-scan last
  resort.** _Codex changed this from my original "pyproject primary":_ pyproject is a
  thin, sparse residue map and misclassifies skills.
- **D6 — UX.** **Friendly pre-flight** ("needs Y; auto-installing into <key>…");
  on an unresolvable miss, degrade with a clear hint — never silently run a doomed
  command. _Codex: agree._

> **Bigger optional decision raised by both passes:** should `parameters.yaml`
> become the *canonical* per-skill/per-method dependency declaration (wired into the
> registry + `catalog.json`)? That is a larger, higher-value investment than the
> minimal pip-spec-map approach above. Flag your preference.

---

## 10. Testing & smallest end-to-end slice

- **Unit:** import-set + kind classification (incl. `spatial-deconv` Python/R split,
  `sc-count` CLI), import↔pip bridge (`scvi-tools`/`scvi`, both `module_name`/`import_name`),
  fingerprint stability, venv helpers (POSIX + Windows).
- **Integration (no network):** monkeypatch the subprocess probe + installer →
  assert in-place vs venv vs soft-bail; assert overlay carries `VIRTUAL_ENV`+PATH
  only on the venv branch; assert `OMICSCLAW_SKIP_ADAPTIVE_ENV=1` reproduces
  today's argv/env byte-for-byte.
- **Smallest E2E** _[Codex]_: one fixture skill needing a tiny pip-only wheel;
  install into a temp `OMICSCLAW_ENV_DIR` overlay (local wheel, no PyPI); `run_skill`
  verifies the subprocess imports it; a second `run_skill` skips install (fingerprint
  hit). This proves probe→provision→reuse end-to-end in one test.
- Cross-check against `tests/` known-pre-existing failures before calling anything a
  regression.

---

## 11. Backward compatibility

Default-off in Phase 1; default-on in Phase 2 with the kill-switch.
`OMICSCLAW_RUN_PYTHON` is preserved (it becomes the `base_python` the resolver
overlays onto). No change to skill scripts or the registry schema in the core
phases (the `parameters.yaml` wiring in Phase 0 is additive). `0_setup_env.sh`
remains the recommended path for a fully-provisioned machine; the adaptive layer is
a safety net + incremental on-ramp, not a replacement.

---

## Appendix — anchor map

Seam `omicsclaw/skill/runner.py:204-247`; interpreter
`skill/execution/python_runtime.py:25-57`; argv `…/argv_builder.py:64-90`;
registry/metadata `skill/registry.py`, `skill/lazy_metadata.py:14`; dep maps
`pyproject.toml[optional-dependencies]`, `skills/<domain>/_lib/dependency_manager.py`,
`omicsclaw/core/{dependency_manager,r_dependency_manager}.py`,
`scripts/audit_conda_availability.py`; sub-env `environments/banksy.yml`,
`omicsclaw/core/external_env.py`; bypasses `agent_executors.py:681,1093`,
`spatial_de.py:1364`, `spatial_annotate.py:719`; AutoAgent whitelist
`autoagent/constants.py:36`; cellclaw reference `core/project_uv.py`,
`core/skill_runtime.py`, `agent/tools/shell.py:777-833`.

*OmicsClaw is a research and educational tool for multi-omics analysis. It is not a
medical device and does not provide clinical diagnoses. Consult a domain expert
before making decisions based on these results.*
