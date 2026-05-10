## Output Structure

```
output_directory/
├── SCAFFOLD_SUMMARY.md
├── report.md
├── result.json
└── reproducibility/
    └── commands.sh

skills/<domain>/<skill-name>/
└── (the new skill directory — written by create_skill_scaffold)
```

## File contents

- `output_dir/SCAFFOLD_SUMMARY.md` — human-readable summary of what was generated. Written at `omics_skill_builder.py:129`.
- `output_dir/report.md` — Markdown report mirroring the scaffold + parameters. Written at `omics_skill_builder.py:130`.
- `output_dir/reproducibility/commands.sh` — replay command including the original `--request` and resolved `--domain`. Written at `omics_skill_builder.py:132-137`.
- `output_dir/result.json` — `summary` includes the new skill's domain, name, paths, and trigger keywords. Written at `omics_skill_builder.py:139-141`.
- `skills/<domain>/<skill-name>/` — the actual NEW skill directory (SKILL.md + parameters.yaml + references/ + tests/), written by `create_skill_scaffold` from `omicsclaw.core.skill_scaffolder`.

## Notes

- The new-skill directory is at `skills/<domain>/<skill-name>/`, NOT under `--output`. `--output` only receives the scaffold summary + report.
- Repeatable flags: `--trigger-keyword`, `--method`, `--input-format`, `--output-item` (each can be passed multiple times via `action="append"`).
- `--source-analysis-dir <path>` and `--promote-from-latest` promote a previous autonomous-analysis output into the new skill.
