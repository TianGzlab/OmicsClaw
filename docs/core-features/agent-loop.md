# Agent Loop 核心实现原理

## 1. 架构总览

OmicsClaw 的核心是一个**标准 ReAct 循环**（`omicsclaw/engine/`）。每个 Turn 调用一次模型：模型请求工具，就执行工具并把结果作为 Observation 追加进历史，然后进入下一个 Turn；模型不再请求工具，循环收敛退出。

引擎只做四件事：Turn 编排、工具调度、Observation 注入、决定何时停止。system prompt 的组装、会话持久化、上下文压缩、执行计划、工具本身都不在引擎里。它们通过引擎声明的几个 `Protocol` 接缝接入，由 `omicsclaw/entry/` 这个组合根装配。

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          AgentEngine (engine/loop.py)                   │
│                                                                         │
│   exchange / exchange_stream        （外壳：渲染 prompt → 拼接 → 委托 → commit）│
│            │                                                            │
│            ▼                                                            │
│   run / run_stream ──► _kernel（唯一一份 ReAct 循环）                      │
│                                                                         │
│   每个 Turn：                                                            │
│   ┌──────────────┐ available_tools() ┌──────────────────────┐          │
│   │  history     │◄──────────────────│ ToolExecutor          │          │
│   └──────┬───────┘                   │ (tools.ToolRegistry)  │          │
│          │ HistoryCompactor.compact  └──────────▲───────────┘          │
│          │ TurnAugmentor.augment                │ execute(call)        │
│          ▼                                      │                      │
│   ┌──────────────────────┐  generate /   ┌──────┴───────────────┐      │
│   │ generate_with_retry  │  generate_    │ execute_tool_calls    │      │
│   │  └─ _attempt         │  stream       │ 批次/并发/超时/事件      │      │
│   │     └─ turn strategy │──────────────►│ (engine/executor.py)  │      │
│   └──────────┬───────────┘ LLMProvider   └──────────┬───────────┘      │
│              │  Completion                          │ ToolResult       │
│              ▼                                      ▼                  │
│      _stop_reason_for ── 有工具调用 ──► _answer_every_call → observations │
│              │ 无 / 被截断                                                │
│              ▼                                                          │
│      RunResult(messages, stop_reason, usage, turns, prompt)             │
└─────────────────────────────────────────────────────────────────────────┘
```

| 组件 | 代码位置 | 职责 |
|------|---------|------|
| `Message` / `Role` / `ToolCall` / `ToolResult` / `ToolDefinition` / `Usage` | `omicsclaw/schema/message.py` | 跨层共享的厂商中立数据类型 |
| `StreamChunk` / `StreamChunkType` | `omicsclaw/schema/stream.py` | Provider 层的流式增量 |
| `LLMProvider` / `Completion` / `ProviderError` | `omicsclaw/provider/base.py` | 模型调用契约（详见 [provider.md](provider.md)） |
| `AgentEngine` | `omicsclaw/engine/loop.py` | 四个入口 + 唯一的循环内核 `_kernel` + 两种 turn strategy |
| `execute_tool_calls` / `observations` | `omicsclaw/engine/executor.py` | 同一 Turn 内多工具调度：分批、并发、单工具超时、事件、结果按位置归位 |
| `ToolExecutor` / `ConcurrencyAwareExecutor` / `DeadlineAwareExecutor` / `TimeoutPause` | `omicsclaw/engine/executor.py` | 工具层接缝（一个必需 + 两个可选 Protocol） |
| `generate_with_retry` / `backoff_delay` | `omicsclaw/engine/retry.py` | 模型调用的应用层重试：两套独立预算 + 错误分类 |
| `EngineConfig` | `omicsclaw/engine/config.py` | 一次运行的预算（冻结 dataclass） |
| `RunResult` / `StopReason` / `EngineEvent` / `EngineEventType` / `EngineError` | `omicsclaw/engine/types.py` | 阻塞返回值、流式事件、停止原因、引擎自身不变量错误 |
| `HistoryCompactor` | `omicsclaw/engine/compactor.py` | 每次模型调用前改写历史的接缝 |
| `TurnAugmentor` | `omicsclaw/engine/augmentor.py` | 每次模型调用前向"发送副本"追加消息的接缝 |
| `PromptSource` / `RenderedPrompt` | `omicsclaw/engine/prompt.py` | 引擎向渲染器索取 system prompt 的接缝 |
| `Conversation` | `omicsclaw/engine/conversation.py` | exchange 读入历史、交还轨迹的接缝 |
| `build_app` / `AgentApp` | `omicsclaw/entry/assembly.py` | 组合根：构造 provider、registry、prompt 装配器与 `AgentEngine` |
| `run_turn` / `stream_turn` / `TurnRunner` | `omicsclaw/entry/turn.py` | 为一次 exchange 装配 compactor / augmentor / conversation 并驱动引擎 |

**分层约束**：`omicsclaw/engine/` 只导入 `omicsclaw.schema`、`omicsclaw.provider` 与标准库，不导入厂商 SDK，也不做 I/O、不打日志。前一条由 `tests/engine/test_engine_is_a_leaf_layer.py` 检查导入边界来保证；"不打日志"只是各模块 docstring 里写明的约定，**没有测试强制**。

## 2. ReAct 设计理念

ReAct 的三个动作在 schema 里都有对应的**字段**，没有只靠约定：

| ReAct | schema 表达 |
|-------|------------|
| Thought | `Message.reasoning_content` |
| Action | `Message.tool_calls`（`tuple[ToolCall, ...]`） |
| Observation | `ToolResult`，经 `ToolResult.to_message()` 投影为 `Role.TOOL` 消息 |

循环只根据一个条件分支：`Message.is_action`（即 `bool(tool_calls)`）。

```
Turn N:
  provider(history, tools) → assistant 消息（reasoning + content + tool_calls）
  → finish_reason 为 length/max_tokens：TRUNCATED，停
  → is_action 为假：CONVERGED，停
  → 否则：执行全部工具调用 → 每个调用一条 Role.TOOL 消息 → Turn N+1
```

**一个内核，两个出口。** `run`（阻塞）和 `run_stream`（流式）共用 `_kernel`，只有注入的 *turn strategy* 不同：`run` 注入 `_blocking_turn`（调 `provider.generate`），`run_stream` 注入 `_streaming_turn`（调 `provider.generate_stream`）。所以阻塞调用方不用为流式付出代价，也不用从 delta 里重新拼消息。

strategy 不能在生成事件的同时直接返回消息：PEP 525 规定 async generator 里的 `return` 不能带值。所以 strategy 一边 `yield` 事件，一边把 `Completion` 填进一个可变容器 `_TurnOutcome`。`execute_tool_calls` 也用同样的 out-parameter 形式（传入的 `results` 列表），整个包只有这一种写法。

| turn strategy | 调用 | 产生的事件 |
|---------------|------|-----------|
| `_blocking_turn` | `await provider.generate(history, tools)` | 无（代码末尾有一个不可达的 `yield`，只为让它成为 async generator） |
| `_streaming_turn` | `provider.generate_stream(history, tools)` | `TEXT_DELTA` / `REASONING_DELTA`；流里出现 `ERROR` chunk 就抛出 `ProviderError` |

## 3. 数据模型（`omicsclaw/schema`）

### 3.1 角色体系

```
Role (StrEnum)
├── "system"     系统提示词
├── "user"       人类输入，以及以用户口吻注入的提醒
├── "assistant"  模型输出：推理、文本、工具调用
└── "tool"       工具结果（Observation），用 tool_call_id 关联
```

这里有**四个**角色。单独设一个 `tool` 角色后，"这条是人说的还是机器说的"直接由数据回答，适配器不用再根据某个字段是否为空去推断。

### 3.2 核心类型

```
Message (frozen, slots)
├── role               Role
├── content            str
├── reasoning_content  str                 Thought，会持久化
├── tool_calls         tuple[ToolCall,...] Action
├── tool_call_id       str                 仅 role=tool
├── name               str                 仅 role=tool，工具名
└── is_error           bool                仅 role=tool
    构造器: Message.system / user / assistant / tool；编辑: replace(**changes)

ToolCall (frozen)             ToolResult (frozen)              ToolDefinition (frozen)
├── id         str            ├── tool_call_id  str            ├── name          str
├── name       str            ├── name          str            ├── description   str
└── arguments  str = "{}"     ├── output        str            └── input_schema  dict
    parsed_arguments()        ├── is_error      bool
                              └── metadata      Mapping（只读，永不发给模型）
                                  to_message() → Role.TOOL Message

Usage (frozen)
├── input_tokens / output_tokens / cache_read_tokens / cache_write_tokens
├── total_tokens            (property)
├── uncached_input_tokens   (property，永不为负)
└── __add__                 跨 Turn 累加
```

**关键设计决策：**

- **`ToolCall.arguments` 保持未解析的 JSON 文本**。字节级一致对 prompt 前缀缓存和回放证据都重要：先 decode 再 encode 可能打乱键的顺序。`parsed_arguments()` 遇到无法解析的载荷时返回 `{}` 而不抛异常，所以一次被截断的流只损失一个 Turn，不会让整个 run 崩掉。
- **`reasoning_content` 会持久化**，不是只拿来显示。有些 thinking 端点会拒绝"历史 assistant 消息丢了推理内容"的请求（例如 DeepSeek 的 thinking 模式）。
- **`Message` 是冻结的**。历史在两次压缩之间只追加；如果某条消息被原地修改，建立在它之上的前缀缓存会悄悄失效。需要编辑时用 `replace()`。
- **`ToolDefinition` 只有三个字段**。风险级别、审批模式、并发安全性这些本地执行策略留在工具层，不会被序列化进 prompt。
- **`ToolResult.metadata`** 存放没有厂商字段可对应的执行事实，永不发给模型。
- **`Usage` 带缓存拆分**：命中缓存的前缀和新读入的前缀在 token 数相同时，价格可以差一个数量级。

### 3.3 流式数据类型

#### Provider 层：`StreamChunk`（`omicsclaw/schema/stream.py`）

```
StreamChunk (frozen)
├── type           StreamChunkType
├── delta          str       TEXT_DELTA / REASONING_DELTA
├── message        Message   DONE：完整的 assistant 消息（含已累积完成的 tool_calls）
├── usage          Usage     DONE：可为 None
├── error          str       ERROR
└── finish_reason  str       DONE：厂商原始停止原因
```

| StreamChunkType | 含义 | 携带数据 |
|-----------------|------|---------|
| `text_delta` | 文本增量 | `delta` |
| `reasoning_delta` | 推理增量（命名沿用 OmicsClaw 的 `reasoning_content` 词汇，而非 "thinking"） | `delta` |
| `done` | 流结束 | `message`、`usage`、`finish_reason` |
| `error` | 流失败 | `error` |

工具调用参数的分片**从不**作为 chunk 暴露。适配器在内部用 `ToolCallAccumulators` 累积，只在 `DONE` 时一次性发出，所以任何消费者都看不到、也无法执行一个参数还没收全的调用。`finish_reason` 是 step 3 唯一一处有声明的 schema 修订：没有它，因输出上限被截断的流和正常结束的流无法区分。

#### Engine 层：`EngineEvent`（`omicsclaw/engine/types.py`）

`EngineEvent` 是一个冻结 dataclass，带枚举标签，形状仿照 `StreamChunk`：

| EngineEventType | 含义 | 有效字段 |
|-----------------|------|---------|
| `text_delta` | 文本增量 | `delta`、`turn` |
| `reasoning_delta` | 推理增量 | `delta`、`turn` |
| `tool_start` | 即将执行一个工具调用 | `tool_call`、`turn` |
| `tool_result` | 一个工具结束（包括失败） | `tool_result`、`turn`、`duration_s` |
| `turn_end` | 一个 Thought→Action→Observation 周期结束 | `turn`、`usage` |
| `done` | 整个 run 结束 | `result`（`RunResult`） |

**没有 `error` 事件。** async generator 能传递异常，异常会在消费者的 `async for` 处重新抛出。

- `usage`（`TURN_END` 上）是 provider 报告的**实际**用量，从不是估算。只有流式路径能表达"后端没报告"（`None`）；阻塞路径的 `Completion.usage` 不可为 None，所以一定是 `Usage()`，此时零值要理解为"免费或没报告"。
- `duration_s`（`TOOL_RESULT` 上）是调度器测得的墙钟时间，包含工具等待人工审批的时间，而单工具超时预算恰恰把这段时间排除在外（见 §5.4）。

**事件流示例**（一次两轮的 `run_stream`）：

```
Turn 1:
  reasoning_delta × N
  text_delta × N          "先看一下这份 Visium 数据的结构。"
  tool_start              ToolCall(bash, …)
  tool_start              ToolCall(read_file, …)      ← 同一批并发，按实际开始顺序
  tool_result             ToolResult(read_file) duration_s=0.02
  tool_result             ToolResult(bash)      duration_s=41.7
  turn_end                turn=1 usage=Usage(…)
Turn 2:
  text_delta × N          最终回复（无工具调用）
  turn_end                turn=2
  done                    RunResult(stop_reason=converged, turns=2)
```

## 4. 循环流程（`_kernel`）

```
history = list(messages); usage = Usage(); turns = 0; stop = MAX_TURNS
while not (0 < max_turns <= turns):
    turns += 1
    tools = tuple(executor.available_tools())           # 每 Turn 重读
    sent  = tuple(history)
    compactor?.compact(sent, tools) → (msgs, keep)      # 可改写发送副本，keep 时写回 history
    augmentor?.augment(sent, tools) → extra             # 只追加到 sent
    generate_with_retry(_attempt(strategy, sent, tools, turns, outcome))
    usage += completion.usage
    history.append(completion.message)                  # 完整 assistant 消息
    verdict = _stop_reason_for(completion)
    if verdict is None:
        execute_tool_calls(...) → results (每调用一个槽)
        history.extend(observations(_answer_every_call(calls, results)))
    yield TURN_END(turns, outcome.usage)
    if verdict: stop = verdict; break
yield DONE(RunResult(tuple(history), stop, usage, turns))
```

### 4.1 三种停止方式（`StopReason`）

| 值 | 触发条件 | 说明 |
|----|---------|------|
| `CONVERGED` | assistant 消息没有请求工具 | ReAct 的正常出口 |
| `MAX_TURNS` | 达到 `max_turns` 时模型仍在请求工具 | 默认结论：只有从 `while` 条件退出才会落到这里；**轨迹保留** |
| `TRUNCATED` | `finish_reason.lower()` 为 `length`（OpenAI 系）或 `max_tokens`（Anthropic） | 被截断的回复同样不含工具调用，没有这个值就会被误报为完成 |

`StopReason` **没有** `ERROR` 或 `CANCELLED`：provider 失败以 `ProviderError` 抛出，取消以 `asyncio.CancelledError` 原样传播。所以只要拿到 `RunResult`，就说明循环是自己停下来的。

`_stop_reason_for` **先判断截断**。被截断的 Turn 可能带着从中途断掉的流里累积出来的工具调用，看起来格式正确，但模型其实没说完，执行它比停下更糟。这个 Turn 仍会追加到历史，于是轨迹以"没被回答的工具调用"结尾；从这里恢复的调用方需要自己回答或丢弃这些调用，引擎不会为没执行的调用编造 Observation。

`max_turns` 在**每次模型调用之前**检查，`max_turns=1` 恰好允许一次调用；`<= 0` 表示不设上限。

### 4.2 每 Turn 重读工具列表

`available_tools()` 每个 Turn 都会调用。registry 的内容可能在运行途中变化（例如 MCP 服务器异步连上），如果只在构造时读一次，之后注册的工具会被悄悄隐藏。

### 4.3 一次尝试：`_attempt`

`_attempt` 位于重试预算和 turn strategy 之间，负责两个不变量：

1. **每次尝试前清空 `_TurnOutcome`**。否则第 1 次尝试已经交付 `DONE` 随后失败、第 2 次尝试没交付 `DONE` 的情况下，会把第 1 次的旧答案当成新结果。
2. **什么都没填上的尝试一律抛 `ProviderError`**，不当作空 Turn。有两种形态：流在拿到可用的 `DONE` 前结束；`generate` 返回 `None`，或 `generate_stream` 返回的东西没有 `__aiter__`。之所以归为 `ProviderError`，是为了让它落在 `generate_with_retry` 的预算里：丢了半截的流正是重试预算要处理的场景。

### 4.4 Observation 注入

`execute_tool_calls` 的结果是"每个调用一个槽"，`results[i]` 对应 `calls[i]`，槽为 `None` 表示该 worker 什么也没产出（例如工具把 `CancelledError` 抛给了调度器）。然后由 `_answer_every_call` 保证**每个 `ToolCall` 恰好一条 Observation**：

- 槽为 `None`，或槽数少于调用数：补一条 `is_error=True` 的结果，内容为 `tool '<name>' produced no result`。Anthropic 要求每个 `tool_use` 在下一条消息里都有对应的 `tool_result`，缺一条会在下一次请求时报 400。
- 结果的 `tool_call_id` 和调用不一致（包装型 registry 或 MCP 代理可能换了 id）：按**位置**配对，把 id 改回调用的 id，原 id 记在 `metadata["reported_tool_call_id"]`。
- 按位置配对，不按 id 查表，因为 id 不保证唯一：厂商省略 id 时适配器不会自己生成，`ollama` 预设就可能让两个调用都带 `""`。

`observations(results, config)` 调用 `ToolResult.to_message()`，并把空输出替换为 `EngineConfig.empty_output_placeholder`（默认 `"[tool completed with no output]"`）。这样做一是因为部分后端会以 400 拒绝空内容的 `tool_result`，二是空 Observation 等于白白浪费一个 Turn。`is_error` 随消息传给适配器（Anthropic 的 `tool_result.is_error`）。

## 5. 工具执行（`omicsclaw/engine/executor.py`）

### 5.1 工具接缝

```python
@runtime_checkable
class ToolExecutor(Protocol):
    def available_tools(self) -> Sequence[ToolDefinition]: ...
    async def execute(self, call: ToolCall) -> ToolResult: ...

@runtime_checkable
class ConcurrencyAwareExecutor(Protocol):       # 可选
    def is_concurrency_safe(self, name: str) -> bool: ...

@runtime_checkable
class DeadlineAwareExecutor(Protocol):          # 可选
    def use_timeout_pause(self, pause: TimeoutPause) -> AbstractContextManager[None]: ...
```

`omicsclaw/tools/registry.py` 的 `ToolRegistry` 在**结构上**满足这三个接口，不导入 `omicsclaw.engine`。两个可选 Protocol 故意没有并入必需接口：没有实现它们的 executor（测试替身、第三方适配器）仍按原方式调度。`is_concurrency_safe` 按工具**名**回答，而不是按 `ToolCall`，所以 executor 不会根据模型给的参数来决定调度。

### 5.2 调度：分批、并发与写屏障

```
calls = [read_file, web_fetch, write_file, read_file, bash]
         safe       safe       UNSAFE      safe       UNSAFE
                     │
      _concurrency_groups
                     ▼
batches = [(0,1), (2,), (3,), (4,)]
          并发      屏障    单独     屏障
```

- `_concurrency_groups` 按调用顺序切批：不是并发安全的调用单独成一批（**屏障**），相邻的安全调用合成一批并发执行。批与批顺序执行，前一批全部完成后下一批才开始。
- 满足以下任一条件时，所有调用放在同一批：`EngineConfig.serialize_unsafe_tools=False`，或 executor 没有实现 `ConcurrencyAwareExecutor`。`is_concurrency_safe` 抛异常时视为 `False`（保守取值）。
- 在 foundation tools 中，声明 `concurrency_safe=True` 的是 `read_file`（`tools/builtin/read.py`）、`web_fetch`、`web_search`，其余默认不安全。所以同一 Turn 里对同一路径发出的两个 `write_file` 会串行执行，不会丢更新。
- 屏障只能约束**一个 Turn 之内**。跨 Turn、跨会话的冲突（两个 Channel 会话、子 agent）仍靠 `omicsclaw/tools/_pathlock.py` 的路径锁。

每批内部：

| 问题 | 解决方案 |
|------|---------|
| 多个 worker 写同一结果集 | 预分配 `slots = [None] * len(calls)`，按 index 写入 |
| 结果顺序 | 槽位即调用顺序，与完成顺序无关 |
| 并发度 | `max_concurrent_tools > 0` 时用 `asyncio.Semaphore` 限流，`0` 表示不限 |
| 事件实时性 | worker 把 `tool_start` / `tool_result` 放进 `asyncio.Queue`，主协程边收边 `yield`，一个 30 秒的工具开始时消费者立即就能看到 |
| 何时一批结束 | 每个 worker 在任意退出路径上都 `put_nowait(None)` 作为哨兵，按 worker 计数排空队列 |
| 审批隔离 | 每个调用用 `asyncio.ensure_future` 起独立 Task，Task 会 `copy_context()`，`tools/context.py` 的每调用审批状态依赖这一点。以下两种写法会破坏它：内联 `await` 调用而不起 Task；多个 Task 共享同一个 `Context` |
| 放弃 / 取消 | `finally` 中 cancel 所有已启动的 Task 并 `gather(..., return_exceptions=True)` 回收，不会有孤儿任务 |

**代价是活性。** 屏障会挡住本 Turn 后面所有批次。如果屏障调用正在等人工审批，而审批暂停了该调用的超时（§5.4），这个 Turn 可能无限期等待。限制等待时长的责任在发出审批提示的那一方（`AppConfig.approval_timeout_s`）。

### 5.3 单工具超时与异常转 Observation（`_execute`）

- 超时**按调用**计算，而不是按 Turn：慢工具只会变成一条失败的 Observation，不会连带取消同批的其他工具。`tool_timeout <= 0` 表示不设限。
- 用 `asyncio.timeout` 而不用 `asyncio.wait_for`，因为前者可以查询：只有 `budget.expired()` 为真时才报 `tool '<name>' timed out after <N>s`。Python 3.11+ 的 `socket.timeout` 就是内建的 `TimeoutError`，`web_fetch` 这类工具自己的读超时会抛出同一个类；如果这时报"引擎超时"，就会把"服务不可达"误报成"工具太慢"。
- 捕获 `except Exception`，不捕获 `BaseException`：`CancelledError` 原样传出。其他异常变成 `tool '<name>' raised <ExcType>: <msg>`（`is_error=True`），让模型看到具体原因并自行修正。第三方 executor 抛异常也不会让 run 崩掉。

### 5.4 审批暂停（`TimeoutPause`）

如果超时计时覆盖整个 `execute`，而审批的 `await` 就在其中，那么用户 61 秒才点"批准"时，模型会被告知 `timed out after 60s`，这是错误的信息，还会引导模型去"让工具更快"。

```
_execute
 └─ async with asyncio.timeout(t) as budget
     └─ _bound_timeout_pause(executor, budget)       # executor 实现了 DeadlineAwareExecutor 才生效
         └─ executor.use_timeout_pause(lambda: _paused(budget))
             └─ ToolRegistry → tools/context.py 发布到 ContextVar
                 └─ require_approval 在人工往返期间 enter pause
                     _paused: 记下剩余秒数 → budget.reschedule(None)
                              退出时 → reschedule(now + remaining)
```

- 退出暂停时恢复的是**进入时剩余的秒数**，不是原来的绝对截止时刻。否则暂停结束后预算可能已经过期。
- 嵌套时，内层看到的 `budget.when()` 为 `None`，什么也不做，由外层负责恢复。两个**并列**打开的暂停（一个调用里 `gather` 两个都要问人的子任务）不在支持范围内，先打开的那个会提前恢复计时。
- `use_timeout_pause` 打开失败时只会失去暂停能力（被 `suppress(Exception)` 吞掉），不会让每个工具调用都失败。
- 被暂停的调用在引擎这一侧**没有上限**。消费 `execute_tool_calls` 的一方必须能在事件之间处理审批请求，可以用独立 Task，也可以在 `async for` 循环体里 await 请求队列。只在事件间隙轮询的消费者会和审批方互相等待，形成死锁。`tests/engine/test_executor.py` 固定了受支持的写法。

## 6. 重试（`omicsclaw/engine/retry.py`）

厂商 SDK 只重试"首字节之前"的失败。流开始之后才断（代理掐掉半截响应、headers 发出后才来的 5xx）的情况，由 `generate_with_retry` 处理。

```
generate_with_retry(attempt_factory, config):
  loop:
    try: 逐个 yield attempt() 的事件；成功 return
    except ProviderError as e:
      budget = _budget_for(e)
      None 或已用尽 → raise
      sleep(backoff_delay(base, n, cap))
```

| 错误 | 判定 | 使用的预算 |
|------|------|-----------|
| `status_code` 为 429 或 ≥ 500 | 结构化 | `generate_retries`（默认 3，base 1.0s，上限 30s） |
| 其他 4xx | 结构化 | **不重试**：请求本身有问题，重试不会有不同结果 |
| `status_code is None` 且消息命中 `_TRANSPORT_MARKERS` | 子串匹配 | `network_retries`（默认 6，base 5.0s，上限 60s） |
| `status_code is None`，未命中 | — | `generate_retries` |

- 两套预算**互不借用**。
- `_TRANSPORT_MARKERS` 是 Python SDK **实际会产生**的字符串：`connection error`、`apiconnectionerror`、`apitimeouterror`、`timed out`、`certificate_verify_failed`、`ssl`、`getaddrinfo`、`name or service not known`、`[errno 111]`、`connection reset`、`connection refused`。最初的版本用的是 `x509:`、`dial tcp` 这类 Python SDK 不会产生的字符串，结果一个也匹配不上，宽预算实际从未生效。这是 step 3 评估中发现的缺陷。
- `backoff_delay(base, attempt, cap) = min(base * 2**(attempt-1), cap)`，超过 `_MAX_BACKOFF_SHIFT = 32` 次翻倍时直接返回 cap。base 如果 ≤ 0，会被替换为默认值（1.0 / 5.0），防止退避变成空转。
- 预算里的数字表示**总尝试次数**，不是"额外重试次数"：`generate_retries=1` 等于不重试，配成 `0` 效果也一样。
- 只捕获 `ProviderError`。`EngineError`（引擎自身不变量被破坏）和 `CancelledError` 都不重试。
- **流式重试会重放**：第 2 次尝试从头开始生成，已经渲染了半段文本的消费者会看到文本重新开始。

## 7. 四个入口与生命周期接缝

### 7.1 `run` / `run_stream`

```python
engine = AgentEngine(provider, tools, EngineConfig(max_turns=50))
result = await engine.run(messages, compactor=c, augmentor=a)       # RunResult
async for event in engine.run_stream(messages, compactor=c, augmentor=a):
    ...                                                             # 最后一个是 DONE
```

- 输入是一段完整对话，输出 `RunResult.messages` 是**包含输入**的完整轨迹（如果 compactor 写回过，则是改写后的版本），可以直接喂给下一次 run。
- `run` 丢弃中间事件，只取 `DONE` 里的结果；如果内核结束时没有 `DONE`，抛 `EngineError`。
- `run_stream` **不是** `async def`，直接返回迭代器，用法是 `async for e in engine.run_stream(...)`。
- `AgentEngine` 不持有对话。provider、executor 和冻结的 `EngineConfig` 在它的整个生命周期内不变，所以同一个引擎可以安全地服务多个会话。

### 7.2 `exchange` / `exchange_stream`

适用于调用方手里有"system prompt 来源 + 历史"，而不是一份现成消息列表的场景。它们只是**外壳**，不是第二个循环：

```
prompt.render()            → Message.system（仅当有 PromptSource）
conversation.messages()    → 历史（不含 system）
+ Message.user(user_text)  （user_text 为空时不追加）
→ run / run_stream         （内核不变）
→ conversation.commit(轨迹去掉 system 消息)
→ RunResult.prompt = 本次渲染结果
```

- `prompt` 与 `conversation` 在构造函数中给出的是**默认值**，每次调用都可以覆盖。
- `commit` 是**整体替换**，不是追加。compactor 写回后，被折叠掉的原始消息已经不在轨迹里；如果只追加本次新增的消息，压缩在单次 exchange 内有效，跨 exchange 就失效了（plan 0027 §12.10.1 返工的核心问题）。
- system 消息**按角色**剔除，不按下标剔除，因为 compactor 可能改变了位置。
- `exchange_stream` 先 `commit`，**再**转发 `DONE`。消费者拿到答案就 `break` 是常见写法，而 `break` 之后在最后一个 `yield` 后面的代码不一定会执行。在 `DONE` 之前放弃流、或 exchange 抛出异常，都**不会 commit**，对话保持原样。
- 没有 deadline：等多久是部署自己的策略。entry 层用 `AppConfig.turn_timeout_s` 在外面套 `asyncio.timeout`。

### 7.3 可选接缝

| 接缝 | 调用时机 | 能做什么 | 不能做什么 |
|------|---------|---------|-----------|
| `PromptSource.render() -> RenderedPrompt` | 每次 exchange **一次**，在第一次模型调用之前 | 提供 `system_prompt` 字符串；渲染对象原样放进 `RunResult.prompt`（节段统计、token 估算等随之保留） | 不会每个 Turn 重渲染，所以 exchange 中途修改 prompt 文件不会改变人设 |
| `HistoryCompactor.compact(history, tools)` | 每个 Turn，在读完工具列表之后 | 返回 `None` 表示不改；返回 `(messages, keep)` 时，本次发送 `messages`，`keep` 为真则同时写回 run 的 history | 空的 `messages` 会被忽略 |
| `TurnAugmentor.augment(history, tools)` | 每个 Turn，**在 compactor 之后**，模型调用之前 | 返回的消息只追加到本次**发送副本** | 永远不进入 history 或 `RunResult.messages`，也不跨 Turn 累积 |
| `Conversation.messages()` / `commit()` | exchange 开始时读一次，成功结束时写一次 | 由实现决定存到哪里 | 失败或放弃时不会 commit |

compactor 和 augmentor 分成两个窄接缝，而没有合成一个宽接缝，原因是 `entry/turn.py` 的 `_outcome` 会读 compactor 的三个具体属性。如果有东西包装或替换了 compactor，却忘了转发这些属性，不会报错，只会悄悄丢掉压缩记录（这就是"R3 形状"的缺陷）。

## 8. 配置：`EngineConfig`

`EngineConfig` 是冻结 dataclass，**不读取任何环境变量**，由调用方构造后传入。原因是：如果 Turn 上限随启动进程的 shell 变化，同一个 benchmark 在两台机器上的结果就没法比较。`with_overrides(**kw)` 采用 copy-on-write，遇到未知字段抛 `TypeError`。

| 字段 | 默认值 | 说明 |
|------|--------|------|
| `max_turns` | `50` | 每次 run 的模型调用上限，`<= 0` 表示不限。参照点：旧 OmicsClaw 用 20，会卡住 30 轮的 benchmark 任务 |
| `tool_timeout` | `60.0` | 单个工具调用的秒数，`<= 0` 表示不限 |
| `max_concurrent_tools` | `0` | 单个 Turn 内并发工具数上限，`0` 表示不限；只限流，不改变顺序 |
| `serialize_unsafe_tools` | `True` | 非并发安全的工具作为屏障单独运行 |
| `generate_retries` | `3` | 一般失败的总尝试次数 |
| `generate_retry_base` | `1.0` | 一般失败重试的首次退避秒数 |
| `network_retries` | `6` | 传输层失败的总尝试次数 |
| `network_retry_base` | `5.0` | 传输层失败重试的首次退避秒数 |
| `empty_output_placeholder` | `"[tool completed with no output]"` | 空工具输出的替代文本 |

**部署时实际生效的值**：`AppConfig.engine_config()`（`omicsclaw/entry/config.py`）只设置两个字段，其余沿用上表默认值：

| `EngineConfig` 字段 | 来源 | 部署默认 |
|--------------------|------|---------|
| `max_turns` | `AppConfig.max_turns` ← `--max-turns` / `OMICSCLAW_MAX_TURNS` | `50` |
| `tool_timeout` | `AppConfig.tool_timeout_s` ← `--tool-timeout` / `OMICSCLAW_TOOL_TIMEOUT_S` | `600.0` |

600 秒是 owner 的裁定（plan 0031 §12-2）：`spatial-deconv` 或一次 STAR 比对要跑几分钟到几小时，60 秒是没有经过核实就照搬过来的数字。`bash` 工具的超时从同一个值推出：`AppConfig.bash_timeout()` = `tool_timeout_s - ENGINE_TIMEOUT_MARGIN`（`omicsclaw/tools/builtin/bash.py` 中为 `15.0`），让引擎自己的截止时间先触发。

## 9. entry 层如何驱动循环

```
surface（entry/cli、entry/desktop、entry/channel）
  └─ attach_sessions(await open_app(config))   # open_app → build_app(config)
       provider = telemetry.trace_provider(provider_from_env(config.provider, config.model))
       registry = build_registry(...)            # 工具 → hooks → 权限门 → ToolRegistry
       app_prompt = build_prompt(default_sections(...))
       engine = AgentEngine(provider, registry, config.engine_config(), prompt=app_prompt)

每次用户消息：
  entry.turn.TurnRunner._sequence  （surface 通过 SessionRegistry 提交）
    exchange = _assemble(app, history, session_id=…, state=…)
       conversation = _Carried(history)                 # 满足 Conversation，只存在内存里
       compactor    = build_compactor(...)              # context.ProgressiveCompactor，满足 HistoryCompactor
       augmentor    = build_injector(...)               # planning.PlanInjector，满足 TurnAugmentor
    async with app.telemetry.run(...) as scope:
       async for event in app.engine.exchange_stream(user_text, conversation=…,
                                                    prompt=app.prompt, compactor=…, augmentor=…):
           scope.observe(event)                         # 可观测层消费事件，引擎没有 observer 接缝
           publish(TurnEvent.from_engine(event, …))     # 转为面向 surface 的 TurnEvent
    return _outcome(result, exchange)                   # TurnOutcome：要保留的历史 + 压缩状态
```

- 阻塞路径 `run_turn` 用 `_run` 调 `engine.exchange`；流式路径 `stream_turn` 和 `TurnRunner` 用 `_stream` 调 `engine.exchange_stream`。三条路径都走同一个 `_assemble`。
- 落盘由 `SessionRegistry`（`omicsclaw/entry/session.py`）负责，它要同时保存历史和 `CompactionState`，而后者引擎看不到。所以 `_Carried.commit` 只在内存里记下轨迹。
- 审批事件不属于 `EngineEventType`。它由 `entry.ApprovalBroker` 以 `TurnEventType.APPROVAL_REQUIRED` 帧发出，与引擎事件在同一个 `TurnStream` 中交错。
- 子 agent（`omicsclaw/entry/subagent.py`）同样是一次 `AgentEngine(provider, child_registry, engine_config)` 构造加一次 `exchange_stream`，`conversation` 保持 `None`，上下文隔离就是这样实现的。

## 10. 完整数据流示例

用户在 CLI 中说"对 `examples/demo_visium.h5ad` 做预处理"：

```
exchange 开始:
  render() → system: OMICSCLAW.md + 安全/工具指引/环境等节段
  history: [...之前的对话...]
  user:    "对 examples/demo_visium.h5ad 做预处理"

Turn 1  compactor: 预算未达阈值 → None
        augmentor: 会话没有计划 → []
        provider.generate_stream(sent, tools)
          assistant: reasoning="需要先读 SKILL.md…"
                     tool_calls=(use_skill{"name":"spatial-preprocess"},)
        execute_tool_calls → 一批（use_skill）
          tool: SKILL.md 正文 + skill 目录            (tool_call_id 对应)
Turn 2  provider → tool_calls=(bash{"command":"python skills/spatial/spatial-preprocess/
                                  spatial_preprocess.py --input … --output …"},)
        bash 非并发安全 → 单独一批；超时 = tool_timeout(600s)
          tool: stdout/stderr 摘要
Turn 3  compactor: （假设）上下文压力达到 WARN 档 → 把超大的工具结果 offload 到
                   <workspace>/.omicsclaw/tool_results/<session>/…，原位置换成占位文本
        provider → assistant: "预处理完成，…"（无 tool_calls）
        _stop_reason_for → CONVERGED
DONE    RunResult(messages=…, stop_reason=converged, turns=3, usage=Σ, prompt=render)
        → Conversation.commit(去掉 system 的完整轨迹) → SessionRegistry 落盘
```

## 11. 已知限制

| 限制 | 现状 |
|------|------|
| `EngineConfig.tool_timeout = 60.0` 是照搬的数字 | 直接构造 `EngineConfig()` 时仍是 60 秒；只有经过 `AppConfig.engine_config()` 的部署才是 600 秒 |
| 被暂停的调用没有上限，屏障会放大这个问题 | 等人工审批的屏障调用会挡住本 Turn 后续所有批次；上限由 surface 的 `approval_timeout_s` 提供，默认 `None`（一直等） |
| 并列的两个审批暂停 | 只有嵌套情况处理正确；并列时先关闭的那个会提前恢复计时 |
| `EngineEventType` 里没有审批 | surface 从引擎事件流无法得知正在等人，只能靠 entry 层的 `TurnEvent` |
| 阻塞路径无法表达"用量未报告" | `Completion.usage` 不可为 None，阻塞 Turn 的 `TURN_END.usage` 为零值时，可能是免费，也可能是没报告。要解决需要改 `omicsclaw.provider` |
| 流式重试会重放文本 | 第 2 次尝试从头生成，UI 上会看到文本重新开始 |
| `TRUNCATED` 的轨迹以没被回答的工具调用结尾 | 调用方如果要从这里恢复，必须自己补上 Observation 或丢弃这些调用 |
| Anthropic 的 thinking 无法回放 | `Message` 没有地方存 thinking 签名，适配器发出请求时会丢掉 `reasoning_content`（见 [provider.md](provider.md)） |
| "引擎不打日志、不做 I/O"没有测试强制 | `test_engine_is_a_leaf_layer.py` 只检查导入边界 |
| `_outcome` 依赖 compactor 的具体属性 | R3 形状的缺陷面从三处收敛成一处，但没有消除；`_compact_only` 仍然单独调用 `compose` |
| 没有调用前的 token 估算事件 | 需要 token 计数器，这属于 `omicsclaw/context`；entry 层通过 compactor 的 `on_measure` 回调发布测量结果 |

## 12. 设计原则总结

| 原则 | 体现 |
|------|------|
| 标准 ReAct | 每个 Turn 调一次模型，`Message.is_action` 是唯一的分支条件 |
| 一个内核 | `run` / `run_stream` / `exchange` / `exchange_stream` 都经过 `_kernel` |
| 接口隔离 | `LLMProvider`、`ToolExecutor` 以及四个生命周期接缝都是结构化 `Protocol`，实现方不用导入引擎 |
| 冻结配置 | `EngineConfig` 不读环境变量，也不能在运行中修改 |
| 顺序由位置保证 | 每个调用一个槽，按下标写入，按位置配对 |
| 失败即 Observation | 工具异常、超时、没有结果都变成 `is_error` Observation，模型可以自行修正 |
| 取消不算失败 | `CancelledError` 永不被吞，也不会变成结果 |
| 该停就停 | `CONVERGED` / `MAX_TURNS` / `TRUNCATED` 三种停止都保留轨迹 |

## 13. 文件索引

| 文件 | 内容 |
|------|------|
| `omicsclaw/schema/__init__.py` | schema 公开面（8 个类型） |
| `omicsclaw/schema/message.py` | `Role`、`ToolCall`、`ToolResult`、`ToolDefinition`、`Message`、`Usage` |
| `omicsclaw/schema/stream.py` | `StreamChunkType`、`StreamChunk` |
| `omicsclaw/engine/__init__.py` | 引擎公开面（18 个名字） |
| `omicsclaw/engine/loop.py` | `AgentEngine`、`_kernel`、`_attempt`、两种 turn strategy、`_opening`、`_settle`、`_stop_reason_for`、`_answer_every_call` |
| `omicsclaw/engine/executor.py` | 工具接缝、`execute_tool_calls`、`observations`、`_concurrency_groups`、`_execute`、`_paused` |
| `omicsclaw/engine/retry.py` | `generate_with_retry`、`backoff_delay`、`_TRANSPORT_MARKERS` |
| `omicsclaw/engine/config.py` | `EngineConfig` |
| `omicsclaw/engine/types.py` | `StopReason`、`EngineEventType`、`EngineEvent`、`RunResult`、`EngineError` |
| `omicsclaw/engine/compactor.py` | `HistoryCompactor` |
| `omicsclaw/engine/augmentor.py` | `TurnAugmentor` |
| `omicsclaw/engine/prompt.py` | `PromptSource`、`RenderedPrompt` |
| `omicsclaw/engine/conversation.py` | `Conversation` |
| `omicsclaw/entry/assembly.py` | `build_app`：构造 `AgentEngine` |
| `omicsclaw/entry/config.py` | `AppConfig.engine_config()`、`bash_timeout()` |
| `omicsclaw/entry/turn.py` | `_assemble`、`_Carried`、`run_turn`、`stream_turn`、`TurnRunner` |
| `omicsclaw/tools/registry.py` | `ToolRegistry`：结构上满足三个工具接缝 |
| `tests/schema/`、`tests/engine/` | 契约、循环、调度、重试、分层测试 |
| `docs/plans/0027-react-main-loop.md` | 计划、陷阱清单、§12 引擎终态 |
| `docs/FRAMEWORK-REBUILD.md` | Step 1 / Step 3 / "Parallel tool calling" 小节 |
