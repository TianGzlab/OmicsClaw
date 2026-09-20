# 0035 —— ProgressiveCompactor：分层渐进式压缩接入 ReAct 主循环

状态：已实现（2026-09-19）；独立评估发现的高危缺陷已修复，结论与修复见 §9。

对标：harness9 `internal/memory/progressive_compactor.go`、`compaction_offloader.go`、
`record_store.go`、`anchor.go`，`internal/engine/history.go`、`loop_phases.go`、
`compact.go`，以及 `docs/核心功能/progressive-compactor.md`。

## 1. 起点：已有什么，缺什么

第 5 步（plan 0030）交付了压缩的**纯变换一半**：`omicsclaw/context/` 的五档
`Pressure`、head/tail 切分、SOFT 摘要一半、FULL 摘要全部、EMERGENCY 不调 LLM 且
保任务锚点、五类锚点的解析/合并/增量模板、摘要失败回退、`CompactionRecord` 值对象。
第 6 步（plan 0031）在 `entry/turn.py` 里**每个 exchange 开始前**压一次。

与 harness9 的核心特性相比，缺口是：

| # | harness9 特性 | 现状 |
|---|---|---|
| G1 | 每次 LLM 调用前压缩（`prepareTurnInput`） | 只在 `run()` 之间压；50 轮长跑中途撑爆窗口接不住（plan 0030 §11.B-1） |
| G2 | 写回式压缩 + 三条门控（issue #117） | exchange 级别隐式写回，**摘要失败的降级截断也被写回**，门控缺失 |
| G3 | 压缩期 tool_result offload（WARN 档的全部内容） | 不做；WARN 档什么都不动 |
| G4 | 压缩消息的 `## Offloaded References` | 不做 |
| G5 | `CompactionRecord` 的 ID/SessionID/Timestamp/Offloaded + JSONL `RecordStore` | 只有值对象，无持久化 |
| G6 | 压缩前 LTM 提取（`MemoryExtractor`） | `omicsclaw/memory/MemoryExtractor` 已有，无接缝 |
| G7 | 手动 `/compact`（ForceCompactor） | channel 命令被移除，"no honest implementation here yet" |
| G8 | 每轮 token 估算上报（`EventTokenUpdate`）与压缩事件 | 每个 exchange 只报一次 |
| G9 | 级联 GC | 无 |

## 2. 分层与依赖（高内聚、低耦合）

```
schema ← engine            （只多一个可选 Protocol：HistoryCompactor）
schema ← context           （压缩语义的全部：档位、offload 策略、锚点、写回门控、ProgressiveCompactor）
schema ← context ← memory  （I/O 实现：FileOffloadStore、JsonlCompactionLog）
entry  → 以上全部           （组装：把 context 的 ProgressiveCompactor 接到 engine 的接缝上）
```

- **engine 不认识压缩。** 接缝定义在使用者侧（engine），实现在外部（context），与
  `ConcurrencyAwareExecutor` / `DeadlineAwareExecutor` 同构，也与 harness9
  `WithCompactor` + `PromptBuilder` 的纪律一致。返回值是 `(messages, keep)` 普通
  元组，所以 context 满足它**不需要 import engine**。
- **context 不做 I/O。** offload 的"哪些该落盘、占位符长什么样、引用怎么携带"是策略，
  在 context；"字节写到哪里"是 `OffloadStore` Protocol，由 memory 实现。记录持久化同理，
  context 只经 `on_compact` 回调交出 `CompactionRecord`。
- **memory 只多两个 I/O 类**，依赖方向不变（schema + context）。
- **entry 只做组装与事件桥接**：`entry/compaction.py` 一个函数把 budget、summarizer、
  offload 目录、记录日志、事件回调接起来。

## 3. 关键决定

### 3.1 轮内压缩（G1）

`AgentEngine.run(messages, *, compactor=None)` / `run_stream(...)`。每轮在读取工具列表
之后、调用模型之前：

```python
rewrite = await compactor.compact(tuple(history), tools)
if rewrite is not None:
    view, keep = rewrite
    if keep: history = list(view)      # 写回
# 本轮发送 view；模型回复追加到 history
```

compactor 是**每次 run 一个实例**，不挂在 engine 上：engine 被多个会话共享，增量状态
（上一份摘要与锚点）是会话的。空的 rewrite 被忽略（harness9 `len(compacted)==0`）。
compactor 抛出的异常照常上抛——engine 的约定是"一切都 raise"。

`entry` 的 exchange 前压缩随之删除：第一轮的压缩就是它，只剩一个压缩点。

### 3.2 写回门控（G2）

`should_write_back(record)`，照 `history.go:117-133`：

1. `degraded` 非空且不是 EMERGENCY → 不写回（瞬时摘要失败，下一轮重试真摘要）；
2. EMERGENCY → 写回（真性溢出，不写回会每轮重新 Emergency）；
3. 没有实际削减（消息数、token 都没少，也没有 offload）→ 不写回。

结果记在 `CompactionRecord.written_back`，事件、日志、渲染都直接读它。

**与 harness9 的一处有意差异**：harness9 在写回点立即持久化到 Session（哪怕这次 Run
随后失败）。本项目的 exchange 是原子的（plan 0031 陷阱 3：失败/取消的 exchange 不改
history），写回结果随 exchange 成功才落库。代价：失败的 exchange 里做过的压缩，下次要
重做一次摘要。

### 3.3 offload（G3/G4）

- **在 context 决策，在 memory 落盘。** `Offloader(store, min_tokens=1000,
  preview_lines=10, preview_chars=800)`。候选：`Role.TOOL`、尚未 offload、估算超过
  `min_tokens`。1000 token 是 harness9 4000 字节按本层 4 字符/token 的换算。
- **先 offload，再重新定档。** offload 不调 LLM、不丢信息，是最便宜的一步；它覆盖
  WARN 及以上所有档（含 EMERGENCY），之后按 offload 后的对话重新定档。offload 已经
  够用时就不再摘要。harness9 定档一次、档内再 offload；这里是它的渐进思想推到底。
  记录里 `trigger` 是到达时测得的档位，`pressure` 是实际执行的档位，降档另写进
  `advisories`。
- **键 = tool_call_id + 内容 SHA-256 前缀**，不是只用 tool_call_id：本仓库有 preset
  （ollama）会给不同调用发同一个或空的 id，harness9 的"按 ID 缓存"会把第二份结果指到
  第一份文件上。内容哈希让幂等键跟着内容走，空 id 也能落盘。
- **预览按行且按字符封顶。** harness9 只按行截预览，一行 100KB 的压缩 JSON 预览就是
  全文，offload 等于没做。
- **引用确定性携带。** 新的压缩消息列出被摘要掉的 head 里所有 offload 引用：本次 offload
  的、之前写回留下的占位符、以及上一份压缩消息里的引用段——最多 50 条。harness9 只列本次
  的，老引用只能指望摘要模型记得。
- 占位符出现时，首次模板追加 harness9 的那条规则（`[offloaded: ...] entries ...`）；
  没有 offload 时模板逐字不变。
- **EMERGENCY 也先 offload，且 offload 范围扩到尾部。** 低于 EMERGENCY 时尾部从不
  offload（模型可能还没读过）；到了 EMERGENCY，截断会整条丢弃消息，尾部的大结果留成
  占位符（全文在磁盘上）好过被 `[tool result unavailable]` 顶替。
- **EMERGENCY 截断的目标是 `usable × full_at`，不是整个 `usable`。** 贪心装填会贴着
  上限停下（实测 0.98），高于 0.95 的触发线，于是之后每一轮都再次 EMERGENCY、永远不再
  摘要——issue #117 的截断死循环。截到 FULL 线，下一次压缩就是摘要（harness9 截到窗口
  的 80%，同一道理）。
- 执行期 OffloadHook（10000 字符）不在本步：它是工具层的事，本仓库工具已有各自的截断。
- **不排除 `read_file`。** plan 0030 §11.A-4 记的排除表属于**执行期** hook（读一个
  被 offload 的文件又被 offload，死循环）。压缩期 offload 只动 head 里模型已读过的结果，
  不存在这个环。

### 3.4 记录与持久化（G5/G9）

`CompactionRecord` 新增 `offloaded`、`written_back`、`forced`。ID/SessionID/Timestamp
是持久化信封的字段，由 `memory.JsonlCompactionLog.append(session_id, record)` 加上，
不进值对象。路径：`<workspace>/.omicsclaw/compaction_records/<session>.jsonl`；offload
文件：`<workspace>/.omicsclaw/tool_results/<session>/<key>.txt`（必须在 workspace 内，
否则 `read_file` 读不回来）。目录 0700、文件 0600。两个类都有 `purge`（级联 GC 的原语；
本仓库还没有"删除会话"的入口，接线留给它）。持久化失败只记 warning（fail-open）。

### 3.5 LTM 提取（G6）

context 定义 `MemoryExtractor` Protocol（`async extract(messages)`），SOFT/FULL 在摘要前
把**offload 之前的原文**交给它；与摘要并发执行；异常吞掉并写进 `advisories`。
`memory.MemoryExtractor` 结构化满足它。`AgentApp.memory_extractor` 默认 `None`——开数据库
是 memory 接线步骤的决定，本步只把接缝接通到组装层。

### 3.6 手动 `/compact`（G7）

`ProgressiveCompactor.force()`：不看阈值，按 FULL 处理（offload + 摘要整个 head），失败
照常回退。与 harness9 不同：harness9 的 `/compact` 对 Recorded 压缩器走分档（低于 60% 时
什么都不做），对非 Recorded 走 Emergency 截断；用户键入 `/compact` 期待的是"现在摘要"。
写回同样过 `should_write_back`：摘要失败时**不**把截断结果写进会话。

`SessionRegistry.compact(session_id)` 把它作为一个"只压缩"的 exchange 放进会话的车道，
与普通消息串行——这正是 channel 命令当初被移除的理由（"forcing one from outside would
race the exchange that owns the history"）。`/compact` 已注册进 channel 命令表
（`dispatch()`）。**但目前没有在线入口会调用 `dispatch()`**：Telegram 只注册了五个原生
命令，Feishu 把文本全部交给模型，CLI REPL 有自己的命令表。把斜杠命令路由进
`dispatch()` 是这些 surface 的接线工作，不在本步。

### 3.7 事件（G8）

每轮 `on_measure(report)` → `TurnEvent.context`；每次改动了对话或失败的压缩
`on_compact(record)` → `TurnEvent.compacted`。engine 事件枚举不变：观察压缩的是提供
compactor 的一方。

**CONTEXT 报的是触发压缩的那次测量**，先于 COMPACTION 发出——这是 plan 0031 钉住的
顺序（`test_compaction_is_announced_before_the_engine_sees_anything`）。实际发出的量在
COMPACTION 帧的 `tokens_after` 里；harness9 是反过来，先报压缩、再报压缩后的估算。

只有"改动了对话或失败了"的压缩才广播、才写 JSONL：一次什么都没做的 WARN 扫描在 IM
channel 里就是一条多余的消息。harness9 对所有非 None 档都记录。日志与 UI 回调彼此隔离，
回调抛错不影响落盘。

### 3.8 `compact_at` 默认值改为 WARN

原默认 FULL 来自 plan 0031 对草稿 `Pressure.HIGH` 的纠错，不是有意关闭低档；在 FULL 之下，
WARN 的 offload 与 SOFT 的半摘要永远不会发生，"渐进"名存实亡。harness9 没有这个门。

## 4. 触及的既有文件（每一处都有理由）

| 文件 | 改动 |
|---|---|
| `omicsclaw/engine/loop.py` / `__init__.py` / `types.py` | `compactor=` 参数、每轮调用、导出 Protocol、`RunResult.messages` 语义说明 |
| `omicsclaw/context/budget.py` | `PRESSURE_ORDER` / `at_least` 从 entry 下沉（ProgressiveCompactor 要用） |
| `omicsclaw/context/compaction.py` / `summary.py` / `__init__.py` | offload 预处理、提取接缝、`floor`、记录新字段、引用段 |
| `omicsclaw/memory/__init__.py` | 导出两个新类 |
| `omicsclaw/entry/turn.py` / `session.py` / `assembly.py` / `config.py` / `events.py` / `render.py` | 轮内压缩、只压缩 exchange、`memory_extractor` 字段、默认档位、渲染 |
| `omicsclaw/entry/channel/commands/builtins.py` | 恢复 `/compact` |
| `tests/entry/test_entry_is_the_top_layer.py` | `omicsclaw.memory` 从"被替换的包"移到 `_SUPERSEDED`：旧图谱记忆已删，这个名字现在属于重建的第 7 步 |
| `tests/entry/test_config.py` | 默认档位断言 |
| `.gitignore` | `.omicsclaw/` |

## 5. 不做

- 执行期 OffloadHook、nudge/gate 家族（plan 0030 §11.B-12，另一步）。
- engine 事件枚举不加压缩/token 事件（§3.7）。
- 打开 LTM 数据库、把精华段挂进 prompt（memory 接线步骤）。
- CLI REPL 与 Telegram/Feishu 的 `/compact` 入口（§3.6）。
- `AgentApp.memory_extractor` 没有任何地方赋值：接缝已通，打开 LTM 数据库是 memory 接线
  步骤的事。`purge` 没有调用方：本仓库还没有"删除会话"的入口。
- 摘要失败时，同一次压缩里已成功的 offload 也随之不写回（写回门控是全有或全无；接缝只
  能返回一个序列）。持续的摘要故障因此更快走到 EMERGENCY。
- `run_turn`/`prepare` 不给 `session_id` 时，文件落在 `default/` 与 `default.jsonl`；
  `prepare()` 作为预览也会写文件。

## 6. 验收

1. 一次 run 内第 N 轮撑到 FULL，第 N 轮发给模型的对话已被压缩（轮内，不是 run 之间）。
2. 写回门控三条各一条测试，含"摘要失败不写回、下一轮重试"。
3. WARN 档 offload：文件落盘、占位符可解析、`read_file` 路径在 workspace 内、同一内容幂等。
4. offload 后降档则不调摘要模型。
5. 引用跨两次压缩仍在压缩消息里。
6. 记录落 JSONL 并能读回；持久化失败不影响压缩。
7. 提取器在摘要前看到 offload 之前的原文；提取器抛错不影响压缩。
8. `/compact` 在车道内串行，摘要失败不改会话历史。
9. 分层：engine 不 import context；context 不 import memory/engine；memory 不 import entry。

## 7. 与 harness9 的差异一览

| 点 | harness9 | 本实现 | 理由 |
|---|---|---|---|
| 定档次数 | 一次 | offload 后重新定档 | 最便宜的手段先用 |
| offload 覆盖档位 | Warn/Soft/Full | Warn 及以上全部 | 同上；Emergency 保留预览优于整条跳过 |
| offload 键 | ToolCallID | ToolCallID + 内容哈希 | 重复/空 id |
| 预览 | 10 行 | 10 行且 ≤800 字符 | 单行巨型输出 |
| 引用携带 | 本次 | 本次 + 历史，≤50 | 摘要不可靠 |
| 写回持久化时机 | 立即 | exchange 成功时 | exchange 原子性 |
| Emergency 截断目标 | 窗口 80% | `usable × full_at` | 同一目的：下一轮能摘要 |
| Emergency 前 offload | 无（靠执行期 OffloadHook） | offload 含尾部 | 大结果留全文而非丢弃 |
| CONTEXT/token 上报 | 压缩后的估算 | 触发压缩的测量；压缩后量在 COMPACTION 帧 | plan 0031 已定顺序 |
| `/compact` | 分档或 Emergency | FULL 摘要，失败不写回 | 用户意图 |
| 增量状态 | 压缩器可变字段 | 每 run 一个压缩器实例，状态随会话存取 | 会话并发 |
| 阈值分母 | 整个窗口 | `usable_tokens` | plan 0030 已定 |

## 8. 结果

见 §9 与 `docs/FRAMEWORK-REBUILD.md`。

## 9. 独立评估

一个只读子 agent 对照 harness9 设计文档与源码逐项审计 F1–F19，并跑了同场景的 Go 探针。
结论：四档、轮内压缩、offload、锚点、增量摘要、记录与 JSONL、写回门控、摘要失败回退结构上
全部落地，多处优于 harness9（内容哈希 key、引用携带、预览截断、每 run 一个实例）；分层方向
经 `sys.modules` 行为探针确认成立。但它找到一个让"渐进"失效的高危缺陷，已修复：

| # | 严重度 | 发现 | 处置 |
|---|---|---|---|
| D1 | 高 | EMERGENCY 贪心装填到 0.98 × usable，高于 0.95 触发线，此后每轮 EMERGENCY、永不摘要（实测连续 12 轮；harness9 同场景截到 0.80 后下一轮 FULL 摘要） | 截断目标改为 `usable × full_at`；测试 `test_after_an_emergency_truncation_the_next_compaction_summarizes`、`test_an_emergency_truncation_leaves_room_to_summarize_next` |
| D2 | 中 | `/compact` 在所有在线入口不可达，"channel 命令恢复"的说法失实 | 更正本计划、FRAMEWORK-REBUILD 与 README（§3.6）；接线留给 surface |
| D3 | 中 | CONTEXT 报压缩前的量 | 保留：plan 0031 钉住的顺序；已写明（§3.7） |
| D4 | 中 | EMERGENCY 下尾部大结果不 offload，被不可恢复地丢弃 | EMERGENCY 时 offload 扩到尾部；测试 `test_an_emergency_offloads_a_large_recent_result_instead_of_dropping_it` |
| D5 | 低 | 落盘挂在 UI 回调之后；"失败的压缩也入日志"无测试 | 回调单独 try；测试 `test_a_failed_compaction_is_logged_and_a_broken_listener_does_not_stop_it` |
| D6/D7 | 低 | 默认会话目录共用；摘要失败连带丢弃 offload | 记入 §5 |
| D8 | 低 | `offload_key("-x", …)` 生成的 key 被存储层拒绝 | key 去掉前导 `-`；测试 `test_every_key_the_context_layer_derives_is_accepted` |
| D9 | 低 | 日志测试只断言 `<=` | 已由 D5 的精确断言补上 |

修复由实现者完成，偏离了"第三个 agent 修复"的惯例（plan 0034 附录 A 有同样的记录）。
五个针对修复的变异各杀死一个具名测试；此前十个针对门控的变异同样全部被杀死。
重建栈测试在冻结副本上 2,996 passed（另一 session 同时在对 `entry/` 做变异测试，
直接在工作树上跑会命中它的临时变异）。
