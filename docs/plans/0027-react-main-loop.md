# 计划 0027 — ReAct 主循环

框架分阶段重建的第 3 步（见 `docs/FRAMEWORK-REBUILD.md`）。第 1 步
（`omicsclaw/schema/`，ADR 0077）与第 2 步（`omicsclaw/provider/`，
计划 0026）已交付；本步写的是驱动这些类型流动的循环。

状态：**已交付**（2026-09-17）。六个任务全部完成，两轮独立只读评估
（正确性 + harness9 对照）已执行并把发现修完。测试 **635 passed**。
结果见附录 B。

## 1. 目标

一个把 ReAct 循环推到收敛的引擎：

```
Message → ToolCall → ToolResult → Message
```

循环持有 Turn 编排、工具调度、Observation 注入与终止判定。除此之外
一概不持有——不做 prompt 装配（第 5 步）、不做会话持久化（第 6 步）、
不实现工具（第 4 步）。

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
- **不做历史持久化与压缩。** harness9 的 engine 持有 `memory.Session`
  与 `memory.Compactor`，两者都属于第 6 步。
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
| 29 | PlanStore 集成 + 写时检查点 | `loop_phases.go` | ⬜ 推迟——planning 层不存在 |
| 30 | `EngineObserver` 生命周期钩子（OTEL） | `observer.go` | ⬜ 推迟，**理由很弱**：「层不存在」正是本计划在 #31/工具那一行**拒绝接受**的论证——`ToolExecutor` 被声明出来恰恰因为第 4 步不存在。更好的理由是流式事件词汇已带 turn 与工具边界；但它只覆盖 `run_stream`，而 `run()` 丢弃全部事件（见 #38） |
| 31 | `PermissionMode` + 人类审批回路 | `permission.go`、`stream.go` | ⬜ 推迟至第 4 步——审批是工具层策略 |
| 32 | 子代理进度事件 | `stream.go` `EventSubAgent` | ⬜ 推迟——ADR 0077 已显式排除 `SubAgentUpdate` |
| 33 | 跨 goroutine `SetSession` + 入口快照 | `options.go`、`loop_phases.go` | ⬜ 不适用——依赖 #21，且 Python 单事件循环无此竞态形态 |
| 34 | 结构化日志（`logfmt`） | 贯穿全包 | ⬜ 不做——本层不产生日志，与 `schema` / `provider` 两层一致 |
| 35 | **单工具引擎侧精确耗时进入事件载荷** | `tools_exec.go:64-66`、`stream.go:100-106` | ⬜ **原表漏记**。`EngineEvent` 无耗时字段。这是 Surface 能拿到的唯一 per-tool 成本信号，且**只有引擎测得出来**——工具层看不到信号量排队时间。不被任何层阻塞，代价是两个 `time.monotonic()` 加一个字段 |
| 36 | **工具缝上的带外通道** | `tools_exec.go:58-60`、`stream.go:203-205` | ⬜ **原表漏记**。Go 经 ctx 向工具注入审批回调与子代理进度 sink；本层的缝是 `execute(call) -> ToolResult`，零 ctx、零回调。#31/#32 推迟的是*策略*，但真正冻结它们的是这个无参缝。§11 承诺第 4 步「不 import 本模块」地满足该 Protocol，所以第 4 步要么改已发布的缝，要么改用 `contextvars` |
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
