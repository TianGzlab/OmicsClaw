# Methodology

<!--
This file holds the WHY behind the algorithm.  It is lazy-loaded — `SKILL.md`
is loaded on every agent invocation, this file only when the agent decides
to dig in.  Keep `SKILL.md` ≤ 200 lines by pushing depth here.

Four sections below are the recommended minimum.  Skills with multi-method
dispatch, complex input matrix contracts, or extensive CLI surfaces should
add the OPTIONAL sections listed at the end (see `skills/singlecell/scrna/
sc-de/references/methodology.md` for a fully-fleshed example).

Skip obvious things — don't recapitulate Wikipedia, don't restate framework-
standard behaviour.  Focus on what the agent (or a future human) would
otherwise get wrong.
-->

## Capabilities

<!--
A numbered list of what this skill does.  Each entry is one short clause —
"X does Y on Z" — not a sales pitch.  Items here should map 1:1 to the
concrete artifacts the script produces (a table, a figure family, an
export, a downstream-skill handoff).
-->

1. **<core capability>** — one-line description of the primary computation.
2. **<secondary capability>** — e.g. a method variant or post-filter.
3. **<export>** — what figure-ready / downstream-handoff artifacts the
   skill emits.

## Workflow

<!--
The runtime pipeline as the script actually executes it.  Match the
numbered list in `SKILL.md`'s `## Flow` but go one level deeper — what
each step validates, what it can raise, what intermediate state it
produces.  Anchor to `<script>.py:LINE` where it helps.
-->

1. **Load** — read the input (`<reader>`) and surface what is in `<X>` /
   `<obs[Y]>`.
2. **Validate** — check required columns / matrix contract; raise
   `ValueError(...)` on mismatch.
3. **Run** — execute the chosen `--method` backend.
4. **Export** — write `tables/<name>.csv` plus `report.md` and
   `result.json` via the common report helper.

## Methodology

<!--
The statistical / biological / algorithmic rationale.  This is the
section a domain expert reads to decide whether to trust the result.
Cover the assumptions each method makes, where each method is and is
NOT appropriate, and the canonical citation.

For multi-method skills, prefer a per-method subsection over a
comparison table — caveats are usually too specific to fit a table cell.
-->

### `<method-name>`

- **Input contract**: `<matrix expectation, e.g. raw counts in
  layers["counts"]>`.
- **Test / algorithm**: one-line statement of the underlying method
  (e.g. "Wilcoxon rank-sum on log-normalized expression").
- **Assumptions**: what the method assumes about the data (e.g.
  independent observations, unequal variance, sufficient sample size).
- **Failure mode**: the most common silent-wrong-answer trap and how to
  detect it from `result.json`.
- **Citation**: (Author, year). Title. Journal. DOI.

## Dependencies

<!--
The runtime requirements as the user will encounter them.  Split into
required vs optional so the installation hint surfaced by the bot is
precise.  `parameters.yaml::requires` and `parameters.yaml::install`
should agree with this list.
-->

**Required**

- `<package>` — `<reason>`

**Optional**

- `<package>` — `<feature that needs it>`

<!--
==============================================================================
OPTIONAL sections — keep ONLY the ones your skill actually needs.  Delete
the rest.  Adding empty placeholder sections is worse than omitting them.

## Input Formats
| Format | Extension | Required Fields | Example |
|--------|-----------|-----------------|---------|

## Input Matrix Convention
(For omics skills with stringent per-method matrix expectations.)

## CLI Reference
(For skills with extensive flag surfaces — mirror the `## Key CLI` block
from `SKILL.md` here with full per-method invocation examples.)

## Safety
(For skills with non-obvious data-handling implications — local-first
caveats, fake-replicate guards, identity / PHI considerations.)
==============================================================================
-->
