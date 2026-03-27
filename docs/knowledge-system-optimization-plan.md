# Knowledge System Optimization Plan

## 1. Current Architecture Overview

### Knowledge Base Structure (`knowledge_base/`)
- **424 files** across 10 numbered categories + scripts/
- 151 markdown docs, 169 Python scripts, 104 R scripts
- Categories: workflow_guides, decision_guides, best_practices, troubleshooting, method_references, interpretation_guides, data_preprocessing_qc, statistical_methods, tool_setup, domain_knowledge
- Covers 7 omics domains: spatial, singlecell, genomics, proteomics, metabolomics, bulkrna, general

### Backend (`omicsclaw/knowledge/`)
- **KnowledgeStore** (`store.py`): SQLite FTS5 full-text search, BM25 ranking
- **KnowledgeIndexer** (`indexer.py`): Parses markdown/Python/R, chunks at heading boundaries (3000 char max)
- **KnowledgeAdvisor** (`retriever.py`): Public API facade — `search()`, `search_formatted()`, `build()`, `list_topics()`

### Access Points
| Channel | Entry | Mechanism |
|---------|-------|-----------|
| CLI interactive | `/guide [topic]` | Prompt injection into LLM → LLM calls `consult_knowledge` tool |
| Bot (Telegram/Feishu) | LLM auto-call | System prompt tells LLM to "use proactively" when user asks method/parameter questions |
| CLI direct | `python omicsclaw.py knowledge search <q>` | Direct FTS5 query, prints results to terminal |

### Call Flow for `/guide`
```
User types "/guide bulk RNA normalization"
  → _handle_guide() wraps as "[GUIDE MODE] ..."
  → Injected as user message into LLM conversation
  → LLM decides to call consult_knowledge tool
  → execute_consult_knowledge() → KnowledgeAdvisor.search_formatted()
  → FTS5 BM25 search → top 5 chunks returned
  → LLM synthesizes answer from chunks
  → Streamed to user
```

---

## 2. Current Design: Strengths

1. **Well-structured knowledge taxonomy**: 10 categories cover the full lifecycle (from tool setup → workflow → interpretation → troubleshooting), mimicking how a researcher thinks
2. **FTS5 + BM25 is solid**: Full-text search with probabilistic ranking is the right primitive for this scale (hundreds of docs, not millions)
3. **Chunk-level retrieval**: Section-based chunking ensures focused, relevant results rather than dumping entire documents
4. **Domain/type filtering**: Allows narrowing search to specific omics domains and document types
5. **Bot integration exists**: The `consult_knowledge` tool is registered for the LLM to call proactively
6. **Separation of content and code**: Knowledge lives in markdown files, independent of skill scripts — easy to add/edit/review

---

## 3. Current Design: Weaknesses

### 3.1 `/guide` is an "extra step" that breaks the user's flow

**Core problem:** User must *stop* their analysis to type `/guide`, wait for results, then manually go back to running skills. This is the "鸡肋" you identified.

Real user flow:
```
User: run sc-preprocessing --demo
→ sees high mitochondrial percentage
→ wants to know: "is 20% the right threshold?"
→ currently must: /guide mitochondrial threshold
→ reads answer
→ manually adjusts: run sc-filter --max-mt-percent 15
```

**What should happen:** Knowledge should surface *during* the analysis, not as a separate interrogation.

### 3.2 Knowledge is disconnected from skill execution context

When a skill runs and produces output (e.g., QC plots, DE results), the knowledge system has **no awareness** of:
- Which skill just ran
- What the output metrics were
- What common issues relate to those specific results
- What the logical next step is

The LLM receives the skill output AND has access to `consult_knowledge`, but **nothing links them together**. The LLM must independently decide to query knowledge — and it usually doesn't, because the system prompt instruction ("use proactively") is a weak signal easily overshadowed by the immediate task of reporting results.

### 3.3 Knowledge coverage is skewed

| Domain | Workflow Guides | Decision Guides | Troubleshooting | Total |
|--------|----------------|-----------------|-----------------|-------|
| Bulk RNA-seq | 5+ | 3+ | 2 | ~15 |
| Genomics (GWAS/variant) | 6+ | 2+ | 2 | ~15 |
| Single-cell (Scanpy/Seurat) | 4+ | 2+ | 3 | ~12 |
| Proteomics | 1 | 0 | 0 | ~2 |
| Metabolomics | 0 | 0 | 0 | ~0 |
| Spatial | 1 | 0 | 0 | ~2 |

The knowledge base is **heavily biased toward genomics and bulk RNA-seq**, with minimal coverage for spatial, proteomics, and metabolomics — the domains that OmicsClaw also supports.

### 3.4 Knowledge and SKILL.md are duplicative

Each SKILL.md already contains:
- Algorithm descriptions and methodology
- Parameter guidance
- CLI reference
- Best practices (embedded in the workflow section)

The knowledge_base contains similar but separate documents. There's no clear boundary: when should info go in SKILL.md vs knowledge_base? This leads to:
- Duplication of effort
- Risk of contradictory guidance
- Unclear source of truth

### 3.5 No contextual attachment between knowledge and skills

There's no mechanism to say "this troubleshooting doc relates to the sc-preprocessing skill" or "this best-practice doc should be surfaced after spatial-domains runs". Knowledge docs are standalone with only domain-level filtering.

### 3.6 Search is keyword-only (no semantic understanding)

FTS5 BM25 is good for exact keyword matches but fails on:
- Synonyms: "normalize" vs "scaling" vs "transform"
- Conceptual queries: "how to handle batch effects" won't match a doc titled "ComBat correction"
- Cross-domain concepts: "differential expression" exists in spatial, singlecell, bulkrna, proteomics — domain context matters

### 3.7 The `/guide` prompt injection is fragile

The `[GUIDE MODE]` prefix is a prompt hack — the LLM must:
1. Notice the prefix
2. Decide to call `consult_knowledge` (not guaranteed)
3. Formulate good search parameters (query, domain, category)
4. Synthesize results well

Each step can fail. If the LLM doesn't call the tool, the user gets a generic answer without knowledge base backing.

---

## 4. Optimization Plan

### Stage 1: Contextual Knowledge Injection (skill-aware guidance)

**Goal:** Knowledge surfaces automatically during skill execution, not as a separate query.

**Approach:** Add a `skill_context` field to each knowledge document (in frontmatter or a mapping file) that links knowledge to specific skills and result patterns. When a skill finishes, automatically attach relevant knowledge context.

**Implementation:**

1. **Add `related_skills` to knowledge document frontmatter:**
   ```yaml
   ---
   title: Mitochondrial Filtering Best Practices
   related_skills: [sc-filter, sc-qc, sc-preprocessing, spatial-preprocessing]
   trigger_on: [high_mt_pct, qc_complete]
   ---
   ```

2. **Create a knowledge context builder** (`omicsclaw/knowledge/context.py`):
   ```python
   class SkillKnowledgeContext:
       """Attach relevant knowledge to skill execution results."""

       def get_post_run_context(self, skill_name: str, result: dict) -> str:
           """Return knowledge snippets relevant to what just ran."""
           # 1. Find docs with related_skills matching skill_name
           # 2. Optionally match result patterns (e.g., high error rate)
           # 3. Return formatted context for LLM
   ```

3. **Integrate into `run_skill()` in `omicsclaw.py`** and `execute_omicsclaw()` in `bot/core.py`:
   - After skill completes, append relevant knowledge context to the result
   - LLM receives: skill output + relevant knowledge → synthesizes a response that naturally includes guidance

**Key files:**
- New: `omicsclaw/knowledge/context.py`
- Modify: `omicsclaw.py` `run_skill()` (lines 202-330)
- Modify: `bot/core.py` `execute_omicsclaw()` (lines 1375-1667)
- Modify: knowledge_base markdown files (add `related_skills` frontmatter)

### Stage 2: Convert `/guide` to inline mode

**Goal:** Instead of a separate `/guide` command, knowledge guidance becomes part of the normal conversation flow.

**Approach:**

1. **Deprecate `/guide` as the primary entry point** — keep it for explicit deep-dive queries but remove the expectation that users should use it

2. **Enhance the system prompt** to make knowledge consultation truly proactive:
   - Current: one line saying "use proactively" (weak signal)
   - New: structured rules with specific triggers:
     ```
     KNOWLEDGE RULES:
     - BEFORE running any skill for the first time in a session, consult knowledge
       for the relevant workflow guide
     - AFTER a skill produces QC warnings or errors, consult troubleshooting docs
     - When user asks "which method", "how to choose", "what parameters" — consult
       decision guides
     - When presenting results, briefly note the relevant interpretation guide
     ```

3. **Add a `/tips` toggle** instead of `/guide`:
   - `/tips on` — enable automatic knowledge tips after each skill run
   - `/tips off` — disable (for expert users who don't need guidance)
   - Default: on for new sessions

**Key files:**
- Modify: `omicsclaw/interactive/interactive.py` (lines 442-481, 1267-1283)
- Modify: `bot/core.py` `get_role_guardrails()` (lines 660-754)
- Modify: `omicsclaw/interactive/_constants.py` (slash commands)

### Stage 3: Skill-Knowledge bridging index

**Goal:** Create an explicit mapping between skills and knowledge documents so the system knows which docs are relevant for which skills.

**Approach:**

1. **Create `knowledge_base/skill_map.yaml`:**
   ```yaml
   sc-preprocessing:
     before_run:
       - 01_workflow_guides/scrnaseq-scanpy-core-analysis.md
     after_run:
       - 03_best_practices/scrnaseq-scanpy-core-analysis--scanpy_best_practices.md
     on_error:
       - 04_troubleshooting/scrnaseq-scanpy-core-analysis--troubleshooting_guide.md
     interpretation:
       - 06_interpretation_guides/...

   bulkrna-de:
     before_run:
       - 01_workflow_guides/bulk-rnaseq-counts-to-de-deseq2.md
     after_run:
       - 03_best_practices/bulk-rnaseq-counts-to-de-deseq2--decision-guide.md
     on_error:
       - 04_troubleshooting/bulk-rnaseq-counts-to-de-deseq2--troubleshooting.md
   ```

2. **Extend KnowledgeAdvisor with skill-aware methods:**
   ```python
   def get_skill_guidance(self, skill_name: str, phase: str = "before_run") -> str:
       """Get relevant knowledge for a specific skill and execution phase."""
   ```

3. **Use during execution:**
   - Bot system prompt includes per-skill knowledge hints
   - CLI interactive mode auto-suggests relevant docs

**Key files:**
- New: `knowledge_base/skill_map.yaml`
- Modify: `omicsclaw/knowledge/retriever.py` — add `get_skill_guidance()`
- Modify: `omicsclaw/knowledge/indexer.py` — parse `skill_map.yaml` during build

### Stage 4: Fill knowledge coverage gaps

**Goal:** Balance knowledge coverage across all 6 OmicsClaw domains.

**Priority additions:**

| Domain | Missing | Action |
|--------|---------|--------|
| Spatial | Workflows, best practices, troubleshooting for all 15 skills | Write 5-8 key docs covering spatial preprocessing, domain identification, SVG detection |
| Metabolomics | Everything | Write 3-4 docs covering XCMS preprocessing, peak detection, annotation |
| Proteomics | Almost everything | Write 3-4 docs covering MS QC, quantification, differential abundance |
| Single-cell | Missing: ambient removal, doublet detection, GRN, cell communication | Write 4 docs for the newer skills |

**Approach:** For each skill that lacks knowledge coverage:
1. Extract the "best practices" and "common pitfalls" sections from SKILL.md
2. Expand into standalone knowledge documents
3. Link via skill_map.yaml

### Stage 5: Improve search quality

**Goal:** Better retrieval without over-engineering.

**Approach (pragmatic, no vector DB):**

1. **Synonym expansion in FTS5 queries**: Before searching, expand common synonyms:
   ```python
   SYNONYMS = {
       "normalize": ["normalization", "scaling", "transform"],
       "batch effect": ["batch correction", "combat", "harmony"],
       "de": ["differential expression", "deg", "differentially expressed"],
   }
   ```
   Append synonyms to the FTS5 query to improve recall.

2. **Better search_terms in frontmatter**: Each knowledge doc should list explicit `search_terms` in YAML frontmatter:
   ```yaml
   search_terms: [normalization, scaling, log transform, library size, depth normalization, CPM, TPM, RPKM]
   ```

3. **Boost recently relevant docs**: If a skill just ran, boost the BM25 score for docs linked to that skill (via skill_map.yaml).

**Key files:**
- Modify: `omicsclaw/knowledge/store.py` — add synonym expansion in `_to_fts5_query()`
- Modify: `omicsclaw/knowledge/indexer.py` — ensure search_terms from frontmatter are indexed
- Modify: knowledge_base docs — add `search_terms` frontmatter

---

## 5. Recommended Implementation Order

```
Stage 1 (Contextual injection)  →  Stage 2 (Inline mode)
         ↘                              ↙
          Stage 3 (Skill-knowledge map)
                    ↓
          Stage 4 (Coverage gaps)
                    ↓
          Stage 5 (Search quality)
```

**Stage 1 + 2** deliver the core value proposition: knowledge surfaces automatically during analysis. Implement these first.

**Stage 3** is the structural foundation that makes 1+2 work well at scale.

**Stage 4** is content work that can be done incrementally.

**Stage 5** is polish that improves quality but isn't blocking.

---

## 6. What to Keep vs. Change

| Component | Verdict | Reason |
|-----------|---------|--------|
| SQLite FTS5 backend | **Keep** | Right tool for this scale, no need for vector DB |
| 10-category taxonomy | **Keep** | Well-designed, covers the analysis lifecycle |
| Chunk-based retrieval | **Keep** | Good granularity for LLM consumption |
| `/guide` command | **Demote** | Keep as explicit query, but not the primary way to access knowledge |
| `consult_knowledge` tool | **Keep + enhance** | Add skill-context parameter for skill-aware queries |
| Prompt injection approach | **Enhance** | Make system prompt rules more specific and actionable |
| Standalone knowledge docs | **Keep + link** | Add explicit skill associations via skill_map.yaml |
| Domain/type filtering | **Keep** | Already works, just needs skill-level filtering too |

---

## 7. Anti-Patterns to Avoid

1. **Don't add vector embeddings yet** — FTS5 is sufficient for 424 documents. Embedding-based search adds complexity (model dependency, indexing time, storage) with marginal benefit at this scale.

2. **Don't merge knowledge into SKILL.md** — Keep them separate. SKILL.md is the "what and how" of execution. Knowledge base is the "why, when, and what if" of analysis decisions. Different audiences, different update cadences.

3. **Don't auto-query knowledge on every skill run** — This adds latency and noise. Only inject knowledge when there's a clear trigger (first run, error, user asks "why").

4. **Don't over-engineer the skill_map.yaml** — Start with the 10-15 most-used skills and expand based on user feedback.
