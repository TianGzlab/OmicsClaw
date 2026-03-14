---
name: your-skill-name
description: >-
  One-line description of what this omics analysis skill does.
version: 0.1.0
author: OmicsClaw
license: MIT
tags: [domain, analysis-type, method]
metadata:
  omicsclaw:
    domain: spatial|singlecell|genomics|proteomics|metabolomics
    requires:
      bins:
        - python3
      env: []
      config: []
    emoji: "🔬"
    homepage: https://github.com/OmicsClaw/OmicsClaw
    os: [macos, linux]
    install:
      - kind: pip
        package: scanpy
        bins: []
    trigger_keywords:
      - keyword that routes to this skill
      - another trigger phrase
---

# 🔬 Skill Name

You are **[Skill Name]**, a specialized OmicsClaw agent for [omics domain]. Your role is to [core function in one sentence].

## Why This Exists

- **Without it**: Users must [painful manual process or complex scripting]
- **With it**: [Automated outcome in seconds/minutes with standardized output]
- **Why OmicsClaw**: [What makes this better — grounded in real algorithms/databases/tools]

## Core Capabilities

1. **Capability 1**: [Primary analysis function]
2. **Capability 2**: [Secondary analysis or validation]
3. **Capability 3**: [Output generation or integration]

## Input Formats

| Format | Extension | Required | Example |
|--------|-----------|----------|---------|
| Primary format | `.ext` | Required fields/structure | `example.ext` |
| Alternative format | `.ext2` | Required fields/structure | `example.ext2` |
| Demo | n/a | `--demo` flag | Built-in demo data |

## Workflow

1. **Load**: Detect input format and load data
2. **Validate**: Check required fields and data quality
3. **Process**: [Core computation — algorithm/method used]
4. **Generate**: Write output files, figures, tables
5. **Report**: Write `report.md` with findings and reproducibility bundle

## CLI Reference

```bash
# Standard usage
python skills/<domain>/<skill-name>/<script>.py \
  --input <input_file> --output <report_dir> [--options]

# Demo mode
python skills/<domain>/<skill-name>/<script>.py --demo --output /tmp/demo

# Via OmicsClaw runner
python omicsclaw.py run <skill-alias> --input <file> --output <dir>
python omicsclaw.py run <skill-alias> --demo
```

## Example Queries

- "Example user query that would route to this skill"
- "Another natural language request this skill handles"
- "Third example showing different phrasing"

## Algorithm / Methodology

1. **Step 1**: [Detailed description with specific function/method]
2. **Step 2**: [Processing step with parameters]
3. **Step 3**: [Output generation]

**Key parameters**:
- `parameter_name`: default_value — [purpose and source reference]
- `another_param`: value — [rationale from paper/tool]

## Output Structure

```
output_directory/
├── report.md
├── result.json
├── processed.h5ad
├── figures/
│   └── plot.png
├── tables/
│   └── results.csv
└── reproducibility/
    ├── commands.sh
    ├── environment.yml
    └── checksums.sha256
```

## Dependencies

**Required** (in `requirements.txt`):
- `package_name` >= version — [purpose in analysis pipeline]
- `another_package` >= version — [specific functionality provided]

**Optional**:
- `optional_package` — [enhanced feature, graceful degradation without it]

## Safety

- **Local-first**: All data processing occurs locally without external upload
- **Disclaimer**: Every report includes the OmicsClaw research tool disclaimer
- **Audit trail**: All operations logged to reproducibility bundle
- **Data preservation**: Original data structures preserved in output

## Integration with Orchestrator

**Trigger conditions**:
- File patterns: [e.g., `.h5ad`, `.vcf`, `.mzML`]
- Keywords: [trigger words from frontmatter]
- User intent: [natural language patterns]

**Chaining partners**:
- `upstream-skill`: [What it provides to this skill]
- `downstream-skill`: [What this skill provides to it]

## Citations

- [Tool/Paper Name](URL) — [what it provides to this skill]
- [Database/Resource](URL) — [data or methodology source]
