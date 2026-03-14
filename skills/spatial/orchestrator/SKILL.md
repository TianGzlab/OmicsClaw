---
name: spatial-orchestrator
description: >-
  Query routing and pipeline orchestration for SpatialClaw skills.
version: 0.1.0
author: SpatialClaw Team
license: MIT
tags: [spatial, orchestrator, routing, pipeline]
metadata:
  omicsclaw:
    domain: spatial
    requires:
      bins:
        - python3
      env: []
      config: []
    emoji: "🎯"
    homepage: https://github.com/SpatialClaw/SpatialClaw
    os: [macos, linux]
    install:
      - kind: pip
        package: scanpy
        bins: []
    trigger_keywords:
      - which skill
      - route query
      - what should I run
      - orchestrate
      - pipeline
---

# 🎯 Spatial Orchestrator

You are **Spatial Orchestrator**, the meta-skill that routes user queries to the correct OmicsClaw analysis skill and orchestrates multi-step pipelines. You never perform analysis yourself — you dispatch to the right specialist.

## Why This Exists

- **Without it**: Users must know skill names and CLI flags to run analyses
- **With it**: Natural language queries are automatically matched to the correct skill
- **Why OmicsClaw**: Single entry point for all spatial analysis capabilities

## Workflow

1. **Calculate**: Determine optimal routing matching input signatures.
2. **Execute**: Dispatch execution to chosen analysis module.
3. **Assess**: Monitor dispatch completion success.
4. **Generate**: Output structured logs encapsulating orchestrations.
5. **Report**: Aggregate execution status.

## Core Capabilities

1. **Keyword routing**: Match user query text to the best skill via KEYWORD_MAP
2. **File type routing**: Match input file extension to default skill via EXTENSION_MAP
3. **Pipeline chains**: Execute multi-skill pipelines (e.g. preprocess → domains → de → genes → statistics)
4. **Skill listing**: Show all available skills with status

## Routing Maps

### KEYWORD_MAP — query text → skill

| Keywords | Skill |
|----------|-------|
| spatial domain, tissue region, niche | spatial-domains |
| cell type annotation | spatial-annotate |
| deconvolution, cell proportion | spatial-deconv |
| spatial autocorrelation, moran | spatial-statistics |
| spatially variable gene | spatial-genes |
| differential expression, marker gene | spatial-de |
| condition comparison, pseudobulk | spatial-condition |
| ligand receptor, cell communication | spatial-communication |
| rna velocity | spatial-velocity |
| trajectory, pseudotime | spatial-trajectory |
| enrichment, gsea, pathway | spatial-enrichment |
| cnv, copy number | spatial-cnv |
| integration, batch correction | spatial-integrate |
| registration, alignment | spatial-register |

### EXTENSION_MAP — file type → default skill

| Extension | Skill |
|-----------|-------|
| .h5ad | spatial-preprocess |
| .h5 | spatial-preprocess |
| .zarr | spatial-preprocess |

## CLI Reference

```bash
# Route a text query
python skills/spatial-orchestrator/spatial_orchestrator.py \
  --query "find spatially variable genes" --output <dir>

# Route by file type
python skills/spatial-orchestrator/spatial_orchestrator.py \
  --input <data.h5ad> --output <dir>

# Run a named pipeline
python skills/spatial-orchestrator/spatial_orchestrator.py \
  --pipeline standard --input <data.h5ad> --output <dir>

# List all skills
python skills/spatial-orchestrator/spatial_orchestrator.py --list-skills

# Demo
python skills/spatial-orchestrator/spatial_orchestrator.py --demo --output /tmp/orch_demo
```

## Output Structure

```
output_directory/
├── report.md          # Routing decision + dispatched skill output summary
├── result.json        # Structured routing result
└── reproducibility/
    ├── commands.sh
    ├── environment.yml
    └── checksums.sha256
```

## Integration

The orchestrator does NOT run analysis itself. It:
1. Determines the best skill for the user's request
2. Returns the recommended command
3. Optionally dispatches to the skill via `omicsclaw.py run <skill>`
