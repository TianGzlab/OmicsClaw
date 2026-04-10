# skill_dispatching_parallel_agents

Use this playbook only when subtasks are genuinely independent.

## Good Candidates

- Separate documentation updates in disjoint files
- Independent code slices with non-overlapping ownership
- Sidecar verification or exploration that does not block the next local step

## Procedure

1. Keep the immediate blocking task local.
2. Split work by clear ownership and disjoint file sets.
3. Give each worker a concrete deliverable and explicit stop condition.
4. Avoid duplicate investigation across workers.
5. Integrate results quickly and resolve conflicts centrally.

## Do Not Parallelize

- Tightly coupled refactors
- Debug-fix-retry loops
- Any step where the next decision depends on the previous result
