# Singlecell Development Checklist

Use this checklist before saying a single-cell skill is aligned with OmicsClaw.

## Matrix & Contract

- [ ] output object is named `processed.h5ad`
- [ ] `omicsclaw_input_contract` is written
- [ ] `omicsclaw_matrix_contract` is written
- [ ] `X` is declared as either `raw_counts` or `normalized_expression`
- [ ] `layers["counts"]` is present whenever raw counts matter
- [ ] `adata.raw` is a raw-count snapshot when writing AnnData

## Runtime Environment

- [ ] no `os.environ.setdefault("NUMBA_DISABLE_JIT", "1")` in skill code or shared `_lib` modules — this corrupts numba after scanpy has already initialized the JIT compiler, causing cold-start crashes (`AttributeError: 'function' object has no attribute 'get_call_template'`). Only `tests/conftest.py` may set it (separate process).
- [ ] no bare `os.environ.setdefault("NUMBA_CACHE_DIR", ...)` or `os.environ.setdefault("MPLCONFIGDIR", ...)` — use `omicsclaw.common.runtime_env.ensure_runtime_cache_dirs()` instead for unified cache management
- [ ] no `os.environ` manipulation of library internals (`NUMBA_*`, `OMP_*`, `MKL_*`) after the affected library has already been imported

## Preflight & Validation

- [ ] preflight checks matrix semantics before running a method
- [ ] normalized-only methods do not silently accept count-oriented `X`
- [ ] count-based methods do not silently sum normalized values
- [ ] preflight guidance is good enough for a user who does not already know the scRNA workflow

## Parameters & Methods

- [ ] `SKILL.md` states the matrix expectations honestly
- [ ] method-specific parameters are mapped honestly when multiple methods exist
- [ ] critical selector parameters such as `use_rep` / `groupby` / `batch_key` are treated as first-class user-facing parameters when they change the analysis result
- [ ] users can override all defaults via CLI flags (`--marker-file`, `--reference`, `--model`, etc.)

## Documentation

- [ ] guardrail and skill-guide mention the same matrix expectations
- [ ] guardrail and skill-guide explain upstream step, key defaults, and usual next step in beginner-friendly language
- [ ] `SKILL.md` includes Reference Data Guide (or equivalent) when external data is needed
- [ ] `SKILL.md` includes method selection table for multi-method skills

## Output & Consistency

- [ ] figures, tables, `figure_data`, and `result.json` match the same analysis result
- [ ] tests cover at least one contract-success path and one contract-mismatch path

## Workflow Guidance

- [ ] **stdout**: success banner后打印 `▶ Next step:` + copy-pasteable 命令，告诉用户下一步该跑什么 skill
- [ ] **result.json**: 包含 `next_steps` 字段（`[{"skill": "sc-xxx", "reason": "...", "priority": "recommended|optional"}]`），供 bot/LLM 自动推荐
- [ ] **result.json**: 包含 `preprocessing_state_after` 字段（如 `"qc_computed"`, `"filtered"`, `"normalized"`, `"clustered"`, `"annotated"`），供 bot 追踪数据集状态（仅改变数据预处理状态的 skill 需要）
- [ ] **SKILL.md**: 包含 `## Workflow Position` 段，写明 **Upstream**（通常的上游 skill）和 **Downstream**（通常的下游 skill）
- [ ] **preflight/runtime**: 对新手的引导是运行时行为（print 到 stdout），不只是写在 SKILL.md 文档里
- [ ] **demo 模式**: `apply_preflight(decision, logger, demo_mode=args.demo)` — demo 模式下 `needs_user_input` 降级为 guidance 但 `blocked` 不降级

## User Experience (see SC-USER-EXPERIENCE-RULES.md)

- [ ] skill detects feature/gene overlap with defaults before running analysis
- [ ] skill detects species/organism mismatch when using species-specific defaults
- [ ] skill detects degenerate output (all Unknown, all NaN, empty, single group) and reports it
- [ ] **stdout**: failure message includes numbered fix options with copy-pasteable example commands
- [ ] **report.md**: includes Troubleshooting section when output is degenerate
- [ ] **result.json**: includes diagnostic fields (`all_unknown`, `suggested_actions`) for bot/agent
- [ ] error messages for missing references include download URLs and alternative methods
- [ ] knowledge_base skill-guide includes troubleshooting for the most common failure mode
- [ ] fallbacks are transparent: logged at WARNING, recorded in summary, shown in stdout and report.md

## R Enhanced Plots (optional, only if skill supports --r-enhanced)

- [ ] `--r-enhanced` argparse flag added to skill's argument parser
- [ ] `R_ENHANCED_PLOTS` dict defined at module level: maps renderer name → output filename (e.g. `"plot_cell_dim": "r_cell_dim.png"`)
- [ ] `_render_r_enhanced(output_dir, figure_data_dir, r_enhanced)` called after `_render_figures()` — never before
- [ ] R Enhanced figures written to `figures/r_enhanced/` subdirectory (not mixed with Python figures)
- [ ] `call_r_plot()` is the only entry point — imported from `skills.singlecell._lib.viz.r`
- [ ] R failure produces a Python `warnings.warn()` only — Python figures are unaffected and already on disk
- [ ] result.json includes R Enhanced figures with `"backend": "r_enhanced"` tag
- [ ] Each renderer name in `R_ENHANCED_PLOTS` is registered in `skills/singlecell/_lib/viz/r/registry.R`'s `R_PLOT_REGISTRY` dict before the skill ships
