## Output Structure

Demo and real-query runs produce DIFFERENT outputs (mutually exclusive):

```
# --demo
output_directory/
└── demo_report.txt

# --query / --input
output_directory/
└── result.json
```

## File contents

- `result.json` — routing decision envelope. Schema:
  ```json
  {
    "status": "success",
    "data": {
      "detected_domain": "<domain or null>",
      "detected_skill":  "<skill name or null>",
      "confidence":      0.0,
      "coverage":        "exact_skill | partial | no_skill",
      "should_search_web": false,
      "missing_capabilities": []
    }
  }
  ```
  Written via `out_json.write_text(json.dumps(result, indent=2))` at `omics_orchestrator.py:409`.
- `demo_report.txt` — synthetic query → skill mapping with confidence, written at `omics_orchestrator.py:334` only on `--demo` (the demo path returns at `:363` BEFORE `result.json` is written).

## Notes

- This skill does NOT execute the chosen downstream skill. It only emits the routing decision; the user (or wrapping orchestration script) must invoke the selected skill separately.
- No `tables/`, `figures/`, or `report.md` — orchestrator output deviates from the standard analysis-skill convention.
- Missing `LLM_API_KEY` for `--routing-mode llm` / `hybrid` SILENTLY falls back to keyword routing (`omicsclaw/routing/llm_router.py:48-50` logs a warning and returns `(None, 0.0)`). The run still exits 0; inspect logs to confirm which mode actually fired.
- `--routing-mode` is IGNORED when `--query` is set (the `args.query` branch dispatches to `resolve_capability` which is keyword-only). It only takes effect for file-only routing and `--demo`.
