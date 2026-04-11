# skill_dispatching_parallel_agents

Use this playbook only when there are two or more genuinely independent tasks
that can proceed without shared state or sequential dependency.

## Overview

Parallelism helps only when tasks are isolated enough that they do not compete
for the same context, files, or decisions.

Core principle: one focused worker per independent problem domain.

## Iron Law

`NO PARALLEL DISPATCH FOR SHARED-STATE OR SEQUENTIAL TASKS`

If one task's result determines what the other task should do, do not
parallelize them.

## Good Candidates

- separate documentation updates in disjoint files
- independent code slices with non-overlapping ownership
- sidecar verification or exploration that does not block the next local step
- multiple unrelated investigations in different subsystems

## Procedure

1. Keep the immediate blocking task local.
2. Identify independent domains of work.
3. Split ownership by disjoint files or responsibilities.
4. Give each worker a self-contained task description with:
   - context
   - goal
   - inputs or file paths
   - numbered steps
   - deliverable
   - explicit stop condition
5. Review returned results centrally and verify they integrate cleanly.

## OmicsClaw Adaptation

- If your environment supports sub-agents, use isolated task descriptions
  rather than inheriting the whole session history.
- If your environment does not support sub-agents, still use this playbook as a
  decomposition discipline and execute the tasks one by one.
- Never let parallel workers edit the same file set without explicit ownership.

## Do Not Parallelize

- tightly coupled refactors
- debug -> fix -> retry loops
- tasks that share mutable state
- tasks where architecture or root cause is still unclear
- any step where the next decision depends on the previous result

## Red Flags

- two workers touching the same files
- parallelizing before the failure domains are understood
- vague task descriptions
- workers blocked on each other's results
- no integration plan after the workers return

## Required Outputs

- ownership boundaries
- concrete deliverables for each worker
- integration check after results return
- final verification that the parallel results work together
