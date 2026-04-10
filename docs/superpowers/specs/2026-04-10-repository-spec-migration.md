# Repository Spec Migration

Date: 2026-04-10

## Goal

Adopt the strongest repository-maintenance and AI-development conventions from
the reference `feishu_agent` `SPEC.md`, but adapt them to OmicsClaw's
repository-level workflow instead of a chat-workspace model.

## Decisions

1. Add a root `SPEC.md` as the repository contract for AI coding agents and
   human maintainers.
2. Treat `README.md` as the living memory for important decisions and
   milestones.
3. Implement the requested workflow "skills" as tracked documentation
   playbooks under `docs/superpowers/playbooks/` rather than runtime-loaded
   tools.
4. Add index `README.md` files under `docs/superpowers/` so durable guidance is
   discoverable.
5. Update `README.md`, `AGENTS.md`, `CLAUDE.md`, `CONTRIBUTING.md`, and
   `llms.txt` so the new contract is visible from every major agent entrypoint.

## Scope

- Documentation and repository-governance changes only
- No runtime behavior changes to OmicsClaw analysis execution
- No changes to skill discovery or end-user workflow routing

## Result

OmicsClaw now has a repo-native equivalent of the reference project's
`SPEC.md` pattern, without importing the reference project's workspace-specific
assumptions.
