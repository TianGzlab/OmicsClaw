# Singlecell Method Matrix Rules

Use this file to decide what matrix state each method should consume.

## Rule 1

Every method in every single-cell skill must declare one of these expectations:
- `requires_raw_counts`
- `requires_normalized_expression`
- `mixed_by_method`

Do not leave matrix expectations implicit.

## Rule 2

If a method requires raw counts:
- prefer `layers["counts"]`
- never silently sum log-normalized values
- if only `X` exists, use it only when contract says `X = raw_counts`

Typical examples:
- `sc-qc`
- `sc-doublet-detection`
- `sc-ambient-removal`
- `sc-de` with `deseq2_r`
- count-based integration backends

## Rule 3

If a method requires normalized expression:
- require `X = normalized_expression`
- do not silently accept a count-oriented object from `sc-qc`
- do not assume `adata.raw` is normalized in singlecell

Typical examples:
- `sc-cell-annotation` marker / reference methods
- `sc-cell-communication` methods expecting normalized expression
- `sc-markers`
- `sc-grn`
- exploratory single-cell DE methods on normalized expression

## Rule 4

If a skill has mixed methods:
- document method-specific matrix needs in `SKILL.md`
- encode the distinction in preflight
- mention the exact expected source in `skill-guide`

## Rule 5

If a method needs scaled values internally:
- scale transiently in memory
- compute PCA / neighbors / model fit as needed
- but do not persist the final `processed.h5ad` with `X = scaled_expression`

The public output object should still end as either `raw_counts` or `normalized_expression`.
