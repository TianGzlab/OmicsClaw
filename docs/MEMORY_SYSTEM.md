# Memory System — Core Value & Comparison

## Executive Summary

OmicsClaw bot's memory system transforms it from a **stateless Q&A tool** into a **persistent research assistant** that remembers your data, analyses, and preferences across conversations.

---

## Without Memory vs With Memory

### Scenario: Multi-Step Spatial Analysis

#### ❌ Without Memory (Stateless Bot)

```
User: "Preprocess my Visium data"
Bot: ✅ Runs preprocessing
     📊 Shows QC plots

[User closes chat, reopens next day]

User: "Find spatial domains"
Bot: ❓ "Which dataset? Please upload again"
User: [Re-uploads 2GB file]
Bot: ❓ "Has it been preprocessed?"
User: "Yes, yesterday"
Bot: ⚠️  "I don't remember. Let me preprocess again..."
     [Wastes 10 minutes re-running QC]

User: "What clustering method did I use last time?"
Bot: 🤷 "I don't have access to previous conversations"
```

**Pain Points:**
- Re-upload data every session
- Re-explain context repeatedly
- No analysis lineage tracking
- Cannot resume interrupted workflows
- Loses user preferences

---

#### ✅ With Memory (Persistent Bot)

```
User: "Preprocess my Visium data"
Bot: ✅ Runs preprocessing
     💾 Saves: DatasetMemory(file_path, platform=Visium, n_obs=5000, state=normalized)
     💾 Saves: AnalysisMemory(skill=preprocessing, method=scanpy, duration=45s)

[User closes chat, reopens next day]

User: "Find spatial domains"
Bot: 🧠 Loads context:
     - Current Dataset: visium_sample.h5ad (Visium, 5000 obs, normalized)
     - Recent: preprocessing (scanpy) - completed

     ✅ "Using your preprocessed Visium data (5000 spots, normalized yesterday).
         Running spatial domain detection..."
     💾 Saves: AnalysisMemory(skill=domains, parent=preprocessing_id)

User: "Use the same clustering as last time"
Bot: 🧠 Recalls: PreferenceMemory(key=clustering_method, value=leiden, resolution=0.8)
     ✅ "Applying leiden clustering (resolution=0.8) as before"
```

**Benefits:**
- Zero re-uploads (remembers file paths)
- Automatic context restoration
- Tracks analysis lineage (preprocessing → domains → ...)
- Learns user preferences
- Resumes interrupted work

---

## Core Differences

| Aspect | Without Memory | With Memory |
|--------|----------------|-------------|
| **Session Continuity** | Every chat starts from zero | Persistent across restarts |
| **Data Handling** | Re-upload every time | Remember file paths & metadata |
| **Analysis Tracking** | No history | Full lineage (parent → child) |
| **User Preferences** | Forget after chat ends | Learn & apply automatically |
| **Context Awareness** | "Which dataset?" | "Using your Visium data from yesterday" |
| **Workflow Resume** | Cannot resume | Pick up where you left off |
| **Multi-Step Pipelines** | Manual coordination | Automatic dependency tracking |

---

## Memory Types & Use Cases

### 1. DatasetMemory
**Stores:** File path, platform (Visium/Xenium), dimensions, preprocessing state

**Value:**
- No re-uploads (bot remembers `data/visium_brain.h5ad`)
- Knows preprocessing status (raw → QC → normalized → clustered)
- Prevents redundant QC runs

**Example:**
```python
DatasetMemory(
    file_path="data/visium_brain.h5ad",
    platform="Visium",
    n_obs=5000,
    n_vars=2000,
    preprocessing_state="normalized"
)
```

---

### 2. AnalysisMemory
**Stores:** Skill, method, parameters, parent analysis, output path, duration

**Value:**
- Reproducibility (exact parameters logged)
- Lineage tracking (preprocessing → clustering → DE)
- Performance monitoring (duration trends)
- Resume interrupted pipelines

**Example:**
```python
AnalysisMemory(
    skill="spatial-domains",
    method="leiden",
    parameters={"resolution": 0.8, "n_neighbors": 15},
    parent_analysis_id="preprocessing_abc123",
    duration_seconds=120.5
)
```

---

### 3. PreferenceMemory
**Stores:** User habits (clustering method, plot style, species)

**Value:**
- Auto-apply preferred methods
- Reduce repetitive parameter input
- Personalized defaults

**Example:**
```python
PreferenceMemory(
    domain="spatial-preprocessing",
    key="clustering_method",
    value="leiden",
    is_strict=False  # Soft preference, can override
)
```

---

### 4. InsightMemory
**Stores:** Biological interpretations (cluster = "T cells", domain = "tumor boundary")

**Value:**
- Preserve domain knowledge across sessions
- Build project-specific ontology
- Avoid re-annotating same clusters

**Example:**
```python
InsightMemory(
    source_analysis_id="clustering_xyz",
    entity_type="cluster",
    entity_id="cluster_3",
    biological_label="CD8+ T cells",
    confidence="user_confirmed"
)
```

---

### 5. ProjectContextMemory
**Stores:** Global scientific context (species, tissue, disease model)

**Value:**
- Contextual analysis suggestions
- Species-specific parameter defaults
- Tissue-aware interpretation

**Example:**
```python
ProjectContextMemory(
    project_goal="Characterize tumor microenvironment in PDAC",
    species="mouse",
    tissue_type="pancreas",
    disease_model="KPC"
)
```

---

## Real-World Impact

### Use Case 1: Interrupted Analysis
**Without Memory:**
```
Day 1: Preprocess → Cluster → [Bot crashes]
Day 2: Start over from preprocessing
```

**With Memory:**
```
Day 1: Preprocess → Cluster → [Bot crashes]
Day 2: Bot: "You completed clustering yesterday. Next: differential expression?"
```

---

### Use Case 2: Parameter Consistency
**Without Memory:**
```
User: "Cluster with leiden, resolution 0.8"
[Next week]
User: "What resolution did I use?"
Bot: "I don't know"
```

**With Memory:**
```
User: "Cluster with leiden, resolution 0.8"
[Next week]
User: "Cluster this new sample the same way"
Bot: "Applying leiden (resolution=0.8) as before"
```

---

### Use Case 3: Multi-Sample Projects
**Without Memory:**
```
User: "Analyze sample A" → [Upload, preprocess, cluster]
User: "Analyze sample B" → [Upload, preprocess, cluster]
User: "Compare A and B" → Bot: "Which samples? Upload both"
```

**With Memory:**
```
User: "Analyze sample A" → [Saved as dataset_A]
User: "Analyze sample B" → [Saved as dataset_B]
User: "Compare A and B" → Bot: "Loading your two Visium samples..."
```

---

## Privacy & Security

### What Memory Does NOT Store
- ❌ Raw gene expression matrices
- ❌ Absolute file paths (only relative)
- ❌ Personally identifiable information
- ❌ Unencrypted biological labels

### What Memory DOES Store
- ✅ File metadata (dimensions, platform)
- ✅ Analysis parameters & methods
- ✅ Relative file paths (`data/sample.h5ad`)
- ✅ Sanitized biological labels (encrypted)

---

## Technical Architecture

```
┌─────────────────────────────────────────────┐
│  User: "Find spatial domains"               │
└──────────────────┬──────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────┐
│  SessionManager.load_context()              │
│  ├─ Get ProjectContextMemory (last 1)       │
│  ├─ Get DatasetMemory (last 2)              │
│  ├─ Get AnalysisMemory (last 3)             │
│  ├─ Get PreferenceMemory (last 5)           │
│  └─ Get InsightMemory (last 3)              │
└──────────────────┬──────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────┐
│  LLM Context Injection                      │
│  "Project: TME in TNBC (Homo sapiens)       │
│   Current Dataset: visium.h5ad (normalized) │
│   Recent: preprocessing (scanpy) - done     │
│   Preference: clustering_method=leiden      │
│   Insight: cluster_3 = CD8+ T cells"       │
└──────────────────┬──────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────┐
│  LLM Decision                               │
│  "User wants domains on preprocessed data.  │
│   Use leiden (their preference)"            │
└──────────────────┬──────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────┐
│  Execute Skill + Save New Memories          │
│  ├─ Run spatial-domains skill               │
│  └─ Save AnalysisMemory(skill=domains)      │
└─────────────────────────────────────────────┘
```

---

## Memory Features

### TTL / Automatic Expiration

Sessions and their memories are automatically expired after a configurable period (default: 30 days). Set `OMICSCLAW_MEMORY_TTL_DAYS` in `.env`:

```env
OMICSCLAW_MEMORY_TTL_DAYS=30  # Default. Set 0 to disable TTL.
```

Cleanup runs on startup and periodically (every 100 memory operations).

### Memory Search

Search across all memory content for a session:

```python
results = await store.search_memories(session_id, "brain")
# Finds all memories containing "brain" (case-insensitive)
# Works across encrypted fields (decrypt → search → return)

# Filter by type
datasets = await store.search_memories(session_id, "visium", memory_type="dataset")
```

### Deduplication

The memory system prevents duplicate entries:

- **DatasetMemory**: Deduplicated by `file_path`. Saving the same file path updates the existing record.
- **PreferenceMemory**: Deduplicated by `domain` + `key`. Changing a preference updates the value in-place.

### Update Re-encryption

When updating memory fields via `update_memory()`, the system:
1. Decrypts existing data
2. Merges in the updates
3. Re-encrypts the entire object

This prevents plaintext leakage of sensitive fields during partial updates.

### Connection Pooling

The SQLite backend maintains a persistent connection with WAL journaling and foreign key enforcement. PRAGMAs are set once on connection creation, not per-operation.

---

## Performance Considerations

### Memory Overhead
- **Storage:** ~1KB per memory node (SQLite)
- **Retrieval:** <10ms for context loading
- **Context Size:** ~500 tokens (2 datasets + 3 analyses + 5 prefs)

### Scalability
- **Per-user isolation:** Each session has independent memory
- **Automatic cleanup:** Old sessions can be pruned
- **Efficient queries:** Indexed by session_id + memory_type

---

## Migration Path

### Enabling Memory (Already Done)
```python
# bot/core.py
from bot.memory.backends.sqlite import SQLiteMemoryStore

store = SQLiteMemoryStore("bot_memory.db")
await store.initialize()
session_mgr = SessionManager(store)
```

### Disabling Memory (Fallback)
```python
# Use NullMemoryStore (no-op implementation)
class NullMemoryStore(MemoryStore):
    async def save_memory(self, *args): pass
    async def get_memories(self, *args): return []
```

---

## Conclusion

**Memory transforms OmicsClaw from a tool into a collaborator.**

| Metric | Without Memory | With Memory |
|--------|----------------|-------------|
| Re-uploads per week | 10-20 | 0 |
| Context re-explanation | Every chat | Once |
| Analysis reproducibility | Manual notes | Automatic |
| Workflow interruption cost | Restart from scratch | Resume instantly |
| User frustration | High | Low |

**Bottom line:** Memory is the difference between a chatbot and a research partner.
