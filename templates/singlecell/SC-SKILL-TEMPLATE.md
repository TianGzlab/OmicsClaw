# Singlecell Skill Template Addendum

Use this together with `templates/SKILL-TEMPLATE.md` when creating or refactoring a scRNA skill.

## Required Additions For `SKILL.md`

### Data / State Requirements

Every scRNA skill should declare:
- whether it needs raw counts or normalized expression
- where it expects them from (`layers["counts"]`, `X`, `raw`)
- whether clustering / labels / batch metadata must already exist

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

## Required Additions For Companion Docs

Every scRNA skill should have:
- a guardrail file
- a skill-guide file

Those files should mention the method-specific matrix expectation explicitly.

## Anti-Patterns

Do not do these:
- assume `adata.raw` always means normalized expression
- assume `adata.X` always means normalized expression
- silently use count-like `X` for normalized-only methods
- persist `scaled_expression` as the public output meaning of `X`
