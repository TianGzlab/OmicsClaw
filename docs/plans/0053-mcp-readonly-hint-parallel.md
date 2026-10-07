# 计划 0053 — MCP 工具按 `readOnlyHint` 并行执行

**状态**：第三版（2026-09-23）。经一轮独立只读审核（需修改后实施，M1–M4），owner 按推荐裁定（M1 由缺陷修复 D4 承担），已据此返工；第三版经架构审核与 harness9 对照小改（§4.4 对 0052 的描述、目标 5 的措辞、显示层前置）；第四轮收敛审核后再做文字修订（§4.4 改引 0052 第三版 §4.6，§4.3 第 1 点改写参数段上限）；第五轮审核后按第三批返工的现状改写（`arguments_block` 已删除，参数由 `approval_body` 渲染）。待 owner 过目。未写任何生产代码。

**2026-10-07 核对**：本计划的任务都还没有实现。

**前置**：计划 0034（MCP 层）已交付；写屏障（`docs/FRAMEWORK-REBUILD.md` "Parallel tool
calling — the barrier and the pause"）已落地。**缺陷修复 D4 与显示层修复 E1/E2 是硬前置，本计划
不实现**：
- **D4**：MCP 审批 reason 带上有界、清洗过的参数预览（控制字符清洗、凭据遮蔽、长度上限），工具
  层通用 helper，各 surface 共用；日志里仍不得出现参数。工作树（未提交）：`tools/preview.py` 的
  `preview_arguments`，由 `MCPTool._reason` 调用（§4.4）。
- **E1/E2**：`ApprovalRequest.reason_shows_call`（`tools/context.py`，经
  `require_approval(..., reason_shows_call=)` 设置）与 `entry/display.py`（`inert_line`、
  `inert_prose`、`approval_body`，底层是 `tools/preview.py::escape_unsafe`）。`MCPTool._reason`
  返回 `(reason, whole)`：预览未截断时 `whole=True`；超过 `MAX_PREVIEW_CHARS` 被截断时为 `False`，
  `entry/render.py::_approval_line` 这时由 `approval_body` 在 reason 之后附上 `arguments:` 与多行、
  已中和的参数（缩进、键排序的 JSON，凭据键的值遮蔽；无法按 JSON 读出时只显示
  `unreadable_arguments_note` 给出的长度）。E2 时的 `arguments_block` 已在第三批返工中删除。截至
  本稿，这些名字已在工作树（未提交），以落地为准。

并发审批卡片能否区分，依赖的是这两者合起来（§4.3 第 1 点）。**让并行真正生效的 T4 必须在
D4、E1/E2 合入之后合入。**

## 1. 缘起

0034 把"MCP 工具在引擎里串行"列为有意偏离（§2 表第 22 项、§5 第一行、附录 A M1），交 owner
决定。**owner 裁定（2026-09-23）：MCP 工具按 `readOnlyHint` 并行执行。**本计划只落实这一条。

规范（2025-06-18）：`server/tools` 写 "clients **MUST** consider tool annotations to be
untrusted unless they come from trusted servers"；`schema.ts` 的 `ToolAnnotations` 注释先
说明全部字段都只是 hint（`readOnlyHint` 缺省 `false`），紧接着写：

> "Clients should never make tool use decisions based on ToolAnnotations received from untrusted servers."

分批为什么不是这里说的 tool use decision，见 §4.3。harness9 不解析 annotations（全仓
grep 无结果），同一 turn 的工具全部并发、没有屏障（`internal/engine/tools_exec.go`）。

## 2. 目标

1. 客户端读出 `annotations.readOnlyHint`；manager 把"hint **恰为 JSON `true`** 且该 server
   没关并行"映射为 `MCPTool(concurrency_safe=True)`；缺失、`false`、非布尔一律保持屏障。
2. hint **只**进入 `concurrency_safe`：`read_only`、`approval_mode`、`risk_level`、
   `prompts_for_itself`、`allowed_in_background`、`tags` 逐字段不变；definition 不含 hint。
3. `.mcp.json` 按 server 写 `parallelReadOnly: false` 关闭（只能收紧）；近似错拼使条目被拒。
4. 最小可观测性：启动日志和 `/mcp` 显示每个 server 有几个工具会并行。
5. 分层：hint 相关词汇（`readOnlyHint`、`read_only_hint`、`parallelReadOnly`、
   `parallel_read_only`）只出现在 `omicsclaw/mcp/`，与 §4.1 的结构测试一致；工具层只认
   `concurrency_safe`；entry 只读 `ToolDetail.concurrency_safe`。

## 3. 现状（读代码所得；行号以 2026-09-23 工作树为准，实施时按所附符号名定位）

| # | 事实 | 出处 |
|---|---|---|
| F1 | annotations 在**客户端解析**时被丢弃：`_remote_tool` 只取 `name`/`description`/`inputSchema`/`title`，`RemoteTool` 没有对应字段；两种传输都把 `result` 原样交给客户端 | `mcp/client.py` `RemoteTool`、`_remote_tool`（:51-57、:204-216） |
| F2 | manager 构造 `MCPTool` 时不传 policy，落到 `_default_policy`：`HIGH`/`ASK`/`prompts_for_itself`/两个 tag，`concurrency_safe` 取默认 `False` | `mcp/manager.py` `MCPManager._mount`（:284-291）；`tools/mcp_tool.py` `_default_policy`；`tools/base.py` `ToolPolicy` |
| F3 | `concurrency_safe` 全仓只有一个消费者，即分批：不安全的调用单独成批（屏障），相邻的安全调用同批；各批按调用顺序依次执行，批内并发 | `tools/registry.py` `ToolRegistry.is_concurrency_safe` → `engine/executor.py` `_concurrency_groups`、`execute_tool_calls` |
| F4 | 部署调用 `register(tool, policy)` 时**整体替换**工具自带的 policy | `ToolRegistry._resolved_policy` |
| F5 | 生产没有并发上限（`max_concurrent_tools=0`，`serialize_unsafe_tools=True`）。**生产 `tool_timeout` 是 600 s**：`AppConfig.tool_timeout_s = 600.0` 经 `engine_config()` 传给引擎，`EngineConfig.tool_timeout` 的 60 s 只是引擎默认值；HTTP socket 超时也取 `tool_timeout_s` | `engine/config.py` `EngineConfig`；`entry/config.py` `AppConfig.tool_timeout_s`、`engine_config`；`entry/assembly.py` `open_app` |
| F6 | `concurrency_safe` **不**控制审批、权限、hooks 和路径锁。`_pathlock` 只协调本进程的 read/write/edit，管不到 MCP server 进程里的写。超时按调用计算，审批暂停按 Task 隔离 | `tools/_pathlock.py` 模块 docstring；`engine/executor.py` `_bound_timeout_pause`、`_paused` |
| F7 | `read_only` 是**权限输入**：read-only 模式只放行 `read_only=True`；`read_only=True` 的工具跳过"改受保护文件必问"。read-only 模式连 `web_search` 都拒绝（向外发送即披露） | `permission/gate.py` `PermissionGate.resolve`、`_protected`；`permission/modes.py` `PermissionMode.READ_ONLY` |
| F8 | hook 层、权限层的包装都原样转发 `policy`；子代理注册表继承 `policy_for` | `hooks/chain.py` `policy`；`permission/gate.py` `GatedTool.policy`；`entry/subagent.py` `_child_registry` |
| F9 | **并发审批在结构上已支持，但并发的 MCP 卡片今天无法区分。** `ApprovalBroker` 按 `request_id`（`<turn id>#<n>`）逐个挂起、逐个结算，与由哪个入口作答无关；CLI 每张卡在独立 Task 里问、在终端排队。`web_fetch`/`web_search` 同为 `ASK` + `concurrency_safe=True`，reason 带 URL/查询；HEAD 上 MCP 的 reason 只有 server、origin、tool 名，**不带参数**（D4 补上预览，E1/E2 让 `_approval_line` 在预览被截断时附上多行参数段，参数段自身的上限见 §4.3 第 1 点）；所有 surface 的审批行都由 `entry/render.py::_approval_line` 渲染，CLI `Repl._ask` 的提示符只写工具名。Channel 今天没有接到任何 adapter 的作答入口（0052 §0） | `entry/approval.py` `ApprovalBroker`；`tools/mcp_tool.py` `MCPTool.execute`、`_reason`；`entry/render.py` `_approval_line`；`entry/cli/_repl.py` `Repl._ask`；`tools/builtin/web_fetch.py`、`web_search.py` `_POLICY` |
| F10 | 传输支持多路复用：`Transport` 协议允许并发 `request`。stdio 用以 int id 为键的 pending 表 + 写锁 + 读循环分发，已有 `test_calls_run_concurrently_on_one_connection`；HTTP 每个请求一次 POST，各用自己的守护线程，**没有并发测试** | `mcp/transport.py` `Transport`；`mcp/stdio.py` `StdioTransport.request`、`_dispatch`；`mcp/streamable_http.py` `HTTPTransport.request`、`_in_daemon_thread` |
| F11 | 同一 server 的并发请求**今天已经存在**：Channel 的所有会话共用一个 `AgentApp`（一个 `MCPManager`），会话内串行、会话间并发。0034 的"串行"只在一个 turn 之内成立 | `entry/session.py` 模块 docstring 第 2 条；`entry/channel/runtime.py` `ChannelRuntime` |
| F12 | 不支持 `list_changed`：客户端声明空 capabilities；stdio `_dispatch` 丢弃通知；HTTP 没有 GET 流；工具表在 `start()` 后固定。annotations 是连接时的快照 | `mcp/client.py` `MCPClient.connect`；`mcp/stdio.py` `_dispatch`；`mcp/streamable_http.py` `_matching`；`mcp/manager.py` 模块 docstring |
| F13 | 配置：未知键静默忽略；`enabled`/`disabled` 不是布尔（含显式 `null`）时拒绝该条目，被拒条目以 FAILED 出现在 `statuses()`、启动日志和 `/mcp`。`enabled`、`tools` 已是在共享 `mcpServers` 形状上加的扩展键。0034 Q2：`.mcp.json` 可能来自仓库，不提供放宽开关 | `mcp/config.py` 模块 docstring、`_enabled`、`parse_mcp_config`；`MCPManager.start` |
| F14 | 可观测性：启动日志和 `/mcp` 只打印工具数；`ToolDetail` 只有 name/tool/description。`.mcp.json` 面向用户的唯一说明是 AGENTS.md 的 "MCP servers" 一节 | `entry/assembly.py` `_log_mcp_outcome`；`entry/cli/_repl.py` `Repl._mcp`；`mcp/manager.py` `ToolDetail` |
| F15 | 分层：`omicsclaw/tools/` 只许 import `omicsclaw.schema`；`omicsclaw/mcp/` 里只有 `manager.py` 触及 `omicsclaw.tools`；其他层不 import `omicsclaw.mcp` | `tests/tools/test_tools_is_a_leaf_layer.py`；`tests/mcp/test_mcp_is_a_layer.py` `test_only_the_manager_reaches_into_the_tool_layer` |
| F16 | 测试基线：§6 的测试命令 456 passed（D4 改动出现之前测得）；第三版重测 470 passed、1 failed，失败的是 E1/E2 实施中的 `test_open_app.py::test_each_mcp_approval_card_shows_the_arguments_of_its_own_call`（断言仍按 E1 之前的 reason 格式，未带 `inert_block` 的续行前缀），实施前以 D4、E1/E2 合入后的结果为基线。`test_an_mcp_tool_defaults_to_the_guarded_policy` 断言默认 `concurrency_safe is False`（实施后依然成立）。`test_manager.py` 的 `_auto` 用 `ToolPolicy(approval_mode=AUTO)` 整体替换 policy，会抹掉并发标记，新测试不能复用 | `tests/tools/test_mcp_tool.py`；`tests/mcp/test_manager.py` `_auto` |

## 4. 设计

### 4.1 数据流与分层

```
tools/list 条目 → mcp/client.py  _read_only_hint(entry) → RemoteTool.read_only_hint
  → mcp/manager.py     safe = remote.read_only_hint and server.parallel_read_only
  → tools/mcp_tool.py  MCPTool(..., concurrency_safe=safe) → _default_policy
  → ToolRegistry.is_concurrency_safe → engine _concurrency_groups
```

"readOnlyHint → 并发安全"的映射**只在 manager 一处**（符合 F15）；引擎、注册表、权限层一行
不改；工具层的新参数按效果命名。T4 加结构测试：`omicsclaw/` 下 `mcp/` 以外的 `.py` 不得出现
`readOnlyHint`、`read_only_hint`、`parallelReadOnly`、`parallel_read_only`（今天全仓都没有）。

### 4.2 各层改动

**client**（`mcp/client.py`）：`RemoteTool` 增加 `read_only_hint: bool = False`，由 `_remote_tool` 填写：

```python
def _read_only_hint(entry: Mapping[str, Any]) -> bool:
    """Whether the entry's ``annotations`` object sets ``readOnlyHint`` to JSON true."""
    annotations = entry.get("annotations")
    return isinstance(annotations, Mapping) and annotations.get("readOnlyHint") is True
```

**config**（`mcp/config.py`）：`ServerConfig.parallel_read_only: bool = True`，由 `_parse_server`
里的 `_parallel_read_only(entry)` 读 `entry.get("parallelReadOnly", True)`：不是布尔（含 `null`）
则拒绝该条目，理由 `'parallelReadOnly' must be true or false`；某个键去掉大小写、`-`、`_` 后
等于 `parallelreadonly` 却不是原样拼写，也拒绝，理由 `unknown key 'parallelReadonly'; did you
mean 'parallelReadOnly'?`。被拒条目沿用 F13 的显示路径；模块 docstring 的键列表补上此键。

**tool**（`tools/mcp_tool.py`）：`MCPTool.__init__` 增加关键字参数 `concurrency_safe: bool = False`，
只传给 `_default_policy(server, *, concurrency_safe=False)`，后者只多设这一个字段；传了显式
`policy=` 时忽略它（显式 policy 是完整声明）。`_default_policy` 原 docstring 保留，补一句
"*concurrency_safe* is the caller's to set; every other field is fixed here."

**manager**（`MCPManager._mount`）：`safe = remote.read_only_hint and server.parallel_read_only`，
传给 `MCPTool(..., concurrency_safe=safe)` 和 `ToolDetail(..., concurrency_safe=safe)`（新字段，
默认 `False`）。模块 docstring 补一句：标为 `readOnlyHint: true` 的工具以并发安全挂载，除非
条目写了 `parallelReadOnly: false`；policy 其他字段不随 hint 变。

**entry**：`_log_mcp_outcome` 改为 `"MCP server %s: %d tool(s), %d parallel"`；`Repl._mcp`
改为 `(3 tool(s), 2 parallel)`。两处只数 `ToolDetail.concurrency_safe`，不输出参数。

### 4.3 信任边界：分批不是 tool use decision

一个调用要经过三个决定：**是否提供**（allowlist 和 `_mount`）、**是否调用**（模型）、**是否
放行**（权限模式、规则、受保护路径和审批，读 `read_only`、`approval_mode`、`risk_level` 与参数，
F7）。hint 不进入其中任何一个：工具表不变，definition 不含 hint，policy 除 `concurrency_safe`
外逐字段不变（T4 整体相等断言）。分批只决定"已被选中、将被同样审批的调用在哪个时间窗里
执行"：串行与并行下被执行的调用集合、各自的审批问题和权限结论都相同。所以它是调度决定，
不是 tool use decision。hint 缺省 `false` 时保持屏障，与规范的缺省一致。

但调度会**间接**影响两件事：
1. **人做审批时的判断质量。** 并发后多张卡同时待决，而 HEAD 上 MCP 卡片不带参数（F9）：审核
   探针里参数为 "harmless" 和 "rm-everything" 的两张卡内容完全相同，"是否放行"名义上
   不变、实际上退化。**并发审批的可区分性依赖 D4 与 E1/E2 合起来**：D4 让 reason 带参数预览；
   预览被 `MAX_PREVIEW_CHARS`（1,000 字符）截断时 `reason_shows_call` 为 `False`，`_approval_line`
   经 `approval_body` 再附上多行参数（缩进、键排序的 JSON），差异不会只藏在预览的截断点之后。但正文
   本身也有上限：理由与参数**合计** `MAX_APPROVAL_BODY_LINES = 400` 行、`MAX_APPROVAL_BODY_CHARS =
   12_000` 字符（按显示文字计，第三批修复；E2 时是每块 40 行、4,000 字符）。超过时 CLI 卡片照样截断，
   截断处以 `…` 标出，首行注记按原文给出显示了多少行与字符、共多少（CLI 提示符也重复这条注记），
   落在上限之后的差异在 CLI 上仍看不见，只能从注记得知卡片不完整；Channel 上（0052 第三版 §4.7）
   被截断的卡片不出卡、直接拒绝。reason
   与参数都经 `entry/display.py` 中和，参数里的换行或转义序列伪造不出另一张卡的开头。所以两者都是
   硬前置。
2. **同批观察结果的正确性。** server 谎报只读时，最坏后果（F3、F6）：同批的本地 `read`/
   `use_skill` 读到写入前、写到一半或写完后的文件（stdio server 的 cwd 是 workspace）；两个
   谎报的工具并发改 server 侧状态；同一条消息里隐含先后的两个调用被打乱。这些只是"这一轮
   观察不对"，不越权、不绕过审批；按厂商 API 语义，同一条消息里的调用本应互不依赖。谎报也
   换不来新能力：stdio server 以用户身份运行，本来就能写任何东西；HTTP server 碰不到本机。

**更常见的是诚实但无法并发的 server**：单线程顺序处理时排队时间计入 `tool_timeout`，生产上是
**600 s**（F5），同批累计超过 600 s 才新增超时，秒级只读查询不受影响；多线程写 stdout 把行写乱
时响应被丢掉，调用要挂满 600 s；远端也可能限流。这些用 `parallelReadOnly: false` 处理（Q2）。

### 4.4 与其他计划和 D4、E1/E2 的交互

- **D4、E1/E2**（工作树中，未提交）：`tools/preview.py` 的 `preview_arguments`（上限
  `MAX_PREVIEW_CHARS = 1000`，凭据键由 `is_credential_key` 判定、值换成 `REDACTED`，不安全字符经
  `escape_unsafe` 转义），`MCPTool._reason` 把它接在 server/origin/tool 之后并返回是否完整；
  `MCPTool.execute` 以 `reason_shows_call=` 交给 `require_approval`。本计划不改 reason；D4、E1/E2 改
  `execute`/`_reason`，T2 改 `__init__`/`_default_policy`，同文件不相邻，后落地者 rebase。
- **0052**（第三版）：第一阶段只有文本作答。卡片带会话内单调的 `#n` 与随机代码（0052 §4.3）；
  授予类裸动词只在恰有一张已呈现、满足呈现时间判定的卡时结算，多张时只列出 `#n 工具名`、不结算；
  动词加 `#n` 或代码结算指定的卡；DENY 裸动词拒绝发起人在本会话的全部待批（0052 第三版 §4.6）。
  按钮与"批准全部"推到第二阶段（0052 §7 B1、B6）。本计划不依赖 Channel 今天的结算入口。
- **0054**：`ask_user` 声明 `concurrency_safe=False`，靠 `_concurrency_groups` 单独成批充当
  屏障。本计划不改分批逻辑，只让部分 MCP 工具成为"安全"一方；`ask_user` 仍独占一批，排在
  它后面的调用仍等回答（接缝审核已确认）。
- **0047 / 0051**：`allowed_in_background` 仍取默认 `False`，0047 A4 不受影响；`Repl._mcp`
  那一行在热点文件 `_repl.py` 里，排在 0051 之后 rebase。

### 4.5 `list_changed`

不改变 F12：hint 在连接时固定，改了要重启才生效。将来做热重载，重新 `tools/list` 时必须重建
`MCPTool`，让 policy 随之重算。

## 5. 开放问题（均已按推荐裁定，2026-09-23）

**Q1 记录哪些 annotations？** **已定：只记 `readOnlyHint`。** 另外三个没有消费者，多存一个
不可信字段就多一个未经裁定拿它做决定的入口；`destructiveHint`/`idempotentHint` 只在
`readOnlyHint == false` 时有意义（schema.ts），`idempotentHint` 与并发无关。

**Q2 信任开关。** **已定：按 server 的 opt-out `parallelReadOnly: false`（默认 true）。**
opt-in 会让裁定对不改配置的用户等于没生效；不设开关则无法并发的 server 只能靠写代码。键名
按效果命名而不叫 `trustAnnotations`，以免将来接别的 hint 时悄悄扩大信任范围；只能收紧，
符合 0034 Q2。审核附带的条件已落实：近似错拼被拒、并行数量可见（§4.2）。

**Q3 每个 server 是否加信号量？** **已定：不加。** (1) 两种传输都支持多路复用（F10）；(2) 跨
会话并发今天已存在（F11），只在 turn 内加只修一半；(3) 生产超时 600 s，排队要累计超过 600 s
才超时，这类 server 用 opt-out 更直接。原稿"default 模式下审批起节流作用"删去：在
auto-approve、`s` 和 allow 规则下不成立。将来要加，放在 `MCPManager._call`（覆盖跨会话）。

**Q4 hint 是否联动权限？** **已定：不做，明确排除。** (1) 免审批或 read-only 放行正是规范禁止
的 tool use decision；(2) `read_only=True` 会让调用跳过受保护路径的必问（F7）。谎报的 stdio
server 自己就能写文件，用不着借道；真正的风险是 hint 标错的文件系统代理类 server（诚实的
作者也会标错），或它被 prompt 注入诱导去写 `.omicsclaw/settings.json` 这类受保护文件，而已有
allow 规则或会话授权时就没人再被问到；(3) read-only 模式连 `web_search` 都拒绝（F7），远端
MCP 的只读工具同样是向外发送。将来要做须另立计划，只允许部署级别逐个 server opt-in。

**Q5 是否显示哪些工具会并行？** **已定：做最小显示**（启动日志和 `/mcp` 的并行数，T4）。

## 6. 任务拆分

测试命令（每个任务都跑；基线见 F16）：

```
PYTHONDONTWRITEBYTECODE=1 /opt/conda/envs/rapids_singlecell/bin/python -m pytest -p no:cacheprovider -q -o addopts="" \
  tests/mcp tests/tools/test_mcp_tool.py tests/tools/test_tools_is_a_leaf_layer.py tests/engine/test_executor.py \
  tests/entry/test_open_app.py tests/entry/test_subagent_wiring.py tests/permission/test_gate.py
```

T4 起另跑 `tests/entry/test_cli_commands.py`。顺序：T0 随时 → T1、T2、T3（不改变行为，
顺序任意）→ **D4、E1/E2 合入** → T4 → T5 → T6。

**T0 HTTP 并发测试**（最先落地，今天的代码应已通过）：在 `tests/mcp/test_streamable_http.py`
的 `ThreadingHTTPServer` 回环里，处理器用 `threading.Barrier(2, timeout=5)` 会合，两个
`tools/call` 同时在途且都成功。变异：给 `HTTPTransport.request` 外包一把 `asyncio.Lock` ⇒ 失败。

**T1 客户端解析**（`mcp/client.py`；`tests/mcp/test_client.py`，`ScriptedTransport`）：
`annotations.readOnlyHint` 为 `true` 得 True；缺失、`false`、`"true"`、`1`、`annotations` 不是
对象、只在顶层写 `readOnlyHint`，都得 False。变异：真值判断；恒 False；读顶层键。

**T2 `MCPTool` 关键字参数**（`tools/mcp_tool.py`；`tests/tools/test_mcp_tool.py`）：默认
`concurrency_safe is False`（既有用例不改）；`concurrency_safe=True` 时 `tool.policy.concurrency_safe
is True`；传显式 `policy=` 时 `tool.policy is trusted`。变异：忽略该参数；该参数覆盖显式 policy。

**T3 配置键**（`mcp/config.py`；`tests/mcp/test_config.py`）
- 验收：缺省 True；`false` 得 False；`"no"`、`0`、`null` 使条目被拒、理由点名该键；
  `parallelReadonly`、`parallel_read_only`、`ParallelReadOnly` 使条目被拒、理由含
  `did you mean 'parallelReadOnly'`；其他条目照常加载。变异：缺省改 False；接受非布尔；
  删掉近似键检查。
- 核实：用 Claude Code 等共用 `<workspace>/.mcp.json` 的客户端加载带该键的文件，确认不会
  校验失败（审核未核实；`enabled`、`tools` 是同类先例），结果写进交付记录。

**T4 manager 接线与显示**（`mcp/manager.py`、`entry/assembly.py`、`entry/cli/_repl.py`；
**D4、E1/E2 合入之后才合入**）
- 验收：scripted server 列出 `look`（`readOnlyHint: true`）和 `poke`（无 annotations）：
  `is_concurrency_safe` 分别 True/False；**整体相等** `policy_for(look) ==
  dataclasses.replace(policy_for(poke), concurrency_safe=True)`；`look` 的 definition 序列化后
  不含 `readOnlyHint`/`annotations`；`parallel_read_only=False` 时两者都 False；`ToolDetail`
  与之一致；日志与 `/mcp` 输出 `1 parallel`（关闭时 `0 parallel`）；§4.1 的结构测试通过。
- 测试：`tests/mcp/test_manager.py`、`test_mcp_is_a_layer.py`；`tests/entry/test_open_app.py`、`test_cli_commands.py`。
- 变异：去掉 `and server.parallel_read_only`；不传 `concurrency_safe`；hint 同时映射到
  `read_only=True` 或 `approval_mode=AUTO`（整体相等捕获）；`tools/` 里出现 `read_only_hint`。

**T5 端到端并发**（stdio；新文件 `tests/mcp/test_parallel.py`，及 `tests/entry/test_open_app.py`）
- `tests/mcp/fake_server.py` 加 `--meet`（默认工具表不变），追加 `meet`（`readOnlyHint: true`）
  和 `meet_unmarked`（无 annotations）：每次调用先登记到场，再在 `seconds` 内等第二个调用
  到场，返回 `met` 或 `alone`。
- 走真实 stdio 的 `MCPManager` → `ToolRegistry` → `execute_tool_calls`，**保留生产 policy**，
  用 `use_tool_context(approval=自动批准)` 代替重新注册（F16）：两个 `meet` → 都 `met`；
  两个 `meet_unmarked` → 都 `alone`；`parallel_read_only=False` 时两个 `meet` → 都 `alone`；
  `[meet, meet_unmarked, meet]` → 三批、全 `alone`，Observation 顺序与调用顺序一致。
- `open_app` 层：`.mcp.json` 指向 `fake_server.py --meet`，断言
  `app.registry.is_concurrency_safe("mcp__fake__meet") is True`、`meet_unmarked` 为 False（F8）。
- 变异：manager 全传 True（`meet_unmarked` 捕获）；全传 False（`meet` 捕获）。

**T6 文档**：0034 的 §2 表第 22 项、§5 第一行、附录 A M1 改为指向本计划，§7"已知限制"
补"无法并发的 server 用 `parallelReadOnly: false`"；AGENTS.md "MCP servers" 补
`parallelReadOnly`（默认 true、只能收紧、近似错拼被拒）和 `/mcp` 的并行计数；
`docs/FRAMEWORK-REBUILD.md` Step 6.5 补一句；README 按惯例记录里程碑；本计划补交付记录（含 T3 核实结果）。

## 7. 非目标

- 权限联动（Q4）；另外三个 hint 和 `outputSchema`（Q1）；每 server 信号量与暴露
  `max_concurrent_tools`（Q3）；`list_changed` 与热重载（§4.5）。
- 改动引擎、注册表、权限层或 `_pathlock`；审批 reason 的参数预览（D4）与审批行的显示层（E1/E2）；逐工具的并行清单；
  环境变量级总开关。

## 8. 风险

- **R1 无法并发的 server 出现新的超时**（§4.3）：只在同批累计超过 600 s 时触发，严重度低；
  stdout 写乱时会挂满 600 s。应对：`parallelReadOnly: false`，写进 0034 §7 与 AGENTS.md。
- **R2 server 谎报 hint**：同批观察结果可能出错，但不越权（§4.3）。
- **R3 将来有人把 hint 接到 `read_only`/`approval_mode`**：T4 整体相等断言与结构测试把关。
- **R4 部署用 `register(tool, policy)` 整体替换 policy 时失去并行**（F4），`/mcp` 计数仍按挂载
  时的值显示。这是"部署优先"的既有语义，生产装配不替换 MCP 工具的 policy；写进文档。
- **R5 同时待决的审批卡片变多。** 可区分性依赖 D4 与 E1/E2（§4.3）。它们之后仍有三点：(1) CLI 卡片号 `#n`
  按审批计数，与 transcript 调用编号不是一套；(2) CLI 对第一张卡答 `s` 后，已排队的同工具第二张卡
  仍会再问（`Repl._ask` 只在 `await self._source.read` 之前查 `_already_granted`），多问一次、
  不会误放行；(3) Channel 上并发卡片的截止时间同时起算，要在同一个 `approval_timeout_s` 窗口里
  答完。Channel 的多卡作答由 0052 desk 处理（§4.4），不依赖今天的任何结算入口。
- **R6 新增键可能让共用 `.mcp.json` 的其他客户端校验失败**（未核实）：T3 核实，若确有拒绝，
  报 owner 另定键的位置。
- **R7 工作树有其他会话的未提交改动**（`tools/context.py`、`tools/mcp_tool.py`（D4、E1/E2）、`entry/render.py`、`entry/display.py`（E1/E2）、`_repl.py`、
  `assembly.py` 等）：引用一律带符号名；`omicsclaw/mcp/` 暂无改动。

## 9. 审核处置

| 审核条目 | 处置 | 位置或理由 |
|---|---|---|
| M1 并发 MCP 卡片无法区分 | 采纳；owner 选 (a)，由缺陷修复 D4 实现，本计划列为硬前置，删去"不是新形态" | "前置"；F9；§4.3 第 1 点；R5；T4 合入门槛 |
| M2 规范引用不完整 | 采纳：逐字引用，论证分批不是 tool use decision | §1；§4.3 |
| M3 `tool_timeout` 写错 | 采纳：改为生产 600 s；R1 降级；Q3 理由调整 | F5；§4.3；R1；Q3 |
| M4 opt-out 找不到、无法确认 | 采纳：T6 加 AGENTS.md；日志与 `/mcp` 显示并行数；近似错拼被拒 | §2 第 3、4 条；§4.2；T3；T4；T6 |
| S1 按效果命名，映射放 manager | 采纳：`MCPTool(concurrency_safe=)`，映射只在 `_mount`，整体相等断言移到 T4 | §4.1；§4.2；T2；T4 |
| S2 T5 保留生产 policy | 采纳：`use_tool_context` 自动批准；加 `open_app` 层断言 | T5 |
| S3 测试命令补三个文件 | 采纳：`test_tools_is_a_leaf_layer.py`、`test_subagent_wiring.py`、`test_gate.py` 均已加入；T4 起另跑 `test_cli_commands.py` | §6 测试命令 |
| S4 R5 过时，补两点 | 采纳：改指 0052 desk；补截止时间同时起算、`s` 对已排队卡片无效 | R5；§4.4 |
| S5 Q3"审批节流"不成立 | 采纳：删去该理由，结论不变 | Q3 |
| S6 Q4 第 (2) 条 | 采纳：改为标错的文件系统代理类 server 与注入诱导 | Q4 |
| S7 T2 的 definition 断言无意义 | 采纳：移到 T4 | T2；T4 |
| S8 HTTP 并发测试最先落地 | 采纳：独立为 T0 | T0 |
| S9 显式 `null`；其他客户端兼容 | 采纳：`null` 写进验收；兼容性在 T3 核实 | T3；R6 |
| Q1 只记 `readOnlyHint` | 已定 A | Q1 |
| Q2 `parallelReadOnly` opt-out | 已定 B，附带条件（M4、近似错拼）已落实 | Q2；T3；T4 |
| Q3 不加信号量 | 已定不加，理由按 M3、S5 修正 | Q3 |
| Q4 排除权限联动 | 已定排除，第 (2) 条按 S6 修正 | Q4 |
| Q5 可观测性 | 改为做最小显示 | Q5；T4 |
| 事实核对（F1–F14 行号漂移、§1、§4.3） | 改为"符号名 + 行号"；F9 改写，不再引用 Channel 结算入口；0034"§2 第 22 行"改为"表第 22 项"；新增 F14–F16 | §3 |
| 接缝审核 M16（`settle_approval` 将被删） | 采纳：F9、R5 不再依赖 Channel 结算入口，改指 `ApprovalBroker` 与 0052 desk | F9；R5；§4.4 |
| 第二轮 S5（§4.4 对 0052 desk 的描述过时；目标 5"annotations 只出现在 `mcp/`"不可验证）；第二轮 M1 与第三轮 O4 行（显示层与 `reason_shows_call`） | 采纳：§4.4 按 0052 第二版改写，按钮与"批准全部"归第二阶段；目标 5 改为四个 hint 词汇，与结构测试一致；E1/E2 列为与 D4 并列的硬前置 | "前置"；§2 目标 5；F9；F16；§4.3 第 1 点；§4.4；R5；T4 合入门槛 |
| 第四轮 S5 遗留（§4.4 仍引"0052 第二版 §4.5"） | 采纳：已核对 0052 第三版 §4.6 即"文本回复：语法与判定"（裸动词与 `was_seen`、多卡只列 `#n 工具名`、动词加 `#n` 或代码、DENY 拒绝全部），改引 §4.6，序号与代码改引 §4.3 | §4.4 |
| 第四轮"其余非阻塞文字不一致"：§4.3"差异不会藏在截断点之后"说过头 | 采纳：按 `tools/preview.py` 与 `entry/display.py` 的实际行为改写。预览截断后参数段接上，但参数段自身有上限（今天每块 40 行 / 4,000 字符，第三批修复后理由与参数合计 400 行 / 12,000 字符）；超限时 CLI 截断并注明，Channel 不出卡。F9 的"完整参数"同样改掉 | §4.3 第 1 点；F9 |
| 第五轮"plan 与代码不一致"：§4.3 仍写"附上 `arguments_block`" | 采纳：`arguments_block` 已删除，参数由 `approval_body` 渲染；上限按显示文字计、截断处带 `…`、注记按原文计数并在 CLI 提示符重复（已读 `entry/display.py` 与 `_repl.py` `_APPROVAL_PROMPT` 核实）；"前置"里的 E1/E2 名单同步改为现状 | "前置"；§4.3 第 1 点 |
