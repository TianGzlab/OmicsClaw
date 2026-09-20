# 计划 0039 — `omicsclaw/planning/`：Agent 原生的执行计划层

**状态**：已实现，两轮独立只读审核已完成，返工已合入（见 §8）。
**参考实现**：harness9 `internal/planning/`、`internal/tools/plan_write.go`、
`internal/engine/loop_phases.go`（4b''/4c/checkpointPlan/savePlan）、
`internal/hooks/plan_writer.go`。

## 1. 现状：主循环能跑，但会忘

重构后的主循环（`omicsclaw/engine/loop.py`）已经具备 ReAct 的全部动作，
step 6.6 之后还会在**每次模型调用前**做渐进式压缩。这两件事叠在一起产生了一个
参考实现早就遇到过、并且专门建了一个模块去解决的问题：

- 压缩把旧的 turn 换成了摘要，模型对"这次任务总共要做哪几件事"的记忆随之变形；
- 会话恢复（`SqliteSessionStore`）恢复的是消息历史，历史里那句"我打算分五步做"
  和"第三步做完了"只是两条普通的 assistant 文本，没有任何权威性；
- 纯只读探索可以无限持续。`read_file` / `bash grep` 不改变工作区，主循环不会
  认为它"没进展"，于是探索过深而迟迟不动手这件事没有任何东西会打断。

参考实现把这三件事归到同一个模块：计划是一份**脱离对话历史单独保存的权威状态**，
每轮原样重新注入发送视图。本计划把这套机制补到新框架上。

**计划是 Agent 的原生能力，不是用户切换的模式。** harness9 的注释写得很清楚
（`plan.go:3-5`：Plan Mode 已移除）。所以这一层没有"进入规划模式"的开关，
只有 System Prompt 的准则 + 一个工具 + 每轮注入。

## 2. 决策：一个叶子邻接包 + 引擎上一条新的可选接缝

### 2.1 包的位置与依赖白名单

`omicsclaw/planning/`，与 `skills/`、`permission/` 同级，白名单是
**`schema` + `tools`**——和 `skills/` 完全一致，理由也一致：`plan_write`
要声明自己的 `ToolPolicy`，默认值（`HIGH`/`ASK`）会让每次写计划都弹一次人工审批。

不依赖 `engine`、不依赖 `context`、不依赖 `entry`、不依赖 `memory`。
注入器通过**结构化满足**引擎的 Protocol，和 `ToolRegistry` 满足 `ToolExecutor`
是同一种关系。

### 2.2 注入走哪条接缝：新增 `TurnAugmentor`，不复用 `HistoryCompactor`

参考实现在 `prepareTurnInput` 里做注入（4c），位置在压缩之后、模型调用之前。
新框架里那个位置由 `HistoryCompactor` 占着，于是第一反应是装饰它——**否决**，
有一条可验证的理由：

`entry/turn.py:_outcome` 直接读 `compactor.state` / `.last_record` / `.records`
三个 `ProgressiveCompactor` 的具体属性。装饰器必须逐个转发，漏一个不会报错，
只会让这一轮的压缩记录静默消失。这正是 `build_registry` 的 docstring 记下的
R3 缺陷形状（包装了却忘记转发 `use_timeout_pause`）。

所以在引擎上开第二条**可选**接缝：

```python
# omicsclaw/engine/augmentor.py
class TurnAugmentor(Protocol):
    async def augment(self, history, tools) -> Sequence[Message]: ...
```

引擎按顺序做：读工具表 → 压缩 → **增补** → 调模型。增补返回的消息只追加到
**发送副本**，永远不进 `history`、不进 `RunResult.messages`、不累积。
引擎对"计划"一无所知，它只知道有人要在这次调用末尾多说几句话。

`augment` 是 `async`，和 `HistoryCompactor.compact` 对齐：一个同步签名等于在
引擎里替所有未来的实现决定了"增补不需要 I/O"，而这不是引擎该决定的事。

### 2.3 持久化走文件，不动 `memory/` 和 `Session`

参考实现把计划存进 session 表（`SavePlan`/`GetPlan`）。照搬要改三处既有文件：
`entry.Session`、`memory.StoredSession`、`memory.SCHEMA`，并让 `memory` 反向
依赖 `planning`。

改走**工作区文件**，理由不是省事，是这个仓库已经有同形状的先例：压缩层的
卸载结果和压缩日志都写在 `<workspace>/.omicsclaw/` 下，按 session 分文件
（`entry/compaction.py`）。计划照此办理：

```
<workspace>/.omicsclaw/plans/<session>.json   机器状态，恢复的唯一来源
<workspace>/.omicsclaw/plans/<session>.md     人读的计划文档（对应 FilePlanWriter）
```

每次 `plan_write` 成功即写盘（写穿），这比参考实现的"写时检查点"更严——
它的崩溃窗口是一轮，这里是一次文件写。`memory/`、`Session`、SQLite schema
一行都不动。

### 2.4 一个 App 多个会话：`PlanBook`

参考实现是单会话 TUI，`main.go` 造一个 `PlanStore` 注入引擎和工具就够了。
这里 Desktop / Channel 是多会话共享一个 `ToolRegistry`，工具在 `build_app`
时挂一次，而计划是每会话一份。

`PlanBook` 做 `session_id → PlanStore` 的映射，工具在 `execute` 里通过
`context_value("session_id")`（`TurnRunner.turn_values` 已经写进去了）取当前
会话。空 `session_id`（`run_turn` 直呼路径）映射到一个专门的匿名槽位。

### 2.5 防作弊校验放进 `planning`，不放进工具

参考实现把校验写在 `plan_write.go` 的 `Execute` 里，`PlanStore` 明确声明自己不校验。
这里反过来：校验和合并是**关于计划状态转换的规则**，不是关于工具管道的，
放在 `rules.py` 做纯函数，工具只负责解参数和序列化。

后果是这条规则可以脱离工具单独测，也可以被未来的第二个写入口（斜杠命令、
Desktop 的计划面板）复用而不需要绕道工具。

## 3. 交付物

### 新增包 `omicsclaw/planning/`（叶子邻接层，白名单 `schema` + `tools`）

| 模块 | 内容 |
|---|---|
| `plan.py` | `PlanStatus`、`PlanItem`、`PlanStore` |
| `rules.py` | `validate`（防作弊）、`merge`（保留已开始条目）、`PlanRefused` |
| `render.py` | `format_plan` 注入块、`render_document` 人读文档、两处标题常量 |
| `archive.py` | `PlanArchive` Protocol、`FilePlanArchive`、`dump_items`/`load_items` |
| `book.py` | `PlanBook`：按会话取 store，首次取用时恢复，写穿归档 |
| `injector.py` | `PlanInjector`：每轮注入 + 规划闸门 nudge |
| `tool.py` | `plan_write_tool(book)`、schema、`ToolPolicy` |
| `guidance.py` | System Prompt 的"先规划后执行"准则文本 |

### 修改（既有文件，最小面）

| 文件 | 改动 |
|---|---|
| `omicsclaw/engine/augmentor.py` | **新增**：`TurnAugmentor` Protocol |
| `omicsclaw/engine/loop.py` | `run`/`run_stream`/`_kernel` 各加一个 `augmentor=` 形参；`_kernel` 里压缩之后三行 |
| `omicsclaw/engine/__init__.py` | 导出 `TurnAugmentor` |
| `omicsclaw/entry/planning.py` | **新增**：`build_plan_book`、`build_injector`、目录常量 |
| `omicsclaw/entry/assembly.py` | `foundation_tools` 挂 `plan_write`；`default_sections` 加 planning 段；`AgentApp.plans` 字段 |
| `omicsclaw/entry/config.py` | `planning: bool`、`planning_gate_turns: int` 两个字段 + 两个开关 |
| `omicsclaw/entry/turn.py` | 三个调用点（`run_turn`/`stream_turn`/`TurnRunner._exchange`）建注入器并传下去 |
| `omicsclaw/entry/__init__.py` | 导出 |

### 测试

`tests/planning/`（包内全部行为）、`tests/engine/test_augmentor.py`（接缝）、
`tests/entry/test_planning.py`（装配与端到端一轮）。
外加一个与 `tests/skills/` 同形状的分层探针：跑真实代码路径，然后断言
`sys.modules` 里没有 `omicsclaw.engine` / `omicsclaw.entry` / `omicsclaw.context`。

## 4. 对参考实现的刻意偏离（逐条给理由）

1. **`PlanStore.read()` 返回 tuple，不做双重拷贝。** Go 的 `copy()` 两次是因为
   slice 是引用。`PlanItem` 是 frozen dataclass、容器是 tuple，一个引用就已经
   是不可变快照，再拷贝一份是纯开销。
2. **锁用 `threading.Lock` 而不是 `asyncio.Lock`。** `format_plan()` 每次模型
   调用都要读，做成 `async` 会把一个纯格式化函数变成 await 点；而工具有可能
   跑在 `asyncio.to_thread` 里，`asyncio.Lock` 在那里不起保护作用。
3. **校验与合并移出工具**（§2.5）。
4. **规划闸门的计数不放在引擎里。** 参考实现用 `loopContext.turnsSincePlanWork`
   计数。这里注入器每次模型调用都看得到完整发送视图，闸门因此是
   (视图尾部的 K 条 assistant 消息, 计划是否为空, 是否已 nudge 过) 的函数。
   **代价写在 docstring 里**：压缩把尾部换掉之后，可见的 assistant 消息可能
   不足 K 条，此时不触发——参考实现的计数器会照常触发。这个差异是可接受的：
   压缩刚发生意味着模型刚拿到一份新摘要，那一轮不是催规划的好时机。
5. **`cancelled → completed` 的拒绝措辞带上恢复路径**，与参考实现一致；
   但"一次最多 1 个直接完成"的阈值**连同它的理由一起**抄进了 docstring：
   阈值取 1 而非 0 是为了保住"真干完了一件事就直接标完成"的正常用法。
6. **不移植 `ActiveCount` 的 TUI 续跑语义，只保留方法。** 新框架没有 TUI
   （plan 0031 §11 记着 TUI 没移植），`active_count()` 留作 surface 的接缝，
   并在 docstring 里说明它当前没有消费者——一个没有调用方的能力即使测试齐全
   也是死代码，这一点 plan 0038 §8 刚付过学费，所以这里明说。
7. **注入块标题与规划 nudge 改写成英文**，参考实现是中文。这条是实现期核对出来的：
   本仓库的 system prompt 全部是英文（`SOUL.md`、`CLAUDE.md`、`SAFETY_RULES`、
   `TOOL_GUIDANCE`），且 `SOUL.md` 第 1 条写着 default to English。一句中文指令
   接在英文提示词后面，是一次没人要求的语言切换，而且恰好发生在唯一一条
   "存在的意义就是被遵守"的消息上。**这就是 plan 0027 记下的"移植字面量是负债"，
   只不过这次的字面量长得像散文。** 措辞的三个要点照旧保留：声明权威性、
   点名压缩与恢复两个时刻、给出可执行骨架。
8. **规划闸门阈值 8 是重算的，不是抄的。** 参考实现取 12，并在 `runner.go:52-55`
   给了理由：与停滞窗口 10 错开、远低于 SWE-bench 的 28 轮中位。这两个数都是
   它那套 80 轮无人值守编码预算的属性。这里的预算是 `EngineConfig.max_turns` = 50
   （那个模块已按本仓库的基准证据重算过），同比例是 7.5，向上取整 8。

## 5. 已知代价

- **注入块每轮都占 token。** 活跃条目多时按条目内容长度线性增长，且在压缩
  之后注入，所以它不参与压缩预算的测量。10 条中等长度条目约 200~300 token。
  条目内容的长度没有上限——模型可以往 `content` 里塞一整段话，目前只靠
  工具描述约束"一个条目对应一个具体可执行动作"。
- **归档目录跟着 workspace 走。** 换 workspace 等于换一套计划文件，
  这与卸载结果、压缩日志的行为一致。
- **`plan_write` 是并发屏障**（`concurrency_safe=False`）。同一轮里它会独占，
  代价是同轮的其他工具要等它。收益是两个 `plan_write` 不会丢更新。
- **多挂一个工具会移动上下文预算。** `plan_write` 的工具声明计入
  `reserve_tool_tokens`，默认开启意味着每个部署的可用窗口都小了一点，
  压缩档位的触发点也随之前移。当下没有测试因此失败，但预算卡得很紧的场景
  （`tests/entry/test_compaction_in_loop.py` 一类）对工具数量是敏感的——
  这条由 §8.4 的审核发现留下，即使那条发现的主体被驳回了。

## 6. 实现期抓出的三个真实缺陷

都不是计划里写错的，是实现过程中被既有测试或自查抓到的。

### 6.1 `run_turn`/`stream_turn` 从不绑定 tool context

`plan_write` 通过 `context_value("session_id")` 定位会话（§2.4），而这个值只有
`TurnRunner.turn_values()` 写。`run_turn`/`stream_turn` 把 `session_id` 传给了
compactor，却没有传给工具——于是工具写进匿名 store、注入器读会话 store，
**计划写完即丢，什么都不报错**。

修法是新增 `entry/turn.py::_session_bound`，按 `use_tool_context` 自己 docstring
里的写法**显式继承外层 context**：那个函数是"替换"而非"合并"语义，直接绑
`values=` 会顺手解绑调用方设的审批通道，让每个受控工具开始 fail-closed。
两个变异（整体空转 / 裸 `values` 绑定）各自打红对应测试。

### 6.2 规划准则里写死了技能名

准则的"具体动作"示例原本写的是 `spatial-deconv`，被既有探针
`test_switching_the_catalogue_off_removes_it_from_the_turn` 抓到——`skills_index=off`
的部署会在提示词里读到一个没被广告、也没有 `use_skill` 去取的技能名。
改成描述工作本身（"deconvolve the Visium sample against the reference"）。

### 6.3 原子写入的测试是假绿

`test_a_failed_write_leaves_the_previous_plan_intact` 原本靠传入一个序列化会炸的
对象来制造失败——异常在 `dump_items` 里就抛了，**根本没走到写文件**，
对着一个会截断的实现照样通过。改成在 `os.replace` 处注入失败，
并加一条"注入确实到达了 replace"的自检；变异（改回 `write_text`）打红 4 个测试。

## 7. 验证

- 全栈 `tests/{schema,provider,engine,tools,context,skills,entry,mcp,memory,permission,planning,launch}`
  = **3679 passed, 7 skipped**，无回归。
- 新增 **215** 项：`tests/planning/` 181、`tests/engine/test_augmentor.py` 13、
  `tests/entry/test_planning.py` 23（含返工后新增）。
- 6 个既有"形状断言"测试**改写而非删除**：引擎导出表、默认提示词段数
  （六→七）、目录关掉后的段数（五→六）、已挂载工具表、turn 的目录关闭断言。
- 变异验证：原子写入、会话绑定（两种）、重复 id 去重、归档写入顺序，
  每一个都确认打红了具名测试。

## 8. 两轮独立只读审核的发现与返工

两个 Sonnet 子 agent，互不知道对方存在，一个查正确性、一个对标 harness9。

### 8.1 已修（3 条）

| 来源 | 发现 | 返工 |
|---|---|---|
| 正确性 | `validate` 对重复 id 重复计数，造成**误判拒绝** | 见 8.2 |
| 正确性 | 归档"JSON 先于 Markdown"的声明没有测试，对调顺序的变异存活 | 两条新测试（其一拦截 markdown 写入、回头读 JSON 是否已落盘），变异确认打红 |
| 对标 | 25 条 Go 引用里 **7 条行号错位** | 全部修正，并把**全部 28 条**逐行重核了一遍，另收紧 3 条范围（有一条的末行是 `package tools`） |

### 8.2 `validate` 的重复 id 误判

`merge` 会把重复 id 折叠成一条（首次出现胜出），`validate` 却按原始序列计数。
于是同一条已完成条目被**重发两次**（不是两条声明，是一次重发）会被判为
"一次调用完成了 2 条"而拒绝。

根因是去重只发生在 `merge` 里，**校验看到的和合并存下的不是同一份数据**。
修法是把去重提成 `_first_by_id`，两者读同一份。顺带修掉一个更隐蔽的不一致：
`[(a, pending), (a, completed)]` 原先会按 completed 校验、按 pending 存储。

### 8.3 已补的覆盖缺口（1 条）

正确性审核指出：`_session_bound` 只在 `run_turn` 一条路径上被测到，
`stream_turn` 与 `TurnRunner` 都没有。`TurnRunner` 经手工验证本来就是对的
（它自己的 `turn_values()` 已经绑了），但**三条路径里两条没有测试**。
已补两条端到端测试，其中 `SessionRegistry → TurnRunner` 是 Channel / Desktop / CLI
真正走的那条——只在库路径上验证过的特性，等于在没人跑的路径上验证过。

### 8.4 已驳回的一条：`planning=True` 默认值"打翻 6 个既有测试"

对标审核称默认挂载 `plan_write` 挤占 `reserve_tool_tokens`、翻转压缩档位，
打翻了 6 个 planning 之外的既有测试。**复跑不成立**：
`tests/entry tests/engine tests/planning` = 1116 passed, 0 failed，
它点名的测试全绿。

根因两轮审核**独立汇合**：工作树里有另一个会话遗留的未跟踪
`omicsclaw/entry/memory.py`，`entry/memory.py` 与 `entry/compaction.py`
之间有真实循环导入，按测试文件子集的收集顺序时好时坏。正确性审核把它中和后
同样跑出 1116 passed。**这是并发污染，不是本次交付的回归。**

不过这条里有一个**值得留下的观察**：多挂一个工具确实会移动
`reserve_tool_tokens`，进而可能翻转压缩档位。当下没有测试失败，
但这是真实敏感性，已记入 §5。

### 8.5 已声明的一条偏离（原先漏写）

对标审核指出：参考实现**每次 interaction** 都从 Session 重新加载计划
（`loop_phases.go:110`），这里只在会话**首次取用**时恢复。功能上成立——
内存副本是这套安排里该文件的唯一写者，归档不可能在它脚下被改动——
但 §4 没有列出来。已补进 `book.py` 的 docstring，连同它失效的条件：
一旦有第二个进程写同一个 workspace 的计划目录，这条推理就不成立，
症状是两个 agent 互相静默覆盖计划。

### 8.6 交付时的两条 `tests/launch/` 失败，同样是并发污染

最后一次全栈跑出 `tests/launch/test_surfaces.py` 两条失败
（`test_an_exported_variable_beats_the_file`、`test_a_missing_dotenv_is_not_an_error`）。
**不是本次交付的**：`omicsclaw/planning/` 与新增的 entry/engine 改动对 dotenv 与
`omicsclaw/launch/` 零引用，而仓库根在本次会话期间（06:49）新出现了一个 `.env`，
`_adopt_dotenv(root=tmp_path)` 把它一并读了回来，测试的断言没有隔离仓库根。

留作一条给 `launch` 层的观察（不在本计划范围内修）：**一个会扫描仓库根、
并对扫到什么下断言的测试，在多会话共写的树里是环境依赖的。**

除 `tests/launch/` 外全栈 = **3,554 passed, 6 skipped**，无失败。
