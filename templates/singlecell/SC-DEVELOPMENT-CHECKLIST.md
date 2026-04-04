# Singlecell Development Checklist

Use this checklist before saying a single-cell skill is aligned with OmicsClaw.

- [ ] output object is named `processed.h5ad`
- [ ] `omicsclaw_input_contract` is written
- [ ] `omicsclaw_matrix_contract` is written
- [ ] `X` is declared as either `raw_counts` or `normalized_expression`
- [ ] `layers["counts"]` is present whenever raw counts matter
- [ ] `adata.raw` is a raw-count snapshot when writing AnnData
- [ ] preflight checks matrix semantics before running a method
- [ ] normalized-only methods do not silently accept count-oriented `X`
- [ ] count-based methods do not silently sum normalized values
- [ ] `SKILL.md` states the matrix expectations honestly
- [ ] guardrail and skill-guide mention the same matrix expectations
- [ ] figures, tables, `figure_data`, and `result.json` match the same analysis result
- [ ] tests cover at least one contract-success path and one contract-mismatch path
