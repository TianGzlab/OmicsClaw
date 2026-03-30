# OmicsClaw 框架架构全面分析报告

> 生成日期：2026-03-27

---

## 一、框架完整架构图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          USER INTERFACES                                    │
│                                                                             │
│  ┌──────────┐  ┌──────────────┐  ┌────────┐  ┌──────────┐  ┌────────────┐ │
│  │ CLI      │  │ Interactive  │  │  TUI   │  │ Telegram │  │   Feishu   │ │
│  │omicsclaw │  │ REPL         │  │Textual │  │   Bot    │  │    Bot     │ │
│  │   .py    │  │interactive.py│  │ tui.py │  │          │  │            │ │
│  └────┬─────┘  └──────┬───────┘  └───┬────┘  └────┬─────┘  └─────┬──────┘ │
│       │               │              │             │              │        │
└───────┼───────────────┼──────────────┼─────────────┼──────────────┼────────┘
        │               │              │             │              │
        └───────────────┴──────┬───────┴─────────────┴──────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         CORE ENGINE LAYER                                   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    OmicsRegistry (registry.py)                      │   │
│  │  ┌──────────────┐  ┌──────────────────┐  ┌───────────────────┐    │   │
│  │  │ _hardcoded   │  │ load_all()       │  │ load_lightweight()│    │   │
│  │  │ _skills (70+)│  │ FS scan → merge  │  │ LazySkillMetadata │    │   │
│  │  └──────────────┘  └──────────────────┘  └───────────────────┘    │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌──────────────────────── ROUTING ────────────────────────────────────┐   │
│  │                                                                     │   │
│  │  ┌─────────────────┐  ┌──────────────┐  ┌───────────────────────┐ │   │
│  │  │ Keyword Router  │  │  LLM Router  │  │   Hybrid Router      │ │   │
│  │  │ substring match │  │ 12 providers │  │ keyword→LLM fallback │ │   │
│  │  │ O(1) fast       │  │ semantic     │  │ threshold: 0.5       │ │   │
│  │  └─────────────────┘  └──────────────┘  └───────────────────────┘ │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌─────────────┐  ┌──────────────┐   │
│  │ run_skill()  │  │ DependencyMgr│  │ Knowledge   │  │ Session/     │   │
│  │ subprocess   │  │ tier-based   │  │ Advisor     │  │ Memory Mgr   │   │
│  │ isolation    │  │ validation   │  │ SQLite FTS5 │  │ graph-based  │   │
│  └──────────────┘  └──────────────┘  └─────────────┘  └──────────────┘   │
│                                                                             │
│  ┌──────────────────── COMMON UTILITIES ──────────────────────────────┐   │
│  │  report.py (header/footer/json) │ checksums.py │ session.py       │   │
│  └────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                       ORCHESTRATION LAYER                                   │
│                                                                             │
│  ┌───────────────────────────────────────────────────────────────────┐     │
│  │              omics_orchestrator.py (Multi-Domain)                  │     │
│  │  detect_domain() → route_query() → dispatch to domain orchestrator│     │
│  └──────────┬─────────────┬──────────────┬──────────────┬────────────┘     │
│             │             │              │              │                   │
│       ┌─────▼────┐  ┌────▼─────┐  ┌────▼─────┐  ┌────▼──────┐           │
│       │ spatial  │  │ sc       │  │ genomics │  │ proteomics│ ...        │
│       │ orch.py  │  │ orch.py  │  │ orch.py  │  │ orch.py   │           │
│       │ PIPELINES│  │          │  │          │  │           │           │
│       └──────────┘  └──────────┘  └──────────┘  └───────────┘           │
└─────────────────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          SKILL LAYER  (60+ skills)                          │
│                                                                             │
│  skills/                                                                    │
│  ├── spatial/ (16 skills)           ├── singlecell/scrna/ (13 skills)      │
│  │   ├── spatial-preprocess/        │   ├── sc-qc/                         │
│  │   │   ├── SKILL.md              │   ├── sc-preprocessing/               │
│  │   │   ├── spatial_preprocess.py │   ├── sc-doublet-detection/           │
│  │   │   └── tests/                │   ├── sc-cell-annotation/             │
│  │   ├── spatial-domains/          │   ├── sc-de/  sc-markers/             │
│  │   ├── spatial-de/               │   ├── sc-velocity/ sc-grn/            │
│  │   ├── spatial-annotate/         │   └── ...                             │
│  │   ├── spatial-deconv/           │                                        │
│  │   ├── spatial-velocity/         ├── genomics/ (10 skills)               │
│  │   ├── spatial-trajectory/       │   ├── genomics-qc/                    │
│  │   ├── ...                       │   ├── genomics-variant-calling/       │
│  │   ├── _lib/ (24 shared modules) │   └── ...                             │
│  │   └── orchestrator/             │                                        │
│  │                                  ├── proteomics/ (8 skills)             │
│  ├── bulkrna/ (13 skills)          ├── metabolomics/ (8 skills)            │
│  │   ├── bulkrna-de/               └── orchestrator/ (master)              │
│  │   ├── bulkrna-enrichment/                                                │
│  │   └── ...                                                                │
│  │                                                                          │
│  └── Each skill follows:                                                    │
│      skill-name/                                                            │
│      ├── SKILL.md          ← YAML frontmatter (auto-discovery)             │
│      ├── skill_name.py     ← Standalone subprocess (--input --output --demo)│
│      ├── tests/            ← pytest                                        │
│      └── _lib/ or _utils   ← Domain shared libs                           │
└─────────────────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                       KNOWLEDGE & MEMORY LAYER                              │
│                                                                             │
│  ┌─────────────────────────────┐    ┌──────────────────────────────────┐   │
│  │  knowledge_base/ (150 docs) │    │  omicsclaw/memory/ (graph-based) │   │
│  │  01_workflow_guides/        │    │  database.py + graph.py          │   │
│  │  02_decision_guides/        │    │  FastAPI server + search engine  │   │
│  │  05_method_references/      │    │  LRU eviction (1000 convos)     │   │
│  │  ...10 categories           │    │  Auto-capture datasets/analyses │   │
│  └─────────────────────────────┘    └──────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 二、数据流图：从用户查询到 Skill 执行

```
User: "帮我做空间转录组的差异表达分析"
 │
 ├─[CLI]─→ omicsclaw.py run spatial-de --input data.h5ad --output ./results
 │
 ├─[Bot]─→ "spatial de" → bot/core.py → LLM function calling
 │           → tool: omicsclaw(skill="spatial-de", mode="file")
 │
 └─[Interactive]─→ /run spatial-de data.h5ad
 │
 ▼
┌─── omics_orchestrator.py ───────────────────────────────────────┐
│ 1. detect_domain("spatial de analysis on h5ad")                 │
│    → file ext .h5ad → "spatial"                                 │
│    → keyword "differential expression" → "spatial-de"           │
│ 2. route_query_unified(mode="hybrid", threshold=0.5)            │
│    → keyword score 0.85 → use keyword result                    │
│    → OR if <0.5 → fallback to LLM router (12 providers)       │
└─────────────────────────────────────────────────────────────────┘
 │
 ▼
┌─── OmicsRegistry ──────────────────────────────────────────────┐
│ registry.skills["spatial-de"] → {                               │
│   script: skills/spatial/spatial-de/spatial_de.py,              │
│   allowed_extra_flags: {"--groupby", "--method", ...},          │
│   demo_args: ["--demo"],                                        │
│   requires_preprocessed: True                                   │
│ }                                                               │
└─────────────────────────────────────────────────────────────────┘
 │
 ▼
┌─── run_skill() ────────────────────────────────────────────────┐
│ 1. Resolve legacy aliases                                       │
│ 2. Security: filter extra_args through allowed_extra_flags      │
│ 3. Build command:                                               │
│    python skills/spatial/spatial-de/spatial_de.py               │
│      --input data.h5ad --output ./results --groupby leiden      │
│ 4. Set PYTHONPATH → project root                                │
│ 5. subprocess.run() ← ISOLATED EXECUTION                       │
└─────────────────────────────────────────────────────────────────┘
 │
 ▼
┌─── spatial_de.py (Skill Process) ──────────────────────────────┐
│ 1. Load h5ad → validate preprocessed                            │
│ 2. Run DE via _lib/de.py (Wilcoxon/t-test/logistic)           │
│ 3. Generate figures/ → volcano, heatmap, dotplot               │
│ 4. Write tables/ → de_results.csv, top_markers.csv             │
│ 5. Write report.md + result.json                                │
│ 6. Save processed.h5ad (if chaining)                           │
└─────────────────────────────────────────────────────────────────┘
 │
 ▼
Output: ./results/{report.md, result.json, figures/, tables/, reproducibility/}
```

---

## 三、Skill 扩展性评估

### 新增 Skill 的完整步骤

以"新增一个蛋白质组 PTM-localization skill"为例：

| 步骤 | 操作 | 涉及文件 | 是否自动化 |
|------|------|----------|-----------|
| 1 | 创建目录 `skills/proteomics/proteomics-ptm-loc/` | 新建目录 | 手动 |
| 2 | 编写 `SKILL.md` (YAML frontmatter + 文档) | 新建文件 | 模板引导 |
| 3 | 编写 `proteomics_ptm_loc.py` (主脚本) | 新建文件 | 模板引导 |
| 4 | Registry 自动发现 | `registry.py load_all()` | **自动** |
| 5 | 添加硬编码条目 (可选，增强安全/别名) | `registry.py` | 手动 |
| 6 | 添加路由关键词 | `omics_orchestrator.py` | 手动 |
| 7 | 添加到 domain orchestrator | `proteomics orchestrator` | 手动 |
| 8 | 更新 CLAUDE.md 路由表 | `CLAUDE.md` | 手动 |
| 9 | 编写测试 | `tests/` | 手动 |

**核心结论：步骤 4 是自动的（Registry FS 扫描），但步骤 5-8 需要手动散布更新到 4-5 个不同文件。**

---

## 四、框架优点

### 1. Subprocess 隔离执行 — 安全且稳健

每个 skill 作为独立子进程运行，依赖隔离，崩溃不影响主进程。`allowed_extra_flags` 白名单机制防止 CLI 注入。这是最大的架构优势。

### 2. 双层注册：自动发现 + 硬编码兜底

`load_all()` 扫描 `skills/` 目录自动发现新 skill，同时 `_hardcoded_skills` 保证核心 skill 即使在文件损坏时也能路由。两层合并策略兼顾灵活性和可靠性。

### 3. 三模态路由（keyword / LLM / hybrid）

Keyword 路由零延迟、确定性；LLM 路由处理模糊语义查询；Hybrid 模式两者结合，confidence < 0.5 自动降级到 LLM。支持 12 种 LLM provider，适应国内外不同部署环境。

### 4. 统一的 Skill 约定

所有 skill 遵循相同的目录结构（SKILL.md + script + tests），相同的 CLI 接口（`--input --output --demo`），相同的输出格式（report.md + result.json + figures/ + tables/）。新开发者可以快速上手。

### 5. 分层 _lib 共享库

每个 domain 有自己的 `_lib/` 共享模块（spatial 24 个，singlecell 20 个），避免跨 domain 耦合，同时域内复用充分（如 `adata_utils`, `viz_utils`, `de.py`）。

### 6. 多前端统一后端

CLI、Interactive REPL、TUI、Telegram Bot、Feishu Bot 五个前端共享同一套 Registry + run_skill() 后端，一次添加 skill 全渠道可用。

### 7. 知识库系统

150 篇文档的 SQLite FTS5 知识库，为 LLM 路由和用户指导提供领域知识支撑，不仅仅是代码执行，还能解释"为什么"。

### 8. LazySkillMetadata 快速启动

不需要 import 所有 skill 模块即可获取元数据（name, description, domain），通过 YAML frontmatter 解析实现，适合 60+ skill 的规模。

---

## 五、框架缺点与改进建议

### 1. 路由信息散布在 4-5 个文件中 — 最大的扩展性障碍

```
新增一个 skill 需要同步更新：
├── skills/{domain}/{skill}/SKILL.md          ← skill 定义
├── omicsclaw/core/registry.py                ← 硬编码条目 (可选但推荐)
├── skills/orchestrator/omics_orchestrator.py  ← DOMAIN_KEYWORD_MAPS
├── skills/{domain}/orchestrator/*_orch.py     ← 域编排器 KEYWORD_MAP
└── CLAUDE.md                                  ← 路由表文档
```

**问题**：忘记更新任何一个文件都会导致 skill 可发现但不可路由，或文档与实际不一致。随着 skill 数量增长，这个同步成本线性增长。

**建议**：将 `trigger_keywords` 放在 SKILL.md frontmatter 中（模板已支持但未被路由器使用），让 orchestrator 动态从 Registry 的 LazySkillMetadata 读取关键词，实现"单点定义，全局生效"。

### 2. 硬编码 skill 列表（912 行 registry.py）与自动发现的矛盾

Registry 同时维护硬编码字典和动态扫描，合并规则是"硬编码优先"。但 70+ skill 的硬编码列表已经很长，每次新增都要改 registry.py。

**建议**：将硬编码作为"migration fallback"而非主数据源。让 SKILL.md frontmatter 承载 `allowed_extra_flags`, `legacy_aliases`, `saves_h5ad` 等元数据，registry 只做扫描和缓存。保留硬编码仅用于极少数需要特殊处理的 skill。

### 3. 跨 domain 无共享 _lib，存在代码重复

spatial/_lib 和 singlecell/_lib 各自有 `de.py`, `integration.py`, `annotation.py`, `trajectory.py` 等同名模块，功能高度重叠（差异表达、批次校正、轨迹推断的核心逻辑相同，只是数据格式不同）。

**建议**：抽取 `omicsclaw/common/analysis/` 层，放置跨 domain 的通用算法（DE dispatcher, enrichment runner, integration methods），各 domain 的 `_lib/` 只做数据格式适配。

### 4. 缺少 Skill 接口契约 (Interface / Protocol)

当前 skill 通过"约定"而非代码契约来保证一致性。没有基类或 Protocol 定义强制 skill 必须实现 `main()`, `get_demo_data()`, `generate_figures()` 等方法。

**建议**：定义一个轻量 Protocol 或 ABC：

```python
class SkillProtocol(Protocol):
    SKILL_NAME: str
    SKILL_VERSION: str
    def main(self) -> int: ...
    def get_demo_data(self) -> tuple[Any, str | None]: ...
```

不需要强制继承，用 Protocol 做静态检查即可。

### 5. Skill 间数据传递依赖文件系统

Pipeline 中 skill A 的输出 `processed.h5ad` 是 skill B 的输入，完全依赖文件路径传递。没有内存中的数据流机制。

**影响**：对于大文件（几 GB 的 h5ad），每步都要读写磁盘，性能开销大。且没有标准化的"上游输出 schema"验证，skill B 无法知道 skill A 是否真的做了它需要的预处理。

**建议（长期）**：引入轻量的 pipeline manifest（JSON），记录每步的输入/输出/参数/版本，让下游 skill 可以校验上游状态，而不仅仅是检查文件是否存在。

### 6. 测试覆盖薄弱

`test_registry.py` 仅 16 行，`test_registry_lazy.py` 仅 17 行。大多数 skill 的 tests/ 目录为空或只有 smoke test。对于 60+ skill 的系统，缺乏集成测试和 skill 输出格式验证测试。

**建议**：基于 `--demo` 模式建立自动化 smoke test 套件：每个 skill 运行 demo 模式，验证输出目录包含 `report.md` + `result.json` + 至少一个 figure。这可以作为 CI 的最低保障。

### 7. R 脚本集成不够成熟

`r_script_runner.py` 和 `r_bridge.py` 存在但集成程度不一。部分 genomics/metabolomics skill 需要 R（DESeq2, XCMS），但没有统一的 R 包依赖管理策略。

**建议**：在 `dependency_manager.py` 中增加 R 包 tier 定义，类似 Python 的 `DOMAIN_TIERS`，提供 `renv` 或 `conda` 的自动化安装指导。

### 8. CLAUDE.md 路由表是手动维护的文档，容易过时

CLAUDE.md 中有一个完整的 Skill Routing Table，但它是静态 Markdown。每次增删 skill 都需要手动更新。当前已有 60+ 条目，维护成本高且容易遗漏。

**建议**：编写一个 `generate_claude_md.py` 脚本，从 Registry + SKILL.md frontmatter 自动生成路由表部分，避免人工同步。

---

## 六、扩展性总评

| 维度 | 评分 | 说明 |
|------|------|------|
| 新增 Skill（同 domain） | **B+** | 自动发现 + 模板引导，但需手动更新 3-4 处路由配置 |
| 新增 Domain | **B-** | 需要改 registry、loader、orchestrator、CLAUDE.md，无自动化脚手架 |
| 新增分析方法（已有 skill） | **A** | _lib 共享模块 + dispatch 模式，加一个方法只需改 _lib 和 SKILL.md |
| 新增前端渠道 | **A** | 后端统一，新前端只需调用 run_skill() |
| 大规模并行开发 | **B** | Subprocess 隔离好，但路由配置散布导致 merge 冲突风险 |
| 维护可持续性 | **B** | 约定优于配置在 60 skills 规模下运转良好，但 100+ 时手动同步会成为瓶颈 |

**总体评价**：当前框架设计合理，在 60-80 个 skill 规模下运转良好。但如果目标是持续扩展到 100+ skill、新增更多组学 domain，最优先的改进是实现 **"SKILL.md 单点定义 → 路由/注册/文档自动生成"** 的机制，消除散布式配置的同步成本。
