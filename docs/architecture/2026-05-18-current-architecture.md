# OmicsClaw 当前架构设计文档

> **Historical snapshot — not current authority.** This document records the
> architecture as understood on 2026-05-18. The canonical current-state
> architecture is [`docs/ARCHITECTURE.md`](../ARCHITECTURE.md). Preserve this
> file as historical evidence; do not update it to describe later architecture.
>
> 时间快照：2026-05-18
> 范围：基于实际代码（不是 README 的宣传性描述），逐层拆解 OmicsClaw 的运行时与领域层结构。本文档为内部理解与优化使用，**不替代** `docs/CONTEXT.md`（领域语言）和 `docs/adr/`（决策记录）。

---

## 0. 一句话定位

OmicsClaw 是一个 **本地优先（local-first）的单用户多组学 AI 研究助手**，把 LLM 工具循环（agent loop）和 95 个组学 skill 黏在一起，对外暴露三个 surface（CLI / Desktop / Channels）。架构选型由 ADR 0001 / 0003–0008 一系列决策**显式收窄**到"单进程 asyncio + 直接执行 + 类型化事件流"。

```
LLM 推理 ──→ run_query_engine ──→ tool 执行 ──→ skill 调用 ──→ 产物（figure + figure_data + report.md）
   ▲              │                    │
   └── memory ────┴── transcript ──────┘
   └── 三个 Surface 都走同一条路径
```

---

## 1. 顶层目录速查

```
OmicsClaw/
├── omicsclaw.py             # 单入口脚本（兼容 `oc` 短别名 + `python omicsclaw.py`）
├── omicsclaw/               # ★ Python 包
│   ├── engine/              # 高层入口（构 deps、调 run_engine_loop）
│   ├── runtime/             # ★ 核心运行时
│   │   ├── agent/           # ★★ LLM 工具循环（query_engine + loop + pathology）
│   │   ├── consensus/       # ★ 多方法共识层（ADR 0010 / 0011，§7.11 / §11）
│   │   ├── context/         # 消息装配 + 预算 + reactive compaction
│   │   ├── policy/          # 工具审批与策略状态
│   │   ├── storage/         # transcript / tool_result / task 持久化
│   │   └── tools/           # 工具注册 / 编排 / 钩子 / 校验
│   ├── memory/              # ★ 图后端记忆系统（Hot + Cold path）
│   ├── surfaces/            # ★ 三个用户入口
│   │   ├── channels/        # 10 个 IM 平台适配器
│   │   ├── desktop/         # FastAPI 后端（SSE 流）
│   │   └── cli/             # prompt_toolkit REPL + Textual TUI
│   ├── skill/               # skill 发现 / 注册 / 解析 / 执行
│   ├── routing/             # 自然语言意图路由（关键词 + LLM 兜底）
│   ├── providers/           # LLM provider 注册（OpenAI 兼容 + 模型补丁）
│   ├── remote/              # 远端 Linux 服务器 SSH 桥接
│   ├── autoagent/           # 实验/优化循环（独立子系统，非主 chat 路径；已删除，运行时调参见 omicsclaw/ensemble/tuning/）
│   ├── agents/              # ★ EvoScientist 风格多 agent 研究流水线（5481 行）
│   ├── core/                # 配置、路径、project_registry、skill_runtime
│   ├── services/            # 计费/usage 累加
│   ├── knowledge/           # KnowHow（领域知识 seeds，写入 core://kh/*）
│   ├── loaders/             # 数据加载
│   ├── extensions/          # 插件扩展
│   └── research/            # 研究脚手架
├── skills/                  # ★ 95 skill 资源（含 4 个 consensus shim）（每个含 SKILL.md + 入口脚本）
│   ├── catalog.json
│   ├── spatial/  (17)  singlecell/ (30)  genomics/ (10)  proteomics/ (8)
│   ├── metabolomics/ (8)  bulkrna/ (13)  orchestrator/ (2)  literature/ (1)
│   ├── spatial/consensus-domains/                  # ★ ADR 0010 thin skill
│   └── singlecell/scrna/sc-consensus-clustering/   # ★ ADR 0010 thin skill
├── docs/
│   ├── CONTEXT.md          # 领域语言术语表（Memory + Surface 层）
│   ├── adr/                # 7 个决策记录（0003–0008；原重复的 0003 已重编号为 0033）
│   └── architecture/       # overview / orchestrator / skill-system + 本文档
├── frontend/               # （Vue 桌面前端，与本文档无关）
├── tools/                  # vendored bin（外部 CLI 工具）
├── r_scripts/              # R Enhanced 绘图脚本
├── tests/                  # 测试套件
├── examples/               # demo 数据（demo_visium.h5ad, demo_bulkrna_counts.csv）
│   └── consensus_benchmark/  # ★ DLPFC 151673 hero benchmark（ADR 0011）
└── workspace/              # 运行时工作区根
```

---

## 2. 五层架构（实际代码版本）

`docs/architecture/overview.mdx` 中给出了对外宣传的 5 层简化图。**本节是基于实际代码的精确五层划分**，与简化图相比：第 2 层（编排器）实际由 `routing/` + `skill/orchestration/` 两个模块联合实现；第 5 层（数据产物）实际由 `runtime/storage/` 接管 transcript / tool_result，而不只是磁盘文件。

```
┌─────────────────────────────────────────────────────────────────────┐
│ L1 — Surface Layer（用户入口）                                        │
│   surfaces/cli/       prompt_toolkit REPL + Textual TUI               │
│   surfaces/desktop/   FastAPI + SSE + asyncio.Queue bridge            │
│   surfaces/channels/  Telegram/Feishu/Slack/Discord/WeChat/...(10)    │
│   ─ 所有 surface 都构造 MessageEnvelope, 调 dispatch(envelope)         │
├─────────────────────────────────────────────────────────────────────┤
│ L2 — Dispatch / Event Stream（ADR 0006）                              │
│   runtime/agent/dispatcher.py   dispatch(envelope) → AsyncIterator    │
│   runtime/agent/envelope.py     MessageEnvelope dataclass             │
│   runtime/agent/events.py       9 种 typed Event                       │
├─────────────────────────────────────────────────────────────────────┤
│ L3 — Engine Layer（高层组装）                                          │
│   engine/loop.py              build deps + identity anchor + 调 RE   │
│   engine/_dependencies.py     EngineDependencies dataclass            │
│   engine/_identity_anchor.py  锁定 model/provider 身份                 │
├─────────────────────────────────────────────────────────────────────┤
│ L4 — Agent Loop（核心控制流）                                          │
│   runtime/agent/loop.py:run_engine_loop      外层（slash-cmd 之后）   │
│   runtime/agent/query_engine.py:run_query_engine   ★ REPL 主循环      │
│      ├ _call_llm_with_reactive_compact_retry        Phase 2（ADR 0008）│
│      ├ _build_execution_requests                    Phase 5            │
│      ├ _resolve_tool_approval_flow                  Phase 6            │
│      └ _record_tool_outcome                         Phase 7            │
│   runtime/agent/loop_state.py     LoopState + compute_args_digest      │
│   runtime/agent/loop_pathology.py detect() → PathologySignal           │
│   runtime/agent/parameter_loop.py preflight 参数补全机制                │
├─────────────────────────────────────────────────────────────────────┤
│ L5 — Domain Capability（领域能力）                                     │
│   runtime/tools/         工具注册 / 编排 / 钩子                        │
│   runtime/policy/        工具审批 + 策略状态机                          │
│   runtime/context/       消息装配 / token 预算 / reactive 压缩          │
│   runtime/storage/       transcript / tool_result / task               │
│   runtime/consensus/     ★ 多方法共识层（ADR 0010 / 0011）             │
│   skill/                 95 skill 解析 + 调度（→ skills/ 资源）        │
│   routing/               自然语言意图路由                              │
│   memory/                MemoryEngine + ReviewLog + MemoryClient        │
│   providers/             LLM provider 注册                             │
│   remote/                SSH 桥接（远端 Linux 执行）                   │
└─────────────────────────────────────────────────────────────────────┘
```

> **不在本图中的两个独立子系统**（各自有独立调用入口，不走 L4 单 chat turn 路径）：
>
> - `autoagent/`：实验循环 / patch engine / metrics — 用于自动化研究和优化任务。**已删除**；运行时调参见 `omicsclaw/ensemble/tuning/`。
> - `agents/`：**EvoScientist 风格的多 agent 研究流水线**（5481 行，基于 LangChain / deepagents / langgraph）。把"一个 idea"端到端跑成完整研究产出。详见 §7.10。
>
> **半独立 L5 子系统**（位于 L5 但有独立编排逻辑，复用 L5 其他模块但不与 L4 query_engine 交互）：
>
> - `runtime/consensus/`：**多方法共识层** — typed-then-narrative 双路径设计，N 个 skill subprocess 并行 fan-out + LLM 评审主席 + 类型化 operator。详见 §7.11；设计哲学 + 创新点见 §11。

---

## 3. L1 — Surface Layer 细节

### 3.1 三个 surface 的共同契约

所有 surface 都：

1. 把用户输入装进 `MessageEnvelope`（`runtime/agent/envelope.py`）
2. 调用 `dispatch(envelope)` 拿到一个 `AsyncIterator[Event]`
3. 按各自渲染规则消费 9 种 Event（见 L2）

这是 ADR 0005（Surfaces 雨伞）+ ADR 0006（事件流）合力的结果：surface 之间互不依赖，**任何 surface 故障都不会污染其他 surface**。

### 3.2 Channel Surface（`omicsclaw/surfaces/channels/`）

```
channels/
├── manager.py       ChannelManager（lifecycle 管理 N 个 adapter）
├── base.py          ChannelAdapter 抽象（10 个适配器都实现）
├── config.py        per-platform 环境变量映射
├── capabilities.py  能力声明（哪些渲染特性可用）
├── commands/        slash-command 注册
├── telegram.py | feishu.py | slack.py | discord.py | wechat.py
├── wecom.py | dingtalk.py | imessage.py | email.py | qq.py
├── README.md            per-platform 配置说明
└── CHANNELS_SETUP.md    总览设置文档
```

**运行方式**：`python -m omicsclaw.surfaces.channels --channels telegram,feishu` 或 `make bot-telegram`。Namespace 形如 `<platform>/<user_id>`（CONTEXT.md §"Surface namespace defaults"）。

**Channel 独有能力**：发送的照片自动走"组织切片分析"路径（H&E / 荧光 / spatial barcodes 识别 → 推荐 skill）。

### 3.3 Desktop Surface（`omicsclaw/surfaces/desktop/`）

```
desktop/
├── server.py                     FastAPI 主服务（host=127.0.0.1, port=8765）
├── _attachments.py               文件附件处理
├── _compaction_event_bridge.py   把 ContextCompacted 事件桥到 SSE
└── notebook/                     notebook session 子模块
```

**端点**：chat（SSE 流）、skills、providers、MCP、outputs、bridge control、memory proxy。客户端是 Electron 包装的 Next.js（位于 `frontend/`，与本文档无关）。

**身份**：`desktop_namespace()` 返回 `app/<OMICSCLAW_DESKTOP_LAUNCH_ID>` 或 `app/desktop_user`。

### 3.4 CLI Surface（`omicsclaw/surfaces/cli/`）

子模块密集程度最高的 surface（21 个文件），因为承担了 onboarding + REPL + TUI + 大量 slash-command。


| 文件                                                                  | 责任                                             |
| ------------------------------------------------------------------- | ---------------------------------------------- |
| `interactive.py`                                                    | prompt_toolkit REPL（`oc interactive`）          |
| `tui.py` + `_tui_support.py`                                        | Textual TUI（`oc tui`）                          |
| `launcher.py`                                                       | 共享启动逻辑                                         |
| `setup_wizard.py`                                                   | `oc onboard` 交互式配置                             |
| `_diagnostics_support.py`                                           | `/diagnostics` slash-command                   |
| `_history_support.py`                                               | 会话历史                                           |
| `_memory_command_support.py`                                        | `/memory` slash-command（兼容 ScopedMemory + 图记忆） |
| `_mcp.py`                                                           | MCP server 管理                                  |
| `_pipeline_support.py`                                              | 管线运行                                           |
| `_plan_mode_support.py`                                             | plan 模式                                        |
| `_session.py` + `_session_state.py` + `_session_command_support.py` | session 状态机                                    |
| `_skill_management_support.py` + `_skill_run_support.py`            | skill CRUD + 运行                                |
| `_slash_command_support.py`                                         | slash-command 分发                               |
| `_style_support.py`                                                 | 主题/样式                                          |
| `_llm_bridge_support.py`                                            | 桥接 LLM provider                                |
| `_omicsclaw_actions.py`                                             | 高层动作封装                                         |


**Namespace**：`cli_namespace_from_workspace(workspace_dir)`，缺省为绝对工作区路径（`~` 也算）。

---

## 4. L2 — Dispatch / Event Stream（ADR 0006）

### 4.1 入口 `dispatch(envelope)`

```python
# omicsclaw/runtime/agent/dispatcher.py
async def dispatch(envelope: MessageEnvelope) -> AsyncIterator[Event]:
    """Run one turn through llm_tool_loop, yielding events as they arrive.
    The generator terminates after exactly one Final or Error event.
    If the consumer breaks out early, the underlying loop task is cancelled."""
```

dispatcher 把 `llm_tool_loop` 的 **7 个 positional callbacks + 返回值 + 异常 + pending_media side-channel** 翻译成单一类型化事件流。**每请求**的状态都活在该函数的 local scope，**不持有跨调用的类**。

### 4.2 9 种 Event 类型（`events.py`）

```python
ProgressStart      # 工具开始（progress_id + text）
ProgressUpdate     # 工具进度更新
ToolCall           # 工具被调用（call_id + tool + parameters）
ToolResult         # 工具返回（call_id + result + ok）
StreamContent      # LLM 流式 content
StreamReasoning    # LLM 流式 reasoning_content（DeepSeek 等支持）
ContextCompacted   # 上下文压缩事件
PathologyDetected  # pingpong / repeated_failure 信号（ADR 0007）
Final              # 终态消息
Error              # 异常
```

### 4.3 设计意图

ADR 0006 在第三方 JSON-RPC 线协议（如 ACP）和"typed Python events"之间选了后者。**理由**：OmicsClaw 没有第三方 IDE 客户端接入需求；类型化事件让三个 surface 各自挑需要的事件渲染，**无需协议版本协商**。

---

## 5. L3 — Engine Layer（`omicsclaw/engine/`）

### 5.1 文件组成

```
engine/
├── loop.py              run_engine_loop（外层组装）
├── _dependencies.py     EngineDependencies dataclass
└── _identity_anchor.py  apply_model_identity_anchor + resolve_effective_model_provider
```

### 5.2 `EngineDependencies`

把"bot 侧依赖"打包成一个 dataclass 注入到 `run_engine_loop`，**强制 engine 不 import bot/**（由 `tests/test_no_reverse_imports.py` 守护）。字段包括：

```
llm, omicsclaw_model, llm_provider_name, session_manager, omicsclaw_dir,
max_history, max_history_chars, max_conversations, audit_fn,
usage_accumulator, skill_aliases, deep_learning_methods,
tool_runtime, tool_registry, callbacks_builder
```

### 5.3 关键常量

```python
MAX_TOOL_ITERATIONS = int(os.getenv("OMICSCLAW_MAX_TOOL_ITERATIONS", "20"))
DEFAULT_MAX_TOKENS = 8192
```

`MAX_TOOL_ITERATIONS` 是工具循环的**终极兜底**——pathology 检测做"软纠正"，到达上限才硬终止。

### 5.4 mode hint 注入

```python
_MODE_HINTS = {
    "code": "You are in code mode. Prefer writing and editing code ...",
    "plan": "You are in plan mode. Create detailed plans ...",
}
```

支持 `ask`（默认）/ `code` / `plan` 三种模式，对应 `oc interactive --mode plan` 等。

---

## 6. L4 — Agent Loop（核心控制流）

### 6.1 两层 loop 函数

OmicsClaw 的 agent 主循环**分两层**，是 ADR 0001（bot/core 拆分）历史拆迁的产物：


| 文件                              | 函数                                              | 责任                                                                             |
| ------------------------------- | ----------------------------------------------- | ------------------------------------------------------------------------------ |
| `runtime/agent/loop.py`         | `run_engine_loop` 647 行                         | slash-command 之后、preflight 之后的入口；构 system prompt + 装上下文 + 调 `run_query_engine` |
| `runtime/agent/query_engine.py` | `run_query_engine` 1147 行（主体 ~250 行 + 4 helper） | 真正的 REPL 主循环（一个 chat turn）                                                     |


### 6.2 `run_query_engine` 的 7 个 phase（ADR 0008）

```
Phase 0  Setup（callbacks/hooks/transcript prime/LoopState 构造）       63 行
Phase 1  每轮消息准备（prepare_model_messages）                          28 行
Phase 2  LLM 调用 + reactive-compact retry  ★ → _call_llm_...           75 行
Phase 3  Assistant 响应持久化                                            17 行
Phase 4  no tool_calls → terminate                                       13 行
Phase 5  Tool execution request build  ★ → _build_execution_requests    64 行
Phase 6  Tool execution + 审批解决  ★ → _resolve_tool_approval_flow      81 行
Phase 7  逐条结果后处理 + pathology  ★ → _record_tool_outcome + detect  124 行
```

四个 `_`-前缀 helper（`★`）是 ADR 0008 重构的产物，把最密的 4 块独立出来；剩下 phase 1/3/4 因为简单到不值得抽出而保留在主体。

### 6.3 `LoopState`（ADR 0007）

```python
@dataclass(slots=True)
class LoopState:
    iteration: int = 0
    tool_calls: deque[ToolCallRecord] = ...    # maxlen=20
    errors: deque[ToolErrorRecord] = ...       # maxlen=10
    signals: list[PathologySignal] = ...

@dataclass(frozen=True, slots=True)
class ToolCallRecord:
    name: str
    args_digest: str       # SHA-1（json.dumps sort_keys + default=str）
    iteration: int
    succeeded: bool

@dataclass(frozen=True, slots=True)
class ToolErrorRecord:
    tool_name: str
    iteration: int
    error_class: str
    message_head: str
```

`compute_args_digest` 把工具参数（可能是大文件路径、MCP 二进制）压成稳定的 SHA-1，**用于 pingpong 判定的细粒度对比**（`grep("A")` vs `grep("B")` 是两次不同的调用，不是 pingpong）。

### 6.4 `loop_pathology.detect(state)`

```python
PINGPONG_WINDOW = 6;  PINGPONG_THRESHOLD = 4   # 6 次里 4 次同 (name, digest)
FAILURE_WINDOW  = 8;  FAILURE_THRESHOLD  = 4   # 8 次错误里 4 次同 tool

def detect(state) -> PathologySignal | None:
    # pingpong 优先（同时存在时返回 pingpong，因为 "在循环" 比 "在失败" 更可操作）
    return _detect_pingpong(state) or _detect_repeated_failure(state)
```

**反应模型：软纠正**。检测到信号 → 注入 synthesized tool result 到下一轮 LLM → 让 LLM 自己决定恢复或终止。`MAX_TOOL_ITERATIONS=20` 是硬兜底。

### 6.5 `QueryEngineCallbacks`（变化点 / 组合式 hook）

```python
@dataclass(slots=True)
class QueryEngineCallbacks:
    accumulate_usage:     Callable[[Any], Any] | None
    on_stream_content:    Callable[[str], Any] | None
    on_stream_reasoning:  Callable[[str], Any] | None
    before_tool:          Callable[[ToolExecutionRequest], Any] | None
    after_tool:           Callable[[ToolExecutionResult, ToolResultRecord, Any], Any] | None
    request_tool_approval: Callable[[ToolExecutionRequest, ToolExecutionResult], Any] | None
    on_llm_error:         Callable[[Exception], Any] | None
    on_context_compacted: Callable[["CompactionEvent"], Any] | None
    on_pathology_signal:  Callable[[PathologySignal], Any] | None
```

ADR 0007 / 0008 选择**组合**（这个 dataclass）而非**继承**（Template Method 风格的类层级备选），核心论据：OmicsClaw 只有单一执行模式，子类层级没有承载需求。

### 6.6 `parameter_loop.py`（preflight 参数补全）

```
_apply_preflight_answers, _build_pending_preflight_message,
_extract_pending_preflight_payload, _is_affirmative_preflight_confirmation,
_parse_preflight_reply, _preflight_payload_needs_reply,
_remember_pending_preflight_request
```

skill 在执行前如果发现关键参数缺失，会先 emit "需要确认的参数"，转化为 LLM 的下一轮提示，等用户回答后再实际执行。这是 OmicsClaw 的 **clarification-as-tool-result** 模式实现（ADR 0007 §"Already present" 指出这等价于其他 agent 框架里常见的 `ASK_USER` 决策类型）。

---

## 7. L5 — Domain Capability（运行时支撑）

### 7.1 `runtime/tools/` — 工具系统

```
tools/
├── registry.py            ToolRuntime + 工具注册
├── spec.py                工具 schema 定义
├── orchestration.py       execute_tool_requests（并行执行）
│                          ToolExecutionRequest / ToolExecutionResult
├── execution_hooks.py     build_default_tool_execution_hooks
├── hooks.py               LifecycleHookRuntime（EVENT_TOOL_BEFORE/AFTER/FAILURE/SESSION_*）
├── executor.py            单工具执行器
├── predicates.py          条件判断
├── validation.py          参数校验
└── builders/              工具构造器（agent_executors 等）
```

**关键概念**：

- `ToolRuntime` 持有可调用工具集合 + JSON schema（暴露给 LLM）
- `LifecycleHookRuntime` 处理 5 个生命周期事件（SESSION_START / SESSION_RESUME / TOOL_BEFORE / TOOL_AFTER / TOOL_FAILURE）
- `execute_tool_requests` 并行执行多个工具请求

### 7.2 `runtime/policy/` — 工具审批

```
policy/
├── policy.py        evaluate_tool_policy → ToolPolicyDecision (allow/deny/REQUIRE_APPROVAL)
├── state.py         ToolPolicyState（跨轮次记忆审批决策）
├── conditions.py    条件规则
├── approval.py      审批流程
└── verification.py  验证
```

`TOOL_POLICY_REQUIRE_APPROVAL` 是关键状态：触发 `request_tool_approval` 回调让 surface 询问用户（"是否允许 OmicsClaw 写入 /etc/hosts？"）。

### 7.3 `runtime/context/` — 消息装配 + 压缩

```
context/
├── assembler.py       assemble_chat_context（系统 prompt + 历史 + memory + skill 元数据）
├── budget.py          check_token_budget + create_token_budget_tracker
├── compaction.py      ContextCompactionConfig + prepare_model_messages + wrap_compaction_summary
├── system_prompt.py   build_system_prompt
└── layers/            output_format（output style 渲染）
```

**Reactive compaction** = 当 LLM 返回 413（prompt too long）时，自动触发上下文压缩并重试一次。`has_attempted_reactive_compact` flag 保证一个 turn 内只重试一次。

### 7.4 `runtime/storage/` — 持久化

```
storage/
├── transcript.py      TranscriptStore（完整对话历史）
├── tool_result.py     ToolResultStore（工具结果归档）
└── task.py            task 状态持久化
```

- `transcript_store` / `tool_result_store` 在 `runtime/agent/state.py` 初始化为单例
- `should_persist_tool_result` 决定哪些工具结果落盘

### 7.5 `skill/` — Skill 系统

```
skill/
├── registry.py            OmicsRegistry（发现 + 加载 95 个 skill）
├── lookup.py              按名/别名/能力查找
├── listing.py             枚举（用于 `oc list`）
├── lazy_metadata.py       SKILL.md 元数据懒加载
├── domain_briefing.py     按 domain 输出简报
├── capability_resolver.py 能力解析（skill 之间的依赖）
├── parameters_md.py       从 SKILL.md 抽取参数表
├── chain.py               skill 链（spatial-pipeline 等）
├── execution/             skill 执行子模块
├── preflight/             skill 执行前检查
├── runner.py              单 skill 运行器
├── result.py              SkillResult
├── orchestration.py       多 skill 编排
├── protocol.py            skill 协议（输入/输出契约）
└── scaffolder.py          新 skill 脚手架
```

每个 skill 是 `skills/<domain>/<skill_name>/` 下的目录，含：

- `SKILL.md` — 方法学契约
- `<skill_name>.py` — Python 入口
- `r_renderers/` （可选）— R Enhanced 重绘
- `tests/` （可选）— 测试

95 个 skill 按 8 个 domain 分组（`skills/catalog.json` 是索引）。

### 7.6 `routing/` — 自然语言意图路由

```
routing/
├── router.py        route_query_unified（关键词优先 → LLM 兜底）
└── llm_router.py    LLM 路由实现
```

`route_keyword(query, keyword_map)` 走精确 / 模糊关键词；`_route_llm(query, skills, domain)` 用 LLM 在候选集中选 skill。**返回**：`(skill_id, confidence)`。

### 7.7 `memory/` — 图后端记忆

```
memory/
├── engine.py            MemoryEngine（Hot path：7 个动词）
├── memory_client.py     MemoryClient（策略层 + Namespace 解析）
├── review_log.py        ReviewLog（Cold path：版本链 / rollback）
├── database.py          SQLAlchemy 引擎初始化
├── models.py            Memory / Path / GlossaryKeyword 等 ORM
├── namespace_policy.py  Namespace 决策
├── glossary.py          术语映射
├── compat.py            CompatMemoryStore（兼容旧 bot 路径）
├── bootstrap.py         seed_knowhows（写入 core://kh/*）
├── scoped_memory.py     ScopedMemory（filesystem markdown 兼容）
├── scoped_memory_index.py
├── api/                 /memory/review/* admin endpoints + _browse_helpers
└── migrations/          schema migration
```

详见 `docs/CONTEXT.md` —— Memory URI = `domain://path`，按 7 个 domain（core/dataset/analysis/insight/preference/project/session）分类，按 Namespace 隔离。

### 7.8 `providers/` — LLM provider 注册

```
providers/
├── registry.py     ProviderRegistry（按名查找 provider）
├── runtime.py      LLM 运行时
├── models.py       模型元数据
├── patches.py      apply_deepseek_reasoning_passback 等模型补丁
├── timeout.py      超时管理
└── ccproxy.py      代理桥接
```

支持任意 OpenAI 兼容 endpoint，外加 DeepSeek 等的特殊补丁（thinking-mode 需要 `reasoning_content` 历史回传）。

### 7.9 `remote/` — 远端 Linux 桥接

```
remote/
├── app_integration.py
├── auth.py
├── routers/             FastAPI router
├── schemas.py
└── storage.py
```

支持把 skill 执行**透传到远端 Linux 服务器**（通过 SSH 隧道）—— 大数据集场景下，本地 UI + 远端计算。

### 7.10 `omicsclaw/agents/` — 多 agent 研究流水线（独立 L5+ 子系统）

> **注意**：此模块**不走 L4 `runtime/agent/` 路径**。它是一个独立的高层编排，基于 LangChain 生态（`deepagents` / `langchain` / `langgraph`）实现，需要可选依赖 `pip install -e ".[research]"`。

#### 7.10.1 设计来源

灵感来自 **EvoScientist**（自主科研 agent）和 **CellVoyager**（notebook session）。把"一个研究 idea + 可选论文/数据"端到端跑成研究产出（含 .ipynb + 报告）。

#### 7.10.2 7 阶段流水线

```
intake → plan → research → execute → analyze → write → review
                                                          │
                                                  不通过 → 回到 write 或 execute
```

每个 stage 在 `pipeline.py:PIPELINE_STAGE_DEFINITIONS` 登记，由不同 sub-agent 拥有（orchestrator / planner / researcher / executor / analyst / writer / reviewer）。

#### 7.10.3 3 种输入模式

| Mode | 输入 | 场景 |
|---|---|---|
| A | PDF + idea | 数据从论文 / GEO 可获取 |
| B | PDF + idea + h5ad | 用户自带数据 |
| C | idea only | 从零开始研究（EvoScientist 风格） |

#### 7.10.4 文件构成

```
agents/
├── __init__.py            run_research_pipeline 入口 + _check_research_deps lazy import
├── pipeline.py     1652行 ResearchPipeline + PipelineState 状态机 + 7 阶段编排
├── intake.py       1338行 PDF→Markdown + GEO accession / organism / tissue 提取
├── tools.py         551行 sub-agent 可调工具集（高于 runtime/tools/）
├── notebook_session.py  512行 持久 Jupyter kernel + .ipynb 编辑器（改自 CellVoyager）
├── prompts.py       354行 各 sub-agent 的 system prompt
├── plan_validation.py  300行 计划校验
├── pipeline_result.py  247行 PlanRunResult / CompletionRunResult / PipelineRunResult
├── backends.py      174行 LLM 后端配置
├── plan_state.py    159行 PlanStateSnapshot + 计划状态持久化（human-in-the-loop）
├── middleware.py     86行 中间件
└── config.yaml      18KB  sub-agents 配置（角色 / 工具 / prompt）
```

#### 7.10.5 入口

```python
# Python API
from omicsclaw.agents import run_research_pipeline
run_research_pipeline(idea="Investigate TME heterogeneity")                # Mode C
run_research_pipeline(idea="...", pdf_path="paper.pdf")                    # Mode A
run_research_pipeline(idea="...", pdf_path="paper.pdf", h5ad_path="d.h5ad") # Mode B
```

```bash
# CLI slash-command（lazy import 避免没装 research deps 时崩）
oc interactive
> /research --idea "..."
> /research paper.pdf --idea "..."
> /research paper.pdf --idea "..." --h5ad d.h5ad
> /research --idea "..." --output /path/to/output
```

#### 7.10.6 持久化与中断恢复

- `.pipeline_tasks.json`（`PIPELINE_TASK_STORE_FILENAME`）—— 7 阶段任务存储（复用 `runtime/storage/task:TaskStore`）
- `.pipeline_checkpoint.json`（`PIPELINE_CHECKPOINT_FILENAME`）—— 流水线状态快照
- 生成的 `.ipynb` —— 由 `NotebookSession` 持久化执行

中断后 `PipelineState.load_checkpoint(workspace)` 从最近完成阶段续跑。

#### 7.10.7 与 L4 `runtime/agent/` 的对照

| | L4 `runtime/agent/` | L5+ `omicsclaw/agents/` |
|---|---|---|
| 抽象层次 | 单 chat turn 的工具循环 | 多阶段研究流水线 |
| 触发 | 每次用户消息 | 一次 `/research` 命令 |
| 时长 | 秒~分钟 | 分钟~小时 |
| LLM stack | OpenAI 兼容 tool calling | LangChain / deepagents / langgraph |
| LLM 模式 | 单次响应 + tool loop | 多 sub-agent 协作 |
| 状态 | `LoopState`（in-memory，单轮） | `PipelineState` + `PlanStateSnapshot`（持久化） |
| 持久化 | `transcript_store` / `tool_result_store` | `.pipeline_*.json` + `.ipynb` |
| 中断恢复 | 不需要 | 必需 |
| 人在回路 | `request_tool_approval` callback | 计划审批（`PLAN_STATUS_PENDING_APPROVAL`） |
| 依赖 | 必装 | 可选（`[research]` extra） |

#### 7.10.8 被谁消费

- `surfaces/cli/_pipeline_support.py` — CLI 渲染 pipeline 进度
- `surfaces/cli/_plan_mode_support.py` — plan 模式（human-in-the-loop 审批）
- `surfaces/cli/_history_support.py` — pipeline 历史
- `surfaces/cli/interactive.py` — `/research` slash-command lazy import
- `surfaces/desktop/notebook/live_session.py` — Desktop notebook UI（`NotebookSession`）
- `execution/autonomous_analysis.py` — 自动化分析路径

#### 7.10.9 复用 L5 的内容

虽然不走 L4，但显式复用了 L5 的几个零件：

- `runtime/storage/task:TaskStore` —— 任务持久化
- `runtime/policy/verification` —— `build_completion_report` / `update_workspace_manifest` / `write_completion_report`
- `runtime/tools/hooks:build_default_lifecycle_hook_runtime` —— 生命周期 hook
- `providers/registry:get_langchain_llm` —— 复用 OmicsClaw 的 provider 注册（LangChain 适配版）
- `providers/timeout:build_llm_timeout_policy` —— 复用超时策略

### 7.11 `runtime/consensus/` — Typed-then-narrative 多方法共识层（半独立 L5 子系统）

> **注意**：此模块**不走每次 chat turn 的 L4 路径**。它是一个 *user-triggered* 的高层编排：由两个 thin skill (`consensus-domains` / `sc-consensus-clustering`) 通过常规 L4 工具调用触发，进入 consensus runtime 后复用 L5 的 `skill.runner.run_skill` 来 fan-out N 个子方法。consensus runtime 自身**不持有 query_engine**，只编排子 skill 的并行执行 + 类型化共识。

#### 7.11.1 设计来源

灵感来自 **SACCELERATOR**（SpatialHackathon 2023 / SpaceHack 2.0 — `consensus/03_Consensus_*` 系列 R 脚本）的"flexible expert-in-the-loop consensus framework"，把 N 个空间聚类方法的标签做 base-clustering (BC) 选择 + 类型化共识（kmodes / LCA / EnSDD-weighted）。OmicsClaw 保留这套思想，把"专家"角色由 LLM 担任，并把 paradigm 从 spatial-clustering 一种任务扩展到 spatial-clustering + sc-clustering 两种任务（v2 计划扩到 DE）。设计哲学和创新点见 §11。

#### 7.11.2 双路径设计：A 路径 typed / B 路径 narrative（ADR 0010）

| 路径 | 触发条件 | 操作子 | 输出 banner | graph memory namespace |
|---|---|---|---|---|
| **A (typed / verified)** | skill ∈ `TYPED_CONSENSUS_REGISTRY` | kmode / weighted（Python）/ LCA（R subprocess） | `[A: Verified consensus]`（强制） | `analysis://typed/<run_id>` |
| **B (narrative / exploratory)** | skill ∉ registry，或显式 `--mode narrative` | LLM extract-then-synthesise + contradiction annotation | `[B: Exploratory synthesis — NOT statistical consensus]`（强制） | `analysis://exploratory/<run_id>` |

ADR 0010 §"Pass-rule" 明令禁止 A 路径自动降级到 B —— A 不通过抛 `InsufficientSurvivorsError` 让用户看到。

#### 7.11.3 文件构成

```
runtime/consensus/
├── __init__.py
├── team.py                  ★ asyncio.gather 并行 fan-out（max_parallel = min(N, cpu//2, 4)，timeout 600s）
├── member.py                  ConsensusMember 数据类（只携带 name/skill_name/params；artifact schema 已下放到 reader）
├── source_registry.py       ★ v1.1 deepening：MemberArtifactReader Protocol + 2 adapter（spatial / sc-clustering） +
│                              TypedConsensusSource frozen dataclass + TYPED_CONSENSUS_REGISTRY: dict[str, Source]
├── dispatch.py                A/B 路径决策（select_consensus_mode + consensus_namespace + output_banner）；
│                              registry 从这里再 re-export，单文件 allowlist 不变
├── driver.py                ★ v1.1 deepening：run_typed_consensus 唯一 orchestration entry +
│                              TypedConsensusRun + ScoreConfig + InsufficientBCsError；fan-out → scoring → BC pick → operator → artifact 写盘
├── report.py                ★ v1.1 deepening：format_typed_report — banner enforcement 唯一位置（thin skill 无法绕过）
├── plan.py                    ★ 评审主席（LLM mode + deterministic fallback；从 param_hints 选 N 成员）
├── scoring.py                 ★ 复合 BC 分数：α·cross_NMI + β·intrinsic + max_class_frac > 0.8 硬过滤
├── spatial_metrics.py         ★ MLAMI（nichecompass BSD-3 移植） + CHAOS / PAS（SACCELERATOR MIT-0 等价）
├── operators/
│   ├── alignment.py           Hungarian alignment（scipy.optimize.linear_sum_assignment）
│   ├── categorical.py         kmode + weighted（Python；earliest-column tiebreak）
│   └── lca_r/
│       ├── consensus_lca.r    diceR::LCA 移植（SACCELERATOR 归因 + LICENSE 兼容）
│       ├── env.yaml           conda recipe
│       └── wrapper.py         subprocess driver + LCAUnavailableError 优雅降级
└── narrative/
    ├── extractor.py           ★ per-member structured extraction（confidence + caveats 强制）；
    │                          LLM 调用 1 行 delegate 到 providers/chat_completion
    ├── synthesizer.py         ★ N JSONs → 综合 markdown（contradictions 强制段；banner 不可关）；同上 1 行 delegate
    └── prompts/
        ├── extract.tmpl
        └── synthesize.tmpl

providers/                     # 与 consensus 协同的两个新零件
├── chat_completion.py       ★ v1.1 deepening：call_chat_completion(prompt, *, timeout, temperature) -> Optional[str]
│                              best-effort，任何失败返回 None；plan/narrative 三处 LLM 调用统一走这里
└── runtime.py                 + resolve_chat_endpoint() -> (api_key, base_url, model)
                               （从 llm_router._resolve_llm_config 提升到 provider 层；router 现在 1 行 alias 兼容）
```

#### 7.11.4 关键概念

- **Consensus member** —— `ConsensusMember(name, skill_name, params)`；**一个 deterministic skill subprocess**，不是 LLM sub-agent。
  *v1.1 deepening*：原本绑在 member 上的 `artifact_relpath / label_column / intrinsic_quality_path` 三字段已下放到 reader（见下条），让 member 退化为纯调度元数据。
- **MemberArtifactReader (v1.1)** —— Protocol；把"成员产物落在哪 / 标签列叫什么 / 内禀质量文件叫什么"的 schema 知识从 member 移到 per-skill adapter（`SpatialDomainsArtifactReader` / `ScClusteringArtifactReader`）。新 typed source 加入只需写一个 adapter + 注册表一行。
- **TypedConsensusSource (v1.1)** —— frozen dataclass `(skill_name, reader, default_n_members)`。Registry 从 `set[str]` 升级为 `dict[str, TypedConsensusSource]`，**值携带行为**而不只是成员资格标志。
- **TypedConsensusRun (v1.1)** —— `run_typed_consensus` 的返回值；冻结一次 typed 跑的全部产物（`team_result / scores / selected_bcs / consensus / nmi_matrix / operator / run_id / output_dir`），供 `format_typed_report` 渲染。
- **Evaluation chair** —— LLM 评审主席。只挑成员 + 解读结果，**不做统计合并**（mode-voting 由 operator 负责）。
- **Base clusterings (BC)** —— 用户在 fan-out 后从分数排名里挑出的子集（CLI 交互；Desktop/Channel 走 top-K 默认）。BC selector 已抽成 `BCSelectorFn` 可调用 seam（v1.x 转 Protocol）。
- **Typed Consensus Registry** —— `source_registry.py` 单文件 allowlist；新 skill 加入必须显式注册 + ADR review。

#### 7.11.5 用户入口（两个 thin skill）

```bash
# spatial
oc run consensus-domains --input preprocessed.h5ad --output out/ \
  [--members banksy,graphst,sedr,leiden,spagcn]   # 显式
  [--all]                                          # 全 fan-out
  [--operator kmode|weighted|lca] [--non-interactive]

# singlecell（resolution sweep）
oc run sc-consensus-clustering --input preprocessed.h5ad --output out/ \
  [--resolutions 0.5,0.8,1.0,1.4,2.0] [--cluster-methods leiden,louvain]
```

#### 7.11.6 与 L4 / L5 既有零件的关系

| 关系 | 说明 |
|---|---|
| **复用 L5 `skill.runner.run_skill`** | fan-out 每个成员都是一次常规 skill subprocess（继承 ADR 0009 的 `threading.Event` → `killpg` cancel 链） |
| **不引入新 dispatch event** | A/B 路径决策在 consensus runtime 内部；ADR 0006 typed event 流不变 |
| **不持有 query_engine 实例** | 与 L4 `runtime/agent/` 解耦；query_engine 通过 thin skill 的 `--query` arg 把信息传进来 |
| **plan / narrative 的 LLM 调用** | 统一走 `omicsclaw.providers.chat_completion.call_chat_completion`（v1.1 deepening；plan.py / narrative/extractor.py / narrative/synthesizer.py 三处的 HTTP boilerplate 收敛成 1 行 delegate，endpoint 解析提升为 `providers.runtime.resolve_chat_endpoint`） |
| **失败语义** | `InsufficientSurvivorsError`（< 2 存活）抛到 thin skill → CLI 退出码 3，**不静默降级** |

#### 7.11.7 评估协议（ADR 0011 amendment）

Task-targeted 三轴：

| 轴 | metric | 触发 |
|---|---|---|
| **GT-比对（hero benchmark）** | ARI + AMI + V-measure + MLAMI（spatial-only） hard pass AND；H + C + CHAOS + PAS report-only | DLPFC 151673 + `RUN_DLPFC_BENCHMARK=1` |
| **stability（self-consistency）** | AMI 跨 seed stdev | unit test 必跑 |
| **BC ranking（每次 consensus 跑）** | α·cross_NMI + β·intrinsic + 0.8 max_class_frac 硬过滤 | runtime 必跑 |

#### 7.11.8 测试

```
tests/runtime/consensus/
├── test_alignment.py             6 cases — Hungarian permutation recovery
├── test_categorical_operators.py 11 cases — kmode/weighted 确定性
├── test_member_scoring.py        13 cases — 复合分数 + 硬过滤 + shape 不匹配抛错
├── test_team_runtime.py          22 cases — 并行 fan-out + cancel + timeout 不广播（v1.1：3 个 read_intrinsic_quality 用例迁出）
├── test_source_registry.py    ★ 12 cases — v1.1：MemberArtifactReader + adapters + TypedConsensusSource registry
├── test_driver.py             ★  6 cases — v1.1：run_typed_consensus orchestration + InsufficientBCsError
├── test_lca_wrapper.py            4 cases — R subprocess（1 gated requires-R）
├── test_plan_narrative.py        17 cases — plan + narrative + 花括号鲁棒性
├── test_spatial_metrics.py       13 cases — MLAMI + CHAOS + PAS
├── test_self_consistency.py       2 cases — AMI stdev seed-vs-seed
└── test_dlpfc_benchmark.py        3 cases — schema 校验 + dry-run + gated full run

tests/providers/
└── test_chat_completion.py    ★  8 cases — v1.1：best-effort delegate + endpoint resolve + 失败返回 None
```

共 **123 passed + 2 skipped**（R / DLPFC `RUN_DLPFC_BENCHMARK` gate）。v1 ship 时为 100；v1.1 deepening 新增 23 case。

---

## 8. 关键调用链：一次 chat 请求的生命周期

```
┌─────────────────────────────────────────────────────────────┐
│ 1. 用户在 CLI/Desktop/Channel 中输入消息                       │
└──────────────────────────────┬──────────────────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ 2. Surface 构造 MessageEnvelope（含 chat_id, user_content,    │
│    surface 标签, attachments...）                              │
└──────────────────────────────┬──────────────────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ 3. dispatch(envelope) → AsyncIterator[Event]                  │
│    在 dispatcher.py 内：                                       │
│    - 创建 asyncio.Queue                                        │
│    - 起 task 运行 run_engine_loop                              │
│    - 边消费 queue 边 yield Event                               │
└──────────────────────────────┬──────────────────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ 4. engine/loop.py:run_engine_loop                              │
│    - 解析 model/provider（identity_anchor）                    │
│    - 处理 slash-command 分发                                   │
│    - 处理 pending preflight resume                             │
│    - assemble_chat_context（系统 prompt + 历史 + memory）       │
│    - 构 QueryEngineConfig + QueryEngineContext + Callbacks     │
└──────────────────────────────┬──────────────────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ 5. runtime/agent/query_engine.py:run_query_engine              │
│    主循环（每轮）：                                              │
│    ① prepare_model_messages（计算 token 预算）                   │
│    ② _call_llm_with_reactive_compact_retry                     │
│       └ LLM API call（流式 emit StreamContent / Reasoning）     │
│       └ 413 时触发 compaction（emit ContextCompacted）         │
│    ③ 持久化 assistant message 到 transcript                    │
│    ④ no tool_calls → emit Final + return                       │
│    ⑤ _build_execution_requests                                 │
│       └ 对每个 tool_call: emit ToolCall                        │
│       └ 触发 EVENT_TOOL_BEFORE hook + before_tool callback     │
│    ⑥ execute_tool_requests（并行执行）                          │
│       └ _resolve_tool_approval_flow                            │
│          └ REQUIRE_APPROVAL 时 callback → surface 询问用户      │
│    ⑦ _record_tool_outcome（逐条）                              │
│       └ emit ToolResult                                        │
│       └ 触发 EVENT_TOOL_AFTER / FAILURE hook                   │
│       └ 追加到 LoopState.tool_calls / errors                   │
│       └ 持久化到 tool_result_store                             │
│    ⑧ detect_loop_pathology(state)                              │
│       └ pingpong / repeated_failure → emit PathologyDetected    │
│       └ 注入合成 tool result 到下一轮                          │
│    ⑨ iteration += 1, 回到 ①                                    │
└──────────────────────────────┬──────────────────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ 6. surface 边迭代 event 边渲染                                  │
│    CLI: 写到终端                                                │
│    Desktop: SSE 推送到前端                                      │
│    Channel: 调 platform API 发送消息                            │
└─────────────────────────────────────────────────────────────┘
```

---

## 9. 数据模型一览

### 9.1 Agent 循环域


| 类型                                   | 位置                      | 性质                                                                      |
| ------------------------------------ | ----------------------- | ----------------------------------------------------------------------- |
| `MessageEnvelope`                    | `agent/envelope.py`     | dispatch 入参                                                             |
| `QueryEngineConfig`                  | `agent/query_engine.py` | 配置（model / max_iterations=20 / max_tokens / compaction）                 |
| `QueryEngineContext`                 | `agent/query_engine.py` | 单次请求上下文（chat_id / surface / policy_state / hook_runtime / token_budget） |
| `QueryEngineCallbacks`               | `agent/query_engine.py` | 8 字段回调                                                                  |
| `LoopState`                          | `agent/loop_state.py`   | 循环状态（iteration / deque[20] tool_calls / deque[10] errors / signals）     |
| `ToolCallRecord` / `ToolErrorRecord` | `agent/loop_state.py`   | bounded 历史项                                                             |
| `PathologySignal`                    | `agent/loop_state.py`   | 病态信号（pingpong / repeated_failure）                                       |
| `Event` (9 种)                        | `agent/events.py`       | 事件流                                                                     |


### 9.2 工具域


| 类型                     | 位置                       | 性质                                                 |
| ---------------------- | ------------------------ | -------------------------------------------------- |
| `ToolRuntime`          | `tools/registry.py`      | 工具注册容器                                             |
| `ToolExecutionRequest` | `tools/orchestration.py` | 单次调用请求                                             |
| `ToolExecutionResult`  | `tools/orchestration.py` | 单次调用结果（status / EXECUTION_STATUS_POLICY_BLOCKED 等） |
| `ToolPolicyState`      | `policy/state.py`        | 跨轮次审批状态                                            |
| `LifecycleHookRuntime` | `tools/hooks.py`         | 生命周期钩子运行时                                          |
| `ToolResultRecord`     | `storage/tool_result.py` | 落盘归档                                               |


### 9.3 Memory 域（见 CONTEXT.md）

`Memory` / `Path` / `GlossaryKeyword` / `MemoryEngine` / `MemoryClient` / `ReviewLog` / `Namespace` / `Memory URI` / `Domain`.

---

## 10. ADR 编年史（决策追踪）


| ADR   | 标题                                      | 状态       | 关键决定                                                                                                   |
| ----- | --------------------------------------- | -------- | ------------------------------------------------------------------------------------------------------ |
| 0003  | message-bus-decision                    | Accepted | 不引入消息总线；事件流直接通过 callback / queue 传递                                                                    |
| 0033  | skill-template-is-human-copy-only       | Accepted | skill 模板只供人类复制，不做自动化                                                                                   |
| 0004  | boundary-restructure-fold-bot           | Accepted | 把 bot/ 折叠进 surfaces/channels/ 与 runtime/，消除 bot 边界                                                     |
| 0005  | surfaces-umbrella-for-ingress           | Accepted | CLI / Desktop / Channels 三个 surface 统一在 `surfaces/` 雨伞下                                                |
| 0006  | agent-dispatch-event-stream             | Accepted | `dispatch(envelope) → AsyncIterator[Event]`；用 typed events 代替 ACP 线协议；关闭 Redis queue / worker 路径       |
| 0007  | loop-state-and-pathology-detection      | Accepted | 引入 `LoopState` + `loop_pathology.detect()`（参考外部 agent runtime 实现）；显式拒绝复杂类层级、DecisionType enum、跨进程 worker queue |
| 0008  | decompose-run-query-engine-into-helpers | Accepted | 把 `run_query_engine` 491 行 body 拆成主体 ~250 行 + 4 个 `_`-前缀 helper                                        |
| 0009  | wire-cancel-event-through-dispatch      | Accepted | `MessageEnvelope.cancel_event`（`threading.Event`）从 dispatch 一路串到 `skill.runner.run_skill` 的 `killpg` 链 |
| 0010  | consensus-runtime-layer                 | Accepted | 引入 `runtime/consensus/`；typed-then-narrative 双路径；in-process asyncio fan-out（**拒绝**跨进程 Gateway / queue / worker 四层模型） |
| 0011  | consensus-evaluation-protocol           | Accepted (amended) | 复合 BC 分数 + DLPFC 151673 hero benchmark + self-consistency；2026-05-18 amend：task-targeted metric panel（ARI 单 metric → 4 hard + 4 report-only）|


> **历史注**：仓库里曾有两个 `0003-*.md` 与两个 `0024-*.md`（编号冲突）；2026-06-22 已重编号消解——`skill-template-is-human-copy-only`→0033、`bench-heartbeat-episodic-memory`→0034（`message-bus-decision` 保留 0003，`prompt-prefix-caching` 保留 0024）。ADR 0009 起恢复连续编号，0010/0011 已就位（§7.11 / §11）。

---

## 11. Consensus Runtime 的设计哲学与创新点

> 本节专门讨论 `runtime/consensus/`（§7.11）的**设计立意**和**与同类 system 的差异化**。它不是新的架构层，而是 L5 内的一个独立 paradigm。架构层的事实性记录见 §7.11；本节聚焦"为什么这样设计、新在哪里"。

### 11.1 问题陈述

**单一聚类方法的输出对参数 / 算法 / 数据偏置敏感**。BANKSY、GraphST、SEDR、Leiden、SpaGCN 在 DLPFC 上 ARI 通常在 0.45–0.70 区间徘徊，但在 cancer / 非标 tissue 上的失败模式各异——同一片样本，5 个方法可能给出 5 套不一致的 layer 划分。**用户没法判断"这个结果是不是稳健的"**。

业界既有共识范式（SACCELERATOR / diceR / nichecompass-benchmark）解决了**一部分**，但留了三个缺口：

| 缺口 | 现状 | 影响 |
|---|---|---|
| **(a) 跨组学普适性** | 局限在 spatial clustering（SACCELERATOR）或 sc latent benchmark（nichecompass） | 用户在跨技术（Visium + scRNA）/ 跨组学（DE / variant）场景里需要重新造 paradigm |
| **(b) "已验证 vs 探索性"边界不可审计** | 报告里没有 banner，graph memory 写在同一 namespace；下游 meta-analysis 区分不出 | 论文复现 / 审稿 / 团队协作时无法快速辨别证据强度 |
| **(c) LLM 在范式中的位置混乱** | 要么不用（SACCELERATOR）；要么 LLM 做"统计合并"——错位（generic agent fan-out tools） | LLM 不擅长 1 万标签向量的众数投票，但擅长挑成员 + 解读结果——两端而非中段 |

### 11.2 三个独立可发表的创新支点

**单做任一支点都不算贡献**（每个都已有先例），三者**合起来**才是 OmicsClaw 独有的 paradigm：

#### 支点 1 ：首次把 SACCELERATOR expert-in-the-loop consensus **用 LLM 操作化**

- **角色分离**：评审主席（LLM）vs. 操作子（确定性算法）。LLM 只做两件事：
  - **挑选**：根据 query + 数据特征 + `param_hints`，从 N 个候选方法挑 5 个 fan-out
  - **解读**：N 个方法的 cross-method NMI 矩阵 + 复合分数 + consensus output → 写一份带矛盾标注的 markdown 报告
- LLM **永远不参与统计合并**——投票交给类型化 operator（kmode / weighted / LCA）
- 这是 SACCELERATOR 的"人类专家选 BC"思想的 LLM 落地，**首次实现**

#### 支点 2 ：把 typed-consensus paradigm **从 clustering 扩展到跨组学**

| 输出 schema | v1 实现 | v2 计划 | v3 计划 |
|---|---|---|---|
| categorical / per-observation | ✅ spatial-domains + sc-clustering | celltype annotation（输入异质性挑战）| — |
| ranked gene lists | — | DE-RRA（DESeq2 + limma + edgeR + pydeseq2）| — |
| genomic intervals | — | — | variant / peak interval merge |

`TYPED_CONSENSUS_REGISTRY` allowlist 是这套扩展的**关键边界设计**——新 skill 要进入 typed 路径必须显式注册 + ADR review，不做隐式 schema 嗅探。

#### 支点 3 ：可审计的"已验证 vs 探索性"边界

| 边界面 | 实现 | 不可关闭 |
|---|---|---|
| 报告 banner | `[A: Verified consensus]` / `[B: Exploratory synthesis — NOT statistical consensus]` 强制 prepend | ✓ |
| graph memory namespace | `analysis://typed/<run_id>` vs `analysis://exploratory/<run_id>` | ✓（dispatch.py 中决策一次性） |
| 失败语义 | A 路径 `< 2` 存活抛 `InsufficientSurvivorsError`，**不自动降级 B** | ✓ |
| metric 体系 | A 路径走 hard pass panel；B 路径不定量评估、仅 narrative | ✓ |

这是 LLM + 生信智能体领域**目前没人显式解决**的可信度边界问题。审稿人 / 团队协作 / 下游 meta-analysis 可以**默认只读 `analysis://typed/*`**，不污染严格证据链。

### 11.3 与同类 system 的对比

| | **SACCELERATOR** | **nichecompass benchmarking** | **通用 LLM sub-agent fan-out 框架** | **OmicsClaw consensus** |
|---|---|---|---|---|
| **应用范畴** | spatial clustering only | spatial latent representation 基准 | LLM sub-agent fan-out（通用 agent runtime） | spatial + sc clustering（v2 DE / v3 intervals） |
| **共识算法** | iterative R: `diceR::k_modes` + LCA + EnSDD | N/A（评测工具） | LLM-based narrative synthesis | typed: Python kmode / weighted + R LCA；B 路径：narrative |
| **人在回路** | 显式 BC 选择（专家手工挑） | N/A | 无 | CLI 同步 BC picker；Desktop/Channel top-K 默认 |
| **评估面板** | 17 R-only metrics（全跑） | 10 multi-axis（CAS/MLAMI/CLISIS/GCS/NASW/+batch）| N/A | **task-targeted**：hero panel = ARI+AMI+V+MLAMI；self-consistency = AMI；BC ranking = α·NMI+β·intrinsic |
| **LLM 在范式中** | 不用 | 不用 | LLM 是整个 sub-agent，包括统计 | LLM 只在两端（plan + narrate），统计交确定性 operator |
| **验证 vs 探索 边界** | 隐式 | 隐式（只评测，不混结果）| 隐式 | **显式 banner + namespace** |
| **跨进程 vs in-process** | R 子进程链 | Python in-process | Redis queue / worker 多进程 | in-process asyncio.gather（ADR 0010 明确**拒绝**跨进程模型） |
| **可扩展性** | R 模块化（dataset / method / metric 三类）| 评测函数级别 | 任意 sub-agent | TYPED_CONSENSUS_REGISTRY allowlist + thin skill 模板 |

### 11.4 关键技术选型（带"为什么不"）

#### 11.4.1 typed operator 选简化 Python，**不**与 SACCELERATOR R 算法 bit-exact

SACCELERATOR 的 `diceR::k_modes` 是迭代 k-modes 算法（基于 published paper），EnSDD 是 NMF + Leiden 后处理的复合算子。OmicsClaw v1 选 **per-row mode after Hungarian alignment**（kmode）+ **weighted majority**（weighted）—— 简化、可审计、零 RNG。

**为什么**：LLM 评审主席是头牌创新，operator 算法 bit-exact 与上游一致**不是关键**（ADR 0010 §Consequences）。简化 operator 让单测能用确定性 fixture 而非 R subprocess fixture。LCA 留 R subprocess（poLCA 是真正的 LCA EM 算法，Python 等价物风险高）。

#### 11.4.2 评估走 **task-targeted metric panel**，不走 ARI-only

3 个评估轴，3 套不同 metric（ADR 0011 amendment）：

```
hero benchmark (有 GT):
  ARI + AMI + V-measure + MLAMI(spatial)    # hard pass AND
  H + C + CHAOS + PAS                       # report-only diagnostic

self-consistency (无 GT):
  AMI stdev across seeds                    # 单 metric stability

BC ranking (无 GT):
  α·cross_NMI + β·intrinsic                 # 2 轴复合分数
```

**为什么**：ARI 单一 metric 有已知偏置（对 cluster 数偏置，不区分 over-merge / over-split，不感知空间结构）。SACCELERATOR 自己实现了 17 metric 不是没有道理。但全跑 17 个是过工程——挑覆盖**三个独立 axes 的最小集**：agreement + chance-correction + over-merge/over-split 诊断 + spatial coherence。

#### 11.4.3 MLAMI / CHAOS / PAS 走 **vendor + attribute**，不依赖 `nichecompass[benchmarking]`

`nichecompass[benchmarking]` 拉 jax / mlflow / scib-metrics 传染依赖。OmicsClaw v1 **vendor 算法源码**，pure Python（numpy + scanpy + sklearn）实现 + 完整 LICENSE 归因（BSD 3-Clause for MLAMI；MIT-0 for CHAOS/PAS）。

**为什么**：与 SACCELERATOR R operator 走 vendor 同一 pattern（ADR 0010）。default install 不膨胀；用户随时可以 `pip install nichecompass` 自己跑原版做交叉验证。

#### 11.4.4 fan-out 走 in-process `asyncio.gather`，**不**用跨进程队列模型

ADR 0010 + 0006 + 0003 三次重申拒绝 `Gateway → Redis → Worker → EventBus` 四层跨进程模型。**为什么**：OmicsClaw 是**单机单用户研究工具**（CLAUDE.md §Safety Rules: 基因数据不出本机）。跨进程伸缩 / 持久队列 / 多租户调度都不是要解决的问题。in-process asyncio + `Semaphore` 并发预算（`min(N, cpu//2, 4)`）就够。

#### 11.4.5 Per-member timeout **不**广播 `cancel_event`（C1 fix）

ADR 0010 操作性默认表写明"≥ 2 存活继续"。team.py runtime 一开始的实现有 bug：单成员 timeout 在 except 分支 `cancel_event.set()`——共享 event 被广播 → 全部兄弟 cancel → 整 team 阵亡。code-review C1 抓到，已修。

**为什么记**：这是 ADR-到-代码契约的一致性问题——文档说"≥ 2 存活"，代码实现得"任意 timeout 全死"——审查时容易漏。回归测试 `test_timeout_does_not_cancel_sibling_members` 长期锁定这条不变量。

### 11.5 可证伪性

设计成功的可检查证据：

| 主张 | 怎么证伪 |
|---|---|
| "consensus 比最好的单方法更稳" | self-consistency: AMI stdev consensus > best member → fail |
| "consensus 在 GT 比对上不输给最好的单方法" | DLPFC 151673 hero: 任一 hard metric `consensus < best_member - noise_floor` → fail |
| "A/B 边界是硬的" | 报告里看不到 banner → 视为代码 bug |
| "LLM 不做统计合并" | grep 任何 LLM 调用对应到 mode-voting 或加权平均 → 视为越权 |
| "evaluation chair 不能凭空打分" | `--llm-judge` 模式下 LLM 能改变成员排名，但 α/β 调整必须在 ±0.2 内（ADR 0011） |

### 11.6 v1 边界 / 已知 trade-off / v1.x 后续

| 项 | v1 现状 | v1.x / v2 计划 |
|---|---|---|
| B 路径用户入口 | **代码完整，但无 CLI entry**（仅可 Python API 调用） | v1.x：`oc run consensus-narrative --skill <X>` |
| thin skill 数量 | 2（spatial-domains + sc-clustering） | v2：consensus-celltypes（异质输入 + 模型自动挑选）+ consensus-de（DE-RRA） |
| composite member score | 2 轴（α·cross_NMI + β·intrinsic） | v1.x ADR：是否扩到 3 轴（spatial-smoothness）|
| evaluation 与 graph memory | 评估 metric 不写入 graph memory | v1.x：A 路径产物的 metric trace 进 `analysis://typed/<run_id>/metrics/*` |
| Surface-aware BC picker | 只 CLI 同步；Desktop/Channel 走 top-K 默认 | v1.x：新增 `consensus_plan_proposed` dispatch event（ADR 0006 扩展） |

### 11.7 给评审 / 读者的快速核查路径

如果你要快速核查"这个 paradigm 的实现质量"，建议这条路径：

1. **ADR 0010** — 架构边界 + rejected alternatives + 操作性默认表
2. **ADR 0011** — metric panel rationale + 4 hard / 4 report-only / pass rule
3. **`runtime/consensus/dispatch.py`** — 23 行；A/B 边界一文件审计
4. **`runtime/consensus/team.py:148-156`** — 单成员 timeout **不**广播 cancel 的注释（C1 fix）
5. **`tests/runtime/consensus/test_team_runtime.py::test_timeout_does_not_cancel_sibling_members`** — 上一条的回归锁
6. **`examples/consensus_benchmark/expected_metrics.json`** — task-targeted panel 的 schema
7. **`docs/CONTEXT.md` §"Cross-reference: Consensus runtime"** — 词汇前向声明

```bash
# 一行跑全部单测：
python -m pytest tests/runtime/consensus/ tests/providers/ \
  skills/spatial/consensus-domains/tests/ \
  skills/singlecell/scrna/sc-consensus-clustering/tests/
# 期望：123 passed, 2 skipped（v1 → v1.1 deepening 后：+23 case）
```

### 11.8 v1.1 deepening pass（2026-05-18 当天，post-ship）

v1 ship 之后立即跑了一轮 `improve-codebase-architecture` 的深化审查（用 LANGUAGE.md 词汇：module / interface / depth / seam / adapter / leverage / locality / deletion test）。审查识别出三个 trinity duplication + 一处 registry **shallow** 的问题，落地了 3 个 bundle：

| Bundle | 问题（deletion test） | 实现 | 提升 |
|---|---|---|---|
| **A — MemberArtifactReader + TypedConsensusSource** | `TYPED_CONSENSUS_REGISTRY: set[str]` 只标"是否进 A 路径"，artifact schema（relpath / label column / quality file）由 thin skill 自己重复编码——deletion test：删掉 set，每个 thin skill 都得各自 hardcode schema，**复杂度上移而非消解** | 新 `source_registry.py`：Protocol `MemberArtifactReader` + 2 个 reader adapter + `TypedConsensusSource` frozen dataclass；registry 升级为 `dict[str, TypedConsensusSource]`，值携带行为 | registry 从 shallow 标志 → **deep adapter dispatch**；新 typed source 加入只需 reader + 一行注册（之前要改 5 处） |
| **B — `run_typed_consensus` driver + `format_typed_report`** | 两个 thin skill 各自重复 fan-out → scoring → BC pick → operator → 4 artifact 写盘 + banner 强制（trinity duplication × ~250 行）；新加 thin skill 等于复制粘贴 | 新 `driver.py:run_typed_consensus(*, members, source, ..., bc_selector, score_config, runner) -> TypedConsensusRun` + `report.py:format_typed_report` 唯一 banner enforcement 点 | thin skill 退化为"CLI 解析 + member 规划 + BC selector 构造"3 件事；行数 781 → 438（−44%）；banner 不可被任何 thin skill 绕过 |
| **C — `call_chat_completion` + `resolve_chat_endpoint`** | plan / extractor / synthesizer 三处都 `from omicsclaw.routing.llm_router import _resolve_llm_config` + 重复 `httpx.AsyncClient` boilerplate（trinity duplication × ~40 行 + 私有 import 跨边界） | 新 `providers/chat_completion.py:call_chat_completion(prompt, *, timeout, temperature) -> Optional[str]`；endpoint 解析提升为 `providers.runtime.resolve_chat_endpoint`；router 保留 1 行 alias 向后兼容 | 3 处 LLM 调用收敛为 single-line delegate；不再有 thin skill / runtime / narrative 反向依赖 routing 的私有 helper |

**测试**：v1 时 100 → v1.1 时 123 passed + 2 skipped（+23 case：12 source_registry + 6 driver + 8 chat_completion，- 3 个 read_intrinsic_quality 用例迁出到 reader 测试）。

**Worth-doing-next-pass 候选**（审查识别但未本轮落地，未列入 v1.x ADR 之前不动）：

- `BCSelectorFn` 当前是 `Callable[[list[MemberScore], int], list[str]]`；当 Desktop / Channel surface 接入交互式 BC 选择时，转 Protocol 让 surface 注入而非 thin skill 写死。
- `MemberPlanner` adapter — 两个 thin skill 的 `_plan_members` 还在各自实现 sweep / explicit-list 解析；如果第三个 thin skill 出现且 planner 形态趋同，再统一。

注意：v1.1 deepening **没有引入新 ADR**——它是 ADR 0010 边界内的实现深化，A/B 路径决策、TYPED_CONSENSUS_REGISTRY allowlist 性质、failure semantics 一律不变。

---


