# Spec: Literature Skill Registration Consistency

## Objective

Resolve the registry/catalog drift where `skills/catalog.json` lists the
`literature` skill but `oc run literature --demo` fails with `Unknown skill`.
The `literature` skill should be registered, listed, runnable in demo mode, and
covered by the same doctor consistency check added in the previous increment.

## Tech Stack

- Python 3.11+
- Existing OmicsClaw CLI runner: `omicsclaw.py`
- Existing registry: `omicsclaw/core/registry.py`
- Existing literature script: `skills/literature/literature_parse.py`
- Existing test runner: `python -m pytest`

## Commands

```bash
python -m pytest tests/test_registry.py tests/test_diagnostics.py tests/test_literature_skill.py -q
python omicsclaw.py run literature --demo --output /tmp/omicsclaw_literature_demo
python omicsclaw.py doctor --workspace .
python scripts/generate_catalog.py --check
```

## Project Structure

- `omicsclaw/core/registry.py`: runtime skill discovery and domain metadata.
- `skills/literature/SKILL.md`: literature skill metadata.
- `skills/literature/literature_parse.py`: literature skill CLI.
- `tests/test_registry.py`: registry discovery regression tests.
- `tests/test_literature_skill.py`: literature demo contract tests.
- `docs/engineering/`: durable specs and architecture notes.

## Code Style

Keep the implementation local and explicit:

```python
if demo:
    resolved_input = DEMO_TEXT
    input_type = "text"
else:
    resolved_input = args.input
    input_type = args.input_type
```

Avoid broad compatibility shims. The registry should discover a valid skill
layout; the literature CLI should support its advertised flags.

## Testing Strategy

- Registry unit tests prove `literature` is a primary skill with a real script.
- CLI-level tests prove `literature_parse.py --demo --output <dir>` writes
  local outputs without network access.
- Existing doctor tests prove registry/catalog drift disappears after the
  registry and catalog agree.
- A final CLI smoke test runs through `python omicsclaw.py run literature`.

## Boundaries

- Always: keep changes scoped to registry discovery, literature CLI, tests, and
  small docs/catalog updates.
- Always: keep demo mode local-first and network-free.
- Ask first: moving `skills/literature` into a domain directory or changing the
  public CLI command name.
- Never: remove `literature` from the generated catalog just to silence drift.
- Never: add new third-party dependencies for this fix.

## Success Criteria

- `literature` appears in `registry.skills` and `registry.iter_primary_skills()`.
- `python omicsclaw.py list` reports 89 primary skills.
- `python omicsclaw.py run literature --demo --output <dir>` succeeds.
- Demo output includes `report.md`, `extracted_metadata.json`, and `result.json`.
- `python scripts/generate_catalog.py --check` passes.
- `python omicsclaw.py doctor --workspace .` no longer reports `Skill Catalog`
  drift for `literature`.

## Open Questions

- Whether `literature` should remain an independent domain or be grouped under
  orchestrator is a future information architecture decision. This increment
  preserves the existing `metadata.omicsclaw.domain: literature` contract.
