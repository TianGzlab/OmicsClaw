# skill_test_driven_development

Use this playbook for feature work, bug fixes, refactors, and behavior changes
when the desired behavior can be tested before implementation.

## Overview

Write the test first. Watch it fail. Then write the minimum code needed to
make it pass.

Core principle: if you did not observe the test fail for the expected reason,
you do not yet know that the test protects the behavior you care about.

## Iron Law

`NO PRODUCTION CODE WITHOUT A FAILING TEST FIRST`

If you wrote implementation code first for a behavior-changing task, you should
step back and re-establish the red-green-refactor cycle.

## When To Use

Use by default for:

- new features
- bug fixes
- refactors that preserve behavior
- parsing, routing, validation, and output-contract changes

Possible exceptions that should be explicit:

- throwaway prototypes
- purely declarative config edits
- documentation-only changes
- generated code the user does not want hand-tested this way

## Red -> Green -> Refactor

### Red

1. State one target behavior in one sentence.
2. Write the smallest failing test that captures that behavior.
3. Prefer observable behavior over implementation trivia.

### Verify Red

This step is mandatory.

Run the targeted test and confirm:

- it fails
- it fails for the expected reason
- it is failing because behavior is missing or wrong, not because of typos or
  broken setup

If the test passes immediately, you are probably testing existing behavior or
the wrong thing.

### Green

1. Write the smallest implementation change that satisfies the failing test.
2. Do not add speculative options, abstractions, or side improvements.
3. Do not refactor until the test is green.

### Verify Green

This step is mandatory.

Run the targeted test again and confirm:

- the new test passes
- nearby affected tests still pass
- output is clean enough for the repository standard

### Refactor

Only after green:

- reduce duplication
- improve names
- extract helpers if useful

Behavior stays fixed; tests remain green.

## Good Test Standards

- one behavior per test
- clear test name
- behavior-focused assertions
- real code paths unless mocks are unavoidable
- extension of existing repo test patterns when possible

## Red Flags

- "I'll add tests after"
- "This is too small to test"
- implementation written before the test
- a passing test that was never seen failing
- using mocks to prove the mock rather than the behavior
- adding extra features while trying to get green

## OmicsClaw Adaptation

- Prefer extending the nearest existing `pytest` file in the same module or
  skill.
- For CLI behavior, write tests around the observable contract: output files,
  exit behavior, registry responses, or structured outputs.
- For doc-only changes, TDD is usually unnecessary; use verification instead.

## Required Outputs

- the failing test name or case
- proof that the test failed for the expected reason
- the minimal implementation change
- proof that the test now passes
- any broader regression checks you ran
