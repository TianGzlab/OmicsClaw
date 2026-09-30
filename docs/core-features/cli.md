# CLI —— `oc` 进程入口与终端 REPL

> OmicsClaw **没有**全屏 TUI（Textual TUI 未移植），终端交互是一个流式 REPL。
> 事实来源：`omicsclaw/launch/`、`omicsclaw/entry/cli/`、`omicsclaw/entry/config.py`、`tests/launch/`、`tests/entry/test_cli_*.py`。

---

## 1. 概述

OmicsClaw 的命令行由两层组成：

| 层 | 包 | 职责 |
|---|---|---|
| 进程外壳 | `omicsclaw/launch/` | 唯一读取 `sys.argv` 与 `os.environ` 的地方；加载 `.env`；按 `--` 切分命令行；决定退出码；处理信号 |
| 终端界面 | `omicsclaw/entry/cli/` | 一个**库**而不是进程：REPL 循环、斜杠命令、审批卡片、事件渲染、`!` Shell、配置向导 |

`oc` 有且仅有三个子命令，对应三个界面（`omicsclaw/launch/_grammar.py` 的 `COMMANDS`，
`tests/launch/test_grammar.py::test_the_entry_points_are_exactly_three` 钉住数量）：

```
oc cli        终端 REPL，或 --prompt/--prompt-file 的一次性执行
oc desktop    OmicsClaw-App 的 HTTP 后端      （见 surfaces.md）
oc channel    即时通讯适配器                  （见 surfaces.md）
```

`oc run <skill>` 被 owner 裁定**不保留**：执行 skill 是 agent 在会话里做的事（见 agent-skills.md §9），不是第四个入口。

---

## 2. 进程入口：`omicsclaw/launch/`

### 2.1 四种写法，同一个 `main`

| 写法 | 定义处 |
|---|---|
| `oc ...` / `omicsclaw ...` | `pyproject.toml` `[project.scripts]` → `omicsclaw.launch:main` |
| `python -m omicsclaw.launch ...` | `omicsclaw/launch/__main__.py` |
| `python -m omicsclaw ...` | `omicsclaw/__main__.py` |
| `python omicsclaw.py ...` | 仓库根 `omicsclaw.py`（源码 checkout 的哨兵文件，勿删） |

`main(argv=None, env=None) -> int` **不抛任何异常**，只返回退出码：

| 退出码 | 含义 | 常量 |
|---|---|---|
| `0` | 收敛 / 正常结束 | `EXIT_OK` |
| `1` | 界面运行了但没收敛，或出现未预料的异常（只打印 `omicsclaw: <Type>: <msg>`，不打 traceback） | `EXIT_FAILED` |
| `2` | 命令行或部署配置被拒（`AppConfigError`），或缺可选依赖（`MissingSurfaceDependency`） | `EXIT_REFUSED` |
| `130` | `SIGINT` | `EXIT_INTERRUPTED` |
| `143` | `SIGTERM` | `EXIT_TERMINATED` |

`env` 显式传入时表示"这就是全部部署"：不读 `.env`、不碰进程环境——测试用它驱动整个部署。

### 2.2 `.env` 加载：`_dotenv.py`

```
main(env=None)
  └─ _adopt_dotenv()
       for candidate in dotenv_candidates():      # 去重后的两处，按序
           load_env_file(candidate, override=False)
```

- **两个位置，项目根优先**：`resolve_omicsclaw_dir()/.env`（依次取 `OMICSCLAW_DIR`、含 `omicsclaw.py` 的源码根、
  用户级回退目录），然后 `<cwd>/.env`。
- **已导出的变量永远赢**（`override=False`），所以两个文件里先出现的那个决定取值。
- 写回用 `dotenv_target()`：第一个已存在的候选；都不存在时取第一个候选。`oc cli --configure` 和 `/auto` 都写这个文件——
  "向导配置了一个文件、外壳却加载另一个"的 bug 由这一处共享搜索杜绝。
- 为什么写进进程环境而不是只放进映射：`omicsclaw.provider.provider_from_env` 直接从进程环境读 API key（plan 0031 Q8 唯一声明的例外）。

优先级：**命令行 flag > 已导出变量 > `.env` 文件 > 默认值**。

### 2.3 命令行文法：`--` 规则

```
oc <surface> [deployment flags] [-- surface flags]
```

`split_command_line(tokens)`：

1. 在第一个 `--` 处切开：左边是**部署 flag**，原样交给 `omicsclaw.entry.resolve_app_config`；右边是**界面 flag**，交给该界面自己的解析器。
2. 左半中处于 flag 位置的 `--help` / `-h` 被移到右半，所以 `oc cli --help` 与 `oc cli -- --help` 等价。
   "flag 位置"用 `_surfaces.flag_stride` 行走判断——`oc cli --workspace --help /data` 里的 `--help` 是 `--workspace` 的值，不会被当成求助。
3. **界面 flag 可以写在 `--` 任一侧**（plan 0048）：`_claim_surface_flags` 先从部署半边里认领本界面的 flag
   （两族 flag 不相交，不会抢走部署 flag），所以 `oc cli --session run-7` 与 `oc cli -- --session run-7` 相同；
   同一 flag 两边都写时，`--` 之后的更显式写法胜出。
4. `--` 仍有用处：值本身长得像 flag 时，例如 `oc cli -- --prompt --model`。

部署半边**总是**先被解析（即使随后只是回答 `--help`），所以部署 flag 的拼写错误不会被某个提前返回的界面 flag 吞掉：

```bash
$ oc cli --bogus x
omicsclaw: unknown option '--bogus'; pass a surface's own flags after '--'
usage: oc cli [deployment flags] [-- surface flags]
...
```

---

## 3. `oc cli` 的界面 flag

`CLI_FLAGS` / `ReplOptions`（`omicsclaw/launch/_surfaces.py`，手写解析器，错误统一抛 `AppConfigError` → 退出码 2）：

| flag | 作用 |
|---|---|
| `--session <id>` | 仅 REPL：继续一个已存储的会话；默认新开 |
| `--prompt <text>` | 回答一次后退出，不进 REPL |
| `--prompt-file <path>` | 同上，整个文件作为**一条**用户消息（避免多行任务被拆成多轮）；空文件被拒 |
| `--show-reasoning` / `--hide-reasoning` | 是否打印模型推理；二者互斥 |
| `--configure` | 运行配置向导写 `.env`，不启动 agent |
| `--help` / `-h` | 打印 `CLI_USAGE` |

组合规则：`--session` 与 `--prompt`/`--prompt-file` 互斥（一次性执行没有会话可继续）；`--configure` 与三者都互斥。

推理默认显示；例外是一次性执行且 stdout 不是终端时默认不显示，保证 `oc cli --prompt "…" > answer.txt` 只写答案
（`ReplOptions.shows_reasoning`）。

> 不要混淆：**部署 flag** `--system-prompt-file`（`OMICSCLAW_SYSTEM_PROMPT_FILES`）替换 system prompt 的前置文件；
> **界面 flag** `--prompt-file` 是用户消息。旧名已被拒绝且没有别名（`test_the_deployment_half_no_longer_answers_to_the_surface_flag_name`）。

---

## 4. 启动流程

```
oc cli [...]
  │
  main()  ── _adopt_dotenv() ── split_command_line()
  │
  start_cli(deployment, surface, env)
  ├─ _claim_surface_flags + ReplOptions.parse
  ├─ resolve_app_config(deployment, _with_the_cli_permission_mode(env))   ← 部署半边总被解析
  ├─ --help → 打印 CLI_USAGE，返回 0
  ├─ --configure → run_configuration_wizard(dotenv_target())，返回 0
  ├─ _report_a_missing_credential(env)          ← 没配 key：stderr 一行 "oc cli --configure"
  └─ with terminal_owned_logging() as records:  ← REPL 期间 root logger 的 handler 换成内存缓冲，几个嘈杂 logger 调到 ERROR
        asyncio.run(_run_cli(config, options, ...))
          ├─ app = attach_sessions(await open_app(config))      ← 组合根：见 surfaces.md
          ├─ 有 prompt → run_once(app, text)  → 收敛返回 0，否则 1
          └─ 否则 → source = open_prompt_source()
                    repl = Repl(app, source=..., screen=Screen(), ...)
                    repl.welcome()                 ← Logo + session/workspace/model/provider 横幅
                    with _interrupts(repl, task):  ← SIGINT → Repl.interrupt()
                        await repl.run()
          finally: _release(app)                   ← asyncio.shield(app.aclose())，吸收一次额外 Ctrl-C
     finally: _replay(records)                     ← 退出后把日志末尾 4000 字符打到 stderr
```

值得注意的三点：

- **一次性执行不接审批**：`run_once` 用空的 `ScriptedSource(())` 作为输入源，任何需要审批的工具调用都会被拒（失败关闭）。
  在默认权限模式下 `bash` / `write_file` / `edit_file` / `web_fetch` / `web_search` 都是 `ASK`，所以脚本化使用时
  通常要配 `--permission-mode auto-approve`（最好同时开沙箱）。
- **关闭是受保护的**：`_release` 用 `asyncio.shield` 包住 `AgentApp.aclose()`（排空会话、停 MCP 子进程、删沙箱容器），
  第二次 Ctrl-C 不会把它截断；若仍未完成，退出码报 1 而不是 130。
- **日志不丢**：REPL 占用终端时日志被重定向，退出时回放尾部，便于诊断。

---

## 5. REPL 循环

`omicsclaw/entry/cli/_repl.py` 的 `Repl`。提示符是 `❯ `（`PROMPT`）。

```python
while self.state.running:
    line = await self._source.read(PROMPT)      # EOF → "Goodbye!" 退出
    if not line.strip(): continue
    if not await self._dispatch(line.strip()): break
```

`_dispatch` 的判定顺序：

```
以 "!" 开头        → _shell(...)                 不调模型（§8）
匹配完整命令目录     → /exit 退出；未实现的名字 → "<name> is not available in this build."
                     已实现的 → _command(name, arg)
"/name" 但没人认领  → "No command named /name."（若恰是 skill 名，提示让 agent 选 skill），不调模型
其余               → ask(text)                  提交给会话注册表
```

一条以路径开头的行（首个 token 里还有 `/` 或 `\`，如 `/data/run7/matrix.h5ad 这是什么？`）不算命令名，照常发给模型
（`slash_token`）。

`ask` 通过 `app.sessions.submit(session_id, text)` 提交，拿到 `TurnHandle`，再由 `_drive` → `_pump` 把事件流画到屏幕，
最后 `await handle.wait()` 等注册表完成持久化，避免下一个提示与保存赛跑。

**Ctrl-C 取消的是本次 exchange，不是进程**：`Repl.interrupt()` 取消正在运行的 handle，注册表发布
`EXCHANGE_END(terminal="cancelled")`，循环回到提示符；对话历史保持**逐字节不变**（取消的 exchange 不保留半截轨迹）。
空闲时按 Ctrl-C 则结束 REPL（`_interrupts._fire`）。信号处理器用 `signal.signal` 安装，因为 prompt_toolkit
每次读提示都会增删自己的 loop 级 SIGINT 处理器（plan 0051 修复的"Ctrl-C 失效"问题）。

---

## 6. 斜杠命令

命令目录分两层（`_constants.py`、`_slash_command_support.py`）：`SLASH_COMMANDS` 是从旧 CLI 逐字移植的**完整目录**
（含本构建不实现的 `/run`、`/research`、`/memory`、`/install-skill` 等），`ADDED_SLASH_COMMANDS` 是新增的 `/compact`、`/auto`；
REPL 真正实现的是 `REPL_SLASH_COMMAND_SPECS` 这个子集——共 14 个：

| 命令 | 行为（均从已组装的 `AgentApp` 回答） |
|---|---|
| `/help` | 列出这 14 个命令 |
| `/skills [query]` | 按领域分组列出已索引 skill；`query` 走 `SkillIndex.search`（name/domain/tags/triggers） |
| `/new` | 新会话 id（`new_turn_id()[:8]`），旧会话仍在存储里可 `/resume` |
| `/clear` | 与 `/new` 实现相同，只是提示文字为 "Cleared; new session"（放弃旧 session 而不是就地清空） |
| `/current` | 当前 session id、workspace、权限模式 |
| `/sessions` | 最近 10 个会话（`SESSION_LIST_LIMIT`），按最近活动倒序，带首条用户消息预览；并说明本部署是否持久化 |
| `/resume [id\|number]` | 无参数且在终端、prompt_toolkit ≥ 3.0.52 时弹出方向键选择器（↑/↓、Enter、Esc）；管道中打印列表；恢复后回显上一问一答 |
| `/compact` | 立即压缩本会话，保留近期消息，报告节省情况；本会话有 exchange 在跑时拒绝 |
| `/plan`、`/tasks` | 只读显示本会话的执行计划（`AgentApp.plans`），图标 `▶ ✔ ⊘ ○` |
| `/usage` | 本 REPL 累计的输入/输出 tokens（仅累加后端报告过的 usage） |
| `/mcp` | 读取实时 `MCPManager.statuses()`：每个 `.mcp.json` 服务器的状态与工具数 |
| `/auto [on\|off\|status]` | 在 `default` 与 `auto-approve` 间切换（§7.3） |
| `/exit` | 退出；别名 `/quit`、`/q` |

目录里其余名字（`/run`、`/research`、`/doctor`、`/export` …）回答 "not available in this build"，而不是被当成问题发给模型。
skill 不是命令：`/spatial-de` 会得到 "No command named /spatial-de." 加一行 "Skills are picked by the agent" 的提示。

Tab 补全（`_input.build_completer`）只补 14 个命令；首个 token 含第二个 `/` 时改走路径补全。

---

## 7. 审批卡片

需要审批的工具调用会在事件流里出现 `APPROVAL_REQUIRED`。REPL 在**独立的 Task** 里提问（`_ask_human` → `_ask`），
事件泵绝不等人——否则同一条模型消息里的第二个工具的审批请求永远到不了（plan 0031 trap 1）。

### 7.1 卡片与回答

提示格式 `approve {name} [{card}]? [y/N/a=always] `，`card` 是请求在本 exchange 内的编号（如 `#1`），
与卡片上 `[<turn id>#1]` 对应，便于区分同一工具的两次调用。卡片上方打印图例：

| 回答 | 效果 | 持久化 |
|---|---|---|
| `y` / `yes` / `ok` / `allow` | 允许这一次 | 无 |
| `s` / `session` | 允许，并在**本会话**内不再询问这个**工具**（plan 0049 起按工具而非按精确调用） | 仅内存 `Repl._granted`，随会话与进程消失 |
| `a` / `always` | 允许，并为**这一个精确调用**写一条 `allow` 规则 | `<workspace>/.omicsclaw/settings.json`（`AgentApp.remember_approval`） |
| `/auto` 或 `/auto on` | 切到 `auto-approve` 并允许这张卡 | 同 §7.3 |
| 其他任何输入（含空行） | 拒绝 | — |

`a` 刻意只覆盖精确调用：规则优先于危险命令模式，`bash(git *)` 会放过 `git status; rm -rf /`。
要"别再问 bash"，用 `s` 或 `--permission-mode auto-approve`。

### 7.2 总是询问的卡片

- `ApprovalRequest.ask_every_time` 为真（危险命令模式、显式 `ask` 规则、改动 `.omicsclaw/`、规则文件或 `.env`、
  声明 `DENY_UNLESS_TRUSTED` 的工具）：图例换成 "this call is always asked about: y or s = allow it once · a = always …"，`s` 只放行这一次。
- 受保护文件（规则文件、`.omicsclaw/`、`.env`）的改动在读取任何规则之前就被判定，`a` 写的规则永远不会被查阅，
  所以卡片只提供 `y`（`AgentApp.can_remember_approval` 返回 `False`）。
- 问不出来（输入源出错）的请求一律拒绝；在卡片上按 Ctrl-C 以 `interrupted at the terminal` 拒绝。CLI 默认没有审批期限
  （`approval_timeout_s=None`）。

### 7.3 `/auto` 与权限模式

`PermissionMode`：`default`（规则决定，未命中时按工具自身策略）、`auto-approve`（未命中即允许，`deny` 规则与危险模式仍生效）、
`read-only`（拒绝所有未声明 `read_only=True` 的工具，包括 `bash` 与 `web_search`）、`bypass-all`（无任何检查）。

`/auto`（`_auto.py`，plan 0050）做两件事：

1. **现在**：`AgentApp.set_permission_mode` 立刻切换本进程唯一的权限门，下一个工具调用即生效；只允许在 `default` ⇄ `auto-approve` 之间切换，
   `read-only` / `bypass-all` 是部署承诺，运行中不可变。
2. **下次启动**：把 `OMICSCLAW_CLI_PERMISSION_MODE` 写进外壳加载的 `.env`。这是 CLI 专用键，Channel / Desktop 不读，
   避免在终端里的一次切换让无人值守的 IM 机器人开始自动批准。

`oc cli` 权限模式的优先级：`--permission-mode` flag > `OMICSCLAW_PERMISSION_MODE`（任何来源）> `OMICSCLAW_CLI_PERMISSION_MODE` > `default`。
被更高优先级压住时 `/auto status` 会说明。`auto-approve` 下仍会询问：危险命令、显式 `ask` 规则、对 `.omicsclaw/` 或 `.env` 的改动。

---

## 8. Shell 模式：`!<cmd>`

实现位于 `omicsclaw/entry/cli/_shell.py`：

| 项 | 取值 |
|---|---|
| 执行方式 | `bash -c`，工作目录为 workspace；stdout+stderr 合并；stdin 为 `/dev/null`；独立进程组，超时整组杀掉 |
| 超时 | `SHELL_TIMEOUT_S = 60.0`（与 `tool_timeout_s` 无关：这是人盯着光标等的命令） |
| 屏幕截断 | `DISPLAY_LIMIT = 4096` 字节 |
| 给模型的截断 | `CONTEXT_LIMIT = 2048` 字节 |
| 注入方式 | 记录累积在 `_shell_records`，以 `[Shell commands run by the operator at the terminal]` 为头**前置到下一个问题**，读后清空 |
| 交互式程序 | `wants_a_terminal` 只看首词（`NEEDS_A_TERMINAL`），命中则提示"去另一个窗口运行"；漏网的由超时兜底 |
| 权限门 | **不经过**：操作者本人就坐在一个 shell 前，给他自己的命令加确认没有意义；门是给模型提出的命令的 |

例：`!ls runs/pp/figures` 然后问"哪张图说明聚类效果最好？"，模型会同时看到你刚才列出的目录。

---

## 9. 事件渲染

`Repl._pump` 在 `async with handle.observe() as observation` 中消费一次 exchange 的 `TurnEvent`
（`async with` 保证中途 break 时观察者被摘除，否则放弃计时不会开始）：

| 事件 | 终端行为 |
|---|---|
| `REASONING_DELTA` | 由 `ReasoningStreamWriter` 以弱化样式流式写出（`--hide-reasoning` 时丢弃）；回答中途再次思考会先收尾 Markdown |
| `TEXT_DELTA` | 由 `MarkdownStreamFormatter` 流式渲染；与推理块之间空一行 |
| `TOOL_START` / `TOOL_RESULT` | `TextRenderer` 给出头行，`ToolTranscript` 加调用编号、参数预览（`ARGUMENT_CHARS = 120`）、输出预览（`OUTPUT_LINES = 3`、`OUTPUT_CHARS = 160`），结果按 `tool_call_id` 配对；控制字符被替换 |
| `TOOL_RESULT` of `plan_write` | 计划有变化时打印完整计划快照（与上次打印的比较，未变则不打印） |
| `APPROVAL_REQUIRED` | 独立 Task 弹审批卡片（§7） |
| `PROGRESS` | 更新活动行的细节 |
| `CONTEXT` / `COMPACTION` / `QUEUED` / `APPROVAL_SETTLED` / `GAP` | `TextRenderer` 的一行控制文本 |
| `TURN_END` | 累加 usage 供 `/usage`（`usage=None` 跳过，零值照加） |
| `EXCHANGE_END` | `converged` 不打印（每个回答下面一行 "Done." 是噪音）；`cancelled` / `failed` 打印 |

`TextRenderer`（`omicsclaw/entry/render.py`）在 CLI 以 `batched=False` 使用：token 一到就上屏。它从不渲染工具参数或输出的原始载荷
（审批行例外，展示给做决定的人，且不写日志）；工具耗时带 `ELAPSED_INCLUDES_APPROVAL_WAIT` 后缀——这个时间包含人思考审批的时间。

### 9.1 活动行：`_activity.py`

两个 token 之间可能静默几十秒（模型思考、`bash` 跑几分钟），`ActivityLine` 在输出底部维护**一行**状态：
动词轮换（`VERBS = ("thinking", "analysing", "working", "reasoning", "weighing")`）+ spinner（`⠋⠙⠹…`）+ 当前工具与耗时 + `ctrl-c to interrupt`。

- 不是 TUI：只用 `\r` + 擦除，结束后 scrollback 与没有它时逐字节相同（`ActivityLine.close` 保证）。
- 与流式文本共享终端的规则是"**不画**"：文本开始流出时 `hold()`，停止时 `release()`；审批期间也 `hold()`（计数式，支持多张卡）。
- 模型调用期间也显示（不只工具期间）——一个只返回 tool call 的模型不产生任何 `TEXT_DELTA`。
- 非终端（管道、文件）不做动画，而是在同一活动持续 `HEARTBEAT_S = 30.0` 秒后追加一行纯文本心跳；短的 `oc cli --prompt ... > answer.txt` 不会出现心跳。
- 刻意不显示 token 计数（plan 0041 裁定：`/usage` 按需打印即为最终答案）。

---

## 10. 输入源

`omicsclaw/entry/cli/_input.py`，REPL 从不直接读 `sys.stdin`：

| 实现 | 何时使用 |
|---|---|
| `PromptToolkitSource` | stdin 是终端且装了 prompt_toolkit：历史（`~/.config/omicsclaw/history`）、历史自动建议、命令补全；多个并发读者排队 |
| `StreamSource` | 非终端（`oc cli < questions.txt`）或没装 prompt_toolkit；`readline` 在工作线程执行，不阻塞事件循环 |
| `ScriptedSource` | 固定列表：测试与一次性执行 |

`open_prompt_source()` 按上述顺序降级而不是失败；prompt_toolkit 在函数体内导入，不是硬依赖。

---

## 11. 配置向导：`oc cli --configure`

`omicsclaw/entry/cli/_configure.py`（移植自旧 `setup_wizard.py`，问题从约 30 个砍到 5 个 + 3 个可选段）：

1. LLM：provider（13 个预设：deepseek、openai、anthropic、gemini、nvidia、siliconflow、openrouter、volcengine、dashscope、moonshot、zhipu、ollama、custom；默认 `deepseek`）、key、model、endpoint；
2. workspace；
3. 可选：Telegram、Feishu、Desktop token。

写入规则：只改用户回答过的键，**保留注释、空行、顺序和不认识的变量**；先备份为 `.env.backup-<timestamp>`，再写临时文件原子替换；
密钥从不回显（只显示末 4 位），也不进日志。保存后回读文件，按 `AppConfig` 的顺序（`OMICSCLAW_PROVIDER` → `LLM_PROVIDER`，`OMICSCLAW_MODEL` → `LLM_MODEL`）取 provider 与模型交给 `resolve_config`，打印"本部署现在解析为：provider / model / endpoint / api key"。

变量名规则（与 Desktop `PUT /providers` 共用 `names_to_write`）：provider 写文件里已有的 `OMICSCLAW_PROVIDER` 和 `LLM_PROVIDER`（两个都在就都写成同一个值），都没有时写 `LLM_PROVIDER`；
模型（`OMICSCLAW_MODEL`、`LLM_MODEL`）与端点（`<PROVIDER>_BASE_URL`、`LLM_BASE_URL`、`OMICSCLAW_BASE_URL`）同理，已有的写法全部写成同一个值，
所以留空的回答不会让低优先级的旧值漏出生效；密钥写已有的最高优先级写法。
picker 的默认项按 `OMICSCLAW_PROVIDER` → `LLM_PROVIDER` → 按 key 探测取当前 provider；provider 不变时，模型、端点、已存密钥的默认值取第一个非空的写法。
向导只读写 `.env` 文件，看不到启动前导出的变量：导出的同名或其他写法的变量仍会覆盖写入的值（Desktop 的保存会在 `shadowed_by_environment` 里列出，CLI 不会提示）。
没装 questionary 时回退到标准库的 `StreamPrompter`。

没有配置任何 key 时（ollama 等无 key 后端除外），`oc cli` 启动时在 stderr 打印一行：
`omicsclaw: no LLM API key is configured. Set one up with:\n    oc cli --configure`。

---

## 12. 会话与工作区

| 路径 | 内容 | 来源 |
|---|---|---|
| `<workspace>/.omicsclaw/memory.db` | 会话（`SqliteSessionStore`）与长期记忆，一个库 | `entry/memory.py`；`--memory false` 时会话只在内存 |
| `<workspace>/.omicsclaw/MEMORY.md` | 长期记忆的摘要（précis） | `entry/memory.py` `PRECIS_FILENAME` |
| `<workspace>/.omicsclaw/settings.json` | 权限规则（`a` 写入处） | `AppConfig.permission_rules_path()` |
| `<workspace>/.omicsclaw/plans/` | 每会话执行计划 | `AppConfig.plans_root()` |
| `<workspace>/.omicsclaw/agents/` | 子代理定义 | `AppConfig.agents_root()` |
| `<workspace>/.omicsclaw/tool_results/` | 压缩时 offload 的大工具结果 | `entry/compaction.py` `TOOL_RESULTS_DIRNAME` |
| `<workspace>/.omicsclaw/compaction_records/` | 压缩记录（JSONL） | `RECORDS_DIRNAME` |
| `~/.config/omicsclaw/history` | REPL 输入历史 | `_input._history_path()` |

workspace 默认是启动时的当前目录（`--workspace` / `OMICSCLAW_WORKSPACE` 可改），它同时是文件工具的沙箱根、
`skills/` / `.mcp.json` 的查找位置；运行时契约 `OMICSCLAW.md` 从 `skills/` 旁读。**在数据目录里启动 `oc cli` 会找不到仓库的 `skills/` 和契约**，
此时用 `--skills-dir` / `OMICSCLAW_SKILLS_DIR` 指回仓库，两者同时就位；把它写进仓库根的 `.env`，每次启动都生效。

`/sessions` 会说明本部署是否持久化会话；`oc cli --session <id>` 或 `/resume` 继续旧会话。

---

## 13. 常用部署 flag 与环境变量

全部定义在 `omicsclaw/entry/config.py` 的 `_OPTIONS`；每个 flag 都有对应环境变量，flag 胜出。节选：

| flag | 环境变量 | 默认 | 说明 |
|---|---|---|---|
| `--workspace` | `OMICSCLAW_WORKSPACE` | 当前目录 | 沙箱根 |
| `--model` | `OMICSCLAW_MODEL`, `LLM_MODEL` | `""`（provider 预设默认） | |
| `--provider` | `OMICSCLAW_PROVIDER`, `LLM_PROVIDER` | `""`（按 key 探测） | |
| `--tool-timeout` | `OMICSCLAW_TOOL_TIMEOUT_S` | `600` | 工具上限的唯一来源；`bash` 用它减 15 s |
| `--max-turns` | `OMICSCLAW_MAX_TURNS` | `50` | 每次 exchange 的模型调用上限 |
| `--turn-timeout` | `OMICSCLAW_TURN_TIMEOUT_S` | 无 | 单次 exchange 墙钟上限 |
| `--approval-timeout` | `OMICSCLAW_APPROVAL_TIMEOUT_S` | 无 | 单次审批期限，到期拒绝 |
| `--system-prompt-file` | `OMICSCLAW_SYSTEM_PROMPT_FILES` | skill 树旁的 `OMICSCLAW.md` | 替换契约，`:` 分隔 |
| `--skills-dir` / `--skills-index` | `OMICSCLAW_SKILLS_DIR` / `OMICSCLAW_SKILLS_INDEX` | `<workspace>/skills` / `full` | 见 agent-skills.md |
| `--compact-at` | `OMICSCLAW_COMPACT_AT` | `warn` | 触发压缩的最低压力档 |
| `--memory` / `--planning` / `--subagents` | `OMICSCLAW_MEMORY` / `OMICSCLAW_PLANNING` / `OMICSCLAW_SUBAGENTS` | 均为开 | |
| `--permission-mode` / `--permission-rules` | `OMICSCLAW_PERMISSION_MODE` / `OMICSCLAW_PERMISSION_RULES` | `default` / `.omicsclaw/settings.json` | |
| `--sandbox` 及 `--sandbox-*` | `OMICSCLAW_SANDBOX*` | `off` | Docker 隔离 `bash` |
| `--mcp-config` | `OMICSCLAW_MCP_CONFIG` | `<workspace>/.mcp.json` | |
| `--audit-log` | `OMICSCLAW_AUDIT_LOG` | 无 | 每次工具调用一行 JSONL |
| — | `OMICSCLAW_CLI_PERMISSION_MODE` | — | 仅 `oc cli` 读取，由 `/auto` 写 |
| — | `LLM_API_KEY` / `LLM_BASE_URL` / 各厂商 `*_API_KEY` | — | 由 `omicsclaw/provider` 读取，见 `.env.example` §1 |

非法值直接拒绝（`AppConfigError`，退出码 2），而不是回退默认值——`OMICSCLAW_TOOL_TIMEOUT_S=6OO` 悄悄变成 60 s 正是要避免的。
完整清单见 `.env.example`（按 12 节组织）。

---

## 14. 已知限制

1. **没有 TUI**。Textual TUI 未移植（会拖入整个 `RunRuntime` 与旧记忆族），`textual` 也未安装。
2. **一次性执行无法审批**：`--prompt` 下所有 `ASK` 工具被拒，需要 `--permission-mode auto-approve`。
3. **日志只保留尾部**：退出后只回放最后 4000 字符；`--log-file` 部署 flag 记为 plan 0037 附录 A 的债务。
4. **目录中有大量不实现的旧命令**（`/run`、`/research`、`/memory`、`/install-skill` …），出于移植保真测试保留，只回答"不可用"。
5. **会话 id 与 `/clear`**：`/clear` 并不清空当前会话，而是开一个新 id；旧会话仍可 `/resume`。
6. **没有常驻上下文窗口占用显示**（FRAMEWORK-REBUILD 记录 context-window reporting #20 仍开放）。
7. **没有跑过真实 provider 的端到端验收之外的持续测试**：界面层对真实 provider / 真实终端的覆盖仍是债务（FRAMEWORK-REBUILD "Debts carried forward"）。

---

## 15. 文件索引

| 文件 | 内容 |
|---|---|
| `omicsclaw/launch/__init__.py` | `main`、`_adopt_dotenv`、退出码语义 |
| `omicsclaw/launch/__main__.py`、`omicsclaw/__main__.py`、`omicsclaw.py` | 其他启动写法 |
| `omicsclaw/launch/_grammar.py` | `COMMANDS`、`split_command_line`、`HELP_FLAGS`、`usage` |
| `omicsclaw/launch/_dotenv.py` | `DOTENV_FILE`、`dotenv_candidates`、`dotenv_target` |
| `omicsclaw/launch/_surfaces.py` | `CLI_USAGE`、`CLI_FLAGS`、`ReplOptions`、`start_cli`、`_run_cli`、`_release`、`_interrupts`、`_replay`；Desktop/Channel 启动 |
| `omicsclaw/entry/config.py` | `AppConfig`、`resolve_app_config`、全部部署 flag |
| `omicsclaw/entry/cli/__init__.py` | 包说明与公开符号 |
| `omicsclaw/entry/cli/_repl.py` | `Repl`、`run_once`、审批、`/sessions` `/resume` `/compact` 等 |
| `omicsclaw/entry/cli/_slash_command_support.py`、`_constants.py` | 命令目录、`REPL_SLASH_COMMAND_SPECS`、`slash_token` |
| `omicsclaw/entry/cli/_activity.py` | `ActivityLine` 活动行 |
| `omicsclaw/entry/cli/_transcript.py` | `ToolTranscript` |
| `omicsclaw/entry/cli/_markdown.py`、`_reasoning.py`、`_screen.py` | 流式 Markdown、推理块、横幅与日志重定向 |
| `omicsclaw/entry/cli/_input.py` | `PromptSource` 三种实现、补全、历史 |
| `omicsclaw/entry/cli/_shell.py` | `!` Shell |
| `omicsclaw/entry/cli/_auto.py` | `/auto`、`OMICSCLAW_CLI_PERMISSION_MODE` |
| `omicsclaw/entry/cli/_configure.py` | 配置向导、`missing_credential_hint` |
| `omicsclaw/entry/render.py` | `TextRenderer` |
| `tests/launch/` | 文法、flag 认领、`.env`、环境读取位置、分层 |
| `tests/entry/test_cli_*.py` | REPL、命令、审批范围、活动行、Shell、配置、补全、推理、transcript |
| `docs/plans/0037-launch-and-entry-points.md`、`0048`、`0049`、`0050`、`0051` | 外壳设计、flag 认领、会话授权、`/auto`、撤回 `/skill-name` 与选择器 |
