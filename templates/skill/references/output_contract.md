# Output Contract

<!--
Describe ONLY the files the script actually writes (`.to_csv` / `.savefig` /
`.write_text` / `json.dump` literals).  Nothing checks this mechanically, so
it is a review item.

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
  When the script finishes cleanly it tail-calls `mark_result_status(output_dir, "ok")`,
  which adds a top-level `status: "ok"` field; a run that crashed before
  that call has no `status`. Valid values: `"ok"`, `"partial"`, `"failed"`.

## Notes

(Replace with anything a downstream skill reading this output needs to know
about edge cases, sentinel values, NaN handling, etc.)

<!--
==============================================================================
OPTIONAL outputs — add the blocks that match what your script actually
writes.  REMOVE the ones that don't apply.  Every path you add here should
appear as a substring in the script (or a sibling `_lib/*.py`).

### When the skill writes a processed AnnData

```
output_directory/
├── processed.h5ad
```

- `processed.h5ad` — written by `<script>.py`. Counts in
  `layers["counts"]`, log-normalized in `adata.X`, results stashed in `uns`.
- Say so in `SKILL.md`'s `## Inputs & Outputs` when the script writes a `.h5ad`.

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
==============================================================================
-->
