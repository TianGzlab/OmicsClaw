# Output Contract

Exact layout an agent or user can rely on after this skill runs successfully.

```
output_directory/
├── report.md
├── result.json
├── figures/
│   └── ...
└── tables/
    └── ...
```

## File-by-file

- `report.md` — human-readable summary.
- `result.json` — machine-readable parameters and key metrics.
- `figures/` — every PNG written by the script.
- `tables/` — every CSV written by the script.
