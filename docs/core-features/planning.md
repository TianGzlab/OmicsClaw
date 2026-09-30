# Planning：执行计划

OmicsClaw 的 Planning 层解决一个具体问题：**一个长任务如何在自己的上下文压缩之后仍记得自己要做什么。**

step 6.6 之后，压缩在一次运行的**每次模型调用前**都可能发生（`ProgressiveCompactor`）。这正是长任务需要的，也正是会把"最初说好的分析步骤"总结掉的机制。执行计划就是这份记忆：它存放在对话**之外**，在每次模型调用前被原样放回发送视图的末尾，所以压缩无法把它总结掉，恢复的会话也不必从头开始。

多组学分析天然是多步、有依赖的：`spatial-preprocess` 产出的 `.h5ad` 是 `spatial-domains` 的输入，域标签又是 `spatial-de` 的分组依据。一次这样的任务可能跑几十个 turn、多次 `bash` 调用 skill 脚本，每次输出都可能很长——这是计划最有价值的场景。

> **规划是能力，不是模式。** 没有"进入规划模式"的开关，没有工具白名单，没有审批对话框。是否为一个任务写计划，由模型读 system prompt 中的规划准则自行判断；`AppConfig.planning` 只决定这项能力在部署中是否存在。

---

## 1. 核心设计决策

| 决策 | 选择 | 理由 |
|------|------|------|
| 规划触发 | System prompt 准则（`PLANNING_GUIDANCE`），模型自主判断；长期只读探索时由"规划闸门"提醒一次 | 简单任务强制规划是浪费；复杂任务漏规划由准则 + 闸门兜底 |
| 粒度 | 一个会话一个计划 | 与会话生命周期对齐，`/resume` 语义自然 |
| 多会话 | `PlanBook`：`session_id → PlanStore`，工具在调用时按会话解析 | 一个 `ToolRegistry` 服务所有会话（Channel / Desktop），工具共享、计划不能共享 |
| 写入模型 | 全量替换 + 按先前状态合并（`rules.merge`） | 模型总是输出它当前相信的整份计划；已开始的条目不因省略而丢失 |
| 防作弊 | `rules.validate`：一次最多 1 个条目直接跳到 `completed`；`cancelled → completed` 始终拒绝 | 阻止"一次把九条标完成"的伪造进度 |
| 持久化 | 写穿（write-through）到 `<workspace>/.omicsclaw/plans/` 下的文件 | 不给 `omicsclaw.memory` 加 `plan` 列；每次被接受的写入在工具返回前落盘 |
| 压缩免疫 | 引擎新接缝 `TurnAugmentor`：在 compactor **之后**、只追加到**发送副本** | 无论哪个压缩档位产出什么视图，计划都在；不写入历史、不累积 |
| 子代理 | 子代理不获得 `plan_write`，也没有计划注入 | 计划属于发起委派的会话；子代理只做一件被委派的事 |

---

## 2. 系统架构

```
omicsclaw/planning/        （叶子邻接层：只 import schema、tools 与标准库）
├── plan.py       PlanStatus / PlanItem / PlanStore / PlanWriteSink
├── rules.py      validate / merge / apply / PlanRefused / MAX_DIRECT_COMPLETIONS
├── tool.py       plan_write_tool / PLAN_WRITE_SCHEMA / SESSION_VALUE_KEY
├── guidance.py   PLANNING_GUIDANCE / PLANNING_SECTION_HEADING
├── injector.py   PlanInjector（满足 engine.TurnAugmentor）/ 规划闸门常量
├── render.py     format_plan（注入块）/ render_document（Markdown 文件）
├── archive.py    PlanArchive Protocol / FilePlanArchive / dump_items / load_items / safe_name
└── book.py       PlanBook / ArchiveErrorSink

omicsclaw/engine/
├── augmentor.py  TurnAugmentor Protocol
└── loop.py       _kernel：compactor → augmentor → 模型调用

omicsclaw/entry/
├── planning.py   build_plan_book（每部署一次）/ build_injector（每 exchange 一次）/ _report
├── assembly.py   foundation_tools(plans=) / default_sections(plan_tool=) / build_app / AgentApp.plans
├── turn.py       _assemble → augmentor=build_injector(app, session_id=...)
├── subagent.py   _WITHHELD_FROM_SUB_AGENTS = {plan_write: …, memory_write: …}
└── cli/_repl.py  /plan、/tasks、_show_plan
```

运行时对象关系：

```
                    build_app（每个部署一次）
                          │
       build_plan_book(config) ──► PlanBook(FilePlanArchive(plans_root), on_archive_error=_report)
            │                             │
            │ plan_write_tool(book)       │ for_session(session_id)
            ▼                             ▼
  ToolRegistry 中的 plan_write        PlanStore（每会话一个，懒创建，首次取用时从归档恢复）
   调用时读 context_value("session_id")   │  write() ──sink──► FilePlanArchive.save
            │                             │                   ├─ <session>.json（原子）
            │  rules.apply(prev, new)     │                   └─ <session>.md（人读）
            └────────── store.write ─────►│
                                          │ read()
  每个 exchange：build_injector(app, session_id) ──► PlanInjector(store, gate_turns)
                                          │
  engine._kernel 每个 turn：                ▼
      sent = compactor.compact(history)  ──►  extra = augmentor.augment(sent, tools)
      sent = (*sent, *extra)  ──► 模型调用     （[闸门提醒], [计划块]，均为 USER 消息）
```

依赖方向：`omicsclaw/planning/` 不 import `omicsclaw.engine`、`omicsclaw.context`、`omicsclaw.entry`。`PlanInjector` 结构化满足 `TurnAugmentor`；`tests/planning/test_planning_is_a_leaf_layer.py` 在子进程里跑真实代码路径后断言这三个包不在 `sys.modules` 中。

---

## 3. 数据模型（`omicsclaw/planning/plan.py`）

```python
class PlanStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"

@dataclass(frozen=True, slots=True)
class PlanItem:
    id: str                 # 模型自己分配；合并与防作弊都以它为键
    content: str            # 一个具体可执行动作；长度无上限
    status: PlanStatus = PlanStatus.PENDING

    @property
    def is_active(self) -> bool:   # pending 或 in_progress
```

意图中的状态转换：

```
pending ──► in_progress ──► completed
   │              │
   └──────────────┴──► cancelled
```

`PlanStore` 本身不校验转换——它原样存储收到的东西，校验在 `rules.validate`。

### 3.1 `PlanStore`

| 方法 | 语义 |
|------|------|
| `read() -> tuple[PlanItem, ...]` | 当前计划。返回内部 tuple 本身，不拷贝（tuple + frozen 条目已是不可变快照） |
| `write(items)` | 全量替换，然后在**锁外**调用 `on_write` sink；返回新内容 |
| `restore(items)` | 从存储播种，**不**调用 sink（恢复不应把刚读到的内容再写回去） |
| `active_count() -> (active, total)` | 未完成条目数与总数。**当前仓库中没有调用者** |
| `is_empty` | 从未写过或写成空；规划闸门读它 |

锁是 `threading.Lock` 而不是 `asyncio.Lock`：`read` 在每次模型调用前经 `PlanInjector` 被调用，做成 async 会在热路径上多一个 await 点；而工具可能跑在 `asyncio.to_thread` 上，`asyncio.Lock` 在那里不起作用。

`PlanWriteSink = Callable[[Sequence[PlanItem]], None]` 是写穿接缝。约定 **sink 不得抛异常**——抛了就会让触发它的那次工具调用失败。`PlanBook` 绑定的 sink 把 `PlanArchiveError` 交给 `on_archive_error`，由 entry 层记日志后继续。

---

## 4. `plan_write` 工具（`omicsclaw/planning/tool.py`）

模型改变计划的唯一途径。两种模式：

- **写模式**：提供非空 `steps` 数组 → 解码 → `rules.apply(store.read(), proposed)` → `store.write(merged)` → 返回完整计划 JSON；
- **读模式**：省略 `steps`，或 `steps=[]` → 返回当前计划 JSON，不修改。把 `[]` 当作"清空计划"会给模型一个用 schema 合法值抹掉全部条目的途径，所以它也是读。

```json
{
  "steps": [
    {"id": "qc",      "content": "Run spatial preprocessing and QC on the Visium sample", "status": "completed"},
    {"id": "domains", "content": "Identify spatial domains with leiden",                  "status": "in_progress"},
    {"id": "de",      "content": "Run differential expression between domains",           "status": "pending"},
    {"id": "report",  "content": "Write the analysis report",                              "status": "pending"}
  ]
}
```

返回值总是 JSON 数组（空计划是 `[]` 而不是 `null`），每项 `{id, content, status}`。

**会话解析**：`book.for_session(str(context_value(SESSION_VALUE_KEY, "") or ""))`，`SESSION_VALUE_KEY = "session_id"`。这个值由 `TurnRunner.turn_values` 写进每次工具调用的上下文，`run_turn` / `stream_turn` 两个库函数也会绑定。

**参数校验**（`_decode`）：每个条目必须是对象，`id` / `content` / `status` 三者齐全，`id` 去空白后非空，`status` 是四个枚举值之一。错误信息带条目下标（`input.steps[3].status is ...`），以 `ToolArgumentError` 形式成为 `is_error` Observation，模型据此自愈。

**`ToolPolicy`**：

| 字段 | 值 | 理由 |
|------|----|------|
| `risk_level` / `approval_mode` | `LOW` / `AUTO` | 爆炸半径是一个 JSON 文件；默认 `HIGH`/`ASK` 会让每次计划更新都弹审批，模型会因此停止规划 |
| `concurrency_safe` | `False` | 成为引擎调度的屏障：同一轮两个 `plan_write` 会基于同一先前状态合并，后者丢更新 |
| `writes_workspace` / `writes_config` | `True` / `True` | 绑定归档时会写 `<workspace>/.omicsclaw/plans/` 下两个文件 |
| `tags` | `{"planning"}` | |

---

## 5. 写入规则（`omicsclaw/planning/rules.py`）

两条规则守护相反的失败：`validate` 防止模型声称没做过的工作，`merge` 防止模型因省略而丢失做过的工作。`apply` 先校验后合并，是写路径唯一应调用的函数。

### 5.1 防作弊：`validate(previous, proposed)`

只检查**本次写入点名的**条目，每个 id 只计一次（重复 id 取第一次出现，与 `merge` 共用 `_first_by_id`）：

1. **`cancelled → completed` 始终拒绝**：已放弃的条目要先恢复为 `pending` / `in_progress`；
2. **直接完成计数**：新状态为 `completed` 且先前状态为"不存在"或 `pending` 的条目计为一次直接完成；超过 `MAX_DIRECT_COMPLETIONS = 1` 则拒绝整批。先前为 `in_progress` 的条目标完成不计数；已经 `completed` 的条目重发也不计数。

阈值取 1 而非 0：真在同一 turn 里完成了一件事并直接记下，是正常用法；一次声称完成多件没有经过 `in_progress` 的条目，才是描述工作而不是做工作。拒绝抛 `PlanRefused(ValueError)`，工具把它转成 `ToolArgumentError`，代价是一个 turn，不是整个运行。

规划准则里配有 prompt 层的另一半："Updating the status without doing any other work is not doing the item."——工具层在事后拒绝，这句话在事前劝阻。

### 5.2 部分更新合并：`merge(previous, proposed)`

按**先前状态**而不是按是否出现来决定：

| 条目情况 | 结果 |
|---------|------|
| 在 `proposed` 中出现 | 采用新版本（无论改成什么状态） |
| 未出现，先前为 `in_progress` 或 `completed` | 原样保留——已开始的工作是事实 |
| 未出现，先前为 `pending` 或 `cancelled` | 丢弃——裁剪从未开始的步骤是模型应能一次做到的编辑 |
| `proposed` 中的新 id | 追加到末尾，保持提交顺序 |

顺序按条目**首次写入**的顺序稳定：注入块每轮都被模型读，列表在两轮之间重排会被读成另一份计划。放弃一个条目的正规途径是显式标 `cancelled`，只有这样它才会被记录为"考虑过并放弃"。

---

## 6. 原生规划：System Prompt 准则

`default_sections` 在 `Tool guidance` 之后插入 `## Planning` 段（`PLANNING_SECTION_HEADING`），内容为 `PLANNING_GUIDANCE`：

```
For a task with several steps — a multi-stage analysis, work that has to be explored
before it can be done, anything where a later step depends on an earlier one — write
the plan with `plan_write` first, then work through it.

- Each item is one concrete action you can carry out: "deconvolve the Visium sample
  against the reference", "write the QC report". Not "clarify the requirements", ...
- Mark an item `in_progress` before you start it, and `completed` once it is actually
  done. Updating the status without doing any other work is not doing the item.
- When you update, send only the items still in play. ...
- The plan is the authoritative record of this task. It stays visible to you after the
  conversation is compacted and after a session is resumed, ...
- A one- or two-step task, a question, a single command: just do it. ...
```

几个约束：

- **只在工具真的挂载时出现**：`default_sections(..., plan_tool=True)` 且 `config.planning` 为真才加该段。`build_app` 检查实际挂载的工具里是否有 `plan_write`；调用方自带 `tools=` 而没挂它时，`plans` 置为 `None`，prompt 不提规划、也不注入计划块——prompt 指示调用一个不存在的工具，只会让模型浪费 turn。
- **示例不点名任何 skill**：初稿用了 `spatial-deconv`，在 `skills_index=off` 的部署中会把一个故意未公开的能力告诉模型，被 `tests/entry/test_turn.py::test_switching_the_catalogue_off_removes_it_from_the_turn` 抓出。示例改为描述**工作**（去卷积、写 QC 报告）。
- **英文**：本仓库 system prompt 全部是英文。

---

## 7. 压缩免疫：`TurnAugmentor` 注入

### 7.1 引擎接缝

`omicsclaw/engine/augmentor.py`：

```python
@runtime_checkable
class TurnAugmentor(Protocol):
    async def augment(
        self,
        history: tuple[Message, ...],
        tools: tuple[ToolDefinition, ...],
    ) -> Sequence[Message]: ...
```

`engine/loop.py: _kernel` 每个 turn：

```python
tools = tuple(self._tools.available_tools())
sent = tuple(history)
if compactor is not None:
    rewrite = await compactor.compact(sent, tools)
    ...                                  # 可能改写 sent，必要时写回 history
if augmentor is not None:
    extra = await augmentor.augment(sent, tools)
    if extra:
        sent = (*sent, *extra)           # 只进发送副本
# → generate_with_retry(... sent ...)
```

性质：

- **在压缩之后**：WARN 卸载、SOFT/FULL 摘要、EMERGENCY 截断，无论产出什么视图，计划块都追加在其后——截断回退这种最容易丢计划的场景也覆盖到；
- **只进发送副本**：不写入 `history`，不出现在 `RunResult.messages`，不持久化，不累积；每个 turn 从存储重新计算，所以 `plan_write` 的更新在**下一次模型调用**就可见；
- **单独的接缝，而不是扩宽 `HistoryCompactor`**：`entry/turn.py:_outcome` 读取 `ProgressiveCompactor` 的三个具体属性，包装 compactor 必须转发它们，忘了也不会报错，只会静默丢掉该次运行的压缩记录。两条窄接缝比一条宽接缝便宜。
- augmentor 抛出的异常会传出整个运行——循环无法区分"读不到计划"和"计划说停"。

### 7.2 `PlanInjector.augment`

按顺序最多追加两条 **USER** 角色消息：

1. **规划闸门提醒**（见 §8）——只在没有计划时可能出现；
2. **计划块**：`format_plan(store.read())`，为空则不追加。

用 USER 角色：assistant 角色的注入会让模型读到"自己没说过的话"，system 角色出现在对话中段会被若干后端直接拒绝。

计划块格式（`render.format_plan`，只含 `pending` / `in_progress`）：

```
## Current execution plan — authoritative. After a context compaction or a resumed session, continue from this list, not from what the conversation above appears to say.
[>] Identify spatial domains with leiden
[ ] Run differential expression between domains
[ ] Write the analysis report
```

`[ ]` 表示 pending，`[>]` 表示 in_progress。已完成条目不注入：重复告诉模型它已经能看到自己做完的事既费 token，又会稀释"还剩什么"这张清单。没有活跃条目时返回 `""`，调用方不追加任何消息（对话以空 user 消息结尾轻则浪费一次调用，重则 400）。

### 7.3 每 exchange 一个注入器

`entry/turn.py: _assemble` 为每个 exchange 构造协作者：

```python
augmentor=build_injector(app, session_id=session_id) if plan_block else None
```

- `build_injector` 返回 `PlanInjector(app.plans.for_session(session_id), gate_turns=app.config.planning_gate_turns)`；`app.plans is None` 时返回 `None`。
- `for_session` 同时是**恢复路径**：进程内首次取用该会话时从归档读回计划，发生在该 exchange 的第一次模型调用之前。
- `plan_block=False` 用于 compaction-only 路径（`/compact`）：那条路径不调模型，没有 turn 需要提醒，也就不去触发恢复。

---

## 8. 规划闸门（Planning Gate）

长时间只读探索、既不写计划也不改动任何东西的运行，会在某次模型调用前收到一次提醒：

```python
DEFAULT_GATE_TURNS = 8
PLANNING_GATE_TEXT = (
    "You have spent several turns reading without changing anything and without "
    "writing a plan. Stop and call `plan_write` once to record a short plan — "
    "locate, act, verify — then work through it, updating each item as you go."
)
PROGRESS_TOOL_NAMES = frozenset({"write_file", "edit_file"})
```

`_gate_fires(history)` 的条件（`history` 是压缩后的发送视图）：

1. 本 exchange 尚未提醒过，且 `gate_turns > 0`；
2. 计划为空（`store.is_empty`）——有计划的会话每轮都已被告知计划，再催它写计划既错又乱；这也覆盖了从上一个会话恢复的计划；
3. 从视图末尾往前数，**最近 `gate_turns` 条 assistant 消息**都没有调用 `plan_write` 或 `PROGRESS_TOOL_NAMES` 中的工具；
4. 视图中可见的 assistant 消息少于 `gate_turns` 条时不触发。

对组学分析的含义：**`bash` 不算进展**。它既是跑 skill 脚本的方式，也是 `grep` / `ls` 的方式，算作进展会让只在探索的模型永远不被提醒。因此一个连续 8 个 turn 只用 `bash` 查看 `.h5ad`、跑 `--help`、读 SKILL.md 而没有写计划的运行会被提醒一次。

阈值为 8，约占部署轮次预算（`EngineConfig.max_turns = 50`）的六分之一；它明显长于一个普通组学问答所需的几个 turn，不会教模型为单步任务写计划。

闸门看的是**窗口**，不是计数器：
- 压缩把尾部换掉后可见的 assistant 消息可能不足 8 条，此时不触发。接受这一点：刚压缩意味着模型刚拿到新摘要，那一轮不是追加指令的好时机；
- 20 个 turn 前编辑过文件、之后一直在读的模型，仍会被提醒；每 exchange 至多一次的约束防止它变成重复骚扰。

`planning_gate_turns = 0` 关闭闸门，计划块照常注入。

---

## 9. 持久化与恢复

### 9.1 `FilePlanArchive`（`omicsclaw/planning/archive.py`）

每个会话两个文件，位于 `AppConfig.plans_root()` = `<workspace>/.omicsclaw/plans/`：

```
<safe_name(session)>.json   机器副本 —— 唯一的恢复来源
<safe_name(session)>.md     人读副本 —— 从不读回
```

`save(session_id, items)`：

1. `mkdir(parents=True, exist_ok=True)`（目录按进程 umask 创建，在首次保存时而非构造时创建——从不写计划的部署不留痕迹）；
2. JSON 经 `tempfile.mkstemp`（同目录）+ `os.chmod(0o600)` + `os.replace` **原子**写入；`O_TRUNC` 会在写入前清空文件，失败时留下空计划，而空计划与"新会话"无法区分；
3. 然后写 Markdown 并 `chmod 0o600`。**顺序是承重的**：崩溃在两者之间只会让人读副本过时，而不会让状态不可恢复。
4. 任何 `OSError` 包装为 `PlanArchiveError`。

`load(session_id)`：文件不存在 → `()`（新会话的正常状态）；存在但不可读、非 JSON、非列表、条目缺字段或状态未知 → `PlanArchiveError`。**任何缺陷都拒绝整个文件**而不是跳过坏条目：防作弊规则依据先前状态判断，恢复出一份悄悄缺条目的计划，恰好会让一次完成声明逃过检查。

Markdown 文件形态（`render_document`）：

```markdown
# Execution plan

session: cli-visium-01
updated: 2026-09-23T08:15:02.113204+00:00

## Items

- [x] Run spatial preprocessing and QC on the Visium sample
- [>] Identify spatial domains with leiden
- [ ] Run differential expression between domains
- [-] Deconvolve against the scRNA reference
```

四种状态都出现（`[ ]` / `[>]` / `[x]` / `[-]`），时间戳为 UTC 带偏移。

`safe_name`：`[A-Za-z0-9._-]` 以外的字符替换为 `_`，去掉首尾 `._`，为空则用 `session`。例如 Channel 会话 `telegram:42` 存为 `telegram_42.json`。已知 `a/b` 与 `a_b` 会撞到同一文件——本仓库真实的 id 是 hex 或 `platform:chat_id`，接受而不哈希（哈希会让人读目录变得不可读）。

### 9.2 `PlanBook`（`omicsclaw/planning/book.py`）

| 方法 | 语义 |
|------|------|
| `for_session(session_id)` | 取或建该会话的 `PlanStore`；新建时绑定写穿 sink，并在锁外从归档 `restore` 一次 |
| `sessions()` | 被问过的全部会话 id，按首次使用顺序 |
| `forget(session_id)` | 丢弃内存中的 store，不动归档（下次 `for_session` 会重新恢复）。**当前没有调用者** |

- **空 `session_id` 得到一个永不持久化的 store**：匿名路径没有可恢复的身份，否则两个无关运行会共享同一文件。
- **每进程每会话只读一次归档**：内存中的 store 是该文件唯一的写者，归档不会在它脚下变动。一旦第二个进程写同一 workspace 的计划目录，这个推理就不成立，症状是两个 agent 静默互相覆盖计划。
- **写穿**：每次被接受的写入在工具返回前落盘，崩溃窗口只有"一次文件写入"。

### 9.3 失败处理

`build_plan_book` 绑定 `on_archive_error=_report`：存储失败记一条 warning（只记 session id，不记计划内容），exchange 继续。计划在内存中是正确的，拒绝工具调用或整个 exchange 会把磁盘问题变成丢失的 turn；代价是持久性。恢复失败时 store 保持为空。没有绑定 sink 的 `PlanBook`（测试、直接使用）会让错误直接抛出。

### 9.4 恢复路径

```
进程退出 / 崩溃
  ──► oc cli --session visium-01     （或在 REPL 中 /resume）
  ──► 用户发一句"继续"
  ──► SessionRegistry 加载历史与压缩摘要（memory.db）
  ──► _assemble → build_injector → PlanBook.for_session("visium-01")
          └─ FilePlanArchive.load → PlanStore.restore
  ──► 第一次模型调用：发送视图末尾出现计划块
  ──► 模型从 [>] Identify spatial domains 继续
```

计划与会话历史是两份独立存储：`memory=False` 时会话不跨进程，但计划文件仍在，`--session` 用同一 id 时计划照样恢复。

---

## 10. Surface 集成

### 10.1 CLI（`omicsclaw/entry/cli/_repl.py`）

| 入口 | 行为 |
|------|------|
| `/plan`、`/tasks` | 同一实现 `_tasks()`：读 `app.plans.for_session(当前 session).read()` 并打印。规划关闭时提示 "Planning is not enabled"；无条目时提示 "No tasks yet" |
| 自动快照 | 每个成功（非 `is_error`）的 `plan_write` TOOL_RESULT 之后调用 `_show_plan`：从 book 读**完整**计划（包括本次没提到的条目）并打印；与上次打印的快照相同则不打印（读模式调用、被拒绝的写入都不会重复刷屏） |
| `/new`、`/clear`、`/resume` | 切换会话时清空"上次打印的快照" |

打印格式（`_task_lines`）：

```
Tasks  ·  1/4 done  ·  1 active
  1. ✔  Run spatial preprocessing and QC on the Visium sample  [completed]
  2. ▶  Identify spatial domains with leiden  [in_progress]
  3. ○  Run differential expression between domains  [pending]
  4. ○  Write the analysis report  [pending]
```

`▶` 黄 / `✔` 绿 / `⊘` 灰 / `○` 默认色，状态词与图标并列。内容用 `rich.text.Text` 而非 markup 渲染，防止 `[read the matrix]` 这类文本被吞成样式标签。

**只可看、不可驱动**：没有 `/approve-plan`、`/do-current-task`、`/resume-task`——它们在移植的命令目录中，但不在 `REPL_SLASH_COMMAND_SPECS` 里。能直接设置状态的 surface 命令会成为绕过 `validate` 的途径。也没有自动续跑：一个 exchange 结束后是否继续，由用户发下一条消息决定。

### 10.2 Desktop 与 Channel

两者都挂载 `plan_write` 并注入计划块（它们走同一个 `SessionRegistry` → `TurnRunner` 路径），但**都没有展示计划的 UI 或命令**；计划只能通过 `.omicsclaw/plans/<session>.md` 查看。

### 10.3 子代理

`entry/subagent.py`：

```python
_WITHHELD_FROM_SUB_AGENTS: Mapping[str, str] = MappingProxyType(
    {
        PLAN_WRITE_TOOL_NAME: "acts on the calling conversation's plan",
        MEMORY_WRITE_TOOL_NAME: "writes memory that every later conversation reads",
    }
)
```

- `ChildRunner._child_registry` 从子代理的工具集中去掉 `plan_write`（及映射里的其他工具），无论其定义要求什么；自定义定义的 `tools:` 列了 `plan_write` 时照常注册，但会记一条 warning 说该工具不会被授予及理由；
- 子引擎 `exchange_stream` 不传 augmentor（也不传 compactor），子代理 prompt（instructions、workspace、environment、skills）不含规划段；
- 结果：父代理的计划对子代理不可见、不可写；子代理没有自己的计划。内置 `general-purpose` 的描述由这份映射渲染，写明 `plan_write` "acts on the calling conversation's plan"。

---

## 11. 组学多步分析示例

用户："用 examples/demo_visium.h5ad 做空间域识别，然后比较各域的差异基因，写一份报告。"

```
turn 1  模型：plan_write
          qc       pending  Run spatial preprocessing and QC on the Visium sample
          domains  pending  Identify spatial domains
          de       pending  Run differential expression between domains
          report   pending  Write the analysis report
        → validate 通过（无 completed）→ merge → store.write → sink 写 JSON + MD
        → CLI 打印 Tasks 0/4

turn 2  模型：plan_write [{qc, in_progress}]           （只发变化的条目）
        → merge：qc 采用新版本；domains/de/report 未出现且为 pending → 被丢弃！
```

最后一步正是 `merge` 语义需要注意的地方：**未开始的条目如果在更新中被省略，会被裁剪掉。** 工具描述明确告诉模型"Omitting an item drops it only if it was never started"，因此正确的更新是带上仍在计划中的 pending 条目，或者只省略已经开始 / 完成的条目：

```
turn 2  plan_write [{qc, in_progress}, {domains, pending}, {de, pending}, {report, pending}]
turn 3  bash: python skills/spatial/spatial-preprocess/spatial_preprocess.py --input ... --output ...
turn 4  plan_write [{qc, completed}, {domains, in_progress}, {de, pending}, {report, pending}]
        → qc 先前为 in_progress → 不计直接完成 → 通过
        （若省略 de / report，它们先前是 pending，会被裁剪掉）
turn 5+ bash 跑 spatial-domains 脚本 …… plan_write [{domains, completed}, {de, in_progress}, {report, pending}]
...
turn 12 ProgressiveCompactor 达到 SOFT：前半段对话被摘要
        → augmentor 在摘要之后追加：
          ## Current execution plan — authoritative. ...
          [>] Run differential expression between domains
          [ ] Write the analysis report
        → 模型从 de 继续，而不是根据摘要重新猜测进度
```

一次伪造进度的尝试：

```
plan_write [{de, completed}, {report, completed}]      （de 先前 in_progress，report 先前 pending）
  → 直接完成计数 = 1（只有 report）→ 通过
plan_write [{a, completed}, {b, completed}]            （两者先前都是 pending）
  → 直接完成计数 = 2 > 1 → PlanRefused → ToolArgumentError：
    "2 plan items were marked completed in one call without having been in_progress. ..."
```

---

## 12. 配置参数

| 配置 | 命令行 / 环境变量 | 默认 | 说明 |
|------|------------------|------|------|
| `AppConfig.planning` | `--planning` / `OMICSCLAW_PLANNING` | `True` | 一个开关三件事：挂载 `plan_write`、加 `## Planning` 段、注入计划块 |
| `AppConfig.planning_gate_turns` | `--planning-gate-turns` / `OMICSCLAW_PLANNING_GATE_TURNS` | `DEFAULT_GATE_TURNS = 8` | 规划闸门窗口；`0` 关闭闸门但保留其余规划功能。提高 `max_turns` 时应同步提高 |
| `AppConfig.plans_root()` | 不可单独配置 | `<workspace>/.omicsclaw/plans` | 与卸载结果、压缩记录同一个状态目录 |
| `MAX_DIRECT_COMPLETIONS` | 常量 | `1` | 一次写入允许的直接完成数 |
| `EngineConfig.max_turns` | — | `50` | 闸门阈值的推导依据 |

布尔值接受 `1/true/yes/on` 与 `0/false/no/off`，例如 `oc cli --planning false`。

---

## 13. 已知限制

1. **计划块不计入压缩预算。** 它在压缩之后追加，压缩器测量时看不到它；条目内容长度没有上限（只靠工具描述要求"一个条目一个动作"），模型往 `content` 里塞长段落会直接增加每次调用的 token（plan 0039 §5）。
2. **多挂一个工具会移动上下文预算。** `plan_write` 的声明计入 `reserve_tool_tokens`，默认开启让每个部署的可用窗口略小、压缩档位触发点略前移；预算卡得很紧的测试对工具数量敏感（plan 0039 §5、§8.4）。
3. **规划闸门在压缩后可能不触发。** 窗口依赖可见的 assistant 消息数，压缩刚把尾部换掉时凑不满 `gate_turns`（plan 0039 §4.4）。
4. **单进程写者假设。** `PlanBook` 每会话只读一次归档；两个进程写同一 workspace 的同一会话计划会静默互相覆盖，没有任何报错（`book.py` docstring、plan 0039 §8.5）。
5. **`forget` 没有调用者。** `SessionRegistry._evict_sessions` 淘汰空闲会话时不通知 `PlanBook`，book 中的 store 字典随进程内接触过的会话数增长。
6. **计划文件没有清理。** 没有删除 `plans/<session>.json` / `.md` 的入口；目录权限按 umask（文件本身是 0600）。
7. **`safe_name` 可能撞名。** `a/b` 与 `a_b` 共享文件（有意接受）。
8. **子代理不能规划。** 一个被委派做多步分析的子代理没有计划工具，也没有压缩器；它的长任务只能靠自身上下文。
9. **只有 CLI 能看计划。** Desktop 与 Channel 注入并持久化计划，但不展示；没有自动续跑，一次 exchange 结束后模型停下，需要用户再发消息。
10. **`active_count()` 是无消费者的接缝**，保留给未来想展示进度的 surface。
11. **`entry/planning.py: build_injector` 的 docstring 与现行为有出入**：它说 `app.plans` 只在规划关闭时为 `None`，但 `build_app` 在调用方自带工具且未挂 `plan_write` 时也会置 `None`（`AgentApp.plans` 的 docstring 是准确的）。
12. **部分更新会裁剪省略的 pending 条目。** 这是设计而非缺陷，但模型若误以为"只发变化条目"是安全的，就会丢掉尚未开始的步骤；防线只有工具描述与准则里的说明。

---

## 14. 测试

| 位置 | 覆盖 |
|------|------|
| `tests/planning/test_plan.py` | `PlanStore` 读写、restore 不触发 sink、`active_count`、并发 |
| `tests/planning/test_rules.py` | 防作弊阈值、`cancelled → completed`、合并保留 / 裁剪、顺序稳定、重复 id |
| `tests/planning/test_tool.py` | 读 / 写模式、`steps=[]` 为读、参数错误带下标、会话解析、policy |
| `tests/planning/test_injector.py` | 注入块与闸门的条件、顺序、至多一次 |
| `tests/planning/test_render.py` | `format_plan` 只含活跃条目、`render_document` 四种标记 |
| `tests/planning/test_archive.py` | 原子写（在 `os.replace` 注入失败）、JSON 先于 Markdown、坏文件整体拒绝 |
| `tests/planning/test_book.py` | 每会话隔离、首次恢复、空 id 不持久化、错误 sink |
| `tests/planning/test_planning_is_a_leaf_layer.py` | 分层守卫 |
| `tests/entry/test_planning.py` | 接线：开关、prompt 段、`--planning-gate-turns`、三条 exchange 路径的会话绑定 |

---

## 15. 文件索引

| 文件 | 内容 |
|------|------|
| `omicsclaw/planning/__init__.py` | 导出面与用法示例 |
| `omicsclaw/planning/plan.py` | `PlanStatus`、`PlanItem`、`PlanStore`、`PlanWriteSink` |
| `omicsclaw/planning/rules.py` | `validate`、`merge`、`apply`、`PlanRefused`、`MAX_DIRECT_COMPLETIONS` |
| `omicsclaw/planning/tool.py` | `plan_write_tool`、`PLAN_WRITE_SCHEMA`、`PLAN_WRITE_TOOL_NAME`、`SESSION_VALUE_KEY` |
| `omicsclaw/planning/guidance.py` | `PLANNING_GUIDANCE`、`PLANNING_SECTION_HEADING` |
| `omicsclaw/planning/injector.py` | `PlanInjector`、`DEFAULT_GATE_TURNS`、`PLANNING_GATE_TEXT`、`PROGRESS_TOOL_NAMES` |
| `omicsclaw/planning/render.py` | `format_plan`、`render_document`、`INJECTION_HEADER`、`DOCUMENT_TITLE` |
| `omicsclaw/planning/archive.py` | `PlanArchive`、`FilePlanArchive`、`PlanArchiveError`、`dump_items`、`load_items`、`safe_name` |
| `omicsclaw/planning/book.py` | `PlanBook`、`ArchiveErrorSink` |
| `omicsclaw/engine/augmentor.py` | `TurnAugmentor` |
| `omicsclaw/engine/loop.py` | `_kernel` 中 compactor → augmentor 的顺序 |
| `omicsclaw/entry/planning.py` | `build_plan_book`、`build_injector`、`_report` |
| `omicsclaw/entry/assembly.py` | `foundation_tools(plans=)`、`default_sections(plan_tool=)`、`build_app`、`AgentApp.plans` |
| `omicsclaw/entry/turn.py` | `_assemble`、`TurnRunner.turn_values` |
| `omicsclaw/entry/config.py` | `planning`、`planning_gate_turns`、`plans_root()` |
| `omicsclaw/entry/subagent.py` | `_WITHHELD_FROM_SUB_AGENTS`、`ChildRunner._child_registry` |
| `omicsclaw/entry/cli/_repl.py` | `_tasks`、`_show_plan`、`_task_lines` |
| `omicsclaw/entry/cli/_slash_command_support.py` | `REPL_SLASH_COMMAND_SPECS`、`/plan` `/tasks` 的描述 |
| `docs/plans/0039-planning-layer.md` | 计划、偏离、已知代价、审核返工 |
| `docs/FRAMEWORK-REBUILD.md` | Step 6.9 小节 |
