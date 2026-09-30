# ProgressiveCompactor 分层渐进式上下文压缩

## 1. 概述

`ProgressiveCompactor`（`omicsclaw/context/progressive.py`）是 OmicsClaw 在一次运行（run）内部管理上下文膨胀的机制。它在**每一次模型调用之前**被引擎咨询：测量对话占用了多少可用空间，按占用比例落到五个压力档位之一（NONE / WARN / SOFT / FULL / EMERGENCY），然后执行强度递增的动作——把大工具结果移到文件、摘要一半的旧消息、摘要全部旧消息、不调模型直接截断——并决定压缩结果是否**写回**运行中的历史。

对多组学 agent 来说这不是锦上添花：一次 `bash` 运行 `sc-preprocessing` 或 `spatial-de` 的脚本可能打印几千行基因表或 QC 统计，几轮之后对话就被工具输出占满。压缩的目标是在不丢掉"用户要做什么、做到哪了、`h5ad` 在哪"的前提下把这些输出挪出去。

压缩本身是一个纯函数 `compact()`（`omicsclaw/context/compaction.py`），`ProgressiveCompactor` 负责跨调用携带状态和写回判定；落盘（offload 文件、压缩日志）在 `omicsclaw/memory/`，接线在 `omicsclaw/entry/compaction.py`。

### 1.1 设计目标

| 目标 | 机制 |
|------|------|
| **渐进触发** | 五档，阈值 0.60 / 0.70 / 0.80 / 0.95，分母是 `ContextBudget.usable_tokens` |
| **最便宜的手段先用** | 每个高于 NONE 的档位都先 offload，再**重新定档**；offload 够用就不调摘要模型 |
| **信息不丢** | 大工具结果写入工作区内的文件，上下文留带预览的占位符；引用列表在历次压缩间确定性携带（最多 50 条） |
| **关键信息保底** | 五类锚点（User Intent / Execution Progress / Key Decisions / Tried Solutions / Next Steps），增量合并时 `N/A` 不覆盖旧值 |
| **失败可降级** | 摘要器缺失、抛错、超时、返回不可解析内容，都回退到按预算裁剪，原因写入 `record.degraded`；摘要不会从 `compact()` 抛出 |
| **不陷入截断循环** | EMERGENCY 截断到 `usable × full_at`，下一次压缩能走摘要 |
| **全链路记录** | 每次压缩一个 `CompactionRecord`；改动了对话或失败的压缩写入 JSONL 并发出 `COMPACTION` 事件 |
| **并发安全** | 每次 run 一个压缩器实例；增量状态随会话持久化，不挂在共享的 engine 上 |

### 1.2 核心架构

```
engine/loop.py  _kernel  每个 Turn：
    rewrite = await compactor.compact(history, tools)        ← HistoryCompactor 协议
                     │
┌────────────────────▼──────────────── ProgressiveCompactor.compact ───────────────┐
│ report = measure(history, tools, budget)   → on_measure(report)  [CONTEXT 事件]   │
│ if not at_least(report.pressure, trigger): return None     （trigger = compact_at）│
│ result, record, state = await compact(history, report.budget, floor=NONE, ...)    │
│ record.written_back = should_write_back(record)；写回时才更新 self._state          │
│ if 改动了对话或失败: await on_compact(record)  [COMPACTION 事件 + JSONL]           │
│ return result, record.written_back                                               │
└────────────────────┬─────────────────────────────────────────────────────────────┘
                     │  context/compaction.py  compact()
     trigger = max(测得档位, floor)
     ├─ trigger > NONE 且有 offloader → offload head 中的大工具结果
     ├─ plan_compaction(offload 后的对话)  → 重新定档
     │     ├─ EMERGENCY 且有 offloader → 连尾部一起 offload，再定档一次
     │
     ├─ NONE / WARN ── 原样（仅含 offload 占位符）
     ├─ SOFT ──────── 摘要 head 较旧的一半 ┐  summarizer ‖ extractor 并发
     ├─ FULL ──────── 摘要整个 head       ┘  失败 → fit_to_budget 降一档目标
     └─ EMERGENCY ─── 不调模型：任务消息 + 从新到旧贪心装入，目标 usable × full_at
     结果仍 > usable → 回退裁剪（非 EMERGENCY）；仍超 → 记录 "still over"
```

---

## 2. 分层压缩机制

### 2.1 档位与阈值

```python
class Pressure(StrEnum):
    NONE = "none"; WARN = "warn"; SOFT = "soft"; FULL = "full"; EMERGENCY = "emergency"
```

`ContextBudget.pressure(used)` 以 `ratio = used / usable_tokens` 判档，边界归上一档：

| 档位 | 条件（默认） | 动作 |
|------|------|------|
| `NONE` | ratio < `warn_at` 0.60 | 什么都不做，逐字节原样 |
| `WARN` | ≥ 0.60 | 只 offload；没有 offloader 时什么都不改，只是信号 |
| `SOFT` | ≥ `soft_at` 0.70 | 摘要 head 较旧的一半，另一半原文保留 |
| `FULL` | ≥ `full_at` 0.80 | 摘要整个 head，保留 `min_tail` 条尾部 |
| `EMERGENCY` | ≥ `emergency_at` 0.95 | 贪心截断，**从不**调用摘要器 |

`usable_tokens = context_tokens − reserve_output_tokens − reserve_tool_tokens − context_tokens × safety_ratio`（推导见 [context-engineering.md](context-engineering.md) §6）。`usable_tokens <= 0` 时比值为无穷大，直接 EMERGENCY。四个阈值是经验值，未在本仓库负载上标定。

比较档位必须用 `at_least()` / `PRESSURE_ORDER`：`Pressure` 是 `StrEnum`，`>=` 按字母序比较。

### 2.2 触发门：`compact_at`

`ProgressiveCompactor(trigger=...)` 是开始压缩的最低档位，entry 层取 `AppConfig.compact_at`（`--compact-at` / `OMICSCLAW_COMPACT_AT`，默认 `warn`）。测得档位低于它时 `compact()` 返回 `None`，引擎原样发送。设成 `full` 会让 WARN 的 offload 与 SOFT 的半摘要永远不发生——这正是默认值从 `full` 改成 `warn` 的原因（plan 0035 §3.8）。

### 2.3 头、尾与 pin

```
[ pinned | ─────────── head ─────────── | ── tail (min_tail) ── ]
  system    可被 offload / 摘要 / 丢弃       最近 DEFAULT_MIN_TAIL = 6 条，原样保留
```

`split_head_tail(messages, pinned=, min_tail=)` 切分；pin 之后不超过 `min_tail` 条时 head 为空，SOFT/FULL 无事可做（`advisories` 会写明）。entry 层传 `pinned=PINNED_SYSTEM_MESSAGES`（1，即 system 消息），`compact()` 本身默认 `pinned=0`、不假设下标 0 是 system——`pinned=0` 且下标 0 恰好是 system 时，`advisories` 里会留一句提醒。

### 2.4 各档数据流

以下 "offload" 都指有 offloader 时；entry 层总是配了一个。

**先 offload，再定档**

```
trigger = max(budget.pressure(tokens_before), floor)
if trigger > NONE:
    offload head 区间 [pinned, pinned + len(head)) 中超过 min_tokens 的 Role.TOOL 消息
plan = plan_compaction(working, ...)     # 以 offload 后的 token 数重新定档
if plan.pressure != trigger:
    advisories += "offloading lowered the pressure from <trigger> to <pressure>"
```

`record.trigger` 是到达时测得的档位（含 floor），`record.pressure` 是实际执行的档位。

**WARN（或 offload 后降到 NONE/WARN）**

```
返回 [pinned, *head(含占位符), *tail]
不修复工具对（纯透传，避免重建一个本来就合法的对话而使缓存前缀失效）
record: offloaded=[...], summarized=0
```

**SOFT**

```
oldest = head[: len(head)//2]
tail'  = head[len(head)//2 :] + tail
summarizer(oldest) ‖ extractor(oldest 的 offload 前原文)
返回 [pinned, (所欠的工具结果), compaction_msg, *tail']  → repair_tool_pairs
```

**FULL**

```
summarizer(head) ‖ extractor(head 的 offload 前原文)
返回 [pinned, (所欠的工具结果), compaction_msg, *tail]  → repair_tool_pairs
```

"所欠的工具结果"：如果 pin 区的最后一个 assistant 轮请求了工具、而答复在 tail 开头，这些答复会排在摘要消息**之前**，否则 `repair_tool_pairs` 只能删掉它们再补占位符（`_answers_owed_by`）。

**EMERGENCY**

```
（有 offloader 时）offload 范围扩大到 [pinned, len)，包括尾部，然后再定档一次
survivors = 任务消息（pin 之后第一条，无条件） + 其余从新到旧、放得下就留、放不下就跳过
目标 = int(usable_tokens × full_at)
返回 repair_tool_pairs([pinned, *survivors])
record.degraded = "emergency fallback: forced truncation"
```

两个细节都来自独立评估发现的缺陷：
- **目标是 `usable × full_at` 而不是整个 `usable`**。贪心装填会贴着上限停在约 0.98，高于 0.95 的触发线，于是之后每一轮都再次 EMERGENCY、永远不再摘要。截到 FULL 线，下一次压缩就是摘要。
- **EMERGENCY 连尾部一起 offload**。低于 EMERGENCY 时尾部从不 offload（模型可能还没读过）；到了 EMERGENCY，截断会整条丢弃消息，一个大的近期结果变成占位符（全文在磁盘上）好过被丢掉。

任务消息无条件保留：丢了它的紧急视图会让模型失去目标空转。

---

## 3. Tool-Call Offload

### 3.1 组件

| 组件 | 代码位置 | 职责 |
|------|---------|------|
| `Offloader` | `omicsclaw/context/offload.py` | 规则：`store`、`min_tokens=1000`、`preview_lines=10`、`preview_chars=800` |
| `OffloadStore` Protocol | `omicsclaw/context/offload.py` | `async put(key, content) -> reference`；异常表示存不下，消息原样保留 |
| `offload_messages()` | `omicsclaw/context/offload.py` | 扫描、写入、替换为占位符；返回 `OffloadOutcome(messages, entries, failures)` |
| `OffloadEntry` | `omicsclaw/context/offload.py` | `reference`、`lines`、`chars`、`tool_call_id`、`tool_name` |
| `FileOffloadStore` | `omicsclaw/memory/offload.py` | 写 `<root>/<safe_name(session)>/<key>.txt` |
| `offload_store(config, session_id)` | `omicsclaw/entry/compaction.py` | root = `<workspace>/.omicsclaw/tool_results`，引用相对工作区 |

**候选条件**：`role == Role.TOOL`、内容不是已有占位符（不以 `[offloaded: ` 开头）、估算 token 数 > `min_tokens`。`read_file` 的结果不排除：压缩期 offload 只处理模型已经读过的 head，不存在"读 offload 文件又被 offload"的环。

### 3.2 键与幂等

```python
offload_key(tool_call_id, content) = f"{stem}-{sha256(content)[:16]}"   # stem 为空时只用摘要
```

`stem` 是 `tool_call_id` 中非 `[A-Za-z0-9_.-]` 字符替换为 `_`、去掉首尾 `._-`、截到 64 字符。键里带内容摘要，是因为某些 preset 会给不同调用发相同或空的 id——只用 id 做键会把第二份结果指到第一份文件上。

`FileOffloadStore.put` 校验键格式（非法抛 `ValueError`）；进程内 `_written` 集合 + 写前 `path.exists()` 保证同一键只写一次；写入走临时文件 + `os.replace`，目录 `0700`、文件 `0600`。引用在 `reference_base`（工作区）之下时返回相对路径，模型可以直接交给 `read_file`。

### 3.3 占位符

```
[offloaded: .omicsclaw/tool_results/<session>/call_7-603931239af5b26c.txt | 5000 lines / 182340 chars]
Preview (first 10 of 5000 lines):
AAACAAGTATCTCCCA-1  ...
...
... full output saved to .omicsclaw/tool_results/<session>/call_7-603931239af5b26c.txt; read it with read_file
```

预览按行（`preview_lines`）**且**按字符（`preview_chars`）封顶，被字符截断时标 `clipped`——只按行截的话，一行 100KB 的压缩 JSON 预览就是全文。`parse_placeholder()` 能从首行恢复 `OffloadEntry`。

### 3.4 引用的确定性携带

每条新的压缩消息末尾带一个 `## Offloaded References` 段，由 `collect_references(plan.head)` 收集：被摘要掉的 head 里所有占位符，加上 head 中上一条压缩消息的引用段，按引用去重、保留最新的 `MAX_REFERENCES = 50` 条。这样即使摘要模型忘了提某个 `h5ad` 报告的路径，文件位置仍在上下文里。

### 3.5 失败

`put` 抛出的异常被捕获，该消息保持原样，失败描述进入 `record.advisories`（不是 `degraded`）；其他消息照常处理。只有 `asyncio.CancelledError` 会穿出。

---

## 4. 锚点与摘要（`context/summary.py`）

### 4.1 五类锚点

```python
@dataclass(frozen=True, slots=True)
class Anchors:
    user_intent: str = "N/A"
    execution_progress: str = "N/A"
    key_decisions: str = "N/A"
    tried_solutions: str = "N/A"
    next_steps: str = "N/A"
```

固定集合、固定顺序（解析、合并、渲染都遍历同一个 `_ANCHOR_HEADERS` 元组）。摘要是自由文本、会漂移；"用户要什么"和"已经试过什么"必须在每一轮压缩后都出现在可辨认的位置。

### 4.2 提示词

摘要器的 system 指令是 `SUMMARY_SYSTEM_PROMPT`（"You are a context compaction engine…"）。首次压缩用 `FIRST_TEMPLATE`：

```
Produce a structured compaction of the following conversation in this exact format:

## Anchors

### User Intent
<one concise sentence>

### Execution Progress
- <key milestone>

### Key Decisions
- <decision: rationale>

### Tried Solutions
- <approach: outcome>

### Next Steps
- <pending task>

## Summary
<supplementary context not captured in anchors>

Rules:
- Each anchor section MUST be present (use "- N/A" if nothing applies)
- Be concise: each item one line

Conversation:
{conversation}
```

当被摘要的对话里出现 offload 占位符时，规则区追加 `OFFLOAD_RULE`（"- [offloaded: ...] entries indicate large outputs saved to files; keep the paths that still matter"）；否则模板逐字不变。

之后的压缩（`state.summary` 非空）用 `INCREMENTAL_TEMPLATE`，把上一份锚点 + 摘要放进 `<previous-compaction>`，要求模型合并；此时 head 里上一条压缩消息不再重复渲染进对话文本。模板保持英文：解析器匹配的就是 `### User Intent` 这些英文标题。

对话文本由 `render_for_summary()` 生成（`[tool_result <id>]: …` / `[<role>]: …` / `[tool_call <name>(<id>)]: <arguments>`），不截断任何一行——体积靠整条丢弃消息控制，不靠渲染器决定工具结果哪部分重要。

### 4.3 解析与合并

`parse_anchors_and_summary(text) -> (Anchors, summary)`：单遍扫描，`### <标题>` 打开已知锚点、未知标题关闭当前锚点，`## Summary` 之后是正文，遇到 `## Offloaded References` 停止。**永不抛出、总返回五个锚点**，缺失的填 `N/A`。因此"解析成功"不等于"摘要成功"：`compact()` 把"既无锚点也无正文"视为摘要失败并降级——这是去掉旧层六道内容闸之后剩下的唯一结构性信号。

`Anchors.merge(newer)`：新值为 `""` 或 `N/A` 时保留旧值，否则新值覆盖。方向很关键：新一轮没提到的锚点是新摘要的空缺，不是对旧信息的撤回。`""` 与 `N/A` 同等对待，是因为锚点经 SQLite 的 JSON 往返后缺失字段会变成 `""`。

### 4.4 跨调用、跨 exchange 的增量状态

```python
@dataclass(frozen=True, slots=True)
class CompactionState:
    summary: str = ""
    anchors: Anchors = Anchors()
```

`compact()` 接收上一份状态、返回下一份；`ProgressiveCompactor` 只在结果**写回**时才采纳新状态（失败的摘要不污染状态）。exchange 结束后 `TurnOutcome.state` 回到 `Session.compaction`，由 `SqliteSessionStore` 存进 `sessions.summary` / `sessions.anchors` 列，下一个 exchange 的 `build_compactor(app, state=session.compaction)` 再带回来。丢失状态的代价：下一次压缩从 `FIRST_TEMPLATE` 重新开始。

只保留**一份**上一次压缩：`COMPACTION_MARKER = "[Context Compaction]"` 只是前缀、没有闭合标记，压缩消息不能安全嵌套。

### 4.5 压缩消息格式

`build_compaction_message(anchors, summary, references)` 产出一条 **user 角色**消息（它是交给模型的上下文，不是模型说过的话）：

```
[Context Compaction]
## Anchors

### User Intent
对 Visium 数据做空间域识别

### Execution Progress
- spatial-preprocess 完成，输出 output/pre/processed.h5ad

### Key Decisions
N/A

### Tried Solutions
N/A

### Next Steps
- run spatial-domains

## Summary
processed h5ad at output/pre/processed.h5ad

## Offloaded References
- .omicsclaw/tool_results/<session>/c0-b219e997d4db02bc.txt (2001 lines, 10000 chars) - output of bash
- .omicsclaw/tool_results/<session>/c1-b219e997d4db02bc.txt (2001 lines, 10000 chars) - output of bash
```

这里没有 `## Active Tasks` 段：执行计划由 `omicsclaw/planning/` 的 `PlanInjector`（`TurnAugmentor`）在压缩**之后**追加到每次发送的副本上，压缩碰不到它。

---

## 5. 错误处理与回退

### 5.1 `degraded` 与 `advisories`

| 字段 | 含义 | 例子 |
|------|------|------|
| `degraded` | 失败原因，`"; "` 连接；**非空 = 走了非预期路径** | 摘要器抛错、返回空、结果超预算、EMERGENCY |
| `advisories` | 关于"怎么被调用"的事实，从不是失败 | `pinned=0` 却以 system 开头、head 为空、offload 降了档、某次 offload 或提取器失败 |

两者曾共用一个字段，结果写回门控把"忘了传 `pinned=1`"当成失败、拒绝写回运行良好的压缩，每轮都重新摘要一次——所以拆开了。注意 EMERGENCY 总会写 `degraded`（截断本身就是降级结果），消费方必须像写回门控那样把 EMERGENCY 单独处理。

### 5.2 分层降级

| 环节 | 失败行为 | 记录 |
|------|---------|------|
| offload 写文件 | 该消息保留原文，继续 | `advisories` |
| 记忆提取器 | 异常被捕获，不影响压缩 | `advisories` |
| 摘要器为 `None` | `fit_to_budget` 回退 | `degraded: no summarizer was supplied` |
| 摘要器抛异常 | 同上 | `degraded: the summarizer raised ...` |
| 摘要超时 | `_ProviderSummarizer` 返回 `""` → 视为空结果回退 | `degraded: the summarizer returned neither anchors nor a summary` |
| 摘要后仍超 `usable` | 丢弃摘要，回退裁剪 | `degraded: the compacted conversation came out at N tokens ...` |
| 回退后仍超 `usable` | 原样返回 | `degraded` 追加 `the compacted conversation is still over usable_tokens` |
| 压缩监听器 / JSONL 写入 | 记日志，不影响压缩与对方 | 日志 |

只有 `asyncio.CancelledError` 会从 `compact()` 穿出。`compact()` 自身不给摘要器设超时；超时由 `_ProviderSummarizer` 在内部实现（`summary_timeout_s`，默认 90 s）——若把 `asyncio.timeout` 包在 `compact()` 外面，超时会以异常形式抛出，这一轮就完全没有压缩。

### 5.3 回退目标比触发线更严

```python
_FALLBACK_TARGETS = {Pressure.SOFT: "warn_at", Pressure.FULL: "soft_at"}
target = int(budget.usable_tokens * getattr(budget, field))
fit_to_budget(working, budget, pinned=, min_tail=, target_tokens=target)
```

降一档的阈值作为裁剪目标。如果回退目标就是 `usable_tokens`，那么 SOFT/FULL 下对话按定义都低于 0.95 × usable，`fit_to_budget` 第一行就会原样返回——"降级"实际什么都没删。`fit_to_budget` 从 head 最旧处逐条剥离，然后 `repair_tool_pairs`。

---

## 6. 写回与引擎接缝

### 6.1 `HistoryCompactor` 协议（`engine/compactor.py`）

```python
class HistoryCompactor(Protocol):
    async def compact(
        self, history: tuple[Message, ...], tools: tuple[ToolDefinition, ...]
    ) -> tuple[Sequence[Message], bool] | None: ...
```

引擎在每个 Turn 读取工具列表之后、调用模型之前调用它：

```python
sent = tuple(history)
if compactor is not None:
    rewrite = await compactor.compact(sent, tools)
    if rewrite is not None and rewrite[0]:      # 空序列被忽略
        sent = tuple(rewrite[0])
        if rewrite[1]:
            history = list(sent)                # 写回：后续 Turn 与返回的轨迹都基于它
if augmentor is not None:
    sent = (*sent, *await augmentor.augment(sent, tools))   # 计划块只进本次发送
```

引擎不知道预算或记录是什么；`ProgressiveCompactor.compact` 结构化满足这个协议，`context` 与 `engine` 互不 import。压缩器抛出的异常照常从 run 中抛出。

### 6.2 写回门控：`should_write_back(record)`

```python
def should_write_back(record):
    if record.degraded and record.pressure is not Pressure.EMERGENCY:
        return False                  # 摘要失败：截断结果只服务这一次调用，下一次重试真摘要
    return (record.msgs_after < record.msgs_before
            or record.tokens_after < record.tokens_before
            or bool(record.offloaded))  # 没有实际削减就不写回
```

- **EMERGENCY 写回**：完整历史已经发不出去，不写回会每轮重新 EMERGENCY；
- **SOFT/FULL 的降级不写回**：同一次压缩里已成功的 offload 也随之不写回（门控全有或全无），持续的摘要故障因此会更快走到 EMERGENCY；
- 结果记在 `record.written_back`，事件、日志、渲染都读它。

### 6.3 每次 run 一个实例

`build_compactor()` 为每个 exchange 新建一个 `ProgressiveCompactor`（`_assemble()` 里），不挂在 engine 上：engine 由所有会话共享，而增量状态属于会话。实例在 exchange 内跨多次模型调用累积 `records`、更新 `state`；exchange 结束时 `TurnOutcome` 带出 `state`、`compaction`（最后一条记录）、`compactions`（全部）。

### 6.4 持久化时机

写回只改变运行中的 history；**落库在 exchange 成功结束时**（`SessionRegistry._attempt` 在 `converged` 时用 `outcome.history` 与 `outcome.state` 替换会话并 `save`）。exchange 是原子的：失败或取消的 exchange 不改会话历史，代价是其中做过的压缩下一次要重做。

---

## 7. 可观测性

### 7.1 `CompactionRecord`

```python
@dataclass(frozen=True, slots=True)
class CompactionRecord:
    pressure: Pressure          # 实际执行的档位（offload 后重新测得，并提升到 floor）
    tokens_before: int
    tokens_after: int
    msgs_before: int
    msgs_after: int
    summarized: int             # 被摘要替代的消息数；降级路径为 0
    preserved_tail: int         # pin 之后按身份原样保留的原始消息数
    anchors: Anchors = ...
    summary_text: str = ""
    degraded: str = ""
    advisories: tuple[str, ...] = ()
    duration_s: float = 0.0     # time.monotonic()，几乎全是摘要器的 await
    trigger: Pressure = NONE    # 到达时测得的档位
    offloaded: tuple[OffloadEntry, ...] = ()
    forced: bool = False        # floor 不是 NONE（/compact）
    written_back: bool = False  # 由 ProgressiveCompactor 填
    compression_ratio (property) = tokens_after / tokens_before
```

值对象不含 ID、会话、时间戳——那是持久化信封的字段。

### 7.2 JSONL 压缩日志

`JsonlCompactionLog`（`memory/compaction_log.py`）：`<workspace>/.omicsclaw/compaction_records/<safe_name(session)>.jsonl`，追加写、从不重写，目录 `0700`、文件 `0600`，写入经 `asyncio.to_thread` 且有线程锁。每行是 `{"id": uuid4().hex, "session_id", "timestamp", ...asdict(record), "compression_ratio"}`（`ensure_ascii=False`）。`list(session_id)` 按写入顺序读回 `LoggedCompaction`，跳过读不回来的行；`record_from_dict` 忽略未知键、缺省可选键，新旧版本的日志都能加载。

**只有改动了对话或失败的压缩才记录与广播**（`_did_something`：`degraded`、有 offload、消息数或 token 数变化）。一次什么都没做的扫描不写日志——在 IM 频道里每条通知都是一条消息。`records` 属性仍保留全部。

`build_compactor` 包装的 `on_compact` 依次：调用 UI 监听器（异常记日志）→ 写 `INFO` 日志 `compacted at <tier>: a→b tokens, m→n messages, k offloaded (not kept)(degraded: ...)` → 追加 JSONL（`OSError` 记 warning）。监听器失败不会阻止落盘，反之亦然。

### 7.3 事件与展示

| 出口 | 内容 |
|------|------|
| `TurnEventType.CONTEXT` | 每次模型调用前的测量（触发压缩的那次，压缩前的量），先于 `COMPACTION` |
| `TurnEventType.COMPACTION` | 携带 `CompactionRecord` |
| CLI（`TextRenderer._compaction_line`） | `Compacted [full]: 18 -> 8 messages, 45210 -> 8102 tokens (82% smaller); 5 offloaded (50000 chars), 11 summarized, 6 kept verbatim`，未写回时加 `this call only`，降级时加 `(degraded: ...)` |
| 线格式（`_compaction_payload`） | `pressure`、`tokens_before/after`、`msgs_before/after`、`summarized`、`preserved_tail`、`degraded`、`trigger`、`offloaded`（条数）、`written_back`、`forced`；刻意不含摘要正文 |
| Desktop | `COMPACTION` 转为 `status` 帧，`kind="compaction"` |
| Channel | 默认不投递 `CONTEXT` / `COMPACTION`（`DEFAULT_DELIVERED_TYPES`） |

---

## 8. 长期记忆提取接缝

`context.MemoryExtractor` Protocol：`async extract(messages) -> object`。SOFT/FULL 摘要时，`compact()` 把**被摘要消息在 offload 之前的原文**交给它，与摘要器 `asyncio.gather` 并发；返回值被忽略，异常写入 `advisories`。EMERGENCY 与纯 offload 不触发提取。

`build_compactor` 优先用 `AgentApp.memory_extractor`；为 `None` 时每次调用都用 `build_memory_extractor(app.memory, app.summarizer)` 现场构造（`memory` 关闭或没有摘要器时为 `None`）。构造出的 `PrecisRefreshingExtractor` 包着 `memory.MemoryExtractor`，存入条目后重写 `.omicsclaw/MEMORY.md` 精华，从不抛出。提取的具体规则见长期记忆文档。

---

## 9. 手动 `/compact`

### 9.1 `ProgressiveCompactor.force()`

```python
async def force(history, tools=()) -> tuple[tuple[Message, ...], CompactionRecord]
```

不看触发门，以 `floor=Pressure.FULL` 调用 `compact()`：offload + 摘要整个 head；测得 EMERGENCY 时仍然截断；失败照常回退，且同样过 `should_write_back`——摘要失败时截断结果**不会**写进会话。理由是用户键入 `/compact` 期待的就是"现在摘要"。

### 9.2 在会话车道里执行

`SessionRegistry.compact(session_id)` 把它作为一个 `compaction_only` exchange 放进该会话的串行车道，不会与正在进行的 exchange 竞争同一段历史（排满时抛 `QueueFull`，关闭中抛 `RegistryClosed`）。`TurnRunner` 走 `_compact_only`：`compose(app, history, "")` → `compactor.force(messages, app.tools_snapshot)` → 写回时用压缩结果、否则保留原对话 → `TurnOutcome(history=kept[1:], state=compactor.state, compaction=record)`。这条路径不调用主模型、不注入计划块。

### 9.3 各入口

| 入口 | 代码 | 行为 |
|------|------|------|
| CLI REPL | `entry/cli/_repl.py:Repl._compact` | 本会话有 exchange 在跑时直接拒绝；结束后打印 `_compaction_verdict`：`Compacted: a -> b tokens (x% smaller), m -> n messages.` / `Nothing to compact: this conversation is already short.` / `Compaction failed and the conversation was left as it was: ...` |
| Channel | `entry/channel/commands/builtins.py` 的 `@register("/compact")` | 经 `dispatch()` 到达：Telegram 直接调用，Feishu/Slack/Discord/DingTalk/QQ/Email 经 `Channel.answer_slash_command`（仅 owner）；回复 `_describe_compaction` 的一句话 |

`/clear`（Channel）把会话的 `history` 与 `compaction` 一起清空。

---

## 10. 配置参数

| 参数 | 位置 | 默认 | 说明 |
|------|------|------|------|
| `compact_at` | `AppConfig` / `--compact-at` / `OMICSCLAW_COMPACT_AT` | `warn` | 触发门 |
| `summary_model` | `--summary-model` / `OMICSCLAW_SUMMARY_MODEL` | `""`（主模型） | 摘要与提取所用模型 |
| `summary_timeout_s` | `--summary-timeout` / `OMICSCLAW_SUMMARY_TIMEOUT_S` | `90.0` | 单次摘要超时，超时降级 |
| `memory` | `--memory` / `OMICSCLAW_MEMORY` | `true` | 关闭则无提取器、会话不持久化 |
| `warn_at` / `soft_at` / `full_at` / `emergency_at` | `ContextBudget` | 0.60 / 0.70 / 0.80 / 0.95 | 无配置入口 |
| `safety_ratio` | `ContextBudget` | 0.10 | 无配置入口 |
| `DEFAULT_MIN_TAIL` | `context/compaction.py` | 6 | 尾部保留条数 |
| `PINNED_SYSTEM_MESSAGES` | `entry/compaction.py` | 1 | pin 住的 system 消息 |
| `Offloader.min_tokens` / `preview_lines` / `preview_chars` | `context/offload.py` | 1000 / 10 / 800 | entry 层用默认值 |
| `MAX_REFERENCES` | `context/offload.py` | 50 | 引用段上限 |

---

## 11. 设计决策

| 决策 | 原因 |
|------|------|
| 压缩在每次模型调用前，而不只在 exchange 之间 | 一次 exchange 内的长工具链同样会撑爆窗口（plan 0030 §11.B-1 关闭） |
| `compact()` 是纯函数，状态由 `ProgressiveCompactor` 携带 | 压缩可以脱离 session 测试；状态随会话持久化，engine 可在会话间共享 |
| 先 offload、再定档 | offload 不花模型调用也不丢信息，够用就省下一次摘要 |
| offload 键含内容摘要 | 重复或空的 call id 不会让两个结果共用一个文件 |
| 预览行数 + 字符双上限 | 单行巨型输出 |
| 引用确定性携带（≤50） | 不依赖摘要模型记住文件路径 |
| 写回门控 | 失败的摘要只服务一次调用；EMERGENCY 必须写回；无削减不写回 |
| EMERGENCY 截到 `usable × full_at` | 打破截断死循环，下一次能摘要 |
| EMERGENCY 连尾部 offload | 大的近期结果留占位符而非被丢弃 |
| 回退目标降一档 | 否则降级是无操作 |
| 摘要超时在摘要器内部，返回 `""` | 超时降级而不是整轮无压缩 |
| 不设内容闸 | 替代品是可靠的降级路径与预算复测，`tests/context/test_summary_gates.py` 禁止重新发明闸门 |
| 只广播改动或失败的压缩 | IM 频道里每条通知都是一条消息 |
| `/compact` = FULL 摘要，走会话车道 | 符合用户意图；不与持有历史的 exchange 竞争 |

---

## 12. 已知限制

- **摘要质量无人把关**：没有内容闸，一次压缩可能丢掉 `h5ad` 路径而没有任何机制察觉；引用段只能保住 offload 过的文件路径（plan 0030 §11.A-9，"本层最值得早点还的一笔债"）。
- **从未与真实模型验证**：摘要模板能否让真实模型产出可解析的锚点，测试全部驱动假实现。
- **阈值与 token 估算未标定**（§11.A-7、§11.A-8）；估算错了没有第二次机会——没有 413 反应式重压（§11.A-14，已接受的风险）。
- **一次压缩后仍可能略超目标**：只做一遍，不迭代收敛（§11.A-13 已接受），下一轮再压。
- **摘要失败时 offload 一起作废**：写回门控全有或全无，持续的摘要故障更快走到 EMERGENCY（plan 0035 §5）。
- **失败 exchange 的压缩要重做**：持久化只在 exchange 成功时发生。
- **没有 session_id 时共用目录**：`run_turn` / `prepare` 不传 `session_id` 时，文件落在 `tool_results/default/` 与 `compaction_records/default.jsonl`；`prepare()` 作为预览也会写文件。
- **没有清理入口**：`FileOffloadStore.purge`、`JsonlCompactionLog.purge` 无调用方，offload 文件与日志只增不减；`JsonlCompactionLog.list` 也没有被任何 surface 读取。
- **没有执行期 offload**：超大工具输出在进入历史时不拦截，要等到下一次压缩（WARN 起）才被移出；各工具自带的输出截断是唯一的源头防线。
- **图片不计成本**：见 [context-engineering.md](context-engineering.md) §12。

---

## 13. 文件索引

| 文件 | 职责 |
|------|------|
| `omicsclaw/context/progressive.py` | `ProgressiveCompactor`、`should_write_back` |
| `omicsclaw/context/compaction.py` | `compact`、`plan_compaction`、`apply_compaction`、`build_summary_prompt`、`collect_references`、`CompactionPlan`、`CompactionRecord`、`CompactionState`、`MemoryExtractor`、`DEFAULT_MIN_TAIL` |
| `omicsclaw/context/summary.py` | `Anchors`、`parse_anchors_and_summary`、`build_compaction_message`、`COMPACTION_MARKER`、`FIRST_TEMPLATE`、`INCREMENTAL_TEMPLATE`、`OFFLOAD_RULE`、`SUMMARY_SYSTEM_PROMPT`、`Summarizer` |
| `omicsclaw/context/offload.py` | `Offloader`、`OffloadStore`、`offload_messages`、`offload_key`、占位符与引用段的渲染/解析 |
| `omicsclaw/context/transcript.py` | `repair_tool_pairs`、`split_head_tail`、`fit_to_budget`、`emergency_fit`、`render_for_summary` |
| `omicsclaw/context/budget.py` | `ContextBudget`、`Pressure`、`at_least`、`measure` |
| `omicsclaw/engine/compactor.py` | `HistoryCompactor` 协议 |
| `omicsclaw/engine/loop.py` | `_kernel` 中每 Turn 调用压缩器与写回 |
| `omicsclaw/entry/compaction.py` | `build_compactor`、`offload_store`、`compaction_log`、`PINNED_SYSTEM_MESSAGES` |
| `omicsclaw/entry/assembly.py` | `_ProviderSummarizer`、`build_summarizer` |
| `omicsclaw/entry/turn.py` | `_assemble`、`TurnRunner._compact_only`、`TurnOutcome` |
| `omicsclaw/entry/session.py` | `SessionRegistry.compact`、会话状态保存 |
| `omicsclaw/entry/memory.py` | `build_memory_extractor`、`PrecisRefreshingExtractor` |
| `omicsclaw/entry/events.py` / `render.py` | `CONTEXT` / `COMPACTION` 事件、文本行、线格式 |
| `omicsclaw/entry/cli/_repl.py` | CLI `/compact` 与 `_compaction_verdict` |
| `omicsclaw/entry/channel/commands/builtins.py` | Channel `/compact`、`/clear` |
| `omicsclaw/memory/offload.py` | `FileOffloadStore`、`safe_name` |
| `omicsclaw/memory/compaction_log.py` | `JsonlCompactionLog`、`LoggedCompaction`、`record_from_dict` |
| `tests/context/test_compaction.py`、`test_progressive.py`、`test_offload.py`、`test_anchors.py`、`test_summary.py`、`test_summary_gates.py` | 压缩单元测试 |
| `tests/entry/test_compaction_in_loop.py` | 轮内压缩、写回、`/compact`、事件 |
| `tests/memory/test_compaction_files.py` | offload 文件与 JSONL 日志 |
| `docs/plans/0035-progressive-compaction-in-loop.md` | 本机制的计划、独立评估 |
| `docs/plans/0030-context-assembly-layer.md` | 压缩函数的原始设计与 §11 债务 |
