# SPEC.md — OmicsClaw Repository Maintenance and Development Contract

This file captures the repository-level working contract for AI coding agents
and human contributors doing maintenance or development work in OmicsClaw.

## Agent Behavior

- Respond in the language the user uses, typically Chinese or English.
- Stay concise, practical, and execution-focused.
- Before any complex maintenance, refactor, or feature task, read `README.md`
  first to understand project context and prior decisions. Then read
  `AGENTS.md`, this `SPEC.md`, and any directly relevant docs or `SKILL.md`
  files.
- Verify claims from the codebase and current docs before acting on them.
- When you make an important decision or complete a meaningful milestone,
  update `README.md` while preserving its existing structure.

## File Conventions

- Treat the root `README.md` as the repository's living memory for goals,
  milestones, architecture changes, and contributor-facing workflow rules.
- Store durable design notes, completion summaries, and architecture records
  under the relevant `docs/` topic area.
- Keep local agent workflow notes outside the repository or under ignored
  paths.
- Use date prefixes on long-lived documents so they sort chronologically.
- Prefer extending existing docs and code paths over introducing new top-level
  files, helper scripts, or fallback branches without a concrete need.

## Development Workflow

OmicsClaw does not ship local agent workflow playbooks as tracked project
documentation. Keep such notes outside the repository or under ignored paths.

Typical workflow chaining:

1. If the task is multi-step or ambiguous, use the planning playbook first.
2. If behavior changes, use TDD unless the task is clearly exempt.
3. If something fails, switch to systematic debugging before proposing fixes.
4. Before claiming success, use completion verification.
5. For substantial or risky changes, use code review before merge or push.
6. When wrapping up branch work, use the branch-finish playbook.

Additional rules:

- Do not overengineer.
- Do not add fallback paths or backward-compatibility shims unless the user,
  public API, or repository contract requires them.
- Prefer the smallest clear change that solves the current problem.
- Verify the affected behavior before declaring work complete.
- Treat planning, debugging discipline, and completion verification as
  required process guardrails for non-trivial changes.

## Repository Maintenance

- Do not commit local agent workflow notes; keep them under ignored paths.
- If the work changes contributor expectations, agent entrypoints, or project
  structure, reflect that in `README.md`, `AGENTS.md`, and `CONTRIBUTING.md`
  together rather than leaving instructions split-brain.
