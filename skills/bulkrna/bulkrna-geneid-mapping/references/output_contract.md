## Output Structure

```
output_directory/
├── report.md
├── result.json
├── commands.sh
└── tables/
    ├── mapped_counts.csv
    ├── mapping_table.csv
    └── unmapped_genes.csv
```

## File contents

- `tables/mapped_counts.csv` — written by `bulkrna_geneid_mapping.py` (or its imported `_lib/` helpers).
- `tables/mapping_table.csv` — written by `bulkrna_geneid_mapping.py` (or its imported `_lib/` helpers).
- `tables/unmapped_genes.csv` — written by `bulkrna_geneid_mapping.py` (or its imported `_lib/` helpers).
- `commands.sh` — written by `bulkrna_geneid_mapping.py`.
- `report.md` — Markdown summary written by the common report helper.
- `result.json` — standardised result envelope (`summary` + `data` keys).

### Demo-only outputs

- `demo_bulkrna_ensembl_counts.csv` — generated only on `--demo`.

## Notes

Auto-generated from `bulkrna_geneid_mapping.py` (and the `_lib/` modules it imports) string literals; refine manually with method semantics if needed.
