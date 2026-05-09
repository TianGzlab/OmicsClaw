# System Prompt Snapshot Fixtures

These files freeze the assembled system prompt content for 10 representative
request shapes. They serve as the regression baseline for the
system-prompt-compression refactor (Phases 2-4).

## Scenarios

| Scenario | Surface | Purpose |
|---|---|---|
| `baseline_bot.txt` | bot | Always-on minimum (no dynamic context) |
| `baseline_interactive.txt` | interactive | CLI surface always-on minimum |
| `baseline_pipeline.txt` | pipeline | Pipeline surface always-on minimum |
| `realistic_bot_scde.txt` | bot | sc-de query with capability + memory + plan + workspace |
| `realistic_bot_bulkrna_de.txt` | bot | bulkrna-de query, capability only |
| `realistic_bot_pdf.txt` | bot | PDF / paper extraction intent |
| `realistic_interactive_workspace.txt` | interactive | Interactive with active workspace |
| `realistic_interactive_mcp.txt` | interactive | Interactive with active MCP server |
| `realistic_bot_capability_present.txt` | bot | sc-de with deterministic capability already provided |
| `realistic_bot_genomics_vc.txt` | bot | Genomics variant-calling query |

## Regenerating

When a phase intentionally changes the system prompt content, regenerate
the fixtures and review the diff:

```bash
UPDATE_SNAPSHOTS=1 pytest tests/test_system_prompt_snapshots.py
git diff tests/fixtures/system_prompt/    # review diff before committing
```

## Determinism

- Workspace paths use `/tmp/` to avoid resolver differences across machines.
- KH content lives in `knowledge_base/knowhows/` (checked into the repo).
- Skill registry is loaded from `skills/<domain>/<skill>/SKILL.md` (also
  checked in).
- No timestamps, random values, or session IDs are included in the
  assembled system prompt.
