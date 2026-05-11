---
name: skill-template
description: Load when copying this directory to bootstrap a new OmicsClaw v2 skill (rename, fill in, then `git add`). Skip when migrating an existing legacy skill — use `scripts/migrate_skill.py` instead, which generates the same layout from the legacy SKILL.md.
version: 0.1.0
author: OmicsClaw
license: MIT
tags:
- template
- scaffold
- v2
requires:
- pyyaml
---

<!--
AUTHORING GUIDE — read once, then delete this comment block.

This scaffold is the canonical v2 OmicsClaw skill skeleton.  It is consumed by:
  * humans copying this dir to start a new skill
  * `omics-skill-builder` (programmatic scaffolder)
  * `scripts/migrate_skill.py` (legacy → v2 migrator)

Filling-in checklist (loosely follows Perplexity's skill-design framework):

1. **Description** is the most important field.  It is the routing trigger
   read by every agent invocation, NOT documentation.
   - Format: "Load when <user intent / data shape>. Skip when <neighbouring
     skill / wrong input>."
   - Hard cap: 50 words (lint-enforced).
   - Mirror real user queries, not workflow summaries.

2. **Body** is loaded into context every time an agent picks this skill.
   - Hard cap: 200 lines (lint-enforced).  Conditional / heavy logic belongs
     in `references/*` (lazy-loaded).
   - "Skip the obvious" — only document things the agent would otherwise get
     wrong.  If removing a sentence wouldn't confuse a future reader, drop it.
   - Every Gotcha bullet should anchor a code reference (`<file>.py:LINE` or
     `result.json[X]` or `tables/X.csv`) — the lint at
     `scripts/skill_lint.py:_check_gotchas_anchors` enforces this.

3. **Gotchas Flywheel** — append-mostly maintenance.  When a reviewer or
   user reports a failure mode, add a Gotcha bullet.  Don't lengthen
   existing instructions; let gotchas accrue value over time.
-->

# REPLACE_SKILL_NAME

## When to use

<!--
Replace this with one short paragraph (3-6 lines).  Mirror the frontmatter
`description` ("Load when… Skip when…") and explicitly call out the closest
adjacent skill so the agent knows when to redirect.
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
  * Anchor to a code line (`<file>.py:LINE`) or output filename.
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
