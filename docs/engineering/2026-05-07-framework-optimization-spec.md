# Spec: Framework Optimization Roadmap

## Objective

Bring OmicsClaw's framework architecture into a single, testable contract from
skill discovery through execution and output UX. The optimization route is
driven by eight concrete outcomes:

1. Public facts stay synchronized with the runtime registry and graphify map.
2. Skill execution is extracted from the root `omicsclaw.py` into a reusable
   core runner module.
3. Skills write native analysis artifacts while the runner owns shared top-level
   output UX such as `README.md` and notebooks.
4. Every `SKILL.md` exposes the same minimum OmicsClaw metadata contract.
5. Each domain has documented input contracts: supported suffixes, real loaders,
   minimum fields, and downstream data conventions.
6. Alias ownership converges toward `SKILL.md` metadata instead of duplicated
   hardcoded legacy tables.
7. CLI, app, bot, interactive, and remote execution share one executor/runner
   contract instead of independently assembling command lines.
8. Lightweight contract tests guard registry counts, skill help, metadata,
   output structure, README/notebook generation, and documentation facts.

The user is repository maintainers and future agents. Success means a maintainer
can inspect docs/tests and know exactly which parts are complete, what remains,
and how a change is verified.

## Tech Stack

- Python 3.11+
- `pytest` for contract and regression tests
- OmicsClaw runtime registry: `omicsclaw/core/registry.py`
- CLI entrypoint: `omicsclaw.py`
- App/remote execution layer: `omicsclaw/execution/`
- Bot/interactive surfaces: `bot/`, `omicsclaw/interactive/`
- Documentation: `README.md`, `AGENTS.md`, `docs/architecture/`,
  `docs/engineering/`, `docs/superpowers/plans/`

## Commands

Targeted verification:

```bash
python -m pytest tests/test_documentation_facts.py -q
python -m pytest tests/test_diagnostics.py tests/test_registry.py -q
python omicsclaw.py doctor --workspace .
python omicsclaw.py list
```

Broader verification before marking a framework slice complete:

```bash
python -m pytest -q
python scripts/generate_catalog.py
python omicsclaw.py doctor --workspace .
graphify update .
```

## Project Structure

```text
omicsclaw.py
  Temporary root CLI dispatcher. `run_skill()` must move out over time.

omicsclaw/core/
  Registry and future shared `skill_runner.py`.

omicsclaw/execution/
  Job/executor abstractions for app and remote execution.

bot/ and omicsclaw/interactive/
  User-facing surfaces that should call the shared runner contract.

docs/engineering/
  Durable specs and architecture contracts.

docs/superpowers/plans/
  Ordered task breakdowns and checkpoints for implementation sessions.

tests/
  Contract tests that prove registry/docs/runner/output behavior.
```

## Code Style

Prefer small, explicit contracts over broad framework rewrites. Tests should
assert observable behavior and avoid depending on optional analysis packages.

Example style for a contract helper:

```python
def registry_skill_counts() -> tuple[int, dict[str, int]]:
    reg = OmicsRegistry()
    reg.load_all()
    items = reg.iter_primary_skills()
    counts: dict[str, int] = {}
    for _, info in items:
        domain = str(info.get("domain", "")).strip()
        counts[domain] = counts.get(domain, 0) + 1
    return len(items), counts
```

## Testing Strategy

- Use TDD for any behavior or contract change: write the focused failing test,
  verify RED, implement the smallest change, then verify GREEN.
- Keep tests lightweight: registry/docs/metadata/output contract tests should
  not import Scanpy, R bridges, or external CLIs.
- Prefer dynamic registry-derived expectations for counts so tests catch future
  documentation drift without hardcoding stale values.
- Add broader all-skill tests only when they can run quickly or are explicitly
  marked for slower CI lanes.

## Boundaries

- Always: keep edits scoped to the current roadmap slice, verify with concrete
  commands, and update durable docs after meaningful milestones.
- Ask first: adding large dependencies, changing CI topology, deleting legacy
  aliases, or changing public CLI behavior in a breaking way.
- Never: remove failing tests to make progress, revert unrelated user changes,
  upload user data, or make scientific behavior changes without a skill-specific
  spec.

## Success Criteria

- The first slice makes facts synchronized across README/AGENTS/architecture
  docs and protects them with a documentation fact test.
- Later slices are implemented in order from the plan, each with acceptance
  criteria and verification commands.
- `oc doctor` remains the quick local health gate for environment,
  registry/catalog, and graphify-map drift.
- No slice is considered complete until its tests and manual verification cover
  the explicit objective for that slice.

## Open Questions

- Whether all top-level output files currently written by individual skills are
  considered legacy behavior that must remain temporarily during runner
  extraction.
- Whether legacy aliases should be removed in one migration or deprecated across
  multiple releases.
- Which all-skill `--help` and demo-output tests belong in default CI versus a
  slower maintenance lane.
