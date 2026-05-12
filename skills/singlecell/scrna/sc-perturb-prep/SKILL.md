---
name: sc-perturb-prep
description: Load when attaching cell-barcode → sgRNA assignments from a mapping TSV/CSV onto a Perturb-seq expression AnnData, producing standardised perturbation / sgRNA / target-gene obs columns. Skip when the AnnData already has perturbation labels (go straight to sc-perturb) or for raw guide-calling from FASTQ (use upstream demuxlet / cellranger guide pipelines).
version: 0.2.0
author: OmicsClaw
license: MIT
tags:
- singlecell
- scrna
- perturb-prep
- perturb-seq
- crispr
- sgrna-assignment
requires:
- anndata
- numpy
- pandas
---

# sc-perturb-prep

## When to use

The user has Perturb-seq expression data (10x h5 / matrix dir / h5ad)
**and** an upstream barcode-to-sgRNA mapping table (TSV / CSV from
demultiplex / cellranger / cellbender output) and needs them merged
into a single AnnData with:

- `obs[--pert-key]` (default `perturbation`) — canonical perturbation label
- `obs[--sgrna-key]` (default `sgRNA`) — guide identifier
- `obs[--target-key]` (default `target_gene`) — inferred target gene
- `obs["assignment_status"]` — `single_guide` / `multi_guide` / `unassigned`
- `obs["n_sgrnas"]` — count per cell

Single backend: `mapping_tsv`. Then chain to `sc-perturb` for Mixscape
classification. This skill does NOT infer guide identities from FASTQ
— bring an upstream assignment table.

## Inputs & Outputs

| Input | Format | Required |
|---|---|---|
| Expression | `.h5ad` / 10x `.h5` / 10x dir | yes (unless `--demo`) |
| Barcode → sgRNA mapping | `.tsv` / `.csv` (`--mapping-file`) | yes (unless `--demo`) |
| Column overrides | `--barcode-column` / `--sgrna-column` / `--target-column` / `--sep` | optional (auto-detect by default) |

| Output | Path | Notes |
|---|---|---|
| Standardised AnnData | `processed.h5ad` | adds `obs["perturbation"]` / `obs["sgRNA"]` / `obs["target_gene"]` / `obs["assignment_status"]` / `obs["n_sgrnas"]`; non-gene features removed from `var` |
| Per-cell assignments | `tables/perturbation_assignments.csv` | always |
| Status counts | `tables/assignment_status_counts.csv` | single_guide / multi_guide / unassigned tally |
| Perturbation tally | `tables/perturbation_counts.csv` | cells per perturbation label |
| Dropped multi-guide | `tables/dropped_multi_guide_cells.csv` | when multi-guide cells were dropped |
| Feature summary | `tables/feature_type_summary.csv` | gene vs non-gene feature breakdown |
| Figure | `figures/perturbation_counts.png` | always |
| Report | `report.md` + `result.json` | always |

## Flow

1. Load expression input via `smart_load`; load mapping via `load_sgrna_mapping` (auto-detect `--sep` if unset).
2. Strip non-gene features from `var` (e.g., 10x guide / antibody capture rows).
3. Collapse mapping rows per cell: tag `single_guide` / `multi_guide` / `unassigned` based on row count.
4. Drop `multi_guide` cells unless `--keep-multi-guide` is set.
5. Match each sgRNA against `--control-patterns` (`,`-separated, includes default NT-style patterns); rewrite matches to `--control-label` (default `NT`).
6. Infer target gene from sgRNA ID via `--delimiter` + `--gene-position`, OR use `--target-column` from the mapping if provided.
7. Save standardised AnnData, tables, figure, `report.md`, `result.json`.

## Gotchas

- **All preflight failures `raise SystemExit`, not `ValueError`.** `sc_perturb_prep.py:205` raises `SystemExit("Provide --input or use --demo")`; `:207` raises `SystemExit("Perturbation preparation requires --mapping-file for real inputs. Generate barcode-to-guide assignments upstream first.")` when `--mapping-file` is missing on a real (non-demo) run. Wrappers expecting standard `ValueError` need to catch `SystemExit`.
- **`multi_guide` cells are DROPPED by default.** Step 4 in the flow filters them out unless `--keep-multi-guide` is passed. `result.json["n_cells_multi_guide_dropped"]` (line 267 / 362) records the count. If your screen has high MOI on purpose (combinatorial perturbations), `--keep-multi-guide` is mandatory.
- **Target gene is *inferred* by default, not read from mapping.** Without `--target-column`, the script splits the sgRNA ID by `--delimiter` (default `_`) and takes token at `--gene-position` (default `0`). For sgRNA IDs like `EGFR_sg1` this gives `EGFR`; for non-standard formats (`sg-EGFR-1`, `EGFR.sg1`) you must pass `--delimiter` accordingly or supply `--target-column`.
- **Control matching is pattern-based, not exact.** `--control-patterns` (default from `DEFAULT_CONTROL_PATTERNS`) is a comma-separated list — any sgRNA whose ID **contains** one of the patterns is rewritten to `--control-label` (default `NT`). False positives are possible if a real guide's ID contains a control-pattern substring; review `tables/perturbation_assignments.csv` after the run.
- **Non-gene features in `var` are silently removed only when `var["feature_types"]` exists.** `sc_perturb_prep.py:222` calls `keep_gene_expression_features(adata)`; the helper early-returns the unchanged AnnData if `feature_types` isn't a `var` column (typical for user-loaded h5ads). When it IS present (e.g., 10x cellranger output), antibody-capture / guide-capture rows are stripped silently and `result.json["n_non_gene_features_removed"]` records the count. A `0` value means either the column was absent or there were no non-gene rows to remove.

## Key CLI

```bash
# Demo (synthetic expression + mapping)
python omicsclaw.py run sc-perturb-prep --demo --output /tmp/sc_perturb_prep_demo

# Real run with auto-detected mapping columns + delimiter
python omicsclaw.py run sc-perturb-prep \
  --input cellranger/raw_feature_bc_matrix.h5 \
  --mapping-file guide_assignments.tsv \
  --output results/

# Custom column names + non-default delimiter
python omicsclaw.py run sc-perturb-prep \
  --input expression.h5ad \
  --mapping-file mapping.csv \
  --barcode-column cell_id --sgrna-column guide_id --target-column gene \
  --sep ',' --delimiter '-' --gene-position 1 \
  --output results/

# Keep combinatorial multi-guide cells (high-MOI screens)
python omicsclaw.py run sc-perturb-prep \
  --input expression.h5ad --mapping-file mapping.tsv \
  --keep-multi-guide --output results/
```

## See also

- `references/parameters.md` — every CLI flag, mapping-file conventions
- `references/methodology.md` — assignment status semantics; control-pattern matching
- `references/output_contract.md` — `obs["perturbation"]` / `obs["sgRNA"]` / `obs["target_gene"]` / `obs["assignment_status"]` schema
- Adjacent skills: `sc-count` / `sc-multi-count` (upstream — produces the expression matrix; the mapping comes from cellranger / demuxlet output), `sc-perturb` (downstream — Mixscape classification on the standardised AnnData), `sc-de` (alternative downstream — direct DE between perturbed and control without Mixscape)
