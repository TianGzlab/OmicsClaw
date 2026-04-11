# skill_systematic_debugging

Use this playbook for any bug, regression, test failure, build failure,
performance regression, or unexpected behavior before proposing fixes.

## Overview

Random fixes waste time, hide the real cause, and often create new bugs.

Core principle: find the root cause before attempting a fix. Symptom fixes are
not debugging.

## Iron Law

`NO FIXES WITHOUT ROOT CAUSE INVESTIGATION FIRST`

If Phase 1 is incomplete, you are not ready to propose a fix.

## When To Use

Use for:

- failing tests
- runtime errors
- wrong outputs
- missing artifacts
- integration failures
- performance regressions
- "this should work" situations where the reason is not proven

Use this especially when:

- the bug looks obvious
- you are under time pressure
- a quick patch is tempting
- you already tried one or more fixes
- the previous fix did not work

## The Four Phases

### Phase 1: Root Cause Investigation

Before attempting any fix:

1. Read the full error, warning, traceback, and command output carefully.
2. Reproduce the failure with exact steps, inputs, and environment.
3. Check recent changes that could explain the breakage.
4. For multi-component paths, instrument the boundaries and identify where the
   failure actually begins.
5. Trace bad data or state backward through the call chain until you find the
   original trigger.

OmicsClaw-specific reminders:

- Check the relevant `SKILL.md`, `README.md`, registry logic, and output
  contract before patching wrappers or prompts.
- For CLI -> registry -> skill -> report paths, verify each boundary rather
  than guessing at the final symptom.
- For generated artifacts, inspect the actual output directory contents before
  changing code.

### Phase 2: Pattern Analysis

1. Find working examples in the same codebase.
2. Compare broken behavior against a known-good pattern or implementation.
3. List concrete differences.
4. Understand dependencies, assumptions, and environment requirements.

### Phase 3: Hypothesis and Testing

1. State one specific hypothesis for the root cause.
2. Test that hypothesis with the smallest possible change or probe.
3. Verify the result before stacking additional fixes.
4. If the hypothesis fails, return to investigation instead of piling on more
   changes.

### Phase 4: Implementation

1. Create or identify a failing reproduction, preferably as an automated test.
2. Implement one fix aimed at the proven root cause.
3. Re-run the minimal failing case first.
4. Run the broader affected verification after the targeted fix works.
5. If multiple fixes fail in a row, question the architecture before trying
   more patches.

## Red Flags

Stop and reset if you notice any of these:

- "I'll just try this quick fix"
- "It is probably that line"
- changing multiple things before reproducing
- fixing where the error appears without tracing where it started
- skipping logs, stack traces, or failing output
- retrying the same action without new evidence

## Required Outputs

- the exact failing symptom
- the proven root cause
- the minimal fix that addresses that cause
- regression coverage when practical
- fresh verification evidence
