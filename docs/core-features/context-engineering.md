# Context Engineering 上下文管理实现原理

## 1. 背景与设计目标

### 1.1 问题背景

ReAct 引擎（`omicsclaw/engine/`）本身不知道对话从哪里来：`AgentEngine.run(messages)` 接收的是一段**已经组装好**的对话，引擎只负责循环。这一篇讲的是"组装好"之前与之后的全部工作：

- **system prompt 由什么组成**：persona、项目契约、安全规则、工具指引、执行计划说明、沙箱说明、skill 目录、环境、长期记忆——谁来拼、按什么顺序、多久重读一次；
- **还放得下吗**：一次模型调用前，对话 + 工具定义占了多少 token，离上限还有多远；
- **放不下怎么办**：分档压缩（细节见 [progressive-compactor.md](progressive-compactor.md)）；
- **会话跨轮、跨进程延续**：历史与压缩状态存在哪里，下一轮如何接上。

多组学场景让这几件事更尖锐：一次 `bash` 跑 `skills/spatial/spatial-preprocess/spatial_preprocess.py` 可能打印数千行 QC 表；中文文本按字节或按码点估 token 差 2–3 倍；96 个 skill 的目录本身就要约 8.5k token。

### 1.2 设计目标

| 目标 | 实现机制 |
|------|---------|
| **一条 system 消息** | `PromptAssembler` 把所有段以 `"\n\n"` 连接成一条，永远在下标 0 |
| **写了就能看见** | 每个段的来源都是 callable，每次渲染重新调用（`OMICSCLAW.md` 改动、`memory_write`、日期跨天都在下一次渲染可见） |
| **中文不低估** | token 估算 = ASCII 字符 ÷ 4 向上取整 + 每个非 ASCII 字符 1 token |
| **预算按"可用空间"算** | `usable = 窗口 − 输出预留 − 工具定义预留 − 窗口 × safety_ratio`，五档压力都以它为分母 |
| **组装与压缩可独立测试** | `omicsclaw/context/` 是叶子包：只依赖 `omicsclaw.schema` 与标准库，没有 I/O、没有 session |
| **会话可恢复** | `<workspace>/.omicsclaw/memory.db`（SQLite, WAL），历史与 `CompactionState` 一起保存 |
| **用户可见** | 每次模型调用前发 `CONTEXT` 事件（估算量、压力档位、比值），压缩发 `COMPACTION` 事件 |

---

## 2. 整体架构

```
┌──────────────────────────────── entry/（组合根） ─────────────────────────────────┐
│                                                                                  │
│  build_app()  (entry/assembly.py)                                                │
│    default_sections(config) ──► build_prompt() ──► PromptAssembler  (app.prompt)  │
│    build_budget(model, tools_snapshot) ─────────► ContextBudget     (app.budget)  │
│    build_summarizer(provider, config) ──────────► _ProviderSummarizer             │
│    open_memory(config) ─────────────────────────► MemoryBinding (memory.db)       │
│                                                                                  │
│  attach_sessions(app) (entry/session.py)                                         │
│    SessionRegistry ── SessionStore = SqliteSessionStore | InMemorySessionStore    │
│                                                                                  │
│  TurnRunner._sequence() (entry/turn.py)  —— 每个 exchange 一次                    │
│    _assemble(): _Carried(history) + build_compactor() + build_injector()          │
│    app.engine.exchange_stream(user_text, conversation=, prompt=app.prompt,        │
│                               compactor=, augmentor=)                             │
└───────────────┬──────────────────────────────────────────────────────────────────┘
                │
                ▼
┌──────────────────────────── engine/loop.py ──────────────────────────────────────┐
│  _opening(): [Message.system(prompt.render().system_prompt), *history, user]      │
│  _kernel() 每个 Turn：                                                            │
│    tools = registry.available_tools()                                             │
│    rewrite = await compactor.compact(history, tools)   ← HistoryCompactor         │
│      └─ ProgressiveCompactor: measure() → on_measure(CONTEXT) → 分档压缩           │
│    extra   = await augmentor.augment(sent, tools)      ← 执行计划块，只进本次调用   │
│    completion = provider.generate(sent, tools)                                    │
│  _settle(): 按角色剔除 system 消息后 conversation.commit(trajectory)               │
└───────────────┬──────────────────────────────────────────────────────────────────┘
                │
                ▼
┌──────────────────────────── context/（叶子包） ───────────────────────────────────┐
│  sections.py  Section / static / text_from_file                                   │
│  prompt.py    PromptAssembler / AssembledPrompt / assemble                        │
│  tokens.py    estimate_* / TokenCounter / format_token_count                      │
│  budget.py    ContextBudget / Pressure / measure / BudgetReport                   │
│  transcript.py repair_tool_pairs / split_head_tail / fit_to_budget / emergency_fit│
│  offload.py / summary.py / compaction.py / progressive.py   —— 压缩（另篇）        │
└──────────────────────────────────────────────────────────────────────────────────┘
                │ 结构化满足的 Protocol（SessionStore / OffloadStore / MemoryExtractor）
                ▼
┌──────────────────────────── memory/ ─────────────────────────────────────────────┐
│  Database（一个连接 + 锁）  SqliteSessionStore  FileOffloadStore  JsonlCompactionLog│
│  <workspace>/.omicsclaw/memory.db   tool_results/   compaction_records/          │
└──────────────────────────────────────────────────────────────────────────────────┘
```

依赖方向是单向的：`context` 只 import `schema`；`memory` import `context`（为了 `CompactionState`、`Anchors`、`CompactionRecord` 这些值类型），不 import `entry`；`entry` 知道所有人。`tests/context/test_context_is_a_leaf_layer.py` 在子进程里跑这一层，检查实际被加载的模块，而不是看源码里写了什么。

---

## 3. 组件一览

| 组件 | 代码位置 | 职责 |
|------|---------|------|
| `Section` / `SectionSource` | `omicsclaw/context/sections.py` | 一段 system prompt：`key`、`heading`、`source`（`Callable[[], str]`）、`enabled` |
| `static` / `text_from_file` | `omicsclaw/context/sections.py` | 两个现成 source；后者每次渲染重读文件，文件不存在返回 `""` |
| `PromptAssembler` | `omicsclaw/context/prompt.py` | 有序段列表，不可变；`with_section` / `without` / `render` |
| `AssembledPrompt` | `omicsclaw/context/prompt.py` | 一次渲染的结果：`system_prompt`、`section_stats`、`total_estimated_tokens` |
| `assemble()` | `omicsclaw/context/prompt.py` | `[system, *history, user?]`，恰好添加一条 system |
| `estimate_*` / `TokenCounter` | `omicsclaw/context/tokens.py` | token 估算规则与精确分词器注入口 |
| `ContextBudget` / `Pressure` / `measure()` | `omicsclaw/context/budget.py` | 可用空间、五档压力、调用前预检 |
| `repair_tool_pairs` 等 | `omicsclaw/context/transcript.py` | 纯函数：工具对修复、头尾切分、按预算裁剪、紧急截断、摘要输入渲染 |
| `get_model_limits()` | `omicsclaw/provider/_model_limits.py` | 模型 → `ModelLimits(context_tokens, output_tokens)` |
| `default_sections` / `build_prompt` / `build_budget` / `build_summarizer` | `omicsclaw/entry/assembly.py` | 组合根：决定有哪些段、按什么顺序、预算与摘要模型 |
| `compose` / `prepare` / `TurnRunner` / `_Carried` | `omicsclaw/entry/turn.py` | 一个 exchange 的装配与收尾 |
| `build_compactor` | `omicsclaw/entry/compaction.py` | 把 `ProgressiveCompactor` 接到本部署的预算、摘要器、文件存储 |
| `Session` / `SessionStore` / `SessionRegistry` / `InMemorySessionStore` | `omicsclaw/entry/session.py` | 会话对象、存储协议、每会话串行车道 |
| `Database` / `SqliteSessionStore` / `StoredSession` | `omicsclaw/memory/database.py`、`sessions.py`、`record.py` | SQLite 连接、schema、会话读写 |
| `open_memory` / `session_store` / `memory_section` | `omicsclaw/entry/memory.py` | 打开 `memory.db`，派生会话存储与长期记忆段 |

---

## 4. System prompt 组装

### 4.1 Section 与 PromptAssembler

```python
@dataclass(frozen=True, slots=True)
class Section:
    key: str                  # 稳定标识，用于 without() 与诊断，不渲染
    heading: str              # 渲染在正文上方，空行分隔；"" 表示无标题（如 persona）
    source: SectionSource     # Callable[[], str]，每次 render() 都调用
    enabled: bool = True
```

`PromptAssembler.render()` 的三条规则：

1. **source 返回 `""` 时整段消失，连标题一起。** 一个挂着空 `## Long-term memory` 标题的 prompt 会让模型以为"这一段存在但是空的"。
2. **正文原样放置**：不截断、不重排、不缩进。
3. **每次渲染都重新调用 source**，异常不捕获、直接上抛——提示文件读失败悄悄变成"少了那一段"比崩溃更贵，因为没人会发现。"文件不存在"不算失败（`text_from_file` 对 `FileNotFoundError` 返回 `""`），其他错误（无权限、解码失败、是目录）都会中断渲染。

渲染结果是**一条** system 消息，各段以 `"\n\n"` 连接。只产出一条的原因写在 `prompt.py` 模块文档里：Anthropic 适配器会把多条 system 合并，OpenAI 适配器逐条透传，多条 system 在两个后端上会是两个不同的 prompt；同时 `apply_cache_breakpoints` 标记的是**最后一条** system 消息，只有一条时缓存断点不会因为谁多加了一段而漂移。

**顺序就是加入顺序。** 没有 `order` 字段，也不排序；组合根必须按想要的顺序 `with_section`。`AssembledPrompt.section_stats` 返回每段的 `(key, estimated_tokens)`，是回答"哪一段在吃窗口"的唯一途径（它随 `TurnOutcome.prompt` 返回给调用方）。

`assemble(prompt, history, user_text)` 只添加东西不修改东西：恰好一条 system 放在下标 0；`user_text` 为空时不追加 user 轮（历史可能已以 user 结尾）；非空时追加一条内容逐字节等于 `user_text` 的 user 消息，不加任何前缀。它不检查 `history` 里有没有 system——所以调用方传回压缩结果时必须先去掉被 pin 住的那条（`smaller[1:]`），否则会出现两条 system。

> 实际的 exchange 路径里，system 消息是由 `engine/loop.py` 的 `_opening()` 拼的（同样的"一条、下标 0、空 user 不追加"规则），`context.assemble` 用在 `entry/turn.py` 的 `compose()`——`prepare()` 预览与 `/compact` 的只压缩路径走它。

### 4.2 默认段序

`entry/assembly.py:default_sections()` 决定默认 prompt 由哪些段组成、以什么顺序出现：

| # | key | heading | source | 何时存在 |
|---|-----|---------|--------|---------|
| 1 | `contract` | （无；文件自带 `# OmicsClaw`） | `text_from_file(<repo_root>/OMICSCLAW.md)` | 文件存在且非空 |
| 2 | `safety` | `## Safety rules` | `static(SAFETY_RULES)` | 总是 |
| 3 | `tools` | `## Tool guidance` | `static(TOOL_GUIDANCE)` | 总是 |
| 4 | `planning` | `PLANNING_SECTION_HEADING` | `static(PLANNING_GUIDANCE)` | `planning=true` 且 `plan_write` 实际挂载 |
| 5 | 沙箱段 | 由 `sandbox_section()` 决定 | — | 配置了沙箱（运行中或请求了但未运行） |
| 6 | `skills` | `## Available skills` | `SkillIndex.prompt_body(compact=...)` | `skills_index` 不是 `off` 且索引非空 |
| 7 | `environment` | `## Environment` | 工作区路径、平台、`date.today()` | 总是 |
| 8 | `memory` | `## Long-term memory` | `Precis.read()`（`.omicsclaw/MEMORY.md`） | `memory=true` 且已有记忆条目 |

排序原则：静态文本在前，易变的放后面——最后一段被改动时让缓存前缀失效得最少。长期记忆段排在环境段之后，因为 `memory_write` 会在会话中途改写它，而环境段只在跨天时变化。环境段写的是**日期而不是时间戳**：时间戳会让每一轮的缓存前缀都失效。

### 4.3 项目指令如何注入

以代码为准，默认注入的指令文件只有一个：

- **`OMICSCLAW.md`** —— 运行时契约，`CONTRACT_FILE`，段 key 为 `contract`，无标题（文件自带 `# OmicsClaw`）。

它从 skill 树旁读取：路径是 `AppConfig.repo_root() / "OMICSCLAW.md"`，而 `repo_root()` 等于 `skills_root().parent`。未设 `skills_dir` 时它就是 workspace；设了 `OMICSCLAW_SKILLS_DIR=<仓库>/skills` 时是仓库根，在数据目录里启动也能拿到仓库的契约。workspace 里的同名文件只在 workspace 就是 `repo_root()` 时被读到；`SOUL.md`、`CLAUDE.md` 不再读取。每次渲染重读，所以会话中途 `edit_file` 改了 `OMICSCLAW.md`，下一个 exchange 就能看到。

**`AGENTS.md`、`CLAUDE.md` 默认不注入**（它们是给开发者代理的仓库说明，不是运行中 agent 的指令）。

`--system-prompt-file`（可重复，环境变量 `OMICSCLAW_SYSTEM_PROMPT_FILES`）**替换**契约：每个文件成为一段，key 为 `prompt:<文件名>`、无标题；后面的安全规则、工具指引、环境段不受影响、不能关闭。命名带 `system` 是为了和 CLI 的 `--prompt-file`（用户消息）区分——两者在 `--` 两侧，但名字能互相够到就是 task brief 被当成 persona 的开始。

**安全规则只有一份**，是 `assembly.py` 里的常量 `SAFETY_RULES`（四条，含免责声明原文），契约文件不重复它。常量不会因为某个文件缺失或标题改名而从 prompt 里消失；它的代价是漂移，由 `tests/entry/test_assembly.py` 断言 skill 报告实际写入的 `skills._sdk.report.DISCLAIMER` 仍在 `SAFETY_RULES` 中来兜住，`tests/entry/test_runtime_contract.py` 另断言真实契约渲染后免责声明只出现一次。

### 4.4 Skills 索引段：full / compact / off

`AppConfig.skills_index`（`--skills-index` / `OMICSCLAW_SKILLS_INDEX`，默认 `full`）一个开关同时决定 prompt 段和 `use_skill` 工具：

| 取值 | prompt 中的内容 | `use_skill` | 体量（`SkillsIndex` 文档所记） |
|------|---------------|-------------|------|
| `full` | 一句引导 + 每个 skill 一行 `name: description`（`SkillIndex.summary()`） | 挂载 | 约 8.5k token（96 个 skill） |
| `compact` | 一句引导 + 每个领域一行、只列名字（`SkillIndex.domain_summary()`） | 挂载 | 约 600 token |
| `off` | 无 skills 段 | **不挂载** | 0 |

引导句固定为 "Load a skill's full instructions with the `use_skill` tool when you need them."。`off` 同时卸载工具的理由：给模型一个工具却不给它目录，比两者都没有更糟。

目录来自 `build_skill_index()` 在 `build_app` 时的**一次扫描**，prompt 段与 `use_skill` 共享同一个 `SkillIndex` 对象（模型看到的目录与它能加载的目录一致）。段的正文每次渲染都从这个快照生成，因此会话中途新写的 `SKILL.md` 要到下一次扫描才出现；`use_skill` 读取正文时则每次都重读磁盘，已索引 skill 的内容改动立即可见。扫描时被跳过的文件（缺 `name`/`description` 等）会记一条 warning。

### 4.5 "每次重读"的代价：缓存前缀

每个段都是 closure、每次渲染都重新调用，这是"写了就能看见"的来源，也是 prompt 缓存失效的来源。易变块（skill 目录、长期记忆、执行计划说明、沙箱状态）都在 system prompt 里，任何一个变化都会让缓存前缀整体失效。这是 2026-09-18 的 owner 裁定（取消旧层"稳定段进 system、易变段挂在 user 轮"的双 placement），`prompt.py` 模块文档明确写着："看到缓存命中率低，先读这一段再动手"。工具定义那一半前缀不受影响：`AgentApp.tools_snapshot` 在 `build_app` 时取一次，字节稳定。

---

## 5. Token 估算与模型感知

### 5.1 估算规则（`context/tokens.py`）

```
tokens(text) = ceil(ascii_chars / 4) + non_ascii_chars
```

Python 的 `len` 数的是码点，直接用 `len(content) / 4` 会把中文低估 2–3 倍，而低估是危险方向（以为放得下，结果被 API 截断或拒绝）。所以规则是：ASCII 部分四字符一个 token，非 ASCII 每个字符算一个 token（偏悲观，但偏高是唯一安全的误差方向）。实测：`estimate_text_tokens("hello") == 2`。

每条消息计入：`content`、`reasoning_content`、`tool_call_id`、`name`，以及每个工具调用的 `id`、`name`、原始 `arguments`；每个字段**单独**向上取整。计入 `reasoning_content` 是因为 thinking 端点会拒绝丢了 `reasoning_content` 的历史，这个字段恰恰是本仓库特意保留的。

工具定义（`estimate_tool_tokens`）计入 `name`、`description` 与 `input_schema` 的 JSON（`sort_keys=True`、紧凑分隔符、`ensure_ascii=False`），保证同一个 schema 无论怎么构造都估出同一个数。

`TokenCounter` Protocol（`count_text(text) -> int`）是接入精确分词器的唯一接缝；所有 `estimate_*`、`measure`、`compact` 都有 `counter=` 参数。本包从不主动 import `tiktoken`，装了也不会改变行为。

`format_token_count(n)`：`500 → "500"`，`45200 → "45.2K"`，`1200000 → "1.2M"`。

### 5.2 模型窗口表（`provider/_model_limits.py`）

```python
@dataclass(frozen=True, slots=True)
class ModelLimits:
    context_tokens: int
    output_tokens: int = 8_192        # 8192 表示"未知"，不是"已知是 8192"

DEFAULT_MODEL_LIMITS = ModelLimits(context_tokens=256_000, output_tokens=8_192)
def get_model_limits(model: str) -> ModelLimits
```

查找规则：先按完整标识（小写）精确匹配，再剥掉最后一个 `/` 之前的网关前缀（`"openai/gpt-4o"` → `"gpt-4o"`）匹配，都不中返回 `DEFAULT_MODEL_LIMITS`。Ollama 的 `:tag` 后缀保留。表是手工维护的静态表（"Last reviewed 2026-09"），覆盖 Claude 4.x/3.x、GPT-5.x/4.x/o 系列、DeepSeek、Gemini、Qwen、Kimi、GLM、MiniMax、Doubao、NVIDIA NIM 与若干 Ollama 本地标签，例如：

| 模型 | context | output |
|------|--------:|-------:|
| `claude-sonnet-4-6` | 1,000,000 | 64,000 |
| `claude-haiku-4-5` | 200,000 | 8,192 |
| `gpt-4o` | 128,000 | 16,384 |
| `deepseek-chat` | 1,000,000 | 8,192（未知） |
| `qwen3-max` | 262,144 | 8,192（未知） |
| 表外模型 | 256,000 | 8,192 |

`build_budget()` 使用的是 provider **实际会调用**的模型（`resolve_config(config.provider, config.model).model`），而不是配置里写的：只设 `LLM_PROVIDER=deepseek` 时 `config.model` 为空、跑的是 preset 的默认模型，按 `""` 做预算会落到默认窗口。模型名确实为空时记一条 warning。

### 5.3 实际用量

`context/` 只做估算。provider 返回的实际用量走另一条路：引擎每个 Turn 结束发 `TURN_END`，`TextRenderer` 渲染为 `Turn N done, tokens: <in> in / <out> out`（后端没报则明确写"未报告"），CLI 的 `/usage` 累加这些值。实际用量**不回灌**到预算或压缩决策里——压缩只看估算。

---

## 6. 预算与压力（`context/budget.py`）

### 6.1 可用空间是减法，不是百分比

```
usable_tokens = context_tokens
              - reserve_output_tokens        # ModelLimits.output_tokens
              - reserve_tool_tokens          # estimate_tool_tokens(tools)
              - int(context_tokens * safety_ratio)   # 默认 0.10
```

`ContextBudget` 的两个预留**没有默认值**，忘了传就是构造时的 `TypeError`：默认 0 会让预算凭空大出 20–30K token 而下游无从察觉。`__post_init__` 还会拒绝：`context_tokens <= 0`（不知道窗口的调用方应持有 `ContextBudget | None`）、负的预留或 `safety_ratio`、乱序的档位阈值、负的 `warn_at`。反过来，`usable_tokens <= 0` 是合法状态，`ratio()` 返回 `inf`，直接落在 EMERGENCY。

以 `claude-sonnet-4-6`、工具定义约 20K 为例：`1,000,000 − 64,000 − 20,000 − 100,000 = 816,000` 可用。

### 6.2 五档压力

```python
class Pressure(StrEnum):
    NONE = "none"; WARN = "warn"; SOFT = "soft"; FULL = "full"; EMERGENCY = "emergency"
```

| 档位 | 默认阈值（`ratio = used / usable`） | 压缩动作（见另篇） |
|------|------|------|
| `NONE` | < 0.60 | 原样 |
| `WARN` | ≥ `warn_at` 0.60 | offload 大工具结果 |
| `SOFT` | ≥ `soft_at` 0.70 | 摘要 head 较旧的一半 |
| `FULL` | ≥ `full_at` 0.80 | 摘要整个 head |
| `EMERGENCY` | ≥ `emergency_at` 0.95 | 不调模型，贪心截断 |

边界值归上一档。**`Pressure` 是 `StrEnum`，`>=` 比的是字符串**（`Pressure.EMERGENCY >= Pressure.FULL` 为 `False`），比较档位必须用 `PRESSURE_ORDER` / `at_least(measured, threshold)`。四个阈值是经验值，未在本仓库负载上标定过。

### 6.3 调用前预检：`measure()`

```python
def measure(messages, tools, budget, *, counter=None) -> BudgetReport
```

工具成本有两个来源：`budget.reserve_tool_tokens`（声明）与本次调用的 `tools`（实测）。`measure` 取两者较大者重算预算，差额作为 `BudgetReport.tool_reserve_shortfall` 暴露——这是调用方发现自己报低了的唯一途径。返回的 `report.budget` 是收紧后的那一份，下游必须用它而不是 `app.budget`。`TurnRunner._on_measure` 在一个 exchange 里第一次看到非零 shortfall 时记一条 warning。

`BudgetReport` 字段：`budget`、`message_tokens`、`tool_tokens`、`tool_reserve_shortfall`、`pressure`、`ratio`。

---

## 7. 纯变换：`context/transcript.py`

所有函数都是 `(messages, …) -> tuple[Message, ...]`，无时钟、无 I/O、无模型；返回值永远是新 tuple，不是调用方列表的切片。**不截断任何单条消息**：容量问题只以整条消息为粒度解决，`ToolCall.arguments` 永远是模型原样输出的 JSON 文本。

| 函数 | 作用 |
|------|------|
| `repair_tool_pairs(messages, *, placeholder=MISSING_TOOL_RESULT)` | 双向修复：丢弃找不到调用的 tool 结果；为没有结果的调用在其后插入 `Role.TOOL` 占位消息 |
| `split_head_tail(messages, *, pinned, min_tail)` | 切成 `(pinned, head, tail)`；pin 之后的消息不超过 `min_tail` 条时 head 为空 |
| `fit_to_budget(messages, budget, *, pinned=0, min_tail, target_tokens=None)` | 从 head 最旧处逐条剥离直到放得下，然后修复工具对 |
| `emergency_fit(messages, budget, *, pinned=0)` | 无条件保留 pin 之后第一条（任务消息），其余从新到旧贪心装入，装不下的跳过而非截短 |
| `render_for_summary(messages)` | 把消息拍平成给摘要模型看的纯文本：`[tool_result <id>]: …` / `[<role>]: …` / `[tool_call <name>(<id>)]: <arguments>` |

`repair_tool_pairs` 的配对判据是**相邻**而不是"列表里某处存在"：Anthropic 要求一个 assistant 轮的每个 `tool_use` 都在**紧接着的** user 轮里有 `tool_result`。并行调用 `c0`、`c1` 中 `c1` 的结果被压缩摘要隔开时，成员判定会放行、API 返回 400；这里只承认紧跟在 assistant 后面那段连续的 `Role.TOOL` 消息。判断"是不是工具结果"用的是 `role == Role.TOOL`（与 Anthropic 适配器相同），占位消息也是真正的 `Role.TOOL` 消息，`is_error=False`（没有失败，标成错误会让模型重试一个已经成功的调用）。比较用 `==` 而不是 `is`：从 session 行反序列化出来的角色可能是普通 `str`。

**没有人猜下标 0 是 system prompt。** 本项目的引擎不注入 system，假定 `msgs[0]` 是 system 会让压缩器对另一种组装方式静默失效。所以由调用方用 `pinned` 说明前面有几条受保护——entry 层固定传 `PINNED_SYSTEM_MESSAGES = 1`。

---

## 8. Entry 层如何接起来

### 8.1 启动时（`build_app`）

```
resolve_app_config(argv, env)  → AppConfig
open_app(config) → build_app(config)
   ├─ build_skill_index(config)                   一次扫描
   ├─ open_memory(config)                         打开 .omicsclaw/memory.db（memory=true 时）
   ├─ foundation_tools(...) → hooks → permission gate → build_registry → [task]
   ├─ snapshot = registry.available_tools()       工具定义快照（字节稳定）
   ├─ default_sections(config, skills=, sandbox=, plan_tool=, memory=)
   ├─ app_prompt = build_prompt(sections)         返回 PromptAssembler（不是一次渲染）
   ├─ budget     = build_budget(model, snapshot)  ContextBudget(窗口, 输出预留, 工具预留)
   ├─ summarizer = build_summarizer(provider, config)
   └─ AgentEngine(provider, registry, config.engine_config(), prompt=app_prompt)
attach_sessions(app)                               SessionRegistry + SessionStore
```

`AgentApp.prompt` 存的是**组装器**，不是渲染结果——只有组装器有 `render()`，存一个 `AssembledPrompt` 会编译通过、能运行，然后悄悄不再读取改动后的 `OMICSCLAW.md` 和新的日期。

`build_summarizer` 把 provider 包成 `_ProviderSummarizer`：`summary_model` 非空时通过 `provider.bind(model=...)` 绑定第二个（通常更便宜的）模型；调用时 `tools=None`（摘要器不能调用工具）；超时 `summary_timeout_s`（默认 90 s）包在摘要器内部，超时返回 `""` 让压缩走降级而不是抛出。

### 8.2 每个 exchange（`TurnRunner._sequence`）

```
SessionRegistry._attempt(handle)
  session = await _session(id)                     内存缓存 → store.load() → 新建
  TurnRunner(app, history=session.history, compaction=session.compaction, ...)
     _assemble():
        _Carried(history)                           Conversation 协议（messages / commit）
        build_compactor(app, session_id, state=compaction, on_measure, on_compact)
        build_injector(app, session_id)             执行计划块（TurnAugmentor）
     app.engine.exchange_stream(user_text, conversation=, prompt=app.prompt,
                                compactor=, augmentor=)
        _opening: [system(render), *history, user]
        每个 Turn：compactor.compact → augmentor.augment → 模型 → 工具
        _settle: 去掉 system 消息 → _Carried.commit(trajectory)
     _outcome → TurnOutcome(history=无 system 的轨迹, prompt=本轮渲染,
                            state=compactor.state, compaction=last_record, compactions=records)
  if converged: session.history = outcome.history; session.compaction = outcome.state
  session.updated_at = time.time(); await store.save(session)
```

几个要点：

- **prompt 在 exchange 开始时渲染一次**（引擎的 `exchange` 里），一次 exchange 内的多个 Turn 共用这份渲染；`TurnOutcome.prompt` 就是这份，不会再读一遍 `OMICSCLAW.md`。
- **压缩在每次模型调用前**，由引擎通过 `HistoryCompactor` 协议调用；返回 `(messages, keep)`，`keep` 为真时替换运行中的 history（写回）。详见另篇。
- **执行计划块在压缩之后、只加到本次发送的副本上**（`TurnAugmentor`），不写入 history：先加后压会被压缩掉，写进 history 会每轮累积一份。
- **历史里不存 system 消息**：`_settle` 按角色剔除，`SqliteSessionStore.save` 也会再过滤一遍。
- **exchange 是原子的**：只有 `converged` 的 exchange 才替换 `history` 与 `compaction`；取消或失败的 exchange 保持会话原样（仍会保存一次以更新 `updated_at`）。保存由 registry 在回收 Task **之后**进行，避免 `finally: await save()` 在被取消的 Task 里执行不完。
- `compose()` / `prepare()`：`prepare` 组装一次对话并按第一次模型调用的方式压缩，用于预览（会写 offload 文件与压缩日志，但不附加计划块）。

---

## 9. 会话存储

### 9.1 两层对象

| 对象 | 位置 | 说明 |
|------|------|------|
| `Session` | `entry/session.py` | 可变：`session_id`、`history`（无 system）、`compaction: CompactionState`、`created_at`、`values`（给工具的会话级事实）、`updated_at` |
| `SessionStore` Protocol | `entry/session.py` | `async load / save / list(limit=50)`，全部 async |
| `InMemorySessionStore` | `entry/session.py` | 退出即丢；`save` 故意 `await asyncio.sleep(0)` 一次 |
| `StoredSession` | `memory/record.py` | 与 `Session` 字段一一对应，store 返回它即结构化满足协议 |
| `SqliteSessionStore` | `memory/sessions.py` | SQLite 实现，另有 `delete(session_id)` |
| `SessionRegistry` | `entry/session.py` | 会话缓存（LRU，上限 `max_sessions` 默认 256，只驱逐空闲会话）、每会话一条串行车道 |

`attach_sessions(app, store=None)` 里 `store=None` 的意思是"用这个 app 自己的"：`memory=true`（默认）时是建在 `memory.db` 上的 `SqliteSessionStore`，`memory=false` 或手工组装的 app 退回 `InMemorySessionStore`。**一个会话要存两样东西**：`history` 和 `CompactionState`（上一份摘要与锚点）。丢了后者不致命但不便宜——下一次压缩从 `FIRST_TEMPLATE` 重新开始，为已经摘要过的内容再付一次钱。

### 9.2 `memory.db` schema

路径：`<workspace>/.omicsclaw/memory.db`（`MEMORY_DB_FILENAME`，每个工作区一个文件）。`Database` 打开时执行 `PRAGMA foreign_keys = ON`、尝试 `PRAGMA journal_mode = WAL`（另一进程同时打开导致切换失败时忽略——模式是文件的属性），busy timeout `BUSY_TIMEOUT_S = 15.0`，一个连接 + 一把线程锁，async 调用经 `asyncio.to_thread`。

```sql
CREATE TABLE IF NOT EXISTS sessions (
    session_id  TEXT PRIMARY KEY,
    created_at  REAL NOT NULL,
    updated_at  REAL NOT NULL,
    summary     TEXT NOT NULL DEFAULT '',     -- CompactionState.summary
    anchors     TEXT NOT NULL DEFAULT '',     -- CompactionState.anchors 的 JSON；全空时存 ''
    values_json TEXT NOT NULL DEFAULT ''      -- Session.values 的 JSON
);

CREATE TABLE IF NOT EXISTS messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT NOT NULL,
    position    INTEGER NOT NULL,             -- 会话内顺序
    role        TEXT NOT NULL,
    content     TEXT NOT NULL DEFAULT '',
    reasoning   TEXT NOT NULL DEFAULT '',     -- Message.reasoning_content
    tool_calls  TEXT NOT NULL DEFAULT '',     -- [{"id","name","arguments"}] 的 JSON；无调用时 ''
    tool_call_id TEXT NOT NULL DEFAULT '',
    name        TEXT NOT NULL DEFAULT '',
    is_error    INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (session_id) REFERENCES sessions (session_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages (session_id, position);
```

同一个文件里还有长期记忆的 `long_term_memories` 表与 `memories_fts`（FTS5）虚表，见长期记忆文档；本篇只关心上面两张表。

### 9.3 读写语义

- **`save`**：一个事务内 `INSERT … ON CONFLICT (session_id) DO UPDATE` 更新会话行（`created_at` 不覆盖），然后 `DELETE FROM messages WHERE session_id = ?` 再按 `position` 批量插入整段历史——**全量替换**，不是追加。这与写回式压缩天然契合：压缩写回后的历史整体取代旧历史。`role` 为 system 的消息被丢弃。`values` 必须能被 JSON 编码，否则 `TypeError` 且什么都不写。
- **`load`**：按 `position ASC` 读回消息，`tool_calls` 反序列化为 `ToolCall`（`arguments` 保持原始字符串），`anchors` 反序列化为 `Anchors`（缺失字段为 `""`，`Anchors.merge` 把 `""` 与 `"N/A"` 同样视为"没有新信息"，不会覆盖旧锚点）。
- **`list(limit)`**：`ORDER BY updated_at DESC, created_at DESC`，供 CLI `/sessions`、`/resume` 使用。**范围就是这个数据库文件**，表里没有 owner/scope 列，查询没有 `WHERE`。
- **`delete`**：删消息与会话行。

---

## 10. 可观测性

| 事件 / 输出 | 来源 | 内容 |
|------|------|------|
| `TurnEventType.CONTEXT` | `ProgressiveCompactor` 的 `on_measure` → `TurnRunner._on_measure` | 每次模型调用前一条，携带 `BudgetReport`；先于该调用的其他事件，也先于同一调用的 `COMPACTION` |
| `TurnEventType.COMPACTION` | `on_compact` → `TurnRunner._on_compacted` | 仅当压缩改动了对话或失败时，携带 `CompactionRecord` |
| `TextRenderer` 文本行 | `entry/render.py:_context_line` | `Context: <消息+工具> tokens of <窗口>, pressure warn (65%)`，有 shortfall 时追加 `tool reserve short by N`；CLI REPL 逐条打印 |
| 线格式 | `entry/render.py:_context_payload`（`to_wire`） | `context_tokens`、`message_tokens`、`tool_tokens`、`tool_reserve_shortfall`、`pressure`、`ratio` |
| `TURN_END` | 引擎 | 实际 usage（见 5.3） |

各 surface 的取舍：CLI 把 `CONTEXT` 与 `COMPACTION` 都打印成暗色行；Channel 的 `DEFAULT_DELIVERED_TYPES`（`entry/channel/runtime.py`）**不含**这两类——IM 平台对发送限流，每次调用一条消息不可接受；Desktop 的 `turn_observation.py` 只把 `COMPACTION` 转成 `kind="compaction"` 的 `status` 帧，`CONTEXT` 不下发。

注意 `CONTEXT` 报告的是**触发压缩的那次测量**（压缩前的量）；压缩之后实际发送的量在 `COMPACTION` 帧的 `tokens_after` 里。比值的分母是 `usable_tokens`，而文本行里 "of N" 显示的是整个窗口 `context_tokens`。

---

## 11. 配置参数

| 配置键（`AppConfig`） | CLI 标志 | 环境变量 | 默认 | 作用 |
|------|------|------|------|------|
| `workspace` | `--workspace` | `OMICSCLAW_WORKSPACE` | — | `skills/`（未设 `skills_dir` 时）/ `.omicsclaw/` 的根 |
| `model` | `--model` | `OMICSCLAW_MODEL`, `LLM_MODEL` | `""` | 预算查表用（经 `resolve_config` 解析为实际模型） |
| `system_prompt_files` | `--system-prompt-file`（可重复） | `OMICSCLAW_SYSTEM_PROMPT_FILES` | `()` | 非空时替换契约 `OMICSCLAW.md` |
| `skills_dir` | `--skills-dir` | `OMICSCLAW_SKILLS_DIR` | `<workspace>/skills` | skill 扫描目录；`OMICSCLAW.md` 从它的上一级读取 |
| `skills_index` | `--skills-index` | `OMICSCLAW_SKILLS_INDEX` | `full` | `full` / `compact` / `off` |
| `planning` | `--planning` | `OMICSCLAW_PLANNING` | `true` | 计划段 + `plan_write` + 计划块注入 |
| `memory` | `--memory` | `OMICSCLAW_MEMORY` | `true` | 打开 `memory.db`：会话持久化、长期记忆段、提取器 |
| `summary_model` | `--summary-model` | `OMICSCLAW_SUMMARY_MODEL` | `""`（沿用主模型） | 压缩摘要模型 |
| `summary_timeout_s` | `--summary-timeout` | `OMICSCLAW_SUMMARY_TIMEOUT_S` | `90.0` | 单次摘要超时 |
| `compact_at` | `--compact-at` | `OMICSCLAW_COMPACT_AT` | `warn` | 触发压缩的最低档位 |
| `max_sessions` | `--max-sessions` | `OMICSCLAW_MAX_SESSIONS` | `256` | 内存中会话上限 |

`ContextBudget` 的 `safety_ratio`（0.10）与四个阈值没有配置入口，`build_budget` 使用默认值。

---

## 12. 已知限制

- **token 估算未标定**（plan 0030 §11.A-8）：本机没有 tokenizer 可对照，任何误差数字都没有测过。
- **图片成本为零**：`Message.content` 是 `str`，多模态内容没有表示；Channel 把照片路由到组织切片分析时，预算每张图约乐观一千 token。`tokens.py` 明确禁止用"看起来像 base64 就加 1300"之类的启发式补丁。
- **档位阈值未标定**（§11.A-7）：0.60/0.70/0.80/0.95 是经验值，未在本仓库负载上标定。
- **输出上限多为"未知"**：`_model_limits.py` 里许多条目的 `output_tokens=8192` 表示未知，真实上限更高时预算按差额偏乐观（FRAMEWORK-REBUILD Debts）。
- **易变段在缓存前缀内**：skill 目录、记忆、计划说明任一变化都使 system 前缀缓存失效（有意为之，见 4.5）。另有一条 Debt：`cache_control` 断点只到了 OpenAI 适配器，原生 Anthropic 不设显式断点就什么都不缓存。
- **skill 目录是启动时快照**：会话中新建的 skill 要重新扫描才出现在 prompt 里。
- **段来源异常会中断渲染**：`OMICSCLAW.md` 存在但不可读时整个 exchange 失败，这是有意选择；需要降级的部署自己包一层 source。
- **会话列表没有隔离**：`SqliteSessionStore.list` 无 scope 列、无 `WHERE`，多人共用一个工作区文件时彼此可见会话。
- **没有删除会话的入口**：`SqliteSessionStore.delete`、`FileOffloadStore.purge`、`JsonlCompactionLog.purge` 都存在，但没有任何调用方。
- **实际 usage 不参与决策**：压缩只看估算，估算错了没有第二次机会（plan 0030 §11.A-14 记录的风险）。
- **没有与真实端点验证过**：摘要模板能否让真实模型产出可解析的锚点，从未验证（§11.A-9）。

---

## 13. 文件索引

| 文件 | 职责 |
|------|------|
| `omicsclaw/context/__init__.py` | 公共 API 与叶子包约定 |
| `omicsclaw/context/sections.py` | `Section`、`SectionSource`、`static`、`text_from_file` |
| `omicsclaw/context/prompt.py` | `PromptAssembler`、`AssembledPrompt`、`assemble` |
| `omicsclaw/context/tokens.py` | token 估算、`TokenCounter`、`format_token_count` |
| `omicsclaw/context/budget.py` | `ContextBudget`、`Pressure`、`PRESSURE_ORDER`、`at_least`、`measure`、`BudgetReport` |
| `omicsclaw/context/transcript.py` | `repair_tool_pairs`、`split_head_tail`、`fit_to_budget`、`emergency_fit`、`render_for_summary` |
| `omicsclaw/provider/_model_limits.py` | `ModelLimits`、`DEFAULT_MODEL_LIMITS`、`get_model_limits` |
| `omicsclaw/engine/loop.py` | `exchange` / `_opening` / `_settle`、每 Turn 调用 compactor 与 augmentor |
| `omicsclaw/engine/compactor.py` | `HistoryCompactor` 协议 |
| `omicsclaw/entry/assembly.py` | `default_sections`、`SAFETY_RULES`、`TOOL_GUIDANCE`、`build_prompt`、`build_budget`、`build_summarizer`、`build_app` |
| `omicsclaw/entry/config.py` | `AppConfig`、`SkillsIndex`、`STATE_DIRNAME`、环境变量表 |
| `omicsclaw/entry/turn.py` | `compose`、`prepare`、`_Carried`、`TurnRunner`、`TurnOutcome` |
| `omicsclaw/entry/compaction.py` | `build_compactor`、`PINNED_SYSTEM_MESSAGES` |
| `omicsclaw/entry/session.py` | `Session`、`SessionStore`、`InMemorySessionStore`、`SessionRegistry`、`attach_sessions` |
| `omicsclaw/entry/memory.py` | `open_memory`、`memory_db_path`、`session_store`、`memory_section` |
| `omicsclaw/entry/events.py` / `render.py` | `CONTEXT` / `COMPACTION` 事件与渲染 |
| `omicsclaw/memory/database.py` | `Database`、`SCHEMA` |
| `omicsclaw/memory/sessions.py` / `record.py` | `SqliteSessionStore`、`StoredSession` |
| `omicsclaw/skills/index.py` | `SkillIndex.prompt_body` |
| `tests/context/` | `test_prompt.py`、`test_sections.py`、`test_tokens.py`、`test_budget.py`、`test_transcript.py`、`test_context_is_a_leaf_layer.py` 等 |
| `tests/entry/test_assembly.py`、`test_turn.py`、`test_session.py`、`test_memory_wiring.py` | 组装、exchange、会话、memory 接线 |
| `tests/memory/test_sessions.py`、`test_database.py` | SQLite 会话存储 |
| `docs/plans/0030-context-assembly-layer.md` | 组装层计划（Step 5） |
| `docs/plans/0031-entry-layer.md`、`0033-memory-layer.md`、`0040-memory-wiring.md` | entry 层、memory 层及其接线 |
