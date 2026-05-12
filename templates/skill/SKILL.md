---
name: skill-template
description: Load when copying this directory to bootstrap a new OmicsClaw v2 skill (rename, fill in, then `git add`). Skip when an existing skill already covers the request.
version: 0.1.0
author: OmicsClaw
license: MIT
tags:
- template
- scaffold
- v2
---

<!--
Authoring checklist (delete this comment block before committing):

  1. Rename: copy this directory, rename `replace_me.py` and the `tests/`
     file, update frontmatter `name`, `parameters.yaml::script`.
  2. Fill: `description` (≤50 words, "Load when … Skip when …"), the six
     `##` sections below, and the three `references/*.md` stubs.
  3. Implement: replace the synthetic-CSV demo in the script with real I/O.
  4. Verify: `python scripts/generate_parameters_md.py <skill_dir>` then
     `python scripts/skill_lint.py <skill_dir>` then `pytest tests/`.

Full usage notes, lint rules, and soft conventions live in
`templates/skill/README.md`.
-->

# REPLACE_SKILL_NAME

## When to use

<!--
One short paragraph (3-6 lines).  Mirror the frontmatter description
("Load when … Skip when …") and explicitly call out the closest adjacent
skill so the agent knows when to redirect.
-->

The user has `<input shape>` and wants `<output shape>`.  Pick this skill
when `<distinguishing condition>`.  For `<adjacent capability>` use
`<sibling-skill>` instead.

## Inputs & Outputs

<!--
One row per format.  Detailed schema lives in `references/output_contract.md`
— do NOT duplicate column-by-column tables here.
-->

| Input | Format | Required |
|---|---|---|
| Primary input | `<.h5ad / .csv / .vcf / …>` | yes (unless `--demo`) |

| Output | Path | Notes |
|---|---|---|
| Primary table | `tables/<name>.csv` | one row per `<unit>` |
| Report | `report.md` + `result.json` | always |

## Flow

<!--
3-7 numbered steps, present-tense, anchor each to a `<file>.py:LINE` if it
helps reviewers verify the contract.  Don't recapitulate idiomatic Python.
-->

1. Load input (`--input <file>`) or generate a demo (`--demo`).
2. Validate required columns / `obs[X]` keys; raise `ValueError(...)` early.
3. Run the chosen `--method` backend.
4. Write `tables/<name>.csv` (`<script>.py:<L>`) + `report.md` + `result.json`.

## Gotchas

<!--
Empirically the highest-leverage section.  Each bullet should:
  * State the trap in the lead sentence.
  * Anchor to a code line (`<file>.py:LINE`) or output filename — lint at
    `scripts/skill_lint.py::_check_gotchas_anchors` enforces this.
  * Explain WHY (the reason the trap exists), not just WHAT.

Skip obvious things — Python-101 advice or framework-standard behaviour.
The bar is "would the agent get this wrong without this instruction?".
-->

- _None yet — append as failure modes are reported._

## Key CLI

```bash
# Demo
python omicsclaw.py run REPLACE_SKILL_NAME --demo --output /tmp/REPLACE_SKILL_NAME_demo

# Real input
python omicsclaw.py run REPLACE_SKILL_NAME \
  --input <data.ext> --output results/ \
  --method <method-name>
```

## See also

- `references/parameters.md` — every CLI flag, per-method tunables
- `references/methodology.md` — the WHY behind the algorithm
- `references/output_contract.md` — `tables/X.csv` + `result.json` schema
- Adjacent skills: `<sibling-1>` (upstream), `<sibling-2>` (parallel), `<sibling-3>` (downstream)
