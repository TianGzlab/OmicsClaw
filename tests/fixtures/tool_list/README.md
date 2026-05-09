# Tool List Snapshot Fixtures

Phase 1 baseline of the tool-list-compression refactor. Each JSON file
freezes the OpenAI-tool payload that ``build_bot_tool_specs()`` produces
for one of 10 representative requests — bot/interactive surfaces ×
{baseline, sc-de, bulkrna-de, pdf-paper, workspace, save-intent,
plot-intent, code-edit-intent, web-intent}.

## Regenerating

```bash
UPDATE_SNAPSHOTS=1 pytest tests/test_tool_list_snapshots.py
git diff tests/fixtures/tool_list/   # review before committing
```

## Phase 1 expectation

Every scenario currently sees all 41 tools. After predicate-gated
lazy-load lands, the visible set per scenario shrinks to:

- baseline: ~8 always-on tools (`omicsclaw`, `resolve_capability`,
  `consult_knowledge`, `inspect_data`, `list_directory`, `glob_files`,
  `file_read`, `read_knowhow`)
- realistic_bot_scde: 8 always-on + ~5 file ops
- realistic_bot_pdf_paper: 8 + 2 (parse_literature + fetch_geo_metadata)
