# skill_verification_before_completion

Use this playbook before declaring a task complete.

## Checklist

1. Run the narrowest meaningful verification for the files or behavior changed.
2. If the change is risky or cross-cutting, run at least one broader affected
   check as well.
3. Inspect generated artifacts, docs, or command outputs directly when the task
   depends on them.
4. Confirm instructions, links, and file references still resolve.
5. Be explicit about anything you could not verify.

## Reporting Standard

- State what you ran or inspected.
- State the result.
- State any remaining risks or gaps.
- Never claim a test or validation step succeeded unless you observed it.
