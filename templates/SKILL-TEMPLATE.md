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
    # Keep this list small and intentional.
    # Prefer unprefixed flags only for true wrapper-level controls shared across
    # methods, such as --method, --species, --fdr-threshold, --n-top-genes.
    # If a flag only affects one method, prefix it with the method name:
    # --morans-n-neighs, --harmony-theta, --cellrank-n-states, etc.
    allowed_extra_flags:
      - "--method"
      - "--species"
    legacy_aliases: [short-alias]
    saves_h5ad: false
    requires_preprocessed: false
    # Strongly recommended for multi-method skills.
    # Rules:
    # 1. one block per method
    # 2. defaults must match actual wrapper/runtime behavior
    # 3. requires should name concrete state/dependencies, not vague prose
    # 4. tips should only cover truly important first-pass tuning knobs
    # 5. wrapper-only controls are allowed, but label them honestly in the body
    param_hints:
      method_name:
        priority: "param_a -> param_b"
        params: ["param_a", "param_b"]
        defaults: {param_a: 1.0, param_b: 10}
        requires: ["obsm.spatial"]
        tips:
          - "--param-a: First tuning knob to adjust."
          - "--param-b: Secondary control for stability or granularity."
---

# 🔬 Skill Name

You are **[Skill Name]**, a specialized OmicsClaw agent for [omics domain]. Your
role is to [core function in one sentence].

## Why This Exists

- **Without it**: Users must [painful manual process or complex scripting]
- **With it**: [Automated outcome in seconds/minutes with standardized output]
- **Why OmicsClaw**: [What makes this better, grounded in actual algorithms, databases, or tooling]

## Core Capabilities

1. **Capability 1**: [Primary analysis function]
2. **Capability 2**: [Secondary analysis or validation]
3. **Capability 3**: [Output generation or downstream integration]
4. **Standard output layer**: [Canonical figures / tables / annotated object]
5. **Reproducibility layer**: [Notebook, commands, requirements, figure-ready exports]

## Input Formats

| Format | Extension | Required Fields / Structure | Example |
|--------|-----------|-----------------------------|---------|
| Primary format | `.ext` | Required fields/structure | `example.ext` |
| Alternative format | `.ext2` | Required fields/structure | `example.ext2` |
| Demo | n/a | `--demo` flag | Built-in demo data |

## Data / State Requirements

Use this section to document the real wrapper assumptions, especially if the
skill is multi-method or stateful.

| Requirement | Where it should exist | Why it matters |
|-------------|------------------------|----------------|
| Spatial / feature coordinates | `obsm["spatial"]` / file column / metadata field | Needed for neighborhood, distance, or plotting |
| Raw counts or primary matrix | `layers["counts"]` / matrix file / assay | Needed for count-aware methods |
| Normalized representation | `adata.X` / normalized matrix / transformed assay | Needed for methods expecting transformed expression |
| Embedding / graph / cluster state | `obsm["X_pca"]`, `uns["neighbors"]`, `obs["cluster"]`, etc. | Needed for downstream inference or visualization |

Remove rows that do not apply, and replace the AnnData examples with the real
data objects used by the skill.

If different methods require different matrix representations or prerequisites,
document that explicitly in a method-by-method table.

## Workflow

1. **Load**: Detect input format and load data or analysis state.
2. **Validate**: Check required fields, structures, dependencies, and method-specific prerequisites.
3. **Run method**: Execute the selected method or the default wrapper path.
4. **Persist results**: Write core outputs into stable structures such as `adata.obs`, `adata.obsm`, `adata.uns`, or standard tables.
5. **Visualize / summarize**: Generate the canonical figure gallery and export figure-ready data when applicable.
6. **Report**: Write `README.md`, `report.md`, `result.json`, and the reproducibility bundle.

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

| Parameter | Default | Description |
|-----------|---------|-------------|
| `parameter_name` | `default_value` | [purpose and source reference] |
| `another_param` | `value` | [rationale from paper, docs, or wrapper design] |

> **Current OmicsClaw behavior**: [Call out any wrapper-specific limitation,
> fallback path, persistence rule, or deviation from the upstream method so the
> document matches what the code actually does today.]

> **Parameter design note**: only expose truly important method knobs. If a
> parameter is a wrapper-level control rather than an upstream public API
> parameter, state that explicitly.

## Visualization Contract

Use this section whenever the skill writes figures.

OmicsClaw now treats visualization as a layered contract:

1. **Python standard gallery**: the canonical result layer users should inspect first.
2. **Figure-ready exports**: `figure_data/` tables for downstream customization.
3. **Optional R customization layer**: a styling/publication layer that consumes
   `figure_data/` and should not recompute the scientific result.

If useful, document gallery roles such as:

- `overview`: main result maps or summary plots
- `diagnostic`: score, QC, or method-behavior plots
- `supporting`: additional ranking or comparison figures
- `uncertainty`: confidence, entropy, or significance-distribution plots

If the skill has no plotting layer, remove this section together with
`figure_data/`, `r_visualization/`, and the related reproducibility helper.

## Output Structure

Remove lines that do not apply, but keep `README.md`, `report.md`,
`result.json`, and `reproducibility/` whenever the skill supports standard
OmicsClaw outputs.

```text
output_directory/
├── README.md
├── report.md
├── result.json
├── processed.h5ad
├── figures/
│   ├── plot.png
│   ├── custom/
│   │   └── publication_plot.png
│   └── manifest.json
├── tables/
│   └── results.csv
├── figure_data/
│   ├── data.csv
│   └── manifest.json
├── r_visualization/
│   ├── README.md
│   └── publication_template.R
└── reproducibility/
    ├── analysis_notebook.ipynb
    ├── commands.sh
    ├── requirements.txt
    └── r_visualization.sh
```

### Output Files Explained

- `README.md`: Human-friendly navigation file describing what ran and what to inspect first.
- `report.md`: Narrative report with findings, parameters, caveats, and follow-up suggestions.
- `result.json`: Machine-readable summary for downstream automation.
- `processed.h5ad`: Output object with new annotations when this skill writes AnnData.
- `figures/`: Canonical quick-look visual summaries for standard OmicsClaw interpretation.
- `figures/manifest.json`: Machine-readable catalog of generated figures and their roles.
- `tables/`: Structured tabular outputs for downstream analysis.
- `figure_data/`: Plot-ready exports for custom visualization without recomputing the science.
- `figure_data/manifest.json`: Inventory of exported plotting tables and their intended use.
- `r_visualization/`: Optional publication-style templates that consume `figure_data/`.
- `reproducibility/analysis_notebook.ipynb`: Notebook for code inspection and reruns.
- `reproducibility/commands.sh`: Minimal shell rerun command with the same core parameters.
- `reproducibility/requirements.txt`: Package snapshot for the current environment.
- `reproducibility/r_visualization.sh`: Optional entrypoint for reproducing the R plotting layer.

## Reproducibility Contract

Document the intended reproducibility behavior clearly.

- Normal `oc run` execution, conversational execution, and bot execution should
  produce the same core reproducibility bundle whenever the wrapper succeeds.
- If the skill supports a notebook output, `analysis_notebook.ipynb` should not
  be limited to `/research` or multi-agent mode only.
- Figures should be generated from persisted results, not only from transient
  local variables created during method execution.

## Knowledge Companions

If this skill has additional guidance documents, link them here.

- `knowledge_base/knowhows/KH-<skill>-guardrails.md`: Short injected rules for
  method choice, interpretation, and common mistakes.
- `knowledge_base/skill-guides/<domain>/<skill>.md`: Longer implementation-aware
  method guide for tuning, comparison, and troubleshooting.

Use this section to clarify boundary:

- `SKILL.md` describes the execution contract
- guardrails provide short prompt-safe operational reminders
- skill guides provide longer tuning and interpretation guidance

## Dependencies

**Required**:

- `package_name` >= version - [purpose in the analysis pipeline]
- `another_package` >= version - [specific functionality provided]

**Optional**:

- `optional_package` - [enhanced feature, graceful degradation without it]

## Safety

- **Local-first**: All data processing occurs locally without external upload.
- **Disclaimer**: Every report includes the OmicsClaw research tool disclaimer.
- **Audit trail**: All operations are logged into the reproducibility bundle.
- **Data preservation**: Original data structures should remain recoverable in output artifacts.
- **Current behavior over paper claims**: Document the wrapper's real implementation, not only the upstream method description.
- **No silent fabrication**: Do not imply that missing biological state was inferred if it was actually absent.
- **No silent method swapping**: Do not describe one method as if another method ran under the hood.

## Integration with Orchestrator

**Trigger conditions**:

- File patterns: [e.g. `.h5ad`, `.vcf`, `.mzML`]
- Keywords: [trigger words from frontmatter]
- User intent: [natural language patterns]

**Chaining partners**:

- `upstream-skill`: [What it provides to this skill]
- `downstream-skill`: [What this skill provides to it]

## Citations

- [Tool / Paper Name](URL) - [what it provides to this skill]
- [Database / Resource](URL) - [data or methodology source]

## Maintainer Notes

Remove this section if you do not want it in the final skill document, but use
it while authoring the skill.

1. Keep common wrapper parameters unprefixed, and prefix method-specific parameters.
2. Expose only core parameters that are actually implemented and worth user control.
3. Make sure `param_hints.defaults` matches real runtime defaults.
4. Persist core results before calling figure generation.
5. Prefer a canonical Python gallery plus optional `figure_data/` and R styling layers.
6. If the skill grows new methods later, update `allowed_extra_flags`, `param_hints`,
   parser arguments, backend defaults, output keys, knowledge docs, and tests together.
