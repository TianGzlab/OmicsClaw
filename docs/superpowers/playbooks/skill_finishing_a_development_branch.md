# skill_finishing_a_development_branch

Use this playbook when preparing a branch, patch series, or handoff for review
or merge.

## Overview

Completion work should end with a deliberate integration choice, not a vague
"I guess we're done".

Core principle: verify -> choose integration path -> execute that choice ->
clean up responsibly.

## Iron Law

`NO BRANCH COMPLETION WITHOUT FRESH VERIFICATION AND AN EXPLICIT INTEGRATION CHOICE`

Do not merge, push, or discard work on autopilot.

## Step 1: Verify Before Offering Completion Paths

Before discussing next steps:

1. verify the relevant tests or checks
2. confirm the diff is coherent
3. review whether docs or README updates are required

If verification fails, stop here and fix that first.

## Step 2: Determine the Base and Current State

Identify:

- current branch
- intended base branch
- whether you are on a feature branch or directly on `main`
- whether there are unrelated local changes you should not touch

## Step 3: Present Explicit Completion Options

When appropriate, present clear options instead of asking an open-ended
question. The reference pattern is:

1. Merge back locally
2. Push and create a PR
3. Keep the branch as-is for later
4. Discard the work

If the repository state differs, present the nearest equivalent choices just as
explicitly.

## Step 4: Execute the Chosen Path Carefully

- Merge or push only after verification.
- Never discard work without explicit confirmation.
- Never force-push unless the user explicitly asks.
- Re-run relevant checks if the merge result materially changes the state.

## Step 5: Cleanup

- remove only the branch or worktree state that should actually be cleaned up
- preserve anything the user wants to keep
- do not revert unrelated changes you did not make

## Red Flags

- offering completion options before verification
- open-ended "what next?" instead of explicit choices
- discarding work without confirmation
- force-pushing without an explicit request
- cleaning up branch or worktree state the user still needs

## Guardrails

- Do not rewrite history or revert unrelated user changes.
- Do not add cleanup-only churn at the end of a branch unless it is necessary
  for correctness.

## Required Outputs

- what was verified
- what integration option was chosen
- what was executed
- what remains open, if anything
- cleanup status
