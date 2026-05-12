# ADR: Inject SKILL.md `## Gotchas` into the runtime LLM context

**Date:** 2026-05-11
**Status:** Proposed
**Affects:** `omicsclaw/runtime/context_layers/__init__.py:316` (`load_skill_context`), `omicsclaw/core/registry.py` (parser), SKILL.md authoring contract

## Decision

When the runtime selects a skill, `load_skill_context()` appends a `## Known pitfalls (from SKILL.md Gotchas)` block to the prefetched skill context, listing the lead sentence of every Gotcha bullet (Phase 1: all Gotchas, no method-based filtering). Whether to add Phase 2 method-based filtering is data-driven, gated on telemetry showing P90 injected token count > 500 or the worst skill > 800 tokens.

## Why

The empirical state of the runtime: `load_skill_context()` reads `description`, `legacy_aliases`, `param_hints` keys, `requires_preprocessed`, `saves_h5ad`, and nearby alternatives — but **does not read SKILL.md body**, including the Gotchas section. Per Perplexity's framework, Gotchas are "the highest-value content" — the empirically-acquired traps the agent would otherwise reinvent, anchored to specific code lines. They are also the section the project has invested most carefully in (lint enforces `<file>.py:LINE` anchoring at `scripts/skill_lint.py:_check_gotchas_anchors`). Today these traps benefit only PR reviewers; the agent that actually runs the skill is blind to them. The "Gotchas Flywheel" Perplexity describes — failure → add Gotcha → next user benefits — is broken at step 3 in this architecture.

## Considered

- **Have the agent `Read` SKILL.md as a tool call when needed.** Rejected: adds a tool-call round-trip; the agent has to know to ask; defeats the purpose of prefetched context; Gotchas are the always-needed-by-default content, not the conditionally-needed reference material.
- **Inject the entire SKILL.md body, not just Gotchas.** Rejected: most body sections (Flow, Inputs & Outputs, Key CLI) are README content for humans and not the highest-leverage tokens; Gotchas alone gives the Pareto-optimal slice.
- **Surface gotchas at runtime via script error messages / try-catch warnings only.** Rejected: gotchas like "paired design auto-activates when ≥2 samples" are interpretation guidance that fires before the script knows whether the run is OK — they need to be in the agent's planning context, not the script's epilogue.
- **Phase 1 with method-based filtering from the start.** Rejected as premature optimisation: requires tagging every Gotcha with applicable methods across 89 skills, plus query → method inference logic, before knowing whether unfiltered injection is actually too noisy.

## Consequences

- Gotchas become runtime capability, not just documentation — the lint rule that every Gotcha lead sentence "must state the trap" stops being style guidance and becomes contract.
- Token cost: estimated 240 tokens for spatial-de's 6 gotchas; for outlier skills (`spatial-statistics` with 10 methods, `spatial-deconv` with 8) injection may approach the 5K body budget. Telemetry (logged per `load_skill_context()` call: skill, gotcha count, total tokens) gates the Phase 2 decision.
- Phase 2 (deferred, data-driven): if telemetry triggers, Gotcha bullets gain optional `[methods: X, Y]` tags; lint requires that skills exposing ≥3 methods have ≥half of Gotchas tagged; `load_skill_context()` filters by `selected_method` (parsed from query or `--method` flag).
- Gotchas Flywheel closes: each appended Gotcha now reaches the next agent invocation, not just the next code reviewer.
