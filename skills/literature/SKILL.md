---
name: literature
description: Load when extracting GEO accessions, dataset metadata, and downloadable references from a scientific paper (PDF / URL / DOI / PubMed ID / raw text) for downstream omics analysis. Skip when the dataset is already in hand or when only routing a query (use `orchestrator`).
version: 0.5.0
author: OmicsClaw
license: MIT
tags:
- literature
- pdf
- doi
- pubmed
- geo
- metadata
requires:
- requests
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

For dispatching a NL query to an analysis skill use `orchestrator`.
For scaffolding a new skill from a paper use `omics-skill-builder`.

## Inputs & Outputs

| Input | Format | Required |
|---|---|---|
| Reference | `--input <URL\|DOI\|PubMed\|PDF path\|text>` | yes (unless `--demo`) |
| Input type | `--input-type {auto,url,doi,pubmed,file,text}` (default `auto`) | no |
| Skip download | `--no-download` (extract metadata only) | no |
| Data dir | `--data-dir <path>` (default `data/`) | no |

| Output | Path | Notes |
|---|---|---|
| Extracted metadata | `output_dir/extracted_metadata.json` | written at `literature_parse.py:80` |
| Report | `output_dir/report.md` | written at `literature_parse.py:193` |
| Result envelope | `output_dir/result.json` | written at `literature_parse.py:147` |
| Downloaded GEO data | `<data-dir>/<GSE...>/...` | only when GEO accessions found AND `--no-download` not set |

## Flow

1. Parse `--input` (or `--demo`); raise `parser.error('the following arguments are required: --input (unless --demo is used)')` at `literature_parse.py:38` when missing.
2. Detect input type (URL / DOI / PubMed / PDF / text) via `--input-type auto` or honour the explicit value.
3. Call `parse_input` (`skills/literature/core/parser.py`); fetch / parse content.
4. Call `extract_metadata` (`skills/literature/core/extractor.py`) → identify GEO accessions, dataset metadata, study type.
5. If GEO accessions found AND not `--no-download`: call `download_geo_dataset` (`skills/literature/core/downloader.py`) → save to `--data-dir`.
6. Write `extracted_metadata.json` (`literature_parse.py:80`) + `report.md` (`:193`) + `result.json` (`:147`).

## Gotchas

- **`--input` REQUIRED unless `--demo` — uses `parser.error` (exit 2).** `literature_parse.py:38` calls `parser.error('the following arguments are required: --input (unless --demo is used)')`. Different from most file-pipeline skills which raise `ValueError`.
- **`--input-type auto` heuristics are positional, not URL-aware.** `core/parser.py:35-55` checks the bare-DOI regex `^10\.\d{4,}/\S+` first; URLs always hit the `startswith("http")` branch and resolve to `url`, even when they wrap a DOI (`https://doi.org/10.1038/...`). For PDF / file paths use `--input-type file` explicitly — `Path.exists()` has to succeed for auto-detection to pick `file`.
- **GEO download requires internet access.** `download_geo_dataset` issues HTTP requests to GEO FTP. Air-gapped runs must pass `--no-download` or the run will hang / time out.
- **PDF parsing requires `pypdf` / similar.** If the PDF parser dependency is missing, the run errors out — verify `skills/literature/requirements.txt` is satisfied.
- **`extracted_metadata.json` is at `output_dir/` ROOT, not `tables/`.** This skill does NOT follow the `tables/<file>.csv` convention used by analysis skills.
- **Empty / unparseable input ⇒ exit 1 (not 2).** `literature_parse.py:64` calls `sys.exit(1)` on internal parse failure (distinct from the `parser.error` exit-2 path for missing args).

## Key CLI

```bash
# Demo (built-in local text)
python omicsclaw.py run literature --demo --output /tmp/lit_demo

# DOI
python omicsclaw.py run literature \
  --input "10.1038/s41586-021-03689-7" --output results/

# PDF (use --input-type file)
python omicsclaw.py run literature \
  --input my_paper.pdf --input-type file --output results/

# URL, metadata-only (no GEO download)
python omicsclaw.py run literature \
  --input "https://www.nature.com/articles/..." \
  --output results/ --no-download
```

## See also

- `references/parameters.md` — every CLI flag, input-type heuristics
- `references/methodology.md` — GEO accession rules, parser fallbacks
- `references/output_contract.md` — `extracted_metadata.json` schema
- Adjacent skills: `orchestrator` (downstream — routes the resulting dataset to an analysis skill), `omics-skill-builder` (parallel — scaffold a new skill from a paper)
