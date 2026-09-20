# 计划 0041 —— CLI Surface 对 harness9 的逐项对照与补齐

状态：**调研已完成，owner 已就四条开放问题裁定（见 §8），实现未开始**。
§1-§7 的对照结论写于裁定之前，凡被裁定改变的地方均已就地更新并回指 §8。

## 0. 材料来源与可核实性

本文严格区分「读过并确认」与「读过目录/grep 印象」。凡是引用 harness9 源码的
一行，**都通过 Read 工具真正打开过对应文件的对应行**（部分由并行 subagent
完成，subagent 被要求引用它们自己实际 Read 到的行并注明「未确证」的边界，
协调者未逐字节复核每一条 subagent 引用，这是本文档在证据链上的唯一一处退让，
已在 §8 末节点名，并附有裁定批复时的补充核实清单）。凡是引用 OmicsClaw
源码的一行，均由本文档作者本人直接 Read 确认。

对照的两棵树：

- 本项目：`/workspace/dataset/private/zhouwg_data/OmicsClaw`
- harness9（Go 参考实现）：`/workspace/dataset/private/zhouwg_data/harness9`

前置材料，已读并纳入判断：`README.md`、`AGENTS.md`、`SPEC.md`、
`omicsclaw/entry/cli/__init__.py` 模块 docstring、
`docs/plans/0031-entry-layer.md`（§1.3、§5.1、Q4、附录 A/B/C）、
`docs/plans/0037-launch-and-entry-points.md`（全文，含附录 A/B）、
`docs/FRAMEWORK-REBUILD.md`（step 6/6.7/6.8/6.9/7 与「Next step」）、
`docs/plans/0038-permission-layer.md`（§8 审核结论）、
`docs/plans/0039-planning-layer.md`（结构参考）、
`omicsclaw/surfaces/cli/`（仅通过 0031/0037 的实测表读其行数与耦合面，未逐文件
重读——它已 import 不动，见 §1.2）。

**已知近期变更，不重复调研**：`prompt_toolkit` 并发审批死锁已修复
（`PromptToolkitSource`/`StreamSource` 序列化读者，`Repl._ask` 对任何异常
fail-closed），本文按「已修复」处理，未在 §3 中重复列出。

---

## 1. 背景

CLAUDE.md 与 AGENTS.md 都要求先读 README 再动手；README 的 What's New 显示
OmicsClaw 正在进行一次「框架重建」，第 6 步（`omicsclaw/entry/`，plan 0031）
与随后的启动外壳重排（`omicsclaw/launch/`，plan 0037）已经把 CLI Surface
搬到了一个新位置。**这意味着「CLI Surface」在本仓库今天有两份**：

| | 位置 | 状态 |
|---|---|---|
| 旧 CLI（26 文件 / 14,936 行） | `omicsclaw/surfaces/cli/` | **import 不动**：`_main.py` 在模块作用域 import 已删除的 `omicsclaw.skill`（单数），`oc` / `omicsclaw` / `python omicsclaw.py <任何子命令>` 今天全部在 import 阶段崩溃（`docs/plans/0037-launch-and-entry-points.md:284-291` 实测复现） |
| 新 CLI | `omicsclaw/entry/cli/` + `omicsclaw/launch/` | **能跑**：`oc cli` 经 `omicsclaw.launch:main` 落地，`tests/entry/`+`tests/launch/` 合计 808 passed（`docs/plans/0037-launch-and-entry-points.md:667`） |

AGENTS.md 里那一整段"CLI Surface — prompt_toolkit REPL + Textual TUI"
（含 `interactive.py`、`_session.py`、`_mcp.py`、35 个子命令、SQLite 会话表）
描述的是**旧 CLI 的设计意图**，而旧 CLI 今天连 `import` 都不成立。任务给的
调研范围明确指向新 CLI（`omicsclaw/entry/cli/` + `omicsclaw/launch/`），本文
遵照执行——**这是唯一还能被真进程验证的那一份**。

调研目标：把新 CLI 与 harness9 的 `cmd/harness9/`（`main.go` 470 行、`cli.go`
105 行、`tui.go` 377 行、`tui_update.go` 1883 行、`tui_view.go` 727 行、
`tui_banner.go` 55 行、`upgrade.go` 312 行）逐项对照，找出真缺口，并按
A/B/C 三类归档，产出分阶段实现 plan。

---

## 2. 方法论

### 2.1 三类判据

- **A 类｜真缺口**：harness9 有、OmicsClaw 没有、也没有任何文档记录说明不做。
- **B 类｜已记录的有意取舍**：OmicsClaw 没有，但 plan 0031/0037/0038 或代码
  docstring 已写明理由；本文档额外判断该理由**今天是否仍然成立**。
- **C 类｜形态不同但能力等价**：不算缺口，只记录映射关系。
- **额外一类｜harness9 有但不该抄**：给出理由。

### 2.2 关键事实：harness9 的 CLI/TUI 命令面本身很小

调研前的预期是"harness9 有一大堆 `/login` `/model` `/cost` `/doctor`
之类的 slash command，OmicsClaw 只实现了一小部分"。**这个预期被证伪**：

- `cli.go`（非 TTY 场景的纯文本 REPL）**只有一种 slash 语法**：
  `/<skill-name> [附加文本]`，由 `resolvePrompt`（`cli.go:83-105`，全文读过）
  解析成一次技能激活；找不到技能名就返回 `ok=false`，提示技能未找到，
  不发给模型。没有 `/help`、`/clear`、`/compact`、`/login`、`/mcp`、
  `/resume`——这些字符串在 `cmd/harness9/*.go` 全仓 grep 为零命中（fork 复核）。
- 真正有固定命令表的是 **TUI**（`tui_update.go`），而且只有 **6 个**：
  `new` `resume` `compact` `tasks` `mcp` `exit`（`builtinCmds`，
  `tui_update.go:85-95`，Tab 补全用的规范列表），加上两个非 `/` 前缀
  `!<cmd>`（shell 直通，`tui_update.go:360-363` → `dispatchShellCommand`，
  `:1612-1635`）与 `@<name>`（前台直跑子代理，`:366-368` →
  `dispatchMention`）。除此之外任何 `/xxx` 都走 `resolvePrompt` 当技能名找。
- 没有 `/login`、没有订阅/费用（美元）展示——只有 token 计数与
  「已用/窗口（百分比）」的颜色分级（`tui_view.go:210-287`，绿 <50%、黄
  50-80%、红 ≥80%，样式定义 `tui.go:62-64`）。凭证只来自 `.env`
  （`main.go:112-119` `env.Load`），没有 OAuth/keychain 流程。

这个事实**大幅收窄**了"缺口"的范围：OmicsClaw `entry/cli/_constants.py`
的 `SLASH_COMMANDS` 目录有 38 条、`CLI_SLASH_COMMAND_SPECS` 也是 38 条，
但其中至少 29 条（`/run` `/doctor` `/context` `/export` `/style` `/tips`
`/install-skill` 等）**根本不对应 harness9 的任何东西**——它们是 OmicsClaw
自己的产品设计，不是「抄 harness9 抄漏了」。本文档只对**harness9 确实有**
的能力做缺口判断，其余属于「OmicsClaw 自己的路线图」，不在本次调研范围内。

---

## 3. 逐项对照

### 3.1 A 类 —— 真缺口

#### A-1【最该先做】`/compact`：手动触发压缩

- **harness9**：TUI 里 `raw == "/compact"`（`tui_update.go:330-349`，已读）：
  若 `m.running` 为真则拒绝（避免和正在跑的回合抢引擎），否则设
  `m.compacting = true` 并异步跑 `eng.Compact(context.Background())`；完成后
  打印压缩前后的 token 对比（`:417-437`）。底层机制是
  `internal/memory/progressive_compactor.go` 的 `ProgressiveCompactor`
  （`main.go:419-430` 装配，未逐行读）。
- **OmicsClaw**：`SessionRegistry.compact(session_id) -> TurnHandle`
  已经存在（`omicsclaw/entry/session.py:383`），是 0035 步「渐进式压缩」
  接进主循环后自然具备的能力——**引擎侧已经能压缩，只是 CLI 没有一个命令
  去调用它**。更进一步：`/compact` 甚至没有出现在
  `omicsclaw/entry/cli/_constants.py` 的 `SLASH_COMMANDS` 目录里（38 条
  全部读过，无此项），说明这不是「实现了但没接」，而是「连目录项都没抄」。
  `docs/FRAMEWORK-REBUILD.md:945-946` 已经点名此债：「there is no
  session-delete entry point for the purge methods; the CLI REPL has no
  `/compact`」。
- **判据**：不是 B 类（没有任何文档说"故意不做 `/compact`"，只是被记成
  待办）。**真缺口，且底层能力已就绪，只差命令层接线**。
- **规模**：小。`_constants.py` 加一行目录项、
  `_slash_command_support.py` 的 `REPL_SLASH_COMMAND_SPECS` 加一个名字、
  `_repl.py._command` 加一个分支调 `self._app.sessions.compact(session_id)`
  并渲染返回的 `TurnHandle`（复用 `_pump`）。
- **可证伪验收标准**：`ScriptedSource(["/compact", ...])` 驱动一个真回合，
  断言 (1) 调用了 `SessionRegistry.compact` 而不是 `submit`；(2) 压缩期间
  `/compact` 再次输入被拒绝并给出理由（对齐 harness9「`m.running` 时拒绝」
  的判断，需要 OmicsClaw 自己的等价条件，例如该 session 的 lane 正忙）；
  (3) 压缩完成后屏幕上出现压缩前后的估算 token 数或至少「已压缩」的确认行。

#### A-2【最该先做】会话发现与续接：`/resume` 与真正的 `/sessions`

- **harness9**：`/resume`（`tui_update.go:382-384`）调用
  `handleResumeList()`（`:1410-1449`）—— 从 `*memory.Manager`
  （SQLite，`main.go:233` 打开于 `~/.harness9/sessions.db`，schema 在
  `internal/memory/manager.go:20-45`：`sessions`/`messages`/
  `session_plans` 三表）拉最近会话，最多列 10 条（`[i] ID updatedAt N
  条消息`），下一次 Enter 按序号选中（`handleResumeSelection`，
  `:1452-1483`），调 `m.manager.OpenSession` + `m.eng.SetSession`。
  `/new`（`:1386-1407`）另建一个。
- **OmicsClaw**：底层持久化**已经存在且默认开启**——
  `AppConfig.memory: bool = True`（`omicsclaw/entry/config.py:255`），
  `attach_sessions(app, store=None)` 的 `store=None` 含义是「这个 app 自己
  的库」而非「内存」：有 memory 数据库时自动用
  `SqliteSessionStore`（`omicsclaw/entry/session.py:858-864`，docstring
  原文核对过）；`SessionRegistry._session()` 在会话不在内存时会
  `await self._store.load(session_id)`（`session.py:768-778`），所以
  `oc cli -- --session <id>` 传入一个此前用过的 ID **确实能续上**
  （`ReplOptions.parse` 接受 `--session`，`omicsclaw/launch/_surfaces.py:
  268-279`；`_run_cli` 把它原样传进 `Repl(...)`，`_surfaces.py:414-420`）。
  **但**：
  1. `REPL_SLASH_COMMAND_SPECS` 只有 9 条
     （`/skills /new /current /sessions /clear /usage /mcp /help /exit`，
     `omicsclaw/entry/cli/_slash_command_support.py:97-112`），**没有
     `/resume`**——它在 38 条目录里，但不在这 9 条实现里。
  2. `/sessions` 已实现，但 `_sessions()`（`_repl.py:315-325`）只读
     `registry.session(self.state.session_id)`——**当前这一个会话**的内存
     消息数，不是从 store 里列出全部会话；而且它打印的一行是
     `"Sessions are in-memory only in this build (plan 0031 Q4)."`
     （`_repl.py:323-325`，原文核对过）——**这句话在 `memory=True` 的默认
     部署下是错的**：memory 打开时用的是 `SqliteSessionStore`，不是
     `InMemorySessionStore`，这行提示是 0040（memory 接线）落地后没有回头
     修的残留。
  3. `SessionStore` Protocol 本来就有 `list(limit=50) ->
     Sequence[Session]`（`session.py:185`），`InMemorySessionStore` 与
     `SqliteSessionStore`（在 `omicsclaw/memory/` 里，`entry/memory.py:
     254-266` 构造）都满足这个接口——**列会话的能力已经在，只是没人在
     REPL 里调它**。
- **判据**：这是本次调研里**最典型的"B 类理由已过期"案例**。plan 0031
  Q4 的原始判断是「本步不建持久化，`SessionStore` 是 Protocol + 一个内存
  实现」（`docs/plans/0031-entry-layer.md:481-489`），这在 2026-09-19 是
  对的；但 plan 0040（memory 接线）已经把 `attach_sessions` 的默认值改成
  「这个 app 自己的库」，前提消失了，而 `_repl.py` 的 `/sessions` 分支
  没有跟着改——**代码里现在有一句过期的、方向错误的提示**。
- **规模**：中。需要：(a) 修正 `_sessions()` 的文案与行为，让它调
  `self._app.sessions._store.list()`（或给 `SessionRegistry` 加一个公开的
  `async def list_sessions()`，更干净）列出最近的几条，区分「这是持久化的」
  还是「这是内存的（memory=false 时）」；(b) 新增 `/resume [id]`：无参数时
  列出并提示按序号/ID 续接，有参数时直接把 `self.state.session_id` 换成
  给定 ID 并触发一次 `_session()` 式的预加载确认它存在；(c) 把
  `/resume` 加进 `REPL_SLASH_COMMAND_SPECS`。
- **可证伪验收标准**：(1) 用一个真实的 `SqliteSessionStore`（临时目录）
  跑两次 `run_once`，各用不同 `--session` id 留下历史，然后在第三次
  `oc cli` 交互会话里输入 `/sessions`，断言输出包含两个此前的 session id
  而不只是当前会话；(2) `/resume <id>` 之后紧跟一条用户消息，断言这条
  消息被追加到该 session 已持久化的历史之后（用 store 直接读出来验证），
  而不是开了一个新的空历史；(3) `memory=false` 时 `/sessions` 打印的提示
  文本明确说明「这次部署没有持久化」，且这句话与 `memory=true` 时的文本
  不同——用一条测试同时断言两种文案，防止再次出现「一句话覆盖两种真相」。

#### A-3【最该先做】Plan/Task 在 CLI 里不可见

- **harness9**：TUI 有专门的任务面板渲染
  `renderPlanLines`（`tui_view.go:87-139`）：标题行「done/total + N
  active」，逐条状态图标 `▶`/`✔`/`⊘`/`○`。每次 `plan_write` 成功
  （`EventToolResult`，`tui_update.go:641-646`）都会调
  `updatePlanBlock()`（`:1637-1649`）把最新快照追加进对话流。更进一步，
  harness9 有**自动继续执行**：`EventDone` 时若 `autoExecuting` 且还有未完成
  项，自动再发一条继续指令（`:670-706`），并有「连续 3 次 `EventDone`
  但完成数没涨」的卡死检测（`autoExecStuck`，`:685-701`）。
- **OmicsClaw**：`omicsclaw/planning/`（plan 0039）已经完整落地并接入主循环
  ——`AgentApp.plans: PlanBook | None`（`omicsclaw/entry/assembly.py:771`，
  由 `build_plan_book(config)` 在 `open_app` 里构造，`:967`），
  `PlanBook.for_session(session_id) -> PlanStore`
  （`omicsclaw/planning/book.py:67`），`PlanStore.read() -> tuple[PlanItem,
  ...]`（`omicsclaw/planning/plan.py:148`），以及现成的格式化函数
  `format_plan(items)`（`omicsclaw/planning/render.py:83`）。**但
  `entry/cli` 里没有任何代码引用 `self._app.plans`**——`/tasks`、`/plan`、
  `/approve-plan`、`/resume-task`、`/do-current-task` 五条都在 38 条目录里，
  一条都不在 9 条 `REPL_SLASH_COMMAND_SPECS` 里。`plan_write` 工具调用
  发生时，CLI 唯一能看到的是 `TextRenderer` 对 `TOOL_RESULT`
  的通用渲染（`omicsclaw/entry/render.py:241`、`:421`），跟任何其他工具
  调用长得一样，没有专门的任务快照展示。
- **判据**：**B 类理由已经明确过期**。0031 §5.1 对旧 CLI 的 Plan mode 支持
  给出的原始判断是「它只焊在第①族上，`entry` 落地后 4 行就能接回来；但
  plan 本身是 harness9 的独立包（`internal/planning`），**接回来属它自己
  那一步**」（`docs/plans/0031-entry-layer.md:1031`，原文核对过）。
  「它自己那一步」正是 0039，而 0039 已经交付。前提消失，裁定却没有人
  回头把 `/plan` `/tasks` 接上。
- **规模**：中。只读展示（`/plan`、`/tasks` 打印 `format_plan(book.
  for_session(session_id).read())` 的结果）是小工作量；「批准计划」
  （`/approve-plan`）与「聚焦/继续某个任务」（`/resume-task`、
  `/do-current-task`）在 OmicsClaw 里的语义还没有定义——0039 的设计是
  「planning 是原生能力，没有人为开关，只有一段 prompt 告诉模型什么时候该
  规划」（`docs/plans/0039-planning-layer.md`），跟 harness9 的
  「自动继续执行直到卡死检测」不是同一个模型，**这两条命令是否要做、做成
  什么语义需要 owner 先拍板**。**owner 已裁定（裁定 2）：保持「模型自己
  判断」，三条控制命令本路线下不做**，因此 A-3 永久收敛为只读可见性，
  只做 `/plan` `/tasks`。
- **可证伪验收标准**：(1) 一次真实回合里模型调用 `plan_write` 建了 3 条
  任务、其中 1 条标记 `in_progress`；紧接着在同一 session 里输入 `/tasks`，
  断言输出包含三条任务的文本与各自的状态词，且这段输出**不是**通用
  `TOOL_RESULT` 渲染格式（用字符串定位断言，不能是一模一样的 JSON 转储）；
  (2) 没有 `plan_write` 被调用过的空 session 里输入 `/tasks`，断言输出是
  「当前没有任务」一类的明确空状态，而不是异常或空字符串。

#### A-4【规模小、优先级较低】审批的「本次会话内始终允许」中间档

- **harness9**：审批对话框（`renderApprovalDialog`，`tui_view.go:
  467-491`；键盘处理 `handleApprovalKey`/`confirmApproval`，
  `tui_update.go:1652-1767`）有 **5 个选项**：允许一次、**本次会话内始终
  允许**、永久始终允许（写入 `.harness9/settings.json`，
  `writeApprovalToConfig`，`:1770-1799`）、拒绝、拒绝并附文字理由
  （自由文本子模式）。
- **OmicsClaw**：`_repl.py` 的 `_APPROVAL_PROMPT` 是三选一
  `[y/N/a=always]`（`_repl.py:101`、`:119-132`）——批准一次、拒绝、
  永久始终允许（写规则文件）。**没有"本次会话内始终允许、但不写盘"的
  中间档**。拒绝时的自由文本理由**已经等价支持**：任何非
  `y/yes/ok/allow/a/always` 的输入都会原样作为拒绝理由传回
  （`_ask`方法内 `ApprovalDecision(approved, "" if approved else
  answer.strip())`，`_repl.py:557-560`），这一点是 C 类（形态不同、能力
  等价），不算缺口。
- **判据**：plan 0038 §8.2 明确讨论过「二选一 → 三选一」的改动理由（补上
  「总是允许」这一档，因为原来完全不可达），但**没有讨论过要不要加会话
  内的中间档**——不是"讨论过但决定不做"，是"没被问到"。因此不是 B 类，
  是一条**未被评估过的小缺口**，规模小，优先级低于 A-1/A-2/A-3。
- **规模**：小。`ApprovalDecision` 已经是 `(approved: bool, reason: str)`
  的二元组（`omicsclaw/tools/context.py`，未在本文重新核实其定义行号，
  标注**未确证**），若要加"本次会话内"需要 REPL 自己维护一张
  `set[str]`（按工具名+参数模式）内存表，在 `_ask` 里先查这张表再问人——
  不需要改 `omicsclaw/tools/` 或 `omicsclaw/permission/` 的任何类型，
  与 plan 0038 §8.2「不给 `ApprovalDecision` 加 `remember` 字段」的既有
  裁定完全兼容（未确证的部分已标注）。
- **可证伪验收标准**：批准一个工具调用时选择"本次会话内始终允许"，
  同一 session 内对同一模式的下一次调用不再询问；`/new` 或进程重启后
  再次询问；且规则文件（`.omicsclaw/settings.json` 一类，未确证具体路径）
  没有被写入——用 mtime 或文件不存在来断言，与「a=always」那一档区分开。

#### A-5【已裁定要做，见裁定 3】`!` Shell 直通（`@` 子代理直跑仍被依赖挡住）

- **OmicsClaw**：两者都不存在。
- **`@` 子代理直跑**依赖尚不存在的子代理层
  （`docs/plans/0031-entry-layer.md` Q13 只留了接缝，未建），在子代理层
  交付前无法实现，**不属于本 plan**，与裁定 3 无关。
- **`!` 直通不构成安全模型上的缺口**——本来就是终端操作者自己在敲命令，
  他/她本来就对这台机器有 shell 访问权，`!ls` 并不比操作者直接开另一个
  终端窗口危险。owner 已裁定要做，成为 Task 6。

**harness9 的完整设计（本次逐行核实）**，以及哪些该抄、哪些不该：

| harness9 的做法 | 出处（已核实） | OmicsClaw 是否照抄 |
|---|---|---|
| `!` 前缀在输入分发的最前段截获，不显示 "▶ You:" 而显示 `$ cmd` | `tui_update.go:359-363` | **抄**。在 `Repl._dispatch` 里、`parse_slash_command` **之前**截获 |
| `bash -c <cmd>`，`cwd = workDir`，支持管道/重定向/`&&` | `tui_update.go:1600-1601` | **抄**。用 `workspace` 作 cwd |
| 固定 30s 超时（与它的 `bashHardTimeout` 对齐） | `tui_update.go:1598` | **抄"要有一个短上限"，不抄 30 这个数**——见下 |
| `CombinedOutput` 合并 stdout/stderr | `tui_update.go:1602` | **抄**。错误信息必须可见 |
| 交互式命令黑名单（13 个名字），命中则拒绝并提示去独立终端 | `tui_update.go:1567-1583` | **抄，但不依赖它**——见下 |
| 输出**双截断**：展示侧 4096 字节，注入 LLM 侧 2048 字节 | `tui_update.go:71`、`:77`、`:445-467` | **抄**。两个不同的上限是对的 |
| 输出以 `[用户执行的 Shell 命令记录]` 为头**前置注入下一次 prompt**，注入后立即清空 | `tui_update.go:1334-1345` | **抄**。模型需要知道操作者刚做了什么 |
| **完全不过审批门** | `tui_update.go:1622-1635` 全函数无 permission 调用 | **抄**。操作者审批自己敲的命令是表演 |

两处**明确不照抄**的地方：

1. **不抄 30s 这个数字，也不抄"固定"。** harness9 的 30s 对齐的是它自己
   的 `bashHardTimeout`；OmicsClaw 的对应物是
   `AppConfig.bash_timeout()`（`tool_timeout_s` 减去
   `ENGINE_TIMEOUT_MARGIN`，默认 585s），那是给 `spatial-deconv`、STAR
   比对这类分析留的，**对一个操作者盯着屏幕等的直通命令来说太长了**。
   Task 6 应引入一个**独立的、短的**上限（建议 60s，并说明它为什么与
   `tool_timeout_s` 无关），而不是复用任何一个现有常数。
2. **不把黑名单当作正确性保障。** `isInteractiveCmd` 只看第一个 token
   （`tui_update.go:1578-1582` 的 `strings.Fields(cmd)[0]`），所以
   `echo hi && vim`、`bash -c vim`、`git commit`（会拉起 `$EDITOR`）
   全都能绕过去。**一次漏判的代价正是这个 REPL 刚刚修好的那类故障——
   一个等 TTY 的程序把整个会话挂死。** 所以黑名单只当"友好提示"，
   **真正的保障是超时**：漏判的代价必须是等 N 秒后拿到一条超时信息，
   而不是会话卡死。这一条要写进实现的 docstring，否则下一个人会以为
   补全黑名单就够了。

### 3.2 B 类 —— 已记录的有意取舍，及是否过期

| # | 取舍 | 记录位置 | 今天是否仍成立 |
|---|---|---|---|
| B-1 | 不做 TUI，REPL 先行 | `docs/plans/0031-entry-layer.md:145`（§1.3）、`docs/FRAMEWORK-REBUILD.md:1444` | **仍成立**。原因不是排序问题而是耦合问题：旧 `tui.py`（1550 行）在模块作用域 import 9 个被封锁的 support 模块，且本机未装 `textual`（`omicsclaw/entry/cli/__init__.py:48-52`，原文核对过）。这不是"这一步还没轮到"，是"照抄旧 TUI 会把 12 个被封锁的模块家族一起拖进来"。**owner 已裁定不立项**（裁定 1），本条不再是待评估的债，而是不在路线上的代码。 |
| B-2 | 不做持久化（`SessionStore` 只有内存实现） | `docs/plans/0031-entry-layer.md:481-489`（Q4） | **已过期**，且已被 plan 0040 在结构上推翻——`attach_sessions` 默认用 app 自己的 `SqliteSessionStore`。**过期后没人回头改 `/sessions` 的文案和 `/resume` 的缺失**，就是 A-2。 |
| B-3 | Plan mode 挡住，等它自己的独立步骤 | `docs/plans/0031-entry-layer.md:1031`（§5.1） | **已过期**：「它自己的独立步骤」是 0039，已交付。没人回头接 `/plan` `/tasks`，就是 A-3。 |
| B-4 | 技能运行器/回放/流水线挡住，等 skill 重设计 | `docs/plans/0031-entry-layer.md:1032`（§5.1） | **部分过期，部分仍成立**——容易被错误合并成一条，必须拆开：0032（skill loader）已经解决了"目录/索引/`use_skill` 工具"这一半（`docs/FRAMEWORK-REBUILD.md:1553-1563` 明确说这条裁定"has lapsed"），**但 `/run <skill> --demo` 这种确定性执行（绕过 LLM、走 shared runner、产出 `result.json`/`reproducibility/replay.json`）依赖的是另一半——`RunRuntime`/shared runner 家族，这一半在 `entry/` 里完全不存在**（`grep -rn "RunRuntime" omicsclaw/entry/` 零命中，本文档核实过）。**不要把"技能索引能注入了"误判成"skill 运行器的阻塞理由也过期了"**——这是本文档特别要提醒下一个读者的一点，因为两条挡住的理由长得像，但依赖的是两个不同的家族。 |
| B-5 | MCP 管理只搬只读展示，不做增删改 | `omicsclaw/entry/cli/__init__.py:34-40`；`docs/plans/0037-launch-and-entry-points.md:225`（§5.3，"mcp add/remove → 配置文件"） | **仍成立**。这是一条独立、自洽的当前裁定（两套 MCP 管理系统只留一套），不是"等下一步"，本文档不建议推翻。harness9 的 MCP 面板有 `e`/`E` 打开 `$EDITOR` 编辑 `.mcp.json` 的快捷方式（`tui_update.go:1863-1864`）——这是一个**很小的、C 类式**的便利功能，可以在不推翻现有裁定的前提下补一个 `/mcp edit` 之类的命令，本文列为规模极小的可选项，不单独立项。 |
| B-6 | 审批三选一（不做四选一/五选一） | `docs/plans/0038-permission-layer.md:277-291`（§8.2） | **部分仍成立**：不加 `remember` 字段到 `ApprovalDecision`、`AgentApp.remember_approval` 放组合根——这些裁定本文档不建议动。但"要不要加会话内中间档"这个具体问题没有被这次讨论覆盖，见 A-4。 |
| B-7 | `_mcp.py`（旧模块）不整体移植 | `omicsclaw/entry/cli/__init__.py:34-40` | **仍成立**，理由本身（两套管理系统好过一套多一个界面）没有过期的前提。 |
| B-8 | `_session.py`（旧模块）不整体移植 | `omicsclaw/entry/cli/__init__.py:42-46` | **仍成立**：旧模块本身指向一个已删除的 584 行文件，移植旧模块字面上不可能；但它想解决的问题（会话管理 UI）现在应该按 A-2 的新形态解决，而不是等旧模块复活。 |

### 3.3 C 类 —— 形态不同、能力等价（记录映射，非缺口）

| harness9 | OmicsClaw | 说明 |
|---|---|---|
| `cli.go:36` `runCLI(ctx, eng, io.Reader, idx)`，reader 是参数 | `Repl(app, source=PromptSource)`（`omicsclaw/entry/cli/_repl.py:168-193`），source 是参数 | 同一设计思路，OmicsClaw 的 docstring 明确说"值得照抄"并照抄了（`_repl.py:12-15`）。 |
| `cli.go:27-33` `RunOnce` 把整个文件当一次 `userPrompt` | `--prompt-file` → `_read_prompt_file`（`omicsclaw/launch/_surfaces.py:294-306`）整份读入，空文件拒绝 | 同构，且 OmicsClaw 多了"空文件拒绝"这一条 harness9 没有的检查。 |
| `stream.go:51-58` 审批消费者契约（UI 必须在展示对话框时继续消费事件） | `Repl._ask_human` 用独立 Task 处理审批，pump 不停（`_repl.py:30-45`、`:478-485`） | 同构，且 OmicsClaw 在 Python 里把这一点做得更严格（详见 CLAUDE.md What's New 的死锁修复记录）。 |
| 审批对话框单请求假设：`m.approvalRequest` 是单个字段，`readNextEvent` 在审批期间不被再次调用，结构性保证一次只有一个请求在飞（`tui_update.go:574-575`，未确证是否有显式排队/互斥，只确证了"未再次消费事件"这个结构性理由） | OmicsClaw **反而支持**并发多个审批请求（各自独立 Task），只是共享的终端设备把它们串行化成"连续两张卡片"（`_input.py` 模块 docstring，`_repl.py:101-117` 的 `_card` 编号机制） | OmicsClaw 的设计**比 harness9 更强**：harness9 结构性地一次只有一个审批在飞；OmicsClaw 允许多个审批同时在飞（对应"一条模型消息两个并发安全工具都要审批"的场景），只是终端展示上排队。这是 OmicsClaw 优于参考实现之处，不是缺口。 |
| TUI 状态栏的 token/百分比展示（`tui_view.go:210-287`） | `/usage` 命令按需打印累计 in/out token（`_repl.py:263-268`） | **不是纯粹的形态差异，而是被 B-1（无 TUI）蕴含的差距**：常驻状态栏本质上需要一个持续渲染的界面，行式 REPL 结构性做不到。等 TUI 立项时应重新评估，不建议现在给 REPL 硬做一个假状态栏。 |
| harness9 的 TUI 输入框是单行 `bubbles/textinput.Model`（`tui.go:16,163,314-317`），**harness9 自己也没有多行输入/粘贴优化/拖拽附件** | OmicsClaw 的 `PromptToolkitSource` 同样是单行 prompt（`_input.py:192-230`） | 两边一致，不是缺口，只是澄清"多行输入"不在 harness9 的能力范围内，不要凭空对标一个参考实现没有的东西。 |
| `upgrade.go` 自升级：查 GitHub Releases、下载 tar.gz、SHA256 校验（失败会跳过而不是拒绝，`upgrade.go:93-102`）、原地替换二进制 | 无 | 见 §3.4，明确建议不抄。 |

### 3.4 harness9 有但不建议抄

**自升级机制（`upgrade.go`，312 行全文读过）**。理由：

1. **分发模型完全不同**。harness9 是单个 Go 静态二进制，"下载新二进制→
   原地 rename 替换"是这类分发形态的标准做法。OmicsClaw 走 pip / conda /
   npm 三条通道（README「npm install & Desktop pairing」一节），每条通道
   都已经有自己的升级机制（`pip install --upgrade`、
   `npm install -g omicsclaw@latest`、`conda update`），一个应用层的
   "自己下载自己替换自己"命令在这些通道之上是重复建设。
2. **它自己的安全实践也不值得照抄**：校验文件下载失败时是"警告后跳过校验,
   继续用未校验的二进制替换正在运行的程序"（`upgrade.go:93-102`，原文
   `"警告：无法下载校验文件，跳过 SHA256 校验"`），这是一个已知的"静默降级
   成不安全路径"模式，CLAUDE.md 的安全规则第一条就是本机数据不外泄，一个
   校验可跳过的自替换机制与这条精神相悖。
3. **没有自动重启**：替换完二进制就返回，不 re-exec；这意味着即使抄了，
   用户体验也不会比"提示一行 `pip install -U omicsclaw` 然后退出"更好。

**建议**：`oc doctor`（面内命令，规划中）里加一行"当前版本 vs PyPI/npm
最新版本"的只读提示即可，不做替换二进制的动作。这条不建议列为任务，只是
明确记录"调研过，决定不抄"，避免下一个人重新调研一遍。

---

## 4. 判断：为什么这三项排在最前面

A-1（`/compact`）、A-2（会话发现）、A-3（Plan 可见性）三项排在最前面，
不是因为它们是"最像 harness9"的三项，而是因为它们共享同一个特征：**底层
能力已经存在，只是 CLI 这一层没有把接线接上**。

- `/compact` 的引擎侧压缩机制（0035）已经跑在每次模型调用之前，只是没有
  一个用户可以主动触发的命令。
- 会话持久化（0040）已经是默认行为，只是 `/sessions` 还在报告一个已经不
  真实的"纯内存"状态，`/resume` 完全没有入口。
- Plan 引擎（0039）已经把每一次 `plan_write` 都写进
  `<workspace>/.omicsclaw/plans/`，只是 CLI 从来没有读过这个目录。

三项加起来的实现成本（§3.1 的规模估计：小/中/中）远低于"重新设计一个能力"
——它们是**总账最便宜、价值最高**的一批。相比之下，A-4（审批中间档）和
A-5 的两半境遇不同：`!` 直通经裁定 3 成为 Task 6，`@` 子代理直跑依赖
不存在的层，仍不排期。

B 类里最有价值的发现是 B-3（Plan mode 挡住的理由已过期）和 B-2（持久化
挡住的理由已过期）——它们直接对应 A-3 和 A-2，说明"理由过期后没人回头看"
在本仓库不是孤立事件，而是这次框架重建里重复出现的一种模式（0031 §5.1
自己也在 §5.4「改判的那 4 项」里承认过一次类似的教训）。**这提示一个流程
问题，不只是代码问题**：一条「等下一步」的裁定没有任何机制在那一步交付时
回头通知它，于是理由过期而代码不动。

---

## 5. 分阶段任务

### Task 1（小，依赖：无）—— 修正 `/sessions` 的过期文案

`_repl.py:323-325` 那句 "Sessions are in-memory only in this build
(plan 0031 Q4)" 在 `memory=True`（默认值）时是错的。这是一个纯粹的
bug-fix，独立于 A-2 的其余部分，应该最先做、单独提交。

**验收标准**：`build_app` 用 `memory=True` 装配后，`/sessions` 的输出
不包含"in-memory only"字样；`memory=False` 装配后，输出明确说明这次
部署没有持久化。两种情况各有一条测试。

### Task 2（中，依赖：Task 1）—— `/resume` 与会话列表

按 A-2 的规模估计实现。建议顺序：先给 `SessionRegistry` 加
`async def list_sessions(limit=10) -> Sequence[Session]`（薄包装
`self._store.list(limit)`），再让 `/sessions` 调用它列出多条，最后加
`/resume [id]`。

**验收标准**：A-2 的三条（§3.1），外加裁定 4 带来的第 4 条——

4. `SqliteSessionStore.list` 的 docstring 明确写出"作用域是数据库文件
   本身，本方法不做任何隔离"，并且有一条测试断言：同一个
   `SqliteSessionStore` 上写入的两个 session，`list()` 都能看见（即
   证明这里**确实没有**隐式过滤，把"文件即边界"变成一条被测事实而不是
   一句注释）。反向的那一半——"两个不同 workspace 的会话互不可见"——
   由 `memory_db_path` 已有的测试覆盖，不在本任务重复。

### Task 3（小，依赖：无，可与 Task 2 并行）—— `/compact`

按 A-1 的规模估计实现。

**验收标准**：见 A-1 的可证伪验收标准（§3.1）。

### Task 4（中，依赖：无，但建议在 Task 2 之后做，复用其渲染经验）
—— `/plan` 与 `/tasks` 只读展示

按 A-3 的规模估计实现，**只做只读部分**（列出当前任务与状态）。按**裁定
1**，行式输出就是最终形态，不是等 TUI 的临时方案，可读性要自己站得住。
按**裁定 2**，`/approve-plan`、`/resume-task`、`/do-current-task`
**本路线下不做**——不再是"待 owner 决定语义"，实现者不必为它们预留接缝。

**验收标准**：见 A-3 的两条可证伪验收标准（§3.1）。

### Task 5（小，依赖：无，优先级最低）—— 审批"本次会话内始终允许"

按 A-4 的规模估计实现。

**验收标准**：见 A-4 的可证伪验收标准（§3.1）。

### Task 6（中，依赖：无，可与 Task 2-5 任一并行）—— `!` Shell 直通

按裁定 3 与 A-5 的表格实现。落点是 `Repl._dispatch`：在
`parse_slash_command` **之前**截获 `!` 前缀，因为 `!` 不是 slash 命令，
不该进那张目录。

**可证伪验收标准**（五条，全部可自动化）：

1. `!echo hi` 在屏幕上出现 `$ echo hi` 与 `hi`，且**不经过任何一次模型
   调用**——用 scripted provider 的 `calls == 0` 断言，与"把它当普通
   问题发给模型"区分开。
2. `!` 后接空串（只敲一个 `!`）不执行任何东西、不报错，直接回到提示符。
3. 一条**超过展示上限**的输出在屏幕上被截断并带截断提示，而注入模型的
   那一份被截到**更小的**上限——两个上限必须能被分别断言，一个测试同时
   读屏幕缓冲与下一次请求的 prompt，证明它们不是同一个数。
4. 一次 `!cmd` 之后的**下一次**提问，其 prompt 前置包含该命令与输出；
   **再下一次**提问不再包含（注入后清空，不重复注入）。这条是这个功能
   最容易写错的地方——harness9 自己用一条注释专门交代
   （`tui_update.go:1333`）。
5. 一条**会永远等 TTY 的命令**（用一个读 stdin 且不会返回的命令构造，
   不要用黑名单里的名字，否则测的是黑名单不是超时）在上限时间后被杀掉，
   REPL 回到提示符并报告超时。**这是本任务唯一的硬安全性验收标准**：
   它证明漏判黑名单的代价是等 N 秒，而不是会话卡死。

**不在本任务内**：`@` 子代理直跑（依赖子代理层，尚不存在）。

### 不建议列为任务的项

- TUI 移植（B-1）——**owner 已裁定不立项**（裁定 1），不再是本文档的判断。
- `@` 子代理直跑——依赖尚不存在的子代理层，不是 CLI 这一层能补的。
- `/approve-plan`、`/resume-task`、`/do-current-task`——**owner 已裁定
  本路线下不做**（裁定 2）。
- 常驻状态栏式 token 展示——被裁定 1 关闭，`/usage` 即最终答案。
- 自升级机制——见 §3.4，明确建议不抄。
- 把 harness9 的 `sessions.db` 放 home 的做法——见裁定 4，明确拒绝。
- MCP `$EDITOR` 快捷编辑——价值/成本比低于以上六项，可作为 Task 2-6
  完成后的顺手项，不单独排期。

---

## 6. 风险与陷阱

1. **不要把 B-4 的两半合并成一条。** 0032 让技能索引可以注入，不代表
   "整个技能运行器家族"都解封了；`/run` 依赖的 `RunRuntime`/shared runner
   在 `entry/` 里不存在，贸然实现一个"轻量版 `/run`"很容易绕开 CLAUDE.md
   要求的 `result.json`/`replay.json` 契约，产生一条不受治理的执行路径。
   本 plan 不包含任何 `/run` 相关任务。
2. **`/resume` 的隔离边界是数据库文件，不是查询——已查清，不再是阻断项。**
   裁定 4 已确认：`sessions` 表没有 owner/scope 列
   （`omicsclaw/memory/database.py:18-25`），`list()` 也没有 `WHERE`
   （`sessions.py:99`），隔离**完全**来自 `build_app` 打开了
   `<workspace>/.omicsclaw/memory.db`。对今天的 CLI（一进程一 workspace）
   这是安全的，Task 2 不被阻断。**残留的真实风险在别处**：哪一天某个
   面向多人的 Surface 共享一个 `memory.db` 又拿到了 `/resume`，会话就会
   跨用户泄漏，而代码里没有任何东西会拦住它——`list()` 看起来像一个
   隔离点，实际上不是。Task 2 的验收标准第 4 条要求把这件事写进
   docstring 并用测试钉住，就是为了让下一个人在加 Channel `/resume`
   之前先撞上它。**不要**为此给 CLI 加一层按 workspace 的过滤：文件已经
   是边界，再加一层只会把同一个事实表达两遍，并让人误以为过滤才是边界。
3. **Task 4 的"只读优先"必须真的只读。** `plan_write` 工具本身有"不许
   一次把没做过的任务标记完成"等防作弊校验（0039 §2.5），CLI 侧新增的
   `/plan`/`/tasks` 命令只应该读 `PlanStore.read()`，不应该提供任何
   反向写入路径，否则等于在工具校验之外开了一个后门。
4. **三个测试环境细节**（沿用 0031/0037 已踩过的坑，直接抄过来）：
   解释器用 `/opt/conda/envs/rapids_singlecell/bin/python`（3.13.11，
   系统默认 `python3` 是 3.10.14）；`pytest-asyncio` 未装，异步测试用
   `asyncio.run` 驱动；变异测试必须带 `-rfE
   --continue-on-collection-errors`，否则破坏 import 的变异会被漏判为
   "存活"。

---

## 7. 整体验收标准

1. `tests/entry/` 与 `tests/launch/` 现有用例一个不少、一个不改（新增
   用例除外）。
2. 每个 Task 各自的可证伪验收标准（§5）全部满足。
3. 真进程冒烟（沿用 plan 0037 §8-4 的形式）：`oc cli` 喂一段包含
   `/compact`、`/sessions`、`/resume <前一次的 id>`、`/tasks`、
   `!echo hi` 的脚本，真实跑通不崩溃，退出码 0。
4. `README.md` 的 CLI Reference 与 `AGENTS.md` 的"Slash Commands"表
   （目前描述的是旧 CLI 的 35 个子命令与 `/delete` 等旧命令）更新为反映
   `entry/cli` 的真实命令集——按 SPEC.md 的纪律，功能变化必须同步文档。

---

## 8. owner 裁定（已批复）

原 §8 的四条开放问题已由 owner 裁定。裁定原文记录在此，后续实现不得
以"文档没写清楚"为由重新解释；若要推翻，需要一条新的裁定而不是一次
重新讨论。

### 裁定 1 —— TUI 不立项，CLI 就足够

> "TUI 不要现在立项，CLI 就足够了"

这把 B-1 从"本文档的判断"升格为 **owner 的裁定**，并且把 §5 全部任务的
工作假设钉死为 **"REPL 长期是唯一界面"**，而不是"REPL 是 TUI 落地前的
过渡"。三条直接后果：

- **Task 4（`/plan` `/tasks`）应该按"这就是最终形态"来做**，而不是按
  "先凑合，等 TUI 再好好做"。行式输出要自己站得住：任务状态要一眼可读，
  不依赖一个将来才有的常驻面板。
- **C 类里那条常驻状态栏式 token 展示（`tui_view.go:210-287`）正式关闭**，
  不再是"等 TUI 立项时重新评估"，而是"本路线下不做"。`/usage` 的按需
  打印就是 OmicsClaw 在这条上的最终答案。
- **B-1 的解封成本论证不必再维护**。旧 `tui.py` 与它拖带的 12 个被封锁
  模块家族不再是"待评估的债"，而是**不在路线上的代码**。

### 裁定 2 —— Plan mode 保持"模型自己判断"，三个控制命令不做

> "参考 harness9，让模型自己判断是否需要进入 plan 模式，暂时不需要做
> `/approve-plan`、`/resume-task`、`/do-current-task`"

这条裁定与两边的现状是**一致的而非折中的**，值得写清楚，免得下一个人以为
这里做了取舍：plan 0039 的模型是"没有开关，只有一段 prompt 告诉模型什么
任务值得规划"，而 harness9 **同样移除了 plan mode 开关**（`README.md`
What's New 0039 条目记录："matching the reference harness, which removed
exactly such a mode"）。所以"参考 harness9"与"保持 0039 现状"指向同一个
结果，不存在需要调和的分歧。

后果：**A-3 永久收敛为只读可见性**。Task 4 只实现"看得见当前计划与任务
状态"，不实现任何人工推进/批准的控制面。三个控制命令从"待 owner 决定
语义"变成 **"本路线下不做"**，§5「不建议列为任务的项」相应更新。

### 裁定 3 —— `!` shell 直通要做

> "`!` shell 直通要做"

A-5 因此**从开放问题升格为任务**，即新增的 Task 6（§5）。设计细节与
harness9 的可抄/不可抄之处见 §3.1 A-5 的改写版本。

### 裁定 4 —— `SessionStore.list()` 隔离粒度：参考 harness9，其方案不成立时用本文建议

> "`SessionStore.list()` 的隔离粒度参考 harness9 的方案，如果那方案没有
> 准确的解决方式，则按照你建议的方案来"

**harness9 的方案已核实，且不成立**，因此按裁定的后半句执行。核实结论：

- harness9 的 `ListSessions` **没有任何隔离**——`SELECT s.id, ... FROM
  sessions s LEFT JOIN messages ... GROUP BY s.id ORDER BY s.updated_at
  DESC`，无 `WHERE`、无 scope 列（`internal/memory/manager.go:129-136`，
  本次亲自打开核实）。
- 它唯一的边界是**打开了哪个数据库文件**，而那个文件在
  **`homeDir/.harness9/sessions.db`**（`cmd/harness9/main.go:232-233`，
  亲自核实），即**按机器用户**隔离，不按项目目录。
- 所以 harness9 的 `/resume` 会把这台机器上**所有项目目录**的历史会话
  混在一张列表里。它自己甚至不自洽：同一次 main 装配里
  `tool_results` 是按 workdir 的（`main.go:230`），
  `compaction_records` 和 `sessions.db` 却是按 home 的
  （`main.go:231`、`main.go:233`）——一次会话的状态被劈成两个粒度。

**这不是一个可以抄的方案，是一个应当明确拒绝的方案。** 采用本文建议：

- **作用域 = 数据库文件本身**，而 OmicsClaw 的数据库在
  `<workspace>/.omicsclaw/memory.db`（`omicsclaw/entry/memory.py:103-109`
  的 `memory_db_path`，亲自核实）。这已经是**按 workspace 隔离**，
  比 harness9 的按 home **严格更强**，Task 2 不需要为 CLI 场景补任何
  过滤。
- **`SqliteSessionStore.list()` 保持无 `WHERE`**（`sessions.py:99`）是
  **正确的**，不是待修的缺陷：文件就是边界，在边界内再加一层按
  workspace 的过滤只会把同一个事实表达两遍，并让人误以为过滤才是边界。
- **但必须把"`list()` 不是隔离机制"写进它自己的 docstring。** `sessions`
  表没有 owner/scope 列（`omicsclaw/memory/database.py:18-25`，亲自核实），
  所以隔离**完全**来自 `build_app` 打开了哪个路径。今天 CLI 一个进程
  一个 workspace，这是安全的；**一旦某个面向多人的 Surface（Channel /
  Desktop 多用户）共享同一个 `memory.db` 又拿到了 `/resume`，会话就会
  跨用户泄漏**，而代码里没有任何东西会拦住它。这条约束的落点见 Task 2
  的验收标准第 4 条。

### 仍然有效的证据链声明（非开放问题）

**本文档的证据链有一处已声明的退让**（§0）：三段 harness9 侧的读码
工作由并行 subagent 完成，协调者复核了其中与 OmicsClaw 已有决策
（`docs/plans/0031-entry-layer.md` 附录 A）重叠的行号（`main.go:453-468`、
`cli.go` 全文、`tui.go`/`tui_update.go` 的两条结构性引用）——这些
**互相印证、结论一致**；但 `tui_update.go`/`tui_view.go` 里 fork 报告的
大量具体行号（例如 `renderPlanLines` 的精确图标）**未逐行重新打开确认**。

**裁定批复时的补充核实（2026-09-20）**：为落实裁定 3 与裁定 4，又亲自
打开确认了以下各处，均与原文一致：`manager.go:129-136`（`ListSessions`
无 `WHERE`）、`main.go:230-233`（三个状态目录的粒度不一致）、
`tui_update.go:1567-1583`（`interactiveCmds` 与 `isInteractiveCmd`）、
`tui_update.go:1595-1610`（`runShellCmd`）、`tui_update.go:1612-1635`
（`dispatchShellCommand`）、`tui_update.go:359-363`（`!` 分发点）、
`tui_update.go:445-467`（`shellResultMsg` 的双截断）、
`tui_update.go:1334-1345`（`pendingShellOutput` 注入 prompt）、
`tui_update.go:71/77`（两个长度上限）、`tui_update.go:1652-1682`
（`handleApprovalKey`，光标范围 0..4 确为 5 档）、
`tui_update.go:382-384`（`/resume` → `handleResumeList`）、
`tui_update.go:1409-1421`（`handleResumeList`）。抽查的另外 8 处
OmicsClaw 侧引用（`session.py:383`、`config.py:255`、`_repl.py:324`、
`assembly.py:771`、`FRAMEWORK-REBUILD.md:946` 等）亦全部准确。

**仍未覆盖的部分**：`tui_view.go` 的渲染细节（图标、颜色分级的精确行号）
没有逐条复核。如果 Task 4 要精确复刻 harness9 的某个渲染细节，实现者
应该自己重新打开对应文件确认，不要把本文档的引用当成不需要复核的事实
——这正是仓库自己记录过的教训（README What's New 提到的
"25 处引用 7 处行号错"）。
