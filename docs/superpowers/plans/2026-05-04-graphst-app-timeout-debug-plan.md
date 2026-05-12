# Goal

Diagnose and fix why OmicsClaw App times out after 600 seconds when running
`spatial-domain-identification` with `method=graphst` on
`data/slideseqv2_mouse_hippocampus.h5ad`, even when the user requests GPU
acceleration and `epochs=1`.

# Scope and Non-Goals

- In scope:
  - prove the actual root cause(s) across App -> backend -> skill layers
  - fix parameter propagation so user-requested GraphST epochs reach the skill
  - fix GraphST platform/datatype routing for Slide-seq-style inputs
  - improve long-running skill progress streaming so the App does not hit a
    false idle/proxy timeout while work is still active
  - add targeted regression coverage and update repo docs
- Out of scope:
  - rewriting GraphST internals
  - introducing a new async job architecture for all skills
  - broad frontend redesign in OmicsClaw-App

# Key Assumptions and Constraints

- OmicsClaw App currently proxies `/chat/stream` with a 600s budget and expects
  ongoing SSE activity for long-running turns.
- The real backend runtime may differ from the current shell interpreter, so
  evidence must come from the interpreter actually running `oc app-server`.
- GraphST preprocessing/graph construction can dominate runtime before the
  actual training epochs start, especially on large Slide-seq-like datasets.

# File Map

- `docs/superpowers/plans/2026-05-04-graphst-app-timeout-debug-plan.md`
- `docs/superpowers/plans/README.md`
- `README.md`
- `omicsclaw/core/registry.py`
- `bot/core.py`
- `skills/spatial/spatial-domains/spatial_domains.py`
- `skills/spatial/_lib/domains.py`
- `skills/spatial/spatial-domains/tests/test_spatial_domains.py`

# Ordered Implementation Tasks

1. Capture root-cause evidence from the real app-server runtime.
   - Verify the actual Python interpreter used by `oc app-server`.
   - Inspect installed GraphST source to confirm how `epochs` and `datatype`
     are consumed.
   - Confirm the App/backend timeout boundary and whether SSE heartbeats exist.

2. Fix GraphST parameter propagation through the OmicsClaw tool/CLI path.
   - Allow `spatial-domain-identification` to receive epoch-related flags.
   - Ensure tool-level `n_epochs` can reach this skill as `--epochs`/`epochs`
     rather than being silently dropped.

3. Fix GraphST datatype handling for Slide-seq inputs.
   - Thread `data_type`/platform hints into `dispatch_method(...)` and
     `identify_domains_graphst(...)`.
   - Auto-detect Slide-seq-like inputs when the user did not pass an explicit
     platform hint.
   - Pass the resolved GraphST datatype into the upstream GraphST constructor.
   - Remove dead/incorrect references such as undefined `detected_datatype`.

4. Improve long-running skill progress visibility for App SSE consumers.
   - Stream subprocess stdout/stderr incrementally for `execute_omicsclaw(...)`
     instead of waiting only for process completion.
   - Preserve final exit handling and error aggregation.

5. Add regression coverage and update docs.
   - Add targeted tests for epoch/datatype propagation where practical.
   - Update `README.md` with the GraphST/App timeout fix and operational notes.
   - Update `docs/superpowers/plans/README.md`.

# Verification Strategy

- Static verification:
  - inspect the patched code paths for `n_epochs` -> `--epochs` forwarding
  - inspect GraphST wrapper code for resolved datatype propagation
- Automated verification:
  - targeted pytest for `spatial-domains` tests
  - any focused regression test covering CLI/tool argument forwarding
- Runtime verification:
  - run a narrow command using the real OmicsClaw environment to show the
    effective GraphST command line now includes the requested epoch value
  - if feasible, run a small or instrumented GraphST path to verify ongoing
    progress output arrives before completion

# Stop Conditions / Acceptance Criteria

- User-requested GraphST epoch settings are no longer silently ignored.
- Slide-seq/Slide-seqV2 inputs no longer default to the generic/10X GraphST
  graph-construction path when a better Slide path can be inferred.
- Long-running skill execution emits progress often enough that the App is not
  forced into a false “Backend stream timed out after 600 seconds” failure
  solely because the subprocess stayed silent.
- README and plan index are updated with the durable decision record.
