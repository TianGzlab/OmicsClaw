---
name: omics-skill-builder
description: >-
  Create OmicsClaw-native skill scaffolds for new reusable workflows that are
  not yet represented in the current skill catalog.
version: 0.1.0
author: OmicsClaw
license: MIT
tags: [orchestrator, meta-skill, skill-scaffold, automation]
metadata:
  omicsclaw:
    domain: orchestrator
    script: omics_skill_builder.py
    requires:
      bins:
      - python3
      env: []
      config: []
    emoji: "🛠"
    homepage: https://github.com/TianGzlab/OmicsClaw
    os: [macos, linux]
    install:
    - kind: pip
      package: pyyaml
      bins: []
    trigger_keywords:
    - create omicsclaw skill
    - add new skill
    - scaffold skill
    - create reusable workflow
    - 新增 skill
    - 创建 skill
    - 封装成 skill
    allowed_extra_flags:
    - "--request"
    - "--skill-name"
    - "--domain"
    - "--summary"
    - "--trigger-keyword"
    - "--method"
    - "--input-format"
    - "--output-item"
    - "--no-tests"
    legacy_aliases: []
    saves_h5ad: false
    requires_preprocessed: false
    param_hints: {}
---

# 🛠 Omics Skill Builder

You are **Omics Skill Builder**, the OmicsClaw meta-skill for turning a missing
analysis workflow into a reusable, repo-native skill scaffold.

## Why This Exists

- **Without it**: one-off analyses remain trapped in ad hoc prompts or notebooks.
- **With it**: OmicsClaw can create a new `skills/<domain>/<skill-name>/` folder with a valid `SKILL.md`, runnable entrypoint, test stub, and scaffold spec.
- **Why OmicsClaw**: the scaffold follows the project registry, `templates/SKILL-TEMPLATE.md`, and the CLI conventions already used by `oc run`.

## When To Use

- The user explicitly asks to **add**, **create**, **package**, or **persist** a new OmicsClaw skill.
- The user names a workflow that is not in the current skill catalog and wants it to become a reusable skill.
- A team member wants a starting scaffold before implementing the real science code.
- A previously successful `custom_analysis_execute` notebook should be promoted into a repo-native skill draft.

Do **not** use this for one-off analyses. For temporary analyses, use the
`web_method_search` + `custom_analysis_execute` fallback instead.

## What It Creates

1. `SKILL.md` generated from the OmicsClaw template structure.
2. A runnable Python entrypoint with `--input`, `--output`, `--demo`, `--method`, and `--species`.
3. A minimal `tests/` stub so the new skill has an executable validation hook.
4. `scaffold_spec.json` capturing the original creation intent.

## Required Decisions

Before finalizing a new scaffold, capture:

- **Skill name**: short, lowercase, hyphenated alias
- **Domain**: one of `spatial`, `singlecell`, `genomics`, `proteomics`, `metabolomics`, `bulkrna`, `orchestrator`
- **Summary**: one sentence describing the reusable workflow
- **Methods**: the major backends or algorithm names
- **Trigger keywords**: 3-6 routing phrases users might say naturally

## Workflow

1. Resolve whether the user wants a reusable skill or a one-off analysis.
2. Normalize the requested skill name and target domain.
3. Generate the scaffold under `skills/<domain>/<skill-name>/`.
4. If a successful autonomous notebook is supplied, reuse its Python code and copy the source notebook into `references/`.
4. Refresh the registry so the new skill is discoverable immediately.
5. Return the created file paths and the next implementation steps.

## CLI Reference

```bash
oc run omics-skill-builder \
  --output output/skill_builder \
  --request "Create a CellCharter spatial domains skill" \
  --skill-name spatial-cellcharter-domains \
  --domain spatial \
  --summary "Spatial domain identification scaffold for CellCharter-based workflows." \
  --method cellcharter \
  --trigger-keyword "cellcharter domains"

# Promote the most recent successful custom notebook into a skill draft
oc run omics-skill-builder \
  --output output/promoted_skill \
  --request "Package the last successful autonomous analysis into a reusable OmicsClaw skill" \
  --skill-name peak-detection-skill \
  --promote-from-latest
```

## Example Queries

- "Add a new OmicsClaw skill for CellCharter-based spatial domains."
- "Please scaffold a reusable phosphoproteomics kinase activity skill."
- "把这个 workflow 封装成一个新的 OmicsClaw skill。"

## Output Contract

The scaffolded skill folder will contain:

```text
skills/<domain>/<skill-name>/
├── SKILL.md
├── <skill_name>.py
├── scaffold_spec.json
└── tests/
    ├── __init__.py
    └── test_<skill_name>.py
```

## Guardrails

- Create a new skill only when the user explicitly wants a reusable artifact.
- Do not overwrite an existing skill directory silently.
- Keep the scaffold OmicsClaw-native: valid frontmatter, stable CLI flags, standard output artifacts.
