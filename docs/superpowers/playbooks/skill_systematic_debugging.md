# skill_systematic_debugging

Use this playbook when a bug, regression, test failure, or unexpected behavior
is not already explained by a single obvious cause.

## Procedure

1. Reproduce the problem with the exact command, input, and environment.
2. Capture the concrete failure signal: stack trace, stderr, wrong output, or
   missing artifact.
3. Narrow the scope to one subsystem, file, or behavior before editing.
4. Form hypotheses from the code and docs; do not guess blindly.
5. Change one thing at a time and keep the fix minimal.
6. Add or update a regression test when practical.
7. Re-run the minimal failing case first, then the affected broader checks.

## Outputs

- A clear root cause
- The exact fix applied
- Verification evidence
- A `README.md` update if the fix changes a lasting repository decision
