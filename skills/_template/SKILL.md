---
name: _template
description: Load when you need a starting point for a brand-new OmicsClaw v2 skill. Skip when migrating an existing skill (use scripts/migrate_skill.py instead).
version: 0.1.0
author: OmicsClaw Team
license: MIT
tags: [template, scaffold]
requires: [pyyaml]
---

# Skill Template

This is the canonical empty skeleton for a v2 OmicsClaw skill.  Copy the whole
directory, rename it, and fill in the sections below.  The companion files —
`parameters.yaml` (runtime contract) and `references/*.md` (lazy-loaded
documentation) — are described in the v2 spec at
`schemas/skills/parameters.schema.yaml`.

## When to use

Replace this section with one short paragraph: which user goals trigger this
skill, and which adjacent skills it differs from.  Mirror the language from
the frontmatter `description` ("Load when… Skip when…").

## Inputs & Outputs

| Input | Format | Required |
|---|---|---|
| primary | `<.h5ad / .csv / …>` | yes |

| Output | Path | Notes |
|---|---|---|
| report | `report.md` | always written |

One sentence per row.  Do not duplicate the full output schema here — that
lives in `references/output_contract.md`.

## Flow

1. Load and validate the input.
2. Run the analysis (delegate to `references/methodology.md` for the algorithm).
3. Write tables and figures.
4. Emit `report.md` and `result.json`.

Keep this list to ≤7 bullets.  If the flow needs more, the skill is doing
too much.

## Gotchas

<!-- Append-only flywheel.  Each entry is one sentence: a failure mode, why it
     matters, and what to do.  Mine new entries from observed agent failures
     (do NOT preemptively brainstorm — only document what has actually broken). -->

- _No gotchas yet — append entries as they surface in production._

## Key CLI

```bash
python omicsclaw.py run <skill-name> --demo
python omicsclaw.py run <skill-name> --input <data> --output <dir>
```

Show one demo invocation and one realistic invocation.  The full CLI flag
list lives in `references/parameters.md`, which is auto-generated.

## See also

- `references/parameters.md` — every CLI flag and per-method tuning hint
- `references/methodology.md` — algorithm details and design decisions
- `references/output_contract.md` — exact output directory layout
- Adjacent skills: `<list any skills a user might confuse this with>`
