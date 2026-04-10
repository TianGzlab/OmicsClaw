# skill_finishing_a_development_branch

Use this playbook when preparing a branch, patch series, or handoff for review
or merge.

## Checklist

1. Remove unrelated edits from the scope you control.
2. Ensure the final diff reflects a coherent single purpose.
3. Confirm tests or verification steps are documented and current.
4. Update `README.md` for important milestones or lasting decisions.
5. Update any affected index docs or playbook references.
6. Summarize what changed, how it was verified, and any residual risk.

## Guardrails

- Do not rewrite history or revert unrelated user changes.
- Do not add cleanup-only churn at the end of a branch unless it is necessary
  for correctness.
