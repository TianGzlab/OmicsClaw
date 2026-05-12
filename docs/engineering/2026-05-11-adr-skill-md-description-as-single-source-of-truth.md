# ADR: SKILL.md frontmatter `description` is the single source of truth for routing

**Date:** 2026-05-11
**Status:** Proposed
**Affects:** `skills/catalog.json`, every domain `INDEX.md`, every `parameters.yaml.trigger_keywords`, `CLAUDE.md` routing table, `omicsclaw/core/registry.py`, `omicsclaw/routing/*`

## Decision

The Load-when / Skip-when sentence in each skill's `SKILL.md` frontmatter `description` is the **only place** where routing intent is authored. All other routing surfaces (`catalog.json` description, domain `INDEX.md`, `parameters.yaml.trigger_keywords`, the `CLAUDE.md` routing table) are auto-generated from it. Lint enforces no drift; a CI check fails if any generated surface diverges from what would be regenerated today from the SKILL.md descriptions.

## Why

Per Perplexity's *Designing, Refining, and Maintaining Agent Skills* (2026), "the description IS the routing trigger". This project currently has ≥ 4 parallel sources expressing what each skill is for, and they have already drifted — `catalog.json` description is doc-style ("Batch effect correction…"), not Load-when style; `parameters.yaml.trigger_keywords` is empty for ~30+ skills; the `CLAUDE.md` table is hand-edited. Multi-source = inevitable drift. Authors changing description must currently remember to update 3-4 mirrors; in practice they don't.

## Considered

- **Keep parallel sources, add a sync test.** Rejected: adds CI noise without reducing the authoring burden; a sync test that auto-fixes equals derivation, just expressed badly.
- **Move all routing metadata into `parameters.yaml`** (description becomes user-facing only). Rejected: SKILL.md description is what the runtime `load_skill_context()` already injects; moving it would break the existing prefetched-context pipeline and make Claude-Code-style skill loaders harder to support.

## Consequences

- The `omicsclaw-skill-builder` scaffolder must stop emitting `trigger_keywords` lists (Q2 follow-on); `catalog.json` `description` and `trigger_keywords` fields become generated artefacts.
- `scripts/check_description_drift.py` (new) becomes a PR-blocking CI step (`make check-drift` wraps it). On first introduction it caught 3/3 surfaces stale: `skills/catalog.json` (1779 lines stale — see below), 7 `skills/<domain>/INDEX.md` files, and the CLAUDE.md routing table.
- Authors only edit `SKILL.md`. The `make catalog` / `make check-drift` targets regenerate from SKILL.md; any diff signals stale generated files.
- `parameters.yaml.trigger_keywords` is downgraded from required field to optional manual override; lint must justify any non-empty value (alias the description doesn't already cover).
- Deferred: `tags` field semantics tightened separately (see Q3 / `2026-05-11-adr-tags-as-method-inventory.md` if drafted).

## Implementation notes

- Implementing this ADR surfaced a latent worktree-incompatibility bug in `scripts/generate_catalog.py`: the hidden-directory filter used `skill_dir.parts` (absolute path components) so a worktree at `~/.worktrees/<branch>` made the generator silently emit a 0-skill catalog. Fixed by switching to `skill_dir.relative_to(SKILLS_DIR).parts`. Without ADR #1's mandatory drift check this bug would have shipped silently.
