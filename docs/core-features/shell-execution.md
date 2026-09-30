# Shell 执行功能技术方案

## 1. 概述

OmicsClaw 有两条执行 shell 命令的通道，服务于两种不同的"谁在发起"：

| 通道 | 谁发起 | 代码位置 | 是否经过模型 | 是否经过审批 |
|---|---|---|---|---|
| **`bash` 工具** | 模型（ReAct 循环中的一次 tool call） | `omicsclaw/tools/builtin/bash.py` | 是，结果作为 Observation 回到模型 | 是（`ASK` + 权限闸门） |
| **CLI `!<cmd>`** | 坐在终端前的操作者 | `omicsclaw/entry/cli/_shell.py` + `omicsclaw/entry/cli/_repl.py` | 否，只把记录前置到下一个问题 | 否 |

`bash` 工具是 OmicsClaw 运行组学 skill 脚本的**主通道**。`OMICSCLAW.md` 规定的调用方式——
先 `use_skill` 取回 SKILL.md 与 skill 目录，再用 shell 执行
`python <skill 目录>/<script>.py --input … --output …`——落到框架里，就是模型
发起一次 `bash` 调用。文件搜索也没有专门工具，`find` / `grep` / `rg` 同样走 `bash`
（`TOOL_NAME` 的 docstring）。

`!<cmd>` 是 REPL 的便利功能：操作者直接跑
`ls`、`git status`、`head results/...`，输出显示在屏幕上，并在下一次提问时以一段
"操作者在终端执行过的命令"前置注入给模型。

---

## 2. 设计原则

| 原则 | `bash` 工具 | `!<cmd>` |
|---|---|---|
| **审批是唯一边界（沙箱关闭时）** | 默认 `ApprovalMode.ASK` + `RiskLevel.HIGH`，审批提示展示**完整**命令 | 不审批：命令是操作者自己敲的 |
| **非零退出不是工具失败** | 退出码写进 Observation 文本，不置 `is_error` | `failed=True` 仅用于着色 |
| **超时是保证，不是礼貌** | 可配置的长预算（默认 585 s），超时附 `[TIMEOUT …]` 横幅 | 固定 60 s，按进程组 SIGKILL |
| **不被后台进程挂住** | 输出写临时文件而不是管道 | 独立 session，超时后整组杀掉 |
| **不和人抢键盘** | `stdin=DEVNULL` | `stdin=DEVNULL` |
| **内存 / 上下文有界** | 16,000 字符，头 1/3 尾 2/3 | 屏幕 4096 字节，模型 2048 字节 |

---

## 3. 架构总览

```
                 ┌──────────── 模型发起 ─────────────┐        ┌──── 操作者发起 ────┐
                 │                                    │        │                    │
LLM ToolCall "bash" {"command": "...", "timeout_secs"?}         REPL 输入 "!git status"
                 │                                    │        │                    │
                 ▼                                    │        ▼                    │
engine/executor.py::_execute                          │   Repl._dispatch            │
  asyncio.timeout(EngineConfig.tool_timeout)          │     text.startswith("!")    │
  (+ TimeoutPause：审批期间停表)                        │        │                    │
                 │                                    │        ▼                    │
                 ▼                                    │   Repl._shell(command)      │
permission.GatedTool          ← 规则 / 危险模式 / 模式  │     ├─ 空命令 → 静默返回      │
  └─ hooks.HookedTool         ← 审计等 hook 链         │     ├─ wants_a_terminal →  │
       └─ BashTool.execute                            │     │   提示去别的终端       │
            ├─ _arguments()   解码 + schema 校验        │     └─ run_shell()          │
            ├─ require_approval()  ← 审批通道           │          bash -c, PIPE,     │
            ├─ report_progress("running in …")        │          new session, 60 s  │
            ├─ environment is None ?                  │        │                    │
            │    ├─ 是 → _locally()  bash -c → 临时文件  │        ▼                    │
            │    └─ 否 → _in_environment()             │   for_display → 屏幕        │
            │           BashEnvironment.run_bash()    │   for_model  → _shell_records
            │           （sandbox 的 DockerEnvironment）│        │                    │
            └─ _report() / _timed_out()               │        ▼                    │
                 │                                    │   下一次 ask()：             │
                 ▼                                    │   shell_preamble + 用户问题  │
            Observation 文本回到模型                    │                            │
                 └────────────────────────────────────┘        └────────────────────┘
```

| 组件 | 代码位置 | 职责 |
|---|---|---|
| `BashTool` | `omicsclaw/tools/builtin/bash.py` | 模型的 shell：解码、审批、执行、截断、报告 |
| `BashEnvironment` | `omicsclaw/tools/builtin/bash.py` | 注入接缝：命令在哪里执行（Protocol，只有 `run_bash`） |
| `CommandOutcome` | `omicsclaw/tools/builtin/bash.py` | 一次执行的结果：`output` + `exit_code` |
| `foundation_tools` 中的 `BashTool(...)` | `omicsclaw/entry/assembly.py` | 用 `AppConfig.bash_timeout()` 与沙箱 environment 构造唯一的 `bash` |
| `_apply_bash_policy` / `bash_policy` | `omicsclaw/entry/assembly.py`、`omicsclaw/entry/sandbox.py` | 沙箱满足条件时把 `bash` 放宽为 `AUTO` |
| `PermissionGate` / `GatedTool` | `omicsclaw/permission/gate.py` | 模式、规则文件、危险命令模式 |
| `DangerPatterns` | `omicsclaw/permission/danger.py` | 对 `command` 参数做危险模式匹配，命中则升级为 ask |
| `require_approval` / `pause_tool_timeout` | `omicsclaw/tools/context.py` | 审批请求；审批等待不计入工具超时 |
| `run_shell` 等 | `omicsclaw/entry/cli/_shell.py` | `!<cmd>` 的执行、截断、上下文记录 |
| `Repl._shell` / `_with_shell_records` | `omicsclaw/entry/cli/_repl.py` | `!` 分发、显示、前置注入 |

---

## 4. `bash` 工具

### 4.1 Schema

```json
{
  "type": "object",
  "properties": {
    "command":      {"type": "string",  "description": "The bash command to run ..."},
    "timeout_secs": {"type": "integer", "description": "Optional: seconds ..., at most <limit>"}
  },
  "required": ["command"],
  "additionalProperties": false
}
```

- 模板是 `BASH_SCHEMA`；每个 `BashTool` 实例在构造时深拷贝一份，并把自己的真实超时写进
  `timeout_secs` 的描述（`_timeout_description`）与工具描述（`_description`）。
  `definition()` 始终返回同一个对象，保证缓存的 prompt 前缀字节稳定。
- 工具描述明确告诉模型：工作目录是 workspace 根；非零退出是命令自己的结果；超过
  N 秒会被杀；超长输出从中间截断；后台进程要自己重定向输出
  （`nohup cmd > out.log 2>&1 &`）；**没有 stdin**；运行前会请求批准。
- `additionalProperties: false`：多余的键会得到可操作的 schema 报错，而不是
  `TypeError`。

### 4.2 执行流程

`BashTool.execute` 的顺序是设计的一部分：**解码 → 审批 → 进度 → 执行 → 报告**。

```
execute(arguments)
  │
  ├─ _arguments(arguments)
  │     decode_arguments + validate_arguments(BASH_SCHEMA)
  │     command.strip() == ""         → ToolArgumentError
  │     timeout_secs <= 0             → ToolArgumentError（0 不被当作"未给"）
  │     timeout = min(timeout_secs, max_timeout)   # 只能缩短
  │
  ├─ cwd = resolve_workspace(self._workspace).root
  │
  ├─ await require_approval(name, arguments（原始字节）, policy, reason=_reason(...))
  │     reason 包含：完整命令、超时、执行位置
  │       沙箱：  "in this session's injected execution environment"
  │       本地：  "directly on this machine, with no OS isolation, in <cwd>"
  │
  ├─ await report_progress("running in <cwd>: <命令第一行> …")
  │
  ├─ environment is None → _locally(command, cwd, timeout)
  │  environment 存在    → _in_environment(environment, command, cwd, timeout)
  │
  └─ timed_out ? _timed_out(output, timeout) : _report(outcome)
```

`BashTool` 是手写类而非 `FunctionTool` 包装：审批提示必须展示模型**实际发送的字节**，
而一个先解码再重编码的适配器做不到这一点。

### 4.3 本地执行：`_locally`

```python
handle, capture = tempfile.mkstemp(prefix="omicsclaw-bash-", suffix=".log")
process = await asyncio.create_subprocess_exec(
    "bash", "-c", command,
    cwd=str(cwd), stdout=sink, stderr=sink,
    stdin=asyncio.subprocess.DEVNULL,
)
```

四个刻意的选择：

1. **输出写临时文件，不写管道。** 管道的读端要等所有写端关闭；`A && B &` 会让后台孙进程
   持有写端，调用一直阻塞。改为文件后，`process.wait()` 只等 `bash -c` 本身。
   `bash.py` 的 docstring 记录了本机测量：`bash -c 'echo hi && sleep 30 &'` 用
   `PIPE` 在 6 s 测试截止时仍阻塞，用临时文件 0.003 s 返回；
   `tests/tools/test_bash.py::test_a_backgrounded_command_returns_in_milliseconds` 钉住这一点。
2. **`bash` 而非 `/bin/sh`。** 用 `create_subprocess_exec("bash", ...)` 而不是
   `create_subprocess_shell`——Debian/Ubuntu 的 `/bin/sh` 是 `dash`，没有 `[[ ]]`、
   数组与 `pipefail`。
3. **`stdin=DEVNULL`。** 读 stdin 的命令立即看到 EOF，而不是阻塞到超时；在 CLI 上，
   继承来的 stdin 就是用户的终端，子进程会和人抢键盘。
4. **临时文件在所有退出路径上删除**（含取消），因此后台进程之后写的是一个已 unlink
   的 inode——这正是描述里要求模型自己重定向后台输出的原因。

启动失败（`bash` 不在 `PATH` 或 workspace 目录不存在）由 `_start` 抛
`RuntimeError`，因为这是部署问题而不是模型能改的参数。

### 4.4 超时

超时由三个数字构成，只有一个是独立配置的：

```
AppConfig.tool_timeout_s = 600           (--tool-timeout / OMICSCLAW_TOOL_TIMEOUT_S)
   ├─ AppConfig.engine_config().tool_timeout = 600      引擎包住整个 tool call
   └─ AppConfig.bash_timeout() = 600 - ENGINE_TIMEOUT_MARGIN(15) = 585
          └─ BashTool.timeout = 585 = BashTool.max_timeout
                 └─ timeout_secs 只能 ≤ 585
```

- **单一来源。** `tool_timeout_s` 在 `omicsclaw/entry/config.py` 定义，默认 600 s
  （owner 裁定：`spatial-deconv` 或 STAR 比对要跑数分钟到数小时）。引擎的
  `EngineConfig.tool_timeout` 与 `bash` 的预算都从它派生；`ENGINE_TIMEOUT_MARGIN`
  从 `bash.py` 导入而非重抄。
- **留 15 s 余量**，让 `bash` 自己的截止先到：模型读到的是 `[TIMEOUT …]` 横幅，
  而不是引擎的 `tool 'bash' timed out after 600s`。
- **裸构造的默认值是 45 s**（`DEFAULT_TIMEOUT = 60 - 15`），对应 `EngineConfig`
  自身默认的 `tool_timeout = 60.0`。只有不经 `omicsclaw/entry/` 装配、直接
  `BashTool(workspace)` 的调用方才会遇到它。
- **`timeout_secs` 只能缩短。** `max_timeout` 就是 `self.timeout`，请求更大值被
  `min()` 截到上限；schema 描述与超时横幅都如实写明这一点。
- **审批不计时。** `require_approval` 在 `pause_tool_timeout()` 里等待审批通道，
  引擎通过 `TimeoutPause` 停表，人思考的时间不会被算作命令超时。

超时后的本地路径：`asyncio.timeout` 触发 → `_kill` 发 SIGKILL 并再次 `wait()`
回收（避免僵尸）→ 读回已写出的部分输出 → `_timed_out` 先截断再追加横幅：

```
<截断后的部分输出>

[TIMEOUT 585s: the command was killed for running past its time limit. This is not
an error in your code, and anything above is only what it had printed by then. If this
was a test suite or an install, run a single test or narrow the command — timeout_secs
can only shorten this limit, never extend it.]
```

"先截断再加横幅"保证横幅永远不会是被截掉的那部分。

### 4.5 输出截断

| 常量 | 值 | 含义 |
|---|---|---|
| `MAX_OUTPUT_CHARS` | 16,000 | 返回给模型的上限，按**字符**计 |
| `HEAD_CHARS` | 5,333（`MAX_OUTPUT_CHARS // 3`） | 保留的开头 |
| `TAIL_CHARS` | 10,667 | 保留的结尾 |

- 字节先用 `errors="replace"` **一次性**解码为 `str` 再测量与切片（`_read_back`），
  因此不可能切断多字节字符。
- 尾部占 2/3：测试运行器、安装器、编译器都把结论打印在最后。组学 skill 脚本同理——
  进度日志在前，报错 traceback 与最终的输出路径在后。
- 中间被省略时插入
  `...[Output too long: N characters from the middle were cut. ...]...`。
- 这只是**单次 Observation** 的上限。对话中已经读过的、超过 `Offloader.min_tokens`
  （默认 1000 token）的工具结果，会在压缩时由 `omicsclaw/context/offload.py` 移到
  `<workspace>/.omicsclaw/tool_results/` 并替换为占位符，详见上下文工程文档。

### 4.6 结果语义

`_report` 与 `_exit_status` 决定模型看到的文本：

| 情况 | 返回文本 | `is_error` |
|---|---|---|
| 退出 0，有输出 | 截断后的输出 | 否 |
| 退出 0，无输出 | `The command finished successfully with no terminal output.` | 否 |
| 退出非 0，有输出 | `[exit status N]\n<输出>` | 否 |
| 退出非 0，无输出 | `[exit status N] The command failed and printed nothing.` | 否 |
| 被信号杀死 | 同上，`N = 128 + signum`（SIGKILL → 137，SIGTERM → 143） | 否 |
| 超时 | 部分输出 + `[TIMEOUT …]` 横幅 | 否 |

判定标准是"**模型下一步该改什么**"：非零退出说明命令所针对的东西有问题（测试失败、
skill 参数不对），调用本身没错，因此不标 `is_error`。反之：

| 异常 | 来源 | 结果 |
|---|---|---|
| `ToolArgumentError` | 参数解不开、不合 schema、空命令、`timeout_secs <= 0` | registry 转成 `is_error=True`，模型改参数重发 |
| `ApprovalDenied` / `ApprovalUnavailable` | 用户拒绝，或未绑定审批通道（fail closed） | `is_error=True`，命令没有运行 |
| `RuntimeError` | 本地无法启动 `bash`；或注入的 environment 抛 `OSError`（如 `SandboxError`） | `is_error=True` |
| `asyncio.CancelledError` | 回合被放弃 | 本地子进程被 SIGKILL 后**原样上抛**，不被捕获 |

`asyncio.subprocess` 把信号报告为负数返回码；`_exit_status` 统一换成 shell 的
`128 + signum`，并对注入 environment 的返回值同样执行一次——防止出现"被信号杀死的
进程被报告为成功"这一类 bug（`bash.py` docstring 中的 trap 16）。

### 4.7 取消

`bash.py` 全文没有 `except Exception` / `except BaseException`。唯一被**点名**的
`CancelledError` 分支在 `_locally` 里：对子进程发 SIGKILL，然后原样 `raise`。
`tests/tools/test_bash.py::test_a_cancelled_turn_does_not_leave_its_subprocess_running`
与 `test_a_cancelled_turn_leaves_no_capture_file_behind` 覆盖这一路径。

### 4.8 `BashEnvironment` 接缝

```python
@runtime_checkable
class BashEnvironment(Protocol):
    async def run_bash(self, command: str, cwd: str, timeout: float) -> CommandOutcome: ...
```

- `environment=None` 表示本机；传入实现后，`_in_environment` 等待
  `environment.run_bash(...)` 而不是启动本地进程。
- 实现方的两项义务：必须在 `cwd`（workspace 根）执行；`timeout` 既**传入**（让实现能
  干净收尾），又由工具用 `asyncio.timeout(timeout)` **强制**（防止实现拖垮引擎预算）。
- 只有真正触发的那个截止才能声称超时：`budget.expired()` 为假的 `TimeoutError`
  会原样上抛，不会被误报成 `[TIMEOUT …]`。
- 在 environment 路径上超时，只有横幅没有部分输出（`_KILLED_BY_DEADLINE`，
  `exit_code=137`）。
- 当前唯一的生产实现是 `omicsclaw.sandbox.DockerEnvironment`，它**结构化满足**该
  Protocol（返回的 `ExecResult` 是 `CommandOutcome` 字段的超集），并不 import
  `omicsclaw.tools`。详见 [sandbox.md](sandbox.md)。

### 4.9 审批与权限

`bash` 的声明策略（`_POLICY`）：

| 字段 | 值 | 理由 |
|---|---|---|
| `risk_level` | `HIGH` | 可以读、改、删这个进程能碰到的一切 |
| `approval_mode` | `ASK` | 沙箱关闭时，人是唯一的边界 |
| `prompts_for_itself` | `True` | 由工具自己发起审批，提示里带完整命令 |
| `read_only` | `False` | `--permission-mode read-only` 下被拒绝 |
| `concurrency_safe` | `False` | 两个 shell 共享文件系统和端口，无路径可锁 |
| `writes_workspace` | `True` | 大多数有用命令都会写 |
| `allowed_in_background` | `False` | 无人值守的回合里没有人 |

装配后 `bash` 被包成 `GatedTool(HookedTool(BashTool))`，一次调用的决策顺序在
`PermissionGate.resolve`（`omicsclaw/permission/gate.py`）中，先命中者生效：

1. `bypass-all` 模式 → 放行；
2. `read-only` 模式 → 拒绝（`bash` 未声明 `read_only`）；
3. 命令会改动 `.omicsclaw/`、规则文件或 `.env` → 必问；
4. 规则文件（`deny` → `allow` → `ask`）；
5. `DangerPatterns` 对 `command` 参数匹配（`DEFAULT_DANGER_PATTERNS`，大小写不敏感，
   命中只会升级为 ask，永不直接 deny）；
6. `auto-approve` 模式 → 放行；
7. 工具自己的 `approval_mode`：`ASK` 则提问，`AUTO` 则放行。

结果为 ask 且来源不是危险模式或受保护路径时，闸门"让开"，由 `BashTool` 自己调用
`require_approval` 提问；危险模式与受保护路径由闸门亲自提问。未绑定审批通道时
`require_approval` 抛 `ApprovalUnavailable`——**没有通道不等于同意**。

**沙箱对审批的影响**：`sandbox_auto_approve=true` 且沙箱在运行、网络为 `none`、
`bash` 是装配层自己构造的那一个时，`_apply_bash_policy` 把第 7 步的
`approval_mode` 改成 `AUTO`。第 1–5 步不受影响：危险命令与 `ask` 规则仍然提问。
细节见 [sandbox.md](sandbox.md#7-审批与权限的关系)。

### 4.10 交互式命令

`bash` 工具**不做命令名拦截**。它的处理方式是结构性的：

- `stdin` 是 `/dev/null`，`read`、`python -i`、`Rscript -e 'readline()'`、`git` 的交互式
  确认等立即看到 EOF；工具描述要求模型用参数、heredoc 或文件提供输入；
- 需要 TTY 的全屏程序（`vim`、`less`）没有终端可用，通常很快报错退出；
- 真正卡住的命令由超时兜底（默认 585 s）。

### 4.11 示例：运行一个组学 skill

模型先 `use_skill("spatial-preprocess")` 拿到 SKILL.md 与目录，然后：

```json
{"name": "bash",
 "arguments": "{\"command\": \"python skills/spatial/spatial-preprocess/spatial_preprocess.py --demo --output output/preprocess_demo\"}"}
```

- 相对路径相对 workspace 根解析（`test_a_relative_path_in_a_command_lands_in_the_workspace`）；
- 审批卡片展示完整命令与 585 s 限制；用户在 CLI 按 `y` / `s` / `a` 放行；
- 脚本打印的数万行进度日志被截到 16,000 字符，结尾的报错或"结果写入 …"保留；
- 脚本以非零状态退出时，模型看到 `[exit status 1]` + traceback，据此修正参数，而不是
  认为工具坏了；
- 超过 585 s 的长任务应让模型用 `nohup … > run.log 2>&1 &` 放到后台，再用 `bash`
  轮询 `tail run.log`——后台进程在调用返回后继续运行（本地路径超时只杀直接子进程）。

---

## 5. CLI `!<cmd>`：操作者的直连 shell

### 5.1 交互流程

```
REPL 输入 "!head -n 3 results/de.csv"
    │
    ▼
Repl._dispatch(text)
    text.startswith("!")  → 在 slash 命令目录之前拦截
    │
    ▼
Repl._shell(text[1:].strip())
    ├── 空命令（单独一个 "!"）      → 什么也不做、什么也不说
    ├── 打印 "$ head -n 3 results/de.csv"（bold cyan）
    ├── wants_a_terminal(command) → 打印 "This one wants a terminal of its own;
    │                                 run it in another window."，不执行
    └── await run_shell(command, cwd=app.config.workspace, timeout_s=SHELL_TIMEOUT_S)
            │   bash -c command
            │   stdin=DEVNULL, stdout=PIPE, stderr=STDOUT, start_new_session=True
            │   asyncio.wait_for(process.communicate(), 60)
            ▼
        ShellResult(command, output, failed, duration_s, timed_out)
            │
            ├── 屏幕：for_display(output)  ≤ 4096 字节（dim）
            ├── 状态行：_shell_status(result)
            │     ✓ done — 0.02s                                     (green)
            │     ✗ non-zero exit — 0.10s                            (red)
            │     ✗ killed after 60.0s — it was still running, ...   (red)
            └── self._shell_records.append(for_model(result))  ≤ 2048 字节
```

用户下一次提问时，`Repl.ask` 调用 `_with_shell_records(text)`：

```
[Shell commands run by the operator at the terminal]
$ head -n 3 results/de.csv
gene,log2fc,padj
...
---
$ ls output/ (timed out after 60s)
...

<用户的实际问题>
```

记录在读取时清空，每条命令只报告一次。标题 `SHELL_RECORD_HEADER` 明确"是谁执行的"，
避免模型把一段用户消息里的命令记录当成"请执行这些命令"的指令。

### 5.2 常量

| 常量 | 值 | 说明 |
|---|---|---|
| `SHELL_TIMEOUT_S` | `60.0` | `!` 命令的上限；与 `tool_timeout_s` / `bash_timeout()` 无关 |
| `DISPLAY_LIMIT` | `4096` 字节 | 屏幕显示上限 |
| `CONTEXT_LIMIT` | `2048` 字节 | 进入模型上下文的上限（记录会累积，故更小） |
| `SHELL_RECORD_HEADER` | `[Shell commands run by the operator at the terminal]` | 前置块的首行 |
| `NEEDS_A_TERMINAL` | `emacs htop less man more nano screen ssh tmux top vi vim watch` | 13 个名字 |

截断使用 `omicsclaw.memory.truncate_utf8`（`omicsclaw/memory/precis.py`）：按 UTF-8
字节截断、只在字符边界切、被截断时追加 `TRUNCATION_MARKER`（`"\n…(truncated)"`）。
两处截断都带同一个标记。

### 5.3 为什么不审批、为什么是 60 秒

- **不过权限闸门。** 敲 `!rm -rf build` 的人本来就有这台机器的 shell；闸门防的是
  **模型**提出的命令，而没有任何命令会从模型流到这个模块。
- **独立的短超时。** `bash_timeout()` 以分钟计，是为无人盯着的反卷积、比对准备的；
  `!` 是一个人盯着光标等结果，所以是单独的常量。需要跑十分钟的，开第二个终端。

### 5.4 交互式命令：名单是礼貌，超时才是保证

`wants_a_terminal` 只看第一个词的 `os.path.basename`（所以 `/usr/bin/vim` 能拦住），
`echo hi && vim`、`bash -c vim`、会打开 `$EDITOR` 的 `git commit` 都会漏过去。
漏过的代价由结构兜底：

- `stdin=/dev/null`，子进程无法和 REPL 抢键盘；
- `start_new_session=True`，子进程在自己的会话 / 进程组里；
- 超时后 `_kill_the_group` 对整个进程组发 `SIGKILL`（失败时退回 `process.kill()`），
  `bash -c 'sleep 60 | cat'` 这类留下多个子进程的命令也不会遗留持有管道的进程；
- `_drain` 在杀掉后再 `communicate()` 一次，收集已写出的部分输出，失败则返回空。

`run_shell` 从不为命令本身抛异常：非零退出、被杀、连 shell 都起不来，都返回
`failed=True` 的 `ShellResult`。

### 5.5 作用范围

- 只在 `oc cli` 的交互式 REPL 中生效（`Repl._dispatch`）。`oc cli --prompt` /
  `--prompt-file` 直接调用 `repl.ask(text)`，以 `!` 开头的文本会作为普通问题发给模型。
- `oc desktop` 与 `oc channel` 没有 `!` 通道。
- `!` 命令始终在**宿主**上、以 `AppConfig.workspace` 为工作目录执行，**不进沙箱容器**，
  即使 `OMICSCLAW_SANDBOX=docker`。

---

## 6. 关键设计决策

| 决策 | 理由 |
|---|---|
| 模型的 `bash` 写临时文件，`!` 用管道 + 进程组 | `bash` 要保留后台进程（`nohup … &` 是长任务的正道），所以不能靠杀进程组解除管道阻塞；`!` 的超时短且整组杀掉，管道足够 |
| 本地 `bash` 超时只杀直接子进程 | 杀进程组会连同模型刻意放到后台的进程一起杀掉；代价是 `bash -c 'sleep 30; echo'` 超时后 `sleep` 成为孤儿 |
| 非零退出不是 `is_error` | 模型应去修命令针对的对象，而不是怀疑工具 |
| 空命令是 `ToolArgumentError` | 以普通字符串返回错误会让错误伪装成成功；保留检测，改变报告方式 |
| 超时预算从 `tool_timeout_s` 派生 | 两个独立字面量迟早会只改一个（plan 0031 §12-2） |
| 审批提示展示完整命令 | 摘要正是 `; rm -rf ~` 藏身之处 |
| `BashEnvironment` 只有一个方法 | 与 `FileReadEnvironment` / `FileWriteEnvironment` 同样按能力切分；测试替身不必伪造文件系统 |

参考：plan 0029（foundation tools，Q2–Q6、Q11 与 traps 5/6/13–16）、plan 0031 §12-2
（600 s 裁定）、plan 0036（沙箱）、plan 0038（权限）。

---

## 7. 配置参数

| 配置 | 旗标 / 环境变量 | 默认 | 影响 |
|---|---|---|---|
| `AppConfig.tool_timeout_s` | `--tool-timeout` / `OMICSCLAW_TOOL_TIMEOUT_S` | `600.0` | 引擎每次 tool call 的上限；`bash` 预算 = 该值 − 15 |
| `AppConfig.workspace` | `--workspace` / `OMICSCLAW_WORKSPACE` | 当前目录 | `bash` 与 `!` 的工作目录 |
| `AppConfig.permission_mode` | `--permission-mode` / `OMICSCLAW_PERMISSION_MODE` | `default` | 见 4.9；CLI 的 `/auto` 写入 `OMICSCLAW_CLI_PERMISSION_MODE` |
| `AppConfig.sandbox` 等 | `--sandbox` / `OMICSCLAW_SANDBOX` … | `off` | `bash` 是否进容器，见 [sandbox.md](sandbox.md) |
| `SHELL_TIMEOUT_S` | 无（模块常量；`Repl(shell_timeout_s=...)` 可覆盖，仅测试使用） | `60.0` | `!` 的上限 |

`OMICSCLAW_TOOL_TIMEOUT_S` 的非法值（例如 `6OO`）会抛 `AppConfigError`，而不是静默
回落到默认值。

---

## 8. 已知限制

- **整段输出先读入内存再截断。** 输出 GB 级的命令是一次内存事件，16,000 字符的上限
  挡不住（`bash.py` docstring "Two residuals"）。
- **本地超时只杀直接子进程**，`bash -c 'sleep 30; echo'` 超时后 `sleep` 成为孤儿。
- **沙箱路径超时时没有部分输出**，只有横幅（`_KILLED_BY_DEADLINE`）。
- **`timeout_secs` 只能缩短。** 真正需要"这条命令给我 1 小时"时，只能由运维调大
  `tool_timeout_s`（对所有工具生效），或让模型改用 `nohup … &` 后台运行再轮询；
  `TimeoutPause` 不带参数，无法表达"延长到 N 秒"（FRAMEWORK-REBUILD.md
  "Open, and named so it is not rediscovered"）。
- **审批等待无上限。** `pause_tool_timeout` 只停表不限时，永不回答的审批通道会让调用
  一直阻塞；Desktop 未移植 `/chat/permission`，需要审批的 `bash` 在该 surface 上会
  挂到超时（FRAMEWORK-REBUILD.md Step 6 debts）。
- **`bash` 与 `bash` 之间不并发**（`concurrency_safe=False`），一回合里多个 `bash`
  调用串行执行。
- **`bash.py` 的部分 docstring 早于 step 6.7 / 6.8**：模块 docstring 的
  "No OS isolation ships with this" 与 `_POLICY` docstring 的 "nothing in production
  binds a channel yet" 已不再成立（沙箱已交付，CLI 已绑定审批通道），
  `ENGINE_TIMEOUT_MARGIN` docstring 关于"人思考时间计入 60 s"的论述也已被
  `pause_tool_timeout` 解决。以代码为准。
- **`!` 的交互式名单只看第一个词**，漏网的命令靠 60 s 超时兜底。
- **`!cmd &` 会等满 60 s。** `!` 走管道，后台进程持有写端时 `communicate()` 不会
  返回，直到超时整组被杀（由代码推断；后台任务请交给模型的 `bash` 并自行重定向）。
- **`!` 不进沙箱**，也没有审批；它等价于操作者自己的终端。

---

## 9. 测试

| 测试 | 覆盖 |
|---|---|
| `tests/tools/test_bash.py`（72 个） | 截断比例与单位、后台进程毫秒返回、信号退出码、非零退出语义、超时横幅顺序、`timeout_secs` 只缩不涨、取消后无残留进程与捕获文件、审批提示内容、environment 接缝（归一、截断、超时归属、取消） |
| `tests/tools/test_bash.py::test_the_default_budget_leaves_room_inside_the_engines` | 同时 import `EngineConfig` 与 `DEFAULT_TIMEOUT` 断言 45 + 15 = 60——这层耦合只靠测试维持 |
| `tests/entry/test_cli_shell.py` | `!` 不触达模型、失败显示、裸 `!`、屏幕与模型截断不同、记录只注入下一次、超时杀整组、交互式命令拒绝、工作目录 |
| `tests/entry/test_sandbox.py` | `bash` 在沙箱中执行、`sandbox_auto_approve` 的放宽条件 |

运行（`pytest` 只在该环境中可用）：

```bash
/opt/conda/envs/rapids_singlecell/bin/python -m pytest tests/tools/test_bash.py \
    tests/entry/test_cli_shell.py -p no:cacheprovider -q -o addopts=""
```

`tests/tools/test_bash.py::test_a_cancelled_turn_leaves_no_capture_file_behind` 是已登记
的负载敏感 flake：失败时单独重跑并重跑整个目录，再判断是否回归。

---

## 10. 文件索引

| 内容 | 文件 | 符号 |
|---|---|---|
| `bash` 工具 | `omicsclaw/tools/builtin/bash.py` | `BashTool`、`BASH_SCHEMA`、`_POLICY` |
| 常量 | `omicsclaw/tools/builtin/bash.py` | `MAX_OUTPUT_CHARS`、`HEAD_CHARS`、`TAIL_CHARS`、`DEFAULT_TIMEOUT`、`ENGINE_TIMEOUT_MARGIN` |
| 本地执行 | `omicsclaw/tools/builtin/bash.py` | `_locally`、`_start`、`_kill`、`_signal`、`_read_back` |
| 注入执行 | `omicsclaw/tools/builtin/bash.py` | `BashEnvironment`、`CommandOutcome`、`_in_environment`、`_KILLED_BY_DEADLINE` |
| 结果渲染 | `omicsclaw/tools/builtin/bash.py` | `_report`、`_truncate`、`_timed_out`、`_timeout_banner`、`_exit_status` |
| 工作区解析 | `omicsclaw/tools/builtin/read.py`、`omicsclaw/tools/_workspace.py` | `resolve_workspace`、`Workspace` |
| 审批与停表 | `omicsclaw/tools/context.py` | `require_approval`、`pause_tool_timeout`、`ApprovalDenied`、`ApprovalUnavailable` |
| 引擎超时 | `omicsclaw/engine/executor.py`、`omicsclaw/engine/config.py` | `_execute`、`DeadlineAwareExecutor`、`EngineConfig.tool_timeout` |
| 超时单一来源 | `omicsclaw/entry/config.py` | `AppConfig.tool_timeout_s`、`AppConfig.engine_config`、`AppConfig.bash_timeout` |
| 装配 | `omicsclaw/entry/assembly.py` | `foundation_tools`（构造 `BashTool`）、`_apply_bash_policy`、`_is_bash` |
| 权限闸门 | `omicsclaw/permission/gate.py`、`omicsclaw/permission/danger.py`、`omicsclaw/hooks/chain.py` | `PermissionGate.resolve`、`GatedTool`、`HookedTool`、`DangerPatterns`、`DEFAULT_DANGER_PATTERNS` |
| `!` 执行 | `omicsclaw/entry/cli/_shell.py` | `run_shell`、`ShellResult`、`wants_a_terminal`、`for_display`、`for_model`、`shell_preamble`、`_kill_the_group`、`_drain` |
| `!` 常量 | `omicsclaw/entry/cli/_shell.py` | `SHELL_TIMEOUT_S`、`DISPLAY_LIMIT`、`CONTEXT_LIMIT`、`SHELL_RECORD_HEADER`、`NEEDS_A_TERMINAL` |
| `!` 分发与注入 | `omicsclaw/entry/cli/_repl.py` | `Repl._dispatch`、`Repl._shell`、`Repl._with_shell_records`、`_shell_status` |
| UTF-8 截断 | `omicsclaw/memory/precis.py` | `truncate_utf8`、`TRUNCATION_MARKER` |
| 测试 | `tests/tools/test_bash.py`、`tests/entry/test_cli_shell.py`、`tests/entry/test_sandbox.py` | — |
