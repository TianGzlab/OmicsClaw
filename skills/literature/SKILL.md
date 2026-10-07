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

Extract GEO accessions and heuristic study metadata from paper text. Read local papers explicitly with read_document or fetch remote papers with fetch_text. Skip when the dataset is already in hand.

## Use from a step

```python
import pandas as pd
from skills._sdk.notebook import load_skill, read_input, write_output
library = load_skill('literature')
text = read_input('paper.txt', reader=library.read_document)
result = library.extract(text)
write_output(result, 'tables/result.csv')
```

[examples/example_step.py](examples/example_step.py) runs offline and supports
fresh-kernel replay. Pure computations return objects; CLI and steps own writes.

## API

<!-- api:begin generated from _api.py; regenerate with run.py api <skill dir> --write -->

### `extract(data)`

Extract GEO accessions and heuristic study metadata from text.

:param data: Local paper text; URLs and paths are treated as text, never fetched.
:returns: A DataFrame of kind/accession pairs, with metadata in attrs['run_info'].
:raises ValueError: data is empty or not a string.

### `methodology(data)`

Extract stated numeric method parameters with exact source spans.

:param data: Paper text containing supported parameter names and numeric values.
:returns: A DataFrame with param, operator, value, quote, start and end columns.
:raises TypeError: data is not text.

### `read_document(data)`

Read a local PDF or UTF-8 text file; use as reader= in read_input.

:param data: Local Path or path string; no network requests are made.
:returns: Extracted text with empty PDF pages omitted.
:raises ImportError: Install pypdf with install_skill_deps for PDFs.
:raises OSError: The file cannot be read.

### `fetch_text(data, *, input_type='url')`

Fetch article text explicitly from a URL, DOI or PubMed reference.

:param data: Reference sent to the remote service; results may change between requests.
:param input_type: Default url; doi and pubmed resolve their respective endpoints.
:returns: HTML/XML with tags removed and whitespace collapsed, as in the CLI.
:raises ImportError: Install requests with install_skill_deps if unavailable.
:raises ValueError: The reference type or URL scheme is unsupported.
:raises Exception: HTTP and network errors propagate instead of becoming article text.

### `run_info(data, *, keep=True)`

Read heuristic metadata and the accession lists extracted from text.

:param data: Accession table returned by extract.
:param keep: Default True; use False to remove metadata from the table.
:returns: An independent metadata dictionary.
:raises KeyError: The table has no extraction diagnostics.

### `accession_figure(data)`

Plot accession counts by GEO accession kind.

:param data: Accession table returned by extract.
:returns: A matplotlib Figure, including zero counts for missing kinds.
:raises KeyError: kind is absent.

<!-- api:end -->

## Methods and parameters

extract performs local regex/keyword extraction only. methodology returns exact quotes and character spans for stated numeric parameters. read_document reads UTF-8 text or PDF, and fetch_text explicitly requests URL/DOI/PubMed text. Neither function downloads datasets; the CLI retains its optional GEO download workflow.

## Gotchas

- `extract` returns uppercase, deduplicated and sorted GEO identifiers. `methodology` never fills absent parameter defaults. `read_document` raises when pypdf is missing or input cannot be read. `fetch_text` propagates failures rather than treating an error message as paper text. Metadata labels remain heuristics, not validated study annotations.

## Inputs and outputs

`extracted_metadata.json`, `source.txt`, `report.md` and `result.json` at the output root. The CLI creates data/ and optionally downloads into per-GSE directories; --data-dir chooses another destination. The original source.txt write remains best-effort. The function library writes no files.

## CLI

```bash
python skills/literature/literature_parse.py --demo --output /tmp/literature
```

## See also

- [Parameters](references/parameters.md)
- [Methodology](references/methodology.md)
- [Output contract](references/output_contract.md)

## Dependencies

`pandas`, `matplotlib`, `pypdf`, `requests`
