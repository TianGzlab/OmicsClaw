---
name: literature
description: Load when extracting GEO accessions, dataset metadata, and downloadable references from a
  scientific paper (PDF / URL / DOI / PubMed ID / raw text) for downstream omics analysis. Skip when the
  dataset is already in hand; the paper names no dataset to fetch.
trigger: parse paper, literature, GEO accession, download dataset, PDF extract, PubMed, DOI
tags:
- literature
- pdf
- doi
- pubmed
- geo
- metadata
---

# literature

## When to use

The user provides a scientific paper reference (PDF path, URL,
DOI, PubMed ID, or raw text excerpt) and wants OmicsClaw to
extract GEO accessions, dataset metadata, and (optionally)
download referenced GEO datasets — so a downstream analysis skill
can be invoked on real data.

`--input-type` defaults to `auto` (sniffs from input shape).
`--no-download` skips the GEO download step (metadata only).

## Inputs & Outputs

**Inputs**

- Input kinds: `file`, `freeform`
- File types: `.pdf`

**Outputs**

- `extracted_metadata.json`
- `report.md`
- `result.json`
- `<--data-dir>/<GSEid>/...`
- Produces artifact `literature.dataset_handoff` as `extracted_metadata.json` (`json`)

## Flow

1. Parse `--input` (or `--demo`); raise `parser.error('the following arguments are required: --input (unless --demo is used)')` at `literature_parse.py` when missing.
2. Detect input type (URL / DOI / PubMed / PDF / text) via `--input-type auto` or honour the explicit value.
3. Call `parse_input` (`skills/literature/core/parser.py`); fetch / parse content.
4. Call `extract_metadata` (`skills/literature/core/extractor.py`) → identify GEO accessions, dataset metadata, study type.
5. If GEO accessions found AND not `--no-download`: call `download_geo_dataset` (`skills/literature/core/downloader.py`) → save to `--data-dir`.
6. Write `extracted_metadata.json` (`literature_parse.py`) + `report.md` + `result.json`.

## Gotchas

- **`--input` REQUIRED unless `--demo` — uses `parser.error` (exit 2).** `literature_parse.py` calls `parser.error('the following arguments are required: --input (unless --demo is used)')`. Different from most file-pipeline skills which raise `ValueError`.
- **`--input-type auto` heuristics are positional, not URL-aware.** `core/parser.py` checks the bare-DOI regex `^10\.\d{4,}/\S+` first; URLs always hit the `startswith("http")` branch and resolve to `url`, even when they wrap a DOI (`https://doi.org/10.1038/...`). For PDF / file paths use `--input-type file` explicitly — `Path.exists()` has to succeed for auto-detection to pick `file`.
- **GEO download requires internet access.** `download_geo_dataset` issues HTTP requests to GEO FTP. Air-gapped runs must pass `--no-download` or the run will hang / time out.
- **Without `pypdf`, a PDF input does not fail.** `parse_file` in `core/parser.py` returns the text "Error: pypdf not installed…" in place of the paper, so the run finishes with no accessions. Check for that string before concluding a PDF names no dataset.
- **`extracted_metadata.json` is at `output_dir/` ROOT, not `tables/`.** This skill does NOT follow the `tables/<file>.csv` convention used by analysis skills.
- **Empty / unparseable input ⇒ exit 1 (not 2).** `literature_parse.py` calls `sys.exit(1)` on internal parse failure (distinct from the `parser.error` exit-2 path for missing args).

## Key CLI

```bash
# Demo (built-in local text)
python skills/literature/literature_parse.py --demo --output /tmp/lit_demo

# DOI
python skills/literature/literature_parse.py \
  --input "10.1038/s41586-021-03689-7" --output results/

# PDF (use --input-type file)
python skills/literature/literature_parse.py \
  --input my_paper.pdf --input-type file --output results/

# URL, metadata-only (no GEO download)
python skills/literature/literature_parse.py \
  --input "https://www.nature.com/articles/..." \
  --output results/ --no-download
```

## See also

- `references/parameters.md` — every CLI flag, input-type heuristics
- `references/methodology.md` — GEO accession rules, parser fallbacks
- `references/output_contract.md` — `extracted_metadata.json` schema
- Adjacent skills: the downloaded dataset goes to the foundation skill for its data type (for example `spatial-preprocess`, `sc-preprocessing`, `bulkrna-qc`)

## Dependencies

Python packages this skill's script needs. They are not installed for you — check before a long run.

`pypdf`, `requests`
