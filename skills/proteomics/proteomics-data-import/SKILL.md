---
name: proteomics-data-import
description: Load when ingesting a MaxQuant `proteinGroups.txt`, FragPipe `combined_protein.tsv`, DIA-NN
  report, or generic CSV / TSV protein-quantification table — normalises columns to a standard schema,
  emits `tables/proteins.csv`. Skip when raw spectra are the input (run the search engine first); the
  file is already OmicsClaw schema.
trigger: data import, convert proteomics, format conversion
tags:
- proteomics
- import
- maxquant
- fragpipe
- diann
- spectronaut
---

# proteomics-data-import

## When to use

The user has a search-engine output (MaxQuant `proteinGroups.txt`,
FragPipe `combined_protein.tsv`, DIA-NN main report, or a generic
CSV / TSV protein table) and wants it normalised into OmicsClaw's
standard schema (lowercase `protein_id` plus `LFQ_<sample>` /
`Int_<sample>` intensity columns derived from MaxQuant's
`LFQ intensity ...` / `Intensity ...` headers).
Pick the format with `--format {maxquant,fragpipe,diann,generic}`
(default `maxquant`).

For raw MS spectra (mzML / RAW), run a search engine first
(MaxQuant / FragPipe / DIA-NN) and feed THIS skill the resulting
table.

## Inputs & Outputs

**Inputs**

- File types: `.txt`, `.tsv`, `.csv`

**Outputs**

- `tables/proteins.csv`
- `report.md`
- `result.json`

## Flow

1. Load input (`--input <file>`) or generate a demo MaxQuant-shaped file (`--demo`).
2. Dispatch to the format-specific importer (`proteomics_data_import.py` `_dispatch_import`); supported keys are `maxquant`, `fragpipe`, `diann`, `generic`.
3. Rename columns: `LFQ intensity <sample>` → `LFQ_<sample>` and `Intensity <sample>` → `Int_<sample>` (`proteomics_data_import.py`); `Majority protein IDs` → `protein_id`; `Gene names` → `gene_name`; etc.
4. Write `tables/proteins.csv` (`proteomics_data_import.py`) + `report.md` + `result.json`.

## Gotchas

- **`--format` value must match `_dispatch_import` keys exactly.** `proteomics_data_import.py` registers `maxquant`, `fragpipe`, `diann`, `generic`. An unknown value raises `ValueError("Unsupported format: ... Supported: ['maxquant', 'fragpipe', 'diann', 'generic']")`. There is no `spectronaut` importer — use `--format generic` for Spectronaut and rename columns yourself.
- **`--input` REQUIRED unless `--demo`.** `proteomics_data_import.py` raises `ValueError("--input required when not using --demo")`. Non-existent paths raise `FileNotFoundError` from `pd.read_csv`.
- **Output schema is LOWERCASE.** Column renaming targets `protein_id`, `intensity_<sample>`, `gene_name` etc. Downstream skills (`proteomics-quantification`, `proteomics-de`) assume this casing. Verify after import with `head tables/proteins.csv`.
- **No deduplication of contaminants / decoys.** Contaminant (`CON_*`) and decoy (`REV_*`) rows are passed through unchanged. Filter them upstream with the search engine's `--keep-contaminants false` flag, or add a downstream `df = df[~df["protein_id"].str.startswith(("CON_", "REV_"))]` step.

## Key CLI

```bash
# Demo (synthetic MaxQuant-style)
python skills/proteomics/proteomics-data-import/proteomics_data_import.py --demo --output /tmp/import_demo

# Real MaxQuant output
python skills/proteomics/proteomics-data-import/proteomics_data_import.py \
  --input proteinGroups.txt --output results/ --format maxquant

# FragPipe combined_protein
python skills/proteomics/proteomics-data-import/proteomics_data_import.py \
  --input combined_protein.tsv --output results/ --format fragpipe

# DIA-NN main report
python skills/proteomics/proteomics-data-import/proteomics_data_import.py \
  --input report.tsv --output results/ --format diann

# Generic / Spectronaut (rename columns yourself first)
python skills/proteomics/proteomics-data-import/proteomics_data_import.py \
  --input my_table.csv --output results/ --format generic
```

## See also

- `references/parameters.md` — every CLI flag
- `references/methodology.md` — per-format column-mapping rules
- `references/output_contract.md` — `tables/proteins.csv` schema
- Adjacent skills: `proteomics-ms-qc` (downstream — QC the imported table), `proteomics-quantification` (downstream — compute LFQ / iBAQ / spectral count), `proteomics-identification` (parallel — peptide-level summary), `proteomics-de` (downstream — differential abundance after import)

## Dependencies

Python packages this skill's script needs. They are not installed for you — check before a long run.

`numpy`, `pandas`
