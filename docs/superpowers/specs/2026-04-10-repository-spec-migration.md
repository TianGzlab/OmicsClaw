# Repository Spec Migration

Date: 2026-04-10

## Goal

Adopt the strongest repository-maintenance and AI-development conventions from
the reference `feishu_agent` `SPEC.md`, but adapt them to OmicsClaw's
repository-level workflow instead of a chat-workspace model.

## Comparison Findings

The initial OmicsClaw migration captured the topic map but not enough of the
reference skills' behavioral force.

What was missing at first:

1. Iron laws and non-negotiable gates
2. Red flags and anti-rationalization language
3. Explicit stage sequencing
4. Required outputs and evidence standards
5. Stronger workflow chaining across planning, TDD/debugging, verification,
   review, and branch completion

What was preserved and then strengthened:

1. Root `SPEC.md` as the repo contract
2. `README.md` as living memory
3. Workflow documents under `docs/superpowers/playbooks/`
4. Cross-links from the main agent and contributor entrypoints

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
6. Rework the playbooks so they preserve the reference skills' core design:
   core principles, iron laws, red flags, gates, and required outputs.

## Scope

- Documentation and repository-governance changes only
- No runtime behavior changes to OmicsClaw analysis execution
- No changes to skill discovery or end-user workflow routing

## Result

OmicsClaw now has a repo-native equivalent of the reference project's
`SPEC.md` pattern, without importing the reference project's workspace-specific
assumptions.

The playbooks are now intended to constrain behavior under pressure, not merely
name the workflow themes.
