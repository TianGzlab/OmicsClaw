# Singlecell Preflight Rules

Use this file when adding or refactoring preflight checks for scRNA skills.

## Decision Levels

- `proceed`
- `proceed_with_guidance`
- `needs_user_input`
- `blocked`

## What Preflight Must Check

1. matrix contract
2. missing metadata
3. method-specific prerequisites
4. whether the requested question is scientifically ambiguous

## Ask The User When

- more than one `groupby`, `batch_key`, `sample_key`, `cluster_key`, or `cell_type_key` is plausible
- reference or model choice changes the scientific meaning
- a fallback would change the biological interpretation

## Block When

- a raw-count method has no usable raw counts
- a normalized-expression method only sees a count-oriented object
- required metadata is absent, not merely ambiguous
- required layers such as `spliced/unspliced` do not exist

## Guidance Rule

Do not tell users to run a helper skill by default when the current workflow can safely canonicalize the object automatically.
Only mention `sc-standardize-input` when the user wants an explicit exported canonical object or when debugging provenance is the main task.

## Matrix-Specific Rule

Preflight should trust `adata.uns["omicsclaw_matrix_contract"]` first and only fall back to heuristics when that contract is missing.
