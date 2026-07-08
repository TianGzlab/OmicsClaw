---
name: sc-geo-download
description: Load when fetching public Gene Expression Omnibus (GEO) series datasets (GSE accessions) over HTTPS from NCBI — downloads the SOFT family file, series matrix, and supplementary `_RAW.tar` bundles into a layout that `sc-geo-import` consumes for AnnData reconstruction. Skip when the files are already on disk (use `sc-geo-import` directly), when you need raw FASTQ from SRA (not supported in this skill), or when working with non-GEO sources.
version: 0.1.0
author: OmicsClaw
license: MIT
tags:
- singlecell
- scrna
- geo
- ncbi
- download
- ingest
- entrez
requires:
- python3
- requests
- pandas
---

# sc-geo-download

Download public GEO datasets over HTTPS from NCBI. Composes with `sc-geo-import`
for the full ingest path:

```bash
oc run sc-geo-download --accession GSE109564 --output /data
oc run sc-geo-import   --input /data/geo/GSE109564 --output /data/imported
```

## What it does

For each GSE accession, the skill fetches up to three files from
`https://ftp.ncbi.nlm.nih.gov/geo/series/<bucket>/<GSE>/`:

| File | Source | Purpose |
|---|---|---|
| `<GSE>_family.soft.gz` | `soft/` | Per-sample SOFT metadata (consumed by `sc-geo-import`) |
| `<GSE>_series_matrix.txt.gz` | `matrix/` | Series-level expression matrix + sample annotations |
| `<GSE>_RAW.tar` | `suppl/` | Per-sample raw bundles (10x triplets, etc.) — optional |

When the `_RAW.tar` is present and `--extract-tar` is enabled (default), the
archive is unpacked under `<accession>/samples/<GSM>/` so `sc-geo-import` can
discover the per-sample files directly.

## PubMed → GEO

Pass `--pubmed-id <PMID>` to resolve linked GEO Series via the NCBI Entrez
E-utilities. Each linked Series is added to the download set. (PubMed itself
does not host data; this is just an accession lookup.)

## Idempotent re-runs

Downloads are atomic (`.part` rename) and idempotent: if the destination file
already exists with size > 0, the skill records a `cached` entry in the manifest
and does not re-fetch. SHA-256 is recomputed every run for the manifest.

## Demo mode

`--demo` synthesizes a tiny GEO-like bundle (`GSE_DEMO_OC` with two GSMs)
directly on disk. No network. Useful for tests, dry runs, and verifying the
output layout.

## Outputs

```
<output>/
├── geo/
│   └── <GSE>/
│       ├── <GSE>_family.soft.gz
│       ├── <GSE>_series_matrix.txt.gz
│       ├── <GSE>_RAW.tar             (when available)
│       └── samples/<GSM>/...         (when --extract-tar)
├── manifest.csv         # accession, kind, status, bytes, sha256, path, url
├── metadata.json        # per-accession Entrez metadata (title/organism/samples/...)
├── report.md            # human-readable summary with next-step commands
├── result.json          # standard OmicsClaw result envelope
└── reproducibility/
    └── commands.sh      # exact CLI invocation used
```

## How to invoke this skill from the agent / orchestrator

`sc-geo-download` is a **fetch-style** skill — its input is a GEO accession,
not a file. Its `parameters.yaml` declares `input_required: false`, so CLI and
agent surfaces can run it with only `--accession` / `--pubmed-id` plus
`--output`:

```python
omicsclaw(
    skill="sc-geo-download",
    extra_args=["--accession", "GSE109564"],
)
```

The script still accepts an injected `--input` and ignores it for backwards
compatibility with older runner calls. `mode="demo"` triggers the
**synthetic** bundle (not a real download). Do not use `mode="demo"` when you
actually want to fetch an accession. `--output` in `extra_args` is filtered by
the runner; the runner writes to its own output directory unless the CLI user
supplies `--output` directly.

## Gotchas

- **`_RAW.tar` 404 is not an error.** Many older GEO series only publish the
  series matrix without a per-sample raw bundle. The manifest records
  `status=absent` and the run still succeeds.
- **NCBI rate limits.** Entrez metadata calls are subject to NCBI's per-IP
  rate limit; pass `--no-metadata` for bulk downloads if you don't need it.
- **No FASTQ.** Raw sequencing reads live in SRA, not GEO supplementary.
  This skill does not query SRA. (Could be added behind a separate
  `--include-sra` flag in a follow-up.)
- **Disk usage.** Series with `_RAW.tar` can exceed 10 GB per accession.
  Plan output paths accordingly.

## Disclaimer

OmicsClaw is a research and educational tool for multi-omics analysis. It is
not a medical device and does not provide clinical diagnoses. Consult a domain
expert before making decisions based on these results.
