# skill_test_driven_development

Use this playbook when behavior can be specified clearly enough to encode in a
test before implementation, especially for regressions, parsing rules, routing,
or output contracts.

## Procedure

1. State the target behavior in one sentence.
2. Write the smallest failing test or assertion that captures that behavior.
3. Confirm the test fails for the expected reason.
4. Implement the smallest code change that makes the test pass.
5. Refactor only after the test is green.
6. Run the targeted test set and any nearby regression checks.

## Guardrails

- Keep tests tied to observable behavior, not internal implementation trivia.
- Prefer extending existing test files and patterns in the same module.
- If the task is too exploratory for strict TDD, fall back to a
  reproduce-fix-verify loop and add tests once behavior is understood.
