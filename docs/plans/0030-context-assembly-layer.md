# 计划 0030 — 组装层 `omicsclaw/context/`（prompt assembly / budget / compaction）

框架重建第 5 步。前序：0026（provider）、0027（engine）、0028（tool
registry）、0029（foundation tools）。交接文档是
`docs/FRAMEWORK-REBUILD.md`，本计划的所有裁决都应能在它和两侧源码里找到
依据。

---

## 0. 材料来源与可核实性

| 材料 | 位置 | 本计划的用法 |
|---|---|---|
| harness9 `internal/context/` | `builder.go`(190) + `builder_test.go`(177) | **全部读过**。这是它 `context` 包的全部内容 |
| harness9 压缩栈 | `internal/memory/` 的 `compaction.go`(239)、`progressive_compactor.go`(514)、`summarization.go`(254)、`token.go`(58)、`anchor.go`(124)、`compaction_offloader.go`(110)；`internal/engine/` 的 `compact.go`(95)、`history.go`(188)、`loop_phases.go`(320) | **全部读过**。附录 A 的每条 `文件:行号` 均逐行核实 |
| 作者自述设计意图 | `website/blog/context-engineering/index.md`(427)、`progressive-context-compaction/index.md`(184) | 读过，**但不作依据**：它描述的是 issue #117 之前的「纯视图压缩」，与今天的 `history.go:95-153` 写回式压缩**已不一致**。引用一律以代码为准 |
| 旧 OmicsClaw 组装层 | `git show HEAD:omicsclaw/runtime/context/*`（已 staged 删除）。**7 个文件 3,705 行**：`__init__.py`(1)、`assembler.py`(600)、`budget.py`(463)、`compaction.py`(1225)、`layers/__init__.py`(1324)、`layers/output_format.py`(15)、`system_prompt.py`(77)，逐个 `git show HEAD:… \| wc -l` 实测 | §5 能力对照表的输入 |
| 旧组装层的 13 个测试 | 同样 `git show HEAD:tests/...`。**全部已 staged 删除，工作区一个都不剩**。逐个点名见 §0.1 | §5 的裁决依据（一条被测试钉过的行为，丢掉的代价更高） |
| 已交付三层 | 工作区 `omicsclaw/schema/`、`provider/`、`engine/`、`tools/` 的**实际代码** | §7 的接缝裁决只依据代码，不依据前序计划的措辞 |

三条声明，先说在前面：

1. **本机没有 tiktoken，没有网络，装不上任何第三方包。** 因此 §4-Q3 的
   token 估算方案里，凡是「精度」类的说法一律标为**未核实**，由实现者
   在能测的环境里补测，不得在 docstring 里断言未测过的精度。
2. **blog 与代码冲突时以代码为准。** 上表第三行不是客套。
3. **工作区已是半拆状态。** `git status --porcelain` 当前有 320 条
   `D `（含 `omicsclaw/memory/`、`omicsclaw/control/`、
   `omicsclaw/runtime/agent/`、`omicsclaw/runtime/context/` 整包）与若干
   ` M `。这直接改写了验收标准的写法，见 §9-3 与 §10。

### 0.1 「旧组装层的 13 个测试」——逐个点名

上表那一行原先只有数字。数字本身不可核对，而 §5 有多条裁决的强度依赖
「这条行为被测试钉过」，所以把它展开。**口径**：文件名含 `context` 或
`compact` 且确实引用 `omicsclaw.runtime.context.*` 的 staged-deleted 测试
文件（`tests/test_assisted_parameterization_context.py`(76) 名字符合但
零引用，已排除）。

| 文件 | 行数 | 钉住什么 |
|---|---|---|
| `tests/test_context_compaction.py` | 1,242 | 压缩主体：分级递进、摘要闸、边界标记 —— **后两者已随裁定 0 丢弃**（§5.3） |
| `tests/test_context_assembler.py` | 1,078 | 组装：placement 拆分（`:1037`，**已随裁定 0 作废**，见 Q5b 代价表）、字节稳定（`:322`，**仍然保留**，见陷阱 7）、F9 后台任务（`:934`/`:975`） |
| `tests/test_context_budget.py` | 453 | 预算：档位、`effective_context_capacity`、块感知裁剪 |
| `tests/test_query_engine_compaction_callback.py` | 350 | 压缩回调与 `ContextBudgetStatus` 的接线 |
| `tests/test_compact_boundary.py` | 186 | 成对边界标记 + `rfind` 取最外层（CodePilot bug #7）—— **该能力已随裁定 0 丢弃**，改用 harness9 的单前缀（§5.3） |
| `tests/test_server_compaction_event.py` | 171 | `CompactionEvent` → SSE |
| `tests/test_skill_context_gotchas_injection.py` | 168 | skill gotchas 注入（ADR 2026-05-11） |
| `tests/test_compact_slash_command.py` | 167 | `/compact` 的反向边界扫描与逐字带过 |
| `tests/test_context_layer_predicate.py` | 165 | predicate 门控（已被 owner 废） |
| `tests/test_soul_md_compact.py` | 134 | 12 条里只有 `:129-131` 碰本层，其余 11 条是 SOUL.md 自己的契约（§11.B-16） |
| `tests/test_compaction_tool_call_rendering.py` | 125 | 反模仿渲染 —— **该能力已随裁定 0 丢弃**（§5.3、陷阱 20），本条不需要对口 |
| `tests/test_compaction_event.py` | 119 | 压缩事件的 wire payload |
| `tests/test_tool_descriptions_compact.py` | 97 | **不属本层**：测 `runtime/tools/builders/agent.build_bot_tool_specs` |

合计 4,455 行。

> **「13」是上面这个口径的数目，不是本层被测试钉住的全部。** 另有 **14**
> 个 staged-deleted 测试文件在**模块级** import `omicsclaw.runtime.context.*`
> 却不以 `context`/`compact` 命名——`test_predicate_gated_injectors.py`(242)、
> `test_tool_list_predicate.py`(252)、`test_tool_list_snapshots.py`(203)、
> `test_tool_list_lazy_exposure.py`(330)、`test_research_stance_persona.py`(233)、
> `test_output_format.py`(104)、`test_surface_voice_rules.py`(94)、
> `test_role_guardrails_removed.py`(59)、`test_token_budget.py`(39)、
> `test_predicates.py`(415)、`test_query_engine.py`(1774)、
> `test_query_engine_cache_diagnostics.py`(360)、
> `test_query_engine_reasoning_capture.py`(258)、
> `tests/control/test_attachment_lifecycle_contract.py`(572)。
> 复现命令：
> ```bash
> for f in $(git status --porcelain | grep "^D " | awk '{print $2}' | grep "^tests/"); do
>   git show HEAD:$f | grep -qE "^from omicsclaw\.runtime\.context" && echo "$f"
> done
> ```
> 迁移时按这张更宽的表找对口，不要按 13 那张。

---

## 1. 背景与目标

### 1.1 这一层要解决什么

前四步交付的东西合起来能跑一轮 ReAct，但**喂给它的东西是凭空来的**：

```python
engine = AgentEngine(provider, registry, EngineConfig())
result = await engine.run(messages)   # messages 从哪来？
```

`omicsclaw/engine/loop.py:34-38` 把这件事讲得很直白（**工作区的新引擎**，
第 3 步交付，`git status` 里是 `?? omicsclaw/engine/`；本计划凡引
`omicsclaw/engine/loop.py:NN` 一律指它，凡引旧引擎一律写
`git show HEAD:omicsclaw/engine/loop.py:NN`——两者是**不同的文件**，
旧的已 staged 删除）：

> **What this layer is not.** No prompt assembly (step 5), no session
> persistence or compaction (step 6), no tool implementations (step 4).
> The conversation arrives assembled and leaves as a trajectory; history
> belongs to the caller.

「conversation arrives assembled」——**第 5 步就是那个 assemble 的人**。

同样地，`omicsclaw/engine/types.py:217-222` 在 `EngineEvent.usage` 的
docstring 里点名了本层：

> The reference harness emits a second, *pre-call* token event so a TUI
> can show context pressure before the model answers, but that needs a
> token counter this layer does not have and must not grow — **it
> belongs to step 5**.

以及 `omicsclaw/tools/base.py:217-223`，`ToolPolicy.tags`：

> Free-form labels for **the assembly layer** to filter on.

三处已交付代码分别从三个方向指向本层。本层的边界因此不是新发明的，是
**被前三步的公开面反向定义出来的**。

### 1.2 目标

1. 把一次对话的**输入**变成一个可复现的、可预算的、可压缩的
   `Sequence[Message]`。
2. 给出 token 估算与上下文压力模型，让「还剩多少」这个问题在调用 LLM
   **之前**就有答案。
3. 在预算不够时，把历史压成仍然可用的形状——并且**不丢任务目标**。
4. 全程只依赖 `omicsclaw.schema` 与标准库。所有外来知识（AGENTS.md、
   skills 索引、长期记忆、摘要用的 LLM）一律走注入接缝。

> **范围约束（owner，2026-09-18）**：「你当前的目标是集中优化 context
> 即可，其他无关的组件可以暂时放一下，后续等我搭建起完整的 agent 架构
> 之后，再考虑进行相关优化。」
>
> 落到本计划：**本步的目标是把 `omicsclaw/context/` 这一个组件做扎实。**
> 一切跨组件的联动优化（引擎侧的轮内压缩与 nudge/gate、事件类型、
> Surface 命令、旧消费方迁移）**一律延后**——本计划不为它们预留工期，
> 也**不以它们为验收前提**。§11 的债务表按这条约束分成两组（§11.A 属
> context 本体、第 6 步要接的接缝；§11.B 等完整架构就绪后由 owner 决定
> 何时开）。

### 1.3 非目标（明确写出来，免得被当成遗漏）

- **不做 Session、不做持久化、不做写回。** 见 §4-Q1。
- **不改 `omicsclaw/engine/`。** 本层不给引擎加 hook，一行都不加。因此
  **轮内压缩（per-turn compaction）在本步结束时是做不到的**，只能在
  `run()` 之间做。这是本步交付的一个**已知功能缺口**，写在 §11.B-1，不是
  被忘掉的。
- **不做 offload（大输出落盘）。** 那是文件系统 I/O，属第 6 步或工具层。
  本层只提供「一条消息太大」的判定与占位符**渲染**，落盘的人自己接。
- **不做 Surface 门控 / predicate 门控 / 每会话冻结工具列表 / 按阶段裁
  剪子集。** owner 已于 2026-09-18 裁定四项全部废弃
  （`FRAMEWORK-REBUILD.md:714-742`）。本层**不得**把它们复活。
  ⚠️ **那条裁定只覆盖这四项。** 计划 0028 §5 还结转了三项
  （`speculative_classifier` / `result_policy` / `progress_policy`），
  owner 没被问过，本计划也**不替他答**——逐条裁决在 **§5.0**，
  其中 `speculative_classifier` 已由 owner 于 2026-09-18 定向（附录 **C.2** 裁定 1）。
- **不做 `/compact` 斜杠命令、不做事件上报。** 命令属 Surface，事件属
  engine。本层只交付一个可被它们调用的纯函数与一个可序列化的记录对象。
- **不迁移任何既有消费方。** 见 §10。

---

## 2. 范围与非范围（一句话版本）

**做**：token 估算、预算与五档压力、分段组装（**单一 system prompt**，
裁定 0）、消息级压缩变换、锚点解析与合并、压缩审计记录，以及把上述
各项接上外部世界所需的全部 Protocol。

**不做**：Session、持久化、写回、offload 落盘、引擎改动、事件类型、
Surface 命令、多模态转换、Surface/predicate 门控、旧层删除、
旧消费方迁移；以及**随裁定 0 丢弃的整条旧层专有路径**——
system/message 双 placement、确定性模板摘要、6 道拒收闸、
反模仿 XML 渲染、摘要 block 累积、三遍收敛、成对边界标记
（见 §5 与附录 C.2）。

---

## 3. 目标架构

### 3.1 模块清单

```
omicsclaw/context/
├── __init__.py        ~80    公开面（re-export + 一段「这一层是什么」）
├── tokens.py          ~200   token 估算：TokenCounter Protocol + 默认估算器
├── budget.py          ~220   ContextBudget / ContextPressure：窗口、预留、档位
├── sections.py        ~160   Section / SectionSource：分段的词汇表
├── prompt.py          ~240   PromptAssembler：有序分段 → **单一 system prompt**
├── transcript.py      ~300   纯消息变换：工具对修复、head/tail 切分、按预算截断
├── summary.py         ~200   锚点解析/合并、摘要 prompt 模板、边界标记
└── compaction.py      ~340   压缩编排：档位判定、head/tail、CompactionRecord
```

合计 ~1,640 行实现（裁定 0 砍掉整条旧层专有路径后，`sections.py` /
`prompt.py` / `summary.py` 三个模块各缩水约三分之一，见 §5 与附录 C.2）。
测试量级按**已交付层的实测比例**预估 ~2,200–3,700 行：

| 已交付层 | 实现 | 测试 | 比例 |
|---|---|---|---|
| `omicsclaw/engine/` ↔ `tests/engine/` | 1,927 | 4,295 | ≈ 1:2.2 |
| `omicsclaw/tools/` ↔ `tests/tools/` | 8,812 | 11,912 | ≈ 1:1.4 |
| `omicsclaw/provider/` ↔ `tests/provider/` | 2,838 | 3,700 | ≈ 1:1.3 |

> 这三行是 `find <dir> -name '*.py' -not -path '*__pycache__*' | xargs wc -l`
> 实测的。**不要按计划编号归因**：`omicsclaw/tools/` 同时装着第 4 步与
> 第 4.5 步，分不开；交接文档里唯一给过的一组数是 step 2 的
> ~2,800/~3,900（`FRAMEWORK-REBUILD.md:114`），0027/0028/0029 三份计划里
> **没有**可比的交付行数。原稿写的「0027 是 1:2.6，0028 是 1:1.5，0029 是
> 1:1.4」无据，已删。

> `summary.py` 仍然独立成模块，但**理由已经换了**。原稿的理由是
> 「§5.3 判给它的东西有一半来自旧 OmicsClaw 层」（6 道拒收闸、确定性
> 模板、反模仿渲染）——**那三样已随裁定 0 全部丢弃**。现在的理由是
> 纯粹的内聚：锚点（`anchor.go` 的 124 行）与摘要模板
> （`progressive_compactor.go:26-65`）是一组自成体系、可脱离压缩编排
> 单测的纯文本变换，混进 `compaction.py` 只会让那个文件变成第二个
> 1,225 行的旧 `compaction.py`。

> **行数是量级，不是指标。** 第 4.5 步的教训之一是「为凑行数写的
> 防御分支正好是死代码」（`FRAMEWORK-REBUILD.md:441-448` 编号列表第 7 条
> 「Dead code ported from Go」，三条全部由**刚刚被告知要找这类问题的那个
> agent 自己写出来**）。少写是对的。
>
> **引用更正**：本计划原稿把这些教训归给「0029 附录 B」。
> `docs/plans/0029-foundation-tools.md:794` 的附录 B 标题是「该不该把
> harness9 的 sandbox 搬进来（owner 提问，2026-09-18）」——**0029 没有
> 交付后评审附录**。教训在 `FRAMEWORK-REBUILD.md:400-464`。全文只有
> §4-Q2 表里那句「`sandbox/` 若真建，见 0029 附录 B」指的是真正的附录 B。

### 3.2 公开 API 草图

```python
# ---- tokens.py ----------------------------------------------------
@runtime_checkable
class TokenCounter(Protocol):
    def count_text(self, text: str) -> int: ...

def estimate_text_tokens(text: str) -> int: ...
def estimate_message_tokens(message: Message, *,
                            counter: TokenCounter | None = None) -> int: ...
def estimate_messages_tokens(messages: Sequence[Message], *,
                             counter: TokenCounter | None = None) -> int: ...
def estimate_tool_tokens(tools: Sequence[ToolDefinition], *,
                         counter: TokenCounter | None = None) -> int: ...
def format_token_count(n: int) -> str: ...        # 45200 → "45.2K"

# ---- budget.py ----------------------------------------------------
class Pressure(StrEnum):
    NONE = "none"; WARN = "warn"; SOFT = "soft"
    FULL = "full"; EMERGENCY = "emergency"

@dataclass(frozen=True, slots=True)
class ContextBudget:
    context_tokens: int                 # 窗口，由调用方从 get_model_limits 取
    reserve_output_tokens: int          # 给回答留的 —— **无默认值**，见 Q9
    reserve_tool_tokens: int            # 工具 schema 实测值 —— **无默认值**
    safety_ratio: float = ...           # 估算误差余量，见 Q3
    warn_at: float = ...; soft_at: float = ...
    full_at: float = ...; emergency_at: float = ...

    def __post_init__(self) -> None: ...   # context_tokens <= 0 → ValueError（Q9）

    @property
    def usable_tokens(self) -> int: ...
    def pressure(self, used_tokens: int) -> Pressure: ...
    def ratio(self, used_tokens: int) -> float: ...

@dataclass(frozen=True, slots=True)
class BudgetReport:
    budget: ContextBudget
    message_tokens: int
    tool_tokens: int                     # 本次**实测**的工具 schema 开销
    tool_reserve_shortfall: int          # max(0, tool_tokens - reserve_tool_tokens)
    pressure: Pressure
    ratio: float

def measure(messages, tools, budget, *, counter=None) -> BudgetReport: ...
# ⚠️ 接缝：`tool_tokens`（实测）与 `budget.reserve_tool_tokens`（声明）是
# 同一个量的两个来源。`measure` **必须**按
# `max(budget.reserve_tool_tokens, tool_tokens)` 扣减，即两者取更收紧的
# 那个，并把差额暴露成 `tool_reserve_shortfall` 供调用方发现自己报低了。
# 反方向（信任声明值）会让预算比真实可用空间大 20-30K（`token.go:32`）。

# ---- sections.py --------------------------------------------------
SectionSource: TypeAlias = Callable[[], str]      # 每次 assemble 都调用

@dataclass(frozen=True, slots=True)
class Section:
    key: str                  # 稳定标识，用于 without() 与诊断
    heading: str              # "" 表示无标题（基础段）
    source: SectionSource
    enabled: bool = True
# ⚠️ **没有 `placement`，也没有 `order`**（裁定 0，见 Q5b）。
#   - placement：harness9 六段全部进 system prompt（`builder.go:78-189`）。
#   - order：harness9 的顺序就是 `parts = append(parts, ...)` 的加入顺序，
#     没有排序键。丢掉 `order` 的代价是**组装根必须按正确顺序
#     `with_section`，不能靠事后调 `order` 纠正**——写进 `PromptAssembler`
#     的 docstring。收益：字节稳定性不再依赖一个排序函数（陷阱 7）。

@dataclass(frozen=True, slots=True)
class RenderedSection:
    key: str
    content: str
    estimated_tokens: int

def static(text: str) -> SectionSource: ...       # 常量转 source
def text_from_file(path, *, encoding="utf-8") -> SectionSource: ...
                                                  # 本层唯一碰文件的地方，见 Q2

# ---- prompt.py ----------------------------------------------------
@dataclass(frozen=True, slots=True)
class PromptAssembler:
    sections: tuple[Section, ...] = ()

    def with_section(self, section: Section) -> PromptAssembler: ...  # 追加到末尾
    def without(self, key: str) -> PromptAssembler: ...
    def render(self) -> AssembledPrompt: ...

@dataclass(frozen=True, slots=True)
class AssembledPrompt:
    sections: tuple[RenderedSection, ...]         # 加入顺序，空段已剔除
    @property
    def system_prompt(self) -> str: ...           # 全部段以 "\n\n" 连接
    @property
    def section_stats(self) -> tuple[tuple[str, int], ...]: ...   # 诊断用

def assemble(
    prompt: AssembledPrompt,
    history: Sequence[Message],
    user_text: str = "",
) -> tuple[Message, ...]: ...
# → [Message.system(system_prompt), *history, Message.user(user_text)]
#
# 两个边界，各要一条点名测试（见 Task B 验收 8）：
#   1. user_text 为空 → **不追加 user 轮**（history 可能已经以 user 收尾）。
#   2. user_text 非空 → 追加**恰好一条** user 轮，内容**逐字节**就是
#      user_text，不加任何前缀、标题或包装。
#
# ⚠️ **原稿的第 3 种边界（「user_text 空 + message_context 非空」）随
#   裁定 0 消失**：`message_context` 这个概念已经不存在，易变段全部进
#   system prompt。`"## User Request"` 标题也随之丢弃——它存在的唯一理由
#   是把 message_context 与用户这句话分开（§5.4）。

# ---- transcript.py ------------------------------------------------
def repair_tool_pairs(messages: Sequence[Message], *,
                      placeholder: str = ...) -> tuple[Message, ...]: ...
def split_head_tail(messages: Sequence[Message], *,
                    pinned: int, min_tail: int
                    ) -> tuple[tuple[Message, ...], ...]: ...
def fit_to_budget(messages, budget, *, pinned=0, min_tail, counter=None
                  ) -> tuple[Message, ...]: ...          # 逐条剥头
def emergency_fit(messages, budget, *, counter=None
                  ) -> tuple[Message, ...]: ...          # 保任务锚 + 贪心纳入

def render_for_summary(messages: Sequence[Message]) -> str: ...
# **本层唯一的渲染器，家在 transcript.py。**
# 它是 `Summarizer` 的**入参**渲染器：把被省略的消息渲染成喂给摘要 LLM
# 的纯文本。**照 harness9 `progressive_compactor.go:391-404` 逐行 port**：
#   tool 消息          → `[tool_result <id>]: <content>`
#   其余非空 content   → `[<role>]: <content>`
#   每个 tool_call     → `[tool_call <name>(<id>)]: <arguments>`
#   行间 "\n" 连接；**不截断任何一行**（`:391-404` 全程无截断，已核实）
# ⚠️ 裁定 0：旧层的散文形式（`[called tools: a, b]`）与
# `<prior-tool-calls .../>` 反模仿渲染**全部丢弃**——前者被 harness9 的
# 对应物取代，后者所属的「确定性模板摘要」整条路径已不存在。见 §5.3。

# ---- summary.py ---------------------------------------------------
@runtime_checkable
class Summarizer(Protocol):
    async def summarize(self, prompt: str, *, system: str) -> str: ...

@dataclass(frozen=True, slots=True)
class Anchors:                       # 五类锚点，固定顺序
    user_intent: str = "N/A"
    execution_progress: str = "N/A"
    key_decisions: str = "N/A"
    tried_solutions: str = "N/A"
    next_steps: str = "N/A"

    def merge(self, newer: Anchors) -> Anchors: ...   # "N/A" 不覆盖
    def render(self) -> str: ...

def parse_anchors_and_summary(text: str) -> tuple[Anchors, str]: ...
                                     # 永不抛，缺段填 "N/A"（陷阱 13）

COMPACTION_MARKER = "[Context Compaction]"       # 照 harness9 anchor.go:42
def build_compaction_message(anchors: Anchors, summary: str) -> Message: ...
                                     # 照 progressive_compactor.go:446-460：
                                     # MARKER + "## Anchors" + "## Summary"
                                     # （去掉 Offloaded 段，本层不做 offload）
def is_summary_message(message: Message) -> bool: ...
                                     # content.startswith(COMPACTION_MARKER)

SUMMARY_SYSTEM_PROMPT = "..."                    # progressive_compactor.go:26-65
FIRST_TEMPLATE       = "..."                     # 首次压缩
INCREMENTAL_TEMPLATE = "..."                     # state.summary 非空时
# ⚠️ **裁定 0 砍掉的整条旧层专有路径**，这里逐个点名，免得被当成漏项：
#   `render_message_preview`（反模仿 XML）、`template_summary`（确定性模板
#   摘要）、`SummaryRejection` / `accept_summary`（6 道拒收闸）、
#   `COMPACTION_OPEN` / `COMPACTION_CLOSE` 成对标记与 `wrap_summary` /
#   `unwrap_summary` 的 rfind、`bound_summary_blocks`（摘要 block 累积 +
#   保新丢旧 + 幂等）。harness9 的对应物分别是：无模板路径（退路是
#   `tierEmergency` 与 `TokenBudgetCompactor`）、无内容闸（`:431` 无条件
#   信任，失败才回退）、单前缀 `compactionMarker`、单份 `lastSummary`。
#   逐行理由见 §5.3。

# ---- compaction.py ------------------------------------------------
@dataclass(frozen=True, slots=True)
class CompactionState:               # 跨轮增量状态：**参数**，不是实例字段
    summary: str = ""
    anchors: Anchors = Anchors()

@dataclass(frozen=True, slots=True)
class CompactionPlan:                # 纯同步决策，无 I/O、无 LLM
    pressure: Pressure
    pinned: tuple[Message, ...]
    head: tuple[Message, ...]
    tail: tuple[Message, ...]
    needs_summary: bool

def plan_compaction(messages, budget, *, pinned: int = 0, min_tail,
                    counter=None) -> CompactionPlan: ...
# `pinned` 必须出现在**公开入口**上，否则 Q8 的泛化在公开面上不可达：
# `CompactionPlan.pinned` 与 `split_head_tail(..., pinned=...)` 有它、
# 两个入口没有 ⇒ 实现者只能自己猜首条是不是 system，而那正是 Q8 禁止的
# 唯一一种猜法。默认值与「默认值算不算一次猜」见 Q8。

def apply_compaction(plan: CompactionPlan, *,
                     summary: str, anchors: Anchors,
                     ) -> tuple[Message, ...]: ...        # 纯同步

def build_summary_prompt(plan: CompactionPlan,
                         state: CompactionState) -> tuple[str, str]: ...
                         # → (system, user)；state.summary 非空时走增量模板

@dataclass(frozen=True, slots=True)
class CompactionRecord:
    pressure: Pressure
    tokens_before: int; tokens_after: int
    msgs_before: int;   msgs_after: int
    summarized: int;    preserved_tail: int
    anchors: Anchors
    summary_text: str = ""
    degraded: str = ""          # 非空 = 走了降级路径，值是原因
    duration_s: float = 0.0
    @property
    def compression_ratio(self) -> float: ...

async def compact(
    messages: Sequence[Message],
    budget: ContextBudget,
    *,
    summarizer: Summarizer | None = None,
    state: CompactionState = CompactionState(),
    pinned: int = 0,                      # 同 plan_compaction，见 Q8
    min_tail: int = ...,
    counter: TokenCounter | None = None,
) -> tuple[tuple[Message, ...], CompactionRecord, CompactionState]: ...
# ⚠️ **`min_omitted_for_summary` 已随裁定 0 删除。** 它是旧层
# `_should_refine_episode`（`compaction:386-398`）的 port，harness9 无对应物
# ——已在 harness9 全栈复核：`determineTier`(`:209-228`) 只看比例，
# `splitHeadTail`(`:233-245`) 只看 `len(rest) <= minTail`，
# `summarizeAndExtract`(`:386-436`) 拿到 head 就调。**唯一的结构性守卫是
# 「head 为空就不压」**（`:235-243` 返回 nil head，调用方跳过整档），
# 那条已经由 `min_tail` + 陷阱 11 覆盖。
# **代价，写明**：省略集只有 3 条时也会付一次 LLM 往返。harness9 接受
# 这个代价（它的 `SoftThreshold=0.70` 意味着触发时 head 本来就不会小）。
# **本层不设超时**：一个永不返回的 summarizer 会让 `compact()` 永不返回。
# 超时归调用方（Q4-3），但这句话必须写进 docstring，见 §5.3 的超时那一行。
```

注意三处形状选择，理由在 §4：

- `compact` 返回**三元组**，第三项是新的 `CompactionState`。harness9 把
  它做成 compactor 的可变实例字段并附带「本类型只被单 goroutine 调用，
  故不加锁」的注释（`progressive_compactor.go:71-76`）。本项目的 Channel
  Surface **按构造就有重叠轮次**（`FRAMEWORK-REBUILD.md` 并行工具调用
  一节为 `_pathlock.py` 辩护时用的就是这个论据），所以那条注释在这里
  不成立。做成入参/返回值，并发问题从设计上消失。
- `plan_compaction` / `apply_compaction` 是**同步纯函数**，`compact` 只是
  把它们和一次 `await summarizer.summarize(...)` 串起来。本机
  `pytest-asyncio` 未装，异步测试要靠 `asyncio.run` 手驱；把 90% 的逻辑
  留在同步侧，测试成本与可读性都更好。
- `Summarizer` 的签名**故意不与 `LLMProvider.generate` 同形**，见 Q4。

---

## 4. 与 harness9 的对照，以及硬问题的裁决

**七个硬问题 → 裁决索引**（方便评审逐条核对）：

> **裁定 0（owner，2026-09-18）先于本节的一切**：「舍弃原本旧框架的相关
> 能力，一律以 harness9 的相关能力为主。」它直接推翻了 **Q5b**，并把
> §5 整张能力对照表的默认值改成「旧框架独有 ⇒ 丢弃；harness9 有对应物
> ⇒ 照 harness9」。三类**不受**它影响的边界（已获批准的 step 1 schema
> 偏离 / 语言级不可直译 / 本层叶子性）逐条标注在各自的裁决里，
> 汇总见附录 **C.2**。

| 硬问题 | 裁决在 | 一句话结论 |
|---|---|---|
| 1. compaction 归第 5 还是第 6 步 | **Q1** | **拆开**：纯函数归 5，跨时间的归 6；接缝三道。⚠️ 与 `FRAMEWORK-REBUILD.md:43` 的字面表述冲突 → **owner 2026-09-18 已裁定「维持」**（附录 C.2 裁定 2） |
| 2. 依赖方向，每处外来输入的接缝 | **Q2**（含 **Q2-d**） | 全部 Protocol / 可调用对象；11 项逐条点名；`ltmReader` 的「每次调用」照搬并推广；**本层不持有 clock、不读时钟** |
| 3. token 怎么数 | **Q3** | Go 的 `len` 是**字节**、Python 是**码点** → 直译低估中文 2–3 倍；重新推导 + `TokenCounter` Protocol；精度不得断言 |
| 4. 旧层能力逐条裁决 | **§5**（含 **§5.0**） | 5 张表，每行有裁决；§5.0 处理 0028 §5 结转的三项 |
| 5. 旧 context 的删除 | **§10** | **已经删了，且不是本步删的**；本步义务只有 §5 那张表 |
| 6. 命名冲突与 import 安全 | **Q6** | 安全，已实测；另发现 `tui.py:21` 的既有 sys.path bug，点名不修 |
| 7. 与已发布三层的接缝 | **Q7** | **组装根居中**，两包互不 import；四个未决项里只有 #20 的一半归本步 |

另有本计划自己提出的裁决：**Q4**（`Summarizer` 不与 `LLMProvider`
同形）、**Q5**（只产一条 system 消息）、**Q5b**（~~保留 system/message
双 placement~~ → **已被裁定 0 推翻，改为 harness9 的单一 system prompt**）、
**Q8**（不要求 `messages[0]` 是 system，含 `pinned` 的默认值裁决）、
**Q9 / Q9-a / Q9-b**（档位分母、两个预留字段无默认值、
`usable_tokens <= 0` 的边界）、**Q10**（Emergency 任务锚）、
**Q11**（工具对修复的两处不可直译）。

> **只有 owner 能拍的，原先集中在 §12。四项已于 2026-09-18 全部裁定**，
> §12 现在是存档记录，不再阻塞任何事。逐条见附录 **C.2**。

---

### Q1 —— 边界：compaction 属于第 5 步还是第 6 步？

**这是本计划最重要的一条。** 现存三份材料互相矛盾：

| 材料 | 说法 |
|---|---|
| `docs/FRAMEWORK-REBUILD.md:43` | `context/` ⬜ step 5 — prompt assembly, budget, **compaction** |
| `omicsclaw/engine/__init__.py:14-15` | Prompt assembly is step 5, session persistence and **compaction are step 6** |
| `omicsclaw/engine/loop.py:34-35` | No prompt assembly (step 5), no session persistence or **compaction (step 6)** |
| harness9 包布局 | 压缩全在 `internal/memory/`，`internal/context/` 只有 190 行 prompt 组装 |
| harness9 作者自述 | 「Context Engineering = 四层流水线：System Prompt 组装 → **上下文压缩** → 大输出外存 → 长期记忆注入」（blog:24、49-54） |

**裁决：拆开，按「是不是时间的函数」切。**

> **第 5 步拿走**：凡是 `(messages, tools, budget) -> messages` 的**纯
> 函数**。包括 token 估算、预算模型、档位判定、head/tail 切分、工具对
> 修复、按预算截断、紧急截断、摘要 prompt 的构造与解析、
> `CompactionRecord` 这个**值**。
>
> **第 6 步拿走**：凡是**跨时间**的东西。Session 读写、压缩产物写回与
> 回滚、`CompactionRecord` 的**持久化**、offload 落盘、跨轮
> `CompactionState` 的**保管**（第 5 步把它做成入参/返回值，第 6 步决定
> 存哪）。

理由，按强度排序：

1. **harness9 的包布局在这里不是边界声明，是打包顺手。**
   `compaction.go` 只 import `schema`；`token.go` import
   `encoding/json`+`fmt`+`schema`；`anchor.go` 只 import `strings`；
   `summarization.go` import `context`+`fmt`+`strings`+`time`+`schema`。
   **四个文件没有一个**引用**`Session` 类型**——实测
   `grep -n Session internal/memory/{compaction,token,anchor,summarization}.go`
   零命中。
   > ⚠️ 这句话**不能**写成「没有一个 import `Session`」（原稿的写法）。
   > `Session` 定义在 `internal/memory/session.go:14`，**同包**；Go 同包
   > 文件之间既不需要也不可能互相 import，那条对 `package memory` 的任何
   > 文件都自动成立，不构成任何证据。可核实的形式是「不引用该类型」，
   > 而那一条为真，所以结论站得住。

   它们在 `memory/` 是因为 Go 想让 `Compactor` 和 `Session` 在同一个包里
   被 `engine` 的 options 一并消费（`cmd/harness9/main.go:441-443`），
   不是因为压缩需要会话。真正需要 Session 的是
   `engine/history.go:117-179` 的 `writeBackCompaction` / `persistCompacted`
   与 `engine/compact.go:39-95`——**那两处在 `engine/`，不在
   `memory/`**。按依赖事实切，切线就落在上面那条。
2. **作者自己的概念模型把压缩放在 Context Engineering 里**（blog:24）。
   包名和意图冲突时，我们在重写，不必继承包名。
3. **预算与压缩的触发条件是同一个数。** 「还剩多少」（第 5 步无争议）
   和「该压了吗」是同一次 `estimate_tokens` 调用。把它们分到两个包，
   要么第 6 步反向 import 第 5 步（多一条边），要么估算器被抄两份
   （`FRAMEWORK-REBUILD.md:441-448` 第 7 条「Dead code ported from Go」
   正是这类）。
4. **纯变换在第 5 步是可测的，在第 6 步是被 Session 遮住的。** 本步
   全部压缩逻辑可以用「消息列表进、消息列表出」测到底，一个
   `tempfile` 都不用。

**这条裁决的代价，说清楚**：第 6 步拿到的是「一半的压缩」——它必须
自己写写回策略、回滚、和 `CompactionState` 的存放。为此本步**留下三道
明确的接缝**给它，写进 §11.A：

| 接缝 | 形状 | 第 6 步要做什么 |
|---|---|---|
| `CompactionState` | 入参 + 返回值（frozen dataclass） | 决定存哪（Session 行 / 内存 / 不存） |
| `CompactionRecord` | 只读值对象，全部字段可 JSON 化 | 决定持久化格式（harness9 是 JSONL，`record_store.go:61-72`） |
| 写回判据 | 本步以 `CompactionRecord.degraded` 与前后计数**表达事实**，不表达策略 | 照 `history.go:117-133` 的三条门控实现策略：Emergency 写回、瞬时摘要失败不写回、无实际削减不写回 |

**当初摆给 owner 的两条替代路径与它们的代价**（已被否，留作存档）：
全给第 6 步，则本步交付的
`budget.py` 会有一个没人调用的 `Pressure` 枚举（「resolves 但没人读」
正是 0028 §11 债 **#1** 的形状——`ToolPolicy.concurrency_safe` 零消费者，
`FRAMEWORK-REBUILD.md:482`；原稿写的 #5 是「`surfaces` 门控的默认语义
反转」，是另一回事）；全给第 5 步（含写回），则本步必须发明半个
Session，而 0027 已经拒绝过一次同样的事
（`FRAMEWORK-REBUILD.md:183-185`：「There is no Session until step 6 and
half of one was not worth inventing」）。

> **owner 已确认：维持本裁决（2026-09-18）。**
> `FRAMEWORK-REBUILD.md:43` 把 `prompt assembly, budget, compaction`
> 整块写在第 5 步名下，本裁决把 compaction 拆成两半。owner 在 2026-09-18
> 的裁定里选了「维持」（§12-2 的选项 A），所以拆分从「一个选择」变成
> **已定稿**。
>
> ⚠️ **交接文档那一行与本裁定并存，且本步不许去动它。**
> `FRAMEWORK-REBUILD.md:43` 仍然写着整块归第 5 步。**该行待 owner 后续
> 更新**——本计划**不得**修改 `docs/FRAMEWORK-REBUILD.md`（§9-4「例外：
> 零」）。下一个人读到两处不一致时，以本裁决 + owner 的 2026-09-18 裁定
> 为准。

---

### Q2 —— 依赖方向：每一处外来输入点名

**约束**：`omicsclaw/context/` 在 `omicsclaw` 内**只许** import
`omicsclaw.schema`（`omicsclaw.context` 内部互 import 除外），外部只许
标准库。由 §8 的分层守卫强制。

harness9 的 `internal/context/builder.go:17` **import 了
`internal/skills`**，所以它不是叶子。我们不照搬这一点，理由见下表。

| 外来输入 | harness9 怎么拿 | 本层接缝 | 谁在什么时候满足它 |
|---|---|---|---|
| 基础人格 / 角色文案 | 硬编码在 `builder.go:82-104` | `Section(key="identity", source=static(...))` 或 `text_from_file("SOUL.md")` | 组装根（Surface / composition root），每次构造 assembler 时 |
| 项目规范 AGENTS.md | `os.ReadFile` 在 `builder.go:107-110` | `SectionSource`（`text_from_file` 是 stdlib-only 便利实现） | 组装根 |
| Skills 索引 | `b.skillsIndex.Summary()`，需 import `skills` | `SectionSource` 返回**已渲染好的文本** | 组装根。本仓库的 `skills/<domain>/INDEX.md` 本来就是生成好的 markdown，渲染器早就在层外 |
| 长期记忆精华 | `ltmReader func() string`，**每次 Build 调用** | 同上，`SectionSource` | 第 6 步 / 组装根 |
| 沙箱环境说明与降级说明 | `WithSandboxContext` / `WithSandboxDegraded` | 两个普通 `Section` | 组装根（`sandbox/` 若真建，见 0029 附录 B） |
| 当前日期 | `time.Now()` 在 `Build()` 内 | **本层不持有 clock**：日期就是一个普通 `Section`，`source` 是组装根给的闭包 | 组装根。测试注入返回固定字符串的闭包；生产用 `lambda: date.today().isoformat()` |
| 摘要用的 LLM | `Summarizer` 接口，消费者侧声明（`summarization.go:20-22`） | `Summarizer` Protocol，消费者侧声明 | 组装根用 `provider.bind(...)` 包一个 5 行适配器 |
| 上下文窗口大小 | `provider.GetModelLimits(model).ContextTokens`（`main.go:397`） | **一个 `int` 入参**，不查表 | 组装根调 `get_model_limits(m).context_tokens` 后传进来 |
| 工具定义 | `registry.GetAvailableTools()` | `Sequence[ToolDefinition]` 入参（`ToolDefinition` 在 `schema`，合法） | 调用方 |
| 压缩记录落盘 | `RecordStore` 接口 + `FileRecordStore` | **不做**。返回值对象交出去 | 第 6 步 |
| 大输出 offload | `CompactionOffloader` 写文件 | **不做**。只提供占位符渲染函数 | 第 6 步 / 工具层 |

四点要展开：

**（a）`ltmReader` 为什么是「每次 Build 调用的函数」而不是快照。**
harness9 在 `builder.go:56-59` 与 blog:296-312 给的理由是：
`memory_write` 工具在 Agent 运行**中**会重写 MEMORY.md，下一轮
`Build()` 必须读到最新版；做成闭包，「写下去的东西下一轮就看得见」
是自然结果，不需要额外的通知机制。

> **裁决：照搬，并且推广到每一个 section。** 理由成立且更普遍——本仓库
> 里会中途变的不止记忆：skills 可以被 `create_omics_skill` 新建、
> AGENTS.md 可以被 `edit_file` 改。做成快照，Agent 就会用自己刚写下的
> 东西的旧版本推理。
>
> **但要补一条 harness9 没有的代价说明**：section 内容变 → system prompt
> 变 → 前缀缓存失效。`omicsclaw/provider/openai_provider.py:212-281` 的
> `apply_cache_breakpoints` 把 `cache_control` 打在**最后一条 system
> 消息**上，前缀一变整段白付。harness9 默默吃了这个成本；我们把它写进
> `PromptAssembler.render` 的 docstring，并用一条**字节恒等测试**保护它
> 不被*意外*破坏（见陷阱 7）。

**（b）为什么文件读取是 `SectionSource` 而不是 path 参数。**
harness9 的 `builder.go` 直接 `os.ReadFile(workDir/AGENTS.md)`——一个固定
文件名、一个固定位置。本仓库的 prompt 来源是 `CLAUDE.md` + `AGENTS.md` +
`SOUL.md` + 8 份 `skills/<domain>/INDEX.md` + skill gotchas，把它们都编码
成路径参数等于把「哪些文件是 prompt」这个策略钉进最底层。`text_from_file`
作为**唯一**碰文件系统的 stdlib-only 便利函数留在 `sections.py`，是可选
的，而且它是本层里**唯一**需要在测试里用 `tempfile` 的东西。

**（c）为什么窗口大小是 `int` 而不是 import `get_model_limits`。**
`omicsclaw/provider/_model_limits.py` 的 `get_model_limits(model)` 已经
存在、不抛异常、miss 时退化到 256K/8K。让本层 import `provider` 只为了
一次查表，就把叶子性换掉了，而且会让分层守卫的白名单从两项变三项。
**裁决：不 import。** 调用方传 `int`。代价：调用方多一行；收益：本层的
分层守卫可以和 `tests/tools/` 那一版一样严。

**（d）为什么没有 `clock` 参数。** 原稿在上表里写「`clock:
Callable[[], date]`，默认 `date.today`，可注入」，Task B 验收里也要一条
「注入 clock 的测试」——但 §3.2 的 `Section` / `PromptAssembler` /
`render()` **没有任何地方能接住它**。按 §1.2-4「所有外来知识一律走注入
接缝」，日期就是外来知识，正确形状是组装根传一个 `SectionSource` 闭包。
**裁决：本层不接受 clock，也不读时钟。** 于是「可注入」这件事在本层
不是一个参数，而是一条**否定性**属性：`render()` 全程不得调用
`date.today()` / `datetime.now()` / `time.time()`。这条比一个 clock 参数
更好测——见 Task B 验收 3 的 monkeypatch 写法与它的变异。

---

### Q3 —— token 怎么数？（本计划最容易出错的一条）

> **本条不受裁定 0 影响，理由：边界 (b) 语言级不可直译。**
> 这里不是「旧层 vs harness9」的取舍——**两边都不能直接用**：
> harness9 的 `charsPerToken=4`（`token.go:15`）作用在 Go 的**字节**长度
> 上，直译成 Python 的码点会把中文低估 2–3 倍；而旧层 `budget.py:191`
> 的 `ceil(码点/4)` **犯的正是同一个错**。所以本条做的是
> **port harness9 的意图（4 字符 ≈ 1 token 的字节口径），在 Python 里
> 重新推导**，而不是保留旧框架的任何东西。Q3 与陷阱 1 全文维持。

**事实一：Go 的 `len(string)` 数的是字节，Python 的 `len(str)` 数的是
码点。** `internal/memory/token.go:15` 的 `charsPerToken = 4` 作用在
`len(m.Content)` 上，因此 harness9 实际算的是 **UTF-8 字节 ÷ 4**。

本机实测：

```
s = '这是一个中文句子，用于测试 token 估算。'
len(s)            == 23     # Python 码点
len(s.encode())   == 55     # Go 的 len()
Go 口径  55 // 4  == 13
直译 Python 23 // 4 ==  5
```

**直译 `len(text) // 4` 会把中文低估 2–3 倍。** 而本仓库的 prompt 主体
（`SOUL.md`、`CLAUDE.md`、各 `SKILL.md`）是中文。

**事实二：旧 `budget.py` 也是这么错的。** `budget.py:191` 是
`-(-len(text) // _CHARS_PER_TOKEN_FALLBACK)`，即 `ceil(码点/4)`。它有
tiktoken 分支（`budget.py:141-142`）兜底，**但本机 tiktoken 未安装**
（已实测），所以生产里跑的就是那条低估分支。

**事实三：低估的方向是危险方向。** 低估 ⇒ 以为还有空间 ⇒ 塞过去 ⇒ 被
API 截断或 400。预算类判断必须**往收紧方向**钉——这正是 0028 §11 的
教训（「pin the effect in the tightening direction」）在本层的形态。

**裁决**：

1. **默认估算器不是 `len(text)/4`，也不是直译的 `len(bytes)/4`，而是
   重新推导的分段式**：

   ```python
   # 概念形态，实现者可换等价写法
   ascii_chars     = 可以映射为单字节的字符数
   non_ascii_chars = 其余字符数
   tokens ≈ ceil(ascii_chars / 4) + non_ascii_chars
   ```

   对纯 ASCII 与 harness9 口径一致（4 字节/token）；对 CJK 按 1 token /
   字符收费，方向偏保守。**这是重新推导，不是搬来的字面量。**

2. **`TokenCounter` 是 Protocol**，装了 tiktoken 的部署可以注入精确的。
   本层**绝不 import tiktoken**（无网络、不是依赖），也**绝不**因为它
   碰巧装上了就改变默认行为——这一条直接沿用旧 `budget.py:155-161` 的
   理由，那段注释是对的：

   > A model-less estimate is part of the deterministic local budget
   > contract: it must not change merely because the optional
   > ``tiktoken`` package happens to be installed.

3. **`estimate_message_tokens` 必须数 `reasoning_content` 与 `name`。**
   harness9 的 `token.go:19-29` 数的是 `Content` + 每个
   `tc.ID/Name/Arguments` + `ToolCallID`，**没有 reasoning**——因为
   harness9 的 schema 里根本没这个字段。本项目的 `Message` 有，而且是
   ADR 0077 **刻意**加的（`FRAMEWORK-REBUILD.md:102-106`：thinking 端点
   要求历史 assistant 轮保留它）。照抄字段清单 = 对 thinking 模型的历史
   **系统性低估恰好是刻意加进来的那个字段**。见陷阱 1。
   > **本条不受裁定 0 影响，理由：边界 (a) 已获 owner 批准的 step 1
   > schema 偏离。** 数 `reasoning_content` 不是「保留旧框架能力」，是
   > 「port harness9 的意图（把消息的全部计费字段都数进去），适配本仓库
   > 已批准的四角色 + 持久化 `reasoning_content` 的 schema」。

4. **必须数工具定义。** `token.go:33-45` 的注释说得很清楚：工具 schema
   在工具多时能吃掉 20-30K+ token，preflight 必须纳入。本仓库有 50+ 个
   既有工具待迁移，这一项会是最大单项。

5. **精度一律不得断言。** 本机装不上 tiktoken，**测不出真值**。实现者
   必须：(a) 在能测的环境里跑一次标定，对
   `SOUL.md` / `CLAUDE.md` / 一份 `skills/*/INDEX.md` / 一段英文 docstring
   四类语料记录估算值 vs 真值；(b) 测不了就在 docstring 里写
   「未标定」，**不得**写「误差 ±10%」之类未测过的话。
   这条进 §9 验收。

   > 第 4.5 步的教训（`FRAMEWORK-REBUILD.md:449-455`）：五条自信描述
   > 参考实现的 docstring 是错的，「confidently wrong 就是缺陷，因为下一个
   > 人会照着做」。精度声明是同一类。

6. **`format_token_count`（`token.go:49-58`）照搬行为，不照搬三分支
   结构**——Python 写成一个循环或两个条件都行，写成三个 `case` 只是
   Go 的 switch 长相。见陷阱 15。

---

### Q4 —— `Summarizer` 为什么不与 `LLMProvider` 同形

harness9 `summarization.go:20-22`：

```go
type Summarizer interface {
    Generate(ctx, messages []schema.Message, availableTools []schema.ToolDefinition) (*schema.Message, *schema.Usage, error)
}
```

与 `provider.LLMProvider` 逐字同形，所以 provider 结构性满足它，
`main.go:425` 直接 `NewProgressiveCompactor(llm, ...)`。

**Python 学不了这一手**：`LLMProvider.generate` 返回
`omicsclaw.provider.Completion`。要让 Protocol 同形，本层就得 import
`provider` 来写返回类型——叶子性没了。

**裁决：换成 `async def summarize(self, prompt: str, *, system: str) -> str`。**
理由三条，**而且第二条本身就是收益**：

1. 保住叶子性（Q2）。
2. 摘要这一次调用**本来就需要不同的绑定**：`tools=None`（`provider` 的
   契约里 `tools=None` 是**剥光工具**，不是「用默认集」——
   `FRAMEWORK-REBUILD.md:137-140`），而且通常该用便宜的小模型
   （`provider_from_env(model="claude-haiku-4-5", max_tokens=64)` 这种
   用法在 `FRAMEWORK-REBUILD.md:121` 就有）。这些决定属于组装根，
   不属于压缩器。写一个 5 行适配器**比结构性满足更诚实**。
3. harness9 在压缩器内部硬编码了 60 秒超时
   （`summarization.go:219-220`、`progressive_compactor.go:420`），理由
   是「`Compact` 接口不传外层 context，感知不到取消」。Python 里这是
   调用方的 `asyncio.timeout`：把超时埋进纯变换里，既测不了也改不了，
   而且我们的 `compact` **是** async 的，取消会自然传播。
   **裁决：不搬那个 60 秒。** 超时归调用方，并在 docstring 里写明
   harness9 为什么需要它、我们为什么不需要。

---

### Q5 —— prompt 只能产出**一条** system 消息

两个适配器对多条 system 消息的处理**不同**：

- Anthropic：`anthropic_provider.py:262-290`，所有 `Role.SYSTEM` 被
  提出来 `"\n\n".join(system_parts)`。
- OpenAI：`openai_provider.py:123-169`，每条原样变成
  `{"role": "system", ...}`，**不合并**。

因此「一段一条 system 消息」的组装方式会在两个后端产出**不同的
prompt**——Anthropic 看到一整块，OpenAI 看到 N 条。

**裁决：`assemble(...)` 产出的序列里，`role == Role.SYSTEM` 的消息
恰好一条，且它是第 0 条；段与段之间用 `"\n\n"` 连接**（与 harness9
`builder.go:189` `strings.Join(parts, "\n\n")` 一致，也与 Anthropic 适配器
的连接符一致）。用一条测试把「多段 → 一条消息」钉死。

> **名字更正。** 原稿这里写的是 `PromptAssembler.build()`，而 §3.2 里
> 根本没有 `build()`：`PromptAssembler.render() -> AssembledPrompt`
> （`.system_prompt` 是 `str`，不是 `Message`），把它变成 `Message` 的是
> 模块级的 `assemble()`。三个名字两种返回类型，按字面读不可执行。
> 「恰好一条 system Message」按 §3.2 是 **`assemble()` 的性质**，Task B
> 验收 1 已同步改写。

附带收益：`apply_cache_breakpoints` 的 `_mark_last_system_message` 找的是
**最后一条** system 消息；只有一条时，断点位置不会因为段数变化而漂移。

---

### Q5b —— ~~保留 system / message 双 placement~~ → **单一 system prompt**

> **本条已被 owner 的裁定 0（2026-09-18）整条推翻。** 原裁决是「保留
> placement 拆分，这是旧层唯一一处明确优于参考实现的设计」。裁定 0 的
> 原话是「舍弃原本旧框架的相关能力，一律以 harness9 的相关能力为主」，
> 而 placement 拆分**恰恰是旧框架独有**的。下面保留原论证的事实部分
> （它们仍然为真，只是不再构成裁决理由），并把**代价**显式记下来。

**事实（未变）：harness9 把六段全部塞进 system prompt。**
`builder.go:78-189`：`Build()` 在 `:78`，`parts` 只有一个去处，
`:189` 是 `strings.Join(parts, "\n\n")`（逐行核实）。包括长期记忆——
一个每轮都可能被 `memory_write` 改写的东西。

**事实（未变）：旧 OmicsClaw 层不是这么做的。**
`layers/__init__.py:1116-1294` 的 **23** 个 injector 每个都带
`placement ∈ {system, message, attachment}`（AST 复核：8 个 `system` +
15 个 `message` + **0 个** `attachment`），ADR 0024 的设计意图写在内联
注释里：**稳定的进 system（可被前缀缓存），随查询变的骑在 user 轮上**。

**裁决（改判）：照 harness9 做——`PromptAssembler.render()` 只产出
一个 `system_prompt: str`，段与段之间 `"\n\n"` 连接；`Placement` 枚举、
`AssembledPrompt.message_context`、`Section.placement` 字段
全部不建。**`attachment` 一档同样不建（原本就已判丢弃，理由不变：
23 个 injector 无一使用）。

**代价，必须写明，不许藏起来**（这是本裁决唯一真正的内容）：

| 代价 | 具体形态 |
|---|---|
| **前缀缓存每轮失效** | 易变内容（skill context、scoped memory、capability assessment、knowledge guidance、plan、knowhow constraints）进 system prompt 后，**每次变动都打断前缀**。`openai_provider.py:212-281` 的 `apply_cache_breakpoints` 把 `cache_control` 打在**最后一条 system 消息**上；前缀一变，那一整段缓存白付 |
| **前两步已经为前缀缓存付过钱** | `registry.py:261-275` 专门保证 `available_tools()` 在注册表不变时**逐字节相同**，docstring 原话是「that is what the prefix cache is paying for」。本裁决不作废那笔投入（工具列表仍然稳定），但**system prompt 这一半的收益归零** |
| **本项目的易变内容比 harness9 多** | harness9 的易变段只有 LTM 一个，所以它吃这个成本吃得起；本仓库上面列的六类**每一个都随用户这一句话变** |
| **一条被测试钉过的不变量消失** | 旧层 `tests/test_context_assembler.py:1037`「volatile memory must not churn the system prefix」与 `:322` 的 byte-stability 断言。前者随本裁决作废，**后者（同一次 render 的字节稳定）仍然保留**，见陷阱 7 与 Task B 验收 3 |

**owner 接受这个代价**（harness9 也接受）。这是一条**显式的取舍记录**，
不是疏漏——下一个人看到 prompt 缓存命中率低时，应该先读这一行再动手。

> **ADR 0024 怎么办？** 它仍然有效，但**适用范围收窄**：本层不再按
> placement 拆分，它在新架构里的落点只剩 provider 侧的
> `apply_cache_breakpoints` 与 `registry.available_tools()` 的字节稳定。
> §10.2 那句「ADR 0024 与 ADR 0039 仍然有效，而且新层要继续遵守」按此
> 理解。ADR 本身的更新**不归本步**（§9-4「例外：零」）。

---

### Q6 —— `omicsclaw/context/` 这个名字安全吗

**结论：安全，可用。已实测。**

1. **不与 `omicsclaw/tools/context.py` 冲突。** 全限定名不同
   （`omicsclaw.context` vs `omicsclaw.tools.context`），`sys.modules`
   是两个键。现有 9 处引用全部是**显式相对导入**
   （`registry.py:48-49`、`tools/__init__.py:82`、
   `builtin/{read,write,edit,bash,web_fetch,web_search}.py` 的
   `from ..context import ...`），`.context` / `..context` 都锚在
   `omicsclaw.tools`，够不到新包。
2. **不与 `contextlib` / `contextvars` 冲突。** Python 3 没有隐式相对
   导入（PEP 328），包内 `import contextlib` 走绝对解析到标准库。
   实测：临时建一个 `omicsclaw/context/__init__.py` 后
   `import omicsclaw.context, omicsclaw.tools.context, contextlib,
   contextvars` 全部正常，`contextlib.__file__` 仍指向标准库。
3. **全仓库没有任何 `import context` / `from context import`。** 实测为空。
4. **`omicsclaw/__init__.py` 只 import `omicsclaw.version`**，其余走
   PEP 562 `__getattr__`；新增子包不会被拖进任何 import。
5. **打包无需改动**：`pyproject.toml` 的 `include` 是
   `["omicsclaw", "omicsclaw.*", ...]`。

**一个真实的、既有的隐患，必须点名但不属本步：**
`omicsclaw/surfaces/cli/tui.py:21` 把 `_OMICSCLAW_DIR` 算成
`Path(__file__).resolve().parent.parent.parent` —— 实测等于
**`<repo>/omicsclaw`（包目录本身）**，而不是仓库根；对比
`interactive.py:208` 用 `parents[3]`，等于仓库根。tui.py 在
第 579 与 1019 行把这个值 `sys.path.insert(0, ...)`。一旦
`omicsclaw/context/` 存在，在 TUI 进程里 `import context` 就会解析到
我们的包。**目前全仓库没有任何裸 `import context`，所以敞口是潜在的，
不是活的**；而且这是既有 bug（与 interactive.py 不一致），属迁移工作。
本步只负责**写下来**，不负责修（一改就违反 one component per step）。

**验证方法**（写进 §9）：分层守卫的行为探针在子进程里 import 并运行
本层，打印 `sorted(m for m in sys.modules if m.startswith("omicsclaw.runtime"))`
必须是 `[]`；另加一条断言 `contextlib.__file__` 落在
`sys.stdlib_module_names` 对应的标准库路径下。

---

### Q7 —— 与已交付三层的接缝：谁调用谁

**先说事实**（读的是代码，不是计划）：

- `AgentEngine.__init__(provider, tools, config)` —— **没有 prompt 参数，
  没有 system 参数，没有 hook 参数**。
- `grep -rn "system" omicsclaw/engine/*.py` 只命中 4 处，**全在
  docstring 里**。引擎从不检查 `Role.SYSTEM`。
- 主循环 `omicsclaw/engine/loop.py:192-274`（**工作区的新引擎**，
  `_kernel` 在 `:192`）里 `history` 是生成器帧内的局部
  `list[Message]`，不暴露、无回调。唯一的注入点是私有的
  `_TurnStrategy`，而且不是构造参数。
- `RunResult.messages` 是 `tuple[Message, ...]`，**含输入**，
  `types.py:139-144` 明说「可以直接喂回下一次 run」。

**裁决：context 产出 messages，由组装根喂给 engine。两个包互不 import。**

```
composition root
   ├─ context.assemble(...)  ──→ Sequence[Message] ──→ engine.run(...)
   └─ context.compact(RunResult.messages, ...) ──→ 下一次 run(...)
```

不做 `engine import context`，理由：engine 已交付且经两轮评审，
one component per step 不许本步改它。也不做 harness9 那种
「engine 声明 `PromptBuilder` 接口、context 结构性满足」——那需要在
`omicsclaw/engine/` 里加一个 Protocol，同样越界。

**代价，必须写明**：harness9 在 `loop_phases.go:164` 是**每轮**调压缩的
（`prepareTurnInput` 阶段 2）。我们做不到。本步交付后能做的只有
「run → 压 → 再 run」这种**轮间**压缩，粒度是一次 `run()`。
一个 `max_turns=50` 的长跑在中途撑爆窗口时，本步拦不住。

**这是缺口，不是设计。** 补法照 0028 / 并行工具调用那一轮的既定做法
——**给 `omicsclaw/engine/` 加一个可选 Protocol**
（`ConcurrencyAwareExecutor` / `DeadlineAwareExecutor` 就是这么加的），
在 `while` 体顶端调用。
**harness9 的同构形状已核实**（owner 裁定 4a）：
`WithCompactor(c memory.Compactor)`（`options.go:135-138`，docstring
原话「在每次 LLM 调用前裁剪历史消息」），调用点
`loop_phases.go:164-168`；纪律是「接口定义在 engine 包（使用者侧），
由 internal/context 包实现」（`options.go:157-159`）。
**这是引擎改动，不归本步。** 形态与行号证据记在 **§11.B-1**，
**等完整 agent 架构就绪后由 owner 决定何时开**——不写排期。

**`FRAMEWORK-REBUILD.md` 提到的四个未决项，哪些归本步：**

| 未决项 | 归属 | 理由 |
|---|---|---|
| `EngineConfig.tool_timeout = 60.0` 是未声明的搬运字面量 | **不归本步** | 在 `engine/config.py`，且是工具调度而非上下文预算 |
| `web_search` / `web_fetch` 与旧名冲突 | **不归本步** | 迁移工作 |
| approval 在 `EngineEventType` 里没有表示 | **不归本步** | 要加枚举成员 = 改 engine |
| context-window 上报（#20，"still open and still cheap"） | **一半归本步** | 缺的那个「token 计数器」就是本步的 `tokens.py`（`engine/types.py:220` 原话「it belongs to step 5」）。但**发事件**要加 `EngineEventType` 成员，归引擎改动。本步交付 `BudgetReport`，让 Surface 能自己算并自己显示。⚠️ 另一半按 owner 裁定 3/4a **与 §11.B-1、§11.B-12 合并为同一个后续步骤**——harness9 的上报点 `loop_phases.go:173-174` 就紧挨着压缩 `:164-168` 与 nudge/gate `:176-206` |

---

### Q8 —— 不要求 `messages[0].role == SYSTEM`

harness9 的每一个 compactor 都以此为前提，不满足就**原样返回**
（`compaction.go:39-41`、`:103-105`、`summarization.go:102-104`、
`progressive_compactor.go:235-237`）。这在 harness9 是安全的，因为
`history.go:62-64` 保证引擎每次都在 0 位注入 system。

**本项目的引擎不注入任何东西**（Q7）。照搬这个前提，一个没带 system
消息的对话会让压缩器**静默变成 no-op**——0028 §11 债 **#1** 那种
「resolves 了但没人读、且不会变红」的形状（`ToolPolicy.concurrency_safe`
零消费者）。原稿写的 #5 是「`surfaces` 门控默认语义反转」，是另一回事。

**裁决：泛化成「被钉住的前缀」**。`split_head_tail(messages, pinned=N,
min_tail=M)`：前 `N` 条无条件保留（组装根传 `1` 即得 harness9 行为，
传 `0` 表示没有 system）。由调用方声明，不由本层猜。

**`pinned` 必须出现在两个公开入口上。** 原稿只把它放在
`split_head_tail` 与 `CompactionPlan` 上，而 `plan_compaction` 和
`compact` 都没有它——那样实现者除了自己猜首条是不是 system 之外无路可走，
而那正是本条禁止的唯一一件事。§3.2 已补：
`plan_compaction(..., pinned: int = 0, ...)`、`compact(..., pinned: int = 0, ...)`。

**默认值 `0`，以及它算不算一次「猜」：**

| | `pinned=0`（采用） | `pinned=1`（不采用） |
|---|---|---|
| 它断言了什么 | **什么都没断言**——「调用方没说，本层就不保护任何前缀」 | 「首条是 system」，即 harness9 的前提 |
| 忘了传的后果 | system 消息落进可压缩的 head，可能被摘要掉 | 一个**没有** system 消息的对话，首条 user 任务消息被当成 system 无条件保留 |
| 这个后果会不会静默 | 不会：摘要里仍有内容，且压缩后**装得下**这条验收（陷阱 2）照常成立 | 会：多保一条，没有任何断言会红 |

`0` 不是一次猜，是「拒绝猜」的编码：它是唯一一个不对输入形状作任何
断言的值。代价是真实的——**忘了传 `pinned=1` 的调用方，其 system 消息
会被当成可压缩的 head**。三条缓解，全部写进 `plan_compaction` 的
docstring：

1. `assemble()` 的产出**必然**以一条 system 打头（Q5），所以组装根把它
   喂给 `compact()` 时的正确值是 `pinned=1`；docstring 里给出这一行示例。
2. `CompactionRecord.degraded` 在 `pinned == 0 且 messages[0].role is
   Role.SYSTEM` 时写一句提示——**表达事实，不改行为**（与 §11 的接缝
   约定一致：本层表达事实，策略归调用方）。
3. 陷阱 8 的变异（把 `pinned` 写死成「首条必须是 system，否则原样返回」）
   点名测试照旧。

---

### Q9 —— 五档压力，但阈值重新推导

harness9 `progressive_compactor.go:129-133` 的默认档位是
`0.60 / 0.70 / 0.80 / 0.95`，分母是 `ContextWindow`
（`:215`：`float64(EstimateTokens(msgs)) / float64(c.ContextWindow)`）。
`TokenBudgetCompactor` 另有一个扁平的 `contextWindow * 80 / 100`
（`compaction.go:89`）。blog:173 给的 80% 理由是：剩下 20% 要覆盖工具
schema（10-30K）、字符÷4 的估算误差、以及模型输出的空间。

**裁决：保留五档结构，但分母换成可算的量。**

```
usable = context_tokens
       - reserve_output_tokens     # 已知：ModelLimits.output_tokens
       - reserve_tool_tokens       # 已测：estimate_tool_tokens(tools)
       - safety                    # 估算误差余量
ratio  = message_tokens / usable
```

理由：harness9 的 80% 是**因为它没有这两个数才只能拍一个比例**。我们
两个都有——`omicsclaw/provider/_model_limits.py` 给 `output_tokens`，
`estimate_tool_tokens` 给工具项。用扁平 80% 等于把已知量当未知量。

> **本条不受裁定 0 影响，理由：这不是「保留旧框架能力」，是 port
> harness9 自己的意图。** 证据是 harness9 自己写的：
> `cmd/swebench/runner.go:293-299` 在**真实 benchmark** 里没有用
> `NewTokenBudgetCompactor` 的 80%，而是
> ```go
> compactor := &memory.TokenBudgetCompactor{
>     MaxTokens:       lim.ContextTokens * 55 / 100,
>     MinTailMessages: 8,
> }
> ```
> `:294` 的注释给的理由逐字是「预算取上下文窗口的 55%，为**工具定义
> (~25K) + 输出预留 + chars/4 估算误差**留足余量」——**它点名的三项，
> 正是本裁决那个减法式的三个被减数**（`reserve_tool_tokens` /
> `reserve_output_tokens` / `safety`）。harness9 在没有这三个数时只能把
> 它们折成一个比例；我们有，就把它写成显式减法。这是 port 意图，不是
> 保留旧层。
>
> **而且它是 Q9-a 的硬证据**：`compaction.go:87-92` 的 80% 默认值在
> **有工具定义时不够保守**，harness9 自己在真实负载上把它压到了 55%
> （差 25 个百分点，200K 窗口上是 50K）。所以「`reserve_tool_tokens`
> 不给默认值、少传就 `TypeError`」不是洁癖，是 harness9 用一次 benchmark
> 返工换来的教训。**`55/100` 与 `MinTailMessages: 8` 这两个字面量同样
> 是从 SWE-bench 标定的，不得直接搬**（陷阱 1）。

**但要带一条警告**：`_model_limits.py` 的默认 `output_tokens = 8192`
的含义是「不知道」，不是「知道是 8192」
（`FRAMEWORK-REBUILD.md:652`）。因此 `reserve_output_tokens` 可能偏
乐观。`ContextBudget` 的 docstring 必须写明。

#### Q9-a —— 两个预留字段**没有默认值**

原稿 §3.2 写的是 `reserve_output_tokens: int = 0` 与
`reserve_tool_tokens: int = 0`，与上面那句「默认值取保守侧」**方向相反**。
`0` 不是守卫值，是便利值，正是
`FRAMEWORK-REBUILD.md:263-264`「Defaults are the **guarded** values, not
the convenient ones」点名的那一类。具体危害：忘了传
`reserve_tool_tokens` 的调用方会拿到一个比真实可用空间大 **20-30K** 的
预算（`token.go:32` 的注释给的量级），而 `plan_compaction` **不收
`tools`**，本层结构上无从发现这件事；陷阱 2 只钉了
`usable_tokens < context_tokens`，`0/0` 也满足它。

**裁决：两个字段都不给默认值，少传就是构造期 `TypeError`。**
理由：任何一个默认值都是一次猜，而 `0` 是所有猜里最乐观的那个。
调用方要么从 `get_model_limits(m).output_tokens` 取，要么从
`estimate_tool_tokens(tools)` 取——两个数都是**已知的**，这正是本条
裁决上半段的立论（「用扁平 80% 等于把已知量当未知量」）。
Task A 验收加一条：`ContextBudget(context_tokens=200_000)` 必须
`TypeError`。

> **harness9 的 55% 是这条裁决的独立佐证**（`runner.go:293-299`，见 Q9
> 正文的引用块）：它的 `NewTokenBudgetCompactor` 默认 80%
> （`compaction.go:87-92`）在真实 benchmark 上被作者自己下调到 55%，
> 理由第一项就是「工具定义 (~25K)」。**一个默认值在有工具时偏乐观
> 25 个百分点，这正是「默认值必须是守卫值」要防的那件事**
> （`FRAMEWORK-REBUILD.md:263-264`）。

#### Q9-b —— `usable_tokens <= 0` 与 `context_tokens <= 0` 走哪一档

原稿在两处给了**相反**的答案：§5.2 写「保留旧层
`effective_capacity <= 0 → BLOCK`」（BLOCK = 新命名的 Emergency），
附录 A.2 写「`progressive_compactor.go:212-213` `ContextWindow<=0 →
TierNone` | port；分母换成 `usable_tokens`」。分母一换，两条作用在**同一
条件**上而结论相反：「什么都不做」vs「紧急压缩」。§9 验收与陷阱 2 的
边界测试都没覆盖到它。

注意方向：`TierNone` 正是 Q8 自己点名要避免的「resolves 但没人读、且
不会变红」的形状——压缩器在最该动手的时候静默成 no-op。

**裁决（三行，互不重叠）：**

| 条件 | 行为 | 依据 |
|---|---|---|
| `context_tokens <= 0` | `ContextBudget.__post_init__` 抛 `ValueError` | 「没配预算」不该用 `0` 表达。旧层为此专门写了 `local_budget_status` 在无预算时返回 `None` 而不是误报 BLOCK（`budget:73`，§5.2 已 port）。新形状下它的等价物是**调用方持有 `ContextBudget \| None`**——不构造，而不是构造一个语义为「不知道」的 |
| `usable_tokens <= 0` 且 `context_tokens > 0`（预留吃光了窗口） | `Pressure.EMERGENCY`，`plan_compaction` 走 emergency 路径 | 收紧方向（Q3-3）。此时连一条历史都放不下，「什么都不做」= 把整段历史原样发出去挨 400 |
| `progressive_compactor.go:212-213` 的 `ContextWindow<=0 → TierNone` | **不 port** | 它在 harness9 安全是因为那里 `ContextWindow` 直接就是窗口；换成 `usable_tokens` 之后同一行代码的含义变了 |

两条都进陷阱 2 的边界测试清单。

**四个档位比例本身不重新推导**（0.60/0.70/0.80/0.95 保留为默认），但
必须在 docstring 里标注它们是 harness9 的经验值、分母已经换过、
**没有在本项目的负载上标定过**。诚实标注 > 编一个新数字。

---

### Q10 —— Emergency 档必须无条件保住第一条任务消息

`compaction.go:136-142` 的注释是 issue #117 的 E2E 实测教训：

> 紧急截断若把任务一并丢弃，模型将失去目标陷入空转死循环
> （实测：连续 143 轮 Emergency、任务失败）

且第二条：从最新往前按剩余预算**逐条**纳入，单条超预算就**跳过**而不是
截断——防止一条巨型 tool_result 撑爆紧急视图。

**裁决：行为全部照搬，理由一并搬进 docstring。** 这是本计划里少数
「有实测证据支撑」的设计，不是风格。对应 `emergency_fit`。

---

### Q11 —— `repair_tool_pairs` 的两处不能直译

`compaction.go:200-239` 做两件事：删掉没有对应 `tool_call` 的孤立
`tool_result`；给没有响应的 `tool_call` 补一条占位 `tool_result`。

**两处 Python 侧必须重判：**

1. **「这条是 tool result」的判据。** harness9 用
   `m.ToolCallID != ""`。本项目的 Anthropic 适配器
   （`anthropic_provider.py:276`）用的是 `message.role == Role.TOOL`。
   **判据必须与适配器一致**，否则「修好了」和「适配器认得」是两件事。
2. **占位消息的角色。** harness9 造的是
   `Message{Role: RoleUser, ToolCallID: tc.ID}`
   （`compaction.go:229-233`）——因为 harness9 的 schema 只有三个角色，
   observation 就是带 `ToolCallID` 的 user 消息
   （`loop_phases.go:279-286` 同样如此）。
   **本项目有第四个角色 `Role.TOOL`**（ADR 0077 的刻意偏离）。
   直译会造出 `Message(role=USER, tool_call_id=...)`，而
   `anthropic_provider.py:270-284` 只按 `role` 分派——它会把这条当成
   **普通 user 文本轮**，`tool_call_id` 被完全忽略，于是那个未回答的
   `tool_use` block **仍然没有回答**，正好撞上这个函数存在的唯一理由
   （API 400）。

   **裁决：占位消息必须是 `Message.tool(tool_call_id=..., content=...)`，
   `is_error=False`。** `is_error=False` 是因为工具没有失败，是历史被
   压缩了——把它标成错误会教模型去重试一个本来成功的调用。

   这是本计划里「结构可搬、字面量不可搬」的样板案例，见陷阱 1。

   > **本条不受裁定 0 影响，理由：边界 (a) 已获 owner 批准的 step 1
   > schema 偏离。** `omicsclaw/schema` 有四个角色（含 `tool`）且持久化
   > `reasoning_content`，这是 ADR 0077 的既定偏离
   > （`FRAMEWORK-REBUILD.md:101-106`，原文「**Four roles including
   > `tool`**, and **`reasoning_content` persisted** — both deliberate
   > deviations from harness9」）。所以这里**不是**「保留旧框架能力」，
   > 是「port harness9 的意图（把未回答的 tool_call 补上一条回答），
   > 适配本仓库已批准的 schema」。**直译反而会功能失效**：已核实
   > `anthropic_provider.py:271-290` 的编码循环严格按 `role` 分派
   > （`Role.SYSTEM` 在 `:271`、`Role.TOOL` 在 `:275`、`Role.USER` 在
   > `:281`），`Message(role=USER, tool_call_id=...)` 会走 `:281` 那支变成
   > 普通文本轮，`tool_call_id` 被完全忽略。

---

## 5. 旧层能力对照表

> **规则同 0028 §5 / 0029 §6：每一行都必须有裁决，留空即缺陷。**
> 「丢弃」是合法裁决，但必须写明后果——谁会坏、迁移工作归谁。
>
> **前提**：旧层 `omicsclaw/runtime/context/` 已被 owner 裁定移除，
> 且在工作区**已是 staged 删除状态**。所以本表不是「必须保住」清单，
> 是**强制交代**清单。

旧层有 **7** 个文件、3,705 行，对应 §0.1 那 13 个测试文件
（**全部已 staged 删除，工作区一个都不剩**）。

#### 5.0 计划 0028 §5 结转过来的三项 —— **本表的第一件事**

> 这一小节是修复轮补上的。原稿里这三个名字**一次都没出现**，而
> `docs/plans/0028-tool-registry.md:803-807` 把它们与已裁决的两项
> （`surfaces`、`predicate`）并列，写明「去向已定，但**家还没建**，
> 家不建工具就迁不干净」。
> owner 2026-09-18 的裁定（`FRAMEWORK-REBUILD.md:717-742`）只覆盖**四项
> 门控**（Surface 门控、predicate 门控、每会话冻结工具列表、按阶段裁剪
> 子集），**不含这三项**。
> 「留空即缺陷」这条机制在一个**权限收紧方向**的能力上失效过一次，
> 就是这里。

| 0028 §5 的名字 | 0028 判给谁 | 消费者与效力 | **本步裁决** |
|---|---|---|---|
| `speculative_classifier`（`0028:515`） | **装配层**（明写「→ 装配层」，即本步） | `runtime/tools/orchestration.py:271` 的 `_classifier_policy_decision`：在执行**前**把 `risk_level`/`approval_mode` 升级为 DENY 或 REQUIRE_APPROVAL，并读 `request.runtime_context` 的 `surface`/`trusted`/`background` | **定稿裁决（owner，2026-09-18）：已定向——交给 owner 后续设计的新入口/交互层**（`FRAMEWORK-REBUILD.md:748-752`，原 §12-1 的选项 B）。**本步不建。** 那一层「后续再设计实现」，没有排期。**空窗期的后果必须被记住**：在它落地之前，「工具执行前二次收紧 `risk_level` / `approval_mode`」的能力在新架构里**不存在**——`ToolPolicy` 的守卫默认（`HIGH`/`ASK`）挡住的是「未声明的工具」，挡不住「声明为 `AUTO` 但在这一次调用里本该 ASK」。这是**唯一一项方向朝收紧**的结转能力，所以它是「被安排」而不是「被删」 |
| `result_policy`（6 个值，`0028:516`） | **存储/压缩层** | `runtime/storage/tool_result.py` 的 `_effective_result_policy` / `_inline_bytes_for_policy` / `_preview_chars_for_policy`，以及 `runtime/context/compaction.py:739`：控制工具输出何时落盘、inline 阈值与预览长度 | **归第 6 步**，随 offload 一起。本步已在 §1.3 声明不做 offload、在 §11.A-4 记了债；这一行把它与 0028 的名字对上。本层只提供「一条消息太大」的判定与占位符渲染，「多大算大、预览留几行」是 `result_policy` 的内容，属落盘的人 |
| `progress_policy`（`0028:517`） | **loop / Surface 层** | `runtime/agent/loop.py:822`：值为 `analysis` 时触发「耗时 10–60 分钟」的进度通知，直接依赖 `chat_id` / `progress_fn` 回调 | **不归本步**，0028 §5 本来也没判给装配层。进度通知已经在新层有家：第 4 步的 `contextvars` 带外通道有一个 progress sink（`FRAMEWORK-REBUILD.md:268-273`）。迁移时把 `analysis` 这个判据接到那个 sink 上即可，**归迁移**，记入 §11.B-17 |

#### 5.1 `layers/` —— 分层与注入

| 旧能力 | 出处 | harness9 有无 | 裁决 | 理由 / 后果 |
|---|---|---|---|---|
| `ContextLayer`（name/content/placement/order/estimated_tokens/cost_chars/metadata） | `layers:572-590` | **无** | **收窄的融合** → `Section` + `RenderedSection` | **裁定 0 后只保留 name/estimated_tokens**。`placement` 与 `order` 随下面两行丢弃；`cost_chars` 丢弃（有 token 就不需要第二个单位）；`metadata` 丢弃（唯一生产者是 prompt-pack 层，见下） |
| `placement ∈ {system, message}` 与 ADR 0024 意图 | `layers:1116-1294` 全表 | **无**（全进 system） | ~~port~~ → **丢弃（裁定 0）** | 旧框架独有。harness9 六段全部进 system prompt（`builder.go:78-189`，`:189` 是 `strings.Join(parts,"\n\n")`）。**后果**：易变段进 system prompt ⇒ 每次变动打断前缀缓存。**这是一条显式的取舍记录，代价表见 Q5b** |
| `placement == attachment` | `assembler:70-71`、`:82-83` | 无 | **丢弃** | 原本就已判丢弃（**23** 个默认 injector **无一使用**，AST 复核，死代码——陷阱 15）；裁定 0 后整个 `Placement` 枚举都不建，本行更无争议。（原稿引的 `assembler:120` 是 `AssembledChatContext.capability_context`，与本行无关） |
| 渲染顺序 = `sorted(key=(order, name))`，**跨 placement 全局排序** | `assembler:324` | 无（append 顺序） | ~~port~~ → **丢弃（裁定 0）** | 旧框架独有。harness9 的顺序就是 `parts = append(parts, ...)` 的**加入顺序**，没有排序键。改为 `PromptAssembler.with_section` 追加到末尾。**顺序确定性不受影响**（加入顺序同样是确定的，字节稳定照旧可测）。**代价**：组装根必须按正确顺序 `with_section`，不能靠事后调 `order` 纠正——写进 `PromptAssembler` 的 docstring |
| 空内容层整段消失（含标题） | `layers:768-803` | 有（`builder.go:113,178`） | **port** | 两侧一致 |
| builder 抛异常 → fail-closed + WARNING | `layers:768-803` | **无** | **丢弃旧层的 fail-closed；异常原样冒泡，且不 logging** | **本行不受裁定 0 影响，理由：(b) + (c)。** 它不是在「保留旧框架能力」——旧层的 fail-closed 恰恰**被丢掉了**。剩下的「冒泡」是 Python 惯用法与叶子性的产物：① 本层是叶子，`omicsclaw/engine/` 已立下「no I/O, no logging」的约定；② `SectionSource` 是**任意可调用对象**（不像 harness9 只 `os.ReadFile` 一个固定的 AGENTS.md），吞掉任意异常是 Python 反模式；③ 旧的 fail-closed 会让「SOUL.md 读失败」静默变成「Agent 没有人格」——**静默的正确性损失比崩溃更贵**。**后果**：调用方必须自己包 try。写进 `Section.source` 的 docstring |
| `ContextAssemblyRequest`（27 字段 **+** 4 个可注入 loader = 31 个注解字段） | `layers:593-672` | 无（`With*` 链） | **丢弃这个形状** | AST 复核：31 个注解字段，其中 4 个是 loader——`base_persona_loader`、`knowhow_loader`（`KnowhowLoader = Callable[..., str]`，`layers:85`）、`knowledge_loader`、`extension_prompt_pack_loader`。31 − 4 = 27。27 个字段的巨型请求对象是「装配层知道全世界」的具象化。换成 `Section` 序列：谁要注入谁自己加一段。**后果**：调用方要自己组 assembler；提供一个「典型组合」的示例放在 `__init__` docstring |
| `surfaces` 门控（bot / interactive / pipeline） | `layers:735-766` | 无 | **丢弃** | owner 2026-09-18 已裁定（`FRAMEWORK-REBUILD.md:722-742`）。**后果**：`_SURFACE_VOICE_RULES` 的三套文案失去自动选择机制——调用方自己选哪一段。迁移工作 |
| `predicate` 门控（per-request，fail-closed） | `layers:735-766`、`policy/conditions.py` 的 11 个谓词 | 无 | **丢弃** | 同上 owner 裁定。**后果**：7 条 predicate-gated 规则（`_PREDICATE_GATED_RULES`，`layers:1029-1088`）失去条件注入，要么全注入要么全不注入。全注入的代价有上界：注释称合并后仍「远低于被删层的 7,800 字符」（`layers:1024-1027`）。**归迁移** |
| predicate 事件上报（`register_predicate_event_sink`） | `layers:676-732` | 无 | **丢弃** | 随特性一起死（`FRAMEWORK-REBUILD.md:733-735` 已把它列为被本裁定关闭的债 #10）。且它依赖 `runtime.tools.hooks`，已删 |
| `load_base_persona` / SOUL.md 注入 | `layers:88-108` | 类比：基础 prompt 硬编码 | **融合** | 能力保留，形式换成 `Section(key="persona", source=text_from_file(SOUL_MD))`。**三级回退**（repo 根 → `$OMICSCLAW_DIR` → 硬编码兜底）**不 port**：回退链属调用方策略。**后果**：SOUL.md 缺失时 persona 段为空，调用方自己兜底 |
| SOUL.md **每次组装都重读磁盘**（无缓存） | `layers:88`、`assembler` 无缓存 | 有（`ltmReader` 每次调用） | **port 语义** | 见 Q2-a。注意旧层的调用方在更高层缓存了（`runtime/agent/loop.py:132` 的模块级 `SYSTEM_PROMPT`）——**那是 bug 的温床**：SOUL.md 改了要重启。新层不缓存，缓存与否留给调用方显式决定 |
| AGENTS.md / CLAUDE.md 注入 | **不存在** | **有**（`builder.go:107-110`） | **新增（port from harness9）** | 已核实：旧仓库全域 grep，`AGENTS.md`/`CLAUDE.md` 只出现在 `autoagent/edit_surface.py` 与 `skill/scaffolder.py`，都不是 prompt 注入。这是 harness9 → 本项目的**净增**，不是 port-back |
| Skills **索引**注入（全量 skill 清单） | **不在 context 层**——在 `omicsclaw` 工具的 description 里（`skill/listing.py` + `skill/domain_briefing.py`） | **有**（`builder.go:113-119`） | **提供槽位，内容不归本层** | 一个 `Section(key="skills_index")` 即可，渲染器仍在 `skill/`。本仓库 96 份 `SKILL.md`（实测 `find skills -name SKILL.md`），正文全放是 token 炸弹。⚠️ **Progressive Disclosure 的负向断言不归本层**：harness9 那条（`builder_test.go:82-85`）之所以有意义，是因为 `builder.go:113-119` 是 **builder 自己**调 `skillsIndex.Summary()`；本层把渲染推到层外（`SectionSource` 返回已渲染文本），于是**没有任何 `omicsclaw/context/` 的改动能让那条断言变红**。它的家跟着渲染器走，归 `skill/`，记入 §11.B-15。本层能被变异杀死的那条性质是「不截断、不改写 source 返回值」——见 Task B 验收 5 |
| 单 skill 上下文预取 `load_skill_context`（含 param_hints、aliases、governed experience、nearby alternatives） | `layers:330-514` | 无 | **丢弃出本层，能力归 `skill/`** | 它读 `omicsclaw.skill.registry`，是 skill 层的知识。本层只提供 `Section` 槽位。**后果**：`skill/evolution_governance.py:4643` 的重校验会断——它 import `load_skill_context` 来断言 gotcha 出现在渲染文本里。**归迁移**：那个函数应当搬进 `omicsclaw/skill/` |
| **skill gotchas 注入**（`## Known pitfalls (from SKILL.md Gotchas)`，ADR 2026-05-11） | `layers:484-512` | 无 | **能力保留，家换成 `skill/`** | 同上。它是 `load_skill_context` 的一个子块。**这条尤其要点名**，因为它有独立测试（`test_skill_context_gotchas_injection.py`,168 行）和 INFO 遥测，是被刻意保护的不变量。**丢在本层 = 丢在迁移的交接缝里**，必须有人接 |
| KnowHow 约束注入（headline-only 懒加载 + 遥测） | `layers:231-289` | 无 | **丢弃出本层，能力归 `knowledge/`** | 依赖 `omicsclaw.knowledge.knowhow` + `.telemetry` |
| 知识库 guidance 预取 + **60** 条 EN/ZH marker 门控 | `layers:517-559`、`:21-82` | 无 | **同上** | 门控是 60 条子串匹配（AST 复核 `_KNOWLEDGE_GUIDANCE_MARKERS`；原稿写 62），属领域知识 |
| `should_prefetch_knowledge_guidance`（「要不要预取知识库 guidance」的判据） | `layers:292-305` | 无 | **丢弃出本层，随上一行一起归 `knowledge/`** | 它就是那 60 条 marker 的消费者（`:303`）。**必须点名**：它是 `omicsclaw/diagnostics.py:30-33` 实际 import 的两个符号之一，删了就是 ImportError（§10.2 那一行）。原稿只裁了「guidance 本身」，没裁「要不要预取」 |
| `should_prefetch_skill_context`（「要不要预取 skill 上下文」的判据） | `layers:306-329` | 无 | **丢弃出本层，随 `load_skill_context` 一起归 `skill/`** | 它读 `request.skill` / `skill_candidates` / `query`。原稿给 `load_skill_context` 判了家（`skill/`），却没给**触发它的判据**判家——迁移时两者必须成对搬，否则会搬出一个「永远预取」或「永远不预取」的版本 |
| `extract_user_text`（多模态 content → 纯文本） | `assembler:205` | 无 | **丢弃出本层** | 它拆的是多模态 content parts，而 `omicsclaw.schema.Message.content` 是 `str`（ADR 0077）——**schema 恢复多模态之前它无事可做**。在 `diagnostics.py:24-29` 的 import 清单里，**归迁移** |
| `should_attach_capability_context`（要不要挂 capability 评估段） | `assembler:139` | 无 | **丢弃出本层，归 `skill/`** | 判据读的是 capability 领域知识。同样在 `diagnostics.py:24-29` 的清单里（§10.2 列了该行，但 §5 原先没裁这两个符号），**归迁移** |
| Extension prompt packs | `layers:888-927` | 无 | **同上，归 `extensions/`** | 也是唯一往 `ContextLayer.metadata` 写东西的层——metadata 随它一起走 |
| `output_format` 层 | `layers/output_format.py`、`layers:1015` | 无 | **提供槽位，渲染器不动** | **后端 `omicsclaw/runtime/output_styles.py` 在工作区里活着**，且是 `runtime/__init__.py` 现在唯一还 re-export 的东西。一个 `Section` 就能接上，**代价最低的一条** |
| MCP instructions（interactive-only，过滤未激活 server） | `layers:182-228` | 无 | **提供槽位，渲染器归 `extensions/`** | 过滤逻辑（`active\|loaded\|connected\|ready`）是 MCP 层知识 |
| workspace context 块（含 `expanduser().resolve()` 归一化） | `layers:141-159` | 类比：`builder.go` 的「工作目录：%s」 | **提供槽位** | ⚠️ **绝对路径进 prompt 是前缀稳定性的破坏源之一**（陷阱 7）。旧层 resolve 了路径，这是对的——但如果路径本身每次不同（临时目录），resolve 也救不了 |
| memory / project_state / scoped_memory 三分（ADR 0024 Decision-2） | `layers:111-140` | 无（LTM 一段全进 system） | ~~port 结构~~ → **丢弃（裁定 0）** | 三分的**全部意义**就是三个不同的 placement（稳定身份→system、工作态→message、查询排序召回→message），placement 一丢它就退化成三个连在一起的 system 段。**照 harness9：长期记忆一段全进 system prompt**（`builder.go:177-187` 的 `ltmReader` 那一块）。组装根仍可自行拆成多个 `Section`，但那是它的排版选择，本层不再有这个概念。内容归第 6 步 |
| surface voice rules 三套文案 | `layers:978-999` | 无 | **提供槽位，文案归调用方** | surface 门控已废，选哪套由调用方决定 |
| 7 条 predicate-gated 规则文案 | `layers:1029-1088` | 无 | **文案保留，门控丢弃**（见上） | 归迁移 |

#### 5.2 `budget.py` —— 预算

> 全模块**零 `omicsclaw.*` import**，只有一个可选 tiktoken guard。
> 这是旧层里**最干净、最该被继承**的一个文件。

| 旧能力 | 出处 | harness9 有无 | 裁决 | 理由 / 后果 |
|---|---|---|---|---|
| tiktoken 优先 + `ceil(chars/4)` 回退 | `budget:140-191` | 无（只有 `字节/4`） | **重新推导的默认估算器 + `TokenCounter` Protocol** | **本行不受裁定 0 影响，理由：(b) 语言级不可直译**——旧层与 harness9 **两边都错**（旧层数码点、harness9 的 `charsPerToken=4` 数字节），见 Q3。这里 port 的是 harness9 的**意图**，不是旧层的实现 |
| 「模型名为空时即使装了 tiktoken 也走回退」的确定性约定 | `budget:153-161` | 无 | ~~port，含理由原文~~ → **不 port 任何机制** | 旧框架独有的一个开关。**但它要保的性质自动成立**：Q3-2 已裁定「本层绝不 import tiktoken」，一个从不 import 它的模块的行为**结构上**不可能因为它碰巧装上了而改变。裁定 0 丢掉的是那段机制与它的原文引用；`tokens.py` 的 docstring 里用自己的话写一句即可 |
| `_TOKEN_ENCODING_CACHE` 模块级缓存 | `budget:150` | 无 | **不 port** | 本层不 import tiktoken，缓存归注入的 counter 自己 |
| 结构化遍历：role + content + tool_calls 各字段 + tool_call_id + reasoning_content | `budget:95-130`、`:194-235` | 有（**缺 reasoning**，`token.go:19-29`） | **数 harness9 的全部字段，外加 `reasoning_content` 与 `name`** | **本行不受裁定 0 影响，理由：(a) 已获 owner 批准的 step 1 schema 偏离。** harness9 缺 `reasoning` 不是设计选择，是它的 schema 里**根本没有这个字段**；本仓库有，而且是 ADR 0077 刻意加的（`FRAMEWORK-REBUILD.md:101-106`）。照抄 harness9 的字段清单 = 对 thinking 模型系统性低估恰好是刻意加进来的那个字段。见 Q3-3 与陷阱 1 |
| 图片 token 会计：`_IMAGE_BUDGET_TOKENS=1300`，**从不 tokenize base64、也从不当 0** | `budget:147`（常量）、`:199-202`（理由）、`:211-212`（加计处） | 无 | ~~记为债~~ → **丢弃（裁定 0）** | 旧框架独有，harness9 无任何图片会计。而且**本层结构上也无处可施**：`omicsclaw.schema.Message.content` 是 `str`，没有多模态 content parts（ADR 0077 刻意排除，`FRAMEWORK-REBUILD.md:108-110`）。⚠️ **后果是真的，必须记住**：`CLAUDE.md` 明写 Channel Surface 接收照片并走组织切片分析；在 schema 恢复多模态之前，**一条图片消息的 token 会被算成 ~0**，预算系统性乐观。**不要为此发明启发式**（陷阱 21）。形态记在 §11.B，不排期 |
| 双估算器（字符 + token）共用一次遍历 | `budget:95` vs `:194` | 无 | **只保留 token 估算器** | 字符版的唯一消费者是 `trim_history_to_budget` 的默认 `size_fn`，而压缩侧一律传 token 版。两个单位并存正是「哪个单位」这类 bug 的来源 |
| `effective_context_capacity(window − reserved_output − safety_margin)` | `budget:26-33` | 无（扁平 80%；真实 benchmark 用 **55%**，`runner.go:293-299`） | **port harness9 的意图，写成显式减法** | **本行不受裁定 0 影响，理由见 Q9 的引用块**：`runner.go:294` 的注释把 55% 拆成「工具定义 (~25K) + 输出预留 + chars/4 估算误差」**三项**——正是本裁决的三个被减数。harness9 是因为**没有这三个数**才只能折成一个比例，不是因为它偏好比例。旧默认 `4096/2048`（`budget:29-30`）；**旧**引擎实际用 `8192/0`（`git show HEAD:omicsclaw/engine/loop.py:239`，其中 `_RESERVED_OUTPUT_TOKENS = 8192` 在同文件 `:196`；注意这是**已 staged 删除的旧引擎**，不是工作区那个新的）——**两处不一致本身就是证据**：这两个数从来没有一个权威来源。新层用 `ModelLimits.output_tokens` 取代拍脑袋，且两个预留字段**不给默认值**（Q9-a） |
| 五档状态 `OK/WARNING/COMPRESS/CRITICAL/BLOCK`（65/80/90/96 %） | `budget:16-57` | 五档 `None/Warn/Soft/Full/Emergency`（60/70/80/95 %） | **全取 harness9 的命名与档位**（裁定 0）；`usable_tokens <= 0 → EMERGENCY` 另有理由 | 两边都是五档，几乎同构；旧层的命名与百分比**整套丢弃**。⚠️ 剩下的 `usable_tokens <= 0 → EMERGENCY`（原先写成「保留旧层 BLOCK 语义」，`budget:46-47`）**不是**在保留旧层：分母从 `ContextWindow` 换成 `usable_tokens` 之后，harness9 的 `ContextWindow<=0 → TierNone`（`:211-213`）那一行**表达的已经是另一件事**（它指「没配预算」，我们用 `ContextBudget \| None` 表达「没配预算」）。**裁决与三行边界见 Q9-b** |
| `local_budget_status`：按**本地压缩预算**而非模型窗口分级 | `budget:60-86` | 无 | **融合进 `ContextBudget`** | 理由（`budget:63-71`）成立且重要：大窗口模型上「相对窗口」永远是 OK，只有相对本地预算才有意义。新设计里 `usable_tokens` 已经是「本地预算」，所以这条**自动成立**，不需要第二个函数。**必须在 docstring 里写明这个等价关系**，否则会被当成能力丢失 |
| 无预算时返回 `None` 而不是误报 BLOCK | `budget:72-73` | 无 | **port 语义，换形状** | 「没配预算」和「爆了」是两件事，wire 上不该混。新形状：`ContextBudget.__post_init__` 拒绝 `context_tokens <= 0`，「没配预算」由调用方持有 `ContextBudget \| None` 表达（Q9-b 第一行）。原稿引的 `:82` 在 `_IMAGE_BUDGET_CHARS` 的注释里 |
| `estimate_prompt_chars` / `estimate_prompt_tokens`（system prompt + messages 一起估） | `compaction:159-183` | 无 | **融合，不另立函数** | token 版由 `estimate_text_tokens(system) + estimate_messages_tokens(messages)` 逐项覆盖；chars 版随「双单位估算器」一起丢（见上一行）。**必须在 `tokens.py` 的 docstring 里写明这个等价关系**，否则会被当成能力丢失——这是本表里第二条「能力自动成立、但不写下来就像丢了」的行（另一条是 `local_budget_status`） |
| `trim_history_to_budget`：**块感知**的最新后缀裁剪，assistant+tool_calls 与其 tool 结果**永不拆开** | `budget:243-314` | 无（靠事后 `repairOrphanedToolPairs` 补） | ~~两边都 port~~ → **只 port harness9（裁定 0）** | 块感知是旧框架独有。改为 harness9 的两步：`fit_to_budget` **逐条剥头**（`compaction.go:95-132`）+ 事后 `repair_tool_pairs`（`:195-239`）。**代价，写明**：被剥掉的 tool_call 的结果会变成孤儿并被删、没有结果的 tool_call 会被塞占位符——**原始内容丢失，旧层的「防止拆开」本来能保住它**。harness9 接受这个代价；本层照办 |
| 「最新的块即使单独超预算也保留」 | `budget:300-304` | 有（`compaction.go:160-169` 的贪心是反过来的：单条超预算就**跳过**） | ~~两条都要~~ → **只要 harness9 的两条（裁定 0）** | harness9 在同一位置上有完整的一对：常规档由 `MinTailMessages` 无条件保住最近 N 条（`compaction.go:110-112`，与预算无关），Emergency 档单条超预算就**跳过**（`:160-169`，Q10）。**旧层的「保最新块」是前者的旧框架版本，丢弃。** 两条 harness9 规则适用档位不同，仍须各有测试 |
| `max_messages=-1` 表示无上限、`0` 表示返回 `[]` 的哨兵 | `budget:265` | 无 | **不 port 哨兵** | `-1`/`0` 双哨兵是 Python 里典型的可读性陷阱。用 `int \| None` |
| 输出/续写预算轴（`TokenBudgetTracker`、`"+500k"` 解析、diminishing returns 三条停止判据） | `budget:317-463` | **无，而且是刻意的** | **正式废弃（owner 裁定 3，2026-09-18）** | **harness9 根本不做 token / 成本预算**，已复核：`grep -rn -iE "price\|pricing\|cost\|usd\|dollar\|spend" internal/ cmd/ --include=*.go` 在 `internal/` 里唯一的 `cost` 是 `compaction.go:164` 的局部变量（指 token 数）；定价字段只在 `cmd/swebench/model_snapshot.go:33,40-41,62-65,106-107,158-159`，是 benchmark 元数据，**不参与任何停止决策**；`"+500k"` 式语法 grep **零命中**。它的停止轴只有三条：`MaxTurns`（默认 500，`agent_loop.go:74`；`options.go:18-21`；判定在 `loop_phases.go:131-134`）、ctx 取消（`:135-140`）、LLM 失败。**替代物是 nudge/gate 家族，属 `omicsclaw/engine/`，不属本层，本步不做**——形态与证据见 §11.B-12 |

#### 5.3 `compaction.py` —— 压缩

| 旧能力 | 出处 | harness9 有无 | 裁决 | 理由 / 后果 |
|---|---|---|---|---|
| 分级递进（snip → micro → collapse → auto，单次调用内全跑） | `compaction:970-1149` | 有（五档，但**单次只走一档**） | **取 harness9 的单档模型** | 旧层每轮无条件跑 snip+micro，**即使完全没有压力**——那与「低压时逐字节 no-op」（陷阱 6）直接冲突，也是前缀缓存的持续伤害。harness9 的 `determineTier` 选一档更干净 |
| `snip_compact`：超 2400 字符的旧消息头尾截断 | `compaction:697-731` | 无（它用 offload） | **丢弃** | 是 offload 的穷人版。**后果**：单条巨型 tool_result 只能靠 Emergency 档的「跳过」兜。第 6 步做了 offload 后这条彻底不需要 |
| **snip 故意不改写 `tool_calls[].arguments`**（F11） | `compaction:697` 注释 | 不适用 | **规则保留（陷阱 17）** | **本行不受裁定 0 影响，理由：(a) 已获 owner 批准的 step 1 schema 偏离。** 这条规则的依据**不是**旧框架，是 `FRAMEWORK-REBUILD.md:98-100`：「**`ToolCall.arguments` stays unparsed JSON text.** Byte-exactness matters for prompt-prefix caching and replay evidence」。旧层的注释只是同一条约束的另一个出处。新层不做 snip，但「绝不截断 `ToolCall.arguments`」仍是硬规则 |
| `micro_compact`：已落盘的 tool 结果换成 5 行引用存根 | `compaction:745-784` | 有（offload，`compaction_offloader.go`） | **丢弃出本层** | 需要 `ToolResultStore`（已删）。归第 6 步的 offload |
| `context_collapse` / `auto_compact` 两级阈值（0.82 / 0.92） | `compaction:85-86` | 有（0.70/0.80） | **融合** | 取 harness9 的四档，见 Q9 |
| `reactive_compact`：真实 413 之后的兜底重压 | `compaction:1033`（触发）、`:1049`（`STAGE_REACTIVE_COMPACT` 追加处；原稿引的 `:1051` 是同一块里的摘要 section 元组）、`query_engine:1415-1472` | 无 | **本层侧无净增；413 检测随裁定 0 丢弃** | 本层交付的 `emergency_fit` **就是 harness9 的 `CompactForce`**（`compaction.go:134-179`），它本来就「无条件、不看阈值」，与 413 无关。旧框架独有的是 **413 的检测与重压编排**（`query_engine:1415-1472`）——裁定 0 下丢弃。⚠️ **代价，必须记住**：harness9 只在估算超阈时压，**估算错了就没有第二次机会**；而本层的估算恰恰未标定（§11.A-8）。这不再是一条「应当早做」的债，是一条**被接受的风险**，形态记在 §11.B |
| 压缩到**目标比例**（而非目标条数），三遍收敛以保「一次压缩 = 一次缓存重热」 | `compaction:581-694` | 无（一遍） | ~~记为债~~ → **正式丢弃（裁定 0）** | 旧框架独有。**而且它的前提在新架构里本来就不成立**：三遍收敛依赖「system prompt 会随摘要一起变」，而本层的 prompt 组装与压缩是分开的两个函数（Q7）。照 harness9 的**一遍**。**后果**：一次压缩后总量仍可能略超目标，需要下一轮再压一次——多一次缓存重热 |
| `<compaction-summary>` / `</compaction-summary>` 成对边界标记，`rfind` 取最外层 | `compaction:35-53` | **有**：`compactionMarker = "[Context Compaction]"`（`anchor.go:42`），仅前缀，无闭合 | ~~port 旧层的成对标记~~ → **照 harness9 的单前缀（裁定 0）** | harness9 在这一位置上**有对应物**，所以按新默认值照它做：`COMPACTION_MARKER = "[Context Compaction]"`，`is_summary_message` 就是 `content.startswith(MARKER)`。⚠️ **代价，写明**：单前缀**不能**安全嵌套与重入——旧层的成对标记配 `rfind` 能取到最外层闭合，那是 CodePilot bug #7 的修复（`test_compact_boundary.py`,186 行专门钉它）。harness9 不需要，因为它**每次只保一份 `lastSummary`**（见下一行）且压缩消息永远在 `msgs[0]` 之后的固定位置。**本层照办的前提就是这个形状；实现者若引入多份摘要共存，本行必须重新评估** |
| `/compact` 反向边界扫描 + **上一份摘要逐字节带过来**，只压边界之后的 | `builtins.py:110-124` | 有（增量模板，`progressive_compactor.go:407-413`） | **只取 harness9 的增量模板（裁定 0）** | 两边都在解「别把摘要再摘要一遍」。**取 harness9 的增量模板**（`state.summary` 非空 → 走 `INCREMENTAL_TEMPLATE`，把上一份摘要 + 锚点交给 LLM 合并）。**旧层的「逐字带过」降级路径丢弃**——`summarizer is None` 时照 harness9 走 `fit_to_budget`（等价于它的 `TokenBudgetCompactor` 回退），不产摘要 |
| 摘要 block 累积 + 按 token 上限保新丢旧 + `_SUMMARY_ELISION_MARKER`，且**幂等** | `compaction:241-294` | 无（只保一份 `lastSummary`） | ~~port~~ → **丢弃（裁定 0）** | 旧框架独有。照 harness9：`CompactionState.summary` 只有**一份**，下一次压缩由增量模板让 LLM 合并（`progressive_compactor.go:482-486` 的 `updateLastState`）。于是 `bound_summary_blocks` 及其幂等要求整条消失。**后果**：多轮压缩的信息损失由 LLM 的合并质量兜底，而不是由一个确定性的「保新丢旧」上限兜底 |
| LLM 摘要的 **6 道拒收闸** | `compaction:506-578`（`_looks_like_tool_invocation` 在 `:408`、`_drops_required_tokens` 在 `:491`） | **无（一道都没有）** | ~~port~~ → **丢弃（裁定 0）** | 旧框架独有。已逐行复核 harness9：`progressive_compactor.go:423-431` 拿到 `resp` 只检查 `err != nil` 与 `resp == nil`，然后 `:431` **无条件** `ParseAnchorsAndSummary(resp.Content)`。丢掉的是：① 空；② token 数超模板（主闸，ADR 0039）；③ 字符数超模板；④ UTF-8 字节数超模板；⑤ 形似工具调用；⑥ **内容保真闸** `_drops_required_tokens`（从模板抽出文件路径与 `Error/Traceback/TODO` 标记，摘要里少了任何一个就拒收）。⚠️ **后果，必须写明**：在一个跑 omics 分析的 Agent 上，**压缩之后可能就找不到那个 `h5ad` 路径了**，而且没有任何机制会发现——②和⑥ 正是为这件事存在的。**但 harness9 不是零防护**：`progressive_compactor.go:488-495` 的「摘要失败 → 回退截断 + 记 `Error`」保留（陷阱 12），`:341-352` 的 `tierEmergency` 保留。**唯一的防线因此从「内容闸」变成「降级路径」**，见陷阱 19 的改写 |
| 反模仿：**确定性模板摘要**里的历史工具调用渲染成 `<prior-tool-calls names="…"/>` XML 自闭合标签 | `compaction:787-812` 的 `_message_preview`，链路 `_build_collapse_summary:854` → `_collect_role_highlights:829-852` → `_message_preview:787`，标签在 `:812` | harness9 的**模板路径不存在**，所以这一位置上**无对照物** | ~~port~~ → **丢弃整条路径（裁定 0）** | 旧框架独有，而且它**依附于**下一行那条同样被丢弃的「确定性模板摘要」——模板没了，模板里的渲染器自然无处可施。⚠️ `:798-802` 的实测理由（「Claude/DeepSeek 把结构化标签当元数据不会复述；散文形式会触发 few-shot 模仿」）**仍然为真**，它只是在新架构里**没有适用对象**了：本层唯一的渲染器 `render_for_summary` 产出的文本**只喂给摘要 LLM，不回到模型视野**。`test_compaction_tool_call_rendering.py`(125 行) 随之作废。陷阱 20 已按此重写 |
| 摘要**素材**（喂给 LLM 的那份）里的历史工具调用渲染 | `compaction:359-383` 的 `_render_omitted_for_summary`，渲染成 `[called tools: a, b]`（`:379`） | **有**：`progressive_compactor.go:391-404` | ~~port 旧层的散文形式~~ → **照 harness9 逐行 port（裁定 0）** | 同一位置上两边都是散文，差别只在字面——所以按新默认值取 harness9 的字面：`[tool_result <id>]: <content>` / `[<role>]: <content>` / `[tool_call <name>(<id>)]: <args>`，`"\n"` 连接。已核实 `:391-404` **全程不截断任何一行**，本层照办（截断留给 `fit_to_budget`，不留给渲染器） |
| 确定性模板摘要（不调 LLM 也能产出结构化摘要） | `compaction:854-903` | **无**（`summarizer` 缺席时走强制截断） | ~~port~~ → **丢弃（裁定 0）** | 旧框架独有。它原先的两个用途一并消失：作 6 道闸的上界参照物（闸已丢），与作 `summarizer is None` 时的产物。**harness9 的两条替代物是**：`tierEmergency`（`progressive_compactor.go:341-352`，跳过 LLM 直接强制截断）与 `TokenBudgetCompactor`（`compaction.go:95-132` 的逐条剥头）。**本层的对应物是 `emergency_fit` 与 `fit_to_budget`，两者已在交付清单里**——所以这一行丢的是「结构化摘要」这个**产物形态**，不是「没有 LLM 时怎么办」这个**能力** |
| 摘要里的附件标记折叠成 `[attachment]` | `compaction:73-74` | 无 | **丢弃** | 依赖 `[[OMICSCLAW_ATTACHMENT_V1:` 这个旧格式。**后果**：附件标记会原样进摘要。归迁移 |
| `_truncate_text` 头 70% / 尾 30% + `[label: omitted N chars]` 尾注 | `compaction:201-226`（调用点 `:716`/`:804`/`:819`） | **无**（`progressive_compactor.go:391-404` 全程不截断） | ~~融合，比例统一~~ → **丢弃（裁定 0）** | 旧框架独有，而且**它的三个调用点全在已被丢弃的路径上**（snip、`_message_preview`、`_collect_role_highlights`）。裁定 0 之后本层**没有任何消费者**需要一个头尾比例：`render_for_summary` 照 harness9 不截断，超预算由 `fit_to_budget` 整条剥、由 `emergency_fit` 整条跳过。**`omicsclaw/tools/` 的头 1/3 尾 2/3 一个字不动**（§9-4「例外：零」）。陷阱 18 已按此重写 |
| `CompactionEvent` + `build_compaction_status_payload`（wire 形状、三种文案变体、`budgetStatus` 仅在非 None 时出现） | `compaction:1152-1225` | 有（`EventCompaction` + `CompactionRecord`） | **值对象 port，事件丢弃** | `CompactionRecord` 留在本层；**事件类型要改 `EngineEventType`，越界**（Q7）。wire payload 的渲染属 Surface。**后果**：`surfaces/desktop/_compaction_event_bridge.py` 与它的 5 条测试没有对口，**归迁移** |
| 「触发压缩的是**压缩前**的压力，不是压缩后被压平的那个」（D1a） | `query_engine:1466-1469` | 有（`CompactionRecord.TokensBefore`） | **port** | `CompactionRecord` 同时带前后两个数，让消费者自己选。这条容易被实现成只报压缩后 |
| 持久化门控：只有真的 collapse/auto/reactive 触发才重写 transcript | `query_engine:733-761` | 有（`history.go:117-133` 三条门控） | **丢弃出本层** | 需要 Session，归第 6 步（§11.A-2） |
| `protected_tail_messages=4` / `micro_keep_recent_tool_messages=1` 两种锚 | `compaction:83-84` | `MinTailMessages=6`（`compaction.go:87-92`；真实 benchmark 用 **8**，`runner.go:293-299`） | **一个 `min_tail`，取 harness9 的 6 为默认（裁定 0）** | 两个不同的尾部保护数是旧层 snip/micro 两档各自的产物；本层只有一档压缩。**不再有「`6` 与 `4` 之间取哪个」的问题**——旧层的 `4` 随裁定 0 丢弃，取 `6`。⚠️ `6` 与 `8` 都是 harness9 的**借来字面量**，按陷阱 1 须在本仓库语料上重验（§9-8） |
| **tier-1 闸：省略集 < 8 条就不付 LLM 往返**（`_should_refine_episode`） | `compaction:386-398`（判据）、`:122`（`llm_summary_min_omitted`）、`:683-684`（调用点） | **无** | ~~port 为能力~~ → **丢弃（裁定 0），`min_omitted_for_summary` 参数一并删除** | 旧框架独有。已在 harness9 全栈复核过**确实没有对应物**：`determineTier`(`:209-228`) 只看比例、`splitHeadTail`(`:233-245`) 只看 `len(rest) <= minTail`、`summarizeAndExtract`(`:386-436`) 拿到 head 就调。**唯一的结构性守卫是「head 为空就不压」**（`:235-243` 返回 nil head，调用方跳过整档），那条已由 `min_tail` + 陷阱 11 覆盖。**代价**：省略集只有 3 条时也会付一次 LLM 往返。harness9 接受它（`SoftThreshold=0.70` 触发时 head 本来就不会小）。§9-8 的字面量清单已删 `llm_summary_min_omitted=8` |
| 摘要 LLM 调用的 **20 秒超时** | `compaction:122`（`llm_summary_timeout_s = 20.0`）、`:528`/`:538`（`asyncio.wait_for`） | 有（60 秒，`summarization.go:216-220`、`progressive_compactor.go:420`） | **两个数字都不搬，超时归调用方** | **本行不受裁定 0 影响，理由：(b) 语言级不可直译。** harness9 埋 60s 的理由是它自己写的——`Compact` 接口不传外层 context，压缩器**感知不到取消**。Python 里这个前提不存在：本层的 `compact()` **是** async 的，取消经 `await` 自然传播。把超时埋进纯变换里既测不了也改不了。（旧层也埋了 20s，同样丢弃——两边都丢，所以这不是在偏袒任何一方。）两条义务不变：① `compact()` 的 docstring 写明**本层不设超时**，一个永不返回的 summarizer 会让 `compact()` 永不返回，调用方必须自己套 `asyncio.timeout`；② 一条点名测试：永远 pending 的 summarizer 在调用方的 `asyncio.timeout` 下被取消时，`CancelledError` **原样传播**（陷阱 12），且遵守陷阱 4 的「恢复后再 await 一次」 |
| **无任何用户可控的 pin/anchor** | 事实陈述 | 同（也无） | **保持无** | 两边都没有。记下来免得被当成漏项 |

#### 5.4 `assembler.py` / `system_prompt.py`

| 旧能力 | 出处 | harness9 有无 | 裁决 | 理由 / 后果 |
|---|---|---|---|---|
| `assemble_prompt_context`（20 行：遍历 → applies → render → 排序） | `assembler:308-328` | 有（`Build()`） | **port** | 干净，直接对应 `PromptAssembler.render()` |
| `assemble_chat_context`（async，扇出到 5 个子系统 + 后台任务注册表 + 全部 fail-open） | `assembler:331-600` | 无 | **丢弃出本层** | 它 import `skill.capability_resolver`、`skill.evolution_governance`、`memory.scoped_memory_select`、`extensions`、`runtime.agent.session`——**五个都在本层的禁区外**。这是**编排**，家在 Surface / 组装根。**后果**：并发预取、F9 后台任务取消与回收、研究立场加载等全部没家。**这是本表里最大的一块「归迁移」**，必须点名 |
| F9 后台任务取消与回收（happy path 不加 await 点） | `assembler:361-368`、`:588-600` | 无 | **同上** | 有两条专门测试（`test_context_assembler.py:934,975`） |
| `build_system_prompt(...)` 25 个关键字参数的门面 | `system_prompt.py:13-38`（`def` 在 `:13`；原稿引的 `:34` 只是 `mcp_servers` 一个参数） | 无 | **丢弃** | 它只是 `ContextAssemblyRequest` 的适配器，随那个请求对象一起走。**后果**：`omicsclaw/agents/prompts.py:12` 会断，**归迁移** |
| `PromptContextAssembly.total_estimated_tokens` / `total_chars` | `assembler:86-92` | 无 | **port token 版，丢 chars 版** | token 版落到 `AssembledPrompt` 上一个汇总属性（`section_stats` 已给逐段值）；chars 版随「双单位估算器」一起丢（§5.2）。**点名消费者**：`omicsclaw/diagnostics.py:1473-1489` 的 `ContextReport` 既读 `total_estimated_tokens`（与阈值比较发警告），也读 `layer.cost_chars` 与 `layer.metadata`——后两者本表已判丢弃，所以 `ContextReport` 必须重写而不是改个 import，**归迁移**（§10.2 已列 `diagnostics.py`） |
| 多模态 user content：Anthropic `image` block → OpenAI `image_url` data-URI 转换 | `assembler:215-250` | 无 | **丢弃出本层** | ① schema 没有多模态 content parts；② **即使有，格式转换也是 provider 适配器的活**，不是组装层的——`omicsclaw/provider/` 里已经有 `encode_conversation` 干这件事。**后果**：Channel Surface 的照片路径没家，**归迁移 + schema 债**（§11） |
| 持久化孪生 `build_stored_user_message_content`（同样加前缀，**不**做 block 转换） | `assembler:253-272` | 无 | **丢弃** | 随上一条走。它的存在本身证明「转换属 wire 边界」 |
| `"## User Request"` 标题 | `assembler:229` | 无 | ~~port~~ → **丢弃（裁定 0）** | 旧框架独有。**而且它存在的唯一理由随 Q5b 一起消失了**：它是用来把 `message_context` 与用户这句话分隔开的，而 `message_context` 已经不存在。裁定 0 之后 `assemble()` 的 user 轮内容**逐字节就是 `user_text`**，不加任何前缀或包装（§3.2） |
| 域关键词 / skill 别名 / 文件扩展名 的 hint 抽取 | `assembler:20-49`、`:129-202` | 无 | **丢弃出本层** | 它读 skill registry，是路由知识（`omicsclaw/routing/` 或 `skill/`）。**归迁移** |
| **无任何缓存 / memoisation** | `assembler` 全文 | 同 | **保持无** | 两边一致；缓存由调用方显式决定（见 5.1 SOUL.md 一行） |
| `cache_control` 断点注入 | **不在本层**（在 `providers/models.py:325`） | 不适用 | **不做** | 新 provider 层已有（`openai_provider.py:212-281`）。⚠️ **裁定 0 之后本层对前缀缓存的贡献只剩「字节稳定」一半**：placement 拆分已丢弃，易变段进 system prompt ⇒ 每次变动打断前缀。代价表见 Q5b。本层能保证的是「输入不变 ⇒ 输出逐字节不变」（陷阱 7），保证不了「输入常常不变」 |

#### 5.5 结论行

> **裁定 0（2026-09-18）之后，这三段全部重写过。** 旧框架独有的能力
> 已从第一段整体移入第二段；第一段现在只剩「harness9 有对应物」与
> 「(a)(b)(c) 三类边界」两种来源。

**本层实际交付的能力**（按来源标注）：
- **照 harness9**：单一 system prompt 的分段组装、空段消失、
  加入顺序渲染、预算模型与五档压力（分母换成显式减法，Q9）、
  逐条剥头裁剪 + 事后工具对修复、Emergency 任务锚与巨型条跳过、
  锚点解析/合并、首次/增量两个摘要模板、单前缀边界标记
  `[Context Compaction]`、摘要素材渲染、`CompactionRecord`、
  摘要失败 → 回退截断 + 记原因。
- **边界 (a)（已批准的 step 1 schema 偏离）**：token 估算数
  `reasoning_content` 与 `name`；占位 `tool` 消息用 `Message.tool(...)`；
  `ToolCall.arguments` 逐字节不动。
- **边界 (b)（语言级不可直译）**：token 口径重新推导（字节 vs 码点）；
  超时归调用方而非埋进压缩器。
- **边界 (c)（本层叶子性）**：全部外来输入走 Protocol / 可调用对象；
  `Summarizer` 签名不与 `LLMProvider` 同形；不 import `provider`、
  不持有 clock。

**随裁定 0 丢弃的旧框架独有能力**（每条的代价已写在 §5 对应行）：
system/message 双 placement、`(order, key)` 全局排序、
memory/project_state/scoped_memory 三分、`## User Request` 标题、
块感知裁剪、「最新块超预算也保留」、图片 token 会计、
tiktoken 确定性开关、成对边界标记与 `rfind`、摘要 block 累积与幂等上限、
**6 道拒收闸**（含内容保真闸）、**确定性模板摘要**、
**反模仿 `<prior-tool-calls/>` 渲染**、旧层的散文素材渲染、
**tier-1 小省略集闸**（`min_omitted_for_summary` 参数一并删除）、
三遍收敛、`_truncate_text` 的 70/30、`/compact` 的逐字带过降级路径、
413 反应式重压的检测编排、输出/续写预算轴（裁定 3）。

**此前已明确丢弃、与裁定 0 无关**：surface 门控、predicate 门控与其
事件、`attachment` placement、27 字段请求对象、双单位估算器（含
`estimate_prompt_chars`）、`-1/0` 哨兵、snip、micro、附件标记折叠、
多模态转换、埋在压缩器内部的摘要超时。

**能力保留但家在别处**（= 跨组件工作。⚠️ **按 owner 2026-09-18 的范围
约束，这一整段等完整 agent 架构就绪后再议**，不是本步的前置条件，也不
排期——形态记在 §11.B）：skill context **与它的预取判据
`should_prefetch_skill_context`**、**gotchas 注入**、KnowHow、
知识库 guidance **与它的预取判据 `should_prefetch_knowledge_guidance`**、
prompt packs、output_format、MCP instructions、hint 抽取、
`extract_user_text` / `should_attach_capability_context`、
Progressive Disclosure 负向断言、`assemble_chat_context` 的扇出编排、
压缩事件的 wire 渲染、`progress_policy` 的 `analysis` 判据。

> **两项已从本段移出，因为它们被裁定 0 正式废弃而不是「换个家」**：
> 输出/续写预算轴（裁定 3；harness9 的替代物是 nudge/gate 家族，属
> engine）、413 反应式重压的检测编排（§5.3）。图片 token 会计同样已
> 改判为丢弃（§5.2），不再记作「被 schema 挡住」。

---

## 6. 陷阱清单

每一条都要有点名回归测试，且**每条经变异验证**（改坏 → 点名测试变红 →
还原 → 字节一致）。变异跑必须带 `-rfE --continue-on-collection-errors`，
并在 pytest 外再套一层 OS 级 `timeout --signal=KILL`。

1. **从 Go 借来的字面量必须在 Python 重新验证**（第 3 步的教训，
   `FRAMEWORK-REBUILD.md:210-216`）。本层有三个一等靶子：
   - `charsPerToken = 4` 作用在 Go 的**字节**长度上（Q3）。直译成
     `len(text)//4` 对中文低估 2–3 倍，而本仓库的 prompt 是中文。
   - `token.go:19-29` 的**字段清单**没有 `reasoning_content`，因为
     harness9 的 schema 没这个字段。照抄 = 对 thinking 模型系统性低估
     ADR 0077 刻意加的那个字段。
   - `compaction.go:229-233` 的占位消息角色是 `RoleUser`，因为
     harness9 只有三个角色。照抄在本项目**功能上失效**（Q11）。
   测试要求：三条各一个点名测试；第二、三条的测试必须断言**行为**
   （token 数随 reasoning 增长；占位消息被 Anthropic 编码成
   `tool_result` block），不是断言字段名。

2. **「有测试」不等于「接上了」；预算类判断必须往收紧方向钉**
   （第 4 步的教训，`FRAMEWORK-REBUILD.md:282-288`）。本层的形态：
   - 「历史超预算就压缩」这条测试，在一个**永远压缩**的实现下照样绿。
     必须**成对**：低于阈值时**真 no-op**（可测形式见陷阱 6，
     **不是**「`result is messages`，或至少 `==`」——入参类型是
     `Sequence[Message]`、返回类型是 `tuple`，调用方大概率传 `list`，
     于是 `result is messages` **永不成立**，剩下的 `==` 是内容相等，
     而「总是重建列表」恰好满足它，退路等于没有），且高于阈值时
     **压完真的装得下**
     （`estimate_messages_tokens(result) <= budget.usable_tokens`）。
   - 档位判定必须每档一个点名测试**且**测边界的两侧（`ratio` 恰好
     等于阈值走哪档），因为 `>=` 写成 `>` 不会让任何一个「中间值」
     测试变红。**边界清单必须包含 Q9-b 的两条**：
     `context_tokens <= 0` → 构造期 `ValueError`；
     `usable_tokens <= 0`（预留吃光窗口）→ `Pressure.EMERGENCY` 且
     `plan_compaction` 真的走 emergency 路径（不是返回 `NONE` 档）。
   - `ContextBudget.usable_tokens` 减法写错方向（加成减）在一个只测
     「大历史被压」的套件里完全不可见。必须有一条测试断言
     `usable_tokens < context_tokens`。**但这一条挡不住 `0/0`**：
     所以还要一条 `ContextBudget(context_tokens=200_000)` 必须
     `TypeError`（两个预留字段无默认值，Q9-a），以及一条
     `measure()` 在 `budget.reserve_tool_tokens` 报低于实测
     `tool_tokens` 时按**实测值**扣减、并把差额写进
     `BudgetReport.tool_reserve_shortfall`（§3.2 的接缝注释）。

3. **缺陷聚集在 lane 之间的接缝**（第 3、4 步的共同教训；
   `FRAMEWORK-REBUILD.md:809-811`：「Seven of step 4's nine repaired
   defects sat between lanes」）。本层的接缝有四处，**每一处都在 §7
   点名了负责人**——原稿里有两处无人认领，已补：

   | 接缝 | 负责人 | 跨包例外 |
   |---|---|---|
   | `tokens.py` 的估算口径 ↔ `budget.py` 的档位分母 | **Task A**（接缝责任，见 §7） | 无 |
   | `budget.py` 的 `Pressure` ↔ `compaction.py` 的 `plan_compaction` | **Task C**（接缝责任 ③，本轮补） | 无 |
   | `transcript.py` 的 `repair_tool_pairs` ↔ 两个 provider 适配器的编码分派（Q11） | **Task C**（接缝责任 ①） | **有**：陷阱 10 授权 `tests/context/` import `provider` |
   | `prompt.py` 的输出 ↔ `apply_cache_breakpoints` 的断点位置（Q5） | **Task B**（接缝责任 ②，本轮补） | **有**：同一条例外，本轮扩到这一处——理由同样是「断言在层外，实现不许 import」 |

   > 后两行原稿都没有归属。第四行尤其要紧：陷阱 10 专门为跨包断言开了
   > 例外，而这一条**同样跨包**（`openai_provider.py:212-281` 的
   > `_mark_last_system_message` 在 `:212`），却既没例外授权也没负责人。

4. **给 deadline 写测试必须在恢复后真的再 `await` 一次**
   （并行工具调用那一轮的教训，`FRAMEWORK-REBUILD.md:578-587`）：
   `asyncio.Timeout` 只在 `await` 处触发，`__aexit__` 出门时会取消它的
   handler——**一个在超时窗口关闭瞬间就返回的协程，观察不到任何被恢复
   到过去的 deadline**。本层的形态：`compact()` 是本层唯一的 async
   函数，任何围绕 `summarizer` 的取消/超时测试，必须在 summarizer
   返回之后再 `await asyncio.sleep(0)` 一次，否则测的是「什么都没发生」。

5. **压缩绝不能改到调用方的列表。** harness9 踩过（issue #117 的别名
   bug，`progressive_compactor.go:354-360` 专门加了防御性拷贝）。
   Python 里 `Message` 是 frozen，改不了单条，但**列表别名仍然在**：
   返回输入列表的切片，调用方 `.append` 一下就串了。
   **裁决：本层所有返回值都是 `tuple`。** 测试：压缩后对原
   `list` 追加，断言返回值长度不变。

6. **`plan_compaction` 在低压时必须是真 no-op——而「真 no-op」要写成
   可测的形状。** 原稿写的是「返回同一个对象或逐字节相等」，那与陷阱 5
   （「本层所有返回值都是 `tuple`」）**互斥**：入参是 `Sequence[Message]`，
   调用方传 `list`，返回 `tuple` ⇒ 容器恒等在设计上不可能成立。
   **裁决：保陷阱 5（别名安全优先），把不变量改写成两条断言。**
   - **元素恒等**：`all(a is b for a, b in zip(result, messages))` 且
     `len(result) == len(messages)`。没有任何一条 `Message` 被重建或
     改写。对 `plan_compaction` 的形式是
     `plan.pressure is Pressure.NONE and not plan.needs_summary and
     plan.head == ()`，且 `plan.pinned + plan.tail` 元素级 `is` 于入参。
   - **前缀字节恒等**：把低压前后的 `result` 分别交给
     `assemble(...)`，两次产出的 system prompt 与前 N 条消息的
     `content` **逐字节相同**。
   > 容器（`tuple`）每次新建是**允许且必要**的——陷阱 5 的别名防护正是
   > 靠它。前缀缓存付费的是**字节**，不是对象身份；说「重建列表是灾难」
   > 混淆了这两件事。真正的灾难是字节漂移，见陷阱 7。
   变异：在低压路径上对任意一条 `Message` 做
   `dataclasses.replace(m, content=m.content)`（内容相同、对象不同），
   元素恒等那条必须变红。

7. **prompt 的字节稳定性有四个隐蔽的破坏源。** 必须有一条
   「同一天内连续两次 `render()` 逐字节相等」的测试，以及一条
   「只改一个 section，其余段落逐字节不变」的测试。四个源：
   - `set` / `frozenset` 迭代顺序 —— **`ToolPolicy.tags` 就是
     `frozenset`**（`tools/base.py:217`）。任何按 tag 渲染的东西必须
     先排序。
   - **段的顺序**。裁定 0 丢掉了 `(order, key)` 排序键，改为
     `with_section` 的**加入顺序**（§5.1）。加入顺序同样是确定的，
     但它现在由**组装根**负责——一条「同一组 Section 以同一顺序
     `with_section` 两次，`render()` 逐字节相等」的测试仍然有效，
     而「组装根换了顺序」不再是本层能防的事。
   - `dict` 顺序（Python 3.7+ 保序，但 `json.dumps` 的 `sort_keys`
     默认是 `False`）。
   - 时间。**本层不读时钟**（Q2-d）——日期由组装根的 `SectionSource`
     闭包提供，所以这一源在本层的形态是「不许引入」而不是「必须可注入」。
     测法与变异见 Task B 验收 3。
   - 绝对路径（`tempfile` 目录名每次不同）进 prompt。
   变异：把某处 `sorted(...)` 去掉，点名测试必须变红。

8. **不许要求 `messages[0].role == SYSTEM`**（Q8）。变异：把
   `pinned` 参数写死成「首条必须是 system，否则原样返回」，
   点名测试（一个没有 system 消息的超预算对话必须仍被压缩）必须变红。

9. **Emergency 档丢任务锚 = 143 轮死循环**（Q10）。点名测试：构造一个
   「首条 user 任务 + 一条巨型 tool_result + 若干小消息」的历史，
   断言压缩后**首条任务消息仍在**，且巨型那条**被整条跳过而不是被
   截断**。

10. **`repair_tool_pairs` 的两个方向都要测，而且要测「补出来的那条
    真的被适配器认作 tool_result」**（Q11）。后半句是跨包断言，而
    本层不许 import `provider`——**裁决：这条断言写在
    `tests/context/` 里，测试文件可以 import `provider`**（测试不受
    分层守卫约束，守卫只扫 `omicsclaw/context/` 的源码）。必须在测试的
    docstring 里写明理由。
    **这条例外覆盖两处跨包断言，不止一处**（陷阱 3 的表）：
    - `repair_tool_pairs` 补出的占位消息 → `anthropic_provider.py:270-284`
      的 `encode_conversation` 必须把它编成 `tool_result` block；
    - `assemble()` 的产出 → `openai_provider.py` 的
      `apply_cache_breakpoints`（`:252`）经 `_mark_last_system_message`
      （`:212`）打出的断点必须落在**第 0 条**上，且**不随 section 数量
      变化而漂移**（Q5 的附带收益，原稿只写了结论没写断言）。
    这是本计划里仅有的、测试比实现宽的地方。

11. **`min_tail` 与 `pinned` 相加超过消息总数时的行为要定义。**
    harness9 用 `len(rest) <= minTail → 原样返回`
    （`compaction.go:110-112`）。在我们放宽了 `pinned` 之后，
    `pinned + min_tail > len(messages)` 是新的可达状态。必须有明确
    行为（建议：原样返回并在 record 里标 `degraded`），且有测试。

12. **摘要失败必须降级，不能抛。** `summarization.go:122-125` 与
    `progressive_compactor.go:280-283` 都是失败即回退到截断。我们的
    `compact()` 里，`summarizer` 抛任何异常（含超时）都必须落到
    `fit_to_budget`，并在 `CompactionRecord.degraded` 里写原因。
    **但 `asyncio.CancelledError` 必须原样传播**——这是 0027 定下的
    规矩（`FRAMEWORK-REBUILD.md:187-190`：「`CancelledError`
    propagates untouched」），而 `except Exception` 在 3.8+ 已经不捕
    它，所以真正的风险是有人写 `except BaseException` 或裸 `except`。
    变异：把 `except Exception` 改成裸 `except`，必须有一条测试变红。

13. **锚点解析器不能对格式跑偏的 LLM 输出抛异常。**
    `anchor.go:47-100` 的解析是纯扫描，缺失段填 `"N/A"`，永远返回
    5 条。模型不听话是常态，不是异常。测试：空串、只有 `## Summary`、
    标题拼错、锚点段里混了 `###` 子标题——四种输入都必须返回 5 条锚点
    且不抛。

14. **`Anchors.merge` 的 `"N/A"` 语义**：`anchor.go:105-124`，新值里
    的 `"N/A"` **不覆盖**旧值（视为缺失）。直译容易写反。测试两个
    方向各一条。

15. **别把 Go 的形状当成逻辑搬过来。**
    `FRAMEWORK-REBUILD.md:441-448` 第 7 条「Dead code ported from Go」
    的类别，本层的候选：
    - `token.go:49-58` 的三分支 switch（写成 Python 的三个 `if` 没问题，
      写成 `match` 只是模仿）。
    - `maxTokens()` / `minTail()` 那种「<=0 就用默认值」的 getter
      （`compaction.go:181-193`）——Go 的零值语义产物。Python 用
      dataclass 默认值即可，**不要**在每个 getter 里再兜一次底；
      兜底分支在 Python 里永远不可达，正好是死代码。
    - `record.FillDefaults()`（`record_store.go:52-59`）——
      Python 的 `__post_init__` 或干脆在构造时算好。
    要求：实现者交付时**逐条声明**哪些 Go 结构被有意丢弃。

16. **`git status` 的验收判据不能照抄 0029。** 0029 §10-3 写的是
    「只许出现 `??`」。**在当前工作区这已经不成立**：有 320 条 `D `
    与若干 ` M `。必须改成**快照 diff**，见 §9-3。

17. **`ToolCall.arguments` 在任何压缩路径上都不得被截断或重写。**
    旧层为此写了 F11（`compaction.py:697` 注释）：截断 JSON 参数会产出
    **无效参数且每轮重发**，若同轮还发生了 collapse 就会被持久化。
    本层不做 snip，但 `render_for_summary` 会把 arguments 渲染进摘要
    文本——**渲染进文本可以截断，改写消息里的 `ToolCall` 不可以**。
    ADR 0077 明确要求 `arguments` 保持未解析的 JSON 文本、逐字节一致
    （前缀缓存与回放证据都依赖它）。
    点名测试：压缩前后，所有幸存 `Message` 的 `tool_calls` 逐字节相等。
    变异：在某处对 `arguments` 做 `[:200]`，测试必须变红。

18. **本层的任何渲染器都不得截断——截断只能发生在「整条纳入 / 整条
    剥掉」这个粒度上。**

    > **裁定 0 改写。** 原条讨论的是「两个头尾比例（旧层 70/30 vs
    > `bash.py` 的 1/3–2/3）该不该统一」，裁决是「各留各的」。
    > **那个问题随裁定 0 消失了**：70/30 的三个调用点
    > （snip、`_message_preview`、`_collect_role_highlights`）全在被丢弃
    > 的路径上，本层**已经没有任何消费者需要一个头尾比例**（§5.3）。

    正面规则，照 harness9：`progressive_compactor.go:391-404` 的摘要素材
    渲染**全程不截断任何一行**（已逐行核实）；容量问题由
    `fit_to_budget` **整条剥头**（`compaction.go:95-132`）与
    `emergency_fit` **整条跳过**（`:160-169`）解决。
    **点名测试**：构造一条 50,000 字符的 tool 消息，
    `render_for_summary` 的输出必须**包含它的全部内容**。
    变异：在渲染器里加一个 `[:2000]`，这条必须变红。
    **`omicsclaw/tools/` 的 1/3–2/3 一个字不动**（§9-4「例外：零」）——
    它是 `bash.py:243-257` 针对命令输出重新推导过的
    （`FRAMEWORK-REBUILD.md:379-381` 列在「Literals re-verified rather
    than pasted」里），与本层无关。

19. **摘要内容不再有任何闸，所以降级路径是唯一的防线——它必须真的
    兜得住，而且必须留下痕迹。**

    > **裁定 0 改写。** 原条要求「6 道拒收闸每道各一条点名测试」。
    > **6 道闸已随裁定 0 整体丢弃**（§5.3）：harness9
    > `progressive_compactor.go:423-431` 只检查 `err != nil` 与
    > `resp == nil`，然后 `:431` **无条件**解析 LLM 输出。
    > **代价已在 §5.3 写明**：一个丢掉 `h5ad` 路径的摘要不会被任何机制
    >拦下。既然内容闸没了，剩下的两条防线就必须钉死。

    **防线一——降级必然发生且必然被记录**（harness9
    `progressive_compactor.go:488-495` 的 `fallbackCompact`：回退截断
    **并且**写 `Error` 字段）：
    `summarizer` 为 `None` / 抛异常 / 返回空串 / 返回格式跑偏的文本，
    四种都必须落到 `fit_to_budget` 并在 `CompactionRecord.degraded` 里
    写**非空**原因。变异：把 `degraded` 的赋值删掉（行为不变，只是不记），
    必须有一条测试变红——**一个不留痕迹的降级等于静默失效**。

    **防线二——`tierEmergency` 不经 LLM**（`:341-352`）：
    Emergency 档**必须**跳过 summarizer 直接强制截断。变异：让
    Emergency 档也去 `await summarizer`，点名测试（用一个会记调用次数的
    假 summarizer，断言 Emergency 档调用次数为 0）必须变红。

    **不许自行发明替代闸。** 「摘要比模板长就拒」这类判据需要一个模板，
    而模板路径已经不存在（§5.3）；凭空造一个上界参照物等于把被裁掉的
    路径偷偷加回来。

20. **本层只有一个渲染器，它的输出只喂给摘要 LLM、绝不回到模型视野
    ——这条性质一旦被破坏，整条反模仿论证就会以最坏的方式重新变得相关。**

    > **裁定 0 改写。** 原条（以及修复轮对它的更正）讨论的是
    > `<prior-tool-calls names="…"/>` 该挂在哪个渲染器上。
    > **两个渲染器现在只剩一个**：`summary.render_message_preview` 与它
    > 服务的确定性模板摘要已随裁定 0 整体丢弃（§5.3），
    > `transcript.render_for_summary` 改为逐行照搬 harness9。
    > 原更正的事实判断仍然成立，只是不再有实践后果，存档见附录 C.2。

    **正面要求**：
    - `transcript.render_for_summary` **照
      `progressive_compactor.go:391-404` 逐行 port**：
      `[tool_result <id>]: <content>` / `[<role>]: <content>` /
      `[tool_call <name>(<id>)]: <arguments>`，`"\n"` 连接，不截断。
      点名测试 + 变异（把 `[tool_call …]` 改成散文
      `[called tools: …]` 必须变红）。
    - **本层不得有第二个把消息渲染成文本的函数。** 变异：新增一个
      与 `render_for_summary` 并存的预览渲染器并让某条路径用它——
      一条「`omicsclaw/context/` 里渲染消息的函数恰好一个」的结构测试
      （AST 扫模块公开面）必须变红。这条防的是实现者顺手把模板摘要
      偷偷加回来。
    - `render_for_summary` 的 docstring 必须写明：**它的输出只进
      `build_summary_prompt` 的 user 侧，永不进 `Message.content`**。
      旧层 `compaction:798-802` 的实测结论（结构化标签当元数据不被复述、
      散文触发 few-shot 模仿）**只对「会回到模型视野的文本」成立**；
      本层没有这种文本，所以不需要反模仿渲染——**但如果哪天有了，
      必须先回来读这一条**。

21. **schema 没有多模态 parts，所以图片会被算成 0 token。**
    `Message.content` 是 `str`（ADR 0077 刻意排除多模态）。旧
    `budget.py:147` 的 `_IMAGE_BUDGET_TOKENS = 1300` 在本层**无处可施**。
    这不是可以靠写代码绕过的——**不要**为此发明一个「看起来像 base64
    就加 1300」的启发式，那会在正常文本上误伤。
    要求：在 `tokens.py` 的 docstring 里写明这个已知盲区（`CLAUDE.md`
    明写 Channel Surface 接收照片），形态记在 §11.B-11。
    ⚠️ 裁定 0 后本条的裁决是**丢弃**而不是「记为债」（§5.2）——
    harness9 无任何图片会计，且 schema 刻意排除多模态。本条要防的只有
    一件事：**不要为此发明启发式**。

---

## 7. 任务分解

四个任务。**A 必须先做完**（其余三个都要它的 token 估算），B / C 可并行，
D 在 A/B/C 全部落地后开。

### Task A —— `tokens.py` + `budget.py`（地基）

- **输入**：Q3、Q9；harness9 `token.go`(58)；旧 `budget.py`
  （`git show HEAD:omicsclaw/runtime/context/budget.py`）；
  `omicsclaw/provider/_model_limits.py`。
- **输出**：两个模块 + `tests/context/test_tokens.py`、
  `test_budget.py` + `tests/context/__init__.py`。
- **验收**：
  1. `estimate_message_tokens` 对 `reasoning_content`、`name`、
     `tool_calls`、`tool_call_id` 各有一条「加了这个字段，估算值严格
     变大」的测试（陷阱 1）。
  2. 中文与英文各一条实测对照，结果**记在 docstring 里**；若无法取得
     真值，写「未标定」（Q3-5）。
  3. `TokenCounter` 注入路径有测试：注入一个恒返回 `1` 的计数器，
     断言全部估算走它。
  4. 档位边界双侧测试（陷阱 2），**含 Q9-b 的两条边界**：
     `context_tokens <= 0` → `ValueError`；`usable_tokens <= 0` →
     `Pressure.EMERGENCY`。
  5. `usable_tokens < context_tokens` 有断言（陷阱 2）；
     **另加** `ContextBudget(context_tokens=200_000)` 必须 `TypeError`
     （两个预留字段无默认值，Q9-a）。
  6. `measure()` 的两源绑定：`budget.reserve_tool_tokens` 报低于实测
     `tool_tokens` 时按**实测值**扣减，`tool_reserve_shortfall` 写出差额
     （§3.2 的接缝注释）。变异：改成信任声明值，这条必须变红。
  7. `estimate_prompt_tokens` 的等价关系写进 `tokens.py` 的模块
     docstring（§5.2 那一行），并有一条测试钉住
     `estimate_text_tokens(system) + estimate_messages_tokens(msgs)`。
- **接缝责任**：A 定义的估算口径是 B 和 C 的共同分母。**A 必须在
  `tokens.py` 的模块 docstring 里写死口径**（数哪些字段、按什么单位），
  B/C 不得各自再发明。

### Task B —— `sections.py` + `prompt.py`（组装）

- **输入**：Q2、Q5、**Q5b（已被裁定 0 改判为单一 system prompt）**；
  harness9 `builder.go`(190) + `builder_test.go`(177)；
  §5.1 / §5.4 表里判为 port / 照 harness9 的行。
  ⚠️ **旧 `system_prompt.py`(77) 与 `layers/__init__.py`(1324) 不再是
  输入**——裁定 0 之后本 Task 的全部形状来自 `builder.go`，旧层只作为
  §5 表里「丢了什么、代价是什么」的交代对象。
- **输出**：两个模块 + `tests/context/test_sections.py`、`test_prompt.py`。
- **验收**：
  1. `assemble(prompt, history, user_text)` 的返回值里
     `role == Role.SYSTEM` 的消息**恰好一条**，且它是第 0 条（Q5）。
     （原稿写的 `build()` 在 §3.2 里不存在——`PromptAssembler.render()`
     返回 `AssembledPrompt`，`.system_prompt` 是 `str`；把它变成
     `Message` 的是模块级 `assemble()`。已按 §3.2 改写。）
  2. 空 source（返回 `""`）的段**整段消失**，标题也不出现——照
     `builder.go:113`、`:178-187` 与 `builder_test.go:105-111` 的语义。
  3. 字节稳定性两条测试（陷阱 7）**+ 一条「本层不读时钟」**（Q2-d）：
     用 `monkeypatch` 把 `date.today` / `datetime.now` / `time.time`
     换成会抛的替身，`render()` 必须正常返回。
     变异：在 `PromptAssembler.render()` 里加一行 `date.today()`，
     这条必须变红。（原稿写的「注入 clock 的测试」测不到本层任何东西
     ——本层没有 clock 可注入。）
  4. `SectionSource` 每次 `render()` 都被调用（不是构造时快照）——
     用一个计数闭包，断言调用两次 `render()` 得到两次调用
     （harness9 `builder.go:56-59` 的语义）。
  5. **本层对 `SectionSource` 的返回值逐字节原样落到对应 placement**
     ——不截断、不改写、不追加、不折行。变异：在 `render()` 里对 source
     返回值做 `[:2000]`（或 `.strip()` 之外的任何改写），这条必须变红。
     > 原稿这里写的是「Progressive Disclosure 负向断言：skills 段里只有
     > 索引、skill 正文不得出现（照 `builder_test.go:82-85`）」。那条 Go
     > 断言有意义，是因为 `builder.go:113-119` 是 **builder 自己**调
     > `skillsIndex.Summary()`；本层把渲染推到层外（Q2 表 + §5.1），
     > 于是它只能断言「假 source 返回什么就渲染什么」，**没有任何
     > `omicsclaw/context/` 的改动能让它变红**——而 §9-5 要求 21 条陷阱
     > 每条都经变异验证。**Progressive Disclosure 归 `skill/` 的渲染器，
     > 记为迁移义务（§11.B-15）**；本层留下的是上面那条可被杀死的性质。
  6. **单一 system prompt 的段隔离**（Q5b 改判后的形态）：
     改动一条 Section 的内容，`system_prompt` 里**只有那一段变**，
     其余各段与分隔符逐字节不变。变异：让 `render()` 在任意两段之间多
     插一个换行（或改成按段数变化的分隔符），这条必须变红。
     > **原稿这一条测的是 placement 拆分**（「易变段变化时
     > `system_prompt` 逐字节不变，只有 `message_context` 变」，对应旧层
     > `test_context_assembler.py:1037`）。**裁定 0 已把双 placement 整条
     > 丢弃**（Q5b），`message_context` 不再存在，那条断言在新形状下
     > **不可能为真**——易变段现在就在 system prompt 里。
     > 代价已记在 Q5b 的代价表。上面这条是它在新形状下**还能被杀死**的
     > 那部分性质。
  7. `render()` 出来的 `section_stats` 里每个 key 的 `estimated_tokens`
     与 `tokens.estimate_text_tokens(该段内容)` 一致（接缝，见下）。
  8. **`assemble()` 的两个边界各一条测试**（§3.2 的注释）：
     ① `user_text` 为空 → **不追加 user 轮**；
     ② `user_text` 非空 → 追加**恰好一条** user 轮，`content` **逐字节**
     就是 `user_text`。变异：在 user 轮内容前加任何前缀
     （例如把 `"## User Request"` 加回来），②必须变红。
     > 原稿的第 3 条边界（`message_context` 非空 + `user_text` 为空 →
     > 仍追加 user 轮）随裁定 0 消失：没有 `message_context` 了。
- **接缝责任**：B 负责三条：
  ① 「render 出来的文本是稳定的」；
  ② 「估算口径与 Task A 一致」（不得在 `sections.py` 里另写一个
  `ceil(len/4)`——旧层就有三个并存的估算器，
  `budget:95`/`budget:194`/`layers:589`）；
  ③ **`prompt.py` 的输出 ↔ `apply_cache_breakpoints` 的断点位置**
  （陷阱 3 第四行，本轮补的归属）：断点必须落在第 0 条 system 上，
  且不随 section 数量变化而漂移。这条是**跨包断言**，按陷阱 10 的例外
  写在 `tests/context/test_prompt.py` 里并 import `provider`，
  测试 docstring 写明理由。
  **B 不负责**内容对不对（那是组装根的）。

### Task C —— `transcript.py` + `summary.py` + `compaction.py`（压缩）

> 内部顺序**必须**是 `transcript` → `summary` → `compaction`，但
> **理由已被裁定 0 换掉**。原稿的理由是「6 道拒收闸要拿确定性模板当
> 参照物」——**闸与模板都已丢弃**。新的理由只有依赖关系：
> `split_head_tail` / `repair_tool_pairs` / `render_for_summary` 是
> `compaction` 的地基，而 `summary` 的锚点与模板是
> `build_summary_prompt` 的地基。

- **输入**：Q1、Q8、Q10、Q11；harness9 `compaction.go`(239)、
  `progressive_compactor.go`(514)、`summarization.go`(254)、
  `anchor.go`(124)；`anthropic_provider.py:262-290`。
  ⚠️ **裁定 0 之后，旧 `compaction.py` 不再是实现输入。** 原稿列的七处
  （6 道拒收闸 `:506-578`/`:408-427`/`:483-503`、模板侧反模仿渲染
  `:787-812`、素材侧散文渲染 `:359-383`、确定性模板摘要 `:854-903`、
  成对边界标记 `:35-53`、摘要累积与幂等上限 `:241-294`、tier-1 闸
  `:386-398`）**全部已丢弃**（§5.3）。行号留在这里只为一个用途：
  交付报告里要能说清「丢的是哪一段代码」。**实现者不得从它们取形状。**
- **输出**：三个模块 + `tests/context/test_transcript.py`、
  `test_summary.py`、`test_summary_gates.py`、`test_anchors.py`、
  `test_compaction.py`。
- **验收**：
  1. 陷阱 5、6、8、9、10、11、12、13、14、17、18、19、20 各有点名测试
     并经变异。
  2. `compact()` 的 async 测试用 `asyncio.run` 驱动（无
     `pytest-asyncio`）；涉及超时/取消的测试遵守陷阱 4。
  3. 压完真的装得下：`estimate_messages_tokens(result) <=
     budget.usable_tokens`，且低压时按**陷阱 6 的两条断言**为真 no-op。
  4. `CompactionRecord` 的每个字段都有至少一条测试读它——
     一个从不被读的审计字段就是
     `FRAMEWORK-REBUILD.md:441-448` 第 7 条的「stored, never read」。
  5. **`summarizer is None` 时走 `fit_to_budget` 并在
     `CompactionRecord.degraded` 里写非空原因**（照 harness9
     `fallbackCompact`，`progressive_compactor.go:488-495`），
     结果仍须满足验收 3 的「压完真的装得下」。
     > 原稿这一条要求「确定性模板摘要在 `summarizer is None` 时产出
     > 结构化结果，且它是 6 道闸的上界参照物」——**模板与闸都已随裁定 0
     > 丢弃**（§5.3）。harness9 在这个位置上的行为就是上面这条。
  6. **Emergency 档不经 LLM**：用一个会记调用次数的假 summarizer，
     断言 `Pressure.EMERGENCY` 下调用次数为 **0**（照
     `progressive_compactor.go:341-352` 的 `tierEmergency`）。
     > 原稿这一条是 `min_omitted_for_summary` 的两侧测试。
     > **那个参数已随裁定 0 删除**（§3.2、§5.3）——harness9 无对应物，
     > 「给了 summarizer 就一定调」是它接受的代价。上面这条是同一位置
     > 上 harness9 **真正有**的那道守卫。
- **接缝责任**：C 负责三条跨界一致性，**明确归 C，不许推给评估**：
  ① `repair_tool_pairs` 与 **provider 适配器**的角色分派一致
  （陷阱 10）；② 压缩里用的估算与 Task A 的口径一致（不得另写）；
  ③ **`budget.Pressure` ↔ `plan_compaction` 的档位分派**（陷阱 3 第二行，
  本轮补的归属）：每一档 `Pressure` 都有一条测试断言
  `plan_compaction` 走了对应的那条路径（`needs_summary`、
  `head`/`tail` 的切法、emergency 与否），**不是**只断言档位枚举值。
  一个把所有档都映射到同一条路径的实现，在只测枚举值的套件里全绿。

### Task D —— 两个独立只读评估（并行，互不知情）

沿用第 3、4、4.5 步的做法：

- **D1 正确性评估**：只读，找缺陷，**不修**。重点交代：陷阱 2 的
  「收紧方向」是否真的被钉住、陷阱 4 的 deadline 测试是否真的在恢复后
  再 await 了、陷阱 5 的别名、以及 §7 点名的四处 lane 接缝。
- **D2 harness9 对照 + 能力保全评估**：给它 §5 的能力表和
  附录 A 的对照表**作为待审材料**，并明确告诉它**表可能是错的**
  （0028 附录 B 记了 20 余处错在计划自身，
  `FRAMEWORK-REBUILD.md:277-280`；本计划自己在实现前的评审里被查出
  30 余处，见附录 C）。
  > **不要说「0029 有 27 处错在计划自身」**——`FRAMEWORK-REBUILD.md:394`
  > 说的 27 处是那一轮**交付代码**里的缺陷，不是计划的错。
  另外**专门瞄准 docstring**——这是 4.5 步付费买到的那条refinement
  （`FRAMEWORK-REBUILD.md:458-465`）：本层的 docstring 会做大量可核验
  断言（「harness9 在 `x.go:NN` 做了 X」「Python 做不到 Y」），
  一条自信写错的就是缺陷。

**两条纪律**（`FRAMEWORK-REBUILD.md:802-808`）：
- **绝不告诉评估者你已经知道的缺陷。** 独立撞上同一个的价值高于任何
  单份报告，而且只有一次机会。
- **明确把评估瞄向接缝。** 第 4 步九个缺陷里七个在 lane 之间。

修复是**第三个任务**，由既没写也没评的 agent 做。

---

## 8. 测试策略

### 8.1 目录

`tests/context/`，需要 `__init__.py`（`tests/engine/` 与 `tests/tools/`
都有）。

### 8.2 行为性分层探针 —— **复制哪一份**

`FRAMEWORK-REBUILD.md:296-300` 的明确指示：

> **Static checks inspect spelling; only a behavioural probe inspects
> fact** — the repaired guard runs the real paths in a subprocess and
> *then* asserts no `omicsclaw.runtime*` is in `sys.modules`.
> **Steps 5 and 6 will copy this test; copy the repaired version.**

**修好的那一版是
`tests/tools/test_tools_is_a_leaf_layer.py`（565 行 / 22,841 字节）。
不是 `tests/engine/test_engine_is_a_leaf_layer.py`（232 行 / 7,772
字节）。** 已核实两者差异：

| | tools 版（复制这个） | engine 版（不要） |
|---|---|---|
| 模块枚举 | `rglob("*.py")`（递归，自动覆盖子包） | `glob("*.py")`（平铺，会漏子包） |
| 相对 import | 按 PEP 328 算术**解析成绝对名** | `if node.level: continue` —— **整个跳过** |
| 第三方判定 | 对 `sys.stdlib_module_names` 取补 | 手写黑名单 |
| 动态 import | `ast.Call` 扫 7 个调用名，**白名单为空** | 无此检查 |
| 行为探针 | **有**：子进程跑真实路径，事后查 `sys.modules` | 无，两个子进程测试都只看 import 期 |

复制成 `tests/context/test_context_is_a_leaf_layer.py`，改三处：

1. 目录常量指向 `omicsclaw/context/`。
2. `_ALLOWED_INTERNAL = ("omicsclaw.schema", "omicsclaw.context")`
   —— **两项，不是三项**（Q2-c 裁定不 import `provider`）。
3. `_BEHAVIOUR_PROBE` 换成本层的真实路径：组装一个带多段的 prompt →
   估算一个超预算的历史 → 用一个假 `Summarizer` 压一次 → 用一个会抛的
   假 `Summarizer` 再压一次（走降级路径）→ `repair_tool_pairs` 一次，
   最后 `print(sorted(m for m in sys.modules if
   m.startswith("omicsclaw.runtime")))`，父进程断言 `== "[]"`。

`_TEMPTING_NEIGHBOURS` **原样保留，一个字都不用加**。
`omicsclaw.provider` **已经在 tools 版的名单里**——
`tests/tools/test_tools_is_a_leaf_layer.py:61-67`，`provider` 在 `:64`
——而且它在名单上**正是因为 tools 不许 import 它**。本层同样不许，
而且这里更诱人（`get_model_limits` 就在那儿），所以这一项原样合用。

> ⚠️ **修复轮更正。** 原稿这里写的是「tools 版里没有它，因为 tools
> 不许用」——**名单事实说反了，括号里的因果也说反了**。这出现在本计划
> **唯一一处「照着这个文件抄」的指令**里，照抄会往一份已经正确的名单里
> 重复加一项。唯一需要动的是紧随其后那段解释性 docstring（`:68-73`
> 讲的是 `omicsclaw.runtime`），把「本层要替代的是哪一层」改对。

### 8.3 变异验证

每条陷阱一次变异：改坏 → 跑 → 确认**点名的那条**测试红 → 还原 →
确认字节一致。

```bash
timeout --signal=KILL 300 /opt/conda/envs/rapids_singlecell/bin/python \
    -m pytest tests/context/ -p no:cacheprovider -q -o addopts="" \
    -rfE --continue-on-collection-errors
```

- `-rfE --continue-on-collection-errors` 是**强制的**：破坏 import 的
  变异会在 *collection* 阶段失败，而 `pytest -rf` 不列 collection
  错误——于是会被误报成「存活的变异体」。两个 agent 为此丢过时间
  （`FRAMEWORK-REBUILD.md:812-816`）。
- OS 级 `timeout` 也是强制的：进程内 deadline 救不了被卡住的事件循环，
  变异驱动的 `finally` 还原逻辑不会执行，**文件会留在被变异的状态**
  （0029 §11）。

### 8.4 环境

- 解释器 `/opt/conda/envs/rapids_singlecell/bin/python`（默认 `python3`
  是 3.10，会失败）。
- 无网络；无 tiktoken、无厂商 SDK。
- `pytest-asyncio` 未装 → async 测试用 `asyncio.run` 驱动。
- `black` 装不上 → 行宽用 `awk 'length > 88'` 验证（须无输出），
  并手工检查 black 会重排的构造。

---

## 9. 验收标准

1. **新套件通过。**
   ```bash
   /opt/conda/envs/rapids_singlecell/bin/python -m pytest \
       tests/schema/ tests/provider/ tests/engine/ tests/tools/ tests/context/ \
       -p no:cacheprovider -q -o addopts=""
   ```
   期望：前四个目录的 1,419 条里 **1,418 条必过，且一个字都没改动**。

   > 与 0029 §10-2 同一条修正：**判据是「原有用例不被触碰」，不是
   > 「总数不变」**——分层守卫用 `rglob` 参数化，每落一个新模块就自动
   > 多几条用例。

   **唯一被点名豁免的红**：
   `tests/tools/test_websafety.py::test_a_server_dripping_bytes_cannot_outlast_the_budget`。
   它是 **pre-existing、order-sensitive、已被交接文档判为 out of scope
   且 open** 的间歇失败——`FRAMEWORK-REBUILD.md:541-548` 原话：
   「failed on some runs — reproducibly when `test_bash.py` runs
   immediately before it, never on its own … Left alone as out of scope,
   and open」，并特意说明这是 **named rather than rounded off**。
   原稿写「1,419 条全部仍然通过」正是把它又圆回去了，而实现者撞红时
   只有两条路：白花时间追，或去动 `_websafety.py`——后者直接违反 §9-4。

   **复跑判据**（撞到它时唯一允许的动作）：
   ```bash
   /opt/conda/envs/rapids_singlecell/bin/python -m pytest \
       tests/tools/test_websafety.py -k dripping \
       -p no:cacheprovider -q -o addopts=""
   ```
   单独跑一次；绿即放行，并在交付报告里记一行「撞到已知间歇失败，
   单独复跑通过」。**红也不要修它**——那时它就不是间歇了，如实报告，
   交给 owner。**任何情况下都不得改 `omicsclaw/tools/_websafety.py`。**

   **本修复轮的实测**（供实现者对照）：整套
   `tests/schema/ tests/provider/ tests/engine/ tests/tools/` 跑一次 =
   `1419 passed in 19.85s`；`tests/tools/test_bash.py
   tests/tools/test_websafety.py` 连跑一次 = `167 passed in 7.60s`。
   两次都没撞上——**「没复现」不等于「不存在」**，交接文档已经把它
   点名为 open。

2. **分层。** `omicsclaw/context/` 在 `omicsclaw` 内**只**导入
   `omicsclaw.schema`；含动态 import 检查与 §8.2 的行为探针。
   探针输出必须是 `[]`。

3. **越界判据用快照 diff，不用「只许 `??`」。**
   开工前先存
   `git status --porcelain | sort > /tmp/step5_before.txt`，
   交付后：
   ```bash
   git status --porcelain | sort > /tmp/step5_after.txt
   diff /tmp/step5_before.txt /tmp/step5_after.txt
   ```
   **期望：只出现新增行，且每一行都是 `?? omicsclaw/context/` 或
   `?? tests/context/` 或 `?? docs/plans/0030-...`。**
   一条消失的行、一条新的 ` M `，都是越界。

   > 理由：当前工作区已有 320 条 `D ` 与若干 ` M `（第 6 步要收编的
   > `omicsclaw/memory/` 也在其中）。照抄 0029 的「只许 `??`」会让
   > 实现者要么误判失败、要么为了让它成立去动别的文件。

4. **本步申请的例外：零，且裁定 4b 确认了这一点。** 不动任何既有文件，
   包括：不修 Q6 里那个 `tui.py:21` 的既有 bug、不改
   `tools/base.py:218-223` 已过期的 `tags` docstring、
   **不改 `docs/FRAMEWORK-REBUILD.md`**（含 Q1 指出的 `:43` 那行冲突）、
   不改 ADR 0024 / 0039。
   > **`ToolPolicy.tags` 的定性（owner 裁定 4b，2026-09-18）**：
   > harness9 **无对应物**，这是纯本仓库的文档腐烂，**不归本步，归迁移
   > 任务**。依据：它承诺的 surface 过滤器已被 owner 废除
   > （`FRAMEWORK-REBUILD.md:722-742`），而字段本身按预期会在迁移后
   > 重新获得消费者（`FRAMEWORK-REBUILD.md:733-735` 记的
   > `orchestration.py:201` 的 `"mcp" in policy_tags` 分派——⚠️ 那个文件
   > **已 staged 删除、磁盘上不存在**，实测 grep `"mcp" in` 零命中，
   > 所以这是预期而非活着的调用点，详见 §11.B-5 的复核注记），
   > 所以**字段该留、错的只有 docstring**——一行注释的修改。

5. **§6 的 21 条陷阱每条有点名测试且经变异验证**，交付报告里逐条列出
   「变异内容 → 变红的测试名」。

6. **§5 的能力表每行都有交代，没有留空。**

7. `awk 'length > 88' omicsclaw/context/*.py tests/context/*.py` 无输出。

8. **每一条搬来的字面量，都要在报告里声明「已在 Python 下重验」**，
   并给出重验方式。**「决定不搬」是合法答案，但要写在报告里。**
   - **从 harness9**（裁定 0 之后本层的字面量**只剩这一组**）：
     `charsPerToken=4`（这条必须重推，见 Q3）、
     `MinTailMessages=6`（`compaction.go:87-92`）
     **与它在真实 benchmark 上被改成的 `8`**
     （`cmd/swebench/runner.go:293-299`——**同一个数在作者自己手里就有
     两个值**，正是「借来的字面量必须重验」的样板）、
     `0.60/0.70/0.80/0.95`（`progressive_compactor.go:124-134`）、
     **`80%` vs 真实 benchmark 的 `55%`**（`compaction.go:87-92`
     vs `runner.go:293-299`，见 Q9 的引用块——本层不用比例，用显式减法，
     但这两个数是 Q9-a「预留字段不给默认值」的证据）、
     `FormatTokenCount` 的 `1000/1_000_000` 分界（`token.go:49-58`）。
     **决定不搬的**：`OffloadThreshold=4000`、`previewLines=10`、
     `precisMaxEntries=30`、`maxBytes=5120`（都属 offload / LTM，本步不做）、
     摘要超时 `60s`（Q4-3，边界 (b)）。
   - **从旧 OmicsClaw 层：一个都不搬（裁定 0）。** 原稿这一整组
     ——`reserved_output=4096` / `safety_margin=2048`、
     五档百分比 `65/80/90/96`、`DEFAULT_MAX_PROMPT_TOKENS=85_000`、
     `collapse_trigger_ratio=0.82` / `auto=0.92`、
     `collapse_target_ratio=0.55` / `auto_target_ratio=0.40`、
     `_PROMPT_BUDGET_FRACTION=0.5`、`_PERSISTED_SUMMARY_RATIO=0.25`、
     `protected_tail_messages=4`、`max_highlights_per_role=3`、
     `_message_preview(max_chars=180)`、头尾比例 `0.7/0.3`、
     `llm_summary_min_omitted=8`、`llm_summary_timeout_s=20.0`、
     `llm_summary_max_tokens=1024`、`_IMAGE_BUDGET_TOKENS=1300`
     ——**全部随它们所属的路径一起丢弃**（§5.2 / §5.3）。
     「决定不搬」是合法答案，本行就是那个答案，**交付报告里仍要写一句**。
     ⚠️ 其中 `reserved_output=4096/2048` 与**旧**引擎实际用的 `8192/0`
     （`git show HEAD:omicsclaw/engine/loop.py:239`，常量在同文件 `:196`；
     这是已 staged 删除的旧引擎，不是工作区那个新的）**两处不一致本身
     就是证据**：这两个数从来没有一个权威来源，新层改用
     `ModelLimits.output_tokens` 取代拍脑袋（Q9-a）。

9. **Token 估算的精度声明必须诚实**（Q3-5）：标定过就给表，没标定就
   在 docstring 里写「未标定」。报告里不得出现未测过的精度数字。

10. **`compact()` 的降级路径有测试覆盖**：`summarizer` 为 `None`、
    `summarizer` 抛异常、`summarizer` 返回空串、`summarizer` 返回
    格式跑偏的文本——四种都必须得到一个可用的结果和一条带
    `degraded` 的 `CompactionRecord`。

---

## 10. 迁移与删除

### 10.1 旧 context 的删除：**不是本步的任务，而且已经做完了**

工作区实测：`omicsclaw/runtime/context/` 的 7 个文件与 13 个对应测试
文件**已是 staged 删除**，且这是一次**更大规模拆除**的一部分——
`git status --porcelain | grep "^D " | wc -l` = **320**，其中包括
`omicsclaw/memory/`(32)、`omicsclaw/control/`(19)、
`omicsclaw/runtime/`(46)、`tests/memory/`(30)、`tests/control/`(21)。
目录在磁盘上已经不存在。

**裁决：本步不碰删除，一行都不碰。** 理由：
1. 已经发生了，且不是本步发生的。
2. 它的范围远超 context —— 补齐「断裂引用」意味着重写 30+ 个
   `omicsclaw/surfaces/*` 文件，那是迁移，不是第 5 步。
3. one component per step：本步只在 `omicsclaw/context/` 与
   `tests/context/` 下建文件。

**本步在删除这件事上的唯一义务：§5 的能力表。** 「决定不要」和
「忘了要」是两件完全不同的事，而后者不会报错。

### 10.2 断裂引用清单（交给迁移，此处只是把它记下来）

**生产代码 6 个文件 / 7 处**（已逐行核实）：

| 文件:行 | 引用 | 消费的能力 | 断法 |
|---|---|---|---|
| `omicsclaw/agents/prompts.py:12` | `from ...context.system_prompt import build_system_prompt`（用在 `:326`，`surface="pipeline"`） | system prompt 门面 | **ImportError** |
| `omicsclaw/diagnostics.py:24-29` | `from ...context.assembler import assemble_prompt_context, extract_analysis_hints, extract_user_text, should_attach_capability_context` | 组装诊断 | **ImportError** |
| `omicsclaw/diagnostics.py:30-33` | `from ...context.layers import ContextAssemblyRequest, should_prefetch_knowledge_guidance`（用在 `:1452-1489` 构造 `ContextReport`） | 逐层 token 报告 | **ImportError** |
| `omicsclaw/skill/evolution_governance.py:4643-4652` | 函数内 `from ...context.layers import load_skill_context`；断言被治理的 Gotcha 出现在渲染文本里，否则抛 `EvolutionRevalidationError` | gotchas 重校验 | **运行时 ImportError**（延迟到调用） |
| `omicsclaw/surfaces/channels/commands/builtins.py:11, 102-108` | `/compact` 里函数内 import 五个符号 | `/compact` 命令 | **运行时 ImportError** |
| `omicsclaw/surfaces/desktop/_compaction_event_bridge.py:13-16` | `CompactionEvent`, `build_compaction_status_payload` | 压缩事件 → SSE | **ImportError** |
| `omicsclaw/surfaces/cli/interactive.py:225-226` | **只是字符串**：`logging.getLogger("omicsclaw.runtime.context")` / `".layers"` 的 `setLevel` | 日志级别配置 | **不报错，静默变成死配置** |

> 最后一行是本清单里最危险的一条：它 **grep 抓得到、AST 抓不到、
> import 时不报错、测试不会红**——正是 0028 §11 债 #2 描述的那一类
> （「`importlib.import_module` 是 grep catches and AST does not」）。
> 迁移时不要只靠静态 import 扫描。

**仍在工作区的测试 3 个文件 / 8 处**：

| 文件:行 | 钉住什么 |
|---|---|
| `tests/test_bot_core_import_behavior.py:12-13` | 重新 import 前先从 `sys.modules` 里 pop 掉 `...context.assembler` / `.layers` |
| `tests/test_skill_evolution_governance.py:1734,1736,1746` | 包装 / monkeypatch `context_layers.load_skill_context` |
| `tests/test_skill_evolution_governance.py:2205,2207` / `2239,2246` | 同上，另两处 |
| `tests/test_skill_promotion_sidechannel.py:144-149` | `inspect.getsource(assembler)` 里必须出现 `build_agent_session_id` —— 钉住「session key 由共享 helper 推导，而不是各处重拼 f-string」 |

**旧测试 13 个文件全部已 staged 删除，工作区一个都不剩**（已核实）。
其中两个其实**不属于 context 层**，写在这里免得迁移时找错地方：
`test_tool_descriptions_compact.py`(97) 测的是
`runtime/tools/builders/agent.build_bot_tool_specs`；
`test_soul_md_compact.py`(134) 的 12 条里只有 `:129-131` 那一条碰
context 层，其余 11 条测的是 `SOUL.md` **文件本身**（≤1500 字符等）
——那些是 SOUL.md 的契约，与本层无关，**不应随本层一起消失**。

**文档**：`AGENTS.md:126-127` 的目录树仍列着
`runtime/ ├── agent/, context/, tools/, policy/, storage/`，且尚未为
`context/` 加行（与 `schema/`、`provider/`、`engine/` 并列）。
`CLAUDE.md` 无 context 引用（已查）。另有会**漂移但不会断**的：
`docs/architecture/2026-05-18-current-architecture.md`、
`docs/reviews/context-assembly-audit-vs-cellclaw.md`（F1-F11 / B1-B3
的完整审计，行号已陈旧）、`docs/adr/0039-token-native-context-budget.md`、
`docs/adr/0024-prompt-prefix-caching.md`、`docs/CONTEXT.md:665`。

> **ADR 0039（token-native budget）仍然有效，新层继续遵守**（Q3、Q9）。
> **ADR 0024（prompt prefix caching）的适用范围被裁定 0 收窄**：它的
> 「稳定的进 system、随查询变的骑在 user 轮上」那一半已随双 placement
> 一起丢弃（Q5b），在新架构里只剩 provider 侧的
> `apply_cache_breakpoints` 与 `registry.available_tools()` 的字节稳定。
> **迁移时不要把这两份 ADR 和旧实现一起整体作废**，也不要照 ADR 0024
> 的原文去给新层加回 placement——**ADR 本身的更新不归本步**
> （§9-4「例外：零」），形态记在 §11.B。

### 10.3 完成条件（属迁移，不属本步）

1. 上表 7 处生产引用全部重写或删除。
2. 3 个测试文件处理掉（重写 / 删除 / 标记 skip）。
3. `AGENTS.md` 目录树更新，且新增 `context/` 一行（与
   `schema/`、`provider/`、`engine/` 并列）。
4. `grep -rn "runtime\.context" --include=*.py .` 无输出。
5. 只有 1–4 全绿，「旧 context 已移除」才算完成。**在此之前，
   FRAMEWORK-REBUILD 不应把它记成 done。**

---

## 11. 已知债务

> **分组依据（owner 范围约束，2026-09-18）**：「你当前的目标是集中优化
> context 即可，其他无关的组件可以暂时放一下，后续等我搭建起完整的
> agent 架构之后，再考虑进行相关优化。」
>
> - **§11.A —— `omicsclaw/context/` 本体的债**，以及 Q1 明确留给
>   **第 6 步**的三道接缝。这一组是本层设计的一部分，接手人已经确定。
> - **§11.B —— 跨组件的形态记录**。引擎侧、Surface 侧、迁移侧、
>   schema 侧。**等 owner 搭好完整 agent 架构之后再议**——**不是本步，
>   也不是「下一步马上要做」**。本计划**不为它们预留工期，也不以它们为
>   验收前提**。每条只留「形状 + 行号证据」，**不写排期**。

### 11.A —— 属 context 本体 / 第 6 步要接的接缝

> **编号沿用原表**，这样全文既有的「§11-N」交叉引用仍然指得准。
> 分组改变的是**紧迫度与接手人**，不是条目本身。

2. **[§11.A-2]** **写回式压缩的策略没家（第 6 步）。** harness9 `history.go:117-153`
   的三条门控（Emergency 写回、瞬时摘要失败不写回、无实际削减不写回）与
   `persistCompacted` 的「Clear + AddMessages + 独立 ctx 回滚」都需要
   Session。本步只交出 `CompactionRecord` 这个**事实**，**策略归第 6
   步**。第 6 步若不实现，压缩就退化成 harness9 issue #117 之前的
   「每轮重算视图」——代价是 Soft/Full 档每轮多一次 LLM 摘要调用。
   （Q1 三道接缝之一。）

3. **[§11.A-3]** **`CompactionState` 的保管归第 6 步。** 本步做成入参/返回值，第 6
   步决定存哪。不存的后果：每次压缩都走「首次模板」而不是增量模板，
   多轮压缩后信息损失叠加（blog:156 给的理由）。
   ⚠️ 裁定 0 之后这一条**变重了**：摘要 block 累积与「保新丢旧」已丢弃
   （§5.3），`CompactionState.summary` 只有一份，全靠增量模板续接。
   （Q1 三道接缝之二；`CompactionRecord` 的持久化格式是之三。）

4. **[§11.A-4]** **offload（大输出落盘）没做（第 6 步 / 工具层）。** harness9 有两套：
   执行后的 `hooks/offload.go`（阈值 10000 字符）与压缩期的
   `memory/compaction_offloader.go`（阈值 4000 字节）。本层只提供
   占位符渲染。**注意 harness9 的排除表**
   （`read_file`/`write_file`/`edit_file` 永不 offload，blog:253 给了
   理由：否则读取被 offload 的文件本身又会被 offload，无限循环）。

7. **[§11.A-7]** **档位阈值未在本项目负载上标定**（Q9）。`0.60/0.70/0.80/0.95` 是
   harness9 的经验值，分母已经被我们换过。需要真实长跑数据。

8. **[§11.A-8]** **token 估算未标定**（Q3-5）。本机装不上 tiktoken。

9. **[§11.A-9]** **本层同样没跟真实端点说过话。** 与 provider 适配器、web 工具是
   同一笔债。本层的具体形态：`Summarizer` 的所有测试都驱动假实现，
   「摘要模板真的能让模型产出可解析的锚点格式」**从未被验证过**。
   ⚠️ 裁定 0 之后这一条**也变重了**：6 道拒收闸已丢弃（§5.3），
   一个解析不出锚点、或悄悄丢掉 `h5ad` 路径的摘要，**没有任何机制会
   拦下它**；陷阱 13 的「解析器永不抛」会让它**静默**失效。
   **这是裁定 0 之后本层最值得早点还的一笔债。**

18. **[§11.A-18]** **`result_policy`（6 个值）随 offload 一起欠着（第 6 步）**
    （§5.0 第二行）。它决定工具输出何时落盘、inline 阈值与预览长度。
    本步不做 offload（债 4），所以这一项在第 6 步做 offload 时必须一并
    接上，否则会出现「有落盘机制、但每个工具都用同一套阈值」的退化。
    旧消费者 `runtime/storage/tool_result.py` 与
    `runtime/context/compaction.py:739` 都在被拆的那一批里。

**本组已关闭的两条**（裁定 0，留编号以免交叉引用悬空）：

13. **[§11.A-13]** ~~压缩「三遍收敛」不做~~ → **已随裁定 0 正式丢弃，不再是债**
    （§5.3）。它的前提（system prompt 随摘要一起变）在本架构里本来就
    不成立。**后果已接受**：一次压缩后总量仍可能略超目标，下一轮再压。

14. **[§11.A-14]** ~~413 反应式重压的检测端没家~~ → **已随裁定 0 丢弃**（§5.3）。
    本层的 `emergency_fit` 就是 harness9 的 `CompactForce`，与 413 无关；
    旧框架独有的是 413 的**检测与重压编排**。
    ⚠️ **接受的风险**：harness9 只在估算超阈时压，**估算错了就没有第二次
    机会**，而本层的估算恰恰未标定（债 8）。这不再是「应当早做」的债，
    是一条被记录在案的风险。

### 11.B —— 跨组件的形态记录（等完整 agent 架构就绪后再议）

> **这一组不是待办排期。** owner 的范围约束是「集中优化 context 即可，
> 其他无关的组件可以暂时放一下」。下面每条只留**形状与行号证据**——
> 它们是调研的产物，不能丢——但**何时开、由谁开，等完整架构就绪后由
> owner 决定**。**本步不做，也不以任何一条为验收前提。**

1. **[§11.B-1]** **轮内压缩做不到（引擎侧）**（Q7）。本步交付后，压缩只能在 `run()`
   之间做。**harness9 有现成答案，形状与本条一致，已核实**：
   - 接口：`WithCompactor(c memory.Compactor)`，`options.go:135-138`，
     docstring 原话「在每次 LLM 调用前裁剪历史消息」。
   - 调用点：`loop_phases.go:164-168`（`applyCompactionWith` +
     `writeBackCompaction` + 上报）。
   - **纪律：接口定义在 engine 侧（使用者侧）、实现在外部包。**
     `options.go:157-159` 对 `PromptBuilder` 的原话是「接口定义在 engine
     包（使用者侧），由 internal/context 包实现。引擎通过此接口与
     Context Engineering 模块解耦」——与 OmicsClaw 已有的
     `ConcurrencyAwareExecutor` / `DeadlineAwareExecutor` **同构**。
   
   **本条与 #12、以及交接文档第 20 项（context-window 上报）是同一个
   后续步骤**，理由是三者全落在 `prepareTurnInput` 这**一个函数的相邻
   几行**：压缩 `:164-168`、token 上报 `:173-174`、nudge/gate `:176-206`。
   分三次开会改同一个函数三遍。

5. **[§11.B-5]** **`ToolPolicy.tags` 的 docstring 已过期（迁移）。**
   `tools/base.py:218-223` 说 tags 是「where surface gating lands once
   that layer exists」，而 owner 已废弃 surface 门控
   （`FRAMEWORK-REBUILD.md:722-742`）。
   **owner 裁定 4b（2026-09-18）：harness9 无对应物，纯本仓库文档腐烂，
   归迁移任务，不归本步**（§9-4「例外：零」不变）。
   **字段该留、错的只有 docstring**——依据是
   `FRAMEWORK-REBUILD.md:733-735`：「It stays — `orchestration.py:201`
   dispatches on `"mcp" in policy_tags` — but the docstring should stop
   promising a filter that will not exist」。一行注释的修改。
   ⚠️ **复核注记**：那个消费者 `orchestration.py:201` 位于
   `omicsclaw/runtime/tools/orchestration.py`，**已 staged 删除且磁盘上
   不存在**（`omicsclaw/tools/` 里没有 `orchestration.py`，实测 grep
   `"mcp" in` 零命中）。所以「字段该留」现在的依据是 owner 的裁定与
   **迁移后会重建那条分派**这个预期，不是一个活着的调用点。

6. **[§11.B-6]** **`tui.py:21` 的 `_OMICSCLAW_DIR` 算的是包目录而非仓库根（迁移）**
   （Q6），与 `interactive.py:208` 不一致，并在 579/1019 行进
   `sys.path[0]`。本步不修。它让 `omicsclaw/context/` 在 TUI 进程里可以
   被裸 `import context` 命中——**当前无人这么写，所以是潜在敞口**。

10. **[§11.B-10]** **`/compact` 斜杠命令没家（Surface）。** 旧的在
    `surfaces/channels/commands/builtins.py:102`。本步交付 `compact()`
    供它调用，但命令本身属 Surface。

11. **[§11.B-11]** **图片 token 会计：已丢弃，形态记录在此（schema 侧）。**
    `Message.content` 是 `str`，ADR 0077 刻意排除了多模态 content parts
    （`FRAMEWORK-REBUILD.md:108-110`）；harness9 也无任何图片会计，
    所以裁定 0 下的裁决是**丢弃**而不是「记为债」（§5.2）。
    旧层的方案留作参考（`budget.py:147`、`:199-202`、`:211-212`：
    从不 tokenize base64、从不当 0、按 1300 token/张定额收费，6 条测试
    保护）。**后果是真的**：`CLAUDE.md` 明写 Channel Surface 接收照片并
    走组织切片分析，在 schema 恢复多模态之前，**一条图片消息的 token 会
    被算成 ~0**，预算系统性乐观。**不要为此发明启发式**（陷阱 21）。

12. **[§11.B-12]** **输出/续写预算轴：正式废弃；替代物是 nudge/gate 家族（引擎侧）。**
    **owner 裁定 3（2026-09-18）。** 旧 `budget.py:317-463` 的
    `TokenBudgetTracker` / `"+500k"` 解析 / diminishing-returns 三条停止
    判据 → **随裁定 0 一起丢**（§5.2）。

    **依据：harness9 根本不做 token / 成本预算**（逐条复核）：
    - `grep -rn -iE "price|pricing|cost|usd|dollar|spend" internal/ cmd/
      --include=*.go`：`internal/` 里唯一的 `cost` 是
      `internal/memory/compaction.go:164` 的局部变量（指 token 数）；
      定价字段只在 `cmd/swebench/model_snapshot.go:33,40-41,62-65,
      106-107,158-159`，是 benchmark 元数据，**不参与任何停止决策**。
    - `"+500k"` 式用户预算语法：grep **零命中**。
    - 停止轴只有三条：`MaxTurns`（默认 500，`agent_loop.go:74`；
      `options.go:18-21`；判定在 `loop_phases.go:131-134`）、ctx 取消
      （`:135-140`）、LLM 失败。

    **harness9 撞上了同一个问题，解法是「没进展就推一把」而不是
    「花够了就停」。** 四个机制全在 `loop_phases.go:176-206`，
    配置入口在 `options.go:69-121`：

    | 机制 | 触发 | 标定值与出处 |
    |---|---|---|
    | `WithMemoryNudge(interval,text)`（`options.go:69-76`） | 每 N 轮 | `cmd/harness9/main.go:446` 用 **10** |
    | `WithStallNudge(window,text)`（`:78-90`） | 连续 N 轮用了工具但未调进展工具（`edit_file`/`write_file`，见 `internal/engine/nudge.go:13-19` 的 `progressToolNames`） | `cmd/swebench/runner.go:35` = **10** |
    | `WithPlanningGate(budget,text)`（`:105-121`） | 连续 N 轮既无进展工具也无 `plan_write` | `runner.go:55` = **12**，`:53` 的注释说明**刻意与 10 错开节拍** |
    | `WithClosingGate(threshold,text)`（`:92-103`） | 剩余轮数 ≤ 阈值，注入「立刻验证并收尾」 | `runner.go:50` = **5** |

    **四者共同纪律**（注释反复强调）：**只注入发送给 LLM 的临时副本，
    绝不持久化、不累积，每次 interaction 至多一次。**
    真实轨迹证据：`runner.go:33-34`（停滞：xarray-3364、pylint-7080 烧满
    80 轮）、`runner.go:318`（探索过深：sphinx-8474 读了 64 轮）、
    `runner.go:47-49`（最后一改未验证被截断：pylint-7114、seaborn-3407）。

    **归属：`omicsclaw/engine/`，不属本层。** 触发条件是**循环状态**
    （轮数、本轮调了哪些工具），只有 engine 知道；文案由组装根以字面量
    传入（`main.go:446` 就是这么接的）。**本步不做。**

    > ⚠️ **必须带着的警告**：`10 / 12 / 5` 与「进展工具 =
    > `edit_file`/`write_file`」是**从 SWE-bench 轨迹标定**的。
    > OmicsClaw 跑 omics 分析，一次 `spatial-deconv` 可能几十分钟，
    > **「连续 10 轮没写文件」在这里可能完全正常**。这正是陷阱 1
    > 「借来的字面量必须重新验证」的教训——**进展工具集合与三个阈值
    > 都必须在本仓库语料上重新定义**，一个都不能直接搬。

    **与 #1、以及交接文档第 20 项（context-window 上报）合并为同一个
    后续步骤**：三者全在 `prepareTurnInput` 的相邻几行（见 #1）。

15. **[§11.B-15]** **跨组件要接的「家在别处」清单**（§5.5 的第三段）：skill context 与
    **gotchas 注入**、**`should_prefetch_skill_context` 这个预取判据**、
    KnowHow、知识库 guidance 与
    **`should_prefetch_knowledge_guidance`**、prompt packs、
    `output_format`（后端 `runtime/output_styles.py` **还活着**，最省力
    的一条）、MCP instructions、hint 抽取、
    **`extract_user_text` / `should_attach_capability_context`**、
    **Progressive Disclosure 的负向断言**（`builder_test.go:82-85` 的
    对应物；渲染器在 `skill/`，断言必须跟着它走——本层结构上无法违反
    它，所以本层也无法保护它）、`assemble_chat_context` 的
    五路扇出编排与 F9 后台任务回收、压缩事件的 wire 渲染。
    **每一项都有旧测试钉过，而那些测试已随旧层一起删除**——所以
    「忘了接」不会有任何东西变红。清单对照见 §0.1 的两张表。

16. **[§11.B-16]** **`test_soul_md_compact.py` 里 11/12 条与本层无关，不应陪葬。**
    它们测的是 `SOUL.md` 文件本身的契约（≤1500 字符、身份措辞、
    不得再出现 Bot Mode / CLI Mode 小节等）。文件还在，契约还在，
    测试却已 staged 删除。**归迁移：把那 11 条挪到一个不依赖 context
    层的测试文件里。**

17. **[§11.B-17]** **`progress_policy` 的 `analysis` 判据没家（迁移）**（§5.0 第三行）。
    0028 §5 把它判给 loop / Surface，不是装配层；新层已经有承接它的
    结构——第 4 步的 `contextvars` 带外通道里有一个 progress sink
    （`FRAMEWORK-REBUILD.md:268-273`，且修复后「a broken transport must
    not turn a finished tool into a failure」）。缺的只是「哪些工具算
    `analysis`」这个判据。

19. **[§11.B-19]** **`speculative_classifier` —— 已定向：新入口/交互层。**
    **owner 裁定 1（2026-09-18）**：交给 owner 后续设计的**新入口/交互
    层**（`FRAMEWORK-REBUILD.md:748-752`），那一层「后续再设计实现」。
    §5.0 第一行已改成定稿裁决，**不再是待拍板**。
    ⚠️ **空窗期的后果照旧成立**：在那一层落地之前，任何「工具执行前
    二次收紧 `risk_level` / `approval_mode`」的能力在新架构里**都不
    存在**——`ToolPolicy` 的守卫默认（`HIGH`/`ASK`）挡住的是「未声明的
    工具」，挡不住「声明为 `AUTO` 但在这一次调用里本该 ASK」。
    **这是唯一一项方向朝收紧的结转能力**，所以它是「被安排」而不是
    「被删」——这个区别正是本条存在的理由。

20. **[§11.B-20]** **ADR 0024 的适用范围被裁定 0 收窄，ADR 文本未更新（文档）。**
    见 §10.2 的注记与 Q5b。本步不改任何 ADR（§9-4「例外：零」）。

---

## 12. ~~待 owner 拍板~~ —— **四项全部已裁定（2026-09-18）**

> **本节已清空待办语义，只剩存档价值。** 这一节原是实现前评审的产物，
> 四项都只有 owner 能拍。**owner 已于 2026-09-18 逐条裁定**，裁定内容与
> 它们各自掀翻了哪几节记在**附录 C.2**。
>
> 下面保留每一项的**选项与代价**——那是当初为了让 owner 一眼看完而做的
> 功课，丢掉它下一个人只会再做一遍——但**每一项的开头都改成了「已裁定」
> 的结论行**。**全节不阻塞任何 Task，也不再有「待拍板」这件事。**

| 项 | 裁定（2026-09-18） | 落地在 |
|---|---|---|
| 12-1 `speculative_classifier` 的家 | **选项 B**：交给 owner 后续设计的新入口/交互层 | §5.0 第一行（定稿裁决）、§11.B-19 |
| 12-2 Q1 的 compaction 拆分 | **选项 A**：维持 | Q1 末尾的确认块 |
| 12-3 输出/续写预算轴的归属 | **选项 C 的加强版**：正式废弃；替代物是 harness9 的 nudge/gate 家族，属 engine | §5.2 末行、§11.B-12 |
| 12-4a 轮内压缩 | 形态与证据入档，**等完整架构就绪后由 owner 决定何时开**；与 12-3、交接文档 #20 合并为同一步 | §11.B-1 |
| 12-4b `ToolPolicy.tags` docstring | **归迁移任务，不归本步** | §9-4、§11.B-5 |

### 12-1 `speculative_classifier` 的家 —— **已裁定：选项 B**

**背景**：`docs/plans/0028-tool-registry.md:515` 明写「→ 装配层」，即本步。
`0028:803-807` 把它与 `result_policy`、`progress_policy`、`surfaces`、
`predicate` 并列，说「去向已定，但**家还没建**」。owner 2026-09-18 的裁定（`FRAMEWORK-REBUILD.md:717-742`）
只覆盖四项门控，**不含它**。它在旧层的效力是：执行**前**把
`risk_level`/`approval_mode` 升级为 DENY 或 REQUIRE_APPROVAL
（`runtime/tools/orchestration.py:271` 的 `_classifier_policy_decision`），
并读 `request.runtime_context` 的 `surface`/`trusted`/`background`。

| 选项 | 代价 |
|---|---|
| **A. 随四项门控一起废弃** | 失去「执行前二次收紧」这一层。`ToolPolicy` 的守卫默认（`HIGH`/`ASK`）挡的是「未声明的工具」，挡不住「声明为 `AUTO`、但在这一次调用的上下文里本该 ASK」。**这是唯一一项方向朝收紧的结转能力**，废掉它是单向的权限放宽 |
| **B. 交给 owner 将设计的新入口/交互层**（`FRAMEWORK-REBUILD.md:748-752`） | 空窗期：在那一层落地之前，能力不存在，与 A 的效果相同，但**是被安排的**而不是被删的。需要 owner 确认那一层确实会承接「按调用上下文收紧策略」，而不只是「工具可见性」 |
| **C. 现在就建进 `omicsclaw/context/`** | 与本层的叶子性**正面冲突**：它要读 `surface`/`trusted`/`background`，而那批字段正是被废掉的四项门控读的同一批；而且它需要一次 LLM 调用（「speculative」），本层只允许 `omicsclaw.schema` + 标准库。要做只能做成又一个 Protocol，交给组装根实现——那时它已经不在本层了，等于 B |

**当初的推荐：B。owner 于 2026-09-18 采纳 B。**
落地：§5.0 第一行已改成**定稿裁决**（不再是「交 §12-1」），
§11.B-19 已改写为「**已定向：新入口层**」并保留空窗期后果的告警。
那一层「后续再设计实现」，**没有排期**。

### 12-2 Q1 的「compaction 拆开」与交接文档字面表述的冲突 —— **已裁定：维持**

**背景**：`FRAMEWORK-REBUILD.md:43` 把 `prompt assembly, budget,
compaction` 整块写在第 5 步名下。Q1 把它按「是不是时间的函数」拆成两半：
纯函数归 5、跨时间的归 6，并给了四条理由与三道接缝。
**论证在 Q1，但那是一个选择，不是既成事实。**

| 选项 | 代价 |
|---|---|
| **A. 维持 Q1 的拆分**（计划现状） | 第 6 步拿到「一半的压缩」，必须自己写写回策略、回滚、`CompactionState` 的存放。本步为此留了三道接缝（Q1 末的表）。另外，轮内压缩在本步结束时做不到（§11.B-1） |
| **B. 全给第 5 步（含写回）** | 本步必须发明半个 Session。0027 已经拒绝过一次同样的事（`FRAMEWORK-REBUILD.md:183-185`：「There is no Session until step 6 and half of one was not worth inventing」）。工作量与风险都显著上升 |
| **C. 全给第 6 步** | 本步交付的 `budget.py` 会有一个没人调用的 `Pressure` 枚举——「resolves 但没人读」正是 0028 §11 债 #1 的形状。而且「还剩多少」与「该压了吗」是同一次估算，分到两个包要么多一条依赖边、要么抄两份估算器 |

**当初的推荐：A（维持）。owner 于 2026-09-18 采纳 A。**
三条理由里最硬的是：本步全部压缩逻辑可以用「消息列表进、消息列表出」
测到底，一个 `tempfile` 都不用；放到第 6 步就被 Session 遮住了。
**落地**：Q1 末尾已加 owner 确认块，并写明
**`FRAMEWORK-REBUILD.md:43` 那一行待 owner 后续更新，本步不许去改它**。
（选项 B / C 各自「要动哪几节」保留作存档：若选 B，§1.3 的「不做
Session」整条作废、§3.1 多一个模块、§7 多一个 Task、§11.A-2 与 §11.A-3
删除、Q1 重写；若选 C，§3.1 删 `compaction.py`、§5.3 整张表移交第 6 步、
§6 的陷阱 5/6/8/9/10/11/12/13/14/17/19/20 随之移交、Task C 取消。）

### 12-3 输出/续写预算轴的归属 —— **已裁定：正式废弃**

旧 `budget.py:317-463` 的 `TokenBudgetTracker` / `"+500k"` 解析 /
diminishing-returns 三条停止判据，回答的是「这一轮还要不要继续生成」。
**`EngineConfig` 里没有对应字段。**

| 选项 | 代价 |
|---|---|
| **A. 进 engine** | 要改 `omicsclaw/engine/`，违反 one component per step，得单独开一步 |
| **B. 进 Surface** | 每个 Surface 各实现一遍，或者共用一个 helper；`"+500k"` 这种用户语法本来就是 Surface 的事 |
| **C. 正式废弃**（**采纳**） | 长跑任务失去「花够了就停」的闸。本仓库跑 omics 分析，长跑是常态 |

**当初的推荐是 B；owner 委托调研后于 2026-09-18 裁定 C。**
推荐被调研结果推翻：**harness9 根本不做 token / 成本预算**（grep 证据
逐条列在 §5.2 末行与 §11.B-12），它的停止轴只有 `MaxTurns` / ctx 取消 /
LLM 失败三条。所以本项**随裁定 0 一起丢**，不是「换个家」。

**但 C 的代价（失去「花够了就停」的闸）有替代物。** harness9 撞上了同一
个问题，解法是**「没进展就推一把」而不是「花够了就停」**：
`WithMemoryNudge` / `WithStallNudge` / `WithPlanningGate` /
`WithClosingGate` 四件套，全在 `loop_phases.go:176-206`，配置入口在
`options.go:69-121`。
**它们属 `omicsclaw/engine/`，不属本层，本步不做**——触发条件是循环状态
（轮数、本轮调了哪些工具），只有 engine 知道。形状、标定值、真实轨迹
证据，以及**「10/12/5 与进展工具集合必须在本仓库语料上重新定义」的
警告**，全部记在 **§11.B-12**。

### 12-4 两条原先「写在 §11 里、需要 owner 点头才动的」 —— **已裁定**

- **12-4a 轮内压缩（原 §11-1 → 现 §11.B-1）**：**owner 裁定 4a**——
  形态与行号证据入档，**等完整 agent 架构就绪后由 owner 决定何时开**，
  不写排期。harness9 有现成答案且形状与本条一致：接口
  `WithCompactor(c memory.Compactor)`（`options.go:135-138`，「在每次
  LLM 调用前裁剪历史消息」）、调用点 `loop_phases.go:164-168`、纪律
  「接口定义在 engine 包（使用者侧），由 internal/context 包实现」
  （`options.go:157-159`），与 OmicsClaw 已有的
  `ConcurrencyAwareExecutor` / `DeadlineAwareExecutor` 同构。
  **与 12-3 的 nudge/gate、以及交接文档第 20 项的 context-window 上报
  合并为同一个后续步骤**——三者全在 `prepareTurnInput` 的相邻几行
  （压缩 `:164-168`、token 上报 `:173-174`、nudge/gate `:176-206`）。
  不开的后果：一个 `max_turns=50` 的长跑在中途撑爆窗口时，本步拦不住。
- **12-4b `ToolPolicy.tags` 的 docstring 已过期（原 §11-5 → 现
  §11.B-5）**：**owner 裁定 4b——harness9 无对应物，纯本仓库文档腐烂，
  归迁移任务，不归本步**（§9-4「例外：零」不变）。
  **字段该留、错的只有 docstring**，依据是
  `FRAMEWORK-REBUILD.md:733-735`：「It stays — `orchestration.py:201`
  dispatches on `"mcp" in policy_tags` — but the docstring should stop
  promising a filter that will not exist」。一行注释的修改。

---

## 附录 A —— harness9 对照原始材料

> 每条 `文件:行号` 均逐行读过。读不到或不确定的一律标「未核实」，
> **不猜**。
>
> ⚠️ **裁定 0（2026-09-18）之后，本附录的地位变了。** 它原先是
> 「harness9 侧的对照材料」，与 §5 的「旧层侧的能力表」并列；现在
> **harness9 是默认来源**，本附录里判为 port 的行就是本层的形状来源。
> 凡本轮因裁定 0 而改判的行，已在「处置」栏里标出。

### A.1 `internal/context/`（全部内容，190 + 177 行）

| 位置 | 内容 | 本计划处置 |
|---|---|---|
| `builder.go:22-31` | `DefaultPromptBuilder` 七个字段 | 改写为 `Section` 序列（Task B） |
| `builder.go:20-21` | 「Go 通过结构类型隐式满足接口，无需 import engine」 | **纪律照搬**：本层不 import engine（Q7） |
| `builder.go:35-37` | `NewPromptBuilder(workDir, idx)` | 不搬 `workDir`/`idx` 参数（Q2） |
| `builder.go:41-75` | 五个 `With*` 链式开关 | 改写为 `with_section` / `without`（不可变） |
| `builder.go:56-59` | `ltmReader` **每次 Build 调用**的理由 | **照搬并推广**（Q2-a） |
| `builder.go:68-75` | Sandbox 降级说明**优先级高于**启用说明；线上事故注释 | 逻辑照搬为两个互斥 Section（若建 sandbox） |
| `builder.go:78-104` | 基础 prompt + `time.Now()` | 日期改为组装根提供的 `SectionSource` 闭包；**本层不持有 clock、不读时钟**（Q2-d） |
| `builder.go:107-110` | AGENTS.md 不存在则**静默跳过** | 照搬语义：空 source → 整段消失 |
| `builder.go:113-119` | Skills 索引：nil 或空则跳过整块 | 照搬语义 |
| `builder.go:78-189` | `Build()` 全程**只往一个 `parts` 里塞**，`:189` `strings.Join(parts, "\n\n")` | **照搬形状与分隔符**（Q5 + 裁定 0：单一 system prompt，无 placement 拆分，见 Q5b） |
| `builder_test.go:82-85` | **Progressive Disclosure 负向断言**：skill 正文不得进 prompt | **不照搬**：渲染推到层外后本层无法违反它，归 `skill/`（§5.1、§11.B-15）。Task B 验收 5 换成可变异的「不截断、不改写 source 返回值」 |
| `builder_test.go:105-111` | 空 LTM 不注入标题段 | 照搬 |
| `options.go:157-162` | `PromptBuilder interface { Build() string }`，**定义在 engine 侧**；`:158` 原话「接口定义在 engine 包（使用者侧），由 internal/context 包实现」 | **本步不照搬**（Q7：改不了 engine）。⚠️ 同一条纪律是 §11.B-1 轮内压缩的形状依据（`WithCompactor`，`options.go:135-138`） |
| `skills/index.go:25-34` | `Summary()` = 每行 `- name: description` | 层外渲染（Q2） |

### A.2 压缩栈（`internal/memory/` + `internal/engine/`）

| 位置 | 内容 | 处置 |
|---|---|---|
| `token.go:15` | `charsPerToken = 4`，作用在 **Go 的字节长度**上 | **重新推导**（Q3、陷阱 1） |
| `token.go:19-29` | `EstimateTokens`：Content + 每个 tc 的 ID/Name/Arguments + ToolCallID。**无 reasoning** | 补 `reasoning_content` + `name`（陷阱 1） |
| `token.go:33-45` | `EstimateToolTokens`；注释：工具 schema 可吃 20-30K+ | **port**（Q3-4） |
| `token.go:49-58` | `FormatTokenCount` | port 行为，不 port switch（陷阱 15） |
| `compaction.go:10-12` | `Compactor` 接口 | 不做接口，做函数（Python 不需要） |
| `compaction.go:14-26` | `ForceCompactor` / `RecordedCompactor` 两个扩展接口 | 融合成 `compact()` 的返回三元组 |
| `compaction.go:28-69` | `SlidingWindowCompactor`（按条数） | **丢弃**（被 token 预算完全取代；harness9 自己也把 TokenBudget 标为推荐默认，`:71-77`） |
| `compaction.go:87-92` | `MaxTokens = contextWindow * 80/100`，`MinTail = 6` | 80% **改写成显式减法**（Q9）；`6` 保留为默认并标注。⚠️ **作者自己在真实 benchmark 上用的是 55% 与 `MinTailMessages: 8`**（`cmd/swebench/runner.go:293-299`，`:294` 注释把 55% 拆成「工具定义 (~25K) + 输出预留 + chars/4 估算误差」三项）——这是 Q9 与 Q9-a 的硬证据 |
| `compaction.go:95-132` | 逐条剥头直到装得下 | **port** → `fit_to_budget` |
| `compaction.go:103-105` | 首条非 system 则**原样返回** | **不 port**（Q8） |
| `compaction.go:134-179` | `CompactForce`：保任务锚 + 从新往旧贪心纳入 + 单条超预算跳过 | **port**，含 issue #117 的理由（Q10） |
| `compaction.go:181-193` | `maxTokens()` / `minTail()` 的 `<=0` 兜底 getter | **不 port**（Go 零值产物，陷阱 15） |
| `compaction.go:195-239` | `repairOrphanedToolPairs` 双向修复 | **port，但两处重判**（Q11、陷阱 1、陷阱 10） |
| `compaction.go:229-233` | 占位消息 = `RoleUser` + `ToolCallID` | **不能直译**（Q11） |
| `summarization.go:20-22` | `Summarizer` 接口，**消费者侧声明**，与 provider 同形 | 纪律照搬，签名改写（Q4） |
| `summarization.go:24-28` | `MemoryExtractor` 接口，同样消费者侧声明 | **本步不做**（归第 6 步；本步不提供钩子，需要时再加） |
| `summarization.go:30-50` | `summaryMarker` + 首次/增量两个模板，五维结构 | 被 `progressive_compactor.go` 的锚点版**取代**；只 port 后者 |
| `summarization.go:134-137` | `CompactForce` 时 `minTail` 固定为 1 | port 语义（强制压缩允许压到只剩 1 条） |
| `summarization.go:216-220` | 摘要 LLM 调用内置 60s 超时 | **不 port**（Q4-3） |
| `progressive_compactor.go:26-65` | 压缩系统 prompt + 首次/增量模板（锚点格式） | **port 结构**；文案需本地化审校 |
| `progressive_compactor.go:71-76` | 「本类型仅被单 goroutine 调用，故不加锁」 | **不 port 这个前提**（本项目轮次会重叠）→ `CompactionState` 做成入参 |
| `progressive_compactor.go:124-134` | 默认阈值 `0.60/0.70/0.80/0.95`，`MinTail=6`，`OffloadThreshold=4000` | 阈值保留+标注（Q9）；offload 阈值**不 port**（不做 offload） |
| `progressive_compactor.go:210-227` | `determineTier` 的**四档比较**（`ratio >= Emergency/Full/Soft/Warn`） | port；分母换成 `usable_tokens`（Q9） |
| `progressive_compactor.go:211-213` | `ContextWindow <= 0 → TierNone` | **不 port**（Q9-b）。原稿这一行写「port」，与 §5.2 的「保留旧层 `effective_capacity <= 0 → BLOCK`」结论相反，而分母一换两者就作用在同一条件上。裁决：`usable_tokens <= 0` → `EMERGENCY`；`context_tokens <= 0` → 构造期 `ValueError` |
| `progressive_compactor.go:230-245` | `splitHeadTail` | port，泛化 `pinned`（Q8） |
| `progressive_compactor.go:249-261` | TierWarn：只 offload，不调 LLM | **降级为「只标记压力，不动消息」**（不做 offload） |
| `progressive_compactor.go:266-301` | TierSoft：head 对半，只摘要前半 | **port** |
| `progressive_compactor.go:305-336` | TierFull：摘要整个 head | **port** |
| `progressive_compactor.go:341-352` | `tierEmergency`：跳过 LLM，直接强制截断，**始终写 `Error`** | **port**（Task C 验收 6：Emergency 档下假 summarizer 的调用次数必须为 0）。裁定 0 之后它与 `TokenBudgetCompactor` 一起，**取代**旧层的「确定性模板摘要」作为非 LLM 退路（§5.3） |
| `progressive_compactor.go:354-380` | `offloadHead` + issue #117 **别名 bug** 的防御性拷贝注释 | 不做 offload，但**别名教训 port 成陷阱 5** |
| `progressive_compactor.go:386-436` | `summarizeAndExtract`：渲染对话文本、选模板、解析、合并锚点 | **port** → `render_for_summary` + `build_summary_prompt` |
| `progressive_compactor.go:391-404` | 摘要素材渲染：`[tool_result <id>]: …` / `[<role>]: …` / `[tool_call <name>(<id>)]: <args>`，**全程不截断**（已逐行核实） | **逐行 port** → `transcript.render_for_summary`。裁定 0：旧层的 `[called tools: …]` 与 `<prior-tool-calls/>` **两者都丢**，见 §5.3 与陷阱 18 / 20 |
| `progressive_compactor.go:446-460` | `buildCompactionMsg`：`[Context Compaction]` + Anchors + Summary + Offloaded | **port**（去掉 Offloaded 段） |
| `progressive_compactor.go:488-495` | `fallbackCompact`：摘要失败 → 回退截断 + 记 `Error` | **port**（陷阱 12）。⚠️ 6 道拒收闸丢弃后，**这条与 `:341-352` 的 `tierEmergency` 是摘要路径上仅存的两道防线**，见陷阱 19 |
| `anchor.go:12-33` | 五类锚点、固定顺序、header 映射表 | **port** |
| `anchor.go:42` | `compactionMarker = "[Context Compaction]"`（**单前缀，无闭合**） | **port**（裁定 0 改判：旧层的 `<compaction-summary>` 成对标记与 `rfind` 丢弃，见 §5.3 的代价说明） |
| `anchor.go:47-100` | `ParseAnchorsAndSummary`：纯扫描，缺失填 `"N/A"`，永远 5 条 | **port**（陷阱 13） |
| `anchor.go:105-124` | `MergeAnchors`：新值中 `"N/A"` **不覆盖**旧值 | **port**（陷阱 14） |
| `record_store.go:33-48` | `CompactionRecord` **16** 字段（逐个数过：`ID`/`SessionID`/`Timestamp`/`Tier`/`TokensBefore`/`TokensAfter`/`MsgsBefore`/`MsgsAfter`/`Anchors`/`Offloaded`/`Summarized`/`PreservedTail`/`SummaryText`/`CompressionRatio`/`Duration`/`Error`） | port 其中与本层有关的；`ID`/`SessionID`/`Timestamp` **不 port**（归第 6 步）；`Offloaded` 不 port（不做 offload） |
| `record_store.go:61-72` | `RecordStore` 接口 + `FileRecordStore`（JSONL） | **不 port**（第 6 步） |
| `compaction_offloader.go:31-110` | 压缩期 offload，阈值 4000 字节、预览 10 行、按 ToolCallID 命名、cache 防重写 | **不 port**（§11.A-4） |
| `engine/compact.go:39-95` | 手动 `/compact`：注入 system → 压 → 剥 system → Clear+AddMessages，失败用独立 5s ctx 回滚 | **不 port**（需要 Session，第 6 步；§11.A-2） |
| `engine/history.go:24-45` | `buildSystemPrompt`：有 PromptBuilder 就用，否则内置默认文案 | 本项目没有这个回退层（引擎不管 prompt） |
| `engine/history.go:50-68` | system prompt **不持久化**，每次 load 时重新注入 | **纪律记下来**（第 6 步的约定） |
| `engine/history.go:95-153` | `writeBackCompaction` 三条门控 + issue #117 的完整说明 | **不 port**（§11.A-2），但把三条门控原文抄进 §11.A |
| `engine/history.go:158-179` | `persistCompacted`：Clear + Add + 独立 ctx 回滚 | 不 port（第 6 步） |
| `engine/loop_phases.go:154-219` | `prepareTurnInput`：工具列表 `:162` → 压缩+写回+上报 `:164-168` → token 估算上报 `:173-174` → nudge/gate `:176-206` → Plan 注入 `:207+` | **调用点参考**（§11.B-1）。**nudge / gate / Plan 注入本步一律不做**——它们属 engine（裁定 3）。⚠️ **三件后续工作全落在这一个函数的相邻几行**，所以 §11.B-1、§11.B-12 与交接文档第 20 项合并为同一步 |
| `engine/loop_phases.go:273-288` | `injectObservations`：空输出兜底为占位文案 | 已在 `omicsclaw/engine/executor.py` 的 `observations` 里（`EngineConfig.empty_output_placeholder`） |
| `engine/stream.go:43-49` | `EventTokenUpdate` / `EventCompaction` 两个事件类型 | **不 port**（要改 `EngineEventType`，越界；§11.B-1、Q7） |
| `cmd/harness9/main.go:215-223,262,425-443` | 组装根把 PromptBuilder 与 Compactor 接到 engine 上 | **接线形态照搬**：组装根负责，不是层自己 |
| `ltm/precis.go:16,26-32` | `precisMaxEntries = 30`（常量在 `:16`，`:15` 是它的注释）、`NewPrecis` 的 5120 字节上限（`:28-29`）、UTF-8 边界截断 | **不 port**（LTM 归第 6 步）；但 5120 的推导（blog:294）值得第 6 步复用 |
| `hooks/offload.go:18` | 执行后 offload 阈值 10000 字符 | 不 port（§11.A-4） |

### A.3 两处 blog 与代码不一致（不要被 blog 误导）

1. **blog:347-373「Non-destructive compaction: two histories」** 描述的
   是「`contextHistory` 从不改写、每轮从完整历史重算压缩视图」。
   **代码已不是这样**：`engine/history.go:95-153` 的
   `writeBackCompaction` 是 issue #117 之后引入的**写回式**压缩，
   压缩产物会替换 `lc.history` 并落盘。blog 没更新。
2. **blog:110-131「SummarizationCompactor is the default strategy」**。
   **代码的默认是 `ProgressiveCompactor`**
   （`cmd/harness9/main.go:425`），`SummarizationCompactor` 不在
   main 的接线里。

> 这两条本身就是本计划反复强调的那件事的证据：**二手叙述会过期，
> 引用必须落到行号。**

### A.4 未核实

- `internal/observability/observer.go` 中与 context 相关的部分：
  只读了 `engine/stream.go` 的事件类型定义，**没有通读 observer**。
  本计划没有任何一条依赖它。
- `internal/hooks/offload.go` 只读了阈值常量与触发条件，
  **完整的 `AfterExecute` 实现未逐行读**（本计划不 port 它）。
- `internal/memory/{manager,mem_session,sqlite_session,record_store}.go`
  只读了 `Session` 接口与 `CompactionRecord`/`RecordStore` 的类型定义，
  **实现未读**（归第 6 步）。
- `progressive_compactor_e2e_test.go` / 各 `_test.go` **未读**。
  实现者若要照搬某个边界用例，需自行核对。

---

## 附录 B —— 交付结果

**待填。留给实现后评审，本轮不得占用。** 由实现完成后、两个独立只读
评估结束、修复任务收尾时填写。应包含：交付物清单与行数、两次评估各自的
发现、**实现阶段暴露出的本计划错误**（附录 C 记的是**实现前**的那一轮，
两者分开记），以及值得带进第 6 步的教训。

> 计数口径提醒：0027 附录 B 记了 5 处计划自身的错误，0028 附录 B 记了
> 20 余处。**0029 没有交付后评审附录**——它的附录 B 是「该不该把
> harness9 的 sandbox 搬进来」（`docs/plans/0029-foundation-tools.md:794`）；
> 常被引用的「27 处」在 `FRAMEWORK-REBUILD.md:394`，指的是那一轮
> **交付代码**里的缺陷，不是计划的错。

---

## 附录 C —— 计划评审结果（实现前）

### C.1 独立只读评审 + 修复轮（实现前）

本计划在实现开始**之前**过了一轮独立只读评审，修复由既没写计划也没做
评审的第三个 agent 执行。下表每条一行：编号 / 一句话 / 处置。

**修复轮只改了本文件一个文件**，`git status --porcelain` 相对开工前
零新增改动（除本文件自身已在 `??` 列表里）。

#### 阻断

| # | 一句话 | 处置 |
|---|---|---|
| A1 | 0028 §5/§11 结转的 `speculative_classifier` / `result_policy` / `progress_policy` 在 0030 里 0 次命中，而 owner 的四项裁定不含它们 | **已修**：新增 §5.0 三行裁决；`result_policy` → 第 6 步（§11.A-18），`progress_policy` → 迁移（§11.B-17），`speculative_classifier` → **§12-1 交 owner**（唯一一项收紧权限方向的能力；owner 已于 2026-09-18 裁定，见附录 C.2 裁定 1）。⚠️ 评审的措辞「三项都被 0028 点名交给本层」不准确：只有 `speculative_classifier` 写的是「→ 装配层」，另两项 0028 分别判给了「存储/压缩层」与「loop / Surface 层」；已按 0028 原文归属 |
| A2 | `<prior-tool-calls/>` 被绑给了「摘要素材」渲染器，而它实际在模板摘要的预览器上；据此得出的「harness9 被实测证伪」不成立 | **已修**：§3.2 去重（`render_for_summary` 只留在 `transcript.py`，新增 `summary.render_message_preview`）、§5.3 拆成两行（模板侧 / 素材侧）、陷阱 20 重写、附录 A.2 加 `:401` 一行、§7 Task C 的排序理由改写 |
| A3 | Q8 的 `pinned` 泛化在公开面上不可达（两个入口都没有这个参数） | **已修**：`plan_compaction` / `compact` 补 `pinned: int = 0`；Q8 加一张「默认值算不算一次猜」的对照表与三条缓解 |
| A4 | `usable_tokens <= 0` 走哪一档，§5.2 与附录 A.2 给了相反答案 | **已修**：新增 Q9-b 三行裁决（`context_tokens<=0` → `ValueError`；`usable_tokens<=0` → `EMERGENCY`；`TierNone` 不 port），并进陷阱 2 与 Task A 验收 4 的边界清单 |
| A5 | §8.2 说「tools 版的 `_TEMPTING_NEIGHBOURS` 里没有 `omicsclaw.provider`」——事实相反，且括号里的因果也反了 | **已修**：改为「原样保留，一个字都不用加」，并给出 `tests/tools/test_tools_is_a_leaf_layer.py:61-67`、`provider` 在 `:64` 的证据。§8.2 其余四行逐条复核**全部正确**，未动 |

#### 应修

| # | 一句话 | 处置 |
|---|---|---|
| B1 | Task B 验收 5（Progressive Disclosure 负向断言）无法被任何 `omicsclaw/context/` 的变异杀死 | **已修**：改成可变异的性质「不截断、不改写 source 返回值」；原断言归 `skill/`，记入 §5.1 与 §11.B-15 |
| B2 | 陷阱 6 与陷阱 5 互斥，退路「或至少 `==`」检测不了它自己点名的危害 | **已修**：保陷阱 5，把陷阱 6 改写成「元素恒等 + 前缀字节恒等」两条可测断言，删掉「或至少 `==`」，并说明容器新建是允许且必要的 |
| B3 | `reserve_*_tokens` 默认 `0` 是放松方向，与 Q9 自己的裁决相反；`BudgetReport.tool_tokens` 与 `reserve_tool_tokens` 两源未绑 | **已修**：新增 Q9-a（两个字段**无默认值**）；§3.2 加 `tool_reserve_shortfall` 与 `max(...)` 扣减规则；Task A 验收 5/6、陷阱 2 各加断言 |
| B4 | 陷阱 3 列的四处 lane 接缝有两处无人认领，其中一处跨包却无例外授权 | **已修**：陷阱 3 改成带负责人的表；Task B 接缝责任 ③、Task C 接缝责任 ③ 补齐；陷阱 10 的跨包例外扩到 `apply_cache_breakpoints` 那一处 |
| B5 | §9-1 的「1,419 全过」把交接文档专门点名的间歇失败圆回去了 | **已修**：§9-1 改为「1,418 必过 + 一条点名豁免 + 复跑判据 + 禁止改 `_websafety.py`」。⚠️ 本轮两次实测都**没复现**（整套 `1419 passed`；`test_bash.py`+`test_websafety.py` 连跑 `167 passed`），豁免的依据是 `FRAMEWORK-REBUILD.md:541-548` 把它写成 open |
| B6 | `omicsclaw/engine/loop.py` 在计划里指两个不同的文件而无区分 | **已修**：§1.1 加全局约定（新引擎写路径，旧引擎一律写 `git show HEAD:…`），Q7、§5.2、§9-8 三处逐个标注 |
| B7 | §5 表缺 7 类行（「留空即缺陷」是 §5 自己的规矩） | **已修**：§5.1 加 4 行（两个 `should_prefetch_*`、`extract_user_text`、`should_attach_capability_context`），§5.2 加 1 行（`estimate_prompt_*`）+ 1 行（`total_estimated_tokens`/`total_chars` 在 §5.4），§5.3 加 2 行（tier-1 闸、20 秒摘要超时）。§5.5 结论行同步 |

#### 建议

| # | 一句话 | 处置 |
|---|---|---|
| C1 | Q1 理由 1 的「四个文件没有一个 import `Session`」在 Go 里是空的（同包） | **已修**：改写成「不引用该类型」并给 grep 证据；同时补全 `token.go` 的 `fmt`、`summarization.go` 的 `fmt`/`strings` |
| C2 | 5 处引用指向错误构造 + 3 处 off-by-one | **已修**：`budget:38→:46-47`、`budget:82→:72-73`、`budget:290→:199-202/:211-212`、`assembler:120→:70-71/:82-83`、`system_prompt.py:34→:13`、`budget:190→:191`、`FRAMEWORK-REBUILD.md:44→:43`、`ltm/precis.go:15→:16`；顺带 `compaction:1051→:1049` |
| C3 | 4 个用来支撑论证的数字错了 | **部分修**：injector `22→23`（AST）、marker `62→60`（AST）、`CompactionRecord` `17→16`（逐字段数）已改。**`ContextAssemblyRequest` 那条评审说错了**——见下面「评审有误」。Q5b 的 placement/order 对照表逐项复核正确，未动 |
| C4 | 三处引错本仓库自己的文档 | **已修**：4 处「0029 附录 B 的教训」全部改指 `FRAMEWORK-REBUILD.md:400-464`（保留 Q2 表里唯一正确的那一次）；「0029 有 27 处错在计划自身」在 Task D 与附录 B 两处改正；「0028 §11 债 #5」→ **#1**（Q1、Q8 各一处）。计划另一处引的「债 #10 = predicate 事件 sink」复核为**对**，未动 |
| C5 | §0 虚构了一个「交接里说旧层是 6 个文件」的对比对象 | **已修**：删掉对比，改为列出 7 个文件各自行数与复现命令。7 文件 / 3,705 行本身复核为真 |
| C6 | 陷阱 18 的前提（两个头尾比例都没验过）不成立 | **已修**：陷阱 18 从「二选一」改判为「各留各的并说明」，附 `bash.py:243` docstring 与 `FRAMEWORK-REBUILD.md:379-381` 的证据；§9-8 的措辞同步 |
| C7 | `assemble()` 的「易变段静默消失」边界没被命名 | **已修**：§3.2 列出三个边界并裁决第 3 种仍追加 user 轮；Task B 新增验收 8 + 变异 |
| C8 | Task B 验收 1 里的 `build()` 在 §3.2 中不存在 | **已修**：Q5 与 Task B 验收 1 都改成 `assemble()` 的性质，并留下更正说明 |
| C9 | Q2 表里的 `clock` 在 API 草图里没有落点 | **已修**：新增 Q2-d「本层不持有 clock，也不读时钟」，Q2 表那一行改写，Task B 验收 3 换成可变异的 monkeypatch 写法，陷阱 7 第三源同步 |

#### 评审未能核实、本轮补上的

| 项 | 处置 |
|---|---|
| 「旧组装层的 13 个测试」从未逐个点名 | **已补**：新增 §0.1，列出 13 个文件与行数（合计 4,455 行）+ 口径 + 复现命令，并点明这个名字口径**undercount** —— 另有 14 个已删测试在模块级 import 本层却不叫 `context`/`compact`，逐个列出 |
| 测试量级系数「0027 1:2.6 / 0028 1:1.5 / 0029 1:1.4」无数据源 | **已修**：删掉，换成 `find … \| xargs wc -l` 实测的三行（engine 1:2.2、tools 1:1.4、provider 1:1.3），并说明 `omicsclaw/tools/` 装着第 4 与 4.5 两步、分不开 |
| `compaction:1051` 标给 `reactive_compact` | **已校准**：`STAGE_REACTIVE_COMPACT` 追加在 `:1049`，触发在 `:1033` |

#### 评审有误（未修，附证据）

| # | 评审说 | 事实 |
|---|---|---|
| C3（第 2 项） | 「`ContextAssemblyRequest` 是 **31 字段，其中 3 个 `Callable`**，计划写的『27 字段 + 4 个可注入 loader』错了」 | **计划是对的。** AST 复核：31 个注解字段，其中 **4** 个是可注入 loader——`base_persona_loader`、**`knowhow_loader`**、`knowledge_loader`、`extension_prompt_pack_loader`。评审漏掉了 `knowhow_loader`，因为它的注解写的是别名 `KnowhowLoader`，而 `layers:85` 就是 `KnowhowLoader = Callable[..., str]`。31 − 4 = **27**，计划的「27 字段 + 4 个可注入 loader」逐字正确。**未改数字**，只加了一句可复核的分解，免得下一轮又被同样地误读 |
| A1（措辞） | 「0028 §5 点名交给**本层**的三项能力」 | 只有 `speculative_classifier`（`0028:515`）写的是「→ 装配层」。`result_policy`（`:516`）判给「存储/压缩层」、`progress_policy`（`:517`）判给「loop / Surface 层」。**结论仍然成立**（三项在 0030 里都是 0 次命中，且 `0028:801-805` 把五项并列为「家还没建」），但归属已按 0028 原文写，不按评审的转述 |
| C2（`budget:290`） | 「`:290` 是 `selected_chars = 0`」 | `selected_chars = 0` 在 `:289`，`:290` 是空行。不影响结论——`:290` 确实不是图片会计的位置，已按 `:199-202`/`:211-212` 改 |

### C.2 owner 裁定（2026-09-18）

本轮**不是评审**，是把 owner 的五条裁定（编号 0–4）与一条范围约束落进
计划，并把连带影响改干净。**本轮同样只改了本文件一个文件**，
`git status --porcelain` 相对开工前零净变化。

#### 裁定 0（总裁定）—— 「舍弃原本旧框架的相关能力，一律以 harness9 的相关能力为主」

把 §5 整张能力对照表的**默认值**换掉：
**旧框架独有 ⇒ 丢弃；harness9 有对应物 ⇒ 照 harness9 做。**

**被它掀翻的小节与行**：

| 位置 | 原裁决 | 新裁决 |
|---|---|---|
| **Q5b** | 保留 system/message 双 placement（「旧层唯一一处优于参考实现」） | **单一 system prompt**（`builder.go:78-189`），Q5b 整节重写为改判 + 代价表 |
| §2、§3.1、§3.2 | 双 placement 的 API（`Placement` / `Section.placement` / `AssembledPrompt.message_context`）、`summary.py` 的模板与闸 | 全部删除；`sections.py` ~240→~160、`prompt.py` ~360→~240、`summary.py` ~360→~200，合计 ~2,020→~1,640 |
| §5.1「placement ∈ {system, message}」 | port，本层最重要的一条 | **丢弃** |
| §5.1「渲染顺序 `sorted(order, key)`」 | port | **丢弃**，改 `with_section` 的加入顺序 |
| §5.1「memory/project_state/scoped_memory 三分」 | port 结构 | **丢弃**（三分的意义就是三个 placement） |
| §5.2「tiktoken 确定性开关」 | port，含理由原文 | **不 port 机制**；性质由「本层不 import tiktoken」自动成立 |
| §5.2「图片 token 会计」 | 本步做不了，记为债 | **丢弃**（后果保留为记录，§11.B-11） |
| §5.2「块感知裁剪」 | 两边都 port，且互补 | **只 port harness9**（逐条剥头 + 事后修复），代价：原始内容丢失 |
| §5.2「最新块超预算也保留」 | 两条都要 | **只要 harness9 的两条**（`MinTailMessages` + Emergency 跳过） |
| §5.2「输出/续写预算轴」 | 丢弃出本层，归迁移 | **正式废弃**（裁定 3） |
| §5.3「6 道拒收闸」 | port，旧层最大净胜 | **丢弃**（`:431` 无条件信任）；保留 `:488-495` 的失败回退 |
| §5.3「确定性模板摘要」 | port | **丢弃**；替代物 `tierEmergency`(`:341-352`) + `TokenBudgetCompactor` |
| §5.3「反模仿 `<prior-tool-calls/>` 渲染」 | port 到 `render_message_preview` | **丢弃整条路径** |
| §5.3「摘要素材散文渲染」 | port 旧层的 `[called tools: …]` | **照 harness9 `:391-404` 逐行 port** |
| §5.3「tier-1 闸 `_should_refine_episode`」 | port 为能力 | **丢弃**；`compact(..., min_omitted_for_summary=8)` 参数一并删除 |
| §5.3「成对边界标记 + `rfind`」 | port 旧层，不 port harness9 单前缀 | **照 harness9 单前缀** `[Context Compaction]`（`anchor.go:42`） |
| §5.3「摘要 block 累积 + 保新丢旧 + 幂等」 | port | **丢弃**；照 harness9 单份 `lastSummary` |
| §5.3「`/compact` 逐字带过降级路径」 | 融合，作降级路径 | **丢弃**；只取 harness9 的增量模板 |
| §5.3「三遍收敛」 | 记为债（原 §11-13） | **正式丢弃**，§11.A 的债 13 关闭 |
| §5.3「413 反应式重压」 | 保留为能力，家在调用方（原 §11-14） | **检测编排丢弃**，§11.A 的债 14 关闭为「接受的风险」 |
| §5.3「`_truncate_text` 70/30」 | 融合，比例统一 | **丢弃**（三个调用点全在被丢的路径上） |
| §5.4「`## User Request` 标题」 | port | **丢弃**（存在理由随 `message_context` 消失） |
| §5.4「`cache_control` 的结构性贡献」 | placement 拆分 + 字节稳定 | **只剩字节稳定** |
| §6 陷阱 18 | 「两个头尾比例各留各的」 | 重写为「本层任何渲染器都不得截断」 |
| §6 陷阱 19 | 「6 道闸每道各一条测试」 | 重写为「降级路径是唯一防线」两条防线 + 「不许自行发明替代闸」 |
| §6 陷阱 20 | `<prior-tool-calls/>` 该挂哪个渲染器 | 重写为「本层只有一个渲染器，且其输出永不回到模型视野」 |
| §6 陷阱 7 | 四个字节稳定破坏源 | 加第五源：段的顺序现在由组装根负责 |
| §7 Task B | 输入含旧 `layers/`；验收 6 测 placement 拆分；验收 8 三个边界 | 输入只剩 `builder.go`；验收 6 改测段隔离；验收 8 收成两个边界 |
| §7 Task C | 排序理由「闸要拿模板当参照物」；输入列旧 `compaction.py` 七处；验收 5/6 | 排序理由改为纯依赖；旧 `compaction.py` **不再是实现输入**；验收 5 改 `summarizer is None` 的降级、验收 6 改 Emergency 不经 LLM |
| §9-8 字面量清单 | 两组（harness9 + 旧层） | 旧层组**一个都不搬**；harness9 组补上 55% / `MinTailMessages: 8` 的双值证据 |
| §10.2 ADR 注记 | 「ADR 0024 与 0039 仍然有效」 | ADR 0039 不变；**ADR 0024 的适用范围收窄**，文本更新不归本步（§11.B-20） |
| §5.5 结论行 | 三段 | 重写为「按来源标注」四组 + 「随裁定 0 丢弃」一组 |
| 附录 A.1 / A.2 | 8 行 | 按新默认值改判并补行号证据 |

**三类不受裁定 0 影响的边界**（每条已在原位写明「本行不受裁定 0 影响，
理由：…」）：

- **(a) 已获 owner 批准的 step 1 schema 偏离**（`FRAMEWORK-REBUILD.md:
  101-106`）：**Q11** 的占位消息用 `Message.tool(...)` 而非直译
  `RoleUser`+`ToolCallID`（直译会让 `anthropic_provider.py:271-290` 按
  `role` 分派时丢掉 `tool_call_id`）；**Q3-3 / §5.2** 的 token 估算数
  `reasoning_content` 与 `name`；**§5.3** 的 `ToolCall.arguments` 逐字节
  不动（依据是 `FRAMEWORK-REBUILD.md:98-100`，不是旧框架）。
- **(b) 语言级不可直译**：**Q3** 的 token 口径（Go `len` 数字节、Python
  数码点；`token.go:15` 的 `charsPerToken=4` 直译低估中文 2–3 倍，而
  **旧层 `budget.py:191` 的码点版同样是错的**——两个都不能直接用，所以
  这里 port 的是 harness9 的**意图**）；**§5.3** 的摘要超时（harness9 埋
  60s 的前提是 `Compact` 接口感知不到取消，Python 的 async `compact()`
  没有这个前提——**旧层的 20s 同样丢弃**）；**§5.1** 的 source 异常冒泡
  （`SectionSource` 是任意可调用对象，不是 harness9 那个固定的
  `os.ReadFile`）。
- **(c) 本层叶子性**：Q2 / Q4 / Q7 / §8.2 里所有「不 import X、改走
  Protocol」的裁决，与旧框架无关，全部维持。
- **另一条不受影响、但理由是「port 意图而非保留旧层」的**：**Q9** 的
  显式减法预算式。证据是 harness9 自己写的——`cmd/swebench/runner.go:
  293-299` 在真实 benchmark 里把 80% 下调到 **55%**，`:294` 的注释把
  55% 拆成「工具定义 (~25K) + 输出预留 + chars/4 估算误差」**三项**，
  正是本裁决的三个被减数。同一条证据也钉住了 **Q9-a**（预留字段不给
  默认值）。

#### 裁定 1 —— `speculative_classifier`（原 §12-1）

**选项 B：交给 owner 后续设计的新入口/交互层**
（`FRAMEWORK-REBUILD.md:748-752`），那一层「后续再设计实现」。
掀翻：§5.0 第一行由「上交 §12-1」改为**定稿裁决**；
§11-19 → **§11.B-19「已定向：新入口层」**；§12-1 改为「已裁定」记录。

#### 裁定 2 —— 维持 Q1 的 compaction 拆分（原 §12-2）

**选项 A：维持。** 掀翻：Q1 末尾的「owner 有权推翻」块改为
**owner 确认块**，并写明 **`FRAMEWORK-REBUILD.md:43` 那一行与本裁定
并存、待 owner 后续更新、本步不许去改它**；§12-2 改为「已裁定：维持」。

#### 裁定 3 —— 输出/续写预算轴正式废弃（原 §12-3）

**harness9 根本不做 token / 成本预算**（grep 证据见 §5.2 末行与
§11.B-12）。替代物是 nudge/gate 家族（`WithMemoryNudge` /
`WithStallNudge` / `WithPlanningGate` / `WithClosingGate`，
`loop_phases.go:176-206`，配置入口 `options.go:69-121`），
**属 `omicsclaw/engine/`，不属本层，本步不做**。
与 §11.B-1 的轮内压缩、交接文档第 20 项的 context-window 上报
**合并为同一个后续步骤**（三者全在 `prepareTurnInput` 的相邻几行）。
**必须带着的警告已写进 §11.B-12**：`10/12/5` 与「进展工具 =
`edit_file`/`write_file`」是从 SWE-bench 轨迹标定的，OmicsClaw 跑 omics
分析时「连续 10 轮没写文件」可能完全正常，**阈值与工具集合都必须在本
仓库语料上重新定义**（陷阱 1）。
掀翻：§5.2 末行、§11-12 → §11.B-12、§12-3。

#### 裁定 4 —— 两条原「需要 owner 点头」的（原 §12-4）

- **4a 轮内压缩**：harness9 有现成答案且形状与 §11.B-1（原 §11-1）一致
  （`WithCompactor`，`options.go:135-138`；调用点 `loop_phases.go:
  164-168`；纪律「接口定义在 engine 侧（使用者侧）、实现在外部包」，
  `options.go:157-159`，与 `ConcurrencyAwareExecutor` /
  `DeadlineAwareExecutor` 同构）。行号证据已写进 §11.B-1，并按裁定 3
  合并成同一步。
- **4b `ToolPolicy.tags` 过期 docstring**：harness9 无对应物，纯本仓库
  文档腐烂 → **归迁移任务，不归本步**（§9-4「例外：零」不变）。
  **字段该留、错的只有 docstring**（`FRAMEWORK-REBUILD.md:733-735`）。
  掀翻：§9-4 补依据、§11-5 → §11.B-5、§12-4。

#### 范围约束（owner，同日，在本轮开工后到达）

> 「你当前的目标是集中优化 context 即可，其他无关的组件可以暂时放一下，
> 后续等我搭建起完整的 agent 架构之后，再考虑进行相关优化。」

它**不改变裁定 0–4 的任何结论**，只改变其余各项的**呈现方式与紧迫度**。
落地四处：

1. **§11 重新分组**：**§11.A**（context 本体 + Q1 留给第 6 步的三道
   接缝：债 2/3/4/7/8/9/18，外加已关闭的 13/14）；
   **§11.B**（跨组件形态记录：债 1/5/6/10/11/12/15/16/17/19，外加新增的
   20）。**编号沿用原表**，所以全文既有的交叉引用仍然指得准。
   §11.B 的标题明写「**等完整 agent 架构就绪后再议**」。
2. **§1.2 加了范围声明**：本步目标是把 `omicsclaw/context/` 一个组件做
   扎实；跨组件联动优化一律延后，**不预留工期、不作验收前提**。
3. **§12 与 §11.B 的措辞**从「建议 owner 单独开一步」改成「形态与行号
   证据入档，等完整架构就绪后由 owner 决定何时开」。**形状与行号一个
   都没丢**——它们是这次调研的产物。
4. **全篇复查**：Q7「补法（留给 owner 决定）」改为指向 §11.B-1；
   §5.5 第三段加了「等完整架构就绪后再议、不是本步前置条件」的前置句；
   §9 验收清单里没有任何一条以跨组件工作为前提（已逐条核对）。
