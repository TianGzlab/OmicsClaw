# Skill Guides

This directory contains **implementation-aligned guides** derived from current
OmicsClaw skills.

These documents are intentionally **separate** from the 28 validated workflows
in `knowledge_base/`:

- **Validated workflows**: stable, end-to-end analytical procedures that have
  already been curated as standard workflows.
- **Skill guides**: evolving method-selection, tuning, and interpretation notes
  derived from the current OmicsClaw skill implementations.

Use skill guides when:
- you want to understand how an OmicsClaw skill currently chooses between methods
- you need parameter tuning ideas that are specific to the current wrapper
- you want implementation-aware guidance without presenting it as a fully
  validated canonical workflow

Some skill guides also act as **navigation guides** across multiple related
skills when one command alone is not enough for a beginner to finish a task.
For example, `skill-guides/singlecell/sc-rna-quickstart.md` gives a novice
route from raw FASTQ to a downstream-ready scRNA object.

Use `knowhows/` for short guardrails. Use `skill-guides/` for the longer,
method-specific reasoning that should not be injected wholesale into prompts.
