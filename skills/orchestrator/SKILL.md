---
name: orchestrator
description: Load when routing a natural-language omics query to the correct domain skill across spatial / singlecell / genomics / proteomics / metabolomics / bulkrna domains via keyword / LLM / hybrid matching. Skip when the target skill is already known — invoke that skill directly.
version: 0.5.0
author: OmicsClaw
license: MIT
tags:
- orchestrator
- routing
- meta
- multi-omics
- registry
requires:
- pyyaml
---

# orchestrator

## When to use

The user asks a natural-language omics question (e.g. "find spatial
domains in my Visium data", "call CNVs from this BAM", "run DE on
my proteomics CSV") and you need to dispatch to the correct skill
across the 6 routed OmicsClaw domains (`_DOMAINS` at `omics_orchestrator.py:190`). Three routing modes:

- `keyword` (default) — fast lexical match against
  `trigger_keywords` in every skill's `parameters.yaml`.
- `llm` — LLM-based query → skill match (slower, more flexible).
- `hybrid` — keyword first, LLM fallback when ambiguous.

If the target skill is already known, invoke it directly — this
skill exists to dispatch ambiguous queries, not as a wrapper.
For scaffolding NEW skills use `omics-skill-builder`.

## Inputs & Outputs

| Input | Format | Required |
|---|---|---|
| Query | `--query <text>` (natural language) | yes (unless `--demo`) |
| Optional input file | `--input <path>` (used to bias domain detection) | no |
| Routing mode | `--routing-mode {keyword,llm,hybrid}` (default `keyword`) | no |

| Output | Path | Notes |
|---|---|---|
| Routing result | `result.json` | written via `out_json.write_text(json.dumps(result))` (`omics_orchestrator.py:409`) — includes selected skill, confidence, candidates |
| Demo report | `demo_report.txt` | only when `--demo` (`omics_orchestrator.py:334`) |

## Flow

1. Parse `--query` (or `--demo`).
2. If `--input` is provided, call `detect_domain_from_path` (`omicsclaw.loaders`) to bias domain selection.
3. Dispatch to `route_keyword` / `route_query_unified` per `--routing-mode` (`omics_orchestrator.py:24-26` imports).
4. Resolve the chosen skill via `resolve_capability` (`omicsclaw.core.capability_resolver`); look up registry entry via `omicsclaw.core.registry.registry`.
5. Write `result.json` (`omics_orchestrator.py:409`); print the selected skill name + suggested CLI invocation.

## Gotchas

- **`--query` REQUIRED unless `--demo`.** No explicit raise — argparse accepts a `None` query, the run still exits 0 and writes `result.json` with `detected_skill: null`, `coverage: "no_skill"`. Always pass `--query` for real use.
- **`--routing-mode` is IGNORED when `--query` is set.** `omics_orchestrator.py:374-389` dispatches `--query` runs to `resolve_capability` (capability-resolver — keyword-based with no mode parameter). `--routing-mode` only takes effect for file-only routing (`:393` `route_query_with_mode`) and `--demo` (`:362` `run_demo`). For LLM-routed queries, call the unified router directly.
- **Missing `LLM_API_KEY` SILENTLY falls back to keyword routing — no error.** `omicsclaw/routing/llm_router.py:48-50` logs a warning and returns `(None, 0.0)`; the orchestrator continues with keyword/capability routing. The run still exits 0 — inspect logs to confirm which mode actually fired.
- **`keyword` mode depends on `trigger_keywords` in `parameters.yaml`.** Stale or missing keywords degrade routing quality silently. The 89 v2 skills' keyword tables are loaded on every call via the registry.
- **No analysis is performed.** This skill only emits a routing decision in `result.json`; it does NOT execute the chosen downstream skill. The user (or a wrapping orchestration script) must invoke it.
- **Demo and real-query outputs are mutually exclusive.** `--demo` writes ONLY `output_dir/demo_report.txt` and returns at `omics_orchestrator.py:363`; real `--query` / `--input` runs write ONLY `output_dir/result.json` (`:409`). The two never co-exist in the same run.

## Key CLI

```bash
# Demo (synthetic queries)
python omicsclaw.py run orchestrator --demo --output /tmp/orch_demo

# Keyword routing (default — fastest)
python omicsclaw.py run orchestrator \
  --query "find spatial domains in my Visium" --output results/

# File-only routing with --routing-mode (LLM mode needs LLM_API_KEY)
python omicsclaw.py run orchestrator \
  --input mystery.csv --output results/ --routing-mode llm
# Note: --routing-mode is IGNORED if --query is also set; file-only path uses it.

# Hybrid (file-only path, keyword first then LLM fallback)
python omicsclaw.py run orchestrator \
  --input data.csv --output results/ --routing-mode hybrid
```

## See also

- `references/parameters.md` — every CLI flag
- `references/methodology.md` — keyword vs LLM vs hybrid trade-offs
- `references/output_contract.md` — `result.json` schema
- Adjacent skills: `omics-skill-builder` (parallel — scaffold NEW skills), every domain `INDEX.md` (downstream — once routing picks a domain, see its index)
