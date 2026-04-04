# Singlecell Matrix Contract

This file defines the canonical matrix semantics for OmicsClaw scRNA skills.

## Core Rule

Only two public semantic states are allowed for `adata.X` in scRNA output objects:
- `raw_counts`
- `normalized_expression`

Do not persist `scaled_expression` as the public meaning of `adata.X`.
If scaling is needed, do it transiently in memory and write a normalized object back out.

## Stable Meanings

- `adata.layers["counts"]`
  - stable raw counts source
  - should be integer-like or count-like
  - downstream count-based methods should prefer this first

- `adata.X`
  - current active matrix for the current stage
  - must be declared in `adata.uns["omicsclaw_matrix_contract"]["X"]`
  - allowed values: `raw_counts`, `normalized_expression`

- `adata.raw`
  - raw-count snapshot aligned to the current object
  - should not be used as a vague catch-all container
  - for singlecell, prefer `raw_counts_snapshot`

## Required Metadata

Every single-cell skill that writes an AnnData should write:
- `adata.uns["omicsclaw_input_contract"]`
- `adata.uns["omicsclaw_matrix_contract"]`

Minimum `omicsclaw_matrix_contract` structure:

```python
{
  "X": "raw_counts" | "normalized_expression",
  "raw": "raw_counts_snapshot" | None,
  "layers": {"counts": "raw_counts" | None},
  "producer_skill": "skill-name",
}
```

Optional additions:
- `preprocess_method`
- `primary_cluster_key`

## Skill-Level Expectations

### Count-oriented outputs
Examples:
- `sc-standardize-input`
- `sc-qc`

Expected contract:
- `X = raw_counts`
- `layers["counts"] = raw_counts`
- `raw = raw_counts_snapshot`

### Normalized outputs
Examples:
- `sc-preprocessing`

Expected contract:
- `X = normalized_expression`
- `layers["counts"] = raw_counts`
- `raw = raw_counts_snapshot`

## Reading Rule For Downstream Skills

- if a method needs raw counts:
  1. use `layers["counts"]`
  2. else use `adata.raw` only if contract says `raw_counts_snapshot`
  3. else use `adata.X` only if contract says `raw_counts`

- if a method needs normalized expression:
  1. prefer `adata.X` when contract says `normalized_expression`
  2. otherwise stop in preflight and tell the user to run `sc-preprocessing`

Do not guess matrix meaning from object shape alone when a contract is available.
