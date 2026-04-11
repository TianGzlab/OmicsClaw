# skill_writing_plans

Use this playbook when work is multi-step, ambiguous, spans multiple sessions,
or needs coordination across files or agents.

## Overview

Implementation plans should be detailed enough that a competent engineer with
little prior context can execute them without guessing what files to touch, how
to test the result, or where scope boundaries are.

Core principle: break multi-step work into small, testable, reviewable units
before coding.

## Iron Law

`NO MULTI-STEP IMPLEMENTATION FROM VAGUE INTENT ALONE`

If the task is large enough that you cannot clearly name the steps, files, and
verification path, write or update a plan first.

## When to Write a Durable Plan

- The task will take multiple commits or handoff points.
- There are multiple plausible implementation paths.
- Several subsystems or contributors must stay aligned.
- The task needs explicit success criteria or stop conditions.

Do not create a durable plan for trivial one-step edits.

## Scope Check

If the request actually contains multiple independent subsystems, split it into
separate plans or clearly separated plan sections. Each slice should be able to
produce working, testable progress on its own.

## File Mapping First

Before writing steps, map out:

- files to create
- files to modify
- tests to add or extend
- docs that must change

Decomposition decisions become more reliable once file ownership is explicit.

## Plan Format

Write durable plans to `docs/superpowers/plans/YYYY-MM-DD-topic.md`.

Every durable plan should include:

1. Goal
2. Scope and non-goals
3. Key assumptions or constraints
4. File map with exact repo-relative paths
5. Ordered implementation tasks
6. Verification strategy
7. Stop conditions or acceptance criteria

## Task Granularity

Prefer bite-sized tasks. Good step sizes are things like:

- write the failing test
- run it and confirm the expected failure
- implement the minimal fix
- run the targeted verification
- update docs

Avoid plan steps like "implement the feature" when that hides multiple code and
verification actions.

## Review Loop

After drafting a plan:

1. Check it against the original request or spec.
2. Remove scope creep and placeholders.
3. Confirm every task has a verification path.
4. If your environment supports independent reviewers or sub-agents, have one
   review the plan in isolation.
5. If not, do a dedicated self-review pass rather than executing immediately.

## OmicsClaw Adaptation

- Use exact repo-relative file paths, not vague references.
- Align with existing repository patterns before inventing structure.
- Prefer DRY, YAGNI, TDD, and frequent verification.
- If the plan changes contributor workflow or repo structure, remember that the
  resulting implementation must update `README.md`.

## Guardrails

- Do not write plan files full of placeholders or vague advice.
- Do not hide risky assumptions.
- Update or close the plan if the chosen direction changes materially.

## Red Flags

- "I'll figure it out while coding"
- plan steps without exact files or verification
- one giant task standing in for multiple real actions
- hidden scope creep
- placeholders that defer important decisions

## Required Outputs

- the durable plan file
- exact file map
- ordered implementation tasks
- verification mapping for each task or task group
- clear acceptance criteria
