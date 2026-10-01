# Human-in-the-Loop 权限控制

OmicsClaw 的 Human-in-the-Loop（HITL）模块回答一个问题：**一次工具调用在真正执行前，要不要停下来问人；问的话怎么问、谁来答、答案能记多久？**

多组学分析 agent 的工具面很宽：`bash` 可以跑 `skills/<domain>/<skill>/*.py`，也可以 `rm -rf` 掉一个测序 run 的输出目录，或者 `scp` 一个 `.h5ad` 到别的机器。`SAFETY_RULES` 第 1 条是"遗传数据不离开本机"。所以本层要同时做到两件事：日常分析（跑 skill 脚本、读文件）不被频繁打断；删除、提权、外传数据，以及修改权限配置本身，必须由人确认。

本层分三块，各自一个包：

- **决策**：`omicsclaw/permission/`，决定一次调用是放行、拒绝还是问人。
- **提问**：`omicsclaw/tools/context.py` 的 `require_approval`，把问题交给当前绑定的审批通道。没有通道时 fail-closed。
- **传输与界面**：`omicsclaw/entry/approval.py` 的 `ApprovalBroker` 把问题变成事件帧加一个 Future；CLI 审批卡片负责读取人的回答。

---

## 1. 系统架构

```
omicsclaw/permission/            决策层（叶子邻接层：只 import schema、tools、标准库）
├── modes.py      PermissionMode：default / auto-approve / read-only / bypass-all
├── rules.py      Rule / Rules / RuleStore：settings.json 的读、匹配、写回
├── danger.py     DangerPattern / DangerPatterns：28 条内置高危 shell 正则
└── gate.py       PermissionGate（决定）+ GatedTool（执行决定）+ gate_tools

omicsclaw/tools/                 提问协议（被本层复用，未修改）
├── base.py       ToolPolicy（approval_mode / risk_level / read_only / prompts_for_itself …）
└── context.py    require_approval · ApprovalChannel · ApprovalRequest / ApprovalDecision
                  ApprovalDenied / ApprovalUnavailable · use_effective_policy · ask_every_time

omicsclaw/entry/                 组合根与界面
├── assembly.py   build_permission_gate · AgentApp.permission
│                 AgentApp.set_permission_mode / remember_approval / can_remember_approval
├── config.py     permission_mode / permission_rules / approval_timeout_s
├── approval.py   ApprovalBroker：APPROVAL_REQUIRED 帧 + Future，超时即拒
├── turn.py       TurnHandle.approvals / TurnHandle.approve
└── cli/
    ├── _repl.py  审批卡片：y / s / a 三种授权
    └── _auto.py  /auto：切换 default ⇄ auto-approve，并写入 .env
```

### 1.1 一次工具调用经过的包装层

```
AgentEngine ──execute(call)──► ToolRegistry.execute
                                  │  发布 effective_policy（部署解析出的 ToolPolicy）
                                  ▼
                               GatedTool.execute              ← omicsclaw/permission/gate.py
                                  │  PermissionGate.resolve → ALLOW / DENY / ASK
                                  │  DENY  → raise PermissionDenied（谁都没问）
                                  │  ASK   → require_approval（或把问题交给工具自己问）
                                  │  ALLOW → 以 approval_mode=AUTO 重新发布策略，运行内层
                                  ▼
                               HookedTool.execute             ← omicsclaw/hooks/chain.py（仅在配置了 hook 时存在）
                                  ▼
                               BashTool / WriteFileTool / …   ← 工具自己的 require_approval 看到 AUTO，立即返回
```

装配顺序写在 `omicsclaw/entry/assembly.py` 的 `build_app` 里：

```python
chain = build_hooks(config, observing) if hooks is None else hooks
mounted = hook_tools(mounted, chain)          # hook 先包
gate = build_permission_gate(config)
mounted = gate_tools(mounted, gate)           # gate 再包，所以 gate 在最外层
registry = build_registry(config, mounted)
```

---

## 2. 工作流概览

```
模型发出 tool_call
      │
      ▼
┌──────────────────────────────────────────────────────────────────┐
│ PermissionGate.resolve(tool, arguments, policy, schema)          │
│ 纯函数：不问人、不执行、不抛异常；第一个给出答案的阶段胜出       │
│                                                                  │
│ 1   mode = bypass-all          → ALLOW（source=mode）            │
│ 2   mode = read-only 且工具未声明 read_only → DENY（source=mode）│
│ 2½  会改写 .omicsclaw/、规则文件或 .env → ASK（source=protected）│
│ 3   规则文件：deny → allow → ask，首条命中 → 对应 verdict        │
│ 4   主参数名为 command 且命中高危正则 → ASK（source=danger）     │
│ 5   mode = auto-approve        → ALLOW（source=mode）            │
│ 6   工具自己的 approval_mode：AUTO → ALLOW，否则 → ASK           │
└──────────────────────────────────────────────────────────────────┘
      │
      ├── DENY  → PermissionDenied → 模型收到 is_error Observation
      ├── ALLOW → _run_settled：发布 approval_mode=AUTO 的策略后运行内层工具
      └── ASK
           ├── 工具声明 prompts_for_itself、这次仍会自己问、且原因不是 danger/protected
           │      → 原样交给工具，由工具用更具体的提示自己 require_approval
           └── 否则 → 网关自己 require_approval（风险等级取 Resolution.risk_level），
                      通过后 _run_settled，工具内部不会再问第二次
                             │
                             ▼
               require_approval → 当前 Task 绑定的 ApprovalChannel
                             │     （没有通道 → ApprovalUnavailable，fail-closed）
                             ▼
               ApprovalBroker.__call__
                 发布 APPROVAL_REQUIRED 帧，await Future（可带 approval_timeout_s）
                             │
                             ▼
               界面（CLI 卡片）读取回答 → TurnHandle.approve → ApprovalBroker.settle
                             │
                             ▼
               APPROVAL_SETTLED 帧；拒绝 → ApprovalDenied；批准 → 工具执行
```

几条关键保证：

- **一次调用最多问一次人。** 网关问过之后，用 `use_effective_policy` 发布一个 `approval_mode=AUTO` 的策略，工具内部的 `require_approval` 首先读这个策略，所以直接返回。这靠的是 `tools/context.py` 里已有的机制，没有新增 context key。
- **规则总是先于高危模式。** 第 4 阶段只有在规则文件对这次调用没有任何表态时才会走到。这一点双向成立：`deny` 规则能拒掉高危模式本来只会问的命令，`allow` 规则也能放行高危模式本来会拦下的命令（见 §10）。
- **受保护文件先于规则。** 第 2½ 阶段排在规则文件之前，因为它保护的就是规则文件：如果一条 `allow` 规则可以让工具改写规则文件，工具就能自己写下一条 `allow`。

---

## 3. PermissionMode

`omicsclaw/permission/modes.py`。`StrEnum`，配置文件、CLI flag、代码与日志中的拼写一致。

| 模式 | 值 | 行为 |
|---|---|---|
| `DEFAULT` | `default` | 规则决定；未命中的调用回落到工具自己的 `ToolPolicy.approval_mode`。默认值 |
| `AUTO_APPROVE` | `auto-approve` | 未命中规则、也未命中高危模式的调用直接放行。`deny` 规则、高危模式、受保护文件仍然生效 |
| `READ_ONLY` | `read-only` | 拒绝所有未声明 `read_only=True` 的工具。`bash` 和 `web_search` 因此都会被拒（后者虽不写本地文件，但查询词会发往外部） |
| `BYPASS_ALL` | `bypass-all` | 本层所有检查关闭：不读规则、不查高危模式、不问人。用于无人值守的受控环境；`Resolution.reason` 会写明 mode 名 |

四个模式都有可测试的效果。

### 3.1 前台基础工具的默认策略

以下数值取自 `foundation_tools(AppConfig(...))` 的实际输出（`use_skill` 仅在 `skills_index` 不为 `off` 时挂载）：

| 工具 | approval_mode | risk_level | read_only | prompts_for_itself |
|---|---|---|---|---|
| `read_file` | `auto` | `low` | ✓ | |
| `write_file` | `ask` | `high` | | ✓ |
| `edit_file` | `ask` | `high` | | ✓ |
| `bash` | `ask` | `high` | | ✓ |
| `web_fetch` | `ask` | `high` | | ✓ |
| `web_search` | `ask` | `medium` | | ✓ |
| `use_skill` | `auto` | `low` | ✓ | |

`prompts_for_itself` 是工具的一个**声明**：它会在自己的 `execute` 里调用 `require_approval`，提示内容能说明实际效果（`edit_file` 的 diff、`web_fetch` 的完整 URL）。网关只读这个声明，不从 `approval_mode` 去推断。`tests/permission/test_foundation_tools_keep_their_prompts.py` 拿真实工具做行为验证，确认声明了的工具确实会问。

另外，沙箱开启、`sandbox_network` 为 `none` 且设置了 `--sandbox-auto-approve` 时，`omicsclaw/entry/sandbox.py` 的 `bash_policy` 会把 `bash` 的策略改为 `AUTO`（`_apply_bash_policy` 在注册后重新登记已被 gate 包好的对象）。此时规则、高危模式和受保护文件检查仍在网关里生效。

---

## 4. 权限规则文件（settings.json）

默认位置为 `<workspace>/.omicsclaw/settings.json`（`AppConfig.permission_rules_path()`），可以用 `--permission-rules` / `OMICSCLAW_PERMISSION_RULES` 改到别处。文件不存在时视为空规则集，不报错。

```json
{
  "permissions": {
    "deny":  ["bash(rm -rf *)", "write_file(data/raw/*)"],
    "allow": ["read_file", "bash(git status)", "bash(python skills/*)"],
    "ask":   ["bash(pip install*)"]
  }
}
```

### 4.1 语法

| 形式 | 语义 |
|---|---|
| `toolName` | 匹配该工具的任意调用 |
| `toolName()` | 同上，空括号等于不限参数 |
| `toolName(pattern)` | *pattern* 匹配该调用的**主参数**时命中 |

**主参数**（`principal_argument`）是工具 JSON Schema 里第一个 `required` 且类型为 `string` 的属性值：`bash` 是 `command`，文件工具是 `path`，`web_fetch` 是 `url`，`web_search` 是 `query`，`use_skill` 是 `skill_name`。`write_file` 的 `required` 是 `["path", "content"]`，所以规则针对的是写入目的地，与写入内容无关。没有必填 string 属性时，取第一个必填的字符串数组，去重、排序后用 `, ` 连接：`install_skill_deps` 的主参数是 `skills`，"总是允许"记下的是 `install_skill_deps(sc-de, sc-qc)` 这样的 skill 组合，与包和参数顺序无关。两者都没有时回落到原始 JSON 文本。

**匹配规则**（`_match_argument`）：

- pattern 不含 `*?[` 时要求**完全相等**。`bash(ls)` 不匹配 `ls -la`，要写成 `bash(ls*)`。
- 含通配符时用 `fnmatch.fnmatchcase` 对整个字符串做 glob，`*` 可以跨越 `/`。
- 区分大小写（与高危模式相反），因为 registry 按精确名称索引工具，大小写不敏感的 `allow` 会放行超出作者本意的调用。
- 没有子串回退，也没有逐词匹配。

### 4.2 求值与加载

- 加载顺序固定为 `deny` → `allow` → `ask`（`_LOAD_ORDER`），第一条命中的规则生效。所以 `deny` 总是压过同时命中的 `allow`，文件内 key 的顺序无关紧要。
- 没有任何规则命中时，`Rules.evaluate` 返回 `None`，不返回 `ask`。这样网关才能继续执行第 4～6 阶段。
- 无法按原样读懂的文件会抛 `PermissionConfigError`：未知 action key（如拼错的 `"denied"`）、缺右括号的 pattern、把列表写成标量等。`build_permission_gate` 在启动时构造 `RuleStore`，所以格式错误的规则文件会让应用**无法启动**，不会等到分析跑到一半的第一次 `bash` 调用才暴露。

### 4.3 RuleStore：每次调用都重读

`RuleStore.current` 每次被询问都重新读取文件，不做缓存。所以在审批卡片上选了"always"，下一次调用立即生效。

- 运行中文件变得不可读时，保留上一份可用规则并记 warning，不抛异常。
- 出现了本进程没有写过的 `allow` 规则时记一条 warning（"permission rules changed outside this process"）。操作员中途编辑文件是合法的，所以不拒绝；但如果是一个无人监督的工具给自己写了 `allow`，这条日志能让人看到。

### 4.4 写回：`save_rules` 与 `literal_pattern`

- 先写临时文件再原子 `os.replace`，失败时删除临时文件，旧规则保持完整。
- 文件权限为 `0600`；本次调用新建的每一级目录为 `0700`（`_make_owner_only` 逐级 `mkdir`，因为 `mkdir(parents=True, mode=…)` 只对最后一级生效）。
- `Rules.to_config` 按 action 去重，重复点"always"不会让文件无限增长。
- 写回后顺序重置为 deny → allow → ask。
- "always allow" 写入的 pattern 由 `literal_pattern` 生成：**只匹配这一次调用本身**，其中的通配符被转义成字符类。例如批准 `ls *.csv` 会写成 `bash(ls [*].csv)`。这样批准过的 `git status` 不会连带放行 `git status; rm -rf /`。

---

## 5. 内置高危命令模式（danger.py）

`DEFAULT_DANGER_PATTERNS` 共 28 条正则，按主题分组，匹配时忽略大小写（`re.IGNORECASE`）。只作用于**主参数名为 `command` 的工具**（`COMMAND_ARGUMENT`），与工具名无关，所以沙箱里的 shell、改了名的 `bash`、MCP server 暴露出来的 shell 都会被覆盖。

| 主题 | 典型命中 | 风险 |
|---|---|---|
| 不可恢复的破坏 | 同一段命令里同时带 `-r` 和 `-f` 的 `rm`、`rm … /`、`shred`、`truncate -s 0`、`find … -delete`、`find … -exec rm`、`xargs … rm`、`dd if=/of=`、`> /dev/sd…`、`> /etc/…`、`mkfs` | high |
| 远程代码执行 | `\| bash`、`\| sh`、`\| python…` 等管道进解释器；fork bomb | high |
| **数据离开本机** | `scp`、`rsync … host:`、`ssh host`、`curl/wget` 上传本地文件（`--upload-file`、`-T`、`--data-binary @`、`-d @`、`--form …=@`） | high |
| 数据离开本机 | `nc host`、`git push` | medium |
| 提权与系统状态 | `chmod -R 777`、`chown -R` | high |
| 提权与系统状态 | `sudo`、`chmod 777`、`killall`、`pkill`、`kill -9`、`iptables`、`systemctl` | medium |

设计要点：

- **命中只会升级为 ask，不会升级为 deny。** 模式命中只是怀疑，`rm -rf ./tmp_run7` 和 `rm -rf /` 只有人能区分。
- **锚点**：左锚 `(?<![\w-])`、右锚 `(?![\w-])`。所以 `sudo` 不匹配 `--sudo-mode`，也不匹配 `pseudobulk`；`sh` 不匹配 `shuf`。`\b` 会把连字符当成词边界，这是审核中发现的问题（plan 0038 §8）。
- **分段扫描**：`_SEGMENT = [^|;&\n]*`。需要两个 flag 同时出现的模式只在同一段命令内查找，所以 `rm -f a | grep -r b` 不会被当成递归删除。
- `DangerPatterns.inspect` 扫描全部模式，返回**风险最高**的一条；风险相同时取表中靠前的一条。这决定了人在卡片上看到的原因，例如 `chmod -R 777 . && git push` 报告的是权限变更。
- 这不是 shell 解析器：命令名作为别的命令的参数（`grep sudo notes.txt`）同样会命中，代价是多问一次。
- `DangerPatterns` 可以注入。比如一个无网络、无数据挂载的容器可以去掉上传类模式：`PermissionGate(danger=DangerPatterns(my_patterns))`。

---

## 6. 受保护文件（stage 2½）

`PermissionGate.touches_protected` 对以下目标做文本检测，大小写不敏感：

- `.omicsclaw/` 目录（`PROTECTED_DIRNAME`）：规则文件、会话库、计划都在这里；
- `.env`（`DOTENV_NAME`），包括 `./.env`、`/srv/app/.env`、`.env.local`，但不包括 `.environ`、`.envrc`、`.venv`；
- 放在 `.omicsclaw/` 之外的规则文件，按完整路径或文件名识别。

保护 `.env` 是因为它可以设置 `OMICSCLAW_PERMISSION_MODE=bypass-all`，而 `bypass-all` 排在所有检查之前；`LLM_BASE_URL` 还决定 API key 发往哪里。一次无人监督的 `echo … >> .env` 就能从下次启动起关掉网关。

判定条件是 `_protected`：工具**没有**声明 `read_only`，主参数名属于 `_WRITING_KEYS`（`command`、`path`、`file_path`、`filename`、`destination`、`target` 等），并且文本命中上述目标。所以读取 `.omicsclaw/settings.json` 不会被拦，`web_search` 的查询词里出现 `.env` 也不会被拦。

受保护调用的特殊之处：

- `Resolution.risk_level` 固定为 `HIGH`；
- **任何规则都无法放行它**，包括"always"写入的 `allow` 规则，因为 2½ 阶段在规则文件之前；
- `AgentApp.can_remember_approval` 对这类调用返回 `False`，CLI 因此不提供 `a`（见 §8）。

`touches_protected` 的 docstring 写明了它检测不到的情况：运行时拼出来的名字（`d=.en; echo >> ${d}v`）、shell glob（`.en?`）、网关不读的其他参数。它防的是粗心或被诱导的模型；面对有意为之、且持有无人监督 shell 的模型，只有沙箱能兜底。

---

## 7. 提问协议与传输

### 7.1 `require_approval`（`omicsclaw/tools/context.py`）

工具在不可逆操作之前调用它。策略解析顺序（`_resolved_policy`）：

1. `effective_policy()`，由 `ToolRegistry.execute` 从 `policy_for` 发布，部署的 `register(policy=)` 在这里优先于工具作者的声明；
2. 调用方传入的 `policy` 参数（工具在 registry 之外被直接调用时）；
3. `ToolPolicy()`，其 `approval_mode` 为 `ASK`。

然后：

- `approval_mode` 为 `AUTO` 时直接批准；
- 没有绑定 `ApprovalChannel` 时抛 `ApprovalUnavailable`。**没有通道不等于同意**，这是 fail-closed；
- 否则在 `pause_tool_timeout()` 中调用通道，所以人的思考时间不计入 `tool_timeout`；
- 通道返回 `None` 按拒绝处理；拒绝时抛 `ApprovalDenied`，工具不会执行。

异常层次：`ApprovalDenied` ← `ApprovalUnavailable`，`ApprovalDenied` ← `PermissionDenied`。一个 `except ApprovalDenied` 就能覆盖三种"没有得到同意"的情况，日志里仍然能区分是规则拒绝、人拒绝还是没有人可问。

`ApprovalRequest` 字段：`tool_name`、`arguments`（原始 JSON 字符串）、`reason`、`risk_level`、`approval_mode`、`ask_every_time`。最后一个由 `require_approval` 从 context 变量 `ask_every_time()` 读出，**由网关绑定**，表示这个问题来自比"工具默认会问"更具体的来源：规则、高危模式、受保护文件，或声明为 `DENY_UNLESS_TRUSTED` 的工具（`GatedTool._always_asked`）。界面据此决定哪些问题不能用"本会话不再问"来回答。

### 7.2 `ApprovalBroker`（`omicsclaw/entry/approval.py`）

问题在于：`require_approval` 的 `await` 发生在工具内部，也就是在 `AgentEngine.run_stream` 的 `__anext__` 内部。负责播报问题的生成器，正是挂起等待答案的那个生成器。解决办法是让引擎在自己的 Task 里运行，由 `ApprovalBroker` 在两个 Task 之间做接缝：

- `__call__(request)`：它本身就是 `ApprovalChannel`。在 exchange 的 `TurnStream` 上发布 `APPROVAL_REQUIRED` 帧（请求 id 形如 `<turn_id>#<n>`），然后 await 一个 `asyncio.Future`；
- `settle(request_id, decision)`：同步方法，从点击回调、HTTP 路由或 IM 回调调用。未知 id、重复 settle 都是 no-op，返回 `False`（重复点击、过期卡片都是正常输入）；
- `abandon(reason)`：exchange 在 `finally` 中调用，把仍未回答的问题全部按拒绝处理，并发布 `APPROVAL_SETTLED`；
- `timeout_s`：来自 `AppConfig.approval_timeout_s`。`None` 表示无限等待（适合 CLI）。**到期即拒绝**，原因文本为 `TIMEOUT_REASON`；非正数在构造时直接拒绝。

`TurnHandle`（`omicsclaw/entry/turn.py`）为每个 exchange 持有一个 `approvals: ApprovalBroker`，界面通过 `TurnHandle.approve(request_id, decision)` 作答。Channel 运行时强制要求 `approval_timeout_s` 为数字（`ChannelRuntime` 构造时检查）。它的 `settle_approval_threadsafe` 负责把厂商 SDK 线程上的回调转到事件循环线程。

**日志不记录参数。** `ApprovalRequest` 里有原始 `bash` 命令行或 `write_file` 内容，broker 只记录工具名、请求 id、风险等级和结果；`GatedTool` 也只记录工具名和 `DecisionSource`。

---

## 8. CLI 审批卡片与 `/auto`

### 8.1 卡片

`omicsclaw/entry/cli/_repl.py`。风险等级和原因由 `TextRenderer` 在卡片上方打印；输入提示为：

```
  y = allow once · s = allow this tool for the rest of the conversation · a = always, and write a rule · anything else denies · /auto stops these
approve bash [#1]? [y/N/a=always]
```

`[#1]` 取自请求 id 的 `#n` 后缀。同一轮里有两个同名工具调用（比如两个 `web_fetch`）时，靠它区分正在回答哪一个。

| 输入 | 效果 | 持久化 |
|---|---|---|
| `y` / `yes` / `ok` / `allow` | 仅本次放行 | 无 |
| `s` / `session` | 放行，并在**本会话**内不再问该**工具** | 仅内存：`Repl._granted`，key 为 `(session_id, tool_name)`；`/new` 自然失效，`/resume` 回到原会话时恢复 |
| `a` / `always` | 放行，并为**这一次调用本身**写入 `allow` 规则 | `AgentApp.remember_approval` → `PermissionGate.remember` → `RuleStore.remember`，写入 `settings.json` |
| 其他任何输入（包括空行） | 拒绝；以 `/` 开头的输入不会作为拒绝理由转给模型 | 无 |
| Ctrl-C | 拒绝（`interrupted at the terminal`）并取消本次 exchange | 无 |
| EOF / 无终端 | 拒绝（`no operator at the terminal`） | 无 |
| `/auto` 或 `/auto on` | 切换到 auto-approve；若这张卡不是 always-asked，按新模式直接放行 | 同 `/auto` |

三种授权的边界：

- `ask_every_time` 的卡片（高危模式、显式 `ask` 规则、受保护文件、`DENY_UNLESS_TRUSTED`）上，`s` 只放行这一次，已有的 `s` 授权也不会自动回答它。图例变为 `this call is always asked about: y or s = allow it once · a = always, and write a rule · …`。
- 受保护文件的卡片上 `a` 不可用（`can_remember_approval` 为 `False`），图例为 `this call is always asked about, and no rule can change that: y = allow it once · anything else denies`。
- `a` 写的是精确规则。对 `bash` 来说几乎等于只放行这一条命令，所以 CLI 会补一句提示：想让这个工具在本会话不再询问，用 `s`。
- 没有规则文件可写（`PermissionGate.store is None`）时，屏幕上会显示 `This run has nowhere to remember that.`，不会假装已经记住。

### 8.2 `/auto [on|off|status]`

`omicsclaw/entry/cli/_auto.py`（plan 0050）。分两部分：

- **当前进程**：`AgentApp.set_permission_mode` 修改进程内唯一的 `PermissionGate`，下一次工具调用就按新模式判定。只允许在 `default` 与 `auto-approve` 之间切换；`read-only` 和 `bypass-all` 是部署层面的承诺，运行中的命令不能建立也不能打破它们，否则抛 `ValueError`。每次切换记一条 WARNING 日志。
- **下次启动**：把 `OMICSCLAW_CLI_PERMISSION_MODE` 写入 `.env`（`persist_cli_mode`）。`.env` 里已经写着 `read-only` / `bypass-all` 时不覆盖。`off` 会显式写入 `default`，不删除这个 key。

优先级（`omicsclaw/launch/_surfaces.py` 的 `_with_the_cli_permission_mode`），从高到低：`--permission-mode` flag，然后 `OMICSCLAW_PERMISSION_MODE`，然后 `OMICSCLAW_CLI_PERMISSION_MODE`，最后 `default`。CLI 专用的 key 只影响 `oc cli`，所以在终端里打 `/auto` 不会让无人值守的 Channel bot 开始自动放行。`/auto status` 会显示当前模式、启动时的来源、`.env` 中的值，以及沙箱状态。

`/auto` 开启时，屏幕会说明哪些情况仍然会问：高危命令、显式 `ask` 规则、对 `.omicsclaw/` 或 `.env` 的改动；`deny` 规则仍然拒绝。同时提醒：高危模式是黑名单，不是隔离边界。

### 8.3 一个多组学场景下的判定表

规则文件为 `deny: ["bash(rm -rf *)"]`，`allow: ["bash(python skills/*)", "bash(git status)"]`。以下结果来自对 `PermissionGate.resolve` 的实际调用：

| 命令 | default | auto-approve | read-only |
|---|---|---|---|
| `python skills/spatial/spatial-preprocess/spatial_preprocess.py --demo --output /tmp/x` | allow（rule） | allow（rule） | deny（mode） |
| `rm -rf results` | deny（rule） | deny（rule） | deny（mode） |
| `ls -la` | ask（policy） | allow（mode） | deny（mode） |
| `scp a.h5ad host:/x` | ask（danger, high） | ask（danger, high） | deny（mode） |
| `echo hi >> .env` | ask（protected, high） | ask（protected, high） | deny（mode） |
| `git status; rm -rf /` | ask（danger） | ask（danger） | deny（mode） |

`bypass-all` 下全部为 allow（mode）。

---

## 9. 子代理、Desktop 与 Channel

### 9.1 子代理：只读模式下的分支

`task` 工具（`omicsclaw/subagent/task_tool.py`）的 `TASK_TOOL_POLICY` 是 `approval_mode=AUTO`、`risk_level=HIGH`，**没有**声明 `read_only`。委派本身不是危险动作，子代理用到的每个工具都各自经过 gate 和审批。

- `task` 和其他工具一样经过 `gate_tools(hook_tools(...))` 挂载，挂在工具表末尾。
- 子代理的 registry 由 `ChildRunner._child_registry` 从父 registry 中挑出**已经 gate 过的对象**，按父 registry 解析出的策略重新注册。所以子代理的权限不可能比父代理宽，部署通过 `register(policy=)` 做的收紧也会带过去。
- 审批不需要额外管道：`contextvars` 会复制进新 Task，子代理里 `bash` 的审批请求会经过两层 Task 边界，到达父 exchange 的同一个 `ApprovalBroker`。`TaskTool` 还把子代理名写进 tool context（`SUBAGENT_VALUE_KEY`），设计上是让审批卡片显示哪个子代理在请求；但 `omicsclaw/entry/` 目前还没有代码读取这个值。
- **只读分支**：`--permission-mode read-only` 下，网关的第 2 阶段会拒掉 `task`，因为它无法如实声明 `read_only=True`。所以只读模式下**委派整体不可用**。这是 fail-closed 的方向，但用户能直接感知到（FRAMEWORK-REBUILD Step 6.12 列为已知代价）。

### 9.2 Desktop：卡片、`/chat/permission` 与 `/chat/abort`

`APPROVAL_REQUIRED` 事件被投影成 `permission_request` SSE 帧（字段见 [surfaces.md](surfaces.md) §8.2），App 显示卡片，用户的选择经 `POST /chat/permission` 回到后端，由 `approvals.settle` 结算（plan 0064）：

- `once`：只放行这一次；拒绝时可以带 `message`，缺省理由是 `denied in the desktop app`，模型会看到它。
- `session`：把该工具授权给这个会话（进程内有效，不落盘，与 CLI 的 `s` 同义），并连带放行同会话、同工具下其他待决请求；之后同类请求由正在读流的 SSE 体直接放行，不再发卡片。`ask_every_time` 为真的请求（高危模式、`ask` 规则、受保护文件、`DENY_UNLESS_TRUSTED`）永远不被会话授权放行。
- "总是允许"（写规则）在 P1 实现（B1-2），目前请求 `scope: "always"` 返回 422。
- 卡片只在请求仍待决时发出；重连时从 ring 重放出来的、已经结算的请求不会再弹卡片。

Desktop 的 `approval_timeout_s` 保持 `None`：审批不会到期（旧后端令牌的 5 分钟自动拒绝不复存在），停止回合（`POST /chat/abort`）是结束一个无人回答的问题的方式，被取消的回合以 `error: "cancelled"` 与 `done` 结束。自动放行需要有观察者在场。

### 9.3 Channel

`ChannelRuntime` 提供 `settle_approval` / `settle_approval_threadsafe`，并强制设置审批超时。但在当前代码里，`omicsclaw/entry/channel/` 下的各 adapter 都没有渲染审批卡片，也没有调用这两个方法（grep 可验证）。所以在 IM 界面上，需要审批的调用会在超时后被拒绝。"always allow" 按钮同样只存在于 CLI（plan 0038 §8.3 列为待办）。

---

## 10. 配置参数

| 设置 | CLI flag | 环境变量 | 默认值 | 说明 |
|---|---|---|---|---|
| `AppConfig.permission_mode` | `--permission-mode` | `OMICSCLAW_PERMISSION_MODE` | `default` | 四个 `PermissionMode` 值之一；拼错直接报错，不回落 |
| （CLI 专用） | — | `OMICSCLAW_CLI_PERMISSION_MODE` | 未设置 | 仅对 `oc cli` 生效，优先级低于上一行；`/auto` 写这个 key |
| `AppConfig.permission_rules` | `--permission-rules` | `OMICSCLAW_PERMISSION_RULES` | `<workspace>/.omicsclaw/settings.json` | 规则文件；不要指向父目录属于他人的路径（`save_rules` 会跟随符号链接） |
| `AppConfig.approval_timeout_s` | `--approval-timeout` | `OMICSCLAW_APPROVAL_TIMEOUT_S` | `None`（无限等待） | 单次审批的截止时间，到期即拒；Channel 必须设置 |
| `AppConfig.sandbox_auto_approve` | `--sandbox-auto-approve` | `OMICSCLAW_SANDBOX_AUTO_APPROVE` | `False` | 沙箱运行且无网络时 `bash` 免审批 |

以编程方式构造一个网关，不需要 `AppConfig`：

```python
from omicsclaw.permission import PermissionGate, PermissionMode, RuleStore, gate_tools

gate = PermissionGate(
    mode=PermissionMode.DEFAULT,
    rules=RuleStore(workspace / ".omicsclaw" / "settings.json"),
)
registry = ToolRegistry(gate_tools(foundation_tools(config), gate))
```

`gate_tools` 保持顺序（工具列表顺序是 prompt 缓存前缀的一部分），并且是幂等的：已经是 `GatedTool` 的对象原样返回，不会套两层网关导致问两次人。

---

## 11. 已知限制

- **规则优先于高危模式，双向都成立。** `allow: ["bash(python skills/*)"]` 会放行 `python skills/x.py; rm -rf /`，因为第 3 阶段命中后第 4 阶段不再执行。需要放行一类命令时，glob 要写得足够窄；CLI 的 `a` 因此只写精确规则。
- **绕过 `gate_tools` 注册的工具不受管辖。** 未被包装的工具照样能跑、照样自己问，只是不再检查规则和高危模式。由 `tests/entry/test_permission_wiring.py` 钉住组合根的行为，但自行组装 registry 的调用方需要自己保证。
- **`prompts_for_itself` 是声明，不是保证。** 声明了却不调用 `require_approval` 的工具会被网关让行，结果没人被问。基础工具有行为测试兜底，MCP 或第三方工具没有。
- **规则 ASK 落到自带提示的工具上时**，交给工具自己问，用的是工具的提示；但高危模式和受保护文件命中时，网关会自己问，`bash` 原本提示里的 cwd/timeout 上下文会让位给"危险在哪"（plan 0038 §5）。
- **网关每次调用只读一个主参数。** MCP 的 `move_file(source, destination)` 这类工具，只有 `source` 会被检查。受保护文件检测也检测不到运行时拼接的名字和 shell glob。
- **`READ_ONLY` 会同时拒掉 `bash`、`web_search` 和 `task`**，只读模式下无法委派子代理。
- **Desktop 的会话授权需要观察者在场**：没有 SSE 体在读的回合，其请求要等有人重新观察时才被放行；"总是允许"在 P1 之前不可用。
- **Channel adapter 没有审批 UI**，需要审批的调用在 `approval_timeout_s` 到期后被拒；"always allow" 只在 CLI 可用。
- **规则文件路径上的符号链接会被跟随**（plan 0038 §8.4，明确决定不修）。`--permission-rules` 只应指向父目录归自己所有的路径。
- **每次调用重读规则文件**，没有 mtime 缓存。文件小于 1 KB，这点代价远小于一次模型往返。

---

## 12. 文件索引

| 文件 | 职责 |
|---|---|
| `omicsclaw/permission/__init__.py` | 公共 API 与用法示例 |
| `omicsclaw/permission/modes.py` | `PermissionMode` |
| `omicsclaw/permission/rules.py` | `Rule`、`Rules`、`RuleStore`、`Verdict`、`load_rules`、`save_rules`、`principal_argument`、`literal_pattern`、`PermissionConfigError` |
| `omicsclaw/permission/danger.py` | `DangerPattern`、`DangerPatterns`、`DEFAULT_DANGER_PATTERNS`、`COMMAND_ARGUMENT` |
| `omicsclaw/permission/gate.py` | `PermissionGate`、`GatedTool`、`gate_tools`、`Resolution`、`DecisionSource`、`PermissionDenied`、`PROTECTED_DIRNAME`、`DOTENV_NAME` |
| `omicsclaw/tools/base.py` | `ToolPolicy`、`ApprovalMode`、`RiskLevel` |
| `omicsclaw/tools/context.py` | `require_approval`、`ApprovalChannel`、`ApprovalRequest`、`ApprovalDecision`、`ApprovalDenied`、`ApprovalUnavailable`、`use_effective_policy`、`ask_every_time`、`pause_tool_timeout` |
| `omicsclaw/entry/approval.py` | `ApprovalBroker`、`TIMEOUT_REASON`、`ABANDONED_REASON` |
| `omicsclaw/entry/assembly.py` | `build_permission_gate`、`build_app` 中的装配顺序、`AgentApp.set_permission_mode` / `remember_approval` / `can_remember_approval`、`_apply_bash_policy` |
| `omicsclaw/entry/config.py` | `permission_mode`、`permission_rules`、`approval_timeout_s`、`permission_rules_path()` |
| `omicsclaw/entry/turn.py` | `TurnHandle.approvals` / `approve` |
| `omicsclaw/entry/cli/_repl.py` | 审批卡片、`_YES` / `_FOR_THIS_SESSION` / `_ALWAYS`、`Repl._granted`、`_auto` |
| `omicsclaw/entry/cli/_auto.py` | `/auto`、`CLI_PERMISSION_MODE_VARIABLE`、`persist_cli_mode` |
| `omicsclaw/launch/_surfaces.py` | CLI 权限模式优先级 |
| `omicsclaw/entry/sandbox.py` | `bash_policy`（沙箱无网络时免审批） |
| `omicsclaw/subagent/task_tool.py` | `TASK_TOOL_POLICY` |
| `omicsclaw/entry/subagent.py` | `ChildRunner._child_registry` |
| `tests/permission/` | 模式、规则、高危模式、网关、ask-every-time、分层约束、基础工具自提示行为验证 |
| `tests/entry/test_permission_wiring.py`、`test_approval.py`、`test_cli_approval_scope.py` | 装配、broker、CLI 授权范围 |

参考：`docs/plans/0038-permission-layer.md`、`0049-session-grant-covers-the-tool.md`、`0050-cli-auto-command.md`；`docs/FRAMEWORK-REBUILD.md` Step 6.8。
