# Skill Architecture

This document describes how OmicsClaw's skill system is laid out, discovered,
routed, and kept lean under LLM context. It is the primary reference for:

- Adding, renaming, or removing a skill
- Debugging routing decisions
- Understanding why a given file, generator, or CI job exists
- Extending the bot's tool surface without inflating always-loaded context

See also `docs/architecture.md` for the system-wide view, and
`CONTRIBUTING.md` for the day-to-day contributor workflow.

---

## 1. What a skill is

A skill is a **single analytical capability** packaged as a directory under
`skills/`. At minimum it contains:

- `SKILL.md` — YAML frontmatter (machine-readable metadata) + markdown body
  (human-readable methodology)
- A runnable entrypoint (`*.py`) invoked by `omicsclaw.py run <alias>`

Skills are dynamically discovered at startup by
`omicsclaw/core/registry.py:OmicsRegistry.load_all()`. There is no
hand-maintained list — adding a directory with a valid `SKILL.md` is enough
to register it.

### Design principles

1. **Directory layout is the source of truth.** CLAUDE.md tables,
   `catalog.json`, `orchestrator/SKILL.md`, and per-domain `INDEX.md` are
   all *generated* from the filesystem + frontmatter. Never hand-edit them.
2. **Frontmatter serves machines; body serves humans.** Everything under
   `metadata.omicsclaw.*` is parsed by the registry and surfaced to the
   LLM or autoagent. The markdown body is for contributors reading the
   repo.
3. **Keep always-loaded context small.** The LLM sees a 7-domain briefing
   plus per-tool specs every turn. Full per-skill detail is paged in on
   demand. See §5 and §9.
4. **Fail fast, with evidence.** CI gates (`sync_skill_docs --check`,
   `check_routing_budget`) reject silent drift. If you add a tool or
   rename a skill and don't regenerate the derived docs, CI stops you.

---

## 2. Directory layout

```
skills/
├── catalog.json                     # generated: full machine-readable index
├── _shared/                          # cross-domain helper libraries (optional)
├── spatial/
│   ├── INDEX.md                      # generated: lazy-load detail for LLM
│   ├── _lib/                         # shared spatial helpers
│   ├── spatial-preprocess/
│   │   ├── SKILL.md                  # frontmatter + methodology
│   │   ├── spatial_preprocess.py     # entrypoint (canonical *.py)
│   │   ├── tests/
│   │   └── figure_data/              # (optional) artifacts for re-rendering
│   └── spatial-de/
│       ├── SKILL.md
│       └── …
├── singlecell/
│   ├── INDEX.md
│   ├── scrna/                        # nested subdomain
│   │   ├── sc-preprocessing/
│   │   └── …
│   └── scatac/                       # nested subdomain
│       └── scatac-preprocessing/
├── genomics/
├── proteomics/
├── metabolomics/
├── bulkrna/
└── orchestrator/
    ├── INDEX.md
    ├── SKILL.md                       # meta-skill — routes across domains
    └── omics-skill-builder/
```

### Flat vs nested subdomains

`skills/singlecell/` is nested (`scrna/` and `scatac/` subdirectories)
because the subdomains share preprocessing conventions but diverge in
downstream methods. All other domains are flat. The registry scanner
(`omicsclaw/core/registry.py:_iter_skill_dirs`) handles both shapes —
a skill directory is anything containing a `SKILL.md`.

### Generated files (never hand-edit)

| Path | Generator | Purpose |
|---|---|---|
| `skills/catalog.json` | `scripts/generate_catalog.py` | Machine-readable listing of every skill |
| `skills/<domain>/INDEX.md` | `scripts/generate_domain_index.py` | Per-domain lazy-load detail (consumed by `list_skills_in_domain` tool and humans) |
| `skills/orchestrator/SKILL.md` (count fields) | `scripts/generate_orchestrator_counts.py` | The three hardcoded skill-count passages kept in sync |
| `CLAUDE.md` (between routing markers) | `scripts/generate_routing_table.py` | Compact 7-domain briefing shown to Claude Code |

Run them all at once:

```bash
python scripts/sync_skill_docs.py --apply    # regenerate
python scripts/sync_skill_docs.py --check    # CI-style drift check
```

---

## 3. The SKILL.md contract

Every skill's `SKILL.md` starts with YAML frontmatter. The parser lives in
`omicsclaw/core/lazy_metadata.py` (lazy, read-only) and
`scripts/generate_catalog.py` (one-shot batch scan).

### Minimum frontmatter

```yaml
---
name: my-skill-alias
description: >-
  One-sentence summary of what the skill does, including headline methods
  and output format.
version: 0.1.0
author: OmicsClaw
license: MIT
tags: [domain, keyword1, keyword2]
metadata:
  omicsclaw:
    domain: spatial                    # REQUIRED: one of the 7 domain keys
    trigger_keywords:                  # REQUIRED: drives routing scoring
      - natural-language-phrase-1
      - method-name-2
    allowed_extra_flags:               # REQUIRED: CLI flags the bot may pass
      - "--method"
      - "--top-n"
---
```

### Optional `param_hints` block (method-level search surface)

For skills that the **autoagent** can auto-tune or that the bot shows
parameter previews for, add one block per method:

```yaml
    param_hints:
      pydeseq2:
        priority: "condition_key → reference_condition → pydeseq2_fit_type"
        params: ["condition_key", "sample_key", "pydeseq2_fit_type", "pydeseq2_alpha"]
        defaults: {condition_key: "condition", sample_key: "sample_id",
                   pydeseq2_fit_type: "parametric", pydeseq2_alpha: 0.05}
        requires: ["raw_or_counts", "obs.condition_key", "obs.sample_key"]
        tips:
          - "--pydeseq2-fit-type: parametric or mean dispersion fit"
          - "--pydeseq2-alpha: significance threshold for DeseqStats"
```

#### The six real consumers of `param_hints`

`param_hints` is not documentation; it is actively read by:

| # | Consumer | File:line | Reads |
|---|---|---|---|
| 1 | Autoagent search space | `omicsclaw/autoagent/search_space.py:197-244` | `params / defaults / tips` |
| 2 | Autoagent optimizability filter | `omicsclaw/autoagent/metrics_registry.py:430` | full dict |
| 3 | Bot parameter-preview block | `bot/core.py:_build_param_hint` | `params / priority / tips / defaults` |
| 4 | Skill inference from method name | `bot/core.py:_infer_skill_for_method` | top-level method keys |
| 5 | Runtime input-suitability check | `bot/core.py:_suitability_*` | `requires` tokens (`obsm.spatial`, `layers.counts`, `obs.<key>`, `raw_or_counts`) |
| 6 | Skill candidate scoring | `omicsclaw/core/capability_resolver.py:411` | method keys |

A skill without `param_hints` still works, but loses: autoagent
optimization, bot parameter preview, and method-name-based routing. Keep
blocks minimal (only fields that actually gate behavior) — see §11 for
the unfinished cleanup plan.

### Legacy aliases

```yaml
    legacy_aliases: [old-name, even-older-name]
```

The registry registers both the canonical alias and each legacy alias.
`omicsclaw.py run old-name` still works. Legacy aliases bubble into
`capability_resolver` scoring (exact-match hit is worth ~9 points) so
users who learned the old name still route correctly.

### Other commonly-used fields

| Field | Effect |
|---|---|
| `saves_h5ad: true` | Advertised in prefetch context; helps LLM plan chained calls |
| `requires_preprocessed: true` | Prefetch warns LLM this skill expects preprocessed input |
| `emoji` | Display only |
| `homepage` | Display only |

---

## 4. Registry mechanism

### Discovery

`OmicsRegistry.load_all()` (in `omicsclaw/core/registry.py`) scans
`skills/` recursively, yielding one entry per canonical alias plus one
entry per legacy alias (both pointing to the same info dict). That means
`registry.skills` can have more keys than there are skills — callers that
want canonical-only results filter with
`if info.get("alias") == alias:`.

### Domain metadata

`_HARDCODED_DOMAINS` (`omicsclaw/core/registry.py:408`) declares the 7
domain keys and their static metadata:

```python
"spatial": {
    "name": "Spatial Transcriptomics",
    "primary_data_types": ["h5ad", "h5", "zarr", "loom"],
    "skill_count": 17,                # refreshed at runtime, see below
    "summary": "Spatial transcriptomics for Visium/Xenium/MERFISH/...",
    "representative_skills": [
        "spatial-preprocess", "spatial-domains", "spatial-de", ...
    ],
},
```

`skill_count` values in `_HARDCODED_DOMAINS` are only initial
placeholders; `_refresh_domain_skill_counts()`
(`omicsclaw/core/registry.py:378`) overwrites them after `load_all()`
with the real count per domain. The `summary` and `representative_skills`
fields drive the 7-domain briefing (§5).

### Lazy metadata

`LazySkillMetadata` (`omicsclaw/core/lazy_metadata.py`) is the per-skill
frontmatter parser. It is *lazy* — the YAML block of a `SKILL.md` is
read and parsed only when the skill is actually accessed. The bot
routing path relies on this: touching the registry doesn't load 89
SKILL.md files' worth of frontmatter.

---

## 5. Three-layer routing architecture

OmicsClaw splits routing across three tiers so the LLM pays for detail
only when it needs detail. The tiers operate within a **single LLM turn**
— this is not two-stage LLM routing (see §5.6 for why).

```
┌──────────────────────────────────────────────────────────────┐
│  L0  capability_resolver (programmatic, 0 LLM tokens)         │
│      scores all 89 skills by trigger_keywords + description    │
│      token overlap + file extension + method mentions          │
│      → returns chosen_skill OR skill_candidates[:5]            │
└──────────────────────────────────────────────────────────────┘
              ▲
              │ call with skill='auto' + query=...
              │
┌──────────────────────────────────────────────────────────────┐
│  L1  domain briefing (always-loaded, ~500 tokens)             │
│      7 domain lines: summary + 5 representative skills each    │
│      + routing policy ("prefer skill='auto'")                  │
│      embedded in the omicsclaw tool description                │
└──────────────────────────────────────────────────────────────┘
              │
              │ LLM needs a domain's full list
              ▼
┌──────────────────────────────────────────────────────────────┐
│  L2  list_skills_in_domain tool (lazy, 500–2000 tokens)       │
│      LLM calls with domain=... [filter=...]                    │
│      returns markdown: alias, desc, triggers                   │
└──────────────────────────────────────────────────────────────┘
              │
              │ skill chosen → execute
              ▼
┌──────────────────────────────────────────────────────────────┐
│  L3  prefetch_skill_context (on-demand, ~500 tokens)          │
│      param_hints keys + requires flags + saves_h5ad            │
│      injected after skill is selected                          │
└──────────────────────────────────────────────────────────────┘
```

### 5.1 L0 — Programmatic capability resolution

`omicsclaw/core/capability_resolver.py:resolve_capability()` (entry at
line 428) scores every canonical skill:

| Signal | Weight (approx.) |
|---|---|
| Alias exact match | +10 |
| Legacy alias mention | +9 |
| Trigger keyword match | +1.0–1.7 per hit (up to 3) |
| Description token overlap | +0.85 per matching token (cap 8) |
| Method name in `param_hints` | +3.0 |
| File extension → domain | filters candidate pool |

`CapabilityDecision` carries:

- `chosen_skill` — best match if top score ≥ 3.0
- `confidence` — `top.score / 14.0` capped at 1.0
- `skill_candidates[:5]` — top candidates for disambiguation
- `coverage` — one of `exact_skill`, `partial_skill`, `no_skill`
- `reasoning[]` — human-readable trace

### 5.2 L1 — Domain briefing (omicsclaw tool description)

The 7-domain briefing is rendered by
`omicsclaw/core/domain_briefing.py:build_domain_briefing()`. Format:

```markdown
OmicsClaw dispatches multi-omics analysis across 8 domains.

- **spatial** (17 skills — Spatial Transcriptomics)
  Spatial transcriptomics for Visium/Xenium/MERFISH/Slide-seq: QC, ...
  Key skills: spatial-preprocess, spatial-domains, spatial-de, ...
- **singlecell** (30 skills — Single-Cell Omics)
  scRNA-seq + scATAC-seq: FASTQ→counts, QC, filter, ...
  ...
```

`bot/core.py:_build_bot_tool_context` pre-renders this once per tool
registry build and passes it into `BotToolContext.domain_briefing`, so
the registry isn't re-scanned for every `build_bot_tool_specs()` call.

### 5.3 L2 — `list_skills_in_domain` tool (lazy detail)

Implemented in `omicsclaw/runtime/skill_listing.py` and exposed as a
bot tool via `omicsclaw/runtime/bot_tools.py`. When the LLM can't pick
a skill from the briefing alone, it calls:

```json
{
  "name": "list_skills_in_domain",
  "domain": "singlecell",
  "filter": "velocity"     // optional, case-insensitive substring
}
```

Returns a markdown block identical in shape to
`skills/<domain>/INDEX.md` but filtered live from the registry (not from
disk, to avoid any staleness surface).

### 5.4 L3 — Prefetched skill context

After the LLM picks a skill, `omicsclaw/runtime/context_layers/`
injects a "Prefetched Skill Context" block showing:

- Selected skill alias + domain + summary
- Up to 4 `param_hints` method keys
- `requires_preprocessed`, `saves_h5ad` flags
- Legacy aliases

This is the closest the LLM gets to the full SKILL.md frontmatter, and
it only happens after a skill is already chosen.

### 5.5 Disambiguation gate (Stage 3)

When `skill="auto"` is used, `bot/core.py` checks the top-1 / top-2
score gap in `decision.skill_candidates`:

```python
_AUTO_DISAMBIGUATE_GAP = 2.0  # bot/core.py

if len(cands) >= 2 and (cands[0].score - cands[1].score) < _AUTO_DISAMBIGUATE_GAP:
    return _format_auto_disambiguation(decision, query)  # refuse to execute
```

When triggered, the bot returns a list of top-3 candidates (alias + desc
+ reason) and asks the LLM to re-invoke with an explicit `skill`. This
avoids running a multi-minute analysis on the wrong skill.

**Known limitation:** in the current resolver scoring distribution, a
trigger-keyword hit adds ~5 points to top-1, so real queries rarely land
in the `3.0 ≤ top1 < top2+2.0` band. The gate is architecturally
correct but under-utilized; tune `_AUTO_DISAMBIGUATE_GAP` against real
bot logs once collected.

### 5.6 Why not two-stage LLM routing?

A tempting alternative: call the LLM once to pick a domain, then again
to pick a skill in that domain. We considered this and rejected it
because:

1. **Domain boundaries are latent.** Queries like "find marker genes in
   tumor regions" route by *data modality* (H&E + coordinates vs. h5ad
   counts vs. bulk CSV), which the LLM infers from context — not from
   being asked "which domain?"
2. **2× P50 latency.** Two LLM round-trips per turn is painful in chat.
3. **Prompt cache eviction.** Two-stage prompts share no prefix (stage
   2's input depends on stage 1's output), defeating the 5-min TTL.
4. **Cross-domain semantic clusters.** `spatial-enrichment`,
   `bulkrna-enrichment`, `sc-enrichment`, and
   `metabolomics-pathway-enrichment` all answer "pathway analysis".
   Domain-first forces an early, possibly wrong, split.

The three-layer design achieves the same "small always-loaded context"
goal without those costs. See the `git log` around Stage 2–4 for the
refactor.

---

## 6. Bot tool contract

The bot-surface tool registry is built by
`omicsclaw/runtime/bot_tools.py:build_bot_tool_specs()` and executed via
`omicsclaw/runtime/tool_registry.py`.

Three tools form the routing triad:

| Tool | Purpose | Cost |
|---|---|---|
| `omicsclaw` | Execute a skill (primary action) | ~2,100 tokens (spec JSON) |
| `list_skills_in_domain` | Page in one domain's full list | ~240 tokens (spec JSON) |
| `resolve_capability` | Programmatically inspect a query's routing decision | small |

### `omicsclaw` tool

- Params: `skill` (enum, always includes `auto`), `mode`, `query`,
  `file_path`, `method`, `extra_args`, `return_media`, ...
- Description contains: domain briefing + routing policy + `return_media` rules
- Implementation: `bot/core.py:execute_omicsclaw`

### `list_skills_in_domain` tool

- Params: `domain` (7-value enum), `filter` (optional substring)
- Implementation: `bot/core.py:execute_list_skills_in_domain` →
  `omicsclaw/runtime/skill_listing.py:list_skills_in_domain`
- Read-only, concurrency-safe

### Routing policy embedded in the tool description

The `omicsclaw` tool description ends with an explicit policy block:

> PREFER `skill='auto'` together with `query=<user's request verbatim>`.
> The capability resolver scores all skills deterministically (no extra
> LLM call). Pass a specific `skill` name ONLY when: (a) the user
> explicitly named that skill, or (b) a prior auto-routing result asked
> you to disambiguate by re-invoking with a chosen candidate.

This nudges the LLM toward the L0 path (free tokens, deterministic)
rather than guessing from the enum directly.

---

## 7. Doc generation pipeline

Four generators keep skill-derived documentation in sync with the
filesystem. All support `--apply`, `--check`, and (where applicable)
preview mode.

```
               ┌────────────────────────────────┐
               │ skills/**/SKILL.md (truth)     │
               │ _HARDCODED_DOMAINS (truth)     │
               └─────────────┬──────────────────┘
                             │ load_all()
                             ▼
                    ┌──────────────────┐
                    │  OmicsRegistry   │
                    └───┬───┬────┬─────┘
                        │   │    │
      ┌─────────────────┘   │    └────────────────────┐
      │                     │                         │
      ▼                     ▼                         ▼
generate_               generate_               generate_
routing_table.py        orchestrator_           domain_index.py
│                       counts.py               │
│ CLAUDE.md routing     │                       │ skills/<domain>/
│ block                 │ skills/orchestrator/  │ INDEX.md (×7)
│                       │ SKILL.md
│
└── generate_catalog.py ─── skills/catalog.json
```

### The four generators

| Generator | Output | Consumers |
|---|---|---|
| `generate_routing_table.py` | `CLAUDE.md` between `<!-- ROUTING-TABLE-START/END -->` | Claude Code context |
| `generate_orchestrator_counts.py` | Three passages in `skills/orchestrator/SKILL.md` | Orchestrator skill body |
| `generate_catalog.py` | `skills/catalog.json` | External tooling, tests |
| `generate_domain_index.py` | `skills/<domain>/INDEX.md` ×7 | Humans browsing the repo |

### `sync_skill_docs.py` — single entry point

```bash
python scripts/sync_skill_docs.py --apply     # regenerate all four
python scripts/sync_skill_docs.py --check     # exit 1 on drift
```

### CI enforcement

`.github/workflows/pr-ci.yml` → `docs-consistency` job runs:

```yaml
- run: python scripts/sync_skill_docs.py --check
- run: python scripts/check_routing_budget.py
```

Either one failing blocks the PR.

---

## 8. Token budget policy

### What "always-loaded" means

Every bot turn the LLM receives:

1. The entire bot-surface tool spec registry (all tools, all params,
   all descriptions) — this is non-negotiable from the LLM provider's
   perspective
2. The system prompt
3. Any injected context (e.g. CLAUDE.md for Claude Code sessions)

Items 1 + 3 are what we measure and budget. Item 2 is
application-level.

### The baseline

Pre-Stage-2 measurements (see `build/routing-baselines/before.json`):

- `omicsclaw.description` alone was 4,160 tokens (flat concatenation of
  all 88 skill "alias (description)" entries)
- CLAUDE.md routing table was 4,345 tokens (one row per skill)
- Bot always-loaded ≈ 9,600 tokens

### Current state

See `build/routing-baselines/after_stage4.json`:

- `omicsclaw.description`: 990 tokens (−76%)
- CLAUDE.md routing block: 734 tokens (−83%)
- Full bot tool registry JSON: ~8,200 tokens (39 tools)

### The ceiling

`build/routing-baselines/ceiling.json`:

```json
{
  "ceilings": {
    "claude_md_routing_block_chars": 4000,
    "bot_tool_description_chars":   5000,
    "bot_tool_spec_json_chars":    10000,
    "bot_all_tools_json_chars":    36000,
    "bot_tool_count":                 50
  }
}
```

`scripts/check_routing_budget.py` compares live measurement against
these ceilings and exits 1 if any exceed.

### Raising the ceiling

Legitimate reasons:

- Adding a genuinely new bot tool (e.g. integrating a new MCP server)
- Expanding a description to cover a new mode/parameter

Not legitimate reasons:

- Inline docs bloat ("let me add three more sentences of context")
- Re-embedding a flat skill list (undoing Stage 2)

When raising: edit `ceiling.json`, commit, and justify in the PR
description (ideally with a measurement diff from
`measure_routing_tokens.py --compare`).

---

## 9. How to add a new skill

Checklist for a brand-new skill `spatial-foo`:

### 1. Create the directory

```
skills/spatial/spatial-foo/
├── SKILL.md
├── spatial_foo.py
└── tests/
    └── test_spatial_foo.py
```

### 2. Write `SKILL.md`

Minimum frontmatter — see §3. Canonical examples for each domain:

- Spatial: `skills/spatial/spatial-preprocess/SKILL.md` (most complete)
- Single-cell: `skills/singlecell/scrna/sc-de/SKILL.md`
- Bulk RNA: `skills/bulkrna/bulkrna-de/SKILL.md`

### 3. Implement the entrypoint

Match existing CLI conventions:

- `--input <path>` / `--output <dir>` positional contract
- `--demo` flag that runs with bundled synthetic data
- Persist results as `.h5ad` / `.csv` + `figure_data/` for replotting

### 4. Regenerate derived docs

```bash
python scripts/sync_skill_docs.py --apply
```

This updates:
- `skills/catalog.json`
- `skills/spatial/INDEX.md`
- `CLAUDE.md` routing block
- `skills/orchestrator/SKILL.md` counts

### 5. Verify

```bash
python omicsclaw.py list                      # new skill should appear
python omicsclaw.py run spatial-foo --demo    # end-to-end smoke test
python -m pytest skills/spatial/spatial-foo/tests/ -v
python scripts/sync_skill_docs.py --check     # should be green
python scripts/check_routing_budget.py        # should stay under budget
```

### 6. (Optional) Add routing regression cases

If the skill introduces new keywords or competes with an existing skill,
add a case in `tests/test_routing_regression.py`:

```python
_CLEAR_INTENT_CASES.append(
    _Case(
        "spatial foo on visium",
        "run spatial foo analysis on my Visium dataset",
        expect_skill="spatial-foo",
    )
)
```

---

## 10. How to add a new bot tool

When the tool is not itself a skill (e.g. a new utility for the bot):

1. Declare the `ToolSpec` in `omicsclaw/runtime/bot_tools.py:build_bot_tool_specs()`
2. Write the executor `async def execute_mytool(args, **kwargs) -> str`
   in `bot/core.py`
3. Register it in `_available_tool_executors` (same file, search for
   the dict)
4. Add tests covering:
   - ToolSpec is present in the registry
   - Executor returns an error message (not an exception) on missing
     required params
   - Happy path end-to-end
5. Run `python scripts/check_routing_budget.py` — new tools increase
   `bot_all_tools_json_chars`

Follow the pattern set by `list_skills_in_domain`:
- `omicsclaw/runtime/skill_listing.py` (pure function)
- `omicsclaw/runtime/bot_tools.py` (ToolSpec)
- `bot/core.py:execute_list_skills_in_domain` (async wrapper)
- `tests/test_skill_listing.py` (coverage)

---

## 11. Known limitations and roadmap

### Tracked xfails in `tests/test_routing_regression.py`

Four resolver weaknesses surfaced by Stage 5, preserved as `xfail` so
they turn green automatically when fixed:

1. **Analysis-verb gate is too narrow.**
   `_looks_like_analysis_request` in `capability_resolver.py` rejects
   queries that start with verbs like *call* ("call SNVs") or *identify*
   ("identify peptides"). Fix: expand the whitelist or accept any query
   that scores any non-zero candidate.

2. **File-extension domain isn't a hard filter.**
   Detecting `.vcf.gz` → genomics is correct, but
   `iter_primary_skills(domain=...)` still surfaces candidates from
   other domains. Legacy alias `annotate` (spatial-annotate) beats
   `genomics-variant-annotation` on `"annotate variants"`. Fix: when a
   file extension pins the domain, hard-filter the candidate pool.

3. **Cross-domain queries collapse to one domain.**
   `_detect_domain` over-commits on keywords like *pathway* (→ spatial).
   For truly cross-domain queries the candidate list should span ≥2
   domains so the disambiguation gate can fire.

4. **`_AUTO_DISAMBIGUATE_GAP` is architecturally correct but rarely
   triggered** (see §5.5). Needs calibration against real traffic.

### Unfinished cleanups

- **SKILL.md frontmatter format is uneven.** Some skills (mostly
  spatial) have full `param_hints` with `tips` and `requires`; others
  are minimal. Low-effort cleanup: backfill `param_hints` skeletons in
  the lean SKILL.md files directly — SKILL.md is the single source of
  truth for skill metadata.
- **`param_hints.defaults` duplicates argparse defaults.** Changing a
  default in the entrypoint without updating `SKILL.md` desyncs the
  autoagent search space. Planned: introspection-based diff in a new
  `scripts/derive_defaults.py`.
- **No explicit input/output schemas.** Downstream skills assume the
  upstream AnnData carries specific `obs`/`obsm` keys without an
  enforceable contract. Planned: per-skill `inputs:`/`outputs:`
  frontmatter sections + a contract test for the core chains
  (preprocess→domains→de, etc.).

### Orchestrator skill vs bot/core routing — duplicate logic

`skills/orchestrator/omics_orchestrator.py` implements routing in
Python for CLI users; `bot/core.py` uses `capability_resolver` directly
for messaging users. They drift. Long-term fix: delete the orchestrator
skill's routing logic and have it call `resolve_capability` too.

---

## 12. Where to look when something is wrong

| Symptom | First file to read |
|---|---|
| New skill not found by `omicsclaw.py run` | `omicsclaw/core/registry.py:_iter_skill_dirs` |
| CLAUDE.md routing table out of date | `scripts/generate_routing_table.py` |
| Bot tool description missing fields | `omicsclaw/runtime/bot_tools.py:build_bot_tool_specs` |
| Routing sends to wrong skill | `omicsclaw/core/capability_resolver.py:resolve_capability` (read `decision.reasoning`) |
| Bot refuses to run an obviously-valid query | `_looks_like_analysis_request` in `capability_resolver.py` |
| Autoagent says "no optimizable methods" | `param_hints` missing or missing `defaults` |
| CI `docs-consistency` fails | Run `python scripts/sync_skill_docs.py --apply` locally |
| CI `check_routing_budget` fails | Run `python scripts/measure_routing_tokens.py --compare build/routing-baselines/after_stage4.json` |

---

## Appendix A — File map

Core modules:

- `omicsclaw/core/registry.py` — skill discovery and alias resolution
- `omicsclaw/core/lazy_metadata.py` — per-skill lazy frontmatter parser
- `omicsclaw/core/capability_resolver.py` — programmatic routing (L0)
- `omicsclaw/core/domain_briefing.py` — L1 briefing renderer

Runtime:

- `omicsclaw/runtime/bot_tools.py` — LLM-facing tool specs
- `omicsclaw/runtime/tool_registry.py` — spec→executor wiring
- `omicsclaw/runtime/skill_listing.py` — L2 `list_skills_in_domain`
- `omicsclaw/runtime/context_layers/` — L3 prefetch

Bot entry:

- `bot/core.py` — `execute_omicsclaw`, disambiguation gate, auto-route banner

Scripts:

- `scripts/sync_skill_docs.py` — one-shot wrapper
- `scripts/generate_routing_table.py`
- `scripts/generate_orchestrator_counts.py`
- `scripts/generate_catalog.py`
- `scripts/generate_domain_index.py`
- `scripts/measure_routing_tokens.py`
- `scripts/check_routing_budget.py`

Baselines:

- `build/routing-baselines/before.json` — pre-Stage-2 snapshot
- `build/routing-baselines/after_stage3.json` — post-disambiguation
- `build/routing-baselines/after_stage4.json` — post-lazy-load
- `build/routing-baselines/ceiling.json` — hard limits

Tests (routing-adjacent):

- `tests/test_registry.py`
- `tests/test_lazy_metadata.py`
- `tests/test_keyword_routing.py`
- `tests/test_capability_resolver.py`
- `tests/test_auto_routing_disambiguation.py` (Stage 3)
- `tests/test_skill_listing.py` (Stage 4)
- `tests/test_routing_regression.py` (Stage 5)
- `tests/test_engineering_tools.py`
