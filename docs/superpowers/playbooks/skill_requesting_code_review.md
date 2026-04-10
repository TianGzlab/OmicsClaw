# skill_requesting_code_review

Use this playbook after substantial or risky changes, or whenever the likely
failure mode is regression rather than syntax.

## Review Focus

1. Behavioral regressions
2. Missing edge cases
3. Test gaps
4. Invalid assumptions
5. Documentation mismatches

## Procedure

1. Present the intended behavior change concisely.
2. Point the reviewer to the highest-risk files or paths.
3. Ask for findings first, ordered by severity.
4. Fix confirmed issues.
5. Re-verify the affected behavior before closing the task.

## Repository Rule

- If the change alters user-facing workflow or contributor expectations, align
  `README.md`, `AGENTS.md`, and `CONTRIBUTING.md` after review.
