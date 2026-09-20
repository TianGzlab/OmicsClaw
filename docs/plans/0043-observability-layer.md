# 计划 0043 — `omicsclaw/observability/`：可观测性层

> 状态：**已实现并经两轮独立只读审核**（2026-09-20）。
> `tests/observability/` 257 项 + `tests/entry/test_telemetry_wiring.py` 17 项全绿。
> §8 记录实现期被自己的测试抓出的**三个真缺陷**，其中第二个
> （阻塞路径把整轮 run 的所有模型调用塞进一个 `agent.turn=1` 的 span）
> 是本步最严重的问题——它产出的不是"缺一层"，而是**错误的数字**。
> §11 记录两轮审核的发现与返工：正确性审核找出一类 span 泄漏和一条
> 没被任何测试钉住的不变量；对等性审核推翻了本文档原先的一条
> **对参考实现的事实性误读**，并找出一条完全没被记录的缺失特性。

参考实现：`/workspace/dataset/private/zhouwg_data/harness9`
（`internal/observability/` 六个文件 1370 行、`internal/engine/observer.go`、
`cmd/harness9/main.go:411-416`）。

## 1. 现状：唯一没人回答的问题是"它跑得怎么样"

重构到第 6.10 步为止，这棵树能回答"发生了什么"（`EngineEvent` 流、
`hooks/audit.py` 的审计行、`entry/events.py` 的 `TurnEvent` 帧），
但没有任何地方回答**"是否正常 / 花了多少 / 哪里慢"**：

- 没有 span，一次 exchange 的结构不可见；
- 没有 metric，token 消耗只能靠事后读 `RunResult.usage` 一次一次加；
- `hooks/audit.py` 自己的 docstring 把这件事点名留给了别人：
  *"**No OpenTelemetry.** … A deployment that wants OTEL writes a
  twelve-line sink; a deployment that does not is not made to carry the
  dependency."*

本计划就是那个部署侧的答案，写一次而不是每处十二行。

## 2. 决策：**不给 engine 开 seam**，改为消费 `EngineEvent`

这是本层与参考实现差别最大、也最值得写下来的一条。

harness9 必须开 seam：Go 的 loop 只能被回调观察，所以
`internal/engine/observer.go` 声明了四方法的 `EngineObserver` 接口，
`AgentEngine` 存一个，`runLoop` 在四处调用它。

**本仓库的 loop 已经在发布同样的四个时刻，而且信息更多**：
`run_stream` 产出的 `EngineEvent` 带 `TURN_END`+`usage`、
`TOOL_RESULT`+`duration_s`、`DONE`+`RunResult`（含 `stop_reason`）。
于是 `RunScope` 是一个**消费者**，而不是一个必须切进 leaf 层的钩子。

代价与收益都写清楚：

- `omicsclaw/engine/` **一行未改**，它 docstring 里
  "no I/O, no logging" 的承诺在可观测层存在之后依然为真；
- `tests/observability/test_observability_boundaries.py`
  用 AST 断言 `engine`/`provider`/`hooks`/`schema`/`tools`/`context`
  **都不 import** 本层——箭头单向，本层可以整包删掉而其余不受影响；
- 代价是**没有 `TURN_START` 事件**，这条直接决定了 §5 的两个设计。

## 3. 决策：契约是我们自己的，OTEL 只是一个适配器

`omicsclaw/observability/contract.py` 用标准库声明 `Span` / `Tracer` /
`Meter` 三个 Protocol 加三个 noop 实现，`otel.py` 是唯一知道
OpenTelemetry 存在的模块，`console.py` 是一个**纯标准库**的可用后端。

为什么不直接依赖 `opentelemetry-api`（它自带 noop，本模块能缩成三行）：

1. **那会让一个可选功能变成硬依赖。** 本次重构每一层都能在什么都没装的
   机器上 import——`provider/base.py` 把这条写进了自己的 docstring——
   一个 import 不了的遥测契约会让 `import omicsclaw.entry` 在从没想要
   遥测的机器上直接失败。
2. **那会在部署做决定之前先把数据模型定死。** OTEL 的 `Span` 带 events、
   links、status code 和一整套 context API，本层只用其中十分之一；
   照着全接口写再只用十分之一，正是那十分之一变得难找的原因。

放弃了什么，也写明：**第三方 OTEL 自动插桩不会嵌到这些 span 里面**
（它们对着 OTEL 的 context 编程，本层什么都不往那里放）。`otel.py` 仍然
设置全局 TracerProvider，所以那类库的 span 会走同一条导出管线，只是各自
成为自己 trace 的根。要补这个缺口只需改一个适配器，不动契约。

`stdout` 后端是纯标准库的直接好处有两个：贡献者不装任何东西就能看到一次
run 的 span 树；整个测试套件能跑一个**真后端**，而不是只跑那个必然满足
契约的 noop。

## 4. 决策：**内容捕获默认关闭**——与参考实现的实质性偏离

harness9 **总是**把整个消息列表、工具参数和工具输出序列化进 span 属性
（`provider.go:86` 与 `:105` 无条件调用 `setInputAttrs`，后者在 `:141` 写入
`serializeMessages`；输出在 `provider.go:93` 与 `:131`；工具参数在
`hook.go:77`，工具输出在 `hook.go:90`）。对一个编码 harness 这很合理。
**对 OmicsClaw 不合理**：`CLAUDE.md` 第一条安全规则是
*"Genetic data never leaves this machine — all processing is local"*，
而本部署的 prompt 会常规性地写出队列名、测序 run 下的文件路径、
差异表达的输出。照抄就等于把这些发给第三方服务。

于是多出一个参考实现没有的字段
`ObservabilityConfig.capture_content`（`OMICSCLAW_OTEL_CAPTURE_CONTENT`），
**默认关**，四个 `langfuse.*` 属性全部受它管辖。关着的时候仍然记录：
span 树、turn 结构、模型名、token 用量、时长、工具名、结局、全部 metric；
丢掉的只有 payload。也就是说仪表盘需要的东西一样不少，而不会有任何
指向某个人或某个基因的字符串离开进程。

字段用 `OMICSCLAW_` 前缀而不是 `OTEL_`，因为没有任何 OpenTelemetry 规范
定义它，装成有规范会把人引到错误的文档里去。

两处相关的收紧，都由测试钉住：

- **工具异常只记类名，不记 message。** `hooks/audit.py` 是被一个测试教会
  这条的（一次 `read_file` 失败把请求路径写进了审计文件）；span 会**离开
  这台机器**，所以这里只会更严不会更松。
- **provider 异常的 message 同样受开关管辖**（返工后，见 §11.1）。原先的
  论证是"provider 的错误由厂商 SDK 对一次 HTTP 交换抛出，描述后端而不是
  payload"——这对 `429 rate limited` 成立，对内容策略拒绝（回显被拒文本）
  和参数校验错误（回显字段值）不成立。一个带例外、且例外取决于厂商恰好
  返回哪种错误的承诺，不是承诺。现在始终记录 `error.type` 与
  `error.status_code`，message 只在开关打开时记录；`llm.model` 本来就在
  span 上，所以"某个模型上的 404"依然是可诊断的。

## 5. 决策：turn span **惰性创建**，且阻塞路径必须**自报**

两条都直接来自 §2 的"没有 `TURN_START`"。

### 5.1 惰性：否则每次 run 末尾都会多导出一个幻影 span

kernel 在 `TURN_END(N)` 之后的**那一次** `__anext__` 里才开始做第 N+1 轮，
所以"开 N+1 轮 span"唯一诚实的时刻就是第 N 轮刚结束那一瞬——而那一刻
没人知道 run 还会不会继续。`TurnScope` 因此只持有**开一个 span 的意图**，
到第一次有人要 parent（也就是模型调用）时才真正创建。run 结束的话，被丢掉
的只是一个意图，零导出。

代价写明：turn span 从**模型调用**开始计时，所以排在它前面的 compaction
和 plan 注入落在 turn 之外（仍在 interaction 之内）。

### 5.2 `turn_events`：阻塞路径拿两层，而且必须说出来

`AgentEngine.run` 驱动的是**同一个内核**，内核产出的也是同一批事件——
是 `run` 自己**把它们丢掉了**。所以"为什么拿不到轮次边界"这个问题的
诚实答案分两半，而且只有前一半是被迫的（这段在对等性审核指出归因不准
之后重写，见 §11.2）：

- **第 1 轮确实推断不出来。** 它的模型调用在任何事件可能到达之前就要
  parent 了，等着弄清楚的 scope 早就已经 parent 完了。
- **第 2..N 轮不是推断不出来。** 第 N 轮的 `TURN_END` 在第 N+1 轮开始的
  那一刻就存在于内核里，是被 `run` 自己**既有的**契约丢弃的，跟本层无关。

于是：**阻塞路径两层是 `run` 契约的代价，不是事件模型的极限**——一个像
参考实现 `EngineObserver` 那样挂在内核里的观察者，两条路径都能拿到三层。
这个取舍是刻意做的（不往 leaf 层切 seam，胜过在一条没有任何 Surface 走的
路径上多拿一层），写在这里而不是留在 commit message 里，是为了让重新打开
它成为一个决定而不是一次发现。

所以有 `RunScope.turn_events`，`run_turn` 传 `False`，所有流式调用方保持
默认。**这个标志是为了防错而不是招错**：

- 说了 `False` 却收到 turn 事件 → 从下一个边界起开始分组，自我纠正；
- 说了 `True` 却一个都没收到 → 退出时告警并点名它无法切分的那次 run。

告警存在的理由就是这个标志存在的理由：不加它的话，一次五轮的 run 会变成
**一个标着 `agent.turn=1` 的 span 静静地装下全部五次模型调用**——那不是
少一层，那是一个错误的数字。§8 记录它是怎么被抓到的。

## 6. 决策：链尾挂 tracing，链首挂 audit；`AuditOutcome` 复用不重写

`build_hooks` 现在决定的是两个相反的端点，两个理由并不冲突：

| hook | 位置 | 为什么 |
|---|---|---|
| `AuditHook` | **链首** | 链逆序收尾，最先挂的最后被告知——包括被后面某个 hook 拒掉的调用。挂尾就会静默漏掉全部 refusal，而 refusal 正是审计存在的意义。 |
| `TracingHook` | **链尾** | 最内层，span 量的是工具本身而不是邻居；且它后面没有邻居，不会被别人的 refusal 留下未闭合。 |

这也正是参考实现的链序（`cmd/harness9/main.go:411-416`：413 行建表把
permHook 放最前，414-416 把 obsHook 追加到最后），只是它挂尾的理由是第三个
（上游 ctx 变更要对它可见）。

**`tool.status` 有四个值而参考实现只有两个。** `observability/hook.go` 只看
`result.IsError`，于是被权限规则拒掉的调用和工具自己崩掉的调用落进同一个桶，
被取消的轮次还会把失败率推高到没人能修。本部署已经在**一个地方**回答过这个
问题（审计日志），所以本层**复用** `AuditOutcome`，并把
`hooks/audit.py` 的私有 `_outcome_of` 提升为公开的 `outcome_of`——
这是本步唯一一处接线之外的既有文件改动，它**减少**而不是增加重复。

## 7. 交付物

新包 `omicsclaw/observability/`，11 个模块：

| 模块 | 对应 harness9 | 作用 |
|---|---|---|
| `attributes.py` | `attributes.go` | span 名 / 属性键 / 6 个仪器的声明表 |
| `config.py` | `config.go` | 5 个环境变量 + `capture_content` |
| `contract.py` | （无，OTEL API 本身） | `Span`/`Tracer`/`Meter` Protocol + noop |
| `serialize.py` | `helpers.go` | UTF-8 安全截断、消息/输出序列化 |
| `console.py` | `stdouttrace`/`stdoutmetric` | 纯标准库后端 |
| `otel.py` | `setup.go` | OTLP 适配器，唯一 import 厂商 SDK 的模块 |
| `telemetry.py` | `setup.go` 的 `Providers` | 门面 + `build_telemetry` |
| `scope.py` | `observer.go` + `engine/observer.go` | interaction / turn span，消费 `EngineEvent` |
| `provider.py` | `provider.go` | `TracedProvider` |
| `hook.py` | `hook.go` | `TracingHook` |
| `__init__.py` | — | 公开面与四条决策 |

接线（`entry/`，共三处）：

- `assembly.py`：`AgentApp.telemetry` 字段（**永不为 None**）、
  `build_app(..., telemetry=)`、provider 包装、`build_hooks(config, telemetry)`、
  `aclose()` 末位关闭；
- `turn.py`：三条 exchange 路径各开一个 scope，阻塞那条传 `turn_events=False`；
- `pyproject.toml` 新增 `otel` extra，`.env.example` 新增第 6 节。

产出的 trace 树：

```
omicsclaw.interaction          session.id  agent.turns  agent.stop_reason
├── omicsclaw.turn             agent.turn=1
│   ├── omicsclaw.llm_request  gen_ai.*  llm.tokens.*
│   ├── omicsclaw.tool         tool.name  tool.status
│   └── omicsclaw.tool         （兄弟重叠 = 这一轮是并行的）
└── omicsclaw.turn             agent.turn=2
    └── omicsclaw.llm_request
```

## 8. 实现期被自己的测试抓出的三个缺陷

**其一：后端中途失效会杀掉模型调用。** `current_parent()` 在
`TracedProvider._start` 里被调用，而惰性 `TurnScope.span()` 里
`tracer.start_span` 抛出的异常会从那里逃逸——遥测把一次 exchange 弄死了。
修法是两处都降级而不是抛：`TurnScope` 记一个 failed 标志并回落到 parent
（trace 少一层，其余照旧，且不会每次模型调用都刷一条日志），
`_start` 整体包住并回落到 `NOOP_SPAN`。

**其二（最严重）：阻塞路径把整轮 run 塞进 `agent.turn=1`。**
`tests/observability/test_end_to_end.py` 里那条"阻塞路径应该是两层"的断言
失败了，失败的是**代码不是测试**：`__aenter__` 无条件开了第 1 轮的
`TurnScope`，而阻塞路径永远等不到 `TURN_END` 去推进它，于是两次模型调用
和一次工具调用全部挂在同一个标着第 1 轮的 span 下面。这不是"缺一层"，是
**错的数字**。修法见 §5.2，并补了三条测试：忘传标志会告警、传错方向会
自我纠正、单轮 run 不告警。

**其三：`ObservabilityConfig(exporter="stdout")` 会静默失活。**
`ExporterType` 是 `StrEnum`，所以 `== "stdout"` 为真而全包使用的
`is ExporterType.STDOUT` 为假——一个手写的 config 会构造出一个什么都不记录
的部署，而且一声不吭。修法是 `__post_init__` 归一化（顺带把
`otlp_headers` 冻成只读，因为这条记录里装着凭据）。

另有一条不算缺陷但值得记的：**Go 与 Python SDK 的方法名不同**。
`setup.go` 用 `tp.Tracer(name)`，Python 是 `provider.get_tracer(name)`；
照着参考实现写的那一行被 `test_otel.py` 当场抓住。这正是"file:line 引用是
一种主张"那条规矩的另一面——**API 形状也是一种主张**。

## 9. 与 harness9 的核心特性逐项对照

| harness9 特性 | 本层 | 备注 |
|---|---|---|
| `ConfigFromEnv` 5 变量 | ✅ | 另加 `capture_content` |
| header `key=val,…` 首个 `=` 分割 | ✅ | 凭据里就带 `=` |
| noop / stdout / otlp 三种 exporter | ✅ | stdout 改为纯标准库实现 |
| noop 零开销默认 | ✅ | 单例 `NOOP_SPAN`，identity 可测 |
| exporter 构建失败 fail-open | ✅ | 两边**本来就一致**（`main.go:127-131` 降级为 noop）；本表原先把它记成我方的加分项，是一条未核对的论断，已在 §11.2 更正 |
| **全局 OTEL error handler**（运行期导出失败可见） | ✅（返工后补上） | `setup.go:57-63` 注册 `otel.SetErrorHandler`；Python 没有这个钩子，SDK 走 `logging`，于是译为确保 `opentelemetry` logger 有人接。**本表原先完全漏了这一条**，见 §11.2 |
| metrics 失败不拖累 traces | ✅ | Langfuse 的 `/v1/metrics` 会 404 |
| endpoint 显式拼 `/v1/traces` | ✅ | 测试钉住"只拼一次" |
| batch 2s / metric 30s | ✅ | 同值 |
| tracer 取自 SDK provider 而非全局 | ✅ | 同时仍设置全局 provider |
| interaction → turn → llm/tool 三层 | ✅ | turn 层惰性；阻塞路径两层且自报 |
| interaction 结束 ForceFlush | ✅ | 移到工作线程；正常退出**与普通失败**都 flush，只对取消 / `GeneratorExit` 跳过（返工后，见 §11.2） |
| `Shutdown` | ✅ | `AgentApp.aclose()` 末位调用 |
| 6 个仪器 | ✅ | 名称表化，缺单位/描述会测试失败 |
| GenAI 语义约定属性 | ✅ | |
| Langfuse v4 input/output 属性 | ✅ | **受 `capture_content` 管辖** |
| `truncateAttr` 4096 字节 + UTF-8 安全 | ✅ | Python 侧是代理字符而非非法字节 |
| `serializeMessages` / `serializeOutput` | ✅ | 不含 `reasoning_content` |
| 工具 span + 两个仪器 | ✅ | status 四值而非两值 |
| LLM span 阻塞 + 流式两条路径 | ✅ | 流式 span 在首个 chunk 打开 |
| `EngineObserver` seam | ❌ **刻意不做** | §2：改为消费 `EngineEvent` |
| 总是捕获 payload | ❌ **刻意不做** | §4：安全契约 |
| ~~`Setup` 失败即致命~~ | — | **这条不存在。** 经核实 harness9 在可观测性链路上从头到尾都是 fail-open 的；原先把它列为刻意偏离，是对参考实现的误读，见 §11.2 |
| 本层独有 | | `agent.stop_reason`、`llm.tokens.cache_read`、四值 `tool.status`、重试的多次 `llm_request` 挂同一 turn、6 个仪器全部带单位（Go 的 4 个 Counter 都没设）、`error.type` / `error.status_code` 结构化错误属性 |

## 10. 验证

```
tests/observability/                  257 passed
tests/entry/test_telemetry_wiring.py   17 passed
tests/hooks/                          120 passed
下层 schema provider engine context skills permission planning
                                     1809 passed / 5 skipped
```

`test_otel.py` 的 17 项在未安装 SDK 时整体 skip——这正是本层其余部分
在什么都没装的情况下仍可测试这一性质的体现。

与本次改动无关的既有失败（已逐条隔离确认）：`tests/tools/test_workspace.py`
（引用已被删除的 `omicsclaw/services/path_validation.py`）、
`tests/tools/test_websafety.py` 的顺序敏感用例（`docs/FRAMEWORK-REBUILD.md`
早有记录）、`tests/entry/test_desktop_http.py` 的 6 项（把本次改动 stash
掉之后同样失败）。

## 11. 两轮独立只读审核的发现与返工

两个 agent，一个查正确性、一个查对参考实现的对等性，互相不知道对方在看
什么。**它们的发现没有重叠**——这本身有信息量：每一个都找到了另一个的
任务书看不见的那类缺陷。

### 11.1 正确性审核：一类 span 泄漏，和一条没人钉住的不变量

**其一：span 创建成功之后再装饰，装饰失败就泄漏。** `RunScope.__aenter__`
和 `TracingHook.before_execute` 都是先 `start_span(...)` 再单独
`set_attributes(...)` 写 `langfuse.*` 输入属性，两句包在同一个
`try/except Exception` 里。若第二句抛出，处理器直接丢掉引用，那个已经创建
的 span 再也没人 `.end()`——**这条 trace 永久消失，而且没有任何日志解释
为什么**。`TracedProvider._start` 因为把属性一次性交给构造参数，本来就没有
这个洞；修法是让另外两处也这么做：一步到位，要么全成要么全不成。
审核员诚实标注这条是静态推断——三个内置后端的 `set_attributes` 都不会抛，
所以现有测试矩阵覆盖不到。修掉的是**缺陷类**而不是一个可复现的失败。

**其二：`__aexit__` 的 flush 位置论证得很起劲，却没有任何测试钉住它。**
审核员做了变异：把 `await self._flush()` 挪进上面的 `try/except` 里，
260 项测试全绿；再把 `except Exception` 改成 `except BaseException`，
同样全绿。也就是说，**这个仓库自己最担心的那类回归（`hooks/chain.py`
当年吞掉真实 `task.cancel()`）如果发生在这个位置，测试套件不会拦住。**
现补 `test_a_cancellation_during_a_flush_is_not_swallowed` 等四条，把 flush
策略的四个方向全部钉死。

**其三：`_CALL` 是覆盖语义，而隔壁 `_CURRENT` 是栈语义。** 这个不对称是
潜在缺陷而不是风格差异：`before_execute` 的 docstring 自己设想了一个工具
跑自己的子 agent，一旦这样的工具在**同一个 Task 内**再调一次工具，内层
退出时的 `_CALL.set(None)` 会把外层状态整个抹掉——外层 span 永不 `.end()`，
parent 绑定永不释放，该 Task 后续所有 span 都挂在一个已关闭的 tool span 上。
现在 `_Call` 带上 `call_token`，`_close` 用 `reset` 恢复**外层**而不是置空；
新测试已确认能杀死改回覆盖语义这个变异。

**其四（安全）：`capture_content=False` 时没有一条测试断言确实没有 payload。**
变异把默认改成开启只有一条测试失败，而且那条测的是默认值等于空环境，不是
关着的时候 span 里没有 payload。现补四条**遍历全部属性 / 全部 metric 标签**
去找 payload 字串的回归测试——刻意不按已知键名断言，因为按键名断言的测试
会在有人加第三个键的那天继续通过。

**其五：阻塞路径的接线只有字符串匹配。** `scope.py` 和 `turn.py` 各自都有
覆盖，但**两者的接缝**没有。现补一条真正调用 `entry.turn.run_turn`、用真
`Telemetry` 读产出树的端到端测试；它和原先那条字符串断言都能杀死拿掉
`turn_events=False` 这个变异，两条都留着，因为它们失败的原因不同。

### 11.2 对等性审核：一条事实性误读、一条未声明的缺失、一处引用错位

**其一（最该记住）：本文档原先声称 harness9 的 `Setup` 失败即致命，这是错的。**
`cmd/harness9/main.go:127-131` 只是 `log.Print` 一句然后换成
`observability.NewNoopProviders()`；`NewTracingProvider`、
`NewObservabilityHook`、`NewOTELEngineObserver` 失败时也全部走打日志、跳过
的降级路径。harness9 在可观测性这条链路上**从头到尾都是 fail-open 的**。
我把两边本来就一致的行为写成了我方更宽容的加分项——**一条没核对过的论断，
即使结论（我方 fail-open 是对的）没错，论据本身就是缺陷**。`otel.py` 的
docstring 和 §9 表格都已更正。

**其二：缺了全局 OTEL error handler，而且这一条在对照表里压根没出现。**
`setup.go:57-63` 注册 `otel.SetErrorHandler` 专捕**运行期**导出失败并显式
写 stderr，绕过 TUI 把日志指向 `io.Discard` 造成的静默。我只在**构造期**
做了 try/except——provider 一旦建成，之后每一批的导出失败就只剩 SDK 自己的
logger。用户会看到的现象是：跑了很久之后 Langfuse 上突然不再有新 trace，
本地却一句错都没有。Python 没有对应的钩子（SDK 走 `logging`），所以译法是
确保 `opentelemetry` logger 有人接：只在它和 root 都没有 handler 时挂一个
stderr handler，不动 `propagate`，已配置过日志的部署保持自己的配置。
`_surface_export_failures` 另加三条测试。

**其三：`contract.py` 引 `observer.go:76-81, 103-107` 错位约 17 行且指向了
错误的函数。** 76-81 是 `OnInteractionEnd` 的尾部，跟重新宣告 parent 无关；
真正双写在 `67-68`，turn 侧恢复在 `101-102`。被它支撑的论断（Go 需要双写
防御、Python 显式传参不需要）经通读全文件核实成立，但**坐标不对就是缺陷**。
连同 `provider.py` 里的 `entry/assembly.py:711`（被我自己这次改动挤到了
722，是改动自己制造的引用腐烂的典型）、`config.py` 的 `setup.go:88-90`
（实为 85-86）、以及 §4 里两条落在无关代码上的引用，共 5 条已全部重新核对
更正。

**其四：`ForceFlush` 在异常路径被跳过，而 Go 在 `defer` 里无条件 flush。**
我原先的理由（取消中的 task 不能 await）只对取消成立，对 `ProviderError`
不成立——而失败那次 exchange 的 trace，恰恰是人最想立刻看到的那一条。现在
正常退出与普通 `Exception` 都 flush，只对非 `Exception` 的 `BaseException`
（取消、`GeneratorExit`）跳过。

**其五：阻塞路径退化的归因不准。** 原文只归因于没有 `TURN_START`，但更深
的原因是 `run()` 把内核**确实产生了的** `TURN_END` 丢掉了。§5.2 已重写，
把被迫的那一半和被既有契约丢弃的那一半分开说。

### 11.3 两条记录在案、本轮**不修**的观察

- **`TurnScope` 的 `_failed` 标志是每轮一个而不是整个 run 一个**，所以一个
  持续宕机的后端会在每一轮的首次模型调用各记一条日志。docstring 原先写的是
  不会为 rest of the run 每次模型调用都刷，措辞过宽，已改成每轮一条这个
  真实的、更小的承诺。行为本身不改：跨轮各记一条是合理的噪音水平。
- **第三方 OTEL 自动插桩不会嵌进这些 span**（`contract.py` 早已写明的代价）。
  补这个缺口只需在 `otel.py` 里同时把 span 写进 OTEL 的 context，不动契约；
  留给需要它的那一天。
