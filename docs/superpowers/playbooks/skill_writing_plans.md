# skill_writing_plans

Use this playbook when work is multi-step, ambiguous, spans multiple sessions,
or needs coordination across files or agents.

## When to Write a Durable Plan

- The task will take multiple commits or handoff points.
- There are multiple plausible implementation paths.
- Several subsystems or contributors must stay aligned.
- The task needs explicit success criteria or stop conditions.

## Plan Format

Write durable plans to `docs/superpowers/plans/YYYY-MM-DD-topic.md` and include:

1. Goal
2. Scope and non-goals
3. Key assumptions or constraints
4. Ordered implementation steps
5. Verification strategy
6. Stop conditions or acceptance criteria

## Guardrails

- Do not create plan files for trivial one-step edits.
- Update or close the plan if the chosen direction changes materially.
