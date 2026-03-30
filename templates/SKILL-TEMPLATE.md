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
    domain: spatial|singlecell|genomics|proteomics|metabolomics|bulkrna|orchestrator
    requires:
      bins:
        - python3
      env: []
      config: []
    emoji: "🔬"
    homepage: https://github.com/TianGzlab/OmicsClaw
    os: [macos, linux]
    install:
      - kind: pip
        package: scanpy
        bins: []
    trigger_keywords:
      - keyword that routes to this skill
      - another trigger phrase
    allowed_extra_flags:
      - "--method"
      - "--species"
    legacy_aliases: [short-alias]
    saves_h5ad: false
    requires_preprocessed: false
    # Optional but strongly recommended for multi-method skills.
    # Keep these defaults synced with current CLI/runtime behavior, not just paper defaults.
    param_hints:
      method_name:
        priority: "param_a → param_b"
        params: ["param_a", "param_b"]
        defaults: {param_a: 1.0, param_b: 10}
        requires: ["obsm.spatial"]
        tips:
          - "--param-a: First tuning knob to adjust."
          - "--param-b: Secondary control for stability or granularity."
---

# 🔬 Skill Name

You are **[Skill Name]**, a specialized OmicsClaw agent for [omics domain]. Your role is to [core function in one sentence].

## Why This Exists

- **Without it**: Users must [painful manual process or complex scripting]
- **With it**: [Automated outcome in seconds/minutes with standardized output]
- **Why OmicsClaw**: [What makes this better, grounded in actual algorithms, databases, or tooling]

## Core Capabilities

1. **Capability 1**: [Primary analysis function]
2. **Capability 2**: [Secondary analysis or validation]
3. **Capability 3**: [Output generation or downstream integration]

## Input Formats

| Format | Extension | Required | Example |
|--------|-----------|----------|---------|
| Primary format | `.ext` | Required fields/structure | `example.ext` |
| Alternative format | `.ext2` | Required fields/structure | `example.ext2` |
| Demo | n/a | `--demo` flag | Built-in demo data |

## Workflow

1. **Load**: Detect input format and load data
2. **Validate**: Check required fields, structure, and data quality
3. **Process**: Run the core computation or selected method
4. **Visualize / Summarize**: Generate figures, tables, or intermediate annotations
5. **Report**: Write `README.md`, `report.md`, and a reproducibility bundle with rerun artifacts

## CLI Reference

```bash
# Standard usage
oc run <skill-alias> --input <input_file> --output <report_dir>

# Demo mode
oc run <skill-alias> --demo --output /tmp/demo

# Optional method-specific example
oc run <skill-alias> --input <file> --method <method_name> --output <dir>

# Direct script entrypoint
python skills/<domain>/<skill-name>/<script>.py \
  --input <input_file> --output <report_dir> [--options]

# Note: `oc run` and `python omicsclaw.py run` are equivalent entrypoints
python omicsclaw.py run <skill-alias> --input <file> --output <dir>
```

## Example Queries

- "Example user query that would route to this skill"
- "Another natural language request this skill handles"
- "Third example showing different phrasing"

## Algorithm / Methodology

Use one subsection per major method if the skill supports multiple backends.

### Method Name (or Default Path)

1. **Step 1**: [Detailed description with specific function or method]
2. **Step 2**: [Processing step with parameters]
3. **Step 3**: [Output generation]

**Key parameters**:
- `parameter_name`: default_value — [purpose and source reference]
- `another_param`: value — [rationale from paper/tool]

> **Current OmicsClaw behavior**: [Call out any wrapper-specific limitation,
> simplification, fallback path, or deviation from the upstream paper/tool so
> the document matches what the code actually does today.]

## Output Structure

Remove lines that do not apply, but keep `README.md`, `report.md`, `result.json`,
and `reproducibility/` whenever the skill supports standard OmicsClaw outputs.

```text
output_directory/
├── README.md
├── report.md
├── result.json
├── processed.h5ad
├── figures/
│   └── plot.png
├── tables/
│   └── results.csv
└── reproducibility/
    ├── analysis_notebook.ipynb
    ├── commands.sh
    └── requirements.txt
```

### Output Files Explained

- `README.md`: Human-friendly output guide describing where to look first.
- `report.md`: Narrative report with findings, parameters, and follow-up suggestions.
- `result.json`: Machine-readable summary for downstream automation.
- `processed.h5ad`: Output object with new annotations when this skill writes AnnData.
- `figures/`: Ready-to-open visual summaries for quick inspection.
- `tables/`: Structured tabular outputs for downstream analysis.
- `reproducibility/analysis_notebook.ipynb`: Notebook for code inspection and reruns.
- `reproducibility/commands.sh`: Minimal shell rerun command with the same core parameters.
- `reproducibility/requirements.txt`: Package snapshot for the current environment.

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
- **Current behavior over paper claims**: Document the wrapper's real implementation, not only the upstream method description

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
