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
- Store dated design notes, completion summaries, and architecture records in
  `docs/superpowers/specs/YYYY-MM-DD-topic.md`.
- Store dated multi-step implementation plans in
  `docs/superpowers/plans/YYYY-MM-DD-topic.md`.
- Keep index `README.md` files current in `docs/superpowers/` and its
  subdirectories when adding or removing durable docs.
- Use date prefixes on long-lived documents so they sort chronologically.
- Prefer extending existing docs and code paths over introducing new top-level
  files, helper scripts, or fallback branches without a concrete need.

## Development Workflow

OmicsClaw does not currently ship these as runtime-loaded tool skills. In this
repository, they are implemented as workflow playbooks under
`docs/superpowers/playbooks/`.

These playbooks are not lightweight reminders. They are repository-level
workflow contracts adapted from the reference `feishu_agent` skills. Each one
should define:

- a core principle
- an iron law or non-negotiable gate
- when to use and when not to use it
- red flags and anti-rationalization checks
- required outputs or evidence

For any non-trivial code task, load the matching playbook before touching code:

- Debugging → `docs/superpowers/playbooks/skill_systematic_debugging.md`
- TDD → `docs/superpowers/playbooks/skill_test_driven_development.md`
- Completion verification →
  `docs/superpowers/playbooks/skill_verification_before_completion.md`
- Task planning → `docs/superpowers/playbooks/skill_writing_plans.md`
- Parallel task dispatch →
  `docs/superpowers/playbooks/skill_dispatching_parallel_agents.md`
- Code review → `docs/superpowers/playbooks/skill_requesting_code_review.md`
- Branch completion →
  `docs/superpowers/playbooks/skill_finishing_a_development_branch.md`

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
- Violating the letter of a workflow playbook is usually violating its spirit;
  treat these playbooks as binding process guardrails, not optional advice.

## Repository Maintenance

- If you create a durable plan, spec, or completion summary under
  `docs/superpowers/`, update the corresponding index `README.md`.
- If the work changes contributor expectations, agent entrypoints, or project
  structure, reflect that in `README.md`, `AGENTS.md`, and `CONTRIBUTING.md`
  together rather than leaving instructions split-brain.
