---
doc_id: sc-velocity-prep-guardrails
title: Single-Cell Velocity Prep Guardrails
doc_type: knowhow
critical_rule: MUST explain that sc-velocity-prep creates spliced and unspliced layers but does not perform RNA-velocity modeling itself
domains: [singlecell]
related_skills: [sc-velocity-prep]
phases: [before_run, on_warning, after_run]
search_terms: [RNA velocity prep, velocyto, STARsolo Velocyto, spliced unspliced, loom, 单细胞速度预处理]
priority: 1.0
source_urls:
  - https://velocyto.org/velocyto.py/tutorial/cli.html
  - https://scvelo.readthedocs.io/en/stable/getting_started.html
  - https://github.com/alexdobin/STAR/blob/master/docs/STARsolo.md
---

# Single-Cell Velocity Prep Guardrails

- **Separate prep from modeling**: this skill prepares `spliced` / `unspliced` layers; the actual scVelo modeling step still belongs to `sc-velocity`.
- **Inspect the source path first**: distinguish among Cell Ranger outputs, STARsolo Velocyto outputs, loom files, and raw FASTQ inputs. They have different prerequisites and should not be described as interchangeable.
- **Do not pretend standardization creates biology**: `sc-standardize-input` can stabilize an AnnData contract, but it cannot fabricate `spliced` / `unspliced` layers.
- **Use velocyto with the right inputs**: when running from a Cell Ranger BAM, require a GTF and a filtered barcode set. The official velocyto docs explicitly warn that omitting barcode filtering is not recommended because runtime and memory can explode.
- **Use STARsolo Velocyto honestly**: the current wrapper supports import of existing Velocyto matrices and a narrow 10x-oriented FASTQ path with `--soloFeatures Gene Velocyto`; do not imply generic support for every custom chemistry.
- **When GTF or STAR references are missing, be actionable**: tell the user where to download or reuse them, and where to place them locally under `resources/singlecell/references/...`; do not stop at “missing --gtf”.
- **Explain merge behavior**: `--base-h5ad` is a convenience merge, not a magic reconciliation step. The current merge only keeps shared cells and shared genes.
- **Do not overpromise velocity quality**: preparing layers successfully does not guarantee that downstream velocity inference will be biologically meaningful.
- **For detailed operator guidance**: see `knowledge_base/skill-guides/singlecell/sc-velocity-prep.md`.
