# 计划 0027 — ReAct 主循环

框架分阶段重建的第 3 步（见 `docs/FRAMEWORK-REBUILD.md`）。第 1 步
（`omicsclaw/schema/`，ADR 0077）与第 2 步（`omicsclaw/provider/`，
计划 0026）已交付；本步写的是驱动这些类型流动的循环。

本文档有**两个纪元**。

- **第一纪元 · §1–§11 + 附录 A/B —— 已交付**（2026-09-17）。六个任务
  全部完成，两轮独立只读评估（正确性 + harness9 对照）已执行并把发现
  修完。测试 **635 passed**。结果见附录 B。
- **第二纪元 · §12 —— 已交付**（2026-09-21）。两轮独立只读审核（计划）+
  一轮独立实现 + 一轮独立代码评估，发现已修完。测试 **1197 passed**。
  交付结果与评估发现见 §12.11。owner 裁定引擎
  应当像 harness9 那样自持 workDir / Session / PromptBuilder / PlanStore /
  审批事件。§12 是对这条裁定的落地方案：它**收下其中两样**（PromptBuilder、
  Session 的边界），**驳回另外三样**（workDir、PlanStore、审批事件）并
  逐条给理由，同时**正面推翻 §1「非目标」的第 2、3 条**。

§1–§11 与附录 A/B **保持 2026-09-17 交付时的原文不动**——它们是那次交付的
忠实记录。被 §12 取代的裁定在原处就地加一行「§12 已推翻」的标注，而不是
改写正文：一份被回填成"当时就想对了"的计划，下一个读它的人就再也无法
分辨哪些结论是当时挣来的、哪些是事后补的。

## 1. 目标

一个把 ReAct 循环推到收敛的引擎：

```
Message → ToolCall → ToolResult → Message
```

循环持有 Turn 编排、工具调度、Observation 注入与终止判定。除此之外
一概不持有——不做 prompt 装配（第 5 步）、不做会话持久化（第 6 步）、
不实现工具（第 4 步）。

> **§12 已推翻「除此之外一概不持有」。** 循环还应持有**一次 exchange 的
> 生命周期**：向 prompt 源要一份 system prompt、从会话取历史、跑到收敛、
> 报告本次新增了哪些消息。持有的是**生命周期**，不是 prompt 装配器、
> 不是会话存储——两者仍在引擎外，经引擎自己声明的 Protocol 结构化接入。

```python
from omicsclaw.engine import AgentEngine, EngineConfig

engine = AgentEngine(provider, tools, EngineConfig(max_turns=50))

result = await engine.run(messages)               # 阻塞
async for event in engine.run_stream(messages):   # 流式
    ...
```

### 非目标

- **不接线。** 与第 1、2 步一样，本步交付后没有任何调用方。legacy 的
  `run_engine_loop` 继续原样服务所有 Surface。
- **不构造 prompt。** `run()` 收到的是已装配好的会话。决定什么东西
  *进入*这条会话是第 5 步（`context/`）的事。
  > **§12 已部分推翻。** 「决定什么进入会话」仍归 `context/`；但
  > 「**去问**装配器要一份 system prompt」归引擎（§12.4 的 `PromptSource`）。
- **不做历史持久化与压缩。** harness9 的 engine 持有 `memory.Session`
  与 `memory.Compactor`，两者都属于第 6 步。
  > **§12 已部分推翻。** 压缩已由 0035 的 `HistoryCompactor` 收进引擎；
  > 持久化仍不归引擎，但「**本次 exchange 新增了哪些消息**」这条边界归
  > 引擎（§12.4.2 的 `Conversation.commit`）。
- **不实现工具。** 只定义循环调用所经过的 Protocol。
- **不做 nudge、plan store、权限模式、observer/OTEL 接入。**
  harness9 的 `engine/` 里这五样俱全，但每一样都需要一个尚不存在的层。
  是推迟，不是否决。

## 2. 接口

### harness9 的形状

```go
func NewAgentEngine(p provider.LLMProvider, r tools.Registry, workDir string, opts ...Option) *AgentEngine
func (e *AgentEngine) Run(ctx context.Context, userPrompt string) error
func (e *AgentEngine) RunStream(ctx context.Context, userPrompt string) (<-chan Event, error)
```

两个入口共享一个 `runLoop` 内核，输出侧的差异通过一个含五个回调的
`emitter` 结构体注入。

### 建议的 Python 形态

```python
class AgentEngine:
    def __init__(
        self,
        provider: LLMProvider,
        tools: ToolExecutor,
        config: EngineConfig | None = None,
    ) -> None: ...

    async def run(self, messages: Sequence[Message]) -> RunResult: ...

    def run_stream(
        self, messages: Sequence[Message]
    ) -> AsyncIterator[EngineEvent]: ...   # 不是 async def，沿用 LLMProvider 的先例
```

对 harness9 的四处偏离，每一处都是有意的：

**收发整条会话，而不是一个 prompt 字符串。** harness9 接收
`userPrompt string`，其余历史从它的 Session 里加载。在第 6 步之前没有
Session，而在这里临时发明半个 Session，正是这次重建要避免的那种耦合。
`run()` 收下 messages 并返回完整轨迹，历史归调用方所有。这也更诚实地
表达了循环真正需要什么。

**返回 `RunResult`，而不是 `error`。** Go 的 `Run` 只返回一个 error，
调用方事后自己去读引擎的历史；harness9 撞上 `maxTurns` 时**丢弃整条
轨迹**。一个 frozen 的结果记录既保住了这些工作，也给 `stop_reason`
找到了落脚处。

**没有 `workDir`。** 它被传进 harness9 的 engine，却只被它的工具层使用，
循环本身从不碰。它属于第 4 步。

**没有 `context.Context` 参数。** Python 的对应物是环境自带的：取消以
`CancelledError` 的形式到达最近的 `await`，超时来自 `asyncio.timeout`。
显式加一个 ctx 是转写，不是翻译。

### 本步持有的类型

第 1 步曾起草又移除的三个名字（`AgentStep`、`Trajectory`、`StopReason`），
本步是它们的归属步骤。答案是**三取其一**：

```python
class StopReason(StrEnum):
    CONVERGED = "converged"    # 助手轮未发起工具调用 —— ReAct 的收敛出口
    MAX_TURNS = "max_turns"    # 触及 Turn 上限
    TRUNCATED = "truncated"    # 输出上限把这一轮拦腰截断
```

- **`StopReason` —— 要。** 循环有三种停法，而 harness9 只靠 error 字符串
  区分它们。一个枚举是让「到底是跑完了还是没地方了」能由数据回答的最
  廉价手段。注意**缺席**的两项：没有 `ERROR`，也没有 `CANCELLED`，因为
  两者都不是返回值——见 §4。
- **`Trajectory` —— 不要。** 轨迹就是 `RunResult` 上的
  `tuple[Message, ...]`。给一串消息套一层包装类型，只有在需要给这串
  消息挂注解时才值回票价；目前没有这样的需求。
- **`AgentStep` —— 不要。** 一条 per-turn 记录，唯一说得通的消费者是
  持久化，而那是第 6 步。在存它的那一层出现之前就定死它的形状，正是
  第 1 步靠移除它所避开的错误。

```python
@dataclass(frozen=True, slots=True)
class RunResult:
    messages: tuple[Message, ...]   # 完整轨迹，含输入
    stop_reason: StopReason
    usage: Usage = field(default_factory=Usage)   # 跨 Turn 累加
    turns: int = 0

    @property
    def final_message(self) -> Message | None: ...
```

`EngineEvent` 沿用 `StreamChunk` 已确立的形状——单个 frozen dataclass，
带一个枚举 tag，按变体在文档中说明字段有效性——而不是六个小类的联合。
与第 1 步已交付的 schema 保持一致，胜过穷尽式 `match` 那点边际收益：

```python
class EngineEventType(StrEnum):
    TEXT_DELTA = "text_delta"
    REASONING_DELTA = "reasoning_delta"
    TOOL_START = "tool_start"
    TOOL_RESULT = "tool_result"
    TURN_END = "turn_end"
    DONE = "done"          # 携带 RunResult
```

没有 `ERROR` 事件。见 §4。

### 工具缝

循环需要一双手，但不需要知道这双手是怎么造出来的。于是它声明能让自己
行动的最小 Protocol，第 4 步**结构化地满足它——完全不 import 本模块**，
与计划 0026 为 `LLMProvider` 所作的论证一致：

```python
@runtime_checkable
class ToolExecutor(Protocol):
    def available_tools(self) -> Sequence[ToolDefinition]: ...
    async def execute(self, call: ToolCall) -> ToolResult: ...
```

两个方法。本地执行策略——风险等级、审批模式、并发安全性、工作目录——
被刻意排除在外，与 `ToolDefinition` 排除它们的理由相同：那是工具层的
事务，且绝不能进入 prompt。

## 3. 文件

```
omicsclaw/engine/                 （须先完成 task 0 才可用 —— 见 §6）
├── __init__.py          ~45   公开接口面
├── types.py            ~150   StopReason、RunResult、EngineEvent(+Type)、EngineError
├── config.py            ~80   EngineConfig
├── executor.py         ~140   ToolExecutor Protocol + 单 Turn 并发调度
├── retry.py            ~120   带重试的生成调用，双档预算，基于 ProviderError
└── loop.py             ~260   AgentEngine —— run() / run_stream() 共享一个内核
                        ~795
tests/engine/                     （须先完成 task 0 才可用）
├── test_types.py              StopReason / RunResult 语义
├── test_config.py
├── test_executor.py           顺序、超时隔离、会抛异常的 executor
├── test_retry.py              预算选择、取消不重试、退避封顶
├── test_loop.py               ReAct 循环，三种 stop reason 全覆盖
├── test_loop_stream.py        事件序列、DONE 载荷、chunk→event 映射
└── test_engine_is_a_leaf_layer.py   AST 分层守卫（见 §9.4）
```

无网络，无厂商 SDK。provider 与 tool executor 都是 Protocol，因此每个
测试都由本地 fake 驱动。

## 4. 决策

**Q1 —— `AgentStep` / `Trajectory` / `StopReason`？** 只回来
`StopReason`。理由见 §2。

**Q2 —— `omicsclaw/engine/` 名字碰撞怎么办？** 先驱逐。这个名字不只是
被占用，而是根本不可用：

```
$ python -c "import omicsclaw.engine"
  File "omicsclaw/engine/__init__.py", line 22, in <module>
    from .loop import (...)
  File "omicsclaw/engine/loop.py", line 22, in <module>
    from openai import APIError
ModuleNotFoundError: No module named 'openai'
```

legacy 的 `__init__.py` 会 eager import 自己的 `loop.py`，而后者在模块
作用域 import `openai` SDK。所以在这次重建自己的测试环境里，
`omicsclaw.engine.<任何东西>` 都导不进来；即便在装了 SDK 的环境里，新层
也会连带拖入整个 legacy agent 栈——使它的分层测试变成一句空话。

legacy 包移动到 **`omicsclaw/runtime/engine/`**。这不是贴「legacy」标签，
而是 AGENTS.md 早已指派给它的边界（"`runtime/` —— agent loop、context
assembly、tool registry、policy、transcript storage"），也是这份代码今天
实际的行为：它当前就从 `omicsclaw.runtime.*` 导入八个符号，因此这次移动
是把一个既有的跨包环变成包内环。见 §6 的 task 0。

**Q3 —— 错误约定：一律 raise。** 不设 `ERROR` 事件，也不捕捉本不该捕捉
的东西。

- **Provider 故障**以 `ProviderError` 向上传播。第 2 步已经在 raise 与
  error chunk 之间做过选择；循环不重新翻案。
- **`run_stream` 同样 raise。** harness9 需要 `EventError`，是因为 Go 的
  channel 装不下异常。async generator 装得下——消费者的 `async for` 会在
  迭代点重新抛出，这正是 Python 调用方已经预期的行为。发明一个 error
  事件，等于要求每个消费者手写一个语言本已免费提供的分支。
- **取消不是错误。** `CancelledError` 与 `GeneratorExit` 原样传播——绝不
  转成结果，绝不记为失败。捕获 `Exception`，绝不捕获 `BaseException`；
  这条注释第 2 步的 Anthropic adapter 里已经写着。
- **`StreamChunkType.ERROR` 不再是死代码。** 债务表问的是哪条约定胜出，
  好让循环不必背一个不可达分支。它以**转换**的方式胜出：我们的两个
  adapter 从不 yield error chunk，但第三方 adapter 只要满足 `LLMProvider`
  就可能 yield，因此循环把它转成抛出的 `ProviderError`。三行代码，按契约
  可达，用一个会 yield 它的 fake provider 来测。删掉这个枚举成员则要动
  `schema/`，且毫无收益。

**Q4 —— 工具接口：只要 Protocol。** `executor.py` 里两个方法，零实现。
第 4 步的 `omicsclaw/tools/` 结构化地满足它。但调度*策略*——并发、
单工具超时、结果顺序——留在这里，因为那是循环的事务：harness9 把
`tools_exec.go` 放在 `engine/` 内正是同一个理由。

**Q5 —— `StreamChunk.finish_reason` 修订：现在就收。** 见 §5。

**Q6 —— `max_turns` 默认值：50。** harness9 用 500，是为长程编码任务调的。
legacy 循环用 `OMICSCLAW_MAX_TOOL_ITERATIONS=20`，而
`docs/evaluation/cross-agent-benchmark-guide.md` 记录了 20 太低——它会卡死
30 轮量级的 benchmark 任务。50 越过了这个已知的失败点，又不至于在首个
版本就放任 500 轮的失控。可配置；本层不读任何环境变量。

## 5. 本步唯一收下的 schema 修订

`StreamChunk` 没有 `finish_reason`（见 `FRAMEWORK-REBUILD.md` 的
"Debts carried forward" 表）。这笔债的后果恰好全部落在本步头上：一条被
输出上限截断的流，与一个正常说完话的模型**无法区分**，于是循环会报
`CONVERGED`，把一个被砍断的答案当作已完成的任务交给调用方。

两个 adapter 其实都已经读到了这个值，然后把它丢在地上：

| Adapter | 值在哪里 | 死在哪里 |
|---|---|---|
| `openai_provider.py` | `choices[0].finish_reason` | `_stream()` → `StreamChunk.done(msg, usage)` |
| `anthropic_provider.py` | `message_delta` → `delta.stop_reason` | 同上，805 行 |

修法是加一个带默认值的 additive 字段，外加每个 adapter 约四行，外加测试，
外加在 ADR 0077 上追加一条修订说明。见 §6 的 task 1。

**这是对「一步一组件」规则一次已声明的例外，而不是对它的破坏。** 该规则
存在的意义，是让 `git status --porcelain` 里一个无法解释的 ` M ` 可被读作
缺陷。一次有计划、有记录、单字段、带独立任务与独立验收标准的修订，与它
所防范的静默范围漂移恰好相反。

**范围纪律：只收这一条。** 第二笔 schema 债务——`Message` 无法携带
Anthropic 的 thinking-block signature——**不收**。无论如何循环都会持久化
并回放 `reasoning_content`；出站时丢弃未签名的 thinking block 是 provider
层已交付的行为，循环不改变它。它继续留在债务表里。

## 6. 任务切分

六个任务。task 0 与 task 1 排在其余任务之前；A 阻塞 B 和 C；D 为本步把关。

> **实施期修正（2026-09-17）：B 与 C 并非相互独立。** 本节原写作「B 与 C
> 相互独立」，那只在*文件归属*上成立——两者不写同一个文件。但 B 的
> `loop.py` 要 import 并调用 C 的 `execute_tool_calls` / `observations`，
> 所以在 C 落地之前 B 连自己的测试都跑不起来。实际执行顺序改为
> **A → C → B**。文件归属的划分不变。

**Task 0 —— 驱逐**（一次独立的重构；不占用第 3 步的 additive 预算）。
把 `omicsclaw/engine/` 移到 `omicsclaw/runtime/engine/`，`tests/engine/`
移到 `tests/runtime/engine/`。更新唯一的生产导入
（`omicsclaw/runtime/agent/loop.py:87`）以及四个点名旧路径的测试文件
（`tests/engine/test_loop.py`、`tests/engine/test_identity_anchor.py`、
`tests/engine/test_dependencies.py`、`tests/test_agent_dispatcher.py:669`、
`tests/test_research_stance_persona.py` ×3）。纯路径改名，零行为变更。

> **实施期修正：本清单漏报了一个文件。** 实际还需改
> `tests/bot/test_commands_registry.py` 的一行 docstring 路径引用——它提到
> `omicsclaw/engine/`，是改名的机械后果。独立评估把它记为一条 finding，
> 判定正确：清单点名 5 个文件，实际是 6 个。漏报的是清单，不是纪律。

> **唯一真正的风险，而且必须被证明而不是被论证。**
> `omicsclaw/runtime/__init__.py` 有 391 行 eager 再导出，因此 import
> `omicsclaw.runtime.engine` 会先执行它。它目前会到达
> `.agent.query_engine`，但**不会**到达 `.agent.loop`——也就是 legacy
> engine 的导入方；而且 `runtime/agent/state.py` 早已用惰性 import
> `runtime.agent.loop` 来规避的正是这一类环。所以预期不会新增包初始化期
> 的依赖边。预期 ≠ 已验证：该任务必须在移动前后各跑一遍受影响的测试套件
> 并对比结果。若环真的咬人，退路是
> `omicsclaw/runtime/agent/legacy_engine/`——它位于那个会处于初始化中途的
> `runtime/__init__.py` 之下。

**Task 1 —— `finish_reason` 修订。** `schema/stream.py`（字段 +
`done()` 参数）、两个 adapter、它们的测试，以及追加到 ADR 0077 的一条修订
说明。additive 且带默认值：所有既有调用点继续可用——这一点由未被改动的
396 个测试来证明。

**Task A —— 类型、配置、工具 Protocol。** `types.py`、`config.py`，以及
`executor.py` 的 Protocol 那一半，配 `test_types.py` 与 `test_config.py`。

**Task B —— 循环内核。** `loop.py` 与 `retry.py`。覆盖陷阱
3、4、7、8、9、10、11、12。

**Task C —— 工具并发调度。** `executor.py` 的执行那一半，以及 Observation
注入。覆盖陷阱 1、2、4、5、6。

**Task D —— 独立评估。** 见 §8。

每个实现任务在动手写代码之前，必须先读 `omicsclaw/schema/`、
`omicsclaw/provider/base.py`，以及对应的 harness9 文件
（`internal/engine/agent_loop.go`、`loop_phases.go`、`tools_exec.go`、
`retry.go`、`stream.go`）。

### 内核缝

`run()` 与 `run_stream()` 必须共享 Turn/工具/Observation 逻辑的**唯一
一份**拷贝；并且 `run()` 必须调 `provider.generate()`，`run_stream()` 必须调
`provider.generate_stream()`——阻塞调用方不该为流式买单，而 `generate()`
是那条 `finish_reason` 从未有过疑问的路径。

Python 无法照 harness9 的写法表达这一点：PEP 525 禁止 async generator 里
出现非空 `return`，所以 Turn 策略没法既 yield 事件又返回一个 `Completion`。
建议形态是让策略填写一个小的可变 outcome holder：

```python
async def _blocking_turn(self, msgs, tools, out: _TurnOutcome) -> AsyncIterator[EngineEvent]:
    out.completion = await self._provider.generate(msgs, tools)
    return
    yield  # pragma: no cover —— 让本函数成为 async generator
```

任何等价的缝都可接受。不可谈判的是那三条约束：逻辑只有一份拷贝、
`run()` 走 `generate`、`run_stream()` 走 `generate_stream`。

## 7. 陷阱

每一条都是必备的回归测试。来源：harness9 自己的修复注释，以及在 Go 里
没有对应物的 Python 特有风险。

1. **Observation 的顺序必须与 ToolCall 一致。** harness9 为此按下标预分配
   结果切片。`asyncio.gather` 保序；`as_completed` 与 task 集合不保序。
   一次错位配对会把结果 B 挂到调用 A 的 id 上，于是模型基于错误的
   Observation 推理——静默地，且永久地。

2. **空的工具输出在部分 backend 上是 400。** harness9 用占位文案兜底，
   并注明：空的 `tool_result` 会被某些 backend 直接拒绝，即便被接受，一条
   不携带任何信息的 Observation 也白白浪费一轮。要在引擎里兜底，在消息
   到达 adapter 之前。

3. **被截断的一轮不是收敛的一轮。** `finish_reason` 指示触及输出上限 ⇒
   `StopReason.TRUNCATED`，**并且本轮的工具调用不予执行**——从一条中途
   停在参数里的流累积出来的调用可能只解析了一半，照着它行动严格劣于
   停下来。

4. **取消不是失败。** `CancelledError` / `GeneratorExit` 原样传播，穿过
   循环、穿过工具调度、穿过重试。捕获 `Exception`，绝不捕获
   `BaseException`。

5. **会抛异常的 tool executor 不得杀死整条 run。** 把 `execute` 包成
   `ToolResult(is_error=True)`。第 4 步将提供的 registry 预期自己会这么做；
   但引擎不能假定第三方实现也会。把错误给模型看，正是
   `ToolResult.is_error` 存在的理由。

6. **单个工具的超时不得取消它的同伴。** 每次调用有自己的
   `asyncio.wait_for`；harness9 为此专门派生 per-tool context。一个慢工具
   应降级为一条 `is_error` Observation，而不是一轮全死。注意 3.11+ 的
   `wait_for` 抛的是 `TimeoutError`，它**不是** `CancelledError`——陷阱 4
   不得把它一并吞掉。

7. **每轮重读工具列表。** harness9 每轮重读，因为注册表内容会在运行期
   变化（MCP 是异步注入的）。在构造时把 `available_tools()` 缓存一次，会
   静默隐藏所有晚注册的工具。

8. **追加到历史的必须是完整的助手消息。** 不是展示视图，也不是截断版。
   harness9 的注释：本地历史必须完整增长，否则后续轮次会丢失这条助手
   消息，Anthropic 的交替约束也会被破坏。

9. **`max_turns` 在调用之前检查，不是之后。** harness9 先自增再判
   `turns > maxTurns`，因此 `max_turns=1` 恰好允许一次模型调用。两侧边界
   各写一个测试。

10. **`StreamChunkType.ERROR` 转换为抛出的 `ProviderError`。** 尽管两个
    已交付的 adapter 都不 emit 它，它按契约仍然可达。用一个会 yield 它的
    fake provider 来测。

11. **一次没有产出 completion 的模型调用是契约违规——而且破的是
    provider 的契约。** 两种形状：流在没送 `DONE` chunk（或 `DONE` 不带
    message）的情况下结束；以及阻塞路径上 `generate()` 直接返回 `None`、
    流式路径上 `generate_stream()` 返回的根本不是迭代器。绝不能当成空的
    一轮处理——那等于在一条已经断掉的连接上报告成功；也绝不能不加判断
    就解引用——`LLMProvider` 是结构化 Protocol，`runtime_checkable` 只比对
    方法名、从不校验返回类型，所以「`Completion.message` 不可为空」拦不住
    任何东西，放行的结果是未捕获的 `AttributeError`（流式侧是
    `TypeError`），而它们不在任何重试预算里，`generate_retries=5` 一次机会
    都买不到。这与陷阱 5（会抛异常的 tool executor）、陷阱 10（第三方
    adapter emit 的 ERROR chunk）是同一条标准：第三方实现者的错误不得
    杀死一整条 run。

    **抛 `ProviderError`，不是 `EngineError`。** 归属正确，它才会落*进*
    重试预算而不是落在预算旁边：harness9 两处都返回普通 error 交给
    `generateWithRetry`（`retry.go:64-68`、`stream.go:244-246`），各给三次
    机会；判成 engine 自己的不变量破裂，就会让「被丢弃的半条流」——
    `retry.py` 开篇点名的那个场景——成为这个预算唯一吞不下的失败，第一次
    出现就杀掉整条 run。检测点必须在**单次 attempt 之内**（`_attempt`），
    否则只改异常类型仍然不会被重试。`EngineError` 相应收窄为本包自己写的
    代码破了自己的不变量，目前可达的只有「内核结束却没 emit `DONE`
    事件」一处。

12. **重试不得重试不可重试的东西。** 不重试已取消的作用域，也不重试
    非瞬时的 4xx。本层在这一点上优于 harness9：harness9 靠对错误文本做
    子串匹配来分类，因为 Go 的 SDK 包装丢掉了类型，而我们有
    `ProviderError.status_code` 这个结构化信号——子串检查保留为
    `status_code is None` 时的兜底，而那恰好是第 2 步设计这个 `None` 所要
    表达的「从未到达网络」那种情形。

## 8. Task D —— 独立评估（本步的关卡）

一个**独立的**子代理，且未参与任何代码的编写。它负责判断，不负责建造。
**只读**：它不修任何东西，也不碰任何东西。发现写进它的报告；修复在之后
作为独立任务派发。

三个问题，用证据回答：

1. **它对吗？** ReAct 循环真的会收敛、会终止、会把 Observation 与它的
   调用配对吗？三种 stop reason 都可达且可区分吗？测试考的是行为，还是
   在拿实现自己的输出当断言？采用第 2 步的纪律：**用变异验证，而不是
   看绿**——把那行改坏，确认点名的测试变红，恢复，确认逐字节一致。
2. **它追平 harness9 的能力了吗？** 逐条对照 §7 的陷阱，逐个特性对照
   `internal/engine/*.go`。凡是 harness9 的 engine 做了而这里没做的，全部
   点名，并逐条说明它是被 §1 的非目标推迟的，还是单纯漏掉的。
3. **每个任务都待在自己的车道里吗？** `git status --porcelain` 应当只在
   两处显示改动：task 0 的移动，与 task 1 那三个被修订的文件。任何其它
   ` M ` 本身就是一条 finding。

报告必须把**已确认缺陷**（每条附一个具体的失败场景）、**相对 harness9
的缺口**、**风格类意见**三者分开陈述；对无法验证的事项必须明说，而不是
默认它通过。

## 9. 验收标准

1. `tests/engine/` 在无网络、两个厂商 SDK 均未安装的条件下通过。
2. task 1 的修订之后，`tests/schema/` + `tests/provider/` 既有的 396 个
   测试仍然通过。
3. task 0 的移动是行为中性的：触及 legacy engine 的测试套件在移动前后
   给出相同结果。
4. `omicsclaw/engine/` 除 `omicsclaw.schema` 与 `omicsclaw.provider` 外不
   从 `omicsclaw` 导入任何东西——由一个仿照
   `tests/schema/test_schema_is_a_leaf_package.py` 的 AST 测试强制执行。
5. 无导入环：在没有厂商 SDK 的环境下 `python -c "import omicsclaw.engine"`
   成功。

   > **实施期修正：本条原文的后半句不可能满足。** 原文还要求「与
   > `omicsclaw.runtime.engine` 以两种顺序互相导入均成功」。但
   > `runtime/engine/loop.py` 在模块作用域 `from openai import APIError`，
   > 所以无 SDK 时它**在任何顺序下都导不进来**——这正是 §4 Q2 用来论证
   > 必须驱逐的那个事实。标准写的是一个与它自己的前提矛盾的条件。
   > 本条要保护的性质（两个包不构成导入环）已用 openai stub 验证：
   > `engine→runtime.engine` 与 `runtime.engine→engine` 两个方向均干净。
6. §7 的每一条陷阱都有一个点名的回归测试。
7. 对新文件执行 `awk 'length > 88'` 不输出任何内容（本机装不了 `black`，
   见 `FRAMEWORK-REBUILD.md` 的 "Working conventions"）。
8. 除 task 0 的移动与 task 1 的三个文件之外，本步纯 additive。

## 10. 验证

```bash
/opt/conda/envs/rapids_singlecell/bin/python -m pytest \
    tests/schema/ tests/provider/ tests/engine/ \
    -p no:cacheprovider -q -o addopts=""
```

本仓库要求 Python 3.11+，而本机默认的 `python3` 是 3.10。`pytest-asyncio`
**未**安装（尽管 `pyproject.toml` 里声明了），因此异步测试用 `asyncio.run`
驱动——`tests/provider/` 已经是这么做的。`tests/runtime/` 里另外约 112 个
既有失败是这个缺失的插件导致的，不是回归。

## 11. 第 4 步继承什么

- `ToolExecutor` 是一个没有实现的 Protocol。第 4 步的 `omicsclaw/tools/`
  提供实现，且必须结构化地满足它，不 import `omicsclaw.engine`。
- §1 非目标里的全部内容：prompt 装配、会话持久化、压缩、nudge、
  plan store、权限模式、可观测性接入。
- `Message` 的 thinking-signature 债务，有意未动（§5）。
- 计划 0026 §10 仍然开着：把既有的 `omicsclaw/providers/`（复数，
  2,426 行）折叠进单数包。本步不影响它，也未开工。

以下四条由独立评估补入——它们是**翻译中丢失的东西**，不写下来就会在
后续步骤里被当成从未存在过：

- **`context.Context` 的第三样载荷：值。** §2 论证「不要 ctx 参数」时
  只枚举了取消与 deadline 就停了。值是第三样，而且恰恰是 harness9 的
  engine 真正用它做事的那一样（审批回调、子代理进度，见附录 A #36）。
  第 4 步要么给 `ToolExecutor.execute` 加可选参数，要么确立 `contextvars`
  约定——`executor.py` 的 `ensure_future` 会复制当前 context，所以后者
  可行，但必须写明，不能靠巧合。
- **deadline 的传播靠显式清理，不是「环境自带」。** 外层
  `asyncio.timeout` 确实能到达工具，但那是因为 `execute_tool_calls` 的
  `finally` 显式 cancel + gather 了自己的游离 task；这些 task 用
  `ensure_future` 创建，**不是**调用方 task 的子任务。这没问题，但它
  是一项被维护出来的性质，不是白拿的。
- **`MAX_TURNS` 在流式路径上不再响。** harness9 撞上限时发 `EventError`，
  Surface 想漏都难；这里是一个 `DONE` 带 `stop_reason=MAX_TURNS`。只检查
  「有没有抛」的消费者会当成成功。**每个 Surface 都必须 branch on
  `stop_reason`**——这是保住轨迹（反超 #1）的代价，接线时必须付。
- **截断的一轮会在轨迹末尾留下未被回答的 `tool_use` 块。** 陷阱 3 要求
  不执行它们；而 1:1 规则只覆盖*已执行*的轮次。所以从一条 `TRUNCATED`
  轨迹续跑的调用方必须先回答或丢弃这些调用，否则 Anthropic 会 400。
  这是第 6 步（续跑）的一条硬约束。

## 12. 引擎层终态 —— 对照 harness9 `agent-loop.md`

**状态：已起草，未实现**（2026-09-20）。owner 裁定见本文档头部「第二纪元」：
引擎应当采取 harness9 `docs/核心功能/agent-loop.md` 那一套设计，自持
workDir / Session / PromptBuilder / PlanStore / 审批事件。

**参考实现**：harness9 `docs/核心功能/agent-loop.md`（全文 770 行，§1 架构
总览、§4 循环流程、§5.5 依赖注入 + 函数选项、§10 设计原则总结、§末
PromptBuilder 与 Skills 集成）；源码 `internal/engine/agent_loop.go:38-65`
（`AgentEngine` 结构体）、`options.go:19-162`、`history.go:24-80`、
`loop_phases.go:33-60`、`stream.go:122-129`。

### 12.1 先把"参考实现更内聚"这件事说准

实测 harness9 源码后必须先纠正一个前提：owner 点名的那五样，**持有方式
并不同质，其中四样带耦合代价**。

| harness9 的持有物 | 实际形态 | 耦合方向 |
|---|---|---|
| `promptBuilder` | **`engine` 包自己声明的 interface**（`options.go:160-162`，注释原文：「接口定义在 engine 包（使用者侧），由 internal/context 包实现。引擎通过此接口与 Context Engineering 模块解耦。」） | 无 |
| `workDir` | `string` | 无 |
| `session` / `compactor` | `memory.Session` / `memory.Compactor`，是接口，但**声明在 memory 包** | `engine → memory` |
| `planStore` | `*planning.PlanStore`，**具体结构体，不是接口** | `engine → planning` |
| 审批事件 | `emitter.approval hooks.ApprovalFunc` + `engine.ApprovalRequest{… ResponseCh chan hooks.ApprovalResponse}` | `engine → hooks` |

更关键的一处：harness9 的 `memory.Session` 接口**自身**就 import 了 planning
（`memory/session.go:21-25`，`GetPlan` / `SavePlan` 收发 `[]planning.PlanItem`），
所以那边存在一条实打实的 `engine → memory → planning`。

**结论：harness9 在这件事上不是"高内聚低耦合"的范本，是"高内聚、中等耦合"。**
`agent-loop.md` §10 自己列的十一条设计原则里，"接口隔离"只点名了
`LLMProvider` 和 `Registry` 两条——恰恰是 Session / PlanStore / hooks 那三条
**没有**被列进"接口隔离"，因为它们确实不是。

它唯一做对且值得照抄的是 `PromptBuilder`：**接口声明在消费侧，由外部包
结构化实现**。而那恰好是本仓库已经用了三遍的写法——`ToolExecutor`
（本文档 §2「工具缝」）、`HistoryCompactor`（0035）、`TurnAugmentor`（0039）。

**§12 收下 `agent-loop.md` 的"内聚"，拒绝连带收下它的"耦合"。** 凡本节决定
收进引擎的东西，一律以「引擎自己声明的 `@runtime_checkable` Protocol + 外部
结构化满足 + 不反向 import」的形式收，一条例外都不开。

### 12.2 对照 `agent-loop.md` 的全量核对表

左列穷举 `agent-loop.md` 描述的引擎层设计面，右列声明它在本仓库的处置。
体例沿用附录 A，并遵守附录 A 自己立的规矩：**「推迟」必须注明在等谁**。

> **顺带纠正附录 A 表头的一个数字**（由独立审核实测）：那里写的「16 个文件、
> 约 1,700 行非测试代码」不对——`internal/engine/` 的**非测试** `.go` 是
> **11 个文件、1,555 行**；16 个文件、3,946 行是把 5 个 `_test.go` 一起算了。
> 附录 A 属第一纪元，按本文档头部的规矩不改正文，在此记一笔。

#### 12.2.1 §10 设计原则十一条

| # | `agent-loop.md` §10 原则 | 本仓库状态 | 处置 |
|---|---|---|---|
| 1 | 标准 ReAct（每 Turn 一次 LLM 调用） | `engine/loop.py:222` `_kernel` | ✅ 已有 |
| 2 | emitter 解耦（阻塞/流式共享内核） | `_TurnStrategy` + `_blocking_turn` / `_streaming_turn` | ✅ 已有，且 §6 论证比参考实现更细（PEP 525 的 `_TurnOutcome` 持有器） |
| 3 | 接口隔离（`LLMProvider` / `Registry`） | `provider.LLMProvider` / `engine.ToolExecutor` | ✅ 已有，且多两条可选半边（`ConcurrencyAware` / `DeadlineAware`） |
| 4 | 双模式共存 | `run` / `run_stream` | ✅ 已有 |
| 5 | channel 驱动流式 | `AsyncIterator[EngineEvent]` | ✅ 已有（Python 形态） |
| 6 | **函数选项（依赖注入）** | `EngineConfig` 只覆盖 8 项预算类配置 | ◐ **本节补齐**，见 §12.2.2 |
| 7 | 并发安全（信号量 + 索引隔离写入） | `executor.py` 的 `results` out-parameter + 并发闸 | ✅ 已有 |
| 8 | 三重保障终止 | `StopReason.CONVERGED / MAX_TURNS` + `CancelledError` 透传 | ✅ 已有，且 `TRUNCATED` 是参考实现没有的第四种 |
| 9 | 可观测性（结构化日志） | 本层承诺不产日志（附录 A #34） | ❌ **不收**，理由见 §12.2.3 |
| 10 | 延迟解析（`json.RawMessage`） | `ToolCall.arguments` 保持原始 JSON 字节 | ✅ 已有，且 0028 给了更强理由（前缀缓存的字节稳定性） |
| 11 | 自愈（`ToolResult.IsError`） | `ToolResult.is_error` | ✅ 已有 |

**十一条里九条已有，一条补齐，一条驳回。** 所以差距不在"设计原则"这一层，
而在下面两层。

#### 12.2.2 §5.5 的函数选项（源码实测 16 个，不是十三个）

> **先纠正一个被继承下来的错数。** `agent-loop.md` §5.5 的表格列了 14 个
> `With*`，实测源码是 **16 个**：`internal/engine/options.go` 15 个 +
> `internal/engine/permission.go:36` 的 `WithPermissionMode` 1 个，另有运行期
> 的 `SetSession` 1 个可变入口。`agent-loop.md` 自己的表漏了
> `WithClosingGate` 与 `WithPlanningGate`。
>
> 更要紧的是：本仓库 `omicsclaw/engine/config.py:19` 的 docstring 里写着
> 「reference harness spells this as thirteen ``With…`` functional options」，
> **那个「thirteen」是错的，且是生产代码里的错误陈述**。§12 落地时顺手改掉，
> 并在提交信息里点名——一条引用参考实现的 docstring 说错了数字，下一个照它
> 核对的人会以为自己数错了。

| `With*` | 默认 | 本仓库今天在哪 | 处置 |
|---|---|---|---|
| `WithMaxTurns` | 500 | `EngineConfig.max_turns`（50） | ✅ 已有 |
| `WithToolTimeout` | 60s | `EngineConfig.tool_timeout` | ✅ 已有 |
| `WithMaxConcurrentTools` | 0 | `EngineConfig.max_concurrent_tools` | ✅ 已有 |
| `WithGenerateRetry` | 3, 1s | `EngineConfig.generate_retries` / `_base` | ✅ 已有 |
| `WithNetworkRetry` | 6, 5s | `EngineConfig.network_retries` / `_base` | ✅ 已有 |
| `WithCompactor` | nil | `run(compactor=)`（0035） | ✅ 已有，**且更好**：per-run 而非 per-engine，两个 run 不共享压缩状态 |
| **`WithPromptBuilder`** | nil | **无** | ✅ **本节收**，见 §12.4.1 |
| **`WithSession`** | nil | **无**（`SessionRegistry` 在 entry 层） | ◐ **本节半收**，见 §12.4.2 |
| `WithPlanStore` | nil | `PlanInjector` 满足 `TurnAugmentor`（0039） | ❌ **不收，已反超**，见 §12.3 |
| `WithStallNudge` | 0 | 无 | ⬜ **推迟至 0047**（2026-09-23 拆分后改由 0055 承接），等一个 `TurnAugmentor` 实现，不等引擎 |
| `WithMemoryNudge` | 0 | 无 | ⬜ **推迟至 0047**（2026-09-23 拆分后改由 0055 承接），同上 |
| `WithPermissionMode` | Default | `permission.PermissionGate.mode`，registry 已被 gate 包过 | ❌ **不收**：引擎被交一个已 gate 的 registry，"永远不知道有东西被 gate 过"（`permission/__init__.py:25-30`） |
| `WithContextWindow` | 0 | `context.ContextBudget.context_tokens` | ❌ **不收**：harness9 拿它只为 TUI 展示 token 占比；本仓库由 `measure()` 算并经 CONTEXT 事件上报，引擎不需要知道 |
| `WithEngineObserver` | noop | 无（0043 的 telemetry 在 entry 与 hooks 两层） | ❌ **不做**（2026-09-21 复核结案），见 §12.2.3 |
| `SetSession`（运行期） | — | 无 | ❌ **不收**，见 §12.4.5 |
| **`AgentEngine.Compact()`**（`compact.go`，不是 `With*`，是绕开 `runLoop` 的手动强制压缩，供 TUI `/compact` 直调） | — | `SessionRegistry.compact()`（`session.py:385`）走同一条 exchange 队列，`compaction_only` 时不跑模型轮次 | ❌ **不收，已有等价物**——**本条为独立审核补入**：原表把"压缩"只当成 `WithCompactor` 一条来核对，漏掉了 harness9 还有一个绕开循环的独立入口 |

**两个 nudge 不进引擎，是本节最容易被误判为"偷懒"的一条，所以给判据**：
harness9 的三个 nudge（stall / memory / closing）与规划门槛，实现方式都是
`appendUserNudge`——**只往发送副本追加一条消息，绝不持久化、不累积**
（`options.go:76-104` 三处注释都这么写）。这与 `TurnAugmentor` 的契约逐字
相同（`engine/augmentor.py`：「appended to the **sent copy only** … never
accumulates」）。而 0039 的 `PlanInjector` 已经**实现了其中的规划门槛**
（`PlanInjector(store, gate_turns=…)` + `PLANNING_GATE_TEXT`）。
所以 nudge 不是引擎缺的能力，是缺三个 `TurnAugmentor` 实现——把它们塞进
引擎反而会让引擎知道"什么叫进展工具"，那是它不该知道的。

#### 12.2.3 `EngineObserver`：附录 A #30 与 #38 的那条债，本节不还但把它写实

附录 A #30 自陈推迟理由「很弱」，#38 记下了后果：**一次阻塞 `run()` 是
完全的黑箱**——它按设计丢弃全部事件（`loop.py:184-188`），而附录 A #34 又
（正确地）承诺不产日志。0043 的 observability 层是在 `entry` 和 `hooks`
两侧接的（`telemetry.run()` 包在 `run_turn` 外、`TracingHook` 包在工具上），
所以引擎内部的 turn 边界在阻塞路径上确实没有任何出口。

**本节仍不还这条债**，但把理由换成一条可检验的：0046（子代理层）会是第一个
大量使用**阻塞路径**的调用方（`task` 工具前台模式要的是结论不是事件流）。
到那时才能知道需要的是 `EngineObserver` 式的回调，还是让 `run()` 也接一个
可选 sink。**在有真实消费者之前定这个接口，就是附录 A #30 批评的那种"为
不存在的层建缝"。** 0046 落地后复核，届时若仍无消费者，本条降级为「不做」。

> **复核结果（2026-09-21，0046 已交付）：仍无消费者，本条结案为「不做」。**
> 预判错在方向上：本节猜子代理层会大量走**阻塞路径**，实际
> `entry/subagent.py` 的 `ChildRunner.delegate` 走的是
> **`exchange_stream`**——因为 0046 §8 要求把子代理的工具边界转成父
> `ProgressSink` 上的进度行，而那些边界只在事件流里。于是"第一个大量使用
> `run()` 的调用方"没有出现，`run()` 的黑箱性质也没有人被它挡住。
> 按 §12.8 第 6 条的自我设限，不许再推第三次，本条降级为「不做」：真要
> 观察引擎内部的 turn 边界，现有的 `run_stream` / `exchange_stream` 已经
> 逐帧发布了它们，再加一条回调只是给同一批事实开第二个出口。

### 12.3 owner 点名的五样，逐条裁定

| 能力 | 本仓库今天 | 裁定 | 理由 |
|---|---|---|---|
| **PromptBuilder** | `AgentApp.prompt: PromptAssembler`，每次 exchange 由 `compose()` 现场 `render()` | ✅ **收** | 见 §12.4.1。实测 `PromptAssembler` **零适配器**满足引擎侧 Protocol |
| **Session** | `SessionRegistry` 持有；持久化发生在 registry 而非 exchange 的 Task（`session.py:794-800`） | ◐ **半收** | 收「本次新增了哪些消息」这条**边界**，不收**存储**。见 §12.4.2 |
| **workDir** | `AppConfig.workspace` → `Workspace` 在 `foundation_tools` 里构造一次分发给四个工具（`assembly.py:329`）；进 prompt 的那份由 `_environment_source`（`assembly.py:441`）负责 | ❌ **不收** | 引擎里**不会有任何一行读它**。harness9 的两个读者是 `FormatLoopStart` 的日志行与 `buildSystemPrompt` 的默认文案；前者被附录 A #34 排除，后者归 prompt 装配器。一个没有读者的字段，只会让下一个人以为它有语义 |
| **PlanStore** | `PlanInjector`（满足 `TurnAugmentor`）+ `PlanBook` 写穿 | ❌ **不收，已反超** | `entry/planning.py` 的 `build_injector` docstring 逐字写明：现状 = harness9 的 restore-at-start + checkpoint-on-write，**且把 save 移到了计划变更那一刻**。harness9 需要引擎持有 PlanStore，是因为它的 save 靠 `defer` 兜所有退出路径（`agent_loop.go:175`）；本仓库不需要兜。收进来是退步 |
| **审批事件** | `tools.require_approval` 读 contextvar → `entry.ApprovalBroker` 发 `APPROVAL_REQUIRED` 帧 + `asyncio.Future` | ❌ **不收，已解决** | 见 §12.6 |

**"不收"占三条，所以每条都给了可证伪判据**：workDir 用「在引擎里 grep
不到读者」证伪；PlanStore 用「找出一条 `defer savePlan` 兜得住而写穿兜不住的
退出路径」证伪；审批用「构造一次子引擎审批，证明它到不了父 broker」证伪
（§12.6 给了具体做法）。

> **PlanStore 那条的残余代价，由独立审核补入。** 证伪没有成功——写穿确实
> 覆盖了 harness9 `defer` 能覆盖的全部退出路径，且 crash window 更小
> （`planning/book.py:67-109`：每次被接受的 plan 写入在工具返回前就已落盘，
> 不必等一整轮工具跑完）。但有一处**不对称没被原文承认**：harness9 的
> `defer savePlan` 给同一次保存**两次机会**（轮末 `checkpointPlan` 失败后，
> 退出时 defer 还会再试一次），而写穿只在 `plan_write` 调用内尝试一次，
> 失败仅经 `on_archive_error` 记一条 warning。这是「立即但单次」对
> 「稍迟但两次」的权衡，不改变"已反超"的结论，但它**不是零代价**。

### 12.4 真正的内聚缺口：同一套装配被写了三遍

逐条核对完 §12.2 与 §12.3，能收的只有一样半。但缺口确实存在——**它不在
那些字段上，在生命周期上**。

今天要驱动一次 exchange，调用方必须自己按顺序做六件事：

```python
messages, prompt = compose(app, history, user_text)          # turn.py:127
compactor = build_compactor(app, session_id=…, state=state)  # compaction.py:76
augmentor = build_injector(app, session_id=session_id)       # planning.py:60
with _session_bound(session_id):                             # turn.py:194
    async with asyncio.timeout(app.config.turn_timeout_s):
        result = await app.engine.run(messages, compactor=compactor, augmentor=augmentor)
outcome = _outcome(result, prompt, compactor)                # turn.py:178
```

这套六步装配在 `omicsclaw/entry/turn.py` 里**出现了三次**：`run_turn`
（`:241-243`）、`stream_turn`（`:290-292`）、`TurnRunner._sequence`
（`:518-530`）。0046 的子代理层会是**第四次**。

`agent-loop.md` §4 的对应物是一张流程图和一行调用：
`beginInteraction → for{…} → saveHistory / savePlan`，外部只看见
`eng.RunStream(ctx, prompt)`。**这才是 owner 感受到的那个差距的真实形状：
不是"引擎持有的字段太少"，是"一次运行的生命周期没有主人"。**

三份拷贝的代价不是抽象的。0039 §2.2 已经记过一次同形缺陷（R3）：`_outcome`
直接读 `compactor.state` / `.last_record` / `.records` 三个具体属性，任何一处
装配漏掉一步都不会报错，只会让那一轮的压缩记录静默消失。装配点每多一个，
这类"漏一步不报错"的面就多一份。

#### 12.4.1 `PromptSource` —— 引擎去要 system prompt，而不是等人喂

新文件 `omicsclaw/engine/prompt.py`，只 import `typing`：

```python
@runtime_checkable
class RenderedPrompt(Protocol):
    @property
    def system_prompt(self) -> str: ...

@runtime_checkable
class PromptSource(Protocol):
    def render(self) -> RenderedPrompt: ...
```

**为什么是 `render() -> RenderedPrompt` 而不是更窄的 `system_prompt() -> str`**：
后者会逼出一个适配器，而适配器会**丢掉** `AssembledPrompt` 的
`section_stats` / `total_estimated_tokens`——`entry` 的 CONTEXT 事件要用它们。
前者让 `PromptAssembler` **零适配器**满足。已实测（`AssembledPrompt.system_prompt`
是 `@property`，`runtime_checkable` 的成员检查看得见）：

```
PromptAssembler 满足 PromptSource      : True
AssembledPrompt 满足 RenderedPrompt    : True
```

`render()` **每次 exchange 调用一次，不是每轮一次**——与 `AgentApp.prompt`
今天的 docstring 承诺一致（「A turn calls `app.prompt.render()` every time,
which is what makes an edited `SOUL.md` and a new day visible」）。每轮一次
会让同一次 exchange 内的 system prompt 在 `SOUL.md` 被编辑时中途变形，
还白白多读几次磁盘。

这条同时也是 `agent-loop.md` 末节「PromptBuilder 与 Skills 集成」的等价物：
skills 索引摘要进 system prompt、全文经 `use_skill` 按需加载，本仓库已由
`default_sections` + `use_skill_tool` 实现（`assembly.py:492` 的 `_skills_section`、`:344` 的 `use_skill_tool` 挂载点），
引擎只需要**去要**那份渲染结果。

#### 12.4.2 `Conversation` —— 引擎交还整条轨迹，存储方整体替换

> **本小节是独立审核后的返工版本。** 初稿把 Protocol 写成 `messages()` +
> `extend()`（追加），被审核判为会让压缩失效。原因与返工见 §12.10.1。

新文件 `omicsclaw/engine/conversation.py`，只 import `omicsclaw.schema`：

```python
@runtime_checkable
class Conversation(Protocol):
    def messages(self) -> Sequence[Message]: ...
    async def commit(self, messages: Sequence[Message]) -> None: ...
```

**`commit` 是整体替换，不是追加**，这一条是被实证逼出来的，不是偏好：

- `engine/loop.py:259-260`：压缩返回 `keep=True` 时，内核执行
  `history = list(sent)`——**整体替换**自己的历史累加器。
- `entry/session.py:126-128`（`Session` 自己的 docstring）：「the registry
  replaces `history` and `compaction` **wholesale** after a successful
  exchange」；实现在 `:794-795` 的 `session.history = outcome.history`。
- harness9 也是整体替换：`history.go:152` 在压缩写回后执行
  `lc.startLen = len(compacted)` **给持久化边界打补丁**，而
  `persistCompacted` 的注释逐字写着「将压缩产物（剥离 system prompt）
  **整体替换** Session 历史」。

也就是说：**追加语义在三个实现里都不成立**。一个 append-only 的 `extend`
会把本次 exchange 内被压缩折叠掉的原始消息原样写回存储，而真正的压缩摘要
只活在 `RunResult.messages` 里、从未进入存储——压缩在跨 exchange 之间
彻底失效，而那正是压缩存在的全部意义。

**system 消息由引擎剥离。** `Session.history` 不含 system（0031 Q3），而
system 是引擎自己加的，所以也由引擎自己摘掉再 `commit`，不把这条约定
外包给调用方去记。

**`CompactionState` 不出现在这个 Protocol 里**，这是硬约束不是风格选择：
它是 `omicsclaw.context` 的类型，而
`tests/engine/test_engine_is_a_leaf_layer.py:36` 的
`_ALLOWED_INTERNAL_PREFIXES` 只有 `schema` / `provider` / `engine`。压缩
状态继续由 entry 侧的 `Session.compaction` 持有、由 entry 在 `commit`
之外自己写——引擎交还轨迹，不交还压缩状态。

**一个写者，不是两个**：引擎调 `commit` 写内存里的 `Session.history`；
`SessionRegistry` 继续是唯一落盘的人（`session.py:800`）。这与 harness9
不同——那边 `persistCompacted` / `saveHistoryWith` 直接写 DB——理由是
0031 Q4 已裁定持久化归 registry，且 registry 需要把 history 与 compaction
状态**一起**存，而后者引擎看不见。

#### 12.4.3 `RunResult.prompt`，以及**不**照抄 `startLen` 的理由

`RunResult` 只新增**一个**带默认值的字段：

```python
prompt: RenderedPrompt | None = None
"""本次 exchange 渲染出的 system prompt，`None` 表示没有 PromptSource。"""
```

> **初稿还有一个 `appended: tuple[Message, ...]` 字段，已删除。** 它是
> harness9 `startLen`（`history.go:65` 写入、`:76` 切片）的等价物，用来告诉
> 调用方"本次新增了哪些消息"。删掉的理由是 §12.4.2 的同一条：本仓库的
> 持久化是**整体替换**，根本不需要增量边界；而 harness9 需要它，是因为它
> 的 `saveHistoryWith` 是增量追加——代价就是**它必须在压缩写回时给
> `startLen` 打补丁**（`history.go:152`）。**照抄一个形状而不照抄它的
> 补丁，就是把参考实现的复杂度搬过来、把它的正确性留在原地。**
>
> 0046 若需要"子代理这一趟产出了什么"，用 `RunResult.final_message`
> （`types.py:162`）——子代理回传的本来就是结论文本，不是轨迹增量。

`RunResult` 仍然是 frozen 记录，加一个带默认值的字段向后兼容；已核实测试侧
27 处构造均使用关键字或默认值，不存在按位置构造会被挤错位的情况。

**`prompt` 是本节最不干净的一处，予以承认。** 它让一个**结果记录**携带了
一个**装配器产物**——`RunResult` 其余字段都是"这次运行做了什么"，只有它是
"这次运行的输入是怎么装配的"，性质不同。替代方案有两个，都更差：entry 自己
再 `render()` 一次会多读一次 `SOUL.md` 且两次渲染可能不一致；用
`execute_tool_calls` 那种 out-parameter 回调（`executor.py:149`）则把一个
本可以是返回值的东西变成了副作用。独立审核复核后同意"动机站得住、属风格
取舍而非错误"，但这仍是 owner 应当重点看的一处。

#### 12.4.4 `exchange` / `exchange_stream` —— 第三、四个入口，但不是第二个内核

> **签名经独立审核返工**：初稿把 `conversation` 只放在构造参数上，与
> §12.4.5「每次 exchange 传一个新的」自相矛盾，且与"一个 `AgentEngine`
> 被 `SessionRegistry` 跨多会话共享"（`assembly.py:1132` 是全仓库唯一的
> 生产构造点）的真实部署形状冲突。见 §12.10.2。

```python
async def exchange(
    self, user_text: str, *,
    conversation: Conversation | None = None,
    prompt: PromptSource | None = None,
    compactor: HistoryCompactor | None = None,
    augmentor: TurnAugmentor | None = None,
) -> RunResult: ...

def exchange_stream(self, user_text: str, *, …同上…) -> AsyncIterator[EngineEvent]: ...
```

**四个协作者全部可按调用覆盖，构造参数只是默认值。** 这是必须的而不是
好看的：`SessionRegistry` 让多个会话共享同一个 `app.engine` 实例，而
`AgentEngine` 不是 dataclass、没有 `dataclasses.replace` 可用，所以
"按 session 换 Conversation"除了按调用传参之外没有别的入口。

做的事一一对应 `agent-loop.md` §4 的
`loadHistoryWith → runLoop → saveHistoryWith`：

```
prompt.render()                        → system 消息（有 PromptSource 时）
conversation.messages()                → 历史（有 Conversation 时）
+ Message(USER, user_text)
→ 委托给 run() / run_stream()          ← 同一个内核，一行都不复制
→ await conversation.commit(去掉 system 的 result.messages)
```

**超时不归引擎。** `turn_timeout_s` 今天由 entry 用 `asyncio.timeout` 包在
引擎调用外（`turn.py:255` 只包引擎调用；`TurnRunner._deadline`
`turn.py:511` 包整个 `_sequence`，比前者更宽，`:494-506` 的 docstring
解释了这个差异）。§12 **不动它**：截止时间是"这个部署愿意等多久"，是部署
策略不是循环语义，收进 `exchange()` 会让引擎多一条它无权决定的策略。
装配收敛后，`asyncio.timeout` 仍然包在 entry 调 `exchange*` 的那一层。
（初稿漏答了这个问题，由独立审核指出，见 §12.10.3。）

**§6「一个内核，两张嘴」没有被破坏**，这点必须钉死，因为它是 §6 花整节
论证的性质：`exchange*` 只是 `run*` 的**生命周期外壳**，不含任何 Turn /
工具 / Observation 逻辑，全部委托。"两张嘴"防的是**阻塞路径与流式路径对
"什么时候算跑完"产生分歧**；两个外壳共用同一对嘴，不引入第三种"跑完"的
判定。§12.9 有一条验收标准专盯这个。

**`run` / `run_stream` 一个字节都不改。** 生产侧构造
（`assembly.py:1132`，**全仓库唯一一处**——`assembly.py:1025`、
`engine/__init__.py:10`、`engine/loop.py:11` 三处都在 docstring 的示例代码块
里，不是生产路径）与测试侧 27 处构造全部保持绿，新能力只经 keyword-only 的
可选构造参数进入：

```python
AgentEngine(provider, tools, config=None, *,
            prompt: PromptSource | None = None,
            conversation: Conversation | None = None)
```

两个都是 `None` 且调用时也不传时，`exchange(text)` 退化为
`run([Message(USER, text)])`——即今天的行为。这条对应 `agent-loop.md`
§5.5 反复强调的「nil 时回退到内置默认（向后兼容）」。

#### 12.4.5 不做的：`SetSession` 运行期可变方法

harness9 有 `SetSession`（`options.go:148-155`，带 `sync.RWMutex`，供 TUI
的 `/new`、`/resume` 跨 goroutine 切换会话）。**不照抄**：§12.4.4 已经让
`conversation` 成为 `exchange` 的按调用参数，会话身份**经参数进出而不经
引擎字段**，所以没有需要加锁保护的可变状态。附录 A #33 早已裁定过
「Python 单事件循环无此竞态形态」，本条与之一致。

#### 12.4.6 仅压缩、不跑模型的那条路径

`TurnRunner._sequence` 在 `force_compaction=True` 时**完全跳过**
`engine.run_stream`，走 `_compact_only`（`turn.py:549-565`）——这是一条
不调用模型、只做压缩的独立形状，对应 harness9 的 `AgentEngine.Compact()`
（`compact.go`，TUI `/compact` 直调）。

**它不进 `exchange*`，留在 `TurnRunner`。** 理由：`exchange` 的语义是
"一次交流"，而这条路径里没有交流——没有 user 消息、没有模型调用、没有
`RunResult`。把它塞进 `exchange` 会逼出一个 `if compaction_only:` 的早退
分支，而那正是 §12.9 的 AST 验收标准要禁止的东西（外壳里不得出现业务
分支）。

**代价要说清**：`_compact_only` 仍会复用 `compose`（`turn.py:518`），所以
§12.4「装配只写一处」**不是完全达成**，而是"三处跑模型的装配收敛为一处，
外加一处不跑模型的特例"。初稿声称的是前者，独立审核指出了这个差距
（§12.10.4）。

#### 12.4.7 不做的：把 `_kernel` 拆成 `loop_phases.go` 那样的阶段方法

`agent-loop.md` §4 把 `runLoop` 拆成七个私有阶段方法 + 一个聚合可变状态的
`loopContext`。**不照抄**，理由在 harness9 自己的注释里
（`loop_phases.go:33-35`）：「引入它是为了**消除阶段方法之间 6+ 参数的层层
透传**」。本仓库的 `_kernel` 是单个 620 行文件里的一个协程，局部变量就是
它的 `loopContext`，没有那个要消除的痛。为了形似而引入一个可变状态聚合体，
换来的是把今天由作用域保证的不变量改成由纪律保证。

若 §12.4.4 落地后 `_kernel` 因新增生命周期而显著变长，再拆不迟——那时拆的
依据是行数与可读性，不是参考实现的文件布局。

### 12.5 交付物

**新增（`omicsclaw/engine/`，白名单不变：`schema` + `provider` + `engine`）**

| 文件 | 内容 | 允许的 import |
|---|---|---|
| `engine/prompt.py` | `RenderedPrompt`、`PromptSource` | 仅 `typing` |
| `engine/conversation.py` | `Conversation` | `typing` + `omicsclaw.schema` |

**修改（既有文件，最小面）**

| 文件 | 改动 |
|---|---|
| `engine/loop.py` | `__init__` 增两个 keyword-only 可选参数（默认值）；新增 `exchange` / `exchange_stream` 两个委托方法，四个协作者均可按调用覆盖；`_kernel` **不改** |
| `engine/types.py` | `RunResult` 增 `prompt` 一个带默认值的字段 |
| `engine/__init__.py` | 导出 `Conversation`、`PromptSource`、`RenderedPrompt` |
| `entry/turn.py` | 三处六步装配收敛为一处；`compose` 退化为构造 `Conversation` 实现；`_outcome` 改读 `result.prompt` |
| `entry/assembly.py` | `build_app` 把 `app.prompt` 作为 `PromptSource` 交给引擎 |

**测试**

| 文件 | 盯什么 |
|---|---|
| `tests/engine/test_prompt_source.py` | `PromptSource` 契约；`render()` 每次 exchange 一次而非每轮一次 |
| `tests/engine/test_conversation.py` | `Conversation` 契约；`commit` 收到的是**去掉 system 的整条 `result.messages`**，不是增量 |
| `tests/engine/test_exchange.py` | 生命周期；两个协作者都为 `None` 时退化为今天的 `run` |
| `tests/engine/test_commit_carries_compaction.py` | **一次 `keep=True` 压缩之后，`commit` 收到的是压缩产物而非被折叠掉的原文**——这是 §12.4.2 的全部理由，也是初稿被判返工那条缺陷的回归测试 |
| `tests/engine/test_engine_is_a_leaf_layer.py` | `:208` 的 `__all__` 断言 15 → 18；`:36` 白名单**不变**（若需要改，说明设计错了） |
| `tests/entry/test_structural_satisfaction.py` | `PromptAssembler` / entry 的 `Conversation` 实现满足引擎 Protocol，**且 `omicsclaw.context`、`omicsclaw.entry` 不被 engine import** |

### 12.6 审批为什么不收，以及 0031 Q5 的三条理由今天还剩几条

附录 A #36 是这条债的源头，0031 §11 债表第 3 条把它记成「**审批没有引擎侧
表示**……**子代理层将来会再遇到一次**（子引擎的审批要穿两层）」。既然
0046 就是那个子代理层，这条必须在这里判掉。

**0031 Q5 当初给了三条理由选择"entry 自己发事件、不改引擎"**：

1. 「(a) 改的是前一步的文件」——**今天已被事实推翻**。0035 往 `engine/`
   加了 `compactor.py`，0039 加了 `augmentor.py`，§12.5 正在第三次这么做。
2. 「绑定 `ApprovalChannel` 的是本层，'有人正在被询问'本层本来就知道」——
   **仍然成立**。
3. 「harness9 把审批塞进 `engine.Event`，是因为 Go 的 channel 装不下异常、
   也装不下第二条流。Python 没有这个约束。**结构从参考实现来是资产，约束
   从参考实现来是负债**」——**仍然成立，且是决定性理由**。

**"子引擎的审批要穿两层"这个预判，经复核不成立。** 判据在
`executor.py:236-248`：每个工具调用用 `asyncio.ensure_future(run_one(…))`
起独立 Task、不传显式 `context=`，而 `asyncio` 起 Task 时 `copy_context()`
——继承的是**创建时刻**生效的 ambient context，不是重置。所以：

```
父 turn 的 Task  ──绑定──►  ToolContext(approval=父 broker)     turn.py:425
  └─ task 工具的 Task（copy_context）                  ← 仍是父 broker
       └─ 子引擎 execute_tool_calls 的 Task（copy_context）  ← 仍是父 broker
            └─ 子代理的工具 require_approval → 到达父 broker，零额外管道
```

**这不是推理，是实测。** 用一段不落库的探针模拟上面那条三层嵌套
（父 turn 绑 broker → `ensure_future` 起 task 工具 Task → 再起子引擎 executor
Task → 再起子代理工具 Task → `require_approval`）：

```
三层 Task 后到达父 broker : True ['bash']
决定                      : ApprovalDecision(approved=True, reason='parent broker said yes')
后台 approval=None         : fail-closed: bash requires approval (approval_mode=ask,
                            risk=high) and no approval channel is bound to this session;
                            refusing rather than assuming consent
```

子代理的审批请求会**自动**变成父 turn 事件流上的 `APPROVAL_REQUIRED` 帧。
0046 真正要补的不是管道，是**归属**——那条帧上没有字段说明"这是
`general-purpose` 在问，不是主代理在问"。那是 `ApprovalRequest` 加一个字段、
或在 `ToolContext.values` 里放一个键的事，属于 0046，不属于引擎。

> **核实（2026-09-21，0046 已交付）：上面那张链路图当时是对尚不存在的代码
> 的预测，现在是实测，且预测正确。** 钉住它的是
> `tests/entry/test_subagent_wiring.py::test_the_child_s_approval_request_reaches_the_parent_s_broker`：
> 父 turn 绑一个**真实的** `ApprovalBroker` → `task` 工具的 Task → 子引擎
> `execute_tool_calls` 的 Task → 子代理的 `bash` → `require_approval`
> 到达父 broker，零额外管道；同一条测试的姊妹篇再断言那次请求确实变成了父
> `TurnStream` 上的 `APPROVAL_REQUIRED` 帧。§12.8 第 6 条给的两个前提条件
> 都成立：0046 的实现路径里没有内联 `await`（工具调用仍由
> `asyncio.ensure_future` 起 Task），也没有任何一处显式传 `context=`。
>
> **归属那半句也兑现了，但比原文写的窄一步**：`ToolContext.values` 里确实
> 多了一个 `SUBAGENT_VALUE_KEY = "subagent"`，而 `ApprovalRequest` **没有**
> 加字段——0046 §7.1 裁定 `values` 已经是"这一轮的事实"的去处。原文把两种
> 做法并列，实际只取了后一种。
>
> **一处原文没预见的代价**：`use_tool_context` 是整体替换语义，所以"放一个
> 键"若按字面实现会连 `workspace` / `session_id` 一起冲掉，子代理里所有
> 文件工具直接 `RuntimeError`。0046 §7.1.1 把它改成显式 spread，并配了
> `test_the_child_s_file_tools_still_resolve_the_bound_workspace` 钉住。

后台子代理要的是相反方向的能力：**审批一律拒绝**。那是 0046 在委派时绑一个
`use_tool_context(approval=None)`——`require_approval` 会 `raise
ApprovalUnavailable`（`tools/context.py:597-603`，fail-closed），正是要的语义。
同样不需要引擎参与。

**附带结清一条**：0028 债表 `:843` 记着「正确的修法要动 `omicsclaw/engine/`
（让 `tool_timeout` 不覆盖审批等待）」。`executor.py:388` 的 `_paused` 已经
做了——它把 per-call deadline 摘掉，再按**剩余秒数**装回去。这条同时是 0046
的地基：一次子代理委派会跑很多轮、远超 60s 的 `tool_timeout`，而 `task` 工具
只要在整个子运行期间握住一个 pause，就等价于 harness9 `runner.go:165`
从会话级 `baseCtx` 派生 `execCtx` 绕开工具超时的那套把戏——且不需要引擎
知道有"子代理"这回事。

### 12.7 刻意偏离参考实现（逐条给理由）

| # | harness9 / `agent-loop.md` | 本节 | 理由 |
|---|---|---|---|
| 1 | `workDir string` 在引擎上 | 不收 | 引擎里没有读者（§12.3） |
| 2 | `WithPlanStore` | 不收 | 0039 已用写穿反超，收进来是退步（§12.3） |
| 3 | `engine.ApprovalRequest` + `ResponseCh` | 不收 | contextvars 已走通；Go 的约束不是本仓库的约束（§12.6） |
| 4 | `WithSession`，引擎直接写 DB | `Conversation`，引擎只写内存、registry 落盘 | 引擎看不见 `CompactionState`，而两者必须一起存（§12.4.2） |
| 5 | `startLen` 增量边界 + 压缩写回时给它打补丁（`history.go:152`） | 不要边界，`commit` 整体替换 | 本仓库持久化本就是整体替换；照抄形状而不照抄补丁，只会把复杂度搬过来、把正确性留在原地（§12.4.3） |
| 6 | `SetSession` + `RWMutex` | 无 | 一个引擎服务多 session；附录 A #33 已裁定（§12.4.5） |
| 7 | `loop_phases.go` 七阶段 + `loopContext` | 不拆 | 它解决的是 Go 的参数透传，本仓库没有那个痛（§12.4.6） |
| 8 | 三个 nudge 在引擎里 | 归 `TurnAugmentor`，0047（拆分后为 0055） | 引擎不该知道"什么叫进展工具"（§12.2.2） |
| 9 | `WithPermissionMode` / `WithContextWindow` | 不收 | 分别归 `PermissionGate` 与 `ContextBudget`（§12.2.2） |
| 10 | 接口散落在 memory / planning / hooks 包 | 全部声明在 `engine/` | §12.1 的全部论点 |

### 12.8 已知代价

1. **`engine.__all__` 从 15 项长到 18 项**，`test_engine_is_a_leaf_layer.py:208`
   的逐字断言必须同步改。那条断言的职责是「公开面不得随手增长」，所以改它
   属于**需要留证据**的动作，不是顺手改数字：三个新名字必须都在 §12.5 的
   交付物表里有对应文件。
2. **入口从两个变成四个。** §12.4.4 论证了它不破坏 §6，但"四个公开入口"
   本身是认知成本。缓解只有一条：`exchange*` 的 docstring 必须写明自己是
   外壳、内核在 `run*`，且不重复解释循环语义。
3. **`RunResult` 多了一个字段 `prompt`。** 详见 §12.4.3——它让一个
   **结果记录**携带了一个**装配器产物**，是本节最不干净的一处。两轮独立
   审核都点到了它，结论是「动机站得住、属风格取舍而非错误」，但 owner
   应当重点看它。
4. **`entry/turn.py` 装配收敛，是本节唯一会动到既有行为的改动。**
   `_outcome` 读 compactor 三个具体属性那条 R3 形状的缺陷面**不会消失**，
   只是从三份变成一份。真正消除它需要给压缩记录一条正式出口，超出本节。
   而且收敛**不彻底**：`_compact_only` 仍单独复用 `compose`（§12.4.6）。
5. ~~**§12.2.3 把 `EngineObserver` 的债又推了一格。**~~ **已结案
   （2026-09-21）**：0046 走的是 `exchange_stream` 而不是阻塞路径，预测的
   消费者没有出现，按本条的自我设限降级为「不做」。见 §12.2.3 的复核。
6. ~~**本节对 0046 的两条推断，是推断不是核实。**~~ **两条均已核实成立
   （2026-09-21）**：审批链路见 §12.6 的核实段；§12.9 的"子引擎构造是一次
   调用"见下。原文如下，保留。 §12.6 的三层 Task 继承链
   已用探针验证了**机制**，但 `task` 工具与子引擎今天都还不存在
   （仓库里搜不到任何 subagent 代码）。准确表述是：底层机制成立，只要 0046
   不触碰 `tools/context.py:37-43` 已写明的两种会打破它的写法（inline
   `await` 不起 Task、显式传 `context=` 共享），这条链就会自动成立。同理，
   §12.9 那条「子引擎构造是一次调用」的验收标准要到 0046 才能真正执行。

### 12.9 验证

- `pytest tests/engine tests/entry -q`（需 `rapids_singlecell` 环境；该环境下
  已知有三处与本改动无关的既有失败，交付时逐条点名）
- 两条**变异测试**：(a) 把 `exchange` 里的 `conversation.commit` 删掉，
  `test_conversation.py` 必须红；(b) 把 `commit` 的实参从「去掉 system 的
  `result.messages`」换成「user + 本次新增消息」（即初稿那个 append 语义），
  `test_commit_carries_compaction.py` 必须红。删掉不红的测试不算测试。
- 一条**反向导入探针**（沿用 `:150` 的写法）：`import omicsclaw.engine` 之后
  `sys.modules` 里仍只多出 `omicsclaw.version`。
- 一条盯 §6 的**结构断言**：`exchange` / `exchange_stream` 的函数体内不得出现
  turn 计数、工具调度或 Observation 构造——用 AST 检查它们除委托之外只做
  消息拼装。
- **0046 的前置检查**：§12 落地后，用一段不落库的探针脚本证明"构造一个窄化
  工具集的子引擎 + 跑一次 exchange"是**一次构造调用**而非六步装配。这是
  §12.4 声称要解决的问题的唯一验收口径。

  > **已执行（2026-09-21）**：`ChildRunner.delegate` 里就是
  > `AgentEngine(provider, child_registry, engine_config)` 一次构造，随后
  > `engine.exchange_stream(prompt, prompt=ChildPrompt(...))` 一次调用。
  > 会话对象一个都没有——`exchange` 的 `conversation` 保持 `None`，这同时
  > 就是 0046 的上下文隔离实现方式。窄化工具集本身是
  > `ToolRegistry()` + 一个 `register` 循环，不属于引擎装配。

### 12.10 两轮独立只读审核的发现与返工（2026-09-20）

体例沿用 0039 §8。§12 初稿写完后交给两个**独立、只读、未参与建造**的
审核者：一个查正确性（对照本仓库源码），一个查 harness9 对照忠实度。两份
报告的判定分别是「需返工」与「忠实，但引用精度有问题」。以下逐条记录，
**包括证伪失败的部分**——一条被认真攻击过却没被推翻的裁定，比一条没人攻击
过的裁定更可信。

#### 12.10.1 已返工（核心）：`Conversation` 的追加语义会让压缩失效

初稿的 Protocol 是 `messages()` + `extend()`（追加），`exchange()` 里写
`await conversation.extend((user_msg, *result.appended))`。审核指出这与
压缩的整体替换语义直接冲突，复核后**成立**：

- `engine/loop.py:259-260`：`keep=True` 时 `history = list(sent)`，整体替换。
- `entry/session.py:126-128` 与 `:794-795`：registry 也是整体替换。
- harness9 `history.go:152` + `persistCompacted`：**它同样是整体替换**，
  并且必须在压缩写回时给 `startLen` 打补丁。

后果是致命的：一旦本次 exchange 内发生 `keep=True` 压缩，被折叠掉的原始
消息会被原样写回存储，而真正的压缩摘要只活在 `RunResult.messages` 里、
从未进入存储——**压缩在跨 exchange 之间彻底失效**。

返工：`extend` → `commit`（整体替换），并删掉 `RunResult.appended`
（§12.4.2、§12.4.3）。**这条缺陷的形状值得记住**：初稿照抄了 harness9
`startLen` 的形状，却没照抄它为这个形状打的补丁。

#### 12.10.2 已返工：`conversation` 绑定时机自相矛盾

初稿把 `conversation` 只放在构造参数上，而 §12.4.5 又说「每次 exchange 传
一个新的」——两句话无法同时成立，且 `AgentEngine` 不是 dataclass、没有
`replace` 可用。真实部署形状（`SessionRegistry` 跨会话共享
`assembly.py:1132` 那唯一一个引擎实例）使这不是边角情况而是主路径。
返工：四个协作者全部可按调用覆盖，构造参数降为默认值（§12.4.4）。

#### 12.10.3 已返工：`turn_timeout_s` 归属未答

初稿声称装配收敛却没说 `asyncio.timeout` 包装去哪。已补：**留在 entry**，
截止时间是部署策略不是循环语义（§12.4.4 末段）。

#### 12.10.4 已返工：`compaction_only` 路径未覆盖

初稿的「三处装配收敛为一处」漏了 `TurnRunner._compact_only` 这条不跑模型的
第四种形状。已补 §12.4.6：它不进 `exchange*`，且如实承认收敛因此**不彻底**。

#### 12.10.5 已修：事实性引用错误（两份报告合计 11 处）

harness9 侧 6 处（`agent_loop.go` 结构体与 `defer savePlan`、`options.go`
的 `SetSession`、`history.go` 的 `startLen`、`runner.go` 的 `execCtx`——
其中两处偏差近 30 行，指向了完全无关的代码）；本仓库侧 5 处
（`planning.py` 的 `build_injector`、`stream_turn` 与 `_sequence` 的装配
起始行、`use_skill_tool` 挂载点、`executor.py` 的 `copy_context` 证据行）。
另修正两个数字：harness9 的函数选项是 **16 个**不是十三个（`agent-loop.md`
§5.5 的表自己漏了两个），`AgentEngine` 的生产侧构造是 **1 处**不是两处
（初稿把三段 docstring 示例当成了生产代码数）。

**其中一条外溢到生产代码**：`omicsclaw/engine/config.py:19` 的 docstring
写着「reference harness spells this as thirteen `With…` functional
options」，那个数字是错的，§12 落地时一并改（§12.2.2）。

#### 12.10.6 已补：`compact.go` 这条能力原表漏记

harness9 还有一个绕开 `runLoop` 的独立 `AgentEngine.Compact()`。初稿的核对表
只把"压缩"当 `WithCompactor` 一条来核对。本仓库有等价物
（`SessionRegistry.compact()`），但账没记过，已补进 §12.2.2。

#### 12.10.7 三条"不收"：两轮审核都认真证伪过，全部失败

这是本节最该被信任的部分，因为它是被攻击过的。

| 裁定 | 审核做了什么 | 结果 |
|---|---|---|
| workDir 不收 | `grep -rin "workdir\|work_dir\|workspace" omicsclaw/engine/` 无匹配；并检查 §12 新增的三样是否会产生读者 | **证伪失败**，裁定成立 |
| PlanStore 不收 | 逐个检查三种退出路径：plan_write 后崩溃、exchange 被 `asyncio.timeout` 取消（`archive.save` 是同步调用，不在 `await` 点，不会被腰斩）、对照 `loop_phases.go:161-163` | **证伪失败**，裁定成立。但补记了一条不对称：harness9 的 defer 给同一次保存两次机会，写穿只有一次（§12.3 已补） |
| 审批不收 | 两个审核者各自独立写了三层嵌套 Task 的 async 探针并跑通 | **证伪失败**，裁定成立。但要求把语气从「已解决」降为「机制已验证，0046 不触碰两种已知破坏写法即自动成立」（§12.8 第 6 条已补） |

#### 12.10.8 已驳回：无

本轮两份报告的发现全部接受。没有一条被驳回。

#### 12.10.9 审核者点名做得对的地方（一并记录，因为下一步会读这份计划）

- §12.1 对「harness9 是否真的低耦合」的反驳经源码 + 文档双重核实成立，
  没有断章取义（`memory/session.go:21-25` 确认 `Session` 接口自己 import
  planning；`agent-loop.md` §10 的"接口隔离"确实只点名两条）。
- §12.4.1 的「已实测」声明被两个审核者各自独立复现为真。
- PlanStore 那条的证据链从 `entry/planning.py` 的 docstring 一路核到
  `planning/book.py` 的实现，「写穿早于 harness9 的轮末 checkpoint」经查为真。
- 与 0031 Q5/Q13/Q16、0028 `:843` 债表、0039 §2.2 **未发现冲突**。

### 12.11 交付结果（2026-09-21）

**已交付。** 实现由一个独立子 agent 完成，代码评估由另一个独立只读子 agent
完成，二者均未参与计划的撰写。

#### 交付物

生产代码新增 2：`omicsclaw/engine/prompt.py`（74 行，只 import `typing`）、
`omicsclaw/engine/conversation.py`（86 行，`typing` + `omicsclaw.schema`）。
生产代码修改 6：`engine/loop.py`、`engine/types.py`、`engine/__init__.py`、
`engine/config.py`、`entry/turn.py`、`entry/assembly.py`。
测试新增 5 + 修改 3。

**测试：`tests/engine tests/entry` → 1197 passed, 1 skipped**
（改动前基线 1147）。重建栈整体 4558 passed, 10 skipped。

#### 硬约束逐条核实通过

`run` / `run_stream` / `_kernel` / `_attempt` / 两个 turn strategy **AST 逐函数
比对字节级不变**；`_ALLOWED_INTERNAL_PREFIXES` 一字未动；新 Protocol 无
`CompactionState`；`import omicsclaw.engine` 后 `sys.modules` 仍只多出
`omicsclaw.version`；`__all__` 18 项字母序；新文件都在 `engine/` 顶层。

#### 实现期发现的、计划写错或没写到的（10 条，择要）

1. **§12.5「`compose` 退化为构造 `Conversation` 实现」做不到。** `prepare()`
   需要的是装配好的消息元组，`_compact_only` 又仍要 `compose`，且 `compose`
   在 `turn.__all__` 里、有 6 处直接调用。实际做法是 `_Carried` 加在旁边，
   `compose` 原样保留。
2. **§12.4.3 漏了流式路径的 `RunResult.prompt`。** `_sequence` 从
   `event.result` 取结果，若原样转发内核的 DONE，`prompt` 会是 `None`。
   `exchange_stream` 必须重新盖章：`yield replace(done, result=await _settle(…))`。
3. **一个 Python 特有的坑，计划没答**：先 yield DONE 再 commit 的话，消费者
   一拿到答案就 `break` 会触发 `GeneratorExit`，**commit 永不执行**。裁定为
   **先 commit 再发 DONE**，并用 `aclosing()` 保证内层生成器被关闭。计划里
   既没写这个时序，也没写 `aclosing`。
4. **交付物 8 是二者都要而非二选一。** entry 必须**每次调用都传
   `prompt=app.prompt`**，构造时那份只作兜底——否则 `tests/entry/` 里自建
   引擎的 27 处会全线拿不到 render。
5. **`build_injector` 也要跳过**（计划 §12.4.6 只说了 `compose`）：压缩-only
   路径今天不调它，无脑调用会让一个不跑模型的 exchange 多做一次磁盘恢复。
6. **一处计划没预告的行为变化**：render 时机从 `asyncio.timeout` /
   telemetry scope **之外**挪到了**之内**，慢或失败的渲染现在计入
   `turn_timeout_s`。评估判定为「把 `run_turn`/`stream_turn` 对齐到
   `TurnRunner._deadline` 本就有的语义，可接受的对齐而非回归」。
7. **剥离 system 按 role 而非按位置**（计划只说「去掉 system」没定实现）。
   按位置切在压缩重写过历史之后会切错。

#### 代码评估的结论与返工

评估结论：**已准确完成计划 §12，未发现破坏性缺陷。** 六项重点攻击
（system 剥离、commit/DONE 时序、取消路径不污染历史、`keep=True` 压缩正确性、
render 时机、AST 守卫可否绕过）逐条实测，均无法证伪。评估自行做的变异测试
使 8 个测试变红，证明测试锁住的是真不变量。

评估留下 3 条发现，**中危一条已修**：

- **【中·已修】§12.9 那条结构守卫可被绕过。** 原实现用 4 个硬编码函数名的
  黑名单，把编排逻辑挪进一个未列名的模块级 helper 即可让三条检查同时失效。
  已改为**按可达性推导**：从 `exchange` / `exchange_stream` 出发，沿 `f()` 与
  `self.f()` 两种调用形式递归收集 `loop.py` 内定义的全部函数（在
  `run` / `run_stream` 处停止下降），对整个闭包施加检查；并补了两条自检——
  闭包必须覆盖到四个已知外壳，以及**守卫自己必须抓得住"藏在下一层"的违规**。
  对真实文件植入该绕过手法做变异测试，守卫报出
  `test_a_shell_contains_no_turn_tool_or_observation_logic[_smuggled]`——
  用例 id 就是那个藏起来的 helper，说明闭包自己发现了它。已还原。
- **【低·已修】违反 `Conversation` 契约的组合无测试覆盖。** 补
  `test_a_conversation_that_breaks_its_contract_loses_its_system_message`：
  一个违规自带 system 消息的 `Conversation`，在引擎也渲染了 system 时**两条
  都会被剥离**。把这个代价钉死而不是留给 0046 当作"历史莫名其妙少了一条"
  去发现。
- **【低·未修，记录在案】** render 计入 `turn_timeout_s` 这条行为没有回归
  测试锁定（`tests/entry/test_turn.py` 现有的超时测试只测 provider 慢）。
  若未来有人把渲染挪回超时之外，没有任何测试会发现。

#### 按计划裁定「不收 / 推迟」的，一条都没顺手做

workDir、PlanStore、审批事件、两个 nudge、`EngineObserver`、`SetSession`、
`WithPermissionMode`、`WithContextWindow` 均未实现，与 §12.2 / §12.3 一致。

#### 仍然欠着的

- `_outcome` 读 compactor 三个具体属性那条 R3 形状的缺陷面**没有消除**，只是
  从三份变成一份（§12.8 第 4 条已预告）。
- 「装配只写一处」**不彻底**：`_compact_only` 仍单独复用 `compose`（§12.4.6）。
- `ruff` / `mypy` 未跑——两个环境里都没装。行宽 ≤ 88 已逐行核过。

## 附录 A —— harness9 `internal/engine/` 特征对照表

§8 第 2 问的标尺。左列穷举 harness9 engine 包（16 个文件、约 1,700 行
非测试代码）暴露的每一项能力，右列声明它在本步的处置。Task D 必须逐行
核对，并对每一个「✅ 在范围内」给出它实际落在哪个文件、哪个测试的证据。

**「⬜ 推迟」不是「没做」的委婉说法**：每一条都注明了它在等哪一层。若
Task D 发现某条推迟项其实无需那一层即可实现，那本身就是一条 finding。

| # | harness9 能力 | 出处 | 本步处置 |
|---|---|---|---|
| 1 | ReAct 轮循环（LLM → 工具 → Observation → 下一轮） | `agent_loop.go` `runLoop` | ✅ 在范围内 |
| 2 | 阻塞入口 `Run` | `agent_loop.go` | ✅ `run()` |
| 3 | 流式入口 `RunStream` + 事件流 | `stream.go` | ✅ `run_stream()` |
| 4 | 双入口共享内核（emitter 缝） | `agent_loop.go` `emitter` | ✅ §6「内核缝」 |
| 5 | Turn 上限终止 | `loop_phases.go` `beginTurn` | ✅ `StopReason.MAX_TURNS`，陷阱 9 |
| 6 | ctx 取消终止 | `loop_phases.go` `beginTurn` | ✅ 陷阱 4（`CancelledError` 原样传播） |
| 7 | 自然收敛（无工具调用） | `agent_loop.go` | ✅ `StopReason.CONVERGED` |
| 8 | 同轮多工具并发 + 按下标保序 | `tools_exec.go` | ✅ 陷阱 1 |
| 9 | 单工具独立超时，互不牵连 | `tools_exec.go` | ✅ 陷阱 6 |
| 10 | 并发上限信号量 | `tools_exec.go` | ✅ `EngineConfig.max_concurrent_tools` |
| 11 | Observation 注入 + 空输出占位兜底 | `loop_phases.go` `injectObservations` | ✅ 陷阱 2 |
| 12 | `is_error` 透传进 Observation | `loop_phases.go` | ✅ 经 `ToolResult.to_message()` |
| 13 | 双档重试（默认预算 / 网络预算，互不借用） | `retry.go` | ✅ `retry.py`，陷阱 12 |
| 14 | 指数退避 + 移位溢出封顶 | `retry.go` `backoffDelay` | ✅ `test_retry.py`「退避封顶」 |
| 15a | 契约违规**检测**（流未送 DONE / 返回空响应） | `retry.go`、`stream.go` | ✅ 陷阱 11 |
| 15b | 契约违规**恢复**（视为瞬时，进重试预算） | `retry.go:64-68`、`stream.go:244-246` | ✅ **已修复**（评估发现，原表漏记）。原实现一次就杀掉整条 run；另，原表称「阻塞路径结构性不可能」为**假**——`LLMProvider` 是结构化 Protocol，`runtime_checkable` 只比对方法名、从不比对返回类型。现在三种形态（流未送 DONE、`generate()` 返回 `None`、`generate_stream()` 返回非异步迭代器）统一在 `_attempt` 内侦测并抛 `ProviderError`，从而落进重试预算 |
| 16 | 每轮重读工具列表 | `loop_phases.go` | ✅ 陷阱 7 |
| 17 | 完整助手消息入历史（非压缩/展示副本） | `loop_phases.go` `generateTurn` | ✅ 陷阱 8 |
| 18 | 流 chunk → 事件映射（text / thinking / done / error） | `stream.go` `streamGenerate` | ✅ 陷阱 10、11 |
| 19 | 每轮 token 用量上报（估算值 + 实际值） | `loop_phases.go` | ◐ **只做实际值**。估算值需 token 计数器，属第 5 步——切分位置经核验正确。但「`None` 表示后端未上报」这一不变量**只有流式路径守得住**：阻塞路径赋的是 `Completion.usage`，其默认零值无法表达「未上报」 |
| 20 | context window 展示 | `options.go` `WithContextWindow` | ❌ **不诚实的推迟**。两半都不成立：`TURN_END` 上已有的 `usage.input_tokens` 就是模型刚吞下的上下文大小，不需要估算值；而 window 这个数第 2 步就交付了（`provider/_model_limits.py` 的 `get_model_limits(model).context_tokens`），engine 本就 import provider。不等任何层 |
| 21 | Session 历史加载 / 保存 | `history.go` | ⬜ 推迟至第 6 步（§1 非目标） |
| 22 | system prompt 构造（`PromptBuilder`） | `history.go` | ⬜ 推迟至第 5 步（§1 非目标） |
| 23 | 上下文压缩 + 写回式持久化 | `history.go`、`compact.go` | ⬜ 推迟至第 5/6 步 |
| 24 | 手动 `/compact` | `compact.go` | ⬜ 推迟——依赖 #23 |
| 25 | 记忆 nudge（周期注入） | `nudge.go`、`options.go` | ⬜ 推迟，但**理由指错了层**：`WithMemoryNudge` 只是 `turns % interval` 加一条调用方给的字符串，不碰任何存储。真正的阻塞是 §1「不构造 prompt」（第 5 步） |
| 26 | 停滞 nudge（无进展检测） | `loop_phases.go`、`nudge.go` | ⬜ 推迟，**原理由为假**：harness9 的进展工具集是 engine 包里一个硬编码 map（`nudge.go:16-19`），工具层根本不被咨询，机制只需 `ToolCall.name`。真正的阻塞同 #25（第 5 步） |
| 27 | 收尾门槛 nudge（P1-4） | `loop_phases.go` | ⬜ 推迟——**原表未注明在等哪一层，违反本表自己的规则**。它是唯一纯算术的 nudge（`max_turns - turns`，两值都在手），阻塞同 #25（第 5 步） |
| 28 | 规划门槛 nudge（P1-1） | `loop_phases.go` | ⬜ 推迟——依赖 `plan_write` 工具 |
| 29 | PlanStore 集成 + 写时检查点 | `loop_phases.go` | ⬜ 推迟——planning 层不存在<br>**§12.3 改判为「不收，已反超」**：0039 用 `TurnAugmentor` + `PlanBook` 写穿实现了同一能力，且把 save 移到计划变更那一刻，不需要 harness9 的 `defer savePlan` 兜底 |
| 30 | `EngineObserver` 生命周期钩子（OTEL） | `observer.go` | ⬜ 推迟，**理由很弱**：「层不存在」正是本计划在 #31/工具那一行**拒绝接受**的论证——`ToolExecutor` 被声明出来恰恰因为第 4 步不存在。更好的理由是流式事件词汇已带 turn 与工具边界；但它只覆盖 `run_stream`，而 `run()` 丢弃全部事件（见 #38） |
| 31 | `PermissionMode` + 人类审批回路 | `permission.go`、`stream.go` | ⬜ 推迟至第 4 步——审批是工具层策略<br>**§12.3 改判为「不收，已解决」**：0028 Q4 的 contextvars 通道 + `executor.py:388` 的 `_paused` 已经把审批完整走通，引擎侧无缺口 |
| 32 | 子代理进度事件 | `stream.go` `EventSubAgent` | ⬜ 推迟——ADR 0077 已显式排除 `SubAgentUpdate`<br>**§12.3 改判为「不收，已有通用通道」**：`ProgressSink` + `TurnEventType.PROGRESS` 已经是 `SubAgentUpdate` 的超集，归 0046 使用而非引擎新增 |
| 33 | 跨 goroutine `SetSession` + 入口快照 | `options.go`、`loop_phases.go` | ⬜ 不适用——依赖 #21，且 Python 单事件循环无此竞态形态 |
| 34 | 结构化日志（`logfmt`） | 贯穿全包 | ⬜ 不做——本层不产生日志，与 `schema` / `provider` 两层一致 |
| 35 | **单工具引擎侧精确耗时进入事件载荷** | `tools_exec.go:64-66`、`stream.go:100-106` | ⬜ **原表漏记**。`EngineEvent` 无耗时字段。这是 Surface 能拿到的唯一 per-tool 成本信号，且**只有引擎测得出来**——工具层看不到信号量排队时间。不被任何层阻塞，代价是两个 `time.monotonic()` 加一个字段 |
| 36 | **工具缝上的带外通道** | `tools_exec.go:58-60`、`stream.go:203-205` | ⬜ **原表漏记**。Go 经 ctx 向工具注入审批回调与子代理进度 sink；本层的缝是 `execute(call) -> ToolResult`，零 ctx、零回调。#31/#32 推迟的是*策略*，但真正冻结它们的是这个无参缝。§11 承诺第 4 步「不 import 本模块」地满足该 Protocol，所以第 4 步要么改已发布的缝，要么改用 `contextvars`<br>**已结清**：0028 Q4 选了 `contextvars`（`execute_tool_calls` 的 `copy_context` 使其成立），0031 补上 `ApprovalBroker`。§12.3 复核后确认引擎侧无残余缺口 |
| 37 | **生成失败时的轮次归属** | `loop_phases.go:229` | ⬜ **原表漏记**。Go 把 provider error 包成「模型生成失败 (turn N)」；本层裸抛，调用方不知死在第几轮。价值低，代价近零 |
| 38 | **阻塞入口的进度信号** | `agent_loop.go:122-135` | ⬜ **原表漏记**。harness9 的 `Run` 打印助手文本并逐轮打日志；本层 `run()` 丢弃全部事件，且 #34 又（正确地）承诺不产日志。净效果：一次阻塞 run 是完全的黑箱。#30 与 #34 各盖住一半，没有任何一行盖住这个组合 |
| 39 | **契约违规的生成结果视为可重试** | `retry.go:64-68`、`stream.go:244-246` | ✅ **已修复**。原表漏记，且原语义与 harness9 相反。见 15b |

**本步反超 harness9 之处**（Task D 应一并核实，而不只是找缺口）：

- **`StopReason` 是数据而非 error 字符串。** harness9 的三种终止只能靠
  解析 error 文本区分，且撞上 `maxTurns` 时**丢弃整条轨迹**；`RunResult`
  把轨迹保住。
- **重试分类基于 `ProviderError.status_code`**，而 harness9 只能对错误
  文本做子串匹配（Go 的 SDK 包装丢掉了类型）。子串检查降级为
  `status_code is None` 时的兜底。
- **截断可判定。** harness9 的流式路径没有 `finish_reason`，被输出上限
  砍断的一轮与正常收敛不可区分（见 §5）。

## 附录 B —— 交付结果（2026-09-17）

`omicsclaw/engine/` 共 6 个模块、约 1,500 行，配 7 个测试文件。
`tests/schema/ tests/provider/ tests/engine/` 合计 **635 passed**
（本步开工时基线 396）。

### 交付物

| 任务 | 内容 | 测试 |
|---|---|---|
| 0 驱逐 | legacy `omicsclaw/engine/` → `omicsclaw/runtime/engine/`，12 个文件改 import 路径 | 33 → 33 passed（行为中性） |
| 1 修订 | `StreamChunk.finish_reason` + 两个 adapter + ADR 0077 附录 | 396 → 405 |
| A | `types.py`、`config.py`、`executor.py`（Protocol） | +46 |
| C | 单 Turn 并发调度 + Observation 注入 | +29 |
| B | `loop.py`、`retry.py`、`__init__.py` | +123 |
| 修复 | 评估发现的 8 条缺陷 + 4 处测试缺口 | +32 |

### 评估这道关卡起了作用

两个**只读**评估并行执行，均未参与任何代码编写，且未被告知彼此或协调者
已知的问题。它们**各自独立**撞上了同两条缺陷（重试标记表失效、Observation
按 id 配对塌陷）——这个交叉印证，比任何一份单独报告都更能说明问题是真的。

三个实现 agent 自报杀死 139 个变异体；评估方**没有采信这些表格**，而是
重新做了 44 次定向变异去验证最强的那些声称。结果：30/32（正确性）与
12/12（对照）被点名的测试抓住，两个幸存者本身就是 finding。

修完的 8 条缺陷里，有 4 条属于同一类：**「本层与两个已交付 adapter 之间
的边界」**——重试分类器和 Observation 配对都是照着一套 adapter 并不使用的
词汇写的。三个实现 agent 谁都没探这个边界，因为它们各自都在自己的车道内
是自洽的。这是并行分工的系统性盲区，值得后续步骤记住。

最有价值的一条发现不在缺陷里，而在**测试质量**上：重试分类的六个测试全都
手工构造 `ProviderError(None, "<Go 错误文本>")`，变异它们会变红——却是被
永远不可能发生的输入杀死的。fixture 与实现出自同一份 Go 源码，于是它们
彼此吻合、与真实世界无关。这正是「测试在对着实现自己的输出做断言」那个
模式，而且它伪装成了绿色。

### 计划自身的错误（一并记录，因为下一步会读这份计划）

1. **§6 称「B 与 C 相互独立」**——只在文件归属上成立，B 要调用 C 的函数。
   实际顺序是 A → C → B。
2. **§6 task 0 的文件清单漏报一个**（5 → 6，`tests/bot/test_commands_registry.py`）。
3. **§9 验收标准第 5 条自相矛盾**：要求与 `runtime.engine` 双向导入成功，
   而 §4 Q2 恰恰论证了无 SDK 时它导不进来。
4. **§7 陷阱 12 的标记表直接照抄了 harness9 的 Go 字符串**，对 Python
   adapter 一个都匹配不上——宽预算形同虚设。这是计划引入的缺陷，不是
   实现的偏差；实现方按指示照做并如实上报了。
5. **附录 A 原表有 5 行判断错误、4 项能力漏记**，已按评估结论逐行更正。

这五条的共同教训：**计划里凡是从参照系直接搬运的具体值（字符串表、
边界条件、"结构性不可能"这类断言），都必须在目标语言里重新验证一次。**
把 harness9 的结构照搬是对的，把它的字面量照搬不是。
