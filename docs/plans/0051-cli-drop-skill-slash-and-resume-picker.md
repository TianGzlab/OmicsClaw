# 计划 0051 — CLI 去掉 `/skill-name` 快捷入口；`/resume` 改为方向键选择

**状态**：**已实现**（2026-09-23）。初稿经一轮独立只读审核（"需修改后实施"，
3 条必须修正、8 条建议），owner 对 Q1–Q7 全部裁定（§9），据此返工后实现。
验证：重建栈整套 **5072 passed, 12 skipped**，0 失败；14 个定点变异全部被捕获；
pty 中的真实 `oc cli` 验收通过（§11）。

**缘起**（owner，2026-09-23）：

1. `oc cli` 里敲 `/` 弹出的补全菜单被 94 个 `/skill-name` 淹没，命令反而找不到。
   skill 在当前架构下由模型按系统提示里的索引 + `use_skill` 自行选用，用户在
   请求里提到关键词即可，`/skill-name` 这条"用户直选"路径不必保留。
2. `/resume` 不带参数时只打印列表，再让人手敲 `/resume <id|编号>`，易用性差；
   应当能直接**选**。

---

## 1. 目标

| 输入 | 现在 | 改后 |
|---|---|---|
| 在提示符敲 `/` | 14 个命令 + 94 个 skill | 只有 14 个命令 |
| `/data/ru` + Tab | 什么都不补（被斜杠命令分支截走） | 首个 token 含第二个 `/` 时走路径补全（§3.1） |
| `/spatial-de 比较两组` | skill 正文作为 prompt 发给模型 | **不发给模型**；报告"没有这个命令"，并提示直接描述任务（§3.2） |
| `/data/run7/x.h5ad 看看这个` | 发给模型 | 不变 |
| `/skills [query]` | 列出 skill，提示"用 `/<name>` 运行" | 保留；列表不再带 `/`，提示改为"在请求里提到它，或直接描述任务" |
| `/resume`（终端、prompt_toolkit ≥ 3.0.52） | 打印列表 + "请输入 /resume <id>" | **方向键选择器**：↑/↓ 移动，Enter 恢复，Esc / Ctrl-C 取消 |
| `/resume`（管道、脚本、旧 prompt_toolkit） | 打印列表 + 提示 | 不变（§3.4：不能吞掉下一行输入） |
| `/resume <id>`、`/resume <编号>` | 可用 | 不变 |
| `/sessions`、`/resume` 的列表顺序 | SQLite 按**创建**时间倒序 | 按**最近活动**倒序（§3.5） |
| 列表每行 | id、消息数、创建时间 | id、消息数、**最近活动**时间、**首条用户消息预览** |
| 恢复成功后 | `Resumed X: N message(s).` | 另回显上一轮的用户问题与助手回答各一行 |
| 对话进行中按 Ctrl-C | **已失效**：第一次提示之后就取消不了（§2、§3.7） | 取消当前对话（Q7） |

## 2. 现状（读代码与实测得到的事实）

- `/skill-name` 只有 CLI 在用：`_repl.py` 的 `_skill_invocation`（分发）、
  `_input.py` 的 `build_completer`（补全里的 skill 分支）、`_repl.py` 的
  `_unknown_slash`（用 skill 索引给"did you mean"）。三者都依赖
  `omicsclaw/skills/invocation.py`。channel、desktop、subagent 均不引用（审核复核）。
  这条路径是计划 0045 为对齐参照实现而有意加入的；本计划按 owner 裁定撤回，模型侧
  `use_skill` 不受影响。
- `SessionRegistry.list_sessions(limit)` 返回完整 `Session`（含 `history`），只有 CLI
  调用它。`SqliteSessionStore._list` 按 `created_at DESC`（`memory/sessions.py:211`）；
  `InMemorySessionStore.save` 做 `move_to_end`（`entry/session.py:223`），**实际按
  最后保存排序**——两个 store 现在就不一致。`sessions` 表**已有** `updated_at` 列，
  每次保存都写 `time.time()`（`memory/sessions.py:164-175`），只是没被读回、也没用于排序。
  所以改排序**不需要迁移**。
- 压缩写回的历史里，摘要本身是一条 **user** 消息，以 `COMPACTION_MARKER`
  （`[Context Compaction]`）开头（`context/summary.py:251-275`，判定函数
  `is_summary_message`）。压缩过的会话，"第一条 user 消息"就是这串标记。
- `shell_preamble` 的结构是 `HEADER\n` + 记录（以 `\n---\n` 连接）+ `\n\n` + 问题
  （`_shell.py:250-260`），命令输出自身可能含空行。
- prompt_toolkit 3.0.52 起有 `ChoiceInput`（`prompt_async()` 无参数，没有
  `input`/`output` 参数，使用当前 app session）。已用 pipe 输入实测：↓+Enter、
  `j`+Enter、数字键、Ctrl-C、`eager` 绑定的 Esc 均符合预期。RadioList 超宽时**截断
  而非折行**，自带左边距 3、符号 `>`、编号 `N.`、右边距 1。
- **Ctrl-C 已失效（审核 M1，已复现）。** `_interrupts` 用
  `loop.add_signal_handler(SIGINT, …)` 安装（`launch/_surfaces.py:778-823`）；
  prompt_toolkit 的 `Application.run_async(handle_sigint=True)`（默认）会自己
  `add_signal_handler`，退出时 `remove_signal_handler(SIGINT)`
  （`prompt_toolkit/application/application.py:807-822`）——REPL 的那条被覆盖且不再恢复。
  `PromptToolkitSource.read` 没传 `handle_sigint=False`，所以**第一次读提示之后**，
  对话中按 Ctrl-C 就没有任何效果（审核在 pty 里跑真实 `oc cli` 复现：spinner 一直
  显示 "ctrl-c to interrupt"，对话不取消）。`ChoiceInput.prompt_async()` 无法关掉
  `handle_sigint`，选择器会再触发一次。而 Python 级 `signal.signal` 的处理器会被
  prompt_toolkit 保存并恢复（`_restore_sigint_from_ctypes`），连续跑 PromptSession 与
  ChoiceInput 后仍能触发（已复现）。

## 3. 设计

### 3.1 去掉 skill 的斜杠入口

- `_repl.py`：删 `_skill_invocation` 及其调用；`_dispatch` 变为
  `!` → 命令表 → 未知 `/name` 报告 → 发给模型。
- `_input.py`：`build_completer(*, specs=...)` 去掉 `skills` 参数与 skill 分支；
  `open_prompt_source(*, stream=None, interactive=None)` 去掉 `skills` 参数；删
  `_NO_SKILLS`。调用方 `launch/_surfaces.py:719` 改为 `open_prompt_source()`。
- 补全的斜杠分支只在 `slash_token(text)` 非空（首个 token 不含第二个 `/`）时生效，
  否则落到路径补全，这样 `/data/ru<Tab>` 能补出路径（审核 O2）。
- **删除** `omicsclaw/skills/invocation.py` 与 `tests/skills/test_invocation.py`；
  `omicsclaw/skills/__init__.py` 去掉 5 个导出；`tests/skills/test_skills_is_a_leaf_layer.py`
  的导出清单同步。
- `slash_token`（"首个 token 含 `/` 或 `\` 就不是名字"）仍需要——它决定
  `/data/run7/x.h5ad` 走模型——迁入 `_slash_command_support.py`，原
  `test_invocation.py` 中它的参数化用例迁到 CLI 测试。

### 3.2 未知的 `/name`

- 文案改为 `No command named /x.`，下一行 `/help lists the commands.`。
- **不做**命令名近似匹配（审核 O5：只有 14 个命令，`/help` 已列全，owner 未要求）。
- 若 token（忽略大小写）恰好是某个 skill 的名字——旧习惯 `/spatial-de …`——多打一行：
  `Skills are picked by the agent: describe the task (e.g. "use spatial-de to …"); /skills lists them.`
  只提示，不代为发送（Q3）。判断用 `SkillIndex.get` 加大小写折叠，不再需要
  `invocation.py`。

### 3.3 `/skills`

保留（Q1）。输出头改为 `N skill(s) — mention one in your request, or just describe the task:`，
每行打印 `name`（不带 `/`）。检索逻辑不变。

### 3.4 `/resume` 选择器

**能力探测，不扩大 `PromptSource` 协议。** `_input.py` 新增内部的
`runtime_checkable` 协议 `ChoiceSource`（不从包导出，审核 O1）：

```python
async def choose(self, message: str, options: Sequence[str], *, default: int = 0) -> int | None
```

返回所选下标；`None` 表示取消（Esc、Ctrl-C）；源已关闭抛 `EOFError`；当前
prompt_toolkit 没有 `ChoiceInput` 时抛 `NotImplementedError`。

只有 `PromptToolkitSource` 实现：持 `_reading` 锁；在
`create_app_session(input=self._session.input, output=self._session.output)` 里运行
`ChoiceInput`（审核 S4：保证与 PromptSession 同一终端，测试也借此注入 pipe）；
Esc 用 `eager=True` 绑定、Ctrl-C 用 `interrupt_exception`，都映射成取消。

`StreamSource` / `ScriptedSource` 不实现：若 `/resume` 改为"读下一行当编号"，
`oc cli < script.txt` 会吞掉脚本的下一句，所以它们保持"列表 + 提示"。

**REPL 侧 `_resume("")`：**

1. 取 `list_sessions(SESSION_LIST_LIMIT)`。为空 → `No saved conversations to resume.`
   （非持久部署另说明不落盘）。只有当前会话一条 → `No other conversation to resume.`，
   不弹只有一项的选择器（审核 S8）。
2. 源是 `ChoiceSource` → 调 `choose`：
   - 选中当前会话 → `Already in <id>.`，不切换；
   - `None` 或 `EOFError` → `Resume cancelled.`，不切换，循环继续（EOF 由下一次
     `read` 正常结束循环）；
   - `NotImplementedError` → **debug** 级日志，回退到第 3 步（旧版属预期，不能用
     `_log.exception`，否则会经 `terminal_owned_logging` 在退出时回放到 stderr，
     审核 S8）；
   - 其他异常 → `_log.exception`，回退到第 3 步。REPL 不能因选择器失败而退出。
3. 否则（或回退）→ 打印 `/sessions` 列表与提示 `/resume <id> or /resume <number>`。
4. 选中后与 `/resume <id>` 走**同一个** `_switch_to(session)`：改 `state.session_id`、
   清 `state.messages`、清 `_plan_shown`、打印结果与回显。

**行格式**（一个格式化函数，`/sessions` 带序号，选择器不带——RadioList 自己编号，
审核 S3）：

```
/sessions:   3. a1b2c3d4  (current)  2026-09-23 14:02  12 message(s)  比较肿瘤与间质区域…
选择器:        a1b2c3d4  (current)  2026-09-23 14:02  12 message(s)  比较肿瘤与间质区域…
```

- `(current)` 放在预览**之前**，截断只影响预览（审核 S3）。时间用完整年月日
  （审核 O3），为**最近活动**时间（§3.5）；`N message(s)` 保持现有措辞。
- **预览**：history 中第一条**非摘要**（`not is_summary_message(m)`）的 `USER` 消息
  （审核 M3）；若以 `SHELL_RECORD_HEADER` 开头，取 `content.rpartition("\n\n")[2]`
  （审核 S2：输出本身可能含空行，`partition` 会拿到输出残片）；空白折叠成单空格；
  没有可用的用户消息 → `(no messages)`。压缩过的会话因此显示压缩后保留下来的
  最早一条真实提问。
- **宽度**：按显示宽度截断（`rich.cells`，中文两列），加 `…`。可用宽度 =
  `screen.console.width` − 固定列 − 选择器边框（左边距 3 + 符号 + 编号 + 右边距 1，
  取 8 列）；终端太窄时预览可为空，但 id 与 `(current)` 不被截。
- 选项作为纯字符串交给 `ChoiceInput`；`/sessions` 与回显用 `rich.text.Text` 打印，
  会话内容里的 `<`、`[red]` 原样显示。
- 默认光标停在第一个非当前会话；当前会话仍列出，编号与 `/sessions`、
  `/resume <编号>` 一致。

**恢复后回显**（Q5）：在 `Resumed X: N message(s).` 下以 dim 样式各打一行：

```
  you: 比较肿瘤与间质区域的差异表达基因…
  agent: 已完成 spatial-de 分析，共 312 个显著基因…
```

取最后一条非摘要 `USER` 消息与最后一条文本非空的 `ASSISTANT` 消息，用同一个清洗
函数（跳过摘要、剥 shell 前导、折叠空白、按宽度截断）。任一缺失则不打该行。

### 3.5 按最近活动排序（Q4）

- `Session`（`entry/session.py`）与 `StoredSession`（`memory/record.py`）各加
  `updated_at: float`（默认 `time.time()`，放在字段末尾，保持二者逐字段兼容）。
- **由注册表打时间戳**：`SessionRegistry` 在保存前（`entry/session.py:800`）设
  `session.updated_at = time.time()`；store 只负责存取，不再自己取时钟。
  取消、失败的对话同样保存，也算一次活动——与现在 SQLite 每次保存都刷新
  `updated_at` 的行为一致。只 `/resume`、不说话不会保存，不改变排序。
- `SqliteSessionStore`：`_save` 写 `session.updated_at`；`_load` 读回；`_list` 改为
  `ORDER BY updated_at DESC, created_at DESC`。
- `InMemorySessionStore.list` 按 `updated_at` 倒序排序（不再依赖插入顺序）。
- `SessionStore.list`、`SqliteSessionStore.list`、`SessionRegistry.list_sessions`
  的 docstring 改为"最近活动的在前"。
- `tests/memory/test_sessions.py:155-160` 由钉住创建顺序改为钉住活动顺序。

### 3.6 帮助文案

`_REPL_DESCRIPTIONS["/resume"]` 改为
`Continue an earlier conversation: pick from a list, or /resume <id|number>`。

### 3.7 Ctrl-C 修复（Q7，owner 裁定并入）

`_interrupts` 改用 `signal.signal(SIGINT, handler)`，`handler` 只做
`loop.call_soon_threadsafe(self._fire)`——真正取消 Task 的动作仍在事件循环上执行，
满足计划 0031 陷阱 10 的要求。`__enter__` 保存 `signal.getsignal(SIGINT)`，
`__exit__` 恢复它（`asyncio.Runner` 自己也装了一个）。prompt_toolkit 会保存并恢复
Python 级处理器，所以 `read` 与 `choose` 之后都仍然有效；不用私有 API，也不需要给
`prompt_async` 传 `handle_sigint=False`。空闲提示符下的 Ctrl-C（raw 模式下是按键，
由 prompt_toolkit 抛 `KeyboardInterrupt`）行为不变。

## 4. 非目标

- 选择器内的搜索过滤（10 条以内不需要）。
- 按 surface 过滤会话：channel 与 CLI 共用 workspace 的 `memory.db`，CLI 的列表本来
  就含 IM 会话，加上预览后能看到它们的内容（见 §8）。
- channel / desktop 的 `/skills`、`/resume`；`use_skill` 与系统提示里的 skill 索引。

## 5. 改动清单

| 文件 | 改动 |
|---|---|
| `omicsclaw/entry/cli/_repl.py` | 删 `_skill_invocation`；改 `_unknown_slash`、`_skills`、`_sessions`、`_resume`；抽 `_switch_to`；行格式、预览清洗、回显；模块与 `_dispatch` docstring |
| `omicsclaw/entry/cli/_input.py` | `ChoiceSource`；`PromptToolkitSource.choose`；`build_completer` / `open_prompt_source` 去掉 `skills`；路径补全落点 |
| `omicsclaw/entry/cli/_slash_command_support.py` | 迁入 `slash_token`；`/resume` 描述；模块 docstring 去掉 `complete_slash` 叙述 |
| `omicsclaw/launch/_surfaces.py` | `open_prompt_source()`；`_interrupts` 改用 `signal.signal`（Q7） |
| `omicsclaw/skills/invocation.py` | **删除** |
| `omicsclaw/skills/__init__.py` | 去掉 5 个导出 |
| `omicsclaw/skills/index.py` | `close_names` docstring 不再提"用户敲错 /name" |
| `omicsclaw/entry/session.py` | `Session.updated_at`；保存前打时间戳；`InMemorySessionStore.list` 排序；docstring |
| `omicsclaw/memory/record.py`、`omicsclaw/memory/sessions.py` | `StoredSession.updated_at`；存取与排序；docstring |
| `environment.yml` | `prompt-toolkit>=3.0.52`（Q6） |
| `tests/skills/test_invocation.py` | **删除**（`slash_token` 用例迁走） |
| `tests/skills/test_skills_is_a_leaf_layer.py` | 导出清单 |
| `tests/launch/test_surfaces.py:674` | 替身改为无参 `lambda: source`（审核 M2） |
| `tests/entry/test_cli_optional_dependencies.py:57-63、88-93` | 去掉 `SkillIndex()` 位置参数（后者在子进程里跑，审核 M2） |
| `tests/entry/test_cli_completion.py` | 只补全命令；路径落点 |
| `tests/entry/test_cli_repl.py` | 删 skill 调用类用例；`:331`、`:350` 的否定断言改为新文案（审核 M2）；未知斜杠与旧习惯提示；`/skills` 文案 |
| `tests/entry/test_cli_commands.py` | 选择器、回退、回显、预览、排序用例；`:122` 的 `2 message(s)` 保持成立 |
| `tests/entry/test_cli_input.py` | `PromptToolkitSource.choose` 真实按键用例 |
| `tests/memory/test_sessions.py` | 活动排序、`updated_at` 往返 |
| `tests/launch/` | SIGINT 回归用例（Q7） |
| `CLAUDE.md`、`AGENTS.md`、`CONTRIBUTING.md`、`templates/skill/README.md` | 删 `/<skill-name>` 的表格行与段落（含 `templates/skill/README.md:34`、`AGENTS.md:209,243`）；`/resume` 行（`AGENTS.md:492`）；`CONTRIBUTING.md:236` 的冒烟命令改成自然语言请求——`--prompt-file` 走 `run_once`，从来不经过斜杠分发 |
| `README.md` | `:214` 的 `/resume` 行；按既有结构记一条里程碑 |

## 6. 测试

**选择器（`create_pipe_input` + `DummyOutput`，经 `choose` 自己的 `create_app_session`
注入，无终端）：** ↓+Enter 选第二项；Enter 选 `default`；Esc、Ctrl-C 取消；源已关闭抛
`EOFError`；阻断 `prompt_toolkit.shortcuts.choice_input` 的导入时抛
`NotImplementedError`；与一个先发起的 `read` 并发时，按键归**先**提出的那个
问题（审核 S5：两个 Application 挂同一输入不会报错，而是后来者抢走按键，所以要断言
归属，不是等 `AssertionError`）。

**REPL 层（真实 `AgentApp` + SQLite；选择源用测试替身：`ScriptedSource` 加脚本化
`choose`）：**

- 裸 `/resume` 调 `choose`，选项含预览、不带序号，默认光标跳过当前会话；
- 选中 → 与 `/resume s-old` 相同的持久化结果（沿用"第三个 app 读回 SQLite"的断言）；
- 取消、`EOFError`、选中当前 → 会话 id 不变且循环继续；
- `NotImplementedError` / `RuntimeError` → 回退到列表 + 提示；前者不产生 error 级日志；
- 无会话、只有当前会话 → 不调 `choose`；
- 非 `ChoiceSource`：`["/resume", "hello", "/exit"]` 中 `hello` 送达模型（不被吞）。

**预览与回显：** 压缩过的会话不显示 `[Context Compaction]`；shell 前导块被剥掉，
且命令输出含空行时仍取到问题本身；中文按两列截断且不超宽；`(current)` 在窄终端下
不被截；无用户消息显示 `(no messages)`；回显取最后一轮；内容含 `[red]` 原样显示。

**排序：** SQLite 与内存 store 都按 `updated_at` 倒序；先建 A 再建 B，之后在 A 里
说一句，列表变为 A 在前；`updated_at` 经 SQLite 往返不变；只 `/resume` 不说话不改变顺序。

**skill 入口移除：** `/` 的补全里没有 skill；`/data/ru<Tab>` 走路径补全；
`/spatial-de 任务` 不调用 provider 且出现 "describe the task"；`/spatial-dx` 报
`No command named`；`/data/run7/x.h5ad` 仍送达模型；`/skills` 输出不含 `/<name>`。

**Ctrl-C（Q7）：** 主线程 `asyncio.run` 里进入 `_interrupts`，跑一次真实
PromptSession 提示与一次 `ChoiceInput`（pipe 输入），再 `os.kill(SIGINT)`，断言
`repl.interrupt` 被调用；退出后 SIGINT 处理器恢复为进入前的值。

**变异（各自须被某个用例捕获）：** 默认光标不跳过当前会话；`_switch_to` 不清
`_plan_shown`；回退分支改为直接 `return`；预览不跳过摘要；`rpartition` 改 `partition`；
截断按字符数；`slash_token` 不排除含 `/` 的 token；`_list` 改回 `created_at`；
注册表不打时间戳；`_interrupts` 改回 `add_signal_handler`。

## 7. 验证

- `/opt/conda/envs/rapids_singlecell/bin/python -m pytest tests/entry tests/skills tests/launch tests/memory -q -p no:randomly`，
  再跑全栈；已知无关失败：`tests/tools/test_workspace.py`、
  `tests/test_control_plane_documentation_contract.py`、`test_websafety` 的顺序依赖。
- 另用 `/opt/conda/bin/python`（prompt_toolkit 3.0.43）跑 `choose` 的回退用例，确认旧版不崩。
- **真实进程验收**（pty，临时 workspace）：产生两段会话 → `/resume`、↓、Enter → 出现
  `Resumed` 与回显 → 再提问并在对话中按 Ctrl-C → 打印 `Cancelled.`；`/`+Tab 的补全
  里没有 skill 名。

## 8. 风险

- **旧习惯**：用过 `/spatial-de` 的人会碰到"没有这个命令"；§3.2 的提示为此而设，文档同步删除入口。
- **prompt_toolkit 版本**：低于 3.0.52 时回退为列表 + 提示，不会崩溃。
- **会话内容可见范围**：channel 与 CLI 共用 workspace 的 `memory.db`，预览会让 CLI
  看到 IM 会话的首句。这与现有"数据库文件即边界"的约定一致（`AGENTS.md:539-541`，
  `SqliteSessionStore.list` docstring），但多人共用一个 workspace 跑 channel 时要知道。
- **Ctrl-C 实现方式改变**：从 loop 级改为 Python 级处理器 + `call_soon_threadsafe`；
  Windows 上 `signal.signal` 同样可用，原先 `add_signal_handler` 在 Windows 不可用而回退
  为默认行为，改后反而一致。

## 9. owner 裁定（2026-09-23）

| # | 问题 | 裁定 |
|---|---|---|
| Q1 | `/skills` 是否删除？ | **保留** |
| Q2 | `omicsclaw/skills/invocation.py` 删除还是留作库？ | **删除** |
| Q3 | `/spatial-de 任务`：报告并提示，还是当普通消息发给模型？ | **只提示** |
| Q4 | 列表是否改为按最近活动排序？ | **改**（初稿建议不做，owner 否决；审核同样认为应纳入）→ §3.5 |
| Q5 | 恢复后是否回显上一轮？ | **回显** |
| Q6 | `environment.yml` 的 prompt-toolkit 下限提到 3.0.52？ | **提** |
| Q7 | Ctrl-C 修复（§3.7）并入本计划，还是另开 issue？ | **并入本计划** |

## 10. 审核记录（2026-09-23）

结论"需修改后实施"。处理情况：

- **M1** Ctrl-C 失效 → 已复现（`add_signal_handler` 被 prompt_toolkit 移除；Python 级
  处理器可存活），§2、§3.7、Q7。
- **M2** 漏改的测试（`tests/launch/test_surfaces.py:674`、
  `test_cli_optional_dependencies.py` 两处、`test_cli_repl.py:331,350` 的否定断言、
  `test_cli_commands.py:122` 的措辞）→ §5；行格式保留 `N message(s)`。
- **M3** 压缩摘要成为预览 → 跳过 `is_summary_message`，§3.4。
- **S1** 排序事实 → §2 已改正；owner 裁定纳入，§3.5。
- **S2** shell 前导剥离 → `rpartition`，§3.4。
- **S3** 宽度与标记位置 → `(current)` 前置、扣除边框、选择器不带序号，§3.4。
- **S4** `create_app_session` 绑定 → §3.4。
- **S5** 串行化测试判据 → 改为断言按键归属，§6。
- **S6** 文档遗漏 → §5 补全；初稿"包 docstring 有 invocation 叙述"不实，已改为"去掉 5 个导出"。
- **S7** 近似匹配候选集 → 随 O5 一并取消近似匹配，不再相关。
- **S8** 补用例与日志级别 → §3.4、§6。
- **O1** 采纳一半：`ChoiceSource` 不导出；保留 `NotImplementedError` 回退（版本下限提高后
  它只是兜底）。**O2** 采纳，§3.1。**O3** 采纳（完整年份；措辞保持 `message(s)`）。
  **O4** 记入 §4、§8。**O5** 采纳，§3.2。

## 11. 交付记录（2026-09-23）

**测试**：`tests/schema … tests/subagent`（AGENTS.md 的整套命令）**5072 passed,
12 skipped**，0 失败。基线（`tests/entry tests/skills tests/launch tests/memory`）
改动前 2030 passed，改动后 2028 passed——删除 `tests/skills/test_invocation.py`
约 30 条，新增约 30 条。

**变异**（每条单独施加、跑对应测试、还原）：默认光标不跳过当前会话；`_switch_to`
不清 `_plan_shown`；`NotImplementedError` 分支直接 `return`；预览不跳过摘要；
`rpartition` 改 `partition`；按字符数截断；`slash_token` 接受路径；SQLite 改回
`created_at` 排序；注册表不打时间戳；`_interrupts` 改回 `add_signal_handler`；
`choose` 不持终端锁；路径补全替换整个词；去掉 skill 提示；补全把路径当命令——
**14 条全部被捕获**。另有一条"整行截断而非只截预览"是等价变异（`(current)` 位于
不截断的固定部分），改用"把 `(current)` 挪到预览之后"验证，被 2 条测试捕获。

**真实进程验收**（pty，临时 workspace，`skills/` 软链到仓库语料，provider 用
`sitecustomize` 替身）：两段会话 → `/resume` 弹出选择器、默认停在另一段 → Enter
恢复并回显 `you:` / `agent:` → 慢对话中 Ctrl-C 打印 `Cancelled.` → `/sessions`
中刚用过的会话排第一 → `/` 的补全菜单只有命令 → `/spatial-de rank markers` 报告并提示。

**计划外的改动**：

- **路径补全一直是坏的。** `build_completer` 把 `PathCompleter` 给出的"剩余部分"
  （如 `n7`）配上 `start_position=-len(整个词)`，接受补全会把 `/data/ru` 替换成
  `n7`。§3.1 让 `/data/ru` 走路径补全后这个缺陷变得常见，所以一并修正（改用
  `PathCompleter` 自己的 `start_position`），并加了"接受后整行仍正确"的用例。
- `tests/entry/test_cli_activity.py` 新增 `/resume` 清 `_plan_shown` 的用例——§5 未列，
  变异 2 需要它。

**未能按 §7 执行的一项**：用 `/opt/conda/bin/python`（prompt_toolkit 3.0.43）跑
回退。该解释器是 Python 3.10，连 `omicsclaw` 都导入不了（`StrEnum`）。回退由
`test_a_prompt_toolkit_without_a_picker_says_so`（把 `choice_input` 模块置为不可导入）
与 REPL 层的 `NotImplementedError` 回退用例覆盖。

### 已知且未处理（写明，供后续裁定）

- 计划 0052、0054 草案引用的 `_repl.py` 行号因本次改动偏移；0054 §3 描述的
  Ctrl-C 调用链（`_interrupts._fire → Repl.interrupt → handle.cancel()`）不变，但
  处理器现在是 Python 级的 `signal.signal`，不再是 loop 级。
- pty 验收中出现的 "your terminal doesn't support cursor position requests (CPR)"
  来自测试替身终端不回应 CPR，真实终端不会出现。
- `/sessions` 仍列出同一 workspace 下 channel 的会话（§8），本次未做按 surface 过滤。

