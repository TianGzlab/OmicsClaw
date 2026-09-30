# 计划 0050 — CLI 的 `/auto`：当场切换，并写入只作用于 CLI 的 `.env` 键

**状态**：**已实现**（2026-09-23）。初稿经一轮独立只读审核（"需修改后实施"，
9 条必须修正），owner 对各项决定按建议裁定（§9），据此返工后实现；实现后又经
一轮代码审查，4 条必须修复均已修复（§11）。
验证：整栈 **5127 passed, 12 skipped**，另 1 项为已知时序敏感测试
`test_websafety.py::test_a_server_dripping_bytes_cannot_outlast_the_budget`（与本
改动无关，审查独立确认）。9 个定点变异全部被测试捕获。真实进程验收在临时目录
下进行，仓库根 `.env` 前后校验和一致。

**前置**：计划 0049 已交付，含其交付后修补的 `.env` 保护（0049 §13.4）——
本计划依赖它：`auto-approve` 下模型仍然不能不经询问改写规则文件或 `.env`。

---

## 1. 目标

| 命令 | 当场 | 写入 `.env` |
|---|---|---|
| `/auto`、`/auto on` | 闸门切到 `auto-approve` | `OMICSCLAW_CLI_PERMISSION_MODE=auto-approve` |
| `/auto off` | 闸门切回 `default` | `OMICSCLAW_CLI_PERMISSION_MODE=default`（**显式写**，不删键） |
| `/auto status` | 不变 | 不变；报告当前模式、文件里的值、下次启动会被什么覆盖、沙箱状态 |
| 其他参数 | **拒绝**（大小写折叠后只认 空/on/off/status） | 不变 |

在审批提示处直接输入 `/auto`：切换，并对这张卡片按 auto-approve 的结果处理
——普通卡片放行，"每次都问"的卡片重新询问（§3.5）。

## 2. 为什么是只作用于 CLI 的键（owner 裁定，审核 M2）

`.env` 由三个入口共用（`launch/__init__.py:122-124`）。写通用的
`OMICSCLAW_PERMISSION_MODE` 会让 `oc channel` 下次启动也进入 `auto-approve`：
Channel 是无人值守的 IM 机器人，default 模式下审批超时即拒绝
（`entry/channel/runtime.py:266-280`），切换后这些询问会静默放行；Desktop 的
`/chat/permission` 尚未移植。

新键 `OMICSCLAW_CLI_PERMISSION_MODE` 只由 `start_cli` 读取。启动时 CLI 的模式
优先级：

1. `--permission-mode` 标志
2. `OMICSCLAW_PERMISSION_MODE`（导出的或来自 `.env`，**部署级显式设置永远优先**）
3. `OMICSCLAW_CLI_PERMISSION_MODE`
4. `default`

实现：`start_cli` 在通用键为空、CLI 键非空时，把 CLI 键的值作为
`OMICSCLAW_PERMISSION_MODE` 放进交给 `resolve_app_config` 的 env 映射副本——
argv 仍然晚于 env，标志照旧优先。非法值以 `OMICSCLAW_CLI_PERMISSION_MODE` 的
名字报错（退出码 2）。只读传入的 `env` 映射，不碰进程全局量。

**这也消掉了初稿 §3.4 的判定难题（审核 M5）**：不必区分"导出"与"来自
`.env`"——通用键无论来自哪里都会遮住 CLI 键，所以"被遮住"只需看 env 映射里
通用键是否非空；"被标志固定"由 `omicsclaw/entry/config.py` 新增的公开函数
`fields_set_by_argv(argv)` 判断（复用 `_from_argv`），launch 层不写任何部署标志
字面量。二者作为 `permission_mode_source`（`"flag"` / `"environment"` /
`"cli-key"` / `""`）传给 `Repl`。

## 3. 设计

### 3.1 闸门与 app

- `PermissionGate.set_mode(mode) -> PermissionMode`：纯机制，返回旧值；`mode`
  及 `modes.py` 的 docstring 改为"启动时设定，操作者可在会话中切换"。
- `AgentApp.set_permission_mode(mode) -> PermissionMode | None`：**转换规则在这
  里强制**（审核 S2），不只靠 REPL——只允许 `default ↔ auto-approve`，其余抛
  `ValueError`；`permission is None` 返回 `None`；每次切换打一条 warning
  日志"旧 → 新，由操作者切换"（审核 S3），因为审计记录里没有模式字段。

### 3.2 运行时与持久化分开判定（审核 M7）

- 运行时：按**闸门当前模式**。`read-only` / `bypass-all` 下拒绝切换。
- 持久化：按**文件里 CLI 键的当前值**。值为 `read-only` / `bypass-all` 时拒绝
  覆盖（那是有人写下的承诺），说明原因；运行时部分照常执行或拒绝，各自报告。
- `/auto` 在运行时已是 `auto-approve` 时仍然写文件（"等同于编辑 `.env`"），反之
  `/auto off` 同理。

### 3.3 写 `.env`（审核 M3、S10 加固 `write_dotenv`，wizard 一并受益）

- **只有 `FileNotFoundError` 视为空文件**；其他读取错误（权限、非 UTF-8）一律
  中止、不写。原实现 `except OSError: original = ""` 会在读不到时用一行内容整份
  覆盖凭据文件。
- **软链接**：写入解析后的真实路径，保留链接本身。
- **临时文件**：`tempfile.mkstemp`（`O_EXCL`、0600、唯一名称）创建，写完再按原
  文件权限 chmod、原子替换；任何失败删除临时文件。原实现先按 umask 建
  `.env.partial` 再 chmod，存在凭据全员可读的窗口，且多进程共用同一个名字。
- 新增 `backup: bool = True`；`/auto` 传 `False`——来回切换不应在仓库根散落多份
  含 API key 的副本。wizard 行为不变。
- 已知且接受：CRLF 会被规范为 LF；`export<Tab>KEY=` 形式的行不被识别（审核
  O1、O2，均为既有行为）。
- `/auto` 的处理器捕获 `(OSError, ValueError)`：写入失败时**当场切换照样生效**，
  屏幕报告失败——与 `_remember` 一致。

### 3.4 路径

`Repl` 新增构造参数 `dotenv_path: Path | None = None`、
`permission_mode_source: str = ""`；`_run_cli` 新增同名关键字参数并带默认值
（`tests/launch/test_surfaces.py` 以 `_run_cli(object(), ReplOptions())` 调用，
审核 S8）。`start_cli` 传入 `dotenv_target()`。`dotenv_path is None` 时当场切换
照常，并说明这次运行没有可写的 `.env`。

`run_once`（`--prompt`）不走斜杠命令分发，`--prompt /auto` 会作为问题发给模型；
不为它做特殊处理（审核 S7）。

### 3.5 审批提示处的 `/auto`（owner 裁定，审核 M4）

今天审批提示读到的任何非 y/s/a 回答都算拒绝，且原文作为拒绝理由发给模型——
输入 `/auto` 会拒绝这条调用并告诉模型"/auto"。改为：

- 回答是 `/auto`（或 `/auto on`）：执行与命令相同的切换；若切换后闸门为
  `auto-approve` 且这张卡片**未**标记 `ask_every_time`，放行（auto-approve 本来
  就会放行它）；否则**重新询问这一张**（打印对应图例）。切换被拒绝时同样重新
  询问。
- 其他以 `/` 开头的回答：照旧拒绝，但**不把原文作为拒绝理由**发给模型，理由
  写 "denied at the terminal"。

### 3.6 提示文字（审核 S4、S6、S9、O6）

每次 `/auto` 打开都打印（成本极低，不做"只打印一次"）：普通调用不再询问；
危险命令、显式 `ask` 规则、`deny` 规则、`.omicsclaw/` 与 `.env` 的改动照旧；
危险模式是黑名单，边界是沙箱——按 `app.sandbox.active` / `degraded` 报告
沙箱实际状态，而不是配置值；作用于**整个进程**（`/new`、`/resume` 不重置），
不同于按会话的 `s`；只作用于 `oc cli`。

### 3.7 让人找得到它（审核 S1、S5、S11）

- `/auto` 进入 `_constants.py` 的 `ADDED_SLASH_COMMANDS` 与 REPL 子集；"端口保真
  测试"已删除，不存在需要更新的冻结测试。
- `/current` 从 `app.permission.mode` 读当前模式——`app.config.permission_mode`
  是冻结的启动值，切换后过时。
- 普通卡片图例追加 ` · /auto stops these`，**仅当闸门处于 `default`** 且卡片未
  标记时显示。

## 4. 非目标

- Channel / Desktop 不加命令，且**不受影响**（它们不读 CLI 键）。
- 会话中不能切到或切出 `read-only` / `bypass-all`。
- 不改通用键与标志的优先级。
- 不保护 `SOUL.md` / `CLAUDE.md` / `.git/hooks` 等通用持久化点（0049 §13.4）。

## 5. 改动清单

| 文件 | 改动 |
|---|---|
| `omicsclaw/permission/gate.py`、`modes.py` | `set_mode`；docstring |
| `omicsclaw/entry/assembly.py` | `AgentApp.set_permission_mode`；类 docstring |
| `omicsclaw/entry/config.py` | 公开 `fields_set_by_argv` |
| `omicsclaw/entry/cli/_configure.py` | `write_dotenv` 加固与 `backup` 参数 |
| `omicsclaw/entry/cli/_repl.py` | `/auto`、审批提示处的 `/auto`、`/current`、图例 |
| `omicsclaw/entry/cli/_constants.py`、`_slash_command_support.py` | 目录 |
| `omicsclaw/launch/_surfaces.py` | CLI 键的读取与优先级、`permission_mode_source`、传路径 |
| `.env.example`、`tests/test_env_example.py` | 记录新键 |
| `README.md`、`CLAUDE.md`、`AGENTS.md` | 命令表与说明 |

## 6. 测试

| 测试 | 断言 |
|---|---|
| 当场生效 | `/auto` 后普通调用不再询问；`/auto off` 后恢复 |
| 写入 | `/auto` 后文件含 `OMICSCLAW_CLI_PERMISSION_MODE=auto-approve`，其他行不变；`/auto off` 后为 `=default` |
| 不产生备份 | 两次切换后无 `.env.backup-*` |
| 仍询问 | `/auto` 后危险命令、写 `.omicsclaw/settings.json`、写 `.env` 仍询问 |
| 拒绝 | `read-only` / `bypass-all` 下运行时不变；文件里 CLI 键为 `read-only` 时不覆盖 |
| 参数 | `/auto of`、`/auto yes` 被拒绝且模式不变 |
| 审批提示处 | 输入 `/auto` 后该普通卡片放行、模式已切换；危险卡片被重新询问；`/foo` 拒绝且理由不含原文 |
| 优先级 | 只有 CLI 键 → 生效；通用键存在 → 通用键优先；标志 → 标志优先；非法 CLI 值 → 退出码 2 且报错点名 CLI 键 |
| 其他入口 | `oc channel` / `oc desktop` 的解析不读 CLI 键 |
| `write_dotenv` | 读取 PermissionError 时不写且原文件不变；非 UTF-8 时不写；软链接目标被更新、链接保留；新文件 0600；失败不留临时文件 |
| 图例与 `/current` | 仅 default 下出现 `/auto stops these`；`/current` 报告切换后的模式 |
| 仓库根 `.env` | 所有测试写 `tmp_path`；对真实 `.env` 前后校验和一致 |
| `app` 转换规则 | `set_permission_mode(READ_ONLY)` 抛 `ValueError` |

## 7. 验证

```bash
/opt/conda/envs/rapids_singlecell/bin/python -m pytest \
  tests/permission tests/entry tests/launch -q -p no:randomly \
  -p no:cacheprovider -o addopts=""
```

整栈回归后，手工验收**同时** `cd` 到临时目录并把 `OMICSCLAW_DIR` 指向它
（审核 M9：只设 `OMICSCLAW_DIR`、cwd 仍在仓库根时 `dotenv_target()` 返回的就是
真实 `.env`），并对真实 `.env` 做前后校验和比对。

## 8. 风险

| 风险 | 缓解 |
|---|---|
| `/auto` 被当成安全开关 | §3.6 每次打开都说清，且报告沙箱实际状态 |
| 写坏凭据文件 | §3.3 加固；每种失败方式一条测试 |
| 影响无人值守的 Channel | §2 只作用于 CLI 的键 |
| 模型诱导人输入 `/auto` | 与诱导人按 `s` 同类，人是最后一道 |
| 回滚 | 删命令处理、`set_mode` 与 CLI 键读取；`.env` 里多出的一行无害 |

## 9. owner 裁定（2026-09-23）

| # | 问题 | 裁定 |
|---|---|---|
| 1 | 初稿 §1：当场生效且写 `.env` | 是 |
| 2 | 初稿 §3.2：会话中不能切换 read-only / bypass-all | 是 |
| 3 | 初稿 §3.3：`/auto` 写入不生成备份 | 是 |
| 4 | 审核 M1：0049 的 `.env` 漏洞 | 保护决定权限姿态的文件（已修补，见 0049 §13.4） |
| 5 | 审核 M2：作用范围 | 只作用于 CLI 的键 |
| 6 | 审核 M4：审批提示处输入 `/auto` | 切换并放行这一条 |

## 10. 审核记录（2026-09-23）

结论"需修改后实施"。必须修正 M1–M9 全部落地：M1→0049 §13.4；M2→§2；M3→§3.3；
M4→§3.5；M5→§2 末段（判定改为只看 env 映射 + config 公开函数，不写部署标志
字面量、不做"导出/`.env`"的推断）；M6→§1 显式写 `default`；M7→§3.2；M8→§1
参数表；M9→§7。建议补充 S1–S11 均采纳（见各节标注）。

## 11. 交付记录（2026-09-23）

按 §1–§7 实现。实现后派一轮只读代码审查，结论：没有发现模型能绕过人改变权限
模式的路径；四条必须修复，均已修复并各有测试：

| # | 缺陷 | 修复 |
|---|---|---|
| 1 | 受保护阶段区分大小写。macOS/Windows 默认文件系统不区分，`.OMICSCLAW/settings.json`、`.ENV` 在 auto-approve 下被放行 | 目录名与 `.env` 均按不区分大小写匹配 |
| 2 | 规则文件不在 `.omicsclaw/` 下时只认绝对路径，`write_file("perm.json")` 在 auto-approve 下整份替换了规则文件 | 自定义规则文件另按文件名匹配；默认的 `settings.json` 仍按目录匹配，避免误拦编辑器配置 |
| 3 | 受保护卡片上按 `a`：打印 "Remembered"、写入规则，但规则永远不被读取（第 2½ 阶段先于规则） | 新增 `PermissionGate.protects` 与 `AgentApp.can_remember_approval`；这类卡片使用单独的图例，不提供 `a`，按 `a` 只放行一次并如实说明 |
| 4 | 卡片处的 `/auto` 若抛出非预期异常，审批永远不结算；`/auto status` 遇非 UTF-8 的 `.env` 使 REPL 退出 | 卡片处捕获并重新询问；`status` 报告"unreadable"；保存路径另捕获 `RuntimeError`（符号链接环） |

采纳的建议：受保护阶段只看"写入类"参数（`command`、`path` 等），不再误拦
`web_search` 的查询或 `plan_write` 的步骤；`/current` 与"Could not save the rule"
改用 `Text`（外部路径里的方括号曾会被 rich 吞掉或让 REPL 退出）；`.env` 备份按
原文件权限创建，不再有 umask 窗口；非法的 CLI 键无论是否被覆盖都报错；三处与
行为不符的 docstring。

### 已知且未处理（写明，供后续裁定）

- **受保护检查可被刻意绕过**：shell glob（`>> .en?`）、运行时拼接文件名、非
  principal 参数（MCP `move_file` 的 `destination`）。与危险命令模式同属一类
  限制，docstring 已如实写明；对手是"有无人监督 shell 的模型"时，边界是沙箱。
- **`.mcp.json` 不在受保护集合里**：它是 OmicsClaw 自己的配置，下次启动会执行
  其中的命令。按 owner 定的界线（"决定 OmicsClaw 问不问的文件"）它不在内，但
  值得单独裁定一次。
- **规则文件被外部改动的告警在 CLI 会话中看不到**：终端占用期间日志被缓存，
  退出后才回放；且只报新增 `allow`，不报删除 `deny`/`ask`。
- **"不覆盖承诺"只读目标 `.env`**：两个候选 `.env` 都存在、承诺写在另一个里时，
  `/auto` 可能写入优先级更高的那个而使承诺失效。
- 两张并发卡片：`/auto` 只结算当前这张，第二张的图例是切换前打印的。
