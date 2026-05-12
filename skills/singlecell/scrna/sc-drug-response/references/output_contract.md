## Output Structure

```
output_directory/
├── report.md
├── result.json
├── analysis_summary.txt
├── commands.sh
├── processed.h5ad
├── requirements.txt
├── tables/
│   ├── IC50_prediction.csv
│   ├── PRISM_prediction.csv
│   ├── cell_metadata.csv
│   ├── drug_rankings.csv
│   └── masked_drugs.csv
└── figures/
    ├── drug_cluster_heatmap.png
    ├── drug_sensitivity_umap.png
    └── top_drugs_bar.png
```

## File contents

- `tables/IC50_prediction.csv` — written by `sc_drug_response.py` (or its imported `_lib/` helpers).
- `tables/PRISM_prediction.csv` — written by `sc_drug_response.py` (or its imported `_lib/` helpers).
- `tables/cell_metadata.csv` — written by `sc_drug_response.py` (or its imported `_lib/` helpers).
- `tables/drug_rankings.csv` — written by `sc_drug_response.py` (or its imported `_lib/` helpers).
- `tables/masked_drugs.csv` — written by `sc_drug_response.py` (or its imported `_lib/` helpers).
- `figures/drug_cluster_heatmap.png` — written by `sc_drug_response.py` (or its imported `_lib/` helpers).
- `figures/drug_sensitivity_umap.png` — written by `sc_drug_response.py` (or its imported `_lib/` helpers).
- `figures/top_drugs_bar.png` — written by `sc_drug_response.py` (or its imported `_lib/` helpers).
- `analysis_summary.txt` — written by `sc_drug_response.py`.
- `commands.sh` — written by `sc_drug_response.py`.
- `processed.h5ad` — written by `sc_drug_response.py`.
- `requirements.txt` — written by `sc_drug_response.py`.
- `report.md` — Markdown summary written by the common report helper.
- `result.json` — standardised result envelope (`summary` + `data` keys).

## Notes

Auto-generated from `sc_drug_response.py` (and the `_lib/` modules it imports) string literals; refine manually with method semantics if needed.
