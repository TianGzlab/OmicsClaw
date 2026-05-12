## Output Structure

```
output_directory/
├── report.md
├── result.json
├── analysis_summary.txt
├── manifest.json
├── metacells.h5ad
├── metacells_annotated.h5ad
├── processed.h5ad
├── tables/
│   ├── cell_metadata.csv
│   ├── cell_to_metacell.csv
│   ├── centroid_points.csv
│   ├── embedding_points.csv
│   └── metacell_summary.csv
└── figures/
    ├── metacell_centroids.png
    ├── metacell_size_distribution.png
    └── r_embedding_discrete.png
```

## File contents

- `tables/cell_metadata.csv` — written by `sc_metacell.py` (or its imported `_lib/` helpers).
- `tables/cell_to_metacell.csv` — written by `sc_metacell.py` (or its imported `_lib/` helpers).
- `tables/centroid_points.csv` — written by `sc_metacell.py` (or its imported `_lib/` helpers).
- `tables/embedding_points.csv` — written by `sc_metacell.py` (or its imported `_lib/` helpers).
- `tables/metacell_summary.csv` — written by `sc_metacell.py` (or its imported `_lib/` helpers).
- `figures/metacell_centroids.png` — written by `sc_metacell.py` (or its imported `_lib/` helpers).
- `figures/metacell_size_distribution.png` — written by `sc_metacell.py` (or its imported `_lib/` helpers).
- `figures/r_embedding_discrete.png` — written by `sc_metacell.py` (or its imported `_lib/` helpers).
- `analysis_summary.txt` — written by `sc_metacell.py`.
- `manifest.json` — written by `sc_metacell.py`.
- `metacells.h5ad` — written by `sc_metacell.py`.
- `metacells_annotated.h5ad` — written by `sc_metacell.py`.
- `processed.h5ad` — written by `sc_metacell.py`.
- `report.md` — Markdown summary written by the common report helper.
- `result.json` — standardised result envelope (`summary` + `data` keys).

## Notes

Auto-generated from `sc_metacell.py` (and the `_lib/` modules it imports) string literals; refine manually with method semantics if needed.
