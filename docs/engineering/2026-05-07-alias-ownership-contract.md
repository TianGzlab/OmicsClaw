# Spec: Alias Ownership Contract

## Objective

Skill aliases need one maintainable source of truth. For every filesystem
discovered skill with a `SKILL.md`, canonical `name` and `legacy_aliases` are
owned by that `SKILL.md` frontmatter. The hardcoded registry table is retained
only as a backward-compatible fallback for skills that cannot be discovered from
the filesystem metadata.

## Commands

```bash
python -m pytest tests/test_registry_alias_contract.py -q
python -m pytest tests/test_registry.py tests/test_keyword_routing.py -q
```

## Project Structure

- `skills/**/SKILL.md`: canonical alias metadata and declared legacy aliases.
- `omicsclaw/core/lazy_metadata.py`: lightweight frontmatter reader.
- `omicsclaw/core/registry.py`: registry discovery and fallback wiring.
- `tests/test_registry_alias_contract.py`: alias ownership guardrail.

## Code Style

Registry merge logic should be explicit about ownership:

```python
if lazy and lazy.description:
    legacy_aliases = list(lazy.legacy_aliases or [])
else:
    legacy_aliases = list(hardcoded_info.get("legacy_aliases", []))
```

## Testing Strategy

- Add a registry-derived contract test that compares each discovered skill's
  runtime `legacy_aliases` with its `SKILL.md` `metadata.omicsclaw.legacy_aliases`.
- Preserve lookup behavior for declared aliases and representative old aliases.
- Keep the test lightweight: no skill execution, no optional analysis imports.

## Boundaries

- Always: preserve documented legacy lookups by moving any needed aliases into
  `SKILL.md` before removing hardcoded merge behavior.
- Ask first: deleting public aliases from `SKILL.md`.
- Never: make hardcoded `_HARDCODED_SKILLS` the source of truth for a skill that
  has valid filesystem metadata.

## Success Criteria

- For every primary skill with `SKILL.md`, registry `legacy_aliases` exactly
  match `metadata.omicsclaw.legacy_aliases`.
- `resolve_skill_alias()` still resolves declared aliases such as `preprocess`.
- Existing registry and keyword routing tests continue to pass.
