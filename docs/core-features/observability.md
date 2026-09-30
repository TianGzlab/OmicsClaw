# 可观测性（Observability）

`omicsclaw/observability/` 回答的问题是：**agent 运行得是否正常，花了多少 token，慢在哪里。**

在这一层之前，框架能回答"发生了什么"（`EngineEvent` 流、`TurnEvent` 帧、`hooks/audit.py` 的审计行），但没有 span，看不出一次 exchange 的结构；也没有 metric，token 消耗只能事后逐次累加 `RunResult.usage`。

本层有四个设计决定：

1. **没有给 engine 开接缝。** 它消费引擎已经发出的 `EngineEvent` 流，`omicsclaw/engine/` 一行代码都没改。
2. **span/tracer/meter 契约由本仓库定义，OpenTelemetry 只是其中一个适配器。** 不装 SDK 也能 import，也能用纯标准库的 stdout 后端。
3. **默认不采集内容。** prompt、工具参数、工具输出都不会写进 span，除非显式打开 `OMICSCLAW_OTEL_CAPTURE_CONTENT`。
4. **不观测的部署和原来一模一样。** 默认的 `Telemetry()` 不包装 provider，也不挂载 hook。

---

## 1. 系统架构

```
omicsclaw/observability/                 适配层（不是叶子层）：import schema、provider、engine、hooks
├── attributes.py   span 名、属性键、6 个 instrument 的声明表 INSTRUMENTS（纯常量）
├── config.py       ObservabilityConfig.from_env()：5 个 OTEL_* 变量 + capture_content
├── contract.py     Span / Tracer / Meter 三个 Protocol + NoopSpan/NoopTracer/NoopMeter
├── serialize.py    truncate_attr（4096 字节，UTF-8 安全）、serialize_messages、serialize_output
├── console.py      ConsoleTracer / ConsoleMeter：纯标准库的 stdout 后端（实际写到 stderr）
├── otel.py         build_otel_backend：唯一 import OpenTelemetry SDK 的模块（在函数内部 import）
├── telemetry.py    Telemetry 门面 + build_telemetry()
├── scope.py        RunScope / TurnScope：interaction 与 turn span，消费 EngineEvent
├── provider.py     TracedProvider：llm_request span + 3 个 instrument
└── hook.py         TracingHook：tool span + 2 个 instrument（挂在 hook 链尾）

omicsclaw/entry/                         组合根（三处接线）
├── assembly.py     build_telemetry → trace_provider → build_hooks(config, telemetry)
│                   AgentApp.telemetry（不会是 None）；aclose() 最后关闭 telemetry
└── turn.py         三条 exchange 路径都用 app.telemetry.run(...) 包起来并调用 scope.observe(event)
```

依赖方向是单向的。`tests/observability/test_observability_boundaries.py` 用 AST 断言 `schema`、`provider`、`engine`、`hooks`、`tools`、`context` 都**不** import 本层，本层也不 import `omicsclaw.entry`。所以整个包可以从部署中删掉，其他部分不受影响。

### 1.1 三个挂载点

```
                       build_app（omicsclaw/entry/assembly.py）
                                     │
          ┌──────────────────────────┼─────────────────────────────┐
          ▼                          ▼                             ▼
 telemetry.trace_provider()   telemetry.tool_hooks()       telemetry.run(...)
 LLMProvider → TracedProvider  → (TracingHook,)            → RunScope（每个 exchange 一个）
 未启用：原样返回 provider      未启用：()                  未启用：所有 span 都是 NOOP_SPAN
          │                          │                             │
   omicsclaw.llm_request       omicsclaw.tool          omicsclaw.interaction / omicsclaw.turn
```

三个组件之间**不互相传参**：`TracedProvider` 和 `TracingHook` 调用 `scope.current_parent()` 找到父 span，它由一个 `ContextVar` 承载。引擎位于它们与 scope 之间，引擎不应该知道它们的存在。用 `ContextVar` 的原因与 `omicsclaw/tools/context.py` 相同：每个工具调用在自己的 `asyncio.Task` 中运行，Task 创建时会复制 context，所以并发的工具调用、同一进程里的两个会话都不会看到彼此的绑定。

---

## 2. Span 树

一次流式 exchange（所有界面走的都是这条路径）产生三层 span：

```
omicsclaw.interaction          session.id  agent.type  agent.turns  agent.stop_reason  llm.tokens.*
├── omicsclaw.turn             agent.turn=1  turn.has_tool_calls=true  llm.tokens.*
│   ├── omicsclaw.llm_request  gen_ai.system  gen_ai.request.model  gen_ai.usage.*  llm.model  llm.tokens.*
│   ├── omicsclaw.tool         tool.name=bash  tool.status=ok  tool.success=true
│   └── omicsclaw.tool         tool.name=read_file …（兄弟 span 时间重叠 = 这一轮是并行执行的）
└── omicsclaw.turn             agent.turn=2  turn.has_tool_calls=false
    └── omicsclaw.llm_request
```

| span | 创建者 | 父 span | 主要属性 |
|---|---|---|---|
| `omicsclaw.interaction` | `RunScope.__aenter__` | 无（trace 根） | `session.id`、`agent.type`（默认 `main`）；结束时写入 `agent.turns`、`agent.stop_reason`（`converged` / `max_turns` / `truncated`）、`llm.tokens.input/output/cache_read` |
| `omicsclaw.turn` | `TurnScope.span()`，**惰性创建** | interaction | `agent.turn`；结束时写入 `turn.has_tool_calls` 与该轮 usage |
| `omicsclaw.llm_request` | `TracedProvider._start` | 当前 turn（阻塞路径下为 interaction） | `gen_ai.system`、`gen_ai.request.model`、`llm.model`、`gen_ai.usage.input_tokens/output_tokens`、`llm.tokens.*`；失败时写 `error.type`、`error.status_code` |
| `omicsclaw.tool` | `TracingHook.before_execute` | 当前 turn | `tool.name`、`tool.status`、`tool.success` |

几个细节：

- **一个会话有多个 exchange，就有多个 interaction trace**，它们通过 `session.id` 关联，不做嵌套。如果 span 跨整个会话一直开着，要等用户离开才会导出。`hooks/audit.py` 的审计记录使用同一个 session id，读自同一个 `ToolContext` 绑定，可以作为关联键。
- **一轮被重试时，会在同一个 turn span 下产生多个 `llm_request`**。token instrument 放在 `TracedProvider` 里，因为只有它能看到**每一次**模型调用；而 `TURN_END` 只报告最后一次尝试的用量。
- `llm.tokens.cache_read`：OmicsClaw 专门做了 prompt 前缀缓存，这个属性用来查看缓存命中率。
- `tool.status` 有四个值，直接复用 `omicsclaw.hooks.AuditOutcome`：`ok` / `error` / `denied` / `cancelled`。分类函数是 `hooks.audit.outcome_of`，与审计日志共用，所以同一次调用在 span 和审计行里的结果不会不一致。
- `TracedProvider.bind(...)` 返回的仍然是 `TracedProvider`。所以压缩阶段绑定的摘要模型（`summary_model`）的调用也会出现在 trace 里。

### 2.1 为什么 turn span 是惰性的

引擎只有 `TURN_END` 事件，没有 `TURN_START`。第 N+1 轮的工作开始于第 N 轮 `TURN_END` 之后的那一次 `__anext__`，所以打开第 N+1 轮 span 唯一可靠的时机，就是第 N 轮刚结束的时候。但在那一刻还不知道这次 run 会不会继续。`TurnScope` 因此只保存"要打开一个 span"的**意图**，直到第一次有调用方需要父 span（也就是模型调用）时才真正创建。如果 run 就此结束，丢掉的只是一个意图，不会导出一个空的"幻影" span。

代价：turn span 从模型调用开始计时，排在它前面的压缩和计划注入都落在 turn 之外，但仍在 interaction 之内。

### 2.2 阻塞路径只有两层

`AgentEngine.run` 驱动的是同一个内核，但它**会丢弃**事件。`entry/turn.py` 的 `run_turn` 因此传入 `turn_events=False`：scope 把 interaction span 直接作为父 span，模型调用和工具调用都挂在它下面。run 结束后，`run_turn` 用返回的 `RunResult` 补发一个 `EngineEvent.done(result)`，让 interaction span 能写上 `agent.turns` 和 `agent.stop_reason`。

这个标志是为了防止出错：

- 传了 `turn_events=False` 却收到了 turn 事件：从下一个边界开始分组，能自我纠正；
- 保持默认 `True` 却一个 `TURN_END` 都没收到，并且 run 超过一轮：退出时记一条 warning，指出这些模型调用被归到了一个 turn span 下。

如果没有这个标志，一次五轮的 run 会变成**一个标着 `agent.turn=1` 的 span 装下全部五次模型调用**。那不是少了一层，而是一个错误的数字（plan 0043 §8，本步发现的最严重缺陷）。

三条 exchange 路径：

| 路径 | 位置 | turn_events | 层数 |
|---|---|---|---|
| `run_turn`（阻塞） | `omicsclaw/entry/turn.py` | `False` | 2 |
| `stream_turn`（流式） | `omicsclaw/entry/turn.py` | 默认 `True` | 3 |
| `TurnRunner._sequence`（`SessionRegistry` 使用，CLI / Desktop / Channel 都走这条） | `omicsclaw/entry/turn.py` | 默认 `True` | 3 |

---

## 3. 不给 engine 开接缝：消费 EngineEvent

OmicsClaw 的循环已经通过 `run_stream` 发布了观测所需的时刻，而且带有足够的信息：`TURN_END` 带 `usage`，`TOOL_RESULT` 带 `duration_s`，`DONE` 带 `RunResult`（包括 `stop_reason`）。所以 `RunScope` 只是一个**消费者**：

```python
async with app.telemetry.run(session_id=sid, prompt=text) as scope:
    async for event in _stream(app, exchange, text):
        scope.observe(event)
        yield event
```

`RunScope.observe` 只读三种事件，其余的有意忽略：

| 事件 | 处理 |
|---|---|
| `TOOL_START` | 把当前 turn 标记为"有工具调用"。工具 span 和计时由 `TracingHook` 负责，它在调用内部，能分辨"被拒绝"和"崩溃" |
| `TURN_END` | 关闭当前 turn span，计数 `omicsclaw.agent.turns.total`，并为下一轮登记一个意图 |
| `DONE` | 保存 `RunResult`，在 `__aexit__` 时写到根 span 上 |
| `TOOL_RESULT` | **忽略**：`EngineEvent.duration_s` 是在执行器接缝外面测的，**包括**人的审批等待时间，不能在仪表盘上当作"工具耗时" |
| `TEXT_DELTA` / `REASONING_DELTA` | 忽略：完整的消息已经记录在 `llm_request` span 上 |

结果：`omicsclaw/engine/` 的 docstring 里"no I/O, no logging"的承诺，在有了遥测层之后仍然成立。代价是没有 `TURN_START` 事件，这直接导致了 §2.1 和 §2.2 的两个设计。

---

## 4. 六个 instrument

全部在 `attributes.INSTRUMENTS` 中以"类型、单位、描述"的形式声明。`tests/observability/test_attributes.py` 断言每个 `METRIC_` 常量都出现在表里，所以新增 instrument 时忘了写单位会导致测试失败，不会带着空白坐标轴上仪表盘。

| 名称 | 类型 | 单位 | 记录者 | 维度 |
|---|---|---|---|---|
| `omicsclaw.llm.request.duration` | Histogram | `s` | `TracedProvider`（成功和失败都记） | `gen_ai.system`、`llm.model` |
| `omicsclaw.llm.tokens.input` | Counter | `{token}` | `TracedProvider` | 同上 |
| `omicsclaw.llm.tokens.output` | Counter | `{token}` | `TracedProvider` | 同上 |
| `omicsclaw.tool.calls.total` | Counter | `{call}` | `TracingHook`（四种结果都记） | `tool.name`、`tool.status` |
| `omicsclaw.tool.execution.duration` | Histogram | `s` | `TracingHook` | `tool.name`、`tool.status` |
| `omicsclaw.agent.turns.total` | Counter | `{turn}` | `RunScope`（每个 `TURN_END`） | 无 |

六个 instrument 都带单位，`tool.status` 有四个值。

---

## 5. 内容采集：默认关闭

如果**总是**把整个消息列表、工具参数和工具输出序列化到 span 属性里，这不适合 OmicsClaw：`SAFETY_RULES` 第 1 条是"Genetic data never leaves this machine"，而 OmicsClaw 的 prompt 经常会写出队列名、测序 run 下的文件路径、差异表达分析的输出。一旦打开 OTLP 导出，这些内容就会发到第三方服务。

所以 `ObservabilityConfig.capture_content`（`OMICSCLAW_OTEL_CAPTURE_CONTENT`）**默认关闭**，受它控制的属性有：

| 属性 | 位置 | 内容 |
|---|---|---|
| `langfuse.trace.input` / `langfuse.trace.output` | interaction span | 用户 prompt / 最终回复 |
| `langfuse.observation.input` / `langfuse.observation.output` | llm_request span | 消息列表 / 模型输出 |
| `langfuse.observation.input` / `langfuse.observation.output` | tool span | 工具参数 / 工具输出 |
| `error.message` | llm_request span | 厂商返回的错误文本 |

关闭时照常记录的有：span 树、turn 结构、模型名、token 用量、耗时、工具名、结果、全部 metric，以及 `error.type` 和 `error.status_code`。仪表盘需要的数据一样不少，丢掉的只有 payload。

另外两处收紧，都有测试覆盖：

- **工具失败只记录异常类名**（`Span.record_error` 只保存 `type(error).__name__`）。无论开关状态如何，tool span 都不会写 `error.message`。一次 `read_file` 失败的信息里会带着 `/data/GSE12345/patient_07.h5ad` 这样的路径。
- **provider 错误的 message 也受开关控制**。`429 rate limited` 不涉及内容，但内容策略拒绝会回显被拒绝的文本，参数校验错误会回显字段值。"默认不外传 payload"的承诺不能依赖厂商恰好返回哪一种错误。

打开开关后，payload 会经过 `truncate_attr` 截断到 4096 **字节**（按字节计，是因为 4096 个中文字符会有 12 KiB），先替换无法编码的代理字符，截断点落在码点边界上，末尾加 `…[truncated]`。`serialize_messages` 不包含 `reasoning_content`；有工具调用时，`serialize_output` 优先输出工具调用。

**测试把"关闭时没有 payload"钉死了**：会遍历**全部**属性和**全部** metric 标签寻找 payload 字符串，而不是只检查已知的 key 名（plan 0043 §11.1）。

---

## 6. 后端与配置

### 6.1 环境变量

`ObservabilityConfig.from_env()` 读取以下变量。`launch` 层会把 `.env` 的内容写入进程环境，所以写在 `.env` 里同样有效。

| 变量 | 默认 | 说明 |
|---|---|---|
| `OTEL_ENABLED` | `false` | 接受 `1` / `true` / `yes` / `on`（忽略大小写和首尾空白） |
| `OTEL_SERVICE_NAME` | `omicsclaw` | 后端用来分组的 `service.name` |
| `OTEL_EXPORTER_TYPE` | `noop` | `noop` / `stdout` / `otlp`；无法识别的值按 `noop` 处理，不报错 |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | 空 | **base URL**，不带 `/v1/traces`，后缀由代码拼接 |
| `OTEL_EXPORTER_OTLP_HEADERS` | 空 | `key=val,key2=val2`，在**第一个** `=` 处切分（token 里常带 `=`）；没有 `=` 的项会被丢弃 |
| `OMICSCLAW_OTEL_CAPTURE_CONTENT` | `false` | 本仓库独有。用 `OMICSCLAW_` 前缀，因为没有任何 OTEL 规范定义这个变量 |

`ObservabilityConfig.records` 等于 `enabled and exporter is not NOOP`，只有两者都满足时才会记录。`__repr__` 只输出 header 的**数量**（`headers=2`），不输出其值（其中有凭据）；`otlp_headers` 被冻结为只读的 `MappingProxyType`。`__post_init__` 会把手写的 `"stdout"` 字符串转换成 `ExporterType.STDOUT`（这修复了一个缺陷：`StrEnum` 用 `==` 比较时相等，但本包到处用的 `is` 比较不成立，导致部署静默失效）。

### 6.2 `build_telemetry` 的决策

```
build_telemetry(config=None)            config 缺省时 = ObservabilityConfig.from_env()
├── not records                → Telemetry(config=…)                  完全不记录（NOOP_TRACER / NOOP_METER）
├── exporter = stdout          → ConsoleTracer + ConsoleMeter          纯标准库；关闭时输出一次 metric 汇总
└── exporter = otlp
    ├── endpoint 为空           → warning + 回落为不记录
    ├── SDK 未安装（ImportError）→ warning（提示 pip install 'omicsclaw[otel]'）+ 回落
    ├── 构造异常                → exception 日志 + 回落
    └── 成功                    → Telemetry(tracer, meter, on_flush, on_shutdown)
```

**所有失败都降级为不记录，并只报一次**，不会让一次运行（可能是一个六小时的比对任务）因为遥测而中断。注意：`build_telemetry` 的 docstring 里还保留着"初始化失败即致命"的旧说法，以 `otel.py` 的 docstring 和本文为准。

`Telemetry.active` 通过判断 `tracer is not NOOP_TRACER` 得出，不单独存储标志，所以不会与实际对象图不一致。`Telemetry.config` 记录的是**请求的配置**，不是实际结果：OTLP 构造失败时，`config.exporter` 仍然是 `otlp`，而 `active` 为 `False`。这两个事实合在一起，正好是运维排查需要的信息。

### 6.3 OTLP 适配器（otel.py）

- 需要安装可选依赖：`pip install 'omicsclaw[otel]'`（`pyproject.toml` 的 `otel` extra：`opentelemetry-sdk>=1.24`、`opentelemetry-exporter-otlp-proto-http>=1.24`）。SDK 只在 `_build` 函数内部 import，所以没有安装 SDK 的机器照样可以 `import omicsclaw.entry`。
- trace 走 OTLP/HTTP，endpoint 为 `<base>/v1/traces`，由代码显式拼接（SDK 不同版本在是否自动追加后缀上行为不一致，猜错的结果是一个没人看得到的 404）。`BatchSpanProcessor` 的批量延迟为 2000 ms（`_BATCH_DELAY_MS`）。
- metric 走 `<base>/v1/metrics`，每 30 s 导出一次（`_METRIC_INTERVAL_MS`）。**metric 与 trace 各自独立 fail-open**：Langfuse 只接收 trace，对 `/v1/metrics` 返回 404，metric 失败不会拖累 trace。
- tracer 从**本模块创建的 provider** 获取（`provider.get_tracer(name)`），不走全局访问器；全局 TracerProvider 仍会被设置一次（`_global_provider_set`），让第三方插桩复用同一条导出管线。
- `force_flush` 的上限为 5000 ms（`_FLUSH_TIMEOUT_MS`）。`shutdown` 会依次关闭 trace 和 metric 两个 provider，前一个出错时后一个也会关闭。
- **运行期的导出失败也能看到**（`_surface_export_failures`）：Python SDK 通过 `logging` 的 `opentelemetry` logger 报告批次失败。本模块只在该 logger 和 root logger 都没有 handler 时，才挂一个 stderr handler（前缀 `[OTEL]`，级别 WARNING），不修改 `propagate`。如果没有这一步，Langfuse key 过期后，trace 会在某天悄无声息地不再出现。
- `_OtelSpan.record_error` 只调用 `set_status(ERROR, 类名)`，不调用 `record_exception`，因为后者会附上包含消息和路径的 traceback。
- `_OtelTracer.start_span` 通过显式的 `context=set_span_in_context(parent)` 指定父 span，不使用 OTEL 的 current-span 机制。

### 6.4 flush 与关闭

- `RunScope.__aexit__` 在正常退出和**普通 `Exception`** 时都会 `await force_flush()`（出错的那次 exchange 的 trace 正是人最急着看的）；只有非 `Exception` 的 `BaseException`（取消、`GeneratorExit`）才跳过 flush，因为在取消过程中 await 并捕获异常会吞掉真正的取消。`test_scope.py::test_a_cancellation_during_a_flush_is_not_swallowed` 钉住这一行为。
- `force_flush` 和 `shutdown` 都通过 `asyncio.to_thread` 执行，不阻塞事件循环（SDK 里这两个操作是同步的：一个要等 HTTP 往返，一个要 join 后台线程）。
- `AgentApp.aclose()` 最后调用 `telemetry.aclose()`，此时其他可能还在产生 span 的组件都已关闭；即使前面的步骤失败，也会关闭 telemetry。

### 6.5 容错：遥测最多丢掉一个 span，不影响运行

- `TracedProvider._start` 在一次真实模型调用的热路径上，出错时回落为 `NOOP_SPAN`，不会抛出异常；
- `TurnScope` 创建 span 失败时设置 failed 标志并回落到父 span，trace 少一层（每轮最多记一条日志）；
- `RunScope.__aenter__` 和 `TracingHook.before_execute` 在 `start_span` 时就一次性传入**所有属性**。如果先创建再单独设置属性，第二步出错时，已创建的 span 就没人去 `end()` 了，这条 trace 会悄无声息地消失（plan 0043 §11.1 修复的缺陷类型）；
- `TracingHook` 的逐调用状态用栈语义的 `ContextVar`（`_Call.call_token`）保存，嵌套调用退出时恢复外层状态，而不是清空。

---

## 7. stdout 后端（console.py）

`OTEL_EXPORTER_TYPE=stdout` 使用 `ConsoleTracer` / `ConsoleMeter`，**只依赖标准库**。贡献者不用安装任何东西就能看到一次 run 的 span 树，整个测试套件也能在一个真实后端上运行。名字是 `stdout`，但实际写到 **`sys.stderr`**，避免破坏占用 stdout 的终端界面。

- **每个 span 在 `end()` 时写一行 JSON**（带时长），所以读的时候是由内向外的：子 span 先于父 span 出现。用 `span_id` / `parent_span_id` 把它们对上。`end()` 是幂等的。
- `ConsoleMeter` 在内存中聚合，`shutdown`（`Telemetry.aclose`）时调用 `dump()` 输出一行 `{"metrics": …}` 汇总；没有记录任何数据时不输出。
- 写入用一把 `threading.Lock` 保护，避免并发结束的工具 span 交错成一行无法解析的文本。

下面是一次两轮 run（第一轮调用一个工具，第二轮收敛）的实际输出，由 `tests/observability/_support.py` 的 `Scripted` provider 和 `Echo` 工具驱动：

```json
{"attributes": {"gen_ai.request.model": "gpt-test", "gen_ai.system": "scripted", "gen_ai.usage.input_tokens": 10, "gen_ai.usage.output_tokens": 5, "llm.model": "gpt-test", "llm.tokens.input": 10, "llm.tokens.output": 5}, "duration_s": 3e-05, "name": "omicsclaw.llm_request", "parent_span_id": "e174088b5106f09a", "span_id": "d109a5489600bea1", "trace_id": "2e2b8e45…"}
{"attributes": {"tool.name": "echo", "tool.status": "ok", "tool.success": true}, "duration_s": 2.8e-05, "name": "omicsclaw.tool", "parent_span_id": "e174088b5106f09a", "span_id": "f98c35f15d5c3c41", "trace_id": "2e2b8e45…"}
{"attributes": {"agent.turn": 1, "llm.tokens.input": 10, "llm.tokens.output": 5, "turn.has_tool_calls": true}, "duration_s": 0.00049, "name": "omicsclaw.turn", "parent_span_id": "7f9ef093061adc84", "span_id": "e174088b5106f09a", "trace_id": "2e2b8e45…"}
{"attributes": {"gen_ai.request.model": "gpt-test", "gen_ai.system": "scripted", "gen_ai.usage.input_tokens": 7, "gen_ai.usage.output_tokens": 3, "llm.model": "gpt-test", "llm.tokens.input": 7, "llm.tokens.output": 3}, "duration_s": 2.7e-05, "name": "omicsclaw.llm_request", "parent_span_id": "b5017892d4ca09f9", "span_id": "de344138385ce072", "trace_id": "2e2b8e45…"}
{"attributes": {"agent.turn": 2, "llm.tokens.input": 7, "llm.tokens.output": 3, "turn.has_tool_calls": false}, "duration_s": 7.4e-05, "name": "omicsclaw.turn", "parent_span_id": "7f9ef093061adc84", "span_id": "b5017892d4ca09f9", "trace_id": "2e2b8e45…"}
{"attributes": {"agent.stop_reason": "converged", "agent.turns": 2, "agent.type": "main", "llm.tokens.input": 17, "llm.tokens.output": 8, "session.id": "s1"}, "duration_s": 0.000703, "name": "omicsclaw.interaction", "parent_span_id": "", "span_id": "7f9ef093061adc84", "trace_id": "2e2b8e45…"}
{"metrics": {"omicsclaw.agent.turns.total": [{"attributes": {}, "count": 2, "total": 2.0}], "omicsclaw.llm.tokens.input": [{"attributes": {"gen_ai.system": "scripted", "llm.model": "gpt-test"}, "count": 2, "total": 17.0}], "omicsclaw.tool.calls.total": [{"attributes": {"tool.name": "echo", "tool.status": "ok"}, "count": 1, "total": 1.0}], "…": "…"}}
```

（`trace_id` 与部分 metric 条目已省略。）本地启用：

```bash
OTEL_ENABLED=true OTEL_EXPORTER_TYPE=stdout oc cli 2> trace.jsonl
```

---

## 8. 接入观测平台

以下接入方式都走 `otel.py` 的 OTLP/HTTP 导出，前提是已安装 `omicsclaw[otel]`。本仓库的测试环境没有安装 SDK，`tests/observability/test_otel.py` 在未安装时会整体 skip，所以下面的步骤没有在真实后端上验证过。

### 8.1 Langfuse

1. 在 Langfuse 项目中创建 API key，得到 Public Key（`pk-lf-…`）和 Secret Key（`sk-lf-…`）。
2. 生成 Basic 认证串：

   ```bash
   AUTH=$(echo -n "pk-lf-YOUR_PUBLIC_KEY:sk-lf-YOUR_SECRET_KEY" | base64 -w 0)
   ```

3. 写入 `.env`（`.env.example` 第 6 节有同样的模板）：

   ```bash
   OTEL_ENABLED=true
   OTEL_EXPORTER_TYPE=otlp
   OTEL_EXPORTER_OTLP_ENDPOINT=https://cloud.langfuse.com/api/public/otel
   OTEL_EXPORTER_OTLP_HEADERS=Authorization=Basic <AUTH>,x-langfuse-ingestion-version=4
   # OMICSCLAW_OTEL_CAPTURE_CONTENT=false   # 默认；见下
   ```

   `x-langfuse-ingestion-version=4` 不能省：缺了它，trace 在 Langfuse 里会延迟出现。OmicsClaw 不会自动加这个 header，`OTEL_EXPORTER_OTLP_HEADERS` 原样透传。header 字段接受任意多组 `key=value`，Langfuse 文档要求的其他 header 可以用逗号追加。

4. 运行 `oc cli`，产生一次对话后，在 Langfuse 的 Traces 页面可以看到 `omicsclaw.interaction` → `omicsclaw.turn` → `omicsclaw.llm_request` / `omicsclaw.tool`，以及 token 用量和模型名。

**注意**：`capture_content` 关闭时，Langfuse 的 Input / Output 面板是**空的**，这是设计如此。只有当接收端部署在存放数据的同一台机器上、并且需要调试 prompt 时，才应该打开 `OMICSCLAW_OTEL_CAPTURE_CONTENT=true`；打开后 prompt、工具参数和输出都会发往 endpoint。Langfuse 返回的 `/v1/metrics` 404 不会影响 trace。

### 8.2 Jaeger（本地）

```bash
docker run --rm -p 16686:16686 -p 4318:4318 jaegertracing/all-in-one

export OTEL_ENABLED=true
export OTEL_EXPORTER_TYPE=otlp
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318
oc cli
# 打开 http://localhost:16686，Service 选 omicsclaw
```

其他 OTLP/HTTP 接收端（本地 OTel Collector、Grafana Tempo 等）配置方式相同：把 base URL 填到 `OTEL_EXPORTER_OTLP_ENDPOINT`。

---

## 9. 与其他层的关系

- **审计日志 vs tracing**：`AuditHook`（`--audit-log`）是持久化的**本地**记录，每次调用一行，只写参数摘要，挂在链首，能记录被其他 hook 拒绝的调用。`TracingHook` 生成 span 和 metric，挂在链尾，只测量工具本身。两者由不同的设置启用，互相不能替代，但共用 `AuditOutcome` 这一套结果分类。`build_hooks(config, telemetry)` 负责把两者分别放到链首和链尾（详见 `hooks.md`）。
- **权限**：hook 链在权限网关内部，所以**被规则拒绝的调用不会产生 tool span**。被拒绝属于权限事件，只在 `omicsclaw.permission.gate` 的 warning 日志中留下记录。
- **子代理**：根据代码推断，`ChildRunner` 使用的是已经被 `TracedProvider` 包装过的同一个 provider，子代理的工具也是父代理挂好 hook 的同一批对象；`TracingHook.before_execute` 把 tool span 设为当前父 span。所以子代理的 `llm_request` 和 `tool` span 会嵌套在父代理 `task` 工具的 `omicsclaw.tool` span 之下。子代理没有自己的 interaction/turn span，`agent.type` 也不会被设为 `sub`（目前没有调用方传 `agent_type="sub"`）。

---

## 10. 已知限制

- **第三方 OTEL 自动插桩的 span 不会嵌套在这些 span 下面。** 本层用显式传参来指定父 span，不往 OTEL 的 context 里写东西，所以那些库的 span 会各自成为独立 trace 的根（仍然走同一条导出管线）。要补上这一点只需改 `otel.py`（`contract.py` 与 plan 0043 §11.3 都有记录）。
- **turn span 从模型调用开始计时**，压缩和计划注入落在 turn 之外（仍在 interaction 之内）。
- **阻塞路径（`run_turn`）只有两层**，并且因为它只补发了 `DONE` 事件、没有 `TURN_END`，**`omicsclaw.agent.turns.total` 在这条路径上不会计数**（`agent.turns` 属性仍然会写入根 span）。用 `ConsoleMeter` 实测：流式路径两轮 run 计数为 2，阻塞路径没有这个 metric。目前没有界面走这条路径，这是 `run_turn` 契约带来的代价，不是事件模型的限制。
- **`TurnScope` 的失败标志是每轮一个**：后端持续不可用时，每一轮的第一次模型调用各记一条日志（plan 0043 §11.3，不修）。
- **被权限规则拒绝的调用不会产生 tool span**（hook 链在 gate 内部）。
- **子代理没有自己的 interaction/turn 层级**，`agent.type` 恒为 `main`；`attributes.py` 中 `ATTR_AGENT_TYPE` 的 docstring 仍写着"nothing in this tree spawns sub-agents yet"，这句已经过时。
- **一个进程只设置一次全局 TracerProvider**（`_global_provider_set`）。重新构建应用时，全局 provider 仍是第一次构建的那个；本层自己的 tracer 不受影响。
- **OTLP 路径没有在真实后端上跑过**，本仓库环境没有安装 SDK，`test_otel.py` 会 skip。整个重建框架也都还没有接过真实的 provider 端点（FRAMEWORK-REBUILD "Debts carried forward"）。
- `build_telemetry` 的 docstring 仍然写着"初始化失败即致命"的旧说法，这句已被 `otel.py` 与 plan 0043 §11.2 更正，是一处过时的注释。`console.py` 的 docstring 提到的 `oc tui` / `oc interactive` 两个界面也已不存在（TUI 没有移植）。

---

## 11. 文件索引

| 文件 | 职责 |
|---|---|
| `omicsclaw/observability/__init__.py` | 公共 API、用法、四条设计决策、环境变量一览 |
| `omicsclaw/observability/attributes.py` | `SPAN_*`、`ATTR_*`、`METRIC_*`、`INSTRUMENTS`、`DEFAULT_SERVICE_NAME` |
| `omicsclaw/observability/config.py` | `ObservabilityConfig`、`ExporterType`、`parse_otlp_headers` |
| `omicsclaw/observability/contract.py` | `Span`、`Tracer`、`Meter`、`NOOP_SPAN`、`NOOP_TRACER`、`NOOP_METER`、`AttributeValue` |
| `omicsclaw/observability/serialize.py` | `truncate_attr`、`MAX_ATTRIBUTE_BYTES`、`serialize_messages`、`serialize_output` |
| `omicsclaw/observability/console.py` | `ConsoleTracer`、`ConsoleSpan`、`ConsoleMeter` |
| `omicsclaw/observability/otel.py` | `build_otel_backend`、`OtelBackend`、`_surface_export_failures` |
| `omicsclaw/observability/telemetry.py` | `Telemetry`（`run`、`trace_provider`、`tool_hooks`、`force_flush`、`aclose`）、`build_telemetry` |
| `omicsclaw/observability/scope.py` | `RunScope`、`TurnScope`、`current_parent`、`push_parent` / `pop_parent` |
| `omicsclaw/observability/provider.py` | `TracedProvider` |
| `omicsclaw/observability/hook.py` | `TracingHook` |
| `omicsclaw/hooks/audit.py` | `AuditOutcome`、`outcome_of`（与 tracing 共用） |
| `omicsclaw/entry/assembly.py` | `build_app(telemetry=)`、`build_hooks(config, telemetry)`、`AgentApp.telemetry`、`AgentApp.aclose` |
| `omicsclaw/entry/turn.py` | `run_turn`（`turn_events=False`）、`stream_turn`、`TurnRunner._sequence` |
| `pyproject.toml` | `otel` extra |
| `.env.example` | 第 6 节：Observability |
| `tests/observability/` | 各模块单元测试、端到端 span 树、依赖边界、OTLP 适配器（SDK 缺失时 skip） |
| `tests/entry/test_telemetry_wiring.py` | 装配：未启用时对象图不变、hook 顺序、阻塞路径两层、关闭顺序 |

参考：`docs/plans/0043-observability-layer.md`；`docs/FRAMEWORK-REBUILD.md` Step 6.11。
