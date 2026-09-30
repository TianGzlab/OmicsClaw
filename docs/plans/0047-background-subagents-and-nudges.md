# 计划 0047 — 子代理后续：用量并入父会话（可实施）与后台委派（暂缓）

**状态**：第三版（2026-09-23）。经一轮独立只读审核（需修改后实施），owner 按推荐裁定，已据此返工：A0/A1 移入缺陷修复，A2 归 0052，B 部分拆至 0055，后台委派暂缓；第三版经架构审核与 harness9 对照小改（S4 的处置、子代理不再获得 `memory_write`、后台恢复时的 harness9 参考）。待 owner 过目。未写任何生产代码。

**缘起**。0046（子代理层）把四件事推给了 0047：后台委派（`task` 的 `background`
模式）与 `TaskTracker`、分离运行的结果注入下一轮、`@agent` 直跑（0046 :41-44、
:243、§9 :494、§11 表第 7 行 :556）；以及"子代理的 token 用量不进父
`RunResult.usage`，后果是 `/usage` 少算。0047 一并解决，或者接受——但要写出来"
（0046 §12 第 3 条，:570-572）。`docs/FRAMEWORK-REBUILD.md` Step 6.12 的
"Front-only"（:1688-1692）重申了后台一项。

第一版（约 970 行）还收了两处 0046 缺陷（A0/A1）、审批归属（A2）和 nudge/gate
家族（B1–B3）。审核记录见 `docs/reviews/2026-09-23-plans-0047-0052-0053-0054.md`
的"0047 审核"与"接缝审核"两节。各项去向（owner 裁定，2026-09-23）：

| 第一版 | 内容 | 去向 |
|---|---|---|
| A0 | 子代理不得改写父会话的计划 | 已移入缺陷修复批次（2026-09-23），见 0046 末尾的交付后修复一节 |
| A1 | 撞轮数上限时不得把工具原文当结论交回 | 已移入缺陷修复批次（2026-09-23），见 0046 末尾的交付后修复一节 |
| A2 | 审批卡片显示是哪个子代理在请求 | 归 0052 T1（S-attr） |
| A3 | 子代理用量计入 `/usage` | **本计划唯一的可实施任务**（§1–§5） |
| A4–A6 | 后台委派、结果注入、CLI 可见性 | 暂缓（§7） |
| A7 | `@<agent> <task>` 直跑 | 暂缓（§7） |
| B1–B3、StallNudge | nudge/gate 家族 | 拆至 0055 |

**前置**：0046 已交付；缺陷修复批次的 D2 改的正是 A3 要动的 `ChildRunner.delegate`
事件循环，A3 在它提交之后实施。0051 已实现，下文 CLI 引用按实现后的 `_repl.py`
重新核对过。行号以 2026-09-23 的工作树为准（`entry/subagent.py` 已含修复批次尚未提交
的 D1/D2/G1 改动）；请按符号名定位。

---

## 1. 目标（A3）

| 可观察的结果 |
|---|
| CLI 的 `/usage` 总量包含子代理花掉的 token，并单列子代理那一份 |
| 交换不论收敛、失败、超时还是被取消，已经完成的子代理模型调用都计入 |
| 撞上轮数上限的委派（D2 之后以 `is_error` 交回）照样计入 |
| 没有发生委派时，`/usage` 的输出逐字不变 |

## 2. 现状（读代码得到的事实）

- **子引擎的用量被丢弃。** `ChildRunner.delegate`（`entry/subagent.py:212-254`）遍历
  `engine.exchange_stream(...)`（:244-246），只处理 `TOOL_START`（转成父代理的进度行，
  :247-251）和带 `result` 的事件（:252-253），再交给 `_conclusion`（:254、:300 起）。
  `TURN_END` 落空，`RunResult.usage` 也没人读。
- 引擎每轮在工具执行**之后**发 `EngineEvent.turn_end(turns, outcome.usage)`
  （`engine/loop.py:449`；工厂在 `engine/types.py:301-302`）。`usage is None` 表示流式
  后端没有报告（`types.py:220-243`）。`RunResult.usage` 是同一批数字之和
  （`loop.py:431`、`:454-461`），只出现在 `DONE` 上。
- **父代理的 `/usage`**：`Repl._count`（`entry/cli/_repl.py:1246-1262`）逐帧累加
  `TURN_END.usage`，`None` 跳过、零照加；`/usage` 打印 `Session total: X in / Y out`
  （`Repl._command`，:625-630），计数器 `self._usage` 在 `Repl.__init__`（:529）。
  `tests/entry/test_cli_render.py::test_only_a_reported_count_is_added_to_the_session_total`
  钉住"`None` 不计"。子引擎的帧不进父流，所以这里一个子代理 token 都看不到。
- `TurnHandle.__init__` 为每个交换建一个 `ApprovalBroker`（`entry/turn.py:826`）；
  `SessionRegistry._attempt` 构造 `TurnRunner(..., approval=handle.approvals, ...)`
  （`entry/session.py:764-775`）。`TurnHandle.wait()` 在取消或失败时返回 `None`
  （`turn.py:882-891`），`handle.outcome` 也是 `None`。
- `TurnRunner.run` 在 `use_tool_context(...)` 里跑完整个交换（`turn.py:559-565`）；
  `TaskTool.execute` 用 `use_tool_context` 整体重绑（`subagent/task_tool.py:156-163`）；
  执行器给每个工具调用开一个 Task（`engine/executor.py:244-247`）。contextvar 按值
  复制进新 Task：复制的是引用，对可变对象的修改外层看得见，`ContextVar.set` 看不见。
- 修复批次 D2 之后，`MAX_TURNS` 退出的委派由 `_conclusion` 抛 `DelegationIncomplete`
  而不是返回结论（见 `test_subagent_wiring.py::test_a_sub_agent_that_runs_out_of_turns_reports_failure_not_its_last_tool_output`）。
  "拿到结论之后再记账"的写法会把这类委派整笔漏掉——审核 M4(a)。
- Desktop 与 Channel 都不汇总用量；Desktop 线格式只带父代理每轮的数字
  （`entry/render.py::_turn_end_payload`）。`run_turn` / `stream_turn`
  （`turn.py:365-436`）没有 handle，也没有哪个 surface 用它们报用量。

## 3. 设计

### 3.1 唯一的计入点：子引擎的每个 `TURN_END`

`ChildRunner.delegate` 的事件循环加一个分支：`TURN_END` 且 `usage is not None` 时，
加到当前绑定的 tally 上。口径与 `Repl._count` 相同：一轮在它的 `TURN_END` 上计入，
没报告的轮跳过；工具执行中被取消的那一轮还没发 `TURN_END`，不计——父代理自己的
计数也是这样。

**不读子引擎 `DONE` 上的 `RunResult.usage`**：它是同一批 `TURN_END` 的和，再读一次
就是第二个计入点。第一版"`DONE` 时记一次"恰好漏掉最贵的几种情形：撞上限（D2 在
取结论时抛出）、`ProviderError`、超时、取消，这几种要么没有 `DONE`，要么在记账前
就已抛出。

### 3.2 tally 由 `TurnHandle` 持有、`TurnRunner` 绑定

与审批 broker 同一个形状：handle 创建它，`_attempt` 交给 runner，runner 在 `run()`
里绑定。交换不论怎么结束，handle 都还在，所以读取点只有一个，而且总能读到
（审核 M4(b)）。

```python
# omicsclaw/entry/subagent.py
class DelegatedUsage:
    """Token usage of the sub-agent model calls made during one exchange."""

    def add(self, usage: Usage) -> None:
        """Add one sub-agent model call."""

    @property
    def total(self) -> Usage:
        """Everything added so far."""


@contextmanager
def counting_delegated_usage(tally: DelegatedUsage) -> Iterator[None]:
    """Add the usage of every delegation run inside the block to *tally*."""
```

- contextvar 是 `entry/subagent.py` 的私有模块变量。写它的 `ChildRunner` 与绑定它的
  `TurnRunner` 都在 entry 层，不新增跨层接口。
- `TurnHandle.__init__` 建 `self.delegated = DelegatedUsage()`（`__slots__` 加一项）；
  `_attempt` 传 `TurnRunner(..., delegated=handle.delegated)`；`TurnRunner.run` 把
  `counting_delegated_usage(self.delegated)` 与 `use_tool_context(...)` 放进同一个
  `with`。直接构造的 `TurnRunner` 不传时自建一个，`runner.delegated` 恒存在。
- 没有绑定时（`run_turn`、`stream_turn`、直接 `app.registry.execute(task…)`）静默不记。

**为什么不用 `ToolContext.values`**：`use_tool_context` 是整体替换，每个重绑点都得
记得转交（今天有 `_session_bound` 与 `TaskTool.execute` 两处），漏一处就静默少算，
正是 0046 §7.1.1 那类缺陷的形状；而且按 0046 §7.1，values 是"这一轮的事实"，不是
累加器。专用 contextvar 不受这些重绑影响。

**为什么不放在 `subagent` 或 `tools` 层**：今天在工具调用里花模型 token 的只有
`ChildRunner`，而它在 entry 层。等出现第二个（比如一个会调模型的工具），再把它提升为
`ToolContext` 上的一条通道。

**为什么不加 `TurnOutcome.delegated_usage`**：取消与失败时 outcome 是 `None`，那会
成为第二个、而且残缺的读取点。

### 3.3 CLI 的读取点

- `Repl._drive` 在 `await handle.wait()` 之后读一次 `handle.delegated.total`，累加到
  新计数器 `self._delegated_usage`。`_count` 不变（`[7, 0]` 那条测试不改）。
- `/usage`：总量 = 父 + 子；子代理非零时追加一段，例如
  `Session total: 1234 in / 567 out (sub-agents: 800 in / 300 out)`。没有发生委派时
  输出逐字不变。
- `/compact` 走同一个 `_drive`，tally 为零，不受影响。

## 4. 开放问题

| Q | 问题 | 推荐与理由 |
|---|---|---|
| Q17 | `/usage` 的总量含不含子代理？ | **含**，括号里单列子代理。总量回答的是"这次会话花了多少"，把子代理放到括号外，最显眼的那个数字会继续少算 |
| Q4 | 后台子代理的能力范围 | 恢复后台委派的前提，本轮不需要裁定（§7.3） |

（Q17 接续第一版的 Q1–Q16 编号，避免与处置表里的旧编号混淆。）

## 5. 任务 A3

**A3 子代理用量并入 `/usage`**（依赖：修复批次 D2 已合入）

- 改：`entry/subagent.py`（`DelegatedUsage`、`counting_delegated_usage`、
  `ChildRunner.delegate` 的 `TURN_END` 分支）；`entry/turn.py`（`TurnHandle.delegated`；
  `TurnRunner` 的 `delegated` 参数与绑定）；`entry/session.py` 的 `_attempt`（传参一行）；
  `entry/cli/_repl.py`（`_drive`、`/usage`）。
- 验收：
  1. 一次前台委派，子引擎两轮分别报 `Usage(5, 2)`、`Usage(2, 1)` →
     `handle.delegated.total == Usage(7, 3)`；父代理的 `RunResult.usage` 不含这些数字；
  2. **撞上轮数上限的委派**（`max_turns: 1`，唯一一轮报 `Usage(7, 3)`，D2 让它以
     `is_error` 交回）→ 仍然计入 `Usage(7, 3)`；
  3. 委派完成后父交换被取消，`handle.wait()` 返回 `None` → `handle.delegated.total`
     仍是子代理的用量；
  4. 子引擎某一轮 `usage is None` → 该轮不计，其余照计；
  5. 在嵌套 Task 里记录的用量落在外层绑定的 tally 上；未绑定时不抛、不记；
  6. CLI：委派之后（包括父交换随后被取消）`/usage` 的总量含子代理并单列；没有委派
     时输出逐字不变。
- 测试：`tests/entry/test_subagent_wiring.py`（`_ScriptedProvider` 增加按调用报告
  `Usage` 的能力；验收 1、2、4、5）；`tests/entry/test_session.py`（验收 3，经真实
  `SessionRegistry` 与 handle）；`tests/entry/test_cli_commands.py`（验收 6）。
- 定点变异：
  1. 改回"拿到结论之后记 `result.usage`"→ 验收 2 红：**撞上限的委派用量为 0**；
  2. `TurnRunner.run` 不绑定 tally → 验收 1 红；
  3. `_attempt` 不把 `handle.delegated` 交给 runner → 验收 3 红；
  4. CLI 改从 `handle.outcome` 读 → 验收 6 的"随后被取消"用例红；
  5. contextvar 里存不可变的 `Usage`、用 `set` 累加 → 验收 5 红（子 Task 里的 `set`
     外层看不见）。

测试命令（`rapids_singlecell` 环境；默认 python 没有 pytest）：

```bash
PYTHONDONTWRITEBYTECODE=1 /opt/conda/envs/rapids_singlecell/bin/python -m pytest \
  tests/subagent tests/entry/test_subagent_wiring.py tests/entry/test_session.py \
  tests/entry/test_turn_runner.py tests/entry/test_cli_commands.py \
  tests/entry/test_cli_render.py -p no:cacheprovider -q -o addopts=""
```

审核时的基线是 `tests/subagent tests/entry/test_subagent_wiring.py tests/planning
tests/engine` = 662 passed, 7 skipped。修复批次正在改同一批文件，实施前重测。

## 6. 与其他计划的交叉

- **缺陷修复批次（D1/D2）**：同改 `ChildRunner.delegate` 与 `_child_registry`；A3 排在
  D2 之后。
- **0055**：共改 `entry/subagent.py`（0055 B2 给子交换传 `augmentor=`；A3 在同一个
  事件循环里加分支）和 `entry/turn.py`（0055 B1 改 `_assemble`；A3 改 `TurnRunner` 与
  `TurnHandle`）。文本相邻、语义无关，两份计划可以独立交付，后落地的 rebase。
  `entry/config.py`、`.env.example`、`tests/test_env_example.py` 本版 0047 不碰（A3
  没有旋钮），只在恢复后台委派（`background_subagents` 等）时才会与 0055 共改。
- **0052 T1（S-attr）**：接管第一版的 A2；与 A3 没有共改文件。
- **0054**：`question=None` 统一在 `ChildRunner.delegate` 绑定（由 0054 负责），
  `ask_user` 加入 `_WITHHELD_FROM_SUB_AGENTS`（D1 建立、G1 改为带理由的映射）；与 A3 只是同一函数里的文本相邻。
- **0051**：已实现；A3 只改 `_drive` 与 `/usage` 分支。
- **0043（观测层）与架构审核 S4**：tally 不兼做"用量与遥测共用的子引擎事件汇"。用量用 tally
  （属于某次父交换，走 contextvar），遥测是应用级静态依赖（走构造注入），两者作用域不同；把原始
  子引擎的 `TURN_END` 送进父 `RunScope` 会截断父轮 span（`observability/scope.py` 的
  `RunScope._observe` → `_end_turn`，:552-579）。子代理遥测另立 0043 的小后续：`ChildRunner` 接收
  `telemetry`，用 `telemetry.run(agent_type=<子代理名>)` 包住循环；`RunScope` 的 interaction span
  以 `parent=current_parent()` 打开（今天一律根 span，`scope.py:435-437`）。与 A3 同改
  `ChildRunner.delegate` 的事件循环，文本相邻、语义无关。
- **缺陷修复 G1**（工作树，未提交）：子代理不再获得 `memory_write`——"不下发给子代理的工具"
  由 D1 的名字集合改为带理由的映射 `_WITHHELD_FROM_SUB_AGENTS`（`entry/subagent.py:55-60`），
  general-purpose 的描述由它渲染。这对应 §7.4 的 M2，M2 因此部分解决。A3 不受影响。

## 7. 后台委派与 `@agent`：暂缓

owner 裁定 3（2026-09-23）：第一版的 A4–A7 暂缓。按现有设计，后台子代理只能读文件、
查 skill、查记忆，价值有限，而且存在安全缺口；等真正需要"后台跑分析"时再设计。

### 7.1 问题陈述（保留）

0046 只做前台：一次委派是一道屏障，父代理在它结束前什么都做不了，真正的上界只有
`turn_timeout_s`（CLI 默认 `None`）。harness9 有后台模式（`task_tool.go`、
`tracker.go`）：`task` 立即返回 id，结论在下一次交换前注入；另有 `@name` 前台直跑。

### 7.2 第一版的设计轮廓（恢复时的起点）

1. `task` 多一个 `background` 参数，只在入口声明"结果送得到人"时出现；立即返回 id。
2. `DelegationTracker`（`subagent/tracker.py`，不叫 `TaskTracker`，避开 `/tasks`）：
   进程内登记后台运行，持有 Task 引用、取回异常、保存未送达的结论；单线程，无锁。
3. 分离运行不绑审批通道（`approval=None` → `ApprovalUnavailable`，失败关闭）。不能沿用
   父交换的 broker：`abandon()` 之后再来的请求在 `timeout_s=None` 下永久挂起（第一版
   探针，审核复现）。工具表在 `_WITHHELD_FROM_SUB_AGENTS` 之外，再按
   `ToolPolicy.allowed_in_background`（`tools/base.py:234`，今天没有读者）过滤。
4. 注入点在 `SessionRegistry._attempt`，不在 `submit`：`submit` 在交换开始前就返回，
   会漏掉排队期间完成的结果。结论前置进下一条用户消息、随历史持久化，**交换收敛后才
   标记送达**（harness9 `DrainCompleted` 取出即标记，在本仓库会随被取消、不落盘的交换
   一起丢失）。
5. CLI：`/tasks` 成为 `/plan` 的超集（0041 裁定 2 不变）；完成时给出提示。
6. `@agent`：走会话 lane 的前台直跑，结论进同一个收件箱。

### 7.3 恢复的前提：Q4（后台能力范围）

过滤后后台只剩 `read_file`、`use_skill`、`memory_search`（`plan_write` 已被 D1 剔除，
`memory_write` 已被 G1 剔除）。恢复前 owner 需要先定能力范围，候选：(a) 接受"只读"
的有限价值；(b) 沙箱已隔离网络且开了 `sandbox_auto_approve` 时，放开 `bash` 的
`allowed_in_background`——与 `entry/sandbox.py::bash_policy` 同一条件，属安全姿态变化，
按 0049/0050 的先例单独裁定、单独审核；(c) 另设一个专门在后台跑 skill 脚本的工具。
未定之前不恢复。

### 7.4 恢复前必须解决的问题

| 审核条目 | 问题 | 方向 |
|---|---|---|
| M1 | 注入块可被伪造：子代理结论里的 `</background-result>` 之后的文字会冒充用户原话 | 中和闭合标签或每次随机 nonce 定界；用户原文前加定界行；"伪造闭合标签"测试，以"去掉转义"作定点变异 |
| M2（部分解决） | 后台 `memory_write` 等于无人值守地写进每个会话的系统提示（`entry/memory.py::_WRITE_POLICY` 声明 `allowed_in_background=True`，0040 从未写理由） | G1 已让任何子代理（前台、后台）都拿不到 `memory_write`，工具描述随 G1 的映射渲染；剩 `_WRITE_POLICY` 的 `allowed_in_background=True` 仍无理由：恢复前改为 `False` 或写明理由 |
| M3 | offload 只处理 `Role.TOOL`（`context/offload.py:254`），注入后的结论是用户消息，超大结论会让"失败即重投"卡死会话 | 注入设上限，超出部分写进 `.omicsclaw/` 文件、注入里只放路径；同一结果连续失败 N 次后只注入一行说明 |
| M5 | 结果送不到的入口仍向模型提供后台模式 | 原则已由裁定 9 定下（§7.5）；由入口显式开启（REPL 调 `open()`，`attach_sessions` 不调），与 0054 的"按 surface 修正配置"收在 launch 的一处（接缝 D6） |
| M6 | 完成提示在最常见路径上不生效，还会说假话 | 打印前查是否已送达并换措辞；空闲时提示要么用 prompt_toolkit 的 `run_in_terminal`/`patch_stdout`，要么明确承认只在交换前后提示；验收加"在空闲提示符时完成" |
| M7 | 会话切换（`/new`、`/clear`、`/resume`，都经 `Repl._switch_to`）与进程重启的生命周期无规格 | 写成规格与验收；id 跨进程唯一；考虑一个每次重述"仍在运行的后台任务"的 augmentor（接到 0055 的链上） |
| M8(a) | `_repl.py::_said` 只剥 `SHELL_RECORD_HEADER`，结果前导会出现在 `/sessions` 预览与恢复回显里 | 导出前导 header 常量，交给同一个清洗函数 |
| M9 | 两条安全验收按原写法测不到 | 用工作区 `ask` 规则或一个 `allowed_in_background=True` 且 `ASK` 的测试工具造出"会询问的后台调用"；禁词测试接上会话层 |
| S2 | 分离 Task 继承调用时的全部 contextvar（有效策略、超时 pause、broker，第一版列举还漏了 `_ASK_EVERY_TIME` 与观测层 `_CALL`） | `asyncio.create_task(coro, context=contextvars.Context())` 空上下文启动，显式绑定需要的值；A3 的 tally 也因此自然解绑，后台运行绑自己的 tally，送达时计入 |
| S3 | 关停顺序 | `delegations.aclose()` 放到 `sessions.shutdown` 的宽限等待之前 |
| S4 | 进程级上限 2 在 Channel 多用户下一人即可占满；未送达条目无界增长 | 加按会话上限；未送达条目设 TTL 或按会话上限 |
| S12 | 前导以用户角色持久化后，记忆提取器会把子代理文字当成用户陈述的事实 | 提取前剥掉前导，或写进风险 |
| S5、S6、S13 | 工具描述写死工具列表；`"session_id"` 字面量多处持有；`Delegation.log` 无读者 | 从过滤后的集合渲染；常量在 `omicsclaw.tools.context` 定义唯一一份；删掉 `log` |
| S7、Q12 | `@agent` 价值低、与 0051 去掉用户直选 `/skill` 的方向相悖、多处无规格 | 另有需求时单独立项 |
| 接缝 Q-F | 群聊里结果会注入给同一会话下一个说话的人 | 恢复时由 owner 定 |

### 7.5 已由裁定定下的约束

- **裁定 9**：结果送不到人的入口——`--prompt` 一次性模式、非 TTY stdin、Desktop、
  0052 落地前的 Channel——不提供后台子代理（也不提供 `ask_user`）。
- **裁定 1**：D1 在 `ChildRunner._child_registry` 建立唯一一个剔除点（G1 后为带理由的映射
  `_WITHHELD_FROM_SUB_AGENTS`）；后台过滤写在同一个函数里，不另起机制。
- `question=None` 在 `ChildRunner.delegate` 统一绑定（0054），后台运行同样覆盖。
- 第一版 Q6（结果到达不自动发起交换）与 Q8（`/tasks` 合并显示）审核均同意，恢复时沿用。

### 7.6 恢复时参考 harness9

harness9 的后台委派（`internal/subagent/task_tool.go:96-120`、`tracker.go:85-205`）没有可直接采纳
的架构。**借鉴**三处：(1) 集中登记的 tracker——启动、进度、完成、取回都经一个对象，状态迁移互斥；
它用 `sync.Mutex`，本仓库在单一事件循环里以"状态迁移不跨 `await`"达到同样效果，§7.2-2 的"无锁"
不变；(2) 换 sink——后台运行只写 tracker 自己的进度汇，不复用父交换那条会随交换关闭的流，与 S2
的"空上下文启动、显式绑定"一致；(3) `recover` 转为失败——分离 Task 的任何意外异常都落成收件箱里
的一条失败结论，而不只是日志。**不照搬**：ctx 语义自相矛盾（以 `context.Background()` 启动、注释
称比会话活得久，却没有取消路径；本仓库按 S3 由 `delegations.aclose()` 收尾）；不过滤工具表（只靠
审批拒绝；本仓库按 §7.2-3 过滤）；结果不转义、不设上限、取出即标记（对应 M1、M3 与 §7.2-4）；
非 TUI 模式丢结果（CLI/`--prompt-file` 下后台结论直接丢失，印证裁定 9）。

## 8. 非目标与风险

- 非目标：`RunResult.usage` 并入子代理（引擎不知道子代理）；Desktop 线格式与 Channel
  报告子代理用量（它们今天也不汇总父代理的总量）；压缩摘要调用的用量；`run_turn` /
  `stream_turn` 的子代理计量。
- 风险：修复批次与 0054 同改 `ChildRunner.delegate`，A3 后落地并 rebase。`_ScriptedProvider`
  今天不报告用量，扩展它时不能改变既有用例看到的消息。

## 9. 第一版的事实更正

1. `Delegate.delegate` 在 `subagent/delegate.py:25-36`（文件共 36 行），不是 :223-237；
   `SUBAGENT_VALUE_KEY` 在 :11-18。
2. 第一版 §1 说 A、B"唯一的共同改动点"是子交换那一次 `exchange_stream` 调用——不属实，
   实际共改 `entry/subagent.py` 多处、`entry/turn.py`、`entry/config.py`、`.env.example`、
   `tests/test_env_example.py`（§6 已按本版范围重写）。
3. 第一版 §8 说 0054 的 `ask_user`"前台子代理会把问题交给父 broker"——与 0054 §3.8/Q8
   相反；按裁定，子代理一律没有 `ask_user`。
4. 第一版 §3.6 说超长结论"过长时由压缩处理"——offload 只处理 `Role.TOOL`（M3）。
5. 第一版 A3 在 `DONE` 时记账、另在 `TurnOutcome` 上读取——两处都会漏算（§3.1、§3.2）。

## 10. 审核处置

"0047 审核"一节的建议从 S2 起编号，没有 S1。

| 审核条目 | 处置 | 位置或理由 |
|---|---|---|
| M1 注入可伪造 | 随暂缓挂起 | §7.4 |
| M2 后台 `memory_write` | 随暂缓挂起 | §7.3、§7.4 |
| M3 超大结果与重投 | 随暂缓挂起；错误说法已更正 | §7.4、§9-4 |
| M4 A3 漏算与重复计数 | 采纳 | §3：按子引擎 `TURN_END` 记账、tally 挂在 handle 上、单一计入点、变异 1；(c) 的重复计数随 A7 暂缓消失 |
| M5 送不到的入口 | 随暂缓挂起；原则由裁定 9 定下 | §7.4、§7.5 |
| M6 完成提示 | 随暂缓挂起 | §7.4 |
| M7 会话切换与重启 | 随暂缓挂起 | §7.4 |
| M8 与并行计划的交叉 | 部分采纳：(b) 已更正并由裁定统一过滤机制；(a) 随暂缓挂起 | §6、§9-3、§7.4 |
| M9 安全验收测不到 | 随暂缓挂起 | §7.4 |
| S2 空上下文启动 | 随暂缓挂起（恢复时采纳） | §7.4 |
| S3 关停顺序 | 随暂缓挂起 | §7.4 |
| S4 按会话上限与 TTL | 随暂缓挂起 | §7.4 |
| S5 工具列表从过滤后集合渲染 | 随暂缓挂起 | §7.4 |
| S6 `session_id` 常量唯一 | 随暂缓挂起 | §7.4 |
| S7 推迟 `@agent` | 采纳 | 裁定 3；§7.4 |
| S8 价值核对 | 采纳 | 裁定 3；Q4 作为恢复前提（§7.3） |
| S9 B 部分小修 | 移至 0055，全部采纳 | 0055 §3、§5 |
| S10 A1 边界 | 已随 A1 移入缺陷修复批次 | 修复批次测试已覆盖"截断且无正文""撞上限时带上最后的 assistant 文字" |
| S11 A0 丢弃 `plan_write` 时告警 | 已随 A0 移入缺陷修复批次 | 修复批次测试 `test_an_agent_file_that_asks_for_plan_write_is_warned_and_runs_without_it` |
| S12 提取器误读前导 | 随暂缓挂起 | §7.4 |
| S13 删 `Delegation.log` | 随暂缓挂起 | §7.4 |
| S14 篇幅 | 采纳 | 拆分后本版约 300 行 |
| Q1 是否拆分 | 不采纳第一版推荐，按审核拆分 | 裁定 2 |
| Q2 计划隔离方式 | 已随 A0 移入修复批次，(i) 由裁定 1 确认 | 0046 交付后修复 |
| Q3 后台工具范围 | 随暂缓挂起（附 M2 条件） | §7.3 |
| Q4 放开后台 `bash` | 保留为恢复前提 | §7.3 |
| Q5 注入位置 | 随暂缓挂起（附 M1、M3、M8 条件） | §7.2-4 |
| Q6 不自动发起交换 | 随暂缓挂起，结论沿用 | §7.5 |
| Q7 并发上限与时限 | 随暂缓挂起（加 S4） | §7.4 |
| Q8 `/tasks` 撞名 | 随暂缓挂起，(a) 沿用 | §7.2-5、§7.5 |
| Q9 后台默认开 | 随暂缓挂起；第一版"默认开"被裁定 9 否定 | §7.5 |
| Q10 用量修还是接受 | 采纳"修" | A3（§3） |
| Q11 审批归属载体 | 归 0052 T1（S-attr） | 裁定 10 |
| Q12 `@agent` | 随 A7 暂缓 | §7.4 |
| Q13 nudge 放在哪 | 移至 0055（Q1） | 0055 |
| Q14 MemoryNudge 触发规则 | 移至 0055（Q2） | 0055 |
| Q15 StallNudge | 移至 0055（Q3），理由 2 已改正 | 0055 §3.6 |
| Q16 ClosingGate 默认与阈值 | 移至 0055（Q4） | 0055 |

接缝审核中涉及 0047 的条目：

| 条目 | 处置 | 位置或理由 |
|---|---|---|
| D1 `TurnEvent.subagent` 重复 / Q-A 措辞 | 采纳 | 裁定 10：S-attr 归 0052 T1，措辞 ` for sub-agent {name}`；A2 删除 |
| D5 剔除机制二选一 / Q-C | 采纳 | 裁定 1：D1 的集合；`ask_user` 加入；`question=None` 在 `ChildRunner.delegate` |
| D6 按 surface 修正配置 / M13 / Q-D | 随暂缓挂起；原则由裁定 9 定下 | §7.4 M5、§7.5 |
| M6 风险行对 `ask_user` 的假设 | 采纳，已删除并更正 | §9-3 |
| M7 结果块进 0051 预览 / M14 切换会话后提示失真 | 随暂缓挂起 | §7.4 M8(a)、M7 |
| M8 A2 对 Channel 的前提 | 随 A2 移出，不再适用 | 0052 T1 |
| M9 `@agent` 绕过 `TaskTool` 的 `question=None` | 采纳 | 裁定：在 `ChildRunner.delegate` 统一绑定（0054） |
| M11 压力档测试 | 不适用于本版 | 本版不改 `task` 定义；该风险落在 0054 |
| M12 / Q-E 审批提示符上的 Ctrl-C | 已移入缺陷修复批次（D3） | 裁定 1 |
| Q-F 群聊注入 | 随暂缓挂起 | §7.4 |

架构审核（第二轮）与 harness9 对照（第三轮）中涉及 0047 的条目：

| 条目 | 处置 | 位置或理由 |
|---|---|---|
| 第二轮总体结论"0047 合理"；逐项结论第 7 项（`DelegatedUsage` contextvar 合理，不并入 `ToolContext`） | 保持 | §3.2 |
| 第二轮 S4 contextvar 兼做子引擎事件汇、用量与遥测共用 | **不采纳为共用的 contextvar**：tally 属于某次父交换（contextvar），遥测是应用级静态依赖（构造注入），作用域不同；原始子引擎 `TURN_END` 进父 `RunScope` 会截断父轮 span。遥测盲区另立 0043 小后续 | §6 |
| 第二轮 S11 中的 0046 §17 引用失效 | 已由 0046 更正（:773 改指"0047 第一版的 A0/A1"） | — |
| 第三轮 A3 / S4 行 | A3 维持；S4 按上行改编 | §3、§6 |
| 第三轮 O3 行"子代理不给 `memory_write`"（缺陷修复 G1） | 记录；M2 部分解决 | §6；§7.3；§7.4 M2 |
| 第三轮"后台（暂缓）"行 | 恢复时参考：借鉴 tracker、换 sink、失败转结论；不照搬 ctx 语义、不过滤工具、结果处理与非 TUI 丢结果 | §7.6 |
