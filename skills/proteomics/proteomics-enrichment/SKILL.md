---
name: proteomics-enrichment
description: Load when running over-representation analysis (ORA) on a list of proteins via Fisher's exact test against a built-in 8-pathway DEMO dictionary, with BH-FDR correction. Skip when needing a real pathway database (this skill is demo-only — use `bulkrna-enrichment` for real KEGG / Reactome / MSigDB) or for rank-based GSEA.
version: 0.5.0
author: OmicsClaw
license: MIT
tags:
- proteomics
- enrichment
- ora
- fisher
- demo
- pathway
requires:
- pandas
- numpy
- scipy
---

# proteomics-enrichment

## When to use

The user has a CSV listing proteins of interest (e.g. the
significant subset from `proteomics-de`, or the PTM-target list
from `proteomics-ptm`) and wants over-representation enrichment
via Fisher's exact test, with BH-adjusted FDR.

**This is a demo-only enrichment.** The pathway database is the
hard-coded 8-pathway `DEMO_PATHWAYS` dict at
`prot_enrichment.py:40-49` (each pathway has 5 fixed members).
There is NO CLI flag to load a real KEGG / Reactome / MSigDB
library. For production proteomics enrichment, export your
significant-protein list and call `bulkrna-enrichment` (which has
real ORA + GSEA + ssGSEA backends with hosted libraries).

## Inputs & Outputs

| Input | Format | Required |
|---|---|---|
| Protein list | `.csv` with `protein_id` column (or any first column treated as gene IDs) | yes (unless `--demo`) |
| Method | `--method ora` (only choice) | no |
| Species | `--species <name>` (default `human`, RECORDED ONLY — does not switch DBs) | no |
| Background size | `--background-size <int>` (default = `max(union(input, pathway-genes), |input|+1)` ≈ 40 + n_input for the demo) | no |

| Output | Path | Notes |
|---|---|---|
| Enrichment results | `tables/enrichment_results.csv` | per-pathway `pvalue`, `fdr` (BH-adjusted), gene counts |
| Report | `report.md` + `result.json` | `summary["n_significant"]` (FDR < 0.05); `summary["n_pathways_tested"]` = 8 |

## Flow

1. Load CSV (`--input <proteins.csv>`) or generate a demo (`--demo`).
2. Pick the gene-list column: `protein_id` if present, otherwise the first column (`prot_enrichment.py:256`).
3. For each pathway in `DEMO_PATHWAYS` (`prot_enrichment.py:40-49`), run Fisher's exact test (`prot_enrichment.py:138-150`); apply BH FDR adjustment (`prot_enrichment.py:167`).
4. Write `tables/enrichment_results.csv` (`prot_enrichment.py:267`) + `report.md` + `result.json` (`:277`).

## Gotchas

- **Pathway database is HARD-CODED 8 demo pathways.** `prot_enrichment.py:40-49` defines 8 pathways × 5 genes each (e.g. cell-cycle, apoptosis, TCA-cycle). There is no CLI for loading real databases. The `n_pathways_tested = 8` in `result.json` (`:271`) is a constant, not a function of input. For real enrichment, route to `bulkrna-enrichment`.
- **Method is Fisher's exact, not hypergeometric.** Mathematically equivalent for over-representation, but the script and report (`prot_enrichment.py:4, 138-150`) consistently say "Fisher's". Hypergeometric is the same distribution but the "Fisher's exact test" naming is what shows in the report.
- **Default background ≠ a real proteome size.** `prot_enrichment.py:126-128` sets `background_size = max(len(gene_set | all_pathway_genes), len(gene_set) + 1)` — for the demo's 8 pathways that's ~40 + n_input. **Always pass `--background-size N` (e.g. 20000 for human, 8000 for your detected proteome) for real enrichment** — the auto-default produces meaningless p-values on a real dataset.
- **`--species` is RECORDED-ONLY.** `prot_enrichment.py:237-241` accepts `--species` but the value is never used to switch databases or filter pathways — it's logged into `result.json` for reproducibility only.
- **Gene-list column auto-detection: `protein_id` first, else first column.** `prot_enrichment.py:256` uses `gene_col = "protein_id" if "protein_id" in df.columns else df.columns[0]`. If your CSV has multiple ID columns (`gene`, `uniprot`, `symbol`), only `protein_id` is preferred — pre-rename the column you want enriched.
- **`--input` REQUIRED unless `--demo`.** `prot_enrichment.py:251` raises `ValueError("--input required when not using --demo")`.

## Key CLI

```bash
# Demo (8-pathway DEMO_PATHWAYS dict)
python omicsclaw.py run proteomics-enrichment --demo --output /tmp/enr_demo

# Real protein list — pass real background size!
python omicsclaw.py run proteomics-enrichment \
  --input significant.csv --output results/ \
  --background-size 20000

# For real pathway databases, use bulkrna-enrichment instead:
# python omicsclaw.py run bulkrna-enrichment --input significant.csv ...
```

## See also

- `references/parameters.md` — every CLI flag
- `references/methodology.md` — Fisher's exact ORA, BH FDR, demo-DB caveats
- `references/output_contract.md` — `tables/enrichment_results.csv` schema
- Adjacent skills: `proteomics-de` (upstream — produces significant protein lists), `proteomics-ptm` (upstream — PTM-target lists), `proteomics-quantification` (upstream — protein-level abundance), `bulkrna-enrichment` (parallel — REAL pathway databases + GSEA + ssGSEA)
