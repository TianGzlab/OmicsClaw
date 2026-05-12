# `templates/skill/` is a human-copy starter, not a codegen source-of-truth

## Status

Accepted (2026-05-12).

## Context

`templates/skill/` was originally framed (in its own `SKILL.md` preamble) as
the canonical v2 OmicsClaw skill skeleton consumed by three callers:

1. Humans copying the directory to bootstrap a new skill.
2. `omics-skill-builder` (`skills/orchestrator/omics-skill-builder/`),
   which wraps `omicsclaw/core/skill_scaffolder.py`.
3. `scripts/migrate_skill.py`, the legacy → v2 migrator.

In reality only the first is true today:

- `skill_scaffolder.py` declares the path `SKILL_TEMPLATE_PATH = …/templates/skill/SKILL.md`
  as provenance metadata on the result dataclass, but its `render_skill_markdown`
  / `render_parameters_yaml` functions emit content from internal f-strings
  and never read the template files.
- `migrate_skill.py` contains no reference to `templates/skill/` at all.

The reference v2 skills (e.g. `skills/singlecell/scrna/sc-de`,
`skills/spatial/spatial-de`) have evolved into a richer shape than the
template currently captures: a runnable `<skill>.py`, a `test_demo_mode`
test, an optional `r_visualization/` directory, and a parameters sidecar
with soft fields (`requires`, `install`, `os`, `homepage`) that `skill_lint.py`
does not enforce but every gold skill carries.

The question is whether to bring the codegen scripts inline so they read
from `templates/skill/` as a single source-of-truth, or to keep them
decoupled and treat the template purely as a human-copy starter.

## Decision

`templates/skill/` is **a human-copy starter only**. The codegen scripts
(`skill_scaffolder.py`, `migrate_skill.py`) keep their internal renderers
and are NOT refactored to read from this directory.

Concretely:

1. The template is structured to bring a new contributor ~80% of the way
   to the shape of `sc-de` / `spatial-de` via `cp -r templates/skill new-skill/`
   plus rename. It includes a runnable `replace_me.py`, a passing
   `test_demo_mode`, the full parameters sidecar including soft fields,
   and a 4-section `methodology.md` skeleton.
2. The "AUTHORING GUIDE" preamble inside `SKILL.md` is shortened to a
   5-line checklist; long-form usage notes move to a new
   `templates/skill/README.md`.
3. The false claim that the template is consumed by
   `omics-skill-builder` and `migrate_skill.py` is removed.
4. `skill_scaffolder.py`'s output, and `migrate_skill.py`'s output, are
   kept honest by `scripts/skill_lint.py` — the same lint that gates the
   gold skills. The template and the codegen share a *shape contract*
   (the lint rules), not a *string contract*.

## Consequences

**Positive**

- The template can be richer and more opinionated (HTML comments, prose
  guidance, `_None yet —` empty markers, contributor-facing README)
  without forcing the codegen to handle templating placeholders or
  Jinja-style interpolation.
- `omics-skill-builder` keeps the ability to render fully-parameterised
  output for autonomous analysis promotion flows, which a static template
  cannot serve.
- `migrate_skill.py` keeps the ability to derive content from the legacy
  SKILL.md it is migrating, which a static template cannot serve either.

**Negative**

- The template and the codegen renderers can drift apart over time.
  Mitigation: both feed through `scripts/skill_lint.py`; structural
  drift surfaces as lint failures rather than silent divergence.
- Future contributors may reasonably ask "why doesn't `omics-skill-builder`
  read this directory?" — this ADR is the answer.

## Alternatives considered

- **Make the codegen read the template** — requires introducing a
  templating mechanism (placeholder substitution or Jinja). The template
  becomes harder to read for the human-copy use case, and the codegen
  gains a non-trivial dependency. Rejected: the cost of templating
  exceeds the benefit of single-source-of-truth, given that `skill_lint.py`
  already enforces the shape contract.
- **Drop the template entirely and rely on copying `sc-de`** — copying
  a gold skill brings along its domain-specific demo data, its R
  visualization layer, and its argparse surface; the contributor has to
  delete more than they keep. A purpose-built minimal template is a
  better starting point.
- **Split into per-domain templates** (`templates/skill-spatial/`,
  `templates/skill-genomics/`, …) — every domain's script today imports
  `omicsclaw.common.report` and follows the same argparse-plus-demo
  shape; the cross-domain delta is mostly the primary input format,
  which the contributor would have to change regardless. Rejected as
  premature splitting.
