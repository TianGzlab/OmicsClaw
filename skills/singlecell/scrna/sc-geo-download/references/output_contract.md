# sc-geo-download — Output Contract

## Directory layout

```
<output>/
├── geo/
│   └── <GSE>/
│       ├── <GSE>_family.soft.gz       # SOFT family metadata (always written when 200)
│       ├── <GSE>_series_matrix.txt.gz # Series matrix (always written when 200)
│       ├── <GSE>_RAW.tar              # Supplementary archive (when not 404)
│       └── samples/<GSM>/...          # Extracted per-sample files (when --extract-tar)
├── manifest.csv
├── metadata.json
├── report.md
├── result.json
└── reproducibility/
    └── commands.sh
```

## `manifest.csv` schema

One row per downloaded (or attempted) artifact.

| Column | Type | Description |
|---|---|---|
| `accession` | str | GSE accession (e.g. `GSE109564`). |
| `kind` | str | One of `soft`, `series_matrix`, `raw_tar`, `supp_file`. (`series_matrix` rows can repeat when a study has multiple per-GPL platforms; `supp_file` rows appear when `suppl/` has files other than the canonical `_RAW.tar`.) |
| `status` | str | `downloaded`, `cached` (file already present), `absent` (404), or `synthesized` (`--demo`). |
| `bytes` | int | File size on disk. `0` for `absent`. |
| `sha256` | str | SHA-256 hex digest of the file. Empty for `absent`. |
| `path` | str | Absolute path on disk. Empty for `absent`. |
| `url` | str | Source URL. `demo://local` for `--demo` synthesized files. |

## `metadata.json` shape

```json
{
  "GSE109564": {
    "title": "...",
    "organism": "Homo sapiens",
    "platform": "GPL...",
    "num_samples": 12,
    "pubmed_ids": ["12345678"],
    "summary": "...",
    "publication_date": "2018/05/01"
  }
}
```

Empty objects are written when `--no-metadata` is used or Entrez has no record
for the accession.

## `result.json` envelope

Standard OmicsClaw result envelope. The `summary` section carries:

```json
{
  "method": "geo_https",
  "demo": false,
  "accessions": ["GSE109564"],
  "n_files": 3,
  "total_bytes": 4290000000,
  "include_supp": true,
  "extract_tar": true,
  "fetch_metadata": true
}
```

The `data` section carries `manifest_path`, `metadata_path`, the inlined
`metadata` dict, `geo_root` (absolute path to `<output>/geo/`), and a
`per_accession_paths` map for convenient downstream chaining into
`sc-geo-import`.

## `report.md` structure

1. Standard OmicsClaw header (skill name, version, mode, accession list, total
   bytes).
2. Per-accession metadata block (title / organism / platform / samples / linked
   PubMed IDs / publication date).
3. Downloaded files table (first 50 rows of `manifest.csv` rendered inline; the
   full file is on disk).
4. Next-step `oc run sc-geo-import` invocations for each accession.
5. Standard OmicsClaw disclaimer footer.

## Stability guarantees

- The directory under `<output>/geo/<GSE>/` is the contract that
  `sc-geo-import` consumes; do not move or rename files inside it.
- `manifest.csv` columns are append-only across versions; new columns will not
  be added to the right of existing ones without a major version bump.
- `result.json.summary` keys are append-only; field names will not be renamed.
