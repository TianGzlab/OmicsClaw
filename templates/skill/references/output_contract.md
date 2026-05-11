## Output Structure

```
output_directory/
├── report.md
├── result.json
└── tables/
    └── replace_me.csv
```

## File contents

<!--
Describe ONLY the files the script actually writes (`.to_csv` / `.savefig` /
`.write_text` / `json.dump` literals).  PR-eval-2 #163 added a lint check at
`scripts/skill_lint.py::_check_output_contract_paths` that fails when a path
mentioned here does not appear in the script (or any imported `_lib/*.py`).

Framework files (report.md, result.json, processed.h5ad, commands.sh, etc.)
are exempt from the substring check — they are written by the common report
helper.
-->

- `tables/replace_me.csv` — written by `<script>.py`. One row per `<unit>`,
  columns: `<col1>, <col2>, ...`.
- `report.md` — Markdown summary written by the common report helper.
- `result.json` — standardised result envelope (`summary` + `data` keys).

## Notes

(Replace with anything a downstream skill reading this output needs to know
about edge cases, sentinel values, NaN handling, etc.)
