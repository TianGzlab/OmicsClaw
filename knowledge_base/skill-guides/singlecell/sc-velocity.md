---
doc_id: skill-guide-sc-velocity
title: OmicsClaw Skill Guide — SC Velocity
doc_type: method-reference
domains: [singlecell]
related_skills: [sc-velocity]
search_terms: [RNA velocity, scVelo, stochastic, dynamical, steady_state, latent time, tuning]
priority: 0.8
---

# OmicsClaw Skill Guide — SC Velocity

**Status**: implementation-aligned guide derived from the current OmicsClaw
`sc-velocity` skill. This guide explains the current wrapper surface around
scVelo modes without pretending the full scVelo API is exposed.

## Purpose

Use this guide when you need to decide:
- whether the input is genuinely velocity-ready
- which scVelo mode is appropriate
- how to explain latent time honestly

## Step 1: Inspect The Data First

Key properties to check:
- **Required layers**:
  - `layers["spliced"]`
  - `layers["unspliced"]`
- **Upstream state**:
  - preprocessed / graph-ready data is preferred
- **Scientific question**:
  - directionality only
  - full dynamical interpretation with latent time

Important implementation notes in current OmicsClaw:
- public methods are `scvelo_stochastic`, `scvelo_dynamical`, and `scvelo_steady_state`
- `--mode` is a public alias for the same backend selection
- `latent_time` should not be promised outside the dynamical path

## Step 2: Pick The Method Deliberately

| Method | Best first use | Strong starting parameters | Main caveat |
|--------|----------------|----------------------------|-------------|
| **scvelo_stochastic** | Standard first-pass velocity visualization | `n_jobs` | No guarantee of latent time |
| **scvelo_dynamical** | When users explicitly want latent-time-style interpretation | `n_jobs` | Requires stronger modeling assumptions |
| **scvelo_steady_state** | Simpler steady-state approximation path | `n_jobs` | More limited than dynamical modeling |

## Step 3: Always Show A Parameter Summary Before Running

```text
About to run RNA velocity
  Method: scvelo_dynamical
  Parameters: n_jobs=4
  Note: latent time is only expected on the dynamical path and still depends on successful dynamics recovery.
```

## Step 4: Method-Specific Tuning Rules

Tune in this order:
1. `method` / `mode`
2. `n_jobs`

Guidance:
- choose the mode before touching runtime controls
- use `stochastic` as the safest first-pass default
- use `dynamical` when the user specifically wants stronger temporal interpretation

Important warnings:
- do not expose `recover_dynamics` internals as if they were current public wrapper parameters
- do not promise latent time for every velocity run
- do not imply arbitrary scVelo options are available just because upstream scVelo documents them

## Step 5: What To Say After The Run

- If latent time is missing: explain that the selected mode or model fit may not support it.
- If velocity plots look noisy: mention input-layer quality and upstream preprocessing before blaming mode choice.
- If users ask for more scVelo knobs: state clearly that the current wrapper exposes only a narrow control surface.

## Step 6: Explain Outputs Using Method-Correct Language

- describe velocity stream / embedding plots as directional summaries on the chosen embedding
- describe velocity magnitude as a heuristic summary, not a direct biological rate constant
- describe latent time only as a dynamical-model-derived quantity

## Official References

- https://scvelo.readthedocs.io/en/stable/scvelo.tl.velocity.html
- https://scvelo.readthedocs.io/en/stable/scvelo.tl.recover_dynamics.html
- https://scvelo.readthedocs.io/en/stable/VelocityBasics.html
- https://scvelo.readthedocs.io/en/stable/DynamicalModeling.html
