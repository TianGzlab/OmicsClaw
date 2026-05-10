---
name: bulkrna-coexpression
description: Load when discovering gene co-expression modules and hub genes in a bulk RNA-seq cohort via WGCNA-style soft-thresholded networks. Skip for direct DE comparison (use bulkrna-de) or PPI lookup of an existing gene list (use bulkrna-ppi-network); single-cell co-expression uses sc-grn instead.
version: 0.3.0
author: OmicsClaw
license: MIT
tags:
- bulkrna
- coexpression
- WGCNA
- network
- modules
- hub-genes
---

# bulkrna-coexpression

## When to use

Run on a bulk RNA-seq cohort (≥15 samples recommended; works on smaller
sets but module structure is unstable below that) when you want to find
groups of co-regulated genes ("modules") and the hub genes within each.
Soft-thresholded correlation network in the WGCNA style; outputs module
assignments, hub genes, and module-trait correlations.

## Inputs & Outputs

| Input | Format | Required |
|---|---|---|
| Count matrix | `.csv` (gene × sample) | yes (or `--demo`) |
| Sample traits | `--traits` CSV | optional, for module-trait correlation |

| Output | Path | Notes |
|---|---|---|
| Module assignments | `tables/module_assignments.csv` | gene → module colour |
| Hub genes | `tables/hub_genes.csv` | per-module top-connectivity genes |
| Soft-threshold diagnostic | `figures/soft_threshold.png` | scale-free fit by power |
| Module dendrogram | `figures/module_dendrogram.png` | gene clustering tree |
| Report | `report.md` + `result.json` | always |

## Flow

1. Load count matrix; check sample count + non-zero gene fraction (`bulkrna_coexpression.py:54` raises `FileNotFoundError` on missing input; `:721, :724` raise on missing/invalid `--input`).
2. Choose soft-thresholding power (`:377` raises `ValueError` if no power achieves scale-free topology).
3. Build adjacency matrix; cluster modules.
4. Compute hub genes (top intramodular connectivity per module).
5. If `--traits` provided, correlate eigengenes vs traits.
6. Render diagnostics; write tables + report.

## Gotchas

- **Soft-thresholding can fail silently with too-few-samples.**  `:382` warns when no candidate power achieves scale-free topology R² > 0.8; the run continues with the highest-R² candidate.  Below ~15 samples, modules become noise — check `result.json["soft_threshold_R2"]` and treat results as exploratory if R² < 0.6.
- **No biological-replicate filter.**  Unlike PyDESeq2, this skill makes no distinction between technical and biological replicates.  Modules built on a cohort with hidden batch structure will reflect the batch, not biology — run `bulkrna-batch-correction` upstream if PCA shows batch separation.
- **Gene IDs must match between counts and traits.**  No automatic mapping — feed counts and traits with consistent identifier system, or run `bulkrna-geneid-mapping` first.
- **Hub genes are connectivity-based, not necessarily biology-load-bearing.**  A hub in WGCNA means "highest intramodular correlation" — useful as a starting hypothesis but not proof of regulatory primacy.  Validate with knockdown / knockout data or eQTL evidence.

## Key CLI

```bash
python omicsclaw.py run bulkrna-coexpression --demo
python omicsclaw.py run bulkrna-coexpression \
  --input counts.csv --output results/
python omicsclaw.py run bulkrna-coexpression \
  --input counts.csv --traits clinical.csv --output results/
```

## See also

- `references/parameters.md` — every CLI flag and tuning hint
- `references/methodology.md` — soft-thresholding, module detection, hub-gene definition
- `references/output_contract.md` — exact output directory layout
- Adjacent skills: `bulkrna-batch-correction` (run upstream if batches suspected), `bulkrna-de` (parallel: differential expression), `bulkrna-ppi-network` (parallel: STRING PPI on a gene list), `sc-grn` (single-cell sibling using GRNBoost2 / pySCENIC)
