# OmicsClaw `/research` Pipeline — 架构设计文档

> 更新日期: 2026-03-27
> 范围: `omicsclaw/agents/` 全模块 + skill 加载链 + 知识库集成 + 交互层

---

## 目录

1. [整体架构](#1-整体架构)
2. [核心组件详解](#2-核心组件详解)
3. [Skill 加载链路](#3-skill-加载链路)
4. [Knowledge Advisor 知识引导系统](#4-knowledge-advisor-知识引导系统)
5. [设计优点](#5-设计优点)
6. [已知限制与未来改进方向](#6-已知限制与未来改进方向)
7. [模块文件一览](#7-模块文件一览)

---

## 1. 整体架构

```
用户 → /research [pdf] --idea "..." → interactive.py._handle_research()
                                              │
                                              ▼
                                     ResearchPipeline(workspace)
                                              │
                        ┌─────────────────────┼─────────────────────┐
                        ▼                     ▼                     ▼
                 Intake Agent           deepagents Graph         Notebook Session
                 (PDF→MD, GEO)         (6 sub-agents)          (Jupyter kernel)
                        │                     │                     │
                        ▼                     ▼                     ▼
                 paper/01-04.md    planner → researcher →     analysis.ipynb
                 metadata.json     coder → analyst →          (load_skill 注入)
                 todos.md          writer → reviewer

用户 → /guide [topic]  → interactive.py._handle_guide()
                                │
                                ▼
                        LLM + consult_knowledge 工具
                                │
                                ▼
                        Knowledge Advisor (SQLite FTS5)
                        424 docs → 5335 chunks 索引
```

### 7 阶段流水线

| 阶段 | Agent | 工具 | 产出 |
|------|-------|------|------|
| intake | IntakeAgent | PDF转换, GEO解析 | `paper/` 目录, `metadata.json` |
| plan | planner-agent | think_tool | `plan.md` (含参数、成功信号) |
| research | research-agent | tavily_search, think_tool | 文献调研结果 |
| execute | coding-agent | skill_search, notebook_*, think_tool | `analysis.ipynb` |
| analyze | analysis-agent | notebook_read/read_cell/add_execute | 指标解读、图表 |
| write | writing-agent | think_tool | `final_report.md` |
| review | reviewer-agent | think_tool, tavily_search | JSON 审查报告 |

### 数据流

```
PDF ──[intake]──→ paper/02_methodology.md ──[注入 initial_prompt]──→ planner-agent
                                                                          │
                                                                    plan.md
                                                                          │
                                              coding-agent ◄──────────────┘
                                                   │
                                          skill_search() → AST 双通道函数提取
                                                   │        Pass 1: FunctionDef (helpers)
                                                   │        Pass 2: ImportFrom _lib (core)
                                                   │
                                          load_skill() → 动态模块导入
                                                   │
                                          notebook_add_execute() → 执行代码
                                                   │
                                          analysis.ipynb ──→ analysis-agent ──→ writing-agent
```

---

## 2. 核心组件详解

### 2.1 ResearchPipeline (`pipeline.py`)

**关键设计决策:**
- 使用 `deepagents.create_deep_agent()` 构建多 agent 图
- `CompositeBackend` 路由: `/` → 沙盒工作空间, `/skills/` → 只读技能目录
- `ToolErrorHandlerMiddleware` 捕获工具异常，返回 ToolMessage 而非崩溃
- `PipelineState` 支持 checkpoint/resume（JSON 持久化）
- Review 循环上限 3 次

**LLM 后端:**
- 支持 DeepSeek / OpenAI / Anthropic / 通用 OpenAI 兼容
- `SafeChatOpenAI` 包装类处理 DeepSeek 的 content 类型校验（list → string）
- 解析优先级: 构造参数 > `OC_LLM_PROVIDER` > `LLM_PROVIDER` > "deepseek"

### 2.2 Agent 配置 (`config.yaml`)

6 个 sub-agent 定义，每个有独立的 system_prompt、tools、skills 列表:

| Agent | 工具权限 | 核心约束 |
|-------|---------|---------|
| planner-agent | think_tool | 不写代码，只输出 plan.md。从论文提取精确参数。自检聚焦于成功信号可度量性、计算复杂度、方法回退策略 — 不验证函数 API 存在性（交由 coder 在执行时通过 skill_search 动态验证） |
| research-agent | tavily_search, think_tool | 最多 5 次搜索 |
| coding-agent | skill_search, notebook_*, think_tool | 先 skill_search 再写代码。Tier1=skill, Tier2=自定义。系统提示仅包含 1 个模式示例 + "不要猜函数名，以 skill_search 返回为准" |
| analysis-agent | notebook_read/read_cell/add_execute, think_tool | 不编造数据 |
| writing-agent | think_tool | 无文件 I/O。不编造引用 |
| reviewer-agent | think_tool, tavily_search | JSON 输出。最多检查 3 条引用 |

### 2.3 Tool Registry (`tools.py`)

```python
tool_registry = {
    "think_tool":            # 反思/规划
    "tavily_search":         # 网络搜索
    "omicsclaw_execute":     # CLI 技能执行
    "skill_search":          # 注册表搜索 + AST 双通道函数提取
    "notebook_create":       # 创建 notebook + kernel
    "notebook_add_execute":  # 插入 cell 并执行
    "notebook_read":         # 读取 notebook 概览
    "notebook_read_cell":    # 读取单个 cell 详情
}
```

### 2.4 Intake (`intake.py`)

三种输入模式:
- **Mode A**: PDF + idea → 自动提取 GEO 号下载数据
- **Mode B**: PDF + idea + h5ad → 使用用户提供的数据
- **Mode C**: idea only → 纯研究模式

PDF 转换管线: `opendataloader-pdf` → `pypdf` → `pdftotext` (三级 fallback)

---

## 3. Skill 加载链路

### 3.1 架构概览

OmicsClaw 的技能采用 **核心逻辑与脚本外壳分离** 的架构:

```
skills/<domain>/<skill-dir>/
    ├── <skill_name>.py          # 外壳脚本: main(), generate_figures(), write_report()
    ├── SKILL.md                 # 元数据 + 文档
    └── tests/

skills/<domain>/_lib/            # 可选，推荐用于复杂域
    ├── preprocessing.py         # 核心逻辑: preprocess(), normalize(), ...
    ├── de.py                    # 核心逻辑: run_de(), run_pydeseq2()
    └── ...
```

### 3.2 自动发现 → 搜索 → 加载 全链路

```
                    ┌─ OmicsRegistry.load_all() ──────────────────────────┐
                    │  扫描 skills/<domain>/<skill-dir>/                  │
                    │  读取 SKILL.md frontmatter (LazySkillMetadata)      │
                    │  生成 registry.skills[alias] = {script, domain, …}  │
                    └────────────────┬────────────────────────────────────┘
                                     │
              ┌──────────────────────┼──────────────────────┐
              ▼                      ▼                      ▼
    skill_search(query)      load_skill(name)       omicsclaw.py run
    AST 双通道扫描:           exec_module() 动态导入   subprocess 执行
    Pass1: FunctionDef       _lib 顶层 import 变     skill 脚本 main()
           → helpers          为 mod 的属性
    Pass2: ImportFrom _lib
           → ▶ core funcs
```

**核心设计原则:**
- `skill_search` 是函数发现的**唯一真相源**
- 核心函数（`_lib` 导入）用 `▶` 标记并置顶，辅助函数压缩为一行
- coding-agent 的 system prompt 只教 `load_skill()` 模式（1 个示例），不硬编码函数名
- 新增技能无需修改任何 prompt 或配置，自动被发现和展示

### 3.3 扩展性保证

贡献者只需遵循命名约定创建文件，技能即自动接入全链路:

| 步骤 | 自动化机制 |
|------|-----------|
| 放置 `skills/<domain>/<name>/<name>.py` + `SKILL.md` | `registry.load_all()` 自动发现 |
| 在 SKILL.md 中声明 `trigger_keywords` | `build_keyword_map()` 自动注册 NLP 路由 |
| 脚本从 `_lib` 导入核心函数 | `skill_search` AST Pass 2 自动提取并标记为 `▶ core` |
| 脚本定义 `main()` + `--demo` | CLI `omicsclaw.py run` 自动支持 |

详细贡献指南见 [CONTRIBUTING.md](../CONTRIBUTING.md)。

---

## 4. Knowledge Advisor 知识引导系统

### 4.1 架构

```
knowledge_base/                      omicsclaw/knowledge/
├── 01_workflow_guides/    (28)      ├── __init__.py         → 导出 KnowledgeAdvisor
├── 02_decision_guides/    (11)      ├── indexer.py          → 文档解析 + section 切分
├── 03_best_practices/     (14)      ├── store.py            → SQLite FTS5 存储
├── ...                              └── retriever.py        → 查询接口（公共 facade）
├── 10_domain_knowledge/
└── scripts/               (273)
    ├── 169 Python 脚本
    └── 104 R 脚本
```

**索引规模:** 424 文档 → 5335 searchable chunks

### 4.2 索引管线 (`indexer.py`)

**文档类型处理:**

| 类型 | 解析方式 | 切分策略 |
|------|---------|---------|
| `.md` | YAML frontmatter + `##` heading 切分 | 每个 section 一个 chunk（超过 3000 字符按段落再切） |
| `.py` | AST: module docstring + FunctionDef 签名 | docstring / function signatures / code preview |
| `.R` | Header comment + `name <- function()` 正则 | script header / function definitions / code preview |

**元数据推断:**
- `_infer_domain()`: frontmatter `category` → 路径片段 → `_DOMAIN_HINTS` 表 → 默认 `general`
- `_infer_doc_type()`: 目录名 (`01_workflow_guides` → `workflow`) → 文件后缀 → 默认 `reference`
- `_make_chunk()`: 统一的 Chunk 构建辅助函数，自动计算 content_hash

### 4.3 存储引擎 (`store.py`)

- SQLite FTS5，零外部依赖
- BM25 排序: `bm25(knowledge_fts, 2.0, 1.5, 1.0, 0.5)` (title 权重最高)
- **两级搜索**: strict AND → relaxed OR → LIKE fallback
- 域/类型过滤: `WHERE kc.domain = ? AND kc.doc_type = ?`
- 数据库路径: `~/.config/omicsclaw/knowledge.db`

### 4.4 查询接口 (`retriever.py`)

`KnowledgeAdvisor` 是唯一的公共 facade:

| 方法 | 用途 |
|------|------|
| `build(kb_path)` | 构建/重建索引 |
| `search(query, domain, doc_type, limit)` | 原始搜索（返回 dict 列表，未构建时抛 RuntimeError） |
| `search_formatted(query, ..., max_snippet)` | 格式化搜索（LLM tool 和 CLI 使用） |
| `list_topics(domain)` | 列出可用知识主题 |
| `stats()` | 索引统计 |
| `is_available()` | 检查索引是否就绪 |
| `get_document(source_path)` | 获取完整文档 |

### 4.5 集成点

| 入口 | 组件 | 机制 |
|------|------|------|
| Bot (Telegram/Feishu) | `bot/core.py` | `consult_knowledge` 工具 + guardrail #13 指引 LLM 主动调用 |
| CLI Interactive | `interactive.py` | `/guide` 命令 → 注入引导 prompt → LLM 调用 `consult_knowledge` |
| CLI 管理 | `omicsclaw.py` | `knowledge build/search/stats/list` 子命令 |

### 4.6 CLI 用法

```bash
python omicsclaw.py knowledge build                    # 构建索引
python omicsclaw.py knowledge search "deconvolution"   # 搜索
python omicsclaw.py knowledge stats                    # 统计
python omicsclaw.py knowledge list --domain bulkrna    # 列出主题
```

---

## 5. 设计优点

### 5.1 三层执行分级 (Tier 0/1/2)

```
Tier 0: deepagents sub-agent 委派（编排器路由）
Tier 1: OmicsClaw skill 函数（load_skill → 直接调用）← 优先
Tier 2: LLM 生成自定义代码（scanpy, scipy 等）← 兜底
```

每层都有优雅降级。如果 skill 不存在，coding-agent 不会卡死，而是写自定义代码。

### 5.2 Macro Agentic FS（CompositeBackend）

- 工作空间沙盒化（写操作限制在 workspace/ 内）
- 技能目录只读（agent 不能修改 SKILL.md 或脚本）
- 路径隔离防止意外覆盖

### 5.3 Planner ↔ Coder 职责分离

- **Planner** 读论文方法论 → 输出 plan.md（含参数、成功信号、回退策略）
- **Coder** 只读 plan.md，不读论文原文 → 通过 `skill_search` 动态发现函数
- 减少 token 浪费，避免 coder 被论文细节干扰
- Planner 不验证函数 API（无 `skill_search` 工具），Coder 在执行时验证

### 5.4 `skill_search` 作为函数发现的单一真相源

- coding-agent 的 system prompt 只教 `load_skill()` 模式（1 个示例）
- 具体函数名完全来自 `skill_search` 动态返回
- 新增技能自动被发现，无需修改任何 prompt
- 核心函数 (`_lib` 导入) 与辅助函数 (脚本内定义) 分层展示

### 5.5 Checkpoint/Resume 机制

- 每个 stage 完成后写 `.pipeline_checkpoint.json`
- 崩溃后 `--resume` 可跳过已完成的 stages
- intake 结果从 workspace 文件重建，不需重新处理 PDF

### 5.6 ToolErrorHandlerMiddleware

- 工具异常不会崩溃整个管线
- 返回 ToolMessage(status="error") 让 agent 自行决策
- 覆盖编排器和所有 sub-agent

### 5.7 Review 循环上限

- 防止无限审查-修改循环
- 3 次上限后强制退出，即使未达到完美也输出部分结果

### 5.8 Knowledge Advisor 零外部依赖

- SQLite FTS5 本地存储，无需向量数据库或网络
- Section 级切分避免返回 500+ 行完整文档
- 文档路径可配置（`OMICSCLAW_KNOWLEDGE_PATH` 环境变量）
- 未构建时优雅降级（`consult_knowledge` 返回提示信息）

---

## 6. 已知限制与未来改进方向

### 6.1 ~~单一 LLM 实例~~ [已解决]

**已解决**: 支持 per-agent model 配置。通过环境变量 `OC_{AGENT}_PROVIDER` / `OC_{AGENT}_MODEL`（如 `OC_PLANNER_MODEL=deepseek-reasoner`）可为每个 agent 指定独立的 LLM。优先级：per-agent env > pipeline env (`OC_LLM_*`) > global env (`LLM_*`/`OMICSCLAW_*`) > provider default。未设置 per-agent 变量的 agent 共享全局 LLM，零额外开销。

### 6.2 ~~`read_file` 工具确认~~ [已确认]

**已解决**: `read_file` 是 deepagents 框架的内置工具，由 `create_deep_agent()` 自动提供，无需在 config.yaml 的 `tools` 列表中声明。deepagents 自动提供的内置工具包括：`read_file`、`write_file`、`edit_file`、`ls`、`glob`、`grep`、`execute`。config.yaml 的 `tools` 列表仅需声明自定义工具（如 `think_tool`、`skill_search`、`notebook_*` 等）。

### 6.3 Knowledge Advisor 集成到 /research [低]

当前 `/research` 管线不使用知识库。planner 和 coder 可以从决策指南和最佳实践中获益。

**改进方向:** 在 `tools.py` 的 tool registry 中添加 `consult_knowledge`，让 planner 和 coder 能查询知识库。

### 6.4 Notebook 超时管理 [低]

notebook_session.py 的超时设置（每条消息 5s，总 wall-clock 600s）不适合深度学习方法（Cell2Location 30min+）。

**改进方向:** 动态超时 / 后台执行 / 进度轮询。

### 6.5 Stage 粒度跳转 [低]

`--resume` 只能从上次 checkpoint 恢复。不能跳过特定 stage 或从中间 stage 开始。

**改进方向:** 支持 `--from-stage execute --skip research` 语法。

### 6.6 审查循环收敛性 [低]

reviewer → writer 循环没有增量修改跟踪，每次全文重写。3 次上限可能对复杂论文不足。

**改进方向:** 增量 diff 修改 + 自适应循环次数。

---

## 7. 模块文件一览

### 7.1 Research Pipeline (`omicsclaw/agents/`)

| 文件 | 行数 | 职责 |
|------|------|------|
| `pipeline.py` | ~840 | 主编排器, stage 跟踪, checkpoint, LLM 配置 |
| `tools.py` | ~600 | 共享工具: think, search, skill_search (双通道 AST), notebook_* |
| `prompts.py` | ~340 | 系统提示 (编排器 + 6 个 sub-agent) |
| `backends.py` | ~175 | 沙盒执行 + 只读技能 FS |
| `intake.py` | ~600 | PDF→MD 转换, GEO 解析, 工作空间初始化 |
| `middleware.py` | ~87 | 工具异常处理中间件 |
| `notebook_session.py` | ~470 | Jupyter kernel 管理, load_skill() 注入 |
| `config.yaml` | ~350 | Sub-agent 定义 (tools, prompts, 职责划分) |
| `__init__.py` | ~50 | 公开 API, 懒加载, 依赖检查 |

### 7.2 Knowledge Advisor (`omicsclaw/knowledge/`)

| 文件 | 行数 | 职责 |
|------|------|------|
| `__init__.py` | ~10 | 导出 KnowledgeAdvisor |
| `indexer.py` | ~430 | 文档解析 (.md / .py / .R), section 切分, 元数据推断, `_make_chunk()` |
| `store.py` | ~290 | SQLite FTS5 存储, BM25 排序, 两级搜索 |
| `retriever.py` | ~165 | KnowledgeAdvisor facade: search, list, stats, get_document |

### 7.3 集成修改

| 文件 | 修改内容 |
|------|---------|
| `bot/core.py` | `consult_knowledge` 工具定义 + 执行器 + TOOL_EXECUTORS 注册 + guardrail #13 |
| `omicsclaw/interactive/_constants.py` | `/guide` 命令注册 |
| `omicsclaw/interactive/interactive.py` | `_handle_guide()` 函数 + `/guide` 分发逻辑 |
| `omicsclaw.py` | `knowledge` 子命令 (build/search/stats/list) |
