## Output Structure

```
output_directory/
├── extracted_metadata.json
├── report.md
└── result.json

<--data-dir>/
└── <GSE.../>...   (only when GEO accessions found AND --no-download not set)
```

## File contents

- `output_dir/extracted_metadata.json` — extracted metadata: GEO accessions, study type, sample counts, downloadable resource URLs. Written at `literature_parse.py:80`.
- `output_dir/report.md` — Markdown summary with parsed input type, accession counts, download status. Written at `literature_parse.py:193`.
- `output_dir/result.json` — `summary` includes `n_geo_accessions`, `download_attempted`, `input_type`, `accessions[]`. Written at `literature_parse.py:147`.
- `<--data-dir>/<GSEid>/...` — downloaded GEO datasets, ONLY when GEO accessions are found AND `--no-download` is not passed. Default `--data-dir` is `data/`.

## Notes

- `extracted_metadata.json` is at the output_dir ROOT, NOT under `tables/`. This skill does not follow the analysis-skill convention.
- GEO download requires internet access (the downloader hits GEO FTP / NCBI APIs). Use `--no-download` for air-gapped runs.
- PDF parsing requires `pypdf` per the `requires.install` block in `parameters.yaml`.
