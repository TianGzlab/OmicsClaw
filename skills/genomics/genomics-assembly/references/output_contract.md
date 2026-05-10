## Output Structure

```
output_directory/
├── report.md
├── result.json
└── tables/
    ├── assembly_metrics.csv
    └── contig_lengths.csv
```

## File contents

- `tables/assembly_metrics.csv` — written by `genome_assembly.py` (or its imported `_lib/` helpers).
- `tables/contig_lengths.csv` — written by `genome_assembly.py` (or its imported `_lib/` helpers).
- `report.md` — Markdown summary written by the common report helper.
- `result.json` — standardised result envelope (`summary` + `data` keys).

### Demo-only outputs

- `demo_assembly.fasta` — generated only on `--demo`.

## Notes

Auto-generated from `genome_assembly.py` (and the `_lib/` modules it imports) string literals; refine manually with method semantics if needed.
