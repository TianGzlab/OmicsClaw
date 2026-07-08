# sc-geo-download — Methodology

## Goal

Fetch public Gene Expression Omnibus (GEO) series datasets from NCBI over HTTPS
into a layout the sibling `sc-geo-import` skill consumes, without introducing
new third-party dependencies (uses only `requests` and `pandas`).

## URL convention

NCBI groups GEO Series by accession prefix. The last three digits of the
accession are replaced with `nnn` to form a bucket directory:

| Accession | Bucket | URL prefix |
|---|---|---|
| GSE109564 | GSE109nnn | `https://ftp.ncbi.nlm.nih.gov/geo/series/GSE109nnn/GSE109564/` |
| GSE12345  | GSE12nnn  | `https://ftp.ncbi.nlm.nih.gov/geo/series/GSE12nnn/GSE12345/` |
| GSE123    | GSEnnn    | `https://ftp.ncbi.nlm.nih.gov/geo/series/GSEnnn/GSE123/` |

Inside that directory, three sub-paths are queried, with a directory-listing
fallback for the matrix and supplementary trees:

1. `soft/<GSE>_family.soft.gz` — per-sample SOFT metadata. Almost always
   present; recorded `status=absent` on 404 rather than failing the run.
2. `matrix/<GSE>_series_matrix.txt.gz` — canonical single-platform series
   matrix. **If 404,** the skill lists `matrix/` and downloads every
   `<GSE>-GPL<id>_series_matrix.txt.gz` file. Multi-platform studies such as
   GSE109564 only publish per-platform matrices and have no canonical name.
3. `suppl/<GSE>_RAW.tar` — canonical per-sample raw bundle (10x triplets,
   processed `.h5`, etc.). **If 404,** the skill lists `suppl/` and downloads
   every `<GSE>_*` file (e.g. DGE `.txt.gz`, per-sample `.h5`). If `suppl/`
   yields nothing usable, the manifest records `status=absent` for `raw_tar`
   and the run still succeeds.

Directory listings are obtained by parsing NCBI's Apache autoindex HTML
(`href="…"` link extraction). The listing call is only made on 404, so the
common single-platform case still does a single GET per artifact.

## PubMed → GEO resolution

When `--pubmed-id` is supplied, the skill performs two Entrez E-utilities
calls against `eutils.ncbi.nlm.nih.gov`:

1. `elink.fcgi?dbfrom=pubmed&db=gds&id=<pmid>` returns linked GEO Data Set
   UIDs.
2. `esummary.fcgi?db=gds&id=<uids>` resolves each UID to a `GSE` accession.

PubMed itself does not host data — this is purely a metadata lookup.

## Download semantics

- **Streaming**: 1 MB chunks via `requests.get(stream=True)`.
- **Atomic**: each file is written to `<dest>.part` and renamed only on
  complete success.
- **Idempotent**: when the final path already exists with size > 0, the skill
  records a `status=cached` row in the manifest and does not re-fetch. SHA-256
  is recomputed every run so the manifest always reflects the current bytes.
- **Optional metadata**: Entrez ESearch + ESummary fetch lightweight metadata
  (title, organism, platform, num_samples, linked PubMed IDs, publication
  date). Disable with `--no-metadata`.

## Raw archive extraction

When the supplementary `_RAW.tar` is present and `--extract-tar` is enabled
(default), the archive is unpacked using stdlib `tarfile` into
`<accession>/samples/<GSM>/` based on the GSM prefix of each member filename.
Files without a GSM prefix land in `samples/_misc/`. This is the layout
`sc-geo-import` already expects to discover per-sample files.

## Failure modes & error contract

| Condition | Behavior |
|---|---|
| Invalid accession (not `GSE\d+`) | `ValueError` with a clear message before any network call. |
| HTTP 404 on SOFT or series matrix | `requests.HTTPError` propagated; the skill exits non-zero with the failing URL. |
| HTTP 404 on `_RAW.tar` | Treated as "absent"; manifest records `status=absent`, run continues. |
| Network error (timeout, DNS, ...) | `requests.RequestException` propagated; the skill exits non-zero with the failing accession. |
| PubMed ID resolves to zero Series | `SystemExit` with a clear message; no partial state. |

## Outputs

See `references/output_contract.md` for the exact file layout, manifest CSV
schema, and metadata JSON shape.

## Why no GEOparse

`GEOparse` would be a single-line replacement for the download + SOFT parse,
but it pulls in additional dependencies (`xlrd`, `tqdm`, etc.) and changes the
implicit download destination semantics. Since `sc-geo-import` already parses
SOFT files locally, the skill stays zero-new-dependency and uses HTTPS
directly.
