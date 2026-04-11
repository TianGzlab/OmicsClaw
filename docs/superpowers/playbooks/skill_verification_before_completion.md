# skill_verification_before_completion

Use this playbook before declaring a task complete.

## Overview

Claiming completion without fresh verification evidence is not efficiency. It
is an accuracy failure.

Core principle: evidence before claims.

## Iron Law

`NO COMPLETION CLAIMS WITHOUT FRESH VERIFICATION EVIDENCE`

If you have not run the proving command or inspection for this task, you are
not ready to say it is done, fixed, or passing.

## Gate Function

Before any success claim:

1. Identify what command or inspection proves the claim.
2. Run it now, not from memory.
3. Read the output and exit status carefully.
4. Confirm whether the evidence actually supports the claim.
5. Only then describe the status.

## What Different Claims Require

- "Tests pass" requires fresh test output showing the relevant tests passed.
- "Bug fixed" requires reproducing the original symptom and showing it no
  longer fails.
- "Build succeeds" requires a successful build command, not just lint.
- "Docs are correct" requires direct inspection of the edited docs, links, and
  referenced paths.
- "Artifact exists" requires checking the generated file or output directly.

## OmicsClaw Adaptation

For this repository:

1. Run the narrowest meaningful verification for the changed behavior.
2. If the change is risky or cross-cutting, run at least one broader check.
3. For docs or process changes, inspect the exact files and link targets.
4. For skill or CLI changes, verify the observable contract, not just internal
   code paths.
5. For reports or outputs, inspect the generated artifacts directly.

## Red Flags

- "should work now"
- "probably fixed"
- "looks good"
- committing or pushing before verification
- relying on older runs
- relying on someone else's or another agent's success report
- checking only part of what the claim implies

## Reporting Standard

- state what you ran or inspected
- state the result
- state what remains unverified
- state residual risks or gaps
- never imply success beyond what the evidence proves

## Required Outputs

- the exact command or inspection used as proof
- the observed result
- the specific claim that result supports
- any unverified areas or remaining risks
