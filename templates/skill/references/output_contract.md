# Output Contract

<!--
Describe ONLY the files the script actually writes (`.to_csv` / `.savefig` /
`.write_text` / `json.dump` literals).  `scripts/skill_lint.py::_check_output_
contract_paths` fails when a path mentioned here does not appear in the
script (or any imported `_lib/*.py`).

Framework files (report.md, result.json, processed.h5ad, commands.sh,
manifest.json, requirements.txt, checksums.sha256) are exempt from the
substring check — they are written by the common report helper.
-->

## Output Structure

```
output_directory/
├── report.md
├── result.json
└── tables/
    └── replace_me.csv
```

## File contents

- `tables/replace_me.csv` — written by `replace_me.py`. One row per `<unit>`,
  columns: `feature, value, rank, method`.
- `report.md` — Markdown summary written by the common report helper.
- `result.json` — standardised result envelope (`summary` + `data` keys).

## Notes

(Replace with anything a downstream skill reading this output needs to know
about edge cases, sentinel values, NaN handling, etc.)

<!--
==============================================================================
OPTIONAL outputs — add the blocks that match what your script actually
writes.  REMOVE the ones that don't apply.  Every path you add here must
appear as a substring in the script (or a sibling `_lib/*.py`) or the lint
will fail.

### When the skill writes a processed AnnData

```
output_directory/
├── processed.h5ad
```

- `processed.h5ad` — written by `<script>.py`. Counts in
  `layers["counts"]`, log-normalized in `adata.X`, results stashed in `uns`.
- Set `saves_h5ad: true` in `parameters.yaml`.

### When the skill emits Python figures

```
output_directory/
└── figures/
    └── <name>.png
```

- `figures/<name>.png` — written by `<script>.py` via matplotlib `savefig`.

### When the skill emits figure-ready data for the R Enhanced layer

```
output_directory/
├── figure_data/
│   ├── manifest.json
│   └── <name>.csv
```

- `figure_data/<name>.csv` — figure-ready export consumed by the optional
  R post-renderer.  See `references/r_visualization.md`.

### When the skill emits a reproducibility bundle

```
output_directory/
└── reproducibility/
    ├── commands.sh
    └── analysis_notebook.ipynb
```

- `reproducibility/commands.sh` — re-invocation script written by the common
  report helper via `write_standard_run_artifacts`.
- `reproducibility/analysis_notebook.ipynb` — Jupyter notebook scaffolding
  the same analysis end-to-end.
==============================================================================
-->
