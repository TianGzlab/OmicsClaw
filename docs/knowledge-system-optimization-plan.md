# Knowledge System Optimization Plan

> **Status**: Engineering-grade architectural and implementation plan
> **Last Updated**: 2026-03-28
> **Confidence**: High (Direction & Feasibility verified against production requirements)

---

## Executive Summary

**Core Problem**: The `/guide` command forces users to interrupt their analysis flow to explicitly query for knowledge. Knowledge retrieving is disconnected from skill execution context.
**Key Insight**: This is not primarily a retrieval problem (FTS5+BM25 is sufficient), but an **orchestration problem**. Knowledge must be dynamically pushed based on determined execution states, not pulled via LLM prompt heuristics.

**Architectural Pivot**: The knowledge system must be decoupled into two distinct layers:
1. **Knowledge Orchestration (Routing)**: A deterministic advisory middleware that decides *when* to query, *why*, and *what type* of knowledge to surface.
2. **Knowledge Retrieval**: The FTS5 engine that finds the best content *after* the candidate set is significantly narrowed down.

**Crucial Clarification**: The knowledge system provides **decision rationale** (why, interpretation, troubleshooting), while the workflow graph/planner provides **workflow progression** (what to do next). These must remain separate responsibilities.

---

## 1. Completed Milestone: Modular Skill & Knowledge Restructuring

**Current State**: The `knowledge_base/` directory has been successfully refactored from a monolithic "docs dump" into a cleanly decoupled staging ground. This resolves the previous functional overlap where execution scripts and domain knowledge were chaotically mixed.

**New Structural Topology**:
1. **Self-Contained Skill Packages**: All code, execution logic, and tool-specific docs have been unified into 28 independent, cohesive tool folders directly under `knowledge_base/` (e.g., `knowledge_base/bulk-omics-clustering/`). Each is now an encapsulated package featuring its own `SKILL.md`, `scripts/`, and local `references/`.
2. **Pure Domain Knowledge (`knowhows/`)**: Genuine non-tool-specific biological principles and decision rationale (originally prefixed with `KH-`) are now strictly isolated within the `knowledge_base/knowhows/` directory. **These serve as mandatory scientific constraints**.
3. **Migration Readiness**: Because each local package in `knowledge_base/` now adheres to the OmicsClaw `SKILL.md` + `scripts/` canonical structure, they mirror the main `skills/` framework. Future integration entails simply dropping these tested folders directly into the central `skills/` registry.

---

## 2. High-Level Target Architecture

Our goal is a localized, context-aware push system that safely augments analysis:

```text
User Request / Setup
  ↓
  ↳ Preflight Context Injection (Know-Hows Pipeline)
      ↳ Identify Domain + Modality
      ↳ Forcibly inject relevant KH rules (e.g., "Always use adjusted p-values")
      ↓
Skill Execution
  ↓
  ↳ Emits Unified Advisory Event (skill, phase, signals, metrics)
      ↓
      ↳ Workflow Planner (suggests next logical skills)
      ↓
      ↳ Knowledge Resolver Layer (Deterministic Orchestration)
          1. Filters candidates based on skill + phase + signals (narrowing)
          2. Applies Session Cooldown / Deduplication
          3. Retrieves Top 1-2 advice snippets via FTS5/BM25
      ↓
  ↳ LLM Synthesizer gets:
       (a) Raw skill result metrics
       (b) Next-step workflow suggestions
       (c) Short knowledge advice snippets / Reminders of active KH constraints
      ↓
Response Presentation to User (Channel-specific UX)
```

### Fundamental Principles
- **Mandatory Preflight Know-Hows**: `KH-*.md` documents are not suggestions; they are high-frequency error checklists that must be injected as **hard system constraints** into the LLM context *before* the relevant analysis begins.
- **`/guide` is demoted, not removed**: Remains an explicit, deep-dive mode for teaching purposes. Inline tips (`/tips`) become the default.
- **Maintain FTS5**: Do not introduce vector databases currently. Contextual narrowing makes BM25 highly effective on this scale (~400 files).
- **SKILL.md vs. Knowledge Separation**: SKILL.md holds the *execution contract* (what it is, parameters, defaults). Knowledge docs hold the *decision rationale* (why choose it, troubleshooting, interpreting warnings). The boundaries must be strict.
- **No Prompt-Driven Knowledge Sourcing**: The decision to look up knowledge must happen via definitive signals in the middleware, not by asking the LLM to decide when to call tools.

---

## 3. Phased Implementation Plan

The implementation must prioritize foundational telemetry and signaling over content or search polish, with immediate integration of the newly minted Know-Hows.

### Stage 0: Observability & Evaluation Baseline ✅ IMPLEMENTED

Before changing the system, we must be able to measure if knowledge injection is helping or becoming noise.

**Action Items**:
- Implement basic telemetry to track:
  - Which skill runs triggered advice queries.
  - Which KH rules were injected.
  - Frequency of advice displays.
  - User engagement: Did they follow up, or turn off `/tips`?
  - Advice duplication rates.
  - $p95$ Latency impact of the retrieval process.
- Establish metrics for **Trigger Precision** (was the hint appropriate) and **Advice Usefulness**.

***

### Stage 1: Mandatory Know-Hows (KH) Injection ✅ IMPLEMENTED

Leverage the 4 newly consolidated Know-How guides to establish a "hard constraint" preflight check.

**Action Items**:
- Develop a `PreflightContextInjector` that runs *before* tool execution.
- Map domains/tasks to specific KH docs (e.g., mapping any differential expression task to `KH-bulk-rnaseq-differential-expression.md`).
- Implement system prompt appending:
  `[SYSTEM CONTENT MODIFICATION]: You must follow these strict scientific constraints for the current task: {KH_CONTENT}`
- This guarantees the AI respects rules like "use padj, not pvalue" or "check duplicates & missing values >20%" unconditionally.

***

### Stage 2: Unified Advisory Event Schema ✅ IMPLEMENTED

The knowledge system cannot trigger reliably on unstructured free-text skill outputs.

**Action Items**:
- Standardize a `dict` or `Pydantic` schema that *every* skill returns when finishing or throwing an error.
- Example structure to emit:
  ```json
  {
    "skill": "sc-filter",
    "phase": "post_run",  // before_run, post_run, on_warning, on_error
    "domain": "singlecell",
    "toolchain": "scanpy",
    "signals": ["qc.high_mt_pct", "filter.overaggressive"],
    "severity": "warning",
    "metrics": {
      "median_mt_pct": 18.4,
      "cells_removed_pct": 47.2
    }
  }
  ```
- *Rollout Strategy*: Start by modifying just 10-15 high-frequency skills to emit these signals, specifically focusing on `on_warning` and `on_error` phases.

***

### Stage 3: Canonical Knowledge Registry ✅ IMPLEMENTED

We must establish a single source of truth mapping skills/signals to documentation, avoiding the double-maintenance trap.

**Action Items**:
- Choose **one** canonical approach. Instead of a separate `skill_map.yaml`, mandate strict YAML frontmatter metadata inside the markdown documents as the sole truth source.
- Standard Metadata Schema:
  ```yaml
  doc_id: sc-mt-filtering-best-practices
  title: Mitochondrial Filtering Best Practices
  doc_type: decision_guide
  domains: [singlecell, spatial]
  related_skills: [sc-qc, sc-filter, sc-preprocessing]
  phases: [post_run, on_warning]
  signals: [qc.high_mt_pct]
  search_terms: [mitochondrial threshold, mt percent, qc cutoff]
  audience: [basic, expert]
  priority: 0.8
  ```
- Build an inverted index at system startup mapping `skill -> phases/signals -> doc_ids` to ensure fast lookups.

***

### Stage 4: Deterministic Knowledge Resolver ✅ IMPLEMENTED

Replace LLM "guesswork" with a hardcoded logic pipeline that curates what the LLM will see.

**Action Items**:
- **Routing First, Retrieval Second**: Given an Advisory Event (Stage 2), look up candidate `doc_ids` matching the `related_skills` + `phases` + `signals`.
- **Ranking**: Apply FTS5/query terms to rank *only* those candidates.
- **Session Deduplication (Crucial)**: Keep a cache of shown `doc_ids` (and injected KHs) per session ID. Suppress or heavily penalize heavily repeated advice unless the severity level escalates.
- Output: Pass only 1-2 highly relevant, short snippets to the LLM contextual prompt.

***

### Stage 5: Inline Presentation UX (`/tips`) ✅ IMPLEMENTED

Integrate the curated knowledge smoothly into user interactions contexts.

**Action Items**:
- Implement `/tips on|off` and optionally `/tips level [basic|expert]`.
- Enforce **Channel Differences** in the presentation layer:
  - **CLI (Terminal)**: Output a distinct, concise `Advice:` block containing bullet points and one-line rationales (to avoid scrolling fatigue).
  - **Bot (Telegram/Feishu)**: Have the LLM synthesize the snippet gracefully into a 1-2 sentence conversational hint at the end of the skill report.
  - **Explicit `/guide`**: Returns full paragraphs and extensive context.

***

### Stage 6: Risk-Driven Content Program (Coverage) — PENDING

Fill knowledge base gaps based on operational necessity, not arbitrary domain symmetry.

**Action Items**:
- Analyze output telemetry (Stage 0) over time to identify what fails most often or causes the most confusion.
- **Prioritize creating docs for**:
  1. Threshold/Parameter decisions (e.g., QC cutoffs, DE parameters).
  2. High-frequency warnings, failures, or blank outputs.
  3. Conceptually complex interpretation gaps (e.g., over-reading cell annotations).
- Avoid copy-pasting code definitions from `SKILL.md`. Focus purely on *why* and *what if*.

***

### Stage 7: Search & Retrieval Polish — PENDING

Now that candidates are highly targeted, polish the FTS5 retrieval.

**Action Items**:
- **Split Corpus**: Ensure code files (Py/R scripts) don't bleed into standard "guidance" searches unless explicitly in full-implementation queries.
- **Field Weighting**: Weight title > explicit search_terms > headings > body text.
- **Synonym Expansion**: Add minimal runtime mapping before querying (e.g., `batch correction` -> `combat` & `harmony`).

---

## 4. Recommended Rollout Summary

1. **Milestone Reached**: Knowledge Base Modular Restructuring (Section 1 - Completed, 28 workflows, 4 Know-Hows).
2. **Foundations**: Telemetry (Stage 0), Mandatory Know-How Injection (Stage 1).
3. **Core Wiring**: Event Schema (Stage 2), Canonical Metadata Frontmatter (Stage 3).
4. **Orchestration**: The Resolver Engine & Session Dedupe (Stage 4).
5. **User Experience**: The `/tips` toggle & Channel integrations (Stage 5).
6. **Maintenance Phase**: Risk-driven content gap filling (Stage 6) & Advanced Search (Stage 7).
