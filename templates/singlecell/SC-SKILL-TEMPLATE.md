# Singlecell Skill Template Addendum

Use this together with `templates/SKILL-TEMPLATE.md` when creating or refactoring a scRNA skill.

## Required Additions For `SKILL.md`

### Data / State Requirements

Every scRNA skill should declare:
- whether it needs raw counts or normalized expression
- where it expects them from (`layers["counts"]`, `X`, `raw`)
- whether clustering / labels / batch metadata must already exist
- if the skill has multiple methods, which parameters are shared and which parameters are method-specific

### User Guidance Requirements

Every scRNA skill should explain the workflow in a novice-friendly way:

- if the user only says “I want to do X”, the skill should state what upstream step usually comes first
- if the current skill can safely continue with defaults, it should say which defaults will be used
- if a choice changes the biological meaning, the skill should stop and ask the user to confirm
- if a side branch is common but optional (for example doublets, batch correction), the skill should mention it explicitly instead of assuming the user already knows
- if the skill is not the right next step, the docs should say what skill the user should run next

### Workflow Section

For scRNA skills, the workflow should usually mention:
1. load
2. preflight
3. canonicalize or validate matrix state
4. run method
5. persist results
6. render gallery
7. export `processed.h5ad`

### Output Contract

Use `processed.h5ad` as the standard output object name.

## Required Additions For Code

- write `adata.uns["omicsclaw_input_contract"]`
- write `adata.uns["omicsclaw_matrix_contract"]`
- ensure matrix semantics match `templates/singlecell/SC-MATRIX-CONTRACT.md`
- ensure preflight follows `templates/singlecell/SC-PREFLIGHT-RULES.md`
- if multiple methods exist, map method-specific CLI parameters explicitly instead of hiding them behind one generic parameter set
- make novice-facing guidance part of preflight/runtime behavior, not only prose in `SKILL.md`

## Required Additions For Companion Docs

Every scRNA skill should have:
- a guardrail file
- a skill-guide file

Those files should mention the method-specific matrix expectation explicitly.
They should also mention:

- what a beginner user should do before this skill
- what this skill will do automatically
- what the key parameters mean in plain language
- what the usual next step is after the skill finishes

## Required Additions For User Experience

See `SC-USER-EXPERIENCE-RULES.md` for the full specification. Key requirements:

### Input Compatibility Detection

- If the skill uses built-in defaults (marker genes, gene sets, models), it must check feature overlap BEFORE running
- If the skill uses species-specific defaults, it must detect species and attempt auto-adaptation
- If a reference file is required, the error message must include download URLs and alternatives

### Degenerate Output Detection

Every skill must detect when its output is degenerate and report at **all three layers**:

1. **stdout (print)**: numbered fix options with example commands — this is what CLI users actually read
2. **report.md**: Troubleshooting section with causes, solutions, and example commands
3. **result.json**: machine-readable diagnostic fields + `suggested_actions` list for bot/agent

### Reference Data Guide

If the skill depends on external data (reference H5AD, pretrained models, gene sets, R packages), `SKILL.md` must include a "Reference Data Guide" section covering:

- Which method needs what
- Where to download it (specific URLs)
- How to choose the right one for their tissue/organism
- Example commands
- Alternative methods that don't need external data

### Method Selection Table

For multi-method skills, `SKILL.md` must include a decision table mapping common scenarios to recommended methods with example commands.

### Override Flags

Users must be able to override every default via a CLI flag. Never assume the built-in default is correct for every dataset. Common patterns:
- `--marker-file` for custom marker genes
- `--reference` for custom reference datasets
- `--model` for custom pretrained models
- `--gene-sets` for custom gene set files

## Required Additions For Runtime Environment

- Use `omicsclaw.common.runtime_env.ensure_runtime_cache_dirs()` for cache setup — do **not** manually `setdefault` `NUMBA_CACHE_DIR` or `MPLCONFIGDIR`
- **Never** set `NUMBA_DISABLE_JIT` in skill code or shared library modules — it corrupts numba after scanpy has already initialized the JIT compiler, causing `AttributeError` crashes on cold start. Only `tests/conftest.py` may set it (separate process).
- Never manipulate `os.environ` for library internals (`NUMBA_*`, `OMP_*`, `MKL_*`) after the affected library has already been imported in the same process

## Anti-Patterns

Do not do these:
- assume `adata.raw` always means normalized expression
- assume `adata.X` always means normalized expression
- silently use count-like `X` for normalized-only methods
- persist `scaled_expression` as the public output meaning of `X`
- expose only a generic parameter set when different methods have different real tuning knobs
- assume the user already understands the full scRNA workflow and skip upstream/downstream guidance
- silently skip features/genes that don't match and produce empty results with no warning
- produce degenerate output (all Unknown, all NaN, empty) without telling the user what went wrong and how to fix it
- print "Success" when the result is clearly wrong — detect and flag it
- write error messages that say "file not found" without telling the user where to get the file
- fall back to a different method silently without logging and recording the fallback
- set `NUMBA_DISABLE_JIT=1` in any module that may be imported after scanpy/numba — this is the #1 cause of cold-start crashes
