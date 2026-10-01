# MCP 工具集成

OmicsClaw 的 MCP 集成让 agent 能调用任何遵循 [Model Context Protocol](https://modelcontextprotocol.io) 的外部工具服务器。每个 MCP 工具被包装成一个 `MCPTool`，以 `mcp__{server}__{tool}` 的名字注册进统一的 `ToolRegistry`。对引擎来说它和本地工具没有区别：调度、超时、审批暂停、错误作为 Observation 回传，这些机制全部沿用，**主循环没有为 MCP 改一行代码**。

本层对应重建步骤 Step 6.5（计划 0034）。整个 `omicsclaw/mcp/` 只用标准库，没有引入 MCP SDK。

---

## 1. 架构总览

```
<workspace>/.mcp.json                      （--mcp-config / OMICSCLAW_MCP_CONFIG 可改）
    │ load_mcp_config()        ${VAR} 展开；坏条目进 rejected，其余照常
    ▼
MCPConfig(servers, rejected)
    │ open_app()：在 build_app() 之前
    ▼
MCPManager.start()             并发连接所有 enabled server，每个限时 mcp_connect_timeout_s（30 s）
    │ open_transport()   stdio → StdioTransport / http → HTTPTransport
    │ MCPClient.connect()  initialize → notifications/initialized → tools/list（翻页）
    │ _mount()           每个远端工具 → MCPTool(mcp__{server}__{tool})，按白名单过滤、同名跳过
    ▼
manager.tools()  ──►  build_app(mcp=manager)
                        mounted = (*foundation, *mcp.tools())
                        hook_tools → gate_tools → ToolRegistry → （最后追加 task）
    ▼
AgentEngine：模型发出 ToolCall(name="mcp__context7__resolve_library_id")
    │ ToolRegistry.execute → GatedTool → MCPTool.execute
    │   _require_object(arguments)         参数必须是 JSON 对象
    │   require_approval(...)              审批卡片写明调用去向与参数预览
    │   MCPManager._call → MCPClient.call_tool → Transport.request("tools/call")
    │   render_result → truncate_output(32,000)
    ▼
Observation 回到模型上下文
    …
AgentApp.aclose()  先排空会话，再 MCPManager.aclose() 关闭所有连接
```

| 组件 | 代码位置 | 职责 |
|---|---|---|
| `load_mcp_config` / `parse_mcp_config` | `omicsclaw/mcp/config.py` | 读 `.mcp.json`，校验、变量展开，得到 `MCPConfig` |
| `Transport` Protocol + JSON-RPC 帧 | `omicsclaw/mcp/transport.py` | `start / request / notify / negotiated / aclose`；消息分类；错误类型 |
| `StdioTransport` | `omicsclaw/mcp/stdio.py` | 子进程的 stdin/stdout 上跑 NDJSON |
| `HTTPTransport` | `omicsclaw/mcp/streamable_http.py` | Streamable HTTP：每条消息一个 `POST` |
| `MCPClient` | `omicsclaw/mcp/client.py` | 握手、分页 `tools/list`、`tools/call`、结果渲染 |
| `MCPManager` | `omicsclaw/mcp/manager.py` | 并发连接、状态快照、铸造 `MCPTool`、输出上限、关闭 |
| `MCPTool` / `mcp_tool_name` | `omicsclaw/tools/mcp_tool.py` | 适配器：把远端工具变成本地 `Tool`；命名规则；默认策略；审批 |
| `open_app` / `_log_mcp_outcome` | `omicsclaw/entry/assembly.py` | 唯一的接线点 |
| `/mcp` | `omicsclaw/entry/cli/_repl.py` `Repl._mcp` | CLI 查看各 server 状态 |

**依赖方向**：`omicsclaw.mcp` 只 import 标准库、`omicsclaw.tools`（以及经由它的 `schema`）和 `omicsclaw.version`；**只有 `manager.py` 接触 tools 层**，协议模块只讲 MCP、只抛 MCP 错误。反方向上，`engine`、`context`、`provider`、`skills`、`tools` 都不 import `omicsclaw.mcp`。`tests/mcp/test_mcp_is_a_layer.py` 钉住了这些约束。

---

## 2. 配置：`.mcp.json`

### 2.1 位置与加载

- 默认路径：**`<workspace>/.mcp.json`**（`AppConfig.mcp_config_path()`）。
- 修改：`--mcp-config <path>` 或 `OMICSCLAW_MCP_CONFIG`。
- **文件不存在 = 不启用 MCP**，`open_app` 此时和 `build_app` 完全等价，`AgentApp.mcp` 为 `None`。
- **文件存在但读不了、不是合法 JSON、顶层不是对象、`mcpServers` 不是对象**：抛 `MCPConfigError`，**启动失败**。
- **单个条目不合法**：只拒绝这一条，记入 `MCPConfig.rejected`，原因会作为 `FAILED` 状态显示；其余条目照常加载。

### 2.2 格式

使用 Claude Code、Claude Desktop 共用的 `mcpServers` 形状：

```json
{
  "mcpServers": {
    "context7": {
      "command": "npx",
      "args": ["-y", "@upstash/context7-mcp"]
    },
    "lab-lims": {
      "type": "http",
      "url": "https://lims.example.org/mcp",
      "headers": {"Authorization": "Bearer ${LIMS_TOKEN}"},
      "tools": ["list_samples", "get_run_metadata"]
    },
    "local-annotator": {
      "command": "python",
      "args": ["-m", "my_annotator_mcp"],
      "env": {"ANNOT_DB": "${ANNOT_DB:-/data/annot.sqlite}"},
      "enabled": false
    }
  }
}
```

（`lab-lims`、`local-annotator` 是示意名称。）

### 2.3 `ServerConfig` 字段

| 键 | 类型 | 说明 |
|---|---|---|
| `type` / `transport` | string | `"stdio"` 或 `"http"`。`"streamable-http"`、`"streamable_http"` 视为 `"http"`。`"sse"`、`"websocket"`、`"ws"` **明确拒绝**（不支持）。两个键都写且不一致时拒绝 |
| `command` | string | stdio server 的可执行程序，必填且非空 |
| `args` | string[] | 命令行参数 |
| `env` | object 或 `["KEY=VALUE"]` | 额外传给子进程的环境变量，两种写法都接受 |
| `url` | string | http server 的端点，必须以 `http://` 或 `https://` 开头 |
| `headers` | object | 每个 HTTP 请求都带的请求头 |
| `enabled` / `disabled` | bool | 不删条目就能关掉一个 server。状态显示为 `disabled` |
| `tools` | string[] | server **自己的**工具名白名单；缺省表示全部 |

**传输推断**：没写 `type` 时，有 `command` 就是 stdio，有 `url` 就是 http；**两个都写则拒绝**，要求补一个 `type`。未知的键会被忽略。

**变量展开**：`command`、`args`、`env` 的值、`url`、`headers` 的值中的 `${VAR}` 与 `${VAR:-default}` 从进程环境展开。`${VAR}` 未设置时**拒绝该 server**，拒绝原因只点出变量名，不暴露其他内容。`${VAR:-default}` 在变量未设置或为空时取默认值。

---

## 3. 传输层

### 3.1 `Transport` Protocol

```python
class Transport(Protocol):
    async def start(self) -> None: ...
    async def request(self, method: str, params: Mapping | None = None) -> Any: ...
    async def notify(self, method: str, params: Mapping | None = None) -> None: ...
    def negotiated(self, protocol_version: str) -> None: ...
    async def aclose(self) -> None: ...
```

`start` 返回之后，`request` 和 `notify` 可以并发调用。取消一个 `request` 只放弃这一次请求，不关闭传输。`aclose` 之后所有调用都抛 `MCPTransportError`，`aclose` 本身可以重复调用。

错误类型：

| 异常 | 含义 |
|---|---|
| `MCPError` | 本包所有错误的基类 |
| `MCPTransportError` | 信道失败或已关闭，答复不可能到达 |
| `MCPProtocolError` | server 的答复违反协议（版本不支持、形状不对） |
| `MCPRemoteError` | server 用 JSON-RPC error 对象回答了请求（带 `code` / `message` / `data`） |
| `MCPToolError`（`client.py`） | 工具执行了，但报告 `isError`；消息就是它的输出 |

`classify()` 把收到的消息分成 `response` / `request` / `notification` / `invalid`。**同时带 `id` 和 `method` 的消息一律视为 server 发来的请求**，即使它的 id 恰好和我们某个挂起请求相同。`is_request_id` 用 `type(value) is int` 判断，所以 `"id": true` 不会被当成请求 1。

### 3.2 `StdioTransport`

- **帧格式**：换行分隔的 JSON（NDJSON）。stdout 上不是 JSON 的行会被忽略，因为很多 server 会在那里打印启动横幅。
- **单条消息上限** `MAX_MESSAGE_BYTES = 8 MiB`。超限时关闭传输，并让所有挂起请求失败，同时说明原因。
- **stderr 持续排空**，保留最近 `STDERR_TAIL_LINES = 20` 行（每行截到 500 字符）。进程意外退出时，报错里会附上退出码和这段 stderr 尾部，而不是只有一句 "transport closed"。
- **server 发来的请求**：`ping` 回 `{}`，其他方法回 `-32601`（method not found）。
- **取消**：请求已经写出后被取消时，会发送 `notifications/cancelled`（`initialize` 除外），传输保持打开。
- **环境变量白名单**：子进程只继承 `INHERITED_ENV_VARS`（POSIX 上是 `HOME LOGNAME PATH SHELL TERM USER`，Windows 另有一组），再叠加配置里的 `env`，并跳过导出的 shell 函数。**进程环境里的 `LLM_API_KEY`、`TELEGRAM_BOT_TOKEN` 等不会流到第三方 server**，除非配置里显式传入。
- **工作目录**：`open_app` 传入 `cwd=config.workspace`，所以 server 在 workspace 下启动。
- **进程组**：POSIX 上以 `start_new_session` 启动，关闭时对整个进程组发信号，`npx → node` 这类孙进程也能一起清掉。
- **关闭顺序**（完成过握手的 server）：关 stdin → 等 `EXIT_GRACE_S`（2 s）→ 进程组 `SIGTERM` → 再等 2 s → `SIGKILL` → 最后再对整组 `SIGKILL` 一次清理后代。握手未完成的 server 直接整组 KILL。
- **事件循环归属**：传输属于启动它的事件循环。该循环停止时读循环把传输标记为关闭，之后的调用立即报错，而不是永久挂起。

### 3.3 `HTTPTransport`（Streamable HTTP）

- 每条消息一个 `POST`，`Accept: application/json, text/event-stream`。答复可以是 JSON 体（单条或批量），也可以是 `text/event-stream`，两种都解析。
- server 分配的 **`Mcp-Session-Id`** 会在之后每条消息里带回；握手协商出的版本放在 **`MCP-Protocol-Version`** 请求头里。
- **关闭时**，如果存在 session，就发一个 `DELETE` 结束服务端会话（5 s 上限，失败忽略）。
- **不跟随重定向**：3xx 被转成错误，提示"配置最终 URL"，因此配置的请求头（比如 Bearer token）不会被重发给没人配置过的主机。
- **错误消息里的 URL 会脱敏**（`redact_url`）：去掉 user-info、query 和 fragment，有 query 时显示为 `?…`。
- **会话过期**：带着 session 收到 404 时报错"server 不再认识这个会话，重启以重连"，不会自动重连。
- 答复体上限 `MAX_RESPONSE_BYTES = 8 MiB`；事件流累计超过这个值时也会失败。
- 每个请求跑在**自己的 daemon 线程**上（`_in_daemon_thread`，不用 `asyncio.to_thread`）。被取消的请求立即返回，线程最迟在 socket 超时后结束，不占用共享线程池，也不拖住进程退出。socket 超时默认 `DEFAULT_TIMEOUT_S = 600`，`open_app` 传入的是 `AppConfig.tool_timeout_s`。

---

## 4. 客户端：`MCPClient`

### 4.1 握手（`connect`）

```
1. transport.start()
2. → initialize {protocolVersion: "2025-06-18", capabilities: {}, clientInfo: {name: "omicsclaw", version: <omicsclaw.version>}}
   ← result.protocolVersion 必须属于 {2024-11-05, 2025-03-26, 2025-06-18}，否则 MCPProtocolError
3. transport.negotiated(version)
4. → notifications/initialized
5. → tools/list，沿 nextCursor 翻页，最多 MAX_TOOL_PAGES = 100 页
```

握手过程中任何失败（包括被取消）都会**先关闭传输再抛出**。没有名字的 `tools/list` 条目会被跳过并计数（`unnamed_tools`），之后在状态里报告。server 自述的 `name` / `version` / `instructions` 记录在 `ServerInfo` 中。

### 4.2 工具调用（`call_tool`）

`call_tool(name, arguments)` 接收模型给出的原始 JSON 字符串（空串视为 `{}`，不是对象则抛 `ValueError`），发送 `tools/call`，再用 `render_result` 把结果转成文本：

| 内容块 | 渲染 |
|---|---|
| `text` | 原文 |
| `resource`（内嵌文本） | 资源文本 |
| `resource`（二进制） | `[binary resource <uri> (<mimeType>) not shown]` |
| `resource_link` | `[resource link: <name> <uri>]` |
| `image` / `audio` | `[image (<mimeType>, N base64 characters) not shown]` |
| 其他类型 | `[content of type '<type>' not shown]` |

多个块之间用换行拼接。**全部没有文本时，改用 `structuredContent` 的 JSON。** `isError: true` 时抛 `MCPToolError`，消息就是渲染出来的文本。非文本块不会被静默丢弃，模型至少知道有东西被省略了。

---

## 5. Manager：`MCPManager`

### 5.1 启动（`start`）

```python
manager = MCPManager(
    servers,
    connect_timeout_s=config.mcp_connect_timeout_s,   # 默认 30.0
    cwd=config.workspace,
    request_timeout_s=config.tool_timeout_s,          # HTTP socket 超时
    on_change=on_mcp_change,
)
await manager.start()
```

1. 被拒绝的条目先记为 `FAILED`（`error` = 拒绝原因）；`enabled=false` 的记为 `DISABLED`；其余记为 `PENDING`。
2. `asyncio.gather` **并发**连接所有 enabled server。每个都放在 `asyncio.timeout(connect_timeout_s)` 里，超时的直接 KILL 并记 `FAILED: did not finish connecting within 30s`。
3. **fail-soft**：单个 server 的任何失败（`MCPError`，或者其他异常，记为 `类型名: 消息`）只影响它自己的状态，**`start` 不会因此抛出**。
4. 全部结束后 `_mount()` 铸造工具，再通知一次状态。

`start` 只能调用一次，第二次抛 `RuntimeError`。`MCPManager` 也可以当 async context manager 用。

### 5.2 状态

```python
class ServerState(StrEnum): PENDING, CONNECTED, FAILED, DISABLED

@dataclass(frozen=True)
class ServerStatus:
    name: str; state: ServerState; transport: str
    tools: tuple[ToolDetail, ...]      # 注册名、远端名、描述
    skipped: tuple[str, ...]           # 未挂载的工具及原因
    error: str; info: ServerInfo | None
```

`statuses()` 返回所有 server 的快照：先是配置里的，再是被拒绝的。每次状态变化都会调用 `on_change(statuses)`。回调抛出的异常会被吞掉，因为本层不写日志，和其他层的约定一致。

### 5.3 挂载（`_mount`）

- 按**配置顺序**遍历 server，server 内部保持 server 返回的工具顺序。
- 按 `tools` 白名单过滤；白名单里点名、server 却没有提供的工具记入 `skipped`（`"<name>: named in 'tools' but not offered"`）。
- 名字重复时**先到者保留**，后到者记入 `skipped`（`"<tool>: <registry name> is already taken"`）。
- 每个工具的 `caller` 是 `functools.partial(self._call, client, remote.name)`，`origin` 是 `origin_of(server)`：stdio 为 `local process <command>`，http 为 `remote <脱敏 URL>`。

### 5.4 输出上限

`_call` 把每个工具结果截到 **`DEFAULT_MAX_OUTPUT_CHARS = 32_000`** 字符，并附一行 `[output truncated: showing the first N of M characters]`。`isError` 的输出也按同样规则截断。MCP 工具是唯一不自己限制输出的工具，所以上限放在 manager 的桥接调用里：面向模型的策略不放进协议层。

### 5.5 关闭

`aclose()` 幂等，并发关闭所有 client。`AgentApp.aclose()` 先排空会话，再关闭 MCP，然后是沙箱容器和记忆数据库。组装失败时 `open_app` 也会关闭已经启动的 server，不泄漏子进程（`test_a_failed_assembly_does_not_leak_the_servers`）。

---

## 6. 适配器：`MCPTool`（`omicsclaw/tools/mcp_tool.py`）

### 6.1 命名：`mcp__{server}__{tool}`

`mcp_tool_name(server, tool)` 是唯一的命名规则，UI 或其他代码要列出 MCP 工具名时应复用它。`sanitize_mcp_name` 对每一段做四件事：

1. `A-Za-z0-9_` 以外的字符（**包括非 ASCII 字符**）替换为 `_`；
2. 连续的 `_` 折叠成一个；
3. 去掉首尾的 `_`；
4. 结果为空时变成 `unnamed_<sha256 前 6 位>`。

这样任何一段都不可能含有 `__`，`name.split("__", 2)` 总能还原出 server 和 tool。

**总长上限 `MAX_TOOL_NAME_LENGTH = 64`**（OpenAI 和 Anthropic 都要求函数名满足 `^[a-zA-Z0-9_-]{1,64}$`）。放不下时**优先保留 server 段**，只有 server 段超过预算一半时才一起缩短。缩短方式是保留开头再追加整段的 6 位摘要，所以 `search_pubmed_by_author` 和 `search_pubmed_by_journal` 这类共享前缀的长名不会撞成同一个键。

例：`resolve-library-id` → `resolve_library_id`，`my--server` → `my_server`，`分析` → `unnamed_xxxxxx`。

**已知代价**：`get-thing` 和 `get_thing` 来自同一个 server 时会撞名。manager 保留第一个，把第二个记入 `skipped`。不给每个有损名字都加摘要是刻意的选择，理由写在 `sanitize_mcp_name` 的 docstring 中，`test_two_names_that_differ_only_by_a_separator_collide` 钉住了这一行为。

### 6.2 定义

- 描述：server 自己的描述，前面加 `[MCP:<server>]` 标签，其余不改写。
- schema：server 的 `inputSchema` 原样透传。解析失败（不是对象、JSON 解码失败等）时换成空对象 schema，原因记在 `MCPTool.schema_error`。**构造永远不会因为 server 的数据而失败**，一个坏工具不能拖垮同一个 server 的其他工具。
- `server` / `tool` 属性保留**未消毒**的原始名字。

### 6.3 默认策略

```python
ToolPolicy(
    risk_level=RiskLevel.HIGH,
    approval_mode=ApprovalMode.ASK,
    prompts_for_itself=True,
    tags=frozenset({"mcp", f"mcp:{server}"}),
)
```

- `HIGH` + `ASK`：第三方代码，这里既没写过也没审过，除了名字一无所知。
- **效果声明全部留空**（`read_only`、`touches_network` 都是 `False`，即"未声明"）：一个 server 可能是本地子进程，也可能在互联网另一端，写 `True` 或 `False` 都是猜测。`ToolPolicy` 明确规定 gate 绝不能凭一个没人写下的 `False` 放行。
- `concurrency_safe` 取默认值 `False`：MCP 工具在引擎里**串行执行**，每个都是一道写屏障（见第 10 节）。
- tags：部署要按 MCP 过滤时，`"mcp"` 能匹配所有 MCP 工具，`"mcp:<server>"` 匹配单个 server。

### 6.4 `execute`：先查形状，再审批，再调用

```
MCPTool.execute(arguments)
  1. _require_object(arguments)     不是 JSON 对象 → ToolArgumentError（空串视为 {}）
                                     只查形状，不按 schema 校验：server 自己校验
  2. require_approval(name, arguments, policy, reason=_reason(arguments))
       reason = "MCP server 'lab-lims' via remote https://lims.example.org/mcp, tool 'list_samples', with arguments:\n<preview>"
       没有审批通道 → 拒绝，server 根本不会被联系（fail-closed）
  3. outcome = caller(arguments)     可以是 async
  4. as_text(outcome)
```

参数预览由 `omicsclaw/tools/preview.py` 的 `preview_arguments` 生成：有长度上限（`MAX_PREVIEW_CHARS = 1000`），控制字符被转义，凭据类键名（`apikey`、`authorization`、`cookie`、`token` 等）下的值替换为 `[redacted]`。

`prompts_for_itself=True` 告诉权限 gate：这个工具会自己用描述实际效果的提示发问。因此在默认模式下 gate 把问题交给工具，不会再弹一次。gate 已经放行（`allow` 规则、`auto-approve` 模式）时，工具的 `require_approval` 会直接返回。

**Q2 的教训**：接入之前，`MCPTool` 声明了 `ASK`，但 `execute` 从来没有调用过 `require_approval`，也就是"声明了却没接上"。现在 `tests/tools/test_mcp_tool.py` 覆盖了：无通道时拒绝、拒绝时不触达 server、收紧方向生效、先查参数形状再审批、审批理由带调用去向。

### 6.5 放宽与收紧

- **`.mcp.json` 不提供放宽开关**，因为它在工作区里，可以被仓库内容控制。
- 放宽途径一：规则文件 `<workspace>/.omicsclaw/settings.json` 的 `allow`，**按完整注册名精确匹配**，例如 `"allow": ["mcp__context7__resolve_library_id"]`；带括号的模式匹配的是该工具 schema 里第一个必填 string 参数。
- 放宽途径二：部署代码用 `registry.register(tool, policy)` 重新注册（例如给可信工具设 `concurrency_safe=True`）。
- 收紧：`deny` / `ask` 规则，或 `--permission-mode read-only`。MCP 工具没有声明 `read_only`，所以在 read-only 模式下**全部被拒绝**。

---

## 7. 接线：`open_app`

```python
app = attach_sessions(await open_app(resolve_app_config()))   # CLI / Desktop / Channel 都走这里
...
await app.aclose()
```

`open_app` 的顺序：`load_mcp_config` → `open_sandbox` → （配置为空则直接 `build_app`）→ `MCPManager.start()` → `_log_mcp_outcome` → `build_app(mcp=manager)` → 记忆清扫。**`build_app` 本身不连接任何 server。**

**为什么在启动时阻塞连接，而不是异步注入**：`AgentApp` 的工具快照和 `ContextBudget.reserve_tool_tokens` 都在 `build_app` 里计算一次，工具定义又位于 prompt 前缀缓存区内。晚到的工具会让预算少算工具 token，还会作废之后的全部缓存。等待时间最多约等于单个 server 的连接超时，因为各 server 是并发连接的。

`_log_mcp_outcome` 为每个 server 写一行日志：

```
INFO    MCP server context7: 2 tool(s)
WARNING MCP server lab-lims failed: HTTP 401 from https://lims.example.org/mcp
WARNING MCP server lab-lims: skipped get_run_metadata: named in 'tools' but not offered
```

工具表顺序是：foundation 工具（`read_file`、`write_file`、`edit_file`、`bash`、`web_fetch`、`web_search`，可选的 `use_skill`、`plan_write`、`memory_*`）→ MCP 工具 → `task`（最后追加，见 `sub-agent.md`）。MCP 工具与调用方通过 `tools=` 传入的工具重名时，注册表抛 `ToolAlreadyRegistered`，**启动失败**。只有部署自己传入 `mcp__` 前缀的工具时才会遇到。

子代理从父注册表继承工具，所以默认也能调用 MCP 工具，审批仍然送到父 turn 的审批通道。

---

## 8. CLI：`/mcp`

`oc cli` 中输入 `/mcp`，读取**正在运行的** `MCPManager`：

```
> /mcp
  context7: connected (2 tool(s))
  lab-lims: failed (0 tool(s))
  local-annotator: disabled (0 tool(s))
```

没有配置文件时（`app.mcp is None`）输出 `No MCP servers configured.`。

它**只报告状态**，不能增删 server。`/help` 里 `/mcp` 那一行仍写着 `Manage MCP servers (/mcp list | add | remove)`：那是从旧 CLI 原样移植的目录文本（`entry/cli/_constants.py` 的 `SLASH_COMMANDS`，由移植保真测试逐元素比对，不能改），`list/add/remove` 子命令并不存在。旧的 `_mcp.py` 管理的是另一份 `~/.config/omicsclaw/mcp.yaml`，经由 `langchain_mcp_adapters` 访问 server；两个管理器对应两个文件，比没有管理界面更糟，所以没有移植。

Desktop 与 Channel 同样经由 `open_app` 连接 `.mcp.json` 里的 server，但目前都没有专门的 MCP 状态界面。本层为 Surface 提供的接缝只有两个：`statuses()` 快照和 `on_mcp_change` 回调。

---

## 9. 配置参数

| 配置 | CLI 标志 | 环境变量 | 默认 | 说明 |
|---|---|---|---|---|
| `AppConfig.mcp_config` | `--mcp-config` | `OMICSCLAW_MCP_CONFIG` | `None` → `<workspace>/.mcp.json` | 配置文件路径 |
| `AppConfig.mcp_connect_timeout_s` | `--mcp-connect-timeout` | `OMICSCLAW_MCP_CONNECT_TIMEOUT_S` | `30.0` | 单个 server 启动加握手的上限；必须为正，否则 `ValueError` |
| `AppConfig.tool_timeout_s` | `--tool-timeout` | `OMICSCLAW_TOOL_TIMEOUT_S` | `600.0` | 引擎侧每次工具调用的上限，同时作为 HTTP 请求的 socket 超时 |

| 常量 | 值 | 位置 |
|---|---|---|
| `PROTOCOL_VERSION` | `"2025-06-18"` | `client.py` |
| `SUPPORTED_PROTOCOL_VERSIONS` | `2024-11-05`, `2025-03-26`, `2025-06-18` | `client.py` |
| `MAX_TOOL_PAGES` | 100 | `client.py` |
| `DEFAULT_CONNECT_TIMEOUT_S` | 30.0 | `manager.py` |
| `DEFAULT_MAX_OUTPUT_CHARS` | 32,000 | `manager.py` |
| `MAX_MESSAGE_BYTES` | 8 MiB | `stdio.py` |
| `EXIT_GRACE_S` | 2.0 | `stdio.py` |
| `MAX_RESPONSE_BYTES` | 8 MiB | `streamable_http.py` |
| `DEFAULT_TIMEOUT_S` | 600.0 | `streamable_http.py` |
| `MAX_TOOL_NAME_LENGTH` | 64 | `tools/mcp_tool.py` |

---

## 10. 已知限制

- **不支持旧的 HTTP+SSE（2024-11-05 双端点）和 websocket**，这类条目会被拒绝并说明原因。
- **HTTP 事件流里 server 发来的请求只会被跳过，不作答**；只有 stdio 会回应 `ping`。
- **HTTP 请求被取消后不发 `notifications/cancelled`**，它的 daemon 线程最迟在 socket 超时（等于 `tool_timeout_s`，默认 600 s）后退出。
- **会话过期（HTTP 404）不自动重连**，需要重启进程。
- **工具表在进程生命周期内固定。** 修改 `.mcp.json` 要重启才生效；`notifications/tools/list_changed` 被忽略。
- **server 的 `instructions` 只记录在 `ServerStatus.info` 中，没有注入 system prompt。**
- **MCP 工具串行执行**，同一 turn 里多个 MCP 调用会排队。
- **每次 MCP 调用都要审批**（默认 `ASK`）。想减少提示，只能写 `allow` 规则、开 `auto-approve`，或者在部署代码里重新注册策略。
- **权限 gate 每次调用只读一个"主参数"**（schema 里第一个必填 string 属性）。例如 MCP 的 `move_file(source, destination)` 按 `source` 判断，受保护路径检查看不到 `destination`（`permission/gate.py`）。
- **`/help` 中 `/mcp` 的说明文字过时**（第 8 节）。
- **本层还没有和真实的第三方 MCP server 通信过。** 测试用的是 `tests/mcp/fake_server.py` 起的真实子进程和本机回环 HTTP server，覆盖了 JSON 与 SSE 两种答复，但 npx 包、远端服务的兼容性没有实测。

---

## 11. 调试与常见问题

**server 显示 `failed`**

先看启动日志里的 `MCP server <name> failed: ...` 行，再用 `/mcp` 确认状态。常见原因：

| 报错片段 | 原因 |
|---|---|
| `cannot start 'npx': ...` | 可执行程序不在 `PATH` 中。注意子进程只继承 `PATH` 等少数变量 |
| `environment variable X is not set` | `.mcp.json` 里用了 `${X}` 却没有导出；可以改用 `${X:-default}` |
| `did not finish connecting within 30s` | 冷启动慢（`npx` 首次下载依赖）。可以调大 `--mcp-connect-timeout` |
| `the server chose protocol version '...'` | server 只支持本客户端不认的协议版本 |
| `... redirected (HTTP 30x) to ...; redirects are not followed` | 把 `url` 改成最终地址 |
| `HTTP 401 from https://host/path?…` | `headers` 里的鉴权不对；URL 已经脱敏 |
| `the server closed its output (exit code N; stderr: ...)` | server 启动后崩溃，stderr 尾部就是线索 |
| `transport 'sse' is not supported` | 旧 SSE 传输；换成 streamable http 端点 |

**工具没出现**

- 检查 `tools` 白名单拼写。日志里会有 `skipped <name>: named in 'tools' but not offered`。
- 检查是否撞名：`skipped <tool>: mcp__… is already taken`。
- 检查条目是否 `enabled: false` / `disabled: true`。

**模型不调用某个工具**

MCP 工具的描述直接来自 server 的 `tools/list`，只加了 `[MCP:<server>]` 前缀。描述质量不好时模型可能不会选它，这需要改 server 端，或者在 `OMICSCLAW.md` 里给出使用提示。

**每次都弹审批**

这是默认行为。可以在 `<workspace>/.omicsclaw/settings.json` 里按注册名写 `allow` 规则，也可以在 CLI 的审批卡片上选 `a`，为这一次的确切调用写一条 allow 规则。

**组学场景提示**：通过 MCP 调用远端服务时，参数会离开本机。`SAFETY_RULES` 第 1 条是遗传数据不离开本机，审批卡片上的参数预览就是让人在放行前确认参数里没有样本标识或序列。本地 stdio server 的卡片写作 `via local process <command>`，远端的写作 `via remote <url>`。

---

## 12. 参考

- 计划 0034 `docs/plans/0034-mcp-layer.md`：§2 能力清单与处置，§4 Q1–Q8 关键裁决，§7 已知限制，附录 A 审计与修复。
- 计划 0053 `docs/plans/0053-mcp-readonly-hint-parallel.md`：按 `readOnlyHint` 并行（计划，未实现）。
- `docs/FRAMEWORK-REBUILD.md` Step 6.5。

---

## 13. 文件索引

| 文件 | 职责 |
|---|---|
| `omicsclaw/mcp/__init__.py` | 公共接口 |
| `omicsclaw/mcp/config.py` | `MCPConfig`、`ServerConfig`、`TransportKind`、`RejectedServer`、`load_mcp_config`、`parse_mcp_config`、`MCPConfigError` |
| `omicsclaw/mcp/transport.py` | `Transport` Protocol、JSON-RPC 帧（`request`/`notification`/`classify`/`result_of`）、错误类型 |
| `omicsclaw/mcp/stdio.py` | `StdioTransport`、`child_environment`、`INHERITED_ENV_VARS` |
| `omicsclaw/mcp/streamable_http.py` | `HTTPTransport`、`redact_url`、`event_messages`、`json_messages` |
| `omicsclaw/mcp/client.py` | `MCPClient`、`RemoteTool`、`ServerInfo`、`render_result`、`MCPToolError` |
| `omicsclaw/mcp/manager.py` | `MCPManager`、`ServerState`、`ServerStatus`、`ToolDetail`、`open_transport`、`origin_of`、`truncate_output` |
| `omicsclaw/tools/mcp_tool.py` | `MCPTool`、`mcp_tool_name`、`sanitize_mcp_name` |
| `omicsclaw/tools/preview.py` | `preview_arguments`：审批卡片的参数预览 |
| `omicsclaw/entry/assembly.py` | `open_app`、`build_app(mcp=)`、`AgentApp.mcp`、`AgentApp.aclose`、`_log_mcp_outcome` |
| `omicsclaw/entry/config.py` | `mcp_config`、`mcp_connect_timeout_s`、`mcp_config_path()` |
| `omicsclaw/entry/cli/_repl.py` | `Repl._mcp`（`/mcp`） |
| `tests/mcp/` | 配置、stdio 真实子进程、HTTP 回环（JSON/SSE）、客户端、manager、分层 |
| `tests/tools/test_mcp_tool.py` | 命名、策略、审批 |
| `tests/entry/test_open_app.py` | 接线：快照与预算、失败 server、关闭、ReAct 端到端调用 MCP 工具 |
