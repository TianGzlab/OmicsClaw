# skill_requesting_code_review

Use this playbook after substantial or risky changes, or whenever the likely
failure mode is regression rather than syntax.

## Overview

Review is a dedicated bug-finding pass, not a courtesy sign-off.

Core principle: review early, review often, and ask for findings first.

## Iron Law

`NO RISKY OR SUBSTANTIAL CHANGE SHOULD BE TREATED AS READY WITHOUT A FINDINGS-FIRST REVIEW PASS`

## When To Request Review

Mandatory or near-mandatory:

- after a substantial feature or refactor
- after a complex bug fix
- before merging risky work
- before calling branch work fully complete

Especially valuable:

- when stuck
- before refactoring further
- after changes that span code, tests, and docs

## Review Focus

1. Behavioral regressions
2. Missing edge cases
3. Test gaps
4. Invalid assumptions
5. Documentation mismatches
6. Scope creep or mismatch with the plan

## Procedure

1. Present the intended behavior change concisely.
2. Provide the requirement, plan, or user intent being implemented.
3. Point the reviewer to the highest-risk files or diff range.
4. Ask for findings first, ordered by severity.
5. Fix confirmed issues before proceeding.
6. Re-verify the affected behavior after review fixes.

## Suggested Review Output

- strengths
- critical issues
- important issues
- minor issues
- recommendations
- ready / not ready assessment

Each finding should say:

- file or path reference
- what is wrong
- why it matters
- how to fix it if not obvious

## Repository Rule

- If the change alters user-facing workflow or contributor expectations, align
  `README.md`, `AGENTS.md`, and `CONTRIBUTING.md` after review.

## OmicsClaw Adaptation

- If your tool supports isolated reviewer agents, use them with focused context.
- If not, do a dedicated review pass in the same structured format instead of
  casually skimming your own diff.
- Treat review as separate from implementation; do not mix "I wrote it" and
  "I reviewed it" reasoning in one pass.

## Red Flags

- "it is simple, no review needed"
- moving on with unresolved important issues
- asking for praise instead of findings
- reviewing without reading the diff or changed docs
- calling something ready without a clear verdict

## Required Outputs

- findings ordered by severity
- file or path references for each issue
- a clear ready / not ready assessment
- follow-up fixes plus re-verification where needed
