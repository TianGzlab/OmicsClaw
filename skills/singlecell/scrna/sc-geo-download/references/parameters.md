# sc-geo-download — Parameter Reference

## Required

| Flag | Type | Notes |
|---|---|---|
| `--output <dir>` | path | Output directory. Created if missing. |

Plus at least one of:

| Flag | Type | Notes |
|---|---|---|
| `--accession <GSE>` | str (repeatable) | GEO accession to download (e.g. `GSE109564`). Use multiple times for batch download. |
| `--pubmed-id <PMID>` | int | PubMed ID whose linked GEO Series should be downloaded. Resolved via NCBI Entrez. |
| `--demo` | flag | Synthesize a tiny GEO-like bundle locally; no network. |

If none of `--accession`, `--pubmed-id`, or `--demo` is supplied, the skill
exits with a clear error.

## Optional

| Flag | Default | Notes |
|---|---|---|
| `--include-supp` / `--no-include-supp` | `True` | Download the optional `<GSE>_RAW.tar` supplementary archive. |
| `--extract-tar` / `--no-extract-tar` | `True` | Unpack the `_RAW.tar` into `samples/<GSM>/` subdirectories. |
| `--no-metadata` | `False` | Skip Entrez metadata lookup (avoids one extra round-trip per accession). |
| `--timeout <seconds>` | `60.0` | Per-HTTP-request timeout. |

## Examples

```bash
# Single accession with default (download SOFT + matrix + RAW, extract RAW)
oc run sc-geo-download --accession GSE109564 --output /data

# Batch download two accessions
oc run sc-geo-download --accession GSE109564 --accession GSE149689 \
  --output /data

# Resolve linked GEO Series from a PubMed publication
oc run sc-geo-download --pubmed-id 33712379 --output /data

# Series matrix only (no raw bundles, no Entrez metadata)
oc run sc-geo-download --accession GSE109564 --output /data \
  --no-include-supp --no-metadata

# Local demo (no network, ~10 KB output)
oc run sc-geo-download --demo --output /tmp/geo_demo
```

## Composition with sc-geo-import

The per-accession directory layout under `<output>/geo/<GSE>/` is the exact
input shape `sc-geo-import` expects:

```bash
oc run sc-geo-download --accession GSE109564 --output /data
oc run sc-geo-import   --input /data/geo/GSE109564 --output /data/imported
```
