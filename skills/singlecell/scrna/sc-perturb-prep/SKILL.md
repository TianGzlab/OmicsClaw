---
name: sc-perturb-prep
description: Load when attaching cell-barcode → sgRNA assignments from a mapping TSV/CSV onto a Perturb-seq
  expression AnnData, producing standardised perturbation / sgRNA / target-gene obs columns. Skip when
  the AnnData already has perturbation labels (use sc-perturb); raw guide-calling from FASTQ (use upstream
  demuxlet / cellranger guide pipelines).
tags:
- singlecell
- scrna
- perturb-prep
- perturb-seq
- crispr
- sgrna-assignment
---

# sc-perturb-prep

Attach an upstream barcode-to-guide table to expression data. This is the
`mapping_tsv` method, not a FASTQ guide caller. It needs no pertpy installation.

## Key CLI

```bash
python skills/singlecell/scrna/sc-perturb-prep/sc_perturb_prep.py --demo --output /tmp/sc_perturb_prep_demo
python skills/singlecell/scrna/sc-perturb-prep/sc_perturb_prep.py --input expression.h5ad --mapping-file mapping.tsv --output results/prep
```

Mapping columns are inferred from common names, or selected with
`--barcode-column`, `--sgrna-column`, and `--target-column`. Without target
values, `--delimiter _ --gene-position 0` extracts the target from a guide ID.
Pass `--keep-multi-guide` only when retaining multi-guide cells is intended.

## Workflow

Upstream: expression counts and guide calls from the same cells. Standardize
mapping columns, collapse guides per barcode, match assigned cells, retain
gene-expression features and canonicalize the matrix. Downstream: use
`sc-perturb` for observed perturbation signatures, or `sc-preprocessing` for
clustering. The API returns objects; the example step writes them explicitly.

## Matrix Contract

Raw counts are preferred; canonicalization can recover counts from a layer or
raw snapshot. Inspect `omicsclaw_matrix_contract` and `run_info` for the actual
expression source. A normalized matrix is not evidence of raw counts.

## Inputs & Outputs

Input: `.h5ad`, 10x H5 or a matrix directory, plus mapping TSV/CSV for real runs.
The CLI writes `processed.h5ad`, `report.md`, `result.json`,
`reproducibility/commands.sh`, `tables/perturbation_assignments.csv`,
`tables/assignment_status_counts.csv`, `tables/perturbation_counts.csv`,
`tables/feature_type_summary.csv` and `figures/perturbation_counts.png`.
`tables/dropped_multi_guide_cells.csv` is written only when rows were dropped.
Plot data are also written under `figure_data/`.

## Gotchas

- `tables/perturbation_assignments.csv` uses status `assigned`, `control` or retained `multi_guide`; dropped rows do not appear in the output AnnData.
- Control tokens match whole words separated by punctuation: `NT_sg1` is a control, while `WNT3_sg1`, `NTRK1_sg1` and `NT5E_sg1` are not. Review `tables/perturbation_assignments.csv` after choosing custom patterns.
- `result.json` → `summary.n_cells_multi_guide_dropped` counts dropped multi-guide cells. No matching barcodes raises `ValueError` in the API.
- `tables/feature_type_summary.csv` describes the input feature types. Filtering needs `var['feature_types']`; absent labels cannot identify guide or antibody features.

## API

<!-- api:begin generated from _api.py; regenerate with run.py api <skill dir> --write -->

### `standardize_mapping(table, *, barcode_column=None, sgrna_column=None, target_column=None)`

Return barcode, sgRNA and target_gene columns from a pandas table.

Column names may be supplied explicitly. Missing target genes are inferred
later from guide names; duplicate rows and empty barcode/guide rows are removed.

### `collapse_assignments(mapping, *, delimiter='_', gene_position=0, control_patterns=('NT', 'NTC', 'NON-TARGET', 'NON_TARGET', 'NEGATIVE_CONTROL', 'NEG_CTRL'), control_label='NT', drop_multi_guide=True)`

Return (assigned, dropped) tables with one row per barcode.

Controls match whole tokens, not substrings of gene names. Multiple guides
are dropped by default; retained multi-guide cells keep their status.

### `attach_assignments(adata, assignments, *, pert_key='perturbation', sgrna_key='sgRNA', target_key='target_gene', species='human')`

Return a gene-expression AnnData with assignments on matching cells.

The input is unchanged. Gene features and the expression matrix are
canonicalized using the single-cell input contract; no pertpy is needed.

### `run_info(adata, *, keep: bool=True)`

Return preparation provenance; keep=False removes the run record.

### `assignment_summary(adata)`

Return assignment_status and n_cells columns for the retained cells.

### `perturbation_counts(adata, *, pert_key='perturbation')`

Return perturbation and n_cells columns, ordered by decreasing cell count.

### `perturbation_counts_figure(adata, *, pert_key='perturbation', n_top=20)`

Return a Figure of cell counts for up to n_top perturbations; save it separately.

<!-- api:end -->

## Dependencies

`anndata`, `matplotlib`, `numpy`, `pandas`, `scanpy`, `scipy`
