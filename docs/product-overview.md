# OmicsClaw 产品全景文档

> **文档说明**
>
> 这份文档的目的是：**让任何没有写过代码的新同事，在 30 分钟内完全理解 OmicsClaw 这个产品到底有哪些能力、每块能力在整体中处于什么位置、一个模块和另一个模块如何协同**。
>
> 它的受众包括：
>
> - **新加入的工程师 / 产品 / 设计 / 运营**——用它做 onboarding 的第一份材料
> - **生物信息学家 / 多组学研究者**——评估 OmicsClaw 能不能替代自己手头的脚本和 SOP
> - **产品介绍工作**——需要对外讲解 OmicsClaw 时的事实基础
> - **文案工作者**——写交互文案、营销文案、帮助文档时，需要知道某个词（比如 "Skill"、"KnowHow"、"Surface"、"Capability resolver"）在产品体系里代表什么
> - **任何需要在修改某个局部前，先理解它与整体关系的人**
>
> 它**不是**：开发者参考手册、架构决策记录（ADR）、或者销售话术。它是**功能事实的汇总**——每一条描述都能在代码、`SKILL.md` 或 API 路由里找到对应。
>
> 文档基于对整个仓库（`omicsclaw/`、`skills/`、`bot/`、`frontend/`、`knowledge_base/`、`docs/`）的系统性调研生成，与代码同步的截止日期 2026-05-11。

---

## 目录

1. [OmicsClaw 是什么](#1-omicsclaw-是什么)
2. [核心概念词典](#2-核心概念词典)
3. [功能全景（按模块）](#3-功能全景按模块)
   - 3.1 [Skill 技能体系](#31-skill-技能体系)
   - 3.2 [Domain 组学领域](#32-domain-组学领域)
   - 3.3 [Routing 路由与 Capability Resolver](#33-routing-路由与-capability-resolver)
   - 3.4 [KnowHow 与 Active Guards](#34-knowhow-与-active-guards)
   - 3.5 [Memory 图记忆系统](#35-memory-图记忆系统)
   - 3.6 [Session 会话与恢复](#36-session-会话与恢复)
   - 3.7 [Interactive CLI / TUI](#37-interactive-cli--tui)
   - 3.8 [App Backend 桌面/网页后端](#38-app-backend-桌面网页后端)
   - 3.9 [Bot 多渠道机器人](#39-bot-多渠道机器人)
   - 3.10 [Research Pipeline 研究流水线](#310-research-pipeline-研究流水线)
   - 3.11 [Self-Evolution 自演化（AutoAgent）](#311-self-evolution-自演化autoagent)
   - 3.12 [Remote Execution 远程执行](#312-remote-execution-远程执行)
   - 3.13 [MCP 外部工具协议](#313-mcp-外部工具协议)
   - 3.14 [Onboarding、Auth 与 Settings](#314-onboardingauth-与-settings)
   - 3.15 [Outputs、Reports 与 Replot](#315-outputsreports-与-replot)
   - 3.16 [Knowledge Base 知识库](#316-knowledge-base-知识库)
   - 3.17 [CLI 命令行工具](#317-cli-命令行工具)
4. [系统架构全景](#4-系统架构全景)
5. [产品地图（全部 Surface 与路由）](#5-产品地图全部-surface-与路由)
6. [跨 Surface 差异：CLI vs TUI vs App vs Bot](#6-跨-surface-差异cli-vs-tui-vs-app-vs-bot)
7. [附录：关键模块速查](#7-附录关键模块速查)

---

## 1. OmicsClaw 是什么

### 一句话定位

**OmicsClaw 把本地多组学工具变成 AI 可调用的 Skill。**

LLM 负责理解你的科研问题、规划分析路径、组织参数和上下文；Python/R/CLI 工具在你的本地或远程 Linux 节点里跑出可复现的结果。OmicsClaw 不是另一个 ChatGPT 套壳，而是一个**把"自然语言意图"翻译成"可执行生物信息学操作"的中间层**——任何输出都能追溯到一个 `SKILL.md` 方法学文档和一段真实执行过的脚本。

### 解决的问题

传统多组学分析的痛点：

- 每次新项目都要重新拼脚本，参数和阈值散落在终端历史里
- Python（scanpy/scvi）、R（Seurat/DESeq2/CellChat）、命令行（STAR/samtools/MaxQuant）三套生态拼接困难
- 想用 LLM 助手时，要么把矩阵贴进 ChatGPT（不合规、不可控），要么自己用 LangChain 拼工具调用（开发成本高）
- 大数据集只能在服务器上，可桌面体验/对话体验只能在本地
- 跨多轮对话没有"记忆"，每次都要重新解释"我处理的是什么数据、上次走到哪一步、用了什么参数"

OmicsClaw 做的事：

- **89 个内置 Skill**横跨 8 大组学领域（spatial、singlecell、bulkrna、genomics、proteomics、metabolomics、orchestrator、literature），每个 Skill 都有 `SKILL.md` 方法学 + Python/R 脚本 + 演示数据
- **统一 Skill Runner 契约**：CLI、Interactive、Bot、桌面 App、远程 Job、研究流水线都通过同一个执行入口，参数白名单、产物布局、报告生成完全一致
- **本地优先（Local-first）**：原始数据从不离开你配置的运行时；只有上下文摘要和工具结果进入 LLM 调用
- **图记忆（Graph Memory）**：基于 SQLite/Postgres 的图数据库记录数据集、分析、洞见、偏好的血缘，按 Namespace 隔离不同用户和工作区
- **多 Surface（多端）共享同一心脏**：CLI、TUI、桌面 App、Telegram/Feishu/Discord/Slack/WeChat 等 9 个 Bot 渠道、远程执行 API、研究流水线，全部 import 同一个 `bot/core.py` 中央枢纽
- **远程模式（Remote）**：桌面/网页 UI 在本地，分析作业通过 SSH 隧道交给远程 Linux 节点的 `oc app-server` 执行
- **可演化（Self-Evolution）**：`omicsclaw/autoagent/` 用 LLM 元代理在受控 edit surface 内对参数和源代码做实验、评估、回滚——既能优化 Skill 参数，也能演化框架自身

### 定位一句话版本

> OmicsClaw 不是一个 AI 工具，而是一个**研究者 + LLM + 本地多组学工具栈协作的科研操作平台**。Skill 是一等公民，跟 SKILL.md 写一致的方法学，被多个 Surface 共同消费。

### 部署形态

OmicsClaw 是**单仓库 + 多 Surface** 的产品，所有形态共享同一份 Python 代码：

- **本地全栈安装（推荐）**：`bash 0_setup_env.sh` 走 conda + R + 生信 CLI 一站式，跑真实分析
- **轻量虚拟环境**：`pip install -e ".[interactive]"`，只装聊天、路由、Python-only Skill；适合开发、纯对话、CI
- **桌面 App / Web 前端**：`oc app-server` 跑 FastAPI 后端（默认 `127.0.0.1:8765`），前端是独立仓库 OmicsClaw-App 或浏览器
- **远程执行**：在远端 Linux 节点上跑 `oc app-server`，绑定 localhost，桌面 App 通过 SSH 隧道 + `OMICSCLAW_REMOTE_AUTH_TOKEN` 接入
- **Memory API（可选）**：`oc memory-server` 暴露图记忆 REST 接口（默认 `127.0.0.1:8766`），供桌面 Review & Audit 面板使用
- **多渠道 Bot**：`python -m bot.run --channels telegram,feishu,...`，9 个聊天渠道用同一份 LLM tool loop

> OmicsClaw 没有"云版本"——所有数据处理都在你自己控制的运行时里发生。只有 LLM API 调用走外部（你也可以指向自建模型/本地 ollama）。

### 支持的 LLM 与 Provider

OmicsClaw **不绑死模型**，通过 `LLM_PROVIDER` + `LLM_BASE_URL` + `LLM_API_KEY` + `OMICSCLAW_MODEL` 四元组配置任意 OpenAI 兼容端点。内置支持的 provider：

- **OpenAI**（gpt-4o, o-series）
- **Anthropic Claude**（claude-opus、claude-sonnet——通过 OpenAI 兼容代理或原生 API）
- **DeepSeek**（deepseek-chat、deepseek-reasoner）
- **Google Gemini**（gemini-pro 系列）
- **Custom**（任何 OpenAI 兼容端点，包括 vLLM、Ollama、TGI、自建 gateway）

Provider runtime 在 CLI、桌面 App 和 Bot 之间共享同一份解析逻辑——参见 [`omicsclaw/runtime/`](#37-interactive-cli--tui) 的 Provider Runtime Contract。

### 团队背景

OmicsClaw 的架构、Skill 设计和 local-first 理念受 [ClawBio](https://github.com/ClawBio/ClawBio) 启发——首个 bioinformatics-native 的 AI agent skill library。记忆和会话连续性参考了 [Nocturne Memory](https://github.com/Dataojitori/nocturne_memory)。维护团队来自 TianGzLab：

- **Luyi Tian** — Principal Investigator
- **Weige Zhou** — Lead Developer
- **Liying Chen** — Developer
- **Pengfei Yin** — Developer

> OmicsClaw 也兼容旧名 **SpatialClaw**——它由空间转录组（spatial transcriptomics）项目演化而来，现在跨 8 个领域。所有 17 个 spatial Skill 仍然可用，路由器会自动跨域分派。

---

## 2. 核心概念词典

**理解下面这 26 个名词是理解 OmicsClaw 的前提。每个概念的定义都严格对应代码路径或 SKILL.md 文档，不允许有"模糊用法"。**

| 概念 | 定义 | 对应代码/文件 |
|------|------|----------------|
| **Skill 技能** | 一个自包含的分析方法学 + 脚本单元，用 kebab-case 命名（如 `sc-de`、`spatial-preprocess`、`bulkrna-survival`）。每个 Skill 住在 `skills/<domain>/<skill-name>/`，包含一份 `SKILL.md`（方法学 + YAML frontmatter）和一个或多个可执行脚本。**避免**：tool、capability、analysis、function | `skills/<domain>/<skill>/SKILL.md`、`skills/<domain>/<skill>/*.py` |
| **Domain 组学领域** | 把 Skill 分组的 7 个组学类目 + 1 个元域：`singlecell`、`spatial`、`bulkrna`、`genomics`、`proteomics`、`metabolomics`、`literature`、`orchestrator`。**避免**：omics type、area、family | `skills/<domain>/INDEX.md` |
| **Skill Runner 执行器** | 把任意 Skill 跑起来并产出标准化 README + 笔记本的共享运行器，统一 CLI / Interactive / Bot / App / 远程 Job / 研究流水线的执行契约 | `omicsclaw/core/skill_result.py`、`docs/engineering/2026-05-07-skill-runner-contract.md` |
| **Routing 路由** | LLM 选定一个 Skill（或 `auto`）来回答用户查询的动作。模型发出 `omicsclaw(skill=...)` 工具调用；当 `skill='auto'` 时由 Capability Resolver 进一步分派 | `omicsclaw/routing/` |
| **Capability Resolver 能力解析器** | 把 `skill='auto'` 或域提示在运行时翻译成具体 Skill 名字的组件 | `omicsclaw/runtime/capability_resolver.*` |
| **KnowHow (KH)** | 一份**强制性科学约束**文档，存为 `knowledge_base/knowhows/KH-<slug>.md`，frontmatter 含 `domains`、`related_skills`、`critical_rule`、`search_terms`、`priority`。两种渲染模式：**Headline-only**（仅注入一行 `→ {label}: {critical_rule}` 到 system prompt）和**Full body**（通过 `read_knowhow` 工具按需拉取） | `knowledge_base/knowhows/KH-*.md` |
| **Active Guards 当前生效约束** | `KnowHowInjector.get_constraints(skill, query, domain)` 在当前请求中被采纳的 KH headline 集合。`read_knowhow` 工具的 description 会指示模型只为这个列表里的名字拉取全文 | `omicsclaw/runtime/system_prompt.py` |
| **System Prompt Builder** | `omicsclaw.runtime.system_prompt.build_system_prompt(surface, ...)`——唯一的共享系统提示组装函数，从 SOUL.md、predicate-gated 层、KH headline、能力简报、工具前言里拼出一份请求级的 system prompt。**任何代码都必须调用它，不允许就地拼接** | `omicsclaw/runtime/system_prompt.py` |
| **Surface 表面** | `build_system_prompt` 的参数之一，决定渲染哪种 prompt 形状：`bot`（完整对话）、`pipeline`（研究流水线编排器，自定义 base persona）等。不同 Surface 启用/关闭不同 predicate-gated 层和 KH 注入；同时也是产品语义上的"用户入口"概念（CLI、TUI、App、Bot） | `omicsclaw/runtime/system_prompt.py`、`omicsclaw/runtime/context_layers/` |
| **Predicate-gated layer 谓词门控层** | 当某个谓词触发时才注入的 system prompt 片段（如 `plot_intent`、`web_or_url_intent`、`skill_creation_intent`）；定义在 `_PREDICATE_GATED_RULES`，由 PR #109 引入，目的是把 baseline token 成本压低 | `omicsclaw/runtime/predicates.py`、`omicsclaw/runtime/context_layers/__init__.py` |
| **Preflight 预飞行检查** | 在 Skill 执行**之前**对用户输入文件做的校验（例如 `.h5ad` 是否带 `obs.batch` 列、count matrix 是否非负整数）。校验失败时不直接执行，而是把问题反问给用户 | `bot/preflight.py` |
| **Central hub 中央枢纽** | `bot/core.py`——所有 User-facing Surface 都 import 它，拿到 LLM tool loop、工具执行、preflight 处理、计费、审计。当前约 648 行（外加 `bot/agent_loop.py` 935 行、`bot/skill_orchestration.py` 771 行、`bot/preflight.py` 280 行）；规划分解记录在 `docs/adr/0001` | `bot/core.py`、`bot/agent_loop.py`、`bot/skill_orchestration.py`、`bot/preflight.py` |
| **User-facing entry 用户面入口** | 任何一个真人输入文字并读到回应的 Surface：`bot/`（9 个渠道）、`omicsclaw/app/`（桌面/网页 App 后端）、`omicsclaw/interactive/`（CLI + Textual TUI）。三者目前都委托给 `bot.core.llm_tool_loop` 和 `build_system_prompt(surface=bot)` | `bot/`、`omicsclaw/app/`、`omicsclaw/interactive/` |
| **Task-locked entry 任务锁定入口** | 跑固定非对话任务、用自有 micro-prompt 的入口；目前只有 `omicsclaw/autoagent/`（参数优化 + 框架自演化）。**故意**不共享用户面 builder | `omicsclaw/autoagent/` |
| **Research Pipeline 研究流水线** | `omicsclaw/agents/`——受 EvoScientist 启发的多 Agent 工作流（intake → plan → research → execute → analyze → write → review）。使用 `build_system_prompt(surface=pipeline)`，自定义 base persona，关闭 KH 注入 | `omicsclaw/agents/pipeline.py` |
| **Self-Evolution 自演化** | `omicsclaw/autoagent/`——元系统，要么 (a) 通过 directive loop 调参，要么 (b) 在受控 edit surface 内改源码。**作用于** OmicsClaw 而非**通过** OmicsClaw | `omicsclaw/autoagent/optimization_loop.py`、`omicsclaw/autoagent/harness_loop.py` |
| **Memory URI** | 一个 `domain://path` 字符串，给记忆一个逻辑地址，独立于行 id。例如 `dataset://pbmc.h5ad`、`core://agent` | `omicsclaw/memory/` |
| **Memory Domain 记忆域** | Memory URI 的顶层段——`core`、`dataset`、`analysis`、`insight`、`preference`、`project`、`session` 之一。**注意**：这是记忆系统内部的 7 个域，与 Skill 的 8 个组学 Domain 是两个完全独立的命名空间 | `omicsclaw/memory/engine.py` |
| **Namespace 命名空间** | 记忆隔离维度，存为 `paths`、`search_documents`、`glossary_keywords` 三张表的列。各 Surface 注入不同的值：CLI/TUI = workspace 绝对路径；Desktop = `app/<launch_id>`；Bot = `<platform>/<user_id>`；系统 = `__shared__`。**避免**：tenant、scope | `omicsclaw/memory/namespace_policy.py` |
| **`__shared__`** | 保留 Namespace，里面的行对所有其他 Namespace 都通过 Read fallback 可见。承载 `core://agent`、`core://kh/*`（每次 `init_db` 由 `seed_knowhows` 幂等种入）、系统词表 | `omicsclaw/memory/namespace_policy.py` |
| **Read fallback 读回退** | `recall` 和 `search` 在当前 Namespace 命中之外，自动包含 `__shared__` 结果的规则。**故意**只对单行查询生效；`list_children` 和 `get_subtree` 不回退，避免跨用户子树污染 | `omicsclaw/memory/engine.py` |
| **MemoryEngine** | 图记忆 Hot path 引擎。单一 SQLAlchemy 模块，对 `(uri, namespace)` 对暴露 7 个动词：`upsert`、`upsert_versioned`、`patch_edge_metadata`、`recall`、`search`、`list_children`、`get_subtree`，加幂等的 `seed_shared`。**完全替代**了已退役的 `GraphService` 类（`graph.py` 已删除） | `omicsclaw/memory/engine.py` |
| **ReviewLog** | 图记忆 Cold path 引擎。只被桌面 App 的 `/memory/review/*` 路由和 bot 清理路径调用，做版本链审计、回滚、孤儿检查、变更集审批 | `omicsclaw/memory/review_log.py` |
| **MemoryClient** | Surface 与 `MemoryEngine` 之间的策略层。决定 Namespace（`resolve_namespace()`）和版本策略（`should_version()`）；Surface 只持有这一个把手 | `omicsclaw/memory/memory_client.py` |
| **ScopedMemory** | 文件系统记忆层，住在 `.omicsclaw/scoped_memory/`（markdown + frontmatter）。承载 workspace 本地提示；当前 Live 消费方是 `/memory` slash 命令（CLI/TUI）和 `omicsclaw/diagnostics.py`。与图记忆**并存**在 CLI/TUI 表面上 | `omicsclaw/memory/scoped_memory.py` |
| **Versioned upsert 版本化写入** | 追加一条新的 `Memory` 行，并把上一条标记为 `deprecated=True`、`migrated_to` 指向新行的写法。`preference://*`、`insight://*` 走这个；`ReviewLog.rollback_to` 只对版本化链生效 | `omicsclaw/memory/engine.py` |
| **Overwrite upsert 覆盖写入** | 在单条活跃 `Memory` 行上原地更新，没有 deprecation 链。高频默认写法 | `omicsclaw/memory/engine.py` |
| **Session 会话** | 一次连续对话的状态。SQLite 持久化的 chat history、provider/model 配置、workspace 路径——可以通过 ID 跨进程恢复 | `omicsclaw/interactive/_session.py`、`~/.config/omicsclaw/sessions.db` |
| **Run 运行** | 一次 Skill 执行实例。每次 `oc run <skill> ...` 或 LLM 触发的 `omicsclaw(skill=...)` 调用都生成一个 Run，落到 `output/<skill>/<run_name>/` 目录 | `omicsclaw/common/manifest.py` |
| **Replot 重绘** | 在已有 Run 的产物上，仅重新渲染 R Enhanced 图像而不重跑分析。读 `figure_data/` 里的中间数据，输出新版图到同一个目录 | `omicsclaw.py` 的 `replot` 子命令 |
| **MCP（Model Context Protocol）** | Anthropic 提出的协议，让 LLM 通过标准接口调用外部工具。OmicsClaw 用 `~/.config/omicsclaw/mcp.yaml` 配置 MCP 服务器列表，CLI / TUI / App 启动时把它们加进工具集 | `omicsclaw/interactive/_mcp.py`、`omicsclaw.py` 的 `mcp` 子命令 |
| **Workspace 工作区** | 当前会话绑定的工作目录。CLI/TUI 用绝对路径；App 后端用 `OMICSCLAW_DESKTOP_LAUNCH_ID`；Bot 用 `<platform>/<user_id>`。**注意**：OmicsClaw 不像 Multica 那样把 Workspace 做成一张表——它是 Surface 注入到 Namespace 里的字符串 | `omicsclaw/memory/memory_client.py` |
| **Knowledge Base 知识库** | `knowledge_base/` 目录下的两类内容：(a) `knowhows/`——上述 KH 文件；(b) 按主题组织的方法学手册（`scrnaseq-scanpy-core-analysis/` 等），由 `oc knowledge build/search/list/stats` 索引与查询 | `knowledge_base/`、`omicsclaw/knowledge/` |

---

## 3. 功能全景（按模块）

### 3.1 Skill 技能体系

> **角色**：OmicsClaw 的执行原子。一切分析都是一次 Skill 调用。

#### Skill 是什么

一个 Skill 是一个**自包含的"方法 + 实现 + 演示"三件套**，住在 `skills/<domain>/<skill-name>/`。它对外暴露三类接口：

- **方法学**（给 LLM 读）：`SKILL.md`，含 YAML frontmatter + Markdown 方法学正文
- **可执行脚本**（给 OS 跑）：Python（统一约定 `--input`、`--output`、`--demo`），可选 R 脚本/Bash 脚本
- **演示数据**（给新手用）：`data/` 或共享 `examples/`，配 `--demo` 一键复现

> 当前总计 **89 个 Skill**，由 `skills/catalog.json` 与 `oc list` 双向校验。

#### SKILL.md 是什么

每个 Skill 的"说明书"。frontmatter 用 `metadata.omicsclaw` 段固定字段：

```yaml
---
name: sc-de
description: Single-cell differential expression
metadata:
  omicsclaw:
    canonical_name: sc-de
    legacy_aliases: [sc-diffexp]
    allowed_extra_flags: [--top-n, --method, --groupby]
    saves_h5ad: false
---
```

这是 **Skill 元数据的唯一真理源**。包含：

- `canonical_name` — Skill 的标准名（用 kebab-case）
- `legacy_aliases` — 旧名兼容（registry 用它做向后兼容）
- `allowed_extra_flags` — 安全白名单：只有这里出现的 flag 才允许通过 `omicsclaw.py run` 传递给脚本，**防止 LLM 注入任意 shell 参数**
- `saves_h5ad` — 是否产出新的 AnnData，影响产物追踪和血缘记录

方法学正文是写给 LLM 读的散文 + 列表 + 代码示例。它会被 KH 系统索引、被 Capability Resolver 拿来匹配用户意图、被 App 后端的 `/skills/<domain>/<skill>` 端点拿来在 UI 上展示。

#### Skill 在产品里的多重身份

| 谁消费 Skill | 怎么消费 | 入口 |
|---|---|---|
| **CLI 用户** | `oc run <skill> --input <file> --output <dir>` 直接命令行执行 | `omicsclaw.py` |
| **Interactive 用户** | `/run <skill>` slash 命令，或自然语言由 LLM 路由 | `omicsclaw/interactive/` |
| **Bot 用户** | 发自然语言消息，LLM 触发 `omicsclaw(skill=...)` 工具调用 | `bot/core.py` |
| **桌面 App 用户** | UI 的 Skills 面板浏览 + 一键执行；也可对话触发 | `omicsclaw/app/server.py` 的 `/skills*` |
| **远程 Job** | 桌面 App 通过 SSH 把 Skill 作业派给远端 `oc app-server` | `omicsclaw/remote/routers/jobs.py` |
| **Research Pipeline** | execute 阶段的子 agent 在 plan 阶段挑出 Skill，按顺序执行 | `omicsclaw/agents/pipeline.py` |
| **AutoAgent** | 在 metrics-driven 优化循环里把 Skill 当成可调参的对象，反复跑、评估、回滚 | `omicsclaw/autoagent/optimization_loop.py` |

无论谁触发，最终都走**同一个 Skill Runner 契约**：参数白名单校验 → 工作目录隔离 → 执行 → 标准化 README + 可复现 notebook + 产物清单。这是 OmicsClaw 跨 Surface 一致性的关键。

#### Skill 的产出（Output Ownership Contract）

跑完一个 Skill 后，输出目录的结构是固定的，**由共享 runner 而非 Skill 脚本自己决定**：

```
output/<skill>/<run_name>/
├── README.md                              # 共享 runner 写，含命令、参数、产物列表
├── reproducibility/
│   └── analysis_notebook.ipynb            # 共享 runner 写，复现笔记本
├── figures/                               # Skill 脚本写，主标准图
├── figure_data/                           # Skill 脚本写，给 R Enhanced 重绘用的中间数据
├── results/                               # Skill 脚本写，CSV/TSV/h5ad 等
└── logs/                                  # 执行日志
```

合同细节见 [`docs/engineering/2026-05-07-output-ownership-contract.md`](engineering/2026-05-07-output-ownership-contract.md)。

#### 添加一个新 Skill

1. `cp -r templates/skill/ skills/<domain>/<your-skill-name>/`，里面是 v2 脚手架
2. 编辑 SKILL.md（方法学 + frontmatter）
3. 实现 Python 脚本，接受 `--input`、`--output`、`--demo`
4. 写 `tests/`（contract 测试会强制脚本符合契约）
5. 跑 `python scripts/generate_catalog.py` 重生成 `skills/catalog.json`
6. 在 `omicsclaw/core/registry.py` 里给稳定别名做登记（可选——动态发现也会兜底）

更详细见 [CONTRIBUTING.md](../CONTRIBUTING.md) 和 [templates/skill/](../templates/skill/)。

#### 对应代码

- `skills/` — 89 个 Skill 实体
- `skills/catalog.json` — 自动生成的 Skill 清单
- `omicsclaw/core/registry.py` — Skill 注册表 + 别名解析
- `omicsclaw/core/skill_result.py` — 共享结果模型
- `omicsclaw.py` — `run` / `list` / `replot` 子命令
- `docs/engineering/2026-05-07-skill-runner-contract.md`
- `docs/engineering/2026-05-07-skill-metadata-contract.md`
- `docs/engineering/2026-05-07-output-ownership-contract.md`
- `docs/engineering/2026-05-07-alias-ownership-contract.md`

---

### 3.2 Domain 组学领域

> **角色**：Skill 的顶层归属，给路由、UI 导航、`/skills` 过滤提供分类轴。

#### 8 个 Domain

| Domain | Skill 数 | 覆盖内容 | INDEX |
|---|---|---|---|
| `spatial` 空间转录组 | 17 | Visium / Xenium / MERFISH / Slide-seq 的 QC、域识别、SVG、反卷积、细胞通讯、轨迹、CNV | `skills/spatial/INDEX.md` |
| `singlecell` 单细胞 | 30 | scRNA-seq + scATAC-seq：FASTQ→count、QC、过滤、双胞、归一化、HVG、PCA、UMAP、聚类、注释、DE、轨迹、velocity、GRN、CCC | `skills/singlecell/INDEX.md` |
| `genomics` 基因组学 | 10 | bulk DNA-seq：QC、比对、SNV/indel/SV/CNV calling、变异注释、phasing、de novo 组装、ATAC/ChIP peak calling | `skills/genomics/INDEX.md` |
| `proteomics` 蛋白质组学 | 8 | 质谱：raw QC、肽段/蛋白鉴定、LFQ/TMT/DIA 定量、差异表达、PTM、通路富集 | `skills/proteomics/INDEX.md` |
| `metabolomics` 代谢组学 | 8 | LC-MS：XCMS 预处理、peak 检测、代谢物注释（SIRIUS/GNPS）、归一化、DE、通路富集 | `skills/metabolomics/INDEX.md` |
| `bulkrna` 批量 RNA | 13 | bulk RNA-seq：QC、比对、count QC、DE（DESeq2/edgeR）、富集、可变剪接、WGCNA、反卷积、PPI、生存、TrajBlend bulk→sc | `skills/bulkrna/INDEX.md` |
| `orchestrator` 编排元域 | 2 | 多组学 query 路由 + Skill 脚手架生成 | `skills/orchestrator/INDEX.md` |
| `literature` 文献元域 | 1 | 文献检索 / 综述支持 | `skills/literature/` |

#### 共享工具（`_lib/`）

每个 Domain 目录下都有一个 `_lib/`（前导下划线），**不是 Skill**——`registry.py` 的发现器跳过 `_*` 目录。`_lib/` 承载的是**跨 Skill 的领域工具**：

- `skills/spatial/_lib/` — `adata_utils.py`、`viz/`（13 个可视化模块）、`loader.py`（多平台数据加载）、`dependency_manager.py`（懒导入）、`exceptions.py`
- `skills/singlecell/_lib/` — `adata_utils.py`、`preprocessing.py`、`markers.py`、`annotation.py`、`trajectory.py`、`grn.py`、`integration.py`、`dimred.py`、`gene_programs.py`、`metacell.py`、`pseudobulk.py`、`differential_abundance.py`、`perturbation.py`、`preflight.py`、`gallery.py`、`upstream.py`、`stat_enrichment.py` 等（含 R 桥接：跨域 R 脚本住在 `omicsclaw/r_scripts/`，Python 通过子进程调用）
- 其他 Domain 同理

> **导入约定**：Skill 脚本通过 `from skills.<domain>._lib.<module> import <name>` 拿到这些工具，不允许跨 Domain 的 `_lib` 互调；想抽公共逻辑就放到 `omicsclaw/` 框架层。

#### 命名空间区分

记忆系统也有 7 个 Domain（`core`、`dataset`、`analysis`、...），**与 Skill 的 8 个组学 Domain 完全独立**。看到 "domain" 这个词时，永远要根据上下文判断：

- 在 `skills/` 和 `oc list --domain` 里，指组学领域
- 在 `omicsclaw/memory/` 和 Memory URI 里，指 URI 前缀

#### 对应代码

- `skills/<domain>/` — 8 个 Domain 目录
- `skills/<domain>/INDEX.md` — 每个 Domain 的 Skill 索引
- `skills/<domain>/_lib/` — 共享工具
- `scripts/generate_routing_table.py` — 自动生成 `CLAUDE.md` 的路由表

---

### 3.3 Routing 路由与 Capability Resolver

> **角色**：让 LLM "选择正确的 Skill"，让 `auto` 落地成一个具体 Skill 名字。

#### Routing 是什么

OmicsClaw 不让 LLM "凭感觉"调用 Skill——所有 Skill 调用都通过一个**唯一的工具函数** `omicsclaw(skill=..., input=..., output=..., mode=...)` 发出。LLM 在系统提示词里看到的能力简报告诉它：

- 当前有哪些 Skill 可用（带描述）
- 哪些 KH 约束当前生效（headline-only）
- 怎么填 `skill` 参数：要么填一个 canonical name，要么填 `auto`

#### Capability Resolver 怎么工作

当 LLM 决定 `skill='auto'` 时，把决策推迟到运行时由 **Capability Resolver** 完成：

1. 读 query + 当前 Domain hint（如果有）
2. 用关键词 + Skill description 匹配候选
3. 应用 KH `priority` 排序
4. 选出一个具体 Skill 或抛"无法解析"错误（让 LLM 重选）

> **当前没有基于向量的语义路由**——尽管产品定位 AI-native，路由器走的是结构化关键词 + Skill metadata 匹配。这是有意的选择：可解释、可单元测试、对 LLM 的"误调用"敏感。

#### 显式 vs 隐式

| LLM 调用 | 路径 | 何时用 |
|---|---|---|
| `omicsclaw(skill='sc-de', ...)` | 直接进 registry → 跑 Skill | LLM 对 Skill 名字有把握 |
| `omicsclaw(skill='auto', query='...')` | Capability Resolver 解析 → 跑 Skill | LLM 不确定，让 OmicsClaw 决策 |

#### 对应代码

- `omicsclaw/routing/` — 路由策略
- `omicsclaw/runtime/capability_resolver.*` — `auto` 解析器
- `omicsclaw/runtime/tool_orchestration.py` — 工具调度
- `omicsclaw/runtime/skill_listing.py` — 给 LLM 看的能力简报
- `CLAUDE.md`（仓库根） — Skill 路由表（由 `scripts/generate_routing_table.py` 生成）

---

### 3.4 KnowHow 与 Active Guards

> **角色**：把"科学正确性约束"从 SKILL.md 抽出来，独立维护，自动注入到每个相关请求。

#### 为什么要 KnowHow

LLM 的"自信幻觉"在生物信息领域代价很高：在 1000 个基因上算 FDR 不调整 p 值就发现"差异基因"，是真的会发到论文里的错误。OmicsClaw 把这类**强制性科学约束**抽成单独的 markdown 文件，让它有自己的版本、自己的 frontmatter、自己的检索 metadata，并且**在每一次相关请求里强制出现**。

#### KH 文件长什么样

`knowledge_base/knowhows/KH-<slug>.md`：

```yaml
---
doc_id: bulk-rnaseq-differential-expression
title: Best practices for Bulk RNA-seq Differential Expression Analysis
doc_type: knowhow
critical_rule: MUST use adjusted p-values (padj/FDR) for DEG filtering and MUST NOT interpret raw p-values as significance thresholds
domains: [bulkrna]
related_skills: [bulk-rnaseq-counts-to-de-deseq2, bulkrna-de, bulkrna-deseq2]
phases: [before_run]
search_terms: [RNA-seq, differential expression, DESeq2, padj, FDR, fold change, 差异表达, 差异基因, 差异分析]
priority: 0.9
---

# Best practices for RNA-seq Differential Expression Analysis
...
```

#### 两种渲染模式

| 模式 | 内容 | 出现时机 | 大小 |
|---|---|---|---|
| **Headline-only**（默认） | 一行 `→ {label}: {critical_rule}` | 每个相关请求的 system prompt 里 | <100 token / KH |
| **Full body**（按需） | 完整 Markdown 文档 | LLM 调用 `read_knowhow(name)` 时返回 | 可达数千 token |

PR #107 引入 headline-only 后，baseline system prompt 缩短了约 70%；模型如果觉得"这个 KH 我需要看全文"，就主动 `read_knowhow`。

#### Active Guards 怎么选

`KnowHowInjector.get_constraints(skill, query, domain)` 综合：

1. **当前 Skill** 的 `related_skills` 反向索引
2. **当前 Domain** 的 `domains` 反向索引
3. **当前 query** 跟 `search_terms` 的关键词匹配
4. 按 `priority` 排序，取 top-N 进入 Active Guards

`read_knowhow` 工具的 description 里会明文写"只能拉取 Active Guards 列表里的 KH"——防止模型把全部 KH 都拉一遍把上下文吃完。

#### 当前状态（截至 2026-05）

| 项 | 状态 |
|---|---|
| KH 文件总数 | 30+（持续增长，单细胞分析占大头） |
| 注入路径 | `KnowHowInjector` → `build_system_prompt` → 当前请求 system prompt |
| 存储 | 文件系统 markdown（canonical）+ 图记忆 `__shared__/core://kh/<doc_id>`（每次 `init_db` 由 `seed_knowhows` 幂等同步） |
| `core://kh/*` 状态 | ✅ **已落地**（PR #172）。`KnowHowInjector.iter_entries()` 枚举 → `MemoryEngine.seed_shared` 幂等写入；同内容重复种子是 no-op；失败降级为 warning log，不阻塞启动 |

> **注**：`read_knowhow` 工具目前仍从文件读，没有改读图。图层是镜像，便于将来 `recall("core://kh/<id>")` 跨命名空间访问，但不是读路径的真源。

#### 对应代码

- `knowledge_base/knowhows/KH-*.md`
- `omicsclaw/runtime/system_prompt.py`（`KnowHowInjector`、`build_system_prompt`）
- `omicsclaw/runtime/predicates.py`
- `omicsclaw/memory/bootstrap.py`（`seed_knowhows` 入口）
- `omicsclaw/memory/engine.py`（`MemoryEngine.seed_shared` 幂等写入原语）
- `omicsclaw/runtime/context_layers/`

---

### 3.5 Memory 图记忆系统

> **角色**：OmicsClaw 的"长期记忆"。让一次 PBMC 分析在下次打开同一工作区时还知道"我处理过这个数据集、走过哪些 Skill、用户偏好怎样、哪条洞见已确认"。

#### 为什么不是简单的对话历史

ChatGPT 的对话历史只解决"上一个 turn 说了什么"。OmicsClaw 解决的是：

- 上次跑 `spatial-domains` 用的是 leiden 还是 louvain？（**preference**）
- `pbmc.h5ad` 这个数据集前后被哪些 Skill 处理过？（**lineage**）
- 用户三周前问过的一个结论，今天又问类似问题，要不要直接召回？（**insight**）
- 多个 user 同时用 Bot，怎么保证数据不串？（**namespace 隔离**）

图记忆用 SQLite/Postgres 把每个"事实"存成一个 `Memory` 节点，节点之间通过 edge 连成 DAG，根节点是 `ROOT_NODE_UUID`。每个节点有 URI（`dataset://pbmc.h5ad`）做地址，Namespace 列做隔离。

#### 三层架构

```
┌──────────────────────────────────────────────┐
│  Strategy:   MemoryClient(engine, namespace) │  ← Surface 持有这个把手
│              ├─ resolve_namespace()          │
│              ├─ should_version()             │
│              └─ remember() / recall() / ...  │
└──────────────────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────┐
│  Hot path:   MemoryEngine                    │  ← 每个对话 turn 都跑
│              7 verbs over (uri, namespace):  │
│              upsert / upsert_versioned       │
│              patch_edge_metadata             │
│              recall / search                 │
│              list_children / get_subtree     │
└──────────────────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────┐
│  Cold path:  ReviewLog                       │  ← 桌面 Review & Audit 面板
│              版本链检查 / rollback / orphan  │
│              browse_shared / 变更集审批      │
└──────────────────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────┐
│  Storage:    SQLite (default) or Postgres    │
│              通过 SQLAlchemy 抽象             │
│              OMICSCLAW_MEMORY_DB_URL          │
└──────────────────────────────────────────────┘
```

#### Surface 的 Namespace 派生

| Surface | Helper | Namespace 字符串 |
|---|---|---|
| CLI / TUI | `cli_namespace_from_workspace(workspace_dir)` | workspace 绝对路径（缺省 cwd） |
| Desktop | `desktop_namespace()` | `app/<OMICSCLAW_DESKTOP_LAUNCH_ID>` 或 `app/desktop_user` |
| Telegram / Feishu / Discord / ... | `CompatMemoryStore` 自动派生 | `f"{platform}/{user_id}"` |
| 系统 / boot 脚本 | 常量 | `__shared__` |

`app/`、`telegram/`、`feishu/` 这些前缀是**结构性**的——防止 Bot 的 user_id 跟 CLI 的绝对路径（如 `/home/...`）撞库。

#### Read fallback 的非对称性

| 操作 | 是否 fallback 到 `__shared__` |
|---|---|
| `recall(uri)` | ✓ 自动包含 |
| `search(query)` | ✓ 自动包含 |
| `list_children(uri)` | ✗ 严格 |
| `get_subtree(uri)` | ✗ 严格 |

设计取舍是：**单行查询**让用户能感知到共享内容（如 `core://agent`、系统词表），**子树遍历**严格隔离避免清单页混入别人的结构。

#### Versioned vs Overwrite

| 写入模式 | URI 前缀（示例） | 行为 | 谁用 |
|---|---|---|---|
| **Versioned upsert** | `preference://*`、`insight://*`、`core://agent` | 追加新行 + 旧行 `deprecated=True` + `migrated_to` 指针 | 高价值/可回滚的内容 |
| **Overwrite upsert** | `dataset://*`、`analysis://*`、`session://*` | 原地更新单行 | 高频/无回滚需求的内容 |

`MemoryClient.should_version(uri)` 用前缀策略决定走哪条。`ReviewLog.rollback_to` 只对 versioned 链生效。

#### Display label 的特殊处理

`analysis://<uuid_hex>` 的 URI 用 UUID 是为了避免**覆盖写入**模式下的写冲突，但 UI 上要给人看的标签需要可读。所以在 API 边界（`/memory/browse`、`/memory/recent` 等）从 `Memory.content` 派生：

```
<dataset_basename> · <yyyy-mm-dd hh:mm> · <status>
```

URI 仍是规范身份；label 只服务于展示。

#### REST API（桌面 Review & Audit）

由 `oc memory-server` 或 `oc app-server` 暴露（参见 [§3.8](#38-app-backend-桌面网页后端)）：

```
GET    /memory/browse            浏览节点（按 domain 树状）
GET    /memory/search            关键词搜索（含 __shared__ fallback）
POST   /memory/create            手动创建节点
PUT    /memory/update            更新节点内容
DELETE /memory/delete            删除节点（级联）
GET    /memory/children          列子节点（严格 namespace）
GET    /memory/domains           按 domain 计数
GET    /memory/recent            最近 N 条
GET    /memory/review/changes    变更集
POST   /memory/review/approve    批准变更
POST   /memory/review/rollback   回滚版本
GET    /memory/review/orphans    检查孤儿节点
GET    /memory/review/version-chain
POST   /memory/review/clear
POST   /memory/glossary/add      词表
DELETE /memory/glossary/remove
GET    /memory/scoped            ScopedMemory（filesystem 层）
POST   /memory/scoped/prune
```

#### ScopedMemory（文件系统记忆）

并行于图记忆，住在 `.omicsclaw/scoped_memory/`，是**workspace 本地的 markdown 笔记**。CLI/TUI 的 `/memory add|list|scope|prune` slash 命令操作的就是它。当前的迁移共识：

- **markdown 笔记** → ScopedMemory（保留）
- **结构化记忆**（remember/recall/search） → MemoryEngine（图）

两者并存，slash 命令的 view 由 `build_graph_memory_command_view`（2026-05 wired）做桥接。

#### 当前迁移状态（2026-05-11 全部完成）

- ✅ 桌面五个 GraphService 端点（`/memory/update`、`/memory/children`、`/memory/domains`、`MemoryClient.forget`、`MemoryClient.get_recent`）全部迁移到 `MemoryEngine` / `MemoryClient`
- ✅ 三个 cold-path API 模块全部脱离 GraphService：`api/maintenance.py`（PR #173 → ReviewLog 上新增 `list_orphans_with_chain` / `get_orphan_detail` / `permanently_delete_orphan`），`api/review.py`（PR #174 → 新增 `get_memory_by_id` / `restore_path`），`api/browse.py`（PR #175 → 改 import 私有 `BrowseHelpers`）
- ✅ `core://kh/*` bootstrap 落地：每个 `init_db` 入口调 `seed_knowhows`，幂等写入 `__shared__/core://kh/<doc_id>`（PR #172）
- ✅ CLI/TUI 的图记忆 wiring（PR #167）
- ✅ **GraphService 类已退役**：`omicsclaw/memory/graph.py` 删除，`get_graph_service()` 工厂消失（PR #175）。Path-based admin 操作以私有 `BrowseHelpers` 类保留在 `omicsclaw/memory/api/_browse_helpers.py`，仅供 `/api/browse/*` admin UI 消费——任何生产代码都不能从外部 import

整个 2026-05 重构计划现已闭合，见 [`docs/2026-05-09-memory-refactor-plan.md`](2026-05-09-memory-refactor-plan.md) §5。

#### 对应代码

- `omicsclaw/memory/engine.py` — MemoryEngine（含 `seed_shared` 幂等原语）
- `omicsclaw/memory/review_log.py` — ReviewLog（含桌面 admin 端点的 `get_memory_by_id` / `restore_path` / `list_orphans_with_chain` 等）
- `omicsclaw/memory/memory_client.py` — MemoryClient
- `omicsclaw/memory/bootstrap.py` — KH `seed_knowhows` 入口
- `omicsclaw/memory/namespace_policy.py` — Namespace 派生 + Shared 前缀策略
- `omicsclaw/memory/compat.py` — Bot 用的 CompatMemoryStore
- `omicsclaw/memory/scoped_memory.py` — 文件系统层
- `omicsclaw/memory/api/_browse_helpers.py` — 私有 legacy 路径操作（仅 `/api/browse/*` 消费，不要外部 import）
- `docs/CONTEXT.md` — 完整词汇表 + 决策记录
- `docs/engineering/memory.mdx` — 引擎细节

---

### 3.6 Session 会话与恢复

> **角色**：让一次对话能跨进程、跨重启、甚至跨 Surface 地继续。

#### Session 是什么

一个 Session 是**一次连续对话的状态快照**：聊天历史、provider/model 配置、workspace 路径、当前 Skill 上下文。OmicsClaw 把它持久化到 SQLite，让用户随时通过 `--session <id>` 把上下文接回来。

#### 数据载体

```
~/.config/omicsclaw/sessions.db        # SQLite，由 aiosqlite 驱动
├─ sessions 表                          # id, created_at, last_used_at, mode, name
├─ messages 表                          # role, content, tool_calls, tool_results
└─ metadata 表                          # provider, model, workspace, mcp 配置快照
```

#### 三种 Session 模式（CLI/TUI）

| 模式 | 工作目录 | 何时用 |
|---|---|---|
| `daemon`（默认） | 持久 workspace（用户传 `--workspace` 或 cwd） | 一般使用 |
| `run` | 每个 session 独立子目录（自动命名或 `--name`） | 隔离实验、对比配置 |
| `run --name <x>` | 命名 workspace | 长期项目 |

#### 恢复机制

- **同进程内**：`/resume [id]` slash 命令（无 id 则交互选择最近 N 条）
- **跨进程**：`oc interactive --session <id>` 从 SQLite 重载历史，重新连 LLM、重新挂 MCP
- **跨 Surface**：当前**不支持**——CLI session 不能在 Bot 上接回；Surface 隔离是有意的边界

#### Session vs Memory

| | Session | Memory |
|---|---|---|
| 存什么 | 一次对话的逐 turn 历史 | 跨对话的事实/血缘/偏好 |
| 谁写 | 每个 turn 自动写 | LLM `remember()` 工具或 auto-capture |
| 谁读 | resume 时读完整历史 | 每个 turn 由 system prompt builder 召回相关片段 |
| 隔离粒度 | session_id | Namespace |
| 持久化 | `~/.config/omicsclaw/sessions.db` | `OMICSCLAW_MEMORY_DB_URL` |

简化记法：**Session 保存"我们刚才聊了什么"，Memory 保存"我们以前学到了什么"。**

#### 对应代码

- `omicsclaw/interactive/_session.py`
- `omicsclaw/agents/notebook_session.py`（研究流水线的 session 视图）
- `omicsclaw/remote/routers/sessions.py`（远程 `POST /sessions/{id}/resume`）
- `bot/session.py`（Bot 端 session）

---

### 3.7 Interactive CLI / TUI

> **角色**：终端里的"OmicsClaw 工作台"。两种 UI 共用同一份对话核心。

#### 两种 UI

| 模式 | 入口 | 实现 | 适合 |
|---|---|---|---|
| **CLI**（默认） | `oc interactive` 或 `oc chat` | `prompt_toolkit` REPL | SSH 会话、tmux 窗格、轻量交互 |
| **TUI** | `oc tui` 或 `oc interactive --ui tui` | `Textual` 全屏 | 长会话、需要侧栏看进度/会话列表 |

两者都进 `omicsclaw/interactive/`，import 同一个 `bot.core.llm_tool_loop`。

#### Slash 命令清单

会话内键入 `/` 触发结构化命令，不进 LLM：

| 命令 | 说明 |
|---|---|
| `/skills [domain]` | 列出所有 Skill（可按 domain 过滤） |
| `/run <skill> [--demo] [--input <path>]` | 直接跑 Skill（绕过 LLM 路由） |
| `/sessions` | 列最近会话 |
| `/resume [id]` | 恢复会话（无 id 则交互选择） |
| `/delete <id>` | 删一个保存的 session |
| `/current` | 显示当前 session 信息 |
| `/new` | 起新 session |
| `/clear` | 清空会话历史（不删 session 记录） |
| `/mcp list` | 列 MCP 服务器 |
| `/mcp add <name> <cmd> [args]` | 添加 MCP 服务器 |
| `/mcp remove <name>` | 删 MCP 服务器 |
| `/config list` | 看 LLM 配置 |
| `/config set <key> <val>` | 改 LLM 配置 |
| `/memory <subcmd>` | 操作 ScopedMemory / 图记忆（参见 §3.5） |
| `/help` | 全部命令 |
| `/exit` | 退出 |

#### 单步模式（`-p`）

需要在 shell 脚本里调用 OmicsClaw 时，用 `-p`：

```bash
oc interactive -p "list all single-cell skills"
oc interactive -p "run sc-de demo and summarize"
```

执行一次就退出，输出走 stdout，可以 pipe。

#### Provider Runtime Contract

CLI、TUI、桌面 App 共享同一个 provider 解析路径：

- `LLM_PROVIDER=custom` 必须遵守 `LLM_BASE_URL`、`OMICSCLAW_MODEL`、`LLM_API_KEY` 三件套
- CLI 的 `--provider` / `--model` 显式参数覆盖环境变量
- 配置错的 custom endpoint 返回可操作诊断，不允许出现 `(no response)`

这是不可破坏的"无声错误防护契约"——所有 Surface 都遵守。

#### 对应代码

- `omicsclaw/interactive/__init__.py` — 包入口（`run_interactive()`、`main()`）
- `omicsclaw/interactive/_constants.py` — Banner、LOGO、slash 命令、slogan
- `omicsclaw/interactive/_session.py` — SQLite session 持久化
- `omicsclaw/interactive/_mcp.py` — MCP 配置/YAML 管理
- `omicsclaw/interactive/interactive.py` — `prompt_toolkit` REPL（CLI 模式）
- `omicsclaw/interactive/tui.py` — Textual 全屏 TUI
- `omicsclaw/interactive/_tui_support.py` — TUI 辅助（依赖最轻）

---

### 3.8 App Backend 桌面/网页后端

> **角色**：给 OmicsClaw-App（Electron 桌面/浏览器）和任何第三方前端提供的 FastAPI 后端。

#### 启动方式

```bash
oc app-server --host 127.0.0.1 --port 8765
# 或 reload 模式开发
oc app-server --host 127.0.0.1 --port 8765 --reload
```

默认绑 `127.0.0.1:8765`。**不要绑到 0.0.0.0**——OmicsClaw 假设你通过 SSH 隧道或本机访问。如果非要绑外部接口，必须同时设 `OMICSCLAW_REMOTE_AUTH_TOKEN` 启用 bearer token。

#### 路由全景

App 后端服务于五大类前端需求：

##### A. Chat（流式对话）

```
POST   /chat/stream                 SSE 流式聊天（最重要的入口）
POST   /chat/abort                  中止当前流
POST   /chat/permission             审批一个待批准的工具调用
POST   /chat/session-permission-profile
                                    保存当前 session 的工具审批偏好
```

`/chat/stream` 是 App 的心脏——它在请求里携带 provider/model/message_history/workspace，后端调 `bot.core.llm_tool_loop`，把 LLM 输出、工具调用、工具结果、metric 全部以 SSE 事件流式推回前端。

##### B. Workspace / Files

```
GET    /workspace                   查询当前 workspace
PUT    /workspace                   切换 workspace
GET    /files/browse                浏览目录（前端文件树）
GET    /files/tree                  获取整个 workspace 的文件树
GET    /files/serve                 给前端按路径下载文件
GET    /health                      健康检查
```

##### C. Skills（浏览 + 安装 + 执行）

```
GET    /skills                      列所有 Skill（带 domain 分组）
GET    /skills/{domain}/{skill_name}  取一个 Skill 的 SKILL.md 全文
GET    /skills/installed            列已安装（含外部源安装的）
POST   /skills/install              从 URL/Git 安装一个第三方 Skill
POST   /skills/uninstall            卸载
```

##### D. Memory（前面 §3.5 列出的全部 `/memory/*`）

##### E. Settings / Providers / Auth / MCP / Outputs

```
GET    /settings                    取设置
GET    /claude/settings             读取本地 Claude Code 的 settings.json
PUT    /claude/settings             写回 Claude Code 设置（共享配置）
GET    /providers                   列 LLM provider + 当前激活
PUT    /providers                   切换 provider/model
POST   /providers/test              短连接测试 LLM 联通性

GET    /auth/{provider}/status      OAuth 状态（claude/openai/...）
POST   /auth/{provider}/login       触发 OAuth login（用户在浏览器完成）
POST   /auth/{provider}/logout      退出登录

GET    /mcp/servers                 列 MCP 服务器
POST   /mcp/servers                 新增
DELETE /mcp/servers/{name}          移除
PUT    /mcp/servers                 批量更新
POST   /mcp/sync                    同步状态

GET    /outputs/latest              最近一次 Run 的元数据
GET    /outputs/{run_id}/files      列某 Run 的产物文件
```

##### F. Notebook（前端的"嵌入式 Jupyter"）

`/notebook/*`（在 `omicsclaw/app/notebook/router.py` 里）暴露：

```
POST /kernel/start | /stop | /interrupt
GET  /kernel/status
POST /complete    代码补全
POST /inspect     变量探查
POST /execute     执行一个 cell
POST /var_detail  查变量值
POST /adata_slot  查 AnnData 的 slot 内容
POST /files/upload | /list | /open | /create | /save | /delete | /rename
```

这让 App 前端能在 Skill 输出旁边直接打开一个嵌入的 IPython kernel——用户可以选中 `adata.obs` 立刻看分布，而不必离开 OmicsClaw。

#### Provider Runtime Contract（再次强调）

桌面 provider 改动必须保证：

- `GET /providers` 报告当前 provider/model/endpoint
- `POST /providers/test` 做短 LLM 联通性探测
- `POST /chat/stream` 在请求改变 model 时**重新初始化** provider runtime，即使 provider id 没变（防止旧 client 复用造成"我换了模型但还是旧的"）

#### 对应代码

- `omicsclaw/app/server.py` — 全部 endpoint
- `omicsclaw/app/notebook/router.py` — Notebook 子路由
- `omicsclaw/app/_attachments.py` — 附件处理
- `omicsclaw/app/_compaction_event_bridge.py` — 长会话压缩事件桥

---

### 3.9 Bot 多渠道机器人

> **角色**：让 OmicsClaw 在 9 个聊天平台变成"群里的同事"。

#### 9 个渠道

| 渠道 | 文件 | 配置入口 |
|---|---|---|
| Telegram | `bot/channels/telegram.py` | `TELEGRAM_BOT_TOKEN`（@BotFather） |
| Feishu / 飞书 | `bot/channels/feishu.py` | `FEISHU_APP_ID` + `FEISHU_APP_SECRET`（飞书开放平台 + WebSocket） |
| DingTalk / 钉钉 | `bot/channels/dingtalk.py` | 钉钉开放平台 |
| Discord | `bot/channels/discord.py` | Discord Developer Portal Bot token |
| Slack | `bot/channels/slack.py` | Slack App tokens（Socket Mode） |
| WeChat / 微信 | `bot/channels/wechat.py` | 微信公众平台 |
| QQ | `bot/channels/qq.py` | QQ 机器人开放接入 |
| Email | `bot/channels/email.py` | SMTP/IMAP |
| iMessage | `bot/channels/imessage.py` | macOS Messages 桥接（本地） |

#### 启动方式

```bash
python -m bot.run --channels telegram                # 单渠道
python -m bot.run --channels telegram,feishu,slack   # 多渠道并发
python -m bot.run --list                             # 列可用
make bot-telegram                                    # Makefile alias
make bot-feishu
```

所有渠道共用一个进程，由 `bot/channels/manager.py` + `bot/channels/bus.py` 调度。

#### 共享心脏：`bot/core.py` + 拆分模块

| 文件 | 行数（约） | 职责 |
|---|---|---|
| `bot/core.py` | 648 | 入口、Tool spec、安全、审计 |
| `bot/agent_loop.py` | 935 | LLM tool-use 主循环 |
| `bot/skill_orchestration.py` | 771 | 把 LLM 的 `omicsclaw(skill=...)` 调用变成 Skill Runner 执行 |
| `bot/preflight.py` | 280 | 执行前的输入校验、追问 |
| `bot/tool_executors.py` | — | 工具实现（save_file、write_file、generate_audio、omicsclaw） |
| `bot/session.py` | — | 渠道无关的 session 抽象 |
| `bot/path_validation.py` | — | 路径白名单 |
| `bot/rate_limit.py` | — | 速率限制 |
| `bot/billing.py` | — | Token 计费 / 上限 |
| `bot/audit.py` | — | JSONL 审计日志 |
| `bot/onboard.py` | — | 共享的交互式 onboarding wizard |

> **拆分计划**：原 `bot/core.py` 单文件 5000+ 行，规划分解记录在 `docs/adr/0001-bot-core-decomposition.md`，当前的 5 个子文件是分解第一阶段的成果。

#### 工具集

LLM 在 Bot 里看到的工具（OpenAI function calling 风格）：

- `omicsclaw(skill, input, output, mode, ...)` — 跑一个 Skill（与 Skill Runner 契约一致）
- `read_knowhow(name)` — 拉 KH 全文
- `save_file(path, content)` / `write_file(...)` — 写文件到 workspace
- `generate_audio(text)` — 文本转语音（部分渠道用）
- 来自 MCP 的工具（按 `~/.config/omicsclaw/mcp.yaml` 加载）

#### 安全边界

- **路径沙箱**：所有文件路径必须落在 workspace 内，用 `bot/path_validation.py` 校验
- **Skill 参数白名单**：执行 Skill 时只允许 `metadata.omicsclaw.allowed_extra_flags` 里列出的 flag
- **文件大小限制**：上传/下载有大小上限
- **审计日志**：所有 LLM 调用、工具调用、Skill 执行写 `bot/logs/audit.jsonl`
- **Rate limit**：按渠道用户限速

#### 图像理解

发图到 Bot 时（H&E、荧光图、空间 barcode 图等），Bot 会先做组织学/平台识别——告诉用户"看起来是 Visium H&E 切片，建议跑 `spatial-preprocess`"，再让用户决策是否上传 h5ad 进入分析流。

#### 持续会话

每个 `(platform, user_id)` 对应一个 Namespace（见 §3.5），多轮对话由 `CompatMemoryStore` 自动派生记忆上下文。重启 Bot 后用户不需要重新介绍自己处理的数据集。

#### 持续运维

```
bot/
├── logs/
│   └── audit.jsonl            # 自动创建，含所有调用记录
└── CHANNELS_SETUP.md          # 9 个渠道的注册流程
```

详见 [`bot/README.md`](../bot/README.md) 和 [`bot/CHANNELS_SETUP.md`](../bot/CHANNELS_SETUP.md)。

#### 对应代码

- `bot/`（整目录）
- `SOUL.md` — OmicsBot 人设（被 `build_system_prompt` 注入）

---

### 3.10 Research Pipeline 研究流水线

> **角色**：把"一句话研究问题"变成"一份完整研究报告"的多 Agent 工作流。

#### 灵感来源

参考 EvoScientist 的科研多 agent 编排范式：每个 sub-agent 只负责一段，stage 之间通过共享的 plan state + 笔记本 session 串联。OmicsClaw 把它落到自己的 Skill / KH / 记忆栈上。

#### 7 个 Stage

```
intake → plan → research → execute → analyze → write → review
                                                          │
                                                          └── 如需修订，回到 write 或 execute
```

| Stage | 干什么 | 关键产物 |
|---|---|---|
| **intake** | 与用户澄清问题、确认数据可用性 | `IntakeBrief` |
| **plan** | 把问题分解为一串 Skill 调用计划 | `PlanState`（含 status 字段） |
| **research** | 在 plan 通过审批前/后做文献检索补充 | 知识摘要 |
| **execute** | 按 plan 顺序触发 Skill | 每个 Skill 的 Run + 笔记本 cell |
| **analyze** | 综合 Skill 产物，提取结论 | 中间分析 |
| **write** | 写成报告（含图表引用） | Markdown / Notebook 报告 |
| **review** | reviewer agent 检查事实、要不要返工 | review 决策 |

#### Plan 审批（Human-in-the-loop）

`PlanState` 有 `pending_approval` 和 `approved` 两个关键状态——plan 阶段产出的执行计划必须由人类审批后才能进 execute。这是为生信任务设计的"贵执行前的安全闸"：你不希望 LLM 自动跑一晚上 STAR 比对发现选错了基因组。

#### 系统提示形状

不调 `build_system_prompt(surface='bot')`，而是 `build_system_prompt(surface='pipeline', base_persona=<研究人设>)`——KH 注入关闭，因为 KH 的强约束已经在每个被 execute 的 Skill 上单独生效。

#### 实现

- 用 [deepagents](https://github.com/...) 的 `create_deep_agent()` 构建 sub-agent
- 配置在 `omicsclaw/agents/config.yaml`
- 入口在 `omicsclaw/agents/pipeline.py`

#### 启用方式

研究流水线当前由 API/SDK 触发，**不是默认对话 Surface**——CLI 用户和 Bot 用户走的是单 agent 路径。要触发研究流水线，需要在程序内显式调用 `omicsclaw.agents.pipeline.run_pipeline(intake=...)`。

#### 对应代码

- `omicsclaw/agents/pipeline.py` — 主控
- `omicsclaw/agents/pipeline_result.py` — 结果模型
- `omicsclaw/agents/plan_state.py` — Plan 状态机
- `omicsclaw/agents/plan_validation.py` — Plan 校验
- `omicsclaw/agents/intake.py` — Intake stage
- `omicsclaw/agents/tools.py` — Stage 间共享工具
- `omicsclaw/agents/notebook_session.py` — 笔记本视图
- `omicsclaw/agents/backends.py` — Provider 后端适配
- `omicsclaw/agents/middleware.py` — 中间件
- `omicsclaw/agents/prompts.py` — Stage 提示词
- `omicsclaw/agents/config.yaml` — Sub-agent 配置

---

### 3.11 Self-Evolution 自演化（AutoAgent）

> **角色**：让 OmicsClaw 自己优化自己——既能调 Skill 参数，也能改源码。

#### 两种工作模式

| 模式 | 干什么 | 调用方 |
|---|---|---|
| **Optimization Loop** | 通过 directive loop 自动搜参，在多次 Run 上比较 metric | `omicsclaw/autoagent/optimization_loop.py` |
| **Harness Loop** | 在受控 edit surface（一组允许改的文件路径）里改源码，跑测试，评估，回滚或合并 | `omicsclaw/autoagent/harness_loop.py` |

两种模式都跑在 **JSON-only micro-prompt** 上——元 agent 每轮只做一个决定：下一组参数是什么 / 下一个 patch 怎么打 / 接受还是回滚。它**不复用** `build_system_prompt`，因为对话型 system prompt 不适合 JSON 任务。

#### 关键模块

- `search_space.py` — 参数搜索空间描述
- `directive.py` — 元 agent 的指令格式
- `harness_directive.py` — Harness 模式专用指令
- `edit_surface.py` — 允许 patch 的文件路径白名单
- `patch_engine.py` — diff 生成 + apply + 回滚
- `evaluator.py` / `metrics_compute.py` / `metrics_registry.py` — Metric 评估
- `judge.py` — 把多个 metric 综合成接受/拒绝决策
- `experiment_ledger.py` — 每次实验的记录
- `failure_memory.py` — 失败实验的记忆，避免重复踩坑
- `hard_gates.py` — 不可破坏的硬约束（测试必须通过、metric 不能倒退）
- `llm_client.py` — 元 agent 专用 LLM 客户端（独立配置）
- `reproduce.py` — 复现一次历史实验
- `result_contract.py` — 结果格式
- `runner.py` — 模式调度
- `trace.py` — 实验链路追踪

#### CLI 入口

```bash
oc optimize <skill> --input <file> --search-space <yaml> --max-rounds 10 --output <dir>
```

#### 安全边界

- **Edit surface 白名单**：harness 模式不能写白名单外的文件
- **Metric 硬阈值**：任何 patch 不能让既有 metric 跌破基线
- **测试必须通过**：每个 patch 都跑 `pytest`，失败立即回滚
- **审计**：每个实验都写 `experiment_ledger`，可追溯

#### 为什么这个是独立 Surface

`build_system_prompt(surface='bot' or 'pipeline')` 假设的是"对话 + 工具调用"形态。AutoAgent 的每轮只输出 JSON（如 `{"action":"apply_patch","patch":"..."}`），多走一段 KH 注入和能力简报是浪费 token、还容易让模型搞混"我应该回答用户还是输出 JSON"。所以**故意**让 AutoAgent 独立。

#### 对应代码

- `omicsclaw/autoagent/`（整目录）

---

### 3.12 Remote Execution 远程执行

> **角色**：桌面在本地，数据/计算在远端 Linux——通过 SSH 隧道把两者粘起来。

#### 场景

研究者的笔记本上跑桌面 App，但 10TB 的 fastq、bam、h5ad 在科室的 Linux 服务器上。要在本地获得"对话 + 数据浏览 + 笔记本"体验，但执行必须在远端。

#### 部署方式

1. 在远端服务器：
   ```bash
   conda activate OmicsClaw
   export OMICSCLAW_REMOTE_AUTH_TOKEN=$(openssl rand -hex 32)
   oc app-server --host 127.0.0.1 --port 8765
   ```
2. 本地：用 SSH 隧道把远端 `127.0.0.1:8765` 转发到本地 `127.0.0.1:8765`
3. 桌面 App 配置 endpoint = `http://127.0.0.1:8765`，bearer token = 上面的 `OMICSCLAW_REMOTE_AUTH_TOKEN`

#### Remote 子模块

`omicsclaw/remote/` 暴露一组**远程优先**的端点：

```
POST   /connections/test                探测连接
GET    /env/doctor                       远端环境检查（conda 包、R 包、生信 CLI）
POST   /sessions/{session_id}/resume     远程恢复 session

POST   /jobs                             提交 Skill 作业
GET    /jobs                             列作业
GET    /jobs/{job_id}                    查作业
POST   /jobs/{job_id}/cancel             取消
POST   /jobs/{job_id}/retry              重试
GET    /jobs/{job_id}/events             SSE 事件流（实时进度）

GET    /artifacts                        列产物
GET    /artifacts/{artifact_id:path}/download   下载产物

GET    /datasets                         列数据集
POST   /datasets/upload                  上传（multipart）
POST   /datasets/import-remote           从远端 URL / S3 导入
DELETE /datasets/{dataset_id}            删除
```

> 注意区分：`omicsclaw/app/server.py` 是**统一 backend**，远端也跑它；`omicsclaw/remote/routers/` 是**远端专有路由**，挂在同一个 FastAPI app 里。

#### 安全边界

- **Localhost 绑定**：永远 `127.0.0.1`，外部访问只能通过 SSH 隧道
- **Bearer token**：`OMICSCLAW_REMOTE_AUTH_TOKEN` 必填（非 localhost 部署时）
- **Dataset path 白名单**：上传必须在配置的 storage root 下
- **Job 隔离**：每个 Job 一个独立 workdir

#### 对应代码

- `omicsclaw/remote/`（整目录）
- `omicsclaw/remote/routers/connections.py`
- `omicsclaw/remote/routers/env.py`
- `omicsclaw/remote/routers/sessions.py`
- `omicsclaw/remote/routers/jobs.py`
- `omicsclaw/remote/routers/artifacts.py`
- `omicsclaw/remote/routers/datasets.py`
- `omicsclaw/remote/auth.py`
- `omicsclaw/remote/storage.py`
- `omicsclaw/remote/app_integration.py`
- `docs/engineering/remote-execution.mdx`
- `docs/_legacy/remote-connection-guide.md`

---

### 3.13 MCP 外部工具协议

> **角色**：让 OmicsClaw 通过标准协议接入"外部 AI 工具"——例如 sequential-thinking、文献检索、代码执行 sandbox。

#### MCP 是什么

Anthropic 提出的 Model Context Protocol，定义了"AI Agent 如何调用外部工具"的标准。OmicsClaw 把它当成**可插拔工具来源**——内置的工具（`omicsclaw`、`read_knowhow`、`save_file` 等）之外，MCP 服务器提供的工具会被自动加进 LLM 看到的 tool list。

#### 配置文件

`~/.config/omicsclaw/mcp.yaml`：

```yaml
servers:
  sequential-thinking:
    transport: stdio
    command: npx
    args: ["-y", "@modelcontextprotocol/server-sequential-thinking"]
  my-http-server:
    transport: http
    url: http://localhost:8080
```

支持四种 transport：`stdio`、`http`、`sse`、`websocket`。

#### CLI 操作

```bash
oc mcp list                              # 列已配置
oc mcp add <name> <cmd> [args]           # stdio：命令 + 参数
oc mcp add <name> http://...             # http 端点
oc mcp add <name> <cmd> --transport sse --env KEY=val
oc mcp remove <name>
oc mcp config                            # 打印配置文件路径
```

#### 在哪些 Surface 生效

- **CLI / TUI**：进 `oc interactive` 时把 MCP 工具加入 LLM tool list
- **App Backend**：UI 的 MCP 管理页（`/mcp/servers`）操作的是同一份 YAML
- **Bot**：渠道启动时加载
- **Research Pipeline**：execute stage 的 sub-agent 可见

#### 依赖

```bash
pip install langchain-mcp-adapters         # 实际执行 MCP 工具
```

> 没装 `langchain-mcp-adapters` 也能 `oc mcp list`，但调用会跳过（degrade gracefully）。

#### 对应代码

- `omicsclaw/interactive/_mcp.py` — 配置管理
- `omicsclaw.py` 的 `mcp` 子命令
- `omicsclaw/app/server.py` 的 `/mcp/*` 路由
- `~/.config/omicsclaw/mcp.yaml` — 配置文件

---

### 3.14 Onboarding、Auth 与 Settings

> **角色**：第一次用 OmicsClaw 的"傻瓜引导"，以及 OAuth、API key、provider 的管理。

#### Onboarding wizard

```bash
oc onboard
```

交互式向导，按顺序配置：

1. **LLM provider + model + API key**（或 custom endpoint）
2. **Workspace 默认路径**
3. **Runtime 检查**（conda 环境、R 包、生信 CLI 是否就位）
4. **Memory 数据库**位置（默认 SQLite，可换 Postgres）
5. **Bot channels**（要不要现在配置 Telegram/Feishu/...）

完成后写 `.env` 和 `~/.config/omicsclaw/config.yaml`。

#### Auth（OAuth）

部分 LLM provider 支持 OAuth（不再需要长期 API key）：

```bash
oc auth login claude         # 触发浏览器 OAuth 流，token 存本机
oc auth login openai
oc auth status               # 查谁登录了
oc auth logout claude
oc auth refresh claude       # 主动刷新 token
```

桌面 App 上有对应 UI（`/auth/{provider}/login`），点击会自动打开浏览器、等回调、回写 token。

#### Provider 切换

CLI：

```bash
oc interactive --provider deepseek --model deepseek-chat
```

App：UI 的 Settings → Providers 直接拉取 `/providers`，下拉切换。**桌面契约**要求 `/chat/stream` 在 model 变化时重启 provider runtime——这是为了防止"我切了模型但还在用旧的"陷阱。

#### Doctor 诊断

```bash
oc doctor                # 检查全部依赖
oc doctor --skip-llm     # 跳过 LLM 联通检查（CI 用）
oc env                   # 看安装了哪些 dependency tier
```

输出会显示：

- Python 包版本 vs 期望
- R 包安装情况
- 生信 CLI（STAR/samtools/MaxQuant/...）是否在 PATH
- LLM provider 是否可达
- MCP 服务器是否可启动
- 已知 `pip check` 警告（如 `jinja2` 冲突）

#### Settings 存哪里

| 配置 | 文件 |
|---|---|
| 全局 OmicsClaw | `~/.config/omicsclaw/config.yaml` |
| LLM key 等敏感 | `.env`（项目根） |
| MCP 服务器 | `~/.config/omicsclaw/mcp.yaml` |
| Session 历史 | `~/.config/omicsclaw/sessions.db` |
| 图记忆 | `OMICSCLAW_MEMORY_DB_URL`（默认 SQLite 文件） |
| ScopedMemory | `.omicsclaw/scoped_memory/`（项目内） |
| Bot 审计 | `bot/logs/audit.jsonl` |

#### 对应代码

- `omicsclaw.py` 的 `onboard` / `auth` / `doctor` / `env` 子命令
- `bot/onboard.py` — 共享 wizard 实现
- `omicsclaw/diagnostics.py` — `doctor` 后端

---

### 3.15 Outputs、Reports 与 Replot

> **角色**：让 Skill 跑出的图、表、Markdown 报告有统一外观，并支持"事后调参重绘"。

#### 三层可视化流

OmicsClaw 设计了 **Python → R Enhanced → Tunable Replot** 三层：

```
1. 首次执行
   oc run sc-de --input data.h5ad --output dir/
   ↓
   Skill 脚本写 Python 标准图（figures/）+ 中间数据（figure_data/）

2. R Enhanced
   oc replot sc-de --output dir/
   ↓
   读 figure_data/，用 ggplot2 重绘"出版级"版本

3. 调参再绘
   oc replot sc-de --output dir/ --renderer plot_de_volcano --top-n 30
   ↓
   只重绘指定 renderer，参数前端可调
```

#### Replot CLI

```bash
oc replot <skill> --output <dir>                         # 全部重绘
oc replot <skill> --output <dir> --list-renderers        # 列出可重绘的图
oc replot <skill> --output <dir> --renderer plot_de_volcano --top-n 30
```

常用参数（透传给 R renderer）：

| Flag | 含义 |
|---|---|
| `--top-n N` | top 项数（火山图标签、heatmap 行数等） |
| `--font-size N` | base font size |
| `--width N` / `--height N` | 图尺寸（inch） |
| `--dpi N` | 分辨率（默认 300） |
| `--palette NAME` | 调色板 |
| `--title TEXT` | 自定义标题 |

#### 用户该用哪个

| 用户说 | OmicsClaw 做什么 |
|---|---|
| "把图美化一下" / "出版级" | `replot <skill> --output <dir>` |
| "Top 30 基因" / "多标几个" | `replot ... --top-n 30` |
| "只改火山图" | `replot ... --renderer plot_de_volcano` |
| "我能调哪些参数？" | `replot ... --list-renderers` |

#### 报告（README + Notebook）

每次 Run 自动生成：

- **`README.md`**：本次 Run 的命令、参数、产物清单、关键 metric、disclaimer
- **`reproducibility/analysis_notebook.ipynb`**：可在 Jupyter 里复现

这两份**由 Skill Runner 而不是 Skill 脚本**写——保证 89 个 Skill 的 README/Notebook 长得一模一样。契约见 `docs/engineering/2026-05-07-output-ownership-contract.md`。

#### 安全免责声明

每份 README 都包含：

> *"OmicsClaw is a research and educational tool for multi-omics analysis. It is not a medical device and does not provide clinical diagnoses. Consult a domain expert before making decisions based on these results."*

这是硬性合规要求，不允许 Skill 单独关闭。

#### 对应代码

- `omicsclaw/common/report.py` — README 生成
- `omicsclaw/common/manifest.py` — 产物 manifest
- `omicsclaw.py` 的 `replot` 子命令
- `omicsclaw/r_scripts/` — R Enhanced 渲染器
- `docs/engineering/2026-05-07-output-ownership-contract.md`
- `docs/engineering/replot.mdx`

---

### 3.16 Knowledge Base 知识库

> **角色**：把 KH（强制约束）和方法学手册（可读经验）打包成可索引、可检索、可搜索的领域知识。

#### 两类内容

| 子目录 | 内容 | 例子 | 谁读 |
|---|---|---|---|
| `knowledge_base/knowhows/` | KH 文件（强制约束） | `KH-sc-de-guardrails.md` | LLM via `build_system_prompt` + `read_knowhow` |
| `knowledge_base/<topic>/` | 方法学手册（经验文档） | `scrnaseq-scanpy-core-analysis/`、`bulk-omics-clustering/`、`survival-analysis-clinical/` | 用户 via `oc knowledge` |

#### CLI 命令

```bash
oc knowledge build [--path <dir>]      # 构建/重建索引
oc knowledge search <query> [--domain <d>] [--type knowhow|guide] [--limit N]
oc knowledge stats                     # 索引统计
oc knowledge list [--domain <d>]       # 列主题
```

#### 索引引擎

- 文档结构化：每个手册有 `INDEX.md`、章节 markdown、可选代码示例
- 索引位置：构建后写入 `omicsclaw/knowledge/` 缓存（具体路径可配置）
- 搜索：基于关键词 + frontmatter 字段（domains、search_terms）匹配；**不是向量检索**

#### 当前覆盖的主题（节选）

```
bulk-omics-clustering
bulk-rnaseq-counts-to-de-deseq2
cell-cell-communication
chip-atlas-diff-analysis / chip-atlas-peak-enrichment / chip-atlas-target-genes
clinicaltrials-landscape
coexpression-network
disease-progression-longitudinal
experimental-design-statistics
functional-enrichment-from-degs
genetic-variant-annotation
grn-pyscenic
gwas-to-function-twas
lasso-biomarker-panel
literature-preclinical
mendelian-randomization-twosamplemr
multi-omics-integration
pcr-primer-design
polygenic-risk-score-prs-catalog
pooled-crispr-screens
proteomics-diff-exp
scrnaseq-scanpy-core-analysis / scrnaseq-seurat-core-analysis
scrna-trajectory-inference
spatial-transcriptomics
survival-analysis-clinical
upstream-regulator-analysis
```

#### 知识库 vs Skill SKILL.md

| | KH | Knowledge Base 手册 | SKILL.md |
|---|---|---|---|
| 形态 | 一行 `critical_rule` + 长文 | 多章节经验文档 | 方法学 + frontmatter |
| 注入路径 | 每个相关请求自动 | 用户主动 `oc knowledge search` | 路由命中时 LLM 读 |
| 强制性 | 强（不可破坏的约束） | 弱（参考资料） | 中（执行规约） |
| 写给谁 | LLM | 人 + LLM | LLM |

三者**互补**：KH 管对错，手册管经验，SKILL.md 管怎么执行。

#### 对应代码

- `knowledge_base/`（整目录）
- `omicsclaw/knowledge/` — 索引 + 搜索
- `omicsclaw.py` 的 `knowledge` 子命令

---

### 3.17 CLI 命令行工具

> **角色**：OmicsClaw 的"瑞士军刀"。所有 Surface 的功能都至少有一个 CLI 等价命令。

#### 全部子命令

| 命令 | 干什么 | 详见 |
|---|---|---|
| `oc version` | 打印版本 | — |
| `oc env` | 看已安装的依赖层级（minimal/interactive/tui/memory/desktop/full） | §3.14 |
| `oc doctor [--skip-llm]` | 环境诊断 | §3.14 |
| `oc list [--domain <d>]` | 列 Skill | §3.1 |
| `oc run <skill> [--demo|--input ...] --output <dir>` | 跑一个 Skill | §3.1 |
| `oc replot <skill> --output <dir> [...]` | R Enhanced 重绘 | §3.15 |
| `oc upload --input <h5ad> ...` | 把 h5ad 注册成 spatial session | — |
| `oc onboard` | 引导向导 | §3.14 |
| `oc interactive [chat]` | 终端对话（CLI 模式） | §3.7 |
| `oc tui` | 终端对话（TUI 模式） | §3.7 |
| `oc app-server` | 启动桌面/网页后端 | §3.8 |
| `oc memory-server` | 启动图记忆 REST API | §3.5 |
| `oc mcp <list|add|remove|config>` | 管理 MCP 服务器 | §3.13 |
| `oc auth <login|logout|status|refresh>` | OAuth 管理 | §3.14 |
| `oc knowledge <build|search|stats|list>` | 知识库索引 | §3.16 |
| `oc optimize <skill> ...` | 自演化优化 Skill 参数 | §3.11 |

`omicsclaw` 与 `oc` 是同一个 CLI 的两个 entry point（由 `pyproject.toml` 的 `[project.scripts]` 注册）。任何环境下二者等价：

```bash
oc run sc-de --demo
# 等价于
python omicsclaw.py run sc-de --demo
```

#### Interactive 子命令的额外开关

```bash
oc interactive --session <id>           # 恢复会话
oc interactive -p "<prompt>"            # 单步模式
oc interactive --ui tui                 # 切 TUI
oc interactive --provider deepseek --model deepseek-chat
oc interactive --workspace /path
oc interactive --mode daemon            # 持久 workspace（默认）
oc interactive --mode run               # 隔离 workspace
oc interactive --mode run --name <x>    # 命名 workspace
```

#### Provider 解析顺序

CLI 解析 provider/model 的优先级（高 → 低）：

1. 显式 CLI flag（`--provider` / `--model`）
2. 环境变量（`LLM_PROVIDER` / `OMICSCLAW_MODEL` / `LLM_BASE_URL` / `LLM_API_KEY`）
3. `~/.config/omicsclaw/config.yaml` 默认
4. 出错时显示可操作诊断，绝不静默回退

这与 App、Bot 的解析逻辑完全一致——参见 §3.7 的 Provider Runtime Contract。

#### 对应代码

- `omicsclaw.py` — 主入口
- `omicsclaw/cli.py` — 子命令实现
- `omicsclaw/__main__.py` — `python -m omicsclaw` 等价入口
- `pyproject.toml` 的 `[project.scripts]`

---

## 4. 系统架构全景

OmicsClaw 在物理形态上是**一个 Python 包 + 一份共享数据存储 + 多个进程入口**。下面的图是逻辑视图，刻意把同一个进程里的多个组件分开画，让你能看清"消息从用户到 Skill 的全程路径"。

```
┌──────────────────────────────────────────────────────────────────────────┐
│                          User-facing Surfaces                            │
│                                                                          │
│  ┌──────────┐ ┌──────────┐ ┌──────────────┐ ┌─────────────────────────┐  │
│  │ CLI      │ │ TUI      │ │ Desktop App  │ │ Bot (9 channels)        │  │
│  │ oc       │ │ Textual  │ │ Electron /   │ │ telegram feishu         │  │
│  │ interac. │ │ tui      │ │ browser →    │ │ dingtalk discord slack  │  │
│  │          │ │          │ │ oc app-server│ │ wechat qq email imessage│  │
│  └────┬─────┘ └────┬─────┘ └──────┬───────┘ └────────────┬────────────┘  │
└───────┼────────────┼──────────────┼──────────────────────┼───────────────┘
        │            │              │                      │
        │            │              ▼                      │
        │            │     ┌─────────────────┐             │
        │            │     │ FastAPI app     │             │
        │            │     │ omicsclaw/app/  │             │
        │            │     │  + /remote/     │             │
        │            │     │  + /notebook/   │             │
        │            │     │  + /memory/     │             │
        │            │     └────────┬────────┘             │
        │            │              │                      │
        ▼            ▼              ▼                      ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                            Central Hub                                   │
│                          bot/core.py                                     │
│                          (User-facing entries 全部 import 它)            │
│                                                                          │
│  ┌─────────────────┐ ┌──────────────────┐ ┌──────────────────────────┐   │
│  │ llm_tool_loop   │ │ preflight        │ │ tool_executors           │   │
│  │ (agent_loop.py) │ │ (preflight.py)   │ │ omicsclaw / read_knowhow │   │
│  └────────┬────────┘ └────────┬─────────┘ └─────────┬────────────────┘   │
│           │                   │                     │                    │
└───────────┼───────────────────┼─────────────────────┼────────────────────┘
            │                   │                     │
            ▼                   ▼                     ▼
┌────────────────────┐ ┌──────────────────┐ ┌──────────────────────────────┐
│ System Prompt      │ │ KnowHow Injector │ │ Capability Resolver          │
│ Builder            │ │ (active guards)  │ │ (auto → concrete skill)      │
│ build_system_prompt│ │                  │ │                              │
│ (runtime/          │ │ knowledge_base/  │ │ omicsclaw/runtime/           │
│  system_prompt.py) │ │  knowhows/*.md   │ │  capability_resolver.*       │
└────────────────────┘ └──────────────────┘ └──────────────┬───────────────┘
                                                           │
                                                           ▼
                                  ┌────────────────────────────────────────┐
                                  │    Skill Runner（共享契约）            │
                                  │  • 参数白名单（allowed_extra_flags）   │
                                  │  • workdir 隔离                        │
                                  │  • 启动 Python/R 子进程                │
                                  │  • 写 README + analysis_notebook.ipynb │
                                  │  • 标准化 figures / figure_data / 结果 │
                                  └─────────────────┬──────────────────────┘
                                                    │
                       ┌────────────────────────────┼─────────────────────────────┐
                       ▼                            ▼                             ▼
              ┌─────────────────┐         ┌──────────────────┐         ┌─────────────────┐
              │ 89 Skills       │         │ Remote Jobs      │         │ AutoAgent       │
              │ skills/         │         │ omicsclaw/       │         │ omicsclaw/      │
              │  spatial/...    │         │  remote/         │         │  autoagent/     │
              │  singlecell/... │         │  routers/jobs.py │         │  optimization   │
              │  bulkrna/...    │         │  → SSH 隧道 →    │         │  harness loop   │
              │  ...            │         │  远端 oc app-svr │         │  experiment     │
              └─────────────────┘         └──────────────────┘         └─────────────────┘

                          ┌─────────────────────────────────────────┐
                          │           Graph Memory                  │
                          │                                         │
                          │   ┌──────────────┐   ┌──────────────┐   │
                          │   │ MemoryClient │──▶│ MemoryEngine │   │
                          │   │  + Namespace │   │  (hot path)  │   │
                          │   └──────────────┘   └──────┬───────┘   │
                          │                             │           │
                          │                      ┌──────▼─────────┐ │
                          │   ┌──────────────┐   │ SQLite/Postgres│ │
                          │   │ ReviewLog    │──▶│ via SQLAlchemy │ │
                          │   │  (cold path) │   │ +ScopedMemory  │ │
                          │   └──────────────┘   │  filesystem    │ │
                          │                      └────────────────┘ │
                          └─────────────────────────────────────────┘

                          ┌─────────────────────────────────────────┐
                          │          External Tools (MCP)           │
                          │  ~/.config/omicsclaw/mcp.yaml           │
                          │  • sequential-thinking                  │
                          │  • 自定义 stdio / http / sse / ws       │
                          └─────────────────────────────────────────┘
```

### 分层职责

| 层 | 负责什么 | 不负责什么 |
|---|---|---|
| **User-facing Surface**（CLI / TUI / App / Bot） | UI 表现、平台特性（消息上下文、文件上传、流式渲染）、Session 持久化 | 不直接调 LLM；不组装 system prompt；不做 Skill 执行 |
| **App Backend（FastAPI）** | HTTP/SSE 路由、Notebook kernel 桥、远程作业调度、文件浏览 | 不写业务逻辑——所有 LLM 流都委托给 Central Hub |
| **Central Hub（bot/core.py + agent_loop + skill_orchestration + preflight）** | 单 agent 主循环、工具调度、Preflight、计费、审计 | 不"思考"——LLM 在外，Central Hub 只编排 |
| **System Prompt Builder + KH Injector + Capability Resolver** | 把"业务上下文"翻译成 LLM 看得到的 prompt | 不持久化、不调用工具 |
| **Skill Runner** | 把一次 Skill 调用变成一组标准化产物 | 不知道是谁触发的（CLI/Bot/Pipeline 对它透明） |
| **Skills（89 个）** | 真正跑 Python/R 分析 | 不写 README、不组装通知——共享 runner 包办 |
| **Graph Memory** | 跨对话的事实/血缘/偏好持久化 | 不参与 system prompt 组装（只在 LLM 主动 recall/search 时被读） |
| **AutoAgent / Research Pipeline** | 多 Run / 多 stage 编排 | 不复用对话 system prompt（自有 micro-prompt 或 pipeline persona） |
| **LLM Provider** | 实际推理 | 不感知 OmicsClaw 数据模型——通过工具调用回读 |

### 数据流：一次"用 sc-de 跑差异表达"的全程

1. **用户**在 Bot 里发消息："用我的 pbmc.h5ad 跑差异表达"
2. **渠道 frontend**（如 `bot/channels/telegram.py`）解析消息，组成 `(session_id, user_id, content, attachments)`
3. **bot/core.py** 拿到请求，根据 `(platform, user_id)` 派生 Namespace（`telegram/<user_id>`）
4. **System Prompt Builder** 用 `surface='bot'` 渲染：
   - SOUL.md base persona
   - 当前 Active Guards 的 KH headlines（命中 KH-sc-de-guardrails 等）
   - 能力简报（含 sc-de 的描述）
   - 谓词层（如果消息提到"图" → 加 plot_intent 层）
5. **LLM** 看到 prompt，决定调 `omicsclaw(skill='sc-de', input='pbmc.h5ad', output='out/')`
6. **Preflight** 校验 `pbmc.h5ad` 是否有 `obs.group` 列；缺则反问用户
7. **Capability Resolver** 跳过（已显式 skill）；参数白名单校验通过
8. **Skill Runner** 在隔离 workdir 启动 `skills/singlecell/sc-de/sc_de.py` 子进程
9. **Skill 脚本**写 `results/de_table.csv`、`figures/volcano.png`、`figure_data/volcano.pkl`
10. **Skill Runner** 写 `README.md`、`reproducibility/analysis_notebook.ipynb`
11. **Central Hub** 把 Run metadata 推到 `MemoryEngine`（`analysis://<uuid>`，overwrite），更新 `dataset://pbmc.h5ad` 的血缘 edge
12. **LLM** 看到工具返回，根据 README 内容写自然语言总结
13. **bot/core.py** 把总结回给渠道 frontend；附上 volcano.png；写 audit 日志
14. **用户**在群里看到图 + 解读；可选"美化一下"触发 `oc replot sc-de`

### 实时层（SSE 流）

App Backend 的 `/chat/stream` 用 **Server-Sent Events** 把 LLM 流式输出推回前端：

- `delta`：增量 token
- `tool_call`：LLM 决定调工具（含参数）
- `tool_result`：工具返回
- `progress`：长执行的中间进度（Skill 跑到哪一步）
- `error`：异常（含可操作信息）
- `done`：本轮结束

Bot 渠道按平台特性把 SSE 流降级为段落消息（每 N 个 delta 合并发送，避免刷屏）。

### LLM 调用在哪里

**只有一处**：`bot/agent_loop.py` 的 `llm_tool_loop`。其他所有模块通过它**间接**调 LLM：

- App 的 `/chat/stream` → 调 `llm_tool_loop`
- CLI/TUI 的 REPL → 调 `llm_tool_loop`
- 9 个 Bot 渠道 → 调 `llm_tool_loop`
- Research Pipeline 的 stage agent → 用 deepagents（独立的 LLM 调用）
- AutoAgent → 用 `omicsclaw/autoagent/llm_client.py`（独立配置）

**Research Pipeline 和 AutoAgent 故意不共享 `llm_tool_loop`**——它们的对话形态完全不同，强行复用会让 system prompt 变得难以理解。

### 后台任务

OmicsClaw 当前**没有常驻后台 worker**——所有作业都是同步触发（CLI 用户阻塞等待，Bot/App 用 async 异步等待）。原因：

- Skill 跑完后是用户语义的"完成"，不需要异步队列
- 远程 Jobs 通过 `omicsclaw/remote/routers/jobs.py` 的 SSE `/jobs/{id}/events` 暴露进度
- AutoAgent 的多 Run 调度由 Python 内部协程实现，不引入 Celery/Arq 等

唯一接近"后台"的是 `app-server` 进程本身——它常驻服务前端请求。

### 持久化总结

| 数据 | 存储 | 路径 |
|---|---|---|
| Skill 产物 | 文件系统 | `output/<skill>/<run_name>/` 或用户 `--output` |
| Session（对话历史） | SQLite | `~/.config/omicsclaw/sessions.db` |
| 图记忆 | SQLite / Postgres | `OMICSCLAW_MEMORY_DB_URL` |
| ScopedMemory | 文件系统 | `.omicsclaw/scoped_memory/` |
| MCP 配置 | YAML | `~/.config/omicsclaw/mcp.yaml` |
| Bot 审计 | JSONL | `bot/logs/audit.jsonl` |
| OAuth token | OS keychain / file | 视 provider |
| AutoAgent ledger | SQLite | `omicsclaw/autoagent/experiment_ledger` 状态 |
| Knowledge index | 文件系统 | `omicsclaw/knowledge/` 缓存 |

---

## 5. 产品地图（全部 Surface 与路由）

### 5.1 CLI 子命令

```
oc version                                       打印版本
oc env                                           安装层级检查
oc doctor [--skip-llm]                           环境诊断

oc list [--domain <d>]                           列 Skill
oc run <skill> --demo                            演示运行
oc run <skill> --input <file> --output <dir>     真实数据运行
oc run <skill> --input ... --output ... [extra]  Skill 自定 flag（受 allowed_extra_flags 白名单）
oc replot <skill> --output <dir>                 R Enhanced 重绘
oc replot <skill> --output <dir> --list-renderers
oc replot <skill> --output <dir> --renderer <r> [--top-n N | --dpi N | ...]
oc upload --input <h5ad> --data-type <t> --species <s>   注册 spatial session

oc onboard                                       引导向导
oc interactive [chat]                            CLI 对话（默认）
oc interactive --ui tui                          切 TUI
oc interactive -p "<prompt>"                     单步模式
oc interactive --session <id>                    恢复会话
oc interactive --provider <p> --model <m>        覆盖 provider
oc interactive --workspace <path>                指定 workspace
oc interactive --mode daemon|run [--name <x>]    workspace 模式
oc tui                                           等价 interactive --ui tui

oc app-server [--host 127.0.0.1] [--port 8765] [--reload]
oc memory-server [--host 127.0.0.1] [--port 8766]

oc mcp list
oc mcp add <name> <command> [args...] [--transport stdio|http|sse|websocket] [--env KEY=VAL ...]
oc mcp remove <name>
oc mcp config

oc auth login <provider>                         OAuth 登录
oc auth logout <provider>
oc auth status [<provider>]
oc auth refresh <provider>

oc knowledge build [--path <dir>]
oc knowledge search <query> [--domain <d>] [--type <t>] [--limit N]
oc knowledge stats
oc knowledge list [--domain <d>]

oc optimize <skill> [...]                        AutoAgent 优化
```

### 5.2 App Backend FastAPI 路由

按功能聚类列出（详见 §3.8）：

```
# Chat / Streaming
POST   /chat/stream                              SSE 主流
POST   /chat/abort
POST   /chat/permission
POST   /chat/session-permission-profile

# Workspace / Files
GET    /workspace
PUT    /workspace
GET    /files/browse
GET    /files/tree
GET    /files/serve
GET    /health

# Skills
GET    /skills
GET    /skills/{domain}/{skill_name}
GET    /skills/installed
POST   /skills/install
POST   /skills/uninstall

# Memory
GET    /memory/browse
GET    /memory/search
POST   /memory/create
PUT    /memory/update
DELETE /memory/delete
GET    /memory/children
GET    /memory/domains
GET    /memory/recent
GET    /memory/review/changes
POST   /memory/review/approve
POST   /memory/review/rollback
GET    /memory/review/orphans
GET    /memory/review/version-chain
POST   /memory/review/clear
POST   /memory/glossary/add
DELETE /memory/glossary/remove
GET    /memory/scoped
POST   /memory/scoped/prune

# Settings / Providers
GET    /settings
GET    /claude/settings
PUT    /claude/settings
GET    /providers
PUT    /providers
POST   /providers/test

# Auth (OAuth)
GET    /auth/{provider}/status
POST   /auth/{provider}/login
POST   /auth/{provider}/logout

# MCP
GET    /mcp/servers
POST   /mcp/servers
DELETE /mcp/servers/{name}
PUT    /mcp/servers
POST   /mcp/sync

# Outputs
GET    /outputs/latest
GET    /outputs/{run_id}/files

# Notebook (omicsclaw/app/notebook/router.py)
POST   /notebook/kernel/start
POST   /notebook/kernel/stop
POST   /notebook/kernel/interrupt
GET    /notebook/kernel/status
POST   /notebook/complete
POST   /notebook/inspect
POST   /notebook/execute
POST   /notebook/var_detail
POST   /notebook/adata_slot
POST   /notebook/files/upload
GET    /notebook/list
GET    /notebook/open
POST   /notebook/create
POST   /notebook/save
POST   /notebook/delete
POST   /notebook/rename

# Remote (omicsclaw/remote/routers/*)
POST   /connections/test
GET    /env/doctor
POST   /sessions/{session_id}/resume
POST   /jobs
GET    /jobs
GET    /jobs/{job_id}
POST   /jobs/{job_id}/cancel
POST   /jobs/{job_id}/retry
GET    /jobs/{job_id}/events           SSE
GET    /artifacts
GET    /artifacts/{artifact_id:path}/download
GET    /datasets
POST   /datasets/upload
POST   /datasets/import-remote
DELETE /datasets/{dataset_id}
```

### 5.3 Bot 9 个渠道入口

| 命令 | 启动渠道 |
|---|---|
| `python -m bot.run --channels telegram` | Telegram |
| `python -m bot.run --channels feishu` | Feishu / 飞书 |
| `python -m bot.run --channels dingtalk` | DingTalk / 钉钉 |
| `python -m bot.run --channels discord` | Discord |
| `python -m bot.run --channels slack` | Slack |
| `python -m bot.run --channels wechat` | WeChat / 微信 |
| `python -m bot.run --channels qq` | QQ |
| `python -m bot.run --channels email` | Email |
| `python -m bot.run --channels imessage` | iMessage（仅 macOS） |
| `python -m bot.run --channels telegram,feishu,slack` | 多渠道并发 |
| `python -m bot.run --list` | 列可用渠道 |

### 5.4 Interactive 内的 Slash 命令

见 §3.7 表格。这些是会话内"绕过 LLM"的快捷入口，永远不会进入 LLM tool loop。

### 5.5 Skill 触发入口

同一个 Skill 可以从这些地方触发：

| 入口 | 形态 |
|---|---|
| CLI | `oc run <skill> ...` |
| Interactive slash | `/run <skill> ...` |
| Interactive 自然语言 | LLM 路由 → `omicsclaw(skill=...)` |
| Bot 自然语言 | 同上 |
| App UI（Skills 面板） | HTTP `POST /chat/stream` 触发 |
| App UI（一键执行） | `POST /chat/stream` 或 `POST /jobs`（远程） |
| Research Pipeline execute stage | 内部 API 调 Skill Runner |
| AutoAgent optimization loop | 内部 API 调 Skill Runner |
| 远程 Job | `POST /jobs` |

---

## 6. 跨 Surface 差异：CLI vs TUI vs App vs Bot

OmicsClaw 的 Surface 设计原则是**共享心脏、差异化外壳**——89 个 Skill、记忆、KH、路由都共享，但每个 Surface 在 UX 上有自己的偏好。

### 6.1 共享能力（全部 Surface 都有）

- LLM 对话 + 工具调用循环
- 89 个 Skill 的执行
- `omicsclaw(skill=...)` 工具
- `read_knowhow` 工具
- Memory recall / search（每个 Surface 在自己的 Namespace 下）
- MCP 工具集
- KH headline 自动注入
- Skill 参数白名单
- 标准化 Skill 产物

### 6.2 各 Surface 的独有/差异

| 能力 | CLI | TUI | App | Bot |
|---|:---:|:---:|:---:|:---:|
| Slash 命令 | ✓ | ✓ | （UI 等价物） | ✗ |
| 流式 SSE 渲染 | 行刷新 | 全屏刷新 | SSE | 段落消息合并 |
| 多 Session 并行 | ✗（按窗口） | ✗（按窗口） | ✓（多 tab） | ✓（按 user_id） |
| 文件浏览 | shell | shell | `/files/*` UI | 渠道附件 |
| 嵌入 Notebook kernel | ✗ | ✗ | ✓（`/notebook/*`） | ✗ |
| 图像理解 | ✗（除非 LLM 支持） | ✗ | ✓ | ✓（按渠道） |
| OAuth login UI | 命令行触发浏览器 | 同 CLI | 内嵌浏览器/系统浏览器 | ✗ |
| 远程 Job | ✗（用 SSH 跑 CLI） | ✗ | ✓（SSH 隧道 + token） | ✗ |
| 审计日志位置 | stdout/`logs/` | 同左 | App log | `bot/logs/audit.jsonl` |
| Workspace 模式 | `daemon`/`run [--name]` | 同左 | 单一 launch | 单一（per user） |
| Namespace 来源 | workspace 绝对路径 | 同左 | `app/<launch_id>` | `<platform>/<user_id>` |
| 长会话压缩 | 自动 | 自动 | 自动 + UI 反馈 | 自动 |
| 计费/限速 | ✗ | ✗ | 软（`billing.py`） | 强（`rate_limit.py`） |

### 6.3 为什么要做这些差异

**CLI 和 TUI 的差别**：本质同一个，TUI 多了 Textual 侧栏（会话列表、Skill 浏览、记忆面板）。CLI 适合 SSH 会话和 tmux 窗格，TUI 适合长时间工作的"工作台"形态。两者共享 `omicsclaw/interactive/`。

**App 和 Bot 的差别**：App 是单用户、本机、有文件树和 Notebook 的"重客户端"——它假设你能看到文件系统、能操作图。Bot 是多用户、远程、消息合并的"轻交互"——它必须假设用户随时切走、消息可能延迟、附件不一定能立刻拿到。

**App 与 CLI 的差别**：App 多了一个 FastAPI 进程作为桥梁；CLI 直接进程内调用。但二者通过 `bot/core.py` 看到的是同一份对话语义。

**远程 vs 本地**：唯一的"重"差异在桌面 App 上。Remote 是把 App 用法**整体**搬到远端：远端跑 `oc app-server`，本地桌面通过 SSH 隧道连过去。Skill、记忆、Notebook 全部在远端，桌面只是 UI。

### 6.4 为什么不做"集中云"

OmicsClaw **明确不做** SaaS 云版：

- 多组学数据合规高（人类基因/医院数据）
- 用户运行时已经在 HPC/工作站上，云端反而绕路
- 模型 token 可以走用户自己的 API key/自建模型，不需要平台撮合

所以 OmicsClaw 永远是"本地 + 远端 SSH" 二选一，没有第三种部署形态。

---

## 7. 附录：关键模块速查

> 共 ~30 个模块文件，按"功能域"列出最重要的入口，供文案/产品查询"某个功能背后到底在哪段代码里"。

### 7.1 框架核心

| 模块 | 职责 |
|---|---|
| `omicsclaw.py` | 主 CLI 入口（27 个子命令） |
| `omicsclaw/cli.py` | CLI 子命令实现 |
| `omicsclaw/__main__.py` | `python -m omicsclaw` 等价入口 |
| `omicsclaw/common/report.py` | README 生成 |
| `omicsclaw/common/manifest.py` | Skill 产物 manifest |
| `omicsclaw/common/checksums.py` | 输入 hash / 产物 hash |
| `omicsclaw/common/session.py` | Skill session 模型 |
| `omicsclaw/core/registry.py` | Skill 注册表 + 别名 |
| `omicsclaw/core/skill_result.py` | 共享 SkillResult 模型 |
| `omicsclaw/core/dependency_manager.py` | 依赖懒加载 |

### 7.2 Runtime（system prompt + 工具 + 谓词）

| 模块 | 职责 |
|---|---|
| `omicsclaw/runtime/system_prompt.py` | `build_system_prompt` + `KnowHowInjector` |
| `omicsclaw/runtime/context_layers/__init__.py` | `_PREDICATE_GATED_RULES` |
| `omicsclaw/runtime/predicates.py` | 谓词函数（plot_intent / web_or_url_intent / ...） |
| `omicsclaw/runtime/capability_resolver.*` | `auto` → 具体 Skill |
| `omicsclaw/runtime/skill_listing.py` | 给 LLM 看的能力简报 |
| `omicsclaw/runtime/tool_orchestration.py` | 工具调度 |
| `omicsclaw/runtime/tool_executor.py` | 工具执行 |
| `omicsclaw/runtime/tool_registry.py` | 工具注册 |
| `omicsclaw/runtime/tool_spec.py` | 工具 schema |
| `omicsclaw/runtime/tool_validation.py` | 工具参数校验 |
| `omicsclaw/runtime/tool_result_store.py` | 工具结果存储 |
| `omicsclaw/runtime/tool_execution_hooks.py` | 工具前/后 hook |
| `omicsclaw/runtime/preflight/` | Preflight 校验器（按 Skill） |
| `omicsclaw/runtime/context_assembler.py` | 把记忆 / KH / 工具结果拼到上下文 |
| `omicsclaw/runtime/context_budget.py` | 上下文 token 预算 |
| `omicsclaw/runtime/context_compaction.py` | 长会话压缩 |
| `omicsclaw/runtime/token_budget.py` | Token 预算 |
| `omicsclaw/runtime/transcript_store.py` | 对话历史存储 |
| `omicsclaw/runtime/task_store.py` | 任务存储 |
| `omicsclaw/runtime/policy.py` / `policy_state.py` | 执行策略 |
| `omicsclaw/runtime/approval.py` | 工具调用审批 |
| `omicsclaw/runtime/events.py` / `hooks.py` / `hook_payloads.py` | 事件总线 |
| `omicsclaw/runtime/output_styles.py` | 输出风格 |
| `omicsclaw/runtime/verification.py` | 工具结果验证 |
| `omicsclaw/runtime/query_engine.py` | 查询引擎 |

### 7.3 Central Hub（Bot 共享心脏）

| 模块 | 职责 |
|---|---|
| `bot/core.py` | 入口、Tool spec、安全、审计（约 648 行） |
| `bot/agent_loop.py` | LLM tool-use 主循环（约 935 行） |
| `bot/skill_orchestration.py` | Skill 编排（约 771 行） |
| `bot/preflight.py` | Preflight 校验（约 280 行） |
| `bot/tool_executors.py` | 工具实现 |
| `bot/session.py` | Session 抽象 |
| `bot/path_validation.py` | 路径白名单 |
| `bot/rate_limit.py` | 速率限制 |
| `bot/billing.py` | Token 计费 |
| `bot/audit.py` | JSONL 审计 |
| `bot/onboard.py` | 共享 onboarding |
| `bot/run.py` | 多渠道统一启动 |
| `bot/channels/manager.py` | 渠道调度 |
| `bot/channels/bus.py` | 跨渠道事件总线 |
| `bot/channels/{telegram,feishu,dingtalk,discord,slack,wechat,qq,email,imessage}.py` | 9 个渠道实现 |

### 7.4 Memory

| 模块 | 职责 |
|---|---|
| `omicsclaw/memory/engine.py` | MemoryEngine（Hot path，7 verbs） |
| `omicsclaw/memory/review_log.py` | ReviewLog（Cold path） |
| `omicsclaw/memory/memory_client.py` | MemoryClient（Strategy） |
| `omicsclaw/memory/namespace_policy.py` | Namespace 派生 + Shared 前缀 |
| `omicsclaw/memory/compat.py` | Bot 用 CompatMemoryStore |
| `omicsclaw/memory/scoped_memory.py` | 文件系统层 |

### 7.5 App Backend

| 模块 | 职责 |
|---|---|
| `omicsclaw/app/server.py` | FastAPI 主 app + 全部 endpoint |
| `omicsclaw/app/notebook/router.py` | Notebook 子路由 |
| `omicsclaw/app/_attachments.py` | 附件处理 |
| `omicsclaw/app/_compaction_event_bridge.py` | 长会话压缩事件桥 |

### 7.6 Remote

| 模块 | 职责 |
|---|---|
| `omicsclaw/remote/auth.py` | Bearer token 校验 |
| `omicsclaw/remote/storage.py` | Dataset 存储 |
| `omicsclaw/remote/app_integration.py` | 把 remote 路由挂到 app |
| `omicsclaw/remote/schemas.py` | Pydantic 模型 |
| `omicsclaw/remote/routers/connections.py` | 连接测试 |
| `omicsclaw/remote/routers/env.py` | 远端环境诊断 |
| `omicsclaw/remote/routers/sessions.py` | 远程 session 恢复 |
| `omicsclaw/remote/routers/jobs.py` | 作业生命周期 |
| `omicsclaw/remote/routers/artifacts.py` | 产物管理 |
| `omicsclaw/remote/routers/datasets.py` | 数据集管理 |

### 7.7 Research Pipeline

| 模块 | 职责 |
|---|---|
| `omicsclaw/agents/pipeline.py` | 主控（7 stage 编排） |
| `omicsclaw/agents/pipeline_result.py` | 结果模型 |
| `omicsclaw/agents/plan_state.py` | Plan 状态机 |
| `omicsclaw/agents/plan_validation.py` | Plan 校验 |
| `omicsclaw/agents/intake.py` | Intake stage |
| `omicsclaw/agents/tools.py` | Stage 间共享工具 |
| `omicsclaw/agents/notebook_session.py` | 笔记本视图 |
| `omicsclaw/agents/backends.py` | Provider 后端 |
| `omicsclaw/agents/middleware.py` | 中间件 |
| `omicsclaw/agents/prompts.py` | Stage 提示词 |
| `omicsclaw/agents/config.yaml` | Sub-agent 配置 |

### 7.8 Self-Evolution (AutoAgent)

| 模块 | 职责 |
|---|---|
| `omicsclaw/autoagent/api.py` | 对外 API |
| `omicsclaw/autoagent/constants.py` | 常量 |
| `omicsclaw/autoagent/runner.py` | 模式调度 |
| `omicsclaw/autoagent/optimization_loop.py` | 参数优化主循环 |
| `omicsclaw/autoagent/harness_loop.py` | 源码 patch 主循环 |
| `omicsclaw/autoagent/harness_directive.py` | Harness 指令 |
| `omicsclaw/autoagent/harness_workspace.py` | Harness 工作目录 |
| `omicsclaw/autoagent/directive.py` | 通用指令格式 |
| `omicsclaw/autoagent/edit_surface.py` | 可改文件白名单 |
| `omicsclaw/autoagent/patch_engine.py` | diff 生成 + apply + 回滚 |
| `omicsclaw/autoagent/evaluator.py` | 评估器 |
| `omicsclaw/autoagent/metrics_compute.py` | Metric 计算 |
| `omicsclaw/autoagent/metrics_registry.py` | Metric 注册 |
| `omicsclaw/autoagent/judge.py` | 决策（accept/reject） |
| `omicsclaw/autoagent/hard_gates.py` | 不可破坏的硬约束 |
| `omicsclaw/autoagent/search_space.py` | 参数搜索空间 |
| `omicsclaw/autoagent/experiment_ledger.py` | 实验账本 |
| `omicsclaw/autoagent/failure_memory.py` | 失败记忆 |
| `omicsclaw/autoagent/reproduce.py` | 复现历史实验 |
| `omicsclaw/autoagent/result_contract.py` | 结果格式 |
| `omicsclaw/autoagent/errors.py` | 异常 |
| `omicsclaw/autoagent/llm_client.py` | 独立 LLM 客户端 |
| `omicsclaw/autoagent/trace.py` | 实验链路追踪 |

### 7.9 Interactive (CLI/TUI)

| 模块 | 职责 |
|---|---|
| `omicsclaw/interactive/__init__.py` | 包入口 |
| `omicsclaw/interactive/_constants.py` | Banner、slash 命令 |
| `omicsclaw/interactive/_session.py` | SQLite session 持久化 |
| `omicsclaw/interactive/_mcp.py` | MCP 配置管理 |
| `omicsclaw/interactive/interactive.py` | prompt_toolkit REPL |
| `omicsclaw/interactive/tui.py` | Textual 全屏 TUI |
| `omicsclaw/interactive/_tui_support.py` | TUI 辅助 |

### 7.10 Knowledge Base 与 KH

| 模块 | 职责 |
|---|---|
| `knowledge_base/knowhows/KH-*.md` | KH 文件（30+） |
| `knowledge_base/<topic>/INDEX.md` | 方法学手册索引 |
| `omicsclaw/knowledge/` | 索引 + 搜索 |
| `omicsclaw/research/web_search.py` | Web 检索 |

### 7.11 Skills（领域共享工具）

| 路径 | 职责 |
|---|---|
| `skills/<domain>/_lib/` | 领域共享工具（不进 registry） |
| `skills/spatial/_lib/viz/` | 13 个空间可视化模块 |
| `omicsclaw/r_scripts/` | R 脚本（Seurat/DESeq2/CellChat/WGCNA/GSEA 等），Python 通过子进程调用 |
| `skills/<domain>/INDEX.md` | 每个 Domain 的 Skill 索引 |

### 7.12 Templates 与 Examples

| 路径 | 职责 |
|---|---|
| `templates/skill/` | v2 Skill 脚手架（SKILL.md + parameters.yaml + references/） |
| `examples/demo_visium.h5ad` | 空间 Demo 数据 |
| `examples/demo_bulkrna_counts.csv` | bulkrna Demo 数据 |

### 7.13 工程契约文档

| 文档 | 内容 |
|---|---|
| `docs/engineering/2026-05-07-framework-optimization-spec.md` | 框架路线 |
| `docs/engineering/2026-05-07-skill-runner-contract.md` | Skill Runner 契约 |
| `docs/engineering/2026-05-07-skill-metadata-contract.md` | Skill 元数据契约 |
| `docs/engineering/2026-05-07-skill-help-contract.md` | Skill `--help` 契约 |
| `docs/engineering/2026-05-07-alias-ownership-contract.md` | 别名所有权契约 |
| `docs/engineering/2026-05-07-output-ownership-contract.md` | 产物所有权契约 |
| `docs/engineering/2026-05-07-bot-runner-contract.md` | Bot Runner 契约 |
| `docs/engineering/2026-05-07-literature-skill-registration-spec.md` | 文献 Skill 注册规范 |
| `docs/engineering/domain-input-contracts.md` | 域输入契约 |
| `docs/engineering/memory.mdx` | Memory 引擎细节 |
| `docs/engineering/remote-execution.mdx` | 远程执行细节 |
| `docs/engineering/replot.mdx` | Replot 细节 |
| `docs/engineering/session-state-inventory.md` | Session 状态盘点 |
| `docs/CONTEXT.md` | Memory 域词汇表 |
| `CONTEXT.md`（仓库根） | Routing & 知识守卫词汇表 |
| `SPEC.md` | 仓库维护契约 |
| `AGENTS.md` | AI 开发者指南 |
| `CLAUDE.md` | Skill 路由表（自动生成） |
| `SOUL.md` | OmicsBot 人设 |
| `docs/adr/` | ADR（架构决策记录） |

### 7.14 测试契约

| 文件 | 测试什么 |
|---|---|
| `tests/test_documentation_facts.py` | README/AGENTS/SPEC 与代码同步 |
| `tests/test_skill_runner_contract.py` | Skill Runner 契约 |
| `tests/test_skill_metadata_contract.py` | SKILL.md 元数据 |
| `tests/test_skill_help_contract.py` | `--help` 契约 |
| `tests/test_registry_alias_contract.py` | 别名解析 |
| `tests/test_output_ownership_contract.py` | 产物布局 |
| `tests/test_bot_runner_contract.py` | Bot 执行 |

---

## 尾声

OmicsClaw 的设计可以归结为一句话：**把"研究者在终端里用 Python/R/CLI 跑多组学分析"这件事，扩展到"研究者在多个 Surface 里和 LLM 协作跑同一份 Skill 栈"**。

所有功能都是围绕这个核心展开：

- 为了让 LLM 不胡说 → **KnowHow + Active Guards + Preflight**
- 为了让分析能跨对话延续 → **图记忆 + Namespace + Session**
- 为了让 89 个 Skill 长得一样 → **Skill Runner Contract + Output Ownership Contract**
- 为了让本地数据安全 → **Local-first + Localhost binding + Bearer token + 路径白名单**
- 为了让大数据可远程 → **Remote Execution + SSH 隧道 + 远端 oc app-server**
- 为了让 OmicsClaw 自己变好 → **Self-Evolution (AutoAgent) + Edit surface + Hard gates**
- 为了让 9 个聊天平台体验一致 → **bot/core.py 中央枢纽 + Surface 派生 Namespace**
- 为了让长流程可控 → **Research Pipeline + Plan 审批 + Stage 编排**

当你读到某段文案、某个 UI 模块、某个 Python 文件时，请把它放回这个"研究者 + LLM + 本地工具栈"的坐标系里去理解它的位置。

---

> *"OmicsClaw is a research and educational tool for multi-omics analysis. It is not a medical device and does not provide clinical diagnoses. Consult a domain expert before making decisions based on these results."*




