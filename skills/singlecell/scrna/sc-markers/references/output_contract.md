## Output Structure

```
output_directory/
├── report.md
├── result.json
├── analysis_summary.txt
├── commands.sh
├── manifest.json
├── processed.h5ad
├── requirements.txt
├── tables/
│   ├── cell_metadata.csv
│   ├── cluster_summary.csv
│   ├── markers_all.csv
│   └── markers_top.csv
└── figures/
    ├── r_feature_violin.png
    └── r_marker_heatmap.png
```

## File contents

- `tables/cell_metadata.csv` — written by `sc_markers.py` (or its imported `_lib/` helpers).
- `tables/cluster_summary.csv` — written by `sc_markers.py` (or its imported `_lib/` helpers).
- `tables/markers_all.csv` — written by `sc_markers.py` (or its imported `_lib/` helpers).
- `tables/markers_top.csv` — written by `sc_markers.py` (or its imported `_lib/` helpers).
- `figures/r_feature_violin.png` — written by `sc_markers.py` (or its imported `_lib/` helpers).
- `figures/r_marker_heatmap.png` — written by `sc_markers.py` (or its imported `_lib/` helpers).
- `analysis_summary.txt` — written by `sc_markers.py`.
- `commands.sh` — written by `sc_markers.py`.
- `manifest.json` — written by `sc_markers.py`.
- `processed.h5ad` — written by `sc_markers.py`.
- `requirements.txt` — written by `sc_markers.py`.
- `report.md` — Markdown summary written by the common report helper.
- `result.json` — standardised result envelope (`summary` + `data` keys).

## Notes

Auto-generated from `sc_markers.py` (and the `_lib/` modules it imports) string literals; refine manually with method semantics if needed.
