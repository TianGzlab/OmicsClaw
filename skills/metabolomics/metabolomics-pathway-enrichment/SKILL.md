---
name: metabolomics-pathway-enrichment
description: Load when running over-representation analysis (ORA) on a metabolite list via Fisher's exact test against a built-in 9-pathway DEMO dictionary, BH-FDR adjusted. Skip when needing real KEGG / Reactome (this skill is demo-only) or `mummichog` / `fella` topology methods (CLI accepts them but only ORA runs).
version: 0.5.0
author: OmicsClaw
license: MIT
tags:
- metabolomics
- pathway
- enrichment
- ora
- fisher
- demo
requires:
- pandas
- numpy
- scipy
---

# metabolomics-pathway-enrichment

## When to use

The user has a CSV listing metabolites of interest (e.g.
significant features from `metabolomics-de` or `metabolomics-statistics`,
joined with their HMDB / KEGG names) and wants over-representation
enrichment via Fisher's exact test, with BH-adjusted FDR.

**This is a demo-only enrichment.** The pathway database is the
hard-coded 9-pathway `DEMO_METABOLIC_PATHWAYS` dict at
`met_pathway.py:45-104` (e.g. glycolysis, TCA cycle, amino-acid
metabolism). There is NO CLI flag to load real KEGG / Reactome /
SMPDB. For production metabolomics enrichment, route to
external tools (MetaboAnalystR, mummichog, FELLA) or send the
metabolite list through `bulkrna-enrichment` after gene-mapping.

## Inputs & Outputs

| Input | Format | Required |
|---|---|---|
| Metabolite list | `.csv` with `metabolite` column (or any first column treated as metabolite names) | yes (unless `--demo`) |
| Method | `--method {ora,mummichog,fella}` (only `ora` is actually implemented) | no |

| Output | Path | Notes |
|---|---|---|
| Pathway enrichment | `tables/pathway_enrichment.csv` | per-pathway `pvalue`, `fdr` (BH-adjusted), overlap counts |
| Report | `report.md` + `result.json` | `summary["n_significant"]` (FDR < 0.05); `summary["n_pathways_tested"]` = 9 |

## Flow

1. Load CSV (`--input <metabolites.csv>`) or generate a demo at `output_dir/<demo>.csv` (`met_pathway.py:300`).
2. Pick the metabolite-list column: `metabolite` if present, otherwise the first column (`met_pathway.py:307`).
3. For each pathway in `DEMO_METABOLIC_PATHWAYS` (`met_pathway.py:45`), run Fisher's exact test (hypergeometric) (`met_pathway.py:132-200`); apply BH FDR adjustment (`:198`).
4. Write `tables/pathway_enrichment.csv` (`met_pathway.py:314`) + `report.md` + `result.json`.

## Gotchas

- **Pathway database is HARD-CODED 9 demo pathways.** `met_pathway.py:45-104` defines `DEMO_METABOLIC_PATHWAYS` (e.g. glycolysis, TCA cycle, urea cycle). The `n_pathways_tested = 9` in `result.json` (`:320`) is constant. For real enrichment, use MetaboAnalystR / mummichog / FELLA externally.
- **`--method mummichog` and `--method fella` are RECORDED-ONLY.** `met_pathway.py:293` accepts `choices=["ora", "mummichog", "fella"]` but `pathway_enrichment` (`:132-200`) ignores the `method` parameter — only ORA (Fisher's exact + BH FDR) is implemented. Calling with `--method mummichog` produces ORA results plus a misleading `method=mummichog` label in `result.json`.
- **Metabolite-name matching is CASE-INSENSITIVE substring.** `met_pathway.py:165` lower-cases both query and pathway-member names. `glucose`, `Glucose`, `D-Glucose` all match a pathway entry `D-Glucose` — but `Hexose` will NOT.
- **Column auto-detection: `metabolite` first, else first column.** `met_pathway.py:307` uses `met_col = "metabolite" if "metabolite" in df.columns else df.columns[0]`. Pre-rename if your CSV has multiple ID columns (`name`, `hmdb_id`, `kegg`).
- **`--input` REQUIRED unless `--demo`.** `met_pathway.py:303` raises `ValueError("--input required when not using --demo")`.

## Key CLI

```bash
# Demo (9-pathway DEMO_METABOLIC_PATHWAYS)
python omicsclaw.py run metabolomics-pathway-enrichment --demo --output /tmp/path_demo

# Real metabolite list (CSV with `metabolite` column)
python omicsclaw.py run metabolomics-pathway-enrichment \
  --input significant_metabolites.csv --output results/

# `--method mummichog` is accepted but produces ORA results regardless
python omicsclaw.py run metabolomics-pathway-enrichment \
  --input significant_metabolites.csv --output results/ \
  --method mummichog
```

## See also

- `references/parameters.md` — every CLI flag
- `references/methodology.md` — Fisher's exact ORA, BH FDR, demo-DB caveats
- `references/output_contract.md` — `tables/pathway_enrichment.csv` schema
- Adjacent skills: `metabolomics-de` (upstream — significant feature list), `metabolomics-statistics` (upstream — multi-test backends), `metabolomics-annotation` (upstream — m/z → metabolite name mapping), `proteomics-enrichment` (parallel — same demo-only ORA pattern but for proteins)
