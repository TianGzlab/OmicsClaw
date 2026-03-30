---
name: spatial-orchestrator
description: >-
  Route spatial transcriptomics requests to the most relevant OmicsClaw spatial
  skill, list the current spatial skill catalog, or run predefined multi-step
  spatial analysis pipelines with consistent canonical skill naming.
version: 0.2.0
author: OmicsClaw Team
license: MIT
tags: [spatial, orchestrator, routing, pipeline, workflow]
metadata:
  omicsclaw:
    domain: spatial
    script: spatial_orchestrator.py
    allowed_extra_flags:
      - "--demo"
      - "--input"
      - "--list-skills"
      - "--output"
      - "--pipeline"
      - "--query"
      - "--timeout"
    param_hints:
      routing:
        priority: "query or input → output"
        params: ["query", "input", "output"]
        defaults: {output: "required"}
        requires: ["registry.skill_catalog"]
        tips:
          - "--query: Route a natural-language spatial analysis request to the best matching spatial skill."
          - "--input: Route by input file extension when no natural-language query is provided."
          - "--output: Required for report/result exports in demo, query, file-routing, and pipeline modes."
      pipeline:
        priority: "pipeline → input → timeout"
        params: ["pipeline", "input", "timeout"]
        defaults: {timeout: 600}
        requires: ["named_pipeline", "input_file"]
        tips:
          - "--pipeline: Run one of the predefined spatial workflows such as standard, full, integration, spatial_only, or cancer."
          - "--input: Required for pipeline execution so processed.h5ad can be chained across steps."
          - "--timeout: Per-step subprocess timeout in seconds."
    legacy_aliases: []
    saves_h5ad: false
    requires_preprocessed: false
    requires:
      bins:
        - python3
      env: []
      config: []
    emoji: "🧭"
    homepage: https://github.com/TianGzlab/OmicsClaw
    os: [macos, linux]
    install:
      - kind: pip
        package: pyyaml
        bins: []
    trigger_keywords:
      - spatial routing
      - route spatial skill
      - spatial pipeline
      - spatial workflow
      - run spatial pipeline
      - choose spatial analysis
---

# Spatial Orchestrator

Use this skill to map a spatial transcriptomics request onto the most relevant
OmicsClaw spatial analysis skill, or to execute a predefined multi-step spatial
workflow while keeping the chained outputs and lineage reports organized.
